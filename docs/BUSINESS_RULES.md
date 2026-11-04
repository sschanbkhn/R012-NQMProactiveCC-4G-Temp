# BUSINESS_RULES.md — Quy tắc nghiệp vụ UC01

> File này là nguồn sự thật (source of truth) cho toàn bộ domain logic.
> Mọi code trong domain/ phải trace back về file này.
> KHÔNG tự suy luận hay mở rộng rule — chỉ implement đúng những gì đã ghi ở đây.

---

## 1. TRIGGER — ĐẦU VÀO HỆ THỐNG

```
Input:  tram_id HOẶC tram_name (1 trong 2, không bắt buộc cả hai)
        action = "shutdown" | "cancel" | "relocate"
        technology = "4G" (chỉ xử lý 4G trong v1)

Validate:
  - tram_id hoặc tram_name phải có ít nhất 1
  - Nếu chỉ có tram_name → lookup tram_id từ DB (bảng tram)
  - Nếu không tìm thấy trong DB → TramNotFoundError (E001)
  - Nếu action = "shutdown"/"relocate" VÀ trạm đã có cr_session DONE
    → từ chối, trả lỗi 409 (CR chỉ chạy 1 lần duy nhất)
  - Nếu trạm đang có cr_session RUNNING
    → từ chối, trả lỗi 409 (tránh 2 CR song song)
  - Nếu action = "cancel" → chuyển sang rollback flow (xem Section 4.3)
```

---

## 2-HO. HO (HANDOVER) + DELAUNAY — THAY THẾ CDS (quyết định 06-08/10/2026)

> **BỎ CDS (quyết định 18/10/2026)**: từ **12/10/2026** mọi danh sách cell
> (xem trước, chạy CR, `cr_affected_cells`, `cell_params`) CHỈ lấy từ thuật
> toán R012 (HO + Delaunay). Công tắc `.env NEIGHBOR_SOURCE` và nhánh CDS trong
> `TriggerCrUseCase` (`_lay_du_lieu_goc_cds`, `NeighborCellFilter`,
> `PriorityAssigner`) ĐÃ GỠ — không còn "nhánh lui nhanh". Session cũ (trước
> 12/10, cell lấy qua CDS) GIỮ NGUYÊN `cr_affected_cells`/`cell_params` đã lưu,
> KHÔNG tính lại. `CdsHttpAdapter` + test của nó còn trong code nhưng KHÔNG nơi
> nào gọi (chờ duyệt xoá). Đoạn blockquote ngay dưới là lịch sử 08/10/2026.

> **BƯỚC 4b (08/10/2026, yêu cầu trực tiếp user) — ĐÃ NỐI VÀO LUỒNG THẬT.**
> `POST /cr/preview` và `POST /cr/trigger` nay CHẠY NHÁNH HO (mục này) theo
> MẶC ĐỊNH qua công tắc `.env NEIGHBOR_SOURCE=HO` — xem
> `application/trigger_cr_use_case.py::_lay_du_lieu_goc_ho()`. `CdsHttpAdapter`/
> `NeighborCellFilter` (Section 2 ngay dưới đây) **VẪN GIỮ NGUYÊN VẸN trong
> code** làm nhánh LUI NHANH — đặt `NEIGHBOR_SOURCE=CDS` để chạy lại đường cũ
> khi cần, KHÔNG tự động rơi về CDS khi nhánh HO lỗi (lỗi HO luôn là 422
> `KHONG_CO_DU_LIEU_HO`, không âm thầm fallback). Mục 2 GIỮ NGUYÊN bên dưới để
> tài liệu không nói sai về code đang có — xem mục "Luồng CR dùng HO" cuối
> mục này để biết cách 2 nhánh ghép lại với PHẦN SAU dùng chung (OSS routing +
> rsboost/qrxlevmin).
>
> **CẢNH BÁO CẤU HÌNH**: nhánh HO dùng `IOssRouter.chon_oss(...).instance_id`
> làm khoá "netact" để đọc `ho_neighbor` (PHẢI khớp CHÍNH XÁC giá trị
> `--netact` lúc nạp, vd "NA09"). Nếu `.env NETACT_SERVERS` server THẬT còn ở
> dạng CŨ (phẳng, vd `{"HNI":{host,user,password}}`) thì `instance_id` sẽ LÀ
> HOST (IP), KHÔNG PHẢI "NA09" — nhánh HO sẽ LUÔN raise 422 dù đã nạp dữ liệu
> (đã xác nhận bằng chạy thật `scripts/kiem_tra_preview_ho.py` trên DB dev:
> lỗi "Chưa có dữ liệu HO của 10.212.242.20 cho trạm 117903"). PHẢI chuyển
> `NETACT_SERVERS` sang dạng MỚI (`instances`/`routes`, giữ nguyên host/user/
> password thật, chỉ đổi "khoá" thành "NA09"/"NA14") TRƯỚC KHI dùng
> `NEIGHBOR_SOURCE=HO` ở môi trường đó — xem `.env.example`.

### Nguyên tắc: "HO thẳng tọa độ"

CDS `/cell/neighbors` tính hàng xóm từ thông số hình học NHẬP TAY (độ cao,
azimuth của trạm) — hay sai/thiếu cập nhật. HO (handover) thật từ NetAct là
BẰNG CHỨNG VẬN HÀNH THẬT: UE của trạm đang handover SANG cell nào nhiều nhất
thì cell đó ĐANG PHỦ VÙNG thật của trạm đó, không cần suy từ hình học.

**Khi HO và tọa độ (RIMS, nhập tay) MÂU THUẪN NHAU → TIN HO, nghi ngờ tọa độ
sai** (không phải ngược lại) — tọa độ chỉ dùng để KIỂM PHỤ (lớp Delaunay/15km
giúp phát hiện trường hợp HO "nhảy" tới nơi xa bất thường, nhưng không được
phép chặn cứng khi bằng chứng HO đủ mạnh).

### Nguồn số liệu

- File report HO neighbor NetAct (NA09 = tỉnh HNI, xem
  `adapters/netact/oss_router_env.py` — route `"HNI|NOKIA":"NA09"`), ~3 triệu
  dòng/lần export, nạp vào bảng `ho_neighbor` qua
  `adapters/netact/import_ho_neighbor.py` (migration `79a3855ede6b` — **ĐÃ
  CHẠY trên DB dev** kể từ SỬA lần 4 dưới đây, để đo kích thước bảng/chỉ mục
  thật).
  **SỬA 08/10/2026 lần 4 (yêu cầu trực tiếp user, "NẠP ĐẦY ĐỦ HO VÀO DB")**:
  bỏ hẳn cắt top 20/nguồn — nạp TOÀN BỘ cặp (nguồn, đích) hợp lệ, để phân
  tích/hiệu chỉnh/ước lượng vị trí cell bằng SQL trực tiếp trên DB (không chỉ
  top 20). Vì DB nay đã là nguồn ĐẦY ĐỦ, **không còn chép lưu file CSV gốc**
  (`HO_RAW_ARCHIVE_DIR`/`luu_tru_va_don_file_cu()` đã bị XOÁ khỏi code — xem
  lịch sử ở mục SỬA 08/10/2026 lần 2 phần `import_ho_neighbor.py` để biết
  tính năng CŨ đã có). Nạp bằng `asyncpg.copy_records_to_table()` (COPY nhị
  phân) trong 1 transaction duy nhất với bước XOÁ dữ liệu cũ của NetAct đó —
  lỗi ở bất kỳ bước nào (kể cả COPY) → ROLLBACK toàn bộ, dữ liệu cũ còn
  nguyên.
  **BUG THẬT phát hiện khi chạy đầy đủ trên file NA09** (chưa từng lộ ra ở
  bản top-20 cũ): gộp theo `(source_enb, source_lncel_name, target_enb,
  target_lcr)` có thể tạo 2 dòng cùng khoá UNIQUE DB `(netact, source_enb,
  source_sector, target_enb, target_lcr)` khi 2 cell nguồn VẬT LÝ khác nhau
  (tên khác) nhưng cùng sector (`%10` trùng) cùng handover tới 1 đích —
  `UniqueViolationError` khi COPY. Sửa: gộp lại THEO SECTOR (`source_enb,
  source_sector, target_enb, target_lcr`) ngay từ `doc_csv()` — đúng bản chất
  (thuật toán chọn cell cũng chỉ gom theo sector, không phân biệt
  `source_lncel_name`), `source_lncel_name` lưu lại là TÊN ĐẠI DIỆN (cell
  đóng góp nhiều `ho_attempt` nhất trong sector đó).
- Giải mã `eci_id` (ECI chuẩn 3GPP, 28-bit): `enb = eci_id // 256`,
  `lcr = eci_id % 256` — đã kiểm chứng bằng dữ liệu thật (143.112 dòng
  intra-eNB trên toàn file, xem `scripts/spike_ho_neighbor.py` Bước 2).
- Sector nguồn = chữ số cuối LNCEL ID nguồn (từ cột `DN`) `% 10` — CÙNG quy
  ước `huong_id % 10` đã dùng trong `domain/services/neighbor_cell_filter.py`.
- Toàn bộ ngưỡng dưới đây được CHỐT bằng cách đo thật trên TOÀN BỘ file NA09
  (3.045.681 dòng) + khảo sát khoảng cách TOÀN BỘ bảng tram (59.916 trạm) -
  xem `scripts/phan_tich_nguong_ho.py`, `scripts/do_khoang_cach_tram.py`.

### SỬA 08/10/2026 LẦN 2 — XỬ LÝ TRẠM TOA_DO_DUNG_CHUNG (CRAN) — THAY THẾ gộp cụm theo ma_csht

> **Luật GỘP CỤM theo `ma_csht` ở mục ngay dưới đây (SỬA 08/10/2026 lần 1) ĐÃ
> BỊ THAY THẾ hoàn toàn bởi luật SỐ SITE ở mục này** — giữ nguyên bên dưới chỉ
> để lưu lại DIỄN TIẾN quyết định (không xoá lịch sử). Code hiện tại
> (`domain/services/ho_delaunay.py`) KHÔNG còn field `ma_csht`/các hằng số
> `NGUONG_GOP_CUM_*_KM` — xem bảng ngưỡng để biết trạng thái mới nhất.

**Bằng chứng (khảo sát `scripts/kiem_gia_thuyet_cran.py`, 08/10/2026)**: trong
12.708 cặp trạm trùng toạ độ (6 số lẻ) CÙNG `ma_csht`, tách số site từ tên
(regex `_SITE_RE`) cho thấy nhiều cặp trùng toạ độ nhưng KHÁC số site (vd
4G-CGY029B-HNI trùng toạ độ với 1 trạm 4G-XXXnnnM-HNI khác site) — đối chiếu
HO thật: **73,3%** các cặp "khác site, cùng toạ độ" này gần như KHÔNG có
handover qua lại (HO < 1%) → toạ độ RIMS đang ghi theo **nơi đặt baseband/
CRAN** (1 vị trí vật lý phục vụ nhiều "site" logic), KHÔNG PHẢI vị trí anten
thật. **5.396 trạm toàn quốc (9,0%)/652 trạm HNI (10,5%)** thuộc nhóm này —
toạ độ KHÔNG dùng được làm mốc hình học cho Delaunay.

**Luật phân loại** `phan_loai_toa_do()` (hàm thuần, gọi 1 LẦN cho toàn bộ tập
trạm liên quan, KHÔNG phụ thuộc trạm X đang xét):
1. Nhóm trạm theo toạ độ (làm tròn 6 số lẻ).
2. Nhóm chỉ 1 trạm (không trùng toạ độ ai) → `TIN_CAY`.
3. Nhóm ≥ 2 trạm: so sánh SỐ SITE tách từ tên (regex DÙNG LẠI nguyên văn từ
   `scripts/kiem_gia_thuyet_cran.py`, đã mở rộng 08/10/2026 để khớp cả tiền tố
   `UL_`/`UL-`/`LN-`/`SN-` ngoài `4G-`, giảm tỷ lệ "không tách được" từ 51,7%
   xuống 4,1%): tên KHÔNG tách được số site → `TOA_DO_DUNG_CHUNG` ngay (thận
   trọng); tên tách được, TOÀN BỘ trạm KHÁC trong nhóm (có tách được số site)
   CÙNG số site → `TIN_CAY`; có BẤT KỲ trạm khác mang số site KHÁC → cả
   những trạm có tách được số site trong nhóm đều `TOA_DO_DUNG_CHUNG`.

