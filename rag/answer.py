from __future__ import annotations

import os
from textwrap import dedent

from rag.filters import QueryFilters


def _review_body(document: str) -> str:
    # Fix 3: stored docs are "metadata prefix + \n\n + review text" (see
    # ingest.py). The context block already renders metadata from the
    # payload, so only the body is shown to avoid duplicating it.
    # Handles both "Season (NH)" (legacy index) and "Season (park-local)".
    if "\n\n" in document:
        head, body = document.split("\n\n", 1)
        if head.lstrip().startswith("Branch:"):
            return body.strip()
    return document


def _format_context(hits: list[dict], max_chars: int = 12000) -> str:
    parts: list[str] = []
    used = 0
    for h in hits:
        m = h.get("metadata") or {}
        body = _review_body(h.get("document", ""))
        block = dedent(
            f"""
            ---
            Review ID: {m.get("review_id", h.get("id"))}
            Branch: {m.get("branch")}
            Reviewer location: {m.get("reviewer_location")}
            Visit: {m.get("year_month")}  Rating: {m.get("rating")}/5
            Text:
            {body}
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
    model: str | None = None,
    metrics: dict | None = None,
) -> str:
    if not hits:
        return "No relevant reviews were retrieved. Try broadening your question."

    context = _format_context(hits)
    relax_note = "\n".join(filters.relaxations) if filters.relaxations else ""

    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            return _answer_openai(question, context, relax_note, model=model, metrics=metrics)
        except Exception as e:
            fallback = _answer_extractive(question, hits, relax_note)
            return f"LLM answer failed ({type(e).__name__}: {e}).\nShowing extractive fallback instead.\n\n{fallback}"

    return _answer_extractive(question, hits, relax_note)


def _answer_openai(
    question: str,
    context: str,
    relax_note: str,
    model: str | None = None,
    metrics: dict | None = None,
) -> str:
    import time

    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY + OPENAI_BASE_URL from env
    model_id = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    # Local runtimes (LM Studio / Ollama / vLLM) often run reasoning models
    # that think for thousands of tokens before answering. For RAG synthesis
    # we want a direct grounded answer, so default to no reasoning locally.
    # Override with LLM_REASONING_EFFORT=low|medium|high (or "auto" to omit).
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    is_local = any(h in base_url for h in ("127.0.0.1", "localhost", ":1234", ":1235", ":11434", ":8000"))
    effort = os.environ.get("LLM_REASONING_EFFORT", "none" if is_local else "auto")
    extra = None if effort.lower() == "auto" else {"reasoning_effort": effort}
    system = dedent(
        """You are an analyst for Disneyland guest reviews.
        Answer ONLY using the provided review excerpts and their metadata.
        If evidence is mixed, say so. If evidence is thin, say you are unsure.
        Format rules (follow exactly):
        1. Paragraph 1 is the direct answer to the question in 2-4 sentences.
        2. Then a structured breakdown as numbered points (1. 2. 3.), each
           starting with a short lead phrase. Put each point on its own
           paragraph, starting exactly with "1. ", "2. ", and so on.
           Support each point with one
           short verbatim quote plus its Review ID in parentheses,
           e.g. ("quote..." 123456789).
        3. NEVER use the * character anywhere in your answer. No bullets,
           no bold markers, no italics. Numbers and plain paragraphs only.
        Keep the answer concise and practical for a customer-experience team."""
    )
    user = f"Question:\n{question}\n\n"
    if relax_note:
        user += f"Note (retrieval):\n{relax_note}\n\n"
    user += f"Retrieved reviews:\n{context}"
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "1500")),
        **({"extra_body": extra} if extra else {}),
    )
    elapsed = time.perf_counter() - t0
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    if not content:
        # Some local reasoning models put the whole answer in
        # reasoning_content when the token budget runs out mid-thought.
        reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
        if reasoning:
            content = reasoning[-2000:].strip()
    if metrics is not None:
        usage = getattr(resp, "usage", None)
        ct = getattr(usage, "completion_tokens", 0) or 0
        metrics.update(
            {
                "model": model_id,
                "completion_tokens": ct,
                "seconds": round(elapsed, 1),
                "tok_per_sec": round(ct / elapsed, 1) if elapsed > 0 else 0,
            }
        )
    return _sanitize_answer(content)


def _sanitize_answer(text: str) -> str:
    """Safety net: convert any *- or --style bullets the model emitted
    into numbered points, so the UI never shows asterisk lists."""
    import re

    out: list[str] = []
    n = 0
    for line in text.splitlines():
        m = re.match(r"^(\s*)[*\-]\s+(.*)$", line)
        if m:
            n += 1
            out.append(f"{m.group(1)}{n}. {m.group(2)}")
        else:
            out.append(line)
    return "\n".join(out)


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
        snippet = _review_body(h.get("document") or "")[:400].replace("\n", " ")
        lines.append(
            f"- [{m.get('review_id')}] {m.get('branch')} | "
            f"{m.get('reviewer_location')} | {m.get('year_month')} | {m.get('rating')}/5 — {snippet}..."
        )
    return "\n".join(lines)
