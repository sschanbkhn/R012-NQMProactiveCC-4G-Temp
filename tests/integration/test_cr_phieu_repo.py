"""
Integration test cho CrPhieuRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: yeu cau truc tiep user (KHOI 2/5 SaveCellClm) - audit + chong trung.
"""

from datetime import date, datetime

import pytest

from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
# Dung DUNG ham cua router (khong tu tinh moc trong test) - neu luat "+1 ngay"
# bi sua thi test loc ngay o duoi phai do theo va FAIL, do la muc dich.
from api.routers.loc_ngay import GMT7, khoang_ngay_gmt7
from domain.entities.cr_session import CrSession, CrStatus
from models.cr_phieu import CrPhieu as CrPhieuModel


async def _new_session_id(db_session, tram_id: str) -> int:
    # cr_phieu.cr_session_id la FK NOT NULL -> can 1 cr_session that truoc,
    # dung lai CrSessionRepo (da co test rieng) thay vi insert tay.
    repo = CrSessionRepo(db_session)
    created = await repo.create(
        CrSession(id=0, tram_id=tram_id, action="shutdown", status=CrStatus.RUNNING, plan_name=None)
    )
    return created.id


def _mau_phieu(cr_session_id: int, cell_name: str) -> dict:
    return {
        "cr_session_id": cr_session_id,
        "cell_name": cell_name,
        "trang_thai": "PENDING",
        "request_payload": {"TenCell": cell_name, "Nam": 2006, "Thang": 11},
    }


async def test_insert_tra_du_field_kem_id_created_at(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)

    result = await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_A"))

    assert result["id"] is not None
    assert result["cr_session_id"] == session_id
    assert result["cell_name"] == "TEST_B5_PHIEU_A"
    assert result["trang_thai"] == "PENDING"
    assert result["request_payload"]["TenCell"] == "TEST_B5_PHIEU_A"
    assert result["response_body"] is None
    assert result["phieu_id"] is None
    assert result["error_message"] is None
    assert result["created_at"] is not None


async def test_get_by_session_cell_co_ton_tai_tra_dung_dong(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_B"))

    found = await repo.get_by_session_cell(session_id, "TEST_B5_PHIEU_B")

    assert found is not None
    assert found["id"] == inserted["id"]


async def test_get_by_session_cell_khong_ton_tai_tra_none(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)

    found = await repo.get_by_session_cell(session_id, "TEST_B5_PHIEU_KHONG_TON_TAI")

    assert found is None


async def test_update_result_success_cap_nhat_dung_field(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_C"))

    await repo.update_result(
        inserted["id"],
        trang_thai="SUCCESS",
        response_body={"isError": False, "code": "200", "message": "OK", "data": {"id": "PHIEU-001"}},
        phieu_id="PHIEU-001",
        error_message=None,
    )

    found = await repo.get_by_session_cell(session_id, "TEST_B5_PHIEU_C")
    assert found["trang_thai"] == "SUCCESS"
    assert found["response_body"]["data"]["id"] == "PHIEU-001"
    assert found["phieu_id"] == "PHIEU-001"
    assert found["error_message"] is None


async def test_update_result_failed_cap_nhat_error_message(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_D"))

    await repo.update_result(
        inserted["id"],
        trang_thai="FAILED",
        response_body=None,
        phieu_id=None,
        error_message="CTS API timeout sau 3 lan retry",
    )

    found = await repo.get_by_session_cell(session_id, "TEST_B5_PHIEU_D")
    assert found["trang_thai"] == "FAILED"
    assert found["response_body"] is None
    assert found["phieu_id"] is None
    assert found["error_message"] == "CTS API timeout sau 3 lan retry"


async def test_get_by_cr_session_id_tra_dung_danh_sach(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_E1"))
    await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_E2"))

    rows = await repo.get_by_cr_session_id(session_id)

    assert {r["cell_name"] for r in rows} == {"TEST_B5_PHIEU_E1", "TEST_B5_PHIEU_E2"}


async def test_get_by_cr_session_id_khong_ton_tai_tra_rong(db_session, test_tram):
    repo = CrPhieuRepo(db_session)
    assert await repo.get_by_cr_session_id(999_999_999) == []


async def test_get_by_cr_session_id_khong_lan_qua_session_khac(db_session, test_tram):
    session_a = await _new_session_id(db_session, test_tram)
    session_b = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_a, "TEST_B5_PHIEU_F"))
    await repo.insert(_mau_phieu(session_b, "TEST_B5_PHIEU_F"))  # cung cell_name, KHAC session -> hop le

    rows_a = await repo.get_by_cr_session_id(session_a)
    assert len(rows_a) == 1
    assert rows_a[0]["cr_session_id"] == session_a


# === list_phieu()/count_phieu() (UI lich su phieu, 11/08) ===
#
# Cac test duoi day loc theo session_id sinh MOI trong chinh test (khong dung
# du lieu that co san) - DB dev co san phieu that (vd 19207) nen moi assertion
# tren "tat ca phieu" phai viet theo kieu tuong doi (>=), khong duoc assert
# con so tuyet doi.


async def _phieu_voi_trang_thai(repo, session_id: int, cell_name: str, trang_thai: str) -> dict:
    phieu = _mau_phieu(session_id, cell_name)
    phieu["trang_thai"] = trang_thai
    return await repo.insert(phieu)


async def test_list_phieu_loc_theo_session_id(db_session, test_tram):
    session_a = await _new_session_id(db_session, test_tram)
    session_b = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_a, "TEST_B5_LIST_A1"))
    await repo.insert(_mau_phieu(session_a, "TEST_B5_LIST_A2"))
    await repo.insert(_mau_phieu(session_b, "TEST_B5_LIST_B1"))

    rows = await repo.list_phieu(session_a, None, page=1, size=20)

    assert {r["cell_name"] for r in rows} == {"TEST_B5_LIST_A1", "TEST_B5_LIST_A2"}
    assert await repo.count_phieu(session_a, None) == 2