**Tác động lên pipeline**:
- **Trạm `TOA_DO_DUNG_CHUNG` bị loại HOÀN TOÀN khỏi tập điểm Delaunay** — cả
  khi là X (trả `[]` ngay — không tính L1/L2) và khi là ứng viên (không được
  làm mốc hình học cho ai).
- **Gộp cụm THAY HOÀN TOÀN sang SỐ SITE** (thay `ma_csht`): các trạm `TIN_CAY`
  cùng số site (vd 4G-CGY029M-HNI/4G-CGY029B-HNI) gộp 1 cụm; tên không tách
  được số site nhưng là `TIN_CAY` (nghĩa là không trùng toạ độ ai) luôn là
  cụm đơn.
- **X là `TOA_DO_DUNG_CHUNG`**: không tính L1/L2 (không trả dữ liệu vành đai);
  KHÔNG áp luật vùng Z (B chọn THUẦN theo HO, giống cơ chế `HO_DI_XA` hiện có
  nhưng gắn cờ RIÊNG `x_la_toa_do_dung_chung` để báo cáo đúng nguyên nhân).
  **SỬA 08/10/2026 lần 3**: khi X là `TOA_DO_DUNG_CHUNG`, cờ `ho_di_xa_x`
  LUÔN là `False` (KHÔNG tính theo công thức thường ">50% HO vào Z") — X
  không có VỊ TRÍ đáng tin nên không thể nói HO đang "đi xa VỀ ĐÂU" (so với
  cái gì?); gắn thêm cờ này sẽ trùng lặp/sai nguyên nhân với cờ
  `x_la_toa_do_dung_chung` đã có sẵn. Hành vi bỏ chặn vùng Z (B theo HO
  thuần) GIỮ NGUYÊN.
- **Trạm ĐÍCH là `TOA_DO_DUNG_CHUNG`**: gán layer riêng **`KHONG_XAC_DINH`**
  (khác `Z`) — vì không có bằng chứng hình học nào (không giống `Z`, là
  trường hợp ĐÃ XÁC NHẬN xa qua Delaunay). Luật LỎNG HƠN `Z`: **CHỈ cần
  `SR >= 95%`** (KHÔNG đòi hỏi `% >= 20%`); `SR < 95%` → `BẤT_THƯỜNG`.

**KẾT QUẢ ĐO LẠI (mẫu 300 trạm NA09, cùng seed=42)** — lần đo gần nhất (sau
SỬA lần 3) tách RIÊNG thống kê L1/L2/%cell A/%HO_DI_XA, CHỈ tính trên tập X
`TIN_CAY` (loại hẳn 39 trạm X `TOA_DO_DUNG_CHUNG` khỏi các số liệu này — đưa
chúng vào sẽ làm lệch trung vị vì chúng luôn có `l1_l2=[]`/mọi cell rơi vào
Z hoặc KHONG_XAC_DINH một cách "giả tạo", không phản ánh mật độ hình học
thật):

| Chỉ số | Trước khi có `TOA_DO_DUNG_CHUNG` | Sau (CHỈ trên 261 trạm X `TIN_CAY`) |
|---|---|---|
| Trạm L1 (trung vị) | 7 | 6 (P10=5) |
| Trạm L2 (trung vị) | 15 | 14 (P10=10) |
| % cell A theo layer | L1 55,0% / L2 28,3% / Z 16,7% | L1 55,5% / L2 26,0% / Z 10,3% / **KHONG_XAC_DINH 8,3%** |
| % trạm X (TIN_CAY) có cờ `HO_DI_XA` | 8,0% | **2,7%** (7/261) |
| Số trạm X là `TOA_DO_DUNG_CHUNG` (loại khỏi bảng trên) | — | 39/300 (13,0%) |

`HO_DI_XA` GIẢM TIẾP (8,0%→2,7%) sau khi loại trạm `TOA_DO_DUNG_CHUNG` khỏi
thống kê — xác nhận thêm: một phần cờ `HO_DI_XA` trước đây bị "nhiễm" bởi
chính các trạm X có toạ độ không dùng được (luôn đẩy toàn bộ HO vào Z/
KHONG_XAC_DINH), chứ không phải do mô hình L1/L2 quá hẹp đối với trạm có
toạ độ đáng tin. Trạm 117903 (kiểm tra bắt buộc, X `TIN_CAY`): B vẫn đúng 6
cell như trước (110021/12, 110054/11, 110054/12, 110056/11, 110056/13,
110057/12). Trạm 117713 (Cầu Giấy — `4G-CGY025B-HNI`) là X
`TOA_DO_DUNG_CHUNG` (trùng toạ độ với 117703 `4G-CGY029M-HNI`, số site KHÁC
`CGY025`≠`CGY029`) — L1/L2 rỗng, B (12 cell) chọn thuần theo HO,
`ho_di_xa_x=False` (cố định — xem SỬA lần 3), `x_la_toa_do_dung_chung=True`.

Module: `domain/services/ho_delaunay.py::phan_loai_toa_do()`,
`domain/services/ho_cell_selector.py` (tham số `x_la_toa_do_dung_chung`,
field `ThongTinTramDich.toa_do_dung_chung`, layer `"KHONG_XAC_DINH"`,
`ho_di_xa_x` ép `False` khi `x_la_toa_do_dung_chung=True`).

### SỬA 08/10/2026 (sau review thiết kế) — GỘP CỤM SITE trước khi tam giác hoá

**Vấn đề phát hiện**: luật "cùng site nếu cách X < 0,2km" (bản đầu) chỉ xét
TỪNG CẶP riêng với X — không gộp các trạm KHÁC cùng site với NHAU trước khi
đưa vào Delaunay, khiến các điểm trùng/gần-trùng toạ độ làm qhull xử lý sai/
suy biến. Khảo sát `scripts/dieu_tra_toa_do_nghi_sai.py` (trước sửa): 76/300
trạm mẫu (25,3%) bị gắn cờ sai lệch, trung vị L1=2, **trung vị L2=0** (đồ thị
quá thưa), 81,6% trạm bị cờ nằm Ở KHU DÀY ĐẶC NHẤT (ngược trực giác).

**Luật GỘP CỤM** (`domain/services/ho_delaunay.py::_gop_cum()`, đo thật qua
`scripts/do_khoang_cach_tram.py` — toàn quốc 59.916 trạm, KD-tree trên mặt
cầu):
- Cặp trạm GẦN NHAU NHẤT **cùng `ma_csht`**: 17.550/17.554 (99,98%) trùng
  toạ độ CHÍNH XÁC (0m), chỉ 4 cặp lệch 105,9–176,3m (không merge mù). →
  `NGUONG_GOP_CUM_MA_CSHT_KM = 0.0` (so sánh `<=`, không phải `<` nghiêm
  ngặt — nếu không ngưỡng 0 sẽ vô hiệu hoá chính nó).
- Cặp **KHÁC** `ma_csht` gần nhau nhất: P1=25,05m (toàn quốc). →
  `NGUONG_GOP_CUM_KHONG_MA_CSHT_KM = 0.025km`, áp dụng cho trạm **THIẾU**
  `ma_csht` (gộp thuần theo khoảng cách D, không cần khớp mã). Khảo sát thật:
  **0/59.916 trạm thiếu `ma_csht`** — nhánh này hiện là lưới an toàn cho dữ
  liệu tương lai, chưa có ví dụ thật kích hoạt.
- Trạm CÙNG CỤM với X → L1 ngay (thay cho luật "< 0,2km" cũ, nay đã gộp đúng
  theo site vật lý thay vì khoảng cách phẳng).

### SỬA 08/10/2026 — mốc lọc cạnh dài tính theo CHÍNH X

Trước: ngưỡng = `ALPHA x trung vị khoảng cách láng giềng gần nhất CỦA TOÀN
BỘ điểm trong bubble 15km` — bị "trung bình hoá", không phản ánh mật độ CỤC
BỘ quanh X. Nay: ngưỡng = `ALPHA x trung vị ĐỘ DÀI CÁC CẠNH NỐI TRỰC TIẾP VỚI
X` (trước khi lọc) — phản ánh đúng mật độ ngay quanh X.

### SỬA 08/10/2026 — fallback khi X không có cạnh

Nếu không đủ điểm để tam giác hoá (< 4 cụm) HOẶC X cô lập trong đồ thị
Delaunay (0 cạnh trước khi lọc) → KHÔNG trả rỗng như bản cũ (đã gây 11,8%
trạm "L1=0, L2=0"). Thay bằng: xếp hạng các cụm còn lại theo khoảng cách tới
X, **6 cụm gần nhất = L1, 12 cụm tiếp theo = L2**.

### SỬA 08/10/2026 — đổi tên cờ TOA_DO_NGHI_SAI → HO_DI_XA

Tên cũ quy kết SAI nguyên nhân — khảo sát trước sửa cho thấy phần lớn (24,7%)
là do ĐỒ THỊ DELAUNAY QUÁ THƯA, không phải toạ độ sai thật. `HO_DI_XA` chỉ mô
tả QUAN SÁT (HO hiện đi xa về mặt hình học), không khẳng định nguyên nhân.
Luật kích hoạt GIỮ NGUYÊN.

### KẾT QUẢ ĐO LẠI sau khi sửa (mẫu 300 trạm NA09, cùng seed=42)

| Chỉ số | Trước sửa | Sau sửa |
|---|---|---|
| Trạm L1 (trung vị) | 2 | **7** (P10=5) |
| Trạm L2 (trung vị) | 0 | **15** (P10=10) |
| % cell A vào L1/L2 | — | **83,3%** (L1 55,0% + L2 28,3%, Z 16,7%) |
| % trạm có cờ (HO_DI_XA) | 25,3% | **8,0%** |

Xác nhận giả thuyết "mô hình L1/L2 quá hẹp" là nguyên nhân chính (không phải
toạ độ sai thật) — sửa đúng chỗ làm tỷ lệ cờ giảm hơn 2/3.

### N_MIN_HO_SECTOR (THEM 08/10/2026) — mẫu tối thiểu/sector

Đo TOÀN BỘ 15.865 nhóm (source_enb, sector) của file NA09: tổng HO/sector
P1=481, **P5=3.156**, P10=6.494, trung vị=58.346. Chốt **N_MIN_HO_SECTOR =
3156** (= P5, TẠM, theo đúng yêu cầu "đặt N_MIN tạm = P5"). Sector có tổng HO
< N_MIN → đánh dấu `IT_DU_LIEU` (vẫn xử lý bình thường, chỉ cảnh báo). MỌI
sector của X đều `IT_DU_LIEU` → xử lý NHƯ `KhongCoDuLieuHoError`.

### Bảng ngưỡng đầy đủ (hằng số có tên, `domain/services/ho_cell_selector.py`
+ `domain/services/ho_delaunay.py`)

