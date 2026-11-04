"""
Unit test cho TriggerCrUseCase — MOCK network_gw/cell_repo/session_repo/
netact_gw/enodeb_repo/event_bus (I/O bien ngoai). Domain services
(neighbor_filter/priority_assigner/rsboost_calc/qrxlevmin_calc/xml_builder)
dung INSTANCE THAT (khong mock) - da co unit test rieng cho tung cai (B3.x/
B7.1), o day muc tieu la xac nhan TriggerCrUseCase noi dung dung, khong test
lai logic domain service.
Tu: TASK_LIST.md C2.1 (chua danh dau task cu the trong TASK_LIST, xem
docs/DEV_LOG.md muc C2.1)

13072026: band_priority_filter/nb_lncel_filter/huong_cell_selector/
neighbor_cell_service (4 service cu) da bi XOA, thay bang 1
NeighborCellFilter duy nhat (domain/services/neighbor_cell_filter.py) - xem
tests/domain/test_neighbor_cell_filter.py cho unit test rieng cua no.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.netact.xml_builder import XmlBuilder
from tests.unit.nguon_cell_gia_lap import gan_nguon_gia_lap
from application.trigger_cr_use_case import TriggerCrUseCase
from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrSession, CrStatus
from domain.entities.tram import Tram
from domain.errors import (
    CdsApiError,
    CrAlreadyDoneError,
    CrAlreadyRunningError,
    CrNhieuOssError,
    SshConnectionError,
    TramNotFoundError,
)
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from domain.services.rsboost_calculator import RsboostCalculator
from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel
from domain.value_objects.vendor import Vendor

TRAM_ID = "160000"
TRAM_NAME = "4G-TEST-HNI"

# 4 cell dung MRBTS/LNBTS=199999 (KHAC TRAM_ID=160000 cua tram goc dang bi
# tat) - 22072026: NeighborCellFilter.filter_for_cr() gio loai cell co LNBTS
# == tram_goc_id (tram tat thi cell cua no cung tat, xem
# domain/services/neighbor_cell_filter.py), neu dung chung 160000 nhu tram
# goc thi CA 4 cell se bi loai het, sai muc dich test nay (test cac nhanh
# logic rsboost/qrxlevmin, khong phai test loai cell tram goc - da co rieng
# tests/domain/test_neighbor_cell_filter.py::TestNhanhADanhGiaAnhHuong).
#
# SUA 09/2026 (MAX_CELLS_PER_HUONG 4 -> 2, fixture PHAI theo dung rang buoc
# moi): 2 huong (huong_id=11 va 12, KHAC Y-sector - 11 -> X=1/Y=1, 12 -> X=1/
# Y=2 - nen KHONG canh tranh nhau o buoc 2 band priority, ca 2 deu song sot),
# moi huong DUNG 2 cell, phu 4 nhanh logic. 12072026: nguon
# current rsboost/qrxlevmin doi tu cell_params sang cell_infor (LIKE tren
# dn_fdd/dn_sib, key = dist_name) - cell KHONG co trong cell_infor bi LOAI KHOI
# CR (khong con "dung gia tri mac dinh" nhu truoc), xem
# test_cell_missing_tu_cell_infor_bi_loai_khoi_cr rieng cho nhanh nay:
#   A: huong 11, priority 1 (rank1->rsboost), CO trong cell_infor (0dB -> next_level 3dB, khong skip)
#   C: huong 11, priority 3 (rank2->qrxlevmin), CO trong cell_infor, DA O FLOOR (-144 -> skip)
#   B: huong 12, priority 2 (rank1->rsboost), CO trong cell_infor, DA O CAP (6dB -> skip)
#   D: huong 12, priority 4 (rank2->qrxlevmin), CO trong cell_infor (-120 -> decrease -124, khong skip)
# Priority GIU NGUYEN gia tri cu (1/2/3/4, khong renumber trong tung huong) -
# chi doi CELL NAO nam CHUNG huong voi CELL NAO, KHONG doi bat ky dist_name/
# cell_name/gia tri cell_infor nao - moi assertion con lai trong file (thu tu
# [DN_A, DN_B] cho rsboost, [DN_C, DN_D] cho qrxlevmin, v.v.) GIU NGUYEN vi
# thu tu duyet van la huong tang dan (11 truoc 12) roi rank tang dan trong
# tung huong, dung y het thu tu cu.
_RAW_HUONGS = [
    {
        "huong_id": 11,
        # CAP NHAT 21072026: NeighborCellFilter gio suy huong_id tu vi tri co
        # dinh [10:12] trong huong_name (khong con doc truc tiep field
        # huong_id) - ten gia lap phai dung dinh dang 16 ky tu that, khac
        # placeholder "Huong 1" cu (se bi guard do dai loai bo).
        "huong_name": "4G-TST001M11-HNI",
        "cells": [
            {
                "cell_id": "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-11",
                "cell_name": "4G-CELL-A-HNI",
                "priority": 1,
                "technology": "4G",
                "status": "active",
            },
            {
                "cell_id": "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-13",
                "cell_name": "4G-CELL-C-HNI",
                "priority": 3,
                "technology": "4G",
                "status": "active",
            },
        ],
    },
    {
        "huong_id": 12,
        "huong_name": "4G-TST001M12-HNI",
        "cells": [
            {
                "cell_id": "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-12",
                "cell_name": "4G-CELL-B-HNI",
                "priority": 2,
                "technology": "4G",
                "status": "active",
            },
            {
                "cell_id": "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-14",
                "cell_name": "4G-CELL-D-HNI",
                "priority": 4,
                "technology": "4G",
                "status": "active",
            },
        ],
    },
]

# dist_name cua tung cell (khop LNCEL-11..14 trong _RAW_HUONGS) - key cho
# cell_infor_repo mock (12072026, khong con keyed by cell_name/tram_id nhu
# CellParam cu).
DN_A = "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-11"
DN_B = "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-12"
DN_C = "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-13"
DN_D = "PLMN-PLMN/MRBTS-199999/LNBTS-199999/LNCEL-14"

_CELL_INFOR_RSBOOST = {DN_A: RsboostLevel(0.0), DN_B: RsboostLevel(6.0)}
_CELL_INFOR_QRXLEVMIN = {DN_C: Qrxlevmin(-144), DN_D: Qrxlevmin(-120)}

# Giai doan 1 buoc 2 (27/09/2026, dinh tuyen OSS theo tung cell) - moi cell
# fixture gio ket thuc bang "-HNI" (xem _RAW_HUONGS o tren) de
# ma_tinh_cu_tu_ten_cell() suy dung "HNI", KHOP voi OssInstance gia lap nay.
_OSS_HNI = OssInstance(
    instance_id="NA09", host="10.212.242.20", user="test_user", password="test_password", noc="NOC1"
)


def _oss_router_mac_dinh() -> MagicMock:
    """Fake IOssRouter mac dinh cho _make_use_case(): MOI cell fixture route
    thanh cong ve _OSS_HNI (chon_oss() la method SYNC - MagicMock, KHONG
    duoc AsyncMock, xem domain/ports/outbound/gateway_ports.py::IOssRouter).
    Test rieng cho CR_NHIEU_OSS/TEN_CELL_SAI_MAU/OSS_CHUA_CAU_HINH tu ghi de
    qua uc._oss_router (cung pattern voi affected_cells_repo/cr_log_repo)."""
    router = MagicMock()
    router.chon_oss.return_value = _OSS_HNI
    return router


def _make_mocks():
    network_gw = AsyncMock()
    network_gw.get_cell_neighbors.return_value = _RAW_HUONGS
    network_gw.get_qos_metrics.return_value = [{"date": "2026-07-05", "value": 95.0}]

    netact_gw = AsyncMock()
    # SUA 18082026 - submit_cr tra DICT thay vi bool (can biet buoc nao hong +
    # DN nao hong de dat PARTIAL_SUCCESS). Mac dinh: 1 DN, thanh cong het.
    netact_gw.submit_cr.return_value = {
        "ok": True,
        "trang_thai": "DONE",
        "buoc_loi": None,
        "dn_list": [
            {
                "dn": "PLMN-PLMN/MRBTS-110548",
                "thanh_cong": True,
                "so_mo_thanh_cong": 3,
                "so_mo_that_bai": 0,
                "ly_do_loi": None,
            }
        ],
        "so_cell_thanh_cong": 1,
        "so_cell_tong": 1,
        "tom_tat": "Provision 1/1 DN thanh cong (3/3 MO)",
    }

    session_repo = AsyncMock()
    session_repo.get_by_tram_id.return_value = []
    session_repo.create.return_value = CrSession(
        id=42, tram_id=TRAM_ID, action="shutdown", status=CrStatus.RUNNING, plan_name=None
    )
    session_repo.update.side_effect = lambda s: s

    cell_repo = AsyncMock()
    cell_repo.snapshot_before_cr.return_value = None
    cell_repo.upsert.return_value = None

    cell_infor_repo = AsyncMock()
    cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = dict(_CELL_INFOR_RSBOOST)
    cell_infor_repo.get_qrxlevmin_by_neighbor_dns.return_value = dict(_CELL_INFOR_QRXLEVMIN)

    enodeb_repo = AsyncMock()
    enodeb_repo.get_ma_tinh.return_value = "HNI"
    enodeb_repo.find.return_value = []

    event_bus = AsyncMock()
    event_bus.publish.return_value = None

    return network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus


def _make_use_case(
    network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus
) -> TriggerCrUseCase:
    # affected_cells_repo (22072026, Phuong an B) - tao MOI o day (khong phai
    # tham so ham nay) de KHONG phai sua het cac call site _make_use_case(...)
    # hien co (7 positional args co dinh) - test nao can assert bulk_insert()
    # thi tu doc qua uc._affected_cells_repo (cung pattern voi
    # preview_uc._trigger_uc._session_repo da dung o test_preview_cr_use_case.py).
    affected_cells_repo = AsyncMock()
    affected_cells_repo.bulk_insert.return_value = 0
    # cr_log_repo (22072026) - tao MOI o day, cung ly do affected_cells_repo o
    # tren (khong sua het cac call site _make_use_case() hien co) - test nao
    # can assert insert() thi tu doc qua uc._cr_log_repo.
    cr_log_repo = AsyncMock()
    # oss_router (Giai doan 1 buoc 2, 27/09/2026) - cung ly do affected_cells_repo/
    # cr_log_repo o tren: tao MOI o day, test can tinh huong khac tu ghi de
    # qua uc._oss_router.
    oss_router = _oss_router_mac_dinh()
    uc = TriggerCrUseCase(
        network_gw=network_gw,
        netact_gw=netact_gw,
        session_repo=session_repo,
        cell_repo=cell_repo,
        cell_infor_repo=cell_infor_repo,
        enodeb_repo=enodeb_repo,
        event_bus=event_bus,
        rsboost_calc=RsboostCalculator(),
        qrxlevmin_calc=QrxlevminCalculator(),
        xml_builder=XmlBuilder(),
        affected_cells_repo=affected_cells_repo,
        cr_log_repo=cr_log_repo,
        oss_router=oss_router,
        # BO CDS (18/10/2026): ho_neighbor_repo bat buoc; nguon cell that
        # duoc thay bang nguon gia lap ben duoi (xem tests/unit/nguon_cell_gia_lap.py).
        ho_neighbor_repo=AsyncMock(),
    )
    gan_nguon_gia_lap(uc, network_gw)
    return uc


def _steps_published(event_bus: AsyncMock) -> list[int]:
    return [call.args[1]["step"] for call in event_bus.publish.call_args_list]


class TestHappyPath:
    async def test_18_buoc_chay_dung_thu_tu_va_dung_du_lieu(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # ----- Ket qua cuoi -----
        assert result.status == CrStatus.DONE
        assert result.plan_name.startswith(f"R012_NQMProactiveCC_{TRAM_ID}_")
        assert result.backup_plan_name.startswith(f"R012_backup_{TRAM_ID}_")
        assert result.xml_filename == f"{result.plan_name}.xml"
        assert result.executed_at is not None

        # ----- Guard (buoc 1) -----
        session_repo.get_by_tram_id.assert_awaited_once_with(TRAM_ID)
        session_repo.create.assert_awaited_once()

        # ----- Buoc 3: CDS goi dung tram_id/tram_name/action -----
        # V6 (12/08): luong CR that chay NEN nen GIU mac dinh cu 30s x 3 lan -
        # chi preview moi duoc nang len 120s x 1 (khong ai cho o luong nay).
        # BO CDS (18/10/2026): nguon gia lap chi nhan tram_id.
        network_gw.get_cell_neighbors.assert_awaited_once_with(TRAM_ID)

        # ----- Buoc 7/9: doc tu cell_infor_repo theo dist_name (KHONG phai
        # cell_repo.get_by_cell_names nua - 12072026) + snapshot
        # PHAI truoc buoc 11 (upsert) -----
        cell_infor_repo.get_rsboost_by_neighbor_dns.assert_awaited_once_with([DN_A, DN_B])
        cell_infor_repo.get_qrxlevmin_by_neighbor_dns.assert_awaited_once_with([DN_C, DN_D])
        cell_repo.snapshot_before_cr.assert_awaited_once_with(42)
        call_order = [c[0] for c in cell_repo.method_calls]
        assert call_order.index("snapshot_before_cr") < call_order.index("upsert")

        # ----- Buoc 11: upsert dung 4 cell (A/B rsboost, C/D qrxlevmin), co cr_session_id -----
        upserted: list[CellParam] = cell_repo.upsert.call_args.args[0]
        assert len(upserted) == 4
        by_name = {p.cell_name: p for p in upserted}
        assert all(p.cr_session_id == 42 for p in upserted)

        assert by_name["4G-CELL-A-HNI"].action_type == "rsboost"
        assert by_name["4G-CELL-A-HNI"].rsboost_new == RsboostLevel(3.0)  # 0dB (cell_infor) -> next_level() = 3dB

        assert by_name["4G-CELL-B-HNI"].action_type == "skip"  # da o cap 6dB, next_level() khong doi -> skip

        assert by_name["4G-CELL-C-HNI"].action_type == "skip"  # da o floor -144, decrease() khong doi -> skip

        assert by_name["4G-CELL-D-HNI"].action_type == "qrxlevmin"
        assert by_name["4G-CELL-D-HNI"].qrxlevmin_new == Qrxlevmin(-124)  # -120 (cell_infor) -> decrease() = -124

        # ----- Buoc 12: XML build dung - loai CELL-B/CELL-C (skip), giu A/D -----
        xml_content = netact_gw.submit_cr.call_args.args[0]
        assert "LNCEL-11" in xml_content  # cell A
        assert "LNCEL-12" not in xml_content  # cell B (skip) - PHAI bi loai
        assert "LNCEL-13" not in xml_content  # cell C (skip) - PHAI bi loai
        assert "LNCEL-14" in xml_content  # cell D
        assert xml_content.count("<managedObject") == 2

        # ----- Buoc 13-16: submit_cr dung tham so, dung OssInstance -----
        # SUA 27092026 (Giai doan 1 buoc 2) - KHONG con goi get_ma_tinh() (ham
        # van con, chi khong duoc TriggerCrUseCase goi nua - xem
        # application/trigger_cr_use_case.py::_chon_oss_va_loc_cells()).
        enodeb_repo.get_ma_tinh.assert_not_awaited()
        call_args = netact_gw.submit_cr.call_args.args
        assert call_args[1] == result.plan_name  # plan_name
        assert call_args[2] == result.backup_plan_name  # backup_name
        assert call_args[3] == _OSS_HNI  # oss (thay ma_tinh: str cu)

        # ----- Buoc 17: cr_session update voi DONE + 3 field moi -----
        assert session_repo.update.await_count == 1
        updated_session_arg = session_repo.update.call_args.args[0]
        assert updated_session_arg.status == CrStatus.DONE
        # oss_instance_id/noc (02/10/2026) - ghi tu plan.oss_instance (_OSS_HNI)
        assert updated_session_arg.oss_instance_id == "NA09"
        assert updated_session_arg.noc == "NOC1"

        # ----- Buoc 18: goi CTS QoS baseline -----
        network_gw.get_qos_metrics.assert_awaited_once()
        qos_call = network_gw.get_qos_metrics.call_args.args
        assert set(qos_call[0]) == {"4G-CELL-A-HNI", "4G-CELL-B-HNI", "4G-CELL-C-HNI", "4G-CELL-D-HNI"}

        # ----- Thu tu SSE dung 18 buoc (buoc 3 co running+success, 13-16 gop) -----
        assert _steps_published(event_bus) == [1, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18]

        # SSE cuoi cung phai co done=True
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["done"] is True
        assert last_event["status"] == "success"

    async def test_cell_missing_tu_cell_infor_bi_loai_khoi_cr(self):
        # 12072026: cell chua tung sync qua Admin CLI export (khong
        # co dong nao trong cell_infor match dn_fdd/dn_sib) PHAI bi loai HOAN
        # TOAN khoi CR - KHONG dung gia tri mac dinh (0dB/-128) nhu quyet dinh
        # cu khi con doc cell_params. O day CELL-A (rsboost) va CELL-D
        # (qrxlevmin) bi thieu, chi con CELL-B/CELL-C tham gia tinh toan.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {DN_B: RsboostLevel(6.0)}  # thieu DN_A
        cell_infor_repo.get_qrxlevmin_by_neighbor_dns.return_value = {DN_C: Qrxlevmin(-144)}  # thieu DN_D
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.DONE
        upserted: list[CellParam] = cell_repo.upsert.call_args.args[0]
        upserted_names = {p.cell_name for p in upserted}
        assert upserted_names == {"4G-CELL-B-HNI", "4G-CELL-C-HNI"}  # A/D bi loai, KHONG co trong cell_params

        # cell bi loai cung KHONG duoc tinh vao QoS baseline cell_names (buoc 18
        # dung "cells" sau khi da loc buoc 7/9, khong phai danh sach goc buoc 6)
        qos_call = network_gw.get_qos_metrics.call_args.args
        assert set(qos_call[0]) == {"4G-CELL-B-HNI", "4G-CELL-C-HNI"}

        xml_content = netact_gw.submit_cr.call_args.args[0]
        assert "LNCEL-11" not in xml_content  # CELL-A bi loai truoc khi tinh, khong the co trong XML
        assert "LNCEL-14" not in xml_content  # CELL-D bi loai truoc khi tinh, khong the co trong XML

    async def test_qos_snapshot_fail_khong_lam_fail_ca_cr(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_qos_metrics.side_effect = CdsApiError("CTS tam thoi loi")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # WORKFLOW.md SS8 - buoc 18 fail KHONG duoc lam FAILED ca CR (da DONE tu buoc 17)
        assert result.status == CrStatus.DONE
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 18
        assert last_event["status"] == "success"  # van success, chi noi dung msg khac

    async def test_affected_cells_ghi_du_4_cell_nhanh_a_cung_buoc_11(self):
        # 22072026, Phuong an B - filter_affected() (Nhanh A, khong loc huong/
        # band/rank) tra CA 4 cell A/B/C/D bat ke MAX_CELLS_PER_HUONG cua Nhanh
        # B la bao nhieu (SUA 09/2026: fixture gio 2 huong x 2 cell, xem
        # _RAW_HUONGS) - kiem tra dung noi dung ghi vao cr_affected_cells,
        # khong chi dem so luong.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        uc._affected_cells_repo.bulk_insert.assert_awaited_once()
        call_args = uc._affected_cells_repo.bulk_insert.call_args.args
        assert call_args[0] == result.id  # dung cr_session_id (session.id, khong phai tram_id)
        affected_cells_data = call_args[1]
        assert {c["cell_name"] for c in affected_cells_data} == {"4G-CELL-A-HNI", "4G-CELL-B-HNI", "4G-CELL-C-HNI", "4G-CELL-D-HNI"}
        cell_a = next(c for c in affected_cells_data if c["cell_name"] == "4G-CELL-A-HNI")
        assert cell_a["tram_id"] == "199999"  # LNBTS parse tu dist_name, khac TRAM_ID=160000 cua tram goc
        assert cell_a["huong_id"] == "11"
        assert cell_a["dist_name"] == DN_A

    async def test_affected_cells_insert_loi_khong_lam_fail_ca_cr(self):
        # Xac nhan lua chon voi user: loi ghi cr_affected_cells CHI la mat data
        # phu tro cho danh gia sau nay, KHONG duoc lam fail CR that (12 cell
        # cell_params van da luu thanh cong truoc do trong CUNG buoc 11).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._affected_cells_repo.bulk_insert.side_effect = RuntimeError("DB tam thoi mat ket noi")

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.DONE  # KHONG bi anh huong boi loi ghi affected_cells
        cell_repo.upsert.assert_awaited_once()  # 12 cell cell_params van duoc luu binh thuong
        netact_gw.submit_cr.assert_awaited_once()  # CR that van chay tiep den buoc 13-16

    async def test_cr_log_ghi_dung_so_lan_khop_so_lan_emit_sse(self):
        # 22072026 - moi lan _emit()/_fail() duoc goi PHAI ghi 1 dong cr_log
        # TUONG UNG (song song, khong thay the SSE) - KHONG tinh heartbeat
        # (_emit_heartbeat_loop() co cau truc event khac han, khong phai buoc
        # CR that su, xem TriggerCrUseCase._log_step()).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # So lan emit SSE (khong tinh heartbeat) = 17, khop CHINH XAC
        # _steps_published() da assert o test_18_buoc_chay_dung_thu_tu_va_dung_du_lieu
        # ([1,2,3,3,4,5,6,7,8,9,10,11,12,13,16,17,18]).
        assert uc._cr_log_repo.insert.await_count == 17

        # Dong DAU (buoc 1) - kiem tra dung noi dung, khong chi dem so luong.
        # Thu tu tham so: insert(cr_session_id, step, step_name, status, message, pct)
        first_call = uc._cr_log_repo.insert.call_args_list[0].args
        assert first_call == (result.id, 1, "Validate input", "success", "Input hop le", 5)

        # Dong CUOI (buoc 18) - status "success" (KHONG phai "failed", happy path)
        last_call = uc._cr_log_repo.insert.call_args_list[-1].args
        assert last_call[1] == 18  # step
        assert last_call[3] == "success"  # status

    async def test_cr_log_insert_loi_khong_lam_fail_ca_cr(self):
        # Xac nhan lua chon voi user: loi ghi cr_log CHI la mat 1 dong log de
        # xem lai, KHONG duoc lam fail CR that (giong quyet dinh voi
        # cr_affected_cells) - SSE van publish binh thuong, CR van chay het.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._cr_log_repo.insert.side_effect = RuntimeError("DB tam thoi mat ket noi")

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.DONE  # KHONG bi anh huong boi loi ghi cr_log
        assert event_bus.publish.await_count == 17  # SSE van publish du, khong bi chan
        netact_gw.submit_cr.assert_awaited_once()  # CR that van chay tiep den buoc 13-16


class TestGuardErrors:
    async def test_cr_already_running_raise_va_khong_tao_session(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        session_repo.get_by_tram_id.return_value = [
            CrSession(id=1, tram_id=TRAM_ID, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
        ]
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(CrAlreadyRunningError):
            await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        session_repo.create.assert_not_awaited()
        event_bus.publish.assert_not_awaited()

    async def test_cr_already_done_raise(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        session_repo.get_by_tram_id.return_value = [
            CrSession(id=1, tram_id=TRAM_ID, action="shutdown", status=CrStatus.DONE, plan_name="old_plan")
        ]
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(CrAlreadyDoneError):
            await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        session_repo.create.assert_not_awaited()

    async def test_tram_not_found_0_ket_qua_khop_ten(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        enodeb_repo.find.return_value = []  # khong co tram nao khop
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(TramNotFoundError):
            await uc.execute("", "TRAM-KHONG-TON-TAI", "shutdown")

        session_repo.create.assert_not_awaited()

    async def test_tram_not_found_nhieu_ket_qua_trung_ten_tu_choi_khong_doan(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        # 2 tram khac tram_id nhung CUNG tram_name (ILIKE + exact-match van ra 2)
        enodeb_repo.find.return_value = [
            Tram(tram_id="AAA", tram_name=TRAM_NAME, longitude=None, latitude=None, trang_thai="active"),
            Tram(tram_id="BBB", tram_name=TRAM_NAME, longitude=None, latitude=None, trang_thai="active"),
        ]
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(TramNotFoundError):
            await uc.execute("", TRAM_NAME, "shutdown")

        session_repo.create.assert_not_awaited()

    async def test_tram_id_resolve_dung_khi_chi_1_ket_qua_khop_chinh_xac(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        enodeb_repo.find.return_value = [
            Tram(tram_id="ZZZ-KHAC-TEN", tram_name="TRAM-GAN-GIONG", longitude=None, latitude=None, trang_thai="active"),
            Tram(tram_id=TRAM_ID, tram_name=TRAM_NAME, longitude=None, latitude=None, trang_thai="active"),
        ]
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute("", TRAM_NAME, "shutdown")

        # Phai resolve dung ve TRAM_ID (khop chinh xac ten), KHONG lay ket qua dau tien mu quang
        assert result.tram_id == TRAM_ID
        session_repo.get_by_tram_id.assert_awaited_once_with(TRAM_ID)

    async def test_input_rong_hoan_toan_raise_value_error(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(ValueError):
            await uc.execute("", "", "shutdown")

    async def test_action_khong_hop_le_raise_value_error(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(ValueError):
            await uc.execute(TRAM_ID, TRAM_NAME, "delete_everything")

    async def test_action_cancel_raise_not_implemented(self):
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        with pytest.raises(NotImplementedError):
            await uc.execute(TRAM_ID, TRAM_NAME, "cancel")

        session_repo.create.assert_not_awaited()


class TestMidFlowErrors:
    async def test_cds_api_error_buoc_3_tra_ve_khong_chay_khong_raise(self):
        # SUA 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") -
        # loi o buoc 3 (< BUOC_SSH_BAT_DAU=13, CHUA TUNG gui lenh len NetAct)
        # gio la KHONG_CHAY, KHONG CON la FAILED - xem
        # application/trigger_cr_use_case.py::_fail(). ma_loi phai la
        # error_code CUA DomainError (CdsApiError -> "CDS_API_ERROR").
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.side_effect = CdsApiError("CDS timeout sau 3 lan retry")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.KHONG_CHAY
        # Cac buoc sau (4 tro di) KHONG duoc chay
        cell_infor_repo.get_rsboost_by_neighbor_dns.assert_not_awaited()
        cell_infor_repo.get_qrxlevmin_by_neighbor_dns.assert_not_awaited()
        cell_repo.upsert.assert_not_awaited()
        netact_gw.submit_cr.assert_not_awaited()

        # session_repo.update duoc goi 1 lan de set KHONG_CHAY + ma_loi
        session_repo.update.assert_awaited_once()
        updated = session_repo.update.call_args.args[0]
        assert updated.status == CrStatus.KHONG_CHAY
        assert updated.ma_loi == "CDS_API_ERROR"

        # SSE cuoi cung la failed dung o buoc 3
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 3
        assert last_event["status"] == "failed"
        assert last_event["done"] is True

    async def test_ssh_connection_error_buoc_13_16_failed_khong_chay_17_18(self):
        # SUA 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") -
        # loi o buoc 13 (>= BUOC_SSH_BAT_DAU, DA goi submit_cr that) VAN la
        # FAILED nhu cu (khac test_cds_api_error_buoc_3_tra_ve_khong_chay_khong_raise()
        # o buoc 3, gio la KHONG_CHAY) - xem _fail(). ma_loi phai la error_code
        # cua SshConnectionError.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        netact_gw.submit_cr.side_effect = SshConnectionError("Mat ket noi SSH giua chung")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.FAILED
        assert result.ma_loi == "SSH_CONNECTION_ERROR"
        # Buoc 17 (cap nhat DONE) va 18 (QoS) KHONG duoc chay
        network_gw.get_qos_metrics.assert_not_awaited()
        assert result.plan_name is None  # buoc 17 khong chay nen plan_name khong duoc set vao session tra ve

        session_repo.update.assert_awaited_once()
        updated = session_repo.update.call_args.args[0]
        assert updated.status == CrStatus.FAILED
        assert updated.ma_loi == "SSH_CONNECTION_ERROR"

        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 13
        assert last_event["pct"] == 90  # loi SAU khi da goi submit_cr (khac pct 70 luc bat dau)
        assert last_event["status"] == "failed"
        assert last_event["done"] is True

    async def test_submit_cr_tra_ve_false_cung_la_failed_khong_can_raise(self):
        # Loi nghiep vu (script chay duoc nhung Import/Provision that bai) -
        # KHAC voi loi ha tang (exception) o test tren, nhung cung phai FAILED
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        netact_gw.submit_cr.return_value = False
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.FAILED
        network_gw.get_qos_metrics.assert_not_awaited()
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 13
        assert last_event["status"] == "failed"

    async def test_khong_co_OSS_nao_duoc_chon_o_buoc_13_failed_dung_pct_truoc_submit(self):
        # SUA 27092026 (Giai doan 1 buoc 2) - THAY THE ban cu
        # "test_ma_tinh_khong_tim_thay_o_buoc_13..." (dung
        # enodeb_repo.get_ma_tinh.side_effect): get_ma_tinh() KHONG con duoc
        # goi trong flow nay nua (xem _chon_oss_va_loc_cells()) nen tinh
        # huong tuong duong bay gio la MOI cell deu KHONG route duoc OSS
        # (vd chua cau hinh cho tinh cu nay) -> plan.oss_instance is None ->
        # raise SshConnectionError NGAY truoc submit_cr(), CUNG buoc/pct nhu
        # ban cu tung kiem (13/70%).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._oss_router.chon_oss.return_value = None  # noqa: SLF001 - bom thang, khong dung DI cho test

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.FAILED
        netact_gw.submit_cr.assert_not_awaited()  # loi truoc khi kip goi submit_cr
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 13
        assert last_event["pct"] == 70  # loi TRUOC khi goi submit_cr (khac pct 90 o test tren)
        # oss_instance_id/noc (02/10/2026) - CR bi tu choi TRUOC khi chon duoc
        # OSS (plan.oss_instance la None) -> PHAI de NULL, khong doan.
        session_repo.update.assert_awaited_once()
        assert session_repo.update.call_args.args[0].oss_instance_id is None
        assert session_repo.update.call_args.args[0].noc is None

    async def test_exception_khong_phai_domainerror_o_buoc_3_thanh_khong_chay_khong_ket_running(self):
        # C1.4-fix bo sung (20072026) - dung bug that: session #197 (tram
        # 111138) ket RUNNING 4 ngay vi 1 loi khong phai DomainError (vd
        # ConnectionError/TimeoutError tu SSH, KeyError do bug) lot thang ra
        # ngoai run_cr_flow() ma khong ai bat, vi ham nay chay qua
        # BackgroundTasks (khong con router await de propagate loi ra HTTP
        # response nua). RuntimeError o day dai dien cho "loi ha tang ngoai
        # du kien" bat ky, KHONG phai 1 trong cac DomainError da biet.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.side_effect = RuntimeError("SSH driver crash khong xac dinh")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        # SUA 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") -
        # loi o buoc 3 (< BUOC_SSH_BAT_DAU=13) la KHONG_CHAY du KHONG phai
        # DomainError - phan loai CHI dua theo BUOC dung, khong dua theo loai
        # exception (khong duoc de RuntimeError lot ra ngoai khien session
        # ket RUNNING vinh vien - day chinh la bug GOC can sua).
        assert result.status == CrStatus.KHONG_CHAY

        # cr_session_repo.update() PHAI duoc goi de persist KHONG_CHAY xuong
        # DB (dung nhu nhanh except DomainError), khong duoc bo qua. ma_loi
        # phai la None (KHONG phai DomainError, khong co error_code structured).
        session_repo.update.assert_awaited_once()
        updated = session_repo.update.call_args.args[0]
        assert updated.status == CrStatus.KHONG_CHAY
        assert updated.ma_loi is None

        # SSE PHAI emit su kien that bai (done=True) de FE biet CR da dung,
        # khong cho SSE mai khong bao gio toi.
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["step"] == 3
        assert last_event["status"] == "failed"
        assert last_event["done"] is True
        assert "SSH driver crash khong xac dinh" in last_event["error"]


class TestDinhTuyenOSS:
    """Giai doan 1 buoc 2 (27/09/2026, chot 27/09) - dinh tuyen OSS theo
    TUNG CELL (khong theo tram tat). Xem application/trigger_cr_use_case.py::
    _chon_oss_va_loc_cells(), domain/services/oss_routing.py,
    adapters/netact/oss_router_env.py."""

    async def test_import_provision_that_bai_van_ghi_oss_instance_id_va_noc(self):
        # Item 4 (02/10/2026) - OSS DA duoc chon VA DA dung that (submit_cr()
        # duoc goi) nhung Import/Provision tren NetAct that bai (ok=False) -
        # KHAC "tu choi TRUOC khi chon OSS": o day OSS THAT SU da gui CR len,
        # chi ket qua la loi - van PHAI ghi oss_instance_id/noc, KHONG de NULL.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        netact_gw.submit_cr.return_value = {
            "ok": False,
            "trang_thai": "FAILED",
            "buoc_loi": "provision",
            "dn_list": [],
            "so_cell_thanh_cong": None,
            "so_cell_tong": None,
            "tom_tat": "Provision that bai: NoRouteToHost",
        }
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.FAILED
        netact_gw.submit_cr.assert_awaited_once()  # OSS DA duoc dung that
        session_repo.update.assert_awaited_once()
        updated = session_repo.update.call_args.args[0]
        assert updated.status == CrStatus.FAILED
        assert updated.oss_instance_id == "NA09"
        assert updated.noc == "NOC1"

    async def test_cell_HNI_goi_chon_oss_dung_khoa_ma_tinh_cu_va_vendor(self):
        # Ca 4 cell fixture (_RAW_HUONGS) deu ket thuc "-HNI" - chon_oss()
        # PHAI duoc goi voi dung khoa (ma_tinh_cu="HNI", vendor=NOKIA) cho
        # TUNG cell, va submit_cr() nhan dung OssInstance ma chon_oss() tra ve.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.DONE
        goi = uc._oss_router.chon_oss.call_args_list  # noqa: SLF001
        assert len(goi) == 4  # 4 cell (A/B/C/D) deu qua dinh tuyen OSS
        assert all(c.args == ("HNI", Vendor.NOKIA) for c in goi)
        assert netact_gw.submit_cr.call_args.args[3] == _OSS_HNI

    async def test_cell_HGG_dinh_tuyen_theo_hau_to_ten_KHONG_theo_tram(self):
        # Ca THAT quyet dinh 27/09/2026 dai dien: tram TAT co the co ma_tinh
        # (cot DB, ma MOI sau sap nhap) la "TQG" (Tuyen Quang), nhung 1 cell
        # lan can ten "...-HGG" (Ha Giang, ma CU - Netact14, KI-08) van PHAI
        # duoc dinh tuyen theo HGG. enodeb_repo.get_ma_tinh da BI BO hoan toan
        # khoi flow (dat "TQG" de CHUNG MINH gia tri do KHONG duoc dung toi -
        # neu code con lo doc no thi test se FAIL vi chon_oss se bi goi voi
        # "TQG" thay vi "HGG").
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.return_value = [
            {
                "huong_id": 11,
                "huong_name": "4G-TST001M11-HNI",
                "cells": [
                    {
                        "cell_id": DN_A,
                        "cell_name": "4G-CELL-E-HGG",
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
        ]
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {DN_A: RsboostLevel(0.0)}
        enodeb_repo.get_ma_tinh.return_value = "TQG"  # CO Y "sai" - xem chu y tren
        oss_hgg = OssInstance(instance_id="NA14", host="10.212.247.20", user="test_user", password="test_password")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._oss_router.chon_oss.return_value = oss_hgg  # noqa: SLF001

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.DONE
        uc._oss_router.chon_oss.assert_called_once_with("HGG", Vendor.NOKIA)  # noqa: SLF001
        enodeb_repo.get_ma_tinh.assert_not_awaited()
        assert netact_gw.submit_cr.call_args.args[3] == oss_hgg

    async def test_cell_ten_sai_mau_bi_loai_ly_do_TEN_CELL_SAI_MAU(self):
        # Ten cell KHONG dung mau "4G-...-XXX" (thieu hau to 3 chu hoa, vd
        # fixture CU truoc 09/2026) - khong suy duoc ma_tinh_cu nen KHONG the
        # dinh tuyen. Goi TRUC TIEP _prepare_plan() (method "internal" nhung
        # CHIA SE co chu dich - xem application/preview_cr_use_case.py) de
        # doc duoc PlanResult.cell_ngoai_pham_vi_chi_tiet, khong quan sat duoc
        # tu execute() (chi tra ve CrSession).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.return_value = [
            {
                "huong_id": 11,
                "huong_name": "4G-TST001M11-HNI",
                "cells": [
                    {
                        "cell_id": DN_A,
                        "cell_name": "4G-CELL-X",  # hau to "-X" chi 1 ky tu, khong khop "-XXX"
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
        ]
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)

        plan = await uc._prepare_plan(TRAM_ID, TRAM_NAME, "shutdown")  # noqa: SLF001

        assert plan.cells == []  # cell bi loai, KHONG con trong danh sach dieu chinh CR
        assert plan.oss_instance is None
        assert "4G-CELL-X" in plan.cell_ngoai_pham_vi
        assert {"cell_name": "4G-CELL-X", "ly_do": "TEN_CELL_SAI_MAU"} in plan.cell_ngoai_pham_vi_chi_tiet
        uc._oss_router.chon_oss.assert_not_called()  # noqa: SLF001 - khong suy duoc khoa nen khong goi toi

    async def test_OSS_chua_cau_hinh_bi_loai_ly_do_OSS_CHUA_CAU_HINH(self):
        # Ten cell dung mau, suy duoc ma_tinh_cu, nhung IOssRouter.chon_oss()
        # tra None (chua co route/credential con placeholder "???" - xem
        # domain/ports/outbound/gateway_ports.py::IOssRouter.chon_oss()).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._oss_router.chon_oss.return_value = None  # noqa: SLF001

        plan = await uc._prepare_plan(TRAM_ID, TRAM_NAME, "shutdown")  # noqa: SLF001

        assert plan.cells == []
        assert plan.oss_instance is None
        # Ca 4 cell fixture (A/B/C/D) deu bi loai vi CUNG 1 ly do.
        assert len(plan.cell_ngoai_pham_vi_chi_tiet) == 4
        assert all(d["ly_do"] == "OSS_CHUA_CAU_HINH" for d in plan.cell_ngoai_pham_vi_chi_tiet)

    async def test_cell_thuoc_2_OSS_khac_nhau_raise_CR_NHIEU_OSS(self):
        # 2 huong, moi huong 1 cell, hau to ten KHAC nhau ("-HNI" va "-HGG") -
        # chon_oss() tra OssInstance KHAC nhau cho tung khoa (mo phong bang
        # side_effect thay vi return_value co dinh). 1 CR khong the tu dong
        # tach 2 XML gui 2 OSS -> phai raise CR_NHIEU_OSS, session -> KHONG_CHAY
        # (SUA 16/10/2026, yeu cau truc tiep user, "TRANG THAI KHONG_CHAY" -
        # loi o buoc 3, TRUOC BUOC_SSH_BAT_DAU=13, nen la KHONG_CHAY chu KHONG
        # con la FAILED - xem test_cds_api_error_buoc_3_tra_ve_khong_chay_khong_raise()
        # lam mau).
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.return_value = [
            {
                "huong_id": 11,
                "huong_name": "4G-TST001M11-HNI",
                "cells": [
                    {
                        "cell_id": DN_A,
                        "cell_name": "4G-CELL-E-HNI",
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
            {
                "huong_id": 12,
                "huong_name": "4G-TST001M12-HNI",
                "cells": [
                    {
                        "cell_id": DN_B,
                        "cell_name": "4G-CELL-F-HGG",
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
        ]
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {
            DN_A: RsboostLevel(0.0),
            DN_B: RsboostLevel(0.0),
        }
        oss_na09 = _OSS_HNI
        oss_na14 = OssInstance(instance_id="NA14", host="10.212.247.20", user="test_user", password="test_password")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._oss_router.chon_oss.side_effect = (  # noqa: SLF001
            lambda ma_tinh_cu, vendor: oss_na09 if ma_tinh_cu == "HNI" else oss_na14
        )

        result = await uc.execute(TRAM_ID, TRAM_NAME, "shutdown")

        assert result.status == CrStatus.KHONG_CHAY
        netact_gw.submit_cr.assert_not_awaited()  # loi CHAN CA CR truoc khi kip goi SSH
        session_repo.update.assert_awaited_once()
        updated = session_repo.update.call_args.args[0]
        assert updated.status == CrStatus.KHONG_CHAY
        assert updated.ma_loi == "CR_NHIEU_OSS"
        # oss_instance_id/noc (02/10/2026) - CrNhieuOssError raise BEN TRONG
        # _prepare_plan() (2 OSS khac nhau, KHONG chon duoc 1 cai cu the) -
        # _prepare_plan() KHONG BAO GIO tra ve, nen oss_da_chon van None -> NULL.
        assert updated.oss_instance_id is None
        assert updated.noc is None
        last_event = event_bus.publish.call_args_list[-1].args[1]
        assert last_event["status"] == "failed"
        assert "NA09" in last_event["error"] and "NA14" in last_event["error"]

    async def test_prepare_plan_raise_CrNhieuOssError_truc_tiep_khi_goi_doc_lap(self):
        # PreviewCrUseCase goi _prepare_plan() TRUC TIEP, KHONG qua try/except
        # cua run_cr_flow() (xem application/preview_cr_use_case.py) - loi
        # PHAI la exception THAT SU (khong bi nuot thanh FAILED) de router
        # /cr/preview map sang 422 dung nhu CrNoNeighborCellError.
        network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus = _make_mocks()
        network_gw.get_cell_neighbors.return_value = [
            {
                "huong_id": 11,
                "huong_name": "4G-TST001M11-HNI",
                "cells": [
                    {
                        "cell_id": DN_A,
                        "cell_name": "4G-CELL-E-HNI",
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
            {
                "huong_id": 12,
                "huong_name": "4G-TST001M12-HNI",
                "cells": [
                    {
                        "cell_id": DN_B,
                        "cell_name": "4G-CELL-F-HGG",
                        "priority": 1,
                        "technology": "4G",
                        "status": "active",
                    },
                ],
            },
        ]
        cell_infor_repo.get_rsboost_by_neighbor_dns.return_value = {
            DN_A: RsboostLevel(0.0),
            DN_B: RsboostLevel(0.0),
        }
        oss_na14 = OssInstance(instance_id="NA14", host="10.212.247.20", user="test_user", password="test_password")
        uc = _make_use_case(network_gw, netact_gw, session_repo, cell_repo, cell_infor_repo, enodeb_repo, event_bus)
        uc._oss_router.chon_oss.side_effect = (  # noqa: SLF001
            lambda ma_tinh_cu, vendor: _OSS_HNI if ma_tinh_cu == "HNI" else oss_na14
        )

        with pytest.raises(CrNhieuOssError):
            await uc._prepare_plan(TRAM_ID, TRAM_NAME, "shutdown")  # noqa: SLF001
