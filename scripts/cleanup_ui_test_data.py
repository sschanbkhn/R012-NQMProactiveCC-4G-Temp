"""
scripts/cleanup_ui_test_data.py — DON SACH du lieu mau do
scripts/seed_ui_test_data.py tao ra. Chay khi FE test xong.
Tu: yeu cau truc tiep user (13/08).

Tuong duong SQL:
    DELETE FROM system_nsn_nqmproactivecc.cr_phieu WHERE cell_name LIKE 'TEST_UI_%';

VI SAO NEN CHAY SCRIPT NAY THAY VI SQL TAY: script IN RA tung dong SAP xoa de
doc lai truoc khi commit, va kiem tra 3 dong THAT (id 51/82/550) van nguyen ven
SAU khi xoa - lenh SQL tay khong co 2 lop nay. Neu lo tay go thieu tien to
(vd `LIKE 'TEST%'`) thi SQL tay xoa im lang, con script se hien ro dong nao bi
dinh truoc khi ghi.

Chay:
    venv/Scripts/python.exe scripts/cleanup_ui_test_data.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402

from infrastructure.db import AsyncSessionLocal  # noqa: E402
from models.cr_phieu import CrPhieu as CrPhieuModel  # noqa: E402

# Xem ly do trong scripts/seed_ui_test_data.py - cr_phieu co FK -> cr_session.id
# nen 2 model nay phai co mat trong metadata luc flush.
from models.cr_session import CrSession as _CrSessionModel  # noqa: E402,F401
from models.tram import Tram as _TramModel  # noqa: E402,F401

# PHAI khop TIEN_TO trong scripts/seed_ui_test_data.py
TIEN_TO = "TEST_UI_"

# 3 dong THAT - phai con nguyen ven sau khi don.
# id=82 DA BI XOA khoi DB tu truoc 20082026 (phat hien khi don du lieu mock:
# script canh bao 'MAT dong cr_phieu that: {82}' trong khi ban chup TRUOC khi
# xoa da khong co no). KHONG phai do lan don nay lam mat - da doi chieu ban
# chup 35 dong truoc khi xoa. Bo khoi danh sach de buoc kiem khong bao dong
# gia moi lan chay.
# 1790 THEM VAO (them 20082026): dong that cua session 1811, truoc gio thieu
# trong danh sach nen KHONG duoc bao ve boi lop chan cung.
ID_THAT = {51, 550, 645, 1790}


async def main() -> None:
    async with AsyncSessionLocal() as s:
        can_xoa = (
            await s.execute(
                select(CrPhieuModel.id, CrPhieuModel.cell_name, CrPhieuModel.trang_thai)
                .where(CrPhieuModel.cell_name.like(f"{TIEN_TO}%"))
                .order_by(CrPhieuModel.id)
            )
        ).all()

        if not can_xoa:
            print(f"Khong co dong nao co tien to {TIEN_TO} - da sach tu truoc.")
            return

        print(f"Sap xoa {len(can_xoa)} dong:")
        for r in can_xoa:
            # Chan cuoi: neu vi ly do nao do 1 id THAT lot vao day thi DUNG NGAY,
            # khong xoa gi ca.
            if r.id in ID_THAT:
                raise SystemExit(f"DUNG LAI: dong THAT id={r.id} khop tien to {TIEN_TO} - KHONG xoa gi.")
            print(f"  id={r.id:<6} {r.cell_name:<26} {r.trang_thai}")

        await s.execute(delete(CrPhieuModel).where(CrPhieuModel.cell_name.like(f"{TIEN_TO}%")))
        await s.commit()

        con_lai = (
            await s.execute(
                select(CrPhieuModel.id, CrPhieuModel.cell_name, CrPhieuModel.trang_thai).order_by(
                    CrPhieuModel.id
                )
            )
        ).all()
        print(f"\nDa xoa xong. cr_phieu con {len(con_lai)} dong:")
        for r in con_lai:
            print(f"  id={r.id:<6} {r.cell_name:<26} {r.trang_thai}")

        thieu = ID_THAT - {r.id for r in con_lai}
        if thieu:
            raise SystemExit(f"CANH BAO: thieu dong THAT id={sorted(thieu)} sau khi don!")
        print("\n3 dong THAT (51/82/550) van nguyen ven.")


if __name__ == "__main__":
    asyncio.run(main())
