# WORKFLOW.md — 18 Bước E2E UC01

> Mô tả chi tiết toàn bộ flow từ khi user trigger đến khi CR hoàn thành.
> Mỗi bước map rõ: Layer nào xử lý, Port/Adapter nào được gọi, SSE event nào được emit.
> Xem docs/BUSINESS_RULES.md cho logic tính toán chi tiết.
> Xem docs/ARCHITECTURE.md cho layer diagram.

---

## 1. TỔNG QUAN FLOW

```
User (FE Tab1 Zone A)
  │ POST /cr/trigger {tram_id, action}
  ▼
API Layer (cr.py router)
  │ validate HTTP request
  │ call TriggerCrUseCase.execute()
  ▼
Application Layer (TriggerCrUseCase)
  │ orchestrate 18 bước
  │ emit SSE event sau mỗi bước
  ▼
Domain Services → Adapters → External Systems
  │
  ├── CĐS API (cell neighbors)
  ├── PostgreSQL (read/write)
  ├── NetAct SSH (Import + Provision)
  └── CTS API (QoS baseline snapshot)
  │
  ▼
SSE Stream → FE Zone C (real-time progress)
```

---

## 2. 18 BƯỚC CHI TIẾT

### Step 1 — Validate Input
```
Layer:    Application (TriggerCrUseCase)
Xử lý:
  - Kiểm tra tram_id hoặc tram_name có ít nhất 1
  - Kiểm tra action hợp lệ: shutdown|cancel|relocate
  - Nếu action = cancel → chuyển sang rollback flow (xem Section 3)
  - Kiểm tra trạm đang có cr_session RUNNING → 409
  - Kiểm tra trạm đã có cr_session DONE → 409 (CR chỉ chạy 1 lần)
Port:     ICrSessionRepo.get_by_tram_id()
SSE:      {"step":1, "pct":5, "status":"running", "msg":"Đang validate input..."}
          {"step":1, "pct":5, "status":"success", "msg":"Input hợp lệ"}
Error:    TramNotFoundError → SSE failed + close stream
```

### Step 2 — Query Tram Info từ DB
```
Layer:    Application → Adapter
Xử lý:
  - Nếu chỉ có tram_name → lookup tram_id từ DB
  - Lấy thông tin tram: tọa độ, tên, trang_thai
  - Tạo cr_session mới: status=RUNNING
  - Lưu cr_session vào DB
Port:     IEnodebRepo.find(), ICrSessionRepo.create()
SSE:      {"step":2, "pct":10, "status":"success",
           "msg":"Tìm thấy trạm {tram_name}, tạo session #{session_id}"}
```

### Step 3 — Gọi CĐS API /cell/neighbors
```
Layer:    Adapter (CdsHttpAdapter)
Xử lý:
  - Build SHA-512 headers
  - POST /cell/neighbors với tramId + action + technology=4G
  - Retry 3 lần nếu timeout (backoff 1s, 2s, 4s)
  - Parse JSON response
Port:     INetworkGateway.get_cell_neighbors()
SSE:      {"step":3, "pct":18, "status":"running", "msg":"Đang gọi CĐS API..."}
          {"step":3, "pct":18, "status":"success",
           "msg":"Nhận được {total} cells từ {n} hướng"}
Error:    CdsApiError sau 3 lần retry → SSE failed, cr_session=FAILED
Log:      INFO session_id tram_id total_cells
```

