# agentAI 学術リファクタリング TDD タスクリスト v2

> 各タスクは RED → GREEN → REFACTOR のサイクルで実行する。
> テスト名は `test_{method}_{scenario}_{expected}` 形式に統一。

---

## Phase 0: 基盤整備

### 0.1 テスト環境確認
- [ ] `uv run pytest --tb=short -q` で全39テストファイル実行
- [ ] 失敗テストをリストアップ
- [ ] 各失敗テストの原因分析・修正
- [ ] 全テスト GREEN 確認

### 0.2 カバレッジベースライン
- [ ] `pyproject.toml` に `pytest-cov` 追加 (`uv add --dev pytest-cov`)
- [ ] `uv run pytest --cov=src/app --cov-report=term-missing` 実行
- [ ] カバレッジ率を記録（現在値: ____%）
- [ ] カバレッジ 0% モジュールをリストアップ

### 0.3 テストヘルパー整備
- [ ] RED: `tests/test_factories.py` — ファクトリ関数の型テスト作成
  - [ ] `test_make_simulation__returns_simulation_instance`
  - [ ] `test_make_simulation__default_mode_unified`
  - [ ] `test_make_agent_profile__returns_profile`
  - [ ] `test_make_kg_node__has_required_fields`
  - [ ] `test_make_llm_response__returns_tuple`
- [ ] GREEN: `tests/factories.py` 実装
  - [ ] `make_simulation()` 関数
  - [ ] `make_agent_profile()` 関数
  - [ ] `make_kg_node()` / `make_kg_edge()` 関数
  - [ ] `make_evaluation_result()` 関数
  - [ ] `make_llm_response()` 関数
  - [ ] `make_society_pulse_result()` 関数
  - [ ] `make_council_result()` 関数
- [ ] テスト GREEN 確認

### 0.4 Alembic 導入
- [ ] `uv add alembic` 実行
- [ ] `cd backend && alembic init alembic` 実行
- [ ] `alembic/env.py` を async engine 対応に書き換え
- [ ] RED: `tests/test_alembic.py` 作成
  - [ ] `test_alembic_upgrade__succeeds`
  - [ ] `test_alembic_downgrade__succeeds`
  - [ ] `test_alembic_heads__single_head`
- [ ] GREEN: 初期マイグレーション生成 (`alembic revision --autogenerate`)
- [ ] テスト GREEN 確認

### 0.5 ブランチ作成
- [ ] `git checkout -b refactor/v2` 実行
- [ ] Phase 0 の成果をコミット

---

## Phase 1: 実行モード統合

### 1.1 Simulation.mode バリデーション変更
- [ ] RED: `tests/test_simulation_model.py` 作成
  - [ ] `test_mode__unified__accepted`
  - [ ] `test_mode__single__accepted`
  - [ ] `test_mode__baseline__accepted`
  - [ ] `test_mode__pipeline__remaps_to_unified`
  - [ ] `test_mode__swarm__remaps_to_unified`
  - [ ] `test_mode__hybrid__remaps_to_unified`
  - [ ] `test_mode__pm_board__remaps_to_unified`
  - [ ] `test_mode__society__remaps_to_unified`
  - [ ] `test_mode__society_first__remaps_to_unified`
  - [ ] `test_mode__meta_simulation__remaps_to_unified`
  - [ ] `test_mode__unknown__raises_value_error`
- [ ] GREEN: `models/simulation.py` に `@validates('mode')` 追加
  - [ ] `MODE_ALIASES` 定数を定義
  - [ ] バリデータで旧モード → 新モードにリマップ
- [ ] REFACTOR: `MODE_ALIASES` を `models/constants.py` に切り出し
- [ ] テスト全 GREEN 確認

### 1.2 simulation_dispatcher.py ルーティング削減
- [ ] RED: `tests/test_simulation_dispatcher.py` 書き直し
  - [ ] `test_dispatch__unified__calls_run_unified`
  - [ ] `test_dispatch__single__calls_run_simulation`
  - [ ] `test_dispatch__baseline__calls_run_baseline`
  - [ ] `test_dispatch__invalid_mode__raises_error`
  - [ ] `test_dispatch__missing_simulation__raises_error`
  - [ ] `test_dispatch__unified__publishes_start_event`
  - [ ] `test_dispatch__failure__publishes_error_event`
  - [ ] `test_dispatch__failure__sets_status_failed`
  - [ ] `test_ensure_project__existing__returns_id`
  - [ ] `test_ensure_project__no_project__creates_new`
  - [ ] `test_ensure_project__prompt_text_propagation`
