# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OmpSubstrate: the Oh-My-Pi (omp) coding agent framework as a solver substrate.

Carries the c1..c8 surface (OMP_SURFACE), the `omp_root` install mode (`.omp/AGENTS.md`,
`.omp/RULES.md`, `.omp/skills`, `.omp/extensions`, `.omp/commands`, `.omp/agents`,
`sub_agents`, and `scripts` materialised at the workspace root where `omp --cwd <ws>`
discovers them natively), the `omp -p --mode json` flag contract, and the omp JSONL
event-stream trajectory renderer.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from .. import config
from ..core import runmark as RM
from ..core import tree as HT
from ..core.tree import SurfaceSpec
from .base import Install, Launcher, RunRequest

OMP_SURFACE = SurfaceSpec(
    name="omp",
    always_on=(
        ".omp/AGENTS.md",
        ".omp/RULES.md",
    ),
    always_on_max=24_000,
    always_on_cap_reason=(
        ".omp/AGENTS.md (project context) and .omp/RULES.md (sticky always-apply rules) "
        "travel with every request and compete with the agent's output budget"
    ),
    skill_dir=".omp/skills",
    skill_name_rule="must_match",
    trigger_hint=(
        "Fix it by adding a trigger line naming `{name}` to .omp/AGENTS.md or "
        '.omp/RULES.md, e.g. "When <the situation this skill handles>, read '
        '`skill://{name}` and follow it."'
    ),
    autotrigger_file=".omp/RULES.md",
    trigger_line="- When {desc}, read `skill://{name}` and follow it.\n",
    subagent_requires_mode=False,
    plugin_dir=".omp/extensions",
    hooks_file=None,
    compile_skill_scripts=True,
    reject_empty_always_on=True,
    stubs=(
        (
            "scripts/README.md",
            "<!-- c7: deterministic helpers, run as `python3 scripts/<name>.py`. "
            "Add one by emitting scripts/<name>.py. -->\n",
        ),
        (
            "sub_agents/README.md",
            "<!-- c5: delegated omp task subagents, each spawned in its OWN context via the "
            "`task` tool. Add one as sub_agents/<name>/AGENT.md with frontmatter `name:` and "
            "`description:`; materialise() also installs it to .omp/agents/<name>.md. -->\n",
        ),
        (
            ".omp/extensions/README.md",
            "<!-- c8: omp runtime extensions (`ExtensionAPI`). Acts INSIDE the tool and turn "
            "loop via `pi.on('tool_call' | 'tool_result' | 'session_stop', ...)` -- the only "
            "lever that can enforce something the model cannot skip. Add one as "
            ".omp/extensions/<name>.ts. -->\n",
        ),
        (
            ".omp/skills/README.md",
            "<!-- c6: reusable workflows loaded on demand via `read` on `skill://<name>`. "
            "Add one as .omp/skills/<name>/SKILL.md with frontmatter `name:` matching the "
            "directory and a required `description:`. -->\n",
        ),
    ),
)

OMP_ROOT_ENTRIES = (".omp", "sub_agents", "scripts")


def _ensure_omp_agent_frontmatter(name: str, body: str) -> str:
    """Ensure `.omp/agents/<name>.md` has `name: <name>` in its YAML frontmatter for omp."""
    if not body.startswith("---\n"):
        return f"---\nname: {name}\ndescription: Subagent {name}\n---\n\n{body}"
    end = body.find("\n---\n", 4)
    if end == -1:
        return body
    fm = body[4:end]
    rest = body[end + 5 :]
    if not re.search(r"^name:\s*\S", fm, re.M):
        fm = f"name: {name}\n" + fm
    return f"---\n{fm}\n---\n{rest}"


