from __future__ import annotations

import os
from textwrap import dedent

from rag.config import OPENAI_MODEL_DEFAULT
from rag.filters import QueryFilters


def _format_context(hits: list[dict], max_chars: int = 12000) -> str:
    parts: list[str] = []
    used = 0
    for h in hits:
        m = h.get("metadata") or {}
        block = dedent(
            f"""
            ---
            Review ID: {m.get("review_id", h.get("id"))}
            Branch: {m.get("branch")}
            Reviewer location: {m.get("reviewer_location")}
            Visit: {m.get("year_month")}  Rating: {m.get("rating")}/5
            Text:
            {h.get("document", "")}
            """
        ).strip()
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def answer_question(
    question: str,
    hits: list[dict],
    filters: QueryFilters,
) -> str:
    if not hits:
        return "No relevant reviews were retrieved. Try broadening your question."

    context = _format_context(hits)
    relax_note = "\n".join(filters.relaxations) if filters.relaxations else ""

    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return _answer_openai(question, context, relax_note)

    return _answer_extractive(question, hits, relax_note)


def _answer_openai(question: str, context: str, relax_note: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    system = dedent(
        """You are an analyst for Disneyland guest reviews.
        Answer ONLY using the provided review excerpts and their metadata.
        If evidence is mixed, say so. If evidence is thin, say you are unsure.
        Cite Review IDs in parentheses when you paraphrase specific reviews.
        Keep the answer concise and practical for a customer-experience team."""
    )
    user = f"Question:\n{question}\n\n"
    if relax_note:
        user += f"Note (retrieval):\n{relax_note}\n\n"
    user += f"Retrieved reviews:\n{context}"
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", OPENAI_MODEL_DEFAULT),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def _answer_extractive(question: str, hits: list[dict], relax_note: str) -> str:
    lines = [
        "Open-ended synthesis needs an LLM. Set OPENAI_API_KEY for full answers.",
        "Below are the top retrieved reviews (by similarity) with metadata.",
        "",
    ]
    if relax_note:
        lines.extend([relax_note, ""])
    lines.append(f"Q: {question}")
    lines.append("")
    for h in hits[:8]:
        m = h.get("metadata") or {}
        snippet = (h.get("document") or "")[:400].replace("\n", " ")
        lines.append(
            f"- [{m.get('review_id')}] {m.get('branch')} | "
            f"{m.get('reviewer_location')} | {m.get('year_month')} | {m.get('rating')}/5 — {snippet}..."
        )
    return "\n".join(lines)