### Step 4-5 — Lọc cell lân cận (NeighborCellFilter)
```
SỬA TOÀN BỘ (13/07/2026, xác nhận với user — viết lại từ đầu, KHÔNG giữ logic
cũ): 4 domain service cũ (NeighborCellService bước 4; BandPriorityFilter →
NbLncelFilter → HuongCellSelector bước 5) đã bị XÓA, thay bằng 1
domain/services/neighbor_cell_filter.py — NeighborCellFilter DUY NHẤT, chạy
liên tục 4 bước nội bộ KHÔNG tách rời được (band priority PHẢI chạy trên raw
list gốc trước khi dedup — xem "Lý do gộp" bên dưới). Vẫn phát 2 SSE step
(4 và 5, cùng nội dung đếm cell) để KHÔNG đổi pct/step-numbering của bước
6-18, dù bên trong chỉ còn 1 lệnh gọi.

Layer:    Domain Service (NeighborCellFilter.filter())
Xử lý (đúng thứ tự, 4 bước nội bộ + 1 bước bổ sung 02/10/2026 — 3b):
  1. Lọc field kỹ thuật cơ bản: technology=="4G" VÀ status=="active"
  2. Gom theo SECTOR + lọc band CỦA CHÍNH CELL — SỬA 03/10/2026 (thay thế
     hoàn toàn "band priority theo sector" cũ, xem BUSINESS_RULES.md Section
     3): huong_id's chữ số cuối (Y) = sector trạm tắt, dùng để GOM NHÓM —
     KHÔNG còn chọn 1 huong "thắng" đại diện cho sector. MỌI huong của sector
     đóng góp ứng viên; cell trùng tên (xuất hiện ở ≥2 huong cùng sector) giữ
     bản priority NHỎ NHẤT, tie-break bằng BAND_PRIORITY (1>3>5>4) của huong
     nguồn. Band lọc là của CHÍNH CELL LÁNG GIỀNG (LNCEL trong DN của nó,
     `^[13][0-9]$`), KHÔNG phải band của huong/trạm tắt — cell không khớp bị
     loại, lý do BAND_KHONG_CHAY_CR. Trước 03/10/2026: lọc theo band CỦA
     HUONG (X=huong_id//10), phát hiện SAI qua khảo sát dữ liệu thật trạm
     160008 (1 cell láng giềng có thể ở nhiều huong band khác nhau).
  3. Trong các huong còn lại sau bước 2: loại cell cell_name bắt đầu "NB-"
     HOẶC "MBF_" HOẶC LNCEL local id (phần sau "LNCEL-" trong cell_id) bắt
     đầu bằng "2"
  3b. Loại SMALL CELL (S/P, thêm 02/10/2026 — xem BUSINESS_RULES.md Section
     4b): loại trạm suy từ 1 ký tự ngay sau số site trong cell_name
     (vd "4G-TPO065S11-TQG" → "S"). PHẢI làm TRƯỚC bước 4 (chọn tối đa 2
     cell/hướng) — loại sau sẽ làm small cell chiếm mất 1 suất, hụt mất cơ
     hội cho cell macro xếp hạng kế tiếp. Cell bị loại ghi lý do SMALL_CELL.
     filter_affected() (Nhánh A, đánh giá QoS/QoE + xuất phiếu) CŨNG áp dụng
     bước này (KHÔNG chỉ CR, khác band ở bước 2) — xem BUSINESS_RULES.md
     Section 4b.3 bảng phạm vi.
  4. Chọn tối đa 2 cell/SECTOR (09/2026 chốt số 2, 03/10/2026 đổi đơn vị từ
     huong sang sector): sort sector (Y) tăng dần, xử lý lần lượt; trong mỗi
     sector sort ứng viên theo (priority, BAND_PRIORITY của huong nguồn) tăng
     dần; loại cell ĐÃ ĐƯỢC CHỌN ở sector xử lý trước đó (không phải toàn bộ
     candidate thô của sector trước); lấy tối đa 2 cell đầu còn lại. Cell bị
     loại vì trùng KHÔNG tiêu một suất của sector sau — sector đó lấy cell kế
     tiếp để vẫn đủ 2. Priority GIỮ NGUYÊN giá trị gốc từ CĐS (không
     renumber, có thể có khoảng trống như 1,2,5,6).
     Sector có ít hơn 2 cell thì lấy hết, KHÔNG lỗi (1 cell → chỉ rsboost).

Lý do gộp (bug thật phát hiện lúc verify, không phải giả định): thứ tự bước
CŨ sai — NeighborCellService.filter() dedup cell trùng tên XUYÊN HUONG
(rsboost-wins) TRƯỚC khi BandPriorityFilter chọn band theo sector Y, làm sai
lệch tập cell có mặt trong mỗi huong lúc so sánh band. Verify bằng dữ liệu
CĐS thật (368 cell, tram_id=110548, đối chiếu tay với log CR thật session
193): thứ tự MỚI (band priority trước, dedup sau) khớp CHÍNH XÁC 100%, thứ
tự CŨ cho kết quả sai lệch (xem tests/domain/test_neighbor_cell_filter.py).

GAP CHƯA XÁC NHẬN với BUSINESS_RULES.md SS2.2-2.4 (KHÔNG có trong 4 bước
trên, viết đúng theo yêu cầu user 13/07/2026 "không thêm điều kiện chưa xác
nhận"): cell_id=null bỏ qua, cell_name prefix "VNP-" bỏ qua, duplicate
huong_id giữ huong đầu, duplicate cell xuyên huong rsboost luôn thắng
qrxlevmin ("rule tuyệt đối" cũ, SS2.4) — CẢ 4 rule này KHÔNG còn được
implement. Trên dữ liệu thật 368 cell: 3 rule đầu "ngủ" (không phát sinh),
rule cuối (2.4) có khả năng phát sinh (52 cell lặp xuyên huong trong raw
data) nhưng không làm sai kết quả verify vì đã được band-priority (bước 2)
giải quyết tự nhiên trước khi tới bước dedup. BUSINESS_RULES.md SS2.2-2.4 đã
được cập nhật theo đúng thuật toán này (chốt 09/2026).

Port:     Không cần (pure domain logic)
SSE:      {"step":4, "pct":25, "status":"success",
           "msg":"Sau filter: {n} cells hợp lệ"}
          {"step":5, "pct":30, "status":"success",
           "msg":"Band priority + loại NB-/MBF_/LNCEL-2xx + chọn tối đa 2 cell/hướng: còn {n} cells hợp lệ"}
```

