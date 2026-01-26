import asyncio
import json
import logging
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import Playwright, async_playwright, Page, Browser

from config import Endpoints
from models import ClientRecord, IdentityRecord
from totp import generate_totp


logger = logging.getLogger(__name__)


async def user_password_login(page: Page, user_email: str, user_password: str) -> None:
    """Get a page on the IDP login page and login the user."""
    logger.info("Signing in to dex")
    await page.get_by_label("Email").fill(user_email)
    await page.get_by_label("Password").fill(user_password)
    await page.get_by_role("button", name="Sign in", exact=True).click()


async def perform_login_flow(
    browser: Browser,
    identity: IdentityRecord,
    client_conf: ClientRecord,
    endpoints: Endpoints,
    http_client: httpx.AsyncClient,
    enable_refresh: bool,
    retries: int = 3,
) -> bool:
    for attempt in range(1, retries + 1):
        try:
            context = await browser.new_context(ignore_https_errors=True)
            # Block unnecessary resources to speed up page load
            await context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ["image", "media", "font"]
                else route.continue_(),
            )
            page = await context.new_page()

            # Go to auth page
            auth_url = (
                f"{endpoints.hydra_public}/oauth2/auth?"
                f"client_id={client_conf.client_id}&"
                f"redirect_uri={client_conf.redirect_uri}&"
                f"response_type=code&"
                f"scope=openid+email+profile+offline_access&"
                f"state=state-{identity.email}"
            )
            await page.goto(auth_url)

            # Password step
            await user_password_login(page, identity.email, identity.password)

            # TOTP step
            totp_code = generate_totp(identity.totp_secret)
            await page.fill('input[name="totp_code"]', totp_code)
            await page.get_by_role("button", name="Sign in").click()

            await page.wait_for_url("**/callback*")
            parsed = urlparse(page.url)
            code = parse_qs(parsed.query).get("code", [None])[0]
            if not code:
                raise RuntimeError("No code in redirect URL")

            # Exchange code for tokens
            token_resp = await http_client.post(
                f"{endpoints.hydra_public}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": client_conf.redirect_uri,
                },
                auth=(client_conf.client_id, client_conf.client_secret),
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()

            # Refresh tokens if enabled
            if enable_refresh and "refresh_token" in tokens:
                for _ in range(10):
                    r = await http_client.post(
                        f"{endpoints.hydra_public}/oauth2/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": tokens["refresh_token"],
                        },
                        auth=(client_conf.client_id, client_conf.client_secret),
                    )
                    r.raise_for_status()
                    tokens = r.json()

            await context.close()
            return True

        except Exception as e:
            print(f"[login] {identity.email} attempt {attempt} failed: {e}")
            if attempt == retries:
                return False


async def run_load(
    setup_path: str, logins_per_user: int, concurrency: int, enable_refresh: bool
):
    with open(setup_path) as f:
        raw = json.load(f)

    identities = [IdentityRecord(**i) for i in raw["identities"]]
    clients = [ClientRecord(**c) for c in raw["clients"]]

    endpoints = Endpoints()
    async with httpx.AsyncClient(timeout=30.0, verify=False) as http_client, async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(concurrency)
        total = len(identities) * logins_per_user
        done = 0
        failed = 0

        async def worker(identity: IdentityRecord, client_conf: ClientRecord):
            nonlocal done, failed
            async with sem:
                ok = await perform_login_flow(
                    browser, identity, client_conf, endpoints, http_client, enable_refresh
                )
                if ok:
                    done += 1
                else:
                    failed += 1
                if (done + failed) % 100 == 0:
                    print(f"[progress] logins: {done}/{total}, failed: {failed}")

        tasks = []
        for idx, identity in enumerate(identities):
            client_conf = clients[idx % len(clients)]
            for _ in range(logins_per_user):
                tasks.append(asyncio.create_task(worker(identity, client_conf)))

        print(f"[run] starting {len(tasks)} login flows with concurrency={concurrency}")
        await asyncio.gather(*tasks)
        print(f"[run] completed. success={done}, failed={failed}")
        await browser.close()
