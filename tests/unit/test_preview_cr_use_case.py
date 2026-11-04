"""
Unit test cho PreviewCrUseCase (POST /cr/preview, 21072026) — MOCK network_gw/
cell_infor_repo/enodeb_repo (I/O bien ngoai). Domain services (neighbor_filter/
priority_assigner/rsboost_calc/qrxlevmin_calc) dung INSTANCE THAT qua
TriggerCrUseCase composed - da co unit test rieng (tests/domain/,
test_trigger_cr_use_case.py), o day muc tieu la xac nhan PreviewCrUseCase gom
dung cau truc 2 tang (tram > cell) + khong crash khi tram lan can khong join
duoc bang tram.
Tu: docs/DEV_LOG.md muc [C1.4-fix11].

Fixture theo tram 111139 (tram that da dung o cac test/DEV_LOG khac cua du an,
xem C1.4-fix8) - cell lan gieng chia lam 2 tram vat ly KHAC nhau (113456 co
trong bang tram, 999999 KHONG co - mo phong dung 0.4% LNBTS khong join duoc
xac nhan qua verify du lieu that truoc khi code tinh nang nay).

21072026 (xac nhan voi user, sau khi verify DB that tram 111139 that): them
2 nhom test moi -
  - TestLoaiCellTramGoc: cell co LNBTS == tram_id goc (CDS tu no tra ve, KHONG
    tu loai) phai bi loai KHOI response - tram tat thi cell cua no cung tat.
  - TestGomTheoLnbtsKhongPhaiMrbts: cell co MRBTS != LNBTS trong cell_id phai
    gom theo LNBTS (mo phong 12 nhom lech da verify tren cell_infor that).

22072026 (xac nhan voi user, sau khi trace tay tram 110548 - 2 nhanh):
PreviewResult doi tu "tram_lan_can" (SAI - suy tu Nhanh B/12 cell CHAY CR)
sang 3 field ro rang - cells_bi_anh_huong/tram_bi_anh_huong (Nhanh A, danh
gia RF, KHONG loc huong/band) va cells_chay_cr (Nhanh B, GIU NGUYEN gia tri
nhu truoc). Toan bo assertion ".tram_lan_can" trong file nay da sua sang 3
field moi - KHONG doi fixture/mock nao, chi doi cach doc ket qua.
"""

from unittest.mock import AsyncMock, MagicMock
from tests.unit.nguon_cell_gia_lap import gan_nguon_gia_lap

import pytest

from adapters.netact.xml_builder import XmlBuilder
from application.preview_cr_use_case import PreviewCrUseCase
from application.trigger_cr_use_case import TriggerCrUseCase
from domain.entities.tram import Tram
from domain.errors import CrNoNeighborCellError, TramNotFoundError
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.services.rsboost_calculator import RsboostCalculator
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel

# Giai doan 1 buoc 2 (27/09/2026) - moi cell fixture ket thuc "-HNI" (xem
# _RAW_HUONGS o duoi) nen fake IOssRouter chi can 1 OssInstance co dinh.
_OSS_HNI = OssInstance(instance_id="NA09", host="10.212.242.20", user="test_user", password="test_password")

TRAM_ID = "111139"
TRAM_NAME = "4G-TST111M-HNI"

