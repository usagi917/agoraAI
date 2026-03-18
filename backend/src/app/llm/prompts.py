"""プロンプトテンプレート"""

WORLD_BUILD_SYSTEM = """あなたは世界モデル構築の専門家です。
入力された文書を分析し、構造化された世界モデルを JSON で出力してください。
必ず以下の形式で出力してください。"""

WORLD_BUILD_USER = """以下の文書から世界モデルを構築してください。

## テンプレート指示
{template_prompt}

## ユーザーの分析指示
{user_prompt}

## 入力文書
{document_text}

## 出力形式（JSON）
{{
  "entities": [
    {{
      "id": "entity_1",
      "label": "エンティティ名",
      "entity_type": "organization|person|policy|market|technology|resource",
      "description": "説明",
      "importance_score": 0.0-1.0,
      "stance": "立場や姿勢",
      "activity_score": 0.0-1.0,
      "sentiment_score": -1.0-1.0,
      "status": "active",
      "group": "グループ名"
    }}
  ],
  "relations": [
    {{
      "id": "rel_1",
      "source": "entity_1",
      "target": "entity_2",
      "relation_type": "competition|cooperation|regulation|supply|influence|dependency",
      "weight": 0.0-1.0,
      "direction": "directed|bidirectional"
    }}
  ],
  "timeline": [
    {{
      "event": "イベント名",
      "description": "説明",
      "involved_entities": ["entity_1"]
    }}
  ],
  "world_summary": "世界の概要説明"
}}

重要: 必ず有効な JSON のみを出力してください。"""

AGENT_GENERATE_SYSTEM = """あなたはマルチエージェントシステムの設計者です。
世界モデルに基づいてエージェントプロファイルを生成してください。"""

AGENT_GENERATE_USER = """以下の世界モデルからエージェントを生成してください。

## テンプレート指示
{template_prompt}

## ユーザーの分析指示
{user_prompt}

## 世界モデル
{world_state}

## 出力形式（JSON）
{{
  "agents": [
    {{
      "id": "agent_1",
      "entity_id": "対応するエンティティID",
      "name": "エージェント名",
      "role": "役割",
      "goals": ["目標1", "目標2"],
      "strategy": "戦略説明",
      "decision_pattern": "意思決定パターン",
      "relationships": [
        {{
          "target_agent": "agent_2",
          "type": "ally|rival|neutral",
          "strength": 0.0-1.0
        }}
      ]
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

ROUND_PROCESS_SYSTEM = """あなたはシミュレーションエンジンです。
現在の世界状態とエージェント情報に基づいて、1ラウンド分のシミュレーションを実行してください。"""

ROUND_PROCESS_USER = """ラウンド {round_number} のシミュレーションを実行してください。

## テンプレート指示
{template_prompt}

## ユーザーの分析指示
{user_prompt}

## 現在の世界状態
{world_state}

## エージェント情報
{agents}

## 出力形式（JSON）
{{
  "agent_decisions": [
    {{
      "agent_id": "agent_1",
      "action": "実行したアクション",
      "reasoning": "理由",
      "impact": "影響"
    }}
  ],
  "entity_updates": [
    {{
      "entity_id": "entity_1",
      "changes": {{
        "importance_score": 0.8,
        "activity_score": 0.7,
        "sentiment_score": 0.3,
        "status": "active",
        "stance": "新しい立場"
      }}
    }}
  ],
  "relation_updates": [
    {{
      "source": "entity_1",
      "target": "entity_2",
      "changes": {{
        "weight": 0.6,
        "relation_type": "cooperation"
      }}
    }}
  ],
  "events": [
    {{
      "title": "イベントタイトル",
      "description": "イベントの詳細説明",
      "event_type": "decision|conflict|cooperation|market_change|policy_change|emergence",
      "severity": 0.0-1.0,
      "involved_entities": ["entity_1", "entity_2"]
    }}
  ],
  "round_summary": "このラウンドの要約"
}}

重要: 必ず有効な JSON のみを出力してください。"""

REPORT_SECTION_SYSTEM = """あなたは分析レポートの専門家です。
シミュレーション結果に基づいて、レポートの指定セクションを日本語で作成してください。
markdown 形式で出力してください。"""

REPORT_SECTION_USER = """以下のシミュレーション結果に基づいて、「{section_name}」セクションを作成してください。

