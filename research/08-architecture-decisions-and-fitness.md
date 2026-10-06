# Quyết định và kiểm chứng kiến trúc MVP

**Ngày:** 06/10/2026. **Trạng thái:** đề xuất; chưa triển khai hoặc chạy các bài thử dưới đây. Áp dụng cho repo sản phẩm `e-agent`, đọc cùng [cấu trúc packages/plugins](07-package-and-plugin-organization.md) và [nguồn](09-architecture-source-register.md).

## 1. Kiến trúc tốt phải đo được chi phí thay đổi

Mục tiêu không phải thay mọi công nghệ mà không sửa code. Mục tiêu là biết thành phần nào cần sửa, dữ liệu nào cần migrate và bộ test nào chứng minh hành vi được giữ. Không dùng số interface hay số plugin làm thước đo chất lượng.

| Phương án | Lợi ích | Chi phí/giới hạn | Lựa chọn đề xuất |
|---|---|---|---|
| Một package có module boundaries | Bootstrap nhanh, ít build metadata | Public API và dependency isolation dễ bị bỏ qua | Có thể phù hợp demo nhỏ, nhưng chưa thể hiện rõ mục tiêu extension của dự án |
| Monorepo, nhiều package, modular monolith | Public contracts rõ, phát hành backend đơn giản, đổi đồng bộ trong một PR | Cần kiểm tra import, wheel và khai báo dependency | Chọn cho MVP; sáu package theo tài liệu 07 |
| Microservices ngay từ đầu | Triển khai/scale độc lập | Distributed transactions, network failures, vận hành và tracing phức tạp hơn | Chỉ tách khi có trust boundary, tải hoặc đội sở hữu thực tế |

Đây là đánh giá thiết kế cho phạm vi dự án, không phải benchmark chứng minh một phương án luôn tốt hơn.

## 2. ADR cần ghi trước khi làm vertical slice

Mỗi ADR ghi bối cảnh, lựa chọn, phương án bỏ qua, hệ quả, owner và điều kiện xét lại. Các quyết định sau đều đang ở trạng thái **proposed**; công nghệ cụ thể cần spike trước khi chốt.

| ADR đề xuất | Quyết định | Khi nào xét lại |
|---|---|---|
| 001 — Deployment | Một backend modular monolith; worker dùng cùng codebase khi cần | Cần cô lập quyền, dependency hoặc scale riêng |
| 002 — Dependency direction | Kernel dùng public ports, composition root chọn implementation | Có use case mới không biểu diễn được qua port hiện tại |
| 003 — Public surface | Contracts và plugin SDK là API công khai; kernel internals là private | Có extension hợp lệ buộc truy cập internal; bổ sung port hẹp trước |
| 004 — Agent execution | Chọn một framework driver; kernel sở hữu quyền thực thi và business state | Conformance/chi phí/tính năng cho thấy driver hiện tại không phù hợp |
| 005 — Plugin activation | Entry points để discovery; allowlist/manifest để admission; không tự cài từ yêu cầu LLM | Có nhu cầu marketplace thì thiết kế riêng supply-chain và sandbox |
| 006 — Side effects | Mọi read/write tool qua action gateway; explicit timeout, idempotency và reconciliation | ERP đích không hỗ trợ cơ chế hiện tại; không che giấu khác biệt |
| 007 — Semantic ownership | Domain pack sở hữu vocabulary, rules, ontology và outcome specs | Domain mới cần shared vocabulary được quản trị chung |
| 008 — Persistence | Một DB; ownership theo module; local transaction bao gồm state/reservation/outbox khi cần | Tách service hoặc yêu cầu dữ liệu buộc đổi transaction boundary |
| 009 — Compatibility | Version riêng cho plugin API, wire schema, ontology và continuation | Có compatibility failure hoặc cần kết thúc hỗ trợ version cũ |
| 010 — Product evidence | Evidence/receipt là dữ liệu có cấu trúc; UI đọc qua application API | Phase 2 cần projection mới; không đọc trực tiếp bảng nội bộ |

## 3. Architecture fitness tests

