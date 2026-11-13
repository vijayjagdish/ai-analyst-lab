"""Talking to the language model - always through the Bifrost gateway.

You never hold a real provider key. Your `OPENAI_API_KEY` is a *virtual* key
(`sk-bf-...`) that only works against the gateway, which adds the real
credential, enforces your budget and rate limit, and records what you spent.

The gateway speaks the OpenAI chat-completions protocol, so the ordinary
`openai` SDK works against it - you only point `base_url` somewhere else. The
model name carries the provider as a prefix, for example
`anthropic/claude-opus-5-5` or `bedrock/mistral-large`.

Two things in here:

    chat()         one plain question, one answer            <- Milestone 2 (you)
    build_model()  the model object the Strands agent uses   <- provided
"""

from __future__ import annotations

from .config import get_settings


def chat(prompt: str, system: str | None = None, max_tokens: int = 1024) -> str:
    """Send one prompt to the model through the gateway and return the reply text.

    Args:
        prompt: the user's message.
        system: optional system prompt.
        max_tokens: upper bound on the length of the reply.
    """
    settings = get_settings()
    settings.require("gateway_url", "api_key")

    # >>> TODO M2-1 ─────────────────────────────────────────────────────────
    # Make ONE chat-completions call and return the text of the reply.
    #
    #   1. Create an OpenAI client with api_key=settings.api_key and
    #      base_url=settings.gateway_url.
    #   2. Build `messages`: an optional {"role": "system", ...} entry first,
    #      then {"role": "user", "content": prompt}.
    #   3. Call client.chat.completions.create(model=settings.model,
    #      messages=..., max_tokens=max_tokens).
    #   4. Return response.choices[0].message.content (or "" if it is None).
    #
    # Do NOT pass `temperature`. The current Claude models reject sampling
    # parameters, and a request that works on one model then fails on another
    # is a miserable thing to debug.
    # >>> SOLUTION
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key, base_url=settings.gateway_url,
                    timeout=settings.http_timeout_s * 6)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=settings.model, messages=messages, max_tokens=max_tokens)
    return response.choices[0].message.content or ""
    # <<< END TODO


def build_model():
    """The model object handed to the Strands `Agent`.  (PROVIDED)

    Strands' OpenAIModel is a thin adapter: it turns the agent's messages and
    tool definitions into a chat-completions request and the streamed reply back
    into text and tool calls. Because Bifrost is OpenAI-compatible, the same
    adapter reaches every model behind the gateway.

    Why there is no `temperature` here either: see chat(). If you need to pass
    an extra request field for an experiment, set LLM_EXTRA_PARAMS in .env to a
    JSON object rather than editing this function.
    """
    from strands.models.openai import OpenAIModel

    settings = get_settings()
    settings.require("gateway_url", "api_key")
    params = {"max_tokens": settings.max_tokens, **settings.extra_params}
    return OpenAIModel(
        client_args={
            "api_key": settings.api_key,
            "base_url": settings.gateway_url,
            "timeout": settings.http_timeout_s * 15,   # agent turns can be slow; 5 minutes
        },
        model_id=settings.model,
        params=params,
        stream=settings.stream,
    )
