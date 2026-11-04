"""
EvaluateCrUseCase — danh gia CR sau 21 ngay (goi tu n8n /jobs/evaluate-cr).
Tu: ARCHITECTURE.md Section 4.2; BUSINESS_RULES.md Section 8; WORKFLOW.md Section 4;
TASK_LIST.md C2.2

PHAM VI + GIA DINH (Nhom 2, 13072026 - CAN XAC NHAN, xem DEV_LOG.md muc C2.2-fix
cho lan sua thu 2 - 13072026 sau khi user review):
1. TU GIA DINH: qoe_snapshot/qos_snapshot KHONG duoc persist vao DB (khong co port/
   repo nao cho 2 bang nay - cung tinh trang cr_log da ghi nhan o C2.1). Chi tinh
   toan trong memory roi ghi ket qua avg vao cr_session (qoe_before/after/...).
2. TU GIA DINH: alert_log KHONG duoc tao khi FAIL (application/alert_use_case.py
   la stub rong, thuoc task C2.7 rieng, ngoai pham vi hom nay).
3. TU GIA DINH: "avg" trong BUSINESS_RULES.md SS8.2 duoc hieu la trung binh CAC
   NGAY (khong phai trung binh xuyen (cell,ngay)) - moi ngay lay trung binh diem
   so cua TAT CA cell truoc, roi moi trung binh cac ngay co du lieu voi nhau. Ly
   do: WORKFLOW.md SS4.2.d dung "days_before = count rows... (max 7)" - ham y dem
   theo NGAY, khong phai theo dong (cell,ngay). KHONG co doan doc nao mo ta ro
   rang cong thuc gop nhieu cell/ngay thanh 1 con so - day la quyet dinh hop ly
   nhat voi thong tin hien co, can user xac nhan lai.
4. status cr_session sau khi evaluate: EVAL_PENDING neu MOT TRONG HAI qoe_result
   HOAC qos_result la INSUFFICIENT_DATA, nguoc lai EVALUATED - WORKFLOW.md SS4.2.d
   viet chung 1 dieu kien cho ca session (khong tach rieng qoe/qos) nen gop OR la
   dien giai hop ly nhat.
5. SUA (13072026, xac nhan voi user): status EVALUATING (BUSINESS_RULES.md SS11
   state machine) GIO CO duoc ghi tam vao DB truoc khi tinh - dung lam "lock"
   don gian tranh 2 tien trinh evaluate_cr_use_case cung xu ly 1 session (n8n
   CHUA chac chan khong trigger chong lan - xem CrEvaluationInProgressError).
   Session dang EVALUATING se KHONG con nam trong ket qua list(DONE/EVAL_PENDING)
   nua (tu dong loai boi status filter) - va execute() tu kiem tra lai neu goi
   truc tiep. Day la guard DON GIAN (khong dung transaction/row-lock that su o
   tang SQL) - van co khe ho race rat nho neu 2 tien trinh doc session GAN
   NHU cung luc truoc khi 1 ben kip ghi EVALUATING, chap nhan duoc theo yeu
   cau "guard don gian" cua user.
6. execute_all_pending() la method CU THE (khong thuoc ABC IEvaluateCrUseCase,
   B2.9 chi dinh nghia execute(session_id) cho 1 session) - dung rieng cho
   POST /jobs/evaluate-cr (api/routers/jobs.py) de quet TOAN BO session
   DONE/EVAL_PENDING da qua EVALUATION_DAYS (.env, mac dinh 21) - KHONG doi ABC
   da co (rui ro thap hon, khong pha vo hop dong cu).
7. SUA (13072026, xac nhan voi user): cua so before/after tinh theo NGAY LICH
   (calendar date) cua executed_at, KHONG phai timedelta tho tren timestamp co
   gio/phut cu the. before_from/before_to/after_from/after_to deu la mocs 00:00
   cua ngay lich tuong ung -> khop CHINH XAC 7 ngay lich T-7..T-1 va T+1..T+7,
   KHONG can buffer/dem du nhu ban truoc (ban truoc dung before_from=cr_date-8
   ngay de "de phong" lech gio nhung khong loc lai ngay that sau khi fetch -
   co the dem du 1 ngay). _daily_averages() van LOC LAI tuong minh theo tap
   ngay cho phep (allowed_dates) truoc khi tinh trung binh - phong thu kep, du
   CTS/SOC tra ve du lieu ngoai [from,to] yeu cau (vi du lech mui gio/DST phia
   ho) thi van khong lam sai ket qua.
8. SUA (13072026, xac nhan voi user): CHI danh gia cell THAT SU thay doi RF -
   loai cell co rsboost_new == rsboost_current (hoac qrxlevmin_new ==
   qrxlevmin_current) - tuc cac cell action_type="skip" (da o cap/floor) hoac
   khong co gia tri moi. Ly do (user nhan manh): cell "skip" khong doi RF, dua
   vao danh gia "CR co cai thien QoE/QoS khong" la sai logic nhan qua. Kiem tra
   TRUC TIEP tren gia tri (khong dua vao action_type field) de dam bao dung du
   lieu that persist trong DB, khong phu thuoc field trung gian.
9. evaluated_at CHI duoc set khi status = EVALUATED (giu None khi EVAL_PENDING)
   - WORKFLOW.md ghi "evaluated_at: luc evaluate xong" khong ro "xong" la chay
   xong (du pending) hay co ket luan cuoi cung - da xac nhan voi user CHAP
   NHAN nhu hien tai, khong doi.
10. 1 session loi trong batch (DomainError) -> log canh bao, bo qua, KHONG lam
    hong ca batch, giu nguyen status cu de hom sau thu lai - da xac nhan voi
    user CHAP NHAN nhu hien tai, khong doi.
11. SUA (13072026, C2.7) - wire AlertUseCase: FAIL -> tao alert_log
    QOE_DEGRADED/QOS_DEGRADED (BUSINESS_RULES.md SS8.3, CO CAN CU). Rieng
    EVAL_PENDING_TOO_LONG (>30 ngay, SS8.4+SS13) duoc check trong
    execute_all_pending() tren TOAN BO session dang EVAL_PENDING (khong chi
    nhung session vua duoc evaluate lai) - moi lan job chay ma van con qua 30
    ngay se tao alert MOI (KHONG dedupe - xem TU GIA DINH trong
    application/alert_use_case.py).
12. SUA HAN (20082026, yeu cau truc tiep user) - persist snapshot PER-CELL,
    15 ngay, THAY CHO "10 diem chart" gop chung truoc day.
    KHAC 3 diem so voi ban cu:
      - Truoc: 1 dong/ngay cho CA SESSION (cell_name = "__ALL_CELLS__", da
        trung binh cheo cell trong _daily_averages_dict()) -> che mat cell
        hong. Nay: 1 dong/CELL/ngay, giu nguyen diem cua tung cell.
      - Truoc: 9 ngay (T-2,T-1 + T+1..T+7). Nay: 15 ngay T-7..T+7 - do rong
        DUNG bang cua so danh gia, khong con khai niem "ngoai pham vi chart".
      - Truoc: T+0 (ngay CR) LUON vang mat vi khong cua so nao phu no. Nay CO:
        cua so FETCH cua nhanh after mo rong xuong T (fetch_after_from =
        cr_day_start) trong khi cua so DANH GIA van la T+1..T+7 - lay them
        ngay T ton 0 request CTS va +1 request CEM. T+0 luu voi period=
        "cr_day" de phan biet ro, KHONG lan vao before/after.
    Nguon du lieu van la du lieu DA FETCH cho viec danh gia, KHONG goi them
    CTS/SOC cho rieng viec luu.
13. Ngay THIEU du lieu that (CTS/SOC khong tra ve - binh thuong theo
    API_CONTRACTS.md) DON GIAN VANG MAT khoi bang snapshot, khong luu gia tri
    null/0 gia (qoe_score/qos_score la NOT NULL). Day la lua chon "bo qua
    diem", khac cach _daily_averages() xu ly thieu ngay khi tinh avg (van tinh
    binh thuong tren so ngay thuc te co).

14. QoE KHONG doc snapshot truoc khi goi CEM (CHOT 02/10/2026, da can nhac VA
    TU CHOI - KHONG phai chua lam toi) - GIU NGUYEN cach cu: execute() LUON
    goi self._soc_gw.get_qoe() moi lan, khong kiem tra qoe_snapshot truoc.

    LY DO TU CHOI them lazy-cache nhu GetQoeCellsUseCase dang lam (ham dung
    chung _doc_snapshot_qoe_neu_du(), module-level, application/
    get_qoe_cells_use_case.py - VAN GIU LAI cho noi khac dung, chi khong
    wire vao day):
      - TIET KIEM IT: EvaluateCrUseCase chi chay 1 LAN DUY NHAT cho moi
        session (job 21 ngay, khong quet lai - xem muc 4/10 o tren), khac
        GetQoeCellsUseCase co the bi goi NHIEU LAN cho CUNG 1 session (nguoi
        dung mo lai tab QoE) - cache chi co gia tri khi co nhieu lan goi lap
        lai de tiet kiem, o day gan nhu khong co loi ich do.
      - RUI RO DOI KET QUA DANH GIA: thu wire ham tren vao day (truoc khi
        chot tu choi) da lam 7 test co san trong
        tests/unit/test_evaluate_cr_use_case.py sai/crash ngay - vi
        EvaluateCrUseCase THUONG LA LAN DAU TIEN cham toi qoe_snapshot cho 1
        session (khong ai xem QoE truoc khi job 21 ngay chay), va
        EVALUATION_DAYS (21) > SNAPSHOT_HAN_GOI_LAI_NGAY (14 mac dinh) nen
        se roi vao nhanh "qua han" cua ham do ngay lan dau - cho du ban than
        ham do DA duoc sua lai cho dung (xem item 1, 02/10/2026:
        "chua tung luu" gio LUON goi CEM bat ke qua han), RUI RO VAN LA tiep
        tuc phu thuoc vao 1 co che vong doi khac han (GetQoeCellsUseCase co
        the goi nhieu lan, EvaluateCrUseCase chi 1 lan) - de an toan va dung
        dong ket qua danh gia KHONG BI ANH HUONG BOI 1 CO CHE THIET KE CHO
        MUC DICH KHAC, giu nguyen EvaluateCrUseCase luon goi CEM truc tiep.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from application.alert_use_case import EVAL_PENDING_TOO_LONG_DAYS, AlertUseCase
from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrStatus
from domain.errors import CrEvaluationInProgressError, CrSessionNotFoundError, DomainError
from domain.ports.inbound.use_case_ports import EvaluationResult, IEvaluateCrUseCase
from domain.ports.outbound.gateway_ports import INetworkGateway, ISocGateway
from domain.ports.outbound.repo_ports import (
    ICellParamsRepo,
    ICrSessionRepo,
    IQoeSnapshotRepo,
    IQosSnapshotRepo,
    SessionFilter,
)
from domain.services.evaluation_service import EvaluationService, diem_snapshot_theo_cua_so

load_dotenv()
logger = logging.getLogger(__name__)

EVALUATION_DAYS = int(os.getenv("EVALUATION_DAYS", "21"))

# C1.4-fix8 (21072026, xac nhan voi user): VN khong co DST nen offset co dinh
# +7h la du chinh xac (KHONG dung zoneinfo.ZoneInfo - may server khong co goi
# tzdata cai san, offline khong tai duoc). Dung chung pattern
# _GMT7 = timezone(timedelta(hours=7)) da co san o adapters/http/sha512_auth.py
# va adapters/netact/xml_builder.py, khong tao cach lam moi.
_GMT7 = timezone(timedelta(hours=7))


def _to_gmt7(dt_utc: datetime) -> datetime:
    # BUG THAT phat hien qua trace tram 111139/session #203 (21072026): executed_at
    # luu UTC (trigger_cr_use_case.py: datetime.now(timezone.utc), xem
    # adapters/postgres/cr_session_repo.py chi strip tzinfo khi ghi/doc, KHONG
    # convert GMT+7) nhung "ngay CR" phai tinh theo LICH VN vi CTS gom du lieu
    # theo GMT+7 (xac nhan voi user) - lay .year/.month/.day truc tiep tu gia
    # tri UTC (nhu code cu) se lech 1 ngay bat cu khi CR chay trong khung UTC
    # 17:00-23:59 (= GMT+7 00:00-06:59 hom sau, ~29% so lan CR, vi du session
    # #203: executed_at UTC 17:48 = GMT+7 00:48 hom sau nhung code cu tinh
    # "ngay CR" la hom truoc). dt_utc la naive (khong co tzinfo, gia tri THUC
    # la UTC) - phai GAN tzinfo=UTC tuong minh truoc astimezone(), Python
    # khong tu suy duoc mui gio thuc tu 1 datetime naive.
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(_GMT7)


def _has_real_rf_change(cp: CellParam) -> bool:
    # Gia dinh #8 (xem docstring dau file) - loai cell "skip" (khong doi RF)
    # khoi tap danh gia. So sanh TRUC TIEP gia tri (khong dua vao action_type)
    # de dung dung du lieu that: rsboost_new/qrxlevmin_new deu la value object
    # bat bien (RsboostLevel/Qrxlevmin, dataclass frozen) nen != so theo gia tri.
    rsboost_changed = (
        cp.rsboost_current is not None
        and cp.rsboost_new is not None
        and cp.rsboost_current != cp.rsboost_new
    )
    qrxlevmin_changed = (
        cp.qrxlevmin_current is not None
        and cp.qrxlevmin_new is not None
        and cp.qrxlevmin_current != cp.qrxlevmin_new
    )
    return rsboost_changed or qrxlevmin_changed


def _daily_averages_dict(raw: list[dict], value_key: str, allowed_dates: set[str]) -> dict[str, float]:
    # Gop tat ca (cell, ngay) -> trung binh theo TUNG NGAY (xem gia dinh #3 o dau
    # file), GIU LAI key ngay ("YYYY-MM-DD") - dung chung cho ca tinh avg
    # PASS/FAIL (_daily_averages() duoi day, KHONG doi hanh vi) VA persist
    # 10-diem chart (gia dinh #12, moi them Nhom 4 - can biet CHINH XAC ngay
    # nao de ghi vao qoe_snapshot/qos_snapshot). raw la format tra ve tu
    # INetworkGateway.get_qos_metrics()/ISocGateway.get_qoe():
    # list[{"cell_name":..., "metrics":[{"time":..., value_key: ...}]}]
    # allowed_dates ("YYYY-MM-DD") - loc lai tuong minh (gia dinh #7) truoc khi
    # tinh trung binh, KHONG dua nguyen moi ngay CTS/SOC tra ve.
    # C1.4-fix8 (21072026) - XAC NHAN LAI khong con lech: allowed_dates gio la
    # tap ngay GMT+7 (tu before_dates/after_dates o execute(), da tinh tu
    # cr_day_start GMT+7 - xem _to_gmt7()). date_key lay 10 ky tu dau time_str
    # CTS/SOC tra ve - dung theo GIA DINH CTS gom/tra ngay theo GMT+7 (xem
    # comment day du o execute(), truoc doan goi get_qos_metrics/get_qoe) nen
    # date_key va allowed_dates CUNG mui gio, khop dung. Neu gia dinh do SAI
    # (CTS thuc su tra time UTC that) thi ca 2 phia (request gui va date_key
    # loc o day) van nhat quan VOI NHAU vi cung dua tren 1 gia dinh - rui ro
    # chi la CA HE THONG lech 1 khoi 7h so voi thuc te, KHONG phai lech giua
    # request va response (xem CAN XAC NHAN THEM VOI TEAM CTS o execute()).
    by_date: dict[str, list[float]] = {}
    for cell_entry in raw:
        for point in cell_entry.get("metrics", []):
            time_str = point["time"]
            date_key = time_str[:10]  # "YYYY-MM-DD" - format ISO chuan tu CTS/SOC
            if date_key not in allowed_dates:
                continue
            by_date.setdefault(date_key, []).append(point[value_key])
    return {d: sum(vals) / len(vals) for d, vals in by_date.items()}


# _diem_theo_cell_ngay()/_snapshot_points() CHUYEN sang domain/services/
# evaluation_service.py (09/2026, gop dung dong snapshot voi GetQoeCellsUseCase
# - xem docstring diem_snapshot_theo_cua_so() ben do). KHONG con dinh nghia
# rieng o day nua - xem import dau file.


def _daily_averages(raw: list[dict], value_key: str, allowed_dates: set[str]) -> list[float]:
    # KHONG DOI HANH VI - chi wrap _daily_averages_dict() de giu nguyen chu ky
    # cu (list[float], khong quan tam thu tu ngay) cho EvaluationService.evaluate().
    return list(_daily_averages_dict(raw, value_key, allowed_dates).values())


class EvaluateCrUseCase(IEvaluateCrUseCase):
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        cell_repo: ICellParamsRepo,
        network_gw: INetworkGateway,
        soc_gw: ISocGateway,
        evaluation_service: EvaluationService,
        alert_use_case: AlertUseCase,
        qoe_snapshot_repo: IQoeSnapshotRepo,
        qos_snapshot_repo: IQosSnapshotRepo,
    ):
        self._session_repo = session_repo
        self._cell_repo = cell_repo
        self._network_gw = network_gw
        self._soc_gw = soc_gw
        self._evaluation_service = evaluation_service
        self._alert_use_case = alert_use_case
        self._qoe_snapshot_repo = qoe_snapshot_repo
        self._qos_snapshot_repo = qos_snapshot_repo

    async def execute(self, session_id: int) -> EvaluationResult:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            raise CrSessionNotFoundError(f"cr_session id={session_id} khong ton tai", session_id=session_id)
        if session.status == CrStatus.EVALUATING:
            # Guard don gian (gia dinh #5) - 1 tien trinh khac dang xu ly session
            # nay, KHONG phai loi that su.
            raise CrEvaluationInProgressError(
                f"cr_session id={session_id} dang duoc evaluate boi 1 tien trinh khac", session_id=session_id
            )
        if session.executed_at is None:
            # Chua chay CR that (khong co executed_at) - khong the xac dinh cua
            # so before/after. Khong co DomainError nao khop - ValueError (cung
            # pattern "loi goi sai cua caller" nhu CrSessionRepo.update()).
            raise ValueError(f"cr_session id={session_id} chua co executed_at, khong the danh gia")

        # Lock: chuyen sang EVALUATING NGAY truoc khi lam I/O cham (CTS/SOC that)
        # - gia dinh #5. Sessions dang EVALUATING se tu dong bi loai khoi
        # execute_all_pending() lan chay ke tiep (status filter DONE/EVAL_PENDING).
        session.status = CrStatus.EVALUATING
        session = await self._session_repo.update(session)

        cell_params = await self._cell_repo.get_by_cr_session_id(session_id)
        # Gia dinh #8 - CHI giu cell that su thay doi RF (loai "skip")
        cell_params = [cp for cp in cell_params if _has_real_rf_change(cp)]
        cell_names = [cp.cell_name for cp in cell_params]

        # Gia dinh #7 - cua so tinh theo NGAY LICH cua executed_at (khong phai
        # timedelta tho tren timestamp co gio/phut), khop CHINH XAC T-7..T-1 /
        # T+1..T+7 (BUSINESS_RULES.md SS8.2), khong can buffer.
        # C1.4-fix8 (21072026) - SUA: "ngay CR" phai la ngay theo LICH VN
        # (GMT+7), KHONG phai ngay UTC tho cua executed_at - xem _to_gmt7()
        # o dau file cho ly do day du (bug that phat hien qua tram 111139/
        # session #203, chi tiet docs/DEV_LOG.md muc [C1.4-fix8]).
        cr_date_vn = _to_gmt7(session.executed_at)
        cr_day_start = datetime(cr_date_vn.year, cr_date_vn.month, cr_date_vn.day)

        before_from, before_to = cr_day_start - timedelta(days=7), cr_day_start - timedelta(days=1)
        after_from, after_to = cr_day_start + timedelta(days=1), cr_day_start + timedelta(days=7)

        before_dates = {(before_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
        after_dates = {(after_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

        # CUA SO FETCH KHAC CUA SO DANH GIA (20082026, de luu snapshot ngay T).
        # Fetch bat dau tu chinh ngay CR (T) thay vi T+1, nhung `after_dates`
        # o tren GIU NGUYEN T+1..T+7 - allowed_dates trong _daily_averages_dict()
        # se loc ngay T ra khoi phep tinh avg. Nho vay:
        #   - Ket qua PASS/FAIL KHONG DOI mot chut nao (van dung 7 ngay T+1..T+7)
        #   - Co du lieu ngay T de luu snapshot period="cr_day" cho chart
        # CHI PHI: CTS 0 request phu (cung 1 lan goi range, chi rong them 1 ngay).
        # CEM +1 request (1 request = 1 NGAY) -> 15 thay vi 14 cho ca 2 cua so.
        fetch_after_from = cr_day_start

        # C1.4-fix8 - GIA DINH DANG DUNG, CAN XAC NHAN THEM VOI TEAM CTS: gui
        # thang before_from/before_to/after_from/after_to (naive, mang gia
        # tri WALL-CLOCK GMT+7 - vd "2026-07-14 00:00:00" nghia la 0h ngay
        # 14/07 GIO VIET NAM) xuong CtsHttpAdapter.get_qos_metrics() - adapter
        # nay format chuoi gui CTS voi hau to "Z" (adapters/http/
        # cts_http_adapter.py dong 54-55) NHUNG KHONG tu convert UTC (xem
        # docstring adapter: "Chuan hoa GIO... KHONG doi NGAY"). Ly do KHONG
        # convert cr_day_start sang UTC that truoc khi gui: user xac nhan CTS
        # gom du lieu theo NGAY GMT+7 - trong toan bo he thong gw-oneoss.vnpt.vn
        # (cung gateway voi CDS), cac truong "Z" duoc quan sat la NHAN DANH
        # UTC nhung mang gia tri WALL-CLOCK GMT+7 tren thuc te (giong pattern
        # CDS X-Request-Date GMT+7 khong phai UTC that - API_CONTRACTS.md
        # SS1). Neu gui UTC that (vd tru them 7h) se lam CTS hieu SAI ranh
        # gioi ngay theo huong nguoc lai. CHUA co bang chung 100% (chua goi
        # CTS that voi 2 kieu de doi chieu response) - neu sau nay xac nhan
        # CTS thuc su parse "Z" la UTC chuan, phai them buoc convert
        # cr_day_start (GMT+7) -> UTC that truoc khi truyen cho get_qos_metrics
        # o day (KHONG sua trong cts_http_adapter.py, giu adapter don gian
        # "nhan gi gui nay").
        qos_before_raw = await self._network_gw.get_qos_metrics(cell_names, before_from, before_to)
        qos_after_raw = await self._network_gw.get_qos_metrics(cell_names, fetch_after_from, after_to)
        # QoE: GIU NGUYEN goi CEM moi moi lan (KHONG doc qoe_snapshot truoc) -
        # CHOT 02/10/2026, xem muc 14 o dau file cho ly do day du (chay 1
        # lan/session nen cache tiet kiem khong dang ke, trong khi rui ro doi
        # ket qua danh gia neu dung chung co che "qua han" cua GetQoeCellsUseCase).
        qoe_before_raw = await self._soc_gw.get_qoe(cell_names, before_from, before_to)
        qoe_after_raw = await self._soc_gw.get_qoe(cell_names, fetch_after_from, after_to)

        # Gia dinh #12 - giu ca dict (theo ngay, dung de persist chart) VA list
        # (dung de tinh avg PASS/FAIL, KHONG doi hanh vi cu).
        qos_before_by_date = _daily_averages_dict(qos_before_raw, "qos", before_dates)
        qos_after_by_date = _daily_averages_dict(qos_after_raw, "qos", after_dates)
        qoe_before_by_date = _daily_averages_dict(qoe_before_raw, "qoe", before_dates)
        qoe_after_by_date = _daily_averages_dict(qoe_after_raw, "qoe", after_dates)

        qos_eval = self._evaluation_service.evaluate(
            list(qos_before_by_date.values()), list(qos_after_by_date.values())
        )
        qoe_eval = self._evaluation_service.evaluate(
            list(qoe_before_by_date.values()), list(qoe_after_by_date.values())
        )

        session.qoe_result = qoe_eval.result
        session.qos_result = qos_eval.result
        session.qoe_before = qoe_eval.avg_before
        session.qoe_after = qoe_eval.avg_after
        session.qos_before = qos_eval.avg_before
        session.qos_after = qos_eval.avg_after

        if qoe_eval.result == "INSUFFICIENT_DATA" or qos_eval.result == "INSUFFICIENT_DATA":
            # CACH C (16082026) - trang thai CUOI, KHONG phai EVAL_PENDING nua.
            #
            # VI SAO DOI: EVAL_PENDING nghia la "cho them du lieu" nen job quet
            # lai HANG NGAY. Nhung du lieu thieu thuong do NGUON KHONG CO chu
            # khong phai chua toi gio - vd lo thung CEM 16/07 va 21-27/07 se
            # khong bao gio duoc bo sung. Session se quet lai vinh vien, ton
            # CTS/CEM moi ngay, va sau EVAL_PENDING_TOO_LONG_DAYS con ban alert
            # admin cho mot viec khong ai sua duoc. Session 553 la ca that.
            #
            # Danh dau KHONG_DU_DU_LIEU -> ra khoi tap quet (execute_all_pending
            # chi lay DONE + EVAL_PENDING), nguoi van hanh doc UI thay ro va tu
            # quyet dinh. qoe_result/qos_result van la "INSUFFICIENT_DATA" va
            # qoe_before/after van duoc ghi o tren - du can cu de doi chieu.
            session.status = CrStatus.KHONG_DU_DU_LIEU
            logger.warning(
                "Khong du du lieu danh gia - danh dau KHONG_DU_DU_LIEU, KHONG quet lai",
                extra={
                    "session_id": session_id,
                    "qoe_result": qoe_eval.result,
                    "qos_result": qos_eval.result,
                },
            )
        else:
            session.status = CrStatus.EVALUATED
            # C1.4-fix10 (21072026) - evaluated_at gio la TIMESTAMPTZ (models/
            # cr_session.py), giu nguyen tzinfo (KHONG con .replace(tzinfo=None))
            # de response tra ve co "Z" nhat quan voi created_at/updated_at.
            session.evaluated_at = datetime.now(timezone.utc)

        await self._session_repo.update(session)

        # === PERSIST SNAPSHOT PER-CELL, DU 15 NGAY (20082026) ===
        #
        # DOI 2 DIEM so voi ban cu:
        # (1) PER-CELL thay vi gop cheo: truoc day ghi 1 dong/ngay voi cell_name
        #     = sentinel "__ALL_CELLS__" (gia tri da gop moi cell). Do la cho
        #     CUOI CUNG con sot lai cua cach "gop chung moi cell" - da bo o moi
        #     noi khac. Gio 1 dong/CELL/ngay, dung ten cell that.
        # (2) DU 15 NGAY thay vi 9: ban cu chi lay 2 ngay cuoi cua cua so truoc
        #     (`sorted(before_dates)[-2:]`) vi chi phuc vu chart. Gio luu du
        #     T-7..T-1 de snapshot THAY THE duoc loi goi API - thieu ngay truoc
        #     thi van phai goi CTS/CEM de tinh avg_before.
        #
        # NGAY T (period="cr_day") - MOI: no lan CA TRUOC va SAU thoi diem doi
        # RF trong cung 1 ngay nen KHONG dung de danh gia (khong thuoc before
        # cung khong thuoc after), nhung hien len chart thi co ich - nguoi doc
        # thay duoc DUNG moc thay doi. Da do that tren session 1811 (CR 13/08):
        # CA CTS lan CEM deu co du lieu ngay T.
        # Ten "cr_day" KHOP tu vung FE da dung (DayGroup = before|cr_day|after)
        # - dat ten khac se tao 2 ten cho cung 1 thu.
        # Tinh bang diem_snapshot_theo_cua_so() (domain/services/
        # evaluation_service.py, gop chung 09/2026) - KHONG tai dung *_by_date
        # o tren (nhung cai do da GOP CHEO CELL de tinh avg cap session, khong
        # con biet cell nao).
        ngay_cr = cr_day_start.strftime("%Y-%m-%d")
        qos_points = diem_snapshot_theo_cua_so(
            "qos", "qos_score", qos_before_raw, before_dates, qos_after_raw, after_dates, ngay_cr
        )
        qoe_points = diem_snapshot_theo_cua_so(
            "qoe", "qoe_score", qoe_before_raw, before_dates, qoe_after_raw, after_dates, ngay_cr
        )
        if qos_points:
            await self._qos_snapshot_repo.upsert_many(session_id, qos_points)
        if qoe_points:
            await self._qoe_snapshot_repo.upsert_many(session_id, qoe_points)

        # Gia dinh #11 - BUSINESS_RULES.md SS8.3, CO CAN CU: FAIL -> tao alert_log
        if qoe_eval.result == "FAIL":
            await self._alert_use_case.check_qoe_degraded(session_id, qoe_eval.avg_before, qoe_eval.avg_after)
        if qos_eval.result == "FAIL":
            await self._alert_use_case.check_qos_degraded(session_id, qos_eval.avg_before, qos_eval.avg_after)

        return EvaluationResult(
            session_id=session_id,
            qoe_result=qoe_eval.result,
            qos_result=qos_eval.result,
            qoe_before=qoe_eval.avg_before,
            qoe_after=qoe_eval.avg_after,
            qos_before=qos_eval.avg_before,
            qos_after=qos_eval.avg_after,
        )

    async def execute_all_pending(self) -> list[EvaluationResult]:
        # Dung boi POST /jobs/evaluate-cr (api/routers/jobs.py, C1.8) - KHONG
        # thuoc ABC (xem gia dinh #6 dau file). page/size=None tren SessionFilter
        # -> khong phan trang, fetch toan bo (xem domain/ports/outbound/repo_ports.py).
        done = await self._session_repo.list(SessionFilter(status=CrStatus.DONE.value))
        eval_pending = await self._session_repo.list(SessionFilter(status=CrStatus.EVAL_PENDING.value))
        candidates = done.items + eval_pending.items

        # C1.4-fix10 (21072026) - executed_at gio doc len tu DB la tz-aware
        # (cot da la TIMESTAMPTZ), cutoff PHAI cung tz-aware de so sanh <=
        # khong bi crash "can't compare offset-naive and offset-aware".
        cutoff = datetime.now(timezone.utc) - timedelta(days=EVALUATION_DAYS)
        eligible = [s for s in candidates if s.executed_at is not None and s.executed_at <= cutoff]

        results: list[EvaluationResult] = []
        for session in eligible:
            try:
                results.append(await self.execute(session.id))
            except DomainError as e:
                # 1 session loi khong duoc lam hong ca batch (n8n chay hang ngay,
                # session loi se duoc thu lai ngay hom sau vi van con EVAL_PENDING/
                # DONE, KHONG bi bo qua vinh vien). Bao gom ca
                # CrEvaluationInProgressError (gia dinh #5) - truong hop nay la
                # BINH THUONG (race voi 1 lan chay khac), khong phai loi that.
                logger.warning(
                    "Loi khi evaluate 1 session, bo qua tiep tuc batch",
                    extra={"session_id": session.id, "error": str(e)},
                )

        # !!! CODE CHET TRONG DUONG CHAY BINH THUONG (tu 16/08, cach C): session
        # KHONG con vao EVAL_PENDING nua - INSUFFICIENT_DATA di THANG sang
        # KHONG_DU_DU_LIEU (xem nhanh set status o execute()). GIU vong lap nay
        # de TUONG THICH NGUOC voi cac dong EVAL_PENDING DA TON TAI trong DB (vd
        # session 553). Khi da chuyen het cac dong cu thi co the bo.
        #
        # CO Y KHONG mo rong alert nay sang KHONG_DU_DU_LIEU: alert cu bao "cho
        # qua lau" (van con hy vong co du lieu), con KHONG_DU_DU_LIEU la ket
        # luan CUOI - khong co gi de cho nen khong co gi de canh bao theo thoi
        # gian. Muon bao thi phai la 1 canh bao KHAC han ve ban chat.
        #
        # BUSINESS_RULES.md SS8.4/SS13 - EVAL_PENDING > 30 ngay -> alert admin.
        # Check tren TOAN BO session dang EVAL_PENDING (khong chi "eligible" o
        # tren, vi 1 session co the da EVAL_PENDING tu lau nhung khong nam
        # trong dot eligible hom nay neu logic INSUFFICIENT_DATA lai xay ra -
        # gia dinh #11, xem application/alert_use_case.py).
        # C1.4-fix10 - cung ly do voi cutoff o tren, giu tz-aware de tru
        # (now - session.executed_at) khong bi crash.
        now = datetime.now(timezone.utc)
        for session in eval_pending.items:
            if session.executed_at is None:
                continue
            days_pending = (now - session.executed_at).days
            if days_pending > EVAL_PENDING_TOO_LONG_DAYS:
                await self._alert_use_case.check_eval_pending_too_long(session.id, days_pending)

        return results
