"""
EvaluationService.
Tu: BUSINESS_RULES.md Section 8 (Danh gia sau CR); TASK_LIST.md B3.6

SUA 03/10/2026 (yeu cau truc tiep user - DOI CHIEU delta): delta gio la
"avg_before - avg_after" (DUONG = TUT, AM = cai thien) - TRUOC DAY la
"avg_after - avg_before" (AM = tut). Ly do doi: moi noi khac trong he thong
(do_te_cua() o duoi, FE, bao cao) deu da quen doc "chenh lech truoc-sau"
theo chieu DUONG = tut (vd "lech 0.5 diem"), delta kieu cu bat FE/nguoi doc
phai tu doi dau ("-0.5 nghia la tut 0.5") - day la dung cho de hieu nham
nhat, tung phai dan giai bang comment "CAN THAN DAU" o moi noi dung no. Doi
chieu + doi dau CA 3 nguong (PASS_THRESHOLD_DELTA, _XUAT_PHIEU_QOS_THRESHOLD_DELTA,
_QOE_CELL_THRESHOLD_DELTA - 2 cai sau o application/) thanh SO DUONG, phep
so sanh tu "delta < threshold -> FAIL" doi thanh "delta > threshold -> FAIL"
(logic nghiep vu KHONG doi mot ty nao, chi la doi he quy chieu dau).

SUA (13072026, xac nhan voi user - chot cong thuc PASS/FAIL co dung sai): thay
vi so sanh tuyet doi avg_after >= avg_before (khong dung sai, moi lan giam dau
tren 0.0 la FAIL - de bi false alarm tu nhieu do luong tu nhien giua cac ngay),
gio dung PASS_THRESHOLD_DELTA (dung sai, xem SUA 03/10/2026 o tren cho dau
hien tai). Da cap nhat BUSINESS_RULES.md SS8.3 cung luc.

SUA (yeu cau truc tiep user, doi tieu chi QoS dat/khong dat cho XuatPhieuUseCase
KHOI 3a/5) - them THAM SO threshold cho evaluate(): XuatPhieuUseCase can dung
sai KHAC (0.2, "chenh lech TB truoc-sau <= 0.2 -> DAT") voi QoE/QoS PASS/FAIL
cap SESSION (BUSINESS_RULES.md SS8.3, dung sai 0.1) - 2 tieu chi DOC LAP nhau,
KHONG duoc trung 1 hang so. Default = PASS_THRESHOLD_DELTA (-0.1) GIU NGUYEN
100% hanh vi EvaluateCrUseCase (khong truyen threshold moi, khong regression).

SUA (16082026, yeu cau truc tiep user) - them VE avg_after >= MUC_TOT (4.0):
    delta >= threshold                     -> PASS  (nhu cu)
    delta <  threshold va avg_after >= 4.0 -> PASS  (VE MOI)
    delta <  threshold va avg_after <  4.0 -> FAIL
Y nghia: cell tut nhieu nhung chat luong CON LAI van tot (>= 4/5) thi KHONG can
xuat phieu - phieu chi danh cho cell THAT SU kem sau CR.
LUU Y HOI TO: luat CU chi xet delta nen he thong DA TUNG danh FAIL cho cell le
ra PASS theo luat moi -> co the da xuat phieu THUA (xem docs/DEV_LOG.md muc
[VE avg_after >= 4]).

DA BO (khong lam) - tieu chi "dem so ngay dat >= 4/7": THUA VE TOAN HOC voi
thang 1-5 / 7 ngay. Neu k = so ngay dat (diem >= 4) thi phan con lai toi da 3
diem/ngay: sum <= 5k + 3(7-k) = 2k + 21. avg >= 4 <=> sum >= 28 => 2k + 21 >= 28
=> k >= 3.5 => k >= 4 = 4/7. Tuc avg_after >= 4 DA BAO HAM >= 4/7 ngay dat -
them dieu kien dem ngay khong loai them duoc cell nao. Chi giu 2 truong THAM
KHAO (diem_thap_nhat_sau, so_ngay_dat_sau) de nguoi van hanh doi chieu.
"""

from dataclasses import dataclass
from datetime import date

