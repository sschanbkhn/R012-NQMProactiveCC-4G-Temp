# DB_SCHEMA.md — Database Schema UC01

> 9 bảng PostgreSQL. Dùng SQLModel (async).
> Mọi timestamp lưu UTC. FE convert sang GMT+7 khi hiển thị.
> Chi tiết business rules xem docs/BUSINESS_RULES.md.
>
> **[C1.4-fix9]** Mọi cột timestamp dùng `timestamptz`, lưu UTC. KHÔNG dùng
> `server_default=now()` (DB server tz=GMT+7 sẽ làm lệch giờ). Luôn set qua
> Python `datetime.now(timezone.utc)`.

---

## TỔNG QUAN — QUAN HỆ GIỮA CÁC BẢNG

```
tram (1) ──────────────────── (N) cell_params
  │                                    │
  │                                    │
  └──── (1) ──── (N) cr_session ───────┘
                      │
          ┌───────────┼───────────────┬───────────────────┐
          │           │               │                    │
        (N)         (N)             (N)                  (N)
       cr_log   qoe_snapshot    qos_snapshot      cr_affected_cells
                      │               │
                      └───────────────┘
                            │
                         alert_log (N)

audit_log ← ghi độc lập, FK optional → cr_session
```

---

## 1. BẢNG `tram`

> Danh sách trạm 4G. Sync hàng ngày từ eNodeB List API (RIMS).

```sql
CREATE TABLE tram (
    id              SERIAL          PRIMARY KEY,
    tram_id         VARCHAR(50)     NOT NULL UNIQUE,   -- enodeb_id từ RIMS
    tram_name       VARCHAR(200)    NOT NULL,           -- ten_he_thong
    ten_quan_ly     VARCHAR(200),                       -- tên địa danh (tên quản lý)
    ma_csht         VARCHAR(100),                       -- mã cơ sở hạ tầng
    ma_tinh         VARCHAR(20),                        -- mã tỉnh/TP
    longitude       NUMERIC(10, 6),                     -- null nếu =0 từ API
    latitude        NUMERIC(10, 6),                     -- null nếu =0 từ API
    ten_thiet_bi    VARCHAR(200),                       -- loại thiết bị Nokia
    trang_thai      VARCHAR(20)     NOT NULL DEFAULT 'active',
                                                        -- active|inactive|relocating
    last_synced_at  TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tram_tram_id   ON tram(tram_id);
CREATE INDEX idx_tram_tram_name ON tram(tram_name);
CREATE INDEX idx_tram_trang_thai ON tram(trang_thai);
```

**Notes:**
```
- longitude=0 / latitude=0 từ eNodeB API → lưu NULL (không lưu 0)
- ma_tinh=None từ API → lưu NULL
- ten_quan_ly: sanitize control characters trước khi insert (openpyxl issue)
- Upsert on conflict tram_id → update (không xóa record cũ)
```

---

## 2. BẢNG `cell_params`

> Tham số RF của từng cell lân cận. Sync từ NetAct + cập nhật sau CR.