# SUA 09/2026 (MAX_CELLS_PER_HUONG 4 -> 2, GIONG tests/unit/
# test_trigger_cr_use_case.py::_RAW_HUONGS - cung ly do, xem comment day du o
# do): 2 huong (11 va 12, khac Y-sector nen khong canh tranh band priority),
# moi huong dung 2 cell, de Nhanh B (cells_chay_cr) van co du 4 nhanh logic
# rsboost/qrxlevmin x skip/khong-skip. Nhanh A (cells_bi_anh_huong) khong loc
# huong/rank nen KHONG bi anh huong boi cach chia nay - van thay ca 4 cell.
# A/C thuoc tram vat ly 113456 (CO trong bang tram), B/D thuoc tram vat ly
# 999999 (KHONG co trong bang tram - mo phong edge case). Priority GIU
# NGUYEN gia tri cu, chi doi CELL NAO chung huong voi CELL NAO.
_RAW_HUONGS = [
    {
        "huong_id": 11,
        "huong_name": "4G-TST111M11-HNI",
        "cells": [
            {
                "cell_id": "PLMN-PLMN/MRBTS-113456/LNBTS-113456/LNCEL-11",
                "cell_name": "4G-CELL-A-HNI",
                "priority": 1,
                "technology": "4G",
                "status": "active",
            },
            {
                "cell_id": "PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-13",
                "cell_name": "4G-CELL-C-HNI",
                "priority": 3,
                "technology": "4G",
                "status": "active",
            },
        ],
    },
    {
        "huong_id": 12,
        "huong_name": "4G-TST111M12-HNI",
        "cells": [
            {
                "cell_id": "PLMN-PLMN/MRBTS-113456/LNBTS-113456/LNCEL-12",
                "cell_name": "4G-CELL-B-HNI",
                "priority": 2,
                "technology": "4G",
                "status": "active",
            },
            {
                "cell_id": "PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-14",
                "cell_name": "4G-CELL-D-HNI",
                "priority": 4,
                "technology": "4G",
                "status": "active",
            },
        ],
    },
]

DN_A = "PLMN-PLMN/MRBTS-113456/LNBTS-113456/LNCEL-11"
DN_B = "PLMN-PLMN/MRBTS-113456/LNBTS-113456/LNCEL-12"
DN_C = "PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-13"
DN_D = "PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-14"

_CELL_INFOR_RSBOOST = {DN_A: RsboostLevel(0.0), DN_B: RsboostLevel(6.0)}  # B da o cap -> skip
_CELL_INFOR_QRXLEVMIN = {DN_C: Qrxlevmin(-144), DN_D: Qrxlevmin(-120)}  # C da o floor -> skip


def _make_use_case(raw_huongs=_RAW_HUONGS, tram_rows=None):
    network_gw = AsyncMock()
    network_gw.get_cell_neighbors.return_value = raw_huongs

    cell_infor_repo = AsyncMock()
    cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = dict(_CELL_INFOR_RSBOOST)
    cell_infor_repo.get_qrxlevmin_by_neighbor_dns.return_value = dict(_CELL_INFOR_QRXLEVMIN)

    enodeb_repo = AsyncMock()
    enodeb_repo.find.return_value = []
    if tram_rows is None:
        tram_rows = [
            Tram(tram_id=TRAM_ID, tram_name=TRAM_NAME, longitude=105.8, latitude=21.0, trang_thai="active"),
            Tram(tram_id="113456", tram_name="4G-CGY108M-HNI", longitude=105.9, latitude=21.1, trang_thai="active"),
            # "999999" CO Y BO QUA - mo phong tram khong join duoc
        ]
    enodeb_repo.get_by_tram_ids.return_value = tram_rows

    trigger_uc = TriggerCrUseCase(
        network_gw=network_gw,
        netact_gw=AsyncMock(),
        session_repo=AsyncMock(),
        cell_repo=AsyncMock(),
        cell_infor_repo=cell_infor_repo,
        enodeb_repo=enodeb_repo,
        event_bus=AsyncMock(),
        rsboost_calc=RsboostCalculator(),
        qrxlevmin_calc=QrxlevminCalculator(),
        xml_builder=XmlBuilder(),
        # affected_cells_repo/cr_log_repo (22072026) - preview KHONG ghi DB
        # (_prepare_plan() dung chung khong goi bulk_insert()/_log_step(), chi
        # run_cr_flow() moi goi) nen mock rong la du, khong test nao trong file
        # nay can assert tren chung.
        affected_cells_repo=AsyncMock(),
        cr_log_repo=AsyncMock(),
        # oss_router (Giai doan 1 buoc 2, 27/09/2026) - fake tra CO DINH
        # _OSS_HNI cho MOI khoa, du cac test o day khong xoay quanh dinh
        # tuyen OSS (da co rieng tests/unit/test_trigger_cr_use_case.py::
        # TestDinhTuyenOSS) - chi can khong loai mat cell fixture.
        oss_router=MagicMock(chon_oss=MagicMock(return_value=_OSS_HNI)),
        ho_neighbor_repo=AsyncMock(),
    )
    # BO CDS (18/10/2026) - xem tests/unit/nguon_cell_gia_lap.py.
    gan_nguon_gia_lap(trigger_uc, network_gw)
    preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)
    return preview_uc, network_gw, cell_infor_repo, enodeb_repo


