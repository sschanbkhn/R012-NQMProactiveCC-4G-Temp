"""
extract_lnbts() — helper dung chung cho RsboostCalculator/QrxlevminCalculator.
Tu: docs/DEV_LOG.md muc "sua gom/join tram MRBTS -> LNBTS" (21072026, xac nhan
voi user sau khi verify DB that).

TAI SAO LNBTS (khong phai MRBTS): MRBTS = site lon (co the chua nhieu LNBTS),
LNBTS = tram nho ben trong (eNodeB) = muc "tram" chuan ma bang tram/RIMS dung
(tram.tram_id = enodeb_id tu RIMS). Da verify that: bang tram JOIN theo LNBTS
ra dung ten/toa do 8/8 mau; JOIN theo MRBTS (khi MRBTS != LNBTS) ra RONG hoan
toan 8/8 mau (khong co dong nao). 57/27763 dong cell_infor co MRBTS != LNBTS
(0.21%, loi nhap lieu Admin CLI export - MRBTS thua 1 chu so dau so voi LNBTS,
KHONG phai 1 MRBTS ung nhieu LNBTS khac toa do). Neu tiep tuc dung MRBTS lam
tram_id cho CellParam se FK VIOLATION khi ghi cell_params (cot tram_id
REFERENCES tram(tram_id), DB_SCHEMA.md dong 79) voi 1 trong 57 nhom nay.
"""

import re

LNBTS_RE = re.compile(r"LNBTS-(\d+)")

# (LNBTS, LNCEL) tu DN dang "PLMN-PLMN/MRBTS-x/LNBTS-y/LNCEL-z".
#
# SUA 10/10/2026 (yeu cau truc tiep user, CHUNG MINH BANG DU LIEU + TOAN HOC):
# TRUOC day quy uoc nham la "eNB ID trong ECI tuong ung MRBTS" (regex cu
# MRBTS_LNCEL_RE lay group MRBTS) - SAI. Chung minh:
#   1. ECI chuan 3GPP la 28 bit = eNB ID (20 bit, toi da 1.048.575) + Cell ID
#      (8 bit). Tram 111629 co MRBTS=1101629 > 1.048.575 - VUOT QUA suc chua
#      20 bit, KHONG THE la gia tri ECI hop le -> MRBTS KHONG THE la nguon
#      cua eNB ID trong ECI (bang chung TOAN HOC, doc lap du lieu).
#   2. Kiem tren file NA09 THAT: loc dong nguon LNBTS=111629 (MRBTS=1101629),
#      so target_enb=eci//256 - co 30 dong target_enb==111629 (LNBTS, dung
#      target_lcr khop CHINH XAC 6 LNCEL that cua tram nay trong cell_infor:
#      11/12/13/51/52/53), 0 dong target_enb==1101629 (MRBTS, khong the xay
#      ra - khop voi (1) o tren).
#   3. Thuc nghiem tren 27.202 cap (target_enb,target_lcr) NA09 vendor NOKIA:
#      ghep theo LNBTS = 26.937 cap (99,03%), theo MRBTS (quy uoc cu) =
#      26.714 cap (98,21%) - LNBTS la TAP CON BAO TRUM HOAN TOAN MRBTS (223
#      cap chi ghep duoc bang LNBTS, 0 cap nguoc lai).
# => eNB ID trong ECI CHINH LA LNBTS (khong phai MRBTS, khong can ket hop ca
# hai) - CUNG quy uoc voi adapters/netact/import_ho_neighbor.py (source_enb)
# va rsboost_calculator.py/qrxlevmin_calculator.py (extract_lnbts() o tren).
# 2,67% dong cell_infor (2.350/87.913) co MRBTS != LNBTS (KHONG con la
# 0,21%/57 dong nhu do luc dau - bang cell_infor da lon hon).
#
# Dung o adapters/postgres/cell_infor_repo.py::get_dn_map_theo_enb_lcr() de
# tra cuu cell dich tu ho_neighbor.target_enb/target_lcr (ECI decode). DAT O
# DAY (domain/, dung chung) thay vi moi noi tu dinh nghia rieng - CAC BAN SAO
# RIENG o adapters/netact/import_ho_neighbor.py va scripts/spike_ho_neighbor.py
# (import boi scripts/phan_tich_nguong_ho.py) van GIU RIENG (khong refactor
# import ve day, ngoai pham vi yeu cau) nhung DA SUA DONG BO cung quy uoc
# LNBTS - xem tung file do.
LNBTS_LNCEL_RE = re.compile(r"LNBTS-(\d+)/LNCEL-(\d+)")


def co_dang_dn_nokia(cell_id: str) -> bool:
    """cell_id co phai DN Nokia (chua "LNBTS-<so>") khong. Them 07092026.

    DUNG CHUNG regex voi extract_lnbts() - neu tach 2 bieu thuc rieng thi
    "kiem duoc" va "parse duoc" se lech nhau vao mot ngay nao do, va luc do
    guard o neighbor_cell_filter cho qua roi extract_lnbts van nem loi.

    VI SAO CAN: CDS tra cell_id dang PHANG (= cell_name, vd
    "4G-PYN015M12-VPC") cho cell no KHONG QUAN LY. Do la tin hieu ngoai pham
    vi, khong phai du lieu hong - xem chu y day du trong
    domain/services/neighbor_cell_filter.py::filter_affected().
    """
    return bool(cell_id) and LNBTS_RE.search(cell_id) is not None


def extract_lnbts(dist_name: str) -> str:
    m = LNBTS_RE.search(dist_name)
    if not m:
        raise ValueError(f"Khong parse duoc LNBTS tu dist_name: {dist_name}")
    return m.group(1)
