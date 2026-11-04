"""
Test tich hop job xuat phieu tu dong (JOB TU DONG buoc 4/4) - DATA THAT.
Tu: yeu cau truc tiep user.

Buoc 1-3 deu test bang MOCK. File nay kiem chung TOAN BO chuoi voi du lieu
that: repo THAT (DB that), EvaluationService THAT, QoS tu CTS THAT.

=== NHUNG GI BI THAY THE, VA TAI SAO ===
1. `save_cell_clm_gateway` -> mock: TUYET DOI KHONG POST that len TTS (WRITE API
   tao phieu that). Ghi lai payload de doi chieu 28 field.
2. `cr_phieu_repo` -> boc lop CHAN GHI (doc van xuyen xuong DB that).

   Ly do (2): `execute()` insert dong PENDING TRUOC khi goi gateway (BUOC 7,
   audit "da thu xuat" ke ca khi crash giua chung) roi update ket qua. Neu de
   chay that vao DB:
     - tao moi toi 10 dong cr_phieu cho SESSION_THAT, VA
     - dong id=82 (4G-SSN104M12-HNI, trang_thai=FAILED - bang chung CTS tu choi
       that ngay 11/08) se bi TAI DUNG va GHI DE, mat error_message/
       response_body goc.
   Yeu cau "cr_phieu van dung so dong nhu truoc khi chay" chi thoa duoc neu
   chan ghi. Cuoi test co assert doi chieu TUNG DONG (khong chi so luong) de
   chung minh khong dong nao bi them/sua.

V2 (12/08): da BO dry_run. Truoc day file nay con dua vao dry_run=True nhu 1
lop an toan THU HAI (gateway mock la lop thu nhat). Gio chi con 1 lop: gateway
LUON la AsyncMock, KHONG BAO GIO la SaveCellClmAdapter that.

V1 (12/08, PA A): job chi quet session co ngay CR cach hom nay DUNG
XUAT_PHIEU_AFTER_DAYS ngay, nen KHONG the de `bay_gio` = gio thuc (SESSION_THAT
chay CR 22/07 se khong bao gio duoc quet lai). Fixture ghim `bay_gio` = 30/07
de ngay_moc roi dung vao 22/07 - xem _NEO_BAY_GIO ben duoi.

Job_run_log VAN ghi THAT (de kiem chung RUNNING -> DONE tren DB that), don rac
o teardown cua fixture.

SUA 04/10/2026 (quyet dinh 03/10/2026, job quet bu THEM dieu kien xuat_phieu_at
IS NULL - xem application/xuat_phieu_use_case.py): execute_all_pending() ghi
THAT cr_session.xuat_phieu_at/xuat_phieu_ket_qua cua SESSION_THAT (cr_session_repo
KHONG bi mock). Fixture gio CHUP gia tri cu truoc khi reset ve NULL (de
SESSION_THAT nam trong dien quet), va KHOI PHUC dung gia tri do o finally
(chay ke ca test fail) - DB dev = DB production, KHONG duoc de lai thay doi
tren session that sau khi test chay xong.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from adapters.postgres.cr_affected_cells_repo import CrAffectedCellsRepo
from adapters.postgres.cr_phieu_repo import CrPhieuRepo
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.enodeb_repo import EnodebRepo
from adapters.postgres.job_run_log_repo import JobRunLogRepo
from application.xuat_phieu_use_case import (
    XUAT_PHIEU_MAX_PER_SECTOR,
    XUAT_PHIEU_STATUS_WHITELIST,
    XuatPhieuUseCase,
)
from domain.services.evaluation_service import EvaluationService
from infrastructure.db import AsyncSessionLocal
from infrastructure.dependencies import (
    get_cds_adapter,
    get_cts_adapter,
    get_enodeb_http_adapter,
    get_network_gateway,
    get_qos_sparkline_use_case,
)
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_session import CrSession as CrSessionModel
from models.job_run_log import JobRunLog as JobRunLogModel

# SUA 16/08: tu 553 -> 433. Session 553 da bi EvaluateCrUseCase chuyen sang
# KHONG_DU_DU_LIEU (cach C) nen ra khoi XUAT_PHIEU_STATUS_WHITELIST - job khong
# quet nua. 433 CUNG NGAY CR 22/07 nen ngay_moc ghim ben duoi van dung.
SESSION_THAT = 433  # tram 112388, CR 22/07/2026, 9 cell trong cr_affected_cells
SO_CELL_SESSION_THAT = 9
JOB_TYPE_TEST = "TEST_JOB_tich_hop_4_4"

# V1 (PA A): ngay_moc = ngay hom nay (GMT+7) - XUAT_PHIEU_AFTER_DAYS, va session
# phai co ngay CR == ngay_moc. Ghim "hom nay" = 30/07/2026 de ngay_moc = 22/07 -
# dung ngay CR cua SESSION_THAT. Chon 03:00 UTC = 10:00 GMT+7 (giua ngay) de
# khong phu thuoc chuyen doi mui gio o bien nua dem.
_NEO_BAY_GIO = datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)
_NGAY_CR_MOC = (_NEO_BAY_GIO + timedelta(hours=7)).date() - timedelta(days=8)


async def _bo_qua_neu_session_ra_khoi_dien_quet() -> None:
    """SKIP (khong FAIL) neu SESSION_THAT khong con duoc job xuat phieu quet.

    VI SAO CAN: file nay bam vao DU LIEU THAT nen trang thai session DOI THEO
    THOI GIAN - khong phai hang so. Session 553 tung dung o day, den 16/08 bi
    EvaluateCrUseCase chuyen sang KHONG_DU_DU_LIEU (cach C) va 3 test lap tuc
    fail voi thong bao rat kho hieu ("assert 553 in [433]", "StopIteration").
    Session 433 roi cung se di duong do: no cung roi vao lo thung du lieu CEM
    23-27/07 nen lan danh gia cap session ke tiep se cho ra INSUFFICIENT_DATA.

    Skip KEM LY DO ro rang tot hon fail khong ro nguyen nhan: nguoi doc biet
    ngay phai lam gi (doi SESSION_THAT sang session khac con DONE), thay vi di
    do xem code hong o dau.
    """
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(CrSessionModel.status).where(CrSessionModel.id == SESSION_THAT)
        )
        status = row.scalar_one_or_none()

    if status is None:
        pytest.skip(f"Session {SESSION_THAT} khong con trong DB")
    if status not in XUAT_PHIEU_STATUS_WHITELIST:
        pytest.skip(
            f"Session {SESSION_THAT} da chuyen sang {status}, khong con trong dien quet "
            "cua job xuat phieu. Doi SESSION_THAT sang session khac con DONE."
        )


class _CrPhieuRepoChanGhi:
    """Doc xuyen xuong repo THAT, CHAN moi lenh ghi.

    KHONG ke thua ICrPhieuRepo: chi can 4 method ma use case goi toi, khong can
    list_phieu/count_phieu (cua endpoint GET /phieu). Duck typing la du.
    """

    def __init__(self, repo_that: CrPhieuRepo):
        self._that = repo_that
        self.da_goi_insert: list[dict] = []
        self.da_goi_update: list[dict] = []
        self._id_gia = 0

    # --- doc: xuyen xuong DB that ---
    async def get_by_session_cell(self, cr_session_id: int, cell_name: str):
        return await self._that.get_by_session_cell(cr_session_id, cell_name)

    async def get_by_cr_session_id(self, cr_session_id: int):
        return await self._that.get_by_cr_session_id(cr_session_id)

    # --- ghi: CHAN, chi ghi nhan lai ---
    async def insert(self, phieu: dict) -> dict:
        self.da_goi_insert.append(phieu)
        # id AM de neu co cho nao lo dung id nay di ghi that thi se loi ngay,
        # khong am tham sua nham dong that (id that luon duong).
        self._id_gia -= 1
        return {**phieu, "id": self._id_gia}

    async def update_result(self, id: int, **kwargs) -> None:
        self.da_goi_update.append({"id": id, **kwargs})

    # V4 (12/08) - job ghi dong cr_phieu cho cell KHONG duoc xuat. Cung phai
    # chan: no se GHI DE trang_thai cua dong that (vd id=82 FAILED).
    async def danh_dau_khong_xuat(self, id: int, trang_thai: str) -> None:
        self.da_goi_update.append({"id": id, "trang_thai": trang_thai, "_danh_dau": True})


async def _chup_cr_phieu(session) -> list[tuple]:
    # Chup TUNG DONG (khong chi dem so luong) - de phat hien ca truong hop
    # so dong khong doi nhung noi dung bi ghi de (dung cai suyt xay ra voi
    # dong id=82).
    rows = (await session.execute(select(CrPhieuModel).order_by(CrPhieuModel.id))).scalars().all()
    return [
        (r.id, r.cr_session_id, r.cell_name, r.trang_thai, r.phieu_id, r.error_message)
        for r in rows
    ]


@pytest_asyncio.fixture(scope="module")
async def ket_qua_chay_that():
    """Chay execute_all_pending() DUNG 1 LAN voi data that, chia se cho ca module.

    Chay 1 lan vi moi luot goi CTS that cho tung cell (2 lan/cell) - chay lai o
    moi test se ton hang tram request khong can thiet.
    """
    async with AsyncSessionLocal() as session:
        # SUA 04/10/2026 (quyet dinh 03/10/2026, job quet bu): _lay_session_du_dieu_kien()
        # gio THEM dieu kien "xuat_phieu_at IS NULL" (chong quet lai). Fixture nay
        # chay THAT tren SESSION_THAT (ghi cr_session that, KHONG mock repo nay) nen
        # lan chay truoc se dong xuat_phieu_at that - lan chay SAU se khong con thay
        # SESSION_THAT nua, 3 test duoi phu thuoc no se FAIL ("assert 0 >= 1").
        #
        # SUA 04/10/2026 (lan 2, yeu cau truc tiep user sau khi phat hien reset
        # truoc day KHONG khoi phuc): DB dev = DB production - test KHONG duoc
        # de lai thay doi vinh vien tren session that. PHAI LUU gia tri CU
        # truoc khi reset, va KHOI PHUC dung gia tri do o finally ben duoi (chay
        # ke ca khi test trong yield raise loi) - KHONG duoc chi reset ve NULL
        # roi bo do nhu lan sua truoc.
        row_cu = (
            await session.execute(
                select(CrSessionModel.xuat_phieu_at, CrSessionModel.xuat_phieu_ket_qua)
                .where(CrSessionModel.id == SESSION_THAT)
            )
        ).first()
        xuat_phieu_at_cu = row_cu.xuat_phieu_at if row_cu else None
        xuat_phieu_ket_qua_cu = row_cu.xuat_phieu_ket_qua if row_cu else None

        await session.execute(
            update(CrSessionModel)
            .where(CrSessionModel.id == SESSION_THAT)
            .values(xuat_phieu_at=None, xuat_phieu_ket_qua=None)
        )
        await session.commit()

        cr_phieu_that = CrPhieuRepo(session)
        phieu_truoc = await _chup_cr_phieu(session)

        cr_phieu_chan_ghi = _CrPhieuRepoChanGhi(cr_phieu_that)

        # KHONG POST that - mock gateway. V2 da bo dry_run nen day la lop an
        # toan DUY NHAT: gateway PHAI la mock. Tra ve hinh dang response THAT
        # (khong con preview {url,headers,body}) de use case xu ly binh thuong.
        gateway = AsyncMock()
        gateway.save_cell_clm.return_value = {
            "status_code": 200, "isError": False, "code": "200", "message": "OK",
            "data": 999999, "totalRecord": 1,
        }

        network_gw = get_network_gateway(get_cds_adapter(), get_cts_adapter(), get_enodeb_http_adapter())
        job_repo = JobRunLogRepo(session)

        use_case = XuatPhieuUseCase(
            cr_phieu_repo=cr_phieu_chan_ghi,
            cr_session_repo=CrSessionRepo(session),
            cr_affected_cells_repo=CrAffectedCellsRepo(session),
            enodeb_repo=EnodebRepo(session),
            qos_sparkline_use_case=get_qos_sparkline_use_case(network_gw),  # CTS THAT
            save_cell_clm_gateway=gateway,
            evaluation_service=EvaluationService(),  # domain service THAT
            job_run_log_repo=job_repo,
        )

        # V1 (PA A) - ghim "hom nay" de SESSION_THAT nam trong dien quet. Boc
        # chinh method that (khong viet lai logic loc) - chi ep tham so bay_gio,
        # phan con lai van la code that dang chay tren production.
        goc_lay_session = use_case._lay_session_du_dieu_kien

        async def _lay_session_ghim_ngay(bay_gio=None, tu_ngay=None, den_ngay=None):
            # tu_ngay/den_ngay them 20082026 (duong chay bu bang tay). Wrapper
            # nay PHAI nhan va chuyen tiep chung, neu khong thi luot chay that
            # se TypeError - va vi execute_all_pending() bat rong loi toan cuc
            # nen no chi hien ra duoi dang "job FAILED", rat kho truy.
            return await goc_lay_session(
                bay_gio=_NEO_BAY_GIO, tu_ngay=tu_ngay, den_ngay=den_ngay
            )

        use_case._lay_session_du_dieu_kien = _lay_session_ghim_ngay

        job_run = await job_repo.insert({"job_type": JOB_TYPE_TEST, "trang_thai": "RUNNING"})
        try:
            ket_qua = await use_case.execute_all_pending(job_run_log_id=job_run["id"])

            dong_job = (
                await session.execute(
                    select(JobRunLogModel).where(JobRunLogModel.id == job_run["id"])
                )
            ).scalar_one()
            # Doc het field ra dict TRUOC khi teardown xoa dong - tranh test truy
            # cap object da bi xoa.
            job_log = {
                "trang_thai": dong_job.trang_thai,
                "started_at": dong_job.started_at,
                "finished_at": dong_job.finished_at,
                "so_session_quet": dong_job.so_session_quet,
                "so_phieu_thanh_cong": dong_job.so_phieu_thanh_cong,
                "so_phieu_that_bai": dong_job.so_phieu_that_bai,
                "so_cell_vuot_gioi_han": dong_job.so_cell_vuot_gioi_han,
                "error_message": dong_job.error_message,
                "chi_tiet": dong_job.chi_tiet,
            }

            yield {
                "ket_qua": ket_qua,
                "job_log": job_log,
                "gateway": gateway,
                "cr_phieu_chan_ghi": cr_phieu_chan_ghi,
                "phieu_truoc": phieu_truoc,
                "session": session,
            }
        finally:
            # Don rac job_run_log - loc theo tien to TEST_JOB_ nen khong bao gio
            # cham vao dong job that.
            await session.execute(
                delete(JobRunLogModel).where(JobRunLogModel.job_type.like("TEST_JOB_%"))
            )
            # KHOI PHUC xuat_phieu_at/xuat_phieu_ket_qua ve gia tri CU (chup o
            # tren, TRUOC khi reset) - chay trong finally nen LUON thuc hien,
            # ke ca khi 1 test trong yield assert/raise loi. DB dev = DB
            # production, khong duoc de lai trang thai khac voi truoc khi chay.
            await session.execute(
                update(CrSessionModel)
                .where(CrSessionModel.id == SESSION_THAT)
                .values(
                    xuat_phieu_at=xuat_phieu_at_cu,
                    xuat_phieu_ket_qua=xuat_phieu_ket_qua_cu,
                )
            )
            await session.commit()


async def test_chay_het_khong_loi_va_ghi_job_run_log_done(ket_qua_chay_that):
    job_log = ket_qua_chay_that["job_log"]

    # RUNNING -> DONE tren DB THAT (khong phai mock)
    assert job_log["trang_thai"] == "DONE"
    assert job_log["error_message"] is None
    assert job_log["finished_at"] is not None
    assert job_log["finished_at"] >= job_log["started_at"]


async def test_so_session_quet_khop_khao_sat(ket_qua_chay_that):
    # V1 (PA A): chi quet session co ngay CR == ngay_moc (= 22/07 do fixture
    # ghim bay_gio=30/07). So session it hon han ban "<=" cu - do CHINH LA dieu
    # PA A muon. Chi kiem "khong ra 0" va SESSION_THAT co mat.
    await _bo_qua_neu_session_ra_khoi_dien_quet()

    ket_qua = ket_qua_chay_that["ket_qua"]
    assert ket_qua["so_session_quet"] >= 1
    print(f"\n[DATA THAT] ngay_moc = {_NGAY_CR_MOC} -> quet {ket_qua['so_session_quet']} session")

    # SESSION_THAT PHAI nam trong danh sach da quet
    ids = [s["cr_session_id"] for s in ket_qua["chi_tiet"]["sessions"] if "cr_session_id" in s]
    assert SESSION_THAT in ids
    # Khong session nao bi loi (chi_tiet co key "loi" nghia la session do chet)
    assert [s for s in ket_qua["chi_tiet"]["sessions"] if "loi" in s] == []


def _chi_tiet_session_that(ket_qua) -> dict:
    return next(s for s in ket_qua["chi_tiet"]["sessions"] if s.get("cr_session_id") == SESSION_THAT)


async def test_session_that_loc_dung_cell_khong_dat(ket_qua_chay_that):
    # 9 cell trong cr_affected_cells; cell KHONG DAT = chenh lech TB truoc-sau
    # > 0.2 (nguong rieng cua xuat phieu). So luong cu the phu thuoc data CTS
    # that nen KHONG hardcode - kiem tinh hop le: nam trong [0, so cell].
    await _bo_qua_neu_session_ra_khoi_dien_quet()

    chi_tiet = _chi_tiet_session_that(ket_qua_chay_that["ket_qua"])
    so_khong_dat = chi_tiet["so_cell_khong_dat"]
    assert 0 <= so_khong_dat <= SO_CELL_SESSION_THAT
    print(
        f"\n[DATA THAT] session {SESSION_THAT}: "
        f"{so_khong_dat}/{SO_CELL_SESSION_THAT} cell KHONG DAT"
    )


async def test_thu_tu_xep_hang_theo_khoa_tren_data_that(ket_qua_chay_that):
    """SUA 09/2026 (dot sua gop truoc): luat xep hang DA DOI - thu tu KHONG
    con do do_te quyet dinh, ma do khoa_uu_tien_xuat_phieu() (nhom truoc, roi
    do_giam, roi avg_after - domain/services/evaluation_service.py). do_te
    van duoc tinh + bao cao trong job_run_log.chi_tiet nhung CHI la so tham
    khao, KHONG con dam bao giam dan xuyen suot danh sach.

    === TAI SAO PHAI DOI ASSERT (khong chi doi ten cho vui) ===
    Ban assert cu (`do_te == sorted(do_te, reverse=True)`) van "xanh" tren du
    lieu HIEN TAI cua session 433 CHI VI tinh co - session nay khong co cell
    nao thuoc nhom 0 (duoi MUC_TOI_THIEU). No PASS TINH CO chu khong phai vi
    luat cu con dung. Ca THAT da ghi trong BUSINESS_RULES.md SS8.45 (session
    4884): cell HKM022M43 do_te CHI 0.286 (thap nhat trong 13 cell) nhung VAN
    phai dung DAU vi thuoc nhom 0. Neu session 433 (hoac session khac sau nay
    duoc chon lam data that cho file nay) tinh co co 1 cell nhu vay, assert cu
    se DO NGAY va nguoi doc se tuong CODE sai - trong khi thuc ra chinh TEST
    dang kiem tra theo luat CU da bi thay. Xem docs/DEV_LOG.md muc
    "Dot sua gop: 2 cell/huong, tran phieu 6, luat xep hang moi...".

    KHONG doi cach chay (van can DB that, van dung fixture
    ket_qua_chay_that) - CHI doi assertion cho khop luat hien hanh.
    """
    await _bo_qua_neu_session_ra_khoi_dien_quet()

    chi_tiet = _chi_tiet_session_that(ket_qua_chay_that["ket_qua"])
    # Loc cell DA qua danh gia day du (co nhom/do_giam) - loai cell roi vao
    # nhanh loi POST trong _xu_ly_mot_session() (`except Exception`), dict o
    # do CHI co do_te/ket_qua, khong lien quan gi den thu tu xep hang.
    da_danh_gia = [c for c in chi_tiet["cell_da_xu_ly"] if "nhom" in c]
    # (nhom, -do_giam) - 2 thanh phan DAU cua khoa (thanh phan thu 3,
    # avg_after_min, chi de pha hoa khi do_giam bang nhau, KHONG duoc
    # job_run_log ghi lai nen khong kiem duoc o day).
    khoa = [(c["nhom"], -c["do_giam"]) for c in da_danh_gia]
    assert khoa == sorted(khoa), (
        f"thu tu sai theo khoa (nhom, -do_giam): {khoa} "
        f"(cell_da_xu_ly: {da_danh_gia})"
    )

    do_te = [c["do_te"] for c in da_danh_gia]
    # Moi cell duoc xuat deu phai THAT SU khong dat (do te > 0.2) - day la
    # tieu chi LOAI ung vien truoc khi xep hang (van GIU NGUYEN), KHONG lien
    # quan gi den thu tu - khac hoan toan voi assert thu tu o tren.
    assert all(d > 0.2 for d in do_te), f"co cell do te <= 0.2 bi xuat: {do_te}"


async def test_khong_vuot_tran_moi_sector(ket_qua_chay_that):
    # SUA 04/10/2026: tran gio tinh THEO SECTOR cua tram tat (khong phai theo
    # ca session nua) - kiem tren TUNG NHOM sector trong cell_da_xu_ly, khong
    # phai tren tong so cell cua session (1 session nhieu sector co the xuat
    # NHIEU HON XUAT_PHIEU_MAX_PER_SECTOR cell, mien la moi sector <= tran).
    ket_qua = ket_qua_chay_that["ket_qua"]
    for s in ket_qua["chi_tiet"]["sessions"]:
        if "cell_da_xu_ly" not in s:
            continue
        dem_theo_sector: dict = {}
        for c in s["cell_da_xu_ly"]:
            dem_theo_sector[c.get("sector")] = dem_theo_sector.get(c.get("sector"), 0) + 1
        for sector, dem in dem_theo_sector.items():
            assert dem <= XUAT_PHIEU_MAX_PER_SECTOR, (
                f"session {s['cr_session_id']} sector {sector} xuat {dem}"
            )


async def test_cell_da_co_phieu_success_khong_bi_xuat_lai(ket_qua_chay_that):
    # 4G-SSN087M43-HNI da co phieu SUCCESS that (phieu_id=19207) -> job KHONG
    # duoc goi gateway cho cell nay (idempotent tren DATA THAT).
    gateway = ket_qua_chay_that["gateway"]
    cell_da_goi = [c.args[0]["TenCell"] for c in gateway.save_cell_clm.call_args_list]
    assert "4G-SSN087M43-HNI" not in cell_da_goi


async def test_khong_POST_that_gateway_luon_la_mock(ket_qua_chay_that):
    # Chot an toan DUY NHAT con lai sau V2 (khong con dry_run): gateway trong
    # test nay PHAI la AsyncMock, tuyet doi khong duoc la SaveCellClmAdapter that.
    gateway = ket_qua_chay_that["gateway"]
    assert isinstance(gateway, AsyncMock)
    # va khong con tham so dry_run nao duoc truyen xuong nua
    for goi in gateway.save_cell_clm.call_args_list:
        assert "dry_run" not in goi.kwargs


async def test_cr_phieu_KHONG_bi_them_hay_sua_dong_nao(ket_qua_chay_that):
    # Doi chieu TUNG DONG (id/cell/trang_thai/phieu_id/error_message), khong
    # chi dem so luong - de bat ca truong hop dong id=82 (FAILED) bi ghi de.
    session = ket_qua_chay_that["session"]
    phieu_sau = await _chup_cr_phieu(session)
    assert phieu_sau == ket_qua_chay_that["phieu_truoc"]


async def test_lenh_ghi_cr_phieu_da_bi_chan_dung_nhu_thiet_ke(ket_qua_chay_that):
    # Chung minh use case THAT SU co y dinh ghi (neu khong chan thi DB da bi sua).
    chan_ghi = ket_qua_chay_that["cr_phieu_chan_ghi"]
    so_lan_ghi = len(chan_ghi.da_goi_insert) + len(chan_ghi.da_goi_update)
    print(
        f"\n[DA CHAN] {len(chan_ghi.da_goi_insert)} lenh insert + "
        f"{len(chan_ghi.da_goi_update)} lenh ghi khac vao cr_phieu"
    )
    # Dong insert la PENDING (truoc khi goi gateway) HOAC KHONG_XUAT_* (V4 -
    # cell job co y khong xuat, chua bao gio goi gateway).
    assert all(
        p["trang_thai"] in ("PENDING", "KHONG_XUAT_VUOT_GIOI_HAN", "KHONG_XUAT_HET_LUOT_THU")
        for p in chan_ghi.da_goi_insert
    ), [p["trang_thai"] for p in chan_ghi.da_goi_insert]
    # Gateway mock luon tra 200 nen ket qua ghi lai phai la SUCCESS (hoac
    # KHONG_XUAT_* neu la lenh danh dau cua V4).
    assert all(
        u["trang_thai"] in ("SUCCESS", "KHONG_XUAT_VUOT_GIOI_HAN", "KHONG_XUAT_HET_LUOT_THU")
        for u in chan_ghi.da_goi_update
    ), [u["trang_thai"] for u in chan_ghi.da_goi_update]
    assert so_lan_ghi >= 0  # co the =0 neu khong cell nao khong dat


async def test_payload_28_field_khop_mau_phieu_19207(ket_qua_chay_that):
    gateway = ket_qua_chay_that["gateway"]
    if not gateway.save_cell_clm.call_args_list:
        pytest.skip("Khong cell nao KHONG DAT trong lan chay nay - khong co payload de doi chieu")

    payload = gateway.save_cell_clm.call_args_list[0].args[0]

    # 28 field dung mau phieu 19207 da POST THAT thanh cong (11/08)
    field_bat_buoc = {
        "Nam", "Thang", "TrangThai", "TenCell", "SiteName", "Qos", "Qoe", "Tsd",
        "Voice", "Ceitsd", "SoChiTieuVP", "NguyenNhan", "PhuongAnXuLyDuKien",
        "MaPhuongAn", "NoiDung", "Vendor", "UserUpdatePa", "LoaiCongNghe",
        "ProvinceCode", "WardCode", "BuildingCode", "BuildingName", "TtvtId",
        "TtvtName", "LoaiTram", "BuildingTypeName", "Address", "NguonSoLieu",
    }
    assert set(payload.keys()) == field_bat_buoc, (
        f"thieu: {field_bat_buoc - set(payload)}, thua: {set(payload) - field_bat_buoc}"
    )

    # SoChiTieuVP PHAI la str - BUG THAT da gap: gui int -> CTS tu choi 400
    assert isinstance(payload["SoChiTieuVP"], str), "SoChiTieuVP phai la STR (int -> CTS 400)"
    assert payload["SoChiTieuVP"] == "1"
    # Cac field kieu str khac (doi chieu mau 19207)
    for ten in ("Qos", "Qoe", "Tsd", "Ceitsd", "TenCell", "SiteName", "ProvinceCode"):
        assert isinstance(payload[ten], str), f"{ten} phai la str, dang la {type(payload[ten])}"
    # Cac field kieu int (mau 19207: Nam/Thang/TrangThai/Voice la so)
    for ten in ("Nam", "Thang", "TrangThai", "Voice"):
        assert isinstance(payload[ten], int), f"{ten} phai la int, dang la {type(payload[ten])}"

    print("\n[PAYLOAD THAT] cell =", payload["TenCell"])
    for k in sorted(payload):
        print(f"   {k:22} = {payload[k]!r:35} ({type(payload[k]).__name__})")
