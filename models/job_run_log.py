"""
SQLModel: bang job_run_log.
Tu: yeu cau truc tiep user (JOB TU DONG - Buoc 1/4) - luu lich su MOI LAN job/
scheduler chay.

Vi sao can bang rieng (khong ghi vao cr_log/audit_log co san):
- cr_log khoa theo cr_session_id (FK NOT NULL) - 1 lan job chay quet NHIEU
  session, khong gan duoc vao 1 session cu the.
- audit_log la nhat ky hanh dong tren doi tuong nghiep vu, khong co cho chua
  cac con so tong ket cua 1 LUOT chay (so session quet, so phieu thanh cong...).
- Job chay nen qua BackgroundTasks, khong ai nhin thay ket qua neu khong ghi
  lai - dong nay CHINH LA bang chung job da chay va ket qua ra sao.

KHONG co FK toi cr_session: 1 dong = 1 LUOT chay job (quet nhieu session),
KHAC cr_log/cr_phieu/cr_affected_cells (deu la du lieu CUA 1 session).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class JobRunLog(SQLModel, table=True):
    __tablename__ = "job_run_log"

    id: int | None = Field(default=None, primary_key=True)

    # "xuat_phieu_auto" (job dau tien se dung), de ngo cho job khac sau nay
    # (evaluate-cr, sync-rims...) dung CHUNG bang nay thay vi moi job 1 bang.
    # VARCHAR + index thay vi Enum: them loai job moi chi la them gia tri, KHONG
    # phai migration doi kieu - cung ly do models/cr_phieu.py chon str cho
    # trang_thai.
    job_type: str = Field(sa_column=sa.Column(sa.VARCHAR(50), nullable=False, index=True))

    # C1.4-fix9 (21072026) - KHONG server_default=now(): Postgres server
    # TimeZone GUC = Asia/Ho_Chi_Minh nen now() se ghi GIO VN thay vi UTC. Luon
    # set qua Python datetime.now(timezone.utc) trong adapter (xem
    # adapters/postgres/job_run_log_repo.py). Lenh cam nay CHI ap dung cho cot
    # thoi gian - cac cot so/bool ben duoi van dung server_default binh thuong
    # (khong dinh gi toi timezone), giong models/alert_log.py::is_acknowledged.
    started_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    # Nullable - dong duoc tao luc job BAT DAU (trang_thai=RUNNING), chua biet
    # khi nao xong. NULL cung la dau hieu nhan ra job chet giua chung (RUNNING
    # + finished_at IS NULL + started_at qua lau) - bai hoc tu session #197 ket
    # vinh vien RUNNING (C1.4-fix2).
    finished_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True)))

    # RUNNING / DONE / FAILED / PARTIAL - cung pattern str cua cr_phieu.trang_thai.
    # PARTIAL them 02092026 (B3): 7 ky tu, vua VARCHAR(20) nen KHONG can migration
    # (3 gia tri don gian, khong co state machine phuc tap can Enum).
    trang_thai: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))

    # V2 (12/08): DA BO cot dry_run. Job khong con che do chay thu - moi luot
    # deu POST that - nen cot nay chi con 1 gia tri duy nhat (false), khong
    # phan biet duoc gi nua ma van bat moi cho doc phai mang theo.

    # 4 con so tong ket 1 luot chay. server_default="0" + NOT NULL de khong bao
    # gio phai xu ly None luc doc/cong don o FE (0 va NULL cung nghia "khong co"
    # nhung NULL bat moi cho doc phai kiem tra rieng).
    so_session_quet: int = Field(
        default=0, sa_column=sa.Column(sa.INTEGER, nullable=False, server_default=sa.text("0"))
    )
    so_phieu_thanh_cong: int = Field(
        default=0, sa_column=sa.Column(sa.INTEGER, nullable=False, server_default=sa.text("0"))
    )
    so_phieu_that_bai: int = Field(
        default=0, sa_column=sa.Column(sa.INTEGER, nullable=False, server_default=sa.text("0"))
    )
    so_cell_vuot_gioi_han: int = Field(
        default=0, sa_column=sa.Column(sa.INTEGER, nullable=False, server_default=sa.text("0"))
    )

    error_message: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))

    # Optional - danh sach session/cell da xu ly. JSONB (khong phai bang con
    # rieng) vi day la du lieu CHI DE DOC LAI khi dieu tra, khong join/query
    # theo tung phan tu - cung ly do cr_log.detail/audit_log.detail dung JSONB.
    chi_tiet: dict | None = Field(default=None, sa_column=sa.Column(JSONB))

    __table_args__ = (
        # DESC index - man hinh lich su luon xem LUOT MOI NHAT truoc, index ASC
        # mac dinh (index=True) khong phuc vu duoc thu tu nay. Dung sa.text()
        # theo dung pattern da co o models/cr_session.py/alert_log.py/audit_log.py.
        sa.Index("idx_job_run_log_started", sa.text("started_at DESC")),
    )
