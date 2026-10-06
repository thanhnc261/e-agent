# Enterprise controls, đánh giá và lộ trình triển khai

**Ngày:** 06/10/2026. Tài liệu chuyển đề xuất kiến trúc thành controls và tiêu chí PoC. Đây chưa phải kết luận hệ thống đạt chuẩn, chứng nhận hoặc đáp ứng pháp luật ngành/khu vực cụ thể.

## 1. “Enterprise-ready” phải gắn với control và evidence

| Nguồn tham chiếu | Ý nghĩa áp dụng | Giới hạn |
|---|---|---|
| [ISO/IEC 42001:2023](https://www.iso.org/standard/42001) | Quản lý AI ở cấp tổ chức: trách nhiệm, vòng đời, đánh giá và cải tiến | Chứng nhận management system có scope; không phải một badge cho agent framework |
| [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) | Quản lý an toàn thông tin và rủi ro | Tính năng encryption/RBAC đơn lẻ không chứng minh conformant |
| [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) | Govern, Map, Measure, Manage để tổ chức AI risk lifecycle | Framework hướng dẫn tự nguyện; không phải chứng nhận sản phẩm |
| [OWASP Agentic Top 10 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | Đầu vào threat modeling cho agent, tool và memory | Danh mục rủi ro không phải danh sách đầy đủ mọi control |
| [NIST Agent Standards Initiative](https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative) | Theo dõi identity, interoperability và agent security | Sáng kiến và tài liệu draft phải phân biệt với chuẩn đã hoàn tất |

Mapping dưới đây là **đề xuất engineering ở mức nhóm control**, không mapping điều khoản ISO. Muốn đánh giá formal phải có toàn văn tiêu chuẩn áp dụng, phạm vi hệ thống và auditor/compliance owner. Ngành, residency, thời hạn retention và nghĩa vụ pháp lý cụ thể còn chưa được xác định.

## 2. Control matrix đề xuất

| ID | Yêu cầu | Điểm cưỡng chế | Evidence nghiệm thu | Owner |
|---|---|---|---|---|
| C01 | Identity user/service/agent tách biệt; delegation có scope/expiry | API gateway, workload identity, credential broker | Trace actor chain; denied impersonation tests; revoke drill | IAM/Security |
| C02 | Least privilege theo tenant, purpose, action, resource | Policy decision service + enforcement ở mọi gateway | Policy tests và decision logs; negative authorization suite | Security/Domain |
| C03 | Plugin không truy cập ngoài capability | Sandbox, egress proxy, credential scope | Network/credential escape tests; sandbox profile | Platform |
| C04 | Approval đúng người, đúng action, còn hiệu lực | Approval service + action digest | Test thay arguments/resource version, expiry, quyền bị thu hồi | Domain owner |
| C05 | Không ghi trùng khi crash/retry | Runtime + action ledger + target idempotency | Fault-injection receipts; final-state reconciliation | Backend/SRE |
| C06 | Không có cross-tenant data leakage | Source ACL, retrieval/graph traversal, cache, model gateway | Adversarial ACL suite qua mọi projection | Data/Security |
| C07 | Fact có provenance, chất lượng và freshness | Ingestion/publish gate + claim registry | Claim-to-source coverage; stale/retracted evidence tests | Data steward |
| C08 | Retention/correction/deletion xuyên mọi bản sao | Catalog + reverse lineage + purge jobs | Deletion report tới vector, graph, memory, cache, logs; backup policy | Privacy/Data |
| C09 | Plugin có chuỗi cung ứng kiểm chứng | Build pipeline + registry admission | Signature, digest, SBOM, provenance, dependency/license review | Platform/Security |
| C10 | Audit bền vững, chống sửa, ít dữ liệu nhạy cảm | Event store/audit sink với quyền ghi riêng | Tamper/access tests, completeness reconciliation, retention policy | Security/SRE |
| C11 | Model/prompt/skill/ontology đổi qua release gate | Version registry + CI/CD + canary | Evals, signed approval, rollback/migration report | AI/Platform |
| C12 | Recovery, availability, bounded workload | Durable state, quotas, circuit breakers, backup/DR | Restore drill, RTO/RPO measurement, load/cancel tests | SRE |
| C13 | Phân biệt unknown/failed/succeeded; abstain khi thiếu bằng chứng | Result verifier + response contract | Final-state checks, unanswerable tests, uncertain outcome queue | Domain/AI |
| C14 | Chi phí và autonomy có giới hạn | Run budget, tool/model quotas, global circuit breaker | Exhaustion tests; alerts; kill-switch exercise | Platform/FinOps |
| C15 | Change approval và vận hành có phân quyền | Admin APIs, registry, policy repo | Developer không tự cấp quyền/publish policy; access review | Governance |
| C16 | Vendor/data exit khả thi | Export contracts, IDs, source catalog, key ownership | Rebuild projection từ export; thay adapter trong môi trường test | Architecture/Data |

Identity workload có thể tham khảo [SPIFFE](https://spiffe.io/docs/latest/spiffe-about/overview/); không bắt buộc SPIFFE nếu IAM hiện có đáp ứng. Tương tự, [SLSA](https://slsa.dev/spec/v1.1/) cung cấp khung provenance nhưng phải xác minh level đạt được. Những control còn lại là yêu cầu thiết kế của e-agent, không tuyên bố được các công cụ này giải quyết tự động.

## 3. Threat model và failure cases ưu tiên

| Kịch bản | Đường lỗi | Mitigation đề xuất | Test quyết định |
|---|---|---|---|
| Prompt injection trong hợp đồng | Nội dung được retrieve yêu cầu gửi dữ liệu ra ngoài | Data/instruction separation, tool allowlist, policy/egress độc lập model | Payload trong PDF/tool result không gây unauthorized call |
| Tool schema/description bị thay | Agent gọi capability rộng hơn đã review | Pin digest/schema; registry quarantine khi thay đổi | Thay description/schema giữa run bị phát hiện/chặn |
| Confused deputy/token passthrough | Agent dùng credential của principal khác hoặc audience khác | Validate issuer/audience, scoped downstream credential, per-client consent | Token sai resource bị từ chối |
| Memory poisoning | Một episode chèn “quy trình” để dùng ở các run sau | Tách candidate/curated/procedural; promotion gate và TTL | Lesson độc hại không được publish thành skill |
| Cross-tenant graph/cache leak | Path, summary hoặc cache chứa nguồn không được xem | ACL ở cả trung gian và artifact suy diễn; cache partition | Hỏi cùng câu ở hai principal không lộ evidence cấm |
| Approval replay | Dùng approval cũ cho số tiền/người nhận mới | Digest, resource version, expiry, single logical operation | Đổi một tham số nhạy cảm làm approval hết hiệu lực |
| Tool commit rồi timeout | Retry tạo hai PO/email/payment | Downstream key, ledger, reconciliation/UNKNOWN | Crash ở từng boundary vẫn không có duplicate commit |
| SSRF/credential exfiltration | Discovery URL/redirect trỏ metadata/internal service | Endpoint validation, DNS/redirect checks, egress policy | URL giả không tới được endpoint cấm |
| Runaway loop/delegation | Agent spawn/recall/tool call lặp | Step/token/time/cost budgets và delegation depth | Hết budget kết thúc có kiểm soát, không tự nâng quota |
| Knowledge bị sửa/xóa nhưng index cũ còn | Agent trả fact hết hiệu lực | Serve-time checks, tombstone, invalidation, watermark | Nguồn đã thu hồi không xuất hiện qua bất kỳ retriever |
| Model fallback vi phạm residency | Private endpoint lỗi, tự gửi prompt ra public model | Policy allowlist theo classification/region | Fallback không hợp lệ bị deny dù giảm availability |

MCP-specific threats được tài liệu hóa trong [Security Best Practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices). Dùng [AgentDojo](https://arxiv.org/abs/2406.13352) làm phương pháp thử injection; suite nội bộ vẫn cần bao phủ tài liệu, ngôn ngữ và hệ thống đích thật.

## 4. Autonomy ladder

| Mức | Khả năng | Điều kiện mở |
|---|---|---|
| A0 | Tìm và tóm tắt dữ liệu đã được phép đọc | ACL, provenance, grounding và abstention đạt gate |
| A1 | Đề xuất kế hoạch/action, không ghi hệ thống ngoài | Typed proposal, policy/precondition validation |
| A2 | Thực thi action cụ thể sau phê duyệt | Durable approval, idempotency/reconciliation, receipt verification |
| A3 | Tự thực thi tập action hạn chế theo policy | Repeated-trial reliability, quota, monitoring, rollback/compensation phù hợp |
| A4 | Workflow nhiều bước trong phạm vi ủy quyền | Delegation, cumulative risk/cost, intermediate checks và incident response |

Không mở mức cao chỉ vì model mới có benchmark tốt hơn. Quyền cấp theo capability và use case; cùng agent có thể A3 cho tạo draft nhưng A1 cho gửi giao dịch có tác động lớn.

## 5. Evaluation design

### 5.1 Bộ dữ liệu và chấm điểm

Đề xuất bắt đầu với **300–500 cases được domain owner xác nhận**, chia theo loại câu hỏi và mức rủi ro; đây là quy mô khởi đầu cho PoC, không chứng minh coverage production. Cần một test set cố định không dùng tuning, một development set và adversarial holdout. Tránh chỉ dùng câu hỏi tổng hợp bởi cùng model đang được chấm.

Các nhóm: fact lookup; exact IDs/từ viết tắt; bảng/số tiền; multi-hop; global summary; temporal/as-of; mâu thuẫn; thiếu bằng chứng; ACL-negative; hành động có side effect; recovery; tiếng Việt/Anh. Số cases cho mỗi nhóm phải theo phân bố production và rủi ro, không chia đều máy móc.

Chấm từ dưới lên:

1. Parser: text/table/cell accuracy, ngày/tiền/đơn vị và source locator.
2. Extraction: entity resolution precision/recall, false merge, relation/claim correctness.
3. Ontology: shape violations, competency-query pass, semantic migration regressions.
4. Retrieval: Recall@k, nDCG, evidence coverage, ACL leaks và freshness.
5. Answer: factual correctness, citation support/coverage, contradiction handling, abstention.
6. Action: final business state, permissions, duplicate effects, policy compliance, recoverability.
7. Operations: p50/p95 latency, cost per successful task, failure/retry rates, recovery time.

LLM judge chỉ là một thành phần: hiệu chỉnh bằng human labels, có blind sampling, đo disagreement và audit các lỗi nghiêm trọng. Dùng deterministic checks cho schema, quyền, số tiền và state transition khi có thể.

### 5.2 Repeated trials và perturbations

Đánh giá ít nhất một tập trọng yếu qua nhiều lần chạy, thay paraphrase, thứ tự dữ kiện, tài liệu nhiễu, timeout và permission changes. `pass^k` biểu diễn độ nhất quán qua k lần, không phải `pass@k` cho phép chọn một lần may mắn. Phương pháp repeated-trial/final-state dựa trên [τ-bench](https://arxiv.org/abs/2406.12045); nhiều chiều reliability dựa trên [Rabanser et al., 2026](https://arxiv.org/abs/2602.16666).

Không cộng các điểm để lỗi critical được bù bằng latency tốt. Báo cáo failure severity, confidence intervals, số mẫu và phân nhóm. Không có lỗi trên một test suite hữu hạn không chứng minh xác suất lỗi bằng 0.

### 5.3 Release gates khởi đầu — đề xuất, phải hiệu chỉnh

| Gate | Ngưỡng PoC đề xuất | Cách hiểu |
|---|---|---|
| Security critical | 0 unauthorized writes, 0 cross-tenant disclosures trong suite bắt buộc | Có một lỗi là chặn release; “0 observed” không phải bảo đảm tuyệt đối |
| Write recovery | 0 duplicate commits trong fault-injection suite; mọi UNKNOWN có đường đối soát | Không đủ chỉ resume đúng đoạn code |
| Evidence metadata | 100% claims được serve có source/derivation + revision + ACL context | Metadata coverage; correctness vẫn chấm riêng |
| Citation support | ≥95% sampled factual claims được evidence hỗ trợ | Tính theo claim với mẫu đủ lớn; domain high-risk có thể cần chặt hơn |
| Answer/task quality | ≥90% task success trên tập scoped low-risk | Kèm repeated-trial và severity; không mở quyền ghi rủi ro cao từ ngưỡng này |
| ACL revocation | Request sau effective revocation bị deny tại gateway | Nếu upstream ACL sync có độ trễ, phải công bố bound; case strict cần online auth hoặc fail closed |
| Knowledge freshness | CDC/structured critical facts: mục tiêu p95 ≤5 phút; batch docs: ≤24 giờ | Ví dụ để đàm phán; quyết định giao dịch phải recheck source hiện tại |
| Latency | Read Q&A mục tiêu p95 ≤8 giây trên workload PoC công bố | Không áp cho workflow nhiều bước hay thời gian chờ human |
| Cost | Budget/request và cost/success không vượt trần do product owner chốt | Chưa có giá/token volume nên chưa đặt một con số USD giả định |
| Reliability/DR | Đo restore thực; mục tiêu ban đầu RPO ≤15 phút, RTO ≤4 giờ | Áp cho KB/metadata phù hợp; ledger của writes đã ack cần yêu cầu nghiêm ngặt hơn và reconcile với target |

Yêu cầu production có thể đòi RPO gần 0 cho dữ liệu giao dịch, multi-zone và DR khác hẳn. Chỉ chốt sau business impact analysis; không sử dụng ngưỡng PoC làm SLA hợp đồng.

## 6. Thí nghiệm quyết định kiến trúc

| Thí nghiệm | So sánh có kiểm soát | Điều kiện chọn |
|---|---|---|
| Retrieval | Lexical+dense+rerank vs thêm graph; cùng model, corpus, token budget | Graph cải thiện nhóm multi-hop/global đủ bù index/query cost; không làm ACL/freshness tệ đi |
| Ontology | Free extraction vs schema-guided extraction + validation | Ít false merge/type errors; CQ coverage tốt hơn; tính cả chi phí steward |
| Cognitive state | Chat-only vs typed state/evidence vs thêm episodic/cognitive graph | Resume, evidence tracking hoặc task success tốt hơn; stale memory không tăng |
| Durability | Hai runtime ứng viên trên cùng workflow approval/write | Crash/retry/cancel/version upgrade đạt gate với chi phí vận hành chấp nhận được |
| Plugin portability | Thay model provider hoặc loop adapter | Domain schema, plugin capability và business events không phải viết lại; quality không giảm vượt tolerance |
| Data portability | Export raw/claims/ontology rồi dựng index mới | CQ và permission tests giữ kết quả; kiểm tra thời gian/cost rebuild |
| Multi-agent | Single-agent baseline vs decomposition thật sự độc lập | Tăng task success/throughput sau khi tính latency, tokens và governance overhead |

Không tối ưu mọi biến một lúc. Ghi experiment config: dataset revision, seed nếu có, model/version, prompt, plugin/ontology versions, permissions, budget và judge rubric.

## 7. Lộ trình 12 tuần có điều kiện

Ước lượng để lập kế hoạch với đội **3–5 kỹ sư và domain/security/data steward tham gia bán thời gian**, sẵn source access và môi trường triển khai. Tuần tính từ kickoff; không phải deadline cố định. Thiếu dữ liệu, quyền truy cập hoặc SME sẽ kéo dài giai đoạn tương ứng.

| Giai đoạn | Deliverables | Exit gate | Phụ thuộc |
|---|---|---|---|
| Tuần 1–2: scope và baseline | Một use case; source inventory; classification; threat model; 30–50 competency questions; eval set v1; ADR runtime | Có domain owner, phép đo business outcome và scoped authorization | SME, dữ liệu mẫu, IAM/security owner |
| Tuần 3–4: nền tảng đọc | Core contracts; plugin registry tối thiểu; identity/policy gateway; ingestion; provenance; hybrid retrieval | A0 với ACL negative tests và evidence lineage; baseline latency/cost | Corpus có ACL và parser quality chấp nhận được |
| Tuần 5–6: hành động có kiểm soát | Durable run; action ledger; approval records; một connector ghi draft; receipts | A2 trong test, vượt crash/retry/revocation tests | Test environment của hệ đích; idempotency/reconciliation |
| Tuần 7–8: ontology và graph pilot | Domain ontology v1; shapes; temporal claims; CQ tests; một graph retriever | Benchmark chứng minh giá trị hoặc quyết định chưa deploy graph | Entity keys và source authority rõ |
| Tuần 9–10: memory và assurance | Typed cognitive state; controlled episodic memory; eval ablation; red-team; data deletion drill | Memory không làm tăng lỗi critical; complete lineage/revocation | Bộ test đủ bao phủ; privacy policy |
| Tuần 11–12: pilot có vận hành | Canary, runbooks, dashboards, backup/restore, rollback, export drill; review gap controls | Product/domain/security/SRE ký readiness theo evidence; mở A3 có chọn lọc nếu đạt | On-call, budget, vendor/region/license review |

Nếu graph hoặc cognitive graph không vượt thí nghiệm, vẫn có thể kết thúc pilot bằng một agent dùng hybrid retrieval và typed state. Điều này giữ nguyên mục tiêu enterprise; không ép thêm công nghệ để hoàn thành checklist.

## 8. Backlog ưu tiên

| Ưu tiên | Epic | Definition of done |
|---|---|---|
| P0 | Canonical contracts | Có schemas và validation cho context, action, receipt, evidence; reject tenant spoofing |
| P0 | Plugin admission và revocation | Install staging, pin digest, tenant grants, revoke; đang chạy/chờ được xử lý rõ |
| P0 | Policy và identity | Mỗi read/write/model call có quyết định quyền; audit nối được actor chain |
| P0 | Source catalog và claim lifecycle | Ingest/update/retract/delete có version và lineage; serve-time ACL |
| P0 | Eval/fault harness | Test ground truth và final states, crash/retry, attack corpus, release gates |
| P0 | Durable writes | Approval, idempotency, UNKNOWN reconciliation, cancellation semantics |
| P1 | Ontology governance | CQ, shapes, review, migration và source authority rules |
| P1 | Retrieval comparison | Hybrid baseline, graph ablation, temporal/cross-tenant coverage |
| P1 | Cognitive state/memory | Schema nhỏ, memory candidates, promotion, TTL và deletion |
| P1 | Operability/exit | Runbooks, observability, DR và export/rebuild drill |
| P2 | A2A/multi-agent marketplace | Chỉ làm sau nhu cầu liên agent được chứng minh và trust model được duyệt |

## 9. Chi phí cần tính trước khi mở rộng

```text
Cost / successful task =
  (model + tools + retrieval + amortized ingestion/indexing
   + storage/compute + human review + operations + failed/retried runs)
  / verified successful tasks
```

Đo riêng chi phí corpus update, graph rebuild, ontology stewardship, tenant isolation và retention. Cache giảm model cost nhưng tăng invalidation complexity; multi-agent tăng token/tool use; graph nhiều projection tăng vận hành. Các trade-off phải hiện trong experiment report.

## 10. Thông tin cần chốt ở kickoff

1. Ngành và 1–2 workflow đầu tiên; hành động nào được phép tự động, hành động nào luôn cần người duyệt?
2. Tenant model, số người dùng, volume tài liệu/truy vấn và latency mục tiêu?
3. Cloud/on-prem, residency, dữ liệu nhạy cảm, vendor/model allowlist?
4. Nguồn có thẩm quyền, owner, entity IDs, ACL APIs và update/deletion feeds?
5. IAM hiện có, audit retention, DR, incident response và các chuẩn/hợp đồng bắt buộc?
6. Ngôn ngữ, tài liệu scan/bảng, chất lượng ground-truth data và availability của SMEs?
7. Đội vận hành, ngân sách và ưu tiên build/buy?

Những câu hỏi này quyết định cấu hình triển khai; chúng không ngăn việc chuẩn bị kiến trúc, contracts và bộ thí nghiệm ở các tài liệu trước.