Các test này bảo vệ hành vi hoặc ranh giới có giá trị; không cần test mỗi getter/interface. Có thể dùng [Import Linter](https://import-linter.readthedocs.io/en/stable/) cho import contracts và test riêng cho runtime admission. Khi thiết lập một gate, cố tình đưa một vi phạm nhỏ vào nhánh test để xác nhận gate thật sự phát hiện được.

| Gate | Tình huống kiểm chứng | Điều kiện pass |
|---|---|---|
| Import boundary | Kernel import Odoo/agent SDK hoặc adapter import kernel internal | CI từ chối; kernel vẫn import/chạy unit tests khi không cài integrations |
| Declared dependencies | Build từng distribution rồi cài wheel trong environment sạch, không dùng workspace source path | Import/public smoke tests chỉ cần dependencies đã khai báo |
| Packaged ontology | Cài domain wheel ngoài repo, load ontology/rules qua package resources | Đủ assets, digest/version đúng; không dựa vào cwd |
| Disabled plugin | Plugin test có marker khi import nhưng bị disable hoặc incompatible | Discovery không tạo marker; activation thất bại trước import implementation |
| Registry integrity | Hai định nghĩa khác nhau cùng capability contract ID, trùng binding ID hoặc manifest không khớp artifact được admission | Startup/activation bị từ chối; nhiều implementation hợp lệ cùng contract dùng binding IDs riêng |
| Gateway enforcement | Driver đề xuất tool gọi ERP; dùng fake executor ghi lại invocation | Chỉ có executor được host cấp mới thực thi; policy deny không có side effect |
| Approval binding | Sửa amount, target, principal hoặc plan digest sau approval | Không dùng được approval cũ; validation lại theo policy hiện hành |
| Tenant scope | Hai tenant có cùng business ID; retrieval/tool request thiếu scope | Không đọc/ghi nhầm; thiếu context bị từ chối trước adapter |
| Mandatory audit | Không thể ghi durable record bắt buộc trước dispatch | Không dispatch action; phân biệt với lỗi optional telemetry |
| Ambiguous execution | ERP nhận lệnh nhưng response timeout | Trạng thái UNKNOWN/pending reconciliation; không retry mù và tạo bản ghi trùng |
| Crash recovery | Dừng worker giữa reservation, dispatch và receipt | Khôi phục đúng các trạng thái đã định nghĩa; dùng ERP sandbox để xác minh side effects |
| Driver conformance | Cùng bộ task chạy qua fake driver và driver đã chọn | Cùng action/evidence semantics; không đòi câu trả lời tự nhiên giống nhau |
| Ontology compatibility | Đổi constraint hoặc vocabulary trong lúc run chờ approval | Biết run dùng version nào; policy xác định revalidation/migration rõ ràng |
| History compatibility | Đọc receipt/event fixture version cũ sau nâng cấp | Reader hỗ trợ đúng compatibility window đã công bố; unknown command bị từ chối |

Gate về import không phải security sandbox. Code không tin cậy trong cùng Python process vẫn có thể truy cập tài nguyên của process; cần isolation và least-privilege thực tế trước khi nhận third-party plugins.

Không đánh đồng fake-driver test với bằng chứng thay framework thành công. Chỉ tuyên bố khả năng thay framework sau khi một driver thứ hai chạy cùng tập conformance, hoặc ghi rõ đây còn là giả thuyết chưa kiểm chứng.

## 4. Các bài thử thay đổi công nghệ

Không xây tất cả adapter ngay MVP. Dùng bảng này làm change-impact checklist; chọn một bài thử thực tế sau khi workflow đầu tiên chạy ổn.

| Thay đổi | Nơi dự kiến thay | Phần phải kiểm chứng, không được giả định |
|---|---|---|
| Đổi model provider | Config và provider mapping trong agent adapter | Tool/schema support, chất lượng task, latency, chi phí; có thể cần đổi prompt |
| Đổi agent framework | AgentDriver implementation, bootstrap, continuation migration/drain | Tool defer/resume, cancellation, streaming, budgets; active runs không tự tương thích |
| Đổi Odoo sang ERP khác | ERP connector adapter và mapping | ID, currency, workflow state, permissions, transaction/idempotency semantics; port/domain có thể phải mở rộng |
| Đổi SHACL implementation | Validator adapter | Supported spec/features, inference mode, normalization của findings; dùng semantic fixtures |
| Thêm graph database | Knowledge adapter, projection/indexing jobs | Provenance, ACL, temporal semantics, deletion, query behavior; không chỉ đổi connection string |
| Đổi PostgreSQL | Persistence adapter, migrations, concurrency tests | Isolation, locks, ordering, durability; không tuyên bố repository interface bảo đảm tương đương |
| Thêm nghiệp vụ ngoài ERP | Domain pack mới + policy/config | Kernel có đang chứa tên trường hoặc quy tắc ERP hardcoded không |
| Thêm durable workflow engine | Orchestration adapter/wiring và version strategy | Owner của retry/checkpoint; tránh hai runtime cùng retry một action |

Ghi lại diff thuộc package nào, thay đổi public API, dữ liệu migrate, số lỗi conformance và thời gian thực hiện. Chỉ đặt mục tiêu định lượng sau bài thử đầu tiên; chưa có cơ sở hứa đổi framework trong vài giờ.

## 5. Nâng cấp và quyền sở hữu dữ liệu

- Mỗi bảng/schema có một module sở hữu write path và migrations. Module khác gọi port thay vì sửa bảng trực tiếp; ban đầu vẫn dùng một DB transaction khi operation cần nguyên tử.
- Dùng expand → migrate/backfill → chuyển reader/writer → contract cho thay đổi DB có deployment overlap. Test trên dữ liệu đại diện, kiểm tra rollback trước khi bỏ cột cũ.
- Run lưu version ontology, capability, plugin artifact và opaque continuation cần thiết để truy nguyên. Revocation hoặc policy an toàn hiện hành có quyền chặn run dù version cũ đã được pin.
- Drain run cũ bằng implementation cũ hoặc migrate tại checkpoint đã kiểm thử. Không khởi tạo lại action đã có side effect chỉ để đổi framework.
- Lockfile giúp tái lập dependency resolution; không tự bảo đảm artifact trust, quyền truy cập hay compatibility của persisted data.

Khi dùng Temporal về sau, lập kế hoạch versioning dựa trên cơ chế của engine và lịch sử workflow thực tế; xem [tài liệu chính thức](https://docs.temporal.io/develop/python/workflows/versioning). MVP chưa cần thêm engine chỉ để có thêm abstraction.

## 6. Thứ tự thực hiện MVP

1. **Chốt một task ERP có outcome đo được.** Ví dụ tạo draft purchase order trong sandbox, có đủ supplier/product/currency và approval trước ghi; xác minh lại bản ghi ERP độc lập với câu trả lời agent.
2. **Tạo workspace và một đường chạy mỏng.** Sáu packages chỉ chứa trách nhiệm cần cho task; thiết lập import gate, wheel install và ontology resource test. Chưa dựng marketplace, generic workflow DSL hoặc microservices.
3. **Spike framework driver.** Chứng minh model đề xuất action, host validate/approve/execute, rồi resume driver. Nếu framework không cho giữ ranh giới này, đổi lựa chọn trước khi mở rộng.
4. **Nối ERP sandbox và validation thật.** Thêm persisted run/receipt, mandatory audit, timeout/reconciliation. Thu evidence từ trạng thái ERP, không chỉ mock hoặc transcript.
5. **Đo chất lượng và giá trị ontology.** Positive/negative tasks, action safety, task success và latency/cost; so sánh ontology với procedural validation tương đương. Không kỳ vọng ontology thắng chỉ vì tên công nghệ.
6. **Chạy một change experiment và đóng gói demo.** Ví dụ driver thứ hai trên cùng fixtures; ghi rõ coverage. Xuất evidence JSON/CLI trước, UI explainable dùng cùng schema ở Phase 2.

Điều kiện kết thúc MVP: một workflow end-to-end chạy lặp lại được, các gate quan trọng ở trên pass trong phạm vi đã công bố, và có bằng chứng ERP outcome. Một bộ thư mục đẹp nhưng chưa chạy task không đạt mục tiêu demo; một demo chỉ happy path cũng chưa chứng minh khả năng phát triển thành ứng dụng doanh nghiệp.

## 7. Kết quả nghiên cứu và phần chưa chứng minh

Đã có đề xuất package boundaries, extension lifecycle, version axes và test plan dựa trên nguồn chính thức. Chưa có code sản phẩm, kết quả benchmark, kiểm định security hoặc kết quả migration framework trong repo này. Các gate là tiêu chí triển khai tiếp theo, không phải kết quả đã pass.
