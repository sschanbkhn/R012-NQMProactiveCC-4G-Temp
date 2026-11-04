"""
Unit test cho nhanh HO cua TriggerCrUseCase._prepare_plan() (BUOC 4b,
08/10/2026, yeu cau truc tiep user: "THAY CDS BANG HO TRONG XEM TRUOC VA
CHAY CR"). MOCK enodeb_repo/cell_infor_repo/ho_neighbor_repo/oss_router (I/O
bien ngoai); domain services (ho_delaunay/ho_cell_selector) la HAM THUAN,
dung THAT (khong mock) - da co unit test rieng (tests/domain/test_ho_delaunay.py,
tests/domain/test_ho_cell_selector.py).

Muc tieu: xac nhan WIRING dung (HO -> CellUngVien -> Cell -> rsboost/
qrxlevmin cu/moi), KHONG test lai logic domain (da test o tests/domain/).
"""

from math import cos, radians
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.netact.xml_builder import XmlBuilder
from application.trigger_cr_use_case import TriggerCrUseCase
from domain.entities.cr_session import CrSession, CrStatus
from domain.errors import CauHinhNetactLoiError, HoNoDataError
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.services.rsboost_calculator import RsboostCalculator
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel

X_ID = "117903"
LAT0, LON0 = 21.000, 105.800
KM_PER_DEG_LAT = 111.32


def _toa_do(bac_km: float, dong_km: float) -> tuple[float, float]:
    lat = LAT0 + bac_km / KM_PER_DEG_LAT
    lon = LON0 + dong_km / (KM_PER_DEG_LAT * cos(radians(LAT0)))
    return lat, lon


_LAT_A, _LON_A = _toa_do(1.0, 0.0)
_LAT_B, _LON_B = _toa_do(0.5, 0.8)
_LAT_C, _LON_C = _toa_do(-1.0, 0.5)
_LAT_D, _LON_D = _toa_do(1.5, -0.5)

_OSS_HNI = OssInstance(instance_id="NA09", host="10.212.242.20", user="u", password="p", noc="NOC1")

# sector 1: dich 200/lcr13 (60%, SR99) + dich 201/lcr11 (40%, SR98) - CA 2
# song sot qua cong-don 80% (60% chua du, +40% moi vuot 80%). attempt*_SCALE
# du lon de vuot N_MIN_HO_SECTOR (3156, xem domain/services/ho_cell_selector.py).
_HO_ROWS = [
    {
        "source_sector": 1, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
        "ho_attempt": 3000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M11-HNI",
        "ngay_du_lieu": "2026-09-28",
    },
    {
        "source_sector": 1, "target_enb": 201, "target_lcr": 11, "target_eci": 201 * 256 + 11,
        "ho_attempt": 2000, "ho_sr": 98.0, "source_lncel_name": "4G-BDH288M11-HNI",
        "ngay_du_lieu": "2026-09-28",
    },
]

_DN_200 = "PLMN-PLMN/MRBTS-200/LNBTS-200/LNCEL-13"
_DN_201 = "PLMN-PLMN/MRBTS-201/LNBTS-201/LNCEL-11"


def _fake_enodeb_repo() -> MagicMock:
    repo = AsyncMock()
    repo.get_all_with_coords.return_value = [
        {"tram_id": X_ID, "tram_name": "4G-BDH288M-HNI", "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA"},
        {"tram_id": "200", "tram_name": "4G-SIA001M-HNI", "longitude": _LON_A, "latitude": _LAT_A, "ten_thiet_bi": "NOKIA"},
        {"tram_id": "201", "tram_name": "4G-SIB002M-HNI", "longitude": _LON_B, "latitude": _LAT_B, "ten_thiet_bi": "NOKIA"},
        {"tram_id": "202", "tram_name": "4G-SIC003M-HNI", "longitude": _LON_C, "latitude": _LAT_C, "ten_thiet_bi": "NOKIA"},
        {"tram_id": "203", "tram_name": "4G-SID004M-HNI", "longitude": _LON_D, "latitude": _LAT_D, "ten_thiet_bi": "NOKIA"},
    ]
    repo.get_by_tram_ids.return_value = []
    return repo


def _fake_cell_infor_repo() -> MagicMock:
    repo = AsyncMock()
    repo.get_dn_map_theo_enb_lcr.return_value = {
        (200, 13): {"dn_lncel": _DN_200, "cell_name": "4G-SIA001M13-HNI"},
        (201, 11): {"dn_lncel": _DN_201, "cell_name": "4G-SIB002M11-HNI"},
    }
    repo.get_rsboost_by_neighbor_dns.return_value = {_DN_200: RsboostLevel(0.0)}
    repo.get_qrxlevmin_by_neighbor_dns.return_value = {_DN_201: Qrxlevmin(-120)}
    return repo


