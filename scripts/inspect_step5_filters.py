"""
scripts/inspect_step5_filters.py — quan sat CHI TIET buoc 5 (BandPriorityFilter
+ NbLncelFilter) voi du lieu CDS THAT cho tram_id=110548. KHONG dung
TriggerCrUseCase.execute() — goi THANG CdsHttpAdapter + NeighborCellService +
BandPriorityFilter + NbLncelFilter, KHONG tao cr_session, KHONG dung DB
(cell_params/tram) o bat ky buoc nao. An toan tuyet doi — khong the tai gay
bug tram_id sai da phat hien truoc do (BUG DO NAM O buoc 8/10 - Rsboost/
QrxlevminCalculator - VAN CHUA SUA, script nay KHONG di toi do).

Tu: yeu cau user 12072026 — dung dung sau khi in xong danh sach cell cuoi
cung cua buoc 5, KHONG chay tiep buoc 6 tro di.

CHUA TU CHAY - chi viet, cho user tu chay:
    python scripts/inspect_step5_filters.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.http.cds_http_adapter import CdsHttpAdapter
from domain.services.band_priority_filter import BandPriorityFilter
from domain.services.nb_lncel_filter import NbLncelFilter
from domain.services.neighbor_cell_service import NeighborCellService

TRAM_ID = "110548"
TRAM_NAME = "4G-HKM005M-HNI"
ACTION = "shutdown"


def _explain_nb_lncel_exclusion(cell) -> str:
    reasons = []
    if cell.cell_name.startswith("NB-"):
        reasons.append("prefix NB-")
    lncel_local_id = cell.dist_name.rsplit("LNCEL-", 1)[-1]
    if lncel_local_id.startswith("2"):
        reasons.append(f"LNCEL-{lncel_local_id} (bat dau bang 2)")
    return " VA ".join(reasons) if reasons else "(khong xac dinh - kiem tra lai logic)"


def _print_table(rows: list[tuple], headers: tuple) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


async def main() -> None:
    adapter = CdsHttpAdapter()
    raw_huongs = await adapter.get_cell_neighbors(TRAM_ID, TRAM_NAME, ACTION)

    # ===== 1. RAW ban dau (truoc MOI filter, thang tu CDS) =====
    raw_total = sum(len(h.get("cells", [])) for h in raw_huongs)
    print("=" * 78)
    print(f"1. RAW tu CDS (truoc moi filter): {len(raw_huongs)} huong, {raw_total} cell")
    print("=" * 78)

    # Buoc 4 (NeighborCellService.filter) - can de co input dung cho band_filter
    after_step4 = NeighborCellService().filter(raw_huongs)
    print(f"\n(Buoc 4 — NeighborCellService.filter(), can lam input cho band_filter): {len(after_step4)} cell")

    # ===== 2. SAU band_filter, TRUOC nb_lncel_filter =====
    after_band = BandPriorityFilter().filter(after_step4)
    print("\n" + "=" * 78)
    print(f"2. SAU band_filter (TRUOC nb_lncel_filter): {len(after_band)} cell")
    print("=" * 78)
    _print_table(
        [(c.cell_name, c.huong_id) for c in after_band],
        ("cell_name", "huong_id"),
    )

    # ===== 3. Cell BI LOAI boi nb_lncel_filter =====
    after_nb = NbLncelFilter().filter(after_band)
    after_nb_names = {c.cell_name for c in after_nb}
    excluded = [c for c in after_band if c.cell_name not in after_nb_names]
    print("\n" + "=" * 78)
    print(f"3. Cell BI LOAI boi nb_lncel_filter: {len(excluded)} cell")
    print("=" * 78)
    _print_table(
        [(c.cell_name, _explain_nb_lncel_exclusion(c)) for c in excluded],
        ("cell_name", "ly do"),
    )

    # ===== 4. Cell CON LAI cuoi cung (sau ca 2 filter) =====
    print("\n" + "=" * 78)
    print(f"4. Cell CON LAI cuoi cung (sau band_filter + nb_lncel_filter): {len(after_nb)} cell")
    print("=" * 78)
    _print_table(
        [(c.cell_name, c.dist_name, c.huong_id) for c in after_nb],
        ("cell_name", "dist_name", "huong_id"),
    )

    print("\n" + "=" * 78)
    print(f"TONG KET: {raw_total} raw -> {len(after_step4)} sau buoc 4 -> {len(after_band)} sau band_filter -> {len(after_nb)} sau nb_lncel_filter")
    print("DUNG O DAY THEO YEU CAU - KHONG chay buoc 6 (assign priority) tro di.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
