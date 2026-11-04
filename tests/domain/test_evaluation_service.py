"""
Unit test cho EvaluationService — so sanh before/after, tra PASS|FAIL|INSUFFICIENT_DATA.
Tu: BUSINESS_RULES.md Section 8; TASK_LIST.md B3.6
"""

import pytest

from domain.services.evaluation_service import (
    LY_DO_DUOI_MUC_TOI_THIEU,
    LY_DO_TUT_QUA_NHIEU,
    EvaluationService,
)


def test_du_ngay_after_ge_before_tra_pass():
    # BUSINESS_RULES.md SS8.3 dong 399/402 (sua 13072026, doi dau 03/10/2026) -
    # PASS neu (avg_before - avg_after) <= 0.1 (co dung sai, khong phai bat
    # dang thuc tuyet doi). Delta o day la -1.0 (CAI THIEN, am), nam sau trong
    # vung PASS - assertion KHONG doi qua lan doi dau (chi doi CACH DIEN GIAI).
    before = [1.0, 2.0, 3.0, 4.0, 5.0]
    after = [2.0, 3.0, 4.0, 5.0, 6.0]
    result = EvaluationService().evaluate(before, after)
    assert result.result == "PASS"


def test_du_ngay_after_lt_before_tra_fail():
    # BUSINESS_RULES.md SS8.3 dong 399/402 (sua 13072026, doi dau 03/10/2026) -
    # FAIL neu (avg_before - avg_after) > 0.1. Delta o day la +4.0 (TUT), vuot
    # xa nguong dung sai 0.1 nen van FAIL - assertion KHONG doi qua lan doi dau.
    before = [5.0, 5.0, 5.0, 5.0, 5.0]
    after = [1.0, 1.0, 1.0, 1.0, 1.0]
    result = EvaluationService().evaluate(before, after)
    assert result.result == "FAIL"


def test_before_thieu_ngay_tra_insufficient_data():
    # BUSINESS_RULES.md SS8.2 dong 371-374 - before < 5 ngay
    before = [1.0, 2.0, 3.0, 4.0]  # 4 ngay < 5
    after = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]  # 7 ngay, du
    result = EvaluationService().evaluate(before, after)
    assert result.result == "INSUFFICIENT_DATA"


def test_after_thieu_ngay_tra_insufficient_data():
    # Nguong ap dung doc lap cho ca 2 ben (da chot voi user)
    before = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]  # 7 ngay, du
    after = [1.0, 2.0, 3.0, 4.0]  # 4 ngay < 5
    result = EvaluationService().evaluate(before, after)
    assert result.result == "INSUFFICIENT_DATA"


def test_avg_tinh_dung_theo_so_ngay_thuc_te_khong_chia_co_dinh_7():
    # BUSINESS_RULES.md SS8.2 dong 363-369 - avg = sum/so_ngay_thuc_te, du roi vao
    # INSUFFICIENT_DATA nhung avg van phai tinh dung truoc khi check nguong
    before = [3.0, 6.0, 9.0]  # 3 phan tu -> avg = 18/3 = 6.0, KHONG phai 18/7
    after = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    result = EvaluationService().evaluate(before, after)
    assert result.avg_before == 6.0
    assert result.result == "INSUFFICIENT_DATA"  # 3 ngay < 5, van insufficient


def test_threshold_tuy_chinh_khong_doi_default_cu():
    # Them (yeu cau truc tiep user, XuatPhieuUseCase KHOI 3a/5 can dung sai
    # 0.2 rieng, KHAC 0.1 mac dinh cua QoE/QoS PASS/FAIL cap session) - xac
    # nhan tham so threshold hoat dong dung VA default KHONG doi (goi khong
    # truyen threshold van la 0.1 nhu 4 test tren, KHONG regression).
    #
    # So lieu CO Y giu avg_after=3.35 >= MUC_TOI_THIEU=3.0 (qua duoc san chat
    # luong tuyet doi) de test nay CHI kiem tra rieng tieu chi threshold/delta,
    # khong lan sang tieu chi san.
    before = [3.5, 3.5, 3.5, 3.5, 3.5]
    after = [3.35, 3.35, 3.35, 3.35, 3.35]  # delta = before-after = +0.15 (TUT)

    # Voi default (0.1): 0.15 > 0.1 -> FAIL
    result_default = EvaluationService().evaluate(before, after)
    assert result_default.result == "FAIL"

    # Voi threshold=0.2 (dung sai rong hon): 0.15 KHONG > 0.2 -> PASS
    result_custom = EvaluationService().evaluate(before, after, threshold=0.2)
    assert result_custom.result == "PASS"


