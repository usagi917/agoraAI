# agentAI 学術リファクタリング TDD開発計画 v2

## 開発原則

### TDDサイクル（Red-Green-Refactor）
```
1. RED:   失敗するテストを書く（期待する振る舞いを定義）
2. GREEN: テストを通す最小限のコードを書く
3. REFACTOR: コードを整理（テストは緑のまま）
```

### テスト命名規則
```python
# ファイル: test_{module_name}.py
# クラス: Test{ClassName}
# メソッド: test_{method_name}_{scenario}_{expected_result}
# 例: test_dispatch_simulation__unified_mode__calls_run_unified
```

### テスト構造（AAA パターン）
```python
async def test_xxx():
    # Arrange: テストデータ・モック準備
    # Act: 対象関数を呼ぶ
    # Assert: 結果を検証
```

---

## Phase 0: 基盤整備（テスト環境の確立）

### 目的
リファクタリング前に、既存テストが全て通る状態を確認し、カバレッジのベースラインを取得する。

### 0.1 テスト実行環境の確認
**対象ファイル:** `backend/tests/` 全39ファイル

```bash
cd backend && uv run pytest --tb=short -q 2>&1 | tail -20
```

- 失敗テストの原因分析と修正
- テスト間の依存関係（順序依存）の排除

### 0.2 カバレッジベースライン
```bash
uv run pytest --cov=src/app --cov-report=term-missing --cov-report=html
```

- 現在のカバレッジ率を記録
- カバレッジ 0% のモジュールをリストアップ

### 0.3 テストヘルパー整備
**新規作成:** `backend/tests/conftest.py` の拡充
**新規作成:** `backend/tests/factories.py`

テストで繰り返し使うファクトリ関数群:
```python
# factories.py
def make_simulation(mode="unified", status="queued", **overrides) -> Simulation
def make_agent_profile(name="Agent-1", **overrides) -> AgentProfile
def make_kg_node(label="TestEntity", **overrides) -> KGNode
def make_kg_edge(source_id, target_id, **overrides) -> KGEdge
def make_evaluation_result(sim_id, metric_name="diversity", **overrides) -> EvaluationResult
def make_llm_response(content: dict, tokens: int = 100) -> tuple[dict, dict]
def make_society_pulse_result(**overrides) -> SocietyPulseResult
def make_council_result(**overrides) -> CouncilResult
```

### 0.4 Alembic 導入
**変更:** `backend/pyproject.toml` に `alembic` 追加
**新規:** `backend/alembic/` ディレクトリ
**新規:** `backend/alembic/env.py` (async engine対応)

```python
# テスト
test_alembic_upgrade_downgrade  # upgrade → downgrade → upgrade が成功
test_alembic_heads_single       # マイグレーションヘッドが1つだけ
```

---

## Phase 1: 実行モード統合

### 1.1 Simulation.mode バリデーション変更

**変更ファイル:** `backend/src/app/models/simulation.py`
**テストファイル:** `backend/tests/test_simulation_model.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestSimulationMode:
    # 新モードの受け入れ
    def test_mode__unified__accepted(self)
    def test_mode__single__accepted(self)
    def test_mode__baseline__accepted(self)

    # 旧モード → 新モードへのリマップ
    def test_mode__pipeline__remaps_to_unified(self)
    def test_mode__swarm__remaps_to_unified(self)
    def test_mode__hybrid__remaps_to_unified(self)
    def test_mode__pm_board__remaps_to_unified(self)
    def test_mode__society__remaps_to_unified(self)
    def test_mode__society_first__remaps_to_unified(self)
    def test_mode__meta_simulation__remaps_to_unified(self)

    # 不正モードの拒否
    def test_mode__unknown__raises_value_error(self)
```

**GREEN 実装:**
- `Simulation` モデルに `@validates('mode')` を追加
- `MODE_ALIASES` マップを定義: `{"pipeline": "unified", "swarm": "unified", ...}`
- 不正モードは `ValueError` を raise

**REFACTOR:**
- `MODE_ALIASES` を定数として `models/constants.py` に切り出し

---

### 1.2 simulation_dispatcher.py のルーティング削減

**変更ファイル:** `backend/src/app/services/simulation_dispatcher.py`
**テストファイル:** `backend/tests/test_simulation_dispatcher.py` (書き直し)

#### TDDステップ

