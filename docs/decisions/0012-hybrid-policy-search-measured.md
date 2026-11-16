# ADR 0012: Policy search is hybrid and reranked, with local models chosen by measurement

- Status: accepted
- Date: 2026-11-16

## Context

The coverage agent (phase 5) must cite the clause of the policy conditions that grounds each
statement, and the rules engine refuses citations that do not exist, belong to another product or
miss the grounding clause (ADR 0008). The agent can only cite what the search hands it, so the
search decides whether the right clause is even on the table.

The corpus is small and structured: 168 clauses in seven products, 15 to 27 per product, written
in legal Spanish. The queries are not: policyholders describe what happened in their own words
("ha reventado el latiguillo de la cisterna"), and a claims handler types terms of art ("hurto",
"artículo 18"). Every search is scoped to the product of the claim's policy. Personal data must
not reach any model (ADR 0011), and everything must run without an API key (ADR 0005); Anthropic
offers no embedding API anyway.

## Options considered

1. **BM25 only** (OpenSearch with a Spanish analyzer). Exact and fast, blind to paraphrase.
2. **Vectors only** (pgvector with a local multilingual embedding model). Handles paraphrase,
   weak on exact terms and references.
3. **Hybrid**: both rankings fused by reciprocal rank (RRF, k = 60), which needs no score
   calibration.
4. **Hybrid plus a cross-encoder reranker** over the fused candidates.

And, for 2 to 4, which local models: four multilingual embedding models and two multilingual
rerankers available as ONNX through fastembed (no PyTorch).

## How it was measured

`make eval-retrieval` (`tramita_agents.evals.retrieval`) with the stack up, the default dataset
(`make data`) and `make index`. Each query is searched within its product; the answer is one
clause. Three query sets, reported apart:

- **Claims** (72 unique descriptions): the answer is the clause that grounds the expected decision
  on the merits, derived from the generated facts (ADR 0007): the exclusion the facts fall under,
  the "not included" clause, or the coverage clause of the guarantee claimed.
- **Questions** (295): 26 templates in everyday Spanish (`evals/retrieval/questions.json`)
  expanded over products and guarantees; a coverage question about a guarantee a product lacks is
  answered by its "not included" clause.
- **Terms** (65): 15 keyword searches copied from the conditions, literal on purpose, measuring
  what lexical search is for.

The metric that matters is **hit@5**: the agent reads the first five clauses. Hit@1 and MRR say
how well they are ordered. Latency is per query, end to end with masking, on a 12-core desktop CPU
in Docker; the CI runner is slower.

## Results

First stage, vector mode only, hit@5 (hit@1 in brackets):

| Embedding model | Size | Claims | Questions | Terms | All 432 | p50 ms |
|---|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 0.22 GB | 79.2% (31.9) | 86.8% (45.1) | 72.3% (44.6) | 83.3% (42.8) | 33 |
| paraphrase-multilingual-mpnet-base-v2 | 1.0 GB | 90.3% (40.3) | 85.8% (50.2) | 63.1% (29.2) | 83.1% (45.4) | 48 |
| **jina-embeddings-v2-base-es** | 0.64 GB | 87.5% (45.8) | **95.6%** (67.5) | 72.3% (43.1) | **90.7%** (60.2) | 55 |
| multilingual-e5-large | 2.24 GB | 87.5% (66.7) | 88.1% (72.2) | 100% (64.6) | 89.8% (70.1) | 103 |

Each mode with jina-embeddings-v2-base-es, hit@5 (hit@1), ten candidates per stage:

| Mode | Claims | Questions | Terms | All 432 | p50 ms |
|---|---|---|---|---|---|
| Lexical (BM25) | 51.4% (40.3) | 53.9% (23.1) | **100%** (89.2) | 60.4% (35.9) | 9 |
| Vector | 87.5% (45.8) | **95.6%** (67.5) | 72.3% (43.1) | 90.7% (60.2) | 55 |
| Hybrid (RRF) | 83.3% (58.3) | 86.8% (51.5) | 96.9% (76.9) | 87.7% (56.5) | 57 |
| **Hybrid + bge-reranker-v2-m3 (int8)** | **91.7%** (62.5) | 90.2% (70.5) | **100%** (100) | **91.9%** (73.6) | 1,503 |
| Hybrid + bge-reranker-v2-m3, 20 candidates | 93.1% (50.0) | 90.2% (70.5) | 100% (100) | 92.1% (71.5) | 3,032 |
| Hybrid + jina-reranker-v2-base-multilingual, 20 | 69.4% (31.9) | 93.9% (64.8) | n/m | n/m | 1,897 |
| Same as chosen, with multilingual-e5-large embeddings | 95.8% (61.1) | 90.5% (70.9) | 100% (100) | 92.8% (73.6) | 1,616 |

