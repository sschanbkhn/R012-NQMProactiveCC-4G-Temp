"""
phan_lop_delaunay() - phan lop tram xung quanh 1 tram X thanh L1 (lang gieng
TRUC TIEP)/L2 (lang gieng cua L1) bang GOP CUM SITE + tam giac hoa Delaunay +
loc canh dai. Tu: quyet dinh 06-08/10/2026 (BO CDS, thay bang HO that +
Delaunay) + quyet dinh 08/10/2026 (SUA sau review thiet ke: gop cum, moc loc
canh theo X, fallback khi X khong co canh, doi ten co TOA_DO_NGHI_SAI ->
HO_DI_XA) + quyet dinh 08/10/2026 lan 2 (XU LY TRAM TOA DO DUNG CHUNG/CRAN) -
xem docs/BUSINESS_RULES.md.

HAM THUAN (khong I/O, khong goi DB) - nhan san danh sach toa do tram (caller/
adapter tu doc tu bang tram), tra ve danh sach da phan lop. Deterministic:
cung dau vao luon ra cung ket qua.

=== VI SAO DUNG numpy/scipy O DAY (domain/) ===
Quy tac BAT BUOC cua du an (docs/ARCHITECTURE.md Section 9) CHI cam domain/
import fastapi/sqlmodel/httpx/paramiko (cac thu vien GAN VOI I/O/framework cu
the). numpy/scipy la thu vien TINH TOAN THUAN, CUNG nhom voi math/statistics
cua stdlib ve ban chat - KHONG vi pham tinh than "domain doc lap ha tang".

=== PHAN LOAI TOA DO: TIN_CAY vs TOA_DO_DUNG_CHUNG (THEM 08/10/2026 lan 2,
    yeu cau truc tiep user, dua tren khao sat scripts/kiem_gia_thuyet_cran.py) ===
BANG CHUNG: 5.396 tram (9,0% ca nuoc)/652 tram (10,5% HNI) trung toa do (6 so
le) VOI tram KHAC so site (vd 4G-CGY029B-HNI trung toa do voi mot tram
4G-XYZ999M-HNI nao do). Doi chieu HO THAT: 73,3% cac cap "khac site, cung toa
do" nay gan nhu KHONG co handover qua lai (HO < 1%) - CHUNG MINH toa do RIMS
dang ghi theo NOI DAT BASEBAND/CRAN (1 noi dat vat ly phuc vu nhieu "site"
logic), KHONG PHAI vi tri anten that - toa do nay KHONG dung duoc lam moc
hinh hoc cho Delaunay.

LUAT PHAN LOAI (phan_loai_toa_do(), ham THUAN, goi 1 LAN cho ca tap tram lien
quan - KHONG phu thuoc tram X dang xet):
  1. Nhom tram theo toa do (lam tron 6 so le).
  2. Nhom chi 1 tram (khong trung toa do ai) -> TIN_CAY (khong co gi mau thuan).
  3. Nhom >= 2 tram: so sanh SO SITE tach tu ten (ham _so_site(), DUNG LAI
     chinh xac regex da mo rong qua khao sat CRAN):
     - Ten KHONG tach duoc so site (khong khop regex) -> TOA_DO_DUNG_CHUNG
       NGAY (than trong - khong co co so xac nhan la "cung site" voi ai).
     - Ten tach duoc so site: neu TOAN BO cac tram KHAC trong nhom (co tach
       duoc so site) co CUNG so site -> TIN_CAY (vd 4G-CGY029M-HNI/
       4G-CGY029B-HNI - 2 tram CUNG 1 site vat ly, nhieu thiet bi). Neu co
       BAT KY tram nao trong nhom mang so site KHAC -> TOA_DO_DUNG_CHUNG (du
       voi 1 tram KHAC CO THE trung so site voi minh - vi "co it nhat 1 tram
       khac site cung dung toa do nay" da du de ket luan toa do nay KHONG
       CON RIENG CHO 1 site, tuc KHONG dung tin cay duoc).

TAC DONG: TramDiem KHONG CON field ma_csht (luat gop cum cu theo ma_csht BI
THAY THE HOAN TOAN boi luat gop theo SO SITE ben duoi - ma_csht khong con y
nghia o day).

=== GOP CUM SITE (SUA 08/10/2026 lan 2 - THAY luat cu theo ma_csht) ===
TRUOC (08/10/2026 lan 1): gop cum theo ma_csht trung + khoang cach. NAY: gop
cum THUAN theo SO SITE (tach tu ten) CHO CAC TRAM TIN_CAY - vi khao sat CRAN
cho thay ma_csht/toa do khong con la tin hieu du tin cay khi ca site lien
quan la "toa do dung chung" (baseband); so site (van ban, on dinh, KHONG phu
thuoc GPS) la tin hieu dung de xac dinh "cac tram nay la 1 site vat ly".
  - TRAM TOA_DO_DUNG_CHUNG BI LOAI HOAN TOAN khoi tap diem dua vao Delaunay
    (ca khi la X - tra ve [] ngay - VA khi la ung vien, xem buoc loc duoi).
  - Cac tram TIN_CAY con lai duoc gop thanh 1 cum NEU CUNG so site (khop
    _so_site()); ten khong tach duoc so site nhung la TIN_CAY (nghia la KHONG
    trung toa do ai - xem luat phan loai) luon la cum DON (khong co gi de gop).

=== MOC LOC CANH DAI (SUA 08/10/2026 lan 1, SUA LAN 2 14/10/2026) ===
08/10/2026 lan 1: nguong = ALPHA x TRUNG VI khoang cach lang gieng gan nhat
CUA TOAN BO diem trong bubble 15km (khong rieng X) - lam nguong qua "trung
binh hoa", khong phan anh dung mat do CUC BO quanh X (vd X o vung thua
nhung bubble co 1 cum dong o xa van keo trung vi xuong). SUA THANH: nguong =
ALPHA x TRUNG VI do dai CAC CANH NOI TRUC TIEP VOI X (truoc khi loc).

BUG MOI (14/10/2026, yeu cau truc tiep user, phat hien qua tram that
240091/4G-TUN009M-LCU, NA14, vung nui doc QL12): cach "sua lan 1" lai sai
theo huong NGUOC LAI khi X CHINH NO co 1-2 hang xom SIEU GAN (vd 0,55km/
0,74km/0,79km - thuong gap o vung tram xep DOC THUNG LUNG/duong QL, mat do
RAT KHONG DEU). TRUNG VI CANH CUA RIENG X (0,79km) bi mau nhung canh sieu
gan nay KEO XUONG THAP HON HAN mat do THAT cua CA VUNG (trung vi TOAN BO
canh Delaunay trong bubble 15km = 3,58km, gap ~4,5 lan) - nguong 3 x 0,79 =
2,38km QUA NHO, CAT OAN 1 canh toi hang xom THAT (4G-TUN008M-LCU, 3,18km, o
huong dang thua tram) le ra van NAM TRONG mat do binh thuong cua vung (so
voi nguong DUNG se la 3 x 3,58 = 10,75km).

SUA LAN 2: nguong = ALPHA x TRUNG VI MOI CANH Delaunay TRONG VUNG 15km
QUANH X (tat ca canh cua do thi tam giac hoa tren cac dai dien cum, KHONG
CHI rieng canh cua X) - phan anh mat do TRUNG BINH cua CA KHU VUC dia ly
quanh X (on dinh, khong bi lam sai lech boi may hang xom DAC BIET GAN cua
rieng 1 minh X), thay vi mat do CUC BO chi tai X (de bi "nhieu" boi vai
diem ngoai le sieu gan/sieu xa ngay canh X).

=== LOC THEO TAM GIAC (ALPHA SHAPE CHUAN), KHONG LOC THEO TUNG CANH RIENG
    (SUA 14/10/2026, yeu cau truc tiep user) ===
TRUOC: loc TUNG CANH rieng le (canh dai > nguong thi xoa, GIU LAI 2 canh con
lai neu chung ngan hon nguong) - co the vo tinh GIU LAI 1 TAM GIAC "MANH"
(thon dai) noi qua VUNG TRONG LON (bien, bien gioi, song rong) neu 2 trong 3
canh cua no NGAN hon nguong du canh con lai rat dai - SAI vi tam giac do VAN
noi X voi 1 diem o XA qua 1 "CAU" hinh hoc gia tao (2 canh ngan chi vi 2 dinh
con lai cua tam giac o GAN NHAU, khong phan anh X THAT SU gan vung do).
NAY: tinh BAN KINH DUONG TRON NGOAI TIEP cua TUNG TAM GIAC (simplex) trong
ket qua tam giac hoa Delaunay; tam giac co ban kinh ngoai tiep > nguong bi
LOAI CA TAM GIAC (ca 3 canh, khong xet rieng tung canh) - dung dinh nghia
ALPHA SHAPE chuan (Edelsbrunner 1983): 1 tam giac "manh" (vd gan thang hang,
hoac rat lon) LUON co ban kinh ngoai tiep LON bat ke do dai tung canh rieng
le, nen bi loai TRON VEN - dung hieu ung mong muon "canh noi qua vung trong
lon bi bo" ke ca khi tam giac do co 1-2 canh ngan.
Cong thuc: R = (a*b*c) / (4*Area) voi a,b,c la 3 canh, Area dien tich tam
giac (qua tich co huong 2D). Tam giac suy bien (3 diem gan nhu thang hang,
Area~=0) -> R = vo cuc (loai chac chan, "manh" toi muc khong con y nghia
hinh hoc tam giac that).

=== FALLBACK KHI X KHONG CO CANH (THEM 08/10/2026 lan 1) ===
Neu khong du diem de tam giac hoa (< 4 diem phan biet) HOAC X bi co lap
hoan toan trong do thi Delaunay (0 canh truoc khi loc - hiem, nhung co the
xay ra voi hinh hoc suy bien) -> KHONG tra ve rong nhu truoc (da gay 11,8%
tram "L1=0, L2=0" trong khao sat scripts/dieu_tra_toa_do_nghi_sai.py). Thay
bang: xep hang TOAN BO cum (ngoai cum cua X) theo khoang cach toi X, 6 cum
GAN NHAT = L1, 12 cum TIEP THEO = L2.

=== DOI TEN CO (THEM 08/10/2026 lan 1) ===
TOA_DO_NGHI_SAI -> HO_DI_XA: khao sat scripts/dieu_tra_toa_do_nghi_sai.py
(24,7% tram bi co, phan lon do DO THI DELAUNAY QUA THUA chu KHONG PHAI toa
do sai that) cho thay ten cu quy ket SAI nguyen nhan - "HO_DI_XA" trung lap
voi QUAN SAT THAT (HO handover di xa ve mat hinh hoc hien tai), KHONG khang
dinh nguyen nhan la loi toa do. LUAT KICH HOAT GIU NGUYEN (xem
domain/services/ho_cell_selector.py).

=== L1/L2 CHI TINH VOI TRAM MACRO + KHAC (THEM 12/10/2026, yeu cau truc tiep
    user, quyet dinh 12/10/2026) ===
Tap diem Delaunay/gop cum site BO HET tram IBS/SMALL_CELL (domain/services/
loai_tram.py::loai_tram_tu_ten_tram()) - 2 loai nay KHONG dung lam moc hinh
hoc cho L1/L2 cua AI CA (ca lam X lan lam ung vien), vi vung phu cua chung
KHONG tuan theo gia dinh "khoang cach gan = lang gieng RF that" ma Delaunay
dua vao (IBS phu TRONG NHA, small cell phu 1 DIEM NONG CUC BO - ca 2 co the
RAT GAN X ve toa do THO nhung khong lien quan gi ve mat vo tuyen). KHAC van
GIU (da xac nhan qua khao sat la DA SO macro ten khong chuan, xem loai_tram.py)
- loai KHAC se lam mat qua nhieu diem that su la macro, sai huong nguoc lai.
X la IBS -> tra ve [] NGAY (step 0, GIONG X la TOA_DO_DUNG_CHUNG ve mat KET
QUA ham nay, tuy KHAC NHAU ve NGUYEN NHAN - xem dac ta "X LA IBS" day du o
domain/services/ho_cell_selector.py, noi X-IBS con duoc xu ly THEM o buoc
chon B/gating, khong chi o day).
"""

