"""
Unit test scripts/doi_mat_khau_netact.py (23/10/2026). Mat khau GIA, file trong
tmp_path; getpass duoc mock.
"""

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "doi_mat_khau_netact", Path(__file__).resolve().parents[2] / "scripts" / "doi_mat_khau_netact.py"
)
dm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dm)

_CU, _MOI = "pw-CU", "pw-MOI-khong-duoc-in"
_H09, _H10, _H14 = "10.212.242.20", "10.212.243.20", "10.212.247.20"


def _nhap(monkeypatch, *lan):
    it = iter(lan)
    monkeypatch.setattr(dm.getpass, "getpass", lambda _="": next(it))


def _moi_dinh_dang():
    return {"instances": {
        "NA09": {"host": _H09, "user": "thembv", "password": _CU, "noc": "NOC1"},
        "NA10": {"host": _H10, "user": "thembv", "password": _CU, "noc": "NOC2"},
        "NA14": {"host": _H14, "user": "thembv", "password": _CU, "noc": "NOC1"},
    }, "routes": {"HNI|NOKIA": "NA09", "HCM|NOKIA": "NA10", "HGG|NOKIA": "NA14"}}


def test_doi_theo_host_ca_file_json_va_env_giu_na10(tmp_path, monkeypatch, capsys):
    f = tmp_path / "r012_netact_servers.json"
    f.write_text(json.dumps(_moi_dinh_dang(), indent=2), encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("A=1\nNETACT_SERVERS=" + json.dumps(_moi_dinh_dang()) + "\nB=2", encoding="utf-8")
    _nhap(monkeypatch, _MOI, _MOI)

    assert dm.main(["--host", _H09, "--host", _H14, "--file", str(f), "--env", str(env)]) == 0

    d = json.loads(f.read_text(encoding="utf-8"))
    assert {k: v["password"] for k, v in d["instances"].items()} == {"NA09": _MOI, "NA10": _CU, "NA14": _MOI}
    s = env.read_text(encoding="utf-8")
    dong = [x for x in s.splitlines() if x.startswith("NETACT_SERVERS=")]
    assert len(dong) == 1 and s.startswith("A=1\n") and s.endswith("B=2")  # giu dong khac, 1 dong JSON
    e = json.loads(dong[0].split("=", 1)[1])
    assert {k: v["password"] for k, v in e["instances"].items()} == {"NA09": _MOI, "NA10": _CU, "NA14": _MOI}
    assert len(list(tmp_path.glob("*.bak_*"))) == 2
    assert _MOI not in capsys.readouterr().out


def test_env_dinh_dang_cu_7_tinh_cung_host_doi_het(tmp_path, monkeypatch):
    cu = {"HNI": {"host": _H09, "user": "thembv", "password": _CU},
          "CBG": {"host": _H14, "user": "thembv", "password": _CU},
          "HGG": {"host": _H14, "user": "thembv", "password": _CU}}
    env = tmp_path / ".env"
    env.write_text("NETACT_SERVERS=" + json.dumps(cu) + "\n", encoding="utf-8")
    _nhap(monkeypatch, _MOI, _MOI)
    assert dm.main(["--host", _H14, "--env", str(env)]) == 0
    e = json.loads(env.read_text(encoding="utf-8").split("=", 1)[1])
    assert {k: v["password"] for k, v in e.items()} == {"HNI": _CU, "CBG": _MOI, "HGG": _MOI}


def test_nhap_2_lan_khong_khop_khong_sua_gi(tmp_path, monkeypatch):
    f = tmp_path / "f.json"
    f.write_text(json.dumps(_moi_dinh_dang()), encoding="utf-8")
    truoc = f.read_text(encoding="utf-8")
    _nhap(monkeypatch, _MOI, _MOI + "x")
    assert dm.main(["--host", _H09, "--file", str(f)]) == 1
    assert f.read_text(encoding="utf-8") == truoc and not list(tmp_path.glob("*.bak_*"))


def test_host_go_sai_canh_bao(tmp_path, monkeypatch, capsys):
    f = tmp_path / "f.json"
    f.write_text(json.dumps(_moi_dinh_dang()), encoding="utf-8")
    _nhap(monkeypatch, _MOI, _MOI)
    assert dm.main(["--host", "10.0.0.1", "--file", str(f)]) == 0
    assert "khong co muc nao host 10.0.0.1" in capsys.readouterr().out
