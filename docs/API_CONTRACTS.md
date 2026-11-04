# API_CONTRACTS.md — API Contracts UC01

> Tất cả request/response đã được test thật hoặc có contract chính thức.
> Phần SOC QoE: auth chưa xác nhận → dùng mock.
> KHÔNG tự suy luận field name hay auth scheme ngoài những gì ghi ở đây.

---

## 1. CĐS API — CELL NEIGHBORS (KHÔNG CÒN DÙNG TỪ 12/10/2026)

> **BỎ CDS (quyết định 18/10/2026)**: từ 12/10/2026 xem trước/chạy CR CHỈ dùng
> HO + Delaunay (BUSINESS_RULES.md mục 2-HO), `.env NEIGHBOR_SOURCE` đã bỏ. Mục
> này giữ làm lịch sử. `CDS_CP_CODE`/`CDS_SECURE_KEY` VẪN cần — CTS dùng chung.

### Endpoint
```
POST https://gw-oneoss.vnpt.vn/oss/vps/service/vpsService/cell/neighbors
Timeout: 30s
Retry:   3 lần (exponential backoff 1s, 2s, 4s)
Status:  ĐÃ TEST THẬT ✅
```

### Authentication — SHA-512
```
SUA 11072026 (B6.2): cong thuc ben duoi (ISO UTC, khong pipe) da test that va
LUON tra HTTP 500 — SAI. Cong thuc DUNG da verify that (200 OK, tram 110548,
368 cells) nam trong adapters/http/sha512_auth.py:
  - X-Request-Date format "yyyyMMddHHmmss", gio GMT+7 (KHONG PHAI UTC)
  - X-Secure-Code = SHA512(request_id + "|" + request_date + "|" + cp_code + "|" + secure_key)
    (co dau "|" phan cach, VA co ca cp_code trong chuoi hash)
Nguon doi chieu: Script/Test_api_CDS/test_cds_neighbors.py (script thuc nghiem
cua team, phan anh dung Postman script CDS cung cap).
Giu nguyen code block duoi day CHI de tham khao lich su — KHONG dung lai.
```
```python
# ĐÃ XÁC NHẬN SAI (11072026) - xem adapters/http/sha512_auth.py cho công thức đúng
import uuid, hashlib
from datetime import datetime, timezone

def build_sha512_headers(cp_code: str, secure_key: str) -> dict:
    request_id   = str(uuid.uuid4())
    request_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw          = request_id + request_date + secure_key
    secure_code  = hashlib.sha512(raw.encode()).hexdigest()
    return {
        "X-Request-Id":   request_id,
        "X-Request-Date": request_date,
        "X-Cp-Code":      cp_code,       # VNPT.NET.KTM.SOC
        "X-Secure-Code":  secure_code,
        "Content-Type":   "application/json"
    }
# secure_key = <CDS_SECURE_KEY> (từ .env)
# cp_code    = VNPT.NET.KTM.SOC (từ .env: CDS_CP_CODE)
```

### Request Body (camelCase)
```json
{
  "tramId":     "160000",
  "tramName":   "4G-CBG001M-CBG",
  "action":     "shutdown",
  "technology": "4G"
}
```
```
tramId hoặc tramName: ít nhất 1 trong 2
action:     "shutdown" | "cancel" | "relocate"
technology: "4G" (cố định trong UC01 v1)
```

### Response 200 OK
```json
{
  "status":      "success",
  "tram_id":     "160000",
  "total_cells": 9,
  "huongs": [
    {
      "huong_id":   11,
      "huong_name": "4G-CBG001M11-CBG",
      "cells": [
        {
          "cell_id":    "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
          "cell_name":  "4G-HKM053M11-CBG",
          "priority":   1,
          "technology": "4G",
          "status":     "active"
        },
        {
          "cell_id":    "PLMN-PLMN/MRBTS-160001/LNBTS-160001/LNCEL-12",
          "cell_name":  "4G-HKM053M12-CBG",
          "priority":   2,
          "technology": "4G",
          "status":     "active"
        }
      ]
    }
  ]
}
```

### Response Error
```json
{
  "status":     "error",
  "error_code": "SITE_NOT_FOUND",
  "message":    "Không tìm thấy trạm",
  "timestamp":  "2025-06-01T10:00:00Z"
}
```

### Data Quality — Đã gặp thực tế
```
- cell_id = null           → bỏ qua cell, log WARNING
- huong_id = null          → bỏ qua hướng, log WARNING
- cell prefix "VNP-"       → operator khác, bỏ qua, log WARNING
- cell_id dạng PHẲNG       → cell NGOÀI PHẠM VI CDS quản lý, bỏ qua, log WARNING
  (không có "LNBTS-", cell_id = chính cell_name, VD "4G-PYN015M12-VPC")
  Thêm 07092026. CDS trả HTTP 200 đúng spec — cell_id phẳng chính là tín hiệu
  "tôi không quản lý cell này", KHÔNG phải dữ liệu hỏng. Trước đó code coi là
  lỗi và ném ValueError → HTTP 500 cho cả request.
  Gặp thật: trạm 112391 (NOKIA, Hà Nội) — CDS trả 6 cell, 3 DN + 3 phẳng, trong
  đó "4G-PYN015M12-VPC" (Vĩnh Phúc) làm vỡ preview. KHÔNG phải lỗi riêng
  Huawei: mọi trạm GIÁP RANH TỈNH đều dính.
  KHÔNG lọc theo hậu tố tỉnh: cell_infor có 8 dòng "-VPC" trên 27.763 → ranh
  giới tỉnh không sạch, lọc theo hậu tố sẽ loại nhầm cell thật sự quản lý được.
  cell_id phẳng là tín hiệu từ CHÍNH NGUỒN, đáng tin hơn suy từ tên.
- Số cell/hướng < 4        → bình thường, xử lý đủ cell có
- Duplicate huong_id       → giữ first, bỏ rest, log WARNING
- huong_id dạng số nguyên  → parse XY: X=band, Y=sector
```

