"""
Unit test cho adapters/netact/import_ho_neighbor.py::doc_csv() - CHI test
logic doc/loc CSV (khong cham DB - xoa_va_nap() can DATABASE_URL that, KHONG
test o day). Tu: quyet dinh 06-08/10/2026 (BO CDS, thay bang HO + Delaunay) +
quyet dinh 08/10/2026 lan 4 (NAP DAY DU - bo cat top-N, them loc mnc_id).
"""

import pytest

from adapters.netact.import_ho_neighbor import COT_BAT_BUOC, MNC_HOP_LE, doc_csv

_HEADER = ";".join([
    "PERIOD_START_TIME", "Source PLMN name", "Source MRBTS name", "Source LNBTS name",
    "Source LNCEL name", "Target PLMN name", "Target MRBTS name", "Target LNBTS name",
    "Target LNBTS ID", "Target LNCEL name", "Target LNCEL TAC", "Target LCR ID",
    "mcc_id", "mnc_id", "eci_id", "DN", "Adj Inter eNB HO Prep SR",
    "Inter eNB HO prep att neigh", "Adj Inter eNB HO SR",
    "Number of Inter eNB Handover attempts per neighbor cell relationship",
    "Inter eNB NB HO fail ratio",
    "Number of inter-frequency load balancing handover attempts per neighbor cell relationship",
])

_SRC_ENB = 117903


def _dong(src_lncel: str, eci: str, att: str, sr: str, src_lncel_name: str = "4G-BDH288M11-HNI", mnc: str = "02") -> str:
    dn = f"PLMN-PLMN/MRBTS-{_SRC_ENB}/LNBTS-{_SRC_ENB}/LNCEL-{src_lncel}/MCC-452/MNC-02/ECI-{eci}"
    # 22 cot, CHI dien cac cot script dung toi - con lai de rong (hop le, PHAN
    # BIET voi "thieu cot" - do la thieu CA MOT TEN COT trong header).
    return ";".join([
        "09.28.2026", "PLMN-PLMN", f"T{_SRC_ENB}", f"T{_SRC_ENB}", src_lncel_name,
        "", "", "", "", "", "", "", "452", mnc, eci, dn, "", att, sr, "", "", "",
    ])


def _ghi_file(tmp_path, dong_list: list[str]):
    path = tmp_path / "ho_test.csv"
    path.write_text(_HEADER + "\n" + "\n".join(dong_list) + "\n", encoding="utf-8")
    return path


def test_doc_csv_giu_dong_hop_le_bo_intra_attempt0_mbf(tmp_path):
    # Dong HOP LE: nguon LNCEL-11 (2 chu so), dich enb=110021 lcr=12.
    eci_hop_le = 110021 * 256 + 12
    dong_hop_le = _dong("11", str(eci_hop_le), "100", "99.5")

    # Dong INTRA-eNB: dich CUNG enb voi nguon (117903).
    eci_intra = _SRC_ENB * 256 + 13
    dong_intra = _dong("11", str(eci_intra), "50", "99.0")

    # Dong attempt=0: dich khac nhung attempt rong.
    eci_att0 = 110022 * 256 + 11
    dong_att0 = _dong("11", str(eci_att0), "0", "99.0")

    # Dong nguon MBF_ (LNCEL 3 chu so "111") - %10 se ra sector SAI, PHAI bo.
    eci_mbf = 110023 * 256 + 11
    dong_mbf = _dong("111", str(eci_mbf), "80", "99.0", src_lncel_name="MBF_H2_TEST_1_M4BA")

    path = _ghi_file(tmp_path, [dong_hop_le, dong_intra, dong_att0, dong_mbf])

    ngay_du_lieu, rows = doc_csv(path)

    assert str(ngay_du_lieu) == "2026-09-28"
    assert len(rows) == 1
    r = rows[0]
    assert r["source_enb"] == _SRC_ENB
    assert r["source_sector"] == 1  # LNCEL-11 % 10 = 1
    assert r["target_enb"] == 110021
    assert r["target_lcr"] == 12
    assert r["ho_attempt"] == 100
    assert r["ho_sr"] == 99.5


def test_doc_csv_source_enb_la_lnbts_khong_phai_mrbts(tmp_path):
    # SUA 10/10/2026 (yeu cau truc tiep user, CHUNG MINH BANG TOAN HOC + DU
    # LIEU THAT): source_enb PHAI lay tu LNBTS trong DN, KHONG PHAI MRBTS -
    # vi eNB ID giai ma tu ECI (target_enb cua chinh file nay) CHINH LA
    # LNBTS (eNB ID ECI toi da 20 bit = 1.048.575, MRBTS co the vuot qua -
    # du lieu that tram 111629: MRBTS=1101629 > 1.048.575, LNBTS=111629 hop
    # le - xem domain/services/dist_name.py::LNBTS_LNCEL_RE). Mo phong dung
    # cap nay: MRBTS=1101629, LNBTS=111629.
    # Tu build DN rieng (khong dung _dong(), vi _dong() luon gan LNBTS=_SRC_ENB=
    # 117903) - dung thang DN that cua tram 111629 (LNBTS khac MRBTS).
    eci = 110021 * 256 + 12
    dn = f"PLMN-PLMN/MRBTS-1101629/LNBTS-111629/LNCEL-11/MCC-452/MNC-02/ECI-{eci}"
    dong = ";".join([
        "09.28.2026", "PLMN-PLMN", "T111629", "T111629", "4G-CGY327M11-HNI",
        "", "", "", "", "", "", "", "452", "02", str(eci), dn, "", "100", "99.5", "", "", "",
    ])
    path = _ghi_file(tmp_path, [dong])

    _, rows = doc_csv(path)

    assert len(rows) == 1
    assert rows[0]["source_enb"] == 111629  # LNBTS - KHONG duoc la 1101629 (MRBTS)


