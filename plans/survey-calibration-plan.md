# Implementation Plan: 実世論調査キャリブレーション基盤の構築

## Requirements Restatement

LLMマルチエージェント社会シミュレーションの出力精度を**測定可能**にするため、以下を構築する:

1. 内閣府世論調査・NHK・日銀の実データを構造化して格納
2. シミュレーション出力と実世論調査の分布乖離を定量測定するモジュール (`survey_anchor.py`)
3. LLM→Human のバイアス補正関数 (`transfer_calibrator.py`)
4. 継続的検証パイプライン (`validation_pipeline.py`) + DBテーブル
5. 既存モジュール (`calibration.py`, `provenance.py`, `society_orchestrator.py`) との統合

### スコープ外
- インターネットデータ連携（Phase 2以降）
- e-Stat API自動取得（手動YAML格納で開始）
- フロントエンドUI変更

---

## Risks & Mitigations

| リスク | 深刻度 | 対策 |
|--------|--------|------|
| 世論調査の質問形式とシミュレーションのスタンス形式が一致しない | HIGH | スタンスマッピング関数を設け、5段階(賛成〜反対)への正規化ルールを定義 |
| 世論調査データの手動入力が大量で品質管理が難しい | MEDIUM | YAML スキーマバリデーションをテストで担保、最初は5テーマに絞る |
| KL-divergence がゼロ除算になるケース(スタンスが0%の時) | MEDIUM | スムージング(additive smoothing)を適用 |
| トランスファー関数の過学習(少数のテーマで校正) | MEDIUM | テーマ数が少ない間は補正を控えめにし、信頼区間を広げる |
| 既存の society_orchestrator.py が複雑で統合が難しい | LOW | orchestrator への変更は最小限(1関数呼び出し追加のみ) |

---

## Architecture Overview

```
config/grounding/survey_data/
├── schema.yaml                    # YAMLスキーマ定義
├── cabinet_office/                # 内閣府世論調査
│   ├── diplomacy_2024.yaml
│   ├── social_awareness_2024.yaml
│   ├── nuclear_energy_2023.yaml
│   ├── aging_society_2023.yaml
│   └── defense_2024.yaml
├── nhk/                           # NHK放送文化研究所
│   └── japanese_consciousness_2023.yaml
└── boj/                           # 日銀生活意識アンケート
    └── living_consciousness_2024.yaml

backend/src/app/
├── models/
│   └── validation_record.py       # 新規: ValidationRecord モデル
├── repositories/
│   └── validation_repo.py         # 新規: ValidationRepository
└── services/society/
    ├── survey_anchor.py            # 新規: 世論調査アンカリング
    ├── transfer_calibrator.py      # 新規: LLM→Human補正
    ├── validation_pipeline.py      # 新規: 検証パイプライン
    ├── calibration.py              # 改修: トランスファー関数統合
    ├── provenance.py               # 改修: 乖離情報の自動追記
    └── society_orchestrator.py     # 改修: validation登録ステップ追加

backend/tests/
├── test_survey_anchor.py           # 新規
├── test_transfer_calibrator.py     # 新規
├── test_validation_pipeline.py     # 新規
└── fixtures/
    └── survey_data_sample.yaml     # 新規: テスト用世論調査データ
```

---

## Implementation Phases

### Phase 1: 世論調査データスキーマとローダー
**目的**: 世論調査データの構造を定義し、読み込めるようにする

#### Step 1.1: YAMLスキーマ定義とサンプルデータ作成
- `config/grounding/survey_data/schema.yaml` にスキーマを定義
- 各エントリの必須フィールド: theme, question, source, survey_date, sample_size, method, stance_distribution
- `stance_distribution` は5段階スタンス(賛成/条件付き賛成/中立/条件付き反対/反対)への正規化済み比率
- テスト用に `backend/tests/fixtures/survey_data_sample.yaml` を作成

