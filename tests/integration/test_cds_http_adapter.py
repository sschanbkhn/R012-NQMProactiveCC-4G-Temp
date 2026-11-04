"""
Integration test cho CdsHttpAdapter — goi CDS API THAT (gw-oneoss.vnpt.vn).
Tu: API_CONTRACTS.md SS1; TASK_LIST.md B6.2

Lich su: lan test dau (11072026) gap HTTP 500 lien tuc, ban dau tuong loi ha tang.
Sau khi doi chieu voi script thuc nghiem cua team (Script/Test_api_CDS/
test_cds_neighbors.py), xac nhan la BUG THAT trong cong thuc SHA-512 auth
(adapters/http/sha512_auth.py) - da fix. Tu day get_cell_neighbors() PHAI tra ve
200 OK that voi tram that "110548"/"4G-HKM005M-HNI" - khong con chap nhan
CdsApiError nhu truoc nua.
"""

from adapters.http.cds_http_adapter import CdsHttpAdapter

REAL_TRAM_ID = "110548"
REAL_TRAM_NAME = "4G-HKM005M-HNI"


async def test_get_cell_neighbors_goi_that_200_ok_parse_dung_cau_truc():
    adapter = CdsHttpAdapter()
    result = await adapter.get_cell_neighbors(REAL_TRAM_ID, REAL_TRAM_NAME, "shutdown")

    assert isinstance(result, list)
    assert len(result) > 0
    for huong in result:
        assert "huong_id" in huong
        assert "huong_name" in huong
        assert "cells" in huong
        assert len(huong["cells"]) > 0
        for cell in huong["cells"]:
            assert "cell_name" in cell
            assert "priority" in cell
            assert "status" in cell
