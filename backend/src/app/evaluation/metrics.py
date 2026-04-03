"""具象メトリクス: 既存 evaluation.py のロジックを BaseMetric パターンに昇格"""

import math
import re
from collections import Counter
from typing import Any

from src.app.evaluation.base import BaseMetric

# 標準スタンスカテゴリ
STANDARD_STANCES = {"賛成", "反対", "中立", "条件付き賛成", "条件付き反対"}


class DiversityMetric(BaseMetric):
    """Shannon entropy ベースの意見多様性指標 (0-1 正規化)。"""

    name = "diversity"
    description = "スタンス分布の均等性 (Shannon entropy)"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "shannon_entropy_normalized"}}

        stances = [r.get("stance", "中立") for r in responses]
        counter = Counter(stances)
        total = len(stances)
        n_categories = len(counter)

        if n_categories <= 1:
            return {"score": 0.0, "details": {"method": "shannon_entropy_normalized", "n_categories": 1}}

        entropy = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        max_entropy = math.log2(n_categories)
        score = round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0

        return {
            "score": score,
            "details": {
                "method": "shannon_entropy_normalized",
                "n_categories": n_categories,
                "entropy": round(entropy, 4),
            },
        }


class ConsistencyMetric(BaseMetric):
    """プロフィールと回答の整合性スコア (0-1)。"""

    name = "consistency"
    description = "エージェントの性格特性と回答の一貫性"

    def compute(self, **kwargs: Any) -> dict:
        agents = kwargs.get("agents", [])
        responses = kwargs.get("responses", [])

        if not agents or not responses or len(agents) != len(responses):
            return {"score": 0.0, "details": {"method": "profile_response_alignment"}}

        consistent_count = 0
        total = len(agents)

        for agent, resp in zip(agents, responses):
            big_five = agent.get("big_five", {})
            values = agent.get("values", {})
            stance = resp.get("stance", "中立")

            score = 0.0
            checks = 0

            if big_five.get("O", 0.5) > 0.7:
                if stance in ("賛成", "条件付き賛成"):
                    score += 1.0
                elif stance == "中立":
                    score += 0.5
                checks += 1
            elif big_five.get("O", 0.5) < 0.3:
                if stance in ("反対", "条件付き反対"):
                    score += 1.0
                elif stance == "中立":
                    score += 0.5
                checks += 1

            if big_five.get("N", 0.5) > 0.7:
                if resp.get("confidence", 0.5) < 0.6:
                    score += 1.0
                checks += 1

            if values:
                top_value = max(values, key=values.get) if values else ""
                reason = resp.get("reason", "").lower()
                if top_value and top_value in reason:
                    score += 1.0
                checks += 1

            if checks > 0 and score / checks >= 0.5:
                consistent_count += 1

        final_score = round(consistent_count / total, 4) if total > 0 else 0.0
        return {
            "score": final_score,
            "details": {
                "method": "profile_response_alignment",
                "consistent_count": consistent_count,
                "total": total,
            },
        }


class ConvergenceMetric(BaseMetric):
    """多数派への収束度 (0-1)。高いほど意見が集約している。"""

    name = "convergence"
    description = "多数派スタンスへの集中度"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "majority_ratio"}}

        stances = [r.get("stance", "中立") for r in responses]
        counter = Counter(stances)
        total = len(stances)
        majority_count = counter.most_common(1)[0][1]
        majority_stance = counter.most_common(1)[0][0]

        score = round(majority_count / total, 4)
        return {
            "score": score,
            "details": {
                "method": "majority_ratio",
                "majority_stance": majority_stance,
                "majority_count": majority_count,
                "total": total,
            },
        }


class CoverageMetric(BaseMetric):
    """スタンスカバレッジ (0-1)。標準5カテゴリのうち何割が出現したか。"""

    name = "coverage"
    description = "標準スタンスカテゴリのカバー率"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "stance_coverage"}}

        observed = {r.get("stance", "中立") for r in responses}
        covered = observed & STANDARD_STANCES
        score = round(len(covered) / len(STANDARD_STANCES), 4)

        return {
            "score": score,
            "details": {
                "method": "stance_coverage",
                "observed_stances": sorted(observed),
                "covered_count": len(covered),
                "total_categories": len(STANDARD_STANCES),
            },
        }


# ---------------------------------------------------------------------------
# Phase 4 追加メトリクス
# ---------------------------------------------------------------------------

# 日本語トークン分割: 句読点・助詞・スペースで分割し、意味のある単位を抽出
_JP_TOKEN_PATTERN = re.compile(
    r"[一-龥ぁ-んァ-ヴー\w]+"
)