---

## 2. CTS API — QoS METRICS

### Endpoint
```
POST https://gw-oneoss.vnpt.vn/oss/cts-integrate/api/CtsReport/mbb-qos-cell-4g
Timeout: 60s
Retry:   3 lần
Status:  ĐÃ TEST THẬT ✅
Auth:    SHA-512 — dùng chung credentials với CĐS (xem Section 1)
```

### Request Body
```json
{
  "cell_name":   ["4G-HKM053M11-CBG", "4G-HKM053M12-CBG"],
  "from":        "2025-06-01T00:00:00Z",
  "to":          "2025-06-07T23:59:59Z",
  "granularity": "day"
}
```
```
QUAN TRỌNG — "to" parameter:
  ĐÚNG: "2025-06-07T23:59:59Z"  ← end of day T-1
  SAI:  "2025-06-08T00:00:00Z"  ← mất data ngày 07

Luôn set to = (today - 1 day) at 23:59:59Z
  from datetime import datetime, timezone, timedelta
  to = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
      hour=23, minute=59, second=59, microsecond=0
  )

granularity: "day" (string — không phải enum)
```

### Response 200 OK
```json
{
  "status": "success",
  "data": [
    {
      "cell_id":   "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
      "cell_name": "4G-HKM053M11-CBG",
      "metrics": [
        {"time": "2025-06-01T00:00:00Z", "qos": 4.2},
        {"time": "2025-06-03T00:00:00Z", "qos": 3.8}
      ]
    }
  ]
}
```
```
QUAN TRỌNG:
- API chỉ trả ngày có data — missing day là bình thường
- metrics có thể ít hơn số ngày request (VD: request 7 ngày → trả 5 ngày)
- qos scale: 1.0 - 5.0
- granularity="day" nhưng time field có thể trả hourly → parse đúng
```

### Dùng cho 2 mục đích trong UC01
```
① Widget F33 (Tab1): 48h hourly QoS — xem trend trước CR
   from = 48 giờ trước, to = yesterday 23:59:59


② Đánh giá sau CR (BR-05): 7 ngày before + 7 ngày after
   before: from=CR_date-8days, to=CR_date-1day 23:59:59
   after:  from=CR_date+1day, to=CR_date+7days 23:59:59

LƯU Ý granularity cho cả 2 use case:
   Luôn dùng granularity="day" (cố định)
   CTS API trả về metrics[] theo giờ (hourly) dù request là "day"
   → Widget F33: parse tất cả metrics[] items → 48 điểm hourly
   → BR-05: group by date → avg theo ngày
```

---

## 3. SOC API — QoE EVALUATION

### Endpoint
```
POST /api/v1/qoe/cells
Auth:   CHƯA XÁC NHẬN ⚠️ — viết SocHttpAdapter dạng MOCK
Status: CHƯA TEST
```

### Request Body (từ contract — CHƯA XÁC NHẬN)
```json
{
  "cell_ name":  ["4G-HKM053M11-CBG", "4G-HKM053M12-CBG"],
  "from":        "2025-06-01T00:00:00Z",
  "to":          "2025-06-07T23:59:59Z",
  "granularity": "day"
}
```
```
⚠️ FIELD "cell_ name" CÓ SPACE — KHÔNG tự sửa thành "cell_name"
   Để nguyên theo contract cho đến khi SOC team xác nhận
⚠️ SOC CHỈ CÓ QoE — KHÔNG có QoS API riêng
   QoS evaluation dùng CTS (Section 2)
```

### Response (dự kiến từ contract)
```json
{
  "status": "success",
  "data": [
    {
      "cell_id":   "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
      "cell_name": "4G-HKM053M11-CBG",
      "metrics": [
        {"time": "2025-06-01T00:00:00Z", "qoe": 3.8}
      ]
    }
  ]
}
```

### Mock Implementation
```python
# adapters/http/soc_http_adapter.py
# MOCK — thay thế khi có auth thật

class SocHttpAdapter:
    async def get_qoe(
        self,
        cell_names: list[str],
        from_date: datetime,
        to_date: datetime,
        granularity: str = "day"
    ) -> list[dict]:
        # TODO: implement khi SOC team xác nhận auth
        # Hiện tại trả mock data để test flow
        logger.warning("SocHttpAdapter đang dùng MOCK data")
        return [
            {
                "cell_name": name,
                "metrics": [
                    {"time": from_date.isoformat(), "qoe": 3.5}
                ]
            }
            for name in cell_names
        ]
```

---

## 4. ENODEB LIST API — RIMS

### Endpoint
```
POST http://10.156.10.119:8080/application/g/enodeb_list
Auth:   Bearer JWT (token cố định — từ .env: ENODEB_BEARER_TOKEN)
Status: ĐÃ TEST THẬT ✅

QUAN TRỌNG: CHỈ gọi được từ IP 10.155.43.196
            → n8n sync job phải chạy từ server đó
```

### Request Body
```json
{
  "pageIndex": 1,
  "pageSize":  1000
}
```
```
pageSize tối đa: 1000
Tổng records:   ~58,219
Tổng trang:     ~5,822
```

### Response 200 OK
```json
{
  "data": [
    {
      "enodeb_id":    "160000",
      "ten_he_thong": "4G-CBG001M-CBG",
      "ma_tinh":      "01",
      "longitude":    105.841200,
      "latitude":     20.987600,
      "ma_csht":      "CSHT-HNI-001",
      "ten_thiet_bi": "Nokia AirScale"
    }
  ],
  "total": 58219,
  "pageIndex": 1,
  "pageSize": 1000
}
```

### Data Anomaly — Đã gặp thực tế
```
longitude = 0, latitude = 0  → lưu NULL vào DB (không lưu 0)
ma_tinh = None                → lưu NULL
ma_csht = None                → lưu NULL
ten_quan_ly (control chars)   → sanitize trước khi lưu:
  import re
  def clean(s): return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s or '')
```

