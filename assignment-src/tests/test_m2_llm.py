"""Milestone 2 - your first call to the model through the gateway.        ./check.sh 2

Code under test: services/llm_client.py -> chat()

These tests call the real model, so they spend a little of your budget (a few
hundred tokens in total).
"""

from __future__ import annotations

import pytest

from services.llm_client import chat

pytestmark = pytest.mark.live


def test_chat_returns_the_models_reply(gateway):
    reply = chat("Reply with exactly this word and nothing else: pineapple")
    assert isinstance(reply, str), f"chat() must return a string, got {type(reply).__name__}"
    assert "pineapple" in reply.lower(), (
        f"asked the model to say 'pineapple', chat() returned {reply[:120]!r}. "
        "Return response.choices[0].message.content.")


def test_chat_passes_the_system_prompt(gateway):
    reply = chat("What is your name?",
                 system="Your name is Meridian. When asked your name, answer with that name only.")
    assert "meridian" in reply.lower(), (
        f"the system prompt named the assistant Meridian, but chat() returned {reply[:120]!r}. "
        "The system message must go FIRST in the messages list, with role 'system'.")