class ResponseDepthMetric(BaseMetric):
    """活性化レスポンスの reason + personal_story 平均文字数を測定する。

    目標: 平均 250 文字以上で score=1.0。0 文字で 0.0。線形補間。
    """

    name = "response_depth"
    description = "活性化レスポンスの理由説明の深さ（平均文字数）"

    TARGET_CHARS = 250

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "avg_reason_length", "avg_chars": 0}}

        total_chars = 0
        valid_count = 0
        for r in responses:
            if r.get("_failed"):
                continue
            reason = r.get("reason", "")
            personal_story = r.get("personal_story", "")
            total_chars += len(reason) + len(personal_story)
            valid_count += 1

        if valid_count == 0:
            return {"score": 0.0, "details": {"method": "avg_reason_length", "avg_chars": 0}}

        avg_chars = total_chars / valid_count
        score = min(1.0, avg_chars / self.TARGET_CHARS)

        return {
            "score": round(score, 4),
            "details": {
                "method": "avg_reason_length",
                "avg_chars": round(avg_chars, 1),
                "target_chars": self.TARGET_CHARS,
                "valid_responses": valid_count,
            },
        }


class MeetingPolarizationMetric(BaseMetric):
    """Meeting 各ラウンドのスタンス多様性を測定する。

    各ラウンドのユニークな position 数をカウントし、最終ラウンドでも
    分極が維持されているかを評価する。
    目標: 最終ラウンドでも少なくとも 2 つ以上のユニークな立場が残る。
    score = 最終ラウンドのユニーク立場数 / 参加者数（上限1.0）。
    """

    name = "meeting_polarization"
    description = "Meeting 最終ラウンドのスタンス多様性維持度"

    # 最終ラウンドでこれ以上のユニーク立場比率なら score=1.0
    TARGET_DIVERSITY_RATIO = 0.4

    def compute(self, **kwargs: Any) -> dict:
        meeting_rounds: list[list[dict]] = kwargs.get("meeting_rounds", [])
        if not meeting_rounds:
            return {"score": 0.0, "details": {"method": "round_stance_diversity", "rounds": 0}}

        round_stats = []
        for round_idx, arguments in enumerate(meeting_rounds):
            positions = [
                self._normalize_position(a.get("position", ""))
                for a in arguments
                if a.get("position")
            ]
            unique = len(set(positions))
            total = len(positions)
            round_stats.append({
                "round": round_idx + 1,
                "unique_positions": unique,
                "total_arguments": total,
            })

        # 最終ラウンドのスタンス多様性で評価
        last = round_stats[-1]
        if last["total_arguments"] == 0:
            score = 0.0
        else:
            ratio = last["unique_positions"] / last["total_arguments"]
            score = min(1.0, ratio / self.TARGET_DIVERSITY_RATIO)

        return {
            "score": round(score, 4),
            "details": {
                "method": "round_stance_diversity",
                "rounds": len(meeting_rounds),
                "round_stats": round_stats,
                "target_diversity_ratio": self.TARGET_DIVERSITY_RATIO,
            },
        }

    @staticmethod
    def _normalize_position(pos: str) -> str:
        """立場表現を正規化して比較可能にする。"""
        pos = pos.strip()
        for label in ("条件付き賛成", "条件付き反対", "賛成", "反対", "中立"):
            if label in pos:
                return label
        return pos[:20]


class LexicalDiversityMetric(BaseMetric):
    """全エージェント応答の語彙多様性を Type-Token Ratio (TTR) で測定する。

    各エージェントの reason テキストを結合し、全体の TTR を計算する。
    score = TTR（0.0〜1.0）。高いほど語彙が豊富で、エージェント間の
    表現の画一化が少ない。
    """

    name = "lexical_diversity"
    description = "全エージェント応答の語彙多様性 (Type-Token Ratio)"

    def compute(self, **kwargs: Any) -> dict:
        responses = kwargs.get("responses", [])
        if not responses:
            return {"score": 0.0, "details": {"method": "type_token_ratio", "types": 0, "tokens": 0}}

        all_tokens: list[str] = []
        for r in responses:
            if r.get("_failed"):
                continue
            text = r.get("reason", "") + " " + r.get("personal_story", "")
            tokens = _JP_TOKEN_PATTERN.findall(text)
            all_tokens.extend(tokens)

        if not all_tokens:
            return {"score": 0.0, "details": {"method": "type_token_ratio", "types": 0, "tokens": 0}}

        types = len(set(all_tokens))
        tokens_count = len(all_tokens)
        ttr = types / tokens_count

        return {
            "score": round(ttr, 4),
            "details": {
                "method": "type_token_ratio",
                "types": types,
                "tokens": tokens_count,
            },
        }
