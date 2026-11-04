"""
chon_cell_cr() - chon danh sach A (danh gia QoS/QoE, phieu) va B (chay CR)
cho 1 tram X, dua TREN DU LIEU HO (handover) THAT + phan lop dia ly Delaunay
(domain/services/ho_delaunay.py) - THAY THE HOAN TOAN CDS /cell/neighbors.
Tu: quyet dinh 06-08/10/2026 (BO CDS, yeu cau truc tiep user) + quyet dinh
08/10/2026 (SUA sau review thiet ke) - xem docs/BUSINESS_RULES.md ve day du
cac nguong + nguon so lieu (scripts/phan_tich_nguong_ho.py, chay tren toan
bo file NA09 ~3 trieu dong).

HAM THUAN (khong I/O) - nhan du lieu HO/phan lop/tram dich/ten cell DA DOC
SAN tu ben ngoai (repo/adapter), tra ve ket qua chon. KHONG goi DB, KHONG goi
CDS, KHONG noi vao XuatPhieuUseCase/TriggerCrUseCase hay bat ky router nao
(yeu cau truc tiep user "KHONG noi vao luong CR/xem truoc") - module nay
hien CHI duoc goi tu scripts/kiem_tra_thuat_toan_ho.py va test.

=== HANG SO CO TEN ===
  NGUONG_80_PCT=80%, TRAN_CELL_MOI_SECTOR=15, NGUONG_BO_1_PCT=1%,
  NGUONG_VUNG_Z_PCT=20%, NGUONG_VUNG_Z_SR=95%, NGUONG_HO_DI_XA_X_PCT=50%,
  HE_SO_KHOANG_CACH_DICH_HO_DI_XA=3 lan (khoang cach L1 trung vi cua X),
  N_MIN_HO_SECTOR=3156 (THEM 08/10/2026 - xem muc rieng duoi day),
  NGUONG_CELL_LON=10% (THEM 10/10/2026 - xem muc LUAT DANH SACH A duoi day).
  (ALPHA=3, ban_kinh=15km nam o ho_delaunay.py).

=== LUAT DANH SACH A - LAY THEM CELL LON (THEM 10/10/2026, yeu cau truc tiep
    user chot cung ngay) ===
Cong don 80% co the DUNG LAI NGAY SAU 1 cell lon (vd 83% chi voi 3 cell),
bo lai cell ke tiep van con % DANG KE (vd 11%, vuot han NGUONG_BO_1_PCT) chi
vi "may" dung dung luc cong don vua vuot nguong. Cell 11% do VAN la 1 phan
dang ke cua huong di HO, khong nen bi loai oan chi vi thu tu cong don. SAU
buoc cong-don-80%/tran-15 (giu NGUYEN, khong doi), QUET LAI phan "con lai"
(cac cell CHUA duoc giu, da sorted giam dan theo attempt tu truoc) va LAY
THEM moi cell co pct_trong_sector >= NGUONG_CELL_LON (10%) - van gioi han
boi TRAN_CELL_MOI_SECTOR (khong vuot 15 cell/sector du cong them).
Test: 41/30/12/11 (%) -> cong don dung o 83% (3 cell), 11% >= 10% -> LAY
THEM -> 4 cell. 41/30/12/9 -> 9% < 10% -> KHONG lay them -> 3 cell.

=== GIA DINH (CAN XAC NHAN NEU KHAC Y) ===
GD1. "%" dung trong luat vung Z (>=20%) VA trong buoc xep A (bo <1%, cong don
     80%) la CUNG 1 chi so: % cua cell TRONG SECTOR cua no (attempt cell /
     tong attempt CA sector SAU buoc loc a, TRUOC khi bo <1%) - KHAC voi
     "% TONG HO cua X" dung RIENG cho luat HO_DI_XA cua chinh X.
GD2. "Tong HO cua X" (luat HO_DI_XA cho X) = tong ho_attempt cua TOAN BO cell
     trong danh sach A cuoi cung (sau loc a/<1%/80%/15) - KHONG phai tong
     tho truoc loc.
GD3. "Bo small cell" CHI ap dung duoc khi co TEN CELL THAT (Nokia, qua
     cell_infor) - cell vendor khac/CAN_GHEP_TEN KHONG the kiem nen KHONG bi
     loai vi ly do nay.
GD4. Cell xuat hien o NHIEU sector cua X -> thuoc VE sector co %-trong-sector
     CAO NHAT (bang nhau -> sector nho hon).

=== N_MIN_HO_SECTOR (THEM 08/10/2026, yeu cau truc tiep user) ===
Do THAT tren TOAN BO 15.865 nhom (source_enb, sector) cua file NA09 (xem
scripts/phan_tich_nguong_ho.py): phan phoi TONG HO/sector P1=481 P5=3.156
P10=6.494 trung_vi=58.346. Dat N_MIN = P5 (TAM, theo dung yeu cau - "dat
N_MIN tam = P5") = 3156 (lam tron tu 3.156,4). Sector co tong HO < N_MIN ->
IT_DU_LIEU (van xu ly, chi canh bao). TOAN BO sector cua X deu IT_DU_LIEU ->
xu ly nhu KHONG_CO_DU_LIEU_HO (khong chay CR) - cung 1 ly do: mau qua nho de
tin cay ket luan "cell nao dang phu vung that".

=== LOC BUOC a (SUA 08/10/2026, dua len TRUOC khi tinh %) ===
Thu tu MOI (dung yeu cau review): small cell, cell nguon MBF_, noi tram
(intra-eNB), attempt=0 - loc TRUOC khi tinh tong_goc (mau so %). Truoc day
small cell bi loai SAU khi tinh %, khien mau so bi "phinh" bang attempt cua
chinh cell sap bi loai - sai nho nhung sai ve nguyen tac ("% trong sector"
phai la % tren tap THAT SU con lai). MBF_/noi tram/attempt=0 DA bi loc tu
luc nap (adapters/netact/import_ho_neighbor.py) - kiem lai o day la PHONG VE
2 LOP (repo/ho_rows khong duoc tin tuyet doi da loc dung, giong nhieu noi
khac trong du an).

=== DOI TEN CO (THEM 08/10/2026, dung GOI Y tu khao sat truoc) ===
TOA_DO_NGHI_SAI -> HO_DI_XA. Ten cu quy ket SAI nguyen nhan (khao sat
scripts/dieu_tra_toa_do_nghi_sai.py: phan lon do DO THI DELAUNAY QUA THUA,
KHONG PHAI toa do sai that). Luat kich hoat GIU NGUYEN.

=== TRAM TOA_DO_DUNG_CHUNG/CRAN (THEM 08/10/2026 lan 2, yeu cau truc tiep
    user, dua tren khao sat scripts/kiem_gia_thuyet_cran.py - xem dac ta day
    du o domain/services/ho_delaunay.py::phan_loai_toa_do()) ===
X la TOA_DO_DUNG_CHUNG (tham so x_la_toa_do_dung_chung, CALLER tu tinh qua
phan_loai_toa_do() roi truyen vao - ham nay KHONG tu tinh lai): toa do cua
chinh X khong dung tin cay duoc nen L1/L2 KHONG duoc tinh (caller PHAI truyen
l1_l2=[] - phan_lop_delaunay() da tu tra ve [] cho X dang nay); luat vung Z
(20%+SR95%) VA luat rieng cua layer KHONG_XAC_DINH (xem duoi) deu bi BO QUA -
B chon THUAN theo HO (giong co che bo qua da co san cho HO_DI_XA_X, gop lam 1
dieu kien duy nhat `bo_qua_gating` nhung BAO CAO rieng 2 co, khong gop nghia).
SUA 08/10/2026 lan 3 (yeu cau truc tiep user): X la TOA_DO_DUNG_CHUNG thi
`ho_di_xa_x` LUON la False, KHONG tinh theo cong thuc thuong (>50% HO vao Z) -
vi X khong co VI TRI dang tin de noi HO dang "di xa VE DAU", gan them co nay
se trung lap/sai nguyen nhan voi co `x_la_toa_do_dung_chung` da co san.

Tram DICH la TOA_DO_DUNG_CHUNG (BAT KE X co la gi): layer gan = "KHONG_XAC_DINH"
(KHAC "Z") - vi toa do dich KHONG BIET la GAN hay XA thuc su (khong co bang
chung hinh hoc nao ca, khac voi "Z" la DA XAC NHAN loai khoi L1/L2 cua X nen
mang nghia "biet la xa, can % lon + SR cao moi tin"). Do do luat cho
KHONG_XAC_DINH LONG HON Z: CHI can SR >= 95% (KHONG doi hoi % >= 20%) la vao
B; SR < 95% (hoac khong co SR) -> BAT_THUONG.

=== SUA 09/10/2026 (yeu cau truc tiep user, bug phat hien qua xem truoc tram
    117713 that - xem docs/BUSINESS_RULES.md muc cung ten) - loai CAN_GHEP_TEN
    TRUOC khi chon B ===
TRUOC: buoc chon B (top 2/sector) KHONG xet can_ghep_ten - cell Nokia nhung
CHUA sync cell_infor (vd tram 111629/4G-CGY327M-HNI: 0 dong trong cell_infor)
van chiem 1 "suat" rank (rsboost/qrxlevmin) trong sector, roi bi loai SAU o
lop application (khong co dist_name de tao Cell/XML) - lam MAT LUON suat do
cua ca sector (khong co cell nao len thay), B tu 12 -> 10 cell cho tram
117713 (2 sector mat rsboost).
NAY: THEM dieu kien `not can_ghep_ten` vao bo loc B (hop_le_b) - loai cell
nay NGAY TRUOC khi xep hang top 2/sector, de cell hop le KE TIEP trong CUNG
sector len thay dung vi tri rank. Cell CAN_GHEP_TEN VAN giu trong A (voi co
CAN_GHEP_TEN) - CHI bi loai khoi B.

=== IBS KHONG CHAY CR + TRAM DICH IBS/SMALL_CELL (THEM 12/10/2026, yeu cau
    truc tiep user, quyet dinh 12/10/2026) ===
Khac SMALL_CELL (da BO HOAN TOAN khoi moi tinh toan tu buoc a, xem GD3/
LOAI_TRAM_SMALL_CELL o tren - CHI kiem duoc khi co TEN THAT qua cell_infor):
IBS PHAI o lai trong A (danh gia QoS/phieu van can thay IBS), CHI bi loai
KHOI B (khong chay CR that qua SSH) - vi IBS la site TRONG NHA, thay doi
rsboost/qrxlevmin cua no it y nghia RF ngoai troi nhu macro. Vi A/B tach rieng
2 buoc (A xong moi toi B), khong the dung lai co che GD3 (loai truoc tong_goc)
- phai them dieu kien RIENG o hop_le_b (xem duoi), CUNG VI TRI/CUNG LY DO voi
fix CAN_GHEP_TEN 09/10/2026 o tren (loai TRUOC xep hang top 2/sector, de cell
hop le ke tiep len thay dung vi tri rank, KHONG de trong 1 "suat" ma khong ai
thay).

Tram DICH la IBS/SMALL_CELL (BAT KE X la gi): layer rieng "IBS"/"SMALL_CELL"
(KHAC "Z"/"KHONG_XAC_DINH") - KHONG xet L1/L2 (da bi loai khoi tap diem
Delaunay tu ho_delaunay.py, xem dac ta o do), KHONG ap luat gating vung Z
(20%+SR95%) - "GIONG" L1/L2 o cho LUON VAO B neu la nguon macro tot (IBS/
SMALL_CELL o day la TRAM DICH, khac voi "IBS khong chay CR" o tren noi ve
tram DICH IBS van duoc chon vao A/ung_vien_b binh thuong - "khong chay CR"
CHI ap dung rieng cho B, tai hop_le_b).

=== X LA IBS (THEM 12/10/2026, yeu cau truc tiep user, "GIONG X CRAN") ===
X la IBS -> phan_lop_delaunay() da tra ve [] (xem ho_delaunay.py, step 0) -
CALLER PHAI truyen l1_l2=[] (giong X CRAN). Tham so MOI x_la_ibs (CALLER tu
tinh qua loai_tram_tu_ten_tram(), ham nay KHONG tu tinh lai - cung mau hinh
voi x_la_toa_do_dung_chung): bo_qua_gating = True (B chon THUAN theo HO,
KHONG ap luat vung Z/KHONG_XAC_DINH - GIONG CRAN, vi KHONG co L1/L2 de xet
"gan/xa hinh hoc" nen Z/KHONG_XAC_DINH mat y nghia). ho_di_xa_x CUNG bi EP
False khi x_la_ibs=True - CUNG LY DO voi X CRAN (SUA 08/10/2026 lan 3): neu
khong ep, MOI cell deu roi vao "Z" mot cach GIA TAO (vi l1_l2 rong, khong
phai vi HO THAT su di xa), se bao HO_DI_XA=True GAN NHU LUON DUNG - trung
lap/sai nguyen nhan voi co TRAM_IBS da co san (ung dung CALLER them vao
x_co, xem application/trigger_cr_use_case.py).
"""