### Step 6 — Assign Priority: rsboost / qrxlevmin
```
Layer:    Domain Service (PriorityAssigner)
Xử lý:
  - Rank 1 trong hướng → action_type = "rsboost"     (09/2026)
  - Rank 2 trong hướng → action_type = "qrxlevmin"   (09/2026)
    (rank = thứ hạng theo priority tăng dần TRONG hướng, KHÔNG phải priority
     gốc từ CĐS — priority gốc có khoảng trống sau khi lọc)
  - Duplicate cell cross-direction → hướng có huong_id nhỏ hơn giữ quyền
    (đã xử lý ở step 4, KHÔNG phải "rsboost wins")
  - Cell ở cap/floor → action_type = "skip"
Port:     Không cần
SSE:      {"step":6, "pct":35, "status":"success",
           "msg":"Assign: {r} cells rsboost, {q} cells qrxlevmin"}
```

### Step 7 — Lấy rsboost_current từ DB
```
Layer:    Adapter (CellInforRepo)
Xử lý:
  - Query cell_infor theo dist_name (LIKE trên dn_fdd)
  - Lấy rsboost_current (dữ liệu thô từ Admin CLI export)
  - Snapshot: copy rsboost_current → rsboost_before_cr (đóng băng lịch sử,
    vẫn ghi qua cell_params/ICellParamsRepo.snapshot_before_cr(), KHÔNG đổi)
  - SỬA (13/07/2026, quyết định 12/07/2026 — thay cho dòng "dùng giá trị mặc định
    (0dB)" cũ): nếu cell chưa có trong cell_infor (chưa từng sync qua Admin
    CLI export) → log WARNING, LOẠI cell khỏi CR (không dùng giá trị mặc
    định) — tránh áp giá trị đoán lên mạng thật khi chưa xác nhận cell đó
    thực sự đang ở trạng thái nào.
Port:     ICellInforRepo.get_rsboost_by_neighbor_dns()
          ICellParamsRepo.snapshot_before_cr()
SSE:      {"step":7, "pct":42, "status":"success",
           "msg":"Lấy được rsboost_current cho {n} cells"}
```