- [ ] GREEN: `simulation_dispatcher.py` を3モード分岐に書き直し
  - [ ] `pipeline` 分岐削除
  - [ ] `meta_simulation` 分岐削除
  - [ ] `society` 分岐削除
  - [ ] `society_first` 分岐削除
  - [ ] `swarm` 分岐削除
  - [ ] `hybrid` 分岐削除
  - [ ] `pm_board` 分岐削除
  - [ ] `unified` 分岐を維持
  - [ ] `single` 分岐を維持
  - [ ] `baseline` 分岐を新規追加
  - [ ] `_dispatch_single()` ヘルパー削除
  - [ ] `_dispatch_swarm()` ヘルパー削除
  - [ ] `_dispatch_pm_board()` ヘルパー削除
- [ ] REFACTOR: 不要 import の除去
- [ ] テスト全 GREEN 確認

### 1.3 不要オーケストレータの削除
- [ ] RED: `tests/test_no_stale_imports.py` 作成
  - [ ] `test_codebase__no_import_pipeline_orchestrator`
  - [ ] `test_codebase__no_import_swarm_orchestrator`
  - [ ] `test_codebase__no_import_pm_board_orchestrator`
  - [ ] `test_codebase__no_import_meta_orchestrator`
  - [ ] `test_codebase__no_import_society_first_orchestrator`
  - [ ] `test_codebase__no_import_colony_factory`
  - [ ] `test_codebase__no_import_claim_extractor`
  - [ ] `test_codebase__no_import_claim_clusterer`
- [ ] GREEN: 参照元の import を全除去
  - [ ] `simulation_dispatcher.py` の旧 import 除去
  - [ ] `__init__.py` の旧 export 除去
  - [ ] その他の参照ファイルの import 除去
- [ ] ファイル削除実行
  - [ ] `services/pipeline_orchestrator.py` 削除
  - [ ] `services/swarm_orchestrator.py` 削除
  - [ ] `services/pm_board_orchestrator.py` 削除
  - [ ] `services/meta_orchestrator.py` 削除
  - [ ] `services/society_first_orchestrator.py` 削除
  - [ ] `services/meta_intervention_planner.py` 削除
  - [ ] `services/swarm_report_generator.py` 削除
  - [ ] `services/colony_factory.py` 削除
  - [ ] `services/claim_extractor.py` 削除
  - [ ] `services/claim_clusterer.py` 削除
  - [ ] `services/final_report_generator.py` 削除
  - [ ] `services/pipeline_fallbacks.py` 削除
  - [ ] `services/aggregator.py` 削除（存在すれば）
- [ ] テスト削除
  - [ ] `tests/test_pipeline_orchestrator.py` 削除
  - [ ] `tests/test_swarm_orchestrator.py` 削除
- [ ] テスト全 GREEN 確認

### 1.4 unified_orchestrator.py の PM Board 統合
- [ ] RED: `tests/test_unified_orchestrator.py` 作成
  - [ ] `test_run_unified__completes_3_phases`
  - [ ] `test_run_unified__saves_result_to_metadata_json`
  - [ ] `test_run_unified__sets_status_completed`
  - [ ] `test_run_unified__publishes_phase_change_events`
  - [ ] `test_run_unified__with_pm_analysis__includes_pm_section`
  - [ ] `test_run_unified__without_pm_analysis__no_pm_section`
  - [ ] `test_run_unified__error_in_pulse__sets_failed`
- [ ] RED: `tests/test_synthesis.py` 作成
  - [ ] `test_run_synthesis__returns_decision_brief`
  - [ ] `test_run_synthesis__agreement_score_between_0_and_1`
  - [ ] `test_run_synthesis__with_pm__includes_pm_perspective`
  - [ ] `test_compute_agreement_score__balanced__midrange`
  - [ ] `test_compute_agreement_score__full_consensus__high`
  - [ ] `test_compute_agreement_score__no_data__zero`
- [ ] GREEN: `unified_orchestrator.py` に `use_pm_analysis` 追加
- [ ] GREEN: `synthesis.py` に PM 視点統合ロジック追加
- [ ] テスト全 GREEN 確認

### 1.5 single モードの簡素化
- [ ] RED: `tests/test_simulator.py` 拡張
  - [ ] `test_init__no_colony_config__defaults`
  - [ ] `test_run__minimal_input__returns_result`
  - [ ] `test_run__preview_profile__2_rounds`
  - [ ] `test_run__standard_profile__4_rounds`
  - [ ] `test_run_simulation__success__sets_completed`
  - [ ] `test_run_simulation__failure__sets_failed`
  - [ ] `test_run_simulation__return_result_true__returns_dict`
  - [ ] `test_run_simulation__return_result_false__returns_none`
