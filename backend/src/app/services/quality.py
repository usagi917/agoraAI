"""Quality and evidence helpers for simulation outputs."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.document import Document

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
MAX_EXCERPT_LENGTH = 240
MAX_BUNDLE_CHARS = 9000
DEFAULT_EVIDENCE_MODE = "prefer"
STRICT_EVIDENCE_MODES = {"strict"}
EVIDENCE_MODE_ALIASES = {
    "required": "strict",
    "strict": "strict",
    "prompt_allowed": "prefer",
    "prefer": "prefer",
    "off": "off",
    "disabled": "off",
    "none": "off",
}


def normalize_evidence_mode(mode: str | None) -> str:
    return EVIDENCE_MODE_ALIASES.get(str(mode or "").strip().lower(), DEFAULT_EVIDENCE_MODE)


def supports_evidence_mode(mode: str | None) -> bool:
    return str(mode or "").strip().lower() in EVIDENCE_MODE_ALIASES


def extract_run_config(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {
            "evidence_mode": DEFAULT_EVIDENCE_MODE,
            "trust_mode": "strict",
        }

    run_config = metadata.get("run_config")
    if not isinstance(run_config, dict):
        run_config = {}

    return {
        **run_config,
        "evidence_mode": normalize_evidence_mode(run_config.get("evidence_mode")),
        "trust_mode": str(run_config.get("trust_mode") or "strict"),
    }


def get_evidence_mode(metadata: dict[str, Any] | None, default: str = DEFAULT_EVIDENCE_MODE) -> str:
    config = extract_run_config(metadata)
    return normalize_evidence_mode(config.get("evidence_mode") or default)


def _has_document_evidence(refs: list[dict[str, Any]]) -> bool:
    return any(str(ref.get("source_type", "")).startswith("document") for ref in refs)


def _tokenize_for_relevance(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9A-Za-z\u3040-\u30ff\u3400-\u9fff_-]{2,}", text.lower())
        if len(token) >= 2
    }


def _iter_text_chunks(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[tuple[int, int, str]]:
    content = text or ""
    if not content.strip():
        return []

    chunks: list[tuple[int, int, str]] = []
    start = 0
    text_len = len(content)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append((start, end, chunk))
        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks


def _build_document_chunk_evidence_ref(
    document: Document,
    *,
    chunk_index: int,
    char_start: int,
    char_end: int,
    excerpt: str,
) -> dict[str, Any]:
    clipped_excerpt = excerpt[:MAX_EXCERPT_LENGTH]
    return {
        "source_type": "document_chunk",
        "source_id": document.id,
        "document_id": document.id,
        "chunk_id": f"{document.id}:{chunk_index}",
        "label": document.filename,
        "excerpt": clipped_excerpt,
        "char_start": char_start,
        "char_end": char_start + len(clipped_excerpt),
    }


def rank_document_evidence_refs(
    document: Document,
    *,
    query_text: str = "",
    max_chunks: int = 2,
) -> list[dict[str, Any]]:
    query_tokens = _tokenize_for_relevance(query_text or document.filename)
    ranked: list[tuple[tuple[float, float, int], dict[str, Any]]] = []

    for chunk_index, (char_start, char_end, chunk_text) in enumerate(
        _iter_text_chunks(document.text_content)
    ):
        chunk_tokens = _tokenize_for_relevance(chunk_text)
        overlap = len(query_tokens & chunk_tokens) if query_tokens else 0
        lexical_density = overlap / max(len(query_tokens), 1) if query_tokens else 0.0
        baseline = overlap if query_tokens else (1 if chunk_index == 0 else 0)
        score = (float(baseline), lexical_density, -char_start)
        ranked.append((
            score,
            _build_document_chunk_evidence_ref(
                document,
                chunk_index=chunk_index,
                char_start=char_start,
                char_end=char_end,
                excerpt=chunk_text,
            ),
        ))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [ref for _, ref in ranked[:max_chunks]]


def _dedupe_evidence_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for ref in refs:
        key = (
            ref.get("source_type"),
            ref.get("source_id"),
            ref.get("chunk_id"),
            ref.get("char_start"),
            ref.get("char_end"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)

    return deduped


def build_prompt_evidence_ref(prompt_text: str) -> dict[str, Any] | None:
    text = (prompt_text or "").strip()
    if not text:
        return None

    excerpt = text[:200]
    return {
        "source_type": "prompt_input",
        "source_id": "prompt_input",
        "label": "User prompt",
        "excerpt": excerpt,
        "char_start": 0,
        "char_end": len(excerpt),
    }


def build_document_evidence_ref(document: Document) -> dict[str, Any]:
    text = (document.text_content or "").strip()
    excerpt = text[:200]
    return {
        "source_type": "document",
        "source_id": document.id,
        "label": document.filename,
        "excerpt": excerpt,
        "char_start": 0,
        "char_end": len(excerpt),
    }


async def collect_simulation_evidence_refs(
    session: AsyncSession,
    project_id: str | None,
    prompt_text: str = "",
    *,
    query_text: str = "",
    max_documents: int = 3,
    max_document_chunks: int = 2,
    max_refs: int = 6,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    query = (query_text or prompt_text or "").strip()

    prompt_ref = build_prompt_evidence_ref(prompt_text)
    if prompt_ref:
        refs.append(prompt_ref)

    if not project_id:
        return refs

    result = await session.execute(
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
        .limit(max_documents)
    )
    documents = result.scalars().all()

    ranked_document_refs: list[dict[str, Any]] = []
    for document in documents:
        ranked_document_refs.extend(
            rank_document_evidence_refs(
                document,
                query_text=query,
                max_chunks=max_document_chunks,
            )
        )

    remaining_slots = max(max_refs - len(refs), 0)
    refs.extend(ranked_document_refs[:remaining_slots])
    return _dedupe_evidence_refs(refs)


def _format_evidence_context_part(
    ref: dict[str, Any],
    *,
    prompt_text: str,
) -> str:
    source_type = str(ref.get("source_type", ""))
    label = str(ref.get("label", "") or "Source")
    excerpt = str(ref.get("excerpt", "") or "").strip()

    if source_type == "prompt_input":
        prompt_body = (prompt_text or excerpt).strip()
        if not prompt_body:
            return ""
        return f"### User prompt\n{prompt_body}"

    location_bits = []
    if ref.get("chunk_id"):
        location_bits.append(str(ref["chunk_id"]))
    if ref.get("char_start") is not None and ref.get("char_end") is not None:
        location_bits.append(f"{ref['char_start']}:{ref['char_end']}")
    location = f" ({', '.join(location_bits)})" if location_bits else ""
    if not excerpt:
        return ""
    return f"### {label}{location}\n{excerpt}"


async def build_evidence_bundle(
    session: AsyncSession,
    project_id: str | None,
    prompt_text: str = "",
    *,
    query_text: str = "",
    inline_document_text: str = "",
    inline_document_label: str = "Input document",
    max_documents: int = 4,
    max_document_chunks: int = 3,
    max_refs: int = 8,
    max_chars: int = MAX_BUNDLE_CHARS,
) -> dict[str, Any]:
    query = (query_text or prompt_text or "").strip()
    refs = await collect_simulation_evidence_refs(
        session,
        project_id,
        prompt_text,
        query_text=query,
        max_documents=max_documents,
        max_document_chunks=max_document_chunks,
        max_refs=max_refs,
    )

    if inline_document_text.strip():
        inline_document = SimpleNamespace(
            id="inline_document",
            filename=inline_document_label,
            text_content=inline_document_text,
        )
        inline_refs = rank_document_evidence_refs(
            inline_document,
            query_text=query,
            max_chunks=max_document_chunks,
        )
        refs = merge_evidence_refs(refs, inline_refs[:max_refs])

    context_parts: list[str] = []
    selected_refs: list[dict[str, Any]] = []
    used_chars = 0

    for ref in refs:
        part = _format_evidence_context_part(ref, prompt_text=prompt_text)
        if not part:
            continue
        projected_len = used_chars + len(part) + (2 if context_parts else 0)
        if context_parts and projected_len > max_chars:
            break
        if not context_parts and len(part) > max_chars:
            part = part[:max_chars]
        context_parts.append(part)
        selected_refs.append(dict(ref))
        used_chars = projected_len

    return {
        "query_text": query,
        "evidence_refs": selected_refs or refs[:max_refs],
        "context_text": "\n\n".join(context_parts),
    }


def build_quality_summary(
    *,
    fallback_used: bool,
    evidence_refs: list[dict[str, Any]] | None = None,
    fallback_reason: str = "",
    calibration_status: str = "uncalibrated",
    evidence_mode: str = DEFAULT_EVIDENCE_MODE,
    unsupported_reason: str = "",
) -> dict[str, Any]:
    refs = evidence_refs or []
    normalized_mode = normalize_evidence_mode(evidence_mode)
    document_refs_count = sum(
        1 for ref in refs if str(ref.get("source_type", "")).startswith("document")
    )
    prompt_refs_count = sum(1 for ref in refs if ref.get("source_type") == "prompt_input")

    if document_refs_count > 0:
        trust_level = "high_trust"
    elif prompt_refs_count > 0:
        trust_level = "low_trust"
    else:
        trust_level = "no_evidence"

    issues: list[str] = []
    resolved_unsupported_reason = unsupported_reason

    if fallback_used:
        status = "draft"
        issues.append("fallback_used")
    elif trust_level == "high_trust":
        status = "verified"
    elif trust_level == "low_trust":
        if normalized_mode in STRICT_EVIDENCE_MODES:
            status = "unsupported"
            issues.append("strict_document_evidence_required")
            resolved_unsupported_reason = (
                resolved_unsupported_reason or "strict_document_evidence_required"
            )
        else:
            status = "draft"
            issues.append("prompt_only_sources")
    else:
        if normalized_mode == "off":
            status = "draft"
            issues.append("evidence_collection_disabled")
        else:
            status = "unsupported"
            issues.append("no_evidence_refs")
            resolved_unsupported_reason = resolved_unsupported_reason or "no_evidence_refs"

    if calibration_status != "calibrated":
        issues.append("uncalibrated_scores")

    return {
        "status": status,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "calibration_status": calibration_status,
        "evidence_mode": normalized_mode,
        "trust_level": trust_level,
        "evidence_available": bool(refs),
        "evidence_refs_count": len(refs),
        "document_refs_count": document_refs_count,
        "prompt_refs_count": prompt_refs_count,
        "unsupported_reason": resolved_unsupported_reason,
        "issues": issues,
    }


def extract_quality(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    quality = payload.get("quality")
    if isinstance(quality, dict):
        return dict(quality)

    sections = payload.get("sections")
    if isinstance(sections, dict):
        embedded_quality = sections.get("quality")
        if isinstance(embedded_quality, dict):
            return dict(embedded_quality)

    return {}


def normalize_scenarios(
    scenarios: list[dict[str, Any]] | None,
    *,
    evidence_refs: list[dict[str, Any]] | None = None,
    evidence_mode: str = DEFAULT_EVIDENCE_MODE,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    shared_refs = evidence_refs or []

    for scenario in scenarios or []:
        item = dict(scenario)
        if "scenario_score" not in item:
            item["scenario_score"] = item.get("probability", 0.0)
        if "support_ratio" not in item:
            item["support_ratio"] = item.get("agreement_ratio", 0.0)
        if "model_confidence_mean" not in item:
            item["model_confidence_mean"] = item.get("mean_confidence", 0.0)
        if "calibrated_probability" not in item:
            item["calibrated_probability"] = None
        if "calibration_version" not in item:
            item["calibration_version"] = None
        if "evidence_refs" not in item:
            item["evidence_refs"] = [dict(ref) for ref in shared_refs]
        if "quality" not in item:
            item["quality"] = build_quality_summary(
                fallback_used=False,
                evidence_refs=item.get("evidence_refs"),
                evidence_mode=evidence_mode,
            )
        normalized.append(item)

    return normalized


def build_section_detail(
    *,
    title: str,
    content: str = "",
    evidence_refs: list[dict[str, Any]] | None = None,
    fallback_used: bool = False,
    fallback_reason: str = "",
    evidence_mode: str = DEFAULT_EVIDENCE_MODE,
    unsupported_reason: str = "",
) -> dict[str, Any]:
    refs = [dict(ref) for ref in (evidence_refs or [])]
    return {
        "title": title,
        "content": content,
        "evidence_refs": refs,
        "quality": build_quality_summary(
            fallback_used=fallback_used,
            evidence_refs=refs,
            fallback_reason=fallback_reason,
            evidence_mode=evidence_mode,
            unsupported_reason=unsupported_reason,
        ),
    }


def enforce_quality_gate(
    quality: dict[str, Any],
    *,
    evidence_mode: str,
    context: str,
) -> None:
    normalized_mode = normalize_evidence_mode(evidence_mode)
    if normalized_mode not in STRICT_EVIDENCE_MODES:
        return

    if quality.get("status") == "verified":
        return

    reason = (
        str(quality.get("unsupported_reason") or "")
        or str(quality.get("fallback_reason") or "")
        or ",".join(str(issue) for issue in quality.get("issues", []))
        or "strict_document_evidence_required"
    )
    raise ValueError(f"{context} failed strict evidence gate: {reason}")


def merge_evidence_refs(*groups: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for refs in groups:
        if refs:
            merged.extend(refs)
    return _dedupe_evidence_refs(merged)


def has_document_evidence(refs: list[dict[str, Any]] | None) -> bool:
    return _has_document_evidence(refs or [])
