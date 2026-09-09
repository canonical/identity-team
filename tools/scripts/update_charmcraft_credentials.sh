#!/usr/bin/env bash

# Helper script for updating the CHARMCRAFT_CREDENTIALS secret in all charm repos.
#
# Usage:
#   1. Using environment variable:
#      export CHARMCRAFT_CREDENTIALS="<token>"
#      ./tools/scripts/update_charmcraft_credentials.sh
#
#   2. Using an exported credentials file:
#      ./tools/scripts/update_charmcraft_credentials.sh path/to/charmcraft.auth
#
#   3. Interactive generation using charmcraft (1 year TTL):
#      ./tools/scripts/update_charmcraft_credentials.sh --generate
#
#   4. Dry run (preview repos without making changes):
#      ./tools/scripts/update_charmcraft_credentials.sh --dry-run
#
# Steps when updating credentials:
# 1. Generate or retrieve fresh credentials
# 2. Run this script to update all charm repos
# 3. Store the new credentials in Bitwarden for team reference

set -eo pipefail

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] [CREDENTIALS_FILE]

Update CHARMCRAFT_CREDENTIALS secret across all charm repositories.

Arguments:
  CREDENTIALS_FILE         Path to a file containing exported charmcraft credentials

Options:
  -g, --generate           Generate credentials interactively with 'charmcraft login' (1 year TTL)
  -d, --dry-run            Display target repositories without setting secrets
  -h, --help               Show this help message and exit

Environment Variables:
  CHARMCRAFT_CREDENTIALS   Base64-encoded charmcraft authentication token

Examples:
  CHARMCRAFT_CREDENTIALS="<token>" $(basename "$0")
  $(basename "$0") /path/to/credentials.auth
  $(basename "$0") --generate
  $(basename "$0") --dry-run
EOF
}

DRY_RUN=false
GENERATE=false
INPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -g|--generate)
            GENERATE=true
            shift
            ;;
        -*)
            echo "Error: Unknown option '$1'" >&2
            show_help >&2
            exit 1
            ;;
        *)
            if [[ -z "$INPUT_FILE" ]]; then
                INPUT_FILE="$1"
            else
                echo "Error: Multiple input files specified" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

source "$(dirname "$0")/repos_list.sh"

if [[ "$DRY_RUN" == true ]]; then
    echo "=== DRY RUN: The following ${#charms[@]} charm repositories will be updated ==="
    for repo in "${charms[@]}"; do
        echo " - canonical/$repo"
    done
    exit 0
fi

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo "Error: 'gh' CLI is required but not installed." >&2
    echo "Please install it: https://cli.github.com" >&2
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Error: 'gh' CLI is not authenticated. Please run 'gh auth login' first." >&2
    exit 1
fi

# Resolve credentials
if [[ "$GENERATE" == true ]]; then
    if ! command -v charmcraft &> /dev/null; then
        echo "Error: 'charmcraft' is required for --generate but not found." >&2
        echo "Please install charmcraft: sudo snap install charmcraft --classic" >&2
        exit 1
    fi

    TEMP_AUTH_FILE="$(mktemp --suffix=.auth)"
    trap 'rm -f "$TEMP_AUTH_FILE"' EXIT

    echo "Running 'charmcraft login' to export credentials (TTL: 365 days)..."
    # 31536000 seconds = 365 days
    charmcraft login --export="$TEMP_AUTH_FILE" --ttl=31536000

    if [[ ! -s "$TEMP_AUTH_FILE" ]]; then
        echo "Error: Failed to generate credentials or export file is empty." >&2
        exit 1
    fi

    CHARMCRAFT_CREDENTIALS="$(cat "$TEMP_AUTH_FILE")"
elif [[ -n "$INPUT_FILE" ]]; then
    if [[ ! -f "$INPUT_FILE" ]]; then
        echo "Error: File '$INPUT_FILE' not found." >&2
        exit 1
    fi
    CHARMCRAFT_CREDENTIALS="$(cat "$INPUT_FILE")"
fi

# Trim whitespace
CHARMCRAFT_CREDENTIALS="$(echo "$CHARMCRAFT_CREDENTIALS" | tr -d '[:space:]')"

if [[ -z "$CHARMCRAFT_CREDENTIALS" ]]; then
    echo "Error: CHARMCRAFT_CREDENTIALS is not set." >&2
    echo "" >&2
    show_help >&2
    exit 1
fi

echo "Updating CHARMCRAFT_CREDENTIALS across ${#charms[@]} charm repositories..."
echo ""

failed_repos=()

for repo in "${charms[@]}"; do
    echo -n "Updating canonical/$repo... "
    if echo "$CHARMCRAFT_CREDENTIALS" | gh secret -R "https://github.com/canonical/$repo" set CHARMCRAFT_CREDENTIALS; then
        echo "Done"
    else
        echo "FAILED"
        failed_repos+=("$repo")
    fi
done

echo ""
if [[ ${#failed_repos[@]} -eq 0 ]]; then
    echo "Successfully updated CHARMCRAFT_CREDENTIALS for all ${#charms[@]} charm repositories!"
else
    echo "Warning: Failed to update ${#failed_repos[@]} repositories: ${failed_repos[*]}" >&2
fi

echo ""
echo "Reminder: Please update the newly generated credentials in Bitwarden for team reference."
