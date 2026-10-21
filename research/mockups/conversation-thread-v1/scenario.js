// The one shared procurement scenario, in EN and VI. Every value is fictional (EA-11).
// The thread for each sample state is built from these records only; nothing is generated.
// Run 1: "hi" is a reply run (ADR 0023 §5); "which products are short?" answers it and ends grounded.
// Run 2: "draft a PO for it" starts a new run (run 1 ended, no reply_to), asks a quantity, waits for
// approval, then ends verified. Branches of run 2: failed, cancelled (answer to an ended run).

export const VARIANTS = [
  {
    id: "a1",
    name: { en: "A1 · Run cards", vi: "A1 · Thẻ lượt" },
    summary: {
      en: "Every message stays in the thread, each run ends with a run card. Workspace about 40 % wide. The refusal hint sits inside the composer, above the text.",
      vi: "Mọi tin nhắn ở lại trong luồng, mỗi lượt kết thúc bằng một thẻ lượt. Không gian làm việc rộng khoảng 40 %. Gợi ý từ chối nằm trong ô soạn, phía trên nội dung.",
    },
  },
  {
    id: "a2",
    name: { en: "A2 · Folded runs", vi: "A2 · Lượt thu gọn" },
    summary: {
      en: "Ended runs fold to a one-line run row; only the latest run shows its messages. Narrow fixed workspace (24 rem). The refusal hint is one line under the composer, beside Send.",
      vi: "Lượt đã kết thúc thu gọn thành một dòng; chỉ lượt mới nhất hiện tin nhắn. Không gian làm việc hẹp cố định (24 rem). Gợi ý từ chối là một dòng dưới ô soạn, cạnh nút Gửi.",
    },
  },
  {
    id: "a3",
    name: { en: "A3 · Wide workspace", vi: "A3 · Không gian rộng" },
    summary: {
      en: "Rich run cards with the result line and the earlier runs used as hints. Wide workspace (about 52 %); when closed, a reopen bar keeps the active run's status in view. The refusal hint is a callout above the composer that links to the decision.",
      vi: "Thẻ lượt chi tiết, có dòng kết quả và các lượt trước được dùng làm gợi ý. Không gian làm việc rộng (khoảng 52 %); khi đóng, một thanh mở lại vẫn hiện trạng thái lượt đang chạy. Gợi ý từ chối là khung phía trên ô soạn, có liên kết tới phần quyết định.",
    },
  },
];

// The brief's normative states (research 20, "Roles and states") plus two reference samples.
export const STATES = [
  { id: "empty", brief: "Thread empty", normative: "Ready", label: { en: "Thread empty", vi: "Luồng trống" } },
  { id: "reply", brief: "Reply pending (\"Your turn\")", normative: "Needs input", label: { en: "Reply pending", vi: "Đã trả lời, đến lượt bạn" } },
  { id: "grounded", brief: "Grounded", normative: "none: product state (grounded answer)", label: { en: "Grounded, not verified", vi: "Có dẫn chứng, chưa xác minh" } },
  { id: "clarification", brief: "Clarification (\"Your answer is needed\")", normative: "Needs input", label: { en: "Clarification", vi: "Cần làm rõ" } },
  { id: "running", brief: "Running", normative: "Working", label: { en: "Running", vi: "Đang chạy" } },
  { id: "approval", brief: "Waiting approval", normative: "Awaiting decision", label: { en: "Waiting approval", vi: "Chờ phê duyệt" } },
  { id: "refused", brief: "Waiting approval, with a refused message", normative: "Awaiting decision", label: { en: "Waiting approval · message refused", vi: "Chờ phê duyệt · tin nhắn bị từ chối" } },
  { id: "verified", brief: "Verified", normative: "Verified complete", label: { en: "Verified", vi: "Đã xác minh" } },
  { id: "failed", brief: "Failed", normative: "Failed", label: { en: "Failed", vi: "Thất bại" } },
  { id: "ended-answer", brief: "Answer to a run that ended", normative: "Failed (the message); its run is Cancelled or stopped", label: { en: "Answer to an ended run", vi: "Trả lời một lượt đã kết thúc" } },
  { id: "fallback", brief: "Per-run fallback", normative: "not a task state: a mode", label: { en: "Per-run fallback", vi: "Dự phòng từng lượt" } },
  { id: "legacy", brief: "Legacy runs", normative: "not a task state: a sidebar placement", label: { en: "Legacy runs", vi: "Tác vụ cũ" } },
  { id: "gallery", brief: "Other normative states inside a run (reachable on their run)", normative: "Blocked by rules, Decision invalidated, Rejected, Executing, Verifying, Outcome uncertain, Cancelled or stopped", label: { en: "Other run states", vi: "Trạng thái lượt khác" } },
];

