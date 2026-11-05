"""Tests for the packaged config-driven engines (validation + drift + init).

These run against throwaway fixtures so the packaged suite works in any
checkout (identity-team does not ship `openspec/specs/`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from openspec_harness.adapter import RUNTIME_SCRIPTS, load_harness_manifest
from openspec_harness.drift import check_drift, load_drift_config
from openspec_harness.init import init_repository
from openspec_harness.validation import load_validation_settings, validate_workspace


SPEC = """# demo Specification

## Purpose
Demonstrates a conforming baseline specification for the packaged engine test fixtures.

## Requirements

### Requirement: Do the thing
The system SHALL perform the thing and reject failures with a clear error.

#### Scenario: Happy path
- **WHEN** a valid request arrives
- **THEN** the system performs the thing
"""

CHANGE_SPEC = """# Spec Delta

## Purpose
Demonstrates a conforming delta specification for the packaged engine test fixtures.

## ADDED Requirements

### Requirement: Add a behaviour
The system SHALL add the behaviour described by this change.

#### Scenario: Behaviour added
- **WHEN** the change is applied
- **THEN** the behaviour is observable
"""

CHANGE_TASKS = """# Tasks

## 1. Verification Suite

- [x] 1.1 Run the unit tests.
- [x] 1.2 Run `openspec validate --all --strict`.

## 2. Documentation & Rollout

- [x] 2.1 Document the change.

## Implementation Notes

- Concrete implementation notes replacing the template placeholder.
"""

CHANGE_PROPOSAL = """# Proposal

## Why
Alignment.

## What Changes
Adds a behaviour.

## Non-goals
Nothing else.

## Success Metrics
All checks pass.

## Capabilities

### New Capabilities
- `demo`

### Modified Capabilities
None.

## Impact
Docs only.
"""

CHANGE_DESIGN = """# Design

## Context
Follows the [proposal](proposal.md).

## Goals / Non-Goals
- Goal: conform

```mermaid
flowchart TD
    A --> B
```

