# Post-Propagation Independence Re-Aggregation

## Goal

Network propagation で推定したクラスター相関を使い、activation responses を second pass で再重み付けする。
密に相関した意見の影響を割り引き、過剰に独立サンプルとして数えない最終集計を作る。

## Design Decision

- v1 の再集計対象は original `stance`
- `propagated_stance` は分析用・会議用に保持するが、v1 の最終集計には使わない
- confidence は v1 では変更しない
- 補正前後の集計は両方保存する
- Prediction Market の weighting はこのチケットでは扱わない

## Why This Design

- propagation を最終意見そのものとして採用すると、社会的影響をすでに反映したあとで independence weighting をかけることになり、同じ効果を二重に入れる可能性がある
- original `stance` を second pass で再重み付けするなら、propagation は「相関構造の推定器」として解釈できる
- まず pre/post aggregation を併存させれば、補正が本当に妥当かを比較可能にできる

## Current State

- `compute_independence_weights()` は実装済み
- `_aggregate_opinions(..., independence_weights=...)` は実装済み
- activation layer の単体テストも追加済み
- orchestrator wiring は実装済み
- pre/post observability は DB / API / SSE / frontend store まで実装済み

## Completion Status

- 2026-03-30 時点で v1 scope は完了
- activation record に pre/post aggregation を両方保持
- propagation record と simulation metadata に pre/post 比較サマリを保持
- `network_propagation_completed` SSE で post-aggregation を frontend に反映
- synthetic / API / frontend store の関連テストを追加して通過

## Formula

```python
agent i in cluster C_k:
    raw_weight_i = 1 / sqrt(cluster_size_k * avg_internal_edge_strength_k)
    singleton or no internal edges -> raw_weight = 1.0
    normalize so mean(weights) = 1.0
```

## Target Data Flow

```text
Phase A
run_activation()
  -> _aggregate_opinions(responses, agents)
  -> activation_result["aggregation"] = pre-independence aggregation

Phase B
run_network_propagation()
  -> PropagationResult(clusters, metrics)
  -> compute_independence_weights(clusters, edges, agent_ids)
  -> _aggregate_opinions(responses, agents, independence_weights=...)
  -> activation_result["aggregation_pre_independence"] = Phase A result
  -> activation_result["aggregation"] = post-independence aggregation
```

## Scope

### In Scope

- `society_orchestrator.py` で propagation 後に independence weights を計算する
- original `responses` を使って second-pass aggregation を実行する
- pre/post aggregation を両方保持する
- 補正前後の `stance_distribution` と `effective_sample_size` を比較可能にする

### Out of Scope

- `propagated_stance` ベースの最終再集計
- Prediction Market の weighted bet
- confidence の再推定
- evaluation 指標の定義変更

## Files in Scope

| File | Change |
|------|--------|
| `backend/src/app/services/society/society_orchestrator.py` | propagation 後に independence weights を計算し second-pass aggregation を実行 |
| `backend/tests/test_society_orchestrator.py` | propagation あり/なし、pre/post metadata、majority cluster discount の統合テスト追加 |
| `backend/src/app/services/society/activation_layer.py` | 基本は現状維持。必要なら pre/post metadata のキー名だけ整理 |

## Edge Cases

| Case | Behavior |
|------|----------|
| propagation 失敗 | 従来挙動のまま継続 |
| clusters が空 | 全員 weight 1.0 |
| cluster 外 agent | weight 1.0 |
| singleton cluster | weight 1.0 |
| クラスター内エッジなし | weight 1.0 |
| 全員が同一巨大クラスター | 正規化後は全員ほぼ 1.0 |

## Implementation Plan

1. orchestrator 統合テストを先に追加する
2. `PropagationResult.clusters` を `compute_independence_weights()` が受け取れる形式へ変換する
3. selected graph `edges` と `selected_agent_ids` を使って independence weights を計算する
4. original `activation_result["responses"]` を second pass で再集計する
5. `aggregation_pre_independence` を保存し、`aggregation` を補正後に差し替える
6. SSE / DB 保存で pre/post を見分けられるようにする
7. synthetic case で分布シフトと `n_eff` 低下を確認する

## Implemented Result

- `society_orchestrator.py` で propagation 後に second-pass re-aggregation を実行
- activation 保存 payload を propagation 後に更新し、pre/post aggregation を併存
- propagation 保存 payload に `aggregation_pre_independence`, `aggregation_post_independence`, `independence_re_aggregation` を追加
- final simulation metadata と `society_completed` SSE に比較サマリを追加
- frontend store は propagation 完了時に post `stance_distribution` を反映

## Success Criteria

- propagation なしでは集計結果が不変
- 密な多数派クラスターでは多数派シェアが下がる
- `effective_sample_size_post < effective_sample_size_pre`
- `activation_result["aggregation"]["independence_weighting_applied"] is True`
- pre/post aggregation を後段で比較できる

## Deferred Questions

- v2 で `propagated_stance` を最終 prediction に使うか
- independence weighting を Prediction Market にも伝播させるか
- evaluation を pre/post のどちらで実行するか
