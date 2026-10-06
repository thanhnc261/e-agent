# Industry và nghiên cứu: cơ sở cho kiến trúc

**Ngày đối chiếu:** 06/10/2026. Đọc cùng [sổ nguồn](05-source-register.md). Các khuyến nghị dưới đây là tổng hợp cho dự án, không phải một “chuẩn enterprise agent” duy nhất đã được thị trường thống nhất.

## 1. Các tín hiệu industry đáng đưa vào thiết kế

| Tín hiệu có bằng chứng | Ý nghĩa đối với e-agent | Mức chắc chắn và giới hạn |
|---|---|---|
| Anthropic phân biệt workflow có đường đi được lập trình và agent tự quyết định bước tiếp theo; khuyến nghị pattern đơn giản, composable. [Nguồn](https://www.anthropic.com/engineering/building-effective-agents) | Dùng workflow cho trình tự bắt buộc; cho model lựa chọn trong phạm vi một bước có giới hạn | Kinh nghiệm nhà cung cấp; không phải thử nghiệm so sánh toàn ngành |
| Thiết kế Managed Agents của Anthropic tách harness, môi trường thực thi và session qua interface. [Nguồn](https://www.anthropic.com/engineering/managed-agents) | Tách agent loop khỏi sandbox và state để nâng cấp từng phần | Tín hiệu kiến trúc từ một nhà cung cấp, không chứng minh khả năng chuyển mọi session giữa vendor |
| MCP chuẩn hóa tương tác với tool/resource; A2A mô tả giao tiếp, task và discovery giữa agent. [MCP security](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices), [A2A](https://a2a-protocol.org/latest/specification/) | Có adapter riêng cho tool và remote agent; giữ hợp đồng nghiệp vụ nội bộ | Tương thích giao thức không chứng minh tương đương quyền hay độ tin cậy |
| Agent Skills cung cấp định dạng đóng gói hướng dẫn và tài nguyên, với nội dung được nạp theo nhu cầu. [Đặc tả](https://agentskills.io/specification) | Import skill vào registry như artifact được version và review | Hướng dẫn trong skill không phải cơ chế cưỡng chế quyền |
| AWS tài liệu hóa gắn Policy Engine vào AgentCore Gateway. [Nguồn](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/create-gateway-with-policy.html) | Policy enforcement nên nằm ở cổng thực thi ngoài quyết định của model | Phải kiểm tra tính năng, mode enforcement và phạm vi triển khai cụ thể |
| Temporal có Activities cho I/O; LangGraph có checkpointer/store; Pydantic AI có tích hợp durable execution. [Temporal](https://docs.temporal.io/activities), [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence), [Pydantic AI](https://ai.pydantic.dev/durable_execution/) | Tách quyết định không xác định khỏi lưu trạng thái, retry và chờ người duyệt | Các cơ chế khác nhau về đơn vị replay và vận hành; không thể so bằng cột “durability: yes” |
| Palantir Ontology kết hợp đối tượng, quan hệ với action/function. [Nguồn](https://www.palantir.com/docs/foundry/ontology/overview/) | Domain pack nên đóng gói cả tri thức và hành động được phép trên đối tượng | Mẫu sản phẩm hữu ích; không đồng nghĩa với OWL hoặc một chuẩn semantic-web |
| NIST có AI Agent Standards Initiative tập trung tiêu chuẩn, giao thức và nghiên cứu identity/security. [Nguồn](https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative) | Dành chỗ cho thay đổi identity/delegation/protocol mà không viết lại nghiệp vụ | Đây là sáng kiến tiêu chuẩn hóa; không được quảng bá hệ thống là “NIST-certified agent” |

**Suy luận cho dự án:** điểm ổn định nên là identity, policy, bằng chứng, trạng thái hành động và ngữ nghĩa nghiệp vụ. Model, harness, planner và thuật toán retrieval được phép thay đổi nhanh. Không cần tự viết lại framework; cần kiểm soát các ranh giới mà framework đi qua.

## 2. Ma trận nghiên cứu và cách áp dụng

Các hàng sau chỉ mô tả đóng góp và kết quả trong phạm vi bài gốc. Không suy rộng điểm benchmark sang dữ liệu doanh nghiệp hoặc tiếng Việt.

| Nghiên cứu | Đóng góp liên quan | Áp dụng đề xuất | Điều chưa chứng minh |
|---|---|---|---|
| [CoALA — Cognitive Architectures for Language Agents, 2023/2024](https://arxiv.org/abs/2309.02427) | Tổ chức agent theo memory, action space và decision process; bản v3 ghi TMLR camera-ready | Tách working/episodic/semantic/procedural memory; định nghĩa interface cho cập nhật memory | Không cung cấp schema ontology enterprise chuẩn hoặc bảo đảm tuân thủ |
| [BDI Agents: From Theory to Practice, 1995](https://aaai.org/papers/icmas95-042-bdi-agents-from-theory-to-practice/) | Phân biệt belief, desire và intention trong kiến trúc tác tử | Phân biệt thông tin agent đang tin, mục tiêu và kế hoạch đã cam kết | Mô hình LLM không tự trở thành một BDI agent có bảo đảm hình thức; trang tóm tắt được tìm thấy nhưng mở trực tiếp lỗi |
| [Reflexion, 2023](https://arxiv.org/abs/2303.11366) | Dùng phản hồi bằng ngôn ngữ và episodic memory để điều chỉnh lần thử sau | Lưu lesson có nguồn và phạm vi; đánh giá trước khi tái sử dụng | Tự phản tư không chứng minh lesson đúng; có thể tích lũy kết luận sai |
| [MemGPT, 2023](https://arxiv.org/abs/2310.08560) | Quản lý nhiều tầng memory trong giới hạn context | Context là working set; có retrieval, eviction và quota rõ ràng | Không thay thế governance về retention, ACL hay chất lượng fact |
| [GraphRAG, 2024; v2 2025](https://arxiv.org/abs/2404.16130) | Entity graph và community summaries hỗ trợ câu hỏi tổng hợp toàn corpus | Thử cho câu hỏi chủ đề/chính sách liên phòng ban | Kết quả global sensemaking không chứng minh ưu thế cho mọi fact lookup |
| [HippoRAG 2, ICML 2025](https://arxiv.org/abs/2502.14802) | Kết hợp passage, graph và Personalized PageRank cho factual/associative memory | Là retriever thử nghiệm cho liên kết nhiều bước | Cảm hứng sinh học không đồng nghĩa mô hình nhận thức đã được xác thực |
| [When to use Graphs in RAG / GraphRAG-Bench, 2025](https://arxiv.org/abs/2506.05690) | Đánh giá graph, retrieval và generation theo độ phức tạp câu hỏi | Chia tập eval theo loại câu hỏi, không gộp một điểm trung bình | Hiệu quả phụ thuộc dataset, graph construction và cách query |
| [τ-bench, 2024](https://arxiv.org/abs/2406.12045) | Kiểm tra tương tác user–tool–agent, policy và trạng thái DB cuối; đánh giá độ ổn định qua nhiều lần thử | Chấm trạng thái nghiệp vụ thực, thêm repeated trials | User mô phỏng và miền benchmark không đại diện toàn bộ doanh nghiệp |
| [AgentDojo, 2024](https://arxiv.org/abs/2406.13352) | Môi trường thử prompt injection và defenses cho tool-using agents | Tạo corpus tấn công trong tài liệu, tool output và email giả lập | Kết quả phòng thủ trên tập biết trước không bảo đảm hết tấn công |
| [Towards a Science of AI Agent Reliability, ICML 2026](https://arxiv.org/abs/2602.16666) | Tách reliability thành consistency, robustness, predictability, safety | Dashboard nhiều chiều; phân loại mức nghiêm trọng của lỗi | Không dùng một task-success score để quyết định cấp quyền tự động |
| [Competency Questions for Ontologies, 2024](https://arxiv.org/abs/2412.13688) | Phân tích loại câu hỏi để xác định và đánh giá phạm vi ontology | Viết câu hỏi nghiệp vụ trước khi thêm class/property | Sinh câu hỏi bằng LLM không thay domain expert xác nhận ý nghĩa |

## 3. Bổ sung và điều chỉnh cách diễn giải hai tài liệu gốc

Đây là review các điểm tác động đến kiến trúc, không phải audit toàn bộ số liệu thị trường.

| Điểm trong báo cáo gốc | Cách dùng trong thiết kế mới |
|---|---|
| “Exactly-once side effects” đi cùng durable runtime | Không mặc định cho mọi external API. Temporal khuyến nghị Activity idempotent vì retry có thể lặp tác dụng phụ. Bổ sung action ledger, downstream idempotency key và reconciliation. [Nguồn](https://docs.temporal.io/activities) |
| Giữ approval sau khi resume | Giữ record để audit; trước lúc thực thi phải kiểm tra expiry, thay đổi tham số, resource version, quyền hiện tại và revocation. Đây là yêu cầu thiết kế bổ sung, không phải tính năng đã được xác minh cho mọi runtime |
| Dùng các mức giảm lỗi retrieval do vendor công bố như mục tiêu mặc định | Anthropic báo cáo cải thiện trong thử nghiệm contextual retrieval; dùng làm giả thuyết benchmark, không đặt tỷ lệ đó thành cam kết cho corpus mới. [Nguồn](https://www.anthropic.com/engineering/contextual-retrieval) |
| “Graph tốn 2.3×”, giảm accuracy 13.4%/16.6%, tăng 4.5% | Các số này có trong phần mở đầu của paper được dẫn, nhưng dẫn lại nghiên cứu trước đó. Không coi là hằng số chi phí/accuracy của GraphRAG. Cần truy nguyên thí nghiệm và benchmark lại. [Bản v1, Introduction](https://arxiv.org/html/2506.05690v1) |
| “Neo4j GPL buộc mọi enterprise closed-source phải mua commercial” | Không dùng kết luận tuyệt đối này để ra quyết định. Xét đúng artifact/edition, cách tích hợp và phân phối, license thực tế và hỗ trợ cần mua. Trang hãng liệt kê Community GPLv3 cùng các điều khoản riêng. [Nguồn](https://neo4j.com/legal-terms/) |
| “Never let agent compute metrics” | Chuẩn hóa định nghĩa metric và thực thi bằng query/tool được quản trị; agent vẫn có thể gọi phép tính xác định trên dữ liệu đã được cấp quyền. Cần kiểm soát định nghĩa, lineage và phép toán, không cấm mọi computation |
| Graph schema/Pydantic được gọi chung là ontology | Schema extraction hữu ích nhưng chưa đủ ngữ nghĩa liên miền, identity, temporal claim, constraints và governance. Tách ontology, validation schema và storage schema |
| Chọn đồng thời pgvector + pgvectorscale + AGE làm default | Chưa có workload chứng minh cần ba extension. PoC chọn ít thành phần, kiểm tra version compatibility/backup/HA trước khi thêm extension |
| Multilingual benchmark ngụ ý chất lượng tiếng Việt | Cần tập kiểm tra tiếng Việt riêng: dấu, tên pháp nhân, viết tắt, bảng, số tiền, ngày và tài liệu scan |

## 4. Chọn runtime theo tình huống

Đề xuất dưới đây dựa trên nhu cầu vận hành, chưa phải kết quả bake-off của repo.

| Hướng | Khi phù hợp | Chi phí/trade-off | Cổng quyết định |
|---|---|---|---|
| Agent loop typed + Temporal | Workflow dài, chờ duyệt, nhiều side effects, cần lịch sử phục hồi | Thêm workers/control service và quy tắc workflow determinism | Crash/retry không tạo giao dịch trùng; resume và nâng version chạy đúng |
| LangGraph + persistent checkpointer | Agent state graph là cấu trúc chính, nhu cầu flow linh hoạt | State/checkpoint phụ thuộc runtime; cần audit side effects riêng | Chứng minh replay boundary, cancellation, timeout và migration |
| Managed agent platform | Đã có cloud mandate, đội vận hành nhỏ | Region, tính năng theo edition, phụ thuộc control plane và chi phí thoát | Xuất được evidence/state nghiệp vụ; IAM, residency và contract thỏa yêu cầu |
| Loop tự viết rất nhỏ | Workflow hẹp, cần kiểm soát cao, ít state | Tự chịu trách nhiệm retry, lifecycle và vận hành | Chỉ chọn khi framework không giảm đáng kể công sức; không tự xây cả orchestration engine |

**Lựa chọn khởi đầu đề xuất:** Python cho PoC (giả định, có thể đổi theo đội), typed contracts, một loop adapter; Temporal làm ứng viên durability nếu có workflow ghi/chờ duyệt. Benchmark thêm phương án LangGraph với persistent checkpointer. Chỉ giữ một phương án chính sau PoC; không chạy hai scheduler cùng retry một action.

Năng lực được xác nhận ở tài liệu runtime; việc bọc chúng bằng contract riêng là đề xuất của dự án. [Pydantic AI](https://ai.pydantic.dev/durable_execution/), [Temporal](https://docs.temporal.io/activities), [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence).

## 5. Những xu hướng nên theo dõi, chưa nên khóa kiến trúc vào

- Giao thức agent-to-agent: theo dõi nhưng chỉ bật khi có remote agent/use case cụ thể.
- Memory tự cập nhật, planner tự cải tiến: chạy shadow/offline; không cho tự sửa policy hoặc publish ontology.
- GraphRAG, associative retrieval: giữ dưới retrieval interface; chọn theo bằng chứng trên nhóm câu hỏi liên quan.
- Harness do model vendor cung cấp: cho phép tích hợp native feature qua capability negotiation, nhưng giữ canonical business events và audit độc lập.
- Semantic conventions về GenAI: pin phiên bản exporter/mapping. Trang OpenTelemetry cũ đã chuyển sang repository riêng tại thời điểm đối chiếu. [Nguồn](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

Kết quả cần theo đuổi là **thay một thành phần với chi phí dự đoán được và không mất kiểm soát**, không phải hỗ trợ mọi framework và protocol ngay từ đầu.
