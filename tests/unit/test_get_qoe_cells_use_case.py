"""
Unit test cho GetQoeCellsUseCase - danh gia QoE PER-CELL (16082026).
MOCK soc_gw/repo, KHONG goi API that.

Trong tam: 3 thu chi sai duoc o day chu khong o dau khac:
  1. Tach ket qua theo TEN CELL (khong zip theo thu tu)
  2. Cell thieu du lieu chi hong RIENG no, khong keo ca session
  3. So request goi CEM: 2 (1/cua so), KHONG phai 2 x so_cell
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from application.get_qoe_cells_use_case import (
    _QOE_CELL_THRESHOLD_DELTA,
    SNAPSHOT_HAN_GOI_LAI_NGAY,
    GetQoeCellsUseCase,
)
from application.xuat_phieu_use_case import cua_so_danh_gia
from domain.entities.cr_session import CrSession, CrStatus
from domain.services.evaluation_service import MUC_TOI_THIEU, EvaluationService

SESSION_ID = 553
CELL_A = "4G-SSN087M43-HNI"
CELL_B = "4G-SSN104M12-HNI"
CELL_C = "4G-SSN019M41-HNI"

# CR chay 02:15 UTC = 09:15 GMT+7 ngay 22/07 -> cua so truoc 15..21/07,
# sau 23..29/07.
EXECUTED_AT = datetime(2026, 7, 22, 2, 15, tzinfo=timezone.utc)

# executed_at "GAN DAY" (09/2026, E1 - han goi lai CEM): moi test kiem hanh
# vi "cache thieu -> VAN goi CEM" (khac test han goi lai) PHAI dung ngay GAN
# HOM NAY, khong phai hang so EXECUTED_AT co dinh o tren - EXECUTED_AT la
# ngay THAT trong qua khu (2026-07-22), ngay cang troi qua (test chay o thoi
# diem khac) khoang cach toi "hom nay" cang xa, som muon se VUOT
# SNAPSHOT_HAN_GOI_LAI_NGAY va lam sai KET QUA nhung test do (khong con goi
# CEM du dang test dung tinh huong "chua qua han").
EXECUTED_AT_GAN_DAY = datetime.now(timezone.utc) - timedelta(days=1)


def _diem(ngay_bat_dau: str, values: list[float]) -> list[dict]:
    """Sinh diem QoE 1 ngay/1 gia tri, dinh dang giong het CemHttpAdapter tra ve."""
    nam, thang, ngay = (int(x) for x in ngay_bat_dau.split("-"))
    goc = datetime(nam, thang, ngay)
    from datetime import timedelta

    return [
        {"time": (goc + timedelta(days=i)).date().isoformat() + "T00:00:00", "qoe": v}
        for i, v in enumerate(values)
    ]


def _ngay_bat_dau(executed_at: datetime, cs_key: str) -> str:
    """"before_from"/"after_from" ("YYYY-MM-DD") tinh THAT tu executed_at, dung
    CHINH cong thuc cua_so_danh_gia() (khong tu tinh lai). Dung khi mock fixture
    can KHOP voi cua so danh gia THAT (D2, 09/2026: execute() gio LOC LAI
    after_raw theo allowed_dates truoc khi tinh avg - fixture dung ngay bia
    khong lien quan executed_at se bi loc RONG)."""
    return cua_so_danh_gia(executed_at)[cs_key].strftime("%Y-%m-%d")


def _use_case(
    cells: list[str], before_raw: list[dict], after_raw: list[dict], executed_at: datetime = EXECUTED_AT
):
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = CrSession(
        id=SESSION_ID,
        tram_id="112721",
        action="shutdown",
        status=CrStatus.DONE,
        plan_name="plan_test",
        executed_at=executed_at,
    )
    affected_repo = AsyncMock()
    affected_repo.get_by_cr_session_id.return_value = [{"cell_name": c} for c in cells]

    soc_gw = AsyncMock()
    soc_gw.get_qoe.side_effect = [before_raw, after_raw]

    uc = GetQoeCellsUseCase(session_repo, affected_repo, soc_gw, EvaluationService())
    return uc, soc_gw


def _theo_ten(ket_qua):
    return {r.cell_name: r for r in ket_qua}


# === Tach theo ten cell ===


async def test_tach_dung_theo_cell_name_khong_zip_theo_thu_tu():
    # Gateway tra ve THEO THU TU KHAC voi thu tu gui di - zip theo index se gan
    # diem cua CELL_B cho CELL_A.
    before = [
        {"cell_name": CELL_B, "metrics": _diem("2026-07-15", [1.0] * 7)},
        {"cell_name": CELL_A, "metrics": _diem("2026-07-15", [5.0] * 7)},
    ]
    after = [
        {"cell_name": CELL_B, "metrics": _diem("2026-07-23", [1.0] * 7)},
        {"cell_name": CELL_A, "metrics": _diem("2026-07-23", [5.0] * 7)},
    ]
    uc, _ = _use_case([CELL_A, CELL_B], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.avg_before == 5.0
    assert r[CELL_B].qoe_eval.avg_before == 1.0


async def test_giu_dung_thu_tu_cell_nhu_danh_sach_affected():
    before = [{"cell_name": c, "metrics": _diem("2026-07-15", [5.0] * 7)} for c in (CELL_C, CELL_A, CELL_B)]
    after = [{"cell_name": c, "metrics": _diem("2026-07-23", [5.0] * 7)} for c in (CELL_C, CELL_A, CELL_B)]
    uc, _ = _use_case([CELL_A, CELL_B, CELL_C], before, after)

    ket_qua = await uc.execute(SESSION_ID)
    assert [r.cell_name for r in ket_qua] == [CELL_A, CELL_B, CELL_C]


# === Cell thieu du lieu ===


async def test_cell_thieu_du_lieu_chi_hong_rieng_no():
    # CELL_B vang mat hoan toan trong response (CEM bo qua cell khong co data).
    # CELL_A phai van duoc danh gia binh thuong.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [5.0] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [5.0] * 7)}]
    uc, _ = _use_case([CELL_A, CELL_B], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "PASS"
    assert r[CELL_B].qoe_eval.result == "INSUFFICIENT_DATA"
    assert r[CELL_B].so_ngay_before == 0
    assert r[CELL_B].so_ngay_after == 0
    assert r[CELL_B].delta is None  # khong co avg de tru


async def test_duoi_5_ngay_la_insufficient_rieng_cell_do():
    # MIN_DAYS_REQUIRED=5: CELL_B chi co 4 ngay sau.
    before = [{"cell_name": c, "metrics": _diem("2026-07-15", [5.0] * 7)} for c in (CELL_A, CELL_B)]
    after = [
        {"cell_name": CELL_A, "metrics": _diem("2026-07-23", [5.0] * 7)},
        {"cell_name": CELL_B, "metrics": _diem("2026-07-23", [5.0] * 4)},
    ]
    uc, _ = _use_case([CELL_A, CELL_B], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "PASS"
    assert r[CELL_B].qoe_eval.result == "INSUFFICIENT_DATA"
    assert r[CELL_B].so_ngay_after == 4


async def test_ngay_thieu_thi_bo_chia_cho_so_ngay_thuc_co():
    # 5 ngay [5,5,5,5,1] -> avg = 21/5 = 4.2, KHONG phai 21/7.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [5.0] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [5.0, 5.0, 5.0, 5.0, 1.0])}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.avg_after == 4.2
    assert r[CELL_A].so_ngay_after == 5


# === So request goi CEM ===


async def test_dung_2_lan_goi_get_qoe_bat_ke_bao_nhieu_cell():
    # 1 lan/cua so, moi lan gui CA danh sach cell. 17 cell van la 2 lan goi
    # (CemHttpAdapter tu tach thanh 7 (before) + 8 (after RONG, D2) request
    # ben trong = 15 request - so lan goi get_qoe() o MUC USE CASE nay van
    # la 2, khong doi).
    # Copy may moc "1 cell/lan" nhu QoS se thanh 17 x 2 = 34 lan goi = 238 request.
    cells = [f"4G-CELL-{i:02d}" for i in range(17)]
    before = [{"cell_name": c, "metrics": _diem("2026-07-15", [5.0] * 7)} for c in cells]
    after = [{"cell_name": c, "metrics": _diem("2026-07-23", [5.0] * 7)} for c in cells]
    uc, soc_gw = _use_case(cells, before, after)

    ket_qua = await uc.execute(SESSION_ID)
    assert len(ket_qua) == 17
    assert soc_gw.get_qoe.await_count == 2


async def test_moi_lan_goi_gui_ca_danh_sach_cell():
    cells = [CELL_A, CELL_B, CELL_C]
    before = [{"cell_name": c, "metrics": _diem("2026-07-15", [5.0] * 7)} for c in cells]
    after = [{"cell_name": c, "metrics": _diem("2026-07-23", [5.0] * 7)} for c in cells]
    uc, soc_gw = _use_case(cells, before, after)

    await uc.execute(SESSION_ID)
    for call in soc_gw.get_qoe.await_args_list:
        assert call.args[0] == cells


async def test_khong_co_cell_nao_thi_khong_goi_gateway():
    uc, soc_gw = _use_case([], [], [])
    assert await uc.execute(SESSION_ID) == []
    assert soc_gw.get_qoe.await_count == 0


# === Nguong danh gia ===


async def test_threshold_la_0_5_giong_qos_khong_phai_0_1():
    # SUA 04092026: nguong cap CELL doi 0.2 -> 0.5 (cap SESSION giu 0.1).
    # SUA 03/10/2026: doi dau thanh so DUONG (xem domain/services/
    # evaluation_service.py muc "SUA 03/10/2026").
    assert _QOE_CELL_THRESHOLD_DELTA == 0.5

    # delta = +0.4 (TUT): FAIL neu dung nguong 0.1, PASS neu dung nguong 0.5.
    # avg_after 3.6 >= 3.0 de ket qua CHI phu thuoc threshold, khong dinh
    # ve muc toi thieu.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [4.0] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [3.6] * 7)}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "PASS"


async def test_tut_qua_nguong_du_avg_after_tot_van_FAIL():
    # DOI VERDICT 04092026 (truoc: PASS). Ten cu
    # test_tut_nhieu_nhung_avg_after_tren_4_van_pass - test dung VE DA BI BO
    # ("tut nhieu nhung con tot thi cuu").
    # delta = 5.0 - 4.0 = 1.0 (TUT), qua nguong 0.5. avg_after 4.0 rat tot
    # nhung KHONG con cuu duoc.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [5.0] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [4.0] * 7)}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "FAIL"
    assert r[CELL_A].qoe_eval.avg_after >= MUC_TOI_THIEU  # qua san, van FAIL vi delta
    assert r[CELL_A].qoe_eval.ly_do_khong_dat == "TUT_QUA_NHIEU"


async def test_duoi_muc_toi_thieu_thi_FAIL_du_tut_it():
    # Ve MOI: avg_after 2.5 < 3.0 -> FAIL bat ke delta chi +0.1 (tut it).
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [2.6] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [2.5] * 7)}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "FAIL"
    assert r[CELL_A].qoe_eval.ly_do_khong_dat == "DUOI_MUC_TOI_THIEU"


async def test_truong_tham_khao_lo_ra_ngay_te():
    # SUA SO LIEU (khong noi long assert): before cu la [5.0]x7 -> delta
    # -0.571, qua nguong -0.5 nen luat moi tra FAIL va test khong con co lap
    # duoc dieu no muon kiem. Ha before xuong 4.5 (delta +0.07), GIU NGUYEN
    # ngay diem 1 - do moi la thu test nay noi ve.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [4.5] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [5, 5, 5, 5, 5, 5, 1])}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].qoe_eval.result == "PASS"
    assert r[CELL_A].qoe_eval.diem_thap_nhat_sau == 1
    assert r[CELL_A].qoe_eval.so_ngay_dat_sau == 6  # 6/7 ngay >= 3.0


async def test_delta_dung_chieu_duong_la_tut():
    # SUA 03/10/2026: delta = avg_before - avg_after, DUONG = tut (truoc day
    # la avg_after - avg_before, AM = tut) - xem domain/services/
    # evaluation_service.py muc "SUA 03/10/2026". 5.0 -> 3.0 la TUT 2 diem.
    before = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [5.0] * 7)}]
    after = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [3.0] * 7)}]
    uc, _ = _use_case([CELL_A], before, after)

    r = _theo_ten(await uc.execute(SESSION_ID))
    assert r[CELL_A].delta == 2.0  # DUONG = tut


# === LAZY CACHE snapshot (20082026) ===
# Muc tieu: KHONG goi CEM lai khi snapshot da du. Cua so T-7..T+7 quanh 1 ngay
# CR trong qua khu la BAT BIEN nen goi lai chi ton thoi gian.


def _snapshot_rows(cells: list[str], so_ngay_before: int = 7, so_ngay_after: int = 7):
    """Dong snapshot dang IQoeSnapshotRepo.get_by_session_id() tra ve."""
    from datetime import date, timedelta

    rows = []
    for c in cells:
        for i in range(so_ngay_before):
            rows.append(
                {
                    "cell_name": c,
                    "snapshot_date": date(2026, 7, 15) + timedelta(days=i),
                    "qoe_score": 4.0,
                    "period": "before",
                }
            )
        for i in range(so_ngay_after):
            rows.append(
                {
                    "cell_name": c,
                    "snapshot_date": date(2026, 7, 23) + timedelta(days=i),
                    "qoe_score": 3.0,
                    "period": "after",
                }
            )
    return rows


def _dem_tu_rows(rows):
    dem = {}
    for r in rows:
        khoa = (r["cell_name"], r["period"])
        dem[khoa] = dem.get(khoa, 0) + 1
    return dem


def _use_case_co_cache(
    cells: list[str], rows, before_raw=None, after_raw=None, executed_at: datetime = EXECUTED_AT
):
    uc, soc_gw = _use_case(cells, before_raw or [], after_raw or [], executed_at)
    repo = AsyncMock()
    repo.get_by_session_id.return_value = rows
    repo.dem_ngay_theo_cell.return_value = _dem_tu_rows(rows)
    uc._snapshot_repo = repo  # noqa: SLF001 - bom thang, khong dung DI cho test
    return uc, soc_gw, repo


async def test_du_snapshot_thi_KHONG_goi_CEM():
    cells = [CELL_A, CELL_B]
    uc, soc_gw, _ = _use_case_co_cache(cells, _snapshot_rows(cells))

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert soc_gw.get_qoe.await_count == 0, "du snapshot ma van goi CEM"
    # Ket qua phai TINH DUOC tu snapshot, khong phai rong: 4.0 -> 3.0
    assert ket_qua[CELL_A].qoe_eval.avg_before == 4.0
    assert ket_qua[CELL_A].qoe_eval.avg_after == 3.0


async def test_thieu_ngay_cua_1_cell_thi_goi_CEM_lai_ca_lo():
    # CEM nhan cells[] la mang nen goi 1 cell hay 17 cell deu 15 request (D2)
    # - khong tach rieng phan thieu.
    cells = [CELL_A, CELL_B]
    rows = [r for r in _snapshot_rows(cells) if not (r["cell_name"] == CELL_B and r["period"] == "after")]
    before_raw = [{"cell_name": c, "metrics": _diem("2026-07-15", [4.0] * 7)} for c in cells]
    after_raw = [{"cell_name": c, "metrics": _diem("2026-07-23", [3.0] * 7)} for c in cells]
    # executed_at GAN DAY (khong dung hang so EXECUTED_AT co dinh trong qua
    # khu) - test nay kiem "cache thieu -> VAN goi CEM" (CHUA qua han), xem
    # EXECUTED_AT_GAN_DAY.
    uc, soc_gw, _ = _use_case_co_cache(cells, rows, before_raw, after_raw, executed_at=EXECUTED_AT_GAN_DAY)

    await uc.execute(SESSION_ID)

    assert soc_gw.get_qoe.await_count == 2


async def test_chua_co_snapshot_nao_thi_goi_CEM_va_LUU_du_15_dong_3_period():
    # SUA 09/2026 (D1/D2) - after_raw gio la ket qua fetch RONG (tu ngay_cr T
    # den T+7, 8 ngay) thay vi chi T+1..T+7 (7 ngay) nhu truoc, de co diem
    # luu period="cr_day". before(7) + cr_day(1) + after(7) = 15 dong/cell -
    # dung con so F yeu cau ("Snapshot: ca 2 duong ghi ra DUNG 15 dong/cell
    # voi du 3 period").
    cells = [CELL_A]
    before_from = _ngay_bat_dau(EXECUTED_AT_GAN_DAY, "before_from")
    ngay_cr = _ngay_bat_dau(EXECUTED_AT_GAN_DAY, "ngay_cr")
    before_raw = [{"cell_name": CELL_A, "metrics": _diem(before_from, [4.0] * 7)}]
    # 8 gia tri: [0]=ngay T (cr_day), [1:]=T+1..T+7 (after) - GIA TRI KHAC
    # nhau de phan biet ro trong assert ben duoi (T=3.5, sau=3.0).
    after_raw_rong = [{"cell_name": CELL_A, "metrics": _diem(ngay_cr, [3.5] + [3.0] * 7)}]
    uc, soc_gw, repo = _use_case_co_cache(
        cells, [], before_raw, after_raw_rong, executed_at=EXECUTED_AT_GAN_DAY
    )

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert soc_gw.get_qoe.await_count == 2
    # avg_after PHAI la 3.0 (T+1..T+7), KHONG bi diem ngay T (3.5) tron vao -
    # xem D2/loc_diem_theo_ngay().
    assert ket_qua[CELL_A].qoe_eval.avg_after == 3.0
    repo.upsert_many.assert_awaited_once()
    diem = repo.upsert_many.await_args.args[1]
    assert len(diem) == 15, "7 before + 1 cr_day + 7 after = 15 dong/cell"
    assert {d["period"] for d in diem} == {"before", "cr_day", "after"}
    assert {d["cell_name"] for d in diem} == {CELL_A}
    diem_cr_day = next(d for d in diem if d["period"] == "cr_day")
    assert diem_cr_day["qoe_score"] == 3.5, "diem ngay T PHAI duoc luu rieng, khong bi loai bo"


async def test_luu_snapshot_that_bai_KHONG_lam_hong_ket_qua():
    # Cache hong chi mat toi uu, khong duoc lam nguoi dung mat ket qua.
    cells = [CELL_A]
    before_from = _ngay_bat_dau(EXECUTED_AT_GAN_DAY, "before_from")
    ngay_cr = _ngay_bat_dau(EXECUTED_AT_GAN_DAY, "ngay_cr")
    before_raw = [{"cell_name": CELL_A, "metrics": _diem(before_from, [4.0] * 7)}]
    after_raw_rong = [{"cell_name": CELL_A, "metrics": _diem(ngay_cr, [3.5] + [3.0] * 7)}]
    uc, _, repo = _use_case_co_cache(cells, [], before_raw, after_raw_rong, executed_at=EXECUTED_AT_GAN_DAY)
    repo.upsert_many.side_effect = RuntimeError("DB down")

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert ket_qua[CELL_A].qoe_eval.avg_after == 3.0


async def test_khong_co_snapshot_repo_thi_chay_y_nhu_truoc():
    # Moi cho tao use case cu (khong truyen repo) phai khong doi hanh vi.
    cells = [CELL_A]
    before_raw = [{"cell_name": CELL_A, "metrics": _diem("2026-07-15", [4.0] * 7)}]
    after_raw = [{"cell_name": CELL_A, "metrics": _diem("2026-07-23", [3.0] * 7)}]
    uc, soc_gw = _use_case(cells, before_raw, after_raw)

    await uc.execute(SESSION_ID)

    assert soc_gw.get_qoe.await_count == 2


# === HAN GOI LAI CEM (E1, 09/2026; SUA 02/10/2026) ===
# CEM khong backfill lo thung du lieu qua khu (16/07, 21-27/07, session 553
# THAT) - "thieu < 7 ngay -> goi lai" VO DIEU KIEN se thanh vong goi vo han.
# Qua SNAPSHOT_HAN_GOI_LAI_NGAY (default 14) ke tu ngay CR: KHONG goi CEM
# nua, tra nguyen cache dang co (du thieu) - NHUNG CHI khi DA TUNG co it
# nhat 1 lan luu truoc do (dem KHONG rong). "Chua tung luu gi" (dem RONG)
# thi LUON goi CEM it nhat 1 lan, bat ke qua han hay chua - xem
# test_qua_han_chua_tung_co_snapshot_VAN_goi_CEM (sua 02/10/2026, BUG THAT:
# ban cu han ca truong hop chua tung thu).


async def test_qua_han_snapshot_thieu_van_KHONG_goi_lai_CEM():
    cells = [CELL_A]
    # Qua han: SNAPSHOT_HAN_GOI_LAI_NGAY (14) + 1 ngay du de chac chan vuot,
    # khong phu thuoc lam tron gio/mui gio.
    executed_at = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_HAN_GOI_LAI_NGAY + 1)
    # Snapshot THIEU RO RET: 3/7 ngay before, 0/7 ngay after - binh thuong day
    # la tin hieu "goi lai CEM" (xem test_thieu_ngay_cua_1_cell_thi_goi_CEM_lai_ca_lo),
    # nhung qua han nen PHAI bi chan.
    rows = _snapshot_rows(cells, so_ngay_before=3, so_ngay_after=0)
    uc, soc_gw, _ = _use_case_co_cache(cells, rows, executed_at=executed_at)

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert soc_gw.get_qoe.await_count == 0, "qua han -> KHONG duoc goi CEM du snapshot con thieu"
    # Van tra ket qua tu 3 ngay cache dang co (khong phai crash/rong hoan toan).
    assert ket_qua[CELL_A].so_ngay_before == 3
    assert ket_qua[CELL_A].so_ngay_after == 0


async def test_qua_han_chua_tung_co_snapshot_VAN_goi_CEM():
    # SUA 02/10/2026 (BUG THAT, xem "SUA 02/10/2026" trong docstring
    # _doc_snapshot_qoe_neu_du()): ban CU coi "chua tung luu + qua han" la
    # DU dieu kien bo cuoc, lam 1 session/cell CHUA TUNG duoc thu goi CEM
    # lan nao (vd lan dau tien ai do mo tab QoE da hon 14 ngay sau CR) bi
    # KHOA VINH VIEN thanh INSUFFICIENT_DATA du CEM van con du lieu that -
    # "qua han" chi dung nghia khi DA TUNG thu it nhat 1 lan (xem test
    # test_qua_han_snapshot_thieu_van_KHONG_goi_lai_CEM o tren, van dung).
    # Bien: KHONG CO dong snapshot nao (chua tung luu, khac test tren la co
    # nhung thieu).
    cells = [CELL_A]
    executed_at = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_HAN_GOI_LAI_NGAY + 1)
    before_from = _ngay_bat_dau(executed_at, "before_from")
    ngay_cr = _ngay_bat_dau(executed_at, "ngay_cr")
    before_raw = [{"cell_name": CELL_A, "metrics": _diem(before_from, [4.0] * 7)}]
    after_raw_rong = [{"cell_name": CELL_A, "metrics": _diem(ngay_cr, [3.5] + [3.0] * 7)}]
    uc, soc_gw, _ = _use_case_co_cache(cells, [], before_raw, after_raw_rong, executed_at=executed_at)

    ket_qua = _theo_ten(await uc.execute(SESSION_ID))

    assert soc_gw.get_qoe.await_count == 2, "chua tung thu lan nao -> PHAI goi CEM, du da qua han"
    assert ket_qua[CELL_A].qoe_eval.avg_before == 4.0
    assert ket_qua[CELL_A].qoe_eval.avg_after == 3.0


async def test_chua_qua_han_snapshot_thieu_van_goi_lai_CEM_binh_thuong():
    # Doi chung voi 2 test tren: DUNG NGAY han (14 ngay dung, KHONG +1) van
    # phai goi CEM binh thuong - han la ">", khong phai ">=" (an tay o bien).
    cells = [CELL_A]
    executed_at = datetime.now(timezone.utc) - timedelta(days=SNAPSHOT_HAN_GOI_LAI_NGAY)
    rows = _snapshot_rows(cells, so_ngay_before=3, so_ngay_after=0)
    before_from = _ngay_bat_dau(executed_at, "before_from")
    ngay_cr = _ngay_bat_dau(executed_at, "ngay_cr")
    before_raw = [{"cell_name": CELL_A, "metrics": _diem(before_from, [4.0] * 7)}]
    after_raw_rong = [{"cell_name": CELL_A, "metrics": _diem(ngay_cr, [3.5] + [3.0] * 7)}]
    uc, soc_gw, _ = _use_case_co_cache(cells, rows, before_raw, after_raw_rong, executed_at=executed_at)

    await uc.execute(SESSION_ID)

    assert soc_gw.get_qoe.await_count == 2, "DUNG NGAY han (khong vuot) van phai goi CEM binh thuong"


# === HAU KIEM = DUNG CELL ANH HUONG DA LUU (18/10/2026) ===
# Doi xung voi test cung ten ben test_qos_cells_use_case.py - bang QoE phai ra
# DUNG danh sach cr_affected_cells, giu thu tu, cell CEM khong tra van giu dong.

_16_CELL = [f"4G-TXN{n:03d}M{s}-HNI" for n, s in [
    (90, 51), (90, 11), (407, 41), (407, 51), (407, 11), (92, 42), (96, 42), (96, 52),
    (96, 12), (12, 41), (12, 11), (92, 52), (92, 12), (92, 32), (250, 11), (250, 21),
]]


async def test_16_cell_anh_huong_ra_DUNG_16_dong_cung_ten_cung_thu_tu_va_cell_thieu_van_co_dong():
    # CEM tra nguoc thu tu VA bo han cell thu 6 (khong co du lieu).
    co_du_lieu = [c for i, c in enumerate(_16_CELL) if i != 5][::-1]
    before = [{"cell_name": c, "metrics": _diem("2026-07-15", [4.0] * 7)} for c in co_du_lieu]
    after = [{"cell_name": c, "metrics": _diem("2026-07-23", [4.0] * 7)} for c in co_du_lieu]
    uc, _ = _use_case(_16_CELL, before, after)

    ket_qua = await uc.execute(SESSION_ID)

    assert [r.cell_name for r in ket_qua] == _16_CELL
    assert ket_qua[5].qoe_eval.result == "INSUFFICIENT_DATA"
    assert ket_qua[0].qoe_eval.result == "PASS"


# === MOT NGUON SO LIEU (18/10/2026) ===
# Session DA DANH GIA (xuat_phieu_at co gia tri) + co snapshot -> dung DUNG
# snapshot do, KHONG goi lai CEM du con thieu ngay va chua qua han goi lai.


async def test_da_danh_gia_snapshot_thieu_ngay_KHONG_goi_lai_CEM_va_tra_ngay_chup():
    from datetime import date

    cells = [CELL_A]
    chup = datetime(2026, 10, 13, 1, 12, tzinfo=timezone.utc)
    rows = [{**r, "created_at": chup} for r in _snapshot_rows(cells, so_ngay_after=6)]
    # executed_at GAN DAY -> duong lazy cu SE goi lai CEM vi thieu ngay; da
    # danh gia thi khong duoc goi.
    uc, soc_gw, _ = _use_case_co_cache(cells, rows, executed_at=EXECUTED_AT_GAN_DAY)
    uc._session_repo.get_by_id.return_value.xuat_phieu_at = chup  # noqa: SLF001

    ket_qua, cs = await uc.danh_gia_kem_cua_so(SESSION_ID)

    soc_gw.get_qoe.assert_not_awaited()
    assert ket_qua[0].so_ngay_after == 6
    assert cs["ngay_chup_snapshot"] == date(2026, 10, 13)


async def test_chua_danh_gia_giu_co_che_lazy_cu_goi_CEM_khi_thieu():
    cells = [CELL_A]
    rows = _snapshot_rows(cells, so_ngay_after=3)
    uc, soc_gw, _ = _use_case_co_cache(cells, rows, executed_at=EXECUTED_AT_GAN_DAY)

    _, cs = await uc.danh_gia_kem_cua_so(SESSION_ID)

    assert soc_gw.get_qoe.await_count == 2
    assert cs["ngay_chup_snapshot"] is None