### Pagination Script Pattern
```python
async def fetch_all_enodeb(session: AsyncSession) -> list[dict]:
    page, records = 1, []
    while True:
        resp = await call_enodeb_api(pageIndex=page, pageSize=1000)
        data = resp.get("data", [])
        if not data:
            break
        records.extend(data)
        page += 1
    logger.info("sync enodeb done", extra={"total": len(records)})
    return records
```

---

## 5. NETACT SSH — NOKIA

### Connection (Paramiko)
```python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(
    hostname=NETACT_HOST,       # từ .env
    username=NETACT_USER,       # từ .env
    password=NETACT_PASSWORD,   # từ .env
    timeout=30,                 # connection timeout
    banner_timeout=30,          # banner handshake timeout
    auth_timeout=30,            # auth timeout
)
```

### Bước 1 — SFTP Upload XML
```python
# Retry 3 lần (SFTP upload — chưa tác động thiết bị)
remote_path = (
    "/d/oss/global/var/pm/shared/content3/scheduler/"
    "exportCustom/R012-NQMProactiveCC/"
    f"{xml_filename}"
)

with ssh.open_sftp() as sftp:
    sftp.put(local_xml_path, remote_path)
# xml_filename = R012_NQMProactiveCC_{tram_id}_{YYYYMMDD_HHMMSS}.xml
```

### Bước 2 — SSH Import Plan
```bash
racclimx.sh -op Import \
  -type plan \
  -planName {plan_name} \
  -inputFile {remote_path} \
  -UIValues true \
  -v
```
```python
cmd = (
    f"racclimx.sh -op Import "
    f"-type plan "
    f"-planName {plan_name} "
    f"-inputFile {remote_path} "
    f"-UIValues true "
    f"-v"
)
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
exit_code = stdout.channel.recv_exit_status()
out = stdout.read().decode()
err = stderr.read().decode()

# KHÔNG retry — đã gửi lệnh là không undo
```

### Bước 3 — SSH Provision (Activate)
```bash
racclimx.sh -op Provision \
  -planName {plan_name} \
  -v \
  -createBackupPlan true \
  -provisioningOperation activate \
  -backupPlanName {backup_plan_name}
```
```python
cmd = (
    f"racclimx.sh -op Provision "
    f"-planName {plan_name} "
    f"-v "
    f"-createBackupPlan true "
    f"-provisioningOperation activate "
    f"-backupPlanName {backup_plan_name}"
)
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
exit_code = stdout.channel.recv_exit_status()

# KHÔNG retry — tác động live network
```

### Parse Kết Quả SSH
```python
# SỬA 13072026 (bug thật phát hiện trên CR session #194, tram 110548):
# racclimx.sh Provision THÀNH CÔNG thật (12/12 MO, "successful for all
# MRBTSs") nhưng stdout có dòng đếm "FAILED MOS        : 0" cho MỖI DN
# thành công — substring "FAILED" khớp nhầm thành lỗi dù count=0. Bản gốc
# (substring match thô, xem git history) sai trên dữ liệu thật — loại trừ
# dòng đếm "FAILED MOS: N" trước khi check keyword; vẫn fail nếu N>0 (lỗi thật).
import re

_FAILED_MOS_COUNT_RE = re.compile(r"FAILED MOS\s*:\s*(\d+)")


def _has_error(text: str) -> bool:
    if any(int(n) > 0 for n in _FAILED_MOS_COUNT_RE.findall(text)):
        return True
    stripped = _FAILED_MOS_COUNT_RE.sub("", text)
    error_keywords = ["ERROR", "FAILED", "Exception", "error"]
    return any(kw in stripped for kw in error_keywords)


def parse_ssh_result(exit_code: int, stdout: str, stderr: str) -> bool:
    # exit_code = 0 → success
    if exit_code != 0:
        return False
    return not (_has_error(stdout) or _has_error(stderr))

# Log toàn bộ stdout + stderr vào cr_log detail (JSONB)
# Không bỏ sót — cần để debug
```

### Plan Naming
```
plan_name:   R012_NQMProactiveCC_{tram_id}_{YYYYMMDD_HHMMSS}
backup_name: R012_backup_{tram_id}_{YYYYMMDD_HHMMSS}
xml_file:    R012_NQMProactiveCC_{tram_id}_{YYYYMMDD_HHMMSS}.xml

Timestamp: UTC
VD: R012_NQMProactiveCC_160000_20260708_143022
```

### Nokia XML Format
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE raml SYSTEM 'raml20.dtd'>
<raml version="2.0" xmlns="raml20.xsd">
  <cmData type="plan" scope="all" name="R012_NQMProactiveCC_160000_20260708_143022">
    <header>
      <log dateTime="2026-07-08T14:30:22Z" action="created" appInfo="PlanExporter">
        UIValues are used
      </log>
    </header>

    <!-- rsboost: class LNCEL_FDD — 1 block/cell có rsboost -->
    <managedObject class="LNCEL_FDD"
                   distName="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11/LNCEL_FDD-0"
                   operation="update">
      <p name="dlRsBoost">3dB</p>
    </managedObject>

    <!-- qrxlevmin: class SIB — 1 block/cell có qrxlevmin -->
    <managedObject class="SIB"
                   distName="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-13/SIB-0"
                   operation="update">
      <p name="qrxlevmin">-132</p>
    </managedObject>
  </cmData>
</raml>
```
```
RULES:
  KHÔNG có attribute "id"
  KHÔNG có attribute "version"
  operation = "update" (luôn luôn)
  distName rsboost   = cell_id + "/LNCEL_FDD-0"
  distName qrxlevmin = cell_id + "/SIB-0"
  dlRsBoost value:   f"{value:g}dB"  → "3dB", "-3dB", "0dB"
  qrxlevmin value:   str(int(value)) → "-128", "-132"
  Thứ tự trong file: rsboost blocks trước, qrxlevmin blocks sau
  1 file XML duy nhất cho cả rsboost + qrxlevmin
