"""
Unit test cho NeighborCellFilter — thay the NeighborCellService + BandPriorityFilter
+ NbLncelFilter + HuongCellSelector (da xoa).
Tu: yeu cau user 13072026 (rewrite tu dau, 4 buoc), verify bang du lieu CDS
that (tests/fixtures/cds_neighbors_110548.json — 368 cell, tram_id=110548).

22072026: NeighborCellFilter tach 2 method - filter_for_cr() (Nhanh B, TRUOC
day ten la filter(), doi ten khi tach nhanh - GIU NGUYEN toan bo test cu, chi
doi ten goi ham, KHONG doi assertion nao) va filter_affected() (Nhanh A, MOI -
xem TestNhanhA ben duoi). tram_goc_id mac dinh None trong ca 2 method nen moi
test cu o day KHONG can sua them gi ngoai doi ten ham.
"""

import json
import logging
from pathlib import Path

import pytest

from domain.services.neighbor_cell_filter import (
    LY_DO_BAND_KHONG_CHAY_CR,
    LY_DO_CELL_ID_PHANG,
    LY_DO_SMALL_CELL,
    NeighborCellFilter,
)
from domain.services.priority_assigner import PriorityAssigner

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "cds_neighbors_110548.json"


# SUA FIXTURE 07092026 (khong noi long guard): 4 placeholder cell_id ngan
# ("c1"/"c2"/"c11"/"c13") da doi sang DN Nokia THAT. Ly do: filter_affected()
# gio LOAI cell co cell_id khong phai DN Nokia (tin hieu "CDS khong quan ly
# cell nay" - xem neighbor_cell_filter.py), nen placeholder ngan bi loai het va
# 12 test ra tap RONG.
# Placeholder do von la du lieu KHONG THUC TE - CDS chua bao gio tra cell_id
# dang do cho cell no quan ly. Doi fixture cho dung thuc te, KHONG sua guard.
def make_cell_dict(cell_id: str, cell_name: str, priority: int, technology: str = "4G", status: str = "active") -> dict:
    return {"cell_id": cell_id, "cell_name": cell_name, "priority": priority, "technology": technology, "status": status}


def make_huong(huong_id: int, cells: list[dict]) -> dict:
    # CAP NHAT 21072026: NeighborCellFilter gio suy huong_id tu VI TRI CO
    # DINH trong huong_name (khong con doc truc tiep field huong_id) - ten
    # gia lap phai dung dinh dang 16 ky tu that (huong_id o vi tri [10:12]),
    # khac truoc chi la placeholder "huong-{id}" khong theo format san xuat.
    huong_name = f"4G-TST001M{huong_id:02d}-HNI"
    return {"huong_id": huong_id, "huong_name": huong_name, "cells": cells}


class TestVerifyDuLieuThat:
    def test_368_cell_that_khop_chinh_xac_bang_tay(self):
        # TINH LAI BANG TAY 04/10/2026 (quyet dinh 03/10/2026, luat chon cell
        # CR moi - band cua CHINH CELL LAN CAN, khong phai cua huong tram tat).
        # Fixture co 12 huong_id (11/12/13/31/32/33/41/42/43/51/52/53), nhom
        # theo sector Y=huong_id%10 -> 3 sector (Y=1: huong 11/31/41/51; Y=2:
        # huong 12/32/42/52; Y=3: huong 13/33/43/53) - KHONG con gioi han chi
        # xet X=1/X=3 nhu truoc, MOI huong cua sector deu dong gop ung vien.
        #
        # Buoc tay (doc lai 368 dong tho, doc lap voi ham dang test):
        #  - Sector Y=1 (huong 11 X=1 xu ly truoc theo BAND_PRIORITY): candidate
        #    co priority nho nhat la DDA155M12 (pr1, LNCEL-12 -> F1) va
        #    HBG295M11 (pr2, LNCEL-11 -> F1) - ca 2 deu tu huong 11, khong
        #    huong nao khac cho priority nho hon. -> rsboost=DDA155M12,
        #    qrxlevmin=HBG295M11.
        #  - Sector Y=2: huong 12 (X=1) cho BDH271M11 pr1 (LNCEL-11->F1); huong
        #    32 (X=3) cho CUNG cell BDH222M12 nhung pr1 (LNCEL-12->F1), tot hon
        #    pr2 cua no o huong 12 -> BDH222M12 "chuyen" nguon ve huong 32.
        #    -> rsboost=BDH271M11 (huong 12), qrxlevmin=BDH222M12 (huong 32).
        #  - Sector Y=3: huong 13 (X=1) cho BDH191M11 pr1 (LNCEL-11->F1, giu)
        #    va HBG295M51 pr2 NHUNG LNCEL-51 (bat dau "5") KHONG khop
        #    ^[13][0-9]$ -> loai (BAND_KHONG_CHAY_CR). Ung vien pr2 ke tiep
        #    sau khi loai: DDA132M12, tot nhat tu huong 43 (X=4) voi pr2
        #    (LNCEL-12->F1, thay vi pr8 cua no o huong 13). DDA155M12/
        #    HBG295M11 (pr1/pr3 cua sector nay) da bi CHON O SECTOR 1 (Y=1,
        #    xu ly truoc) nen bi dedup xuyen sector, bo qua.
        #    -> rsboost=BDH191M11 (huong 13), qrxlevmin=DDA132M12 (huong 43).
        #
        # KET QUA DOI so voi truoc 03/10/2026 o 2 diem: (1) BDH222M12 gio gan
        # huong_id=32 (khong phai 12, vi huong 32 cho priority tot hon); (2)
        # sector 3 lay DDA132M12 thay vi HBG295M51 (HBG295M51 bi loai vi LNCEL
        # cua chinh no la LNCEL-51, khong phai band huong tram tat).
        raw_huongs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["huongs"]

        result = NeighborCellFilter().filter_for_cr(raw_huongs)
        PriorityAssigner().assign(result)

        actual = {(int(c.huong_id), c.priority, c.cell_name, c.action_type) for c in result}
        expected = {
            (11, 1, "4G-DDA155M12-HNI", "rsboost"), (11, 2, "4G-HBG295M11-HNI", "qrxlevmin"),
            (12, 1, "4G-BDH271M11-HNI", "rsboost"), (32, 1, "4G-BDH222M12-HNI", "qrxlevmin"),
            (13, 1, "4G-BDH191M11-HNI", "rsboost"), (43, 2, "4G-DDA132M12-HNI", "qrxlevmin"),
        }
        assert actual == expected
        assert len(result) == 6

    def test_dist_name_dung_cell_id_goc_tu_CDS(self):
        raw_huongs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["huongs"]
        result = NeighborCellFilter().filter_for_cr(raw_huongs)
        cell_a = next(c for c in result if c.cell_name == "4G-DDA155M12-HNI")
        assert cell_a.dist_name == "PLMN-PLMN/MRBTS-115750/LNBTS-115750/LNCEL-12"
        assert cell_a.dist_name == cell_a.cell_id

    def test_110548_tinh_lai_bang_tay_sau_quyet_dinh_03102026_band_cell_lan_can(self):
        # TINH LAI BANG TAY 04/10/2026 (quyet dinh 03/10/2026) - xem chi tiet
        # tung buoc trong test_368_cell_that_khop_chinh_xac_bang_tay o tren
        # (cung fixture, cung ket qua, khac goc nhin: test nay xac nhan Nhanh A
        # (danh gia QoS/QoE + xuat phieu, KHONG loc band) van GIU NGUYEN 47
        # cell - CHI Nhanh B (CR) doi theo luat band moi).
        #
        # Small cell: van KHONG co cell S/P nao trong fixture nay (xem quyet
        # dinh 02/10/2026 cu) - khong anh huong ket qua.
        raw_huongs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["huongs"]
        nf = NeighborCellFilter()

        affected = nf.filter_affected(raw_huongs)
        assert len(affected) == 47  # danh sach danh gia QoS/QoE + xuat phieu - khong doi, Nhanh A khong loc band

        cr_cells = nf.filter_for_cr(raw_huongs, affected_cells=affected)
        assert {c.cell_name for c in cr_cells} == {
            "4G-DDA155M12-HNI", "4G-HBG295M11-HNI",
            "4G-BDH271M11-HNI", "4G-BDH222M12-HNI",
            "4G-BDH191M11-HNI", "4G-DDA132M12-HNI",
        }  # danh sach chay CR - DOI so voi truoc 03/10/2026: HBG295M51 (LNCEL-51,
        # khong khop band cell) bi thay bang DDA132M12 (tu huong 43, LNCEL-12)


