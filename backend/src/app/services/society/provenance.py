"""方法論メタデータ（Provenance）モジュール

シミュレーション結果に学術的な再現性・透明性を付与するための構造化メタデータを生成する。

- _get_git_hash()   : 現在の git commit hash を取得
- build_provenance(): 方法論、データソース、パラメータ、品質メトリクス、制約、再現性情報を返す
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Optional


def _get_git_hash() -> str:
    """現在の git commit hash（short形式）を取得する。

    取得できない場合は 'unknown' を返す。

    Returns:
        7文字の git commit hash 文字列、または 'unknown'
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


# 組み込みデータソース（日本の国勢調査・統計データ）
_BUILTIN_DATA_SOURCES: list[dict] = [
    {
        "name": "2020 国勢調査",
        "used_for": "age/region/gender distribution weights",
    },
    {
        "name": "国税庁 2021 民間給与実態統計調査",
        "used_for": "income bracket distribution",
    },
    {
        "name": "総務省 統計局 人口推計 2022",
        "used_for": "regional population proportions",
    },
]

# 固定の制約事項（常に適用）
_STATIC_LIMITATIONS: list[str] = [
    "LLMが生成した意見は実際の人間の選好を反映するものではない",
    "エージェントの性格は統計的にサンプリングされたものであり、実証的に測定されたものではない",
    "会議レイヤーは10名の参加者に限定されており、熟議の深さに制約がある",
]


def build_provenance(
    population_size: int,
    selected_count: int,
    effective_sample_size: float,
    activation_params: Optional[dict] = None,
    meeting_params: Optional[dict] = None,
    grounding_sources: Optional[list[dict]] = None,
    quality_metrics: Optional[dict] = None,
    seed: Optional[int] = None,
    provider_bias_detected: bool = False,
    survey_comparison: Optional[dict] = None,
) -> dict:
    """シミュレーション結果のプロベナンス（方法論メタデータ）を構築する。

    Args:
        population_size: シミュレーション母集団のエージェント数
        selected_count: 活性化フェーズで選出されたエージェント数
        effective_sample_size: ポスト層化ウェイト適用後の実効標本サイズ
        activation_params: 活性化フェーズのパラメータ辞書（temperature など）
        meeting_params: 会議フェーズのパラメータ辞書（num_rounds, participants など）
        grounding_sources: 追加のデータグラウンディングソース一覧
        quality_metrics: 外部から計算された品質メトリクス辞書
        seed: 乱数シード（再現性のために記録）
        provider_bias_detected: LLMプロバイダ間でスタンス分布の有意差が検出されたか
        survey_comparison: 世論調査との比較結果辞書（kl_divergence, emd, best_match_source, matched_surveys）

    Returns:
        以下のキーを持つ辞書:
        - methodology: 方法論の説明と引用
        - data_sources: 使用データソース一覧
        - parameters: 実行時パラメータ
        - quality_metrics: 品質メトリクス
        - limitations: 制約事項と注意点
        - reproducibility: 再現性情報（seed, git hash, timestamp）
    """
    # --- methodology ---
    methodology = {
        "framework": "Modified Fishkin Deliberative Polling",
        "citation": (
            "Fishkin, J.S. (2009). When the People Speak: Deliberative Democracy "
            "and Public Consultation. Oxford University Press."
        ),
        "population_sampling": (
            "Census-weighted stratified random sampling with post-stratification raking"
        ),
        "activation_protocol": (
            "Single-shot LLM elicitation with Big Five personality-based temperature mapping"
        ),
        "deliberation_protocol": (
            "3-round structured discussion with moderator-selected direct exchanges"
        ),
        "aggregation_method": (
            "Post-stratification weighted counting with bootstrap confidence intervals "
            "(Kish 1965)"
        ),
    }

    # --- data_sources ---
    data_sources: list[dict] = list(_BUILTIN_DATA_SOURCES)
    if grounding_sources:
        for source in grounding_sources:
            data_sources.append(source)

    # --- parameters ---
    num_rounds = (
        meeting_params.get("num_rounds", 3) if meeting_params else 3
    )
    num_participants = (
        meeting_params.get("participants", 10) if meeting_params else 10
    )
    temperature_base = (
        activation_params.get("temperature", 0.5) if activation_params else 0.5
    )
    parameters = {
        "population_size": population_size,
        "selected_sample_size": selected_count,
        "effective_sample_size": effective_sample_size,
        "meeting_rounds": num_rounds,
        "meeting_participants": num_participants,
        "activation_temperature_base": temperature_base,
        "random_seed": seed,
    }

    # --- limitations (固定 + 動的) ---
    limitations: list[str] = list(_STATIC_LIMITATIONS)

    if effective_sample_size < 30:
        limitations.append(
            "有効標本数が30未満であり、統計的信頼性が限定的"
        )

    if provider_bias_detected:
        limitations.append(
            "LLMプロバイダ間でスタンス分布に有意差が検出された"
        )

    # --- reproducibility ---
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    reproducibility = {
        "random_seed": seed,
        "code_version": _get_git_hash(),
        "timestamp": timestamp,
        "deterministic": False,
    }

    # --- survey_comparison (optional) ---
    result: dict = {
        "methodology": methodology,
        "data_sources": data_sources,
        "parameters": parameters,
        "quality_metrics": quality_metrics if quality_metrics is not None else {},
        "limitations": limitations,
        "reproducibility": reproducibility,
    }

    if survey_comparison is not None:
        kl = survey_comparison.get("kl_divergence", 0.0)
        emd = survey_comparison.get("emd", 0.0)
        best_source = survey_comparison.get("best_match_source", "")

        result["survey_validation"] = {
            "kl_divergence": kl,
            "emd": emd,
            "matched_survey_source": best_source,
        }

        # data_sources に比較した調査の情報を追加
        for survey in survey_comparison.get("matched_surveys", []):
            source_name = survey.get("source", best_source)
            data_sources.append({
                "name": source_name,
                "used_for": "simulation output validation",
            })

        # KL > 0.3: 乖離警告
        if kl > 0.3:
            limitations.append(
                "シミュレーション出力と実世論調査の間に大きな乖離が検出された"
                f"（KL-divergence: {kl:.3f}）"
            )

        # KL <= 0.15: 整合性注記
        if kl <= 0.15:
            methodology["survey_validation_note"] = (
                "実世論調査との整合性が確認された"
                f"（KL-divergence: {kl:.3f}）"
            )

    return result
