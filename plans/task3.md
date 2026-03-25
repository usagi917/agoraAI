# agentAI TDD タスクリスト v3 — コードレベル粒度

> 各タスクの右には対応する **テストファイル:テスト名** を記載。
> `[T]` = テスト作成, `[I]` = 実装, `[R]` = リファクタ, `[D]` = 削除, `[V]` = 検証

---

## Phase 0: 基盤整備

### 0.1 テスト環境確認
- [ ] [V] `uv run pytest --tb=short -q` 実行 → 全テスト GREEN
- [ ] [V] 失敗テストのリストアップ: ___件
- [ ] [I] 各失敗テストの修正
- [ ] [V] 修正後 `uv run pytest` → 全 GREEN 確認
- [ ] [V] `uv run pytest --cov=src/app --cov-report=term-missing` → ベースライン: ___%

### 0.2 conftest.py 作成
- [ ] [I] `backend/tests/conftest.py` 新規作成
  - [ ] `db_session` フィクスチャ (SQLite in-memory)
  - [ ] `mock_sse_manager` フィクスチャ
  - [ ] `mock_llm_client` フィクスチャ

### 0.3 テストファクトリ

#### RED テスト
- [ ] [T] `backend/tests/test_factories.py` 新規作成
  - [ ] `TestMakeSimulation::test_returns_simulation_instance`
  - [ ] `TestMakeSimulation::test_default_mode_unified`
  - [ ] `TestMakeSimulation::test_override_mode`
  - [ ] `TestMakeSimulation::test_override_status`
  - [ ] `TestMakeSimulation::test_unique_ids`
  - [ ] `TestMakeResponses::test_returns_list_of_dicts`
  - [ ] `TestMakeResponses::test_custom_confidence`
  - [ ] `TestMakeAgents::test_returns_correct_count`
  - [ ] `TestMakeAgents::test_has_big_five`
  - [ ] `TestMakeLlmResponse::test_returns_tuple`
  - [ ] `TestMakeLlmResponse::test_custom_content`

#### GREEN 実装
- [ ] [I] `backend/tests/factories.py` 新規作成
  - [ ] `make_simulation(**overrides) -> Simulation`
  - [ ] `make_responses(stances, confidence) -> list[dict]`
  - [ ] `make_agents(count, openness) -> list[dict]`
  - [ ] `make_pulse_result(**overrides) -> dict`
  - [ ] `make_council_result(**overrides) -> dict`
  - [ ] `make_llm_response(content, tokens) -> tuple`

#### 検証
- [ ] [V] `uv run pytest tests/test_factories.py -v` → 11テスト GREEN

### 0.4 ブランチ作成
- [ ] [I] `git checkout -b refactor/v2`
- [ ] [I] Phase 0 コミット: `git commit -m "chore: add test infrastructure (conftest, factories)"`

---

## Phase 1: 実行モード統合

### 1.1 Simulation.mode バリデーション

#### RED テスト (11テスト)
- [ ] [T] `backend/tests/test_simulation_mode.py` 新規作成
  - [ ] `TestValidModes::test_valid_mode_accepted` — パラメータ: `["unified", "single", "baseline"]`
  - [ ] `TestModeAliases::test_old_mode_remaps` — パラメータ: 7旧モード
    - [ ] `pipeline → unified`
    - [ ] `swarm → unified`
    - [ ] `hybrid → unified`
    - [ ] `pm_board → unified`
    - [ ] `society → unified`
    - [ ] `society_first → unified`
    - [ ] `meta_simulation → unified`
  - [ ] `TestInvalidMode::test_unknown_mode_raises` — `ValueError` を確認
- [ ] [V] テスト実行 → 11テスト RED（`normalize_mode` 未実装）

#### GREEN 実装
- [ ] [I] `backend/src/app/models/simulation.py` に追加:
  - [ ] `MODE_ALIASES` dict定数（7エントリ）
  - [ ] `VALID_MODES` set定数（3エントリ: unified, single, baseline）
  - [ ] `normalize_mode(mode: str) -> str` 関数
  - [ ] `mode` フィールドのデフォルトを `"pipeline"` → `"unified"` に変更
- [ ] [V] `uv run pytest tests/test_simulation_mode.py -v` → 11テスト GREEN

#### REFACTOR
- [ ] [R] `MODE_ALIASES`, `VALID_MODES` が他でも使われる場合 → 維持
- [ ] [V] 全テスト GREEN 確認

### 1.2 simulation_dispatcher.py 書き直し

