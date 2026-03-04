#!/usr/bin/env python3
"""
Seed Qdrant with style knowledge from PDFs in data/style_knowledge/.

Uses the pattern from 11_Advanced_Retrieval: PyPDFLoader + RecursiveCharacterTextSplitter.
Run: cd backend && PYTHONPATH=. python scripts/seed_rag.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Load .env from project root (parent of backend)
from dotenv import load_dotenv
load_dotenv(backend_dir.parent / ".env")

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.config import DATA_DIR
from services import rag

STYLE_KNOWLEDGE_DIR = DATA_DIR / "style_knowledge"


def load_and_chunk_pdfs() -> list[tuple[str, dict]]:
    """Load all PDFs, chunk, return (content, metadata) for each chunk."""
    if not STYLE_KNOWLEDGE_DIR.exists():
        print(f"Directory not found: {STYLE_KNOWLEDGE_DIR}")
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )
    all_chunks: list[tuple[str, dict]] = []

    for pdf_path in sorted(STYLE_KNOWLEDGE_DIR.glob("*.pdf")):
        print(f"Loading {pdf_path.name}...")
        try:
            loader = PyPDFLoader(str(pdf_path))
            raw_docs = loader.load()
            chunks = text_splitter.split_documents(raw_docs)
            for doc in chunks:
                meta = dict(doc.metadata)
                if "source" in meta:
                    meta["source"] = str(Path(meta["source"]).name)
                all_chunks.append((doc.page_content, meta))
        except Exception as e:
            print(f"  Error loading {pdf_path.name}: {e}")

    return all_chunks


def main():
    chunks = load_and_chunk_pdfs()
    if not chunks:
        print("No chunks to add. Ensure PDFs exist in data/style_knowledge/")
        return 1

    contents = [c[0] for c in chunks]
    metadatas = [c[1] for c in chunks]
    print(f"Adding {len(contents)} chunks to Qdrant...")
    rag.add_documents(contents, metadatas=metadatas)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