```

---

## 6. INTERNAL BE API — FastAPI

### POST /cr/trigger
```
Mô tả: Trigger CR cho 1 trạm
Auth:  IAM/CAS (hệ thống hiện có)
```

**Request:**
```json
{
  "tram_id":   "160000",
  "tram_name": "4G-CBG001M-CBG",
  "action":    "shutdown"
}
```
```
tram_id hoặc tram_name: ít nhất 1
action: "shutdown" | "cancel" | "relocate"
```

**Response 202 Accepted:**
```json
{
  "session_id": 42,
  "status":     "PENDING",
  "message":    "CR đã được khởi tạo, theo dõi qua SSE stream"
}
```

**Response 409 Conflict:**
```json
{
  "error_code": "CR_ALREADY_DONE",
  "message":    "Trạm 160000 đã có CR session hoàn thành. Dùng action=cancel để rollback.",
  "session_id": 38
}
```

**Response 404:**
```json
{
  "error_code": "TRAM_NOT_FOUND",
  "message":    "Không tìm thấy trạm 160000"
}
```

---

### POST /cr/preview
```
Mô tả: Xem trước cell/tram bị ảnh hưởng + giá trị rsboost/qrxlevmin sẽ đổi
       (buoc 3-10 cua flow trigger that) - KHONG SSH, KHONG tao cr_session,
       KHONG ghi DB. Them 21072026 (C1.4-fix11, xem DEV_LOG.md).
Auth:  IAM/CAS (giong /cr/trigger)
```

**Request:** giống hệt `POST /cr/trigger` (`TriggerCrRequest`: `tram_id`/
`tram_name`/`action`). `action="cancel"` KHÔNG được hỗ trợ (Rollback Flow
riêng) — trả 500.

**Response 200** (SUA 22/09/2026: thay hoan toan cau truc "tram_lan_can" cu -
sai vi suy tu 12 cell Nhanh B, khong phai tu pham vi anh huong RF that - bang
3+2 field ro rang, xem `application/preview_cr_use_case.py`):
```json
{
  "tram_goc": {
    "tram_id": "111138", "tram_name": "4G-STY007M-HNI",
    "longitude": 105.495107, "latitude": 21.140749
  },
  "cells_bi_anh_huong": [
    {"cell_name": "4G-STY024M32-HNI", "huong_id": "11", "tram_id": "113456"}
  ],
  "tram_bi_anh_huong": [
    {
      "tram_id": "113456", "tram_name": "4G-STY024M-HNI",
      "longitude": 105.491906, "latitude": 21.149736
    }
  ],
  "cells_chay_cr": [
    {
      "cell_name": "4G-STY024M32-HNI", "tram_id": "113456", "huong_id": "11",
      "priority": 4, "action_type": "qrxlevmin",
      "rsboost_cu": null, "rsboost_moi": null,
      "qrxlevmin_cu": -128, "qrxlevmin_moi": -132
    }
  ],
  "so_cell_ngoai_pham_vi": 1,
  "cell_ngoai_pham_vi": ["4G-PYN015M12-VPC"],
  "cell_ngoai_pham_vi_chi_tiet": [
    {"cell_name": "4G-PYN015M12-VPC", "ly_do": "CELL_ID_PHANG"}
  ]
}
```
```
cells_bi_anh_huong / tram_bi_anh_huong (Nhanh A): PHAM VI anh huong RF -
  KHONG loc huong/band/rank, KHONG co gia tri rsboost/qrxlevmin. tram_name/
  longitude/latitude cua tram_bi_anh_huong co the null - tram MRBTS chua sync
  vao bang tram (RIMS chua co, ~0.4% du lieu that) - KHONG bi loai khoi response.
cells_chay_cr (Nhanh B): tap con cua cells_bi_anh_huong - cell THAT SU se
  duoc dieu chinh rsboost/qrxlevmin trong CR (da qua loc huong/band/rank).
cell_ngoai_pham_vi / so_cell_ngoai_pham_vi (them 07/09/2026): ten cell CDS
  TRA VE nhung khong quan ly duoc (cell_id dang PHANG, khong phai DN Nokia) -
  da bi loai khoi 3 danh sach tren. PHAI hien len UI, KHONG duoc im lang -
  ket qua thieu cell nguy hiem hon loi 500.
cell_ngoai_pham_vi_chi_tiet (them 22/09/2026, V8): BAN CHI TIET SONG SONG
  voi cell_ngoai_pham_vi (KHONG doi/xoa field cu, FE dang doc list[str]) -
  moi phan tu them ly_do (MA CO DINH, khong phai chuoi dien giai tu do):
    CELL_ID_PHANG - cell_id CDS tra ve dang PHANG (= cell_name, vd
      "4G-PYN015M12-VPC") thay vi DN Nokia -> CDS khong quan ly cell nay
      (KHAC tinh/vendor, vd giap ranh Vinh Phuc). HIEN TAI la ly do DUY NHAT
      co the xuat hien - danh sach nay se dai ra neu sau them nhanh loai moi.
  chi_tiet (THEM 23/10/2026, str | null): cau cu the cho ly_do
    OSS_CHUA_CAU_HINH, vd "NA14 cau hinh loi: thieu password",
    "NA11 cau hinh loi: route DLK|NOKIA tro toi NA khong ton tai",
    "chua co route XXX|NOKIA trong cau hinh NetAct". Chi TEN NA, khong
    host/IP/mat khau. null voi ly do khac.
