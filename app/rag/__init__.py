"""RAG layer — documentary knowledge only (CP2).

Answers "what does the documented knowledge say?". It never calculates payroll,
never determines PASS / FAIL and never modifies Validation Engine results.

    documents.py   parse knowledge/ Markdown + front matter
    chunking.py    one chunk per section, with traceable metadata
    embeddings.py  provider interface: Gemini (approved) + deterministic fake
    vector_index.py  JSON index + plain-Python cosine similarity
    ingest.py      Documents -> Chunks -> Embeddings -> Index (once)
    retriever.py   Question -> Embedding -> Similarity search -> Chunks
    consistency.py documentation <-> config/validation_rules.yaml check
"""
