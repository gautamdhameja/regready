# AGENTS.md: EU Digital Regulation RAG + MCP

## What this project is

A retrieval system over five EU digital regulations, with a evaluation comparing three ways of answering questions.
The system finds and cites the relevant provisions for a question. It does not give legal advice and must never present output as legal advice.

## Corpus (version 1)

English only. Source: EUR-Lex exclusively (eur-lex.europa.eu), HTML format.

| Act | Reference | CELEX |
|---|---|---|
| AI Act | Regulation (EU) 2024/1689 | 32024R1689 |
| GDPR | Regulation (EU) 2016/679 | 32016R0679 |
| DORA | Regulation (EU) 2022/2554 | 32022R2554 |
| NIS2 | Directive (EU) 2022/2555 | 32022L2555 |
| Data Act | Regulation (EU) 2023/2854 | 32023R2854 |

Versioning rules:

- The AI Act was amended by the Digital Omnibus on AI (OJ L 2026/1744, in force 27 July 2026). Use the consolidated text if EUR-Lex provides one; otherwise index the original plus the amending act.
- GDPR and Data Act amendments under the broader Digital Omnibus were still in negotiation as of August 2026. Index current texts and record that they may change.
- Consolidated EUR-Lex texts are documentation, not legally binding. Note this in the corpus record.
- Every document carries: source URL, original or consolidated, version date, download date.

Out of scope for version 1: official guidance (EDPB, Commission guidelines), case law, national implementing laws, other languages.

## Approach

The pipeline follows standard production RAG practice:

1. **Questions first.** A hand-written eval set defines success before any code. Question types: provision lookup, definition, exact identifier, date or version-sensitive, cross-act, unanswerable.
2. **Parsing.** Preserve legal structure: chapter, article, paragraph, point, recital, annex. Keep cross-references ("Article 6(1)", "Annex III") as data.
3. **Chunking.** Structure-aware, aligned to legal units. Each chunk carries its full citation path and metadata (act, article, version date).
4. **Indexing.** Dense embeddings plus BM25. Legal identifiers need keyword search.
5. **Retrieval.** Hybrid search with metadata filters, merged with reciprocal rank fusion.
6. **Reranking.** Tested with and without; candidate depth tuned on the eval set.
7. **Generation.** Answers grounded only in retrieved provisions, with citations, and explicit abstention when the corpus does not answer the question.
8. **MCP server.** Retrieval exposed as a small set of well-defined tools (search, fetch provision, resolve cross-reference).
9. **Experiment.** The same eval set run through three modes:
   - Classic RAG: retrieve once, then answer.
   - Agentic: the model uses the MCP tools freely.
   - Hybrid: retrieval up front plus tools for follow-up.

Every component change is judged against the eval set. Keep a change only if the numbers support it.

## Evaluation principles

- Measure per stage: retrieval (recall@k, MRR, nDCG), then generation (faithfulness, correctness, citation accuracy, correct abstention).
- Break results down by question type, never only averages.
- Any LLM judge is validated against the developer's own labels before it is trusted.
- Report cost and latency per mode next to quality.
- Record failures and dropped approaches. They belong in the write-up.

## Stack

- Python.
- Hosted APIs for embeddings, reranking and the LLM. Specific models are chosen by evaluation, not fixed in advance.
- Store the model name and version with every vector. Never mix vectors from different models in one index.

## Writing conventions

For all docs, comments and reports in this repo: plain, direct, short sentences. No em dashes. No filler or hype.
Use Google's recommended documentation best practices and guidelines.