const T = (en, vi) => ({ en, vi });

export const TEXT = {
  convTitle: T("Restock short products (sample)", "Bổ sung hàng đang thiếu (mẫu)"),
  u_hi: T("hi", "chào bạn"),
  a_reply: T(
    "Hello. In this sample workspace I can answer questions about stock and purchasing, and prepare purchase order drafts for you to review. What do you need?",
    "Xin chào. Trong không gian mẫu này, tôi có thể trả lời câu hỏi về tồn kho và mua hàng, và chuẩn bị bản nháp đơn mua hàng để bạn xem xét. Bạn cần gì?",
  ),
  u_short: T("which products are short?", "sản phẩm nào đang thiếu?"),
  a_grounded: T(
    "One product is below its reorder point: Bracket B-12 has 20 on hand against a reorder point of 60, so it is short by 40. The other 11 products I read are at or above their reorder points.",
    "Có một sản phẩm dưới mức đặt hàng lại: Giá đỡ B-12 còn 20, mức đặt hàng lại là 60, nên thiếu 40. 11 sản phẩm còn lại tôi đã đọc đều bằng hoặc trên mức đặt hàng lại.",
  ),
  r1_line: T("1 product short: Bracket B-12 (sample)", "1 sản phẩm thiếu: Giá đỡ B-12 (mẫu)"),
  u_po: T("draft a PO for it", "lập đơn mua hàng cho nó"),
  a_question: T(
    "How many units of Bracket B-12 should the draft order? 40 brings it to its reorder point of 60.",
    "Bản nháp nên đặt bao nhiêu đơn vị Giá đỡ B-12? Đặt 40 sẽ đưa tồn kho lên mức đặt hàng lại 60.",
  ),
  u_40: T("40", "40"),
  u_busy: T("also add 10 of hinge H-3", "thêm 10 bản lề H-3 nữa"),
  r2_waiting: T("Draft purchase order · 40 × Bracket B-12 · 100.00", "Đơn mua hàng nháp · 40 × Giá đỡ B-12 · 100,00"),
  a_verified: T(
    "I created draft purchase order PO-SAMPLE-0042 for 40 units of Bracket B-12 from Supplier North. It is a draft and has not been sent to the supplier.",
    "Tôi đã tạo đơn mua hàng nháp PO-SAMPLE-0042 cho 40 đơn vị Giá đỡ B-12 từ Nhà cung cấp Bắc. Đây là bản nháp và chưa được gửi cho nhà cung cấp.",
  ),
  r2_verified: T("Draft PO-SAMPLE-0042 read back · matches the approved values", "Đã đọc lại bản nháp PO-SAMPLE-0042 · khớp giá trị đã phê duyệt"),
  r2_failed: T("Stopped before any proposal: the purchase rules could not be read", "Dừng trước khi có đề xuất: không đọc được quy tắc mua hàng"),
  failedCause: T(
    "The purchase rules source did not answer within its time limit (sample), so no proposal was made.",
    "Nguồn quy tắc mua hàng không phản hồi trong thời hạn (mẫu), nên chưa có đề xuất nào.",
  ),
  failedNext: T(
    "Send your request again as a new message; it starts a new run in this conversation.",
    "Gửi lại yêu cầu bằng một tin nhắn mới; tin nhắn đó bắt đầu một lượt mới trong cuộc trò chuyện này.",
  ),
  r2_cancelled: T("You stopped this run from another window at 09:46 (sample). Nothing was sent.", "Bạn đã dừng lượt này từ một cửa sổ khác lúc 09:46 (mẫu). Chưa có gì được gửi."),
  // Per-run fallback: a self-contained task, as today's view has no thread.
  u_fallback: T("draft a PO for 40 units of Bracket B-12", "lập đơn mua hàng 40 đơn vị Giá đỡ B-12"),
  a_fallbackReply: T(
    "Which supplier should the draft use? Supplier North is the approved supplier for Bracket B-12 (sample).",
    "Bản nháp nên dùng nhà cung cấp nào? Nhà cung cấp Bắc là nhà cung cấp được duyệt cho Giá đỡ B-12 (mẫu).",
  ),
  u_fallbackDraft: T("Supplier North", "Nhà cung cấp Bắc"),
  // Legacy runs.
  legacyRuns: [
    { title: T("restock hinge H-3 (sample)", "bổ sung bản lề H-3 (mẫu)"), last: "status.WAITING_APPROVAL", tone: "attention", now: "status.CANCELLED", nowTone: "neutral" },
    { title: T("price check for bracket B-12 (sample)", "kiểm tra giá giá đỡ B-12 (mẫu)"), last: "status.SUCCEEDED", tone: "verified" },
  ],
  conversations: [
    { title: T("Restock short products (sample)", "Bổ sung hàng đang thiếu (mẫu)"), status: "status.SUCCEEDED", tone: "verified", current: true },
    { title: T("Supplier price question (sample)", "Câu hỏi giá nhà cung cấp (mẫu)"), status: "status.WAITING_INPUT.reply", tone: "attention", yourTurn: true },
    { title: T("Weekly stock check (sample)", "Kiểm tra tồn kho hằng tuần (mẫu)"), status: "status.SUCCEEDED.grounded", tone: "neutral" },
  ],
  legacyMsg: T("restock hinge H-3", "bổ sung bản lề H-3"),
  legacyEnd: T("You stopped this task at 08:12 (sample). Nothing was written.", "Bạn đã dừng tác vụ này lúc 08:12 (mẫu). Không có dữ liệu nào được ghi."),
};

