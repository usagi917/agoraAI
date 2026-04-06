"""感度分析モジュールのテスト (TDD - RED phase)"""

import pytest
from unittest.mock import AsyncMock

# 安定したケース: 3シードとも似た分布
stable_distributions = [
    {"賛成": 0.40, "反対": 0.35, "中立": 0.10, "条件付き賛成": 0.10, "条件付き反対": 0.05},
    {"賛成": 0.42, "反対": 0.33, "中立": 0.10, "条件付き賛成": 0.10, "条件付き反対": 0.05},
    {"賛成": 0.41, "反対": 0.34, "中立": 0.10, "条件付き賛成": 0.10, "条件付き反対": 0.05},
]

# 不安定なケース: シードによって大きく変動
unstable_distributions = [
    {"賛成": 0.60, "反対": 0.20, "中立": 0.10, "条件付き賛成": 0.05, "条件付き反対": 0.05},
    {"賛成": 0.25, "反対": 0.55, "中立": 0.10, "条件付き賛成": 0.05, "条件付き反対": 0.05},
    {"賛成": 0.40, "反対": 0.30, "中立": 0.15, "条件付き賛成": 0.10, "条件付き反対": 0.05},
]

SAMPLE_AGENTS = [
    {"id": "a1", "name": "田中太郎", "age": 35, "gender": "男性", "region": "東京"},
    {"id": "a2", "name": "鈴木花子", "age": 28, "gender": "女性", "region": "大阪"},
    {"id": "a3", "name": "佐藤次郎", "age": 52, "gender": "男性", "region": "名古屋"},
]

SAMPLE_THEME = "最低賃金引き上げ"


def _make_activation_fn(distributions: list[dict]):
    """指定された distributions を順番に返す activation_fn モックを作る。"""
    call_count = 0

    async def activation_fn(agents, theme, **kwargs):
        nonlocal call_count
        dist = distributions[call_count % len(distributions)]
        call_count += 1
        return {
            "stance_distribution": dist,
            "responses": [],
        }

    return activation_fn


@pytest.mark.asyncio
async def test_sensitivity_returns_robustness_score():
    """返り値に robustness_score (0-1 float) が存在すること。"""
    from src.app.services.society.sensitivity_analysis import run_sensitivity_check

    activation_fn = _make_activation_fn(stable_distributions)
    result = await run_sensitivity_check(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        n_seeds=3,
        activation_fn=activation_fn,
    )

    assert "robustness_score" in result
    score = result["robustness_score"]
    assert isinstance(score, float), f"robustness_score must be float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"robustness_score must be in [0, 1], got {score}"


@pytest.mark.asyncio
async def test_sensitivity_returns_distributions():
    """返り値に distributions (list of dict) が存在し、n_seeds 個あること。"""
    from src.app.services.society.sensitivity_analysis import run_sensitivity_check

    n_seeds = 3
    activation_fn = _make_activation_fn(stable_distributions)
    result = await run_sensitivity_check(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        n_seeds=n_seeds,
        activation_fn=activation_fn,
    )

    assert "distributions" in result
    dists = result["distributions"]
    assert isinstance(dists, list), f"distributions must be a list, got {type(dists)}"
    assert len(dists) == n_seeds, f"Expected {n_seeds} distributions, got {len(dists)}"
    for d in dists:
        assert isinstance(d, dict), f"Each distribution must be a dict, got {type(d)}"

    assert "n_seeds" in result
    assert result["n_seeds"] == n_seeds


@pytest.mark.asyncio
async def test_sensitivity_flags_unstable():
    """unstable_distributions (分布変動>15pt) → stability が "unstable" になること。"""
    from src.app.services.society.sensitivity_analysis import run_sensitivity_check

    activation_fn = _make_activation_fn(unstable_distributions)
    result = await run_sensitivity_check(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        n_seeds=3,
        activation_fn=activation_fn,
    )

    assert "stability" in result
    assert result["stability"] == "unstable", (
        f"Expected 'unstable' but got '{result['stability']}'. "
        f"max_deviation={result.get('max_deviation')}"
    )