MIN_DAYS_REQUIRED = 5  # BUSINESS_RULES.md SS8.2 dong 372 - < 5 ngay -> INSUFFICIENT_DATA
# SUA 03/10/2026 - DOI DAU thanh SO DUONG (xem "SUA 03/10/2026" dau file):
# delta = avg_before - avg_after (duong = tut) nen PASS la "tut KHONG QUA 0.1",
# dieu kien trong evaluate() la "delta > threshold -> FAIL" (truoc day la
# "delta < threshold", khi delta/threshold con la so am).
PASS_THRESHOLD_DELTA = 0.1  # BUSINESS_RULES.md SS8.3 - dung sai, tranh false alarm tu nhieu do luong

# Muc chat luong TOI THIEU tuyet doi. CA HAI metric deu la thang 1-5 (QoS tu
# CTS, QoE tu CEM - truong ux_final, da kiem chung bang goi that 15/08) nen doc
# theo cung mot cach hieu.
#
# === DOI TEN + DOI VAI TRO (04092026, yeu cau nghiep vu) ===
# Ten cu MUC_TOT = 4.0, vai tro CUU: cell tut qua dung sai NHUNG avg_after >= 4
# thi VAN DAT ("tut nhieu nhung con tot thi bo qua").
# Nay MUC_TOI_THIEU = 3.0, vai tro SAN: avg_after duoi muc nay la KHONG DAT
# NGAY, khong lien quan gi den delta.
#
# DOI TEN chu khong giu ten cu: hang so gio noi mot dieu NGUOC LAI voi truoc.
# Giu ten "MUC_TOT" cho mot cai san toi thieu se lam moi nguoi doc sau nay hieu
# nham chieu cua phep so sanh - va day dung la loai nham lan da lam FE tinh sai
# suot 2 dot.
MUC_TOI_THIEU = 3.0

# SUA 18/10/2026 (quyet dinh user, sau doi chieu file hau kiem TXN250M): TB va
# Lech LAM TRON 2 chu so TRUOC khi so nguong.
# Bug that: TXN092M12 session 10707 QoS TB truoc 25/6, TB sau 22/6 -> float
# tru ra 0.5000000000000004 > 0.5 -> KHONG DAT va da xuat phieu 32084, trong
# khi 2 cell lech DUNG 0.5 cung session thi DAT. Nguoi doc bang (hien 2 chu
# so) thay 3 cell cung "0.50" ma 2 ket luan khac nhau.
# TB = round(TB tho, 2); Lech = round(TB tho truoc - TB tho sau, 2) - khop
# cach file hau kiem doi chieu tinh (Lech 0.1667 -> 0.17). round() cung bo
# luon nhieu float (0.5000000000000004 -> 0.5).
# Dashboard SQL dung ROUND(...,2) CUNG cong thuc (adapters/postgres/
# dashboard_repo.py).
LAM_TRON_SO_THAP_PHAN = 2

# Ly do KHONG DAT. Dat thanh hang so de cho doc (log, DEV_LOG, FE) khong go lai
# chuoi - go sai 1 ky tu la loc nham.
#
# TU 04092026 co 2 ly do RIENG BIET, vi 2 dieu kien da doc lap: nguoi van hanh
# can biet cell nay "tut nhieu" hay "dang o muc kem" - 2 tinh huong doi 2 cach
# xu ly khac nhau.
LY_DO_DUOI_MUC_TOI_THIEU = "DUOI_MUC_TOI_THIEU"
LY_DO_TUT_QUA_NHIEU = "TUT_QUA_NHIEU"

# Ten cu (truoc 04092026), khi 2 dieu kien con dinh vao nhau thanh 1 nhanh.
# GIU LAI de code/du lieu cu doc duoc, KHONG con duoc gan moi.
LY_DO_TUT_VA_KEM = "TUT_VA_CHAT_LUONG_KEM"


