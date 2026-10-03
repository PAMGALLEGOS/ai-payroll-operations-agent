"""Embeddings provider abstraction, fake provider, Gemini request mapping, missing credentials.

The Gemini provider is tested with an injected fake client: these tests check
what would be sent to Gemini and how responses are handled, without network
access or credentials.
"""

import math
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingsConfigError,
    EmbeddingsError,
    FakeEmbeddingProvider,
    GeminiEmbeddingProvider,
    create_embedding_provider,
)


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)  # never read a developer's real .env in tests


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


class FakeGeminiClient:
    """Records embed_content calls and returns vectors of the requested size."""

    def __init__(self, dims=8, count_override=None, size_override=None, error=None):
        self.calls = []
        self.dims, self.count_override, self.size_override, self.error = dims, count_override, size_override, error
        self.models = self

    def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        if self.error:
            raise self.error
        n = self.count_override if self.count_override is not None else len(contents)
        size = self.size_override or self.dims
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0] + [0.0] * (size - 1)) for _ in range(n)])


# ------------------------------------------------------------------ fake
def test_fake_provider_implements_the_interface():
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)


def test_fake_provider_is_deterministic_and_normalised():
    provider = FakeEmbeddingProvider()
    a = provider.embed_query("What is the net pay tolerance?")
    b = provider.embed_query("What is the net pay tolerance?")
    assert a == b
    assert len(a) == provider.dimensions
    assert _norm(a) == pytest.approx(1.0)


def test_fake_provider_separates_different_texts():
    provider = FakeEmbeddingProvider()
    assert provider.embed_query("gross pay tolerance") != provider.embed_query("pasta recipe")


def test_fake_provider_handles_text_without_words():
    vector = FakeEmbeddingProvider().embed_query("?? !!")
    assert all(v == 0.0 for v in vector)


# --------------------------------------------------------------- factory
def test_factory_builds_fake_without_credentials():
    provider = create_embedding_provider(_settings(embeddings_provider="fake"))
    assert provider.name == "fake"


def test_factory_refuses_gemini_without_api_key():
    with pytest.raises(EmbeddingsConfigError, match="GEMINI_API_KEY"):
        create_embedding_provider(_settings(embeddings_provider="gemini"))


def test_factory_explicit_provider_overrides_settings():
    provider = create_embedding_provider(_settings(embeddings_provider="gemini"), "fake")
    assert provider.name == "fake"


def test_factory_rejects_unknown_provider():
    with pytest.raises(EmbeddingsConfigError, match="Unknown"):
        create_embedding_provider(_settings(), "openai")


def test_default_settings_use_gemini_as_approved_provider():
    settings = _settings()
    assert settings.embeddings_provider == "gemini"
    assert settings.gemini_embedding_model == "gemini-embedding-001"


# ---------------------------------------------------------------- gemini
def _gemini(client, dims=8):
    return GeminiEmbeddingProvider(api_key="test-key", model="gemini-embedding-001", dimensions=dims, client=client)


def test_gemini_documents_use_retrieval_document_task():
    client = FakeGeminiClient()
    _gemini(client).embed_documents(["a", "b"])
    call = client.calls[0]
    assert call["model"] == "gemini-embedding-001"
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].output_dimensionality == 8


def test_gemini_query_uses_retrieval_query_task():
    client = FakeGeminiClient()
    _gemini(client).embed_query("question")
    assert client.calls[0]["config"].task_type == "RETRIEVAL_QUERY"


def test_gemini_batches_large_requests():
    client = FakeGeminiClient()
    vectors = _gemini(client).embed_documents([f"t{i}" for i in range(250)])
    assert len(vectors) == 250
    assert [len(c["contents"]) for c in client.calls] == [100, 100, 50]


def test_gemini_vectors_are_normalised():
    vector = _gemini(FakeGeminiClient()).embed_query("q")
    assert _norm(vector) == pytest.approx(1.0)


def test_gemini_count_mismatch_is_an_error():
    with pytest.raises(EmbeddingsError, match="returned 1 embeddings for 2"):
        _gemini(FakeGeminiClient(count_override=1)).embed_documents(["a", "b"])


def test_gemini_wrong_vector_size_is_an_error():
    with pytest.raises(EmbeddingsError, match="unexpected size"):
        _gemini(FakeGeminiClient(size_override=4)).embed_query("q")


def test_gemini_sdk_errors_are_wrapped():
    with pytest.raises(EmbeddingsError, match="request failed"):
        _gemini(FakeGeminiClient(error=RuntimeError("quota"))).embed_query("q")


def test_gemini_requires_api_key():
    with pytest.raises(EmbeddingsConfigError):
        GeminiEmbeddingProvider(api_key="", model="gemini-embedding-001", dimensions=8, client=FakeGeminiClient())


def test_gemini_embedding_2_is_refused_explicitly():
    with pytest.raises(EmbeddingsConfigError, match="not supported"):
        GeminiEmbeddingProvider(api_key="k", model="gemini-embedding-2", dimensions=8, client=FakeGeminiClient())
