"""
Unit test cho OssRouterEnv (implement IOssRouter.chon_oss()) - doc
NETACT_SERVERS tu .env, ho tro CA 2 dinh dang (MOI/CU).
Tu: Giai doan 1 buoc 2 (27/09/2026, dinh tuyen OSS theo tung cell).
"""

import json

import pytest

from adapters.netact.oss_router_env import OssRouterEnv
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.vendor import Vendor

_DINH_DANG_MOI = json.dumps(
    {
        "instances": {
            "NA09": {"host": "10.212.242.20", "user": "test_user", "password": "test_password"},
            "NA14": {"host": "10.212.247.20", "user": "???", "password": "???"},
        },
        "routes": {
            "HNI|NOKIA": "NA09",
            "HGG|NOKIA": "NA14",
            "CBG|NOKIA": "NA14",
        },
    }
)

_DINH_DANG_CU = json.dumps(
    {
        "HNI": {"host": "10.212.242.20", "user": "test_user", "password": "test_password"},
        "CBG": {"host": "10.212.247.20", "user": "???", "password": "???"},
    }
)

# .env that (server .196/.197) dang co 7 khoa CBG/DBN/SLA/HGG/LCU/LSN/LCI
# CUNG 1 host NetAct14 (10.212.247.20) - fixture rieng day de test bug that:
# neu instance_id lay theo KHOA (thay vi host) thi 7 khoa nay thanh 7
# OssInstance khac nhau du CUNG 1 server vat ly, khien 2 cell CUNG NetAct14
# nhung khac tinh cu (vd -CBG va -HGG) bi coi la 2 OSS -> CR_NHIEU_OSS oan.
_DINH_DANG_CU_NETACT14_NHIEU_KHOA_CUNG_HOST = json.dumps(
    {
        "CBG": {"host": "10.212.247.20", "user": "test_user", "password": "test_password"},
        "HGG": {"host": "10.212.247.20", "user": "test_user", "password": "test_password"},
    }
)


@pytest.fixture(autouse=True)
def _khong_file(monkeypatch):
    # 23/10/2026: NETACT_SERVERS_FILE uu tien hon NETACT_SERVERS - .env may dev
    # co bien nay thi moi test o day se doc file that thay vi fixture.
    monkeypatch.delenv("NETACT_SERVERS_FILE", raising=False)
    # Ban nho "cau hinh hop le gan nhat" la bien module - xoa giua cac test de
    # test sau khong vo tinh dung cau hinh cua test truoc.
    monkeypatch.setattr("adapters.netact.oss_router_env._ban_nho", None)


@pytest.fixture
def dinh_dang_moi(monkeypatch):
    monkeypatch.setenv("NETACT_SERVERS", _DINH_DANG_MOI)


@pytest.fixture
def dinh_dang_cu(monkeypatch):
    monkeypatch.setenv("NETACT_SERVERS", _DINH_DANG_CU)


# === Dinh dang MOI ===


def test_dinh_dang_moi_HNI_ra_dung_instance(dinh_dang_moi):
    router = OssRouterEnv()
    oss = router.chon_oss("HNI", Vendor.NOKIA)
    assert oss == OssInstance(instance_id="NA09", host="10.212.242.20", user="test_user", password="test_password")


def test_dinh_dang_moi_nhieu_tinh_cu_tro_ve_CUNG_1_instance(monkeypatch):
    # HGG va CBG (2 tinh cu KHAC nhau) deu route ve CUNG 1 instance NA_CHUNG
    # - dung khoa (ma_tinh_cu, vendor) -> 1 OSS, KHONG phai 1-1. Fixture RIENG
    # (khong dung dinh_dang_moi/NA14 - instance do CO Y de credential
    # placeholder cho test khac, dung chung se nham 2 dieu kien).
    monkeypatch.setenv(
        "NETACT_SERVERS",
        json.dumps(
            {
                "instances": {
                    "NA_CHUNG": {"host": "10.212.247.20", "user": "test_user", "password": "test_password"},
                },
                "routes": {"HGG|NOKIA": "NA_CHUNG", "CBG|NOKIA": "NA_CHUNG"},
            }
        ),
    )
    router = OssRouterEnv()
    oss_hgg = router.chon_oss("HGG", Vendor.NOKIA)
    oss_cbg = router.chon_oss("CBG", Vendor.NOKIA)
    assert oss_hgg is not None
    assert oss_hgg == oss_cbg


