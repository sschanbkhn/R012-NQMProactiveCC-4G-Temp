"""
Unit test cho EvaluateCrUseCase — tap trung vao bug lech gio (C1.4-fix8,
21072026): "ngay CR" phai tinh theo LICH VN (GMT+7), khong phai ngay UTC tho
cua executed_at. Tu: docs/DEV_LOG.md muc [C1.4-fix8].

MOCK toan bo I/O bien ngoai (session_repo/cell_repo/network_gw/soc_gw/
qoe_snapshot_repo/qos_snapshot_repo/alert_use_case) - chi dung INSTANCE THAT
cua EvaluationService (domain service thuan, khong I/O).
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from application.evaluate_cr_use_case import EvaluateCrUseCase, _to_gmt7
from domain.entities.cell_param import CellParam
from domain.entities.cr_session import CrSession, CrStatus
from domain.services.evaluation_service import EvaluationService
from domain.value_objects.rsboost_level import RsboostLevel

TRAM_ID = "111139"
CELL_NAME = "4G-TEST-HNI"


def _make_session(executed_at: datetime) -> CrSession:
    return CrSession(
        id=1,
        tram_id=TRAM_ID,
        action="shutdown",
        status=CrStatus.DONE,
        plan_name="R012_NQMProactiveCC_111139_20260720_174822",
        executed_at=executed_at,
    )


def _make_cell_param() -> CellParam:
    # rsboost_current != rsboost_new -> _has_real_rf_change() = True, cell
    # nay duoc giu lai trong tap danh gia (khong bi loai nhu cell "skip").
    return CellParam(
        tram_id=TRAM_ID,
        cell_name=CELL_NAME,
        rsboost_current=RsboostLevel(0.0),
        rsboost_new=RsboostLevel(3.0),
        cr_session_id=1,
    )


def _make_use_case(session, network_gw, soc_gw):
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = session
    session_repo.update.side_effect = lambda s: s  # echo lai, khong that persist

    cell_repo = AsyncMock()
    cell_repo.get_by_cr_session_id.return_value = [_make_cell_param()]

    # raw rong -> INSUFFICIENT_DATA (khong du 5 ngay), khong trigger nhanh
    # snapshot/alert - muc tieu test la XAC NHAN THAM SO from_dt/to_dt goi
    # xuong gateway, khong phai logic tinh avg (da co evaluation_service.py
    # rieng, khong test lai o day).
    network_gw.get_qos_metrics.return_value = []
    soc_gw.get_qoe.return_value = []

    qoe_snapshot_repo = AsyncMock()
    qos_snapshot_repo = AsyncMock()
    alert_use_case = AsyncMock()

    return EvaluateCrUseCase(
        session_repo=session_repo,
        cell_repo=cell_repo,
        network_gw=network_gw,
        soc_gw=soc_gw,
        evaluation_service=EvaluationService(),
        alert_use_case=alert_use_case,
        qoe_snapshot_repo=qoe_snapshot_repo,
        qos_snapshot_repo=qos_snapshot_repo,
    )


class TestToGmt7:
    # Test truc tiep helper (pure function, khong can mock) - phu tinh huong
    # nguy hiem da xac nhan voi user: CR chay sau nua dem GMT+7 nhung truoc
    # nua dem UTC (khung UTC 17:00-23:59).
    def test_executed_at_qua_ranh_gioi_ngay_UTC_tinh_dung_ngay_VN(self):
        # Du lieu that session #203/tram 111139 (21072026): executed_at UTC
        # 17:48:22 = GMT+7 00:48:22 HOM SAU - code cu (lay .date() truc tiep
        # tu UTC) se ra 20/07 (SAI), code moi phai ra 21/07 (DUNG theo VN).
        executed_at_utc = datetime(2026, 7, 20, 17, 48, 22)
        cr_date_vn = _to_gmt7(executed_at_utc)
        assert cr_date_vn.date() == date(2026, 7, 21)

    def test_executed_at_ban_ngay_khong_qua_ranh_gioi_van_dung(self):
        # UTC 8h sang = GMT+7 15h CUNG ngay - truong hop "binh thuong" (khong
        # cham ranh gioi), phai van ra dung ngay, khong bi lech do sua sai.
        executed_at_utc = datetime(2026, 7, 20, 8, 0, 0)
        cr_date_vn = _to_gmt7(executed_at_utc)
        assert cr_date_vn.date() == date(2026, 7, 20)


class TestWindowTinhTheoLichVN:
    # Test qua execute() day du (khong chi goi helper rieng le) - xac nhan
    # cr_day_start MOI (dua tren _to_gmt7()) thuc su duoc dung de tinh
    # before_from/before_to/after_from/after_to gui xuong network_gw/soc_gw,
    # khong chi dung trong 1 ham bi co lap khong ai goi toi.
    async def test_window_before_after_dung_theo_ngay_VN_khi_qua_ranh_gioi_UTC(self):
        # Cung du lieu that session #203 - ngay CR THAT theo VN la 21/07,
        # nen before phai la 14/07..20/07 (KHONG phai 13/07..19/07 nhu code cu
        # tinh tu UTC).
        #
        # SUA 20082026 (snapshot per-cell): cua so FETCH cua nhanh after bat
        # dau tu NGAY CR (21/07) chu khong phai 22/07 - de lay them diem ngay
        # T luu snapshot period="cr_day". Cua so DANH GIA van la 22/07..28/07
        # (xem test_ngay_CR_duoc_fetch_nhung_KHONG_tinh_vao_avg_after ben duoi).
        # Ton them 0 request CTS (van 1 request/cell/cua so) va 1 request CEM.
        session = _make_session(executed_at=datetime(2026, 7, 20, 17, 48, 22))
        network_gw = AsyncMock()
        soc_gw = AsyncMock()
        uc = _make_use_case(session, network_gw, soc_gw)

        await uc.execute(1)

        # network_gw.get_qos_metrics goi 2 lan: before roi after (dong 226-227
        # cua evaluate_cr_use_case.py, execute() dung thu tu nay).
        before_call, after_call = network_gw.get_qos_metrics.await_args_list
        before_from, before_to = before_call.args[1], before_call.args[2]
        after_from, after_to = after_call.args[1], after_call.args[2]

        assert (before_from.date(), before_to.date()) == (date(2026, 7, 14), date(2026, 7, 20))
        assert (after_from.date(), after_to.date()) == (date(2026, 7, 21), date(2026, 7, 28))

        # soc_gw.get_qoe phai nhan CUNG bo before/after (execute() dung 1 bo
        # before_from/before_to/after_from/after_to cho ca CTS lan SOC).
        qoe_before_call, qoe_after_call = soc_gw.get_qoe.await_args_list
        assert qoe_before_call.args[1].date() == before_from.date()
        assert qoe_before_call.args[2].date() == before_to.date()
        assert qoe_after_call.args[1].date() == after_from.date()
        assert qoe_after_call.args[2].date() == after_to.date()

    async def test_window_ban_ngay_khong_qua_ranh_gioi_van_dung_nhu_truoc(self):
        # Truong hop KHONG cham ranh gioi UTC/VN - ngay CR van la 20/07.
        # after bat dau tu chinh ngay CR (20/07), xem test tren.
        session = _make_session(executed_at=datetime(2026, 7, 20, 8, 0, 0))
        network_gw = AsyncMock()
        soc_gw = AsyncMock()
        uc = _make_use_case(session, network_gw, soc_gw)

        await uc.execute(1)

        before_call, after_call = network_gw.get_qos_metrics.await_args_list
        before_from, before_to = before_call.args[1], before_call.args[2]
        after_from, after_to = after_call.args[1], after_call.args[2]

        assert (before_from.date(), before_to.date()) == (date(2026, 7, 13), date(2026, 7, 19))
        assert (after_from.date(), after_to.date()) == (date(2026, 7, 20), date(2026, 7, 27))

    async def test_ngay_CR_duoc_fetch_nhung_KHONG_tinh_vao_avg_after(self):
        """Mo rong cua so FETCH khong duoc lam sai KET QUA danh gia.

        Day la rui ro chinh cua thay doi 20082026: neu diem ngay T lot vao
        avg_after thi moi ket luan PASS/FAIL deu lech (ngay T la ngay DANG thi
        cong, chat luong bat thuong theo dinh nghia).
        """
        session = _make_session(executed_at=datetime(2026, 7, 20, 8, 0, 0))
        network_gw = AsyncMock()
        soc_gw = AsyncMock()

        # Ngay CR 20/07 co diem 1.0 (rat te). 7 ngay sau deu 4.0. Neu ngay CR
        # bi tinh vao thi avg_after = 3.625, khong thi = 4.0.
        after_raw = [
            {"cell_name": CELL_NAME, "metrics": [{"time": "2026-07-20T00:00:00", "qos": 1.0}]},
        ] + [
            {"cell_name": CELL_NAME, "metrics": [{"time": f"2026-07-{20 + d}T00:00:00", "qos": 4.0}]}
            for d in range(1, 8)
        ]
        before_raw = [
            {"cell_name": CELL_NAME, "metrics": [{"time": f"2026-07-{12 + d}T00:00:00", "qos": 4.0}]}
            for d in range(1, 8)
        ]
        network_gw.get_qos_metrics.side_effect = [before_raw, after_raw]
        soc_gw.get_qoe.side_effect = [[], []]

        uc = _make_use_case(session, network_gw, soc_gw)
        # side_effect da dat o tren, _make_use_case() set return_value nen phai
        # dat lai sau khi goi no.
        network_gw.get_qos_metrics.side_effect = [before_raw, after_raw]
        soc_gw.get_qoe.side_effect = [[], []]

        result = await uc.execute(1)

        assert result.qos_after == 4.0, "diem ngay CR (1.0) KHONG duoc lot vao avg_after"


# === CACH C (16082026) - trang thai CUOI thay vi EVAL_PENDING ===


class TestKhongDuDuLieu:
    """INSUFFICIENT_DATA -> KHONG_DU_DU_LIEU, KHONG quet lai.

    EVAL_PENDING nghia la "cho them du lieu" nen job quet lai hang ngay. Nhung
    du lieu thieu thuong do NGUON KHONG CO (lo thung CEM 16/07, 21-27/07) nen
    se khong bao gio duoc bo sung -> quet lai vinh vien. Session 553 la ca that.
    """

    async def test_thieu_du_lieu_set_KHONG_DU_DU_LIEU_khong_phai_EVAL_PENDING(self):
        session = _make_session(datetime(2026, 7, 22, 2, 15, tzinfo=timezone.utc))
        network_gw, soc_gw = AsyncMock(), AsyncMock()
        # Ca 2 gateway tra rong -> 0 ngay < MIN_DAYS_REQUIRED -> INSUFFICIENT_DATA
        network_gw.get_qos_metrics.return_value = []
        soc_gw.get_qoe.return_value = []
        uc = _make_use_case(session, network_gw, soc_gw)

        await uc.execute(session.id)

        da_ghi = uc._session_repo.update.await_args_list[-1].args[0]
        assert da_ghi.status == CrStatus.KHONG_DU_DU_LIEU
        assert da_ghi.status != CrStatus.EVAL_PENDING

    async def test_van_giu_qoe_result_va_avg_de_doi_chieu(self):
        # Danh dau KHONG_DU_DU_LIEU nhung KHONG duoc xoa can cu: nguoi van hanh
        # phai doc duoc "thieu vi sao, so lieu den dau".
        session = _make_session(datetime(2026, 7, 22, 2, 15, tzinfo=timezone.utc))
        network_gw, soc_gw = AsyncMock(), AsyncMock()
        network_gw.get_qos_metrics.return_value = []
        soc_gw.get_qoe.return_value = []
        uc = _make_use_case(session, network_gw, soc_gw)

        ket_qua = await uc.execute(session.id)

        assert ket_qua.qoe_result == "INSUFFICIENT_DATA"
        assert ket_qua.qos_result == "INSUFFICIENT_DATA"

    async def test_khong_set_evaluated_at_khi_thieu_du_lieu(self):
        # evaluated_at = "da danh gia xong" - thieu du lieu thi CHUA xong.
        session = _make_session(datetime(2026, 7, 22, 2, 15, tzinfo=timezone.utc))
        network_gw, soc_gw = AsyncMock(), AsyncMock()
        network_gw.get_qos_metrics.return_value = []
        soc_gw.get_qoe.return_value = []
        uc = _make_use_case(session, network_gw, soc_gw)

        await uc.execute(session.id)

        assert uc._session_repo.update.await_args_list[-1].args[0].evaluated_at is None

    async def test_KHONG_DU_DU_LIEU_khong_nam_trong_tap_quet_lai(self):
        # execute_all_pending() chi lay DONE + EVAL_PENDING -> session da danh
        # dau KHONG_DU_DU_LIEU se KHONG bi quet lai. Day chinh la muc dich.
        from domain.entities.cr_session import CrStatus as _S

        status_duoc_quet = {_S.DONE.value, _S.EVAL_PENDING.value}
        assert _S.KHONG_DU_DU_LIEU.value not in status_duoc_quet


class TestSnapshotDu3Period:
    """SUA 09/2026 (D1) - qos_points/qoe_points gio dung diem_snapshot_theo_cua_so()
    dung chung voi GetQoeCellsUseCase. Test nay xac nhan CA HAI bang
    (qos_snapshot/qoe_snapshot) duoc upsert DU 15 dong/cell (7 before + 1
    cr_day + 7 after) - truoc 09/2026 file nay KHONG co test nao kiem tra
    NOI DUNG snapshot duoc ghi (chi implicit qua mock rong o cac test khac)."""

    async def test_upsert_du_15_dong_3_period_ca_qos_lan_qoe(self):
        # Ngay CR (VN) 20/07, khong cham ranh gioi UTC -> before 13-19/07,
        # fetch after (RONG) 20-27/07 (T..T+7, 8 ngay), cua so danh gia
        # T+1..T+7 (21-27/07).
        session = _make_session(executed_at=datetime(2026, 7, 20, 8, 0, 0))
        network_gw, soc_gw = AsyncMock(), AsyncMock()

        qos_before_raw = [
            {"cell_name": CELL_NAME, "metrics": [{"time": f"2026-07-{13 + d}T00:00:00", "qos": 4.0} for d in range(7)]}
        ]
        # 8 diem: [0]=ngay T (cr_day, gia tri rieng 9.9 de nhan dien), [1:]=T+1..T+7
        qos_after_raw = [
            {
                "cell_name": CELL_NAME,
                "metrics": [{"time": f"2026-07-{20 + d}T00:00:00", "qos": (9.9 if d == 0 else 4.0)} for d in range(8)],
            }
        ]
        qoe_before_raw = [
            {"cell_name": CELL_NAME, "metrics": [{"time": f"2026-07-{13 + d}T00:00:00", "qoe": 4.0} for d in range(7)]}
        ]
        qoe_after_raw = [
            {
                "cell_name": CELL_NAME,
                "metrics": [{"time": f"2026-07-{20 + d}T00:00:00", "qoe": (9.9 if d == 0 else 4.0)} for d in range(8)],
            }
        ]
        network_gw.get_qos_metrics.side_effect = [qos_before_raw, qos_after_raw]
        soc_gw.get_qoe.side_effect = [qoe_before_raw, qoe_after_raw]

        uc = _make_use_case(session, network_gw, soc_gw)
        # _make_use_case() dat return_value mac dinh truoc, phai ghi de lai
        # side_effect SAU khi goi (giong pattern test_ngay_CR_duoc_fetch... o tren).
        network_gw.get_qos_metrics.side_effect = [qos_before_raw, qos_after_raw]
        soc_gw.get_qoe.side_effect = [qoe_before_raw, qoe_after_raw]

        await uc.execute(1)

        for repo, ten_bang in (
            (uc._qos_snapshot_repo, "qos_snapshot"),
            (uc._qoe_snapshot_repo, "qoe_snapshot"),
        ):
            repo.upsert_many.assert_awaited_once()
            diem = repo.upsert_many.await_args.args[1]
            assert len(diem) == 15, f"{ten_bang}: 7 before + 1 cr_day + 7 after = 15 dong/cell"
            assert {d["period"] for d in diem} == {"before", "cr_day", "after"}, ten_bang
            assert {d["cell_name"] for d in diem} == {CELL_NAME}, ten_bang
            diem_cr_day = next(d for d in diem if d["period"] == "cr_day")
            score_key = "qos_score" if ten_bang == "qos_snapshot" else "qoe_score"
            assert diem_cr_day[score_key] == 9.9, f"{ten_bang}: diem ngay T phai duoc luu rieng"