#### Step 1.2: 内閣府世論調査データの格納 (5テーマ)
- 外交に関する世論調査 (2024)
- 社会意識に関する世論調査 (2024)
- 原子力に関する世論調査 (2023)
- 高齢社会に関する世論調査 (2023)
- 自衛隊・防衛問題に関する世論調査 (2024)
- 各テーマで主要な質問を2-3問ずつ、スタンス分布を手動入力

#### Step 1.3: NHK・日銀データの格納
- NHK「日本人の意識」調査 (2023) から主要テーマ3-5問
- 日銀「生活意識に関するアンケート調査」(2024) から経済テーマ3-5問

---

### Phase 2: survey_anchor.py — 世論調査アンカリングモジュール
**目的**: シミュレーション出力と実世論調査の分布乖離を測定する

#### Step 2.1: テスト作成 (Red)
- `test_survey_anchor.py` を作成
- テストケース:
  - `test_load_survey_data`: YAMLからの読み込みと構造バリデーション
  - `test_find_relevant_surveys`: テーマキーワードでの関連調査検索
  - `test_kl_divergence`: 2つのスタンス分布間のKL-divergence計算(スムージング付き)
  - `test_earth_movers_distance`: EMD計算(スタンスの序数距離考慮)
  - `test_compare_distributions`: シミュレーション出力と調査データの比較レポート生成
  - `test_empty_survey_data`: データなし時のグレースフルな処理
  - `test_stance_mapping`: 調査の回答選択肢→5段階スタンスへの変換

#### Step 2.2: 実装 (Green)
- `survey_anchor.py` に以下の関数を実装:
  - `load_survey_data(data_dir: str) -> list[SurveyRecord]`
  - `find_relevant_surveys(theme: str, surveys: list[SurveyRecord], top_k: int = 5) -> list[SurveyRecord]`
  - `kl_divergence_symmetric(p: dict[str, float], q: dict[str, float], smoothing: float = 1e-6) -> float`
  - `earth_movers_distance(p: dict[str, float], q: dict[str, float]) -> float`
  - `compare_with_surveys(simulation_distribution: dict[str, float], theme: str, data_dir: str) -> ComparisonReport`
- `SurveyRecord` と `ComparisonReport` は TypedDict で定義
- キーワードマッチングは既存の `_ngrams` + Jaccard (backtest.py のパターン) を流用

#### Step 2.3: リファクタリング (Refactor)
- backtest.py から `_ngrams`, `_jaccard` を共通ユーティリティに抽出するか、survey_anchor 内で再利用可能にする
- `evaluation.py` の既存 `kl_divergence()` との整合性を確認し、重複を排除

---

### Phase 3: transfer_calibrator.py — LLM→Human バイアス補正
**目的**: LLMエージェントの系統的バイアスを検出・補正する関数を実装

#### Step 3.1: テスト作成 (Red)
- `test_transfer_calibrator.py` を作成
- テストケース:
  - `test_compute_bias_profile`: シミュレーション分布と実分布の差からバイアスプロファイルを構築
  - `test_apply_transfer_correction`: バイアスプロファイルによる分布補正
  - `test_correction_preserves_normalization`: 補正後も分布の合計が1.0
  - `test_no_correction_when_insufficient_data`: テーマ別データが少ない場合は補正しない
  - `test_confidence_interval_widening`: 補正による不確実性の拡大
  - `test_bias_profile_by_theme_category`: テーマカテゴリ別のバイアスプロファイル

#### Step 3.2: 実装 (Green)
- `transfer_calibrator.py` に以下の関数を実装:
  - `compute_bias_profile(comparisons: list[ComparisonReport]) -> BiasProfile`
    - テーマカテゴリ別に (LLM分布 - 実分布) の平均ズレを計算
  - `apply_transfer_correction(distribution: dict[str, float], bias_profile: BiasProfile, theme_category: str) -> dict[str, float]`
    - バイアスプロファイルが十分なデータに基づく場合のみ補正適用
    - 補正強度は比較データ数に応じて減衰 (shrinkage)
  - `compute_transfer_uncertainty(bias_profile: BiasProfile, theme_category: str) -> float`
    - トランスファー補正による追加の不確実性を推定
