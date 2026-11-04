"""
SQLModel: bang cr_phieu.
Tu: yeu cau truc tiep user (KHOI 2/5 SaveCellClm) - luu phieu da xuat qua
SaveCellClm (KHOI 1/5) de audit + chong trung (khong goi API 2 lan cho cung
1 cell trong cung 1 CR session).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CrPhieu(SQLModel, table=True):
    __tablename__ = "cr_phieu"

    id: int | None = Field(default=None, primary_key=True)
    cr_session_id: int = Field(
        sa_column=sa.Column(sa.INTEGER, sa.ForeignKey("cr_session.id"), nullable=False, index=True)
    )
    cell_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False))

    # PENDING (moi tao, chua goi CTS) / SUCCESS / FAILED / KHONG_XUAT_VUOT_GIOI_HAN
    # / KHONG_XUAT_HET_LUOT_THU (V4) - gan giong pattern trang_thai str cua
    # cr_session.status (models/cr_session.py), khong dung Enum rieng vi chi vai
    # gia tri, khong co state machine phuc tap.
    #
    # VARCHAR(30) chu KHONG phai 20 (noi rong o V4, 12/08): 2 gia tri moi dai 24
    # va 23 ky tu -> VARCHAR(20) lam INSERT chet ngay
    # (StringDataRightTruncationError, bat duoc bang test integration TRUOC khi
    # len production). 30 = du cho gia tri dai nhat + con cho, khong noi qua tay.
    trang_thai: str = Field(sa_column=sa.Column(sa.VARCHAR(30), nullable=False))

    # Luu nguyen 28 field da gui CTS - audit "da gui gi", doc lap voi ket qua
    # tra ve (request co the dung nhung response fail o buoc khac).
    request_payload: dict = Field(sa_column=sa.Column(JSONB, nullable=False))
    # Nullable - chua co khi trang_thai=PENDING (moi tao dong truoc khi goi CTS).
    response_body: dict | None = Field(default=None, sa_column=sa.Column(JSONB))
    # id phieu tren he thong TTS, trich tu response.data khi SUCCESS - dung de
    # tra cuu/doi chieu phieu that tren CTS/TTS, KHONG phai PK noi bo.
    phieu_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100)))
    error_message: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))

    # So lan DA THU XUAT THAT (POST len TTS) cho cell nay - them 12/08 (viec 2b).
    # VI SAO CAN COT RIENG: uq_cr_phieu_session_cell chi cho 1 dong/cell/session,
    # retry GHI DE dong cu hoan toan (update_result) nen KHONG the dem so lan thu
    # tu so dong hay tu created_at (created_at la luc tao dong dau tien, khong
    # doi qua cac lan retry). Khong co cot nay thi phieu FAILED do loi du lieu
    # (CTS tra 400) se bi thu lai VO HAN moi ngay.
    #
    # server_default="0" + NOT NULL: dong CU (da ton tai truoc migration) tu
    # nhien co gia tri 0 - dung y nghia "chua dem lan nao", khong can backfill.
    # Day KHONG phai cot thoi gian nen server_default an toan (lenh cam
    # server_default chi ap dung cho timestamp - C1.4-fix9).
    so_lan_thu: int = Field(
        default=0, sa_column=sa.Column(sa.INTEGER, nullable=False, server_default=sa.text("0"))
    )

    # QOS / QOE / CA_HAI - chi so nao lam cell nay KHONG DAT (17082026, QoE
    # ngang hang QoS). Xem ly do day du trong migration them cot nay.
    #
    # NULLABLE, khong server_default: dong tao TRUOC dot nay khong biet duoc
    # nguon that (luc do chi co QoS nen "doan nguoc" thanh QOS se la BIA - co
    # the co cell luc do dat QoS nhung khong dat QoE ma he thong chua biet).
    # NULL dung nghia "khong ghi nhan".
    nguon_khong_dat: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(10)))

    # KHONG server_default=now() - dung pattern C1.4-fix9 da ap dung cho toan
    # bo cot TIMESTAMPTZ trong project (Postgres server TimeZone GUC =
    # Asia/Ho_Chi_Minh, server_default=now() se ghi gio VN thay vi UTC). Luon
    # set qua Python datetime.now(timezone.utc) trong adapter (xem
    # adapters/postgres/cr_phieu_repo.py).
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    # XOA MEM (THEM 04/10/2026, yeu cau truc tiep user, migration c2d1b876c908)
    # - thay the HARD DELETE cu. NULL = chua xoa (gia tri mac dinh moi dong).
    # Co gia tri = da xoa: dong VAN CON trong bang (giu nguyen UNIQUE(cr_session_id,
    # cell_name) chiem cho) de get_by_session_cell() con THAY duoc ma chan
    # XuatPhieuUseCase.execute() tao lai phieu cho cung cell - xem chu y day du
    # trong application/xuat_phieu_use_case.py. MOI noi hien thi/dem (list_phieu,
    # count_phieu...) phai loc deleted_at IS NULL - xem adapters/postgres/cr_phieu_repo.py.
    #
    # KHONG server_default=now() - pattern C1.4-fix9 (xem created_at o tren).
    deleted_at: datetime | None = Field(default=None, sa_column=sa.Column(sa.TIMESTAMP(timezone=True)))

    __table_args__ = (
        # Chong trung 1 cell chi co 1 phieu / 1 CR session - khoi phai POST
        # lai SaveCellClm (WRITE API that) neu retry/goi lai cung session.
        sa.UniqueConstraint("cr_session_id", "cell_name", name="uq_cr_phieu_session_cell"),
    )
