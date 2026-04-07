"""精度評価の仕様定義

主指標・副指標・ホールドアウトルール・CI リグレッション閾値を定義する。
"""

# 主指標: Jensen-Shannon Divergence
PRIMARY_METRIC = "jsd"

# 副指標
SECONDARY_METRICS = {
    "brier": "Brier Score (確信度キャリブレーション)",
    "symmetric_kl": "Symmetric KL Divergence",
    "emd": "Earth Mover's Distance (Wasserstein-1)",
}

# ホールドアウトルール
HOLDOUT_RULES = {
    "split_method": "temporal",
    "min_test_cases": 5,
    "leakage_checklist": [
        "テストケースの調査日がトレーニング期間より後であること",
        "テストケースのテーマがトレーニングセットと重複しないこと",
        "人口構成パラメータが独立していること",
    ],
}

# CI リグレッション閾値: JSD がベースラインから 0.02 以上悪化で失敗
CI_REGRESSION_THRESHOLD = 0.02