export const EXAMPLES = [
  T("Which products are below their reorder point?", "Sản phẩm nào đang dưới mức đặt hàng lại?"),
  T("Draft a purchase order for a short product", "Lập đơn mua hàng nháp cho một sản phẩm đang thiếu"),
];

// The approval card's server presentation (unchanged card: ADR 0034 §5 deferred, G-A "3 defer").
export const APPROVAL = {
  capability: T("Create a draft purchase order (sample)", "Tạo đơn mua hàng nháp (mẫu)"),
  connection: T("Sample purchasing system · sandbox", "Hệ thống mua hàng mẫu · môi trường thử"),
  actsAs: T("Sample buyer (you)", "Người mua mẫu (bạn)"),
  expires: T("10:16 · in 30 minutes", "10:16 · sau 30 phút"),
  reversible: T("A draft can be cancelled before it is confirmed. Nothing is sent to the supplier.", "Bản nháp có thể hủy trước khi xác nhận. Không có gì được gửi cho nhà cung cấp."),
  fields: [
    { f: T("Supplier", "Nhà cung cấp"), cur: null, val: T("Supplier North (sample)", "Nhà cung cấp Bắc (mẫu)") },
    { f: T("Product", "Sản phẩm"), cur: null, val: T("Bracket B-12 (sample)", "Giá đỡ B-12 (mẫu)") },
    { f: T("Quantity", "Số lượng"), cur: null, val: T("40", "40") },
    { f: T("Unit price", "Đơn giá"), cur: null, val: T("2.50", "2,50") },
    { f: T("Order total", "Tổng đơn"), cur: null, val: T("100.00", "100,00") },
    { f: T("Order state", "Trạng thái đơn"), cur: null, val: T("Draft · not sent to the supplier", "Nháp · chưa gửi cho nhà cung cấp") },
  ],
  findings: [
    T("Supplier North is an approved supplier (sample rule)", "Nhà cung cấp Bắc là nhà cung cấp được duyệt (quy tắc mẫu)"),
    T("Quantity 40 is within the 500-unit limit", "Số lượng 40 nằm trong hạn mức 500 đơn vị"),
    T("Order total 100.00 is below the 5,000.00 limit", "Tổng đơn 100,00 dưới hạn mức 5.000,00"),
  ],
};

export const CITATIONS = [
  { record: T("Stock level · Bracket B-12 (sample) · revision 7", "Mức tồn kho · Giá đỡ B-12 (mẫu) · phiên bản 7"), field: "/on_hand" },
  { record: T("Reorder rule · Bracket B-12 (sample) · revision 3", "Quy tắc đặt hàng lại · Giá đỡ B-12 (mẫu) · phiên bản 3"), field: "/reorder_point" },
  { unresolved: true },
];