```sql
CREATE TABLE cell_params (
    id                    SERIAL          PRIMARY KEY,
    tram_id               VARCHAR(50)     NOT NULL REFERENCES tram(tram_id),
    cell_name             VARCHAR(200)    NOT NULL,     -- VD: 4G-HKM053M11-CBG
    cell_id               VARCHAR(200),                 -- nullable (cell_id=null từ CĐS)

    -- distName base (đến LNCEL-y) — lấy từ CĐS response
    dist_name_base        VARCHAR(300),                 -- PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y
    -- distName đầy đủ cho từng class
    dist_name_lncel_fdd   VARCHAR(350),                 -- .../LNCEL-y/LNCEL_FDD-0
    -- SUA (13072026, xac nhan that qua "psql \d cell_params" tren DB that):
    -- ten cot THAT la dist_name_lncel_fdd (co suffix "_fdd") - ban goc tai
    -- lieu nay ghi "dist_name_lncel" la SAI, DB da bi doi ten ngoai luong
    -- migration (cung dang bug doc/thuc te da gap nhieu lan truoc do).
    dist_name_sib         VARCHAR(350),                 -- .../LNCEL-y/SIB-0

    -- Tham số hiện tại (sync từ NetAct hàng ngày)
    rsboost_current       NUMERIC(4, 1),   -- [-6.0, -3.0, 0.0, 3.0, 6.0]
    rsboost_before_cr     NUMERIC(4, 1),   -- snapshot trước CR để rollback
    rsboost_new           NUMERIC(4, 1),   -- kết quả tính toán sau trigger
    
    qrxlevmin_current     INTEGER,                      -- dBm: -128, -132, -144

    -- Tham số trước khi CR (lưu để rollback)
    
    qrxlevmin_before_cr   INTEGER,                      -- null nếu chưa có CR

    -- Tham số sau CR (kết quả tính toán)
    

    qrxlevmin_new         INTEGER,                      -- null nếu chưa có CR

    -- Metadata từ CĐS
    huong_id              VARCHAR(10),                  -- XY: X=band, Y=sector
    priority              INTEGER,                      -- 1|2|3|4
    action_type           VARCHAR(20),                  -- rsboost|qrxlevmin|skip

    -- FK session CR gần nhất
    cr_session_id         INTEGER         REFERENCES cr_session(id),

    last_synced_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at            TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cell_params_tram_id   ON cell_params(tram_id);
CREATE INDEX idx_cell_params_cell_name ON cell_params(cell_name);
CREATE INDEX idx_cell_params_dist_name ON cell_params(dist_name_base);
CREATE INDEX idx_cell_params_session   ON cell_params(cr_session_id);
```

**Notes:**
```
- rsboost_current: parse từ "3dB" → 3.0 khi sync từ NetAct
- rsboost_before_cr: PHẢI copy từ rsboost_current NGAY KHI cr_session khởi tạo
  → đóng băng giá trị lịch sử của phiên CR đó trước khi sync-netact ghi đè
  → dùng để rollback (action=cancel)
- action_type = "skip" nếu cell đã ở cap/floor hoặc bị filter
- Upsert on conflict (tram_id, cell_name) → update
  → sync-netact chỉ update *_current, KHÔNG được ghi đè *_before_cr và *_new
    nếu cr_session_id đã có (phiên CR đang active)
```

---

## 3. BẢNG `cr_session`

> Mỗi lần trigger CR = 1 session. Track toàn bộ lifecycle.

```sql
CREATE TABLE cr_session (
    id                  SERIAL          PRIMARY KEY,
    tram_id             VARCHAR(50)     NOT NULL REFERENCES tram(tram_id),
    action              VARCHAR(20)     NOT NULL,       -- shutdown|cancel|relocate

    -- Status lifecycle
    status              VARCHAR(20)     NOT NULL DEFAULT 'PENDING',
    -- PENDING|RUNNING|DONE|FAILED|EVALUATING|EVALUATED|EVAL_PENDING

    -- NetAct plan info
    plan_name           VARCHAR(200),                   -- R012_NQMProactiveCC_{id}_{ts}
    backup_plan_name    VARCHAR(200),                   -- R012_backup_{id}_{ts}
    xml_filename        VARCHAR(200),                   -- tên file XML đã upload

    -- Kết quả đánh giá sau CR
    qoe_result          VARCHAR(20),                    -- PASS|FAIL|INSUFFICIENT_DATA|null
    qos_result          VARCHAR(20),                    -- PASS|FAIL|INSUFFICIENT_DATA|null
    qoe_before          NUMERIC(3, 2),                  -- avg QoE 7 ngày trước
    qoe_after           NUMERIC(3, 2),                  -- avg QoE 7 ngày sau
    qos_before          NUMERIC(3, 2),                  -- avg QoS 7 ngày trước
    qos_after           NUMERIC(3, 2),                  -- avg QoS 7 ngày sau

    -- Rollback tracking
    is_rollback         BOOLEAN         NOT NULL DEFAULT FALSE,
    rollback_of_id      INTEGER         REFERENCES cr_session(id), -- null nếu không phải rollback

    -- Timestamps
    executed_at         TIMESTAMP,                      -- lúc bắt đầu provision
    evaluated_at        TIMESTAMP,                      -- lúc evaluate xong
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cr_session_tram_id    ON cr_session(tram_id);
CREATE INDEX idx_cr_session_status     ON cr_session(status);
CREATE INDEX idx_cr_session_created_at ON cr_session(created_at DESC);
CREATE INDEX idx_cr_session_executed   ON cr_session(executed_at);
```