import re
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import numpy as np
from scipy.spatial import Delaunay

from domain.services.loai_tram import _MA_KHU_VUC, NHOM_IBS, NHOM_KHAC, NHOM_MACRO, loai_tram_tu_ten_tram

EARTH_R_KM = 6371.0088

ALPHA_MAC_DINH = 3.0
BAN_KINH_KM_MAC_DINH = 15.0

_SO_DIEM_TOI_THIEU_TAM_GIAC_HOA = 4
_SO_CUM_FALLBACK_L1 = 6
_SO_CUM_FALLBACK_L2 = 12

TIN_CAY = "TIN_CAY"
TOA_DO_DUNG_CHUNG = "TOA_DO_DUNG_CHUNG"

# THEM 16/10/2026 (yeu cau truc tiep user, "VONG L1 KHONG LAY TRAM CUNG SITE")
# - truoc day tram CUNG SITE voi X (vd "4G-DPG063E-HNI" cung so site voi X
# "4G-DPG063M-HNI") duoc gan THANG layer="L1" (dung chung voi L1 THAT suy tu
# Delaunay) - khien duong_bao_hinh_sao() (ve "vong" L1 tren ban do) GOM NHAM
# ca diem cung site (lat/lon THUONG trung X het - khong co y nghia hinh hoc
# de ve vong). TACH RIENG layer "L1_CUNG_SITE": VAN la L1 ve mat THUAT TOAN
# chon cell (khong doi B/A/vung Z - xem domain/services/ho_cell_selector.py
# cho moi cho dung "L1" phai cong them gia tri nay), CHI khac o 2 noi HIEN
# THI: (1) application/trigger_cr_use_case.py loai KHOI danh sach dua vao
# duong_bao_hinh_sao() (l1_vong.danh_sach), (2) layer tra ve cho TUNG CELL
# cua tram nay la "L1_CUNG_SITE" (FE hien "L1 (cung site)") thay vi "L1" -
# giup nguoi xem phan biet duoc "lang gieng hinh hoc that" voi "chi la sector
# khac cua CHINH tram X".
L1_CUNG_SITE = "L1_CUNG_SITE"

