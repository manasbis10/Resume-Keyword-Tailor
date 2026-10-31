import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import NotFoundError, RateLimitError

from app import rewrite

SOURCE = "Jane Doe jane@example.com Software Engineer Acme 2021-2024 Built Python APIs and reduced latency by 25%. Skills: Python, SQL"


def test_markdown_json():
    assert rewrite._parse_json('```json\n{"name": "Jane"}\n```') == {"name": "Jane"}
    with pytest.raises(ValueError):
        rewrite._parse_json("Sorry I cannot do that")


def test_grounding_rejects_new_facts(tailored):
    rewrite._validate_grounding(tailored, SOURCE)
    tailored.experience[0].company = "Invented Corporation"
    with pytest.raises(ValueError, match="identity"):
        rewrite._validate_grounding(tailored, SOURCE)


def test_grounding_rejects_new_metrics(tailored):
    tailored.experience[0].bullets = ["Improved latency by 90%"]
    with pytest.raises(ValueError, match="number"):
        rewrite._validate_grounding(tailored, SOURCE)


def test_empty_output_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        rewrite._validate_grounding(rewrite.TailoredResume(), SOURCE)


def completion(tailored, finish_reason="stop"):
    return SimpleNamespace(model="test-model", choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=tailored.model_dump_json()))])


def test_model_fallback_and_client_cleanup(monkeypatch, tailored):
    monkeypatch.setenv("OPENROUTER_MODEL", "preferred:free")
    client = Mock()
    client.chat.completions.create.side_effect = [NotFoundError("gone", response=httpx.Response(404, request=httpx.Request("POST", "https://example.com")), body=None), completion(tailored)]
    monkeypatch.setattr(rewrite, "_client", lambda: client)
    result = rewrite.tailor_resume(SOURCE, "Python engineer")
    assert result.model_used == "test-model"
    assert [call.kwargs["model"] for call in client.chat.completions.create.call_args_list] == ["preferred:free", "openrouter/free"]
    request = client.chat.completions.create.call_args.kwargs
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"]["reasoning"]["effort"] == "low"
    client.close.assert_called_once()


def test_truncated_output_rejected(monkeypatch, tailored):
    client = Mock()
    client.chat.completions.create.return_value = completion(tailored, "length")
    monkeypatch.setattr(rewrite, "_client", lambda: client)
    with pytest.raises(ValueError, match="finish"):
        rewrite.tailor_resume(SOURCE, "Python engineer")
    client.close.assert_called_once()


def test_rate_limit_not_retried(monkeypatch):
    client = Mock()
    client.chat.completions.create.side_effect = RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "https://example.com")), body=None)
    monkeypatch.setattr(rewrite, "_client", lambda: client)
    with pytest.raises(RateLimitError):
        rewrite.tailor_resume(SOURCE, "Python engineer")
    client.chat.completions.create.assert_called_once()
    client.close.assert_called_once()