| Hằng số | Giá trị | Lý do chốt (đo thật trên NA09) |
|---|---|---|
| `NGUONG_80_PCT` | 80% | Trung vị chỉ cần 5 cell/sector để đạt — cân bằng với trần 15 |
| `TRAN_CELL_MOI_SECTOR` | 15 | Trần 10 làm 6,3% sector chạm trần (hụt ~5,8% HO); trần 15 chỉ 0,4% sector chạm trần, phủ 98,6% HO |
| `NGUONG_BO_1_PCT` | 1% | Chỉ làm mất 9,73% tổng HO toàn cục, loại bỏ đuôi dài nhiễu |
| `NGUONG_VUNG_Z_PCT` | 20% | Dùng chung với luật "cell ở vùng Z" |
| `NGUONG_VUNG_Z_SR` | 95% | P10 của top-2/sector thực tế đã là 98,68% — ngưỡng không loại oan |
| `NGUONG_HO_DI_XA_X_PCT` | 50% | Tỷ lệ HO của X rơi vào Z vượt mốc này mới đủ mạnh để coi là HO đi xa bất thường, không phải Z thật |
| `HE_SO_KHOANG_CACH_DICH_HO_DI_XA` | 3 lần (khoảng cách L1 trung vị của X) | Chọn tương đối theo mật độ cục bộ |
| `ALPHA` (alpha-shape) | 3 | ALPHA=2 đẩy vùng Z lên 68,5% (loại oan L1/L2 thật); ALPHA=4 chỉ giảm thêm ~4,4 điểm % so với 3 |
| Bán kính vùng cục bộ | 15 km | Đủ rộng bắt hầu hết neighbor thật trong khu đô thị mật độ cao |
| ~~`NGUONG_GOP_CUM_MA_CSHT_KM`~~ | ~~0 km (`<=`)~~ | **ĐÃ BỊ THAY THẾ 08/10/2026 lần 2** bởi gộp cụm theo SỐ SITE (không còn tồn tại trong code) — xem mục XỬ LÝ TOA_DO_DUNG_CHUNG |
| ~~`NGUONG_GOP_CUM_KHONG_MA_CSHT_KM`~~ | ~~0,025 km~~ | **ĐÃ BỊ THAY THẾ 08/10/2026 lần 2** — như trên |
| Gộp cụm | theo SỐ SITE (tách từ tên, `_SITE_RE`) | Thay `ma_csht` — văn bản, không phụ thuộc GPS; CHỈ gộp trạm `TIN_CAY` (xem XỬ LÝ TOA_DO_DUNG_CHUNG) |
| Fallback (X không có cạnh) | 6 cụm gần nhất=L1, 12 tiếp theo=L2 | Thay cho trả rỗng (từng gây 11,8% trạm L1=0/L2=0) |
| `N_MIN_HO_SECTOR` | 3156 (=P5) | Phân phối tổng HO/sector toàn NA09 |
| ~~Top lưu/nguồn~~ | ~~20~~ | **BỎ 08/10/2026 lần 4** — nạp ĐẦY ĐỦ, không cắt top-N (phục vụ phân tích SQL trên toàn bộ quan hệ) |
| `MNC_HOP_LE` (`import_ho_neighbor.py`) | "02" | mnc_id khác bị loại — 100% dòng NA09 thật đã là "02" (VinaPhone), lưới an toàn cho NetAct/thuê bao khác |
| Chỉ mục `ho_neighbor` | GHÉP `(netact, source_enb)` + riêng `target_enb` | Khớp đúng mẫu truy vấn của `HoNeighborRepo.get_by_source_enb()` (luôn lọc cả 2 cột cùng lúc) — thay 2 chỉ mục riêng lẻ ở bản trước |
| Layer `KHONG_XAC_DINH` (trạm đích `TOA_DO_DUNG_CHUNG`) | chỉ `SR >= 95%` | Không đòi `% >= 20%` như `Z` — không có bằng chứng hình học để đòi khối lượng HO lớn |

Chi tiết đầy đủ (phân phối, P90/P95, ví dụ bị chặn...) xem báo cáo chạy
`scripts/phan_tich_nguong_ho.py`, `scripts/do_khoang_cach_tram.py`.

### Luật chọn cell (tóm tắt — xem code để biết chính xác)

0. **Lọc bước a** (trước khi tính %): bỏ small cell (S, P), cell nguồn MBF_,
   nội trạm (intra-eNB), attempt=0 — lọc 2 lớp (đã lọc từ lúc nạp, lọc lại
   trong `chon_cell_cr()` để không tin tuyệt đối caller).
0b. **Phân loại toạ độ** (`phan_loai_toa_do()`, trước mọi bước khác): trạm
    `TOA_DO_DUNG_CHUNG` (CRAN, xem mục XỬ LÝ TOA_DO_DUNG_CHUNG) bị loại khỏi
    tập điểm Delaunay; X là `TOA_DO_DUNG_CHUNG` → bỏ qua bước 1 (L1/L2=rỗng),
    đi thẳng xuống bước 3 (B chọn thuần theo HO).
1. **L1/L2** (gộp cụm theo SỐ SITE giữa các trạm `TIN_CAY` → Delaunay +
   alpha-shape trên đại diện cụm, bán kính 15km quanh X, cạnh dài hơn
   `ALPHA x trung_vị_cạnh_của_X` bị xoá, fallback 6/12 khi X không có cạnh)
   → KHÔNG bị chặn thêm gì khi vào B (ngoài luật Nokia/band/2-sector chung).
2. **Vùng Z/KHONG_XAC_DINH** (ngoài L1/L2): cell ở **Z** (trạm đích `TIN_CAY`,
   ngoài vành đai) cần `% trong sector >= 20%` VÀ `SR >= 95%`; cell ở
   **KHONG_XAC_DINH** (trạm đích `TOA_DO_DUNG_CHUNG`) chỉ cần `SR >= 95%`
   (không đòi `%`) — không đạt → đánh dấu `BẤT_THƯỜNG` (vẫn ở A, không vào B).
3. **X có HO_DI_XA hoặc X là TOA_DO_DUNG_CHUNG**: nếu > 50% tổng HO của X
   (tính trên danh sách A cuối cùng) rơi vào vùng Z, HOẶC X tự thân là
   `TOA_DO_DUNG_CHUNG` → KHÔNG áp luật ở bước 2 nữa cho MỌI cell Z/
   KHONG_XAC_DINH (B chọn thuần theo HO) — 2 nguyên nhân được báo cáo RIÊNG
   (`ho_di_xa_x` và `x_la_toa_do_dung_chung`), dù cùng dẫn tới hành vi bỏ qua.
   **SỬA 08/10/2026 lần 3**: X là `TOA_DO_DUNG_CHUNG` → `ho_di_xa_x` LUÔN
   `False` (không tính theo công thức ">50% vào Z" — X không có vị trí đáng
   tin nên không thể nói HO "đi xa về đâu", tránh gắn 2 cờ trùng nguyên nhân).
4. **Trạm đích có HO_DI_XA**: cell vùng Z có `% >= 20%` VÀ cách X xa hơn 3
   lần khoảng cách L1 trung vị của X → gắn cờ (độc lập với B/BẤT_THƯỜNG).
5. **Danh sách B** (chạy CR thật): từ A, bỏ BẤT_THƯỜNG, chỉ Nokia, **CÓ TÊN**
   (tên cell tra qua `cell_infor` theo DN — KHÔNG đoán từ tên trạm, vì đoán
   chỉ khớp 78,5% ngay cả với cell Nokia cùng site; cell `CAN_GHEP_TEN` —
   KHÔNG resolve được DN qua `cell_infor` — bị loại KHỎI B **TRƯỚC** khi xếp
   hạng top 2/sector, SỬA 09/10/2026, xem bên dưới), `lcr` khớp `^[13][0-9]$`,
   tối đa 2 cell/sector (thứ 1 rsboost, thứ 2 qrxlevmin), cell ở nhiều sector
   → gán sector có `%` CAO NHẤT (bằng nhau → sector nhỏ hơn).
6. **Quan hệ đầy đủ**: trả kèm TOÀN BỘ quan hệ (sector, cell đích, %, số HO,
   SR, layer) cho mỗi cell trong A — kể cả sector "phụ" bị loại bởi dedup ở
   bước 5, để xem lại/kiểm toán.

### SỬA 09/10/2026 — loại cell `CAN_GHEP_TEN` TRƯỚC khi chọn B (không phải sau)

**Bug phát hiện qua xem trước trạm 117713 thật**: trước sửa, `chon_cell_cr()`
chọn top 2/sector (rsboost+qrxlevmin) KHÔNG quan tâm cell đã resolve được DN
qua `cell_infor` hay chưa — cell `CAN_GHEP_TEN` (Nokia nhưng trạm chưa từng
sync `cell_infor`, vd trạm `111629`/`4G-CGY327M-HNI`: 0 dòng trong
`cell_infor`) vẫn chiếm 1 "suất" rank trong sector. Lớp `application/
trigger_cr_use_case.py` phải loại cell này SAU (vì không có `dist_name` để
tạo `Cell`/XML) — kết quả: **mất suất rsboost/qrxlevmin của CẢ sector đó**
(không có cell hợp lệ nào lên thay), B co lại từ 12 → 10 cell cho trạm 117713
(sector 1 + sector 2 đều mất 1 cell rsboost).

**Sửa**: thêm điều kiện `not can_ghep_ten` vào bộ lọc B TRƯỚC khi xếp hạng
top 2/sector (`domain/services/ho_cell_selector.py::chon_cell_cr()`) — cell
`CAN_GHEP_TEN` bị loại khỏi ứng viên B ngay từ đầu, để cell hợp lệ KẾ TIẾP
trong CÙNG sector lên thay đúng vị trí rank. Cell `CAN_GHEP_TEN` **vẫn giữ
trong A** (với cờ `CAN_GHEP_TEN`) — chỉ bị loại khỏi B.

Module: `domain/services/ho_delaunay.py` (L1/L2), `domain/services/
ho_cell_selector.py` (A/B + 2 cờ HO_DI_XA). Cả hai là HÀM THUẦN (không I/O) -
`application/trigger_cr_use_case.py::_lay_du_lieu_goc_ho()` là nơi DUY NHẤT
đọc DB + gọi 2 hàm này cho luồng CR thật (xem mục ngay dưới); `scripts/
kiem_tra_thuat_toan_ho.py`/`scripts/kiem_tra_preview_ho.py` dùng để chạy thử/
kiểm tra độc lập trên dữ liệu thật.

### BƯỚC 4b (08/10/2026) — Luồng CR dùng HO (thay thế bước 3-10 của CDS)

**NetAct của X**: dùng `IOssRouter.chon_oss(ma_tinh_cu, vendor)` ĐANG CÓ (mã
tỉnh cũ suy từ `tram.tram_name` qua `ma_tinh_cu_tu_ten_cell()`, vendor từ
`tram.ten_thiet_bi`) — KHÔNG viết cơ chế định tuyến riêng. `instance_id` trả
về CHÍNH LÀ khoá "netact" dùng để đọc `ho_neighbor` (xem cảnh báo cấu hình ở
đầu mục 2-HO).

**Các bước** (thay 3-10 của CDS, PHẦN SAU từ "định tuyến OSS theo từng cell"
trở đi DÙNG CHUNG với CDS — xem muc 12 docstring `trigger_cr_use_case.py`):
1. Đọc TOÀN BỘ trạm có toạ độ (1 lần) — vừa làm tập điểm Delaunay/phân loại
   toạ độ, vừa làm thông tin trạm đích (vendor/toạ độ).
2. Không tìm được NetAct (mã tỉnh cũ không suy được, hoặc OSS chưa cấu hình)
   HOẶC `ho_neighbor` rỗng cho (netact, X) HOẶC `chon_cell_cr()` tự raise
   (mọi sector dưới N_MIN) → **`HoNoDataError` (422 `KHONG_CO_DU_LIEU_HO`)**,
   message `"Chưa có dữ liệu HO của <NetAct> cho trạm <X>"` khi đã biết
   NetAct. KHÔNG tự động rơi về CDS.
3. Gọi `phan_loai_toa_do()` + `phan_lop_delaunay()` + `chon_cell_cr()` →
   danh sách A/B (xem mục 0-6 ở trên).
4. Quy đổi A/B (`CellUngVien`) sang `Cell` entity qua `ICellInforRepo.
   get_dn_map_theo_enb_lcr()` (tra `dn_lncel`/`cell_name` từ (enb,lcr) giải
   mã ECI — CÙNG quy ước **LNBTS** với `import_ho_neighbor.py`, SỬA
   10/10/2026, xem mục riêng dưới đây — TRƯỚC đó dùng MRBTS, SAI). Cell
   `CAN_GHEP_TEN` (không resolve được tên/DN) KHÔNG tạo được `Cell` hợp lệ
   (thiếu `dist_name`) → loại khỏi CẢ affected_cells và B, log cảnh báo.
5. **B** → `cells` (giống Nhánh B cũ) → chạy tiếp định tuyến OSS/rsboost/
   qrxlevmin/XML/SSH KHÔNG ĐỔI. **A chỉ cell có tên (Nokia, resolve được DN)**
   → `affected_cells` → `cr_affected_cells` (bước 11, KHÔNG đổi). Cell
   `CAN_GHEP_TEN` trong A KHÔNG ghi `cr_affected_cells`, chỉ trả trong API
   xem trước (field `ho_extra`/`PlanResult.ho_extra`) để người dùng biết.

