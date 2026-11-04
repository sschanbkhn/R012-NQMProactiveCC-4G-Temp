"""
scripts/download_osm_tiles.py — tai tile OSM ve dia de phuc vu ban do OFFLINE.
Tu: yeu cau truc tiep user (14/08).

CHAY TREN PC CO MANG (Windows/Linux deu duoc), KHONG chay tren server .196/.197.
Server va may nguoi dung deu KHONG CO INTERNET nen FE R012 (Leaflet) dang tro
thang ra https://{s}.tile.openstreetmap.org/... se hien ban do TRANG.

QUY TRINH:
  1. Chay script nay tren may co mang -> ra thu muc ./osm_tiles/{z}/{x}/{y}.png
  2. Nen lai, mang sang .197, giai nen vao /home/auto/osm-tiles/
  3. symlink /home/auto/FE/tiles -> /home/auto/osm-tiles (da test voi http-server)
  4. Doi TileLayer ben FE tro ve /tiles/{z}/{x}/{y}.png

VI SAO LUU DANG THU MUC {z}/{x}/{y}.png ma KHONG dung .mbtiles:
.mbtiles la 1 file SQLite - muon phuc vu no phai co phan mem doc mbtiles chay
tren server (tileserver-gl, mbtileserver...). Server .197 OFFLINE, cai them 1
service nua la them 1 thu phai bao tri. Cau truc thu muc thi http-server co san
phuc vu duoc TRUC TIEP, khong can gi them - doi lai ton nhieu inode hon, chap
nhan duoc.

=========================================================================
!!! OSM TILE USAGE POLICY - DOC TRUOC KHI SUA SCRIPT NAY !!!
=========================================================================
tile.openstreetmap.org chay bang tien va cong suc cua TINH NGUYEN VIEN.
Policy chinh thuc CAM bulk download. Vi pham -> chan IP (ca dai IP cua don vi).
Script nay CO Y bi lam cham lai va KHONG the tang toc:
  - User-Agent ghi ro ten cong cu + don vi (tham so --user-agent)
  - Gian cach --delay giua MOI request (mac dinh 0.5s)
  - TUYET DOI KHONG tai song song: khong thread, khong asyncio, khong
    ThreadPoolExecutor. Chi 1 vong for tuan tu.
  - KHONG xoay vong subdomain a/b/c: xoay subdomain la ky thuat de TANG SO
    KET NOI SONG SONG cua trinh duyet - dung o day se dung y do "lam cham".
    Goi thang tile.openstreetmap.org.
  - Gap HTTP 429 (qua nhieu request) hoac 403 (bi cam) -> DUNG NGAY toan bo,
    KHONG thu lai. Thu lai khi da bi chan chi lam tinh hinh xau hon.
Neu can nhieu tile hon muc script nay tai duoc trong dem, DUNG lach policy -
hay tim nguon cho phep (Geofabrik extract + tu render, hoac dich vu tra phi).

Chi dung THU VIEN CHUAN Python (urllib.request) - KHONG can pip install gi,
chay duoc ngay tren may bat ky co Python 3.

Chay thu (khong tai gi):
    python scripts/download_osm_tiles.py --dry-run
Tai that:
    python scripts/download_osm_tiles.py
"""

import argparse
import math
import os
import signal
import sys
import time
import urllib.error
import urllib.request

_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

# Magic bytes dau file PNG. Kiem tra truoc khi ghi de KHONG luu nham trang loi
# HTML/JSON thanh file .png - loai file rac nay rat kho phat hien ve sau (dung
# duoi ten .png, kich thuoc > 0 nen vong "bo qua file da co" se coi la da tai
# xong, va Leaflet chi hien o trong).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Uoc luong dung luong cho --dry-run.
# SUA 15 -> 7 (15/08) sau khi DO THUC TE tren vung Viet Nam (lon 102-110,
# lat 8.2-23.5, zoom 6-13): 89.153 tile / 538,46 MB = ~6,3 KB/tile - chi bang
# 42% con so 15KB cu (con so do gia dinh tile do thi). Khung nay phu rat nhieu
# BIEN va RUNG, tile gan nhu trong nen rat nhe.
# Lam tron LEN 7 chu khong lay 6,3: uoc dung luong hoi DU thi nguoi chay chuan
# bi thua cho trong; uoc THIEU thi day dia giua chung, mat ca luot tai dai nhieu
# tieng. Sai so 2 huong khong ngang gia nhau.
_UOC_KB_MOI_TILE = 7

