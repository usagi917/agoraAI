# agentAI TDD タスクリスト v4 — フェーズ部品化

---

## Phase 0: 基盤整備

- [x] 全テスト GREEN 確認 (308テスト, 52%カバレッジ)
- [x] カバレッジベースライン記録 (52%)
- [x] `tests/conftest.py` 作成（db_session, mock_sse, mock_llm）
- [x] `tests/factories.py` 作成 + テスト (16テスト)
- [x] `refactor/v2` ブランチ作成

---

## Phase 1: フェーズ部品化

### 1.1 multi_perspective.py（swarm から移植）

#### RED
- [ ] `tests/test_multi_perspective.py` 作成
  - [ ] `test_run__returns_perspectives_list`
  - [ ] `test_run__returns_aggregated_scenarios`
  - [ ] `test_run__returns_agreement_matrix`
  - [ ] `test_run__returns_integrated_report`
  - [ ] `test_run__respects_perspective_count`
  - [ ] `test_run__respects_max_concurrent`
  - [ ] `test_run__clones_world_state_per_perspective`
  - [ ] `test_run__calls_claim_extractor`
  - [ ] `test_run__calls_claim_clusterer`
  - [ ] `test_run__empty_input__returns_empty_results`

#### GREEN
- [ ] `services/phases/multi_perspective.py` 新規作成
  - [ ] `MultiPerspectiveResult` dataclass 定義
  - [ ] `run_multi_perspective()` 関数
  - [ ] swarm_orchestrator.py から移植:
    - [ ] Colony並列実行ロジック（Semaphore制御）
    - [ ] `_clone_world_state()` ロジック
    - [ ] Claim抽出呼び出し（claim_extractor.py 利用）
    - [ ] Claimクラスタリング呼び出し（claim_clusterer.py 利用）
    - [ ] シナリオ集約ロジック
    - [ ] agreement_matrix 計算ロジック
    - [ ] 統合レポート生成（swarm_report_generator.py 利用）
- [ ] テスト GREEN 確認

#### 回帰テスト
- [ ] 旧 swarm テスト（あれば）が新ファイルで通ること確認

---

### 1.2 pm_analysis.py（PM Board から移植）

#### RED
- [ ] `tests/test_pm_analysis.py` 作成
  - [ ] `test_run__returns_3_persona_analyses`
  - [ ] `test_run__returns_chief_pm_synthesis`
  - [ ] `test_run__returns_11_sections`
  - [ ] `test_run__loads_yaml_templates`
  - [ ] `test_run__parallel_persona_execution`
  - [ ] `test_run__fallback_when_llm_fails`
  - [ ] `test_run__includes_evidence_references`
  - [ ] `test_run__includes_quality_gates`
  - [ ] `test_sections__has_core_question`
  - [ ] `test_sections__has_plan_30_60_90`

#### GREEN
- [ ] `services/phases/pm_analysis.py` 新規作成
  - [ ] `PMAnalysisResult` dataclass 定義
  - [ ] `run_pm_analysis()` 関数
  - [ ] pm_board_orchestrator.py から移植:
    - [ ] `_load_pm_template()` ロジック
    - [ ] 3ペルソナ並列分析ロジック
    - [ ] Chief PM統合ロジック
    - [ ] 11セクション構造化出力
    - [ ] フォールバック合成（`build_pm_board_fallback`）
    - [ ] エビデンス参照収集
    - [ ] 品質ゲート + 検証
- [ ] テスト GREEN 確認

---

### 1.3 issue_mining.py（Society First から移植）

#### RED
- [ ] `tests/test_issue_mining_phase.py` 作成
  - [ ] `test_run__returns_ranked_issues`
  - [ ] `test_run__returns_issue_analyses`
  - [ ] `test_run__returns_intervention_comparison`
  - [ ] `test_run__respects_max_issues`
  - [ ] `test_run__uses_society_pulse_data`
  - [ ] `test_run__backtest_overlay_applied`
  - [ ] `test_run__empty_pulse__returns_empty`

#### GREEN
- [ ] `services/phases/issue_mining.py` 新規作成
  - [ ] `IssueMiningResult` dataclass 定義
  - [ ] `run_issue_mining()` 関数
  - [ ] society_first_orchestrator.py から移植:
    - [ ] イシュー候補抽出（issue_miner.py 利用）
    - [ ] イシュー別Colony深掘り（`_run_issue_colonies` ロジック）
    - [ ] 介入比較（`build_intervention_comparison` 利用）
    - [ ] バックテストオーバーレイ（`overlay_observed_intervention_comparison` 利用）
    - [ ] `_flatten_issue_scenarios()` ロジック
