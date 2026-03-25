# agentAI 学術リファクタリング タスクリスト

## Phase 0: 基盤整備とテストインフラ

### 0.1 テスト実行環境の確認・修復
- [ ] 既存テスト37ファイルの全実行と結果確認
- [ ] 失敗テストの修正
- [ ] `pytest-cov` でベースラインカバレッジ計測

### 0.2 リファクタリング用ブランチ戦略
- [ ] `refactor/v2` ブランチ作成

### 0.3 DB マイグレーション戦略
- [ ] Alembic 導入（`pyproject.toml` に追加）
- [ ] `alembic init` でディレクトリ構成作成
- [ ] `alembic/env.py` に async engine 設定
- [ ] 初期マイグレーション生成（現状スキーマのベースライン）
- [ ] upgrade/downgrade のテスト

### 0.4 設定バリデーション強化
- [ ] `config.py` に Pydantic validator 追加
- [ ] YAML設定スキーマのバリデーションテスト作成

---

## Phase 1: 実行モード統合とオーケストレータ整理

### 1.1 Simulation モデルの mode フィールド変更
- [ ] テスト作成: 旧モード → 新モードリマップの単体テスト
- [ ] `Simulation.mode` バリデーションを `unified | single | baseline` に変更
- [ ] 旧モード値のエイリアスマッピング追加
- [ ] テスト実行・パス確認

### 1.2 simulation_dispatcher.py のルーティング削減
- [ ] テスト作成: 3モード dispatch の単体テスト
- [ ] `pipeline`, `meta_simulation`, `society`, `society_first`, `swarm`, `hybrid`, `pm_board` 分岐削除
- [ ] `unified`, `single`, `baseline` の3分岐のみに
- [ ] テスト実行・パス確認

### 1.3 不要オーケストレータの削除
- [ ] テスト作成: 削除後のインポートエラーがないことの確認テスト
- [ ] `pipeline_orchestrator.py` 削除
- [ ] `swarm_orchestrator.py` 削除
- [ ] `pm_board_orchestrator.py` 削除
- [ ] `meta_orchestrator.py` 削除
- [ ] `society_first_orchestrator.py` 削除
- [ ] `meta_intervention_planner.py` 削除
- [ ] `swarm_report_generator.py` 削除
- [ ] `colony_factory.py` 削除
- [ ] `claim_extractor.py` 削除
- [ ] `claim_clusterer.py` 削除
- [ ] `final_report_generator.py` 削除
- [ ] `pipeline_fallbacks.py` 削除
- [ ] 関連テストファイルの削除・更新
- [ ] 全テスト実行・パス確認

### 1.4 unified_orchestrator.py の強化
- [ ] テスト作成: PM分析あり/なしの統合テスト
- [ ] `use_pm_analysis: bool` パラメータ追加
- [ ] PM Board 分析を Synthesis フェーズに統合
- [ ] テスト実行・パス確認

### 1.5 single モードの簡素化
- [ ] テスト作成: single モードの E2E テスト
- [ ] `simulator.py` から Colony 関連ロジック除去
- [ ] `colony_config` パラメータ削除
- [ ] テスト実行・パス確認

### 1.6 baseline モードの新設
- [ ] テスト作成: baseline モードの単体テスト（シード再現性含む）
- [ ] `baseline_orchestrator.py` 新規作成
- [ ] 単一 LLM プロンプト分析の実装
- [ ] unified と同じフォーマットでの結果保存
- [ ] シード固定による決定論的実行
- [ ] テスト実行・パス確認

---

## Phase 2: DB モデル統合

### 2.1 新モデルの追加（破壊的変更なし）
- [ ] テスト作成: 新モデル CRUD テスト
- [ ] `LLMCallLog` モデル作成
- [ ] `ExperimentConfig` モデル作成
- [ ] `Simulation` に新フィールド追加（`name`, `description`, `input_documents`, `seed`, `config_snapshot`）
- [ ] Alembic マイグレーション生成
- [ ] テスト実行・パス確認

### 2.2 データアクセス抽象化レイヤー導入
- [ ] テスト作成: リポジトリ CRUD テスト
- [ ] `repositories/` ディレクトリ新設
- [ ] `SimulationRepository` 作成
- [ ] `AgentRepository` 作成
- [ ] `KGRepository` 作成
- [ ] `EvaluationRepository` 作成
- [ ] テスト実行・パス確認