async def test_list_phieu_khong_truyen_session_id_tra_ca_phieu_khac(db_session, test_tram):
    # session_id=None -> KHONG loc: phai thay ca phieu cua session khac (day la
    # ngu canh "tab lich su rieng" cua UI).
    session_a = await _new_session_id(db_session, test_tram)
    session_b = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_a, "TEST_B5_LIST_ALL_A"))
    await repo.insert(_mau_phieu(session_b, "TEST_B5_LIST_ALL_B"))

    total_tat_ca = await repo.count_phieu(None, None)
    total_rieng_a = await repo.count_phieu(session_a, None)

    assert total_tat_ca >= 2
    assert total_tat_ca > total_rieng_a  # co du lieu ngoai session_a

    # sort mac dinh created_at DESC -> 2 dong vua insert nam dau danh sach
    rows = await repo.list_phieu(None, None, page=1, size=20)
    ten_cell = {r["cell_name"] for r in rows}
    assert "TEST_B5_LIST_ALL_A" in ten_cell
    assert "TEST_B5_LIST_ALL_B" in ten_cell


async def test_list_phieu_loc_theo_trang_thai(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_TT_OK", "SUCCESS")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_TT_FAIL", "FAILED")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_TT_PEND", "PENDING")

    rows = await repo.list_phieu(session_id, "SUCCESS", page=1, size=20)

    assert [r["cell_name"] for r in rows] == ["TEST_B5_TT_OK"]
    assert await repo.count_phieu(session_id, "SUCCESS") == 1
    assert await repo.count_phieu(session_id, "FAILED") == 1
    # 2 filter ket hop (session_id VA trang_thai), khong phai chi 1 trong 2
    assert await repo.count_phieu(session_id, None) == 3


async def test_v2_khong_truyen_trang_thai_thi_LAY_TAT_CA(db_session, test_tram):
    # V2 (12/08): da BO luat "an dong DRY_RUN mac dinh". Tu V4, cac dong
    # KHONG_XUAT_* PHAI hien mac dinh - do chinh la muc dich cua V4 (cell chua
    # xuat phai nhin thay duoc tren UI, khong bien mat im lang).
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR_OK", "SUCCESS")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR_FAIL", "FAILED")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR_PEND", "PENDING")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR_VUOT", "KHONG_XUAT_VUOT_GIOI_HAN")

    rows = await repo.list_phieu(session_id, None, page=1, size=20)

    assert {r["cell_name"] for r in rows} == {
        "TEST_B5_DR_OK",
        "TEST_B5_DR_FAIL",
        "TEST_B5_DR_PEND",
        "TEST_B5_DR_VUOT",
    }
    # count_phieu PHAI dung CHUNG dieu kien - neu lech, FE tinh du so trang
    # nhung trang cuoi rong.
    assert await repo.count_phieu(session_id, None) == 4