```

**Response 404:** `TRAM_NOT_FOUND` (giống `/cr/trigger`).

> **SỬA 18/10/2026 (BỎ CDS)**: `CR_CDS_NO_NEIGHBOR_DATA` không còn phát sinh —
> thiếu dữ liệu nguồn nay là 422 `KHONG_CO_DU_LIEU_HO` (nhánh HO).
> `CR_NO_NEIGHBOR_CELL` giữ nguyên nhưng message đổi thành
> `"Tram X: HO co N cell nguon nhung khong cell nao du dieu kien preview"`.
> SSE bước 3 đổi tên `"Lay du lieu HO"`. Phần dưới là lịch sử thời CDS.

**Response 422 — 2 trường hợp, 2 mã khác nhau** (tách 18/09/2026):

1. `CR_CDS_NO_NEIGHBOR_DATA` — CĐS gọi thành công nhưng **trả 0 cell** (0 hướng,
   hoặc có hướng nhưng mọi hướng `cells: []`). Thiếu dữ liệu **nguồn** → xử lý ở
   CĐS, không phải ở R012.
```json
{
  "error_code": "CR_CDS_NO_NEIGHBOR_DATA",
  "message":    "Tram 111138: CDS khong co du lieu cell lan can. Co the tram moi lap hoac chua khai bao neighbor tren CDS. Lien he team CDS neu can kiem tra.",
  "session_id": null
}
```

2. `CR_NO_NEIGHBOR_CELL` — CĐS **có** trả cell nhưng bị loại hết bởi luật nghiệp
   vụ R012 (prefix `NB-`/`MBF_`/`VNP-`, cell của chính trạm gốc, `cell_id` phẳng
   ngoài phạm vi quản lý, thiếu rsboost/qrxlevmin trong `cell_infor`). `message`
   luôn kèm **tổng số cell CĐS trả về**; nếu có cell ngoài phạm vi thì kèm thêm
   số lượng + **tối đa 3 tên** làm ví dụ (trạm 280003 có 114 cell loại này):
```json
{
  "error_code": "CR_NO_NEIGHBOR_CELL",
  "message":    "Tram 111138: CDS tra 5 cell nhung khong cell nao du dieu kien preview; 5 cell ngoai pham vi quan ly R012 (vd: 4G-NPA001M11-VPC, 4G-NPA002M12-VPC, 4G-NPA003M13-VPC)",
  "session_id": null
}
```
Khi không có cell ngoài phạm vi (K=0), `message` **không** nhắc gì đến phạm vi
quản lý — chỉ còn mệnh đề đầu: `"Tram 111138: CDS tra 1 cell nhung khong cell nao du dieu kien preview"`.

**Response 502:** `CDS_API_ERROR` (giống `/cr/trigger`).

---

### GET /cr/stream/{session_id}
```
Mô tả: SSE stream — theo dõi 18 bước real-time
Content-Type: text/event-stream
```

**SSE Event format:**
```
data: {"step": 3, "step_name": "Gọi CĐS API /cell/neighbors", "pct": 20, "status": "running", "msg": "Đang gọi CĐS API..."}

data: {"step": 3, "step_name": "Gọi CĐS API /cell/neighbors", "pct": 20, "status": "success", "msg": "Lấy được 9 cells, 3 hướng"}

data: {"step": 14, "step_name": "SSH: racclimx.sh Import", "pct": 78, "status": "failed", "msg": "SSH connection timeout", "error": "Connection timed out after 120s"}

data: {"step": 18, "step_name": "Snapshot QoS baseline", "pct": 100, "status": "success", "msg": "CR hoàn thành", "done": true}
```
```
pct: 0-100 (% tiến trình)
status: "running" | "success" | "failed" | "skipped"
done: true chỉ có ở event cuối cùng
```

---

### GET /stations
```
Mô tả: Danh sách trạm cho Tab1 Zone A
```

**Query params:**
```
q        (string)  tìm kiếm theo tram_id / tram_name / ten_quan_ly / ma_csht
status   (string)  lọc theo trang_thai: active|inactive|relocating
page     (int)     mặc định 1
size     (int)     mặc định 50, max 200
```

**Response 200:**
```json
{
  "total": 1250,
  "page": 1,
  "size": 50,
  "data": [
    {
      "tram_id":      "160000",
      "tram_name":    "4G-CBG001M-CBG",
      "ten_quan_ly":  "Cầu Bươu",
      "ma_csht":      "CSHT-HNI-001",
      "longitude":    105.8412,
      "latitude":     20.9876,
      "trang_thai":   "active",
      "cr_status":    "DONE",
      "cr_session_id": 42,
      "ma_tinh":      "HNI",
      "vendor":       "NOKIA"
    }
  ]
}
```
```
cr_status: trạng thái CR session gần nhất (null nếu chưa có CR)
ma_tinh: ma tỉnh SAU sáp nhập (34 giá trị), đọc THẲNG từ cột tram.ma_tinh -
         KHÔNG suy từ hậu tố tên trạm (hậu tố là mã TRƯỚC sáp nhập, 992 giá
         trị, lệch ~37.8% so với ma_tinh thật). Có thể null (~56/58.230 dòng).
vendor: giá trị enum Vendor ĐÃ CHUẨN HÓA (domain/value_objects/vendor.py) -
        {NOKIA, ERICSSON, HUAWEI, ZTE, UNKNOWN}, KHÔNG phải ten_thiet_bi thô
        từ DB. Có thể null.
