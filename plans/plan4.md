# agentAI リファクタリング計画 v4 — フェーズ部品化

## 設計原則

```
1. 機能は削除しない。移植する。
2. 各フェーズは独立した小さいファイル（100-200行）
3. プリセットで組み合わせる（ユーザーは名前を選ぶだけ）
4. 各フェーズは単独でテスト可能
```

---

## 現状分析: 各オーケストレータの固有能力

| オーケストレータ | 固有能力（これを失うと品質低下） |
|----------------|-------------------------------|
| `swarm` | 多視点Colony並列 → Claim抽出 → クラスタリング → シナリオ合成 |
| `pm_board` | 3PMペルソナ並列分析 → Chief PM統合 → 11セクション構造 |
| `pipeline` | Single→Swarm→PM の段階的コンテキスト変換 |
| `society_first` | 社会調査 → イシュー抽出 → イシュー別深掘り → 介入比較 |
| `meta` | 反復ループ（最大5サイクル）→ 介入テスト → 収束判定 |
| `unified` | Society Pulse → Council → Synthesis + KG進化 + ReACT |

---

## ターゲット設計

### フェーズ部品（`services/phases/` に配置）

```
services/phases/
├── society_pulse.py          ← 既存（そのまま）
├── council_deliberation.py   ← 既存（そのまま）
├── synthesis.py              ← 既存（そのまま）
├── multi_perspective.py      ← 新規: swarm_orchestrator から移植
├── pm_analysis.py            ← 新規: pm_board_orchestrator から移植
├── issue_mining.py           ← 新規: society_first_orchestrator から移植
└── intervention.py           ← 新規: meta_orchestrator から移植
```

各フェーズは同じインターフェース:
```python
@dataclass
class PhaseResult:
    data: dict
    usage: dict

async def run_xxx(session, sim, context: dict, **kwargs) -> XxxResult:
    """独立して実行可能。他フェーズに依存しない。"""
```

### プリセット（ユーザーが選ぶもの）

```
┌──────────┬──────────────────────────────────────────────────────────────┐
│ preset   │ フェーズ構成                                                 │
├──────────┼──────────────────────────────────────────────────────────────┤
│ quick    │ society_pulse → synthesis                                    │
│          │ （素早い社会反応サーベイ + レポート）                            │
├──────────┼──────────────────────────────────────────────────────────────┤
│ standard │ society_pulse → council → synthesis                         │
│          │ （現在の unified と同じ。社会調査 + 評議会 + 統合）              │
├──────────┼──────────────────────────────────────────────────────────────┤
│ deep     │ society_pulse → multi_perspective → council                 │
│          │ → pm_analysis → synthesis                                    │
│          │ （全フェーズ投入。最高品質。旧 pipeline 相当）                   │
├──────────┼──────────────────────────────────────────────────────────────┤
│ research │ society_pulse → issue_mining → multi_perspective            │
│          │ → intervention → synthesis                                   │
│          │ （旧 society_first + meta 相当。イシュー深掘り + 介入テスト）    │
├──────────┼──────────────────────────────────────────────────────────────┤
│ baseline │ （単一LLM。エージェントなし。学術比較用）                       │
└──────────┴──────────────────────────────────────────────────────────────┘
```

### unified_orchestrator.py（薄い関数になる）

```python
PRESETS = {
    "quick":    ["society_pulse", "synthesis"],
    "standard": ["society_pulse", "council", "synthesis"],
    "deep":     ["society_pulse", "multi_perspective", "council", "pm_analysis", "synthesis"],
    "research": ["society_pulse", "issue_mining", "multi_perspective", "intervention", "synthesis"],
}

async def run_unified(simulation_id: str) -> None:
    sim = await session.get(Simulation, simulation_id)
    preset = sim.execution_profile  # quick / standard / deep / research
    phases = PRESETS[preset]

    context = {"theme": sim.prompt_text}
    for phase_name in phases:
        result = await run_phase(phase_name, session, sim, context)
        context.update(result.data)  # 前フェーズの出力を次フェーズの入力に
        await checkpoint(session, sim, phase_name, result)

    sim.status = "completed"
```

---

## Phase 1: フェーズ部品化（機能移植）

