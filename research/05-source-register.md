# Sổ nguồn và phạm vi xác minh

**Ngày truy cập/đối chiếu:** 06/10/2026, theo múi giờ Asia/Ho_Chi_Minh.

Nguồn dưới đây được mở bằng công cụ web trong phiên nghiên cứu, trừ hàng ghi rõ chỉ có kết quả tìm kiếm. Không tải/chạy lại benchmark. Bài nghiên cứu chủ yếu được đối chiếu ở trang tác giả/arXiv, abstract, metadata và phần nội dung liên quan khi ghi rõ; bảng này không ngụ ý đã review toàn văn mọi paper. Tài liệu sản phẩm chứng minh khả năng được nhà cung cấp mô tả, không chứng minh chất lượng deployment thực tế.

## 1. Industry, giao thức và runtime

| ID | Nguồn | Loại / nội dung đã dùng | Giới hạn |
|---|---|---|---|
| S01 | [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Engineering, 19/12/2024; workflow/agent và composable patterns | Kinh nghiệm vendor, không phải market-wide controlled study |
| S02 | [Anthropic — Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents) | Engineering; tách harness, session và execution environment | Thiết kế của vendor; không suy ra mọi state portable |
| S03 | [MCP — Security Best Practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices) | Official docs; token audience, confused deputy, SSRF, consent, security boundaries | URL `latest` khi mở chuyển sang docs `2026-07-28`; pin bản cụ thể lúc triển khai |
| S04 | [A2A — Specification](https://a2a-protocol.org/latest/specification/) | Official specification; agent discovery/task interoperability | `latest` thay đổi; chưa chọn protocol version cho PoC |
| S05 | [Agent Skills — Specification](https://agentskills.io/specification) | Official specification; skill packaging và progressive loading | Không phải plugin sandbox/authorization specification |
| S06 | [AWS — Create gateway with Policy Engine](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/create-gateway-with-policy.html) | Official developer guide; policy integration ở gateway | Không dùng để kết luận mọi region/edition có cùng SLA/feature |
| S07 | [Temporal — Activities](https://docs.temporal.io/activities) | Official docs; Activities, retries, idempotency | Tác dụng phụ ngoài Temporal vẫn cần contract ở target |
| S08 | [LangGraph — Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Official docs; checkpointers và cross-thread stores | Đường dẫn durable-execution chuyển tới persistence; chưa benchmark runtime |
| S09 | [Pydantic AI — Durable Execution](https://ai.pydantic.dev/durable_execution/) | Official docs; durable integrations | URL chuyển sang `pydantic.dev/docs/ai/capabilities/durable_execution/overview/`; integrations/version cần kiểm tra khi chọn |
| S10 | [Palantir — Ontology overview](https://www.palantir.com/docs/foundry/ontology/overview/) | Official product docs; semantic và operational/action concepts | Không đồng nhất Palantir Ontology với W3C OWL |
| S11 | [Graphiti — official repository](https://github.com/getzep/graphiti) | Maintainer docs/code repository; temporal graph và custom entity modeling | Chưa audit feature semantics, license từng dependency hoặc reproduce benchmark |
| S12 | [pgvector — official repository](https://github.com/pgvector/pgvector) | Maintainer docs; vector retrieval trong PostgreSQL | Không xem pgvector là lexical/BM25 engine |
| S13 | [Apache Jena — Fuseki](https://jena.apache.org/documentation/fuseki2/) | Official docs; SPARQL serving candidate | Chưa bake-off graph store, sizing/HA/IAM |
| S14 | [Open Policy Agent — Documentation](https://www.openpolicyagent.org/docs) | Official docs; policy engine candidate | Policy language không tự bảo đảm enforcement ở mọi đường I/O |
| S15 | [OpenTelemetry — GenAI conventions move notice](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Official notice; GenAI conventions chuyển repository | Không tuyên bố toàn bộ semantic conventions đã stable |
| S16 | [OpenTelemetry — semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) | Official repository được liên kết từ S15 | Cần pin version/schema mapping cho exporter |

## 2. Chuẩn semantics và ontology engineering

| ID | Nguồn | Loại / nội dung đã dùng | Giới hạn |
|---|---|---|---|
| S17 | [W3C — RDF 1.1 Concepts](https://www.w3.org/TR/rdf11-concepts/) | W3C Recommendation; graph/dataset/IRI model | Chọn baseline tương thích; không khẳng định là mới nhất trong họ RDF |
| S18 | [W3C — OWL 2 Overview](https://www.w3.org/TR/owl2-overview/) | W3C Recommendation; ontology language và profiles | Reasoning profile/tool cụ thể chưa được chọn |
| S19 | [W3C — OWL 2 Primer](https://www.w3.org/TR/owl2-primer/) | W3C Primer; open-world semantics và ý nghĩa domain/range | Primer informative; kiểm tra normative spec khi cần conformance |
| S20 | [W3C — SHACL](https://www.w3.org/TR/shacl/) | W3C Recommendation; graph validation | Validation theo shape không chứng minh factual truth |
| S21 | [W3C — SKOS Reference](https://www.w3.org/TR/skos-reference/) | W3C Recommendation; concept scheme và lexical labels | Không thay entity-resolution logic |
| S22 | [W3C — PROV-O](https://www.w3.org/TR/prov-o/) | W3C Recommendation; provenance entity/activity/agent | Không có sẵn ACL hay retention enforcement |
| S23 | [NIST — Industrial Ontologies Foundry Core Ontology](https://www.nist.gov/publications/industrial-ontologies-foundry-iof-core-ontology) | Publication summary; layered ontology và BFO alignment trong IOF | Bối cảnh industrial; không suy là lựa chọn bắt buộc cho mọi doanh nghiệp |
| S24 | [ISO/IEC 21838-3:2023 — DOLCE](https://committee.iso.org/standard/78927.html?browse=tc) | Trang catalog chính thức; top-level ontology | Chỉ public summary, chưa đánh giá conformity theo toàn văn |
| S25 | [Cognitive Atlas](https://www.cognitiveatlas.org/) | Website dự án nghiên cứu; ontology/KB về cognitive concepts/tasks | Không phải enterprise agent runtime ontology |
| S26 | [Discerning and Characterising Types of Competency Questions for Ontologies](https://arxiv.org/abs/2412.13688) | Paper metadata/abstract, 2024; CQ taxonomy và ROCQS | Dùng phương pháp xác định yêu cầu; chưa reproduce dataset analysis |

## 3. Nghiên cứu agent, memory và retrieval

| ID | Nguồn | Loại / nội dung đã dùng | Giới hạn |
|---|---|---|---|
| S27 | [Sumers et al. — CoALA](https://arxiv.org/abs/2309.02427) | 2023, v3 15/03/2024, TMLR camera-ready theo metadata; memory/action/decision framework | Khung khái niệm; không phải schema enterprise đã chuẩn hóa |
| S28 | [Rao & Georgeff — BDI Agents: From Theory to Practice](https://aaai.org/papers/icmas95-042-bdi-agents-from-theory-to-practice/) | ICMAS 1995; **chỉ xác minh search listing/abstract của AAAI**, mở trực tiếp lỗi | Dùng để dẫn nguồn phân biệt belief/desire/intention; không rút technical claim chi tiết từ full text |
| S29 | [Shinn et al. — Reflexion](https://arxiv.org/abs/2303.11366) | Paper metadata/abstract, 2023; verbal feedback và memory | Không xác minh lesson learned luôn đúng |
| S30 | [Packer et al. — MemGPT](https://arxiv.org/abs/2310.08560) | Paper metadata/abstract, 2023; hierarchical memory/context management | Không suy thành memory governance solution |
| S31 | [Edge et al. — From Local to Global: GraphRAG](https://arxiv.org/abs/2404.16130) | 2024, v2 19/02/2025; community summaries và global sensemaking | Kết quả gắn query class và dataset của tác giả |
| S32 | [Jiménez Gutiérrez et al. — HippoRAG 2](https://arxiv.org/abs/2502.14802) | ICML 2025 theo metadata; associative/factual memory và PPR | Benchmark của tác giả; chưa đo corpus nội bộ |
| S33 | [Xiang et al. — When to use Graphs in RAG](https://arxiv.org/abs/2506.05690) | Paper, 2025; GraphRAG-Bench và evaluation theo độ phức tạp | [Đã mở HTML v1](https://arxiv.org/html/2506.05690v1), kiểm tra Introduction: các số 13.4%, 16.6%, 4.5%, 2.3× dẫn lại prior work, không dùng như hằng số cho thiết kế |
| S34 | [Anthropic — Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | Vendor engineering experiment; contextual lexical/dense retrieval và reranking | Không dùng mức giảm lỗi vendor làm target bảo đảm cho dự án |
| S35 | [Yao et al. — τ-bench](https://arxiv.org/abs/2406.12045) | Paper, 2024; tool/user/policy interaction, final DB state và pass^k | User mô phỏng, giới hạn miền; không dùng kết quả model cũ để kết luận model hiện tại |
| S36 | [Debenedetti et al. — AgentDojo](https://arxiv.org/abs/2406.13352) | Paper, 2024; dynamic prompt-injection evaluation | Không có defense nào được coi là đầy đủ chỉ từ một suite |
| S37 | [Rabanser et al. — Towards a Science of AI Agent Reliability](https://arxiv.org/abs/2602.16666) | 2026, v3 02/06/2026, ICML accepted theo metadata; reliability nhiều chiều | Dùng framework đo; không reproduce 15-model benchmark |

## 4. Governance, security và procurement

| ID | Nguồn | Loại / nội dung đã dùng | Giới hạn |
|---|---|---|---|
| S38 | [NIST — AI Agent Standards Initiative](https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative) | Trang chính thức, ghi tạo 17/02/2026, cập nhật 14/08/2026; standards/protocol/identity research | Sáng kiến, không phải chứng nhận agent |
| S39 | [NIST — AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) | Khung quản lý rủi ro chính thức | Không kết luận compliance của sản phẩm |
| S40 | [ISO/IEC 42001:2023](https://www.iso.org/standard/42001) | Public catalog/overview; AI management system | Chưa đọc toàn văn trả phí; mapping chỉ cấp control family |
| S41 | [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) | Public catalog/overview; information security management | Chưa thực hiện certification gap analysis |
| S42 | [OWASP — Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | Trang resource chính thức; threat-modeling reference | Không tuyên bố matrix nội bộ là full mapping 1:1 toàn tài liệu |
| S43 | [SLSA specification v1.1](https://slsa.dev/spec/v1.1/) | Versioned specification; build/supply-chain provenance reference | Chọn version tham khảo; không khẳng định latest hoặc project đạt level nào |
| S44 | [SPIFFE overview](https://spiffe.io/docs/latest/spiffe-about/overview/) | Official docs; workload identity reference | Cần tích hợp IAM/delegation; không tự giải quyết quyền nghiệp vụ |
| S45 | [Neo4j — Legal terms overview](https://neo4j.com/legal-terms/) | Official vendor page; liên kết Community GPLv3 và điều khoản theo sản phẩm | Không diễn giải nghĩa vụ license cho mô hình triển khai chưa xác định |

## 5. Những gì chưa xác minh và cần nghiên cứu tiếp có mục tiêu

- Toàn bộ version/price/adoption/license trong hai tài liệu đầu vào; không tái sử dụng các con số này làm cơ sở chốt procurement.
- Framework cụ thể có đáp ứng đầy đủ canonical contracts, approval expiry, revocation và replay semantics đề xuất hay không.
- End-to-end ACL của graph/retrieval store, kể cả edition/region, derived summaries, caches và control plane.
- Chất lượng parser, embeddings và reranker trên corpus tiếng Việt của doanh nghiệp.
- Chi phí ontology stewardship, graph maintenance và model/tool usage trên workload thật.
- Pháp luật áp dụng, phạm vi ISO/SOC hoặc control hợp đồng khách hàng yêu cầu; cần domain và jurisdiction trước khi lập mapping chi tiết.
- Upper ontology nào đáng áp dụng: quyết định qua CQ và integration requirements, không qua tên gọi “cognitive”.
- Khả năng export/migrate dữ liệu và adapter theo bài thử trong [lộ trình](04-enterprise-controls-and-roadmap.md).

## 6. Quy tắc duy trì research

Mỗi ADR mới phải gắn evidence: URL, ngày truy cập, phiên bản/edition, loại bằng chứng, experiment nếu có và điều kiện mở lại quyết định. Rà soát định kỳ protocol/security/runtime changes; trigger review ngay khi có deprecation, security advisory, license change hoặc thay đổi requirement. Tài liệu nói “latest” chỉ dùng để discovery, không dùng làm dependency lock.
