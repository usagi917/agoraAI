"""全人口意見伝播 (population_propagation) のテスト。

選抜済み（活性化済み）エージェントの意見を種として、未活性化の大衆へ
ネットワーク伝播させる。活性化済みはアンカーとして意見を保ち、
未活性化は頑固さが減衰され周囲に感化されやすい。
"""

import pytest

from src.app.services.society.population_propagation import (
    MIN_SUSCEPTIBLE_STUBBORNNESS,
    SUSCEPTIBILITY_DAMPENING,
    build_engine_agents,
    run_population_propagation,
)
from src.app.services.society.opinion_dynamics import stubbornness_from_big_five


def _agent(index: int, big_five: dict | None = None) -> dict:
    return {
        "id": f"agent-{index}",
        "agent_index": index,
        "big_five": big_five or {"C": 0.5, "A": 0.5, "O": 0.5},
        "demographics": {"occupation": "会社員", "age": 30, "region": "関東"},
    }


def _edge(src: int, tgt: int, strength: float = 0.8) -> dict:
    return {
        "agent_id": f"agent-{src}",
        "target_id": f"agent-{tgt}",
        "strength": strength,
    }


def _response(index: int, stance: str, confidence: float = 1.0) -> dict:
    return {"agent_id": f"agent-{index}", "stance": stance, "confidence": confidence}


class TestAnchoring:
    @pytest.mark.asyncio
    async def test_activated_agents_keep_stance(self):
        """活性化済みエージェント同士は意見アンカーでスタンスを保持する。"""
        agents = [_agent(0, {"C": 0.9, "A": 0.3}), _agent(1, {"C": 0.9, "A": 0.3})]
        edges = [_edge(0, 1), _edge(1, 0)]
        responses = [_response(0, "賛成"), _response(1, "賛成")]

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=6,
        )

        stances = {s["agent_id"]: s["stance"] for s in result.final_stances}
        assert stances["agent-0"] == "賛成"
        assert stances["agent-1"] == "賛成"

    @pytest.mark.asyncio
    async def test_isolated_undecided_stays_neutral(self):
        """エッジを持たない未活性化エージェントは中立のまま。"""
        agents = [_agent(0), _agent(1)]
        responses = [_response(0, "賛成")]
        # エッジなし

        result = await run_population_propagation(
            agents, responses, [], max_timesteps=6,
        )

        stances = {s["agent_id"]: s["stance"] for s in result.final_stances}
        assert stances["agent-1"] == "中立"


class TestSusceptibleMass:
    @pytest.mark.asyncio
    async def test_undecided_neighbors_get_influenced(self):
        """活性化済み（賛成）の周囲の未活性化エージェントは賛成側に動く。"""
        # スター型: agent-0 (賛成アンカー) を 1..4 が囲む
        agents = [_agent(i) for i in range(5)]
        edges = []
        for i in range(1, 5):
            edges.append(_edge(i, 0))
            edges.append(_edge(0, i))
        responses = [_response(0, "賛成", confidence=1.0)]

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=8,
        )

        for s in result.final_stances:
            if s["agent_id"] == "agent-0":
                continue
            assert s["opinion"] > 0.55, f"{s['agent_id']} が感化されていない: {s['opinion']}"
            assert s["stance"] in ("条件付き賛成", "賛成")

    @pytest.mark.asyncio
    async def test_single_directed_edge_influences_target_endpoint(self):
        """無向タイは片方向で保存されても両端が相互に感化される（エッジミラー回帰）。

        本番の network_generator は無向タイを agent_id->target_id の一方向で1本だけ
        保存する。ミラーリングがないと target 側（ここでは agent-1）はエンジンの
        片方向隣接で誰の隣人にもならず、中立のまま固定されてしまう。
        """
        agents = [_agent(0), _agent(1)]
        # 無向タイを 1 本だけ、アンカー(agent-0)を source として保存
        edges = [_edge(0, 1)]
        responses = [_response(0, "賛成", confidence=1.0)]

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=8,
        )

        stances = {s["agent_id"]: s for s in result.final_stances}
        # ミラーがなければ 0.5 のまま。あれば賛成アンカーへ引き寄せられる。
        assert stances["agent-1"]["opinion"] > 0.55, stances["agent-1"]
        assert stances["agent-1"]["stance"] in ("条件付き賛成", "賛成")

    def test_susceptibility_dampening_applied(self):
        """未活性化エージェントの頑固さは減衰され、活性化済みは素の値を使う。"""
        big_five = {"C": 0.8, "A": 0.4}
        agents = [_agent(0, big_five), _agent(1, big_five)]
        responses = [_response(0, "賛成", confidence=1.0)]

        engine_agents = build_engine_agents(
            agents, {r["agent_id"]: r for r in responses},
        )

        base = stubbornness_from_big_five(0.8, agreeableness=0.4)
        by_id = {ea["id"]: ea for ea in engine_agents}
        assert by_id["agent-0"]["stubbornness"] == pytest.approx(base)
        assert by_id["agent-1"]["stubbornness"] == pytest.approx(
            max(MIN_SUSCEPTIBLE_STUBBORNNESS, base * SUSCEPTIBILITY_DAMPENING)
        )
        # 初期意見: 活性化済みは stance×confidence、未活性化は中立 0.5
        assert by_id["agent-0"]["opinion_vector"][0] == pytest.approx(0.9)
        assert by_id["agent-1"]["opinion_vector"][0] == pytest.approx(0.5)


