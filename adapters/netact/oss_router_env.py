"""
OssRouterEnv — implement IOssRouter.chon_oss(): doc cau hinh NetAct tu file
JSON (NETACT_SERVERS_FILE, 23/10/2026) hoac NETACT_SERVERS trong .env, tra
OssInstance theo khoa (ma_tinh_cu, vendor).
Tu: Giai doan 1 buoc 2 (27/09/2026, dinh tuyen OSS theo tung cell).
LUU Y: get_oss_router() tao OssRouterEnv MOI request -> file JSON duoc doc lai
moi lan chon OSS; nhung NETACT_SERVERS_FILE/NETACT_SERVERS la bien moi truong
(systemd EnvironmentFile) chi nap luc khoi dong -> doi .env phai restart.

=== 2 DINH DANG .env ho tro ===
a) MOI (co "instances"/"routes"):
   {"instances": {"NA09": {"host":.., "user":.., "password":.., "noc":"NOC1"}, ...},
    "routes":    {"HNI|NOKIA": "NA09", "HGG|NOKIA": "NA14", ...}}
   - "instances": 1 OSS vat ly = 1 khoa (instance_id tu dat, vd "NA09" khop
     ten goi NetAct that - KI-08). "noc" (02/10/2026) la khoa TUY CHON trong
     tung instance - don vi van hanh quan ly OSS do (vd "NOC1"/"NOC2"), de
     cr_session luu lai tra lich su. Thieu khoa nay -> OssInstance.noc=None
     (KHONG doan "NOC1" cho instance moi chua xac dinh NOC - khac han dinh
     dang CU o muc b), vi dinh dang MOI la noi se co THEM OSS khac NOC1
     trong tuong lai, doan se sai).
   - "routes": khoa "<ma_tinh_cu>|<vendor>" -> instance_id. Cho phep NHIEU
     tinh cu TRO VE CUNG 1 instance (vd ca 7 tinh Netact14 -> "NA14") ma
     KHONG lap lai host/user/password 7 lan.

b) CU (phang, dang truoc Giai doan 1 - vd {"HNI": {host,user,password}}):
   HIEU la: moi khoa suy ra 1 route "<khoa>|NOKIA" -> instance (he thong
   hien tai CHI co vendor NOKIA duoc quan ly qua NetAct - moi cell khac
   vendor da bi loai o Nhanh A truoc khi toi buoc dinh tuyen, xem
   domain/services/neighbor_cell_filter.py). instance_id lay THEO HOST,
   KHONG lay theo khoa - .env that co 7 khoa (CBG/DBN/SLA/HGG/LCU/LSN/LCI)
   CUNG tro ve 1 host NetAct14 (10.212.247.20); neu lay instance_id = khoa
   thi 7 khoa do thanh 7 OssInstance rieng du CUNG 1 server vat ly, khien
   cell -CBG + cell -HGG (cung NetAct14) bi coi la 2 OSS khac nhau ->
   CR_NHIEU_OSS oan. Nhieu khoa CUNG host phai gom ve CUNG 1 OssInstance.
   VI SAO PHAI HO TRO CA 2: .env server (.196/.197) KHONG duoc sua LUC DEPLOY
   ban nay - deploy code moi ma .env van dang dinh dang CU van phai chay dung
   (KHONG duoc bat nguoi van hanh phai doi .env cung luc voi deploy code,
   2 viec do co the lam boi 2 nguoi khac nhau, 2 thoi diem khac nhau).
   noc (02/10/2026): dinh dang CU GAN CUNG "NOC1" cho MOI instance - he thong
   truoc Giai doan 1 CHI chay 1 vung (HNI), xac nhan voi user "truoc nay chi
   chay HNI" nen gan cung la dung voi thuc te, KHONG phai doan.
"""

import json
import logging
import os
from pathlib import Path

from domain.errors import CauHinhNetactLoiError
from domain.ports.outbound.gateway_ports import IOssRouter
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.vendor import Vendor

logger = logging.getLogger(__name__)

_PLACEHOLDER = "???"

# === NETACT_SERVERS_FILE (quyet dinh 23/10/2026) ===
# Gom mat khau theo NA de doi 1 cho, vi moi NA co mat khau/han rieng (do
# 23/10/2026: mat khau moi vao duoc NA09 + NA14, NA10/11/12 tu choi). JSON 1
# dong trong .env kho tim dung NA de sua; JSON nhieu dong thi KHONG dat duoc
# trong .env vi service .196 nap .env bang systemd EnvironmentFile (khong hieu
# gia tri nhieu dong). Nen tach ra 1 file JSON rieng (chmod 600).
# Thu tu uu tien: NETACT_SERVERS_FILE -> NETACT_SERVERS (giu tuong thich nguoc:
# .env cu chua co bien FILE van chay nhu truoc).
BIEN_FILE = "NETACT_SERVERS_FILE"
BIEN_ENV = "NETACT_SERVERS"