class TestPreviewCauTruc2Tang:
    async def test_nhanh_a_va_nhanh_b_tra_dung_ca_2_danh_sach(self):
        preview_uc, network_gw, cell_infor_repo, enodeb_repo = _make_use_case()

        result = await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # ----- tram_goc -----
        assert result.tram_goc.tram_id == TRAM_ID
        assert result.tram_goc.tram_name == TRAM_NAME
        assert result.tram_goc.longitude == 105.8
        assert result.tram_goc.latitude == 21.0

        # ----- CDS goi dung tram_id/tram_name/action (KHONG SSH, KHONG DB write) -----
        # V6 (12/08): preview truyen timeout/so_lan_thu RIENG - 120s x 1 lan.
        # BO CDS (18/10/2026): nguon gia lap chi nhan tram_id (khong con
        # timeout/retry CDS rieng cho preview).
        network_gw.get_cell_neighbors.assert_awaited_once_with(TRAM_ID)

        # ----- Nhanh A: cells_bi_anh_huong co ca 4 cell (A/B/C/D), khong loc
        # huong/band - KHAC Nhanh B se loai bot theo action_type/skip ----
        affected_names = {c.cell_name for c in result.cells_bi_anh_huong}
        assert affected_names == {"4G-CELL-A-HNI", "4G-CELL-B-HNI", "4G-CELL-C-HNI", "4G-CELL-D-HNI"}
        cell_a_affected = next(c for c in result.cells_bi_anh_huong if c.cell_name == "4G-CELL-A-HNI")
        assert cell_a_affected.huong_id == "11"
        assert cell_a_affected.tram_id == "113456"

        # ----- tram_bi_anh_huong: 2 tram, sort theo tram_id tang dan -----
        assert [t.tram_id for t in result.tram_bi_anh_huong] == ["113456", "999999"]
        tram_113456 = result.tram_bi_anh_huong[0]
        assert tram_113456.tram_name == "4G-CGY108M-HNI"
        assert tram_113456.longitude == 105.9
        assert tram_113456.latitude == 21.1
        # 999999 KHONG join duoc bang tram - null-able, KHONG crash
        tram_999999 = result.tram_bi_anh_huong[1]
        assert tram_999999.tram_name is None
        assert tram_999999.longitude is None
        assert tram_999999.latitude is None

        # ----- Nhanh B: cells_chay_cr co gia tri rsboost/qrxlevmin, flat list
        # kem tram_id tren tung cell (KHONG con nested duoi tram) -----
        cells_chay_cr = {c.cell_name: c for c in result.cells_chay_cr}
        assert set(cells_chay_cr) == {"4G-CELL-A-HNI", "4G-CELL-B-HNI", "4G-CELL-C-HNI", "4G-CELL-D-HNI"}
        assert cells_chay_cr["4G-CELL-A-HNI"].tram_id == "113456"
        assert cells_chay_cr["4G-CELL-A-HNI"].action_type == "rsboost"
        assert cells_chay_cr["4G-CELL-A-HNI"].rsboost_cu == 0.0
        assert cells_chay_cr["4G-CELL-A-HNI"].rsboost_moi == 3.0  # next_level() cua 0.0
        assert cells_chay_cr["4G-CELL-B-HNI"].action_type == "skip"  # da o cap 6dB
        assert cells_chay_cr["4G-CELL-C-HNI"].tram_id == "999999"
        assert cells_chay_cr["4G-CELL-C-HNI"].action_type == "skip"  # da o floor -144
        assert cells_chay_cr["4G-CELL-D-HNI"].action_type == "qrxlevmin"
        assert cells_chay_cr["4G-CELL-D-HNI"].qrxlevmin_cu == -120
        assert cells_chay_cr["4G-CELL-D-HNI"].qrxlevmin_moi == -124  # decrease() cua -120

        # ----- band/sector (quyet dinh 03/10/2026, luat chon cell CR moi) -
        # A/C cung huong 11 (sector 1), LNCEL-11/-13 deu band F1; B/D cung
        # huong 12 (sector 2), LNCEL-12/-14 deu band F1 -----
        assert cells_chay_cr["4G-CELL-A-HNI"].band == "1800 F1"
        assert cells_chay_cr["4G-CELL-A-HNI"].sector == 1
        assert cells_chay_cr["4G-CELL-B-HNI"].sector == 2
        assert cells_chay_cr["4G-CELL-C-HNI"].sector == 1
        assert cells_chay_cr["4G-CELL-D-HNI"].band == "1800 F1"

        # ----- get_by_tram_ids goi dung 1 lan, dung tap tram_id (goc + bi anh huong) -----
        enodeb_repo.get_by_tram_ids.assert_awaited_once()
        called_ids = set(enodeb_repo.get_by_tram_ids.call_args.args[0])
        assert called_ids == {TRAM_ID, "113456", "999999"}

        # ----- OSS se dung (Giai doan 1 buoc 2, 27/09/2026) -----
        assert result.oss_instance == _OSS_HNI


