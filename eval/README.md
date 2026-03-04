# Stylepal Evals with Ragas

Evaluation notebooks for RAG and Agent, based on AIE9/10_Evaluating_RAG_With_Ragas.

## Prerequisites

- `.env` at project root with `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`
- RAG: Qdrant collection populated with style knowledge (run ingestion if needed)
- Agent: Wardrobe with items (run `backend/scripts/seed_wardrobe.py` if needed)

## Install

```bash
pip install ragas pandas
# or from project root: pip install -r backend/requirements.txt
```

## Notebooks

### eval_rag_ragas.ipynb

Evaluates the RAG pipeline (retrieval + generation) with:
- **Faithfulness** – answer grounded in context
- **Context Precision** – retrieval relevance
- **Context Recall** – retrieval completeness
- **Response Relevancy** – answer relevance to question

Uses a curated eval set from Flattering Fashions style knowledge.

### eval_agent_ragas.ipynb

Evaluates the Stylist Agent with:
- **Agent Goal Accuracy** – did the agent achieve the user's goal?
- **Topic Adherence** – does the agent stay on topic (wardrobe, styling)?

Uses test queries for outfit requests and informational questions.

## Running

Open in Jupyter from project root:

```bash
cd stylepal
jupyter notebook eval/
```

Or run cells in VS Code / Cursor. Ensure the kernel can see the `backend` package (setup cell adds it to `sys.path`).
