import asyncio
import json
from random import randint
from typing import List

import httpx

from config import DEFAULT_PASSWORD, DEFAULT_REDIRECT_URI, Endpoints
from models import ClientRecord, IdentityRecord, SetupData
from totp import generate_totp


def generate_user_email(i: int) -> str:
    return f"user{i:06d}@example.com"


def generate_client_id(i: int) -> str:
    return f"client{i:04d}"


async def get_session_token(
    email: str, password: str, endpoints: Endpoints, client: httpx.AsyncClient
) -> str:
    flow = await client.get(f"{endpoints.kratos_public}/self-service/login/api")
    flow.raise_for_status()
    data = flow.json()

    submit = await client.post(
        data["ui"]["action"].replace(endpoints.login_ui_base_url, endpoints.kratos_public),
        json={"identifier": email, "password": password, "method": "password"},
    )
    submit.raise_for_status()
    out = submit.json()
    return out["session_token"]


async def enroll_totp(
    identity_email: str, password: str, endpoints: Endpoints, client: httpx.AsyncClient
) -> str:
    session_token = await get_session_token(identity_email, password, endpoints, client)

    flow = await client.get(
        f"{endpoints.kratos_public}/self-service/settings/api",
        headers={"X-Session-Token": session_token},
    )
    flow.raise_for_status()
    data = flow.json()

    totp_secret = None
    for node in data["ui"]["nodes"]:
        if node["group"] == "totp" and node["attributes"].get("id") == "totp_secret_key":
            totp_secret = node["attributes"]["text"]["text"]
            break
    if not totp_secret:
        raise RuntimeError("No TOTP secret found in settings flow")

    code = generate_totp(totp_secret)

    submit = await client.post(
        data["ui"]["action"].replace(endpoints.login_ui_base_url, endpoints.kratos_public),
        json={"method": "totp", "totp_code": code},
        headers={"X-Session-Token": session_token},
    )
    submit.raise_for_status()
    return totp_secret


async def create_clients(
    num_clients: int, endpoints: Endpoints, client: httpx.AsyncClient
) -> List[ClientRecord]:
    clients = []
    for i in range(1, num_clients + 1):
        cid = generate_client_id(randint(1, 999999))
        resp = await client.post(
            f"{endpoints.hydra_admin}/clients",
            json={
                "client_id": cid,
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "redirect_uris": [DEFAULT_REDIRECT_URI],
                "scope": "openid email profile offline_access",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        clients.append(
            ClientRecord(
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                redirect_uri=data["redirect_uris"][0],
            )
        )
        if i % 10 == 0 or i == num_clients:
            print(f"[clients] created {i}/{num_clients}")
    return clients


async def create_identities(
    num_users: int,
    endpoints: Endpoints,
    client: httpx.AsyncClient,
    password: str = DEFAULT_PASSWORD,
) -> List[IdentityRecord]:
    identities = []
    for i in range(1, num_users + 1):
        email = generate_user_email(randint(1, 999999))
        resp = await client.post(
            f"{endpoints.kratos_admin}/admin/identities",
            json={
                "traits": {"email": email},
                "credentials": {"password": {"config": {"password": password}}},
            },
        )

        resp.raise_for_status()
        identity = resp.json()
        totp_secret = await enroll_totp(email, password, endpoints, client)

        identities.append(
            IdentityRecord(
                id=identity["id"],
                email=email,
                password=password,
                totp_secret=totp_secret,
            )
        )
        if i % 50 == 0 or i == num_users:
            print(f"[identities] created + TOTP enrolled {i}/{num_users}")
    return identities


async def create_identities_concurrent(
    num_users: int,
    endpoints: Endpoints,
    client: httpx.AsyncClient,
    password: str = DEFAULT_PASSWORD,
    concurrency: int = 50,
):
    sem = asyncio.Semaphore(concurrency)
    identities = []

    async def worker(i: int):
        email = generate_user_email(randint(1, 999999))
        async with sem:
            # 1. Create identity
            resp = await client.post(
                f"{endpoints.kratos_admin}/admin/identities",
                json={
                    "traits": {"email": email},
                    "credentials": {"password": {"config": {"password": password}}},
                },
            )
            resp.raise_for_status()
            identity = resp.json()

            # 2. Enroll TOTP
            totp_secret = await enroll_totp(email, password, endpoints, client)

            return IdentityRecord(
                id=identity["id"],
                email=email,
                password=password,
                totp_secret=totp_secret,
            )

    tasks = [asyncio.create_task(worker(i)) for i in range(1, num_users + 1)]

    # Collect results as they complete
    for idx, task in enumerate(asyncio.as_completed(tasks), start=1):
        identities.append(await task)
        if idx % 50 == 0 or idx == num_users:
            print(f"[identities] created + TOTP enrolled {idx}/{num_users}")

    return identities


async def run_setup(num_users: int, num_clients: int, output_path: str):
    endpoints = Endpoints()
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        clients = await create_clients(num_clients, endpoints, client)
        identities = await create_identities_concurrent(num_users, endpoints, client)

    data = SetupData(identities=identities, clients=clients)
    with open(output_path, "w") as f:
        json.dump(
            {
                "identities": [i.__dict__ for i in data.identities],
                "clients": [c.__dict__ for c in data.clients],
            },
            f,
        )
    print(f"[setup] written to {output_path}")
