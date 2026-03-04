"""Advanced RAG retrieval: reranking, multi-query, and both combined.

Based on AIE9/11_Advanced_Retrieval patterns:
- Reranking: ContextualCompressionRetriever + CohereRerank (retrieve more, compress to top)
- Multi-query: MultiQueryRetriever (LLM expands query into variants, union of results)
- Both: Multi-query first, then rerank the combined results
"""

from typing import Literal

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from services import rag

# Mode for retrieval strategy
RetrievalMode = Literal["rerank", "multi_query", "both"]


class StyleRetriever(BaseRetriever):
    """LangChain retriever wrapping rag.retrieve_as_documents with configurable top_k."""

    top_k: int = 5

    def _get_relevant_documents(self, query: str) -> list[Document]:
        return rag.retrieve_as_documents(query, top_k=self.top_k)


def _get_base_retriever(retrieve_k: int = 15) -> StyleRetriever:
    """Base retriever for advanced pipelines. Uses higher k for reranking."""
    return StyleRetriever(top_k=retrieve_k)


def _get_rerank_retriever(retrieve_k: int = 15, top_n: int = 5):
    """Reranking: retrieve more docs, then Cohere rerank to top_n."""
    try:
        from langchain_classic.retrievers import ContextualCompressionRetriever
    except ImportError:
        from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
    from langchain_cohere import CohereRerank

    base = _get_base_retriever(retrieve_k=retrieve_k)
    compressor = CohereRerank(model="rerank-v3.5", top_n=top_n)
    return ContextualCompressionRetriever(base_compressor=compressor, base_retriever=base)


def _get_multi_query_retriever(llm, retrieve_k: int = 5):
    """Multi-query: LLM expands query into variants, union of retrievals."""
    try:
        from langchain_classic.retrievers import MultiQueryRetriever
    except ImportError:
        from langchain_classic.retrievers.multi_query import MultiQueryRetriever

    base = _get_base_retriever(retrieve_k=retrieve_k)
    return MultiQueryRetriever.from_llm(retriever=base, llm=llm)


def _get_rerank_multi_query_retriever(llm, retrieve_k: int = 15, top_n: int = 5):
    """Both: multi-query first (diverse retrieval), then rerank to top_n."""
    try:
        from langchain_classic.retrievers import ContextualCompressionRetriever, MultiQueryRetriever
    except ImportError:
        from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
        from langchain_classic.retrievers.multi_query import MultiQueryRetriever
    from langchain_cohere import CohereRerank

    base = _get_base_retriever(retrieve_k=retrieve_k)
    multi_query = MultiQueryRetriever.from_llm(retriever=base, llm=llm)
    compressor = CohereRerank(model="rerank-v3.5", top_n=top_n)
    return ContextualCompressionRetriever(base_compressor=compressor, base_retriever=multi_query)


def retrieve_advanced(
    query: str,
    mode: RetrievalMode = "rerank",
    top_k: int = 5,
    llm=None,
) -> list[dict]:
    """
    Retrieve with advanced techniques.

    Args:
        query: User question.
        mode: "rerank" | "multi_query" | "both"
        top_k: Final number of docs to return (used for rerank top_n; multi_query returns union).
        llm: Required for multi_query and both. Chat model for query expansion.

    Returns:
        List of {"content": str, "metadata": dict} like rag.retrieve().
    """
    if mode in ("multi_query", "both") and llm is None:
        raise ValueError("llm is required for multi_query and both modes")

    if mode == "rerank":
        retriever = _get_rerank_retriever(retrieve_k=15, top_n=top_k)
        docs = retriever.invoke(query)
    elif mode == "multi_query":
        retriever = _get_multi_query_retriever(llm=llm, retrieve_k=top_k)
        docs = retriever.invoke(query)
        # Multi-query returns union; optionally cap to top_k by taking first top_k
        docs = docs[:top_k] if len(docs) > top_k else docs
    else:  # both
        retriever = _get_rerank_multi_query_retriever(llm=llm, retrieve_k=15, top_n=top_k)
        docs = retriever.invoke(query)

    return [
        {"content": d.page_content, "metadata": d.metadata}
        for d in docs
    ]


def retrieve_advanced_as_documents(
    query: str,
    mode: RetrievalMode = "rerank",
    top_k: int = 5,
    llm=None,
) -> list[Document]:
    """Same as retrieve_advanced but returns LangChain Documents."""
    hits = retrieve_advanced(query=query, mode=mode, top_k=top_k, llm=llm)
    return [
        Document(page_content=h["content"], metadata=h.get("metadata", {}))
        for h in hits
    ]
