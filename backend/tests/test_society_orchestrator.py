"""Society オーケストレータ統合テスト（LLMモック）"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock


class TestIndependenceWeightedReaggregation:
    """独立性重み → 再集計の統合テスト.

    orchestrator が propagation 後に行う再集計フローを直接テスト:
    compute_independence_weights → _aggregate_opinions(independence_weights=...)
    """

    @pytest.mark.asyncio
    async def test_re_aggregation_applies_independence_weights(self):
        """クラスター情報から独立性重みを計算し、再集計で分布が変化すること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.statistical_inference import (
            compute_independence_weights,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]

        # 最初の20人が「賛成」、残り10人が「反対」
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        # Phase A: 通常集計（独立性重みなし）
        agg_plain = _aggregate_opinions(responses, agents=agents)

        # 最初の20人を1つの密クラスター、残り10人をシングルトンとする
        clusters = [
            {"member_ids": agent_ids[:20], "size": 20},
        ] + [
            {"member_ids": [aid], "size": 1} for aid in agent_ids[20:]
        ]

        # 密クラスター内のエッジ（全ペア、高強度）
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        independence_weights = compute_independence_weights(clusters, edges, agent_ids)

        # Phase B: 独立性重み付き再集計
        agg_weighted = _aggregate_opinions(
            responses, agents=agents, independence_weights=independence_weights,
        )

        # 密クラスター（賛成）が割り引かれるので、賛成の割合が減少する
        assert agg_weighted["stance_distribution"]["賛成"] < agg_plain["stance_distribution"]["賛成"]
        assert agg_weighted["independence_weighting_applied"] is True

    @pytest.mark.asyncio
    async def test_re_aggregation_without_propagation_is_unchanged(self):
        """propagation がない場合（independence_weights=None）、集計結果は同じ."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )

        agents = await generate_population("test-pop", count=10, seed=42)
        responses = [
            _parse_activation_response({
                "stance": "賛成",
                "confidence": 0.7,
                "reason": "test",
                "concern": "",
                "priority": "",
            })
            for _ in range(10)
        ]

        agg_a = _aggregate_opinions(responses, agents=agents, independence_weights=None)
        agg_b = _aggregate_opinions(responses, agents=agents)

        assert agg_a["stance_distribution"] == agg_b["stance_distribution"]
        assert agg_a.get("independence_weighting_applied") is False

    @pytest.mark.asyncio
    async def test_re_aggregation_saves_pre_independence(self):
        """orchestrator フローで aggregation_pre_independence が保存されること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.statistical_inference import (
            compute_independence_weights,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]

        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        # Phase A の集計を模擬
        original_aggregation = _aggregate_opinions(responses, agents=agents)

        activation_result = {
            "responses": responses,
            "aggregation": original_aggregation,
        }

        clusters = [
            {"member_ids": agent_ids[:20], "size": 20},
        ] + [
            {"member_ids": [aid], "size": 1} for aid in agent_ids[20:]
        ]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        # aggregation_pre_independence が保存される
        assert "aggregation_pre_independence" in activation_result
        pre = activation_result["aggregation_pre_independence"]
        post = activation_result["aggregation"]

        # pre は独立性重みなし → independence_weighting_applied: False
        assert pre.get("independence_weighting_applied") is False

        # post は独立性重みあり → independence_weighting_applied: True
        assert post["independence_weighting_applied"] is True

        # 分布が異なる（密クラスター割引の効果）
        assert post["stance_distribution"]["賛成"] < pre["stance_distribution"]["賛成"]

    @pytest.mark.asyncio
    async def test_re_aggregation_noop_without_weights(self):
        """independence_weights が空の場合、aggregation_pre_independence は保存されない."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=10, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成",
                "confidence": 0.7,
                "reason": "test",
                "concern": "",
                "priority": "",
            })
            for _ in range(10)
        ]
        original_agg = _aggregate_opinions(responses, agents=agents)
        activation_result = {
            "responses": responses,
            "aggregation": original_agg,
        }

        # 空のクラスター・エッジ → independence_weights は全員 1.0
        _apply_independence_re_aggregation(
            activation_result, [], [], agent_ids, agents,
        )

        # 空クラスターなので re-aggregation は実質スキップ
        assert "aggregation_pre_independence" not in activation_result

    @pytest.mark.asyncio
    async def test_effective_sample_size_decreases_after_re_aggregation(self):
        """independence 再集計後に effective_sample_size が減少すること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]

        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        original_agg = _aggregate_opinions(responses, agents=agents)
        activation_result = {
            "responses": responses,
            "aggregation": original_agg,
        }

        clusters = [
            {"member_ids": agent_ids[:20], "size": 20},
        ] + [
            {"member_ids": [aid], "size": 1} for aid in agent_ids[20:]
        ]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        pre = activation_result["aggregation_pre_independence"]
        post = activation_result["aggregation"]

        assert post["effective_sample_size"] < pre["effective_sample_size"]