### Step 8 — Tính rsboost_new (+3dB theo scale [-3,0,3,6])
```
Layer:    Domain Service (RsboostCalculator)
Xử lý:
  - Với mỗi cell action_type=rsboost:
    RsboostLevel.from_raw(rsboost_current).next_level()
    → next_level(): value + 3.0, cap tại 6.0
  - Cell đang ở cap (6.0dB) → action_type="skip", log INFO
  - Ghi rsboost_new vào cell object
Port:     Không cần (pure domain logic)
SSE:      {"step":8, "pct":48, "status":"success",
           "msg":"Tính rsboost: {n} cells thay đổi, {s} cells ở cap (skip)"}
```

### Step 9 — Lấy qrxlevmin_current từ DB
```
Layer:    Adapter (CellInforRepo)
Xử lý:
  - Query cell_infor theo dist_name (LIKE trên dn_sib) cho cells
    action_type=qrxlevmin
  - Snapshot: copy qrxlevmin_current → qrxlevmin_before_cr (vẫn ghi qua
    cell_params/ICellParamsRepo.snapshot_before_cr() ở Step 7, KHÔNG đổi)
  - SỬA (13/07/2026, quyết định 12/07/2026 — thay cho dòng "dùng mặc định (-128)"
    cũ): nếu cell chưa có trong cell_infor → log WARNING, LOẠI cell khỏi CR
    (không dùng giá trị mặc định) — cùng lý do Step 7 (tránh áp giá trị đoán
    lên mạng thật).
Port:     ICellInforRepo.get_qrxlevmin_by_neighbor_dns()
SSE:      {"step":9, "pct":52, "status":"success",
           "msg":"Lấy được qrxlevmin_current cho {n} cells"}
```

### Step 10 — Tính qrxlevmin_new (-4dBm, floor -144)
```
Layer:    Domain Service (QrxlevminCalculator)
Xử lý:
  - Với mỗi cell action_type=qrxlevmin:
    Qrxlevmin(qrxlevmin_current).decrease()
    → decrease(): value - 4, floor tại -144
  - Cell đang ở floor (-144) → action_type="skip", log INFO
Port:     Không cần
SSE:      {"step":10, "pct":56, "status":"success",
           "msg":"Tính qrxlevmin: {n} cells thay đổi, {s} cells ở floor (skip)"}
```

### Step 11 — Lưu cell_params vào DB
```
Layer:    Adapter (CellParamsRepo)
Xử lý:
  - Upsert tất cả cell_params:
    rsboost_before_cr, rsboost_new
    qrxlevmin_before_cr, qrxlevmin_new
    action_type, cr_session_id
  - Ghi audit_log: action=CR_CALCULATE
Port:     ICellParamsRepo.upsert()
SSE:      {"step":11, "pct":60, "status":"success",
           "msg":"Đã lưu {n} cell params vào DB"}
```

### Step 12 — Build XML RAML 2.0
```
Layer:    Adapter (XmlBuilder)
Xử lý:
  - Build 1 file XML duy nhất:
    rsboost blocks (LNCEL_FDD): giá trị f"{val:g}dB"
    qrxlevmin blocks (SIB): giá trị integer
  - KHÔNG có attribute id, version
  - distName rsboost:   cell_id + "/LNCEL_FDD-0"
  - distName qrxlevmin: cell_id + "/SIB-0"
  - Validate XML trước khi upload
  - Lưu file XML tạm trên local
Port:     INetActGateway (XmlBuilder là internal của NetActAdapter)
SSE:      {"step":12, "pct":65, "status":"success",
           "msg":"Build XML: {n} managedObject blocks"}
Error:    XmlBuildError → SSE failed, cr_session=FAILED
```

