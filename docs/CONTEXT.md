# CONTEXT.md — Môi trường, Server, Constraints

---

## 1. TỔNG QUAN HỆ THỐNG

```
Automation_Noc1 là nền tảng tự động hóa vận hành mạng nội bộ VNPT-Net.
UC01 (R012-NQMProactiveCC) là 1 use case trong hệ thống này.

Các UC khác đã có sẵn trong cùng FE project (Automation_Noc1_FE).
UC01 được build thêm vào — KHÔNG được phá vỡ các UC đã có.
```

### Vị trí UC01 trong hệ thống lớn
```
Automation Factory Platform (xem HLD)
  └── Web Automation Portal (FE)
      └── RNOC1 Module
          ├── UC khác (đã có)
          └── R012-NQMProactiveCC  ← UC01 — đang build
```

---

## 2. MÔI TRƯỜNG PHÁT TRIỂN (LOCAL DEV)

```
OS:           Windows 10/11
IDE:          VS Code
Python:       3.x (kiểm tra: python --version)
Node:         >= 16 (kiểm tra: node --version)
Git:          Có (kiểm tra: git --version)
Internet:     Có (local dev)

BE Project:   E:\Python Project\R012-NQMProactiveCustomerCare\R012-NQMProactiveCC\
FE Project:   D:\WebSite\FE\20062026_RNOC1\Automation_Noc1_FE\
```

### Cách chạy local
```bash
# BE
cd "E:\Python Project\R012-NQMProactiveCustomerCare\R012-NQMProactiveCC"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000

# FE
cd "D:\WebSite\FE\20062026_RNOC1\Automation_Noc1_FE"
npm install
npm run dev   # hoặc npm start
```

---

## 3. MÔI TRƯỜNG PRODUCTION (SERVER LINUX)

### Server Layout
```
┌─────────────────────────────────────────────────────────┐
│  Server BE (Ubuntu — noc1auto03)                        │
│  IP: nội bộ VNPT                                        │
│  Deploy path: /home/auto/R012-NQMProactiveCC/ (dự kiến) │
│  Run: uvicorn main:app --host 0.0.0.0 --port 8000       │
│  Process manager: systemd service                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Server FE (Ubuntu)                                     │
│  Deploy path: /home/auto/Automation_Noc1_FE/dist/       │
│  Serve: nginx hoặc static file server                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Server DB (PostgreSQL — server riêng)                  │
│  KHÔNG cùng server với BE/FE                            │
│  Kết nối qua internal network                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Server eNodeB API (10.156.10.119:8080)                 │
│  CHỈ chấp nhận request từ 10.155.43.196                 │
│  → n8n sync-rims job phải chạy từ 10.155.43.196        │
└─────────────────────────────────────────────────────────┘
```

### Constraints Production
```
1. KHÔNG có internet → pip install offline:
   pip3 install --no-index \
     --find-links=/home/auto/Python_Project/Package/python_packages/ \
     --break-system-packages <package>

2. KHÔNG có load balancer / Nginx trước BE
   → FE gọi thẳng BE qua IP:port nội bộ

3. KHÔNG có staging environment (v1)
   → Test trên local → deploy thẳng production
   → Rủi ro: test kỹ domain logic trước khi deploy

4. eNodeB API (RIMS sync) chỉ gọi được từ 10.155.43.196
   → n8n và sync job phải deploy/trigger từ server đó

5. NetAct SSH: kết nối từ BE server → NetAct host (nội bộ)
   → Host, user, pass lưu trong .env (không commit)

6. PostgreSQL: kết nối từ BE server → DB server (nội bộ)
   → Connection string lưu trong .env
```

---

## 4. CẤU HÌNH .ENV

### .env.example (template — commit file này)
```ini
# === DATABASE ===
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/r012_db

# === CĐS API (SHA-512) ===
CDS_BASE_URL=https://gw-oneoss.vnpt.vn
CDS_CP_CODE=VNPT.NET.KTM.SOC
CDS_SECURE_KEY=<your_secure_key_here>

# === CTS API (QoS metrics — dùng chung credentials với CĐS) ===
CTS_BASE_URL=https://gw-oneoss.vnpt.vn
# Dùng CDS_CP_CODE và CDS_SECURE_KEY — không cần key riêng

# === SOC API (QoE — auth chưa xác nhận, để trống) ===
SOC_BASE_URL=
SOC_API_KEY=

# === ENODEB LIST API ===
ENODEB_API_URL=http://10.156.10.119:8080/application/g/enodeb_list
ENODEB_BEARER_TOKEN=<jwt_token_cố_định>
# CẢNH BÁO: chỉ gọi được từ server 10.155.43.196

# === NETACT SSH ===
NETACT_HOST=<netact_host_nội_bộ>
NETACT_USER=<username>
NETACT_PASSWORD=<password>
NETACT_UPLOAD_PATH=/d/oss/global/var/pm/shared/content3/scheduler/exportCustom/R012-NQMProactiveCC/
NETACT_SSH_TIMEOUT=30
NETACT_CMD_TIMEOUT=120

# === APP CONFIG ===
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
EVALUATION_DAYS=21
```