class TestObservabilityPrePostAggregation:
    """Phase 3: pre/post aggregation の observability テスト."""

    @pytest.mark.asyncio
    async def test_post_aggregation_retains_independence_metadata(self):
        """再集計後の aggregation に independence_weighting_applied と effective_sample_size が残ること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }

        clusters = [
            {"member_ids": agent_ids[:20], "size": 20},
        ] + [{"member_ids": [aid], "size": 1} for aid in agent_ids[20:]]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        post = activation_result["aggregation"]
        assert "independence_weighting_applied" in post
        assert post["independence_weighting_applied"] is True
        assert "effective_sample_size" in post
        assert post["effective_sample_size"] > 0

    @pytest.mark.asyncio
    async def test_pre_post_both_contain_stance_distribution(self):
        """pre/post 両方に stance_distribution が含まれ、比較可能であること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }

        clusters = [{"member_ids": agent_ids[:20], "size": 20}]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        pre = activation_result["aggregation_pre_independence"]
        post = activation_result["aggregation"]

        # 両方に stance_distribution がある
        assert "stance_distribution" in pre
        assert "stance_distribution" in post

        # 両方に effective_sample_size がある
        assert "effective_sample_size" in pre
        assert "effective_sample_size" in post

        # 同じスタンスキーを持つ
        assert set(pre["stance_distribution"].keys()) == set(post["stance_distribution"].keys())

    @pytest.mark.asyncio
    async def test_activation_phase_payload_persists_pre_and_post_aggregations(self):
        """activation 保存 payload に pre/post aggregation が両方載ること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
            _build_activation_phase_data,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }
        individual_responses = [
            {
                "agent_id": agent["id"],
                "agent_index": agent.get("agent_index", 0),
                "stance": resp["stance"],
                "confidence": resp["confidence"],
                "reason": resp["reason"],
                "concern": resp["concern"],
                "priority": resp["priority"],
            }
            for agent, resp in zip(agents, responses)
        ]

        clusters = [{"member_ids": agent_ids[:20], "size": 20}]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )
        phase_data = _build_activation_phase_data(
            activation_result=activation_result,
            representative_count=8,
            individual_responses=individual_responses,
        )

        assert phase_data["aggregation"] == activation_result["aggregation"]
        assert phase_data["aggregation_pre_independence"] == activation_result["aggregation_pre_independence"]
        assert phase_data["responses_summary"]["stance_distribution"] == activation_result["aggregation"]["stance_distribution"]
        assert phase_data["responses_summary_pre_independence"]["stance_distribution"] == activation_result["aggregation_pre_independence"]["stance_distribution"]

    @pytest.mark.asyncio
    async def test_reaggregation_summary_contains_pre_post_comparison_metrics(self):
        """propagation 保存用 summary が pre/post 分布と n_eff を持つこと."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
            _build_independence_reaggregation_summary,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }
        clusters = [{"member_ids": agent_ids[:20], "size": 20}]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )
        summary = _build_independence_reaggregation_summary(activation_result)

        assert summary["applied"] is True
        assert summary["effective_sample_size_pre"] == activation_result["aggregation_pre_independence"]["effective_sample_size"]
        assert summary["effective_sample_size_post"] == activation_result["aggregation"]["effective_sample_size"]
        assert summary["stance_distribution_pre"] == activation_result["aggregation_pre_independence"]["stance_distribution"]
        assert summary["stance_distribution_post"] == activation_result["aggregation"]["stance_distribution"]


