from types import SimpleNamespace

import pytest

from src.app.services.quality import (
    build_prompt_evidence_ref,
    build_quality_summary,
    enforce_quality_gate,
    extract_quality,
    normalize_evidence_mode,
    normalize_scenarios,
    rank_document_evidence_refs,
)


def test_build_prompt_evidence_ref_returns_none_for_empty_prompt():
    assert build_prompt_evidence_ref("") is None


def test_build_prompt_evidence_ref_builds_prompt_source():
    ref = build_prompt_evidence_ref("Analyze this market")
    assert ref is not None
    assert ref["source_type"] == "prompt_input"
    assert ref["label"] == "User prompt"


def test_build_quality_summary_marks_fallback_as_draft():
    quality = build_quality_summary(
        fallback_used=True,
        evidence_refs=[{"source_type": "prompt_input", "source_id": "prompt_input"}],
        fallback_reason="fallback",
    )
    assert quality["status"] == "draft"
    assert quality["fallback_used"] is True
    assert "fallback_used" in quality["issues"]
    assert quality["trust_level"] == "low_trust"


def test_build_quality_summary_marks_missing_evidence_as_unsupported():
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=[],
    )
    assert quality["status"] == "unsupported"
    assert quality["evidence_available"] is False
    assert quality["trust_level"] == "no_evidence"


def test_build_quality_summary_marks_prompt_only_as_draft():
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=[{"source_type": "prompt_input", "source_id": "prompt_input"}],
    )
    assert quality["status"] == "draft"
    assert quality["trust_level"] == "low_trust"
    assert "prompt_only_sources" in quality["issues"]


def test_build_quality_summary_marks_prompt_only_as_unsupported_in_strict_mode():
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=[{"source_type": "prompt_input", "source_id": "prompt_input"}],
        evidence_mode="strict",
    )
    assert quality["status"] == "unsupported"
    assert quality["unsupported_reason"] == "strict_document_evidence_required"
    assert "strict_document_evidence_required" in quality["issues"]


def test_build_quality_summary_marks_document_backed_as_verified():
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=[{"source_type": "document_chunk", "source_id": "doc-1"}],
    )
    assert quality["status"] == "verified"
    assert quality["trust_level"] == "high_trust"


def test_extract_quality_prefers_top_level_quality():
    payload = {"quality": {"status": "verified"}}
    assert extract_quality(payload)["status"] == "verified"


def test_extract_quality_falls_back_to_sections_quality():
    payload = {"sections": {"quality": {"status": "draft"}}}
    assert extract_quality(payload)["status"] == "draft"


def test_normalize_evidence_mode_supports_legacy_aliases():
    assert normalize_evidence_mode("required") == "strict"
    assert normalize_evidence_mode("prompt_allowed") == "prefer"
    assert normalize_evidence_mode("off") == "off"


def test_normalize_scenarios_adds_new_fields():
    scenarios = [{
        "description": "A",
        "probability": 0.6,
        "agreement_ratio": 0.5,
        "mean_confidence": 0.7,
    }]
    result = normalize_scenarios(
        scenarios,
        evidence_refs=[{"source_type": "prompt_input", "source_id": "prompt_input"}],
    )
    assert result[0]["scenario_score"] == 0.6
    assert result[0]["support_ratio"] == 0.5
    assert result[0]["model_confidence_mean"] == 0.7
    assert result[0]["evidence_refs"][0]["source_id"] == "prompt_input"
    assert result[0]["quality"]["status"] == "draft"


def test_rank_document_evidence_refs_prefers_relevant_chunk():
    document = SimpleNamespace(
        id="doc-1",
        filename="policy.md",
        text_content=(
            "Battery pricing outlook and chemistry trends.\n\n"
            "Regulation risk is rising because subsidy rules change in 2026.\n\n"
            "Distribution strategy is still undecided."
        ),
    )

    refs = rank_document_evidence_refs(document, query_text="regulation subsidy risk", max_chunks=1)

    assert len(refs) == 1
    assert refs[0]["source_type"] == "document_chunk"
    assert "Regulation risk" in refs[0]["excerpt"]


def test_enforce_quality_gate_raises_for_strict_non_verified_quality():
    quality = build_quality_summary(
        fallback_used=False,
        evidence_refs=[{"source_type": "prompt_input", "source_id": "prompt_input"}],
        evidence_mode="strict",
    )

    with pytest.raises(ValueError, match="strict evidence gate"):
        enforce_quality_gate(quality, evidence_mode="strict", context="report")