#### RED テスト (11テスト)
- [ ] [T] `backend/tests/test_dispatch_v2.py` 新規作成
  - [ ] `TestDispatchRouting::test_unified_mode_calls_run_unified`
    - mock: `async_session`, `run_unified`
    - assert: `run_unified.assert_awaited_once_with(sim.id)`
  - [ ] `TestDispatchRouting::test_single_mode_calls_run_simulation`
    - mock: `async_session`, `run_simulation`
    - assert: `run_simulation.assert_awaited_once()`
  - [ ] `TestDispatchRouting::test_baseline_mode_calls_run_baseline`
    - mock: `async_session`, `run_baseline`
    - assert: `run_baseline.assert_awaited_once_with(sim.id)`
  - [ ] `TestDispatchRouting::test_missing_simulation_returns_early`
    - mock: `session.get` returns `None`
    - assert: 例外なし
  - [ ] `TestDispatchErrorHandling::test_failure_sets_status_failed`
    - mock: `run_unified` が `RuntimeError` を raise
    - assert: `sim.status == "failed"`, `"LLM error" in sim.error_message`
  - [ ] `TestDispatchErrorHandling::test_failure_publishes_sse_event`
    - mock: `run_unified` が `ValueError` を raise
    - assert: SSE の `"simulation_failed"` イベント配信確認
  - [ ] `TestEnsureProject::test_prompt_propagation_logic`
    - pure logic: `bool(sim_prompt) and not bool(project_prompt)`
  - [ ] `TestEnsureProject::test_no_overwrite_logic`
    - pure logic
- [ ] [V] テスト実行 → RED（dispatcher 未書き換え、旧 import がある）

#### GREEN 実装
- [ ] [I] `backend/src/app/services/simulation_dispatcher.py` 全面書き換え
  - [ ] 旧 import 全削除:
    - [ ] `from src.app.models.project import Project` 削除
    - [ ] `from src.app.models.run import Run` 削除
    - [ ] `from src.app.models.swarm import Swarm` 削除
    - [ ] `from src.app.services.swarm_orchestrator import run_swarm` 削除
    - [ ] `from src.app.services.pm_board_orchestrator import run_pm_board` 削除
    - [ ] `from src.app.services.pipeline_orchestrator import run_pipeline` 削除
    - [ ] `from src.app.services.colony_factory import generate_colony_configs` 削除
    - [ ] `from src.app.services.meta_orchestrator import run_meta_simulation` 削除
    - [ ] `from src.app.services.society.society_orchestrator import run_society` 削除
    - [ ] `from src.app.services.society_first_orchestrator import run_society_first` 削除
  - [ ] 新 import 追加:
    - [ ] `from src.app.models.simulation import Simulation, normalize_mode`
    - [ ] `from src.app.services.baseline_orchestrator import run_baseline`
  - [ ] `dispatch_simulation()` 書き換え: 3分岐のみ
    - [ ] `normalize_mode(sim.mode)` 呼び出し追加
    - [ ] `unified` → `run_unified(sim.id)`
    - [ ] `single` → `run_simulation(sim.id, prompt_text=sim.prompt_text)`
    - [ ] `baseline` → `run_baseline(sim.id)`
  - [ ] `_dispatch_single()` 関数削除
  - [ ] `_dispatch_swarm()` 関数削除
  - [ ] `_dispatch_pm_board()` 関数削除
  - [ ] `_ensure_project()` を簡素化（後方互換のみ）
- [ ] [V] `uv run pytest tests/test_dispatch_v2.py -v` → 8テスト GREEN

#### REFACTOR
- [ ] [D] 旧テスト `backend/tests/test_simulation_dispatcher.py` 削除
- [ ] [V] 全テスト GREEN 確認

### 1.3 不要オーケストレータの削除

#### RED テスト (2テスト)
- [ ] [T] `backend/tests/test_no_stale_imports.py` 新規作成
  - [ ] `TestNoStaleImports::test_no_references_to_deleted_modules`
    - AST パーサーで全 .py ファイルの import を走査
    - 13 モジュール名が含まれないことを確認
  - [ ] `TestNoStaleImports::test_deleted_files_do_not_exist`
    - 13 ファイルパスが存在しないことを確認
- [ ] [V] テスト実行 → RED（ファイルがまだ存在）

#### GREEN 実装 — 参照除去

Step A: 残存参照の確認と除去
- [ ] [V] `grep -rn "pipeline_orchestrator" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] `simulation_dispatcher.py` の旧 import 除去（1.2 で実施済み）
- [ ] [V] `grep -rn "swarm_orchestrator" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "pm_board_orchestrator" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "meta_orchestrator" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "society_first_orchestrator" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "colony_factory" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "claim_extractor\|claim_clusterer" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去
- [ ] [V] `grep -rn "final_report_generator\|pipeline_fallbacks\|swarm_report_generator\|meta_intervention_planner" src/app/ --include="*.py"` → 残存箇所特定
- [ ] [I] 各残存参照の除去

