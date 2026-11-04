"""
GET /hau-kiem/excel tren DU LIEU THAT session 10707 (4G-TXN250M-HNI, CR
05/10/2026) - doi chieu bang file mau user cung cap 18/10/2026.

Session da danh gia -> doc snapshot, KHONG goi CTS/CEM (so lieu co dinh).
"""

from io import BytesIO

import httpx
import pytest
from openpyxl import load_workbook

import main

# cell -> (QoS TB, QoS lech, QoS DG, QoE TB, QoE lech, QoE >=3, phieu HT, phieu HeThong)
# So file mau lam tron 2 chu so. TXN092M12 QoS: file "Khong dat" (luat cu, lech
# float 0.5000000000000004) -> nay "Dat" theo luat lam tron 18/10/2026.
_MONG_DOI = {
    "4G-TXN090M51-HNI": (4.83, 0.17, "Dat", 4.71, -0.14, "7/7", None, None),
    "4G-TXN407M41-HNI": (2.83, 0.17, "Khong dat", 3.86, -0.29, "7/7", "32166", None),
    "4G-TXN092M32-HNI": (1.17, 0.33, "Khong dat", 4.14, 0.43, "6/7", "32165", None),
    "4G-TXN092M12-HNI": (3.67, 0.5, "Dat", 4.57, 0.14, "7/7", None, "32084"),
    "4G-TXN096M52-HNI": (4.17, 0.67, "Khong dat", 5.0, -0.43, "7/7", None, "32167"),
    "4G-TXN012M41-HNI": (3.33, 0.5, "Dat", 3.86, 0.14, "7/7", None, None),
}
_CELL_CR = {"4G-TXN092M12-HNI", "4G-TXN090M11-HNI", "4G-TXN096M12-HNI",
            "4G-TXN092M32-HNI", "4G-TXN407M11-HNI", "4G-TXN012M11-HNI"}


async def test_excel_session_10707_khop_bang_doi_chieu():
    # AsyncClient + ASGITransport (KHONG TestClient): TestClient chay app tren
    # event loop RIENG, dung lai pool asyncpg da gan loop cua pytest -> loi
    # "attached to a different loop" khi chay chung suite.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        res = await c.get("/api/v1/hau-kiem/excel?session_id=10707")
    if res.status_code == 404:
        pytest.skip("DB khong co session 10707")
    assert res.status_code == 200
    # DOT 2: 1 session -> hau_kiem_<ma_tram>_<ten_tram>_<ts>.xlsx + filename* UTF-8.
    assert 'filename="hau_kiem_114664_4G-TXN250M-HNI_' in res.headers["content-disposition"]
    assert "filename*=UTF-8''hau_kiem_114664_4G-TXN250M-HNI_" in res.headers["content-disposition"]

    ws = load_workbook(BytesIO(res.content))["Hau kiem"]
    gop = {str(m) for m in ws.merged_cells.ranges}
    # 19/10/2026: moi nhom QoS/QoE 7 cot (them TB truoc + so ngay truoc).
    assert {"A4:A17", "B4:B17", "A1:E1", "F1:W1", "G2:M2", "N2:T2", "U2:W2", "X1:X3"} <= gop
    assert ws["F1"].value == "HAU KIEM (Trung binh QoS, QoE 7 ngay truoc / sau CR)"
    dong = [r for r in ws.iter_rows(min_row=4, values_only=True) if r[3]]
    assert len(dong) == 14
    assert ws["A4"].value == "05/10/2026" and ws["B4"].value == "4G-TXN250M-HNI"

    theo_cell = {r[3]: r for r in dong}
    for cell, (qos_tb, qos_l, qos_dg, qoe_tb, qoe_l, qoe_3, ht, hethong) in _MONG_DOI.items():
        r = theo_cell[cell]
        assert (r[7], r[8], r[9]) == (qos_tb, qos_l, qos_dg), cell
        assert (r[14], r[15], r[19]) == (qoe_tb, qoe_l, qoe_3), cell
        # 19/10/2026: U Ma phieu | V Phuong an (thay 2 cot Hien truong/He thong).
        ma = ht or hethong
        assert (r[20], r[21]) == (ma, "Hien truong" if ht else "He thong" if hethong else None), cell
        if ma:
            assert r[22] == "SUCCESS", cell
        assert r[5] == cell  # F = cung cell D

    # Sheet "Phieu": dung cac phieu cua session 10707, cung bo cot voi
    # /phieu/excel (dung chung ham); ma phieu khop cot U sheet chinh.
    wb = load_workbook(BytesIO(res.content))
    assert wb.sheetnames == ["Hau kiem", "Phieu", "Chu giai"]
    ph = list(wb["Phieu"].iter_rows(min_row=2, values_only=True))
    assert ph and all(p[6] == 10707 for p in ph)
    assert {p[1] for p in ph if p[1]} == {r[20] for r in dong if r[20]}

    # Cot moi phai KHOP bang hau kiem tren man hinh (cung API FE goi) - 1 nguon
    # so lieu snapshot, Excel khong duoc ra so khac UI.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t") as c:
        qos = (await c.get("/api/v1/sessions/10707/qos-cells")).json()["data"]
        qoe = (await c.get("/api/v1/sessions/10707/qoe-cells")).json()["data"]
    def n7(n):
        return f"{n}/7" if n else None
    for bat_dau, ds in ((6, qos), (13, qoe)):
        for x in ds:
            r = theo_cell[x["cell_name"]]
            assert (r[bat_dau], r[bat_dau + 1], r[bat_dau + 2]) == (x["avg_before"], x["avg_after"], x["delta"]), x
            assert (r[bat_dau + 4], r[bat_dau + 5]) == (n7(x["so_ngay_before"]), n7(x["so_ngay_after"])), x
    # Cot E: chi cell co trong cell_params cua session, CUNG dong voi D.
    assert {r[3] for r in dong if r[4]} == _CELL_CR
    assert all(r[4] in (None, r[3]) for r in dong)
