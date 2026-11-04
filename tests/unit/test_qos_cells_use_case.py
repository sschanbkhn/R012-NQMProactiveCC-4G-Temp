"""
Unit test cho GetQosCellsUseCase + GET /sessions/{id}/qos-cells (04092026).
MOCK gateway/repo, KHONG goi CTS that.

Trong tam: endpoint nay sinh ra DE FE THOI TU TINH LAI LUAT. Neu no cho ket
qua khac XuatPhieuUseCase thi khong giai quyet duoc gi - chi doi cho lech tu FE
sang BE. Vi vay test quan trong nhat la
test_qos_cells_va_danh_gia_qos_cell_cho_CUNG_ket_luan().
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import main
from application.get_qos_cells_use_case import GetQosCellsUseCase
from application.xuat_phieu_use_case import danh_gia_qos_tu_diem
from domain.entities.cr_session import CrSession, CrStatus
from domain.errors import CrSessionNotFoundError
from domain.services.evaluation_service import MUC_TOI_THIEU, EvaluationService
from fastapi.testclient import TestClient
from infrastructure.dependencies import get_qos_cells_use_case

SESSION_ID = 2644
EXECUTED_AT = datetime(2026, 8, 18, 7, 7, tzinfo=timezone.utc)
_CR_DAY = datetime(2026, 8, 18)


def _diem(offset_dau: int, values: list[float]) -> list[dict]:
    """Diem QoS 1 gia tri/ngay, dang giong CTS tra ve."""
    return [
        {"time": (_CR_DAY + timedelta(days=offset_dau + i)).strftime("%Y-%m-%dT00:00:00Z"), "qos": v}
        for i, v in enumerate(values)
    ]


def _use_case(theo_cell: dict, snapshot_repo=None):
    """theo_cell: {cell_name: (before_values, after_values)}"""
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = CrSession(
        id=SESSION_ID,
        tram_id="111474",
        action="shutdown",
        status=CrStatus.DONE,
        plan_name="plan_test",
        executed_at=EXECUTED_AT,
    )
    affected = AsyncMock()
    affected.get_by_cr_session_id.return_value = [{"cell_name": c} for c in theo_cell]

    sparkline = AsyncMock()

    async def _execute(cell_name, from_dt=None, to_dt=None):
        before, after = theo_cell[cell_name]
        return _diem(-7, before) if from_dt < _CR_DAY else _diem(1, after)

    sparkline.execute.side_effect = _execute

    uc = GetQosCellsUseCase(session_repo, affected, sparkline, EvaluationService(), snapshot_repo)
    return uc, sparkline


def _theo_ten(ket_qua):
    return {r.cell_name: r for r in ket_qua}


# === TRONG TAM: khong duoc lech voi duong xuat phieu ===


async def test_qos_cells_va_danh_gia_qos_cell_cho_CUNG_ket_luan():
    """CA HAI duong PHAI cho cung ket luan tren cung so lieu.

    Neu lech, endpoint nay vo nghia - chi doi cho lech tu FE sang BE."""
    bo_so_lieu = {
        "C_DAT_DELTA": ([5.0] * 7, [4.95] * 7),  # tut it, tren san -> PASS
        "C_DAT_BIEN_DELTA": ([4.83] * 7, [4.33] * 7),  # tut DUNG 0.5 -> PASS (bien)
        "C_FAIL_DELTA": ([4.83] * 7, [3.83] * 7),  # tut 1.0 > 0.5 -> FAIL
        "C_FAIL_SAN": ([2.33] * 7, [2.00] * 7),  # 2.00 < 3.0 -> FAIL du tut it
        "C_THIEU": ([5.0] * 3, [4.0] * 3),  # < 5 ngay -> INSUFFICIENT_DATA
    }
    uc, _ = _use_case(bo_so_lieu)

    qua_endpoint = _theo_ten(await uc.execute(SESSION_ID))

    ev = EvaluationService()
    for ten, (before, after) in bo_so_lieu.items():
        truc_tiep = danh_gia_qos_tu_diem(_diem(-7, before), _diem(1, after), ev)
        assert qua_endpoint[ten].qos_eval.result == truc_tiep.qos_eval.result, (
            f"{ten}: qos-cells={qua_endpoint[ten].qos_eval.result} "
            f"nhung duong xuat phieu={truc_tiep.qos_eval.result}"
        )
        assert qua_endpoint[ten].qos_eval.avg_after == truc_tiep.qos_eval.avg_after


async def test_cell_117449_van_PASS_theo_luat_moi_nhung_LY_DO_KHAC():
    """Ca THAT: 4.83 -> 4.33, tut DUNG 0.50.

    Luat cu: PASS nho ve CUU (avg_after 4.33 >= 4.0) du tut 0.50 > 0.2.
    Luat moi: PASS vi tut DUNG 0.50 - KHONG qua nguong 0.5 (bien) - VA
    avg_after 4.33 >= 3.0. Cung ket qua, 2 ly do hoan toan khac nhau."""
    uc, _ = _use_case({"4G-TEST-117449": ([4.83] * 7, [4.33] * 7)})

    r = _theo_ten(await uc.execute(SESSION_ID))["4G-TEST-117449"]

    assert r.qos_eval.avg_after >= MUC_TOI_THIEU
    assert round(r.qos_eval.avg_before - r.qos_eval.avg_after, 2) == 0.50, "tut DUNG bien"
    assert r.qos_eval.result == "PASS"


async def test_tut_qua_bien_mot_chut_thi_FAIL():
    # Doi xung voi test tren: tut 0.51 > 0.5 -> KHONG DAT.
    uc, _ = _use_case({"C1": ([4.83] * 7, [4.32] * 7)})

    r = _theo_ten(await uc.execute(SESSION_ID))["C1"]

    assert r.qos_eval.result == "FAIL"
    assert r.qos_eval.ly_do_khong_dat == "TUT_QUA_NHIEU"


async def test_duoi_san_thi_FAIL_du_tut_it():
    # Ca THAT 115560: 2.33 -> 2.00, tut chi 0.33 nhung dang o muc kem.
    uc, _ = _use_case({"C_KEM": ([2.33] * 7, [2.00] * 7)})

    r = _theo_ten(await uc.execute(SESSION_ID))["C_KEM"]

    assert r.qos_eval.result == "FAIL"
    assert r.qos_eval.ly_do_khong_dat == "DUOI_MUC_TOI_THIEU"


async def test_delta_theo_CHIEU_TOAN_HOC_duong_la_tut():
    # SUA 03/10/2026: delta = avg_before - avg_after, DUONG = tut (truoc day
    # AM = tut) - xem domain/services/evaluation_service.py muc "SUA
    # 03/10/2026". Doi xung voi QoeCellEvaluation.delta - 2 bang canh nhau
    # tren UI phai cung quy uoc dau, neu khong FE ve mui ten nguoc chieu o 1
    # trong 2 bang.
    uc, _ = _use_case({"C1": ([5.0] * 7, [4.0] * 7)})

    r = _theo_ten(await uc.execute(SESSION_ID))["C1"]

    assert r.delta == pytest.approx(1.0)


async def test_thieu_du_lieu_1_cell_khong_lam_hong_cell_khac():
    uc, _ = _use_case({"C_TOT": ([5.0] * 7, [3.0] * 7), "C_THIEU": ([5.0] * 2, [3.0] * 2)})

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert ket_qua["C_TOT"].qos_eval.result == "FAIL"
    assert ket_qua["C_THIEU"].qos_eval.result == "INSUFFICIENT_DATA"


async def test_cell_loi_CTS_VAN_TRA_VE_voi_INSUFFICIENT_DATA():
    """SUA 04092026: truoc day cell loi bi BO HAN khoi mang.

    Day la duong DOC - bo cell di thi bang QoS va bang QoE canh nhau tren UI co
    SO DONG KHAC NHAU, nguoi dung khong biet cell dau mat."""
    uc, sparkline = _use_case({"C_OK": ([5.0] * 7, [3.0] * 7), "C_LOI": ([5.0] * 7, [3.0] * 7)})

    async def _execute(cell_name, from_dt=None, to_dt=None):
        if cell_name == "C_LOI":
            raise RuntimeError("CTS timeout")
        return _diem(-7, [5.0] * 7) if from_dt < _CR_DAY else _diem(1, [3.0] * 7)

    sparkline.execute.side_effect = _execute

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert "C_OK" in ket_qua
    assert "C_LOI" in ket_qua, "cell loi PHAI van co trong mang"
    assert ket_qua["C_LOI"].qos_eval.result == "INSUFFICIENT_DATA"
    assert ket_qua["C_LOI"].so_ngay_before == 0
    assert ket_qua["C_LOI"].so_ngay_after == 0
    assert ket_qua["C_LOI"].qos_eval.avg_before is None
    assert ket_qua["C_LOI"].delta is None
    # Cell tot KHONG bi anh huong
    assert ket_qua["C_OK"].qos_eval.result == "FAIL"


async def test_qos_va_qoe_tra_CUNG_SO_DONG_cho_cung_session():
    """2 bang nam canh nhau tren UI - so dong lech la nguon hieu nham.

    Gia lap CTS hong TOAN BO: ke ca vay, qos-cells van phai tra du so cell
    cua session (giong qoe-cells von luon tra du)."""
    cells = {f"C{i}": ([5.0] * 7, [3.0] * 7) for i in range(5)}
    uc, sparkline = _use_case(cells)
    sparkline.execute.side_effect = RuntimeError("CTS chet hoan toan")

    ket_qua = await uc.execute(SESSION_ID)

    assert len(ket_qua) == len(cells), "phai tra DU so cell du CTS hong"
    assert all(r.qos_eval.result == "INSUFFICIENT_DATA" for r in ket_qua)


# === SO REQUEST CTS ===


async def test_so_request_CTS_la_2_moi_cell():
    # CTS tinh theo CELL (khac CEM tinh theo NGAY) - phai do de biet chi phi
    # that khi bang co 17 cell.
    uc, sparkline = _use_case({f"C{i}": ([5.0] * 7, [3.0] * 7) for i in range(5)})

    await uc.execute(SESSION_ID)

    assert sparkline.execute.await_count == 10, "5 cell x 2 cua so"


async def test_snapshot_du_thi_KHONG_goi_CTS_cho_cell_do():
    from datetime import date

    rows = []
    for i in range(7):
        rows.append({"cell_name": "C_CACHE", "snapshot_date": date(2026, 8, 11) + timedelta(days=i),
                     "qos_score": 5.0, "period": "before"})
        rows.append({"cell_name": "C_CACHE", "snapshot_date": date(2026, 8, 19) + timedelta(days=i),
                     "qos_score": 3.0, "period": "after"})
    repo = AsyncMock()
    repo.get_by_session_id.return_value = rows
    repo.dem_ngay_theo_cell.return_value = {("C_CACHE", "before"): 7, ("C_CACHE", "after"): 7}

    uc, sparkline = _use_case({"C_CACHE": ([5.0] * 7, [3.0] * 7)}, snapshot_repo=repo)
    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert sparkline.execute.await_count == 0, "du snapshot ma van goi CTS"
    assert ket_qua["C_CACHE"].tu_cache is True
    assert ket_qua["C_CACHE"].qos_eval.avg_before == 5.0
    assert ket_qua["C_CACHE"].qos_eval.avg_after == 3.0


async def test_cell_thieu_snapshot_van_goi_CTS_RIENG_no():
    # Kiem THEO TUNG CELL: cell co cache khong phai tra gia cho cell thieu cache.
    from datetime import date

    rows = [
        {"cell_name": "C_CACHE", "snapshot_date": date(2026, 8, 11) + timedelta(days=i),
         "qos_score": 5.0, "period": "before"} for i in range(7)
    ] + [
        {"cell_name": "C_CACHE", "snapshot_date": date(2026, 8, 19) + timedelta(days=i),
         "qos_score": 3.0, "period": "after"} for i in range(7)
    ]
    repo = AsyncMock()
    repo.get_by_session_id.return_value = rows
    repo.dem_ngay_theo_cell.return_value = {
        ("C_CACHE", "before"): 7, ("C_CACHE", "after"): 7,
        ("C_THIEU", "before"): 7, ("C_THIEU", "after"): 3,  # thieu ve after
    }

    uc, sparkline = _use_case(
        {"C_CACHE": ([5.0] * 7, [3.0] * 7), "C_THIEU": ([5.0] * 7, [3.0] * 7)}, snapshot_repo=repo
    )
    await uc.execute(SESSION_ID)

    assert sparkline.execute.await_count == 2, "chi goi cho C_THIEU (2 cua so)"


async def test_snapshot_repo_loi_thi_van_goi_CTS_khong_vo():
    repo = AsyncMock()
    # SUA 18/10/2026: duong doc snapshot gio la get_by_session_id() (khong con
    # dem_ngay_theo_cell) - gia lap loi DUNG ham dang duoc goi.
    repo.get_by_session_id.side_effect = RuntimeError("DB down")
    uc, sparkline = _use_case({"C1": ([5.0] * 7, [3.0] * 7)}, snapshot_repo=repo)

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert sparkline.execute.await_count == 2
    assert ket_qua["C1"].qos_eval.result == "FAIL"


# === Edge case ===


async def test_session_khong_ton_tai_raise_not_found():
    uc, _ = _use_case({})
    uc._session_repo.get_by_id.return_value = None  # noqa: SLF001

    with pytest.raises(CrSessionNotFoundError):
        await uc.execute(SESSION_ID)


async def test_session_chua_chay_CR_raise_value_error():
    uc, _ = _use_case({})
    uc._session_repo.get_by_id.return_value = CrSession(  # noqa: SLF001
        id=SESSION_ID, tram_id="111474", action="shutdown",
        status=CrStatus.FAILED, plan_name=None, executed_at=None,
    )

    with pytest.raises(ValueError, match="chua co executed_at"):
        await uc.execute(SESSION_ID)


async def test_session_khong_co_cell_tra_mang_rong():
    uc, sparkline = _use_case({})

    assert await uc.execute(SESSION_ID) == []
    assert sparkline.execute.await_count == 0


# === ROUTER ===


class TestRouter:
    def test_tra_dung_hinh_dang_giong_qoe_cells(self):
        uc = AsyncMock()

        class _R:
            cell_name = "4G-TEST-117449"
            delta = -0.5

            class qos_eval:  # noqa: N801
                avg_before = 4.83
                avg_after = 4.33
                result = "PASS"
                diem_thap_nhat_sau = 4.0
                so_ngay_dat_sau = 7

            so_ngay_before = 7
            so_ngay_after = 7

        # Router goi danh_gia_kem_cua_so() (04092026), khong con execute().
        uc.danh_gia_kem_cua_so.return_value = ([_R()], {"ngay_cr": date(2026, 8, 13), "before_from": datetime(2026, 8, 6), "before_to": datetime(2026, 8, 12), "after_from": datetime(2026, 8, 14), "after_to": datetime(2026, 8, 20)})
        main.app.dependency_overrides[get_qos_cells_use_case] = lambda: uc
        try:
            resp = TestClient(main.app).get(f"/api/v1/sessions/{SESSION_ID}/qos-cells")
            assert resp.status_code == 200
            body = resp.json()
            assert body["cr_session_id"] == SESSION_ID
            assert body["total"] == 1
            item = body["data"][0]
            # Dung BO TRUONG voi qoe-cells - 2 bang canh nhau tren UI.
            assert set(item) == {
                "cell_name", "avg_before", "avg_after", "delta",
                "so_ngay_before", "so_ngay_after", "ket_qua",
                "diem_thap_nhat_sau", "so_ngay_dat_sau",
            }
            assert item["ket_qua"] == "PASS"
            assert item["avg_after"] == 4.33
        finally:
            main.app.dependency_overrides.clear()


# === VIEC 2: message DAT_KHONG_XUAT phai neu DUNG VE nao lam cell dat ===
#
# Cau cu hardcode "chenh lech TB truoc-sau <= 0.2" cho MOI truong hop dat.
# Voi cell 117449 (chenh 0.50) nguoi doc thay "chenh 0.50 ma bao <= 0.2" ->
# tuong he thong mau thuan voi chinh no.


def _ly_do(before: list[float], after: list[float]) -> str:
    from application.xuat_phieu_use_case import _cau_ly_do_dat  # noqa: PLC2701

    return _cau_ly_do_dat(EvaluationService().evaluate(before, after, threshold=-0.5))


def test_message_neu_CA_HAI_so_lam_cell_dat():
    # Tu 04092026 PASS = qua CA HAI dieu kien, nen cau chu phai neu ca hai -
    # khong con chuyen "dat nho ve nao".
    cau = _ly_do([5.0] * 7, [4.95] * 7)
    assert "TB sau 4.95 >= 3.0" in cau
    assert "chenh lech TB truoc-sau 0.05 <= 0.5" in cau


def test_message_o_bien_van_neu_dung_2_so():
    cau = _ly_do([4.83] * 7, [4.33] * 7)  # tut DUNG 0.5
    assert "TB sau 4.33 >= 3.0" in cau
    assert "0.50 <= 0.5" in cau
    # KHONG duoc noi "<= 0.2" - nguong cu, da doi
    assert "<= 0.2" not in cau


def test_message_khong_bia_so_khi_thieu_du_lieu():
    cau = _ly_do([], [])
    assert "Cell dat tieu chi QoS" in cau
    assert "chenh lech" not in cau


# === VIEC 3: 3 trang thai KHONG_XUAT_* luon la NGHIEP_VU ===


@pytest.mark.parametrize(
    "trang_thai",
    ["KHONG_XUAT_DA_CO_PHIEU_THANG", "KHONG_XUAT_VUOT_GIOI_HAN", "KHONG_XUAT_THIEU_DU_LIEU"],
)
def test_3_trang_thai_khong_xuat_la_NGHIEP_VU(trang_thai):
    from domain.services.phan_loai_loi_cts import phan_loai_loi_cts

    # Ke ca khi error_message rong: ban than trang thai da noi day du y nghia.
    assert phan_loai_loi_cts(None, trang_thai) == "NGHIEP_VU"
    # Va ke ca khi error_message la ghi chu he thong (khong phai loi CTS).
    assert phan_loai_loi_cts("Ngoai top 10 cell te nhat cua session", trang_thai) == "NGHIEP_VU"


def test_HET_LUOT_THU_van_phan_loai_theo_noi_dung():
    # CO Y khac 3 cai tren: cell nay DA POST that va that bai 3 lan,
    # error_message la LOI THAT tu CTS.
    from domain.services.phan_loai_loi_cts import phan_loai_loi_cts

    assert phan_loai_loi_cts("Bad Cell X dang xu ly cua thang 202608", "KHONG_XUAT_HET_LUOT_THU") == "NGHIEP_VU"
    assert phan_loai_loi_cts('{"title":"validation errors"}', "KHONG_XUAT_HET_LUOT_THU") == "KY_THUAT"


def test_khong_truyen_trang_thai_thi_hanh_vi_cu_khong_doi():
    from domain.services.phan_loai_loi_cts import phan_loai_loi_cts

    assert phan_loai_loi_cts(None) is None
    assert phan_loai_loi_cts("Bad Cell X dang xu ly cua thang 202608") == "NGHIEP_VU"
    assert phan_loai_loi_cts("timeout") == "KY_THUAT"


# === 3 truong CUA SO (04092026) ===
# QoS va QoE dung CUNG cong thuc cua so nhung SO NGAY THUC TE co du lieu thuong
# lech nhau (CTS tre 1 ngay, CEM tre 2 ngay + lo thung). Do that session 1811:
# QoS 7/6 ngay, QoE 6/7 ngay tren CA 14 cell. FE can biet cua so goc de hien
# "6/7 ngay (14-20/08)" thay vi chi mot con so troi.


async def test_cua_so_tinh_dung_theo_ngay_CR_GMT7():
    uc, _ = _use_case({"C1": ([5.0] * 7, [3.0] * 7)})

    _, cs = await uc.danh_gia_kem_cua_so(SESSION_ID)

    # executed_at 18/08 07:07 UTC = 14:07 GMT+7 -> ngay CR 18/08
    assert cs["ngay_cr"] == date(2026, 8, 18)
    assert cs["before_from"].date() == date(2026, 8, 11)
    assert cs["before_to"].date() == date(2026, 8, 17)
    assert cs["after_from"].date() == date(2026, 8, 19)
    assert cs["after_to"].date() == date(2026, 8, 25)


async def test_cua_so_QoS_va_QoE_dung_CHUNG_ham_nen_GIONG_HET():
    # Neu 2 ben tu tinh rieng thi se lech nhau vao mot ngay nao do - da xay ra
    # 2 lan voi luat danh gia.
    from application.get_qoe_cells_use_case import cua_so_danh_gia as cs_qoe
    from application.xuat_phieu_use_case import cua_so_danh_gia as cs_qos

    assert cs_qoe is cs_qos, "2 use case phai dung CUNG MOT ham tinh cua so"


async def test_cua_so_khong_lech_ngay_voi_CR_chay_khung_UTC_toi():
    # Bug C1.4-fix8: lay .date() thang tren UTC se lech 1 ngay voi CR chay
    # trong khung UTC 17:00-23:59 (= sang hom sau GMT+7).
    from application.xuat_phieu_use_case import cua_so_danh_gia

    cs = cua_so_danh_gia(datetime(2026, 8, 18, 17, 30, tzinfo=timezone.utc))
    assert cs["ngay_cr"] == date(2026, 8, 19), "17:30 UTC = 00:30 GMT+7 ngay hom sau"


def test_router_tra_3_truong_cua_so():
    uc = AsyncMock()

    class _R:
        cell_name = "C1"
        delta = -0.5

        class qos_eval:  # noqa: N801
            avg_before, avg_after, result = 4.83, 4.33, "PASS"
            diem_thap_nhat_sau, so_ngay_dat_sau = 4.0, 7

        so_ngay_before, so_ngay_after = 7, 6

    uc.danh_gia_kem_cua_so.return_value = (
        [_R()],
        {
            "ngay_cr": date(2026, 8, 13),
            "before_from": datetime(2026, 8, 6),
            "before_to": datetime(2026, 8, 12),
            "after_from": datetime(2026, 8, 14),
            "after_to": datetime(2026, 8, 20),
        },
    )
    main.app.dependency_overrides[get_qos_cells_use_case] = lambda: uc
    try:
        body = TestClient(main.app).get(f"/api/v1/sessions/{SESSION_ID}/qos-cells").json()
        assert body["ngay_cr"] == "2026-08-13"
        assert body["cua_so_before"] == {"tu": "2026-08-06", "den": "2026-08-12"}
        assert body["cua_so_after"] == {"tu": "2026-08-14", "den": "2026-08-20"}
        # Cua so o CAP RESPONSE, KHONG lap lai trong tung cell
        assert "cua_so_before" not in body["data"][0]
        # so_ngay van o cap cell - do la cho FE phat hien lech
        assert body["data"][0]["so_ngay_before"] == 7
        assert body["data"][0]["so_ngay_after"] == 6
    finally:
        main.app.dependency_overrides.clear()


# === HAU KIEM = DUNG CELL ANH HUONG DA LUU (18/10/2026) ===
# Bao loi that tram 4G-TXN250M-HNI: nghi bang hau kiem lay cell khac danh sach
# anh huong. Chot: bang hau kiem PHAI la cr_affected_cells cua session, 1-1,
# giu thu tu, cell khong co du lieu van giu dong.

_16_CELL = [f"4G-TXN{n:03d}M{s}-HNI" for n, s in [
    (90, 51), (90, 11), (407, 41), (407, 51), (407, 11), (92, 42), (96, 42), (96, 52),
    (96, 12), (12, 41), (12, 11), (92, 52), (92, 12), (92, 32), (250, 11), (250, 21),
]]


async def test_16_cell_anh_huong_ra_DUNG_16_dong_cung_ten_cung_thu_tu():
    uc, _ = _use_case({c: ([4.0] * 7, [4.0] * 7) for c in _16_CELL})

    ket_qua = await uc.execute(SESSION_ID)

    assert [r.cell_name for r in ket_qua] == _16_CELL


async def test_1_cell_khong_co_du_lieu_VAN_co_dong_THIEU_DU_LIEU():
    theo_cell = {c: ([4.0] * 7, [4.0] * 7) for c in _16_CELL}
    theo_cell[_16_CELL[5]] = ([], [])  # CTS khong tra diem nao cho cell nay
    uc, _ = _use_case(theo_cell)

    ket_qua = await uc.execute(SESSION_ID)

    assert len(ket_qua) == 16
    assert ket_qua[5].cell_name == _16_CELL[5]
    assert ket_qua[5].qos_eval.result == "INSUFFICIENT_DATA"
    assert ket_qua[5].so_ngay_after == 0


# === MOT NGUON SO LIEU (18/10/2026) ===
# Session 10707: snapshot QoS chi 6 ngay sau (luu luc job danh gia 13/10), UI
# goi CTS live ra 7 ngay -> so khac file/phieu. Co snapshot (du thieu) -> dung
# snapshot, KHONG goi CTS; tra ngay chup cho FE.


async def test_snapshot_THIEU_ngay_VAN_dung_snapshot_khong_goi_CTS_va_tra_ngay_chup():
    from datetime import date

    chup = datetime(2026, 10, 13, 1, 12, tzinfo=timezone.utc)  # 08:12 GMT+7
    rows = [
        {"cell_name": "C6", "snapshot_date": date(2026, 9, 28) + timedelta(days=i),
         "qos_score": 4.0, "period": "before", "created_at": chup} for i in range(6)
    ] + [
        {"cell_name": "C6", "snapshot_date": date(2026, 10, 6) + timedelta(days=i),
         "qos_score": 4.0, "period": "after", "created_at": chup} for i in range(6)
    ]
    repo = AsyncMock()
    repo.get_by_session_id.return_value = rows
    uc, sparkline = _use_case({"C6": ([1.0] * 7, [1.0] * 7)}, snapshot_repo=repo)

    ket_qua, cs = await uc.danh_gia_kem_cua_so(SESSION_ID)

    assert sparkline.execute.await_count == 0, "co snapshot luc danh gia ma van goi CTS"
    assert ket_qua[0].so_ngay_after == 6
    assert ket_qua[0].qos_eval.avg_after == 4.0
    assert cs["ngay_chup_snapshot"] == date(2026, 10, 13)


async def test_khong_co_snapshot_goi_CTS_va_ngay_chup_None():
    repo = AsyncMock()
    repo.get_by_session_id.return_value = []
    uc, sparkline = _use_case({"C1": ([5.0] * 7, [3.0] * 7)}, snapshot_repo=repo)

    _, cs = await uc.danh_gia_kem_cua_so(SESSION_ID)

    assert sparkline.execute.await_count == 2
    assert cs["ngay_chup_snapshot"] is None
