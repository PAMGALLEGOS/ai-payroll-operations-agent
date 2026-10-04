"""F6b: malformed Gemini model names are refused at start-up with a clear message."""

import pytest

from app.core.config import Settings
from app.core.model_names import model_name_problem
from app.llm.client import LLMConfigError
from app.llm.gemini_client import GeminiLLMClient
from app.rag.embeddings import EmbeddingsConfigError, GeminiEmbeddingProvider
from tests.helpers import FAKE_KEY

BAD = ["GEMINI_MODEL=gemini-3.8-flash", "gemini-3.8-flash ", " gemini-3.8-flash", '"gemini-3.8-flash"',
       "'gemini-3.8-flash'", "gemini 3.8 flash", "models/", "gemini-3.8-flash # comment"]
GOOD = ["gemini-3.8-flash", "models/gemini-3.8-flash", "gemini-2.5-flash-lite", "models/gemini-embedding-001"]


@pytest.mark.parametrize("value", GOOD)
def test_valid_names_are_accepted(value):
    assert model_name_problem("GEMINI_MODEL", value, "gemini-3.8-flash") is None
    GeminiLLMClient(FAKE_KEY, value, client=object())


@pytest.mark.parametrize("value", BAD)
def test_llm_rejects_malformed_model_name(value):
    with pytest.raises(LLMConfigError) as error:
        GeminiLLMClient(FAKE_KEY, value, client=object())
    assert repr(value) in str(error.value) and "GEMINI_MODEL=gemini-3.8-flash" in str(error.value)


def test_embeddings_reject_duplicated_variable_name():
    value = "GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001"
    with pytest.raises(EmbeddingsConfigError) as error:
        GeminiEmbeddingProvider(FAKE_KEY, value, 768, client=object())
    assert repr(value) in str(error.value)


def test_embeddings_accept_valid_name():
    GeminiEmbeddingProvider(FAKE_KEY, "models/gemini-embedding-001", 768, client=object())


def test_factory_fails_fast_instead_of_falling_back():
    from app.agent.factory import create_llm_client

    settings = Settings(_env_file=None, gemini_api_key=FAKE_KEY, gemini_model="GEMINI_MODEL=gemini-3.8-flash")
    with pytest.raises(LLMConfigError):
        create_llm_client(settings, "gemini")


def test_fake_mode_is_not_affected_by_a_malformed_gemini_name():
    from app.agent.factory import create_llm_client

    settings = Settings(_env_file=None, gemini_model="GEMINI_MODEL=gemini-3.8-flash")
    assert create_llm_client(settings, "fake").name == "fake"
