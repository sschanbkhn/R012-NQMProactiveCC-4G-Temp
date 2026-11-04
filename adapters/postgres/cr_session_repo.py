"""
CrSessionRepo — implement ICrSessionRepo (create/update/get_by_id/get_by_tram_id/list).
Tu: ARCHITECTURE.md Section 5.3; TASK_LIST.md B5.2. list()/get_by_id() mo rong o
C2.3/C2.4 (Nhom 2, 13072026): filter q/status/date range + phan trang that + join
tram_name; update() them persist qoe_result/qos_result/... (C2.2).
"""

from datetime import datetime, timezone

from sqlalchemy import Date, delete, false as sa_false, func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cr_session import CrSession, CrStatus
from domain.ports.outbound.repo_ports import ICrSessionRepo, Page, SessionFilter
from domain.value_objects.trang_thai_phieu import TRANG_THAI_CHO_XUAT_TAY
from models.alert_log import AlertLog as AlertLogModel
from models.audit_log import AuditLog as AuditLogModel
from models.cell_params import CellParams as CellParamsModel
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel
from models.cr_log import CrLog as CrLogModel
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_session import CrSession as CrSessionModel
from models.qoe_snapshot import QoeSnapshot as QoeSnapshotModel
from models.qos_snapshot import QosSnapshot as QosSnapshotModel
from models.tram import Tram as TramModel


# Whitelist ten cot duoc phep sort cho GET /sessions (22072026, xac nhan voi
# user) - BAT BUOC, khong duoc bo qua: neu build ORDER BY tu chuoi sort_by
# nguoi dung nhap truc tiep (vd f"ORDER BY {sort_by}"), day chinh la SQL
# injection vector kinh dien (sort_by co the chua "; DROP TABLE..." hoac subquery
# doc du lieu bang khac). Whitelist nay khop CHINH XAC voi Literal o
# api/routers/sessions.py (FastAPI da chan gia tri la o tang schema, 422 tu
# dong) - o day whitelist lai LAN NUA cho an toan 2 lop (repo khong duoc tin
# tuyet doi caller da validate dung, phong truong hop bi goi truc tiep tu noi
# khac ngoai router, vd script/EvaluateCrUseCase tuong lai).
_SESSION_SORT_WHITELIST = {"id", "tram_id", "tram_name", "action", "status", "executed_at", "created_at"}

# Ten mui gio cho func.timezone() - Postgres tu tra cuu trong tz database. Dung
# ten vung thay vi "+07:00" de khop cach viet o cac cho khac trong project
# (scheduler timezone="Asia/Ho_Chi_Minh"). VN khong co DST nen 2 cach tuong duong.
_TZ_VN = "Asia/Ho_Chi_Minh"

# 3 status coi la "dung o buoc 1" (CR chua xong: dang chay hoac loi - CA 2
# dang loi, KHONG_CHAY la loi "chua gui lenh len NetAct" cung CHUA xong CR).
# Dat o day de dieu kien SQL va tinh_buoc_hien_tai() (application) dung CHUNG 1
# dinh nghia - lech nhau se cho ra danh sach loc 1 dang nhung cot "buoc" hien 1
# dang khac. THEM KHONG_CHAY 16/10/2026 (yeu cau truc tiep user).
_BUOC_1_STATUS = (CrStatus.FAILED.value, CrStatus.KHONG_CHAY.value, CrStatus.RUNNING.value)

# Trang thai CUOI -> buoc 4 du CHUA xuat phieu (xuat_phieu_at IS NULL). Cach C
# (16082026): session khong ket luan duoc thi da ket thuc, khong "dang cho" gi.
_BUOC_4_STATUS_CUOI = CrStatus.KHONG_DU_DU_LIEU.value


def _session_sort_column(sort_by: str):
    # tram_name KHONG nam tren CrSessionModel (chi co qua JOIN voi TramModel)
    # - phai tro rieng, cac ten con lai deu la cot that cua CrSessionModel nen
    # dung getattr() truc tiep tren class (KHONG noi chuoi SQL) - an toan vi
    # sort_by da qua whitelist o tren TRUOC KHI ham nay duoc goi.
    if sort_by == "tram_name":
        return TramModel.tram_name
    return getattr(CrSessionModel, sort_by)


