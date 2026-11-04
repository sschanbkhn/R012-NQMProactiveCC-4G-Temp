"""
XoaSessionUseCase — xoa 1 cr_session FAILED/KHONG_CHAY va toan bo dong con.
Tu: yeu cau truc tiep user 20082026, mo rong 16/10/2026 (THEM KHONG_CHAY).

=== VI SAO CHI CHO XOA FAILED/KHONG_CHAY ===
Session DONE va PARTIAL_SUCCESS co tram DA DOI THAM SO RF THAT tren thiet bi
(rsboost/qrxlevmin da duoc provision xuong NetAct). Dong cr_session kem
cr_log/cell_params la BANG CHUNG DUY NHAT ve viec do - xoa di thi sau nay
khong ai truy duoc vi sao RF cua tram lech so voi thiet ke ban dau, va cung
khong biet phai rollback ve gia tri nao.

FAILED = 0 DN thanh cong = KHONG tram nao doi gi -> khong co bang chung nao de
mat, xoa an toan. KHONG_CHAY (THEM 16/10/2026) con "sach" hon FAILED: loi xay
ra TRUOC buoc 13 (SSH) nen KHONG MOT lenh nao tung duoc gui len NetAct - cung
LY DO xoa an toan nhu FAILED, ap dung CHO CA 2.

PARTIAL_SUCCESS bi chan DU chi 1/4 DN thanh cong: 1 tram da doi that van la
1 tram can truy duoc.
"""

import logging

from domain.entities.cr_session import CrStatus
from domain.errors import CrSessionNotFoundError, XoaSessionKhongHopLeError
from domain.ports.outbound.repo_ports import ICrSessionRepo

logger = logging.getLogger(__name__)

# Whitelist (khong phai blacklist): them trang thai moi vao he thong thi mac
# dinh KHONG xoa duoc, phai co nguoi chu dong them vao day - an toan hon "tru
# DONE va PARTIAL_SUCCESS ra". THEM CrStatus.KHONG_CHAY 16/10/2026 (yeu cau
# truc tiep user) - xem ly do o dau file.
_TRANG_THAI_XOA_DUOC = (CrStatus.FAILED, CrStatus.KHONG_CHAY)


class XoaSessionUseCase:
    def __init__(self, session_repo: ICrSessionRepo):
        self._session_repo = session_repo

    async def execute(self, session_id: int) -> dict:
        """Tra {ten_bang: so_dong_da_xoa}. Raise neu khong xoa duoc."""
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={session_id} khong ton tai", session_id=session_id
            )

        if session.status not in _TRANG_THAI_XOA_DUOC:
            raise XoaSessionKhongHopLeError(
                _thong_bao_tu_choi(session),
                session_id=session_id,
                status=session.status.value,
            )

        # rollback_of_id la FK TU cr_session TRO VE cr_session (ON DELETE NO
        # ACTION). Neu co session khac tro toi thi xoa se FK violation. CHAN
        # tai day thay vi de Postgres nem loi tho, va KHONG tu set NULL dum -
        # do la sua du lieu cua MOT SESSION KHAC ma nguoi dung khong yeu cau.
        so_rollback = await self._session_repo.dem_session_rollback_tu(session_id)
        if so_rollback > 0:
            raise XoaSessionKhongHopLeError(
                f"Session {session_id} dang la nguon rollback cua {so_rollback} session khac - "
                "xoa cac session do truoc.",
                session_id=session_id,
                so_session_rollback=so_rollback,
            )

        so_dong = await self._session_repo.xoa_cascade(session_id)
        logger.warning(
            "DA XOA cr_session FAILED/KHONG_CHAY",
            extra={"cr_session_id": session_id, "tram_id": session.tram_id, "so_dong": so_dong},
        )
        return so_dong


def _thong_bao_tu_choi(session) -> str:
    """Thong bao 409 - phai noi RO da co bao nhieu tram doi RF that.

    Con so n/m la thu quyet dinh: nguoi doc can biet "co that su co tram nao
    da doi khong" chu khong chi biet "status khac FAILED/KHONG_CHAY".
    """
    n = session.so_cell_thanh_cong
    m = session.so_cell_tong
    if n is None or m is None:
        # Session cu (truoc migration 4ae6f4d7503b) khong co 2 con so nay.
        # KHONG doan la 0 - "0 tram da doi" la cau NGUY HIEM neu sai, no lam
        # nguoi doc tuong xoa duoc.
        phan_dn = "khong ro bao nhieu tram da doi tham so RF (session cu, chua ghi so DN)"
    else:
        phan_dn = f"co {n}/{m} tram da doi tham so RF that"
    return (
        f"Chi xoa duoc session FAILED/KHONG_CHAY. Session nay la {session.status.value}, {phan_dn}."
    )