from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

from domain.services.ho_delaunay import L1_CUNG_SITE, TramPhanLop
from domain.services.loai_tram import (
    LOAI_TRAM_SMALL_CELL,
    NHOM_IBS,
    NHOM_KHAC,
    NHOM_SMALL_CELL,
    loai_tram_tu_ten_cell,
    loai_tram_tu_ten_tram,
)
from domain.services.neighbor_cell_filter import band_tu_lncel
from domain.value_objects.vendor import chuan_hoa_vendor

_EARTH_R_KM = 6371.0088


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1r, lon1r, lat2r, lon2r = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2r - lat1r, lon2r - lon1r
    a = sin(dlat / 2) ** 2 + cos(lat1r) * cos(lat2r) * sin(dlon / 2) ** 2
    return 2 * _EARTH_R_KM * asin(sqrt(a))


NGUONG_80_PCT = 0.80
TRAN_CELL_MOI_SECTOR = 15
NGUONG_BO_1_PCT = 0.01
NGUONG_CELL_LON = 0.10
NGUONG_VUNG_Z_PCT = 0.20
NGUONG_VUNG_Z_SR = 95.0
NGUONG_HO_DI_XA_X_PCT = 0.50
HE_SO_KHOANG_CACH_DICH_HO_DI_XA = 3.0
TOI_DA_CELL_MOI_SECTOR_B = 2
N_MIN_HO_SECTOR = 3156