def test_dinh_dang_moi_credential_placeholder_tra_None(dinh_dang_moi):
    # NA14 (route cua HGG/CBG) co user/password con la "???" - coi nhu CHUA
    # cau hinh, KHONG cho ket noi voi credential gia.
    router = OssRouterEnv()
    assert router.chon_oss("HGG", Vendor.NOKIA) is None


def test_dinh_dang_moi_khong_co_route_tra_None(dinh_dang_moi):
    router = OssRouterEnv()
    assert router.chon_oss("SLA", Vendor.NOKIA) is None


def test_dinh_dang_moi_vendor_khac_khong_co_route_tra_None(dinh_dang_moi):
    # Chi co route "...|NOKIA" trong fixture - vendor khac (vd HUAWEI/UNKNOWN)
    # khong khop khoa nao.
    router = OssRouterEnv()
    assert router.chon_oss("HNI", Vendor.HUAWEI) is None


# === Dinh dang CU (phang) ===


def test_dinh_dang_cu_van_chay_dung(dinh_dang_cu):
    # .env server (.196/.197) KHONG bat buoc phai sua LUC DEPLOY ban nay -
    # dinh dang cu (truoc Giai doan 1) van phai cho ra dung OssInstance,
    # tu suy route "<khoa>|NOKIA" -> instance (xem docstring OssRouterEnv).
    # instance_id = HOST (khong phai khoa "HNI") - xem bug fix
    # test_dinh_dang_cu_2_khoa_cung_host_ra_CUNG_1_instance ben duoi.
    # noc="NOC1" (02/10/2026) - dinh dang cu GAN CUNG, xem docstring OssRouterEnv.
    router = OssRouterEnv()
    oss = router.chon_oss("HNI", Vendor.NOKIA)
    assert oss == OssInstance(
        instance_id="10.212.242.20", host="10.212.242.20", user="test_user", password="test_password", noc="NOC1"
    )


def test_dinh_dang_cu_placeholder_tra_None(dinh_dang_cu):
    router = OssRouterEnv()
    assert router.chon_oss("CBG", Vendor.NOKIA) is None


def test_dinh_dang_cu_2_khoa_cung_host_ra_CUNG_1_instance(monkeypatch):
    # Bug that (27/09/2026): .env server .196/.197 co 7 khoa
    # CBG/DBN/SLA/HGG/LCU/LSN/LCI CUNG host NetAct14 - truoc khi sua, moi
    # khoa sinh 1 OssInstance rieng (instance_id = khoa) nen cell -CBG +
    # cell -HGG (dinh tuyen theo TriggerCrUseCase._chon_oss_va_loc_cells(),
    # gom nhom bang so sanh == giua OssInstance) bi coi la 2 OSS khac nhau
    # -> raise CR_NHIEU_OSS oan du thuc chat CUNG 1 server vat ly. Sua:
    # instance_id lay theo host -> 2 khoa nay PHAI ra CUNG 1 OssInstance.
    monkeypatch.setenv("NETACT_SERVERS", _DINH_DANG_CU_NETACT14_NHIEU_KHOA_CUNG_HOST)
    router = OssRouterEnv()
    oss_cbg = router.chon_oss("CBG", Vendor.NOKIA)
    oss_hgg = router.chon_oss("HGG", Vendor.NOKIA)
    assert oss_cbg is not None
    assert oss_cbg == oss_hgg  # CUNG 1 OssInstance -> gom 1 nhom, KHONG raise CR_NHIEU_OSS
    assert oss_cbg.instance_id == "10.212.247.20"  # instance_id = host, khong phai khoa


