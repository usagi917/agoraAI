# 要件定義: Decision Brief 議論ハイライト機能 (Phase 1)

**バージョン**: v2.1 (autoplan CEO + Design + Eng レビュ���全反映)
**ブランチ**: scenario-comparison-validation-followups-20260407
**作成日**: 2026-04-13
**レビュー**: CEO Review (Claude + Codex dual voice), Design Review, Eng Review

---

## 1. 概要

### 1.1 目的

Decision Brief は現在「結論だけを返すサマリー」だが、「どの会話が結論を動かしたか」が見えない。
議論ハイライト機能を追加し、ユーザーが「結論 → なぜそうなったか → 何が未解決か」の読み筋で
Decision Brief を理解できるようにする。

### 1.2 ターゲットユーザー

地方議員（低デジタルリテラシー）。TurboTax モデル: 入力は極限まで簡��、出力はプロ品質のレポート。
4カテゴリの分析者向け分類ではな���、「合意されたこと」「まだ割れていること」の2軸で直感的に読める UI にする。

### 1.3 スコープ

**In:**
- Decision Brief に `conversation_highlights` セクションを追加
- 既存の LLM ベース `extract_conversation_highlights()` を統一スキーマに適応
- Backend のデータ生成・返却
- Frontend の UI 表示
- テスト

**Out:**
- 会話全文の常時表示
- Transcript 機能の全面置換
- 新規 LLM プロンプトの最適化（Phase 2）
- インラ��ン表示（Phase 2。データモデルに `linked_to` を設けて将来対応）

---

## 2. 方針決定 (autoplan レビュー結果)

### 2.1 抽出方式: 既存 LLM 関数の適応

**決定**: 既存の `extract_conversation_highlights()` (`conversation_highlights.py`) を
Decision Brief 向けに適応する。新たに rule-based 関数を作らない。

**理由**:
- 既に `synthesis.py:362` で council データから LLM 抽出が走っている
- rule-based は機械的で低品質な出力になるリスクが高い（Codex/Claude subagent 両方が指摘）
- 既存コード再利用で実装量を削減

**変更点**:
- `extract_conversation_highlights()` のプロンプトを拡張し、Decision Brief 用フィ��ルドを出力
- 出力スキーマ���統一型 `ConversationHighlights` に合わせる
- `_build_narrative_report()` 内で既に呼ばれているため、追加 API call なし
- ただし `run_synthesis()` で Decision Brief にも注入する経路を追加

### 2.2 スキーマ統一

**決定**: Theater ナラテ��ブ用と Decision Brief 用で単一の `ConversationHighlights` 型を共有。

**理由**:
- 2���統並存は6ヶ月後に誰もメンテしなくなる技術負債
- DRY 原則

**影響範囲**:
- `conversation_highlights.py`: 出力スキーマを統一型に変更
- `narrative_generator.py`: 統一型からナラティブ用フィールドを取得するアダプタ
- `synthesis.py`: 統一型を Decision Brief に注入

### 2.3 UI: 独立セクション + linked_to

**決定**: Phase 1 は独立セクションとして配置。データモデルに `linked_to` フィールドを設けて
Phase 2 でのインライン表示に備える。

**理由**:
- Phase 1 は出荷を優先
- linked_to があれば Phase 2 で推奨事項の直下にインライン化できる

### 2.4 confidence フィールド削除

**決定**: `len(consensus) / (len(consensus) + len(conflicts))` による独自 confidence は廃止。
`agreement_score` を再利用する。

**理由**: 両レビュアーが「無意味な比率。正直な議論（対立点多）を罰する」と指摘。

### 2.5 Speaker Attribution の安全策

**決定**: `key_quotes` に `is_paraphrased: bool` フィールドを追加し、
UI で「AI要約」ラベルを付けて原文引用と誤解させない。

