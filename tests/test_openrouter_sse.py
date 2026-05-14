"""Unit tests for OpenRouter SSE delta parsing (hub streaming)."""

import json

from forager_ai.ai.openrouter_client import sse_delta_content_chunks


def test_sse_done_empty():
    assert sse_delta_content_chunks(line="data: [DONE]") == []


def test_sse_content_string():
    payload = {"choices": [{"delta": {"content": "Hello"}}]}
    line = "data: " + json.dumps(payload)
    assert sse_delta_content_chunks(line=line) == ["Hello"]


def test_sse_ignores_ping():
    assert sse_delta_content_chunks(line=": ping") == []
    assert sse_delta_content_chunks(line="") == []


def test_sse_malformed():
    assert sse_delta_content_chunks(line="data: {broken") == []


def test_sse_content_parts_string_list():
    payload = {"choices": [{"delta": {"content_parts": ["Hel", "lo"]}}]}
    line = "data: " + json.dumps(payload)
    assert sse_delta_content_chunks(line=line) == ["Hel", "lo"]


def test_sse_content_parts_dict_with_text():
    payload = {"choices": [{"delta": {"content_parts": [{"text": "ok"}]}}]}
    line = "data: " + json.dumps(payload)
    assert sse_delta_content_chunks(line=line) == ["ok"]


def test_sse_uses_first_choice_only():
    payload = {"choices": [{"delta": {"content": "A"}}, {"delta": {"content": "B"}}]}
    line = "data: " + json.dumps(payload)
    assert sse_delta_content_chunks(line=line) == ["A"]


def test_sse_missing_delta_or_content():
    assert sse_delta_content_chunks(line="data: " + json.dumps({"choices": [{}]})) == []
    assert sse_delta_content_chunks(line="data: " + json.dumps({"choices": [{"delta": {}}]})) == []
