#!/usr/bin/env python3
"""Thin CLI wrapper for src.app.evaluation.diagnostic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.app.evaluation.diagnostic import DiagnosticConfig, run_diagnostic_sync


def _parse_seeds(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _parse_conditions(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run accuracy diagnostic harness")
    parser.add_argument("--preset", default="economy")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--conditions", default="0,1,2,3,3b")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "evaluation" / "baselines"),
    )
    args = parser.parse_args()

    result = run_diagnostic_sync(
        DiagnosticConfig(
            preset=args.preset,
            runs=args.runs,
            seeds=_parse_seeds(args.seeds),
            conditions=_parse_conditions(args.conditions),
            output_dir=Path(args.output_dir),
            dry_run=args.dry_run,
        )
    )
    if args.dry_run:
        print(result["dry_run"])
    else:
        print({
            "status": result["summary"]["status"],
            "run_id": result["run_id"],
            "output_dir": str(Path(args.output_dir)),
        })


if __name__ == "__main__":
    main()
