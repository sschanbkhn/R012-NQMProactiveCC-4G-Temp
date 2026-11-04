"""
GET /dashboard/* (18/10/2026, yeu cau truc tiep user - muc 4; DOT 2 cung ngay).
Router CHI nhan tham so + anh xa - so lieu tinh o DashboardUseCase/DashboardRepo,
ve Excel o adapters/excel/dashboard_xlsx.py.

Bo loc chung: tu_ngay, den_ngay, khu_vuc[], ma_tinh[], vendor[] (lap tham so
de chon nhieu, ?vendor=NOKIA&vendor=ZTE). DOT 2 BO netact.
VENDOR AP 2 CACH: chi so CR theo vendor TRAM TAT; hau kiem + phieu theo vendor
CUA CELL (xem adapters/postgres/dashboard_repo.py muc "VENDOR").
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.excel.dashboard_xlsx import ve_chi_tiet, ve_tong_hop
from adapters.excel.kieu import luat_danh_gia
from api.routers.tai_file import dau_thoi_gian, tra_xlsx
from application.dashboard_use_case import DashboardUseCase
from domain.ports.outbound.repo_ports import COT_SAP_XEP_DASHBOARD
from infrastructure.dependencies import get_dashboard_use_case

router = APIRouter()

# Whitelist bang Literal - gia tri la tra 422 ro rang thay vi am tham ra rong.
_KhuVucFilter = Literal["KV1", "KV2", "KV3"]
_VendorFilter = Literal["NOKIA", "ERICSSON", "HUAWEI", "ZTE"]
_Loai = Literal["cr", "qos", "qoe", "phieu", "can_xu_ly"]
_KetQua = Literal["DAT", "KHONG_DAT", "INSUFFICIENT_DATA"]
_LyDo = Literal["duoi_muc", "tut"]
_PhuongAn = Literal["1", "2"]


@dataclass
class _BoLoc:
    tu_ngay: date
    den_ngay: date
    khu_vuc: list[str] | None
    ma_tinh: list[str] | None
    vendor: list[str] | None


def _bo_loc(
    tu_ngay: date,
    den_ngay: date,
    khu_vuc: list[_KhuVucFilter] | None = Query(default=None),
    ma_tinh: list[str] | None = Query(default=None),
    vendor: list[_VendorFilter] | None = Query(default=None),
) -> _BoLoc:
    # 1 dependency cho bo loc chung - 4 endpoint dung CUNG dinh nghia tham so,
    # khong lap lai (lech 1 cho la FE goi cung URL ma ra so khac).
    if tu_ngay > den_ngay:
        raise HTTPException(status_code=422, detail="tu_ngay phai <= den_ngay")
    return _BoLoc(tu_ngay, den_ngay, khu_vuc, ma_tinh, vendor)


def _luat() -> list[str]:
    return luat_danh_gia(**DashboardUseCase.nguong())


@router.get("/dashboard/bo-loc")
async def bo_loc(use_case: DashboardUseCase = Depends(get_dashboard_use_case)) -> dict:
    """Danh sach lua chon cho dropdown FE - DISTINCT tu bang tram."""
    return await use_case.bo_loc()


@router.get("/dashboard/tong-quan")
async def tong_quan(
    loc: _BoLoc = Depends(_bo_loc),
    chi_tiet_thoi_gian: Literal["ngay", "tuan"] = "ngay",
    use_case: DashboardUseCase = Depends(get_dashboard_use_case),
) -> dict:
    return await use_case.execute(
        loc.tu_ngay, loc.den_ngay, loc.khu_vuc, loc.ma_tinh, loc.vendor, chi_tiet_thoi_gian
    )


def _loc_con(
    trang_thai: list[str] | None = Query(default=None),
    ket_qua: list[_KetQua] | None = Query(default=None),
    ly_do: list[_LyDo] | None = Query(default=None),
    phuong_an: list[_PhuongAn] | None = Query(default=None),
) -> dict:
    # Loc con theo loai card: trang_thai (cr, phieu), ket_qua + ly_do (qos,
    # qoe), phuong_an (phieu). Tham so khong thuoc loai dang xem bi bo qua.
    return {"trang_thai": trang_thai, "ket_qua": ket_qua, "ly_do": ly_do, "phuong_an": phuong_an}


@dataclass
class _TimSapXep:
    q: str | None
    sap_xep: str | None
    chieu: str


def _tim_sap_xep(
    loai: _Loai,
    q: str | None = Query(default=None, max_length=100),
    sap_xep: str | None = None,
    chieu: Literal["asc", "desc"] = "desc",
) -> _TimSapXep:
    # Kiem sap_xep theo whitelist CUA TUNG LOAI (cot hop le khac nhau giua cac
    # card) -> 422 kem danh sach cot hop le de FE sua ngay. Dung CHUNG cho
    # trang chi tiet va Excel nen 2 ben luon nhan cung tap tham so.
    if sap_xep is not None and sap_xep not in COT_SAP_XEP_DASHBOARD[loai]:
        raise HTTPException(
            status_code=422,
            detail=f"sap_xep '{sap_xep}' khong hop le cho loai {loai}; cho phep: "
            + ", ".join(COT_SAP_XEP_DASHBOARD[loai]),
        )
    return _TimSapXep(q, sap_xep, chieu)


@router.get("/dashboard/chi-tiet")
async def chi_tiet(
    loai: _Loai,
    loc: _BoLoc = Depends(_bo_loc),
    loc_con: dict = Depends(_loc_con),
    tsx: _TimSapXep = Depends(_tim_sap_xep),
    trang: int = Query(default=1, ge=1),
    # Tran 200 (yeu cau user): phan trang THAT o SQL, 1 trang lon hon la dau
    # hieu FE dang keo het ve loc phia client.
    kich_thuoc: int = Query(default=50, ge=1, le=200),
    use_case: DashboardUseCase = Depends(get_dashboard_use_case),
) -> dict:
    return await use_case.chi_tiet(
        loai, loc.tu_ngay, loc.den_ngay, loc.khu_vuc, loc.ma_tinh, loc.vendor, loc_con, trang, kich_thuoc,
        q=tsx.q, sap_xep=tsx.sap_xep, chieu=tsx.chieu,
    )


@router.get("/dashboard/chi-tiet/excel")
async def chi_tiet_excel(
    loai: _Loai,
    loc: _BoLoc = Depends(_bo_loc),
    loc_con: dict = Depends(_loc_con),
    tsx: _TimSapXep = Depends(_tim_sap_xep),
    use_case: DashboardUseCase = Depends(get_dashboard_use_case),
):
    # Excel = TOAN BO dong khop (kich_thuoc None), CUNG tim + sap xep voi trang
    # chi tiet - nguoi dung tai ve dung nhung gi dang nhin, theo dung thu tu.
    kq = await use_case.chi_tiet(
        loai, loc.tu_ngay, loc.den_ngay, loc.khu_vuc, loc.ma_tinh, loc.vendor, loc_con, 1, None,
        q=tsx.q, sap_xep=tsx.sap_xep, chieu=tsx.chieu,
    )
    ten = f"dashboard_{loai}_{loc.tu_ngay:%Y%m%d}_den_{loc.den_ngay:%Y%m%d}_{dau_thoi_gian()}.xlsx"
    return tra_xlsx(ve_chi_tiet(loai, kq["dong"], _luat()), ten)


@router.get("/dashboard/excel")
async def tong_hop_excel(
    loc: _BoLoc = Depends(_bo_loc),
    chi_tiet_thoi_gian: Literal["ngay", "tuan"] = "ngay",
    use_case: DashboardUseCase = Depends(get_dashboard_use_case),
):
    tq = await use_case.execute(
        loc.tu_ngay, loc.den_ngay, loc.khu_vuc, loc.ma_tinh, loc.vendor, chi_tiet_thoi_gian
    )
    ten = f"dashboard_tong_hop_{loc.tu_ngay:%Y%m%d}_den_{loc.den_ngay:%Y%m%d}_{dau_thoi_gian()}.xlsx"
    return tra_xlsx(ve_tong_hop(tq, _luat()), ten)
