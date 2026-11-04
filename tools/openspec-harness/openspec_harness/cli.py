"""CLI entrypoint for Google's harness2 + OpenSpec integration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from harness2.core import judge, report, schedule
from harness2.core import tree as harness_tree
from harness2.substrate.omp import OMP_SURFACE
from harness2.substrate.opencode import OPENCODE_SURFACE
from .adapter import RUNTIME_SCRIPTS, OpenSpecAdapter
from .proposer import OpenSpecScriptedProposer
from .remediate import apply_all_remediations


def _repo_root() -> Path:
    return Path.cwd()


def _census(surface: harness_tree.SurfaceSpec, t: harness_tree.Tree) -> dict[str, int]:
    counts = {
        "files": len(t),
        "always_on_chars": len(harness_tree.always_on_text(surface, t)),
        "skills": 0,
        "sub_agents": 0,
        "commands": 0,
        "scripts": 0,
        "plugins": 0,
        "hooks": 0,
    }
    skill_prefix = surface.skill_dir + "/"
    plugin_prefix = (surface.plugin_dir + "/") if surface.plugin_dir else None
    for rel in t:
        if rel.startswith(skill_prefix) and rel.endswith("/SKILL.md"):
            counts["skills"] += 1
        elif rel.startswith("sub_agents/") and rel.endswith("/AGENT.md"):
            counts["sub_agents"] += 1
        elif rel.startswith("commands/") and rel.endswith(".md"):
            counts["commands"] += 1
        elif rel.startswith("scripts/"):
            counts["scripts"] += 1
        elif plugin_prefix and rel.startswith(plugin_prefix):
            counts["plugins"] += 1
        elif surface.hooks_file and rel == surface.hooks_file:
            counts["hooks"] += 1
    return counts


def cmd_validate_harnesses(args: argparse.Namespace) -> int:
    root = _repo_root()
    h2 = root / ".harness2" / "harnesses"
    targets = [
        ("opencode_seed", h2 / "opencode_seed", OPENCODE_SURFACE),
        ("opencode_base", h2 / "opencode_base", OPENCODE_SURFACE),
        ("omp_seed", h2 / "omp_seed", OMP_SURFACE),
        ("omp_base", h2 / "omp_base", OMP_SURFACE),
    ]
    rows = []
    for name, path, surface in targets:
        rejected: list[str] = []
        t = harness_tree.read_tree(surface, path, rejected=rejected)
        if rejected:
            print(f"[FAIL] {name}: off-surface files: {rejected}", file=sys.stderr)
            return 1
        harness_tree.validate(
            surface,
            t,
            allow_subagents=True,
            reserved_scripts=harness_tree.RESERVED_SCRIPTS | RUNTIME_SCRIPTS,
        )
        c = _census(surface, t)
        rows.append({"name": name, "surface": surface.name, "cap": surface.always_on_max, **c})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("harness2 c1..c8 Surface Validation")
        print("=" * 72)
        for r in rows:
            print(
                f"  [PASS] {r['name']:<15} ({r['surface']:<8}) | "
                f"always-on: {r['always_on_chars']:>5,}/{r['cap']:,} chars | "
                f"files={r['files']} skills={r['skills']} sub_agents={r['sub_agents']} "
                f"scripts={r['scripts']} plugins={r['plugins']} hooks={r['hooks']}"
            )
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve() if args.repo_root else _repo_root()
    target_root = Path(args.root).resolve() if args.root else root
    val_cmd = [
        sys.executable,
        "-m",
        "openspec_harness.validation",
        "--workspace",
        str(target_root),
        "--repo-root",
        str(root),
    ]
    drift_cmd = [
        sys.executable,
        "-m",
        "openspec_harness.drift",
        "--repo-root",
        str(root),
    ]
    if args.item:
        val_cmd.extend(["--target", args.item])
        drift_cmd.extend(["--target", args.item])
    if args.json:
        val_cmd.append("--json")
        drift_cmd.append("--json")
        v = json.loads(subprocess.run(val_cmd, capture_output=True, text=True).stdout)
        d = json.loads(subprocess.run(drift_cmd, capture_output=True, text=True).stdout)
        ok = bool(v["all_checks_ok"] and d["all_checks_ok"])
        print(json.dumps({"validation": v, "drift": d, "ok": ok}, indent=2))
        return 0 if ok else 1

    r1 = subprocess.run(val_cmd)
    print()
    r2 = subprocess.run(drift_cmd)
    return 0 if (r1.returncode == 0 and r2.returncode == 0) else 1


def cmd_remediate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else _repo_root()
    actions = apply_all_remediations(root, args.item)
    print(f"Applied {len(actions)} OpenSpec INV+DOM remediations under {root}:")
    for a in actions:
        print(f"  - {a}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    from .init import init_repository

    repo = Path.cwd()
    written = init_repository(repo)
    print(f"Scaffolded {len(written)} file(s) under {repo}.")
    print("Next: edit openspec/harness.yaml tasks and openspec/drift-checks.yaml checks.")
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    root = _repo_root()
    runs_root = Path(args.runs_root).resolve() if args.runs_root else (root / ".harness2" / "runs" / "openspec_sts")
    modes = tuple(schedule.mode_token(m) for m in args.modes.split(",") if m.strip())
    k_values = [int(x.strip()) for x in str(args.k).split(",") if x.strip()]

    adapter = OpenSpecAdapter(
        root,
        substrate_name=args.substrate,
        runs_root=runs_root,
        use_seed_base=not args.from_full_base,
    )
    prop = OpenSpecScriptedProposer(root, substrate_name=args.substrate)

    all_scored: list[judge.Scored] = []
    base_scored: list[judge.Scored] = []
    fell_back: dict[tuple[str, int], int] = {}

    for k in k_values:
        library_root = runs_root / "library" / f"k{k}"
        rep = schedule.run_sweep(
            k,
            adapter=adapter,
            prop=prop,
            runs_root=runs_root,
            library_root=library_root,
            split="all",
            modes=modes,
            seed=args.seed,
            tag=args.tag,
            domain_parallel=1,
            pool_policy="finals",
        )

        # Collect selections and base rollouts for judging
        selections: list[dict] = []
        base_seen: set[str] = set()
        for task_id in adapter.tasks("all"):
            base_ns = schedule.Namespace(adapter.spec.name, adapter.substrate.name, "agg", k, args.seed, args.tag)
            summary_path = base_ns.task_dir(runs_root, task_id) / "summary.json"
            if not summary_path.is_file():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if k == k_values[0] and task_id not in base_seen and summary.get("base"):
                b0 = summary["base"][0]
                base_scored.append(
                    judge.judge_one(
                        adapter,
                        task_id,
                        "base",
                        0,
                        b0["label"],
                        b0["run_id"],
                        Path(b0["run_dir"]),
                        chosen_is_base=True,
                    )
                )
                base_seen.add(task_id)
            for m in modes:
                m_rec = (summary.get("modes") or {}).get(m) or {}
                fell_back[(m, k)] = fell_back.get((m, k), 0) + len(m_rec.get("fell_back") or [])
                sel = (summary.get("selections") or {}).get(m)
                if sel:
                    selections.append(sel)

        scored = judge.judge_selections(adapter, selections)
        judge.write(scored, runs_root / "_judged" / f"openspec-{adapter.substrate.name}-k{k}.json")
        all_scored.extend(scored)
        del rep

    judge.write(base_scored, runs_root / "_judged" / f"openspec-{adapter.substrate.name}-base.json")
    summaries = report.summarise(all_scored, fell_back=fell_back)
    base_summary = report.summarise(base_scored)

    print("\n" + "=" * 76)
    if base_summary:
        b = base_summary[0]
        print(
            f"  seed baseline (k=0): n={b.n:>3} | score {b.score:6.2f}% | "
            f"all-checks-pass {b.all_pass:5.1f}%"
        )
    print(
        report.render(
            summaries,
            title=f"harness2 x OpenSpec Adaptation Sweep (substrate={adapter.substrate.name})",
            bench="lab",
        )
    )
    print("=" * 76)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openspec-harness",
        description="Google harness2 recursive agent harness for OpenSpec",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Scaffold OpenSpec harness config for this repository")
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser("validate-harnesses", help="Validate c1..c8 harness surfaces")
    p_val.add_argument("--json", action="store_true")
    p_val.set_defaults(func=cmd_validate_harnesses)

    p_aud = sub.add_parser("audit", help="Run deterministic OpenSpec strict + code-drift checks")
    p_aud.add_argument("--root", type=str, default=None)
    p_aud.add_argument("--repo-root", type=str, default=None, help="Repository root (default: current directory)")
    p_aud.add_argument("--item", type=str, default=None)
    p_aud.add_argument("--json", action="store_true")
    p_aud.set_defaults(func=cmd_audit)

    p_rem = sub.add_parser("remediate", help="Apply INV+DOM OpenSpec remediations to the workspace")
    p_rem.add_argument("--root", type=str, default=None)
    p_rem.add_argument("--item", type=str, default=None)
    p_rem.set_defaults(func=cmd_remediate)

    p_swp = sub.add_parser("sweep", help="Run two-level harness2 recursion over OpenSpec tasks")
    p_swp.add_argument("--substrate", choices=("oc", "omp"), default="oc")
    p_swp.add_argument("--modes", default="parallel,sequential")
    p_swp.add_argument("--k", default="1,2")
    p_swp.add_argument("--seed", type=int, default=None)
    p_swp.add_argument("--tag", default="")
    p_swp.add_argument("--runs-root", default=None)
    p_swp.add_argument("--from-full-base", action="store_true")
    p_swp.set_defaults(func=cmd_sweep)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
