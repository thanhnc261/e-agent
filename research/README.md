# Research: nền tảng agent doanh nghiệp theo kiến trúc plugin

**Ngày tổng hợp:** 06/10/2026 · **Trạng thái:** đề xuất kiến trúc để review và làm PoC.

**Khuyến nghị:** xây một lõi điều phối và kiểm soát nhỏ, ổn định; đưa model, agent framework, công cụ, retrieval và ontology nghiệp vụ vào các module có hợp đồng rõ ràng. Tri thức và quyền thực thi phải thuộc nền tảng, có thể chuyển đổi nhà cung cấp. Bắt đầu bằng một workflow hữu ích, một agent và một miền tri thức có kiểm soát.

## Đọc theo thứ tự

| Tài liệu | Nội dung chính |
|---|---|
| [01 — Industry và nghiên cứu](01-industry-and-research.md) | Bằng chứng từ industry, bài nghiên cứu, giới hạn và điểm cần điều chỉnh trong hai báo cáo gốc |
| [02 — Kiến trúc plugin](02-plugin-driven-architecture.md) | Ranh giới thành phần, plugin contract, quyền, durability, thay framework/model và các ADR đề xuất |
| [03 — Knowledge và ontology](03-knowledge-and-cognitive-ontology.md) | Vòng đời dữ liệu, ontology nghiệp vụ, cognitive ontology, provenance, thời gian, ACL và ví dụ thiết kế |
| [04 — Enterprise controls và lộ trình](04-enterprise-controls-and-roadmap.md) | Control matrix, threat model, eval, tiêu chí nghiệm thu và kế hoạch 12 tuần có điều kiện |
| [05 — Sổ nguồn](05-source-register.md) | Nguồn chính thức/nghiên cứu, loại bằng chứng, nội dung được dùng và giới hạn xác minh |
| [06 — Kế hoạch MVP ERP](06-erp-mvp-delivery-plan.md) | Phạm vi demo dựa trên việc kiểm tra `enterprise-agent/experiment`, tiêu chí chứng minh ontology/ERP và ranh giới Phase 2 |
| [07 — Packages, plugins và adapters](07-package-and-plugin-organization.md) | Đề xuất tổ chức repo sản phẩm: sáu packages, cây thư mục, import rules, plugin lifecycle và versioning |
| [08 — Quyết định và kiểm chứng kiến trúc](08-architecture-decisions-and-fitness.md) | ADR, architecture fitness tests, bài thử thay công nghệ và thứ tự triển khai vertical slice |
| [09 — Nguồn kiến trúc bổ sung](09-architecture-source-register.md) | Nguồn chính thức về extension systems, packaging và compatibility |
| [10 — Review khả năng mở rộng](10-extensibility-architecture-review.md) | Multi-domain, thay tổ chức KB/KG, các mức độc lập và điều chỉnh cấu trúc adapter distributions |

**Để bắt đầu tổ chức code, đọc 10 → 07 → 08.** Tài liệu 10 cập nhật các giới hạn của baseline sáu package, đặc biệt việc tách adapter distributions để phát hành độc lập. Khuyến nghị hiện tại là monorepo với modular monolith, ports/adapters và plugin SDK nhỏ; package không mặc nhiên là service. Repo `e-agent` là nơi đề xuất phát triển sản phẩm; `enterprise-agent/experiment` giữ vai trò thực nghiệm và nguồn tham khảo, không trở thành dependency của sản phẩm.

## Các quyết định quan trọng

1. **Plugin-driven có ranh giới tin cậy:** plugin mở rộng năng lực; không tự thay đổi quyền, audit hoặc cơ chế phê duyệt của nền tảng.
2. **Framework là adapter:** dữ liệu miền nghiệp vụ, lịch sử hành động và ontology không phụ thuộc vào kiểu dữ liệu riêng của framework.
3. **Chỉ một thành phần sở hữu retry và resume của mỗi bước:** phải thiết kế idempotency với hệ thống đích; lưu checkpoint chưa đủ để chống tác dụng phụ trùng.
4. **Knowledge là một data product:** nguồn gốc, chất lượng, quyền, freshness, xóa dữ liệu và người chịu trách nhiệm phải được quản trị cùng nội dung.
5. **Ontology là hợp đồng ngữ nghĩa:** dùng vocabulary/ID chung, ràng buộc và kiểm thử; chỉ thêm reasoner hoặc graph engine khi có nhu cầu đã chứng minh.
6. **Cognitive ontology là giả thuyết thiết kế có thể kiểm chứng:** biểu diễn goal, belief, evidence, plan, action và outcome; không coi đây là chuẩn chứng nhận hoặc mô hình hoàn chỉnh của nhận thức con người.
7. **Mở rộng autonomy theo bằng chứng:** nâng từ đọc → đề xuất → ghi có phê duyệt → tự động có giới hạn sau khi vượt các cổng đánh giá.