### 2.3 オーケストレータのリポジトリ移行
- [ ] `unified_orchestrator.py` を Repository 経由に書き換え
- [ ] `simulator.py` を Repository 経由に書き換え
- [ ] 既存 E2E テスト実行・パス確認

### 2.4 旧モデルの段階的削除
- [ ] テスト作成: 削除後の CRUD テスト
- [ ] `Project` モデル削除（Simulation に統合）
- [ ] `Document` モデル削除（JSON フィールドに）
- [ ] `Run` モデル削除
- [ ] `Swarm` モデル削除
- [ ] `Colony` モデル削除
- [ ] `WorldState` モデル削除
- [ ] `GraphState` / `GraphDiff` 削除
- [ ] `TimelineEvent` 削除
- [ ] `Report` モデル削除（SocietyResult に統合）
- [ ] `Followup` 削除
- [ ] `OutcomeClaim` / `ClaimCluster` / `AggregationResult` 削除
- [ ] `CalibrationData` 削除（EvaluationResult に統合）
- [ ] `SocialEdge` 削除
- [ ] `Community` 削除（KGNode 属性に）
- [ ] `EnvironmentRule` 削除
- [ ] `EvaluationScore` 削除（EvaluationResult に統合）
- [ ] Alembic マイグレーション生成
- [ ] 全テスト実行・パス確認

---

## Phase 3: 学術機能の追加

### 3.1 再現性（Reproducibility）
- [ ] テスト作成: シード制御の再現性テスト
- [ ] `Simulation.seed` フィールド追加
- [ ] シミュレーション開始時のシードセット処理
- [ ] LLM 呼び出しの `temperature=0` + `seed` オプション
- [ ] テスト: 同一シード・同一入力で同一結果

- [ ] テスト作成: 設定スナップショットの保存・復元テスト
- [ ] `ExperimentConfig` への自動スナップショット実装
- [ ] YAML設定 + モデルID + パッケージバージョンの記録

- [ ] テスト作成: 決定論的実行テスト
- [ ] `deterministic: bool` フラグ実装
- [ ] async 実行順序の固定化

### 3.2 評価フレームワーク
- [ ] テスト作成: 各メトリクスの計算精度テスト
- [ ] `evaluation/metrics/` モジュール新設
- [ ] `BaseMetric` 抽象基底クラス作成
- [ ] 既存メトリクス移行（diversity_index, internal_consistency, calibration_score, brier_score）

- [ ] テスト作成: KG品質メトリクスのテスト
- [ ] `kg_precision` 実装
- [ ] `kg_recall` 実装
- [ ] `kg_f1` 実装
- [ ] `entity_coverage` 実装
- [ ] `relation_accuracy` 実装

- [ ] テスト作成: エージェント合意メトリクスのテスト
- [ ] `fleiss_kappa` 実装
- [ ] `consensus_convergence` 実装
- [ ] `belief_stability` 実装

- [ ] テスト作成: 予測精度メトリクスのテスト
- [ ] `prediction_accuracy` 実装
- [ ] `scenario_calibration` 実装

### 3.3 実験ログ
- [ ] テスト作成: LLM呼び出しログのテスト
- [ ] `LLMCallLog` 記録インターセプター実装
- [ ] `multi_client.py` への組み込み
- [ ] プロンプト全文のオプション保存

- [ ] テスト作成: エージェント状態遷移ログのテスト
- [ ] BDI belief/desire/intention 変化の `ConversationLog` 記録
- [ ] `phase = "bdi_transition"` タイプ定義

- [ ] テスト作成: 構造化実験レポートのテスト
- [ ] JSON/YAML 実験レポートテンプレート作成
- [ ] 完了時の自動レポート生成

### 3.4 ベースライン比較
- [ ] テスト作成: 比較レポート生成のテスト
- [ ] baseline vs unified の自動比較ロジック
- [ ] メトリクス差分・判断差分・根拠差分の計算
- [ ] `GET /simulations/{id1}/compare/{id2}` API 実装
- [ ] テスト実行・パス確認

---

## Phase 4: GraphRAG 置換と LLM クライアント統合

### 4.1 LLM クライアント統合
- [ ] テスト作成: 統合クライアントの単体テスト
- [ ] `client.py` を `multi_client.py` のラッパーに書き換え
- [ ] task_name ベースのモデル選択を統合
- [ ] テスト実行・パス確認

