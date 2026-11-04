"""
scripts/cleanup_mock_process_data.py — DON SACH du lieu mau do
scripts/seed_mock_process_data.py tao ra. Tu: yeu cau truc tiep user (14/08).

3 LOP CHAN (giong scripts/cleanup_ui_test_data.py da co):
  1. IN TUNG DONG sap xoa truoc khi commit - doc lai duoc truoc khi mat.
  2. CHAN CUNG neu co id THAT lot vao dien xoa -> raise, khong xoa gi.
  3. KIEM LAI SAU khi xoa: 4 dong cr_phieu THAT (51/82/550/645) con nguyen,
     cell_infor van 27763.

DIEU KIEN XOA:
    tram              : tram_id LIKE 'MOCK%'
    cr_session        : tram_id LIKE 'MOCK%'
    qos_snapshot      : theo cr_session_id cua cac session tren
    qoe_snapshot      : theo cr_session_id cua cac session tren
    cr_phieu          : theo cr_session_id cua cac session tren
    cr_affected_cells : theo cr_session_id cua cac session tren
    cr_log            : theo cr_session_id cua cac session tren
    cell_params       : theo cr_session_id cua cac session tren
    alert_log         : theo cr_session_id cua cac session tren
    audit_log         : SET NULL cr_session_id (KHONG xoa dong)
    rollback_of_id    : SET NULL o cac cr_session KHAC dang tro toi
    job_run_log       : chi_tiet->>'_mock' = 'true'
                        (bang nay KHONG co cot nao chua chuoi MOCK, nen phai
                         danh dau bang khoa trong JSONB)

THU TU XOA (nguoc chieu FK, KHONG duoc doi):
    qos_snapshot -> qoe_snapshot -> cr_phieu -> cr_log -> cr_affected_cells ->
    cell_params -> alert_log -> audit_log(SET NULL) -> rollback_of_id(SET NULL)
    -> cr_session -> tram -> job_run_log

qos_snapshot/qoe_snapshot/cell_params/alert_log/audit_log/rollback_of_id them
20082026. Do bang pg_constraint tren DB THAT: co 9 FK tro toi cr_session, TAT
CA ON DELETE NO ACTION (Postgres KHONG tu don) nen phai xoa TRUOC
cr_session - thieu 1 bang la FK violation va script chet GIUA CHUNG, de lai
mock da mat mot nua dong con.

Hien 6 bang nay dang 0 dong cho session mock nen chua no, NHUNG:
  - tu 20/08 job xuat phieu ghi snapshot PER-CELL: session mock nao chay qua
    job se co ~15 ngay x so cell dong;
  - alert_use_case CO ghi alert_log khi danh gia FAIL - se no NGAY khi co
    session mock nao FAIL.

audit_log va rollback_of_id dung SET NULL chu KHONG xoa:
  - audit_log la vet KIEM TOAN "ai lam gi luc nao", phai song lau hon doi
    tuong bi thao tac - xoa doi tuong ma xoa luon bang chung ai da xoa la sai.
    Cot cr_session_id o bang nay NULLABLE nen lam duoc.
  - rollback_of_id nam tren cr_session KHAC (self-FK). Xoa dong do la xoa mot
    session khong thuoc dien don. Dung loai bug da gap that o teardown test_tram trong
tests/integration/conftest.py (thieu 2 bang snapshot -> dong tram sot lai ->
lan chay sau loi duplicate key).

Chay:
    venv/Scripts/python.exe scripts/cleanup_mock_process_data.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from infrastructure.db import AsyncSessionLocal  # noqa: E402

S = "system_nsn_nqmproactivecc"
TIEN_TO_TRAM = "MOCK"

# 4 dong cr_phieu THAT - phai con nguyen sau khi don.
# id=82 DA BI XOA khoi DB tu truoc 20082026 (phat hien khi don du lieu mock:
# script canh bao 'MAT dong cr_phieu that: {82}' trong khi ban chup TRUOC khi
# xoa da khong co no). KHONG phai do lan don nay lam mat - da doi chieu ban
# chup 35 dong truoc khi xoa. Bo khoi danh sach de buoc kiem khong bao dong
# gia moi lan chay.
# 1790 THEM VAO (them 20082026): dong that cua session 1811, truoc gio thieu
# trong danh sach nen KHONG duoc bao ve boi lop chan cung.
CR_PHIEU_THAT = (51, 550, 645, 1790)
CELL_INFOR_MONG_DOI = 27763

_SESSION_MOCK = f"(SELECT id FROM {S}.cr_session WHERE tram_id LIKE '{TIEN_TO_TRAM}%')"


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # --- LOP 1: in tung dong sap xoa ---
        print("=== SAP XOA ===")
        r = await s.execute(text(
            f"SELECT id, tram_id, status, executed_at FROM {S}.cr_session "
            f"WHERE tram_id LIKE '{TIEN_TO_TRAM}%' ORDER BY tram_id DESC"))
        sessions = r.mappings().all()
        if not sessions:
            print(f"  Khong co session nao co tram_id LIKE '{TIEN_TO_TRAM}%'")
        for m in sessions:
            print(f"  cr_session  id={m['id']:<6} {m['tram_id']:<9} {m['status']}")

        r = await s.execute(text(
            f"SELECT id, cr_session_id, cell_name, trang_thai FROM {S}.cr_phieu "
            f"WHERE cr_session_id IN {_SESSION_MOCK} ORDER BY id"))
        phieu = r.mappings().all()
        for m in phieu:
            print(f"  cr_phieu    id={m['id']:<6} sess={m['cr_session_id']:<6} "
                  f"{m['cell_name']:<22} {m['trang_thai']}")

        for bang in ("qos_snapshot", "qoe_snapshot", "cr_affected_cells", "cr_log",
                     "cell_params", "alert_log", "audit_log"):
            r = await s.execute(text(
                f"SELECT count(*) FROM {S}.{bang} WHERE cr_session_id IN {_SESSION_MOCK}"))
            print(f"  {bang:<18} {r.scalar_one()} dong")

        r = await s.execute(text(
            f"SELECT id, started_at, trang_thai FROM {S}.job_run_log "
            "WHERE chi_tiet->>'_mock' = 'true' ORDER BY id"))
        job_runs = r.mappings().all()
        for m in job_runs:
            print(f"  job_run_log id={m['id']:<6} {m['started_at']} {m['trang_thai']}")

        r = await s.execute(text(
            f"SELECT count(*) FROM {S}.tram WHERE tram_id LIKE '{TIEN_TO_TRAM}%'"))
        print(f"  tram               {r.scalar_one()} dong")

        if not sessions and not job_runs:
            print("\nKhong co gi de xoa - da sach tu truoc.")
            return

        # --- LOP 2: chan cung neu id THAT lot vao dien xoa ---
        id_phieu_xoa = {m["id"] for m in phieu}
        cham_phai_that = id_phieu_xoa & set(CR_PHIEU_THAT)
        if cham_phai_that:
            raise SystemExit(
                f"DUNG LAI: dien xoa co chua dong cr_phieu THAT id={sorted(cham_phai_that)} "
                "- KHONG xoa gi ca."
            )
        # Dong TEST_UI_ (tu dot seed FE) KHONG duoc dinh toi - khac tien to,
        # khac script don. Kiem cho chac.
        r = await s.execute(text(
            f"SELECT count(*) FROM {S}.cr_phieu WHERE cr_session_id IN {_SESSION_MOCK} "
            "AND cell_name LIKE 'TEST_UI_%'"))
        if r.scalar_one():
            raise SystemExit("DUNG LAI: dien xoa cham vao dong TEST_UI_ - KHONG xoa gi ca.")

        # --- XOA theo dung thu tu FK ---
        print("\n=== DANG XOA ===")
        for nhan, sql in [
            # 2 bang snapshot phai di TRUOC cr_phieu trong chuoi nay - thuc te
            # thu tu giua cac bang CON khong quan trong (chung khong tro vao
            # nhau), cai BAT BUOC la tat ca deu truoc cr_session. Dat len dau
            # cho khop thu tu ghi trong docstring.
            ("qos_snapshot", f"DELETE FROM {S}.qos_snapshot WHERE cr_session_id IN {_SESSION_MOCK}"),
            ("qoe_snapshot", f"DELETE FROM {S}.qoe_snapshot WHERE cr_session_id IN {_SESSION_MOCK}"),
            ("cr_phieu", f"DELETE FROM {S}.cr_phieu WHERE cr_session_id IN {_SESSION_MOCK}"),
            ("cr_log", f"DELETE FROM {S}.cr_log WHERE cr_session_id IN {_SESSION_MOCK}"),
            ("cr_affected_cells",
             f"DELETE FROM {S}.cr_affected_cells WHERE cr_session_id IN {_SESSION_MOCK}"),
            # cell_params: xoa theo cr_session_id (KHONG theo tram_id). Dong
            # cell_params dung chung khoa UNIQUE (tram_id, cell_name) va bi
            # upsert de qua nhieu session - loc theo cr_session_id chi dinh
            # dung dong ma session mock ghi lan cuoi.
            ("cell_params",
             f"DELETE FROM {S}.cell_params WHERE cr_session_id IN {_SESSION_MOCK}"),
            # alert_log: FK NOT NULL -> khong co lua chon nao khac ngoai XOA.
            ("alert_log", f"DELETE FROM {S}.alert_log WHERE cr_session_id IN {_SESSION_MOCK}"),
            # 2 buoc SET NULL (khong phai DELETE) - xem ly do o docstring.
            ("audit_log SET NULL",
             f"UPDATE {S}.audit_log SET cr_session_id = NULL "
             f"WHERE cr_session_id IN {_SESSION_MOCK}"),
            ("rollback_of_id SET NULL",
             f"UPDATE {S}.cr_session SET rollback_of_id = NULL "
             f"WHERE rollback_of_id IN {_SESSION_MOCK}"),
            ("cr_session", f"DELETE FROM {S}.cr_session WHERE tram_id LIKE '{TIEN_TO_TRAM}%'"),
            ("tram", f"DELETE FROM {S}.tram WHERE tram_id LIKE '{TIEN_TO_TRAM}%'"),
            ("job_run_log", f"DELETE FROM {S}.job_run_log WHERE chi_tiet->>'_mock' = 'true'"),
        ]:
            res = await s.execute(text(sql))
            print(f"  {nhan:<18} xoa {res.rowcount} dong")
        await s.commit()

        # --- LOP 3: kiem lai sau khi xoa ---
        print("\n=== KIEM LAI SAU KHI XOA ===")
        loi = []
        r = await s.execute(text(
            f"SELECT id FROM {S}.cr_phieu WHERE id IN {CR_PHIEU_THAT} ORDER BY id"))
        con = [x[0] for x in r.all()]
        print(f"  cr_phieu THAT con: {con}")
        if con != sorted(CR_PHIEU_THAT):
            loi.append(f"MAT dong cr_phieu that: {set(CR_PHIEU_THAT) - set(con)}")

        r = await s.execute(text(f"SELECT count(*) FROM {S}.cell_infor"))
        n = r.scalar_one()
        print(f"  cell_infor = {n}")
        if n != CELL_INFOR_MONG_DOI:
            loi.append(f"cell_infor = {n}, mong doi {CELL_INFOR_MONG_DOI}")

        for bang, dk in [("tram", f"tram_id LIKE '{TIEN_TO_TRAM}%'"),
                         ("cr_session", f"tram_id LIKE '{TIEN_TO_TRAM}%'"),
                         ("job_run_log", "chi_tiet->>'_mock' = 'true'")]:
            r = await s.execute(text(f"SELECT count(*) FROM {S}.{bang} WHERE {dk}"))
            n = r.scalar_one()
            print(f"  {bang} con sot du lieu mau: {n}")
            if n:
                loi.append(f"{bang} con {n} dong mau")

        if loi:
            raise SystemExit("CANH BAO:\n  " + "\n  ".join(loi))
        print("\nDa don sach. Du lieu that nguyen ven.")


if __name__ == "__main__":
    asyncio.run(main())
