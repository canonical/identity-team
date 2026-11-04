"""Proposer for OpenSpec harness adaptation (scripted local evolution + live LLM fallback)."""

from __future__ import annotations

import shutil
from pathlib import Path

from harness2.core import tree as harness_tree
from harness2.core.proposer import Proposer, Reply
from harness2.core.spec import ChannelSpec
from harness2.substrate.omp import OMP_SURFACE
from harness2.substrate.opencode import OPENCODE_SURFACE
TASK_LESSONS: dict[str, dict[str, str]] = {
    "artifact-security-gate": {
        "cue": "When an archived OpenSpec capability spec retains a `TBD - created by archiving` placeholder in `## Purpose`",
        "lesson": "Pair `openspec-strict-authoring` with `sts-go-domain` to synthesize a concrete `## Purpose` grounded in the CI workflow (`.github/workflows/secscan-gate.yaml`) and `rockcraft.yaml` before running `scripts/validate_openspec.py`.",
        "evidence": "In `base1`, `spec:artifact-security-gate:purpose` failed due to the `TBD` archive placeholder; `dom1` and the composed final replaced it with the Trivy/Syft security-gate contract and resolved all 6 structural and 3 code-drift checks.",
        "confidence": "high across archived OpenSpec specifications in STS",
    },
    "m2m-token-exchange": {
        "cue": "When an OpenSpec change links to `.archify/` from a delta spec (`changes/<id>/specs/<cap>/spec.md`) or leaves `Implementation Notes` as template text",
        "lesson": "Enforce 5-level `../../../../../` relative link traversal from delta specs in `openspec_spec_auditor` (`INV`) while populating `Implementation Notes` from `pkg/core/service.go` and `pkg/authn/` (`DOM`).",
        "evidence": "In `base1`, 3 `.archify` links failed with 4-level `../../../../` paths (`INV`) and `tasks_notes` failed on template text (`DOM`); only the composed harness (`agg1`/`c1`) resolved all 16 structural checks and 3 drift checks simultaneously.",
        "confidence": "high for multi-file OpenSpec change bundles",
    },
    "support-multi-arch-rocks-and-pipelines": {
        "cue": "When an OpenSpec change modifies an existing capability spec and references repository files from `proposal.md` and `tasks.md`",
        "lesson": "Use `openspec-strict-authoring` to enforce 3-level `../../../` relative links from `changes/<id>/*.md` and `<= 500` char requirement bodies, and use `sts-go-domain` to ensure delta specs include `## Purpose`.",
        "evidence": "In `base1`, 16 relative links in `proposal.md`/`tasks.md` and 2 requirement bodies (550 and 691 chars) failed (`INV`), while `specs/artifact-security-gate/spec.md` lacked `## Purpose` (`DOM`); composing `inv1` + `dom1` fixed all 20 structural and 3 drift checks.",
        "confidence": "high for cross-cutting CI and Rockcraft OpenSpec changes",
    },
    "support-ubuntu-one-openid": {
        "cue": "When `openspec validate --strict` rejects a delta spec for exceeding 500 characters or `tasks.md` uses unnumbered bullets in `Verification Suite`",
        "lesson": "Apply `openspec-strict-authoring` to condense `### Requirement:` bodies under 500 characters without dropping `SHALL` clauses, convert `Verification Suite` bullets to numbered checkboxes (`1. [x]`), and prefix `design.md` repo links with `../../../`.",
        "evidence": "In `base1`, `openspec validate --strict` failed on 536-char and 633-char requirements in `openid-provider-login/spec.md`, 7 links in `design.md` failed resolution, and `Verification Suite` lacked numbered checkboxes; the composed harness passed all 15 structural and 3 drift checks.",
        "confidence": "high for strict OpenSpec change validation",
    },
}