### Step 13 — Upload XML lên NetAct (SFTP)
```
Layer:    Adapter (SshExecutor)
Xử lý:
  - Paramiko SSH connect (timeout 30s)
  - SFTP put: local → /d/oss/.../R012-NQMProactiveCC/{filename}
  - Retry SFTP upload 3 lần nếu fail (chưa tác động mạng)
  - Ghi audit_log: action=CR_SSH_UPLOAD
Port:     INetActGateway.submit_cr() → nội bộ SshExecutor
SSE:      {"step":13, "pct":70, "status":"running",
           "msg":"Đang upload XML lên NetAct..."}
          {"step":13, "pct":70, "status":"success",
           "msg":"Upload thành công: {filename}"}
Error:    SshConnectionError → SSE failed, cr_session=FAILED
```

### Step 14 — SSH: racclimx.sh Import
```
Layer:    Adapter (SshExecutor)
Xử lý:
  - exec_command: racclimx.sh -op Import -type plan -planName ... -UIValues true -v
  - Timeout: 120s
  - Parse stdout/stderr: exit_code=0 + không có ERROR keyword → success
  - Log toàn bộ stdout + stderr vào cr_log.detail (JSONB)
  - Ghi audit_log: action=CR_SSH_IMPORT
  - KHÔNG retry (đã gửi lệnh là không undo)
Port:     INetActGateway
SSE:      {"step":14, "pct":78, "status":"running",
           "msg":"SSH: racclimx.sh Import..."}
          {"step":14, "pct":78, "status":"success",
           "msg":"Import plan thành công: {plan_name}"}
Error:    exit_code!=0 hoặc ERROR trong stdout → SSE failed
```

### Step 15 — SSH: racclimx.sh Provision
```
Layer:    Adapter (SshExecutor)
Xử lý:
  - exec_command: racclimx.sh -op Provision -planName ... -createBackupPlan true ...
  - Timeout: 120s
  - Parse stdout/stderr
  - Lưu backup_plan_name vào cr_session
  - Ghi audit_log: action=CR_SSH_PROVISION
  - KHÔNG retry (tác động live network)
Port:     INetActGateway
SSE:      {"step":15, "pct":85, "status":"running",
           "msg":"SSH: racclimx.sh Provision..."}
          {"step":15, "pct":85, "status":"success",
           "msg":"Provision thành công, backup: {backup_name}"}
Error:    exit_code!=0 → SSE failed, cr_session=FAILED
```

### Step 16 — Parse Kết Quả SSH + Verify
```
Layer:    Adapter (SshExecutor / NetActAdapter)
Xử lý:
  - Tổng hợp kết quả Step 14 + 15
  - Verify: cả 2 bước đều success
  - Lưu stdout/stderr đầy đủ vào cr_log
  - Cập nhật cr_session: plan_name, backup_plan_name, executed_at=NOW()
Port:     ICrSessionRepo.update()
SSE:      {"step":16, "pct":90, "status":"success",
           "msg":"CR đã được áp dụng lên NetAct thành công"}
```

### Step 17 — Cập nhật cr_session Status
```
Layer:    Application (TriggerCrUseCase)
Xử lý:
  - cr_session.status = DONE
  - cr_session.executed_at = NOW() (UTC)
  - Ghi audit_log: action=CR_TRIGGER, status=SUCCESS
Port:     ICrSessionRepo.update()
SSE:      {"step":17, "pct":95, "status":"success",
           "msg":"CR session #{session_id} đã hoàn thành"}
```

### Step 18 — Snapshot QoS Baseline (CTS)
```
Layer:    Adapter (CtsHttpAdapter)
Xử lý:
  - Lấy QoS 7 ngày trước CR (T-7 → T-1, to=yesterday 23:59:59)
  - Lưu vào qos_snapshot (period="before", source="cts")
  - SOC QoE baseline: bỏ qua nếu mock (ghi NOTE, lấy sau khi có auth)
  - Nếu CTS call fail → log WARNING nhưng KHÔNG fail CR
    (baseline có thể lấy lại sau)
Port:     INetworkGateway.get_qos_metrics()
SSE:      {"step":18, "pct":100, "status":"success",
           "msg":"CR hoàn thành. Đánh giá sau 21 ngày.", "done":true}
Log:      INFO số ngày QoS snapshot đã lưu
```

