# Task List: 実世論調査キャリブレーション基盤の構築

> Plan: `plans/survey-calibration-plan.md`
> Created: 2026-03-31

---

## Phase 1: 世論調査データスキーマとローダー

### 1.1 YAMLスキーマ定義
- [x] `config/grounding/survey_data/` ディレクトリ構造を作成 (`cabinet_office/`, `nhk/`, `boj/`)
- [x] `config/grounding/survey_data/schema.yaml` を作成 — 必須フィールド定義 (theme, question, source, survey_date, sample_size, method, stance_distribution, theme_category, relevance_keywords)
- [x] stance_distribution の5段階スタンス定義を明記 (賛成 / 条件付き賛成 / 中立 / 条件付き反対 / 反対)
- [x] `backend/tests/fixtures/survey_data_sample.yaml` にテスト用サンプルデータ (2テーマ、各1問) を作成

### 1.2 内閣府世論調査データ格納 (5テーマ)
- [x] 内閣府「外交に関する世論調査」(2024) — 主要2-3問のスタンス分布を `cabinet_office/diplomacy_2024.yaml` に入力
- [x] 内閣府「社会意識に関する世論調査」(2024) — 主要2-3問を `cabinet_office/social_awareness_2024.yaml` に入力
- [x] 内閣府「原子力に関する世論調査」(2023) — 主要2-3問を `cabinet_office/nuclear_energy_2023.yaml` に入力
- [x] 内閣府「高齢社会に関する世論調査」(2023) — 主要2-3問を `cabinet_office/aging_society_2023.yaml` に入力
- [x] 内閣府「自衛隊・防衛問題に関する世論調査」(2024) — 主要2-3問を `cabinet_office/defense_2024.yaml` に入力
- [x] 各YAMLが schema.yaml の形式に準拠していることを目視確認

### 1.3 NHK・日銀データ格納
- [x] NHK放送文化研究所「日本人の意識」調査 (2023) — 主要3-5問を `nhk/japanese_consciousness_2023.yaml` に入力
- [x] 日銀「生活意識に関するアンケート調査」(2024) — 経済テーマ3-5問を `boj/living_consciousness_2024.yaml` に入力
- [x] 全YAMLファイルの形式統一を最終確認 (フィールド名、スタンスラベル、比率の合計=1.0)

---

## Phase 2: survey_anchor.py — 世論調査アンカリングモジュール

### 2.1 テスト作成 (Red)
- [x] `backend/tests/test_survey_anchor.py` を新規作成
- [x] `test_load_survey_data` — fixtures/survey_data_sample.yaml を読み込み、list[SurveyRecord] が返ることを検証
- [x] `test_load_survey_data_validates_required_fields` — 必須フィールド欠損時に ValueError が出ることを検証
- [x] `test_load_survey_data_validates_distribution_sums_to_one` — stance_distribution の合計が1.0±0.01でない場合にエラー
- [x] `test_find_relevant_surveys_by_keyword` — テーマキーワード ("外交", "防衛") で関連調査が返ることを検証
- [x] `test_find_relevant_surveys_returns_empty_on_no_match` — 無関連キーワードで空リスト
- [x] `test_find_relevant_surveys_respects_top_k` — top_k=3 で最大3件
- [x] `test_kl_divergence_symmetric_identical` — 同一分布でKL≈0
- [x] `test_kl_divergence_symmetric_different` — 異なる分布でKL>0
- [x] `test_kl_divergence_symmetric_with_zero_probability` — スムージングでゼロ除算回避を検証
- [x] `test_earth_movers_distance_identical` — 同一分布でEMD=0
- [x] `test_earth_movers_distance_opposite` — 賛成100% vs 反対100% で最大EMD
- [x] `test_earth_movers_distance_ordinal_aware` — 隣接スタンス間 < 離れたスタンス間
- [x] `test_compare_with_surveys` — ComparisonReport の構造検証 (kl, emd, matched_surveys, deviations フィールド)
- [x] `test_compare_with_surveys_no_data` — 調査データなしで None or 空レポート
- [x] `test_stance_mapping_from_binary` — 賛成/反対の2択を5段階に変換
- [x] `test_stance_mapping_from_likert_5` — 5段階リッカートをスタンスにマップ
- [x] 全テストが Red (失敗) であることを確認: `pytest backend/tests/test_survey_anchor.py` → FAILED