def _fake_ho_neighbor_repo(rows=None, rows_vao=None, co_du_lieu_netact=False) -> MagicMock:
    # rows_vao/co_du_lieu_netact THEM 15/10/2026 (yeu cau truc tiep user,
    # "SUA THONG BAO KHI THIEU HO") - mac dinh RONG/False: khi caller KHONG
    # chi dinh gi khac (vd test chi quan tam HO DI RA), tinh huong "khong co
    # dong source_enb nao" se roi dung vao truong hop (c) NetAct chua co du
    # lieu gi (thong bao CU) - xem 2 test rieng cho (a)/(b) duoi day.
    repo = AsyncMock()
    repo.get_by_source_enb.return_value = rows if rows is not None else list(_HO_ROWS)
    repo.get_by_target_enb.return_value = rows_vao if rows_vao is not None else []
    repo.co_du_lieu_netact.return_value = co_du_lieu_netact
    return repo


def _fake_oss_router() -> MagicMock:
    router = MagicMock()
    router.chon_oss.return_value = _OSS_HNI
    return router


def _fake_cell_vi_tri_uoc_luong_repo(du_lieu=None) -> MagicMock:
    repo = AsyncMock()
    repo.get_by_netact.return_value = du_lieu if du_lieu is not None else {}
    return repo


def _make_use_case_ho(
    enodeb_repo=None, cell_infor_repo=None, ho_neighbor_repo=None, oss_router=None,
    cell_vi_tri_uoc_luong_repo=None,
) -> TriggerCrUseCase:
    affected_cells_repo = AsyncMock()
    affected_cells_repo.bulk_insert.return_value = 0
    cr_log_repo = AsyncMock()
    session_repo = AsyncMock()
    session_repo.get_by_tram_id.return_value = []
    session_repo.create.return_value = CrSession(
        id=1, tram_id=X_ID, action="shutdown", status=CrStatus.RUNNING, plan_name=None
    )
    return TriggerCrUseCase(
        network_gw=AsyncMock(),
        netact_gw=AsyncMock(),
        session_repo=session_repo,
        cell_repo=AsyncMock(),
        cell_infor_repo=cell_infor_repo or _fake_cell_infor_repo(),
        enodeb_repo=enodeb_repo or _fake_enodeb_repo(),
        event_bus=AsyncMock(),
        rsboost_calc=RsboostCalculator(),
        qrxlevmin_calc=QrxlevminCalculator(),
        xml_builder=XmlBuilder(),
        affected_cells_repo=affected_cells_repo,
        cr_log_repo=cr_log_repo,
        oss_router=oss_router or _fake_oss_router(),
        ho_neighbor_repo=ho_neighbor_repo or _fake_ho_neighbor_repo(),
        cell_vi_tri_uoc_luong_repo=cell_vi_tri_uoc_luong_repo or _fake_cell_vi_tri_uoc_luong_repo(),
    )


async def test_ho_tra_dung_danh_sach_b_voi_rsboost_qrxlevmin():
    uc = _make_use_case_ho()

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    b_names = {c.cell_name for c in plan.cells}
    assert b_names == {"4G-SIA001M13-HNI", "4G-SIB002M11-HNI"}
    a_names = {c.cell_name for c in plan.affected_cells}
    assert a_names == {"4G-SIA001M13-HNI", "4G-SIB002M11-HNI"}
    # rank_b: item attempt lon nhat (3000, dich 200) -> rsboost; item con lai
    # (dich 201) -> qrxlevmin (xem domain/services/ho_cell_selector.py).
    rsboost_cells = {p.cell_name for p in plan.rsboost_results}
    qrxlevmin_cells = {p.cell_name for p in plan.qrxlevmin_results}
    assert "4G-SIA001M13-HNI" in rsboost_cells
    assert "4G-SIB002M11-HNI" in qrxlevmin_cells
    assert plan.oss_instance == _OSS_HNI
    assert plan.ho_extra is not None
    # nguon_du_lieu DA BO (14/10/2026, yeu cau truc tiep user) - xem
    # docs/BUSINESS_RULES.md, khong con key nay trong ho_extra.
    assert "nguon_du_lieu" not in plan.ho_extra


