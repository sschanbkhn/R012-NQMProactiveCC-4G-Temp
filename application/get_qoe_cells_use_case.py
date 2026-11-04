"""
GetQoeCellsUseCase — danh gia QoE PER-CELL cho 1 cr_session.
Tu: yeu cau truc tiep user 16082026.

Tra loi cau hoi "TUNG cell co te di sau CR khong" - trung binh 7 ngay TRUOC vs
7 ngay SAU cua CHINH cell do, ngay thieu thi BO (chia cho so ngay thuc co).
Y het XuatPhieuUseCase._danh_gia_qos_cell() lam voi QoS.

=== TACH DOC LAP ===
KHONG dung toi cr_session.qoe_result/qos_result (danh gia cap SESSION, gop
trung binh TAT CA cell vao 1 so moi ngay - xem _daily_averages_dict() trong
evaluate_cr_use_case.py). 2 thu tra loi 2 cau hoi khac nhau, khong thay the
nhau:
  - qoe_result cap session : "ca vung co te di khong"
  - file nay              : "cell NAO te di"
Trung binh cap session CHE duoc cell hong - vd 4 cell [5, 5, 1, 5] ra 4.0
(dat muc tot) trong khi co 1 cell diem 1 (do that, session 553 ngay 17/07).

=== KET QUA DANH GIA: TINH LAI MOI LAN HOI, KHONG LUU ===
qoe_eval (PASS/FAIL tung cell) luon tinh tai cho, GIONG QoS (XuatPhieuUseCase
khong luu ket qua danh gia cua tung cell - cell DAT khong tao dong nao). Khong
them bang rieng cho ket qua danh gia, khong migration.

=== DIEM THO (qoe_snapshot): CO LUU, tu 20/08 (SUA 09/2026 - xem D4) ===
Doan tren noi ve KET QUA DANH GIA (PASS/FAIL) - con DIEM THO lay tu CEM (truoc
khi tinh avg/PASS-FAIL) THI CO duoc luu vao bang qoe_snapshot, lam LAZY CACHE
(xem _doc_snapshot_neu_du()/_luu_snapshot()): du 7 ngay/period cho MOI cell thi
lan hoi sau doc tu DB thay vi goi lai CEM. Ghi chu "KHONG LUU DB" ban dau (khi
file moi tao, truoc khi co lazy cache) khong con dung nua - xem DEV_LOG.md
muc snapshot QoE/09/2026.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from application.xuat_phieu_use_case import (  # noqa: PLC2701
    _daily_averages,
    cua_so_danh_gia,
)
from domain.errors import CrSessionNotFoundError
from domain.ports.outbound.gateway_ports import ISocGateway
from domain.ports.outbound.repo_ports import ICrAffectedCellsRepo, ICrSessionRepo
from domain.services.evaluation_service import (
    EvaluationService,
    diem_snapshot_theo_cua_so,
    loc_diem_theo_ngay,
)

load_dotenv()

_GMT7 = timezone(timedelta(hours=7))

# HAN GOI LAI CEM (09/2026, quyet dinh van hanh) - doc tu .env, xem
# .env.example. Ly do va cach dung: docstring _doc_snapshot_neu_du().
SNAPSHOT_HAN_GOI_LAI_NGAY = int(os.getenv("SNAPSHOT_HAN_GOI_LAI_NGAY", "14"))

# Dung sai -0.2, GIONG QoS cap cell (_XUAT_PHIEU_QOS_THRESHOLD_DELTA), KHONG
# phai -0.1 cua PASS/FAIL cap session.
#
# VI SAO: day la CUNG MOT CAU HOI voi QoS cap cell - "cell nay co te di khong,
# co dang de nguoi xu ly khong" - nen phai cung dung sai. Dung -0.1 se lam QoE
# bat cell chat hon QoS tren cung 1 cell, cung 1 cua so, chi khac chi so do -
# khong co can cu nghiep vu nao cho su chenh lech do.
#
# Hang so RIENG chu khong import tu xuat_phieu_use_case: 2 tieu chi doc lap ve
# nghiep vu (dieu chinh 1 ben khong duoc am tham keo ben kia), dung tien le da
# co khi tach -0.1 va -0.2.
logger = logging.getLogger(__name__)

# SUA 04092026 (yeu cau nghiep vu): -0.2 -> -0.5. Nay la "tut qua 0.5 diem thi
# KHONG DAT"; tut DUNG 0.5 van DAT.
# Di kem: MUC_TOT 4.0 (ve CUU "tut nhieu nhung van tot") da doi thanh
# MUC_TOI_THIEU 3.0 (SAN "duoi muc nay la khong dat ngay") - 2 dieu kien gio
# DOC LAP, xem domain/services/evaluation_service.py.
# SUA 03/10/2026 - DOI DAU thanh SO DUONG (xem domain/services/
# evaluation_service.py muc "SUA 03/10/2026" dau file): delta gio la
# avg_before - avg_after (duong = tut), nen nguong cung doi dau cho dong bo -
# FAIL khi delta > 0.5 (truoc day la delta < -0.5).
_QOE_CELL_THRESHOLD_DELTA = 0.5


def _ve_dang_gateway(rows: list[dict], period: str) -> list[dict]:
    """Dang snapshot DB -> dang ISocGateway.get_qoe(), de phan tinh toan ben
    duoi KHONG phai biet du lieu den tu API hay tu cache."""
    theo_cell: dict = {}
    for r in rows:
        if r["period"] != period:
            continue
        theo_cell.setdefault(r["cell_name"], []).append(
            {"time": r["snapshot_date"].isoformat() + "T00:00:00", "qoe": r["qoe_score"]}
        )
    return [{"cell_name": c, "metrics": m} for c, m in theo_cell.items()]


async def _doc_snapshot_qoe_neu_du(
    snapshot_repo, cr_session_id: int, cell_names: list[str], ngay_cr: date
) -> tuple[list, list] | None:
    """Tra (before_raw, after_raw) dang giong ISocGateway.get_qoe() neu snapshot
    DU 7 ngay/period cho MOI cell, HOAC neu DA TUNG LUU (du thieu) ma qua
    HAN goi lai; None neu CHUA CO DU LIEU DE TRA (caller se goi API CEM).

    HAM MODULE-LEVEL (02/10/2026, tach tu method cung ten cua
    GetQoeCellsUseCase) - de co the dung chung o nhieu noi (hien chi
    GetQoeCellsUseCase dung - xem muc "KHONG dung cho EvaluateCrUseCase" o
    duoi). snapshot_repo truyen vao TUONG MINH (thay vi self._snapshot_repo)
    de ham khong rang buoc vao 1 instance cu the.

    DEM so ngay thay vi xem created_at - xem ly do trong
    IQoeSnapshotRepo.dem_ngay_theo_cell().

    === HAN GOI LAI (09/2026, quyet dinh van hanh) ===
    CEM KHONG backfill du lieu qua khu - lo thung THAT (16/07, 21-27/07,
    session 553) se KHONG BAO GIO duoc lap day. Truoc 09/2026, "thieu < 7
    ngay" la tin hieu goi lai VO DIEU KIEN -> lo thung bien thanh VONG GOI
    VO HAN: moi lan mo tab van thieu (vi lo thung khong tu lap) -> van goi
    lai 15 request CEM -> van thieu -> lap lai. Qua SNAPSHOT_HAN_GOI_LAI_NGAY
    ngay ke tu ngay CR: TRA NGUYEN du lieu cache DANG CO (du thieu), KHONG
    goi CEM nua - chap nhan chart/danh gia co the thieu diem thay vi goi API
    lang phi vinh vien.

    SUA 02/10/2026 - BUG THAT phat hien khi can noi ham nay vao
    EvaluateCrUseCase (thu wire, 7 test co san bi sai ngay - xem
    docs/DEV_LOG.md): ban truoc GOP CHUNG 2 tinh huong khac nhau vao 1 dieu
    kien "qua han":
      (a) CHUA TUNG goi CEM/luu gi cho session nay (dem RONG) - o day "qua
          han" KHONG co nghia gi de "bo cuoc", vi CO THE CEM VAN CON DU LIEU
          (lo thung la tung NGAY cu the, khong phai MOI session cu deu
          thung) - ta chi don gian CHUA THU LAN NAO. Tra ([], []) trong
          truong hop nay la SAI: 1 session (hoac 1 cell) 15+ ngay tuoi, lan
          DAU TIEN ai do mo tab QoE, se LUON ra rong vinh vien du CEM van co
          du lieu that - KHONG BAO GIO duoc thu, chi vi "qua han" ma chua ai
          thu lan nao ca.
      (b) DA TUNG goi CEM it nhat 1 lan (dem KHONG rong) nhung van thieu
          ngay sau khi goi - day moi la tin hieu "lo thung that", va "qua
          han" o day moi dung y nghia "CEM khong bu duoc nua, dung ep goi
          lai vo ich".
    Sua: (a) LUON goi CEM (tra None) bat ke qua han hay chua - CHI (b) moi
    duoc dung du lieu cache thieu khi qua han. Tiet lo trong luc sua: ban cu
    VAN DUNG cho GetQoeCellsUseCase (muc dich ban dau cua ham - nguoi dung
    bam "xem QoE" lap lai cho 1 session DA TUNG thu it nhat 1 lan), BUG CHI
    lo o truong hop (a) - session/cell CHUA TUNG duoc thu goi nao.
    """
    if snapshot_repo is None:
        return None
    dem = await snapshot_repo.dem_ngay_theo_cell(cr_session_id)

    if not dem:
        # CHUA TUNG luu gi cho session nay - LUON goi CEM it nhat 1 lan, bat
        # ke qua han hay chua (xem "SUA 02/10/2026" o docstring: "qua han"
        # chi co nghia khi DA TUNG thu va biet chac la thung, khong ap dung
        # cho truong hop chua thu lan nao).
        return None

    qua_han = (datetime.now(_GMT7).date() - ngay_cr).days > SNAPSHOT_HAN_GOI_LAI_NGAY

    # DU = moi cell co dung 7 ngay o CA HAI period. Thieu 1 cell cung phai
    # goi lai ca lo: CEM nhan cells[] la mang nen goi 1 cell hay 17 cell
    # deu la 15 request (7 before + 8 after RONG, xem D2 o execute()) -
    # khong co loi gi khi goi rieng phan thieu.
    du = all(
        dem.get((cell, "before"), 0) >= 7 and dem.get((cell, "after"), 0) >= 7
        for cell in cell_names
    )
    if not du and not qua_han:
        return None

    rows = await snapshot_repo.get_by_session_id(cr_session_id)
    return (
        _ve_dang_gateway(rows, "before"),
        _ve_dang_gateway(rows, "after"),
    )


@dataclass
class QoeCellEvaluation:
    """Ket qua danh gia QoE cua 1 cell - doi xung voi QosCellEvaluation
    (application/xuat_phieu_use_case.py)."""

    cell_name: str
    qoe_eval: object  # MetricEvaluation (domain/services/evaluation_service.py)
    so_ngay_before: int
    so_ngay_after: int
    # Diem QoE TUNG NGAY cua cua so SAU CR (da gop theo ngay). Them 17082026 de
    # dien field "Qoe" trong payload phieu = min(7 ngay sau), GIONG cach "Qos"
    # dang lam. Khong giu lai thi phai goi CEM lan nua chi de lay min.
    #
    # KIEU list[float] (KHAC QosCellEvaluation.after_points la list[dict] diem
    # tho tu CTS): o day da qua _daily_averages() nen chi con gia tri/ngay -
    # dung thu payload can, khong mang theo "time" khong dung toi.
    after_points: list[float]

    @property
    def delta(self) -> float | None:
        """avg_before - avg_after. DUONG = tut. None khi thieu du lieu 1 trong 2 ve.

        SUA 03/10/2026 - doi chieu dong bo voi domain/services/
        evaluation_service.py::evaluate() (xem "SUA 03/10/2026" dau file do):
        truoc day la avg_after - avg_before (AM = tut), gio DUONG = tut cho
        dong nhat voi do_te cua QosCellEvaluation (do_te = before - after,
        cung DUONG khi te di) - KHONG con 2 chieu dau khac nhau giua QoE/QoS
        nua, giam rui ro doc nham."""
        e = self.qoe_eval
        # SUA 18/10/2026: doc lech DA LAM TRON tu EvaluationService - CHINH so
        # da dem so nguong, khong tru lai tren float (xem LAM_TRON_SO_THAP_PHAN).
        # Fallback tru tay cho MetricEvaluation dung tay khong co lech (test cu).
        if e.lech is not None:
            return e.lech
        if e.avg_before is None or e.avg_after is None:
            return None
        return e.avg_before - e.avg_after


class GetQoeCellsUseCase:
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        affected_cells_repo: ICrAffectedCellsRepo,
        soc_gw: ISocGateway,
        evaluation_service: EvaluationService,
        # LAZY CACHE (20082026). Optional de moi cho tao use case san co
        # (test cu) khong phai sua theo - thieu repo thi luon goi CEM nhu truoc.
        snapshot_repo=None,
    ):
        self._session_repo = session_repo
        self._affected_cells_repo = affected_cells_repo
        self._soc_gw = soc_gw
        self._evaluation_service = evaluation_service
        self._snapshot_repo = snapshot_repo

    async def _doc_snapshot_neu_du(
        self, cr_session_id: int, cell_names: list[str], ngay_cr: date
    ) -> tuple[list, list] | None:
        """Wrapper mong - xem _doc_snapshot_qoe_neu_du() (module-level, duoi
        day) cho toan bo logic. Tach rieng ham module-level (02/10/2026) de
        EvaluateCrUseCase GOI CHUNG DUNG co che nay (doc snapshot truoc khi
        goi lai CEM) MA KHONG viet lai ban sao thu 2 - xem
        application/evaluate_cr_use_case.py."""
        return await _doc_snapshot_qoe_neu_du(self._snapshot_repo, cr_session_id, cell_names, ngay_cr)

    async def _luu_snapshot(
        self,
        cr_session_id: int,
        before_raw: list,
        after_raw_rong: list,
        before_dates: set[str],
        after_dates: set[str],
        ngay_cr: str,
    ) -> None:
        """Upsert diem vua lay tu CEM, LUON DU 3 period (before/cr_day/after -
        09/2026, xem domain/services/evaluation_service.py::
        diem_snapshot_theo_cua_so()). NUOT loi: cache hong khong duoc lam hong
        ket qua danh gia ma nguoi dung dang cho.

        after_raw_rong PHAI la ket qua fetch TU ngay_cr (T) den T+7 (xem
        execute()) - GIONG EvaluateCrUseCase, de co diem cho period="cr_day".
        """
        if self._snapshot_repo is None:
            return
        try:
            points = diem_snapshot_theo_cua_so(
                "qoe", "qoe_score", before_raw, before_dates, after_raw_rong, after_dates, ngay_cr
            )
            if points:
                await self._snapshot_repo.upsert_many(cr_session_id, points)
        except Exception as exc:  # noqa: BLE001 - xem docstring
            logger.warning(
                "Khong luu duoc snapshot QoE, bo qua (khong anh huong ket qua)",
                extra={"cr_session_id": cr_session_id, "loi": str(exc)},
            )

    async def danh_gia_kem_cua_so(self, cr_session_id: int) -> tuple[list, dict]:
        """(danh sach cell, cua so) - doi xung voi GetQosCellsUseCase.

        Tach method rieng thay vi doi kieu tra cua execute(): execute() dang
        duoc XuatPhieuUseCase._lay_qoe_theo_cell va nhieu test goi."""
        session = await self._session_repo.get_by_id(cr_session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={cr_session_id} khong ton tai", session_id=cr_session_id
            )
        if session.executed_at is None:
            raise ValueError(f"cr_session id={cr_session_id} chua co executed_at, khong the danh gia")
        ket_qua, ngay_chup = await self._danh_gia(cr_session_id)
        # ngay_chup_snapshot (THEM 18/10/2026) - xem GetQosCellsUseCase.
        return ket_qua, {**cua_so_danh_gia(session.executed_at), "ngay_chup_snapshot": ngay_chup}

    async def execute(
        self, cr_session_id: int, luu_snapshot: bool = True
    ) -> list[QoeCellEvaluation]:
        return (await self._danh_gia(cr_session_id, luu_snapshot))[0]

    async def _da_danh_gia_doc_snapshot(self, session) -> tuple[list, list, date] | None:
        """(before_raw, after_raw, ngay chup) tu snapshot neu session DA DANH GIA
        (xuat_phieu_at co gia tri) VA da co snapshot; None -> di duong cu.

        SUA 18/10/2026 (quyet dinh user - MOT NGUON SO LIEU): session da qua job
        xuat phieu thi bang hau kiem/Excel/dashboard PHAI dung DUNG so luc danh
        gia, KHONG goi lai CEM (lazy cache cu goi lai khi thieu ngay truoc han
        SNAPSHOT_HAN_GOI_LAI_NGAY -> so tren UI troi khoi so da ra quyet dinh
        xuat phieu). Session CHUA danh gia giu nguyen co che lazy (mo tab som o
        T+3 van duoc lap day dan)."""
        if session.xuat_phieu_at is None or self._snapshot_repo is None:
            return None
        try:
            rows = await self._snapshot_repo.get_by_session_id(session.id)
        except Exception as exc:  # noqa: BLE001 - cache hong thi di duong cu
            logger.warning(
                "qoe-cells: doc snapshot da danh gia that bai, di duong cu",
                extra={"cr_session_id": session.id, "loi": str(exc)},
            )
            return None
        rows = [r for r in rows if r["period"] in ("before", "after")]
        if not rows:
            return None
        ngay_chup = max(
            (r["created_at"].astimezone(_GMT7).date() for r in rows if r.get("created_at") is not None),
            default=None,
        )
        return _ve_dang_gateway(rows, "before"), _ve_dang_gateway(rows, "after"), ngay_chup

    async def _danh_gia(
        self, cr_session_id: int, luu_snapshot: bool = True
    ) -> tuple[list[QoeCellEvaluation], date | None]:
        """luu_snapshot=False (20082026): DOC cache duoc nhung KHONG ghi.

        Danh cho duong XEM TRUOC cua job xuat phieu - no hua "khong dong vao
        DB", ma mot loi hua chi co gia tri khi kiem duoc bang test. Doc cache
        van bat: doc khong pha vo loi hua nao va tiet kiem 15 request CEM."""
        session = await self._session_repo.get_by_id(cr_session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={cr_session_id} khong ton tai", session_id=cr_session_id
            )
        if session.executed_at is None:
            # Chua chay CR -> khong co moc de dung cua so truoc/sau. ValueError
            # (loi goi sai cua caller) - cung pattern EvaluateCrUseCase.execute().
            raise ValueError(f"cr_session id={cr_session_id} chua co executed_at, khong the danh gia")

        # Lay cell tu cr_affected_cells - GIONG QoS (XuatPhieuUseCase), KHONG loc
        # _has_real_rf_change() nhu EvaluateCrUseCase. Ly do: cau hoi la "cell nao
        # trong vung bi anh huong da te di", khong phai "cell nao ta vua chinh RF".
        affected = await self._affected_cells_repo.get_by_cr_session_id(cr_session_id)
        cell_names = [c["cell_name"] for c in affected]
        if not cell_names:
            return [], None

        # Cua so tinh theo NGAY LICH GMT+7 cua executed_at - CHINH XAC pattern
        # da verify that o EvaluateCrUseCase (C1.4-fix8) va XuatPhieuUseCase.
        # Cong thuc cua so nam o cua_so_danh_gia() - DUNG CHUNG voi QoS va voi
        # duong xuat phieu (04092026), khong viet lai o day.
        cs = cua_so_danh_gia(session.executed_at)
        before_from, before_to = cs["before_from"], cs["before_to"]
        after_from, after_to = cs["after_from"], cs["after_to"]
        ngay_cr_date = cs["ngay_cr"]
        ngay_cr = ngay_cr_date.isoformat()
        # cr_day_start = chinh ngay CR duoi dang datetime (before_to = ngay
        # CR - 1, nen +1 ngay la ra lai ngay CR - tranh dung lai
        # cs["before_to"]/cs["after_from"] rai rac, khong tu tinh datetime(...)
        # moi o day de khong lech voi cong thuc goc trong cua_so_danh_gia()).
        cr_day_start = before_to + timedelta(days=1)
        before_dates = {(before_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
        after_dates = {(after_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

        # === CHONG BUNG SO REQUEST ===
        # KHONG goi tung cell mot nhu QoS lam. QoS goi CTS 1 lan/cell/cua so vi
        # CTS nhan CA cua so trong 1 request. CEM thi 1 REQUEST = 1 NGAY, nen
        # copy may moc "1 cell/lan" se thanh:
        #     17 cell x 2 cua so x 7 ngay = 238 request
        # Thay vao do goi get_qoe() DUNG 1 LAN cho ca danh sach cell moi cua so
        # (CEM nhan cells[] la mang), roi tach theo cell_name:
        #     before (7 ngay) + after RONG (8 ngay, T..T+7 - xem D2 duoi day) = 15 request
        # Ket qua danh gia GIONG HET, chi khac so lan lam phien CEM.
        # === LAZY CACHE (20082026) ===
        # Doc snapshot TRUOC. Du 7 ngay before + 7 ngay after cho MOI cell thi
        # KHONG goi CEM (tiet kiem 15 request va 10-30 giay cho moi lan mo chi
        # tiet). Thieu -> goi API roi upsert lai.
        #
        # Cua so T-7..T+7 quanh ngay CR la BAT BIEN sau khi qua T+7 - khong bao
        # gio doi nua, nen cache khong can han su dung DU LIEU (han o day chi
        # ap dung cho VIEC GOI LAI CEM khi thieu, xem SNAPSHOT_HAN_GOI_LAI_NGAY).
        ngay_chup = None
        da_danh_gia = await self._da_danh_gia_doc_snapshot(session)
        du_snapshot = (
            None if da_danh_gia is not None
            else await self._doc_snapshot_neu_du(cr_session_id, cell_names, ngay_cr_date)
        )
        if da_danh_gia is not None:
            before_raw, after_raw, ngay_chup = da_danh_gia
        elif du_snapshot is not None:
            before_raw, after_raw = du_snapshot
        else:
            before_raw = await self._soc_gw.get_qoe(cell_names, before_from, before_to)
            # Fetch tu ngay_cr (T) thay vi after_from (T+1) - GIONG
            # EvaluateCrUseCase (application/evaluate_cr_use_case.py), de co
            # du lieu luu period="cr_day" (D2, 09/2026). 1 request CEM PHU
            # (15 thay vi 14 cho ca 2 cua so, CEM la 1 request/ngay).
            after_raw_rong = await self._soc_gw.get_qoe(cell_names, cr_day_start, after_to)
            if luu_snapshot:
                await self._luu_snapshot(
                    cr_session_id, before_raw, after_raw_rong, before_dates, after_dates, ngay_cr
                )
            # Cua so DANH GIA van la T+1..T+7 - loc lai TUONG MINH truoc khi
            # tinh avg, KHONG de diem ngay T (vua fetch them o tren) lot vao
            # PASS/FAIL (_daily_averages() cua xuat_phieu_use_case.py KHONG tu
            # loc allowed_dates - xem loc_diem_theo_ngay()).
            after_raw = loc_diem_theo_ngay(after_raw_rong, after_dates)

        # Tach theo TEN CELL, TUYET DOI khong zip theo thu tu: gateway co the tra
        # thieu cell hoac tra khac thu tu gui di (CEM bo qua cell khong co du
        # lieu - da do that).
        before_theo_cell = {e["cell_name"]: e.get("metrics", []) for e in before_raw}
        after_theo_cell = {e["cell_name"]: e.get("metrics", []) for e in after_raw}

        ket_qua = []
        for cell_name in cell_names:
            # .get(..., []) chu khong [..]: cell vang mat hoan toan trong
            # response -> coi nhu 0 ngay du lieu, roi vao INSUFFICIENT_DATA cua
            # RIENG cell do. KHONG duoc nem loi lam hong ca danh sach.
            # value_key="qoe" - diem tu CEM co key "qoe" (mac dinh cua ham la
            # "qos" cho duong xuat phieu).
            before_daily = _daily_averages(before_theo_cell.get(cell_name, []), "qoe")
            after_daily = _daily_averages(after_theo_cell.get(cell_name, []), "qoe")

            # Dung LAI EvaluationService y nguyen - muc_toi_thieu KHONG truyen
            # (mac dinh MUC_TOI_THIEU=3.0), MIN_DAYS_REQUIRED=5 nam trong service.
            qoe_eval = self._evaluation_service.evaluate(
                before_daily, after_daily, threshold=_QOE_CELL_THRESHOLD_DELTA
            )
            ket_qua.append(
                QoeCellEvaluation(
                    cell_name=cell_name,
                    qoe_eval=qoe_eval,
                    so_ngay_before=len(before_daily),
                    so_ngay_after=len(after_daily),
                    after_points=after_daily,
                )
            )
        return ket_qua, ngay_chup
