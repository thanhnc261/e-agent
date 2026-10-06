# Review: nhiều domain, thay KB/KG và tính độc lập của plugin

**Ngày:** 06/10/2026. **Phạm vi:** review thiết kế trong tài liệu 03, 07, 08; chưa có implementation sản phẩm để kiểm chứng. Các thay đổi bên dưới là đề xuất điều chỉnh, không phải kết quả test đã pass.

## 1. Kết luận

| Câu hỏi | Đánh giá thiết kế hiện tại | Việc cần bổ sung |
|---|---|---|
| Hỗ trợ ERP, CRM, Google…? | Có nền tảng, chưa đủ bằng chứng multi-domain | Tách domain khỏi provider; capability binding theo connection; workflow xuyên domain; test host không cài ERP |
| Thay cơ chế tổ chức KB/KG? | Có nguyên tắc tốt ở tài liệu 03; package/port design ở 07 chưa đủ cụ thể | Knowledge module riêng, hợp đồng pipeline/query và migration ngữ nghĩa; không chỉ EvidenceRetriever |
| Packages/plugins tồn tại độc lập? | Có thể build theo distribution; không phải mọi adapter phát hành độc lập | Tách integrations theo artifact khi cần; SDK public, conformance harness và dependency closure sạch |

**Không cần bỏ kiến trúc hiện tại. Cần làm rõ ba ranh giới trước khi viết nhiều code.** Sáu package trước đây là cách thu gọn demo ERP; không phải thiết kế đầy đủ cho mọi miền và cũng không phải giới hạn cố định.

## 2. Nhiều domain: tách nghiệp vụ, provider và connection

Ba trục phải độc lập:

| Trục | Ví dụ | Sở hữu |
|---|---|---|
| Domain | Procurement, CRM, document collaboration, scheduling | Khái niệm, use cases, rules, acceptance criteria |
| Provider/connector | Odoo, Google Drive, Google Calendar | API mapping, auth integration, pagination, rate limits, error semantics |
| Connection | Odoo của công ty A; Google account B; shared-drive scope C | Tenant binding, credential reference, resource grants, sync checkpoint |

CRM là miền nghiệp vụ. Trong review này, “Google” được hiểu là Google Workspace; nếu là Google Cloud hoặc Search thì thêm connector family tương ứng, giữ nguyên cách phân chia. Không tạo một `domain-google` chứa mọi khái niệm nghiệp vụ chỉ vì chúng dùng chung vendor.

Một provider có thể phục vụ nhiều domain; một domain có thể dùng nhiều provider. Tuy vậy không ép tất cả provider vào một API có cùng mẫu số thấp nhất. Capability có schema và feature requirements rõ; provider thiếu tính năng phải trả unsupported hoặc bị loại khi binding, không âm thầm mô phỏng sai.

### Những bổ sung cần thiết

1. **Domain packs độc lập:** `domain-crm`, `domain-procurement` hoặc domain ERP hiện tại có phạm vi được công bố. Kernel không import các pack này. Chỉ tách nhỏ `domain-erp` khi thực sự có owner hoặc API riêng; không tạo nhiều package trống.
2. **Capability contract khác implementation binding:** `crm.customer.lookup.v1` là hợp đồng; Odoo connector là một implementation; `connection_id` xác định tài khoản/hệ thống. Một capability có thể có nhiều binding đã được host đăng ký. Trùng capability ID với định nghĩa khác là lỗi; hai implementation hợp lệ của cùng contract không phải lỗi. Không dùng “last registration wins”.
3. **Connection context do host xác lập:** tenant, principal, connection, grants và credential reference. Agent có thể đề xuất đích nhưng host phải resolve/authorize trước dispatch. Không mặc định lấy connection đầu tiên hoặc dùng credential chung cho mọi tenant.
4. **Workflow xuyên domain thuộc application/workflow module:** gọi public capabilities, không import adapter hoặc query bảng private. Domain CRM không cần import domain ERP chỉ để cùng tham gia workflow.
5. **Shared identity có mapping quản trị:** CRM customer và ERP customer có thể là cùng pháp nhân nhưng không tự ghép bằng tên. Giữ domain-local IDs, mapping provenance, scope và version; chỉ trích shared vocabulary khi có nhu cầu dùng chung thực tế.

Ví dụ: tìm khách hàng trong CRM → tìm hợp đồng trên Drive → đề xuất draft PO trong ERP. Mỗi bước kiểm tra quyền riêng, evidence giữ nguồn; permission đọc Drive không cho phép tạo PO. Workflow ghi từng kết quả. Khi bước cuối lỗi, không có giả định rollback nguyên tử trên cả ba hệ thống; retry/reconcile hoặc compensation phải được định nghĩa cho từng action.

