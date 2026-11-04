"""
DashboardRepo - implement IDashboardRepo (GET /dashboard/*).
Tu: yeu cau truc tiep user 18/10/2026 (muc 4 - API dashboard; DOT 2 - vendor,
chi tiet theo card, xu huong theo ngay/tuan).

=== VI SAO SQL THO (text) THAY VI ORM ===
Can GROUPING SETS + COUNT FILTER + CTE nhieu tang - viet bang SQLAlchemy Core
dai gap 3 va kho doi chieu voi cau SQL do tay tren DB. 1 cau query cho TOAN BO
so lieu tong/nhom/moc: 1 round-trip, khong N+1 theo session.

=== MOT CTE DANH GIA CELL DUNG CHUNG ===
_CTE_CELL (danh gia tung cell anh huong x QoS/QoE) dung CHUNG cho tong_hop() va
chi_tiet() - so dong chi tiet khong loc con LUON bang so tren card tong quan.

=== HAU KIEM TINH TU SNAPSHOT DB ===
Diem QoS/QoE lay tu qos_snapshot/qoe_snapshot (period before/after) - nguon
DUY NHAT trong DB. Session/cell chua co snapshot -> THIEU_DU_LIEU o day.
Chap nhan: dashboard khong duoc goi API ngoai cho hang tram session.

Luat danh gia la BAN SQL cua EvaluationService.evaluate() (THU TU xet giong
het: thieu ngay -> duoi san -> lech). Nguong truyen tu application, test
tests/integration/test_dashboard_repo.py doi chieu ket qua SQL voi ham Python.

LAM TRON (SUA 18/10/2026, xem evaluation_service.py::LAM_TRON_SO_THAP_PHAN):
TB = ROUND(avg, 2), Lech = ROUND(avg truoc - avg sau, 2) (avg THO) TRUOC khi so
nguong - CUNG cong thuc ham Python. avg tren NUMERIC (chinh xac); voi diem
nguyen 1-5 va 5-7 ngay, TB/Lech tho khong bao gio roi dung .xx5 nen ROUND
numeric va round() float cua Python ra cung so.

=== VENDOR (DOT 2) ===
Chi so CR theo vendor TRAM TAT; hau kiem + phieu theo vendor CUA CELL (tram
cua cell qua cr_affected_cells.tram_id). Vi vay so lieu duoc trai thanh bang
"fact" 1 dong / (session, vendor): dong CR (la_cr=1) mang vendor tram tat,
dong hau kiem/phieu mang vendor cell - GROUPING SETS (vendor) tu dung dung
vendor cho tung loai chi so. Cell khong ghep duoc tram -> 'UNKNOWN'.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import COT_SAP_XEP_DASHBOARD, BoLocDashboard, IDashboardRepo
from domain.services.bo_dau import CO_DAU, KHONG_DAU
from domain.value_objects.khu_vuc import KV1, KV2, KV3, khu_vuc_tu_ma_tinh, ma_tinh_theo_khu_vuc
from domain.value_objects.ten_tinh import TEN_TINH_THEO_MA, ten_tinh_tu_ma
from domain.value_objects.trang_thai_phieu import TRANG_THAI_CHO_XUAT_TAY

# Ten schema ghi thang trong SQL - GIONG cell_infor_repo.py (raw SQL khong di
# qua SQLModel.metadata.schema nen khong tu gan schema nhu ORM).
_S = "system_nsn_nqmproactivecc"

# Chuan hoa vendor GIONG enodeb_repo.find_stations() (UPPER(TRIM)); NULL ->
# 'UNKNOWN' de khong bien mat khoi nhom vendor (xem domain/value_objects/vendor.py).
_VENDOR = "coalesce(upper(trim({col})), 'UNKNOWN')"

# Session theo NGAY GMT+7 cua created_at (Lich su CR cung loc created_at) +
# tinh tram tat. CHUA loc vendor o day: vendor ap khac nhau cho tung loai chi so.
_LOC_SESSION = f"""
    SELECT cs.id, cs.tram_id, cs.status, cs.oss_instance_id AS netact, t.ma_tinh,
           t.tram_name, cs.executed_at, cs.xuat_phieu_at, cs.ma_loi, cs.created_at,
           {_VENDOR.format(col="t.ten_thiet_bi")} AS vendor_tram,
           date_trunc(:don_vi, timezone('Asia/Ho_Chi_Minh', cs.created_at))::date AS moc
    FROM {_S}.cr_session cs
    LEFT JOIN {_S}.tram t ON t.tram_id = cs.tram_id
    WHERE timezone('Asia/Ho_Chi_Minh', cs.created_at)::date BETWEEN :tu_ngay AND :den_ngay
      AND (CAST(:ma_tinh AS varchar[]) IS NULL OR t.ma_tinh = ANY(CAST(:ma_tinh AS varchar[])))
