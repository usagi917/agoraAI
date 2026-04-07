"""P4-1a: 結合分布サンプリングのテスト"""

import pytest


class TestJointDemographicsSampler:
    """IPF ベースの結合分布サンプリングテスト."""

    def test_sample_joint_demographics_returns_dict(self):
        """結合サンプリングが demographics dict を返すこと."""
        from src.app.services.society.population_generator import _sample_joint_demographics

        result = _sample_joint_demographics(seed=42)
        assert "age" in result
        assert "region" in result
        assert "gender" in result

    def test_deterministic_with_seed(self):
        """同一 seed で同じ結果を返すこと."""
        from src.app.services.society.population_generator import _sample_joint_demographics

        r1 = _sample_joint_demographics(seed=123)
        r2 = _sample_joint_demographics(seed=123)
        assert r1 == r2

    def test_region_uses_population_generator_regions(self):
        """生成される region が REGIONS に含まれること."""
        from src.app.services.society.population_generator import (
            _sample_joint_demographics,
            REGIONS,
        )

        for i in range(50):
            result = _sample_joint_demographics(seed=i)
            assert result["region"] in REGIONS

    def test_age_bracket_consistent_with_age(self):
        """age_bracket が age と整合していること."""
        from src.app.services.society.population_generator import _sample_joint_demographics

        for i in range(50):
            result = _sample_joint_demographics(seed=i)
            age = result["age"]
            bracket = result.get("age_bracket")
            if bracket:
                if age < 30:
                    assert bracket == "18-29"
                elif age < 50:
                    assert bracket == "30-49"
                elif age < 70:
                    assert bracket == "50-69"
                else:
                    assert bracket == "70+"