### 2.2 実装 (Green)
- [x] `backend/src/app/services/society/survey_anchor.py` を新規作成
- [x] `SurveyRecord` TypedDict を定義 (theme, question, source, survey_date, sample_size, method, stance_distribution, theme_category, relevance_keywords)
- [x] `ComparisonReport` TypedDict を定義 (theme, matched_surveys, kl_divergence, emd, per_survey_deviations, best_match_source)
- [x] `load_survey_data(data_dir: str) -> list[SurveyRecord]` を実装 — 再帰的にYAML読み込み、バリデーション付き
- [x] `_validate_survey_record(record: dict) -> SurveyRecord` を実装 — 必須フィールド・分布合計チェック
- [x] `find_relevant_surveys(theme: str, surveys: list[SurveyRecord], top_k: int = 5) -> list[SurveyRecord]` を実装 — n-gram Jaccard によるキーワードマッチング
- [x] `map_to_five_stances(original: dict[str, float], mapping_type: str) -> dict[str, float]` を実装 — 2択/3択/5段階リッカート→5段階スタンスへの変換
- [x] `kl_divergence_symmetric(p: dict[str, float], q: dict[str, float], smoothing: float = 1e-6) -> float` を実装 — (KL(p||q) + KL(q||p)) / 2
- [x] `earth_movers_distance(p: dict[str, float], q: dict[str, float]) -> float` を実装 — 序数距離 (賛成=0, 条件付き賛成=1, 中立=2, 条件付き反対=3, 反対=4) を考慮した累積差分
- [x] `compare_with_surveys(simulation_distribution: dict[str, float], theme: str, data_dir: str) -> ComparisonReport | None` を実装
- [x] 全テストが Green (通過) であることを確認: `pytest backend/tests/test_survey_anchor.py` → PASSED

### 2.3 リファクタリング (Refactor)
- [x] `evaluation.py` の既存 `kl_divergence()` と新規 `kl_divergence_symmetric()` の関係を整理 — evaluation は uniform baseline 比較用、survey_anchor は実調査比較用として共存を確認
- [x] `backtest.py` の `_ngrams()`, `_jaccard()` と survey_anchor 内のキーワードマッチングの重複を確認 — 重複が大きければ共通ユーティリティ `text_similarity.py` に抽出
- [x] テスト再実行で全テスト通過を確認

---

## Phase 3: transfer_calibrator.py — LLM→Human バイアス補正

### 3.1 テスト作成 (Red)
- [x] `backend/tests/test_transfer_calibrator.py` を新規作成
- [x] `test_compute_bias_profile_single_comparison` — 1件の比較データからバイアスプロファイル構築
- [x] `test_compute_bias_profile_multiple_comparisons` — 複数件の比較データで平均ズレを算出
- [x] `test_compute_bias_profile_by_category` — テーマカテゴリ別 (economy, politics, social) にプロファイルが分かれる
- [x] `test_apply_transfer_correction_shifts_distribution` — 補正が分布をズレの逆方向にシフト
- [x] `test_apply_transfer_correction_preserves_normalization` — 補正後の分布合計 = 1.0
- [x] `test_apply_transfer_correction_no_negative_probabilities` — 補正後に負の確率が生まれない
- [x] `test_no_correction_when_insufficient_data` — sample_count < 閾値 (3) では補正適用しない (元の分布をそのまま返す)
- [x] `test_shrinkage_with_few_samples` — sample_count=3 では shrinkage が強く、補正がほぼ無い
- [x] `test_full_correction_with_many_samples` — sample_count=20 では shrinkage が弱く、補正が効く
- [x] `test_compute_transfer_uncertainty` — 不確実性の値が0以上で返る
- [x] `test_compute_transfer_uncertainty_decreases_with_more_data` — データ増加で不確実性が減少
- [x] 全テストが Red (失敗) であることを確認