"""

_LOC_VENDOR = "(CAST(:vendor AS varchar[]) IS NULL OR {col} = ANY(CAST(:vendor AS varchar[])))"

# Danh gia tung cell anh huong x 2 chi so. LEFT JOIN diem: cell khong co
# snapshot van co dong (THIEU) - giong bang hau kiem giu dong cell thieu.
_CTE_CELL = f"""
diem AS (
    SELECT 'QOS' AS chi_so, cr_session_id, cell_name, period,
           count(*) AS n, avg(qos_score) AS tb
    FROM {_S}.qos_snapshot
    WHERE period IN ('before', 'after') AND qos_score IS NOT NULL
      AND cr_session_id IN (SELECT id FROM s)
    GROUP BY cr_session_id, cell_name, period
    UNION ALL
    SELECT 'QOE', cr_session_id, cell_name, period, count(*), avg(qoe_score)
    FROM {_S}.qoe_snapshot
    WHERE period IN ('before', 'after') AND qoe_score IS NOT NULL
      AND cr_session_id IN (SELECT id FROM s)
    GROUP BY cr_session_id, cell_name, period
),
cell AS (
    SELECT a.cr_session_id, a.cell_name, c.chi_so,
        {_VENDOR.format(col="tc.ten_thiet_bi")} AS vendor_cell,
        coalesce(b.n, 0) AS n_truoc, coalesce(f.n, 0) AS n_sau,
        round(b.tb, 2) AS tb_truoc, round(f.tb, 2) AS tb_sau,
        round(b.tb - f.tb, 2) AS lech,
        CASE
            WHEN coalesce(b.n, 0) < :min_ngay OR coalesce(f.n, 0) < :min_ngay THEN 'THIEU'
            WHEN round(f.tb, 2) < CAST(:muc_toi_thieu AS numeric) THEN 'KD_SAN'
            WHEN round(b.tb - f.tb, 2) > CASE c.chi_so WHEN 'QOS' THEN CAST(:lech_qos AS numeric)
                                              ELSE CAST(:lech_qoe AS numeric) END
                THEN 'KD_LECH'
            ELSE 'DAT'
        END AS kq
    FROM {_S}.cr_affected_cells a
    CROSS JOIN (VALUES ('QOS'), ('QOE')) AS c(chi_so)
    LEFT JOIN {_S}.tram tc ON tc.tram_id = a.tram_id
    LEFT JOIN diem b ON b.cr_session_id = a.cr_session_id AND b.cell_name = a.cell_name
                    AND b.chi_so = c.chi_so AND b.period = 'before'
    LEFT JOIN diem f ON f.cr_session_id = a.cr_session_id AND f.cell_name = a.cell_name
                    AND f.chi_so = c.chi_so AND f.period = 'after'
    WHERE a.cr_session_id IN (SELECT id FROM s)
)"""

# Phieu + vendor CUA CELL (ghep cr_affected_cells cung session/cell). deleted_at
# IS NULL: giong sq_da_xuat/sq_cho_xuat_tay cua CrSessionRepo.list().
# PhuongAnXuLyDuKien chi co trong request_payload: "1" He thong, "2" Hien truong.
_CTE_PHIEU = f"""
phieu AS (
    SELECT p.id, p.cr_session_id, p.cell_name, p.trang_thai, p.phieu_id, p.created_at,
           p.request_payload->>'PhuongAnXuLyDuKien' AS phuong_an,
           {_VENDOR.format(col="tp.ten_thiet_bi")} AS vendor_cell
    FROM {_S}.cr_phieu p
    LEFT JOIN {_S}.cr_affected_cells ap ON ap.cr_session_id = p.cr_session_id
                                       AND ap.cell_name = p.cell_name
    LEFT JOIN {_S}.tram tp ON tp.tram_id = ap.tram_id
    WHERE p.deleted_at IS NULL AND p.cr_session_id IN (SELECT id FROM s)
)"""

_SQL_TONG_HOP = f"""
WITH s AS ({_LOC_SESSION}),
{_CTE_CELL},
{_CTE_PHIEU},
cp AS (
    SELECT cr_session_id, count(*) AS n FROM {_S}.cell_params
    WHERE cr_session_id IN (SELECT id FROM s) GROUP BY cr_session_id
),
-- Bang fact 1 dong / (session, vendor) - xem "VENDOR" dau file. Gop ve muc
-- (session, vendor) TRUOC khi GROUPING SETS: join thang cac bang con vao nhau
-- se nhan cheo (tich Descartes) va dem sai.
fact AS (
    SELECT s.id, s.vendor_tram AS vendor, 1 AS la_cr, coalesce(cp.n, 0) AS n_cp,
           0 AS qos_tong, 0 AS qos_dat, 0 AS qos_kd_san, 0 AS qos_kd_lech, 0 AS qos_thieu,
           0 AS qoe_tong, 0 AS qoe_dat, 0 AS qoe_kd_san, 0 AS qoe_kd_lech, 0 AS qoe_thieu,
           0 AS phieu_he_thong, 0 AS phieu_hien_truong, 0 AS phieu_success,
           0 AS phieu_cho_xuat_tay, 0 AS phieu_loi
    FROM s LEFT JOIN cp ON cp.cr_session_id = s.id
    UNION ALL
    SELECT cr_session_id, vendor_cell, 0, 0,
        count(*) FILTER (WHERE chi_so = 'QOS'),
        count(*) FILTER (WHERE chi_so = 'QOS' AND kq = 'DAT'),
        count(*) FILTER (WHERE chi_so = 'QOS' AND kq = 'KD_SAN'),
        count(*) FILTER (WHERE chi_so = 'QOS' AND kq = 'KD_LECH'),
        count(*) FILTER (WHERE chi_so = 'QOS' AND kq = 'THIEU'),
        count(*) FILTER (WHERE chi_so = 'QOE'),
        count(*) FILTER (WHERE chi_so = 'QOE' AND kq = 'DAT'),
        count(*) FILTER (WHERE chi_so = 'QOE' AND kq = 'KD_SAN'),
        count(*) FILTER (WHERE chi_so = 'QOE' AND kq = 'KD_LECH'),
        count(*) FILTER (WHERE chi_so = 'QOE' AND kq = 'THIEU'),
        0, 0, 0, 0, 0
    FROM cell GROUP BY cr_session_id, vendor_cell
    UNION ALL
    SELECT cr_session_id, vendor_cell, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        count(*) FILTER (WHERE trang_thai = 'SUCCESS' AND phuong_an = '1'),
        count(*) FILTER (WHERE trang_thai = 'SUCCESS' AND phuong_an = '2'),
        count(*) FILTER (WHERE trang_thai = 'SUCCESS'),
        count(*) FILTER (WHERE trang_thai = ANY(CAST(:cho_xuat_tay AS varchar[]))),
        count(*) FILTER (WHERE trang_thai = 'FAILED')
    FROM phieu GROUP BY cr_session_id, vendor_cell
),
f AS (
    SELECT fact.*, s.tram_id, s.status, s.ma_tinh, s.moc
    FROM fact JOIN s ON s.id = fact.id
    WHERE {_LOC_VENDOR.format(col="fact.vendor")}
)
SELECT
    CASE WHEN GROUPING(ma_tinh) = 0 THEN 'ma_tinh'
         WHEN GROUPING(vendor) = 0 THEN 'vendor'
         WHEN GROUPING(moc) = 0 THEN 'moc'
         ELSE 'tong' END AS nhom,
    coalesce(ma_tinh, vendor, moc::text) AS gia_tri,
    count(*) FILTER (WHERE la_cr = 1) AS so_session,
    count(*) FILTER (WHERE la_cr = 1 AND status = 'DONE') AS done,
    count(*) FILTER (WHERE la_cr = 1 AND status = 'PARTIAL_SUCCESS') AS partial_success,
    count(*) FILTER (WHERE la_cr = 1 AND status = 'KHONG_CHAY') AS khong_chay,
    count(*) FILTER (WHERE la_cr = 1 AND status = 'FAILED') AS failed,
    count(*) FILTER (WHERE la_cr = 1 AND status IN ('PENDING', 'RUNNING')) AS dang_chay,
    count(DISTINCT tram_id) FILTER (WHERE la_cr = 1) AS so_tram,
    sum(n_cp) AS so_cell_cr,
    sum(qos_tong) AS qos_tong, sum(qos_dat) AS qos_dat, sum(qos_kd_san) AS qos_kd_san,
    sum(qos_kd_lech) AS qos_kd_lech, sum(qos_thieu) AS qos_thieu,
    sum(qoe_tong) AS qoe_tong, sum(qoe_dat) AS qoe_dat, sum(qoe_kd_san) AS qoe_kd_san,
    sum(qoe_kd_lech) AS qoe_kd_lech, sum(qoe_thieu) AS qoe_thieu,
    sum(phieu_he_thong) AS phieu_he_thong, sum(phieu_hien_truong) AS phieu_hien_truong,
    sum(phieu_success) AS phieu_success, sum(phieu_cho_xuat_tay) AS phieu_cho_xuat_tay,
    sum(phieu_loi) AS phieu_loi