**RED テスト群:**
```python
class TestDispatchSimulation:
    # 正常系: 3モードのルーティング
    async def test_dispatch__unified__calls_run_unified(self)
    async def test_dispatch__single__calls_run_simulation(self)
    async def test_dispatch__baseline__calls_run_baseline(self)

    # 異常系
    async def test_dispatch__invalid_mode__raises_error(self)
    async def test_dispatch__missing_simulation__raises_error(self)

    # SSE通知
    async def test_dispatch__unified__publishes_start_event(self)
    async def test_dispatch__failure__publishes_error_event(self)
    async def test_dispatch__failure__sets_status_failed(self)

class TestEnsureProject:
    async def test_ensure_project__existing_project__returns_id(self)
    async def test_ensure_project__no_project__creates_new(self)
    async def test_ensure_project__prompt_text_propagation(self)
```

**GREEN 実装:**
- `dispatch_simulation()` を書き直し: unified/single/baseline の3分岐のみ
- 旧モードの import を全削除
- `_dispatch_single`, `_dispatch_swarm`, `_dispatch_pm_board` ヘルパーを削除
- baseline は新設の `run_baseline()` を呼ぶ

**REFACTOR:**
- dispatcher を薄くし、各 orchestrator に責務を委譲

---

### 1.3 不要オーケストレータの削除

**削除対象（13ファイル）:**
```
backend/src/app/services/pipeline_orchestrator.py
backend/src/app/services/swarm_orchestrator.py
backend/src/app/services/pm_board_orchestrator.py
backend/src/app/services/meta_orchestrator.py
backend/src/app/services/society_first_orchestrator.py
backend/src/app/services/meta_intervention_planner.py
backend/src/app/services/swarm_report_generator.py
backend/src/app/services/colony_factory.py
backend/src/app/services/claim_extractor.py
backend/src/app/services/claim_clusterer.py
backend/src/app/services/final_report_generator.py
backend/src/app/services/pipeline_fallbacks.py
backend/src/app/services/aggregator.py (存在すれば)
```

**テスト削除対象:**
```
backend/tests/test_pipeline_orchestrator.py
backend/tests/test_swarm_orchestrator.py
```

#### TDDステップ

**RED テスト（削除前の安全確認）:**
```python
class TestNoStaleImports:
    def test_simulation_dispatcher__no_deleted_imports(self)
    def test_unified_orchestrator__no_deleted_imports(self)
    def test_simulator__no_deleted_imports(self)
    def test_all_routes__no_deleted_imports(self)

    # 全 Python ファイルに削除モジュールの import がないことを確認
    def test_codebase__no_references_to_deleted_modules(self)
```

**GREEN 実装:**
1. 各ファイルの参照元を grep で確認
2. 参照を全て除去
3. ファイルを削除
4. 関連テストを削除

**REFACTOR:**
- `__init__.py` の `__all__` をクリーンアップ

---

### 1.4 unified_orchestrator.py の PM Board 統合

**変更ファイル:** `backend/src/app/services/unified_orchestrator.py`
**変更ファイル:** `backend/src/app/services/phases/synthesis.py`
**テストファイル:** `backend/tests/test_unified_orchestrator.py` (新規)
**テストファイル:** `backend/tests/test_synthesis.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestRunUnified:
    async def test_run_unified__completes_3_phases(self)
    async def test_run_unified__saves_result_to_metadata_json(self)
    async def test_run_unified__sets_status_completed(self)
    async def test_run_unified__publishes_phase_change_events(self)
    async def test_run_unified__with_pm_analysis__includes_pm_section(self)
    async def test_run_unified__without_pm_analysis__no_pm_section(self)
    async def test_run_unified__error_in_pulse__sets_failed(self)

class TestRunSynthesis:
    async def test_run_synthesis__returns_decision_brief(self)
    async def test_run_synthesis__agreement_score_between_0_and_1(self)
    async def test_run_synthesis__with_pm__includes_pm_perspective(self)
    async def test_compute_agreement_score__balanced_inputs__returns_midrange(self)
    async def test_compute_agreement_score__full_consensus__returns_high(self)
    async def test_compute_agreement_score__no_data__returns_zero(self)
```

**GREEN 実装:**
- `run_unified()` に `use_pm_analysis: bool = False` パラメータ追加
- `run_synthesis()` に PM 視点統合ロジック追加
- PM Board の4ペルソナ分析を synthesis のプロンプトに内包

---

### 1.5 single モードの簡素化

**変更ファイル:** `backend/src/app/services/simulator.py`
**テストファイル:** `backend/tests/test_simulator.py` (拡張)

#### TDDステップ

