"""Compact population activation prompt and schema tests."""

from src.app.services.society.activation_prompts import (
    build_activation_prompt,
    build_activation_response_format,
)


def _agent() -> dict:
    return {
        "id": "agent-1",
        "demographics": {
            "age": 43,
            "gender": "female",
            "occupation": "会社員",
            "region": "関東（郊外）",
            "income_bracket": "lower_middle",
            "education": "bachelor",
            "employment_status": "employed",
            "household_type": "couple_with_children",
        },
        "big_five": {"O": 0.6, "C": 0.7, "E": 0.4, "A": 0.5, "N": 0.3},
        "values": {"security": 0.9, "fairness": 0.8, "growth": 0.4},
        "speech_style": "率直で簡潔",
    }


def test_compact_prompt_is_bounded_and_omits_long_story_fields() -> None:
    system_prompt, user_prompt = build_activation_prompt(
        _agent(),
        "公共交通の値上げについて",
        compact=True,
    )

    assert len(system_prompt) < 2_000
    assert len(user_prompt) < 500
    assert "personal_story" not in system_prompt
    assert "80文字以内" in system_prompt
    assert "性別=female" in system_prompt
    assert "世帯=couple_with_children" in system_prompt


def test_activation_response_format_uses_strict_json_schema() -> None:
    response_format = build_activation_response_format(compact=True)
    schema = response_format["json_schema"]

    assert response_format["type"] == "json_schema"
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == {
        "stance",
        "confidence",
        "reason",
        "concern",
        "priority",
    }
    assert "personal_story" not in schema["schema"]["properties"]


def test_minimal_population_schema_only_emits_prediction_fields() -> None:
    response_format = build_activation_response_format(compact=True, minimal=True)
    schema = response_format["json_schema"]["schema"]

    assert set(schema["properties"]) == {"stance", "confidence"}
    assert set(schema["required"]) == {"stance", "confidence"}

    system_prompt, _ = build_activation_prompt(_agent(), "テーマ", compact=True, minimal=True)
    assert "stanceとconfidenceだけ" in system_prompt


def test_compact_prompt_includes_bounded_social_update_context() -> None:
    agent = _agent()
    agent["social_context"] = {
        "initial_stance": "賛成",
        "network_stance": "条件付き賛成",
    }

    _, user_prompt = build_activation_prompt(agent, "公共交通の値上げについて", compact=True)

    assert "最初の立場: 賛成" in user_prompt
    assert "周囲との相互作用後: 条件付き賛成" in user_prompt
    assert "最終反応" in user_prompt
    assert len(user_prompt) < 700


def test_compact_prompt_bounds_untrusted_long_theme_for_cost_safety() -> None:
    long_theme = "冒頭" + ("政策の詳細" * 1_000) + "末尾の質問"

    _, user_prompt = build_activation_prompt(_agent(), long_theme, compact=True, minimal=True)

    assert len(user_prompt) < 1_000
    assert "冒頭" in user_prompt
    assert "末尾の質問" in user_prompt


def test_compact_prompt_keeps_bounded_kg_and_grounding_evidence() -> None:
    agent = _agent()
    agent["kg_context"] = "地域バスの利用者数が減少している。" + ("背景" * 500)
    grounding_facts = [
        {
            "fact": "運転手の平均年齢が上昇している",
            "source": "交通統計",
            "date": "2026-01-01",
        },
        {
            "fact": "設備更新費が前年比で増えた",
            "source": "事業報告",
            "date": "2026-02-01",
        },
        {"fact": "3件目は上限外", "source": "別資料", "date": "2026-03-01"},
    ]

    system_prompt, _ = build_activation_prompt(
        agent,
        "公共交通政策",
        grounding_facts=grounding_facts,
        compact=True,
        minimal=True,
    )

    assert "地域バスの利用者数" in system_prompt
    assert "運転手の平均年齢" in system_prompt
    assert "設備更新費" in system_prompt
    assert "3件目は上限外" not in system_prompt
    assert len(system_prompt) < 1_500
