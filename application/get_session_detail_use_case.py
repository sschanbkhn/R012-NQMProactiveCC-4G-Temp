"""
GetSessionDetailUseCase — chi tiet 1 session.
Tu: ARCHITECTURE.md Section 3.4 (IGetSessionDetailUseCase); API_CONTRACTS.md
GET /sessions/{id}; TASK_LIST.md C2.4

BO (20082026): qoe_snapshots/qos_snapshots DA XOA khoi response, cung voi
GetEvaluationChartUseCase (file da xoa) va tham so use case chart cua __init__.
Ly do: snapshot gio luu PER-CELL nen 2 mang do phinh 15 lan (15 ngay x so
cell), trong khi FE da thoi doc chung tu 23/07.

(Co y KHONG viet lai nguyen ten bien da xoa o day: quy trinh dong bundle co
buoc grep ten do va doi ket qua = 0 - de lai 1 lan nhac trong comment se lam
buoc kiem do do VINH VIEN, va mot buoc kiem luon do thi se bi bo qua.)
cell_params lay qua ICellParamsRepo.get_by_cr_session_id() (C2.4).

affected_cells them 22072026 (Phuong an B, DA DUYET) - 47 cell Nhanh A qua
ICrAffectedCellsRepo.get_by_cr_session_id(), BEN CANH cell_params (12 cell
Nhanh B) - KHONG thay the, chi cong them.

cr_logs SUA 22072026 (xac nhan voi user) - THAT su doc tu bang cr_log qua
ICrLogRepo.get_by_cr_session_id() (truoc gio LUON RONG vi chua co repo, du
bang DA CO SAN tu B4.4) - de xem lai log tung buoc CR SAU KHI da chay xong
(SSE chi real-time trong RAM, dong tab la mat het).
"""

from domain.errors import CrSessionNotFoundError
from domain.ports.inbound.use_case_ports import (
    CrSessionDetail,
    IGetSessionDetailUseCase,
)
from domain.ports.outbound.repo_ports import (
    ICellParamsRepo,
    ICrAffectedCellsRepo,
    ICrLogRepo,
    ICrSessionRepo,
)


class GetSessionDetailUseCase(IGetSessionDetailUseCase):
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        cell_repo: ICellParamsRepo,
        affected_cells_repo: ICrAffectedCellsRepo,
        cr_log_repo: ICrLogRepo,
    ):
        self._session_repo = session_repo
        self._cell_repo = cell_repo
        self._affected_cells_repo = affected_cells_repo
        self._cr_log_repo = cr_log_repo

    async def execute(self, session_id: int) -> CrSessionDetail:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            raise CrSessionNotFoundError(f"cr_session id={session_id} khong ton tai", session_id=session_id)

        cell_params = await self._cell_repo.get_by_cr_session_id(session_id)
        # Session cu (truoc 22072026) khong co affected_cells (KHONG backfill,
        # xac nhan voi user - du lieu test) - get_by_cr_session_id() tra [] binh
        # thuong cho cac session do, KHONG loi.
        affected_cells = await self._affected_cells_repo.get_by_cr_session_id(session_id)
        # cr_logs: session CU (truoc khi _log_step() duoc them vao _emit()/
        # _fail()) cung se tra [] tu nhien (chua tung ghi dong nao) - khong
        # can xu ly rieng, giong affected_cells.
        cr_logs = await self._cr_log_repo.get_by_cr_session_id(session_id)

        return CrSessionDetail(
            session=session,
            cell_params=cell_params,
            cr_logs=cr_logs,
            affected_cells=affected_cells,
        )
