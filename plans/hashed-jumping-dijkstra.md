# Plan: シミュレーション精度・堅牢性改善 (H1, H2, M1-M5)

## Context

アーキテクトレビューにより、シミュレーションモジュール群に以下の問題が特定された:
- **H1**: LMSR 予測市場の `math.exp()` が大規模シミュレーションでオーバーフローするリスク
- **H2**: 事後層化ウェイトの cap 適用後に再正規化が行われず mean≠1.0 になる
- **M1-M2**: KL divergence / EMD が `survey_anchor.py` と `validation_repo.py` に重複実装
- **M3**: `validation_pipeline.py` の `auto_compare` で KL divergence を冗長に再計算
- **M4**: Polarization Index が U字型分布で飽和し極端な二極化を区別できない
- **M5**: Stance-Opinion 変換で低 confidence の roundtrip が非対称（ドキュメント・テスト不足）

TDD (Red → Green → Refactor) で進める。

---

## Phase 1: H1 — LMSR 数値オーバーフロー修正

### 対象ファイル
- `backend/src/app/services/society/prediction_market.py` (行44-49)
- `backend/tests/test_prediction_market.py`

### 変更内容
`get_prices()` に log-sum-exp トリックを導入:

```python
def get_prices(self) -> dict[str, float]:
    b = self._liquidity
    max_q = max(self._quantities.values())
    exp_vals = {o: math.exp((q - max_q) / b) for o, q in self._quantities.items()}
    total = sum(exp_vals.values())
    return {o: v / total for o, v in exp_vals.items()}
```

### TDD
- **Red**: 極端な量でオーバーフローしないテストを追加 (`q=10000` 等)
- **Green**: log-sum-exp トリック適用
- **Refactor**: 既存テスト全パス確認

---

## Phase 2: H2 — Poststratification cap 後の再正規化

### 対象ファイル
- `backend/src/app/services/society/statistical_inference.py` (行256-262)
- `backend/tests/test_statistical_inference.py`

### 変更内容
cap 適用と正規化を反復して mean=1.0 を保証:

```python
# 正規化 + cap を収束するまで反復
for _ in range(10):
    mean_w = sum(weights) / n
    if mean_w > 0:
        weights = [w / mean_w for w in weights]
    capped = [min(w, cap) for w in weights]
    if capped == weights:
        break
    weights = capped
```

### TDD
- **Red**: cap 適用後も `mean(weights) ≈ 1.0` を保証するテストを追加
- **Green**: 反復正規化を実装
- **Refactor**: 既存テスト全パス確認

---

## Phase 3: M1-M2 — KL divergence / EMD の重複解消

### 対象ファイル
- 新規: `backend/src/app/utils/__init__.py`
- 新規: `backend/src/app/utils/distribution_metrics.py`
- `backend/src/app/services/society/survey_anchor.py` (行163-205)
- `backend/src/app/repositories/validation_repo.py` (行13-55)
- `backend/src/app/services/society/validation_pipeline.py` (行23)

### 変更内容
1. `distribution_metrics.py` に以下を配置 (`survey_anchor.py` から移動):
   - `kl_divergence_symmetric()`
   - `earth_movers_distance()`
   - `STANCE_ORDER` 定数 (constants.py から re-export)
2. `survey_anchor.py`: import 元を `distribution_metrics` に変更
3. `validation_repo.py`: private 関数 `_kl_divergence_symmetric`, `_earth_movers_distance`, `STANCE_ORDER` を削除し `distribution_metrics` から import
4. `validation_pipeline.py`: import パスを `distribution_metrics` に変更

### レイヤー設計の根拠
`validation_repo.py` は「service 層に依存しないよう自己完結」の方針だったが、KL/EMD は純粋な数学関数。`app/utils/` はどの層からも参照可能な中立的な位置で、層の依存関係ルールを破らない。

### TDD
- **Red**: `distribution_metrics.py` の単体テスト（既存の振る舞いと同等）
- **Green**: 関数を移動し import を差し替え
- **Refactor**: 既存テスト全パス確認、validation_repo の private 関数を削除

---

## Phase 4: M3 — auto_compare の冗長な KL 再計算を解消

### 対象ファイル
- `backend/src/app/services/society/validation_pipeline.py` (行72-79)

### 変更内容
`compare_with_surveys` が返す `best_match_source` と `per_survey_deviations` を活用し、KL divergence の再計算を削除:

```python
# Before (冗長): kl_divergence_symmetric を再計算して best_survey を選択
best_survey = min(
    report["matched_surveys"],
    key=lambda survey: kl_divergence_symmetric(
        record.simulated_distribution,
        survey["stance_distribution"],
    ),
)

# After: compare_with_surveys が返す best_match_source を使用
best_survey = next(
    s for s in report["matched_surveys"]
    if s["source"] == report["best_match_source"]
)
```

### TDD
- **Red**: 不要（既存テストで auto_compare の振る舞いがカバー済み）
- **Green**: 冗長計算を削除
- **Refactor**: `kl_divergence_symmetric` の import が不要になった場合は削除

---

## Phase 5: M4 — Polarization Index の飽和問題修正

### 対象ファイル
- `backend/src/app/services/society/network_propagation.py` (行208-210)
- `backend/tests/test_network_propagation.py`

### 変更内容
正規化の分母を `1/12 ≈ 0.083` (均一分布) から `0.25` (Bernoulli 最大分散) に変更:

```python
# Before: uniform [0,1] の分散 1/12 で正規化 → U字型で飽和
polarization = min(variance / 0.083, 1.0)

# After: Bernoulli 最大分散 0.25 で正規化 → 二極化の程度を正確に反映
polarization = min(variance / 0.25, 1.0)
```

### TDD
- **Red**: U字型分布（例: 半数が0.0、半数が1.0）で polarization < 1.0 にならず正確に区別できるテスト
- **Green**: 分母を 0.25 に変更
- **Refactor**: 既存テストの期待値を調整（homophily テストの polarization_index 値が変わる可能性）

---

## Phase 6: M5 — Stance-Opinion 変換の非対称性ドキュメント化 + テスト

### 対象ファイル
- `backend/src/app/services/society/network_propagation.py` (行50-64)
- `backend/tests/test_network_propagation.py`

### 変更内容
1. `_convert_stance_to_opinion` にドキュメントコメント追加:
   - confidence が低い場合、極端なスタンス（賛成/反対）が中央方向に圧縮される設計意図を明記
   - 例: stance="賛成", confidence=0.3 → opinion=0.62 → "条件付き賛成"
2. 低 confidence の roundtrip テストを追加

### TDD
- **Red**: `confidence=0.3` での roundtrip が "賛成"→"条件付き賛成" になることを明示的にテスト
- **Green**: テストをパスするドキュメントコメント（コード変更なし、テストが意図的挙動を確認）
- **Refactor**: テストクラスの整理

---

## 検証

```bash
cd backend && uv run pytest tests/test_prediction_market.py tests/test_statistical_inference.py tests/test_network_propagation.py tests/test_validation_pipeline.py tests/test_survey_anchor.py -v
```

全テスト（既存 + 新規）がパスすること。
