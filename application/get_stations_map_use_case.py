"""
GetStationsMapUseCase - GET /stations/map?ma_tinh=... (BUOC 4c, 10/10/2026,
yeu cau truc tiep user) - tra TOAN BO tram co toa do cua 1 tinh, kem co
toa_do_dung_chung (CRAN, xem domain/services/ho_delaunay.py::phan_loai_toa_do()).

HAM THUAN VE LOGIC, nhung CO I/O (goi IEnodebRepo) - khac domain/services/,
day la use case tang application/ (duoc phep goi repo qua port, ARCHITECTURE.md
SS9).

VI SAO TINH phan_loai_toa_do() TREN TOAN QUOC roi MOI loc theo tinh (khong
loc truoc roi tinh rieng cho tinh do): TOA_DO_DUNG_CHUNG phat hien qua TRUNG
TOA DO voi tram KHAC (CO THE o tinh khac, giap ranh) - tinh truoc tren tap da
loc hep se BO SOT cap trung toa do co 1 ben nam ngoai tinh dang xem, cho ra
ket qua SAI (tram that ra la CRAN nhung bi bao TIN_CAY vi khong thay "ban
trung" cua no).
"""

from domain.ports.outbound.repo_ports import IEnodebRepo
from domain.services.ho_delaunay import TOA_DO_DUNG_CHUNG, TramDiem, phan_loai_toa_do
from domain.services.loai_tram import loai_tram_tu_ten_tram
from domain.value_objects.vendor import chuan_hoa_vendor


class GetStationsMapUseCase:
    def __init__(self, enodeb_repo: IEnodebRepo):
        self._enodeb_repo = enodeb_repo

    async def execute(self, ma_tinh: str) -> list[list]:
        """Tra list cac row (dung thu tu voi StationsMapResponse.columns):
        [tram_id, ten, lat, lon, vendor, toa_do_dung_chung, loai_tram]."""
        tram_rows = await self._enodeb_repo.get_all_with_coords()

        tram_diem_list = [
            TramDiem(tram_id=r["tram_id"], tram_name=r["tram_name"], lat=r["latitude"], lon=r["longitude"])
            for r in tram_rows
        ]
        phan_loai = phan_loai_toa_do(tram_diem_list)

        ket_qua: list[list] = []
        for r in tram_rows:
            if r["ma_tinh"] != ma_tinh:
                continue
            ket_qua.append([
                r["tram_id"],
                r["tram_name"],
                r["latitude"],
                r["longitude"],
                chuan_hoa_vendor(r["ten_thiet_bi"]).value,
                phan_loai.get(r["tram_id"]) == TOA_DO_DUNG_CHUNG,
                # loai_tram THEM (11-12/10/2026) - CHI hien thi, xem dac ta
                # "Quyet dinh 11-12/10/2026" o domain/services/loai_tram.py.
                loai_tram_tu_ten_tram(r["tram_name"]),
            ])
        return ket_qua
