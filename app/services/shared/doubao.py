"""Shared client for calling Doubao's chat completions API.

This module centralises the logic for talking to the Doubao chat API. It
loads the API key, model name and endpoint from a `.env.doubao` file in the
project root using python‑dotenv. You can reuse the exported `chat`
function in multiple services (e.g. scoring and WeCom webhook) to
generate natural language replies.

Note: The environment variables used are:

* `DOUBAO_API_KEY` – your secret API key provided by Doubao.
* `DOUBAO_MODEL` – the model identifier (e.g. `doubao-seed-1-6-250615`).
* `DOUBAO_ENDPOINT` – the full URL to the chat completions endpoint.

If a request fails or returns an unexpected structure, the `chat`
function will raise an exception, which callers should catch and handle
appropriately (for example by falling back to a static response).
"""

from __future__ import annotations

import json
import os
from typing import Iterable, List, Mapping

import requests
from dotenv import load_dotenv

# Load credentials from `.env.doubao` relative to project root. If this file
# doesn't exist, load_dotenv simply does nothing.
load_dotenv(".env.doubao")


def _get_doubao_config() -> tuple[str, str, str]:
    """Read Doubao configuration from environment variables.

    Returns a tuple of (api_key, model_name, endpoint). Raises
    ValueError if any of these are missing.
    """
    api_key = os.getenv("DOUBAO_API_KEY")
    model_name = os.getenv("DOUBAO_MODEL")
    endpoint = os.getenv("DOUBAO_ENDPOINT")
    if not api_key or not model_name or not endpoint:
        raise ValueError(
            "DOUBAO_API_KEY, DOUBAO_MODEL and DOUBAO_ENDPOINT must be set in .env.doubao"
        )
    return api_key, model_name, endpoint


def chat(
    messages: Iterable[Mapping[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 512,
    stop: Iterable[str] | None = None,
) -> str:
    """Send a chat completion request to Doubao and return the assistant's reply.

    Parameters
    ----------
    messages : iterable of dict
        The conversation history formatted as a list of message dicts with
        roles ("system", "user" or "assistant") and content. This will be
        passed directly to Doubao's API.
    temperature : float, optional
        The randomness temperature. Lower values make the output more
        deterministic. Defaults to 0.3.
    max_tokens : int, optional
        Maximum number of tokens in the generated reply. Defaults to 512.
    stop : iterable of str, optional
        Optional stop sequence(s). If provided, they will be passed to
        Doubao.

    Returns
    -------
    str
        The assistant's reply content.

    Raises
    ------
    Exception
        If the HTTP request fails or the response payload is malformed.
    """
    api_key, model_name, endpoint = _get_doubao_config()
    headers = {
        "Content-Type": "application/json",
        # Doubao follows a similar authorization scheme to OpenAI: Bearer + API key
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, object] = {
        "model": model_name,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if stop:
        # Doubao may accept a single string or list of strings for stop sequences.
        payload["stop"] = stop
    response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    # The structure is expected to follow OpenAI's pattern: {"choices":[{"message":{"content":...}}]}
    try:
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception as exc:  # noqa: BLE001
        raise Exception(f"Unexpected Doubao response structure: {data}") from exc