# Regex tach SO SITE tu ten tram (vd "4G-CGY029B-HNI" -> "CGY029"). DUNG LAI
# NGUYEN VAN tu scripts/kiem_gia_thuyet_cran.py (da mo rong 08/10/2026 de
# khop ca tien to UL_/UL-/LN-/SN- - xem khao sat, giam 51,7% -> 4,1% cap
# "khong xac dinh duoc so site").
#
# SUA 15/10/2026 (yeu cau truc tiep user, "SUA TIEP _SITE_RE") - mau CU doi
# ma khu vuc la [A-Z]{2,4} (CHU THUAN), nen tram HCM dang "Q01"/"Q08" (ma
# quan, chu+so - vd "4G-Q01219M-HCM") KHONG tach duoc so site -> bi coi la
# "khong xac dinh" -> neu trung toa do voi tram khac se BI OAN thanh
# TOA_DO_DUNG_CHUNG (CRAN) dung ra la CUNG 1 site that. DUNG CHUNG _MA_KHU_VUC
# voi domain/services/loai_tram.py (KHONG viet regex rieng) - cung 1 dinh
# nghia "ma khu vuc 3 ky tu, dau la chu, 2 sau la chu hoac so" o CA 2 noi.
_SITE_RE = re.compile(rf"^[A-Za-z0-9]+[-_]({_MA_KHU_VUC}[0-9]+)[A-Z][-_][A-Z]{{3}}$")