@dataclass
class MetricEvaluation:
    # Kieu rieng cua domain (KHONG dung EvaluationResult, B2.9) — EvaluationResult
    # la placeholder danh cho C2.2 (application layer, ghep ca qoe+qos result +
    # cac field khac cua session). Da chot voi user.
    result: str  # "PASS" | "FAIL" | "INSUFFICIENT_DATA"
    avg_before: float | None
    avg_after: float | None

    # === 3 truong THAM KHAO (co default) - KHONG tham gia phan quyet ===
    # Them cung luc voi ve avg_after >= 4. Co default nen KHONG cho goi nao phai
    # sua (MetricEvaluation chi duoc dung o dung 1 cho: cuoi evaluate()).
    #
    # VI SAO CAN: phan quyet dua tren TRUNG BINH, ma trung binh CHE duoc ngay mat
    # dich vu - vd [5,5,5,5,5,5,1] co avg 4.43 >= 4 nen PASS, nhung co 1 ngay
    # diem 1 (gan nhu mat dich vu ca ngay). 2 truong nay de nguoi van hanh doi
    # chieu va phat hien nhung ca do.
    # NEU sau nay thay lot nhieu ca kieu vay -> them ve diem_thap_nhat_sau >= 2
    # vao dieu kien PASS (KHONG sua o day cho den khi co so lieu that).
    diem_thap_nhat_sau: float | None = None  # min(after_values)
    so_ngay_dat_sau: int = 0  # so ngay after_values >= muc_toi_thieu (3.0)

    # Chi dien khi FAIL; PASS/INSUFFICIENT_DATA -> None (khong co "ly do khong
    # dat" cho cell DAT). Hien chi 1 gia tri vi chi con 1 duong dan toi FAIL.
    ly_do_khong_dat: str | None = None

    # Lech DA LAM TRON = round(avg_before - avg_after, 2), DUONG = tut (SUA
    # 18/10/2026, xem LAM_TRON_SO_THAP_PHAN). None khi thieu 1 trong 2 ve. Moi
    # noi can "lech" (API delta, Excel, ly do dat) doc field nay thay vi tu tru
    # lai 2 avg - tru lai tren float se ra 0.5000000000000004 thay vi 0.5.
    lech: float | None = None


class EvaluationService:
    def evaluate(
        self,
        before_values: list[float],
        after_values: list[float],
        threshold: float = PASS_THRESHOLD_DELTA,
        muc_toi_thieu: float = MUC_TOI_THIEU,
    ) -> MetricEvaluation:
        # Dung 1 method cho ca QoE va QoS (goi 2 lan tu use case, C2.2) - 2 ket qua
        # hoan toan doc lap (BUSINESS_RULES.md dong 387). before_values/after_values
        # da duoc loc san (chi chua ngay CO data) - viec query/loc tu SOC/CTS la
        # cua use case, ngoai scope domain service nay.
        #
        # threshold them cho XuatPhieuUseCase (KHOI 3a/5, dung sai 0.2 rieng) -
        # default = PASS_THRESHOLD_DELTA nen moi cho goi CU (EvaluateCrUseCase,
        # khong truyen tham so nay) GIU NGUYEN het hanh vi -0.1 cu.
        #
        # Avg luon duoc tinh truoc (theo so ngay thuc te, KHONG chia co dinh 7 -
        # BUSINESS_RULES.md dong 363-369), roi moi check nguong - de avg_before/
        # avg_after van co gia tri huu ich cho log ngay ca khi INSUFFICIENT_DATA.
        # Lam tron NGAY tai day (SUA 18/10/2026, xem LAM_TRON_SO_THAP_PHAN) -
        # MetricEvaluation chi mang TB da tron, nen moi noi doc tiep (do_te,
        # khoa uu tien, API, Excel) dung CUNG so voi phep so nguong.
        tho_truoc = sum(before_values) / len(before_values) if before_values else None
        tho_sau = sum(after_values) / len(after_values) if after_values else None
        avg_before = round(tho_truoc, LAM_TRON_SO_THAP_PHAN) if tho_truoc is not None else None
        avg_after = round(tho_sau, LAM_TRON_SO_THAP_PHAN) if tho_sau is not None else None
        # Lech = round(TB THO truoc - TB THO sau, 2) - KHONG tru 2 TB da tron:
        # file hau kiem doi chieu (TXN090M11 4.3333 - 4.1667 = 0.1667 -> 0.17)
        # se ra 0.16 neu tru 4.33 - 4.17.
        lech = (
            round(tho_truoc - tho_sau, LAM_TRON_SO_THAP_PHAN)
            if tho_truoc is not None and tho_sau is not None
            else None
        )

        # 2 truong THAM KHAO - tinh cho MOI ket qua (ke ca INSUFFICIENT_DATA) vi
        # chung mo ta du lieu, khong phai phan quyet.
        diem_thap_nhat_sau = min(after_values) if after_values else None
        so_ngay_dat_sau = sum(1 for v in after_values if v >= muc_toi_thieu)

        ly_do_khong_dat = None

        if len(before_values) < MIN_DAYS_REQUIRED or len(after_values) < MIN_DAYS_REQUIRED:
            # Nguong ap dung doc lap cho CA before VA after (da chot voi user) -
            # thieu 1 ben la khong du tin cay de so sanh.
            result = "INSUFFICIENT_DATA"
        else:
            # SUA 03/10/2026: delta = avg_before - avg_after - DUONG nghia la
            # TUT (chat luong giam), AM nghia la CAI THIEN. Dac ta noi "chenh
            # lech TB truoc-sau <= 0.2 -> DAT" doc TU NHIEN theo dung chieu
            # nay (khong con can doi dau nhu truoc). Ve moi ben duoi khong
            # dung delta nen khong anh huong.
            delta = lech

            # === 2 DIEU KIEN DOC LAP (04092026) ===
            # Vi pham BAT KY cai nao la KHONG DAT. KHONG con nhanh "tut nhieu
            # nhung van tot thi cuu" - xem lich su luat o docstring dau file.
            if avg_after < muc_toi_thieu:
                # Dieu kien 1 - SAN chat luong tuyet doi. Xet TRUOC delta vi no
                # KHONG phu thuoc delta: cell dang o 2.0 diem thi du no khong
                # tut ti nao (delta = 0) van la cell kem, van phai co nguoi di
                # xem. So sanh < (KHONG phai <=): dung 3.0 VAN DAT.
                result = "FAIL"
                ly_do_khong_dat = LY_DO_DUOI_MUC_TOI_THIEU
            elif delta > threshold:
                # Dieu kien 2 - MUC TUT tuong doi (SUA 03/10/2026, dau DUONG):
                # "tut qua 0.5 la khong dat" -> (avg_before - avg_after) > 0.5.
                # Bien: tut DUNG 0.5 thi delta = 0.5, KHONG > 0.5, nen DAT.
                result = "FAIL"
                ly_do_khong_dat = LY_DO_TUT_QUA_NHIEU
            else:
                result = "PASS"

        return MetricEvaluation(
            result=result,
            avg_before=avg_before,
            avg_after=avg_after,
            diem_thap_nhat_sau=diem_thap_nhat_sau,
            so_ngay_dat_sau=so_ngay_dat_sau,
            ly_do_khong_dat=ly_do_khong_dat,
            lech=lech,
        )