def test_dinh_dang_cu_2_khoa_khac_host_ra_2_instance_khac_nhau(monkeypatch):
    # Doi chieu voi test tren: 2 khoa KHAC host nhau thi PHAI la 2 OssInstance
    # khac nhau (dung credential that ca 2 ben, khong dung dinh_dang_cu fixture
    # - khoa CBG cua no bi placeholder nen se tra None, khong the sanh != ro rang).
    monkeypatch.setenv(
        "NETACT_SERVERS",
        json.dumps(
            {
                "HNI": {"host": "10.212.242.20", "user": "test_user", "password": "test_password"},
                "CBG": {"host": "10.212.247.20", "user": "test_user", "password": "test_password"},
            }
        ),
    )
    router = OssRouterEnv()
    oss_hni = router.chon_oss("HNI", Vendor.NOKIA)
    oss_cbg = router.chon_oss("CBG", Vendor.NOKIA)
    assert oss_hni is not None and oss_cbg is not None
    assert oss_hni != oss_cbg  # 2 host khac nhau -> 2 OSS khac nhau -> se raise CR_NHIEU_OSS neu 1 CR dung ca 2


def test_dinh_dang_cu_vendor_khac_NOKIA_khong_co_route(dinh_dang_cu):
    # Dinh dang cu CHI suy ra route cho NOKIA (he thong hien tai chi quan ly
    # Nokia qua NetAct) - vendor khac khong co route du khoa (ma_tinh_cu)
    # ton tai trong instances.
    router = OssRouterEnv()
    assert router.chon_oss("HNI", Vendor.HUAWEI) is None


# === Rong / thieu bien ===


def test_khong_co_NETACT_SERVERS_tra_None(monkeypatch):
    monkeypatch.delenv("NETACT_SERVERS", raising=False)
    router = OssRouterEnv()
    assert router.chon_oss("HNI", Vendor.NOKIA) is None


# === Field "noc" (02/10/2026 - cr_session luu NetAct + NOC) ===


def test_dinh_dang_cu_noc_la_NOC1_cho_moi_instance(monkeypatch):
    # Item 4 (02/10/2026) - dinh dang CU GAN CUNG noc="NOC1" cho TAT CA instance,
    # khong phan biet khoa/host nao - he thong truoc Giai doan 1 chi chay 1
    # vung (HNI), xac nhan voi user.
    monkeypatch.setenv("NETACT_SERVERS", _DINH_DANG_CU)
    router = OssRouterEnv()
    oss_hni = router.chon_oss("HNI", Vendor.NOKIA)
    assert oss_hni.noc == "NOC1"


def test_dinh_dang_moi_co_khoa_noc_dung_gia_tri_do(monkeypatch):
    monkeypatch.setenv(
        "NETACT_SERVERS",
        json.dumps(
            {
                "instances": {
                    "NA09": {"host": "10.212.242.20", "user": "test_user", "password": "test_password", "noc": "NOC1"},
                    "NA99": {"host": "10.212.247.99", "user": "test_user", "password": "test_password", "noc": "NOC2"},
                },
                "routes": {"HNI|NOKIA": "NA09", "ABC|NOKIA": "NA99"},
            }
        ),
    )
    router = OssRouterEnv()
    assert router.chon_oss("HNI", Vendor.NOKIA).noc == "NOC1"
    assert router.chon_oss("ABC", Vendor.NOKIA).noc == "NOC2"


def test_dinh_dang_moi_thieu_khoa_noc_tra_None_khong_doan(dinh_dang_moi):
    # Dinh dang MOI KHONG tu doan "NOC1" khi thieu khoa "noc" trong instance -
    # khac dinh dang CU (xem docstring OssRouterEnv muc a). _DINH_DANG_MOI
    # (NA09) khong co khoa "noc".
    router = OssRouterEnv()
    oss = router.chon_oss("HNI", Vendor.NOKIA)
    assert oss.noc is None


