import os

import openai


def _tracing_enabled() -> bool:
    """True if either the legacy LANGCHAIN_TRACING_V2 or newer LANGSMITH_TRACING is set."""
    return (
        os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
        or os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
    )


def _maybe_wrap(client: openai.OpenAI) -> openai.OpenAI:
    """Wrap the OpenAI client with LangSmith tracing when enabled.

    Uses langsmith.wrappers.wrap_openai which patches chat.completions.create
    in-place so all LLM calls appear as traced spans — no call-site changes needed.
    """
    if _tracing_enabled():
        try:
            from langsmith.wrappers import wrap_openai
            return wrap_openai(client)
        except ImportError:
            pass
    return client


def get_discovery_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for the discovery node."""
    client = openai.OpenAI(
        base_url=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
    )
    deployment = os.environ.get("AZURE_DEPLOYMENT_DISCOVERY", "gpt-4.1")
    return _maybe_wrap(client), deployment


def _profiler_client() -> openai.OpenAI:
    return openai.OpenAI(
        base_url=os.environ["AZURE_OPENAI_PROFILER_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_PROFILER_KEY"],
    )


def get_profiler_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for the profiler node."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_PROFILER", "gpt-5.4")
    return _maybe_wrap(_profiler_client()), deployment


def get_synth_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for the synthesis node."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_SYNTH", "gpt-5.4")
    return _maybe_wrap(_profiler_client()), deployment


def get_writer_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for section writers and compiler."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_WRITER", "gpt-5.4")
    return _maybe_wrap(_profiler_client()), deployment


def get_lead_researcher_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for the Lead Researcher planning node."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_LEAD", "gpt-5")
    return _maybe_wrap(_profiler_client()), deployment


def get_subagent_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for section sub-agents (Phase B)."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_SUBAGENT", "gpt-4.1")
    return _maybe_wrap(_profiler_client()), deployment


def get_extraction_llm() -> tuple[openai.OpenAI, str]:
    """Returns (OpenAI client, deployment name) for evidence extraction (Phase B)."""
    deployment = os.environ.get("AZURE_DEPLOYMENT_EXTRACTION", "gpt-4.1-mini")
    return _maybe_wrap(_profiler_client()), deployment