FROM f
GROUP BY GROUPING SETS ((), (ma_tinh), (vendor), (moc))
"""

# Qua han: GIONG HET dieu kien qua_han cua CrSessionRepo.list() (Lich su CR
# ?qua_han=true) - 2 noi dem khac nhau la nguoi dung thay 2 con so mau thuan.
# Vendor = vendor tram tat (chi so CR).
_DIEU_KIEN_QUA_HAN = """xuat_phieu_at IS NULL AND executed_at IS NOT NULL
  AND timezone('Asia/Ho_Chi_Minh', executed_at)::date < :qua_han_truoc_ngay"""

_SQL_QUA_HAN = f"""
WITH s AS ({_LOC_SESSION})
SELECT id, tram_id, tram_name, status,
       timezone('Asia/Ho_Chi_Minh', executed_at)::date AS ngay_cr
FROM s
WHERE {_DIEU_KIEN_QUA_HAN} AND {_LOC_VENDOR.format(col="vendor_tram")}
ORDER BY executed_at
"""

_SQL_KHONG_CHAY = f"""
WITH s AS ({_LOC_SESSION})
SELECT id, tram_id, tram_name, ma_loi, created_at FROM s
WHERE status = 'KHONG_CHAY' AND {_LOC_VENDOR.format(col="vendor_tram")}
ORDER BY created_at DESC
"""

# === CHI TIET THEO CARD (DOT 2 + tim/sap xep 18/10/2026) ===
# Moi loai 1 cau GOC (chi chon cot + loc con), roi BOC chung 1 lop ngoai
# (_boc_chi_tiet) lo tim kiem + sap xep + phan trang - 4 loai dung CUNG 1 cach,
# va tim/sap xep chay tren TEN COT DA RA (vd ma_phieu la string_agg) nen khong
# phai lap lai bieu thuc. count(*) OVER () = tong so dong SAU loc + tim, TRUOC
# LIMIT, trong cung 1 query. Tham so loc con NULL = khong loc; limit NULL = lay
# het (xuat Excel).

# Map kq noi bo SQL -> ket_qua/ly_do cong khai cua API (giong ten MetricEvaluation).
_KET_QUA = "CASE c.kq WHEN 'DAT' THEN 'DAT' WHEN 'THIEU' THEN 'INSUFFICIENT_DATA' ELSE 'KHONG_DAT' END"
_LY_DO = "CASE c.kq WHEN 'KD_SAN' THEN 'duoi_muc' WHEN 'KD_LECH' THEN 'tut' END"

_SQL_GOC = {
    "cr": f"""