- [ ] GREEN: `simulator.py` から Colony 関連ロジック除去
  - [ ] `SingleRunSimulator.__init__()` から `colony_config` 削除
  - [ ] `_inject_perspective()` メソッド削除
  - [ ] Colony 関連 import 除去
- [ ] テスト全 GREEN 確認

### 1.6 baseline モードの新設
- [ ] RED: `tests/test_baseline_orchestrator.py` 作成
  - [ ] `test_run_baseline__returns_result`
  - [ ] `test_run_baseline__result_format_matches_unified`
  - [ ] `test_run_baseline__uses_single_llm_call`
  - [ ] `test_run_baseline__no_agents_created`
  - [ ] `test_run_baseline__saves_to_metadata_json`
  - [ ] `test_run_baseline__sets_status_completed`
  - [ ] `test_run_baseline__same_seed_same_result`
  - [ ] `test_run_baseline__different_seed_different_result`
  - [ ] `test_run_baseline__seed_stored_in_simulation`
- [ ] GREEN: `services/baseline_orchestrator.py` 新規作成
  - [ ] `async def run_baseline(simulation_id: str) -> None`
  - [ ] シード固定ロジック
  - [ ] 単一LLMプロンプト分析
  - [ ] 結果を unified 互換フォーマットで保存
- [ ] テスト全 GREEN 確認
- [ ] Phase 1 完了: `uv run pytest --cov` で全テスト GREEN 確認

---

## Phase 2: DB モデル統合

### 2.1 新モデル追加（非破壊的）
- [ ] RED: `tests/test_new_models.py` 作成
  - [ ] `test_llm_call_log__create_minimal__saved`
  - [ ] `test_llm_call_log__create_full_fields__saved`
  - [ ] `test_llm_call_log__query_by_simulation_id`
  - [ ] `test_llm_call_log__query_by_task_name`
  - [ ] `test_llm_call_log__latency_ms_positive`
  - [ ] `test_experiment_config__create__saved`
  - [ ] `test_experiment_config__yaml_configs_serialized`
  - [ ] `test_experiment_config__package_versions_recorded`
  - [ ] `test_experiment_config__restore__returns_original`
- [ ] GREEN: `models/llm_call_log.py` 新規作成
- [ ] GREEN: `models/experiment_config.py` 新規作成
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認

### 2.2 Simulation モデルのフィールド追加
- [ ] RED: `tests/test_simulation_model.py` 拡張
  - [ ] `test_name__default_empty`
  - [ ] `test_description__default_empty`
  - [ ] `test_input_documents__stores_json_list`
  - [ ] `test_seed__stores_integer`
  - [ ] `test_seed__auto_generated_when_none`
  - [ ] `test_config_snapshot_id__references_experiment_config`
- [ ] GREEN: `models/simulation.py` にフィールド追加
  - [ ] `name: str`
  - [ ] `description: str`
  - [ ] `input_documents: dict`
  - [ ] `seed: int | None`
  - [ ] `config_snapshot_id: str | None`
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認

### 2.3 Repository レイヤー導入
- [ ] RED: `tests/test_repositories.py` 作成 — SimulationRepository
  - [ ] `test_sim_repo__create__returns_simulation`
  - [ ] `test_sim_repo__get_by_id__found`
  - [ ] `test_sim_repo__get_by_id__not_found__returns_none`
  - [ ] `test_sim_repo__list__ordered_by_created_at`
  - [ ] `test_sim_repo__update_status__changes_status`
  - [ ] `test_sim_repo__save_result__stores_metadata_json`
  - [ ] `test_sim_repo__get_with_report__includes_data`
- [ ] GREEN: `repositories/simulation_repo.py` 実装
- [ ] テスト GREEN 確認

- [ ] RED: `tests/test_repositories.py` 拡張 — AgentRepository
  - [ ] `test_agent_repo__save_profiles__stores_batch`
  - [ ] `test_agent_repo__get_by_simulation__returns_list`
  - [ ] `test_agent_repo__save_state__creates_agent_state`
  - [ ] `test_agent_repo__get_states_by_round__filters`
- [ ] GREEN: `repositories/agent_repo.py` 実装
- [ ] テスト GREEN 確認

- [ ] RED: `tests/test_repositories.py` 拡張 — KGRepository
  - [ ] `test_kg_repo__save_nodes__batch_insert`
  - [ ] `test_kg_repo__save_edges__with_references`
  - [ ] `test_kg_repo__get_graph__returns_nodes_and_edges`
  - [ ] `test_kg_repo__get_graph_history__returns_snapshots`
- [ ] GREEN: `repositories/kg_repo.py` 実装
- [ ] テスト GREEN 確認