**理由**: 要約からの引用を原文と誤解させると、政治的文脈では信頼リスクになる。
「synthetic」は専門用語であり地方議員には意味不明。`is_paraphrased` に改名。
UI ラベルは「AI要約」とし、ツールチップで「AIが議論を要約した文です。原文ではありません。」と表示。

### 2.6 UI カテゴリの簡素化 (Design Review)

**決定**: ユーザーに見せるカテゴリは「合意されたこと」「まだ割れていること」の2グループを主表示。
「議論が動いた瞬間」「代表的な発言」は折りたたみ（disclosure toggle）で詳細表示。

**理由**: 4カテゴリは分析者のメンタルモデル。低リテラシーユーザーは
「turning point」と「conflict」を区別できない。2軸で十分。

### 2.7 セクション配置の変更 (Design Review)

**決定**: 議論ハイライトの配置を7番目から3番目に変更
（確信度の見立ての直後、主な判断根拠の直前）。

**理由**: ユーザーは「結論(hero) → どれだけ確信あるか → 何が議論されたか → なぜそう判断したか」
の順で読む。結論の根拠が7番目では深すぎて到達しない。

### 2.8 LLM 出力の Runtime Validation (Eng Review)

**決定**: LLM 出力に軽量バリデーションを追加。`consensus` または `conflicts` キーが
存在しない場合は旧フォーマットとみなし、空フォールバックを返却。

**理由**: プロンプト変更直後、LLM がキャッシュ済み旧フォーマットを返す可能性がある。

### 2.9 Adapter の配置先修正 (Eng Review)

**決定**: ナラティブ用アダプタは `narrative_generator.py` ではなく
`_build_narrative_report()` 内（`synthesis.py`）に配置。

**理由**: 旧スキーマフィールド (`turning_point.participant`, `turning_point.round`,
`strongest_exchange.summary`, `belief_journeys[].story`, `dramatic_tension`) の
実際の利用箇所は `synthesis.py:374-482`。narrative_generator は使っていない。

---

## 3. データ設計

### 3.1 統一型 ConversationHighlights

```python
# Backend: TypedDict or dataclass
class ConversationHighlightItem(TypedDict):
    point: str
    impact: str
    linked_to: str | None  # Phase 2: "key_reason_1", "guardrail_2" etc.

class ConflictItem(TypedDict):
    point: str
    status: str  # "unresolved" | "partially_resolved" | "resolved"
    impact: str
    linked_to: str | None

class TurningPointItem(TypedDict):
    moment: str
    why_it_changed: str
    linked_to: str | None

class KeyQuoteItem(TypedDict):
    speaker: str
    quote: str
    decision_impact: str
    is_paraphrased: bool  # True = LLM 要約, False = 原文引用
    linked_to: str | None

class ConversationHighlights(TypedDict):
    summary: str
    source_phase: str  # "council" | "meeting" | "discussion"
    consensus: list[ConversationHighlightItem]   # max 3
    conflicts: list[ConflictItem]                 # max 3
    turning_points: list[TurningPointItem]        # max 3
    key_quotes: list[KeyQuoteItem]                # max 3
```

### 3.2 Frontend TypeScript 型

```typescript
export interface ConversationHighlightItem {
  point: string
  impact: string
  linked_to?: string | null
}

export interface ConflictItem {
  point: string
  status: 'unresolved' | 'partially_resolved' | 'resolved'
  impact: string
  linked_to?: string | null
}

export interface TurningPointItem {
  moment: string
  why_it_changed: string
  linked_to?: string | null
}

export interface KeyQuoteItem {
  speaker: string
  quote: string
  decision_impact: string
  is_paraphrased: boolean
  linked_to?: string | null
}

export interface ConversationHighlights {
  summary: string
  source_phase: 'council' | 'meeting' | 'discussion'
  consensus: ConversationHighlightItem[]
  conflicts: ConflictItem[]
  turning_points: TurningPointItem[]
  key_quotes: KeyQuoteItem[]
}
```