WITH s AS ({_LOC_SESSION}),
-- Danh muc tinh (ma -> ten, KV) dung tu hang so Python (xem _danh_muc_tinh())
-- de JOIN va SAP XEP o SQL theo ten_tinh/khu_vuc.
dm AS (
    SELECT * FROM unnest(CAST(:dm_ma AS varchar[]), CAST(:dm_ten AS varchar[]),
                         CAST(:dm_kv AS varchar[])) AS dm(ma, ten_tinh, khu_vuc)
)
SELECT s.id AS session_id,
       timezone('Asia/Ho_Chi_Minh', s.executed_at)::date AS ngay_cr,
       s.tram_id, s.tram_name, s.ma_tinh, dm.ten_tinh, dm.khu_vuc,
       s.vendor_tram, s.status, s.ma_loi,
       (SELECT count(*) FROM {_S}.cell_params p WHERE p.cr_session_id = s.id) AS so_cell_cr,
       (SELECT count(*) FROM {_S}.cr_affected_cells a WHERE a.cr_session_id = s.id) AS so_cell_anh_huong
FROM s LEFT JOIN dm ON dm.ma = s.ma_tinh
WHERE {_LOC_VENDOR.format(col="s.vendor_tram")}
  AND (CAST(:trang_thai AS varchar[]) IS NULL OR s.status = ANY(CAST(:trang_thai AS varchar[])))