## セクション名
{section_display_name}

## 世界状態（最終）
{world_state_final}

## イベント履歴
{events}

## エージェント情報
{agents}

markdown 形式で、そのセクションの内容のみを出力してください。"""

FOLLOWUP_SYSTEM = """あなたはシミュレーション結果の分析アシスタントです。
レポートと世界状態に基づいて、ユーザーの質問に日本語で回答してください。"""

FOLLOWUP_USER = """以下のレポートと世界状態に基づいて質問に回答してください。

## レポート
{report}

## 世界状態
{world_state}

## 質問
{question}

回答:"""

# === SwarmMind: 主張抽出プロンプト ===

CLAIM_EXTRACT_SYSTEM = """あなたはシミュレーション結果から構造化された予測主張を抽出する専門家です。
各シミュレーション結果から、明確な予測主張（将来の出来事や状態に関する主張）を抽出してください。"""

CLAIM_EXTRACT_USER = """以下のシミュレーション結果から予測主張を抽出してください。

## 世界状態（最終）
{world_state}

## イベント履歴
{events}

## エージェント情報
{agents}

## 出力形式（JSON）
{{
  "claims": [
    {{
      "claim_text": "具体的な予測主張",
      "claim_type": "market_outcome|technology_shift|regulatory_change|competitive_dynamics|risk_event",
      "confidence": 0.0-1.0,
      "evidence": "この主張を支持する根拠",
      "entities_involved": ["entity_1", "entity_2"],
      "timeframe": "short_term|medium_term|long_term"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。各主張は具体的で検証可能な内容にしてください。"""

# === GraphRAG: エンティティ抽出 ===

ENTITY_EXTRACT_SYSTEM = """あなたはナレッジグラフ構築の専門家です。
テキストチャンクからエンティティ（人物、組織、概念、技術、場所、イベント等）を抽出してください。"""

ENTITY_EXTRACT_USER = """以下のテキストチャンク（チャンク {chunk_index}）からエンティティを抽出してください。

## テキスト
{chunk_text}

## 出力形式（JSON）
{{
  "entities": [
    {{
      "name": "エンティティ名（正式名称）",
      "type": "person|organization|concept|technology|location|event|policy|market|resource",
      "description": "エンティティの簡潔な説明",
      "aliases": ["別名1", "略称"]
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === GraphRAG: 関係抽出 ===

RELATION_EXTRACT_SYSTEM = """あなたはナレッジグラフの関係抽出の専門家です。
指定されたエンティティ間の関係をテキストから抽出してください。"""

RELATION_EXTRACT_USER = """以下のテキストに含まれるエンティティ間の関係を抽出してください。

## エンティティ
{entities}

## テキスト
{chunk_text}

## 出力形式（JSON）
{{
  "relations": [
    {{
      "source": "ソースエンティティ名",
      "target": "ターゲットエンティティ名",
      "type": "competition|cooperation|regulation|supply|influence|dependency|ownership|alliance|conflict",
      "evidence": "この関係を示すテキスト中の根拠",
      "confidence": 0.0-1.0
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === GraphRAG: エンティティ重複解決 ===

ENTITY_DEDUP_SYSTEM = """あなたはエンティティ解決の専門家です。
2つのエンティティが同一の実体を指すかどうかを判定してください。"""

ENTITY_DEDUP_USER = """以下の2つのエンティティが同一かどうか判定してください。

## エンティティA
名前: {entity_a_name}
説明: {entity_a_description}

## エンティティB
名前: {entity_b_name}
説明: {entity_b_description}

## 出力形式（JSON）
{{
  "is_same": true/false,
  "merged_name": "統合後の正式名称",
  "merged_description": "統合後の説明"
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === GraphRAG: コミュニティサマリー ===

COMMUNITY_SUMMARY_SYSTEM = """あなたはナレッジグラフのコミュニティ分析の専門家です。
エンティティグループの関係性を要約してください。"""

COMMUNITY_SUMMARY_USER = """以下のコミュニティ {community_index} のメンバーと関係性を要約してください。

## メンバー
{members}

## 関係
{relations}

このコミュニティの特徴、テーマ、メンバー間の主要な関係性を2-3文で簡潔に要約してください。

## 出力形式（JSON）
{{
  "summary": "コミュニティの要約文"
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === 記憶システム: 重要度判定 ===

MEMORY_IMPORTANCE_SYSTEM = """あなたはエージェントの記憶重要度を判定する専門家です。
経験の重要度を0（日常的・些細）から1（人生を変える・極めて重要）のスケールで判定してください。"""

MEMORY_IMPORTANCE_USER = """以下の経験の重要度を判定してください。

## エージェント
名前: {agent_name}
役割: {agent_role}

## 経験
{experience}

## 出力形式（JSON）
{{
  "importance": 0.0-1.0,
  "reasoning": "この重要度を付けた理由"
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === 記憶システム: Reflection ===

REFLECTION_SYSTEM = """あなたはエージェントの経験を高次の洞察に統合する専門家です。
最近の経験群から、パターン、教訓、重要な気づきを抽出してください。"""

REFLECTION_USER = """以下の経験群から高次の洞察を生成してください。

## エージェント
名前: {agent_name}
役割: {agent_role}

## 最近の経験
{experiences}

## 出力形式（JSON）
{{
  "reflections": [
    {{
      "insight": "洞察の内容",
      "importance": 0.0-1.0,
      "source_ids": ["元となった経験のID"]
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === BDI認知アーキテクチャ: 知覚 ===

BDI_PERCEIVE_SYSTEM = """あなたはエージェントの知覚システムです。
環境状態と関連する記憶から、エージェントにとって重要な観察を抽出してください。"""

BDI_PERCEIVE_USER = """エージェント「{agent_name}」の視点から環境を知覚してください。

## エージェント情報
名前: {agent_name}
役割: {agent_role}
目標: {agent_goals}

## 現在の環境状態
{environment}

## 関連する記憶
{relevant_memories}

## 最近のイベント
{recent_events}

## 出力形式（JSON）
{{
  "observations": [
    {{
      "content": "観察内容",
      "relevance": 0.0-1.0,
      "source": "environment|memory|event"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === BDI認知アーキテクチャ: 熟慮 ===

BDI_DELIBERATE_SYSTEM = """あなたはBDI（Belief-Desire-Intention）推論エンジンです。
エージェントの信念、欲求、現在の意図、観察に基づいて、次の行動計画を推論してください。"""

BDI_DELIBERATE_USER = """エージェント「{agent_name}」の行動を推論してください。

## 信念（Beliefs）
{beliefs}

## 欲求（Desires）
{desires}

## 現在の意図（Intentions）
{intentions}

## 新しい観察
{observations}

## 受信メッセージ
{incoming_messages}

## 他エージェントのメンタルモデル
{mental_models}

## 出力形式（JSON）
{{
  "reasoning_chain": "推論の過程を段階的に説明",
  "chosen_action": "選択した行動の説明",
  "expected_outcomes": ["予想される結果1", "予想される結果2"],
  "commitment_strength": 0.0-1.0,
  "belief_updates": [
    {{
      "proposition": "更新する信念",
      "confidence": 0.0-1.0,
      "source": "observation|inference"
    }}
  ],
  "communication_intents": [
    {{
      "type": "say|propose|inform|request",
      "target_ids": ["対象エージェントID"],
      "content": "メッセージ内容",
      "urgency": "low|normal|high"
    }}
  ],
  "evidence_likelihoods": [
    {{
      "evidence": "観察された証拠",
      "likelihood_ratio": 0.1-10.0
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === BDI認知アーキテクチャ: 行動実行 ===

BDI_EXECUTE_SYSTEM = """あなたはエージェントの行動を自然言語で記述するシステムです。
選択された行動を具体的でリアリスティックな描写に変換してください。"""

BDI_EXECUTE_USER = """エージェント「{agent_name}」の行動を記述してください。

## エージェント情報
名前: {agent_name}
役割: {agent_role}

## 選択された行動
{chosen_action}

## コンテキスト
{context}

## 出力形式（JSON）
{{
  "action_description": "行動の詳細な自然言語記述",
  "impact": "この行動が世界に与える影響",
  "entity_updates": [
    {{
      "entity_id": "影響を受けるエンティティ",
      "changes": {{"importance_score": 0.0-1.0, "sentiment_score": -1.0-1.0}}
    }}
  ],
  "relation_updates": [
    {{
      "source": "エンティティ1",
      "target": "エンティティ2",
      "changes": {{"weight": 0.0-1.0, "relation_type": "新しい関係種別"}}
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === Game Master: 行動衝突解決 ===

GM_ACTION_RESOLVE_SYSTEM = """あなたはシミュレーションのGame Masterです。
複数エージェントの同時行動の衝突を検出し、現実的に解決してください。"""

GM_ACTION_RESOLVE_USER = """以下のエージェント行動の衝突を検出・解決してください。

## エージェント行動一覧
{agent_actions}

## 現在の世界状態
{world_state}

## 出力形式（JSON）
{{
  "resolved_actions": [
    {{
      "agent_id": "エージェントID",
      "original_action": "元の行動",
      "outcome": "解決後の実際の結果",
      "success": true/false,
      "side_effects": ["副作用1"]
    }}
  ],
  "conflicts_detected": [
    {{
      "agents": ["agent_1", "agent_2"],
      "resource": "競合リソース",
      "resolution": "解決方法の説明"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === Game Master: 一貫性検証 ===

GM_CONSISTENCY_CHECK_SYSTEM = """あなたは世界状態の論理的整合性を検証するシステムです。
矛盾や不整合を検出し、修正案を提案してください。"""

GM_CONSISTENCY_CHECK_USER = """以下の世界状態の整合性を検証してください。

## 世界状態
{world_state}

## 最近の変更
{recent_changes}

## 出力形式（JSON）
{{
  "is_consistent": true/false,
  "inconsistencies": [
    {{
      "type": "contradiction|impossible_state|temporal_violation",
      "description": "不整合の説明",
      "affected_entities": ["entity_1"]
    }}
  ],
  "corrections": [
    {{
      "entity_id": "修正対象",
      "field": "修正フィールド",
      "current_value": "現在値",
      "corrected_value": "修正値",
      "reason": "修正理由"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""


# === エージェント間通信: 会話応答 ===

CONVERSATION_RESPOND_SYSTEM = """あなたはエージェントの会話応答システムです。
エージェントの役割・目標・性格に基づいて、受信メッセージに対する自然な応答を生成してください。
応答はエージェントの立場を反映し、戦略的であるべきです。"""

CONVERSATION_RESPOND_USER = """エージェント「{agent_name}」（{agent_role}）として以下のメッセージに応答してください。

## エージェント情報
目標: {agent_goals}
現在の信念: {beliefs}

## 受信メッセージ
送信者: {sender_name}
種別: {message_type}
内容: {message_content}

## 会話コンテキスト
{conversation_context}

## 出力形式（JSON）
{{
  "response_content": "応答内容",
  "message_type": "say|propose|accept|reject|inform|request",
  "intent": "応答の意図",
  "topics": ["関連トピック"],
  "urgency": "low|normal|high"
}}

重要: 必ず有効な JSON のみを出力してください。"""

# === バッチ応答生成 ===

BATCH_RESPONSE_SYSTEM = """あなたは複数エージェントの応答を同時に生成するシステムです。
各エージェントの役割と性格に基づいて、それぞれ異なる自然な応答を生成してください。
必ず JSON 形式で出力してください。"""

BATCH_RESPONSE_USER = """以下のメッセージに対する各エージェントの応答を生成してください。

## 受信メッセージ
送信者: {sender_name}
種別: {message_type}
内容: {message_content}

## 会話コンテキスト
{conversation_context}

## 応答すべきエージェント
{agents_description}

## 出力形式（JSON）
{{
  "responses": [
    {{
      "agent_id": "エージェントID",
      "content": "応答内容",
      "message_type": "say|propose|accept|reject|inform|request",
      "intent": "応答の意図"
    }}
  ]
}}

重要: 必ず有効な JSON のみを出力してください。"""

REPORT_SECTIONS = {
    "executive_summary": "エグゼクティブサマリー",
    "input_assumptions": "入力と前提条件",
    "entities_overview": "エンティティ概要",
    "simulation_summary": "シミュレーション要約",
    "scenario_comparison": "シナリオ比較",
    "event_timeline": "イベントタイムライン",
    "risks": "リスク分析",
    "opportunities": "機会分析",
    "recommended_actions": "推奨アクション",
    "uncertainty": "不確実性評価",
    "evidence_references": "エビデンス参照",
    "cognitive_evaluation": "認知シミュレーション評価",
}
