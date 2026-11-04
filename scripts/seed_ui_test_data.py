"""
scripts/seed_ui_test_data.py — tao 3 dong cr_phieu MAU cho FE test giao dien.
Tu: yeu cau truc tiep user (13/08).

VI SAO CAN: sau V4, cr_phieu that chi co 3 dong (2 SUCCESS + 1 FAILED) va
KHONG dong nao mang 2 trang thai moi, nen FE khong kiem chung duoc:
  - nut [Xuat] tren dong KHONG_XUAT_* (bam vao phai cap nhat DUNG dong do,
    khong tao dong moi - uq_cr_phieu_session_cell da chan trung)
  - 2 gia tri loc moi cua GET /phieu
  - cot so_lan_thu (phan biet "chua thu lan nao" vs "da het luot thu")

KHONG POST gi len CTS/TTS - script nay CHI ghi DB.

AN TOAN:
  - Moi cell_name deu co tien to TEST_UI_ -> don sach bang 1 lenh duy nhat,
    xem scripts/cleanup_ui_test_data.py.
  - CHI insert. Tuyet doi KHONG dung toi 3 dong THAT (id 51/82/550): script
    kiem tra lai chung TRUOC va SAU, bao loi neu lech.
  - Chay lai duoc nhieu lan (idempotent): dong TEST_UI_ cu bi xoa truoc khi
    insert lai, nen khong bao gio dung uq_cr_phieu_session_cell.

Chay:
    venv/Scripts/python.exe scripts/seed_ui_test_data.py

=== CANH BAO (20082026) - CHI DUNG DE TEST TAY TREN FE ===
KHONG dung script nay cho test tu dong. Test integration da chuyen sang TU TAO
du lieu trong fixture (tests/integration/fixtures_tien_trinh.py).

VI SAO: du lieu o day dung NGAY CO DINH, trong khi scheduler THAT van chay hang
ngay tren cung DB. Job xuat phieu quet theo dieu kien "ngay CR == hom nay -
XUAT_PHIEU_AFTER_DAYS" nen moi session seed deu SE bi quet vao mot ngay nao do
va troi tu buoc 2 sang buoc 4. Da xay ra that: MOCK996 (executed_at 11/08) bi
scheduler quet ngay 19/08, job_run_log id=735.

Hau qua neu van dung cho test tu dong: test phai them guard skip, ma mot test
luon skip la mot test KHONG KIEM GI CA nhung van hien "xanh".
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402

from infrastructure.db import AsyncSessionLocal  # noqa: E402
from models.cr_phieu import CrPhieu as CrPhieuModel  # noqa: E402

# BAT BUOC import du CA 2 model, du script chi ghi cr_phieu: cr_phieu co
# ForeignKey -> cr_session.id, SQLAlchemy phai thay bang cr_session trong
# metadata moi resolve duoc FK luc flush (NoReferencedTableError neu thieu).
# Trong app that khong gap loi nay vi infrastructure/dependencies.py da import
# san toan bo model.
from models.cr_session import CrSession as _CrSessionModel  # noqa: E402,F401
from models.tram import Tram as _TramModel  # noqa: E402,F401

# Session THAT da co trong DB (tram 112721, CR 22/07/2026) - dung lai thay vi
# tao session gia, de dong cr_phieu co FK hop le va FE mo duoc man hinh session.
CR_SESSION_ID = 553

# Tien to BAT BUOC - la thu duy nhat phan biet du lieu mau voi du lieu that
# khi don rac. Doi tien to o day thi PHAI doi ca cleanup_ui_test_data.py.
TIEN_TO = "TEST_UI_"

# 3 dong THAT trong bang - script phai de nguyen ven.
# id=82 DA BI XOA khoi DB tu truoc 20082026 (phat hien khi don du lieu mock:
# script canh bao 'MAT dong cr_phieu that: {82}' trong khi ban chup TRUOC khi
# xoa da khong co no). KHONG phai do lan don nay lam mat - da doi chieu ban
# chup 35 dong truoc khi xoa. Bo khoi danh sach de buoc kiem khong bao dong
# gia moi lan chay.
# 1790 THEM VAO (them 20082026): dong that cua session 1811, truoc gio thieu
# trong danh sach nen KHONG duoc bao ve boi lop chan cung.
ID_THAT = {51, 550, 645, 1790}


def _payload(cell_name: str) -> dict:
    # Toi thieu hop le (KHONG can du 28 field - day la du lieu mau cho UI, khong
    # phai thu se gui len CTS). request_payload la NOT NULL nen van phai co gi do.
    return {
        "_ghi_chu": "DU LIEU MAU cho FE test UI - KHONG phai payload da gui CTS",
        "TenCell": cell_name,
        "Nam": 2026,
        "Thang": 8,
    }


_DONG_MAU = [
    # (cell_name, trang_thai, so_lan_thu, error_message)
    (
        f"{TIEN_TO}001",
        "KHONG_XUAT_VUOT_GIOI_HAN",
        0,
        "Ngoai top 10 cell te nhat cua session - can xuat tay",
    ),
    (
        f"{TIEN_TO}003",
        "KHONG_XUAT_HET_LUOT_THU",
        3,
        "Bad Cell TEST_UI_003 dang xu ly cua thang 202608",
    ),
    (f"{TIEN_TO}002", "PENDING", 0, None),
]


async def main() -> None:
    async with AsyncSessionLocal() as s:
        truoc = await _chup_dong_that(s)

        # Xoa dong TEST_UI_ cu (neu chay lai lan 2) - KHONG cham dong that vi
        # dieu kien loc theo tien to.
        da_xoa = await s.execute(
            delete(CrPhieuModel).where(CrPhieuModel.cell_name.like(f"{TIEN_TO}%"))
        )
        if da_xoa.rowcount:
            print(f"Da xoa {da_xoa.rowcount} dong {TIEN_TO}% cu truoc khi tao lai")

        for cell_name, trang_thai, so_lan_thu, error_message in _DONG_MAU:
            s.add(
                CrPhieuModel(
                    cr_session_id=CR_SESSION_ID,
                    cell_name=cell_name,
                    trang_thai=trang_thai,
                    request_payload=_payload(cell_name),
                    response_body=None,
                    phieu_id=None,  # chua co phieu that tren TTS
                    error_message=error_message,
                    so_lan_thu=so_lan_thu,
                    # C1.4-fix9 - set qua Python UTC, KHONG server_default=now()
                    created_at=datetime.now(timezone.utc),
                )
            )
        await s.commit()

        sau = await _chup_dong_that(s)
        if truoc != sau:
            raise SystemExit(f"DUNG LAI: 3 dong THAT da bi thay doi!\n  truoc={truoc}\n  sau={sau}")

        print(f"\nDa tao {len(_DONG_MAU)} dong mau. Toan bo bang cr_phieu:")
        rows = (
            await s.execute(
                select(
                    CrPhieuModel.id,
                    CrPhieuModel.cell_name,
                    CrPhieuModel.trang_thai,
                    CrPhieuModel.so_lan_thu,
                ).order_by(CrPhieuModel.id)
            )
        ).all()
        print(f"  {'id':<6} {'cell_name':<26} {'trang_thai':<26} so_lan_thu")
        for r in rows:
            danh_dau = "" if r.id in ID_THAT else "  <- MAU"
            print(f"  {r.id:<6} {r.cell_name:<26} {r.trang_thai:<26} {r.so_lan_thu}{danh_dau}")


async def _chup_dong_that(s) -> list[tuple]:
    # Chup NGUYEN noi dung 3 dong that de doi chieu truoc/sau - khong chi dem so
    # luong (dem khong bat duoc truong hop bi ghi de).
    rows = (
        await s.execute(
            select(
                CrPhieuModel.id,
                CrPhieuModel.cell_name,
                CrPhieuModel.trang_thai,
                CrPhieuModel.phieu_id,
                CrPhieuModel.so_lan_thu,
                CrPhieuModel.error_message,
            )
            .where(CrPhieuModel.id.in_(ID_THAT))
            .order_by(CrPhieuModel.id)
        )
    ).all()
    return [tuple(r) for r in rows]


if __name__ == "__main__":
    asyncio.run(main())
