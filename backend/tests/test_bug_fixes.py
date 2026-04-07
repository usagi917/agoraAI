"""TDDバグ修正テスト群 (RED phase)

5つのバグを修正するためのテスト:
[1] sensitivity_analysis: run_provider_ensemble が実際の run_activation コントラクトを使う
[2] validation_pipeline: find_optimal_gamma が全分布 Brier スコアを使う
[3] population_generator: _generate_big_five が pop_config の mean を使う
[4] scenario_pair_status: queued 状態を running に誤って変換しない
[5] scenario_pair_status: concurrent 更新で completed -> running にならない
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


# ===========================================================================
# Bug [1]: sensitivity_analysis.py — run_provider_ensemble の正しいコントラクト
# ===========================================================================

# run_activation の実際の返り値構造:
# {
#     "responses": [...],
#     "aggregation": {
#         "stance_distribution": {...},
#         ...
#     },
#     "representatives": [...],
#     "usage": {...},
# }

def _make_correct_activation_fn(provider_dists: dict[str, dict]):
    """run_activation の実際の返り値構造を返すモック。

    run_activation は provider 引数を受け取らない。
    stance_distribution は aggregation キーの中に入っている。
    """
    async def activation_fn(agents, theme, **kwargs):
        provider = agents[0].get("llm_backend", "default")
        dist = provider_dists[provider]
        return {
            "responses": [],
            "aggregation": {
                "stance_distribution": dist,
                "total_respondents": 3,
            },
            "representatives": [],
            "usage": {},
        }

    return activation_fn


_PROVIDER_DISTS = {
    "openai": {"賛成": 0.35, "反対": 0.30, "中立": 0.15, "条件付き賛成": 0.10, "条件付き反対": 0.10},
    "anthropic": {"賛成": 0.40, "反対": 0.25, "中立": 0.15, "条件付き賛成": 0.12, "条件付き反対": 0.08},
    "google": {"賛成": 0.38, "反対": 0.28, "中立": 0.14, "条件付き賛成": 0.11, "条件付き反対": 0.09},
}

SAMPLE_AGENTS = [
    {"id": "a1", "name": "田中太郎"},
    {"id": "a2", "name": "鈴木花子"},
]
SAMPLE_THEME = "最低賃金引き上げ"


@pytest.mark.asyncio
async def test_ensemble_uses_aggregation_structure():
    """run_provider_ensemble は run_activation の実際の返り値構造から
    aggregation.stance_distribution を読み取る。

    モックが run_activation の実際の返り値構造 (aggregation.stance_distribution) を
    返す場合、ensemble_distribution に値が入ること。
    """
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_correct_activation_fn(_PROVIDER_DISTS)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic", "google"],
        activation_fn=activation_fn,
    )

    assert "ensemble_distribution" in result
    dist = result["ensemble_distribution"]
    assert isinstance(dist, dict)
    assert len(dist) > 0, "ensemble_distribution should not be empty"
    total = sum(dist.values())
    assert abs(total - 1.0) < 0.01, f"Distribution should sum to 1.0, got {total}"


@pytest.mark.asyncio
async def test_ensemble_uses_provider_specific_agent_backends():
    """各 provider run は agents.llm_backend を対象 provider に揃えて呼び出される。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    received_backends: list[list[str]] = []

    async def spy_activation_fn(agents, theme, **kwargs):
        received_backends.append([agent.get("llm_backend") for agent in agents])
        return {
            "responses": [],
            "aggregation": {"stance_distribution": {"賛成": 0.5, "反対": 0.5}},
            "representatives": [],
            "usage": {},
        }

    await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic"],
        activation_fn=spy_activation_fn,
    )

    assert received_backends == [
        ["openai", "openai"],
        ["anthropic", "anthropic"],
    ]