**Notes:**
```
- Mỗi trạm chỉ có 1 CR session DONE (check trước khi trigger)
- is_rollback=TRUE khi action=cancel/relocate restore
- rollback_of_id trỏ về cr_session gốc (lần trigger shutdown)
- evaluated_at: set sau khi có đủ data đánh giá
```

---

## 4. BẢNG `cr_log`

> 18 bước chi tiết của mỗi CR session. Dùng cho SSE stream + xem lại log.

```sql
CREATE TABLE cr_log (
    id              SERIAL          PRIMARY KEY,
    cr_session_id   INTEGER         NOT NULL REFERENCES cr_session(id),

    step            INTEGER         NOT NULL,           -- 1..18
    step_name       VARCHAR(100)    NOT NULL,           -- "Gọi CĐS API", "Build XML", ...
    status          VARCHAR(20)     NOT NULL,
    -- running|success|failed|skipped

    message         TEXT,                               -- mô tả chi tiết / lỗi
    pct             INTEGER,                            -- % tiến trình (cho SSE progress)
    detail          JSONB,                              -- data bổ sung tùy bước
    -- VD: {"cells_found": 9, "directions": 3}
    -- VD: {"error": "Connection timeout", "host": "netact01"}

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cr_log_session_id ON cr_log(cr_session_id);
CREATE INDEX idx_cr_log_step       ON cr_log(cr_session_id, step);
```

**18 step_name chuẩn:**
```
Step  1  "Validate input"
Step  2  "Query tram info từ DB"
Step  3  "Gọi CĐS API /cell/neighbors"
Step  4  "Filter cell (null, VNP-, duplicate)"
Step  5  "Apply band priority filter"
Step  6  "Assign priority: rsboost / qrxlevmin"
Step  7  "Lấy rsboost_current từ DB"
Step  8  "Tính rsboost_new (+3dB theo scale [-3,0,3,6])"
Step  9  "Lấy qrxlevmin_current từ DB"
Step 10  "Tính qrxlevmin_new (-4dBm, floor -144)"
Step 11  "Lưu cell_params vào DB"
Step 12  "Build XML RAML 2.0"
Step 13  "Upload XML lên NetAct (SFTP)"
Step 14  "SSH: racclimx.sh Import"
Step 15  "SSH: racclimx.sh Provision"
Step 16  "Parse kết quả SSH"
Step 17  "Cập nhật cr_session status"
Step 18  "Snapshot QoS baseline (CTS)"
```

---

## 5. BẢNG `qoe_snapshot`

> QoE score từ SOC. Lưu theo ngày để tính before/after CR.

```sql
CREATE TABLE qoe_snapshot (
    id              SERIAL          PRIMARY KEY,
    cr_session_id   INTEGER         NOT NULL REFERENCES cr_session(id),
    cell_name       VARCHAR(200)    NOT NULL,
    snapshot_date   DATE            NOT NULL,           -- ngày lấy data (UTC)
    qoe_score       NUMERIC(3, 2)   NOT NULL,           -- 1.00 - 5.00
    period          VARCHAR(10)     NOT NULL,            -- before|after
    source          VARCHAR(20)     NOT NULL DEFAULT 'soc',

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    UNIQUE(cr_session_id, cell_name, snapshot_date, period)
);

CREATE INDEX idx_qoe_session    ON qoe_snapshot(cr_session_id);
CREATE INDEX idx_qoe_cell_date  ON qoe_snapshot(cell_name, snapshot_date);
CREATE INDEX idx_qoe_period     ON qoe_snapshot(cr_session_id, period);
```

---

## 6. BẢNG `qos_snapshot`

> QoS score từ CTS. Lưu theo ngày để tính before/after CR.