`DecisionBrief` に `conversation_highlights?: ConversationHighlights` を追加。

### 3.3 旧スキーマとのマッピング

既存 `extract_conversation_highlights()` の出力:
```
turning_point    → turning_points[0] (moment=moment, why_it_changed=impact)
strongest_exchange → conflicts[0] (point=topic, status="unresolved", impact=summary)
key_quotes       → key_quotes (speaker, quote, is_synthetic=true)
belief_journeys  → turning_points の追加項目として変換
dramatic_tension → summary に統合
```

Theater ナラティブ側は統一型からフィールドを取得するアダプタを `narrative_generator.py` に追加。

---

## 4. Backend 実装要件

### 4.1 `conversation_highlights.py` の変更

**変更内容**: LLM プロンプトを拡張し、統一型 `ConversationHighlights` を出力。

**プロ��プト出力スキーマ**:
```json
{
  "summary": "議論の要約（100文字）",
  "consensus": [{"point": "合意点", "impact": "判断への影響"}],
  "conflicts": [{"point": "対立点", "status": "unresolved", "impact": "影響"}],
  "turning_points": [{"moment": "転換の瞬間", "why_it_changed": "理由"}],
  "key_quotes": [{"speaker": "名前", "quote": "発言（100文字）", "decision_impact": "判断への影響", "is_synthetic": true}]
}
```

**制約**:
- 各配列 max 3 件
- `quote` は 120 文��以内
- 全配列空なら `None` 返却
- `source_phase` はコード側で付与（LLM に任せない）
- `linked_to` は Phase 1 では常に `null`

**フォールバック**: LLM 呼���出し失敗���は空の統一型を返却（`summary: ""`, 各配列空）。
Phase 1 では rule-based フォ���ルバックは作らない（YAGNI）。

**既存互換**: `_build_narrative_report()` (`synthesis.py:374-482`) で使用している既存フィールド
(`turning_point.participant`, `turning_point.round`, `strongest_exchange.summary`,
`belief_journeys[].story`, `dramatic_tension`) は統一型から導出するアダプタ関数で再構築。

**注意 (Eng Review)**: アダプタは `narrative_generator.py` ではなく `synthesis.py` の
`_build_narrative_report()` 内に配置すること。旧フィールドの実利用箇所は synthesis.py。

**アダプタ変換ルール**:
```python
def _adapt_unified_to_narrative(highlights: dict) -> dict:
    """統一型 ConversationHighlights → ナラティブ用旧スキーマ"""
    tp = (highlights.get("turning_points") or [{}])[0]
    exchange = (highlights.get("conflicts") or [{}])[0]
    return {
        "turning_point": {
            "participant": tp.get("speaker", "参加者"),  # 新スキーマにない → "参加者" fallback
            "round": 0,  # 新スキーマにない → 0 fallback
            "moment": tp.get("moment", ""),
            "impact": tp.get("why_it_changed", ""),
        },
        "strongest_exchange": {
            "participants": [],
            "topic": exchange.get("point", ""),
            "summary": exchange.get("impact", ""),
        },
        "key_quotes": [
            {"speaker": q["speaker"], "quote": q["quote"], "round": 0}
            for q in (highlights.get("key_quotes") or [])
        ],
        "belief_journeys": [],  # 統一スキーマには対応フィールドなし → Phase 2 で対応
        "dramatic_tension": highlights.get("summary", ""),
    }
```

**Runtime Validation (Eng Review)**: LLM 出力のパース後、`consensus` または `conflicts`
キーの存在をチェック。不在なら旧フォーマットと判断し、空フォールバックを返却:
```python
if isinstance(result, dict):
    if "consensus" in result or "conflicts" in result:
        # 新スキーマ OK
        return result
    else:
        logger.warning("LLM returned old schema, falling back to empty")
        return None
```