@pytest.mark.asyncio
async def test_ensemble_single_provider_with_correct_structure():
    """プロバイダ1つ + 正しい返り値構造 → ensemble_distribution に値が入る。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    expected_dist = {"賛成": 0.35, "反対": 0.30, "中立": 0.15, "条件付き賛成": 0.10, "条件付き反対": 0.10}

    async def activation_fn(agents, theme, **kwargs):
        return {
            "responses": [],
            "aggregation": {"stance_distribution": expected_dist},
            "representatives": [],
            "usage": {},
        }

    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai"],
        activation_fn=activation_fn,
    )

    ensemble = result["ensemble_distribution"]
    for stance, prob in expected_dist.items():
        assert stance in ensemble, f"Missing stance: {stance}"
        assert abs(ensemble[stance] - prob) < 0.01, (
            f"Stance {stance}: expected {prob}, got {ensemble[stance]}"
        )


# ===========================================================================
# Bug [2]: validation_pipeline.py — gamma チューニングが全分布 Brier スコアを使う
# ===========================================================================

# validation_repo.py の _brier_score_distributions は全分布で計算:
#   Σ(p_i - a_i)² where p_i = predicted, a_i = actual
#
# 現在の find_optimal_gamma は argmax(actual) を observed_outcome として
# brier_external(corrected, observed) を使っており、全分布評価と異なる。
# 修正後: Σ(corrected_i - actual_i)² を直接使う。


class _FakeRecord:
    """検証済みレコードのフェイク。"""

    def __init__(self, sim_dist: dict, actual_dist: dict, category: str = "economy"):
        self.simulated_distribution = sim_dist
        self.actual_distribution = actual_dist
        self.theme_category = category
        self.validated_at = "2024-01"


@pytest.mark.asyncio
async def test_find_optimal_gamma_uses_full_distribution_brier():
    """find_optimal_gamma は全分布 Brier スコア Σ(p_i - a_i)² で最適化する。

    全分布 Brier を最小化する gamma が選ばれることを確認する。
    具体的には、simulated_distribution が actual_distribution と最も近くなる
    gamma でスコアが最小になるべき。
    """
    from src.app.services.society.validation_pipeline import find_optimal_gamma
    from src.app.services.society.calibration import extremeness_aversion_correction

    # シミュレーション結果: 中立寄りバイアスあり
    sim_dist = {"賛成": 0.25, "中立": 0.50, "反対": 0.25}
    # 実際の分布: より両端寄り
    actual_dist = {"賛成": 0.40, "中立": 0.20, "反対": 0.40}

    records = [_FakeRecord(sim_dist, actual_dist)]

    # 全分布 Brier で手動計算して期待 gamma を求める
    best_manual_gamma = None
    best_manual_brier = float("inf")
    g = 0.3
    while g <= 1.5 + 1e-9:
        gamma = round(g, 2)
        corrected = extremeness_aversion_correction(sim_dist, gamma)
        all_keys = set(corrected.keys()) | set(actual_dist.keys())
        brier = sum(
            (corrected.get(k, 0.0) - actual_dist.get(k, 0.0)) ** 2
            for k in all_keys
        )
        if brier < best_manual_brier:
            best_manual_brier = brier
            best_manual_gamma = gamma
        g += 0.1

    result = await find_optimal_gamma(session=None, _records=records)

    assert result["best_gamma"] == pytest.approx(best_manual_gamma, abs=0.05), (
        f"Expected gamma {best_manual_gamma} (full-dist Brier), "
        f"got {result['best_gamma']}"
    )


@pytest.mark.asyncio
async def test_find_optimal_gamma_brier_scores_are_full_distribution():
    """gamma_scores の avg_brier は全分布 Brier スコアであること。

    argmax ベースの Brier (brier_external) は全分布 Brier とは値が異なるため、
    この差で実装を区別できる。
    """
    from src.app.services.society.validation_pipeline import find_optimal_gamma
    from src.app.services.society.calibration import extremeness_aversion_correction

    sim_dist = {"賛成": 0.30, "条件付き賛成": 0.25, "中立": 0.20, "条件付き反対": 0.15, "反対": 0.10}
    actual_dist = {"賛成": 0.25, "条件付き賛成": 0.20, "中立": 0.25, "条件付き反対": 0.15, "反対": 0.15}

    records = [_FakeRecord(sim_dist, actual_dist)]
    result = await find_optimal_gamma(session=None, _records=records)

    # gamma=1.0 のエントリを取得
    gamma_1_entry = next(
        (e for e in result["gamma_scores"] if abs(e["gamma"] - 1.0) < 1e-9),
        None,
    )
    assert gamma_1_entry is not None

    # gamma=1.0 の全分布 Brier は correction なしなので sim_dist vs actual_dist の差
    all_keys = set(sim_dist.keys()) | set(actual_dist.keys())
    expected_brier_full_dist = sum(
        (sim_dist.get(k, 0.0) - actual_dist.get(k, 0.0)) ** 2 for k in all_keys
    )

    # argmax ベースの Brier (brier_external) は異なる値
    from src.app.services.society.calibration import brier_external
    argmax_actual = max(actual_dist, key=actual_dist.get)
    expected_brier_argmax = brier_external(sim_dist, argmax_actual)

    # 二つの値は異なるはず
    assert abs(expected_brier_full_dist - expected_brier_argmax) > 0.001, (
        "Full-dist Brier and argmax Brier should differ for this test to be meaningful"
    )

    # 実装が全分布 Brier を使っているなら、gamma_1_entry の avg_brier は expected_brier_full_dist
    assert gamma_1_entry["avg_brier"] == pytest.approx(expected_brier_full_dist, abs=1e-6), (
        f"Expected full-dist Brier {expected_brier_full_dist}, "
        f"got {gamma_1_entry['avg_brier']} (argmax Brier would be {expected_brier_argmax})"
    )


# ===========================================================================
# Bug [3]: population_generator.py — Big Five means がハードコード
# ===========================================================================


class TestGenerateBigFiveUsesMeanFromConfig:
    """_generate_big_five が pop_config の big_five.mean を使うことを確認。"""

    def test_custom_high_mean_shifts_distribution_up(self):
        """pop_config で mean=0.9 を指定すると、生成値の平均が 0.8 以上になる。

        現在は mean がハードコード (0.45-0.58) のため、この範囲に収まらない。
        修正後: 設定値が反映される。
        """
        import random
        from src.app.services.society.population_generator import _generate_big_five

        random.seed(42)
        pop_config_high = {
            "big_five": {
                "mean": {"O": 0.9, "C": 0.9, "E": 0.9, "A": 0.9, "N": 0.9},
                "std": 0.05,  # 小さい std で値が mean 付近に集中
            }
        }

        samples = [_generate_big_five(pop_config_high) for _ in range(500)]
        for trait in ["O", "C", "E", "A", "N"]:
            mean_val = sum(s[trait] for s in samples) / len(samples)
            assert mean_val > 0.75, (
                f"Trait {trait}: mean {mean_val:.3f} should be > 0.75 "
                f"when configured mean=0.9 (got {mean_val:.3f})"
            )

    def test_custom_low_mean_shifts_distribution_down(self):
        """pop_config で mean=0.1 を指定すると、生成値の平均が 0.25 以下になる。"""
        import random
        from src.app.services.society.population_generator import _generate_big_five

        random.seed(123)
        pop_config_low = {
            "big_five": {
                "mean": {"O": 0.1, "C": 0.1, "E": 0.1, "A": 0.1, "N": 0.1},
                "std": 0.05,
            }
        }

        samples = [_generate_big_five(pop_config_low) for _ in range(500)]
        for trait in ["O", "C", "E", "A", "N"]:
            mean_val = sum(s[trait] for s in samples) / len(samples)
            assert mean_val < 0.25, (
                f"Trait {trait}: mean {mean_val:.3f} should be < 0.25 "
                f"when configured mean=0.1 (got {mean_val:.3f})"
            )

    def test_default_means_used_when_no_config(self):
        """pop_config に big_five 設定がない場合はデフォルト平均 (_BIG_FIVE_MEANS) を使う。"""
        import random
        from src.app.services.society.population_generator import _generate_big_five, _BIG_FIVE_MEANS

        random.seed(99)
        samples = [_generate_big_five({}) for _ in range(1000)]

        # O (index 0) のデフォルト mean = 0.45 → 平均は 0.48 以下程度
        o_mean = sum(s["O"] for s in samples) / len(samples)
        assert o_mean < 0.52, (
            f"O mean {o_mean:.3f} should be near default 0.45 when no config"
        )

    def test_per_trait_mean_applied_independently(self):
        """各 trait ごとに異なる mean が設定できる。"""
        import random
        from src.app.services.society.population_generator import _generate_big_five

        random.seed(77)
        # O だけ高い mean, N だけ低い mean
        pop_config = {
            "big_five": {
                "mean": {"O": 0.85, "C": 0.50, "E": 0.50, "A": 0.50, "N": 0.15},
                "std": 0.05,
            }
        }

        samples = [_generate_big_five(pop_config) for _ in range(500)]
        o_mean = sum(s["O"] for s in samples) / len(samples)
        n_mean = sum(s["N"] for s in samples) / len(samples)

        assert o_mean > 0.70, f"O mean {o_mean:.3f} should be > 0.70 with configured mean=0.85"
        assert n_mean < 0.30, f"N mean {n_mean:.3f} should be < 0.30 with configured mean=0.15"


# ===========================================================================
# Bug [4]: scenario_pair_status.py — queued->running の誤報
# ===========================================================================


class TestDeriveScenarioPairStatus:
    """derive_scenario_pair_status の状態マッピングが正しいことを確認。"""

    def test_queued_status_preserved(self):
        """子シミュレーションが queued 状態のとき、pair は 'queued' のまま。

        現在の実装は queued を running に折り畳んでいるバグがある。
        修正後: queued は queued として返す。
        """
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["queued", "queued"])
        assert result == "queued", (
            f"Expected 'queued' when all children are queued, got '{result}'"
        )

    def test_mixed_queued_and_created(self):
        """一方が queued、他方が created のとき、pair は 'queued'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["queued", "created"])
        assert result == "queued", (
            f"Expected 'queued', got '{result}'"
        )

    def test_running_status_returned_when_running(self):
        """子シミュレーションが running のとき、pair は 'running'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["running", "queued"])
        assert result == "running", (
            f"Expected 'running' when at least one child is running, got '{result}'"
        )

    def test_completed_status_preserved(self):
        """全ての子シミュレーションが completed のとき、pair は 'completed'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["completed", "completed"])
        assert result == "completed"

    def test_failed_status_takes_priority(self):
        """一方が failed のとき、pair は 'failed'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["failed", "running"])
        assert result == "failed"

    def test_queued_does_not_become_running_on_get(self):
        """GET 時に queued が running に書き換えられないこと。

        refresh_scenario_pair_status が呼ばれても、子シミュレーションが
        queued のままなら pair.status は queued になる。
        """
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        # queued, queued → "queued" (NOT "running")
        status = derive_scenario_pair_status(["queued", "queued"])
        assert status != "running", (
            "queued should not be reported as running (false positive)"
        )

    def test_single_queued_child(self):
        """子シミュレーションが1つだけ queued のとき、pair は 'queued'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["queued"])
        assert result == "queued"

    def test_all_running_returns_running(self):
        """全子シミュレーションが running のとき pair は 'running'。"""
        from src.app.services.scenario_pair_status import derive_scenario_pair_status

        result = derive_scenario_pair_status(["running", "running"])
        assert result == "running"


