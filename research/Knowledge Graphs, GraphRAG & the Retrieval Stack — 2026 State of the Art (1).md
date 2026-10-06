# Knowledge Graphs, GraphRAG & the Retrieval Stack for Enterprise Agents — State of the Art, September 2026

**Research date:** 2026-09-12 · **Scope:** graph databases, GraphRAG frameworks, vector databases, embeddings/rerankers, document ingestion, ontology & semantic layer, plus agentic-RAG patterns, chunking, and evaluation.

**Grounding rule applied throughout:** every value below was taken from a page fetched during this research session, and the exact source URL sits next to the value. Where a value could not be confirmed from a fetched page, the cell reads `n.a.` rather than an estimate. Vendor-published benchmarks are labelled as such — they are marketing claims, not independent measurements.

---

## 0. Executive summary

1. **The "graph vs. vector" debate is over; the answer is both, but asymmetrically.** Independent analysis finds graph-based retrieval delivers a **4.5% improvement in reasoning depth on HotpotQA multi-hop questions** but is **2.3× higher latency on average**, and on Natural Questions GraphRAG scored **13.4% lower accuracy** than vanilla RAG, with a **16.6% accuracy drop** on time-sensitive queries ([When to use Graphs in RAG, arXiv 2506.05690](https://arxiv.org/html/2506.05690v1)). Graphs win on multi-hop and global/thematic questions; they lose on single-fact lookup and freshness. Architect accordingly: vector-first with graph as a second-stage expansion.
2. **The cheapest big win is not a graph — it is contextual retrieval plus reranking.** Anthropic measured top-20 retrieval failure rate dropping from 5.7% to 3.7% with contextual embeddings (**−35%**), to 2.9% with contextual BM25 added (**−49%**), and to 1.9% with reranking on top (**−67%**), at a one-time cost of **$1.02 per million document tokens** ([Anthropic Engineering](https://www.anthropic.com/engineering/contextual-retrieval)). That is a larger, more reliable delta than most GraphRAG deployments achieve, for a fraction of the build cost.
3. **Cost of GraphRAG has been the blocker, and 2025–2026 fixed part of it.** Microsoft's LazyGraphRAG removes up-front source-text summarization entirely and uses best-first + breadth-first iterative deepening with a tunable relevance-test budget (100/500/1500) ([Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)).
4. **Embedded graph is now a risk area.** Kùzu was **archived on 10 Oct 2025** at v0.11.3, and Apple agreed on **9 Oct 2025 to acquire Kùzu Inc.** ([GitHub](https://github.com/kuzudb/kuzu), [PuppyGraph analysis](https://www.puppygraph.com/blog/what-is-kuzudb)). Anyone who standardised on Kuzu for local/embedded KG work needs a migration plan.
5. **GQL is real and now maintained.** ISO/IEC 39075:2024 was published 12 Apr 2024 ([Wikipedia/GQL](https://en.wikipedia.org/wiki/Graph_Query_Language)) and **Technical Corrigendum 1 was published 30–31 Jul 2026** (21 pages, clarifying catalog structure, conformance rules, node/edge type label syntax, error reporting and temporal types) ([ISO/IEC 39075:2024/Cor 1:2026](https://standards.iteh.ai/catalog/standards/iso/e9bee956-a206-4886-bbc7-97c3684e6f76/iso-iec-39075-2024-cor-1-2026), [IEC Webstore](https://webstore.iec.ch/en/publication/115503)).
6. **For Vietnamese-language enterprise documents, parsing — not embedding — is the bottleneck.** The new ViDocParse benchmark (11,439 Vietnamese page images, 9 categories, 7 OCR/VLM systems) finds **no single model dominates**, with persistent failures in column merging, table omission and inline-formula boundary drift, driven by tone/vowel diacritics and dense multi-column layouts ([ViDocParse, ACL ARR 2026](https://openreview.net/forum?id=Vkeag2cpRN)).

---

## A. Graph databases

| Product | Latest version / date | License | Query language | Vector index | GraphRAG tooling | Managed offering | Weaknesses |
|---|---|---|---|---|---|---|---|
| **Neo4j** | **2026.08.1, released 10 Sep 2026**; LTS line 5.26.30 (26 Aug 2026) ([release notes](https://neo4j.com/release-notes/database/)) | Community Edition **GPL v3**; Enterprise requires a **commercial subscription**; free Startup License for firms ≤50 employees; free Developer/Evaluation licenses ([Neo4j Licensing](https://neo4j.com/licensing/)) | Cypher; **Cypher 25** adds a `SEARCH` clause ([graphrag-python](https://github.com/neo4j/neo4j-graphrag-python)) | Yes — `create_vector_index` in the official GraphRAG package; also supports external stores Weaviate/Pinecone/Qdrant ([GitHub](https://github.com/neo4j/neo4j-graphrag-python)) | **neo4j-graphrag-python 1.19.0 (26 Aug 2026), Apache-2.0**, incl. `SimpleKGPipeline` (requires APOC) ([GitHub](https://github.com/neo4j/neo4j-graphrag-python), [docs](https://neo4j.com/developer/genai-ecosystem/graphrag-python/)); plus LLM Knowledge Graph Builder ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) | **Neo4j Aura**: AuraDB (Free / Professional / Business Critical / Virtual Dedicated Cloud), AuraDS (Professional / Enterprise), Aura Graph Analytics ([Aura docs](https://neo4j.com/docs/aura/)) | GPLv3 Community forces commercial licensing for closed-source Enterprise use ([licensing](https://neo4j.com/licensing/)); "Aura Agent" not documented on the Aura docs landing page (`n.a.`) |
| **FalkorDB** | **v4.18.11, 24 Jun 2026** per repo landing page ([GitHub](https://github.com/FalkorDB/FalkorDB)); the releases feed also listed v4.12.4 on 24 Aug ([releases](https://github.com/FalkorDB/FalkorDB/releases)) — treat version as needing confirmation at deploy time | **Server Side Public License v1 (SSPLv1)** ([GitHub](https://github.com/FalkorDB/FalkorDB), [docs](https://docs.falkordb.com/)) | Cypher (OpenCypher-style) ([docs](https://docs.falkordb.com/)) | **Yes** — full-text, vector and range indexes combinable in one engine; vector similarity search ([docs](https://docs.falkordb.com/)) | **GraphRAG-SDK** with automated ontology generation from unstructured data, ontology management, built-in agent orchestration ([falkordb.com](https://www.falkordb.com/), [docs](https://docs.falkordb.com/)) | **FalkorDB Cloud** — fully managed, multi-tenant, free instance tier ([docs](https://docs.falkordb.com/)) | SSPLv1 is not OSI-approved and blocks SaaS resale; positions "10K+ multi-graphs (tenants)" but Redis-based architecture ([falkordb.com](https://www.falkordb.com/)) |
| **Memgraph** | **v3.13.0, 9 Sep 2026** ([release notes](https://memgraph.com/docs/release-notes)) | `n.a.` (not stated on pages fetched); note **`cross_database` is Enterprise-only** as of 3.13 ([release notes](https://memgraph.com/docs/release-notes)) | Cypher ([release notes](https://memgraph.com/docs/release-notes)) | **Yes, strongest in class** — vector indexes on **nodes and edges**, multi-label and wildcard label filters, quantization; **Single Store Vector Index** cut vector memory ~**85%** in 3.8 ([3.13 notes](https://memgraph.com/docs/release-notes), [3.8 release](https://memgraph.com/blog/memgraph-3-8-release-atomic-graphrag-vector-single-store-parallel-runtime)) | **"Atomic GraphRAG"** shipped in 3.8 (12 Feb 2026); **Leiden** community detection for GraphRAG ([3.8 release](https://memgraph.com/blog/memgraph-3-8-release-atomic-graphrag-vector-single-store-parallel-runtime), [release notes](https://memgraph.com/docs/release-notes)) | `n.a.` | In-memory-first design implies RAM cost; feature gating moving toward Enterprise ([release notes](https://memgraph.com/docs/release-notes)) |
| **Kuzu** | **ARCHIVED 10 Oct 2025; last release v0.11.3** ([GitHub](https://github.com/kuzudb/kuzu)) | **MIT** ([GitHub](https://github.com/kuzudb/kuzu)) | Cypher ([GitHub](https://github.com/kuzudb/kuzu)) | Yes — disk-based **HNSW** vector index since 0.9.0 (Apr 2025), NaviX VLDB paper ([GitHub](https://github.com/kuzudb/kuzu)) | Community integrations only; project archived | None — **Apple agreed on 9 Oct 2025 to acquire Kùzu Inc.**, disclosed in a Feb 2026 EU DMA filing ([PuppyGraph](https://www.puppygraph.com/blog/what-is-kuzudb)) | **Discontinued.** Embedded-only, no HA/distributed mode; community forks exist but no vendor support ([PuppyGraph](https://www.puppygraph.com/blog/what-is-kuzudb)) |
| **NebulaGraph** | OSS **v3.8.0**; Enterprise **v5.3 (6 Jul 2026)**, marketed as "Graph-Native Intelligence for the Ontology-Driven AI Era" ([downloads](https://www.download.nebula-graph.io/), [posts](https://nebula-graph.io/posts)) | OSS **Apache 2.0**; Enterprise commercial ([downloads](https://www.download.nebula-graph.io/)) | **nGQL + openCypher + ISO-GQL compatibility**; Enterprise **v5.0 claimed as first distributed DB with native GQL** ([downloads](https://www.download.nebula-graph.io/)) | `n.a.` for OSS 3.8 from fetched pages | **LightRAG support added 20 Aug 2026** ([posts](https://nebula-graph.io/posts)) | `n.a.` | Two-tier split: GQL and the ontology/AI features land in Enterprise first ([posts](https://nebula-graph.io/posts)) |
| **Amazon Neptune** | Serverless managed service, no public semver on product page ([AWS](https://aws.amazon.com/neptune/)) | Proprietary managed service | openCypher, Gremlin, SPARQL per product positioning ([AWS](https://aws.amazon.com/neptune/)) | **Yes** — vector search in Neptune Analytics ([AWS](https://aws.amazon.com/neptune/)) | **Fully managed GraphRAG GA via Amazon Bedrock Knowledge Bases + Neptune Analytics** ([AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/announcing-general-availability-of-amazon-bedrock-knowledge-bases-graphrag-with-amazon-neptune-analytics/)); **Strands Agents SDK** integration ([AWS](https://aws.amazon.com/neptune/)) | Native AWS managed; Neptune Analytics **GA in additional regions Jan 2026** ([AWS What's New](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-neptune-analytics-generally-available-additional-regions/)) | AWS lock-in; scale ceilings **128 TiB/cluster, 15 read replicas, 100k+ QPS** ([AWS](https://aws.amazon.com/neptune/)) |
| **TigerGraph** | **DB 4.2.5 (2 Sep 2026)**; 4.3.0-rc1 preview (8 Jul 2026) ([docs home](https://www.tigergraph.com/docs/home/)) | Commercial (Enterprise); no OSS license found on fetched pages — `n.a.` | **GSQL + openCypher** ([docs home](https://www.tigergraph.com/docs/home/)) | **Yes** — graph + vector **hybrid search** ([docs home](https://www.tigergraph.com/docs/home/)) | **TigerGraph GraphRAG v2.0, released 1 Jul 2026**: agentic chat, MCP tools, structure-aware chunking ([graphwiz](https://graphwiz.ai/content/graphs/tigergraph-graphrag-v2-agentic-mcp/)); GraphRAG Python libraries ([docs home](https://www.tigergraph.com/docs/home/)) | **TigerGraph Savanna** ([docs home](https://www.tigergraph.com/docs/home/)) | Proprietary; enterprise-integration features (mTLS, Kerberos SSO, NULL support, Iceberg connector) only arrived in **4.3 on 15 Jul 2026** ([TigerGraph blog](https://www.tigergraph.com/blog/tigergraph-4-3-built-for-enterprise-security-integration-and-scale/)) |
| **Apache AGE (PostgreSQL)** | **1.7.0 for PostgreSQL 18**; 1.6.0 for PG 14–17 ([downloads](https://age.apache.org/download/)) | Apache License 2.0 (ASF project) | openCypher inside SQL ([downloads](https://age.apache.org/download/)) | Not native — use **pgvector** in the same Postgres ([pgvector 0.8.2](https://www.postgresql.org/about/news/pgvector-082-released-3245/)) | `n.a.` | `n.a.` (depends on Postgres host) | Version follows Postgres majors; no built-in graph algorithm/GraphRAG suite found on fetched pages |
| **ArangoDB** | **3.12.10.1, 12 Aug 2026** ([EOL wiki](https://www.eol.wiki/arangodb/)) | From 3.12.5 the **Community Edition includes all Enterprise features but is free for non-commercial use only, capped at 100 GB of data, with no commercial use or embedding rights** ([arango.ai downloads](https://arango.ai/downloads/)) | AQL | `n.a.` from fetched pages | `n.a.` | `n.a.` | **The 2024–25 license change is the story**: effectively no free commercial tier; 3.11/3.10 reached **EOL 30 May 2025** ([arango.ai](https://arango.ai/downloads/), [EOL wiki](https://www.eol.wiki/arangodb/)) |

### GQL / ISO standard status

| Item | Status |
|---|---|
| ISO/IEC 39075:2024 (GQL) | **Published 12 Apr 2024**, stage 60.60, developed by ISO/IEC JTC 1/SC 32/WG 3, influenced by SQL, Cypher and GSQL ([Wikipedia](https://en.wikipedia.org/wiki/Graph_Query_Language)) |
| Technical Corrigendum 1 | **ISO/IEC 39075:2024/Cor 1:2026 — published 30 Jul 2026, released 31 Jul 2026, effective 07 Jan 2026, stage 6060, 21 pages, English, first edition** ([iTeh/ISO catalog](https://standards.iteh.ai/catalog/standards/iso/e9bee956-a206-4886-bbc7-97c3684e6f76/iso-iec-39075-2024-cor-1-2026), [IEC Webstore](https://webstore.iec.ch/en/publication/115503)) |
| What Cor 1 changes | Aligns catalog-structure diagrams with normative text; clarifies GQL-environments/catalogs/directories/schemas; refines conformance rules and conditional feature dependencies; clarifies node-type and edge-type label definition syntax, property type identification, execution outcomes, error reporting, partial results, and handling of list/numeric/temporal values ([ISO catalog](https://standards.iteh.ai/catalog/standards/iso/e9bee956-a206-4886-bbc7-97c3684e6f76/iso-iec-39075-2024-cor-1-2026)) |
| First distributed native-GQL claim | NebulaGraph Enterprise v5.0 ([downloads](https://www.download.nebula-graph.io/)) |

**Practical read:** Cypher remains the de-facto dialect (Neo4j, Memgraph, FalkorDB, Kuzu, AGE, plus openCypher in TigerGraph/Neptune/NebulaGraph). GQL conformance is still a vendor talking point rather than a portability guarantee — write your traversal layer behind an abstraction.

---

## B. GraphRAG frameworks

| Framework | Version / date | License | Approach | Benchmark evidence | Cost & latency concerns |
|---|---|---|---|---|---|
| **Microsoft GraphRAG** | GraphRAG 1.0 shipped Dec 2024; project adds DRIFT Search, auto-tuning, **BenchmarkQED**, **VeriTrail** ([MSR project](https://www.microsoft.com/en-us/research/project/graphrag/)) | `n.a.` on fetched pages (repo license not fetched) | Entity–relation extraction → community detection → **community summaries**; global + local + DRIFT search ([MSR](https://www.microsoft.com/en-us/research/project/graphrag/)) | Microsoft reports **+26% comprehensiveness and +57% diversity** vs vanilla RAG (vendor claim, via third-party summary) ([Merciv](https://www.merciv.com/blog/graphrag-vanilla-rag-comparison)) | Up-front indexing of the whole corpus is the dominant cost; third-party analysis puts GraphRAG at roughly **2.3× slower** ([Merciv](https://www.merciv.com/blog/graphrag-vanilla-rag-comparison), [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1)) |
| **LazyGraphRAG** (Microsoft) | Editor's note dated **6 Jun 2025**; integrated into **Microsoft Discovery** and **Azure Local (preview)** ([MSR blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) | `n.a.` | **No up-front source-text summarization**; defers LLM work to query time using best-first + breadth-first **iterative deepening** with a **relevance-test budget (100 / 500 / 1500)** ([MSR blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) | Evaluated on **5,590 AP news articles** with **100 synthetic queries (50 local, 50 global)** scored on **comprehensiveness, diversity, empowerment** ([MSR blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) | Designed explicitly to attack GraphRAG's indexing cost; query-time cost scales with the relevance-test budget ([MSR blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) |
| **LightRAG** | **v1.5.7, 2 Sep 2026**; EMNLP 2025 paper ([GitHub](https://github.com/HKUDS/LightRAG)) | **MIT** ([GitHub](https://github.com/HKUDS/LightRAG)) | Dual-level retrieval — modes `local`, `global`, `hybrid`, `naive`, `mix` (default **mix**); **no community report generation** ([GitHub](https://github.com/HKUDS/LightRAG)) | Win-rate vs NaiveRAG (author-reported): **Legal 84.8% vs 15.2%**, **Agriculture 67.6 vs 32.4**, **CS 61.2 vs 38.8**, **Mix 60 vs 40** ([GitHub](https://github.com/HKUDS/LightRAG)) | Much cheaper to index than community-summary GraphRAG because it skips community reports ([GitHub](https://github.com/HKUDS/LightRAG)); now supported natively by NebulaGraph ([NebulaGraph posts](https://nebula-graph.io/posts)) |
| **HippoRAG 2** | arXiv **2502.14802**, v2 revised **19 Jun 2025** ([arXiv](https://arxiv.org/abs/2502.14802)) | `n.a.` | Neurobiologically-inspired memory: **Personalized PageRank** over an open KG plus deeper passage integration ([arXiv](https://arxiv.org/abs/2502.14802)) | Paper: **+7% on associative memory tasks vs the SOTA embedding model** ([arXiv](https://arxiv.org/abs/2502.14802)). Third-party aggregation: **59.8 average F1 vs 57.0 for NV-Embed-v2 across 7 benchmarks** ([memorypapers.org](https://memorypapers.org/papers/hipporag-2-rag-to-memory)) | PPR over the full graph per query adds retrieval-time compute; gains are concentrated in associative/multi-hop questions ([arXiv](https://arxiv.org/abs/2502.14802)) |
| **nano-graphrag** | **v0.0.8 (Oct 2024)**; last commit Jan 2026 ([GitHub](https://github.com/gusye1234/nano-graphrag)) | **MIT** ([GitHub](https://github.com/gusye1234/nano-graphrag)) | ~**1,100 lines of code** reimplementation of MS GraphRAG: community reports, **top-K communities (default 512)** ([GitHub](https://github.com/gusye1234/nano-graphrag)) | `n.a.` | Minimal maintenance since Oct 2024; best treated as a readable reference implementation, not production infrastructure ([GitHub](https://github.com/gusye1234/nano-graphrag)) |
| **Graphiti (Zep)** | **v0.30.2, 8 Sep 2026** ([GitHub](https://github.com/getzep/graphiti)) | **Apache-2.0** ([GitHub](https://github.com/getzep/graphiti)) | **Temporal / bi-temporal** knowledge graph: validity windows, episodes with provenance, prescribed **and** learned ontology defined via **Pydantic** models ([GitHub](https://github.com/getzep/graphiti)) | Placed at **"Trial"** on the Thoughtworks Technology Radar (Apr 2026) ([Thoughtworks](https://www.thoughtworks.com/en-us/radar/platforms/graphiti)) | Requires a model with reliable structured output — **small models fail structured extraction** ([GitHub](https://github.com/getzep/graphiti)) |
| **Cognee** | **1.0 released 26 Jun 2026**; releases through **v1.5.4** ([announcement](https://www.cognee.ai/cognee-1-0-announcement), [releases](https://github.com/topoteretes/cognee/releases)) | `n.a.` on fetched pages | Memory primitives **remember / recall / improve / forget**; Rust core; **runs on a single Postgres with no graph DB required**; COGX export ([announcement](https://www.cognee.ai/cognee-1-0-announcement)) | **BEAM: 79% at 100k context vs 73.4% SOTA; 67% at 10M context vs 64.1%**, with roughly flat token usage as context grows (vendor-reported) ([announcement](https://www.cognee.ai/cognee-1-0-announcement)) | Vendor-run benchmark; single-Postgres mode is the cost story ([announcement](https://www.cognee.ai/cognee-1-0-announcement)) |
| **LlamaIndex PropertyGraphIndex** | Current framework module (no separate version on page) ([docs](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)) | `n.a.` | Pluggable `kg_extractors` — `SimpleLLMPathExtractor`, `ImplicitPathExtractor`, `DynamicLLMPathExtractor`, `SchemaLLMPathExtractor`; retrievers — `LLMSynonymRetriever`, `VectorContextRetriever`, `TextToCypherRetriever`, `CypherTemplateRetriever` ([docs](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)) | `n.a.` | Cost is driven by which extractor you pick: schema-constrained extraction is far cheaper and more stable than dynamic extraction ([docs](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)) |
| **LangChain graph transformers** | Used as `llm-graph-transformer` inside Neo4j's builder ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) | `n.a.` | LLM-driven extraction of nodes/relationships into a property graph ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) | `n.a.` | `n.a.` |
| **Neo4j LLM Knowledge Graph Builder** | Neo4j Labs GenAI ecosystem project ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) | `n.a.` | Builds a **lexical graph + entity graph**; query modes **GraphRAG / Vector / Text2Cypher**; React + FastAPI, deployed on Cloud Run; uses `llm-graph-transformer` ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) | `n.a.` | Documented as **best for long-form English text and poor for tabular Excel/CSV, images and slides** ([Neo4j Labs](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)) |

### Does GraphRAG actually beat vanilla RAG? The 2026 evidence

The honest answer from the independent literature is **"only on the right question types."**

| Finding | Number | Source |
|---|---|---|
| GraphRAG vs vanilla RAG, Natural Questions | **13.4% lower accuracy** for GraphRAG | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| Time-sensitive NQ queries needing real-time knowledge updates | **16.6% accuracy drop** | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| Graph retrieval on HotpotQA multi-hop | **+4.5% reasoning depth** | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| Graph retrieval latency | **2.3× higher on average** | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| GraphRAG-Bench (Novel), Fact Retrieval ACC | RAG without rerank **58.76**, RAG with rerank **60.92** — i.e. a plain reranker beats many graph pipelines on Level-1 facts | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| GraphRAG-Bench (Novel), Complex Reasoning ACC | RAG w/o rerank **41.35**, w/ rerank **42.93** (ROUGE-L 15.12 / 15.39) | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| GraphRAG-Bench (Novel), Contextual Summarize | RAG w/o rerank ACC **50.08** / Cov **82.53**; w/ rerank ACC **51.30** / Cov **83.64** | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |
| GraphRAG-Bench (Novel), Creative Generation | RAG w/o rerank ACC **41.52**, FS **47.46**, Cov **37.84** | [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1) |

**GraphRAG-Bench** structures evaluation into four increasing-difficulty levels — **Fact Retrieval, Complex Reasoning, Contextual Summarization, Creative Generation** — with metrics Accuracy/ROUGE-L (L1–L2), Accuracy/Coverage (L3) and Accuracy/Factual Score/Coverage (L4), across two domain leaderboards (**Novel** and **Medical**) ([GraphRAG-Bench repo](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)). A 2026 survey of variants (Deep GraphRAG, CatRAG, ParallaxRAG, TagRAG, LeanRAG) reports the benchmark at **ICLR 2026 with 1,018 college-level questions across 16 CS disciplines** ([graphwiz](https://graphwiz.ai/graphrag-variants-compared-2026/)).

**Design rule this implies:** route by question type. Send single-fact and time-sensitive queries to hybrid vector+BM25+rerank. Send multi-hop, relationship and global-summary queries to the graph. Never make the graph the only path.

---

## C. Vector databases & search engines

| System | Latest version / date | License | Hybrid search (BM25 + dense) | Multi-tenancy | Filtering | Quantization | Managed / self-host | Benchmark signals |
|---|---|---|---|---|---|---|---|---|
| **Qdrant** | **v1.19.1, 4 Sep 2026** ([GitHub](https://github.com/qdrant/qdrant)) | **Apache-2.0** ([GitHub](https://github.com/qdrant/qdrant)) | Yes — dense + sparse with **RRF and DBSF** fusion, **BM25 with IDF modifier, miniCOIL, SPLADE**, formula queries, multivector/ColBERT ([GitHub](https://github.com/qdrant/qdrant), [hybrid search article](https://qdrant.tech/articles/hybrid-search/)) | Yes, native multitenancy ([GitHub](https://github.com/qdrant/qdrant)) | Payload filtering with payload indexes ([GitHub](https://github.com/qdrant/qdrant)) | Yes — **up to 97% RAM reduction** ([GitHub](https://github.com/qdrant/qdrant)) | **Qdrant Cloud** + self-host + **Qdrant Edge** ([GitHub](https://github.com/qdrant/qdrant)) | Vendor-documented quantization/RAM figures above; no independent benchmark on fetched pages |
| **Milvus / Zilliz** | **v3.0.1, 9 Sep 2026** ([release notes](https://milvus.io/docs/release_notes.md)) | **Apache 2.0** for Milvus 3.0 ([Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)) | Yes — native **TEXT fields + BM25**, **SINDI** sparse index, **Block-Max WAND / MaxScore**, weighted **RRF**, function-chain reranking ([release notes](https://milvus.io/docs/release_notes.md)) | Yes (collections/partitions/databases); **per-entity TTL** new in 3.0 ([release notes](https://milvus.io/docs/release_notes.md)) | Yes, with server-side **sort/aggregate/facet** ([Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)) | `n.a.` explicit ratio | **Zilliz Cloud "Vector Lakebase"** (May 2026) ([changelog](https://docs.zilliz.com/docs/changelogs)) | **Lake-native** architecture: `StructList` multi-vector for ColBERT/ColPali, **External Collections over Lance/Iceberg/Parquet/Vortex** ([Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)) |
| **Weaviate** | **1.39.x, first release 2026-08-04**; 1.39 feature post 28 Aug 2026 ([release notes](https://docs.weaviate.io/weaviate/release-notes), [newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) | `n.a.` on fetched pages | Yes (hybrid is a core primitive; see effort-tier numbers) ([newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) | Yes (tenants) — `n.a.` detail from fetched pages | Yes — **Boost API + MMR GA** in 1.39 ([newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) | **4-bit rotational quantization (preview): 1536-dim vector → 784 bytes, 7.84× smaller** ([newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) | Weaviate Cloud + self-host; auto **HNSW snapshots** in 1.39 ([newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) | **Search effort tiers on BRIGHT Biology: 57.5 nDCG@10 at "ultrahigh" vs 13.0 for plain hybrid**; and notably **rerankers lose recall beyond ~100 documents** ([newsletter](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) |
| **pgvector** | **0.8.2, 26 Feb 2026 — security release fixing CVE-2026-3172**, a buffer overflow in parallel HNSW builds ([PostgreSQL news](https://www.postgresql.org/about/news/pgvector-082-released-3245/)) | PostgreSQL-style license (extension) — `n.a.` exact string on fetched page | Via Postgres FTS/`tsvector` + pgvector (composable, not built-in fusion) | Postgres-native (schemas/RLS) | Full SQL `WHERE` filtering | Via **pgvectorscale SBQ** ([GitHub](https://github.com/timescale/pgvectorscale)) | Self-host anywhere Postgres runs; every managed Postgres | **Patch immediately** — 0.8.2 is a CVE fix, not a feature release ([PostgreSQL news](https://www.postgresql.org/about/news/pgvector-082-released-3245/)) |
| **pgvectorscale** | **0.9.1, 4 Sep 2026** ([GitHub](https://github.com/timescale/pgvectorscale)) | **PostgreSQL License** ([GitHub](https://github.com/timescale/pgvectorscale)) | Inherits Postgres | Postgres-native | **Label-based filtering via smallint ranges** ([GitHub](https://github.com/timescale/pgvectorscale)) | **SBQ (statistical binary quantization)** ([GitHub](https://github.com/timescale/pgvectorscale)) | Self-host / Tiger Cloud | **StreamingDiskANN** index ([GitHub](https://github.com/timescale/pgvectorscale)) |
| **Pinecone** | API version **2026-07**; **full-text search + Documents API GA 2026-09-02** ([release notes](https://docs.pinecone.io/release-notes/2026)) | Proprietary, managed-only (+ **BYOC on Enterprise**) ([release notes](https://docs.pinecone.io/release-notes/2026)) | Yes — **BM25 + Lucene `query_string` + dense + sparse scoring**, `$match_phrase`, fuzzy matching, ngram substring search ([release notes](https://docs.pinecone.io/release-notes/2026)) | **Namespaces** — Starter allows 100 namespaces per index ([pricing](https://www.pinecone.io/pricing/)) | Metadata filtering | `n.a.` | Managed SaaS; **Terraform provider v4.0.0 (1 Aug 2026)** ([release notes](https://docs.pinecone.io/release-notes/2026)) | Starter limits: **2 GB, 5 indexes, 100 namespaces/index**; Enterprise **99.95% SLA** ([pricing](https://www.pinecone.io/pricing/)). Note reranker churn: **cohere-rerank-3.5 deprecated 1 Jul 2026**, traffic served by **cohere-rerank-4-fast since 31 Aug 2026** ([model page](https://docs.pinecone.io/models/cohere-rerank-3.5)) |
| **LanceDB** | **v0.39.0-beta.6 (8 Sep 2026)**; **v0.38.0 stable** ([releases](https://github.com/lancedb/lancedb/releases)) | `n.a.` on fetched pages | Yes — **FTS** built in, **FTS v2 now default** in Lance ([releases](https://github.com/lancedb/lancedb/releases), [newsletter](https://www.lancedb.com/blog/newsletter-july-2026)) | **Namespaces** ([releases](https://github.com/lancedb/lancedb/releases)) | Yes | `n.a.` | Embedded/self-host + LanceDB Cloud | **Materialized views** added; Lance format at **v8.0.0/v9.0.0** ([newsletter](https://www.lancedb.com/blog/newsletter-july-2026)) |
| **Vespa** | **8.738 / 8.748.3** feature releases ([newsletter Sept 2026](https://blog.vespa.ai/vespa-newsletter-sept-2026/)) | `n.a.` on fetched pages | Yes — **`bm25` with labels** plus HNSW ANN in one ranking expression ([newsletter](https://blog.vespa.ai/vespa-newsletter-sept-2026/)) | `n.a.` | **`filterFirstExploration`** and **`ranking.matching.anntimebudget`** for filtered ANN control ([newsletter](https://blog.vespa.ai/vespa-newsletter-sept-2026/)) | `n.a.` | Vespa Cloud + self-host | Vendor claim of **5× infrastructure cost savings** ([press releases](https://vespa.ai/press-releases/)) |
| **Elasticsearch** | **9.5.2, 20 Aug 2026**; ~8-week release cycle ([Coralogix comparison](https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/)) | **SSPL + Elastic License 2.0** since 7.11, with **AGPLv3 added in 8.16.0** ([Coralogix](https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/)) | Yes, mature BM25 + dense + RRF | Yes | Yes | **BBQ, disk-BBQ and ACON** — Elastic claims "two orders of magnitude less RAM" ([Q3 2026 earnings call](https://www.theglobeandmail.com/investing/markets/stocks/ESTC/pressreleases/458265/elastic-estc-q3-2026-earnings-call-transcript/)) | Elastic Cloud + self-host | **Vendor benchmark:** ES 9.3.0 up to **8× higher throughput** than OpenSearch 3.5.0 on filtered vector search (20M docs, Recall@100) ([Elastic Search Labs](https://www.elastic.co/search-labs/blog/opensearch-vs-elasticsearch-filtered-vector-search)) |
| **OpenSearch** | **3.8.0, 4 Aug 2026** ([Coralogix](https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/)) | **Strictly Apache-2.0** ([Coralogix](https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/)) | Yes | Yes | Yes | `n.a.` | AWS OpenSearch Service + self-host | The license is the differentiator; Elastic's own benchmark above is unfavourable and independently unverified ([Elastic](https://www.elastic.co/search-labs/blog/opensearch-vs-elasticsearch-filtered-vector-search)) |
| **Chroma** | Changelog's latest entry is **EU Region Support (Apr 2026)**; **Chroma Sync** for S3/GitHub/Web (Mar 2026) ([changelog](https://www.trychroma.com/changelog)) | `n.a.` on fetched pages | `n.a.` | **CMEK** and EU region for Chroma Cloud ([changelog](https://www.trychroma.com/changelog)) | **Metadata Arrays** ([changelog](https://www.trychroma.com/changelog)) | `n.a.` | Chroma Cloud + embedded/self-host | **Rust core rewrite in 1.0 → 4× faster** ([Chroma 1.0](https://www.trychroma.com/project/1.0.0)) |
| **Turbopuffer** | Continuous service; roadmap/pricing log through **Aug 2026** ([roadmap](https://turbopuffer.com/docs/roadmap), [pricing log](https://turbopuffer.com/docs/pricing-log)) | Proprietary managed, **object-storage-first** ([pricing log](https://turbopuffer.com/docs/pricing-log)) | Yes — **sparse vector support (Apr 2026)**, **per-subquery RRF weights (Jul 2026)**, **FTS v2 up to 20× faster (Jan 2026)**, `word_v4` tokenizer ~3× faster ([roadmap](https://turbopuffer.com/docs/roadmap)) | **Namespace**-per-tenant model, with namespace pinning ([pricing log](https://turbopuffer.com/docs/pricing-log)) | Yes | `n.a.` | Managed only | **Price trajectory is the signal:** base query rate cut **$5/PB → $1/PB (Feb 2026)**, 80% marginal discount at 32–128 GB and 96% above 128 GB, minimum billable 1.28 GB/query; Launch plan minimum **$64 → $16/month (Jun 2026)**; namespace-pinning minimum raised **64 GB → 128 GB (Aug 2026)** ([pricing log](https://turbopuffer.com/docs/pricing-log)). Adopted by Cursor and Notion ([Particula](https://particula.tech/blog/turbopuffer-vs-pinecone-vector-database-migration)) |

**Reading the 2026 vector-DB landscape:** three structural shifts are visible in the fetched release notes. (1) **Lexical search came home** — Milvus 3.0, Pinecone, Turbopuffer and Qdrant all shipped first-class BM25/sparse in 2026, so "vector DB + separate Elasticsearch" is no longer the default hybrid architecture ([Milvus](https://milvus.io/docs/release_notes.md), [Pinecone](https://docs.pinecone.io/release-notes/2026), [Turbopuffer](https://turbopuffer.com/docs/roadmap), [Qdrant](https://qdrant.tech/articles/hybrid-search/)). (2) **Storage/compute separation over object storage** is now table stakes — Milvus 3.0 "lake-native", Turbopuffer's object-storage design, Chroma Sync ([Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database), [Turbopuffer](https://turbopuffer.com/docs/pricing-log)). (3) **Aggressive quantization** is where the cost curve is bending: Qdrant up to 97% RAM reduction, Weaviate's 7.84× 4-bit RQ, Elastic BBQ/disk-BBQ ([Qdrant](https://github.com/qdrant/qdrant), [Weaviate](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39), [Elastic](https://www.theglobeandmail.com/investing/markets/stocks/ESTC/pressreleases/458265/elastic-estc-q3-2026-earnings-call-transcript/)).

---

## D. Embeddings & rerankers (2026)

### D.1 Embedding models

| Model | MTEB / benchmark | Multilingual (incl. Vietnamese) | Dimensions | Context | License | Price |
|---|---|---|---|---|---|---|
| **Gemini Embedding 2** (`gemini-embedding-2`, Apr 2026) | MTEB by dimension: **2048 → 68.16, 1536 → 68.17, 768 → 67.99, 512 → 67.55, 256 → 66.19, 128 → 63.31** ([Google AI docs](https://ai.google.dev/gemini-api/docs/embeddings)); paper reports **69.9 MTEB multilingual, 84.0 MTEB Code, 62.9 R@1 MSCOCO, 68.8 NDCG@10 Vatex** ([arXiv 2605.27295](https://arxiv.org/abs/2605.27295)) | **100+ languages** ([Google AI docs](https://ai.google.dev/gemini-api/docs/embeddings)); Vietnamese not individually scored — `n.a.` | **128–3072 (default 3072)**, Matryoshka ([docs](https://ai.google.dev/gemini-api/docs/embeddings)) | **8,192 tokens** ([docs](https://ai.google.dev/gemini-api/docs/embeddings)) | Proprietary API | `gemini-embedding-001` GA at **$0.15/1M tokens** ([Google Developers Blog](https://developers.googleblog.com/gemini-embedding-available-gemini-api/)); **Batch API 50% off** ([docs](https://ai.google.dev/gemini-api/docs/embeddings)) |
| **OpenAI text-embedding-3-large** | **MTEB 64.60** ([leaderboard summary](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/)) | Multilingual; Vietnamese-specific score `n.a.` | **3072** ([OpenAI docs](https://developers.openai.com/api/docs/models/text-embedding-3-large)) | **8,191 tokens** ([OpenAI docs](https://developers.openai.com/api/docs/models/text-embedding-3-large)) | Proprietary API | **$0.13/1M** (3-large); **$0.02/1M** (3-small) ([OpenAI docs](https://developers.openai.com/api/docs/models/text-embedding-3-large), [announcement](https://openai.com/index/new-embedding-models-and-api-updates/)) |
| **Voyage (voyage-4 family)** | **voyage-3.1-large MTEB 67.40** ([leaderboard](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/)) | Multilingual; Vietnamese score `n.a.` | `n.a.` | `n.a.` | Proprietary API | **voyage-4-large $0.12/1M, voyage-4 $0.06, voyage-4-lite $0.02, voyage-context-4 $0.12, voyage-code-4 $0.12**; multimodal-3.5 $0.12/1M + $0.60/1B pixels; **200M free tokens**, Batch API **33% discount**, Files API $0.05/GB/month ([Voyage pricing](https://docs.voyageai.com/docs/pricing)) |
| **Cohere Embed v4** (`embed-v4.0`) | **MTEB 65.20** ([leaderboard](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/)) | Multilingual; text, images and **mixed text/image (PDFs)** ([Cohere docs](https://docs.cohere.com/docs/cohere-embed)) | **256 / 512 / 1024 / 1536 (default 1536)** ([Cohere docs](https://docs.cohere.com/docs/cohere-embed)) | **128k tokens** ([Cohere docs](https://docs.cohere.com/docs/cohere-embed)) | Proprietary API; also self-hostable via Model Vault | **$0.12/1M** per leaderboard; Model Vault hourly: **Embed 4 Small $4/hr (~$2,500/mo), Embed 4 Medium $5/hr** ([Cohere pricing](https://cohere.com/pricing)) |
| **Qwen3-Embedding** (0.6B / 4B / 8B, Jun 2025) | **8B was #1 on MTEB multilingual at 70.58 (5 Jun 2025)** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)); still 70.58 in Apr 2026 rankings ([leaderboard](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/)) | **100+ languages** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) — the best-documented open option for Vietnamese-inclusive coverage | **0.6B → 1024, 4B → 2560, 8B → 4096**, with MRL truncation ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | **32K tokens** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | **Apache 2.0** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | Self-host. Measured serving cost on an L4: **0.6B $0.011/1M tokens at 157 ms p50; 4B $0.039/1M at 464 ms** ([Superlinked](https://superlinked.com/blog/qwen3-embedding-reranker-guide)) |
| **BGE-M3** | `n.a.` MTEB on fetched page | **100+ languages** ([HF model card](https://huggingface.co/BAAI/bge-m3)) | **1024** ([HF](https://huggingface.co/BAAI/bge-m3)) | **8192 tokens** ([HF](https://huggingface.co/BAAI/bge-m3)) | `n.a.` on fetched card | Self-host (free weights) |
| **jina-embeddings-v5 family** | **v5-text-small: MMTEB 67.0, English MTEB 71.7**; v5-text-nano MMTEB 65.5; **v5-omni-small described as best open-weight omni model under 2B** ([Jina](https://jina.ai/en-US/embeddings/)) | v5-text-nano covers **15 languages** (EuroBERT-210M base); v3 covered **89 languages** ([Jina](https://jina.ai/en-US/embeddings/)) | v5-omni-small **1024**; v5-omni-nano **768**; all v5 support **Matryoshka down to 32** ([Jina](https://jina.ai/en-US/embeddings/)) | v5-omni-small **32K**; v5-omni-nano **8K**; v4 **32,768** ([Jina](https://jina.ai/en-US/embeddings/)) | **v4 is Qwen Research License — non-commercial only**; commercial licensing brokered via Elastic Sales ([Jina](https://jina.ai/en-US/embeddings/)) — a real procurement trap | `n.a.`; Elastic partnership announced Feb 2026 ([Elastic IR](https://ir.elastic.co/News--Events/news/news-details/2026/Elastic-Introduces-Best-in-Class-Embedding-Models-for-High-Performance-Semantic-Search/default.aspx)) |
| **NVIDIA NeMo Retriever** | Vendor claims **50% fewer incorrect answers, 3× embedding throughput, 15× extraction throughput, 35× storage efficiency** ([NVIDIA](https://developer.nvidia.com/nemo-retriever)) | `n.a.` | `n.a.` | `n.a.` | Open weights for Nemotron Retriever models; **license not stated** ([NVIDIA](https://developer.nvidia.com/nemo-retriever)) | Self-host NIM microservices; repo default is now **Nemotron 3 Embed**, GA branch **26.08** ([GitHub](https://github.com/NVIDIA/NeMo-Retriever)) |
| **Mixedbread Wholembed v3** | `n.a.` score | Omnimodal late-interaction, now the **default** embedding model ([changelog](https://www.mixedbread.com/docs/changelog)) | `n.a.` | `n.a.` | `n.a.` | `n.a.` |

Reference points from the Apr 2026 leaderboard snapshot (secondary source, use with care): **Gemini Embedding 001 #1 at 68.32**, NV-Embed-v2 72.31 flagged as legacy, Qwen3-Embedding-8B 70.58, Voyage-3.1-large 67.40 at $0.05/1M, Jina v4 66.81, Cohere Embed v4 65.20, OpenAI text-embedding-3-large 64.60 ([awesomeagents leaderboard](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/)).

### D.2 Rerankers

| Reranker | Benchmark | Languages | Context | License | Price |
|---|---|---|---|---|---|
| **Qwen3-Reranker 8B** | **MTEB-R 69.02 / MMTEB-R 72.94**; 4B: **69.76 / 72.74**; 0.6B: **65.80 / 66.36**; baseline bge-reranker-v2-m3 **57.03 / 58.36** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | 100+ ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | 32K ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | **Apache 2.0** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | Self-host; **Reranker-0.6B at 65 ms** on an L4 ([Superlinked](https://superlinked.com/blog/qwen3-embedding-reranker-guide)) |
| **Cohere Rerank v4.0-pro / v4.0-fast** | `n.a.` public score | Multilingual, JSON-aware ([Cohere docs](https://docs.cohere.com/docs/rerank)) | rerank-v3.5 context **4096 tokens** ([Cohere docs](https://docs.cohere.com/docs/rerank)) | Proprietary | Search unit = **1 query + up to 100 documents**, docs >500 tokens auto-chunked; Model Vault: **Rerank 3.5 / Rerank 4 Fast / Rerank 4 Pro Medium $5/hr, Rerank 4 Pro Large $10/hr** ([Cohere pricing](https://cohere.com/pricing)) |
| **Voyage rerank-3 / rerank-3-lite** | `n.a.` | `n.a.` | `n.a.` | Proprietary | **$0.05/1M** and **$0.02/1M** ([Voyage pricing](https://docs.voyageai.com/docs/pricing)) |
| **bge-reranker-v2-m3** | Baseline **MTEB-R 57.03 / MMTEB-R 58.36** ([Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)) | Multilingual, 0.6B; **18.1M downloads/month** ([HF](https://huggingface.co/BAAI/bge-reranker-v2-m3)) | **max_length 512** ([HF](https://huggingface.co/BAAI/bge-reranker-v2-m3)) | `n.a.` | Self-host |
| **jina-reranker-v3.5** | `n.a.` | `n.a.` | `n.a.` | See Jina licensing caveat above | Released **3 Aug 2026** ([Jina GitHub](https://github.com/jina-ai)) |
| **mxbai-rerank-large-v2 / base-v2** | **BEIR accuracy 57.49** (large, 1.5B) and **55.57** (base, 0.5B) ([Mixedbread models](https://www.mixedbread.com/docs/models/reranking)) | **100+ languages**, 32k context ([Mixedbread](https://www.mixedbread.com/docs/models/reranking)) | 32k ([Mixedbread](https://www.mixedbread.com/docs/models/reranking)) | **Apache 2.0** for mxbai-rerank-v2 ([Mixedbread blog](https://www.mixedbread.com/blog/mxbai-rerank-v2)) | Self-host |
| **mxbai-rerank-v3.1-listwise** | **Now the default reranker; 25–54% faster than v3-listwise** at comparable quality ([changelog](https://www.mixedbread.com/docs/changelog)) | `n.a.` | `n.a.` | `n.a.` | Mixedbread also ships **Toast 1**, a search model claimed **10× cheaper and 12× faster** than frontier LLM rerankers ([changelog](https://www.mixedbread.com/docs/changelog)) |

### D.3 Visual document retrieval (ColPali / ColQwen) — ViDoRe scores

| Model | ViDoRe | License / note |
|---|---|---|
| colqwen3.5-4.5B-v3 | **90.9** | ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| tomoro-colqwen3-embed-4b | **90.6** (320-dim ColBERT embeddings) | ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| colqwen2.5-v0.2 | **89.4** | ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| colqwen2-v1.0 | **89.3** | **Apache-2.0** ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| ColNetraEmbed | **86.4**, 22 languages | ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| colpali-v1.3 | **84.8** | **Gemma license** ([ColPali repo](https://github.com/illuin-tech/colpali)) |
| colSmol-500M / 256M | **82.3 / 80.1** | ([ColPali repo](https://github.com/illuin-tech/colpali)) |

Also relevant: **Qwen3-VL-Embedding-2B and Qwen3-VL-Reranker-2B** shipped Jan 2026 ([Superlinked](https://superlinked.com/blog/qwen3-embedding-reranker-guide)), and Milvus 3.0's `StructList` type exists specifically to store ColBERT/ColPali multi-vectors natively ([Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)).

**Vietnamese-specific guidance:** no fetched source publishes a Vietnamese-only embedding benchmark. The defensible choices are the models with documented 100+ language coverage — **Qwen3-Embedding (Apache 2.0, self-hostable)**, **BGE-M3**, **Gemini Embedding 2** and **Cohere Embed v4** ([Qwen](https://qwenlm.github.io/blog/qwen3-embedding/), [BAAI](https://huggingface.co/BAAI/bge-m3), [Google](https://ai.google.dev/gemini-api/docs/embeddings), [Cohere](https://docs.cohere.com/docs/cohere-embed)). Avoid jina-v5-text-nano for Vietnamese: it documents only **15 languages** ([Jina](https://jina.ai/en-US/embeddings/)).

---

## E. Document ingestion & parsing

| Tool | License | OCR / table / layout quality (as claimed or benchmarked) | Vietnamese OCR | Output formats |
|---|---|---|---|---|
| **Docling** (IBM → LF AI & Data) | **MIT**; latest **v2.126.0, 4 Sep 2026** ([GitHub](https://github.com/docling-project/docling)) | No benchmark numbers on the project page; uses the **GraniteDocling** VLM. Third-party olmocr-bench puts docling at **50.3 overall at 2.1 pages/s** ([Marker repo](https://github.com/datalab-to/marker)) | `n.a.` | **Markdown, HTML, WebVTT, DocLang, DocTags, lossless JSON**; inputs PDF/DOCX/PPTX/XLSX/HTML/EPUB/audio/video ([GitHub](https://github.com/docling-project/docling)) |
| **Unstructured** | OSS library **Apache-2.0** ([pricing](https://unstructured.io/pricing)) | **45+ file types** ([pricing](https://unstructured.io/pricing)); no benchmark numbers on fetched pages | `n.a.` | `n.a.` explicit list. **Free 10,000 pages; pay-as-you-go $0.015/page; Business tier with dedicated instance/VPC/bare metal** ([pricing](https://unstructured.io/pricing)); Unstructured Transform MCP GA 9 Jul 2026 ([aibestnav](https://aibestnav.com/ai-tools/unstructured/)) |
| **LlamaParse / LlamaCloud** | Proprietary SaaS; LlamaCloud **renamed LlamaParse in Feb 2026** ([LlamaIndex newsletter](https://www.llamaindex.ai/blog/llamaindex-newsletter-2026-02-24)) | **Agentic OCR**, 130+ formats; modules Parse / Extract / Classify / Split / Index ([LlamaParse docs](https://developers.llamaindex.ai/llamaparse/)). Its local-first `liteparse` scores **22.4** on olmocr-bench ([Marker repo](https://github.com/datalab-to/marker)) | `n.a.` | `n.a.` explicit list. **$1.25 per 1,000 credits** ([markaicode](https://markaicode.com/pricing/llamaparse-pricing/)); the `llama-parse` PyPI package is **deprecated after 1 May 2026** ([docs](https://developers.llamaindex.ai/llamaparse/)) |
| **Marker** (Datalab) | **Code Apache 2.0; weights under a modified AI Pubs OpenRAIL-M — free only below $5M funding/revenue**; **v2.0.0, 20 Jul 2026** ([GitHub](https://github.com/datalab-to/marker)) | **olmocr-bench (1,403 PDFs, ~8,400 tests): Marker balanced 76.0 overall / 83.5 digital at 2.9 pages/s; Marker fast 66.6 at 7.4 pages/s.** Context: Chandra 2 hosted **85.8**, Gemini Flash 3.5 **76.4**, MinerU pipeline **72.7 at 0.54 pg/s**, docling **50.3** ([GitHub](https://github.com/datalab-to/marker)) | `n.a.` | Markdown/JSON/HTML per project ([GitHub](https://github.com/datalab-to/marker)) |
| **MinerU** (OpenDataLab) | **MinerU Open Source License** — Apache-2.0-based with added conditions; **moved off AGPLv3 at 3.1.0**; latest **3.4.5, 14 Aug 2026** ([GitHub](https://github.com/opendatalab/MinerU)) | **OmniDocBench v1.6 end-to-end: pipeline 86.47, vlm-engine 95.30, hybrid-engine (high) 95.39**; PP-OCRv6 adds **~+11% accuracy and ~100% speed** ([GitHub](https://github.com/opendatalab/MinerU)) | **109 OCR languages** ([GitHub](https://github.com/opendatalab/MinerU)) — the strongest documented multilingual OCR breadth among OSS parsers | Markdown/JSON ([GitHub](https://github.com/opendatalab/MinerU)) |
| **Reducto** | Proprietary SaaS | **LongExtractBench (micro1; 225 documents, ~358 pages average): precision 99.6%, recall ~99%**; also publishes RD-TableBench; layout-aware chunking and handwriting support ([Reducto comparison](https://llms.reducto.ai/document-parser-comparison), [benchmark guide](https://reducto.ai/guides/document-ai-benchmark-ocr-parsing-extraction)) | **100+ languages** ([Reducto](https://reducto.ai/guides/document-ai-benchmark-ocr-parsing-extraction)) | `n.a.` explicit list |
| **Azure AI Document Intelligence** | Proprietary Azure service | **v4.0 (2024-11-30) is the current GA API**; page last updated 2026-09-08 ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0)) | `n.a.` | `n.a.`. **Lifecycle matters: v2.0 cloud API and the v2.1 container were retired 31 Aug 2026; v2.1 EOS 15 Sep 2027; v3.0 EOS 30 Mar 2029** ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0)). Azure Content Understanding added GPT-5-class models at Build 2026 ([Foundry blog](https://devblogs.microsoft.com/foundry/whats-new-in-azure-content-understanding-at-build-2026/)) |
| **Chunkr** | **Dual AGPL-3.0 / commercial**; **v2.2.1, 31 Jul 2025** ([GitHub](https://github.com/lumina-ai-inc/chunkr)) | OSS build uses community models while the cloud uses proprietary models — so OSS quality ≠ cloud quality ([GitHub](https://github.com/lumina-ai-inc/chunkr)) | `n.a.` | **HTML, Markdown, chunks + bounding boxes** ([GitHub](https://github.com/lumina-ai-inc/chunkr)) |
| **Apache Tika** | Apache-2.0; **4.0.0, 21 Aug 2026** (Java 17); 3.3.2 (16 Jul 2026) still supported ([tika.apache.org](https://tika.apache.org/)) | Adds **VLM parsers for Claude, Gemini and OpenAI** plus in-process Tesseract ([tika.apache.org](https://tika.apache.org/)) | Via Tesseract language packs — `n.a.` quality data | **Markdown is now the default output** in 4.0.0 ([tika.apache.org](https://tika.apache.org/)) |

### E.1 Vietnamese document parsing — the 2026 picture

| Finding | Number / detail | Source |
|---|---|---|
| PaddleOCR-VL-1.6 on OmniDocBench v1.6 | **96.33%** | [centrix.digital](https://centrix.digital/paddleocr-vl-1-6-dat-963-tren-omnidocbench-v1-6/) |
| SenOCR-Vi (fine-tuned on PaddleOCR-VL-1.6) | **82.83 Vietnamese document score** | [HuggingFace](https://huggingface.co/VietAlphaLabs/SenOCR-Vi) |
| ViDocParse benchmark | **11,439 Vietnamese document-page images, 9 categories, 7 OCR/VLM systems benchmarked**, block- and span-level labels on the OmniDocBench schema; 3 LoRA fine-tuning splits and 3 released checkpoints | [OpenReview / ACL ARR 2026, CC BY 4.0](https://openreview.net/forum?id=Vkeag2cpRN) |
| ViDocParse conclusion | **No single model dominates across document attributes**; remaining layout-sensitive failures are **column merging, table omission, inline-formula boundary drift**, driven by tone/vowel diacritics, syllable-based writing and dense multi-column layouts | [OpenReview](https://openreview.net/forum?id=Vkeag2cpRN) |

**Implication for a Vietnamese-language enterprise corpus:** treat parsing as an ensemble problem, not a vendor choice. Run a VLM-based parser (PaddleOCR-VL / SenOCR-Vi / MinerU vlm-engine) and validate table extraction separately, because tables are the documented failure mode. Do not assume an English olmocr-bench or OmniDocBench score transfers to Vietnamese.

---

## F. Ontology & semantic layer

| Item | Version / status | License | Capability relevant to enterprise agents |
|---|---|---|---|
| **Protégé** (Stanford) | Desktop + WebProtégé; no version stated on the software page (`n.a.`) — GitHub tags show 5.6.8 (3 Sep 2025) ([protege GitHub](https://github.com/protegeproject/protege)) | **Free and open source** ([Stanford](https://protege.stanford.edu/software/)) | Full **OWL 2** editing, direct connection to DL reasoners **HermiT** and **Pellet**, inference explanation, ontology merging/refactoring/batch rename, plug-in extensible; WebProtégé adds collaborative editing, permissions, threaded notes, full revision history, and upload/download in RDF/XML, Turtle, OWL/XML and OBO ([Stanford](https://protege.stanford.edu/software/)) |
| **rdflib** | **7.6.0, 13 Feb 2026**; a major **v8 expected in the second half of 2026** ([rdflib.dev](https://rdflib.dev/)) | `n.a.` on page | Pure-Python RDF: parsers/serializers for RDF/XML, N3, NTriples, N-Quads, Turtle, TriX, TriG, JSON-LD, HexTuples; **SPARQL 1.1 queries and updates** with function extensions; stores for in-memory, Berkeley DB and remote SPARQL endpoints; **7.6.0 added clients for RDF4J and GraphDB APIs**; `OWL-RL` implements the **OWL2 RL profile** ([rdflib.dev](https://rdflib.dev/)) |
| **Ontotext GraphDB** | **11.5.0, 19 Aug 2026** (RDF4J 5.3.1, Connectors 16.7.0, Workbench 3.5.0) ([release notes](https://graphdb.ontotext.com/documentation/master/release-notes.html)) | Commercial with a **new license metric in 11.5 tracking days until license expiry** ([release notes](https://graphdb.ontotext.com/documentation/master/release-notes.html)) | Enterprise governance moved forward in 11.5: repository-level `maintain_repo_<repositoryId>` permission (restart + edit permissions, cannot delete), and **multiple simultaneous authorization sources** (one primary plus additional local/ldap/oauth) where previously only one backend could be active ([release notes](https://graphdb.ontotext.com/documentation/master/release-notes.html)) |
| **Stardog** | Version `n.a.` on the platform page | `n.a.` | Positions as a **"Semantic AI Platform"** creating a semantic layer that connects and enriches enterprise data for reuse across AI, analytics, search and applications; **virtualize or materialize** (query data in place without copying, preserving ownership and governance); inference engine for explainable AI; connectors to all major SQL systems ([Stardog](https://www.stardog.com/platform/)) |
| **Palantir Ontology** | Foundry product; no version (`n.a.`) | Proprietary | Semantic search over ontology objects: text is embedded into vectors so that semantically similar text is nearby in N-dimensional space (their example: "face mask" is closer to "face covering" than to "respirator"); embeddings are **bound to a specific object in the Ontology**, which is what makes search-driven operational workflows useful; documented patterns for Palantir-provided vs custom models, chunking, and PDFs ([Palantir docs](https://palantir.com/docs/foundry/ontology/overview-semantic-search/)) |
| **dbt Semantic Layer (MetricFlow)** | Participant in the OSI working group; **dbt→OSI converter merged** ([datus.ai](https://datus.ai/blog/semantic-layer-tools-list-osi/)) | `n.a.` | Metric definitions as code, now with a reference path to a shared interchange format ([datus.ai](https://datus.ai/blog/semantic-layer-tools-list-osi/)) |
| **Cube** | `n.a.` version; **$40/developer/month Starter** ([colrows pricing comparison](https://colrows.com/blogs/semantic-layer-pricing-comparison/)) | `n.a.` | Explicitly repositioned as an **AI context layer for agents**: certified metrics, dimensions, joins and access rules defined once and enforced, so an LLM selects from governed math instead of re-deriving joins per prompt (which is how the same question yields different numbers); adds glossary/business logic/edge-case guidance, lineage back to named definitions, external context (docs, tickets, incidents) over **MCP connectors**, and **Cube Evals** for testing an agent against question/known-answer cases ([Cube](https://cube.dev/product/semantic-layer)) |
| **AtScale** | OSI working-group participant ([datus.ai](https://datus.ai/blog/semantic-layer-tools-list-osi/)) | `n.a.` | `n.a.` |
| **Open Semantic Interchange → Apache Ossie** | **Entered the Apache Incubator as Apache Ossie in June 2026**; as of **July 2026 no semantic-layer product ships user-facing OSI import/export**; first native support expected within 2026; **50+ organizations** in the working group; repo `github.com/apache/ossie` ([datus.ai](https://datus.ai/blog/semantic-layer-tools-list-osi/)) | Apache (incubating) | **Merged reference converters: dbt/MetricFlow, GoodData, Salesforce, Apache Polaris; Spark in review.** These are CLI reference implementations, not product features — Level 1 of 3 on their own maturity scale ([datus.ai](https://datus.ai/blog/semantic-layer-tools-list-osi/)) |
| **ISO/IEC 39075 (GQL)** | Published 2024; **Technical Corrigendum 1 published 30–31 Jul 2026** | ISO/IEC copyright, all rights reserved ([ISO catalog](https://standards.iteh.ai/catalog/standards/iso/e9bee956-a206-4886-bbc7-97c3684e6f76/iso-iec-39075-2024-cor-1-2026)) | See the GQL table in Section A |

**How ontology fits enterprise agents, concretely.** Two patterns are visible in the 2026 evidence and they are not the same thing:

1. **Ontology-as-schema for extraction.** Graphiti lets you declare a **prescribed ontology in Pydantic** and also learn one ([Graphiti](https://github.com/getzep/graphiti)); LlamaIndex's `SchemaLLMPathExtractor` constrains extraction to a schema ([LlamaIndex](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)); FalkorDB's GraphRAG-SDK auto-detects and manages ontologies ([FalkorDB](https://www.falkordb.com/)). This is what stops LLM-built graphs from turning into inconsistent mush.
2. **Ontology/semantic layer as the numeric authority.** Cube's argument is the important one for agents: if the agent queries raw tables, it re-derives joins and metric logic per prompt and produces different numbers for the same question ([Cube](https://cube.dev/product/semantic-layer)). Agents should read **metrics** from a semantic layer and **entities/relationships** from a knowledge graph, never recompute revenue from raw facts.

---

## G. Cross-cutting techniques

### G.1 Agentic retrieval and agentic RAG patterns

**Azure AI Search agentic retrieval** is the most concretely documented managed implementation. It is a **multi-query pipeline** that uses an LLM to break a complex query into smaller focused subqueries, incorporates chat history into those subqueries, **runs subqueries in parallel**, **semantically reranks each subquery's results**, and merges the best results into a unified grounded response with **source references and an activity log** ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)). Status: **some agentic retrieval features are GA in the 2026-04-01 REST API**, while the Azure portal and Microsoft Foundry portal remain preview-only for the full feature set; the full surface is in the **2026-08-01-preview** REST API, which is licensed as part of the Azure subscription under Microsoft's preview terms with no SLA and is not recommended for production ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview), [What's New](https://learn.microsoft.com/en-us/azure/search/whats-new)). Note the compliance caveat Microsoft states explicitly: the preview supports connections to Microsoft and third-party services, which **may result in data processing or storage outside the Azure compliance boundary** ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)).

Named patterns catalogued in the 2026 production literature: **router, ReAct, plan-and-execute, multi-agent, self-RAG, corrective RAG (CRAG) and adaptive RAG** ([MarsDevs](https://www.marsdevs.com/guides/agentic-rag-2026-guide), [Brightter](https://www.brightter.com/articles/agentic-rag-five-retrieval-patterns-that-survive-production)). The same guide frames GraphRAG as an **optional third retriever stage for relationship and cross-document queries**, and argues the strongest 2026 systems combine agentic orchestration with a graph-backed knowledge base ([MarsDevs](https://www.marsdevs.com/guides/agentic-rag-2026-guide)). It also notes Anthropic's **Citations API** provides guaranteed pointers back to source documents with `cited_text` excluded from output token cost — recommended for compliance and high-stakes citation surfaces — and that Anthropic **donated MCP to the Linux Foundation's Agentic AI Foundation in December 2025** ([MarsDevs](https://www.marsdevs.com/guides/agentic-rag-2026-guide)).

### G.2 Hybrid search + reranking best practice

| Practice | Evidence |
|---|---|
| Combine BM25 and dense, then fuse | BM25 (Best Matching 25) refines TF-IDF by considering document length and applying a saturation function to term frequency; it catches exact identifiers like `"Error code TS-999"` that embeddings miss. Canonical pipeline: chunk → build TF-IDF encodings **and** embeddings → retrieve top chunks from each → **combine and deduplicate with rank fusion** → pass top-K to the model ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)) |
| Retrieve wide, rerank down | Anthropic's reranking setup retrieved **top 150** candidates and cut to **top 20**, using a Cohere reranker; of chunk counts 5/10/20 tested, **20 was most performant** ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)) |
| But do not rerank too wide | Weaviate reports **rerankers lose recall beyond roughly 100 documents** ([Weaviate](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) |
| Tune effort per query | Weaviate's search effort tiers moved BRIGHT Biology from **13.0 nDCG@10 (plain hybrid) to 57.5 (ultrahigh effort)** ([Weaviate](https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39)) |
| Two-stage hybrid + neural rerank, measured | **Recall@5 0.816, MRR@3 0.605** ([arXiv 2604.01733](https://arxiv.org/pdf/2604.01733)) |
| Fusion algorithm choice is now configurable | Qdrant offers **RRF and DBSF**; Milvus offers **weighted RRF and function-chain reranking**; Turbopuffer added **per-subquery RRF weights** ([Qdrant](https://qdrant.tech/articles/hybrid-search/), [Milvus](https://milvus.io/docs/release_notes.md), [Turbopuffer](https://turbopuffer.com/docs/roadmap)) |
| Skip RAG below a threshold | A knowledge base under **200,000 tokens (~500 pages)** can go directly in the prompt ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)) |

### G.3 Chunking strategies

**Anthropic Contextual Retrieval** prepends chunk-specific explanatory context (typically **50–100 tokens**) before both embedding and BM25 indexing. Measured on top-20 retrieval with Gemini Text 004 embeddings and a 1−recall@20 failure metric ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)):

| Configuration | Failure rate | Reduction |
|---|---|---|
| Baseline | 5.7% | — |
| Contextual Embeddings | **3.7%** | **35%** |
| Contextual Embeddings + Contextual BM25 | **2.9%** | **49%** |
| + Reranking | **1.9%** | **67%** |

Cost: **$1.02 per million document tokens** one-time, assuming 800-token chunks in 8,000-token documents with 50-token instructions and 100 tokens of context per chunk; **prompt caching cuts latency by more than 2× and cost by up to 90%** ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)).

**Late chunking** achieves a related goal without any LLM calls. The method tokenizes the whole document, applies the transformer to **all** tokens first to produce contextualized token embeddings, and only **then** applies chunk boundaries, mean-pooling token embeddings per chunk. Chunk embeddings therefore carry semantics from their position in the whole document. It is an architectural change to long-context mean-pooling embedding models that **requires no additional training**, works with any boundary algorithm (fixed-size, sentence, semantic-sentence), and translates character boundaries to token positions used only at the pooling step. Illustrative context length: **8,192 tokens for jina-embeddings-v2-small, roughly ten pages**, versus paragraph-sized optimal chunks ([Late Chunking, OpenReview](https://openreview.net/pdf?id=74QmBTV0Zf)). The paper's Berlin example shows coreference-heavy sentences gaining similarity under late chunking versus naive (e.g. 0.8486 → 0.8495 on the lead sentence, with larger gains on pronoun-bearing follow-ons) ([OpenReview](https://openreview.net/pdf?id=74QmBTV0Zf)). A side-by-side comparison of the two approaches is available from [Particula](https://particula.tech/blog/contextual-retrieval-vs-late-chunking).

Baseline chunking parameters recommended in 2026 production guidance: **512–1024 tokens with 50–100 token overlap**, chunked by section header where structure allows, with semantic chunking outperforming fixed-size in the authors' tests ([MarsDevs](https://www.marsdevs.com/guides/agentic-rag-2026-guide)). Parser-side, **Reducto offers layout-aware chunking** and **TigerGraph GraphRAG v2.0 added structure-aware chunking** ([Reducto](https://reducto.ai/guides/document-ai-benchmark-ocr-parsing-extraction), [graphwiz](https://graphwiz.ai/content/graphs/tigergraph-graphrag-v2-agentic-mcp/)).

**Decision rule:** use late chunking as the default because it is free at index time; add Anthropic-style contextual retrieval for the subset of the corpus where chunks are genuinely unintelligible standalone (contracts, tables, references to "the Company"); always pair either with BM25 and a reranker.

### G.4 Evaluation — RAGAS and GraphRAG-Bench

RAGAS organises metrics by application aspect, with LLM-based metrics using one or more LLM calls per score, and supports user-defined metrics ([RAGAS docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)):

| Category | Metrics |
|---|---|
| Retrieval Augmented Generation | Context Precision, Context Recall, Context Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness, Multimodal Faithfulness, Multimodal Relevance |
| Nvidia Metrics | Answer Accuracy, Context Relevance, Response Groundedness |
| Agents / tool use | Topic Adherence, Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy |
| Natural language comparison | Factual Correctness, Semantic Similarity, Non-LLM String Similarity, BLEU, CHRF, ROUGE, String Presence, Exact Match |
| Other | Summarization |

All metric names above are from [the RAGAS available-metrics page](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/); the page does not state formal definitions or benchmark numbers (`n.a.`). A broader comparison of LLM evaluation frameworks is at [Atlan](https://atlan.com/know/llm-evaluation-frameworks-compared/).

For graph-specific evaluation use **GraphRAG-Bench**'s four levels and metrics (Section B) ([repo](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)), and Microsoft's **BenchmarkQED** plus **VeriTrail** for claim verification ([MSR](https://www.microsoft.com/en-us/research/project/graphrag/)). Cube's **Evals** extends the same idea to governed metrics: question plus known-correct answer, run against the agent ([Cube](https://cube.dev/product/semantic-layer)).

---

## H. Recommended enterprise knowledge architecture

The evidence above supports a **four-layer architecture** in which each layer answers the question class it is actually good at, with an agent doing the routing.

```
                        ┌──────────────────────────────────────┐
   User / agent  ──────▶ │  ORCHESTRATION: query decomposition, │
                        │  routing, self/corrective RAG loops  │
                        └───────┬───────┬───────┬──────────────┘
                                │       │       │
        ┌───────────────────────▼──┐ ┌──▼─────────────┐ ┌▼───────────────────────┐
        │ 1. HYBRID SEARCH         │ │ 2. KNOWLEDGE   │ │ 3. SEMANTIC LAYER      │
        │ dense + BM25 + rerank    │ │    GRAPH       │ │    over warehouse      │
        │ (facts, passages, cites) │ │ (multi-hop,    │ │ (governed metrics,     │
        │                          │ │  relationships,│ │  "what is revenue")    │
        │                          │ │  temporal)     │ │                        │
        └───────────┬──────────────┘ └──────┬─────────┘ └───────────┬────────────┘
                    │                       │                       │
        ┌───────────▼───────────────────────▼───────────────────────▼────────────┐
        │ 0. INGESTION & ONTOLOGY: parse → chunk (late/contextual) → extract     │
        │    entities under a declared schema → embed → index                    │
        └────────────────────────────────────────────────────────────────────────┘
```

**Layer 0 — ingestion and ontology.** Parsing quality caps everything downstream, and for Vietnamese corpora the ViDocParse result — no model dominates, tables and multi-column layouts fail — means you should ensemble and validate rather than trust a single vendor ([ViDocParse](https://openreview.net/forum?id=Vkeag2cpRN)). Use **Docling (MIT)** as the permissive default with **MinerU (109 OCR languages)** for hard multilingual scans and **Marker** where its benchmark lead matters and the funding threshold in its weight license is acceptable ([Docling](https://github.com/docling-project/docling), [MinerU](https://github.com/opendatalab/MinerU), [Marker](https://github.com/datalab-to/marker)). Declare the ontology up front — Pydantic in Graphiti or a `SchemaLLMPathExtractor` in LlamaIndex — rather than letting an LLM invent node types per document ([Graphiti](https://github.com/getzep/graphiti), [LlamaIndex](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)).

**Layer 1 — hybrid search is the workhorse, not the fallback.** This is where the measured wins are: −49% retrieval failure from contextual embeddings plus contextual BM25, −67% with reranking ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)). Build it first, in one system rather than two, since Qdrant, Milvus 3.0, Pinecone and Turbopuffer now all do BM25 natively ([Qdrant](https://qdrant.tech/articles/hybrid-search/), [Milvus](https://milvus.io/docs/release_notes.md), [Pinecone](https://docs.pinecone.io/release-notes/2026), [Turbopuffer](https://turbopuffer.com/docs/roadmap)).

**Layer 2 — the graph is a targeted second stage.** Justify it per question class, because graph retrieval costs **2.3× latency** and loses **13.4% accuracy on Natural Questions** while gaining only **4.5% reasoning depth on HotpotQA multi-hop** ([arXiv 2506.05690](https://arxiv.org/html/2506.05690v1)). Prefer approaches that skip whole-corpus summarization: **LazyGraphRAG**'s deferred, budgeted query-time work ([MSR](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)) or **LightRAG**'s dual-level retrieval with no community reports ([LightRAG](https://github.com/HKUDS/LightRAG)). If facts change over time — org charts, contracts, prices — use a **bi-temporal** store like Graphiti so answers carry validity windows rather than silently going stale, which is precisely the failure the 16.6% time-sensitive drop measures ([Graphiti](https://github.com/getzep/graphiti), [arXiv 2506.05690](https://arxiv.org/html/2506.05690v1)).

**Layer 3 — never let the agent compute metrics.** Route "what was Q3 revenue" to a semantic layer that enforces certified metrics, dimensions, joins and access rules, otherwise the same question yields different numbers on different prompts ([Cube](https://cube.dev/product/semantic-layer)). Expose it to the agent over MCP.

**Orchestration.** Decompose, run subqueries in parallel, rerank each, merge, and return source references plus an activity log — the shape Azure AI Search has productised ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)). Add self-RAG/corrective-RAG loops only where you can measure them; RAGAS's agent metrics (Tool Call F1, Agent Goal Accuracy, Topic Adherence) exist for exactly this ([RAGAS](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)).

### Concrete stack recommendations

| Scenario | Recommendation | Why (with source) |
|---|---|---|
| **Default enterprise stack, open-source-first** | Postgres + **pgvector 0.8.2** + **pgvectorscale 0.9.1** + **Apache AGE 1.7.0** in one database | One operational system; PostgreSQL-licensed StreamingDiskANN with SBQ quantization and label filtering ([pgvectorscale](https://github.com/timescale/pgvectorscale)); AGE 1.7.0 tracks PostgreSQL 18 ([AGE](https://age.apache.org/download/)). **Patch pgvector to 0.8.2 — CVE-2026-3172** ([PostgreSQL](https://www.postgresql.org/about/news/pgvector-082-released-3245/)) |
| **High-scale retrieval, permissive license** | **Qdrant 1.19.1 (Apache-2.0)** or **Milvus 3.0.1 (Apache 2.0)** | Both ship native hybrid; Milvus adds lake-native external collections over Iceberg/Lance/Parquet and `StructList` for ColPali multi-vectors ([Qdrant](https://github.com/qdrant/qdrant), [Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)) |
| **Cost-sensitive, bursty, multi-tenant SaaS** | **Turbopuffer** | Object-storage-first with query rate cut to **$1/PB** and Launch minimum down to **$16/month**; used by Cursor and Notion ([pricing log](https://turbopuffer.com/docs/pricing-log), [Particula](https://particula.tech/blog/turbopuffer-vs-pinecone-vector-database-migration)) |
| **Graph layer, mature ecosystem** | **Neo4j 2026.08.1 + neo4j-graphrag-python 1.19.0 (Apache-2.0)** | Best-documented GraphRAG tooling with native vector indexes; budget for the Enterprise commercial license if closed-source ([Neo4j](https://neo4j.com/release-notes/database/), [GitHub](https://github.com/neo4j/neo4j-graphrag-python), [licensing](https://neo4j.com/licensing/)) |
| **Graph layer, vector-heavy and RAM-conscious** | **Memgraph 3.13.0** | Vector indexes on nodes *and* edges, label filtering, quantization, ~85% vector memory reduction, Leiden communities, "Atomic GraphRAG" ([release notes](https://memgraph.com/docs/release-notes), [3.8 release](https://memgraph.com/blog/memgraph-3-8-release-atomic-graphrag-vector-single-store-parallel-runtime)) |
| **Avoid / migrate off** | **Kuzu** (archived, Apple acquisition) and **ArangoDB Community** for commercial use (100 GB cap, no commercial rights) | ([Kuzu](https://github.com/kuzudb/kuzu), [PuppyGraph](https://www.puppygraph.com/blog/what-is-kuzudb), [arango.ai](https://arango.ai/downloads/)) |
| **Embeddings, self-hosted & multilingual (incl. Vietnamese)** | **Qwen3-Embedding-4B or 8B (Apache 2.0)** + **Qwen3-Reranker-4B** | 100+ languages, 32K context, MRL dims; 8B hit **70.58** MTEB multilingual; reranker **69.76/72.74 (4B)** vs bge-reranker-v2-m3 **57.03/58.36**; measured **$0.039/1M at 464 ms p50** for 4B on an L4 ([Qwen](https://qwenlm.github.io/blog/qwen3-embedding/), [Superlinked](https://superlinked.com/blog/qwen3-embedding-reranker-guide)) |
| **Embeddings, managed** | **Gemini Embedding 2** | MTEB 68.17 at 1536 dims, 100+ languages, multimodal, Matryoshka 128–3072, Batch API 50% off ([Google](https://ai.google.dev/gemini-api/docs/embeddings)) |
| **Scanned/visual documents where layout is the content** | **ColQwen2-v1.0 (Apache-2.0, ViDoRe 89.3)** stored as multi-vectors in Milvus `StructList` | Avoids the OCR error cascade entirely ([ColPali](https://github.com/illuin-tech/colpali), [Zilliz](https://zilliz.com/news/milvus-3-0-lake-native-vector-database)) |
| **Licensing traps to check before adoption** | FalkorDB **SSPLv1**; Chunkr **AGPL-3.0**; Marker weights **modified OpenRAIL-M with a $5M revenue threshold**; jina-embeddings-v4 **Qwen Research License, non-commercial**; ArangoDB Community **non-commercial, 100 GB**; Elasticsearch **SSPL/ELv2/AGPLv3** vs OpenSearch **Apache-2.0** | ([FalkorDB](https://github.com/FalkorDB/FalkorDB), [Chunkr](https://github.com/lumina-ai-inc/chunkr), [Marker](https://github.com/datalab-to/marker), [Jina](https://jina.ai/en-US/embeddings/), [arango.ai](https://arango.ai/downloads/), [Coralogix](https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/)) |

### Build order (what to do in which quarter)

1. **Fix ingestion.** Parse with Docling/MinerU, validate tables specifically, keep page-level provenance. Without provenance you cannot use the Citations-API pattern later ([Docling](https://github.com/docling-project/docling), [MinerU](https://github.com/opendatalab/MinerU), [MarsDevs](https://www.marsdevs.com/guides/agentic-rag-2026-guide)).
2. **Ship hybrid + rerank and measure it with RAGAS Context Precision/Recall and Faithfulness.** Target the Anthropic-style −49%/−67% range before considering a graph ([Anthropic](https://www.anthropic.com/engineering/contextual-retrieval), [RAGAS](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)).
3. **Add late chunking** (free) then contextual retrieval on the subset of documents where it pays ([OpenReview](https://openreview.net/pdf?id=74QmBTV0Zf), [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)).
4. **Introduce the graph only for identified multi-hop/global question classes**, with a declared ontology and, if facts are time-varying, bi-temporal edges ([arXiv 2506.05690](https://arxiv.org/html/2506.05690v1), [Graphiti](https://github.com/getzep/graphiti)).
5. **Wire the semantic layer for metrics over MCP** and evaluate the agent with question/known-answer cases ([Cube](https://cube.dev/product/semantic-layer)).

### Open gaps in this research

- No Vietnamese-specific embedding or reranker benchmark was found on any fetched page; recommendations rest on documented 100+ language coverage rather than measured Vietnamese retrieval quality.
- Licenses for Memgraph, TigerGraph OSS components, Weaviate, LanceDB, Vespa, Chroma, Microsoft GraphRAG, HippoRAG 2 and Cognee could not be confirmed from the pages fetched and are marked `n.a.` rather than inferred.
- FalkorDB's latest version is inconsistent across its own GitHub surfaces (v4.18.11 on the repo landing page, v4.12.4 in the releases feed); confirm at deploy time.
- Neo4j "Aura Agent" is not documented on the Aura docs landing page; the named product could not be verified.
- Vendor benchmarks (Elastic vs OpenSearch, Cognee BEAM, NVIDIA NeMo Retriever, Vespa cost savings, Microsoft GraphRAG comprehensiveness/diversity) are self-published and were not independently reproduced.

---

## Full source list

**A. Graph databases**
- Neo4j release notes — https://neo4j.com/release-notes/database/
- Neo4j licensing — https://neo4j.com/licensing/
- Neo4j Aura docs — https://neo4j.com/docs/aura/
- neo4j-graphrag-python — https://github.com/neo4j/neo4j-graphrag-python
- Neo4j GraphRAG for Python (docs) — https://neo4j.com/developer/genai-ecosystem/graphrag-python/
- FalkorDB GitHub — https://github.com/FalkorDB/FalkorDB
- FalkorDB releases — https://github.com/FalkorDB/FalkorDB/releases
- FalkorDB docs — https://docs.falkordb.com/
- FalkorDB product site — https://www.falkordb.com/
- Memgraph release notes — https://memgraph.com/docs/release-notes
- Memgraph 3.8 release — https://memgraph.com/blog/memgraph-3-8-release-atomic-graphrag-vector-single-store-parallel-runtime
- Kùzu GitHub (archived) — https://github.com/kuzudb/kuzu
- PuppyGraph on KuzuDB / Apple acquisition — https://www.puppygraph.com/blog/what-is-kuzudb
- NebulaGraph downloads — https://www.download.nebula-graph.io/
- NebulaGraph posts — https://nebula-graph.io/posts
- Amazon Neptune — https://aws.amazon.com/neptune/
- Bedrock Knowledge Bases GraphRAG GA — https://aws.amazon.com/blogs/machine-learning/announcing-general-availability-of-amazon-bedrock-knowledge-bases-graphrag-with-amazon-neptune-analytics/
- Neptune Analytics new regions (Jan 2026) — https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-neptune-analytics-generally-available-additional-regions/
- TigerGraph docs home — https://www.tigergraph.com/docs/home/
- TigerGraph 4.3 blog — https://www.tigergraph.com/blog/tigergraph-4-3-built-for-enterprise-security-integration-and-scale/
- TigerGraph GraphRAG v2 — https://graphwiz.ai/content/graphs/tigergraph-graphrag-v2-agentic-mcp/
- Apache AGE downloads — https://age.apache.org/download/
- ArangoDB EOL data — https://www.eol.wiki/arangodb/
- ArangoDB downloads/licensing — https://arango.ai/downloads/
- GQL (ISO/IEC 39075) overview — https://en.wikipedia.org/wiki/Graph_Query_Language
- ISO/IEC 39075:2024/Cor 1:2026 — https://standards.iteh.ai/catalog/standards/iso/e9bee956-a206-4886-bbc7-97c3684e6f76/iso-iec-39075-2024-cor-1-2026
- IEC Webstore, Cor 1:2026 — https://webstore.iec.ch/en/publication/115503

**B. GraphRAG frameworks**
- Microsoft GraphRAG project — https://www.microsoft.com/en-us/research/project/graphrag/
- LazyGraphRAG — https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
- LightRAG — https://github.com/HKUDS/LightRAG
- HippoRAG 2 (arXiv 2502.14802) — https://arxiv.org/abs/2502.14802
- HippoRAG 2 third-party summary — https://memorypapers.org/papers/hipporag-2-rag-to-memory
- nano-graphrag — https://github.com/gusye1234/nano-graphrag
- Graphiti — https://github.com/getzep/graphiti
- Thoughtworks Radar: Graphiti — https://www.thoughtworks.com/en-us/radar/platforms/graphiti
- Cognee 1.0 announcement — https://www.cognee.ai/cognee-1-0-announcement
- Cognee releases — https://github.com/topoteretes/cognee/releases
- LlamaIndex PropertyGraphIndex guide — https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/
- Neo4j LLM Knowledge Graph Builder — https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/
- When to use Graphs in RAG (arXiv 2506.05690) — https://arxiv.org/html/2506.05690v1
- GraphRAG-Bench repo — https://github.com/GraphRAG-Bench/GraphRAG-Benchmark
- GraphRAG variants compared 2026 — https://graphwiz.ai/graphrag-variants-compared-2026/
- GraphRAG vs vanilla RAG comparison — https://www.merciv.com/blog/graphrag-vanilla-rag-comparison

**C. Vector databases**
- Qdrant GitHub — https://github.com/qdrant/qdrant
- Qdrant hybrid search — https://qdrant.tech/articles/hybrid-search/
- Milvus release notes — https://milvus.io/docs/release_notes.md
- Milvus 3.0 lake-native — https://zilliz.com/news/milvus-3-0-lake-native-vector-database
- Zilliz Cloud changelog — https://docs.zilliz.com/docs/changelogs
- Weaviate release notes — https://docs.weaviate.io/weaviate/release-notes
- Weaviate 1.39 + search effort tiers — https://newsletter.weaviate.io/p/new-search-effort-tiers-and-weaviate-1-39
- pgvector 0.8.2 (CVE-2026-3172) — https://www.postgresql.org/about/news/pgvector-082-released-3245/
- pgvectorscale — https://github.com/timescale/pgvectorscale
- Pinecone 2026 release notes — https://docs.pinecone.io/release-notes/2026
- Pinecone pricing — https://www.pinecone.io/pricing/
- Pinecone cohere-rerank-3.5 deprecation — https://docs.pinecone.io/models/cohere-rerank-3.5
- LanceDB releases — https://github.com/lancedb/lancedb/releases
- LanceDB July 2026 newsletter — https://www.lancedb.com/blog/newsletter-july-2026
- Vespa newsletter Sept 2026 — https://blog.vespa.ai/vespa-newsletter-sept-2026/
- Vespa press releases — https://vespa.ai/press-releases/
- Elasticsearch vs OpenSearch — https://coralogix.com/guides/elasticsearch/elasticsearch-vs-opensearch-key-differences/
- Elastic filtered vector search benchmark — https://www.elastic.co/search-labs/blog/opensearch-vs-elasticsearch-filtered-vector-search
- Elastic Q3 2026 earnings call (BBQ/ACON) — https://www.theglobeandmail.com/investing/markets/stocks/ESTC/pressreleases/458265/elastic-estc-q3-2026-earnings-call-transcript/
- Chroma changelog — https://www.trychroma.com/changelog
- Chroma 1.0 — https://www.trychroma.com/project/1.0.0
- Turbopuffer pricing log — https://turbopuffer.com/docs/pricing-log
- Turbopuffer roadmap — https://turbopuffer.com/docs/roadmap
- Turbopuffer vs Pinecone migration (Cursor/Notion) — https://particula.tech/blog/turbopuffer-vs-pinecone-vector-database-migration

**D. Embeddings & rerankers**
- Gemini embeddings docs — https://ai.google.dev/gemini-api/docs/embeddings
- Gemini Embedding paper (arXiv 2605.27295) — https://arxiv.org/abs/2605.27295
- Gemini Embedding GA blog — https://developers.googleblog.com/gemini-embedding-available-gemini-api/
- OpenAI text-embedding-3-large — https://developers.openai.com/api/docs/models/text-embedding-3-large
- OpenAI new embedding models — https://openai.com/index/new-embedding-models-and-api-updates/
- Voyage AI pricing — https://docs.voyageai.com/docs/pricing
- Cohere Embed docs — https://docs.cohere.com/docs/cohere-embed
- Cohere Rerank docs — https://docs.cohere.com/docs/rerank
- Cohere pricing / Model Vault — https://cohere.com/pricing
- Qwen3-Embedding & Reranker — https://qwenlm.github.io/blog/qwen3-embedding/
- Qwen3 embedding/reranker serving guide — https://superlinked.com/blog/qwen3-embedding-reranker-guide
- BGE-M3 — https://huggingface.co/BAAI/bge-m3
- bge-reranker-v2-m3 — https://huggingface.co/BAAI/bge-reranker-v2-m3
- Jina embeddings — https://jina.ai/en-US/embeddings/
- Jina AI GitHub (release dates) — https://github.com/jina-ai
- Elastic × Jina announcement — https://ir.elastic.co/News--Events/news/news-details/2026/Elastic-Introduces-Best-in-Class-Embedding-Models-for-High-Performance-Semantic-Search/default.aspx
- NVIDIA NeMo Retriever — https://developer.nvidia.com/nemo-retriever
- NeMo Retriever GitHub — https://github.com/NVIDIA/NeMo-Retriever
- ColPali / ColQwen ViDoRe scores — https://github.com/illuin-tech/colpali
- Mixedbread reranking models — https://www.mixedbread.com/docs/models/reranking
- Mixedbread changelog — https://www.mixedbread.com/docs/changelog
- mxbai-rerank-v2 — https://www.mixedbread.com/blog/mxbai-rerank-v2
- MTEB leaderboard snapshot (Apr 2026) — https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/

**E. Document ingestion**
- Docling — https://github.com/docling-project/docling
- Docling for IBM watsonx GA — https://www.ibm.com/new/announcements/docling-for-ibm-watsonx-turn-complex-documents-into-ai-ready-data
- LF AI & Data DocLang working group — https://lfaidata.foundation/press-release/2026/06/09/lf-ai-data-foundation-launches-doclang-specification-working-group-to-advance-an-open-standard-for-ai-native-documents/
- Unstructured pricing — https://unstructured.io/pricing
- Unstructured Transform MCP — https://aibestnav.com/ai-tools/unstructured/
- LlamaParse docs — https://developers.llamaindex.ai/llamaparse/
- LlamaIndex newsletter 2026-02-24 — https://www.llamaindex.ai/blog/llamaindex-newsletter-2026-02-24
- LlamaParse pricing — https://markaicode.com/pricing/llamaparse-pricing/
- Marker (olmocr-bench) — https://github.com/datalab-to/marker
- MinerU — https://github.com/opendatalab/MinerU
- Reducto parser comparison — https://llms.reducto.ai/document-parser-comparison
- Reducto benchmark guide — https://reducto.ai/guides/document-ai-benchmark-ocr-parsing-extraction
- Azure AI Document Intelligence overview — https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview?view=doc-intel-4.0.0
- Azure Content Understanding at Build 2026 — https://devblogs.microsoft.com/foundry/whats-new-in-azure-content-understanding-at-build-2026/
- Chunkr — https://github.com/lumina-ai-inc/chunkr
- Apache Tika — https://tika.apache.org/
- PaddleOCR-VL-1.6 on OmniDocBench v1.6 — https://centrix.digital/paddleocr-vl-1-6-dat-963-tren-omnidocbench-v1-6/
- SenOCR-Vi — https://huggingface.co/VietAlphaLabs/SenOCR-Vi
- ViDocParse (Vietnamese benchmark) — https://openreview.net/forum?id=Vkeag2cpRN

**F. Ontology & semantic layer**
- Protégé software — https://protege.stanford.edu/software/
- Protégé GitHub — https://github.com/protegeproject/protege
- rdflib — https://rdflib.dev/
- Ontotext GraphDB release notes — https://graphdb.ontotext.com/documentation/master/release-notes.html
- Stardog platform — https://www.stardog.com/platform/
- Palantir Foundry Ontology semantic search — https://palantir.com/docs/foundry/ontology/overview-semantic-search/
- Semantic layer tools 2026 / Apache Ossie (OSI) — https://datus.ai/blog/semantic-layer-tools-list-osi/
- Cube semantic layer — https://cube.dev/product/semantic-layer
- Semantic layer pricing comparison — https://colrows.com/blogs/semantic-layer-pricing-comparison/
- Semantic layer tools compared — https://www.allocatingintelligence.com/semantic-layer-tools-dbt-cube-atscale-compared

**G. Cross-cutting**
- Azure AI Search agentic retrieval — https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview
- Azure AI Search what's new — https://learn.microsoft.com/en-us/azure/search/whats-new
- Anthropic Contextual Retrieval — https://www.anthropic.com/engineering/contextual-retrieval
- Late Chunking (OpenReview PDF) — https://openreview.net/pdf?id=74QmBTV0Zf
- Contextual retrieval vs late chunking — https://particula.tech/blog/contextual-retrieval-vs-late-chunking
- Hybrid + neural rerank benchmark (arXiv 2604.01733) — https://arxiv.org/pdf/2604.01733
- RAGAS available metrics — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- LLM evaluation frameworks compared — https://atlan.com/know/llm-evaluation-frameworks-compared/
- Agentic RAG 2026 production guide — https://www.marsdevs.com/guides/agentic-rag-2026-guide
- Agentic RAG retrieval patterns — https://www.brightter.com/articles/agentic-rag-five-retrieval-patterns-that-survive-production