**API `POST /cr/preview` trả thêm (field OPTIONAL, `None`/`[]` khi chạy CDS)**:
mỗi cell A/B thêm `pct_ho`/`so_ho`/`sr`/`layer` (`L1`/`L2`/`Z`/`KHONG_XAC_DINH`),
cell A thêm `co` (`BAT_THUONG`/`CAN_GHEP_TEN`; cell A `CAN_GHEP_TEN` không
ghép được tên vẫn xuất hiện với `cell_name=None`) và `sector`/`sectors_khac`
(sector đã gán cho cell — % HO cao nhất — và các sector phụ khác cũng có HO
sang cell này, THÊM 12/10/2026), `x_co` (cờ của X: `TOA_DO_DUNG_CHUNG`/
`HO_DI_XA`/`IT_DU_LIEU`/`TRAM_IBS`), `quan_he_day_du` (toàn bộ quan hệ
sector/cell đích/%/SR/layer, kể cả sector phụ bị dedup).

SỬA 14/10/2026 (yêu cầu trực tiếp user) — **BỎ field `nguon_du_lieu`**
(trước đây dạng `"HO NA09, 7 ngày đến 2026-09-28"`): hằng số "7 ngày"
(`_SO_NGAY_BAO_CAO_HO`) là SAI khi áp cho mọi NetAct — khảo sát NA14 (file
nạp 13/10/2026) ban đầu tưởng "chỉ có 1 ngày dữ liệu" vì file chỉ có 1 giá
trị `PERIOD_START_TIME`, nhưng thực chất **CẢ NA09 và NA14 đều export GỘP
THEO TUẦN** — `PERIOD_START_TIME` là NGÀY BẮT ĐẦU TUẦN (luôn rơi vào Thứ
Hai), KHÔNG PHẢI 1 ngày đơn lẻ. User quyết định KHÔNG hiển thị dòng "nguồn
dữ liệu" trên màn xem trước nữa (thay vì sửa lại chuỗi cho đúng) — field đã
bị xoá khỏi `PreviewCrResponse`/`PlanResult.ho_extra`/`CellUngVien` pipeline.
Cột `ho_neighbor.ngay_du_lieu` (ngày bắt đầu tuần của dữ liệu đang nạp) VẪN
GIỮ trong DB — chỉ không lộ ra API này nữa.

### SỬA 10/10/2026 — enb giải mã từ ECI là LNBTS, KHÔNG PHẢI MRBTS

**Bug phát hiện qua xem trước trạm 117713 thật** (xem SỬA 09/10/2026 ngay
trên — lúc đó tưởng nguyên nhân là "trạm 111629 chưa sync `cell_infor`").
Điều tra sâu hơn (yêu cầu trực tiếp user) phát hiện trạm 111629 **CÓ ĐỦ** 6
dòng trong `cell_infor` — chỉ là tra theo **MRBTS** (`1101629`) trong khi DN
thật của nó là `MRBTS-1101629/LNBTS-111629/LNCEL-xx`.

**Chứng minh `eNB ID` trong ECI = LNBTS, không phải MRBTS**:
1. **Toán học, độc lập dữ liệu**: ECI chuẩn 3GPP 28 bit = eNB ID (20 bit, tối
   đa 1.048.575) + Cell ID (8 bit). `MRBTS=1.101.629 > 1.048.575` — VƯỢT
   QUÁ sức chứa 20 bit, KHÔNG THỂ là giá trị ECI hợp lệ. `LNBTS=111.629` nằm
   trong giới hạn.
2. **Dữ liệu thật** (file NA09): lọc dòng nguồn LNBTS=111629, decode
   `target_enb=eci//256` — có **30 dòng intra-eNB** khi so `target_enb==
   111629` (LNBTS), với `target_lcr` khớp CHÍNH XÁC 6 LNCEL thật của trạm
   này; **0 dòng** khi so `target_enb==1101629` (MRBTS — khớp với (1), về
   toán học không thể xảy ra).
3. **Thực nghiệm 27.202 cặp** (target_enb,target_lcr) NA09 vendor NOKIA:
   ghép theo LNBTS = 26.937 (99,03%), theo MRBTS (quy ước CŨ) = 26.714
   (98,21%) — LNBTS là **tập con bao trùm hoàn toàn** MRBTS (223 cặp chỉ
   ghép được bằng LNBTS, 0 cặp ngược lại).
4. Toàn `cell_infor` (87.913 dòng): **2.350 dòng (2,67%)** có MRBTS ≠ LNBTS —
   cao hơn con số "0,21%/57 dòng" đã ghi trong `domain/services/dist_name.py`
   lúc trước (bảng `cell_infor` đã lớn lên kể từ đó).

**Sửa**: `domain/services/dist_name.py::MRBTS_LNCEL_RE` → đổi tên
`LNBTS_LNCEL_RE`, regex đổi sang bắt LNBTS; `adapters/postgres/
cell_infor_repo.py::get_dn_map_theo_enb_lcr()` tra theo LNBTS;
`adapters/netact/import_ho_neighbor.py::_DN_RE` (và bản sao dùng chung ở
`scripts/spike_ho_neighbor.py`, được `scripts/phan_tich_nguong_ho.py` import
lại) đổi sang bắt LNBTS — **`ho_neighbor.source_enb` giờ là LNBTS, KHÔNG
PHẢI MRBTS như trước**. Vì luật lọc intra-eNB (`target_enb == source_enb`)
trước đây so MRBTS(nguồn) với LNBTS-tương-đương(đích) cho 2,67% trạm lệch —
dữ liệu NA09 đã nạp trước SỬA này cần **nạp lại** để `source_enb` đúng và
intra-eNB được lọc đúng cho các trạm lệch.

**Không đổi** (RAML/XML gửi NetAct giữ nguyên DN đầy đủ `PLMN-PLMN/MRBTS-x/
LNBTS-y/LNCEL-z` — `XmlCellData.cell_id`/`Cell.dist_name` không bị rút gọn
hay đổi, NetAct Admin CLI cần đúng DN đầy đủ để Import/Provision).

---

## 2. CĐS API — PARSE RESPONSE (LỊCH SỬ — KHÔNG CÒN DÙNG TỪ 12/10/2026)

> **BỎ CDS 18/10/2026**: mục này chỉ còn giá trị đọc hiểu session cũ (trước
> 12/10). Code không còn gọi CDS — xem đầu mục 2-HO.

> **BƯỚC 4b (08/10/2026)**: mục này mô tả `CdsHttpAdapter`/
> `NeighborCellFilter` — code GIỮ NGUYÊN VẸN, nhưng KHÔNG CÒN LÀ ĐƯỜNG CHẠY
> MẶC ĐỊNH của `POST /cr/preview`/`POST /cr/trigger` (mặc định nay là HO, xem
> mục 2-HO). Chỉ còn chạy khi `.env NEIGHBOR_SOURCE=CDS` (nhánh lui nhanh,
> yêu cầu trực tiếp user).

### 2.1 Cấu trúc response
```
{
  "huongs": [
    {
      "huong_id": 11,        ← XY: X=band, Y=sector
      "huong_name": "...",
      "cells": [
        {"cell_id": "PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y",
         "cell_name": "4G-xxx",
         "priority": 1,      ← 1|2|3|4
         "technology": "4G",
         "status": "active"}
      ]
    }
  ]
}
```

### 2.2 Filter ngay khi parse — bỏ qua các cell sau
```
① huong_id = null          → bỏ qua toàn bộ hướng, log WARNING
② cell_id = null           → bỏ qua cell đó, log WARNING
③ cell_name prefix "VNP-"  → bỏ qua (operator khác — Viettel), log WARNING
④ status != "active"       → bỏ qua, log INFO
```

### 2.3 Duplicate huong_id (cùng huong_id, khác huong_name)
```
Trường hợp thực tế: huong_id=11 xuất hiện 2 lần với huong_name khác nhau
→ Ghi WARNING log
→ Giữ lại huong đầu tiên (first-wins)
→ Bỏ qua huong thứ 2 trở đi
Lý do: chưa xác nhận rule với CĐS team → chọn safe default
```

### 2.4 Duplicate cell xuất hiện nhiều hướng (chốt 09/2026)
```
Một cell_name xuất hiện ở nhiều hướng → dedup theo THỨ TỰ huong_id TĂNG DẦN:
→ Hướng có huong_id NHỎ HƠN xử lý trước và GIỮ QUYỀN cell đó
→ Hướng sau gặp lại cell này → bỏ qua, và KHÔNG tiêu một suất của hướng sau
  (vòng lặp `continue`, không tăng biến `picked`) → hướng sau lấy cell kế
  tiếp để vẫn đủ 2 cell, miễn còn ứng viên hợp lệ
→ Cell giữ `priority` gốc của hướng đã giành được nó
```
> **KHÔNG còn rule "rsboost luôn thắng qrxlevmin khi conflict".** Bản cũ của
> mục này mô tả dedup theo action (rsboost-wins tuyệt đối). Thuật toán đang
> chạy dedup theo thứ tự `huong_id` và điều đó đã được xác nhận là đúng — trên
> dữ liệu thật 368 cell (trạm 110548) hai cách cho cùng kết quả vì xung đột đã
> được bước 2 (band priority) giải quyết trước khi tới bước dedup.
> Code: `domain/services/neighbor_cell_filter.py::filter_for_cr()` bước 4.

---

## 3. BAND RULE — CHỌN CELL CHẠY CR

**Áp dụng CHO CR** (`filter_for_cr()`, Nhánh B) — `filter_affected()` (Nhánh A,
đánh giá QoS/QoE + xuất phiếu) KHÔNG lọc band, tính mọi band (xem Section 4b).

### 3.0 CHỐT 03/10/2026 — band là của CELL LÁNG GIỀNG, KHÔNG phải của hướng

**THAY THẾ HOÀN TOÀN luật cũ (02/10/2026, Section 3.1-3.4 bản trước)**: luật cũ
lọc theo band của HƯỚNG trạm tắt (`X = huong_id // 10`) — khảo sát dữ liệu thật
(trạm 160008) phát hiện SAI: cùng 1 cell láng giềng có thể xuất hiện ở NHIỀU
hướng trạm tắt khác nhau (band khác nhau), nên "band của hướng" không phải
thuộc tính ổn định của cell. Band THẬT SỰ cần lọc là của CHÍNH CELL LÁNG GIỀNG
sẽ bị sửa rsboost/qrxlevmin, suy từ LNCEL trong DN của chính nó — band của
hướng/trạm tắt KHÔNG còn dùng để lọc.

```
LNCEL cua CHINH CELL (2 chu so cuoi DN, VD ".../LNCEL-13" -> "13"):
  ^1[0-9]$  -> "1800 F1" (duoc chay CR)
  ^3[0-9]$  -> "1800 F2" (duoc chay CR)
  Khac (40-59, 112, 211/212...) -> KHONG duoc chay CR, ly do BAND_KHONG_CHAY_CR
```

`huong_id` vẫn dùng để xác định **sector trạm tắt** (`Y = huong_id % 10`) —
đây là đơn vị GOM NHÓM, không phải đơn vị LỌC band.

### 3.1 Thuật toán `filter_for_cr()` (6 bước)

```
[1] Gom huong_id theo SECTOR trạm tắt = chữ số cuối huong_id (Y = huong_id%10).
    huong_id null -> suy từ huong_name (vị trí cố định [10:12], xem Section 2).
    KHÔNG giới hạn số sector (khác luật cũ - không còn gắn X=1/3/4/5 cố định).

[2] Trong 1 sector: GỘP cell láng giềng của MỌI huong_id (khác luật cũ - chỉ
    1 huong "thắng" mới đóng góp). Cell trùng tên (xuất hiện ở >=2 huong cùng
    sector) -> giữ bản có priority NHỎ NHẤT; nếu priority bằng nhau, giữ bản
    từ huong có band TRẠM TẮT ưu tiên hơn (BAND_PRIORITY bên dưới) - chỉ dùng
    để TIE-BREAK, không dùng để lọc.

[3] Lọc theo band CỦA CHÍNH CELL (^[13][0-9]$, xem 3.0) + small cell (loại
    như cũ, Section 4b.1). Cell không khớp -> loại, lý do BAND_KHONG_CHAY_CR.

[4] Sắp theo (priority, band_priority của huong nguồn) - cùng cơ chế tie-break
    với bước [2].

[5] Chọn tối đa MAX_CELLS_PER_HUONG (=2)/sector: rank 1 -> rsboost, rank 2 ->
    qrxlevmin.

[6] Dedup XUYÊN SECTOR: sector nhỏ hơn (Y bé hơn) xử lý TRƯỚC và giữ quyền -
    cell đã chọn ở sector trước bị BỎ QUA (không tính vào suất đã chọn) ở
    sector sau, giống cơ chế dedup xuyên hướng cũ (chỉ đổi đơn vị "hướng"
    sang "sector").
```