class TestBuoc1LocKyThuat:
    def test_technology_khac_4G_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-A-HNI", 1, technology="3G")])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_status_khong_active_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-A-HNI", 1, status="inactive")])]
        assert NeighborCellFilter().filter_for_cr(raw) == []


class TestBuoc2BandCuaChinhCell:
    """Quyet dinh 03/10/2026 (THAY THE hoan toan luat band-theo-huong cu 02/10):
    band gio la cua CHINH CELL LAN CAN (suy tu LNCEL trong DN cua no), KHONG
    phai cua huong tram tat. filter_for_cr() KHONG con chon 1 huong "thang"
    moi sector - MOI huong deu dong gop ung vien, chi loc/dedup o muc CELL."""

    def test_LNCEL_bat_dau_1_duoc_giu_band_F1(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-A-HNI", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {"4G-A-HNI"}
        assert result[0].band == "1800 F1"

    def test_LNCEL_bat_dau_3_duoc_giu_band_F2(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-31", "4G-A-HNI", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {"4G-A-HNI"}
        assert result[0].band == "1800 F2"

    def test_LNCEL_bat_dau_4_hoac_5_bi_loai(self):
        # Band cua HUONG TRAM TAT (huong 11, X=1 - truoc 03/10 se duoc "thang"
        # sector) KHONG con quyet dinh gi nua - cell bi loai vi CHINH no mang
        # LNCEL-41/51 (900/2100), du huong chua no la huong uu tien cao nhat.
        raw = [make_huong(11, [
            make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-41", "4G-BAND4-HNI", 1),
            make_cell_dict("PLMN-PLMN/MRBTS-902/LNBTS-902/LNCEL-51", "4G-BAND5-HNI", 2),
        ])]
        nf = NeighborCellFilter()
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []
        result = nf.filter_for_cr(raw, cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet)
        assert result == []
        assert {"cell_name": "4G-BAND4-HNI", "ly_do": LY_DO_BAND_KHONG_CHAY_CR} in cell_ngoai_pham_vi_chi_tiet
        assert {"cell_name": "4G-BAND5-HNI", "ly_do": LY_DO_BAND_KHONG_CHAY_CR} in cell_ngoai_pham_vi_chi_tiet

    def test_LNCEL_112_khong_khop_2_chu_so_bi_loai(self):
        # Du lieu that (khao sat tram 110548 ngay 03/10/2026) - LNCEL-112 xuat
        # hien 12 lan trong fixture, KHONG khop ^[13][0-9]$ (3 chu so, khong
        # phai 2) du bat dau bang "1".
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-112", "4G-A-HNI", 1)])]
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []
        result = NeighborCellFilter().filter_for_cr(raw, cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet)
        assert result == []
        assert {"cell_name": "4G-A-HNI", "ly_do": LY_DO_BAND_KHONG_CHAY_CR} in cell_ngoai_pham_vi_chi_tiet

    def test_filter_affected_khong_loc_band_cua_cell(self):
        # Nhanh A (danh gia QoS/QoE + xuat phieu) KHONG loc band - cell LNCEL-41
        # van co mat, CHI Nhanh B (CR) moi loai.
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-41", "4G-BAND4-HNI", 1)])]
        nf = NeighborCellFilter()
        affected = nf.filter_affected(raw)
        assert {c.cell_name for c in affected} == {"4G-BAND4-HNI"}
        cr = nf.filter_for_cr(raw, affected_cells=affected)
        assert cr == []

    def test_cell_trung_2_huong_cung_sector_giu_priority_nho_nhat(self):
        # Du lieu that tram 160008 (khao sat 03/10/2026) - CUNG 1 cell co mat
        # o 2 huong KHAC NHAU cung sector (Y=1: huong 11 X=1, huong 51 X=5),
        # priority khac nhau - phai giu ban priority NHO NHAT (tot hon),
        # KHONG phai ban cua huong xu ly truoc.
        raw = [
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-DUP-HNI", 2)]),
            make_huong(51, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-DUP-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1
        assert result[0].priority == 1  # priority nho nhat (tu huong 51), KHONG phai 2 cua huong 11

    def test_priority_bang_nhau_2_huong_giu_ban_tu_huong_band_uu_tien_cao_hon(self):
        # Priority BANG NHAU o 2 huong (X=1 vs X=4, cung sector Y=1) - tie-break
        # dung BAND_PRIORITY (1 > 4): giu ban tu huong X=1 (huong_id=11).
        raw = [
            make_huong(41, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-DUP-HNI", 1)]),
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-DUP-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1
        assert result[0].huong_id == "11"  # giu ban tu huong X=1, khong phai X=4

    def test_khong_gioi_han_so_sector(self):
        # SUA 03/10/2026 - truoc day luat band cu khong tuong minh gioi han
        # sector, nhung test nay xac nhan RO: nhieu sector (Y khac nhau) deu
        # duoc xu ly binh thuong, khong co "tran" so luong sector.
        raw = [
            make_huong(10 + y, [make_cell_dict(f"PLMN-PLMN/MRBTS-{y}/LNBTS-{y}/LNCEL-11", f"4G-S{y}-HNI", 1)])
            for y in range(1, 6)
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {f"4G-S{y}-HNI" for y in range(1, 6)}

    def test_sector_tra_ve_dung_cell_sector_cua_tram_tat(self):
        raw = [make_huong(52, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-A-HNI", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert result[0].sector == 2  # Y = 52 % 10 = 2, X=5 KHONG lien quan


class TestDuLieuThatTram160008:
    """Du lieu THAT lay tu CDS /cell/neighbors cho tram 160008 (khao sat
    03/10/2026, truoc khi quyet dinh luat band moi) - 5 huong, dung de xac
    nhan thuat toan moi tren chinh du lieu da phat hien van de (cell
    TAN025M13-CBG xuat hien o CA huong "M" (X=5) va "W" (X=1) cung sector,
    minh hoa dung tinh huong user mo ta khi quyet dinh bo luat band-theo-huong
    cu)."""

    _TAN023 = "PLMN-PLMN/MRBTS-160023/LNBTS-160023/LNCEL-13"
    _TAN025 = "PLMN-PLMN/MRBTS-160025/LNBTS-160025/LNCEL-13"
    _TAN050 = "PLMN-PLMN/MRBTS-160050/LNBTS-160050/LNCEL-11"

    @classmethod
    def _raw_huongs(cls) -> list[dict]:
        # 3 huong "M52/W51/W54" mang CUNG 3 cell/priority (sector 1 va 2 giao
        # nhau qua cell TAN023/TAN025/TAN050) - dung THAT trong fixture goc,
        # khong phai gia lap dun cho test.
        bo_3_cell = [
            make_cell_dict(cls._TAN023, "4G-TAN023M13-CBG", 1),
            make_cell_dict(cls._TAN025, "4G-TAN025M13-CBG", 2),
            make_cell_dict(cls._TAN050, "4G-TAN050M11-CBG", 3),
        ]
        return [
            {"huong_id": 52, "huong_name": "4G-TAN001M52-CBG", "cells": bo_3_cell},
            {"huong_id": None, "huong_name": "4G-TAN001W11-CBG", "cells": [make_cell_dict(cls._TAN025, "4G-TAN025M13-CBG", 1)]},
            {"huong_id": None, "huong_name": "4G-TAN001W14-CBG", "cells": [make_cell_dict(cls._TAN025, "4G-TAN025M13-CBG", 1)]},
            {"huong_id": None, "huong_name": "4G-TAN001W51-CBG", "cells": bo_3_cell},
            {"huong_id": None, "huong_name": "4G-TAN001W54-CBG", "cells": bo_3_cell},
        ]

    def test_dung_3_cell_sector_1_va_2_sector_4_rong(self):
        # TINH TAY (xem KHAO SAT 03/10/2026, doc lap voi ham dang test):
        #  - Sector 1 (huong_id %10==1: huong 11 X=1, huong 51 X=5) - gop ca
        #    2, dedup TAN025M13 (pr1 o huong11 X=1, pr2 o huong51 X=5 -> giu
        #    pr1 tu huong11) + TAN023M13 (chi o huong51, pr1) + TAN050M11
        #    (chi o huong51, pr3) -> sort (1,1)TAN025M13, (1,4...)TAN023M13
        #    (X=5->rank3) -> top2: TAN025M13 (rsboost), TAN023M13 (qrxlevmin).
        #  - Sector 2 (chi huong 52, X=5): TAN023M13(pr1), TAN025M13(pr2),
        #    TAN050M11(pr3) - nhung TAN023M13/TAN025M13 DA CHON o sector 1
        #    (xu ly truoc, Y=1<2) -> dedup xuyen sector bo qua CA 2 (khong
        #    tinh vao suat da chon) -> con lai TAN050M11 -> rsboost (1 minh).
        #  - Sector 4 (huong 14, 54 - CA 3 cell deu DA CHON o sector 1/2) ->
        #    dedup xuyen sector loai sach -> RONG.
        raw = self._raw_huongs()
        nf = NeighborCellFilter()
        affected = nf.filter_affected(raw)
        assert {c.cell_name for c in affected} == {
            "4G-TAN023M13-CBG", "4G-TAN025M13-CBG", "4G-TAN050M11-CBG",
        }

        result = nf.filter_for_cr(raw, affected_cells=affected)
        PriorityAssigner().assign(result)

        by_sector: dict[int, list[tuple]] = {}
        for c in result:
            by_sector.setdefault(c.sector, []).append((c.cell_name, c.action_type))

        assert by_sector == {
            1: [("4G-TAN025M13-CBG", "rsboost"), ("4G-TAN023M13-CBG", "qrxlevmin")],
            2: [("4G-TAN050M11-CBG", "rsboost")],
        }
        assert 4 not in by_sector  # sector 4 rong - khong co entry nao
        assert len(result) == 3

    def test_band_tra_dung_1800_F1_ca_3_cell(self):
        # Ca 3 cell (TAN023/025M13 LNCEL-13, TAN050M11 LNCEL-11) deu band F1 -
        # xac nhan field Cell.band (THEM 03/10/2026) tra dung cho preview.
        raw = self._raw_huongs()
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.band for c in result} == {"1800 F1"}


class TestBuoc3LocCellKhongHopLe:
    def test_NB_prefix_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "NB-XXX-HNI", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_MBF_prefix_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "MBF_XXX-HNI", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_LNCEL_local_id_bat_dau_bang_2_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-211", "4G-X-HNI", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_LNCEL_local_id_khong_bat_dau_bang_2_duoc_giu(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-12", "4G-X-HNI", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1

    def test_VNP_prefix_bi_loai(self):
        # BUSINESS_RULES.md SS2.2 ③ - operator khac (Viettel), khong phai rule "ngu"
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "VNP-XXX-HNI", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_cell_id_null_bi_loai(self):
        raw = [make_huong(11, [{"cell_id": None, "cell_name": "4G-X-HNI", "priority": 1, "technology": "4G", "status": "active"}])]
        assert NeighborCellFilter().filter_for_cr(raw) == []

    def test_cell_id_rong_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("", "4G-X-HNI", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []


class TestBuoc3bSmallCell:
    """Quyet dinh 02/10/2026 - KHONG dua small cell (loai S/P) vao BAT KY
    danh sach nao (CR lan danh gia QoS/QoE/xuat phieu - SUA PHAM VI, ban dau
    chi dinh "khong chay CR"). Nhom nay tap trung kiem tra Buoc 3b (loai
    TRUOC buoc chon toi da MAX_CELLS_PER_HUONG=2) trong filter_for_cr() -
    xem TestNhanhADanhGiaAnhHuong cho phan loai o filter_affected()."""

    def test_small_cell_bi_loai_o_CA_filter_affected_LAN_filter_for_cr_chi_1_ly_do(self):
        # Item 1 (02/10/2026) - mo phong DUNG pattern production
        # (trigger_cr_use_case.py::_prepare_plan()): goi filter_affected()
        # TRUOC voi 2 list rong, roi goi filter_for_cr() VOI affected_cells=
        # ket qua do VA CUNG 2 list - ly do SMALL_CELL phai xuat hien DUNG 1
        # lan (phat sinh trong filter_affected(), khong bi filter_for_cr()
        # Buoc 3b ghi lai lan 2 vi cell da khong con trong affected_names).
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-TPO065S11-TQG", 1)])]
        nf = NeighborCellFilter()
        cell_ngoai_pham_vi: list[str] = []
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []

        affected = nf.filter_affected(
            raw, ngoai_pham_vi=cell_ngoai_pham_vi, ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet
        )
        assert affected == []  # Nhanh A cung loai small cell (item 1)

        cr = nf.filter_for_cr(
            raw,
            affected_cells=affected,
            cell_ngoai_pham_vi=cell_ngoai_pham_vi,
            cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet,
        )
        assert cr == []
        assert cell_ngoai_pham_vi.count("4G-TPO065S11-TQG") == 1
        assert cell_ngoai_pham_vi_chi_tiet.count({"cell_name": "4G-TPO065S11-TQG", "ly_do": LY_DO_SMALL_CELL}) == 1

    def test_goi_filter_for_cr_doc_lap_khong_truyen_affected_cells_van_ghi_dung_1_lan(self):
        # filter_for_cr() TU goi filter_affected() ben trong (affected_cells=
        # None, "khong qua filter_affected" theo nghia caller KHONG tu goi
        # rieng) - van phai chuyen tiep cell_ngoai_pham_vi/_chi_tiet xuong loi
        # goi noi bo do, neu khong ly do SMALL_CELL se "mat" (BUG da phat hien
        # va sua trong luc viet test nay - xem comment trong filter_for_cr()).
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-TPO065S11-TQG", 1)])]
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []
        result = NeighborCellFilter().filter_for_cr(raw, cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet)

        assert result == []
        assert cell_ngoai_pham_vi_chi_tiet == [{"cell_name": "4G-TPO065S11-TQG", "ly_do": LY_DO_SMALL_CELL}]

    def test_small_cell_priority_1_bi_loai_2_macro_con_lai_duoc_chon(self):
        # Huong co 3 cell: small cell (S) priority 1 (cao nhat), 2 macro (M)
        # priority 2/3. Neu loai SAU buoc chon thi small cell se chiem suat
        # rank1, chi con 1 macro duoc chon (rank2) - loai TRUOC thi 2 macro
        # (priority 2,3) duoc chon du khong phai priority thap nhat tuyet doi.
        raw = [
            make_huong(
                11,
                [
                    make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-TPO065S11-TQG", 1),
                    make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-12", "4G-TPO065M12-TQG", 2),
                    make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-13", "4G-TPO065M13-TQG", 3),
                ],
            )
        ]
        cell_ngoai_pham_vi: list[str] = []
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []
        result = NeighborCellFilter().filter_for_cr(
            raw,
            cell_ngoai_pham_vi=cell_ngoai_pham_vi,
            cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet,
        )

        assert {c.cell_name for c in result} == {"4G-TPO065M12-TQG", "4G-TPO065M13-TQG"}
        assert "4G-TPO065S11-TQG" in cell_ngoai_pham_vi
        assert {"cell_name": "4G-TPO065S11-TQG", "ly_do": LY_DO_SMALL_CELL} in cell_ngoai_pham_vi_chi_tiet

    def test_cell_P_cung_bi_loai(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-TPO065P11-TQG", 1)])]
        cell_ngoai_pham_vi_chi_tiet: list[dict] = []
        result = NeighborCellFilter().filter_for_cr(raw, cell_ngoai_pham_vi_chi_tiet=cell_ngoai_pham_vi_chi_tiet)

        assert result == []
        assert {"cell_name": "4G-TPO065P11-TQG", "ly_do": LY_DO_SMALL_CELL} in cell_ngoai_pham_vi_chi_tiet

    @pytest.mark.parametrize("loai", ["W", "F", "E", "X", "R"])
    def test_loai_khac_S_P_van_duoc_chon(self, loai):
        # 6 loai con lai (du lieu that 5 NetAct) deu la macro/cac loai tram
        # lon khac - KHONG bi loai boi Buoc 3b.
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", f"4G-TPO065{loai}11-TQG", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {f"4G-TPO065{loai}11-TQG"}

    def test_khong_truyen_out_param_van_loai_dung_chi_khong_ghi_bao_cao(self):
        # cell_ngoai_pham_vi/cell_ngoai_pham_vi_chi_tiet mac dinh None - ham
        # van PHAI loai small cell dung (HANH VI LOC), chi bo qua buoc ghi
        # bao cao (khong AttributeError/crash khi None).
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-TPO065S11-TQG", 1)])]
        assert NeighborCellFilter().filter_for_cr(raw) == []


class TestSuyHuongIdTuTen:
    # CAP NHAT 21072026 (thay the TestBuoc1HuongIdNone cu) - guard cu
    # "if huong_id is None: continue" (C1.4-fix3, 20072026) la SAI ve nghiep
    # vu: loai oan toan bo nhom huong ten "W..." (BUG THAT phat hien qua
    # trace tram 111139/session #203 - 11/13 huong bi loai, chi con 1 cell
    # song sot). Sua: huong_id gio SUY TU huong_name (vi tri co dinh [10:12]),
    # khong con phu thuoc field huong_id CDS tra ve (khong dang tin, tra null
    # cho nhom "W"). Nhom test nay xac nhan hanh vi MOI.
    def test_huong_id_none_tu_CDS_van_duoc_xu_ly_qua_ten_suy_ra(self):
        # Truoc fix: huong nay bi loai sach vi huong_id (CDS) la None.
        # Sau fix: huong_name "4G-TST001W11-HNI" hop le (16 ky tu, vi tri
        # [10:12]="11") -> suy huong_id=11, THAM GIA xu ly binh thuong du
        # ky tu loai tram la "W" (khong phai "M").
        raw = [
            {"huong_id": None, "huong_name": "4G-TST001W11-HNI", "cells": [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-VALID1-HNI", 1)]},
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {"4G-VALID1-HNI"}
        assert {c.huong_id for c in result} == {"11"}

    def test_toan_bo_huong_deu_huong_id_none_tu_CDS_van_xu_ly_du_qua_ten(self):
        # Truong hop truoc day tra ve [] hoan toan (ca 2 huong bi loai) -
        # sau fix, ca 2 huong deu co ten hop le (16 ky tu) nen deu duoc suy
        # huong_id va xu ly binh thuong, KHONG con tra ve rong nua.
        raw = [
            {"huong_id": None, "huong_name": "4G-TST001W11-HNI", "cells": [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-X1-HNI", 1)]},
            {"huong_id": None, "huong_name": "4G-TST001W12-HNI", "cells": [make_cell_dict("PLMN-PLMN/MRBTS-902/LNBTS-902/LNCEL-11", "4G-X2-HNI", 1)]},
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {"4G-X1-HNI", "4G-X2-HNI"}
        assert {c.huong_id for c in result} == {"11", "12"}

    def test_huong_name_do_dai_bat_thuong_bi_bo_qua_va_log_canh_bao(self, caplog):
        # Guard an toan: huong_name khong dung 16 ky tu -> vi tri [10:12] co
        # the tro sai cho khac trong ten, KHONG tach mu - bo qua huong nay +
        # log canh bao ro rang de nguoi van hanh kiem tra lai, thay vi crash
        # hoac suy ra huong_id sai.
        raw = [
            {"huong_id": None, "huong_name": "4G-TEN-NGAN-HNI", "cells": [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-X-HNI", 1)]},
        ]
        with caplog.at_level(logging.WARNING):
            result = NeighborCellFilter().filter_for_cr(raw)
        assert result == []
        assert "do dai bat thuong" in caplog.text

    def test_huong_id_cds_lech_voi_ten_uu_tien_gia_tri_tu_ten_va_log_canh_bao(self, caplog):
        # huong_id CDS=99 (gia lap lech/sai) nhung huong_name noi ro huong_id=11
        # (vi tri [10:12]) - TEN la nguon chuan theo xac nhan nghiep vu, phai
        # dung 11 (khong phai 99), chi log canh bao ve do lech.
        raw = [
            {"huong_id": 99, "huong_name": "4G-TST001M11-HNI", "cells": [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-X-HNI", 1)]},
        ]
        with caplog.at_level(logging.WARNING):
            result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.huong_id for c in result} == {"11"}
        assert "lech" in caplog.text

    def test_du_lieu_that_tram_111138_nhom_W_gio_duoc_xu_ly_qua_ten(self):
        # Fixture lay THAT tu CDS API (goi doc lap 20072026) - 6/12 huong
        # huong_id=None tu CDS (nhom ten "4G-STY007Wxx-HNI"). Truoc fix: bi
        # loai sach, chi 6 huong nhom "M" tham gia. Sau fix: nhom "W" cung
        # duoc suy huong_id tu ten va tham gia band-priority/dedup binh
        # thuong nhu nhom "M" - ket qua co nhieu huong/cell hon truoc.
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "cds_neighbors_111138.json"
        raw_huongs = json.loads(fixture_path.read_text(encoding="utf-8"))["huongs"]
        assert sum(1 for h in raw_huongs if h.get("huong_id") is None) == 6  # xac nhan fixture dung nhu mo ta

        result = NeighborCellFilter().filter_for_cr(raw_huongs)

        by_huong: dict[str, list[str]] = {}
        for c in result:
            by_huong.setdefault(c.huong_id, []).append(c.cell_name)

        # Huong 12/15 (tu nhom "W", huong_id CDS=None) gio XUAT HIEN trong
        # ket qua - bang chung song nhom "W" khong con bi loai oan.
        assert "12" in by_huong
        assert "15" in by_huong
        assert len(result) > 1  # truoc fix: chi 1 huong (13)/1 cell song sot

    def test_du_lieu_that_tram_111139_11_trong_13_huong_la_nhom_W(self):
        # Fixture lay THAT tu CDS API cho tram 111139 (trace session #203,
        # 21072026) - day chinh la bang chung goc phat hien bug: 11/13 huong
        # thuoc nhom ten "W..." (huong_id=None tu CDS), truoc fix bi loai
        # sach chi con LAI 1 cell duy nhat (huong 13, nhom "M").
        #
        # TINH LAI BANG TAY 04/10/2026 (quyet dinh 03/10/2026, luat band cua
        # CHINH CELL): toan bo cell "4G-STY008Mxx-HNI" mang LNCEL-41/42/43
        # (cua CHINH no, khong phai 11/12/13 nhu huong_id) -> band_tu_lncel()
        # tra None (khong khop ^[13][0-9]$) -> bi loai BAND_KHONG_CHAY_CR o
        # MOI huong (ke ca huong "M" - khac han luat cu, luc do huong nay
        # duoc "thang" sector vi band CUA HUONG la X=1/X=3/X=5 tuy sector).
        # CHI con "4G-STY079Mxx-HNI" (LNCEL-11/-12, band F1 THAT) song sot -
        # cell nay la neighbor CHUNG cua ca nhom "M" va "W" cung sector
        # (huong 12/32 cung Y=2 cho STY079M11; huong 15/35/55 cung Y=5 cho
        # STY079M12), dedup giu 1 ban (priority bang nhau ca 2 huong).
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "cds_neighbors_111139.json"
        raw_huongs = json.loads(fixture_path.read_text(encoding="utf-8"))["huongs"]
        assert sum(1 for h in raw_huongs if h.get("huong_id") is None) == 11  # xac nhan fixture dung nhu mo ta

        result = NeighborCellFilter().filter_for_cr(raw_huongs)

        by_huong: dict[str, list[str]] = {}
        for c in result:
            by_huong.setdefault(c.huong_id, []).append(c.cell_name)

        # Sau quyet dinh 03/10/2026: CHI 2 cell song sot (STY008Mxx bi loai
        # het vi band CUA CHINH CELL, khong con lien quan band huong) - khac
        # ket qua truoc do (3 huong/5 cell, xem comment tren).
        assert by_huong == {
            "12": ["4G-STY079M11-HNI"],
            "15": ["4G-STY079M12-HNI"],
        }
        assert len(result) == 2


class TestBuoc1DuplicateHuongId:
    def test_duplicate_huong_id_giu_entry_dau(self):
        # BUSINESS_RULES.md SS2.3 - huong_id trung, khac huong_name - first-wins
        raw = [
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-FIRST-HNI", 1)]),
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-902/LNBTS-902/LNCEL-11", "4G-SECOND-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.cell_name for c in result} == {"4G-FIRST-HNI"}


class TestBuoc4ChonToiDa2ChoDedup:
    def test_toi_da_2_cell_moi_huong(self):
        # SUA 09/2026: MAX_CELLS_PER_HUONG 4 -> 2 (quyet dinh van hanh).
        # cell_id sinh dong PHAI la DN Nokia - xem ghi chu o make_cell_dict().
        cells = [
            make_cell_dict(f"PLMN-PLMN/MRBTS-90{i}/LNBTS-90{i}/LNCEL-11", f"4G-X{i}-HNI", i)
            for i in range(1, 7)
        ]  # 6 cell, priority 1-6
        raw = [make_huong(11, cells)]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 2
        assert [c.priority for c in result] == [1, 2]

    def test_huong_it_hon_2_cell_lay_het_khong_loi(self):
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-X1-HNI", 1)])]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1

    def test_dedup_xuyen_huong_huong_xu_ly_truoc_giu_quyen(self):
        # cell_name trung nhau o 2 huong khac Y - huong_id nho hon xu ly TRUOC,
        # giu quyen; huong sau bi loai cell nay (dung theo dedup MOI, khong
        # phai rsboost-wins cua BUSINESS_RULES.md SS2.4 cu).
        raw = [
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-DUP-HNI", 3)]),
            make_huong(12, [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-DUP-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1
        assert result[0].huong_id == "11"
        assert result[0].priority == 3  # giu priority cua huong 11 (xu ly truoc), khong phai priority 1 cua huong 12

    def test_priority_giu_nguyen_gia_tri_goc_khong_renumber(self):
        cells = [make_cell_dict("PLMN-PLMN/MRBTS-901/LNBTS-901/LNCEL-11", "4G-A-HNI", 1), make_cell_dict("PLMN-PLMN/MRBTS-902/LNBTS-902/LNCEL-11", "4G-B-HNI", 6)]
        raw = [make_huong(11, cells)]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert {c.priority for c in result} == {1, 6}

    def test_sort_huong_id_tang_dan_khi_xu_ly(self):
        raw = [
            make_huong(13, [make_cell_dict("PLMN-PLMN/MRBTS-904/LNBTS-904/LNCEL-13", "4G-DUP-HNI", 1)]),
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-903/LNBTS-903/LNCEL-11", "4G-DUP-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_for_cr(raw)
        assert len(result) == 1
        assert result[0].huong_id == "11"  # huong 11 < 13, xu ly truoc, giu quyen


class TestNhanhADanhGiaAnhHuong:
    # 22072026 - Nhanh A (filter_affected) MOI, xac nhan voi user sau khi
    # trace tay tram 110548: 368 tho -> dedup 52 -> loc prefix 47 (KHONG loc
    # huong/band). filter_for_cr() (Nhanh B) phai la TAP CON cua ket qua nay.
    def test_filter_affected_tram_110548_ra_47_cell(self):
        raw_huongs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["huongs"]
        result = NeighborCellFilter().filter_affected(raw_huongs)
        assert len(result) == 47

    def test_filter_for_cr_la_tap_con_cua_filter_affected(self):
        # Nhanh B chi loc TIEP tu Nhanh A theo huong/band/rank - khong the co
        # cell nao trong Nhanh B ma khong nam trong Nhanh A.
        raw_huongs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["huongs"]
        affected_names = {c.cell_name for c in NeighborCellFilter().filter_affected(raw_huongs)}
        cr_names = {c.cell_name for c in NeighborCellFilter().filter_for_cr(raw_huongs)}
        assert cr_names <= affected_names
        # SUA 09/2026: MAX_CELLS_PER_HUONG 4 -> 2 nen 3 huong x 2 cell = 6
        # (truoc la 3 x 4 = 12) - xem TestVerifyDuLieuThat cho danh sach day du.
        assert len(cr_names) == 6

    def test_filter_affected_khong_loc_huong_band(self):
        # 2 huong CUNG sector Y=1 (huong 11 X=1, huong 31 X=3) - Nhanh B se
        # loai huong 31 (band kem hon, xem TestBuoc2BandPriority), nhung
        # Nhanh A PHAI giu ca 2 cell vi khong loc huong/band.
        raw = [
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-BAND1-HNI", 1)]),
            make_huong(31, [make_cell_dict("PLMN-PLMN/MRBTS-2/LNBTS-2/LNCEL-11", "4G-BAND3-HNI", 1)]),
        ]
        result = NeighborCellFilter().filter_affected(raw)
        assert {c.cell_name for c in result} == {"4G-BAND1-HNI", "4G-BAND3-HNI"}

    def test_filter_affected_van_ap_dung_filter_prefix_va_lncel2(self):
        raw = [make_huong(11, [
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-OK-HNI", 1),
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-12", "NB-BAD-HNI", 2),
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-13", "VNP-BAD-HNI", 3),
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-14", "MBF_BAD", 4),
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-215", "4G-LNCEL2-HNI", 5),
        ])]
        result = NeighborCellFilter().filter_affected(raw)
        assert {c.cell_name for c in result} == {"4G-OK-HNI"}

    def test_filter_affected_loai_cell_cua_tram_goc(self):
        raw = [make_huong(11, [
            make_cell_dict("PLMN-PLMN/MRBTS-110548/LNBTS-110548/LNCEL-11", "4G-SELF-HNI", 1),
            make_cell_dict("PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-11", "4G-NEIGHBOR-HNI", 2),
        ])]
        result = NeighborCellFilter().filter_affected(raw, tram_goc_id="110548")
        assert {c.cell_name for c in result} == {"4G-NEIGHBOR-HNI"}

    def test_khong_truyen_tram_goc_id_khong_loai_gi(self):
        # tram_goc_id mac dinh None - caller khong biet/khong can tram_id goc
        # (vd test cu) van goi duoc binh thuong, khong bi crash/loai oan.
        raw = [make_huong(11, [
            make_cell_dict("PLMN-PLMN/MRBTS-110548/LNBTS-110548/LNCEL-11", "4G-SELF-HNI", 1),
        ])]
        result = NeighborCellFilter().filter_affected(raw)
        assert {c.cell_name for c in result} == {"4G-SELF-HNI"}

    def test_filter_for_cr_cung_loai_cell_tram_goc(self):
        # Nhanh B tai dung Nhanh A nen cung duoc loai cell tram goc mien phi.
        raw = [make_huong(11, [
            make_cell_dict("PLMN-PLMN/MRBTS-110548/LNBTS-110548/LNCEL-11", "4G-SELF-HNI", 1),
            make_cell_dict("PLMN-PLMN/MRBTS-999999/LNBTS-999999/LNCEL-11", "4G-NEIGHBOR-HNI", 2),
        ])]
        result = NeighborCellFilter().filter_for_cr(raw, tram_goc_id="110548")
        assert {c.cell_name for c in result} == {"4G-NEIGHBOR-HNI"}

    def test_filter_affected_khong_gan_action_type(self):
        # Nhanh A khong tinh rsboost/qrxlevmin - action_type luon rong, chi
        # Nhanh B (qua priority_assigner.py) moi gan gia tri that sau nay.
        raw = [make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-A-HNI", 1)])]
        result = NeighborCellFilter().filter_affected(raw)
        assert result[0].action_type == ""

    def test_filter_affected_dedup_theo_cell_name_qua_nhieu_huong(self):
        # 1 cell la neighbor cua ca 2 huong (thuong gap that - 1 cell phu song
        # nhieu huong) - Nhanh A chi tinh 1 lan, khong nhan doi so lieu.
        raw = [
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-DUP-HNI", 1)]),
            make_huong(12, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-DUP-HNI", 2)]),
        ]
        result = NeighborCellFilter().filter_affected(raw)
        assert len(result) == 1

    def test_filter_affected_cung_loai_small_cell(self):
        # Item 1 (02/10/2026, SUA pham vi) - Nhanh A (danh gia QoS/QoE + xuat
        # phieu) GIO CUNG loai small cell, khong con "tinh ca small cell nhu
        # truoc" (hanh vi CU truoc quyet dinh nay).
        raw = [
            make_huong(11, [
                make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-TPO065S11-TQG", 1),
                make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-12", "4G-TPO065M12-TQG", 2),
            ]),
        ]
        bo_qua_chi_tiet: list[dict] = []
        result = NeighborCellFilter().filter_affected(raw, ngoai_pham_vi_chi_tiet=bo_qua_chi_tiet)

        assert {c.cell_name for c in result} == {"4G-TPO065M12-TQG"}
        assert {"cell_name": "4G-TPO065S11-TQG", "ly_do": LY_DO_SMALL_CELL} in bo_qua_chi_tiet

    def test_filter_affected_tinh_sector_tu_ten_huong(self):
        # THEM 04/10/2026 (luat xuat phieu toi da 2/sector) - sector = chu so
        # cuoi huong_id suy TU TEN (huong 11 -> Y=1), KHONG phai field huong_id
        # CDS tra ve (o day co gia tri 99 gia lap de chung minh KHONG dung no).
        raw = [{"huong_id": 99, "huong_name": "4G-TST001M11-HNI", "cells": [
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-A-HNI", 1),
        ]}]
        result = NeighborCellFilter().filter_affected(raw)
        assert result[0].sector == 1

    def test_filter_affected_cell_o_nhieu_huong_giu_sector_nho_nhat(self):
        # Cell la neighbor cua 2 huong khac sector (Y=4 va Y=1) - quyet dinh
        # 04/10/2026: giu sector NHO NHAT (1), KHONG phai sector cua huong
        # "thang" dedup (huong 14, xu ly TRUOC nen giu cac truong khac nhu
        # huong_id/priority - xem test_filter_affected_dedup_theo_cell_name_qua_nhieu_huong).
        raw = [
            make_huong(14, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-DUP-HNI", 1)]),
            make_huong(11, [make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-DUP-HNI", 2)]),
        ]
        result = NeighborCellFilter().filter_affected(raw)
        assert len(result) == 1
        assert result[0].sector == 1  # MIN(4, 1) = 1
        assert result[0].huong_id == "14"  # truong KHAC van giu ban dau tien (huong 14)

    def test_filter_affected_huong_name_khong_hop_le_sector_none(self):
        # huong_name sai dinh dang (khong suy duoc huong_id) -> sector None,
        # KHONG crash - giong cach filter_for_cr() xu ly huong khong hop le.
        raw = [{"huong_id": None, "huong_name": "4G-TEN-NGAN-HNI", "cells": [
            make_cell_dict("PLMN-PLMN/MRBTS-1/LNBTS-1/LNCEL-11", "4G-A-HNI", 1),
        ]}]
        result = NeighborCellFilter().filter_affected(raw)
        assert result[0].sector is None


# === CELL NGOAI PHAM VI CDS QUAN LY (07092026) ===
# CDS tra cell_id dang PHANG (= cell_name) cho cell no KHONG quan ly. Truoc
# 07/09 code de extract_lnbts() nem ValueError -> HTTP 500 cho ca request.
# Ca THAT: tram 112391 (NOKIA, Ha Noi) CDS tra 6 cell, 3 DN + 3 phang, trong
# do "4G-PYN015M12-VPC" (Vinh Phuc) lam vo preview.

_DN = "PLMN-PLMN/MRBTS-{0}/LNBTS-{0}/LNCEL-11"


class TestCellNgoaiPhamVi:
    def test_hon_hop_DN_va_phang_tra_ve_cell_DN_KHONG_nem_loi(self):
        # Dung hinh dang THAT cua tram 112391.
        raw = [
            make_huong(
                12,
                [
                    make_cell_dict(_DN.format(970110), "4G-SSN127M11-HNI", 1),
                    make_cell_dict(_DN.format(970111), "4G-SSN127M41-HNI", 2),
                    make_cell_dict(_DN.format(970112), "4G-SSN127M51-HNI", 3),
                    # cell_id PHANG = cell_name -> CDS khong quan ly
                    make_cell_dict("4G-PYN015M12-VPC", "4G-PYN015M12-VPC", 4),
                ],
            )
        ]
        bo_qua: list[str] = []

        ket_qua = NeighborCellFilter().filter_affected(raw, ngoai_pham_vi=bo_qua)

        assert {c.cell_name for c in ket_qua} == {
            "4G-SSN127M11-HNI",
            "4G-SSN127M41-HNI",
            "4G-SSN127M51-HNI",
        }
        assert bo_qua == ["4G-PYN015M12-VPC"]

    def test_TOAN_BO_phang_tra_mang_rong_KHONG_nem_loi(self):
        # Ca tram Huawei (280003): CDS tra cell_id phang cho toan bo.
        raw = [
            make_huong(
                11,
                [
                    make_cell_dict("4G-CLO035M51-NAN", "4G-CLO035M51-NAN", 1),
                    make_cell_dict("4G-CLO035M52-NAN", "4G-CLO035M52-NAN", 2),
                ],
            )
        ]
        bo_qua: list[str] = []

        ket_qua = NeighborCellFilter().filter_affected(raw, ngoai_pham_vi=bo_qua)

        assert ket_qua == []
        assert bo_qua == ["4G-CLO035M51-NAN", "4G-CLO035M52-NAN"]

    def test_khong_truyen_ngoai_pham_vi_van_chay_binh_thuong(self):
        # out-param la TUY CHON - caller cu (filter_for_cr, test cu) khong
        # truyen gi van phai chay.
        raw = [
            make_huong(
                11,
                [
                    make_cell_dict(_DN.format(970110), "4G-A-HNI", 1),
                    make_cell_dict("4G-B-VPC", "4G-B-VPC", 2),
                ],
            )
        ]
        ket_qua = NeighborCellFilter().filter_affected(raw)
        assert {c.cell_name for c in ket_qua} == {"4G-A-HNI"}

    def test_khong_co_cell_phang_thi_bo_dem_RONG(self):
        # Tram binh thuong (110548) - khong doi hanh vi, bo dem phai rong.
        raw = [make_huong(11, [make_cell_dict(_DN.format(110549), "4G-HKM006M42-HNI", 1)])]
        bo_qua: list[str] = []

        ket_qua = NeighborCellFilter().filter_affected(raw, ngoai_pham_vi=bo_qua)

        assert len(ket_qua) == 1
        assert bo_qua == []

    def test_cell_phang_KHONG_lot_sang_nhanh_B(self):
        # filter_for_cr() tai dung filter_affected() nen cell phang cung bi
        # loai o Nhanh B -> rsboost/qrxlevmin calculator (deu goi
        # extract_lnbts) khong bao gio nhan duoc cell phang.
        raw = [
            make_huong(
                11,
                [
                    make_cell_dict(_DN.format(970110), "4G-A-HNI", 1),
                    make_cell_dict("4G-B-VPC", "4G-B-VPC", 2),
                ],
            )
        ]
        ket_qua = NeighborCellFilter().filter_for_cr(raw)
        assert all("LNBTS-" in c.dist_name for c in ket_qua)
        assert "4G-B-VPC" not in {c.cell_name for c in ket_qua}

    def test_bo_dem_KHONG_trung_lap_khi_cell_o_nhieu_huong(self):
        # 1 cell co the la neighbor cua nhieu huong - dedup phai ap ca cho bo dem.
        c = make_cell_dict("4G-B-VPC", "4G-B-VPC", 1)
        raw = [make_huong(11, [c]), make_huong(12, [dict(c)])]
        bo_qua: list[str] = []

        NeighborCellFilter().filter_affected(raw, ngoai_pham_vi=bo_qua)

        assert bo_qua == ["4G-B-VPC"]

    def test_chi_tiet_ghi_dung_ly_do_CELL_ID_PHANG(self):
        # V8 (09/2026) - ban CHI TIET song song voi ngoai_pham_vi (list[str]
        # cu, KHONG doi). HIEN TAI chi co 1 nhanh (cell_id phang) nen ly_do
        # LUON la LY_DO_CELL_ID_PHANG.
        raw = [
            make_huong(
                12,
                [
                    make_cell_dict(_DN.format(970110), "4G-SSN127M11-HNI", 1),
                    make_cell_dict("4G-PYN015M12-VPC", "4G-PYN015M12-VPC", 4),
                ],
            )
        ]
        chi_tiet: list[dict] = []

        NeighborCellFilter().filter_affected(raw, ngoai_pham_vi_chi_tiet=chi_tiet)

        assert chi_tiet == [{"cell_name": "4G-PYN015M12-VPC", "ly_do": LY_DO_CELL_ID_PHANG}]

    def test_chi_tiet_khong_trung_lap_khi_cell_o_nhieu_huong(self):
        # Dedup RIENG cho ban chi tiet - cung tinh huong voi
        # test_bo_dem_KHONG_trung_lap_khi_cell_o_nhieu_huong o tren.
        c = make_cell_dict("4G-B-VPC", "4G-B-VPC", 1)
        raw = [make_huong(11, [c]), make_huong(12, [dict(c)])]
        chi_tiet: list[dict] = []

        NeighborCellFilter().filter_affected(raw, ngoai_pham_vi_chi_tiet=chi_tiet)

        assert chi_tiet == [{"cell_name": "4G-B-VPC", "ly_do": LY_DO_CELL_ID_PHANG}]

    def test_khong_truyen_chi_tiet_van_chay_binh_thuong(self):
        # out-param moi CUNG la TUY CHON, giong ngoai_pham_vi cu - caller
        # khong quan tam ban chi tiet thi khong truyen gi, hanh vi y nguyen.
        raw = [make_huong(11, [make_cell_dict("4G-B-VPC", "4G-B-VPC", 1)])]
        ket_qua = NeighborCellFilter().filter_affected(raw)
        assert ket_qua == []


class TestLogNgoaiPhamViChiMotLan:
    """V-item7 (09/2026) - BUG THAT: filter_for_cr() tu goi lai
    filter_affected() ben trong nen khi caller (application/
    trigger_cr_use_case.py::_prepare_plan()) goi CA HAI ham cho 1 request,
    moi cell ngoai pham vi bi logger.warning() 2 LAN. Sua bang tham so
    affected_cells (filter_for_cr() tai su dung ket qua da co thay vi tu
    tinh lai) - test o day khoa lai HANH VI DUNG, KHONG phai chi tiet ky
    thuat cua cach sua."""

    def test_goi_ca_filter_affected_va_filter_for_cr_chi_log_1_lan(self, caplog):
        # Mo phong DUNG pattern cua _prepare_plan(): goi filter_affected()
        # TRUOC (Nhanh A cho preview), roi filter_for_cr() VOI affected_cells
        # da tinh (Nhanh B) - day CHINH LA tinh huong tung bi log 2 lan.
        raw = [
            make_huong(
                12,
                [
                    make_cell_dict(_DN.format(970110), "4G-SSN127M11-HNI", 1),
                    make_cell_dict("4G-PYN015M12-VPC", "4G-PYN015M12-VPC", 4),
                ],
            )
        ]

        with caplog.at_level(logging.WARNING):
            affected = NeighborCellFilter().filter_affected(raw)
            NeighborCellFilter().filter_for_cr(raw, affected_cells=affected)

        so_dong = sum(1 for r in caplog.records if "ngoai pham vi" in r.message.lower())
        assert so_dong == 1, (
            f"phai dung 1 dong canh bao cho 1 request, thuc te {so_dong}: "
            f"{[r.message for r in caplog.records]}"
        )

    def test_goi_filter_for_cr_doc_lap_van_log_dung_1_lan(self, caplog):
        # filter_for_cr() goi DOC LAP (khong truyen affected_cells - cach da
        # co tu truoc, cac test khac trong file nay van dung) van phai log
        # DUNG 1 lan - KHONG duoc mat canh bao vi qua sua loi tren.
        raw = [
            make_huong(
                12,
                [
                    make_cell_dict(_DN.format(970110), "4G-SSN127M11-HNI", 1),
                    make_cell_dict("4G-PYN015M12-VPC", "4G-PYN015M12-VPC", 4),
                ],
            )
        ]

        with caplog.at_level(logging.WARNING):
            NeighborCellFilter().filter_for_cr(raw)

        so_dong = sum(1 for r in caplog.records if "ngoai pham vi" in r.message.lower())
        assert so_dong == 1