# === LUAT 04092026: 2 DIEU KIEN DOC LAP ===
# avg_after < MUC_TOI_THIEU (3.0) -> FAIL, KHONG lien quan delta
# tut qua nguong dung sai          -> FAIL
# con lai                          -> PASS
# Da BO han ve "tut nhieu nhung van tot thi cuu" (16082026 - 04092026).


def test_tut_it_NHUNG_duoi_muc_toi_thieu_van_FAIL():
    # DOI VERDICT 04092026 (truoc: PASS). Ten cu
    # test_tut_it_du_chat_luong_kem_van_pass - chinh cai ten do gio la SAI LUAT.
    #
    # Luat cu: nhanh "delta trong dung sai" tra PASS NGAY, khong xet chat luong
    # -> cell dang o 2.0 diem ma khong tut them thi coi nhu dat.
    # Luat moi: 2.0 < 3.0 -> FAIL bat ke delta. Day CHINH LA y dinh cua thay
    # doi: cell dang kem thi phai co nguoi di xem, du no da kem tu truoc CR.
    #
    # LUU Y FLOAT (that, da do): 2.1 - 2.0 = 0.10000000000000009 chu khong
    # phai 0.1 chan. Giu threshold=0.5 de delta chac chan nam trong dung sai,
    # ket qua CHI co the den tu ve muc toi thieu.
    before = [2.1] * 5
    after = [2.0] * 5
    result = EvaluationService().evaluate(before, after, threshold=0.5)
    assert result.result == "FAIL"
    assert result.ly_do_khong_dat == LY_DO_DUOI_MUC_TOI_THIEU
    assert result.so_ngay_dat_sau == 0


def test_tut_it_VA_tren_muc_toi_thieu_thi_PASS():
    # Doi xung voi test tren - CHI khac avg_after nam tren san. Chung minh ve
    # muc toi thieu la thu DUY NHAT lam test tren FAIL.
    before = [3.6] * 5
    after = [3.5] * 5  # delta +0.1, avg_after 3.5 >= 3.0
    result = EvaluationService().evaluate(before, after, threshold=0.5)
    assert result.result == "PASS"
    assert result.ly_do_khong_dat is None


def test_tut_qua_nguong_du_chat_luong_con_TOT_van_FAIL():
    # DOI VERDICT 04092026 (truoc: PASS). Ten cu
    # test_tut_nhieu_nhung_van_tot_tra_pass - test dung VE DA BI BO.
    #
    # delta = 5.0 - 4.5 = 0.5, qua dung sai 0.1 cap session. avg_after 4.5
    # RAT TOT (>= 3.0) nhung KHONG con cuu duoc nua - do la thay doi chinh cua
    # luat moi: tut 0.5 diem tu 5.0 xuong 4.5 da la dau hieu CR gay anh huong.
    before = [5.0] * 5
    after = [4.5] * 5
    result = EvaluationService().evaluate(before, after)
    assert result.result == "FAIL"
    assert result.ly_do_khong_dat == LY_DO_TUT_QUA_NHIEU
    assert result.avg_after == 4.5


def test_tut_qua_nguong_thi_FAIL_voi_ly_do_TUT_QUA_NHIEU():
    # Ten cu test_tut_nhieu_va_chat_luong_kem_tra_fail. Ket qua KHONG doi (van
    # FAIL) - chi ly_do doi tu TUT_VA_CHAT_LUONG_KEM sang TUT_QUA_NHIEU, vi 2
    # dieu kien gio doc lap nen phai noi RO vi pham cai nao.
    # avg_after 3.9 >= 3.0 (qua duoc san) nen FAIL chi co the den tu delta.
    before = [4.4] * 5
    after = [3.9] * 5
    result = EvaluationService().evaluate(before, after)
    assert result.result == "FAIL"
    assert result.ly_do_khong_dat == LY_DO_TUT_QUA_NHIEU


def test_bien_avg_after_DUNG_BANG_muc_toi_thieu_tra_PASS():
    # BIEN: so sanh la < (KHONG phai <=), nen avg_after DUNG 3.0 phai PASS.
    # Ten cu test_avg_after_dung_bang_muc_tot_tra_pass (bien cua ve 4.0 cu).
    # threshold=0.5 CO Y (khong dung default 0.1): 3.1 - 3.0 =
    # 0.10000000000000009 trong so hoc dau phay dong, tuc LON HON 0.1 that -
    # bay float da ghi o test_tut_it_... ben tren. Dung dung sai rong hon de
    # ket qua CHI phu thuoc ve muc toi thieu, dung y dinh cua test nay.
    before = [3.1] * 5
    after = [3.0] * 5
    result = EvaluationService().evaluate(before, after, threshold=0.5)
    assert result.result == "PASS"
    assert result.ly_do_khong_dat is None
    assert result.avg_after == 3.0