**RED テスト群:**
```python
class TestSingleRunSimulator:
    def test_init__no_colony_config__defaults(self)
    async def test_run__minimal_input__returns_result(self)
    async def test_run__with_graphrag__builds_kg(self)
    async def test_run__without_graphrag__skips_kg(self)
    async def test_run__preview_profile__2_rounds(self)
    async def test_run__standard_profile__4_rounds(self)

class TestRunSimulation:
    async def test_run_simulation__success__sets_completed(self)
    async def test_run_simulation__failure__sets_failed(self)
    async def test_run_simulation__return_result_true__returns_dict(self)
    async def test_run_simulation__return_result_false__returns_none(self)
```

**GREEN 実装:**
- `SingleRunSimulator.__init__()` から `colony_config` を削除
- `_inject_perspective()` を削除（Colony 概念の除去）
- Colony 関連の import を除去

---

### 1.6 baseline モードの新設

**新規ファイル:** `backend/src/app/services/baseline_orchestrator.py`
**テストファイル:** `backend/tests/test_baseline_orchestrator.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestRunBaseline:
    async def test_run_baseline__returns_result(self)
    async def test_run_baseline__result_format_matches_unified(self)
    async def test_run_baseline__uses_single_llm_call(self)
    async def test_run_baseline__no_agents_created(self)
    async def test_run_baseline__saves_to_metadata_json(self)
    async def test_run_baseline__sets_status_completed(self)

class TestBaselineReproducibility:
    async def test_run_baseline__same_seed__same_result(self)
    async def test_run_baseline__different_seed__different_result(self)
    async def test_run_baseline__seed_stored_in_simulation(self)
```

**GREEN 実装:**
```python
# baseline_orchestrator.py
async def run_baseline(simulation_id: str) -> None:
    """単一LLMでテーマを分析。エージェントなし。学術比較用ベースライン。"""
    # 1. Simulation 取得
    # 2. シード固定 (temperature=0, seed=sim.seed)
    # 3. 単一プロンプトでテーマ分析
    # 4. unified と同じ JSON フォーマットで結果保存
    # 5. status = completed
```

---

## Phase 2: DB モデル統合

### 2.1 新モデル追加（非破壊的）

**新規ファイル:** `backend/src/app/models/llm_call_log.py`
**新規ファイル:** `backend/src/app/models/experiment_config.py`
**テストファイル:** `backend/tests/test_new_models.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestLLMCallLog:
    async def test_create__minimal__saved(self)
    async def test_create__full_fields__saved(self)
    async def test_query_by_simulation_id__returns_calls(self)
    async def test_query_by_task_name__filters_correctly(self)
    async def test_latency_ms__positive_integer(self)

class TestExperimentConfig:
    async def test_create__snapshot_saved(self)
    async def test_create__yaml_configs_serialized(self)
    async def test_create__package_versions_recorded(self)
    async def test_restore__returns_original_config(self)
```

**GREEN 実装:**
```python
# models/llm_call_log.py
class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"
    id: str           # uuid
    simulation_id: str
    task_name: str
    provider: str
    model: str
    system_prompt_hash: str
    user_prompt_hash: str
    response_hash: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    temperature: float
    seed: int | None
    full_prompt: str | None  # オプション
    full_response: str | None  # オプション
    created_at: datetime

# models/experiment_config.py
class ExperimentConfig(Base):
    __tablename__ = "experiment_configs"
    id: str           # uuid
    simulation_id: str
    models_yaml: dict
    cognitive_yaml: dict
    graphrag_yaml: dict
    llm_providers_yaml: dict
    python_packages: dict   # {"fastapi": "0.115.0", ...}
    git_commit_hash: str | None
    created_at: datetime
```

### 2.2 Simulation モデルへのフィールド追加

**変更ファイル:** `backend/src/app/models/simulation.py`
**テストファイル:** `backend/tests/test_simulation_model.py` (拡張)

#### TDDステップ

**RED テスト群:**
```python
class TestSimulationNewFields:
    async def test_name__default_empty(self)
    async def test_description__default_empty(self)
    async def test_input_documents__stores_json_list(self)
    async def test_seed__stores_integer(self)
    async def test_seed__auto_generated_when_none(self)
    async def test_config_snapshot_id__references_experiment_config(self)
```

**GREEN 実装:**
- `Simulation` に以下を追加:
  - `name: str = ""`
  - `description: str = ""`
  - `input_documents: dict = {}` (JSON)
  - `seed: int | None`
  - `config_snapshot_id: str | None`

### 2.3 Repository レイヤー導入

