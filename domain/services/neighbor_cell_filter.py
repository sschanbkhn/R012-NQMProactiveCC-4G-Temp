"""
NeighborCellFilter — 2 nhanh loc cell lang gieng tu raw CDS response.
Thay the hoan toan NeighborCellService + BandPriorityFilter + NbLncelFilter +
HuongCellSelector (da xoa, KHONG con trong domain/services/) - viet lai tu dau
theo dung 4 buoc user chi dinh (13072026, xac nhan voi user, KHONG giu logic
cu), verify khop CHINH XAC 100% voi bang tay tren du lieu that (368 cell,
tram_id=110548, tram_name=4G-HKM005M-HNI) - xem tests/domain/test_neighbor_cell_filter.py.

BUG THAT phat hien trong luc verify (khong phai gia dinh): thu tu buoc cu SAI —
NeighborCellService.filter() dedup cell trung ten XUYEN HUONG (rsboost-wins)
TRUOC khi BandPriorityFilter chon band theo sector Y, lam sai lech tap cell co
mat trong moi huong luc so sanh band. Pipeline moi chon band TRUOC (tren toan
bo raw list moi huong, chua dedup), roi moi loc/dedup — day la thu tu DUNG,
khop 100% voi ket qua tay xac nhan tu WORKFLOW that (session 193).

CAP NHAT 13072026 (xac nhan voi user): BUSINESS_RULES.md SS2.2/2.3 bo sung 3
rule null-safety/validity vao buoc 1 va buoc 3 - cell_name prefix "VNP-" bo qua
(operator khac - Viettel, RULE THAT, khong phai rule "ngu" nhu bao cao truoc
do), cell_id null/rong bo qua, duplicate huong_id trong raw response (2 entry
cung huong_id) giu entry xuat hien dau (first-wins).

CHOT 09/2026 (user xac nhan): dedup cell xuyen huong dung THU TU huong_id tang
dan - huong_id nho hon xu ly truoc va giu quyen. KHONG con rule "rsboost luon
thang qrxlevmin" cua BUSINESS_RULES.md SS2.4 ban cu; SS2.4 da duoc sua theo
dung thuat toan nay. Tren du lieu that 368 cell (110548) hai cach cho CUNG ket
qua vi xung dot da duoc buoc 2 (band priority) giai quyet truoc khi toi dedup.

CAP NHAT 21072026 (xac nhan voi user, BUG THAT phat hien qua trace tram
111139 - session #203): guard "if huong_id is None: continue" o buoc 1 (them
20072026 cho tram 111138) la SAI ve nghiep vu - loai oan phan lon huong
(tram 111139: 11/13 huong nhom ten "W..." bi loai, chi con 1 cell song sot
trong khi le ra phai xu ly ca 13 huong). "M"/"W"/"E"/"S" trong huong_name
(ky tu vi tri 9, VD "4G-STY008W12-HNI") CHI la quy uoc loai tram, KHONG anh
huong y nghia huong_id - moi huong (bat ke ky tu loai) deu phai tham gia CR
binh thuong. Sua: huong_id gio SUY TU huong_name (2 chu so vi tri co dinh
[10:12], xem _extract_huong_id_from_name() ben duoi) thay vi doc truc tiep
field huong_id CDS tra ve (field nay khong dang tin - CDS tra null cho nhom
"W" nhu da thay). Neu CDS co huong_id (khong null) VA lech voi ten -> uu
tien gia tri tu TEN (nguon chuan theo xac nhan nghiep vu), chi log canh bao.

CAP NHAT 22072026 (xac nhan voi user, sau khi trace that tram 110548: 368
cell CDS -> 52 unique -> 47 hop le -> 12 chay CR): pipeline gio tach RO 2
nhanh, KHONG con 1 method filter() duy nhat -
  - filter_affected() (Nhanh A): dedup + loc prefix/null + loai cell tram goc,
    KHONG loc huong/band/rank. Dung DANH GIA PHAM VI anh huong (BUSINESS_RULES.md
    Section 9) - vd hien thi cho user biet "47 cell nay co the bi tac dong RF",
    KHONG phai danh sach se dieu chinh rsboost/qrxlevmin.
  - filter_for_cr() (Nhanh B): TAI DUNG filter_affected() de lay tap cell_name
    hop le, roi loc TIEP huong+band+rank (buoc 1/2/4 GIU NGUYEN 100% logic cu,
    KHONG doi) -> danh sach THAT SU dieu chinh rsboost/qrxlevmin trong CR (12
    cell voi tram 110548 - da verify KHONG doi so voi truoc khi tach nhanh).
Ly do tach: Nhanh A (47 cell) va Nhanh B (12 cell, tap con cua Nhanh A) phuc vu
2 muc dich khac nhau trong preview (xem application/preview_cr_use_case.py) -
truoc day chi co Nhanh B, khong co cach nao biet "pham vi RF bi anh huong that
su" rong hon 12 cell se dieu chinh.

Input: raw_huongs (list[dict], dung "huongs" tu response CDS - INetworkGateway.
get_cell_neighbors() da tra dung field nay, KHONG doi contract).
Output: list[Cell], priority GIU NGUYEN gia tri goc tu CDS (khong renumber).

CAP NHAT 03/10/2026 (quyet dinh moi, xac nhan voi user - THAY THE buoc 2 cu):
luat band cu (02/10/2026, BAND_CHAY_CR) loc theo band cua HUONG TRAM TAT la
SAI - khao sat du lieu that tram 160008 cho thay CUNG 1 cell lan can (vd
TAN025M13) xuat hien o NHIEU huong tram tat khac nhau voi band khac nhau, nen
"band cua huong" khong phai thuoc tinh on dinh cua cell. Luat moi: band la
cua CHINH CELL LAN CAN, suy tu LNCEL trong DN cua no (xem band_tu_lncel() o
tren) - band cua tram tat KHONG con dung de loc nua. filter_for_cr() gio:
  1. Gom huong_id theo SECTOR (Y = huong_id % 10) - KHONG gioi han band, moi
     huong deu dong gop ung vien (khac truoc: chi 1 huong "thang" moi dong gop).
  2. Trong 1 sector, GOP ung vien cua MOI huong_id - cell trung ten (xuat
     hien o >=2 huong cung sector) giu ban co priority NHO NHAT; neu bang
     nhau, giu ban tu huong co BAND_PRIORITY cao hon (xu ly huong theo thu tu
     nay TRUOC khi gop nen tie-break tu nhien, khong can code rieng).
  3. Loc theo band CUA CELL (^[13][0-9]$) + small cell (loai nhu cu).
  4. Sap theo (priority, BAND_PRIORITY cua huong nguon) - cung co che tie-break
     voi buoc 2.
  5. Chon toi da MAX_CELLS_PER_HUONG/sector (rank1=rsboost, rank2=qrxlevmin).
  6. Dedup XUYEN SECTOR - sector nho hon (Y be hon) xu ly truoc va giu quyen,
     giong y het co che dedup xuyen huong cu (chi doi don vi tu "huong" sang
     "sector").
Cell ket qua gio mang them Cell.sector (KHOA gom nhom thay huong_id cho
priority_assigner.py, vi 1 sector co the gom cell tu nhieu huong_id goc khac
nhau) va Cell.band (hien thi preview, KHONG dung de loc gi them).
"""

