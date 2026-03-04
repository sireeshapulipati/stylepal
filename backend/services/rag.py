"""RAG service for style knowledge using Qdrant Cloud."""
import os
import re
import time
import uuid
from typing import TYPE_CHECKING

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

if TYPE_CHECKING:
    from langchain_core.documents import Document

COLLECTION_NAME = "style_knowledge"
VECTOR_SIZE = 768  # gemini-embedding-001
EMBEDDING_MODEL = "models/gemini-embedding-001"

_embeddings = None


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            task_type="retrieval_document",
            output_dimensionality=VECTOR_SIZE,  # Match Qdrant collection (768)
        )
    return _embeddings


def _embed(texts: list[str], task_type: str = "retrieval_document") -> list[list[float]]:
    """Generate embeddings via Gemini (langchain-google-genai, no deprecated package).
    Retries on 503 UNAVAILABLE and 429 RESOURCE_EXHAUSTED."""
    emb = _get_embeddings()
    max_retries = 3
    retry_wait_max = 60  # Cap wait to avoid long hangs
    for attempt in range(max_retries):
        try:
            if task_type == "retrieval_query":
                return [emb.embed_query(t) for t in texts]
            return emb.embed_documents(texts)
        except Exception as e:
            err_str = str(e)
            if attempt >= max_retries - 1:
                raise
            # 503/429: use suggested retry delay or default
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", err_str, re.I) or re.search(
                    r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", err_str
                )
                wait = int(float(match.group(1))) if match else (5 if "503" in err_str else 30)
                time.sleep(min(wait, retry_wait_max))
                continue
            # Connection errors: Server disconnected, RemoteProtocolError, etc.
            if (
                "Server disconnected" in err_str
                or "RemoteProtocolError" in type(e).__name__
                or "Connection" in type(e).__name__
            ):
                time.sleep(2 * (attempt + 1))
                continue
            raise


def _get_qdrant_client() -> QdrantClient:
    """Get Qdrant Cloud client."""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url or not api_key:
        raise ValueError("QDRANT_URL and QDRANT_API_KEY must be set for Qdrant Cloud")
    return QdrantClient(url=url, api_key=api_key, timeout=10.0)


def _ensure_collection(client: QdrantClient) -> None:
    """Create collection if it doesn't exist."""
    collections = client.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def add_documents(
    documents: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> None:
    """Add documents to Qdrant. Generates embeddings via Gemini."""
    client = _get_qdrant_client()
    _ensure_collection(client)
    embeddings = _embed(documents, task_type="retrieval_document")
    if ids is None:
        ids = [str(uuid.uuid4()) for _ in documents]
    if metadatas is None:
        metadatas = [{}] * len(documents)
    points = [
        PointStruct(id=id_, vector=emb, payload={"content": doc, **meta})
        for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve relevant style guidance for a query."""
    client = _get_qdrant_client()
    try:
        collection_info = client.get_collection(COLLECTION_NAME)
    except Exception:
        return []
    if collection_info.points_count == 0:
        return []
    query_embedding = _embed([query], task_type="retrieval_query")[0]
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
    )
    points = response.points if hasattr(response, "points") else []
    return [
        {"content": (hit.payload or {}).get("content", ""), "metadata": {k: v for k, v in (hit.payload or {}).items() if k != "content"}}
        for hit in points
    ]


def retrieve_as_documents(query: str, top_k: int = 5) -> list["Document"]:
    """Retrieve style guidance as LangChain Documents for LangGraph RAG."""
    from langchain_core.documents import Document

    hits = retrieve(query, top_k=top_k)
    return [
        Document(page_content=h["content"], metadata=h.get("metadata", {}))
        for h in hits
    ]