export const SOURCES = {
  1: [
    { name: T("Stock levels · 12 products (sample)", "Mức tồn kho · 12 sản phẩm (mẫu)"), at: "09:41", complete: true },
    { name: T("Reorder rules · 12 products (sample)", "Quy tắc đặt hàng lại · 12 sản phẩm (mẫu)"), at: "09:41", complete: true },
  ],
  2: [
    { name: T("Stock level · Bracket B-12 (sample)", "Mức tồn kho · Giá đỡ B-12 (mẫu)"), at: "09:44", complete: true },
    { name: T("Supplier price list · Supplier North (sample)", "Bảng giá · Nhà cung cấp Bắc (mẫu)"), at: "09:45", complete: true },
    { name: T("Purchase rules (sample)", "Quy tắc mua hàng (mẫu)"), at: "09:45", complete: true },
  ],
};

// Activity: recorded events only (EA-5). Each list ends at the state's last event.
export const EVENTS = {
  1: [
    ["09:40", T("Task received", "Đã nhận yêu cầu")],
    ["09:40", T("Replied · waiting for your answer", "Đã trả lời · chờ câu trả lời của bạn")],
    ["09:41", T("Answer received", "Đã nhận câu trả lời")],
    ["09:41", T("Read stock levels · 12 products · complete", "Đã đọc mức tồn kho · 12 sản phẩm · đầy đủ")],
    ["09:41", T("Read reorder rules · complete", "Đã đọc quy tắc đặt hàng lại · đầy đủ")],
    ["09:41", T("Answer recorded with 2 citations", "Đã ghi câu trả lời kèm 2 trích dẫn")],
    ["09:41", T("Completed · grounded, not verified", "Hoàn tất · có dẫn chứng, chưa xác minh")],
  ],
  2: [
    ["09:44", T("Task received", "Đã nhận yêu cầu")],
    ["09:44", T("Earlier runs carried as hints: run 1", "Đã mang theo lượt trước làm gợi ý: lượt 1")],
    ["09:44", T("Read stock level · Bracket B-12 · complete", "Đã đọc mức tồn kho · Giá đỡ B-12 · đầy đủ")],
    ["09:44", T("Asked a question", "Đã đặt câu hỏi")],
    ["09:45", T("Answer received", "Đã nhận câu trả lời")],
    ["09:45", T("Read supplier price list · complete", "Đã đọc bảng giá nhà cung cấp · đầy đủ")],
    ["09:45", T("Checked 3 purchase rules · all passed", "Đã kiểm tra 3 quy tắc mua hàng · đều đạt")],
    ["09:45", T("Proposal ready · waiting for your review", "Đề xuất sẵn sàng · chờ bạn xem xét")],
    ["09:47", T("Approval recorded", "Đã ghi nhận phê duyệt")],
    ["09:47", T("Sending the change", "Đang gửi thay đổi")],
    ["09:47", T("Change recorded · checking", "Đã ghi nhận · đang kiểm tra")],
    ["09:48", T("Read back the draft order · matches", "Đã đọc lại đơn nháp · khớp")],
    ["09:48", T("Completed · verified", "Hoàn tất · đã xác minh")],
  ],
};

export const VERIFIED_VALUES = [
  [T("Quantity", "Số lượng"), T("40", "40")],
  [T("Supplier", "Nhà cung cấp"), T("Supplier North (sample)", "Nhà cung cấp Bắc (mẫu)")],
  [T("Order state", "Trạng thái đơn"), T("Draft", "Nháp")],
];

export const GALLERY = [
  { key: "status.BLOCKED", tone: "attention", body: "gallery.blockedRule", stop: "on", normative: "Blocked by rules" },
  { key: "status.INVALIDATED", tone: "attention", body: null, action: "gallery.reviewAgain", stop: "on", normative: "Decision invalidated" },
  { key: "status.REJECTED", tone: "neutral", body: null, stop: "off", normative: "Rejected" },
  { key: "status.DISPATCHING", tone: "progress", body: "gallery.dispatching", stop: "on", normative: "Executing" },
  { key: "status.VERIFYING", tone: "progress", body: "gallery.verifying", stop: "on", normative: "Verifying" },
  { key: "status.NEEDS_RECONCILIATION", tone: "unknown", body: "gallery.unknown", action: "gallery.checkStatus", stop: "reconcile", normative: "Outcome uncertain" },
  { key: "status.CANCELLED", tone: "neutral", body: "gallery.cancelled", stop: "off", normative: "Cancelled or stopped" },
];