class OpenSpecScriptedProposer(Proposer):
    """Deterministic local proposer exercising INV, DOM, AGG/COMPOSE, Selection, and Library reflection."""

    def __init__(self, repo_root: Path, substrate_name: str = "oc") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.harness2_dir = self.repo_root / ".harness2"
        self.substrate_name = "omp" if substrate_name == "omp" else "oc"
        self.surface = OMP_SURFACE if self.substrate_name == "omp" else OPENCODE_SURFACE
        channel_kind = "omp" if self.substrate_name == "omp" else "opencode"
        spec = ChannelSpec(channel_kind, "google/gemini-2.5-pro")
        super().__init__(spec, audit_dir=None)

    def _full_harness_dir(self) -> Path:
        if self.substrate_name == "omp":
            return self.harness2_dir / "harnesses" / "omp_base"
        return self.harness2_dir / "harnesses" / "opencode_base"
    def _copy_rel(self, src_root: Path, dst_root: Path, rel: str) -> None:
        src = src_root / rel
        if src.is_file():
            dst = dst_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _detect_task_id(self, context: Path) -> str:
        task_md = context / "task.md"
        if task_md.is_file():
            body = task_md.read_text(encoding="utf-8")
            for tid in sorted(TASK_LESSONS, key=len, reverse=True):
                if tid in body:
                    return tid
        return "artifact-security-gate"

    def call(self, mission: str, context_dir: Path | str, label: str, **kwargs) -> Reply:
        del mission, kwargs
        context = Path(context_dir)
        workspace: Path | None = None
        stage_prefix = label.split(".")[0]

        if label.startswith("select."):
            candidates = sorted((context / "candidates").glob("*.md"))
            best_anon = candidates[0].stem if candidates else "A"
            best_failed = 999999
            for cand in candidates:
                body = cand.read_text(encoding="utf-8")
                failed_count = body.count("- [FAILED]")
                if failed_count < best_failed:
                    best_failed = failed_count
                    best_anon = cand.stem
            text = (
                f"<why>Candidate {best_anon} achieved {best_failed} failed verification checks "
                f"across `openspec validate --strict`, `openspec/config.yaml` contracts, "
                f"relative Markdown link resolution, and Go 1.26 code-drift alignment, "
                f"combining both task-agnostic OpenSpec structural rules (INV) and STS "
                f"domain traceability (DOM).</why>\n"
                f"```choice\n{best_anon}\n```"
            )
        elif label.startswith("experience."):
            task_id = self._detect_task_id(context)
            lesson_info = TASK_LESSONS[task_id]
            skill_dir = self.surface.skill_dir
            text = (
                "<edits>\n"
                f"component: {skill_dir}/openspec-strict-authoring/SKILL.md\n"
                "candidates: inv1, agg1, c1\n"
                "change: added strict <=500 char requirement guardrails, 3-level/5-level relative link depth table, and numbered checkbox rules\n"
                "observed: resolved all strict schema, link resolution, and checklist formatting failures\n"
                "verdict: helped\n\n"
                f"component: {skill_dir}/sts-go-domain/SKILL.md\n"
                "candidates: dom1, agg1, c1\n"
                "change: added STS Go 1.26 package map and non-placeholder Purpose / Implementation Notes rules\n"
                "observed: resolved archive TBD purpose placeholders and implementation notes gaps\n"
                "verdict: helped\n"
                "</edits>\n\n"
                "<experience>\n"
                f"cue: {lesson_info['cue']}\n"
                f"lesson: {lesson_info['lesson']}\n"
                f"evidence: {lesson_info['evidence']}\n"
                f"confidence: {lesson_info['confidence']}\n"
                "</experience>"
            )
        else:
            workspace = context / "harness"
            full_dir = self._full_harness_dir()
            lib_index = context / "library" / "INDEX.md"
            lib_note = (
                " Reused prior domain experience from `context/library/INDEX.md`."
                if lib_index.is_file()
                else ""
            )

            skill_dir = self.surface.skill_dir
            plugin_dir = self.surface.plugin_dir or "plugin"
            if stage_prefix.startswith("inv"):
                rels = [
                    f"{skill_dir}/openspec-strict-authoring/SKILL.md",
                    "sub_agents/openspec_spec_auditor/AGENT.md",
                    f"{plugin_dir}/openspec_guard.ts",
                    "commands/openspec-check.md",
                ]
                for rel in rels:
                    self._copy_rel(full_dir, workspace, rel)
                if stage_prefix.endswith("2"):
                    target_file = workspace / self.surface.autotrigger_file
                    if target_file.is_file():
                        target_file.write_text(
                            target_file.read_text(encoding="utf-8").rstrip()
                            + "\n- Always verify both 3-level (`../../../`) and 5-level (`../../../../../`) relative link depths.\n",
                            encoding="utf-8",
                        )
                text = (
                    "<notes>Added `openspec-strict-authoring` skill, `openspec_spec_auditor` "
                    "subagent, and execution guard to enforce `<= 500` char requirement bodies, "
                    "3-level/5-level relative Markdown link resolution, and numbered checkboxes "
                    f"observed failing in `context/rollouts/base1.md`.{lib_note}</notes>"
                )
            elif stage_prefix.startswith("dom"):
                rels = [
                    f"{skill_dir}/sts-go-domain/SKILL.md",
                    f"{skill_dir}/openspec-detect-drift/SKILL.md",
                    "sub_agents/sts_security_reviewer/AGENT.md",
                    "commands/openspec-drift.md",
                ]
                for rel in rels:
                    self._copy_rel(full_dir, workspace, rel)
                if stage_prefix.endswith("2"):
                    target_file = workspace / self.surface.always_on[0]
                    if target_file.is_file():
                        target_file.write_text(
                            target_file.read_text(encoding="utf-8").rstrip()
                            + "\n\nCross-check `## Purpose` and `## Implementation Notes` against `internal/grpc/server.go` and `internal/auth/`.\n",
                            encoding="utf-8",
                        )
                text = (
                    "<notes>Added `sts-go-domain` and `openspec-detect-drift` skills, "
                    "`sts_security_reviewer` subagent, and `scripts/check_openspec_drift.py` "
                    "to remediate archive `TBD` purpose placeholders and verify alignment with "
                    f"Go 1.26 `pkg/core`, `pkg/authn`, and CI workflows.{lib_note}</notes>"
                )
            else:
                # AGG or COMPOSE stage: merge all components from the full target harness
                for p in sorted(full_dir.rglob("*")):
                    if p.is_file():
                        rel = p.relative_to(full_dir).as_posix()
                        self._copy_rel(full_dir, workspace, rel)
                if stage_prefix.endswith("2"):
                    target_file = workspace / self.surface.always_on[0]
                    if target_file.is_file():
                        target_file.write_text(
                            target_file.read_text(encoding="utf-8").rstrip()
                            + "\n\nAlways run both `python3 scripts/validate_openspec.py` and `python3 scripts/check_openspec_drift.py` before finishing.\n",
                            encoding="utf-8",
                        )
                text = (
                    "<notes>Composed task-agnostic OpenSpec structural guardrails (`INV`: "
                    "`openspec-strict-authoring`, `openspec_spec_auditor`, `openspec_guard.ts`) "
                    "with STS Go 1.26 domain skills (`DOM`: `sts-go-domain`, `openspec-detect-drift`, "
                    "`sts_security_reviewer`, `check_openspec_drift.py`) into a unified `c1..c8` "
                    f"harness tree.{lib_note}</notes>"
                )

            # Ensure all skills and subagents are wired in always-on instructions
            cur_tree = harness_tree.read_tree(self.surface, workspace)
            harness_tree.autotrigger(self.surface, cur_tree)
            harness_tree.write_tree(self.surface, cur_tree, workspace, stubs=False)
        reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
        self._calls.append(reply)
        return reply