**新規ファイル:** `backend/src/app/repositories/__init__.py`
**新規ファイル:** `backend/src/app/repositories/simulation_repo.py`
**新規ファイル:** `backend/src/app/repositories/agent_repo.py`
**新規ファイル:** `backend/src/app/repositories/kg_repo.py`
**新規ファイル:** `backend/src/app/repositories/evaluation_repo.py`
**テストファイル:** `backend/tests/test_repositories.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestSimulationRepository:
    async def test_create__returns_simulation(self)
    async def test_get_by_id__found__returns_simulation(self)
    async def test_get_by_id__not_found__returns_none(self)
    async def test_list__returns_all_ordered_by_created_at(self)
    async def test_update_status__changes_status(self)
    async def test_save_result__stores_metadata_json(self)
    async def test_get_with_report__includes_report_data(self)

class TestAgentRepository:
    async def test_save_profiles__stores_batch(self)
    async def test_get_profiles_by_simulation__returns_list(self)
    async def test_save_state__creates_agent_state(self)
    async def test_get_states_by_round__filters_correctly(self)

class TestKGRepository:
    async def test_save_nodes__batch_insert(self)
    async def test_save_edges__with_references(self)
    async def test_get_graph__returns_nodes_and_edges(self)
    async def test_get_graph_history__returns_snapshots(self)

class TestEvaluationRepository:
    async def test_save_metrics__batch_insert(self)
    async def test_get_by_simulation__returns_all_metrics(self)
    async def test_get_by_metric_name__filters(self)
```

**GREEN 実装:**
```python
# repositories/simulation_repo.py
class SimulationRepository:
    def __init__(self, session: AsyncSession)
    async def create(self, **kwargs) -> Simulation
    async def get(self, sim_id: str) -> Simulation | None
    async def list(self, limit: int = 50) -> list[Simulation]
    async def update_status(self, sim_id: str, status: str) -> None
    async def save_result(self, sim_id: str, result: dict) -> None
    async def get_with_report(self, sim_id: str) -> dict
```

### 2.4 旧モデル段階的削除

**削除順序（依存関係を考慮）:**

```
Step 1: Colony → Swarm → Run の削除（Phase 1 で使用停止済み）
Step 2: Project → Document の Simulation 統合
Step 3: WorldState, GraphState, GraphDiff の統合
Step 4: Report → SocietyResult 統合
Step 5: その他（CalibrationData, OutcomeClaim, ClaimCluster 等）
```

各ステップで:
1. 参照元を Repository に移行済みか確認
2. Alembic マイグレーション作成（データ移行 + テーブル削除）
3. モデルファイル削除
4. 全テスト実行

**テスト群（各ステップ共通パターン）:**
```python
class TestModelDeletion:
    async def test_simulation__no_run_id_reference(self)
    async def test_simulation__no_swarm_id_reference(self)
    async def test_repository__still_functional_after_deletion(self)
    async def test_migration__upgrade__succeeds(self)
    async def test_migration__downgrade__succeeds(self)
```

---

## Phase 3: 学術機能の追加

### 3.1 シード制御と再現性

**変更ファイル:** `backend/src/app/services/simulation_dispatcher.py`
**変更ファイル:** `backend/src/app/llm/multi_client.py`
**新規ファイル:** `backend/src/app/services/reproducibility.py`
**テストファイル:** `backend/tests/test_reproducibility.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestSeedControl:
    def test_set_global_seed__deterministic_random(self)
    def test_set_global_seed__deterministic_numpy(self)
    def test_generate_seed__returns_positive_int(self)
    def test_generate_seed__within_32bit_range(self)

class TestDeterministicExecution:
    async def test_deterministic_mode__llm_temperature_zero(self)
    async def test_deterministic_mode__seed_passed_to_llm(self)
    async def test_deterministic_mode__same_seed_same_order(self)

class TestConfigSnapshot:
    async def test_take_snapshot__captures_all_yamls(self)
    async def test_take_snapshot__captures_package_versions(self)
    async def test_take_snapshot__captures_git_hash(self)
    async def test_restore_snapshot__matches_original(self)
```

**GREEN 実装:**
```python
# services/reproducibility.py
import random, numpy as np

def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)

def generate_seed() -> int:
    return random.randint(0, 2**31 - 1)

async def take_config_snapshot(session, simulation_id: str) -> ExperimentConfig:
    """全YAML設定 + パッケージバージョン + git hash をスナップショット"""

async def restore_config_snapshot(config_id: str) -> dict:
    """スナップショットから設定を復元"""
```

### 3.2 評価フレームワーク

