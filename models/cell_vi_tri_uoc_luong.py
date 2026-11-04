"""
SQLModel: bang cell_vi_tri_uoc_luong.
Tu: BUOC 4c (10/10/2026, yeu cau truc tiep user) - uoc luong vi tri CELL cua
tram TOA_DO_DUNG_CHUNG (CRAN) qua toa do cac tram DICH TIN_CAY ma cell do HO
sang - xem domain/services/cran_vi_tri_estimator.py.

VI SAO CO BANG NAY: tram TOA_DO_DUNG_CHUNG (xem domain/services/ho_delaunay.py::
phan_loai_toa_do()) co toa do RIMS KHONG dung tin cay (baseband/CRAN hub, xem
scripts/kiem_gia_thuyet_cran.py) - khong co toa do nao de VE LEN BAN DO. Bang
nay luu VI TRI UOC LUONG (THAM KHAO, KHONG PHAI toa do that) de BAN DO van co
gi de hien thi - CHI DUNG DE HIEN THI, TUYET DOI KHONG dua vao L1/L2/vung Z
cua domain/services/ho_delaunay.py hay ho_cell_selector.py (se tao VONG LAP:
HO -> vi tri uoc luong -> dung vi tri do de kiem lai HO, mat tinh doc lap cua
2 nguon du lieu).

CHI 1 BAN GHI/(netact, enb, lcr) TAI 1 THOI DIEM: tinh lai TOAN BO moi lan
nap ho_neighbor (xem adapters/netact/import_ho_neighbor.py), XOA + GHI LAI
theo netact giong ho_neighbor (khong phai upsert tung dong).

"lcr" o day KHONG PHAI LNCEL local id goc (ho_neighbor.source_sector da GOP
nhieu LNCEL cung sector thanh 1 nhom tu SUA 09/10/2026 - khong con giu duoc
LNCEL rieng cua tung cell nguon) - DUNG source_sector (0-9) lam "lcr" o day,
dai dien cho CA NHOM cell cung sector cua 1 tram. Chap nhan do PHAN GIAI nay
la MUC CHI TIET CAO NHAT con lai sau buoc gop (xem BUSINESS_RULES.md).
"""

from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class CellViTriUocLuong(SQLModel, table=True):
    __tablename__ = "cell_vi_tri_uoc_luong"

    id: int | None = Field(default=None, primary_key=True)

    netact: str = Field(sa_column=sa.Column(sa.VARCHAR(20), nullable=False))
    # enb = LNBTS cua tram NGUON (TOA_DO_DUNG_CHUNG) - CUNG quy uoc LNBTS voi
    # ho_neighbor.source_enb (SUA 10/10/2026, xem domain/services/dist_name.py).
    enb: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))
    # lcr = source_sector (0-9) - xem WHY dau file, KHONG PHAI LNCEL local id.
    lcr: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))

    lat: float = Field(sa_column=sa.Column(sa.NUMERIC(10, 6), nullable=False))
    lon: float = Field(sa_column=sa.Column(sa.NUMERIC(10, 6), nullable=False))

    # % HO (tren tong HO cua cell nay) roi vao cac tram dich TIN_CAY DA dung
    # de tinh trung tam co trong so - PHAI >= NGUONG_TY_LE_HO_TIN_CAY (0.5,
    # domain/services/cran_vi_tri_estimator.py) moi co ban ghi (duoi nguong
    # thi KHONG ghi gi - "khong xac dinh", khong luu 0%).
    ty_le_ho_tin_cay: float = Field(sa_column=sa.Column(sa.NUMERIC(5, 4), nullable=False))
    # So tram DICH TIN_CAY PHAN BIET da gop vao trung tam co trong so - PHAI
    # >= NGUONG_SO_TRAM_DICH_TOI_THIEU (3) moi co ban ghi.
    so_tram_dich: int = Field(sa_column=sa.Column(sa.INTEGER, nullable=False))

    # Ngay du lieu THAT cua lan nap ho_neighbor da dung de tinh (PERIOD_START_TIME,
    # CUNG gia tri voi ho_neighbor.ngay_du_lieu cua lan nap do).
    ngay_du_lieu: date = Field(sa_column=sa.Column(sa.DATE, nullable=False))

    created_at: datetime = Field(
        sa_column=sa.Column(
            sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
        )
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "netact", "enb", "lcr",
            name="uq_cell_vi_tri_uoc_luong_netact_enb_lcr",
        ),
    )
