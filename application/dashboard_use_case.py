"""
DashboardUseCase - GET /dashboard/* (18/10/2026, yeu cau truc tiep user; DOT 2
cung ngay: vendor, chi tiet theo card, bo loc, xu huong theo ngay/tuan).

=== CHIA VIEC ===
Repo dem BANG SQL (GROUP BY / GROUPING SETS) - o day CHI gop dong nhom, tinh %,
lap day moc thoi gian va anh xa ten tinh/KV. Vong for chi chay tren DONG NHOM
hoac 1 TRANG chi tiet, khong bao gio tren toan bo session.

=== NGUONG ===
Lay THANG tu hang so dang dung cho bang hau kiem (MIN_DAYS_REQUIRED,
MUC_TOI_THIEU, nguong lech QoS/QoE) roi truyen xuong SQL - doi nguong 1 noi thi
dashboard doi theo, khong co ban so thu 2.

=== VENDOR ===
Chi so CR theo vendor TRAM TAT, hau kiem + phieu theo vendor CUA CELL - xem
adapters/postgres/dashboard_repo.py muc "VENDOR".
"""

from datetime import date, datetime, timedelta

from application.get_qoe_cells_use_case import _QOE_CELL_THRESHOLD_DELTA  # noqa: PLC2701
from application.get_sessions_use_case import hom_nay_vn
from application.xuat_phieu_use_case import (  # noqa: PLC2701
    XUAT_PHIEU_AFTER_DAYS,
    _XUAT_PHIEU_QOS_THRESHOLD_DELTA,
)
from domain.ports.outbound.repo_ports import BoLocDashboard, IDashboardRepo
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, MUC_TOI_THIEU
from domain.value_objects.khu_vuc import KV1, KV2, KV3, khu_vuc_tu_ma_tinh, ma_tinh_theo_khu_vuc
from domain.services.bo_dau import bo_dau
from domain.value_objects.ten_tinh import TEN_TINH_THEO_MA, ten_tinh_tu_ma

# Cot dem cua repo - dung de cong don khi gop ma_tinh -> khu_vuc.
_COT_DEM = (
    "so_session", "done", "partial_success", "khong_chay", "failed", "dang_chay",
    "so_tram", "so_cell_cr",
    "qos_tong", "qos_dat", "qos_kd_san", "qos_kd_lech", "qos_thieu",
    "qoe_tong", "qoe_dat", "qoe_kd_san", "qoe_kd_lech", "qoe_thieu",
    "phieu_he_thong", "phieu_hien_truong", "phieu_success", "phieu_cho_xuat_tay", "phieu_loi",
)

# Tram co ma_tinh la/rong -> khu_vuc_tu_ma_tinh() tra None. Van phai hien ra
# (giong tinh than khu_vuc.py: "khong biet" phai thay duoc, khong gan bua KV).
_KV_KHONG_XAC_DINH = "KHONG_XAC_DINH"
# Vendor SQL gan cho cell/tram khong ghep duoc ten_thiet_bi (dashboard_repo._VENDOR).
_VENDOR_KHONG_XAC_DINH = "UNKNOWN"

# chi_tiet_thoi_gian (API) -> don vi date_trunc cua Postgres.
DON_VI_THOI_GIAN = {"ngay": "day", "tuan": "week"}

# Cac trang thai CO THE xuat hien trong tong.theo_trang_thai (FE tu map nhan,
# muc 6 DOT 2): 5 trang thai dem rieng + "khac" (gom phan con lai - EVAL_PENDING,
# EVALUATING, EVALUATED, KHONG_DU_DU_LIEU... - de tong luon bang so_session).
TRANG_THAI_DEM = ("DONE", "PARTIAL_SUCCESS", "KHONG_CHAY", "FAILED", "dang_chay", "khac")


def _ty_le(so: int, tong: int) -> float | None:
    # None (khong phai 0) khi khong co mau - 0% va "khong co gi de tinh" la 2
    # thong tin khac nhau tren dashboard.
    return round(so * 100 / tong, 1) if tong else None


def _n(r: dict, k: str) -> int:
    # sum() SQL tra NULL khi nhom rong (vd loc vendor khong co du lieu) -> 0.
    return int(r.get(k) or 0)


