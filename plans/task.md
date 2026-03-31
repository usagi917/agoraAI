# Independence Re-Aggregation - Completed

## Status

- Completed on 2026-03-30
- original `stance` ベースの second-pass re-aggregation は実装済み
- pre/post aggregation は orchestrator, DB, API, SSE, frontend store まで反映済み
- backend / frontend の関連テストは実行済み

## Phase 0: Semantics Freeze

- [x] v1 では original `stance` を再集計対象にする
- [x] `propagated_stance` は分析用・会議用に限定する
- [x] pre/post aggregation を両方保存する方針にする
- [x] Prediction Market weighting は別チケットに切り出す

## Phase 1: Already Done

- [x] `backend/tests/test_independence_weights.py` を追加
- [x] `statistical_inference.py` に `compute_independence_weights()` を実装
- [x] `backend/tests/test_activation_layer.py` に independence weights テストを追加
- [x] `activation_layer.py:_aggregate_opinions()` に `independence_weights` を統合

## Phase 2: Orchestrator Wiring

- [x] RED: propagation 後に second-pass aggregation が走る統合テストを追加
- [x] RED: propagation なしでは aggregation が不変な統合テストを追加
- [x] GREEN: `propagation_result.clusters` を dict 形式へ変換
- [x] GREEN: `edges` と `selected_agent_ids` から independence weights を計算
- [x] GREEN: `_aggregate_opinions(..., independence_weights=...)` を second pass として再実行
- [x] GREEN: `activation_result["aggregation_pre_independence"]` を保存
- [x] GREEN: `activation_result["aggregation"]` を補正後に差し替える
- [x] REFACTOR: `_apply_independence_re_aggregation()` ヘルパーに抽出、ログ・エラーハンドリング整理

## Phase 3: Observability

- [x] SSE payload で pre/post のどちらを送るかを明確化 (`network_propagation_completed` に `aggregation` と `independence_weighting_applied` を追加)
- [x] DB 保存時に pre/post aggregation の比較ができる形にする (`independence_re_aggregation` セクションを propagation record に追加)
- [x] `independence_weighting_applied` と `effective_sample_size` が最終集計に残ることを確認
- [x] activation record に `aggregation_pre_independence` / `responses_summary_pre_independence` を保存
- [x] simulation metadata に pre/post aggregation と比較サマリを保存
- [x] propagation API で `aggregation_pre_independence` / `aggregation_post_independence` / 比較サマリを取得可能にする
- [x] propagation 完了 SSE で frontend の `opinionDistribution` を post-aggregation に更新する

## Phase 4: Verification

- [x] synthetic case で多数派密クラスターのシェアが下がることを確認
- [x] `effective_sample_size_post < effective_sample_size_pre` を確認
- [x] narrative / provenance が補正後 aggregation を読んでも壊れないことを確認
- [x] 全テスト実行手順を確認し、実行可能環境で回す
- [x] `uv run --directory backend pytest tests/test_society_orchestrator.py tests/test_activation_layer.py tests/test_independence_weights.py tests/test_society_api.py` が通る
- [x] `pnpm test:unit -- src/stores/__tests__/simulationStore.spec.ts` が通る

## Explicitly Out of Scope

- [ ] Prediction Market の weighted bet
- [ ] `propagated_stance` ベースの最終再集計
- [ ] confidence の再計算
- [ ] evaluation metric の定義変更
