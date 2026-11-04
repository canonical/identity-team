# OpenSpec Harness2 Toolkit (shared, config-driven)

This package (`tools/openspec-harness`) holds the shared, repository-agnostic
OpenSpec tooling consumed by Canonical Identity repositories:
the `openspec_harness` package (validation + drift + adapter + init), the
`harness2` recursive-harnessing core, and this repository's `c1..c8` agent
harness trees. All repository-specific values are **declarative**:

- `openspec/config.yaml` → `validation:` settings (`max_requirement_chars`, `require_mermaid_in_design`, `proposal_sections`, `design_sections`, `tasks_checkbox_sections`)
- `openspec/drift-checks.yaml` → per-spec/change code-to-spec drift checks (`id`, `path`, `needles` / `regex`)
- `openspec/harness.yaml` → adapter manifest (`domain`, `repo_symlinks`, `tasks`)

`scripts/validate_openspec.py` and `scripts/check_openspec_drift.py` are thin
shims over `openspec_harness.validation:main` / `openspec_harness.drift:main`;
the harness trees carry no duplicate script copies — the adapter materialises
them into rollout workspaces from `scripts/` at execution time.

## Original: Google `harness2` × OpenSpec Integration for Secure Token Service (STS)

This configures [`google-research/harness2`](https://github.com/google-research/harness2) (*Recursive Agent Harnessing for an Open World*) to operate natively over the local **OpenSpec** specification-driven workflow in `secure-token-service`.

## Architecture: Two-Level Recursive Harnessing (`c1..c8`)

`harness2` treats the entire agent harness as an explicit, versioned, validator-checked directory tree (`Tree = dict[str, str]`) spanning eight component types (`c1..c8`):

| Component | Purpose | OpenCode Path (`.harness2/harnesses/opencode_base/`) | OMP Path (`.harness2/harnesses/omp_base/` & Repo `.omp/`) | Antigravity / Repo-Root Path |
| :--- | :--- | :--- | :--- | :--- |
| **`c1`** | System Prompt / Context | `systemprompt.md` | `.omp/AGENTS.md` | Folded into `AGENTS.md` |
| **`c2`** | Workspace / Sticky Rules | `guardrails.md` (`<= 24,000` chars combined) | `.omp/RULES.md` (`<= 24,000` chars combined) | `AGENTS.md` |
| **`c3` / `c6`** | Domain & Invariant Skills | `skills/{openspec-strict-authoring,sts-go-domain,openspec-detect-drift}/SKILL.md` | `.omp/skills/{openspec-strict-authoring,sts-go-domain,openspec-detect-drift}/SKILL.md` | `.agents/skills/{openspec-strict-authoring,sts-go-domain,openspec-detect-drift}/SKILL.md` |
| **`c4`** | Subagents | `sub_agents/{openspec_spec_auditor,sts_security_reviewer}/AGENT.md` | `sub_agents/.../AGENT.md` & `.omp/agents/{openspec_spec_auditor,sts_security_reviewer}.md` | `sub_agents/{openspec_spec_auditor,sts_security_reviewer}/AGENT.md` |
| **`c5`** | Slash Commands | `commands/{openspec-check,openspec-drift}.md` | `.omp/commands/{openspec-check,openspec-drift}.md` | Folded into `AGENTS.md` |
| **`c7`** | Deterministic Verification Scripts | `scripts/{validate_openspec.py,check_openspec_drift.py}` | `scripts/{validate_openspec.py,check_openspec_drift.py}` | `scripts/{validate_openspec.py,check_openspec_drift.py}` |
| **`c8`** | Lifecycle Hooks / Extensions | `plugin/openspec_guard.ts` | `.omp/extensions/openspec_guard.ts` | `.agents/hooks.json` |
### Orthogonal Improvement Dimensions (`INV` vs `DOM`)

During each recursive pass, `harness2` decomposes harness adaptation into two orthogonal axes before composing them:

1. **`INV` (Task-Agnostic OpenSpec Invariants)**:
   - Enforces `openspec validate --strict` and `openspec/config.yaml` structural contracts.
   - Enforces `<= 500` character requirement bodies (`### Requirement:` up to the first `#### Scenario:`).
   - Enforces relative Markdown link depth resolution (`../../../` from `openspec/changes/<id>/*.md`, `../../../../../` from `openspec/changes/<id>/specs/<cap>/spec.md`).
   - Enforces numbered checkbox formatting (`1. [x] ...` or `- [x] 7.1 ...`) in `Verification Suite` and `Documentation & Rollout`.
2. **`DOM` (STS Go 1.26 Domain Practitioner Knowledge)**:
   - Maps OpenSpec capabilities (`artifact-security-gate`, `m2m-token-exchange`, `support-multi-arch-rocks-and-pipelines`, `support-ubuntu-one-openid`) to the Go 1.26 source tree (`internal/auth/`, `internal/grpc/`, `internal/http/`, `internal/cookie/`, `api/sts/v1/sts.proto`, `rockcraft.yaml`, `.github/workflows/`).
   - Eliminates archive `TBD` purpose placeholders and template `Implementation Notes` by synthesizing accurate architectural prose.

## Quickstart Commands

```bash
# 1. Validate all c1..c8 harness trees (opencode_seed, opencode_base, omp_seed, omp_base)
PYTHONPATH=.harness2 python3 -m openspec_harness.cli validate-harnesses

# 2. Audit OpenSpec specs & changes (strict CLI + config.yaml contracts + code drift)
PYTHONPATH=.harness2 python3 -m openspec_harness.cli audit

# 3. Run the two-level harness2 recursive sweep (OpenCode or OMP substrate, parallel & sequential modes, k=1,2)
PYTHONPATH=.harness2 python3 -m openspec_harness.cli sweep --substrate oc --modes parallel,sequential --k 1,2
PYTHONPATH=.harness2 python3 -m openspec_harness.cli sweep --substrate omp --modes parallel,sequential --k 1,2
# 4. Apply INV+DOM OpenSpec remediations to the live repository
PYTHONPATH=.harness2 python3 -m openspec_harness.cli remediate

# 5. Run the test suite (upstream harness2 tests + OpenSpec integration tests)
PYTHONPATH=.harness2 pytest .harness2/tests -v
```

## Multi-Repository Usage

Install from a git ref (`#subdirectory=tools/openspec-harness` when consumed
from `canonical/identity-team`):

```bash
pip install "openspec-harness @ git+https://github.com/canonical/identity-team.git@main#subdirectory=tools/openspec-harness"

# Entrypoints (same engines the shims delegate to)
openspec-validate --workspace . --repo-root . --json
openspec-drift --repo-root . --config openspec/drift-checks.yaml --json

# Scaffold the per-repo pieces into a new repository (idempotent)
openspec-harness init
```

`init` generates `openspec/drift-checks.yaml`, `openspec/harness.yaml`, the
`scripts/` shims, and `Makefile` `harness2-*` targets. Domain skills
(`<service>-domain`) and security reviewers stay repo-local by design.