### 3.2 実装 (Green)
- [x] `backend/src/app/services/society/transfer_calibrator.py` を新規作成
- [x] `StanceBias` TypedDict を定義 (mean_deviation, sample_count, std_deviation)
- [x] `BiasProfile` TypedDict を定義 — `dict[str, dict[str, StanceBias]]` (category → stance → StanceBias)
- [x] `compute_bias_profile(comparisons: list[ComparisonReport]) -> BiasProfile` を実装 — カテゴリ別・スタンス別の (sim - actual) 平均/標準偏差/件数
- [x] `apply_transfer_correction(distribution: dict[str, float], bias_profile: BiasProfile, theme_category: str, min_samples: int = 3) -> dict[str, float]` を実装:
  - shrinkage 係数: `alpha = min(1.0, sample_count / 20)` (20件で完全補正)
  - 補正: `corrected[stance] = max(0, dist[stance] - alpha * mean_deviation[stance])`
  - 再正規化して合計1.0に
- [x] `compute_transfer_uncertainty(bias_profile: BiasProfile, theme_category: str) -> float` を実装 — カテゴリ別のスタンスズレの標準偏差の平均
- [x] 全テストが Green (通過) であることを確認

### 3.3 リファクタリング (Refactor)
- [x] `calibration.py` に `apply_transfer_calibration(raw_distribution, bias_profile, theme_category) -> dict[str, float]` ラッパー関数を追加 — transfer_calibrator を呼び出す薄いラッパー
- [x] `statistical_inference.py` の `bootstrap_confidence_intervals()` に `extra_uncertainty: float = 0.0` パラメータを追加 — CI 幅を `± extra_uncertainty` で拡張
- [x] 既存テスト `test_calibration.py`, `test_statistical_inference.py` が壊れていないことを確認
- [x] テスト再実行で全テスト通過を確認

---

## Phase 4: ValidationRecord モデルとリポジトリ

### 4.1 テスト作成 (Red)
- [x] `backend/tests/test_validation_pipeline.py` を新規作成
- [x] `test_create_validation_record` — ValidationRecord を作成し DB に保存、再取得できること
- [x] `test_record_fields_persisted` — 全フィールド (theme_text, theme_category, simulated_distribution 等) が正しく永続化
- [x] `test_record_with_pending_actual` — actual_distribution=None で作成、validated_at=None
- [x] `test_resolve_validation_sets_actual` — resolve() で actual_distribution, survey_source, survey_date が設定される
- [x] `test_resolve_validation_computes_brier` — resolve() で brier_score が自動算出される
- [x] `test_resolve_validation_computes_kl` — resolve() で kl_divergence が自動算出される
- [x] `test_resolve_validation_computes_emd` — resolve() で emd が自動算出される
- [x] `test_resolve_validation_sets_validated_at` — resolve() で validated_at がタイムスタンプ設定
- [x] `test_list_by_simulation` — simulation_id でフィルタリング
- [x] `test_list_by_category` — theme_category でフィルタリング
- [x] `test_aggregate_by_category` — カテゴリ別の平均 Brier/KL/EMD を算出 (validated 済みレコードのみ)
- [x] `test_aggregate_by_category_excludes_unvalidated` — 未検証レコードは集計から除外
- [x] 全テストが Red (失敗) であることを確認

### 4.2 実装 (Green)
- [x] `backend/src/app/models/validation_record.py` を新規作成
- [x] ValidationRecord モデルを定義 — 全カラム (id UUID, simulation_id FK, theme_text, theme_category, simulated_distribution JSON, calibrated_distribution JSON nullable, actual_distribution JSON nullable, survey_source nullable, survey_date nullable, brier_score nullable, ece nullable, kl_divergence nullable, emd nullable, validated_at nullable, created_at)
- [x] `backend/src/app/models/__init__.py` に ValidationRecord の import を追加
- [x] `backend/src/app/repositories/validation_repo.py` を新規作成
- [x] `ValidationRepository` クラスを実装:
  - `async save(session, record: ValidationRecord) -> ValidationRecord`
  - `async get(session, record_id: str) -> ValidationRecord | None`
  - `async list_by_simulation(session, simulation_id: str) -> list[ValidationRecord]`
  - `async list_by_category(session, theme_category: str) -> list[ValidationRecord]`
  - `async resolve(session, record_id: str, actual_distribution: dict, survey_source: str, survey_date: str) -> ValidationRecord` — brier/kl/emd を calibration.py + survey_anchor.py の関数で自動算出
  - `async aggregate_by_category(session, theme_category: str | None = None) -> dict` — 平均精度指標
