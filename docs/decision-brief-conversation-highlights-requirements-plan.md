# Plan

Decision Brief を「結論だけを返すサマリー」から「どの会話が結論に効いたかまで読める意思決定ビュー」に拡張する。全文 transcript の露出ではなく、判断に効いた会話を `議論ハイライト` として抽出・要約し、Recommendation、判断基準、追加で潰す論点と同じ文脈で読めるようにする。

## Scope
- In:
  - Decision Brief に `議論ハイライト` セクションを追加するための要件整理
  - Backend で会話要約データを生成・返却するためのデータ設計
  - Frontend で読みやすく表示する UI/UX 要件
  - テスト、段階導入、受け入れ条件の定義
- Out:
  - 会話全文の常時表示
  - Transcript 機能そのものの全面置換
  - LLM プロンプト最適化の詳細実装
  - すべての既存レポート形式の一括刷新

## Action items
[ ] 目的を固定する: `議論ハイライト` の目的を「結論の透明性を上げる」「どの発言が判断に効いたかを示す」「次の follow-up の起点を作る」の3点に限定する。
[ ] 表示対象を定義する: 会話全文ではなく、`consensus_points`、`conflict_points`、`turning_points`、`key_quotes` の4区分だけを Decision Brief に載せる仕様を定める。
[ ] Backend データ契約を定義する: `decision_brief.conversation_highlights` を追加し、`summary`、`consensus`、`conflicts`、`turning_points`、`key_quotes`、`source_phase`、`confidence` を持つ JSON 形に統一する。
[ ] 抽出ルールを定義する: Council、meeting、society discussion から「結論に効いた発話」だけを抽出し、1項目あたり 1〜2 文、最大件数を設け、重複・冗長な発言は除外するルールを定める。
[ ] 要約ルールを定義する: `key_quotes` は全文引用ではなく短い代表発言、`consensus` は合意済み論点、`conflicts` は未解決または条件付きの対立点、`turning_points` は議論の流れが変わった瞬間として要約する。
[ ] UI 要件を定義する: Results の Decision Brief 内に `議論ハイライト` セクションを設け、上から `要約` → `合意点` → `対立点` → `転換点` → `代表発言` の順で表示する。
[ ] 読み筋を定義する: Recommendation の直下または `判断の基準` の直後に `議論ハイライト` を置き、ユーザーが「結論 → なぜそうなったか → 何が未解決か」の順で読める構成にする。
[ ] 非機能要件を定義する: ハイライトは短く保ち、初期表示で 3〜5 件まで、全文 transcript へのリンクは任意、レスポンスサイズ増加を許容範囲内に抑える。
[ ] テスト要件を定義する: Backend は conversation highlights の生成・整形ユニットテスト、API レスポンス互換テスト、Frontend はセクション表示・空状態・長文切り詰めのコンポーネントテストを追加する。
[ ] 段階導入計画を定義する: Phase 1 は固定ルールベースで抽出、Phase 2 で LLM による要約品質改善、Phase 3 で follow-up prompt と連動させる段階導入にする。
[ ] 受け入れ条件を定義する: 少なくとも 1 つの `合意点` または `対立点` が表示され、Recommendation と矛盾せず、ユーザーが「どの会話が判断を動かしたか」を 30 秒以内に把握できる状態を成功条件にする。
[ ] リスクと回避策を定義する: 情報過多、冗長な引用、誤要約、Transcript との二重管理を主なリスクとして明示し、件数制限・要約テンプレート・原文導線で抑える。

## Open questions
- `議論ハイライト` の一次ソースは Council のみで始めるか、それとも society meeting まで初期対象に含めるか。
- `key_quotes` は引用符付きの短文として出すか、引用ではなく間接話法の要約だけにするか。
- 初回リリースで Transcript への deep link まで付けるか、それともハイライト単体表示に留めるか。

## Requirements Notes

### 1. 背景

現状の Decision Brief は Recommendation、判断根拠、未知論点、推奨アクションは見えるが、「どういう議論を経てその結論になったか」が薄い。結果として、ユーザーは次のような疑問を持ちやすい。

- なぜこの Recommendation になったのか
- 誰のどの主張が効いたのか
- どこがまだ割れているのか
- 次に深掘りすべき論点はどこか

このギャップを埋めるため、Transcript 全文ではなく、意思決定に効いた会話を構造化して Decision Brief に取り込む。

### 2. 機能要件

追加するデータ構造の例:

```json
{
  "conversation_highlights": {
    "summary": "価格受容性は需要自体よりも強いボトルネックとして扱われ、結論は条件付きGoに寄った。",
    "source_phase": "council",
    "confidence": 0.74,
    "consensus": [
      {
        "point": "需要は存在するが、現価格では初期導入が鈍る",
        "impact": "条件付きGoの中心根拠"
      }
    ],
    "conflicts": [
      {
        "point": "初期価格を維持するか下げるかで意見が割れた",
        "status": "unresolved",
        "impact": "最終Go判断を保留させる論点"
      }
    ],
    "turning_points": [
      {
        "moment": "市場性の議論から価格設計の議論へ焦点が移った",
        "why_it_changed": "採用障壁が価格に集中していると整理されたため"
      }
    ],
    "key_quotes": [
      {
        "speaker": "consumer_representative",
        "quote": "需要はあるが、今の価格では広がらない",
        "decision_impact": "価格検証を最優先に繰り上げた"
      }
    ]
  }
}
```

制約:

- 各配列は最大 3 件
- `quote` は短文のみ
- 原文をそのまま長く貼らない
- `decision_impact` を必須にして「なぜ重要か」を明示する

### 3. UX 要件

表示順:

1. Recommendation
2. 判断の基準
3. 議論ハイライト
4. 追加で潰すべき論点
5. 推奨アクション
6. 深掘りに使う follow-up

表示ルール:

- `summary` は 1 段落
- `consensus` と `conflicts` はカード表示
- `turning_points` は「どこで議論が動いたか」が一目で分かる書式にする
- `key_quotes` は引用文だけでなく `decision_impact` を必ず併記する
- データが空ならセクション自体を出さない

### 4. 実装方針

Phase 1:

- 既存の `council` / `meeting` / `decision_brief` データからルールベースで生成
- まずは既存情報の再構成で成立させる

Phase 2:

- 必要なら LLM ベースの要約生成を追加
- ただし、入力は会話全文ではなく抽出済み候補に限定する

Phase 3:

- `followup_prompts` と接続し、「どの対立点を次に聞くべきか」を自動提案する

### 5. 受け入れ基準

- Results 画面で Recommendation の理由が会話ベースで追える
- 少なくとも `consensus` または `conflicts` が 1 件以上表示される
- `decision_impact` が各ハイライトに含まれる
- ハイライトを読めば Transcript 全文を見なくても判断の流れを理解できる
- 既存の Decision Brief 表示を壊さない

