"""
Integration test cho 6 truong tien trinh - DB THAT.
Tu: yeu cau truc tiep user 16082026; doi sang TU TAO DU LIEU 20082026 (huong C).

=== DOI TU DU LIEU MOCK SEED SAN SANG TU TAO (20082026) ===
Truoc day file nay ghim vao 12 session MOCK* do scripts/seed_mock_process_data.py
seed san. Bo di vi 2 ly do:
  1. Seed dung NGAY CO DINH ma scheduler THAT van chay hang ngay tren cung DB ->
     moi session mock deu troi tu buoc 2 sang buoc 4 theo thoi gian. MOCK996 da
     bi quet that ngay 19/08 (job_run_log id=735).
  2. Vi vay test phai them guard skip - va mot test luon skip la mot test khong
     kiem gi ca, nhung van hien "xanh".
Nay dung fixture du_lieu_tien_trinh (tests/integration/fixtures_tien_trinh.py):
moi luot chay tu tao 4 session voi ngay TUONG DOI, tu don sau khi xong. KHONG
con guard skip nao trong file nay.

Muc dich chinh van la 2 thu KHONG the kiem bang unit test:
  1. 3 con so dem duoc tinh DUNG bang SQL subquery tren du lieu that.
  2. Bo loc buoc/qua_han chay DUNG trong SQL (total va phan trang dung theo).
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from adapters.postgres.cr_session_repo import CrSessionRepo
from application.get_sessions_use_case import GetSessionsUseCase
from domain.entities.cr_session import CrStatus
from domain.ports.outbound.repo_ports import SessionFilter
from tests.integration.fixtures_tien_trinh import (  # noqa: F401 - fixture dung qua ten
    TRAM_CHO_KPI,
    TRAM_CR_LOI,
    TRAM_QUA_HAN,
    TRAM_XONG,
    du_lieu_tien_trinh,
)


@pytest_asyncio.fixture
async def use_case(db_session):
    return GetSessionsUseCase(CrSessionRepo(db_session))


async def _lay_theo_id(use_case, cr_session_id: int):
    """Tim dong theo cr_session_id - KHONG tim theo q=<tram_id>.

    Chac chan hon: id la khoa chinh, khong phu thuoc `q` tim trong cot nao. Va
    fixture tra ve id nen khong can doan."""
    page = await use_case.execute(SessionFilter(page=None, size=None))
    khop = [r for r in page.items if r.session.id == cr_session_id]
    assert len(khop) == 1, f"khong tim thay dung 1 dong cho cr_session_id={cr_session_id}"
    return khop[0]


class TestBuocHienTai:
    async def test_da_xuat_phieu_la_buoc_4(self, use_case, du_lieu_tien_trinh):
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["xong"])
        assert row.session.xuat_phieu_at is not None
        assert row.buoc_hien_tai == 4

    async def test_cho_kpi_la_buoc_2(self, use_case, du_lieu_tien_trinh):
        # KHONG con guard skip: fixture vua tao session nay voi xuat_phieu_at
        # NULL ngay truoc do, khong co cach nao no "da troi sang buoc 4".
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["cho_kpi"])
        assert row.session.xuat_phieu_at is None
        assert row.buoc_hien_tai == 2

    async def test_cr_loi_la_buoc_1(self, use_case, du_lieu_tien_trinh):
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["cr_loi"])
        assert row.session.status == CrStatus.FAILED
        assert row.buoc_hien_tai == 1

    async def test_cr_loi_khong_co_ngay_du_kien(self, use_case, du_lieu_tien_trinh):
        # executed_at NULL -> khong co moc de cong AFTER_DAYS.
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["cr_loi"])
        assert row.session.executed_at is None
        assert row.ngay_du_kien_xuat_phieu is None
        assert row.con_bao_nhieu_ngay is None


class TestConBaoNhieuNgay:
    async def test_qua_han_co_so_ngay_AM(self, use_case, du_lieu_tien_trinh):
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["qua_han"])
        assert row.session.xuat_phieu_at is None
        assert row.con_bao_nhieu_ngay is not None
        assert row.con_bao_nhieu_ngay < 0, "session nay la case qua han - phai ra so AM"

    async def test_cho_kpi_con_so_ngay_DUONG(self, use_case, du_lieu_tien_trinh):
        # Doi xung voi test tren. Truoc day KHONG kiem duoc vi mock CHO_KPI da
        # troi qua han tu luc nao khong biet - gio fixture tao no cach hom nay
        # 2 ngay nen chac chan chua den han.
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["cho_kpi"])
        assert row.con_bao_nhieu_ngay is not None
        assert row.con_bao_nhieu_ngay > 0

    async def test_ngay_du_kien_khop_con_bao_nhieu_ngay(self, use_case, du_lieu_tien_trinh):
        # 2 truong phai nhat quan: ngay_du_kien - hom nay == con_bao_nhieu_ngay.
        # Truyen bay_gio TUONG MINH de phep tru khong bi lech khi test chay
        # dung luc qua nua dem.
        bay_gio = datetime.now(timezone.utc)
        hom_nay_vn = (bay_gio + timedelta(hours=7)).date()

        page = await use_case.execute(SessionFilter(page=None, size=None), bay_gio=bay_gio)
        co_du_lieu = [r for r in page.items if r.ngay_du_kien_xuat_phieu is not None]
        assert co_du_lieu, "fixture da tao 3 session co executed_at"

        for row in co_du_lieu:
            assert (row.ngay_du_kien_xuat_phieu - hom_nay_vn).days == row.con_bao_nhieu_ngay


class TestConSoDem:
    async def test_3_con_so_khong_am_va_dung_quan_he(self, use_case, du_lieu_tien_trinh):
        # Bat bug tich Descartes: neu join 2 bang con roi COUNT(*) thi 2 con so
        # phieu se bi NHAN len theo so affected cell (6 cell x 4 phieu = 24).
        # Rang buoc that: so phieu (da xuat + cho tay) KHONG BAO GIO vuot so
        # cell bi anh huong - moi phieu ung voi 1 cell cua session do.
        page = await use_case.execute(SessionFilter(page=None, size=None))
        assert page.items

        for row in page.items:
            s = row.session
            assert s.so_cell_anh_huong >= 0
            assert s.so_phieu_da_xuat >= 0
            assert s.so_cell_cho_xuat_tay >= 0
            if s.so_cell_anh_huong > 0:
                assert s.so_phieu_da_xuat + s.so_cell_cho_xuat_tay <= s.so_cell_anh_huong, (
                    f"session {s.id}: so phieu vuot so cell bi anh huong - "
                    "dau hieu COUNT bi nhan len do join sai"
                )

    async def test_dem_dung_6_cell_va_4_phieu_da_xuat(self, use_case, du_lieu_tien_trinh):
        # Fixture tao DUNG 6 cell + 4 phieu SUCCESS + 0 dong KHONG_XUAT_*.
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["xong"])
        assert row.session.so_cell_anh_huong == 6
        assert row.session.so_phieu_da_xuat == 4
        assert row.session.so_cell_cho_xuat_tay == 0

    async def test_session_khong_co_cell_dem_ra_0_khong_phai_None(
        self, use_case, du_lieu_tien_trinh
    ):
        # Session CHO_KPI co Y de 0 cell - subquery COUNT phai ra 0, khong duoc
        # tra None (FE se hien "null" thay vi "0").
        row = await _lay_theo_id(use_case, du_lieu_tien_trinh["cho_kpi"])
        assert row.session.so_cell_anh_huong == 0
        assert row.session.so_phieu_da_xuat == 0
        assert row.session.so_cell_cho_xuat_tay == 0


class TestBoLoc:
    async def test_loc_buoc_1_chi_ra_session_dang_chay_hoac_loi(self, use_case, du_lieu_tien_trinh):
        page = await use_case.execute(SessionFilter(buoc=1, page=None, size=None))
        for row in page.items:
            assert row.buoc_hien_tai == 1
            assert row.session.status in (CrStatus.FAILED, CrStatus.RUNNING)
        assert du_lieu_tien_trinh["cr_loi"] in {r.session.id for r in page.items}

    async def test_loc_buoc_2_chi_ra_session_chua_xuat_phieu(self, use_case, du_lieu_tien_trinh):
        page = await use_case.execute(SessionFilter(buoc=2, page=None, size=None))
        for row in page.items:
            assert row.buoc_hien_tai == 2
            assert row.session.xuat_phieu_at is None
        ids = {r.session.id for r in page.items}
        assert du_lieu_tien_trinh["cho_kpi"] in ids
        assert du_lieu_tien_trinh["qua_han"] in ids

    async def test_loc_buoc_4_chi_ra_session_da_xuat_phieu(self, use_case, du_lieu_tien_trinh):
        page = await use_case.execute(SessionFilter(buoc=4, page=None, size=None))
        for row in page.items:
            assert row.buoc_hien_tai == 4
            assert row.session.xuat_phieu_at is not None
        assert du_lieu_tien_trinh["xong"] in {r.session.id for r in page.items}

    async def test_tong_3_buoc_bang_tong_khong_loc(self, use_case, du_lieu_tien_trinh):
        # 3 buoc phai PHU KIN va KHONG CHONG NHAU - neu ho thi co session bien
        # mat khoi ca 3 tab tren UI, khong ai nhin thay.
        tong = (await use_case.execute(SessionFilter(page=None, size=None))).total
        cong_don = 0
        for buoc in (1, 2, 4):
            cong_don += (await use_case.execute(SessionFilter(buoc=buoc, page=None, size=None))).total
        assert cong_don == tong

    async def test_loc_qua_han_chi_ra_session_chua_xuat_va_da_tre(
        self, use_case, du_lieu_tien_trinh
    ):
        page = await use_case.execute(SessionFilter(qua_han=True, page=None, size=None))
        for row in page.items:
            assert row.session.xuat_phieu_at is None, "qua han thi phai CHUA xuat phieu"
            assert row.con_bao_nhieu_ngay is not None
            assert row.con_bao_nhieu_ngay < 0, "qua han thi so ngay con lai phai AM"

    async def test_session_qua_han_nam_trong_ket_qua(self, use_case, du_lieu_tien_trinh):
        page = await use_case.execute(SessionFilter(qua_han=True, page=None, size=None))
        assert du_lieu_tien_trinh["qua_han"] in {r.session.id for r in page.items}

    async def test_da_xuat_phieu_KHONG_nam_trong_qua_han(self, use_case, du_lieu_tien_trinh):
        page = await use_case.execute(SessionFilter(qua_han=True, page=None, size=None))
        assert du_lieu_tien_trinh["xong"] not in {r.session.id for r in page.items}

    async def test_cho_kpi_chua_den_han_KHONG_nam_trong_qua_han(
        self, use_case, du_lieu_tien_trinh
    ):
        # Truoc day KHONG kiem duoc: mock CHO_KPI da troi qua han. Gio fixture
        # tao no cach hom nay 2 ngay nen chac chan chua den han.
        page = await use_case.execute(SessionFilter(qua_han=True, page=None, size=None))
        assert du_lieu_tien_trinh["cho_kpi"] not in {r.session.id for r in page.items}

    async def test_total_khop_so_dong_khi_loc(self, use_case, du_lieu_tien_trinh):
        # total PHAI dem sau khi ap bo loc (loc trong SQL), khong phai dem het
        # roi moi loc o Python - neu sai thi phan trang tren UI lech han.
        page = await use_case.execute(SessionFilter(buoc=4, page=None, size=None))
        assert page.total == len(page.items)


class TestAnToanDuLieuTest:
    async def test_khong_session_test_nao_roi_vao_ngay_job_quet(
        self, use_case, du_lieu_tien_trinh
    ):
        """Du lieu test KHONG duoc roi vao dien quet cua job xuat phieu THAT.

        Job quet: ngay CR == hom nay - XUAT_PHIEU_AFTER_DAYS VA status thuoc
        whitelist. Roi trung = scheduler that POST PHIEU THAT len CTS, khong
        thu hoi duoc. Fixture da chan bang _kiem_offset_an_toan(), test nay
        kiem lai tren DU LIEU DA VAO DB (chan ca truong hop tinh ngay sai).
        """
        from application.xuat_phieu_use_case import (
            XUAT_PHIEU_AFTER_DAYS,
            XUAT_PHIEU_STATUS_WHITELIST,
            _to_gmt7,
        )

        ngay_job_quet = (datetime.now(timezone.utc) + timedelta(hours=7)).date() - timedelta(
            days=XUAT_PHIEU_AFTER_DAYS
        )
        page = await use_case.execute(SessionFilter(page=None, size=None))
        cua_test = [r.session for r in page.items if r.session.id in set(du_lieu_tien_trinh.values())]
        assert len(cua_test) == 4

        for s in cua_test:
            if s.executed_at is None or s.status.value not in XUAT_PHIEU_STATUS_WHITELIST:
                continue
            assert _to_gmt7(s.executed_at).date() != ngay_job_quet, (
                f"NGUY HIEM: session test {s.id} ({s.tram_id}) co ngay CR trung "
                "ngay job quet - scheduler THAT se xuat phieu that cho no"
            )