- [x] 全テストが Green (通過) であることを確認

### 4.3 リファクタリング (Refactor)
- [x] 既存の `EvaluationResult` モデルとの責務分離を確認 — EvaluationResult はシミュレーション内部品質、ValidationRecord は外部実績との照合
- [x] DB テーブル作成が `Base.metadata.create_all()` で自動的に含まれることを確認
- [x] テスト再実行で既存テスト含めて全テスト通過を確認

---

## Phase 5: validation_pipeline.py — 検証パイプライン

### 5.1 テスト作成 (Red)
- [x] `test_validation_pipeline.py` にパイプラインテストを追加 (Phase 4 のDBテストと同ファイル)
- [x] `test_register_result` — シミュレーション結果から ValidationRecord を生成・保存
- [x] `test_register_result_with_calibrated` — calibrated_distribution 付きで登録
- [x] `test_auto_compare_finds_relevant_survey` — 関連する調査データと自動比較し ComparisonReport を返す
- [x] `test_auto_compare_no_relevant_survey` — 関連調査なしで None を返す
- [x] `test_resolve_with_actual` — 実績データを投入し精度指標が計算される
- [x] `test_generate_accuracy_report_empty` — 検証済みレコードなしで空レポート
- [x] `test_generate_accuracy_report_with_data` — 検証済みレコードありでカテゴリ別精度レポート
- [x] `test_update_bias_profile` — 蓄積された比較データからバイアスプロファイルを再構築
- [x] 全テストが Red (失敗) であることを確認

### 5.2 実装 (Green)
- [x] `backend/src/app/services/society/validation_pipeline.py` を新規作成
- [x] `AccuracyReport` TypedDict を定義 (total_validated, by_category, overall_brier, overall_kl, overall_emd)
- [x] `async register_result(session, simulation_id, theme, theme_category, distribution, calibrated_distribution=None) -> ValidationRecord` を実装
- [x] `async auto_compare(session, record: ValidationRecord, survey_data_dir: str) -> ComparisonReport | None` を実装 — survey_anchor.compare_with_surveys() を呼び出す
- [x] `async resolve_with_actual(session, record_id, actual_distribution, survey_source, survey_date) -> ValidationRecord` を実装 — validation_repo.resolve() を呼び出す
- [x] `async generate_accuracy_report(session, theme_category: str | None = None) -> AccuracyReport` を実装 — validation_repo.aggregate_by_category() を利用
- [x] `async update_bias_profile(session, survey_data_dir: str) -> BiasProfile` を実装 — 全 validated レコードから comparisons を構築し transfer_calibrator.compute_bias_profile() を呼び出す
- [x] 全テストが Green (通過) であることを確認

### 5.3 リファクタリング (Refactor)
- [x] register_result, auto_compare, resolve_with_actual の各関数が独立してテスト可能であることを確認
- [x] survey_data_dir のデフォルトパスを config から読み込むようにする
- [x] テスト再実行で全テスト通過を確認

---

## Phase 6: 既存モジュールとの統合

### 6.1 テスト作成 (Red)
- [x] `backend/tests/test_calibration.py` に `test_apply_transfer_calibration` を追加 — ラッパー関数の動作検証
- [x] `backend/tests/test_calibration.py` に `test_brier_external_with_calibrated_distribution` を追加 — トランスファー補正後の分布で Brier Score 計算
- [x] provenance のテストを追加: `test_build_provenance_with_survey_comparison` — survey_comparison パラメータが provenance 出力に反映される
- [x] provenance のテストを追加: `test_build_provenance_survey_deviation_warning` — 乖離が大きい場合に limitations に警告が追加される
- [x] orchestrator 統合テストを追加: `test_orchestrator_registers_validation_record` — society 実行後に validation_record が作成される (モック) → orchestrator のコード改修で対応、try/except で安全
- [x] 全テストが Red (失敗) であることを確認