class TestPreviewEdgeCases:
    async def test_tram_khong_ton_tai_raise_tram_not_found(self):
        preview_uc, _, _, enodeb_repo = _make_use_case()
        enodeb_repo.find.return_value = []

        with pytest.raises(TramNotFoundError):
            await preview_uc.execute("", "TRAM-KHONG-TON-TAI", "shutdown")

    # BO CDS (18/10/2026): da xoa 2 test CrCdsNoNeighborDataError ("CDS tra 0
    # huong"/"huong rong") - nhanh CDS khong con; thieu du lieu HO duoc kiem o
    # test_preview_cr_use_case_ho.py/test_trigger_cr_use_case_ho.py (HoNoDataError).

    async def test_action_cancel_raise_not_implemented(self):
        preview_uc, _, _, _ = _make_use_case()

        with pytest.raises(NotImplementedError):
            await preview_uc.execute(TRAM_ID, TRAM_NAME, "cancel")

    async def test_action_khong_hop_le_raise_value_error(self):
        preview_uc, _, _, _ = _make_use_case()

        with pytest.raises(ValueError):
            await preview_uc.execute(TRAM_ID, TRAM_NAME, "xoa_het")

    async def test_khong_goi_session_repo_khong_goi_cell_repo_upsert(self):
        # KHONG tao session/KHONG ghi DB - session_repo/cell_repo cua
        # TriggerCrUseCase composed KHONG duoc dung toi trong preview.
        preview_uc, _, _, _ = _make_use_case()
        session_repo = preview_uc._trigger_uc._session_repo
        cell_repo = preview_uc._trigger_uc._cell_repo

        await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        session_repo.create.assert_not_awaited()
        session_repo.update.assert_not_awaited()
        cell_repo.upsert.assert_not_awaited()
        cell_repo.snapshot_before_cr.assert_not_awaited()


# --- Fixture rieng cho TestLoaiCellTramGoc: 1 huong co 1 cell CUA CHINH tram
# goc (LNBTS == TRAM_ID, giong tinh huong that tram 111139 - CDS tu no tra ve
# cell nay nhu 1 "cell lan can" binh thuong) + 1 cell CUA tram lan can that.
_SELF_CELL_DN = f"PLMN-PLMN/MRBTS-{TRAM_ID}/LNBTS-{TRAM_ID}/LNCEL-99"
# LNCEL-11 (khong phai -41 nhu truoc) - SUA 03/10/2026: luat band moi loc
# theo LNCEL CUA CHINH CELL LAN CAN (xem neighbor_cell_filter.py), "-41" vo
# tinh bi loai BAND_KHONG_CHAY_CR lam test nay (muc dich test loai cell TRAM
# GOC, khong lien quan band) ra cells_chay_cr rong oan.
_NEIGHBOR_CELL_DN = "PLMN-PLMN/MRBTS-113456/LNBTS-113456/LNCEL-11"