def test_bien_avg_after_DUOI_muc_toi_thieu_mot_chut_tra_FAIL():
    # Doi xung voi test tren: 2.99 < 3.0 -> FAIL, du delta chi +0.10.
    before = [3.09] * 5
    after = [2.99] * 5
    result = EvaluationService().evaluate(before, after, threshold=0.5)  # xem test tren
    assert result.result == "FAIL"
    assert result.ly_do_khong_dat == LY_DO_DUOI_MUC_TOI_THIEU


def test_bien_tut_DUNG_BANG_nguong_tra_PASS():
    # BIEN cua dieu kien delta: "tut qua 0.5 la khong dat" -> tut DUNG 0.5 van
    # DAT. delta = 0.5, so sanh la > threshold (KHONG phai >=).
    before = [5.0] * 5
    after = [4.5] * 5
    result = EvaluationService().evaluate(before, after, threshold=0.5)
    assert result.result == "PASS"
    assert result.ly_do_khong_dat is None


def test_bien_tut_QUA_nguong_mot_chut_tra_FAIL():
    before = [5.0] * 5
    after = [4.49] * 5  # delta +0.51
    result = EvaluationService().evaluate(before, after, threshold=0.5)
    assert result.result == "FAIL"
    assert result.ly_do_khong_dat == LY_DO_TUT_QUA_NHIEU


def test_2_dieu_kien_DOC_LAP_khong_cai_nao_cuu_cai_nao():
    # Chot lai tinh DOC LAP: vi pham 1 trong 2 la du de FAIL.
    ev = EvaluationService()
    # Chi vi pham san chat luong (delta = 0, khong tut ti nao)
    assert ev.evaluate([2.0] * 5, [2.0] * 5).result == "FAIL"
    # Chi vi pham muc tut (chat luong con rat tot)
    assert ev.evaluate([5.0] * 5, [4.0] * 5, threshold=0.5).result == "FAIL"
    # Khong vi pham cai nao
    assert ev.evaluate([4.0] * 5, [3.6] * 5, threshold=0.5).result == "PASS"


def test_thieu_ngay_van_insufficient_data_du_chat_luong_tot():
    # MIN_DAYS_REQUIRED van duoc xet TRUOC ca 2 dieu kien.
    before = [5.0] * 5
    after = [5.0] * 4  # 4 ngay < MIN_DAYS_REQUIRED=5
    result = EvaluationService().evaluate(before, after)
    assert result.result == "INSUFFICIENT_DATA"
    assert result.ly_do_khong_dat is None


def test_truong_tham_khao_lo_ra_ngay_mat_dich_vu_bi_trung_binh_che():
    # SUA SO LIEU (khong noi long assert): bo so cu la before=[5.0]x7 -> delta
    # (before-after) +0.571 (TUT) nen luat moi tra FAIL, lam test khong con CO
    # LAP duoc dieu no muon kiem. Ha before xuong 4.4 de delta ~ -0.03 (CAI
    # THIEN nhe, khong vi pham gi), GIU NGUYEN ngay diem 1.0 - do moi la thu
    # test nay noi ve.
    before = [4.4] * 7
    after = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 1.0]  # avg 4.43, co 1 ngay diem 1
    result = EvaluationService().evaluate(before_values=before, after_values=after)
    assert result.result == "PASS"
    assert result.diem_thap_nhat_sau == 1.0  # <- ngay bi trung binh che
    assert result.so_ngay_dat_sau == 6  # 6/7 ngay >= 3.0


def test_muc_toi_thieu_tuy_chinh_khong_doi_default():
    # Doi xung voi test_threshold_tuy_chinh_khong_doi_default_cu: tham so
    # muc_toi_thieu hoat dong VA default 3.0 khong doi.
    # Ten cu test_muc_tot_tuy_chinh_khong_doi_default.
    # threshold=0.5 CO Y - xem bay float o
    # test_bien_avg_after_DUNG_BANG_muc_toi_thieu_tra_PASS.
    before = [3.6] * 5
    after = [3.5] * 5  # avg_after 3.5

    ev = EvaluationService()
    assert ev.evaluate(before, after, threshold=0.5).result == "PASS"  # 3.5 >= 3.0 mac dinh
    # Nang san len 4.0 -> 3.5 khong con dat -> FAIL
    assert (
        ev.evaluate(before, after, threshold=0.5, muc_toi_thieu=4.0).result == "FAIL"
    )


# === 6 CA BIEN theo dac ta 04092026 (yeu cau truc tiep user) ===
# Dat rieng mot khoi, doc duoc nhu bang doi chieu voi dac ta.