```sql
CREATE TABLE qos_snapshot (
    id              SERIAL          PRIMARY KEY,
    cr_session_id   INTEGER         NOT NULL REFERENCES cr_session(id),
    cell_name       VARCHAR(200)    NOT NULL,
    snapshot_date   DATE            NOT NULL,           -- ngày lấy data (UTC)
    qos_score       NUMERIC(3, 2)   NOT NULL,           -- 1.00 - 5.00
    period          VARCHAR(10)     NOT NULL,            -- before|after
    source          VARCHAR(20)     NOT NULL DEFAULT 'cts',

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    UNIQUE(cr_session_id, cell_name, snapshot_date, period)
);

CREATE INDEX idx_qos_session    ON qos_snapshot(cr_session_id);
CREATE INDEX idx_qos_cell_date  ON qos_snapshot(cell_name, snapshot_date);
CREATE INDEX idx_qos_period     ON qos_snapshot(cr_session_id, period);
```

**Notes (chung cho qoe + qos snapshot):**
```
- period="before": lấy 7 ngày trước CR (T-7 → T-1)
- period="after":  lấy 7 ngày sau CR (T+1 → T+7)
- UNIQUE constraint: tránh duplicate khi retry evaluate
- source: "soc" cho QoE, "cts" cho QoS
- Nếu API trả missing day → không insert row đó
  → avg tính trên số row thực tế (không chia cho 7 cố định)
  → nếu < 5 row/period → INSUFFICIENT_DATA
```

---

## 7. BẢNG `alert_log`

> Cảnh báo khi phát hiện degradation sau CR.

```sql
CREATE TABLE alert_log (
    id              SERIAL          PRIMARY KEY,
    cr_session_id   INTEGER         NOT NULL REFERENCES cr_session(id),
    alert_type      VARCHAR(50)     NOT NULL,
    -- QOE_DEGRADED | QOS_DEGRADED | EVAL_PENDING_TOO_LONG

    severity        VARCHAR(20)     NOT NULL DEFAULT 'WARNING',
    -- WARNING | CRITICAL

    message         TEXT            NOT NULL,
    detail          JSONB,
    -- VD: {"qoe_before": 3.5, "qoe_after": 2.8, "delta": -0.7}

    is_acknowledged BOOLEAN         NOT NULL DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_session    ON alert_log(cr_session_id);
CREATE INDEX idx_alert_type       ON alert_log(alert_type);
CREATE INDEX idx_alert_created    ON alert_log(created_at DESC);
CREATE INDEX idx_alert_ack        ON alert_log(is_acknowledged);
```

**Alert types:**
```
QOE_DEGRADED:          qoe_after < qoe_before
QOS_DEGRADED:          qos_after < qos_before
EVAL_PENDING_TOO_LONG: cr_session ở EVAL_PENDING > 30 ngày
```

---

## 8. BẢNG `audit_log`

> Mọi thao tác quan trọng. Actor + action + result + context.

```sql
CREATE TABLE audit_log (
    id              SERIAL          PRIMARY KEY,

    -- Ai làm
    actor           VARCHAR(100),
    -- "user:ktvA" | "system:n8n" | "system:cr_engine"

    -- Làm gì
    action          VARCHAR(50)     NOT NULL,
    -- CR_TRIGGER | CR_XML_BUILD | CR_SSH_IMPORT | CR_SSH_PROVISION
    -- CR_EVALUATE | CR_ROLLBACK
    -- SYNC_ENODEB | SYNC_CELL_PARAMS | SYNC_TRAM_STATUS
    -- CONFIG_UPDATE

    -- Làm với cái gì
    target_type     VARCHAR(50),
    -- "tram" | "cr_session" | "cell_params" | "system_config"
    target_id       VARCHAR(100),
    -- tram_id, session_id, cell_name, config_key

    -- Kết quả
    status          VARCHAR(20)     NOT NULL,
    -- SUCCESS | FAILED | PARTIAL

    -- Chi tiết linh hoạt
    detail          JSONB,
    -- {"error": "SSH timeout", "step": 14}
    -- {"cells_affected": 9, "directions": 3}
    -- {"old_value": "-128", "new_value": "-132"}
    -- {"records_synced": 58219, "duration_sec": 47}

    -- Trace về CR session (nullable)
    cr_session_id   INTEGER         REFERENCES cr_session(id),

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_action     ON audit_log(action);
CREATE INDEX idx_audit_session    ON audit_log(cr_session_id);
CREATE INDEX idx_audit_created    ON audit_log(created_at DESC);
CREATE INDEX idx_audit_status     ON audit_log(status);
CREATE INDEX idx_audit_actor      ON audit_log(actor);
```

