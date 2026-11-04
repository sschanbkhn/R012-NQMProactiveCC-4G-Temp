"""
SaveCellClmPayload — 28 field, ten CHINH XAC theo API
POST /oss/tts/ticket/ticket-tts-api/ApiCTS/SaveCellClm.
Tu: yeu cau truc tiep user (KHOI 2/5 SaveCellClm) + curl mau CTS xac nhan
(D:\\Python_Project\\Script\\test_api_hn\\test_savecellclm.py).

Dat trong adapters/http/ (khong phai domain/) - day la DTO khop nguyen field
API ben ngoai (PascalCase, khong phai ten nghiep vu domain), ARCHITECTURE.md
SS9 domain/ CHI import stdlib nen pydantic khong duoc dung trong domain/.
"""

from pydantic import BaseModel


class SaveCellClmPayload(BaseModel):
    # ---- Ky bao cao ------------------------------------------------------
    Nam: int
    Thang: int

    # ---- Trang thai --------------------------------------------------
    # Spec ghi kieu Number (int) - KHAC curl mau CTS gui thu (string "1").
    # Lam theo spec (yeu cau truc tiep user), khong theo mau thu.
    TrangThai: int

    # ---- Dinh danh cell ---------------------------------------------------
    TenCell: str
    SiteName: str

    # ---- Cac chi tieu vi pham ---------------------------------------------
    # Qos/Qoe/Tsd/Ceitsd = String theo spec (Voice = Number).
    Qos: str
    Qoe: str
    Tsd: str
    Voice: int
    Ceitsd: str
    # SUA (do THAT bang POST that 11/08): spec ghi Number (int) nhung CTS TU CHOI
    # 400 voi thong bao ro rang:
    #   "$.SoChiTieuVP": "The JSON value could not be converted to System.String"
    # -> API that nhan STRING. Sau khi doi sang str, cung payload do POST tra 200.
    # Day la truong hop spec SAI so voi API that (cung dang bug doc/thuc te da gap
    # nhieu lan trong project: SHA-512 timezone, XML dateTime GMT+7, FAILED MOS).
    SoChiTieuVP: str

    # ---- Nguyen nhan / phuong an --------------------------------------------
    NguyenNhan: str
    PhuongAnXuLyDuKien: str
    MaPhuongAn: str

    # ---- Noi dung -----------------------------------------------------------
    NoiDung: str

    # ---- Vendor / nguoi cap nhat / cong nghe --------------------------------
    Vendor: str
    UserUpdatePa: str
    LoaiCongNghe: str

    # ---- Dia ly / ha tang -----------------------------------------------
    # ProvinceCode/WardCode: spec ghi Number nhung gia tri that la chu
    # ("HPG"/"HPG094") - de str, TODO xac nhan lai voi CTS.
    ProvinceCode: str
    WardCode: str
    BuildingCode: str
    BuildingName: str

    # ---- To chuc --------------------------------------------------------
    TtvtId: str
    TtvtName: str

    # ---- Loai tram --------------------------------------------------------
    LoaiTram: str
    BuildingTypeName: str

    # ---- Dia chi ------------------------------------------------------------
    Address: str

    # ---- Nguon du lieu --------------------------------------------------
    NguonSoLieu: str