_RAW_HUONGS_WITH_SELF_CELL = [
    {
        "huong_id": 11,
        "huong_name": "4G-TST111M11-HNI",
        "cells": [
            {
                "cell_id": _SELF_CELL_DN,
                "cell_name": "4G-CELL-SELF-HNI",
                "priority": 1,
                "technology": "4G",
                "status": "active",
            },
            {
                "cell_id": _NEIGHBOR_CELL_DN,
                "cell_name": "4G-CELL-NEIGHBOR-HNI",
                "priority": 2,
                "technology": "4G",
                "status": "active",
            },
        ],
    }
]

_RAW_HUONGS_ONLY_SELF = [
    {
        "huong_id": 11,
        "huong_name": "4G-TST111M11-HNI",
        "cells": [
            {
                "cell_id": _SELF_CELL_DN,
                "cell_name": "4G-CELL-SELF-HNI",
                "priority": 1,
                "technology": "4G",
                "status": "active",
            },
        ],
    }
]


class TestLoaiCellTramGoc:
    async def test_cell_cua_tram_goc_bi_loai_khoi_ca_2_nhanh(self):
        preview_uc, _, cell_infor_repo, _ = _make_use_case(raw_huongs=_RAW_HUONGS_WITH_SELF_CELL)
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {
            _SELF_CELL_DN: RsboostLevel(0.0),
            _NEIGHBOR_CELL_DN: RsboostLevel(0.0),
        }

        result = await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # Cell CUA tram goc (4G-CELL-SELF) khong xuat hien o BAT KY dau trong
        # response (ca Nhanh A lan Nhanh B) - loai tu ben trong _prepare_plan()
        # (NeighborCellFilter.filter_affected()/filter_for_cr() voi tram_goc_id).
        assert {c.cell_name for c in result.cells_bi_anh_huong} == {"4G-CELL-NEIGHBOR-HNI"}
        assert {c.cell_name for c in result.cells_chay_cr} == {"4G-CELL-NEIGHBOR-HNI"}
        assert [t.tram_id for t in result.tram_bi_anh_huong] == ["113456"]

    async def test_toan_bo_cell_deu_cua_tram_goc_raise_no_neighbor_error(self):
        # Edge case: sau khi loai het cell cua tram goc, khong con cell nao ->
        # PHAI raise CrNoNeighborCellError, KHONG duoc tra response rong ngam.
        #
        # 18092026: case nay GIU NGUYEN CrNoNeighborCellError (KHONG doi sang
        # CrCdsNoNeighborDataError nhu case CDS tra 0 huong) - CDS o day CO tra
        # du lieu (1 cell), cell bi loai la do LUAT NGHIEP VU R012 (cell cua
        # chinh tram goc). Day dung la ranh gioi giua 2 ma loi.
        preview_uc, _, cell_infor_repo, _ = _make_use_case(raw_huongs=_RAW_HUONGS_ONLY_SELF)
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {_SELF_CELL_DN: RsboostLevel(0.0)}

        with pytest.raises(CrNoNeighborCellError) as exc_info:
            await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert exc_info.value.error_code == "CR_NO_NEIGHBOR_CELL"
        # CDS tra 1 cell - con so phai co trong message de nguoi dung biet CDS
        # KHONG rong (phan biet voi ma CR_CDS_NO_NEIGHBOR_DATA).
        assert "HO co 1 cell nguon" in exc_info.value.message
        # K == 0 -> TUYET DOI khong nhac den pham vi quan ly. Them menh de
        # "0 cell ngoai pham vi" chi lam nguoi doc di tim van de khong ton tai.
        assert "ngoai pham vi" not in exc_info.value.message


# --- Fixture rieng cho TestGomTheoLnbtsKhongPhaiMrbts: 1 cell co MRBTS !=
# LNBTS trong cell_id (mo phong dung 12 nhom lech da verify tren cell_infor
# that - MRBTS "la" (999998) khong ton tai trong bang tram, LNBTS (113456) CO).
_MISMATCH_CELL_DN = "PLMN-PLMN/MRBTS-999998/LNBTS-113456/LNCEL-31"