(2 trường ma_tinh/vendor thêm 18092026, commit 5c9f557 - CHỈ THÊM, không đổi/
xóa 9 trường cũ)
```

---

### GET /sessions
```
Mô tả: Lịch sử CR sessions cho Tab2 Zone D
```

**Query params:**
```
q        tìm kiếm theo tram_id / tram_name
status   PENDING|RUNNING|DONE|FAILED|EVALUATING|EVALUATED|EVAL_PENDING
from     ISO date (created_at từ ngày)
to       ISO date (created_at đến ngày)
page     mặc định 1
size     mặc định 20
```

**Response 200:**
```json
{
  "total": 156,
  "data": [
    {
      "id":           42,
      "tram_id":      "160000",
      "tram_name":    "4G-CBG001M-CBG",
      "action":       "shutdown",
      "status":       "EVALUATED",
      "qoe_result":   "PASS",
      "qos_result":   "FAIL",
      "executed_at":  "2026-07-08T14:30:22Z",
      "evaluated_at": "2026-07-29T08:00:00Z",
      "created_at":   "2026-07-08T14:30:00Z"
    }
  ]
}
```

---

### GET /sessions/{id}
```
Mô tả: Chi tiết 1 session — Tab2 Zone E / route /history/:id
```

**Response 200:**
```json
{
  "id":             42,
  "tram_id":        "160000",
  "tram_name":      "4G-CBG001M-CBG",
  "action":         "shutdown",
  "status":         "EVALUATED",
  "plan_name":      "R012_NQMProactiveCC_160000_20260708_143022",
  "qoe_result":     "PASS",
  "qos_result":     "FAIL",
  "qoe_before":     3.80,
  "qoe_after":      4.10,
  "qos_before":     3.50,
  "qos_after":      3.20,
  "executed_at":    "2026-07-08T14:30:22Z",
  "evaluated_at":   "2026-07-29T08:00:00Z",
  "cell_params": [
    {
      "cell_name":          "4G-HKM053M11-CBG",
      "huong_id":           "11",
      "priority":           1,
      "action_type":        "rsboost",
      "rsboost_before_cr":   0.0,
      "rsboost_new":         3.0,
      "qrxlevmin_before_cr": -128,
      "qrxlevmin_new":       -132
    }
  ],
  "cr_logs": [
    {
      "step":       3,
      "step_name":  "Gọi CĐS API /cell/neighbors",
      "status":     "success",
      "message":    "Lấy được 9 cells, 3 hướng",
      "pct":        20,
      "created_at": "2026-07-08T14:30:05Z"
    }
  ],
  "qoe_snapshots": [
    {"snapshot_date": "2026-07-01", "qoe_score": 3.8, "period": "before"},
    {"snapshot_date": "2026-07-09", "qoe_score": 4.1, "period": "after"}
  ],
  "qos_snapshots": [
    {"snapshot_date": "2026-07-01", "qos_score": 3.5, "period": "before"},
    {"snapshot_date": "2026-07-09", "qos_score": 3.2, "period": "after"}
  ]
}
```

---

### GET /qos/{cell_name}
```
Mô tả: 48h hourly QoS cho Widget F33
```

**Response 200:**
```json
{
  "cell_name": "4G-HKM053M11-CBG",
  "data": [
    {"time": "2026-07-07T00:00:00Z", "qos": 4.2},
    {"time": "2026-07-07T01:00:00Z", "qos": 3.9}
  ]
}
```

---

### POST /jobs/sync-rims
### POST /jobs/sync-netact
### POST /jobs/sync-status
### POST /jobs/evaluate-cr
```
Mô tả: n8n trigger background jobs
Auth:  Không cần (internal network)
```

**Response 202 Accepted (ngay lập tức):**
```json
{
  "job":     "sync-rims",
  "status":  "accepted",
  "message": "Job đã được nhận, đang chạy background"
}
```
```
BE chạy asyncio background task ngay sau khi return 202
Không block HTTP response
n8n không cần chờ kết quả — chỉ trigger
```

---

### Thêm 18/10/2026 — hậu kiểm, Excel, dashboard

**Luật đánh giá (QoS/QoE, 1 hàm `EvaluationService.evaluate`)**: TB và Lệch làm
tròn 2 chữ số TRƯỚC khi so ngưỡng — TB = round(TB thô, 2), Lệch = round(TB thô
trước − TB thô sau, 2). `< 5` ngày → THIEU_DU_LIEU; TB sau < 3.0 hoặc Lệch > 0.5
→ KHONG_DAT. Dashboard SQL dùng ROUND(...,2) cùng công thức.

**Một nguồn số liệu**: `/sessions/{id}/qos-cells`, `/qoe-cells`, Excel,
dashboard đọc snapshot đã lưu lúc đánh giá (`qos_snapshot`/`qoe_snapshot`);
chỉ gọi CTS/CEM khi CHƯA có snapshot. Response 2 endpoint có thêm
`ngay_chup_snapshot` (date GMT+7 | null = số liệu gọi trực tiếp).

**GET /phieu**: thêm `vuot_luat_lam_tron` (bool | null) — phiếu SUCCESS xuất
trước khi làm tròn mà tính lại trên snapshot thì cell không còn KHONG_DAT
(vd 32084, 25366). null cho dòng không phải SUCCESS. Tính lúc đọc, không cột DB.

**GET /hau-kiem/excel**`?session_id=` HOẶC `?tu_ngay=&den_ngay=[&ma_tinh&khu_vuc&trang_thai]`
→ .xlsx. Tên file (DOT 2): 1 session `hau_kiem_<ma_tram>_<ten_tram>_<yyyymmdd_hhmm>.xlsx`,
nhiều session `hau_kiem_<tu>_den_<den>_<yyyymmdd_hhmm>.xlsx` (ngày yyyymmdd; ký tự lạ
trong tên trạm → `_`). Header `Content-Disposition` có cả `filename` và
`filename*=UTF-8''...`. Sheet "Hau kiem" (cột A..S, xem dưới) + sheet "Chu giai"
(ý nghĩa màu + luật). Màu: tiêu đề #DDEBF7, nhóm QoS #E2EFDA, QoE #EDE7F6, Phiếu
#FFF2CC; Đạt #E8F5E9, Không đạt #FDECEA chữ đỏ đậm, Thiếu dữ liệu #F2F2F2; ô có mã
phiếu #FFF8E1; khối session xen kẽ trắng / #FAFAFA. Freeze 3 dòng tiêu đề.
Cột (SỬA 19/10/2026): A Ngày thực hiện | B Trạm tác động | C Site ảnh hưởng | D Cell ảnh hưởng |
E Cell chạy CR (R012) | F Cell hậu kiểm | G-M QoS (TB trước, TB sau, Lệch, Đánh giá,
Số ngày có DL trước n/7, Số ngày có DL sau n/7, Số ngày ≥3 n/7) | N-T QoE (như QoS) |
U Mã phiếu | V Phương án | W Trạng thái phiếu (tô màu theo nhóm) | X Ghi chú.
Tiêu đề nhóm "HAU KIEM (Trung binh QoS, QoE 7 ngay truoc / sau CR)". Sheet
thứ 2 "Phieu" = các phiếu của session/khoảng đang xuất, CÙNG hàm vẽ với
`/phieu/excel`. Sheet "Chu giai" thêm: "Số ngày ≥3" chỉ là thống kê; ý nghĩa
trạng thái/nhóm phiếu. 422 nếu thiếu cả session_id lẫn khoảng ngày.

**GET /phieu** (THÊM 19/10/2026): mỗi item thêm `phuong_an` ("He thong" | "Hien truong"
| null — từ `request_payload.PhuongAnXuLyDuKien`, null với KHONG_XUAT_*) và
`nhom_trang_thai` (THANH_CONG | LOI | CHO_XUAT_TAY | null = PENDING). Lọc
`trang_thai` nhận đủ 7 giá trị trong `TRANG_THAI_LOC` (hết 422 với
KHONG_XUAT_DA_CO_PHIEU_THANG). Tham số lọc mới (lặp tham số để chọn nhiều):
`khu_vuc[]` (KV1/KV2/KV3), `ma_tinh[]`, `vendor[]` (NOKIA/ERICSSON/HUAWEI/ZTE) —
theo TRẠM CỦA CELL (`cr_affected_cells.tram_id` → `tram`, KHÔNG phải trạm tắt);
`khu_vuc` × `ma_tinh` lấy GIAO (giao rỗng → 0 dòng); `phuong_an[]` (1/2, từ
`request_payload.PhuongAnXuLyDuKien` — dòng KHONG_XUAT_* không khớp giá trị nào).
Dùng CHUNG hàm lọc với `/phieu/excel`: cùng bộ lọc → `total` = số dòng Excel.
Cột `tram_id`/`tram_name` của item vẫn là trạm TẮT (không đổi).

**GET /phieu/excel** (THÊM 19/10/2026)`?session_id=` HOẶC `?tu_ngay=&den_ngay=`
+ `trang_thai`, `q`, `nguon` (như GET /phieu) + `khu_vuc[]`, `ma_tinh[]`, `vendor[]`
(theo TRẠM CỦA CELL qua `cr_affected_cells.tram_id`), `phuong_an[]` (1/2) → .xlsx
`phieu_<tu>_den_<den>_<yyyymmdd_hhmm>.xlsx` (1 session không ngày:
`phieu_session_<id>_<ts>.xlsx`). Không phân trang, lọc `deleted_at IS NULL`.
Cùng hàm lọc (`CrPhieuRepo._filter_conditions`) với GET /phieu.
Sheet "Phieu" cột: Ma log | Ma phieu CLK | Cell | Tram cua cell | Tinh | Vendor |
Session CR | Tram tat (session) | Tao luc | Gui lan cuoi (max `cr_phieu_lan_thu.thoi_diem`)
| So lan thu | Trang thai | Nhom trang thai | Phuong an | Nguon khong dat | QoS gui
CTS (min 7 ngay sau) | QoE gui CTS (min 7 ngay sau) | So chi tieu VP | Noi dung |
Ma loi (`HTTP <status_code> / <response_body.code>`) | Thong bao loi. Giờ GMT+7.
Không đưa các key hằng số của payload. Tô CẢ DÒNG theo nhóm: THANH_CONG #E8F5E9,
LOI #FDECEA, CHO_XUAT_TAY #FFF2CC, PENDING không tô. Sheet "Chu giai": ý nghĩa
trạng thái + nhóm; QoS/QoE trong file là MIN theo ngày cắt nguyên, KHÁC TB hậu kiểm.
422 nếu thiếu cả session_id lẫn đủ 2 đầu ngày.

**Dashboard — bộ lọc chung** (DOT 2, bỏ `netact`): `tu_ngay`, `den_ngay`,
`khu_vuc[]` (KV1/KV2/KV3), `ma_tinh[]`, `vendor[]` (NOKIA/ERICSSON/HUAWEI/ZTE) —
lặp tham số để chọn nhiều. `ma_tinh`/`khu_vuc` lọc theo tỉnh của TRẠM TẮT.
**Vendor áp 2 cách**: chỉ số CR (số session/trạm/cell CR, cần xử lý) theo vendor
TRẠM TẮT; chỉ số hậu kiểm + phiếu theo vendor CỦA CELL (trạm của cell,
`tram.ten_thiet_bi` chuẩn hoá UPPER(TRIM); không ghép được → `UNKNOWN`).

**GET /dashboard/bo-loc** → `{khu_vuc: [KV1,KV2,KV3], ma_tinh: [{ma, ten, khu_vuc}],
vendor: [...]}` — DISTINCT từ bảng `tram`.

**GET /dashboard/tong-quan**`?(bộ lọc)&chi_tiet_thoi_gian=ngay|tuan` (mặc định ngay) →
`tong` (`theo_trang_thai` có ĐÚNG 6 khoá: DONE, PARTIAL_SUCCESS, KHONG_CHAY,
FAILED, dang_chay, khac — "khac" gom phần còn lại để tổng = so_session), 
`hau_kiem.qos/qoe`, `phieu`, `theo_nhom.khu_vuc/ma_tinh(kèm ten_tinh, khu_vuc)/vendor`
(SỬA 19/10/2026: `theo_nhom` và sheet "Theo nhom" BỎ nhóm `UNKNOWN`/`KHONG_XAC_DINH`/tỉnh
NULL — tổng chung vẫn tính đủ, nên tổng các nhóm có thể nhỏ hơn tổng chung),
`xu_huong[]` mỗi điểm `{moc, so_cr, so_phieu, ty_le_dat_qos, ty_le_dat_qoe,
so_cell_khong_dat_qos, so_cell_khong_dat_qoe}` — ĐỦ mọi mốc trong khoảng (mốc
trống: số = 0, tỷ lệ = null; tuần bắt đầu thứ Hai), `can_xu_ly`.

**GET /dashboard/chi-tiet**`?loai=cr|qos|qoe|phieu|can_xu_ly&(bộ lọc)&trang=1&kich_thuoc=50`
+ lọc con: `trang_thai[]` (cr, phieu), `ket_qua[]` DAT/KHONG_DAT/INSUFFICIENT_DATA
và `ly_do[]` duoi_muc/tut (qos, qoe), `phuong_an[]` 1/2 (phieu) →
`{loai, tong, trang, kich_thuoc, dong[]}`. Dòng: cr `session_id, ngay_cr,
tram_id, tram_name, ma_tinh, ten_tinh, khu_vuc, vendor_tram, status,
so_cell_cr, so_cell_anh_huong, ma_loi`; qos/qoe `session_id, ngay_cr, tram_id,
tram_name, cell_name, vendor_cell, tb_truoc, tb_sau, lech, ket_qua, ly_do,
so_ngay_co_du_lieu, ma_phieu`; phieu `ma_phieu, session_id, cell_name,
vendor_cell, phuong_an, trang_thai, ngay_xuat`; can_xu_ly `loai
(QUA_HAN_XUAT_PHIEU|KHONG_CHAY), session_id, tram_id, tram_name, status, ngay,
ma_loi`. Cùng CTE với tong-quan: `tong` không lọc con = số trên card.
Tìm + sắp xếp + phân trang ở BE (18/10/2026): `q` tìm tự do, không phân biệt
hoa/thường và dấu (chuẩn hoá Python + `translate(lower())` ở SQL, KHÔNG cần
extension unaccent) — cr: tram_id, tram_name, ma_tinh, tên tỉnh, session_id;
qos/qoe: tram_name, cell_name, session_id, ma_phieu; phieu: ma_phieu, cell_name,
session_id; can_xu_ly: tram_id, tram_name, session_id. `sap_xep` (cột cho phép,
sai → 422) + `chieu` asc|desc, mặc định cột ngày giảm dần, NULL xếp cuối, khoá
phá hoà cố định nên các trang không trùng. `kich_thuoc` ≤ 200. `tong` = số dòng
SAU lọc + tìm. Cột sắp xếp: cr `ngay_cr, session_id, tram_id, tram_name,
ma_tinh, ten_tinh, khu_vuc, vendor_tram, status, so_cell_cr, so_cell_anh_huong,
ma_loi` (ten_tinh/khu_vuc JOIN ở SQL từ hằng số Python, 19/10/2026); qos/qoe
`ngay_cr, session_id, tram_name, cell_name, vendor_cell, tb_truoc, tb_sau, lech,
ket_qua, so_ngay_co_du_lieu, ma_phieu`; phieu `ngay_xuat, ma_phieu, session_id,
cell_name, vendor_cell, phuong_an, trang_thai`; can_xu_ly `ngay, loai,
session_id, tram_id, tram_name, status, ma_loi`. `/chi-tiet/excel` nhận cùng
`q`/`sap_xep`/`chieu`, xuất TOÀN BỘ dòng khớp.

**GET /dashboard/chi-tiet/excel**`?(cùng tham số, không phân trang)` → .xlsx
`dashboard_<loai>_<tu>_den_<den>_<ts>.xlsx`. **GET /dashboard/excel**`?(bộ lọc)` →
.xlsx tổng hợp `dashboard_tong_hop_<tu>_den_<den>_<ts>.xlsx`: sheet Tong quan,
Theo nhom (KV/Tinh/Vendor), Xu huong, Can xu ly, Chu giai.

---

## 7. ERROR CODE CHUẨN

```
Tất cả lỗi trả về format:
{
  "error_code": "...",
  "message":    "...",
  "session_id": null hoặc số
}