`BAND_PRIORITY = {1: 1, 3: 2, 5: 3, 4: 4}` (X của huong nguồn → rank, thấp =
ưu tiên cao) — **CHỈ còn dùng để TIE-BREAK ở bước [2]/[4]**, KHÔNG còn dùng để
loại band nào (khác luật cũ, lúc đó dùng để CHỌN 1 huong "thắng" sector).

### 3.2 Ví dụ thật (trạm 160008, khảo sát 03/10/2026)

```
Huong M52 (huong_id=52, X=5,Y=2): TAN023M13(pr1,LNCEL-13), TAN025M13(pr2,LNCEL-13), TAN050M11(pr3,LNCEL-11)
Huong W11 (huong_id=11, X=1,Y=1): TAN025M13(pr1,LNCEL-13)
Huong W14 (huong_id=14, X=1,Y=4): TAN025M13(pr1,LNCEL-13)
Huong W51 (huong_id=51, X=5,Y=1): TAN023M13(pr1), TAN025M13(pr2), TAN050M11(pr3)
Huong W54 (huong_id=54, X=5,Y=4): TAN023M13(pr1), TAN025M13(pr2), TAN050M11(pr3)

Sector 1 (huong 11, 51) gộp -> TAN025M13 (pr1, từ huong 11) + TAN023M13 (pr1,
  từ huong 51) + TAN050M11 (pr3) -> top 2: TAN025M13 (rsboost), TAN023M13 (qrxlevmin)
Sector 2 (chỉ huong 52) -> TAN023M13/TAN025M13 ĐÃ CHỌN ở sector 1 -> dedup bỏ
  qua -> còn lại TAN050M11 (pr3) -> rsboost (1 mình, không đủ cell cho qrxlevmin)
Sector 4 (huong 14, 54) -> cả 3 cell ĐÃ CHỌN ở sector 1/2 -> RỖNG

Kết quả: 3 cell (KHÔNG phải 6 hay 9) - xem tests/domain/test_neighbor_cell_filter.py::TestDuLieuThatTram160008
```

### 3.3 Code reference
```python
# Từ: BUSINESS_RULES.md — Section 3 (domain/services/neighbor_cell_filter.py)
BAND_PRIORITY = {1: 1, 3: 2, 5: 3, 4: 4}  # X cua huong nguon -> rank, CHI tie-break
_LNCEL_CHAY_CR_RE = re.compile(r"^[13][0-9]$")  # band cua CHINH CELL

def band_tu_lncel(cell_id: str) -> str | None:
    local_id = cell_id.rsplit("LNCEL-", 1)[-1]
    if not _LNCEL_CHAY_CR_RE.match(local_id):
        return None
    return "1800 F1" if local_id[0] == "1" else "1800 F2"
```

---

## 4. CELL TREATMENT — RSBOOST vs QRXLEVMIN

### 4.1 Rule assign theo RANK trong hướng (cập nhật 09/2026)
```
Mỗi hướng chọn tối đa 2 cell (MAX_CELLS_PER_HUONG = 2):

Rank 1 → rsboost   (tăng 1 bậc)
Rank 2 → qrxlevmin (giảm 4 dBm)
```
> **Rank, KHÔNG phải `priority` gốc từ CĐS.** Rank là thứ hạng trong danh sách
> cell cuối cùng của mỗi hướng, sort theo `priority` tăng dần. Dùng `priority`
> gốc là sai: nó có khoảng trống (1,2,5,6) sau khi lọc NB-/MBF_/LNCEL-2xx.
> Code: `domain/services/priority_assigner.py` (`RSBOOST_RANKS={1}`,
> `QRXLEVMIN_RANKS={2}`) + `domain/services/neighbor_cell_filter.py`
> (`MAX_CELLS_PER_HUONG=2`). **Hai chỗ này phải sửa cùng lúc** — lệch nhau thì
> cell rank 3+ giữ `action_type=""` và biến mất khỏi CR mà không báo lỗi.

Trước 09/2026: tối đa 4 cell/hướng, rank 1-2 → rsboost, rank 3-4 → qrxlevmin.

### 4.2 Cell count không cố định
```
Thực tế: một hướng có thể chỉ có 1 cell (không phải luôn đủ 2)
→ Xử lý đủ cell hiện có
→ KHÔNG raise error khi thiếu cell
→ Log INFO số cell thực tế mỗi hướng

Ví dụ:
  H1 chỉ có 1 cell hợp lệ → chỉ làm rsboost, không có qrxlevmin
  H2 có ≥ 2 cell          → rsboost cho rank 1, qrxlevmin cho rank 2
```

### 4.3 Cancel / Relocate Action — Rollback Logic
```
action = "cancel" hoặc "relocate":
→ KHÔNG tính ngược (không giảm 1 bậc rsboost, không +4 qrxlevmin)
→ Restore từ DB: lấy giá trị gốc trước khi CR

Nguồn restore:
  rsboost_new   = cell_params.rsboost_before_cr   (lưu trước khi trigger)
  qrxlevmin_new = cell_params.qrxlevmin_before_cr (lưu trước khi trigger)

Lý do dùng restore thay vì tính ngược:
  - Tính ngược giả định chỉ có 1 lần thay đổi — không an toàn
  - Nếu ai đó sửa NetAct thủ công → tính ngược sai hoàn toàn
  - Restore từ DB luôn về đúng giá trị gốc

Điều kiện rollback:
  - Phải có cr_session.status = DONE trước đó
  - rsboost_before_cr / qrxlevmin_before_cr phải có trong DB
  - Nếu thiếu → từ chối rollback, log ERROR, notify admin

Flow rollback:
  1. Lấy rsboost_before_cr + qrxlevmin_before_cr từ cell_params
  2. Build XML với giá trị gốc (giống flow trigger bình thường)
  3. Upload + Import + Provision lên NetAct
  4. Cập nhật cr_session: thêm rollback_session_id
  5. Ghi audit_log: action=CR_ROLLBACK
```

---

## 4b. SMALL CELL & BAND — PHẠM VI LOẠI CELL (chốt 02/10/2026)

**CHỐT LẠI PHẠM VI cùng ngày** — small cell ban đầu chỉ định "không chạy CR",
sau đó chốt MỞ RỘNG ra cả đánh giá/xuất phiếu; band KHÔNG đổi, vẫn CHỈ áp
dụng cho CR. 2 quyết định dùng CHUNG tên gọi "loại cell" nhưng PHẠM VI khác
nhau — đọc kỹ bảng 4b.3 trước khi áp dụng.

### 4b.1 SMALL CELL — loại khỏi MỌI danh sách (CR + đánh giá + xuất phiếu)

```
Cell loại SMALL CELL (S, P) KHÔNG được đưa vào BẤT KỲ danh sách nào (chạy CR,
đánh giá QoS/QoE, xuất phiếu). Dữ liệu vẫn giữ trong cell_infor (KHÔNG xóa) —
đây là quyết định về PHẠM VI SỬ DỤNG, không phải về lưu trữ.
```

Loại trạm = 1 ký tự ngay SAU số site trong tên cell:
```
4G-TPO065S11-TQG -> "S"   (site TPO065, loại S, cell 11, tỉnh TQG)
regex: ^4G-[A-Z]+[0-9]+([A-Z])[0-9]+-[A-Z]{3}$
```

**Đo thật 5 NetAct (đếm theo loại trạm)**:

| Loại | M | W | F | S | E | X | R | P |
|---|---|---|---|---|---|---|---|---|
| Số lượng | 74.627 | 6.087 | 2.411 | 1.413 | 106 | 11 | 6 | 1 |

**CHỈ `S` và `P` là small cell** — 6 loại còn lại (M/W/F/E/X/R) là macro/các loại
trạm lớn khác, vẫn chạy CR/đánh giá bình thường.

**Chỗ loại**: CẢ `filter_affected()` (Nhánh A) **VÀ** `filter_for_cr()` (Nhánh
B, Bước 3b) — xem bảng 4b.3. Trong `filter_for_cr()`, Bước 3b vẫn **PHẢI** chạy
TRƯỚC Bước 4 (chọn tối đa `MAX_CELLS_PER_HUONG`), không phải sau: nếu chọn
trước rồi mới loại, small cell đã chiếm mất 1 suất trong hướng đó — hướng chỉ
còn lại 1 cell (hoặc 0), mất cơ hội cho cell macro xếp hạng kế tiếp (rank 3+)
được chọn thay. Loại trước thì danh sách ứng viên của hướng đã SẠCH small cell
khi Bước 4 sort theo `priority` và lấy 2 đầu.

Cell bị loại ghi vào `ngoai_pham_vi_chi_tiet`/`cell_ngoai_pham_vi_chi_tiet` với
lý do `SMALL_CELL` — dùng CHUNG cơ chế báo cáo với `CELL_ID_PHANG`/
`TEN_CELL_SAI_MAU`/`OSS_CHUA_CAU_HINH`/`BAND_KHONG_CHAY_CR` (xem Section 2.2 ③
và 7b.3). Khi `filter_for_cr()` tự gọi `filter_affected()` bên trong (không
truyền sẵn `affected_cells`), 2 out-param được CHUYỂN TIẾP xuống lời gọi đó —
tránh "mất" lý do SMALL_CELL phát sinh bên trong `filter_affected()` mà không
ai ghi lại; dedup theo `cell_name` ở cả 2 hàm đảm bảo DÙ có đi qua cả 2 đường
cũng KHÔNG ghi lý do 2 lần.

### 4b.2 BAND — CHỈ áp dụng cho CR (Nhánh B) — SỬA 03/10/2026 (band của CELL)

```
Band KHÔNG được chạy CR: LNCEL của CHÍNH CELL bắt đầu 4x/5x, hoặc không khớp
dạng 2 chữ số (VD "112").
Band ĐƯỢC chạy CR: LNCEL của CHÍNH CELL bắt đầu "1" (1800 F1) hoặc "3" (1800 F2).
Band của HƯỚNG/TRẠM TẮT KHÔNG còn dùng để lọc (SỬA so với luật 02/10/2026 -
xem Section 3.0 để biết lý do/ví dụ thật phát hiện sai).
```

Khác `SMALL_CELL` ở phạm vi: luật band CHỈ nằm trong `filter_for_cr()` (Bước
3/4, xem Section 3.1) — `filter_affected()` (Nhánh A) **KHÔNG lọc band**, vẫn
tính mọi band cho đánh giá QoS/QoE + xuất phiếu, giống hệt trước. Cell bị loại
vì band ghi lý do `BAND_KHONG_CHAY_CR` (tên mã KHÔNG đổi dù điều kiện phát
sinh đã đổi). Chi tiết thuật toán + lý do đổi: xem Section 3.

### 4b.3 Bảng phạm vi — tránh áp nhầm quyết định này sang quyết định kia

| Quyết định | `filter_affected()` (Nhánh A — CR affected_cells, QoS/QoE, xuất phiếu) | `filter_for_cr()` (Nhánh B — "cells" chạy CR) |
|---|---|---|
| SMALL CELL (S/P) | **CÓ** loại (mới, 02/10/2026) | **CÓ** loại (Bước 3b, giữ từ trước) |
| BAND (LNCEL của cell ∈ {1x,3x}) | **KHÔNG** loại — mọi band đều tính | **CÓ** loại (Bước 3, sửa lại 03/10/2026) |

`cr_affected_cells` (Nhánh A) là nguồn dữ liệu cho đánh giá QoS/QoE
(`get_qoe_cells_use_case.py`, `get_qos_cells_use_case.py`) và xuất phiếu
(`xuat_phieu_use_case.py`) — 2 danh sách này **đã tách riêng từ trước** (Phương
án B, 22/07/2026), không dùng chung 1 danh sách với "cells" chạy CR.

---

## 5. RSBOOST CALCULATION

### 5.1 Discrete scale — 5 bậc
```python

RSBOOST_SCALE = [-3.0, 0.0, 3.0, 6.0]  # đơn vị: dB (bước nhảy cố định 3dB)
# Index:            0    1    2    3

```