**Zero-rounds ガード (Eng Review)**: `extract_conversation_highlights()` の先頭で
`if not rounds: return None` を追加。空ラウンドでの LLM 呼び出しを回避。

### 4.2 `synthesis.py` の変更

**変更内容**: `run_synthesis()` で `extract_conversation_highlights()` の結果を
Decision Brief にも注入する。

**注入ポイント**: `_build_narrative_report()` 内で既に呼ばれている
`extract_conversation_highlights()` の結果を、`run_synthesis()` から直接アクセスできるように
関数構造を変更。

**選択肢 A（推奨）**: `extract_conversation_highlights()` を `_build_narrative_report()` の外に出し、
`run_synthesis()` から直接呼び出す。結果を narrative report と decision_brief の両方に���す。

```python
# run_synthesis() 内
highlights = await extract_conversation_highlights(
    council.rounds, council.synthesis, theme,
)

# Decision Brief に注入
if highlights and any([
    highlights.get("consensus"),
    highlights.get("conflicts"),
    highlights.get("turning_points"),
    highlights.get("key_quotes"),
]):
    decision_brief["conversation_highlights"] = highlights

# ナラティブレポートにも渡す
content = await _build_narrative_report(
    theme, pulse=pulse, council=council,
    decision_brief=decision_brief, agreement_score=agreement_score,
    highlights=highlights,  # 既に抽出済みを渡す
)
```

**重複呼び出し防止**: `_build_narrative_report()` 内の `extract_conversation_highlights()` 呼び��しを
削除し、引数で受け取る形に変更。

### 4.3 `decision_briefing.py` の変更

**build_pm_board_decision_brief()**: 変更なし。PM Board 単独の場合は `conversation_highlights`
なし（council データがないため）。

**enrich_decision_brief()**: `council_synthesis` パラメータは追加しない（方針変更）。
highlights は `run_synthesis()` で直接注入されるため、enrich 経路での注入は不要。
既存の `enrich_decision_brief()` 呼び出し元（`report_generator.py`, `final_report_generator.py`,
`api/routes/simulations.py`）に影響な��。

**render_decision_brief_markdown()**: `議論ハイライト` セクションを追加。
配置は `判断の基準` と `深掘りに使う follow-up` の間。

```markdown
### 議論ハイライト

{summary}

**合意されたこと:**
- {point} ({impact})

**まだ割れていること:**
- {point} [{status}] ({impact})

**議論が動いた瞬間:**
- {moment} — {why_it_changed}

**代表的な発言:**
> 「{quote}」 — {speaker} ({decision_impact}) [要約]
```

### 4.4 エラーパス

| codepath | what can go wrong | handling |
|----------|-------------------|----------|
| `extract_conversation_highlights()` LLM call | API timeout / rate limit | catch → return empty highlights → section hidden |
| `extract_conversation_highlights()` LLM call | malformed JSON response | catch → log warning → return empty |
| `extract_conversation_highlights()` LLM call | model refusal | catch → log → return empty |
| `run_synthesis()` highlights injection | highlights is None | skip injection → decision_brief has no highlights → section hidden |
| `render_decision_brief_markdown()` | highlights has empty arrays | skip that sub-section, render non-empty ones only |
| Frontend rendering | `conversation_highlights` missing from API | `v-if` guard → section hidden |
| Frontend rendering | partial data (e.g. consensus only, no conflicts) | each sub-section independently guarded |

### 4.5 非互換リスクチェックリス���

| 呼び出し元 | 影響 | 対応 |
|-----------|------|------|
| `report_generator.py` (single report) | `enrich_decision_brief()` に変更なし | 影響なし |
| `final_report_generator.py` (pipeline) | `enrich_decision_brief()` に変更なし | 影響なし |
| `api/routes/simulations.py` | レスポンスに `conversation_highlights` が追加される | 後方互換（optional フィールド追加） |
| `narrative_generator.py` | 統一型からナラティブ用フィールドを導出 | アダプタ関数追加 |
| `ComparisonBrief.vue` | `DecisionBrief` コンポーネントを再利用 | highlights セクションが自然に表示される |