### .env (thực tế — KHÔNG commit, KHÔNG đưa vào git)
```
Tạo file .env từ .env.example và điền giá trị thật.
Thêm .env vào .gitignore
```

---

## 5. EXTERNAL SYSTEMS — CHI TIẾT KẾT NỐI

### 5.1 CĐS API (OneOSS)
```
Vai trò:    Cung cấp danh sách cell lân cận + QoS metrics tham chiếu
Base URL:   https://gw-oneoss.vnpt.vn
Auth:       SHA-512 signature — 4 headers
Timeout:    30s
Retry:      3 lần khi timeout, không retry khi 4xx

Auth details (SUA 11072026 B6.2 — bang duoi day la cong thuc DA SAI, tung lam
CDS/CTS luon tra HTTP 500. Cong thuc DUNG da verify that trong
adapters/http/sha512_auth.py):
  X-Request-Id:   UUID4 mỗi request (uuid.uuid4())
  X-Request-Date: format "yyyyMMddHHmmss", GIỜ GMT+7 (KHÔNG PHẢI UTC)
  X-Cp-Code:      VNPT.NET.KTM.SOC  (từ .env: CDS_CP_CODE)
  X-Secure-Code:  SHA-512( X-Request-Id + "|" + X-Request-Date + "|" + X-Cp-Code + "|" + secureKey )
                  (có dấu "|" phân cách VÀ có cả cp_code trong chuỗi hash)
                  secureKey = <CDS_SECURE_KEY> (từ .env)

Endpoints dùng trong UC01:
  POST /oss/vps/service/vpsService/cell/neighbors      ← cell lân cận
  POST /oss/cts-integrate/api/CtsReport/mbb-qos-cell-4g ← QoS metrics

Trạng thái: ĐÃ TEST THẬT ✅
Timezone:
  X-Request-Date dùng UTC: datetime.utcnow().isoformat() + "Z"
  (xem Timezone Policy bên dưới — Section 5.6)
```

### 5.2 SOC/CEM API
```
Vai trò:    Cung cấp QoE score để đánh giá sau CR
Auth:       CHƯA XÁC NHẬN ⚠️ → viết SocHttpAdapter dạng MOCK
Endpoint:   POST /api/v1/qoe/cells
Trạng thái: CHƯA TEST — dùng mock, fill thật khi có thông tin

LƯU Ý: SOC CHỈ CÓ QoE — KHÔNG có QoS API riêng
        QoS evaluation dùng CTS (đã có ✅)
```

### 5.3 eNodeB List API (RIMS)
```
Vai trò:    Danh sách trạm (enodeb_id, tọa độ, mã CSHT, ...)
URL:        POST http://10.156.10.119:8080/application/g/enodeb_list
Auth:       Bearer JWT (token cố định trong .env)
Giới hạn:  CHỈ gọi được từ IP 10.155.43.196
Phân trang: pageIndex + pageSize (max 1000/page)
Tổng:       ~58,219 records (~5,822 trang)
Timeout:    60s (fetch nhiều trang)
Trạng thái: ĐÃ TEST THẬT ✅

Data anomaly cần handle:
  longitude=0, latitude=0    → không crash, ghi warning
  ma_tinh=None               → cho phép null
  ma_csht=None               → cho phép null
  ten_quan_ly (control chars) → sanitize trước khi lưu DB
```

### 5.4 NetAct / OSS (Nokia)
```
Vai trò:    Nhận CR XML, thực thi thay đổi tham số trên thiết bị 4G
Protocol:   SSH (Paramiko)
Tool:       racclimx.sh
Auth:       username/password từ .env

Upload path:
  /d/oss/global/var/pm/shared/content3/scheduler/exportCustom/R012-NQMProactiveCC/

Flow:
  1. SFTP upload XML file lên NetAct server
  2. SSH exec: racclimx.sh -op Import ...
  3. SSH exec: racclimx.sh -op Provision ...
  4. Parse stdout/stderr → xác nhận success

Timeout: connect=30s, banner=30s, auth=30s, cmd=120s
Trạng thái: Có syntax thật ✅ (xem docs/API_CONTRACTS.md)
```

