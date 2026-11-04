"""
scripts/import_5_neighbor_cells.py — upsert 5 gia tri current THAT (rsboost/
qrxlevmin) cho 5 cell lang gieng cua tram 110548 (CR shutdown), lay tu file
CSV that adapters/netact/data_test/data_crr012_hni_11072026_11122.csv.
Tu: yeu cau user 12072026 (verify cell_params truoc khi tu chay scripts/run_real_cr.py)

QUAN TRONG - KHONG PHAI general CSV importer: file CSV nay bi loi cau truc
tren dien rong (~27700/27763 dong) - 3 khoi cot LNCEL/LNCEL_FDD/SIB dan ngang
hang theo VI TRI DONG nhung KHONG khop nhau ve $dn (da xac minh bang grep
thu cong, xem log/DEV_LOG.md). Doc CSV theo vi tri dong la SAI tren dien
rong. Script nay CHI xu ly dung 5 cell cu the da duoc xac dinh/tra cuu THU
CONG bang cach join theo key ($dn day du, khong theo vi tri dong) - KHONG
tu dong hoa viec loc "NB-" prefix hay xu ly lech LNCEL cho toan bo file (2
van de do da xac nhan KHONG lien quan toi 5 dong nay, xem yeu cau user).
Neu can import hang loat that su sau nay, phai viet lai script rieng xu ly
dung 2 van de tren cho TOAN BO file, KHONG tai su dung script nay.

tram_id LUU DUNG THEO MRBTS CUA TUNG CELL LANG GIENG (115750/114820/114848)
- KHONG phai '110548' (do la tram bi tat, dung de tao cr_session, khong phai
tram chua cac cell lang gieng nay).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.postgres.cell_params_repo import CellParamsRepo
from domain.entities.cell_param import CellParam
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel
from infrastructure.db import AsyncSessionLocal

# Tra cuu THU CONG bang grep tren CSV that (12072026), join theo $dn day du
# (KHONG theo vi tri dong - xem canh bao dau file):
#   1. LNCEL $dn=MRBTS-115750/LNCEL-12 -> cell_name (dong 20847)
#      LNCEL_FDD $dn=MRBTS-115750/LNCEL-12/LNCEL_FDD-0 -> dlRsBoost=0dB (dong 20569)
#   2. LNCEL $dn=MRBTS-114820/LNCEL-11 -> cell_name (dong 18997)
#      LNCEL_FDD $dn=MRBTS-114820/LNCEL-11/LNCEL_FDD-0 -> dlRsBoost=0dB (dong 18722)
#   3. LNCEL $dn=MRBTS-114820/LNCEL-51 -> cell_name (dong 19000)
#      SIB $dn=MRBTS-114820/LNCEL-51/SIB-0 -> qrxlevmin=-126 (dong 18997)
#   4. LNCEL $dn=MRBTS-114820/LNCEL-31 -> cell_name (dong 18999)
#      SIB $dn=MRBTS-114820/LNCEL-31/SIB-0 -> qrxlevmin=-126 (dong 18996)
#   5. LNCEL $dn=MRBTS-114848/LNCEL-11 -> cell_name (dong 19065)
#      SIB $dn=MRBTS-114848/LNCEL-11/SIB-0 -> qrxlevmin=-126 (dong 19062)
_CELLS = [
    # (tram_id, cell_name, rsboost_current, qrxlevmin_current)
    ("115750", "4G-DDA155M12-HNI", RsboostLevel(0.0), None),
    ("114820", "4G-HBG295M11-HNI", RsboostLevel(0.0), None),
    ("114820", "4G-HBG295M51-HNI", None, Qrxlevmin(-126)),
    ("114820", "4G-HBG295M31-HNI", None, Qrxlevmin(-126)),
    ("114848", "4G-HKM300M11-HNI", None, Qrxlevmin(-126)),
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        repo = CellParamsRepo(session)
        params = [
            CellParam(tram_id=tram_id, cell_name=cell_name, rsboost_current=rsboost, qrxlevmin_current=qrxlevmin)
            for tram_id, cell_name, rsboost, qrxlevmin in _CELLS
        ]
        await repo.upsert(params)
        print(f"Da upsert {len(params)} cell_params.")


if __name__ == "__main__":
    asyncio.run(main())