**新規ディレクトリ:** `backend/src/app/services/evaluation/`
**新規ファイル:** `backend/src/app/services/evaluation/__init__.py`
**新規ファイル:** `backend/src/app/services/evaluation/base.py`
**新規ファイル:** `backend/src/app/services/evaluation/society_metrics.py`
**新規ファイル:** `backend/src/app/services/evaluation/kg_metrics.py`
**新規ファイル:** `backend/src/app/services/evaluation/consensus_metrics.py`
**新規ファイル:** `backend/src/app/services/evaluation/prediction_metrics.py`
**テストファイル:** `backend/tests/test_evaluation_metrics.py` (新規)

#### 3.2.1 BaseMetric 抽象基底クラス

**RED テスト群:**
```python
class TestBaseMetric:
    def test_abstract__cannot_instantiate(self)
    def test_concrete__must_implement_compute(self)
    def test_concrete__must_have_name(self)
    def test_compute__returns_metric_result(self)

class TestMetricResult:
    def test_metric_result__has_name_score_details(self)
    def test_metric_result__score_between_0_and_1(self)
    def test_metric_result__to_dict(self)
```

**GREEN 実装:**
```python
# evaluation/base.py
@dataclass
class MetricResult:
    name: str
    score: float  # 0.0 - 1.0
    details: dict

class BaseMetric(ABC):
    name: str
    @abstractmethod
    def compute(self, **kwargs) -> MetricResult: ...
```

#### 3.2.2 既存メトリクス移行

**RED テスト群:**
```python
class TestDiversityMetric:
    def test_compute__uniform_distribution__max_entropy(self)
    def test_compute__single_stance__zero_entropy(self)
    def test_compute__empty_responses__returns_zero(self)
    def test_compute__returns_metric_result_type(self)

class TestConsistencyMetric:
    def test_compute__aligned_profiles__high_score(self)
    def test_compute__misaligned_profiles__low_score(self)
    def test_compute__empty_data__returns_zero(self)

class TestCalibrationMetric:
    def test_compute__perfect_calibration__returns_one(self)
    def test_compute__poor_calibration__returns_low(self)

class TestBrierMetric:
    def test_compute__perfect_forecast__returns_one(self)  # inverted: 1 = good
    def test_compute__random_forecast__returns_mid(self)
```

**GREEN 実装:**
- `society/evaluation.py` の5関数を `evaluation/society_metrics.py` の5クラスに変換
- 各クラスは `BaseMetric` を継承
- 旧 `evaluation.py` は新クラスへの委譲ラッパーに（後方互換）

#### 3.2.3 KG 品質メトリクス（新規）

**RED テスト群:**
```python
class TestKGPrecision:
    def test_compute__all_correct__returns_one(self)
    def test_compute__half_correct__returns_0_5(self)
    def test_compute__no_ground_truth__returns_none(self)

class TestKGRecall:
    def test_compute__all_found__returns_one(self)
    def test_compute__half_found__returns_0_5(self)

class TestKGF1:
    def test_compute__perfect__returns_one(self)
    def test_compute__precision_1_recall_0_5__returns_0_67(self)
    def test_compute__both_zero__returns_zero(self)

class TestEntityCoverage:
    def test_compute__full_coverage__returns_one(self)
    def test_compute__partial__returns_ratio(self)
    def test_compute__empty_kg__returns_zero(self)

class TestRelationAccuracy:
    async def test_compute__correct_relations__high_score(self)
    async def test_compute__incorrect_relations__low_score(self)
```

**GREEN 実装:**
```python
# evaluation/kg_metrics.py
class KGPrecision(BaseMetric):
    name = "kg_precision"
    def compute(self, extracted: list[dict], ground_truth: list[dict]) -> MetricResult

class KGRecall(BaseMetric):
    name = "kg_recall"
    def compute(self, extracted: list[dict], ground_truth: list[dict]) -> MetricResult

class KGF1(BaseMetric):
    name = "kg_f1"
    def compute(self, precision: float, recall: float) -> MetricResult

class EntityCoverage(BaseMetric):
    name = "entity_coverage"
    def compute(self, kg_entities: list[dict], theme_keywords: list[str]) -> MetricResult

class RelationAccuracy(BaseMetric):
    name = "relation_accuracy"
    async def compute(self, relations: list[dict], llm_client) -> MetricResult
```

#### 3.2.4 エージェント合意メトリクス（新規）

