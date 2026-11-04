"""
scripts/seed_mock_process_data.py — tao 12 session MOCK cho man hinh THEO DOI
TIEN TRINH (FE test giao dien). Tu: yeu cau truc tiep user (14/08).

KHONG POST gi len CTS/TTS - script nay CHI ghi DB.

=========================================================================
!!! CHAN CUNG AN TOAN - DOC TRUOC KHI SUA DU LIEU MAU !!!
=========================================================================
SCHEDULER_ENABLED=true tren server 10.155.43.196. Moi 8h sang job quet:
    ngay_moc = hom_nay(GMT+7) - XUAT_PHIEU_AFTER_DAYS
    dieu kien: status IN (DONE, EVALUATED, EVAL_PENDING)
               VA executed_at::date(GMT+7) == ngay_moc
Session mock nao THOA CA 3 dieu duoi day se bi job quet va POST PHIEU THAT len
CTS cho cell KHONG TON TAI -> rac tren he thong that, phai nho CTS xoa tay:
    (1) executed_at >= 2026-08-06  (tuc con nam trong tuong lai cua vong quet)
    (2) co cr_affected_cells > 0   (co cell de danh gia -> co the xuat phieu)
    (3) status IN whitelist
_kiem_tra_an_toan() chay TRUOC MOI LENH INSERT va RAISE neu co dong nao thoa
ca 3 - khong insert dong nao. Sua du lieu mau thi PHAI chay lai script, neu
vi pham no se chan.

Vi sao MOCK996 CO Y de 0 cell: no la case "dang cho KPI" nen executed_at phai
gan (11/08) -> se bi job quet ngay 19/08. De 0 cell thi job quet xong khong co
ung vien nao -> ket luan KHONG_CAN_XUAT, KHONG goi CTS lan nao.
Vi sao MOCK989 (executed_at = hom nay) an toan: status RUNNING NGOAI whitelist.

Chay:
    venv/Scripts/python.exe scripts/seed_mock_process_data.py
Don:
    venv/Scripts/python.exe scripts/cleanup_mock_process_data.py

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
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from infrastructure.db import AsyncSessionLocal  # noqa: E402

S = "system_nsn_nqmproactivecc"

# Tien to BAT BUOC - la thu duy nhat phan biet du lieu mau voi du lieu that khi
# don rac. Doi o day thi PHAI doi ca cleanup_mock_process_data.py.
TIEN_TO_TRAM = "MOCK"

GMT7 = timezone(timedelta(hours=7))

# Nguong (1) cua chan an toan - xem docstring dau file.
NGAY_NGUY_HIEM = date(2026, 8, 6)
WHITELIST = ("DONE", "EVALUATED", "EVAL_PENDING")

# 4 dong cr_phieu THAT - script tuyet doi khong duoc cham vao.
# id=82 DA BI XOA khoi DB tu truoc 20082026 (phat hien khi don du lieu mock:
# script canh bao 'MAT dong cr_phieu that: {82}' trong khi ban chup TRUOC khi
# xoa da khong co no). KHONG phai do lan don nay lam mat - da doi chieu ban
# chup 35 dong truoc khi xoa. Bo khoi danh sach de buoc kiem khong bao dong
# gia moi lan chay.
# 1790 THEM VAO (them 20082026): dong that cua session 1811, truoc gio thieu
# trong danh sach nen KHONG duoc bao ve boi lop chan cung.
CR_PHIEU_THAT = (51, 550, 645, 1790)

# Ten buoc CR lay DUNG tu bang cr_log that (khong bia ten moi) - de Timeline
# tren FE hien y het session that.
_CAC_BUOC = [
    (1, "Validate input", 5), (2, "Query tram + tao session", 10),
    (3, "Goi CDS API /cell/neighbors", 18), (4, "Filter cell", 25),
    (5, "Band priority filter", 30), (6, "Assign priority", 35),
    (7, "Lay rsboost_current", 42), (8, "Tinh rsboost_new", 48),
    (9, "Lay qrxlevmin_current", 52), (10, "Tinh qrxlevmin_new", 56),
    (11, "Luu cell_params", 60), (12, "Build XML", 65),
    (13, "SSH: Upload+Import+Provision", 70), (16, "Parse ket qua SSH + Verify", 90),
    (17, "Cap nhat cr_session Status", 95), (18, "Snapshot QoS baseline", 100),
]

# Hau to cell theo mau 4G-LDG{so}M{huong}{index}-HNI
_HAU_TO = ["11", "12", "13", "21", "22", "23", "31", "32", "33",
           "41", "42", "43", "51", "52", "53"]


def _vn(nam, thang, ngay, gio=0, phut=0, giay=0) -> datetime:
    # Tat ca moc thoi gian trong dac ta la GIO VN (+07). Tao aware datetime roi
    # de asyncpg tu quy ve UTC khi ghi TIMESTAMPTZ - KHONG tu tru 7 tieng bang
    # tay (de sai, va da co bug loai nay o C1.4-fix8).
    # giay: can cho job_run_log (vd 08:00:47) de demo thoi gian chay khac nhau.
    return datetime(nam, thang, ngay, gio, phut, giay, tzinfo=GMT7)


def _cells(so_tram: str, n: int) -> list[str]:
    return [f"4G-LDG{so_tram}M{h}-HNI" for h in _HAU_TO[:n]]


# === 12 SESSION MAU ===
# do_te cua MOCK998 giam dan 0.9 -> 0.2: bang cr_affected_cells KHONG CO cot
# do_te (do te duoc tinh runtime tu QoS CTS, khong luu DB) nen gia tri nay nam
# trong job_run_log.chi_tiet - dung cho de FE demo "sap xep te nhat truoc".
MOCK_SESSIONS = [
    {
        "tram": "MOCK999", "ten": "4G-LDG999M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 8, 1, 9, 15),
        "plan_name": "R012_NQMProactiveCC_MOCK999_20260801_091500",
        "xuat_phieu_at": _vn(2026, 8, 9, 8, 2), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": ["4G-LDG999M11-HNI", "4G-LDG999M12-HNI", "4G-LDG999M13-HNI",
                  "4G-LDG999M31-HNI", "4G-LDG999M32-HNI", "4G-LDG999M51-HNI"],
        "phieu": [("4G-LDG999M11-HNI", "SUCCESS", "MOCK-90001", 1, None),
                  ("4G-LDG999M12-HNI", "SUCCESS", "MOCK-90002", 1, None),
                  ("4G-LDG999M13-HNI", "SUCCESS", "MOCK-90003", 1, None),
                  ("4G-LDG999M31-HNI", "SUCCESS", "MOCK-90004", 1, None)],
        "log": "day_du", "ghi_chu": "XONG DAY DU",
    },
    {
        "tram": "MOCK998", "ten": "4G-LDG998M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 7, 28, 14, 30),
        "plan_name": "R012_NQMProactiveCC_MOCK998_20260728_143000",
        "xuat_phieu_at": _vn(2026, 8, 5, 8, 3), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": _cells("998", 14),
        "phieu": [(c, "SUCCESS", f"MOCK-900{11 + i}", 1, None)
                  for i, c in enumerate(_cells("998", 14)[:10])]
                 + [(c, "KHONG_XUAT_VUOT_GIOI_HAN", None, 0,
                     "Ngoai top 10 cell te nhat cua session - can xuat tay")
                    for c in _cells("998", 14)[10:14]],
        "log": "day_du", "ghi_chu": "CON CELL CHO XUAT TAY",
    },
    {
        "tram": "MOCK997", "ten": "4G-LDG997M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 7, 25, 10, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK997_20260725_100000",
        "xuat_phieu_at": None, "xuat_phieu_ket_qua": None,
        "cells": _cells("997", 8), "phieu": [],
        "log": "day_du", "ghi_chu": "QUA HAN - job lo ngay 07/08, mat vinh vien",
    },
    {
        "tram": "MOCK996", "ten": "4G-LDG996M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 8, 11, 16, 20),
        "plan_name": "R012_NQMProactiveCC_MOCK996_20260811_162000",
        "xuat_phieu_at": None, "xuat_phieu_ket_qua": None,
        # 0 CELL LA BAT BUOC - xem docstring dau file (chan job quet ngay 19/08)
        "cells": [], "phieu": [],
        "log": "day_du", "ghi_chu": "DANG CHO KPI",
    },
    {
        "tram": "MOCK995", "ten": "4G-LDG995M-HNI", "status": "FAILED",
        "executed_at": None, "created_at": _vn(2026, 8, 12, 11, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK995_20260812_110000",
        "xuat_phieu_at": None, "xuat_phieu_ket_qua": None,
        "cells": [], "phieu": [],
        "log": "loi_ssh", "ghi_chu": "CR LOI",
    },
    {
        "tram": "MOCK994", "ten": "4G-LDG994M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 8, 3, 8, 45),
        "plan_name": "R012_NQMProactiveCC_MOCK994_20260803_084500",
        "xuat_phieu_at": _vn(2026, 8, 11, 8, 1), "xuat_phieu_ket_qua": "KHONG_CAN_XUAT",
        "cells": _cells("994", 5), "phieu": [],
        "log": "day_du", "ghi_chu": "TAT CA CELL DAT - case CHINH cua 2 cot moi",
    },
    {
        "tram": "MOCK993", "ten": "4G-LDG993M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 7, 30, 13, 10),
        "plan_name": "R012_NQMProactiveCC_MOCK993_20260730_131000",
        "xuat_phieu_at": _vn(2026, 8, 7, 8, 2), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": _cells("993", 7),
        "phieu": [("4G-LDG993M11-HNI", "SUCCESS", "MOCK-90031", 1, None),
                  ("4G-LDG993M12-HNI", "SUCCESS", "MOCK-90032", 1, None),
                  ("4G-LDG993M13-HNI", "SUCCESS", "MOCK-90033", 1, None),
                  ("4G-LDG993M31-HNI", "FAILED", None, 1,
                   "Bad Cell 4G-LDG993M31-HNI dang xu ly cua thang 202607"),
                  ("4G-LDG993M32-HNI", "FAILED", None, 1,
                   "Bad Cell 4G-LDG993M31-HNI dang xu ly cua thang 202607")],
        "log": "day_du", "ghi_chu": "PHIEU LOI, CON THU LAI DUOC",
    },
    {
        "tram": "MOCK992", "ten": "4G-LDG992M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 7, 27, 15, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK992_20260727_150000",
        "xuat_phieu_at": _vn(2026, 8, 4, 8, 3), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": _cells("992", 6),
        "phieu": [("4G-LDG992M11-HNI", "SUCCESS", "MOCK-90041", 1, None),
                  ("4G-LDG992M12-HNI", "SUCCESS", "MOCK-90042", 1, None),
                  ("4G-LDG992M13-HNI", "KHONG_XUAT_HET_LUOT_THU", None, 3,
                   "Da thu 3 lan that bai - CTS tu choi")],
        "log": "day_du", "ghi_chu": "HET LUOT THU",
    },
    {
        "tram": "MOCK991", "ten": "4G-LDG991M-HNI", "status": "EVALUATED",
        "executed_at": _vn(2026, 8, 2, 10, 30), "evaluated_at": _vn(2026, 8, 12, 9, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK991_20260802_103000",
        "xuat_phieu_at": _vn(2026, 8, 10, 8, 1), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": _cells("991", 5),
        "phieu": [("4G-LDG991M11-HNI", "SUCCESS", "MOCK-90051", 1, None),
                  ("4G-LDG991M12-HNI", "SUCCESS", "MOCK-90052", 1, None),
                  ("4G-LDG991M13-HNI", "SUCCESS", "MOCK-90053", 1, None)],
        "log": "day_du", "ghi_chu": "STATUS EVALUATED (whitelist)",
    },
    # MOCK990 co Y de EVAL_PENDING - tu 16/08 (cach C) session THAT khong con
    # vao trang thai nay, nhung nhanh code van giu de tuong thich nguoc voi cac
    # dong da co trong DB. Day la du lieu mau duy nhat con test duoc nhanh do.
    {
        "tram": "MOCK990", "ten": "4G-LDG990M-HNI", "status": "EVAL_PENDING",
        "executed_at": _vn(2026, 8, 4, 11, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK990_20260804_110000",
        "xuat_phieu_at": _vn(2026, 8, 12, 8, 2), "xuat_phieu_ket_qua": "DA_XUAT",
        "cells": _cells("990", 4),
        "phieu": [("4G-LDG990M11-HNI", "SUCCESS", "MOCK-90061", 1, None),
                  ("4G-LDG990M12-HNI", "SUCCESS", "MOCK-90062", 1, None),
                  ("4G-LDG990M13-HNI", "PENDING", None, 0, None)],
        "log": "day_du", "ghi_chu": "EVAL_PENDING + phieu ket PENDING",
    },
    {
        "tram": "MOCK989", "ten": "4G-LDG989M-HNI", "status": "RUNNING",
        # executed_at = HOM NAY 08:00 - an toan vi RUNNING NGOAI whitelist
        "executed_at": None, "executed_at_hom_nay_8h": True,
        "plan_name": "R012_NQMProactiveCC_MOCK989_HOMNAY_080000",
        "xuat_phieu_at": None, "xuat_phieu_ket_qua": None,
        "cells": _cells("989", 3), "phieu": [],
        "log": "dang_chay", "ghi_chu": "CR DANG CHAY",
    },
    {
        "tram": "MOCK988", "ten": "4G-LDG988M-HNI", "status": "DONE",
        "executed_at": _vn(2026, 7, 29, 9, 0),
        "plan_name": "R012_NQMProactiveCC_MOCK988_20260729_090000",
        "xuat_phieu_at": _vn(2026, 8, 6, 8, 5), "xuat_phieu_ket_qua": "LOI",
        "cells": _cells("988", 6), "phieu": [],
        "log": "day_du", "ghi_chu": "JOB LOI KHI XU LY SESSION",
    },
]

# === 8 DONG job_run_log ===
# chi_tiet co khoa "_mock": true - DAU HIEU DUY NHAT de script don nhan ra
# (bang nay khong co cot nao chua chuoi MOCK).
# NGAY 07/08 CO Y KHONG CO DONG NAO: job khong chay hom do, chinh la ly do
# MOCK997 bi qua han. Day la du lieu quan trong nhat cua bang nay.
_CELL_998_VUOT = [{"cell_name": c, "do_te": d} for c, d in
                  zip(_cells("998", 14)[10:14], [0.5, 0.4, 0.3, 0.2])]
_CELL_998_XUAT = [{"cell_name": c, "do_te": d, "ket_qua": "SUCCESS", "phieu_id": f"MOCK-900{11 + i}"}
                  for i, (c, d) in enumerate(zip(_cells("998", 14)[:10],
                                                 [0.9, 0.87, 0.84, 0.8, 0.76, 0.72, 0.68, 0.64, 0.6, 0.55]))]

MOCK_JOB_RUNS = [
    {"bat_dau": _vn(2026, 8, 4, 8, 0, 0), "ket_thuc": _vn(2026, 8, 4, 8, 0, 47), "trang_thai": "DONE",
     "quet": 1, "ok": 3, "loi": 0, "vuot": 0, "err": None,
     "sessions": [{"tram_id": "MOCK992", "xuat_phieu_ket_qua": "DA_XUAT", "so_cell_khong_dat": 3,
                   "cell_da_xu_ly": [{"cell_name": "4G-LDG992M11-HNI", "do_te": 0.8, "ket_qua": "SUCCESS"},
                                     {"cell_name": "4G-LDG992M12-HNI", "do_te": 0.6, "ket_qua": "SUCCESS"}],
                   "cell_vuot_gioi_han": []}]},
    {"bat_dau": _vn(2026, 8, 5, 8, 0, 0), "ket_thuc": _vn(2026, 8, 5, 8, 0, 12), "trang_thai": "DONE",
     "quet": 0, "ok": 0, "loi": 0, "vuot": 0, "err": None, "sessions": []},
    {"bat_dau": _vn(2026, 8, 6, 8, 0, 0), "ket_thuc": _vn(2026, 8, 6, 8, 0, 5), "trang_thai": "FAILED",
     "quet": 0, "ok": 0, "loi": 0, "vuot": 0,
     "err": "Khong ket noi duoc CTS: timeout sau 30s", "sessions": []},
    # NGAY 07/08 KHONG CO DONG - job khong chay -> MOCK997 qua han
    {"bat_dau": _vn(2026, 8, 8, 8, 0, 0), "ket_thuc": _vn(2026, 8, 8, 8, 1, 33), "trang_thai": "DONE",
     "quet": 1, "ok": 2, "loi": 1, "vuot": 0, "err": None,
     "sessions": [{"tram_id": "MOCK993", "xuat_phieu_ket_qua": "DA_XUAT", "so_cell_khong_dat": 5,
                   "cell_da_xu_ly": [{"cell_name": "4G-LDG993M11-HNI", "do_te": 0.7, "ket_qua": "SUCCESS"},
                                     {"cell_name": "4G-LDG993M31-HNI", "do_te": 0.5, "ket_qua": "FAILED"}],
                   "cell_vuot_gioi_han": []}]},
    {"bat_dau": _vn(2026, 8, 9, 8, 0, 0), "ket_thuc": _vn(2026, 8, 9, 8, 2, 10), "trang_thai": "DONE",
     "quet": 1, "ok": 4, "loi": 0, "vuot": 0, "err": None,
     "sessions": [{"tram_id": "MOCK999", "xuat_phieu_ket_qua": "DA_XUAT", "so_cell_khong_dat": 4,
                   "cell_da_xu_ly": [{"cell_name": "4G-LDG999M11-HNI", "do_te": 0.75, "ket_qua": "SUCCESS"},
                                     {"cell_name": "4G-LDG999M12-HNI", "do_te": 0.6, "ket_qua": "SUCCESS"}],
                   "cell_vuot_gioi_han": []}]},
    {"bat_dau": _vn(2026, 8, 10, 8, 0, 0), "ket_thuc": _vn(2026, 8, 10, 8, 3, 25), "trang_thai": "DONE",
     "quet": 2, "ok": 10, "loi": 0, "vuot": 4, "err": None,
     "sessions": [{"tram_id": "MOCK998", "xuat_phieu_ket_qua": "DA_XUAT", "so_cell_khong_dat": 14,
                   "cell_da_xu_ly": _CELL_998_XUAT, "cell_vuot_gioi_han": _CELL_998_VUOT},
                  {"tram_id": "MOCK991", "xuat_phieu_ket_qua": "DA_XUAT", "so_cell_khong_dat": 3,
                   "cell_da_xu_ly": [], "cell_vuot_gioi_han": []}]},
    {"bat_dau": _vn(2026, 8, 11, 8, 0, 0), "ket_thuc": _vn(2026, 8, 11, 8, 0, 58), "trang_thai": "DONE",
     "quet": 1, "ok": 0, "loi": 0, "vuot": 0, "err": None,
     "sessions": [{"tram_id": "MOCK994", "xuat_phieu_ket_qua": "KHONG_CAN_XUAT", "so_cell_khong_dat": 0,
                   "cell_da_xu_ly": [], "cell_vuot_gioi_han": []}]},
    # finished_at NULL + RUNNING -> demo canh bao "job treo bat thuong"
    {"bat_dau": _vn(2026, 8, 12, 8, 0, 0), "ket_thuc": None, "trang_thai": "RUNNING",
     "quet": 1, "ok": 0, "loi": 0, "vuot": 0, "err": None, "sessions": []},
]


async def _kiem_tra_an_toan(s) -> None:
    """RAISE neu co session mau nao co the bi job quet va POST phieu that."""
    hom_nay = datetime.now(GMT7).date()
    nguy_hiem = []
    for m in MOCK_SESSIONS:
        ea = m["executed_at"]
        if m.get("executed_at_hom_nay_8h"):
            ea = datetime(hom_nay.year, hom_nay.month, hom_nay.day, 8, 0, tzinfo=GMT7)
        if ea is None:
            continue
        if ea.date() >= NGAY_NGUY_HIEM and len(m["cells"]) > 0 and m["status"] in WHITELIST:
            nguy_hiem.append(
                f"{m['tram']}: executed_at={ea.date()} status={m['status']} so_cell={len(m['cells'])}"
            )
    if nguy_hiem:
        raise SystemExit(
            "DUNG LAI - KHONG insert dong nao.\n"
            "Cac session sau THOA CA 3 dieu kien nguy hiem (executed_at >= "
            f"{NGAY_NGUY_HIEM} VA co cell VA status trong whitelist) -> job 8h sang "
            "se POST PHIEU THAT len CTS cho cell khong ton tai:\n  "
            + "\n  ".join(nguy_hiem)
        )
    print(f"  [OK] Chan an toan: khong session mau nao co the bi job quet (hom nay {hom_nay})")


async def _dem(s) -> dict:
    kq = {}
    for b in ("tram", "cr_session", "cr_affected_cells", "cr_phieu", "cr_log", "job_run_log", "cell_infor"):
        r = await s.execute(text(f"SELECT count(*) FROM {S}.{b}"))
        kq[b] = r.scalar_one()
    return kq


async def main() -> None:
    async with AsyncSessionLocal() as s:
        print("=== CHAN AN TOAN ===")
        await _kiem_tra_an_toan(s)

        truoc = await _dem(s)
        print("\n=== SO DONG TRUOC ===")
        for k, v in truoc.items():
            print(f"  {k:<20} = {v}")

        hom_nay = datetime.now(GMT7).date()
        now = datetime.now(timezone.utc)

        # 1. tram - phai co truoc vi cr_session.tram_id la FK -> tram.tram_id
        for i, m in enumerate(MOCK_SESSIONS):
            await s.execute(
                text(f"""INSERT INTO {S}.tram
                    (tram_id, tram_name, ma_tinh, longitude, latitude, ten_thiet_bi,
                     trang_thai, last_synced_at, created_at, updated_at)
                    VALUES (:t, :n, 'HNI', :lon, :lat, 'NOKIA', 'active', :now, :now, :now)"""),
                {"t": m["tram"], "n": m["ten"], "lon": 105.84 + i * 0.004,
                 "lat": 21.02 + i * 0.003, "now": now},
            )

        # 2. cr_session
        id_theo_tram = {}
        for m in MOCK_SESSIONS:
            ea = m["executed_at"]
            if m.get("executed_at_hom_nay_8h"):
                ea = datetime(hom_nay.year, hom_nay.month, hom_nay.day, 8, 0, tzinfo=GMT7)
            r = await s.execute(
                text(f"""INSERT INTO {S}.cr_session
                    (tram_id, action, status, plan_name, executed_at, evaluated_at,
                     xuat_phieu_at, xuat_phieu_ket_qua, is_rollback, created_at, updated_at)
                    VALUES (:t, 'shutdown', :st, :pl, :ea, :eva, :xpa, :xpk, false, :ca, :ca)
                    RETURNING id"""),
                {"t": m["tram"], "st": m["status"], "pl": m["plan_name"], "ea": ea,
                 "eva": m.get("evaluated_at"), "xpa": m["xuat_phieu_at"],
                 "xpk": m["xuat_phieu_ket_qua"],
                 "ca": m.get("created_at") or ea or now},
            )
            id_theo_tram[m["tram"]] = r.scalar_one()

        # 3. cr_affected_cells
        for m in MOCK_SESSIONS:
            sid = id_theo_tram[m["tram"]]
            for c in m["cells"]:
                await s.execute(
                    text(f"""INSERT INTO {S}.cr_affected_cells
                        (cr_session_id, cell_name, tram_id, huong_id, created_at)
                        VALUES (:sid, :c, :t, :h, :now)"""),
                    {"sid": sid, "c": c, "t": m["tram"], "h": c.split("M")[-1][:1], "now": now},
                )

        # 4. cr_phieu
        for m in MOCK_SESSIONS:
            sid = id_theo_tram[m["tram"]]
            for cell, tt, pid, so_lan, err in m["phieu"]:
                await s.execute(
                    text(f"""INSERT INTO {S}.cr_phieu
                        (cr_session_id, cell_name, trang_thai, request_payload, response_body,
                         phieu_id, error_message, so_lan_thu, created_at)
                        VALUES (:sid, :c, :tt, CAST(:rp AS jsonb), NULL, :pid, :err, :sl, :ca)"""),
                    {"sid": sid, "c": cell, "tt": tt,
                     "rp": '{"_mock": true, "_ghi_chu": "DU LIEU MAU cho FE - KHONG phai payload da gui CTS"}',
                     "pid": pid, "err": err, "sl": so_lan,
                     "ca": m["xuat_phieu_at"] or m["executed_at"] or now},
                )

        # 5. cr_log
        for m in MOCK_SESSIONS:
            sid = id_theo_tram[m["tram"]]
            goc = m["executed_at"] or m.get("created_at") or now
            if m["log"] == "day_du":
                cac_buoc = [(st, ten, pct, "success") for st, ten, pct in _CAC_BUOC]
            elif m["log"] == "loi_ssh":
                cac_buoc = [(st, ten, pct, "success") for st, ten, pct in _CAC_BUOC[:4]]
                cac_buoc.append((13, "SSH: Upload+Import+Provision", 70, "failed"))
            elif m["log"] == "dang_chay":
                goc = datetime(hom_nay.year, hom_nay.month, hom_nay.day, 8, 0, tzinfo=GMT7)
                cac_buoc = [(st, ten, pct, "success") for st, ten, pct in _CAC_BUOC[:7]]
                cac_buoc.append((8, "Tinh rsboost_new", 48, "running"))
            else:
                cac_buoc = []
            for j, (st, ten, pct, stt) in enumerate(cac_buoc):
                msg = "SSH timeout khi ket noi NetAct" if stt == "failed" else None
                await s.execute(
                    text(f"""INSERT INTO {S}.cr_log
                        (cr_session_id, step, step_name, status, message, pct, created_at)
                        VALUES (:sid, :st, :ten, :stt, :msg, :pct, :ca)"""),
                    {"sid": sid, "st": st, "ten": ten, "stt": stt, "msg": msg, "pct": pct,
                     "ca": goc + timedelta(seconds=j * 3)},
                )

        # 6. job_run_log - khoa "_mock" trong chi_tiet la dau hieu de don rac
        import json
        for j in MOCK_JOB_RUNS:
            sessions = [{**x, "cr_session_id": id_theo_tram.get(x.get("tram_id"))} for x in j["sessions"]]
            await s.execute(
                text(f"""INSERT INTO {S}.job_run_log
                    (job_type, started_at, finished_at, trang_thai, so_session_quet,
                     so_phieu_thanh_cong, so_phieu_that_bai, so_cell_vuot_gioi_han,
                     error_message, chi_tiet)
                    VALUES ('xuat_phieu_auto', :bd, :kt, :tt, :q, :ok, :loi, :vuot, :err,
                            CAST(:ct AS jsonb))"""),
                {"bd": j["bat_dau"], "kt": j["ket_thuc"], "tt": j["trang_thai"], "q": j["quet"],
                 "ok": j["ok"], "loi": j["loi"], "vuot": j["vuot"], "err": j["err"],
                 "ct": json.dumps({"sessions": sessions, "_mock": True})},
            )

        await s.commit()

        sau = await _dem(s)
        print("\n=== BANG DOI CHIEU ===")
        print(f"  {'bang':<20} {'truoc':>8} {'sau':>8} {'them':>8}")
        for k in truoc:
            print(f"  {k:<20} {truoc[k]:>8} {sau[k]:>8} {sau[k] - truoc[k]:>8}")

        print("\n=== 12 SESSION MAU ===")
        r = await s.execute(text(f"""
            SELECT s.tram_id, s.status, s.executed_at, s.xuat_phieu_ket_qua,
                   (SELECT count(*) FROM {S}.cr_affected_cells a WHERE a.cr_session_id = s.id) AS so_cell,
                   (SELECT count(*) FROM {S}.cr_phieu p WHERE p.cr_session_id = s.id) AS so_phieu
            FROM {S}.cr_session s WHERE s.tram_id LIKE '{TIEN_TO_TRAM}%' ORDER BY s.tram_id DESC"""))
        print(f"  {'tram':<9} {'status':<13} {'executed_at (VN)':<18} {'cell':>5} {'phieu':>6}  ket_qua")
        for m in r.mappings().all():
            ea = m["executed_at"].astimezone(GMT7).strftime("%d/%m/%Y %H:%M") if m["executed_at"] else "-"
            print(f"  {m['tram_id']:<9} {m['status']:<13} {ea:<18} {m['so_cell']:>5} {m['so_phieu']:>6}  "
                  f"{m['xuat_phieu_ket_qua'] or '-'}")

        print("\n=== KIEM TRA LAI SAU KHI SEED ===")
        # TACH RIENG mock va that: session THAT thoa 3 dieu kien la chuyen BINH
        # THUONG (do chinh la cach job hoat dong - CR that den ngay thu 8 se duoc
        # xuat phieu). Chi session MAU thoa 3 dieu kien moi la su co, vi cell mau
        # KHONG TON TAI tren CTS.
        r = await s.execute(text(f"""
            SELECT s.tram_id, s.executed_at::date AS ngay,
                   (SELECT count(*) FROM {S}.cr_affected_cells a WHERE a.cr_session_id = s.id) AS so_cell
            FROM {S}.cr_session s
            WHERE s.executed_at >= :ng AND s.status IN ('DONE','EVALUATED','EVAL_PENDING')
              AND (SELECT count(*) FROM {S}.cr_affected_cells a WHERE a.cr_session_id = s.id) > 0
            ORDER BY s.tram_id"""),
            {"ng": datetime(NGAY_NGUY_HIEM.year, NGAY_NGUY_HIEM.month, NGAY_NGUY_HIEM.day, tzinfo=GMT7)})
        rows = r.mappings().all()
        nguy_mock = [m for m in rows if m["tram_id"].startswith(TIEN_TO_TRAM)]
        nguy_that = [m for m in rows if not m["tram_id"].startswith(TIEN_TO_TRAM)]

        print(f"  Session MAU thoa 3 dieu kien nguy hiem: "
              f"{[m['tram_id'] for m in nguy_mock] if nguy_mock else 'KHONG CO (dung)'}")
        if nguy_mock:
            raise SystemExit("!!! SESSION MAU NGUY HIEM - phai xoa ngay bang cleanup script")

        if nguy_that:
            # KHONG phai loi cua seed - chi bao de nguoi van hanh biet truoc ngay
            # job se POST phieu that cho session THAT nao.
            print("  [CHU Y] Session THAT se duoc job quet (binh thuong, khong lien quan mock):")
            for m in nguy_that:
                print(f"    tram {m['tram_id']} - CR ngay {m['ngay']}, {m['so_cell']} cell "
                      f"-> job se xuat phieu ngay {m['ngay'] + timedelta(days=8)}")

        r = await s.execute(text(f"SELECT count(*) FROM {S}.cell_infor"))
        print(f"  cell_infor = {r.scalar_one()} (phai 27763)")
        r = await s.execute(text(
            f"SELECT id FROM {S}.cr_phieu WHERE id IN {CR_PHIEU_THAT} ORDER BY id"))
        print(f"  cr_phieu THAT con nguyen: {[x[0] for x in r.all()]}")


if __name__ == "__main__":
    asyncio.run(main())
