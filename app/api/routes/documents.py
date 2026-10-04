"""POST /documents/ingest — rebuild the index from the repository's knowledge/ folder (D15).

* No uploads: a request with a body is refused (D15).
* Optional token (D4-06).
* After rebuilding, the running Agent switches to the new index without a
  restart; conversations are kept (D4-07).
* One ingestion at a time: a second concurrent request gets 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.agent.factory import load_knowledge
from app.api.dependencies import check_ingest_token, get_agent, get_state
from app.api.errors import ApiError
from app.api.schemas import IngestResponse
from app.rag.documents import DocumentLoadError
from app.rag.embeddings import EmbeddingsError
from app.rag.ingest import ingest

router = APIRouter(tags=["documents"])


@router.post("/documents/ingest", response_model=IngestResponse, dependencies=[Depends(check_ingest_token)])
def ingest_documents(request: Request) -> IngestResponse:
    if int(request.headers.get("content-length") or 0) > 0:
        raise ApiError(400, "uploads_not_accepted",
                       "This endpoint only re-indexes the repository's knowledge/ folder; uploads are not accepted.")
    state = get_state(request)
    agent = get_agent(request)
    if state.embeddings is None:
        raise ApiError(503, "embeddings_unavailable", "No embeddings provider is configured")
    if not state.ingest_lock.acquire(blocking=False):
        raise ApiError(409, "ingest_in_progress", "Another ingestion is already running")
    try:
        index, _ = ingest(state.embeddings, knowledge_dir=state.knowledge_dir, index_dir=state.index_dir)
        retriever, guard = load_knowledge(state.settings, state.embeddings, state.index_dir, state.knowledge_dir)
        agent.replace_retriever(retriever, guard)
    except EmbeddingsError as error:
        raise ApiError(502, "embeddings_failed", f"The embeddings provider failed: {error}") from None
    except DocumentLoadError as error:
        raise ApiError(422, "invalid_knowledge", f"A knowledge document is invalid: {error}") from None
    finally:
        state.ingest_lock.release()

    status = guard.status()
    state.observer.emit("ingest_completed", provider=index.info.embeddings_provider,
                        chunks=index.info.chunk_count, index_status=status)
    return IngestResponse(
        provider=index.info.embeddings_provider,
        model=index.info.embeddings_model,
        documents=len({e.metadata["source_document"] for e in index.entries}),
        chunks=index.info.chunk_count,
        knowledge_fingerprint=index.info.knowledge_fingerprint,
        index_status=status,
    )