def doi_ket_luan_do_lam_tron(
    before_values: list[float],
    after_values: list[float],
    threshold: float,
    muc_toi_thieu: float = MUC_TOI_THIEU,
) -> bool:
    """True neu CHI vi lam tron 2 chu so (SUA 18/10/2026) ma chi so nay doi tu
    KHONG DAT (so tren TB/lech THO, cach truoc 18/10) sang khong con KHONG DAT.

    KHONG phai luat danh gia thu 2: ket luan van chi do evaluate() quyet dinh.
    Ham nay chi tra loi "phieu da xuat truoc 18/10 co phai do nhieu float o
    bien khong" de FE danh dau phieu "xuat theo luat cu" (vd phieu 32084,
    TXN092M12: lech tho 0.5000000000000004). Thieu ngay -> False (khong ket
    luan duoc ca truoc lan sau)."""
    if len(before_values) < MIN_DAYS_REQUIRED or len(after_values) < MIN_DAYS_REQUIRED:
        return False
    tb_truoc = sum(before_values) / len(before_values)
    tb_sau = sum(after_values) / len(after_values)
    tho_khong_dat = tb_sau < muc_toi_thieu or (tb_truoc - tb_sau) > threshold
    moi = EvaluationService().evaluate(before_values, after_values, threshold, muc_toi_thieu)
    return tho_khong_dat and moi.result != "FAIL"


