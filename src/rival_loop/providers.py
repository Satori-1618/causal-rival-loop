"""Tool-free, stateless generator calls and a clearly labelled engineering fake.

No call is made on import. API prices are operator-supplied frozen assumptions;
there is no automatic model selection, key discovery, or request retry.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request


class FatalProviderError(RuntimeError):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


def validate_live_settings(settings):
    allowed = {"provider", "model", "model_revision", "max_input_tokens", "max_output_tokens",
               "temperature", "reasoning_effort", "timeout_seconds", "run_timeout_seconds",
               "max_cost_usd", "input_usd_per_million", "output_usd_per_million",
               "tokenizer_encoding", "max_calls_per_case", "max_total_calls", "retry_calls"}
    if set(settings) - allowed:
        raise ValueError("unknown generation settings; credentials must stay in environment")
    required = ("model", "model_revision", "max_input_tokens", "max_output_tokens",
                "timeout_seconds", "run_timeout_seconds", "max_cost_usd",
                "input_usd_per_million", "output_usd_per_million", "tokenizer_encoding")
    if settings.get("provider") != "openai_responses":
        raise ValueError("live provider must explicitly be openai_responses")
    missing = [name for name in required if settings.get(name) is None]
    if missing:
        raise ValueError(f"live configuration pending: {', '.join(missing)}")
    for name in ("model", "model_revision", "tokenizer_encoding"):
        if not isinstance(settings[name], str) or not settings[name].strip():
            raise ValueError(f"invalid {name}")
    for name in required[2:-1]:
        value = settings[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("max_input_tokens", "max_output_tokens"):
        if int(settings[name]) != settings[name]:
            raise ValueError(f"{name} must be an integer")
    if settings["max_output_tokens"] < 16:
        raise ValueError("max_output_tokens must be at least 16")
    temperature = settings.get("temperature")
    if temperature is not None and (type(temperature) not in (int, float)
            or not math.isfinite(temperature) or not 0 <= temperature <= 2):
        raise ValueError("invalid temperature")
    if settings.get("reasoning_effort") is not None and (not isinstance(settings["reasoning_effort"], str)
            or not settings["reasoning_effort"].strip()):
        raise ValueError("reasoning_effort must be a declared string or null")
    if any(settings.get(k) != v for k, v in
           (("max_calls_per_case", 3), ("max_total_calls", 144), ("retry_calls", 0))):
        raise ValueError("generation call budget is fixed")
    return settings


def call_reservation(settings):
    return (settings["max_input_tokens"] * settings["input_usd_per_million"]
            + settings["max_output_tokens"] * settings["output_usd_per_million"]) / 1_000_000


class FakeProvider:
    """Fixed authored responses, never an empirical LLM or an oracle generator."""
    model = "engineering-fake-v1"
    live = False

    def generate(self, prompt, settings):
        rule = {"op": "avg", "left": {"var": "a"}, "right": {"var": "b"}}
        return {"status": "ok", "model": self.model, "provider": "fake",
                "raw": json.dumps({"rules": [{"id": "authored_average",
                    "mechanism": "Authored fixture; no empirical generation claim.", "readout": rule}]}),
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "cost_usd": 0.0, "cost_reserved_usd": 0.0}


class OpenAIProvider:
    live = True

    def __init__(self, settings):
        self.settings = validate_live_settings(settings)
        import tiktoken
        self.encoding = tiktoken.get_encoding(settings["tokenizer_encoding"])
        self.model = settings["model_revision"]

    def generate(self, prompt, settings):
        instruction = "Return only the requested JSON. No tools or external resources are available."
        # Framing allowance is explicit; authoritative server counts are checked too.
        estimated_input = len(self.encoding.encode(instruction + prompt)) + 128
        if estimated_input > settings["max_input_tokens"]:
            return {"status": "input_limit", "model": self.model, "provider": "openai_responses",
                    "raw": "", "usage": None, "cost_usd": 0.0, "cost_reserved_usd": 0.0}
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise FatalProviderError("OPENAI_API_KEY is not set; no request attempted")
        payload = {"model": self.model, "instructions": instruction, "input": prompt,
                   "max_output_tokens": settings["max_output_tokens"], "store": False,
                   "tools": [], "tool_choice": "none", "truncation": "disabled"}
        if settings.get("temperature") is not None:
            payload["temperature"] = settings["temperature"]
        if settings.get("reasoning_effort") is not None:
            payload["reasoning"] = {"effort": settings["reasoning_effort"]}
        request = urllib.request.Request("https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        started = time.monotonic()
        reservation = call_reservation(settings)
        try:
            with urllib.request.urlopen(request, timeout=settings["timeout_seconds"]) as response:
                result = json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # A timeout may still be billable: reserve the full configured maximum.
            return {"status": "transport_failure", "model": self.model,
                    "provider": "openai_responses", "raw": "", "usage": None,
                    "reason": type(error).__name__, "cost_usd": None,
                    "cost_reserved_usd": reservation, "elapsed_seconds": time.monotonic() - started}
        usage = result.get("usage")
        raw = "".join(item.get("text", "") for output in result.get("output", [])
                      if output.get("type") == "message" for item in output.get("content", [])
                      if item.get("type") == "output_text")
        status = "ok" if result.get("status") == "completed" else "incomplete_response"
        if result.get("model") != self.model:
            raise FatalProviderError("response model differs from frozen model revision", result)
        if not isinstance(usage, dict) or any(not isinstance(usage.get(k), int) or usage[k] < 0
                                             for k in ("input_tokens", "output_tokens")):
            raise FatalProviderError("missing authoritative usage; budget cannot be checked", result)
        if usage["input_tokens"] > settings["max_input_tokens"] or usage["output_tokens"] > settings["max_output_tokens"]:
            raise FatalProviderError("authoritative token count exceeded frozen ceiling", result)
        cost = (usage["input_tokens"] * settings["input_usd_per_million"]
                + usage["output_tokens"] * settings["output_usd_per_million"]) / 1_000_000
        return {"status": status, "provider": "openai_responses", "model": self.model,
                "raw": raw, "response_id": result.get("id"), "usage": usage,
                "cost_usd": cost, "cost_reserved_usd": reservation,
                "elapsed_seconds": time.monotonic() - started}
