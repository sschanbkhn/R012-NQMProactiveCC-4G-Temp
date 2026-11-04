"""
GetSessionsUseCase — list session voi filter/paging + 6 truong tien trinh.
Tu: ARCHITECTURE.md Section 3.4 (IGetSessionsUseCase); API_CONTRACTS.md GET /sessions;
TASK_LIST.md C2.3

Loc/phan trang/join tram_name/dem 3 con so nam trong CrSessionRepo.list()
(adapters/postgres/cr_session_repo.py). File nay giu 3 thu con lai - deu la
NGHIEP VU nen khong duoc de o repo hay o router:
  - ngay du kien xuat phieu (executed_at + XUAT_PHIEU_AFTER_DAYS)
  - con bao nhieu ngay (so voi hom nay, GMT+7)
  - buoc hien tai (1/2/4)

NGUYEN TAC (yeu cau truc tiep user 16082026): BE tinh san TAT CA, FE KHONG can
biet quy tac nghiep vu nao - khong can biet XUAT_PHIEU_AFTER_DAYS=8, khong can
tu tru ngay, khong can tu suy buoc tu status.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.inbound.use_case_ports import IGetSessionsUseCase
from domain.ports.outbound.repo_ports import (
    ICellParamsRepo,
    ICrAffectedCellsRepo,
    ICrSessionRepo,
    Page,
    SessionFilter,
)
from domain.services.danh_gia_dieu_kien_cr_moi import gan_nhan_ngoai_dieu_kien_moi

# Dung LAI tu xuat_phieu_use_case, KHONG dinh nghia lai (application ->
# application, hop le theo ARCHITECTURE.md SS9):
#   XUAT_PHIEU_AFTER_DAYS - moc "sau CR bao nhieu ngay thi xuat phieu". Doc tu
#       os.getenv o module do; hardcode 8 o day se lam UI va job lech nhau khi
#       van hanh doi bien moi truong.
#   _to_gmt7 - quy doi UTC -> gio VN. Viet lai logic mui gio lan 2 chinh la loi
#       da gap khi lam GET /jobs/runs.
from application.xuat_phieu_use_case import XUAT_PHIEU_AFTER_DAYS, _to_gmt7  # noqa: PLC2701

# 3 status coi la "dung o buoc 1". PHAI khop _BUOC_1_STATUS trong
# adapters/postgres/cr_session_repo.py (bo loc SQL) - lech nhau se cho ra danh
# sach loc mot dang nhung cot "buoc" hien mot dang khac.
# PARTIAL_SUCCESS KHONG nam o day: CR da chay xong, chi mot so DN hong - xu
# nhu DONE (di tiep sang buoc cho KPI), KHONG dung o buoc 1 nhu CR loi han.
# THEM KHONG_CHAY 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") -
# tach tu FAILED nhung VAN la "CR chua xong" ve mat tien trinh, dung o buoc 1
# giong het FAILED (CHI khac nguyen nhan hien thi, khong khac buoc).
_BUOC_1_STATUS = (CrStatus.FAILED, CrStatus.KHONG_CHAY, CrStatus.RUNNING)


@dataclass
class SessionTienTrinh:
    """1 dong cua GET /sessions: entity + 3 gia tri tinh san.

    3 con so dem (so_cell_anh_huong/so_phieu_da_xuat/so_cell_cho_xuat_tay) nam
    TREN entity (repo dien qua subquery), khong lap lai o day.
    """

    session: CrSession
    ngay_du_kien_xuat_phieu: date | None
    con_bao_nhieu_ngay: int | None
    buoc_hien_tai: int
    # THEM 04/10/2026 (quyet dinh 04/10/2026, CHI DOC) - so cell CHAY CR cua
    # session nay dang "ngoai dieu kien moi" (band/sector) - xem
    # domain/services/danh_gia_dieu_kien_cr_moi.py. 0 mac dinh cho session
    # chua chay CR (khong co cell_params nao).
    so_cell_ngoai_dieu_kien_moi: int = 0


def tinh_buoc_hien_tai(session: CrSession) -> int:
    """Buoc hien tai trong tien trinh 4 buoc (CR -> cho KPI -> danh gia -> xuat phieu).

    KHONG BAO GIO tra ve 3. Buoc 3 ("dang danh gia") la trang thai THOANG QUA
    ben trong 1 luot chay job xuat phieu: job danh gia cell roi xuat phieu ngay
    trong cung mot ham, khong co cot nao trong cr_session ghi lai "dang o giua
    2 viec do". Muon hien duoc buoc 3 thi phai them cot moc thoi gian rieng -
    ngoai pham vi hien tai. FE cu ve 4 buoc va hieu rang buoc 3 se khong sang.
    """
    # Thu tu kiem tra QUAN TRONG: status xet TRUOC xuat_phieu_at. Session FAILED
    # ma van co xuat_phieu_at (khong nen xay ra nhung khong co rang buoc DB nao
    # cam) phai hien la "CR loi", khong phai "da xuat phieu xong".
    if session.status in _BUOC_1_STATUS:
        return 1  # CR dang chay hoac da loi - dung o buoc 1

    # KHONG_DU_DU_LIEU (cach C, 16082026) la TRANG THAI CUOI: session da ket
    # thuc, KHONG bao gio duoc quet lai (execute_all_pending chi lay DONE +
    # EVAL_PENDING). Phai xet TRUOC xuat_phieu_at vi no cung co
    # xuat_phieu_at IS NULL - roi xuong nhanh duoi se ra buoc 2 "dang cho thu
    # thap KPI" va hien "dang cho" MAI MAI tren UI. Do dung la cai loi ma cach C
    # sinh ra khi thay EVAL_PENDING bang trang thai cuoi.
    if session.status == CrStatus.KHONG_DU_DU_LIEU:
        return 4  # da ket thuc - khong ket luan duoc, khong cho gi nua

    if session.xuat_phieu_at is None:
        return 2  # CR xong, dang cho thu thap KPI 7 ngay
    return 4  # da xuat phieu xong


def tinh_ngay_du_kien(session: CrSession) -> date | None:
    """Ngay du kien job quet de xuat phieu = NGAY CR (lich GMT+7) + AFTER_DAYS.

    None khi chua chay CR (executed_at NULL) - chua co moc nao de cong.
    """
    if session.executed_at is None:
        return None
    # .date() PHAI lay SAU khi quy ve GMT+7: executed_at luu UTC (TIMESTAMPTZ),
    # lay .date() thang tren UTC se lech 1 ngay voi CR chay trong khung UTC
    # 17:00-23:59 - dung bug C1.4-fix8 da sua o EvaluateCrUseCase.
    return _to_gmt7(session.executed_at).date() + timedelta(days=XUAT_PHIEU_AFTER_DAYS)


def hom_nay_vn(bay_gio: datetime | None = None) -> date:
    """Hom nay theo lich VN. bay_gio truyen vao de test khong phu thuoc dong ho may."""
    return _to_gmt7(bay_gio or datetime.now(timezone.utc)).date()


class GetSessionsUseCase(IGetSessionsUseCase):
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        # 2 repo THEM 04/10/2026 (quyet dinh 04/10/2026, CHI DOC) - tinh
        # so_cell_ngoai_dieu_kien_moi. Optional (mac dinh None) de test cu/noi
        # goi cu KHONG truyen 2 tham so nay KHONG phai sua - luc do field moi
        # tu nhien la 0 cho MOI session (xem vong lap trong execute()), giu
        # dung nguyen tac "them field moi KHONG doi hanh vi cu".
        cell_params_repo: ICellParamsRepo | None = None,
        affected_cells_repo: ICrAffectedCellsRepo | None = None,
    ):
        self._session_repo = session_repo
        self._cell_params_repo = cell_params_repo
        self._affected_cells_repo = affected_cells_repo

    async def _dem_ngoai_dieu_kien_moi(self, session: CrSession) -> int:
        # THEM 04/10/2026 - xem chu y day du o __init__. Chi tinh khi CA 2 repo
        # deu co (test/caller cu khong truyen) VA session DA chay CR
        # (executed_at khong None - session chua chay thi cell_params chac
        # chan rong, goi 2 query vo ich).
        if (
            self._cell_params_repo is None
            or self._affected_cells_repo is None
            or session.executed_at is None
        ):
            return 0
        cell_params = await self._cell_params_repo.get_by_cr_session_id(session.id)
        if not cell_params:
            return 0
        affected_cells = await self._affected_cells_repo.get_by_cr_session_id(session.id)
        dist_name_theo_cell = {
            c["cell_name"]: c["dist_name"] for c in affected_cells if c.get("dist_name")
        }
        nhan = gan_nhan_ngoai_dieu_kien_moi(cell_params, dist_name_theo_cell)
        return sum(1 for ly_do in nhan.values() if ly_do)

    async def execute(self, filters: SessionFilter, bay_gio: datetime | None = None) -> Page:
        hom_nay = hom_nay_vn(bay_gio)

        if filters.qua_han:
            # Dich Y DINH "qua_han=true" thanh NGAY MOC cu the roi moi dua xuong
            # repo - hang so nghiep vu khong duoc ro ri xuong adapters/.
            #   ngay_cr + AFTER_DAYS < hom nay  <=>  ngay_cr < hom nay - AFTER_DAYS
            # Chuyen ve ve phai de phep cong nam o Python, SQL chi con so sanh
            # DATE voi 1 tham so - khong phu thuoc cach Postgres cong interval.
            filters = replace(
                filters, qua_han_truoc_ngay=hom_nay - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
            )

        page = await self._session_repo.list(filters)

        items = []
        for s in page.items:
            ngay_du_kien = tinh_ngay_du_kien(s)
            items.append(
                SessionTienTrinh(
                    session=s,
                    ngay_du_kien_xuat_phieu=ngay_du_kien,
                    # AM = da qua han bao nhieu ngay. None khi chua co ngay du
                    # kien - KHONG dung 0, vi 0 co nghia "dung hom nay".
                    con_bao_nhieu_ngay=(ngay_du_kien - hom_nay).days if ngay_du_kien else None,
                    buoc_hien_tai=tinh_buoc_hien_tai(s),
                    so_cell_ngoai_dieu_kien_moi=await self._dem_ngoai_dieu_kien_moi(s),
                )
            )
        return Page(items=items, total=page.total)