class TestVerificationPhase:
    """Phase 4: narrative / provenance が補正後 aggregation でも壊れないことを確認."""

    @pytest.mark.asyncio
    async def test_narrative_accepts_independence_weighted_aggregation(self):
        """generate_narrative が independence-weighted aggregation を受け取ってもエラーにならない."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.narrative_generator import generate_narrative
        from src.app.services.society.demographic_analyzer import analyze_demographics
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "コスト" if i % 2 == 0 else "環境",
                "priority": "効率",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }

        clusters = [{"member_ids": agent_ids[:20], "size": 20}]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        demographic_analysis = analyze_demographics(agents, responses)

        # independence-weighted aggregation を渡しても壊れない
        narrative = generate_narrative(
            agents,
            responses,
            synthesis={"consensus_points": ["テスト"], "key_insights": []},
            aggregation=activation_result["aggregation"],
            demographic_analysis=demographic_analysis,
        )

        assert "executive_summary" in narrative
        assert "key_findings" in narrative

    @pytest.mark.asyncio
    async def test_provenance_accepts_independence_weighted_n_eff(self):
        """build_provenance が independence-weighted effective_sample_size を受け取ってもエラーにならない."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.provenance import build_provenance
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=30, seed=42)
        agent_ids = [a["id"] for a in agents]
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 20 else "反対",
                "confidence": 0.8,
                "reason": f"理由{i}",
                "concern": "",
                "priority": "",
            })
            for i in range(30)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }

        clusters = [{"member_ids": agent_ids[:20], "size": 20}]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.9}
            for i in range(20) for j in range(i + 1, 20)
        ]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        post_n_eff = activation_result["aggregation"]["effective_sample_size"]

        # independence-weighted n_eff を渡しても壊れない
        provenance = build_provenance(
            population_size=100,
            selected_count=30,
            effective_sample_size=post_n_eff,
            activation_params={"temperature": 0.5},
            meeting_params={"num_rounds": 3, "participants": 10},
        )

        assert "methodology" in provenance
        assert provenance["parameters"]["effective_sample_size"] == post_n_eff

    @pytest.mark.asyncio
    async def test_synthetic_majority_cluster_share_decreases(self):
        """合成ケース: 多数派密クラスターのシェアが independence 再集計で下がること."""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.activation_layer import (
            _aggregate_opinions,
            _parse_activation_response,
        )
        from src.app.services.society.society_orchestrator import (
            _apply_independence_re_aggregation,
        )

        agents = await generate_population("test-pop", count=50, seed=42)
        agent_ids = [a["id"] for a in agents]

        # 40人が賛成（密クラスター）、10人が反対（シングルトン）
        # reason を十分長く・具体的にして品質分類を統一（high tier）
        responses = [
            _parse_activation_response({
                "stance": "賛成" if i < 40 else "反対",
                "confidence": 0.8,
                "reason": f"私は東京都内の職場で月額{i+10}万円の影響を受けており、この政策について具体的な意見があります。生活への直接的な影響が大きいと感じています。",
                "concern": "",
                "priority": "",
            })
            for i in range(50)
        ]

        activation_result = {
            "responses": responses,
            "aggregation": _aggregate_opinions(responses, agents=agents),
        }

        # 40人を密クラスター、10人をシングルトン
        clusters = [
            {"member_ids": agent_ids[:40], "size": 40},
        ] + [
            {"member_ids": [aid], "size": 1} for aid in agent_ids[40:]
        ]
        edges = [
            {"agent_id": agent_ids[i], "target_id": agent_ids[j], "strength": 0.85}
            for i in range(40) for j in range(i + 1, 40)
        ]

        pre_share = activation_result["aggregation"]["stance_distribution"]["賛成"]

        _apply_independence_re_aggregation(
            activation_result, clusters, edges, agent_ids, agents,
        )

        post_share = activation_result["aggregation"]["stance_distribution"]["賛成"]

        # 多数派クラスターのシェアが下がる
        assert post_share < pre_share


class TestSocietyOrchestratorImports:
    """基本的なインポートテスト"""

    def test_import_orchestrator(self):
        from src.app.services.society.society_orchestrator import run_society
        assert callable(run_society)

    def test_import_all_services(self):
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.network_generator import generate_network
        from src.app.services.society.agent_selector import select_agents
        from src.app.services.society.activation_layer import run_activation
        from src.app.services.society.evaluation import evaluate_society_simulation
        assert all(callable(f) for f in [
            generate_population, generate_network, select_agents,
            run_activation, evaluate_society_simulation,
        ])


