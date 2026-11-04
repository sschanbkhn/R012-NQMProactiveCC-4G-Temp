"""
SQLModel: bang cr_phieu_lan_thu - lich su TUNG LAN POST phieu len CTS (A5).

Tu: yeu cau truc tiep user 02092026.

VI SAO CAN BANG RIENG (khong nhet them cot vao cr_phieu):
cr_phieu chi giu duoc TRANG THAI HIEN TAI cua 1 cell - moi lan POST lai deu
ghi de len chinh dong do (update_result). Truoc B8, ghi de con lam MAT ly do
CTS tu choi lan truoc; sau B8 thi giu duoc ly do GAN NHAT, nhung van chi 1 cai.
Bang nay ghi THEM 1 dong moi lan POST, khong bao gio ghi de - tra loi duoc
"cell nay da bi tu choi may lan, moi lan vi sao, ai bam" ma cr_phieu khong tra
loi duoc.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CrPhieuLanThu(SQLModel, table=True):
    __tablename__ = "cr_phieu_lan_thu"

    id: int | None = Field(default=None, primary_key=True)

    # ondelete CASCADE - xem ly do day du trong migration b3f7d21ac504:
    # xoa_phieu_use_case dang hard-delete cr_phieu, khong CASCADE thi tinh nang
    # DELETE /phieu/{id} se chet vi vi pham FK
    cr_phieu_id: int = Field(
        sa_column=sa.Column(
            sa.INTEGER, sa.ForeignKey("cr_phieu.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )

    # KHONG server_default=now() - Postgres server co TimeZone GUC = Asia/
    # Ho_Chi_Minh nen now() ghi gio VN vao TIMESTAMPTZ thay vi UTC (C1.4-fix9,
    # ap dung cho MOI cot thoi gian trong project). Luon set qua Python.
    thoi_diem: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    # JOB_AUTO | MANUAL - ai kich hoat lan POST nay. Phan biet duoc "job tu dong
    # thu lai moi ngay" voi "nguoi truc bam tay" la thu can khi truy nguyen: 2
    # tinh huong nay doi hoi cach xu ly khac han nhau.
    nguoi_thuc_hien: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))

    # SUCCESS | FAILED. VARCHAR(30) chu khong phai 20 - bai hoc tu
    # cr_phieu.trang_thai (migration b7f4c2a91d38) phai chay them 1 migration
    # rieng chi vi mot gia tri dai 24 ky tu.
    ket_qua: str = Field(sa_column=sa.Column(sa.VARCHAR(30), nullable=False))

    phieu_id: str | None = Field(default=None, sa_column=sa.Column(sa.VARCHAR(100)))
    error_message: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))

    # CA HAI nullable (khac cr_phieu.request_payload la NOT NULL): co nhung lan
    # hong TRUOC khi kip dung payload, hoac khong nhan duoc response (timeout,
    # dut ket noi). Ep NOT NULL se khien dung nhung lan hong nang nhat lai khong
    # ghi lai duoc - tuc la mat dung du lieu can nhat.
    request_payload: dict | None = Field(default=None, sa_column=sa.Column(JSONB))
    response_body: dict | None = Field(default=None, sa_column=sa.Column(JSONB))