def _so_site(tram_name: str) -> str | None:
    m = _SITE_RE.match(tram_name)
    return m.group(1) if m else None


@dataclass(frozen=True)
class TramDiem:
    """1 tram kem toa do - dau vao cua phan_lop_delaunay()/phan_loai_toa_do()."""

    tram_id: str
    tram_name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class TramPhanLop:
    """1 tram da duoc xep lop (L1 hoac L2), kem khoang cach that toi X."""

    tram_id: str
    tram_name: str
    lat: float
    lon: float
    km: float
    layer: str  # "L1" | "L1_CUNG_SITE" | "L2" - xem dac ta L1_CUNG_SITE dau file


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2r - lat1r, lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * asin(sqrt(a))


def _toa_do_hop_le(d: TramDiem) -> bool:
    # Bo lat/long rong HOAC bang 0 (dac ta 06-08/10/2026) - (0,0) la "null
    # island" ngoai khoi Phi, KHONG PHAI toa do that o VN.
    return d.lat is not None and d.lon is not None and not (d.lat == 0 and d.lon == 0)


def phan_loai_toa_do(tram_list: list[TramDiem]) -> dict[str, str]:
    """Tra {tram_id: TIN_CAY|TOA_DO_DUNG_CHUNG} cho MOI tram co toa do hop le
    trong tram_list (tram toa do rong/0,0 KHONG co trong ket qua - khong co
    gi de phan loai). Xem dac ta LUAT PHAN LOAI dau file. Goi 1 LAN cho toan
    bo tap tram lien quan (KHONG phu thuoc tram X dang xet rieng le nao)."""
    hop_le = [t for t in tram_list if _toa_do_hop_le(t)]
    nhom: dict[tuple[float, float], list[TramDiem]] = {}
    for t in hop_le:
        nhom.setdefault((round(t.lat, 6), round(t.lon, 6)), []).append(t)

    ket_qua: dict[str, str] = {}
    for thanh_vien in nhom.values():
        if len(thanh_vien) == 1:
            ket_qua[thanh_vien[0].tram_id] = TIN_CAY
            continue
        cac_site_xac_dinh = {s for t in thanh_vien if (s := _so_site(t.tram_name)) is not None}
        dong_nhat = len(cac_site_xac_dinh) <= 1
        for t in thanh_vien:
            site_t = _so_site(t.tram_name)
            ket_qua[t.tram_id] = TIN_CAY if (site_t is not None and dong_nhat) else TOA_DO_DUNG_CHUNG
    return ket_qua