async def test_ho_netact_chua_co_du_lieu_gi_giu_thong_bao_cu():
    # SUA 15/10/2026 (yeu cau truc tiep user, "SUA THONG BAO KHI THIEU HO")
    # - truong hop (c): NetAct CHUA TUNG nap du lieu (khong co dong nao, ke
    # ca chieu den) -> GIU NGUYEN thong bao CU (khong doi).
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=[], rows_vao=[], co_du_lieu_netact=False))

    with pytest.raises(HoNoDataError) as exc_info:
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    assert "Chua co du lieu HO cua NA09 cho tram 117903" in str(exc_info.value)
    assert exc_info.value.error_code == "KHONG_CO_DU_LIEU_HO"


async def test_ho_thieu_du_lieu_chay_qua_execute_set_khong_chay_va_ma_loi():
    # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - goi
    # uc.execute() (FULL flow: prepare_session() + run_cr_flow(), khong chi
    # _prepare_plan() rieng le nhu cac test (a)/(b)/(c) o tren) de xac nhan
    # HoNoDataError (raise o buoc 3, TRUOC BUOC_SSH_BAT_DAU=13 - chua tung
    # gui lenh len NetAct) khien cr_session.status = KHONG_CHAY (KHONG CON la
    # FAILED) VA cr_session.ma_loi = "KHONG_CO_DU_LIEU_HO" (error_code cua
    # HoNoDataError) - xem application/trigger_cr_use_case.py::_fail().
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=[], rows_vao=[], co_du_lieu_netact=False))

    result = await uc.execute(X_ID, "4G-BDH288M-HNI", "shutdown")

    assert result.status == CrStatus.KHONG_CHAY
    assert result.ma_loi == "KHONG_CO_DU_LIEU_HO"
    uc._session_repo.update.assert_awaited_once()  # noqa: SLF001
    updated = uc._session_repo.update.call_args.args[0]  # noqa: SLF001
    assert updated.status == CrStatus.KHONG_CHAY
    assert updated.ma_loi == "KHONG_CO_DU_LIEU_HO"


async def test_ho_khong_co_ho_ra_nhung_co_ho_vao_bao_nghi_chua_khai_bao_neighbor():
    # Truong hop (a): X khong HO RA nhung CO HO VAO tu tram khac (NetAct DA
    # co du lieu - co_du_lieu_netact=True ngam dinh qua rows_vao khac rong,
    # nhung van chi dinh ro de khang dinh y do test).
    rows_vao = [
        {"source_enb": 117893, "ho_attempt": 12},
        {"source_enb": 117893, "ho_attempt": 2},
        {"source_enb": 117893, "ho_attempt": 4},
        {"source_enb": 111025, "ho_attempt": 1},
    ]
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=[], rows_vao=rows_vao, co_du_lieu_netact=True))

    with pytest.raises(HoNoDataError) as exc_info:
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    msg = str(exc_info.value)
    assert "4G-BDH288M-HNI (117903) khong co luot HO di ra nao" in msg
    assert "chi nhan 19 luot HO vao tu 2 tram" in msg
    assert "chua khai bao neighbor hoac rat it UE" in msg
    assert "xu ly tay" in msg
    assert exc_info.value.error_code == "KHONG_CO_DU_LIEU_HO"


async def test_ho_khong_co_ho_ca_2_chieu_bao_nghi_khong_phat_song():
    # Truong hop (b): X khong HO RA, CUNG KHONG co HO VAO - nhung NetAct VAN
    # CO du lieu (cac tram khac), chi RIENG tram X la khong co gi ca 2 chieu.
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=[], rows_vao=[], co_du_lieu_netact=True))

    with pytest.raises(HoNoDataError) as exc_info:
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    msg = str(exc_info.value)
    assert "4G-BDH288M-HNI (117903) khong co du lieu HO ca chieu di lan chieu den" in msg
    assert "khong phat song trong ky du lieu" in msg
    assert "Xu ly tay" in msg
    assert exc_info.value.error_code == "KHONG_CO_DU_LIEU_HO"


async def test_ho_khong_xac_dinh_duoc_netact_raise_khong_co_du_lieu_ho():
    enodeb_repo = _fake_enodeb_repo()
    enodeb_repo.get_all_with_coords.return_value = [
        # tram_name KHONG dung mau "4G-...-XXX" -> ma_tinh_cu_tu_ten_cell() tra None.
        {"tram_id": X_ID, "tram_name": "TRAM KHONG DUNG MAU", "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA"},
    ]
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo)

    with pytest.raises(HoNoDataError):
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")


async def test_ho_tram_khong_co_toa_do_raise_khong_co_du_lieu_ho():
    enodeb_repo = _fake_enodeb_repo()
    enodeb_repo.get_all_with_coords.return_value = []  # X khong trong danh sach tra ve
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo)

    with pytest.raises(HoNoDataError):
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")