- [ ] RED: `tests/test_repositories.py` 拡張 — EvaluationRepository
  - [ ] `test_eval_repo__save_metrics__batch_insert`
  - [ ] `test_eval_repo__get_by_simulation__returns_all`
  - [ ] `test_eval_repo__get_by_metric_name__filters`
- [ ] GREEN: `repositories/evaluation_repo.py` 実装
- [ ] テスト GREEN 確認

### 2.4 オーケストレータの Repository 移行
- [ ] `unified_orchestrator.py` の DB 直接操作を `SimulationRepository` 経由に置換
- [ ] `simulator.py` の DB 直接操作を Repository 経由に置換
- [ ] 既存テスト全 GREEN 確認（回帰なし）

### 2.5 旧モデル段階的削除

#### Step A: Colony → Swarm → Run 削除
- [ ] RED: 削除後の Repository テストが通ることを確認するテスト追加
- [ ] Colony モデルへの全参照を除去
- [ ] Colony モデルファイル削除
- [ ] Swarm モデルへの全参照を除去
- [ ] Swarm モデルファイル削除
- [ ] Run モデルへの全参照を除去
- [ ] Run モデルファイル削除
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認

#### Step B: Project → Document 統合
- [ ] Simulation の `input_documents` に Document データを移行する処理確認
- [ ] Project モデルへの全参照を除去
- [ ] Project モデルファイル削除
- [ ] Document モデルへの全参照を除去
- [ ] Document モデルファイル削除
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認

#### Step C: WorldState, GraphState, GraphDiff 統合
- [ ] WorldState の機能を Simulation.metadata_json に統合
- [ ] GraphState → KGNode/KGEdge のスナップショットに統合
- [ ] WorldState, GraphState, GraphDiff モデル削除
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認

#### Step D: Report → SocietyResult 統合
- [ ] Report の内容を SocietyResult に統合
- [ ] Report モデル削除
- [ ] テスト全 GREEN 確認

#### Step E: その他の不要モデル削除
- [ ] CalibrationData → EvaluationResult に統合して削除
- [ ] OutcomeClaim, ClaimCluster, AggregationResult 削除
- [ ] Followup → ConversationLog 統合して削除
- [ ] SocialEdge 削除
- [ ] Community → KGNode 属性に統合して削除
- [ ] EnvironmentRule 削除
- [ ] EvaluationScore → EvaluationResult 統合して削除
- [ ] TimelineEvent → ConversationLog 統合して削除
- [ ] Alembic マイグレーション生成
- [ ] テスト全 GREEN 確認
- [ ] Phase 2 完了: 残モデル数 ≤ 12 を確認

---

## Phase 3: 学術機能の追加

### 3.1 シード制御
- [ ] RED: `tests/test_reproducibility.py` 作成
  - [ ] `test_set_global_seed__deterministic_random`
  - [ ] `test_set_global_seed__deterministic_numpy`
  - [ ] `test_generate_seed__returns_positive_int`
  - [ ] `test_generate_seed__within_32bit_range`
- [ ] GREEN: `services/reproducibility.py` 新規作成
  - [ ] `set_global_seed(seed: int)` 実装
  - [ ] `generate_seed() -> int` 実装
- [ ] テスト GREEN 確認

### 3.2 設定スナップショット
- [ ] RED: `tests/test_reproducibility.py` 拡張
  - [ ] `test_take_snapshot__captures_all_yamls`
  - [ ] `test_take_snapshot__captures_package_versions`
  - [ ] `test_take_snapshot__captures_git_hash`
  - [ ] `test_restore_snapshot__matches_original`
- [ ] GREEN: `services/reproducibility.py` に追加
  - [ ] `take_config_snapshot()` 実装
  - [ ] `restore_config_snapshot()` 実装
- [ ] テスト GREEN 確認

### 3.3 決定論的実行モード
- [ ] RED: `tests/test_reproducibility.py` 拡張
  - [ ] `test_deterministic_mode__llm_temperature_zero`
  - [ ] `test_deterministic_mode__seed_passed_to_llm`
  - [ ] `test_deterministic_mode__same_seed_same_order`
- [ ] GREEN: dispatcher にデターミニスティックフラグ統合
- [ ] テスト GREEN 確認

### 3.4 BaseMetric 抽象基底クラス
- [ ] RED: `tests/test_evaluation_metrics.py` 作成
  - [ ] `test_base_metric__abstract__cannot_instantiate`
  - [ ] `test_base_metric__concrete__must_implement_compute`
  - [ ] `test_metric_result__has_name_score_details`
  - [ ] `test_metric_result__score_between_0_and_1`
  - [ ] `test_metric_result__to_dict`
