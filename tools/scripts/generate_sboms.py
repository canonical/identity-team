#!/usr/bin/env python3
"""Canonical SSDLC Software Bill of Materials (SBOM) Generation Client.

Automates the generation of compliant SBOMs as specified in SEC0027:
"SSDLC - Software Bill of Materials (SBOM)".

Interacts with the Canonical SBOM Request REST API at:
https://sbom-request.canonical.com

Prerequisites:
    - Canonical VPN connection is required to reach the SBOM service.
    - Python 3.8+ with `requests`.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' package is required. Install it with: pip install requests")

API_BASE_URL = os.environ.get("SBOM_API_BASE", "https://sbom-request.canonical.com")
DEFAULT_DEPT = "charm_engineering"
DEFAULT_TEAM = "identity"

VALID_DEPARTMENTS = [
    "alliances", "channel", "charm_engineering", "cloud_engineering",
    "commercial_systems", "design", "devex", "devices_engineering",
    "excellence_engineering", "executive", "field_engineering", "finance",
    "marketing", "operations", "partner", "people", "product", "sre",
    "saas_engineering", "sales", "substrate", "support_engineering",
    "ubuntu_engineering", "web_engineering"
]

VALID_TEAMS = [
    "academy", "alliances_field", "analytics", "anbox", "app_armor",
    "business_data", "business_services", "ceph", "certification", "channel",
    "charm_collection", "cloud_gtm", "cloud_partner", "commercial_systems",
    "communication", "community", "compliance", "core", "customer_success",
    "dc_field", "debcrafters", "design", "design_system", "desktop",
    "developer_relations", "devices_field", "devices_sales", "documentation",
    "engineering", "enterprise_sales", "executive", "field", "finance",
    "foundations", "gsi_alliances", "growth_engineering", "hpc", "ihv_alliances",
    "is", "identity", "industrial", "industrial_standards", "infrastructure",
    "iot", "jaas", "juju", "kern_os", "kernel", "kernel_factory", "kubernetes",
    "lxd", "landscape", "launchpad", "legal", "maas", "managed_solutions", "mir",
    "multipass", "networking", "no_sql", "octo", "oem_enablement", "oem_qa",
    "observability", "open_stack", "partner", "partner_marketing",
    "platform_engineering", "portal", "pro", "product_management",
    "product_marketing", "project_management", "public_cloud", "rtos",
    "regional_marketing", "release_management", "renewals", "revenue_operations",
    "robotics", "rockcrafters", "runtimes", "sql", "sales_development", "sec_ops",
    "sectors", "security", "security_engineering", "security_standards", "server",
    "silicon_alliances", "sites", "snapd", "software_alliances",
    "solutions_engineering", "solutions_qa", "starcraft", "store", "support",
    "sustaining", "talent_development", "talent_experience", "talent_science",
    "telco", "telco_field", "telemetry", "ux", "ubuntu", "vanilla", "workplace",
    "workshop"
]


def format_department_info(dept: str) -> Dict[str, Any]:
    """Format department as predefined enum or custom value per OpenAPI schema."""
    norm = dept.strip().lower().replace(" ", "_").replace("-", "_")
    if norm in VALID_DEPARTMENTS:
        return {"type": "predefined", "value": norm}
    return {"type": "custom", "valueOther": dept}


def format_team_info(team: str) -> Dict[str, Any]:
    """Format team as predefined enum or custom value per OpenAPI schema."""
    norm = team.strip().lower().replace(" ", "_").replace("-", "_")
    if norm in VALID_TEAMS:
        return {"type": "predefined", "value": norm}
    return {"type": "custom", "valueOther": team}
# Mapping from identity-team repository names to Charmhub registered charm names
IDENTITY_CHARM_MAP: Dict[str, str] = {
    "hook-service-operator": "hook-service",
    "hydra-operator": "hydra",
    "identity-platform-login-ui-operator": "identity-platform-login-ui-operator",
    "kratos-external-idp-integrator": "kratos-external-idp-integrator",
    "kratos-operator": "kratos",
    "oauth2-proxy-k8s-operator": "oauth2-proxy-k8s",
    "openfga-operator": "openfga-k8s",
    "authentik-server-operator": "authentik-server",
    "authentik-worker-operator": "authentik-worker",
    "authentik-ldap-outpost-operator": "authentik-ldap-outpost",
}

# Mapping from identity-team rock names to container image references
IDENTITY_ROCK_MAP: Dict[str, str] = {
    "authentik-ldap-outpost-rock": "ghcr.io/canonical/authentik-ldap-outpost",
    "authentik-server-rock": "ghcr.io/canonical/authentik-server",
    "hook-service-rock": "ghcr.io/canonical/hook-service",
    "hydra-rock": "ghcr.io/canonical/hydra",
    "identity-platform-login-ui-rock": "ghcr.io/canonical/identity-platform-login-ui",
    "kratos-rock": "ghcr.io/canonical/kratos",
    "oauth2-proxy-rock": "ghcr.io/canonical/oauth2-proxy",
    "openfga-rock": "ghcr.io/canonical/openfga",
}

def get_default_email() -> str:
    """Determine the default Canonical email for the current user."""
    env_email = os.environ.get("CANONICAL_EMAIL")
    if env_email:
        return env_email
    user = getpass.getuser()
    if "@" in user:
        return user
    return f"{user}@canonical.com"


class SBOMClient:
    """Client for the Canonical SBOM Request REST API (SEC0027)."""

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        email: Optional[str] = None,
        department: str = DEFAULT_DEPT,
        team: str = DEFAULT_TEAM,
        dry_run: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email or get_default_email()
        self.department = department
        self.team = team
        self.dry_run = dry_run
        self.session = requests.Session()

    def check_connection(self) -> bool:
        """Check if the Canonical SBOM API is reachable (requires VPN)."""
        if self.dry_run:
            return True
        try:
            resp = self.session.get(f"{self.base_url}/openapi.json", timeout=4)
            return resp.status_code in (200, 301, 302, 401, 403, 404)
        except requests.RequestException:
            return False

    def require_connection(self) -> None:
        """Raise error if the Canonical SBOM API is unreachable."""
        if not self.check_connection():
            sys.exit(
                f"\n[!] Cannot reach {self.base_url}\n"
                "    The Canonical SBOM Request service is only available over the Canonical VPN.\n"
                "    Please connect to the VPN (e.g. `nmcli connection up <vpn-name>`) and retry,\n"
                "    or pass --dry-run / --local to run in offline mode.\n"
            )

    def request_store_artifact(
        self,
        artifact_type: str,
        name: str,
        version: str,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a request for an artifact from an upstream store (Charmhub, etc.)."""
        endpoint = f"{self.base_url}/api/v1/artifacts/{artifact_type}/store"

        payload: Dict[str, Any] = {
            "maintainer": "Canonical",
            "email": self.email,
            "version": str(version),
            "department": format_department_info(self.department),
            "team": format_team_info(self.team),
            "artifactName": name,
        }
        if extra_fields:
            payload.update(extra_fields)

        if self.dry_run:
            print(f"[DRY-RUN] POST {endpoint}")
            print(f"[DRY-RUN] Payload: {json.dumps(payload, indent=2)}")
            return {"status": "dry-run", "artifactId": f"dryrun-{name}-{version}"}

        self.require_connection()
        print(f"[*] Submitting SBOM request to {endpoint} for {name} (rev: {version})...")
        resp = self.session.post(endpoint, json=payload, timeout=30)
        if resp.status_code == 422:
            try:
                print(f"[!] Server validation error (422): {json.dumps(resp.json(), indent=2)}")
            except Exception:
                print(f"[!] Server validation error (422): {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        artifact_id = data.get("artifactId") or data.get("data", {}).get("artifactId") or data.get("id")
        print(f"[+] Request accepted! Artifact ID: {artifact_id}")
        return data

    def request_url_artifact(
        self,
        artifact_type: str,
        name: str,
        download_url: str,
        version: str = "latest",
    ) -> Dict[str, Any]:
        """Submit a request for an artifact via download URL per SEC0027."""
        endpoint = f"{self.base_url}/api/v1/artifacts/{artifact_type}/url"
        payload: Dict[str, Any] = {
            "maintainer": "Canonical",
            "email": self.email,
            "version": str(version),
            "department": format_department_info(self.department),
            "team": format_team_info(self.team),
            "artifactName": name,
            "downloadUrl": download_url,
        }
        if self.dry_run:
            print(f"[DRY-RUN] POST {endpoint}")
            print(f"[DRY-RUN] Payload: {json.dumps(payload, indent=2)}")
            return {"status": "dry-run", "artifactId": f"dryrun-{name}"}

        self.require_connection()
        print(f"[*] Submitting SBOM URL request to {endpoint} for {name} ({download_url})...")
        resp = self.session.post(endpoint, json=payload, timeout=30)
        if resp.status_code == 422:
            try:
                print(f"[!] Server validation error (422): {json.dumps(resp.json(), indent=2)}")
            except Exception:
                print(f"[!] Server validation error (422): {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        aid = data.get("artifactId") or data.get("data", {}).get("artifactId") or data.get("id")
        print(f"[+] Request accepted! Artifact ID: {aid}")
        return data
    def upload_artifact(
        self,
        artifact_type: str,
        file_path: Path,
        name: Optional[str] = None,
        version: Optional[str] = None,
        artifact_format: Optional[str] = None,
        compression_format: Optional[str] = None,
        chunk_size_mb: int = 2,
    ) -> Dict[str, Any]:
        """Upload an artifact file in chunks and trigger SBOM generation per OpenAPI spec."""
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        max_size = 8 * 1024 * 1024 * 1024  # 8 GB per SEC0027
        if file_size > max_size:
            raise ValueError(f"File exceeds maximum allowed size of 8GB: {file_size} bytes")

        artifact_name = name or file_path.stem
        fmt = artifact_format or ("charm" if artifact_type == "charm" else ("rock" if file_path.suffix == ".rock" else "tar"))

        init_endpoint = f"{self.base_url}/api/v1/artifacts/{artifact_type}/upload"
        init_payload: Dict[str, Any] = {
            "maintainer": "Canonical",
            "email": self.email,
            "version": str(version or "latest"),
            "department": format_department_info(self.department),
            "team": format_team_info(self.team),
            "artifactName": artifact_name,
            "artifactFormat": fmt,
            "filename": file_path.name,
        }
        if compression_format:
            init_payload["compressionFormat"] = compression_format

        if self.dry_run:
            print(f"[DRY-RUN] POST {init_endpoint}")
            print(f"[DRY-RUN] Payload: {json.dumps(init_payload, indent=2)}")
            print(f"[DRY-RUN] Would upload {file_path} ({file_size / (1024*1024):.2f} MB) in chunks.")
            return {"status": "dry-run", "artifactId": f"dryrun-{artifact_name}"}

        self.require_connection()
        print(f"[*] Initializing upload session for {file_path.name} ({file_size / (1024*1024):.2f} MB)...")
        resp = self.session.post(init_endpoint, json=init_payload, timeout=30)
        if resp.status_code == 422:
            try:
                print(f"[!] Server validation error (422): {json.dumps(resp.json(), indent=2)}")
            except Exception:
                print(f"[!] Server validation error (422): {resp.text}")
        resp.raise_for_status()
        init_data = resp.json()
        artifact_id = init_data.get("artifactId") or init_data.get("data", {}).get("artifactId")
        if not artifact_id:
            raise RuntimeError(f"Server response missing artifactId: {init_data}")

        print(f"[+] Artifact initialized. ID: {artifact_id}")

        chunk_size = chunk_size_mb * 1024 * 1024
        total_chunks = max(1, (file_size + chunk_size - 1) // chunk_size)
        chunk_endpoint = f"{self.base_url}/api/v1/artifacts/upload/chunk/{artifact_id}"

        with open(file_path, "rb") as f:
            for chunk_idx in range(1, total_chunks + 1):
                chunk_data = f.read(chunk_size)
                current_chunk_size = len(chunk_data)
                params = {
                    "resumableChunkNumber": chunk_idx,
                    "resumableTotalChunks": total_chunks,
                    "resumableChunkSize": chunk_size,
                    "resumableCurrentChunkSize": current_chunk_size,
                    "resumableTotalSize": file_size,
                    "resumableType": "application/octet-stream",
                    "resumableIdentifier": f"{artifact_id}-{file_path.name}",
                    "resumableFilename": file_path.name,
                }
                data = {
                    "resumableChunkNumber": str(chunk_idx),
                    "resumableTotalChunks": str(total_chunks),
                    "resumableChunkSize": str(chunk_size),
                    "resumableCurrentChunkSize": str(current_chunk_size),
                    "resumableTotalSize": str(file_size),
                    "resumableType": "application/octet-stream",
                    "resumableIdentifier": f"{artifact_id}-{file_path.name}",
                    "resumableFilename": file_path.name,
                }
                files = {"file": (file_path.name, chunk_data, "application/octet-stream")}
                if chunk_idx % 5 == 1 or chunk_idx == total_chunks:
                    print(f"  -> Uploading chunk {chunk_idx}/{total_chunks} ({(current_chunk_size * chunk_idx) / (1024*1024):.1f}/{file_size / (1024*1024):.1f} MB)...")
                chunk_uploaded = False
                chunk_resp = None
                for chunk_attempt in range(3):
                    chunk_resp = self.session.post(chunk_endpoint, params=params, data=data, files=files, timeout=120)
                    if chunk_resp.status_code == 200:
                        chunk_uploaded = True
                        break
                    time.sleep(2)
                if not chunk_uploaded and chunk_resp is not None:
                    chunk_resp.raise_for_status()
        complete_endpoint = f"{self.base_url}/api/v1/artifacts/upload/complete/{artifact_id}"
        print("[*] Finalizing and stitching upload chunks...")
        comp_resp = self.session.post(complete_endpoint, timeout=60)
        comp_resp.raise_for_status()
        print(f"[+] Artifact upload complete! Artifact ID: {artifact_id}")
        return comp_resp.json() if comp_resp.text else {"artifactId": artifact_id}

    def get_status(self, artifact_id: str, retries: int = 3, retry_delay: int = 3) -> Dict[str, Any]:
        """Fetch request and processing status for an artifact with retry resilience."""
        if self.dry_run:
            return {"status": "completed", "data": {"status": "completed", "sbomUrl": f"/reports/{artifact_id}"}}

        self.require_connection()
        endpoint = f"{self.base_url}/api/v1/artifacts/status/{artifact_id}"
        last_exc: Optional[Exception] = None

        for attempt in range(retries):
            try:
                resp = self.session.get(endpoint, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    # Backend can temporarily return 404 during internal state transitions (e.g. processing -> completed)
                    if attempt < retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return {"status": "transitioning", "data": {"status": "transitioning"}, "message": "Artifact status temporarily unavailable"}
                else:
                    resp.raise_for_status()
            except requests.RequestException as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(retry_delay)
                    continue

        if last_exc:
            return {"status": "network_retry", "data": {"status": "network_retry"}, "error": str(last_exc)}
        return {"status": "unknown", "data": {"status": "unknown"}}

    def download_sbom(
        self,
        artifact_id: str,
        output_dir: Path,
        retries: int = 5,
        arch: Optional[str] = None,
        artifact_name: Optional[str] = None,
        revision: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> Path:
        """Download the generated SBOM files for a completed artifact."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self.dry_run:
            arch_str = f"_{arch}" if arch and arch != "all" else ""
            type_str = f"_{artifact_type}" if artifact_type else ""
            rev_str = f"_{revision}" if revision else ""
            mock_file = output_dir / f"{artifact_name or artifact_id}{type_str}{rev_str}{arch_str}.spdx.json"
            print(f"[DRY-RUN] Would download SBOM to {mock_file}")
            return mock_file

        self.require_connection()
        endpoint = f"{self.base_url}/api/v1/artifacts/sbom/{artifact_id}"
        print(f"[*] Downloading SBOM artifact from {endpoint}...")

        resp = None
        for attempt in range(retries):
            try:
                resp = self.session.get(endpoint, stream=True, timeout=120)
                if resp.status_code == 200:
                    break
                if attempt < retries - 1:
                    time.sleep(3)
            except requests.RequestException:
                if attempt < retries - 1:
                    time.sleep(3)
                    continue
                raise

        if resp is None or resp.status_code != 200:
            if resp is not None:
                resp.raise_for_status()
            raise RuntimeError(f"Failed to download SBOM for {artifact_id}")

        content_disp = resp.headers.get("Content-Disposition", "")
        raw_filename = f"{artifact_id}.spdx.json"
        if "filename=" in content_disp:
            raw_filename = content_disp.split("filename=")[-1].strip('"\'')

        if raw_filename.endswith(".zip"):
            out_path = output_dir / raw_filename
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            print(f"[+] Saved SBOM package to: {out_path}")
            try:
                shutil.unpack_archive(str(out_path), str(output_dir))
                print(f"[+] Unpacked SBOM files into: {output_dir}")
            except Exception as e:
                print(f"[!] Note: Could not auto-unpack archive ({e}).")
            return out_path

        # Clean up filename: strip '.charm.best.SHAREABLE', '.best.SHAREABLE', etc.
        clean_name = raw_filename
        for suffix in [
            ".charm.best.SHAREABLE.spdx.json",
            ".best.SHAREABLE.spdx.json",
            ".best.spdx.json",
            ".spdx.json",
        ]:
            if clean_name.endswith(suffix):
                clean_name = clean_name[:-len(suffix)]
                break

        # Prefer using metadata to construct a clean, consistent filename
        if artifact_name:
            type_str = f"_{artifact_type}" if artifact_type else ""
            rev_str = f"_{revision}" if revision else ""
            arch_str = f"_{arch}" if arch and arch != "all" else ""
            final_filename = f"{artifact_name}{type_str}{rev_str}{arch_str}.spdx.json"
        else:
            arch_suffix = f"_{arch}" if arch and arch != "all" and not clean_name.endswith(f"_{arch}") else ""
            final_filename = f"{clean_name}{arch_suffix}.spdx.json"

        out_path = output_dir / final_filename
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

        print(f"[+] Saved SBOM package to: {out_path}")
        return out_path

    def poll_and_download(
        self,
        artifact_id: str,
        output_dir: Path,
        poll_interval: int = 30,
        timeout: int = 1800,
        arch: Optional[str] = None,
        artifact_name: Optional[str] = None,
        revision: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> Optional[Path]:
        """Poll the artifact status until completed and download results."""
        if self.dry_run:
            print("[DRY-RUN] Skipping poll loop.")
            return self.download_sbom(artifact_id, output_dir, arch=arch, artifact_name=artifact_name, revision=revision, artifact_type=artifact_type)

        print(f"[*] Monitoring SBOM generation for {artifact_id} (interval: {poll_interval}s, timeout: {timeout}s)...")
        start_time = time.time()
        consecutive_errors = 0

        while time.time() - start_time < timeout:
            data = self.get_status(artifact_id)
            status = data.get("status") or data.get("data", {}).get("status") or "unknown"
            elapsed = int(time.time() - start_time)

            if status in ("transitioning", "network_retry"):
                consecutive_errors += 1
                print(f"  [{elapsed}s] Status: {status} (backend updating record or network transient, retrying in {poll_interval}s...)")
                if consecutive_errors >= 10:
                    print(f"[!] Persistent error fetching status for {artifact_id}.")
                    return None
                time.sleep(poll_interval)
                continue

            consecutive_errors = 0
            meta = data.get("data", {}).get("metadata", {})
            scans = meta.get("completedScans", [])
            scan_str = f" (completed scans: {', '.join(scans)})" if scans else ""
            print(f"  [{elapsed}s] Status: {status}{scan_str}")

            if status in ("completed", "success", "done"):
                print("[+] SBOM generation succeeded!")
                return self.download_sbom(artifact_id, output_dir, arch=arch, artifact_name=artifact_name, revision=revision, artifact_type=artifact_type)
            if status in ("failed", "error"):
                print(f"[!] SBOM generation failed for {artifact_id}: {data}")
                return None

            time.sleep(poll_interval)

        print(f"[!] Timed out after {timeout} seconds waiting for {artifact_id}.")
        return None


def resolve_charm_entries(
    charm_name: str,
    channel: str = "latest/stable",
    target_arch: str = "all",
    fallback_channel: Optional[str] = "latest/edge",
) -> List[Dict[str, Any]]:
    """Query `juju info` to discover track, risk, revisions, and all supported architectures with fallback."""
    actual_charm = IDENTITY_CHARM_MAP.get(charm_name, charm_name)

    try:
        cmd = ["juju", "info", actual_charm, "--format", "json"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
    except Exception as e:
        print(f"[!] Warning: Could not query `juju info {actual_charm}` ({e}).")
        fallback_arch = "amd64" if target_arch == "all" else target_arch
        return [{"charm_name": actual_charm, "channel": channel, "revision": None, "arch": fallback_arch, "version": None}]

    channels_dict = data.get("channels", {})
    pref_track, pref_risk = channel.split("/", 1) if "/" in channel else ("latest", channel)
    pref_list = channels_dict.get(pref_track, {}).get(pref_risk, [])

    fall_list = []
    if fallback_channel and fallback_channel != channel:
        fall_track, fall_risk = fallback_channel.split("/", 1) if "/" in fallback_channel else ("latest", fallback_channel)
        fall_list = channels_dict.get(fall_track, {}).get(fall_risk, [])

    archs_to_find = ["amd64", "arm64"] if target_arch in ("all", "any") else [target_arch]
    entries: List[Dict[str, Any]] = []

    for a in archs_to_find:
        # Check preferred channel first
        found = False
        for item in pref_list:
            if a in item.get("architectures", []):
                entries.append({
                    "charm_name": actual_charm,
                    "channel": f"{pref_track}/{pref_risk}",
                    "revision": item.get("revision"),
                    "version": item.get("version"),
                    "arch": a,
                })
                found = True
                break
        # Fallback if not found in preferred channel
        if not found and fall_list:
            for item in fall_list:
                if a in item.get("architectures", []):
                    entries.append({
                        "charm_name": actual_charm,
                        "channel": f"{fallback_channel} (fallback)",
                        "revision": item.get("revision"),
                        "version": item.get("version"),
                        "arch": a,
                    })
                    found = True
                    break

    if not entries:
        print(f"[!] No release found for {actual_charm} on channel '{channel}' (or fallback '{fallback_channel}').")
        return []

    return entries

def generate_local_sbom(target: str, output_dir: Path, arch: Optional[str] = None, artifact_type: Optional[str] = None, artifact_name: Optional[str] = None) -> Path:
    """Generate an SPDX 2.3 JSON SBOM locally using Trivy (fallback/offline mode)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = Path(target)
    if target_path.exists():
        resolved = target_path.resolve()
        sanitized_name = artifact_name or (resolved.name if resolved.name else "project")
        type_str = f"_{artifact_type}" if artifact_type else ""
        out_file = output_dir / f"{sanitized_name}{type_str}.spdx.json"
    else:
        # Container image target e.g. "ghcr.io/canonical/authentik-server:latest"
        image_clean = target.split("/")[-1]
        name_part = artifact_name or image_clean.split(":")[0]
        tag_part = image_clean.split(":")[-1] if ":" in image_clean else "latest"
        arch_part = f"_{arch}" if arch and arch != "all" else ""
        type_str = f"_{artifact_type}" if artifact_type else "_rock"
        out_file = output_dir / f"{name_part}{type_str}_{tag_part}{arch_part}.spdx.json"

    trivy_bin = shutil.which("trivy")
    if not trivy_bin:
        sys.exit("Error: Trivy is not installed. Run `sudo snap install trivy` for local generation.")

    arch_desc = f" (platform: linux/{arch})" if arch and arch != "all" else ""
    print(f"[*] Running local Trivy SBOM generation on: {target}{arch_desc}...")
    if target_path.exists():
        # Filesystem target
        cmd = [
            trivy_bin,
            "fs",
            "--format",
            "spdx-json",
            "--output",
            str(out_file),
            str(target),
        ]
    else:
        # Container image target
        cmd = [
            trivy_bin,
            "image",
            "--image-src",
            "remote,docker",
            "--format",
            "spdx-json",
            "--output",
            str(out_file),
        ]
        if arch and arch != "all":
            cmd.extend(["--platform", f"linux/{arch}"])
        cmd.append(target)

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Trivy failed: {res.stderr}")
        sys.exit(1)

    print(f"[+] Successfully generated local SBOM: {out_file}")
    return out_file


def get_manifest_entries(image_base: str, tag: str, target_arch: str) -> Dict[str, Tuple[str, str]]:
    """Inspect remote OCI image manifest for a specific tag."""
    full_ref = f"{image_base}:{tag}"
    cmd = ["docker", "manifest", "inspect", full_ref]
    res = subprocess.run(cmd, capture_output=True, text=True)
    entries = {}
    if res.returncode == 0:
        try:
            data = json.loads(res.stdout)
            manifests = data.get("manifests", [])
            if manifests:
                for m in manifests:
                    a = m.get("platform", {}).get("architecture")
                    d = m.get("digest")
                    if d and (target_arch in ("all", "any") or a == target_arch):
                        entries[a] = (tag, d)
            else:
                arch = data.get("architecture", "amd64")
                digest = data.get("config", {}).get("digest", "")
                if not digest and "manifests" in data:
                    digest = data["manifests"][0].get("digest", "")
                if target_arch in ("all", "any") or arch == target_arch:
                    entries[arch] = (tag, digest)
        except Exception:
            pass
    return entries


def resolve_container_entries(
    image_ref: str,
    tag: str = "stable",
    target_arch: str = "all",
    fallback_tag: Optional[str] = "latest",
) -> List[Dict[str, str]]:
    """Inspect remote OCI image manifest on GHCR to find all available architectures and their digests with fallback."""
    base_img = image_ref.split(":")[0]
    archs_to_find = ["amd64", "arm64"] if target_arch in ("all", "any") else [target_arch]

    pref_entries = get_manifest_entries(base_img, tag, target_arch)
    fall_entries = (
        get_manifest_entries(base_img, fallback_tag, target_arch)
        if fallback_tag and fallback_tag != tag
        else {}
    )

    final_entries = []
    for a in archs_to_find:
        if a in pref_entries:
            t, d = pref_entries[a]
            final_entries.append({"arch": a, "tag": t, "digest": d})
        elif a in fall_entries:
            t, d = fall_entries[a]
            final_entries.append({"arch": a, "tag": f"{t} (fallback)", "digest": d})
    return final_entries


def resolve_container_digest(image_ref: str, tag: str = "stable", arch: str = "amd64", fallback_tag: Optional[str] = "latest") -> str:
    """Inspect remote OCI image manifest to resolve platform-specific sha256 digest without pulling."""
    entries = resolve_container_entries(image_ref, tag, target_arch=arch, fallback_tag=fallback_tag)
    if entries:
        return entries[0].get("digest", "")
    # Fallback to local inspect if already pulled
    full_ref = f"{image_ref}:{tag}" if ":" not in image_ref else image_ref
    insp = subprocess.run(["docker", "image", "inspect", full_ref, "--format", "{{json .RepoDigests}}"], capture_output=True, text=True)
    if insp.returncode == 0:
        try:
            digests = json.loads(insp.stdout.strip())
            for d in digests:
                if "@sha256:" in d:
                    return "sha256:" + d.split("@sha256:")[-1]
        except Exception:
            pass
    return ""


def pull_and_save_container(image_ref: str, temp_dir: Path, arch: str = "amd64") -> Tuple[Path, str]:
    """Pull container image for target platform, extract digest, and export as an uncompressed .tar file per SEC0027."""
    platform = f"linux/{arch}"
    clean_ref = image_ref.replace("/", "_").replace(":", "_")
    tar_path = temp_dir / f"{clean_ref}_{arch}.tar"
    print(f"[*] Pulling container image: {image_ref} (platform: {platform})...")
    pull_res = subprocess.run(["docker", "pull", "--platform", platform, image_ref], capture_output=True, text=True, check=True)
    if pull_res.stdout:
        print(pull_res.stdout.strip())

    digest = ""
    for line in pull_res.stdout.splitlines():
        if "Digest: sha256:" in line:
            digest = "sha256:" + line.split("Digest: sha256:")[-1].strip()
            break

    if not digest:
        insp = subprocess.run(["docker", "image", "inspect", image_ref, "--format", "{{json .RepoDigests}}"], capture_output=True, text=True)
        if insp.returncode == 0:
            try:
                digests = json.loads(insp.stdout.strip())
                for d in digests:
                    if "@sha256:" in d:
                        digest = "sha256:" + d.split("@sha256:")[-1]
                        break
            except Exception:
                pass

    if not digest:
        insp_id = subprocess.run(["docker", "image", "inspect", image_ref, "--format", "{{.Id}}"], capture_output=True, text=True)
        if insp_id.returncode == 0 and insp_id.stdout.strip().startswith("sha256:"):
            digest = insp_id.stdout.strip()

    if not digest:
        digest = f"sha256:{hashlib.sha256(image_ref.encode('utf-8')).hexdigest()}"

    print(f"[*] Resolved container digest: {digest}")
    print(f"[*] Saving container image to uncompressed tar: {tar_path}...")
    subprocess.run(["docker", "save", image_ref, "-o", str(tar_path)], check=True)
    return tar_path, digest


def build_parser() -> argparse.ArgumentParser:
    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument("--base-url", dest="sub_base_url", default=None, help=f"Base URL for SBOM API (default: {API_BASE_URL})")
    common_sub.add_argument("--email", dest="sub_email", default=None, help=f"Email for notification (default: {get_default_email()})")
    common_sub.add_argument("--dept", dest="sub_dept", default=None, help=f"Department (default: {DEFAULT_DEPT})")
    common_sub.add_argument("--team", dest="sub_team", default=None, help=f"Team (default: {DEFAULT_TEAM})")
    common_sub.add_argument("--output-dir", dest="sub_output_dir", default=None, help="Directory to save downloaded SBOMs (default: ./sboms)")
    common_sub.add_argument("--poll", dest="sub_poll", action="store_true", default=None, help="Wait and download when completed (default: true)")
    common_sub.add_argument("--no-poll", dest="sub_poll", action="store_false", default=None, help="Do not wait for completion; submit only")
    common_sub.add_argument("--poll-interval", dest="sub_poll_interval", type=int, default=None, help="Polling interval in seconds (default: 30)")
    common_sub.add_argument("--timeout", dest="sub_timeout", type=int, default=None, help="Max wait timeout in seconds (default: 1800)")
    common_sub.add_argument("--dry-run", dest="sub_dry_run", action="store_true", default=False, help="Print request details without contacting server")

    parser = argparse.ArgumentParser(
        description="Canonical SSDLC SBOM Generation Tool (SEC0027)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check connection to the SBOM REST API (requires VPN):
  %(prog)s check-vpn

  # List known Identity Team artifacts and Charmhub mappings:
  %(prog)s list-artifacts

  # Request SBOM for a charm from Charmhub (auto-resolves revision from `juju info`):
  %(prog)s charm --name hydra --channel latest/stable

  # Request SBOMs for all Identity Team charms in parallel/batch:
  %(prog)s batch-charms --channel latest/stable

  # Request SBOMs for all Identity Team rocks in batch (dry-run):
  %(prog)s batch-rocks --dry-run

  # Request SBOM for a container image (pulls, saves uncompressed .tar, uploads via REST API):
  %(prog)s container --image ghcr.io/canonical/hydra:latest

  # Check status of an artifact:
  %(prog)s status --id <artifactId>

  # Download completed SBOM:
  %(prog)s download --id <artifactId> --output-dir ./sboms

  # Generate local SBOM without VPN using Trivy:
  %(prog)s local --target ghcr.io/canonical/hydra:latest
        """,
    )
    parser.add_argument("--base-url", default=API_BASE_URL, help=f"Base URL for SBOM API (default: {API_BASE_URL})")
    parser.add_argument("--email", default=get_default_email(), help="Email for notification (default: current user)")
    parser.add_argument("--dept", default=DEFAULT_DEPT, help=f"Department (default: {DEFAULT_DEPT})")
    parser.add_argument("--team", default=DEFAULT_TEAM, help=f"Team (default: {DEFAULT_TEAM})")
    parser.add_argument("--output-dir", default="./sboms", help="Directory to save downloaded SBOMs (default: ./sboms)")
    parser.add_argument("--poll", action="store_true", default=True, help="Wait and download when completed (default: true)")
    parser.add_argument("--no-poll", dest="poll", action="store_false", help="Do not wait for completion; submit only")
    parser.add_argument("--poll-interval", type=int, default=30, help="Polling interval in seconds (default: 30)")
    parser.add_argument("--timeout", type=int, default=1800, help="Max wait timeout in seconds (default: 1800)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Print request details without contacting server")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: check-vpn
    subparsers.add_parser("check-vpn", parents=[common_sub], help="Verify reachability to Canonical SBOM service")

    # Subcommand: list-artifacts
    subparsers.add_parser("list-artifacts", parents=[common_sub], help="List known Identity Team charms, rocks, and repositories")
    # Subcommand: charm
    charm_p = subparsers.add_parser("charm", parents=[common_sub], help="Request SBOM for a Juju Charm")
    charm_p.add_argument("--name", required=True, help="Charm name (e.g. hydra, kratos, glauth-k8s)")
    charm_p.add_argument("--channel", default="latest/stable", help="Preferred channel (default: latest/stable)")
    charm_p.add_argument("--fallback-channel", default="latest/edge", help="Fallback channel if preferred channel or arch is missing (default: latest/edge)")
    charm_p.add_argument("--revision", help="Revision number (if omitted, auto-discovered via juju info)")
    charm_p.add_argument("--arch", default="all", choices=["amd64", "arm64", "all"], help="Architecture: amd64, arm64, or all (default: all)")
    charm_p.add_argument("--file", help="Path to local .charm file to upload instead of store download")

    # Subcommand: container
    container_p = subparsers.add_parser("container", parents=[common_sub], help="Request SBOM for a Container/Rock image")
    container_p.add_argument("--image", help="Container image tag (e.g. ghcr.io/canonical/hydra:latest)")
    container_p.add_argument("--tag", default="stable", help="Preferred container image tag (default: stable)")
    container_p.add_argument("--fallback-tag", default="latest", help="Fallback container image tag if preferred tag or arch is missing (default: latest)")
    container_p.add_argument("--file", help="Path to local container .tar file to upload")
    container_p.add_argument("--digest", help="Explicit container SHA256 digest (e.g. sha256:...)")
    container_p.add_argument("--name", help="Name for the container artifact")
    container_p.add_argument("--arch", default="all", choices=["amd64", "arm64", "all"], help="Architecture: amd64, arm64, or all (default: all)")
    container_p.add_argument("--store-pull", action="store_true", help="Request server-side pull from registry instead of local pull & upload (NOT SUPPORTED for GHCR due to server network restrictions)")
    # Subcommand: source
    source_p = subparsers.add_parser("source", parents=[common_sub], help="Submit source code repository for SBOM generation")
    source_p.add_argument("--path", help="Path to local repository or directory to upload")
    source_p.add_argument("--url", help="Public download URL for source archive (e.g. GitHub archive .tar.gz)")
    source_p.add_argument("--version", default="latest", help="Version identifier (default: latest)")
    source_p.add_argument("--name", help="Artifact name (default: directory name or url repo)")
    source_p.add_argument("--language", default="Golang", help="Primary language variant (e.g. Golang, Python, Node.js)")

    # Subcommand: batch-charms
    batch_p = subparsers.add_parser("batch-charms", parents=[common_sub], help="Request SBOMs for all Identity Team charms")
    batch_p.add_argument("--channel", default="latest/stable", help="Preferred channel (default: latest/stable)")
    batch_p.add_argument("--fallback-channel", default="latest/edge", help="Fallback channel if preferred channel or arch is missing (default: latest/edge)")
    batch_p.add_argument("--arch", default="all", choices=["amd64", "arm64", "all"], help="Architecture filter: amd64, arm64, or all (default: all)")
    batch_p.add_argument("--exclude", nargs="*", default=[], help="Charm names to exclude from processing")

    # Subcommand: batch-rocks
    batch_r = subparsers.add_parser("batch-rocks", parents=[common_sub], help="Request SBOMs for all Identity Team rocks/containers")
    batch_r.add_argument("--tag", default="stable", help="Preferred container image tag (default: stable)")
    batch_r.add_argument("--fallback-tag", default="latest", help="Fallback container image tag if preferred tag or arch is missing (default: latest)")
    batch_r.add_argument("--arch", default="all", choices=["amd64", "arm64", "all"], help="Architecture: amd64, arm64, or all (default: all)")
    batch_r.add_argument("--exclude", nargs="*", default=[], help="Rock names to exclude from processing (e.g. authentik-server-rock)")
    batch_r.add_argument("--store-pull", action="store_true", help="Request server-side pull from registry instead of local pull & upload (NOT SUPPORTED for GHCR due to server network restrictions)")
    batch_r.add_argument("--local", action="store_true", help="Generate locally with Trivy instead of uploading")
    # Subcommand: status
    status_p = subparsers.add_parser("status", parents=[common_sub], help="Check status of an artifact request")
    status_p.add_argument("--id", required=True, help="Artifact ID")

    # Subcommand: download
    dl_p = subparsers.add_parser("download", parents=[common_sub], help="Download SBOM for a completed artifact request")
    dl_p.add_argument("--id", required=True, help="Artifact ID")
    dl_p.add_argument("--name", help="Optional artifact name to use for the saved file")
    dl_p.add_argument("--arch", choices=["amd64", "arm64"], help="Optional architecture to include in the saved filename")

    # Subcommand: local
    local_p = subparsers.add_parser("local", parents=[common_sub], help="Generate local SPDX 2.3 JSON SBOM using Trivy (offline mode)")
    local_p.add_argument("--target", required=True, help="Image name or file/directory path")
    local_p.add_argument("--arch", default="amd64", choices=["amd64", "arm64", "all"], help="Architecture for container images (default: amd64)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Reconcile flags that may be provided either before or after subcommands
    args.dry_run = getattr(args, "sub_dry_run", False) or args.dry_run
    if getattr(args, "sub_base_url", None):
        args.base_url = args.sub_base_url
    if getattr(args, "sub_email", None):
        args.email = args.sub_email
    if getattr(args, "sub_dept", None):
        args.dept = args.sub_dept
    if getattr(args, "sub_team", None):
        args.team = args.sub_team
    if getattr(args, "sub_output_dir", None):
        args.output_dir = args.sub_output_dir
    if getattr(args, "sub_poll_interval", None) is not None:
        args.poll_interval = args.sub_poll_interval
    if getattr(args, "sub_timeout", None) is not None:
        args.timeout = args.sub_timeout
    if getattr(args, "sub_poll", None) is not None:
        args.poll = args.sub_poll

    client = SBOMClient(
        base_url=args.base_url,
        email=args.email,
        department=args.dept,
        team=args.team,
        dry_run=args.dry_run,
    )
    out_dir = Path(args.output_dir)

    if args.command == "check-vpn":
        print(f"[*] Checking connection to {client.base_url}...")
        if client.check_connection():
            print(f"[+] Success: {client.base_url} is reachable.")
        else:
            print(f"[!] Error: {client.base_url} is unreachable.")
            print("    Please ensure you are connected to the Canonical VPN (e.g. `nmcli connection up <vpn>`).")
            sys.exit(1)

    elif args.command == "list-artifacts":
        multi_arch_charms = {
            "authentik-ldap-outpost",
            "authentik-server",
            "glauth-k8s",
            "hydra",
            "identity-platform-login-ui-operator",
            "kratos",
            "ldap-integrator",
            "openfga-k8s",
        }
        print("=== Identity Team Charms (Repository -> Charmhub [Supported Archs]) ===")
        for repo, charm in sorted(IDENTITY_CHARM_MAP.items()):
            arch_str = "amd64, arm64" if charm in multi_arch_charms else "amd64"
            print(f"  {repo:<40} -> {charm:<36} [{arch_str}]")
        single_arch_rocks = {"hook-service-rock", "authentik-ldap-outpost-rock", "oauth2-proxy-rock"}
        print("\n=== Identity Team Rocks (Repository -> Container Image [Supported Archs]) ===")
        for rock, img in sorted(IDENTITY_ROCK_MAP.items()):
            arch_str = "amd64" if rock in single_arch_rocks else "amd64, arm64"
            print(f"  {rock:<40} -> {img:<36} [{arch_str}]")
    elif args.command == "charm":
        if args.file:
            res = client.upload_artifact("charm", Path(args.file), name=args.name)
            artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId")
            if artifact_id and args.poll:
                client.poll_and_download(str(artifact_id), out_dir, args.poll_interval, args.timeout, artifact_name=args.name, artifact_type="charm")
        else:
            fallback = getattr(args, "fallback_channel", "latest/edge")
            entries = resolve_charm_entries(args.name, args.channel, args.arch, fallback_channel=fallback)
            if not entries:
                sys.exit(1)

            for entry in entries:
                actual_name = entry["charm_name"]
                revision = args.revision or entry["revision"]
                arch = entry["arch"]
                print(f"[*] Resolved Charm: {actual_name} | Arch: {arch} | Channel: {args.channel} | Revision: {revision}")

                res = client.request_store_artifact(
                    artifact_type="charm",
                    name=actual_name,
                    version=revision,
                )
                artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId") or res.get("id")
                if artifact_id and args.poll:
                    charm_out = out_dir / actual_name / arch
                    client.poll_and_download(str(artifact_id), charm_out, args.poll_interval, args.timeout, arch=arch, artifact_name=actual_name, revision=f"r{revision}", artifact_type="charm")

    elif args.command == "container":
        if args.file:
            file_path = Path(args.file)
            digest = getattr(args, "digest", None)
            if not digest:
                with open(file_path, "rb") as f:
                    digest = f"sha256:{hashlib.sha256(f.read()).hexdigest()}"
            res = client.upload_artifact("container", file_path, name=args.name, version=digest, artifact_format="tar")
            artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId")
            if artifact_id and args.poll:
                client.poll_and_download(str(artifact_id), out_dir, args.poll_interval, args.timeout, artifact_name=args.name, artifact_type="rock")
        elif args.image:
            target_archs = ["amd64", "arm64"] if args.arch == "all" else [args.arch]
            tag = getattr(args, "tag", "stable")
            fallback_tag = getattr(args, "fallback_tag", "latest")
            img_ref = f"{args.image}:{tag}" if ":" not in args.image else args.image
            base_img = img_ref.split(":")[0]
            entries = resolve_container_entries(base_img, tag=tag, target_arch=args.arch, fallback_tag=fallback_tag)
            if not entries:
                entries = [{"arch": a, "tag": tag, "digest": ""} for a in target_archs]
            for entry in entries:
                arch = entry["arch"]
                entry_tag = entry.get("tag", tag)
                clean_tag = entry_tag.split()[0]
                effective_ref = f"{base_img}:{clean_tag}"
                art_name = f"{args.name or Path(base_img).name}_{arch}"
                if getattr(args, "store_pull", False) and entry.get("digest"):
                    digest = getattr(args, "digest", None) or entry.get("digest")
                    print(f"[*] Requesting server-side pull for {base_img} (tag: {entry_tag}, arch: {arch}, digest: {digest})...")
                    res = client.request_store_artifact(
                        artifact_type="container",
                        name=base_img,
                        version=digest,
                    )
                else:
                    # Default: Local pull & chunked upload
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tar_file, pull_digest = pull_and_save_container(effective_ref, Path(tmpdir), arch=arch)
                        res = client.upload_artifact(
                            "container",
                            tar_file,
                            name=art_name,
                            version=pull_digest,
                            artifact_format="tar",
                        )
                artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId") or res.get("id")
                if artifact_id and args.poll:
                    client.poll_and_download(str(artifact_id), out_dir / arch, args.poll_interval, args.timeout, arch=arch, artifact_name=Path(base_img).name, revision=clean_tag, artifact_type="rock")
    elif args.command == "source":
        if getattr(args, "url", None):
            raw_url = args.url.rstrip("/").split("?")[0]
            art_name = args.name or Path(raw_url).name.replace(".tar.gz", "").replace(".tar", "")
            res = client.request_url_artifact(
                "source",
                name=art_name,
                download_url=args.url,
                version=getattr(args, "version", "latest"),
            )
            artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId") or res.get("id")
            if artifact_id and args.poll:
                client.poll_and_download(str(artifact_id), out_dir, args.poll_interval, args.timeout, artifact_name=art_name, revision=getattr(args, "version", "latest"), artifact_type="source")
        elif getattr(args, "path", None):
            src_path = Path(args.path).resolve()
            with tempfile.TemporaryDirectory() as tmpdir:
                archive_path = Path(tmpdir) / f"{src_path.name}.tar.gz"
                print(f"[*] Packaging source directory {src_path} into {archive_path.name}...")
                shutil.make_archive(str(archive_path.with_suffix("").with_suffix("")), "gztar", root_dir=str(src_path))
                res = client.upload_artifact(
                    "source",
                    archive_path,
                    name=args.name or src_path.name,
                    version=getattr(args, "version", "latest"),
                    artifact_format="tar",
                    compression_format="gz",
                )
                artifact_id = res.get("artifactId") or res.get("data", {}).get("artifactId")

            if artifact_id and args.poll:
                client.poll_and_download(str(artifact_id), out_dir, args.poll_interval, args.timeout, artifact_name=args.name or src_path.name, revision=getattr(args, "version", "latest"), artifact_type="source")
        else:
            sys.exit("Error: Provide either --path <local_dir> or --url <archive_url>")

    elif args.command == "batch-charms":
        print(f"[*] Starting batch SBOM requests for {len(IDENTITY_CHARM_MAP)} Identity charms (Channel: {args.channel}, Arch: {args.arch}, Team: {args.team}, Dept: {args.dept})...")
        submitted: List[Dict[str, Any]] = []
        exclude_set = set(getattr(args, "exclude", []) or [])
        for repo, charm_name in sorted(IDENTITY_CHARM_MAP.items()):
            if repo in exclude_set or charm_name in exclude_set or any(ex in repo or ex in charm_name for ex in exclude_set):
                print(f"[*] Skipping excluded charm: {repo} ({charm_name})")
                continue
            fallback = getattr(args, "fallback_channel", "latest/edge")
            entries = resolve_charm_entries(charm_name, args.channel, args.arch, fallback_channel=fallback)
            for entry in entries:
                actual_name = entry["charm_name"]
                rev = entry["revision"]
                arch = entry["arch"]
                print(f"\n--- Submitting: {repo} ({actual_name}) [Arch: {arch}, Rev: {rev}] ---")
                try:
                    res = client.request_store_artifact(
                        artifact_type="charm",
                        name=actual_name,
                        version=rev,
                    )
                    aid = res.get("artifactId") or res.get("data", {}).get("artifactId") or res.get("id")
                    submitted.append({"repo": repo, "charm": actual_name, "arch": arch, "revision": rev, "artifactId": aid})
                except Exception as e:
                    print(f"[!] Failed to submit request for {actual_name} ({arch}): {e}")

        print("\n=== Batch Submission Summary ===")
        print(json.dumps(submitted, indent=2))

        if args.poll and not args.dry_run:
            print("\n[*] Polling and downloading SBOMs...")
            for item in submitted:
                aid = item.get("artifactId")
                if aid:
                    client.poll_and_download(str(aid), out_dir / item["charm"] / item["arch"], args.poll_interval, args.timeout, arch=item["arch"], artifact_name=item["charm"], revision=f"r{item['revision']}", artifact_type="charm")

    elif args.command == "batch-rocks":
        tag = getattr(args, "tag", "stable")
        fallback_tag = getattr(args, "fallback_tag", "latest")
        target_arch = args.arch
        print(f"[*] Starting batch SBOM processing for {len(IDENTITY_ROCK_MAP)} Identity rocks (Tag: {tag}, Fallback: {fallback_tag}, Arch: {target_arch}, Team: {args.team}, Dept: {args.dept})...")
        submitted: List[Dict[str, Any]] = []
        exclude_set = set(getattr(args, "exclude", []) or [])
        for rock_repo, base_img in sorted(IDENTITY_ROCK_MAP.items()):
            if rock_repo in exclude_set or any(ex in rock_repo for ex in exclude_set):
                print(f"[*] Skipping excluded rock: {rock_repo}")
                continue
            entries = resolve_container_entries(base_img, tag=tag, target_arch=target_arch, fallback_tag=fallback_tag)
            if not entries:
                fallback_archs = ["amd64", "arm64"] if target_arch == "all" else [target_arch]
                entries = [{"arch": a, "tag": tag, "digest": ""} for a in fallback_archs]

            for entry in entries:
                arch = entry["arch"]
                entry_tag = entry.get("tag", tag)
                clean_tag = entry_tag.split()[0]
                effective_ref = f"{base_img}:{clean_tag}"
                digest = entry.get("digest", "")
                print(f"\n--- Processing Rock: {rock_repo} ({base_img}:{entry_tag}) [Arch: {arch}] ---")
                rock_out = out_dir / rock_repo / arch
                if getattr(args, "local", False):
                    generate_local_sbom(effective_ref, rock_out, arch=arch, artifact_type="rock", artifact_name=Path(base_img).name)
                elif args.dry_run:
                    method = "Store Download" if getattr(args, "store_pull", False) else "Upload (local pull + chunked)"
                    print(f"[DRY-RUN] Method: {method}")
                    print(f"[DRY-RUN] Would submit {effective_ref} (platform: linux/{arch}, digest: {digest or 'auto'}) via {method} to container endpoint.")
                    print(f"[DRY-RUN] Metadata: team={args.team}, department={args.dept}, artifactName={rock_repo}_{arch}")
                    submitted.append({"rock": rock_repo, "image": effective_ref, "arch": arch, "digest": digest, "artifactId": f"dryrun-{rock_repo}-{arch}"})
                elif getattr(args, "store_pull", False) and digest:
                    try:
                        print(f"[*] Resolved digest: {digest}. Requesting server-side pull for {base_img} ({arch})...")
                        res = client.request_store_artifact(
                            artifact_type="container",
                            name=base_img,
                            version=digest,
                        )
                        aid = res.get("artifactId") or res.get("data", {}).get("artifactId") or res.get("id")
                        submitted.append({"rock": rock_repo, "image": effective_ref, "arch": arch, "digest": digest, "artifactId": aid})
                    except Exception as e:
                        print(f"[!] Failed to request store pull for rock {rock_repo} ({arch}): {e}")
                else:
                    # Default: Local pull & chunked upload
                    try:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            tar_file, pull_digest = pull_and_save_container(effective_ref, Path(tmpdir), arch=arch)
                            res = client.upload_artifact(
                                "container",
                                tar_file,
                                name=f"{rock_repo}_{arch}",
                                version=pull_digest or digest,
                                artifact_format="tar",
                            )
                            aid = res.get("artifactId") or res.get("data", {}).get("artifactId")
                            submitted.append({"rock": rock_repo, "image": effective_ref, "arch": arch, "digest": pull_digest or digest, "artifactId": aid})
                    except Exception as e:
                        print(f"[!] Failed to upload rock {rock_repo} ({arch}): {e}")
        print("\n=== Batch Rock Submission Summary ===")
        print(json.dumps(submitted, indent=2))

        if args.poll and not args.dry_run:
            print("\n[*] Polling and downloading SBOMs...")
            for item in submitted:
                aid = item.get("artifactId")
                if aid:
                    client.poll_and_download(str(aid), out_dir / item["rock"] / item["arch"], args.poll_interval, args.timeout, arch=item["arch"], artifact_name=Path(IDENTITY_ROCK_MAP[item["rock"]]).name, revision=tag, artifact_type="rock")
    elif args.command == "status":
        status_info = client.get_status(args.id)
        print(json.dumps(status_info, indent=2))
    elif args.command == "download":
        client.download_sbom(args.id, out_dir, arch=getattr(args, "arch", None), artifact_name=getattr(args, "name", None))

    elif args.command == "local":
        target_archs = ["amd64", "arm64"] if args.arch == "all" else [args.arch]
        for arch in target_archs:
            generate_local_sbom(args.target, out_dir, arch=arch, artifact_type="rock" if not Path(args.target).exists() else None)

if __name__ == "__main__":
    main()