import logging
import re

from domain.entities.cell import Cell
from domain.services.dist_name import co_dang_dn_nokia, extract_lnbts
from domain.services.loai_tram import LOAI_TRAM_SMALL_CELL, loai_tram_tu_ten_cell

logger = logging.getLogger(__name__)

BAND_PRIORITY = {1: 1, 3: 2, 5: 3, 4: 4}  # X -> rank, thap = uu tien cao (BUSINESS_RULES.md SS3.2)

# SUA 03/10/2026 (quyet dinh moi, THAY THE hoan toan BAND_CHAY_CR cu da xoa):
# truoc day band duoc hieu la cua HUONG TRAM TAT (X = huong_id // 10), chon 1
# huong/sector theo band do roi loc cell trong huong con lai. Phat hien SAI:
# band THAT SU can loc la cua CHINH CELL LAN CAN (cell se bi sua rsboost/
# qrxlevmin), suy tu LNCEL trong DN cua no - khong lien quan gi huong_id tram
# tat. Vi du that (tram 160008): huong W11 (X=1) va huong M52 (X=5) cung
# sector 1 deu co cell dung LNCEL-13 (F1) - neu loc theo huong se loai oan
# nhung cell hop le chi vi no "dung sai huong", trong khi ban chat no van la
# 1800 F1/F2 hop le.
#
# ^[13][0-9]$ - LNCEL dung 2 chu so, chu so dau la 1 (F1) hoac 3 (F2). Khac
# (40-59 la 900/2100, 112/211/212... khong khop do dai/dau so) -> loai, ly do
# BAND_KHONG_CHAY_CR. CHI filter_for_cr() (Nhanh B) ap dung - filter_affected()
# (Nhanh A) KHONG loc band, van tinh MOI cell cho danh gia QoS/QoE + xuat phieu.
_LNCEL_CHAY_CR_RE = re.compile(r"^[13][0-9]$")


def _lncel_local_id(cell_id: str) -> str:
    # Phan sau "LNCEL-" trong DN, VD ".../LNCEL-13" -> "13".
    return cell_id.rsplit("LNCEL-", 1)[-1]


def band_tu_lncel(cell_id: str) -> str | None:
    """Band CUA CHINH CELL (khong phai huong tram tat), suy tu LNCEL trong DN.

    "1800 F1" (LNCEL bat dau "1"), "1800 F2" (bat dau "3"), None neu khong
    khop ^[13][0-9]$ (cell nay se bi loai khoi Nhanh B, ham nay van dung lai
    duoc cho muc dich hien thi/debug o noi khac khi can).
    """
    local_id = _lncel_local_id(cell_id)
    if not _LNCEL_CHAY_CR_RE.match(local_id):
        return None
    return "1800 F1" if local_id[0] == "1" else "1800 F2"