- [ ] テスト作成: LLMキャッシュのテスト
- [ ] Redis ベースのキャッシュ層追加
- [ ] キャッシュキー: `hash(prompt + model + temperature)`
- [ ] TTL 設定の実装
- [ ] テスト: 2回目呼び出しのキャッシュヒット確認

- [ ] テスト作成: LLMCallLog インターセプターのテスト
- [ ] デコレータパターンで `multi_client.py` に組み込み

### 4.2 GraphRAG 置換
- [ ] LightRAG / nano-graphrag の API 調査
- [ ] 既存 GraphRAGPipeline との機能マッピング作成
- [ ] `pyproject.toml` に依存追加

- [ ] テスト作成: アダプターの出力比較テスト
- [ ] `services/graphrag/adapter.py` 新設
- [ ] `GraphRAGAdapter` 抽象基底クラス定義
- [ ] `LightRAGAdapter` 実装
- [ ] `LegacyAdapter`（フォールバック）実装

- [ ] テスト作成: KG生成の統合テスト
- [ ] `GraphRAGPipeline` 内部を `LightRAGAdapter` に差し替え
- [ ] `KnowledgeGraph` インターフェース維持確認

- [ ] 自作 GraphRAG コード削除
  - [ ] `chunker.py` 削除
  - [ ] `entity_extractor.py` 削除
  - [ ] `relation_extractor.py` 削除
  - [ ] `dedup_resolver.py` 削除
  - [ ] `community_detector.py` 削除
  - [ ] `ontology_generator.py` 削除
- [ ] `pipeline.py` をアダプター委譲のみに簡素化
- [ ] 全テスト実行・パス確認

---

## Phase 5: API 整理とフロントエンド対応

### 5.1 API ルート統合
- [ ] テスト作成: 新API 16エンドポイントの正常系・異常系テスト
- [ ] `runs.py` 削除
- [ ] `swarms.py` 削除
- [ ] `admin.py` 必要機能を simulations に統合後削除
- [ ] `stream.py` を simulations に統合後削除
- [ ] `projects.py` 削除
- [ ] `templates.py` 内部ヘルパー化
- [ ] `simulations.py` を16エンドポイントに書き直し
- [ ] `society.py` を Population 関連のみに簡素化
- [ ] テスト実行・パス確認

### 5.2 フロントエンド対応
- [ ] `frontend/src/api/client.ts` を新API対応に更新
- [ ] LaunchPadPage のモード選択を3モードに変更
- [ ] ResultsPage のモード別分岐を3モードに統合
- [ ] baseline 比較ビュー追加
- [ ] 不要コンポーネント削除（ColonyGrid 等）
- [ ] EvaluationDashboard に新メトリクス可視化追加
- [ ] `pnpm test:unit` 全パス確認

---

## Phase 6: エージェントインタビュー、ドキュメント、最終品質調整

### 6.1 エージェントインタビュー機能
- [ ] テスト作成: インタビューAPI のテスト
- [ ] `POST /simulations/{id}/interview` エンドポイント追加
- [ ] BDI状態・メモリ参照の応答生成ロジック
- [ ] ResultsPage にインタビューパネル追加
- [ ] テスト実行・パス確認

### 6.2 メモリシステム確認
- [ ] 現状の3層（episodic, semantic, procedural）構造を確認
- [ ] `retrieval.py`, `reflection.py` をユーティリティとして維持
- [ ] 不要コードがあれば削除

### 6.3 ドキュメント整備
- [ ] README のアーキテクチャ図更新（3モード構成）
- [ ] API リファレンス更新
- [ ] クイックスタートガイド更新
- [ ] BDI エンジンのアルゴリズム記述（学術論文向け）
- [ ] 評価メトリクスの数学的定義（学術論文向け）
- [ ] 再現性プロトコルの記述（学術論文向け）

### 6.4 カバレッジ目標達成
- [ ] `pytest --cov` 実行、80%未満のモジュール特定
- [ ] `unified_orchestrator.py` のテスト強化
- [ ] `evaluation/metrics/` のテスト強化
- [ ] `multi_client.py` のエラーハンドリングテスト強化
- [ ] 最終カバレッジ 80% 以上達成確認