class TestSocietyOrchestratorFlow:
    """オーケストレーションフローのユニットテスト"""

    @pytest.mark.asyncio
    async def test_population_then_select_then_activate(self):
        """Population→Selection→Activation の一連の流れ（LLMモック）"""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.agent_selector import select_agents
        from src.app.services.society.activation_layer import _aggregate_opinions, _parse_activation_response

        # 1. Population 生成
        agents = await generate_population("test-pop", count=100, seed=42)
        assert len(agents) == 100

        # 2. 選抜
        selected = await select_agents(agents, "日本の経済政策について", target_count=20, min_count=20, max_count=20)
        assert 15 <= len(selected) <= 60  # diversity additions may increase count

        # 3. 活性化レスポンスのパースと集計（LLM呼び出しなし）
        mock_responses = [
            _parse_activation_response({
                "stance": ["賛成", "反対", "中立", "条件付き賛成"][i % 4],
                "confidence": 0.5 + (i % 5) * 0.1,
                "reason": f"理由{i}",
                "concern": f"懸念{i % 3}",
                "priority": f"優先{i % 2}",
            })
            for i in range(len(selected))
        ]

        aggregation = _aggregate_opinions(mock_responses)
        assert aggregation["total_respondents"] == len(selected)
        assert len(aggregation["stance_distribution"]) >= 2

    @pytest.mark.asyncio
    async def test_evaluation_after_activation(self):
        """評価メトリクスの計算"""
        from src.app.services.society.population_generator import generate_population
        from src.app.services.society.evaluation import evaluate_society_simulation

        agents = await generate_population("test-pop", count=50, seed=42)
        responses = [
            {
                "stance": ["賛成", "反対", "中立"][i % 3],
                "confidence": 0.3 + (i % 7) * 0.1,
                "reason": f"理由{i}",
            }
            for i in range(50)
        ]

        metrics = await evaluate_society_simulation(agents, responses)
        assert len(metrics) >= 3  # diversity, consistency, calibration

        metric_dict = {m["metric_name"]: m["score"] for m in metrics}
        assert "diversity" in metric_dict
        assert metric_dict["diversity"] > 0  # 3 stances should give some diversity

    @pytest.mark.asyncio
    async def test_run_society_uses_configured_default_population_size(self, monkeypatch: pytest.MonkeyPatch):
        from src.app.services.society import society_orchestrator as orchestrator

        observed_counts: list[int] = []
        published_events: list[tuple[str, dict]] = []

        class FakeSession:
            def __init__(self):
                self.simulation = SimpleNamespace(
                    id="sim-1",
                    prompt_text="日本の経済政策について",
                    population_id=None,
                    status="running",
                    completed_at=None,
                    metadata_json={},
                    error_message=None,
                )

            async def get(self, model, obj_id):
                return self.simulation

            def add(self, obj):
                pass

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def execute(self, stmt):
                """func.count() クエリ用のフェイクレスポンス。"""
                return SimpleNamespace(scalar=lambda: 5)

        class FakeSessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = FakeSession()

        async def fake_get_or_create_population(session, population_id, count=None):
            observed_counts.append(count)
            return "pop-1", [{"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}}]

        async def fake_publish(simulation_id, event, data):
            published_events.append((event, data))

        async def fake_select_agents(agents, theme, target_count=100):
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
            return {"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "rounds": []}

        monkeypatch.setattr(orchestrator, "async_session", lambda: FakeSessionContext(fake_session))
        monkeypatch.setattr(orchestrator, "get_default_population_size", lambda: 321)
        monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
        monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
        monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
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

        monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
        monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
        monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
        monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())

        await orchestrator.run_society("sim-1")

        assert observed_counts == [321]
        assert any(
            event == "population_status" and payload.get("target_count") == 321
            for event, payload in published_events
        )


class TestRunSocietyPipelineFixes:
    @pytest.mark.asyncio
    async def test_run_society_tracks_real_timestep_opinions(self, monkeypatch: pytest.MonkeyPatch):
        from src.app.services.society import society_orchestrator as orchestrator

        class FakeTracker:
            instances: list["FakeTracker"] = []

            def __init__(self):
                self.recorded: list[dict] = []
                FakeTracker.instances.append(self)

            def record_timestep(self, data: dict) -> None:
                self.recorded.append(data)

            def detect_phase_transitions(self):
                return []

            def detect_tipping_points(self):
                return []

        class FakeSession:
            def __init__(self):
                self.simulation = SimpleNamespace(
                    id="sim-1",
                    prompt_text="日本の経済政策について",
                    population_id=None,
                    status="running",
                    completed_at=None,
                    metadata_json={},
                    error_message=None,
                )

            async def get(self, model, obj_id):
                return self.simulation

            def add(self, obj):
                pass

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def execute(self, stmt):
                return SimpleNamespace(
                    scalar=lambda: 5,
                    scalars=lambda: SimpleNamespace(all=lambda: []),
                )

        class FakeSessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = FakeSession()

        async def fake_get_or_create_population(session, population_id, count=None):
            return "pop-1", [
                {"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}},
                {"id": "a2", "demographics": {"age": 62, "region": "九州", "occupation": "自営業"}},
            ]

        async def fake_publish(simulation_id, event, data):
            return None

        async def fake_select_agents(agents, theme, target_count=100):
            return agents

        async def fake_run_activation(selected_agents, theme, on_progress=None):
            if on_progress is not None:
                await on_progress(2, 2)
            return {
                "aggregation": {"stance_distribution": {"賛成": 0.5, "反対": 0.5}, "total_respondents": 2},
                "representatives": [{"id": "a1"}, {"id": "a2"}],
                "responses": [
                    {"stance": "賛成", "confidence": 0.8, "reason": "test1", "concern": ""},
                    {"stance": "反対", "confidence": 0.7, "reason": "test2", "concern": ""},
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        async def fake_run_network_propagation(
            agents, initial_responses, edges, theme,
            max_timesteps=20, confidence_threshold=0.4, on_timestep=None
        ):
            records = [
                SimpleNamespace(
                    timestep=0,
                    opinions=[[0.5], [0.5]],
                    opinion_distribution={"中立": 1.0},
                    entropy=0.0,
                    cluster_count=1,
                    max_delta=0.0,
                ),
                SimpleNamespace(
                    timestep=1,
                    opinions=[[0.2], [0.8]],
                    opinion_distribution={"反対": 0.5, "賛成": 0.5},
                    entropy=0.69,
                    cluster_count=2,
                    max_delta=0.3,
                ),
            ]
            if on_timestep is not None:
                for record in records:
                    await on_timestep(record)
            return SimpleNamespace(
                final_opinions=[[0.2], [0.8]],
                timestep_history=records,
                clusters=[],
                converged=True,
                total_timesteps=2,
                metrics={},
            )

        async def fake_evaluate_society_simulation(selected_agents, responses):
            return [{"metric_name": "diversity", "score": 0.5, "details": {}}]

        async def fake_run_meeting(participants, theme, simulation_id=None, num_rounds=3):
            return {
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "rounds": [],
                "participants": [],
                "synthesis": {"consensus_points": [], "key_insights": []},
            }

        monkeypatch.setattr(orchestrator, "async_session", lambda: FakeSessionContext(fake_session))
        monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
        monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
        monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
        monkeypatch.setattr(orchestrator, "select_agents", fake_select_agents)
        monkeypatch.setattr(orchestrator, "run_activation", fake_run_activation)
        monkeypatch.setattr(orchestrator, "run_network_propagation", fake_run_network_propagation)
        monkeypatch.setattr(orchestrator, "_apply_independence_re_aggregation", lambda *args, **kwargs: {})
        monkeypatch.setattr(orchestrator, "evaluate_society_simulation", fake_evaluate_society_simulation)
        monkeypatch.setattr(orchestrator, "select_representatives", lambda *args, **kwargs: [])
        monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
        monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
        monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
        monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())
        monkeypatch.setattr(orchestrator, "load_grounding_facts", lambda theme: [])
        monkeypatch.setattr(orchestrator, "distribute_facts_to_agents", lambda agents, facts: {})
        monkeypatch.setattr(orchestrator, "EmergenceTracker", FakeTracker)

        from src.app.services.society import validation_pipeline

        async def fake_register_result(session, simulation_id, theme, theme_category, distribution):
            return {"id": "validation-1"}

        async def fake_auto_compare(session, validation_record, survey_data_dir):
            return None

        monkeypatch.setattr(validation_pipeline, "register_result", fake_register_result)
        monkeypatch.setattr(validation_pipeline, "auto_compare", fake_auto_compare)

        await orchestrator.run_society("sim-1")

        tracker = FakeTracker.instances[-1]
        assert [entry["opinions"] for entry in tracker.recorded] == [
            [[0.5], [0.5]],
            [[0.2], [0.8]],
        ]

    @pytest.mark.asyncio
    async def test_run_society_uses_repo_level_survey_data_dir(self, monkeypatch: pytest.MonkeyPatch):
        from src.app.services.society import society_orchestrator as orchestrator

        observed_dirs: list[str] = []

        class FakeSession:
            def __init__(self):
                self.simulation = SimpleNamespace(
                    id="sim-1",
                    prompt_text="日本の経済政策について",
                    population_id=None,
                    status="running",
                    completed_at=None,
                    metadata_json={},
                    error_message=None,
                )

            async def get(self, model, obj_id):
                return self.simulation

            def add(self, obj):
                pass

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def execute(self, stmt):
                return SimpleNamespace(
                    scalar=lambda: 5,
                    scalars=lambda: SimpleNamespace(all=lambda: []),
                )

        class FakeSessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = FakeSession()

        async def fake_get_or_create_population(session, population_id, count=None):
            return "pop-1", [
                {"id": "a1", "demographics": {"age": 35, "region": "関東（都市部）", "occupation": "会社員"}},
            ]

        async def fake_publish(simulation_id, event, data):
            return None

        async def fake_select_agents(agents, theme, target_count=100):
            return agents

        async def fake_run_activation(selected_agents, theme, on_progress=None):
            return {
                "aggregation": {"stance_distribution": {"賛成": 1.0}, "total_respondents": 1},
                "representatives": [{"id": "a1"}],
                "responses": [{"stance": "賛成", "confidence": 0.8, "reason": "test"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        async def fake_evaluate_society_simulation(selected_agents, responses):
            return [{"metric_name": "diversity", "score": 0.5, "details": {}}]

        async def fake_run_meeting(participants, theme, simulation_id=None, num_rounds=3):
            return {
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "rounds": [],
                "participants": [],
                "synthesis": {"consensus_points": [], "key_insights": []},
            }

        async def fake_run_network_propagation(*args, **kwargs):
            raise RuntimeError("skip propagation")

        monkeypatch.setattr(orchestrator, "async_session", lambda: FakeSessionContext(fake_session))
        monkeypatch.setattr(orchestrator, "_get_or_create_population", fake_get_or_create_population)
        monkeypatch.setattr(orchestrator.sse_manager, "publish", fake_publish)
        monkeypatch.setattr(orchestrator, "_save_network", AsyncMock())
        monkeypatch.setattr(orchestrator, "select_agents", fake_select_agents)
        monkeypatch.setattr(orchestrator, "run_activation", fake_run_activation)
        monkeypatch.setattr(orchestrator, "run_network_propagation", fake_run_network_propagation)
        monkeypatch.setattr(orchestrator, "evaluate_society_simulation", fake_evaluate_society_simulation)
        monkeypatch.setattr(orchestrator, "select_representatives", lambda *args, **kwargs: [])
        monkeypatch.setattr(orchestrator, "run_meeting", fake_run_meeting)
        monkeypatch.setattr(orchestrator, "generate_meeting_report", lambda meeting_result: {"summary": "ok"})
        monkeypatch.setattr(orchestrator, "update_agent_memories", AsyncMock())
        monkeypatch.setattr(orchestrator, "evolve_social_graph", AsyncMock())
        monkeypatch.setattr(orchestrator, "load_grounding_facts", lambda theme: [])
        monkeypatch.setattr(orchestrator, "distribute_facts_to_agents", lambda agents, facts: {})

        from src.app.services.society import validation_pipeline

        async def fake_register_result(session, simulation_id, theme, theme_category, distribution):
            return {"id": "validation-1"}

        async def fake_auto_compare(session, validation_record, survey_data_dir):
            observed_dirs.append(survey_data_dir)
            return None

        monkeypatch.setattr(validation_pipeline, "register_result", fake_register_result)
        monkeypatch.setattr(validation_pipeline, "auto_compare", fake_auto_compare)

        await orchestrator.run_society("sim-1")

        assert observed_dirs == [
            str(orchestrator.settings.config_dir / "grounding" / "survey_data")
        ]