**RED テスト群:**
```python
class TestFleissKappa:
    def test_compute__perfect_agreement__returns_one(self)
    def test_compute__random_agreement__returns_near_zero(self)
    def test_compute__two_raters__correct_calculation(self)
    def test_compute__empty_ratings__returns_zero(self)

class TestConsensusConvergence:
    def test_compute__converging__positive_slope(self)
    def test_compute__diverging__negative_slope(self)
    def test_compute__single_round__returns_none(self)

class TestBeliefStability:
    def test_compute__stable_beliefs__high_score(self)
    def test_compute__volatile_beliefs__low_score(self)
    def test_compute__single_snapshot__returns_one(self)
```

**GREEN 実装:**
```python
# evaluation/consensus_metrics.py
class FleissKappa(BaseMetric):
    name = "fleiss_kappa"
    def compute(self, ratings: list[list[str]]) -> MetricResult
    # Fleiss' κ の標準的な計算式

class ConsensusConvergence(BaseMetric):
    name = "consensus_convergence"
    def compute(self, round_stances: list[list[str]]) -> MetricResult
    # ラウンドごとのスタンス分布の収束速度

class BeliefStability(BaseMetric):
    name = "belief_stability"
    def compute(self, agent_states: list[list[dict]]) -> MetricResult
    # BDI belief の変化量の逆数
```

### 3.3 実験ログ

**変更ファイル:** `backend/src/app/llm/multi_client.py`
**新規ファイル:** `backend/src/app/services/experiment_logger.py`
**テストファイル:** `backend/tests/test_experiment_logger.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestLLMCallLogger:
    async def test_log_call__saves_to_db(self)
    async def test_log_call__computes_latency(self)
    async def test_log_call__hashes_prompts(self)
    async def test_log_call__optional_full_prompt(self)
    async def test_decorator__wraps_multi_client_call(self)
    async def test_decorator__preserves_return_value(self)

class TestBDITransitionLogger:
    async def test_log_transition__saves_belief_change(self)
    async def test_log_transition__saves_desire_change(self)
    async def test_log_transition__saves_intention_change(self)
    async def test_log_transition__includes_round_number(self)

class TestExperimentReport:
    async def test_generate_report__includes_config(self)
    async def test_generate_report__includes_metrics(self)
    async def test_generate_report__includes_llm_summary(self)
    async def test_generate_report__includes_timing(self)
    async def test_generate_report__json_serializable(self)
    async def test_generate_report__yaml_export(self)
```

**GREEN 実装:**
```python
# services/experiment_logger.py
class LLMCallLogger:
    def __init__(self, session, simulation_id: str, save_full_prompt: bool = False)
    async def log(self, task_name, provider, model, system_prompt, user_prompt,
                  response, tokens, latency_ms, temperature, seed) -> None

class BDITransitionLogger:
    def __init__(self, session, simulation_id: str)
    async def log_transition(self, agent_id, round_number,
                             old_beliefs, new_beliefs,
                             old_desires, new_desires,
                             old_intentions, new_intentions) -> None

async def generate_experiment_report(session, simulation_id: str) -> dict:
    """完了したシミュレーションの構造化実験レポートを生成"""
```

### 3.4 ベースライン比較

**新規ファイル:** `backend/src/app/services/comparison.py`
**テストファイル:** `backend/tests/test_comparison.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestCompareSimulations:
    async def test_compare__returns_metric_diffs(self)
    async def test_compare__returns_judgment_diffs(self)
    async def test_compare__returns_evidence_diffs(self)
    async def test_compare__different_modes__still_comparable(self)
    async def test_compare__missing_sim__raises_not_found(self)

class TestComparisonReport:
    async def test_format__includes_side_by_side_metrics(self)
    async def test_format__highlights_significant_differences(self)
    async def test_format__includes_improvement_indicators(self)
```

**GREEN 実装:**
```python
# services/comparison.py
@dataclass
class ComparisonResult:
    sim_a_id: str
    sim_b_id: str
    metric_diffs: list[dict]      # [{name, a_score, b_score, diff}]
    judgment_diffs: list[dict]     # [{aspect, a_judgment, b_judgment}]
    improvement_score: float       # 総合改善スコア

async def compare_simulations(session, sim_a_id: str, sim_b_id: str) -> ComparisonResult
```

---

## Phase 4: GraphRAG 置換と LLM クライアント統合

### 4.1 LLM クライアント統合

**変更ファイル:** `backend/src/app/llm/client.py`
**変更ファイル:** `backend/src/app/llm/multi_client.py`
**テストファイル:** `backend/tests/test_llm_client.py` (拡張)
**テストファイル:** `backend/tests/test_llm_cache.py` (新規)

