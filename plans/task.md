# Task: シミュレーション精度・堅牢性改善 (H1, H2, M1-M5)

> Plan: `plans/hashed-jumping-dijkstra.md`
> Created: 2026-03-31

---

## Phase 1: H1 — LMSR 数値オーバーフロー修正
- [x] Red: オーバーフローテスト追加 (`test_prediction_market.py`)
- [x] Green: log-sum-exp トリック適用 (`prediction_market.py`)
- [x] Refactor: 既存テスト全パス確認 (16/16 passed)

## Phase 2: H2 — Poststratification cap 後の再正規化
- [x] Red: cap 後 mean≈1.0 保証テスト追加 (`test_statistical_inference.py`)
- [x] Green: 反復正規化実装 (`statistical_inference.py`)
- [x] Refactor: 既存テスト全パス確認 (23/23 passed)

## Phase 3: M1-M2 — KL divergence / EMD の重複解消
- [x] Red: `distribution_metrics.py` 単体テスト作成
- [x] Green: 共通モジュール作成 + import 差し替え
- [x] Refactor: 重複コード削除、既存テスト全パス確認 (47/47 passed)

## Phase 4: M3 — auto_compare の冗長計算解消
- [x] Green: `best_match_source` を活用し KL 再計算削除
- [x] Refactor: 不要 import 削除、既存テスト全パス確認 (21/21 passed)

## Phase 5: M4 — Polarization Index の飽和問題修正
- [x] Red: U字型分布の polarization テスト追加
- [x] Green: 正規化分母を 0.083 → 0.25 に変更
- [x] Refactor: 既存テスト全パス確認 (20/20 passed)

## Phase 6: M5 — Stance-Opinion 変換の非対称性
- [x] Red: 低 confidence roundtrip テスト追加
- [x] Green: ドキュメントコメント追加
- [x] Refactor: 全テストスイート 845 passed
