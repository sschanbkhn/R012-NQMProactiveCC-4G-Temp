"""
Unit test cho XuatPhieuUseCase.execute_all_pending() (JOB TU DONG buoc 2/4).

MOCK toan bo I/O (repo/gateway) - KHONG POST that len CTS/TTS: gateway LUON la
AsyncMock. V2 (12/08) da bo dry_run nen day la lop an toan duy nhat.
DUNG THAT EvaluationService (domain service thuan, khong I/O) - giong
tests/unit/test_xuat_phieu_use_case.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from application.xuat_phieu_use_case import (
    KET_QUA_DA_XUAT as TRANG_THAI_KET_QUA_DA_XUAT,
    KET_QUA_KHONG_CAN_XUAT as TRANG_THAI_KET_QUA_KHONG_CAN_XUAT,
    KET_QUA_LOI as TRANG_THAI_KET_QUA_LOI,
    TRANG_THAI_HET_LUOT_THU,
    TRANG_THAI_THIEU_DU_LIEU,
    TRANG_THAI_VUOT_GIOI_HAN,
    XUAT_PHIEU_AFTER_DAYS,
    XUAT_PHIEU_MAX_PER_SECTOR,
    XUAT_PHIEU_MAX_RETRY,
    XuatPhieuUseCase,
)
from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.outbound.repo_ports import Page
from domain.services.evaluation_service import MIN_DAYS_REQUIRED, EvaluationService

SESSION_ID = 42
TRAM_ID = "111139"

# executed_at PHAI tz-aware: _lay_session_du_dieu_kien() so sanh voi cutoff
# tz-aware (cot TIMESTAMPTZ tu C1.4-fix10 doc len la aware) - dung naive o day
# se che mat bug that "can't compare offset-naive and offset-aware".
#
# V1 (PA A, 12/08): dieu kien la "==" chu khong con "<=" - ngay CR phai cach hom
# nay DUNG XUAT_PHIEU_AFTER_DAYS ngay, mot moc co dinh kieu "30 ngay truoc" se
# KHONG con duoc quet. Chon 12h trua GMT+7 de doi mui gio khong bao gio lam
# lech sang ngay khac.
_GMT7_TEST = timezone(timedelta(hours=7))
_NGAY_CR_TEST = datetime.now(_GMT7_TEST).date() - timedelta(days=XUAT_PHIEU_AFTER_DAYS)
EXECUTED_AT = datetime(
    _NGAY_CR_TEST.year, _NGAY_CR_TEST.month, _NGAY_CR_TEST.day, 12, 0, tzinfo=_GMT7_TEST
)
_CR_DAY_START = datetime(EXECUTED_AT.year, EXECUTED_AT.month, EXECUTED_AT.day)


def _points(base_day_offset: int, values: list[float]) -> list[dict]:
    # Sinh diem QoS quanh ngay CR - moi gia tri 1 ngay rieng biet (>=5 ngay moi
    # du MIN_DAYS_REQUIRED cua EvaluationService).
    return [
        {
            "time": (_CR_DAY_START + timedelta(days=base_day_offset + i)).strftime("%Y-%m-%dT00:00:00Z"),
            "qos": v,
        }
        for i, v in enumerate(values)
    ]


def _make_session(session_id: int = SESSION_ID) -> CrSession:
    return CrSession(
        id=session_id,
        tram_id=TRAM_ID,
        action="shutdown",
        status=CrStatus.DONE,
        plan_name="R012_NQMProactiveCC_111139_TEST",
        executed_at=EXECUTED_AT,
    )


def _make_use_case(
    cells: list[str],
    qos_sau_theo_cell: dict[str, list[float]],
    phieu_da_co: list[dict] | None = None,
    sessions: list[CrSession] | None = None,
    status_theo_filter: dict | None = None,
    qos_snapshot_repo=None,
    # THEM 04/10/2026 (luat xuat phieu toi da 2/sector) - mac dinh None cho
    # MOI cell (giu nguyen hanh vi test cu: tat ca cell roi vao 1 "sector"
    # rieng = None). Test nao can mo phong nhieu sector thi truyen dict
    # {cell_name: sector}, cell khong co trong dict van la None.
    sector_theo_cell: dict[str, int] | None = None,
):
    """cells: danh sach cell_name cua session. qos_sau_theo_cell: QoS 7 ngay SAU
    cua tung cell (QoS TRUOC luon 5.0 x5 ngay) - do te = 5.0 - avg(sau), cang
    lon cang te."""
    sector_theo_cell = sector_theo_cell or {}
    phieu_da_co = phieu_da_co or []
    cell_da_success = {p["cell_name"] for p in phieu_da_co if p["trang_thai"] == "SUCCESS"}

    cr_session_repo = AsyncMock()
    if status_theo_filter is not None:
        # Whitelist status (viec 2b): use case goi list() RIENG cho tung status
        # -> mock tra ve theo dung status duoc hoi, de test kiem duoc status nao
        # thuc su duoc quet.
        async def _list_theo_status(filters):
            return Page(items=status_theo_filter.get(filters.status, []), total=0)

        cr_session_repo.list.side_effect = _list_theo_status
    else:
        # Use case goi list() RIENG cho tung status trong whitelist -> mock phai
        # LOC theo status duoc hoi, neu tra nguyen danh sach cho ca 3 lan thi
        # session bi dem 3 lan. Loc (khong dem so lan goi) de test nao goi 2 lan
        # van chay dung.
        danh_sach = sessions or [_make_session()]

        async def _list_loc_theo_status(filters):
            khop = [s for s in danh_sach if s.status.value == filters.status]
            return Page(items=khop, total=len(khop))

        cr_session_repo.list.side_effect = _list_loc_theo_status
    cr_session_repo.get_by_id.side_effect = lambda sid: _make_session(sid)

    cr_affected_cells_repo = AsyncMock()
    cr_affected_cells_repo.get_by_cr_session_id.return_value = [
        {"cell_name": c, "tram_id": TRAM_ID, "huong_id": "11", "sector": sector_theo_cell.get(c)}
        for c in cells
    ]

    cr_phieu_repo = AsyncMock()
    # B9 - AsyncMock tra Mock TRUTHY cho method chua khai bao; khong dat None
    # thi test roi vao nhanh "da co phieu trong thang" va khong chay toi phan dang test
    cr_phieu_repo.get_success_cung_thang.return_value = None
    # Dong cu khong khai bao so_lan_thu -> mac dinh 0 (giong dong tao truoc
    # migration them cot).
    phieu_da_co = [{"so_lan_thu": 0, **p} for p in phieu_da_co]
    cr_phieu_repo.get_by_cr_session_id.return_value = phieu_da_co
    # execute() tu check trung lan nua (lop 2) - tra dung dong SUCCESS neu co
    cr_phieu_repo.get_by_session_cell.side_effect = lambda sid, cell: (
        {"id": 99, "trang_thai": "SUCCESS", "phieu_id": "TTS-CU"} if cell in cell_da_success else None
    )
    cr_phieu_repo.insert.return_value = {"id": 1}

    enodeb_repo = AsyncMock()
    enodeb_repo.get_by_tram_id.return_value = {
        "tram_name": "4G-TEST001M-HNI",
        "ma_tinh": "HNI",
        "ma_csht": "CSHT-HNI-999",
        "ten_thiet_bi": "Nokia AirScale",
        "ten_quan_ly": "Cau Giay",
    }

    truoc = _points(-7, [5.0] * 5)

    async def _qos_side_effect(cell_name, from_dt, to_dt):
        if from_dt < _CR_DAY_START:
            return truoc
        return _points(1, qos_sau_theo_cell[cell_name])

    qos_sparkline_use_case = AsyncMock()
    qos_sparkline_use_case.execute.side_effect = _qos_side_effect

    save_cell_clm_gateway = AsyncMock()
    # V2: gateway khong con che do preview - phai tra hinh dang response THAT.
    save_cell_clm_gateway.save_cell_clm.return_value = {
        "status_code": 200, "isError": False, "code": "200", "message": "OK",
        "data": 19177, "totalRecord": 1,
    }

    job_run_log_repo = AsyncMock()

    use_case = XuatPhieuUseCase(
        cr_phieu_repo=cr_phieu_repo,
        cr_session_repo=cr_session_repo,
        cr_affected_cells_repo=cr_affected_cells_repo,
        enodeb_repo=enodeb_repo,
        qos_sparkline_use_case=qos_sparkline_use_case,
        save_cell_clm_gateway=save_cell_clm_gateway,
        evaluation_service=EvaluationService(),  # domain service THAT, khong mock
        job_run_log_repo=job_run_log_repo,
        qos_snapshot_repo=qos_snapshot_repo,
    )
    return use_case, save_cell_clm_gateway, job_run_log_repo


def _cell_da_goi_xuat(gateway) -> list[str]:
    # Thu tu goi save_cell_clm = thu tu xuat phieu that su -> dung de kiem tra
    # sap xep "te nhat truoc".
    return [call.args[0]["TenCell"] for call in gateway.save_cell_clm.call_args_list]


async def test_session_du_ngay_co_cell_khong_dat_xuat_dung_so_cell():
    # 2 cell KHONG DAT (do te 4.0 va 3.0) + 1 cell DAT (do te 0.05 <= 0.2).
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE", "CELL_VUA", "CELL_DAT"],
        qos_sau_theo_cell={
            "CELL_TE": [1.0] * 5,
            "CELL_VUA": [2.0] * 5,
            "CELL_DAT": [4.95] * 5,
        },
    )

    ket_qua = await use_case.execute_all_pending()

    assert ket_qua["so_session_quet"] == 1
    # CHI 2 cell KHONG DAT duoc xuat - CELL_DAT khong goi gateway lan nao
    assert _cell_da_goi_xuat(gateway) == ["CELL_TE", "CELL_VUA"]
    assert ket_qua["so_phieu_thanh_cong"] == 2
    assert ket_qua["so_phieu_that_bai"] == 0
    assert ket_qua["so_cell_vuot_gioi_han"] == 0


async def test_sap_xep_te_nhat_truoc():
    # Dua vao theo thu tu NGUOC (tot -> te) de chac chan ket qua la do SORT,
    # khong phai do trung thu tu dau vao.
    #
    # MOI cell trong test nay PHAI co avg_after < 4.0 (MUC_TOT trong
    # evaluation_service.py) - neu >= 4.0 thi cell do PASS o ve "tut nhieu nhung
    # van con tot" va bi loai khoi danh sach ung vien, khong con gi de sap xep.
    # SUA SO LIEU (16082026): C_NHE truoc day la [4.0]*5 - DUNG bang MUC_TOT nen
    # bi loai; ha xuong 3.8 de van la cell "nhe nhat" trong 3 ma van KHONG DAT.
    #
    # SUA 04/10/2026 (lo phu thuoc .env): moi cell 1 sector RIENG - test nay
    # kiem SAP XEP (khoa_uu_tien_xuat_phieu), KHONG phai tran/sector, nen
    # KHONG duoc de chung 1 sector roi phu thuoc XUAT_PHIEU_MAX_PER_SECTOR
    # (.env local=10 thi qua, nhung .env=2 nhu production se cat mat 1 cell
    # va test FAIL oan - da xac nhan bang cach thu doi .env local ve 2).
    use_case, gateway, _ = _make_use_case(
        cells=["C_NHE", "C_NANG", "C_VUA"],
        qos_sau_theo_cell={
            "C_NHE": [3.8] * 5,   # do te 1.2 (nhe nhat, van < 4.0)
            "C_NANG": [0.5] * 5,  # do te 4.5
            "C_VUA": [2.0] * 5,   # do te 3.0
        },
        sector_theo_cell={"C_NHE": 1, "C_NANG": 2, "C_VUA": 3},
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["C_NANG", "C_VUA", "C_NHE"]


async def test_vuot_tran_chi_xuat_top_te_nhat_con_lai_vao_chi_tiet():
    # (tran + 2) cell KHONG DAT, do te giam dan theo chi so: cell 0 te nhat.
    #
    # So cell SUY TU HANG SO (khong go 12) va moi assert deu dung hang so thay
    # vi so 10: tran la gia tri doc tu .env (09/2026 da doi 10 -> 6), test khoa
    # cung con so se do moi lan van hanh doi tran - trong khi y nghia can kiem
    # ("xuat dung tran, thua 2 cell") khong he thay doi.
    cells = [f"CELL_{i:02d}" for i in range(XUAT_PHIEU_MAX_PER_SECTOR + 2)]
    use_case, gateway, job_repo = _make_use_case(
        cells=cells,
        # qos sau = 0.5 + i*0.1 -> do te = 4.5 - i*0.1 (cang i lon cang do te thap)
        qos_sau_theo_cell={c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)},
    )

    # truyen job_run_log_id vi test nay con kiem tra chi_tiet ghi xuong job_run_log
    ket_qua = await use_case.execute_all_pending(job_run_log_id=555)

    da_xuat = _cell_da_goi_xuat(gateway)
    assert len(da_xuat) == XUAT_PHIEU_MAX_PER_SECTOR
    # Dung top TE NHAT (CELL_00...), dung thu tu te dan
    assert da_xuat == cells[:XUAT_PHIEU_MAX_PER_SECTOR]
    assert ket_qua["so_phieu_thanh_cong"] == XUAT_PHIEU_MAX_PER_SECTOR
    # 2 cell con lai KHONG bien mat im lang - phai dem duoc + nam trong chi_tiet
    assert ket_qua["so_cell_vuot_gioi_han"] == 2
    session_chi_tiet = ket_qua["chi_tiet"]["sessions"][0]
    assert [c["cell_name"] for c in session_chi_tiet["cell_vuot_gioi_han"]] == (
        cells[XUAT_PHIEU_MAX_PER_SECTOR:]
    )
    # SUA 04/10/2026 (lo phu thuoc .env): "12" cu la gia tri CHUNG con TINH
    # TAY tu .env local (=10 luc do, 10+2=12) - lech hoan toan voi comment
    # ngay tren "SUY TU HANG SO (khong go 12)". Phat hien khi thu doi .env
    # local ve 2 (nhu production) de kiem doc lap .env - 2+2=4 != 12, FAIL.
    assert session_chi_tiet["so_cell_khong_dat"] == len(cells)
    # chi_tiet ghi xuong job_run_log cung phai co thong tin do
    chi_tiet_da_ghi = job_repo.update_result.call_args.kwargs["chi_tiet"]
    assert chi_tiet_da_ghi["sessions"][0]["cell_vuot_gioi_han"][0]["cell_name"] == (
        cells[XUAT_PHIEU_MAX_PER_SECTOR]
    )


async def test_luot_2_cell_ngoai_tran_VAN_khong_duoc_xuat_tu_dong():
    # TEST KHOA CHINH cua thiet ke "N cell / SESSION" (KHONG phai N/ngay).
    #
    # Kich ban: session co (tran + 2) cell KHONG DAT.
    #   Luot 1 (hom qua) da xuat dung tran cell te nhat -> nay deu co phieu SUCCESS.
    #   Luot 2 (hom nay): 2 cell ngoai tran PHAI VAN nam ngoai top, KHONG duoc
    #   xuat tu dong - chung danh cho nguoi lam tay (FE danh dau).
    #
    # Ban cu SAI o day: loai cell da xuat TRUOC khi xep hang -> 2 cell ngoai
    # tran tro thanh toan bo ung vien -> leo len top -> bi xuat tu dong.
    cells = [f"CELL_{i:02d}" for i in range(XUAT_PHIEU_MAX_PER_SECTOR + 2)]
    use_case, gateway, job_repo = _make_use_case(
        cells=cells,
        qos_sau_theo_cell={c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)},
        # dung tran cell te nhat da xuat thanh cong o luot 1
        phieu_da_co=[
            {"cell_name": c, "trang_thai": "SUCCESS"}
            for c in cells[:XUAT_PHIEU_MAX_PER_SECTOR]
        ],
    )

    ket_qua = await use_case.execute_all_pending(job_run_log_id=888)

    # KHONG goi gateway lan nao nua - khong con gi de xuat tu dong
    assert _cell_da_goi_xuat(gateway) == []
    assert ket_qua["so_phieu_thanh_cong"] == 0
    # 2 cell ngoai tran VAN bi dem la vuot gioi han + VAN nam trong chi_tiet
    assert ket_qua["so_cell_vuot_gioi_han"] == 2
    chi_tiet = ket_qua["chi_tiet"]["sessions"][0]
    assert [c["cell_name"] for c in chi_tiet["cell_vuot_gioi_han"]] == (
        cells[XUAT_PHIEU_MAX_PER_SECTOR:]
    )
    # Cell trong top da co phieu -> ghi lai ly do luot nay khong xuat gi
    assert chi_tiet["cell_da_co_phieu"] == cells[:XUAT_PHIEU_MAX_PER_SECTOR]


async def test_luot_1_va_luot_2_lien_tiep_tong_khong_qua_tran():
    # Doc lien 2 luot de thay TONG so phieu tu dong cua 1 session KHONG BAO GIO
    # vuot tran, du job chay bao nhieu ngay.
    cells = [f"CELL_{i:02d}" for i in range(XUAT_PHIEU_MAX_PER_SECTOR + 2)]
    qos = {c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)}

    use_case_1, gateway_1, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos)
    ket_qua_1 = await use_case_1.execute_all_pending()
    da_xuat_luot_1 = _cell_da_goi_xuat(gateway_1)

    # Luot 2: dung ket qua luot 1 lam trang thai dau vao
    use_case_2, gateway_2, _ = _make_use_case(
        cells=cells,
        qos_sau_theo_cell=qos,
        phieu_da_co=[{"cell_name": c, "trang_thai": "SUCCESS"} for c in da_xuat_luot_1],
    )
    ket_qua_2 = await use_case_2.execute_all_pending()

    tong_xuat = len(da_xuat_luot_1) + len(_cell_da_goi_xuat(gateway_2))
    assert tong_xuat == XUAT_PHIEU_MAX_PER_SECTOR
    assert ket_qua_1["so_cell_vuot_gioi_han"] == 2
    assert ket_qua_2["so_cell_vuot_gioi_han"] == 2  # van la 2 cell do, khong doi


async def test_duoi_tran_thi_xuat_het_khong_bo_sot():
    # 5 cell KHONG DAT, MOI cell 1 sector rieng -> xuat het, khong co cell nao
    # bi coi la vuot (tung sector chi co 1 ung vien nen luon "duoi tran" DU
    # tran la bao nhieu - SUA 04/10/2026, lo phu thuoc .env: 5 cell CUNG 1
    # sector se FAIL neu .env production=2, vi y dinh test la kiem "duoi tran
    # thi xuat het" chu KHONG phai kiem tran, nen tach sector de doc lap).
    cells = [f"CELL_{i}" for i in range(5)]
    use_case, gateway, _ = _make_use_case(
        cells=cells,
        qos_sau_theo_cell={c: [1.0 + i * 0.1] * 5 for i, c in enumerate(cells)},
        sector_theo_cell={c: i + 1 for i, c in enumerate(cells)},
    )

    ket_qua = await use_case.execute_all_pending()

    assert len(_cell_da_goi_xuat(gateway)) == 5
    assert ket_qua["so_phieu_thanh_cong"] == 5
    assert ket_qua["so_cell_vuot_gioi_han"] == 0


async def test_cell_da_co_phieu_trong_top_khong_keo_cell_ngoai_tran_len_thay_the():
    # (tran+1) cell KHONG DAT CUNG 1 sector, cell te nhat (index 0) da co
    # phieu tu luot truoc. Cell NGOAI tran (index cap, te nhat trong so con
    # lai) KHONG duoc "dien vao cho trong" cua cell da SUCCESS - suat trong
    # top da dung roi, chi la dung o luot truoc.
    #
    # SUA 04/10/2026 (lo phu thuoc .env): truoc day hard-code 11 cell + mong
    # doi "top 10" - CHI dung tinh co voi .env local=10 luc do, se SAI ngay
    # neu .env=2 (production). Gio SUY TU HANG SO giong cac test tran khac
    # trong file nay.
    cap = XUAT_PHIEU_MAX_PER_SECTOR
    cells = [f"CELL_{i:02d}" for i in range(cap + 1)]
    use_case, gateway, _ = _make_use_case(
        cells=cells,
        qos_sau_theo_cell={c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)},
        phieu_da_co=[{"cell_name": cells[0], "trang_thai": "SUCCESS"}],
    )

    ket_qua = await use_case.execute_all_pending()

    da_xuat = _cell_da_goi_xuat(gateway)
    # Top `cap` ung vien la cells[0:cap]; cells[0] da SUCCESS nen bi loai,
    # con lai cells[1:cap] (cap-1 cell) duoc xuat. cells[cap] (ngoai top tu
    # dau) KHONG bao gio duoc xet toi.
    assert da_xuat == cells[1:cap]
    assert cells[cap] not in da_xuat
    assert ket_qua["so_cell_vuot_gioi_han"] == 1  # cells[cap] van la cell vuot


# === TRAN THEO SECTOR (quyet dinh 04/10/2026) ===
#
# TAI SAO SUY SO LUONG TU XUAT_PHIEU_MAX_PER_SECTOR (khong go cung 2/3/8 nhu
# spec goc): .env CUA MOI TRUONG test nay dang ghi gia tri RIENG (10, ke thua
# tu XUAT_PHIEU_MAX_PER_SESSION cu, giu lai de cac test "vuot tran" khac trong
# file nay khong phai sua lai so luong cell) - test di theo dung hang so DANG
# CHAY se luon dung bat ke .env doi, dung tinh than "So cell SUY TU HANG SO"
# da ap dung cho ca file nay tu truoc (xem test_vuot_tran_chi_xuat_top_te_nhat...).


async def test_4_sector_moi_sector_toi_da_tran_tong_4_lan_tran():
    # Spec goc (vi du minh hoa voi tran=2): 4 sector, moi sector 3 ung vien ->
    # dung 8 phieu, moi sector 2. Tong quat hoa: moi sector (tran+1) ung vien
    # -> dung DUNG tran/sector, tong 4*tran.
    cap = XUAT_PHIEU_MAX_PER_SECTOR
    so_sector = 4
    cells: list[str] = []
    sector_theo_cell: dict[str, int] = {}
    qos_sau_theo_cell: dict[str, list[float]] = {}
    for sector in range(1, so_sector + 1):
        for i in range(cap + 1):
            c = f"S{sector}_C{i}"
            cells.append(c)
            sector_theo_cell[c] = sector
            qos_sau_theo_cell[c] = [1.0 + i * 0.1] * 5  # tat ca KHONG DAT (duoi san)
    use_case, gateway, _ = _make_use_case(
        cells=cells, qos_sau_theo_cell=qos_sau_theo_cell, sector_theo_cell=sector_theo_cell,
    )

    ket_qua = await use_case.execute_all_pending()

    da_xuat = _cell_da_goi_xuat(gateway)
    assert len(da_xuat) == so_sector * cap
    assert ket_qua["so_phieu_thanh_cong"] == so_sector * cap
    assert ket_qua["so_cell_vuot_gioi_han"] == so_sector  # 1 cell thua/sector
    for sector in range(1, so_sector + 1):
        so_xuat_sector = sum(1 for c in da_xuat if sector_theo_cell[c] == sector)
        assert so_xuat_sector == cap, f"sector {sector} xuat {so_xuat_sector}, ky vong {cap}"


async def test_1_sector_nhieu_ung_vien_sector_khac_rong_khong_anh_huong_tran():
    # 1 sector co (tran+3) ung vien KHONG DAT, sector khac CHI co 1 cell DAT
    # (khong vao danh sach ung vien) - tran cua sector 1 KHONG bi anh huong
    # boi viec sector 2 "rong" (khong duoc cong them suat thua).
    cap = XUAT_PHIEU_MAX_PER_SECTOR
    cells_sector1 = [f"S1_C{i}" for i in range(cap + 3)]
    cells = cells_sector1 + ["S2_DAT"]
    sector_theo_cell = {**{c: 1 for c in cells_sector1}, "S2_DAT": 2}
    qos_sau_theo_cell = {c: [1.0 + i * 0.1] * 5 for i, c in enumerate(cells_sector1)}
    qos_sau_theo_cell["S2_DAT"] = [4.95] * 5  # DAT - khong vao ung_vien
    use_case, gateway, _ = _make_use_case(
        cells=cells, qos_sau_theo_cell=qos_sau_theo_cell, sector_theo_cell=sector_theo_cell,
    )

    await use_case.execute_all_pending()

    assert len(_cell_da_goi_xuat(gateway)) == cap


async def test_cell_sector_da_resolve_chi_tinh_vao_1_sector():
    # cr_affected_cells da LUU SAN sector (MIN qua nhieu huong - xem
    # domain/services/neighbor_cell_filter.py::filter_affected()) - 1 cell
    # tung la neighbor cua ca huong sector 1 VA 2 nhung DA duoc resolve ve
    # sector=1 (nho nhat) TRUOC KHI toi day. _danh_gia_va_xep_hang() PHAI
    # dung dung gia tri da luu (CHI tinh vao sector 1), KHONG tu gop/nhan doi
    # sang sector 2.
    cap = XUAT_PHIEU_MAX_PER_SECTOR
    cells_sector1_du_tran = [f"S1_C{i}" for i in range(cap)]
    cell_da_resolve = "CELL_DA_RESOLVE_VE_SECTOR_1"
    cells = cells_sector1_du_tran + [cell_da_resolve]
    sector_theo_cell = {c: 1 for c in cells_sector1_du_tran}
    sector_theo_cell[cell_da_resolve] = 1  # DA resolve ve 1 (min), KHONG con la 2
    qos_sau_theo_cell = {c: [1.0 + i * 0.1] * 5 for i, c in enumerate(cells_sector1_du_tran)}
    # avg thap nhat (te nhat) - chac chan canh tranh duoc 1 suat trong sector 1
    qos_sau_theo_cell[cell_da_resolve] = [0.5] * 5
    use_case, gateway, _ = _make_use_case(
        cells=cells, qos_sau_theo_cell=qos_sau_theo_cell, sector_theo_cell=sector_theo_cell,
    )

    await use_case.execute_all_pending()

    da_xuat = _cell_da_goi_xuat(gateway)
    # VAN chi toi da CAP cho sector 1 - cell "da resolve" KHONG mang them 1
    # suat rieng cho "sector 2" (ma no khong con thuoc ve nua).
    assert len(da_xuat) == cap
    assert cell_da_resolve in da_xuat  # te nhat nhat nen thang 1 trong cap suat do


async def test_sector_null_la_1_nhom_rieng_toi_da_tran():
    # Cell khong suy duoc sector (huong_name sai dinh dang, hoac CDS tra null
    # ca gia tri CDS lan ten - xem filter_affected()) -> sector=None, gom
    # thanh 1 "sector" rieng, CUNG chiu tran nhu sector so thuc - KHONG duoc
    # mien tran (vd xu ly nhu "khong sector nao ca nen khong gioi han").
    cap = XUAT_PHIEU_MAX_PER_SECTOR
    cells = [f"CELL_{i}" for i in range(cap + 2)]
    qos_sau_theo_cell = {c: [1.0 + i * 0.1] * 5 for i, c in enumerate(cells)}
    # KHONG truyen sector_theo_cell -> tat ca None (dung mac dinh cua helper)
    use_case, gateway, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos_sau_theo_cell)

    await use_case.execute_all_pending()

    assert len(_cell_da_goi_xuat(gateway)) == cap


async def test_trong_sector_cell_duoi_san_dung_truoc_cell_tut_nhieu():
    # Ca 2 cell CUNG 1 sector. CELL_DUOI_SAN: avg_after 2.9 < 3.0 (nhom 0).
    # CELL_TUT_NHIEU: avg_after 3.6 >= 3.0 (nhom 1) nhung tut nhieu hon ve SO
    # TUYET DOI (5.0->3.6 = 1.4, so voi 5.0->2.9 = 2.1 cua CELL_DUOI_SAN - o
    # day CELL_DUOI_SAN thuc ra tut NHIEU HON, nhung diem la o nhom 0 LUON
    # dung TRUOC nhom 1 BAT KE do_giam, xem khoa_uu_tien_xuat_phieu()).
    cells = ["CELL_DUOI_SAN", "CELL_TUT_NHIEU"]
    sector_theo_cell = {"CELL_DUOI_SAN": 1, "CELL_TUT_NHIEU": 1}
    qos_sau_theo_cell = {
        "CELL_DUOI_SAN": [2.9] * 5,
        "CELL_TUT_NHIEU": [3.6] * 5,
    }
    use_case, gateway, _ = _make_use_case(
        cells=cells, qos_sau_theo_cell=qos_sau_theo_cell, sector_theo_cell=sector_theo_cell,
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_DUOI_SAN", "CELL_TUT_NHIEU"]


async def test_cell_da_co_phieu_success_thi_skip():
    # Idempotent: chay lai job KHONG duoc tao phieu trung cho cell da xuat.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_DA_XUAT", "CELL_MOI"],
        qos_sau_theo_cell={"CELL_DA_XUAT": [1.0] * 5, "CELL_MOI": [2.0] * 5},
        phieu_da_co=[
            {"cell_name": "CELL_DA_XUAT", "trang_thai": "SUCCESS"},
        ],
    )

    ket_qua = await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_MOI"]
    assert ket_qua["so_phieu_thanh_cong"] == 1


async def test_cell_co_phieu_da_xoa_khong_tao_lai():
    # XOA MEM (THEM 04/10/2026, quyet dinh 04/10/2026) - cell nguoi dung da CHU
    # DONG xoa phieu KHONG duoc job tu dong "cuu" tao lai, khac han cell FAILED
    # binh thuong (test_phieu_cu_that_bai_thi_van_xuat_lai ben duoi - PHAI thu
    # lai). Phan biet DUY NHAT la deleted_at co gia tri hay khong.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_DA_XOA", "CELL_MOI"],
        qos_sau_theo_cell={"CELL_DA_XOA": [1.0] * 5, "CELL_MOI": [2.0] * 5},
        phieu_da_co=[
            {"cell_name": "CELL_DA_XOA", "trang_thai": "FAILED", "deleted_at": EXECUTED_AT},
        ],
    )

    ket_qua = await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_MOI"]
    assert ket_qua["so_phieu_thanh_cong"] == 1


async def test_phieu_cu_that_bai_thi_van_xuat_lai():
    # Chi SUCCESS moi duoc bo qua - dong FAILED/KHONG_XUAT_* cua lan truoc PHAI duoc
    # thu lai (dung y "chua xuat that thi chua xong").
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_LOI_LAN_TRUOC"],
        qos_sau_theo_cell={"CELL_LOI_LAN_TRUOC": [1.0] * 5},
        phieu_da_co=[{"cell_name": "CELL_LOI_LAN_TRUOC", "trang_thai": "FAILED"}],
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_LOI_LAN_TRUOC"]


async def test_cell_thieu_data_bi_bo_qua_khong_giet_ca_luot():
    # CELL_THIEU chi co 3 ngay sau (<5 = MIN_DAYS_REQUIRED) -> INSUFFICIENT_DATA.
    use_case, gateway, job_repo = _make_use_case(
        cells=["CELL_THIEU", "CELL_DU"],
        qos_sau_theo_cell={"CELL_THIEU": [1.0] * 3, "CELL_DU": [1.0] * 5},
    )

    ket_qua = await use_case.execute_all_pending(job_run_log_id=556)

    # Cell thieu data KHONG duoc xuat, nhung cell con lai VAN chay binh thuong
    assert _cell_da_goi_xuat(gateway) == ["CELL_DU"]
    assert ket_qua["so_phieu_thanh_cong"] == 1
    # Luot chay VAN la DONE (thieu data khong phai loi)
    assert job_repo.update_result.call_args.kwargs["trang_thai"] == "DONE"


async def test_mot_session_loi_khong_giet_cac_session_khac():
    session_loi = _make_session(101)
    session_ok = _make_session(102)
    use_case, gateway, job_repo = _make_use_case(
        cells=["CELL_OK"],
        qos_sau_theo_cell={"CELL_OK": [1.0] * 5},
        sessions=[session_loi, session_ok],
    )
    # Session 101 nem loi khi lay affected cells; 102 chay binh thuong
    async def _affected_side_effect(session_id):
        if session_id == 101:
            raise RuntimeError("DB rot ket noi")
        return [{"cell_name": "CELL_OK", "tram_id": TRAM_ID, "huong_id": "11"}]

    use_case._cr_affected_cells_repo.get_by_cr_session_id.side_effect = _affected_side_effect

    ket_qua = await use_case.execute_all_pending(job_run_log_id=557)

    assert ket_qua["so_session_quet"] == 2  # dem CA session loi (da quet toi)
    assert _cell_da_goi_xuat(gateway) == ["CELL_OK"]  # session 102 van chay
    assert job_repo.update_result.call_args.kwargs["trang_thai"] == "DONE"
    # Loi cua session 101 KHONG bi nuot im lang
    loi_ghi_lai = [s for s in ket_qua["chi_tiet"]["sessions"] if "loi" in s]
    assert len(loi_ghi_lai) == 1
    assert loi_ghi_lai[0]["cr_session_id"] == 101


async def test_job_run_log_update_done_kem_so_dem():
    use_case, _, job_repo = _make_use_case(
        cells=["C1", "C2", "C_DAT"],
        qos_sau_theo_cell={"C1": [1.0] * 5, "C2": [2.0] * 5, "C_DAT": [5.0] * 5},
    )

    await use_case.execute_all_pending(job_run_log_id=777)

    kwargs = job_repo.update_result.call_args.kwargs
    assert job_repo.update_result.call_args.args[0] == 777
    assert kwargs["trang_thai"] == "DONE"
    assert kwargs["so_session_quet"] == 1
    assert kwargs["so_phieu_thanh_cong"] == 2
    assert kwargs["so_phieu_that_bai"] == 0
    assert kwargs["so_cell_vuot_gioi_han"] == 0
    assert kwargs["error_message"] is None
    # finished_at do caller truyen (khong phai adapter tu set) va PHAI tz-aware
    assert kwargs["finished_at"].tzinfo is not None


async def test_loi_toan_cuc_ghi_failed_kem_error_message():
    use_case, _, job_repo = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    use_case._cr_session_repo.list.side_effect = RuntimeError("DB chet han")

    try:
        await use_case.execute_all_pending(job_run_log_id=778)
    except RuntimeError:
        pass  # loi toan cuc VAN raise len caller (scheduler) sau khi da ghi log

    kwargs = job_repo.update_result.call_args.kwargs
    assert kwargs["trang_thai"] == "FAILED"
    assert "DB chet han" in kwargs["error_message"]


async def test_session_chua_du_ngay_khong_bi_quet():
    # CR chay HOM QUA - chua du XUAT_PHIEU_AFTER_DAYS (7 ngay) -> cua so QoS
    # T+1..T+7 chua co du data, KHONG duoc dong toi.
    session_moi = _make_session(200)
    session_moi.executed_at = datetime.now(timezone.utc) - timedelta(days=1)
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[session_moi]
    )

    ket_qua = await use_case.execute_all_pending()

    assert ket_qua["so_session_quet"] == 0
    assert gateway.save_cell_clm.call_args_list == []


# === Dieu kien loc thoi gian: SO THEO NGAY LICH, khong theo thoi diem (12/08) ===
#
# Truyen "bay_gio" tuong minh vao _lay_session_du_dieu_kien() - KHONG phu thuoc
# dong ho may chay test (chay luc nao trong ngay cung ra ket qua giong nhau).

_GMT7_TZ = timezone(timedelta(hours=7))


def _session_chay_luc(nam: int, thang: int, ngay: int, gio: int, phut: int = 0) -> CrSession:
    # Tham so la GIO VN (nguoi doc nghi theo lich VN), doi sang UTC de luu -
    # dung cach DB that luu (TIMESTAMPTZ, C1.4-fix10).
    vn = datetime(nam, thang, ngay, gio, phut, tzinfo=_GMT7_TZ)
    s = _make_session(300)
    s.executed_at = vn.astimezone(timezone.utc)
    return s


def _job_chay_luc(nam: int, thang: int, ngay: int, gio: int, phut: int = 0) -> datetime:
    return datetime(nam, thang, ngay, gio, phut, tzinfo=_GMT7_TZ).astimezone(timezone.utc)


async def test_du_8_ngay_lich_thi_duoc_quet_du_cr_chay_buoi_chieu():
    # CR 14:00 ngay 20, job chay 08:00 ngay 28 -> DU (8 ngay lich).
    # Ban cu (so thoi diem) se TRUOT: now-8ngay = 08:00 ngay 20 < 14:00 ngay 20.
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 20, 14)]
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 28, 8))

    assert len(duoc_quet) == 1


async def test_chua_du_8_ngay_lich_thi_khong_duoc_quet():
    # CR 14:00 ngay 20, job chay 08:00 ngay 27 -> CHUA du (moi 7 ngay lich).
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 20, 14)]
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 27, 8))

    assert duoc_quet == []


async def test_ngay_xuat_phieu_khong_phu_thuoc_gio_chay_cr():
    # Diem chinh cua viec doi sang ngay lich: CR chay 00:01 hay 23:59 CUNG NGAY
    # thi deu duoc quet vao dung ngay 28, khong lech nhau 1 ngay.
    use_case_sang, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 20, 0, 1)]
    )
    use_case_toi, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 20, 23, 59)]
    )
    job_ngay_28 = _job_chay_luc(2026, 7, 28, 8)

    assert len(await use_case_sang._lay_session_du_dieu_kien(bay_gio=job_ngay_28)) == 1
    assert len(await use_case_toi._lay_session_du_dieu_kien(bay_gio=job_ngay_28)) == 1


async def test_cr_chay_khung_utc_lech_ngay_van_tinh_dung_theo_lich_vn():
    # CR 23:30 gio VN ngay 20 = 16:30 UTC ngay 20 (cung ngay UTC).
    # CR 00:30 gio VN ngay 21 = 17:30 UTC ngay 20 (LECH ngay neu lay .date()
    # thang tren UTC) - phai tinh theo lich VN, dung bug C1.4-fix8.
    use_case, _, _ = _make_use_case(
        cells=["C1"],
        qos_sau_theo_cell={"C1": [1.0] * 5},
        sessions=[_session_chay_luc(2026, 7, 21, 0, 30)],  # ngay 21 gio VN
    )

    # Job ngay 28: CR ngay 21 -> moi 7 ngay lich -> CHUA du.
    # (Neu tinh nham theo UTC se ra ngay 20 -> du 8 ngay -> quet som 1 ngay.)
    assert await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 28, 8)) == []
    # Sang ngay 29 moi du.
    assert len(await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 29, 8))) == 1


# === QUET BU (03/10/2026) - xem XUAT_PHIEU_QUET_BU_NGAY ===
#
# CA THAT: session 7296 (CR 15/09/2026) KHONG bao gio duoc job tu dong quet
# toi vi lo dung ngay moc (PA A cu, chi quet "==" 1 ngay/lan chay) - xem khao
# sat 02/10/2026. Nhom test nay xac nhan cua so quet bu + dieu kien idempotent
# moi (xuat_phieu_at IS NULL).


async def test_session_tre_3_ngay_CHUA_quet_van_DUOC_quet():
    # CR ngay 20/07, job le ra chay dung ngay 28 (ngay_moc = 28-8 = 20) nhung
    # LO 3 ngay, mai den 31/07 moi chay (ngay_moc = 31-8 = 23). Truoc 03/10/2026
    # (PA A "=="), session nay se MAT VINH VIEN (20 != 23). Gio nam trong cua
    # so quet bu [23-14, 23] = [9, 23] nen VAN duoc quet.
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 20, 14)]
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 31, 8))

    assert len(duoc_quet) == 1


async def test_session_DA_quet_roi_thi_KHONG_quet_lai():
    # Cung ngay CR/ngay chay job nhu test tren (van nam trong cua so), nhung
    # session DA co xuat_phieu_at (gia lap da duoc 1 lan chay truoc xu ly xong)
    # - PHAI bi loai, du van trong cua so ngay. Day la dieu kien IDEMPOTENT
    # THAT SU can them (truoc day "==" tu nhien chi khop 1 ngay/doi session nen
    # khong can kiem rieng).
    session = _session_chay_luc(2026, 7, 20, 14)
    session.xuat_phieu_at = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[session]
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 31, 8))

    assert duoc_quet == []


async def test_small_cell_bi_loai_khi_doc_cr_affected_cells():
    # CHOT PHONG VE (03/10/2026, "khi doc cr_affected_cells") - small cell
    # (S/P) KHONG duoc dua vao danh gia/xep hang/xuat phieu du co trong
    # cr_affected_cells (vd du lieu cu/nguon ghi khac sau nay) - khao sat
    # 02/10/2026 xac nhan SQL that 0/464 dong hien co la small cell, day la
    # luoi an toan cho TUONG LAI, khong phai sua loi dang xay ra.
    use_case, gateway, _ = _make_use_case(
        cells=["C1", "4G-TPO065S11-TQG"],
        qos_sau_theo_cell={"C1": [1.0] * 5, "4G-TPO065S11-TQG": [1.0] * 5},
    )

    await use_case.execute_all_pending()

    assert "4G-TPO065S11-TQG" not in _cell_da_goi_xuat(gateway)


async def test_session_QUA_cua_so_quet_bu_KHONG_duoc_quet():
    # Job chay 31/07 -> ngay_moc = 23, cua so = [9, 23] (QUET_BU_NGAY mac
    # dinh 14). CR ngay 05/07 (14:00) la NGAY 5 - NAM NGOAI cua so (< 9) nen
    # KHONG duoc quet - qua xa de "bu", phai xuat tay.
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, sessions=[_session_chay_luc(2026, 7, 5, 14)]
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien(bay_gio=_job_chay_luc(2026, 7, 31, 8))

    assert duoc_quet == []


# === PHAN A (viec 2b): WHITELIST status ===


@pytest.mark.parametrize("status", [CrStatus.DONE, CrStatus.EVALUATED, CrStatus.EVAL_PENDING])
async def test_status_trong_whitelist_thi_duoc_quet(status):
    # 3 status nay deu la "CR da chay xong" - deu co the con cell KHONG DAT.
    session = _make_session(400)
    session.status = status
    use_case, _, _ = _make_use_case(
        cells=["C1"],
        qos_sau_theo_cell={"C1": [1.0] * 5},
        status_theo_filter={status.value: [session]},
    )

    duoc_quet = await use_case._lay_session_du_dieu_kien()

    assert [s.id for s in duoc_quet] == [400]


@pytest.mark.parametrize(
    "status", [CrStatus.PENDING, CrStatus.RUNNING, CrStatus.FAILED, CrStatus.EVALUATING]
)
async def test_status_ngoai_whitelist_khong_bao_gio_duoc_quet(status):
    # Fail-safe: 4 status nay KHONG duoc xuat phieu tu dong. Mock tra session
    # cho DUNG status dang test - neu use case lo hoi status nay thi test fail.
    session = _make_session(401)
    session.status = status
    use_case, gateway, _ = _make_use_case(
        cells=["C1"],
        qos_sau_theo_cell={"C1": [1.0] * 5},
        status_theo_filter={status.value: [session]},
    )

    assert await use_case._lay_session_du_dieu_kien() == []

    # Kiem ca duong end-to-end: khong session nao duoc quet -> khong xuat gi
    ket_qua = await use_case.execute_all_pending()
    assert ket_qua["so_session_quet"] == 0
    assert gateway.save_cell_clm.call_args_list == []


async def test_chi_hoi_dung_status_trong_whitelist():
    # Khoa DANH SACH status duoc hoi - them status moi vao CrStatus se KHONG tu
    # dong lot vao dien quet (day chinh la muc dich cua whitelist).
    # 18082026: them PARTIAL_SUCCESS (CR da chay, chi mot so DN hong - cell van
    # phai duoc danh gia binh thuong).
    use_case, _, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}, status_theo_filter={}
    )

    await use_case._lay_session_du_dieu_kien()

    da_hoi = [c.args[0].status for c in use_case._cr_session_repo.list.call_args_list]
    assert da_hoi == ["PARTIAL_SUCCESS", "DONE", "EVALUATED", "EVAL_PENDING"]


# === PHAN B (viec 2b): so_lan_thu + XUAT_PHIEU_MAX_RETRY ===


async def test_post_that_that_bai_thi_tang_so_lan_thu():
    # V3: so_lan_thu_them la SO lan da POST that (khong con co bool).
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    # CTS tu choi 400 -> FAILED va DUNG NGAY (1 lan thu that su, da lam phien CTS)
    gateway.save_cell_clm.return_value = {"isError": True, "message": "loi", "status_code": 400}

    await use_case.execute_all_pending()

    assert use_case._cr_phieu_repo.update_result.await_args.kwargs["so_lan_thu_them"] == 1


async def test_post_thanh_cong_cung_tang_so_lan_thu():
    # V2: khong con duong nao KHONG dem - moi lan goi gateway deu lam phien CTS.
    use_case, _, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})

    await use_case.execute_all_pending()

    assert use_case._cr_phieu_repo.update_result.await_args.kwargs["so_lan_thu_them"] == 1


async def test_cham_tran_so_lan_thu_thi_ngung_xuat():
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_HONG", "CELL_MOI"],
        qos_sau_theo_cell={"CELL_HONG": [0.5] * 5, "CELL_MOI": [2.0] * 5},
        phieu_da_co=[
            {"cell_name": "CELL_HONG", "trang_thai": "FAILED", "so_lan_thu": XUAT_PHIEU_MAX_RETRY}
        ],
    )

    ket_qua = await use_case.execute_all_pending(job_run_log_id=901)

    # CELL_HONG te hon (do te 4.5 > 3.0) nhung da het luot -> KHONG goi gateway
    assert _cell_da_goi_xuat(gateway) == ["CELL_MOI"]
    chi_tiet = ket_qua["chi_tiet"]["sessions"][0]
    assert chi_tiet["cell_vuot_so_lan_thu"] == ["CELL_HONG"]
    # Nhom RIENG, KHONG lan sang cell_vuot_gioi_han (2 ly do khac han nhau)
    assert chi_tiet["cell_vuot_gioi_han"] == []


async def test_chua_cham_tran_thi_van_xuat():
    # so_lan_thu = MAX-1 -> con 1 luot, van phai thu.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_THU_LAI"],
        qos_sau_theo_cell={"CELL_THU_LAI": [1.0] * 5},
        phieu_da_co=[
            {
                "cell_name": "CELL_THU_LAI",
                "trang_thai": "FAILED",
                "so_lan_thu": XUAT_PHIEU_MAX_RETRY - 1,
            }
        ],
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_THU_LAI"]


async def test_cell_success_khong_bi_anh_huong_boi_so_lan_thu():
    # Cell da SUCCESS thi bo qua vi DA XONG, khong phai vi het luot thu - du
    # so_lan_thu cua no vuot tran.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_XONG"],
        qos_sau_theo_cell={"CELL_XONG": [1.0] * 5},
        phieu_da_co=[
            {"cell_name": "CELL_XONG", "trang_thai": "SUCCESS", "so_lan_thu": 99}
        ],
    )

    ket_qua = await use_case.execute_all_pending(job_run_log_id=902)

    assert _cell_da_goi_xuat(gateway) == []
    chi_tiet = ket_qua["chi_tiet"]["sessions"][0]
    assert chi_tiet["cell_da_co_phieu"] == ["CELL_XONG"]
    assert chi_tiet["cell_vuot_so_lan_thu"] == []  # KHONG bi xep nham nhom


async def test_v2_khong_con_tham_so_dry_run_truyen_xuong_gateway():
    # V2 (12/08): execute_all_pending() khong con tham so dry_run, va gateway
    # duoc goi KHONG kem kwarg nao ngoai payload.
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})

    await use_case.execute_all_pending()

    assert gateway.save_cell_clm.call_args.kwargs == {}


# === V4 (12/08): ghi dong cr_phieu cho cell KHONG duoc xuat ===


async def test_v4_cell_vuot_tran_duoc_ghi_dong_cr_phieu():
    # Tao du cell de co 2 cell vuot tran; do te giam dan theo thu tu tao nen
    # biet chac 2 cell CUOI bi cat.
    cells = [f"C{i:02d}" for i in range(XUAT_PHIEU_MAX_PER_SECTOR + 2)]
    qos = {c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)}
    use_case, gateway, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos)

    await use_case.execute_all_pending()

    ghi_khong_xuat = [
        goi.args[0]
        for goi in use_case._cr_phieu_repo.insert.call_args_list
        if goi.args[0]["trang_thai"] == TRANG_THAI_VUOT_GIOI_HAN
    ]
    assert {p["cell_name"] for p in ghi_khong_xuat} == set(cells[-2:])
    # cell bi cat KHONG duoc goi gateway
    assert not (set(cells[-2:]) & set(_cell_da_goi_xuat(gateway)))
    # dong ghi ra phai co ly do doc duoc ngay tren cot error_message
    assert all(p["error_message"] for p in ghi_khong_xuat)


async def test_v4_cell_het_luot_thu_duoc_danh_dau_KHONG_ghi_de_error_message():
    # Cell het luot thu DA CO dong FAILED kem ly do CTS tu choi - chi duoc doi
    # trang_thai, KHONG duoc goi update_result (se xoa mat error_message goc).
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_HONG"],
        qos_sau_theo_cell={"CELL_HONG": [0.5] * 5},
        phieu_da_co=[
            {"cell_name": "CELL_HONG", "trang_thai": "FAILED", "so_lan_thu": XUAT_PHIEU_MAX_RETRY}
        ],
    )
    use_case._cr_phieu_repo.get_by_session_cell.side_effect = lambda sid, cell: {
        "id": 82, "trang_thai": "FAILED", "phieu_id": None,
    }

    await use_case.execute_all_pending()

    use_case._cr_phieu_repo.danh_dau_khong_xuat.assert_awaited_once_with(82, TRANG_THAI_HET_LUOT_THU)
    use_case._cr_phieu_repo.update_result.assert_not_awaited()
    assert _cell_da_goi_xuat(gateway) == []


async def test_v4_KHONG_ha_cap_dong_SUCCESS_thanh_khong_xuat():
    # Cell da co phieu THAT tren TTS ma bi ha xuong KHONG_XUAT_* se bao mat 1
    # phieu co that.
    cells = [f"C{i:02d}" for i in range(XUAT_PHIEU_MAX_PER_SECTOR + 1)]
    qos = {c: [0.5 + i * 0.1] * 5 for i, c in enumerate(cells)}
    cell_bi_cat = cells[-1]
    use_case, _, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos)
    use_case._cr_phieu_repo.get_by_session_cell.side_effect = lambda sid, cell: (
        {"id": 51, "trang_thai": "SUCCESS", "phieu_id": "19207"} if cell == cell_bi_cat else None
    )

    await use_case.execute_all_pending()

    for goi in use_case._cr_phieu_repo.danh_dau_khong_xuat.await_args_list:
        assert goi.args[0] != 51


# === 14/08: ghi 2 cot tien trinh vao cr_session ===


def _lay_ghi_ket_qua(use_case):
    """(ket_qua, so lan goi) cua cr_session_repo.ghi_ket_qua_xuat_phieu."""
    goi = use_case._cr_session_repo.ghi_ket_qua_xuat_phieu.await_args_list
    return ([g.kwargs["xuat_phieu_ket_qua"] for g in goi], len(goi))


async def test_ket_qua_DA_XUAT_khi_co_it_nhat_1_phieu_success():
    use_case, gateway, _ = _make_use_case(
        cells=["C_TE", "C_DAT"],
        qos_sau_theo_cell={"C_TE": [1.0] * 5, "C_DAT": [4.95] * 5},
    )

    await use_case.execute_all_pending()

    ket_qua, so_lan = _lay_ghi_ket_qua(use_case)
    assert ket_qua == [TRANG_THAI_KET_QUA_DA_XUAT]
    assert so_lan == 1
    # xuat_phieu_at PHAI la tz-aware (cot TIMESTAMPTZ) - naive se lam Postgres
    # hieu theo TimeZone GUC cua server (Asia/Ho_Chi_Minh) -> lech 7 tieng.
    moc = use_case._cr_session_repo.ghi_ket_qua_xuat_phieu.await_args.kwargs["xuat_phieu_at"]
    assert moc.tzinfo is not None


async def test_ket_qua_KHONG_CAN_XUAT_khi_0_cell_khong_dat():
    # TAT CA cell DAT (do te 0.05 <= 0.2) -> 0 dong cr_phieu duoc tao. Day la
    # case CHINH cua 2 cot moi: khong co no thi khong phan biet duoc voi
    # "chua toi luot quet".
    use_case, gateway, _ = _make_use_case(
        cells=["C_DAT_1", "C_DAT_2"],
        qos_sau_theo_cell={"C_DAT_1": [4.95] * 5, "C_DAT_2": [4.95] * 5},
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == []  # khong goi CTS lan nao
    ket_qua, so_lan = _lay_ghi_ket_qua(use_case)
    assert ket_qua == [TRANG_THAI_KET_QUA_KHONG_CAN_XUAT]
    assert so_lan == 1


async def test_ket_qua_LOI_khi_session_nem_exception_giua_chung():
    # _xu_ly_mot_session() chet giua chung -> KHONG tu ghi duoc, phai do
    # execute_all_pending() danh dau. Neu bo qua thi session loi hien y het
    # session "chua toi luot" va theo PA A khong bao gio duoc quet lai.
    use_case, _, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    use_case._cr_affected_cells_repo.get_by_cr_session_id.side_effect = RuntimeError("DB chet")

    ket_qua_job = await use_case.execute_all_pending()

    ket_qua, so_lan = _lay_ghi_ket_qua(use_case)
    assert ket_qua == [TRANG_THAI_KET_QUA_LOI]
    assert so_lan == 1
    # van ghi vao chi_tiet, khong nuot im lang
    assert "loi" in ket_qua_job["chi_tiet"]["sessions"][0]


async def test_ket_qua_LOI_khi_co_cell_can_phieu_nhung_khong_xuat_duoc_cai_nao():
    # TU GIA DINH (dac ta khong neu): co ung vien nhung CTS tu choi het.
    # KHONG_CAN_XUAT se noi doi "session nay khong can phieu" -> nguoi van hanh
    # bo qua session dang can xu ly tay. Chon nhanh bao dong.
    use_case, gateway, _ = _make_use_case(cells=["C_TE"], qos_sau_theo_cell={"C_TE": [1.0] * 5})
    gateway.save_cell_clm.return_value = {
        "status_code": 400, "isError": True, "message": "CTS tu choi",
        "code": None, "data": None, "totalRecord": None, "raw_body": "loi",
    }

    await use_case.execute_all_pending()

    ket_qua, _ = _lay_ghi_ket_qua(use_case)
    assert ket_qua == [TRANG_THAI_KET_QUA_LOI]


async def test_loi_ghi_cr_session_KHONG_lam_hong_luot_quet():
    # Ghi 2 cot la ghi chu PHU TRO - phieu that da gui len TTS roi. De loi DB
    # noi len se lam cac cell/session con lai mat luot.
    use_case, gateway, _ = _make_use_case(cells=["C_TE"], qos_sau_theo_cell={"C_TE": [1.0] * 5})
    use_case._cr_session_repo.ghi_ket_qua_xuat_phieu.side_effect = RuntimeError("DB chet")

    ket_qua_job = await use_case.execute_all_pending()  # KHONG duoc raise

    assert ket_qua_job["so_phieu_thanh_cong"] == 1  # phieu van tinh la da xuat
    assert _cell_da_goi_xuat(gateway) == ["C_TE"]


async def test_ket_qua_tra_ve_trong_chi_tiet_session():
    # FE doc job_run_log.chi_tiet -> can biet ket qua tung session ma khong phai
    # join sang cr_session.
    use_case, _, _ = _make_use_case(cells=["C_TE"], qos_sau_theo_cell={"C_TE": [1.0] * 5})

    ket_qua_job = await use_case.execute_all_pending(job_run_log_id=777)

    assert ket_qua_job["chi_tiet"]["sessions"][0]["xuat_phieu_ket_qua"] == TRANG_THAI_KET_QUA_DA_XUAT


# === CACH C (16082026) - danh dau cell thieu du lieu, KHONG bo qua im lang ===


async def test_cell_thieu_data_duoc_ghi_dong_KHONG_XUAT_THIEU_DU_LIEU():
    # Truoc day nhanh nay chi `continue` -> cell mat vinh vien (PA A quet DUNG
    # 1 ngay, khong co luot sau). Gio phai de lai dau vet trong cr_phieu.
    use_case, _, _ = _make_use_case(
        cells=["CELL_THIEU"],
        qos_sau_theo_cell={"CELL_THIEU": [1.0] * 3},  # 3 ngay < MIN_DAYS_REQUIRED=5
    )

    await use_case.execute_all_pending()

    dong = [g.args[0] for g in use_case._cr_phieu_repo.insert.call_args_list]
    assert len(dong) == 1
    assert dong[0]["cell_name"] == "CELL_THIEU"
    assert dong[0]["trang_thai"] == TRANG_THAI_THIEU_DU_LIEU


async def test_error_message_ghi_dung_so_ngay_thuc_te():
    # Nguoi van hanh doc dong nay de biet thieu bao nhieu, ben nao.
    use_case, _, _ = _make_use_case(
        cells=["CELL_THIEU"],
        qos_sau_theo_cell={"CELL_THIEU": [1.0] * 2},  # 2 ngay sau, 5 ngay truoc
    )

    await use_case.execute_all_pending()

    msg = use_case._cr_phieu_repo.insert.call_args.args[0]["error_message"]
    assert "5/7 ngay truoc" in msg
    assert "2/7 ngay sau" in msg
    assert f">= {MIN_DAYS_REQUIRED}" in msg


async def test_cell_thieu_data_KHONG_bi_goi_gateway():
    # Danh dau la de nguoi xuat TAY - job tuyet doi khong tu xuat voi Qos
    # thieu can cu.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_THIEU"], qos_sau_theo_cell={"CELL_THIEU": [1.0] * 3}
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == []


async def test_cell_du_data_KHONG_doi_hanh_vi():
    # Khong regression: cell du ngay van xuat binh thuong, KHONG sinh dong
    # KHONG_XUAT_THIEU_DU_LIEU nao.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_DU"], qos_sau_theo_cell={"CELL_DU": [1.0] * 5}
    )

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["CELL_DU"]
    trang_thai_da_ghi = [
        g.args[0]["trang_thai"] for g in use_case._cr_phieu_repo.insert.call_args_list
    ]
    assert TRANG_THAI_THIEU_DU_LIEU not in trang_thai_da_ghi


async def test_ten_cell_thieu_du_lieu_vao_chi_tiet_job_run_log():
    use_case, _, job_repo = _make_use_case(
        cells=["CELL_THIEU", "CELL_DU"],
        qos_sau_theo_cell={"CELL_THIEU": [1.0] * 3, "CELL_DU": [1.0] * 5},
    )

    await use_case.execute_all_pending(job_run_log_id=556)

    chi_tiet = job_repo.update_result.call_args.kwargs["chi_tiet"]
    ss = chi_tiet["sessions"][0]
    assert ss["cell_thieu_du_lieu"] == ["CELL_THIEU"]
    # "khong ket luan duoc" KHAC "khong dat" - khong duoc gop vao cung con so.
    assert ss["so_cell_khong_dat"] == 1  # chi CELL_DU


async def test_cell_da_co_phieu_SUCCESS_khong_bi_ha_xuong_thieu_du_lieu():
    # Cell da xuat that roi ma lan nay CTS thieu data -> KHONG duoc ha trang
    # thai (se bao mat 1 phieu co that tren TTS).
    use_case, _, _ = _make_use_case(
        cells=["CELL_THIEU"],
        qos_sau_theo_cell={"CELL_THIEU": [1.0] * 3},
        phieu_da_co=[{"cell_name": "CELL_THIEU", "trang_thai": "SUCCESS", "phieu_id": "19207"}],
    )

    await use_case.execute_all_pending()

    use_case._cr_phieu_repo.danh_dau_khong_xuat.assert_not_awaited()
    use_case._cr_phieu_repo.insert.assert_not_awaited()


# === QoE NGANG HANG QoS (17082026) ===
# Cell KHONG DAT o BAT KY chi so nao deu xuat phieu; 1 cell = 1 PHIEU chua ca 2.


def _qoe_gia(theo_cell: dict):
    """GetQoeCellsUseCase gia - tra QoeCellEvaluation cho tung cell.

    theo_cell: {cell_name: (before, after)} - avg QoE truoc/sau. None = cell
    khong co du lieu QoE (CEM bo qua).
    """
    from application.get_qoe_cells_use_case import QoeCellEvaluation
    from domain.services.evaluation_service import EvaluationService

    uc = AsyncMock()

    async def _execute(cr_session_id, luu_snapshot=True):
        # luu_snapshot them 20082026 (duong xem truoc). Mock PHAI nhan kwarg
        # nay, neu khong thi _lay_qoe_theo_cell() nuot TypeError va tra dict
        # rong -> test "QoE tut manh" hoa ra chay khong co QoE ma van xanh.
        ket_qua = []
        for cell, gia_tri in theo_cell.items():
            if gia_tri is None:
                before_daily, after_daily = [], []
            else:
                before, after = gia_tri
                before_daily, after_daily = [before] * 5, [after] * 5
            # SUA 03/10/2026: threshold gio la so DUONG (delta = before - after,
            # DUONG = tut) - xem domain/services/evaluation_service.py muc
            # "SUA 03/10/2026". 0.2 la dung sai GIA LAP cho test nay (KHONG
            # phai hang so that _QOE_CELL_THRESHOLD_DELTA=0.5 - test nay chi
            # can PASS/FAIL dung chieu, khong can trung hang so production).
            ev = EvaluationService().evaluate(before_daily, after_daily, threshold=0.2)
            ket_qua.append(
                QoeCellEvaluation(
                    cell_name=cell,
                    qoe_eval=ev,
                    so_ngay_before=len(before_daily),
                    so_ngay_after=len(after_daily),
                    after_points=after_daily,
                )
            )
        return ket_qua

    uc.execute.side_effect = _execute
    return uc


def _payload_theo_cell(gateway) -> dict:
    return {c.args[0]["TenCell"]: c.args[0] for c in gateway.save_cell_clm.call_args_list}


async def test_chi_khong_dat_QoS_thi_nguon_QOS():
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5}  # QoS tut manh
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 5.0)})  # QoE khong tut

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    assert p["SoChiTieuVP"] == "1"
    assert p["NoiDung"].endswith("khong dat chi tieu QoS")
    dong = use_case._cr_phieu_repo.insert.call_args.args[0]
    assert dong["nguon_khong_dat"] == "QOS"


async def test_chi_khong_dat_QoE_thi_van_xuat_phieu_nguon_QOE():
    # Truoc 17/08 cell nay KHONG duoc xuat (chi xet QoS). Gio QoE ngang hang
    # nen phai xuat.
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [5.0] * 5}  # QoS KHONG tut -> PASS
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 1.0)})  # QoE tut manh

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["C1"]
    p = _payload_theo_cell(gateway)["C1"]
    assert p["SoChiTieuVP"] == "1"
    assert p["NoiDung"].endswith("khong dat chi tieu QoE")
    assert use_case._cr_phieu_repo.insert.call_args.args[0]["nguon_khong_dat"] == "QOE"


async def test_khong_dat_CA_HAI_thi_nguon_CA_HAI_va_SoChiTieuVP_2():
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 1.0)})

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    assert p["SoChiTieuVP"] == "2"  # vi pham 2 chi tieu
    assert p["NoiDung"].endswith("khong dat ca 2 chi tieu QoS va QoE")
    assert use_case._cr_phieu_repo.insert.call_args.args[0]["nguon_khong_dat"] == "CA_HAI"


async def test_Qoe_trong_payload_la_min_after_points_khong_con_0_cung():
    # SUA KY VONG 01092026: truoc day test nay khang dinh Qoe == "2.5" - tuc la
    # no DANG KHOA LAI CHINH CAI BUG lam hong 39 phieu that. CTS khai Qoe la
    # System.Nullable`1[System.Int32], chuoi co dau cham thap phan bi tu choi
    # 400. Muc tieu GOC cua test (Qoe la so do THAT, khong con "0" cung) van
    # duoc giu - chi doi dang so cho dung kieu CTS nhan.
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 2.5)})

    await use_case.execute_all_pending()

    qoe = _payload_theo_cell(gateway)["C1"]["Qoe"]
    assert qoe == "2"  # 2.5 -> cat phan thap phan, KHONG lam tron len 3
    assert qoe != "0", "van phai la so do THAT, khong quay ve '0' cung"


async def test_khong_co_du_lieu_QoE_thi_Qoe_giu_0():
    # CEM khong tra ve cell nay -> khong co so lieu, "0" nghia la "khong co".
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    use_case._qoe_cells_use_case = _qoe_gia({"C1": None})

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    assert p["Qoe"] == "0"
    assert p["SoChiTieuVP"] == "1"
    assert use_case._cr_phieu_repo.insert.call_args.args[0]["nguon_khong_dat"] == "QOS"


async def test_sap_xep_max_khong_phai_trung_binh():
    # QoS/QoE truoc deu 5.0 (fixture ghim before=5.0).
    #   C_QOE: QoS 5.0 (tut 0.0) + QoE 2.5 (tut 2.5) -> max 2.5, TB 1.25
    #   C_DEU: QoS 3.5 (tut 1.5) + QoE 3.5 (tut 1.5) -> max 1.5, TB 1.50
    # Theo MAX  : C_QOE truoc  <- dung nhu thiet ke
    # Theo TB   : C_DEU truoc  <- test nay se do neu ai doi sang trung binh
    #
    # LUU Y khi doi so lieu: tut xuong DUNG 4.0 la PASS (ve avg_after >= MUC_TOT)
    # nen phai chon gia tri < 4.0 moi that su FAIL.
    use_case, gateway, _ = _make_use_case(
        cells=["C_DEU", "C_QOE"],
        qos_sau_theo_cell={"C_DEU": [3.5] * 5, "C_QOE": [5.0] * 5},  # before luon 5.0
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C_DEU": (5.0, 3.5), "C_QOE": (5.0, 2.5)})

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["C_QOE", "C_DEU"]


async def test_thieu_1_chi_so_van_danh_gia_theo_chi_so_kia():
    # QoS thieu ngay (3 < 5) nhung QoE ket luan duoc -> VAN xuat theo QoE,
    # KHONG roi vao KHONG_XUAT_THIEU_DU_LIEU.
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 3})
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 1.0)})

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["C1"]
    assert use_case._cr_phieu_repo.insert.call_args.args[0]["nguon_khong_dat"] == "QOE"


async def test_thieu_CA_2_chi_so_moi_la_KHONG_XUAT_THIEU_DU_LIEU():
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 3})
    use_case._qoe_cells_use_case = _qoe_gia({"C1": None})

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == []
    dong = use_case._cr_phieu_repo.insert.call_args.args[0]
    assert dong["trang_thai"] == TRANG_THAI_THIEU_DU_LIEU
    assert "CA HAI" in dong["error_message"]


async def test_QoE_chi_goi_1_LAN_cho_ca_session_khong_goi_tung_cell():
    # CEM: 1 request = 1 NGAY nhung nhan cells[] la MANG. Goi tung cell se
    # thanh 238 request/session thay vi 14.
    cells = [f"CELL_{i:02d}" for i in range(17)]
    use_case, _, _ = _make_use_case(
        cells=cells, qos_sau_theo_cell={c: [1.0] * 5 for c in cells}
    )
    qoe_uc = _qoe_gia({c: (5.0, 5.0) for c in cells})
    use_case._qoe_cells_use_case = qoe_uc

    await use_case.execute_all_pending()

    assert qoe_uc.execute.await_count == 1


async def test_QoE_loi_thi_van_chay_tiep_chi_voi_QoS():
    # QoE la chi so THEM VAO - khong duoc lam hong duong QoS da on dinh.
    use_case, gateway, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 5})
    qoe_uc = AsyncMock()
    qoe_uc.execute.side_effect = RuntimeError("CEM sap")
    use_case._qoe_cells_use_case = qoe_uc

    await use_case.execute_all_pending()

    assert _cell_da_goi_xuat(gateway) == ["C1"]
    assert use_case._cr_phieu_repo.insert.call_args.args[0]["nguon_khong_dat"] == "QOS"


# === SNAPSHOT QoS PER-CELL o job (20082026, VIEC 3) ===
# Job da goi du CTS cho toan bo cell nen luu tai day ton 0 request phu.


async def test_job_luu_snapshot_qos_RIENG_tung_cell():
    repo = AsyncMock()
    use_case, _, _ = _make_use_case(
        cells=["CELL_TE", "CELL_DAT"],
        qos_sau_theo_cell={"CELL_TE": [1.0] * 7, "CELL_DAT": [4.95] * 7},
        qos_snapshot_repo=repo,
    )

    await use_case.execute_all_pending()

    # 1 lan upsert cho MOI cell - KHONG gop chung 1 dong cho ca session
    # (bug cu "__ALL_CELLS__" che mat cell hong).
    assert repo.upsert_many.await_count == 2
    cell_da_luu = set()
    for call in repo.upsert_many.await_args_list:
        diem = call.args[1]
        ten = {d["cell_name"] for d in diem}
        assert len(ten) == 1, "1 lan upsert chi duoc chua diem cua DUNG 1 cell"
        cell_da_luu |= ten
        # 5 ngay truoc + 7 ngay sau (xem _make_use_case: QoS truoc la 5 ngay)
        assert len(diem) == 12
        assert {d["period"] for d in diem} == {"before", "after"}
    assert cell_da_luu == {"CELL_TE", "CELL_DAT"}

    # Cell DAT (khong xuat phieu) VAN duoc luu snapshot - snapshot la du lieu
    # xem lai, khong phu thuoc cell co bi xuat phieu hay khong.
    assert "CELL_DAT" in cell_da_luu


async def test_job_snapshot_qos_du_3_period_ca_ngay_T():
    """SUA 09/2026 (D3) - _luu_snapshot_qos() gio ghi DU 3 period
    (before/cr_day/after), GIONG QoE (D1). _qos_side_effect() dung chung cua
    _make_use_case() (o dau file) KHONG tra diem ngay T rieng biet (luon tra
    tu offset+1 bat ke from_dt thuc te) nen goi TRUC TIEP
    _luu_snapshot_qos() thay vi qua execute_all_pending() - kiem soat duoc
    du lieu ngay T ma khong phai sua fixture dung chung cho ca file."""
    repo = AsyncMock()
    use_case, _, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}, qos_snapshot_repo=repo
    )
    before_points = [
        {"time": (_CR_DAY_START - timedelta(days=d)).strftime("%Y-%m-%dT00:00:00Z"), "qos": 5.0}
        for d in range(1, 8)
    ]
    # 8 diem: [0]=ngay T (cr_day, gia tri rieng 9.9), [1:]=T+1..T+7 (after)
    after_points_rong = [
        {
            "time": (_CR_DAY_START + timedelta(days=d)).strftime("%Y-%m-%dT00:00:00Z"),
            "qos": (9.9 if d == 0 else 1.0),
        }
        for d in range(8)
    ]
    after_dates = {(_CR_DAY_START + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(1, 8)}
    ngay_cr = _CR_DAY_START.strftime("%Y-%m-%d")

    await use_case._luu_snapshot_qos(  # noqa: SLF001 - kiem tra truc tiep noi dung snapshot
        999, "CELL_TE", before_points, after_points_rong, after_dates, ngay_cr
    )

    repo.upsert_many.assert_awaited_once()
    diem = repo.upsert_many.await_args.args[1]
    assert len(diem) == 15, "7 before + 1 cr_day + 7 after = 15 dong"
    assert {d["period"] for d in diem} == {"before", "cr_day", "after"}
    diem_cr_day = next(d for d in diem if d["period"] == "cr_day")
    assert diem_cr_day["qos_score"] == 9.9, "diem ngay T phai duoc luu rieng, khong bi loai bo"


async def test_job_khong_co_snapshot_repo_van_chay_binh_thuong():
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )

    ket_qua = await use_case.execute_all_pending()

    assert ket_qua["so_phieu_thanh_cong"] == 1
    assert len(gateway.save_cell_clm.call_args_list) == 1


async def test_luu_snapshot_that_bai_KHONG_chan_xuat_phieu():
    # Viec chinh la xuat phieu; snapshot chi de xem lai bieu do.
    repo = AsyncMock()
    repo.upsert_many.side_effect = RuntimeError("DB down")
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}, qos_snapshot_repo=repo
    )

    ket_qua = await use_case.execute_all_pending()

    assert ket_qua["so_phieu_thanh_cong"] == 1
    assert len(gateway.save_cell_clm.call_args_list) == 1


# === XEM TRUOC (20082026) - POST /jobs/xuat-phieu-auto/xem-truoc ===
#
# Xem truoc la BAN AN TOAN cho nut chay that. No chi co gia tri neu 2 dieu
# duoi day dung, va ca 2 deu phai kiem duoc bang test chu khong phai tin.


def _khoang_ngay_cr():
    """Khoang ngay bao tron ngay CR cua session test."""
    return _NGAY_CR_TEST, _NGAY_CR_TEST


async def test_xem_truoc_KHONG_POST_len_CTS():
    # Loi hua so 1. Neu vi pham thi "xem truoc" chinh la chay that.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE", "CELL_VUA", "CELL_DAT"],
        qos_sau_theo_cell={
            "CELL_TE": [1.0] * 7,
            "CELL_VUA": [2.0] * 7,
            "CELL_DAT": [4.95] * 7,
        },
    )
    tu, den = _khoang_ngay_cr()

    ket_qua = await use_case.xem_truoc(tu, den)

    assert gateway.save_cell_clm.await_count == 0, "xem truoc KHONG duoc POST len CTS"
    assert ket_qua["tong_phieu_se_xuat"] == 2  # 2 cell te, cell DAT khong tinh


async def test_xem_truoc_KHONG_ghi_cr_phieu_va_KHONG_ghi_snapshot():
    # Loi hua so 2: khong dong vao DB. Ke ca snapshot - de ho 1 duong ghi thi
    # loi hua khong con kiem duoc.
    snapshot_repo = AsyncMock()
    use_case, _, job_log_repo = _make_use_case(
        cells=["CELL_TE"],
        qos_sau_theo_cell={"CELL_TE": [1.0] * 7},
        qos_snapshot_repo=snapshot_repo,
    )
    cr_phieu_repo = use_case._cr_phieu_repo  # noqa: SLF001
    tu, den = _khoang_ngay_cr()

    await use_case.xem_truoc(tu, den)

    cr_phieu_repo.insert.assert_not_awaited()
    cr_phieu_repo.danh_dau_khong_xuat.assert_not_awaited()
    snapshot_repo.upsert_many.assert_not_awaited()
    job_log_repo.insert.assert_not_awaited()
    job_log_repo.update_result.assert_not_awaited()


async def test_xem_truoc_KHONG_ghi_xuat_phieu_at_vao_cr_session():
    # Neu ghi thi session bi danh dau "da xu ly" va PA A se khong quet lai -
    # xem truoc se AN MAT chinh cai session no vua liet ke.
    use_case, _, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )
    tu, den = _khoang_ngay_cr()

    await use_case.xem_truoc(tu, den)

    use_case._cr_session_repo.ghi_ket_qua_xuat_phieu.assert_not_awaited()  # noqa: SLF001


async def test_xem_truoc_va_chay_that_ra_CUNG_danh_sach_cell():
    """Diem quan trong nhat cua ca tinh nang nay.

    Lech nhau thi xem truoc thanh CAI BAY: nguoi bam thay 3 phieu roi he thong
    xuat 30. Chay 2 luot tren CUNG so lieu dau vao va so ket qua.
    """
    cells = ["C_TE_NHAT", "C_TE_VUA", "C_TE_IT", "C_DAT"]
    qos = {
        "C_TE_NHAT": [1.0] * 7,
        "C_TE_VUA": [2.5] * 7,
        # 3.5 chu KHONG 4.0: avg_after == MUC_TOT (4.0) se DAT theo nhanh
        # "tut nhieu nhung van >= 4/5" (BUSINESS_RULES.md SS8.3) va cell nay
        # se khong co phieu - lam hong y dinh cua test (can 3 cell KHONG DAT).
        "C_TE_IT": [3.5] * 7,
        "C_DAT": [4.95] * 7,
    }

    # SUA 04/10/2026 (lo phu thuoc .env): MOI cell 1 sector rieng - test nay
    # kiem "xem truoc == chay that" + SAP XEP, KHONG phai tran/sector, nen 3
    # cell KHONG DAT khong duoc chung 1 sector (se bi cat con 2 neu .env=2
    # nhu production, lam SAI y dinh test can CA 3 cell).
    sector_theo_cell = {"C_TE_NHAT": 1, "C_TE_VUA": 2, "C_TE_IT": 3, "C_DAT": 4}

    uc1, _, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos, sector_theo_cell=sector_theo_cell)
    tu, den = _khoang_ngay_cr()
    xem_truoc = await uc1.xem_truoc(tu, den)
    cell_xem_truoc = [c["cell_name"] for s in xem_truoc["sessions"] for c in s["cells"]]

    uc2, gateway2, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos, sector_theo_cell=sector_theo_cell)
    await uc2.execute_all_pending()
    cell_chay_that = _cell_da_goi_xuat(gateway2)

    assert cell_xem_truoc == cell_chay_that
    # Va DUNG THU TU te nhat truoc - xem truoc phai the hien dung uu tien ma
    # luot chay that se dung khi cat theo tran.
    assert cell_xem_truoc == ["C_TE_NHAT", "C_TE_VUA", "C_TE_IT"]
    assert xem_truoc["tong_phieu_se_xuat"] == len(cell_chay_that)


async def test_xem_truoc_bo_cell_da_co_phieu_SUCCESS():
    # Giong luot chay that: cell da xuat roi thi khong dem lai, neu khong con
    # so se lon hon thuc te va nguoi bam so oan.
    use_case, _, _ = _make_use_case(
        cells=["CELL_TE", "CELL_VUA"],
        qos_sau_theo_cell={"CELL_TE": [1.0] * 7, "CELL_VUA": [2.0] * 7},
        phieu_da_co=[{"cr_session_id": SESSION_ID, "cell_name": "CELL_TE", "trang_thai": "SUCCESS"}],
    )
    tu, den = _khoang_ngay_cr()

    ket_qua = await use_case.xem_truoc(tu, den)

    ten = [c["cell_name"] for s in ket_qua["sessions"] for c in s["cells"]]
    assert ten == ["CELL_VUA"]
    assert ket_qua["tong_phieu_se_xuat"] == 1


async def test_xem_truoc_bo_cell_co_phieu_da_xoa():
    # XOA MEM (THEM 04/10/2026) - xem truoc PHAI khop voi hanh vi chay that
    # (cell nay se bi execute() tu choi 409 neu co trong danh sach), neu khong
    # xem truoc "hua" xuat mot cell ma chay that lai khong xuat duoc.
    use_case, _, _ = _make_use_case(
        cells=["CELL_DA_XOA", "CELL_VUA"],
        qos_sau_theo_cell={"CELL_DA_XOA": [1.0] * 7, "CELL_VUA": [2.0] * 7},
        phieu_da_co=[
            {
                "cr_session_id": SESSION_ID,
                "cell_name": "CELL_DA_XOA",
                "trang_thai": "FAILED",
                "deleted_at": EXECUTED_AT,
            }
        ],
    )
    tu, den = _khoang_ngay_cr()

    ket_qua = await use_case.xem_truoc(tu, den)

    ten = [c["cell_name"] for s in ket_qua["sessions"] for c in s["cells"]]
    assert ten == ["CELL_VUA"]
    assert ket_qua["tong_phieu_se_xuat"] == 1


async def test_xem_truoc_ngoai_khoang_ngay_thi_khong_quet():
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )
    xa = _NGAY_CR_TEST - timedelta(days=20)

    ket_qua = await use_case.xem_truoc(xa, xa)

    assert ket_qua["tong_phieu_se_xuat"] == 0
    assert ket_qua["sessions"] == []
    assert gateway.save_cell_clm.await_count == 0


# === E: execute_all_pending() nhan khoang ngay ===


async def test_khong_truyen_ngay_thi_hanh_vi_PA_A_khong_doi():
    # Job tu dong KHONG truyen tu_ngay/den_ngay -> phai quet DUNG 1 ngay
    # (hom nay - XUAT_PHIEU_AFTER_DAYS) y nhu truoc.
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )

    ket_qua = await use_case.execute_all_pending()

    assert ket_qua["so_session_quet"] == 1
    assert _cell_da_goi_xuat(gateway) == ["CELL_TE"]


async def test_truyen_khoang_ngay_BAO_ngay_CR_thi_van_quet():
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )

    ket_qua = await use_case.execute_all_pending(
        tu_ngay=_NGAY_CR_TEST - timedelta(days=3), den_ngay=_NGAY_CR_TEST + timedelta(days=3)
    )

    assert ket_qua["so_session_quet"] == 1
    assert _cell_da_goi_xuat(gateway) == ["CELL_TE"]


async def test_truyen_khoang_ngay_KHONG_bao_ngay_CR_thi_bo_qua():
    # Chan bug "khoang ngay bi bo qua, van quet nhu cu".
    use_case, gateway, _ = _make_use_case(
        cells=["CELL_TE"], qos_sau_theo_cell={"CELL_TE": [1.0] * 7}
    )

    ket_qua = await use_case.execute_all_pending(
        tu_ngay=_NGAY_CR_TEST - timedelta(days=10), den_ngay=_NGAY_CR_TEST - timedelta(days=5)
    )

    assert ket_qua["so_session_quet"] == 0
    assert _cell_da_goi_xuat(gateway) == []


# === Qos/Qoe PHAI la CHUOI SO NGUYEN (su co 39 phieu FAILED, 01092026) ===
#
# CTS khai ca 2 field la System.Nullable`1[System.Int32]. Gui "4.0" -> 400:
#   "$.Qoe": ["The JSON value could not be converted to
#             System.Nullable`1[System.Int32]"]
#   "request": ["The request field is required."]   <- body khong parse duoc
# 39/39 dong cr_phieu FAILED tren DB that deu mang dung loi nay.
#
# Bug vao tu 8f54b09 (doi Qoe tu hardcode "0" sang str(min(after_points))):
# after_points la list[float] vi _daily_averages() co phep chia, nen
# str(min(...)) ra "4.0". Truoc do "0" la chuoi so nguyen nen khong ai thay.


def _diem_qoe_thap_nhat(gateway, cell: str) -> str:
    return _payload_theo_cell(gateway)[cell]["Qoe"]


async def test_Qoe_KHONG_duoc_co_dau_cham_thap_phan():
    """Chan CHINH XAC lo hong da lam hong 39 phieu."""
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7}
    )
    # QoE tut tu 5.0 xuong 4.0 -> min(after_points) = 4.0 (FLOAT)
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 4.0)})  # noqa: SLF001

    await use_case.execute_all_pending()

    qoe = _diem_qoe_thap_nhat(gateway, "C1")
    assert qoe == "4", f"phai la '4', khong phai {qoe!r}"
    assert "." not in qoe, "dau cham thap phan lam .NET tu choi convert sang Int32"


async def test_Qos_va_Qoe_deu_la_chuoi_so_nguyen():
    # Ca 2 field cung 1 rang buoc kieu ben CTS - kiem chung 1 the de khong ai
    # sua 1 ben quen ben kia.
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [2.0] * 7}
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 3.0)})  # noqa: SLF001

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    for field in ("Qos", "Qoe"):
        assert isinstance(p[field], str), f"{field} phai la str"
        assert "." not in p[field], f"{field}={p[field]!r} co dau cham -> CTS 400"
        int(p[field])  # nem ValueError neu khong phai so nguyen


async def test_Qoe_khong_co_du_lieu_van_giu_0():
    # Duong router / CEM khong tra cell nay -> giu "0" nhu truoc, KHONG doi.
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7}
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": None})  # noqa: SLF001

    await use_case.execute_all_pending()

    assert _diem_qoe_thap_nhat(gateway, "C1") == "0"


async def test_Qoe_cat_phan_thap_phan_KHONG_lam_tron_len():
    # 4.9 -> "4" chu KHONG "5". Qoe la diem THAP NHAT 7 ngay sau CR; lam tron
    # len se bao cao chat luong TOT HON thuc te.
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7}
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 4.9)})  # noqa: SLF001

    await use_case.execute_all_pending()

    assert _diem_qoe_thap_nhat(gateway, "C1") == "4"


async def test_SoChiTieuVP_van_la_STR_khong_bi_doi_nham():
    # int -> CTS 400 (da gap 11/08). Dot sua kieu Qos/Qoe KHONG duoc cham vao
    # field nay.
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7}
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 1.0)})  # noqa: SLF001

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    assert p["SoChiTieuVP"] == "2"  # khong dat CA HAI
    assert isinstance(p["SoChiTieuVP"], str)


async def test_kieu_tung_field_khop_mau_phieu_19207_da_tao_THANH_CONG():
    """Doi chieu KIEU voi phieu 19207 - ban da duoc CTS chap nhan that.

    Lay tu request_payload that trong DB (cr_phieu id=51). Chi so KIEU, khong
    so gia tri (gia tri phu thuoc tram/cell)."""
    KIEU_MAU = {
        "Nam": int, "Thang": int, "TrangThai": int, "Voice": int,
        "TenCell": str, "SiteName": str, "Qos": str, "Qoe": str, "Tsd": str,
        "Ceitsd": str, "SoChiTieuVP": str, "NguyenNhan": str,
        "PhuongAnXuLyDuKien": str, "MaPhuongAn": str, "NoiDung": str,
        "Vendor": str, "UserUpdatePa": str, "LoaiCongNghe": str,
        "ProvinceCode": str, "WardCode": str, "BuildingCode": str,
        "BuildingName": str, "TtvtId": str, "TtvtName": str, "LoaiTram": str,
        "BuildingTypeName": str, "Address": str, "NguonSoLieu": str,
    }
    use_case, gateway, _ = _make_use_case(
        cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7}
    )
    use_case._qoe_cells_use_case = _qoe_gia({"C1": (5.0, 2.0)})  # noqa: SLF001

    await use_case.execute_all_pending()

    p = _payload_theo_cell(gateway)["C1"]
    assert set(p) == set(KIEU_MAU), (
        f"thieu/thua field so voi mau 19207: "
        f"thieu={set(KIEU_MAU) - set(p)}, thua={set(p) - set(KIEU_MAU)}"
    )
    for field, kieu in KIEU_MAU.items():
        assert isinstance(p[field], kieu), (
            f"{field}: mau 19207 la {kieu.__name__}, dang gui {type(p[field]).__name__}"
        )


# === B9 trong XEM TRUOC (04092026) ===
# Truoc day B9 chi ap o duong CHAY THAT -> xem truoc dem THUA: bao 16 phieu,
# chay that ra 14, nguoi bam khong hieu 2 phieu di dau.


def _repo_b9(use_case, cell_da_co: dict):
    """Gia lap cr_phieu_repo.get_success_cung_thang() cho cac cell chi dinh."""

    async def _get(cell_name, nam, thang):
        return cell_da_co.get(cell_name)

    use_case._cr_phieu_repo.get_success_cung_thang.side_effect = _get  # noqa: SLF001


async def test_xem_truoc_LOAI_cell_da_co_phieu_cung_thang():
    # SUA 04/10/2026 (lo phu thuoc .env): MOI cell 1 sector rieng - test nay
    # kiem loc B9 (da co phieu cung thang), KHONG phai tran/sector, nen ca 3
    # cell khong duoc chung 1 sector (se bi cat con 2 TRUOC khi loc B9 neu
    # .env=2 nhu production, lam sai so dem con lai sau khi loai C_TE_2).
    use_case, _, _ = _make_use_case(
        cells=["C_TE_1", "C_TE_2", "C_TE_3"],
        qos_sau_theo_cell={"C_TE_1": [1.0] * 7, "C_TE_2": [1.5] * 7, "C_TE_3": [2.0] * 7},
        sector_theo_cell={"C_TE_1": 1, "C_TE_2": 2, "C_TE_3": 3},
    )
    _repo_b9(use_case, {"C_TE_2": {"phieu_id": "20001", "cr_session_id": 999}})
    tu, den = _khoang_ngay_cr()

    ket_qua = await use_case.xem_truoc(tu, den)

    ten = [c["cell_name"] for s in ket_qua["sessions"] for c in s["cells"]]
    assert "C_TE_2" not in ten, "cell da co phieu thang nay PHAI bi loai"
    assert ket_qua["tong_phieu_se_xuat"] == 2
    assert ket_qua["tong_cell_da_co_phieu_thang"] == 1
    s0 = ket_qua["sessions"][0]
    assert s0["so_cell_da_co_phieu_thang"] == 1
    assert s0["cell_da_co_phieu_thang"] == ["C_TE_2"]


async def test_xem_truoc_va_chay_that_ra_CUNG_SO_PHIEU_khi_co_cell_dinh_B9():
    """Diem chinh cua viec nay: 2 duong phai ra CUNG con so.

    Truoc khi sua, xem truoc dem ca cell dinh B9 nen lech han voi chay that."""
    cells = ["C_TE_1", "C_TE_2", "C_TE_3"]
    qos = {"C_TE_1": [1.0] * 7, "C_TE_2": [1.5] * 7, "C_TE_3": [2.0] * 7}
    da_co = {"C_TE_2": {"phieu_id": "20001", "cr_session_id": 999}}
    tu, den = _khoang_ngay_cr()

    uc1, _, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos)
    _repo_b9(uc1, da_co)
    xem_truoc = await uc1.xem_truoc(tu, den)
    cell_xem_truoc = [c["cell_name"] for s in xem_truoc["sessions"] for c in s["cells"]]

    uc2, gateway2, _ = _make_use_case(cells=cells, qos_sau_theo_cell=qos)
    _repo_b9(uc2, da_co)
    await uc2.execute_all_pending()
    cell_chay_that = _cell_da_goi_xuat(gateway2)

    assert cell_xem_truoc == cell_chay_that
    assert xem_truoc["tong_phieu_se_xuat"] == len(cell_chay_that)


async def test_xem_truoc_khong_co_cell_nao_dinh_B9_thi_dem_0():
    use_case, _, _ = _make_use_case(
        cells=["C_TE_1"], qos_sau_theo_cell={"C_TE_1": [1.0] * 7}
    )
    _repo_b9(use_case, {})
    tu, den = _khoang_ngay_cr()

    ket_qua = await use_case.xem_truoc(tu, den)

    assert ket_qua["tong_phieu_se_xuat"] == 1
    assert ket_qua["tong_cell_da_co_phieu_thang"] == 0


async def test_xem_truoc_dung_CHUNG_ham_B9_voi_chay_that():
    # Ca 2 duong deu goi _da_co_phieu_cung_thang() - neu ai do viet dieu kien
    # rieng cho xem truoc thi test nay khong bat duoc, nhung test so 2 duong o
    # tren se bat. Day chi la chot them ve mat cau truc.
    use_case, _, _ = _make_use_case(cells=["C1"], qos_sau_theo_cell={"C1": [1.0] * 7})
    goi = []
    goc = use_case._da_co_phieu_cung_thang  # noqa: SLF001

    async def _theo_doi(cell_name, executed_at_vn):
        goi.append(cell_name)
        return await goc(cell_name, executed_at_vn)

    use_case._da_co_phieu_cung_thang = _theo_doi  # noqa: SLF001
    _repo_b9(use_case, {})
    tu, den = _khoang_ngay_cr()

    await use_case.xem_truoc(tu, den)

    assert goi == ["C1"], "xem truoc phai goi ham B9 dung chung"