# === NETACT_SERVERS_FILE + kiem tra khoi dong (23/10/2026) ===

from adapters.netact.oss_router_env import NetactConfigError, kiem_tra_khi_khoi_dong  # noqa: E402
from domain.errors import CauHinhNetactLoiError  # noqa: E402

_MAT_KHAU_GIA = "pw-KHONG-DUOC-LOG"


def _ghi(tmp_path, noi_dung: str):
    p = tmp_path / "r012_netact_servers.json"
    p.write_text(noi_dung, encoding="utf-8")
    return p


def test_file_uu_tien_hon_env_va_doc_json_nhieu_dong(tmp_path, monkeypatch):
    # JSON nhieu dong (indent 2) - ly do ton tai cua NETACT_SERVERS_FILE.
    p = _ghi(tmp_path, json.dumps({
        "instances": {"NA14": {"host": "10.212.247.20", "user": "thembv", "password": _MAT_KHAU_GIA}},
        "routes": {"HGG|NOKIA": "NA14"},
    }, indent=2))
    monkeypatch.setenv("NETACT_SERVERS_FILE", str(p))
    monkeypatch.setenv("NETACT_SERVERS", _DINH_DANG_MOI)  # bi bo qua vi co FILE
    router = OssRouterEnv()
    assert router.chon_oss("HGG", Vendor.NOKIA).user == "thembv"
    assert router.chon_oss("HNI", Vendor.NOKIA) is None  # chi co trong env, khong co trong file


def test_khong_co_file_thi_dung_env_dinh_dang_cu(dinh_dang_cu):
    oss = OssRouterEnv().chon_oss("HNI", Vendor.NOKIA)
    assert oss.host == "10.212.242.20" and oss.noc == "NOC1"


def test_file_khong_ton_tai_bao_loi_ro_ten_bien_va_duong_dan(tmp_path, monkeypatch):
    p = tmp_path / "khong_co.json"
    monkeypatch.setenv("NETACT_SERVERS_FILE", str(p))
    with pytest.raises(NetactConfigError, match=r"NETACT_SERVERS_FILE=.*khong_co\.json.*khong ton tai"):
        kiem_tra_khi_khoi_dong()


def test_file_json_hong_bao_loi_khong_lo_noi_dung(tmp_path, monkeypatch):
    p = _ghi(tmp_path, '{"instances": {"NA09": {"password": "' + _MAT_KHAU_GIA + '"')
    monkeypatch.setenv("NETACT_SERVERS_FILE", str(p))
    # Chua tung doc duoc -> CauHinhNetactLoiError (422), khong lo noi dung file.
    with pytest.raises(CauHinhNetactLoiError) as exc:
        OssRouterEnv()
    assert exc.value.error_code == "CAU_HINH_NETACT_LOI" and _MAT_KHAU_GIA not in str(exc.value)
    with pytest.raises(NetactConfigError):  # luc khoi dong: app khong len
        kiem_tra_khi_khoi_dong()


def test_route_tro_toi_na_khong_ton_tai_va_thieu_password_chi_canh_bao(tmp_path, monkeypatch, caplog):
    p = _ghi(tmp_path, json.dumps({
        "instances": {
            "NA09": {"host": "10.212.242.20", "user": "thembv", "password": _MAT_KHAU_GIA, "noc": "NOC1"},
            "NA10": {"host": "10.212.243.20", "user": "thembv", "password": ""},
        },
        "routes": {"HNI|NOKIA": "NA09", "HCM|NOKIA": "NA10", "DLK|NOKIA": "NA11"},
    }))
    monkeypatch.setenv("NETACT_SERVERS_FILE", str(p))
    caplog.set_level("INFO", logger="adapters.netact.oss_router_env")
    canh_bao = kiem_tra_khi_khoi_dong()  # KHONG raise - NA09 van phai chay duoc
    assert "route DLK|NOKIA -> NA11: instance khong ton tai" in canh_bao
    assert "NA10: thieu password" in canh_bao
    log = caplog.text
    assert "NetAct NA09 host=10.212.242.20 user=thembv noc=NOC1 so_tinh=1 trang_thai=OK" in log
    assert "NA10" in log and "THIEU password" in log
    assert _MAT_KHAU_GIA not in log
    r = OssRouterEnv()
    assert r.chon_oss("HNI", Vendor.NOKIA) is not None
    assert r.chon_oss("HCM", Vendor.NOKIA) is None and r.chon_oss("DLK", Vendor.NOKIA) is None