- [ ] GREEN: `services/evaluation/base.py` 新規作成
  - [ ] `MetricResult` dataclass
  - [ ] `BaseMetric` ABC
- [ ] テスト GREEN 確認

### 3.5 既存メトリクス移行（society → evaluation/）
- [ ] RED: `tests/test_evaluation_metrics.py` 拡張
  - [ ] `test_diversity__uniform__max_entropy`
  - [ ] `test_diversity__single_stance__zero`
  - [ ] `test_diversity__empty__zero`
  - [ ] `test_diversity__returns_metric_result`
  - [ ] `test_consistency__aligned__high`
  - [ ] `test_consistency__misaligned__low`
  - [ ] `test_consistency__empty__zero`
  - [ ] `test_calibration__perfect__one`
  - [ ] `test_calibration__poor__low`
  - [ ] `test_brier__perfect_forecast__one`
  - [ ] `test_brier__random_forecast__mid`
  - [ ] `test_kl_divergence__same_dist__zero`
  - [ ] `test_kl_divergence__diff_dist__positive`
- [ ] GREEN: `services/evaluation/society_metrics.py` 新規作成
  - [ ] `DiversityMetric(BaseMetric)` 実装
  - [ ] `ConsistencyMetric(BaseMetric)` 実装
  - [ ] `CalibrationMetric(BaseMetric)` 実装
  - [ ] `BrierMetric(BaseMetric)` 実装
  - [ ] `KLDivergenceMetric(BaseMetric)` 実装
- [ ] REFACTOR: `society/evaluation.py` を新クラスへの委譲に書き換え
- [ ] テスト全 GREEN 確認（既存テストも含む）

### 3.6 KG 品質メトリクス
- [ ] RED: `tests/test_kg_metrics.py` 作成
  - [ ] `test_kg_precision__all_correct__one`
  - [ ] `test_kg_precision__half_correct__0_5`
  - [ ] `test_kg_precision__no_ground_truth__none`
  - [ ] `test_kg_recall__all_found__one`
  - [ ] `test_kg_recall__half_found__0_5`
  - [ ] `test_kg_f1__perfect__one`
  - [ ] `test_kg_f1__precision_1_recall_0_5__0_67`
  - [ ] `test_kg_f1__both_zero__zero`
  - [ ] `test_entity_coverage__full__one`
  - [ ] `test_entity_coverage__partial__ratio`
  - [ ] `test_entity_coverage__empty_kg__zero`
  - [ ] `test_relation_accuracy__correct__high`
  - [ ] `test_relation_accuracy__incorrect__low`
- [ ] GREEN: `services/evaluation/kg_metrics.py` 新規作成
  - [ ] `KGPrecision` 実装
  - [ ] `KGRecall` 実装
  - [ ] `KGF1` 実装
  - [ ] `EntityCoverage` 実装
  - [ ] `RelationAccuracy` 実装
- [ ] テスト GREEN 確認

### 3.7 エージェント合意メトリクス
- [ ] RED: `tests/test_consensus_metrics.py` 作成
  - [ ] `test_fleiss_kappa__perfect_agreement__one`
  - [ ] `test_fleiss_kappa__random_agreement__near_zero`
  - [ ] `test_fleiss_kappa__two_raters__correct`
  - [ ] `test_fleiss_kappa__empty__zero`
  - [ ] `test_convergence__converging__positive_slope`
  - [ ] `test_convergence__diverging__negative_slope`
  - [ ] `test_convergence__single_round__none`
  - [ ] `test_belief_stability__stable__high`
  - [ ] `test_belief_stability__volatile__low`
  - [ ] `test_belief_stability__single_snapshot__one`
- [ ] GREEN: `services/evaluation/consensus_metrics.py` 新規作成
  - [ ] `FleissKappa` 実装
  - [ ] `ConsensusConvergence` 実装
  - [ ] `BeliefStability` 実装
- [ ] テスト GREEN 確認

### 3.8 予測精度メトリクス
- [ ] RED: `tests/test_prediction_metrics.py` 作成
  - [ ] `test_prediction_accuracy__correct__high`
  - [ ] `test_prediction_accuracy__incorrect__low`
  - [ ] `test_prediction_accuracy__no_backtest__none`
  - [ ] `test_scenario_calibration__well_calibrated__high`
  - [ ] `test_scenario_calibration__poorly_calibrated__low`
- [ ] GREEN: `services/evaluation/prediction_metrics.py` 新規作成
  - [ ] `PredictionAccuracy` 実装
  - [ ] `ScenarioCalibration` 実装
- [ ] テスト GREEN 確認