- [ ] テスト GREEN 確認

---

### 1.4 intervention.py（Meta から移植）

#### RED
- [ ] `tests/test_intervention_phase.py` 作成
  - [ ] `test_run__returns_cycles`
  - [ ] `test_run__returns_best_cycle`
  - [ ] `test_run__returns_interventions`
  - [ ] `test_run__returns_convergence_score`
  - [ ] `test_run__respects_max_cycles`
  - [ ] `test_run__stops_at_target_score`
  - [ ] `test_run__injects_intervention_into_next_cycle`
  - [ ] `test_run__cycle_0_has_no_intervention`
  - [ ] `test_run__selects_best_cycle_by_score`

#### GREEN
- [ ] `services/phases/intervention.py` 新規作成
  - [ ] `InterventionResult` dataclass 定義
  - [ ] `run_intervention()` 関数
  - [ ] meta_orchestrator.py から移植:
    - [ ] 反復ループロジック（max_cycles制御）
    - [ ] 介入計画（meta_intervention_planner.py 利用）
    - [ ] 介入注入（プロンプト変換）
    - [ ] 目的スコア計算（compute_objective_score 利用）
    - [ ] 収束判定（evaluate_stop_condition 利用）
    - [ ] 最良サイクル選択ロジック
    - [ ] `_build_cycle_summary()` ロジック
- [ ] テスト GREEN 確認

---

### 1.5 Simulation.mode & プリセット定義

#### RED
- [ ] `tests/test_presets.py` 作成
  - [ ] `test_preset_quick__has_2_phases`
  - [ ] `test_preset_standard__has_3_phases`
  - [ ] `test_preset_deep__has_5_phases`
  - [ ] `test_preset_research__has_5_phases`
  - [ ] `test_preset_baseline__is_special`
  - [ ] `test_normalize_mode__old_modes_remap`
    - [ ] `pipeline → deep`
    - [ ] `swarm → deep`
    - [ ] `hybrid → deep`
    - [ ] `pm_board → deep`
    - [ ] `single → quick`
    - [ ] `society → standard`
    - [ ] `society_first → research`
    - [ ] `meta_simulation → research`
    - [ ] `unified → standard`
  - [ ] `test_normalize_mode__unknown__raises`

#### GREEN
- [ ] `models/simulation.py` に追加:
  - [ ] `PRESETS` dict定数
  - [ ] `VALID_PRESETS` set定数
  - [ ] `normalize_mode()` 関数（旧モード → プリセットにマップ）
  - [ ] `mode` フィールドのデフォルトを `"standard"` に変更
- [ ] テスト GREEN 確認

---

### 1.6 unified_orchestrator.py リファクタ

#### RED
- [ ] `tests/test_unified_v2.py` 作成
  - [ ] `test_run__quick__executes_2_phases`
  - [ ] `test_run__standard__executes_3_phases`
  - [ ] `test_run__deep__executes_5_phases`
  - [ ] `test_run__research__executes_5_phases`
  - [ ] `test_run__phase_checkpoint_after_each`
  - [ ] `test_run__sse_published_per_phase`
  - [ ] `test_run__context_passes_between_phases`
  - [ ] `test_run__error__sets_failed`
  - [ ] `test_run__kg_data_propagated_through_phases`

#### GREEN
- [ ] `unified_orchestrator.py` をプリセット駆動に書き換え
  - [ ] `PHASE_RUNNERS` dict（フェーズ名 → 実行関数のマップ）
  - [ ] `run_unified()` をループ形式に書き換え
  - [ ] context dict のフェーズ間引き渡し
  - [ ] KG進化トラッキング維持
  - [ ] SSEイベント配信維持
  - [ ] チェックポイント維持
- [ ] テスト GREEN 確認

---

### 1.7 baseline_orchestrator.py 新設

#### RED
- [ ] `tests/test_baseline_orchestrator.py` 作成
  - [ ] `test_run__completes_successfully`
  - [ ] `test_run__saves_unified_result_format`
  - [ ] `test_run__uses_temperature_zero`
  - [ ] `test_run__missing_sim__returns_early`
  - [ ] `test_run__error__sets_failed`

#### GREEN
- [ ] `services/baseline_orchestrator.py` 新規作成
- [ ] テスト GREEN 確認

---

### 1.8 simulation_dispatcher.py 書き換え