def do_te_cua(metric_eval, muc_toi_thieu: float = MUC_TOI_THIEU) -> float:
    """Muc do TE cua 1 cell theo 1 chi so. Cang LON cang te. Dung de XEP HANG.

    do_te = max(muc_tut, muc_thieu)
        muc_tut   = max(0, avg_before - avg_after)   <- GIAM tuong doi
        muc_thieu = max(0, muc_toi_thieu - avg_after) <- THIEU tuyet doi

    === VI SAO PHAI THEM VE muc_thieu (04092026) ===
    Truoc day do_te CHI la (avg_before - avg_after). Tu khi luat co them SAN
    3.0, cell vi pham san MA KHONG TUT se co do_te AM.
    Ca THAT do duoc: 4G-NTM380M43 di tu 1.29 len 1.86 -> do_te = -0.571.
    Cell nay dang o 1.86/5 - KEM NHAT ca lo - nhung sort giam dan day no xuong
    CUOI. Session nao co hon 10 cell khong dat se CAT MAT no, trong khi cell
    chi tut nhe tu 5.0 xuong 4.4 lai duoc suat xuat phieu. Nguoc hoan toan voi
    muc dich cua tran 10 (uu tien cell te nhat).

    === VI SAO max CHU KHONG PHAI CONG ===
    2 dai luong do 2 THU KHAC NHAU: muc GIAM tuong doi vs muc THIEU tuyet doi.
    Cong lai ra mot so khong co y nghia vat ly (vd "tut 0.5 + thieu 1.0 = 1.5"
    khong tra loi duoc cau hoi gi). max tra loi dung cau hoi can hoi: "cell nay
    te nhat o muc nao" - cung cach da dung cho max giua QoS va QoE.
    Va max giu do_te CUNG THANG DIEM 1-5 voi avg_after nen so sanh duoc voi
    nhau; cong thi vuot thang.

    max(0, ...) o CA HAI ve: cell cai thien (avg_after > avg_before) khong duoc
    tra do_te am keo tut thu hang cua chinh no o ve kia.

    Tra 0.0 khi thieu avg (INSUFFICIENT_DATA) - cell do bi loai truoc khi sort
    nen gia tri nay khong anh huong thu tu, chi de tranh crash None.
    """
    if metric_eval is None or metric_eval.avg_before is None or metric_eval.avg_after is None:
        return 0.0
    # SUA 18/10/2026: lech DA LAM TRON (cung so da so nguong). Tru lai 2 avg
    # tren float lam 2 cell cung lech 0.69 thanh 0.6899.. va 0.6900..4 - pha
    # hoa sai thu tu xep hang. Fallback tru tay cho MetricEvaluation dung tay
    # (test cu) khong co lech.
    lech = metric_eval.lech if metric_eval.lech is not None else metric_eval.avg_before - metric_eval.avg_after
    muc_tut = max(0.0, lech)
    muc_thieu = max(0.0, muc_toi_thieu - metric_eval.avg_after)
    return max(muc_tut, muc_thieu)


def _ket_luan_duoc(metric_eval) -> bool:
    """Chi so nay co du can cu de tham gia xep hang khong.

    Loai CA 2 truong hop: khong co so (avg None), VA co so nhung
    INSUFFICIENT_DATA (< MIN_DAYS_REQUIRED ngay). Ly do loai truong hop thu 2:
    evaluate() tinh avg TRUOC roi moi check so ngay, nen mot chi so 3/7 ngay van
    co avg_after - nhung chinh EvaluationService da tu choi ket luan tu no. Lay
    no ra xep hang la mau thuan voi quyet dinh do, va 3 ngay nhieu do luong du
    keo mot cell len dau danh sach uu tien.
    """
    return (
        metric_eval is not None
        and metric_eval.avg_after is not None
        and metric_eval.result != "INSUFFICIENT_DATA"
    )


