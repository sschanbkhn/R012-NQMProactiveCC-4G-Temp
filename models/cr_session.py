"""
SQLModel: bang cr_session + CrStatusDB enum.
Tu: DB_SCHEMA.md Section 3; TASK_LIST.md B4.3
"""

from datetime import datetime, timezone
from enum import Enum

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class CrStatusDB(str, Enum):
    # Enum rieng cho DB layer (khac domain/entities/cr_session.py CrStatus, B2.6) —
    # models/ khong import tu domain/ de giu 2 layer doc lap (models/__init__.py
    # dong 2). Gia tri phai khop 9 trang thai cua CrStatus (V23, 09/2026: sua
    # tu 7 - da doi chieu voi enum THAT, khong con mau thuan) — neu domain
    # enum doi thi phai tu sua cho nay theo.
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    EVALUATING = "EVALUATING"
    EVALUATED = "EVALUATED"
    EVAL_PENDING = "EVAL_PENDING"
    # Cach C (16082026) - dong bo voi CrStatus.KHONG_DU_DU_LIEU ben domain
    # (theo dung canh bao o comment tren: "neu domain enum doi thi phai tu sua
    # cho nay theo"). 16 ky tu, vua VARCHAR(20) - KHONG can migration.
    KHONG_DU_DU_LIEU = "KHONG_DU_DU_LIEU"
    # 18082026 - dong bo voi CrStatus.PARTIAL_SUCCESS ben domain (2 enum RIENG,
    # sua 1 cai la lech AM THAM - da gap dung loi nay o KHONG_DU_DU_LIEU).
    # 15 ky tu, vua VARCHAR(20) - khong can migration.
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    # THEM 16/10/2026 - dong bo voi CrStatus.KHONG_CHAY ben domain (xem dac ta
    # day du o do). 10 ky tu, vua VARCHAR(20) - khong can migration cho CHINH
    # cot status (chi can migration RIENG cho cot MOI ma_loi, xem duoi).
    KHONG_CHAY = "KHONG_CHAY"