Step B: ファイル削除 (13ファイル)
- [ ] [D] `rm backend/src/app/services/pipeline_orchestrator.py`
- [ ] [D] `rm backend/src/app/services/swarm_orchestrator.py`
- [ ] [D] `rm backend/src/app/services/pm_board_orchestrator.py`
- [ ] [D] `rm backend/src/app/services/meta_orchestrator.py`
- [ ] [D] `rm backend/src/app/services/society_first_orchestrator.py`
- [ ] [D] `rm backend/src/app/services/meta_intervention_planner.py`
- [ ] [D] `rm backend/src/app/services/swarm_report_generator.py`
- [ ] [D] `rm backend/src/app/services/colony_factory.py`
- [ ] [D] `rm backend/src/app/services/claim_extractor.py`
- [ ] [D] `rm backend/src/app/services/claim_clusterer.py`
- [ ] [D] `rm backend/src/app/services/final_report_generator.py`
- [ ] [D] `rm backend/src/app/services/pipeline_fallbacks.py`
- [ ] [D] `rm backend/src/app/services/aggregator.py` (存在すれば)

Step C: 旧テスト削除
- [ ] [D] `rm backend/tests/test_pipeline_orchestrator.py`
- [ ] [D] `rm backend/tests/test_swarm_orchestrator.py`

#### 検証
- [ ] [V] `uv run pytest tests/test_no_stale_imports.py -v` → 2テスト GREEN
- [ ] [V] `uv run pytest --tb=short -q` → 全テスト GREEN
- [ ] [I] コミット: `refactor: remove 13 unused orchestrator files`

### 1.4 baseline_orchestrator.py 新設

#### RED テスト (5テスト)
- [ ] [T] `backend/tests/test_baseline_orchestrator.py` 新規作成
  - [ ] `TestRunBaseline::test_completes_successfully`
    - mock: `async_session`, `multi_llm_client`, `sse_manager`
    - assert: `sim.status == "completed"`, `sim.completed_at is not None`
  - [ ] `TestRunBaseline::test_saves_result_to_metadata_json`
    - assert: `"unified_result" in sim.metadata_json`
    - assert: `result["type"] == "baseline"`
  - [ ] `TestRunBaseline::test_uses_temperature_zero`
    - assert: `call_kwargs["temperature"] == 0.0`
  - [ ] `TestRunBaseline::test_missing_simulation_returns_early`
    - assert: `mock_llm.call.assert_not_awaited()`
  - [ ] `TestRunBaseline::test_error_sets_status_failed`
    - mock: `call` が `RuntimeError` を raise
    - assert: `sim.status == "failed"`
- [ ] [V] テスト実行 → RED（`baseline_orchestrator` 未作成）

#### GREEN 実装
- [ ] [I] `backend/src/app/services/baseline_orchestrator.py` 新規作成
  - [ ] `async def run_baseline(simulation_id: str) -> None`
  - [ ] システムプロンプト定義（JSON出力指示）
  - [ ] `multi_llm_client.call()` — `temperature=0.0`
  - [ ] 結果を `sim.metadata_json["unified_result"]` に保存
  - [ ] `type: "baseline"` フラグ
  - [ ] エラーハンドリング: `status="failed"`, SSE通知
- [ ] [V] `uv run pytest tests/test_baseline_orchestrator.py -v` → 5テスト GREEN

### 1.5 compute_agreement_score テスト強化

#### RED テスト (8テスト)
- [ ] [T] `backend/tests/test_synthesis_score.py` 新規作成
  - [ ] `test_balanced_inputs` — 0.3 <= score <= 0.7
  - [ ] `test_full_consensus` — score >= 0.8
  - [ ] `test_no_data` — score == 0.0
  - [ ] `test_society_only_no_council_points` — 0.6 <= score <= 0.8
  - [ ] `test_all_disagreement` — score == 0.25
  - [ ] `test_none_values_handled` — score == 0.0
  - [ ] `test_score_is_float` — isinstance(score, float)
  - [ ] `test_score_bounded_0_to_1` — 0.0 <= score <= 1.0
- [ ] [V] テスト実行 → GREEN（既存実装で通るはず）
- [ ] [V] 失敗があれば `synthesis.py` の `_safe_float` 等を修正

### 1.6 single モード簡素化

