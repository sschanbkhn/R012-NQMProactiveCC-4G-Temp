"""
CrPhieuRepo — implement ICrPhieuRepo.
Tu: yeu cau truc tiep user (KHOI 2/5 SaveCellClm) - audit + chong trung.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import ICrPhieuRepo
from models.cr_affected_cells import CrAffectedCells as CrAffectedCellsModel
from models.cr_phieu import CrPhieu as CrPhieuModel
from models.cr_phieu_lan_thu import CrPhieuLanThu as CrPhieuLanThuModel
from models.cr_session import CrSession as CrSessionModel
from models.tram import Tram as TramModel

# Whitelist sort (11/08, UI lich su phieu) - khop CHINH XAC voi Literal o
# api/routers/phieu.py. Router da chan gia tri la (422 tu dong o tang schema),
# o day whitelist LAI lan nua cho an toan 2 lop: repo khong duoc tin tuyet doi
# caller da validate (co the bi goi tu script/use case khac ngoai router) -
# cung nguyen tac da ap dung o CrSessionRepo._SESSION_SORT_WHITELIST.
_PHIEU_SORT_WHITELIST = {"id", "cr_session_id", "cell_name", "trang_thai", "created_at"}

# TRAM CUA CELL (19/10/2026, yeu cau truc tiep user) lay tu
# cr_affected_cells.tram_id (= LNBTS trong dist_name cua chinh cell; do DB
# 19/10: 178/178 phieu khop, 0 dong trung tram tat) - CUNG nguon voi vendor
# cell cua dashboard. KHONG dung cell_infor: bang do khong co tram_id,
# cell_name khong unique (87.913 dong / 87.800 cell) va 12/178 phieu khong
# khop ten. Vendor chuan hoa UPPER(TRIM) GIONG dashboard_repo._VENDOR de loc
# 2 noi ra cung so.
def _vendor_chuan(cot):
    return func.upper(func.trim(cot))


def _phuong_an():
    # PhuongAnXuLyDuKien chi nam trong payload JSONB (khong co cot rieng).
    return CrPhieuModel.request_payload["PhuongAnXuLyDuKien"].astext


def _mau_tim(q: str) -> str:
    # ESCAPE '%' va '_' truoc khi boc vao '%...%': trong LIKE/ILIKE chung la KY
    # TU DAI DIEN, khong phai chu binh thuong. Khong escape thi go "TEST_UI_001"
    # se khop ca "TESTxUIy001" - nguoi dung thay ket qua la nhung khong hieu vi
    # sao co no. Cell name that co dau '-' (khong dai dien) nen it lo, nhung
    # phieu_id/cell mau lai co '_'.
    # Escape '\' TRUOC TIEN, neu khong se escape nham chinh cac dau '\' minh vua
    # them vao. escape="\\" duoc truyen o cho goi .ilike().
    an_toan = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{an_toan}%"


def _to_dict(
    row: CrPhieuModel,
    tram_id: str | None = None,
    tram_name: str | None = None,
    vuot_2_phieu_sector: bool | None = None,
) -> dict:
    # tram_id/tram_name (04092026) - cua CR TAT TRAM, lay bang JOIN cr_session
    # + tram o list_phieu(). Mac dinh None cho cac cho goi khac (get_by_id,
    # get_by_session_cell...) von khong can 2 truong nay va khong join.
    #
    # !!! CAI BAY: request_payload->>'SiteName' TRONG NHU dap an nhung KHONG
    # PHAI - do la tram cua CHINH CELL duoc xuat phieu (cell LAN CAN), con cai
    # nguoi dung can biet la tram BI TAT trong CR. Hai tram nay KHAC NHAU:
    # phieu id=2258 co SiteName 4G-SSN121M-HNI (tram 111459 cua cell) trong khi
    # CR tat tram 111121. Bat buoc JOIN cr_session.
    return {
        "id": row.id,
        "tram_id": tram_id,
        "tram_name": tram_name,
        "cr_session_id": row.cr_session_id,
        "cell_name": row.cell_name,
        "trang_thai": row.trang_thai,
        "request_payload": row.request_payload,
        "response_body": row.response_body,
        "phieu_id": row.phieu_id,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "so_lan_thu": row.so_lan_thu,
        "nguon_khong_dat": row.nguon_khong_dat,
        # vuot_2_phieu_sector (THEM 04/10/2026, quyet dinh 04/10/2026, CHI DOC -
        # KHONG sua du lieu cu) - None cho dong KHONG phai SUCCESS (khong tinh,
        # KHONG phai "False" - tranh hieu nham "da xac nhan KHONG vuot" voi
        # "khong ap dung"). Xem list_phieu() ve cach tinh (window function
        # theo (session, sector), sector=None gom 1 nhom rieng).
        "vuot_2_phieu_sector": vuot_2_phieu_sector,
        # deleted_at (THEM 04/10/2026, XOA MEM) - None = chua xoa. Tra ve o
        # MOI cho goi _to_dict() (ke ca get_by_session_cell/get_by_id) - BAT
        # BUOC de XuatPhieuUseCase.execute() phat hien duoc phieu da xoa va
        # chan tao lai (xem domain/errors.py::PhieuDaXoaError).
        "deleted_at": row.deleted_at,
    }


class CrPhieuRepo(ICrPhieuRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_session_cell(self, cr_session_id: int, cell_name: str) -> dict | None:
        stmt = select(CrPhieuModel).where(
            CrPhieuModel.cr_session_id == cr_session_id, CrPhieuModel.cell_name == cell_name
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_dict(row) if row else None

    async def get_success_cung_thang(self, cell_name: str, nam: int, thang: int) -> dict | None:
        """Tim phieu SUCCESS cua cell nay trong CUNG Nam/Thang, KHONG gioi han session.

        === VI SAO CAN (B9 - loi that) ===
        Chong trung hien tai chi xet trong 1 SESSION (get_by_session_cell). Nhung
        CTS chong trung theo CELL + THANG. Mot cell co the nam trong
        cr_affected_cells cua HAI session khac nhau (2 lan CR cua 2 tram lan can
        nhau trong cung thang) -> session thu hai van POST -> CTS tu choi
        "Bad Cell ... dang xu ly cua thang 202608".
        Da xay ra that voi 4 cell: HDG116M13, HDG138M42, HDG138M52, TTI087M11.

        CTS chan dung nen KHONG co phieu trung nao lot len that. Cai mat la ta
        POST vo ich (WRITE API len he thong ngoai) va sinh ra mot dong FAILED
        moi lan - lam nhieu bang lich su phieu va lam so lieu that bai cua job
        cao gia tao.

        === VI SAO DOC Nam/Thang TU request_payload thay vi tu created_at ===
        Nam/Thang trong payload duoc tinh tu cr_session.executed_at (gio GMT+7),
        KHONG phai luc tao dong cr_phieu. Mot phieu xuat ngay 02/09 cho CR chay
        ngay 30/08 mang Thang=8. So sanh theo created_at se so nham sang thang 9
        va bo lot dung truong hop can chan. request_payload la thu CTS THAT SU
        nhin thay, nen so theo no moi khop voi luat chong trung cua CTS.
        """
        stmt = select(CrPhieuModel).where(
            CrPhieuModel.cell_name == cell_name,
            CrPhieuModel.trang_thai == "SUCCESS",
            # astext + so sanh chuoi: JSONB luu so nguyen nhung ->> luon tra text
            CrPhieuModel.request_payload["Nam"].astext == str(nam),
            CrPhieuModel.request_payload["Thang"].astext == str(thang),
        )
        result = await self._session.execute(stmt)
        # first() chu khong scalar_one_or_none(): ve ly thuyet chi co 1 dong,
        # nhung neu du lieu cu co 2 dong SUCCESS trung thi scalar_one_or_none()
        # se NEM LOI ngay giua luong xuat phieu - trong khi cau tra loi ta can
        # ("da co phieu roi") van dung. Lay dong dau la du.
        row = result.scalars().first()
        return _to_dict(row) if row else None

    async def get_by_id(self, id: int) -> dict | None:
        stmt = select(CrPhieuModel).where(CrPhieuModel.id == id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_dict(row) if row else None

    async def xoa(self, id: int) -> int:
        """XOA MEM (SUA 04/10/2026, quyet dinh 04/10/2026, yeu cau truc tiep
        user) - set deleted_at=now() THAY VI DELETE that. Tra so dong CAP NHAT
        lan nay (0 = khong tim thay HOAC da xoa tu truoc).

        VI SAO DOI TU HARD DELETE: dong cu xoa() DELETE that -> mat sach dau
        vet, UNIQUE(cr_session_id, cell_name) trong lai ngay nen job tu dong
        lai TAO MOI phieu cho dung cell vua bi nguoi dung xoa - di NGUOC quyet
        dinh 04/10/2026 ("phieu da xoa KHONG BAO GIO duoc tao lai"). Dong VAN
        CON trong bang (chi danh dau) de get_by_session_cell()/get_by_id() con
        THAY duoc ma chan XuatPhieuUseCase.execute() tao lai - xem
        domain/errors.py::PhieuDaXoaError.

        WHERE deleted_at IS NULL (khong phai chi WHERE id=id): goi lai tren
        dong DA xoa tra ve 0 (KHONG ghi de lai thoi diem xoa goc) - XoaPhieuUseCase
        dung gia tri nay de bao "da xoa truoc do" thay vi am tham cap nhat lai.

        Repo KHONG kiem trang_thai - luat nghiep vu "khong xoa phieu da len
        CTS" nam o XoaPhieuUseCase.

        cr_phieu_lan_thu (A5, FK ON DELETE CASCADE) KHONG bi anh huong - day
        la UPDATE, khong con DELETE nen lich su lan thu GIU NGUYEN (dung yeu
        cau "xoa -> cr_phieu_lan_thu con nguyen").
        """
        r = await self._session.execute(
            update(CrPhieuModel)
            .where(CrPhieuModel.id == id, CrPhieuModel.deleted_at.is_(None))
            .values(deleted_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        return r.rowcount or 0

    async def insert(self, phieu: dict) -> dict:
        # C1.4-fix9 pattern - created_at set qua Python datetime.now(timezone.utc),
        # KHONG server_default (xem models/cr_phieu.py).
        row = CrPhieuModel(
            cr_session_id=phieu["cr_session_id"],
            cell_name=phieu["cell_name"],
            trang_thai=phieu["trang_thai"],
            request_payload=phieu["request_payload"],
            response_body=phieu.get("response_body"),
            phieu_id=phieu.get("phieu_id"),
            error_message=phieu.get("error_message"),
            # 17082026 - QOS/QOE/CA_HAI. .get() chu khong [..]: dong
            # KHONG_XUAT_* (thieu du lieu / vuot tran) khong co nguon nao ca.
            nguon_khong_dat=phieu.get("nguon_khong_dat"),
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_dict(row)

    async def update_result(
        self,
        id: int,
        trang_thai: str,
        response_body: dict | None,
        phieu_id: str | None,
        error_message: str | None,
        request_payload: dict | None = None,
        so_lan_thu_them: int = 0,
    ) -> None:
        row = await self._session.get(CrPhieuModel, id)
        if row is None:
            return
        row.trang_thai = trang_thai
        row.response_body = response_body
        row.phieu_id = phieu_id
        # B8 (02092026) - GIU error_message cu khi lan nay KHONG co loi.
        # Truoc day gan thang error_message (= None khi SUCCESS) nen luc phieu
        # chuyen FAILED -> SUCCESS la XOA SACH ly do CTS tu choi cac lan truoc.
        # Da xay ra that voi 3 cell SSN121M*: nhin vao DB chi con SUCCESS,
        # khong con dau vet vi sao 2 lan dau hong.
        # Chi ghi de khi lan nay CO loi moi; None = "lan nay khong co loi",
        # KHONG phai "xoa loi cu di".
        # (Lich su day du tung lan POST nam o bang cr_phieu_lan_thu - A5. Cot
        # nay van giu de doc nhanh ngay tren dong phieu, khong phai join.)
        if error_message is not None:
            row.error_message = error_message
        # V3 (12/08) - CONG THEM so lan da POST that trong lan goi nay (truoc
        # day la co bool +1). Retry nam trong 1 lan goi execute() nen +1 se noi
        # doi: cell bi 5xx 3 lan van hien so_lan_thu=1 du da lam phien CTS 3
        # lan. Caller quyet dinh con so, repo KHONG tu suy tu trang_thai.
        if so_lan_thu_them:
            row.so_lan_thu = (row.so_lan_thu or 0) + so_lan_thu_them
        # CHI ghi de khi caller truyen tuong minh - None nghia la "khong dung
        # toi cot nay" (KHONG phai "xoa thanh NULL"), vi request_payload la
        # NOT NULL trong DB va caller cu khong truyen tham so nay.
        if request_payload is not None:
            row.request_payload = request_payload
        await self._session.commit()

    async def ghi_lan_thu(
        self,
        cr_phieu_id: int,
        nguoi_thuc_hien: str,
        ket_qua: str,
        phieu_id: str | None = None,
        error_message: str | None = None,
        request_payload: dict | None = None,
        response_body: dict | None = None,
    ) -> None:
        """Ghi THEM 1 dong lich su lan POST (A5) - KHONG BAO GIO ghi de.

        Bang nay la noi duy nhat giu duoc TOAN BO lich su: cr_phieu chi co 1
        dong/cell/session va bi ghi de moi lan thu lai.
        """
        row = CrPhieuLanThuModel(
            cr_phieu_id=cr_phieu_id,
            # C1.4-fix9 - set qua Python de dam bao UTC (xem models/cr_phieu_lan_thu.py)
            thoi_diem=datetime.now(timezone.utc),
            nguoi_thuc_hien=nguoi_thuc_hien,
            ket_qua=ket_qua,
            phieu_id=phieu_id,
            error_message=error_message,
            request_payload=request_payload,
            response_body=response_body,
        )
        self._session.add(row)
        await self._session.commit()

    async def lay_lan_thu(self, cr_phieu_id: int) -> list[dict]:
        """Lich su cac lan POST cua 1 phieu, cu -> moi."""
        stmt = (
            select(CrPhieuLanThuModel)
            .where(CrPhieuLanThuModel.cr_phieu_id == cr_phieu_id)
            .order_by(CrPhieuLanThuModel.thoi_diem)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "id": r.id,
                "cr_phieu_id": r.cr_phieu_id,
                "thoi_diem": r.thoi_diem,
                "nguoi_thuc_hien": r.nguoi_thuc_hien,
                "ket_qua": r.ket_qua,
                "phieu_id": r.phieu_id,
                "error_message": r.error_message,
                "request_payload": r.request_payload,
                "response_body": r.response_body,
            }
            for r in result.scalars().all()
        ]

    async def get_by_cr_session_id(self, cr_session_id: int) -> list[dict]:
        stmt = select(CrPhieuModel).where(CrPhieuModel.cr_session_id == cr_session_id)
        result = await self._session.execute(stmt)
        return [_to_dict(row) for row in result.scalars().all()]

    async def danh_dau_khong_xuat(self, id: int, trang_thai: str) -> None:
        # V4 (12/08) - doi DUY NHAT cot trang_thai. KHONG dung update_result():
        # ham do ghi de ca response_body/phieu_id/error_message/so_lan_thu, se
        # xoa mat ly do CTS tu choi tren dong FAILED cu - dung thu nguoi van
        # hanh can de sua nguyen nhan goc. Xem ICrPhieuRepo.danh_dau_khong_xuat().
        row = await self._session.get(CrPhieuModel, id)
        if row is None:
            # Im lang bo qua giong update_result() - day la ban ghi phu tro,
            # khong duoc lam ca luot quet crash chi vi 1 id sai.
            return
        row.trang_thai = trang_thai
        await self._session.commit()

    def _filter_conditions(
        self,
        session_id: int | None,
        trang_thai: str | None,
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
        session_ids: list[int] | None = None,
    ) -> list:
        # Tach rieng de list_phieu()/count_phieu() dung CHUNG dieu kien - neu
        # viet 2 lan se co ngay total lech voi data khi sua 1 ben quen ben kia.
        # 19/10/2026: dong_excel() (Excel phieu + sheet Phieu hau kiem) cung
        # dung ham nay -> danh sach va Excel cung bo loc ra cung so dong.
        #
        # deleted_at IS NULL (THEM 04/10/2026, quyet dinh 04/10/2026, yeu cau
        # truc tiep user) - LUON loc, KHONG co tham so bat/tat: "phieu da xoa
        # KHONG hien o bat cu dau nua" la quyet dinh TUYET DOI, khong co man
        # hinh/che do nao can xem lai phieu da xoa qua endpoint nay. Day cung
        # la noi GET /phieu?trang_thai=FAILED (nguon dem song cho canh bao
        # "Co N phieu xuat loi" o FE sau khi sua) tu dong het loi do - KHONG
        # can sua rieng o dau khac.
        conditions: list = [CrPhieuModel.deleted_at.is_(None)]
        if session_id is not None:
            conditions.append(CrPhieuModel.cr_session_id == session_id)
        if trang_thai is not None:
            conditions.append(CrPhieuModel.trang_thai == trang_thai)
        # 17082026 - loc theo chi so lam cell khong dat (QOS/QOE/CA_HAI).
        # LUU Y: dong tao TRUOC dot nay co nguon_khong_dat = NULL nen se KHONG
        # xuat hien o bat ky gia tri loc nao - dung y (khong ghi nhan thi khong
        # the khang dinh thuoc nhom nao).
        if nguon is not None:
            conditions.append(CrPhieuModel.nguon_khong_dat == nguon)
        # V2 (12/08) - DA BO luat "khong truyen trang_thai thi an dong DRY_RUN".
        # Khong con dong DRY_RUN nao duoc sinh ra nua, va tu V4 thi cac gia tri
        # KHONG_XUAT_* PHAI hien mac dinh (do la ca muc dich cua V4: cell chua
        # xuat phai nhin thay duoc tren UI). Gio "khong truyen trang_thai" dung
        # nghia den la LAY TAT CA.

        # 13/08 - 1 o tim chung: GAN DUNG tren cell_name HOAC phieu_id.
        # `if q` (khong phai `is not None`): ?q= rong tu FE la "chua go gi", them
        # dieu kien ILIKE '%%' vao chi ton 1 lan quet vo ich.
        if q:
            # phieu_id NULL (dong chua xuat duoc) -> ILIKE tra NULL, OR van xu ly
            # dung: dong do chi khop khi cell_name khop. KHONG can coalesce.
            conditions.append(
                or_(
                    CrPhieuModel.cell_name.ilike(_mau_tim(q), escape="\\"),
                    CrPhieuModel.phieu_id.ilike(_mau_tim(q), escape="\\"),
                )
            )

        # Nua khoang [tu_ngay, den_ngay) - router da quy doi NGAY LICH GMT+7 ->
        # moc UTC va tu cong 1 ngay vao den_ngay (api/routers/loc_ngay.py). Repo
        # CHI nhan datetime da chuan, KHONG tu doi mui gio (giong
        # JobRunLogRepo._filter_conditions).
        if tu_ngay is not None:
            conditions.append(CrPhieuModel.created_at >= tu_ngay)
        if den_ngay is not None:
            conditions.append(CrPhieuModel.created_at < den_ngay)

        # 4 bo loc 19/10/2026. None = khong loc; list RONG = 0 dong (vd giao
        # khu_vuc x ma_tinh rong) - in_([]) cua SQLAlchemy ra FALSE, dung y.
        if session_ids is not None:
            conditions.append(CrPhieuModel.cr_session_id.in_(session_ids))
        if phuong_an is not None:
            conditions.append(_phuong_an().in_(phuong_an))
        if ma_tinh is not None or vendor is not None:
            # EXISTS tren tram cua cell (khong JOIN vao cau chinh) de list_phieu
            # giu nguyen JOIN tram TAT san co. cr_affected_cells UNIQUE
            # (session, cell) nen EXISTS tuong duong JOIN 1-1.
            a, t = aliased(CrAffectedCellsModel), aliased(TramModel)
            dk = [a.cr_session_id == CrPhieuModel.cr_session_id, a.cell_name == CrPhieuModel.cell_name]
            if ma_tinh is not None:
                dk.append(t.ma_tinh.in_(ma_tinh))
            if vendor is not None:
                dk.append(_vendor_chuan(t.ten_thiet_bi).in_(vendor))
            conditions.append(
                select(1).select_from(a).join(t, t.tram_id == a.tram_id).where(*dk).exists()
            )
        return conditions

    async def list_phieu(
        self,
        session_id: int | None,
        trang_thai: str | None,
        page: int,
        size: int,
        sort_by: str | None = None,
        order: str = "desc",
        # 3 tham so 13/08 dat o CUOI + co default: moi cho dang goi
        # list_phieu(session_id, trang_thai, page, size, sort_by, order) theo vi
        # tri (router, test cu) KHONG phai sua theo.
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> list[dict]:
        conditions = self._filter_conditions(
            session_id, trang_thai, q, tu_ngay, den_ngay, nguon, ma_tinh, vendor, phuong_an
        )

        # sort_by=None hoac ngoai whitelist (khong nen xay ra - router da
        # Literal-validate) -> created_at DESC: phieu moi nhat truoc, dung nhu
        # dac ta va cung la thu tu UI lich su can mac dinh.
        if sort_by is not None and sort_by in _PHIEU_SORT_WHITELIST:
            # getattr() tren model column, KHONG noi chuoi SQL - an toan vi
            # sort_by da qua whitelist ngay tren.
            sort_column = getattr(CrPhieuModel, sort_by)
            order_clause = sort_column.asc() if order == "asc" else sort_column.desc()
        else:
            order_clause = CrPhieuModel.created_at.desc()

        # ORDER BY dat TRUOC offset/limit trong CUNG 1 cau SQL - Postgres sort
        # toan bo tap khop filter roi moi cat trang (khong phai sort trong
        # trang), giong C1.6-fix da lam cho /sessions va /stations.
        offset = (page - 1) * size

        # vuot_2_phieu_sector (THEM 04/10/2026, quyet dinh 04/10/2026, CHI DOC
        # - KHONG sua cr_phieu cu) - subquery RIENG tinh THU TU cua MOI phieu
        # SUCCESS trong (cr_session_id, sector), sector suy tu JOIN
        # cr_affected_cells theo (cr_session_id, cell_name). PHAI tinh tren
        # TOAN BO phieu SUCCESS (khong phu thuoc filter/trang cua request
        # hien tai) roi moi JOIN vao cau chinh - neu tinh TRONG cung 1 cau co
        # WHERE loc theo session_id/trang_thai thi cua so PARTITION se bi thu
        # hep sai (vd loc trang_thai=FAILED se lam mat het phieu SUCCESS dung
        # de xep hang). PARTITION BY voi sector=NULL tu nhien gom thanh 1 nhom
        # rieng (hanh vi chuan cua Postgres), dung YEU CAU "sector NULL la 1
        # nhom rieng" ma khong can xu ly rieng.
        rank_subq = (
            select(
                CrPhieuModel.id.label("phieu_id"),
                func.row_number()
                .over(
                    partition_by=(CrPhieuModel.cr_session_id, CrAffectedCellsModel.sector),
                    order_by=CrPhieuModel.created_at,
                )
                .label("thu_tu"),
            )
            .select_from(CrPhieuModel)
            .outerjoin(
                CrAffectedCellsModel,
                (CrAffectedCellsModel.cr_session_id == CrPhieuModel.cr_session_id)
                & (CrAffectedCellsModel.cell_name == CrPhieuModel.cell_name),
            )
            .where(
                CrPhieuModel.trang_thai == "SUCCESS",
                # deleted_at IS NULL (THEM 04/10/2026) - phong ve: SUCCESS
                # KHONG the bi xoa o thoi diem viet (XoaPhieuUseCase chan), nen
                # dieu kien nay hien KHONG doi ket qua, nhung giu cho rank_subq
                # dung nguyen tac "khong bao gio xep hang tren dong da xoa"
                # neu luat chan SUCCESS thay doi sau nay.
                CrPhieuModel.deleted_at.is_(None),
            )
            .subquery()
        )

        # JOIN trong CUNG 1 query (khong goi rieng tung dong): 20 dong/trang ma
        # goi lai thi thanh 20 round-trip DB - dung loi N+1 da tranh o
        # GET /sessions bang subquery. outerjoin chu khong join: cr_session
        # luon ton tai (FK NOT NULL) nhung tram co the khong (DB THAT khong co
        # FK cr_session.tram_id -> tram, da do bang pg_constraint 20/08), nen
        # inner join se AM THAM LAM MAT dong phieu neu tram bi xoa. Tuong tu
        # voi rank_subq: dong KHONG phai SUCCESS khong co trong subquery do
        # (WHERE trang_thai='SUCCESS' o tren), outerjoin tra NULL cho thu_tu,
        # _to_dict() doc dung thanh None (khong phai False - xem comment do).
        stmt = (
            select(CrPhieuModel, CrSessionModel.tram_id, TramModel.tram_name, rank_subq.c.thu_tu)
            .outerjoin(CrSessionModel, CrSessionModel.id == CrPhieuModel.cr_session_id)
            .outerjoin(TramModel, TramModel.tram_id == CrSessionModel.tram_id)
            .outerjoin(rank_subq, rank_subq.c.phieu_id == CrPhieuModel.id)
            .where(*conditions)
            .order_by(order_clause)
            .offset(offset)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        return [
            _to_dict(
                row,
                tram_id=tid,
                tram_name=tname,
                vuot_2_phieu_sector=(thu_tu > 2) if thu_tu is not None else None,
            )
            for row, tid, tname, thu_tu in result.all()
        ]

    async def count_phieu(
        self,
        session_id: int | None,
        trang_thai: str | None,
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> int:
        # COUNT rieng, KHONG dung len(items) sau khi da LIMIT - len() chi ra so
        # dong cua 1 trang, FE se tinh sai so trang.
        #
        # DUNG CHUNG _filter_conditions() voi list_phieu() - 1 diem sua duy nhat
        # nen total va data KHONG THE lech nhau khi them filter moi.
        stmt = (
            select(func.count())
            .select_from(CrPhieuModel)
            .where(*self._filter_conditions(
                session_id, trang_thai, q, tu_ngay, den_ngay, nguon, ma_tinh, vendor, phuong_an
            ))
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def dong_excel(
        self,
        session_ids: list[int] | None = None,
        trang_thai: str | None = None,
        q: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
        nguon: str | None = None,
        ma_tinh: list[str] | None = None,
        vendor: list[str] | None = None,
        phuong_an: list[str] | None = None,
    ) -> list[dict]:
        # WHERE = CHINH _filter_conditions() cua list_phieu/count_phieu (SUA
        # 19/10/2026, truoc la SQL tho rieng) - cung bo loc thi danh sach va
        # Excel KHONG the ra so dong khac nhau.
        conditions = self._filter_conditions(
            None, trang_thai, q, tu_ngay, den_ngay, nguon, ma_tinh, vendor, phuong_an, session_ids
        )
        p = CrPhieuModel
        tc, tt = aliased(TramModel), aliased(TramModel)
        # Lan POST cuoi - created_at chi la luc TAO dong (PENDING), khong phai
        # luc gui.
        lt = (
            select(CrPhieuLanThuModel.cr_phieu_id, func.max(CrPhieuLanThuModel.thoi_diem).label("gui_lan_cuoi"))
            .group_by(CrPhieuLanThuModel.cr_phieu_id)
            .subquery()
        )
        pl, rb = p.request_payload, p.response_body
        stmt = (
            select(
                p.id, p.phieu_id, p.cell_name, p.cr_session_id, p.created_at, p.so_lan_thu,
                p.trang_thai, p.nguon_khong_dat, p.error_message,
                CrAffectedCellsModel.tram_id.label("tram_cell_id"),
                tc.tram_name.label("tram_cell_name"), tc.ma_tinh,
                # Khong ghep duoc tram -> UNKNOWN giong dashboard (khong de trong).
                func.coalesce(_vendor_chuan(tc.ten_thiet_bi), "UNKNOWN").label("vendor"),
                CrSessionModel.tram_id.label("tram_tat_id"), tt.tram_name.label("tram_tat_name"),
                lt.c.gui_lan_cuoi,
                _phuong_an().label("phuong_an"),
                pl["Qos"].astext.label("qos_gui"),
                pl["Qoe"].astext.label("qoe_gui"),
                pl["SoChiTieuVP"].astext.label("so_chi_tieu_vp"),
                pl["NoiDung"].astext.label("noi_dung"),
                rb["status_code"].astext.label("http_status"),
                rb["code"].astext.label("ma_loi_cts"),
            )
            .select_from(p)
            .outerjoin(
                CrAffectedCellsModel,
                and_(CrAffectedCellsModel.cr_session_id == p.cr_session_id,
                     CrAffectedCellsModel.cell_name == p.cell_name),
            )
            .outerjoin(tc, tc.tram_id == CrAffectedCellsModel.tram_id)
            .outerjoin(CrSessionModel, CrSessionModel.id == p.cr_session_id)
            .outerjoin(tt, tt.tram_id == CrSessionModel.tram_id)
            .outerjoin(lt, lt.c.cr_phieu_id == p.id)
            .where(*conditions)
            .order_by(p.created_at.desc(), p.id.desc())
        )
        result = await self._session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]
