"""
Schemas cho /cr/* endpoints.
Tu: TASK_LIST.md C1.1; API_CONTRACTS.md Section 6 (POST /cr/trigger)
"""

from typing import Literal

from pydantic import BaseModel, model_validator


class TriggerCrRequest(BaseModel):
    tram_id: str | None = None
    tram_name: str | None = None
    action: Literal["shutdown", "cancel", "relocate"]

    @model_validator(mode="after")
    def _check_tram_identifier(self) -> "TriggerCrRequest":
        # BUSINESS_RULES.md SS1 dong 16 - "tram_id hoac tram_name phai co it nhat 1"
        if not self.tram_id and not self.tram_name:
            raise ValueError("Phai co it nhat tram_id hoac tram_name")
        return self


class TriggerCrResponse(BaseModel):
    # API_CONTRACTS.md dong 526-533 - Response 202 Accepted
    session_id: int
    status: str
    message: str


class PreviewTramGoc(BaseModel):
    # KHONG co danh sach cell rieng - tram_goc la tram bi tac dong (shutdown/
    # relocate), cell cua chinh no da bi loai khoi ca 2 nhanh (xem
    # AffectedCellItem/CrCellItem - cell_bi_anh_huong/cells_chay_cr).
    tram_id: str
    tram_name: str | None = None
    longitude: float | None = None
    latitude: float | None = None


class AffectedCellItem(BaseModel):
    # 22072026 (xac nhan voi user) - Nhanh A: danh gia PHAM VI anh huong RF,
    # KHONG loc huong/band, KHONG co gia tri rsboost/qrxlevmin (xem
    # application/preview_cr_use_case.py docstring "2 nhanh").
    #
    # cell_name/tram_id: str | None (SUA BUOC 4b, 08/10/2026) - nhanh HO co
    # the co cell CAN_GHEP_TEN (khong resolve duoc ten/DN) van PHAI tra ra de
    # nguoi dung biet (yeu cau truc tiep user), chi khong ghi cr_affected_cells.
    cell_name: str | None = None
    huong_id: str | None = None
    tram_id: str | None = None
    # 5 field OPTIONAL THEM (BUOC 4b, 08/10/2026) - CHI co gia tri o nhanh HO
    # (None/[] cho nhanh CDS).
    pct_ho: float | None = None
    so_ho: int | None = None
    sr: float | None = None
    layer: str | None = None
    co: list[str] = []
    # sector/sectors_khac THEM (12/10/2026, yeu cau truc tiep user) - sector
    # DA GAN cho cell (sector co %HO cao nhat, xem GD4) + cac sector PHU khac
    # cung co HO sang cell nay (co the rong). KHONG co 2 field nay, FE khong
    # biet pct_ho/so_ho dang tinh tren mau so sector nao, de tuong %HO lech
    # giua cac cell do KHAC sector (khac mau so), khong phai do loi du lieu.
    sector: int | None = None
    sectors_khac: list[int] = []


class AffectedTramItem(BaseModel):
    tram_id: str
    tram_name: str | None = None
    longitude: float | None = None
    latitude: float | None = None


class CrCellItem(BaseModel):
    # Nhanh B - THAY THE PreviewCellItem cu (da xoa) - them field tram_id
    # (truoc day nam duoi PreviewTramItem.cells, gio flat list nen can tram_id
    # rieng tren tung cell de FE biet cell thuoc tram nao).
    cell_name: str
    tram_id: str
    huong_id: str | None = None
    priority: int | None = None
    action_type: str | None = None
    rsboost_cu: float | None = None
    rsboost_moi: float | None = None
    qrxlevmin_cu: int | None = None
    qrxlevmin_moi: int | None = None
    # 2 field THEM (quyet dinh 03/10/2026, luat chon cell CR moi thay band
    # theo huong_id): band cua CHINH CELL LAN CAN ("1800 F1"/"1800 F2", suy tu
    # LNCEL trong DN cua no - KHONG phai band huong tram tat) + sector cua
    # TRAM TAT (Y = huong_id % 10) - FE hien thi de nguoi dung hieu VI SAO
    # cell nay duoc/khong duoc chon (vd 2 cell cung priority nhung khac band).
    band: str | None = None
    sector: int | None = None
    # 4 field OPTIONAL THEM (BUOC 4b, 08/10/2026) - CHI co gia tri o nhanh HO
    # (None cho nhanh CDS).
    pct_ho: float | None = None
    so_ho: int | None = None
    sr: float | None = None
    layer: str | None = None