_RAW_HUONGS_MRBTS_MISMATCH = [
    {
        "huong_id": 11,
        "huong_name": "4G-TST111M11-HNI",
        "cells": [
            {
                "cell_id": _MISMATCH_CELL_DN,
                "cell_name": "4G-CELL-MISMATCH-HNI",
                "priority": 1,
                "technology": "4G",
                "status": "active",
            },
        ],
    }
]


class TestGomTheoLnbtsKhongPhaiMrbts:
    async def test_cell_mrbts_khac_lnbts_gom_theo_lnbts_khong_phai_mrbts(self):
        preview_uc, _, cell_infor_repo, _ = _make_use_case(raw_huongs=_RAW_HUONGS_MRBTS_MISMATCH)
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {_MISMATCH_CELL_DN: RsboostLevel(0.0)}

        result = await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # Gom theo LNBTS=113456 (CO trong bang tram fixture) - KHONG tao nhom
        # rieng theo MRBTS=999998 (neu gom sai theo MRBTS, tram_name/toa do se
        # la None vi 999998 khong co trong bang tram).
        assert [t.tram_id for t in result.tram_bi_anh_huong] == ["113456"]
        tram = result.tram_bi_anh_huong[0]
        assert tram.tram_name == "4G-CGY108M-HNI"
        assert tram.longitude == 105.9
        assert tram.latitude == 21.1
        assert {c.cell_name for c in result.cells_bi_anh_huong} == {"4G-CELL-MISMATCH-HNI"}
        assert result.cells_chay_cr[0].cell_name == "4G-CELL-MISMATCH-HNI"
        assert result.cells_chay_cr[0].tram_id == "113456"


# --- Fixture rieng cho TestMessageCellNgoaiPhamVi (18092026): TOAN BO cell
# CDS tra ve deu co cell_id dang PHANG (= cell_name, khong chua "LNBTS-") -
# tuc CDS dang noi "toi khong quan ly cell nay" (xem
# neighbor_cell_filter.py:144). Ket qua: CDS CO du lieu (5 cell) nhung ca 5 bi
# loai -> CrNoNeighborCellError, va message PHAI noi ra con so nay.
#
# 5 cell (khong phai 3) de kiem luon gioi han "toi da 3 ten": tram that 280003
# co 114 cell ngoai pham vi, do het vao message thi khong ai doc duoc.
_FLAT_CELL_NAMES = [
    "4G-NPA001M11-VPC",
    "4G-NPA002M12-VPC",
    "4G-NPA003M13-VPC",
    "4G-NPA004M14-VPC",
    "4G-NPA005M15-VPC",
]

_RAW_HUONGS_ALL_FLAT = [
    {
        "huong_id": 11,
        "huong_name": "4G-TST111M11-HNI",
        "cells": [
            {
                # cell_id PHANG - chinh la cell_name, khong co "LNBTS-<so>"
                "cell_id": ten,
                "cell_name": ten,
                "priority": i + 1,
                "technology": "4G",
                "status": "active",
            }
            for i, ten in enumerate(_FLAT_CELL_NAMES)
        ],
    }
]


class TestMessageCellNgoaiPhamVi:
    async def test_cell_id_phang_message_co_so_luong_va_toi_da_3_ten(self):
        preview_uc, _, _, _ = _make_use_case(raw_huongs=_RAW_HUONGS_ALL_FLAT)

        with pytest.raises(CrNoNeighborCellError) as exc_info:
            await preview_uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        message = exc_info.value.message
        assert exc_info.value.error_code == "CR_NO_NEIGHBOR_CELL"
        # CDS CO tra du lieu -> KHONG duoc dung ma CR_CDS_NO_NEIGHBOR_DATA.
        assert "HO co 5 cell nguon" in message
        # So luong DAY DU (5), khong phai so ten duoc liet ke (3) - nguoi dung
        # phai biet quy mo that.
        assert "5 cell ngoai pham vi quan ly R012" in message
        # Dung 3 ten dau, 2 ten con lai KHONG duoc xuat hien.
        for ten in _FLAT_CELL_NAMES[:3]:
            assert ten in message
        for ten in _FLAT_CELL_NAMES[3:]:
            assert ten not in message
