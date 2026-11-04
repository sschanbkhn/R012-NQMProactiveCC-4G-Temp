"""
Chuyen NETACT_SERVERS (1 dong JSON trong .env) -> file JSON nhieu dong cho
NETACT_SERVERS_FILE (quyet dinh 23/10/2026).

VI SAO: moi NA co mat khau/han rieng (23/10/2026: mat khau moi vao NA09 +
NA14, NA10/11/12 tu choi). Doi mat khau trong 1 dong JSON dai rat de sua nham
NA. Service .196 nap .env bang systemd EnvironmentFile nen KHONG viet JSON
nhieu dong trong .env duoc -> tach ra file rieng, moi NA 1 khoi, moi mat khau
xuat hien DUNG 1 LAN.

Nhan CA 2 dinh dang (giong adapters/netact/oss_router_env.py):
  - MOI ({"instances", "routes"}): giu nguyen ten NA, chi sap xep lai.
  - CU (khoa theo tinh): gom theo host -> NA09..NA14. 2 tinh cung host ma
    user/mat khau KHAC nhau -> DUNG, khong tu chon (chon sai = khoa tai khoan).

KHONG in mat khau, KHONG in do dai mat khau (chi "co"/"thieu").
KHONG ghi de file da ton tai tru khi co --force (khi do backup file cu).

Chay:  python scripts/convert_netact_servers.py --env .env --out /home/auto/secrets/r012_netact_servers.json
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

# Bang NA -> host / noc / tinh (user xac nhan 23/10/2026). Thu tu tinh = thu
# tu routes trong file ra, de moi NA la 1 nhom dong lien nhau (JSON khong co
# comment nen khong ghi duoc "nhom NA10" bang chu).
NA = {
    "NA09": ("10.212.242.20", "NOC1", ["HNI"]),
    "NA10": ("10.212.243.20", "NOC2", ["DNO", "HCM", "BPC", "BTN", "LDG", "TNH", "CTO", "AGG", "BTE", "BDG", "DNI"]),
    "NA11": ("10.212.244.20", "NOC3", ["DLK", "GLI", "KTM", "NTN"]),
    "NA12": ("10.212.245.20", "NOC2", ["BLU", "CMU", "HUG", "KGG", "STG"]),
    "NA14": ("10.212.247.20", "NOC1", ["CBG", "DBN", "SLA", "HGG", "LCU", "LSN", "LCI"]),
}
NA_THEO_HOST = {host: na for na, (host, _, _) in NA.items()}
_VENDOR = "NOKIA"  # dinh dang CU chi co NOKIA (xem oss_router_env.py muc b)
_PLACEHOLDER = "???"


class LoiChuyenDoi(Exception):
    pass


def _tu_dinh_dang_cu(raw: dict) -> tuple[dict, dict]:
    instances: dict[str, dict] = {}
    routes: dict[str, str] = {}
    for tinh, server in raw.items():
        host = server.get("host")
        na = NA_THEO_HOST.get(host)
        if na is None:
            raise LoiChuyenDoi(f"tinh {tinh}: host {host} khong co trong bang NA - them vao bang NA truoc")
        moi = {"host": host, "user": server.get("user"), "password": server.get("password")}
        if na in instances:
            cu = instances[na]
            # So sanh nhung KHONG in gia tri - chi noi truong nao lech.
            lech = [k for k in ("user", "password") if cu[k] != moi[k]]
            if lech:
                raise LoiChuyenDoi(f"{na} ({host}): tinh {tinh} co {', '.join(lech)} KHAC cac tinh cung host "
                                   "- khong tu chon, sua NETACT_SERVERS cho thong nhat roi chay lai")
        else:
            instances[na] = {**moi, "noc": server.get("noc") or NA[na][1]}
        routes[f"{tinh}|{_VENDOR}"] = na
    return instances, routes


def _tu_dinh_dang_moi(raw: dict) -> tuple[dict, dict]:
    instances = {k: dict(v) for k, v in raw.get("instances", {}).items()}
    for na, v in instances.items():
        # Dien noc tu bang neu thieu; co san ma khac bang thi GIU ban dang chay
        # (khong am tham doi) va canh bao.
        if na in NA:
            if not v.get("noc"):
                v["noc"] = NA[na][1]
            elif v["noc"] != NA[na][1]:
                print(f"CANH BAO: {na} noc={v['noc']} khac bang ({NA[na][1]}) - giu nguyen {v['noc']}")
    return instances, dict(raw.get("routes", {}))


def _sap_xep(instances: dict, routes: dict) -> dict:
    thu_tu_na = [na for na in NA if na in instances] + sorted(na for na in instances if na not in NA)
    thu_tu_tinh = {f"{t}|{_VENDOR}": i for i, t in enumerate(t for _, _, ds in NA.values() for t in ds)}
    routes_sx = dict(sorted(routes.items(), key=lambda kv: (
        thu_tu_na.index(kv[1]) if kv[1] in thu_tu_na else len(thu_tu_na),
        thu_tu_tinh.get(kv[0], len(thu_tu_tinh)), kv[0])))
    # Thu tu khoa trong instance co dinh: host, user, password, noc.
    inst = {na: {k: instances[na].get(k) for k in ("host", "user", "password", "noc")} for na in thu_tu_na}
    return {"instances": inst, "routes": routes_sx}


def chuyen_doi(raw: dict) -> dict:
    if "instances" in raw or "routes" in raw:
        return _sap_xep(*_tu_dinh_dang_moi(raw))
    return _sap_xep(*_tu_dinh_dang_cu(raw))


def _ghi(out: Path, du_lieu: dict, force: bool) -> None:
    if out.exists():
        if not force:
            raise LoiChuyenDoi(f"{out} da ton tai - khong ghi de (dung --force neu chac chan)")
        bak = out.with_name(f"{out.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(out, bak)
        print(f"Da backup file cu: {bak}")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Tao file voi quyen 600 NGAY tu dau (os.open mode) - khong co khoang thoi
    # gian file chua mat khau mo cho user khac doc. Windows bo qua mode.
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(du_lieu, indent=2, ensure_ascii=False) + "\n")
    if os.name == "posix":
        os.chmod(out, 0o600)  # file da ton tai truoc (--force) giu quyen cu -> ep lai


def in_bang(du_lieu: dict) -> None:
    so_tinh: dict[str, int] = {}
    for na in du_lieu["routes"].values():
        so_tinh[na] = so_tinh.get(na, 0) + 1
    print("NA | host | user | noc | so tinh | password")
    for na, v in du_lieu["instances"].items():
        pw = "co" if v.get("password") and v["password"] != _PLACEHOLDER else "thieu"
        print(f"{na} | {v.get('host')} | {v.get('user')} | {v.get('noc')} | {so_tinh.get(na, 0)} | {pw}")
    mo_coi = sorted({na for na in du_lieu["routes"].values() if na not in du_lieu["instances"]})
    if mo_coi:
        print(f"CANH BAO: route tro toi NA khong co trong instances: {', '.join(mo_coi)}")
    thieu_na = [na for na in NA if na not in du_lieu["instances"]]
    if thieu_na:
        print(f"Luu y: chua co NA {', '.join(thieu_na)} trong nguon - cac tinh do chua chay CR duoc")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--env", default=".env", help="file .env chua NETACT_SERVERS (mac dinh .env)")
    ap.add_argument("--out", required=True, help="duong dan file JSON ra")
    ap.add_argument("--force", action="store_true", help="cho phep ghi de file JSON da co (co backup)")
    a = ap.parse_args(argv)

    try:
        gia_tri = dotenv_values(a.env).get("NETACT_SERVERS")
        if not gia_tri:
            raise LoiChuyenDoi(f"{a.env}: khong co bien NETACT_SERVERS")
        try:
            raw = json.loads(gia_tri)
        except json.JSONDecodeError as exc:
            raise LoiChuyenDoi(f"{a.env}: NETACT_SERVERS khong phai JSON hop le (cot {exc.colno})") from None
        du_lieu = chuyen_doi(raw)
        _ghi(Path(a.out), du_lieu, a.force)
    except LoiChuyenDoi as exc:
        print(f"LOI: {exc}", file=sys.stderr)
        return 1
    print(f"Da ghi {a.out}")
    in_bang(du_lieu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
