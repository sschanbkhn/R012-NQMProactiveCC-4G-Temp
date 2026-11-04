"""
Unit test cho CellInforRepo.get_dn_map_theo_enb_lcr() - MOCK asyncpg connection
(.fetch()), KHONG can DB that. Tu: SUA 10/10/2026 (yeu cau truc tiep user) -
tra cuu PHAI theo LNBTS (KHONG phai MRBTS) - xem domain/services/dist_name.py::
LNBTS_LNCEL_RE va docs/BUSINESS_RULES.md muc "SUA 10/10/2026".
"""

from unittest.mock import AsyncMock

from adapters.postgres.cell_infor_repo import CellInforRepo


def _fake_conn(rows: list[dict]):
    conn = AsyncMock()
    conn.fetch.return_value = rows
    return conn


async def test_tram_mrbts_khac_lnbts_ghep_dung_theo_lnbts():
    # Du lieu THAT tram 111629 (4G-CGY327M-HNI, da xac nhan 10/10/2026):
    # MRBTS=1101629, LNBTS=111629 - PHAI tra ve duoc theo khoa (LNBTS, lcr),
    # KHONG PHAI (MRBTS, lcr).
    rows = [
        {"dn_lncel": "PLMN-PLMN/MRBTS-1101629/LNBTS-111629/LNCEL-11", "cell_name": "4G-CGY327M11-HNI"},
        {"dn_lncel": "PLMN-PLMN/MRBTS-1101629/LNBTS-111629/LNCEL-51", "cell_name": "4G-CGY327M51-HNI"},
    ]
    repo = CellInforRepo(_fake_conn(rows))

    dn_map = await repo.get_dn_map_theo_enb_lcr()

    assert dn_map[(111629, 11)] == {
        "dn_lncel": "PLMN-PLMN/MRBTS-1101629/LNBTS-111629/LNCEL-11",
        "cell_name": "4G-CGY327M11-HNI",
    }
    assert dn_map[(111629, 51)]["cell_name"] == "4G-CGY327M51-HNI"
    # KHONG duoc co khoa theo MRBTS (1101629) - se SAI vi target_enb cua
    # ho_neighbor (giai ma tu ECI) la LNBTS, khong bao gio ra 1101629 (vuot
    # qua 20-bit eNB ID cua ECI, xem dist_name.py).
    assert (1101629, 11) not in dn_map


async def test_tram_mrbts_bang_lnbts_van_ghep_dung_nhu_cu():
    # Truong hop PHO BIEN (97,33% - MRBTS == LNBTS) - khong duoc regression.
    rows = [{"dn_lncel": "PLMN-PLMN/MRBTS-117903/LNBTS-117903/LNCEL-11", "cell_name": "4G-BDH288M11-HNI"}]
    repo = CellInforRepo(_fake_conn(rows))

    dn_map = await repo.get_dn_map_theo_enb_lcr()

    assert dn_map[(117903, 11)]["cell_name"] == "4G-BDH288M11-HNI"


async def test_dn_lncel_khong_dung_mau_bi_bo_qua_khong_raise():
    rows = [{"dn_lncel": "DANG_LA_KHONG_DUNG_MAU", "cell_name": "X"}]
    repo = CellInforRepo(_fake_conn(rows))

    dn_map = await repo.get_dn_map_theo_enb_lcr()

    assert dn_map == {}
