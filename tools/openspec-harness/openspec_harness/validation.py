"""Config-driven OpenSpec structural, strict-CLI, and link validator.

The generic engine reads its structural thresholds from the optional
`validation:` block of the repository's `openspec/config.yaml`, so a
repository adopts it by declaring (or inheriting) settings rather than by
patching the validator:

    validation:
      max_requirement_chars: 500
      require_mermaid_in_design: true
      proposal_sections: [Why, What Changes, Non-goals, ...]
      design_sections: [Context, Goals, Risks]
      tasks_checkbox_sections: [Verification Suite, Documentation & Rollout]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.M)
REQ_BLOCK_RE = re.compile(
    r"^###\s+Requirement:\s*(.+?)\n(.*?)(?=^###\s+Requirement:|^####\s+Scenario:|^##\s+|\Z)",
    re.M | re.S,
)
SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$", re.M)
MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

DEFAULT_SETTINGS: dict[str, Any] = {
    "max_requirement_chars": 500,
    "require_mermaid_in_design": True,
    "proposal_sections": ("Why", "What Changes", "Non-goals", "Success Metrics", "Capabilities", "Impact"),
    "design_sections": ("Context", "Goals", "Risks"),
    "tasks_checkbox_sections": ("Verification Suite", "Documentation & Rollout"),
}

PLACEHOLDER_PURPOSE_PATTERNS = (
    "tbd - created by archiving change",
    "update purpose after archive",
    "tbd",
    "todo",
)

PLACEHOLDER_NOTES_PATTERNS = (
    "*(deviations from original plan or implementation discoveries will be recorded here during execution)*",
)


def load_validation_settings(workspace_root: Path) -> dict[str, Any]:
    """Merge `validation:` from `<workspace>/openspec/config.yaml` over the strict defaults."""
    cfg: dict[str, Any] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in DEFAULT_SETTINGS.items()}
    config_path = Path(workspace_root) / "openspec" / "config.yaml"
    if not config_path.is_file():
        return cfg
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return cfg
    overrides = data.get("validation")
    if not isinstance(overrides, dict):
        return cfg
    for key in DEFAULT_SETTINGS:
        if key in overrides:
            cfg[key] = overrides[key]
    return cfg


def _strip_code(md: str) -> str:
    """Remove fenced and inline code before scanning Markdown links."""
    no_fences = CODE_FENCE_RE.sub("", md)
    return INLINE_CODE_RE.sub("", no_fences)


def _extract_section(md: str, heading_prefix: str) -> str:
    """Return body text under the first `## <heading_prefix>` section."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading_prefix)}[^\n]*\n(.*?)(?=^##\s+|\Z)",
        re.M | re.S | re.I,
    )
    m = pattern.search(md)
    return m.group(1).strip() if m else ""


def _extract_numbered_section(md: str, name: str) -> str:
    """Return body text under `## <name>` or `## N. <name>` for any N."""
    pattern = re.compile(
        rf"^##\s+(?:\d+\.\s+)?{re.escape(name)}\s*\n(.*?)(?=^##\s+|\Z)",
        re.M | re.S | re.I,
    )
    m = pattern.search(md)
    return m.group(1).strip() if m else ""


def check_relative_links(md_path: Path, repo_root: Path) -> list[str]:
    """Verify every relative markdown link in `md_path` resolves on disk."""
    issues: list[str] = []
    text = _strip_code(md_path.read_text(encoding="utf-8", errors="replace"))
    rel_file = md_path.relative_to(repo_root) if md_path.is_relative_to(repo_root) else md_path
    for raw_target in MD_LINK_RE.findall(text):
        target = raw_target.strip().split()[0].strip("<>")
        if (
            not target
            or target.startswith(("#", "http://", "https://", "mailto:", "file://", "conversation://"))
        ):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (md_path.parent / path_part).resolve()
        if not resolved.exists():
            issues.append(
                f"{rel_file}: broken relative link '{target}' (resolved to {resolved})"
            )
    return issues