- `BiasProfile` は TypedDict: `{category: {stance: mean_deviation, sample_count, std_deviation}}`

#### Step 3.3: リファクタリング (Refactor)
- `statistical_inference.py` の `bootstrap_confidence_intervals()` にトランスファー不確実性を加算するオプションを追加
- `calibration.py` にトランスファー後の Brier Score 計算を統合

---

### Phase 4: ValidationRecord モデルとリポジトリ
**目的**: シミュレーション結果と実績の対を永続化するDB基盤を構築

#### Step 4.1: テスト作成 (Red)
- `test_validation_pipeline.py` を作成 (DB部分)
- テストケース:
  - `test_create_validation_record`: レコード作成と保存
  - `test_record_with_pending_actual`: actual_distribution が null のレコード
  - `test_resolve_validation`: 実績データ投入と精度指標自動算出
  - `test_list_by_theme_category`: テーマカテゴリでのフィルタリング
  - `test_aggregate_accuracy_stats`: テーマカテゴリ別の精度統計

#### Step 4.2: 実装 (Green)
- `models/validation_record.py`:
  ```python
  class ValidationRecord(Base):
      id: Mapped[str]               # UUID
      simulation_id: Mapped[str]    # FK → Simulation
      theme_text: Mapped[str]
      theme_category: Mapped[str]   # economy | social | politics | ...
      simulated_distribution: Mapped[dict]   # JSON
      calibrated_distribution: Mapped[dict | None]  # JSON (トランスファー補正後)
      actual_distribution: Mapped[dict | None]  # JSON (実績未確定時 null)
      survey_source: Mapped[str | None]
      survey_date: Mapped[str | None]
      brier_score: Mapped[float | None]
      ece: Mapped[float | None]
      kl_divergence: Mapped[float | None]
      emd: Mapped[float | None]
      validated_at: Mapped[datetime | None]
      created_at: Mapped[datetime]
  ```
- `repositories/validation_repo.py`:
  - `save(record)`, `get(id)`, `list_by_simulation(sim_id)`, `list_by_category(category)`
  - `resolve(id, actual_distribution, survey_source, survey_date)` — 実績投入 + 精度指標自動算出
  - `aggregate_by_category()` — カテゴリ別の平均 Brier/ECE/KL

#### Step 4.3: リファクタリング (Refactor)
- 既存の `EvaluationResult` モデルとの関係整理
- `__init__.py` の model import に追加

---

### Phase 5: validation_pipeline.py — 検証パイプライン
**目的**: シミュレーション実行→記録→事後検証のフローを自動化

#### Step 5.1: テスト作成 (Red)
- `test_validation_pipeline.py` にパイプラインテストを追加
- テストケース:
  - `test_register_simulation_result`: シミュレーション結果を validation_record に登録
  - `test_auto_compare_with_surveys`: 関連する過去調査との自動比較
  - `test_update_bias_profile`: 蓄積された比較データからバイアスプロファイル更新
  - `test_generate_accuracy_report`: テーマカテゴリ別の精度レポート生成

#### Step 5.2: 実装 (Green)
- `validation_pipeline.py` に以下の関数を実装:
  - `async register_result(session, simulation_id, theme, distribution, calibrated_distribution) -> ValidationRecord`
  - `async auto_compare(session, record: ValidationRecord, survey_data_dir: str) -> ComparisonReport | None`
  - `async resolve_with_actual(session, record_id, actual_distribution, survey_source, survey_date) -> ValidationRecord`
  - `async generate_accuracy_report(session, theme_category: str | None = None) -> AccuracyReport`
  - `async update_bias_profile(session, survey_data_dir: str) -> BiasProfile`