def _naive(dt: datetime | None) -> datetime | None:
    # Con dung cho filters.date_from/date_to (list(), so sanh voi created_at) -
    # KHONG dung cho executed_at/evaluated_at nua (C1.4-fix10, 2 cot nay da la
    # TIMESTAMPTZ, phai giu tzinfo).
    return dt.replace(tzinfo=None) if dt is not None else None


def _to_domain(
    row: CrSessionModel,
    tram_name: str | None = None,
    so_cell_anh_huong: int = 0,
    so_phieu_da_xuat: int = 0,
    so_cell_cho_xuat_tay: int = 0,
) -> CrSession:
    # CrSession domain entity (B2.6, mo rong o C2.1 va C2.3/C2.4 - Nhom 2
    # 13072026) - xem chu y day du trong domain/entities/cr_session.py. tram_name
    # chi duoc dien khi caller join tram (get_by_id()/list(), C2.3/C2.4) - con
    # create()/get_by_tram_id() khong join, giu None (khong can cho nghiep vu do).
    return CrSession(
        id=row.id,
        tram_id=row.tram_id,
        action=row.action,
        status=CrStatus(row.status),
        plan_name=row.plan_name,
        backup_plan_name=row.backup_plan_name,
        xml_filename=row.xml_filename,
        executed_at=row.executed_at,
        tram_name=tram_name,
        created_at=row.created_at,
        qoe_result=row.qoe_result,
        qos_result=row.qos_result,
        qoe_before=float(row.qoe_before) if row.qoe_before is not None else None,
        qoe_after=float(row.qoe_after) if row.qoe_after is not None else None,
        qos_before=float(row.qos_before) if row.qos_before is not None else None,
        qos_after=float(row.qos_after) if row.qos_after is not None else None,
        evaluated_at=row.evaluated_at,
        xuat_phieu_at=row.xuat_phieu_at,
        so_cell_thanh_cong=row.so_cell_thanh_cong,
        so_cell_tong=row.so_cell_tong,
        duong_dan_log=row.duong_dan_log,
        oss_instance_id=row.oss_instance_id,
        noc=row.noc,
        ma_loi=row.ma_loi,
        # 3 con so chi co khi caller chay subquery dem (list()) - mac dinh 0.
        so_cell_anh_huong=so_cell_anh_huong,
        so_phieu_da_xuat=so_phieu_da_xuat,
        so_cell_cho_xuat_tay=so_cell_cho_xuat_tay,
    )


