"""
Unit test cho GetSessionsUseCase — 6 truong tien trinh (16082026).
Tu: yeu cau truc tiep user - man hinh theo doi tien trinh 4 buoc cua FE.

MOCK session_repo (I/O). 3 con so dem (so_cell_anh_huong/so_phieu_da_xuat/
so_cell_cho_xuat_tay) do REPO dien bang subquery - o day gia lap san tren
entity de kiem router/use case truyen dung, con phan SQL dem that duoc kiem o
tests/integration/test_cr_session_repo.py.

bay_gio LUON truyen tuong minh - test khong duoc phu thuoc dong ho may (mai
chay lai se ra ket qua khac).
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

from application.get_sessions_use_case import (
    GetSessionsUseCase,
    tinh_buoc_hien_tai,
    tinh_ngay_du_kien,
)
from application.xuat_phieu_use_case import XUAT_PHIEU_AFTER_DAYS
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.outbound.repo_ports import Page, SessionFilter

# KHONG dat pytestmark = pytest.mark.asyncio: pytest.ini da co
# asyncio_mode = auto (tu nhan dien async def), va dat marker o module se ap
# nham len ca test dong bo -> PytestWarning moi lan chay.

_GMT7 = timezone(timedelta(hours=7))

# THOI GIAN TRONG FILE NAY LUON LA UTC - dung y het thu repo tra ve
# (executed_at/xuat_phieu_at la TIMESTAMPTZ, SQLAlchemy doc len thanh datetime
# aware UTC). QUAN TRONG: _to_gmt7() lam .replace(tzinfo=utc) VO DIEU KIEN, nen
# neu test truyen datetime gan san tzinfo=+07:00 thi no bi DIEN GIAI LAI thanh
# UTC - test se "xanh" ma khong kiem dung thu can kiem.
#
# 05:00 UTC = 12h trua GMT+7: xa ranh gioi ngay o ca 2 mui nen cac phep tru
# ngay khong bao gio lam lech sang ngay khac.
BAY_GIO = datetime(2026, 8, 16, 5, 0, tzinfo=timezone.utc)
HOM_NAY = BAY_GIO.astimezone(_GMT7).date()  # 2026-08-16


def _session(
    session_id: int = 1,
    status: CrStatus = CrStatus.DONE,
    executed_at: datetime | None = None,
    xuat_phieu_at: datetime | None = None,
    **kwargs,
) -> CrSession:
    return CrSession(
        id=session_id,
        tram_id="110548",
        action="shutdown",
        status=status,
        plan_name="plan_test",
        executed_at=executed_at,
        xuat_phieu_at=xuat_phieu_at,
        **kwargs,
    )


def _use_case(sessions: list[CrSession]):
    repo = AsyncMock()
    repo.list.return_value = Page(items=sessions, total=len(sessions))
    return GetSessionsUseCase(repo), repo


# === buoc_hien_tai: 4 nhanh ===


def test_buoc_1_khi_status_failed():
    # CR loi -> dung o buoc 1, KHONG di tiep duoc.
    assert tinh_buoc_hien_tai(_session(status=CrStatus.FAILED)) == 1


def test_buoc_1_khi_status_running():
    assert tinh_buoc_hien_tai(_session(status=CrStatus.RUNNING)) == 1


def test_buoc_1_khi_status_khong_chay():
    # THEM 16/10/2026 (yeu cau truc tiep user, "TRANG THAI KHONG_CHAY") - CR
    # chua tung gui lenh len NetAct van la "dung o buoc 1" GIONG HET FAILED
    # (CHI khac nguyen nhan hien thi, khong khac tien trinh) - xem
    # _BUOC_1_STATUS o dau file.
    assert tinh_buoc_hien_tai(_session(status=CrStatus.KHONG_CHAY)) == 1


def test_buoc_2_khi_chua_xuat_phieu():
    # CR xong, dang cho thu thap KPI 7 ngay.
    s = _session(status=CrStatus.DONE, executed_at=BAY_GIO, xuat_phieu_at=None)
    assert tinh_buoc_hien_tai(s) == 2


def test_buoc_4_khi_da_xuat_phieu():
    s = _session(status=CrStatus.DONE, executed_at=BAY_GIO, xuat_phieu_at=BAY_GIO)
    assert tinh_buoc_hien_tai(s) == 4


def test_status_duoc_xet_TRUOC_xuat_phieu_at():
    # Session FAILED ma van co xuat_phieu_at (khong nen xay ra, nhung khong co
    # rang buoc DB nao cam) phai hien "CR loi", KHONG phai "da xuat phieu xong".
    s = _session(status=CrStatus.FAILED, xuat_phieu_at=BAY_GIO)
    assert tinh_buoc_hien_tai(s) == 1


def test_khong_bao_gio_tra_ve_buoc_3():
    # Buoc 3 (dang danh gia) la trang thai thoang qua trong 1 luot job, khong
    # luu lai duoc -> quet HET moi to hop status x xuat_phieu_at, phai khong co
    # cai nao ra 3.
    ket_qua = {
        tinh_buoc_hien_tai(_session(status=st, xuat_phieu_at=xp))
        for st in CrStatus
        for xp in (None, BAY_GIO)
    }
    assert 3 not in ket_qua
    assert ket_qua <= {1, 2, 4}


# === ngay_du_kien_xuat_phieu + con_bao_nhieu_ngay ===


def test_ngay_du_kien_None_khi_chua_chay_cr():
    assert tinh_ngay_du_kien(_session(executed_at=None)) is None


def test_ngay_du_kien_bang_ngay_cr_cong_after_days():
    # 02:15 UTC 01/08 = 09:15 GMT+7 cung ngay -> ngay CR la 01/08.
    ngay_cr = datetime(2026, 8, 1, 2, 15, tzinfo=timezone.utc)
    ket_qua = tinh_ngay_du_kien(_session(executed_at=ngay_cr))
    assert ket_qua == date(2026, 8, 1) + timedelta(days=XUAT_PHIEU_AFTER_DAYS)


def test_ngay_du_kien_tinh_theo_lich_GMT7_khong_phai_UTC():
    # 17:30 UTC ngay 01/08 = 00:30 GMT+7 ngay 02/08 -> ngay CR phai la 02/08.
    # Lay .date() THANG tren UTC se ra 01/08 (SAI 1 NGAY) - day dung la bug
    # C1.4-fix8 da gap that o EvaluateCrUseCase. Khung UTC 17:00-23:59 la khung
    # DUY NHAT lam lo ra bug nay.
    ngay_cr = datetime(2026, 8, 1, 17, 30, tzinfo=timezone.utc)
    ket_qua = tinh_ngay_du_kien(_session(executed_at=ngay_cr))

    assert ket_qua == date(2026, 8, 2) + timedelta(days=XUAT_PHIEU_AFTER_DAYS)
    # Khang dinh nguoc: KHONG duoc bang ket qua cua cach tinh sai (theo UTC).
    assert ket_qua != date(2026, 8, 1) + timedelta(days=XUAT_PHIEU_AFTER_DAYS)


async def test_con_bao_nhieu_ngay_duong_khi_chua_toi_han():
    # CR hom nay -> con dung XUAT_PHIEU_AFTER_DAYS ngay nua.
    uc, _ = _use_case([_session(executed_at=BAY_GIO)])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    assert page.items[0].con_bao_nhieu_ngay == XUAT_PHIEU_AFTER_DAYS


async def test_con_bao_nhieu_ngay_bang_0_dung_ngay_du_kien():
    # 0 = DUNG hom nay, phai phan biet duoc voi None (chua co ngay du kien).
    ngay_cr = BAY_GIO - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
    uc, _ = _use_case([_session(executed_at=ngay_cr)])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    assert page.items[0].con_bao_nhieu_ngay == 0


async def test_con_bao_nhieu_ngay_AM_khi_qua_han():
    # Qua han 3 ngay -> -3. Day la gia tri FE dung de to do canh bao.
    ngay_cr = BAY_GIO - timedelta(days=XUAT_PHIEU_AFTER_DAYS + 3)
    uc, _ = _use_case([_session(executed_at=ngay_cr)])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    assert page.items[0].con_bao_nhieu_ngay == -3


async def test_con_bao_nhieu_ngay_None_khi_chua_chay_cr():
    # None chu KHONG phai 0 - 0 da mang nghia "dung hom nay".
    uc, _ = _use_case([_session(status=CrStatus.FAILED, executed_at=None)])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    assert page.items[0].ngay_du_kien_xuat_phieu is None
    assert page.items[0].con_bao_nhieu_ngay is None


# === 3 con so dem (repo dien, use case chi chuyen tiep) ===


async def test_3_con_so_dem_duoc_giu_nguyen_tu_repo():
    s = _session(
        executed_at=BAY_GIO,
        so_cell_anh_huong=17,
        so_phieu_da_xuat=4,
        so_cell_cho_xuat_tay=2,
    )
    uc, _ = _use_case([s])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    item = page.items[0].session
    assert (item.so_cell_anh_huong, item.so_phieu_da_xuat, item.so_cell_cho_xuat_tay) == (17, 4, 2)


async def test_3_con_so_mac_dinh_0_khi_repo_khong_dien():
    uc, _ = _use_case([_session(executed_at=BAY_GIO)])
    page = await uc.execute(SessionFilter(), bay_gio=BAY_GIO)
    item = page.items[0].session
    assert (item.so_cell_anh_huong, item.so_phieu_da_xuat, item.so_cell_cho_xuat_tay) == (0, 0, 0)


# === Bo loc ===


async def test_loc_buoc_duoc_chuyen_thang_xuong_repo():
    # Loc phai xay ra trong SQL (de total/phan trang dung) - use case KHONG duoc
    # tu loc list sau khi fetch.
    uc, repo = _use_case([])
    await uc.execute(SessionFilter(buoc=2), bay_gio=BAY_GIO)
    assert repo.list.await_args.args[0].buoc == 2


async def test_qua_han_duoc_dich_thanh_ngay_moc_cu_the():
    # qua_han=True (y dinh) -> qua_han_truoc_ngay=<ngay> (SQL dung duoc).
    # Hang so XUAT_PHIEU_AFTER_DAYS KHONG duoc ro ri xuong repo.
    uc, repo = _use_case([])
    await uc.execute(SessionFilter(qua_han=True), bay_gio=BAY_GIO)
    filter_da_gui = repo.list.await_args.args[0]
    assert filter_da_gui.qua_han_truoc_ngay == HOM_NAY - timedelta(days=XUAT_PHIEU_AFTER_DAYS)


async def test_khong_qua_han_thi_khong_dien_ngay_moc():
    uc, repo = _use_case([])
    await uc.execute(SessionFilter(qua_han=False), bay_gio=BAY_GIO)
    assert repo.list.await_args.args[0].qua_han_truoc_ngay is None


async def test_total_giu_nguyen_tu_repo_khong_dem_lai():
    # total la tong ban ghi KHOP filter (co the > so dong tren 1 trang) - use
    # case KHONG duoc thay bang len(items).
    repo = AsyncMock()
    repo.list.return_value = Page(items=[_session(executed_at=BAY_GIO)], total=57)
    page = await GetSessionsUseCase(repo).execute(SessionFilter(), bay_gio=BAY_GIO)
    assert page.total == 57
    assert len(page.items) == 1


# === CACH C (16082026) - KHONG_DU_DU_LIEU la trang thai CUOI ===


def test_KHONG_DU_DU_LIEU_la_buoc_4_khong_phai_buoc_2():
    # Session nay co xuat_phieu_at IS NULL nhu buoc 2, nhung da KET THUC:
    # execute_all_pending() chi quet DONE + EVAL_PENDING nen no khong bao gio
    # duoc xet lai. Xep vao buoc 2 se hien "dang cho thu thap KPI" MAI MAI.
    s = _session(status=CrStatus.KHONG_DU_DU_LIEU, executed_at=BAY_GIO, xuat_phieu_at=None)
    assert tinh_buoc_hien_tai(s) == 4


def test_KHONG_DU_DU_LIEU_van_la_4_ke_ca_khi_co_xuat_phieu_at():
    s = _session(status=CrStatus.KHONG_DU_DU_LIEU, executed_at=BAY_GIO, xuat_phieu_at=BAY_GIO)
    assert tinh_buoc_hien_tai(s) == 4


def test_status_buoc_1_van_uu_tien_hon_KHONG_DU_DU_LIEU():
    # Thu tu xet khong bi ve moi lam hong: FAILED/RUNNING van ra 1.
    for st in (CrStatus.FAILED, CrStatus.RUNNING):
        assert tinh_buoc_hien_tai(_session(status=st, xuat_phieu_at=None)) == 1


def test_van_khong_bao_gio_tra_ve_buoc_3_sau_khi_them_status_moi():
    # Quet lai HET to hop - status moi khong duoc lam lo ra buoc 3.
    ket_qua = {
        tinh_buoc_hien_tai(_session(status=st, xuat_phieu_at=xp))
        for st in CrStatus
        for xp in (None, BAY_GIO)
    }
    assert 3 not in ket_qua
    assert ket_qua <= {1, 2, 4}


def test_PARTIAL_SUCCESS_xu_nhu_DONE_khong_phai_buoc_1():
    # CR da chay xong, chi mot so DN hong -> di tiep sang buoc cho KPI.
    # Xep vao buoc 1 se hien "CR loi" trong khi phan lon tram DA doi tham so.
    s = _session(status=CrStatus.PARTIAL_SUCCESS, executed_at=BAY_GIO, xuat_phieu_at=None)
    assert tinh_buoc_hien_tai(s) == 2


def test_PARTIAL_SUCCESS_da_xuat_phieu_thi_buoc_4():
    s = _session(status=CrStatus.PARTIAL_SUCCESS, executed_at=BAY_GIO, xuat_phieu_at=BAY_GIO)
    assert tinh_buoc_hien_tai(s) == 4