#### RED
- [ ] `tests/test_dispatch_v2.py` 作成
  - [ ] `test_dispatch__standard__calls_run_unified`
  - [ ] `test_dispatch__deep__calls_run_unified`
  - [ ] `test_dispatch__baseline__calls_run_baseline`
  - [ ] `test_dispatch__old_mode_pipeline__remapped_and_calls_unified`
  - [ ] `test_dispatch__missing_sim__returns_early`
  - [ ] `test_dispatch__error__sets_failed`

#### GREEN
- [ ] `simulation_dispatcher.py` を2分岐に書き換え（baseline or unified）
- [ ] テスト GREEN 確認

---

### 1.9 旧オーケストレータ削除

#### RED
- [ ] `tests/test_no_stale_imports.py` 作成
  - [ ] 旧モジュール名の import が存在しないことを AST で確認

#### GREEN — 参照除去 + 削除
- [ ] 全残存参照を grep で確認・除去
- [ ] ファイル削除:
  - [ ] `services/pipeline_orchestrator.py`
  - [ ] `services/swarm_orchestrator.py`
  - [ ] `services/pm_board_orchestrator.py`
  - [ ] `services/meta_orchestrator.py`
  - [ ] `services/society_first_orchestrator.py`
- [ ] **削除しない（フェーズ部品が利用）:**
  - claim_extractor.py, claim_clusterer.py, swarm_report_generator.py
  - meta_intervention_planner.py, react_reporter.py, final_report_generator.py
  - colony_factory.py（multi_perspective.py が視点生成に利用）
- [ ] 旧テスト削除:
  - [ ] `tests/test_pipeline_orchestrator.py`
  - [ ] `tests/test_swarm_orchestrator.py`
- [ ] テスト全 GREEN 確認

### 1.10 Phase 1 完了検証

- [ ] `uv run pytest --tb=short -q` → 全 GREEN
- [ ] `uv run pytest --cov=src/app` → カバレッジ確認
- [ ] 回帰テスト:
  - [ ] standard プリセット → 旧 unified と同等の出力構造
  - [ ] deep プリセット → multi_perspective + pm_analysis が動作
  - [ ] research プリセット → issue_mining + intervention が動作
- [ ] コミット: `feat: refactor orchestrators to composable phase architecture`

---

## Phase 2: DB モデル整理

（plan3 task3 と同じ。変更なし。）

- [ ] LLMCallLog, ExperimentConfig 新モデル追加
- [ ] Simulation フィールド追加（name, seed, config_snapshot_id）
- [ ] Repository レイヤー導入
- [ ] 旧モデル段階的削除（Colony, Swarm, Run, Project, Document 等）
- [ ] 最終: 12モデル以下

---

## Phase 3: 学術機能追加

（plan3 task3 と同じ。変更なし。）

- [ ] シード制御 + 再現性
- [ ] 設定スナップショット
- [ ] BaseMetric + 既存メトリクス移行
- [ ] KG品質メトリクス（precision, recall, F1）
- [ ] エージェント合意メトリクス（Fleiss κ, convergence, stability）
- [ ] 実験ログ（LLMCallLog, BDI遷移ログ）
- [ ] ベースライン比較

---

## Phase 4: GraphRAG アダプター化

**方針変更: 全面置換 → アダプター + ベンチマーク**

- [ ] `GraphRAGAdapter` ABC 定義
- [ ] `LegacyAdapter` 作成（現在の自作実装をラップ）
- [ ] `LightRAGAdapter` 作成（LightRAG利用）
- [ ] ベンチマークテスト作成（同一入力で品質比較）
- [ ] 品質が同等以上の場合のみ LightRAG をデフォルトに
- [ ] 品質が劣る場合は LegacyAdapter を維持

---

## Phase 5: API + フロントエンド

- [ ] API: `POST /simulations` の `mode` を `preset` に変更
  - quick / standard / deep / research / baseline
- [ ] API: 16エンドポイントに整理
- [ ] フロントエンド: LaunchPad に5プリセットのカード選択UI
- [ ] フロントエンド: ResultsPage のモード分岐を統一

---

## Phase 6: 仕上げ

- [ ] エージェントインタビュー機能
- [ ] ドキュメント整備（README, 学術論文向け記述）
- [ ] カバレッジ 80%+ 達成

---

## 完了基準

- [ ] プリセット: 5つ（quick, standard, deep, research, baseline）
- [ ] フェーズ部品: 7つ（独立テスト可能）
- [ ] DB モデル: ≤ 12
- [ ] API: 16-20 エンドポイント
- [ ] カバレッジ: ≥ 80%
- [ ] 出力品質: 旧モードと同等（回帰テストで確認）
- [ ] 旧オーケストレータ: 5ファイル削除済み
- [ ] サポートファイル: 6ファイル維持（フェーズ部品が利用）