# 4 -> 2 (quyet dinh van hanh 09/2026, user chot): MOI HUONG chi con DUNG 2
# cell - 1 cell rsboost (rank 1) + 1 cell qrxlevmin (rank 2). Con so nay khop
# 1-1 voi RSBOOST_RANKS/QRXLEVMIN_RANKS o domain/services/priority_assigner.py:
# sua 1 trong 2 cho ma quen cho kia se tao cell khong duoc gan action_type nao
# (rank 3+) va cell do se bien mat khoi CR mot cach im lang.
#
# Truoc 09/2026 la 4 (2 rsboost + 2 qrxlevmin), va con so 4 do KHONG co nguon
# trong BUSINESS_RULES.md/WORKFLOW.md goc - chi la minh thi cua user luc code
# buoc 5. Nay ca con so lan y nghia deu da duoc chot ro.
#
# SUA 03/10/2026: ten bien giu nguyen "HUONG" vi ly do lich su/it noi tham
# chieu, nhung tu nay DON VI AP DUNG la SECTOR (xem CAP NHAT 03/10/2026 dau
# file) - 1 sector co the gom cell tu nhieu huong_id, con so 2 la "2 cell/
# sector", khong con la "2 cell/huong" theo nghia cu.
MAX_CELLS_PER_HUONG = 2

# Ma ly do cell ngoai pham vi (V8, 09/2026) - CO DINH, FE/nguoi doc dua vao
# CHUOI nay de phan biet nhieu ly do (hien tai CHI CO 1 nhanh dua cell vao
# ngoai_pham_vi - xem docstring filter_affected() - nhung khai bao CO DINH tu
# dau de sau nay them nhanh moi thi FE khong phai doan chuoi tu do).
LY_DO_CELL_ID_PHANG = "CELL_ID_PHANG"

# 2 ma THEM (Giai doan 1 buoc 2, 27/09/2026) - dinh tuyen OSS theo tung cell.
# KHAC CELL_ID_PHANG o CHO PHAT SINH: 2 ma nay KHONG phat sinh trong ham nay
# (filter_affected() - Nhanh A, "cell co bi anh huong RF khong"), ma phat
# sinh o buoc SAU, trong application/trigger_cr_use_case.py khi gom cell
# Nhanh B theo OSS truoc khi submit_cr() - nhung DUNG CHUNG danh sach bao cao
# "cell_ngoai_pham_vi_chi_tiet" (API_CONTRACTS.md) vi cung tra loi 1 cau hoi:
# "cell nay vi sao KHONG nam trong CR duoc xu ly".
#   TEN_CELL_SAI_MAU     - ten cell khong dung mau "4G-...-XXX" nen KHONG suy
#                          duoc ma tinh cu (domain/services/oss_routing.py)
#   OSS_CHUA_CAU_HINH    - suy duoc ma tinh cu/vendor nhung IOssRouter khong
#                          co route, hoac credential con la placeholder "???"
LY_DO_TEN_CELL_SAI_MAU = "TEN_CELL_SAI_MAU"
LY_DO_OSS_CHUA_CAU_HINH = "OSS_CHUA_CAU_HINH"

# 1 ma THEM (quyet dinh 02/10/2026, SUA PHAM VI cung ngay - ban dau chi dinh
# "khong chay CR", sau CHOT LAI MO RONG ra CA danh gia QoS/QoE + xuat phieu):
# KHONG dua small cell vao BAT KY danh sach nao (chay CR LAN danh gia). Du
# lieu small cell VAN giu nguyen trong cell_infor (khong xoa) - day la quyet
# dinh ve PHAM VI SU DUNG trong CR/danh gia, khong phai ve luu tru.
#
# Ma nay phat sinh o CA 2 nhanh:
#   - filter_affected() (Nhanh A) - gate CUOI CUNG truoc khi cell vao result,
#     cung vi tri/kieu voi check CELL_ID_PHANG o tren.
#   - filter_for_cr() (Nhanh B) - Buoc 3b, GIU LAI (khong xoa) du filter_affected()
#     da loai san: filter_for_cr() CO THE duoc goi DOC LAP (truyen affected_cells
#     tu ben ngoai, KHONG qua filter_affected() that), nen can luoi an toan RIENG.
#     Trong duong chay THAT (trigger_cr_use_case.py, filter_for_cr() nhan
#     affected_cells=ket qua filter_affected() da loai small cell san), small
#     cell KHONG CON trong affected_names nen Buoc 3b se khong gap lai no nua -
#     + dedup "cell_name not in {...}" o ca 2 nhanh dam bao DU co gap lai cung
#     KHONG ghi ly do SMALL_CELL 2 lan vao cung 1 list cell_ngoai_pham_vi_chi_tiet.
LY_DO_SMALL_CELL = "SMALL_CELL"