---

## 8.1 BẢNG `cr_affected_cells`

> Phương án B (22072026, ĐÃ DUYỆT thiết kế). 47 cell "bị ảnh hưởng" (Nhánh A —
> `NeighborCellFilter.filter_affected()`, KHÔNG lọc huống/band), khác
> `cell_params` (12 cell "chạy CR" — Nhánh B, được điều chỉnh rsboost/qrxlevmin
> thật). Lưu riêng để sau này đánh giá chất lượng trên đúng phạm vi RF bị ảnh
> hưởng, không chỉ 12 cell được điều chỉnh tham số.

```sql
CREATE TABLE cr_affected_cells (
    id              SERIAL          PRIMARY KEY,
    cr_session_id   INTEGER         NOT NULL REFERENCES cr_session(id),
    cell_name       VARCHAR(200)    NOT NULL,
    tram_id         VARCHAR(50),                  -- LNBTS, nullable (site chưa sync RIMS)
    huong_id        VARCHAR(10),                  -- nullable (xem Cell.huong_id Nhánh A)
    dist_name       VARCHAR(300),                 -- nullable, tiện đối chiếu sau

    created_at      TIMESTAMPTZ     NOT NULL,      -- KHÔNG server_default, xem note đầu file

    UNIQUE(cr_session_id, cell_name)
);

CREATE INDEX idx_affected_cells_session ON cr_affected_cells(cr_session_id);
CREATE INDEX idx_affected_cells_cell    ON cr_affected_cells(cell_name);
```

**Notes:**
```
- KHÔNG dùng chung cell_params: cell_params có UNIQUE(tram_id, cell_name) —
  trạng thái HIỆN TẠI của 1 cell vật lý (upsert liên tục bởi sync-netact hàng
  ngày), 1 cell chỉ giữ được DUY NHẤT 1 cr_session_id tại 1 thời điểm. Nếu 1
  cell là "affected" của NHIỀU CR session khác nhau theo thời gian sẽ MẤT
  lịch sử session trước. Bảng này khóa theo (cr_session_id, cell_name) — cùng
  pattern qoe_snapshot/qos_snapshot (Section 5/6).
- Ghi CÙNG lúc cell_params.upsert() (buộc 11 của run_cr_flow()), dùng
  ICrAffectedCellsRepo.bulk_insert() — lỗi ghi KHÔNG làm fail CR (chỉ log
  warning, data phụ trợ cho đánh giá, không phải data CORE của CR).
- KHÔNG backfill 6 session cũ (trước 22072026) — dữ liệu test, chấp nhận
  bảng rỗng cho các session đó. GET /sessions/{id} trả affected_cells=[]
  bình thường, không lỗi.
- tram_id = LNBTS trong dist_name của CHÍNH cell (trạm chứa cell), KHÁC
  cr_session.tram_id (trạm tắt). Đo 19/10/2026: 178/178 phiếu khớp, 0 trùng
  trạm tắt. Dashboard + Excel phiếu lấy tỉnh/vendor của cell qua cột này.
```

---

## 8.2 BẢNG `cr_phieu` (bổ sung tài liệu 19/10/2026 — bảng có từ KHỐI 2/5)

> Phiếu xuất CLK qua CTS SaveCellClm — 1 dòng / (session, cell). Model:
> `models/cr_phieu.py`; migration gốc `f717675f110d_create_cr_phieu.py`.