class CellNgoaiPhamViChiTiet(BaseModel):
    # V8 (09/2026) - ban CHI TIET cua cell_ngoai_pham_vi (list[str] cu, GIU
    # NGUYEN khong doi kieu vi FE dang doc). ly_do la MA CO DINH (xem
    # domain/services/neighbor_cell_filter.py::LY_DO_*), khong phai chuoi tu
    # do dien giai - FE map ma -> text hien thi, tranh doi chu 1 cho phai sua
    # ca 2 phia.
    cell_name: str
    ly_do: str
    # THEM 23/10/2026 - cau cu the cho OSS_CHUA_CAU_HINH (vd "NA14 cau hinh
    # loi: thieu password"); None voi ly do khac. ly_do van la ma co dinh.
    chi_tiet: str | None = None


class OssSeDung(BaseModel):
    # Giai doan 1 buoc 2 (27/09/2026) - CHI lo instance_id, TUYET DOI KHONG
    # user/password (xem domain/value_objects/oss_instance.py). Preview tra
    # field nay de nguoi dung THAY OSS se dung TRUOC khi bam nut chay that -
    # vd phat hien nham OSS (do sai mau ten cell) truoc khi anh huong live
    # network, khong phai sau khi da SSH.
    #
    # SUA 03/10/2026 - BO host: IP NetAct la thong tin ha tang noi bo, KHONG
    # can thiet cho nguoi dung quyet dinh "co bam nut chay khong" (chi can
    # biet TEN GOI instance_id de nhan ra dung/sai OSS) - lo IP qua API cong
    # khai la thua rui ro an ninh so voi loi ich mang lai.
    instance_id: str


class PreviewCrResponse(BaseModel):
    # 22072026: THAY THE hoan toan "tram_lan_can" cu (SAI - truoc day suy tu
    # 12 cell Nhanh B, khong phai tu 47 cell pham vi anh huong that - xem
    # docs/DEV_LOG.md muc trace tram 110548/111139) bang 3 field ro rang:
    tram_goc: PreviewTramGoc
    cells_bi_anh_huong: list[AffectedCellItem]
    tram_bi_anh_huong: list[AffectedTramItem]
    cells_chay_cr: list[CrCellItem]
    # 2 truong cell ngoai pham vi (07092026) - CDS tra cell_id dang PHANG cho
    # cell no khong quan ly (vd "4G-PYN015M12-VPC" tinh Vinh Phuc). Chung da bi
    # loai khoi 3 danh sach tren.
    #
    # PHAI hien len UI, KHONG duoc im lang: nguoi dung nhin pham vi anh huong
    # de quyet dinh co trigger CR that hay khong. Danh sach THIEU cell ma ho
    # tuong la du con nguy hiem hon loi 500 - loi thi ho biet ma hoi, con thieu
    # am tham thi khong.
    so_cell_ngoai_pham_vi: int = 0
    cell_ngoai_pham_vi: list[str] = []
    # Ban CHI TIET (V8, 09/2026) - THEM MOI song song, KHONG doi 2 field tren.
    # Xem CellNgoaiPhamViChiTiet.
    cell_ngoai_pham_vi_chi_tiet: list[CellNgoaiPhamViChiTiet] = []
    # OSS se dung (Giai doan 1 buoc 2, 27/09/2026) - None khi KHONG con cell
    # nao route duoc OSS nao (xem TriggerCrUseCase.PlanResult.oss_instance).
    oss_se_dung: OssSeDung | None = None
    # 2 field OPTIONAL THEM (BUOC 4b, 08/10/2026, yeu cau truc tiep user) -
    # CHI co gia tri o nhanh HO (None/[] cho nhanh CDS).
    # (nguon_du_lieu: str | None - DA BO 14/10/2026, yeu cau truc tiep user:
    # khong muon hien dong nay tren man xem truoc - xem docs/BUSINESS_RULES.md).
    x_co: list[str] = []
    quan_he_day_du: list[dict] = []
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - du lieu ban do (X/L1/L2/
    # tram bi anh huong/duong bao) - None cho nhanh CDS.
    ban_do: dict | None = None
    # THEM cho FE (yeu cau truc tiep user) - sector cua X duoi N_MIN_HO_SECTOR
    # (it du lieu HO, van xu ly nhung canh bao - xem ho_cell_selector.py). Rong
    # neu khong co sector nao/nhanh CDS.
    sectors_it_du_lieu: list[int] = []