def _hau_kiem(r: dict, p: str) -> dict:
    tong = _n(r, f"{p}_tong")
    kd_san, kd_lech = _n(r, f"{p}_kd_san"), _n(r, f"{p}_kd_lech")
    dat, thieu = _n(r, f"{p}_dat"), _n(r, f"{p}_thieu")
    return {
        "so_cell": tong,
        "dat": {"so": dat, "ty_le": _ty_le(dat, tong)},
        "khong_dat": {
            "so": kd_san + kd_lech,
            "ty_le": _ty_le(kd_san + kd_lech, tong),
            # Tach theo THU TU xet cua EvaluationService.evaluate(): duoi san
            # xet truoc, nen 1 cell vua duoi san vua tut nhieu chi dem o san.
            "tb_sau_duoi_muc": kd_san,
            "lech_qua_nguong": kd_lech,
        },
        "thieu_du_lieu": {"so": thieu, "ty_le": _ty_le(thieu, tong)},
    }


def _chi_so(r: dict) -> dict:
    so_session = int(r["so_session"] or 0)
    dem = {
        "DONE": int(r["done"] or 0),
        "PARTIAL_SUCCESS": int(r["partial_success"] or 0),
        "KHONG_CHAY": int(r["khong_chay"] or 0),
        "FAILED": int(r["failed"] or 0),
        "dang_chay": int(r["dang_chay"] or 0),
    }
    dem["khac"] = so_session - sum(dem.values())
    return {
        "tong": {
            "so_session": so_session,
            "theo_trang_thai": dem,
            "so_tram": int(r["so_tram"] or 0),
            "so_cell_cr": int(r["so_cell_cr"] or 0),
        },
        "hau_kiem": {"qos": _hau_kiem(r, "qos"), "qoe": _hau_kiem(r, "qoe")},
        "phieu": {
            "success": int(r["phieu_success"] or 0),
            "he_thong": int(r["phieu_he_thong"] or 0),
            "hien_truong": int(r["phieu_hien_truong"] or 0),
            "cho_xuat_tay": int(r["phieu_cho_xuat_tay"] or 0),
            "loi": int(r["phieu_loi"] or 0),
        },
    }


def _gop_theo_khu_vuc(dong_ma_tinh: list[dict]) -> list[dict]:
    # Cong don cac dong ma_tinh cung KV. so_tram cong duoc vi 1 tram chi co 1
    # ma_tinh (tap tram giua cac ma_tinh khong giao nhau).
    gop: dict[str, dict] = {}
    for r in dong_ma_tinh:
        kv = khu_vuc_tu_ma_tinh(r["gia_tri"]) or _KV_KHONG_XAC_DINH
        dich = gop.setdefault(kv, {"gia_tri": kv, **{c: 0 for c in _COT_DEM}})
        for c in _COT_DEM:
            dich[c] += int(r[c] or 0)
    return [gop[k] for k in sorted(gop)]


def _cac_moc(tu_ngay: date, den_ngay: date, don_vi: str) -> list[date]:
    # Lap DU moc trong khoang (ke ca moc khong co session) de bieu do lien tuc.
    # Tuan bat dau thu Hai - khop date_trunc('week') cua Postgres.
    if don_vi == "week":
        moc, buoc = tu_ngay - timedelta(days=tu_ngay.weekday()), timedelta(days=7)
    else:
        moc, buoc = tu_ngay, timedelta(days=1)
    ket_qua = []
    while moc <= den_ngay:
        ket_qua.append(moc)
        moc += buoc
    return ket_qua


def _diem_xu_huong(moc: date, r: dict | None) -> dict:
    r = r or {}
    def n(k):  # noqa: E306 - helper 1 dong
        return int(r.get(k) or 0)
    return {
        "moc": moc.isoformat(),
        "so_cr": n("so_session"),
        "so_phieu": n("phieu_success"),
        "ty_le_dat_qos": _ty_le(n("qos_dat"), n("qos_tong")),
        "ty_le_dat_qoe": _ty_le(n("qoe_dat"), n("qoe_tong")),
        "so_cell_khong_dat_qos": n("qos_kd_san") + n("qos_kd_lech"),
        "so_cell_khong_dat_qoe": n("qoe_kd_san") + n("qoe_kd_lech"),
    }


