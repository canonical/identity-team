import json
import asyncio
from typing import List

import httpx

from config import Endpoints
from models import IdentityRecord, ClientRecord
from hydra_flow import run_hydra_flow

async def run_load(setup_path: str, logins_per_user: int,
                   concurrency: int, enable_refresh: bool):
    with open(setup_path) as f:
        raw = json.load(f)

    identities: List[IdentityRecord] = [IdentityRecord(**i) for i in raw["identities"]]
    clients: List[ClientRecord] = [ClientRecord(**c) for c in raw["clients"]]

    endpoints = Endpoints()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, verify=False) as http_client:
        sem = asyncio.Semaphore(concurrency)
        total = len(identities) * logins_per_user
        done = 0
        failed = 0

        async def worker(identity: IdentityRecord, client_conf: ClientRecord):
            nonlocal done, failed
            async with sem:
                try:
                    await run_hydra_flow(
                        endpoints,
                        http_client,
                        client_conf.client_id,
                        client_conf.client_secret,
                        client_conf.redirect_uri,
                        subject=identity.email,
                        scope="openid offline",
                        enable_refresh=enable_refresh,
                    )
                    done += 1
                except Exception as e:
                    failed += 1
                    print(f"[flow] {identity.email} failed: {e}")
                if (done + failed) % 100 == 0:
                    print(f"[progress] flows: {done}/{total}, failed: {failed}")

        tasks = []
        for idx, identity in enumerate(identities):
            client_conf = clients[idx % len(clients)]
            for _ in range(logins_per_user):
                tasks.append(asyncio.create_task(worker(identity, client_conf)))

        print(f"[run] starting {len(tasks)} Hydra flows with concurrency={concurrency}")
        await asyncio.gather(*tasks)
        print(f"[run] completed. success={done}, failed={failed}")