### 3.9 LLM 呼び出しログ
- [ ] RED: `tests/test_experiment_logger.py` 作成
  - [ ] `test_llm_logger__log_call__saves_to_db`
  - [ ] `test_llm_logger__computes_latency`
  - [ ] `test_llm_logger__hashes_prompts`
  - [ ] `test_llm_logger__optional_full_prompt`
  - [ ] `test_llm_logger__decorator__wraps_call`
  - [ ] `test_llm_logger__decorator__preserves_return`
- [ ] GREEN: `services/experiment_logger.py` 新規作成
  - [ ] `LLMCallLogger` クラス実装
  - [ ] `log()` メソッド
  - [ ] `@log_llm_call` デコレータ
- [ ] テスト GREEN 確認

### 3.10 BDI 状態遷移ログ
- [ ] RED: `tests/test_experiment_logger.py` 拡張
  - [ ] `test_bdi_logger__saves_belief_change`
  - [ ] `test_bdi_logger__saves_desire_change`
  - [ ] `test_bdi_logger__saves_intention_change`
  - [ ] `test_bdi_logger__includes_round_number`
- [ ] GREEN: `services/experiment_logger.py` に追加
  - [ ] `BDITransitionLogger` クラス実装
- [ ] テスト GREEN 確認

### 3.11 構造化実験レポート
- [ ] RED: `tests/test_experiment_logger.py` 拡張
  - [ ] `test_experiment_report__includes_config`
  - [ ] `test_experiment_report__includes_metrics`
  - [ ] `test_experiment_report__includes_llm_summary`
  - [ ] `test_experiment_report__includes_timing`
  - [ ] `test_experiment_report__json_serializable`
  - [ ] `test_experiment_report__yaml_export`
- [ ] GREEN: `services/experiment_logger.py` に追加
  - [ ] `generate_experiment_report()` 関数
- [ ] テスト GREEN 確認

### 3.12 ベースライン比較
- [ ] RED: `tests/test_comparison.py` 作成
  - [ ] `test_compare__returns_metric_diffs`
  - [ ] `test_compare__returns_judgment_diffs`
  - [ ] `test_compare__returns_evidence_diffs`
  - [ ] `test_compare__different_modes__comparable`
  - [ ] `test_compare__missing_sim__raises_not_found`
  - [ ] `test_comparison_report__side_by_side_metrics`
  - [ ] `test_comparison_report__highlights_significant_diffs`
  - [ ] `test_comparison_report__improvement_indicators`
- [ ] GREEN: `services/comparison.py` 新規作成
  - [ ] `ComparisonResult` dataclass
  - [ ] `compare_simulations()` 関数
- [ ] テスト GREEN 確認
- [ ] Phase 3 完了: 全メトリクスが計算可能であることを確認

---

## Phase 4: GraphRAG 置換と LLM クライアント統合

### 4.1 client.py → multi_client.py ラッパー化
- [ ] RED: `tests/test_llm_client.py` 拡張
  - [ ] `test_wrapper__call__delegates_to_multi_client`
  - [ ] `test_wrapper__task_name_routing_preserved`
  - [ ] `test_wrapper__call_with_retry__validation_fn_passed`
  - [ ] `test_wrapper__call_batch__delegates_to_batch`
  - [ ] `test_wrapper__backward_compat__existing_callers_work`
- [ ] GREEN: `llm/client.py` を `multi_client.py` のラッパーに書き換え
- [ ] テスト GREEN 確認（既存テスト含む全テスト）

### 4.2 Redis キャッシュ層
- [ ] RED: `tests/test_llm_cache.py` 作成
  - [ ] `test_cache_hit__returns_cached_response`
  - [ ] `test_cache_miss__calls_llm_and_stores`
  - [ ] `test_cache_key__includes_prompt_model_temp`
  - [ ] `test_cache_ttl__expires_after_configured_time`
  - [ ] `test_cache_bypass__when_temperature_nonzero`
  - [ ] `test_cache_invalidate__clears_by_pattern`
- [ ] GREEN: `llm/cache.py` 新規作成
  - [ ] `LLMCache` クラス実装
  - [ ] `multi_client.py` にキャッシュ層統合
- [ ] テスト GREEN 確認

### 4.3 LLMCallLog インターセプター統合
- [ ] RED: `tests/test_llm_interceptor.py` 作成
  - [ ] `test_interceptor__logs_after_success`
  - [ ] `test_interceptor__logs_after_failure`
  - [ ] `test_interceptor__measures_latency`
  - [ ] `test_interceptor__does_not_alter_response`
  - [ ] `test_interceptor__disabled_without_context`
- [ ] GREEN: `multi_client.py` にインターセプター組み込み
- [ ] テスト GREEN 確認