""",
    # qos/qoe chung 1 cau, :chi_so chon nhanh.
    "cell": f"""
WITH s AS ({_LOC_SESSION}),
{_CTE_CELL},
{_CTE_PHIEU}
SELECT c.cr_session_id AS session_id,
       timezone('Asia/Ho_Chi_Minh', s.executed_at)::date AS ngay_cr,
       s.tram_id, s.tram_name, c.cell_name, c.vendor_cell,
       c.tb_truoc, c.tb_sau, c.lech,
       {_KET_QUA} AS ket_qua, {_LY_DO} AS ly_do,
       c.n_sau AS so_ngay_co_du_lieu,
       (SELECT string_agg(ph.phieu_id, ', ' ORDER BY ph.id) FROM phieu ph
         WHERE ph.cr_session_id = c.cr_session_id AND ph.cell_name = c.cell_name
           AND ph.trang_thai = 'SUCCESS') AS ma_phieu
FROM cell c JOIN s ON s.id = c.cr_session_id
WHERE c.chi_so = :chi_so AND {_LOC_VENDOR.format(col="c.vendor_cell")}
  AND (CAST(:ket_qua AS varchar[]) IS NULL OR {_KET_QUA} = ANY(CAST(:ket_qua AS varchar[])))
  AND (CAST(:ly_do AS varchar[]) IS NULL OR {_LY_DO} = ANY(CAST(:ly_do AS varchar[])))
""",
    "phieu": f"""
WITH s AS ({_LOC_SESSION}),
{_CTE_PHIEU}
SELECT ph.phieu_id AS ma_phieu, ph.cr_session_id AS session_id, ph.cell_name,
       ph.vendor_cell, ph.phuong_an, ph.trang_thai,
       timezone('Asia/Ho_Chi_Minh', ph.created_at)::date AS ngay_xuat,
       ph.id AS _id
FROM phieu ph
WHERE {_LOC_VENDOR.format(col="ph.vendor_cell")}
  AND (CAST(:phuong_an AS varchar[]) IS NULL OR ph.phuong_an = ANY(CAST(:phuong_an AS varchar[])))
  AND (CAST(:trang_thai AS varchar[]) IS NULL OR ph.trang_thai = ANY(CAST(:trang_thai AS varchar[])))
""",
    "can_xu_ly": f"""
WITH s AS ({_LOC_SESSION})
SELECT 'QUA_HAN_XUAT_PHIEU' AS loai, id AS session_id, tram_id, tram_name, status,
       timezone('Asia/Ho_Chi_Minh', executed_at)::date AS ngay, NULL AS ma_loi
FROM s WHERE {_DIEU_KIEN_QUA_HAN} AND {_LOC_VENDOR.format(col="vendor_tram")}
UNION ALL
SELECT 'KHONG_CHAY', id, tram_id, tram_name, status,
       timezone('Asia/Ho_Chi_Minh', created_at)::date, ma_loi