def _gop_cum_site(diem: list[TramDiem]) -> list[list[int]]:
    """Gop danh sach diem (INDEX trong `diem`) thanh cac CUM theo SO SITE
    (xem GOP CUM SITE dau file). Tat ca diem dua vao day duoc gia dinh la
    TIN_CAY (TOA_DO_DUNG_CHUNG da bi loc tu truoc, xem phan_lop_delaunay()).
    Ten khong tach duoc so site -> cum DON (khong gop voi ai)."""
    nhom: dict[str, list[int]] = {}
    for i, d in enumerate(diem):
        site = _so_site(d.tram_name)
        khoa = site if site is not None else f"__don__{i}"
        nhom.setdefault(khoa, []).append(i)
    return list(nhom.values())


def _ban_kinh_ngoai_tiep(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> float:
    """Ban kinh duong tron ngoai tiep tam giac (p0,p1,p2) - cong thuc
    R = (a*b*c)/(4*Area). Tam giac suy bien (gan thang hang, Area~=0) tra VO
    CUC (loai chac chan boi moi nguong huu han - xem dac ta ALPHA SHAPE dau
    file, THEM 14/10/2026)."""
    a = float(np.linalg.norm(p1 - p2))
    b = float(np.linalg.norm(p0 - p2))
    c = float(np.linalg.norm(p0 - p1))
    dien_tich_x2 = abs((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1]))
    if dien_tich_x2 < 1e-9:
        return float("inf")
    return (a * b * c) / (2 * dien_tich_x2)