### 5.5 n8n Scheduler
```
Vai trò:    Trigger background jobs tự động theo lịch
Cách hoạt động:
  n8n → POST /jobs/sync-rims    (hàng ngày, từ 10.155.43.196)
  n8n → POST /jobs/sync-netact  (hàng ngày)
  n8n → POST /jobs/sync-status  (hàng ngày)
  n8n → POST /jobs/evaluate-cr  (hàng ngày — check session cần evaluate)

BE response: 202 Accepted ngay → chạy asyncio background task
Không cần API key (internal network)
n8n KHÔNG xử lý logic — chỉ trigger
```
### 5.6 TIMEZONE POLICY — TOÀN BỘ BACKEND

Nguyên tắc: UTC inside, GMT+7 outside

  Lưu DB:        UTC (tất cả timestamp — created_at, updated_at, ...)
  Logic nội bộ:  UTC (tính toán, so sánh thời gian)
  API headers:   NGOẠI LỆ — X-Request-Date (SHA-512 auth CDS/CTS) dùng GIỜ GMT+7,
                 format "yyyyMMddHHmmss" (SUA 11072026 B6.2, xem SS5.1 chi tiet +
                 adapters/http/sha512_auth.py). Request body "from"/"to" (CTS,
                 SS2 API_CONTRACTS.md) vẫn UTC ISO như cũ — đã verify thật, không đổi.
  CTS "from/to": GMT+7 → convert sang UTC trước khi gọi API
                 VD: "2025-06-01T23:59:59+07:00" hoặc "2025-06-01T16:59:59Z"
  Hiển thị FE:   Convert UTC → GMT+7 tại FE (dùng dayjs hoặc date-fns-tz)
  Log timestamp: UTC (dễ correlate với external system logs)

Lý do:
  - CĐS/CTS API nhận UTC → dùng UTC tránh nhầm lẫn
  - DB lưu UTC → không bị DST issues
  - FE convert → một điểm duy nhất xử lý timezone display



---

## 6. POSTGRESQL — DATABASE

```
Version:    PostgreSQL 12+ (async với asyncpg)
ORM:        SQLModel (SQLAlchemy async engine)
Migration:  Alembic
Connection: asyncpg (async driver)

Connection string format:
  postgresql+asyncpg://user:password@host:5432/dbname

8 bảng (chi tiết xem docs/DB_SCHEMA.md):
  tram, cell_params, cr_session, cr_log,
  qoe_snapshot, qos_snapshot, alert_log, audit_log

Index quan trọng:
  tram.tram_id, tram.tram_name
  cell_params.cell_name, cell_params.dist_name_base
  cr_session.tram_id, cr_session.status, cr_session.created_at
  audit_log.action, audit_log.cr_session_id, audit_log.created_at
```

---

## 7. FE PROJECT — THÔNG TIN CÓ SẴN

```
Project:    Automation_Noc1_FE (đang chạy, có các UC khác)
Framework:  React 17 + TypeScript
Build tool: Vite 6 / Webpack 5
UI:         Ant Design 5
Routing:    React Router (đã có MainPageRoute.tsx)
Config:     menu_config.json (đã có các UC khác)

Cách thêm UC01:
  1. Thêm entry vào menu_config.json:
     { "code": "R012NQMProactiveCC", "path": "/r012-nqm-proactive-cc", ... }
  2. Thêm Route vào MainPageRoute.tsx
  3. Tạo folder src/components/RNOC1/R012-NQMProactiveCC/
  4. Tạo entry component R012HomeNQMProactiveCC.tsx

QUAN TRỌNG: KHÔNG sửa code của các UC khác đã có
            KHÔNG thay đổi cấu trúc routing hiện tại (chỉ thêm)
            KHÔNG đổi config chung của project
```

### FE Axios Base URL
```typescript
// Tạo axios instance riêng cho UC01
// Base URL lấy từ env (VITE_R012_API_URL hoặc dùng chung VITE_API_BASE_URL)
// Không hardcode URL — dùng import.meta.env.VITE_API_BASE_URL
```

### Map Tiles (Leaflet)
```
OSM offline tiles: zoom 6-12, ~300MB
Download trên Windows → deploy cùng với FE build
Không dùng online tiles (môi trường production có thể không có internet)
Tile path: public/tiles/{z}/{x}/{y}.png (hoặc theo cấu trúc đã có)
```