class TestRoundsAndResult:
    @pytest.mark.asyncio
    async def test_empty_population_returns_empty_result_without_rounds(self):
        """空 population はエンジンに渡さず空結果として扱う。"""
        received: list = []

        result = await run_population_propagation(
            [],
            [_response(0, "賛成")],
            [_edge(0, 1)],
            max_timesteps=4,
            on_round=received.append,
        )

        assert result.final_stances == []
        assert result.distribution == {}
        assert result.total_rounds == 0
        assert result.converged is True
        assert received == []

    @pytest.mark.asyncio
    async def test_on_round_receives_stance_changes(self):
        """ラウンドコールバックがスタンス変化デルタを受け取る。"""
        agents = [_agent(i) for i in range(5)]
        edges = []
        for i in range(1, 5):
            edges.append(_edge(i, 0))
            edges.append(_edge(0, i))
        responses = [_response(0, "賛成", confidence=1.0)]

        received: list = []

        async def on_round(delta):
            received.append(delta)

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=8, on_round=on_round,
        )

        assert len(received) == result.total_rounds
        all_changes = [c for d in received for c in d.changes]
        changed_indices = {c["agent_index"] for c in all_changes}
        # 未活性化の誰かが中立から変化している
        assert changed_indices & {1, 2, 3, 4}
        for c in all_changes:
            assert set(c.keys()) >= {"agent_index", "stance"}
        for d in received:
            assert d.changed_count == len(d.changes)
            assert abs(sum(d.distribution.values()) - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_changed_agent_reports_deterministic_primary_influencer(self):
        """同じ寄与度なら agent_id 順で主要影響元を一意に決める。"""
        agents = [_agent(index) for index in range(3)]
        responses = [
            _response(0, "賛成", confidence=1.0),
            _response(1, "賛成", confidence=1.0),
        ]
        edges = [
            _edge(2, 1, strength=0.9),
            _edge(2, 0, strength=0.9),
        ]

        result = await run_population_propagation(
            agents,
            responses,
            edges,
            max_timesteps=8,
            seed=7,
        )

        target_change = next(
            change
            for delta in result.rounds
            for change in delta.changes
            if change["agent_id"] == "agent-2"
        )
        assert target_change["source_id"] == "agent-0"
        assert target_change["target_id"] == "agent-2"
        assert target_change["before_stance"] == "中立"
        assert target_change["after_stance"] in ("条件付き賛成", "賛成")
        assert target_change["opinion_delta"] > 0
        assert target_change["edge_strength"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_on_round_accepts_sync_callback(self):
        """同期コールバックも await されず正しく呼ばれる。"""
        agents = [_agent(i) for i in range(5)]
        edges = []
        for i in range(1, 5):
            edges.append(_edge(i, 0))
            edges.append(_edge(0, i))
        responses = [_response(0, "賛成", confidence=1.0)]

        received: list = []

        def on_round(delta):  # 非同期ではない普通の関数
            received.append(delta)

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=8, on_round=on_round,
        )

        assert len(received) == result.total_rounds
        assert all(
            d.changed_count == len(d.changes) for d in received
        )

    @pytest.mark.asyncio
    async def test_distribution_covers_population(self):
        """最終分布は全人口ベースで合計 1。"""
        agents = [_agent(i) for i in range(10)]
        edges = [_edge(i, (i + 1) % 10) for i in range(10)]
        responses = [_response(0, "賛成"), _response(5, "反対")]

        result = await run_population_propagation(
            agents, responses, edges, max_timesteps=4,
        )

        assert abs(sum(result.distribution.values()) - 1.0) < 1e-6
        assert len(result.final_stances) == 10

    @pytest.mark.asyncio
    async def test_deterministic_with_seed(self):
        """同じ seed では結果が一致する。"""
        agents = [_agent(i) for i in range(20)]
        edges = [_edge(i, (i + 1) % 20) for i in range(20)]
        responses = [_response(0, "賛成"), _response(10, "反対")]

        r1 = await run_population_propagation(
            agents, responses, edges, max_timesteps=6, seed=42,
        )
        r2 = await run_population_propagation(
            agents, responses, edges, max_timesteps=6, seed=42,
        )

        assert [s["opinion"] for s in r1.final_stances] == [
            s["opinion"] for s in r2.final_stances
        ]

    @pytest.mark.asyncio
    async def test_converges_early_without_edges(self):
        """変化がなければ max_timesteps を待たずに収束する。"""
        agents = [_agent(i) for i in range(5)]
        responses = [_response(0, "賛成")]

        result = await run_population_propagation(
            agents, responses, [], max_timesteps=10,
        )

        assert result.converged is True
        assert result.total_rounds < 10
