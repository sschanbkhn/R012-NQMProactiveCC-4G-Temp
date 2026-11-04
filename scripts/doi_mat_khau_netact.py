"""
Doi mat khau NetAct theo HOST (23/10/2026) - cho file JSON NETACT_SERVERS_FILE
va/hoac dong NETACT_SERVERS trong .env, trong 1 lan chay.

VI SAO LOC THEO HOST: moi NA giu mat khau rieng (23/10/2026: mat khau moi vao
NA09 + NA14, NA10/11/12 tu choi) - doi dong loat moi muc se lam hong NA chua
doi. Host la khoa on dinh o CA 2 dinh dang .env (cu: khoa theo tinh, 7 tinh
NA14 lap lai host; moi: instances) va ca file JSON.

VI SAO getpass: mat khau khong nam tren dong lenh (khong vao history, khong
hien trong `ps`), khong in ra man hinh. Nhap 2 lan de tranh go sai.

VI SAO CHI stdlib: phai chay duoc ca khi ROLLBACK ve code cu (venv cu, khong
dam bao co python-dotenv) - goi bang duong dan script cua goi moi.

Moi file sua deu duoc backup (<ten>.bak_<thoi_gian>, quyen 600) truoc khi ghi.
.env giu NGUYEN cac dong khac, NETACT_SERVERS van la JSON 1 DONG (systemd
EnvironmentFile khong hieu gia tri nhieu dong).

Chay:
  python3 scripts/doi_mat_khau_netact.py --host 10.212.242.20 --host 10.212.247.20 \\
      --file /home/auto/secrets/r012_netact_servers.json --env .env
"""

import argparse
import getpass
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path

_DONG_ENV = re.compile(r"^NETACT_SERVERS=(.*)$", re.M)


class LoiDoiMatKhau(Exception):
    pass


def _cac_muc(d: dict) -> dict[str, dict]:
    # Dinh dang moi: instances; dinh dang cu: chinh dict (khoa theo tinh).
    return d["instances"] if "instances" in d or "routes" in d else d


def _doi(d: dict, hosts: set[str], mat_khau: str) -> list[tuple[str, str, str]]:
    """Doi password cac muc co host trong `hosts`. Tra (khoa, host, ket qua)."""
    kq = []
    for khoa, v in _cac_muc(d).items():
        if v.get("host") in hosts:
            v["password"] = mat_khau
            kq.append((khoa, v.get("host"), "DA DOI"))
        else:
            kq.append((khoa, v.get("host"), "giu nguyen"))
    return kq


def _backup(p: Path) -> Path:
    bak = p.with_name(f"{p.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(p, bak)
    os.chmod(bak, 0o600)  # ban backup cung chua mat khau
    return bak


def _ghi_giu_quyen(p: Path, noi_dung: str, mac_dinh: int = 0o600) -> None:
    # Giu quyen file goc (vd .env 600/640); file moi -> 600.
    quyen = stat.S_IMODE(p.stat().st_mode) if p.exists() else mac_dinh
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, quyen)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(noi_dung)
    if os.name == "posix":
        os.chmod(p, quyen)


def doi_file_json(p: Path, hosts: set[str], mat_khau: str) -> list:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoiDoiMatKhau(f"{p}: khong doc duoc JSON ({type(exc).__name__})") from None
    kq = _doi(d, hosts, mat_khau)
    bak = _backup(p)
    _ghi_giu_quyen(p, json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print(f"Da sua {p} (backup: {bak})")
    return kq


def doi_env(p: Path, hosts: set[str], mat_khau: str) -> list:
    s = p.read_text(encoding="utf-8")
    m = _DONG_ENV.search(s)
    if not m:
        raise LoiDoiMatKhau(f"{p}: khong co dong NETACT_SERVERS=")
    gia_tri = m.group(1).strip()
    nhay = gia_tri[0] if gia_tri[:1] in ("'", '"') and gia_tri[-1:] == gia_tri[:1] else ""
    try:
        d = json.loads(gia_tri[1:-1] if nhay else gia_tri)
    except json.JSONDecodeError as exc:
        raise LoiDoiMatKhau(f"{p}: NETACT_SERVERS khong phai JSON hop le (cot {exc.colno})") from None
    kq = _doi(d, hosts, mat_khau)
    moi = "NETACT_SERVERS=" + nhay + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + nhay
    bak = _backup(p)
    _ghi_giu_quyen(p, s[:m.start()] + moi + s[m.end():])
    print(f"Da sua {p} (backup: {bak})")
    return kq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Doi mat khau NetAct theo host (getpass)")
    ap.add_argument("--host", action="append", required=True, help="host can doi (lap lai de chon nhieu)")
    ap.add_argument("--file", help="file JSON NETACT_SERVERS_FILE")
    ap.add_argument("--env", help="file .env chua dong NETACT_SERVERS")
    a = ap.parse_args(argv)
    if not a.file and not a.env:
        print("LOI: can it nhat --file hoac --env", file=sys.stderr)
        return 1
    hosts = set(a.host)

    mat_khau = getpass.getpass("Mat khau moi: ")
    if not mat_khau or mat_khau != getpass.getpass("Nhap lai: "):
        print("LOI: mat khau rong hoac 2 lan nhap khong khop - khong sua gi", file=sys.stderr)
        return 1

    try:
        for nhan, p, ham in (("file", a.file, doi_file_json), ("env", a.env, doi_env)):
            if not p:
                continue
            kq = ham(Path(p), hosts, mat_khau)
            khop = {h for _, h, r in kq if r == "DA DOI"}
            for khoa, host, r in kq:
                print(f"  [{nhan}] {khoa} | {host} | {r}")
            # Host go sai -> khong muc nao doi: bao ro de nguoi chay khong tuong da doi.
            for h in sorted(hosts - khop):
                print(f"  CANH BAO [{nhan}]: khong co muc nao host {h}")
    except LoiDoiMatKhau as exc:
        print(f"LOI: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
