"""
GET /stations.
Tu: ARCHITECTURE.md Section 6.1; API_CONTRACTS.md Section 6 (GET /stations);
TASK_LIST.md C1.3
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from api.schemas.station_schemas import StationItem, StationListResponse, StationsMapResponse
from application.get_stations_map_use_case import GetStationsMapUseCase
from domain.ports.outbound.repo_ports import IEnodebRepo
from infrastructure.dependencies import get_enodeb_repo, get_stations_map_use_case

router = APIRouter()

# Sort server-side (22072026) - cung ly do/co che voi api/routers/sessions.py
# (Literal BAT BUOC whitelist, FastAPI tu tra 422 neu gia tri ngoai danh sach).
# Chi 3 cot: tram_id/tram_name/ma_tinh - da kiem tra ca 3 deu ton tai that
# tren models/tram.py truoc khi liet ke (khong doan/gia dinh ten cot).
_StationSortBy = Literal["tram_id", "tram_name", "ma_tinh"]
_SortOrder = Literal["asc", "desc"]

# vendor (THEM 04/10/2026, yeu cau truc tiep user) - Literal BAT BUOC (cung co
# che voi _StationSortBy o tren): FastAPI/Pydantic tu tra 422 neu gia tri
# ngoai 4 cai nay, KHONG can tu viet code kiem tra. Chi 4 gia tri THAT dang
# chay tren mang (xem domain/value_objects/vendor.py - khao sat 04/10/2026:
# NOKIA/ERICSSON/HUAWEI/ZTE, 0 gia tri la khac). KHONG dua UNKNOWN vao day:
# UNKNOWN la ket luan cua chuan_hoa_vendor() khi du lieu la (khong phai 1
# "vendor" nguoi dung co the chu dong loc theo), dua vao se gay hieu nham la
# loc duoc theo "nhung tram du lieu loi".
_VendorFilter = Literal["NOKIA", "ERICSSON", "HUAWEI", "ZTE"]

# khu_vuc (THEM 04/10/2026, yeu cau truc tiep user) - CHI 3 gia tri da xac
# nhan (domain/value_objects/khu_vuc.py), Literal BAT BUOC giong vendor o tren
# de FastAPI tu tra 422 neu gia tri ngoai KV1/KV2/KV3 (vd "KV4" go nham).
_KhuVucFilter = Literal["KV1", "KV2", "KV3"]


@router.get("/stations", response_model=StationListResponse)
async def list_stations(
    q: str | None = None,
    status: str | None = None,
    # vendor (THEM 04/10/2026) - list (KHONG phai 1 gia tri don) de nhan
    # NHIEU vendor cung luc qua lap lai tham so URL (?vendor=NOKIA&vendor=HUAWEI),
    # dung quy uoc chuan cua FastAPI cho "1 tham so, nhieu gia tri" (KHAC
    # cach "1 chuoi phan cach dau phay" - tranh phai tu parse/split rieng).
    # Query(default=None) BAT BUOC o day (khac q/status o tren khong can) vi
    # kieu list[...] can khai bao ro la query param lap lai, neu khong
    # FastAPI se hieu nham la request body.
    vendor: list[_VendorFilter] | None = Query(default=None),
    # khu_vuc (THEM 04/10/2026) - cung quy uoc lap lai tham so voi vendor o
    # tren (?khu_vuc=KV1&khu_vuc=KV3), loc o TANG DB (ma_tinh IN (...)).
    khu_vuc: list[_KhuVucFilter] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    sort_by: _StationSortBy | None = None,
    order: _SortOrder = "desc",
    enodeb_repo: IEnodebRepo = Depends(get_enodeb_repo),
) -> StationListResponse:
    offset = (page - 1) * size
    total = await enodeb_repo.count_stations(q, status, vendor, khu_vuc)
    rows = await enodeb_repo.find_stations(q, status, offset, size, sort_by, order, vendor, khu_vuc)
    return StationListResponse(total=total, page=page, size=size, data=[StationItem(**row) for row in rows])


# GET /stations/map (BUOC 4c, 10/10/2026, yeu cau truc tiep user) - toan bo
# tram co toa do cua 1 tinh, dang GON (xem StationsMapResponse) de phuc vu
# hien thi ban do - KHAC /stations o tren (phan trang, nhieu field, phuc vu
# bang danh sach). PHAI dat o DAY, TRUOC moi route /stations/{...} tuong lai
# (hien chua co) de FastAPI khong hieu nham "map" la 1 gia tri path param.
@router.get("/stations/map", response_model=StationsMapResponse)
async def get_stations_map(
    ma_tinh: str = Query(..., min_length=3, max_length=3),
    use_case: GetStationsMapUseCase = Depends(get_stations_map_use_case),
) -> StationsMapResponse:
    rows = await use_case.execute(ma_tinh)
    return StationsMapResponse(rows=rows)
