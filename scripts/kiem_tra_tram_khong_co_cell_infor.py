"""
scripts/kiem_tra_tram_khong_co_cell_infor.py - CHI DOC. Dem so tram NOKIA
netact NA09 co mat trong ho_neighbor (lam NGUON source_enb HOAC DICH
target_enb) nhung KHONG co dong nao trong cell_infor (chua tung sync qua
Admin CLI export) - tram dang tin la B sai nham CAN_GHEP_TEN cho MOI cell
cua no trong chon_cell_cr() (xem SUA 09/10/2026, domain/services/
ho_cell_selector.py).

Tu: yeu cau truc tiep user (09/10/2026) sau khi phat hien bug B 12->10 cho
tram 117713 (nguyen nhan LUC DO tuong la: tram 111629 chua sync cell_infor).

SUA 10/10/2026: ly do THAT cua tram 111629 KHONG phai "chua sync" - tram nay
CO 6 dong trong cell_infor, chi la ma MRBTS cua no (1101629) khac LNBTS
(111629) nen tra theo MRBTS (quy uoc CU) khong thay. Script nay nay DOI
sang tra theo LNBTS (dung) - xem domain/services/dist_name.py::LNBTS_LNCEL_RE -
nen so "tram NOKIA thieu cell_infor" se GIAM manh so voi lan chay truoc (108).

Chay:
    python -m scripts.kiem_tra_tram_khong_co_cell_infor
"""

import asyncio

from domain.services.dist_name import LNBTS_LNCEL_RE
from infrastructure.db import AsyncSessionLocal
from sqlalchemy import text

NETACT = "NA09"


async def main() -> None:
    async with AsyncSessionLocal() as s:
        enb_ho_rows = (await s.execute(text(
            "SELECT DISTINCT source_enb AS enb FROM system_nsn_nqmproactivecc.ho_neighbor WHERE netact = :netact "
            "UNION "
            "SELECT DISTINCT target_enb AS enb FROM system_nsn_nqmproactivecc.ho_neighbor WHERE netact = :netact"
        ), {"netact": NETACT})).all()
        enb_ho = {r[0] for r in enb_ho_rows}
        print(f"So enb phan biet (nguon + dich) trong ho_neighbor netact={NETACT}: {len(enb_ho):,}")

        dn_rows = (await s.execute(text(
            "SELECT dn_lncel FROM system_nsn_nqmproactivecc.cell_infor"
        ))).all()
        enb_co_cell_infor: set[int] = set()
        for (dn_lncel,) in dn_rows:
            m = LNBTS_LNCEL_RE.search(dn_lncel or "")
            if m:
                enb_co_cell_infor.add(int(m.group(1)))
        print(f"So enb phan biet co it nhat 1 dong trong cell_infor: {len(enb_co_cell_infor):,}")

        enb_thieu = enb_ho - enb_co_cell_infor
        print(f"So enb (trong ho_neighbor NA09) KHONG co dong nao trong cell_infor: {len(enb_thieu):,}")

        if not enb_thieu:
            return

        tram_rows = (await s.execute(text(
            "SELECT tram_id, tram_name, ten_thiet_bi FROM system_nsn_nqmproactivecc.tram "
            "WHERE tram_id = ANY(:tram_ids)"
        ), {"tram_ids": [str(e) for e in enb_thieu]})).all()
        tram_theo_id = {r[0]: r for r in tram_rows}

        nokia_thieu = []
        khong_ro_tram = 0
        vendor_khac = 0
        for enb in enb_thieu:
            row = tram_theo_id.get(str(enb))
            if row is None:
                khong_ro_tram += 1
                continue
            _tram_id, tram_name, ten_thiet_bi = row
            if (ten_thiet_bi or "").strip().upper() == "NOKIA":
                nokia_thieu.append((str(enb), tram_name, ten_thiet_bi))
            else:
                vendor_khac += 1

        print(f"\nTrong so {len(enb_thieu):,} enb thieu cell_infor:")
        print(f"  - Khong tim thay trong bang tram (co the chua sync RIMS): {khong_ro_tram:,}")
        print(f"  - Co trong bang tram nhung vendor KHAC Nokia: {vendor_khac:,}")
        print(f"  - Co trong bang tram VA la NOKIA (dang tin la B sai nham CAN_GHEP_TEN): {len(nokia_thieu):,}")

        print("\n10 vi du tram NOKIA khong co du lieu trong cell_infor:")
        for tram_id, tram_name, ten_thiet_bi in sorted(nokia_thieu)[:10]:
            print(f"    tram_id={tram_id:<10} tram_name={tram_name:<24} ten_thiet_bi={ten_thiet_bi}")


if __name__ == "__main__":
    asyncio.run(main())
