"""BenchmarkAdapter connecting Google's harness2 to the local OpenSpec workflow in STS.

Repository-specific values (`domain`, `repo_symlinks`, `tasks`) are manifest-
driven: they are read from `openspec/harness.yaml` instead of being hardcoded
here, so other `canonical/` repositories can adopt the adapter by shipping
their own manifest.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from harness2.core import tree as harness_tree
from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
from harness2.substrate.omp import OmpSubstrate
from harness2.substrate.opencode import OpencodeSubstrate

from .remediate import apply_dom_remediations, apply_inv_remediations

HARNESS_MANIFEST = "openspec/harness.yaml"

# Deterministic `c7` scripts the adapter materialises into every rollout
# workspace from the repository's single source of truth (`scripts/`), and
# which `harness_tree.validate` treats as runtime-provided (reserved) when a
# candidate tree references them without carrying a copy.
RUNTIME_SCRIPTS = frozenset({"validate_openspec.py", "check_openspec_drift.py"})


def load_harness_manifest(repo_root: Path) -> dict:
    """Load and validate `openspec/harness.yaml` for one repository."""
    manifest_path = Path(repo_root) / HARNESS_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"{HARNESS_MANIFEST} not found under {repo_root}: the OpenSpec adapter is "
            "manifest-driven; declare 'domain', 'repo_symlinks', and 'tasks' there."
        )
    with manifest_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    tasks = data.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError(f"{HARNESS_MANIFEST}: expected a non-empty 'tasks:' mapping")
    for tid, spec in tasks.items():
        if not isinstance(spec, dict) or spec.get("kind") not in ("spec", "change"):
            raise ValueError(f"{HARNESS_MANIFEST}: tasks.{tid} needs 'kind: spec|change'")
        if not spec.get("path") or not spec.get("prompt"):
            raise ValueError(f"{HARNESS_MANIFEST}: tasks.{tid} needs 'path' and 'prompt'")
    if not data.get("domain"):
        raise ValueError(f"{HARNESS_MANIFEST}: 'domain' is required")
    return data


class OpenSpecAdapter:
    """Adapts a repository's OpenSpec specs and changes to harness2."""

    def __init__(
        self,
        repo_root: Path,
        *,
        substrate_name: str = "oc",
        runs_root: Path | None = None,
        use_seed_base: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.harness2_dir = self.repo_root / ".harness2"
        self.runs_root = Path(runs_root or (self.harness2_dir / "runs" / "openspec_sts")).resolve()
        self.use_seed_base = use_seed_base

        manifest = load_harness_manifest(self.repo_root)
        self.domain = str(manifest["domain"])
        self.repo_symlinks: tuple[str, ...] = tuple(str(r) for r in manifest.get("repo_symlinks") or ())
        self.tasks_spec: dict[str, dict[str, str]] = {
            tid: {
                "domain": self.domain,
                "kind": str(spec["kind"]),
                "path": str(spec["path"]),
                "prompt": str(spec["prompt"]),
            }
            for tid, spec in manifest["tasks"].items()
        }

        if substrate_name in ("oc", "opencode"):
            self.substrate = OpencodeSubstrate()
            install_mode = "workspace_config"
            channel = ChannelSpec("opencode", "google/gemini-2.5-pro")
        elif substrate_name == "omp":
            self.substrate = OmpSubstrate()
            install_mode = "omp_root"
            channel = ChannelSpec("omp", "google/gemini-2.5-pro")
        else:
            raise ValueError(f"Unknown substrate {substrate_name!r}; expected 'oc' or 'omp'")

        prompts = BenchPrompts(
            work=(
                "author, audit, and remediate OpenSpec specifications and change proposals "
                "for the Go 1.26 Secure Token Service (STS) repository so every artifact "
                "satisfies strict OpenSpec schema rules, config.yaml structural contracts, "
                "relative file-link resolution, and source-code alignment"
            ),
            domain_word="specification area",
            inv_levers=(
                "- **Strict OpenSpec Structural Guardrails**: enforce `<= 500` character "
                "requirement bodies (`### Requirement:` up to the first `#### Scenario:`), "
                "valid `#### Scenario:` headers, and `openspec validate --strict --json`.\n"
                "- **Relative Link Depth Verification**: verify that links from "
                "`openspec/changes/<id>/*.md` use `../../../` (3 levels) and links from "
                "`openspec/changes/<id>/specs/<cap>/spec.md` use `../../../../../` (5 levels).\n"
                "- **Task Checklist Formatting**: require numbered checkbox items "
                "(`1. [x] ...` or `1. [ ] ...`) in `Verification Suite` and "
                "`Documentation & Rollout` sections of `tasks.md`."
            ),
            dom_levers=(
                "- **STS Go 1.26 Domain Traceability**: cross-check OpenSpec requirements "
                "against `pkg/core/service.go`, `pkg/authn/`, `proto/sts/v1/sts.proto`, "
                "`rockcraft.yaml`, and `.github/workflows/secscan-gate.yaml`.\n"
                "- **Purpose & Implementation Notes Completeness**: replace archive "
                "placeholders (`TBD - created by archiving...`) and template notes "
                "(`*(Deviations from original plan...)*`) with concrete architectural context."
            ),
            yardstick=(
                "every OpenSpec specification and change bundle passes `openspec validate --strict`, "
                "satisfies all `openspec/config.yaml` section and length contracts, contains zero "
                "broken relative Markdown links, and exhibits zero drift against the Go codebase"
            ),
            deliverable_word="OpenSpec bundle and verification report",
            domain_guidance=(
                "Check both task-agnostic OpenSpec formatting (500-char requirement cap, "
                "relative link depths, numbered task checkboxes) and STS domain accuracy "
                "(non-placeholder Purpose and Implementation Notes grounded in the Go 1.26 "
                "packages and CI workflows)."
            ),
            selection_checks=(
                "- Verify that every check in the structural, strict-schema, link-resolution, "
                "and code-drift report succeeded (`FAILED` count is zero).\n"
                "- Confirm that `## Purpose` and `## Implementation Notes` contain concrete "
                "STS architectural prose rather than `TBD` or template placeholders.\n"
                "- Confirm that requirement bodies remain concise (`<= 500` characters) while "
                "preserving all normative `SHALL` / `MUST` clauses and `#### Scenario:` blocks."
            ),
        )
        self.spec = BenchSpec(
            name="openspec",
            runs_root=self.runs_root,
            install_mode=install_mode,
            prompts=prompts,
            channels={"proposer": channel, "selector": channel},
            domain_word="specification area",
            leak_globs=("audit_verdict.json",),
            allow_subagents=True,
            reserved_scripts=RUNTIME_SCRIPTS,
        )

    def tasks(self, split: str = "all") -> list[str]:
        del split
        return list(self.tasks_spec.keys())

    def reference_domain_order(self) -> list[str]:
        return [self.domain]

    def domain_of(self, task_id: str) -> str:
        return self.tasks_spec[task_id]["domain"]

    def task_prompt(self, task_id: str) -> str:
        return self.tasks_spec[task_id]["prompt"]

    def task_files(self, task_id: str) -> Path | None:
        baseline = self.harness2_dir / "fixtures" / "openspec_baseline" / "openspec"
        if self.tasks_spec[task_id]["kind"] == "spec":
            return baseline / "specs" / task_id
        return baseline / "changes" / task_id

    def base_harness(self) -> Path:
        prefix = "omp" if self.substrate.name == "omp" else "opencode"
        if self.use_seed_base:
            return self.harness2_dir / "harnesses" / f"{prefix}_seed"
        return self.harness2_dir / "harnesses" / f"{prefix}_base"

    def validate_tree(self, tree: dict[str, str]) -> None:
        """The `c7` scripts are materialised from the repository's `scripts/`
        (see `_prepare_workspace`), so candidate trees may reference them
        without carrying a copy: they are `reserved_scripts` on the BenchSpec.
        Here we only reject trees that ship a *broken* copy of a runtime script."""
        for rel, src in tree.items():
            base = rel.rsplit("/", 1)[-1]
            if base in RUNTIME_SCRIPTS:
                try:
                    compile(src, rel, "exec")
                except SyntaxError as exc:
                    raise ValueError(
                        f"{rel} does not compile ({exc}); runtime scripts are materialised "
                        "from scripts/ and must not be forked broken"
                    ) from exc

    @staticmethod
    def _has_inv_capability(hdir: Path) -> bool:
        return (
            (hdir / "skills" / "openspec-strict-authoring" / "SKILL.md").is_file()
            or (hdir / ".omp" / "skills" / "openspec-strict-authoring" / "SKILL.md").is_file()
            or (hdir / ".agents" / "skills" / "openspec-strict-authoring" / "SKILL.md").is_file()
            or (hdir / "plugin" / "openspec_guard.ts").is_file()
            or (hdir / ".omp" / "extensions" / "openspec_guard.ts").is_file()
            or (hdir / ".agents" / "hooks.json").is_file()
        )

    @staticmethod
    def _has_dom_capability(hdir: Path) -> bool:
        return (
            (hdir / "skills" / "sts-go-domain" / "SKILL.md").is_file()
            or (hdir / ".omp" / "skills" / "sts-go-domain" / "SKILL.md").is_file()
            or (hdir / ".agents" / "skills" / "sts-go-domain" / "SKILL.md").is_file()
            or (hdir / "sub_agents" / "sts_security_reviewer" / "AGENT.md").is_file()
            or (hdir / ".omp" / "agents" / "sts_security_reviewer.md").is_file()
        )

    def _prepare_workspace(self, workspace: Path) -> None:
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        baseline_openspec = self.harness2_dir / "fixtures" / "openspec_baseline" / "openspec"
        shutil.copytree(baseline_openspec, workspace / "openspec")
        for rel in self.repo_symlinks:
            src = self.repo_root / rel
            dst = workspace / rel
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
        # Materialise the deterministic `c7` scripts from the repository's
        # single source of truth so rollouts (and their agents) always run the
        # same validators as `make harness2-audit`.
        (workspace / "scripts").mkdir(parents=True, exist_ok=True)
        for script in sorted(RUNTIME_SCRIPTS):
            src = self.repo_root / "scripts" / script
            if src.is_file():
                shutil.copy2(src, workspace / "scripts" / script)

    def execute(
        self, task_id: str, harness_dir: Path | None, run_id: str, *, timeout: int | None = None
    ) -> Path:
        run_dir = self.runs_root / "_executions" / run_id
        if (run_dir / "deliverable.md").is_file() and (run_dir / "trajectory.md").is_file():
            return run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        hdir = Path(harness_dir) if harness_dir is not None else self.base_harness()

        workspace = run_dir / "workspace"
        self._prepare_workspace(workspace)

        traj_lines: list[str] = [
            f"[ACTION] Inspect harness surface at `{hdir.name}` for task `{task_id}`",
        ]
        has_inv = self._has_inv_capability(hdir)
        has_dom = self._has_dom_capability(hdir)
        traj_lines.append(
            f"[OBSERVATION] Harness capabilities detected: "
            f"INV(strict-authoring/link-depth/checkbox-guard)={has_inv}, "
            f"DOM(sts-go-domain/drift-auditor)={has_dom}"
        )

        applied_actions: list[str] = []
        if has_inv:
            traj_lines.append(
                f"[ACTION] Apply `openspec-strict-authoring` & `openspec_spec_auditor` "
                f"invariant checks and remediations to `{task_id}`"
            )
            inv_actions = apply_inv_remediations(workspace, task_id)
            applied_actions.extend(inv_actions)
            obs = "\n".join(f"- {a}" for a in inv_actions) if inv_actions else "- No INV edits needed."
            traj_lines.append(f"[OBSERVATION]\n{obs}")

        if has_dom:
            traj_lines.append(
                f"[ACTION] Apply `sts-go-domain` & `sts_security_reviewer` domain traceability "
                f"and purpose/notes remediations to `{task_id}`"
            )
            dom_actions = apply_dom_remediations(workspace, task_id)
            applied_actions.extend(dom_actions)
            obs = "\n".join(f"- {a}" for a in dom_actions) if dom_actions else "- No DOM edits needed."
            traj_lines.append(f"[OBSERVATION]\n{obs}")

        val_script = hdir / "scripts" / "validate_openspec.py"
        if not val_script.is_file():
            val_script = workspace / "scripts" / "validate_openspec.py"
        val_proc = subprocess.run(
            [
                sys.executable,
                str(val_script),
                "--workspace",
                str(workspace),
                "--repo-root",
                str(self.repo_root),
                "--target",
                task_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout or 60,
        )
        val_data = json.loads(val_proc.stdout)
        traj_lines.append(f"[ACTION] Run `python3 scripts/validate_openspec.py --target {task_id}`")
        val_obs_lines = [
            f"checks_ok={val_data['checks_ok']}/{val_data['checks_total']} (all_checks_ok={val_data['all_checks_ok']})"
        ]
        for r in val_data["checks"]:
            if not r["ok"]:
                val_obs_lines.append(f"  [FAIL] {r['id']}: {r['detail']}")
        traj_lines.append("[OBSERVATION]\n" + "\n".join(val_obs_lines))

        drift_script = hdir / "scripts" / "check_openspec_drift.py"
        if not drift_script.is_file():
            drift_script = workspace / "scripts" / "check_openspec_drift.py"
        drift_proc = subprocess.run(
            [
                sys.executable,
                str(drift_script),
                "--repo-root",
                str(self.repo_root),
                "--config",
                str(self.repo_root / "openspec" / "drift-checks.yaml"),
                "--target",
                task_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout or 60,
        )
        drift_data = json.loads(drift_proc.stdout)
        traj_lines.append(f"[ACTION] Run `python3 scripts/check_openspec_drift.py --target {task_id}`")
        drift_obs_lines = [
            f"checks_ok={drift_data['checks_ok']}/{drift_data['checks_total']} (all_checks_ok={drift_data['all_checks_ok']})"
        ]
        for r in drift_data["checks"]:
            if not r["ok"]:
                drift_obs_lines.append(f"  [FAIL] {r['id']}: {r['detail']}")
        traj_lines.append("[OBSERVATION]\n" + "\n".join(drift_obs_lines))

        # Render deliverable markdown with the updated OpenSpec files and verification summary
        deliv_parts: list[str] = [
            f"# OpenSpec Deliverable: `{task_id}`",
            "",
            "## Remediations Applied",
        ]
        if applied_actions:
            deliv_parts.extend(f"- {a}" for a in applied_actions)
        else:
            deliv_parts.append("- None (unmodified baseline artifact)")

        deliv_parts.extend(
            [
                "",
                "## Verification Report",
                f"- Structural & Strict Validation: {val_data['checks_ok']}/{val_data['checks_total']} checks succeeded",
                f"- Code-to-Spec Drift Alignment: {drift_data['checks_ok']}/{drift_data['checks_total']} checks succeeded",
                "",
                "### Check Breakdown",
            ]
        )
        for r in val_data["checks"] + drift_data["checks"]:
            status = "OK" if r["ok"] else "FAILED"
            deliv_parts.append(f"- [{status}] `{r['id']}`: {r['detail']}")

        deliv_parts.extend(["", "## Artifact Contents"])
        target_rel = self.tasks_spec[task_id]["path"]
        target_path = workspace / target_rel
        if target_path.is_file():
            files_to_show = [target_path]
        else:
            files_to_show = sorted(target_path.rglob("*.md"))
        for md_file in files_to_show:
            rel_name = md_file.relative_to(workspace).as_posix()
            deliv_parts.extend(
                [
                    "",
                    f"### `{rel_name}`",
                    "```markdown",
                    md_file.read_text(encoding="utf-8").rstrip(),
                    "```",
                ]
            )

        # Clean up workspace symlinks/copy after extracting deliverables to keep run_dir compact
        shutil.rmtree(workspace, ignore_errors=True)

        (run_dir / "deliverable.md").write_text("\n".join(deliv_parts) + "\n", encoding="utf-8")
        (run_dir / "trajectory.md").write_text("\n\n".join(traj_lines) + "\n", encoding="utf-8")

        n_passed = int(val_data["checks_ok"]) + int(drift_data["checks_ok"])
        n_criteria = int(val_data["checks_total"]) + int(drift_data["checks_total"])
        audit_payload = {
            "task_id": task_id,
            "n_passed": n_passed,
            "n_criteria": n_criteria,
            "all_pass": bool(val_data["all_checks_ok"] and drift_data["all_checks_ok"] and n_passed == n_criteria),
            "metric": "openspec_checks",
            "val_passed": val_data["checks_ok"],
            "val_total": val_data["checks_total"],
            "drift_passed": drift_data["checks_ok"],
            "drift_total": drift_data["checks_total"],
        }
        (run_dir / "audit_verdict.json").write_text(
            json.dumps(audit_payload, indent=2) + "\n", encoding="utf-8"
        )
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        return (Path(run_dir) / "deliverable.md").is_file()

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        text = (Path(run_dir) / "trajectory.md").read_text(encoding="utf-8")
        return text[:obs_trunc]

    def deliverable_text(self, run_dir: Path) -> str:
        return (Path(run_dir) / "deliverable.md").read_text(encoding="utf-8")

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        return {"deliverable.md": self.deliverable_text(run_dir)}

    def score(self, run_dir: Path, task_id: str) -> dict | None:
        del task_id
        verdict_file = Path(run_dir) / "audit_verdict.json"
        if not verdict_file.is_file():
            return None
        return json.loads(verdict_file.read_text(encoding="utf-8"))