async def test_ho_cell_khong_resolve_duoc_dn_bi_loai_khoi_b_khong_crash():
    # (201,11) KHONG co trong dn_map (gia lap chua sync cell_infor cho cell nay) -
    # CellUngVien.can_ghep_ten=True -> _cell_ung_vien_to_cell() tra None -> cell
    # nay bi loai khoi CA affected_cells va cells (B), KHONG crash.
    cell_infor_repo = _fake_cell_infor_repo()
    cell_infor_repo.get_dn_map_theo_enb_lcr.return_value = {
        (200, 13): {"dn_lncel": _DN_200, "cell_name": "4G-SIA001M13-HNI"},
    }
    uc = _make_use_case_ho(cell_infor_repo=cell_infor_repo)

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    names_a = {c.cell_name for c in plan.affected_cells}
    names_b = {c.cell_name for c in plan.cells}
    assert "4G-SIB002M11-HNI" not in names_a
    assert "4G-SIB002M11-HNI" not in names_b
    assert "4G-SIA001M13-HNI" in names_a


async def test_ho_x_cran_dung_vi_tri_cell_uoc_luong():
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - X la TOA_DO_DUNG_CHUNG
    # (CRAN, chia toa do voi tram KHAC site "999") -> L1/L2 phai RONG (xem
    # phan_lop_delaunay() buoc 0, domain/services/ho_delaunay.py) va
    # ban_do["x"]["vi_tri_uoc_luong_cell"] phai lay dung tu
    # cell_vi_tri_uoc_luong_repo (khoa (enb cua X, sector) - KHONG tu tinh
    # lai o day, chi doc du lieu da duoc import_ho_neighbor.py ghi san).
    enodeb_repo = _fake_enodeb_repo()
    rows = list(enodeb_repo.get_all_with_coords.return_value)
    rows.append({
        "tram_id": "999", "tram_name": "4G-ZZZ999M-HNI",
        "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA",
    })
    enodeb_repo.get_all_with_coords.return_value = rows

    cran_repo = _fake_cell_vi_tri_uoc_luong_repo({
        (int(X_ID), 1): {
            "lat": _LAT_A, "lon": _LON_A,
            "ty_le_ho_tin_cay": 0.9, "so_tram_dich": 5,
            "ngay_du_lieu": "2026-09-28",
        },
    })
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo, cell_vi_tri_uoc_luong_repo=cran_repo)

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    ban_do = plan.ho_extra["ban_do"]
    assert "TOA_DO_DUNG_CHUNG" in ban_do["x"]["co"]
    # l1/l2 GIU NGUYEN la list (SUA LAI 15/10/2026, yeu cau truc tiep user,
    # "GIU TUONG THICH NGUOC" - FE dang doc list truc tiep). Thong tin vong
    # hinh sao nam o l1_vong/l2_vong (field MOI, xem test rieng ben duoi).
    assert ban_do["l1"] == []
    assert ban_do["l2"] == []
    assert ban_do["l1_vong"] == {"danh_sach": [], "x_tren_vien": False}
    assert ban_do["l2_vong"] == {"danh_sach": [], "x_tren_vien": False}
    uoc_luong = ban_do["x"]["vi_tri_uoc_luong_cell"]
    # cell_name=None - dn_map gia lap (_fake_cell_infor_repo) KHONG co cell nao
    # cua X_ID (117903), chi co 200/201 (tram DICH) - xem test rieng
    # test_ho_x_cran_vi_tri_uoc_luong_co_cell_name_ghep_theo_lnbts_lcr() cho
    # truong hop ghep duoc.
    assert uoc_luong == [{
        "lcr": 1, "cell_name": None, "lat": _LAT_A, "lon": _LON_A,
        "ty_le_ho_tin_cay": 0.9, "so_tram_dich": 5,
        "ngay_du_lieu": "2026-09-28",
    }]


