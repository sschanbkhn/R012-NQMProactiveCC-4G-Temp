"""
Unit test scripts/convert_netact_servers.py (23/10/2026). Mat khau GIA, ghi vao
tmp_path - khong cham .env that.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "convert_netact_servers", Path(__file__).resolve().parents[2] / "scripts" / "convert_netact_servers.py"
)
cv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cv)

_PW = "pw-GIA-khong-duoc-in"


def _env(tmp_path, raw: dict) -> Path:
    p = tmp_path / ".env"
    p.write_text("A=1\nNETACT_SERVERS=" + json.dumps(raw) + "\nB=2\n", encoding="utf-8")
    return p


def test_dinh_dang_cu_gom_theo_host_thanh_na_va_routes_lien_nhau(tmp_path, capsys):
    raw = {"HGG": {"host": "10.212.247.20", "user": "thembv", "password": _PW},
           "HNI": {"host": "10.212.242.20", "user": "thembv", "password": _PW},
           "CBG": {"host": "10.212.247.20", "user": "thembv", "password": _PW}}
    out = tmp_path / "s" / "r012_netact_servers.json"
    assert cv.main(["--env", str(_env(tmp_path, raw)), "--out", str(out)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert list(d["instances"]) == ["NA09", "NA14"]
    assert d["instances"]["NA14"] == {"host": "10.212.247.20", "user": "thembv", "password": _PW, "noc": "NOC1"}
    # Routes NA09 truoc, NA14 sau, trong NA theo thu tu bang (CBG truoc HGG).
    assert list(d["routes"]) == ["HNI|NOKIA", "CBG|NOKIA", "HGG|NOKIA"]
    assert out.read_text(encoding="utf-8").count(_PW) == 2  # moi NA 1 lan
    in_ra = capsys.readouterr().out
    assert _PW not in in_ra and "NA14 | 10.212.247.20 | thembv | NOC1 | 2 | co" in in_ra


def test_2_tinh_cung_host_khac_mat_khau_thi_dung(tmp_path, capsys):
    raw = {"CBG": {"host": "10.212.247.20", "user": "thembv", "password": _PW},
           "HGG": {"host": "10.212.247.20", "user": "thembv", "password": _PW + "x"}}
    out = tmp_path / "o.json"
    assert cv.main(["--env", str(_env(tmp_path, raw)), "--out", str(out)]) == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert "NA14" in err and "password KHAC" in err and _PW not in err


def test_dinh_dang_moi_giu_ten_na_dien_noc_thieu(tmp_path):
    raw = {"instances": {"NA11": {"host": "10.212.244.20", "user": "thembv", "password": _PW}},
           "routes": {"KTM|NOKIA": "NA11", "DLK|NOKIA": "NA11"}}
    out = tmp_path / "o.json"
    assert cv.main(["--env", str(_env(tmp_path, raw)), "--out", str(out)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["instances"]["NA11"]["noc"] == "NOC3"
    assert list(d["routes"]) == ["DLK|NOKIA", "KTM|NOKIA"]


def test_khong_ghi_de_tru_khi_force_va_backup(tmp_path):
    raw = {"HNI": {"host": "10.212.242.20", "user": "thembv", "password": _PW}}
    env, out = _env(tmp_path, raw), tmp_path / "o.json"
    out.write_text("cu", encoding="utf-8")
    assert cv.main(["--env", str(env), "--out", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == "cu"
    assert cv.main(["--env", str(env), "--out", str(out), "--force"]) == 0
    assert [p.read_text(encoding="utf-8") for p in tmp_path.glob("o.json.bak_*")] == ["cu"]


def test_host_la_khong_co_trong_bang_thi_dung(tmp_path):
    raw = {"XXX": {"host": "1.2.3.4", "user": "u", "password": _PW}}
    assert cv.main(["--env", str(_env(tmp_path, raw)), "--out", str(tmp_path / "o.json")]) == 1


@pytest.mark.parametrize("mau", ["netact_servers.example.json"])
def test_file_mau_chuyen_lai_khong_doi(mau):
    # Example la dinh dang MOI da sap xep - chay qua chuyen_doi phai giu nguyen.
    d = json.loads(Path(mau).read_text(encoding="utf-8"))
    assert cv.chuyen_doi(d) == d
