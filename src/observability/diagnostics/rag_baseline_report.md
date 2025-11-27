# RAG Baseline Performance Report
**Generated:** 2025-10-12 01:43:00
**Test Queries:** 10

---

## 1. Initialization
- ✅ RAG backend initialized successfully
- Documents loaded: 422

## 2. Query Results

### Query 1: When did we last discuss D-REAM?
- **Latency:** 3571.9ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** The most recent discussion about D-REAM focused on behavioral changes post-evolution cycle, addressing drift issues by adjusting kl_tau settings and v...

### Query 2: What errors occurred this week?
- **Latency:** 2413.2ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** This week, there were no specific error events noted in the provided context. However, it's recommended to check conversation logs for any tone drift ...

### Query 3: Show the most recent successful candidate_pack run
- **Latency:** 5774.8ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** To answer your question about showing the most recent successful candidate_pack run, I need to refer to logs or a specific report that tracks these ru...

### Query 4: Summarize my last five voice-pipeline updates
- **Latency:** 6693.5ms
- **Sources retrieved:** 2
- **Documents retrieved:** 2
- **Relevance:** good
- **Response preview:** Your recent updates include verifying the integrity of 3616 voice samples, updating baseline metrics, and testing PERSONA_PROMPT injection in all code...

### Query 5: Which changes from D-REAM results were made recently?
- **Latency:** 7539.9ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** Recent changes include lowering kl_tau to stricter values and verifying that PERSONALITY_PRESERVATION is set to 1 to address drift issues after D-REAM...

### Query 6: What was the conclusion of the AgentFlow comparison?
- **Latency:** 3265.7ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** The context provided does not contain specific information about a conclusion from an AgentFlow comparison. The details given pertain more broadly to ...

### Query 7: List all mentions of PETRI in the past month
- **Latency:** 5883.9ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** To answer your query about mentioning PETRI in the past month, I would need to access episode summaries or specific event logs that contain references...

### Query 8: When was the hybrid retriever introduced?
- **Latency:** 2057.6ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** The provided quotes do not specify an exact date or version when the hybrid retriever was introduced. It is mentioned that KLoROS employs a hybrid mem...

### Query 9: What feature was added in Phase 2 of D-REAM?
- **Latency:** 1924.8ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** In Phase 2 of the D-REAM cycle, continuous background evolution was initiated, including parameter mutation and selection to optimize system performan...

### Query 10: What did I tell you to prioritize next?
- **Latency:** 2750.4ms
- **Sources retrieved:** 5
- **Documents retrieved:** 5
- **Relevance:** good
- **Response preview:** Based on the provided context, the next priority seems to be running regular housekeeping tasks as specified in the best practices section. Specifical...

## 3. Performance Summary

- **Total queries:** 10
- **Successful queries:** 10
- **Success rate:** 100.0%
- **Average latency:** 4187.6ms
- **Total time:** 41875.8ms

### Relevance Breakdown
| Relevance | Count | Percentage |
|-----------|-------|------------|
| good | 10 | 100.0% |

## 4. Assessment Against Acceptance Criteria

**Target criteria (from plan):**
- ≥90% relevance rate
- <1500ms latency

**Actual results:**
- ❌ Latency: 4187.6ms (FAIL)
- ✅ Success rate: 100.0% (PASS)

## 5. Identified Issues

- **High latency:** Average 4187.6ms exceeds 1500ms target

## 6. Blind Spots Identified

- No blind spots identified

## 7. Recommendations

2. **HIGH:** Optimize retrieval latency
   - Cache embeddings
   - Use FAISS indexing (appears to be available)
   - Reduce embedding dimension if possible
3. **MEDIUM:** Distinguish between RAG and memory queries
   - Time-based queries ('when', 'recent') should use episodic memory
   - Factual queries should use RAG knowledge base
   - Current system doesn't clearly separate these

**Detailed results saved to:** `/home/kloros/diagnostics/rag_test_results.json`
