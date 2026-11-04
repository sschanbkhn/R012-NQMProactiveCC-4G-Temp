"""
Schemas cho GET /sessions/{id}/qoe-cells.
Tu: yeu cau truc tiep user 16082026 (QoE danh gia PER-CELL).
"""

from datetime import date

from pydantic import BaseModel

from api.schemas.qos_schemas import CuaSoNgay, NguongDanhGia


class QoeCellItem(BaseModel):
    cell_name: str

    # None khi cell khong co ngay nao co du lieu (CEM bo qua cell khong co so
    # lieu) - KHONG dung 0.0, vi 0.0 la mot diem QoE hop le ve mat kieu du lieu.
    avg_before: float | None = None
    avg_after: float | None = None
    # avg_before - avg_after. DUONG = TUT (sua 03/10/2026, truoc day AM = tut).
    # None khi thieu 1 trong 2 ve.
    delta: float | None = None

    # So ngay THUC TE co du lieu trong cua so 7 ngay (khong phai luon = 7).
    # < 5 (MIN_DAYS_REQUIRED) -> ket_qua = INSUFFICIENT_DATA.
    so_ngay_before: int
    so_ngay_after: int

    # "PASS" | "FAIL" | "INSUFFICIENT_DATA" - cua RIENG cell nay. Cell thieu du
    # lieu KHONG lam hong cac cell khac trong cung response.
    ket_qua: str

    # 2 truong THAM KHAO (khong tham gia phan quyet) - trung binh CHE duoc ngay
    # mat dich vu, vd [5,5,5,5,5,5,1] co avg 4.43 nen PASS nhung co 1 ngay diem 1.
    diem_thap_nhat_sau: float | None = None
    so_ngay_dat_sau: int = 0


class QoeCellsResponse(BaseModel):
    cr_session_id: int
    # 3 truong cua so (04092026) - GIONG HET QosCellsResponse de FE doi chieu
    # duoc 2 bang. Xem ly do day du o api/schemas/qos_schemas.py.
    # Tai dung CuaSoNgay tu qos_schemas thay vi dinh nghia lai: 2 ban se lech
    # nhau khi 1 ben doi.
    ngay_cr: date
    cua_so_before: CuaSoNgay
    cua_so_after: CuaSoNgay
    # THEM 18/10/2026 (MOT NGUON SO LIEU) - ngay (GMT+7) chup snapshot ma bang
    # nay dang doc; FE ghi "So lieu tai thoi diem danh gia dd/mm". None = so
    # lieu goi CTS/CEM truc tiep (session chua danh gia / chua co snapshot).
    ngay_chup_snapshot: date | None = None
    # nguong dang ap dung - TAI DUNG NguongDanhGia tu qos_schemas (cung ly do da tai
    # dung CuaSoNgay: 2 ban dinh nghia rieng se lech nhau khi 1 ben doi)
    nguong: NguongDanhGia
    total: int
    data: list[QoeCellItem]
