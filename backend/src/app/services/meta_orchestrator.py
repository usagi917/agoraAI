"""Meta simulation orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.app.database import async_session
from src.app.models.document import Document
from src.app.models.run import Run
from src.app.models.simulation import Simulation
from src.app.models.swarm import Swarm
from src.app.models.template import Template
from src.app.services.meta_intervention_planner import plan_interventions, select_intervention
from src.app.services.meta_score import (
    MAX_META_CYCLES,
    TARGET_OBJECTIVE_SCORE,
    compute_objective_score,
    evaluate_stop_condition,
)
from src.app.services.pm_board_orchestrator import run_pm_board
from src.app.services.quality import get_evidence_mode
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.issue_miner import (
    build_issue_prompt,
    mine_issue_candidates,
    select_top_issues,
)
from src.app.services.society.meeting_layer import run_meeting
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.population_generator import get_default_population_size
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.society_orchestrator import _get_or_create_population, _save_network
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation
from src.app.services.swarm_orchestrator import run_swarm
from src.app.services.world_builder import build_world
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

MAX_SELECTED_ISSUES = 3
MAX_SCENARIOS_PER_CYCLE = 6


def _build_world_context(prompt_text: str, world_state: dict[str, Any]) -> str:
    summary = str(world_state.get("world_summary") or "").strip()
    if not summary:
        return prompt_text
    return (
        f"{prompt_text}\n\n"
        "--- 初期世界モデル ---\n"
        f"{summary}"
    ).strip()


def _build_cycle_prompt(
    prompt_text: str,
    world_summary: str,
    selected_intervention: dict[str, Any] | None,
    cycle_index: int,
) -> str:
    parts = [prompt_text.strip()]
    if world_summary.strip():
        parts.append(f"世界モデル要約:\n{world_summary.strip()}")
    parts.append(f"現在サイクル: {cycle_index}")
    if selected_intervention:
        parts.append(
            "適用中の介入:\n"
            f"- {selected_intervention.get('label', '')}\n"
            f"- 仮説: {selected_intervention.get('hypothesis', '')}\n"
            f"- 対象: {', '.join(selected_intervention.get('target_issues') or [])}"
        )
    return "\n\n".join(part for part in parts if part)


def _flatten_issue_scenarios(issue_colonies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for colony in issue_colonies:
        for scenario in list(colony.get("top_scenarios") or [])[:2]:
            description = str(scenario.get("description") or "").strip()
            if not description:
                continue
            flattened.append({
                **scenario,
                "description": f"[{colony.get('label', '論点')}] {description}",
            })
    flattened.sort(
        key=lambda item: float(item.get("scenario_score", item.get("probability", 0.0)) or 0.0),
        reverse=True,
    )
    return flattened[:MAX_SCENARIOS_PER_CYCLE]


def _build_meta_markdown(
    *,
    prompt_text: str,
    baseline: dict[str, Any],
    cycles: list[dict[str, Any]],
    final_state: dict[str, Any],
) -> str:
    lines = [
        "# Meta Simulation",
        "",
        "## テーマ",
        prompt_text or "入力テーマなし",
        "",
        "## 初期世界モデル",
        str(baseline.get("world_summary") or "要約なし"),
        "",
        "## 収束結果",
        f"- 停止理由: {final_state.get('stop_reason', 'unknown')}",
        f"- 最良サイクル: {final_state.get('best_cycle_index', 0)}",
        f"- 最良スコア: {(float(final_state.get('best_objective_score', 0.0)) * 100):.1f}%",
    ]

    selected_intervention = dict(final_state.get("selected_intervention") or {})
    if selected_intervention:
        lines.extend([
            f"- 採択介入: {selected_intervention.get('label', '')}",
            f"- 介入仮説: {selected_intervention.get('hypothesis', '')}",
        ])

    lines.extend(["", "## サイクル履歴"])
    for cycle in cycles:
        lines.append(
            f"- Cycle {cycle['cycle_index']}: "
            f"objective={(float(cycle.get('objective_score', 0.0)) * 100):.1f}% / "
            f"society={(float((cycle.get('score_breakdown') or {}).get('society_score', 0.0)) * 100):.1f}% / "
            f"swarm={(float((cycle.get('score_breakdown') or {}).get('swarm_score', 0.0)) * 100):.1f}% / "
            f"pm={(float((cycle.get('score_breakdown') or {}).get('pm_score', 0.0)) * 100):.1f}%"
        )
        if cycle.get("selected_intervention"):
            lines.append(f"  介入: {cycle['selected_intervention'].get('label', '')}")

    best_cycle = next(
        (cycle for cycle in cycles if cycle.get("cycle_index") == final_state.get("best_cycle_index")),
        None,
    )
    if best_cycle:
        lines.extend(["", "## 最良サイクルの主要シナリオ"])
        for scenario in list(best_cycle.get("scenarios") or [])[:3]:
            lines.append(
                f"- {scenario.get('description', '')} "
                f"({float(scenario.get('scenario_score', scenario.get('probability', 0.0)) or 0.0) * 100:.0f}%)"
            )

    return "\n".join(lines).strip()


async def _fetch_document_text(session, project_id: str | None) -> str:
    if not project_id:
        return ""
    result = await session.execute(
        select(Document).where(Document.project_id == project_id)
    )
    documents = result.scalars().all()
    return "\n\n---\n\n".join(d.text_content for d in documents)


async def _build_initial_world(
    session,
    sim: Simulation,
    document_text: str,
    prompt_text: str,
) -> tuple[str, dict[str, Any]]:
    template_result = await session.execute(
        select(Template).where(Template.name == sim.template_name)
    )
    template = template_result.scalar_one_or_none()
    template_prompts = template.prompts if template else {}

    world_run_id = str(uuid.uuid4())
    world_run = Run(
        id=world_run_id,
        project_id=sim.project_id,
        template_name=sim.template_name,
        execution_profile=sim.execution_profile,
        status="running",
        total_rounds=1,
        started_at=datetime.now(timezone.utc),
        metadata_json={"meta_simulation": True},
    )
    session.add(world_run)
    await session.commit()

    world_state = await build_world(
        session,
        world_run_id,
        document_text,
        template_prompts.get("world_build", ""),
        prompt_text=prompt_text,
    )
    world_run.status = "completed"
    world_run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return world_run_id, world_state


async def _run_issue_colonies(
    *,
    session,
    sim: Simulation,
    simulation_id: str,
    cycle_index: int,
    theme: str,
    society_summary: dict[str, Any],
    selected_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for index, issue in enumerate(selected_issues, start=1):
        issue_prompt = build_issue_prompt(
            theme=theme,
            issue=issue,
            society_summary=society_summary.get("aggregation", {}),
        )
        swarm = Swarm(
            id=str(uuid.uuid4()),
            project_id=sim.project_id,
            template_name=sim.template_name or "scenario_exploration",
            execution_profile=sim.execution_profile,
            status="queued",
            metadata_json={
                "meta_simulation": True,
                "parent_simulation_id": simulation_id,
                "cycle_index": cycle_index,
                "issue_id": issue.get("issue_id"),
                "issue_label": issue.get("label"),
            },
        )
        session.add(swarm)
        await session.commit()

        await sse_manager.publish(simulation_id, "meta_phase_changed", {
            "cycle_index": cycle_index,
            "phase": "issue_swarm",
            "issue_label": issue.get("label"),
            "issue_index": index,
            "issue_total": len(selected_issues),
        })

        swarm_result = await run_swarm(
            swarm.id,
            prompt_text=issue_prompt,
            additional_context=(
                f"社会全体の論点: {issue.get('label', '')}\n"
                f"立場分布: {issue.get('supporting_stances', [])}\n"
                f"代表理由: {issue.get('sample_reasons', [])}"
            ),
            return_result=True,
        ) or {}

        aggregation = dict(swarm_result.get("aggregation") or {})
        results.append({
            "issue_id": issue.get("issue_id"),
            "label": issue.get("label"),
            "description": issue.get("description", ""),
            "swarm_id": swarm.id,
            "integrated_report": swarm_result.get("integrated_report", ""),
            "top_scenarios": list(aggregation.get("scenarios") or [])[:3],
            "diversity_score": aggregation.get("diversity_score", 0),
            "entropy": aggregation.get("entropy", 0),
            "colony_count": len(swarm_result.get("colony_results", []) or []),
        })

        await sse_manager.publish(simulation_id, "meta_issue_swarm_completed", {
            "cycle_index": cycle_index,
            "issue_label": issue.get("label"),
            "swarm_id": swarm.id,
            "scenario_count": len(aggregation.get("scenarios", []) or []),
        })

    return results


def _build_cycle_pm_prompt(
    cycle_prompt: str,
    cycle_index: int,
    society_summary: dict[str, Any],
    selected_issues: list[dict[str, Any]],
    issue_colonies: list[dict[str, Any]],
    selected_intervention: dict[str, Any] | None,
) -> str:
    issue_lines = [f"- {issue.get('label', '')}: {issue.get('description', '')}" for issue in selected_issues]
    scenario_lines = []
    for colony in issue_colonies:
        for scenario in list(colony.get("top_scenarios") or [])[:2]:
            scenario_lines.append(
                f"- [{colony.get('label', '')}] {scenario.get('description', '')} "
                f"({float(scenario.get('scenario_score', scenario.get('probability', 0.0)) or 0.0) * 100:.0f}%)"
            )

    parts = [
        cycle_prompt,
        f"Cycle {cycle_index} の社会反応サマリー: {society_summary.get('aggregation', {})}",
        "重要論点:\n" + ("\n".join(issue_lines) if issue_lines else "- なし"),
        "主要シナリオ:\n" + ("\n".join(scenario_lines) if scenario_lines else "- なし"),
    ]
    if selected_intervention:
        parts.append(
            "現在適用している介入:\n"
            f"- {selected_intervention.get('label', '')}\n"
            f"- 仮説: {selected_intervention.get('hypothesis', '')}"
        )
    return "\n\n".join(parts)


def _build_cycle_summary(
    *,
    population_id: str,
    population_count: int,
    selected_count: int,
    activation_result: dict[str, Any],
    evaluation: dict[str, Any],
    meeting_report: dict[str, Any],
    issue_candidates: list[dict[str, Any]],
    selected_issues: list[dict[str, Any]],
    issue_colonies: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    pm_result: dict[str, Any],
    interventions: list[dict[str, Any]],
    selected_intervention: dict[str, Any] | None,
    score_breakdown: dict[str, float],
    stop_evaluation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "population_id": population_id,
        "population_count": population_count,
        "selected_count": selected_count,
        "aggregation": activation_result.get("aggregation", {}),
        "evaluation": evaluation,
        "meeting": meeting_report,
        "issue_candidates": issue_candidates[:5],
        "selected_issues": selected_issues,
        "issue_colonies": issue_colonies,
        "scenarios": scenarios,
        "pm_board": pm_result,
        "interventions": interventions,
        "selected_intervention": selected_intervention,
        "score_breakdown": score_breakdown,
        "objective_score": score_breakdown.get("objective_score", 0.0),
        "stop_evaluation": stop_evaluation,
    }


async def run_meta_simulation(simulation_id: str) -> None:
    logger.info("Starting meta simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        try:
            sim.status = "running"
            sim.started_at = datetime.now(timezone.utc)
            await session.commit()

            document_text = await _fetch_document_text(session, sim.project_id)
            prompt_text = str(sim.prompt_text or "").strip()
            if not prompt_text and sim.project_id:
                from src.app.models.project import Project

                project = await session.get(Project, sim.project_id)
                if project and project.prompt_text:
                    prompt_text = project.prompt_text.strip()

            if not prompt_text and not document_text.strip():
                raise ValueError("入力文書またはプロンプトが必要です")

            await sse_manager.publish(simulation_id, "meta_started", {
                "simulation_id": simulation_id,
                "target_score": TARGET_OBJECTIVE_SCORE,
                "max_cycles": MAX_META_CYCLES,
            })

            await sse_manager.publish(simulation_id, "meta_phase_changed", {
                "cycle_index": 0,
                "phase": "world_building",
            })
            baseline_run_id, world_state = await _build_initial_world(session, sim, document_text, prompt_text)
            world_summary = str(world_state.get("world_summary") or "").strip()

            pop_count = get_default_population_size()
            pop_id, agents = await _get_or_create_population(session, sim.population_id, pop_count)
            sim.population_id = pop_id
            await session.commit()

            await _save_network(session, agents, pop_id)
            cycle_seed_prompt = _build_world_context(prompt_text, world_state)
            selected_agents = await select_agents(agents, cycle_seed_prompt, target_count=100)

            cycles: list[dict[str, Any]] = []
            current_intervention: dict[str, Any] | None = None
            best_cycle: dict[str, Any] | None = None

            for cycle_index in range(1, MAX_META_CYCLES + 1):
                cycle_prompt = _build_cycle_prompt(prompt_text, world_summary, current_intervention, cycle_index)
                await sse_manager.publish(simulation_id, "meta_cycle_started", {
                    "cycle_index": cycle_index,
                    "target_score": TARGET_OBJECTIVE_SCORE,
                    "selected_intervention": current_intervention,
                })

                await sse_manager.publish(simulation_id, "meta_phase_changed", {
                    "cycle_index": cycle_index,
                    "phase": "society",
                })

                async def on_progress(completed: int, total: int) -> None:
                    await sse_manager.publish(simulation_id, "meta_activation_progress", {
                        "cycle_index": cycle_index,
                        "completed": completed,
                        "total": total,
                    })

                activation_result = await run_activation(
                    selected_agents,
                    cycle_prompt,
                    on_progress=on_progress,
                )
                eval_metrics = await evaluate_society_simulation(
                    selected_agents,
                    activation_result["responses"],
                )
                eval_data = {metric["metric_name"]: metric["score"] for metric in eval_metrics}

                meeting_participants = select_representatives(
                    selected_agents,
                    activation_result["responses"],
                    max_citizen_reps=6,
                    max_experts=4,
                )
                meeting_result = await run_meeting(
                    meeting_participants,
                    cycle_prompt,
                    simulation_id=simulation_id,
                    num_rounds=3,
                )
                meeting_report = generate_meeting_report(meeting_result)

                society_summary = {
                    "population_id": pop_id,
                    "population_count": len(agents),
                    "selected_count": len(selected_agents),
                    "aggregation": activation_result.get("aggregation", {}),
                    "evaluation": eval_data,
                    "meeting": meeting_report,
                    "usage": activation_result.get("usage", {}),
                }

                await sse_manager.publish(simulation_id, "meta_phase_changed", {
                    "cycle_index": cycle_index,
                    "phase": "issue_mining",
                })
                issue_candidates = mine_issue_candidates(
                    selected_agents,
                    activation_result["responses"],
                    meeting_report=meeting_report,
                )
                selected_issues = select_top_issues(issue_candidates, limit=MAX_SELECTED_ISSUES)

                issue_colonies = await _run_issue_colonies(
                    session=session,
                    sim=sim,
                    simulation_id=simulation_id,
                    cycle_index=cycle_index,
                    theme=cycle_prompt,
                    society_summary=society_summary,
                    selected_issues=selected_issues,
                )
                scenarios = _flatten_issue_scenarios(issue_colonies)

                await sse_manager.publish(simulation_id, "meta_phase_changed", {
                    "cycle_index": cycle_index,
                    "phase": "pm_board",
                })
                pm_prompt = _build_cycle_pm_prompt(
                    cycle_prompt,
                    cycle_index,
                    society_summary,
                    selected_issues,
                    issue_colonies,
                    current_intervention,
                )
                pm_result = await run_pm_board(
                    session=session,
                    simulation_id=simulation_id,
                    prompt_text=pm_prompt,
                    document_text=document_text,
                    scenario_candidates=scenarios,
                    project_id=sim.project_id,
                    evidence_mode=get_evidence_mode(sim.metadata_json),
                )

                interventions = plan_interventions(pm_result, selected_issues, issue_colonies)
                selected_intervention = select_intervention(interventions)
                await sse_manager.publish(simulation_id, "meta_interventions_generated", {
                    "cycle_index": cycle_index,
                    "count": len(interventions),
                    "selected_intervention": selected_intervention,
                })

                score_breakdown = compute_objective_score(
                    society_summary,
                    issue_colonies,
                    selected_issues,
                    pm_result,
                )
                stop_evaluation = evaluate_stop_condition(
                    [float(item.get("objective_score", 0.0)) for item in cycles]
                    + [score_breakdown["objective_score"]],
                )

                cycle_summary = _build_cycle_summary(
                    population_id=pop_id,
                    population_count=len(agents),
                    selected_count=len(selected_agents),
                    activation_result=activation_result,
                    evaluation=eval_data,
                    meeting_report=meeting_report,
                    issue_candidates=issue_candidates,
                    selected_issues=selected_issues,
                    issue_colonies=issue_colonies,
                    scenarios=scenarios,
                    pm_result=pm_result,
                    interventions=interventions,
                    selected_intervention=selected_intervention,
                    score_breakdown=score_breakdown,
                    stop_evaluation=stop_evaluation,
                )
                cycle_summary["cycle_index"] = cycle_index
                cycles.append(cycle_summary)

                if not best_cycle or score_breakdown["objective_score"] > float(best_cycle.get("objective_score", 0.0)):
                    best_cycle = cycle_summary

                sim.metadata_json = {
                    **dict(sim.metadata_json or {}),
                    "meta_state": {
                        "current_cycle": cycle_index,
                        "best_cycle_index": best_cycle.get("cycle_index") if best_cycle else cycle_index,
                        "best_score": best_cycle.get("objective_score", 0.0) if best_cycle else score_breakdown["objective_score"],
                        "target_score": TARGET_OBJECTIVE_SCORE,
                        "stop_reason": stop_evaluation["reason"],
                        "selected_intervention": selected_intervention,
                    },
                }
                await session.commit()

                await sse_manager.publish(simulation_id, "meta_score_updated", {
                    "cycle_index": cycle_index,
                    **score_breakdown,
                    "stop_evaluation": stop_evaluation,
                })
                await sse_manager.publish(simulation_id, "meta_cycle_completed", {
                    "cycle_index": cycle_index,
                    "objective_score": score_breakdown["objective_score"],
                    "stop_reason": stop_evaluation["reason"],
                })

                current_intervention = selected_intervention
                if stop_evaluation["should_stop"]:
                    break

            if not best_cycle:
                raise ValueError("meta simulation produced no cycles")

            final_state = {
                "best_cycle_index": best_cycle.get("cycle_index"),
                "best_objective_score": best_cycle.get("objective_score", 0.0),
                "stop_reason": best_cycle.get("stop_evaluation", {}).get("reason", "unknown"),
                "selected_intervention": best_cycle.get("selected_intervention"),
                "target_score": TARGET_OBJECTIVE_SCORE,
                "cycle_count": len(cycles),
                "score_breakdown": best_cycle.get("score_breakdown", {}),
            }
            content = _build_meta_markdown(
                prompt_text=prompt_text,
                baseline={
                    "world_run_id": baseline_run_id,
                    "world_summary": world_summary,
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                },
                cycles=cycles,
                final_state=final_state,
            )

            meta_report = {
                "type": "meta_simulation",
                "content": content,
                "summary_markdown": content,
                "baseline": {
                    "world_run_id": baseline_run_id,
                    "world_summary": world_summary,
                    "entity_count": len(world_state.get("entities", [])),
                    "relation_count": len(world_state.get("relations", [])),
                    "population_id": pop_id,
                },
                "cycles": cycles,
                "final_state": final_state,
                "intervention_history": [
                    cycle["selected_intervention"]
                    for cycle in cycles
                    if cycle.get("selected_intervention")
                ],
                "scenarios": best_cycle.get("scenarios", []),
                "pm_board": best_cycle.get("pm_board"),
                "society_summary": {
                    "population_id": best_cycle.get("population_id"),
                    "population_count": best_cycle.get("population_count"),
                    "selected_count": best_cycle.get("selected_count"),
                    "aggregation": best_cycle.get("aggregation", {}),
                    "evaluation": best_cycle.get("evaluation", {}),
                    "meeting": best_cycle.get("meeting", {}),
                },
            }

            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "meta_state": {
                    "current_cycle": len(cycles),
                    "best_cycle_index": final_state["best_cycle_index"],
                    "best_score": final_state["best_objective_score"],
                    "target_score": TARGET_OBJECTIVE_SCORE,
                    "stop_reason": final_state["stop_reason"],
                    "selected_intervention": final_state["selected_intervention"],
                },
                "meta_simulation_result": meta_report,
            }
            await session.commit()

            await sse_manager.publish(simulation_id, "meta_converged", {
                "simulation_id": simulation_id,
                "best_cycle_index": final_state["best_cycle_index"],
                "best_score": final_state["best_objective_score"],
                "stop_reason": final_state["stop_reason"],
            })
            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "meta_simulation",
            })
        except Exception as e:
            logger.error("Meta simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim = await session.get(Simulation, simulation_id)
            if sim:
                sim.status = "failed"
                sim.error_message = f"{type(e).__name__}: {e}"[:500]
                await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
