# Stylepal: Step-by-Step Implementation

Add one capability at a time, test it, then iterate.

---

## Step 1: Backend health check

**Goal:** Verify backend runs and responds.

- Run backend: `cd backend && PYTHONPATH=. uvicorn main:app --reload`
- Hit `GET http://localhost:8000/health` → expect `{"status": "ok"}`

**Test:** curl or browser.

---

## Step 2: Wardrobe API (basic)

**Goal:** Add and list wardrobe items.

- **Pre-load DB:** Run seed script to load ~180 items from CSV:
  ```bash
  cd backend && PYTHONPATH=. python scripts/seed_wardrobe.py
  ```
  (CSV: `backend/data/wardrobe_seed.csv`)
- Implement `POST /wardrobe/items` and `GET /wardrobe/items` (already scaffolded)
- List items via `GET /wardrobe/items` and confirm seed data appears

**Test:** curl/Postman/Thunder Client.

---

## Step 3: Profile and memory API

**Goal:** Read/write profile and outfit history.

- `GET /profile` → returns profile (or defaults)
- `PATCH /profile` → update preferences
- `POST /outfits` → record outfit
- `POST /outfits/{id}/rate` → rate outfit

**Test:** Verify `backend/data/profile.json` and `outfit_history.json` are created/updated.

---

## Step 4: Stylist Agent (no tools)

**Goal:** Gemini returns a simple outfit plan from a text query only.

- Implement `POST /stylist/plan` with body `{ query }`
- Call Gemini with a fixed system prompt (no tools)
- Return `{ outfit_plan, reasoning }` (can be mock/placeholder structure)

**Test:** Send "outfit for a business meeting" → get back a text response.

---

## Step 5: Wardrobe tool

**Goal:** Agent can read the user's wardrobe.

- Add wardrobe tool: agent calls service to get items
- Inject wardrobe data into Gemini context
- Agent uses real items in its plan

**Test:** Add 2–3 items to wardrobe, ask for outfit → plan references those items by name.

---

## Step 6: Weather tool

**Goal:** Agent considers weather when planning.

- Add Open-Meteo (or similar) weather tool
- Agent calls it when query implies weather (e.g. "tomorrow", "this week")
- Include forecast in context

**Test:** "Outfit for tomorrow" → plan mentions weather-appropriate choices.

---

## Step 7: RAG style knowledge (with seed content)

**Goal:** Agent uses curated styling principles.

- Create `backend/data/style_knowledge/` with markdown docs (fit, color, occasion, etc.)
- Add seed script: chunk docs, call `rag.add_documents()`
- Add RAG tool: agent retrieves style guidance for the query
- Inject retrieved chunks into context

**Test:** Ask "business casual outfit" → plan reflects rules from the knowledge base.

---

## Step 8: Memory integration

**Goal:** Agent uses profile and outfit history.

- Inject `memory.get_profile()` and `memory.get_outfit_history()` into context
- Agent tailors plans to preferences and avoids over-worn items

**Test:** Set preferences, add past outfits → plan respects them.

---

## Step 9: Frontend – Home / Chat

**Goal:** UI to query the Stylist Agent.

- Home page with input for query + optional constraints
- Call `POST /stylist/plan`
- Display outfit plan and reasoning

**Test:** Use UI to get an outfit plan.

---

## Step 10: Frontend – Wardrobe management

**Goal:** Add, edit, delete items from the UI.

- Wardrobe page: list items, filters
- Add-item form (dialog)
- Edit/delete actions

**Test:** Manage wardrobe via UI.

---

## Step 11: Frontend – Profile and outfit history

**Goal:** View/edit profile, record and rate outfits.

- Profile page: view/edit preferences
- After accepting a plan: record outfit
- Rate past outfits

**Test:** Full flow: plan → accept → rate.

---

## Step 12: Web search tool (optional)

**Goal:** Agent can suggest products when wardrobe has gaps.

- Add Serper/Tavily/Google Custom Search
- Agent calls it when suggesting additions

**Test:** "I need a navy blazer" → plan includes product search results.

---

## Summary

| Step | Capability           | Test checkpoint                    |
|------|----------------------|------------------------------------|
| 1    | Backend health       | `/health` returns ok               |
| 2    | Wardrobe CRUD        | Add + list items via API           |
| 3    | Profile + memory API | Profile/outfit JSON files update   |
| 4    | Stylist (no tools)   | Text response from Gemini          |
| 5    | Wardrobe tool        | Plan uses real wardrobe items      |
| 6    | Weather tool         | Plan considers weather             |
| 7    | RAG + seed docs      | Plan follows style knowledge      |
| 8    | Memory integration   | Plan uses profile + history        |
| 9    | Frontend chat        | UI → plan flow works               |
| 10   | Frontend wardrobe    | Manage items in UI                 |
| 11   | Frontend profile     | Full plan → accept → rate flow     |
| 12   | Web search (opt)     | Product suggestions when needed    |
