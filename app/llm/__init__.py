"""LLM provider abstraction (CP3).

    client.py         LLMClient interface + errors
    gemini_client.py  Gemini (approved provider, D1) with structured JSON output
    fake_client.py    deterministic, scriptable test double

The Agent depends only on LLMClient. The LLM is used for two jobs only:
classifying intent and writing explanations from evidence it is given.
"""