def khoa_uu_tien_xuat_phieu(qos_eval, qoe_eval, muc_toi_thieu: float = MUC_TOI_THIEU) -> tuple:
    """Khoa sort chon cell xuat phieu. Sort TANG DAN, phan tu dau = uu tien nhat.

    Tra (nhom, -do_giam, avg_after_min):
        nhom        0 neu diem TB sau THAP NHAT trong 2 chi so < muc_toi_thieu
                    (3.0), nguoc lai 1  -> nhom 0 LUON dung truoc nhom 1
        do_giam     max(0, before - after), lay MAX giua QoS va QoE
                    (de dau AM trong khoa: giam cang lon cang dung truoc)
        avg_after_min  pha hoa nguoi cuoi: diem con lai cang thap cang truoc

    === VI SAO THAY do_te_cua() O CHO XEP HANG (09/2026, user chot) ===
    Tieu chi van hanh moi: "diem TB < 3 di truoc, trong moi nhom thi do giam
    lon di truoc". Day la thu tu TU DIEN 2 TANG - mot con so don khong dien
    dat duoc, vi no luon phai quy doi "duoi san" va "tut nhieu" ve cung mot
    thang roi so sanh.
    do_te_cua() = max(muc_tut, muc_thieu) chinh la phep quy doi do, va no LAM
    MAT tieu chi tang 1. Ca THAT, session 4884 (do 09/2026):
        4G-HKM022M43-HNI  QoE 2.71 -> 2.83  (DUOI san 3.0)
            muc_thieu = 3.00 - 2.83 = 0.17
            muc_tut (QoS) = 4.29 - 4.00 = 0.29
            do_te = max(0.17, 0.29) = 0.286  -> xep CHOT bang 13, bi cat
        4G-HKM022M13-HNI  QoE 4.57 -> 3.17  (TREN san, chi tut nhieu)
            do_te = 1.405 -> xep dau bang, duoc xuat
    Tuc cell DUY NHAT dang duoi muc toi thieu lai la cell bi cat dau tien.
    Khoa 2 tang sua dung cho do: nhom 0 (duoi san) luon di truoc, bat ke tut
    bao nhieu.

    === CHI SO THIEU DU LIEU: BO QUA, KHONG COI LA 0 ===
    Coi la 0 se lam cell thieu QoE tu dong roi vao nhom 0 (0 < 3.0) va nhay len
    dau danh sach uu tien - tuc "khong do duoc" bi doc thanh "rat te". Cell chi
    con 1 chi so thi xep hang bang DUNG chi so do. Xem _ket_luan_duoc().
    """
    co_du_lieu = [e for e in (qos_eval, qoe_eval) if _ket_luan_duoc(e)]

    if not co_du_lieu:
        # Khong xay ra qua duong xuat phieu (caller chi xep hang cell da FAIL,
        # ma FAIL doi hoi du ngay) - nhung khoa sort PHAI luon tra ve tuple so
        # sanh duoc, khong duoc None. Day xuong cuoi, khong bia diem.
        return (1, 0.0, float("inf"))

    avg_after_min = min(e.avg_after for e in co_du_lieu)
    # Chi tinh do giam tren chi so CO CA before LAN after - avg_before co the
    # None rieng (cua so truoc rong) trong khi after van du.
    # SUA 18/10/2026: dung lech DA LAM TRON - xem ly do o do_te_cua().
    do_giam = max(
        (
            max(0.0, e.lech if e.lech is not None else e.avg_before - e.avg_after)
            for e in co_du_lieu
            if e.avg_before is not None
        ),
        default=0.0,
    )

    # So sanh < (KHONG <=): dung 3.0 la DAT, cung nguong voi nhanh FAIL o
    # evaluate() - 2 cho phai cung chieu, neu khong se co cell "dat" ma van bi
    # xep vao nhom uu tien cao nhat.
    nhom = 0 if avg_after_min < muc_toi_thieu else 1
    return (nhom, -do_giam, avg_after_min)


# === SNAPSHOT PER-CELL, DUNG CHUNG cho QoS lan QoE (09/2026) ===
#
# 3 ham duoi day CHUYEN TU application/evaluate_cr_use_case.py sang day
# (khong phai viet moi): domain la noi DUY NHAT cac ham nay duoc dinh nghia,
# ca EvaluateCrUseCase (job danh gia) lan GetQoeCellsUseCase (lazy load + job
# xuat phieu) cung goi TU DAY thay vi moi noi tu viet lai.
#
# LY DO GOP (bug that, khong phai gia dinh): truoc 09/2026, moi noi tu viet
# ham rieng de "gop diem theo (cell, ngay) roi upsert" - EvaluateCrUseCase co
# _diem_theo_cell_ngay()/_snapshot_points() rieng, GetQoeCellsUseCase co
# _diem_tu_gateway() rieng va CHI xu ly 2/3 period (thieu "cr_day"). Day la
# LAN THU 3 mot cong thuc nghiep vu bi chep tay o nhieu noi va lech nhau (2
# lan truoc: qosEvaluation.ts o FE, va do_te QoE tinh rieng bang -delta thay
# vi do_te_cua() dung chung - xem docstring khoa_uu_tien_xuat_phieu() o tren).


