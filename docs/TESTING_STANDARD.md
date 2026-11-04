# TESTING STANDARD — Quy trình Test 3 Tầng + Vận hành dài hạn

> Tài liệu chuẩn dùng chung cho mọi dự án. Áp dụng từ R012-NQMProactiveCC,
> có thể tái sử dụng cho dự án khác không cần sửa đổi.

## Tổng quan — 3 Tầng cốt lõi (Testing Pyramid)

Nguyên tắc gốc: **test rẻ/nhanh chạy nhiều ở dưới, test đắt/chậm chạy ít ở trên**. Không nhảy tầng khi tầng dưới chưa đạt. Không lặp lại phạm vi tầng dưới ở tầng trên.

---

## Tầng 1 — Test cấu trúc

**Khi nào chạy:** trong lúc code từng module, và **tự động lại mỗi khi có thay đổi** (không phải chỉ 1 lần).

| Loại | Phạm vi | Công cụ |
|---|---|---|
| Unit test domain logic | Mock toàn bộ dependency, so sánh kết quả với công thức/quy tắc nghiệp vụ trong tài liệu | pytest |
| Integration test adapter | DB/API thật, nhưng test TỪNG adapter RIÊNG LẺ, không ghép chuỗi | pytest + DB/API thật |
| Contract test (BE↔FE) | Xem mục "Hợp đồng giao tiếp" bên dưới | OpenAPI schema |

**Mục đích:** xác nhận từng thành phần đúng yêu cầu, đúng cấu trúc — CHƯA xác nhận hệ thống chạy được.

---

## Tầng 2 — Test full Backend

**Khi nào chạy:** sau khi ghép nối xong toàn bộ BE, TRƯỚC khi làm FE. Lặp lại mỗi khi merge vào staging.

- Gọi thật qua API (Postman/curl/Newman) — toàn bộ chuỗi Router → UseCase → DB/External API thật.
- Dùng dữ liệu THẬT, có Setup/Teardown (xem mục "Quản lý dữ liệu test" bên dưới).
- **Mục đích:** lần đầu xác nhận CẢ CHUỖI Backend hoạt động đúng — bắt lỗi tích hợp SỚM, khi còn dễ sửa.

---

## Tầng 3 — Test full Backend + Frontend

**Khi nào chạy:** sau khi FE xong, trước bàn giao/demo. Chạy đúng kịch bản người dùng cuối.

**Mục đích:** xác nhận trải nghiệm hoàn chỉnh — KHÔNG còn phát hiện lỗi cấu trúc/tích hợp cơ bản ở bước này (đã bắt hết ở Tầng 1-2).

---

## 4 lỗ hổng vận hành dài hạn — bắt buộc cho dự án chạy nhiều năm, nhiều team

### 1. Tính liên tục & Tự động hoá (Regression + CI/CD)

**Vấn đề:** 3 tầng dễ hiểu nhầm là tuyến tính "làm 1 lần rồi xong". Thực tế: sửa code sau này ở Tầng 3 có thể làm gãy Tầng 1.

**Giải pháp:**
- **Automated Gates:** Tích hợp bộ kiểm thử vào Pipeline CI/CD. Chặn mọi PR (Pull Request) lên nhánh chung nếu **Tầng 1** không pass 100%. Tự động kích hoạt bộ script **Tầng 2** sau khi mã nguồn được deploy lên môi trường Staging.
- **Bảo vệ mã nguồn:** Coi các bộ test suite cũ là tài sản cốt lõi chống lỗi hồi quy (`Regression`). Tuyệt đối không cho phép merge thủ công hoặc bypass khi hệ thống kiểm thử tự động báo đỏ (`Failed`).

### 2. Hợp đồng giao tiếp BE-FE (Contract Testing)

**Vấn đề:** Team BE/FE làm độc lập. BE đổi field (`cell_id` → `cellId`) mà không báo, FE lệch pha, phát hiện muộn ở Tầng 3.

**Giải pháp:**
- **Nguồn chân lý (source of truth):** BE tự generate OpenAPI schema từ code (FastAPI → `/openapi.json` miễn phí, không cần viết tay).
- FE consume schema đó để generate type — không tự viết tay 2 bản schema riêng.
- Đặt kiểm tra này ở **biên giữa Tầng 1 và Tầng 2** — CI chặn ngay nếu FE dùng sai schema, không đợi tới Tầng 3.

### 3. Quản lý trạng thái dữ liệu sạch (Test Data Isolation)

**Vấn đề:** Chạy đi chạy lại Tầng 2 trên DB thật sinh dữ liệu rác, trùng khóa chính, không Idempotent (chạy 100 lần phải ra kết quả nhất quán).

**Giải pháp — 2 chiến lược tuỳ ngữ cảnh:**

| Chiến lược | Áp dụng khi | Cách làm |
|---|---|---|
| Transaction rollback | Test nội bộ DB (Tầng 1/2, không gọi External API) | Mỗi test chạy trong 1 transaction, rollback cuối test — nhanh, sạch tuyệt đối |
| Cleanup có đánh dấu | Test có gọi External API thật (CĐS/NetAct...) không nằm trong transaction DB | Prefix rõ ràng (`TEST_*`), cleanup tường minh cuối mỗi lần test, verify lại DB sạch sau cleanup |

### 4. Kiểm soát rủi ro tác động hạ tầng (Staged Rollout / Canary)

**Vấn đề:** Hệ thống tác động trực tiếp hạ tầng thật (viễn thông, mạng lưới, thiết bị vật lý) — pass Tầng 3 trên staging/giả lập vẫn chưa đủ an toàn để đẩy thẳng production diện rộng.

**Giải pháp — bước phụ lục sau Tầng 3:**
- **Triển khai phân tầng (Canary Deployment):** Cấu hình luồng tự động hóa chạy thử nghiệm trên một nhóm nhỏ đối tượng hạ tầng cô lập (ví dụ: 1-5 phần tử mạng/trạm phát vùng phụ tải thấp) trong vòng 24-48 giờ để theo dõi hành vi thực tế.

- **Giám sát chỉ số sinh mạng mạng lưới:** Liên tục chạy các vòng lặp quét KPIs mạng (tỷ lệ drop, cảnh báo alarm hệ thống). Nếu phát hiện tỷ lệ lỗi tăng vượt ngưỡng an toàn quy định (> 1%), cơ chế tự động ngắt (`Circuit Breaker`) được kích hoạt để ngay lập tức hủy lệnh và **Rollback trạng thái** về phiên bản an toàn gần nhất, bảo vệ mạng lưới core diện rộng.



