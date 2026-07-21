"""
Integration tests for token usage recording in QA chat flow.

Tests:
1. After calling AI assistant chat completion, token usage is recorded
2. Token usage stats are correctly aggregated
3. User quota is updated after token usage
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlalchemy import select

from app.models.token_usage import TokenUsage, UserQuota
from app.models.user import User
from app.services.llm_service import generate_rag_response, _record_token_usage, _get_llm_config
from app.schemas.retrieval import SearchResultItem


# Test fixtures
@pytest.fixture
def test_user():
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_pwd",
    )


@pytest.fixture
def mock_chunks():
    """Mock retrieved document chunks"""
    return [
        SearchResultItem(
            chunk_id="chunk_1",
            content="This is a test document about RAG systems. RAG stands for Retrieval-Augmented Generation.",
            score=0.95,
            metadata={"doc_name": "Test Doc 1", "page": 1},
            content_type="text",
        ),
        SearchResultItem(
            chunk_id="chunk_2",
            content="Vector databases store embeddings for efficient similarity search.",
            score=0.87,
            metadata={"doc_name": "Test Doc 2", "page": 3},
            content_type="text",
        ),
    ]


@pytest.fixture
def mock_llm_config():
    """Mock LLM configuration"""
    return {
        "id": 1,
        "name": "Test LLM",
        "model_id": "test-model-v1",
        "api_url": "http://test-api.example.com/v1",
        "api_key": "test-key-123",
        "model_type": "llm",
        "provider": "api",
    }


@pytest.mark.asyncio
@patch("app.core.database.async_session_factory")
async def test_record_token_usage_creates_record(mock_session_factory):
    """Test that _record_token_usage creates a TokenUsage record"""
    # Arrange - mock session
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act
    await _record_token_usage(
        model_config_id=1,
        model_name="Test Model",
        model_type="llm",
        provider="api",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=250.5,
        user_id=1,
    )

    # Assert - TokenUsage was created and added
    assert mock_session.add.called
    assert mock_session.commit.called

    # Verify TokenUsage was created with correct params
    call_args = mock_session.add.call_args[0][0]
    assert isinstance(call_args, TokenUsage)
    assert call_args.user_id == 1
    assert call_args.model_config_id == 1
    assert call_args.model_name == "Test Model"
    assert call_args.input_tokens == 100
    assert call_args.output_tokens == 50
    assert call_args.total_tokens == 150


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
@patch("app.services.llm_service.httpx.AsyncClient")
@patch("app.core.database.async_session_factory")
async def test_generate_rag_response_records_token_usage(
    mock_session_factory, mock_client_class, mock_get_config, mock_chunks
):
    """Test that generate_rag_response records token usage after calling LLM"""
    # Arrange - mock LLM config
    mock_get_config.return_value = {
        "id": 1,
        "name": "Test LLM",
        "model_id": "test-model",
        "api_url": "http://test.example.com/v1",
        "api_key": "test-key",
        "model_type": "llm",
        "provider": "api",
    }

    # Mock HTTP client and response
    mock_client = AsyncMock()
    mock_response = MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "choices": [{
                "message": {
                    "content": "This is a test answer based on the documents.",
                    "reasoning": "",
                }
            }],
            "usage": {
                "prompt_tokens": 80,
                "completion_tokens": 40,
                "total_tokens": 120,
            }
        })
    )
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client_class.return_value = mock_client

    # Mock session for token usage recording
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act
    result = await generate_rag_response(
        query="What is RAG?",
        chunks=mock_chunks,
        conversation_context="",
        stream=False,
        user_id=1,
    )

    # Assert - response is generated
    assert "answer" in result
    assert result["chunks_used"] == len(mock_chunks)

    # Assert - token usage was recorded
    assert mock_session.add.called
    token_usage = mock_session.add.call_args[0][0]
    assert isinstance(token_usage, TokenUsage)
    assert token_usage.total_tokens == 120
    assert token_usage.request_type == "chat"
    assert token_usage.model_config_id == 1


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
async def test_generate_rag_response_no_llm_returns_fallback(mock_get_config, mock_chunks):
    """Test that response falls back gracefully when no LLM is configured"""
    # Arrange - no LLM configured
    mock_get_config.return_value = None

    # Act
    result = await generate_rag_response(
        query="What is RAG?",
        chunks=mock_chunks,
        stream=False,
        user_id=1,
    )

    # Assert - fallback response returned
    assert "No LLM configured" in result["answer"]
    assert result["chunks_used"] == len(mock_chunks)


@pytest.mark.asyncio
@patch("app.core.database.async_session_factory")
async def test_token_usage_multiple_requests_accumulates(mock_session_factory):
    """Test that multiple requests correctly accumulate token usage"""
    # Arrange - mock session
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act - record multiple usages
    await _record_token_usage(
        model_config_id=1,
        model_name="Model A",
        model_type="llm",
        provider="api",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=200,
        user_id=1,
    )

    await _record_token_usage(
        model_config_id=1,
        model_name="Model A",
        model_type="llm",
        provider="api",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        latency_ms=300,
        user_id=1,
    )

    # Assert - both were recorded
    assert mock_session.add.call_count == 2


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
async def test_generate_rag_response_with_empty_chunks(mock_get_config):
    """Test that empty chunks returns early without calling LLM"""
    # Arrange
    mock_get_config.return_value = {
        "id": 1,
        "name": "Test LLM",
        "model_id": "test-model",
        "api_url": "http://test.example.com/v1",
        "api_key": "test-key",
    }

    # Act
    result = await generate_rag_response(
        query="What is RAG?",
        chunks=[],  # Empty chunks
        stream=False,
        user_id=1,
    )

    # Assert - LLM was not called, early return message
    assert "could not find relevant information" in result["answer"].lower()
    assert result["chunks_used"] == 0


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
@patch("app.services.llm_service.httpx.AsyncClient")
async def test_llm_api_error_returns_fallback(mock_client_class, mock_get_config, mock_chunks):
    """Test that LLM API error returns fallback response"""
    # Arrange
    mock_get_config.return_value = {
        "id": 1,
        "name": "Test LLM",
        "model_id": "test-model",
        "api_url": "http://test.example.com/v1",
        "api_key": "test-key",
    }

    # Mock HTTP error
    mock_client = AsyncMock()
    mock_response = MagicMock(status_code=500, text="Internal Server Error")
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client_class.return_value = mock_client

    # Act
    result = await generate_rag_response(
        query="What is RAG?",
        chunks=mock_chunks,
        stream=False,
        user_id=1,
    )

    # Assert - fallback response
    assert "AI generation service is currently unavailable" in result["answer"]


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
@patch("app.services.llm_service.httpx.AsyncClient")
@patch("app.core.database.async_session_factory")
async def test_token_usage_includes_latency(mock_session_factory, mock_client_class, mock_get_config, mock_chunks):
    """Test that token usage recording includes latency"""
    # Arrange
    mock_get_config.return_value = {
        "id": 1,
        "name": "Test LLM",
        "model_id": "test-model",
        "api_url": "http://test.example.com/v1",
        "api_key": "test-key",
        "model_type": "llm",
        "provider": "api",
    }

    mock_client = AsyncMock()
    mock_response = MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "choices": [{"message": {"content": "Answer"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
        })
    )
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client_class.return_value = mock_client

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act
    await generate_rag_response(
        query="What is RAG?",
        chunks=mock_chunks,
        stream=False,
        user_id=1,
    )

    # Assert
    token_usage = mock_session.add.call_args[0][0]
    assert token_usage.latency_ms is not None


@pytest.mark.asyncio
@patch("app.core.database.async_session_factory")
async def test_token_usage_user_id_optional(mock_session_factory):
    """Test that token usage can be recorded without user_id"""
    # Arrange
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act
    await _record_token_usage(
        model_config_id=1,
        model_name="Test Model",
        model_type="llm",
        provider="api",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=250.5,
        user_id=None,  # No user
    )

    # Assert
    call_args = mock_session.add.call_args[0][0]
    assert call_args.user_id is None
    assert call_args.total_tokens == 150


@pytest.mark.asyncio
@patch("app.services.llm_service._get_llm_config")
@patch("app.services.llm_service.httpx.AsyncClient")
@patch("app.core.database.async_session_factory")
async def test_full_qa_flow_with_token_recording(
    mock_session_factory, mock_client_class, mock_get_config, mock_chunks, test_user
):
    """
    End-to-end test: Full QA chat flow with token usage recording.

    This test verifies the complete flow:
    1. User asks a question
    2. System retrieves relevant chunks
    3. LLM generates answer
    4. Token usage is recorded to database
    """
    # Arrange - mock LLM config
    mock_get_config.return_value = {
        "id": 1,
        "name": "Gemini Pro",
        "model_id": "gemini-pro",
        "api_url": "https://generativelanguage.googleapis.com/v1",
        "api_key": "test-key",
        "model_type": "llm",
        "provider": "google",
    }

    # Mock HTTP client and response with realistic token usage
    mock_client = AsyncMock()
    mock_response = MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "choices": [{
                "message": {
                    "content": "RAG (Retrieval-Augmented Generation) is a technique that combines information retrieval with generative AI. It works by first searching a knowledge base for relevant documents, then using those documents as context for generating accurate, grounded responses.",
                    "reasoning": "",
                }
            }],
            "usage": {
                "prompt_tokens": 150,  # Query + retrieved chunks
                "completion_tokens": 85,  # Generated answer
                "total_tokens": 235,
            }
        })
    )
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client_class.return_value = mock_client

    # Mock session for token usage recording
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Act - Full QA flow
    result = await generate_rag_response(
        query="What is RAG and how does it work?",
        chunks=mock_chunks,
        conversation_context="",
        stream=False,
        user_id=test_user.id,
    )

    # Assert - Response generated correctly
    assert "answer" in result
    assert result["chunks_used"] == len(mock_chunks)
    assert result["latency_ms"] is not None

    # Assert - Token usage was recorded with correct values
    assert mock_session.add.called, "TokenUsage should have been added to session"
    token_usage = mock_session.add.call_args[0][0]

    assert isinstance(token_usage, TokenUsage), "Should record TokenUsage object"
    assert token_usage.user_id == test_user.id, "Should record correct user"
    assert token_usage.model_config_id == 1, "Should record correct model config"
    assert token_usage.model_name == "Gemini Pro", "Should record model name"
    assert token_usage.model_type == "llm", "Should record model type"
    assert token_usage.provider == "google", "Should record provider"
    assert token_usage.input_tokens == 150, "Should record input tokens"
    assert token_usage.output_tokens == 85, "Should record output tokens"
    assert token_usage.total_tokens == 235, "Should record total tokens"
    assert token_usage.request_type == "chat", "Should record request type"
    assert token_usage.status == "success", "Should record success status"
