"""
Unit test cho XuatPhieuUseCase — MOCK toan bo I/O bien ngoai (cr_phieu_repo/
cr_session_repo/cr_affected_cells_repo/enodeb_repo/qos_sparkline_use_case/
save_cell_clm_gateway), DUNG THAT EvaluationService (domain service thuan,
khong I/O - giong pattern tests/unit/test_evaluate_cr_use_case.py).
Tu: yeu cau truc tiep user (KHOI 3a/5 SaveCellClm + doi tieu chi QoS moi).
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from application.get_qoe_cells_use_case import QoeCellEvaluation
from application.xuat_phieu_use_case import (
    NGUON_QOE,
    TRANG_THAI_THIEU_DU_LIEU,
    XUAT_PHIEU_MAX_RETRY,
    XuatPhieuUseCase,
    _extract_phieu_id,
)
from domain.entities.cr_session import CrSession, CrStatus
from domain.errors import PhieuDaXoaError, QoeDataInsufficientError, SaveCellClmApiError
from domain.services.evaluation_service import EvaluationService, MetricEvaluation

# Response CTS THANH CONG mac dinh cho cac test khong quan tam ket qua POST.
# V2 (12/08): gateway KHONG con che do dry_run tra preview {url,headers,body} -
# goi la POST that, nen mock phai tra ve hinh dang response THAT.
_RESP_OK = {
    "status_code": 200,
    "isError": False,
    "code": "200",
    "message": "OK",
    "data": 19177,
    "totalRecord": 1,
}

SESSION_ID = 42
CELL_NAME = "4G-TEST-HNI"
TRAM_ID = "111139"

# executed_at UTC - chon gio KHONG lech ngay qua GMT+7 (10:00 UTC = 17:00 GMT+7,
# cung ngay) de test de doi chieu bang tay, khong lien quan bug C1.4-fix8 (da
# co test rieng o evaluate_cr_use_case).
EXECUTED_AT = datetime(2026, 7, 20, 10, 0, 0)
# cr_day_start (GMT+7, naive) - dung lam moc phan biet cuoc goi before/after
# trong side_effect cua qos_sparkline_use_case ben duoi.
_CR_DAY_START = datetime(2026, 7, 20)


def _points(dates: list[str], values: list[float]) -> list[dict]:
    return [{"time": f"{d}T00:00:00Z", "qos": v} for d, v in zip(dates, values)]


# 5 ngay rieng biet - du MIN_DAYS_REQUIRED=5 (EvaluationService).
_5_DATES_BEFORE = ["2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-18"]
_5_DATES_AFTER = ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25"]


def _make_session() -> CrSession:
    return CrSession(
        id=SESSION_ID,
        tram_id=TRAM_ID,
        action="shutdown",
        status=CrStatus.DONE,
        plan_name="R012_NQMProactiveCC_111139_20260720_100000",
        executed_at=EXECUTED_AT,
    )


def _make_use_case(
    cr_phieu_repo=None,
    cr_session_repo=None,
    cr_affected_cells_repo=None,
    enodeb_repo=None,
    qos_sparkline_use_case=None,
    save_cell_clm_gateway=None,
    before_points=None,
    after_points=None,
    # SUA 04/10/2026 (lo nhom bo sot QoE tren duong xuat tay) - mac dinh None
    # GIU NGUYEN moi test cu (execute() se tu bo qua danh gia QoE, dung y het
    # truoc sua). Test moi muon mo phong "QoE da co san qua snapshot/CEM" thi
    # tu truyen AsyncMock rieng (xem test_xuat_tay_tu_danh_gia_qoe_khi_chua_truyen).
    qoe_cells_use_case=None,
):
    # QUAN TRONG: chi set default khi caller KHONG tu truyen mock rieng - neu
    # khong se GHI DE cau hinh mock ma test da chu dong dat (bug tung gap khi
    # viet test nay lan dau, xem docs/DEV_LOG.md).
    if cr_phieu_repo is None:
        cr_phieu_repo = AsyncMock()
        cr_phieu_repo.get_by_session_cell.return_value = None
        # B9 (02092026) - PHAI dat tuong minh None: AsyncMock tra ve mot Mock
        # TRUTHY cho moi method chua khai bao, nen khong dat thi MOI test se roi
        # vao nhanh "cell da co phieu trong thang" va khong bao gio chay toi phan
        # dang test. Mac dinh cua bo test la "cell chua co phieu thang nay".
        cr_phieu_repo.get_success_cung_thang.return_value = None
        cr_phieu_repo.insert.return_value = {"id": 1}

    if cr_session_repo is None:
        cr_session_repo = AsyncMock()
        cr_session_repo.get_by_id.return_value = _make_session()

    if cr_affected_cells_repo is None:
        cr_affected_cells_repo = AsyncMock()
        cr_affected_cells_repo.get_by_cr_session_id.return_value = [
            {"cell_name": CELL_NAME, "tram_id": TRAM_ID, "huong_id": "11"}
        ]

    if enodeb_repo is None:
        enodeb_repo = AsyncMock()
        enodeb_repo.get_by_tram_id.return_value = {
            "tram_name": "4G-TEST001M-HNI",
            "ma_tinh": "HNI",
            "ma_csht": "CSHT-HNI-999",
            "ten_thiet_bi": "Nokia AirScale",
            "ten_quan_ly": "Cau Giay",
        }

    if qos_sparkline_use_case is None:
        # Mac dinh: KHONG DAT (before avg=5.0 cao han han after avg=1.9, delta
        # = 1.9-5.0=-3.1 << -0.2) - nhanh "xuat phieu" la nhanh PHO BIEN nhat
        # can test (ghep payload, check trung...).
        before_points = before_points or _points(_5_DATES_BEFORE, [5.0] * 5)
        after_points = after_points or _points(_5_DATES_AFTER, [2.0, 2.0, 2.0, 2.0, 1.5])

        async def _side_effect(cell_name, from_dt, to_dt):
            return before_points if from_dt < _CR_DAY_START else after_points

        qos_sparkline_use_case = AsyncMock()
        qos_sparkline_use_case.execute.side_effect = _side_effect

    if save_cell_clm_gateway is None:
        save_cell_clm_gateway = AsyncMock()
        save_cell_clm_gateway.save_cell_clm.return_value = dict(_RESP_OK)

    use_case = XuatPhieuUseCase(
        cr_phieu_repo=cr_phieu_repo,
        cr_session_repo=cr_session_repo,
        cr_affected_cells_repo=cr_affected_cells_repo,
        enodeb_repo=enodeb_repo,
        qos_sparkline_use_case=qos_sparkline_use_case,
        save_cell_clm_gateway=save_cell_clm_gateway,
        evaluation_service=EvaluationService(),  # domain service THAT, khong mock
        qoe_cells_use_case=qoe_cells_use_case,
    )
    return use_case, cr_phieu_repo, save_cell_clm_gateway


async def test_khong_dat_xuat_phieu_ghep_payload_dung_28_field():
    # before avg=5.0, after avg=1.9 -> delta=-3.1 < -0.2 -> KHONG DAT -> xuat.
    use_case, cr_phieu_repo, save_cell_clm_gateway = _make_use_case()

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert set(payload) == {
        "Nam", "Thang", "TrangThai", "TenCell", "SiteName", "Qos", "Qoe", "Tsd",
        "Voice", "Ceitsd", "SoChiTieuVP", "NguyenNhan", "PhuongAnXuLyDuKien",
        "MaPhuongAn", "NoiDung", "Vendor", "UserUpdatePa", "LoaiCongNghe",
        "ProvinceCode", "WardCode", "BuildingCode", "BuildingName", "TtvtId",
        "TtvtName", "LoaiTram", "BuildingTypeName", "Address", "NguonSoLieu",
    }
    assert payload["Nam"] == 2026
    assert payload["Thang"] == 7
    assert payload["TenCell"] == CELL_NAME
    assert payload["SiteName"] == "4G-TEST001M-HNI"
    assert payload["ProvinceCode"] == "HNI"
    assert payload["BuildingCode"] == "CSHT-HNI-999"
    assert payload["Vendor"] == "Nokia AirScale"
    assert payload["BuildingName"] == "Cau Giay"
    # SUA KY VONG 01092026: truoc day la "1.5". Van la MIN cua 5 diem after
    # (khong doi cach tinh), nhung gui di duoi dang SO NGUYEN - CTS khai Qos
    # la Int32 nullable, chuoi co dau cham thap phan bi tu choi 400. Test nay
    # chinh la bang chung qos_min CO THE la float (diem gia lap 1.5): tren du
    # lieu that hom nay Qos luon la so nguyen nen chua no, nhung duong code
    # thi mo san - dung cai lo hong da lam hong 39 phieu qua field Qoe.
    assert payload["Qos"] == "1"
    # str (KHONG phai int) - CTS tu choi 400 neu gui Number, do THAT bang POST that
    assert payload["SoChiTieuVP"] == "1"  # QoS KHONG DAT -> luon 1
    assert payload["Qoe"] == "0"
    assert payload["Ceitsd"] == "0"
    assert payload["TrangThai"] == 1
    assert payload["NguyenNhan"] == "NN15"
    # V5 (12/08): "1" -> "2" (gia tri nghiep vu do RNOC1 quy dinh)
    assert payload["PhuongAnXuLyDuKien"] == "2"
    assert result.trang_thai == "SUCCESS"
    assert result.cr_phieu_id == 1


async def test_dat_tieu_chi_khong_xuat_phieu():
    # SUA SO LIEU 04092026 (khong noi long assert): bo so cu 3.0 -> 2.9 co
    # avg_after 2.9 < MUC_TOI_THIEU (3.0) nen luat moi tra FAIL - test khong
    # con co lap duoc dieu no muon kiem (delta trong dung sai -> DAT).
    # Nang ca 2 ve len de avg_after qua san, GIU NGUYEN delta = -0.1.
    # before avg=4.0, after avg=3.9 -> delta=-0.1 >= -0.5 VA 3.9 >= 3.0 -> DAT.
    before_points = _points(_5_DATES_BEFORE, [4.0] * 5)
    after_points = _points(_5_DATES_AFTER, [3.9] * 5)
    use_case, cr_phieu_repo, save_cell_clm_gateway = _make_use_case(
        before_points=before_points, after_points=after_points
    )

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.trang_thai == "DAT_KHONG_XUAT"
    assert result.cr_phieu_id is None
    assert result.phieu_id is None
    assert result.already_exists is False
    save_cell_clm_gateway.save_cell_clm.assert_not_called()
    cr_phieu_repo.insert.assert_not_called()
    cr_phieu_repo.update_result.assert_not_called()


async def test_chenh_lech_gan_sat_nguong_van_dat():
    # Bien gan nguong 0.5 (SUA 04092026 tu 0.2). Khong dung CHINH XAC 0.5 -
    # so sanh float truc tiep voi hang so thap phan de bi sai so lam tron, xem
    # test rieng cho bien o tests/domain/test_evaluation_service.py.
    # delta = -0.49, trong nguong dung sai VA avg_after 3.51 >= 3.0 -> DAT.
    before_points = _points(_5_DATES_BEFORE, [4.0] * 5)
    after_points = _points(_5_DATES_AFTER, [3.51] * 5)  # delta = 3.51-4.0 = -0.49
    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=before_points, after_points=after_points
    )

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.trang_thai == "DAT_KHONG_XUAT"
    save_cell_clm_gateway.save_cell_clm.assert_not_called()


async def test_thieu_du_lieu_before_raise_khong_xuat_phieu():
    # BUOC 4 - chua du du lieu (before chi 3 ngay < MIN_DAYS_REQUIRED=5) -> raise,
    # KHONG xuat phieu, du after co du 5 ngay.
    before_points = _points(["2026-07-14", "2026-07-15", "2026-07-16"], [5.0, 5.0, 5.0])
    after_points = _points(_5_DATES_AFTER, [2.0] * 5)
    use_case, cr_phieu_repo, save_cell_clm_gateway = _make_use_case(
        before_points=before_points, after_points=after_points
    )

    with pytest.raises(QoeDataInsufficientError):
        await use_case.execute(SESSION_ID, CELL_NAME)

    save_cell_clm_gateway.save_cell_clm.assert_not_called()
    cr_phieu_repo.insert.assert_not_called()


async def test_thieu_du_lieu_after_raise_khong_xuat_phieu():
    before_points = _points(_5_DATES_BEFORE, [5.0] * 5)
    after_points = _points(["2026-07-21", "2026-07-22"], [2.0, 2.0])  # 2 ngay < 5
    use_case, cr_phieu_repo, save_cell_clm_gateway = _make_use_case(
        before_points=before_points, after_points=after_points
    )

    with pytest.raises(QoeDataInsufficientError):
        await use_case.execute(SESSION_ID, CELL_NAME)

    save_cell_clm_gateway.save_cell_clm.assert_not_called()
    cr_phieu_repo.insert.assert_not_called()


async def test_check_trung_da_co_phieu_success_khong_goi_gateway_lai():
    cr_phieu_repo = AsyncMock()
    # B9 - AsyncMock tra Mock TRUTHY cho method chua khai bao; khong dat None
    # thi test roi vao nhanh "da co phieu trong thang" va khong chay toi phan dang test
    cr_phieu_repo.get_success_cung_thang.return_value = None
    cr_phieu_repo.get_by_session_cell.return_value = {
        "id": 99, "trang_thai": "SUCCESS", "phieu_id": "PHIEU-OLD-001",
    }
    use_case, _, save_cell_clm_gateway = _make_use_case(cr_phieu_repo=cr_phieu_repo)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.already_exists is True
    assert result.cr_phieu_id == 99
    assert result.trang_thai == "SUCCESS"
    assert result.phieu_id == "PHIEU-OLD-001"
    save_cell_clm_gateway.save_cell_clm.assert_not_called()
    cr_phieu_repo.insert.assert_not_called()


async def test_da_co_phieu_khong_success_thi_thu_lai_khong_insert_moi():
    # Phieu cu bi FAILED/KHONG_XUAT_* (khac SUCCESS) - PHAI thu lai nhung KHONG duoc
    # insert() moi (se vi pham UNIQUE(cr_session_id, cell_name), KHOI 2/5) - tai
    # su dung id cu, chi update_result(). Data mac dinh cua _make_use_case() la
    # nhanh KHONG DAT (xuat phieu).
    cr_phieu_repo = AsyncMock()
    # B9 - AsyncMock tra Mock TRUTHY cho method chua khai bao; khong dat None
    # thi test roi vao nhanh "da co phieu trong thang" va khong chay toi phan dang test
    cr_phieu_repo.get_success_cung_thang.return_value = None
    cr_phieu_repo.get_by_session_cell.return_value = {
        "id": 55, "trang_thai": "FAILED", "phieu_id": None,
    }
    use_case, _, save_cell_clm_gateway = _make_use_case(cr_phieu_repo=cr_phieu_repo)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    cr_phieu_repo.insert.assert_not_called()
    save_cell_clm_gateway.save_cell_clm.assert_called_once()
    cr_phieu_repo.update_result.assert_called_once()
    assert cr_phieu_repo.update_result.call_args.args[0] == 55
    assert result.cr_phieu_id == 55
    assert result.already_exists is False


async def test_cell_co_phieu_da_xoa_tu_choi_409_khong_tao_lai():
    # XOA MEM (THEM 04/10/2026, quyet dinh 04/10/2026) - dong cu VAN CON trong
    # bang sau khi xoa (chi danh dau deleted_at), get_by_session_cell() VAN
    # THAY no. Phai chan NGAY, KHONG duoc roi xuong nhanh "thu lai" (se insert/
    # update_result tren dong da xoa - chinh la "tao lai" ma quyet dinh cam).
    from datetime import timezone

    cr_phieu_repo = AsyncMock()
    cr_phieu_repo.get_success_cung_thang.return_value = None
    cr_phieu_repo.get_by_session_cell.return_value = {
        "id": 88,
        "trang_thai": "FAILED",
        "phieu_id": None,
        "deleted_at": datetime(2026, 10, 4, 1, 0, 0, tzinfo=timezone.utc),
    }
    use_case, _, save_cell_clm_gateway = _make_use_case(cr_phieu_repo=cr_phieu_repo)

    with pytest.raises(PhieuDaXoaError) as exc:
        await use_case.execute(SESSION_ID, CELL_NAME)

    assert "khong xuat lai" in str(exc.value)
    save_cell_clm_gateway.save_cell_clm.assert_not_called()
    cr_phieu_repo.insert.assert_not_called()
    cr_phieu_repo.update_result.assert_not_called()


async def test_v2_khong_con_tham_so_dry_run_luon_post_that():
    # V2 (12/08) - gateway duoc goi KHONG kem tham so dry_run nao, va dong
    # cr_phieu di thang PENDING -> SUCCESS (khong con trang thai DRY_RUN).
    use_case, cr_phieu_repo, save_cell_clm_gateway = _make_use_case()

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    save_cell_clm_gateway.save_cell_clm.assert_called_once()
    assert "dry_run" not in save_cell_clm_gateway.save_cell_clm.call_args.kwargs

    cr_phieu_repo.insert.assert_called_once()
    inserted_arg = cr_phieu_repo.insert.call_args.args[0]
    assert inserted_arg["trang_thai"] == "PENDING"
    assert inserted_arg["cr_session_id"] == SESSION_ID
    assert inserted_arg["cell_name"] == CELL_NAME

    cr_phieu_repo.update_result.assert_called_once()
    assert cr_phieu_repo.update_result.call_args.kwargs["trang_thai"] == "SUCCESS"

    assert result.trang_thai == "SUCCESS"
    assert result.already_exists is False


# === V3 (12/08) - RETRY PHAN LOAI LOI ===


async def test_v3_timeout_thu_du_3_lan_roi_ghi_FAILED_va_nem_lai():
    # V3d - loi mang KHONG duoc de dong cr_phieu ket vinh vien o PENDING.
    gw = AsyncMock()
    gw.save_cell_clm.side_effect = SaveCellClmApiError(
        "SaveCellClm POST that loi mang/timeout: ReadTimeout", cell=CELL_NAME
    )
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    # V3b - het luot van loi thi NEM LAI (router giu nguyen 503)
    with pytest.raises(SaveCellClmApiError):
        await use_case.execute(SESSION_ID, CELL_NAME)

    assert gw.save_cell_clm.await_count == XUAT_PHIEU_MAX_RETRY

    kwargs = cr_phieu_repo.update_result.call_args.kwargs
    assert kwargs["trang_thai"] == "FAILED", "KHONG duoc de dong ket PENDING mo coi"
    assert "3 lan thu" in kwargs["error_message"]
    # so_lan_thu phai cong DUNG so lan da lam phien CTS, khong phai +1
    assert kwargs["so_lan_thu_them"] == XUAT_PHIEU_MAX_RETRY


async def test_v3_loi_400_dung_ngay_chi_goi_1_lan():
    # 4xx = loi NOI DUNG request - thu lai chac chan hong y het.
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 400, "isError": None, "code": None, "message": None,
        "data": None, "totalRecord": None, "raw_body": '{"title":"validation error"}',
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert gw.save_cell_clm.await_count == 1, "400 PHAI dung ngay"
    assert result.trang_thai == "FAILED"
    assert cr_phieu_repo.update_result.call_args.kwargs["so_lan_thu_them"] == 1


async def test_v3_200_kem_isError_dung_ngay_chi_goi_1_lan():
    # Loi NGHIEP VU - mau that lay tu dong cr_phieu id=82 tren DB.
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 200, "isError": True, "code": 2,
        "message": "Bad Cell 4G-SSN104M12-HNI dang xu ly cua thang 202607",
        "data": 0, "totalRecord": 0,
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert gw.save_cell_clm.await_count == 1, "200+isError PHAI dung ngay"
    assert result.trang_thai == "FAILED"
    assert "Bad Cell" in cr_phieu_repo.update_result.call_args.kwargs["error_message"]


async def test_v3_500_thu_lai_va_thanh_cong_o_lan_2():
    # 5xx = loi TAM THOI phia CTS -> thu lai; lan 2 qua thi ket qua la SUCCESS.
    gw = AsyncMock()
    gw.save_cell_clm.side_effect = [
        {"status_code": 503, "isError": True, "code": None, "message": "Service Unavailable",
         "data": None, "totalRecord": None, "raw_body": "upstream down"},
        dict(_RESP_OK),
    ]
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert gw.save_cell_clm.await_count == 2
    assert result.trang_thai == "SUCCESS"
    assert result.phieu_id == "19177"
    assert cr_phieu_repo.update_result.call_args.kwargs["so_lan_thu_them"] == 2


async def test_v3_500_het_luot_thi_FAILED_nhung_KHONG_nem_exception():
    # Van co response HOP LE tu CTS (khac han loi mang) -> giu hop dong cu:
    # router tra 200 kem trang_thai=FAILED, KHONG phai 503.
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 500, "isError": True, "code": None, "message": "Internal Server Error",
        "data": None, "totalRecord": None, "raw_body": "boom",
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert gw.save_cell_clm.await_count == XUAT_PHIEU_MAX_RETRY
    assert result.trang_thai == "FAILED"
    assert cr_phieu_repo.update_result.call_args.kwargs["so_lan_thu_them"] == XUAT_PHIEU_MAX_RETRY


async def test_v3a_status_code_duoc_giu_lai_trong_cts_response():
    # V3a - truoc day status_code bi vut khi loc cts_response nen doc lai
    # cr_phieu.response_body khong phan biet duoc 400 voi 200+isError.
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 400, "isError": None, "code": None, "message": None,
        "data": None, "totalRecord": None, "raw_body": "loi 400",
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.cts_response["status_code"] == 400
    # va phai duoc persist xuong cot JSONB response_body
    assert cr_phieu_repo.update_result.call_args.kwargs["response_body"]["status_code"] == 400


async def test_tram_chua_sync_rims_dien_rong_khong_chan_xuat_phieu():
    # ~0.4% MRBTS chua sync RIMS (da gap truoc o PreviewCrResponse) - tram=None
    # KHONG duoc chan xuat phieu, chi dien "" cho field lien quan.
    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_id.return_value = None
    use_case, _, save_cell_clm_gateway = _make_use_case(enodeb_repo=enodeb_repo)

    await use_case.execute(SESSION_ID, CELL_NAME)

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["SiteName"] == ""
    assert payload["ProvinceCode"] == ""
    assert payload["BuildingCode"] == ""
    assert payload["BuildingName"] == ""
    assert payload["Vendor"] == "NOKIA"  # fallback mac dinh khi ten_thiet_bi rong


async def test_cts_tu_choi_raw_body_duoc_luu_xuong_cr_phieu():
    # VIEC 2 - CTS tu choi bang .NET problem+json: 4 key chuan deu None nen
    # message rong -> raw_body PHAI duoc dua vao ca cts_response (persist xuong
    # cot JSONB response_body) LAN error_message (doc phat ra ngay ly do).
    raw = '{"title":"One or more validation errors occurred.","errors":{"$.SoChiTieuVP":["..."]}}'
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 400, "isError": None, "code": None, "message": None,
        "data": None, "totalRecord": None, "raw_body": raw,
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.trang_thai == "FAILED"
    assert result.phieu_id is None
    assert result.cts_response["raw_body"] == raw  # router tra ve FE
    # luu DB: response_body (JSONB) chua raw_body, error_message dung raw_body
    # lam ly do (vi message chuan la None)
    kwargs = cr_phieu_repo.update_result.call_args.kwargs
    assert kwargs["response_body"]["raw_body"] == raw
    assert kwargs["error_message"] == raw


async def test_xuat_lai_dong_cu_PHAI_cap_nhat_lai_request_payload():
    # BUG THAT (11/08, phat hien khi test ghep full tren session #553): cell da
    # co dong cr_phieu cu (FAILED tu lan truoc) -> use case TAI DUNG dong do,
    # nhanh insert() KHONG chay, va truoc day cung KHONG cap nhat lai
    # request_payload -> cot audit giu payload cua lan DAU (vd SoChiTieuVP=1
    # kieu int) trong khi thu VUA GUI da khac (SoChiTieuVP="1" str). Audit noi
    # doi -> debug lac huong. Phai luon ghi de payload lan nay.
    cr_phieu_repo = AsyncMock()
    # B9 - AsyncMock tra Mock TRUTHY cho method chua khai bao; khong dat None
    # thi test roi vao nhanh "da co phieu trong thang" va khong chay toi phan dang test
    cr_phieu_repo.get_success_cung_thang.return_value = None
    cr_phieu_repo.get_by_session_cell.return_value = {
        "id": 51, "trang_thai": "FAILED", "phieu_id": None,
    }
    use_case, _, _ = _make_use_case(cr_phieu_repo=cr_phieu_repo)

    await use_case.execute(SESSION_ID, CELL_NAME)

    cr_phieu_repo.insert.assert_not_called()  # tai dung dong cu, khong insert moi
    kwargs = cr_phieu_repo.update_result.call_args.kwargs
    assert kwargs["request_payload"] is not None, "PHAI ghi lai payload lan nay"
    assert kwargs["request_payload"]["TenCell"] == CELL_NAME
    # kieu dung cua SoChiTieuVP (bai hoc 400) phai duoc phan anh vao cot audit
    assert kwargs["request_payload"]["SoChiTieuVP"] == "1"


async def test_cts_thanh_cong_khong_co_raw_body():
    # Luong thanh cong: KHONG co raw_body, phieu_id lay tu data (so nguyen)
    gw = AsyncMock()
    gw.save_cell_clm.return_value = {
        "status_code": 200, "isError": False, "code": "200", "message": "OK",
        "data": 19177, "totalRecord": 1,
    }
    use_case, cr_phieu_repo, _ = _make_use_case(save_cell_clm_gateway=gw)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    assert result.trang_thai == "SUCCESS"
    assert result.phieu_id == "19177"
    assert "raw_body" not in result.cts_response
    assert cr_phieu_repo.update_result.call_args.kwargs["error_message"] is None


class TestExtractPhieuId:
    # Ham thuan, khong can mock - test truc tiep. Hinh dang data DA XAC NHAN
    # bang 1 lan POST that thanh cong (phieu id=19177): SO NGUYEN.
    def test_data_la_so_nguyen_tra_str_cua_chinh_no(self):
        assert _extract_phieu_id(19177) == "19177"

    def test_data_none_tra_none(self):
        # CTS bao loi (isError=true) thuong khong kem data - khong duoc crash
        assert _extract_phieu_id(None) is None


async def test_nut_xuat_tay_van_xuat_duoc_cho_cell_KHONG_XUAT_THIEU_DU_LIEU():
    # Cach C (16082026): job danh dau cell thieu du lieu bang dong cr_phieu
    # KHONG_XUAT_THIEU_DU_LIEU. Muc dich cua viec danh dau la de NGUOI XUAT TAY -
    # nen nut [Xuat] PHAI van hoat dong, giong het 2 trang thai KHONG_XUAT_* kia.
    # Neu cho nay chan lai thi viec danh dau tro nen vo nghia (cell hien tren UI
    # ma khong ai xuat duoc).
    cr_phieu_repo = AsyncMock()
    # B9 - AsyncMock tra Mock TRUTHY cho method chua khai bao; khong dat None
    # thi test roi vao nhanh "da co phieu trong thang" va khong chay toi phan dang test
    cr_phieu_repo.get_success_cung_thang.return_value = None
    cr_phieu_repo.get_by_session_cell.return_value = {
        "id": 77, "trang_thai": TRANG_THAI_THIEU_DU_LIEU, "phieu_id": None,
    }
    use_case, _, save_cell_clm_gateway = _make_use_case(cr_phieu_repo=cr_phieu_repo)

    result = await use_case.execute(SESSION_ID, CELL_NAME)

    save_cell_clm_gateway.save_cell_clm.assert_called_once()
    cr_phieu_repo.insert.assert_not_called()  # tai dung id 77
    assert result.cr_phieu_id == 77
    assert result.already_exists is False


async def test_router_van_raise_422_khi_thieu_du_lieu_KHONG_DOI():
    # Nhanh ROUTER (nguoi bam nut) GIU NGUYEN raise QoeDataInsufficientError -
    # Cach C chi doi nhanh JOB. Nguoi bam nut can thay loi RO RANG ngay, khong
    # phai 1 dong cr_phieu im lang.
    use_case, _, save_cell_clm_gateway = _make_use_case(
        # 3 ngay sau < MIN_DAYS_REQUIRED=5
        after_points=_points(_5_DATES_AFTER[:3], [1.0] * 3),
    )

    with pytest.raises(QoeDataInsufficientError):
        await use_case.execute(SESSION_ID, CELL_NAME)

    save_cell_clm_gateway.save_cell_clm.assert_not_called()


# === PhuongAnXuLyDuKien theo NGUYEN NHAN (quyet dinh 04/10/2026) ===
#
# TAI SAO khong con hardcode "2": truoc day moi phieu deu ghi cung 1 gia tri
# "2" (xem git blame V5 12/08) - KHONG phan biet duoc nguyen nhan xuat phieu
# (duoi san chat luong toi thieu 3.0, hay chi tut nhieu nhung van con tren
# san). "2" gio CHI con danh cho ca duoi san (nang hon), "1" cho ca con lai.
#
# TAI SAO dung khoa_uu_tien_xuat_phieu() thay vi viet lai so sanh 3.0/0.5:
# ham nay DA la nguon chuan cho dinh nghia "nhom" (dung de XEP HANG chon 6
# phieu/session) - dinh nghia "2 neu duoi san" trung khop 100% voi "nhom 0".
# Viet lai 1 ham rieng se tao 2 noi cung mot cong thuc, dam truoc sau lech
# nguong khi 1 ben duoc sua ma ben kia bi quen (dung bai hoc tu lich su file
# nay - xem docstring do_te_cua()/khoa_uu_tien_xuat_phieu()).
def _qoe(avg_before: float, avg_after: float) -> QoeCellEvaluation:
    # result="FAIL" gia dinh (khoa_uu_tien_xuat_phieu() KHONG doc .result, chi
    # doc avg_before/avg_after qua _ket_luan_duoc() - result o day chi can
    # KHAC "INSUFFICIENT_DATA" de khong bi loai khoi xep hang).
    return QoeCellEvaluation(
        cell_name=CELL_NAME,
        qoe_eval=MetricEvaluation(result="FAIL", avg_before=avg_before, avg_after=avg_after),
        so_ngay_before=5,
        so_ngay_after=5,
        after_points=[avg_after] * 5,
    )


async def test_qoe_duoi_san_khong_tut_van_ra_2():
    # QoE sau 2.8 (duoi san 3.0), KHONG tut (before == after = 2.8) -> "2".
    # Minh chung "2" KHONG con gan voi "tut nhieu" - duoi san la dieu kien
    # RIENG, du khong tut 1 chut nao van la "2" (nang hon "1").
    use_case, _, save_cell_clm_gateway = _make_use_case(
        # QoS khoe manh, KHONG anh huong nhom (nhom lay MIN avg_after giua 2
        # chi so - QoE 2.8 van la min du QoS 4.0).
        before_points=_points(_5_DATES_BEFORE, [4.0] * 5),
        after_points=_points(_5_DATES_AFTER, [4.0] * 5),
    )

    await use_case.execute(SESSION_ID, CELL_NAME, nguon=NGUON_QOE, qoe=_qoe(2.8, 2.8))

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "2"


async def test_qos_vua_duoi_san_vua_tut_nhieu_van_ra_2():
    # QoS 3.5 -> 2.9: VUA duoi san (2.9 < 3.0) VUA tut qua 0.5 (tut 0.6).
    # Quyet dinh 04/10: duoi san THANG, ra "2" - KHONG phai "1" du dong thoi
    # thoa dieu kien cua "1" (tut > 0.5).
    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=_points(_5_DATES_BEFORE, [3.5] * 5),
        after_points=_points(_5_DATES_AFTER, [2.9] * 5),
    )

    await use_case.execute(SESSION_ID, CELL_NAME)

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "2"


async def test_qos_tut_nhieu_nhung_tren_san_ra_1():
    # QoS 4.5 -> 3.6: tut 0.9 (> 0.5, nen FAIL) nhung avg_after=3.6 VAN >= 3.0
    # (tren san) -> "1", khong phai "2".
    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=_points(_5_DATES_BEFORE, [4.5] * 5),
        after_points=_points(_5_DATES_AFTER, [3.6] * 5),
    )

    await use_case.execute(SESSION_ID, CELL_NAME)

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "1"


async def test_qos_tren_san_khong_tut_qoe_tut_nhieu_nhung_tren_san_ra_1():
    # QoS tren san va KHONG tut (4.0 -> 4.0, PASS - job da ket luan KHONG DAT
    # qua QoE nen nguon=NGUON_QOE, KHAC voi nhanh ROUTER o tren). QoE 4.2 ->
    # 3.4: tut 0.8 (> 0.5) nhung avg_after=3.4 VAN >= 3.0 -> ca 2 chi so DEU
    # tren san -> "1".
    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=_points(_5_DATES_BEFORE, [4.0] * 5),
        after_points=_points(_5_DATES_AFTER, [4.0] * 5),
    )

    await use_case.execute(SESSION_ID, CELL_NAME, nguon=NGUON_QOE, qoe=_qoe(4.2, 3.4))

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "1"


async def test_xuat_tay_1_cell_qua_router_cung_tinh_nhom_dung():
    # Duong XUAT TAY (POST /phieu, api/routers/phieu.py) goi use_case.execute()
    # KHONG truyen nguon/qoe (y het cach cac test tren goi qua router) - tai su
    # dung CHINH XAC 1 ham execute() voi job tu dong (yeu cau 2: khong duoc co
    # 2 duong tinh PhuongAnXuLyDuKien khac nhau). Test nay dung lai kich ban
    # "QoS duoi san" de xac nhan duong xuat tay (CHI co QoS, KHONG co QoE) van
    # ra dung "2" - KHONG phai vi no may man giong duong job, ma vi CUNG 1 dong
    # code xu ly CA 2 duong.
    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=_points(_5_DATES_BEFORE, [3.5] * 5),
        after_points=_points(_5_DATES_AFTER, [2.9] * 5),
    )

    result = await use_case.execute(SESSION_ID, CELL_NAME)  # dung het mac dinh nhu router

    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "2"
    assert result.trang_thai == "SUCCESS"


async def test_xuat_tay_tu_danh_gia_qoe_khi_chua_truyen():
    # SUA 1 LO (04/10/2026): truoc sua nay, duong xuat tay (qoe=None, nguon=
    # None) KHONG tu danh gia QoE - nhom CHI tinh tu QoS, cell QoS binh
    # thuong (PASS) nhung QoE kem se bi bao SAI "1" (dung ra phai "2", VA
    # dung ra phai duoc XUAT PHIEU thay vi "DAT_KHONG_XUAT").
    #
    # QoS 4.0 -> 4.0 (PASS, khong tut). QoE 3.5 -> 2.8 (duoi san 3.0) - mo
    # phong qoe_cells_use_case.execute() tra ve ket qua CHO CA SESSION (dung
    # dinh dang GetQoeCellsUseCase.execute() that su tra ve, xem
    # application/get_qoe_cells_use_case.py), KHONG phai truyen thang qua
    # tham so qoe cua execute() - dung CHINH co che _lay_qoe_theo_cell() moi
    # them se goi, khong mo phong tat.
    qoe_cells_use_case = AsyncMock()
    qoe_cells_use_case.execute.return_value = [_qoe(3.5, 2.8)]

    use_case, _, save_cell_clm_gateway = _make_use_case(
        before_points=_points(_5_DATES_BEFORE, [4.0] * 5),
        after_points=_points(_5_DATES_AFTER, [4.0] * 5),
        qoe_cells_use_case=qoe_cells_use_case,
    )

    result = await use_case.execute(SESSION_ID, CELL_NAME)  # KHONG truyen qoe/nguon

    qoe_cells_use_case.execute.assert_awaited_once_with(SESSION_ID, luu_snapshot=True)
    payload = save_cell_clm_gateway.save_cell_clm.call_args.args[0]
    assert payload["PhuongAnXuLyDuKien"] == "2"
    # QoS PASS nhung QoE FAIL -> PHAI xuat phieu (QoE ngang hang QoS), KHONG
    # duoc dung o "DAT_KHONG_XUAT" nhu truoc sua (luc do chi nhin QoS).
    assert result.trang_thai == "SUCCESS"
    assert payload["Qoe"] == "2"  # min(after_points QoE) = 2.8 -> int() = 2
