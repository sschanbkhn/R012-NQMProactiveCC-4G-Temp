"""
Schemas cho /stations endpoint.
Tu: TASK_LIST.md C1.1; API_CONTRACTS.md Section 6 (GET /stations)
"""

from pydantic import BaseModel


class StationItem(BaseModel):
    tram_id: str
    tram_name: str
    ten_quan_ly: str | None = None
    ma_csht: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    trang_thai: str
    cr_status: str | None = None
    cr_session_id: int | None = None

    # 2 truong THEM 15092026 (V2 buoc 3). CHI THEM, khong doi/xoa truong nao o
    # tren - FE dang dung ca 9 truong cu (FE types/index.ts:22-32).
    #
    # ma_tinh: ma tinh SAU sap nhap (34 gia tri), doc THANG tu cot tram.ma_tinh.
    # TUYET DOI KHONG suy tu hau to ten tram: hau to la ma TRUOC sap nhap (992
    # gia tri) va 22.021/58.230 dong (37,8%) LECH nhau - vd 601 tram ten *-HGG
    # nam duoi ma_tinh=TQG (Ha Giang nhap vao Tuyen Quang).
    #
    # Optional vi 56/58.230 dong co ma_tinh NULL (da do 13092026).
    ma_tinh: str | None = None

    # vendor: gia tri cua enum Vendor (domain/value_objects/vendor.py) - DA
    # CHUAN HOA, khong phai ten_thiet_bi tho tu DB. Xem chu y o
    # EnodebRepo.find_stations() ve ly do khong tra chuoi tho.
    #
    # Khai str | None (khong phai Vendor) de giu StationItem la DTO thuan cua
    # tang api/ - schema khong phu thuoc kieu domain, va OpenAPI sinh ra van la
    # string nhu 9 truong cu. Gia tri thuc te luon thuoc {NOKIA, ERICSSON,
    # HUAWEI, ZTE, UNKNOWN} vi repo luon di qua chuan_hoa_vendor().
    vendor: str | None = None

    # khu_vuc: KV1/KV2/KV3 (THEM 04/10/2026, yeu cau truc tiep user) - suy TU
    # ma_tinh qua domain/value_objects/khu_vuc.py::khu_vuc_tu_ma_tinh(), KHONG
    # phai cot rieng trong RIMS (RIMS khong co khai niem khu vuc). Optional
    # vi ma_tinh co the NULL hoac la (chua xac nhan trong bang) - xem chu y
    # day du o khu_vuc.py.
    khu_vuc: str | None = None


class StationListResponse(BaseModel):
    total: int
    page: int
    size: int
    data: list[StationItem]


class StationsMapResponse(BaseModel):
    """GET /stations/map?ma_tinh=... (BUOC 4c, 10/10/2026, yeu cau truc tiep
    user) - dang GON (mang, KHONG lap ten truong) vi 1 tinh co the toi
    ~6.200 tram (vd HNI) - list[dict] (lap ten truong 6 lan/tram) se lam JSON
    nang khong can thiet. "columns" liet ke THU TU field, "rows" la mang cac
    gia tri THEO DUNG thu tu do (giong CSV/DataFrame) - FE tu zip lai."""

    # loai_tram THEM (11-12/10/2026, yeu cau truc tiep user, PHAN LOAI TRAM +
    # DO ANH HUONG) - enum MACRO|IBS|SMALL_CELL|KHAC, xem
    # domain/services/loai_tram.py::loai_tram_tu_ten_tram(). CHI de HIEN THI -
    # KHONG doi cach tinh L1/L2 hien tai (quyet dinh 11-12/10/2026, do anh
    # huong de quyet sau).
    columns: list[str] = ["tram_id", "ten", "lat", "lon", "vendor", "toa_do_dung_chung", "loai_tram"]
    rows: list[list]