def test_doc_csv_bo_dong_mnc_khac_02(tmp_path):
    # THEM 08/10/2026 lan 4 (yeu cau truc tiep user) - dong mnc_id KHAC
    # MNC_HOP_LE ("02") PHAI bi loai, du cac truong khac deu hop le.
    assert MNC_HOP_LE == "02"
    eci_hop_le = 110021 * 256 + 12
    dong_hop_le = _dong("11", str(eci_hop_le), "100", "99.5", mnc="02")

    eci_mnc_khac = 110024 * 256 + 11
    dong_mnc_khac = _dong("11", str(eci_mnc_khac), "100", "99.0", mnc="01")

    path = _ghi_file(tmp_path, [dong_hop_le, dong_mnc_khac])

    _, rows = doc_csv(path)

    assert len(rows) == 1
    assert rows[0]["target_enb"] == 110021


def test_doc_csv_gop_nhieu_dong_cung_nguon_dich_cong_don_attempt(tmp_path):
    eci = 110021 * 256 + 12
    # 2 dong CUNG (nguon, dich) - attempt phai CONG DON, SR tinh trung binh
    # CO TRONG SO theo attempt (dung pattern da dung o scripts/spike_ho_neighbor.py).
    d1 = _dong("11", str(eci), "100", "100.0")
    d2 = _dong("11", str(eci), "50", "97.0")
    path = _ghi_file(tmp_path, [d1, d2])

    _, rows = doc_csv(path)

    assert len(rows) == 1
    assert rows[0]["ho_attempt"] == 150
    assert rows[0]["ho_sr"] == pytest.approx((100 * 100.0 + 50 * 97.0) / 150)


def test_doc_csv_gop_theo_sector_khi_2_cell_nguon_khac_ten_cung_dich(tmp_path):
    # SUA 08/10/2026 lan 4 (bug THAT phat hien khi chay day du tren file NA09
    # - UniqueViolationError khi COPY): 2 cell nguon VAT LY khac nhau (ten
    # khac nhau) nhung CUNG sector (LNCEL-11 va LNCEL-21 deu %10=1) VA cung
    # handover toi 1 dich - PHAI gop thanh 1 DONG DUY NHAT (attempt cong don),
    # khong duoc tao 2 dong trung khoa (source_enb, source_sector, target_enb,
    # target_lcr) - khoa UNIQUE cua bang KHONG co source_lncel_name.
    eci = 110021 * 256 + 12
    d1 = _dong("11", str(eci), "100", "99.0", src_lncel_name="4G-BDH288M11-HNI")  # sector 1, attempt lon hon
    d2 = _dong("21", str(eci), "30", "98.0", src_lncel_name="4G-BDH288M21-HNI")  # sector 1 (21%10=1), attempt nho hon
    path = _ghi_file(tmp_path, [d1, d2])

    _, rows = doc_csv(path)

    assert len(rows) == 1  # gop thanh 1 dong duy nhat, khong trung khoa unique
    r = rows[0]
    assert r["source_sector"] == 1
    assert r["ho_attempt"] == 130  # cong don 100 + 30
    assert r["ho_sr"] == pytest.approx((100 * 99.0 + 30 * 98.0) / 130)
    # Ten dai dien = cell dong gop NHIEU ho_attempt nhat (100 > 30).
    assert r["source_lncel_name"] == "4G-BDH288M11-HNI"


def test_doc_csv_khong_cat_top_n_giu_toan_bo_cell_dich(tmp_path):
    # SUA 08/10/2026 lan 4 (yeu cau truc tiep user, "NAP DAY DU HO VAO DB"):
    # BO han cat top-20/nguon - 1 nguon co 25 cell dich PHAN BIET (vuot ca
    # TOP_N_MOI_NGUON=20 cua ban truoc) PHAI giu DU CA 25, khong bi cat.
    dong_list = []
    for i in range(25):
        eci = (120000 + i) * 256 + 11
        dong_list.append(_dong("11", str(eci), str(100 - i), "99.0"))  # attempt giam dan 100..76
    path = _ghi_file(tmp_path, dong_list)

    _, rows = doc_csv(path)

    assert len(rows) == 25  # KHONG con bi cat ve 20 nhu ban truoc
    assert min(r["ho_attempt"] for r in rows) == 76
    assert max(r["ho_attempt"] for r in rows) == 100


def test_doc_csv_thieu_cot_bat_buoc_dung_sys_exit(tmp_path):
    header_thieu = _HEADER.replace("eci_id;", "")  # xoa mot cot bat buoc
    path = tmp_path / "ho_thieu_cot.csv"
    path.write_text(header_thieu + "\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        doc_csv(path)


def test_cot_bat_buoc_khop_dac_ta():
    assert COT_BAT_BUOC == [
        "PERIOD_START_TIME", "Source LNBTS name", "Source LNCEL name",
        "eci_id", "mnc_id", "DN", "Inter eNB HO prep att neigh", "Adj Inter eNB HO SR",
    ]