def _json(gia_tri):
    return gia_tri.isoformat() if isinstance(gia_tri, (date, datetime)) else gia_tri


class DashboardUseCase:
    def __init__(self, dashboard_repo: IDashboardRepo):
        self._repo = dashboard_repo

    @staticmethod
    def bo_loc_tu_tham_so(tu_ngay, den_ngay, khu_vuc=None, ma_tinh=None, vendor=None) -> BoLocDashboard:
        # khu_vuc va ma_tinh cung loc tren tram.ma_tinh -> co ca 2 thi lay
        # GIAO (nguoi dung chon KV1 + HCM thi khong co ket qua, dung y nghia).
        loc_ma_tinh = ma_tinh or None
        if khu_vuc:
            theo_kv = ma_tinh_theo_khu_vuc(khu_vuc)
            loc_ma_tinh = [m for m in theo_kv if m in ma_tinh] if ma_tinh else theo_kv
        return BoLocDashboard(tu_ngay, den_ngay, loc_ma_tinh, vendor or None)

    @staticmethod
    def nguong() -> dict:
        return {
            "min_ngay": MIN_DAYS_REQUIRED,
            "muc_toi_thieu": MUC_TOI_THIEU,
            "lech_qos": _XUAT_PHIEU_QOS_THRESHOLD_DELTA,
            "lech_qoe": _QOE_CELL_THRESHOLD_DELTA,
        }

    @staticmethod
    def _moc_qua_han(bay_gio: datetime | None) -> date:
        # Moc qua han GIONG GetSessionsUseCase (?qua_han=true).
        return hom_nay_vn(bay_gio) - timedelta(days=XUAT_PHIEU_AFTER_DAYS)

    async def execute(
        self,
        tu_ngay: date,
        den_ngay: date,
        khu_vuc: list[str] | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        chi_tiet_thoi_gian: str = "ngay",
        bay_gio: datetime | None = None,
    ) -> dict:
        loc = self.bo_loc_tu_tham_so(tu_ngay, den_ngay, khu_vuc, ma_tinh, vendor)
        don_vi = DON_VI_THOI_GIAN[chi_tiet_thoi_gian]
        rows = await self._repo.tong_hop(loc, self.nguong(), don_vi)
        can = await self._repo.can_xu_ly(loc, self._moc_qua_han(bay_gio))

        theo_nhom: dict[str, list[dict]] = {"tong": [], "ma_tinh": [], "vendor": [], "moc": []}
        for r in rows:
            theo_nhom[r["nhom"]].append(r)
        # GROUPING SETS () luon tra 1 dong ke ca khi khong co session nao.
        tong = theo_nhom["tong"][0] if theo_nhom["tong"] else {c: 0 for c in _COT_DEM}

        def _nhom(ds: list[dict], them=None) -> list[dict]:
            return [
                {"gia_tri": r["gia_tri"], **(them(r["gia_tri"]) if them else {}), **_chi_so(r)}
                for r in sorted(ds, key=lambda x: x["gia_tri"] or "")
            ]

        theo_moc = {r["gia_tri"]: r for r in theo_nhom["moc"]}
        theo_ma_loi: dict[str, int] = {}
        for s in can["khong_chay"]:
            theo_ma_loi[s["ma_loi"] or "KHONG_RO"] = theo_ma_loi.get(s["ma_loi"] or "KHONG_RO", 0) + 1

        return {
            "tu_ngay": tu_ngay.isoformat(),
            "den_ngay": den_ngay.isoformat(),
            "chi_tiet_thoi_gian": chi_tiet_thoi_gian,
            **_chi_so(tong),
            # SUA 19/10/2026 (yeu cau user): theo_nhom BO nhom khong xac dinh
            # (vendor UNKNOWN, KV KHONG_XAC_DINH, tinh NULL/ma la) - nhom do
            # khong co y nghia de so sanh tren bieu do. Tong chung o tren VAN
            # tinh ca cac dong nay (khong mat so) - vi vay tong cac nhom co the
            # NHO HON tong chung, la co y.
            "theo_nhom": {
                "khu_vuc": _nhom([r for r in _gop_theo_khu_vuc(theo_nhom["ma_tinh"])
                                  if r["gia_tri"] != _KV_KHONG_XAC_DINH]),
                "ma_tinh": _nhom([r for r in theo_nhom["ma_tinh"] if khu_vuc_tu_ma_tinh(r["gia_tri"])],
                                 lambda m: {"ten_tinh": ten_tinh_tu_ma(m), "khu_vuc": khu_vuc_tu_ma_tinh(m)}),
                "vendor": _nhom([r for r in theo_nhom["vendor"] if r["gia_tri"] != _VENDOR_KHONG_XAC_DINH]),
            },
            "xu_huong": [
                _diem_xu_huong(m, theo_moc.get(m.isoformat()))
                for m in _cac_moc(tu_ngay, den_ngay, don_vi)
            ],
            "can_xu_ly": {
                "qua_han_xuat_phieu": {
                    "so_luong": len(can["qua_han"]),
                    "sessions": [{k: _json(v) for k, v in s.items()} for s in can["qua_han"]],
                },
                "khong_chay": {
                    "so_luong": len(can["khong_chay"]),
                    "theo_ma_loi": theo_ma_loi,
                    "sessions": [{k: _json(v) for k, v in s.items()} for s in can["khong_chay"]],
                },
            },
        }

    async def chi_tiet(
        self,
        loai: str,
        tu_ngay: date,
        den_ngay: date,
        khu_vuc: list[str] | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        loc_con: dict | None = None,
        trang: int = 1,
        kich_thuoc: int | None = 50,
        bay_gio: datetime | None = None,
        q: str | None = None,
        sap_xep: str | None = None,
        chieu: str = "desc",
    ) -> dict:
        """kich_thuoc None = lay HET (xuat Excel chi tiet). q: tim tu do (khong
        phan biet hoa/thuong, dau). sap_xep: cot trong COT_SAP_XEP_DASHBOARD
        (router da kiem), None = cot ngay cua loai."""
        loc = self.bo_loc_tu_tham_so(tu_ngay, den_ngay, khu_vuc, ma_tinh, vendor)
        offset = (trang - 1) * kich_thuoc if kich_thuoc else 0
        rows, tong = await self._repo.chi_tiet(
            loai, loc, self.nguong(), loc_con or {}, self._moc_qua_han(bay_gio), offset, kich_thuoc,
            tim=self._tim(q), sap_xep=sap_xep, chieu=chieu,
        )
        dong = []
        for r in rows:
            # ten_tinh/khu_vuc cua cr DA co tu SQL (JOIN danh muc tinh, 19/10/2026)
            # - khong anh xa lai o day, tranh 2 noi cho cung 1 gia tri.
            d = {k: _json(v) for k, v in r.items()}
            for k in ("tb_truoc", "tb_sau", "lech"):
                if d.get(k) is not None:
                    d[k] = float(d[k])  # NUMERIC -> so JSON
            dong.append(d)
        return {"loai": loai, "tong": tong, "trang": trang, "kich_thuoc": kich_thuoc, "dong": dong}

    @staticmethod
    def _tim(q: str | None) -> dict | None:
        """Chuan hoa chuoi tim o Python (bo dau + chu thuong - xem
        domain/services/bo_dau.py). Ten tinh CHI co o Python (ten_tinh.py), nen
        khop ten tinh tai day roi day xuong SQL danh sach ma_tinh khop - "ha
        noi" tim ra session tinh HNI du cot tram_name khong chua chu do."""
        q = bo_dau(q).strip()
        if not q:
            return None
        ma_khop = [ma for ma, ten in TEN_TINH_THEO_MA.items() if q in bo_dau(ten)]
        return {"q": q, "ma_tinh": ma_khop}

    async def bo_loc(self) -> dict:
        tu_db = await self._repo.bo_loc()
        return {
            "khu_vuc": [KV1, KV2, KV3],
            "ma_tinh": [
                {"ma": m, "ten": ten_tinh_tu_ma(m), "khu_vuc": khu_vuc_tu_ma_tinh(m)}
                for m in tu_db["ma_tinh"]
            ],
            "vendor": tu_db["vendor"],
        }
