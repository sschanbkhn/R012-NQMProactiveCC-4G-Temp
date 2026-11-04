"""
CrSession entity + CrStatus enum — pure Python.
Tu: ARCHITECTURE.md Section 3.1; BUSINESS_RULES.md Section 11; DB_SCHEMA.md (cr_session)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CrStatus(str, Enum):
    # BUSINESS_RULES.md SS11 dong 502-511 — 9 state (V23, 09/2026: sua tu 7 -
    # da them KHONG_DU_DU_LIEU 16/08 va PARTIAL_SUCCESS 18/08 sau khi comment
    # nay viet, so LAI voi enum THAT thay vi sua theo tri nho), khop
    # DB_SCHEMA.md dong 146.
    # Ke thua str de value khop thang string luu DB (VD: CrStatus("PENDING")),
    # khong can bang mapping rieng — dung nhu ARCHITECTURE.md dong 528:
    # status=CrStatus(record.status)
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    EVALUATING = "EVALUATING"
    EVALUATED = "EVALUATED"
    EVAL_PENDING = "EVAL_PENDING"
    # Cach C (16082026, yeu cau truc tiep user) - TRANG THAI CUOI cho "thieu du
    # lieu, KHONG ket luan duoc". KHAC EVAL_PENDING:
    #   EVAL_PENDING     = "CHO them du lieu" -> job quet lai hang ngay
    #   KHONG_DU_DU_LIEU = "KHONG cho nua"    -> khong quet lai
    # Ly do phai tach: du lieu thieu do nguon KHONG CO (vd lo thung CEM
    # 16/07 va 21-27/07) se KHONG BAO GIO xuat hien. Giu EVAL_PENDING thi
    # session quet lai VINH VIEN va sau 30 ngay con ban alert admin - session
    # 553 la ca that.
    KHONG_DU_DU_LIEU = "KHONG_DU_DU_LIEU"
    # 18082026 - CR chay xong nhung CHI MOT SO DN provision duoc.
    #
    # VI SAO CAN: CR that 18/08 co 4 DN, 3 thanh cong (6 MO da doi tham so RF
    # THAT len thiet bi) va 1 hong (NoRouteToHost). Bao ca CR la FAILED la NOI
    # SAI SU THAT - nguoi van hanh tuong khong co gi xay ra va chay lai ca 4,
    # trong khi 3 tram kia DA doi roi. Bao DONE cung sai not: tram thu 4 chua
    # doi ma khong ai biet.
    #
    # 15 ky tu, vua VARCHAR(20) - KHONG can migration (KHONG_DU_DU_LIEU 16 ky
    # tu da vua tu truoc).
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - tach
    # khoi FAILED: loi xay ra TRUOC buoc 13 "SSH: Upload+Import+Provision"
    # (chua tung gui lenh nao len NetAct - vd HoNoDataError/CrNhieuOssError/
    # CdsApiError/XmlBuildError) -> KHONG_CHAY. Loi tu buoc 13 tro di (da gui/
    # dang gui SSH that, ke ca khi SSH that bai hoan toan) -> VAN la FAILED
    # nhu cu (xem application/trigger_cr_use_case.py::_fail()). Ly do tach:
    # FE hien CA 2 giong het nhau (tag do + nut [Retry]) - nguoi van hanh
    # khong phan biet duoc "can sua du lieu/cau hinh truoc khi thu lai" voi
    # "NetAct/mang that su co van de". 10 ky tu, vua VARCHAR(20).
    KHONG_CHAY = "KHONG_CHAY"


@dataclass
class CrSession:
    # Entity mutable (khong frozen) — status bi ghi de xuyen suot vong doi
    # (PENDING->RUNNING->DONE/FAILED->EVALUATING->EVALUATED/EVAL_PENDING).
    #
    # (a) Co field "id" — khac Tram/Cell (khong co "id"). Ly do: session_id o day
    # la business identifier duoc dung xuyen suot he thong (API response
    # "session_id": 42, SSE stream /cr/stream/{session_id}, audit_log,
    # rollback_of_id tham chieu chinh no) — khong phai surrogate key an nhu
    # tram.id/cell_params.id ma domain khong bao gio dung toi.
    #
    # (b) KHONG co method (VD: can_transition_to()/is_terminal()) du co state
    # machine ro rang (BUSINESS_RULES.md SS11). Bang chung: ca TriggerCrUseCase
    # va EvaluateCrUseCase (ARCHITECTURE.md SS4.1/4.2) deu tu gan status truc
    # tiep theo tung buoc, khong goi qua guard method nao tren entity. Giu nhat
    # quan voi Tram/Cell (data holder thuan) — khong tu them logic ngoai docs.
    #
    # (c) 8/19 field so voi bang cr_session (DB_SCHEMA.md dong 139-169) — GAP
    # phat hien khi code C2.1 (TriggerCrUseCase, 12072026, xac nhan voi user):
    # ban dau chi 5 field (id/tram_id/action/status/plan_name), nhung
    # WORKFLOW.md buoc 15 ("Luu backup_plan_name vao cr_session") va buoc 17
    # ("cr_session.executed_at = NOW()") KHONG THE thuc hien duoc voi 5 field
    # do — them dung 3 field flow trigger thuc su can (backup_plan_name,
    # xml_filename, executed_at), KHONG them het 11 field con lai.
    # qoe_result/qos_result/qoe_before/after/qos_before/after/is_rollback/
    # rollback_of_id/evaluated_at/created_at/updated_at VAN KHONG co o day —
    # thuoc CrSessionDetail (read-model rieng, Part D, chua lam toi) hoac
    # EvaluateCrUseCase (C2.2, chua code).
    id: int
    tram_id: str
    action: str
    status: CrStatus
    plan_name: str | None
    backup_plan_name: str | None = None
    xml_filename: str | None = None
    executed_at: datetime | None = None

    # Them o C2.3/C2.4 (13072026, Nhom 2) - can cho GET /sessions + GET /sessions/{id}
    # (API_CONTRACTS.md). Tat ca Optional default None - KHONG anh huong caller cu
    # (TriggerCrUseCase C2.1 khong set cac field nay, van None nhu truoc).
    tram_name: str | None = None
    # read-model, KHONG phai cot cua bang cr_session (join tu tram.tram_name) -
    # chi CrSessionRepo.list()/get_by_id() (co join) moi dien gia tri, con
    # create()/update() (khong join) de None.
    created_at: datetime | None = None
    qoe_result: str | None = None
    qos_result: str | None = None
    qoe_before: float | None = None
    qoe_after: float | None = None
    qos_before: float | None = None
    qos_after: float | None = None
    evaluated_at: datetime | None = None

    # Them 16082026 (man hinh theo doi tien trinh 4 buoc cua FE).
    #
    # xuat_phieu_at: cot THAT cua bang cr_session (migration e98069b2cd40) nhung
    # truoc gio KHONG duoc map vao entity - GAP that, phat hien khi lam man hinh
    # tien trinh: khong co no thi khong phan biet duoc "cho thu thap KPI" (buoc 2)
    # voi "da xuat phieu xong" (buoc 4).
    xuat_phieu_at: datetime | None = None

    # Ty le DN provision thanh cong (19082026) - cot THAT cua cr_session
    # (migration 4ae6f4d7503b). None o session cu (chay truoc dot nay) VA khi
    # provision chua chay xong - khac 0/0 ("da dem, khong DN nao thanh cong").
    so_cell_thanh_cong: int | None = None
    so_cell_tong: int | None = None
    # A6 - duong dan file log NetAct (xem models/cr_session.py)
    duong_dan_log: str | None = None

    # oss_instance_id/noc (02/10/2026) - xem chu y day du trong
    # models/cr_session.py. NULL o session cu (chay truoc dot nay, se duoc
    # BACKFILL rieng qua migration VIET TAY - xem alembic/versions/) VA o
    # session bi tu choi truoc khi chon duoc OSS.
    oss_instance_id: str | None = None
    noc: str | None = None

    # ma_loi (16/10/2026) - error_code cua DomainError gay FAILED/KHONG_CHAY
    # (vd "KHONG_CO_DU_LIEU_HO", "SSH_CONNECTION_ERROR" - xem domain/errors.py).
    # None o session DONE/PARTIAL_SUCCESS (khong co loi) VA o session cu (chay
    # truoc migration nay, KHONG backfill - khong co du lieu goc de suy lai
    # error_code chinh xac tu message tu do da luu).
    ma_loi: str | None = None

    # 3 field READ-MODEL - KHONG phai cot cua bang cr_session, dem tu bang khac.
    # Chi CrSessionRepo.list() dien gia tri (co subquery dem); create()/update()/
    # get_by_id() de mac dinh 0. Dung y het cach tram_name da lam (xem chu y o
    # tren) - khong tao read-model rieng cho 3 con so.
    so_cell_anh_huong: int = 0  # COUNT cr_affected_cells
    so_phieu_da_xuat: int = 0  # COUNT cr_phieu trang_thai=SUCCESS
    so_cell_cho_xuat_tay: int = 0  # COUNT cr_phieu trang_thai KHONG_XUAT_*