@pytest.mark.parametrize(
    "before,after,mong_doi,ghi_chu",
    [
        # delta DUNG 0.50, avg_after 4.0 -> DAT (bien delta)
        (4.5, 4.0, "PASS", "tut dung 0.50, tren san"),
        # delta 0.51 -> KHONG DAT
        (4.5, 3.99, "FAIL", "tut 0.51, qua bien"),
        # delta 0.10, avg_after DUNG 3.0 -> DAT (bien san)
        (3.1, 3.0, "PASS", "tut it, TB sau dung bang san"),
        # delta 0.10, avg_after 2.99 -> KHONG DAT
        (3.09, 2.99, "FAIL", "tut it nhung duoi san"),
        # CA THAT 116311: delta 1.00, avg_after 3.83 -> KHONG DAT
        # (luat CU cung KHONG DAT nhung vi avg_after < 4.0; luat MOI vi tut qua 0.5)
        (4.83, 3.83, "FAIL", "ca that 116311 - tut 1.00"),
        # CA THAT 115560: delta 0.33, avg_after 2.00 -> KHONG DAT
        # (luat CU cung KHONG DAT; luat MOI vi duoi san 3.0)
        (2.33, 2.00, "FAIL", "ca that 115560 - duoi san"),
    ],
)
def test_6_ca_bien_theo_dac_ta_04092026(before, after, mong_doi, ghi_chu):
    # threshold=0.5 (cap CELL) - dac ta noi ve nguong 0.5.
    result = EvaluationService().evaluate([before] * 7, [after] * 7, threshold=0.5)
    assert result.result == mong_doi, (
        f"{ghi_chu}: {before} -> {after} (tut {before - after:.2f}, "
        f"TB sau {after}) mong doi {mong_doi} nhung ra {result.result}"
    )


def test_ca_that_116311_va_115560_KHAC_LY_DO_du_cung_FAIL():
    # 2 ca that deu FAIL o ca luat cu lan moi, NHUNG luat moi noi ro vi sao -
    # do la diem huu ich cho nguoi van hanh.
    ev = EvaluationService()
    r_116311 = ev.evaluate([4.83] * 7, [3.83] * 7, threshold=0.5)
    r_115560 = ev.evaluate([2.33] * 7, [2.00] * 7, threshold=0.5)

    assert r_116311.ly_do_khong_dat == LY_DO_TUT_QUA_NHIEU
    assert r_115560.ly_do_khong_dat == LY_DO_DUOI_MUC_TOI_THIEU


# === do_te_cua(): LUAT XEP HANG (sua 04092026) ===
# Truoc day do_te = (before - after) thuan, chi do MUC TUT. Tu khi co san 3.0,
# cell vi pham san MA KHONG TUT co do_te AM -> sort giam dan day no xuong CUOI
# va bi cat khi session co > 10 cell khong dat. Nguoc muc dich cua tran 10.


def _do_te(before: float, after: float) -> float:
    from domain.services.evaluation_service import do_te_cua

    return do_te_cua(EvaluationService().evaluate([before] * 7, [after] * 7, threshold=0.5))


@pytest.mark.parametrize(
    "before,after,mong_doi,ghi_chu",
    [
        (5.00, 4.20, 0.80, "tut 0.8, tren san -> lay muc tut"),
        (1.29, 1.86, 1.14, "CAI THIEN nhung duoi san -> lay muc thieu"),
        (4.83, 3.83, 1.00, "tut 1.0, tren san -> lay muc tut"),
    ],
)
def test_do_te_3_ca_theo_dac_ta(before, after, mong_doi, ghi_chu):
    assert _do_te(before, after) == pytest.approx(mong_doi, abs=0.005), ghi_chu


def test_do_te_lay_gia_tri_LON_HON_khi_vua_tut_vua_duoi_san():
    # 4.0 -> 2.0: muc_tut = 2.0, muc_thieu = 3.0 - 2.0 = 1.0 -> max = 2.0
    assert _do_te(4.0, 2.0) == pytest.approx(2.0)
    # 3.2 -> 2.0: muc_tut = 1.2, muc_thieu = 1.0 -> max = 1.2
    assert _do_te(3.2, 2.0) == pytest.approx(1.2)
    # 2.2 -> 2.0: muc_tut = 0.2, muc_thieu = 1.0 -> max = 1.0 (ve san thang)
    assert _do_te(2.2, 2.0) == pytest.approx(1.0)


def test_do_te_KHONG_BAO_GIO_am():
    # Cell cai thien VA tren san -> ca 2 ve deu bi max(0, ...) chan.
    assert _do_te(4.0, 4.5) == 0.0
    # Cell cai thien nhung duoi san -> ve san van duong.
    assert _do_te(1.29, 1.86) > 0


def test_thu_tu_sap_xep_te_nhat_TRUOC():
    # Dung dac ta: 1.86 xep TRUOC 3.83, 3.83 truoc 4.20.
    ca = [("A_1.86", 1.29, 1.86), ("B_3.83", 4.83, 3.83), ("C_4.20", 5.00, 4.20)]
    sap = sorted(ca, key=lambda x: _do_te(x[1], x[2]), reverse=True)
    assert [t[0] for t in sap] == ["A_1.86", "B_3.83", "C_4.20"]


