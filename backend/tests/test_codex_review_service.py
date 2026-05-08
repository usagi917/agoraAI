import json

from src.app.services.codex_review_service import (
    CODEX_CONTEXT_CHAR_LIMIT,
    CODEX_FIELD_CHAR_LIMIT,
    CodexReviewService,
)


def test_compact_for_codex_trims_large_text_fields():
    service = CodexReviewService()
    compacted = service._compact_for_codex({"summary_markdown": "x" * (CODEX_FIELD_CHAR_LIMIT + 100)})

    assert len(compacted["summary_markdown"]) < CODEX_FIELD_CHAR_LIMIT + 80
    assert "TRUNCATED" in compacted["summary_markdown"]


def test_compact_for_codex_prioritizes_decision_fields():
    service = CodexReviewService()
    payload = {f"noise_{i}": i for i in range(30)}
    payload["decision_brief"] = {"recommendation": "条件付きGo"}
    payload["quality"] = {"status": "unsupported"}

    compacted = service._compact_for_codex(payload)

    assert list(compacted.keys())[:2] == ["decision_brief", "quality"]
    assert compacted["_truncated_keys"] > 0
    assert len(json.dumps(compacted, ensure_ascii=False)) < CODEX_CONTEXT_CHAR_LIMIT