### 5.2 Logic tính toán
```
rsboost_current → tìm index trong RSBOOST_SCALE
rsboost_new     = RSBOOST_SCALE[current_index + 1]

Cap: nếu current_index = 3 (đang ở 6dB — max)
     → không thay đổi
     → ghi log INFO: "Cell {cell_name} đã ở bậc cao nhất (6dB), bỏ qua"
     → rsboost_new = rsboost_current (không đổi)

CR chỉ chạy 1 lần duy nhất cho mỗi trạm:
     → KHÔNG trigger lại CR cho trạm đã có session DONE
     → Kiểm tra cr_session trước khi chạy — nếu đã có DONE → từ chối

Nếu rsboost_current không nằm trong RSBOOST_SCALE:
     → tính abs(bậc_scale - rsboost_current) cho từng bậc
     → chọn bậc có khoảng cách nhỏ nhất
     → nếu khoảng cách bằng nhau (nằm chính giữa) → chọn bậc THẤP HƠN (an toàn mạng)
     → log WARNING kèm giá trị gốc và bậc đã chọn
     VD: -4.5dB → cách -6.0 là 1.5, cách -3.0 là 1.5 → tie → chọn -6.0
         -4.0dB → cách -6.0 là 2.0, cách -3.0 là 1.0 → chọn -3.0
```

### 5.3 Lưu DB và build XML
```
DB:  lưu float/numeric (VD: -6.0, -3.0, 0.0, 3.0, 6.0)
XML: format string có "dB" suffix
     → f"{value:g}dB"  (loại bỏ trailing zero: 3.0 → "3dB", -6.0 → "-6dB")
     ĐÚNG:  <p name="dlRsBoost">-6dB</p>
     ĐÚNG:  <p name="dlRsBoost">-3dB</p>
     ĐÚNG:  <p name="dlRsBoost">0dB</p>
     ĐÚNG:  <p name="dlRsBoost">3dB</p>
     ĐÚNG:  <p name="dlRsBoost">6dB</p>
     SAI:   <p name="dlRsBoost">3.0dB</p>
     SAI:   <p name="dlRsBoost">3</p>

CASE-SENSITIVE — Nokia Managed Object tên tham số phân biệt hoa thường:
     ĐÚNG:  name="dlRsBoost"   (chữ R và B viết hoa)
     SAI:   name="dlrsboost"
     SAI:   name="DlRsBoost"
     SAI:   name="dlRsboost"

     ĐÚNG:  name="qrxlevmin"   (toàn bộ viết thường)
     SAI:   name="qrxLevMin"
     SAI:   name="QrxLevMin"
     SAI:   name="Qrxlevmin"
```

### 5.4 distName cho rsboost
```
cell_id từ CĐS: "PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y"
distName XML:   cell_id + "/LNCEL_FDD-0"
VD: "PLMN-PLMN/MRBTS-161313/LNBTS-161313/LNCEL-11/LNCEL_FDD-0"
```

---

## 6. QRXLEVMIN CALCULATION

### 6.1 Logic tính toán
```
qrxlevmin_new = qrxlevmin_current - 4

Floor: -144 dBm
  Nếu qrxlevmin_current - 4 < -144:
    → qrxlevmin_new = -144
    → log INFO: "Cell {cell_name} đã ở floor (-144dBm), bỏ qua"

Nếu qrxlevmin_current = -144:
    → không thay đổi
    → log INFO tương tự
```

### 6.2 Lưu DB và build XML
```
DB:  lưu integer (VD: -128, -132, -144)
XML: integer thuần, không có đơn vị
     ĐÚNG:  <p name="qrxlevmin">-128</p>
     SAI:   <p name="qrxlevmin">-128dBm</p>
```

### 6.3 distName cho qrxlevmin
```
cell_id từ CĐS: "PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y"
distName XML:   cell_id + "/SIB-0"
VD: "PLMN-PLMN/MRBTS-161313/LNBTS-161313/LNCEL-11/SIB-0"
```

---

## 7. NOKIA XML — BUILD RULES

### 7.1 File structure
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE raml SYSTEM 'raml20.dtd'>
<raml version="2.0" xmlns="raml20.xsd">
  <cmData type="plan" scope="all" name="{plan_name}">
    <header>
      <log dateTime="{GMT7_datetime_with_millisecond}" action="created" appInfo="PlanExporter">UIValues are used</log>
    </header>
    {managedObject blocks}
  </cmData>
</raml>
```

**ĐÃ SỬA (12/07/2026) theo bằng chứng file XML thật chạy thành công 08/07/2026** —
`dateTime` dùng format `GMT+7` có millisecond, VÍ DỤ: `2026-07-08T19:46:51.000+07:00`
(`%Y-%m-%dT%H:%M:%S.mmm+07:00`) — **KHÔNG dùng UTC "Z"** như bản gốc tài liệu này
ghi (`{UTC_ISO_datetime}`). Cùng dạng lệch tài liệu/thực tế đã gặp ở SHA-512 auth
(Section... xem API_CONTRACTS.md SS1) — ưu tiên bằng chứng file/API thật đã chạy
thành công hơn mô tả trong doc gốc.

Ngoài ra `cmData` trong file thật đã Import+Provision thành công CÓ thêm attribute
`id="PlanConfiguration( 8156 )"` — đã xác nhận đây là ID do PlanExporter tự gán
SAU KHI export lại 1 plan đã tồn tại (file mẫu là bản export lại, không phải input
gốc dùng để Import), KHÔNG phải input cần cung cấp. XmlBuilder chủ động KHÔNG đưa
attribute `id` vào `cmData` khi build (đồng nhất nguyên tắc "không id/version" ở
Section 7.3 dưới đây).

### 7.2 Plan naming
```
plan_name:   R012_NQMProactiveCC_{tram_id}_{YYYYMMDD_HHMMSS}
backup_name: R012_backup_{tram_id}_{YYYYMMDD_HHMMSS}
filename:    R012_NQMProactiveCC_{tram_id}_{YYYYMMDD_HHMMSS}.xml

Timestamp: UTC (nhất quán với timezone policy)
```

### 7.3 managedObject rules
```
KHÔNG có attribute "id"
KHÔNG có attribute "version"
operation = "update" (luôn là update — không phải create/delete)

Với mỗi cell có rsboost thay đổi:
  <managedObject class="LNCEL_FDD"
                 distName="{cell_id}/LNCEL_FDD-0"
                 operation="update">
    <p name="dlRsBoost">{value:g}dB</p>
  </managedObject>

Với mỗi cell có qrxlevmin thay đổi:
  <managedObject class="SIB"
                 distName="{cell_id}/SIB-0"
                 operation="update">
    <p name="qrxlevmin">{value}</p>
  </managedObject>

Thứ tự: rsboost objects trước, qrxlevmin objects sau (trong cùng 1 file)
```

### 7.4 Bao nhiêu file XML
```
1 file XML duy nhất chứa cả rsboost + qrxlevmin
→ 1 lần Import → 1 lần Provision
(không tách 2 file)
```

---

## 7b. ĐỊNH TUYẾN OSS (NetAct) — Giai đoạn 1 (chốt 27/09/2026)

### 7b.1 Quyết định

```
OSS phân trạm theo MÃ TỈNH CŨ (trước sáp nhập 2025) = 3 ký tự cuối TÊN CELL
chuẩn "4G-...-XXX". Khóa định tuyến = (mã_tỉnh_cũ, vendor).
1 tỉnh cũ + 1 vendor → dùng ĐÚNG 1 OSS.
CR sửa cell LÂN CẬN → chọn OSS theo TỪNG CELL, KHÔNG theo trạm bị tắt.
```

**KHÔNG dùng `tram_name`** (quy ước đặt tên riêng từng vendor/đội thi công,
đo thật: **13.038 trạm** không đúng mẫu `...-XXX`).

**KHÔNG dùng cột `tram.ma_tinh`** cho định tuyến (mã MỚI sau sáp nhập, lệch
37,8% so với ranh giới OSS đang chia theo địa giới CŨ) — cột này **CHỈ dùng
cho dashboard** (`GET /stations`), không liên quan định tuyến OSS.

**Nguồn xác nhận**: 456/456 cell trong `cr_affected_cells` (dữ liệu thật)
đúng mẫu `4G-...-XXX` — 100%, không có ngoại lệ.

### 7b.2 Vì sao đổi từ thiết kế cũ (chọn theo trạm tắt)

Thiết kế cũ: `IEnodebRepo.get_ma_tinh(tram_id)` đọc cột `tram.ma_tinh` của
**trạm bị tắt**, dùng 1 giá trị đó để chọn OSS cho **toàn bộ** cell lân cận
trong CR. Sai khi cell lân cận thuộc 1 trạm vật lý ở **tỉnh cũ khác** (giáp
ranh tỉnh) — XML bị gửi nhầm lên OSS không quản lý cell đó.

### 7b.3 Cơ chế — 1 CR = 1 XML = tối đa 1 OSS

```
Với MỖI cell trong Nhánh B (cells_chay_cr, đã qua filter_for_cr()):
  1. Suy ma_tinh_cu tu ten cell (domain/services/oss_routing.py) - khong
     dung mau -> LOAI, ly do TEN_CELL_SAI_MAU
  2. vendor = NOKIA neu cell_id la DN Nokia (he thong hien tai chi quan ly
     Nokia qua NetAct - moi cell khac vendor da bi loai o Nhanh A truoc do)
  3. IOssRouter.chon_oss(ma_tinh_cu, vendor) -> khong co route/credential
     con placeholder "???" -> LOAI, ly do OSS_CHUA_CAU_HINH
  4. Gom cell CON LAI theo OSS. > 1 OSS khac nhau trong cung 1 CR -> raise
     CR_NHIEU_OSS (422) - KHONG tu chon 1 OSS roi bo sot cell cua OSS kia.
```

Cell bị loại (`TEN_CELL_SAI_MAU`/`OSS_CHUA_CAU_HINH`) dùng CHUNG cơ chế báo
cáo với `CELL_ID_PHANG` (Section 2.2 ③, `cell_ngoai_pham_vi_chi_tiet` trong
`POST /cr/preview` — xem `API_CONTRACTS.md`) — cùng trả lời 1 câu hỏi "cell
này vì sao không nằm trong CR".

### 7b.4 Chốt 017 ("không suy tính từ tên") vẫn đúng — cho DASHBOARD

Chốt cũ (`domain/services/neighbor_cell_filter.py`, mục "cell ngoài phạm vi
CDS quản lý") nói: **KHÔNG** dùng hậu tố tên để LOẠI cell theo vendor (8/27.763
dòng cell_infor lệch hậu tố "-VPC" — ranh giới KHÔNG SẠCH cho câu hỏi
"cell này của vendor nào/CDS có quản lý không"). Chốt đó **VẪN ĐÚNG** và
**KHÔNG bị đảo lại** bởi quyết định 27/09/2026 — 2 chốt trả lời 2 câu hỏi
khác nhau:

| | Câu hỏi | Nguồn | Độ sạch đã đo |
|---|---|---|---|
| Chốt 017 (cũ) | Cell này CDS có quản lý không (vendor)? | `cell_id` (DN Nokia hay phẳng) | 8/27.763 lệch nếu suy từ hậu tố — KHÔNG dùng |
| Chốt mới (7b) | Cell này gửi SSH lên OSS nào (tỉnh cũ)? | Hậu tố TÊN CELL | 456/456 đúng mẫu — DÙNG |

### 7b.5 Cấu hình `.env`

```
NETACT_SERVERS={"instances": {"NA09": {host,user,password}, ...},
                "routes":    {"HNI|NOKIA": "NA09", "HGG|NOKIA": "NA14", ...}}
```
Định dạng CŨ (phẳng, `{"HNI": {host,user,password}}`) vẫn chạy đúng — hiểu
ngầm là route `"<khóa>|NOKIA" -> <khóa>` (xem `adapters/netact/oss_router_env.py`).

---

## 8. ĐÁNH GIÁ SAU CR (BR-05)

### 8.1 Thời điểm đánh giá
```
Sau 21 ngày kể từ ngày thực thi CR
n8n trigger POST /jobs/evaluate-cr mỗi ngày
BE check: cr_session nào đã đủ 21 ngày mà chưa evaluate → evaluate
```

### 8.2 Dữ liệu cần lấy
```
QoE (nguồn: SOC API):
  Before: 7 ngày trước ngày CR (T-7 → T-1)
  After:  7 ngày sau ngày CR   (T+1 → T+7)
  → 14 data points

QoS (nguồn: CTS API):
  Before: 7 ngày trước ngày CR (T-7 → T-1)
  After:  7 ngày sau ngày CR   (T+1 → T+7)
  → 14 data points

