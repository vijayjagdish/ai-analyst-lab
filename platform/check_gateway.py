#!/usr/bin/env python3
"""Check what a gateway key can really do - before a student finds out the hard way.

    python check_gateway.py --url https://ai-gateway.eks.dev.cream-collar.com --model claude-opus-5-5-bedrock
    python check_gateway.py --url ... --model claude-opus-5-5-bedrock --model gemma

For every model it runs the two things the assignment needs:

    chat    one plain question, one answer                       (Milestone 2)
    tools   the model asks for a tool, gets the result, answers  (everything the agent does)

and, on a LiteLLM gateway, it also shows the key's settings and its OWNER's settings.
LiteLLM checks both: a key whose own model list includes a model is still refused
if the user who owns the key may not use it. That is the usual cause of
"403 ... User not allowed to access model".

The key is never taken from the command line (it would land in shell history) and
never printed. It comes from, in order: --key-file, the GATEWAY_KEY environment
variable, or a hidden prompt.

Works against any OpenAI-compatible gateway (LiteLLM, Bifrost). Standard library
only: any machine with Python 3.8+, nothing to install.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

TOOL = {
    "type": "function",
    "function": {
        "name": "add_numbers",
        "description": "Add two whole numbers and return their sum.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "the first number"},
                "b": {"type": "integer", "description": "the second number"},
            },
            "required": ["a", "b"],
        },
    },
}

# (text found in an error, lower case) -> what it means and what to do
HINTS = [
    ("no default model access",
     "LiteLLM refused because the key's OWNER (a user) is set to 'No Default Models' and the key is "
     "not in a team. Fix in the LiteLLM UI: Internal Users -> that user -> Edit -> Models: remove "
     "'No Default Models' and add the model. Or put the key in a team whose Models include it."),
    ("team not allowed",
     "The key's team does not include this model. LiteLLM UI: Teams -> the team -> Models."),
    ("not allowed to access model",
     "The model is not in an allowed list (the key's, its owner's or its team's)."),
    ("invalid_payment_instrument",
     "AWS Marketplace billing block on the AWS account (the AISPL issue). Not fixable in the gateway."),
    ("temperature",
     "The gateway's settings for this model send a sampling parameter the model rejects. Remove "
     "temperature / top_p from that model's settings in the gateway."),
    ("top_p",
     "The gateway's settings for this model send a sampling parameter the model rejects. Remove "
     "temperature / top_p from that model's settings in the gateway."),
    ("thinking",
     "A problem with the model's reasoning blocks in a multi-step tool call through the gateway. "
     "Send this message to whoever runs the gateway."),
    ("budget",
     "The key, its owner or its team has used up its budget."),
    ("rate limit",
     "Rate limit reached. Wait a minute and run again."),
    ("invalid model",
     "No model with this exact name on the gateway. Use a name from the model list above."),
    ("does not exist",
     "No model with this exact name on the gateway. Use a name from the model list above."),
]


def mask(key: str) -> str:
    return f"{key[:3]}...{key[-4:]}" if len(key) > 10 else "(set)"


def request(method: str, url: str, key: str, body: dict | None = None, timeout: int = 120):
    """Return (status or None, parsed JSON or {'raw': text}). Never raises for HTTP errors."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "ai-analyst-lab-check-gateway/1")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _parse(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"error": {"message": f"could not reach {url}: {getattr(exc, 'reason', exc)}"}}


def _parse(raw: bytes):
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text[:500]}


def error_text(payload) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
        if "detail" in payload:
            return str(payload["detail"])
        if "raw" in payload:
            return payload["raw"]
    return str(payload)[:500]


def hint_for(status, message: str) -> str | None:
    lowered = message.lower()
    for needle, hint in HINTS:
        if needle in lowered:
            return hint
    if status == 401:
        return "The gateway does not accept this key: wrong, expired or blocked."
    if status == 429:
        return "Rate limit or budget reached."
    return None