@pytest.mark.asyncio
async def test_sensitivity_passes_stable():
    """stable_distributions (分布変動<5pt) → stability が "stable" になること。"""
    from src.app.services.society.sensitivity_analysis import run_sensitivity_check

    activation_fn = _make_activation_fn(stable_distributions)
    result = await run_sensitivity_check(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        n_seeds=3,
        activation_fn=activation_fn,
    )

    assert "stability" in result
    assert result["stability"] == "stable", (
        f"Expected 'stable' but got '{result['stability']}'. "
        f"max_deviation={result.get('max_deviation')}"
    )


@pytest.mark.asyncio
async def test_sensitivity_max_deviation():
    """返り値に max_deviation (各スタンスの最大標準偏差) が存在すること。"""
    from src.app.services.society.sensitivity_analysis import run_sensitivity_check

    activation_fn = _make_activation_fn(stable_distributions)
    result = await run_sensitivity_check(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        n_seeds=3,
        activation_fn=activation_fn,
    )

    assert "max_deviation" in result
    dev = result["max_deviation"]
    assert isinstance(dev, float), f"max_deviation must be float, got {type(dev)}"
    assert dev >= 0.0, f"max_deviation must be non-negative, got {dev}"


# ===== Phase C: Provider-mix ensemble テスト =====

# プロバイダごとに異なる分布を返すモック
provider_distributions = {
    "openai": {"賛成": 0.35, "反対": 0.30, "中立": 0.15, "条件付き賛成": 0.10, "条件付き反対": 0.10},
    "anthropic": {"賛成": 0.40, "反対": 0.25, "中立": 0.15, "条件付き賛成": 0.12, "条件付き反対": 0.08},
    "google": {"賛成": 0.38, "反対": 0.28, "中立": 0.14, "条件付き賛成": 0.11, "条件付き反対": 0.09},
}


def _make_provider_activation_fn(provider_dists: dict[str, dict]):
    """プロバイダ名に応じて異なる分布を返す activation_fn モック。"""
    async def activation_fn(agents, theme, **kwargs):
        provider = kwargs.get("provider", "openai")
        dist = provider_dists.get(provider, list(provider_dists.values())[0])
        return {
            "stance_distribution": dist,
            "responses": [],
        }
    return activation_fn


@pytest.mark.asyncio
async def test_ensemble_returns_ensemble_distribution():
    """返り値に ensemble_distribution (合計≈1.0 の dict) が存在すること。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_provider_activation_fn(provider_distributions)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic", "google"],
        activation_fn=activation_fn,
    )

    assert "ensemble_distribution" in result
    dist = result["ensemble_distribution"]
    assert isinstance(dist, dict)
    assert sum(dist.values()) == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_ensemble_returns_provider_distributions():
    """返り値に各プロバイダの分布が含まれること。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_provider_activation_fn(provider_distributions)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic"],
        activation_fn=activation_fn,
    )

    assert "provider_distributions" in result
    assert len(result["provider_distributions"]) == 2


@pytest.mark.asyncio
async def test_ensemble_returns_agreement_score():
    """返り値に agreement_score (0-1) が存在すること。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_provider_activation_fn(provider_distributions)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic", "google"],
        activation_fn=activation_fn,
    )

    assert "agreement_score" in result
    score = result["agreement_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_ensemble_returns_weights():
    """返り値に provider weights が存在すること。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_provider_activation_fn(provider_distributions)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai", "anthropic"],
        activation_fn=activation_fn,
    )

    assert "weights" in result
    weights = result["weights"]
    assert len(weights) == 2
    assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_ensemble_single_provider_returns_its_distribution():
    """プロバイダ1つの場合、そのプロバイダの分布がそのまま返る。"""
    from src.app.services.society.sensitivity_analysis import run_provider_ensemble

    activation_fn = _make_provider_activation_fn(provider_distributions)
    result = await run_provider_ensemble(
        agents=SAMPLE_AGENTS,
        theme=SAMPLE_THEME,
        providers=["openai"],
        activation_fn=activation_fn,
    )

    ensemble = result["ensemble_distribution"]
    expected = provider_distributions["openai"]
    for stance, prob in expected.items():
        assert ensemble[stance] == pytest.approx(prob, abs=0.01)