class NetactConfigError(RuntimeError):
    """Cau hinh NetAct HONG TOAN BO (file khai bao ma khong ton tai, JSON sai
    cu phap) - lam app dung luc khoi dong, de nguoi deploy thay ngay thay vi
    phat hien giua 1 CR that."""


def _doc_cau_hinh() -> tuple[dict, str]:
    """Tra (raw dict, mo ta nguon). Raise NetactConfigError neu hong toan bo."""
    duong_dan = os.getenv(BIEN_FILE, "").strip()
    if duong_dan:
        p = Path(duong_dan)
        if not p.is_file():
            # Ghi RO ten bien + duong dan: loi hay gap nhat la go sai duong dan
            # hoac quen tao file tren server.
            raise NetactConfigError(f"{BIEN_FILE}={duong_dan}: file khong ton tai")
        try:
            return json.loads(p.read_text(encoding="utf-8")), f"{BIEN_FILE}={duong_dan}"
        except (OSError, json.JSONDecodeError) as exc:
            # Chi ghi vi tri loi, KHONG ghi noi dung (co the chua mat khau).
            raise NetactConfigError(f"{BIEN_FILE}={duong_dan}: doc/parse JSON loi - {type(exc).__name__} "
                                    f"{getattr(exc, 'lineno', '')}:{getattr(exc, 'colno', '')}") from None
    try:
        return json.loads(os.getenv(BIEN_ENV, "{}")), BIEN_ENV
    except json.JSONDecodeError as exc:
        raise NetactConfigError(f"{BIEN_ENV}: JSON loi o cot {exc.colno} - {exc.msg}") from None


def _thieu(server: dict) -> list[str]:
    """Cac truong bat buoc rong/placeholder cua 1 instance (khong tra gia tri)."""
    return [k for k in ("host", "user", "password")
            if not server.get(k) or server.get(k) == _PLACEHOLDER]


def kiem_tra_khi_khoi_dong() -> list[str]:
    """Goi 1 lan trong lifespan. Log trang thai TUNG NA + so tinh; tra danh sach
    canh bao. KHONG raise cho loi tung phan (1 NA thieu password, 1 route sai) -
    cac NA con lai van phai chay duoc CR; chi raise khi hong toan bo
    (NetactConfigError tu _doc_cau_hinh). KHONG log mat khau."""
    # Doc MOI (khong dung cau hinh nho san): luc khoi dong phai biet file hien
    # tai co hop le khong, khong duoc che bang ban cu trong bo nho.
    _doc_cau_hinh()
    router = OssRouterEnv()
    canh_bao: list[str] = []
    so_tinh: dict[str, int] = {}
    for route, na in router._routes.items():
        if na not in router._instances:
            # Route tro toi NA khong co -> tinh do KHONG chay CR duoc; noi ro
            # thay vi de chon_oss() am tham tra None giua CR.
            canh_bao.append(f"route {route} -> {na}: instance khong ton tai")
        so_tinh[na] = so_tinh.get(na, 0) + 1
    logger.info("NetAct: nguon cau hinh %s, %d NA, %d route",
                router._nguon, len(router._instances), len(router._routes))
    for na, server in router._instances.items():
        thieu = _thieu(server)
        if thieu:
            canh_bao.append(f"{na}: thieu {', '.join(thieu)}")
        logger.info("NetAct %s host=%s user=%s noc=%s so_tinh=%d trang_thai=%s",
                    na, server.get("host"), server.get("user"), server.get("noc"),
                    so_tinh.get(na, 0), "OK" if not thieu else "THIEU " + ",".join(thieu))
    for cb in canh_bao:
        logger.warning("NetAct cau hinh: %s", cb)
    return canh_bao


# Cau hinh hop le GAN NHAT da doc duoc (raw, nguon) - xem _doc_hoac_dung_ban_nho().
_ban_nho: tuple[dict, str] | None = None