def test_4_cell_that_dang_CAI_THIEN_ma_van_kem_deu_co_do_te_DUONG():
    """4 ca THAT do duoc 04/09 - luat cu cho chung do_te AM nen bi xep cuoi.

    Day la dieu KIEN TIEN QUYET: do_te am thi khong bao gio canh tranh duoc
    suat trong tran 10."""
    for ten, b, a in (
        ("NTM404M41", 1.43, 1.57),
        ("NTM380M43", 1.29, 1.86),
        ("BTM128M41", 1.43, 2.00),
        ("TTN007M42", 2.33, 2.71),
    ):
        assert _do_te(b, a) > 0, f"{ten} phai co do_te DUONG (luat cu cho AM)"


def test_cell_duoi_san_SAU_khong_chac_xep_truoc_cell_tut_nhieu():
    """GIOI HAN DA BIET cua cong thuc - ghi lai de khong ai tuong da xong.

    Cell vi pham san co do_te = (3.0 - avg_after). Cell vi pham nguong tut co
    do_te > 0.5 (vi phai tut qua 0.5 moi FAIL). Nen cell nao duoi san CHUA TOI
    0.5 (tuc avg_after > 2.5) SE xep sau MOI cell vi pham nguong tut.

    Ca that: TTN007M42 o 2.71/5 (thieu 0.29) xep SAU mot cell tut 0.6 tu 5.0
    xuong 4.4 - du 2.71 kem hon 4.4 nhieu.

    CHAP NHAN vi: cell chi thieu 0.29 duoi san la truong hop bien, con cell tut
    0.6 la thay doi ro rang do CR. Neu sau nay thay lot ca dang nay thi phai
    doi cach xep hang (vd nhan trong so cho ve san), KHONG phai sua cong thuc
    do_te - do_te dang tra loi dung cau hoi "te nhat o muc nao"."""
    assert _do_te(2.33, 2.71) == pytest.approx(0.29, abs=0.005)  # thieu 0.29
    assert _do_te(5.0, 4.4) == pytest.approx(0.60, abs=0.005)  # tut 0.60
    assert _do_te(2.33, 2.71) < _do_te(5.0, 4.4)

    # 3/4 ca that CON LAI van xep truoc - vi chung kem sau hon han.
    for b, a in ((1.43, 1.57), (1.29, 1.86), (1.43, 2.00)):
        assert _do_te(b, a) > _do_te(5.0, 4.4)


def test_do_te_thieu_du_lieu_tra_0_khong_crash():
    from domain.services.evaluation_service import do_te_cua

    ket_qua = EvaluationService().evaluate([], [])
    assert do_te_cua(ket_qua) == 0.0
    assert do_te_cua(None) == 0.0


# === khoa_uu_tien_xuat_phieu(): KHOA XEP HANG 2 TANG (sua 09/2026) ===
#
# GHI CHU PHAM VI (khong bo qua, khong doan): dac ta yeu cau kiem bang 13 cell
# THAT cua session 4884, assert top 6 = [HKM022M43, HKM022M13, HKM018M12,
# HKM018M51, HKM070M53, HKM023W56]. Da tim toan bo repo (docs/, tests/,
# scripts/) va KHONG tim thay du lieu QoS/QoE truoc-sau cua 11/13 cell con
# lai (chi 2 cell HKM022M43/HKM022M13 duoc ghi lai VOI SO LIEU trong
# BUSINESS_RULES.md SS8.45 + docstring khoa_uu_tien_xuat_phieu()). Khong
# ket noi duoc DB production (10.155.43.204) tu moi truong dev (xem bao cao
# rieng gui nguoi dung) nen KHONG THE tu truy van bu. Test duoi day CHI dung
# 2 cell THAT da co so lieu - KHONG bia so cho 11 cell con lai. Neu co du
# lieu 13 cell that, them lai test full-list rieng, KHONG sua test nay.
from domain.services.evaluation_service import MUC_TOI_THIEU, do_te_cua, khoa_uu_tien_xuat_phieu  # noqa: E402