async def test_ho_x_cran_vi_tri_uoc_luong_co_cell_name_ghep_theo_lnbts_lcr():
    # THEM (yeu cau truc tiep user) - cell_name cua vi_tri_uoc_luong_cell ghep
    # theo LNBTS (x_enb) + LCR: "lcr" cua cran_map la SECTOR (1), dn_map co cell
    # that LCR=11 (11%10=1 - CUNG sector) -> PHAI ghep duoc cell_name do.
    enodeb_repo = _fake_enodeb_repo()
    rows = list(enodeb_repo.get_all_with_coords.return_value)
    rows.append({
        "tram_id": "999", "tram_name": "4G-ZZZ999M-HNI",
        "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA",
    })
    enodeb_repo.get_all_with_coords.return_value = rows

    cell_infor_repo = _fake_cell_infor_repo()
    dn_map_voi_x = dict(cell_infor_repo.get_dn_map_theo_enb_lcr.return_value)
    dn_map_voi_x[(int(X_ID), 11)] = {"dn_lncel": "PLMN-PLMN/MRBTS-117903/LNBTS-117903/LNCEL-11", "cell_name": "4G-BDH288M11-HNI"}
    cell_infor_repo.get_dn_map_theo_enb_lcr.return_value = dn_map_voi_x

    cran_repo = _fake_cell_vi_tri_uoc_luong_repo({
        (int(X_ID), 1): {"lat": _LAT_A, "lon": _LON_A, "ty_le_ho_tin_cay": 0.9, "so_tram_dich": 5, "ngay_du_lieu": "2026-09-28"},
    })
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo, cell_infor_repo=cell_infor_repo, cell_vi_tri_uoc_luong_repo=cran_repo)

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    uoc_luong = plan.ho_extra["ban_do"]["x"]["vi_tri_uoc_luong_cell"]
    assert uoc_luong[0]["cell_name"] == "4G-BDH288M11-HNI"


async def test_ho_x_cran_tam_duong_bao_la_trung_binh_3_cell_uoc_luong():
    # THEM 10/10/2026 (yeu cau truc tiep user) - X CRAN co 3 cell UOC LUONG
    # (sector 1/2/3, toa do A/B/C) -> tam dung de sap goc/ve duong bao PHAI la
    # TRUNG BINH 3 vi tri do (KHONG phai toa do tong dai cua X, LAT0/LON0) -
    # xem _xay_du_lieu_ban_do() muc "TAM duong bao".
    enodeb_repo = _fake_enodeb_repo()
    rows = list(enodeb_repo.get_all_with_coords.return_value)
    rows.append({
        "tram_id": "999", "tram_name": "4G-ZZZ999M-HNI",
        "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA",
    })
    enodeb_repo.get_all_with_coords.return_value = rows

    cran_repo = _fake_cell_vi_tri_uoc_luong_repo({
        (int(X_ID), 1): {"lat": _LAT_A, "lon": _LON_A, "ty_le_ho_tin_cay": 0.9, "so_tram_dich": 5, "ngay_du_lieu": "2026-09-28"},
        (int(X_ID), 2): {"lat": _LAT_B, "lon": _LON_B, "ty_le_ho_tin_cay": 0.8, "so_tram_dich": 4, "ngay_du_lieu": "2026-09-28"},
        (int(X_ID), 3): {"lat": _LAT_C, "lon": _LON_C, "ty_le_ho_tin_cay": 0.7, "so_tram_dich": 3, "ngay_du_lieu": "2026-09-28"},
    })
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo, cell_vi_tri_uoc_luong_repo=cran_repo)

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    x_block = plan.ho_extra["ban_do"]["x"]
    assert x_block["tam_la_tong_dai"] is False
    assert x_block["tam_lat"] == pytest.approx((_LAT_A + _LAT_B + _LAT_C) / 3)
    assert x_block["tam_lon"] == pytest.approx((_LON_A + _LON_B + _LON_C) / 3)
    # Toa do tong dai (lat/lon goc) van giu NGUYEN, KHONG bi tam "de" mat.
    assert x_block["lat"] == LAT0
    assert x_block["lon"] == LON0


async def test_ho_x_cran_khong_co_cell_uoc_luong_tam_la_tong_dai():
    # X CRAN nhung KHONG cell nao uoc luong duoc (cran_map rong) -> fallback
    # tam VE toa do tong dai, danh dau tam_la_tong_dai=True.
    enodeb_repo = _fake_enodeb_repo()
    rows = list(enodeb_repo.get_all_with_coords.return_value)
    rows.append({
        "tram_id": "999", "tram_name": "4G-ZZZ999M-HNI",
        "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA",
    })
    enodeb_repo.get_all_with_coords.return_value = rows
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo, cell_vi_tri_uoc_luong_repo=_fake_cell_vi_tri_uoc_luong_repo({}))

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    x_block = plan.ho_extra["ban_do"]["x"]
    assert x_block["tam_la_tong_dai"] is True
    assert x_block["tam_lat"] == LAT0
    assert x_block["tam_lon"] == LON0


async def test_ho_x_khong_cran_tam_la_toa_do_chinh_khong_tong_dai():
    # X KHONG phai CRAN (TIN_CAY) - tam_la_tong_dai PHAI la False (khong co
    # van de "tong dai" can fallback, toa do X CHINH la vi tri anten thuc).
    uc = _make_use_case_ho()

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    x_block = plan.ho_extra["ban_do"]["x"]
    assert x_block["tam_la_tong_dai"] is False
    assert x_block["tam_lat"] == LAT0
    assert x_block["tam_lon"] == LON0