(n/m: not measured; that run predates the terms set.)

What the numbers say:

- **Each first stage has a blind spot.** BM25 finds every keyword search but only half of the
  everyday questions and claims: many share no word with the legal text ("latiguillo",
  "papeles"), and on average it returns six of a product's clauses. The vectors are the reverse:
  95.6% of the questions, 72.3% of the keyword searches.
- **Fusion alone does not pay.** RRF gives BM25's confident but wrong first places too much
  weight, so the hybrid ranking is below the vector ranking on everyday language. Its value is
  the candidate pool: both stages' best clauses reach the reranker.
- **The reranker turns the pool into the best ordering overall**, with no weak set: 100% of the
  keyword searches (hit@1 too), 91.7% of the claims, 90.2% of the questions. It costs 1.5 s per
  query on CPU. On questions it ranks 5 points lower at hit@5 than the vectors alone, which is
  the price of being right on the other two sets.
- **Ten candidates beat twenty**: half the time, the same hit@5 within one query, and a better
  first place on claims (fewer near-duplicates to confuse the reranker).
- The Jina reranker was worse than no reranker on claims and was dropped.
- **e5-large under the same reranker is slightly better**: 4 more of 432 queries at hit@5 (3 of
  them claims), the same hit@1. It weighs 2.24 GB against 0.64 GB, embeds twice as slowly, and
  every fresh clone and CI cache would download it. The gain is small next to the run-to-run
  spread between machines (below), so the lighter model stays the default and e5-large is a
  configuration change away.

## Decision

Option 4, with:

- **Lexical**: OpenSearch index `policy-clauses`, Spanish light stemmer and stop words then ASCII
  folding, BM25 over title (weight 2), text, article and product name, filtered by product.
- **Vectors**: `jinaai/jina-embeddings-v2-base-es` in the agent service's own schema
  `policy_search` in PostgreSQL, keyed by model; an exact cosine scan (a few hundred rows; an
  approximate index would only lose recall).
- **Fusion**: RRF over ten candidates from each stage.
- **Reranking**: `BAAI/bge-reranker-v2-m3` quantised to int8, over the fused ten.
- **Masking first**: the query is masked like a document before any backend or model sees it.
- **Traceable hits**: each hit keeps its lexical, vector and fused rank and its rerank score.
- **Gate in CI**: the fast modes on every set and the reranker on claims and terms, against
  hit@5 floors a few points under these measurements.

Models are configuration (`TRAMITA_EMBEDDING_MODEL`, `TRAMITA_RERANKER_MODEL`,
`TRAMITA_SEARCH_CANDIDATES`); an empty reranker turns the second stage off.

## Consequences

- The agents get the grounding clause among five in about 92% of the queries measured, and every
  keyword search right first; the citation check in the core (ADR 0008) still catches the rest.
- About 1.5 s per search on a desktop CPU, more on a small runner. Fine for a claims pipeline
  that runs in the background; an interactive tool would want a GPU or a smaller reranker.
- About 1.2 GB of models are downloaded once into `models-cache/` (cached in CI).
- ONNX Runtime gives slightly different scores on different CPUs, so near ties can flip: the
  reranked claims and terms scored 95.6% hit@5 locally and 96.4% on the CI runner (one query).
  The gate floors leave room for that.
- The evaluation is synthetic. The questions and keyword searches were written by the same
  author as the system, from the conditions; the claims come from the generator's templates
  (72 unique descriptions for 150 claims). Real policyholder text would be messier, and the
  numbers should be read as a comparison between options, not as production accuracy.
- "The answer" is a single clause, but for a covered claim the limits, exclusions and documents
  of the same guarantee are useful too. Hit@1 is therefore a strict measure; hit@5 is the one the
  agents depend on.
- Choosing among options with the same queries the gate checks risks fitting the evaluation.
  The choices were few and coarse (four models, two rerankers, two candidate counts), and no
  parameter was tuned query by query; RRF's k stayed at the published 60.