def phan_lop_delaunay(
    x: TramDiem,
    ung_vien: list[TramDiem],
    phan_loai: dict[str, str],
    alpha: float = ALPHA_MAC_DINH,
    ban_kinh_km: float = BAN_KINH_KM_MAC_DINH,
) -> list[TramPhanLop]:
    """Tra danh sach L1+L2 (KHONG bao gom X, KHONG bao gom tram ngoai pham vi
    L1/L2 - nhung tram do la "vung Z" theo dinh nghia LOAI TRU: khong co trong
    ket qua tra ve == Z, xem domain/services/ho_cell_selector.py).

    phan_loai: ket qua phan_loai_toa_do() tren TOAN BO tap tram lien quan.

    0. X la TOA_DO_DUNG_CHUNG (hoac khong co toa do hop le) HOAC X la IBS
       (THEM 12/10/2026, yeu cau truc tiep user, GIONG X CRAN ve mat ket qua -
       xem dac ta rieng o domain/services/ho_cell_selector.py muc "X LA IBS")
       -> tra ve [] NGAY (khong tinh L1/L2).
    1. Loc ung_vien: bo toa do rong/0, bo trung tram_id voi X, BO CA tram
       TOA_DO_DUNG_CHUNG (loai hoan toan khoi tap diem - khong duoc lam moc
       hinh hoc cho ai); giu trong ban_kinh_km (tinh tu TOA DO THO, truoc gop
       cum - gop cum chi xap xi lai VI TRI, khong doi PHAM VI xet). THEM
       12/10/2026 (yeu cau truc tiep user, quyet dinh "L1/L2 CHI TINH VOI TRAM
       MACRO"): BO CA tram IBS/SMALL_CELL (domain/services/loai_tram.py) khoi
       tap diem - vung phu IBS (trong nha)/small cell (diem nong cuc bo) KHONG
       phan anh dung do GAN GEOGRAPHIC thuc su nhu macro, dua chung vao se lam
       SAI lech tam giac hoa (vd 1 IBS gan X ve khoang cach THO nhung phu vung
       hoan toan khac macro xung quanh). CHI giu MACRO va KHAC (KHAC da xac
       nhan qua khao sat la DA SO macro ten khong chuan - xem loai_tram.py).
    2. GOP CUM SITE (X + ung_vien con lai, TOAN BO da la TIN_CAY sau buoc 1).
       Tram CUNG CUM voi X -> L1_CUNG_SITE NGAY, khong qua Delaunay (THAT RA
       van la "L1" ve thuat toan chon cell - CHI tach rieng de hien thi, xem
       dac ta L1_CUNG_SITE dau file).
    3. < 4 cum phan biet (ke ca cum cua X) HOAC X khong co canh nao trong do
       thi Delaunay (truoc khi loc) -> FALLBACK: xep hang cac cum CON LAI
       theo khoang cach toi X, 6 cum gan nhat = L1, 12 cum tiep theo = L2.
    4. Nguoc lai: tam giac hoa Delaunay tren cac DAI DIEN cum (trung binh toa
       do cac thanh vien), xoa canh > ALPHA x TRUNG VI do dai cac canh NOI
       TRUC TIEP VOI X, suy L1/L2 tu do thi con lai.
    """
    if (
        not _toa_do_hop_le(x)
        or phan_loai.get(x.tram_id) == TOA_DO_DUNG_CHUNG
        or loai_tram_tu_ten_tram(x.tram_name) == NHOM_IBS
    ):
        return []

    ung_vien_hop_le = [
        d for d in ung_vien
        if _toa_do_hop_le(d) and d.tram_id != x.tram_id and phan_loai.get(d.tram_id) != TOA_DO_DUNG_CHUNG
        and loai_tram_tu_ten_tram(d.tram_name) in (NHOM_MACRO, NHOM_KHAC)
    ]
    trong_pham_vi = [d for d in ung_vien_hop_le if _haversine_km(x.lat, x.lon, d.lat, d.lon) <= ban_kinh_km]
    if not trong_pham_vi:
        return []

    # Buoc 2 - GOP CUM SITE (X + ung vien trong pham vi).
    tat_ca_diem = [x, *trong_pham_vi]
    cac_cum_idx = _gop_cum_site(tat_ca_diem)
    cum_cua_x = next(c for c in cac_cum_idx if 0 in c)  # index 0 luon la X

    ket_qua: list[TramPhanLop] = []
    for i in cum_cua_x:
        if i == 0:
            continue
        d = tat_ca_diem[i]
        km = _haversine_km(x.lat, x.lon, d.lat, d.lon)
        ket_qua.append(TramPhanLop(d.tram_id, d.tram_name, d.lat, d.lon, km, L1_CUNG_SITE))

    cac_cum_khac = [c for c in cac_cum_idx if c is not cum_cua_x]
    if not cac_cum_khac:
        return ket_qua

    def _trung_binh_toa_do(cum: list[int]) -> tuple[float, float]:
        return (
            sum(tat_ca_diem[i].lat for i in cum) / len(cum),
            sum(tat_ca_diem[i].lon for i in cum) / len(cum),
        )

    dai_dien_latlon = [_trung_binh_toa_do(c) for c in cac_cum_khac]

    # Buoc 3/4 - can >= 4 CUM phan biet (ke ca cum cua X) de tam giac hoa.
    if len(cac_cum_khac) + 1 < _SO_DIEM_TOI_THIEU_TAM_GIAC_HOA:
        ket_qua.extend(_fallback_6_12(x, cac_cum_khac, dai_dien_latlon, tat_ca_diem))
        return ket_qua

    lat0, lon0 = radians(x.lat), radians(x.lon)
    pts = [(0.0, 0.0)]
    for lat_d, lon_d in dai_dien_latlon:
        x_km = (radians(lon_d) - lon0) * EARTH_R_KM * cos(lat0)
        y_km = (radians(lat_d) - lat0) * EARTH_R_KM
        pts.append((x_km, y_km))
    pts_arr = np.array(pts)

    try:
        tri = Delaunay(pts_arr)
    except Exception:
        ket_qua.extend(_fallback_6_12(x, cac_cum_khac, dai_dien_latlon, tat_ca_diem))
        return ket_qua

    canh: set[tuple[int, int]] = set()
    for simplex in tri.simplices:
        for i in range(3):
            a, b = int(simplex[i]), int(simplex[(i + 1) % 3])
            canh.add((min(a, b), max(a, b)))

    IDX_X = 0
    canh_cua_x = [(a, b) for a, b in canh if a == IDX_X or b == IDX_X]
    if not canh_cua_x:
        # X bi co lap trong do thi Delaunay (hiem - hinh hoc suy bien).
        ket_qua.extend(_fallback_6_12(x, cac_cum_khac, dai_dien_latlon, tat_ca_diem))
        return ket_qua

    # SUA 14/10/2026 (yeu cau truc tiep user) - nguong tinh tren TRUNG VI MOI
    # CANH Delaunay trong vung (khong CHI rieng canh cua X) - xem dac ta "MOC
    # LOC CANH DAI, SUA LAN 2" dau file (tranh X co 1-2 hang xom sieu gan keo
    # trung vi CUA RIENG X xuong qua thap so voi mat do THAT ca vung).
    do_dai_tat_ca_canh = [float(np.linalg.norm(pts_arr[a] - pts_arr[b])) for a, b in canh]
    trung_vi_vung = float(np.median(do_dai_tat_ca_canh))
    nguong = alpha * trung_vi_vung

    # SUA 14/10/2026 - loc THEO TAM GIAC (alpha shape chuan: ban kinh duong
    # tron ngoai tiep > nguong thi loai CA tam giac), KHONG loc tung canh rieng
    # le - xem dac ta "LOC THEO TAM GIAC" dau file (tranh giu oan 1 "cau" hinh
    # hoc noi qua vung trong lon qua 2 canh ngan cua 1 tam giac thon dai).
    do_thi: dict[int, set[int]] = {i: set() for i in range(len(pts_arr))}
    for simplex in tri.simplices:
        p0, p1, p2 = pts_arr[simplex[0]], pts_arr[simplex[1]], pts_arr[simplex[2]]
        if _ban_kinh_ngoai_tiep(p0, p1, p2) > nguong:
            continue  # tam giac "manh o ria" - loai CA 3 canh cua no
        for i in range(3):
            a, b = int(simplex[i]), int(simplex[(i + 1) % 3])
            do_thi[a].add(b)
            do_thi[b].add(a)

    l1_idx = do_thi[IDX_X]
    l2_idx: set[int] = set()
    for a in l1_idx:
        l2_idx |= do_thi[a]
    l2_idx -= l1_idx
    l2_idx.discard(IDX_X)

    for idx, layer in [(i, "L1") for i in l1_idx] + [(i, "L2") for i in l2_idx]:
        cum = cac_cum_khac[idx - 1]  # idx=0 la X
        for i in cum:
            d = tat_ca_diem[i]
            km = _haversine_km(x.lat, x.lon, d.lat, d.lon)
            ket_qua.append(TramPhanLop(d.tram_id, d.tram_name, d.lat, d.lon, km, layer))

    return ket_qua