class OmpSubstrate:
    """Oh-My-Pi (`omp`) behind the one Substrate interface."""

    name = "omp"

    def __init__(self, launcher: Launcher | None = None):
        self._launcher = launcher

    def surface(self) -> SurfaceSpec:
        return OMP_SURFACE

    def materialise(self, tree_dir: Path, spec, ctx: Mapping[str, str]) -> Install:
        """Stage the omp harness tree for workspace execution, bridging `sub_agents/<name>/AGENT.md`
        into `.omp/agents/<name>.md` so omp's native task agent discovery finds them."""
        if spec.install_mode != "omp_root":
            raise ValueError(
                f"install_mode {spec.install_mode!r} is not the omp mode; this substrate "
                f"has exactly one: 'omp_root'"
            )
        tree_dir = Path(tree_dir)
        if not HT.is_tree(OMP_SURFACE, tree_dir):
            raise ValueError(
                f"{tree_dir} is not an omp harness tree (no .omp/AGENTS.md or .omp/RULES.md)"
            )
        staged = Path(tempfile.mkdtemp(prefix="adapt-omp-root-"))
        try:
            for entry in OMP_ROOT_ENTRIES:
                src = tree_dir / entry
                if not src.exists():
                    continue
                if src.is_dir():
                    shutil.copytree(src, staged / entry, dirs_exist_ok=True)
                else:
                    (staged / entry).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, staged / entry)

            for key, body in ctx.items():
                if key.startswith("file:"):
                    rel = HT.normalize_rel(key[len("file:") :])
                    p = staged / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(body, encoding="utf-8")

            # Bridge harness2's canonical sub_agents/<name>/AGENT.md into .omp/agents/<name>.md
            for agent_md in sorted((staged / "sub_agents").glob("*/AGENT.md")):
                agent_name = agent_md.parent.name
                omp_agent_path = staged / ".omp" / "agents" / f"{agent_name}.md"
                omp_agent_path.parent.mkdir(parents=True, exist_ok=True)
                omp_agent_path.write_text(
                    _ensure_omp_agent_frontmatter(
                        agent_name, agent_md.read_text(encoding="utf-8", errors="replace")
                    ),
                    encoding="utf-8",
                )
        except BaseException:
            shutil.rmtree(staged, ignore_errors=True)
            raise

        return Install(
            staging_dir=staged,
            fingerprint=RM.fingerprint(tree_dir),
            extras={
                "install_mode": "omp_root",
                **{k: v for k, v in ctx.items() if not k.startswith("file:")},
            },
        )

    def run_argv(
        self,
        prompt: str,
        workspace: Path,
        model: str,
        *,
        thinking: str = "high",
    ) -> list[str]:
        """The reference `omp -p --mode json` argv for headless rollout execution."""
        cli = shutil.which("omp") or str(config.OMP_BIN)
        argv = [
            cli,
            "-p",
            "--mode",
            "json",
            "--no-session",
            "--no-title",
            "--yolo",
            "--cwd",
            str(workspace),
        ]
        if model:
            argv += ["--model", model]
        if thinking:
            argv += ["--thinking", thinking]
        argv.append(prompt)
        return argv

    def execute(
        self, task_ref: str, install: Install, run_ids: list[str], timeout: int
    ) -> list[Path]:
        if self._launcher is None:
            raise RuntimeError(
                "OmpSubstrate was constructed without a launcher body; the benchmark "
                "adapter must supply one"
            )
        return self._launcher(
            RunRequest(task_ref=task_ref, run_ids=tuple(run_ids), timeout=int(timeout)), install
        )

    def read_trajectory(
        self, stream_path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 800
    ) -> str:
        return render_events(
            Path(stream_path), obs_trunc=obs_trunc, max_chars=max_chars, args_trunc=args_trunc
        )

    def preflight(self) -> None:
        """Checks the `omp` CLI binary is available on PATH or at config.OMP_BIN."""
        cli = shutil.which("omp") or (str(config.OMP_BIN) if Path(config.OMP_BIN).is_file() else "")
        if not cli:
            raise RuntimeError(
                "omp CLI not found on PATH or at HARNESS2_OMP_BIN; install @oh-my-pi/pi-coding-agent "
                "or set HARNESS2_OMP_BIN."
            )


_TRUNC_FMT = "…(+{n} chars — render truncation)"


def _clip(s, n: int) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\x00", "")
    if n <= 0 or len(s) <= n:
        return s
    return s[:n] + _TRUNC_FMT.format(n=len(s) - n)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return "\n".join(parts)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return ""


def render_events(path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 800) -> str:
    """Render omp's `-p --mode json` JSONL event stream into the shared grammar."""
    args_cap = int(args_trunc)
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"(failed to read trajectory: {e})"
    lines: list[str] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        etype = ev.get("type", "")
        if etype == "message_end":
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            role = msg.get("role", "")
            content = msg.get("content")
            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "thinking":
                        t = block.get("thinking") or block.get("text")
                        if isinstance(t, str) and t.strip():
                            lines.append(f"[THINKING] {_clip(t, obs_trunc)}")
                    elif btype == "text":
                        t = block.get("text")
                        if isinstance(t, str) and t.strip():
                            lines.append(f"[ASSISTANT] {_clip(t, obs_trunc)}")
                    elif btype in ("toolCall", "tool_call", "tool_use"):
                        name = block.get("name") or block.get("toolName") or "tool"
                        tin = block.get("arguments") or block.get("input") or {}
                        args = json.dumps(tin, default=str, ensure_ascii=False)
                        lines.append(f"[ACTION] {name}({_clip(args, args_cap)})")
        elif etype == "tool_execution_end":
            res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            is_err = bool(ev.get("isError") or res.get("isError"))
            txt = _extract_text(res.get("content")) or str(res.get("error") or "")
            tag = "OBSERVATION ERROR" if is_err else "OBSERVATION"
            lines.append(f"[{tag}] {_clip(txt, obs_trunc)}")
        elif etype == "error" or ev.get("error"):
            err = ev.get("error") or ev.get("message") or json.dumps(ev)[:300]
            lines.append(f"[ERROR] {_clip(err, 300)}")
    rendered = "\n".join(lines).strip()
    if not rendered:
        return "(no parseable events in trajectory)"
    if len(rendered) > max_chars:
        dropped = len(rendered) - max_chars
        rendered = rendered[:max_chars] + "\n" + _TRUNC_FMT.format(n=dropped)
    return rendered