Tính average — công thức khi có missing day:
  avg = sum(các ngày có data) / số ngày thực tế có data
  (KHÔNG chia cho 7 cố định — chia cho số ngày thực tế)

  VD: 7 ngày before nhưng CTS chỉ trả 6 ngày:
      qoe_before = sum(6 ngày) / 6   ← ĐÚNG
      qoe_before = sum(6 ngày) / 7   ← SAI

Ngưỡng INSUFFICIENT_DATA:
  Nếu số ngày có data thực tế < 5 (trong khoảng 7 ngày):
    → đánh dấu INSUFFICIENT_DATA cho metric đó
    → retry ngày hôm sau
  Nếu >= 5 ngày có data → tính average bình thường
  Lý do: cho phép mất tối đa 2 ngày data mà không bị treo EVAL_PENDING
```

### 8.3 Kết quả đánh giá
```
SỬA (13072026, chốt với user): so sánh CÓ DUNG SAI -0.1, KHÔNG phải bất đẳng
thức tuyệt đối >= 0 như bản gốc bên dưới. Lý do: so sánh tuyệt đối (chỉ cần
giảm dù rất nhỏ, VD 0.01) sẽ bị false alarm từ nhiễu đo lường tự nhiên giữa
các ngày (dao động ngẫu nhiên của QoE/QoS không liên quan đến CR) — dung sai
-0.1 cho phép sụt giảm nhỏ trong biên độ nhiễu bình thường mà không báo FAIL.

SỬA (04092026, yêu cầu nghiệp vụ) — LUẬT HIỆN HÀNH. Bỏ hẳn vế "cứu" thêm ngày
16082026. Nay là **2 điều kiện ĐỘC LẬP**, vi phạm bất kỳ cái nào là KHÔNG ĐẠT:

  avg_after <  MUC_TOI_THIEU (3.0)  → KHÔNG ĐẠT  (ly_do = "DUOI_MUC_TOI_THIEU")
  tụt quá 0.5 điểm                  → KHÔNG ĐẠT  (ly_do = "TUT_QUA_NHIEU")
  còn lại                           → ĐẠT

Biên: tụt ĐÚNG 0.5 → ĐẠT. avg_after ĐÚNG 3.0 → ĐẠT.

Viết theo delta (SỬA 03/10/2026: delta = avg_before - avg_after, DƯƠNG khi
tụt, threshold DƯƠNG — đảo dấu so với bản trước để khớp chiều `do_te_cua()`
và quy ước báo cáo cho FE, tránh nhầm "giảm 2 lần dấu âm" khi đọc code):
  avg_after <  muc_toi_thieu   → FAIL   ← xét TRƯỚC, không phụ thuộc delta
  delta     >  threshold       → FAIL
  ngược lại                    → PASS
"tụt quá 0.5" ⟺ delta > 0.5. Tụt đúng 0.5 cho delta = 0.5, KHÔNG > 0.5 → PASS.

LỊCH SỬ (trước 03/10/2026): delta = avg_after - avg_before (ÂM khi tụt),
threshold ÂM, so sánh `delta < threshold`. Test cũ hardcode threshold âm (VD
-0.5) đã được đổi dấu đồng bộ - xem tests/domain/test_evaluation_service.py.

MUC_TOI_THIEU = 3.0 — ĐỔI TÊN VÀ ĐỔI VAI TRÒ so với MUC_TOT = 4.0 cũ:
  cũ: ngưỡng "vẫn còn tốt", vai trò CỨU cell tụt nhiều
  mới: ngưỡng "chất lượng tối thiểu", vai trò SÀN — dưới mức này là KHÔNG ĐẠT
       ngay, không liên quan gì tới delta
Đổi tên vì hằng số nay nói điều NGƯỢC LẠI với trước; giữ tên cũ sẽ làm người
đọc hiểu nhầm chiều so sánh.

Ngưỡng delta theo CẤP (2 hằng số ĐỘC LẬP, không gộp — giá trị TUYỆT ĐỐI
không đổi, CHỈ dấu đổi theo quy ước mới 03/10/2026):
  cấp CELL (xuất phiếu):   0.5   ← đổi 04092026 từ -0.2 (giá trị tuyệt đối 0.2→0.5)
    _XUAT_PHIEU_QOS_THRESHOLD_DELTA, _QOE_CELL_THRESHOLD_DELTA
  cấp SESSION (qos_result/qoe_result): 0.1  ← GIỮ NGUYÊN giá trị tuyệt đối
    PASS_THRESHOLD_DELTA
MUC_TOI_THIEU = 3.0 dùng CHUNG cho cả hai cấp (1 hằng số duy nhất).

MIN_DAYS_REQUIRED = 5 GIỮ NGUYÊN. Cách tính avg_before/avg_after GIỮ NGUYÊN
(trung bình các ngày thực tế có dữ liệu — xem §8.2).

2 trường THAM KHẢO kèm theo (KHÔNG dùng để phán quyết, chỉ để người vận hành
đối chiếu): diem_thap_nhat_sau = min(after), so_ngay_dat_sau = số ngày >= 3.0
(theo MUC_TOI_THIEU mới). Lý do: trung bình CHE được ngày mất dịch vụ — VD
[5,5,5,5,5,5,1] có avg 4.43 nên PASS nhưng có 1 ngày điểm 1.

--- LỊCH SỬ (KHÔNG còn hiệu lực, giữ để truy ngược) ---
Luật 16082026 → 04092026:
  delta >= threshold                       → PASS
  delta <  threshold VÀ avg_after >= 4.0   → PASS   ← vế CỨU, đã BỎ
  delta <  threshold VÀ avg_after <  4.0   → FAIL ("TUT_VA_CHAT_LUONG_KEM")
Ngưỡng cấp cell khi đó là -0.2.
Vế "cứu" bị bỏ vì: cell tụt 1.0 điểm từ 5.0 xuống 4.0 vẫn được coi là đạt, trong
khi mức tụt đó đã là dấu hiệu CR gây ảnh hưởng thật.

KHÔNG thêm tiêu chí "đếm số ngày đạt >= 4/7" — THỪA VỀ TOÁN HỌC (chứng minh
với MUC_TOT=4.0 cũ: thang 1-5, 7 ngày, k = số ngày >= 4 thì sum <= 2k + 21; mà
avg >= 4 ⟺ sum >= 28 ⟹ k >= 4). Với MUC_TOI_THIEU = 3.0 phép chứng minh này
KHÔNG còn áp dụng nguyên văn, nhưng tiêu chí đếm ngày vẫn không được thêm vào.

LƯU Ý HỒI TỐ: luật CŨ chỉ xét delta nên hệ thống ĐÃ TỪNG đánh FAIL cho cell lẽ
ra PASS theo luật mới → có thể đã xuất phiếu THỪA. Xem docs/DEV_LOG.md mục
[VE avg_after >= 4].

2 kết quả hoàn toàn độc lập (áp dụng riêng cho từng chỉ số, KHÔNG gộp
QoE+QoS thành 1 kết quả chung):
  cr_session.qoe_result = "PASS" | "FAIL" | "INSUFFICIENT_DATA"
  cr_session.qos_result = "PASS" | "FAIL" | "INSUFFICIENT_DATA"

Bản gốc (THAM KHẢO LỊCH SỬ — KHÔNG dùng lại, xem quyết định sửa ở trên):
  QoE stable: qoe_after  >= qoe_before   → PASS
  QoE degraded: qoe_after < qoe_before   → FAIL → ghi alert_log
  QoS stable: qos_after  >= qos_before   → PASS
  QoS degraded: qos_after < qos_before   → FAIL → ghi alert_log
```

### 8.4 Dữ liệu chưa đủ
```
Ngưỡng: cần >= 5 ngày có data trong khoảng 7 ngày (before hoặc after)
  < 5 ngày → INSUFFICIENT_DATA → retry ngày hôm sau
  >= 5 ngày → tính average bình thường (chia cho số ngày thực tế có data)

Xử lý:
  → cr_session.qoe_result = "INSUFFICIENT_DATA" (hoặc qos_result)
  → cr_session.status = "EVAL_PENDING"
  → Không coi là lỗi — n8n trigger lại ngày hôm sau
  → Log INFO kèm: session_id, số ngày có data, số ngày cần thêm

Trường hợp đặc biệt:
  Nếu EVAL_PENDING > 30 ngày → log WARNING, notify admin
  (có thể SOC/CTS đang có vấn đề dài hạn)
```

### 8.44 Chọn SESSION để quét xuất phiếu — CỬA SỔ QUÉT BÙ (sửa 03/10/2026)

**Vấn đề thật**: luật cũ chọn session theo đúng 1 ngày mốc duy nhất
(`ngay_cr == hôm_nay - XUAT_PHIEU_AFTER_DAYS`, so khớp CHÍNH XÁC, không phải
khoảng) — nếu job bỏ lỡ chạy đúng ngày đó (lỗi hạ tầng, bảo trì...), session
rơi vào khoảng ngày đã trôi qua sẽ KHÔNG BAO GIỜ được quét lại, vĩnh viễn mất
cơ hội xuất phiếu. Ca thật: session 7296 (phát hiện 03/10/2026).

**Sửa**: quét theo CỬA SỔ, không phải 1 ngày đơn:
```
ngay_moc = hôm_nay - XUAT_PHIEU_AFTER_DAYS          (mặc định 8 ngày)
cua_so_duoi = ngay_moc - XUAT_PHIEU_QUET_BU_NGAY    (mặc định 14 ngày)

Điều kiện quét 1 session:
  cua_so_duoi <= ngày(executed_at) <= ngay_moc
  AND executed_at IS NOT NULL
  AND xuat_phieu_at IS NULL     ← chống quét lại (idempotent)

Hằng số (.env, có default trong code):
  XUAT_PHIEU_AFTER_DAYS    = 8   (giữ nguyên)
  XUAT_PHIEU_QUET_BU_NGAY  = 14  (MỚI 03/10/2026)
```

**Idempotent**: `cr_session.xuat_phieu_at` được ghi KHÔNG ĐIỀU KIỆN ở cuối xử
lý mỗi session (dù kết quả là `DA_XUAT`/`KHONG_CAN_XUAT`/`LOI`) — điều kiện
`xuat_phieu_at IS NULL` đảm bảo 1 session chỉ được quét đúng 1 lần dù nằm
trong cửa sổ bao nhiêu ngày liên tiếp, giống hệt tác dụng của so khớp CHÍNH
XÁC 1 ngày trước đây (session chỉ "đúng ngày mốc" đúng 1 lần trong đời), chỉ
khác là giờ có THÊM cơ hội bắt kịp nếu job từng bỏ lỡ.

Code: `application/xuat_phieu_use_case.py::_lay_session_du_dieu_kien()`.

### 8.45 Chọn cell xuất phiếu — TRẦN + LUẬT XẾP HẠNG (sửa 04/10/2026, TRẦN THEO SECTOR)

**Trần: 2 phiếu / SECTOR của tram tắt / lượt chạy** (SỬA 04/10/2026, THAY THẾ
hoàn toàn trần theo SESSION cũ — trước đó là 6/session, 09/2026; 10/session
trước nữa).

```
Hằng số: XUAT_PHIEU_MAX_PER_SECTOR
  đọc từ .env, default trong code = 2
  application/xuat_phieu_use_case.py

TẠI SAO đổi đơn vị tính TỪ session SANG sector: 1 session có thể ảnh hưởng
NHIỀU sector độc lập nhau (trạm 4 sector = 4 hướng vật lý khác nhau). Trần
theo session cũ (6/session dù có bao nhiêu sector) để 1 sector ít cell "ăn
hết suất" của sector khác đang còn nhiều cell tệ hơn chờ xử lý — không công
bằng giữa các sector. Trần theo sector: MỖI sector độc lập được tối đa 2
phiếu — trạm 4 sector tối đa 2×4 = 8 phiếu/lượt chạy.

Sector CỦA 1 CELL = sector của TRẠM TẮT (suy từ huong_id%10 qua tên hướng,
_extract_huong_id_from_name() - xem domain/services/neighbor_cell_filter.py),
lưu SẴN trên cr_affected_cells.sector lúc trigger CR (KHÔNG tính lại ở bước
xuất phiếu). Cell là neighbor của NHIỀU hướng (có thể khác sector) → giữ
sector NHỎ NHẤT (quyết định 04/10/2026).

sector = NULL (CDS không suy được huong_id từ cả field lẫn tên) → gộp thành
1 "sector" RIÊNG, CHỊU CÙNG trần như sector số thực - KHÔNG được miễn trần.

