"""
Schemas cho GET /sessions/{id}/qos-cells (04092026).
Ban DOI XUNG cua api/schemas/qoe_schemas.py - 2 bang nam canh nhau trong cung
1 muc tren UI nen hinh dang response phai GIONG NHAU, FE dung chung 1 kieu
render.
"""

from datetime import date

from pydantic import BaseModel


class CuaSoNgay(BaseModel):
    """Khoang ngay LICH GMT+7 cua 1 cua so danh gia (04092026).

    Day la cua so YEU CAU (tinh tu executed_at), KHONG phai so ngay thuc su co
    du lieu - cai do nam o so_ngay_before/so_ngay_after cua tung cell.
    """

    tu: date
    den: date


class QosCellItem(BaseModel):
    cell_name: str

    # None khi cell khong co ngay nao co du lieu - KHONG dung 0.0, vi 0.0 la
    # mot diem QoS hop le ve mat kieu du lieu.
    avg_before: float | None = None
    avg_after: float | None = None
    # avg_before - avg_after. DUONG = TUT (sua 03/10/2026, truoc day AM = tut).
    # None khi thieu 1 trong 2 ve.
    delta: float | None = None

    # So ngay THUC TE co du lieu trong cua so 7 ngay (khong phai luon = 7).
    # < 5 (MIN_DAYS_REQUIRED) -> ket_qua = INSUFFICIENT_DATA.
    so_ngay_before: int
    so_ngay_after: int

    # "PASS" | "FAIL" | "INSUFFICIENT_DATA" - cua RIENG cell nay.
    #
    # PASS = qua CA HAI dieu kien doc lap (luat 04092026):
    #   avg_after >= 3.0 (MUC_TOI_THIEU)  VA  tut khong qua 0.5 diem
    # FE doc thang truong nay, KHONG tu tinh lai - ban sao luat ben FE da troi
    # khoi BE 2 lan (lan gan nhat lam cell 117449 bi gan nhan sai).
    ket_qua: str

    # 2 truong THAM KHAO (khong tham gia phan quyet) - trung binh CHE duoc ngay
    # mat dich vu, vd [5,5,5,5,5,5,1] co avg 4.43 nen PASS nhung co 1 ngay diem 1.
    diem_thap_nhat_sau: float | None = None
    so_ngay_dat_sau: int = 0


class NguongDanhGia(BaseModel):
    """3 nguong quyet dinh DAT/KHONG DAT cua mot lan danh gia (04092026).

    === VI SAO PHAI TRA RA CHO FE ===
    FE ve chart 15 ngay va can ve DUONG THAM CHIEU cho nguong. Truoc day FE tu
    hardcode so trong qosEvaluation.ts - va ban sao do da TROI KHOI BE 3 LAN:
      Lan 1: FE thieu han ve "avg_after >= 4 thi van DAT" -> gan nhan KHONG DAT
             cho cell 117449 (4.83 -> 4.33), nguoi dung bam xuat, BE tra
             DAT_KHONG_XUAT. FE noi mot dang, BE lam mot dang.
      Lan 2: BE doi dung sai 0.2 -> 0.5, FE van giu 0.2.
      Lan 3: BE them san MUC_TOI_THIEU = 3.0, FE khong biet -> chart ve duong
             nguong SAI, nguoi xem tuong nguong van la 0.2.
    Ban sao troi KHONG phai rui ro ma la chuyen chac chan xay ra. Tra nguong ra
    theo response thi FE khong con gi de hardcode.

    Dat o CAP RESPONSE (khong phai cap cell): nguong la NHU NHAU cho moi cell
    trong 1 lan danh gia - lap lai 14 lan la thua, giong het ly do da dat 3
    truong cua so o cap nay.

    === DAU CUA delta_toi_da: SO DUONG ===
    SUA 03/10/2026: delta va threshold trong code NAY DA la so DUONG tu goc
    (domain/services/evaluation_service.py::evaluate(), delta = avg_before -
    avg_after) - dieu kien KHONG DAT la delta > 0.5. KHONG con buoc doi dau
    nao giua code va response nua (truoc day code dung so am, phai doi dau
    rieng o day cho FE - chinh cho doi dau do la noi de sai nhat, xem lich su
    trong domain/services/evaluation_service.py).
    Tra DUONG: 0.5 = "tut qua 0.5 diem la KHONG DAT". FE dung thang, khong
    tinh toan gi them.
    """

    # Tut qua muc nay (theo huong GIAM) la KHONG DAT. So DUONG - xem docstring.
    # Bien: tut DUNG bang gia tri nay VAN DAT (code so sanh delta > threshold).
    delta_toi_da: float
    # avg_after DUOI muc nay la KHONG DAT ngay, khong lien quan delta.
    # Bien: dung bang gia tri nay VAN DAT (code so sanh avg_after < muc_toi_thieu).
    muc_toi_thieu: float
    # It hon so ngay nay o BAT KY phia nao (truoc/sau) -> INSUFFICIENT_DATA
    so_ngay_toi_thieu: int


class QosCellsResponse(BaseModel):
    cr_session_id: int
    # 3 truong cua so (04092026) - CAP RESPONSE chu khong phai cap cell: cua so
    # la NHU NHAU cho moi cell trong session, lap lai 14 lan la thua.
    #
    # VI SAO CAN: QoS va QoE dung CUNG cong thuc cua so nhung SO NGAY THUC TE
    # co du lieu thuong LECH NHAU (CTS tre 1 ngay, CEM tre 2 ngay, va CEM co lo
    # thung). Do that session 1811: QoS 7/6 ngay, QoE 6/7 ngay tren CA 14 cell.
    # Hai con so trung binh vi vay KHONG so sanh truc tiep duoc.
    # FE doi chieu so_ngay_* cua 2 bang de biet CO lech; 3 truong nay cho biet
    # cua so goc de hien cau day du "6/7 ngay (14-20/08)".
    #
    # KHONG tra danh sach ngay day du: 14 cell x 14 ngay = 196 chuoi (~2.5KB)
    # trong khi thong tin do suy duoc tu ngay_cr, va cai FE that su can chi la
    # "co lech hay khong" - so_ngay_* da tra loi.
    ngay_cr: date
    cua_so_before: CuaSoNgay
    cua_so_after: CuaSoNgay
    # THEM 18/10/2026 (MOT NGUON SO LIEU) - ngay (GMT+7) chup snapshot ma bang
    # nay dang doc; FE ghi "So lieu tai thoi diem danh gia dd/mm". None = so
    # lieu goi CTS/CEM truc tiep (session chua danh gia / chua co snapshot).
    ngay_chup_snapshot: date | None = None
    # nguong dang ap dung cho lan danh gia nay - xem NguongDanhGia
    nguong: NguongDanhGia
    total: int
    data: list[QosCellItem]
