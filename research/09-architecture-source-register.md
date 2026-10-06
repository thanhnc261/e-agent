# Nguồn bổ sung về packages, plugins và kiến trúc có thể phát triển

**Ngày truy cập:** 06/10/2026. Bổ sung cho [sổ nguồn ban đầu](05-source-register.md). Các nguồn dưới đây là tài liệu chính thức hoặc tác giả gốc, dùng để đối chiếu pattern/cơ chế. Cấu trúc sáu package là đề xuất riêng cho dự án, không phải cấu trúc được nguồn nào chứng nhận.

| ID | Nguồn | Nội dung sử dụng và giới hạn |
|---|---|---|
| A01 | [Alistair Cockburn — Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture) | Ports/adapters và cô lập application khỏi UI/DB. Không quy định số package hoặc framework agent. |
| A02 | [OpenTelemetry — Library Guidelines](https://opentelemetry.io/docs/specs/otel/library-guidelines/) | Phân tách API/SDK và plugin/exporter implementation. Học cách tổ chức extension; không sao chép toàn bộ kiến trúc telemetry sang agent. |
| A03 | [Backstage — Extension Points](https://backstage.io/docs/backend-system/architecture/extension-points/) | Public extension API tách khỏi implementation, interface hẹp. Pattern từ hệ sinh thái TypeScript, không phải Python SDK dùng trực tiếp. |
| A04 | [Backstage — Backend Plugins](https://backstage.io/docs/backend-system/architecture/plugins/) | Plugin isolation và quản lý state để hỗ trợ vận hành. Logical isolation không đồng nghĩa sandbox bảo mật. |
| A05 | [PyPA — Creating and Discovering Plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) | Discovery qua naming, namespace, entry points. Admission/allowlist/signature policy là phần dự án phải bổ sung. |
| A06 | [pluggy documentation](https://pluggy.readthedocs.io/en/stable/) | Hook specifications và implementations. Không phải authorization boundary hoặc sandbox. |
| A07 | [HashiCorp — go-plugin](https://github.com/hashicorp/go-plugin) | Subprocess/RPC plugin pattern và lifecycle. Thư viện Go không được chọn làm dependency Python MVP. |
| A08 | [VS Code — Extension Host](https://code.visualstudio.com/api/advanced-topics/extension-host) | Extension có các execution host khác nhau. Nguồn tham khảo phân biệt plugin với deployment location. |
| A09 | [uv — Workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) | Multi-package workspace, lockfile chung và giới hạn dependency isolation. Workspace không tự chặn undeclared imports. |
| A10 | [uv — Building Distributions](https://docs.astral.sh/uv/concepts/projects/build/) | Build distributions để kiểm tra artifacts. Việc build thành công chưa chứng minh wheel đủ resources/dependencies. |
| A11 | [PyPA — src Layout vs Flat Layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) | Giảm nguy cơ import code trực tiếp từ repository thay vì installed package. Vẫn cần clean-install tests. |
| A12 | [Import Linter](https://import-linter.readthedocs.io/en/stable/) và [Configuration](https://import-linter.readthedocs.io/en/stable/get_started/configure/) | Khai báo/kiểm tra import contracts. Không kiểm soát đầy đủ dynamic imports hay runtime security. |
| A13 | [Pydantic AI — Deferred Tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) | Cơ chế defer/external tool execution làm ứng viên cho host-controlled action gateway. Cần spike xác minh semantics và version trước khi chọn. |
| A14 | [Temporal — Python Workflow Versioning](https://docs.temporal.io/develop/python/workflows/versioning) | Nâng cấp workflow đang chạy cần cơ chế versioning tương ứng. Không hàm ý MVP bắt buộc dùng Temporal. |
| A15 | [Semantic Versioning](https://semver.org/) | Public API và ý nghĩa version; major zero chưa là API ổn định. SemVer không thay thế behavioral conformance tests. |
| A16 | [JSON Schema — Draft 2020-12](https://json-schema.org/draft/2020-12) | Wire schema validation có dialect rõ. Schema hợp lệ không bảo đảm business validity hoặc backward compatibility. |
| A17 | [CloudEvents](https://cloudevents.io/) | Chuẩn hóa event envelope khi cần interoperability. Không cung cấp delivery ordering hoặc exactly-once execution. |

## Cách đọc bằng chứng

- Các tài liệu dự án có thể thay đổi theo thời gian; khi implementation bắt đầu cần pin thư viện và đối chiếu lại API tương ứng.
- Pattern từ OpenTelemetry, Backstage, VS Code và HashiCorp là phép đối chiếu thiết kế, không phải bằng chứng thực nghiệm rằng e-agent đã đạt mức vận hành của các dự án đó.
- Lựa chọn modular monolith, sáu distributions, PostgreSQL, một framework driver và các test gates là khuyến nghị theo phạm vi hiện tại. Chưa benchmark các lựa chọn thay thế.
- Nguồn về ontology, enterprise controls và nghiên cứu agent nằm trong [05](05-source-register.md); đợt bổ sung này tập trung vào tổ chức code, extension và vòng đời nâng cấp.
