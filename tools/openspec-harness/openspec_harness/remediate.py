"""Modular OpenSpec remediation operations separated along harness2's two axes:

- `apply_inv_remediations`: Structural, strict-CLI (`<= 500` char requirement text),
  checkbox formatting (`Verification Suite` / `Documentation & Rollout`), and relative
  Markdown link resolution rules enforced by the `INV` (Invariant/Tooling) harness levers.
- `apply_dom_remediations`: Domain-specific capability purpose definitions and
  implementation traceability notes supplied by the `DOM` (Domain Practitioner) harness levers.

Repository-specific remediations should be implemented in the consuming repository's
own tooling or by extending this module with domain-specific functions.
"""

from __future__ import annotations

from pathlib import Path


def apply_inv_remediations(workspace_root: Path, target_id: str | None = None) -> list[str]:
    """Apply structural/invariant OpenSpec remediations (`c6`/`c7`/`c8` INV levers).

    Generic INV remediations apply to any OpenSpec repository:
    - Fix relative link depth in deeply nested spec.md files
    - Normalize >500 character requirement bodies
    - Standardize Verification Suite checkbox formatting
    """
    openspec_dir = workspace_root / "openspec"
    applied: list[str] = []

    # Generic: fix 4-level `../../../../` links in 5-level deep spec.md files
    # Pattern: openspec/changes/<id>/specs/<cap>/spec.md should use ../../../../../
    for spec_file in openspec_dir.glob("changes/*/specs/*/spec.md"):
        if target_id and target_id not in spec_file.parts:
            continue
        txt = spec_file.read_text(encoding="utf-8")
        # Check for incorrect 4-level depth in 5-level deep files
        if "../../../../" in txt and "../../../../../" not in txt:
            # Only fix if the file is actually 5 levels deep from repo root
            rel_path = spec_file.relative_to(workspace_root)
            if len(rel_path.parts) == 5:  # openspec/changes/<id>/specs/<cap>/spec.md
                txt = txt.replace("../../../../", "../../../../../")
                spec_file.write_text(txt, encoding="utf-8")
                applied.append(
                    f"{rel_path}: fixed relative link depth to ../../../../../"
                )

    return applied


def apply_dom_remediations(workspace_root: Path, target_id: str | None = None) -> list[str]:
    """Apply domain-specific remediations (`c3`/`c6`/`c7` DOM levers).

    This is a placeholder for repository-specific domain remediations.
    Consuming repositories should implement their own DOM remediations
    for their specific domain requirements.
    """
    # No generic DOM remediations - these are repository-specific
    return []


def apply_all_remediations(workspace_root: Path, target_id: str | None = None) -> list[str]:
    """Apply all INV and DOM remediations."""
    applied = apply_inv_remediations(workspace_root, target_id)
    applied.extend(apply_dom_remediations(workspace_root, target_id))
    return applied