async def test_ho_ban_do_co_loai_tram_o_x_l1_l2_tram_bi_anh_huong_va_dinh_duong_bao():
    # THEM 11-12/10/2026 (yeu cau truc tiep user, "PHAN LOAI TRAM + DO ANH
    # HUONG") - loai_tram CHI de hien thi, suy tu TEN TRAM qua
    # domain/services/loai_tram.py::loai_tram_tu_ten_tram(). X ("4G-BDH288M-HNI")
    # va cac tram dich mac dinh (SIA001M/SIB002M/...) deu la chu cai "M" -> MACRO.
    uc = _make_use_case_ho()

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    ban_do = plan.ho_extra["ban_do"]
    assert ban_do["x"]["loai_tram"] == "MACRO"
    assert all(d["loai_tram"] == "MACRO" for d in ban_do["l1"])
    assert all(d["loai_tram"] == "MACRO" for d in ban_do["l2"])
    assert all(d["loai_tram"] == "MACRO" for d in ban_do["l1_vong"]["danh_sach"])
    assert all(d["loai_tram"] == "MACRO" for d in ban_do["l2_vong"]["danh_sach"])
    assert ban_do["tram_bi_anh_huong"]  # co du lieu de kiem, khong rong oan
    assert all(t["loai_tram"] == "MACRO" for t in ban_do["tram_bi_anh_huong"])
    dinh = ban_do["duong_bao"]["polygon"] or ban_do["duong_bao"]["doan"]
    assert dinh and all(d["loai_tram"] == "MACRO" for d in dinh)


async def test_ho_ban_do_loai_tram_phan_biet_dung_small_cell_vs_macro():
    # Them 1 tram dich SMALL_CELL (chu cai "S") de xac nhan loai_tram
    # PHAN BIET DUNG theo tung tram (khong phai hang so cung gia tri).
    enodeb_repo = _fake_enodeb_repo()
    rows = list(enodeb_repo.get_all_with_coords.return_value)
    for r in rows:
        if r["tram_id"] == "202":
            r["tram_name"] = "4G-SIC003S-HNI"
    enodeb_repo.get_all_with_coords.return_value = rows

    rows_ho = list(_HO_ROWS) + [{
        "source_sector": 3, "target_enb": 202, "target_lcr": 99, "target_eci": 202 * 256 + 99,
        "ho_attempt": 500, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M13-HNI",
        "ngay_du_lieu": "2026-09-28",
    }]
    uc = _make_use_case_ho(enodeb_repo=enodeb_repo, ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows_ho))

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    theo_tram = {t["tram_id"]: t for t in plan.ho_extra["ban_do"]["tram_bi_anh_huong"]}
    assert theo_tram["202"]["loai_tram"] == "SMALL_CELL"
    assert theo_tram["200"]["loai_tram"] == "MACRO"


async def test_ho_cell_o_2_sector_sector_la_sector_thang_sectors_khac_la_sector_con_lai():
    # THEM 12/10/2026 (yeu cau truc tiep user, "THEM SECTOR CHO BANG A") -
    # cell (200,13) xuat hien o CA sector 1 (40%, 2000/5000) VA sector 2
    # (100%, 5000/5000 - CHI minh no) -> GD4 chon sector 2 (pct cao hon) lam
    # sector "thang". sector=2, sectors_khac=[1] (sector 1 la "phu", van CO
    # HO that sang cell nay, chi KHONG phai mau so dang hien trong pct_ho).
    rows = [
        {"source_sector": 1, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
         "ho_attempt": 2000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M11-HNI", "ngay_du_lieu": "2026-09-28"},
        {"source_sector": 1, "target_enb": 201, "target_lcr": 11, "target_eci": 201 * 256 + 11,
         "ho_attempt": 3000, "ho_sr": 98.0, "source_lncel_name": "4G-BDH288M11-HNI", "ngay_du_lieu": "2026-09-28"},
        {"source_sector": 2, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
         "ho_attempt": 5000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M12-HNI", "ngay_du_lieu": "2026-09-28"},
    ]
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows))

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    chi_tiet = plan.ho_extra["theo_cell_name"]["4G-SIA001M13-HNI"]
    assert chi_tiet["sector"] == 2
    assert chi_tiet["sectors_khac"] == [1]
    # Cell KHONG trung sector nao (vd 201) -> sectors_khac rong.
    chi_tiet_201 = plan.ho_extra["theo_cell_name"]["4G-SIB002M11-HNI"]
    assert chi_tiet_201["sector"] == 1
    assert chi_tiet_201["sectors_khac"] == []