def test_khoa_uu_tien_ca_that_session_4884_HKM022M43_truoc_HKM022M13():
    """Ca THAT session 4884 (09/2026, BUSINESS_RULES.md SS8.45) - chinh ca
    dan chung khien phai doi luat xep hang.

    HKM022M43 (duoi san 3.0, nhom 0) PHAI xep TRUOC HKM022M13 (tren san,
    nhom 1) du do_te CU (1 con so max(muc_tut,muc_thieu)) xep NGUOC LAI
    (0.286 < 1.405 -> HKM022M43 tung bi coi la "it te hon", xep chot bang 13,
    bi cat khoi tran). khoa_uu_tien_xuat_phieu() la thu SUA dung dieu do."""
    svc = EvaluationService()
    # So lieu THAT, nguyen van tu BUSINESS_RULES.md SS8.45 / docstring
    # khoa_uu_tien_xuat_phieu(). threshold=0.5 GIONG _XUAT_PHIEU_QOS_
    # THRESHOLD_DELTA/_QOE_CELL_THRESHOLD_DELTA (application/xuat_phieu_use_case.py,
    # application/get_qoe_cells_use_case.py) - danh gia PASS/FAIL khong anh
    # huong khoa (khoa chi dung avg_before/avg_after), nhung dung threshold
    # that de MetricEvaluation phan anh dung nghiep vu.
    qos_43 = svc.evaluate([4.29] * 7, [4.00] * 7, threshold=0.5)
    qoe_43 = svc.evaluate([2.71] * 7, [2.83] * 7, threshold=0.5)
    qos_13 = svc.evaluate([4.57] * 7, [4.80] * 7, threshold=0.5)
    qoe_13 = svc.evaluate([4.57] * 7, [3.17] * 7, threshold=0.5)

    khoa_43 = khoa_uu_tien_xuat_phieu(qos_43, qoe_43)
    khoa_13 = khoa_uu_tien_xuat_phieu(qos_13, qoe_13)

    assert khoa_43[0] == 0, "HKM022M43: avg_after QoE 2.83 < MUC_TOI_THIEU 3.0 -> nhom 0"
    assert khoa_13[0] == 1, "HKM022M13: avg_after QoS 4.80 va QoE 3.17 deu >= 3.0 -> nhom 1"
    assert khoa_43 < khoa_13, "sort TANG DAN: nhom 0 (khoa_43) PHAI dung TRUOC nhom 1 (khoa_13)"

    # do_te CU (khong con quyet dinh thu tu, nhung van duoc bao cao - xem C3)
    # xep NGUOC LAI - ghi lai bang chung cho chinh cai bug da sua, tranh ai
    # sau nay tuong khoa moi va do_te cu luon dong thuan.
    do_te_43 = max(do_te_cua(qos_43), do_te_cua(qoe_43))
    do_te_13 = max(do_te_cua(qos_13), do_te_cua(qoe_13))
    assert do_te_43 < do_te_13, "do_te CU xep HKM022M43 'it te hon' HKM022M13 - dung la bug da sua"
    assert MUC_TOI_THIEU == 3.0


# === khoa_uu_tien_xuat_phieu(): 13 CELL THAT session 4884 (them 09/2026) ===
#
# NGUON: query DB THAT session 4884 (tram 110570, CR chay 04/09/2026), 13 cell
# KHONG DAT. Diem la TRUNG BINH cua so before/after doc tu qos_snapshot/
# qoe_snapshot (KHONG phai gia bia). Truoc ban sua nay chi co 2/13 cell
# (HKM022M43/HKM022M13) duoc ghi lai VOI SO LIEU trong repo (xem test o tren)
# - 11 cell con lai + danh sach top-6 day du KHONG the tu suy ra hay bia them,
# nen phai cho du lieu THAT tu nguoi dung (da xac nhan qua doi thoai, KHONG
# phai tu doan).
_CA_THAT_SESSION_4884 = {
    # ten cell: (qos_before, qos_after, qoe_before, qoe_after)
    "HKM018M12": (4.857, 5.000, 4.143, 3.000),
    "HKM018M51": (4.714, 3.600, 3.714, 4.333),
    "HKM022M13": (4.571, 4.800, 4.571, 3.167),
    "HKM022M43": (4.286, 4.000, 2.714, 2.833),
    "HKM023M11": (4.857, 5.000, 4.857, 4.167),
    "HKM023M12": (4.286, 3.600, 4.286, 4.167),
    "HKM023W53": (4.714, 4.200, 4.286, 4.333),
    "HKM023W56": (4.857, 4.000, 3.286, 4.833),
    "HKM070M13": (4.143, 4.400, 4.429, 3.833),
    "HKM070M51": (4.571, 4.800, 3.857, 3.167),
    "HKM070M52": (4.143, 3.600, 4.143, 4.000),
    "HKM070M53": (4.714, 4.800, 4.429, 3.500),
    "HKM164M13": (4.000, 3.200, 3.143, 4.500),
}