#### Step 5.3: リファクタリング (Refactor)
- パイプライン内の各ステップが独立してテスト可能であることを確認
- エラーハンドリングの統一

---

### Phase 6: 既存モジュールとの統合
**目的**: 新規モジュールを既存のオーケストレーションフローに組み込む

#### Step 6.1: テスト作成 (Red)
- 既存テストファイルに統合テストを追加:
  - `test_calibration.py` に `test_brier_with_transfer_correction` 追加
  - `test_provenance.py` (or inline) に `test_provenance_includes_survey_deviation` 追加
  - orchestrator のモック統合テスト

#### Step 6.2: 実装 (Green)

**calibration.py の改修**:
- `apply_transfer_calibration(raw_distribution, bias_profile, theme_category) -> dict[str, float]` を追加
- 既存の `brier_external()` はそのまま維持(新旧比較用)

**provenance.py の改修**:
- `build_provenance()` に `survey_comparison: dict | None = None` パラメータを追加
- `survey_comparison` が提供された場合、以下を provenance に追記:
  - `survey_reference`: 比較した調査名・日付
  - `distribution_deviation`: KL-divergence, EMD の値
  - limitations に乖離の大きさに応じた警告を動的追加

**society_orchestrator.py の改修**:
- Phase 4 (Evaluation) の後に validation 登録ステップを追加:
  ```python
  # Phase 4.5: Validation Registration
  from src.app.services.society.validation_pipeline import register_result, auto_compare
  validation_record = await register_result(session, simulation_id, theme, distribution, calibrated_dist)
  comparison = await auto_compare(session, validation_record, survey_data_dir)
  ```
- provenance 構築時に comparison 結果を渡す

#### Step 6.3: リファクタリング (Refactor)
- 統合後の全テスト実行
- パフォーマンス確認(survey_data の読み込みがボトルネックにならないこと)

---

## Dependencies Between Phases

```
Phase 1 (データ) ──→ Phase 2 (survey_anchor) ──→ Phase 3 (transfer_calibrator)
                                                        │
Phase 4 (DB モデル) ──→ Phase 5 (validation_pipeline) ←─┘
                                                        │
                           Phase 6 (統合) ←─────────────┘
```

- Phase 1 は全ての前提条件
- Phase 2 と Phase 4 は並行作業可能
- Phase 3 は Phase 2 の ComparisonReport 型に依存
- Phase 5 は Phase 2, 3, 4 全てに依存
- Phase 6 は全フェーズ完了後

---

## Estimated Complexity

| Phase | 複雑度 | 新規ファイル | 改修ファイル |
|-------|--------|------------|------------|
| Phase 1 | LOW | 8 YAML | 0 |
| Phase 2 | MEDIUM | 2 (.py + test) | 0 |
| Phase 3 | MEDIUM | 2 (.py + test) | 2 (calibration, statistical_inference) |
| Phase 4 | LOW | 2 (model + repo) | 0 |
| Phase 5 | MEDIUM | 1 (.py) | 0 |
| Phase 6 | MEDIUM | 0 | 3 (calibration, provenance, orchestrator) |

---

## Success Criteria

1. `pytest backend/tests/test_survey_anchor.py` — 全テスト通過
2. `pytest backend/tests/test_transfer_calibrator.py` — 全テスト通過
3. `pytest backend/tests/test_validation_pipeline.py` — 全テスト通過
4. 内閣府5テーマでシミュレーション実行 → KL-divergence, EMD が数値として出力される
5. provenance に世論調査との乖離情報が自動追記される
6. `validation_records` テーブルにシミュレーション結果が自動登録される
7. 既存テスト (`pytest backend/tests/`) が全て通過し続ける

---

**WAITING FOR CONFIRMATION**: このプランで進めてよいですか? (yes / modify / 別のアプローチ)