class CrSessionRepo(ICrSessionRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, session: CrSession) -> CrSession:
        # session.id tu caller khong dung toi — id la SERIAL PK, DB tu sinh.
        # WORKFLOW.md dong 60 "Tao cr_session moi: status=RUNNING" — status do
        # caller quyet dinh, khong dung server_default PENDING cua model.
        row = CrSessionModel(
            tram_id=session.tram_id,
            action=session.action,
            status=session.status.value,
            plan_name=session.plan_name,
            backup_plan_name=session.backup_plan_name,
            xml_filename=session.xml_filename,
            # C1.4-fix10 - executed_at gio la TIMESTAMPTZ, giu nguyen tzinfo
            # (KHONG con .replace(tzinfo=None) nhu truoc).
            executed_at=session.executed_at,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def update(self, session: CrSession) -> CrSession:
        row = await self._session.get(CrSessionModel, session.id)
        if row is None:
            # Khong co domain error nao khop truong hop nay (domain/errors.py) —
            # day la loi goi sai cua caller (update id khong ton tai), khong phai
            # business rule violation. ValueError ro rang hon de AttributeError
            # mo ho neu de row=None crash tu nhien o buoc gan attribute ben duoi.
            raise ValueError(f"cr_session id={session.id} khong ton tai")
        row.tram_id = session.tram_id
        row.action = session.action
        row.status = session.status.value
        row.plan_name = session.plan_name
        row.backup_plan_name = session.backup_plan_name
        row.xml_filename = session.xml_filename
        # C1.4-fix10 - executed_at gio la TIMESTAMPTZ, giu nguyen tzinfo
        # (KHONG con _naive() nhu truoc).
        row.executed_at = session.executed_at
        # Them o C2.2 (Nhom 2, 13072026) - EvaluateCrUseCase can persist ket qua
        # danh gia qua CUNG method update() nay (khong tao method rieng). An toan
        # voi TriggerCrUseCase (C2.1, khong set may field nay tren CrSession no
        # dang giu - default None) vi 2 use case luon thao tac 2 OBJECT CrSession
        # khac nhau, fetch RIENG tai 2 THOI DIEM cach nhau >=21 ngay (executed_at
        # vs evaluated_at) - khong co truong hop ghi de nham gia tri cua nhau.
        # 19082026 - ty le DN provision. CHI TriggerCrUseCase set 2 field nay
        # (1 lan, luc CR chay xong). Cac use case khac (EvaluateCrUseCase) KHONG
        # lam mat gia tri: chung load session qua get_by_id() -> _to_domain() da
        # dien san 2 field tu DB, nen update() ghi lai DUNG gia tri cu.
        # (Da kiem: get_by_id() dung _to_domain, khong phai dung tay tung field.)
        row.so_cell_thanh_cong = session.so_cell_thanh_cong
        row.so_cell_tong = session.so_cell_tong
        row.duong_dan_log = session.duong_dan_log
        # oss_instance_id/noc (02/10/2026) - CHI TriggerCrUseCase set 2 field
        # nay (xem _fail()/run_cr_flow()). Cac use case khac (EvaluateCrUseCase)
        # KHONG lam mat gia tri: chung load session qua get_by_id() -> _to_domain()
        # da dien san 2 field tu DB (cung pattern voi so_cell_thanh_cong/
        # so_cell_tong o tren).
        row.oss_instance_id = session.oss_instance_id
        row.noc = session.noc
        # ma_loi (16/10/2026) - CUNG tinh than voi oss_instance_id/noc tren:
        # CHI TriggerCrUseCase set field nay (xem _fail()); cac use case khac
        # KHONG lam mat gia tri vi load qua get_by_id() -> _to_domain() da
        # dien san tu DB.
        row.ma_loi = session.ma_loi
        row.qoe_result = session.qoe_result
        row.qos_result = session.qos_result
        row.qoe_before = session.qoe_before
        row.qoe_after = session.qoe_after
        row.qos_before = session.qos_before
        row.qos_after = session.qos_after
        # C1.4-fix10 - evaluated_at gio la TIMESTAMPTZ, giu nguyen tzinfo
        # (KHONG con _naive() nhu truoc).
        row.evaluated_at = session.evaluated_at
        # C1.4-fix9 (21072026) - updated_at gio la TIMESTAMPTZ (models/cr_session.py),
        # PHAI giu tzinfo (KHONG _naive()) - nguoc lai voi executed_at/evaluated_at
        # o tren (van TIMESTAMP thuong, van can _naive()).
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def ghi_ket_qua_xuat_phieu(
        self, id: int, xuat_phieu_at: datetime, xuat_phieu_ket_qua: str
    ) -> None:
        # 14/08 - ghi DUNG 2 cot theo doi tien trinh, KHONG dong vao cot nao khac
        # (xem ly do day du trong ICrSessionRepo.ghi_ket_qua_xuat_phieu()).
        row = await self._session.get(CrSessionModel, id)
        if row is None:
            # Im lang bo qua - giong CrPhieuRepo.update_result()/danh_dau_khong_xuat():
            # day la ban ghi PHU TRO cho man hinh theo doi, khong duoc lam ca luot
            # quet crash chi vi 1 id sai.
            return
        row.xuat_phieu_at = xuat_phieu_at
        row.xuat_phieu_ket_qua = xuat_phieu_ket_qua
        # LUU Y - updated_at SE TU NHAY (khong chan duoc, va da CHAP NHAN):
        # models/cr_session.py khai bao updated_at voi onupdate=now(utc), ma
        # onupdate cua SQLAlchemy ban theo MOI lenh UPDATE tren dong - khong
        # phan biet cot nao doi. Muon giu nguyen updated_at thi phai gan de lai
        # gia tri cu, vua xau vua co race.
        # Chap nhan vi dong nay THUC SU co doi (2 cot moi), noi "vua duoc cap
        # nhat" khong phai noi doi - chi la no khong con nghia hep "du lieu
        # NGHIEP VU cua CR vua doi" nhu truoc. Ai dung updated_at de phat hien
        # thay doi nghiep vu phai doi chieu them cot cu the.
        # (Phat hien qua test test_ghi_ket_qua_xuat_phieu_KHONG_dung_toi_cot_khac,
        # ban dau comment o day ghi SAI la "KHONG dong vao updated_at".)
        await self._session.commit()

    async def xoa_cascade(self, id: int) -> dict:
        """Xoa 1 cr_session va TAT CA dong con tro toi no. Tra {ten_bang: so_dong}.

        Repo KHONG kiem status - do la luat NGHIEP VU, nam o
        XoaSessionUseCase (domain/application). Repo chi thi hanh.

        === VI SAO GOM CA CASCADE VAO 1 METHOD REPO (da xac nhan 20082026) ===
        Moi repo trong project tu commit() sau khi ghi. Neu tach viec nay ra
        use case goi 7 repo thi thanh 7 COMMIT ROI RAC, va hong o giua (mat ket
        noi, DB restart, process bi kill) se de lai 1 session MAT MOT NUA dong
        con. Trang thai do vua KHONG DOC RA duoc tu UI (so cell/so phieu hien
        len da sai, khong con khop gi voi thuc te) vua KHONG XOA LAI duoc bang
        chinh endpoint nay - vi buoc cuoi co the da chay (session bien mat, con
        dong con mo coi) hoac guard status khong con dung nua. Nguoi van hanh
        het duong, phai vao DB go tay.

        Gom lai day = 1 TRANSACTION: hoac xoa het, hoac khong xoa gi. Lan chay
        lai luon bat dau tu trang thai doc duoc.

        === THU TU XOA ===
        Nguoc chieu FK. TAT CA FK tro toi cr_session deu la ON DELETE NO ACTION
        (da kiem tren DB that 20/08) nen Postgres KHONG tu don - thieu 1 bang
        la FK violation.
        """
        so_dong: dict[str, int] = {}

        # audit_log: SET NULL chu KHONG xoa. cr_session_id o day NULLABLE, va
        # audit_log la vet KIEM TOAN "ai lam gi luc nao" - no phai song lau hon
        # doi tuong bi thao tac, neu khong thi xoa doi tuong cung xoa luon bang
        # chung ai da xoa. 2 bang kia khong co lua chon nay (NOT NULL).
        r = await self._session.execute(
            sa_update(AuditLogModel)
            .where(AuditLogModel.cr_session_id == id)
            .values(cr_session_id=None)
        )
        so_dong["audit_log_set_null"] = r.rowcount or 0

        # Thu tu theo dung dac ta (yeu cau truc tiep user), THEM alert_log:
        # no cung co FK cr_session_id (NOT NULL) nen khong xoa se chan buoc
        # cuoi. Hien bang nay dang RONG tren DB that nhung khong the dua vao
        # do - alert_use_case CO ghi vao no khi danh gia FAIL.
        for ten, model in (
            ("qos_snapshot", QosSnapshotModel),
            ("qoe_snapshot", QoeSnapshotModel),
            ("cr_phieu", CrPhieuModel),
            ("cr_log", CrLogModel),
            ("cr_affected_cells", CrAffectedCellsModel),
            ("alert_log", AlertLogModel),
            ("cell_params", CellParamsModel),
        ):
            r = await self._session.execute(delete(model).where(model.cr_session_id == id))
            so_dong[ten] = r.rowcount or 0

        r = await self._session.execute(delete(CrSessionModel).where(CrSessionModel.id == id))
        so_dong["cr_session"] = r.rowcount or 0

        # KHONG dong toi bang tram - 1 tram dung chung cho nhieu session.
        await self._session.commit()
        return so_dong

    async def dem_session_rollback_tu(self, id: int) -> int:
        """So session KHAC dang tro rollback_of_id -> session nay.

        Dung de CHAN xoa: xoa session goc se lam FK violation (rollback_of_id
        la ON DELETE NO ACTION). KHONG tu set NULL dum - do la sua du lieu cua
        MOT SESSION KHAC ma nguoi dung khong yeu cau.
        """
        stmt = select(func.count()).where(CrSessionModel.rollback_of_id == id)
        return (await self._session.execute(stmt)).scalar_one()

    async def get_by_id(self, id: int) -> CrSession | None:
        # Them join tram (C2.4, Nhom 2) - GET /sessions/{id} can tram_name hien thi
        # (API_CONTRACTS.md dong 665). outerjoin (khong inner) - tram co the bi xoa/
        # chua sync ma cr_session van con (khong nen 404 vi thieu tram_name).
        stmt = (
            select(CrSessionModel, TramModel.tram_name)
            .outerjoin(TramModel, CrSessionModel.tram_id == TramModel.tram_id)
            .where(CrSessionModel.id == id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        cr_row, tram_name = row
        return _to_domain(cr_row, tram_name)

    async def get_by_tram_id(self, tram_id: str) -> list[CrSession]:
        # Dung noi bo boi TriggerCrUseCase (C2.1, guard buoc 1) - khong can
        # tram_name (caller da biet tram_id/tram_name tu request), giu nguyen
        # khong join de khong ton chi phi thua.
        stmt = select(CrSessionModel).where(CrSessionModel.tram_id == tram_id)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def list(self, filters: SessionFilter) -> Page[CrSession]:
        # SessionFilter dien day du field o C2.3 (Nhom 2, 13072026) - xem chu y
        # trong domain/ports/outbound/repo_ports.py. q tim tren CA tram_id (cot
        # cr_session) VA tram_name (join tram) - API_CONTRACTS.md dong 625 "tim
        # kiem theo tram_id / tram_name".
        conditions = []
        if filters.q:
            pattern = f"%{filters.q}%"
            conditions.append(or_(CrSessionModel.tram_id.ilike(pattern), TramModel.tram_name.ilike(pattern)))
        if filters.status:
            conditions.append(CrSessionModel.status == filters.status)
        if filters.date_from:
            conditions.append(CrSessionModel.created_at >= _naive(filters.date_from))
        if filters.date_to:
            conditions.append(CrSessionModel.created_at <= _naive(filters.date_to))

        # === Loc theo tien trinh (16082026) ===
        # Ngay CR theo LICH GMT+7, tinh TRONG SQL: executed_at la TIMESTAMPTZ
        # (C1.4-fix10) nen .date() tho tren UTC se lech 1 ngay voi CR chay trong
        # khung UTC 17:00-23:59 - dung bug C1.4-fix8. timezone('Asia/Ho_Chi_Minh',
        # ts) doi timestamptz -> timestamp gio VN, roi moi cast DATE.
        ngay_cr_vn = func.timezone(_TZ_VN, CrSessionModel.executed_at).cast(Date)

        if filters.buoc is not None:
            # Cung so do voi tinh_buoc_hien_tai() (application/
            # get_sessions_use_case.py) - 2 cho PHAI khop nhau, neu khong thi loc
            # ra 1 danh sach nhung moi dong lai hien 1 buoc khac.
            if filters.buoc == 1:
                conditions.append(CrSessionModel.status.in_(_BUOC_1_STATUS))
            elif filters.buoc == 2:
                # KHONG_DU_DU_LIEU cung co xuat_phieu_at IS NULL nhung la trang
                # thai CUOI -> phai LOAI khoi buoc 2, khop voi
                # tinh_buoc_hien_tai(). Lech 1 trong 2 cho la session hien
                # buoc 4 tren dong nhung lai lot vao tab "dang cho KPI".
                conditions.append(CrSessionModel.status.notin_(_BUOC_1_STATUS))
                conditions.append(CrSessionModel.status != _BUOC_4_STATUS_CUOI)
                conditions.append(CrSessionModel.xuat_phieu_at.is_(None))
            elif filters.buoc == 4:
                conditions.append(CrSessionModel.status.notin_(_BUOC_1_STATUS))
                # Da xuat phieu xong HOAC da ket thuc vi khong du du lieu.
                conditions.append(
                    or_(
                        CrSessionModel.xuat_phieu_at.is_not(None),
                        CrSessionModel.status == _BUOC_4_STATUS_CUOI,
                    )
                )
            else:
                # buoc=3 (hoac gia tri la) - KHONG BAO GIO co ban ghi nao (buoc 3
                # la trang thai thoang qua, khong luu). Tra rong thay vi bo qua
                # bo loc: bo qua se tra ve TOAN BO, nguoi dung tuong "co 200
                # session dang danh gia".
                conditions.append(sa_false())

        if filters.qua_han_truoc_ngay is not None:
            # NGAY MOC do APPLICATION tinh san va truyen xuong (xem
            # GetSessionsUseCase) - repo KHONG biet XUAT_PHIEU_AFTER_DAYS la gi,
            # cung khong tu tinh "hom nay". Ly do: adapters/ KHONG duoc import
            # application/ (ARCHITECTURE.md SS9) va hang so nghiep vu khong thuoc
            # tang nay. O day chi con 1 phep so sanh DATE thuan tuy.
            conditions.append(CrSessionModel.xuat_phieu_at.is_(None))
            conditions.append(CrSessionModel.executed_at.is_not(None))
            conditions.append(ngay_cr_vn < filters.qua_han_truoc_ngay)

        # total = tong so ban ghi KHOP filter (khong phai so ban ghi tren 1 trang) -
        # can query COUNT rieng, KHONG dung len(items) sau khi da LIMIT.
        count_stmt = (
            select(func.count())
            .select_from(CrSessionModel)
            .outerjoin(TramModel, CrSessionModel.tram_id == TramModel.tram_id)
            .where(*conditions)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()

        # sort_by/order (22072026) - QUAN TRONG: ORDER BY phai ap TRUOC
        # offset()/limit() ben duoi (SQL tu no da dam bao thu tu nay trong 1
        # cau query - ORDER BY luon xu ly truoc LIMIT/OFFSET o muc engine,
        # KHONG phai sort roi moi cat trang o tang Python) - day chinh la
        # muc dich chinh cua task: FE truoc gio sort client-side CHI tren
        # 1 trang da fetch (sai pham vi). sort_by=None hoac ngoai whitelist
        # (khong nen xay ra - router da Literal-validate) -> GIU NGUYEN thu
        # tu mac dinh cu created_at desc, tranh regression.
        if filters.sort_by is not None and filters.sort_by in _SESSION_SORT_WHITELIST:
            sort_column = _session_sort_column(filters.sort_by)
            order_clause = sort_column.asc() if filters.order == "asc" else sort_column.desc()
        else:
            order_clause = CrSessionModel.created_at.desc()

        # === 3 con so tien trinh - CHONG N+1 (16082026) ===
        # Dung SUBQUERY TUONG QUAN trong SELECT, KHONG phai JOIN + GROUP BY.
        #
        # VI SAO KHONG JOIN: phai join TOI 2 bang con (cr_affected_cells va
        # cr_phieu). Join ca hai cung luc tao TICH DESCARTES giua chung - session
        # co 17 affected cell va 4 phieu se ra 68 dong, COUNT(*) tra 68 thay vi
        # 17/4. Sua bang COUNT(DISTINCT ...) duoc nhung cham hon va rat de doc
        # nham. Subquery tuong quan cho tung bang -> moi con so dem doc lap,
        # khong the lay nhiem nhau.
        #
        # VI SAO KHONG goi COUNT rieng cho tung session: GET /sessions tra ve
        # nhieu dong (size toi da 200) -> 3 x 200 = 600 query/1 request. Toan bo
        # 3 con so nay nam TRONG cung 1 cau SELECT ben duoi - dung 1 round-trip
        # DB cho ca trang (khong ke query COUNT total da co san tu truoc).
        sq_anh_huong = (
            select(func.count())
            .select_from(CrAffectedCellsModel)
            .where(CrAffectedCellsModel.cr_session_id == CrSessionModel.id)
            .scalar_subquery()
        )
        sq_da_xuat = (
            select(func.count())
            .select_from(CrPhieuModel)
            .where(
                CrPhieuModel.cr_session_id == CrSessionModel.id,
                CrPhieuModel.trang_thai == "SUCCESS",
                # deleted_at IS NULL (THEM 04/10/2026, XOA MEM) - phong ve:
                # SUCCESS KHONG the bi xoa o thoi diem viet (XoaPhieuUseCase
                # chan), nen dieu kien nay hien KHONG doi ket qua - giu cho
                # dung nhat quan voi sq_cho_xuat_tay va an toan neu luat chan
                # SUCCESS thay doi sau nay.
                CrPhieuModel.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        sq_cho_xuat_tay = (
            select(func.count())
            .select_from(CrPhieuModel)
            .where(
                CrPhieuModel.cr_session_id == CrSessionModel.id,
                # SUA 19/10/2026: danh sach CHUNG (domain/value_objects/
                # trang_thai_phieu.py) thay LIKE 'KHONG_XUAT_%' - Lich su CR,
                # dashboard, bo loc va Excel dung 1 dinh nghia "cho xuat tay";
                # them trang thai moi chi sua 1 cho, khong lech so giua man hinh.
                CrPhieuModel.trang_thai.in_(TRANG_THAI_CHO_XUAT_TAY),
                # deleted_at IS NULL (THEM 04/10/2026, XOA MEM) - KHAC sq_da_xuat
                # o tren, day la thay doi THAT: cac trang thai KHONG_XUAT_* CO
                # the bi nguoi dung xoa (chi SUCCESS moi bi chan), neu khong
                # loc thi "cho xuat tay" van dem ca dong da xoa - sai y nghia
                # "cho xu ly" vi dong do da duoc xu ly (xoa) roi.
                CrPhieuModel.deleted_at.is_(None),
            )
            .scalar_subquery()
        )

        stmt = (
            select(
                CrSessionModel,
                TramModel.tram_name,
                sq_anh_huong.label("so_cell_anh_huong"),
                sq_da_xuat.label("so_phieu_da_xuat"),
                sq_cho_xuat_tay.label("so_cell_cho_xuat_tay"),
            )
            .outerjoin(TramModel, CrSessionModel.tram_id == TramModel.tram_id)
            .where(*conditions)
            .order_by(order_clause)
        )
        # page/size = None (ca 2) -> KHONG phan trang, fetch tat ca - dung boi
        # EvaluateCrUseCase.execute_all_pending() (C2.6) can quet toan bo session
        # DONE/EVAL_PENDING (xem chu y SessionFilter). GET /sessions router luon
        # truyen page/size cu the (mac dinh 1/20) nen nhanh nay khong anh huong UI.
        if filters.page is not None and filters.size is not None:
            offset = (filters.page - 1) * filters.size
            stmt = stmt.offset(offset).limit(filters.size)

        result = await self._session.execute(stmt)
        items = [
            _to_domain(cr_row, tram_name, n_anh_huong, n_da_xuat, n_cho_tay)
            for cr_row, tram_name, n_anh_huong, n_da_xuat, n_cho_tay in result
        ]
        return Page(items=items, total=total)