---

## 3. ROLLBACK FLOW (action=cancel)

```
Trigger: POST /cr/trigger {action: "cancel", tram_id: "160000"}

Step 1: Validate → tìm cr_session có status=DONE cho trạm này
        Nếu không có → từ chối, trả 400 CR_ROLLBACK_NO_SOURCE

Step 2: Lấy rsboost_before_cr + qrxlevmin_before_cr từ cell_params
        Nếu null → từ chối, trả 400 CR_ROLLBACK_NO_SOURCE

Step 3: Build XML với giá trị gốc (before_cr)
        QUAN TRỌNG — AN TOÀN LIVE NETWORK:
        Domain layer KHÔNG tự tính toán ngược (không trừ 3dB, không cộng 4dBm)
        Bắt buộc nạp nguyên trạng rsboost_before_cr + qrxlevmin_before_cr từ Step 2
        Build XML y hệt Step 12 nhưng value = before_cr thay vì new
        Lý do: tính ngược không an toàn nếu có thay đổi thủ công giữa chừng

Step 4: Upload + Import + Provision (giống Step 13-15)

Step 5: Tạo cr_session mới:
        is_rollback = True
        rollback_of_id = original_session_id
        status = DONE

Step 6: Cập nhật cell_params:
        rsboost_current = rsboost_before_cr
        qrxlevmin_current = qrxlevmin_before_cr
        rsboost_new = null, qrxlevmin_new = null

Step 7: Ghi audit_log: action=CR_ROLLBACK
```

---

## 4. EVALUATE FLOW (n8n trigger hàng ngày)

```
Trigger: POST /jobs/evaluate-cr (n8n, hàng ngày)
         → BE return 202 ngay, chạy background task

Background Task (EvaluateCrUseCase):

  1. Query: cr_session WHERE status IN (DONE, EVAL_PENDING)
            AND executed_at <= NOW() - 21 days

  2. Với mỗi session:
     a. Gọi SOC: get_qoe()
          period=before: T-7 → T-1 (7 ngày trước ngày chạy CR)
          period=after:  T+1 → T+7 (7 ngày sau ngày chạy CR)
     b. Gọi CTS: get_qos_metrics()
          period=before: T-7 → T-1 (7 ngày trước ngày chạy CR)
          period=after:  T+1 → T+7 (7 ngày sau ngày chạy CR)
          to = T-1 lúc 23:59:59Z (KHÔNG phải 00:00:00)
     c. Lưu snapshots vào qoe_snapshot, qos_snapshot

     d. Đánh giá:
        days_before = count rows WHERE period=before  (max 7)
        days_after  = count rows WHERE period=after   (max 7)
        IF days_before < 5 OR days_after < 5:
          → status = EVAL_PENDING
          → qoe_result = INSUFFICIENT_DATA
        ELSE:
          -- Chia cho số ngày THỰC TẾ có data, KHÔNG chia cho 7 cố định
          qoe_before = sum(qoe_score WHERE period=before) / days_before
          qoe_after  = sum(qoe_score WHERE period=after)  / days_after
          qoe_result = PASS if qoe_after >= qoe_before else FAIL
          -- Tương tự cho qos (nguồn CTS)
          qos_before = sum(qos_score WHERE period=before) / days_before
          qos_after  = sum(qos_score WHERE period=after)  / days_after
          qos_result = PASS if qos_after >= qos_before else FAIL

     NOTE — Chart FE (Zone E) hiển thị 10 điểm:
        T-2, T-1, T+0(CR day), T+1 → T+7
        → Khác với evaluate (dùng T-7→T-1 để tính avg)
        → FE lấy từ snapshot table, filter theo date range

     e. Nếu FAIL → tạo alert_log (QOE_DEGRADED / QOS_DEGRADED)

     f. Cập nhật cr_session:
        qoe_result, qos_result, qoe_before, qoe_after,
        qos_before, qos_after, evaluated_at=NOW(), status=EVALUATED

     g. Ghi audit_log: action=CR_EVALUATE

  3. Check EVAL_PENDING > 30 ngày → alert_log EVAL_PENDING_TOO_LONG
```