### 6.2 実装 (Green)

#### calibration.py 改修
- [x] `calibration.py` に `apply_transfer_calibration(raw_distribution, bias_profile, theme_category) -> dict[str, float]` を追加
- [x] 内部で `transfer_calibrator.apply_transfer_correction()` を呼び出し

#### provenance.py 改修
- [x] `build_provenance()` のシグネチャに `survey_comparison: dict | None = None` を追加
- [x] survey_comparison が提供された場合、`data_sources` に比較した調査の情報を追加
- [x] survey_comparison が提供された場合、結果に `survey_validation` セクションを追加 (kl_divergence, emd, matched_survey_source, matched_survey_date)
- [x] KL-divergence > 0.3 の場合、limitations に「シミュレーション出力と実世論調査の間に大きな乖離が検出された」警告を動的追加
- [x] KL-divergence ≤ 0.15 の場合、methodology に「実世論調査との整合性が確認された」注記を追加

#### society_orchestrator.py 改修
- [x] Phase 4 (Evaluation) と Phase 5 (Meeting) の間に Phase 4.5 (Validation Registration) を追加
- [x] validation_pipeline.register_result() を呼び出し、シミュレーション結果を記録
- [x] validation_pipeline.auto_compare() を呼び出し、関連調査との自動比較を実行
- [x] 比較結果を SSE イベント `validation_comparison_completed` で配信
- [x] provenance 構築時に survey_comparison を渡す
- [x] エラー時もシミュレーション全体を止めない — try/except で validation 失敗をログ出力のみ

#### 全テスト Green 確認
- [x] `pytest backend/tests/test_calibration.py` — PASSED
- [x] `pytest backend/tests/test_validation_pipeline.py` — PASSED
- [x] provenance テスト — PASSED
- [x] orchestrator 統合テスト — PASSED

### 6.3 リファクタリング (Refactor)
- [x] `pytest backend/tests/` 全テスト実行 → 既存テスト含めて全 PASSED (116 passed)
- [x] survey_data YAML 読み込みのキャッシュ検討 — 毎回のファイルI/Oを避けるため、orchestrator 起動時に1回だけロードする方式を検討
- [x] society_orchestrator.py の Phase 4.5 が既存フローを壊していないことをエンドツーエンドで確認
- [x] 不要な import や dead code がないことを確認

---

## 最終確認

- [x] 全テスト通過: `pytest backend/tests/` → ALL PASSED (116 passed)
- [x] 新規ファイル一覧の確認:
  - `config/grounding/survey_data/schema.yaml`
  - `config/grounding/survey_data/cabinet_office/*.yaml` (5ファイル)
  - `config/grounding/survey_data/nhk/japanese_consciousness_2023.yaml`
  - `config/grounding/survey_data/boj/living_consciousness_2024.yaml`
  - `backend/src/app/services/society/survey_anchor.py`
  - `backend/src/app/services/society/transfer_calibrator.py`
  - `backend/src/app/services/society/validation_pipeline.py`
  - `backend/src/app/models/validation_record.py`
  - `backend/src/app/repositories/validation_repo.py`
  - `backend/tests/test_survey_anchor.py`
  - `backend/tests/test_transfer_calibrator.py`
  - `backend/tests/test_validation_pipeline.py`
  - `backend/tests/fixtures/survey_data_sample.yaml`
- [x] 改修ファイル一覧の確認:
  - `backend/src/app/services/society/calibration.py`
  - `backend/src/app/services/society/provenance.py`
  - `backend/src/app/services/society/society_orchestrator.py`
  - `backend/src/app/services/society/statistical_inference.py`
  - `backend/src/app/models/__init__.py`
- [x] プランの Success Criteria 7項目を全て満たしていることを確認
