#!/bin/bash
set -e

# Default number of rows
ROWS=${1:-100000}
OUTPUT_FILE="populate_hydra_bulk.sql"
NID="00000000-0000-0000-0000-000000000000"
CLIENT_COUNT=50

echo "Generating SQL for $ROWS flows into $OUTPUT_FILE..."

# Write the header for the SQL file
echo "-- Bulk load data for hydra_oauth2_flow and dependencies" > "$OUTPUT_FILE"
echo "BEGIN;" >> "$OUTPUT_FILE"
echo "SET session_replication_role = 'replica';" >> "$OUTPUT_FILE" # Disable triggers/constraints check temporarily if needed, but we will try to be correct.

# 1. Networks
echo "-- Populating networks" >> "$OUTPUT_FILE"
echo "INSERT INTO public.networks (id, created_at, updated_at) VALUES ('$NID', NOW(), NOW()) ON CONFLICT (id) DO NOTHING;" >> "$OUTPUT_FILE"

# 2. Clients
echo "-- Populating hydra_client" >> "$OUTPUT_FILE"
echo "CREATE TEMP TABLE tmp_hydra_client (LIKE public.hydra_client INCLUDING DEFAULTS);" >> "$OUTPUT_FILE"
echo "COPY tmp_hydra_client (id, nid, client_name, client_secret, scope, owner, policy_uri, tos_uri, client_uri, logo_uri, sector_identifier_uri, jwks, jwks_uri, pk_deprecated, metadata, redirect_uris, grant_types, response_types, audience, allowed_cors_origins, contacts, request_uris) FROM stdin;" >> "$OUTPUT_FILE"

awk -v count="$CLIENT_COUNT" -v nid="$NID" 'BEGIN {
    for (i = 1; i <= count; i++) {
        # Using tabs as delimiters
        # Note: Empty strings for text fields that are NOT NULL but have no default
        printf "client_app_%d\t%s\tClient %d\tsecret\topenid\towner\t\t\t\t\t\t{}\t\t0\t\t[]\t[]\t[]\t[]\t[]\t[]\t[]\n", i, nid, i
    }
}' /dev/null >> "$OUTPUT_FILE"
echo "\." >> "$OUTPUT_FILE"
echo "INSERT INTO public.hydra_client SELECT * FROM tmp_hydra_client ON CONFLICT DO NOTHING;" >> "$OUTPUT_FILE"
echo "DROP TABLE tmp_hydra_client;" >> "$OUTPUT_FILE"

# 3. Authentication Sessions
echo "-- Populating hydra_oauth2_authentication_session" >> "$OUTPUT_FILE"
echo "CREATE TEMP TABLE tmp_auth_session (LIKE public.hydra_oauth2_authentication_session INCLUDING DEFAULTS);" >> "$OUTPUT_FILE"
echo "COPY tmp_auth_session (id, nid, subject, authenticated_at, remember) FROM stdin;" >> "$OUTPUT_FILE"

awk -v rows="$ROWS" -v nid="$NID" 'BEGIN {
    for (i = 1; i <= rows; i++) {
        printf "session_%09d\t%s\tuser%d@example.com\tNOW()\tf\n", i, nid, i
    }
}' /dev/null >> "$OUTPUT_FILE"
echo "\." >> "$OUTPUT_FILE"
echo "INSERT INTO public.hydra_oauth2_authentication_session SELECT * FROM tmp_auth_session ON CONFLICT DO NOTHING;" >> "$OUTPUT_FILE"
echo "DROP TABLE tmp_auth_session;" >> "$OUTPUT_FILE"

# 4. Flows
echo "-- Populating hydra_oauth2_flow" >> "$OUTPUT_FILE"
echo "CREATE TEMP TABLE tmp_hydra_flow (LIKE public.hydra_oauth2_flow INCLUDING DEFAULTS);" >> "$OUTPUT_FILE"
# We list specific columns to rely on database defaults for timestamps and other fields where appropriate
echo "COPY tmp_hydra_flow (login_challenge, login_verifier, login_csrf, subject, request_url, login_skip, client_id, state, login_remember, login_remember_for, acr, login_was_used, forced_subject_identifier, context, consent_skip, consent_remember, session_access_token, session_id_token, consent_was_used, nid, requested_scope, login_session_id) FROM stdin;" >> "$OUTPUT_FILE"

# Generate the data rows using awk
# Tab (\t) is the default delimiter for COPY
# \N would be used for NULL, but here we use empty strings for text fields to match NOT NULL constraints (e.g., forced_subject_identifier)
awk -v rows="$ROWS" -v nid="$NID" -v client_count="$CLIENT_COUNT" 'BEGIN {
    for (i = 1; i <= rows; i++) {
        client_idx = (i % client_count) + 1
        printf "challenge_%09d\tverifier_%09d\tcsrf_%09d\tuser%d@example.com\thttps://hydra.example.com/oauth2/auth?client_id=client_app_%d\tf\tclient_app_%d\t1\tf\t0\t0\tf\t\t{}\tf\tf\t{}\t{}\tf\t%s\t[\"openid\"]\tsession_%09d\n", i, i, i, i, client_idx, client_idx, nid, i
    }
}' /dev/null >> "$OUTPUT_FILE"

# End the COPY command (matched by \.)
echo "\." >> "$OUTPUT_FILE"

# Explicitly select columns excluding 'expires_at' which is GENERATED ALWAYS
FLOW_COLS="login_challenge, login_verifier, login_csrf, subject, request_url, login_skip, client_id, requested_at, login_initialized_at, oidc_context, login_session_id, state, login_remember, login_remember_for, login_error, acr, login_authenticated_at, login_was_used, forced_subject_identifier, context, consent_challenge_id, consent_skip, consent_verifier, consent_csrf, consent_remember, consent_remember_for, consent_handled_at, consent_error, session_access_token, session_id_token, consent_was_used, nid, requested_scope, requested_at_audience, amr, granted_scope, granted_at_audience, login_extend_session_lifespan, identity_provider_session_id, device_challenge_id, device_code_request_id, device_verifier, device_csrf, device_user_code_accepted_at, device_was_used, device_handled_at, device_error"
echo "INSERT INTO public.hydra_oauth2_flow ($FLOW_COLS) SELECT $FLOW_COLS FROM tmp_hydra_flow ON CONFLICT DO NOTHING;" >> "$OUTPUT_FILE"
echo "DROP TABLE tmp_hydra_flow;" >> "$OUTPUT_FILE"
echo "COMMIT;" >> "$OUTPUT_FILE"

echo "Done. Generated $ROWS rows."
echo "To apply the data, run:"
echo "  psql -d <your_database_name> -f $OUTPUT_FILE"