def loc_diem_theo_ngay(raw: list[dict], allowed_dates: set[str]) -> list[dict]:
    """Loc raw dang gateway (nhieu cell, [{"cell_name":.., "metrics":[..]}])
    chi giu lai diem co ngay ("time"[:10]) nam trong allowed_dates.

    VI SAO CAN: mot so duong FETCH cua so RONG HON cua so DANH GIA - vd mo
    rong fetch sang ngay T (ngay CR) de co du lieu luu snapshot
    period="cr_day" (xem diem_snapshot_theo_cua_so() ben duoi), nhung phep
    tinh avg_after PASS/FAIL van PHAI gioi han DUNG T+1..T+7 nhu truoc, khong
    duoc de ngay T lot vao am tham lam lech ket qua danh gia.
    """
    ket_qua = []
    for entry in raw:
        metrics = [p for p in entry.get("metrics", []) if p.get("time", "")[:10] in allowed_dates]
        ket_qua.append({**entry, "metrics": metrics})
    return ket_qua


def _diem_theo_cell_ngay(raw: list[dict], value_key: str, allowed_dates: set[str]) -> dict:
    """{(cell_name, "YYYY-MM-DD"): diem} - GIU RIENG tung cell, KHONG gop cheo.

    Phuc vu persist snapshot PER-CELL: moi cell 1 dong/ngay. 1 cell co the co
    nhieu diem trong cung 1 ngay (CTS/CEM co the tra hourly du granularity
    ngay) nen van phai trung binh trong NOI BO 1 cell/1 ngay.
    """
    gom: dict = {}
    for cell_entry in raw:
        cell_name = cell_entry.get("cell_name")
        if cell_name is None:
            continue
        for point in cell_entry.get("metrics", []):
            date_key = point["time"][:10]
            if date_key not in allowed_dates:
                continue
            gom.setdefault((cell_name, date_key), []).append(point[value_key])
    return {k: sum(v) / len(v) for k, v in gom.items()}


def _snapshot_points(score_key: str, nhom: list) -> list[dict]:
    """Ghep cac nhom (du_lieu, danh_sach_ngay, period) thanh list dict de upsert.

    nhom: [({(cell,ngay): diem}, [ngay...], "before"|"cr_day"|"after"), ...]
    Ngay KHONG co du lieu don gian VANG MAT (khong co placeholder null - cot
    score la NOT NULL trong DB).
    """
    points = []
    for theo_cell_ngay, ngay_list, period in nhom:
        for (cell_name, ngay), diem in theo_cell_ngay.items():
            if ngay in ngay_list:
                points.append(
                    {
                        "cell_name": cell_name,
                        "snapshot_date": date.fromisoformat(ngay),
                        score_key: diem,
                        "period": period,
                    }
                )
    return points


def diem_snapshot_theo_cua_so(
    value_key: str,
    score_key: str,
    before_raw: list[dict],
    before_dates: set[str],
    after_raw_rong: list[dict],
    after_dates: set[str],
    ngay_cr: str,
) -> list[dict]:
    """Ghep du lieu tho gateway thanh diem snapshot upsert-duoc, LUON DU 3
    period (before/cr_day/after). Dung chung cho ca QoS lan QoE, ca duong
    danh gia (EvaluateCrUseCase) lan duong lazy/job xuat phieu
    (GetQoeCellsUseCase) - xem docstring khoi tren.

    after_raw_rong PHAI la ket qua fetch TU ngay_cr (T) den T+7 (KHONG chi
    T+1..T+7) - ngay T duoc tach rieng cho period="cr_day" ngay tai day
    (allowed_dates={ngay_cr}), KHONG anh huong avg_after o cho khac vi ham
    nay CHI xay diem snapshot, khong tinh PASS/FAIL.
    """
    diem_before = _diem_theo_cell_ngay(before_raw, value_key, before_dates)
    diem_after_rong = _diem_theo_cell_ngay(after_raw_rong, value_key, after_dates | {ngay_cr})
    nhom = [
        (diem_before, sorted(before_dates), "before"),
        (diem_after_rong, [ngay_cr], "cr_day"),
        (diem_after_rong, sorted(after_dates), "after"),
    ]
    return _snapshot_points(score_key, nhom)
