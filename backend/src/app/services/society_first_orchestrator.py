"""Society-first orchestration.

Runs the society simulation first, extracts ranked issues from the resulting
opinion landscape, then deep-dives the top issues through focused swarms.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.app.database import async_session
from src.app.models.evaluation_result import EvaluationResult
from src.app.models.simulation import Simulation
from src.app.models.society_result import SocietyResult
from src.app.models.swarm import Swarm
from src.app.services.society.issue_miner import (
    build_intervention_comparison,
    build_issue_prompt,
    mine_issue_candidates,
    select_top_issues,
)
from src.app.services.society.backtest import (
    build_empty_backtest_result,
    overlay_observed_intervention_comparison,
)
from src.app.services.society.society_orchestrator import (
    _get_or_create_population,
    _save_network,
)
from src.app.services.society.population_generator import get_default_population_size
from src.app.services.society.agent_selector import select_agents
from src.app.services.society.activation_layer import run_activation
from src.app.services.society.evaluation import evaluate_society_simulation
from src.app.services.society.representative_selector import select_representatives
from src.app.services.society.meeting_layer import run_meeting
from src.app.services.society.meeting_report import generate_meeting_report
from src.app.services.society.memory_compressor import update_agent_memories
from src.app.services.society.graph_evolution import evolve_social_graph
from src.app.services.swarm_orchestrator import run_swarm
from src.app.services.verification import (
    ensure_verification_passed,
    verify_society_first_result,
)
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)

DEFAULT_ISSUE_TEMPLATE = "scenario_exploration"
DEFAULT_SELECTED_ISSUES = 3


def _build_society_summary(
    *,
    pop_id: str,
    agents: list[dict[str, Any]],
    selected_agents: list[dict[str, Any]],
    activation_result: dict[str, Any],
    evaluation: dict[str, Any],
    meeting_report: dict[str, Any],
    usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "population_id": pop_id,
        "population_count": len(agents),
        "selected_count": len(selected_agents),
        "aggregation": activation_result.get("aggregation", {}),
        "evaluation": evaluation,
        "meeting": meeting_report,
        "usage": usage,
    }


def _flatten_issue_scenarios(issue_colonies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for colony in issue_colonies:
        for scenario in colony.get("top_scenarios", [])[:2]:
            description = str(scenario.get("description") or "").strip()
            if not description:
                continue
            flattened.append({
                **scenario,
                "description": f"[{colony.get('label', '論点')}] {description}",
            })
    flattened.sort(key=lambda item: float(item.get("scenario_score", 0) or 0), reverse=True)
    return flattened[:6]


def _build_society_first_markdown(
    theme: str,
    *,
    society_summary: dict[str, Any],
    issue_candidates: list[dict[str, Any]],
    selected_issues: list[dict[str, Any]],
    issue_colonies: list[dict[str, Any]],
    intervention_comparison: list[dict[str, Any]],
) -> str:
    aggregation = society_summary.get("aggregation", {})
    lines = [
        "# Society-First Market Lab",
        "",
        f"## テーマ",
        theme or "入力テーマなし",
        "",
        "## 社会反応サマリー",
        f"- 対象人口: {society_summary.get('population_count', 0)}人",
        f"- 選抜対象: {society_summary.get('selected_count', 0)}人",
        f"- 平均信頼度: {(float(aggregation.get('average_confidence', 0) or 0) * 100):.1f}%",
        "",
        "### 主要な立場分布",
    ]

    stance_distribution = aggregation.get("stance_distribution", {}) or {}
    if stance_distribution:
        for stance, ratio in stance_distribution.items():
            lines.append(f"- {stance}: {float(ratio) * 100:.1f}%")
    else:
        lines.append("- 立場分布データなし")

    lines.extend([
        "",
        "## 重要論点ランキング",
    ])
    for issue in issue_candidates[:5]:
        lines.append(
            f"- {issue['label']} "
            f"(score={issue['selection_score']:.2f}, "
            f"share={issue['population_share'] * 100:.0f}%, "
            f"controversy={issue['controversy_score']:.2f})"
        )

    lines.extend([
        "",
        "## 選抜した Issue Colony",
    ])
    for issue in selected_issues:
        lines.append(
            f"- {issue['label']}: 市場影響 {issue['market_impact_score']:.2f} / "
            f"波及性 {issue['network_spread_score']:.2f}"
        )

    lines.extend([
        "",
        "## Issue Colony 深掘り",
    ])
    for colony in issue_colonies:
        lines.append(f"### {colony.get('label', '論点')}")
        lines.append(colony.get("integrated_report") or "統合レポートなし")
        top_scenarios = colony.get("top_scenarios", []) or []
        if top_scenarios:
            lines.append("")
            lines.append("主なシナリオ:")
            for scenario in top_scenarios[:2]:
                lines.append(
                    f"- {scenario.get('description', '')} "
                    f"({float(scenario.get('scenario_score', 0) or 0) * 100:.0f}%)"
                )
        lines.append("")

    lines.extend([
        "## 介入比較",
    ])
    if intervention_comparison:
        for intervention in intervention_comparison:
            lines.append(
                f"- {intervention['label']} ({intervention['expected_effect']}): "
                f"{intervention['change_summary']} / 対象: {', '.join(intervention['affected_issues'])}"
            )
    else:
        lines.append("- 介入比較は未生成")

    lines.extend([
        "",
        "## 次の検証",
        "- 上位論点ごとの一次情報を追加取得する",
        "- 価格・規制・訴求変更のうち、最も効果の高い介入から検証する",
        "- issue colony の上位シナリオを実データで追跡する",
    ])
    return "\n".join(lines).strip()


async def _run_issue_colonies(
    *,
    session,
    sim: Simulation,
    simulation_id: str,
    theme: str,
    society_summary: dict[str, Any],
    selected_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    template_name = sim.template_name or DEFAULT_ISSUE_TEMPLATE

    await sse_manager.publish(simulation_id, "colonies_created", {
        "colonies": [
            {
                "colony_id": issue["issue_id"],
                "perspective": issue["label"],
                "temperature": 0.0,
                "adversarial": True,
            }
            for issue in selected_issues
        ],
    })

    for index, issue in enumerate(selected_issues, start=1):
        issue_prompt = build_issue_prompt(
            theme=theme,
            issue=issue,
            society_summary=society_summary.get("aggregation", {}),
        )
        swarm = Swarm(
            id=str(uuid.uuid4()),
            project_id=sim.project_id,
            template_name=template_name,
            execution_profile=sim.execution_profile,
            status="queued",
            metadata_json={
                "society_first_simulation_id": simulation_id,
                "issue_id": issue["issue_id"],
                "issue_label": issue["label"],
            },
        )
        session.add(swarm)
        await session.commit()

        await sse_manager.publish(simulation_id, "colony_started", {
            "colony_id": issue["issue_id"],
            "perspective": f"Issue {index}: {issue['label']}",
        })

        swarm_result = await run_swarm(
            swarm.id,
            prompt_text=issue_prompt,
            additional_context=(
                f"社会全体の論点: {issue['label']}\n"
                f"立場分布: {issue.get('supporting_stances', [])}\n"
                f"代表理由: {issue.get('sample_reasons', [])}"
            ),
            return_result=True,
        ) or {}

        aggregation = swarm_result.get("aggregation", {})
        await sse_manager.publish(simulation_id, "colony_completed", {
            "colony_id": issue["issue_id"],
            "event_count": len(aggregation.get("scenarios", []) or []),
        })
        results.append({
            "issue_id": issue["issue_id"],
            "label": issue["label"],
            "description": issue.get("description", ""),
            "swarm_id": swarm.id,
            "integrated_report": swarm_result.get("integrated_report", ""),
            "top_scenarios": aggregation.get("scenarios", [])[:3],
            "diversity_score": aggregation.get("diversity_score", 0),
            "entropy": aggregation.get("entropy", 0),
            "colony_count": len(swarm_result.get("colony_results", []) or []),
        })
    return results


async def run_society_first(simulation_id: str) -> None:
    logger.info("Starting society-first simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            await sse_manager.publish(simulation_id, "society_started", {
                "simulation_id": simulation_id,
                "theme": theme[:100],
            })

            pop_count = get_default_population_size()
            await sse_manager.publish(simulation_id, "population_status", {
                "status": "generating",
                "target_count": pop_count,
            })

            pop_id, agents = await _get_or_create_population(session, sim.population_id, pop_count)
            sim.population_id = pop_id
            await session.commit()

            await sse_manager.publish(simulation_id, "population_status", {
                "status": "ready",
                "agent_count": len(agents),
                "population_id": pop_id,
            })

            await _save_network(session, agents, pop_id)

            selected_agents = await select_agents(agents, theme, target_count=100)
            await sse_manager.publish(simulation_id, "society_selection_completed", {
                "selected_count": len(selected_agents),
                "total_population": len(agents),
            })

            await sse_manager.publish(simulation_id, "society_activation_started", {
                "agent_count": len(selected_agents),
            })

            async def on_progress(completed: int, total: int):
                await sse_manager.publish(simulation_id, "society_activation_progress", {
                    "completed": completed,
                    "total": total,
                    "percent": round(completed / total * 100, 1),
                })

            activation_result = await run_activation(selected_agents, theme, on_progress=on_progress)
            for key in total_usage:
                total_usage[key] += activation_result["usage"].get(key, 0)

            activation_record = SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="activation",
                phase_data={
                    "aggregation": activation_result["aggregation"],
                    "representative_count": len(activation_result["representatives"]),
                },
                usage=activation_result["usage"],
            )
            session.add(activation_record)
            await session.commit()

            await sse_manager.publish(simulation_id, "society_activation_completed", {
                "aggregation": activation_result["aggregation"],
                "representative_count": len(activation_result["representatives"]),
                "usage": activation_result["usage"],
            })

            eval_metrics = await evaluate_society_simulation(selected_agents, activation_result["responses"])
            eval_data = {m["metric_name"]: m["score"] for m in eval_metrics}
            for metric in eval_metrics:
                session.add(EvaluationResult(
                    id=str(uuid.uuid4()),
                    simulation_id=simulation_id,
                    metric_name=metric["metric_name"],
                    score=metric["score"],
                    details=metric["details"],
                    baseline_type=metric.get("baseline_type"),
                    baseline_score=metric.get("baseline_score"),
                ))
            session.add(SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="evaluation",
                phase_data={"metrics": eval_data},
                usage={},
            ))
            await session.commit()

            await sse_manager.publish(simulation_id, "society_evaluation_completed", {
                "metrics": eval_data,
            })

            meeting_participants = select_representatives(
                selected_agents,
                activation_result["responses"],
                max_citizen_reps=6,
                max_experts=4,
            )
            meeting_result = await run_meeting(
                meeting_participants,
                theme,
                simulation_id=simulation_id,
                num_rounds=3,
            )
            for key in total_usage:
                total_usage[key] += meeting_result["usage"].get(key, 0)

            meeting_report = generate_meeting_report(meeting_result)
            session.add(SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="meeting",
                phase_data={"report": meeting_report, "participant_count": len(meeting_participants)},
                usage=meeting_result["usage"],
            ))
            await session.commit()

            await update_agent_memories(
                session,
                selected_agents,
                activation_result["responses"],
                meeting_result=meeting_result,
            )
            await evolve_social_graph(session, pop_id, meeting_result, meeting_participants)

            await sse_manager.publish(simulation_id, "phase_changed", {
                "phase": "issue_mining",
            })

            issue_candidates = mine_issue_candidates(
                selected_agents,
                activation_result["responses"],
                meeting_report=meeting_report,
            )
            selected_issues = select_top_issues(issue_candidates, limit=DEFAULT_SELECTED_ISSUES)

            session.add(SocietyResult(
                id=str(uuid.uuid4()),
                simulation_id=simulation_id,
                population_id=pop_id,
                layer="issue_mining",
                phase_data={
                    "issue_candidates": issue_candidates,
                    "selected_issues": selected_issues,
                },
                usage={},
            ))
            await session.commit()

            society_summary = _build_society_summary(
                pop_id=pop_id,
                agents=agents,
                selected_agents=selected_agents,
                activation_result=activation_result,
                evaluation=eval_data,
                meeting_report=meeting_report,
                usage=total_usage,
            )

            await sse_manager.publish(simulation_id, "phase_changed", {
                "phase": "colony_execution",
            })

            issue_colonies = await _run_issue_colonies(
                session=session,
                sim=sim,
                simulation_id=simulation_id,
                theme=theme,
                society_summary=society_summary,
                selected_issues=selected_issues,
            )
            backtest = build_empty_backtest_result()
            intervention_comparison = overlay_observed_intervention_comparison(
                build_intervention_comparison(selected_issues, issue_colonies),
                backtest,
            )

            report_sections = [
                "社会反応サマリー",
                "重要論点ランキング",
                "Issue Colony 深掘り",
                "介入比較",
                "次の検証",
            ]
            await sse_manager.publish(simulation_id, "report_started", {
                "sections": report_sections,
            })
            for section_name in report_sections:
                await sse_manager.publish(simulation_id, "report_section_done", {
                    "section": section_name,
                })

            content = _build_society_first_markdown(
                theme,
                society_summary=society_summary,
                issue_candidates=issue_candidates,
                selected_issues=selected_issues,
                issue_colonies=issue_colonies,
                intervention_comparison=intervention_comparison,
            )

            final_payload = {
                "type": "society_first",
                "society_summary": society_summary,
                "issue_candidates": issue_candidates,
                "selected_issues": selected_issues,
                "issue_colonies": issue_colonies,
                "intervention_comparison": intervention_comparison,
                "backtest": backtest,
                "scenarios": _flatten_issue_scenarios(issue_colonies),
                "content": content,
                "sections": {
                    "society_summary": society_summary,
                    "issue_candidates": issue_candidates,
                    "selected_issues": selected_issues,
                    "intervention_comparison": intervention_comparison,
                    "backtest": backtest,
                },
            }
            await sse_manager.publish(simulation_id, "report_completed", {
                "report_length": len(content),
            })
            verification = verify_society_first_result(final_payload)
            ensure_verification_passed(verification, context="society_first")
            final_payload["verification"] = verification

            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            sim.metadata_json = {
                **dict(sim.metadata_json or {}),
                "society_result": society_summary,
                "society_first_result": final_payload,
            }
            await session.commit()

            await sse_manager.publish(simulation_id, "society_completed", {
                "simulation_id": simulation_id,
                "aggregation": activation_result["aggregation"],
                "evaluation": eval_data,
                "meeting_available": True,
                "issue_count": len(issue_candidates),
                "deep_dive_count": len(issue_colonies),
                "usage": total_usage,
            })
            logger.info("Society-first simulation %s completed", simulation_id)

        except Exception as exc:
            logger.error("Society-first simulation %s failed: %s", simulation_id, exc, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(exc).__name__}: {exc}"[:500]
            await session.commit()
            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(exc),
            })
