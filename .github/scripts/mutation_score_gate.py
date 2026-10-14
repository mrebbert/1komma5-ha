"""Score-gate helper for the mutation-testing workflow.

Reads `mutation-results.txt` (one survivor per line, mutmut format), compares
the current survivor counts against a baseline committed to the repo
(`.mutmut-baseline` JSON), and either passes or fails the job.

The baseline file is the single source of truth. It carries:

- `total_survivors_max`: hard cap on the total number of surviving mutations.
- `per_function_max`: per-function caps; any listed function that regresses
  beyond its cap fails the job.
- Functions not listed in `per_function_max` are only guarded by the global
  total (so adding a new function to the codebase does not break CI
  immediately).

When a mutation lane kills survivors, run this script with `--write-baseline`
locally against the latest `mutation-results.txt` to produce a fresh JSON
with the lowered caps, then commit the updated file alongside the test PR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MUTANT_RE = re.compile(
    r"^\s*(?P<module>custom_components\.onekommafive\.[a-z_]+)"
    r"\.(?P<fn>x[ǁǂǀ]?[A-Za-z0-9_ǀ-ǂ]+?)"
    r"__mutmut_\d+:\s*survived\s*$"
)


def _parse_results(path: Path) -> dict[str, int]:
    """Return a {function_label: survivor_count} map.

    Function label is the mutmut qualifier stripped of the leading `x` and
    `ǁ` separators, e.g.
    `custom_components.onekommafive.helpers.x__find_window__mutmut_1`
    becomes `helpers._find_window`;
    `...sensor_entities.xǁOneKomma5PriceSensorǁ_price_breakdown__mutmut_6`
    becomes `sensor_entities.OneKomma5PriceSensor._price_breakdown`.
    """
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.endswith(": survived"):
            continue
        head = stripped.split(":", 1)[0]
        # Drop the trailing `__mutmut_<N>` suffix.
        qualifier = head.rsplit("__mutmut_", 1)[0]
        # Strip the `custom_components.onekommafive.` prefix.
        qualifier = qualifier.removeprefix("custom_components.onekommafive.")
        # Split module + mutant-tag; the mutant-tag contains the function
        # (prefixed with `x` and class-separated by `ǁ`).
        if "." not in qualifier:
            continue
        module, mutant_tag = qualifier.split(".", 1)
        # Replace mutmut's `xǁClassǁmethod` with `Class.method`, or plain
        # `x_fn` with `fn`.
        parts = mutant_tag.split("ǁ")
        if len(parts) == 1:
            # Flat function: strip the leading `x` and (optional) `_`.
            fn = parts[0].removeprefix("x_").removeprefix("x")
            label = f"{module}.{fn}"
        else:
            # Class method: `xǁClassǁmethod[Ǳ...]` — drop the leading `x`.
            parts[0] = parts[0].removeprefix("x")
            parts = [p for p in parts if p]  # drop any empty strings
            label = f"{module}." + ".".join(parts)
        counts[label] = counts.get(label, 0) + 1
    return counts


def _render_summary(counts: dict[str, int], total: int, baseline_total: int) -> str:
    score = 1 - (total / 918)  # 918 total mutants on current source tree
    lines = [
        f"### Mutation score: **{score * 100:.1f} %**",
        "",
        f"Total survivors: **{total}** (baseline max: {baseline_total})",
        "",
        "| Function | Survivors |",
        "| --- | ---: |",
    ]
    for label, count in sorted(counts.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"| `{label}` | {count} |")
    return "\n".join(lines) + "\n"


def _check(counts: dict[str, int], baseline: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    total = sum(counts.values())
    total_max = baseline.get("total_survivors_max")
    if isinstance(total_max, int) and total > total_max:
        issues.append(f"Total survivors regressed: {total} > baseline max {total_max}.")
    per_fn_max = baseline.get("per_function_max", {})
    for label, cap in per_fn_max.items():
        current = counts.get(label, 0)
        if current > cap:
            issues.append(
                f"`{label}` regressed: {current} survivors (baseline max {cap})."
            )
    return (not issues), issues


def _write_baseline(path: Path, counts: dict[str, int]) -> None:
    """Rewrite the baseline file from the current counts.

    Caps every function at its CURRENT count (so the next run has to match or
    improve). Keeps the top-level comment + updated_at timestamp conventions
    the manual edits already use.
    """
    import datetime  # local import — only used in the write path

    data = {
        "comment": (
            "Mutation-score baseline — see .github/scripts/mutation_score_gate.py "
            "for semantics. Only lower these caps; never raise them."
        ),
        "updated_at": datetime.date.today().isoformat(),
        "total_survivors_max": sum(counts.values()),
        "per_function_max": dict(sorted(counts.items())),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, required=True, help="mutation-results.txt"
    )
    parser.add_argument(
        "--baseline", type=Path, required=True, help=".mutmut-baseline JSON"
    )
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Print a Markdown summary to stdout (feed into $GITHUB_STEP_SUMMARY).",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite the baseline file with the current counts.",
    )
    args = parser.parse_args()

    if not args.results.exists():
        print(f"mutation results file not found: {args.results}", file=sys.stderr)
        return 2

    counts = _parse_results(args.results)
    total = sum(counts.values())

    if args.write_baseline:
        _write_baseline(args.baseline, counts)
        print(
            f"Wrote baseline with {total} total survivors across "
            f"{len(counts)} functions to {args.baseline}.",
            file=sys.stderr,
        )
        return 0

    if not args.baseline.exists():
        print(f"baseline file not found: {args.baseline}", file=sys.stderr)
        return 2
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    ok, issues = _check(counts, baseline)
    if args.write_summary:
        print(_render_summary(counts, total, baseline.get("total_survivors_max", -1)))
        if issues:
            print("\n### Regressions\n")
            for issue in issues:
                print(f"- {issue}")

    if not ok:
        print("Mutation score regressed:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