FROM s WHERE status = 'KHONG_CHAY' AND {_LOC_VENDOR.format(col="vendor_tram")}
""",
}

# Bo dau phia SQL bang translate() - xem domain/services/bo_dau.py ve ly do
# khong dung extension unaccent. :q da bo dau + boc %...% o Python; ky tu
# escape la '!' (tranh dau '\' de khong vuong quy tac escape cua chuoi SQL).
_KHOP = "translate(lower(CAST({col} AS text)), :co_dau, :khong_dau) LIKE :q ESCAPE '!'"

# Cot tim kiem theo loai (yeu cau user). cr con khop ten tinh qua :ma_tinh_q
# (ten tinh nam o Python - xem DashboardUseCase).
_COT_TIM = {
    "cr": ("tram_id", "tram_name", "ma_tinh", "session_id"),
    "cell": ("tram_name", "cell_name", "session_id", "ma_phieu"),
    "phieu": ("ma_phieu", "cell_name", "session_id"),
    "can_xu_ly": ("tram_id", "tram_name", "session_id"),
}

# Cot ngay mac dinh + khoa pha hoa ON DINH: thieu khoa pha hoa thi cac dong
# cung gia tri sap xep co the doi thu tu giua 2 truy van -> trang 2 lap dong
# trang 1.
_NGAY_MAC_DINH = {"cr": "ngay_cr", "cell": "ngay_cr", "phieu": "ngay_xuat", "can_xu_ly": "ngay"}
_PHA_HOA = {
    "cr": "session_id DESC",
    "cell": "session_id DESC, cell_name",
    "phieu": "_id DESC",
    "can_xu_ly": "loai, session_id",
}


def _danh_muc_tinh() -> dict:
    """3 mang song song (ma, ten_tinh, khu_vuc) cho CTE dm cua chi tiet cr.

    SINH TU CHINH 2 bang Python dang dung (domain/value_objects/khu_vuc.py +
    ten_tinh.py) qua ham cong khai cua chung - KHONG chep tay bang lan 2 vao
    SQL (2 ban se troi nhau khi sap nhap tinh/doi KV). Truyen bang bind param
    (unnest mang) thay vi ghep chuoi VALUES: khong co ky tu nao vao SQL tho.
    Gom ca ma CU (chi co KV, ten None) lan ma MOI - giong cach khu_vuc.py giu
    ca 2 de tram chua dong bo RIMS khong mat KV."""
    ma = sorted(set(ma_tinh_theo_khu_vuc([KV1, KV2, KV3])) | set(TEN_TINH_THEO_MA))
    return {
        "dm_ma": ma,
        "dm_ten": [ten_tinh_tu_ma(m) for m in ma],
        "dm_kv": [khu_vuc_tu_ma_tinh(m) for m in ma],
    }


def _boc_chi_tiet(nhom: str, co_tim: bool, sap_xep: str, chieu: str) -> str:
    dk_tim = "TRUE"
    if co_tim:
        dk = [_KHOP.format(col=c) for c in _COT_TIM[nhom]]
        if nhom == "cr":
            dk.append("ma_tinh = ANY(CAST(:ma_tinh_q AS varchar[]))")
        dk_tim = "(" + " OR ".join(dk) + ")"
    # sap_xep/chieu DA qua whitelist (COT_SAP_XEP_DASHBOARD / asc|desc) - ghep
    # thang vao SQL la an toan; NULLS LAST de dong thieu so (vd ngay_cr cua
    # session KHONG_CHAY) khong chiem dau trang khi sap giam.
    return f"""
SELECT *, count(*) OVER () AS tong FROM ({_SQL_GOC[nhom]}) x
WHERE {dk_tim}
ORDER BY {sap_xep} {chieu.upper()} NULLS LAST, {_PHA_HOA[nhom]}
LIMIT :limit OFFSET :offset
"""


_SQL_BO_LOC = f"""
SELECT 'ma_tinh' AS loai, ma_tinh AS gia_tri FROM {_S}.tram WHERE ma_tinh IS NOT NULL GROUP BY ma_tinh
UNION ALL
SELECT 'vendor', upper(trim(ten_thiet_bi)) FROM {_S}.tram
WHERE ten_thiet_bi IS NOT NULL AND trim(ten_thiet_bi) <> '' GROUP BY upper(trim(ten_thiet_bi))
ORDER BY 1, 2
"""

# Xuat Excel hau kiem (18/10/2026) - CUNG _LOC_SESSION voi dashboard, chi lay
# session da chay CR (chua co executed_at thi khong co cua so danh gia).
_SQL_LOC_SESSION_EXCEL = f"""
WITH s AS ({_LOC_SESSION})
SELECT id, tram_id, tram_name, executed_at, status FROM s
WHERE executed_at IS NOT NULL
  AND (CAST(:trang_thai AS varchar[]) IS NULL OR status = ANY(CAST(:trang_thai AS varchar[])))
