import os
import requests


def summarize_content(text: str, focus: str, bullet_count: int = 3) -> str:
    use_crewai = os.getenv("USE_CREWAI", "").lower() in {"1", "true", "yes"}
    if use_crewai:
        try:
            return summarize_with_crewai(text, focus, bullet_count)
        except Exception:
            # Fall back to Ollama if CrewAI fails
            pass
    return summarize_with_ollama(text, focus, bullet_count)


def summarize_with_crewai(text: str, focus: str, bullet_count: int) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for CrewAI summarization.")

    from crewai import Agent, Task, Crew

    agent = Agent(
        role="Summarizer",
        goal="Summarize content into exactly 3 crisp bullet points.",
        backstory="You create concise summaries for busy readers.",
        allow_delegation=False,
        verbose=False,
    )

    task = Task(
        description=(
            f"Summarize the following content into EXACTLY {bullet_count} bullet points. "
            "Each bullet should be a short, crisp sentence. "
            f"Context: {focus}.\n\nContent:\n{text}"
        ),
        expected_output=f"Exactly {bullet_count} bullet points, each starting with '-'",
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=False)
    result = crew.kickoff()

    if hasattr(result, "tasks_output") and result.tasks_output:
        return result.tasks_output[-1].raw.strip()
    return str(result).strip()


def summarize_with_ollama(text: str, focus: str, bullet_count: int) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    prompt = (
        f"Summarize the following content into EXACTLY {bullet_count} bullet points. "
        "Each bullet should be a short, crisp sentence. "
        "Focus on key developments, names, and capabilities if present. "
        f"Context: {focus}.\n\n"
        f"Content:\n{text}\n\n"
        "Return ONLY bullet points, each starting with '-'"
    )

    payload = {"model": model, "prompt": prompt, "stream": False}
    response = requests.post(f"{base_url}/api/generate", json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()