## Phạm vi và giả định

- Repo tại thời điểm nghiên cứu có hai báo cáo Markdown, chưa có implementation để kiểm chứng.
- Chưa biết ngành, quy mô, cloud, dữ liệu nhạy cảm, khu vực pháp lý hay ngân sách. Đề xuất lấy trợ lý tri thức nội bộ kết hợp workflow mua sắm làm ví dụ; các ngưỡng và lịch trình là mục tiêu PoC, không phải cam kết SLA.
- Tách ba lớp bằng chứng: **đặc tả/tài liệu chính thức**, **kết quả nghiên cứu hoặc vendor tự báo cáo**, **đề xuất thiết kế của dự án**. Những phần thiết kế không phải tuyên bố rằng một framework đã cung cấp sẵn mọi khả năng.
- Đã đối chiếu các nguồn ảnh hưởng đến quyết định kiến trúc; chưa tái kiểm chứng mọi version, giá, license và số liệu adoption trong hai báo cáo gốc. Cần kiểm tra lại đúng phiên bản/edition/region trước procurement.
- Đối chiếu ISO ở mức trang giới thiệu công khai; chưa thực hiện gap assessment theo toàn văn tiêu chuẩn hoặc đánh giá chứng nhận.

## Hai tài liệu đầu vào

- [Agent Frameworks, Orchestration Runtimes and Managed Agent Platforms — September 2026](18-agent-frameworks-market-2026-09.md)
- [Knowledge Graphs, GraphRAG & the Retrieval Stack — September 2026](19-knowledge-graphs-retrieval-stack-2026.md)

Hai bản gốc được giữ nguyên. Bản bổ sung này chuyển trọng tâm từ danh mục công nghệ sang kiến trúc, kiểm soát và thí nghiệm cần làm để lựa chọn công nghệ.

## Enterprise agent overlay design

[11 — Enterprise agent overlay: research and design](11-enterprise-agent-overlay-design.md) reviews primary enterprise AI design references and specifies the selectable Compact, Workbench, Docked and Workspace surfaces. It extends the UI design without replacing the earlier research reports.

[12 — Modern enterprise agent overlay: research-first UX brief](12-agentic-overlay-ux-research.md) sets the research and candidate-design requirements, including comparable visual directions and honest outcome states.

[13 — Agentic overlay: trend research and interactive design study](13-agentic-overlay-mockup-study.md) adds current primary sources, technology recommendations, an annotated reference board and a standalone synthetic mockup with Calm, AI Presence and Operator directions. Run instructions, screenshots and actual verification notes are linked in the study.

[14 — Enterprise-wide agent experience: research and mockup revision 2](14-enterprise-wide-agent-experience.md) corrects the ERP-centered framing with cross-application work, connection capabilities and identity, read-only answers, independent per-action approvals, missing access and partial outcomes. The procurement prototype is preserved as revision 1.

[15 — Agentic UX patterns: mockup before implementation](15-agentic-ux-patterns-mockup.md) provides a new isolated design study based on the user-supplied pattern library and enterprise UX articles. It includes a source-linked visual rationale, six fictional enterprise scenarios, contextual overlays, per-action review, recovery states and desktop/mobile evidence. Application implementation is paused for this design review.

[16 — Conversation-first enterprise workspace](16-conversation-workspace-revision.md) responds to the owner's rejection of study 03: a focused chat, collapsible navigation and an on-demand artifact workspace on the right. Earlier studies are preserved; this is the current candidate for visual review.