ORDER BY executed_at, id
"""


class DashboardRepo(IDashboardRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _loc(loc: BoLocDashboard, don_vi: str = "day") -> dict:
        # list rong = khong loc (giong vendor/khu_vuc cua find_stations()).
        return {
            "tu_ngay": loc.tu_ngay,
            "den_ngay": loc.den_ngay,
            "ma_tinh": loc.ma_tinh or None,
            "vendor": loc.vendor or None,
            "don_vi": don_vi,
        }

    async def _rows(self, sql: str, params: dict) -> list[dict]:
        result = await self._session.execute(text(sql), params)
        return [dict(r) for r in result.mappings().all()]

    async def tong_hop(self, loc, nguong, don_vi) -> list[dict]:
        # Cho xuat tay = danh sach CHUNG (domain/value_objects/trang_thai_phieu.py)
        # thay LIKE 'KHONG_XUAT_%' - cung 1 dinh nghia voi bo loc + 2 file Excel.
        p = {**self._loc(loc, don_vi), **nguong, "cho_xuat_tay": list(TRANG_THAI_CHO_XUAT_TAY)}
        return await self._rows(_SQL_TONG_HOP, p)

    async def can_xu_ly(self, loc, qua_han_truoc_ngay: date) -> dict:
        p = self._loc(loc)
        return {
            "qua_han": await self._rows(_SQL_QUA_HAN, {**p, "qua_han_truoc_ngay": qua_han_truoc_ngay}),
            "khong_chay": await self._rows(_SQL_KHONG_CHAY, p),
        }

    async def chi_tiet(self, loai, loc, nguong, loc_con, qua_han_truoc_ngay, offset, limit,
                       tim=None, sap_xep=None, chieu="desc"):
        nhom = "cell" if loai in ("qos", "qoe") else loai
        # Phong ve lop 2: ten cot ghep thang vao ORDER BY - tu choi moi thu ngoai
        # whitelist du caller da kiem (sai o day la loi lap trinh, khong phai 422).
        sap_xep = sap_xep or _NGAY_MAC_DINH[nhom]
        if sap_xep not in COT_SAP_XEP_DASHBOARD[loai] or chieu not in ("asc", "desc"):
            raise ValueError(f"sap_xep/chieu khong hop le: {sap_xep} {chieu}")
        p = {**self._loc(loc), "offset": offset, "limit": limit}
        if nhom == "cell":
            p.update(nguong)
            p.update(chi_so=loai.upper(), ket_qua=loc_con.get("ket_qua") or None,
                     ly_do=loc_con.get("ly_do") or None)
        elif nhom == "cr":
            p["trang_thai"] = loc_con.get("trang_thai") or None
            p.update(_danh_muc_tinh())
        elif nhom == "phieu":
            p.update(phuong_an=loc_con.get("phuong_an") or None,
                     trang_thai=loc_con.get("trang_thai") or None)
        else:
            p["qua_han_truoc_ngay"] = qua_han_truoc_ngay
        if tim:
            # Escape % va _ cua nguoi dung: "TXN_1" phai tim dung chuoi do,
            # khong phai mau LIKE. Ky tu escape '!' (xem _KHOP).
            q = tim["q"].replace("!", "!!").replace("%", "!%").replace("_", "!_")
            p.update(q=f"%{q}%", co_dau=CO_DAU, khong_dau=KHONG_DAU, ma_tinh_q=tim.get("ma_tinh") or [])
        sql = _boc_chi_tiet(nhom, bool(tim), sap_xep, chieu)
        rows = await self._rows(sql, p)
        if not rows and offset:
            # Trang vuot qua cuoi: count(*) OVER () khong co dong nao de mang
            # tong - dem lai tu dau de FE van hien dung so trang.
            return [], len(await self._rows(sql, {**p, "offset": 0, "limit": None}))
        tong = int(rows[0]["tong"]) if rows else 0
        for r in rows:
            r.pop("tong", None)
            r.pop("_id", None)
        return rows, tong

    async def bo_loc(self) -> dict:
        rows = await self._rows(_SQL_BO_LOC, {})
        return {
            "ma_tinh": [r["gia_tri"] for r in rows if r["loai"] == "ma_tinh"],
            "vendor": [r["gia_tri"] for r in rows if r["loai"] == "vendor"],
        }

    async def loc_session(self, tu_ngay, den_ngay, ma_tinh, trang_thai) -> list[dict]:
        p = {**self._loc(BoLocDashboard(tu_ngay, den_ngay, ma_tinh)), "trang_thai": trang_thai or None}
        return await self._rows(_SQL_LOC_SESSION_EXCEL, p)
