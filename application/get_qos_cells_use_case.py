"""
GetQosCellsUseCase — danh gia QoS PER-CELL cho 1 cr_session (04092026).
Ban DOI XUNG cua GetQoeCellsUseCase.

=== VI SAO CAN ENDPOINT NAY ===
FE dang NHAN BAN cong thuc danh gia QoS trong qosEvaluation.ts (goi
GET /qos/{cell} lay diem tho roi tu tinh). Ban sao do da TROI KHOI BE 2 LAN;
lan gan nhat thieu han ve `avg_after >= MUC_TOT` nen:
  cell 117449: 4.83 -> 4.33, delta 0.50
  FE ket luan KHONG DAT -> ve nut [Xuat phieu]
  BE ket luan DAT       -> bam nut thi tra DAT_KHONG_XUAT
Nguoi dung thay nhan sai VA thay he thong tu mau thuan voi chinh no.

Va sua rieng qosEvaluation.ts thi lan 3 se lai troi. Bang QoE ben canh DA goi
/sessions/{id}/qoe-cells lay ket luan tu BE - bang QoS lam GIONG thi luat chi
con MOT ban duy nhat.

=== KHONG VIET CONG THUC MOI ===
Dung danh_gia_qos_tu_diem() - CHINH XAC ham ma XuatPhieuUseCase dung. Xem
docstring cua no ve ly do bat buoc dung chung.

=== KHONG LUU DB ===
Tinh tai cho moi lan hoi, GIONG GetQoeCellsUseCase. Co DOC snapshot (lazy
cache) nhung KHONG ghi: duong doc khong duoc lam thay doi du lieu, va job xuat
phieu (T+8) da la noi ghi snapshot roi.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from application.xuat_phieu_use_case import (  # noqa: PLC2701
    cua_so_danh_gia,
    danh_gia_qos_tu_diem,
)
from domain.errors import CrSessionNotFoundError
from domain.ports.inbound.use_case_ports import IGetQosSparklineUseCase
from domain.ports.outbound.repo_ports import ICrAffectedCellsRepo, ICrSessionRepo
from domain.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)

_GMT7 = timezone(timedelta(hours=7))


class QosCellEvaluationItem:
    """1 dong ket qua - doi xung voi QoeCellEvaluation.

    Dung class thuong (khong dataclass) de co property delta giong ban QoE."""

    def __init__(self, cell_name: str, danh_gia, tu_cache: bool):
        self.cell_name = cell_name
        self.qos_eval = danh_gia.qos_eval
        self.so_ngay_before = danh_gia.so_ngay_before
        self.so_ngay_after = danh_gia.so_ngay_after
        # Chi de log/do dem, KHONG tra ra API - FE khong can biet du lieu den
        # tu cache hay tu CTS.
        self.tu_cache = tu_cache

    @property
    def delta(self) -> float | None:
        """avg_before - avg_after. DUONG = TUT. None khi thieu 1 trong 2 ve.

        SUA 03/10/2026 - doi chieu dong bo voi domain/services/
        evaluation_service.py::evaluate() (xem "SUA 03/10/2026" dau file do):
        truoc day la avg_after - avg_before (AM = tut). Gio CUNG CHIEU voi
        do_te cua QosCellEvaluation (do_te = before - after, cung DUONG khi
        te) - khong con 2 chieu dau khac nhau giua delta/do_te nua."""
        e = self.qos_eval
        # SUA 18/10/2026: doc lech DA LAM TRON tu EvaluationService - CHINH so
        # da dem so nguong, khong tru lai tren float (xem LAM_TRON_SO_THAP_PHAN).
        # Fallback tru tay cho MetricEvaluation dung tay khong co lech (test cu).
        if e.lech is not None:
            return e.lech
        if e.avg_before is None or e.avg_after is None:
            return None
        return e.avg_before - e.avg_after


class GetQosCellsUseCase:
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        affected_cells_repo: ICrAffectedCellsRepo,
        qos_sparkline_use_case: IGetQosSparklineUseCase,
        evaluation_service: EvaluationService,
        # Lazy cache. Optional de moi cho tao use case san co khong phai sua.
        snapshot_repo=None,
    ):
        self._session_repo = session_repo
        self._affected_cells_repo = affected_cells_repo
        self._qos_sparkline_use_case = qos_sparkline_use_case
        self._evaluation_service = evaluation_service
        self._snapshot_repo = snapshot_repo

    async def danh_gia_kem_cua_so(self, cr_session_id: int) -> tuple[list, dict]:
        """(danh sach cell, cua so) - router can ca 2 de tra ra API.

        Tach method rieng thay vi doi kieu tra cua execute(): execute() dang
        duoc XuatPhieuUseCase va nhieu test goi, doi kieu se pha het."""
        session = await self._session_repo.get_by_id(cr_session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={cr_session_id} khong ton tai", session_id=cr_session_id
            )
        if session.executed_at is None:
            raise ValueError(f"cr_session id={cr_session_id} chua co executed_at, khong the danh gia")
        ket_qua, ngay_chup = await self._danh_gia(cr_session_id)
        # ngay_chup_snapshot (THEM 18/10/2026) di kem dict cua so: router doc ra
        # cho FE ghi "So lieu tai thoi diem danh gia dd/mm". None = co cell
        # phai goi CTS truc tiep (chua co snapshot).
        return ket_qua, {**cua_so_danh_gia(session.executed_at), "ngay_chup_snapshot": ngay_chup}

    async def execute(self, cr_session_id: int) -> list[QosCellEvaluationItem]:
        return (await self._danh_gia(cr_session_id))[0]

    async def _danh_gia(self, cr_session_id: int) -> tuple[list[QosCellEvaluationItem], date | None]:
        session = await self._session_repo.get_by_id(cr_session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={cr_session_id} khong ton tai", session_id=cr_session_id
            )
        if session.executed_at is None:
            # Chua chay CR -> khong co moc de dung cua so truoc/sau.
            raise ValueError(f"cr_session id={cr_session_id} chua co executed_at, khong the danh gia")

        cells = await self._affected_cells_repo.get_by_cr_session_id(cr_session_id)
        cell_names = [c["cell_name"] for c in cells]
        if not cell_names:
            return [], None

        # Cong thuc cua so nam o cua_so_danh_gia() - DUNG CHUNG voi QoE va voi
        # duong xuat phieu, khong viet lai o day.
        cs = cua_so_danh_gia(session.executed_at)
        before_from, before_to = cs["before_from"], cs["before_to"]
        after_from, after_to = cs["after_from"], cs["after_to"]

        diem_cache, ngay_chup = await self._doc_snapshot(cr_session_id)

        ket_qua = []
        for cell_name in cell_names:
            try:
                diem = diem_cache.get(cell_name)
                if diem is not None:
                    before_points, after_points = diem
                    tu_cache = True
                else:
                    # CTS: 1 REQUEST/CELL/CUA SO -> 2 request cho cell nay.
                    # KHAC CEM (1 request/ngay cho CA danh sach cell) nen chi
                    # phi o day ti le THUAN voi so cell - xem chu y o router.
                    before_points = await self._qos_sparkline_use_case.execute(
                        cell_name, from_dt=before_from, to_dt=before_to
                    )
                    after_points = await self._qos_sparkline_use_case.execute(
                        cell_name, from_dt=after_from, to_dt=after_to
                    )
                    tu_cache = False

                danh_gia = danh_gia_qos_tu_diem(
                    before_points, after_points, self._evaluation_service
                )
            except Exception as exc:  # noqa: BLE001 - CO Y bat rong: 1 cell loi
                # (CTS timeout rieng cell do) KHONG duoc lam mat ket qua cua
                # cac cell khac.
                #
                # SUA 04092026: VAN TRA cell do voi INSUFFICIENT_DATA, KHONG
                # con bo han khoi mang.
                # VI SAO: day la duong DOC (nguoi dung xem bang), khac duong
                # GHI (_xu_ly_mot_session bo qua cell loi la DUNG vi no dang
                # quyet dinh co xuat phieu hay khong - khong du can cu thi
                # khong xuat). Ban DOC ma bo cell di thi bang QoS va bang QoE
                # nam canh nhau tren UI co SO DONG KHAC NHAU, nguoi dung khong
                # biet cell dau mat va tuong he thong dem sai.
                # GetQoeCellsUseCase xu su dung nhu vay tu dau (cell vang mat
                # trong response CEM -> 0 ngay -> INSUFFICIENT_DATA).
                logger.warning(
                    "qos-cells: danh gia cell that bai, tra INSUFFICIENT_DATA",
                    extra={"cr_session_id": cr_session_id, "cell_name": cell_name, "loi": str(exc)},
                )
                # Danh gia tren 2 list RONG -> EvaluationService tu tra
                # INSUFFICIENT_DATA (0 < MIN_DAYS_REQUIRED) va avg = None.
                # Di qua CHINH ham danh gia chung thay vi tu dung ket qua gia -
                # neu mai luat doi thi cho nay khong bi bo quen.
                danh_gia = danh_gia_qos_tu_diem([], [], self._evaluation_service)
                tu_cache = False
            ket_qua.append(QosCellEvaluationItem(cell_name, danh_gia, tu_cache))
        # Chi bao ngay chup khi MOI dong deu tu snapshot - lan voi so CTS live
        # ma van ghi "so lieu tai ngay X" la noi sai voi nguoi doc.
        return ket_qua, (ngay_chup if ket_qua and all(r.tu_cache for r in ket_qua) else None)

    async def _doc_snapshot(self, cr_session_id: int) -> tuple[dict, date | None]:
        """({cell_name: (before_points, after_points)}, ngay chup) - MOI cell CO
        snapshot, du thieu ngay.

        SUA 18/10/2026 (quyet dinh user - MOT NGUON SO LIEU): truoc day chi doc
        snapshot khi DU 7+7 ngay, thieu thi goi CTS live -> bang hau kiem tren
        UI khac so lieu luc danh gia/xuat phieu (session 10707: snapshot 6 ngay
        sau, UI live 7 ngay, TXN096M12 lech 0.50 DAT thanh 0.57 KHONG DAT).
        qos_snapshot CHI duoc ghi luc job xuat phieu danh gia (duong doc nay
        khong ghi) nen "co snapshot" = "da danh gia" -> dung DUNG so do. Cell
        chua co snapshot moi goi CTS (giu co che cu).
        """
        if self._snapshot_repo is None:
            return {}, None
        try:
            rows = await self._snapshot_repo.get_by_session_id(cr_session_id)
            theo_cell: dict = {}
            ngay_chup = None
            for r in rows:
                if r["period"] not in ("before", "after"):
                    continue
                truoc, sau = theo_cell.setdefault(r["cell_name"], ([], []))
                diem = {
                    "time": r["snapshot_date"].isoformat() + "T00:00:00",
                    "qos": r["qos_score"],
                }
                (truoc if r["period"] == "before" else sau).append(diem)
                tao = r.get("created_at")
                if tao is not None:
                    ngay = tao.astimezone(_GMT7).date()
                    ngay_chup = ngay if ngay_chup is None else max(ngay_chup, ngay)
            return theo_cell, ngay_chup
        except Exception as exc:  # noqa: BLE001 - cache hong thi goi CTS, KHONG
            # duoc lam hong ca request.
            logger.warning(
                "qos-cells: doc snapshot that bai, se goi CTS",
                extra={"cr_session_id": cr_session_id, "loi": str(exc)},
            )
            return {}, None
