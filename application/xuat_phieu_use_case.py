"""
XuatPhieuUseCase — ghep 28 field SaveCellClmPayload tu nguon DA CO (tram +
danh gia QoS + mac dinh), goi ISaveCellClmGateway, luu cr_phieu.
Tu: yeu cau truc tiep user (KHOI 3a/5 SaveCellClm). Qoe/Ceitsd="0" TAM - noi
SOC o KHOI 3b (chua lam).

SUA (yeu cau truc tiep user, doi HOAN TOAN tieu chi danh gia QoS dat/khong
dat) - bo nguong tuyet doi _QOS_KPI_THRESHOLD=3.0 (so 1 diem QoS min don le)
da tu chon o ban dau, thay bang tieu chi MOI: chenh lech TB QoS 7 ngay TRUOC
CR - TB QoS 7 ngay SAU CR. Chenh lech <= 0.2 -> DAT (KHONG xuat phieu).
Chenh lech > 0.2 -> KHONG DAT (xuat phieu). Tai dung EvaluationService (domain
service DA CO, dung cho QoE/QoS PASS/FAIL cap session BUSINESS_RULES.md SS8.3)
voi threshold=-0.2 rieng (KHAC -0.1 mac dinh cua session-level) thay vi tu
viet lai cong thuc avg/nguong du lieu tu dau.

SUA (KHOI 4a/5, yeu cau truc tiep user) - doc isError/status_code that tu CTS
de quyet SUCCESS/FAILED, trich phieu_id (ticketId) tu response.data, giu
nguyen cts_response tho de router tra ve FE "khong nuot loi" (BUOC 1 dac ta).
Loi ghi cr_phieu SAU KHI POST thanh cong (network/DB) KHONG duoc lam mat
phieu_id da co - bat rieng, tra ve kem db_save_warning (BUOC 2 dac ta).

SUA (V2, 12/08 - yeu cau truc tiep user) - BO HOAN TOAN tham so dry_run. Moi
lan goi gateway deu POST THAT len TTS. Giai doan quan sat da xong, giu them 1
duong chay thu chi lam moi cho phai mang theo 2 nhanh (va tung gay hieu nham
"da xuat phieu" tren UI). Bat/tat job van con SCHEDULER_ENABLED.

SUA (V3, 12/08 - yeu cau truc tiep user) - RETRY PHAN LOAI LOI ngay trong 1
luot goi: loi mang/timeout va 5xx thi thu lai toi XUAT_PHIEU_MAX_RETRY lan,
con 4xx / 200+isError (loi du lieu, loi nghiep vu) thi DUNG NGAY vi thu lai
chac chan hong y het. Xem _goi_gateway_co_retry().

SUA (V4, 12/08 - yeu cau truc tiep user) - cell KHONG duoc xuat (vuot tran 10
hoac het luot thu) gio CO dong cr_phieu rieng thay vi chi nam trong
job_run_log.chi_tiet - de nguoi van hanh loc/sap xep/xu ly tay tren UI.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from domain.entities.cr_session import CrStatus
from domain.errors import (
    CrSessionNotFoundError,
    PhieuDaXoaError,
    QoeDataInsufficientError,
    SaveCellClmApiError,
    TramNotFoundError,
)
from domain.ports.inbound.use_case_ports import IGetQosSparklineUseCase, IXuatPhieuUseCase, XuatPhieuResult
from domain.ports.outbound.gateway_ports import ISaveCellClmGateway
from domain.ports.outbound.repo_ports import (
    ICrAffectedCellsRepo,
    ICrPhieuRepo,
    ICrSessionRepo,
    IEnodebRepo,
    IJobRunLogRepo,
    SessionFilter,
)
from domain.services.evaluation_service import (
    MIN_DAYS_REQUIRED,
    MUC_TOI_THIEU,
    EvaluationService,
    do_te_cua,
    khoa_uu_tien_xuat_phieu,
)
from domain.services.loai_tram import LOAI_TRAM_SMALL_CELL, loai_tram_tu_ten_cell

load_dotenv()
logger = logging.getLogger(__name__)

# C1.4-fix8 (evaluate_cr_use_case.py) - VN khong co DST nen offset co dinh +7h
# la du chinh xac. Dung LAI PATTERN da co (khong tao cach lam moi), moi file
# tu dinh nghia hang so nay (quy uoc da co san trong project, xem sha512_auth.py/
# xml_builder.py/evaluate_cr_use_case.py).
_GMT7 = timezone(timedelta(hours=7))


def _to_gmt7(dt_utc: datetime) -> datetime:
    # Giong het _to_gmt7() trong evaluate_cr_use_case.py - dt_utc la naive
    # (executed_at luu UTC, khong tzinfo), phai gan tzinfo=UTC tuong minh
    # truoc astimezone(), Python khong tu suy duoc mui gio tu datetime naive.
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(_GMT7)


def _loc_diem_flat_theo_ngay(points: list[dict], allowed_dates: set[str]) -> list[dict]:
    """Loc 1 danh sach diem THO (1 cell, [{"time":.., "qos":..}]) chi giu diem
    co ngay nam trong allowed_dates.

    Ban RIENG cho shape "1 cell/list phang" (khac
    domain/services/evaluation_service.py::loc_diem_theo_ngay() danh cho shape
    "nhieu cell/{"cell_name":..,"metrics":[..]}" cua CEM/CDS) - dung khi fetch
    CTS RONG hon cua so danh gia (mo rong sang ngay T de luu period="cr_day",
    xem _danh_gia_qos_cell()) nhung avg_after PASS/FAIL van phai gioi han DUNG
    T+1..T+7.
    """
    return [p for p in points if p.get("time", "")[:10] in allowed_dates]


def _diem_qos_de_luu(cell_name: str, points: list[dict], period: str) -> list[dict]:
    """Diem tho tu CTS -> dang upsert_many(): 1 dong/cell/NGAY.

    CTS tra nhieu diem trong 1 ngay (moi gio 1 diem) nhung bang snapshot khoa
    UNIQUE theo (session, cell, ngay, period) nen phai gop TRUNG BINH THEO NGAY
    truoc - dung cong thuc cua _daily_averages(), chi khac la giu lai ngay.
    """
    theo_ngay: dict = {}
    for p in points:
        gia_tri = p.get("qos")
        if gia_tri is None:
            continue
        theo_ngay.setdefault(p["time"][:10], []).append(gia_tri)
    return [
        {
            "cell_name": cell_name,
            "snapshot_date": date.fromisoformat(ngay),
            "qos_score": sum(vals) / len(vals),
            "period": period,
        }
        for ngay, vals in theo_ngay.items()
    ]


def _daily_averages(points: list[dict], value_key: str = "qos") -> list[float]:
    # Gop cac diem QoS CUNG 1 ngay lich thanh 1 trung binh/ngay - CTS co the
    # tra hourly du granularity="day" (API_CONTRACTS.md SS2 dong 175), khong
    # gop truoc se dem SAI so "ngay co data" khi EvaluationService kiem tra
    # MIN_DAYS_REQUIRED (vd 1 ngay co 3 diem hourly se bi dem thanh 3 "ngay").
    # Ban rut gon cua _daily_averages_dict() trong evaluate_cr_use_case.py -
    # KHONG can loc allowed_dates o day vi from_dt/to_dt truyen thang xuong
    # CTS da dung dung cua so can (khong co nhieu use case dung chung ham nay
    # voi nhieu cua so ngay khac nhau nhu evaluate_cr_use_case.py).
    #
    # value_key them 16082026: GetQoeCellsUseCase tai dung ham nay cho QoE (diem
    # CEM co key "qoe" thay vi "qos"). MAC DINH "qos" nen moi cho goi cu KHONG
    # phai sua, khong doi hanh vi. Dung tien le _daily_averages_dict(value_key)
    # da co san trong evaluate_cr_use_case.py - KHONG chep ham ra lam ban thu 2
    # (2 ban se lech nhau khi 1 ben sua).
    by_date: dict[str, list[float]] = {}
    for point in points:
        date_key = point["time"][:10]  # "YYYY-MM-DD"
        by_date.setdefault(date_key, []).append(point[value_key])
    return [sum(vals) / len(vals) for vals in by_date.values()]


# TU GIA DINH - CAN XAC NHAN: "chua du du lieu" (dac ta BUOC 4: "chua du 7
# ngay truoc HOAC sau") duoc hieu la tai dung NGUONG DA CO cua EvaluationService
# (MIN_DAYS_REQUIRED=5, BUSINESS_RULES.md SS8.2/8.4 - "chua du 7 ngay" trong dac
# ta la cach noi tat cua "chua du du lieu trong cua so 7 ngay", KHONG phai doi
# hoi CHINH XAC ca 7/7 ngay - CTS thuong xuyen thieu vai ngay, "missing day la
# binh thuong" theo API_CONTRACTS.md SS2), thay vi tu dat 1 nguong MOI (vd bat
# buoc du 7/7) chua co can cu nao trong docs. PHAI xac nhan lai neu y dinh that
# la can DU CA 7 NGAY.
# SUA 04092026 (yeu cau nghiep vu): -0.2 -> -0.5. Nay la "tut qua 0.5 diem thi
# KHONG DAT"; tut DUNG 0.5 van DAT.
# Di kem: MUC_TOT 4.0 (ve CUU "tut nhieu nhung van tot") da doi thanh
# MUC_TOI_THIEU 3.0 (SAN "duoi muc nay la khong dat ngay") - 2 dieu kien gio
# DOC LAP, xem domain/services/evaluation_service.py.
# SUA 03/10/2026 - DOI DAU thanh SO DUONG (xem domain/services/
# evaluation_service.py muc "SUA 03/10/2026" dau file): delta gio la
# avg_before - avg_after (duong = tut), FAIL khi delta > 0.5 (truoc day la
# delta < -0.5).
_XUAT_PHIEU_QOS_THRESHOLD_DELTA = 0.5  # tuong duong "chenh lech truoc-sau <= 0.5"

_DEFAULT_VENDOR = "NOKIA"

# JOB TU DONG buoc 2/4 (yeu cau truc tiep user) - so ngay sau CR moi bat dau
# xuat phieu, va tran so phieu 1 session/1 luot. Doc tu .env giong
# EVALUATION_DAYS (application/evaluate_cr_use_case.py) - KHONG hardcode, van
# hanh co the doi ma khong sua code.
#
# VI SAO KHONG dung lai EVALUATION_DAYS (21): 2 moc nghiep vu KHAC NHAU - 21
# ngay la de danh gia PASS/FAIL cap session (BUSINESS_RULES.md SS8), 7 ngay la
# du dai cua so QoS "T+1..T+7" ma tieu chi xuat phieu can. Dung chung 1 bien se
# lam doi 1 moc keo theo moc kia.
# Mac dinh 8 (KHONG phai 7 - sua 12/08): CTS chi co data den HET HOM QUA (T-1).
# CR ngay 20 -> cua so danh gia sau la 21..27; sang ngay 27 CTS moi co data den
# 26 = 6/7 ngay, sang ngay 28 moi du ca 21..27. Danh gia chi dien ra MOT LAN
# (xuat phieu xong cell bi loai khoi vong quet) nen phai du data TRUOC khi ket
# luan - xem giai thich day du trong .env.example.
XUAT_PHIEU_AFTER_DAYS = int(os.getenv("XUAT_PHIEU_AFTER_DAYS", "8"))

# SUA 03/10/2026 (yeu cau truc tiep user) - QUET BU. Truoc day job CHI quet
# DUNG 1 ngay CR ("==" o _lay_session_du_dieu_kien()) - neu job khong chay
# (server down ca ngay, deploy loi...) thi ngay CR do MAT VINH VIEN, khong
# bao gio duoc quet lai (ca THAT: session 7296, xem khao sat 02/10/2026). Mo
# RONG dieu kien thanh 1 CUA SO [hom_nay - AFTER_DAYS - QUET_BU, hom_nay -
# AFTER_DAYS] - job tu dong "bat" lai duoc nhung ngay da lo trong vong
# QUET_BU_NGAY ngay gan nhat, KHONG can con nguoi phai chay tay POST
# /jobs/xuat-phieu-auto moi lan nua. VAN IDEMPOTENT: dieu kien chon session
# them "xuat_phieu_at IS NULL" (truoc day dieu kien nay KHONG can thiet vi
# "==" tu nhien chi khop 1 ngay DUY NHAT trong doi 1 session; gio PHAI co
# tuong minh, neu khong 1 session se bi quet lai MOI NGAY trong suot ca cua
# so QUET_BU_NGAY, tao phieu trung).
XUAT_PHIEU_QUET_BU_NGAY = int(os.getenv("XUAT_PHIEU_QUET_BU_NGAY", "14"))
# SUA 04/10/2026 (quyet dinh van hanh, THAY THE hoan toan tran theo SESSION
# cu - bo XUAT_PHIEU_MAX_PER_SESSION): tran gio tinh THEO SECTOR cua tram
# tat, khong phai theo ca session. TAI SAO: 1 session co the anh huong NHIEU
# sector doc lap nhau (vd tram 4 sector) - tran theo session cu (6/session du
# co bao nhieu sector) de sector nho (it cell) "an het suat" cua sector khac,
# trong khi sector kia co the con nhieu cell te hon dang cho. Tran theo
# sector cong bang hon: MOI sector duoc toi da 2 phieu, tram 4 sector toi da
# 8 - khong con tranh suat xuyen sector.
#
# Default 2 (so voi 6 cu cho CA session) - vi don vi tinh da doi tu "session"
# sang "sector" (1 session co the co 1-4+ sector). Doi DEFAULT trong code
# KHONG tu dong doi tran tren server: .env cua server .196 dang ghi gia tri
# rieng va os.getenv() uu tien gia tri do - phai sua tay .env tren server,
# xem checklist trong docs/DEPLOY.md.
XUAT_PHIEU_MAX_PER_SECTOR = int(os.getenv("XUAT_PHIEU_MAX_PER_SECTOR", "2"))

# So lan POST THAT toi da cho 1 cell. Phieu FAILED do loi DU LIEU (vd CTS tra
# 400 vi field sai) se that bai y het o moi lan chay - khong gioi han thi job
# thu lai VO HAN, rac log va lam nguoi van hanh mat long tin vao canh bao.
# Cham tran -> de nguoi xu ly tay (giong cell vuot tran 10).
#
# V3 (12/08): so nay gio dung cho CA HAI cho, cung mot y nghia "so lan da lam
# phien CTS cho cell nay":
#   - so lan thu lai TRONG 1 luot goi execute() (_goi_gateway_co_retry)
#   - tran tich luy tren cot cr_phieu.so_lan_thu (cell_het_luot_thu)
# Dung chung 1 bien de khong bao gio co chuyen "retry trong luot 5 lan nhung
# tran tich luy la 3" - cell se bi khoa ngay o luot dau, rat kho hieu.
XUAT_PHIEU_MAX_RETRY = int(os.getenv("XUAT_PHIEU_MAX_RETRY", "3"))

# V4 (12/08) - 2 trang_thai cho cell KHONG duoc xuat tu dong. Truoc day cac
# cell nay CHI nam trong job_run_log.chi_tiet (JSONB) nen khong loc/sap xep/
# danh dau da xu ly duoc tren UI - nguoi van hanh phai mo tung luot chay job ra
# doc. Ghi thanh dong cr_phieu that thi chung nam chung bang voi phieu da xuat,
# dung duong query san cua GET /phieu.
#
# KHONG phai loi: day la ket qua HOP LE cua vong quet ("job co y khong xuat"),
# khac FAILED (da POST va CTS tu choi).
TRANG_THAI_VUOT_GIOI_HAN = "KHONG_XUAT_VUOT_GIOI_HAN"
TRANG_THAI_HET_LUOT_THU = "KHONG_XUAT_HET_LUOT_THU"

# Cach C (16082026, yeu cau truc tiep user) - trang thai CUOI cho "thieu du
# lieu", dong ho voi 2 gia tri tren. 24 ky tu, vua VARCHAR(30).
#
# VI SAO PHAI CO: truoc day nhanh INSUFFICIENT_DATA chi `continue` voi ly do
# "lan chay sau se xet lai". Ly do do SAI tu khi doi sang PA A (12/08): job quet
# DUNG 1 ngay (ngay CR == hom nay - XUAT_PHIEU_AFTER_DAYS), KHONG phai "<=" -
# nen KHONG CO luot sau. Cell bi bo qua la MAT VINH VIEN va khong de lai dau
# vet nao: khong dong cr_phieu, chi 1 dong log INFO se troi di.
TRANG_THAI_THIEU_DU_LIEU = "KHONG_XUAT_THIEU_DU_LIEU"

# NoiDung trong payload phieu. Phan GOC giu nguyen y het phieu that 19207 da
# tao thanh cong; chi GHEP THEM ve chi tieu vi pham o cuoi - khong doi cau truc
# cau, khong doi tu ngu da duoc CTS/TTS chap nhan.
_NOI_DUNG_GOC = "Cell CLK do gan tram di doi"
_NOI_DUNG_THEO_NGUON = {
    "QOS": "khong dat chi tieu QoS",
    "QOE": "khong dat chi tieu QoE",
    "CA_HAI": "khong dat ca 2 chi tieu QoS va QoE",
}

# 3 gia tri cua cr_session.xuat_phieu_ket_qua (migration e98069b2cd40, 14/08).
# Ghi vao cr_session chu KHONG suy tu cr_phieu: truong hop TAT CA CELL DAT tao ra
# 0 dong cr_phieu, khong phan biet duoc voi "chua toi luot quet" (cung 0 dong) -
# va voi PA A thi session do KHONG BAO GIO duoc quet lai de sua nham lan do.
KET_QUA_DA_XUAT = "DA_XUAT"  # co it nhat 1 phieu SUCCESS trong luot nay
KET_QUA_KHONG_CAN_XUAT = "KHONG_CAN_XUAT"  # 0 cell KHONG DAT -> khong can phieu nao
KET_QUA_LOI = "LOI"  # session nem exception, HOAC co cell can phieu ma khong xuat duoc cai nao

# WHITELIST status cua cr_session duoc phep quet (viec 2b, 12/08).
#   DONE         - CR chay xong, chua danh gia. Truong hop pho bien nhat.
#   EVALUATED    - da xong VA da danh gia du lieu -> cang chac chan la CR that
#                  su ket thuc, cell KHONG DAT cang dang tin.
#   EVAL_PENDING - da xong, chi THIEU du lieu QoE/QoS luc danh gia cap session.
#                  Van co the co cell KHONG DAT theo tieu chi QoS rieng cua xuat
#                  phieu (2 nguong doc lap: -0.1 cap session vs -0.2 xuat phieu).
#
#                  !!! CODE CHET TRONG DUONG CHAY BINH THUONG (tu 16/08, cach C):
#                  session KHONG con vao EVAL_PENDING nua - INSUFFICIENT_DATA di
#                  THANG sang KHONG_DU_DU_LIEU. GIU nhanh nay de TUONG THICH
#                  NGUOC voi cac dong EVAL_PENDING DA TON TAI trong DB (vd
#                  session 553). Khi da chuyen het cac dong cu thi co the bo.
#
#                  KHONG them KHONG_DU_DU_LIEU vao day: session chi vao trang
#                  thai do o ngay 21 (EvaluateCrUseCase), da qua moc quet phieu
#                  ngay 8 tu 13 ngay - nam ngoai dien quet bat ke status.
# KHONG lay: PENDING (chua xu ly), RUNNING (dang chay 18 buoc), FAILED (CR loi -
# khong co thay doi mang nao de danh gia), EVALUATING (trang thai thoang qua).
#
# VI SAO WHITELIST CHU KHONG BLACKLIST: neu sau nay them status moi ma quen sua
# cho nay thi hau qua 2 huong lech nhau rat xa:
#   - Whitelist: job BO SOT session moi -> nguoi xuat tay duoc, mat vai phut.
#   - Blacklist: status moi TU DONG lot vao dien quet -> job POST PHIEU THAT cho
#     session chua du dieu kien -> phai nho CTS xoa phieu, mat uy tin.
# Day la WRITE API tao phieu that nen chon huong fail-safe.
#
# !!! THEM STATUS MOI VAO CrStatus (domain/entities/cr_session.py) THI PHAI XEM
# !!! XET LAI MUC NAY - mac dinh status moi se KHONG duoc quet.
XUAT_PHIEU_STATUS_WHITELIST = (
    # PARTIAL_SUCCESS (18082026) - CR DA CHAY, chi mot so DN khong provision
    # duoc. Cell cua tram hong VAN duoc danh gia binh thuong: phieu chi la de
    # nguoi di kiem tra, va cell do that su co the da te di (tram khong doi
    # duoc tham so RF nhu du dinh).
    CrStatus.PARTIAL_SUCCESS.value,
    CrStatus.DONE.value,
    CrStatus.EVALUATED.value,
    CrStatus.EVAL_PENDING.value,
)


def _trang_thai_luot_chay(so_thanh_cong: int, so_that_bai: int) -> str:
    """Quyet dinh trang_thai cua 1 luot chay job xuat phieu.

    === VI SAO PHAI SUA (B3) ===
    Truoc day luot chay nao khong nem exception deu duoc ghi DONE. Ket qua:
    job_run_log 977/978/980/981/1010 deu DONE trong khi 0 phieu thanh cong va
    94 phieu that bai. DONE nghia la "chay xong khong van de" - POST 20 phieu
    hong het ma bao DONE la NOI DOI.
    Nang hon: dong canh bao tren FE doc CHINH trang_thai nay de quyet dinh co
    keu hay khong, nen no cung im lang theo. Do la ly do 8 NGAY khong ai biet
    job dang hong.

    Khong nem exception KHONG dong nghia voi khong co van de: job van chay het
    vong lap binh thuong khi CTS tu choi tung phieu mot.

    PARTIAL: co ca thanh cong lan that bai - khong the goi la DONE (co viec hong
    can nguoi xem) cung khong the goi la FAILED (phan lon co the da chay duoc).
    """
    if so_that_bai > 0 and so_thanh_cong == 0:
        return "FAILED"
    if so_that_bai > 0 and so_thanh_cong > 0:
        return "PARTIAL"
    # 0 that bai - ke ca 0 thanh cong (khong co viec de lam) deu la chay xong
    # binh thuong
    return "DONE"


@dataclass
class QosCellEvaluation:
    """Ket qua danh gia QoS cua 1 cell - dung chung boi execute() (xuat 1 cell)
    va execute_all_pending() (xep hang cell truoc khi chon).

    Dung dataclass thay vi tuple: execute_all_pending() can ca do te (de bao
    cao/hien thi - SUA 09/2026: KHONG con dung de sort, xem docstring
    do_te property duoi day) lan so ngay co data (de log ly do bo qua) -
    tuple 4 phan tu se rat de doc nham thu tu o cho goi.
    """

    qos_eval: object  # MetricEvaluation (domain/services/evaluation_service.py)
    after_points: list[dict]
    so_ngay_before: int
    so_ngay_after: int

    @property
    def do_te(self) -> float:
        """Muc do TE cua cell theo QoS. Cang LON cang te.

        SUA 04092026: khong con la (before - after) thuan. Cong thuc va ly do
        nam o domain/services/evaluation_service.py::do_te_cua() - dat o domain
        vi la mot phan cua nghiep vu danh gia, va QoE dung CHUNG ham do.

        SUA 09/2026: do_te_cua() KHONG con la luat XEP HANG - thu tu xuat
        phieu gio do khoa_uu_tien_xuat_phieu() quyet dinh (nhom truoc, roi
        do_giam, roi avg_after). do_te VAN duoc tinh va bao cao (job_run_log,
        API xem truoc) nhung CHI de nguoi doc hieu muc do te, KHONG con dung
        de suy ra thu tu."""
        return do_te_cua(self.qos_eval)


# === QoE NGANG HANG QoS (17082026) ===
NGUON_QOS = "QOS"
NGUON_QOE = "QOE"
NGUON_CA_HAI = "CA_HAI"


def _nguon_khong_dat(qos_result: str, qoe_result: str) -> str:
    """Chi so nao lam cell KHONG DAT -> ghi vao cr_phieu.nguon_khong_dat.

    Chi goi khi DA BIET co it nhat 1 ve FAIL (caller da loc). INSUFFICIENT_DATA
    o 1 ve KHONG duoc tinh la "khong dat" - khong ket luan duoc thi khong ket
    toi, xem _do_te_max().
    """
    qos_fail = qos_result == "FAIL"
    qoe_fail = qoe_result == "FAIL"
    if qos_fail and qoe_fail:
        return NGUON_CA_HAI
    return NGUON_QOS if qos_fail else NGUON_QOE


def _dong_xem_truoc(
    cell_name: str, do_te: float, nguon: str, qoe_wrapper, qos_wrapper, khoa: tuple, sector: int | None
) -> dict:
    """1 dong cell trong ket qua xem truoc.

    avg_before/avg_after lay theo chi so LAM CELL KHONG DAT: nguon=QOE thi lay
    so QoE, con lai (QOS/CA_HAI) lay so QoS. VI SAO khong luon lay QoS: cell
    chi FAIL o QoE thi 2 so QoS cua no van "dat" - hien len se mau thuan voi
    chinh cot nguon ngay ben canh, nguoi doc tuong he thong tinh sai.

    nhom/do_giam (them 09/2026, cung mau voi job_run_log.chi_tiet o
    _xu_ly_mot_session()): khoa da duoc tinh SAN trong _danh_gia_va_xep_hang()
    (khong tinh lai), CHI trich xuat 2 thanh phan de nguoi xem truoc thay
    DUNG ly do thu tu - truoc ban sua nay xem truoc chi tra do_te, ma do_te
    KHONG con quyet dinh thu tu (xem khoa_uu_tien_xuat_phieu()) nen nguoi
    xem se khong hieu tai sao cell do_te thap hon lai dung truoc cell do_te
    cao hon.
    """
    eval_chinh = qoe_wrapper.qoe_eval if nguon == NGUON_QOE and qoe_wrapper else qos_wrapper.qos_eval
    return {
        "cell_name": cell_name,
        "nguon": nguon,
        "do_te": round(do_te, 3),
        "avg_before": eval_chinh.avg_before,
        "avg_after": eval_chinh.avg_after,
        # nhom 0 = duoi MUC_TOI_THIEU (uu tien tuyet doi), 1 = con lai.
        "nhom": khoa[0],
        "do_giam": round(-khoa[1], 3),
        # sector (THEM 04/10/2026) - sector cua TRAM TAT, None neu khong suy
        # duoc tu huong_id (xem domain/services/neighbor_cell_filter.py::
        # filter_affected()). De nguoi xem truoc doi chieu dung tran 2/sector.
        "sector": sector,
    }


def cua_so_danh_gia(executed_at) -> dict:
    """Cua so danh gia quanh ngay CR, theo LICH GMT+7. Tach ra 04092026.

    Tra {"ngay_cr", "before_from", "before_to", "after_from", "after_to"}.

    === VI SAO TACH ===
    Cong thuc nay dang bi VIET LAI o 3 cho: XuatPhieuUseCase._danh_gia_qos_cell,
    GetQoeCellsUseCase.execute, GetQosCellsUseCase.execute - va gio ca 2 router
    cung can no de tra cua so ra API. 5 ban sao cua cung 1 cong thuc la cach
    chac chan nhat de chung lech nhau (da xay ra 2 lan voi luat danh gia).

    .date() PHAI lay SAU khi quy ve GMT+7: executed_at luu UTC (TIMESTAMPTZ),
    lay .date() thang tren UTC se lech 1 ngay voi CR chay trong khung UTC
    17:00-23:59 - dung bug C1.4-fix8 da sua.
    """
    vn = _to_gmt7(executed_at)
    cr_day_start = datetime(vn.year, vn.month, vn.day)
    return {
        "ngay_cr": cr_day_start.date(),
        "before_from": cr_day_start - timedelta(days=7),
        "before_to": cr_day_start - timedelta(days=1),
        "after_from": cr_day_start + timedelta(days=1),
        "after_to": cr_day_start + timedelta(days=7),
    }


def danh_gia_qos_tu_diem(before_points, after_points, evaluation_service) -> "QosCellEvaluation":
    """Cong thuc danh gia QoS 1 cell tu DIEM DA CO. Tach ra 04092026.

    === VI SAO TACH ===
    GET /sessions/{id}/qos-cells (doc) va XuatPhieuUseCase (ghi) phai cho ra
    CUNG KET LUAN cho cung mot cell. Cach duy nhat bao dam la dung CHUNG mot
    ham - khong phai "copy roi nho sua ca hai".
    Bai hoc that: FE tung nhan ban cong thuc nay trong qosEvaluation.ts va da
    TROI KHOI BE 2 LAN; lan gan nhat thieu han mot ve cua luat nen bao cell
    117449 (4.83 -> 4.33) la KHONG DAT trong khi BE ket luan DAT.

    Nhan DIEM THO (chua gop ngay) chu khong nhan avg: viec gop theo ngay
    (_daily_averages) cung la mot phan cua luat - CTS tra hourly nen ai gop
    khac di se dem sai so ngay va lam lech ca nguong MIN_DAYS_REQUIRED.
    """
    before_daily = _daily_averages(before_points)
    after_daily = _daily_averages(after_points)

    # threshold=-0.2 (KHAC -0.1 mac dinh cua QoE/QoS PASS/FAIL cap session,
    # BUSINESS_RULES.md SS8.3) - 2 dung sai DOC LAP nhau (yeu cau truc tiep
    # user). MIN_DAYS_REQUIRED=5 (dinh nghia trong EvaluationService, tai dung
    # nguyen) quyet dinh INSUFFICIENT_DATA.
    qos_eval = evaluation_service.evaluate(
        before_daily, after_daily, threshold=_XUAT_PHIEU_QOS_THRESHOLD_DELTA
    )
    return QosCellEvaluation(
        qos_eval=qos_eval,
        after_points=after_points,
        so_ngay_before=len(before_daily),
        so_ngay_after=len(after_daily),
    )


def _cau_ly_do_dat(qos_eval) -> str:
    """Cau giai thich cell DAT - neu CA HAI dieu kien deu qua (04092026).

    Tu 04092026 luat co 2 dieu kien DOC LAP, PASS nghia la qua CA HAI:
      1. avg_after >= MUC_TOI_THIEU (3.0)
      2. tut khong qua 0.5 diem
    Nen cau chu phai neu CA HAI so - khong con chuyen "dat nho ve nao".

    Truoc do (khi con nhanh CUU) ham nay chon 1 trong 2 cau; cach do khong con
    dung nua vi PASS khong con nhieu duong."""
    before, after = qos_eval.avg_before, qos_eval.avg_after
    if before is None or after is None:
        return "Cell dat tieu chi QoS - khong can xuat phieu"

    # SUA 18/10/2026: lech da lam tron (CHINH so da so nguong), khong tru lai.
    chenh = qos_eval.lech
    # SUA 03/10/2026: _XUAT_PHIEU_QOS_THRESHOLD_DELTA gio DA la so duong
    # (0.5) - KHONG con doi dau o day nua (truoc day hang so goc la am nen
    # phai doi dau moi ra 0.5 de in cau nay).
    nguong = _XUAT_PHIEU_QOS_THRESHOLD_DELTA
    return (
        f"Cell dat: TB sau {after:.2f} >= {MUC_TOI_THIEU:.1f} (muc toi thieu) "
        f"va chenh lech TB truoc-sau {chenh:.2f} <= {nguong:.1f} "
        "- khong can xuat phieu"
    )

def _do_te_max(qos_eval_wrapper, qoe_eval_wrapper) -> float:
    """Do te = MAX cua 2 muc tut, dung de xep hang "te nhat truoc".

    VI SAO MAX chu khong phai TRUNG BINH: cell tut 2.0 QoE + 0.0 QoS ra trung
    binh 1.0 - NGANG voi cell tut 1.0 ca hai chi so. Hai tinh huong do khac han
    nhau ve muc do gap (mot cai dang hong nang o 1 mat, mot cai suy giam deu).
    max phan anh dung "cell nao dang hong nang nhat", va do la thu quyet dinh ai
    duoc suat trong tran 10 phieu/session.

    Cung KHONG dung TONG: tong lam cell tut nhe ca 2 vuot len tren cell tut nang
    1 chi so - cung sai huong nhu trung binh.
    """
    # SUA 04092026: CA HAI chi so dung CHUNG do_te_cua() - truoc day QoE tinh
    # rieng bang -delta nen KHONG co ve "duoi san", cell QoE kem ma khong tut
    # bi xep sai hang y nhu QoS.
    do_te_qos = qos_eval_wrapper.do_te  # da goi do_te_cua() ben trong
    qoe_eval = qoe_eval_wrapper.qoe_eval if qoe_eval_wrapper is not None else None
    do_te_qoe = do_te_cua(qoe_eval)  # None (thieu du lieu) -> 0.0
    return max(do_te_qos, do_te_qoe)


def _extract_phieu_id(data) -> str | None:  # noqa: ANN001 - data la JSON tho tu CTS
    # DA XAC NHAN bang 1 lan POST THAT THANH CONG (phieu id=19177): response.data
    # la SO NGUYEN - chinh la id phieu tren TTS, KHONG phai dict boc ngoai. Da BO
    # cac nhanh doan hinh dang cu (dict co key "ticketId"/"id") vi gio da co mau
    # that, khong con phai phong thu mu.
    # Van ep str() vi XuatPhieuResult.phieu_id/cr_phieu.phieu_id khai bao kieu
    # str (VARCHAR(100) trong DB) - giu 1 kieu duy nhat xuyen suot, khong de int
    # lot xuong tang duoi.
    if data is None:
        return None
    return str(data)


class XuatPhieuUseCase(IXuatPhieuUseCase):
    def __init__(
        self,
        cr_phieu_repo: ICrPhieuRepo,
        cr_session_repo: ICrSessionRepo,
        cr_affected_cells_repo: ICrAffectedCellsRepo,
        enodeb_repo: IEnodebRepo,
        qos_sparkline_use_case: IGetQosSparklineUseCase,
        save_cell_clm_gateway: ISaveCellClmGateway,
        evaluation_service: EvaluationService,
        # JOB TU DONG buoc 2/4 - CHI execute_all_pending() dung. Optional (mac
        # dinh None) de moi cho tao XuatPhieuUseCase san co (router POST /phieu,
        # test cu) KHONG phai sua theo - xuat 1 cell khong lien quan gi den
        # lich su chay job.
        job_run_log_repo: IJobRunLogRepo | None = None,
        # QoE NGANG HANG QoS (17082026). Optional (mac dinh None) de moi cho tao
        # XuatPhieuUseCase san co (router POST /phieu, test cu) KHONG phai sua
        # theo - thieu no thi job chi danh gia QoS nhu truoc, khong vo.
        qoe_cells_use_case=None,
        # SNAPSHOT PER-CELL (20082026). Optional - thieu no thi job chay y het
        # nhu truoc, chi la khong luu lai duoc diem.
        qos_snapshot_repo=None,
    ):
        self._cr_phieu_repo = cr_phieu_repo
        self._cr_session_repo = cr_session_repo
        self._cr_affected_cells_repo = cr_affected_cells_repo
        self._enodeb_repo = enodeb_repo
        self._qos_sparkline_use_case = qos_sparkline_use_case
        self._save_cell_clm_gateway = save_cell_clm_gateway
        self._evaluation_service = evaluation_service
        self._job_run_log_repo = job_run_log_repo
        self._qoe_cells_use_case = qoe_cells_use_case
        self._qos_snapshot_repo = qos_snapshot_repo

    async def _lay_qoe_theo_cell(self, cr_session_id: int, luu_snapshot: bool = True) -> dict:
        """Danh gia QoE cho TOAN BO cell cua session trong 1 lan -> dict theo ten.

        Tra dict RONG (khong nem loi) khi khong co use case QoE hoac khi CEM loi:
        QoE la chi so THEM VAO, khong duoc lam hong duong QoS da chay on dinh tu
        truoc. Cell thieu QoE se roi vao nhanh "chi ket luan theo QoS".
        """
        if self._qoe_cells_use_case is None:
            return {}
        try:
            ket_qua = await self._qoe_cells_use_case.execute(
                cr_session_id, luu_snapshot=luu_snapshot
            )
            return {r.cell_name: r for r in ket_qua}
        except Exception as exc:  # noqa: BLE001 - CO Y bat rong, xem docstring
            logger.warning(
                "Job xuat phieu: danh gia QoE that bai cho ca session, tiep tuc CHI voi QoS",
                extra={"cr_session_id": cr_session_id, "loi": str(exc)},
            )
            return {}

    async def _danh_gia_qos_cell(
        self, cell_name: str, executed_at_vn: datetime, cr_session_id: int | None = None
    ) -> QosCellEvaluation:
        """Danh gia QoS 7 ngay TRUOC vs 7 ngay SAU CR cho 1 cell.

        after_points duoc tra kem de caller tinh Qos=min(7 ngay sau) ma KHONG
        goi CTS lan nua.

        cr_session_id (20082026) - truyen vao thi LUU snapshot diem vua lay.
        Xem _luu_snapshot_qos() ve ly do luu tai day.

        Tach ra o JOB TU DONG buoc 2/4: execute_all_pending() can BIET do te cua
        TUNG cell de xep hang truoc khi chon 10 cell - khong the goi execute()
        de biet (execute() da POST luon). Tach ham thay vi copy cong thuc de 2
        duong (xuat 1 cell qua router / job tu dong) KHONG BAO GIO lech tieu chi.
        """
        # Cua so tinh theo NGAY LICH GMT+7 cua executed_at - dung CHINH XAC
        # pattern da xac nhan/verify that trong EvaluateCrUseCase (C1.4-fix8),
        # khong tu nghi cach tinh moi. Tai dung GetQosSparklineUseCase (KHONG
        # goi lai gateway CTS truc tiep tu file nay).
        cr_day_start = datetime(executed_at_vn.year, executed_at_vn.month, executed_at_vn.day)
        before_from, before_to = cr_day_start - timedelta(days=7), cr_day_start - timedelta(days=1)
        after_from, after_to = cr_day_start + timedelta(days=1), cr_day_start + timedelta(days=7)
        after_dates = {(after_from + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
        ngay_cr = cr_day_start.strftime("%Y-%m-%d")

        before_points = await self._qos_sparkline_use_case.execute(
            cell_name, from_dt=before_from, to_dt=before_to
        )
        # Fetch tu cr_day_start (T) thay vi after_from (T+1) - GIONG
        # EvaluateCrUseCase/GetQoeCellsUseCase (D3, 09/2026), de co diem luu
        # period="cr_day". CTS nhan CA cua so trong 1 request (khac CEM 1
        # request/ngay) nen mo rong 1 ngay o day TON 0 REQUEST PHU.
        after_points_rong = await self._qos_sparkline_use_case.execute(
            cell_name, from_dt=cr_day_start, to_dt=after_to
        )
        # Cua so DANH GIA van la T+1..T+7 - loc lai TUONG MINH truoc khi tinh
        # avg, KHONG de diem ngay T lot vao PASS/FAIL (_daily_averages() cua
        # danh_gia_qos_tu_diem() KHONG tu loc allowed_dates).
        after_points = _loc_diem_flat_theo_ngay(after_points_rong, after_dates)

        # Cong thuc nam o danh_gia_qos_tu_diem() - DUNG CHUNG voi
        # GetQosCellsUseCase (GET /sessions/{id}/qos-cells). Method nay chi con
        # lo 2 viec rieng cua duong GHI: goi CTS lay diem, va luu snapshot.
        danh_gia = danh_gia_qos_tu_diem(before_points, after_points, self._evaluation_service)

        if cr_session_id is not None:
            await self._luu_snapshot_qos(
                cr_session_id, cell_name, before_points, after_points_rong, after_dates, ngay_cr
            )

        return danh_gia

    async def _luu_snapshot_qos(
        self,
        cr_session_id: int,
        cell_name: str,
        before_points: list[dict],
        after_points_rong: list[dict],
        after_dates: set[str],
        ngay_cr: str,
    ) -> None:
        """Upsert diem QoS THO (chua gop theo ngay) vua lay tu CTS vao
        qos_snapshot, LUON DU 3 period (before/cr_day/after - D3, 09/2026,
        cung mau hinh voi QoE - xem domain/services/evaluation_service.py::
        diem_snapshot_theo_cua_so()).

        === VI SAO LUU O DAY ===
        Job xuat phieu DA goi du CTS cho toan bo cell roi (34 request cho 17
        cell - CTS nhan CA cua so trong 1 request nen mo rong 1 ngay sang T
        KHONG doi so request, khac CEM 1 request/ngay) - luu them tai cho nay
        ton 0 REQUEST PHU. Neu de mot job/endpoint khac di lay lai de luu thi
        phai goi lai tung ay request.

        Va day la thoi diem du lieu DA ON DINH: job chay dung 1 lan/session sau
        T+7, ca 2 cua so T-7..T-1 va T+1..T+7 deu da nam tron trong qua khu,
        CTS khong bo sung gi nua. Luu som hon (vd ngay CR) se chup phai cua so
        con thieu ngay.

        after_points_rong PHAI la ket qua fetch TU cr_day_start (T) den T+7
        (xem _danh_gia_qos_cell()) - ngay T tach rieng cho period="cr_day" tai
        day, KHONG can truyen rieng gia tri ngay T.

        NUOT loi: cache hong khong duoc lam hong luot xuat phieu - do la viec
        chinh, con snapshot chi de xem lai bieu do.
        """
        if self._qos_snapshot_repo is None:
            return
        try:
            cr_day_points = [p for p in after_points_rong if p.get("time", "")[:10] == ngay_cr]
            after_points = _loc_diem_flat_theo_ngay(after_points_rong, after_dates)
            points = (
                _diem_qos_de_luu(cell_name, before_points, "before")
                + _diem_qos_de_luu(cell_name, cr_day_points, "cr_day")
                + _diem_qos_de_luu(cell_name, after_points, "after")
            )
            if points:
                await self._qos_snapshot_repo.upsert_many(cr_session_id, points)
        except Exception as exc:  # noqa: BLE001 - xem docstring
            logger.warning(
                "Khong luu duoc snapshot QoS, bo qua (khong anh huong xuat phieu)",
                extra={"cr_session_id": cr_session_id, "cell_name": cell_name, "loi": str(exc)},
            )

    # === V3 (12/08) - RETRY PHAN LOAI LOI ===

    @staticmethod
    def _nen_thu_lai(response: dict) -> bool:
        """CO nen POST lai cho response nay khong.

        CHI thu lai loi TAM THOI phia server. Loi do NOI DUNG gui len thi thu
        lai bao nhieu lan cung ra ket qua y het - chi lam phien CTS va keo dai
        luot chay cua job."""
        status_code = response.get("status_code")

        # 5xx = loi phia CTS/gateway (qua tai, restart, loi noi bo) - TAM THOI,
        # lan sau co the qua. Xet 5xx TRUOC isError: response 5xx thuong kem ca
        # isError, nhung khi da 5xx thi ban chat la loi HA TANG chu khong phai
        # loi nghiep vu -> phai roi vao nhanh retry.
        if isinstance(status_code, int) and status_code >= 500:
            return True

        # Moi truong hop con lai DUNG NGAY:
        #   - 4xx: CTS tu choi NOI DUNG request (field sai kieu, sai quyen...).
        #     Payload lan sau y het lan nay nen chac chan hong y het.
        #   - 200 + isError=true: loi NGHIEP VU. Bang chung that la dong
        #     cr_phieu id=82: "Bad Cell 4G-SSN104M12-HNI dang xu ly cua thang
        #     202607" - phieu cua thang do da ton tai, thu 100 lan van the.
        #   - status_code thieu hoac khong phai int (CTS tra thu la, adapter doi
        #     hinh dang): KHONG doan mo. Day la WRITE API tao phieu THAT nen
        #     "khong xac dinh duoc" phai xu ly nhu "dung ngay".
        #   - 2xx thanh cong: khong co gi de thu lai.
        return False

    async def _goi_gateway_co_retry(
        self, payload: dict, cr_session_id: int, cell_name: str
    ) -> tuple[dict | None, int, SaveCellClmApiError | None]:
        """Goi SaveCellClm, thu lai toi XUAT_PHIEU_MAX_RETRY lan neu loi TAM THOI.

        Tra ve (response, so_lan_da_thu, loi_mang):
          - (dict, n, None) - DA nhan duoc response HTTP tu CTS. Co the la
            4xx/5xx/isError; caller tu doc de quyet SUCCESS/FAILED.
          - (None, n, exc)  - het luot ma van KHONG toi duoc CTS lan nao.

        KHONG cho (sleep) giua cac lan thu (yeu cau truc tiep user): 1 lan POST
        chi mat 1-2 giay, them do tre khong lam CTS bot qua tai ma chi keo dai
        luot chay cua job."""
        loi_mang: SaveCellClmApiError | None = None
        response_cuoi: dict | None = None

        for lan_thu in range(1, XUAT_PHIEU_MAX_RETRY + 1):
            try:
                response = await self._save_cell_clm_gateway.save_cell_clm(payload)
            except SaveCellClmApiError as exc:
                # Loi MANG/timeout - adapter gop httpx.TimeoutException va
                # httpx.TransportError vao dung 1 exception nay (xem
                # adapters/http/save_cell_clm_adapter.py). Dung loai TAM THOI.
                #
                # RUI RO DA BIET, DA CAN NHAC: POST co the DA toi CTS thanh cong
                # roi moi mat response tren duong ve -> thu lai se tao PHIEU
                # TRUNG. Truoc V3 chon KHONG retry chinh vi ly do nay, nhung doi
                # lai cell mat luon co hoi xuat: theo PA A (V1) moi session chi
                # duoc quet DUNG 1 ngay, truot la het. Chon phieu trung (nguoi
                # van hanh nhin thay va xoa duoc tren TTS) thay vi phieu KHONG
                # BAO GIO ra (khong ai biet ma lam).
                loi_mang, response_cuoi = exc, None
                logger.warning(
                    "SaveCellClm loi mang/timeout - se thu lai",
                    extra={
                        "cr_session_id": cr_session_id,
                        "cell_name": cell_name,
                        "lan_thu": lan_thu,
                        "max_retry": XUAT_PHIEU_MAX_RETRY,
                        "loi": str(exc),
                    },
                )
                continue

            loi_mang, response_cuoi = None, response
            if not self._nen_thu_lai(response):
                return response, lan_thu, None

            logger.warning(
                "SaveCellClm CTS tra 5xx - se thu lai",
                extra={
                    "cr_session_id": cr_session_id,
                    "cell_name": cell_name,
                    "lan_thu": lan_thu,
                    "max_retry": XUAT_PHIEU_MAX_RETRY,
                    "status_code": response.get("status_code"),
                },
            )

        # Het luot thu. Lan CUOI CUNG roi vao 1 trong 2 tinh huong:
        #   - co response (5xx) -> tra ve de caller ghi FAILED kem noi dung loi
        #     that cua CTS, KHONG nem exception (van la "CTS co tra loi").
        #   - khong co response -> loi_mang khac None, caller ghi FAILED roi nem.
        return response_cuoi, XUAT_PHIEU_MAX_RETRY, loi_mang

    async def _ghi_ket_qua_phieu(
        self,
        cr_phieu_id: int,
        trang_thai: str,
        response_body: dict | None,
        phieu_id: str | None,
        error_message: str | None,
        request_payload: dict,
        so_lan_thu_them: int,
    ) -> str | None:
        """Ghi ket qua vao cr_phieu, NUOT loi DB (tra ve canh bao dang chuoi).

        Tach ra o V3 vi gio co HAI duong ghi ket qua (co response tu CTS / het
        luot thu vi loi mang) va CA HAI deu phai giu nguyen tac cu: loi ghi DB
        sau khi DA POST xong KHONG duoc lam mat ket qua POST (dac biet phieu_id
        that neu SUCCESS - xem su co PHIEU MO COI trong
        adapters/http/save_cell_clm_adapter.py)."""
        try:
            await self._cr_phieu_repo.update_result(
                cr_phieu_id,
                trang_thai=trang_thai,
                response_body=response_body,
                phieu_id=phieu_id,
                error_message=error_message,
                # BUG THAT (11/08): khi TAI DUNG dong cu (xuat lai cho cell da
                # co dong PENDING/FAILED/KHONG_XUAT_*) thi nhanh insert() KHONG
                # chay -> cot request_payload van la payload cua lan xuat DAU
                # TIEN, khong khop thu VUA GUI. Luon ghi lai payload lan nay de
                # cot audit noi DUNG su that.
                request_payload=request_payload,
                so_lan_thu_them=so_lan_thu_them,
            )
        except Exception as db_exc:  # noqa: BLE001 - CO Y bat rong: bat ky loi DB nao (ket noi/timeout/
            # constraint) sau khi DA POST xong deu KHONG duoc che phieu_id that - log day du de debug,
            # KHONG raise lai (raise se lam FE/router mat phieu_id that su da tao tren TTS).
            logger.error(
                "Ghi cr_phieu THAT BAI sau khi goi SaveCellClm (KHONG mat phieu_id, chi mat audit DB)",
                extra={
                    "cr_phieu_id": cr_phieu_id,
                    "trang_thai": trang_thai,
                    "phieu_id": phieu_id,
                    "loi": str(db_exc),
                },
            )
            return f"Da goi SaveCellClm xong (trang_thai={trang_thai}) nhung LUU DB THAT BAI: {db_exc}"
        return None

    async def execute(
        self,
        cr_session_id: int,
        cell_name: str,
        nguon: str | None = None,
        qoe=None,
        # A5 - ai kich hoat lan POST nay, de ghi vao cr_phieu_lan_thu.
        # Mac dinh MANUAL: execute() duoc goi truc tiep tu router (nguoi bam
        # tay); job tu dong truyen JOB_AUTO tuong minh. Mac dinh nga ve MANUAL
        # chu khong phai JOB_AUTO vi doan nham "may lam" cho viec NGUOI lam la
        # kieu sai kho phat hien hon khi truy nguyen.
        nguoi_thuc_hien: str = "MANUAL",
    ) -> XuatPhieuResult:
        # nguon/qoe (17082026): job da danh gia QoE cho CA session trong 1 lan
        # nen truyen SAN xuong day, KHONG goi CEM lai cho tung cell (se thanh
        # 238 request/session).
        #
        # CA HAI mac dinh None cho duong ROUTER (nguoi bam nut [Xuat] cho 1
        # cell): duong do khong co san ket qua QoE tu truoc.
        #
        # SUA 04/10/2026 (lo phat hien: nhom/"Qoe" payload bo sot QoE tren
        # duong nay) - KHAC voi mo ta CU o day ("Qoe='0', KHONG goi CEM o
        # duong router"): gio TU danh gia QoE cho duong nay (xem khoi code
        # ngay truoc khi tinh PhuongAnXuLyDuKien, sau qos_min) khi nguon is
        # None - tai dung _lay_qoe_theo_cell() (uu tien doc snapshot, CHI goi
        # CEM khi that su thieu) nen chi phat sinh THEM request trong truong
        # hop chua co du lieu san, khong phai "luon luon 15 request/lan bam".
        # BUOC 1 - check trung: CHI "SUCCESS" moi bo qua xuat lai (dung nguyen
        # dac ta). Neu co dong PENDING/FAILED/KHONG_XUAT_* cu (lan xuat truoc bi
        # loi, hoac job da danh dau khong xuat - V4) thi KHONG return som: se
        # thu lai ben duoi, TAI SU DUNG id
        # dong nay (KHONG insert() moi, se vi pham UNIQUE(cr_session_id,
        # cell_name) tu KHOI 2/5).
        existing = await self._cr_phieu_repo.get_by_session_cell(cr_session_id, cell_name)
        # XOA MEM (THEM 04/10/2026, quyet dinh 04/10/2026, yeu cau truc tiep
        # user) - dong cu van CON trong bang (chi danh dau deleted_at, xem
        # CrPhieuRepo.xoa()) nen get_by_session_cell() VAN THAY no. Chan NGAY
        # tai day, TRUOC ca nhanh SUCCESS ben duoi: "phieu da xoa KHONG BAO
        # GIO duoc tao lai" la quyet dinh TUYET DOI, ap dung ke ca khi dong cu
        # (truoc khi bi xoa) chua tung SUCCESS.
        if existing is not None and existing.get("deleted_at") is not None:
            raise PhieuDaXoaError(
                "Phieu cua cell nay da bi xoa, khong xuat lai",
                cr_session_id=cr_session_id,
                cell_name=cell_name,
                cr_phieu_id=existing["id"],
            )
        if existing is not None and existing["trang_thai"] == "SUCCESS":
            return XuatPhieuResult(
                cr_phieu_id=existing["id"],
                trang_thai=existing["trang_thai"],
                phieu_id=existing["phieu_id"],
                already_exists=True,
            )

        # BUOC 2 - lay session, tinh Nam/Thang tu executed_at GMT+7.
        session = await self._cr_session_repo.get_by_id(cr_session_id)
        if session is None:
            raise CrSessionNotFoundError(
                f"cr_session id={cr_session_id} khong ton tai", session_id=cr_session_id
            )
        if session.executed_at is None:
            # Chua chay CR that - khong co moc thoi gian de tinh Nam/Thang hay
            # cua so "7 ngay truoc/sau CR". Cung pattern ValueError da dung
            # trong EvaluateCrUseCase cho tinh huong "loi goi sai cua caller".
            raise ValueError(f"cr_session id={cr_session_id} chua co executed_at, chua the xuat phieu")

        executed_at_vn = _to_gmt7(session.executed_at)

        # BUOC 2b (B9, 02092026) - CHONG TRUNG THEO CELL + THANG, truoc khi POST.
        # CTS chong trung theo CELL + THANG chu khong theo session: cung 1 cell
        # nam trong cr_affected_cells cua 2 session khac nhau thi session thu hai
        # van POST va bi CTS tu choi "Bad Cell ... dang xu ly cua thang 202608".
        # Da xay ra that voi 4 cell: HDG116M13, HDG138M42, HDG138M52, TTI087M11.
        # Kiem O DAY (sau khi da co Nam/Thang tu executed_at, truoc moi buoc danh
        # gia/dung payload): khong ton mot lan goi CTS vo ich, va cung khong ton
        # cong danh gia QoS cho mot cell chac chan khong xuat duoc.
        da_co = await self._da_co_phieu_cung_thang(cell_name, executed_at_vn)
        if da_co is not None:
            # Ghi nhan bang mot trang_thai RIENG chu khong phai FAILED: day KHONG
            # phai loi - phieu cho cell nay trong thang nay DA TON TAI va dang
            # duoc xu ly, dung y muon nghiep vu. Ghi FAILED se lam bang lich su
            # va so lieu job hong het y nghia.
            ly_do = (
                f"Cell da co phieu SUCCESS trong thang {executed_at_vn.month}/{executed_at_vn.year} "
                f"(phieu {da_co['phieu_id']}, session {da_co['cr_session_id']}) - khong POST lai"
            )
            # do te = 0.0: ham dung chung nhan list[(cell, do_te)], o nhanh nay ta
            # CHUA danh gia QoS (co y bo qua de khoi ton cong) nen khong co do te
            # that de dien - 0.0 la cho trong, khong phai ket qua do
            await self._ghi_cell_khong_xuat(
                cr_session_id, [(cell_name, 0.0)], "KHONG_XUAT_DA_CO_PHIEU_THANG", ly_do
            )
            return XuatPhieuResult(
                cr_phieu_id=None,
                trang_thai="KHONG_XUAT_DA_CO_PHIEU_THANG",
                # phieu_id cua phieu DA CO san (khong phai cua lan goi nay) - dung
                # y nghia already_exists=True da dung o nhanh chong trung theo session
                phieu_id=da_co["phieu_id"],
                already_exists=True,
            )

        # BUOC 3 - lay tram tu cell_name. Nguon: cr_affected_cells (Nhanh A, 47
        # cell "bi anh huong", da luu san tram_id/LNBTS tren tung dong tu luc
        # trigger CR - Phuong an B 22072026) - KHONG dung cell_params (Nhanh B,
        # 12 cell "chay CR"): NoiDung mac dinh "Cell CLK do gan tram di doi" mo
        # ta dung PHAM VI anh huong RF (Nhanh A), khong phai tap cell duoc dieu
        # chinh tham so (Nhanh B).
        # TU GIA DINH - CAN XAC NHAN: neu nghiep vu can xuat phieu ca cho cell
        # Nhanh B, phai doi/mo rong nguon nay.
        affected_cells = await self._cr_affected_cells_repo.get_by_cr_session_id(cr_session_id)
        affected = next((c for c in affected_cells if c["cell_name"] == cell_name), None)
        if affected is None or affected.get("tram_id") is None:
            raise TramNotFoundError(
                f"Khong xac dinh duoc tram cho cell_name={cell_name} trong cr_session {cr_session_id}",
                cr_session_id=cr_session_id,
                cell_name=cell_name,
            )
        tram_id = affected["tram_id"]

        # tram co the None hoan toan (~0.4% MRBTS chua sync RIMS, da gap truoc o
        # PreviewCrResponse.tram_lan_can) - KHONG chan xuat phieu, dien "" cho
        # cac field lien quan, GIONG cach PreviewCrResponse xu ly tram thieu.
        tram = await self._enodeb_repo.get_by_tram_id(tram_id) or {}

        # BUOC 4 - danh gia QoS truoc/sau CR. Tach ra _danh_gia_qos_cell() (JOB
        # TU DONG buoc 2/4) de execute_all_pending() XEP HANG cell theo do te
        # truoc khi chon 10 cell - hanh vi cua execute() KHONG DOI (van cung
        # cong thuc, cung tham so, cung thu tu goi).
        danh_gia = await self._danh_gia_qos_cell(cell_name, executed_at_vn)
        qos_eval, after_points = danh_gia.qos_eval, danh_gia.after_points

        if qos_eval.result == "INSUFFICIENT_DATA":
            # DE XUAT xu ly "chua du data" (dac ta yeu cau tu chon cach + comment,
            # giu nguyen quyet dinh tu Khoi 3a): KHONG xuat phieu voi Qos gia/
            # thieu can cu - day la WRITE API tao phieu THAT tren TTS. Tai su
            # dung QoeDataInsufficientError (domain/errors.py, error_code
            # QOE_INSUFFICIENT_DATA - API_CONTRACTS.md SS7 dinh nghia ro "khong
            # phai loi that su"). Caller (KHOI 4, router) tu quyet dinh map ve
            # HTTP nhu QOE_INSUFFICIENT_DATA cu.
            # NGOAI LE (17082026): neu caller DA ket luan cell nay khong dat
            # (nguon != None, tuc job da danh gia CA 2 chi so) thi KHONG chan o
            # day - QoS thieu du lieu nhung QoE ket luan duoc la truong hop hop
            # le, da xu ly o tang job. Chan o day se lam cell chi hong QoE
            # khong bao gio xuat duoc.
            if nguon is None:
                raise QoeDataInsufficientError(
                    f"Chua du du lieu QoS 7 ngay truoc/sau CR cho cell_name={cell_name} "
                    f"(before={danh_gia.so_ngay_before} ngay, after={danh_gia.so_ngay_after} ngay) "
                    f"- CHUA xuat phieu",
                    cr_session_id=cr_session_id,
                    cell_name=cell_name,
                )

        # SUA 1 LO (04/10/2026): duong XUAT TAY (router POST /phieu) goi
        # execute() KHONG truyen qoe/nguon (ca 2 deu None, xem api/routers/
        # phieu.py:139) - truoc sua nay, danh gia QoE (nhom LAN truong "Qoe"
        # trong payload ben duoi) deu coi nhu KHONG co, chi tinh/dien tu QoS.
        # Cell CHI kem QoE (QoS van binh thuong) bi bo sot hoan toan tren
        # duong nay - CA o nhom (ra "1" sai, dung le phai "2") LAN o cong
        # "QoS DAT -> khong xuat" ngay duoi day (bao DAT_KHONG_XUAT sai, trong
        # khi QoE dang FAIL va dung ra PHAI xuat phieu).
        #
        # nguon is None CHINH LA tin hieu "chua ai danh gia QoE cho cell nay"
        # (duong JOB LUON truyen nguon khac None - xem _nguon_khong_dat() va
        # noi goi self.execute() o execute_all_pending()) - CHI tu danh gia
        # trong truong hop nay, tranh goi CEM THEM 1 lan vo ich cho duong JOB
        # (duong do da tu _danh_gia_va_xep_hang() danh gia QoE cho CA session
        # 1 lan roi, qoe=None o do nghia la cell nay THAT SU thieu du lieu,
        # khong phai chua duoc xet).
        #
        # self._qoe_cells_use_case DA duoc wire san cho CA router (xem
        # infrastructure/dependencies.py::get_xuat_phieu_use_case() - comment
        # "wire san de scheduler tai dung", nhung factory nay CHINH LA factory
        # Depends() cua router) - _lay_qoe_theo_cell() (da co, dung chung voi
        # duong job) tu uu tien doc snapshot qua GetQoeCellsUseCase truoc khi
        # goi CEM (_doc_snapshot_qoe_neu_du()), nen KHONG tinh la "goi CEM them
        # lan nua" neu du lieu da san tu truoc (vd job da chay cho session nay).
        if qoe is None and nguon is None:
            qoe_theo_cell = await self._lay_qoe_theo_cell(cr_session_id)
            qoe = qoe_theo_cell.get(cell_name)
        qoe_eval = qoe.qoe_eval if qoe is not None else None

        # Cong "QoS DAT -> khong xuat" CHI ap cho duong ROUTER (nguon None).
        # Duong JOB da danh gia CA 2 chi so va ket luan cell KHONG DAT truoc khi
        # goi vao day - cell dat QoS nhung hong QoE van PHAI duoc xuat, day
        # chinh la y nghia "QoE ngang hang QoS".
        #
        # SUA 04/10/2026: PHAI xet CA qoe_eval (vua danh gia o tren) o day -
        # truoc sua, cong nay CHI nhin QoS nen QoS PASS + QoE FAIL se bao NHAM
        # "DAT_KHONG_XUAT" (dung nguyen tac "QoE ngang hang QoS" nhu duong
        # JOB dang ap dung, GIO ap dung CA duong ROUTER vi gio no CUNG co du
        # lieu QoE de xet). qoe_eval None/INSUFFICIENT_DATA -> GIU hanh vi CU
        # (chi xet QoS) - QoE la chi so THEM VAO, KHONG duoc lam hong ket luan
        # QoS khi chinh no khong ket luan duoc (xem docstring _lay_qoe_theo_cell()).
        qoe_that_su_fail = qoe_eval is not None and qoe_eval.result == "FAIL"
        if nguon is None and qos_eval.result == "PASS" and not qoe_that_su_fail:
            # DAT tieu chi QoS moi (chenh lech TB truoc-sau <= 0.2) - BUOC 3:
            # "cell duoc xuat phieu = cell KHONG DAT" -> cell nay KHONG duoc
            # xuat phieu. KHONG goi gateway, KHONG tao dong cr_phieu nao (khac
            # nhanh loi ben tren - day la KET QUA HOP LE, khong phai loi).
            return XuatPhieuResult(
                cr_phieu_id=None,
                trang_thai="DAT_KHONG_XUAT",
                phieu_id=None,
                already_exists=False,
                ly_do_dat=_cau_ly_do_dat(qos_eval),
            )

        # qos_eval.result == "FAIL" HOAC qoe_that_su_fail -> KHONG DAT, tiep
        # tuc xuat phieu ben duoi.

        # Qos (diem trong payload, KHAC voi tieu chi dat/khong dat o tren) - GIU
        # NGUYEN la MIN 7 ngay SAU CR theo dung yeu cau ("khong doi"). Tai su
        # dung LAI after_points da fetch o tren (KHONG goi CTS lan nua).
        qos_min = min(p["qos"] for p in after_points)

        # PhuongAnXuLyDuKien - SUA 04/10/2026 (quyet dinh user, THAY THE hang so
        # cung "2" cu): gia tri gio PHU THUOC muc do te cua cell, KHONG CON LA
        # 1 con so co dinh cho moi phieu.
        #   "2" - QoS HOAC QoE co diem TB sau < 3.0 (duoi san), KE CA khi dong
        #         thoi tut > 0.5 - duoi san la dieu kien NANG hon nen uu tien
        #         xet truoc.
        #   "1" - ca 2 chi so (hoac chi so DUY NHAT con lai, neu 1 ben thieu
        #         du lieu) deu >= 3.0 nhung chenh lech (truoc - sau) > 0.5.
        # Day CHINH LA dinh nghia "nhom" cua khoa_uu_tien_xuat_phieu() (nhom 0
        # = duoi san, nhom 1 = con lai) - TAI SU DUNG ham domain DA CO thay vi
        # viet lai cong thuc so sanh 3.0/0.5 lan thu 2 o day (se lech nhau neu
        # 1 noi sua nguong ma noi kia quen). qos_eval LUON san (vua danh gia o
        # tren); qoe_eval (tinh o tren, TRUOC ca cong QoS-DAT) co the None (that
        # su thieu du lieu, hoac _qoe_cells_use_case chua wire o mot so
        # test/caller cu) - khoa_uu_tien_xuat_phieu() tu bo qua chi so None,
        # dung chi so con lai (yeu cau 4: ca 2 thieu thi KHONG toi duoc day, da
        # bi chan o cac nhanh insufficient-data ben tren).
        #
        # Dung CHUNG qoe_eval (tu bien qoe o tren, co the la gia tri VUA fetch)
        # cho CA nhom o day LAN qoe_min ben duoi (truong "Qoe" payload), dam
        # bao nhom va "Qoe" LUON dong bo (yeu cau: "nhom phai dung CUNG danh
        # gia QoE ma payload dang dung cho truong Qoe").
        nhom_uu_tien, _, _ = khoa_uu_tien_xuat_phieu(qos_eval, qoe_eval)
        phuong_an_xu_ly_du_kien = "2" if nhom_uu_tien == 0 else "1"

        # BUOC 5 - ghep 28 field theo mapping da CHOT voi user (dac ta KHOI 3a/5).
        vendor = tram.get("ten_thiet_bi") or _DEFAULT_VENDOR

        # === QoE NGANG HANG QoS (17082026) ===
        # nguon mac dinh QOS: duong router goc khong truyen nguon (xem execute()).
        nguon_ghi = nguon or NGUON_QOS

        # Qoe = min 7 ngay SAU CR - GIONG HET cach Qos dang lam. 2 chi so ngang
        # hang thi cach dien vao phieu phai nhu nhau, khong the 1 ben la so do
        # that con 1 ben la "0" cung.
        # Giu "0" khi khong co du lieu QoE (SUA 04/10/2026: ca duong router GIO
        # CUNG da tu danh gia QoE truoc do trong execute(), nen day CHI CON
        # nghia la that su khong co so lieu - CEM khong tra ve cell nay, hoac
        # _qoe_cells_use_case chua duoc wire - khong con rieng cho "duong
        # router" nhu truoc).
        #
        # int() BAT BUOC (sua 01092026 - su co 39 phieu FAILED): CTS khai
        # Qoe la System.Nullable`1[System.Int32]. after_points la list[float]
        # (qua _daily_averages() -> phep chia luon ra float) nen str(min(...))
        # cho "4.0" - .NET KHONG convert duoc chuoi co dau cham thap phan sang
        # Int32 va tra 400:
        #   "$.Qoe": ["The JSON value could not be converted to
        #             System.Nullable`1[System.Int32]"]
        # Keo theo "request": ["The request field is required."] vi body khong
        # parse duoc thi CTS coi nhu thieu toan bo.
        # Truoc 8f54b09 field nay hardcode "0" - chuoi so NGUYEN nen parse
        # duoc, do la ly do loi chi lo ra sau khi doi sang so do that.
        #
        # int() = CAT phan thap phan (4.9 -> 4), KHONG lam tron. Chon cat de
        # khong bao cao chat luong TOT HON thuc te: Qoe la diem THAP NHAT 7
        # ngay sau CR, lam tron len se lam nhe di muc do te.
        qoe_min = "0"
        if qoe is not None and qoe.after_points:
            qoe_min = str(int(min(qoe.after_points)))

        # SoChiTieuVP - DEM so chi tieu KHONG DAT. Truoc 17/08 luon "1" vi chi
        # co QoS; gio co the "2" khi cell khong dat CA HAI.
        # KIEU str (KHONG phai int): CTS tu choi 400 neu gui Number - do THAT
        # bang POST that 11/08, xem adapters/http/save_cell_clm_payload.py.
        so_chi_tieu_vp = "2" if nguon_ghi == NGUON_CA_HAI else "1"

        # NoiDung - ghep DONG theo chi so vi pham. GIU nguyen phan dau cau
        # (doi chieu phieu that 19207 da tao thanh cong), chi thay phan noi ve
        # chi tieu - khong doi cau truc cau.
        noi_dung = f"{_NOI_DUNG_GOC} - {_NOI_DUNG_THEO_NGUON[nguon_ghi]}"

        # dict thuan (KHONG phai SaveCellClmPayload) - application/ KHONG duoc
        # import adapters/ truc tiep (ARCHITECTURE.md SS9). SaveCellClmAdapter
        # (KHOI 1/5, da sua) tu validate/ep kieu qua SaveCellClmPayload noi bo.
        payload = {
            "Nam": executed_at_vn.year,
            "Thang": executed_at_vn.month,
            "TrangThai": 1,
            "TenCell": cell_name,
            "SiteName": tram.get("tram_name") or "",
            # CA HAI deu la CHUOI CHUA SO NGUYEN - CTS khai ca 2 la Int32
            # nullable, chuoi co dau cham thap phan bi tu choi 400 (xem
            # qoe_min o tren).
            #
            # str(int(...)) cho Qos la PHONG XA (01092026), khong sua loi dang
            # co: qos_min lay tu diem THO cua CTS nen tu truoc den nay luon la
            # int (da kiem 56 dong cr_phieu: Qos deu la '1'/'2'/'3', khong dong
            # nao co dau cham). Neu mai CTS doi sang tra so thuc thi field nay
            # se dinh DUNG loi ma Qoe vua gap - int() chan truoc, va voi du
            # lieu hien tai no la phep dong nhat.
            "Qos": str(int(qos_min)),
            "Qoe": qoe_min,  # min 7 ngay sau CR - giong Qos (17082026)
            "Tsd": "0",
            "Voice": 0,
            "Ceitsd": "0",  # noi SOC o KHOI 3b, chua lam
            "SoChiTieuVP": so_chi_tieu_vp,
            "NguyenNhan": "NN15",
            # SUA 04/10/2026 - xem comment day du o cho tinh phuong_an_xu_ly_du_kien
            # phia tren (truoc qos_min). KIEU str giong moi field "so" khac trong
            # payload nay (CTS tu choi Number, xem SoChiTieuVP/Qos/Qoe o tren).
            "PhuongAnXuLyDuKien": phuong_an_xu_ly_du_kien,
            "MaPhuongAn": "PA01",
            "NoiDung": noi_dung,
            "Vendor": vendor,
            "UserUpdatePa": "khainv",
            "LoaiCongNghe": "4G",
            "ProvinceCode": tram.get("ma_tinh") or "",
            "WardCode": "",
            "BuildingCode": tram.get("ma_csht") or "",
            "BuildingName": tram.get("ten_quan_ly") or "",
            "TtvtId": "",
            "TtvtName": "Phong Ha tang",
            "LoaiTram": "Macro",
            "BuildingTypeName": "Tram vien thong loai 2",
            "Address": "",
            "NguonSoLieu": "TATHUYTRAM",
        }

        # BUOC 7 (phan dau) - insert PENDING TRUOC khi goi gateway (audit: biet
        # DA THU xuat ke ca crash giua chung). Neu da co dong cu (PENDING/FAILED/
        # KHONG_XUAT_* tu truoc, BUOC 1) thi DUNG LAI id do thay vi insert
        # moi (se vi pham UNIQUE).
        if existing is not None:
            cr_phieu_id = existing["id"]
        else:
            inserted = await self._cr_phieu_repo.insert(
                {
                    "cr_session_id": cr_session_id,
                    "cell_name": cell_name,
                    "trang_thai": "PENDING",
                    "request_payload": payload,
                    # Ghi NGAY tu luc PENDING (khong doi den khi SUCCESS): day
                    # la KET LUAN DANH GIA, da biet chac truoc khi goi CTS.
                    # Dong FAILED cung can biet "dinh xuat vi chi so nao".
                    "nguon_khong_dat": nguon_ghi,
                }
            )
            cr_phieu_id = inserted["id"]

        # BUOC 6 - goi gateway (LUON POST THAT tu V2). V3: thu lai ngay trong
        # luot nay neu loi TAM THOI (mang/timeout/5xx), dung ngay neu loi do noi
        # dung (4xx / 200+isError) - xem _goi_gateway_co_retry().
        response, so_lan_da_thu, loi_mang = await self._goi_gateway_co_retry(
            payload, cr_session_id, cell_name
        )

        if loi_mang is not None:
            # V3d - het luot thu ma KHONG lan nao toi duoc CTS.
            #
            # PHAI ghi cr_phieu FAILED TRUOC KHI nem loi. Ban cu de exception
            # bay thang khoi execute() nen update_result() khong bao gio chay:
            # dong cr_phieu ket VINH VIEN o PENDING (mo coi, khong ai biet vi
            # sao) va so_lan_thu khong tang -> guard XUAT_PHIEU_MAX_RETRY khong
            # bao gio chan duoc cell loi mang, trong khi loi 400 (thu lai vo
            # ich) thi lai bi chan. Chan NGUOC han y dinh.
            error_message = (
                f"Khong goi duoc SaveCellClm sau {so_lan_da_thu} lan thu: {loi_mang.message}"
            )
            logger.error(
                "SaveCellClm het luot thu - KHONG toi duoc CTS",
                extra={
                    "cr_session_id": cr_session_id,
                    "cell_name": cell_name,
                    "cr_phieu_id": cr_phieu_id,
                    "so_lan_da_thu": so_lan_da_thu,
                },
            )
            await self._ghi_ket_qua_phieu(
                cr_phieu_id,
                trang_thai="FAILED",
                response_body=None,
                phieu_id=None,
                error_message=error_message,
                request_payload=payload,
                so_lan_thu_them=so_lan_da_thu,
            )
            # NEM LAI (V3b) - giu nguyen hop dong hien tai: router POST /phieu
            # tra 503 cho loi HA TANG, khac han "CTS tu choi" (200 kem FAILED).
            raise loi_mang

        # TU GIA DINH - CAN XAC NHAN THAT VOI 1 LAN POST THAT CTS TRA VE THANH
        # CONG (chua tung co mau response thanh cong that, chi co mau curl loi
        # tu khong-CTS - xem Script/test_api_hn/test_savecellclm.py): coi la
        # THANH CONG khi isError KHONG True VA status_code HTTP < 400 - CA HAI
        # dieu kien, phong truong hop 1 trong 2 sai ma cai kia khong bao. "loi
        # CTS" (isError true HOAC status>=400) van la response HOP LE nhan duoc
        # tu CTS (KHAC loi mang o tren) - KHONG raise, tra ve nguyen trang de
        # router tra FE "khong nuot loi" (BUOC 1 dac ta).
        is_cts_success = not response.get("isError") and response.get("status_code", 200) < 400
        cts_response = {
            "isError": response.get("isError"),
            "code": response.get("code"),
            "message": response.get("message"),
            "data": response.get("data"),
            # V3a - GIU LAI status_code (truoc day bi vut o dung cho nay). Khong
            # co no thi doc lai cr_phieu.response_body KHONG bao gio phan biet
            # duoc "CTS tra 400" voi "CTS tra 200 kem isError" - 2 nguyen nhan
            # khac han nhau ma cung hien ra 1 dong FAILED (bang chung: dong
            # id=82 that trong DB, khong ai biet no la 400 hay 200).
            "status_code": response.get("status_code"),
        }
        # raw_body CHI co khi CTS tu choi (adapter tu them, xem
        # save_cell_clm_adapter.py) - day la NOI DUNG LOI THAT dang .NET
        # problem+json (key errors/title) ma 4 key chuan o tren khong bat
        # duoc. Nhet vao cts_response de: (1) persist xuong
        # cr_phieu.response_body (cot JSONB, KHONG can them cot moi),
        # (2) router tra thang ve FE (khong nuot loi).
        raw_body = response.get("raw_body")
        if raw_body is not None:
            cts_response["raw_body"] = raw_body

        if is_cts_success:
            result_trang_thai = "SUCCESS"
            result_phieu_id = _extract_phieu_id(response.get("data"))
            error_message = None
            # LOG NGAY phieu_id, TRUOC moi buoc tiep theo (ghi DB, tra
            # response...) - bai hoc tu su co PHIEU MO COI: phieu DA TON TAI
            # THAT tren TTS ke tu giay phut nay, neu buoc sau chet (DB loi,
            # crash, mat ket noi) ma chua kip log thi KHONG CACH NAO truy lai
            # ID (SaveCellClm khong co API GET). Logger da ghi ra file
            # (infrastructure/logger.py) nen dong nay song sot ca khi console chet.
            logger.info(
                "SaveCellClm TAO PHIEU THANH CONG tren TTS",
                extra={
                    "phieu_id": result_phieu_id,
                    "cr_session_id": cr_session_id,
                    "cell_name": cell_name,
                    "cr_phieu_id": cr_phieu_id,
                },
            )
        else:
            result_trang_thai = "FAILED"
            result_phieu_id = None
            # Uu tien message chuan cua CTS; neu KHONG co (dung truong hop
            # .NET problem+json) thi dung raw_body - de cot error_message
            # doc phat ra ngay ly do, khong phai mo cot JSONB ra doi chieu.
            error_message = (
                response.get("message")
                or raw_body
                or f"CTS tra ve status_code={response.get('status_code')}"
            )
            # Log ca truong hop that bai kem raw_body - de debug duoc ngay
            # tu file log, khong phai vao DB doc cot JSONB.
            logger.warning(
                "SaveCellClm CTS TU CHOI - khong tao duoc phieu",
                extra={
                    "cr_session_id": cr_session_id,
                    "cell_name": cell_name,
                    "status_code": response.get("status_code"),
                    "so_lan_da_thu": so_lan_da_thu,
                    "ly_do": error_message,
                },
            )

        # BUOC 2 (dac ta KHOI 4a/5) - loi ghi cr_phieu SAU KHI da POST xong (du
        # thanh cong hay CTS bao loi) KHONG duoc lam MAT ket qua da co (dac
        # biet phieu_id that neu SUCCESS) - xem _ghi_ket_qua_phieu().
        db_save_warning = await self._ghi_ket_qua_phieu(
            cr_phieu_id,
            trang_thai=result_trang_thai,
            response_body=cts_response,
            phieu_id=result_phieu_id,
            error_message=error_message,
            request_payload=payload,
            # so_lan_thu = "so lan DA LAM PHIEN CTS". V3: 1 lan goi execute() co
            # the POST toi 3 lan (retry trong luot) nen phai cong DUNG so lan da
            # POST, khong phai +1 - neu khong, cell 5xx lien tuc se hien
            # so_lan_thu=1 du da lam phien CTS 3 lan.
            so_lan_thu_them=so_lan_da_thu,
        )

        # A5 (02092026) - ghi THEM 1 dong lich su lan POST nay. Dat SAU
        # _ghi_ket_qua_phieu va boc try rieng: day la du lieu AUDIT, hong no
        # KHONG duoc lam hong ket qua POST that su da xay ra tren CTS (bai hoc
        # PHIEU MO COI - moi buoc sau khi POST deu phai chiu duoc loi rieng le).
        try:
            await self._cr_phieu_repo.ghi_lan_thu(
                cr_phieu_id=cr_phieu_id,
                # nguoi_thuc_hien: job tu dong truyen JOB_AUTO qua execute_all_pending,
                # con lai la nguoi bam tay tren FE
                nguoi_thuc_hien=nguoi_thuc_hien,
                ket_qua=result_trang_thai,
                phieu_id=result_phieu_id,
                error_message=error_message,
                request_payload=payload,
                response_body=cts_response,
            )
        except Exception as exc:  # noqa: BLE001 - xem ly do bat rong o comment tren
            logger.error(
                "Ghi cr_phieu_lan_thu THAT BAI (chi mat lich su audit, khong mat phieu)",
                extra={"cr_phieu_id": cr_phieu_id, "loi": str(exc)},
            )

        return XuatPhieuResult(
            cr_phieu_id=cr_phieu_id,
            trang_thai=result_trang_thai,
            phieu_id=result_phieu_id,
            already_exists=False,
            cts_response=cts_response,
            db_save_warning=db_save_warning,
        )

    # === JOB TU DONG (buoc 2/4) ===
    #
    # execute_all_pending() la method CU THE, KHONG nam trong ABC
    # IXuatPhieuUseCase (chi dinh nghia execute(session_id, cell_name) cho 1
    # cell) - dung Y HET tien le EvaluateCrUseCase.execute_all_pending() (C2.2):
    # khong doi ABC da co (rui ro thap hon, khong pha hop dong cu voi router
    # POST /phieu). DI factory tra concrete class, xem infrastructure/
    # dependencies.py.
    #
    # V2 (12/08): da BO dry_run - moi luot chay deu POST THAT. Cong tac bat/tat
    # duy nhat con lai la SCHEDULER_ENABLED (infrastructure/scheduler.py): khong
    # bat lich thi ham nay khong ai goi.

    async def _lay_session_du_dieu_kien(
        self,
        bay_gio: datetime | None = None,
        tu_ngay: date | None = None,
        den_ngay: date | None = None,
    ) -> list:
        # Dieu kien 1: NGAY chay CR nam trong 1 CUA SO ket thuc tai hom_nay -
        # XUAT_PHIEU_AFTER_DAYS.
        #
        # SUA 03/10/2026 (QUET BU, yeu cau truc tiep user) - THAY THE PA A cu
        # (dung "==", chi quet DUNG 1 ngay CR/lan chay). Ca THAT lam loi PA A:
        # session 7296 (CR 15/09/2026) KHONG BAO GIO duoc job tu dong quet
        # toi, vi job khong chay dung ngay moc cua no (xem khao sat
        # 02/10/2026) - "==" khong co co che tu phuc hoi, phai cho NGUOI chay
        # tay POST /jobs/xuat-phieu-auto moi lan lo. Gio dung CUA SO
        # [ngay_moc - XUAT_PHIEU_QUET_BU_NGAY, ngay_moc] (ca 2 dau BAO GOM) -
        # job tu dong "bat" lai duoc nhung ngay da lo trong vong
        # QUET_BU_NGAY ngay gan nhat ma KHONG can con nguoi can thiep.
        #
        # VAN AN TOAN truoc rui ro "<=" cu tung lo ngai (mot session con cell
        # vuot tran 10 se bi quet lai MOI NGAY vo thoi han, ton CTS): dieu
        # kien MOI them "xuat_phieu_at IS NULL" - BAT KY session nao DA duoc
        # _xu_ly_mot_session() xu ly xong (du ket qua la DA_XUAT/KHONG_CAN_XUAT/
        # LOI) deu CO xuat_phieu_at (xem _ghi_ket_qua_xuat_phieu_session()),
        # nen KHONG BAO GIO duoc chon lai lan 2 - moi session CHI duoc xu ly
        # DUNG 1 LAN du cua so quet bu rong bao nhieu ngay. Day la DIEU KIEN
        # IDEMPOTENT THAT (truoc day dua vao "==" chi khop 1 ngay DUY NHAT
        # trong doi 1 session de tranh trung, gio PHAI kiem tuong minh vi cua
        # so quet nhieu ngay lien tiep co the khop CUNG 1 session nhieu lan).
        #
        # SO THEO NGAY LICH (GMT+7), KHONG so theo THOI DIEM (sua 12/08).
        # Ban cu dung `datetime.now(utc) - timedelta(days=N)` roi so voi
        # executed_at -> ngay xuat phieu phu thuoc GIO chay CR: CR chay 14:00
        # ngay 20, job chay 08:00 ngay 28 thi cutoff = 08:00 ngay 20 < 14:00
        # ngay 20 -> coi nhu CHUA du, truot sang ngay 29. Cung 1 ngay CR nhung
        # CR chay buoi sang thi xuat ngay 28, chay buoi chieu thi ngay 29 -
        # khong xac dinh, kho doi chieu voi quy trinh TTS. So theo ngay lich
        # thi ngay 28 luon la ngay 28.
        #
        # Quy ve GMT+7 CA HAI VE truoc khi lay .date(): executed_at luu UTC
        # (TIMESTAMPTZ, C1.4-fix10), lay .date() thang tren UTC se lech 1 ngay
        # voi CR chay trong khung UTC 17:00-23:59 - dung bug C1.4-fix8 da sua o
        # EvaluateCrUseCase. Dung _to_gmt7() co san, khong tu nghi cach moi.
        #
        # bay_gio: cho phep truyen vao de test khong phu thuoc dong ho may
        # (mac dinh None = lay gio thuc).
        #
        # tu_ngay/den_ngay (20082026) - LAT LAI quyet dinh cu ghi o day
        # ("KHONG dua len execute_all_pending() - ngoai test khong ai can doi
        # hom nay la ngay khac"). Gio da co nhu cau THAT: PA A quet DUNG 1
        # ngay, nen job lo 1 ngay la MAT VINH VIEN ngay CR do. Chay bu bang
        # tay (POST /jobs/xuat-phieu-auto) la duong cuu duy nhat ngoai xuat
        # tay tung cell.
        #
        # CA HAI None = hanh vi CU khong doi mot ly nao (PA A, dung 1 ngay).
        bay_gio = bay_gio or datetime.now(timezone.utc)
        ngay_moc = _to_gmt7(bay_gio).date() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)

        # Dieu kien 2: status nam trong WHITELIST (viec 2b, 12/08 - TRUOC day
        # chi lay DONE). Ly do doi: 8 session DONE that deu da qua
        # EVALUATION_DAYS=21 ngay, lan dau ai goi POST /jobs/evaluate-cr thi ca
        # 8 chuyen sang EVALUATED/EVAL_PENDING va job xuat phieu MAT HUT toan
        # bo. Xem chu y day du tai XUAT_PHIEU_STATUS_WHITELIST.
        #
        # Goi list() RIENG cho tung status thay vi 1 query nhieu status:
        # SessionFilter.status la 1 gia tri don (domain/ports/outbound/
        # repo_ports.py) - doi sang list se pha hop dong dang dung boi
        # GET /sessions. Dung LAI pattern EvaluateCrUseCase.execute_all_pending()
        # (goi 2 lan cho DONE + EVAL_PENDING roi cong lai).
        sessions = []
        for status in XUAT_PHIEU_STATUS_WHITELIST:
            page = await self._cr_session_repo.list(SessionFilter(status=status))
            sessions.extend(page.items)

        # Duong CHAY TAY (co tu_ngay/den_ngay) GIU NGUYEN - dung BETWEEN theo
        # khoang NGUOI DUNG tu chon, doc lap voi XUAT_PHIEU_QUET_BU_NGAY (job
        # tu dong). 2 nhanh TACH BACH: job tu dong khong truyen ngay nen luon
        # di nhanh cua so ben duoi, khong co cach nao vo tinh chuyen sang
        # nhanh nay.
        if tu_ngay is not None or den_ngay is not None:
            tu = tu_ngay or den_ngay
            den = den_ngay or tu_ngay
            return [
                s
                for s in sessions
                if s.executed_at is not None and tu <= _to_gmt7(s.executed_at).date() <= den
            ]

        # CUA SO QUET BU (03/10/2026): [ngay_moc - QUET_BU_NGAY, ngay_moc], CA
        # 2 dau bao gom - xem "SUA 03/10/2026" o tren. xuat_phieu_at IS NULL
        # la dieu kien IDEMPOTENT bat buoc (session da xu ly xong roi thi
        # KHONG duoc chon lai, du van con nam trong cua so ngay).
        cua_so_duoi = ngay_moc - timedelta(days=XUAT_PHIEU_QUET_BU_NGAY)
        return [
            s
            for s in sessions
            if s.executed_at is not None
            and s.xuat_phieu_at is None
            and cua_so_duoi <= _to_gmt7(s.executed_at).date() <= ngay_moc
        ]

    async def _ghi_ket_qua_xuat_phieu_session(self, cr_session_id: int, ket_qua: str) -> None:
        """Ghi 2 cot tien trinh vao cr_session (14/08), NUOT loi DB.

        NUOT loi CO CHU DICH: day la ghi chu cho man hinh theo doi, con phieu
        that thi DA gui len TTS roi. De loi DB o day noi len se lam ca luot quet
        session dung giua chung va cac cell con lai mat luot - danh doi sai
        huong. Log ERROR de van truy duoc."""
        try:
            await self._cr_session_repo.ghi_ket_qua_xuat_phieu(
                cr_session_id,
                xuat_phieu_at=datetime.now(timezone.utc),
                xuat_phieu_ket_qua=ket_qua,
            )
        except Exception as exc:  # noqa: BLE001 - xem ly do ngay tren
            logger.error(
                "Job xuat phieu: ghi ket qua tien trinh vao cr_session THAT BAI",
                extra={"cr_session_id": cr_session_id, "ket_qua": ket_qua, "loi": str(exc)},
            )

    async def _ghi_cell_khong_xuat(
        self,
        cr_session_id: int,
        cells: list[tuple[str, float]],
        trang_thai: str,
        ly_do: str,
    ) -> None:
        """V4 - ghi dong cr_phieu cho cell ma job CO Y KHONG xuat.

        KHONG dung update_result() cho dong da co: ham do ghi de ca
        response_body/phieu_id/error_message nen se XOA SACH noi dung loi that
        cua dong FAILED cu (cell "het luot thu" LUON da co san 1 dong FAILED
        kem ly do CTS tu choi - do chinh la thu nguoi van hanh can doc). O day
        chi doi DUY NHAT trang_thai, xem ICrPhieuRepo.danh_dau_khong_xuat()."""
        for cell_name, do_te in cells:
            try:
                existing = await self._cr_phieu_repo.get_by_session_cell(cr_session_id, cell_name)
                if existing is None:
                    await self._cr_phieu_repo.insert(
                        {
                            "cr_session_id": cr_session_id,
                            "cell_name": cell_name,
                            "trang_thai": trang_thai,
                            # request_payload la NOT NULL trong DB, nhung cell
                            # nay CHUA BAO GIO duoc ghep 28 field (bi loai truoc
                            # buoc do). Ghi marker noi ro ly do thay vi payload
                            # gia - doc cot audit se khong hieu nham thanh "da
                            # tung gui thu nay len CTS".
                            "request_payload": {
                                "_khong_xuat": trang_thai,
                                "_ly_do": ly_do,
                                "do_te": round(do_te, 3),
                            },
                            "error_message": ly_do,
                        }
                    )
                    continue

                if existing["trang_thai"] == "SUCCESS":
                    # Da co phieu THAT tren TTS (nguoi dung xuat tay truoc do) -
                    # ha xuong KHONG_XUAT_* se bao mat 1 phieu co that.
                    continue

                await self._cr_phieu_repo.danh_dau_khong_xuat(existing["id"], trang_thai)
            except Exception as exc:  # noqa: BLE001 - CO Y bat rong: day chi la ghi chu AUDIT,
                # khong duoc lam hong luot xuat phieu that (cac cell khac trong session van phai chay).
                logger.error(
                    "Job xuat phieu: ghi dong cr_phieu cho cell KHONG XUAT that bai",
                    extra={
                        "cr_session_id": cr_session_id,
                        "cell_name": cell_name,
                        "trang_thai": trang_thai,
                        "loi": str(exc),
                    },
                )

    async def xem_truoc(self, tu_ngay: date, den_ngay: date) -> dict:
        """Quet + danh gia DAY DU nhung KHONG POST, KHONG ghi DB.

        === VI SAO BAT BUOC CO BUOC NAY ===
        POST phieu la hanh dong KHONG THU HOI: phieu da len CTS thi ben nay xoa
        dong cr_phieu cung khong go duoc phieu ben do (xem XoaPhieuUseCase).
        Bam nham 1 khoang ngay rong = hang tram phieu THAT len CTS, va viec don
        dep phai lam bang tay qua team CTS. Nguoi bam PHAI biet truoc con so.

        Tra ve dung danh sach cell ma execute_all_pending() se xuat - vi CA HAI
        deu di qua _danh_gia_va_xep_hang() va cung mot phep cat top N.

        DANH DOI: van goi CTS + CEM day du (~48 request/session) nen CHAM. Do
        la ban chat cua viec danh gia - khong co cach nao biet cell nao FAIL ma
        khong hoi so lieu. Gioi han 30 ngay o tang router giu cho no huu han.
        """
        sessions = await self._lay_session_du_dieu_kien(tu_ngay=tu_ngay, den_ngay=den_ngay)

        ket_qua_sessions = []
        tong = 0
        for session in sessions:
            try:
                cells, bi_b9 = await self._xem_truoc_mot_session(session)
            except Exception as exc:  # noqa: BLE001 - 1 session loi KHONG duoc
                # giet ca luot xem truoc (dung tinh than voi execute_all_pending).
                # Ghi "loi" vao dong do de nguoi bam THAY session nay chua duoc
                # danh gia, thay vi tuong no khong co cell nao can xuat.
                logger.warning(
                    "Xem truoc: danh gia session that bai",
                    extra={"cr_session_id": session.id, "loi": str(exc)},
                )
                ket_qua_sessions.append(
                    {
                        "cr_session_id": session.id,
                        "tram_id": session.tram_id,
                        "tram_name": session.tram_name,
                        "executed_at": session.executed_at,
                        "so_cell_se_xuat": 0,
                        "cells": [],
                        "so_cell_da_co_phieu_thang": 0,
                        "cell_da_co_phieu_thang": [],
                        "loi": str(exc),
                    }
                )
                continue

            tong += len(cells)
            ket_qua_sessions.append(
                {
                    "cr_session_id": session.id,
                    "tram_id": session.tram_id,
                    "tram_name": session.tram_name,
                    "executed_at": session.executed_at,
                    "so_cell_se_xuat": len(cells),
                    "cells": cells,
                    # B9 (04092026) - de nguoi bam biet VI SAO so phieu it hon
                    # tong cell khong dat, thay vi tuong he thong dem sai.
                    "so_cell_da_co_phieu_thang": len(bi_b9),
                    "cell_da_co_phieu_thang": bi_b9,
                    "loi": None,
                }
            )

        tong_b9 = sum(s_.get("so_cell_da_co_phieu_thang", 0) for s_ in ket_qua_sessions)
        return {
            "tong_phieu_se_xuat": tong,
            "tong_cell_da_co_phieu_thang": tong_b9,
            "sessions": ket_qua_sessions,
        }

    async def _da_co_phieu_cung_thang(self, cell_name: str, executed_at_vn: datetime) -> dict | None:
        """B9 - cell da co phieu SUCCESS trong CUNG THANG (bat ke session nao)?

        Tra dong phieu da co, hoac None.

        === VI SAO TACH RA (04092026) ===
        DUONG CHAY THAT va DUONG XEM TRUOC phai ap DUNG MOT dieu kien. Truoc
        do B9 chi nam trong execute() nen xem truoc dem ca cell se bi B9 chan:
        bao 16 phieu, chay that ra 14 - va nguoi bam khong hieu 2 phieu di dau.
        Xem truoc lech voi chay that thi no thanh CAI BAY, dung loai loi da gap
        voi _danh_gia_va_xep_hang().

        CTS chong trung theo CELL + THANG (khong theo session), nen dieu kien
        nay KHONG the suy tu cr_phieu cua rieng session dang xet.
        """
        return await self._cr_phieu_repo.get_success_cung_thang(
            cell_name, executed_at_vn.year, executed_at_vn.month
        )

    async def _xem_truoc_mot_session(self, session) -> tuple[list[dict], list[str]]:
        """(cell SE duoc xuat, cell bi B9 loai) cho 1 session - KHONG ghi, KHONG POST.

        Lap lai DUNG chuoi loc cua _xu_ly_mot_session():
        xep hang -> cat top N -> loai cell da SUCCESS / het luot thu / DA CO
        PHIEU CUNG THANG (B9).
        Thu tu do la BAT BUOC (xem chu y trong _xu_ly_mot_session): cat top
        TRUOC roi moi loai, khong duoc doi cho.
        """
        # SUA 04/10/2026: _danh_gia_va_xep_hang() gio tu CAT THEO SECTOR, tra
        # san (top_duoc_phep, vuot_gioi_han, thieu_du_lieu) - khong con tu
        # slice [:XUAT_PHIEU_MAX_PER_SESSION] o day nua (hang so da bo).
        top_duoc_phep, _vuot_gioi_han, _ = await self._danh_gia_va_xep_hang(
            session, chi_xem_truoc=True
        )

        phieu_da_co = await self._cr_phieu_repo.get_by_cr_session_id(session.id)
        cell_da_xuat = {p["cell_name"] for p in phieu_da_co if p["trang_thai"] == "SUCCESS"}
        cell_het_luot_thu = {
            p["cell_name"]
            for p in phieu_da_co
            if p["trang_thai"] != "SUCCESS" and (p.get("so_lan_thu") or 0) >= XUAT_PHIEU_MAX_RETRY
        }
        # XOA MEM (THEM 04/10/2026) - get_by_cr_session_id() KHONG loc deleted_at
        # (phai THAY duoc dong da xoa de loai o day), KHAC list_phieu()/count_phieu()
        # (BAT BUOC loc, dung cho hien thi/dem). Cell co phieu da xoa PHAI loai
        # khoi ung vien xem truoc - khop HANH VI THAT cua execute() (PhieuDaXoaError,
        # 409) de xem truoc khong "hua" xuat nhung cell chay that se bi tu choi.
        cell_da_xoa = {p["cell_name"] for p in phieu_da_co if p.get("deleted_at") is not None}

        executed_at_vn = _to_gmt7(session.executed_at)

        se_xuat, bi_b9 = [], []
        for cell_name, do_te, nguon, qoe_wrapper, danh_gia, khoa, sector in top_duoc_phep:
            if cell_name in cell_da_xuat or cell_name in cell_het_luot_thu or cell_name in cell_da_xoa:
                continue
            # B9 (them 04092026) - CUNG ham voi duong chay that. Truoc do xem
            # truoc bo qua dieu kien nay nen dem THUA: bao 16, chay that ra 14.
            #
            # Goi 1 query/cell. Chap nhan: chi chay tren top 10 cell DA loc
            # (toi da 10 query/session), va xem truoc von da ton 34 request CTS
            # cho session do - them vai query DB la khong dang ke.
            if await self._da_co_phieu_cung_thang(cell_name, executed_at_vn) is not None:
                bi_b9.append(cell_name)
                continue
            se_xuat.append(_dong_xem_truoc(cell_name, do_te, nguon, qoe_wrapper, danh_gia, khoa, sector))
        return se_xuat, bi_b9

    async def _danh_gia_va_xep_hang(
        self, session, chi_xem_truoc: bool = False
    ) -> tuple[list, list, list]:
        """Danh gia TOAN BO cell cua 1 session -> (top_duoc_phep, vuot_gioi_han,
        thieu_du_lieu).

        Moi phan tu cua top_duoc_phep/vuot_gioi_han la tuple 7 phan tu:
        (cell_name, do_te, nguon, qoe_eval, qos_eval, khoa, sector) - xem cho
        append() ben duoi. top_duoc_phep da CAT THEO SECTOR (quyet dinh
        04/10/2026, XUAT_PHIEU_MAX_PER_SECTOR/sector - xem Buoc d ben duoi),
        vuot_gioi_han la phan con lai ngoai tran cua sector tuong ung.

        === VI SAO TACH RA (20082026) ===
        POST /jobs/xuat-phieu-auto/xem-truoc phai cho ra DUNG danh sach cell ma
        luot chay that se xuat. Neu xem truoc tu tinh lai theo cong thuc rieng
        thi 2 ben SE lech nhau vao mot ngay nao do (sua tieu chi 1 ben quen ben
        kia) - va luc do "xem truoc" tro thanh cai bay: nguoi bam thay 3 phieu
        roi he thong xuat 30. Dung CHUNG mot ham la cach duy nhat khong lech.

        chi_xem_truoc=True: KHONG ghi bat cu gi vao DB (khong cr_phieu, khong
        snapshot). Van GOI CTS/CEM day du - do la ban chat cua viec danh gia,
        va cung la ly do xem truoc cham.
        """
        # Lay TRONG ham nay (khong nhan tu ngoai): ca 2 caller (_xu_ly_mot_session
        # va xem_truoc) deu can dung danh sach nay, truyen tu ngoai chi tao them
        # 1 duong de 2 ben lech nhau.
        affected = await self._cr_affected_cells_repo.get_by_cr_session_id(session.id)

        # CHOT PHONG VE (03/10/2026) - loai small cell (S/P) NEU co trong
        # cr_affected_cells. Tai sao can du filter_affected() (Nhanh A,
        # domain/services/neighbor_cell_filter.py) tu 02/10/2026 da loai
        # small cell truoc khi ghi vao cr_affected_cells: kiem tra SQL that
        # (02/10/2026) xac nhan 0/464 dong hien co la small cell, nen day la
        # luoi AN TOAN cho TUONG LAI (vd 1 nguon ghi khac sau nay, hoac du
        # lieu cu truoc 02/10 cua tram khac chua tung kiem), KHONG phai sua
        # loi dang xay ra. Dat o DAY (ngay sau khi doc) de BAO VE CA 2 nhanh
        # dung "affected" phia duoi (QoS vong lap + _lay_qoe_theo_cell doc
        # rieng cung session.id nen khong qua bien nay, nhung QoS - chi tieu
        # CHINH quyet dinh xep hang - da duoc chan o day).
        affected = [c for c in affected if loai_tram_tu_ten_cell(c["cell_name"]) not in LOAI_TRAM_SMALL_CELL]

        executed_at_vn = _to_gmt7(session.executed_at)

        # Buoc a+b: danh gia TOAN BO cell bi anh huong, chi giu cell KHONG DAT
        # (FAIL).
        #
        # QUAN TRONG (sua 12/08): KHONG loai cell da co phieu SUCCESS o day nua.
        # Ban cu loai TRUOC khi xep hang -> luot sau, 10 cell da xuat bien mat
        # khoi danh sach, cell thu 11-12 tro thanh toan bo ung vien va LEO LEN
        # top 10 -> duoc xuat tu dong. Nhu vay tran 10 bien thanh "10 cell MOI
        # MOI NGAY" thay vi "10 cell / SESSION" nhu thiet ke da chot (Khoi 5:
        # "cell vuot 10 -> KHONG tao cr_phieu, de THU CONG").
        #
        # Vi vay thu tu BAT BUOC la: xep hang TOAN BO -> cat top 10 -> SAU DO
        # moi loai cell da co phieu trong top do. Cell thu 11 tro di nam ngoai
        # top VINH VIEN (do te cua chung khong doi giua cac luot vi cua so QoS
        # T+1..T+7 co dinh theo ngay CR), nen KHONG BAO GIO duoc job tu xuat.
        #
        # DANH DOI da biet: phai danh gia lai ca cell da co phieu (2 lan goi CTS/
        # cell) chi de biet do te ma xep hang. Chap nhan - do te la thu DUY NHAT
        # quyet dinh thu hang, khong luu san o dau. Xem them no ky thuat "danh
        # gia 2 lan" (DEV_LOG buoc 2/4): neu cham toi nguong phai sua thi xu ly
        # chung 1 the.
        ung_vien = []
        # Cach C - gom ten cell thieu du lieu de dua vao chi_tiet cua job_run_log
        # (nguoi van hanh doc 1 luot chay la thay ngay cell nao can xuat tay).
        thieu_du_lieu: list[str] = []

        # QoE NGANG HANG QoS (17082026) - danh gia QoE cho TOAN BO cell cua
        # session TRONG 1 LAN, TRUOC vong lap.
        #
        # !!! TUYET DOI KHONG goi QoE trong vong lap tung cell !!!
        # CEM co rang buoc 1 REQUEST = 1 NGAY nhung nhan cells[] la MANG, nen:
        #   goi 1 lan cho ca danh sach -> before(7) + after RONG(8, T..T+7 - D2) = 15 request
        #   goi rieng tung cell        -> 15 x 17 cell    = 255 request
        # CTS thi nguoc lai (1 request/cell/cua so, KHONG doi theo do rong cua
        # so = 34 request cho 17 cell) nen QoS van phai nam trong vong lap.
        # Tong ~49 request/session - gon trong cua so misfire 30 phut cua
        # scheduler.
        qoe_theo_cell = await self._lay_qoe_theo_cell(session.id, luu_snapshot=not chi_xem_truoc)

        for cell in affected:
            cell_name = cell["cell_name"]
            try:
                danh_gia = await self._danh_gia_qos_cell(
                    cell_name,
                    executed_at_vn,
                    # Xem truoc KHONG ghi gi vao DB - ke ca snapshot. Snapshot
                    # chi la cache doc, ghi cung khong sai, nhung "xem truoc
                    # khong dong vao DB" la mot loi hua de kiem chung; de ho 1
                    # duong ghi la loi hua do khong con kiem duoc bang test.
                    cr_session_id=None if chi_xem_truoc else session.id,
                )
            except Exception as exc:  # noqa: BLE001 - CO Y bat rong: 1 cell loi
                # (CTS timeout, du lieu la...) KHONG duoc giet ca luot quet.
                logger.warning(
                    "Job xuat phieu: danh gia cell that bai, BO QUA cell nay",
                    extra={"cr_session_id": session.id, "cell_name": cell_name, "loi": str(exc)},
                )
                continue

            qoe = qoe_theo_cell.get(cell_name)
            qoe_result = qoe.qoe_eval.result if qoe is not None else "INSUFFICIENT_DATA"
            qos_result = danh_gia.qos_eval.result

            # CHI khi CA HAI chi so deu khong ket luan duoc moi coi la "thieu du
            # lieu". Thieu 1 chi so ma chi so kia ket luan duoc -> VAN danh gia
            # binh thuong theo chi so co du lieu: bo qua ca session chi vi 1
            # nguon im lang la mat oan ket luan da co san.
            if qos_result == "INSUFFICIENT_DATA" and qoe_result == "INSUFFICIENT_DATA":
                # CACH C (16082026) - GHI DAU VET roi moi bo qua, KHONG con
                # `continue` tran.
                #
                # VI SAO DOI: comment cu ("lan chay sau se xet lai") DUNG voi ban
                # truoc PA A, khi dieu kien quet la "<=" nen session con trong
                # dien quet nhieu ngay. Tu 12/08 dieu kien la "==" (quet DUNG 1
                # ngay) - KHONG CO luot sau. Cell thieu du lieu bi bo qua se MAT
                # VINH VIEN, khong dong cr_phieu nao, khong ai biet ma xuat tay.
                #
                # Ghi 1 dong cr_phieu KHONG_XUAT_THIEU_DU_LIEU de cell nay noi
                # len tren UI (GET /phieu) giong 2 truong hop KHONG_XUAT_* kia.
                # Van `continue` sau khi ghi - tuyet doi KHONG xuat phieu voi Qos
                # thieu can cu.
                ly_do = (
                    f"QoS chi co {danh_gia.so_ngay_before}/7 ngay truoc, "
                    f"{danh_gia.so_ngay_after}/7 ngay sau; "
                    f"QoE chi co {qoe.so_ngay_before if qoe else 0}/7 ngay truoc, "
                    f"{qoe.so_ngay_after if qoe else 0}/7 ngay sau "
                    f"- CA HAI deu khong du de ket luan (can >= {MIN_DAYS_REQUIRED})"
                )
                logger.warning(
                    "Job xuat phieu: cell thieu du lieu CA QoS LAN QoE, danh dau de xuat tay",
                    extra={
                        "cr_session_id": session.id,
                        "cell_name": cell_name,
                        "so_ngay_before": danh_gia.so_ngay_before,
                        "so_ngay_after": danh_gia.so_ngay_after,
                    },
                )
                # Goi RIENG tung cell (list 1 phan tu) chu khong gom lo: moi cell
                # co so ngay KHAC NHAU nen ly_do khac nhau, ma _ghi_cell_khong_xuat
                # dung CHUNG 1 ly_do cho ca lo. Van tai dung ham do de huong het
                # phan an toan da co (bo qua dong SUCCESS, nuot loi ghi DB).
                # do_te = 0.0 - dung gia tri QosCellEvaluation.do_te tra ve khi
                # thieu avg, khong bia so.
                if not chi_xem_truoc:
                    await self._ghi_cell_khong_xuat(
                        session.id, [(cell_name, 0.0)], TRANG_THAI_THIEU_DU_LIEU, ly_do
                    )
                thieu_du_lieu.append(cell_name)
                continue

            # QoE NGANG HANG QoS: KHONG DAT o BAT KY chi so nao deu xuat phieu.
            if qos_result == "FAIL" or qoe_result == "FAIL":
                nguon = _nguon_khong_dat(qos_result, qoe_result)
                # do_te = MAX cua 2 do tut (khong phai trung binh, khong phai
                # tong). VI SAO: cell tut 2.0 QoE + 0.0 QoS ra trung binh 1.0,
                # NGANG voi cell tut 1.0 ca hai - trong khi 2 tinh huong khac
                # han nhau ve muc do gap. max phan anh dung "cell nao dang hong
                # nang nhat o mot chi so nao do", va do moi la thu quyet dinh
                # thu tu uu tien khi phai cat theo tran 10.
                do_te = _do_te_max(danh_gia, qoe)
                # khoa (09/2026): do_te VAN duoc tinh va bao cao (job_run_log,
                # API xem truoc, FE) nhung KHONG con quyet dinh thu tu - xem
                # domain/services/evaluation_service.py::khoa_uu_tien_xuat_phieu.
                khoa = khoa_uu_tien_xuat_phieu(
                    danh_gia.qos_eval, qoe.qoe_eval if qoe is not None else None
                )
                # 7 phan tu (them sector 04/10/2026 - LUON o CUOI cung de KHONG
                # xao tron vi tri 6 phan tu cu; them khoa 09/2026; danh_gia them
                # 20082026): duong XEM TRUOC can avg_before/avg_after de nguoi
                # bam doi chieu, ma 2 so do chi co trong danh gia QoS. CHI CO 2
                # cho unpack theo vi tri (vong lap xuat phieu + vong lap xem
                # truoc) - cac cho khac dung t[0]/t[1]/t[-1]. Da tung sot 1 cho
                # khi tuple no tu 2 len 4 (18/08), nen moi lan them phan tu phai
                # kiem CA 2 cho do.
                ung_vien.append((cell_name, do_te, nguon, qoe, danh_gia, khoa, cell.get("sector")))

        # Buoc c: sort TANG DAN theo khoa uu tien (khoa da mang sang dau am o
        # ve do_giam nen khong dung reverse=True).
        #   nhom 0 (diem TB < 3.0) di TRUOC nhom 1, roi trong moi nhom do giam
        #   lon di truoc, cuoi cung diem con lai thap di truoc.
        # SUA 09/2026: truoc day sort theo do_te giam dan - cach do lam cell
        # DUOI muc toi thieu bi cat trong khi cell chi tut nhieu lai duoc xuat
        # (ca that 4G-HKM022M43-HNI session 4884, xem khoa_uu_tien_xuat_phieu).
        ung_vien.sort(key=lambda x: x[5])

        # Buoc d: cat theo SECTOR (quyet dinh 04/10/2026, THAY THE cat phang
        # theo session) - xem chu y day du o XUAT_PHIEU_MAX_PER_SECTOR. Duyet
        # ung_vien THEO DUNG THU TU vua sort (khoa uu tien) - dem rieng cho
        # tung sector, cell thu (N+1) tro di CUA SECTOR DO moi bi day sang
        # vuot_gioi_han, KHONG phai thu (N+1) cua toan session. sector=None
        # (cell khong suy duoc huong - xem filter_affected()) gom chung thanh
        # 1 "sector" rieng, CUNG tran nhu cac sector so thuc - KHONG duoc mien
        # tran hay gop lan vao sector khac.
        #
        # CHUYEN VAO DAY (khong de 2 caller tu cat o ngoai nhu truoc) - vi ca
        # xem_truoc() LAN job that deu phai cat GIONG HET nhau (dung 1 cho
        # tranh lech, xem docstring dau ham), va logic "dem theo sector" se
        # phai lap lai y het o 2 noi neu khong gom vao day.
        dem_theo_sector: dict[int | None, int] = {}
        top_duoc_phep: list = []
        vuot_gioi_han: list = []
        for item in ung_vien:
            sector = item[-1]
            dem = dem_theo_sector.get(sector, 0)
            if dem < XUAT_PHIEU_MAX_PER_SECTOR:
                top_duoc_phep.append(item)
                dem_theo_sector[sector] = dem + 1
            else:
                vuot_gioi_han.append(item)

        return top_duoc_phep, vuot_gioi_han, thieu_du_lieu

    async def _xu_ly_mot_session(self, session) -> dict:
        """Xu ly 1 session: danh gia -> xep hang -> xuat toi da N cell.

        Tra ve dict thong ke cua RIENG session nay (caller tu cong don) - tach
        ham de vong lap ngoai chi lo bat loi + cong so, khong long 3 tang."""
        phieu_da_co = await self._cr_phieu_repo.get_by_cr_session_id(session.id)
        cell_da_xuat = {p["cell_name"] for p in phieu_da_co if p["trang_thai"] == "SUCCESS"}
        # Cell da thu POST that >= XUAT_PHIEU_MAX_RETRY lan ma van chua SUCCESS
        # (viec 2b, 12/08). Nguyen nhan thuong la loi DU LIEU (CTS tra 400 vi 1
        # field sai) - thu lai bao nhieu lan cung hong y het, chi tao rac. Giao
        # cho nguoi xu ly tay, giong cell vuot tran 10.
        # .get(..., 0) chu KHONG p["so_lan_thu"]: dong cu tao truoc migration co
        # the chua co key nay neu doc qua repo ban cu - khong de KeyError giet
        # ca luot quet.
        cell_het_luot_thu = {
            p["cell_name"]
            for p in phieu_da_co
            if p["trang_thai"] != "SUCCESS" and (p.get("so_lan_thu") or 0) >= XUAT_PHIEU_MAX_RETRY
        }
        # XOA MEM (THEM 04/10/2026) - xem chu y day du o _xem_truoc_mot_session()
        # (CUNG 1 dieu kien, 2 noi phai khop nhau tranh xem truoc/chay that lech).
        cell_da_xoa = {p["cell_name"] for p in phieu_da_co if p.get("deleted_at") is not None}

        # Buoc d+e: cat theo tran TRUOC (tren toan bo cell KHONG DAT, GIO theo
        # TUNG SECTOR - xem Buoc d trong _danh_gia_va_xep_hang()). Cell vuot
        # tran cua sector no KHONG xuat nhung PHAI ghi lai - de FE danh dau xu
        # ly thu cong, neu khong chung bien mat im lang (nguoi van hanh tuong
        # da xu ly het). SUA 04/10/2026: _danh_gia_va_xep_hang() tu cat san,
        # khong con slice [:XUAT_PHIEU_MAX_PER_SESSION] o day nua.
        top_duoc_phep, vuot_gioi_han, thieu_du_lieu = await self._danh_gia_va_xep_hang(session)
        # Tong so cell KHONG DAT (truoc khi cat theo sector) - dung lai cho
        # thong ke "so_cell_khong_dat"/"session co ung vien khong" ben duoi,
        # thu tu KHONG quan trong o 2 cho do (chi dem/kiem rong).
        ung_vien = top_duoc_phep + vuot_gioi_han

        # SAU KHI da cat top moi loai cell da co phieu SUCCESS - chong trung
        # (idempotent) o TANG JOB. execute() cung tu check lai (BUOC 1 cua no)
        # nen day la lop 2, KHONG phai duy nhat. Cell bi loai o day KHONG duoc
        # thay the bang cell thu 11: suat cua no trong top 10 da dung, chi la
        # da dung o luot truoc.
        duoc_xuat = [
            t
            for t in top_duoc_phep
            if t[0] not in cell_da_xuat and t[0] not in cell_het_luot_thu and t[0] not in cell_da_xoa
        ]
        bo_qua_da_co_phieu = [t[0] for t in top_duoc_phep if t[0] in cell_da_xuat]
        if bo_qua_da_co_phieu:
            logger.info(
                "Job xuat phieu: cac cell sau da co phieu SUCCESS tu luot truoc, bo qua",
                extra={"cr_session_id": session.id, "cell": bo_qua_da_co_phieu},
            )

        # XOA MEM (THEM 04/10/2026) - cell nguoi dung da CHU DONG xoa phieu,
        # KHONG duoc job tu dong tao lai (quyet dinh 04/10/2026). Chi LOG, KHONG
        # ghi cr_phieu moi nao cho nhom nay - ghi lai se chinh la "tao lai" ma
        # quyet dinh cam.
        bo_qua_da_xoa = [t[0] for t in top_duoc_phep if t[0] in cell_da_xoa]
        if bo_qua_da_xoa:
            logger.info(
                "Job xuat phieu: cac cell sau co phieu DA BI XOA, KHONG tao lai",
                extra={"cr_session_id": session.id, "cell": bo_qua_da_xoa},
            )

        # Cell het luot thu cung bi loai SAU khi cat top (giong cell da co
        # phieu): suat trong top 10 cua no da dung roi, KHONG duoc thay the
        # bang cell thu 11.
        vuot_so_lan_thu = [t[0] for t in top_duoc_phep if t[0] in cell_het_luot_thu]
        if vuot_so_lan_thu:
            logger.warning(
                "Job xuat phieu: cac cell sau da thu >= XUAT_PHIEU_MAX_RETRY lan van FAILED - "
                "NGUNG thu tu dong, can nguoi xu ly tay",
                extra={
                    "cr_session_id": session.id,
                    "max_retry": XUAT_PHIEU_MAX_RETRY,
                    "cell": vuot_so_lan_thu,
                },
            )

        if vuot_gioi_han:
            logger.warning(
                "Job xuat phieu: VUOT tran phieu/sector - cac cell sau KHONG duoc xuat tu dong",
                extra={
                    "cr_session_id": session.id,
                    "tran_moi_sector": XUAT_PHIEU_MAX_PER_SECTOR,
                    "so_cell_vuot": len(vuot_gioi_han),
                    "cell_vuot": [t[0] for t in vuot_gioi_han],
                },
            )

        # V4 (12/08) - ghi dong cr_phieu cho cell KHONG duoc xuat. Truoc day 2
        # nhom nay CHI nam trong job_run_log.chi_tiet nen nguoi van hanh phai mo
        # tung luot chay job ra doc, khong loc/sap xep/danh dau duoc.
        #
        # SUA 04/10/2026: thong diep doi tu "top N cell te nhat cua session"
        # sang "top N/sector" - tung cell vuot gioi han gio co the thuoc sector
        # BAT KY, khong con nghia la "ca session chi duoc N cell" nua.
        await self._ghi_cell_khong_xuat(
            session.id,
            [(t[0], t[1]) for t in vuot_gioi_han],
            TRANG_THAI_VUOT_GIOI_HAN,
            f"Ngoai top {XUAT_PHIEU_MAX_PER_SECTOR} cell te nhat cua sector (tram tat) - can xuat tay",
        )
        await self._ghi_cell_khong_xuat(
            session.id,
            [(t[0], t[1]) for t in top_duoc_phep if t[0] in cell_het_luot_thu],
            TRANG_THAI_HET_LUOT_THU,
            f"Da POST that >= {XUAT_PHIEU_MAX_RETRY} lan van khong thanh cong - "
            f"NGUNG thu tu dong, can nguoi xu ly nguyen nhan goc",
        )

        thanh_cong, that_bai, cell_da_xu_ly = 0, 0, []
        for cell_name, do_te, nguon, qoe, _danh_gia, khoa, sector in duoc_xuat:
            try:
                # Truyen nguon + QoE da tinh SAN xuong: execute() se dung de
                # dien Qoe/SoChiTieuVP/NoiDung trong payload va cot
                # nguon_khong_dat, KHONG goi CEM lai lan nua.
                # nguoi_thuc_hien=JOB_AUTO: day la vong lap cua job tu dong, khong phai
                # nguoi bam tay - phan biet duoc 2 nguon nay la muc dich chinh cua cot do
                result = await self.execute(
                    session.id, cell_name, nguon=nguon, qoe=qoe, nguoi_thuc_hien="JOB_AUTO"
                )
            except QoeDataInsufficientError:
                # execute() danh gia LAI (xem _danh_gia_qos_cell) - ve ly thuyet
                # da qua vong loc o tren nen khong toi day, tru khi data CTS doi
                # giua 2 lan goi. Bat rieng: day KHONG phai loi that su.
                logger.info(
                    "Job xuat phieu: cell thieu du lieu luc xuat, bo qua",
                    extra={"cr_session_id": session.id, "cell_name": cell_name},
                )
                continue
            except Exception as exc:  # noqa: BLE001 - CO Y bat rong: 1 cell loi khong giet ca session
                that_bai += 1
                logger.error(
                    "Job xuat phieu: goi xuat phieu that bai",
                    extra={"cr_session_id": session.id, "cell_name": cell_name, "loi": str(exc)},
                )
                cell_da_xu_ly.append(
                    {"cell_name": cell_name, "do_te": do_te, "ket_qua": f"LOI: {exc}", "sector": sector}
                )
                continue

            # SUCCESS = da tao phieu that tren TTS; FAILED = CTS tu choi;
            # DAT_KHONG_XUAT = cell dat tieu chi, khong can phieu (KHONG dem vao
            # ca 2 con so - khong phai thanh cong cung khong phai that bai).
            if result.trang_thai == "SUCCESS":
                thanh_cong += 1
            elif result.trang_thai == "FAILED":
                that_bai += 1
            cell_da_xu_ly.append(
                {
                    "cell_name": cell_name,
                    "do_te": round(do_te, 3),
                    # nhom + do_giam (09/2026) - 2 thanh phan THAT SU quyet dinh
                    # thu tu tu khi bo sort theo do_te. Khong ghi ra thi doc
                    # job_run_log se thay thu tu "sai" (do_te khong giam dan) ma
                    # khong co cach nao giai thich.
                    #   nhom 0 = diem TB sau < 3.0 (duoi muc toi thieu)
                    #   nhom 1 = con lai
                    "nhom": khoa[0],
                    "do_giam": round(-khoa[1], 3),
                    # sector (THEM 04/10/2026) - sector cua tram tat, de nguoi
                    # doc job_run_log doi chieu dung tran 2/sector (thay vi
                    # tran 6/session cu) - xem XUAT_PHIEU_MAX_PER_SECTOR.
                    "sector": sector,
                    "nguon_khong_dat": nguon,
                    "ket_qua": result.trang_thai,
                    "phieu_id": result.phieu_id,
                }
            )

        # 14/08 - GHI KET QUA vao cr_session (2 cot moi). Day la dau vet DUY NHAT
        # cho biet job DA quet session nay; khong co no thi truong hop
        # KHONG_CAN_XUAT (0 dong cr_phieu) khong phan biet duoc voi "chua quet".
        #
        # TU GIA DINH - dac ta chi neu 3 nhanh (co SUCCESS / 0 cell KHONG DAT /
        # session nem exception), KHONG neu truong hop CO cell KHONG DAT nhung
        # KHONG xuat duoc phieu nao (tat ca FAILED, hoac deu bi loai vi da co
        # phieu / het luot thu). Chon KET_QUA_LOI cho truong hop do:
        #   - DA_XUAT sai han: khong co phieu nao duoc tao.
        #   - KHONG_CAN_XUAT sai nguy hiem hon: no bao "session nay khong can
        #     phieu", trong khi that ra co cell can ma job khong lam duoc -> nguoi
        #     van hanh se BO QUA session dang can xu ly tay.
        # Chon nhanh bao dong thay vi nhanh im lang.
        if thanh_cong > 0:
            ket_qua_session = KET_QUA_DA_XUAT
        elif not ung_vien:
            ket_qua_session = KET_QUA_KHONG_CAN_XUAT
        else:
            ket_qua_session = KET_QUA_LOI
        await self._ghi_ket_qua_xuat_phieu_session(session.id, ket_qua_session)

        return {
            "cr_session_id": session.id,
            "xuat_phieu_ket_qua": ket_qua_session,
            "tram_id": session.tram_id,
            "so_cell_khong_dat": len(ung_vien),
            # Cach C - cell KHONG ket luan duoc (da co dong cr_phieu
            # KHONG_XUAT_THIEU_DU_LIEU). Tach RIENG khoi so_cell_khong_dat:
            # "khong dat" la KET LUAN, con day la "khong ket luan duoc" - gop
            # chung se lam thong ke sai ban chat.
            "cell_thieu_du_lieu": thieu_du_lieu,
            "cell_da_xu_ly": cell_da_xu_ly,
            # Chi luu TEN cell vuot + do te - du de FE hien danh sach can xu ly
            # thu cong, khong phinh chi_tiet bang ca payload. Danh sach nay
            # GIU NGUYEN qua cac luot (cell thu 11+ khong bao gio duoc xuat tu
            # dong) - do la thu FE can de danh dau viec con ton.
            "cell_vuot_gioi_han": [
                {
                    "cell_name": t[0],
                    "do_te": round(t[1], 3),
                    # nhom/do_giam (09/2026) - de nguoi doc kiem chung duoc VI
                    # SAO cell nay bi cat con cell kia thi khong.
                    "nhom": t[5][0],
                    "do_giam": round(-t[5][1], 3),
                    "nguon_khong_dat": t[2],
                    # sector (THEM 04/10/2026) - sector cua tram tat, giai
                    # thich cell nay vuot tran CUA SECTOR NAO (tran gio tinh
                    # theo sector, khong phai theo ca session).
                    "sector": t[-1],
                }
                for t in vuot_gioi_han
            ],
            # Cell nam trong top 10 nhung da xuat phieu o luot truoc - ghi lai
            # de doc job_run_log biet vi sao luot nay xuat it hon 10 cell.
            "cell_da_co_phieu": bo_qua_da_co_phieu,
            # Nhom RIENG (khong gop vao cell_vuot_gioi_han): 2 ly do bi loai
            # khac han nhau - "vuot tran 10" la con cho o luot sau neu cell tren
            # no xong, con "het luot thu" la da that bai 3 lan, phai sua nguyen
            # nhan goc moi xuat duoc. FE can phan biet de hien dung viec can lam.
            "cell_vuot_so_lan_thu": vuot_so_lan_thu,
            "_thanh_cong": thanh_cong,
            "_that_bai": that_bai,
            "_vuot": len(vuot_gioi_han),
        }

    async def execute_all_pending(
        self,
        job_run_log_id: int | None = None,
        tu_ngay: date | None = None,
        den_ngay: date | None = None,
    ) -> dict:
        """Quet session du ngay -> xuat phieu cho cell KHONG DAT (toi da
        XUAT_PHIEU_MAX_PER_SECTOR cell/sector cua tram tat - SUA 04/10/2026,
        te nhat trong sector truoc).

        LUON POST THAT (V2 da bo dry_run). Cong tac bat/tat la SCHEDULER_ENABLED.

        job_run_log_id: dong RUNNING da duoc tao TRUOC khi goi ham nay (caller
        tao, xem IJobRunLogRepo.insert) - ham nay chi cap nhat KET QUA vao dong
        do. Tach vai tro nhu vay de dong RUNNING ton tai NGAY CA KHI ham nay
        chet ngay dong dau tien.

        tu_ngay/den_ngay (20082026, CHAY BU BANG TAY): quet khoang ngay CR
        thay vi DUNG 1 ngay. CA HAI mac dinh None -> hanh vi PA A CU KHONG DOI,
        nen JOB TU DONG khong phai sua gi (no khong truyen 2 tham so nay).
        Gioi han an toan (toi da 30 ngay, khong quet ngay chua du T+7) nam o
        TANG ROUTER - day la ham thi hanh, khong phai noi dat luat cho UI.
        """
        so_session_quet = 0
        so_phieu_thanh_cong = 0
        so_phieu_that_bai = 0
        so_cell_vuot_gioi_han = 0
        chi_tiet_sessions = []

        try:
            sessions = await self._lay_session_du_dieu_kien(tu_ngay=tu_ngay, den_ngay=den_ngay)
            for session in sessions:
                so_session_quet += 1
                try:
                    ket_qua = await self._xu_ly_mot_session(session)
                except Exception as exc:  # noqa: BLE001 - CO Y bat rong: 1 session loi
                    # KHONG duoc giet ca luot (dac ta BUOC 1). Ghi vao chi_tiet
                    # de doc lai duoc, KHONG nuot im lang.
                    logger.error(
                        "Job xuat phieu: xu ly session that bai, bo qua session nay",
                        extra={"cr_session_id": session.id, "loi": str(exc)},
                    )
                    # 14/08 - PHAI danh dau LOI vao cr_session ngay o day.
                    # _xu_ly_mot_session() da chet giua chung nen khong tu ghi
                    # duoc; neu bo qua thi session hien "chua toi luot quet"
                    # (xuat_phieu_at NULL) y het session that su chua quet - va
                    # theo PA A no se KHONG BAO GIO duoc quet lai de sua, tuc la
                    # 1 session loi bi giau vinh vien khoi man hinh theo doi.
                    await self._ghi_ket_qua_xuat_phieu_session(session.id, KET_QUA_LOI)
                    chi_tiet_sessions.append({"cr_session_id": session.id, "loi": str(exc)})
                    continue

                so_phieu_thanh_cong += ket_qua.pop("_thanh_cong")
                so_phieu_that_bai += ket_qua.pop("_that_bai")
                so_cell_vuot_gioi_han += ket_qua.pop("_vuot")
                chi_tiet_sessions.append(ket_qua)

        except Exception as exc:  # noqa: BLE001 - loi TOAN CUC (vd query session chet)
            # Khac loi tung session o tren: toi day khong con gi de quet nua ->
            # danh dau ca luot FAILED. VAN ghi cac con so da dem duoc (khong
            # xoa trang) de biet job da lam duoc den dau truoc khi chet.
            logger.error("Job xuat phieu: LOI TOAN CUC, dung luot chay", extra={"loi": str(exc)})
            await self._ghi_ket_qua_job(
                job_run_log_id,
                trang_thai="FAILED",
                so_session_quet=so_session_quet,
                so_phieu_thanh_cong=so_phieu_thanh_cong,
                so_phieu_that_bai=so_phieu_that_bai,
                so_cell_vuot_gioi_han=so_cell_vuot_gioi_han,
                error_message=str(exc),
                chi_tiet={"sessions": chi_tiet_sessions},
            )
            raise

        await self._ghi_ket_qua_job(
            job_run_log_id,
            trang_thai=_trang_thai_luot_chay(so_phieu_thanh_cong, so_phieu_that_bai),
            so_session_quet=so_session_quet,
            so_phieu_thanh_cong=so_phieu_thanh_cong,
            so_phieu_that_bai=so_phieu_that_bai,
            so_cell_vuot_gioi_han=so_cell_vuot_gioi_han,
            error_message=None,
            chi_tiet={"sessions": chi_tiet_sessions},
        )

        return {
            "so_session_quet": so_session_quet,
            "so_phieu_thanh_cong": so_phieu_thanh_cong,
            "so_phieu_that_bai": so_phieu_that_bai,
            "so_cell_vuot_gioi_han": so_cell_vuot_gioi_han,
            "chi_tiet": {"sessions": chi_tiet_sessions},
        }

    async def _ghi_ket_qua_job(self, job_run_log_id: int | None, **kwargs) -> None:
        # job_run_log_id=None (goi truc tiep tu script/test, khong qua scheduler)
        # -> khong co dong nao de cap nhat, bo qua. KHONG raise: ghi lich su la
        # viec PHU TRO, khong duoc lam hong luot xuat phieu that su da chay xong.
        if job_run_log_id is None or self._job_run_log_repo is None:
            return
        try:
            await self._job_run_log_repo.update_result(
                job_run_log_id, finished_at=datetime.now(timezone.utc), **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - xem ly do ngay tren
            logger.error(
                "Job xuat phieu: ghi job_run_log THAT BAI (phieu da xuat KHONG bi anh huong)",
                extra={"job_run_log_id": job_run_log_id, "loi": str(exc)},
            )