# ===========================================================================
# Bug [5]: scenario_pair_status.py — ロックなし read-modify-write
# ===========================================================================


class TestRefreshScenarioPairStatusConcurrency:
    """refresh_scenario_pair_status の楽観的ロック/CAS 保護を確認。"""

    @pytest.mark.asyncio
    async def test_completed_not_overwritten_by_stale_running(self):
        """既に completed になったペアが、遅延した running 更新で上書きされない。

        シナリオ:
        1. pair.status = "completed"
        2. DB から取得したシミュレーション状態: ["completed", "completed"]
        3. derive が "completed" を返す → pair は completed のまま

        これは楽観的ロックの基本ケース:
        derive_scenario_pair_status の結果が現在より「後退」する場合は更新しない。
        """
        from src.app.services.scenario_pair_status import (
            refresh_scenario_pair_status,
            _STATUS_RANK,
        )

        # _STATUS_RANK が存在することで「後退防止」の実装があることを検証
        assert _STATUS_RANK is not None, (
            "_STATUS_RANK dict should exist for optimistic lock protection"
        )
        # completed > running > queued > created の順序を確認
        assert _STATUS_RANK.get("completed", 0) > _STATUS_RANK.get("running", 0), (
            "completed should rank higher than running"
        )
        assert _STATUS_RANK.get("running", 0) > _STATUS_RANK.get("queued", 0), (
            "running should rank higher than queued"
        )
        assert _STATUS_RANK.get("queued", 0) > _STATUS_RANK.get("created", 0), (
            "queued should rank higher than created"
        )

    @pytest.mark.asyncio
    async def test_status_monotonically_increases(self):
        """derive_scenario_pair_status の結果が現在の status より低いランクなら更新しない。

        refresh_scenario_pair_status は status を後退させてはいけない。
        例: completed -> running への後退は禁止。
        """
        from src.app.services.scenario_pair_status import (
            derive_scenario_pair_status,
            _STATUS_RANK,
        )

        # pair が completed で、子シミュレーションが running を返す場合
        # (レースコンディション: 古いステータスが遅延して届いた)
        derived = derive_scenario_pair_status(["running", "completed"])
        current_pair_status = "completed"

        current_rank = _STATUS_RANK.get(current_pair_status, 0)
        derived_rank = _STATUS_RANK.get(derived, 0)

        # 修正後: derived_rank < current_rank なら更新しない
        should_update = derived_rank >= current_rank
        # この場合 "running" < "completed" なので更新しない
        assert not should_update, (
            f"Should not update from '{current_pair_status}' to '{derived}' "
            f"(rank regression: {current_rank} -> {derived_rank})"
        )

    @pytest.mark.asyncio
    async def test_refresh_does_not_regress_status(self):
        """refresh_scenario_pair_status が completed を running に戻さないこと。

        モックセッションで pair.status = "completed" を設定し、
        子シミュレーションのうち一方が running を返しても、
        pair.status が completed のままであることを確認。
        """
        from src.app.services.scenario_pair_status import refresh_scenario_pair_status

        # pair モック
        pair_mock = MagicMock()
        pair_mock.status = "completed"
        pair_mock.baseline_simulation_id = "sim-1"
        pair_mock.intervention_simulation_id = "sim-2"

        # sim-1 は running、sim-2 は completed
        sim1_mock = MagicMock()
        sim1_mock.status = "running"
        sim2_mock = MagicMock()
        sim2_mock.status = "completed"

        async def mock_get(model_class, obj_id):
            if obj_id == "pair-id":
                return pair_mock
            elif obj_id == "sim-1":
                return sim1_mock
            elif obj_id == "sim-2":
                return sim2_mock
            return None

        session_mock = MagicMock()
        session_mock.get = mock_get

        updated_pair = await refresh_scenario_pair_status(session_mock, "pair-id")
        assert updated_pair is not None
        # completed -> running への後退は起きない
        assert updated_pair.status == "completed", (
            f"Expected status to remain 'completed' but got '{updated_pair.status}'. "
            "Status regression (completed -> running) must be prevented."
        )