def _khoa_theo_cell_session_4884() -> dict:
    """{ten_cell: khoa} cho ca 13 cell - tai su dung trong nhieu test ben duoi.

    Diem TRUNG BINH cua so (khong phai diem tung ngay that) nen lap lai DUNG
    gia tri do o CA 7 "ngay" ([gia_tri] * 7) - EvaluationService.evaluate()
    tra avg = trung binh cac phan tu, [x]*7 cho avg = x dung boc MIN_DAYS_
    REQUIRED (5) de KHONG roi vao INSUFFICIENT_DATA."""
    svc = EvaluationService()
    ket_qua = {}
    for ten, (qos_b, qos_a, qoe_b, qoe_a) in _CA_THAT_SESSION_4884.items():
        qos_eval = svc.evaluate([qos_b] * 7, [qos_a] * 7, threshold=0.5)
        qoe_eval = svc.evaluate([qoe_b] * 7, [qoe_a] * 7, threshold=0.5)
        ket_qua[ten] = khoa_uu_tien_xuat_phieu(qos_eval, qoe_eval)
    return ket_qua


def test_khoa_13_cell_that_session_4884_sap_xep_dung_top_6():
    """Ca THAT session 4884 (tram 110570, CR 04/09/2026) - 13 cell KHONG DAT,
    sap xep bang khoa_uu_tien_xuat_phieu() (sort TANG DAN, khoa nho nhat =
    uu tien xuat truoc). Top 6 (vi du minh hoa mot tran co dinh - tu
    04/10/2026 tran THAT SU tinh theo SECTOR, xem XUAT_PHIEU_MAX_PER_SECTOR
    trong application/xuat_phieu_use_case.py, khong con la hang so phang
    nay nua, nhung thu tu sort cua khoa_uu_tien_xuat_phieu() KHONG doi)
    PHAI dung THU TU:
        1. HKM022M43  (duoi san QoE 2.833 -> nhom 0)
        2. HKM022M13  (nhom 1, do_giam 1.404 - lon nhat nhom 1)
        3. HKM018M12  (nhom 1, do_giam 1.143)
        4. HKM018M51  (nhom 1, do_giam 1.114)
        5. HKM070M53  (nhom 1, do_giam 0.929)
        6. HKM023W56  (nhom 1, do_giam 0.857)
    """
    khoa_theo_cell = _khoa_theo_cell_session_4884()
    xep_hang = sorted(khoa_theo_cell, key=lambda ten: khoa_theo_cell[ten])

    top_6 = xep_hang[:6]
    assert top_6 == [
        "HKM022M43",
        "HKM022M13",
        "HKM018M12",
        "HKM018M51",
        "HKM070M53",
        "HKM023W56",
    ]


def test_khoa_13_cell_HKM022M43_dau_bang_vi_duoi_san_du_do_giam_chi_0_286():
    """HKM022M43 dung DAU (nhom 0) du do_giam CHI 0.286 - nho nhat trong toan
    bo 13 cell - vi avg_after QoE 2.833 DUOI MUC_TOI_THIEU (3.0).

    LUAT CU (do_te_cua() = max(muc_tut, muc_thieu), 1 con so gop ca 2 tieu
    chi) cho cell nay do_te = max(muc_tut QoS 0.286, muc_thieu QoE 0.167) =
    0.286 - THAP NHAT trong 13 cell nen bi xep CHOT BANG (13/13) va BI CAT
    khoi tran 6. Day chinh la ca THAT khien phai doi sang khoa 2 tang."""
    khoa_theo_cell = _khoa_theo_cell_session_4884()
    xep_hang = sorted(khoa_theo_cell, key=lambda ten: khoa_theo_cell[ten])

    assert xep_hang[0] == "HKM022M43"

    khoa_43 = khoa_theo_cell["HKM022M43"]
    nhom, do_giam_am, avg_after_min = khoa_43
    assert nhom == 0, "avg_after QoE 2.833 < MUC_TOI_THIEU 3.0"
    # 0.29 (khong con 0.286): tu 18/10/2026 TB/lech lam tron 2 chu so.
    assert -do_giam_am == pytest.approx(0.29, abs=0.001), (
        "do_giam (QoS 4.286->4.000) CHI 0.286 - nho nhat trong ca 13 cell, "
        "nhung van dung DAU vi nhom 0 luon truoc nhom 1"
    )

    # Doi chung: MOI cell nhom 1 con lai deu co do_giam >= 0.286 (thuc te lon
    # hon nhieu) - chung minh do_giam KHONG PHAI ly do HKM022M43 dung dau.
    for ten, khoa in khoa_theo_cell.items():
        if ten == "HKM022M43":
            continue
        assert khoa[0] == 1
        assert -khoa[1] >= 0.286


