"""
POST /phieu - xuat phieu SaveCellClm cho 1 cell.
GET  /phieu - lich su phieu da xuat (bang cr_phieu), filter + phan trang.
GET  /phieu/excel - xuat Excel phieu (19/10/2026), ve o adapters/excel/phieu_xlsx.py.
Tu: yeu cau truc tiep user (KHOI 4a/5 SaveCellClm; UI lich su phieu 11/08).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from api.routers.loc_ngay import khoang_ngay_gmt7
from api.schemas.phieu_schemas import (
    PhieuListItem,
    PhieuListResponse,
    XoaPhieuResponse,
    XuatPhieuRequest,
    XuatPhieuResponse,
)
from domain.errors import QoeDataInsufficientError
from domain.ports.inbound.use_case_ports import IXuatPhieuUseCase
from domain.ports.outbound.repo_ports import ICrPhieuRepo, IQoeSnapshotRepo, IQosSnapshotRepo
from application.phieu_lam_tron import co_vuot_luat_lam_tron
from application.xoa_phieu_use_case import XoaPhieuUseCase
from domain.services.phan_loai_loi_cts import phan_loai_loi_cts
from domain.value_objects.khu_vuc import ma_tinh_theo_khu_vuc
from domain.value_objects.trang_thai_phieu import TRANG_THAI_LOC, nhom_trang_thai, ten_phuong_an
from adapters.excel.phieu_xlsx import ve_excel_phieu
from api.routers.tai_file import dau_thoi_gian, tra_xlsx
from infrastructure.dependencies import (
    get_qoe_snapshot_repo,
    get_qos_snapshot_repo,
    get_cr_phieu_repo,
    get_xoa_phieu_use_case,
    get_xuat_phieu_use_case,
)

router = APIRouter()

# Whitelist BAT BUOC bang Literal (khong phai str thuong) - FastAPI/Pydantic tu
# tra 422 ngay o tang validate, request khong bao gio toi duoc code xu ly. Cung
# co che da dung o /sessions va /stations (C1.6-fix).
#
# V2 (12/08): BO "DRY_RUN" - khong con dong nao mang trang_thai do.
# V4 (12/08): THEM 2 gia tri cho cell job CO Y khong xuat (vuot tran 10 /
# het luot thu) - dung de nguoi van hanh loc ra danh sach can xu ly tay, dung
# muc dich cua V4. Khop hang so trong application/xuat_phieu_use_case.py.
#
# 19/10/2026: lay tu danh sach CHUNG domain/value_objects/trang_thai_phieu.py
# thay vi liet ke tay - ban liet ke tay thieu KHONG_XUAT_DA_CO_PHIEU_THANG nen
# loc gia tri do bi 422. Literal[tuple] = Literal["a", "b", ...].
_PhieuTrangThai = Literal[TRANG_THAI_LOC]
_PhieuSortBy = Literal["id", "cr_session_id", "cell_name", "trang_thai", "created_at"]
# 17082026 - chi so lam cell KHONG DAT. Literal (khong phai str thuong) de gia
# tri la bi tu choi 422 ngay o tang validate, khong am tham tra ve danh sach rong.
_PhieuNguon = Literal["QOS", "QOE", "CA_HAI"]
_SortOrder = Literal["asc", "desc"]
# Bo loc Excel phieu - CUNG gia tri voi /dashboard (api/routers/dashboard.py).
_KhuVucFilter = Literal["KV1", "KV2", "KV3"]
_VendorFilter = Literal["NOKIA", "ERICSSON", "HUAWEI", "ZTE"]
_PhuongAn = Literal["1", "2"]


def _loc_tram_cell(khu_vuc, ma_tinh, vendor, phuong_an) -> dict:
    # 1 ham cho GET /phieu va /phieu/excel - 2 endpoint quy doi tham so GIONG
    # HET thi cung bo loc moi ra cung so dong.
    # khu_vuc + ma_tinh -> GIAO (giong dashboard). Giao rong giu [] (khong
    # phai None) de ra 0 dong, khong bi hieu thanh "khong loc".
    loc_ma_tinh = ma_tinh or None
    if khu_vuc:
        theo_kv = ma_tinh_theo_khu_vuc(khu_vuc)
        loc_ma_tinh = [m for m in theo_kv if m in ma_tinh] if ma_tinh else theo_kv
    return {"ma_tinh": loc_ma_tinh, "vendor": vendor or None, "phuong_an": phuong_an or None}


@router.get("/phieu", response_model=PhieuListResponse)
async def list_phieu(
    session_id: int | None = None,
    trang_thai: _PhieuTrangThai | None = None,
    # 1 O TIM CHUNG cho cell_name VA phieu_id (13/08): nguoi dung KHONG phai
    # chon truoc "tim theo gi" - go "SSN104" hay "19207" deu ra dung thu ho can.
    # Bat FE bay 1 dropdown "tim theo: [cell/phieu]" chi la day viec phan loai
    # cho nguoi dung, trong khi 2 truong nay khong bao gio nham lan duoc voi
    # nhau (ten cell co chu, phieu_id toan so).
    q: str | None = None,
    # NGAY LICH GMT+7 tren created_at, hai dau mut DOC LAP - y het GET /jobs/runs
    # (api/routers/loc_ngay.py). KHONG viet lai logic mui gio o day.
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    sort_by: _PhieuSortBy | None = None,
    order: _SortOrder = "desc",
    # 17082026 - loc theo chi so lam cell khong dat. Dong tao TRUOC dot nay co
    # nguon_khong_dat=NULL nen KHONG xuat hien o bat ky gia tri loc nao.
    nguon: _PhieuNguon | None = None,
    # 19/10/2026 - CUNG bo loc tram cua cell voi /phieu/excel (xem _loc_tram_cell).
    khu_vuc: list[_KhuVucFilter] | None = Query(default=None),
    ma_tinh: list[str] | None = Query(default=None),
    vendor: list[_VendorFilter] | None = Query(default=None),
    phuong_an: list[_PhuongAn] | None = Query(default=None),
    cr_phieu_repo: ICrPhieuRepo = Depends(get_cr_phieu_repo),
    # THEM 18/10/2026 - doc snapshot de gan co vuot_luat_lam_tron (xem
    # application/phieu_lam_tron.py).
    qos_snapshot_repo: IQosSnapshotRepo = Depends(get_qos_snapshot_repo),
    qoe_snapshot_repo: IQoeSnapshotRepo = Depends(get_qoe_snapshot_repo),
) -> PhieuListResponse:
    # Goi THANG repo (khong qua use case) - dung tien le GET /stations (C1.3):
    # day la read-model thuan cho 1 man hinh, KHONG co logic nghiep vu nao de
    # dat vao application/ (chi filter + phan trang + sort, deu la viec cua tang
    # DB). Them 1 use case chi de chuyen tiep 2 loi goi repo se la lop trung
    # gian rong. Khac POST /phieu ngay duoi - cho do CO nghiep vu that (danh
    # gia QoS, chong trung, goi CTS) nen bat buoc qua XuatPhieuUseCase.
    #
    # 1 endpoint dung cho CA 2 ngu canh UI: tab lich su rieng (khong truyen
    # session_id -> tat ca phieu) va trong 1 session (session_id=<id>).
    #
    # V2 (12/08): khong truyen trang_thai = LAY TAT CA. Luat "an dong DRY_RUN
    # mac dinh" da bi bo cung voi dry_run.
    #
    # 13/08: them q/tu_ngay/den_ngay -> loc CHUYEN SANG SERVER-SIDE. Truoc day FE
    # tu loc cell tren du lieu da tai ve nen chi loc duoc TRONG TRANG HIEN TAI:
    # go ten 1 cell nam o trang 3 thi khong bao gio ra, ma man hinh van bao
    # "khong tim thay" - sai pham vi im lang (da co ghi chu canh bao duoi bang).
    tu_moc, den_moc = khoang_ngay_gmt7(tu_ngay, den_ngay)
    loc = _loc_tram_cell(khu_vuc, ma_tinh, vendor, phuong_an)

    total = await cr_phieu_repo.count_phieu(session_id, trang_thai, q, tu_moc, den_moc, nguon, **loc)
    rows = await cr_phieu_repo.list_phieu(
        session_id, trang_thai, page, size, sort_by, order, q, tu_moc, den_moc, nguon, **loc
    )
    co_lam_tron = await co_vuot_luat_lam_tron(rows, qos_snapshot_repo, qoe_snapshot_repo)
    return PhieuListResponse(
        total=total,
        page=page,
        size=size,
        # phan_loai_loi KHONG co trong row tu DB - tinh tai day tu error_message
        # (B4). Tinh o router chu khong o repo: day la thong tin danh cho NGUOI
        # DOC man hinh, khong phai du lieu luu tru
        data=[
            PhieuListItem(
                **row,
                phan_loai_loi=phan_loai_loi_cts(row.get("error_message"), row.get("trang_thai")),
                vuot_luat_lam_tron=co_lam_tron.get(row["id"]),
                # 19/10/2026 - nhan san cho FE (dau modal, mau dong) de FE khong
                # tu map "1"/"2" va tu chia nhom - 1 dinh nghia o domain.
                phuong_an=ten_phuong_an((row.get("request_payload") or {}).get("PhuongAnXuLyDuKien")),
                nhom_trang_thai=nhom_trang_thai(row.get("trang_thai")),
            )
            for row in rows
        ],
    )


@router.get("/phieu/excel")
async def xuat_excel_phieu(
    session_id: int | None = None,
    trang_thai: _PhieuTrangThai | None = None,
    q: str | None = None,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    nguon: _PhieuNguon | None = None,
    # 4 bo loc them so voi man danh sach (19/10/2026) - theo TRAM CUA CELL.
    # Lap tham so de chon nhieu, giong /dashboard va /hau-kiem/excel.
    khu_vuc: list[_KhuVucFilter] | None = Query(default=None),
    ma_tinh: list[str] | None = Query(default=None),
    vendor: list[_VendorFilter] | None = Query(default=None),
    phuong_an: list[_PhuongAn] | None = Query(default=None),
    cr_phieu_repo: ICrPhieuRepo = Depends(get_cr_phieu_repo),
):
    # Giong /hau-kiem/excel: 1 session HOAC du 2 dau ngay - thieu ca 2 se keo
    # ca bang va ten file khong co khoang ngay de dat.
    if session_id is None and (tu_ngay is None or den_ngay is None):
        raise HTTPException(status_code=422, detail="Can session_id HOAC ca tu_ngay va den_ngay")
    if tu_ngay and den_ngay and tu_ngay > den_ngay:
        raise HTTPException(status_code=422, detail="tu_ngay phai <= den_ngay")

    tu_moc, den_moc = khoang_ngay_gmt7(tu_ngay, den_ngay)
    rows = await cr_phieu_repo.dong_excel(
        session_ids=[session_id] if session_id is not None else None,
        trang_thai=trang_thai, q=q, tu_ngay=tu_moc, den_ngay=den_moc, nguon=nguon,
        **_loc_tram_cell(khu_vuc, ma_tinh, vendor, phuong_an),
    )
    if tu_ngay and den_ngay:
        ten = f"phieu_{tu_ngay:%Y%m%d}_den_{den_ngay:%Y%m%d}_{dau_thoi_gian()}.xlsx"
    else:
        ten = f"phieu_session_{session_id}_{dau_thoi_gian()}.xlsx"
    return tra_xlsx(ve_excel_phieu(rows), ten)


@router.post("/phieu", response_model=XuatPhieuResponse)
async def xuat_phieu(
    body: XuatPhieuRequest,
    use_case: IXuatPhieuUseCase = Depends(get_xuat_phieu_use_case),
) -> XuatPhieuResponse:
    # POST THAT len TTS. V2 (12/08): use case da bo dry_run nen KHONG con tham
    # so nao de truyen - goi execute() la POST that, y het job tu dong.
    #
    # QoeDataInsufficientError la NGOAI LE DUY NHAT can bat rieng o day - anh
    # xa MAC DINH (api/middleware/error_handler.py) la 202 (dung cho
    # EvaluateCrUseCase, "khong phai loi"), nhung dac ta BUOC 1 endpoint nay
    # muon 422 rieng (request hop le ve cu phap nhung khong xu ly duoc ve
    # nghiep vu luc nay - thieu du lieu QoS). Cac DomainError khac
    # (CrSessionNotFoundError/TramNotFoundError/SaveCellClmApiError) GIU
    # NGUYEN, bubble tu nhien len global handler (404/404/503 - da dang ky san
    # trong error_handler.py/domain/errors.py), KHONG can try/except rieng o
    # day - dung pattern preview_cr() trong api/routers/cr.py.
    try:
        result = await use_case.execute(body.session_id, body.cell_name)
    except QoeDataInsufficientError as exc:
        # detail thuan (khong phai {error_code,message,session_id} cua
        # DomainError global handler) - dung CHUNG format voi qos.py
        # (HTTPException 422 rieng), da co tien le trong module nay.
        raise HTTPException(status_code=422, detail="Chua du du lieu danh gia") from exc

    if result.trang_thai == "DAT_KHONG_XUAT":
        # Cell DAT tieu chi QoS - KHONG goi CTS, KHONG tao cr_phieu (xem
        # application/xuat_phieu_use_case.py).
        #
        # SUA 04092026: message lay tu result.ly_do_dat (use case dat cau, vi
        # no biet VE NAO cua luat lam cell dat). Truoc day router hardcode
        # "chenh lech TB truoc-sau <= 0.2" cho MOI truong hop - sai voi cell
        # dat nho ve avg_after >= 4.0, va nguoi doc thay "chenh 0.50 ma bao
        # <= 0.2" thi tuong he thong mau thuan.
        return XuatPhieuResponse(
            trang_thai=result.trang_thai,
            message=result.ly_do_dat or "Cell dat tieu chi QoS - khong can xuat phieu",
        )

    if result.already_exists:
        # BUOC 1 (use case) da check trung, phat hien phieu SUCCESS co san -
        # KHONG goi lai CTS, tra ve NGUYEN phieu_id cu.
        return XuatPhieuResponse(
            trang_thai=result.trang_thai,
            phieu_id=result.phieu_id,
            message="Cell nay da duoc xuat phieu thanh cong truoc do",
        )

    # Da THAT SU goi CTS lan nay - SUCCESS (co phieu_id) hoac FAILED (CTS bao
    # loi, cts_response.message la ly do that tu CTS - "khong nuot loi", dung
    # BUOC 1 dac ta). message o day CHI mang canh bao ghi DB (BUOC 2, thuong
    # la None) - loi CTS that nam trong cts_response, KHONG lap lai o day.
    return XuatPhieuResponse(
        trang_thai=result.trang_thai,
        phieu_id=result.phieu_id,
        cts_response=result.cts_response,
        message=result.db_save_warning,
    )


@router.delete("/phieu/{phieu_row_id}", response_model=XoaPhieuResponse)
async def xoa_phieu(
    phieu_row_id: int,
    use_case: XoaPhieuUseCase = Depends(get_xoa_phieu_use_case),
) -> XoaPhieuResponse:
    """Xoa 1 dong cr_phieu de cell quay lai "chua xu ly" va xuat lai duoc.

    phieu_row_id la KHOA CHINH cr_phieu.id (so thu tu dong trong DB), KHONG
    phai phieu_id cua CTS - 2 thu khac nhau va deu la so, de nham.

    SUCCESS -> 409 (XoaPhieuKhongHopLeError bubble len global handler).
    """
    ket_qua = await use_case.execute(phieu_row_id)
    if not ket_qua:
        # Use case tra {} khi khong tim thay. 404 tho (HTTPException) chu khong
        # tao DomainError moi: khong co luat nghiep vu nao o day, chi la
        # "khong co dong nao mang id nay".
        raise HTTPException(status_code=404, detail=f"Khong tim thay cr_phieu id={phieu_row_id}")
    return XoaPhieuResponse(
        id=ket_qua["id"],
        da_xoa=True,
        cell_name=ket_qua["cell_name"],
        trang_thai=ket_qua["trang_thai"],
        message=ket_qua.get("message"),
    )
