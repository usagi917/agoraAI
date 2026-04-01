"""Tests for distribution_metrics: shared KL divergence and EMD utilities.

Verifies:
- kl_divergence_symmetric: symmetry, identity, positivity, smoothing
- earth_movers_distance: identity, ordinal awareness, maximum distance
"""

import math
import pytest

from src.app.utils.distribution_metrics import (
    kl_divergence_symmetric,
    earth_movers_distance,
    STANCE_ORDER,
)


class TestKLDivergenceSymmetric:
    def test_identical_distributions_near_zero(self):
        """Same distribution → KL ≈ 0."""
        p = {"賛成": 0.3, "条件付き賛成": 0.2, "中立": 0.2, "条件付き反対": 0.2, "反対": 0.1}
        assert kl_divergence_symmetric(p, p) == pytest.approx(0.0, abs=0.001)

    def test_different_distributions_positive(self):
        """Different distributions → KL > 0."""
        p = {"賛成": 0.8, "反対": 0.2}
        q = {"賛成": 0.2, "反対": 0.8}
        assert kl_divergence_symmetric(p, q) > 0

    def test_symmetry(self):
        """KL(p, q) == KL(q, p)."""
        p = {"賛成": 0.6, "反対": 0.4}
        q = {"賛成": 0.3, "反対": 0.7}
        assert kl_divergence_symmetric(p, q) == pytest.approx(
            kl_divergence_symmetric(q, p), abs=1e-10
        )

    def test_smoothing_handles_zero_probability(self):
        """Zero probability in one distribution should not raise."""
        p = {"賛成": 1.0, "反対": 0.0}
        q = {"賛成": 0.5, "反対": 0.5}
        result = kl_divergence_symmetric(p, q)
        assert result > 0
        assert math.isfinite(result)

    def test_missing_keys_handled(self):
        """Keys present in one but not the other are treated as 0."""
        p = {"賛成": 1.0}
        q = {"反対": 1.0}
        result = kl_divergence_symmetric(p, q)
        assert result > 0
        assert math.isfinite(result)


class TestEarthMoversDistance:
    def test_identical_distributions_zero(self):
        """Same distribution → EMD = 0."""
        p = {s: 0.2 for s in STANCE_ORDER}
        assert earth_movers_distance(p, p) == pytest.approx(0.0, abs=1e-10)

    def test_opposite_distributions_maximum(self):
        """賛成100% vs 反対100% → maximum EMD."""
        p = {s: 0.0 for s in STANCE_ORDER}
        q = {s: 0.0 for s in STANCE_ORDER}
        p["賛成"] = 1.0
        q["反対"] = 1.0
        emd = earth_movers_distance(p, q)
        assert emd > 0

    def test_ordinal_awareness(self):
        """Adjacent stances should have smaller EMD than distant ones."""
        base = {s: 0.0 for s in STANCE_ORDER}

        p = dict(base); p["賛成"] = 1.0
        q_near = dict(base); q_near["条件付き賛成"] = 1.0
        q_far = dict(base); q_far["反対"] = 1.0

        emd_near = earth_movers_distance(p, q_near)
        emd_far = earth_movers_distance(p, q_far)
        assert emd_near < emd_far

    def test_stance_order_used(self):
        """STANCE_ORDER should have 5 elements."""
        assert len(STANCE_ORDER) == 5
