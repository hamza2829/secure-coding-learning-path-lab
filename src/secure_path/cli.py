import argparse
from pathlib import Path

from .inputs import load_catalog, load_model, load_rules
from .models import STRATEGIES
from .planner import build_plans
from .reports import write_exports


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan and export secure coding training")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Compare two paths and export the selected one")
    build.add_argument("--catalog", type=Path, default=Path("catalog"))
    build.add_argument("--model", type=Path, default=Path("config/competencies.yml"))
    build.add_argument("--rules", type=Path, default=Path("config/path.yml"))
    build.add_argument("--group-size", required=True, type=int)
    build.add_argument("--strategy", choices=STRATEGIES, default=STRATEGIES[0])
    build.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        if not 1 <= args.group_size <= 100_000:
            raise ValueError("group size must be between 1 and 100000")
        model = load_model(args.model)
        catalog = load_catalog(args.catalog, model)
        rules = load_rules(args.rules)
        plans = build_plans(catalog, model, rules)
        selected = next(plan for plan in plans if plan.strategy == args.strategy)
        write_exports(args.out, model, catalog, rules, plans, selected, args.group_size)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Wrote learning path, cost comparison and Basic training exports to {args.out}")
    for level in selected.levels:
        print(f"{level.name}: {level.covered}/{level.targets} targets covered")
    if selected.basic.gaps:
        print("Basic has gaps. The LMS files contain zero assignments.")
    return 0
