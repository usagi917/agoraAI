"""予測精度診断ハーネス。

条件定義、manifest holdout 読み込み、評価集計、YAML出力をここに集約する。
実際のスワーム実行は Simulation row + dispatch_simulation 経由で行う。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml
from sqlalchemy import select

from src.app.database import async_session
from src.app.evaluation.retrodiction_runner import evaluate_case
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.services.simulation_dispatcher import dispatch_simulation
from src.app.services.society.constants import STANCE_ORDER
from src.app.services.society.diagnostic_baseline import run_single_llm_distribution
from src.app.services.society.survey_anchor import (
    load_manifest_anchor_distribution,
    normalize_stance_distribution,
)
from src.app.services.society.validation_pipeline import (
    load_manifest_split,
    validate_no_leakage,
)
from src.app.utils.distribution_metrics import earth_movers_distance

logger = logging.getLogger(__name__)


PredictionFn = Callable[[dict[str, Any], int, int], Awaitable[dict[str, float]]]


@dataclass(frozen=True)
class DiagnosticCondition:
    id: str
    label: str
    diagnostic: dict[str, Any] | None
    uses_simulation: bool
    description: str


@dataclass(frozen=True)
class DiagnosticConfig:
    preset: str = "economy"
    runs: int = 3
    seeds: tuple[int, ...] = (42, 43, 44)
    conditions: tuple[str, ...] = ("0", "1", "2", "3", "3b")
    output_dir: Path = Path("evaluation/baselines")
    dry_run: bool = False
    cross_source_trials: int = 3


def condition_definitions(preset: str) -> dict[str, DiagnosticCondition]:
    return {
        "0": DiagnosticCondition(
            id="0",
            label="null_train_average",
            diagnostic=None,
            uses_simulation=False,
            description="train平均分布をそのまま提出するヌルモデル",
        ),
        "1": DiagnosticCondition(
            id="1",
            label="single_llm_distribution",
            diagnostic=None,
            uses_simulation=False,
            description="単一LLMによる5分類分布推定",
        ),
        "2": DiagnosticCondition(
            id="2",
            label="current_swarm_pure",
            diagnostic={"anchor_blend": False, "stop_after": "society_pulse"},
            uses_simulation=True,
            description="現行スワーム、事後アンカーブレンドOFF",
        ),
        "3": DiagnosticCondition(
            id="3",
            label="per_agent_anchor",
            diagnostic={
                "anchor_blend": False,
                "per_agent_anchor": True,
                "anchor_source": f"manifest_train:{preset}",
                "stop_after": "society_pulse",
            },
            uses_simulation=True,
            description="train平均分布からper-agent priorを注入",
        ),
        "3b": DiagnosticCondition(
            id="3b",
            label="random_unrelated_anchor",
            diagnostic={
                "anchor_blend": False,
                "per_agent_anchor": True,
                "anchor_source": "unrelated:security",
                "stop_after": "society_pulse",
            },
            uses_simulation=True,
            description="無関係security train平均をper-agent priorとして注入",
        ),
        "4": DiagnosticCondition(
            id="4",
            label="production_blend",
            diagnostic={"stop_after": "society_pulse"},
            uses_simulation=True,
            description="現行構成の事後アンカーブレンドON",
        ),
    }


def load_eval_cases(preset: str) -> list[dict[str, Any]]:
    split = load_manifest_split(preset)
    survey_data_dir = split.manifest_path.parents[1] / "survey_data"
    cases: list[dict[str, Any]] = []
    for entry in split.eval_surveys:
        file_path = survey_data_dir / str(entry["file"])
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        matched = None
        for survey in data.get("surveys", []):
            if (
                survey.get("theme") == entry.get("theme")
                and survey.get("source") == entry.get("source")
                and survey.get("survey_date") == entry.get("survey_date")
            ):
                matched = survey
                break
        if matched is None:
            raise ValueError(f"Eval survey not found: {entry.get('survey_id')}")
        cases.append({
            **entry,
            "actual_distribution": normalize_stance_distribution(
                matched.get("stance_distribution", {})
            ),
            "question": matched.get("question", ""),
            "source_origin": "same_source_as_train"
            if any(t.get("source") == entry.get("source") for t in split.train_surveys)
            else "cross_source",
        })
    return cases


def bootstrap_ci(
    values: list[float],
    *,
    iterations: int = 1000,
    seed: int = 0,
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    import random

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    lower = means[int(0.025 * (len(means) - 1))]
    upper = means[int(0.975 * (len(means) - 1))]
    return lower, upper


def evaluate_prediction(
    predicted: dict[str, float],
    actual: dict[str, float],
) -> dict[str, float | None]:
    predicted = normalize_stance_distribution(predicted)
    actual = normalize_stance_distribution(actual)
    metrics = evaluate_case(predicted, actual)
    metrics["emd"] = earth_movers_distance(predicted, actual)
    return metrics


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete_rows = [row for row in rows if not row.get("partial")]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in complete_rows:
        groups.setdefault((row["condition_id"], row["survey_id"]), []).append(row)

    cases: list[dict[str, Any]] = []
    for (condition_id, survey_id), items in sorted(groups.items()):
        summary = {
            "condition_id": condition_id,
            "survey_id": survey_id,
            "theme": items[0]["theme"],
            "source_origin": items[0].get("source_origin"),
            "n": len(items),
        }
        for metric in ("jsd", "emd", "brier", "ece"):
            values = [
                float(item[metric])
                for item in items
                if item.get(metric) is not None
            ]
            summary[f"mean_{metric}"] = sum(values) / len(values) if values else None
            if values:
                low, high = bootstrap_ci(values)
                summary[f"{metric}_ci95"] = [low, high]
        cases.append(summary)

    by_condition: dict[str, dict[str, Any]] = {}
    for condition_id in sorted({row["condition_id"] for row in complete_rows}):
        items = [row for row in complete_rows if row["condition_id"] == condition_id]
        by_condition[condition_id] = {"n": len(items)}
        for metric in ("jsd", "emd", "brier", "ece"):
            values = [
                float(item[metric])
                for item in items
                if item.get(metric) is not None
            ]
            by_condition[condition_id][f"mean_{metric}"] = (
                sum(values) / len(values) if values else None
            )
            if values:
                low, high = bootstrap_ci(values)
                by_condition[condition_id][f"{metric}_ci95"] = [low, high]

    return {
        "status": "partial" if any(row.get("partial") for row in rows) else "completed",
        "by_condition": by_condition,
        "cases": cases,
        "partial_failures": [row for row in rows if row.get("partial")],
    }


def build_trial_plan(
    config: DiagnosticConfig,
    conditions: list[DiagnosticCondition],
    cases: list[dict[str, Any]],
) -> list[tuple[DiagnosticCondition, dict[str, Any], int, int]]:
    """plan.md の層別実行ポリシーに沿って trial 一覧を作る。"""
    full_matrix = [
        (seed, run_index)
        for seed in config.seeds
        for run_index in range(config.runs)
    ]
    if not full_matrix:
        return []

    trial_plan: list[tuple[DiagnosticCondition, dict[str, Any], int, int]] = []
    for condition in conditions:
        for case in cases:
            max_trials = len(full_matrix)
            if case.get("source_origin") == "cross_source":
                max_trials = min(config.cross_source_trials, len(full_matrix))
            for seed, run_index in full_matrix[:max_trials]:
                trial_plan.append((condition, case, seed, run_index))
    return trial_plan


def estimate_dry_run(config: DiagnosticConfig) -> dict[str, Any]:
    cases = load_eval_cases(config.preset)
    conditions = condition_definitions(config.preset)
    selected = [conditions[c] for c in config.conditions]
    trial_plan = build_trial_plan(config, selected, cases)
    simulation_runs = sum(
        1
        for condition, _case, _seed, _run in trial_plan
        if condition.uses_simulation
    )
    single_llm_calls = sum(
        1
        for condition, _case, _seed, _run in trial_plan
        if condition.id == "1"
    )
    return {
        "preset": config.preset,
        "conditions": [condition.id for condition in selected],
        "eval_cases": len(cases),
        "trial_count": len(trial_plan),
        "cross_source_trials": config.cross_source_trials,
        "simulation_runs": simulation_runs,
        "single_llm_calls": single_llm_calls,
        "estimated_swarm_llm_calls": simulation_runs * 100,
        "note": "概算: swarm 1 simulation ~= selected agents 100 LLM calls; council/synthesisはstop_afterで回避",
    }


async def _run_simulation_prediction(
    case: dict[str, Any],
    seed: int,
    diagnostic: dict[str, Any],
    dispatcher: Callable[[str], Awaitable[None]],
) -> dict[str, float]:
    sim_id = str(uuid.uuid4())
    async with async_session() as session:
        sim = Simulation(
            id=sim_id,
            mode="quick",
            prompt_text=case["theme"],
            status="queued",
            seed=seed,
            metadata_json={"diagnostic": diagnostic},
        )
        session.add(sim)
        await session.commit()

    await dispatcher(sim_id)

    async with async_session() as session:
        sim = await session.get(Simulation, sim_id)
        metadata = dict(sim.metadata_json or {}) if sim else {}
        pulse = dict(metadata.get("pulse_result") or {})
        aggregation = dict(pulse.get("aggregation") or {})
        distribution = aggregation.get("stance_distribution")
        if distribution:
            return normalize_stance_distribution(distribution)

        result = await session.execute(
            select(SocietyResult)
            .where(SocietyResult.simulation_id == sim_id, SocietyResult.layer == "activation")
            .order_by(SocietyResult.created_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record and record.phase_data:
            aggregation = dict(record.phase_data.get("aggregation") or {})
            distribution = aggregation.get("stance_distribution")
            if distribution:
                return normalize_stance_distribution(distribution)

    raise RuntimeError(f"No stance_distribution produced for simulation {sim_id}")


async def run_single_trial(
    condition: DiagnosticCondition,
    case: dict[str, Any],
    seed: int,
    run_index: int,
    *,
    preset: str,
    dispatcher: Callable[[str], Awaitable[None]] = dispatch_simulation,
    single_llm_fn: Callable[[str, int], Awaitable[dict[str, float]]] = run_single_llm_distribution,
) -> dict[str, Any]:
    if condition.id == "0":
        predicted, anchor_ids = load_manifest_anchor_distribution(preset, split="train")
        validate_no_leakage(anchor_ids, [case["survey_id"]])
    elif condition.id == "1":
        predicted = await single_llm_fn(case["theme"], seed)
    elif condition.uses_simulation:
        diagnostic = dict(condition.diagnostic or {})
        if diagnostic.get("anchor_source") == f"manifest_train:{preset}":
            _anchor, anchor_ids = load_manifest_anchor_distribution(preset, split="train")
            validate_no_leakage(anchor_ids, [case["survey_id"]])
        predicted = await _run_simulation_prediction(case, seed, diagnostic, dispatcher)
    else:
        raise ValueError(f"Unsupported condition: {condition.id}")

    actual = case["actual_distribution"]
    metrics = evaluate_prediction(predicted, actual)
    return {
        "condition_id": condition.id,
        "condition_label": condition.label,
        "survey_id": case["survey_id"],
        "theme": case["theme"],
        "source": case["source"],
        "source_origin": case.get("source_origin"),
        "seed": seed,
        "run_index": run_index,
        "predicted": normalize_stance_distribution(predicted),
        "actual": actual,
        **metrics,
    }


async def run_trial_with_retry(
    condition: DiagnosticCondition,
    case: dict[str, Any],
    seed: int,
    run_index: int,
    *,
    preset: str,
    dispatcher: Callable[[str], Awaitable[None]] = dispatch_simulation,
    single_llm_fn: Callable[[str, int], Awaitable[dict[str, float]]] = run_single_llm_distribution,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            return await run_single_trial(
                condition,
                case,
                seed,
                run_index,
                preset=preset,
                dispatcher=dispatcher,
                single_llm_fn=single_llm_fn,
            )
        except Exception as exc:  # pragma: no cover - exercised through tests with mocks
            last_exc = exc
            logger.warning(
                "diagnostic trial failed condition=%s survey=%s seed=%s run=%s: %s",
                condition.id, case.get("survey_id"), seed, run_index, exc,
            )
    return {
        "partial": True,
        "condition_id": condition.id,
        "condition_label": condition.label,
        "survey_id": case.get("survey_id"),
        "theme": case.get("theme"),
        "seed": seed,
        "run_index": run_index,
        "error": f"{type(last_exc).__name__}: {last_exc}",
    }


async def run_diagnostic(
    config: DiagnosticConfig,
    *,
    dispatcher: Callable[[str], Awaitable[None]] = dispatch_simulation,
    single_llm_fn: Callable[[str, int], Awaitable[dict[str, float]]] = run_single_llm_distribution,
) -> dict[str, Any]:
    if config.dry_run:
        return {"status": "dry_run", "dry_run": estimate_dry_run(config)}

    cases = load_eval_cases(config.preset)
    definitions = condition_definitions(config.preset)
    selected = [definitions[c] for c in config.conditions]
    trial_plan = build_trial_plan(config, selected, cases)

    rows: list[dict[str, Any]] = []
    for condition, case, seed, run_index in trial_plan:
        rows.append(await run_trial_with_retry(
            condition,
            case,
            seed,
            run_index,
            preset=config.preset,
            dispatcher=dispatcher,
            single_llm_fn=single_llm_fn,
        ))

    aggregate = aggregate_results(rows)
    result = {
        "run_id": datetime.now(UTC).strftime("diagnostic_%Y%m%d_%H%M%S"),
        "preset": config.preset,
        "created_at": datetime.now(UTC).isoformat(),
        "seeds": list(config.seeds),
        "runs": config.runs,
        "cross_source_trials": config.cross_source_trials,
        "conditions": {
            condition.id: {
                "label": condition.label,
                "description": condition.description,
                "diagnostic": condition.diagnostic,
            }
            for condition in selected
        },
        "rows": rows,
        "summary": aggregate,
    }
    write_diagnostic_yaml(result, config.output_dir)
    return result


def write_diagnostic_yaml(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_key = datetime.now(UTC).strftime("%Y%m%d")
    path = output_dir / f"diagnostic_{date_key}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False)
    return path


def run_diagnostic_sync(config: DiagnosticConfig) -> dict[str, Any]:
    return asyncio.run(run_diagnostic(config))