# 1 ma THEM (quyet dinh 02/10/2026, cung dot voi SMALL_CELL) - band KHONG
# duoc chay CR. KHAC SMALL_CELL o PHAM VI: ma nay CHI phat sinh trong
# filter_for_cr() (Nhanh B) - filter_affected() (Nhanh A, danh gia QoS/QoE +
# xuat phieu) KHONG loc band, van tinh moi band nhu truoc.
#
# SUA 03/10/2026: dieu kien phat sinh ma nay da doi (band_tu_lncel() tra None
# - xem Buoc 3b trong filter_for_cr()), nhung Y NGHIA ma nay (cell bi loai vi
# ly do band) KHONG doi, nen GIU NGUYEN ten ma - FE khong can sua gi.
LY_DO_BAND_KHONG_CHAY_CR = "BAND_KHONG_CHAY_CR"

# Do dai chuan huong_name (VD "4G-STY008M13-HNI" = 16 ky tu) - VNPT dat ten
# co dinh dang, huong_id (2 chu so) LUON nam o vi tri [10:12]. Day la gia
# dinh dua tren du lieu that (tram 110548/111138/111139) - CHUA co dac ta
# chinh thuc trong docs/, neu sai o vung/ma tinh khac se bi bat boi guard
# do dai ben duoi (log canh bao + bo qua, khong tach mu).
_HUONG_NAME_LENGTH = 16
_HUONG_ID_START = 10
_HUONG_ID_END = 12


def _extract_huong_id_from_name(huong_name: str) -> int | None:
    # Tach huong_id tu VI TRI CO DINH trong ten thay vi doc field huong_id
    # CDS tra ve - field CDS khong dang tin (tra null cho nhom ten "W...",
    # xem CAP NHAT 21072026 o dau file). Guard do dai TRUOC khi tach: neu
    # huong_name khong dung 16 ky tu, vi tri [10:12] co the tro sai cho khac
    # trong ten (VD quy uoc dat ten khac vung/ma tinh) - tach mu se ra
    # huong_id SAI ma khong ai biet, nguy hiem hon nhieu so voi bo qua han
    # huong nay va canh bao ro rang de nguoi van hanh kiem tra lai.
    if len(huong_name) != _HUONG_NAME_LENGTH:
        logger.warning(
            "Bo qua huong vi huong_name do dai bat thuong (mong doi %d ky tu, "
            "thuc te %d): %s",
            _HUONG_NAME_LENGTH, len(huong_name), huong_name,
        )
        return None
    digits = huong_name[_HUONG_ID_START:_HUONG_ID_END]
    if not digits.isdigit():
        # Do dai dung 16 nhung vi tri [10:12] khong phai 2 chu so - van la
        # dau hieu format ten khac thuong, khong ep int() (se crash
        # ValueError) ma bo qua + log giong truong hop do dai sai.
        logger.warning(
            "Bo qua huong vi vi tri [10:12] cua huong_name khong phai so: %s",
            huong_name,
        )
        return None
    return int(digits)


