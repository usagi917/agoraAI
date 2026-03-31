# Aggregation Flow Analysis - Updated Planning Notes

## Executive Summary

現在の実装では、独立性補正の土台そのものはすでにできている。
残っている本質的な仕事は「network propagation の結果を使って、どのタイミングで何を再集計するか」を orchestrator で定義すること。

この計画では、v1 の source of truth を original `stance` に固定する。
network propagation は最終意見を上書きするためではなく、相関構造を推定するために使う。

## Current Architecture Snapshot

### Activation Layer

- `_aggregate_opinions()` は `independence_weights` をすでに受け取れる
- population weighting と independence weighting は乗算される
- `effective_sample_size` と `stance_distribution` は最終 weights から再計算される

### Network Propagation

- `run_network_propagation()` は `PropagationResult` を返す
- `PropagationResult.clusters` は `ClusterInfo` の list
- `edges` は戻り値に含まれないため、orchestrator 側で保持して再利用する必要がある

### Orchestrator

- propagation 後、各 response に `propagated_stance` は保存される
- ただし現状の集計や評価は基本的に `stance` を読む
- したがって、second pass aggregation を orchestrator で明示的に差し込まない限り、独立性補正は最終予測に反映されない

## Recommended v1 Semantics

- 最終再集計対象は original `stance`
- `propagated_stance` は分析と会議用の補助情報として保持
- pre/post aggregation を両方保存
- Prediction Market weighting は別チケット

## Why This Is The Safer First Step

- propagation と independence weighting を両方とも最終意見へ直接使うと、social influence を二重に効かせる可能性がある
- original `stance` の second pass なら、「社会的影響で相関した回答を割り引く」という解釈が一貫する
- pre/post を同時保存すれば、効果が妥当かどうかを比較可能にできる

## Concrete Wiring Plan

1. activation 完了時点の `aggregation` を pre-independence とみなす
2. propagation 完了後に clusters と selected edges から independence weights を計算する
3. original responses を使って `_aggregate_opinions(..., independence_weights=...)` を再実行する
4. `activation_result["aggregation_pre_independence"]` に旧値を保存する
5. `activation_result["aggregation"]` を補正後へ差し替える

## Main Risks

- `ClusterInfo` と dict 形式の変換忘れ
- `stance` と `propagated_stance` の意味の混同
- SSE / DB 保存が pre/post どちらを指すか曖昧になること
- テスト環境の `pytest` 実行手順が未整備なこと

## Success Signal

- propagation なしでは挙動不変
- 密な多数派クラスターでは多数派シェアが下がる
- `effective_sample_size` が補正後に低下する
- 補正前後の集計を後から比較できる