async def test_ho_tong_pct_ho_tram_la_ty_le_tren_tong_ho_x_khong_cong_sector():
    # SUA 11/10/2026 (yeu cau truc tiep user, bug that tren ban do tram 117903:
    # tong_pct_ho TRUOC DAY = CONG % tung sector, co the VUOT 100%/tram). O day:
    # sector 1 (dich 200, TOAN BO HO cua sector) attempt=80000; sector 2 (dich
    # 201, TOAN BO HO cua sector) attempt=20000 - MOI sector rieng cell nay
    # chiem 100% sector cua no (bug CU se cho CA 2 tram tong_pct_ho=100%, tong
    # 200%). DUNG: 200 phai la 80000/100000=80%, 201 la 20%, tong = 100%.
    rows = [
        {"source_sector": 1, "target_enb": 200, "target_lcr": 13, "target_eci": 200 * 256 + 13,
         "ho_attempt": 80_000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M11-HNI", "ngay_du_lieu": "2026-09-28"},
        {"source_sector": 2, "target_enb": 201, "target_lcr": 11, "target_eci": 201 * 256 + 11,
         "ho_attempt": 20_000, "ho_sr": 98.0, "source_lncel_name": "4G-BDH288M12-HNI", "ngay_du_lieu": "2026-09-28"},
    ]
    uc = _make_use_case_ho(ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows))

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    theo_tram = {t["tram_id"]: t for t in plan.ho_extra["ban_do"]["tram_bi_anh_huong"]}
    assert theo_tram["200"]["tong_pct_ho"] == pytest.approx(0.8)
    assert theo_tram["201"]["tong_pct_ho"] == pytest.approx(0.2)
    tong_tat_ca = sum(t["tong_pct_ho"] for t in theo_tram.values())
    assert tong_tat_ca <= 1.0 + 1e-9

    # Dinh duong bao (diem_bao) cung phai dung CONG THUC moi (KHONG phai % sector).
    dinh_theo_tram = {d["tram_id"]: d for d in plan.ho_extra["ban_do"]["duong_bao"]["doan"]}
    assert dinh_theo_tram["200"]["pct_ho"] == pytest.approx(0.8)
    assert dinh_theo_tram["201"]["pct_ho"] == pytest.approx(0.2)


async def test_ho_ban_do_l1_l2_giu_dang_list_tuong_thich_nguoc_voi_field_vong_moi_song_song():
    # SUA 15/10/2026 (yeu cau truc tiep user, "GIU TUONG THICH NGUOC") - lan
    # sua 14/10/2026 doi ban_do.l1/l2 tu list sang dict lam VO client CU dang
    # doc list truc tiep (vd `for t in ban_do["l1"]`/`len(ban_do["l1"])`).
    # NAY: ban_do.l1/l2 PHAI VAN la list (client cu chay binh thuong, KHONG
    # sua gi); thong tin vong hinh sao (danh_sach da chen X neu can + co
    # x_tren_vien) chuyen sang 2 field MOI, TACH RIENG: l1_vong/l2_vong.
    uc = _make_use_case_ho()

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")

    ban_do = plan.ho_extra["ban_do"]
    # "Client cu" doc nhu list thuan - PHAI hoat dong (len(), iterate, index).
    assert isinstance(ban_do["l1"], list)
    assert isinstance(ban_do["l2"], list)
    _ = len(ban_do["l1"])
    for _t in ban_do["l1"]:
        assert "tram_id" in _t
    if ban_do["l1"]:
        assert "tram_id" in ban_do["l1"][0]

    # Field MOI ton tai song song, KHONG thay the.
    assert isinstance(ban_do["l1_vong"], dict)
    assert isinstance(ban_do["l2_vong"], dict)
    assert "danh_sach" in ban_do["l1_vong"] and "x_tren_vien" in ban_do["l1_vong"]
    assert "danh_sach" in ban_do["l2_vong"] and "x_tren_vien" in ban_do["l2_vong"]
    # Cung 1 tap tram (chi khac THU TU/co the chen X) - KHONG mat/them tram la.
    id_l1 = {t["tram_id"] for t in ban_do["l1"]}
    id_l1_vong = {t["tram_id"] for t in ban_do["l1_vong"]["danh_sach"] if not t.get("la_x")}
    assert id_l1 == id_l1_vong


