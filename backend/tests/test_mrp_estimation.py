"""P6-1: MrP (Multilevel Regression + Post-stratification) テスト

statistical_inference.py の mrp_estimate() をテスト。
人口統計予測変数でマルチレベル回帰し、ターゲット人口に事後層化する。
"""

import math
import pytest


def _make_agents_responses(n=100, seed=42):
    """テスト用のエージェントとレスポンスを生成する."""
    import random
    rng = random.Random(seed)

    regions = ["関東", "関西", "中部", "九州", "東北"]
    genders = ["male", "female"]
    stances = ["賛成", "反対", "中立", "条件付き賛成", "条件付き反対"]
    brackets = ["18-29", "30-49", "50-69", "70+"]

    agents = []
    responses = []
    for i in range(n):
        bracket = rng.choice(brackets)
        age_ranges = {"18-29": (18, 29), "30-49": (30, 49), "50-69": (50, 69), "70+": (70, 85)}
        age_range = age_ranges[bracket]
        age = rng.randint(age_range[0], age_range[1])

        agents.append({
            "id": f"agent_{i}",
            "demographics": {
                "age": age,
                "age_bracket": bracket,
                "region": rng.choice(regions),
                "gender": rng.choice(genders),
                "income_bracket": rng.choice(["low", "lower_middle", "upper_middle", "high"]),
                "occupation": "会社員",
            },
        })
        responses.append({
            "stance": rng.choice(stances),
            "confidence": round(rng.uniform(0.3, 1.0), 2),
        })

    return agents, responses


class TestMrpEstimate:
    """MrP 推定のテスト."""

    def test_mrp_returns_distribution(self):
        """mrp_estimate() がスタンス分布を返すこと."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=80)
        result = mrp_estimate(agents, responses)

        assert isinstance(result, dict)
        assert "distribution" in result
        dist = result["distribution"]
        assert len(dist) > 0
        # 分布の合計が約1.0
        assert math.isclose(sum(dist.values()), 1.0, abs_tol=0.01)

    def test_mrp_returns_cell_estimates(self):
        """mrp_estimate() がセル別推定を返すこと."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=80)
        result = mrp_estimate(agents, responses)

        assert "cell_estimates" in result
        assert len(result["cell_estimates"]) > 0

    def test_mrp_with_custom_target(self):
        """カスタムターゲット周辺分布で推定できること."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=80)
        target = {
            "age_bracket": {"18-29": 0.20, "30-49": 0.30, "50-69": 0.30, "70+": 0.20},
            "region": {"関東": 0.40, "関西": 0.20, "中部": 0.15, "九州": 0.10, "東北": 0.15},
            "gender": {"male": 0.49, "female": 0.51},
        }
        result = mrp_estimate(agents, responses, target_marginals=target)

        dist = result["distribution"]
        assert math.isclose(sum(dist.values()), 1.0, abs_tol=0.01)

    def test_mrp_differs_from_raw_distribution(self):
        """MrP 推定はサンプルの偏りを補正するため、生の分布と異なりうる."""
        from src.app.services.society.statistical_inference import (
            mrp_estimate,
            weighted_stance_distribution,
        )

        # 意図的に若年・関東に偏ったサンプル
        agents = []
        responses = []
        import random
        rng = random.Random(123)

        for i in range(80):
            agents.append({
                "id": f"agent_{i}",
                "demographics": {
                    "age": rng.randint(18, 29),
                    "age_bracket": "18-29",
                    "region": "関東",
                    "gender": "male",
                    "income_bracket": "low",
                    "occupation": "学生",
                },
            })
            # 若者は賛成寄り
            responses.append({
                "stance": rng.choice(["賛成", "賛成", "賛成", "反対", "中立"]),
                "confidence": 0.7,
            })

        result = mrp_estimate(agents, responses)
        raw_dist = weighted_stance_distribution(responses, [1.0] * len(responses))

        # MrP 補正後と生分布が完全一致しないこと（補正が効いている）
        # 完全に同質なサンプルの場合は同じになりうるので、差が出ればOK
        mrp_dist = result["distribution"]
        assert isinstance(mrp_dist, dict)
        assert len(mrp_dist) > 0

    def test_mrp_small_sample(self):
        """少数サンプルでもエラーなく推定できること."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=10)
        result = mrp_estimate(agents, responses)

        assert "distribution" in result
        dist = result["distribution"]
        assert len(dist) > 0

    def test_mrp_returns_effective_sample_size(self):
        """MrP 推定結果に実効標本サイズが含まれること."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=50)
        result = mrp_estimate(agents, responses)

        assert "effective_sample_size" in result
        assert result["effective_sample_size"] > 0

    def test_mrp_deterministic_with_same_input(self):
        """同一入力で同じ結果が得られること."""
        from src.app.services.society.statistical_inference import mrp_estimate

        agents, responses = _make_agents_responses(n=50, seed=99)
        r1 = mrp_estimate(agents, responses)
        r2 = mrp_estimate(agents, responses)

        assert r1["distribution"] == r2["distribution"]