def test_file_mau_trong_repo_hop_le_va_password_rong(monkeypatch):
    # netact_servers.example.json: 5 NA, 28 tinh, moi route tro dung NA co that.
    monkeypatch.setenv("NETACT_SERVERS_FILE", "netact_servers.example.json")
    canh_bao = kiem_tra_khi_khoi_dong()
    assert sorted(c for c in canh_bao if "route" in c) == []
    assert len([c for c in canh_bao if c.endswith("thieu password")]) == 5
    r = OssRouterEnv()
    assert sorted(r._instances) == ["NA09", "NA10", "NA11", "NA12", "NA14"] and len(r._routes) == 28


def test_ly_do_khong_chon_noi_ro_na_va_truong_thieu(monkeypatch):
    monkeypatch.setenv("NETACT_SERVERS", json.dumps({
        "instances": {"NA14": {"host": "10.212.247.20", "user": "thembv", "password": ""},
                      "NA09": {"host": "10.212.242.20", "user": "thembv", "password": _MAT_KHAU_GIA}},
        "routes": {"HGG|NOKIA": "NA14", "HNI|NOKIA": "NA09", "DLK|NOKIA": "NA11"},
    }))
    r = OssRouterEnv()
    assert r.ly_do_khong_chon("HGG", Vendor.NOKIA) == "NA14 cau hinh loi: thieu password"
    assert r.ly_do_khong_chon("DLK", Vendor.NOKIA) == "NA11 cau hinh loi: route DLK|NOKIA tro toi NA khong ton tai"
    assert r.ly_do_khong_chon("XXX", Vendor.NOKIA) == "chua co route XXX|NOKIA trong cau hinh NetAct"
    assert r.ly_do_khong_chon("HNI", Vendor.NOKIA) is None


def test_file_bi_sua_hong_khi_dang_chay_giu_ban_hop_le_gan_nhat(tmp_path, monkeypatch, caplog):
    # 23/10/2026: go sai JSON luc doi mat khau khong duoc lam dung CR.
    p = _ghi(tmp_path, json.dumps({
        "instances": {"NA09": {"host": "10.212.242.20", "user": "thembv", "password": _MAT_KHAU_GIA}},
        "routes": {"HNI|NOKIA": "NA09"},
    }))
    monkeypatch.setenv("NETACT_SERVERS_FILE", str(p))
    assert OssRouterEnv().chon_oss("HNI", Vendor.NOKIA).instance_id == "NA09"

    p.write_text('{"instances": {"NA09": {"password": "' + _MAT_KHAU_GIA + '"', encoding="utf-8")  # hong
    caplog.set_level("ERROR", logger="adapters.netact.oss_router_env")
    oss = OssRouterEnv().chon_oss("HNI", Vendor.NOKIA)
    assert oss is not None and oss.instance_id == "NA09"
    assert "NetAct cau hinh HONG, dung ban hop le gan nhat" in caplog.text
    assert _MAT_KHAU_GIA not in caplog.text


def test_api_preview_cau_hinh_hong_tu_dau_tra_422_khong_500(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setenv("NETACT_SERVERS_FILE", str(tmp_path / "khong_co.json"))
    # KHONG dung "with TestClient" (lifespan se chan khoi dong) - mo phong file
    # hong SAU khi app da len.
    r = TestClient(main.app).post("/api/v1/cr/preview", json={"tram_id": "114664", "action": "shutdown"})
    assert r.status_code == 422
    assert r.json()["error_code"] == "CAU_HINH_NETACT_LOI"
