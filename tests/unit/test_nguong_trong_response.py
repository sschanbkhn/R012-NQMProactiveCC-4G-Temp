"""Test: 2 endpoint qos-cells/qoe-cells tra nguong LAY TU HANG SO domain (04092026).

=== NGUYEN TAC CUA BO TEST NAY ===
KHONG duoc go so (0.5 / 3.0 / 5) vao test. Neu go, test se chi chung minh
"response khop voi so toi vua go" - dung cai benh dang chua: mot ban sao nua cua
hang so, va no cung se troi y het.
Test doc THANG hang so tu module nghiep vu, nen khi doi hang so o do thi:
  - response doi theo  -> test VAN XANH (dung y muon)
  - response khong doi -> test DO ngay (bat duoc luc ban sao bat dau troi)
"""

import pytest

from api.schemas.qos_schemas import NguongDanhGia
from application.get_qoe_cells_use_case import _QOE_CELL_THRESHOLD_DELTA  # noqa: PLC2701
from application.xuat_phieu_use_case import _XUAT_PHIEU_QOS_THRESHOLD_DELTA  # noqa: PLC2701
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, MUC_TOI_THIEU


def _nguong_qos() -> NguongDanhGia:
    """Dung y HET cach api/routers/qos.py dien nguong.

    SUA 03/10/2026: _XUAT_PHIEU_QOS_THRESHOLD_DELTA gio DA la so duong - KHONG
    con doi dau o day (truoc day hang so goc la am nen phai doi dau)."""
    return NguongDanhGia(
        delta_toi_da=_XUAT_PHIEU_QOS_THRESHOLD_DELTA,
        muc_toi_thieu=MUC_TOI_THIEU,
        so_ngay_toi_thieu=MIN_DAYS_REQUIRED,
    )


def _nguong_qoe() -> NguongDanhGia:
    return NguongDanhGia(
        delta_toi_da=_QOE_CELL_THRESHOLD_DELTA,
        muc_toi_thieu=MUC_TOI_THIEU,
        so_ngay_toi_thieu=MIN_DAYS_REQUIRED,
    )


# ==================== Lay dung tu hang so, khong go so ====================


def test_qos_nguong_lay_dung_tu_hang_so():
    n = _nguong_qos()
    # so sanh voi CHINH hang so, khong voi so go tay
    assert n.delta_toi_da == _XUAT_PHIEU_QOS_THRESHOLD_DELTA
    assert n.muc_toi_thieu == MUC_TOI_THIEU
    assert n.so_ngay_toi_thieu == MIN_DAYS_REQUIRED


def test_qoe_nguong_lay_dung_tu_hang_so():
    n = _nguong_qoe()
    assert n.delta_toi_da == _QOE_CELL_THRESHOLD_DELTA
    assert n.muc_toi_thieu == MUC_TOI_THIEU
    assert n.so_ngay_toi_thieu == MIN_DAYS_REQUIRED


# ==================== Dau cua delta_toi_da ====================


def test_delta_toi_da_la_so_DUONG():
    """SUA 03/10/2026: hang so trong code GIO DA DUONG tu goc (0.5) - xem
    domain/services/evaluation_service.py muc "SUA 03/10/2026". Response CHI
    con chuyen tiep nguyen gia tri, KHONG con buoc doi dau nao (truoc day
    hang so la am, response phai doi dau thanh duong cho FE)."""
    assert _XUAT_PHIEU_QOS_THRESHOLD_DELTA > 0, "hang so gio phai la so duong"
    assert _nguong_qos().delta_toi_da > 0, "response phai tra so duong"
    # va phai DUNG BANG hang so (khong qua buoc bien doi nao)
    assert _nguong_qos().delta_toi_da == _XUAT_PHIEU_QOS_THRESHOLD_DELTA


def test_qoe_delta_toi_da_cung_la_so_DUONG():
    assert _QOE_CELL_THRESHOLD_DELTA > 0
    assert _nguong_qoe().delta_toi_da == _QOE_CELL_THRESHOLD_DELTA


# ==================== Doi hang so -> response doi theo ====================


def test_doi_hang_so_thi_response_doi_theo(monkeypatch):
    """Chan chot chinh: doi hang so o module nghiep vu thi nguong tra ra phai doi.

    Neu ai do sau nay go cung so vao router, test nay se DO - do la muc dich.
    """
    import domain.services.evaluation_service as es

    monkeypatch.setattr(es, "MUC_TOI_THIEU", 2.5)
    monkeypatch.setattr(es, "MIN_DAYS_REQUIRED", 9)

    # doc lai qua module (khong dung bien da import o dau file) de thay gia tri moi
    n = NguongDanhGia(
        delta_toi_da=_XUAT_PHIEU_QOS_THRESHOLD_DELTA,
        muc_toi_thieu=es.MUC_TOI_THIEU,
        so_ngay_toi_thieu=es.MIN_DAYS_REQUIRED,
    )
    assert n.muc_toi_thieu == 2.5
    assert n.so_ngay_toi_thieu == 9


def test_qos_va_qoe_dung_nguong_delta_RIENG():
    """2 chi so co hang so delta RIENG - khong duoc gop lam mot.

    Hien tai 2 gia tri BANG NHAU (0.5) nen so sanh gia tri se khong phat hien
    duoc neu ai do lam router qoe doc nham hang so cua qos. Vi vay khang dinh o
    day la 2 hang so PHAI ton tai doc lap, con gia tri co the trung.
    """
    import application.get_qoe_cells_use_case as qoe_uc
    import application.xuat_phieu_use_case as qos_uc

    assert hasattr(qoe_uc, "_QOE_CELL_THRESHOLD_DELTA")
    assert hasattr(qos_uc, "_XUAT_PHIEU_QOS_THRESHOLD_DELTA")


# ==================== Schema co du 3 truong ====================


def test_schema_co_dung_3_truong():
    assert set(NguongDanhGia.model_fields) == {"delta_toi_da", "muc_toi_thieu", "so_ngay_toi_thieu"}


def test_ca_2_response_deu_co_truong_nguong():
    from api.schemas.qoe_schemas import QoeCellsResponse
    from api.schemas.qos_schemas import QosCellsResponse

    assert "nguong" in QosCellsResponse.model_fields
    assert "nguong" in QoeCellsResponse.model_fields
    # cung KIEU - 2 ban dinh nghia rieng se lech nhau khi 1 ben doi
    assert QosCellsResponse.model_fields["nguong"].annotation is NguongDanhGia
    assert QoeCellsResponse.model_fields["nguong"].annotation is NguongDanhGia


@pytest.mark.parametrize("ten", ["delta_toi_da", "muc_toi_thieu", "so_ngay_toi_thieu"])
def test_moi_truong_deu_bat_buoc(ten):
    """Khong truong nao co default: thieu 1 cai la loi ngay luc dung response,
    khong de lot ra FE thanh null roi FE lai quay ve hardcode."""
    assert NguongDanhGia.model_fields[ten].is_required()
