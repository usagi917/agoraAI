"""run_society の永続化 characterization(golden)テスト。

run_society は12フェーズを通して SocietyResult レコードを layer 別に永続化する。
P5 でこの巨大関数を _phase_xxx へ分割する際、永続化されるレイヤ集合や
最終ステータスが変わっていないことを保証する安全網。
ハーネスは test_society_orchestrator.py の既存 end-to-end テストの構成を流用する。

2系統の経路を固定する:
- エッジ無し: Network Propagation フェーズが edge クエリで例外→握り潰し（伝播なし）
- エッジ有り: Network Propagation が happy path を通り network_propagation レイヤを追加
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeResult:
    """`.scalar()`(件数) と `.scalars().all()`(行) の両インターフェースに応答する。"""

    def __init__(self, rows):
        self._rows = rows

    def scalar(self):
        return len(self._rows)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeSession:
    def __init__(self, persisted_layers, *, edges=None):
        self._persisted_layers = persisted_layers
        self._edges = edges
        self.simulation = SimpleNamespace(
            id="sim-1",
            prompt_text="日本の経済政策について",
            population_id=None,
            status="running",
            completed_at=None,
            metadata_json={},
            error_message=None,
            seed=42,
            scenario_pair_id=None,
        )

    async def get(self, model, obj_id):
        return self.simulation

    def add(self, obj):
        if obj.__class__.__name__ == "SocietyResult":
            self._persisted_layers.append(obj.layer)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def execute(self, stmt):
        # エッジ有り経路では SocialEdge 行を返す。エッジ無し経路では旧来通り
        # scalar(件数)のみ応答し、伝播フェーズは .scalars() 不在で例外→握り潰しとなる
        # （現行挙動の保持）。
        if self._edges is not None:
            return _FakeResult(self._edges)
        return SimpleNamespace(scalar=lambda: 5)


def _install_common_mocks(monkeypatch, orchestrator, fake_session, published_events):
    """両ケース共通の monkeypatch をまとめて適用する。"""

    async def fake_get_or_create_population(session, population_id, count=None, seed=None, *, strict=False):
        return "pop-1", [
            {"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}}
        ]

    async def fake_publish(simulation_id, event, data):
        published_events.append(event)

    async def fake_select_agents(agents, theme, target_count=100, edges=None):
        return agents

    async def fake_run_activation(selected_agents, theme, on_progress=None):
        if on_progress is not None:
            await on_progress(1, 1)
        return {
            "aggregation": {"stance_distribution": {"賛成": 1}, "total_respondents": 1},
            "representatives": [{"id": "a1"}],
            "responses": [{"stance": "賛成", "confidence": 0.8, "reason": "test"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def fake_evaluate_society_simulation(selected_agents, responses):
        return [{"metric_name": "diversity", "score": 0.5, "details": {}}]

    async def fake_run_meeting(participants, theme, simulation_id=None, num_rounds=3):
        return {
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "rounds": [[{
                "participant_index": 0,
                "participant_name": "会社員・35歳",
                "role": "citizen_representative",
                "expertise": "",
                "round": 1,
                "position": "賛成",
                "argument": "経済成長のため",
                "evidence": "GDP成長率",
                "concerns": [],
                "questions_to_others": [],
            }]],
            "participants": [{"role": "citizen_representative", "display_name": "会社員・35歳", "stance": "賛成"}],
            "synthesis": {"consensus_points": ["経済成長は重要"], "key_insights": []},
        }

    monkeypatch.setattr(orchestrator, "async_session", lambda: _FakeSessionContext(fake_session))
    monkeypatch.setattr(orchestrator, "get_default_population_size", lambda: 5)
    monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
    monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
    monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
    monkeypatch.setattr(orchestrator, "_load_population_edges", AsyncMock(return_value=[]))
    monkeypatch.setattr(orchestrator, "select_agents", fake_select_agents)
    monkeypatch.setattr(orchestrator, "run_activation", fake_run_activation)
    monkeypatch.setattr(orchestrator, "evaluate_society_simulation", fake_evaluate_society_simulation)
    monkeypatch.setattr(orchestrator, "select_representatives", lambda *args, **kwargs: [
        {
            "role": "citizen_representative",
            "agent_profile": {"id": "a1", "agent_index": 0, "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}},
            "display_name": "会社員・35歳",
            "stance": "賛成",
            "expertise": "",
        }
    ])
    monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
    monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
    monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
    monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())


@pytest.mark.asyncio
async def test_run_society_persists_expected_layers(monkeypatch: pytest.MonkeyPatch):
    from src.app.services.society import society_orchestrator as orchestrator

    persisted_layers: list[str] = []
    published_events: list[str] = []
    fake_session = _FakeSession(persisted_layers)  # edges=None → 伝播スキップ
    _install_common_mocks(monkeypatch, orchestrator, fake_session, published_events)

    await orchestrator.run_society("sim-1")

    # 永続化されるレイヤ集合(エッジ無し=伝播フェーズ無しの代表ケース)を golden として固定。
    # P5 のフェーズ抽出でレイヤの欠落/改名が起きたら即検知する。
    assert set(persisted_layers) == {
        "activation",
        "deliberation_quality",
        "demographic_analysis",
        "evaluation",
        "meeting",
        "narrative",
    }, f"永続化レイヤ集合が変化した: {sorted(set(persisted_layers))}"

    # パイプライン完走の契約: 最終ステータスと主要 SSE イベント。
    assert fake_session.simulation.status == "completed"
    for required_event in ("society_started", "society_activation_completed", "society_completed"):
        assert required_event in published_events, f"必須 SSE イベント欠落: {required_event}"


@pytest.mark.asyncio
async def test_run_society_persists_propagation_layer_with_edges(monkeypatch: pytest.MonkeyPatch):
    """エッジが存在する経路では network_propagation レイヤが追加されることを固定する。

    Network Propagation フェーズは ~200 行の巨大ブロックで、エッジ無し golden では
    最初の edge クエリで例外→握り潰しとなり一切カバーされない。P5 で本フェーズを
    抽出する前に、エッジ有り(happy path)の永続化レイヤ集合を characterize する。
    """
    from src.app.services.society import society_orchestrator as orchestrator
    from src.app.services.society import time_axis_runner
    from src.app.services.society.network_propagation import (
        PropagationResult,
        TimestepRecord,
    )
    from src.app.services.society.opinion_dynamics import ClusterInfo

    persisted_layers: list[str] = []
    published_events: list[str] = []

    edges = [SimpleNamespace(agent_id="a1", target_id="a1", strength=0.5)]
    fake_session = _FakeSession(persisted_layers, edges=edges)
    _install_common_mocks(monkeypatch, orchestrator, fake_session, published_events)

    # 伝播エンジンは LLM/数値計算を伴うため決定論的なダミー結果でモックする。
    prop_result = PropagationResult(
        final_opinions=[[0.7]],
        timestep_history=[
            TimestepRecord(
                timestep=0,
                opinions=[[0.7]],
                opinion_distribution={"賛成": 1.0},
                entropy=0.0,
                cluster_count=1,
                max_delta=0.0,
            )
        ],
        clusters=[ClusterInfo(label=0, member_ids=["a1"], centroid=[0.7], size=1)],
        converged=True,
        total_timesteps=1,
        metrics={"echo_chamber": {"homophily_index": 0.0, "polarization_index": 0.0}},
    )

    async def fake_run_network_propagation(**kwargs):
        return prop_result

    monkeypatch.setattr(orchestrator, "run_network_propagation", fake_run_network_propagation)
    # エッジが供給されると Phase 6 の time-axis パイプラインが実体を呼ぶため無効化する
    # （永続化レイヤには影響しないが LLM 呼び出しを避ける）。
    monkeypatch.setattr(time_axis_runner, "run_time_axis_pipeline", AsyncMock(return_value={}))

    await orchestrator.run_society("sim-1")

    # エッジ無し golden の集合 + network_propagation を固定。
    assert set(persisted_layers) == {
        "activation",
        "deliberation_quality",
        "demographic_analysis",
        "evaluation",
        "meeting",
        "narrative",
        "network_propagation",
    }, f"エッジ有り経路の永続化レイヤ集合が変化した: {sorted(set(persisted_layers))}"

    assert fake_session.simulation.status == "completed"
    for required_event in (
        "network_propagation_started",
        "network_propagation_completed",
        "society_completed",
    ):
        assert required_event in published_events, f"必須 SSE イベント欠落: {required_event}"