| Cột | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | INTEGER PK | | Mã log nội bộ — KHÔNG phải mã phiếu CTS |
| `cr_session_id` | INTEGER FK cr_session.id | NOT NULL | Session CR |
| `cell_name` | VARCHAR(200) | NOT NULL | Cell được xuất phiếu |
| `trang_thai` | VARCHAR(30) | NOT NULL | Xem bảng giá trị bên dưới |
| `request_payload` | JSONB | NOT NULL | 28 key gửi CTS; dòng KHONG_XUAT_* chỉ là marker (`_khong_xuat`, `_ly_do`...) |
| `response_body` | JSONB | NULL | `{isError, code, message, data, status_code}` (+ `raw_body` khi lỗi) — mã lỗi CTS nằm ở `code`/`status_code`, KHÔNG có cột riêng |
| `phieu_id` | VARCHAR(100) | NULL | Mã phiếu CLK (ticketId TTS), chỉ có khi SUCCESS |
| `error_message` | TEXT | NULL | Thông báo lỗi / lý do không xuất |
| `so_lan_thu` | INTEGER | NOT NULL, default 0 | Số lần đã POST thật lên CTS |
| `nguon_khong_dat` | VARCHAR(10) | NULL | QOS / QOE / CA_HAI; NULL = dòng cũ hoặc KHONG_XUAT_* |
| `created_at` | TIMESTAMPTZ | NOT NULL | Lúc TẠO dòng (không phải lúc gửi) |
| `deleted_at` | TIMESTAMPTZ | NULL | Xoá mềm; mọi API đọc đều lọc `IS NULL` |

UNIQUE `(cr_session_id, cell_name)`; index `idx_cr_phieu_session`.

**Giá trị `trang_thai` + nhóm** (khai báo 1 chỗ: `domain/value_objects/trang_thai_phieu.py`,
dùng chung dashboard, bộ lọc `/phieu`, Excel phiếu, Excel hậu kiểm):

| Nhóm | trang_thai | Ý nghĩa |
|---|---|---|
| THANH_CONG | SUCCESS | Đã tạo phiếu trên CTS (có `phieu_id`) |
| LOI | FAILED | Đã gọi CTS nhưng bị từ chối / lỗi mạng hết lượt retry |
| CHO_XUAT_TAY | KHONG_XUAT_THIEU_DU_LIEU | Không đủ ngày dữ liệu QoS/QoE để kết luận |
| CHO_XUAT_TAY | KHONG_XUAT_VUOT_GIOI_HAN | Vượt trần phiếu mỗi sector của trạm tắt |
| CHO_XUAT_TAY | KHONG_XUAT_HET_LUOT_THU | Đã POST hết `XUAT_PHIEU_MAX_RETRY` lần vẫn lỗi |
| CHO_XUAT_TAY | KHONG_XUAT_DA_CO_PHIEU_THANG | Cell đã có phiếu SUCCESS cùng tháng |
| (không nhóm) | PENDING | Tạm trong lúc gọi CTS — kẹt lâu là bất thường |

`DAT_KHONG_XUAT` chỉ là kết quả trả về của POST /phieu, KHÔNG bao giờ ghi DB.
Số liệu 19/10/2026: SUCCESS 145 (PA "2": 137, PA "1": 8), FAILED 5, CHO_XUAT_TAY 28; tổng 178.

**request_payload — key có giá trị thay đổi** (các key còn lại là hằng số trong
`xuat_phieu_use_case.py`): `Nam`/`Thang` (int, tháng của executed_at GMT+7),
`TenCell`, `SiteName` (trạm CỦA CELL), `Qos`/`Qoe` (str, `int(min)` điểm theo ngày
7 ngày sau CR — KHÁC TB hậu kiểm), `SoChiTieuVP` ("2" khi CA_HAI, còn lại "1"),
`PhuongAnXuLyDuKien` ("2" Hiện trường khi TB sau QoS hoặc QoE < 3.0, "1" Hệ thống),
`NoiDung`, `Vendor`, `ProvinceCode`, `BuildingCode`, `BuildingName`.

## 8.3 BẢNG `cr_phieu_lan_thu`

> Lịch sử TỪNG lần POST CTS của 1 dòng cr_phieu (model `models/cr_phieu_lan_thu.py`,
> migration `b3f7d21ac504`). Excel phiếu dùng `max(thoi_diem)` làm "Gửi lần cuối".