Mã lỗi:
  TRAM_NOT_FOUND        → 404  Không tìm thấy trạm
  CR_ALREADY_DONE       → 409  CR đã chạy xong, dùng cancel để rollback
  CR_ALREADY_RUNNING    → 409  CR đang chạy, không trigger thêm
  CR_ROLLBACK_NO_SOURCE → 400  Không có before_cr để rollback
  CDS_API_ERROR         → 502  CĐS API lỗi sau 3 lần retry
  SSH_CONNECTION_ERROR  → 502  Không kết nối được NetAct SSH
  XML_BUILD_ERROR       → 500  Lỗi build XML
  QOE_INSUFFICIENT_DATA → 202  Chưa đủ data đánh giá (không phải lỗi)
  CR_CDS_NO_NEIGHBOR_DATA → 422  POST /cr/preview: CĐS OK nhưng trả 0 cell
                                 (0 hướng, hoặc mọi hướng cells=[]) — thiếu dữ
                                 liệu nguồn, liên hệ team CĐS
  CR_NO_NEIGHBOR_CELL     → 422  POST /cr/preview: CĐS CÓ trả cell nhưng bị luật
                                 nghiệp vụ R012 loại hết (prefix, cell trạm gốc,
                                 cell_id phẳng, thiếu rsboost/qrxlevmin)
  KHONG_CO_DU_LIEU_HO   → 422  Thiếu dữ liệu HO tin cậy cho trạm tắt (chưa nạp HO,
                                 không có HO, mọi sector dưới N_MIN, tên trạm sai mẫu)
  CAU_HINH_NETACT_LOI   → 422  (THÊM 23/10/2026) NetAct của trạm tắt chưa cấu hình /
                                 cấu hình lỗi. Message chỉ tên NA, vd "Khong xac dinh
                                 duoc NetAct cho tram 114664: NA14 cau hinh loi: thieu
                                 password". Xử lý: sửa file NETACT_SERVERS_FILE + restart
                                 (docs/DEPLOY.md). cr_session.status = KHONG_CHAY.
  INTERNAL_ERROR        → 500  Lỗi không xác định

Câu lỗi NetAct lên API/cr_log (SSH_CONNECTION_ERROR, CAU_HINH_NETACT_LOI) chỉ ghi
TÊN NA (NA09...), không host/IP (23/10/2026). Host vẫn có trong log file netact.
```