class NeighborCellFilter:
    def filter_affected(
        self,
        raw_huongs: list[dict],
        tram_goc_id: str | None = None,
        ngoai_pham_vi: list[str] | None = None,
        ngoai_pham_vi_chi_tiet: list[dict] | None = None,
    ) -> list[Cell]:
        # Nhanh A - danh gia PHAM VI ANH HUONG. KHONG ap dung guard huong_name/
        # band-priority (khac Nhanh B) - flatten TOAN BO cell tho tu MOI huong,
        # vi Nhanh A can biet CA cell bi anh huong RF, ke ca cell thuoc huong
        # se "thua" ve band o Nhanh B (van la neighbor RF that, chi khong duoc
        # chon de dieu chinh rsboost/qrxlevmin).
        #
        # tram_goc_id mac dinh None (bo qua buoc loai cell tram goc) - de cac
        # test/caller cu KHONG can biet tram_id goc van goi duoc binh thuong.
        # ngoai_pham_vi (07092026): caller truyen list RONG vao de HUNG ten cac
        # cell bi loai vi CDS khong quan ly. Dung out-param thay vi doi kieu tra
        # ve: filter_affected() dang duoc filter_for_cr() va _prepare_plan() goi
        # theo kieu list[Cell], doi kieu se pha het. Caller khong quan tam thi
        # khong truyen gi - hanh vi y nguyen.
        #
        # ngoai_pham_vi_chi_tiet (V8, 09/2026): THEM SONG SONG voi ngoai_pham_vi
        # (KHONG doi kieu field cu, FE dang doc list[str]) - moi phan tu la
        # {"cell_name":.., "ly_do":..} de FE/API tra ra LY DO thay vi chi ten
        # cell tron. 2 nhanh append (LY_DO_CELL_ID_PHANG ben duoi, VA
        # LY_DO_SMALL_CELL them 02/10/2026 - xem gate cuoi cung truoc khi cell
        # vao result).
        # SECTOR CUA TRAM TAT (THEM 04/10/2026, luat xuat phieu toi da 2/sector)
        # - suy huong_id tu TEN (_extract_huong_id_from_name(), CUNG ham dung
        # trong filter_for_cr(), KHONG viet ban sao cong thuc) vi field
        # huong_id CDS tra ve KHONG dang tin (null cho nhom huong ten "W...",
        # xem CAP NHAT 21072026 dau file) - khac han huong_id_cds ben duoi
        # (van GIU RIENG cho Cell.huong_id cua Nhanh A, chi de tham khao,
        # KHONG doi y nghia cu). Cell o NHIEU huong -> giu sector NHO NHAT
        # (quyet dinh 04/10/2026) - gop tu TAT CA lan xuat hien cua cell_name
        # xuyen suot moi huong, KHONG chi huong "thang" dedup o duoi (dedup
        # chi giu 1 BAN GHI dai dien cho cac truong khac, sector la ngoai le
        # rieng can MIN qua tat ca). Ghi vao Cell.sector o 1 PASS RIENG sau
        # vong lap chinh (xem duoi return) - trong vong lap chinh, 1 cell co
        # the duoc append TRUOC khi gap huong co sector nho hon no, nen khong
        # the gan truc tiep luc append duoc.
        cell_sector_min: dict[str, int] = {}
        seen_cell_names: set[str] = set()
        result: list[Cell] = []
        for huong in raw_huongs:
            huong_id_cds = huong.get("huong_id")
            huong_id_tu_ten = _extract_huong_id_from_name(huong.get("huong_name", ""))
            sector_cua_huong = huong_id_tu_ten % 10 if huong_id_tu_ten is not None else None
            for c in huong.get("cells", []):
                if c.get("technology") != "4G" or c.get("status") != "active":
                    continue
                cell_name = c.get("cell_name")
                if not cell_name:
                    continue
                if sector_cua_huong is not None:
                    hien_tai = cell_sector_min.get(cell_name)
                    if hien_tai is None or sector_cua_huong < hien_tai:
                        cell_sector_min[cell_name] = sector_cua_huong
                if cell_name in seen_cell_names:
                    continue  # dedup theo cell_name - 1 cell co the la neighbor cua nhieu huong, chi tinh 1 lan
                cell_id = c.get("cell_id")
                if not cell_id:
                    continue  # null-safety (BUSINESS_RULES.md SS2.2 ②)
                if cell_name.startswith("NB-") or cell_name.startswith("MBF_") or cell_name.startswith("VNP-"):
                    continue  # VNP- = operator khac (Viettel) (BUSINESS_RULES.md SS2.2 ③)
                if not co_dang_dn_nokia(cell_id):
                    # === CELL NGOAI PHAM VI CDS QUAN LY (sua 07092026) ===
                    # CDS tra cell_id dang PHANG (chinh la cell_name, vd
                    # "4G-PYN015M12-VPC") thay vi DN Nokia. Do CHINH LA tin
                    # hieu CDS dang noi "toi khong quan ly cell nay" - khong
                    # phai du lieu hong.
                    #
                    # Truoc 07/09 code coi day la loi va de extract_lnbts()
                    # nem ValueError -> HTTP 500 cho ca request. Do la HIEU SAI
                    # y nghia: dung ra phai xu nhu VNP- (operator khac) o tren
                    # - ngoai pham vi thi BO QUA.
                    #
                    # Do that: tram 112391 (NOKIA, Ha Noi) CDS tra 6 cell, 3
                    # DN Nokia + 3 phang, trong do "4G-PYN015M12-VPC" (Vinh
                    # Phuc) lam vo ca preview. KHONG phai loi rieng Huawei -
                    # moi tram GIAP RANH TINH deu dinh.
                    #
                    # VIET LAI 27/09/2026 (Giai doan 1 buoc 2) - doan cu o day
                    # de ten "KHONG doi chieu hau to tinh voi NETACT_SERVERS"
                    # de bi hieu nham la cam DUNG hau to ten cho DINH TUYEN
                    # OSS - SAI, 2 chuyen KHAC NHAU:
                    #   - O DAY (Nhanh A): loai cell THEO VENDOR - cell_id
                    #     phang la tin hieu "CDS khong quan ly cell nay" (vd
                    #     cell Huawei "-VPC" nam canh tram NSN "-HNI" dang xet),
                    #     KHONG lien quan tinh cu/moi. Da can nhac VA BAC BO
                    #     suy hau to LAM DIEU KIEN LOAI o day: cell_infor co 8
                    #     dong "-VPC" tren 27.763 -> neu dung hau to de loai se
                    #     loai NHAM ca cell that su quan ly duoc (rieng ve
                    #     VENDOR, khong phai ve tinh).
                    #   - DINH TUYEN OSS (application/trigger_cr_use_case.py,
                    #     domain/services/oss_routing.py) LAI DUNG hau to ten
                    #     cell lam ma tinh cu - day la CAU HOI KHAC ("cell nay
                    #     gui SSH len OSS nao"), va da xac nhan hau to SACH
                    #     100% (456/456 cell that dung mau) cho DUNG MUC DICH
                    #     NAY - khac han "8/27.763" cua cau hoi vendor o tren.
                    # Tom lai: hau to ten VAN KHONG dung de LOAI cell o day,
                    # nhung VAN dung de DINH TUYEN o buoc khac - 2 quyet dinh
                    # khong mau thuan nhau vi tra loi 2 cau hoi khac nhau.
                    logger.warning(
                        "Cell ngoai pham vi CDS quan ly (cell_id khong phai DN Nokia) - bo qua",
                        extra={"cell_name": cell_name, "cell_id": cell_id},
                    )
                    if ngoai_pham_vi is not None and cell_name not in ngoai_pham_vi:
                        ngoai_pham_vi.append(cell_name)
                    if ngoai_pham_vi_chi_tiet is not None and cell_name not in {
                        d["cell_name"] for d in ngoai_pham_vi_chi_tiet
                    }:
                        ngoai_pham_vi_chi_tiet.append({"cell_name": cell_name, "ly_do": LY_DO_CELL_ID_PHANG})
                    continue
                lncel_local_id = cell_id.rsplit("LNCEL-", 1)[-1]
                if lncel_local_id.startswith("2"):
                    continue
                if tram_goc_id is not None and extract_lnbts(cell_id) == tram_goc_id:
                    # Cell cua CHINH tram goc - tram tat thi cell cua no cung
                    # tat, khong tinh la "bi anh huong" rieng can danh gia
                    # (xac nhan nghiep vu 22072026, tram 111139 co 3 cell
                    # dang STY008xx roi vao truong hop nay).
                    continue

                # Small cell (quyet dinh 02/10/2026, pham vi MOI thay cho ban
                # dau "chi CR") - loai KHOI CA danh gia QoS/QoE + xuat phieu
                # (Nhanh A nay) LAN chay CR (Nhanh B). Dat o DAY - gate CUOI
                # CUNG truoc khi vao result - de CHI loai cell da qua moi dieu
                # kien hop le khac, giong cau truc check CELL_ID_PHANG o tren.
                loai_tram = loai_tram_tu_ten_cell(cell_name)
                if loai_tram in LOAI_TRAM_SMALL_CELL:
                    logger.info(
                        "Cell la small cell (loai tram=%s) - loai khoi CA danh gia lan CR",
                        loai_tram,
                        extra={"cell_name": cell_name},
                    )
                    if ngoai_pham_vi is not None and cell_name not in ngoai_pham_vi:
                        ngoai_pham_vi.append(cell_name)
                    if ngoai_pham_vi_chi_tiet is not None and cell_name not in {
                        d["cell_name"] for d in ngoai_pham_vi_chi_tiet
                    }:
                        ngoai_pham_vi_chi_tiet.append({"cell_name": cell_name, "ly_do": LY_DO_SMALL_CELL})
                    continue

                seen_cell_names.add(cell_name)
                result.append(
                    Cell(
                        cell_id=cell_id,
                        cell_name=cell_name,
                        dist_name=cell_id,
                        priority=c.get("priority", 0),
                        # huong_id RAW tu CDS (KHONG qua guard/suy tu ten nhu
                        # Nhanh B) - Nhanh A khong chon 1 huong dai dien cho
                        # cell (1 cell co the o nhieu huong khac nhau), gia
                        # tri nay CHI de tham khao, co the None (CDS tra null
                        # cho nhom huong ten "W...").
                        huong_id=str(huong_id_cds) if huong_id_cds is not None else None,
                        action_type="",  # Nhanh A khong gan action_type - chi
                                          # Nhanh B (qua priority_assigner.py)
                                          # moi can dieu chinh rsboost/qrxlevmin
                        status=c["status"],
                    )
                )

        # Gan sector SAU KHI toan bo raw_huongs da duoc quet het - xem chu y
        # "1 PASS RIENG" o dau ham.
        for cell in result:
            cell.sector = cell_sector_min.get(cell.cell_name)
        return result

    def filter_for_cr(
        self,
        raw_huongs: list[dict],
        tram_goc_id: str | None = None,
        affected_cells: list[Cell] | None = None,
        cell_ngoai_pham_vi: list[str] | None = None,
        cell_ngoai_pham_vi_chi_tiet: list[dict] | None = None,
    ) -> list[Cell]:
        # Nhanh B - loc TIEP tu Nhanh A theo huong+band+rank, ra danh sach
        # cell THAT SU dieu chinh rsboost/qrxlevmin. Tai dung filter_affected()
        # de lay tap cell_name hop le (dedup + prefix/null + loai tram goc),
        # KHONG viet lai 4 dieu kien do o day - tranh 2 noi cung 1 logic loc
        # co the lech nhau ve sau.
        #
        # affected_cells (them V-item7, 09/2026): CHO PHEP caller TRUYEN SAN
        # ket qua filter_affected() da tinh TRUOC do, thay vi ham nay tu goi
        # lai filter_affected() ben trong. LY DO: _prepare_plan()
        # (application/trigger_cr_use_case.py) da goi filter_affected() RIENG
        # de lay Nhanh A (affected_cells cho preview) TRUOC khi goi ham nay -
        # neu khong truyen lai ket qua do, filter_affected() se CHAY LAN 2
        # tren CUNG raw_huongs, va moi cell "ngoai pham vi" bi logger.warning()
        # 2 LAN cho 1 request (BUG THAT). Khong truyen (test/caller cu goi
        # filter_for_cr() doc lap) thi tu tinh nhu truoc, HANH VI LOC khong doi.
        #
        # cell_ngoai_pham_vi/cell_ngoai_pham_vi_chi_tiet (quyet dinh 02/10/2026,
        # small cell): out-param CUNG CO CHE voi ngoai_pham_vi/ngoai_pham_vi_chi_tiet
        # cua filter_affected() - caller (trigger_cr_use_case.py) truyen VAO
        # CUNG 2 list da dung cho filter_affected()/_chon_oss_va_loc_cells(), de
        # MOI ly do loai cell (CELL_ID_PHANG, SMALL_CELL, TEN_CELL_SAI_MAU,
        # OSS_CHUA_CAU_HINH) gom chung vao 1 bao cao duy nhat. Khong truyen
        # (None) thi bo qua buoc ghi bao cao, HANH VI LOC small cell van chay.
        #
        # SUA 02/10/2026 - khi TU goi filter_affected() o day (affected_cells
        # khong duoc truyen vao), PHAI chuyen tiep ca cell_ngoai_pham_vi/
        # cell_ngoai_pham_vi_chi_tiet xuong CUNG loi goi: neu khong, ly do
        # SMALL_CELL (hoac CELL_ID_PHANG) phat sinh BEN TRONG filter_affected()
        # se bi "mat" (Nhanh A tu loai cell khoi affected_names, nhung khong
        # ai duoc bao de ghi ly do vao danh sach cua filter_for_cr()) - BUG
        # THAT phat hien qua test (goi filter_for_cr() doc lap kem 2 out-param
        # nhung KHONG truyen affected_cells, ky vong thay SMALL_CELL ma khong
        # thay vi truoc day thieu dong nay).
        if affected_cells is None:
            affected_cells = self.filter_affected(
                raw_huongs,
                tram_goc_id,
                ngoai_pham_vi=cell_ngoai_pham_vi,
                ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet,
            )
        affected_names = {c.cell_name for c in affected_cells}

        # --- Buoc 1: loc field ky thuat co ban (GIU LAI theo chi dinh) ---
        huong_cells: dict[int, list[dict]] = {}
        for huong in raw_huongs:
            # CAP NHAT 21072026: suy huong_id tu huong_name (vi tri co dinh)
            # thay vi doc truc tiep field huong_id CDS tra ve - guard cu
            # "if huong_id is None: continue" loai oan toan bo nhom ten "W..."
            # (BUG THAT tram 111139: 11/13 huong bi loai). Xem CAP NHAT
            # 21072026 o dau file.
            huong_id_from_name = _extract_huong_id_from_name(huong.get("huong_name", ""))
            if huong_id_from_name is None:
                continue  # da log canh bao trong _extract_huong_id_from_name()

            huong_id_cds = huong.get("huong_id")
            if huong_id_cds is not None and huong_id_cds != huong_id_from_name:
                # huong_id CDS khong dang tin (co the null hoac sai) - TEN la
                # nguon chuan theo xac nhan nghiep vu, chi canh bao de biet co
                # lech, KHONG dung gia tri CDS.
                logger.warning(
                    "huong_id CDS lech voi huong_id suy tu huong_name - dung "
                    "gia tri tu TEN: huong_name=%s, huong_id_cds=%s, "
                    "huong_id_from_name=%s",
                    huong.get("huong_name"), huong_id_cds, huong_id_from_name,
                )
            huong_id = huong_id_from_name

            if huong_id in huong_cells:
                continue  # duplicate huong_id trong raw response - giu entry dau (BUSINESS_RULES.md SS2.3, first-wins)
            huong_cells[huong_id] = [
                c for c in huong.get("cells", [])
                if c.get("technology") == "4G" and c.get("status") == "active"
            ]

        # --- Buoc 2: gom huong_id theo SECTOR Y=huong_id%10 cua TRAM TAT -
        # SUA 03/10/2026: KHONG con loc/chon 1 huong "thang" theo band o day
        # nua (xem CAP NHAT 03/10/2026 dau file) - MOI huong_id cua sector deu
        # dong gop ung vien o Buoc 3, khong gioi han so luong sector.
        by_sector: dict[int, list[int]] = {}
        for huong_id in huong_cells:
            y = huong_id % 10
            by_sector.setdefault(y, []).append(huong_id)

        # --- Buoc 3: gop ung vien cua MOI huong trong 1 sector, cell trung
        # ten (xuat hien o >=2 huong cung sector - du lieu that tram 160008)
        # giu ban priority NHO NHAT. Xu ly huong_id theo thu tu BAND_PRIORITY
        # (1>3>5>4) TRUOC khi gop: vua la thu tu "ai gop truoc", vua la
        # tie-break TU NHIEN khi 2 huong cho CUNG 1 cell CUNG priority (giu
        # ban dau tien, tu huong uu tien band cao hon) - 1 co che dung cho CA
        # 2 yeu cau, khong can code rieng 2 lan. Chi gop cell DA qua Nhanh A
        # (affected_names) - thay the Buoc 3 cu (loai cell khong hop le).
        #
        # Moi ung vien giu them "_huong_id_nguon" (huong_id THAT SU dong gop
        # ban duoc giu, co the khac huong_id dang duyet neu ban cu tot hon) -
        # dung o Buoc 4 (tie-break band khi sap) va gan vao Cell.huong_id ket
        # qua (chi de hien thi, KHONG con dung de gom nhom - xem Cell.sector).
        candidates_by_sector: dict[int, dict[str, dict]] = {}
        for y, huong_ids in by_sector.items():
            huong_ids_sorted = sorted(huong_ids, key=lambda hid: BAND_PRIORITY.get(hid // 10, 99))
            candidates: dict[str, dict] = {}
            for huong_id in huong_ids_sorted:
                for c in huong_cells[huong_id]:
                    cell_name = c.get("cell_name")
                    if cell_name not in affected_names:
                        continue
                    existing = candidates.get(cell_name)
                    if existing is None or c["priority"] < existing["priority"]:
                        candidates[cell_name] = {**c, "_huong_id_nguon": huong_id}
            candidates_by_sector[y] = candidates

        # --- Buoc 3b: loc band CUA CELL (^[13][0-9]$, SUA 03/10/2026 - thay
        # the hoan toan loc band-theo-huong cu) + small cell (loai nhu cu,
        # GIU NGUYEN vi tri: TRUOC Buoc 4 chon toi da MAX_CELLS_PER_HUONG, de
        # khong chiem mat 1 suat cua cell macro xep hang ke tiep). CHI anh
        # huong Nhanh B - filter_affected() (Nhanh A) KHONG goi buoc nay.
        for y, candidates in candidates_by_sector.items():
            con_lai: dict[str, dict] = {}
            for cell_name, c in candidates.items():
                band = band_tu_lncel(c["cell_id"])
                if band is None:
                    if cell_ngoai_pham_vi is not None and cell_name not in cell_ngoai_pham_vi:
                        cell_ngoai_pham_vi.append(cell_name)
                    if cell_ngoai_pham_vi_chi_tiet is not None and cell_name not in {
                        d["cell_name"] for d in cell_ngoai_pham_vi_chi_tiet
                    }:
                        cell_ngoai_pham_vi_chi_tiet.append({"cell_name": cell_name, "ly_do": LY_DO_BAND_KHONG_CHAY_CR})
                    continue
                if loai_tram_tu_ten_cell(cell_name) in LOAI_TRAM_SMALL_CELL:
                    if cell_ngoai_pham_vi is not None and cell_name not in cell_ngoai_pham_vi:
                        cell_ngoai_pham_vi.append(cell_name)
                    if cell_ngoai_pham_vi_chi_tiet is not None and cell_name not in {
                        d["cell_name"] for d in cell_ngoai_pham_vi_chi_tiet
                    }:
                        cell_ngoai_pham_vi_chi_tiet.append({"cell_name": cell_name, "ly_do": LY_DO_SMALL_CELL})
                    continue
                con_lai[cell_name] = {**c, "_band": band}
            candidates_by_sector[y] = con_lai

        # --- Buoc 4: sap theo (priority, BAND_PRIORITY cua huong nguon) -
        # cung co che tie-break voi Buoc 3 (huong uu tien band cao hon thang
        # khi priority bang nhau), chon toi da MAX_CELLS_PER_HUONG/sector,
        # dedup XUYEN SECTOR (sector nho hon xu ly TRUOC va giu quyen - sort Y
        # tang dan, cell da CHON o sector truoc bi BO QUA (khong tinh vao suat
        # da chon) o sector sau, giong y het co che dedup xuyen huong cu).
        result: list[Cell] = []
        seen_cell_names: set[str] = set()
        for y in sorted(candidates_by_sector):
            sorted_cells = sorted(
                candidates_by_sector[y].values(),
                key=lambda c: (c["priority"], BAND_PRIORITY.get(c["_huong_id_nguon"] // 10, 99)),
            )
            picked = 0
            for c in sorted_cells:
                if picked >= MAX_CELLS_PER_HUONG:
                    break
                if c["cell_name"] in seen_cell_names:
                    continue
                result.append(
                    Cell(
                        cell_id=c["cell_id"],
                        cell_name=c["cell_name"],
                        dist_name=c["cell_id"],  # cung 1 format tu CDS (xem Cell entity)
                        priority=c["priority"],
                        huong_id=str(c["_huong_id_nguon"]),
                        action_type="",  # priority_assigner.py gan sau
                        status=c["status"],
                        sector=y,
                        band=c["_band"],
                    )
                )
                seen_cell_names.add(c["cell_name"])
                picked += 1

        return result
