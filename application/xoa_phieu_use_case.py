"""
XoaPhieuUseCase — xoa MEM 1 dong cr_phieu de cell "coi nhu da xu ly xong, khong
con hien/dem o dau nua".
Tu: yeu cau truc tiep user 20082026; SUA 04/10/2026 (quyet dinh 04/10/2026,
yeu cau truc tiep user) - XOA MEM thay the HARD DELETE cu.

=== SUA 04/10/2026: XOA MEM, KHONG CON LA "coi nhu chua co gi, xuat lai duoc" ===
Ban cu (hard delete) coi xoa la "undo xong cell quay ve chua xu ly, co the xuat
lai". Quyet dinh MOI dao nguoc y nay: phieu da xoa la QUYET DINH CUOI CUNG cua
nguoi van hanh (vd xac dinh phieu rac/sai), KHONG BAO GIO duoc hien lai VA
KHONG BAO GIO duoc tao lai - XuatPhieuUseCase.execute() tu choi 409 neu ai do
(nguoi hoac job tu dong) thu xuat lai dung cell nay (xem domain/errors.py::
PhieuDaXoaError). Dong cr_phieu VAN CON trong bang (chi danh dau deleted_at)
chinh la co che thuc hien dieu do - chu KHONG phai de "khoi phuc" duoc.

=== VI SAO CHAN SUCCESS ===
SUCCESS nghia la phieu DA nam ben CTS that va co phieu_id. Xoa dong o DB
KHONG xoa duoc phieu ben CTS - chi lam mat dau vet phia minh, roi lan sau he
thong tuong cell nay chua xuat va xuat TRUNG (CTS se bao "Bad Cell ... dang xu
ly cua thang ..." - da gap that o cr_phieu id=82).

=== XOA 2 LAN ===
Lan 2 KHONG goi lai repo.xoa() (se khong lam gi vi WHERE deleted_at IS NULL -
xem CrPhieuRepo.xoa()) - phat hien TRUOC qua phieu["deleted_at"] da co san tu
get_by_id(), tra ve cung hinh dang ket qua kem message bao "da xoa truoc do"
thay vi am tham coi nhu thanh cong lan nua.
"""

import logging

from domain.errors import XoaPhieuKhongHopLeError
from domain.ports.outbound.repo_ports import ICrPhieuRepo

logger = logging.getLogger(__name__)

# Blacklist 1 gia tri (khac XoaSessionUseCase dung whitelist) - CO CHU DICH:
# moi trang thai KHAC SUCCESS deu la "chua len duoc CTS" (FAILED / PENDING /
# KHONG_XUAT_*), va cac trang thai KHONG_XUAT_* moi them gan day cho thay
# nhom nay con no ra tiep. Whitelist o day se phai sua moi lan them 1 trang
# thai "khong xuat" moi, va QUEN sua = chan nham thu dang le xoa duoc.
_TRANG_THAI_KHONG_XOA_DUOC = "SUCCESS"


class XoaPhieuUseCase:
    def __init__(self, cr_phieu_repo: ICrPhieuRepo):
        self._cr_phieu_repo = cr_phieu_repo

    async def execute(self, phieu_row_id: int) -> dict:
        """phieu_row_id la KHOA CHINH cr_phieu.id, KHONG phai phieu_id cua CTS.

        Tra {"id", "cell_name", "trang_thai", "message"} cua dong. "message"
        None o lan xoa DAU TIEN, co gia tri "da xoa truoc do" (THEM 04/10/2026)
        neu dong nay DA bi xoa tu truoc - xem docstring dau file muc "XOA 2 LAN".
        """
        phieu = await self._cr_phieu_repo.get_by_id(phieu_row_id)
        if phieu is None:
            # KHONG raise CrSessionNotFoundError (sai doi tuong) - router tu
            # map sang 404 vi day la truong hop duy nhat tra None.
            return {}

        if phieu["trang_thai"] == _TRANG_THAI_KHONG_XOA_DUOC:
            raise XoaPhieuKhongHopLeError(
                f"Phieu {phieu['phieu_id']} da len CTS, khong xoa duoc o day. "
                "Lien he team CTS de xoa ben do.",
                id=phieu_row_id,
                phieu_id=phieu["phieu_id"],
            )

        # THEM 04/10/2026 - da xoa tu truoc (deleted_at khong NULL). KHONG goi
        # lai repo.xoa() (WHERE deleted_at IS NULL se tra 0, khong lam gi) -
        # phat hien TRUOC o day de tra ve message ro rang thay vi im lang coi
        # nhu vua xoa thanh cong.
        da_xoa_truoc_do = phieu.get("deleted_at") is not None
        if not da_xoa_truoc_do:
            await self._cr_phieu_repo.xoa(phieu_row_id)
            logger.warning(
                "DA XOA (MEM) dong cr_phieu",
                extra={
                    "id": phieu_row_id,
                    "cr_session_id": phieu["cr_session_id"],
                    "cell_name": phieu["cell_name"],
                    "trang_thai": phieu["trang_thai"],
                },
            )
        return {
            "id": phieu_row_id,
            "cell_name": phieu["cell_name"],
            "trang_thai": phieu["trang_thai"],
            "message": "Phieu nay da duoc xoa truoc do" if da_xoa_truoc_do else None,
        }