## Risks & Trade-offs
- None.
"""


def _make_repo(root: Path) -> Path:
    (root / "openspec" / "specs" / "demo").mkdir(parents=True)
    (root / "openspec" / "specs" / "demo" / "spec.md").write_text(SPEC, encoding="utf-8")
    change = root / "openspec" / "changes" / "demo-change"
    (change / "specs" / "demo").mkdir(parents=True)
    (change / "proposal.md").write_text(CHANGE_PROPOSAL, encoding="utf-8")
    (change / "design.md").write_text(CHANGE_DESIGN, encoding="utf-8")
    (change / "tasks.md").write_text(CHANGE_TASKS, encoding="utf-8")
    (change / "specs" / "demo" / "spec.md").write_text(CHANGE_SPEC, encoding="utf-8")
    (root / "Makefile").write_text("build:\n\tgo build ./...\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "demo.txt").write_text("needle-one needle-two\n", encoding="utf-8")
    return root


def test_validation_settings_defaults_and_overrides(tmp_path: Path) -> None:
    """A repository without config.yaml inherits the strict defaults, and an
    explicit validation: block overrides only what it declares."""
    bare = tmp_path / "bare"
    bare.mkdir()
    assert load_validation_settings(bare)["max_requirement_chars"] == 500
    assert load_validation_settings(bare)["require_mermaid_in_design"] is True
    assert load_validation_settings(Path("/nonexistent")) == load_validation_settings(bare)

    repo = _make_repo(tmp_path / "repo")
    settings = load_validation_settings(repo)
    assert settings["max_requirement_chars"] == 500
    assert "Why" in settings["proposal_sections"]

    cfg = repo / "openspec" / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "schema": "spec-driven",
                "validation": {"max_requirement_chars": 120, "require_mermaid_in_design": False},
            }
        ),
        encoding="utf-8",
    )
    overridden = load_validation_settings(repo)
    assert overridden["max_requirement_chars"] == 120
    assert overridden["require_mermaid_in_design"] is False
    # undeclared keys keep their defaults
    assert overridden["proposal_sections"] == list(load_validation_settings(bare)["proposal_sections"])


def test_validate_workspace_config_driven(tmp_path: Path) -> None:
    """The generic engine validates a conforming fixture repository."""
    repo = _make_repo(tmp_path / "repo")
    report = validate_workspace(repo, repo_root=repo)
    assert report["all_checks_ok"], report["findings"]
    assert report["checks_total"] > 0

    # Overlong requirement bodies trip the strict cap from the config block.
    cfg = repo / "openspec" / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"schema": "spec-driven", "validation": {"max_requirement_chars": 10}}),
        encoding="utf-8",
    )
    failing = validate_workspace(repo, repo_root=repo)
    assert not failing["all_checks_ok"]
    assert any("requirement_length_strict" in c["id"] for c in failing["checks"] if not c["ok"])


def test_drift_declarative_config(tmp_path: Path) -> None:
    """check_drift runs a declarative manifest; needles and regex both gate."""
    repo = _make_repo(tmp_path / "repo")
    cfg = repo / "openspec" / "drift-checks.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "checks": {
                    "demo": [
                        {
                            "id": "needles_ok",
                            "path": "src/demo.txt",
                            "needles": ["needle-one", "needle-two"],
                        },
                        {
                            "id": "regex_ok",
                            "path": "src/demo.txt",
                            "regex": ["needle\\-[a-z]+"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_drift_config(cfg)
    assert data["version"] == 1
    report = check_drift(repo, config_path=cfg)
    assert report["all_checks_ok"], report["findings"]
    assert report["checks_total"] == 2

    scoped = check_drift(repo, target_id="demo", config_path=cfg)
    assert scoped["checks_total"] == 2
    assert check_drift(repo, target_id="missing-target", config_path=cfg)["checks_total"] == 0

    (repo / "src" / "demo.txt").write_text("only one needle\n", encoding="utf-8")
    failed = check_drift(repo, config_path=cfg)
    assert not failed["all_checks_ok"]
    assert failed["checks_failed"] == 2


def test_harness_manifest_and_runtime_scripts(tmp_path: Path) -> None:
    """The adapter manifest is the single source of adapter state."""
    repo = _make_repo(tmp_path / "repo")
    (repo / "openspec" / "harness.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "schema": "spec-driven",
                "domain": "openspec-demo",
                "repo_symlinks": ["Makefile", "src"],
                "tasks": {
                    "demo": {
                        "kind": "change",
                        "path": "openspec/changes/demo-change",
                        "prompt": "Audit and remediate the demo change.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = load_harness_manifest(repo)
    assert manifest["domain"] == "openspec-demo"
    assert manifest["tasks"]["demo"]["prompt"] == "Audit and remediate the demo change."
    assert RUNTIME_SCRIPTS == frozenset({"validate_openspec.py", "check_openspec_drift.py"})

    broken = repo / "openspec" / "harness.yaml"
    broken.write_text("version: 1\ntasks: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_harness_manifest(repo)
    broken.unlink()
    with pytest.raises(FileNotFoundError):
        load_harness_manifest(repo)


def test_init_scaffolds_idempotently(tmp_path: Path) -> None:
    """init generates the per-repo pieces, then a second run writes nothing."""
    repo = tmp_path / "example-service"
    (repo / "openspec" / "changes" / "add-login").mkdir(parents=True)
    (repo / "Makefile").write_text("build:\n\tgo build ./...\n", encoding="utf-8")

    written = init_repository(repo)
    names = {p.name for p in written}
    assert {"drift-checks.yaml", "harness.yaml", "validate_openspec.py", "check_openspec_drift.py"} <= names
    assert "harness2-audit:" in (repo / "Makefile").read_text(encoding="utf-8")
    assert "add-login" in load_drift_config(repo / "openspec" / "drift-checks.yaml")["checks"]

    marker = (repo / "openspec" / "harness.yaml").read_text(encoding="utf-8")
    assert init_repository(repo) == []
    assert (repo / "openspec" / "harness.yaml").read_text(encoding="utf-8") == marker

    shutil.rmtree(repo / "openspec", ignore_errors=True)
    with pytest.raises(FileNotFoundError):
        init_repository(repo)