class KhongCoDuLieuHoError(Exception):
    """X khong co dong HO nao (hoac MOI sector deu IT_DU_LIEU - duoi N_MIN_HO_SECTOR)
    - KHONG duoc chay CR.

    CO Y la Exception THUONG, KHONG PHAI domain.errors.DomainError - module
    nay CHUA noi vao API/use case nao (yeu cau truc tiep user), nen chua co
    y nghia gi de anh xa sang HTTP status. Xem chu y day du o ban SUA 1 (tai
    lieu lich su) - KHONG dinh nghia ke thua DomainError de tranh bi
    test_error_handler_map.py bat loi thieu entry."""


@dataclass
class ThongTinTramDich:
    """Tram dich (dich cua 1 cell_name) - CHI thong tin can cho thuat toan,
    DO CALLER (adapter) tu doc tu bang tram roi dung sang day."""

    tram_id: str
    tram_name: str
    ten_thiet_bi: str | None  # RAW tu tram.ten_thiet_bi - chuan hoa qua chuan_hoa_vendor() ben trong
    lat: float | None
    lon: float | None
    # THEM 08/10/2026 lan 2: CALLER tu tinh qua ho_delaunay.phan_loai_toa_do()
    # roi gan vao day - quyet dinh layer="KHONG_XAC_DINH" cho cell dich nay.
    toa_do_dung_chung: bool = False


