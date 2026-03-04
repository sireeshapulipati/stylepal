# Evaluation Results Summary (Cert Challenge)

## RAG Evals: Final Summary (across tests)

**Mean metrics (Original 5 + Extended 6 + Synthetic 12):**

| Metric | Original (5) | Extended (6) | Synthetic (12) |
|--------|---------------|--------------|----------------|
| Context recall | 100% | 50% | ~75% |
| Context precision | ~0.82 | ~0.76 | ~0.77 |
| Faithfulness | 100% | 83% | ~79% |
| Factual correctness | ~0.69 | ~0.45 | ~0.55 |
| Answer relevancy | ~0.80 | ~0.46 | ~0.78 |

**What worked:** Retrieval strong on curated questions; faithfulness high when context recall succeeds; context precision generally good (0.77–0.82).

**What didn't:** Extended set has retrieval gaps (navy colors, apple waistlines, necklines); factual correctness and answer relevancy drop on harder queries; context entity recall near 0.

**Possible improvements:** Add KB content for navy pairing, apple-shape styling; improve retrieval for multi-hop queries; tune chunking/embedding; review weak samples (5, 7, 8) for KB/retrieval fixes.

---

## Agent Evals: Final Summary (gpt-4.1 evaluator only)

**Mean metrics:**

| Metric | Original (6) | Extended (14) |
|--------|---------------|---------------|
| Agent Goal Accuracy | 0.33 | 0.57 |
| Topic Adherence | 0.61 | 0.80 |
| Tool Coverage | 0.83 | 0.86 |

**What worked:** Profile updates (I moved to NYC, pear-shaped); add wardrobe (white sneakers); deprecate item; informational (colors with navy, golden mean); outfit suggestions when context clear. Tool coverage high—agent calls expected tools.

**What didn't:** "I prefer tailored fits" (0.0s, no tool calls); tech conference (ToolCov 0); some outfit requests still fail goal; add navy blazer with full metadata inconsistent.

**Possible improvements:** Fix profile-update routing for "tailored fits"; relax or broaden reference strings; add multiple acceptable outcomes per query; investigate tech-conference ToolCov failure.
