import os
import requests
import re


def _fallback_bullets(text: str, bullet_count: int) -> str:
    """
    Extremely simple fallback when the LLM endpoint is unavailable.
    Keeps the pipeline running so scheduled sends still deliver an email.
    """
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return ""

    # Naive sentence split; good enough as a "keep the lights on" fallback.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    picks = (sentences or [cleaned])[: max(1, bullet_count)]
    return "\n".join(f"- {s[:240].rstrip()}" for s in picks)


def summarize_content(text: str, focus: str, bullet_count: int = 3) -> str:
    return summarize_with_ollama(text, focus, bullet_count)


def _extract_bullets(output: str) -> list[str]:
    """
    Extract bullet-like lines from model output and normalize to "- ...".
    """
    if not output:
        return []
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    bullets: list[str] = []
    for line in lines:
        low = line.lower()
        if "here are" in low and "bullet" in low:
            continue

        if line.startswith(("-", "•", "*")):
            text = line.lstrip("-•* ").strip()
            if text:
                bullets.append(f"- {text}")
            continue

        m = re.match(r"^\d+\s*[\).:-]\s*(.+)$", line)
        if m:
            text = m.group(1).strip()
            if text:
                bullets.append(f"- {text}")
            continue

    return bullets


def _ollama_options_from_env() -> dict:
    """
    Convert optional env vars into Ollama generate options.
    Keeping this configurable makes it easier to tune summary "style" without code changes.
    """
    options: dict = {}
    # Use low temperature for deterministic bullet formatting.
    temp = os.getenv("OLLAMA_TEMPERATURE", "").strip()
    top_p = os.getenv("OLLAMA_TOP_P", "").strip()
    num_ctx = os.getenv("OLLAMA_NUM_CTX", "").strip()
    num_predict = os.getenv("OLLAMA_NUM_PREDICT", "").strip()
    repeat_penalty = os.getenv("OLLAMA_REPEAT_PENALTY", "").strip()

    def _maybe_float(v: str) -> float | None:
        try:
            return float(v)
        except Exception:
            return None

    def _maybe_int(v: str) -> int | None:
        try:
            return int(v)
        except Exception:
            return None

    if temp:
        f = _maybe_float(temp)
        if f is not None:
            options["temperature"] = f
    else:
        options["temperature"] = 0.2

    if top_p:
        f = _maybe_float(top_p)
        if f is not None:
            options["top_p"] = f

    if repeat_penalty:
        f = _maybe_float(repeat_penalty)
        if f is not None:
            options["repeat_penalty"] = f

    if num_ctx:
        i = _maybe_int(num_ctx)
        if i is not None:
            options["num_ctx"] = i

    if num_predict:
        i = _maybe_int(num_predict)
        if i is not None:
            options["num_predict"] = i

    return options


def _ollama_generate(prompt: str, timeout: int = 180) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": _ollama_options_from_env(),
    }
    response = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return (data.get("response") or "").strip()


def _build_summary_prompt(text: str, focus: str, max_bullets: int) -> str:
    """
    Prompt tuned for consistent bullet output (no preamble, no markdown headers).
    """
    # Keep it short by default; allow fewer bullets for thin content.
    min_bullets = 2 if max_bullets <= 3 else 3
    return (
        "You are a concise newsletter editor.\n"
        "Task: write a factual summary from the provided content.\n"
        f"Output requirements:\n"
        f"- Write between {min_bullets} and {max_bullets} bullet points depending on content density\n"
        f"- Never exceed {max_bullets} bullets\n"
        "- Each bullet must start with '- '\n"
        "- No intro sentences, no headings, no 'Here are...' preambles\n"
        "- No links, no citations, no markdown formatting beyond the leading '- '\n"
        "- Prefer concrete nouns (people/orgs/models), numbers, and outcomes if present\n"
        "- Keep bullets short (aim <= 20 words each)\n"
        "- If the content is unclear, write the most defensible high-level bullets without guessing\n"
        f"\nContext: {focus}\n"
        "\nContent:\n"
        f"{text}\n"
    )


def summarize_with_ollama(text: str, focus: str, bullet_count: int) -> str:
    # `bullet_count` is treated as a maximum; the model may output fewer bullets if content is thin.
    max_bullets = max(1, int(bullet_count))
    # For long transcripts, do a simple 2-pass summarize to stay within context.
    max_input_chars = int(os.getenv("OLLAMA_MAX_INPUT_CHARS", "20000"))
    text = (text or "").strip()
    if not text:
        return ""

    try:
        if len(text) <= max_input_chars:
            prompt = _build_summary_prompt(text, focus, max_bullets)
            raw = _ollama_generate(prompt)
            bullets = _extract_bullets(raw)
            if not bullets:
                return _fallback_bullets(text, max_bullets)
            return "\n".join(bullets[:max_bullets]).strip()

        # Pass 1: chunk -> short bullets per chunk
        chunk_size = max_input_chars
        overlap = 500
        chunk_bullets = max(2, min(3, max_bullets))
        interim_parts: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            chunk = text[start:end]
            prompt = _build_summary_prompt(chunk, f"{focus} (partial)", chunk_bullets)
            interim_parts.append(_ollama_generate(prompt))
            if end >= len(text):
                break
            start = max(0, end - overlap)

        # Pass 2: combine -> final bullets
        combined = "\n".join(interim_parts)
        prompt = _build_summary_prompt(combined, f"{focus} (combined)", max_bullets)
        raw = _ollama_generate(prompt)
        bullets = _extract_bullets(raw)
        if not bullets:
            return _fallback_bullets(text, max_bullets)
        return "\n".join(bullets[:max_bullets]).strip()
    except requests.RequestException:
        return _fallback_bullets(text, max_bullets)
    except ValueError:
        return _fallback_bullets(text, max_bullets)
