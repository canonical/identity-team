"""Scaffold OpenSpec harness configuration for a repository.

`openspec-harness init` generates the per-repository pieces a new
`canonical/` repository needs to adopt the shared validators and the
harness2 OpenSpec adapter:

- `openspec/drift-checks.yaml` (declarative code-to-spec drift checks stub)
- `openspec/harness.yaml` (adapter manifest: domain, repo symlinks, tasks)
- `scripts/validate_openspec.py` / `scripts/check_openspec_drift.py` shims
  over the package entrypoints
- Makefile `harness2-*` targets

Domain skills (`<service>-domain`) and security reviewers stay repo-local by
design: only the generic OpenSpec authoring/drift machinery is scaffolded.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DRIFT_TEMPLATE = """version: 1

# Declarative code-to-spec drift checks.
# Each top-level key is a spec or change id (matching `openspec validate`
# targets); each entry needs `id`, `path`, and `needles` (literal substrings,
# all required) and/or `regex` patterns (any match), plus optional
# `must_exist` (default true).
checks:
  {first_task}:
    - id: example_check
      path: Makefile
      needles:
        - "build:"
"""

HARNESS_TEMPLATE = """version: 1

# Repository manifest consumed by the `openspec_harness` adapter
# (`openspec_harness.adapter.OpenSpecAdapter`).
schema: spec-driven
domain: openspec-{service}

# Repository entries materialised into each rollout workspace so the drift
# checker and skills can resolve real source files.
repo_symlinks:
  - Makefile
  - README.md

# OpenSpec spec/change ids targeted by sweeps, with their artifact path
# (`kind: spec` baseline specs, `kind: change` bundles) and rollout prompt.
tasks:
  {first_task}:
    kind: change
    path: openspec/changes/{first_task}
    prompt: >-
      Audit and remediate the OpenSpec change `{first_task}`
      (`openspec/changes/{first_task}/`) so that `proposal.md`, `design.md`,
      `tasks.md`, and `specs/*/spec.md` satisfy all `openspec/config.yaml`
      contracts, resolve all relative Markdown links, keep every requirement
      body <= 500 characters, and pass `openspec validate --strict`.
"""

VALIDATE_SHIM = '''#!/usr/bin/env python3
"""Deterministic OpenSpec structural, strict-CLI, and link validator (shim).

Delegates to the shared `openspec-harness` package entrypoint
(`openspec_harness.validation:main`), kept at `scripts/` so `make
harness2-*`, CI, and agents can keep invoking it unchanged.
"""

from __future__ import annotations

import sys

from openspec_harness.validation import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

DRIFT_SHIM = '''#!/usr/bin/env python3
"""Declarative OpenSpec code-to-spec drift checker (shim).

Delegates to the shared `openspec-harness` package entrypoint
(`openspec_harness.drift:main`), kept at `scripts/` so `make harness2-*`,
CI, and agents can keep invoking it unchanged.
"""

from __future__ import annotations

import sys

from openspec_harness.drift import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

MAKEFILE_SNIPPET = """
# OpenSpec harness2 targets
harness2-validate:
\tpython3 -m openspec_harness.cli validate-harnesses
.PHONY: harness2-validate

harness2-audit:
\tpython3 scripts/validate_openspec.py --workspace . --repo-root .
\tpython3 scripts/check_openspec_drift.py --repo-root .
.PHONY: harness2-audit

harness2-remediate:
\tpython3 -m openspec_harness.cli remediate
.PHONY: harness2-remediate

harness2-test:
\tpytest tools/openspec-harness/tests -v
.PHONY: harness2-test
"""


def _write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        print(f"  [skip] {path} (exists)")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [add ] {path}")
    return True


def init_repository(repo_root: Path) -> list[Path]:
    """Scaffold the OpenSpec harness pieces; returns paths written."""
    repo_root = Path(repo_root).resolve()
    openspec_dir = repo_root / "openspec"
    if not openspec_dir.is_dir():
        raise FileNotFoundError(
            f"no openspec/ directory under {repo_root}: run `openspec init` first, "
            "then `openspec-harness init` to add the shared validators."
        )
    changes_dir = openspec_dir / "changes"
    specs_dir = openspec_dir / "specs"
    active_changes = (
        sorted(p.name for p in changes_dir.iterdir() if p.is_dir() and p.name != "archive")
        if changes_dir.is_dir()
        else []
    )
    baseline_specs = (
        sorted(p.parent.name for p in specs_dir.glob("*/spec.md")) if specs_dir.is_dir() else []
    )
    if active_changes:
        first_task = active_changes[0]
    elif baseline_specs:
        first_task = baseline_specs[0]
    else:
        first_task = "example-change"

    written: list[Path] = []
    service = repo_root.name

    p = openspec_dir / "drift-checks.yaml"
    if _write_if_absent(p, DRIFT_TEMPLATE.format(first_task=first_task)):
        written.append(p)
    p = openspec_dir / "harness.yaml"
    if _write_if_absent(p, HARNESS_TEMPLATE.format(first_task=first_task, service=service)):
        written.append(p)
    p = repo_root / "scripts" / "validate_openspec.py"
    if _write_if_absent(p, VALIDATE_SHIM):
        written.append(p)
        p.chmod(0o755)
    p = repo_root / "scripts" / "check_openspec_drift.py"
    if _write_if_absent(p, DRIFT_SHIM):
        written.append(p)
        p.chmod(0o755)

    makefile = repo_root / "Makefile"
    if makefile.is_file():
        body = makefile.read_text(encoding="utf-8")
        if "harness2-audit:" not in body:
            makefile.write_text(body.rstrip() + "\n" + MAKEFILE_SNIPPET, encoding="utf-8")
            print(f"  [add ] Makefile targets (harness2-*)")
            written.append(makefile)
        else:
            print("  [skip] Makefile targets (exists)")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openspec-harness",
        description="Scaffold OpenSpec harness config for this repository.",
    )
    parser.parse_args(argv)
    repo = Path.cwd()
    written = init_repository(repo)
    print(f"Scaffolded {len(written)} file(s) under {repo}.")
    print("Next: edit openspec/harness.yaml tasks and openspec/drift-checks.yaml checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