### 1.1 multi_perspective.py — swarm の中身を移植

**移植元:** `swarm_orchestrator.py` の以下のロジック
- Colony並列実行（asyncio.Semaphore制御）
- world_state のクローン
- 各Colonyの独立実行
- Claim抽出 → クラスタリング → シナリオ集約
- 統合レポート生成

**新ファイル:** `services/phases/multi_perspective.py`

```python
@dataclass
class MultiPerspectiveResult:
    perspectives: list[dict]    # 各視点の分析結果
    scenarios: list[dict]       # 集約されたシナリオ
    agreement_matrix: dict      # 視点間合意度
    integrated_report: str      # 統合レポート
    usage: dict

async def run_multi_perspective(
    session, sim, context: dict,
    perspective_count: int = 5,
    max_concurrent: int = 5,
) -> MultiPerspectiveResult:
    """複数視点で並列分析し、シナリオに集約する。"""
```

**保持する機能:**
- [ ] Colony並列実行（Semaphore制御）
- [ ] world_state クローン
- [ ] Claim抽出（claim_extractor.py はそのまま利用）
- [ ] Claimクラスタリング（claim_clusterer.py はそのまま利用）
- [ ] シナリオ集約
- [ ] agreement_matrix 計算
- [ ] 統合レポート生成（swarm_report_generator.py はそのまま利用）

**削除するもの:** swarm_orchestrator.py のファイル自体（中身は移植済み）

---

### 1.2 pm_analysis.py — PM Board の中身を移植

**移植元:** `pm_board_orchestrator.py` の以下のロジック
- YAMLからPMペルソナテンプレート読み込み
- 3ペルソナ並列分析
- Chief PM統合
- 11セクション構造化出力
- エビデンス参照・品質ゲート

**新ファイル:** `services/phases/pm_analysis.py`

```python
@dataclass
class PMAnalysisResult:
    analyses: list[dict]        # 各PMの分析
    synthesis: dict             # Chief PM統合
    sections: dict              # 11セクション構造
    decision_brief: dict        # PM視点のDecision Brief
    usage: dict

async def run_pm_analysis(
    session, sim, context: dict,
) -> PMAnalysisResult:
    """3PMペルソナ + Chief PMによる構造化分析。"""
```

**保持する機能:**
- [ ] PMテンプレートYAML読み込み
- [ ] 3ペルソナ並列実行（strategy_pm, discovery_pm, execution_pm）
- [ ] Chief PM統合（矛盾検出含む）
- [ ] 11セクション構造（core_question〜top_5_actions）
- [ ] フォールバック合成（LLM失敗時）
- [ ] エビデンス参照・品質ゲート

---

### 1.3 issue_mining.py — Society First の中身を移植

**移植元:** `society_first_orchestrator.py`
**既存:** `society/issue_miner.py` を内部で利用

**新ファイル:** `services/phases/issue_mining.py`

```python
@dataclass
class IssueMiningResult:
    issues: list[dict]               # ランク付きイシュー
    issue_analyses: list[dict]       # イシュー別深掘り結果
    intervention_comparison: dict    # 介入比較
    usage: dict

async def run_issue_mining(
    session, sim, context: dict,
    max_issues: int = 3,
) -> IssueMiningResult:
    """社会調査結果からイシューを抽出し、各イシューを深掘りする。"""
```

**保持する機能:**
- [ ] イシュー候補抽出（issue_miner.py 利用）
- [ ] イシュー別Colony深掘り
- [ ] 介入比較（build_intervention_comparison）
- [ ] バックテスト結果オーバーレイ

---

### 1.4 intervention.py — Meta の中身を移植

**移植元:** `meta_orchestrator.py`
**既存:** `meta_intervention_planner.py` を内部で利用

**新ファイル:** `services/phases/intervention.py`

```python
@dataclass
class InterventionResult:
    cycles: list[dict]           # 各サイクルの結果
    best_cycle: dict             # 最良サイクル
    interventions: list[dict]    # テストした介入策
    convergence_score: float     # 収束度
    usage: dict

async def run_intervention(
    session, sim, context: dict,
    max_cycles: int = 3,
    target_score: float = 0.8,
) -> InterventionResult:
    """反復ループで介入策をテストし、最良の結果を選択する。"""
```

