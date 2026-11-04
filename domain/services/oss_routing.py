"""
ma_tinh_cu_tu_ten_cell() — suy MA TINH CU (truoc sap nhap) tu 3 ky tu cuoi
TEN CELL. Tu: Giai doan 1 buoc 2 (27/09/2026, quyet dinh dinh tuyen OSS).

# Quyet dinh design: dung TEN CELL (khong dung tram_name, khong dung cot
# tram.ma_tinh) de dinh tuyen OSS
# Tai sao:
#   - tram_name SAI: 13.038 tram (do that) khong dung mau "...-XXX" - moi
#     vendor/doi thi cong dat ten trạm theo quy uoc rieng, khong dong bo.
#   - cot tram.ma_tinh SAI: la ma tinh MOI (sau sap nhap 2025, 34 gia tri) -
#     lech 37,8% so voi ma tinh CU ma OSS dang phan vung theo (moi OSS chia
#     theo dia gioi HANH CHINH CU luc trien khai, chua cap nhat theo sap
#     nhap). Dung cot nay se gui NHAM XML sang OSS khac.
#   - TEN CELL DUNG: du lieu that xac nhan 456/456 cell trong cr_affected_cells
#     dung dung mau "4G-...-XXX" (100%, KHONG co ngoai le nhu tram_name).
"""

import re

# 4G-<bat ky>-<3 chu hoa> - vd "4G-STY024M32-HNI" -> "HNI". ".+"" (>=1 ky tu)
# o giua CHU Y khong gioi han do dai/ky tu, chi ep dung PREFIX "4G-" va HAU TO
# "-XXX" (3 chu HOA) - day la mau DUY NHAT da xac nhan qua du lieu that
# (456/456 cell), KHONG suy doan them quy tac nao khac.
_MA_TINH_CU_RE = re.compile(r"^4G-.+-([A-Z]{3})$")


def ma_tinh_cu_tu_ten_cell(cell_name: str) -> str | None:
    """Tra ma tinh CU (3 ky tu, vd "HNI") tu ten cell, hoac None neu ten
    KHONG dung mau "4G-...-XXX".

    CO Y tra None thay vi raise: day la 1 CELL trong ca CR (co the co nhieu
    cell), 1 cell sai mau KHONG duoc lam hong toan bo request - caller (xem
    application/trigger_cr_use_case.py) tu quyet dinh loai RIENG cell do
    (ly do TEN_CELL_SAI_MAU) va van chay tiep voi cac cell con lai, GIONG
    tinh than "khong doan, khong bo qua" da dung cho CELL_ID_PHANG.
    """
    if not cell_name:
        return None
    m = _MA_TINH_CU_RE.match(cell_name)
    return m.group(1) if m else None
