# Stylepal

A trusted style companion that starts with your wardrobe.

StylePal is a wardrobe intelligence system that helps intentional professionals maximize what they already own while staying stylistically current. It maintains a structured wardrobe database with item attributes, wear frequency, and occasion tags, and plans outfits based on real constraints such as business trips, speaking engagements, or seasonal shifts. A curated retrieval-augmented styling knowledge base ensures recommendations reflect current professional styling principles without chasing volatile trends.

Unlike a standard chatbot, StylePal models behavior over time. It tracks outfit selections, look ratings, and confidence signals to refine silhouette preferences, comfort thresholds, and rotation patterns. When structural gaps limit combination diversity, it may suggest minimal, well-aligned additions, but reuse remains the default. As engagement increases, the system improves personalization, reduces repetition, and evolves alongside the user's professional identity.

## Project Structure

- `frontend/` — Next.js 14+ (App Router) with shadcn/ui
- `backend/` — FastAPI with SQLAlchemy, Gemini, Qdrant Cloud

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

API runs at http://localhost:8000

**Seed wardrobe (optional):** Pre-load ~180 sample items from CSV:
```bash
cd backend && PYTHONPATH=. python scripts/seed_wardrobe.py
```
Uses `backend/data/wardrobe_seed.csv`. Database file: `stylepal.db` (in cwd when uvicorn runs).

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

App runs at http://localhost:3000

### Environment

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` for the Stylist Agent.