#### RED テスト (3テスト)
- [ ] [T] `backend/tests/test_simulator_v2.py` 新規作成
  - [ ] `test_single_run_simulator__init_no_args`
    - `SingleRunSimulator()` がエラーなしで生成されること
  - [ ] `test_single_run_simulator__no_colony_config_attr`
    - `hasattr(sim, 'colony_config')` が `False` であること（削除後）
  - [ ] `test_profile_rounds__known_profiles`
    - `PROFILE_ROUNDS["preview"] == 2`, `["standard"] == 4`, `["quality"] == 6`
- [ ] [V] テスト実行 → RED（colony_config まだ存在）

#### GREEN 実装
- [ ] [I] `backend/src/app/services/simulator.py` 修正:
  - [ ] `from src.app.services.colony_factory import ColonyConfig` — import 削除
  - [ ] `SingleRunSimulator.__init__()` から `colony_config` パラメータ削除
  - [ ] `self.colony_config` 参照を全て除去
  - [ ] `_inject_perspective()` メソッド削除
  - [ ] `colony_config.colony_id` 参照を `None` に置換
  - [ ] `colony_config.round_count` を `total_rounds` に置換
- [ ] [V] `uv run pytest tests/test_simulator_v2.py -v` → 3テスト GREEN
- [ ] [V] `uv run pytest --tb=short -q` → 全テスト GREEN

### 1.7 Phase 1 最終検証

- [ ] [V] `uv run pytest --tb=short -q` → 全テスト GREEN
- [ ] [V] `uv run pytest --cov=src/app --cov-report=term-missing` → カバレッジ記録
- [ ] [V] 新規テスト数: 11 + 8 + 2 + 5 + 8 + 3 + 11(factories) = **48テスト**
- [ ] [V] 削除ファイル数: 13(オーケストレータ) + 2(旧テスト) = **15ファイル削除**
- [ ] [V] 新規ファイル数: 7テスト + 2実装 + 2インフラ = **11ファイル追加**
- [ ] [I] コミット: `feat: complete Phase 1 — 9 modes consolidated to 3 (unified, single, baseline)`

---

## Phase 2-6: タスク概要

> Phase 1 完了後に同じ粒度で展開。以下は概要のみ。

### Phase 2: DB モデル統合 (推定 35タスク)
- [ ] `LLMCallLog` モデル: T5 + I1 = 6タスク
- [ ] `ExperimentConfig` モデル: T4 + I1 = 5タスク
- [ ] `Simulation` フィールド追加: T6 + I1 = 7タスク
- [ ] Repository レイヤー: T17 + I4 = 21タスク
- [ ] 旧モデル削除: 5ステップ × 各4タスク = 20タスク

### Phase 3: 学術機能追加 (推定 55タスク)
- [ ] シード制御: T4 + I2 = 6タスク
- [ ] 設定スナップショット: T4 + I2 = 6タスク
- [ ] BaseMetric: T5 + I2 = 7タスク
- [ ] 既存メトリクス移行: T13 + I5 = 18タスク
- [ ] KG品質メトリクス: T13 + I5 = 18タスク
- [ ] 合意メトリクス: T10 + I3 = 13タスク
- [ ] 実験ログ: T12 + I3 = 15タスク
- [ ] ベースライン比較: T8 + I2 = 10タスク

### Phase 4: GraphRAG/LLM (推定 30タスク)
- [ ] LLMクライアント統合: T5 + I1 = 6タスク
- [ ] Redisキャッシュ: T6 + I1 = 7タスク
- [ ] LLMCallLogインターセプター: T5 + I1 = 6タスク
- [ ] GraphRAGアダプター: T8 + I3 = 11タスク
- [ ] 自作コード削除: 6ファイル + 検証 = 8タスク

### Phase 5: API/Frontend (推定 35タスク)
- [ ] APIルート統合: T28 + I8 = 36タスク
- [ ] フロントエンド更新: T8 + I5 = 13タスク

### Phase 6: 仕上げ (推定 15タスク)
- [ ] インタビュー: T6 + I2 = 8タスク
- [ ] ドキュメント: 6タスク
- [ ] カバレッジ: 5タスク

---

## 完了基準

- [ ] 実行モード: 3つのみ（unified, single, baseline）
- [ ] DB モデル: ≤ 12
- [ ] API エンドポイント: 16-20
- [ ] テストカバレッジ: ≥ 80%
- [ ] 新規テスト総数: ~210
- [ ] 全テスト GREEN
- [ ] シード再現性: 同一シード → 同一結果
- [ ] 実験ログ: 全LLM呼び出し記録
- [ ] 評価メトリクス: ≥ 12種
- [ ] ベースライン比較: baseline vs unified 定量比較
- [ ] エージェントインタビュー: 動作確認
- [ ] GraphRAG: アダプター経由で動作
