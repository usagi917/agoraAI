# agentAI 学術リファクタリング計画

## 概要

agentAI を「シンプル・高性能・学術レベル」に再構築する。

## 目標

1. **削る**: 9モード → 3モード、35テーブル → 12テーブル、59 API → 16 API
2. **委譲する**: 自作GraphRAG → LightRAG等の学術ライブラリに置換
3. **足す**: 再現性・評価フレームワーク・実験ログ・ベースライン比較

## ターゲットモード

| モード | 目的 |
|--------|------|
| `unified` | 主力。Society Pulse → Council → Synthesis の3フェーズ |
| `single` | 軽量。単体Runで素早い分析 |
| `baseline` | 学術比較用。単一LLMベースライン |

## フェーズ構成

```
Phase 0 (基盤整備)        → 1-2日
    ↓
Phase 1 (モード統合)      → 3-5日
    ↓
Phase 2 (DB統合)          → 2-3日
    ↓
Phase 3 (学術機能追加)    → 3-5日
    ↓
Phase 4 (GraphRAG/LLM)   → 3-4日
    ↓
Phase 5 (API/Frontend)   → 2-3日
    ↓
Phase 6 (仕上げ)         → 2-3日
```

## 依存関係

- Phase 1 → Phase 2（Swarm/Colony削除後にDBモデル統合）
- Phase 3, 4 は比較的並列可能
- Phase 5 は Phase 1-4 の完了後
- Phase 6 は全フェーズ完了後

## リスクと軽減策

1. **DBマイグレーションのデータロス** → Alembic downgrade テスト必須
2. **GraphRAG置換の品質劣化** → LegacyAdapter をフォールバックとして維持
3. **フロントエンド大幅変更** → 旧API互換レイヤーを一時維持
4. **LLMキャッシュ整合性** → 設定変更時の自動パージ

## 重要ファイル

- `backend/src/app/services/simulation_dispatcher.py` — 全モード分岐のハブ
- `backend/src/app/services/unified_orchestrator.py` — 主力オーケストレータ
- `backend/src/app/models/simulation.py` — DBモデル統合の中心
- `backend/src/app/api/routes/simulations.py` — 最大のAPIファイル
- `backend/src/app/services/society/evaluation.py` — 学術メトリクスの基盤
