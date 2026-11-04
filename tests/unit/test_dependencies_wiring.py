"""
Kiem MOI factory trong infrastructure/dependencies.py THUC SU CHAY DUOC.
Tu: loi 500 that tren server 20082026.

=== VI SAO CAN FILE NAY ===
Commit b3e88de xoa tham so chart_use_case khoi GetSessionDetailUseCase.__init__
va xoa ca GetEvaluationChartUseCase, nhung QUEN sua LOI GOI trong
get_session_detail_use_case():

    return GetSessionDetailUseCase(session_repo, cell_repo, chart_use_case, ...)

Bien chart_use_case khong con ton tai -> NameError. Nhung:
  - `import infrastructure.dependencies` VAN OK: NameError chi no khi THAN HAM
    chay, khong phai luc import. Moi lan kiem "import OK" deu qua.
  - `pytest` VAN XANH: test_sessions_detail_router.py ghi de HAN factory nay
    bang dependency_overrides -> than ham that KHONG BAO GIO duoc goi.
Ket qua: 500 chi lo ra khi nguoi dung bam vao man hinh chi tiet tren server.

=== BAI HOC (lan thu 2 gap kieu nay) ===
Lan truoc: fixture "Provision OK" khang dinh mot hanh vi SAI, test xanh trong
khi code that hong. Cung mot goc: MOCK QUA SAU thi chi con kiem duoc HOP DONG
CUA MOCK, khong kiem duoc code that co chay khong. Mock cang gan endpoint,
vung code that duoc bao ve cang nho.

File nay di huong nguoc lai: KHONG mock use case nao ca, chi thay DUY NHAT
lop I/O tan cung (AsyncSession) - de toan bo day wiring that phai chay.
"""

import inspect
from unittest.mock import AsyncMock

import pytest

import infrastructure.dependencies as deps


def _factory_can_kiem():
    """Moi ham get_*_use_case / get_*_repo / get_*_gateway trong dependencies.py.

    Lay bang inspect chu KHONG liet ke tay: liet ke tay thi factory THEM MOI
    sau nay se khong duoc kiem, ma do dung la truong hop de sot nhat.
    """
    ra = []
    for ten, ham in inspect.getmembers(deps, inspect.isfunction):
        if ham.__module__ != deps.__name__:
            continue
        if ten.startswith("get_") and (
            ten.endswith("_use_case") or ten.endswith("_repo") or ten.endswith("_gateway")
        ):
            ra.append((ten, ham))
    return sorted(ra)


def _doi_so_gia(ham):
    """Thay moi tham so Depends(...) bang mock. Tra kwargs de goi ham.

    Muc tieu KHONG phai kiem cac collaborator dung hay sai (unit test rieng lo
    viec do) - ma la kiem THAN HAM co chay het khong: sai ten bien, sai so
    tham so, goi ham da xoa... deu lo ra ngay.
    """
    return {ten: AsyncMock() for ten in inspect.signature(ham).parameters}


@pytest.mark.parametrize("ten,ham", _factory_can_kiem(), ids=lambda x: x if isinstance(x, str) else "")
def test_factory_chay_duoc_khong_NameError(ten, ham):
    ket_qua = ham(**_doi_so_gia(ham))
    assert ket_qua is not None, f"{ten}() tra ve None"


def test_co_bat_duoc_factory_de_kiem():
    # Chan truong hop _factory_can_kiem() tra rong (vd doi quy uoc dat ten) -
    # luc do moi test tren se "pass" ma khong kiem gi ca.
    assert len(_factory_can_kiem()) >= 15