@dataclass
class CellUngVien:
    """1 cell dich, da gan du thong tin de bao cao/quyet dinh A/B."""

    target_enb: int
    target_lcr: int
    sector: int  # sector CUA X ma cell nay duoc giu (sau dedup xuyen sector)
    ho_attempt: int
    ho_sr: float | None
    pct_trong_sector: float  # % attempt/tong sector (tinh TRUOC khi bo <1%) - xem GD1
    cell_name: str | None  # None neu CAN_GHEP_TEN (xem GD3)
    can_ghep_ten: bool
    vendor: str  # gia tri Vendor.value, hoac "KHONG_RO_TRAM" neu khong ghep duoc tram dich
    tram_dich_id: str | None
    tram_dich_ten: str | None
    # "L1" | "L1_CUNG_SITE" | "L2" | "Z" | "KHONG_XAC_DINH" | "IBS" |
    # "SMALL_CELL" (2 gia tri sau THEM 12/10/2026 - tram DICH la IBS/
    # SMALL_CELL, xem dac ta dau file; L1_CUNG_SITE THEM 16/10/2026 - tram
    # dich CUNG SITE voi X, xu ly GIONG HET "L1" o moi noi - CHI khac TEN
    # HIEN THI, xem domain/services/ho_delaunay.py::L1_CUNG_SITE).
    layer: str
    km: float | None
    ho_di_xa_dich: bool = False
    rank_b: str | None = None  # "rsboost" | "qrxlevmin" - CHI gan khi cell vao B


@dataclass
class QuanHe:
    """1 quan he (sector nguon, cell dich) DAY DU - THEM 08/10/2026, yeu cau
    truc tiep user, de "xem lai, kiem toan". Khac CellUngVien o cho: GIU CA
    cac sector "phu" bi loai boi dedup xuyen sector (GD4) - trong khi
    KetQuaChonCell.a CHI giu 1 ban ghi/cell (sector thang)."""

    sector: int
    target_enb: int
    target_lcr: int
    pct_trong_sector: float
    ho_attempt: int
    ho_sr: float | None
    layer: str


@dataclass
class KetQuaChonCell:
    x_tram_id: str
    a: list[CellUngVien]
    b: list[CellUngVien]
    bat_thuong: list[CellUngVien]  # cell trong A, bi chan boi luat vung Z (KHONG vao B)
    ho_di_xa_x: bool
    x_la_toa_do_dung_chung: bool = False  # THEM 08/10/2026 lan 2 - xem dac ta dau file
    quan_he_day_du: list[QuanHe] = field(default_factory=list)
    sectors_it_du_lieu: set[int] = field(default_factory=set)
    log_vung_z: list[dict] = field(default_factory=list)  # {enb,lcr,pct,sr,quyet_dinh}


def _resolve_tram_dich(
    target_enb: int,
    tram_dich_theo_enb: dict[int, ThongTinTramDich],
    cell_name_theo_enb_lcr: dict[tuple[int, int], str],
    target_lcr: int,
) -> tuple[str | None, bool, str, str | None, str | None, float | None, float | None, bool, str]:
    """Tra (cell_name, can_ghep_ten, vendor, tram_id, tram_name, lat, lon,
    toa_do_dung_chung, loai_tram_dich).

    loai_tram_dich (THEM 12/10/2026, yeu cau truc tiep user) - suy TU
    info.tram_name qua loai_tram_tu_ten_tram(), KHONG can them field rieng
    tren ThongTinTramDich (tram_name DA CO SAN, tinh lai 1 lan/cell la du re)."""
    info = tram_dich_theo_enb.get(target_enb)
    if info is None:
        return None, True, "KHONG_RO_TRAM", None, None, None, None, False, NHOM_KHAC
    vendor = chuan_hoa_vendor(info.ten_thiet_bi).value
    cell_name = cell_name_theo_enb_lcr.get((target_enb, target_lcr))
    loai_tram_dich = loai_tram_tu_ten_tram(info.tram_name)
    return (
        cell_name, cell_name is None, vendor, info.tram_id, info.tram_name, info.lat, info.lon,
        info.toa_do_dung_chung, loai_tram_dich,
    )


