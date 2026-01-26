import http
from typing import Dict
import httpx
from urllib.parse import urlencode

from config import Endpoints

async def start_auth_request(endpoints: Endpoints, http_client: httpx.AsyncClient,
                             client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    resp = await http_client.get(
        f"{endpoints.hydra_public}/oauth2/auth",
        params=params,
        follow_redirects=False,
    )
    # Hydra will redirect to login URL with login_challenge
    location = resp.headers.get("Location")
    if not location:
        raise RuntimeError(f"No Location header from /oauth2/auth: {resp.status_code} {resp.text}")
    return location

def extract_query_param(url: str, name: str) -> str:
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return parse_qs(parsed.query).get(name, [None])[0]

async def accept_login(endpoints: Endpoints, http_client: httpx.AsyncClient,
                       login_challenge: str, subject: str):
    resp = await http_client.put(
        f"{endpoints.hydra_admin}/oauth2/auth/requests/login/accept?login_challenge={login_challenge}",
        json={"subject": subject},
    )
    resp.raise_for_status()
    return resp.json()["redirect_to"]

async def accept_consent(endpoints: Endpoints, http_client: httpx.AsyncClient,
                         consent_challenge: str, scope: str):
    resp = await http_client.put(
        f"{endpoints.hydra_admin}/oauth2/auth/requests/consent/accept?consent_challenge={consent_challenge}",
        json={
            "grant_scope": scope.split(),
            "remember": False,
        },
    )
    resp.raise_for_status()
    return resp.json()["redirect_to"]

async def exchange_code_for_tokens(endpoints: Endpoints, http_client: httpx.AsyncClient,
                                   client_id: str, client_secret: str,
                                   code: str, redirect_uri: str) -> Dict:
    resp = await http_client.post(
        f"{endpoints.hydra_public}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
    )
    resp.raise_for_status()
    return resp.json()

async def refresh_tokens(endpoints: Endpoints, http_client: httpx.AsyncClient,
                         client_id: str, client_secret: str, refresh_token: str, times: int = 10):
    for _ in range(times):
        resp = await http_client.post(
            f"{endpoints.hydra_public}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
        )
        resp.raise_for_status()

async def run_hydra_flow(endpoints: Endpoints, http_client: httpx.AsyncClient,
                         client_id: str, client_secret: str, redirect_uri: str,
                         subject: str, scope: str = "openid offline",
                         enable_refresh: bool = False) -> None:
    # 1. Start auth request
    location = await start_auth_request(endpoints, http_client, client_id, redirect_uri, scope, state=f"state-{subject}")
    login_challenge = extract_query_param(location, "login_challenge")
    if not login_challenge:
        raise RuntimeError("No login_challenge in redirect")

    # 2. Accept login
    after_login = await accept_login(endpoints, http_client, login_challenge, subject)

    # 3. Visit oauth page with login_verifier
    resp = await http_client.get(after_login, follow_redirects=False)
    location = resp.headers.get("Location")
    if not location:
        raise RuntimeError("No Location header after login accept redirect")

    # 3. Accept consent
    after_consent = await accept_consent(endpoints, http_client, consent_challenge, scope)
    code = extract_query_param(after_consent, "code")
    if not code:
        raise RuntimeError("No code after consent accept")

    # 4. Exchange code for tokens
    tokens = await exchange_code_for_tokens(
        endpoints, http_client, client_id, client_secret, code, redirect_uri
    )

    # 5. Optional refresh storm
    if enable_refresh and "refresh_token" in tokens:
        await refresh_tokens(
            endpoints, http_client, client_id, client_secret, tokens["refresh_token"], times=10
        )