def check_chat(base: str, key: str, model: str):
    status, payload = request("POST", f"{base}/v1/chat/completions", key, {
        "model": model, "max_tokens": 512,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
    })
    if status != 200:
        return False, f"HTTP {status}: {error_text(payload)}", status
    try:
        text = (payload["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        return False, f"unexpected reply: {str(payload)[:200]}", status
    return (bool(text), f"replied {text[:60]!r}" if text else "empty reply", status)


def check_tools(base: str, key: str, model: str):
    """Two turns, exactly as an agent framework does them: ask -> tool call -> result -> answer."""
    messages = [
        {"role": "system", "content": "You are a calculator. Always use the add_numbers tool to add."},
        {"role": "user", "content": "Use the add_numbers tool to add 17 and 25, then tell me the result."},
    ]
    body = {"model": model, "max_tokens": 1024, "messages": messages, "tools": [TOOL]}
    status, payload = request("POST", f"{base}/v1/chat/completions", key, body)
    if status != 200:
        return False, f"turn 1: HTTP {status}: {error_text(payload)}", status
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return False, f"turn 1: unexpected reply: {str(payload)[:200]}", status
    calls = message.get("tool_calls") or []
    if not calls:
        said = (message.get("content") or "").strip()[:80]
        return (False, "the model answered WITHOUT calling the tool - it does not do tool calling "
                       f"through this gateway (it said {said!r})", status)

    # Send back what an agent framework sends: role, content, tool_calls. Nothing else.
    messages.append({
        "role": "assistant",
        "content": message.get("content"),
        "tool_calls": [{"id": c["id"], "type": "function",
                        "function": {"name": c["function"]["name"],
                                     "arguments": c["function"].get("arguments") or "{}"}}
                       for c in calls],
    })
    asked = []
    for call in calls:
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
            result = {"sum": int(args.get("a", 0)) + int(args.get("b", 0))}
            asked.append(f"{call['function']['name']}({args.get('a')}, {args.get('b')})")
        except (ValueError, TypeError):
            result = {"error": "arguments were not two numbers"}
            asked.append(f"{call['function']['name']}(unreadable arguments)")
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})

    body = {"model": model, "max_tokens": 1024, "messages": messages, "tools": [TOOL]}
    status, payload = request("POST", f"{base}/v1/chat/completions", key, body)
    if status != 200:
        return False, f"turn 2 (after sending the tool result): HTTP {status}: {error_text(payload)}", status
    try:
        final = (payload["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        return False, f"turn 2: unexpected reply: {str(payload)[:200]}", status
    if "42" in final:
        return True, f"called {', '.join(asked)} and answered 42", status
    return False, f"called {', '.join(asked)} but the final answer has no 42: {final[:80]!r}", status


def read_key(args) -> str:
    if args.key_file:
        with open(args.key_file, encoding="utf-8") as handle:
            key = handle.readline().strip()
    elif os.environ.get("GATEWAY_KEY", "").strip():
        key = os.environ["GATEWAY_KEY"].strip()
    elif sys.stdin.isatty():
        key = getpass.getpass("Gateway key (typing is hidden): ").strip()
    else:
        raise SystemExit("no key: use --key-file, set GATEWAY_KEY, or run in a terminal to be prompted")
    if not key:
        raise SystemExit("the key is empty")
    return key


def show_litellm_access(base: str, key: str) -> None:
    """LiteLLM only: who owns the key, and what the key, its owner and its team may use."""
    status, payload = request("GET", f"{base}/key/info", key, timeout=30)
    if status != 200 or not isinstance(payload, dict) or "info" not in payload:
        print("  (no LiteLLM key information - not a LiteLLM gateway, or not visible to this key)")
        return
    info = payload["info"] or {}
    user_id, team_id = info.get("user_id"), info.get("team_id")
    print(f"  key alias     : {info.get('key_alias') or '-'}")
    print(f"  key models    : {info.get('models') or 'all the owner may use'}")
    print(f"  key team      : {team_id or 'none (a personal key)'}")
    print(f"  key owner     : {user_id or '-'}")
    budget = info.get("max_budget")
    print(f"  key spend     : {info.get('spend', 0)} of {budget if budget is not None else 'no limit'}")
    if info.get("expires"):
        print(f"  key expires   : {info['expires']}")
    if info.get("blocked"):
        print("  KEY IS BLOCKED")

    if not user_id:
        return
    status, payload = request("GET", f"{base}/user/info?user_id={quote(str(user_id))}", key, timeout=30)
    if status != 200 or not isinstance(payload, dict):
        print(f"  owner models  : (not visible with this key - HTTP {status})")
        return
    user = payload.get("user_info") or {}
    models = user.get("models")
    teams = [t.get("team_alias") or t.get("team_id") for t in (payload.get("teams") or []) if isinstance(t, dict)]
    print(f"  owner models  : {models if models else 'all proxy models'}")
    print(f"  owner teams   : {teams or 'none'}")
    if models and "no-default-models" in models and not team_id:
        print("  >> The owner is set to 'No Default Models' and this key is not in a team, so LiteLLM")
        print("     will refuse EVERY model for this key. Fix: Internal Users -> this user -> Edit ->")
        print("     Models: remove 'No Default Models' and add the models. Or create the key in a team.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check what a gateway key can really do.")
    parser.add_argument("--url", required=True,
                        help="gateway address, with or without /v1, e.g. https://ai-gateway.eks.dev.cream-collar.com")
    parser.add_argument("--model", action="append", required=True,
                        help="model name exactly as the gateway calls it; repeat for several")
    parser.add_argument("--key-file", help="file whose first line is the key")
    args = parser.parse_args()

    base = args.url.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    key = read_key(args)

    print(f"Gateway : {base}")
    print(f"Key     : {mask(key)}")

    status, payload = request("GET", f"{base}/v1/models", key, timeout=30)
    if status is None:
        print(f"\nCould not reach the gateway: {error_text(payload)}")
        print("  -> Check the URL, and that this machine can reach it (VPN, proxy, firewall).")
        return 1
    if status != 200:
        message = error_text(payload)
        print(f"\nThe gateway did not accept the key: HTTP {status}: {message}")
        hint = hint_for(status, message)
        if hint:
            print(f"  -> {hint}")
        return 1
    names = sorted(m.get("id", "?") for m in payload.get("data", []) if isinstance(m, dict))
    print(f"Models this key can see: {', '.join(names) or '(none)'}")

    print("\nAccess settings:")
    show_litellm_access(base, key)

    all_ok = True
    for model in args.model:
        print(f"\n=== {model} ===")
        if names and model not in names:
            print(f"  note: {model!r} is not in the key's model list above")
        for label, check in (("chat ", check_chat), ("tools", check_tools)):
            ok, detail, status = check(base, key, model)
            all_ok &= ok
            print(f"  {label}  {'PASS' if ok else 'FAIL'}  {detail}")
            if not ok:
                hint = hint_for(status, detail)
                if hint:
                    print(f"         -> {hint}")
                if label == "chat " and status in (401, 403, 404):
                    print("  tools  SKIP  (the model cannot be reached at all)")
                    break

    print("\nResult: " + ("every model passed - it will work for the assignment."
                          if all_ok else
                          "at least one check failed - see the lines above. 'tools' must PASS for the agent to work."))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
