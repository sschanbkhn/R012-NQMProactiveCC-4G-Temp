"""
SQLModel: bang ho_neighbor.
Tu: quyet dinh 06-08/10/2026 (BO CDS, thay bang HO that + Delaunay) - xem
docs/BUSINESS_RULES.md muc "Chon cell CR tu HO neighbor".

VI SAO CO BANG NAY: CDS /cell/neighbors tinh neighbor tu azimuth/do cao NHAP
TAY (hay sai/thieu cap nhat). HO (handover) that tu NetAct la nguon THAT SU
dang tin: UE cua tram dang handover SANG cell nao nhieu nhat thi cell do dang
PHU VUNG that, khong can suy tu thong so hinh hoc. File report HO (~3 trieu
dong/lan export, 1 NetAct) qua lon de doc truc tiep moi lan chay thuat toan -
nap truoc vao bang nay de doc nhanh theo (netact, source_enb). SUA
08/10/2026 lan 4 (yeu cau truc tiep user): nap TOAN BO cap (source, dich) hop
le, KHONG con cat top 20/nguon - de phan tich/hieu chinh/uoc luong vi tri
cell bang SQL truc tiep tren toan bo quan he (xem adapters/netact/
import_ho_neighbor.py).

CHI 1 BAN/NETACT TAI 1 THOI DIEM: import_ho_neighbor.py XOA SACH du lieu CU
CUA NETACT DO roi nap lai TOAN BO (khong phai upsert tung dong) - file export
la snapshot DAY DU 1 lan chay, khong phai incremental.
"""

from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class HoNeighbor(SQLModel, table=True):
    __tablename__ = "ho_neighbor"

    id: int | None = Field(default=None, primary_key=True)

    # ten NetAct instance (vd "NA09") - PHAN BIET du lieu cua tung NetAct khi
    # co nhieu file nap chong nhau (xem adapters/netact/oss_router_env.py ve
    # y nghia "NA09"). KHONG phai FK (NetAct cau hinh trong .env, khong co
    # bang DB rieng - giong oss_instance_id cua cr_session). Chi muc: xem
    # Index('ix_ho_neighbor_netact_source_enb', ...) o __table_args__ duoi -
    # KHONG dat index=True rieng o day (SUA 08/10/2026 lan 4, thay bang 1 chi
    # muc GHEP voi source_enb, khop dung mau truy van cua HoNeighborRepo).
    netact: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))

    # Ngay du lieu THAT trong file (cot PERIOD_START_TIME cua NetAct, vd
    # 28/09/2026) - KHAC last_synced_at/created_at (luc NAP vao DB). Can de
    # biet du lieu HO nay "cu" bao nhieu khi doi chieu voi CR da chay (xem
    # G7 trong scripts/phan_tich_nguong_ho.py - HO va CR co the lech thoi diem).
    ngay_du_lieu: date = Field(sa_column=sa.Column(sa.DATE, nullable=False))

    # source_enb (int, tu LNBTS trong cot DN - SUA 10/10/2026, TRUOC la MRBTS,
    # xem domain/services/dist_name.py::LNBTS_LNCEL_RE) + source_lncel_name
    # (nguyen van "Source LNCEL name", vd "4G-BDH288M11-HNI") - giu CA TEN de
    # nguoi doc khong phai tra nguoc qua tram/cell_infor moi hieu dong du lieu.
    source_enb: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))
    source_lncel_name: str = Field(sa_column=sa.Column(sa.VARCHAR(200), nullable=False))
    # sector = chu so cuoi LNCEL ID nguon (tu DN, %10) - CHI nap dong co ID
    # nguon DUNG 2 chu so (xem adapters/netact/import_ho_neighbor.py va
    # scripts/phan_tich_nguong_ho.py muc 4 - ID 3 chu so la nhom "MBF_",
    # %10 se ra sector SAI nen KHONG duoc nap).
    source_sector: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))

    # target_eci (nguyen goc, de doi chieu/debug) + target_enb/target_lcr (da
    # giai ma san: enb = eci//256, lcr = eci%256 - cong thuc da KIEM CHUNG
    # bang du lieu that, xem scripts/spike_ho_neighbor.py Buoc 2).
    target_eci: int = Field(sa_column=sa.Column(sa.BIGINT, nullable=False))
    # Chi muc rieng cho target_enb: xem Index('ix_ho_neighbor_target_enb')
    # o __table_args__ duoi (KHONG dat index=True o day de tranh tao 2 chi
    # muc trung nhau tren cung 1 cot).
    target_enb: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))
    target_lcr: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))

    # ho_attempt ("Inter eNB HO prep att neigh") - so lan CHUAN BI handover,
    # dung xep hang/tinh % (xem domain/services/ho_cell_selector.py). CHI nap
    # dong attempt > 0 (xem import script).
    ho_attempt: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))
    # ho_sr ("Adj Inter eNB HO SR") - % THANH CONG, NULLABLE (file co the de
    # trong khi attempt > 0 o mot so dong hiem - KHONG ep ve 0, se lam sai
    # luat loc SR>=95%).
    ho_sr: float | None = Field(default=None, sa_column=sa.Column(sa.NUMERIC(5, 2)))

    # KHONG server_default=now() - pattern C1.4-fix9 (xem models/tram.py).
    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        # Chong nap trung trong CUNG 1 lan import (vd chay --dry-run roi chay
        # that 2 lan lien tiep ma quen xoa) - KHONG phai luat nghiep vu, chi
        # la luoi an toan DB. 1 cap (source_enb, source_sector, target_enb,
        # target_lcr) chi co nghia khi CUNG netact (2 NetAct khac nhau co the
        # co eNB trung ID - khong thuc te trong pham vi 1 vendor/vung, nhung
        # KHONG LOAI TRU ve mat du lieu nen van dua netact vao khoa).
        sa.UniqueConstraint(
            "netact", "source_enb", "source_sector", "target_enb", "target_lcr",
            name="uq_ho_neighbor_netact_source_target",
        ),
        # Chi muc GHEP (netact, source_enb) - khop DUNG mau truy van duy nhat
        # cua HoNeighborRepo.get_by_source_enb() (luon loc CA HAI cot cung
        # luc). THAY cho 2 chi muc rieng le o ban truoc (SUA 08/10/2026 lan 4).
        sa.Index("ix_ho_neighbor_netact_source_enb", "netact", "source_enb"),
        sa.Index("ix_ho_neighbor_target_enb", "target_enb"),
    )
