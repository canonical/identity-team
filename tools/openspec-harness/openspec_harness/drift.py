"""Config-driven OpenSpec code-to-spec drift checker.

The generic engine (`_file_contains`) reads declarative drift checks from
`openspec/drift-checks.yaml` instead of hardcoding repository-specific
invariants, so any `canonical/` repository can adopt it by shipping its own
drift-check manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DRIFT_CONFIG = "openspec/drift-checks.yaml"


def load_drift_config(config_path: Path) -> dict[str, Any]:
    """Load and minimally validate a declarative drift-checks manifest."""
    config_path = Path(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"drift config not found: {config_path}. Declare code-to-spec checks in "
            "openspec/drift-checks.yaml (see openspec-harness docs) or pass --config."
        )
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    checks = data.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError(f"{config_path}: expected a non-empty top-level 'checks:' mapping")
    for tid, entries in checks.items():
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError(f"{config_path}: checks.{tid} must be a list of check mappings")
        for entry in entries:
            if "id" not in entry or "path" not in entry:
                raise ValueError(f"{config_path}: checks.{tid} entries need 'id' and 'path'")
            if not entry.get("needles") and not entry.get("regex"):
                raise ValueError(
                    f"{config_path}: checks.{tid}.{entry.get('id')} needs 'needles' or 'regex'"
                )
    return data


def _file_contains(root: Path, entry: dict[str, Any]) -> tuple[bool, list[str]]:
    """Run one declarative check entry against the repository."""
    rel_path = str(entry["path"])
    p = root / rel_path
    must_exist = bool(entry.get("must_exist", True))
    if not p.is_file():
        return (not must_exist), ([] if not must_exist else [f"missing file {rel_path}"])

    text = p.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for needle in entry.get("needles") or ():
        if str(needle) not in text:
            missing.append(f"{rel_path} missing '{needle}'")
    for pattern in entry.get("regex") or ():
        if not re.search(str(pattern), text, re.M):
            missing.append(f"{rel_path} missing pattern /{pattern}/")
    return (not missing), missing


def check_drift(
    repo_root: Path,
    *,
    target_id: str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Run every declarative drift check and return a structured report."""
    repo_root = Path(repo_root).resolve()
    config_path = Path(config_path) if config_path else repo_root / DEFAULT_DRIFT_CONFIG
    checks_by_task: dict[str, list[dict[str, Any]]] = load_drift_config(config_path)["checks"]

    checks: list[dict[str, Any]] = []
    for task_id in sorted(checks_by_task):
        if target_id and target_id != task_id:
            continue
        for entry in checks_by_task[task_id]:
            ok, missing = _file_contains(repo_root, entry)
            cid = str(entry["id"])
            checks.append(
                {
                    "id": f"{task_id}:{cid}",
                    "ok": ok,
                    "detail": (
                        f"{entry['path']} satisfies {cid}"
                        if ok
                        else f"Drift in {task_id} ({cid}): {'; '.join(missing)}"
                    ),
                }
            )

    total = len(checks)
    ok_count = sum(1 for c in checks if c["ok"])
    failed = [c for c in checks if not c["ok"]]
    return {
        "repo_root": str(repo_root),
        "target_id": target_id or "all",
        "config": str(config_path),
        "checks_total": total,
        "checks_ok": ok_count,
        "checks_failed": len(failed),
        "all_checks_ok": total > 0 and len(failed) == 0,
        "checks": checks,
        "findings": [c["detail"] for c in failed],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check OpenSpec specs against the repository for code-to-spec drift."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument(
        "--config",
        default=None,
        help=f"Declarative drift-check config (default: <repo-root>/{DEFAULT_DRIFT_CONFIG})",
    )
    parser.add_argument("--target", default=None, help="Optional single spec or change id")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--quiet", action="store_true", help="Only output on failure")
    args = parser.parse_args(argv)

    repo = Path(args.repo_root)
    config = Path(args.config) if args.config else None
    report = check_drift(repo, target_id=args.target, config_path=config)
    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.quiet or not report["all_checks_ok"]:
        status = "OK" if report["all_checks_ok"] else "DRIFT_DETECTED"
        print(
            f"[check_openspec_drift] {status}: {report['checks_ok']}/{report['checks_total']} "
            f"code-to-spec checks aligned (config={report['config']})"
        )
        for f in report["findings"]:
            print(f"  - {f}")
    return 0 if report["all_checks_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))