def check_spec_file(
    spec_path: Path, repo_root: Path, *, is_delta: bool, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Run granular checks on a main or delta `spec.md` file."""
    checks: list[dict[str, Any]] = []
    text = spec_path.read_text(encoding="utf-8", errors="replace")
    rel = str(spec_path.relative_to(repo_root) if spec_path.is_relative_to(repo_root) else spec_path)

    purpose = _extract_section(text, "Purpose")
    purpose_lower = purpose.lower().strip()
    has_purpose = bool(purpose_lower) and not any(
        p == purpose_lower or purpose_lower.startswith("tbd ")
        or "created by archiving change" in purpose_lower
        for p in PLACEHOLDER_PURPOSE_PATTERNS
    )
    checks.append(
        {
            "id": f"{rel}:purpose",
            "ok": has_purpose,
            "detail": (
                "Non-placeholder ## Purpose section present"
                if has_purpose
                else f"{rel}: missing or placeholder ## Purpose section"
            ),
        }
    )

    if is_delta:
        has_delta_header = bool(
            re.search(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b", text, re.M)
        )
        checks.append(
            {
                "id": f"{rel}:delta_headers",
                "ok": has_delta_header,
                "detail": (
                    "Delta requirement section header present"
                    if has_delta_header
                    else f"{rel}: missing ## ADDED/MODIFIED/REMOVED Requirements header"
                ),
            }
        )
    else:
        has_req_header = bool(re.search(r"^##\s+Requirements\b", text, re.M))
        checks.append(
            {
                "id": f"{rel}:requirements_header",
                "ok": has_req_header,
                "detail": (
                    "Main ## Requirements header present"
                    if has_req_header
                    else f"{rel}: missing ## Requirements header"
                ),
            }
        )

    max_chars = int(settings["max_requirement_chars"])
    req_matches = list(REQ_BLOCK_RE.finditer(text))
    long_reqs: list[str] = []
    non_normative: list[str] = []
    for m in req_matches:
        req_name = m.group(1).strip()
        req_body = m.group(2).strip()
        if len(req_body) > max_chars:
            long_reqs.append(f"{req_name} ({len(req_body)} chars > {max_chars})")
        if not re.search(r"\b(SHALL|MUST)\b", req_body):
            non_normative.append(req_name)

    checks.append(
        {
            "id": f"{rel}:requirement_length_strict",
            "ok": bool(req_matches) and not long_reqs,
            "detail": (
                f"All {len(req_matches)} requirements <= {max_chars} chars"
                if req_matches and not long_reqs
                else f"{rel}: requirements exceeding {max_chars} chars: {', '.join(long_reqs) or 'no requirements found'}"
            ),
        }
    )
    checks.append(
        {
            "id": f"{rel}:normative_keywords",
            "ok": bool(req_matches) and not non_normative,
            "detail": (
                "All requirements use SHALL/MUST normative phrasing"
                if req_matches and not non_normative
                else f"{rel}: missing SHALL/MUST in: {', '.join(non_normative) or 'no requirements'}"
            ),
        }
    )

    scenarios = SCENARIO_RE.findall(text)
    has_when_then = "- **WHEN**" in text and "- **THEN**" in text
    checks.append(
        {
            "id": f"{rel}:scenarios",
            "ok": bool(scenarios) and has_when_then,
            "detail": (
                f"{len(scenarios)} scenario(s) with WHEN/THEN clauses"
                if scenarios and has_when_then
                else f"{rel}: missing #### Scenario blocks or WHEN/THEN clauses"
            ),
        }
    )

    link_issues = check_relative_links(spec_path, repo_root)
    checks.append(
        {
            "id": f"{rel}:links",
            "ok": not link_issues,
            "detail": "All relative links resolve" if not link_issues else "; ".join(link_issues),
        }
    )
    return checks


def check_change_dir(
    change_dir: Path, repo_root: Path, *, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate an active OpenSpec change directory against `openspec/config.yaml` contracts."""
    checks: list[dict[str, Any]] = []
    cid = change_dir.name

    # 1. proposal.md
    proposal = change_dir / "proposal.md"
    if not proposal.is_file():
        checks.append({"id": f"{cid}:proposal_exists", "ok": False, "detail": "Missing proposal.md"})
    else:
        ptext = proposal.read_text(encoding="utf-8", errors="replace")
        required_sections = tuple(str(s) for s in settings["proposal_sections"])
        missing = [
            s for s in required_sections if not re.search(rf"^##\s+{re.escape(s)}\b", ptext, re.M | re.I)
        ]
        checks.append(
            {
                "id": f"{cid}:proposal_sections",
                "ok": not missing,
                "detail": (
                    f"proposal.md contains all required sections ({', '.join(required_sections)})"
                    if not missing
                    else f"{cid}/proposal.md: missing sections: {', '.join(missing)}"
                ),
            }
        )
        plinks = check_relative_links(proposal, repo_root)
        checks.append(
            {
                "id": f"{cid}:proposal_links",
                "ok": not plinks,
                "detail": "proposal.md relative links resolve" if not plinks else "; ".join(plinks),
            }
        )

    # 2. design.md
    design = change_dir / "design.md"
    if not design.is_file():
        checks.append({"id": f"{cid}:design_exists", "ok": False, "detail": "Missing design.md"})
    else:
        dtext = design.read_text(encoding="utf-8", errors="replace")
        missing_design = [
            s
            for s in tuple(str(x) for x in settings["design_sections"])
            if not re.search(rf"^##\s+(?:\d+\.\s+)?{re.escape(s)}\b", dtext, re.M | re.I)
        ]
        if settings["require_mermaid_in_design"] and "```mermaid" not in dtext:
            missing_design.append("Mermaid diagram")
        checks.append(
            {
                "id": f"{cid}:design_structure",
                "ok": not missing_design,
                "detail": (
                    (
                        f"design.md has {', '.join(str(s) for s in settings['design_sections'])}"
                        + (", and a Mermaid diagram" if settings["require_mermaid_in_design"] else "")
                    )
                    if not missing_design
                    else f"{cid}/design.md: missing {', '.join(missing_design)}"
                ),
            }
        )
        dlinks = check_relative_links(design, repo_root)
        checks.append(
            {
                "id": f"{cid}:design_links",
                "ok": not dlinks,
                "detail": "design.md relative links resolve" if not dlinks else "; ".join(dlinks),
            }
        )

    # 3. tasks.md
    tasks = change_dir / "tasks.md"
    if not tasks.is_file():
        checks.append({"id": f"{cid}:tasks_exists", "ok": False, "detail": "Missing tasks.md"})
    else:
        ttext = tasks.read_text(encoding="utf-8", errors="replace")
        missing_checkboxes: list[str] = []
        for section in tuple(str(s) for s in settings["tasks_checkbox_sections"]):
            body = _extract_numbered_section(ttext, section)
            has_checkbox = bool(re.search(r"^-\s+\[[ xX]\]\s+\d+\.\d+\b", body, re.M))
            if not has_checkbox:
                missing_checkboxes.append(section)
        checks.append(
            {
                "id": f"{cid}:tasks_verification_and_rollout",
                "ok": not missing_checkboxes,
                "detail": (
                    f"tasks.md has numbered checkbox items in {', '.join(str(s) for s in settings['tasks_checkbox_sections'])}"
                    if not missing_checkboxes
                    else f"{cid}/tasks.md: numbered checkboxes missing in: {', '.join(missing_checkboxes)}"
                ),
            }
        )
        notes_body = _extract_section(ttext, "Implementation Notes").strip()
        notes_lower = notes_body.lower()
        notes_ok = bool(notes_body) and not any(p in notes_lower for p in PLACEHOLDER_NOTES_PATTERNS)
        checks.append(
            {
                "id": f"{cid}:tasks_implementation_notes",
                "ok": notes_ok,
                "detail": (
                    "tasks.md has concrete Implementation Notes"
                    if notes_ok
                    else f"{cid}/tasks.md: Implementation Notes is empty or still contains the template placeholder"
                ),
            }
        )
        tlinks = check_relative_links(tasks, repo_root)
        checks.append(
            {
                "id": f"{cid}:tasks_links",
                "ok": not tlinks,
                "detail": "tasks.md relative links resolve" if not tlinks else "; ".join(tlinks),
            }
        )

    # 4. specs/*/spec.md deltas
    delta_specs = sorted((change_dir / "specs").glob("*/spec.md"))
    if not delta_specs:
        checks.append({"id": f"{cid}:delta_specs", "ok": False, "detail": "No specs/*/spec.md found"})
    else:
        for sp in delta_specs:
            checks.extend(check_spec_file(sp, repo_root, is_delta=True, settings=settings))

    return checks


def run_openspec_cli_strict(workspace_root: Path, target_id: str | None = None) -> list[dict[str, Any]]:
    """Invoke `openspec validate --strict --json` if the `openspec` binary is installed."""
    cli = shutil.which("openspec")
    if not cli:
        return []
    cmd = [cli, "validate", "--strict", "--json"]
    if target_id:
        cmd.append(target_id)
    else:
        cmd.append("--all")
    proc = subprocess.run(
        cmd,
        cwd=workspace_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [
            {
                "id": "openspec_cli_strict",
                "ok": proc.returncode == 0,
                "detail": (proc.stderr or proc.stdout or "").strip()[:300],
            }
        ]
    checks: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        item_id = item.get("id", "unknown")
        valid = bool(item.get("valid"))
        issues = [i.get("message", "") for i in item.get("issues", [])]
        checks.append(
            {
                "id": f"openspec_cli:{item_id}",
                "ok": valid and not issues,
                "detail": (
                    f"openspec validate {item_id} --strict: valid"
                    if valid and not issues
                    else f"openspec validate {item_id} --strict failed: {'; '.join(issues)}"
                ),
            }
        )
    return checks


def validate_workspace(
    workspace_root: Path,
    *,
    repo_root: Path | None = None,
    target_id: str | None = None,
    include_cli: bool = True,
) -> dict[str, Any]:
    """Validate OpenSpec artifacts in `workspace_root` and return a structured report."""
    workspace_root = Path(workspace_root).resolve()
    effective_repo = (repo_root or workspace_root).resolve()
    settings = load_validation_settings(workspace_root)
    openspec_dir = workspace_root / "openspec"
    checks: list[dict[str, Any]] = []

    if include_cli:
        checks.extend(run_openspec_cli_strict(workspace_root, target_id=target_id))

    specs_dir = openspec_dir / "specs"
    if specs_dir.is_dir():
        for sp in sorted(specs_dir.glob("*/spec.md")):
            cap_id = sp.parent.name
            if target_id and target_id != cap_id:
                continue
            checks.extend(
                check_spec_file(sp, effective_repo, is_delta=False, settings=settings)
            )
            if target_id == cap_id:
                for delta_sp in sorted((openspec_dir / "changes").glob(f"*/specs/{cap_id}/spec.md")):
                    if "archive" not in delta_sp.parts:
                        checks.extend(
                            check_spec_file(
                                delta_sp, effective_repo, is_delta=True, settings=settings
                            )
                        )

    changes_dir = openspec_dir / "changes"
    if changes_dir.is_dir():
        for cdir in sorted(changes_dir.iterdir()):
            if not cdir.is_dir() or cdir.name == "archive":
                continue
            if target_id and target_id != cdir.name:
                continue
            checks.extend(check_change_dir(cdir, effective_repo, settings=settings))

    total = len(checks)
    ok_count = sum(1 for c in checks if c["ok"])
    failed = [c for c in checks if not c["ok"]]
    return {
        "workspace": str(workspace_root),
        "target_id": target_id or "all",
        "checks_total": total,
        "checks_ok": ok_count,
        "checks_failed": len(failed),
        "all_checks_ok": total > 0 and len(failed) == 0,
        "checks": checks,
        "findings": [c["detail"] for c in failed],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OpenSpec specs and changes strictly.")
    parser.add_argument("--workspace", default=".", help="Workspace directory containing openspec/")
    parser.add_argument("--repo-root", default=None, help="Repository root for resolving relative links")
    parser.add_argument("--target", default=None, help="Optional single spec or change id")
    parser.add_argument("--no-cli", action="store_true", help="Skip shelling out to openspec CLI")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--quiet", action="store_true", help="Only print when findings exist")
    args = parser.parse_args(argv)

    ws = Path(args.workspace).resolve()
    rr = Path(args.repo_root).resolve() if args.repo_root else ws
    report = validate_workspace(ws, repo_root=rr, target_id=args.target, include_cli=not args.no_cli)

    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.quiet or not report["all_checks_ok"]:
        status = "OK" if report["all_checks_ok"] else "FAILED"
        print(
            f"[validate_openspec] {status}: {report['checks_ok']}/{report['checks_total']} checks succeeded "
            f"(target={report['target_id']})"
        )
        for f in report["findings"]:
            print(f"  - {f}")
    return 0 if report["all_checks_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))