def test_khoa_13_cell_pha_hoa_bang_avg_after_khi_do_giam_bang_nhau():
    """HKM070M51 va HKM023M11 CUNG do_giam 0.690 (lam tron 3 chu so) - khoa
    phai pha hoa bang avg_after_min: HKM070M51 (3.167) xep TRUOC HKM023M11
    (4.167) vi diem con lai THAP HON (cang thap cang uu tien)."""
    khoa_theo_cell = _khoa_theo_cell_session_4884()

    khoa_070M51 = khoa_theo_cell["HKM070M51"]
    khoa_023M11 = khoa_theo_cell["HKM023M11"]

    # Cung nhom, cung do_giam (lam tron 3 chu so) - chi khac o thanh phan thu 3.
    assert khoa_070M51[0] == khoa_023M11[0] == 1
    assert round(-khoa_070M51[1], 3) == round(-khoa_023M11[1], 3) == 0.690
    # 3.17/4.17 (khong con 3.167/4.167): tu 18/10/2026 TB lam tron 2 chu so.
    assert khoa_070M51[2] == pytest.approx(3.17, abs=0.001)
    assert khoa_023M11[2] == pytest.approx(4.17, abs=0.001)

    assert khoa_070M51 < khoa_023M11, "avg_after_min thap hon (3.167 < 4.167) -> xep TRUOC"


def test_khoa_13_cell_tran_6_cat_dung_7_cell_nhom_thang_do_giam():
    """Tran minh hoa = 6 (vi du co dinh de kiem thu tu sort - tu 04/10/2026
    tran THAT SU la XUAT_PHIEU_MAX_PER_SECTOR, tinh theo sector chu khong
    phang theo session, xem application/xuat_phieu_use_case.py) cat DUNG
    7/13 cell.

    HKM164M13 (nhom 1, do_giam 0.800 - LON HON han do_giam 0.286 cua
    HKM022M43) VAN bi cat, trong khi HKM022M43 (nhom 0) duoc xuat - chung
    minh KHOA XEP theo NHOM TRUOC, do_giam chi la tieu chi PHU trong CUNG 1
    nhom (khong phai "do_giam cang lon cang uu tien" xuyen nhom)."""
    khoa_theo_cell = _khoa_theo_cell_session_4884()
    xep_hang = sorted(khoa_theo_cell, key=lambda ten: khoa_theo_cell[ten])

    tran = 6
    duoc_xuat = xep_hang[:tran]
    bi_cat = xep_hang[tran:]

    assert len(bi_cat) == 7
    # SUA 18/10/2026 (lam tron 2 chu so): HKM023M12 QoS 4.286->3.600 tu do_giam
    # 0.686 thanh 4.29-3.60 = 0.69, BANG HKM070M51/HKM023M11 -> pha hoa bang
    # avg_after_min (3.60 < 4.17) nen 023M12 len truoc 023M11. Tap bi cat KHONG doi.
    assert bi_cat == [
        "HKM164M13",
        "HKM070M51",
        "HKM023M12",
        "HKM023M11",
        "HKM070M13",
        "HKM070M52",
        "HKM023W53",
    ]

    assert "HKM164M13" in bi_cat, "do_giam 0.800 (lon hon HKM022M43) nhung VAN bi cat"
    assert "HKM022M43" in duoc_xuat, "do_giam CHI 0.286 (nho nhat) nhung VAN duoc xuat vi o nhom 0"
    do_giam_164 = -khoa_theo_cell["HKM164M13"][1]
    do_giam_43 = -khoa_theo_cell["HKM022M43"][1]
    assert do_giam_164 > do_giam_43, "164M13 tut NHIEU HON 022M43 ve so tuyet doi, nhung van bi cat"


# === LAM TRON 2 CHU SO TRUOC KHI SO NGUONG (18/10/2026) ===
# Bug that TXN092M12 session 10707: 25/6 - 22/6 = 0.5000000000000004 trong
# float -> KHONG DAT + phieu 32084, trong khi lech dung 0.5 la DAT.


def test_lam_tron_lech_25_6_tru_22_6_la_0_50_thi_DAT():
    r = EvaluationService().evaluate([5, 5, 4, 4, 4, 3], [4, 4, 4, 4, 3, 3], threshold=0.5)

    assert (r.avg_before, r.avg_after, r.lech) == (4.17, 3.67, 0.5)
    assert r.result == "PASS"


def test_lam_tron_lech_0_51_thi_KHONG_DAT():
    r = EvaluationService().evaluate([4.0] * 6, [3.49] * 6, threshold=0.5)

    assert r.lech == 0.51
    assert r.result == "FAIL"
    assert r.ly_do_khong_dat == LY_DO_TUT_QUA_NHIEU


def test_lam_tron_TB_sau_2_995_thanh_3_00_thi_khong_duoi_san():
    # TB sau tho 2.996 -> lam tron 3.00 -> KHONG duoi san (so < 3.0 tren TB da tron).
    r = EvaluationService().evaluate([3.0] * 5, [2.98, 3.0, 3.0, 3.0, 3.0], threshold=0.5)

    assert r.avg_after == 3.0  # 2.996 -> 3.00
    assert r.result == "PASS"