Connector sync cũng không chỉ là một `search()` method. Ví dụ Drive cung cấp cơ chế theo dõi changes; adapter cần quản lý checkpoint và xử lý thay đổi tài nguyên theo semantics của nguồn. [Google Drive — Retrieve changes](https://developers.google.com/workspace/drive/api/guides/manage-changes). Không coi cùng một checkpoint model là tương thích với mọi provider.

## 3. Thay KB/KG: cần tách cả semantics lẫn pipeline

Tài liệu 03 đã phân biệt canonical claims với projections và có correction/deletion/ACL. Thiếu sót nằm ở việc chưa gắn các trách nhiệm đó vào public ports, ownership và package rõ ràng. Một `EvidenceRetriever` chỉ che được query surface; không đủ để thay ingestion, entity resolution, memory hoặc ontology governance.

Đề xuất `knowledge` là module độc lập với kernel; khi triển khai KB ingestion/curation thực, đóng gói thành `e-agent-knowledge`. Package này phụ thuộc contracts/SDK, nhận domain schemas qua registration, không import `domain-erp` hoặc vendor SDK. Chưa cần tạo package rỗng nếu MVP chỉ đọc ontology assets và ERP state trực tiếp.

| Ranh giới đề xuất | Hợp đồng có ý nghĩa | Thay đổi được cô lập |
|---|---|---|
| Source ingestion | Source revision, resource identity, ACL refs, checkpoint, tombstone | Google/ERP/file ingestion |
| Parse/extract | Document structure, evidence locator, candidate claims, extractor version | Parser, chunking, model extraction |
| Resolve/curate | Entity mappings, merge/split history, accepted/disputed claims | Entity resolution và curation strategy |
| Ontology registry | Published bundle, imports/dependencies, mappings, compatibility metadata | Registry/file-backed storage và governance UI |
| Claim store | Versioned claims, provenance, temporal semantics, corrections | Physical canonical storage |
| Projection builder | Input revision, index version, watermark, replay/rebuild | Vector, lexical, property graph, RDF views |
| Evidence query | Authorized query intent, evidence bundle, completeness/freshness | Query strategy hoặc retrieval engine |

Đây là logical seams; chỉ tạo interface công khai cho seam có implementation/use case thật. Public knowledge-specific contracts nên nằm ở `knowledge.api`; adapter cho knowledge có thể phụ thuộc API đó nhưng không internal. Chỉ tách `knowledge-api` distribution riêng khi consumer cần tránh kéo implementation/dependency của toàn package, tương tự cách tách extension API khỏi implementation trong [Backstage](https://backstage.io/docs/backend-system/architecture/extension-points/).

### Contract phải giữ được ý nghĩa

- Query context có tenant/principal đáng tin, resource scope, query intent, domain/schema version và yêu cầu thời gian/freshness. Không để raw Cypher/SPARQL hoặc vendor response tràn vào kernel.
- Evidence trả source revision, locator, claim refs nếu có, provenance, policy context và trạng thái completeness/freshness. `Không có kết quả`, `chưa index`, `không hỗ trợ truy vấn` là trạng thái nội bộ khác nhau; API không được tiết lộ tài nguyên bị cấm qua lỗi khác biệt.
- Adapter khai báo khả năng như temporal query, relation traversal, provenance preservation. Nếu không đáp ứng yêu cầu query thì reject hoặc fallback đã được công bố; không trả kết quả gần đúng như thể đã bảo đảm semantics.
- Chunk ID không phải canonical entity ID. Rechunk/re-embed tạo projection revision mới; evidence cũ cần source revision và locator còn phân giải được trong retention cho phép.
- Working/episodic memory khác curated knowledge. Memory framework không được tự publish fact vào canonical registry.

### Mức độ thay đổi và chi phí

| Thay đổi | Công việc tối thiểu |
|---|---|
| Đổi embedding, chunking, vector engine | Reindex + retrieval evaluation; kiểm tra citation và ACL không mất |
| Thêm graph retrieval bên cạnh search | Projection/mapping + query routing; competency questions và quyền trên path |
| Đổi RDF sang property graph | Mapping semantics và fixtures; không giả định reasoning/constraints tương đương |
| Đổi entity/claim/temporal model | Versioned contracts, data migration, cập nhật domain mappings và consumers |
| Chuyển graph từ projection thành nguồn authoritative | ADR mới về ownership, write path, export/recovery và transactions; không chỉ đổi adapter |

Migration theo thứ tự: snapshot/version → build shadow projection → replay thay đổi phát sinh → kiểm tra CQ, ACL, deletion và freshness → cutover → theo dõi và retire. Rollback projection cũng phải áp dụng tombstones/revocations mới; không khôi phục quyền hoặc nội dung đã bị thu hồi. Không hứa zero-downtime cho mọi semantic migration.

## 4. “Độc lập” có bốn mức

| Mức | Ý nghĩa | Mục tiêu |
|---|---|---|
| Build/install | Cài từ artifact ngoài repo với dependency công bố | Mọi distribution |
| Test/reuse | Test qua public APIs/fakes không cần chạy server toàn hệ thống | Contracts, SDK, domains, knowledge, adapters |
| Version/release | Phát hành riêng, có compatibility range, không buộc cả monorepo cùng version | Các plugin cần được thay/nâng độc lập |
| Execute/deploy | Có host/CLI/process/API riêng và operational contract | Chỉ plugin cần cô lập hoặc vận hành riêng |

Độc lập không có nghĩa zero dependencies. Plugin vẫn cần SDK/contract và các service port được inject. Một plugin library không mặc nhiên là ứng dụng có thể tự chạy; có thể chạy dưới conformance harness hoặc host khác đáp ứng đúng protocol. Không mặc nhiên tương thích với mọi agent framework hoặc runtime của bên thứ ba.

### Điểm cần sửa trong cấu trúc sáu package

`integrations` hiện gộp Odoo, agent framework, PostgreSQL và SHACL vào một distribution. Chúng có thể độc lập ở mức module/test, nhưng **chưa độc lập về artifact/version/release**. Optional extras không tạo ra những artifact độc lập.

Nếu phát hành plugin độc lập là yêu cầu ngay từ MVP, thay package gộp bằng các distributions thực sự được dùng:

```text
packages/
  contracts/
  plugin-sdk/
  kernel/
  domain-erp/
  adapter-agent-<selected-framework>/
  adapter-odoo/
  adapter-postgres/
  adapter-shacl/
apps/
  server/

# Khi có use case thực:
# packages/domain-crm/
# packages/connector-google-drive/
# packages/connector-google-calendar/
# packages/knowledge/
# packages/adapter-knowledge-<selected-store>/
```

Đây là revision được khuyến nghị theo yêu cầu độc lập đang review: số distribution tăng nhưng deployment vẫn là modular monolith. Không tạo Google/CRM packages trước khi có use case. Adapter Odoo dùng `domain-erp.api`; nếu domain pack trở nên nặng hoặc nhiều consumers chỉ cần DTOs, tách domain API distribution khi đó.

Mỗi plugin cần manifest đóng gói, factory không side effects, settings schema riêng, declared dependencies, capability/port requirements và conformance tests. Host cung cấp scoped services; không truyền một global service locator chứa mọi internal/credential. Với RPC plugin cần thêm wire protocol, authentication, deadline/cancellation và error contract; Python Protocol không đủ làm remote protocol.

Monorepo không cản independent releases. Tuy nhiên [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) dùng lockfile chung; dependency conflict vẫn cần environment/process hoặc project riêng. Clean-install CI phải chạy ngoài editable workspace, chỉ cài dependency closure của artifact.

## 5. Những bài thử cần thêm trước khi tuyên bố hỗ trợ tốt

| Test | Bằng chứng cần có |
|---|---|
| Host không có ERP | Cài kernel + test domain plugin, hoàn thành task mà không cài/import ERP/Odoo |
| Multi-domain | CRM stub và ERP fixture cùng hoạt động, workflow không chứa provider type; phân biệt test stub với live integration |
| Multi-binding | Hai connections cùng capability; host chọn đúng tenant/resource; ambiguous target không tự thực thi |
| Partial cross-domain failure | Bước 1 thành công, bước 2 timeout; ledger và recovery không tạo side effect trùng |
| Knowledge replaceability | Hai implementations chạy cùng CQ subset; công bố rõ phần unsupported; giữ provenance/ACL/temporal semantics |
| Knowledge migration | Rechunk/rebuild giữ citation; revoke/delete trong lúc shadow indexing không bị hồi sinh sau cutover/rollback |
| Independent plugin artifact | Build và cài wheel ngoài repo; chạy harness chỉ với SDK + declared dependencies; không cần server source |
| Release compatibility | Host hỗ trợ plugin versions đã công bố; reject incompatible version trước load; test thêm phiên bản dependency được hỗ trợ ngoài workspace lock |

Ưu tiên MVP: host không ERP bằng fixture nhỏ, multi-binding authorization, independent wheel install và một knowledge fixture có source revision/ACL. Live CRM/Google và thay graph engine toàn bộ thuộc phase sau nếu không nằm trong workflow demo. Không gọi các fixture này là bằng chứng hiệu quả trên ERP/CRM thực tế.

## 6. Kết luận sau review

Giữ kernel/domain/provider separation. Bổ sung knowledge ownership và pipeline seams. Tách adapter distributions thực sự dùng khi yêu cầu independent release là bắt buộc. Đánh giá từng mức độc lập bằng artifact và conformance tests; chưa tuyên bố kiến trúc đã hỗ trợ đầy đủ khi mới có tài liệu.