---

## 5. Frontend 実装要件

### 5.1 型定義 (`client.ts`)

上記 3.2 の TypeScript ��を追加。`DecisionBrief` に `conversation_highlights?` を追加。

### 5.2 セクション順序 (`DecisionBrief.vue`)

```
1. Hero (recommendation + summary)
2. 確信度の見立て
3. 議論ハイライト          ← NEW (Design Review: 位置を7→3に変更)
4. 主な判断根拠
5. この判断が成り立つ条件
6. 判断を覆すトリガー
7. 判断の基準
8. 追加で潰すべき論点
9. 推奨アクション
10. 深掘りに使う follow-up
11. その他 (options, risks, etc.)
```

読み筋: 結論 → 確信度 → 何が議論されたか → なぜそう判断したか → 条件・リスク → 次にやること

### 5.3 議論ハイライト UI

**表示制御**: `v-if="brief.conversation_highlights"` でセクション全体をガード。

**サブセクション構成** (Design Review 反映: 2グループ主表示 + 折りたたみ):

**主表示 (常に表示):**
1. **要約** (`summary`): `.section-prose` で 1段落表示
2. **合意されたこと** (`consensus`): 緑ボーダー `.detail-card`。各 max 2件 + 「もっと見る」
3. **まだ割れていること** (`conflicts`): 黄ボーダー `.detail-card`。`status` バッジ表示

**詳細 (折りたたみ、デフォルト閉じ):**
4. **議論が動いた瞬間** (`turning_points`): disclosure toggle 内
5. **代表的な発言** (`key_quotes`): blockquote。`is_paraphrased=true` → 「AI要約」ラベル + ツールチップ

**CSS**: 既存クラス再利用。追加:
- `.detail-card-consensus`: `border-color: rgba(34,197,94,0.25); background: rgba(34,197,94,0.04);`
- `.detail-card-conflict`: `border-color: rgba(245,158,11,0.25); background: rgba(245,158,11,0.04);`
- `.quote-card`: blockquote スタイル
- `.quote-paraphrased-label`: 「AI要約」ラベル
- `.highlights-detail-toggle`: 折りたたみトグル (44px min touch target)
- `.highlights-skeleton`: ローディングスケルトン

**Loading 状態**: SSE 中はスケルトンローダー表示。データ到着で実コンテンツに切替。
**空データ処理**: 各サブセクション独立 `v-if="arr.length"` ガード。全空→非表示。
**カード制約**: 各サブセクション max 2件初期表示 + 展開。
**レスポンシブ**: 720px 以下で縦スタック。全タッチターゲット 44px 以上。

### 5.4 ComparisonBrief.vue 互換

`ComparisonBrief.vue` は `DecisionBrief` コンポーネントを再利用しているため、追加 props なしで
議論ハイライトが表示され���。DOM 量増加による既存レイアウト崩れがないことをテストで確認。

---

## 6. テスト要件

### 6.1 Backend テスト

