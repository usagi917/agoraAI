"""LLMClient の JSON 抽出ロジックテスト"""

from src.app.llm.client import _extract_json


def test_extract_plain_json():
    result = _extract_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_extract_json_from_markdown_block():
    text = '```json\n{"key": "value"}\n```'
    result = _extract_json(text)
    assert result == {"key": "value"}


def test_extract_json_from_text_with_braces():
    text = 'Here is the result: {"key": "value"} that is it.'
    result = _extract_json(text)
    assert result == {"key": "value"}


def test_extract_json_with_thinking_tags():
    text = '<think>Let me think about this...</think>\n{"key": "value"}'
    result = _extract_json(text)
    assert result == {"key": "value"}


def test_extract_json_returns_none_for_invalid():
    result = _extract_json("This is not JSON at all")
    assert result is None


def test_extract_json_empty_string():
    result = _extract_json("")
    assert result is None


def test_extract_json_nested():
    text = '{"entities": [{"id": "e1", "name": "test"}], "count": 1}'
    result = _extract_json(text)
    assert result["count"] == 1
    assert len(result["entities"]) == 1


def test_extract_json_code_block_without_lang():
    text = '```\n{"key": "value"}\n```'
    result = _extract_json(text)
    assert result == {"key": "value"}
