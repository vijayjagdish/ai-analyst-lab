"""The agent: a model, a system prompt and a set of tools, run in a loop.

That loop is the whole idea of an agent, and Strands runs it for you:

    1. send the conversation and the tool descriptions to the model
    2. the model replies with text, or asks for one or more tools
    3. run the tools it asked for, append their results to the conversation
    4. go to 1 - until the model replies with text only

You supply the three ingredients (build_agent) and decide what comes back to
the caller (ask). Notice what ask() does NOT do: it never parses the model's
prose to find out which query ran. It takes the answer text from the model and
the evidence from the tools' own record.
"""

from __future__ import annotations

import time

from services.config import get_settings
from services.llm_client import build_model

from .evidence import EVIDENCE, AgentAnswer
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS


def build_agent(model=None):
    """Create the agent.

    Args:
        model: a Strands model object. Leave it as None to use the gateway model
            from services.llm_client.build_model(); the tests pass a scripted
            fake here so the agent can be exercised without spending a token.

    Returns:
        A strands.Agent ready to be called with a question.
    """
    # TODO M6-4 ─────────────────────────────────────────────────────────
    # Return strands.Agent(...) built from:
    #     model          = model, or build_model() when model is None
    #     system_prompt  = SYSTEM_PROMPT
    #     tools          = ALL_TOOLS
    #     callback_handler = None
    #
    # callback_handler=None switches off Strands' default behaviour of printing
    # every token and tool call as it happens. You want that off in tests and
    # in the evaluation run; while exploring in a notebook, leave the argument
    # out to watch the agent think.
    raise NotImplementedError("TODO M6-4 (agent/agent.py)")


def ask(question: str, model=None) -> AgentAnswer:
    """Answer one question and return the answer together with its evidence.

    A NEW agent is built for every question, so nothing said in one question
    leaks into the next - each answer stands on its own evidence.

    Args:
        question: the user's question in plain language.
        model: optional Strands model object (see build_agent).

    Returns:
        An AgentAnswer: the answer text, the evidence the tools recorded, the
        tools used in order, and how much the run cost.
    """
    settings = get_settings()

    # TODO M6-5 ─────────────────────────────────────────────────────────
    #   1. agent = build_agent(model)
    #   2. EVIDENCE.reset()        - start this question with an empty record
    #   3. Time the call:  started = time.perf_counter()
    #        result = agent(question, limits={"turns": settings.agent_max_turns})
    #      `limits` is the circuit breaker. A model that keeps calling tools and
    #      never answers would otherwise loop until your budget is gone.
    #   4. Build and return the AgentAnswer:
    #        answer       str(result).strip()
    #                     If it is empty (the turn limit was hit before the
    #                     model answered), put a sentence saying so - an empty
    #                     answer looks like a crash to whoever reads it.
    #        evidence     EVIDENCE.snapshot()
    #        tools_used   EVIDENCE.tools_used()
    #        model        agent.model.get_config().get("model_id", "")
    #        stop_reason  str(result.stop_reason)
    #        turns        result.metrics.cycle_count
    #        usage        from result.metrics.accumulated_usage - keys
    #                     inputTokens / outputTokens / totalTokens - stored as
    #                     input_tokens / output_tokens / total_tokens
    #        latency_s    seconds, rounded to 2 decimals
    raise NotImplementedError("TODO M6-5 (agent/agent.py)")