async def test_v4_loc_tuong_minh_trang_thai_khong_xuat(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR2_OK", "SUCCESS")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_DR2_VUOT", "KHONG_XUAT_VUOT_GIOI_HAN")

    rows = await repo.list_phieu(session_id, "KHONG_XUAT_VUOT_GIOI_HAN", page=1, size=20)

    assert [r["cell_name"] for r in rows] == ["TEST_B5_DR2_VUOT"]
    assert await repo.count_phieu(session_id, "KHONG_XUAT_VUOT_GIOI_HAN") == 1


async def test_v4_danh_dau_khong_xuat_chi_doi_trang_thai(db_session, test_tram):
    # V4: cell het luot thu da co dong FAILED kem ly do CTS tu choi - danh dau
    # KHONG duoc xoa error_message/so_lan_thu (do la thu nguoi van hanh can doc).
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    dong = await repo.insert(_mau_phieu(session_id, "TEST_B5_DANHDAU"))
    await repo.update_result(
        dong["id"],
        trang_thai="FAILED",
        response_body={"isError": True},
        phieu_id=None,
        error_message="Bad Cell dang xu ly cua thang 202607",
        so_lan_thu_them=3,
    )

    await repo.danh_dau_khong_xuat(dong["id"], "KHONG_XUAT_HET_LUOT_THU")

    sau = await repo.get_by_session_cell(session_id, "TEST_B5_DANHDAU")
    assert sau["trang_thai"] == "KHONG_XUAT_HET_LUOT_THU"
    assert sau["error_message"] == "Bad Cell dang xu ly cua thang 202607"
    assert sau["so_lan_thu"] == 3
    assert sau["response_body"] == {"isError": True}