| テスト | ファイル | 内容 |
|-------|---------|------|
| `test_extract_highlights_unified_schema` | `test_decision_briefing.py` | 統一型の全フィールドが返却される |
| `test_extract_highlights_empty_rounds` | `test_decision_briefing.py` | 空ラウンド → None 返却 |
| `test_extract_highlights_max_3_per_array` | `test_decision_briefing.py` | 各配列 max 3 件制約 |
| `test_extract_highlights_llm_failure_returns_empty` | `test_decision_briefing.py` | LLM 失敗 → 空 highlights |
| `test_highlights_adapter_for_narrative` | `test_decision_briefing.py` | 統一型 → ナラティブ用変換 |
| `test_run_synthesis_includes_highlights` | `test_unified_phases.py` | decision_brief に highlights が含まれる |
| `test_run_synthesis_no_duplicate_llm_call` | `test_unified_phases.py` | extract が 1 回だけ呼ばれる |
| `test_render_markdown_includes_highlights` | `test_decision_briefing.py` | Markdown に議論ハイライトセクションが含まれる |
| `test_render_markdown_skips_empty_highlights` | `test_decision_briefing.py` | 空 → セクション非表示 |
| `test_enrich_decision_brief_unchanged` | `test_decision_briefing.py` | enrich 経路で highlights が消えない（pass-through） |
| `test_extract_highlights_returns_none_for_empty_rounds` | `test_decision_briefing.py` | 空 rounds → None (LLM 呼び出しスキップ) |
| `test_extract_highlights_validates_new_schema_keys` | `test_decision_briefing.py` | LLM が旧スキーマ返却 → 空フォールバック |
| `test_narrative_report_renders_from_unified_schema` | `test_unified_phases.py` | アダプタ経由で participant, turning point テキストが含まれる |
| `test_adapt_unified_to_narrative_reconstructs_old_fields` | `test_decision_briefing.py` | 各旧フィールドが非空で再構築される |

### 6.2 Frontend テスト

| テスト | ファイル | 内容 |
|-------|---------|------|
| `displays highlights section when data present` | `DecisionBrief.spec.ts` | highlights セクションが表示される |
| `hides highlights section when data missing` | `DecisionBrief.spec.ts` | highlights なし → 非表示 |
| `renders consensus with green border` | `DecisionBrief.spec.ts` | 合意点が緑ボーダーで表示 |
| `renders conflicts with yellow border and status badge` | `DecisionBrief.spec.ts` | 対立点が黄ボーダー + status 表示 |
| `renders key quotes with synthetic label` | `DecisionBrief.spec.ts` | is_synthetic=true で「要約」ラベル |
| `renders partial data (consensus only)` | `DecisionBrief.spec.ts` | consensus のみでも正常表示 |
| `section order matches requirements` | `DecisionBrief.spec.ts` | セクション順序が要件通り |
| `ComparisonBrief renders highlights without layout break` | `ComparisonBrief.spec.ts` | 比較画面でもレイアウト崩れなし |
| `renders paraphrased label with tooltip on synthetic quotes` | `DecisionBrief.spec.ts` | is_paraphrased=true で「AI要約」ラベル + ツールチップ |
| `detail toggle collapses turning_points and key_quotes` | `DecisionBrief.spec.ts` | 折りたたみがデフォルト閉じ、クリックで開く |
| `shows skeleton loader during SSE streaming` | `DecisionBrief.spec.ts` | highlights 未到着時にスケルトン表示 |
| `section appears at position 3 (after confidence)` | `DecisionBrief.spec.ts` | セクション順序が要件通り |

---

## 7. 縮退動作

| ケース | 動作 |
|--------|------|
| Council データあり | LLM 抽出 → 統一型 → Decision Brief に注入 |
| Council データなし (PM Board 単独) | highlights なし → セクション非表示 |
| Single レポート | highlights なし → セクション非表示 |
| LLM 呼び出し失敗 | 空 highlights → セクション非表示 |
| LLM が不完全な JSON を返却 | catch → log → 空 highlights |
| consensus のみで conflicts なし | consensus だけ表示 |
| 全配列空 | None 返却 → セクション非表示 |

---

## 8. 受け入れ基準

1. Results 画面で、council データを含むシミュレーショ���完了後に「議論ハイライト」セクションが表示される
2. 少なくとも `合意されたこと` または `まだ割れていること` が 1 件以上表示される
3. `key_quotes` の `is_synthetic=true` の引用に「要約」ラベルが付いている
4. ハイライトを読めば Transcript 全文を見なくても判断の流れを理解���きる
5. 既存の Decision Brief 表示を壊さない（全テスト通過）
6. `conversation_highlights` がない場合（Single/PM Board 単独）はセクションが非���示
7. ComparisonBrief 画面でも��イアウトが崩れない
8. Markdown レンダリング（レポート出力）にも議論ハイライトが含まれる