Cell vượt trần (CỦA SECTOR nó thuộc về) → KHÔNG xuất tự động, nhưng VẪN ghi
1 dòng cr_phieu trạng thái KHONG_XUAT_VUOT_GIOI_HAN để người vận hành lọc ra
xử lý tay. Cell ngoài trần nằm ngoài VĨNH VIỄN (độ tệ không đổi giữa các lượt
vì cửa sổ T+1..T+7 cố định) → job không bao giờ tự xuất chúng ở lượt sau.

Thứ tự cắt trần: sort TOÀN BỘ ứng viên của session theo khóa ưu tiên (bên
dưới) TRƯỚC, rồi duyệt theo đúng thứ tự đó, đếm RIÊNG cho từng sector - ứng
viên thứ (N+1) CỦA SECTOR ĐÓ mới bị đẩy sang vượt trần (không phải thứ N+1
của toàn session). Thực hiện 1 LẦN DUY NHẤT trong
_danh_gia_va_xep_hang() (dùng chung job tự động + API xem trước) - tránh 2
nơi tự cắt trần lệch nhau.
```
> ⚠️ `.env` bị `.gitignore` — đổi default trong code **KHÔNG** đổi trần trên
> server. Phải sửa tay `.env` của `.196` khi deploy.

**Luật xếp hạng — khóa 2 tầng, sort TĂNG DẦN:**
```
khoa = (nhom, -do_giam, avg_after_min)

  nhom          = 0 nếu min(avg_after QoS, QoE) < MUC_TOI_THIEU (3.0)
                  = 1 nếu ngược lại
                  → nhóm 0 (dưới sàn) LUÔN đứng trước nhóm 1
  do_giam       = max(0, avg_before - avg_after), lấy MAX giữa QoS và QoE
                  → trong mỗi nhóm, giảm càng nhiều càng ưu tiên
  avg_after_min = phá hòa: điểm còn lại càng thấp càng ưu tiên

Chỉ số THIẾU DỮ LIỆU (không có QoE, hoặc < 5 ngày → INSUFFICIENT_DATA)
→ BỎ QUA chỉ số đó, KHÔNG coi là 0 điểm.
  Coi là 0 sẽ đẩy cell "không đo được" lên đầu danh sách ưu tiên.
  Cell chỉ còn 1 chỉ số → xếp hạng bằng đúng chỉ số đó.

Code: domain/services/evaluation_service.py::khoa_uu_tien_xuat_phieu()
```

**Vì sao thay `do_te = max(mức_tụt, mức_thiếu)`:** công thức cũ gộp "dưới sàn"
và "tụt nhiều" vào MỘT con số nên làm mất tầng ưu tiên thứ nhất. Ca thật,
session 4884 (đo 09/2026):

| Cell | QoS b→a | QoE b→a | do_te cũ | Hạng cũ |
|---|---|---|---|---|
| `4G-HKM022M43-HNI` | 4.29→4.00 | **2.71→2.83** (dưới sàn) | 0.286 | 13/13 → **bị cắt** |
| `4G-HKM022M13-HNI` | 4.57→4.80 | 4.57→3.17 (trên sàn) | 1.405 | 1/13 → được xuất |

Cell **duy nhất** đang dưới mức tối thiểu lại là cell bị cắt đầu tiên, vì
`mức_thiếu` của nó chỉ `3.00 − 2.83 = 0.17`. Khóa 2 tầng sửa đúng chỗ đó.

`do_te` VẪN được tính và báo cáo (`job_run_log.chi_tiet`, API xem trước, FE)
nhưng KHÔNG còn quyết định thứ tự — `chi_tiet` ghi thêm `nhom` + `do_giam` để
đọc log giải thích được thứ tự.

### 8.46 PhuongAnXuLyDuKien (payload CTS) — SỬA 04/10/2026 (theo NGUYÊN NHÂN)

**Trước 04/10/2026**: hằng số CỨNG `"2"` cho MỌI phiếu (V5, 12/08) — không
phân biệt được "cell dưới sàn chất lượng tối thiểu" với "cell chỉ tụt nhiều
nhưng vẫn còn trên sàn".

**Sửa (chốt với user 04/10/2026)** — giá trị PHỤ THUỘC "nhóm" của cell, dùng
LẠI đúng định nghĩa `nhom` của `khoa_uu_tien_xuat_phieu()` (Section 8.45),
KHÔNG viết công thức so sánh 3.0/0.5 lần thứ 2:

```
"2"  nếu QoS HOẶC QoE có điểm TB sau < 3.0 (dưới sàn)  ⟺ nhom == 0
     - KE CA khi đồng thời tụt > 0.5 (dưới sàn LUÔN nặng hơn, bất kể tụt bao
       nhiêu — giống hệt lý do nhom 0 luôn đứng trước nhom 1 ở Section 8.45)
"1"  nếu CẢ 2 chỉ số (hoặc chỉ số DUY NHẤT còn lại, khi 1 bên thiếu dữ liệu)
     đều >= 3.0 NHƯNG chênh lệch (trước − sau) > 0.5             ⟺ nhom == 1
```

Chỉ số thiếu dữ liệu: `khoa_uu_tien_xuat_phieu()` tự bỏ qua chỉ số đó (không
coi là 0 điểm — xem `_ket_luan_duoc()`), xét chỉ số còn lại. Cell thiếu CẢ
HAI không bao giờ tới được bước này (đã bị chặn ở các nhánh `INSUFFICIENT_DATA`
phía trên, giữ nguyên hành vi cũ — không xuất phiếu).

**Áp dụng CHO CẢ 2 đường xuất phiếu** (job tự động + nút "Xuất" 1 cell,
`POST /phieu`): cả 2 đường đều gọi chung `XuatPhieuUseCase.execute()` — tính
1 LẦN DUY NHẤT tại đó, không có bản sao logic thứ 2 cho đường xuất tay.

Giá trị gửi CTS vẫn là CHUỖI chứa số (`"1"`/`"2"`), giống mọi field "số" khác
trong payload (CTS khai Int32/Number nhưng từ chối 400 nếu gửi kiểu Number
thật — xem `SoChiTieuVP`/`Qos`/`Qoe` cùng payload).

Phiếu đã gửi TRƯỚC 04/10/2026 (mang giá trị "2" cứng cũ): KHÔNG hồi tố/sửa lại
— quyết định này chỉ áp dụng cho phiếu MỚI từ thời điểm sửa.

Code: `application/xuat_phieu_use_case.py::execute()` (ngay trước khi ghép
payload), tái dùng `domain/services/evaluation_service.py::khoa_uu_tien_xuat_phieu()`.

### 8.5 Chart display (FE — Zone E)
```
Hiển thị 10 điểm trên chart:
  T-2, T-1  (2 ngày trước CR)
  T+0       (ngày CR — highlight màu amber/orange)
  T+1 → T+7 (7 ngày sau CR)

Trục X: ngày
Trục Y: QoE hoặc QoS (scale 1-5)
2 chart riêng: QoE (nguồn SOC) + QoS (nguồn CTS)
```

---

## 9. WIDGET F33 — QoS SPARKLINE (THAM KHẢO)

```
Mục đích: xem nhanh QoS cell lân cận TRƯỚC khi trigger CR (tham khảo)
Không tham gia vào logic pass/fail của BR-05

Data: 48 điểm theo giờ (2 ngày gần nhất)
Nguồn: CTS API (granularity="day" nhưng response trả hourly)
Cell: các cell lân cận của trạm đang chọn trong Zone A

Hiển thị: sparkline nhỏ trong Zone A/F33
          mỗi cell 1 sparkline
          không có title phức tạp — chỉ xem trend
```

---

## 10. SYNC JOBS (BACKGROUND)

### 10.1 sync-rims (sync eNodeB → bảng tram)
```
Nguồn: eNodeB List API (10.156.10.119:8080)
Đích:  bảng tram
Logic:
  - Fetch tất cả pages (pageSize=1000, ~5822 trang)
  - Upsert vào bảng tram (on conflict tram_id → update)
  - Handle anomaly: longitude=0, latitude=0, ma_tinh=None → lưu null, không crash
  - Log tổng số records synced + thời gian
Chạy từ: server 10.155.43.196 (IP whitelist)
Tần suất: 1 lần/ngày (n8n schedule)
```

### 10.2 sync-netact (sync cell params từ NetAct)
```
Nguồn: NetAct (SSH export hoặc API — cần xác nhận method)
Đích:  bảng cell_params (rsboost_current, qrxlevmin_current)
Logic:
  - Lấy giá trị hiện tại của tất cả cell
  - Upsert vào cell_params theo cell_name/dist_name_base
  - Parse "3dB" → 3.0 (rsboost), "-128" → -128 (qrxlevmin)
Tần suất: 1 lần/ngày
```

### 10.3 sync-status (sync tram active/inactive)
```
Nguồn: CĐS hoặc NetAct (xác nhận sau)
Đích:  bảng tram (field trang_thai)
Logic: update trang_thai = active/inactive/relocating
Tần suất: 1 lần/ngày
```

---

## 11. STATE MACHINE — CR SESSION

```
                    ┌─────────┐
                    │ PENDING │  ← vừa tạo session
                    └────┬────┘
                         │ bắt đầu xử lý
                    ┌────▼────┐
                    │ RUNNING │  ← đang chạy 18 bước
                    └────┬────┘
              ┌──────────┴──────────┐
              │ success             │ failed
         ┌────▼────┐          ┌─────▼─────┐
         │  DONE   │          │  FAILED   │
         └────┬────┘          └───────────┘
              │ sau 21 ngày
         ┌────▼──────┐
         │ EVALUATING│  ← n8n trigger evaluate job
         └────┬──────┘
    ┌─────────┴─────────┐
    │ đủ data           │ chưa đủ data
┌───▼──────┐      ┌─────▼──────────┐
│ EVALUATED│      │ EVAL_PENDING   │  ← retry ngày hôm sau
└──────────┘      └────────────────┘
```

```
cr_session.status values:
  PENDING     → vừa tạo
  RUNNING     → đang chạy
  DONE        → 18 bước hoàn thành
  FAILED      → có bước thất bại
  EVALUATING  → đang lấy QoE/QoS data
  EVALUATED   → đã có kết quả pass/fail
  EVAL_PENDING → chờ đủ data để evaluate
```

---

## 12. AUDIT LOG — EVENTS CẦN GHI

```
Bắt buộc ghi audit_log cho:
  CR_TRIGGER        khi user trigger CR (actor=user, target=tram)
  CR_XML_BUILD      khi build XML xong (actor=system)
  CR_SSH_IMPORT     khi Import plan xong (actor=system)
  CR_SSH_PROVISION  khi Provision xong (actor=system)
  CR_EVALUATE       khi evaluate xong (actor=system)
  SYNC_ENODEB       khi sync-rims job xong (actor=n8n)
  SYNC_CELL_PARAMS  khi sync-netact job xong (actor=n8n)
  CONFIG_UPDATE     khi admin thay đổi system_config (actor=user)
```

---

## 13. EDGE CASES — TỔNG HỢP

| Case | Xử lý | Log level |
|------|--------|-----------|
| huong_id = null | Bỏ qua hướng | WARNING |
| cell_id = null | Bỏ qua cell | WARNING |
| cell prefix "VNP-" | Bỏ qua cell | WARNING |
| Duplicate huong_id | Giữ first, bỏ rest | WARNING |
| Duplicate cell cross-direction | rsboost wins | INFO |
| Cell count < 4/hướng | Xử lý đủ cell có | INFO |
| rsboost ở cap (6dB) | Không đổi | INFO |
| qrxlevmin ở floor (-144) | Không đổi | INFO |
| rsboost value không trong scale | Làm tròn bậc gần nhất (min abs distance, tie→thấp hơn) | WARNING |
| CTS missing day | Bình thường, không error, tính avg trên số ngày có data | DEBUG |
| QoE/QoS data < 5/7 ngày | INSUFFICIENT_DATA, retry | INFO |
| EVAL_PENDING > 30 ngày | Notify admin | WARNING |
| Trạm đang RUNNING | Từ chối trigger mới | 409 |
| Trạm đã có CR DONE | Từ chối trigger shutdown/relocate lần 2 | 409 |
| action=cancel không có DONE trước | Từ chối rollback | ERROR |
| rsboost_before_cr = null | Từ chối rollback, notify admin | ERROR |