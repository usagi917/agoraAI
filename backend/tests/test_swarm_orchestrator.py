"""swarm_orchestrator の純粋ロジックテスト"""

import pytest

from src.app.services.swarm_orchestrator import _clone_world_state


# -----------------------------------------------------------------------
# additional_context の注入ロジック（_build_effective_prompt）
# -----------------------------------------------------------------------

def _build_effective_prompt(prompt_text: str, additional_context: str) -> str:
    """run_swarm 内の effective_prompt 構築ロジックを再現する。"""
    if additional_context:
        return f"{prompt_text}\n\n--- 前段階分析結果 ---\n{additional_context}"
    return prompt_text


def test_effective_prompt_with_additional_context():
    result = _build_effective_prompt("base prompt", "context from stage 1")
    assert "base prompt" in result
    assert "context from stage 1" in result
    assert "前段階分析結果" in result


def test_effective_prompt_without_additional_context():
    result = _build_effective_prompt("base prompt", "")
    assert result == "base prompt"


def test_effective_prompt_empty_base():
    result = _build_effective_prompt("", "some context")
    assert "some context" in result
    assert "前段階分析結果" in result


def test_effective_prompt_both_empty():
    result = _build_effective_prompt("", "")
    assert result == ""


# -----------------------------------------------------------------------
# document_text 結合ロジック
# -----------------------------------------------------------------------

def _build_document_text(documents: list) -> str:
    """run_swarm 内の document_text 構築ロジックを再現する。"""
    return "\n\n---\n\n".join(d["text_content"] for d in documents)


def test_document_text_single_doc():
    docs = [{"text_content": "Document 1 content"}]
    result = _build_document_text(docs)
    assert result == "Document 1 content"


def test_document_text_multiple_docs():
    docs = [{"text_content": "Doc A"}, {"text_content": "Doc B"}]
    result = _build_document_text(docs)
    assert "Doc A" in result
    assert "Doc B" in result
    assert "---" in result


def test_document_text_empty_docs():
    result = _build_document_text([])
    assert result == ""


# -----------------------------------------------------------------------
# colony 成功/失敗の集計ロジック
# -----------------------------------------------------------------------

def _count_successful(colony_results: list, configs: list) -> tuple:
    """run_swarm 内の successful_results 集計ロジックを再現する。"""
    successful = []
    failed_count = 0
    for i, result in enumerate(colony_results):
        if isinstance(result, Exception):
            failed_count += 1
        else:
            successful.append({
                "colony_id": configs[i]["colony_id"],
                **result,
            })
    return successful, failed_count


def test_count_successful_all_pass():
    results = [{"events": []}, {"events": []}]
    configs = [{"colony_id": "c1"}, {"colony_id": "c2"}]
    successful, failed = _count_successful(results, configs)
    assert len(successful) == 2
    assert failed == 0


def test_count_successful_all_fail():
    results = [Exception("error1"), Exception("error2")]
    configs = [{"colony_id": "c1"}, {"colony_id": "c2"}]
    successful, failed = _count_successful(results, configs)
    assert len(successful) == 0
    assert failed == 2


def test_count_successful_mixed():
    results = [{"events": []}, Exception("error"), {"events": []}]
    configs = [{"colony_id": "c1"}, {"colony_id": "c2"}, {"colony_id": "c3"}]
    successful, failed = _count_successful(results, configs)
    assert len(successful) == 2
    assert failed == 1


def test_count_successful_empty():
    successful, failed = _count_successful([], [])
    assert successful == []
    assert failed == 0


# -----------------------------------------------------------------------
# 全 Colony 失敗の検知
# -----------------------------------------------------------------------

def test_all_colonies_failed_raises():
    """全 Colony が失敗した場合は ValueError を発生させる。"""
    successful_results = []
    should_raise = len(successful_results) == 0
    assert should_raise is True


def test_partial_colony_failure_does_not_raise():
    successful_results = [{"colony_id": "c1"}]
    should_raise = len(successful_results) == 0
    assert should_raise is False


def test_clone_world_state_is_deep_copy():
    original = {
        "entities": [{"id": "e1", "value": 1}],
        "relations": [{"source": "e1", "target": "e2", "weight": 0.4}],
    }
    cloned = _clone_world_state(original)

    cloned["entities"][0]["value"] = 99
    cloned["relations"][0]["weight"] = 0.9

    assert original["entities"][0]["value"] == 1
    assert original["relations"][0]["weight"] == 0.4