---

## 9. 変更対象ファイル（更新版）

| # | ファイル | 変更内容 |
|---|---------|---------|
| 1 | `backend/src/app/services/society/conversation_highlights.py` | プロンプト拡張 → 統一型 `ConversationHighlights` 出力 |
| 2 | `backend/src/app/services/phases/synthesis.py` | `extract` を `run_synthesis()` レベルに引き上��、Decision Brief + narrative 両方に渡す |
| 3 | `backend/src/app/services/decision_briefing.py` | `render_decision_brief_markdown()` にハイライトセクション追加 |
| 4 | `backend/src/app/services/phases/synthesis.py` (内 `_build_narrative_report`) | 統一型→ナラティブ用変換アダプタ (Eng Review: 配置先修正) |
| 5 | `frontend/src/api/client.ts` | `ConversationHighlights` 型 + `DecisionBrief` に optional 追加 |
| 6 | `frontend/src/components/DecisionBrief.vue` | セクション順序変更 + 議論ハイライト UI 追加 |
| 7 | `backend/tests/test_decision_briefing.py` | highlights 関連テスト追加 |
| 8 | `backend/tests/test_unified_phases.py` | run_synthesis の統合テスト追加 |
| 9 | `frontend/src/components/__tests__/DecisionBrief.spec.ts` | highlights 表示テスト追加 |

---

## 10. 段階導入計画

### Phase 1 (本要件)
- 既存 LLM 関数の統一スキーマ適応
- Decision Brief への注入
- 独立セクション UI
- `linked_to` フィールドを null で設置

### Phase 2 (将来)
- `linked_to` を使ったインライン表示（推奨事項の直下に紐付け）
- LLM プロンプトの品質改善
- followup_prompts との連動（「どの対立点を次に聞くべきか」自動提案）

### Phase 3 (将来)
- Theater ナラティブとの完全統合
- ユーザーフィードバックに基づく UI 最適化

---

## 11. リスクと回避策

| リスク | 影響 | 回避策 |
|--------|------|--------|
| LLM 出力の品質が低い | ユーザーの信頼を損なう | summary の deterministic フォールバック + 「要約」ラベ�� |
| highlights が常に空 | 機能が実質的に無効 | テストで council ありケースの非空を保証 |
| 統一スキー���変更で narrative が壊れる | 既存レポート品質低下 | アダプタ関数でナラティブ用フィールドを保全 |
| Speaker attribution の政治的リスク | 引用の誤解、信頼失墜 | `is_synthetic` ラベルで要約であることを明示 |
| API レスポンスサイズ増加 | レスポンス遅延 | max 3 件制約、quote 120 文字制限 |

---

## Appendix A: 旧プラン (v1) からの差分

| 項目 | v1 (旧プラン) | v2 (本要件) |
|------|--------------|------------|
| 抽出方式 | rule-based `build_conversation_highlights()` 新規作成 | 既存 LLM `extract_conversation_highlights()` 適応 |
| スキーマ | Decision Brief 専用型、Theater 系と別 | 統一型 `ConversationHighlights` |
| confidence | `len(consensus)/(len(consensus)+len(conflicts))` | 削除（`agreement_score` で代替） |
| enrich_decision_brief | `council_synthesis` パラメータ追加 | 変更なし（synthesis.py で直接注入） |
| decision_briefing.py | `build_conversation_highlights()` 追加 | 変更は `render_decision_brief_markdown()` のみ |
| narrative_generator.py | 変更���し | アダプタ関数追加（統一型対応） |
| key_quotes | is_synthetic なし | `is_synthetic: bool` 追加 |
| linked_to | なし | 全項目に `linked_to: null` (Phase 2 準備) |
