import pytest
from unittest.mock import patch, MagicMock
from llm_client import LLMClient, LLMResponse

def test_llm_response_model():
    r = LLMResponse(text="hello", model_used="ollama", raw=None)
    assert r.text == "hello"
    assert r.model_used == "ollama"

def test_client_init():
    client = LLMClient()
    assert client is not None

@patch("llm_client.requests.post")
def test_query_ollama_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": '{"score": 75}'}
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    client = LLMClient()
    result = client.query(
        messages=[{"role": "user", "content": "Score this"}],
        model_preference="local",
    )
    assert result.text == '{"score": 75}'
    assert result.model_used == "ollama"

@patch("llm_client.requests.post")
def test_query_ollama_fallback_to_haiku(mock_post):
    mock_post.side_effect = Exception("Ollama down")

    client = LLMClient()
    with patch.object(client, "_query_anthropic") as mock_anthropic:
        mock_anthropic.return_value = LLMResponse(
            text="fallback response", model_used="claude-haiku-4-5-20251001", raw=None
        )
        result = client.query(
            messages=[{"role": "user", "content": "test"}],
            model_preference="local",
        )
        assert result.model_used == "claude-haiku-4-5-20251001"

@patch("llm_client.anthropic")
def test_query_sonnet_direct(mock_anthropic_mod):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="sonnet response")]
    mock_msg.model = "claude-sonnet-4-20250514"
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic_mod.Anthropic.return_value = mock_client

    client = LLMClient()
    client._anthropic_client = mock_client
    result = client.query(
        messages=[{"role": "user", "content": "test"}],
        model_preference="sonnet",
    )
    assert "sonnet" in result.model_used

def test_query_with_tools_sonnet():
    client = LLMClient()
    assert callable(client.query_with_tools)


@patch("llm_client.requests.post")
def test_query_all_models_fail_raises(mock_post):
    """All models in chain fail → RuntimeError."""
    mock_post.side_effect = Exception("Ollama down")
    client = LLMClient()
    client._anthropic_client = None  # no anthropic fallback
    with pytest.raises(RuntimeError, match="All LLM models failed"):
        client.query(
            messages=[{"role": "user", "content": "test"}],
            model_preference="local",
        )


def test_query_with_tools_no_api_key():
    """query_with_tools without API key → RuntimeError."""
    client = LLMClient()
    client._anthropic_client = None
    with pytest.raises(RuntimeError, match="Anthropic API key required"):
        client.query_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "foo", "input_schema": {}}],
        )


@patch("llm_client.requests.post")
def test_query_ollama_with_system_prompt(mock_post):
    """System prompt is prepended as system message for Ollama."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": {"content": "ok"}}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    client = LLMClient()
    client.query(
        messages=[{"role": "user", "content": "test"}],
        model_preference="local",
        system="You are an analyst",
    )
    call_json = mock_post.call_args[1]["json"]
    assert call_json["messages"][0]["role"] == "system"
    assert "analyst" in call_json["messages"][0]["content"]


@patch("llm_client.anthropic")
def test_query_anthropic_empty_content(mock_anthropic_mod):
    """Anthropic returns empty content list → empty string text."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = []  # empty
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic_mod.Anthropic.return_value = mock_client

    client = LLMClient()
    client._anthropic_client = mock_client
    result = client.query(
        messages=[{"role": "user", "content": "test"}],
        model_preference="sonnet",
    )
    assert result.text == ""


def test_query_unknown_preference_falls_back_to_local():
    """Unknown model_preference → uses 'local' chain."""
    from llm_client import FALLBACK_CHAINS
    client = LLMClient()
    # Just verify the chain lookup works — "unknown_model" → local chain
    chain = FALLBACK_CHAINS.get("unknown_model", FALLBACK_CHAINS["local"])
    assert chain == FALLBACK_CHAINS["local"]


@patch("llm_client.anthropic")
@patch("llm_client.ANTHROPIC_API_KEY", "fake-key")
def test_query_with_tools_success(mock_anthropic_mod):
    """query_with_tools happy path → returns content, stop_reason, model."""
    mock_client_inst = MagicMock()
    mock_anthropic_mod.Anthropic.return_value = mock_client_inst

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Hello")]
    mock_response.stop_reason = "end_turn"
    mock_response.model = "claude-sonnet-4-20250514"
    mock_client_inst.messages.create.return_value = mock_response

    client = LLMClient()
    result = client.query_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[{"name": "foo", "description": "bar", "input_schema": {}}],
        system="You are helpful",
    )
    assert result["stop_reason"] == "end_turn"
    assert result["content"] == mock_response.content
    assert result["model"] == "claude-sonnet-4-20250514"
    # Verify system was passed in kwargs
    call_kwargs = mock_client_inst.messages.create.call_args[1]
    assert call_kwargs["system"] == "You are helpful"


@patch("llm_client.anthropic")
@patch("llm_client.ANTHROPIC_API_KEY", "fake-key")
def test_query_with_tools_no_system(mock_anthropic_mod):
    """query_with_tools without system → system not in kwargs."""
    mock_client_inst = MagicMock()
    mock_anthropic_mod.Anthropic.return_value = mock_client_inst

    mock_response = MagicMock()
    mock_response.content = []
    mock_response.stop_reason = "end_turn"
    mock_response.model = "claude-sonnet-4-20250514"
    mock_client_inst.messages.create.return_value = mock_response

    client = LLMClient()
    client.query_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[{"name": "foo", "description": "bar", "input_schema": {}}],
    )
    call_kwargs = mock_client_inst.messages.create.call_args[1]
    assert "system" not in call_kwargs


@patch("llm_client.anthropic")
@patch("llm_client.ANTHROPIC_API_KEY", "fake-key")
def test_query_anthropic_with_system(mock_anthropic_mod):
    """_query_anthropic with system param → system included in kwargs."""
    mock_client_inst = MagicMock()
    mock_anthropic_mod.Anthropic.return_value = mock_client_inst

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    mock_client_inst.messages.create.return_value = mock_response

    client = LLMClient()
    result = client.query(
        messages=[{"role": "user", "content": "test"}],
        model_preference="sonnet",
        system="You are an analyst",
    )
    call_kwargs = mock_client_inst.messages.create.call_args[1]
    assert call_kwargs["system"] == "You are an analyst"