### 4.4 GraphRAG アダプター抽象化
- [ ] RED: `tests/test_graphrag_adapter.py` 作成
  - [ ] `test_abstract__cannot_instantiate`
  - [ ] `test_concrete__must_implement_extract`
  - [ ] `test_legacy_adapter__returns_knowledge_graph`
  - [ ] `test_legacy_adapter__entities_have_fields`
  - [ ] `test_legacy_adapter__relations_have_fields`
- [ ] GREEN: `services/graphrag/adapter.py` 新規作成
  - [ ] `GraphRAGAdapter` ABC
  - [ ] `LegacyAdapter` 実装
- [ ] テスト GREEN 確認

### 4.5 LightRAG アダプター実装
- [ ] LightRAG / nano-graphrag の API 調査・選定
- [ ] `uv add lightrag` (または選定ライブラリ)
- [ ] RED: `tests/test_graphrag_adapter.py` 拡張
  - [ ] `test_lightrag__returns_knowledge_graph`
  - [ ] `test_lightrag__output_format_matches_legacy`
  - [ ] `test_lightrag__handles_empty_document`
  - [ ] `test_lightrag__handles_large_document`
- [ ] GREEN: `LightRAGAdapter` 実装
- [ ] テスト GREEN 確認

### 4.6 パイプライン差し替え
- [ ] RED: `tests/test_graphrag_pipeline.py` 作成
  - [ ] `test_pipeline__uses_configured_adapter`
  - [ ] `test_pipeline__lightrag__produces_valid_kg`
  - [ ] `test_pipeline__legacy_fallback__works`
  - [ ] `test_pipeline__adapter_error__falls_back`
- [ ] GREEN: `graphrag/pipeline.py` をアダプター委譲に書き換え
- [ ] テスト GREEN 確認

### 4.7 自作 GraphRAG コード削除
- [ ] RED: 削除後にテストが通ることを確認
- [ ] `graphrag/chunker.py` 削除
- [ ] `graphrag/entity_extractor.py` 削除
- [ ] `graphrag/relation_extractor.py` 削除
- [ ] `graphrag/dedup_resolver.py` 削除
- [ ] `graphrag/community_detector.py` 削除
- [ ] `graphrag/ontology_generator.py` 削除
- [ ] テスト全 GREEN 確認
- [ ] Phase 4 完了: LLM統合 + GraphRAG置換完了

---

## Phase 5: API 整理とフロントエンド対応

### 5.1 バックエンド API ルート統合
- [ ] RED: `tests/test_simulations_api.py` 書き直し
  - [ ] `test_create__unified__201`
  - [ ] `test_create__single__201`
  - [ ] `test_create__baseline__201`
  - [ ] `test_create__invalid_mode__422`
  - [ ] `test_create__missing_prompt__422`
  - [ ] `test_get__existing__200`
  - [ ] `test_get__not_found__404`
  - [ ] `test_list__returns_ordered`
  - [ ] `test_list__empty__returns_empty`
  - [ ] `test_stream__returns_sse`
  - [ ] `test_report__unified__returns_result`
  - [ ] `test_report__single__returns_report`
  - [ ] `test_report__baseline__returns_result`
  - [ ] `test_report__not_completed__404`
  - [ ] `test_graph__returns_nodes_edges`
  - [ ] `test_graph__no_graph__empty`
  - [ ] `test_graph_history__returns_snapshots`
  - [ ] `test_evaluation__returns_metrics`
  - [ ] `test_evaluation__no_metrics__empty`
  - [ ] `test_compare__returns_comparison`
  - [ ] `test_compare__missing_sim__404`
  - [ ] `test_followup__returns_answer`
  - [ ] `test_rerun__creates_new`
  - [ ] `test_interview__returns_response`
  - [ ] `test_interview__invalid_agent__404`
  - [ ] `test_deleted_colonies__404`
  - [ ] `test_deleted_scenarios__404`
  - [ ] `test_deleted_backtest__404`
- [ ] GREEN: ルートファイル削除・書き直し
  - [ ] `routes/runs.py` 削除
  - [ ] `routes/swarms.py` 削除
  - [ ] `routes/admin.py` → 必要機能を simulations に統合後削除
  - [ ] `routes/stream.py` → simulations に統合後削除
  - [ ] `routes/projects.py` 削除
  - [ ] `routes/templates.py` → 内部ヘルパー化
  - [ ] `routes/simulations.py` 16エンドポイントに書き直し
  - [ ] `routes/society.py` Population のみに簡素化
- [ ] テスト全 GREEN 確認