def _fallback_6_12(
    x: TramDiem, cac_cum_khac: list[list[int]], dai_dien_latlon: list[tuple[float, float]], tat_ca_diem: list[TramDiem]
) -> list[TramPhanLop]:
    """6 cum GAN X NHAT (ngoai cum cua X) -> L1, 12 cum tiep theo -> L2 (THEM
    08/10/2026 - xem "FALLBACK KHI X KHONG CO CANH" dau file)."""
    cum_voi_km = [
        (cum, _haversine_km(x.lat, x.lon, lat_d, lon_d))
        for cum, (lat_d, lon_d) in zip(cac_cum_khac, dai_dien_latlon)
    ]
    cum_voi_km.sort(key=lambda t: t[1])

    ket_qua: list[TramPhanLop] = []
    for i, (cum, _km_dai_dien) in enumerate(cum_voi_km):
        layer = "L1" if i < _SO_CUM_FALLBACK_L1 else "L2" if i < _SO_CUM_FALLBACK_L1 + _SO_CUM_FALLBACK_L2 else None
        if layer is None:
            break
        for idx in cum:
            d = tat_ca_diem[idx]
            km = _haversine_km(x.lat, x.lon, d.lat, d.lon)
            ket_qua.append(TramPhanLop(d.tram_id, d.tram_name, d.lat, d.lon, km, layer))
    return ket_qua