_TEN_FILE_LOI = "_failed_tiles.txt"


# =========================================================================
# CHUYEN DOI TOA DO -> CHI SO TILE (Web Mercator / EPSG:3857)
# =========================================================================
def lon_sang_x(lon: float, z: int) -> int:
    """Kinh do -> chi so tile theo truc X.

    Buoc 1: (lon + 180) doi tu [-180, 180] sang [0, 360] - bo so am cho de tinh.
    Buoc 2: / 360 -> ty le [0, 1] tren toan bo be ngang the gioi.
    Buoc 3: * 2^z -> so tile. Zoom z chia the gioi thanh 2^z cot.
    Buoc 4: floor -> lay chi so cot chua diem do.
    """
    return int(math.floor((lon + 180.0) / 360.0 * (2 ** z)))


def lat_sang_y(lat: float, z: int) -> int:
    """Vi do -> chi so tile theo truc Y (cong thuc chieu Mercator).

    Buoc 1: doi sang radian - ham luong giac cua Python nhan radian.
    Buoc 2: tan(lat) + 1/cos(lat) roi ln(...) - day la phep chieu Mercator,
            keo gian dan vung gan 2 cuc de moi tile van vuong tren man hinh.
    Buoc 3: / pi rooi (1 - ...) / 2 -> ty le [0, 1] tinh TU BAC XUONG NAM.
    Buoc 4: * 2^z va floor -> chi so hang.

    !!! CHU Y CHIEU TRUC Y: lat cang LON (cang ve phia BAC) thi y cang NHO.
    Vi vay khi tinh khoang tile phai lay:
        y_min = lat_sang_y(max_lat)   <- bien BAC
        y_max = lat_sang_y(min_lat)   <- bien NAM
    Lam nguoc lai se ra khoang RONG (y_min > y_max) va vong for khong chay lan
    nao - script "thanh cong" ma khong tai gi.
    """
    lat_rad = math.radians(lat)
    return int(math.floor(
        (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * (2 ** z)
    ))


def khoang_tile(min_lon, max_lon, min_lat, max_lat, z):
    """Tra (x_min, x_max, y_min, y_max) da kep trong [0, 2^z - 1]."""
    toi_da = 2 ** z - 1
    x_min = max(0, min(toi_da, lon_sang_x(min_lon, z)))
    x_max = max(0, min(toi_da, lon_sang_x(max_lon, z)))
    # Doi chieu truc Y: max_lat cho y NHO, min_lat cho y LON (xem lat_sang_y)
    y_min = max(0, min(toi_da, lat_sang_y(max_lat, z)))
    y_max = max(0, min(toi_da, lat_sang_y(min_lat, z)))
    return x_min, x_max, y_min, y_max


def dem_tile(min_lon, max_lon, min_lat, max_lat, z) -> int:
    x_min, x_max, y_min, y_max = khoang_tile(min_lon, max_lon, min_lat, max_lat, z)
    return (x_max - x_min + 1) * (y_max - y_min + 1)


def _dinh_dang_thoi_gian(giay: float) -> str:
    giay = int(giay)
    gio, du = divmod(giay, 3600)
    phut, gy = divmod(du, 60)
    if gio:
        return f"{gio}h{phut:02d}m"
    if phut:
        return f"{phut}m{gy:02d}s"
    return f"{gy}s"


def _dinh_dang_dung_luong(byte: float) -> str:
    for don_vi in ("B", "KB", "MB", "GB"):
        if byte < 1024 or don_vi == "GB":
            return f"{byte:.1f} {don_vi}"
        byte /= 1024
    return f"{byte:.1f} GB"


# =========================================================================
# --dry-run: CHI TINH VA IN
# =========================================================================
def chay_dry_run(args) -> None:
    print("=== DRY RUN - CHI TINH, KHONG TAI GI ===\n")
    print(f"Vung   : lon {args.min_lon} .. {args.max_lon} | lat {args.min_lat} .. {args.max_lat}")
    print(f"Zoom   : {args.min_zoom} .. {args.max_zoom}")
    print(f"Delay  : {args.delay}s / request")
    print(f"Output : {args.output}\n")

    print(f"  {'zoom':>4} | {'so tile':>10} | {'uoc dung luong':>15} | {'uoc thoi gian':>14}")
    print(f"  {'-' * 4}-+-{'-' * 10}-+-{'-' * 15}-+-{'-' * 14}")

    tong_tile = 0
    for z in range(args.min_zoom, args.max_zoom + 1):
        n = dem_tile(args.min_lon, args.max_lon, args.min_lat, args.max_lat, z)
        tong_tile += n
        dung_luong = n * _UOC_KB_MOI_TILE * 1024
        # Thoi gian = so tile x delay. KHONG cong them thoi gian tai that (phu
        # thuoc mang, khong doan duoc) - nen day la CAN DUOI, thuc te lau hon.
        print(f"  {z:>4} | {n:>10,} | {_dinh_dang_dung_luong(dung_luong):>15} | "
              f"{_dinh_dang_thoi_gian(n * args.delay):>14}")

    print(f"  {'-' * 4}-+-{'-' * 10}-+-{'-' * 15}-+-{'-' * 14}")
    tong_dung_luong = tong_tile * _UOC_KB_MOI_TILE * 1024
    tong_giay = tong_tile * args.delay
    print(f"  {'TONG':>4} | {tong_tile:>10,} | {_dinh_dang_dung_luong(tong_dung_luong):>15} | "
          f"{_dinh_dang_thoi_gian(tong_giay):>14}")

    print(f"\nUoc tinh theo {_UOC_KB_MOI_TILE}KB/tile va delay {args.delay}s "
          f"(CHUA cong thoi gian tai that -> thuc te lau hon).")

    if tong_giay > 12 * 3600:
        print("\n" + "!" * 70)
        print(f"!! CANH BAO: tong thoi gian uoc tinh {_dinh_dang_thoi_gian(tong_giay)} > 12 tieng.")
        print("!! Nen: giam --max-zoom (moi muc zoom BOT DI x4 tile), thu hep vung,")
        print("!! hoac chay lam nhieu dot (script co the chay lai, tu bo qua file da tai).")
        print("!! DUNG giam --delay de chay nhanh hon - se bi OSM chan IP.")
        print("!" * 70)


# =========================================================================
# TAI THAT
# =========================================================================
class BiChanError(Exception):
    """HTTP 429/403 - phai DUNG NGAY toan bo, khong thu lai."""


def tai_1_tile(url: str, user_agent: str, timeout: int = 30) -> bytes | None:
    """Tra ve bytes cua tile, hoac None neu 404 (tile khong ton tai).

    Raise BiChanError khi 429/403. Raise urllib.error.URLError/socket timeout
    cho loi mang de caller tu thu lai.
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Tile khong ton tai - binh thuong o vung bien/ngoai pham vi du lieu.
            return None
        if e.code in (429, 403):
            raise BiChanError(f"HTTP {e.code}") from e
        raise


def chay_tai_that(args) -> int:
    tong = {"moi": 0, "bo_qua": 0, "khong_co": 0, "loi": 0, "byte": 0}
    theo_zoom: dict[int, int] = {}
    tile_loi: list[str] = []
    bat_dau = time.time()
    bi_chan = False
    bi_ngat = False

    tong_tile_can = sum(
        dem_tile(args.min_lon, args.max_lon, args.min_lat, args.max_lat, z)
        for z in range(args.min_zoom, args.max_zoom + 1)
    )
    print(f"=== BAT DAU TAI {tong_tile_can:,} tile | delay {args.delay}s | output {args.output} ===")
    print("Ctrl+C bat cu luc nao de dung - lan sau chay lai se tu tiep tuc.\n")

    try:
        for z in range(args.min_zoom, args.max_zoom + 1):
            x_min, x_max, y_min, y_max = khoang_tile(
                args.min_lon, args.max_lon, args.min_lat, args.max_lat, z)
            so_tile_zoom = (x_max - x_min + 1) * (y_max - y_min + 1)
            theo_zoom[z] = so_tile_zoom
            da_xu_ly_zoom = 0

            for x in range(x_min, x_max + 1):
                thu_muc = os.path.join(args.output, str(z), str(x))
                os.makedirs(thu_muc, exist_ok=True)

                for y in range(y_min, y_max + 1):
                    da_xu_ly_zoom += 1
                    duong_dan = os.path.join(thu_muc, f"{y}.png")

                    # CHAY LAI DUOC: file da co va > 0 byte -> bo qua, KHONG goi
                    # mang. Nho vay dut giua chung (Ctrl+C, mat dien, rot mang)
                    # chi mat dung tile dang tai do.
                    # Kiem ca size > 0 vi file 0 byte la dau vet cua lan ghi
                    # hong - phai tai lai chu khong duoc coi la xong.
                    if os.path.exists(duong_dan) and os.path.getsize(duong_dan) > 0:
                        tong["bo_qua"] += 1
                    else:
                        url = _TILE_URL.format(z=z, x=x, y=y)
                        du_lieu = None
                        loi_cuoi = None

                        # Thu lai toi da 3 lan cho loi MANG (timeout/dut ket noi)
                        # voi do tre tang dan 1s/2s/4s. KHONG ap dung cho 404
                        # (tra None ngay) va 429/403 (nem BiChanError ra ngoai).
                        for lan in range(3):
                            try:
                                du_lieu = tai_1_tile(url, args.user_agent)
                                loi_cuoi = None
                                break
                            except BiChanError:
                                raise
                            except Exception as e:  # noqa: BLE001 - loi mang du loai
                                loi_cuoi = e
                                if lan < 2:
                                    time.sleep(2 ** lan)  # 1s, 2s (lan 3 khong cho)

                        if loi_cuoi is not None:
                            tong["loi"] += 1
                            tile_loi.append(f"{z}/{x}/{y}  {loi_cuoi}")
                        elif du_lieu is None:
                            # 404 - tile khong ton tai, dem RIENG, KHONG phai loi
                            tong["khong_co"] += 1
                        elif not du_lieu.startswith(_PNG_MAGIC):
                            # Khong phai PNG - thuong la trang loi HTML. KHONG ghi
                            # ra dia (xem _PNG_MAGIC dau file).
                            tong["loi"] += 1
                            tile_loi.append(f"{z}/{x}/{y}  KHONG PHAI PNG ({len(du_lieu)} byte)")
                        else:
                            with open(duong_dan, "wb") as f:
                                f.write(du_lieu)
                            tong["moi"] += 1
                            tong["byte"] += len(du_lieu)

                        # Delay SAU MOI request that (khong ap cho tile bo qua -
                        # bo qua khong cham toi may chu OSM).
                        time.sleep(args.delay)

                    # Tien do moi 100 tile
                    da_xu_ly = tong["moi"] + tong["bo_qua"] + tong["khong_co"] + tong["loi"]
                    if da_xu_ly % 100 == 0:
                        pct = da_xu_ly_zoom * 100 // so_tile_zoom
                        con_lai = tong_tile_can - da_xu_ly
                        # ETA tinh theo toc do THUC TE tu dau den gio (da gom ca
                        # tile bo qua rat nhanh) - sat hon la nhan delay suong.
                        toc_do = da_xu_ly / max(time.time() - bat_dau, 0.001)
                        eta = con_lai / toc_do if toc_do > 0 else 0
                        print(f"[z={z}] {da_xu_ly_zoom:,}/{so_tile_zoom:,} ({pct}%) | "
                              f"moi: {tong['moi']:,} | bo qua: {tong['bo_qua']:,} | "
                              f"loi: {tong['loi']:,} | ETA {_dinh_dang_thoi_gian(eta)}")

    except BiChanError as e:
        bi_chan = True
        print("\n" + "!" * 70)
        print(f"!! DUNG NGAY - OSM DA CHAN ({e})")
        print("!!")
        print("!! Script KHONG thu lai (thu lai khi da bi chan chi lam xau hon).")
        print("!! Goi y xu ly:")
        print("!!   1. Tang --delay (vd 1.0 hoac 2.0) roi chay lai sau vai gio.")
        print("!!      Script tu bo qua tile da tai nen khong mat cong.")
        print("!!   2. Doi IP ra (bi chan thuong theo IP, co the ca dai IP don vi).")
        print("!!   3. Neu can nhieu tile: DUNG lach policy - dung nguon cho phep")
        print("!!      (Geofabrik extract + tu render, hoac dich vu tile tra phi).")
        print("!" * 70)
    except KeyboardInterrupt:
        bi_ngat = True
        print("\n\n=== DA DUNG (Ctrl+C) - lan sau chay lai se tu tiep tuc ===")

    # Ghi danh sach tile loi de chay lai rieng
    if tile_loi:
        os.makedirs(args.output, exist_ok=True)
        duong_dan_loi = os.path.join(args.output, _TEN_FILE_LOI)
        with open(duong_dan_loi, "w", encoding="utf-8") as f:
            f.write("\n".join(tile_loi) + "\n")
        print(f"\nDa ghi {len(tile_loi)} tile loi vao {duong_dan_loi}")

    # === THONG KE CUOI ===
    troi_qua = time.time() - bat_dau
    print("\n=== THONG KE ===")
    if theo_zoom:
        print("  Tile theo zoom (tong so trong vung):")
        for z, n in sorted(theo_zoom.items()):
            print(f"    z={z:<3} {n:>10,}")
    print(f"  Tai moi       : {tong['moi']:,}")
    print(f"  Bo qua (da co): {tong['bo_qua']:,}")
    print(f"  404 khong co  : {tong['khong_co']:,}")
    print(f"  Loi           : {tong['loi']:,}")
    print(f"  Dung luong tai: {_dinh_dang_dung_luong(tong['byte'])}")
    print(f"  Thoi gian     : {_dinh_dang_thoi_gian(troi_qua)}")

    if bi_chan:
        return 2
    if bi_ngat:
        return 130  # quy uoc chuan cho SIGINT
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Tai tile OSM ve dia cho ban do offline (chay tren may CO MANG).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Mac dinh: bao tron Viet Nam (gom ca Truong Sa/Hoang Sa nam trong lon 102-110)
    p.add_argument("--min-lon", type=float, default=102.0)
    p.add_argument("--max-lon", type=float, default=110.0)
    p.add_argument("--min-lat", type=float, default=8.2)
    p.add_argument("--max-lat", type=float, default=23.5)
    # ZOOM - moi muc zoom TANG 1 thi so tile x4 (chia doi ca 2 chieu):
    #   z=6  : ca Viet Nam gon trong 1 man hinh
    #   z=12 : ca thanh pho, thay ten phuong - DU cho nghiep vu R012 (xem quan he
    #          tram goc <-> cell lan can, cach nhau vai tram met den vai km)
    #   z=13 : bien an toan cho cac cell rat sat nhau (do thi day dac)
    #   z=14+: thay ten duong/so nha - KHONG phuc vu danh gia vung phu song, ma
    #          ton x4 dung luong VA x4 thoi gian cho MOI muc them vao
    p.add_argument("--min-zoom", type=int, default=6)
    p.add_argument("--max-zoom", type=int, default=13)
    p.add_argument("--output", default="./osm_tiles")
    p.add_argument("--delay", type=float, default=0.5,
                   help="giay giua 2 request - DUNG giam de chay nhanh, se bi OSM chan IP")
    p.add_argument("--user-agent",
                   default="R012-NQMProactiveCC-4G/1.0 (VNPT-Net internal NOC tool)",
                   help="OSM policy BAT BUOC User-Agent ro rang, khong duoc de mac dinh cua urllib")
    p.add_argument("--dry-run", action="store_true", help="chi tinh va in, KHONG tai")
    args = p.parse_args()

    if args.min_zoom > args.max_zoom:
        print("Loi: --min-zoom > --max-zoom", file=sys.stderr)
        return 1
    if args.min_lon > args.max_lon or args.min_lat > args.max_lat:
        print("Loi: khoang lon/lat nguoc chieu (min > max)", file=sys.stderr)
        return 1

    if args.dry_run:
        chay_dry_run(args)
        return 0
    return chay_tai_that(args)


if __name__ == "__main__":
    sys.exit(main())