async def test_ho_vong_l1_khong_lay_tram_cung_site_nhung_ban_do_l1_van_giu():
    # THEM 16/10/2026 (yeu cau truc tiep user, "VONG L1 KHONG LAY TRAM CUNG
    # SITE") - tram 204 (4G-BDH288B-HNI) CUNG SO SITE voi X (4G-BDH288M-HNI,
    # site "BDH288") va dat CUNG toa do X (km=0) - ban_do.l1 (tuong thich
    # nguoc) PHAI VAN giu no, nhung ban_do.l1_vong.danh_sach (vong ve tren ban
    # do) PHAI LOAI no ra. Cell cua tram nay PHAI mang layer "L1_CUNG_SITE"
    # (khac "L1" thuong) trong ho_extra.theo_cell_name.
    enodeb_repo = _fake_enodeb_repo()
    enodeb_repo.get_all_with_coords.return_value = [
        *enodeb_repo.get_all_with_coords.return_value,
        {"tram_id": "204", "tram_name": "4G-BDH288B-HNI", "longitude": LON0, "latitude": LAT0, "ten_thiet_bi": "NOKIA"},
    ]
    cell_infor_repo = _fake_cell_infor_repo()
    cell_infor_repo.get_dn_map_theo_enb_lcr.return_value = {
        **cell_infor_repo.get_dn_map_theo_enb_lcr.return_value,
        (204, 11): {"dn_lncel": "PLMN-PLMN/MRBTS-204/LNBTS-204/LNCEL-11", "cell_name": "4G-BDH288B11-HNI"},
    }
    rows = [
        *_HO_ROWS,
        {
            "source_sector": 2, "target_enb": 204, "target_lcr": 11, "target_eci": 204 * 256 + 11,
            "ho_attempt": 4000, "ho_sr": 99.0, "source_lncel_name": "4G-BDH288M12-HNI",
            "ngay_du_lieu": "2026-09-28",
        },
    ]
    uc = _make_use_case_ho(
        enodeb_repo=enodeb_repo, cell_infor_repo=cell_infor_repo,
        ho_neighbor_repo=_fake_ho_neighbor_repo(rows=rows),
    )

    plan = await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")
    ban_do = plan.ho_extra["ban_do"]

    assert "204" in {t["tram_id"] for t in ban_do["l1"]}
    assert "204" not in {t["tram_id"] for t in ban_do["l1_vong"]["danh_sach"] if not t.get("la_x")}
    assert plan.ho_extra["theo_cell_name"]["4G-BDH288B11-HNI"]["layer"] == "L1_CUNG_SITE"


async def test_ho_na_thieu_password_loi_cr_ghi_ro_na_va_truong_thieu(monkeypatch):
    # THEM 23/10/2026 - moi NA co mat khau rieng; NA thieu password thi loi CR
    # (ma_loi KHONG_CO_DU_LIEU_HO + message vao cr_log) phai noi RO NA nao,
    # thieu gi - khong chi "OSS chua cau hinh". Dung OssRouterEnv THAT.
    import json

    from adapters.netact.oss_router_env import OssRouterEnv

    monkeypatch.delenv("NETACT_SERVERS_FILE", raising=False)
    monkeypatch.setenv("NETACT_SERVERS", json.dumps({
        "instances": {"NA09": {"host": "10.212.242.20", "user": "thembv", "password": ""}},
        "routes": {"HNI|NOKIA": "NA09"},
    }))
    uc = _make_use_case_ho(oss_router=OssRouterEnv())

    # ma_loi RIENG CAU_HINH_NETACT_LOI (khong phai KHONG_CO_DU_LIEU_HO - sai nghia).
    with pytest.raises(CauHinhNetactLoiError, match="NA09 cau hinh loi: thieu password") as exc:
        await uc._prepare_plan(X_ID, "4G-BDH288M-HNI", "shutdown")  # noqa: SLF001
    assert not isinstance(exc.value, HoNoDataError) and exc.value.error_code == "CAU_HINH_NETACT_LOI"
    assert "10.212." not in str(exc.value)  # chi ten NA, khong host/IP

    result = await uc.execute(X_ID, "4G-BDH288M-HNI", "shutdown")
    assert result.ma_loi == "CAU_HINH_NETACT_LOI" and result.status == CrStatus.KHONG_CHAY
    msgs = [c.args[4] if len(c.args) > 4 else c.kwargs.get("message") for c in uc._cr_log_repo.insert.call_args_list]  # noqa: SLF001
    assert any(m and "NA09 cau hinh loi: thieu password" in m for m in msgs)
    assert not any(m and "10.212." in m for m in msgs)


def test_cau_hinh_netact_loi_tra_422_nhu_truoc():
    # Preview/trigger van 422 nhu khi con gop chung KHONG_CO_DU_LIEU_HO.
    from api.middleware.error_handler import _ERROR_CODE_STATUS  # noqa: PLC2701

    assert _ERROR_CODE_STATUS["CAU_HINH_NETACT_LOI"] == 422 == _ERROR_CODE_STATUS["KHONG_CO_DU_LIEU_HO"]