### 5.2 フロントエンド API クライアント更新
- [ ] RED: `frontend/tests/unit/api-client.test.ts` 作成
  - [ ] `test createSimulation sends correct payload`
  - [ ] `test getSimulation returns typed response`
  - [ ] `test getReport returns unified format`
  - [ ] `test compareSimulations returns diff`
  - [ ] `test interviewAgent sends question`
- [ ] GREEN: `frontend/src/api/client.ts` を新API対応に更新
- [ ] テスト GREEN 確認

### 5.3 LaunchPadPage 更新
- [ ] RED: `frontend/tests/unit/LaunchPadPage.test.ts` 作成
  - [ ] `test renders 3 mode options`
  - [ ] `test unified mode selected by default`
  - [ ] `test baseline mode shows seed input`
- [ ] GREEN: `LaunchPadPage.vue` のモード選択を3モードに変更
- [ ] テスト GREEN 確認

### 5.4 ResultsPage 更新
- [ ] RED: `frontend/tests/unit/ResultsPage.test.ts` 作成
  - [ ] `test unified mode shows decision brief`
  - [ ] `test baseline mode shows comparison view`
  - [ ] `test evaluation tab shows all metrics`
- [ ] GREEN: `ResultsPage.vue` のモード別分岐を3モードに統合
- [ ] 不要コンポーネント削除（ColonyGrid 等）
- [ ] テスト GREEN 確認

### 5.5 EvaluationDashboard 強化
- [ ] 新メトリクス（KG品質、合意度、予測精度）の可視化追加
- [ ] baseline 比較チャート追加
- [ ] `pnpm test:unit` 全パス確認
- [ ] Phase 5 完了

---

## Phase 6: 仕上げ

### 6.1 エージェントインタビュー機能
- [ ] RED: `tests/test_interview.py` 作成
  - [ ] `test_interview__returns_response_with_reasoning`
  - [ ] `test_interview__uses_agent_bdi_state`
  - [ ] `test_interview__uses_agent_memory`
  - [ ] `test_interview__persona_consistent`
  - [ ] `test_interview__agent_not_found__raises`
  - [ ] `test_interview__sim_not_completed__raises`
- [ ] GREEN: `services/interview.py` 新規作成
  - [ ] `InterviewResponse` dataclass
  - [ ] `interview_agent()` 関数
- [ ] テスト GREEN 確認

### 6.2 インタビュー UI
- [ ] ResultsPage にインタビューパネルコンポーネント追加
- [ ] エージェント選択 → 質問入力 → 応答表示のフロー実装
- [ ] フロントエンドテスト追加・GREEN 確認

### 6.3 メモリシステム確認
- [ ] 3層構造（episodic, semantic, procedural）の現状確認
- [ ] 不要コードの除去（あれば）
- [ ] `retrieval.py`, `reflection.py` をユーティリティとして維持

### 6.4 ドキュメント整備
- [ ] README のアーキテクチャ図更新（3モード構成）
- [ ] API リファレンス更新（16エンドポイント）
- [ ] クイックスタートガイド更新
- [ ] BDI エンジンのアルゴリズム記述（学術論文向け）
- [ ] 評価メトリクスの数学的定義（学術論文向け）
- [ ] 再現性プロトコルの記述（学術論文向け）

### 6.5 カバレッジ目標達成
- [ ] `uv run pytest --cov=src/app --cov-report=term-missing` 実行
- [ ] 80% 未満のモジュール特定
- [ ] `unified_orchestrator.py` テスト追加（目標: 80%+）
- [ ] `evaluation/` テスト追加（目標: 90%+）
- [ ] `multi_client.py` テスト追加（目標: 80%+）
- [ ] `reproducibility.py` テスト追加（目標: 90%+）
- [ ] `experiment_logger.py` テスト追加（目標: 90%+）
- [ ] 最終カバレッジ: `uv run pytest --cov=src/app --cov-fail-under=80`
- [ ] Phase 6 完了: 全テスト GREEN + カバレッジ 80%+ 達成

---

## 完了基準チェックリスト

- [ ] 実行モード: 3つのみ（unified, single, baseline）
- [ ] DB モデル: 12以下
- [ ] API エンドポイント: 16-20
- [ ] テストカバレッジ: 80%+
- [ ] 新規テスト数: ~210
- [ ] 全テスト GREEN
- [ ] シード再現性: 同一シード → 同一結果
- [ ] 実験ログ: 全LLM呼び出し記録
- [ ] 評価メトリクス: 12種以上
- [ ] ベースライン比較: baseline vs unified の定量比較
- [ ] エージェントインタビュー: 完了済みシミュレーションで動作
- [ ] GraphRAG: LightRAG アダプター動作
- [ ] ドキュメント: README + 学術論文向け記述