class CrSession(SQLModel, table=True):
    __tablename__ = "cr_session"

    id: int | None = Field(default=None, primary_key=True)
    tram_id: str = Field(
        sa_column=sa.Column(sa.VARCHAR(50), sa.ForeignKey("tram.tram_id"), nullable=False, index=True)
    )
    action: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))

    status: str = Field(
        default=CrStatusDB.PENDING.value,
        sa_column=sa.Column(sa.VARCHAR(20), nullable=False, server_default=CrStatusDB.PENDING.value, index=True),
    )

    plan_name: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))
    backup_plan_name: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))
    xml_filename: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(200)))

    qoe_result: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(20)))
    qos_result: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(20)))
    qoe_before: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(3, 2)))
    qoe_after: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(3, 2)))
    qos_before: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(3, 2)))
    qos_after: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(3, 2)))

    is_rollback: bool = Field(
        default=False, sa_column=sa.Column(sa.BOOLEAN, nullable=False, server_default=sa.false())
    )
    rollback_of_id: int | None = Field(
        default=None, sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"))
    )

    # C1.4-fix10 (21072026) - doi sang TIMESTAMPTZ (truoc la TIMESTAMP thuong,
    # bi loai khoi C1.4-fix9 vi gia tri da dung UTC san). Van khong bug ve GIA
    # TRI, nhung cot naive khien SQLAlchemy/asyncpg doc len tra datetime KHONG
    # tzinfo -> response JSON (Pydantic) thieu "Z" khac voi created_at/
    # updated_at (da la TIMESTAMPTZ) - sua de BE tra timestamp NHAT QUAN.
    # KHONG them default= (gia tri luon do use case tu gan tuong minh khi CR
    # xong/evaluate xong, khong set luc tao session).
    executed_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True)))
    evaluated_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True)))

    # === Theo doi tien trinh XUAT PHIEU (14/08) ===
    #
    # VI SAO CAN 2 COT MOI (khong suy ra duoc tu du lieu da co):
    # 1. KHONG co truong nao ghi "da danh gia theo tieu chi XUAT PHIEU".
    #    status=EVALUATED den tu EvaluateCrUseCase (nguong -0.1, moc
    #    EVALUATION_DAYS=21) - co che KHAC HAN XuatPhieuUseCase (nguong -0.2,
    #    moc XUAT_PHIEU_AFTER_DAYS=8). Hai thu doc lap, va job 21 ngay CHUA
    #    TUNG chay that (kiem tra DB: 0 session co evaluated_at).
    # 2. Suy tien trinh tu bang cr_phieu KHONG DU: truong hop TAT CA CELL DAT
    #    (job quet xong nhung khong xuat phieu nao) tao ra 0 dong cr_phieu -
    #    KHONG phan biet duoc voi "chua toi luot quet" (cung 0 dong).
    #    Voi PA A moi session chi duoc quet DUNG 1 LAN, nen session do se hien
    #    "dang cho" VINH VIEN tren UI du thuc te da xong.
    #
    # NULL = chua toi luot quet (hoac da qua han ma job lo mat ngay do).
    xuat_phieu_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True)))

    # === TY LE CELL PROVISION THANH CONG (02092026, thay 2 cot so_dn_* cu) ===
    # Dem theo CELL chu khong theo DN/tram: 1 managedObject trong XML NetAct la
    # 1 CELL (LNCEL), MRBTS chi la noi cell cam vao. Lay tu SUCCESSFUL MOS /
    # FAILED MOS trong output provision. Xem ly do day du trong migration
    # b3f7d21ac504.
    # NULL o cac session cu (2 cot DN cu da bi xoa han, KHONG chuyen gia tri
    # sang vi so cu dem tram - copy sang se thanh so cell noi doi).
    so_cell_thanh_cong: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    so_cell_tong: int | None = Field(default=None, sa_column=sa.Column(sa.INTEGER))
    # A6 (02092026) - duong dan file log NetAct trong docs/logs/netact_runs/.
    # NULL khi session chua chay xong hoac chay truoc dot nay. Dung cho endpoint
    # GET /sessions/{id}/log-netact doc lai output that khi can dieu tra.
    duong_dan_log: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(500)))
    # oss_instance_id/noc (02/10/2026) - OSS/NOC MA session nay THAT SU gui CR
    # len (hoac co gang gui, tham chi that bai o Import/Provision - xem
    # trigger_cr_use_case.py::_fail()), de tra lich su "session nay chay tren
    # NetAct nao". NULL khi CR bi tu choi TRUOC khi chon duoc OSS (vd
    # CR_NHIEU_OSS, OSS_CHUA_CAU_HINH cho het cell, CDS loi som...) - khong co
    # gia tri nao de ghi, KHONG duoc doan/dien bua. instance_id la CHUOI (ten
    # goi NetAct, vd "NA09"), KHONG phai FK toi bang nao (OSS cau hinh trong
    # .env, khong co bang DB rieng).
    oss_instance_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(50)))
    noc: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(20)))
    # ma_loi (THEM 16/10/2026, migration VIET TAY - xem alembic/versions/) -
    # error_code cua DomainError gay FAILED/KHONG_CHAY (vd "KHONG_CO_DU_LIEU_HO",
    # xem domain/errors.py). VARCHAR(30) chu KHONG phai 20 - CUNG bai hoc voi
    # xuat_phieu_ket_qua duoi day (ma_loi dai nhat hien tai la
    # "CR_EVALUATION_IN_PROGRESS" = 25 ky tu, can du cho con cho).
    ma_loi: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(30)))
    # DA_XUAT / KHONG_CAN_XUAT / LOI - VARCHAR(30) chu KHONG phai 20: bai hoc
    # tu cr_phieu.trang_thai (V4) phai them 1 migration rieng chi vi gia tri
    # dai 24 ky tu khong vua VARCHAR(20). 30 la du cho cac gia tri nay + con cho.
    # Dung str thay vi Enum - cung ly do voi status/trang_thai da co: them gia
    # tri moi chi la them chuoi, KHONG phai migration doi kieu.
    xuat_phieu_ket_qua: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(30)))
    # C1.4-fix9 (21072026) - xem chu y day du trong models/tram.py
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )
    updated_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )
    )

    __table_args__ = (
        # DB_SCHEMA.md dong 174 - DESC index, khong dung index=True (mac dinh ASC)
        sa.Index("idx_cr_session_created_at", sa.text("created_at DESC")),
        sa.Index("idx_cr_session_executed", "executed_at"),
    )