def chon_cell_cr(
    x_tram_id: str,
    ho_rows: list[dict],
    l1_l2: list[TramPhanLop],
    tram_dich_theo_enb: dict[int, ThongTinTramDich],
    cell_name_theo_enb_lcr: dict[tuple[int, int], str],
    x_lat: float | None = None,
    x_lon: float | None = None,
    x_la_toa_do_dung_chung: bool = False,
    x_la_ibs: bool = False,
) -> KetQuaChonCell:
    """ho_rows: dict voi field source_lncel_name, source_sector, target_enb,
    target_lcr, ho_attempt, ho_sr (list tra tu IHoNeighborRepo.get_by_source_enb()).

    x_lat/x_lon: dung tinh km CHO MOI cell (ke ca Z) - xem ban SUA 1 (lich
    su) de biet ly do can tham so nay.

    x_la_toa_do_dung_chung: CALLER tu tinh qua ho_delaunay.phan_loai_toa_do()
    roi truyen vao (ham nay KHONG tu tinh lai) - xem dac ta TRAM
    TOA_DO_DUNG_CHUNG/CRAN dau file. Khi True, caller PHAI truyen l1_l2=[]
    (phan_lop_delaunay() da tu lam dieu nay cho X dang TOA_DO_DUNG_CHUNG).

    x_la_ibs (THEM 12/10/2026): CALLER tu tinh qua loai_tram_tu_ten_tram()
    (ham nay KHONG tu tinh lai) - xem dac ta "X LA IBS" dau file. Khi True,
    caller PHAI truyen l1_l2=[] (phan_lop_delaunay() da tu lam dieu nay cho
    X la IBS, GIONG CRAN)."""
    x_enb = int(x_tram_id)

    # --- BUOC a: LOC TRUOC khi tinh % - noi tram, nguon MBF_, attempt<=0.
    # PHONG VE 2 LOP: da loc tu luc nap (import_ho_neighbor.py) nhung ham
    # nay KHONG tin tuyet doi caller da loc dung (xem GHI CHU dau file).
    rows_loc = [
        r for r in ho_rows
        if r["ho_attempt"] > 0
        and r["target_enb"] != x_enb
        and not str(r.get("source_lncel_name", "")).startswith("MBF_")
    ]
    if not rows_loc:
        raise KhongCoDuLieuHoError(f"Tram {x_tram_id} khong co dong HO nao - khong chay CR")

    layer_theo_enb = {int(t.tram_id): t.layer for t in l1_l2}
    km_theo_enb = {int(t.tram_id): t.km for t in l1_l2}
    # L1_CUNG_SITE (THEM 16/10/2026) VAN la L1 ve mat thuat toan - PHAI gom
    # chung o day, nguoc lai trung_vi_l1_km se bi thoi phong sai (mat cac
    # tram cung site, km=0, ra khoi mau).
    khoang_cach_l1 = [t.km for t in l1_l2 if t.layer in ("L1", L1_CUNG_SITE)]
    trung_vi_l1_km = sorted(khoang_cach_l1)[len(khoang_cach_l1) // 2] if khoang_cach_l1 else None

    # --- Gom theo sector cua X ---
    theo_sector: dict[int, dict[tuple[int, int], dict]] = {}
    for r in rows_loc:
        nhom = theo_sector.setdefault(r["source_sector"], {})
        khoa = (r["target_enb"], r["target_lcr"])
        d = nhom.setdefault(khoa, {"attempt": 0, "sr_x_att": 0.0, "sr_w": 0})
        d["attempt"] += r["ho_attempt"]
        if r["ho_sr"] is not None:
            d["sr_x_att"] += r["ho_sr"] * r["ho_attempt"]
            d["sr_w"] += r["ho_attempt"]

    # --- Moi sector: resolve tram dich + loai small cell TRUOC (buoc a), roi
    # MOI tinh tong_goc (mau so %) tren tap DA loc small cell (SUA 08/10/2026). ---
    ung_vien_theo_sector: dict[int, list[CellUngVien]] = {}
    sectors_it_du_lieu: set[int] = set()
    for sector, cands in theo_sector.items():
        da_resolve: list[tuple[int, int, dict, str | None, bool, str, str | None, str | None, float | None, float | None, bool, str]] = []
        for (enb, lcr), v in cands.items():
            cell_name, can_ghep_ten, vendor, tram_id, tram_ten, lat, lon, dung_chung, loai_tram_dich = _resolve_tram_dich(
                enb, tram_dich_theo_enb, cell_name_theo_enb_lcr, lcr
            )
            if cell_name is not None and loai_tram_tu_ten_cell(cell_name) in LOAI_TRAM_SMALL_CELL:
                continue  # bo small cell (CHI kiem duoc khi co ten that - xem GD3)
            da_resolve.append((enb, lcr, v, cell_name, can_ghep_ten, vendor, tram_id, tram_ten, lat, lon, dung_chung, loai_tram_dich))

        tong_goc = sum(t[2]["attempt"] for t in da_resolve)
        if tong_goc == 0:
            continue
        if tong_goc < N_MIN_HO_SECTOR:
            sectors_it_du_lieu.add(sector)

        xep = sorted(da_resolve, key=lambda t: -t[2]["attempt"])
        sau_loc: list[CellUngVien] = []
        for enb, lcr, v, cell_name, can_ghep_ten, vendor, tram_id, tram_ten, lat, lon, dung_chung, loai_tram_dich in xep:
            pct = v["attempt"] / tong_goc
            if pct < NGUONG_BO_1_PCT:
                continue  # bo cell < 1%
            sr_tb = (v["sr_x_att"] / v["sr_w"]) if v["sr_w"] > 0 else None
            # Tram dich TOA_DO_DUNG_CHUNG -> layer rieng "KHONG_XAC_DINH" (KHAC
            # "Z" - xem dac ta TRAM TOA_DO_DUNG_CHUNG/CRAN dau file), BAT KE co
            # trong l1_l2 hay khong (toa do khong dang tin nen khong the nam
            # trong L1/L2 cua X - phan_lop_delaunay() da loai truoc, nhung van
            # kiem lai o day phong truong hop goi truc tiep/khong qua ham do).
            # Tram dich IBS/SMALL_CELL (THEM 12/10/2026) - CUNG kiem lai o day
            # (da bi loai khoi tap diem Delaunay tu ho_delaunay.py nen KHONG
            # bao gio co trong layer_theo_enb, nhung KIEM TRUOC dung_chung de
            # CHOT thu tu uu tien ro rang neu 1 tram vua la CRAN vua la IBS/
            # SMALL_CELL - IBS/SMALL_CELL la ban chat VAT LY co dinh (ten tram),
            # uu tien hon TOA_DO_DUNG_CHUNG la trang thai suy luan tu toa do).
            if enb in layer_theo_enb:
                layer = layer_theo_enb[enb]
            elif loai_tram_dich == NHOM_IBS:
                layer = "IBS"
            elif loai_tram_dich == NHOM_SMALL_CELL:
                layer = "SMALL_CELL"
            else:
                layer = "KHONG_XAC_DINH" if dung_chung else "Z"
            if x_lat is not None and x_lon is not None and lat is not None and lon is not None:
                km = _haversine_km(x_lat, x_lon, lat, lon)
            else:
                km = km_theo_enb.get(enb)
            sau_loc.append(
                CellUngVien(
                    target_enb=enb, target_lcr=lcr, sector=sector,
                    ho_attempt=v["attempt"], ho_sr=sr_tb, pct_trong_sector=pct,
                    cell_name=cell_name, can_ghep_ten=can_ghep_ten, vendor=vendor,
                    tram_dich_id=tram_id, tram_dich_ten=tram_ten,
                    layer=layer, km=km,
                )
            )

        # Cong don >= 80% (lay ca cell vuot nguong) HOAC du 15 cell - tinh
        # tren TOAN BO quan he cua sector SAU buoc a (CHUA dedup xuyen sector).
        tong_sau_loc = sum(c.ho_attempt for c in sau_loc)
        if tong_sau_loc == 0:
            continue
        giu: list[CellUngVien] = []
        cong_don = 0
        for i, c in enumerate(sau_loc, start=1):
            giu.append(c)
            cong_don += c.ho_attempt
            if cong_don / tong_sau_loc >= NGUONG_80_PCT or i >= TRAN_CELL_MOI_SECTOR:
                break
        # LAY THEM cell LON con lai (10/10/2026) - xem dac ta "LUAT DANH SACH A
        # - LAY THEM CELL LON" dau file. sau_loc[len(giu):] da sorted giam dan
        # theo attempt nen chi can dung lai ngay khi gap cell < NGUONG_CELL_LON.
        for c in sau_loc[len(giu):]:
            if len(giu) >= TRAN_CELL_MOI_SECTOR or c.pct_trong_sector < NGUONG_CELL_LON:
                break
            giu.append(c)
        ung_vien_theo_sector[sector] = giu

    if not ung_vien_theo_sector or sectors_it_du_lieu == set(ung_vien_theo_sector):
        # MOI sector deu IT_DU_LIEU (hoac khong con sector nao sau loc) -> xu
        # ly NHU KHONG_CO_DU_LIEU_HO (xem dac ta N_MIN_HO_SECTOR dau file).
        raise KhongCoDuLieuHoError(
            f"Tram {x_tram_id} - moi sector deu duoi N_MIN_HO_SECTOR ({N_MIN_HO_SECTOR}) hoac khong co du lieu - khong chay CR"
        )

    # --- quan_he_day_du (THEM 08/10/2026) - GIU CA cac sector "phu" TRUOC dedup. ---
    quan_he_day_du = [
        QuanHe(sector=c.sector, target_enb=c.target_enb, target_lcr=c.target_lcr,
               pct_trong_sector=c.pct_trong_sector, ho_attempt=c.ho_attempt,
               ho_sr=c.ho_sr, layer=c.layer)
        for sector in sorted(ung_vien_theo_sector)
        for c in ung_vien_theo_sector[sector]
    ]

    # --- Dedup xuyen sector: cell o nhieu sector -> 1 lan, GIU sector co %
    # HO CAO NHAT (xem GD4). Bang nhau -> sector nho hon (duyet TANG DAN,
    # dieu kien so sanh la "> nghiem ngat" nen ban ghi dau o muc bang nhau
    # khong bi ghi de). ---
    a_theo_khoa: dict[tuple[int, int], CellUngVien] = {}
    for sector in sorted(ung_vien_theo_sector):
        for c in ung_vien_theo_sector[sector]:
            khoa = (c.target_enb, c.target_lcr)
            hien_tai = a_theo_khoa.get(khoa)
            if hien_tai is None or c.pct_trong_sector > hien_tai.pct_trong_sector:
                a_theo_khoa[khoa] = c
    danh_sach_a = list(a_theo_khoa.values())

    # --- Luat HO_DI_XA cho X: > 50% tong HO (cua A) roi vao vung Z. SUA
    # 08/10/2026 lan 3: X la TOA_DO_DUNG_CHUNG -> KHONG tinh/gan co nay -
    # X khong co vi tri dang tin nen khong the noi HO "di xa VE DAU" (so
    # voi cai gi?) - da co co TOA_DO_DUNG_CHUNG RIENG mo ta dung nguyen
    # nhan, gan them HO_DI_XA se trung lap/sai y nghia cho cung 1 tinh huong.
    # THEM 12/10/2026: X la IBS -> CUNG EP False, CUNG LY DO (xem dac ta "X LA
    # IBS" dau file) - l1_l2 rong nen MOI cell deu la "Z" GIA TAO, khong phai
    # HO THAT su di xa. ---
    tong_ho_a = sum(c.ho_attempt for c in danh_sach_a)
    tong_z = sum(c.ho_attempt for c in danh_sach_a if c.layer == "Z")
    ho_di_xa_x = (
        not x_la_toa_do_dung_chung
        and not x_la_ibs
        and tong_ho_a > 0
        and (tong_z / tong_ho_a) > NGUONG_HO_DI_XA_X_PCT
    )

    # --- Luat vung Z (20% + SR>=95%) / luat KHONG_XAC_DINH (CHI SR>=95%) +
    # luat HO_DI_XA cho tram dich. bo_qua_gating: X co HO_DI_XA (nghi toa do
    # qua suy dien tu HO) HOAC X la TOA_DO_DUNG_CHUNG (biet truoc toa do X
    # khong dung tin cay duoc) HOAC X la IBS (THEM 12/10/2026, GIONG CRAN - xem
    # dac ta "X LA IBS" dau file) - CA 3 deu dan den "B chon THUAN theo HO",
    # nhung giu RIENG CAC co de BAO CAO dung nguyen nhan (xem dac ta dau file). ---
    bo_qua_gating = ho_di_xa_x or x_la_toa_do_dung_chung or x_la_ibs
    bat_thuong: list[CellUngVien] = []
    log_vung_z: list[dict] = []
    ung_vien_b: list[CellUngVien] = []
    for c in danh_sach_a:
        # IBS/SMALL_CELL (THEM 12/10/2026) - tram DICH, LUON vao ung_vien_b
        # GIONG L1/L2 (KHONG ap gating vung Z - da bi loai khoi Delaunay nen
        # khong co nghia "gan/xa hinh hoc" de ap luat Z). "Khong chay CR" cho
        # IBS la RIENG o buoc hop_le_b duoi, KHONG phai o day.
        # L1_CUNG_SITE (THEM 16/10/2026) PHAI xu ly GIONG HET "L1" o day - chi
        # la ten hien thi khac, KHONG duoc doi ket qua A/B/vung Z (xem dac ta
        # domain/services/ho_delaunay.py::L1_CUNG_SITE).
        if c.layer in ("L1", L1_CUNG_SITE, "L2", "IBS", "SMALL_CELL"):
            ung_vien_b.append(c)
            continue

        if (
            c.layer == "Z"
            and trung_vi_l1_km is not None
            and c.pct_trong_sector >= NGUONG_VUNG_Z_PCT
            and c.km is not None
            and c.km > HE_SO_KHOANG_CACH_DICH_HO_DI_XA * trung_vi_l1_km
        ):
            c.ho_di_xa_dich = True

        if bo_qua_gating:
            ly_do = "X co HO_DI_XA" if ho_di_xa_x else "X la TOA_DO_DUNG_CHUNG"
            quyet_dinh = f"VAO_B (bo qua luat vung Z/KHONG_XAC_DINH - {ly_do})"
            ung_vien_b.append(c)
        elif c.layer == "KHONG_XAC_DINH":
            if c.ho_sr is not None and c.ho_sr >= NGUONG_VUNG_Z_SR:
                quyet_dinh = "VAO_B"
                ung_vien_b.append(c)
            else:
                quyet_dinh = "BAT_THUONG"
                bat_thuong.append(c)
        elif c.pct_trong_sector >= NGUONG_VUNG_Z_PCT and c.ho_sr is not None and c.ho_sr >= NGUONG_VUNG_Z_SR:
            quyet_dinh = "VAO_B"
            ung_vien_b.append(c)
        else:
            quyet_dinh = "BAT_THUONG"
            bat_thuong.append(c)

        log_vung_z.append({
            "target_enb": c.target_enb, "target_lcr": c.target_lcr,
            "pct": c.pct_trong_sector, "sr": c.ho_sr, "quyet_dinh": quyet_dinh,
        })

    # --- Danh sach B: tu ung_vien_b, chi Nokia, lcr ^[13][0-9]$, CO TEN (DA
    # resolve duoc DN qua cell_infor), toi da 2/sector, khong trung giua
    # sector (sector nho hon giu quyen) ---
    #
    # SUA 09/10/2026 (yeu cau truc tiep user, phat hien qua xem truoc tram
    # 117713 that - B 12 cell o day nhung chi 10 cell con lai sau khi lop
    # application loai CAN_GHEP_TEN VI DA CHON XONG top 2/sector): THEM dieu
    # kien "not c.can_ghep_ten" o DAY - TRUOC khi xep hang top 2/sector -
    # thay vi loai SAU (o application/trigger_cr_use_case.py, khi can_ghep_ten
    # khong resolve duoc dist_name de tao Cell/XML). Loai SAU de lo 1 "cho
    # trong" trong sector (vd rank rsboost "mat" vi cell dung hang 1 khong co
    # DN) ma KHONG co cell nao len thay - trong khi loai TRUOC (o day) cho
    # phep cell hop le ke tiep trong CUNG sector len thay dung vi tri rank.
    # Cell CAN_GHEP_TEN VAN giu trong danh sach A (danh_sach_a, voi co
    # CAN_GHEP_TEN qua CellUngVien.can_ghep_ten) - CHI bi loai khoi B o day.
    # THEM 12/10/2026 (yeu cau truc tiep user, "IBS KHONG CHAY CR") - dieu kien
    # "layer not in (IBS, SMALL_CELL)" loai cell dich thuoc tram IBS/SMALL_CELL
    # KHOI B, CUNG VI TRI (TRUOC xep hang top 2/sector) voi fix can_ghep_ten
    # 09/10/2026 o tren - de cell hop le ke tiep trong CUNG sector len thay
    # dung vi tri rank, KHONG de trong 1 "suat" rsboost/qrxlevmin ma khong ai
    # thay. Cell IBS/SMALL_CELL VAN nam trong danh_sach_a (A, da vao ung_vien_b
    # o vong lap tren) - CHI bi loai o day (B).
    hop_le_b = [
        c for c in ung_vien_b
        if c.vendor == "NOKIA" and not c.can_ghep_ten and c.layer not in ("IBS", "SMALL_CELL")
        and band_tu_lncel(f"LNCEL-{c.target_lcr}") is not None
    ]
    theo_sector_b: dict[int, list[CellUngVien]] = {}
    for c in hop_le_b:
        theo_sector_b.setdefault(c.sector, []).append(c)

    danh_sach_b: list[CellUngVien] = []
    da_chon: set[tuple[int, int]] = set()
    for sector in sorted(theo_sector_b):
        xep = sorted(theo_sector_b[sector], key=lambda c: -c.ho_attempt)
        so_da_chon = 0
        for c in xep:
            if so_da_chon >= TOI_DA_CELL_MOI_SECTOR_B:
                break
            khoa = (c.target_enb, c.target_lcr)
            if khoa in da_chon:
                continue
            c.rank_b = "rsboost" if so_da_chon == 0 else "qrxlevmin"
            danh_sach_b.append(c)
            da_chon.add(khoa)
            so_da_chon += 1

    return KetQuaChonCell(
        x_tram_id=x_tram_id,
        a=danh_sach_a,
        b=danh_sach_b,
        bat_thuong=bat_thuong,
        ho_di_xa_x=ho_di_xa_x,
        x_la_toa_do_dung_chung=x_la_toa_do_dung_chung,
        quan_he_day_du=quan_he_day_du,
        sectors_it_du_lieu=sectors_it_du_lieu,
        log_vung_z=log_vung_z,
    )