| Cột | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | INTEGER PK | | |
| `cr_phieu_id` | INTEGER FK cr_phieu.id ON DELETE CASCADE | NOT NULL | Dòng phiếu |
| `thoi_diem` | TIMESTAMPTZ | NOT NULL | Lúc POST |
| `nguoi_thuc_hien` | VARCHAR(20) | NOT NULL | JOB_AUTO / MANUAL |
| `ket_qua` | VARCHAR(30) | NOT NULL | Kết quả lần POST |
| `phieu_id` | VARCHAR(100) | NULL | Mã phiếu nếu thành công |
| `error_message` | TEXT | NULL | |
| `request_payload` / `response_body` | JSONB | NULL | Payload / response của lần đó |

---

## 9. ALEMBIC MIGRATION

### Thứ tự tạo bảng (dependency order)
```
1. tram           (không có FK)
2. cr_session     (FK → tram; self-ref rollback_of_id)
3. cell_params    (FK → tram, cr_session)
4. cr_log         (FK → cr_session)
5. qoe_snapshot   (FK → cr_session)
6. qos_snapshot   (FK → cr_session)
7. alert_log      (FK → cr_session)
8. audit_log      (FK optional → cr_session)
9. cr_affected_cells (FK → cr_session) — them 22072026, migration rieng 35c121cc3135
```

### Commands
```bash
# Init (chạy 1 lần)
alembic init alembic

# Tạo migration
alembic revision --autogenerate -m "create_8_tables_uc01"

# Apply
alembic upgrade head

# Rollback 1 bước
alembic downgrade -1

# Xem trạng thái
alembic current
alembic history
```

### env.py config (alembic/env.py)
```python
from models.tram import Tram
from models.cr_session import CrSession
from models.cell_params import CellParams
from models.cr_log import CrLog
from models.qoe_snapshot import QoeSnapshot
from models.qos_snapshot import QosSnapshot
from models.alert_log import AlertLog
from models.audit_log import AuditLog
from sqlmodel import SQLModel

target_metadata = SQLModel.metadata
```

---

## 10. SQLMODEL — PATTERNS

### Async engine setup (infrastructure/db.py)
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

engine = create_async_engine(
    DATABASE_URL,           # postgresql+asyncpg://...
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,     # check connection health
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

### Upsert pattern (tram sync)
```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(Tram).values(**tram_data)
stmt = stmt.on_conflict_do_update(
    index_elements=["tram_id"],
    set_={
        "tram_name": stmt.excluded.tram_name,
        "longitude": stmt.excluded.longitude,
        "latitude": stmt.excluded.latitude,
        "last_synced_at": stmt.excluded.last_synced_at,
        "updated_at": stmt.excluded.updated_at,
    }
)
await session.execute(stmt)
await session.commit()
```

### Updated_at auto-update
```python
# Trong SQLModel model: dùng event hoặc set manually trước commit
from datetime import datetime, timezone

record.updated_at = datetime.now(timezone.utc)
await session.commit()
```

---

## 11. DATA EXAMPLES

### tram record
```json
{
  "tram_id": "160000",
  "tram_name": "4G-CBG001M-CBG",
  "ten_quan_ly": "Cầu Bươu",
  "ma_csht": "CSHT-HNI-001",
  "ma_tinh": "01",
  "longitude": 105.8412,
  "latitude": 20.9876,
  "ten_thiet_bi": "Nokia AirScale",
  "trang_thai": "active"
}
```

### cell_params record (sau CR)
```json
{
  "tram_id": "160000",
  "cell_name": "4G-CBG001M11-CBG",
  "dist_name_base": "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
  "dist_name_lncel_fdd": "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11/LNCEL_FDD-0",
  "dist_name_sib": "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11/SIB-0",
  "rsboost_current": 3.0,
  "rsboost_before_cr": 0.0,
  "rsboost_new": 3.0,
  "qrxlevmin_current": -128,
  "qrxlevmin_before_cr": null,
  "qrxlevmin_new": null,
  "huong_id": "11",
  "priority": 1,
  "action_type": "rsboost"
}
```

### cr_session record
```json
{
  "tram_id": "160000",
  "action": "shutdown",
  "status": "EVALUATED",
  "plan_name": "R012_NQMProactiveCC_160000_20260708_143022",
  "qoe_result": "PASS",
  "qos_result": "FAIL",
  "qoe_before": 3.80,
  "qoe_after": 4.10,
  "qos_before": 3.50,
  "qos_after": 3.20,
  "is_rollback": false
}
```