#### 4.1.1 client.py → multi_client.py ラッパー化

**RED テスト群:**
```python
class TestLLMClientWrapper:
    async def test_call__delegates_to_multi_client(self)
    async def test_call__task_name_routing_preserved(self)
    async def test_call_with_retry__validation_fn_passed(self)
    async def test_call_batch__delegates_to_batch_by_provider(self)
    async def test_backward_compat__existing_callers_work(self)
```

#### 4.1.2 Redis キャッシュ層

**RED テスト群:**
```python
class TestLLMCache:
    async def test_cache_hit__returns_cached_response(self)
    async def test_cache_miss__calls_llm_and_stores(self)
    async def test_cache_key__includes_prompt_model_temp(self)
    async def test_cache_ttl__expires_after_configured_time(self)
    async def test_cache_bypass__when_temperature_nonzero(self)
    async def test_cache_invalidate__clears_by_pattern(self)
```

#### 4.1.3 LLMCallLog インターセプター

**RED テスト群:**
```python
class TestLLMCallLogInterceptor:
    async def test_interceptor__logs_after_successful_call(self)
    async def test_interceptor__logs_after_failed_call(self)
    async def test_interceptor__measures_latency(self)
    async def test_interceptor__does_not_alter_response(self)
    async def test_interceptor__disabled_when_no_simulation_context(self)
```

### 4.2 GraphRAG 置換

**新規ファイル:** `backend/src/app/services/graphrag/adapter.py`
**変更ファイル:** `backend/src/app/services/graphrag/pipeline.py`
**テストファイル:** `backend/tests/test_graphrag_adapter.py` (新規)

#### 4.2.1 アダプター抽象化

**RED テスト群:**
```python
class TestGraphRAGAdapter:
    def test_abstract__cannot_instantiate(self)
    def test_concrete__must_implement_extract(self)

class TestLegacyAdapter:
    async def test_extract__returns_knowledge_graph(self)
    async def test_extract__entities_have_required_fields(self)
    async def test_extract__relations_have_required_fields(self)

class TestLightRAGAdapter:
    async def test_extract__returns_knowledge_graph(self)
    async def test_extract__output_format_matches_legacy(self)
    async def test_extract__handles_empty_document(self)
    async def test_extract__handles_large_document(self)
```

**GREEN 実装:**
```python
# services/graphrag/adapter.py
class GraphRAGAdapter(ABC):
    @abstractmethod
    async def extract(self, document_text: str, theme: str,
                      session=None, run_id: str = "") -> KnowledgeGraph: ...

class LegacyAdapter(GraphRAGAdapter):
    """既存の自作 GraphRAG パイプラインのラッパー"""

class LightRAGAdapter(GraphRAGAdapter):
    """LightRAG ライブラリを使用したアダプター"""
```

#### 4.2.2 パイプライン差し替えと旧コード削除

**RED テスト群:**
```python
class TestGraphRAGPipelineWithAdapter:
    async def test_run__uses_configured_adapter(self)
    async def test_run__lightrag__produces_valid_kg(self)
    async def test_run__legacy_fallback__works(self)
    async def test_run__adapter_error__falls_back_to_legacy(self)
```

---

## Phase 5: API 整理とフロントエンド対応

### 5.1 API ルート統合

**変更ファイル:** `backend/src/app/api/routes/simulations.py` (書き直し)
**変更ファイル:** `backend/src/app/api/routes/society.py` (簡素化)
**テストファイル:** `backend/tests/test_simulations_api.py` (書き直し)

#### TDDステップ

**RED テスト群:**
```python
class TestCreateSimulation:
    async def test_create__unified__returns_201(self)
    async def test_create__single__returns_201(self)
    async def test_create__baseline__returns_201(self)
    async def test_create__invalid_mode__returns_422(self)
    async def test_create__missing_prompt__returns_422(self)

class TestGetSimulation:
    async def test_get__existing__returns_200(self)
    async def test_get__not_found__returns_404(self)

class TestListSimulations:
    async def test_list__returns_ordered_list(self)
    async def test_list__empty__returns_empty_list(self)

class TestStreamSimulation:
    async def test_stream__returns_sse(self)
    async def test_stream__not_found__returns_404(self)

class TestGetReport:
    async def test_report__unified__returns_unified_result(self)
    async def test_report__single__returns_report(self)
    async def test_report__baseline__returns_baseline_result(self)
    async def test_report__not_completed__returns_404(self)

class TestGetGraph:
    async def test_graph__returns_nodes_and_edges(self)
    async def test_graph__no_graph__returns_empty(self)
    async def test_graph_history__returns_snapshots(self)

class TestGetEvaluation:
    async def test_evaluation__returns_all_metrics(self)
    async def test_evaluation__no_metrics__returns_empty(self)

class TestCompareSimulations:
    async def test_compare__returns_comparison(self)
    async def test_compare__missing_sim__returns_404(self)

class TestFollowup:
    async def test_followup__returns_answer(self)

class TestRerun:
    async def test_rerun__creates_new_simulation(self)

class TestInterview:
    async def test_interview__returns_agent_response(self)
    async def test_interview__invalid_agent__returns_404(self)

class TestDeletedEndpoints:
    async def test_colonies__returns_404(self)   # 削除されたエンドポイント
    async def test_scenarios__returns_404(self)
    async def test_backtest__returns_404(self)
```

