"""
Test bao ve _ERROR_CODE_STATUS (api/middleware/error_handler.py) - MOI subclass
cua DomainError phai co entry trong dict map.

VI SAO CAN TEST NAY (19092026, sau khi tach CR_CDS_NO_NEIGHBOR_DATA):
Dict map tra theo KHOA CHUOI error_code:

    status_code = _ERROR_CODE_STATUS.get(exc.error_code, 500)

KHONG phai isinstance. Nghia la mot error_code moi KHONG tu thua status cua
class cha qua quan he ke thua - thieu entry thi roi vao mac dinh 500 mot cach
IM LANG. 500 = "loi khong xac dinh, bug cua he thong" trong khi that ra day la
loi nghiep vu da duoc luong truoc: nguoi dung bi bao sai ban chat van de, con
nguoi truc thi di tim bug khong ton tai.

Middleware KHONG the tu phat hien viec nay (no chi thay 1 chuoi khong co trong
dict), va khong test API nao di qua het 16 error_code. Nen cho duy nhat bat
duoc la o day.
"""

from api.middleware.error_handler import _ERROR_CODE_STATUS  # noqa: PLC2701
from domain.errors import DomainError


def _moi_subclass(cls: type) -> set[type]:
    """Toan bo subclass cua cls, DE QUY (ke ca subclass cua subclass).

    __subclasses__() chi tra ve con TRUC TIEP - neu sau nay co ai tao
    class XyzError(CdsApiError) thi ban khong de quy se bo sot dung cai
    class moi ma test nay sinh ra de canh gac.

    Luu y: __subclasses__() chi thay class DA duoc import. Hien tai CA 16
    class deu nam trong domain/errors.py (da kiem 19092026) nen import
    DomainError o dau file la du. Neu mai nay co class dinh nghia o module
    khac, module do phai duoc import truoc khi test chay - neu khong, test
    se PASS oan vi khong nhin thay class do.
    """
    ket_qua = set()
    for con in cls.__subclasses__():
        ket_qua.add(con)
        ket_qua |= _moi_subclass(con)
    return ket_qua


def test_moi_domain_error_deu_co_entry_trong_map():
    # error_code duoc hardcode trong __init__ cua tung subclass (khong phai
    # class attribute) nen phai KHOI TAO moi doc duoc. Moi subclass hien tai
    # deu co chu ky (message, **context) - class moi lech chu ky se lam cho
    # nay nem TypeError, cung la mot tin hieu can nguoi nhin lai.
    thieu = {
        cls.__name__: cls("test").error_code
        for cls in _moi_subclass(DomainError)
        if cls("test").error_code not in _ERROR_CODE_STATUS
    }

    # Liet ke HET trong 1 lan chay (khong assert trong vong lap de dung o
    # class dau tien) - nguoi sua thay ngay day du cai gi con thieu.
    assert not thieu, (
        "Cac DomainError sau KHONG co entry trong _ERROR_CODE_STATUS "
        f"-> se tra 500 im lang: {thieu}. Them entry vao "
        "api/middleware/error_handler.py, hoac neu co y de no la 500 that "
        "thi khai bao tuong minh (vd XML_BUILD_ERROR: 500)."
    )
