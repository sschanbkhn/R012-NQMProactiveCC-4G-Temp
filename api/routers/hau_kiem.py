"""
GET /hau-kiem/excel (18/10/2026, yeu cau truc tiep user) - xuat bang hau kiem
ra .xlsx theo bo cuc file mau Check_4G-TXN250M-HNI.xlsx.
Router chi nhan tham so + dat ten file; du lieu o XuatExcelHauKiemUseCase, ve
file o adapters/excel/hau_kiem_xlsx.py.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from adapters.excel.hau_kiem_xlsx import ve_excel
from adapters.excel.kieu import luat_danh_gia
from api.routers.tai_file import dau_thoi_gian, lam_sach, tra_xlsx
from application.dashboard_use_case import DashboardUseCase
from application.xuat_excel_hau_kiem_use_case import XuatExcelHauKiemUseCase
from infrastructure.dependencies import get_xuat_excel_hau_kiem_use_case

router = APIRouter()

_KhuVucFilter = Literal["KV1", "KV2", "KV3"]


@router.get("/hau-kiem/excel")
async def xuat_excel_hau_kiem(
    session_id: int | None = None,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    # Bo loc giong Lich su CR / dashboard - lap tham so de chon nhieu.
    ma_tinh: list[str] | None = Query(default=None),
    khu_vuc: list[_KhuVucFilter] | None = Query(default=None),
    trang_thai: list[str] | None = Query(default=None),
    use_case: XuatExcelHauKiemUseCase = Depends(get_xuat_excel_hau_kiem_use_case),
) -> Response:
    # 2 che do LOAI TRU nhau: 1 session, hoac 1 khoang ngay. Thieu ca 2 (hoac
    # chi 1 dau mut) se xuat ca DB - tu choi ro rang thay vi doan.
    if session_id is None and (tu_ngay is None or den_ngay is None):
        raise HTTPException(status_code=422, detail="Can session_id HOAC ca tu_ngay va den_ngay")
    if session_id is None and tu_ngay > den_ngay:
        raise HTTPException(status_code=422, detail="tu_ngay phai <= den_ngay")

    khoi = await use_case.execute(session_id, tu_ngay, den_ngay, ma_tinh, khu_vuc, trang_thai)
    # Sheet "Phieu" (19/10/2026): chi phieu cua cac session dang xuat, lay qua
    # CUNG ham repo voi /phieu/excel de 2 file ra cung so.
    phieu = await use_case.phieu([k["session_id"] for k in khoi])
    noi_dung = ve_excel(khoi, luat_danh_gia(**DashboardUseCase.nguong()), phieu)

    # Ten file (DOT 2): 1 session -> hau_kiem_<ma_tram>_<ten_tram>_<ts>;
    # nhieu session -> hau_kiem_<tu>_den_<den>_<ts> (ngay yyyymmdd).
    if session_id is not None:
        if khoi:
            ten = f"{lam_sach(khoi[0]['tram_id'])}_{lam_sach(khoi[0]['tram'])}"
        else:
            ten = f"session_{session_id}"
    else:
        ten = f"{tu_ngay:%Y%m%d}_den_{den_ngay:%Y%m%d}"
    return tra_xlsx(noi_dung, f"hau_kiem_{ten}_{dau_thoi_gian()}.xlsx")