def _doc_hoac_dung_ban_nho() -> tuple[dict, str]:
    """Doc cau hinh cho 1 lan chon OSS. File bi sua HONG khi app dang chay ->
    giu ban hop le gan nhat + log ERROR, CR van chay (1 lan go sai dau phay
    trong luc doi mat khau khong duoc lam dung moi CR). Chua tung doc duoc lan
    nao -> CauHinhNetactLoiError (DomainError -> 422 CAU_HINH_NETACT_LOI), KHONG
    de NetactConfigError thanh 500."""
    global _ban_nho
    try:
        _ban_nho = _doc_cau_hinh()
    except NetactConfigError as exc:
        # str(exc) chi co ten bien/duong dan/vi tri loi - khong co noi dung file.
        if _ban_nho is None:
            raise CauHinhNetactLoiError(f"Cau hinh NetAct loi, chua co ban hop le nao: {exc}") from None
        logger.error("NetAct cau hinh HONG, dung ban hop le gan nhat (%s): %s", _ban_nho[1], exc)
    return _ban_nho


class OssRouterEnv(IOssRouter):
    def __init__(self):
        raw, self._nguon = _doc_hoac_dung_ban_nho()
        self._instances: dict[str, dict] = {}
        self._routes: dict[str, str] = {}

        if "instances" in raw or "routes" in raw:
            # Dinh dang MOI.
            self._instances = raw.get("instances", {})
            self._routes = raw.get("routes", {})
        else:
            # Dinh dang CU (phang) - xem docstring dau file muc b). Gom
            # cac khoa (ma_tinh_cu) CUNG host ve CUNG 1 instance_id (=host)
            # - KHONG dung khoa lam instance_id, vi nhieu tinh cu co the
            # dung chung 1 server NetAct vat ly.
            for ma_tinh_cu, server in raw.items():
                host = server.get("host")
                instance_id = host if host else ma_tinh_cu
                if instance_id not in self._instances:
                    # noc (02/10/2026) - dinh dang CU khong co khoa nay trong
                    # .env that, GAN CUNG "NOC1" (xem docstring dau file muc b)
                    # - "server" la dict tu .env, KHONG sua truc tiep (co the
                    # bi setdefault() dung lai cho instance_id khac ve sau),
                    # tao ban sao moi voi "noc" them vao.
                    self._instances[instance_id] = {**server, "noc": "NOC1"}
                self._routes[f"{ma_tinh_cu}|{Vendor.NOKIA.value}"] = instance_id

    def ly_do_khong_chon(self, ma_tinh_cu: str, vendor: Vendor) -> str | None:
        # Cung thu tu xet voi chon_oss() de cau giai thich khop dung nhanh da
        # tra None. Chi ten truong thieu, KHONG gia tri.
        khoa = f"{ma_tinh_cu}|{vendor.value}"
        instance_id = self._routes.get(khoa)
        if instance_id is None:
            return f"chua co route {khoa} trong cau hinh NetAct"
        server = self._instances.get(instance_id)
        if not server:
            return f"{instance_id} cau hinh loi: route {khoa} tro toi NA khong ton tai"
        thieu = _thieu(server)
        if thieu:
            return f"{instance_id} cau hinh loi: thieu {', '.join(thieu)}"
        return None

    def chon_oss(self, ma_tinh_cu: str, vendor: Vendor) -> OssInstance | None:
        instance_id = self._routes.get(f"{ma_tinh_cu}|{vendor.value}")
        if instance_id is None:
            # Khong co route cho khoa nay - CHUA cau hinh, KHONG doan/fallback
            # sang OSS khac (xem docstring IOssRouter.chon_oss()).
            return None

        server = self._instances.get(instance_id)
        if not server:
            return None

        # "???" - placeholder credential CHUA CO (KI-08: 7 tinh Netact14 tai
        # thoi diem viet code nay). Coi nhu CHUA cau hinh, KHONG cho SshExecutor
        # thu ket noi voi credential gia. Dung CHUNG _thieu() voi kiem tra
        # khoi dong - 2 noi cung 1 dinh nghia "thieu".
        if _thieu(server):
            return None
        host, user, password = server["host"], server["user"], server["password"]

        # noc (02/10/2026) - "server" o day la dict goc tu .env (dinh dang
        # MOI) hoac dict da them "noc":"NOC1" tu __init__ (dinh dang CU) -
        # ca 2 truong hop deu chi can .get("noc"), dinh dang MOI thieu khoa
        # nay -> None (dung y, xem docstring dau file).
        noc = server.get("noc")
        return OssInstance(instance_id=instance_id, host=host, user=user, password=password, noc=noc)