---

## 8. LOGGING STRATEGY

```
Library:  Python logging (stdlib) — cấu hình trong infrastructure/logger.py
Format:   [LEVEL] [timestamp] [module] key=value key=value — message
Output:   Console (stdout) + file log (nếu production)
NOTE:     v1 dùng text format — dễ đọc bằng tail -f khi debug live
          Nếu sau này tích hợp ELK/Grafana Loki → đổi sang JSON format
          (chỉ cần thay formatter trong infrastructure/logger.py, không sửa code khác)

Log levels:
  DEBUG:   Chi tiết internal, chỉ bật khi debug
  INFO:    Bước thực hiện bình thường (step 1/18, sync done, ...)
  WARNING: Dữ liệu bất thường nhưng không crash (cell_id=null, anomaly, ...)
  ERROR:   Lỗi có thể recover (API timeout, retry, ...)
  CRITICAL: Lỗi không recover (SSH fail hoàn toàn, DB down, ...)

Mandatory context fields trong mọi log:
  session_id  (khi trong CR flow)
  tram_id     (khi xử lý trạm cụ thể)
  cell_name   (khi xử lý cell cụ thể)
```

---

## 9. ERROR HANDLING STRATEGY

```
Domain errors (domain/errors.py):
  TramNotFoundError      → HTTP 404
  CdsApiError            → HTTP 502
  SshConnectionError     → HTTP 502
  XmlBuildError          → HTTP 500
  QoeDataInsufficientError → HTTP 202 (chưa đủ data, không phải lỗi)

HTTP errors → api/middleware/ global error handler
  → Format chuẩn: {"error_code": "...", "message": "...", "session_id": "..."}

SSE errors → emit event {"status": "failed", "msg": "...", "step": N}
  → Không đóng stream đột ngột — luôn emit event trước khi close


Retry policy:
  CĐS API:       retry 3 lần (exponential backoff 1s, 2s, 4s)
  CTS API:       retry 3 lần
  SFTP upload:   retry 3 lần (chỉ upload file — chưa tác động thiết bị)
  SSH Import:    KHÔNG retry — đã gửi lệnh racclimx.sh là không thể undo
  SSH Provision: KHÔNG retry — tác động trực tiếp live network, retry nguy hiểm
  DB:            SQLModel/asyncpg tự handle connection pool
```

---

## 10. SECURITY

```
Credentials:   Lưu trong .env — KHÔNG commit, KHÔNG log, KHÔNG in ra console
SSH password:  Paramiko — không hardcode, lấy từ .env
Bearer token:  eNodeB API — lấy từ .env
SHA-512 key:   CĐS/CTS — lấy từ .env

.gitignore phải có:
  .env
  __pycache__/
  *.pyc
  venv/
  .venv/
  *.log

CORS:  Chỉ allow origin của FE server (cấu hình trong main.py)
n8n → BE: Không cần auth (internal network) — có thể thêm IP whitelist sau
```

---

## 11. GIT STRATEGY

```
Branch:
  main      ← production-ready code
  develop   ← integration branch
  feature/  ← feature branches (VD: feature/b1-skeleton)

Commit message format:
  [Part][Task] mô tả ngắn
  VD: [B1] Create project skeleton
      [B2] Add RsboostLevel value object
      [C1] Implement BandPriorityFilter

.gitignore:
  .env, __pycache__, venv/, *.pyc, *.log, dist/, node_modules/
```

---

## 12. KNOWN CONSTRAINTS & RISKS

| # | Constraint | Impact | Xử lý |
|---|-----------|--------|-------|
| 1 | SOC QoE auth chưa xác nhận | SocHttpAdapter chưa code thật | Dùng mock — fill sau |
| 2 | Không có staging env | Risk live network | Test domain logic kỹ trước deploy |
| 3 | eNodeB chỉ từ 10.155.43.196 | sync-rims job phải deploy đúng server | Note rõ trong deployment guide |
| 4 | Nokia XML: không có id/version | xml_builder không thêm attribute này | Đã xác nhận từ file thật |
| 5 | SOC field "cell_ name" (space) | Không auto-correct | Để nguyên, chờ xác nhận |
| 6 | Offline pip install | Không thể thêm package tùy tiện | List đủ trong requirements.txt từ đầu |
| 7 | CTS "to" = T-1 23:59:59 | Sai format → mất data | Xử lý trong CtsHttpAdapter |