**保持する機能:**
- [ ] 反復ループ（max_cycles制御）
- [ ] 介入計画（meta_intervention_planner.py 利用）
- [ ] 介入注入（次サイクルのプロンプトに反映）
- [ ] 目的スコア計算（compute_objective_score）
- [ ] 収束判定（evaluate_stop_condition）
- [ ] 最良サイクル選択

---

### 1.5 unified_orchestrator.py のリファクタ

**変更:** プリセット駆動のフェーズ合成に書き換え

```python
# Before: ハードコードされた3フェーズ
pulse = await run_society_pulse(...)
council = await run_council(...)
synthesis = await run_synthesis(...)

# After: プリセットに応じてフェーズを動的に合成
for phase_name in PRESETS[preset]:
    result = await PHASE_RUNNERS[phase_name](session, sim, context)
    context.update(result)
```

**変更しないもの:**
- KG進化トラッキング（context経由で引き継ぎ）
- フェーズチェックポイント（各フェーズ後にcommit）
- SSEイベント配信（各フェーズ開始/完了時）
- ReACTレポーター（synthesis フェーズ内で利用）

---

### 1.6 baseline_orchestrator.py 新設

現行 plan3 と同じ。単一LLMベースライン。

---

### 1.7 simulation_dispatcher.py 書き換え

```python
async def dispatch_simulation(simulation_id: str) -> None:
    sim = await session.get(Simulation, simulation_id)
    mode = normalize_mode(sim.mode)

    if mode == "baseline":
        await run_baseline(sim.id)
    else:
        # quick / standard / deep / research は全て unified が処理
        await run_unified(sim.id)
```

---

### 1.8 旧オーケストレータファイル削除

中身を移植済みなので安全に削除:
- `pipeline_orchestrator.py` → 段階実行は deep プリセットで再現
- `swarm_orchestrator.py` → multi_perspective.py に移植済み
- `pm_board_orchestrator.py` → pm_analysis.py に移植済み
- `society_first_orchestrator.py` → issue_mining.py に移植済み
- `meta_orchestrator.py` → intervention.py に移植済み

**削除しないサポートファイル:**
- `claim_extractor.py` — multi_perspective.py が利用
- `claim_clusterer.py` — multi_perspective.py が利用
- `swarm_report_generator.py` — multi_perspective.py が利用
- `meta_intervention_planner.py` — intervention.py が利用
- `react_reporter.py` — synthesis.py が利用
- `final_report_generator.py` — synthesis.py が利用（deep時）

---

## Phase 2: DB モデル整理

plan3 と同じ方針。35テーブル → 12テーブル。
ただし WorldState, GraphState は **metadata_json に構造化格納** してスナップショット能力を維持。

---

## Phase 3: 学術機能追加

plan3 と同じ。再現性、評価フレームワーク、実験ログ、ベースライン比較。

---

## Phase 4: GraphRAG

**修正:** 全面置換ではなく **アダプター層 + ベンチマーク比較**。
- 自作実装を `LegacyAdapter` として残す
- LightRAG を `LightRAGAdapter` として追加
- ベンチマークで品質比較してから切り替え判断

---

## Phase 5: API整理 + フロントエンド

- API: プリセット選択UIに対応（quick/standard/deep/research/baseline）
- フロントエンド: モード選択を5プリセットのシンプルなカード選択に

---

## 品質保証チェックリスト

### 各フェーズ移植時の確認事項

```
□ 旧オーケストレータの全関数が新フェーズに移植されているか
□ 旧テストが新フェーズのテストに変換されているか
□ 旧オーケストレータの呼び出し元が全て新フェーズに切り替わっているか
□ プリセット経由で旧モードと同等の出力が得られるか（回帰テスト）
□ サポートファイル（claim_extractor等）への依存が維持されているか
```

### 出力品質の回帰テスト

```
□ standard プリセット → 旧 unified と同じ出力構造
□ deep プリセット → 旧 pipeline と同等以上の分析深度
□ research プリセット → 旧 society_first + meta と同等のイシュー分析
□ baseline → 単一LLMの出力（新規、比較基準）
```