### 5.2 フロントエンド対応

**変更ファイル:** `frontend/src/api/client.ts`
**変更ファイル:** `frontend/src/pages/LaunchPadPage.vue`
**変更ファイル:** `frontend/src/pages/ResultsPage.vue`
**テストファイル:** `frontend/tests/unit/api-client.test.ts` (新規)

#### TDDステップ

**RED テスト群:**
```typescript
// frontend/tests/unit/api-client.test.ts
describe('API Client', () => {
  test('createSimulation sends correct payload', async () => {})
  test('getSimulation returns typed response', async () => {})
  test('getReport returns unified format', async () => {})
  test('compareSimulations returns diff', async () => {})
  test('interviewAgent sends question', async () => {})
})

// frontend/tests/unit/LaunchPadPage.test.ts
describe('LaunchPadPage', () => {
  test('renders 3 mode options', () => {})
  test('unified mode selected by default', () => {})
  test('baseline mode shows seed input', () => {})
})

// frontend/tests/unit/ResultsPage.test.ts
describe('ResultsPage', () => {
  test('unified mode shows decision brief', () => {})
  test('baseline mode shows comparison view', () => {})
  test('evaluation tab shows all metrics', () => {})
})
```

---

## Phase 6: 仕上げ

### 6.1 エージェントインタビュー

**新規ファイル:** `backend/src/app/services/interview.py`
**テストファイル:** `backend/tests/test_interview.py` (新規)

#### TDDステップ

**RED テスト群:**
```python
class TestInterviewAgent:
    async def test_interview__returns_response_with_reasoning(self)
    async def test_interview__uses_agent_bdi_state(self)
    async def test_interview__uses_agent_memory(self)
    async def test_interview__persona_consistent(self)
    async def test_interview__agent_not_found__raises(self)
    async def test_interview__simulation_not_completed__raises(self)
```

**GREEN 実装:**
```python
# services/interview.py
@dataclass
class InterviewResponse:
    agent_name: str
    answer: str
    reasoning: str
    beliefs_referenced: list[str]
    confidence: float

async def interview_agent(
    session, simulation_id: str, agent_index: int, question: str
) -> InterviewResponse
```

### 6.2 カバレッジ目標

```bash
# 最終目標
uv run pytest --cov=src/app --cov-fail-under=80
```

**カバレッジ強化対象モジュール:**
- `unified_orchestrator.py` — 統合テスト
- `evaluation/` — 全メトリクスの境界値テスト
- `multi_client.py` — エラーハンドリング、タイムアウト
- `reproducibility.py` — シード制御の確実性
- `experiment_logger.py` — ログ記録の網羅性

---

## 全体の進行ルール

1. **各タスクの開始時**: RED テストを書いてコミット（`test: add failing tests for XXX`）
2. **実装完了時**: GREEN にしてコミット（`feat: implement XXX`）
3. **リファクタ時**: テスト緑を維持しながらコミット（`refactor: simplify XXX`）
4. **各フェーズ完了時**: `uv run pytest --cov` で全テストパス + カバレッジ確認
5. **削除作業時**: まず参照がゼロであることをテストで確認、次に削除

## タイムライン目安

| Phase | 期間 | テスト数（新規概算） |
|-------|------|---------------------|
| 0 | 1-2日 | ~10 |
| 1 | 3-5日 | ~40 |
| 2 | 2-3日 | ~35 |
| 3 | 3-5日 | ~55 |
| 4 | 3-4日 | ~30 |
| 5 | 2-3日 | ~25 |
| 6 | 2-3日 | ~15 |
| **合計** | **16-25日** | **~210テスト** |