async def test_list_phieu_phan_trang_khong_trung_khong_sot(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    for i in range(5):
        await repo.insert(_mau_phieu(session_id, f"TEST_B5_PAGE_{i}"))

    trang_1 = await repo.list_phieu(session_id, None, page=1, size=2, sort_by="cell_name", order="asc")
    trang_2 = await repo.list_phieu(session_id, None, page=2, size=2, sort_by="cell_name", order="asc")
    trang_3 = await repo.list_phieu(session_id, None, page=3, size=2, sort_by="cell_name", order="asc")

    assert [r["cell_name"] for r in trang_1] == ["TEST_B5_PAGE_0", "TEST_B5_PAGE_1"]
    assert [r["cell_name"] for r in trang_2] == ["TEST_B5_PAGE_2", "TEST_B5_PAGE_3"]
    assert [r["cell_name"] for r in trang_3] == ["TEST_B5_PAGE_4"]  # trang cuoi le
    # total = tong toan bo KHOP filter, KHONG phai so dong tren 1 trang
    assert await repo.count_phieu(session_id, None) == 5


async def test_list_phieu_sort_mac_dinh_created_at_desc(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_SORT_CU"))
    await repo.insert(_mau_phieu(session_id, "TEST_B5_SORT_MOI"))

    rows = await repo.list_phieu(session_id, None, page=1, size=20)

    # phieu moi nhat truoc (dac ta) - so bang created_at that, khong dua vao
    # thu tu insert (2 dong co the trung mili-giay tren may nhanh)
    assert rows[0]["created_at"] >= rows[-1]["created_at"]
    assert rows[0]["cell_name"] == "TEST_B5_SORT_MOI"


async def test_list_phieu_sort_by_ngoai_whitelist_khong_crash_ve_mac_dinh(db_session, test_tram):
    # An toan lop 2: router da chan bang Literal, nhung neu bi goi truc tiep tu
    # script voi ten cot bay ba thi repo PHAI ve mac dinh, KHONG duoc crash hay
    # ghep chuoi do vao SQL.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_SORT_LA"))

    rows = await repo.list_phieu(session_id, None, page=1, size=20, sort_by="request_payload; DROP TABLE")

    assert [r["cell_name"] for r in rows] == ["TEST_B5_SORT_LA"]


async def test_list_phieu_tra_du_field_chi_tiet_cho_modal(db_session, test_tram):
    # Quyet dinh "cach 1" (list kem chi tiet) - modal FE dung data co san,
    # KHONG goi them endpoint chi tiet.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_DETAIL"))
    await repo.update_result(
        inserted["id"],
        trang_thai="FAILED",
        response_body={"isError": True, "message": "TenCell khong hop le"},
        phieu_id=None,
        error_message="CTS tu choi",
    )

    row = (await repo.list_phieu(session_id, None, page=1, size=20))[0]

    assert row["request_payload"]["TenCell"] == "TEST_B5_DETAIL"
    assert row["response_body"]["message"] == "TenCell khong hop le"
    assert row["error_message"] == "CTS tu choi"


async def test_unique_cr_session_cell_chan_trung(db_session, test_tram):
    # UNIQUE(cr_session_id, cell_name) - insert 2 LAN cung cell_name trong
    # CUNG 1 session PHAI raise loi DB (khac cr_affected_cells dung ON
    # CONFLICT DO NOTHING - o day insert() KHONG bat loi, de caller
    # (use case Khoi 3) tu quyet dinh xu ly, vi INSERT phieu la hanh dong co
    # y nghia nghiep vu ro rang, khong phai ghi lai idempotent nhu affected_cells).
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_DUP"))

    with pytest.raises(Exception):
        await repo.insert(_mau_phieu(session_id, "TEST_B5_PHIEU_DUP"))

    await db_session.rollback()  # transaction bi abort sau IntegrityError, can rollback truoc khi teardown query tiep


# === 13/08: tim kiem (q) + loc khoang ngay cho GET /phieu ===


def _mau_phieu_day_du(cr_session_id: int, cell_name: str, phieu_id: str | None = None) -> dict:
    return {**_mau_phieu(cr_session_id, cell_name), "phieu_id": phieu_id}


async def _dat_created_at(db_session, phieu_id_db: int, thoi_diem) -> None:
    # insert() luon set created_at = now(UTC), khong nhan tu caller (C1.4-fix9).
    # Test loc ngay CAN moc thoi gian XAC DINH nen phai ghi de sau khi insert -
    # day la ly do chinh dang de UPDATE thang trong test thay vi qua repo.
    row = await db_session.get(CrPhieuModel, phieu_id_db)
    row.created_at = thoi_diem
    await db_session.commit()


async def test_q_khop_cell_name(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_Q_SSN104M12"))
    await repo.insert(_mau_phieu(session_id, "TEST_B5_Q_KHAC"))

    rows = await repo.list_phieu(session_id, None, 1, 20, None, "desc", "SSN104")

    assert [r["cell_name"] for r in rows] == ["TEST_B5_Q_SSN104M12"]
    # ILIKE - khong phan biet hoa thuong (nguoi dung go thuong van phai ra)
    rows_thuong = await repo.list_phieu(session_id, None, 1, 20, None, "desc", "ssn104")
    assert [r["cell_name"] for r in rows_thuong] == ["TEST_B5_Q_SSN104M12"]


async def test_q_khop_phieu_id(db_session, test_tram):
    # 1 o tim chung: go so phieu cung phai ra, khong phai doi sang o khac.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu_day_du(session_id, "TEST_B5_Q_CO_PHIEU", phieu_id="19207"))
    await repo.insert(_mau_phieu_day_du(session_id, "TEST_B5_Q_KHONG_PHIEU", phieu_id=None))

    rows = await repo.list_phieu(session_id, None, 1, 20, None, "desc", "19207")

    assert [r["cell_name"] for r in rows] == ["TEST_B5_Q_CO_PHIEU"]


async def test_q_khong_khop_tra_rong(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_Q_RONG"))

    rows = await repo.list_phieu(session_id, None, 1, 20, None, "desc", "KHONG_TON_TAI_XYZ")

    assert rows == []
    assert await repo.count_phieu(session_id, None, "KHONG_TON_TAI_XYZ") == 0


async def test_q_ket_hop_trang_thai(db_session, test_tram):
    # 2 filter phai AND voi nhau, khong phai OR - go "SSN" + loc SUCCESS thi
    # dong FAILED cung ten SSN KHONG duoc lot vao.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_QK_SSN_OK", "SUCCESS")
    await _phieu_voi_trang_thai(repo, session_id, "TEST_B5_QK_SSN_FAIL", "FAILED")

    rows = await repo.list_phieu(session_id, "SUCCESS", 1, 20, None, "desc", "SSN")

    assert [r["cell_name"] for r in rows] == ["TEST_B5_QK_SSN_OK"]
    assert await repo.count_phieu(session_id, "SUCCESS", "SSN") == 1


async def test_q_escape_gach_duoi_khong_thanh_ky_tu_dai_dien(db_session, test_tram):
    # '_' trong LIKE la KY TU DAI DIEN. Khong escape thi go "TEST_B5" se khop ca
    # "TESTxB5" - nguoi dung thay ket qua la ma khong hieu vi sao.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(_mau_phieu(session_id, "TEST_B5_ESC_A_B"))
    await repo.insert(_mau_phieu(session_id, "TEST_B5_ESCxAxB"))

    rows = await repo.list_phieu(session_id, None, 1, 20, None, "desc", "ESC_A_B")

    assert [r["cell_name"] for r in rows] == ["TEST_B5_ESC_A_B"]


async def test_loc_khoang_ngay_dong_0930_ngay_cuoi_VAN_nam_trong_ket_qua(db_session, test_tram):
    # KHOA HOP DONG MUI GIO: neu ai do bo buoc "+1 ngay vao den_ngay"
    # (api/routers/loc_ngay.py) thi dong tao luc 09:30 ngay den_ngay se bi loai
    # (09:30 > 00:00) - loi IM LANG vi man hinh van co du lieu.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)

    trong = await repo.insert(_mau_phieu(session_id, "TEST_B5_NGAY_TRONG_0930"))
    truoc = await repo.insert(_mau_phieu(session_id, "TEST_B5_NGAY_TRUOC_2330"))
    sau = await repo.insert(_mau_phieu(session_id, "TEST_B5_NGAY_SAU_0030"))
    # 09:30 ngay 20/08 GMT+7 - dung giua ngay den_ngay
    await _dat_created_at(db_session, trong["id"], datetime(2026, 8, 20, 9, 30, tzinfo=GMT7))
    # 23:30 ngay 19/08 GMT+7 - TRUOC cua so (chi 30 phut, du bat loi lech mui gio)
    await _dat_created_at(db_session, truoc["id"], datetime(2026, 8, 19, 23, 30, tzinfo=GMT7))
    # 00:30 ngay 21/08 GMT+7 - SAU cua so (chi 30 phut)
    await _dat_created_at(db_session, sau["id"], datetime(2026, 8, 21, 0, 30, tzinfo=GMT7))

    # Dung DUNG ham ma router dung, khong tu tinh moc trong test
    tu_moc, den_moc = khoang_ngay_gmt7(date(2026, 8, 20), date(2026, 8, 20))
    rows = await repo.list_phieu(session_id, None, 1, 20, None, "desc", None, tu_moc, den_moc)

    ten = {r["cell_name"] for r in rows}
    assert "TEST_B5_NGAY_TRONG_0930" in ten, "dong 09:30 ngay den_ngay BI MAT - thieu +1 ngay"
    assert "TEST_B5_NGAY_TRUOC_2330" not in ten
    assert "TEST_B5_NGAY_SAU_0030" not in ten


async def test_total_va_data_nhat_quan_khi_co_filter(db_session, test_tram):
    # total va data PHAI dung chung _filter_conditions() - lech nhau thi FE hien
    # du so trang nhung trang cuoi rong.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    for i in range(3):
        await repo.insert(_mau_phieu(session_id, f"TEST_B5_NQ_KHOP_{i}"))
    await repo.insert(_mau_phieu(session_id, "TEST_B5_NQ_LECH"))

    tong = await repo.count_phieu(session_id, None, "NQ_KHOP")
    trang = await repo.list_phieu(session_id, None, 1, 100, None, "desc", "NQ_KHOP")

    assert tong == 3
    assert len(trang) == tong


# === tram_id / tram_name lay tu cr_session (04092026) ===
# FE can cot "Tram tat" o tab Phieu. Phieu xuat cho cell LAN CAN nen cell_name
# khong noi len no thuoc CR tat tram nao.


async def test_list_phieu_tra_tram_cua_CR_khong_phai_SiteName_trong_payload(db_session, test_tram):
    """CAI BAY: request_payload['SiteName'] la tram cua CHINH CELL duoc xuat
    phieu (cell lan can), KHONG phai tram bi tat trong CR."""
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(
        {
            "cr_session_id": session_id,
            "cell_name": "4G-CELL-LAN-CAN",
            "trang_thai": "SUCCESS",
            # SiteName CO Y khac tram cua session - neu code lay nham truong nay
            # thi test se lo ra ngay.
            "request_payload": {"TenCell": "4G-CELL-LAN-CAN", "SiteName": "4G-TRAM-KHAC-HNI"},
            "response_body": None,
            "phieu_id": "99999",
            "error_message": None,
        }
    )

    rows = await repo.list_phieu(session_id, None, 1, 20)
    assert len(rows) == 1
    assert rows[0]["tram_id"] == test_tram, "phai la tram cua cr_session"
    assert rows[0]["tram_id"] != "4G-TRAM-KHAC-HNI"
    assert rows[0]["tram_name"] == "TEST STATION B5"  # ten tu bang tram


async def test_list_phieu_KHONG_N_PLUS_1(db_session, test_tram):
    # 20 dong phieu phai lay bang DUNG 1 cau SQL (JOIN), khong phai 1 + 20.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    for i in range(20):
        await repo.insert(
            {
                "cr_session_id": session_id,
                "cell_name": f"4G-CELL-{i:02d}",
                "trang_thai": "SUCCESS",
                "request_payload": {"TenCell": f"4G-CELL-{i:02d}"},
                "response_body": None,
                "phieu_id": str(90000 + i),
                "error_message": None,
            }
        )

    dem = {"n": 0}
    goc = db_session.execute

    async def _dem(*a, **kw):
        dem["n"] += 1
        return await goc(*a, **kw)

    db_session.execute = _dem
    try:
        rows = await repo.list_phieu(session_id, None, 1, 20)
    finally:
        db_session.execute = goc

    assert len(rows) == 20
    assert dem["n"] == 1, f"phai 1 query cho ca trang, dang la {dem['n']} (N+1)"
    assert all(r["tram_id"] == test_tram for r in rows)


async def test_list_phieu_session_bi_xoa_van_tra_dong_phieu(db_session, test_tram):
    # outerjoin (khong phai inner): tram thieu thi tram_name = None chu KHONG
    # duoc lam BIEN MAT dong phieu.
    from sqlalchemy import text

    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    await repo.insert(
        {
            "cr_session_id": session_id,
            "cell_name": "4G-CELL-MO-COI",
            "trang_thai": "FAILED",
            "request_payload": {},
            "response_body": None,
            "phieu_id": None,
            "error_message": "loi test",
        }
    )
    # Doi tram_id cua session sang mot ma KHONG co trong bang tram (DB that
    # khong co FK cr_session.tram_id -> tram, da do bang pg_constraint).
    #
    # !!! BAT BUOC try/finally KHOI PHUC lai tram_id !!!
    # Fixture test_tram don dep bang dieu kien `cr_session.tram_id ==
    # TEST_TRAM_ID`. Doi cot do di ma khong tra lai thi teardown KHONG TIM
    # THAY session nay -> rac o lai DB THAT vinh vien. Da xay ra that ngay lan
    # chay dau (2 session 5531/5572 + 2 dong cr_phieu phai don tay).
    doi_tram = text(
        "UPDATE system_nsn_nqmproactivecc.cr_session SET tram_id = :tram WHERE id = :sid"
    )
    await db_session.execute(doi_tram, {"tram": "TRAM_KHONG_TON_TAI", "sid": session_id})
    await db_session.commit()
    try:
        rows = await repo.list_phieu(session_id, None, 1, 20)
        assert len(rows) == 1, "dong phieu KHONG duoc bien mat"
        assert rows[0]["tram_id"] == "TRAM_KHONG_TON_TAI"
        assert rows[0]["tram_name"] is None
    finally:
        await db_session.execute(doi_tram, {"tram": test_tram, "sid": session_id})
        await db_session.commit()


# === XOA MEM (THEM 04/10/2026, quyet dinh 04/10/2026, yeu cau truc tiep user) ===
# xoa() gio la UPDATE deleted_at=now() THAY VI DELETE that - cac test duoi day
# xac nhan: (1) dong VAN CON trong bang kem deleted_at co gia tri, (2) goi lai
# lan 2 KHONG lam gi (tra 0, khong ghi de thoi diem xoa goc), (3) list_phieu/
# count_phieu loai dong da xoa, (4) cr_phieu_lan_thu KHONG bi mat (UPDATE,
# khong con la DELETE nen FK ON DELETE CASCADE khong kich hoat).


async def test_xoa_la_soft_delete_dong_van_con_kem_deleted_at(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_MEM"))

    so_dong = await repo.xoa(inserted["id"])

    assert so_dong == 1
    # Dong VAN CON - get_by_session_cell() (duong doc KHONG loc deleted_at)
    # phai THAY duoc, KHAC list_phieu()/count_phieu() o duoi.
    found = await repo.get_by_session_cell(session_id, "TEST_B5_XOA_MEM")
    assert found is not None
    assert found["deleted_at"] is not None


async def test_xoa_2_lan_lan_2_tra_0_khong_ghi_de_thoi_diem(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_2_LAN"))

    assert await repo.xoa(inserted["id"]) == 1
    thoi_diem_xoa_goc = (await repo.get_by_session_cell(session_id, "TEST_B5_XOA_2_LAN"))["deleted_at"]

    so_dong_lan_2 = await repo.xoa(inserted["id"])

    assert so_dong_lan_2 == 0
    thoi_diem_sau = (await repo.get_by_session_cell(session_id, "TEST_B5_XOA_2_LAN"))["deleted_at"]
    assert thoi_diem_sau == thoi_diem_xoa_goc


async def test_get_by_id_van_thay_dong_da_xoa(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_GET_ID"))
    await repo.xoa(inserted["id"])

    found = await repo.get_by_id(inserted["id"])

    assert found is not None
    assert found["deleted_at"] is not None


async def test_list_phieu_va_count_phieu_loai_dong_da_xoa(db_session, test_tram):
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    con_lai = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_CON_LAI"))
    bi_xoa = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_BI_XOA"))
    await repo.xoa(bi_xoa["id"])

    rows = await repo.list_phieu(session_id, None, page=1, size=20)

    assert [r["cell_name"] for r in rows] == ["TEST_B5_XOA_CON_LAI"]
    assert await repo.count_phieu(session_id, None) == 1
    assert con_lai["id"] != bi_xoa["id"]  # phong ve: 2 dong THAT khac nhau


async def test_xoa_khong_lam_mat_cr_phieu_lan_thu(db_session, test_tram):
    # UPDATE (khong phai DELETE) nen FK ON DELETE CASCADE cua cr_phieu_lan_thu
    # KHONG kich hoat - lich su lan POST PHAI con nguyen sau khi xoa.
    session_id = await _new_session_id(db_session, test_tram)
    repo = CrPhieuRepo(db_session)
    inserted = await repo.insert(_mau_phieu(session_id, "TEST_B5_XOA_LAN_THU"))
    await repo.ghi_lan_thu(
        inserted["id"], nguoi_thuc_hien="MANUAL", ket_qua="FAILED", error_message="CTS tu choi"
    )

    await repo.xoa(inserted["id"])

    lich_su = await repo.lay_lan_thu(inserted["id"])
    assert len(lich_su) == 1
    assert lich_su[0]["ket_qua"] == "FAILED"
