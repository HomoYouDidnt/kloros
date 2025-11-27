#!/usr/bin/env python3
"""RAG Baseline Performance Test"""
import sys
import time
import json
sys.path.insert(0, '/home/kloros')

from src.cognition.reasoning.local_rag_backend import LocalRagBackend

# Test queries from the diagnostic plan
test_queries = [
    "When did we last discuss D-REAM?",
    "What errors occurred this week?",
    "Show the most recent successful candidate_pack run",
    "Summarize my last five voice-pipeline updates",
    "Which changes from D-REAM results were made recently?",
    "What was the conclusion of the AgentFlow comparison?",
    "List all mentions of PETRI in the past month",
    "When was the hybrid retriever introduced?",
    "What feature was added in Phase 2 of D-REAM?",
    "What did I tell you to prioritize next?"
]

report = []
report.append("# RAG Baseline Performance Report")
report.append("**Generated:** 2025-10-12 01:43:00")
report.append("**Test Queries:** 10")
report.append("")
report.append("---")
report.append("")

# Initialize RAG backend
try:
    print("[rag_test] Initializing RAG backend...")
    rag = LocalRagBackend(bundle_path="/home/kloros/rag_data/rag_store.npz")

    if rag.rag_instance is None:
        report.append("## ❌ CRITICAL ERROR")
        report.append("RAG instance failed to initialize. Cannot perform baseline test.")
    else:
        report.append("## 1. Initialization")
        report.append(f"- ✅ RAG backend initialized successfully")
        report.append(f"- Documents loaded: {len(rag.rag_instance.metadata)}")
        report.append("")

        # Test each query
        report.append("## 2. Query Results")
        report.append("")

        results = []
        total_time = 0
        successful_queries = 0

        for i, query in enumerate(test_queries, 1):
            print(f"[rag_test] Testing query {i}/10: {query[:50]}...")

            try:
                start_time = time.time()
                result = rag.reply(query)
                elapsed = (time.time() - start_time) * 1000  # Convert to ms
                total_time += elapsed

                # Extract response details
                response_text = result.reply_text[:200] if result.reply_text else "(empty)"
                sources_count = len(result.sources)
                retrieved_count = result.meta.get('retrieved_count', 0)

                # Assess relevance (simple heuristic)
                relevance = "unknown"
                if response_text == "(empty)" or "not available" in response_text.lower():
                    relevance = "poor"
                elif sources_count > 0:
                    relevance = "good"
                elif retrieved_count > 0:
                    relevance = "fair"
                else:
                    relevance = "poor"

                if relevance in ["good", "fair"]:
                    successful_queries += 1

                results.append({
                    "query": query,
                    "elapsed_ms": elapsed,
                    "response_preview": response_text,
                    "sources_count": sources_count,
                    "retrieved_count": retrieved_count,
                    "relevance": relevance
                })

                # Add to report
                report.append(f"### Query {i}: {query}")
                report.append(f"- **Latency:** {elapsed:.1f}ms")
                report.append(f"- **Sources retrieved:** {sources_count}")
                report.append(f"- **Documents retrieved:** {retrieved_count}")
                report.append(f"- **Relevance:** {relevance}")
                report.append(f"- **Response preview:** {response_text[:150]}...")
                report.append("")

            except Exception as e:
                print(f"[rag_test] Query {i} failed: {e}")
                results.append({
                    "query": query,
                    "error": str(e),
                    "relevance": "error"
                })

                report.append(f"### Query {i}: {query}")
                report.append(f"- **Status:** ❌ ERROR")
                report.append(f"- **Error:** {str(e)}")
                report.append("")

        # Performance summary
        report.append("## 3. Performance Summary")
        report.append("")

        avg_latency = total_time / len(test_queries) if test_queries else 0
        success_rate = (successful_queries / len(test_queries) * 100) if test_queries else 0

        report.append(f"- **Total queries:** {len(test_queries)}")
        report.append(f"- **Successful queries:** {successful_queries}")
        report.append(f"- **Success rate:** {success_rate:.1f}%")
        report.append(f"- **Average latency:** {avg_latency:.1f}ms")
        report.append(f"- **Total time:** {total_time:.1f}ms")
        report.append("")

        # Relevance breakdown
        relevance_counts = {}
        for r in results:
            rel = r.get('relevance', 'unknown')
            relevance_counts[rel] = relevance_counts.get(rel, 0) + 1

        report.append("### Relevance Breakdown")
        report.append("| Relevance | Count | Percentage |")
        report.append("|-----------|-------|------------|")
        for rel, count in sorted(relevance_counts.items()):
            pct = (count / len(results) * 100) if results else 0
            report.append(f"| {rel} | {count} | {pct:.1f}% |")
        report.append("")

        # Assessment against acceptance criteria
        report.append("## 4. Assessment Against Acceptance Criteria")
        report.append("")
        report.append("**Target criteria (from plan):**")
        report.append("- ≥90% relevance rate")
        report.append("- <1500ms latency")
        report.append("")
        report.append("**Actual results:**")

        if avg_latency < 1500:
            report.append(f"- ✅ Latency: {avg_latency:.1f}ms (PASS)")
        else:
            report.append(f"- ❌ Latency: {avg_latency:.1f}ms (FAIL)")

        if success_rate >= 90:
            report.append(f"- ✅ Success rate: {success_rate:.1f}% (PASS)")
        elif success_rate >= 70:
            report.append(f"- ⚠️ Success rate: {success_rate:.1f}% (MARGINAL)")
        else:
            report.append(f"- ❌ Success rate: {success_rate:.1f}% (FAIL)")
        report.append("")

        # Identified issues
        report.append("## 5. Identified Issues")
        report.append("")

        issues = []
        if success_rate < 90:
            issues.append(f"- **Low success rate:** Only {success_rate:.1f}% of queries returned relevant results")
        if avg_latency > 1500:
            issues.append(f"- **High latency:** Average {avg_latency:.1f}ms exceeds 1500ms target")

        # Check for specific query failures
        time_based_queries = [q for q in results if any(word in q.get('query', '').lower() for word in ['when', 'recent', 'last', 'week'])]
        if time_based_queries:
            time_based_failures = [q for q in time_based_queries if q.get('relevance') == 'poor']
            if len(time_based_failures) > 0:
                issues.append(f"- **Temporal query weakness:** {len(time_based_failures)}/{len(time_based_queries)} time-based queries failed")

        if not issues:
            report.append("- ✅ No major issues identified")
        else:
            for issue in issues:
                report.append(issue)
        report.append("")

        # Blind spots
        report.append("## 6. Blind Spots Identified")
        report.append("")

        poor_queries = [r for r in results if r.get('relevance') == 'poor']
        if poor_queries:
            report.append("**Queries with poor results:**")
            for q in poor_queries:
                report.append(f"- {q['query']}")
            report.append("")

            report.append("**Possible reasons:**")
            report.append("- RAG corpus doesn't contain this information")
            report.append("- Embeddings not capturing semantic meaning")
            report.append("- Query requires episodic memory, not RAG knowledge base")
            report.append("- Temporal queries need time-based filtering (not implemented)")
        else:
            report.append("- No blind spots identified")
        report.append("")

        # Recommendations
        report.append("## 7. Recommendations")
        report.append("")

        if success_rate < 70:
            report.append("1. **CRITICAL:** Investigate why RAG is returning irrelevant results")
            report.append("   - Check document corpus quality")
            report.append("   - Verify embeddings are working correctly")
            report.append("   - Test with known-good queries")

        if avg_latency > 1000:
            report.append("2. **HIGH:** Optimize retrieval latency")
            report.append("   - Cache embeddings")
            report.append("   - Use FAISS indexing (appears to be available)")
            report.append("   - Reduce embedding dimension if possible")

        report.append("3. **MEDIUM:** Distinguish between RAG and memory queries")
        report.append("   - Time-based queries ('when', 'recent') should use episodic memory")
        report.append("   - Factual queries should use RAG knowledge base")
        report.append("   - Current system doesn't clearly separate these")
        report.append("")

        # Save detailed results
        results_file = '/home/kloros/diagnostics/rag_test_results.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        report.append(f"**Detailed results saved to:** `{results_file}`")
        report.append("")

except Exception as e:
    print(f"[rag_test] Fatal error: {e}")
    import traceback
    traceback.print_exc()

    report.append("## ❌ CRITICAL ERROR")
    report.append(f"RAG testing failed: {str(e)}")
    report.append("")
    report.append("**Traceback:**")
    report.append("```")
    report.append(traceback.format_exc())
    report.append("```")

# Write report
output_path = '/home/kloros/diagnostics/rag_baseline_report.md'
with open(output_path, 'w') as f:
    f.write('\n'.join(report))

print(f"[rag_test] Report written to {output_path}")