---

## 5. SYNC FLOWS (n8n trigger hàng ngày)

### sync-rims (POST /jobs/sync-rims)
```
Chạy từ: server 10.155.43.196 (bắt buộc — IP whitelist eNodeB API)
Background task:
  1. Fetch all pages từ eNodeB API (pageSize=1000, ~5822 trang)
  2. Sanitize: longitude=0 → None, control chars → strip
  3. Upsert vào bảng tram (on conflict tram_id → update)
  4. Log: tổng records, thời gian sync
  5. audit_log: SYNC_ENODEB
```

### sync-netact (POST /jobs/sync-netact)
```
Background task:
  1. SSH vào NetAct → export cell params (method TBD)
  2. Parse: "3dB" → 3.0 (rsboost), "-128" → -128 (qrxlevmin)
  3. Upsert vào cell_params (*_current fields)
     → KHÔNG ghi đè *_before_cr và *_new nếu cr_session_id đã có
  4. audit_log: SYNC_CELL_PARAMS
```

### sync-status (POST /jobs/sync-status)
```
Background task:
  1. Lấy danh sách trạm active/inactive từ nguồn (CĐS hoặc NetAct — TBD)
  2. Update tram.trang_thai
  3. audit_log: SYNC_TRAM_STATUS
```

---

## 6. SSE EVENT FORMAT — ĐẦY ĐỦ

```json
{
  "step":      3,
  "step_name": "Gọi CĐS API /cell/neighbors",
  "pct":       18,
  "status":    "running|success|failed|skipped",
  "msg":       "Mô tả ngắn gọn",
  "detail":    {},
  "done":      false,
  "error":     null
}
```

```
FE consume SSE (useSseStream.ts):
  const es = new EventSource(`/api/v1/cr/stream/${sessionId}`)
  es.onmessage = (e) => {
    const event = JSON.parse(e.data)
    updateProgress(event)
    if (event.done || event.status === 'failed') es.close()
  }
  es.onerror = () => es.close()
```

---

## 7. PROGRESS % MAPPING

```
Step  1  Validate input             →  5%
Step  2  Query tram + tạo session   → 10%
Step  3  Gọi CĐS API               → 18%
Step  4  Filter cells               → 25%
Step  5  Band priority filter       → 30%
Step  6  Assign priority            → 35%
Step  7  Lấy rsboost_current        → 42%
Step  8  Tính rsboost_new           → 48%
Step  9  Lấy qrxlevmin_current      → 52%
Step 10  Tính qrxlevmin_new         → 56%
Step 11  Lưu cell_params            → 60%
Step 12  Build XML                  → 65%
Step 13  Upload SFTP                → 70%
Step 14  SSH Import                 → 78%
Step 15  SSH Provision              → 85%
Step 16  Parse kết quả              → 90%
Step 17  Cập nhật cr_session        → 95%
Step 18  Snapshot QoS baseline      → 100%
```

---

## 8. ERROR HANDLING TRONG FLOW

```
Nguyên tắc:
  - Lỗi ở bất kỳ step nào → emit SSE event status=failed → đóng stream
  - cr_session.status = FAILED
  - Ghi chi tiết lỗi vào cr_log.detail (JSONB)
  - Ghi audit_log với status=FAILED

Các lỗi có thể recover (retry):
  Step 3:  CĐS API timeout → retry 3 lần
  Step 13: SFTP upload fail → retry 3 lần

Lỗi KHÔNG retry (đã tác động):
  Step 14: racclimx.sh Import đã chạy
  Step 15: racclimx.sh Provision đã chạy

Step 18 fail (CTS snapshot):
  → KHÔNG fail CR session (CR đã thành công)
  → Log WARNING, snapshot sẽ lấy lại khi evaluate
```