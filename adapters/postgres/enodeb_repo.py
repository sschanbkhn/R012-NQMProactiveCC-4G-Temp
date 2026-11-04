"""
EnodebRepo — implement IEnodebRepo (upsert_many/find/get_ma_tinh/find_stations/count_stations).
Tu: ARCHITECTURE.md Section 5.3; TASK_LIST.md B5.1; find_stations/count_stations them o C1.3
(13072026) cho GET /stations - xem chu y tai dinh nghia trong domain/ports/outbound/repo_ports.py
"""

import re
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.tram import Tram
from domain.errors import TramNotFoundError
from domain.ports.outbound.repo_ports import IEnodebRepo
from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh, ma_tinh_theo_khu_vuc
from domain.value_objects.vendor import chuan_hoa_vendor
from models.cr_session import CrSession as CrSessionModel
from models.tram import Tram as TramModel

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Whitelist ten cot duoc phep sort cho GET /stations (22072026, xac nhan voi
# user) - BAT BUOC (cung ly do _SESSION_SORT_WHITELIST trong cr_session_repo.py
# - tranh SQL injection neu sort_by bi noi thang vao chuoi SQL, va tranh sort
# vao cot khong ton tai gay loi ngam). Ca 3 ten deu la cot that tren TramModel
# (models/tram.py) - da kiem tra truoc khi liet ke.
_STATION_SORT_WHITELIST = {"tram_id", "tram_name", "ma_tinh"}


def _clean(s: str | None) -> str | None:
    # API_CONTRACTS.md SS4 "Data Anomaly" dong 305-307 — regex dung y nguyen tu doc
    return _CONTROL_CHARS.sub("", s) if s else s


def _sanitize_coord(v: float | None) -> float | None:
    # DB_SCHEMA.md SS1 Notes dong 60 + API_CONTRACTS.md SS4 dong 302 — 0 la gia tri
    # loi tu API (khong phai toa do that), luu NULL thay vi 0
    return None if v == 0 else v


class EnodebRepo(IEnodebRepo):
    # B2.7: upsert_many nhan raw list[dict] tu INetworkGateway.get_enodeb_list()
    # (API_CONTRACTS.md SS4 dong 285-291: enodeb_id/ten_he_thong/ma_tinh/longitude/
    # latitude/ma_csht/ten_thiet_bi) — repo tu map sang cot DB (tram_id/tram_name/...)
    # vi Tram domain entity (B2.4, 5 field) khong co cho chua het field DB can.
    # ten_quan_ly KHONG co trong API nay (OQ-11 con block, RIMS API rieng chua co) —
    # khong dua vao set_ khi update de khong ghi de gia tri that (neu sau nay co
    # nguon khac dien vao) bang NULL.
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_many(self, records: list[dict]) -> int:
        if not records:
            return 0

        # C1.4-fix9 (21072026) - last_synced_at/updated_at gio la TIMESTAMPTZ
        # (models/tram.py), PHAI giu tzinfo (truoc day la TIMESTAMP thuong nen
        # phai .replace(tzinfo=None), gio nguoc lai - asyncpg can gia tri
        # tz-aware cho cot timestamptz).
        now = datetime.now(timezone.utc)
        values = []
        for r in records:
            values.append(
                {
                    # str() bat buoc - test that B6.4 phat hien enodeb_id tra ve
                    # tu RIMS API la int (VD 777, 888), khong phai string nhu vi
                    # du minh hoa trong API_CONTRACTS.md ("160000"). asyncpg tu
                    # choi bind int vao cot VARCHAR (DataError: expected str, got int).
                    "tram_id": str(r["enodeb_id"]),
                    "tram_name": r["ten_he_thong"],
                    "ma_tinh": r.get("ma_tinh") or None,
                    "ma_csht": r.get("ma_csht") or None,
                    "ten_thiet_bi": r.get("ten_thiet_bi") or None,
                    "longitude": _sanitize_coord(r.get("longitude")),
                    "latitude": _sanitize_coord(r.get("latitude")),
                    "last_synced_at": now,
                    "updated_at": now,
                }
            )

        stmt = insert(TramModel).values(values)
        stmt = stmt.on_conflict_do_update(
            # DB_SCHEMA.md SS1 Notes dong 63 — "Upsert on conflict tram_id -> update
            # (khong xoa record cu)"; tram_id co UNIQUE constraint that (models/tram.py)
            index_elements=["tram_id"],
            set_={
                "tram_name": stmt.excluded.tram_name,
                "ma_tinh": stmt.excluded.ma_tinh,
                "ma_csht": stmt.excluded.ma_csht,
                "ten_thiet_bi": stmt.excluded.ten_thiet_bi,
                "longitude": stmt.excluded.longitude,
                "latitude": stmt.excluded.latitude,
                "last_synced_at": stmt.excluded.last_synced_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return len(values)

    async def find(self, q: str) -> list[Tram]:
        # API_CONTRACTS.md SS "GET /stations" dong 559 — tim theo tram_id/tram_name/
        # ten_quan_ly/ma_csht
        pattern = f"%{q}%"
        stmt = select(TramModel).where(
            TramModel.tram_id.ilike(pattern)
            | TramModel.tram_name.ilike(pattern)
            | TramModel.ten_quan_ly.ilike(pattern)
            | TramModel.ma_csht.ilike(pattern)
        )
        result = await self._session.execute(stmt)
        return [
            Tram(
                tram_id=row.tram_id,
                tram_name=row.tram_name,
                longitude=row.longitude,
                latitude=row.latitude,
                trang_thai=row.trang_thai,
            )
            for row in result.scalars().all()
        ]

    async def get_by_tram_ids(self, tram_ids: list[str]) -> list[Tram]:
        # API preview (21072026) - EXACT match nhieu tram_id trong 1 query
        # (IN clause), KHAC find() (ILIKE, 1 tu khoa tim kiem UI) - xem chu y
        # day du trong domain/ports/outbound/repo_ports.py::IEnodebRepo.
        if not tram_ids:
            return []
        stmt = select(TramModel).where(TramModel.tram_id.in_(tram_ids))
        result = await self._session.execute(stmt)
        return [
            Tram(
                tram_id=row.tram_id,
                tram_name=row.tram_name,
                longitude=row.longitude,
                latitude=row.latitude,
                trang_thai=row.trang_thai,
            )
            for row in result.scalars().all()
        ]

    async def get_ma_tinh(self, tram_id: str) -> str:
        # Bo sung o C2.1 (12072026, xac nhan voi user) - query THANG cot ma_tinh
        # tu models/tram.py (DB layer), KHONG qua domain Tram entity (B2.4 co
        # chu y khong chua ma_tinh - infrastructure concern cho viec chon NetAct
        # server, khong phai business concept).
        stmt = select(TramModel.ma_tinh).where(TramModel.tram_id == tram_id)
        result = await self._session.execute(stmt)
        ma_tinh = result.scalar_one_or_none()
        if ma_tinh is None:
            raise TramNotFoundError(f"Khong tim thay ma_tinh cho tram_id={tram_id}", tram_id=tram_id)
        return ma_tinh

    def _station_filters(
        self,
        q: str | None,
        status: str | None,
        vendor: list[str] | None = None,
        khu_vuc: list[str] | None = None,
    ) -> list:
        # Dung chung boi find_stations()/count_stations() (C1.3, 13072026) - GIU
        # NGUYEN dieu kien tim kiem cua find() (dong 96-99: tram_id/tram_name/
        # ten_quan_ly/ma_csht ILIKE), them status filter tren trang_thai.
        conditions = []
        if q:
            pattern = f"%{q}%"
            conditions.append(
                or_(
                    TramModel.tram_id.ilike(pattern),
                    TramModel.tram_name.ilike(pattern),
                    TramModel.ten_quan_ly.ilike(pattern),
                    TramModel.ma_csht.ilike(pattern),
                )
            )
        if status:
            conditions.append(TramModel.trang_thai == status)
        # vendor (THEM 04/10/2026) - loc O TANG DB (khong qua chuan_hoa_vendor()
        # Python) vi muc dich khac nhau: chuan_hoa_vendor() danh cho HIEN THI
        # (luon tra 1 Vendor, ke ca UNKNOWN, cho MOI dong), con loc nay can
        # SQL WHERE de khong phai doc tron bang roi loc o Python (58k+ dong).
        # UPPER(TRIM(...)) GIONG HET cach chuan_hoa_vendor() xu ly chuoi truoc
        # khi so khop - dam bao 2 duong (loc va hien thi) dong nhat ket qua
        # ("NOKIA" that va " nokia " deu duoc loc ra cung 1 nhom). Router da
        # Literal-whitelist vendor (chi NOKIA/ERICSSON/HUAWEI/ZTE, UNKNOWN
        # KHONG trong whitelist - khong co y nghia "loc theo UNKNOWN" ro rang,
        # xem api/routers/stations.py), nen o day KHONG can validate lai.
        if vendor:
            conditions.append(func.upper(func.trim(TramModel.ten_thiet_bi)).in_(vendor))
        # khu_vuc (THEM 04/10/2026) - loc O TANG DB qua ma_tinh IN (...), KHONG
        # phai cot rieng (RIMS khong co khai niem khu vuc). ma_tinh_theo_khu_vuc()
        # tra DANH SACH ma (CA cu lan moi) thuoc cac KV duoc chon - tranh phai
        # keo tron bang roi loc o Python (58k+ dong, giong ly do vendor o tren).
        if khu_vuc:
            conditions.append(TramModel.ma_tinh.in_(ma_tinh_theo_khu_vuc(khu_vuc)))
        return conditions

    async def find_stations(
        self,
        q: str | None,
        status: str | None,
        offset: int,
        limit: int,
        sort_by: str | None = None,
        order: str = "desc",
        vendor: list[str] | None = None,
        khu_vuc: list[str] | None = None,
    ) -> list[dict]:
        # DISTINCT ON (Postgres-only, chap nhan duoc vi DB_SCHEMA.md dong 3 xac
        # dinh PostgreSQL) lay dung 1 dong cr_session MOI NHAT/tram_id (id lon
        # nhat - SERIAL PK tang dan, khong co created_at tren domain CrSession
        # luc code file nay nen dung id lam proxy "moi nhat", cung logic da dung
        # trong TriggerCrUseCase step 1 truoc do). ORDER BY phai bat dau bang
        # cot DISTINCT ON (tram_id) - yeu cau cua Postgres. LUU Y: day la
        # subquery NOI BO de lay "cr_session moi nhat/tram", KHONG phai sort
        # cua danh sach station tra ve - sort_by/order KHONG duoc dung o day.
        latest_cr = (
            select(CrSessionModel.tram_id, CrSessionModel.id, CrSessionModel.status)
            .distinct(CrSessionModel.tram_id)
            .order_by(CrSessionModel.tram_id, CrSessionModel.id.desc())
            .subquery()
        )
        # sort_by/order (22072026) - GIONG CrSessionRepo.list(), xem chu y day
        # du _SESSION_SORT_WHITELIST. sort_by=None hoac ngoai whitelist (khong
        # nen xay ra - router da Literal-validate) -> GIU NGUYEN thu tu mac
        # dinh cu TramModel.tram_id TANG DAN (chu y: KHONG phai .desc(), day
        # la hanh vi cu truoc khi co task nay, phai giu nguyen tranh regression).
        if sort_by is not None and sort_by in _STATION_SORT_WHITELIST:
            sort_column = getattr(TramModel, sort_by)  # an toan vi da qua whitelist
            order_clause = sort_column.desc() if order == "desc" else sort_column.asc()
        else:
            order_clause = TramModel.tram_id
        stmt = (
            select(
                TramModel,
                latest_cr.c.id.label("cr_session_id"),
                latest_cr.c.status.label("cr_status"),
            )
            .outerjoin(latest_cr, TramModel.tram_id == latest_cr.c.tram_id)
            .where(*self._station_filters(q, status, vendor, khu_vuc))
            .order_by(order_clause)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "tram_id": row.Tram.tram_id,
                "tram_name": row.Tram.tram_name,
                "ten_quan_ly": row.Tram.ten_quan_ly,
                "ma_csht": row.Tram.ma_csht,
                "longitude": row.Tram.longitude,
                "latitude": row.Tram.latitude,
                "trang_thai": row.Tram.trang_thai,
                "cr_status": row.cr_status,
                "cr_session_id": row.cr_session_id,
                # 2 truong THEM 15092026 (V2 buoc 3). KHONG phai sua cau SELECT:
                # stmt da select(TramModel) NGUYEN VEN o tren nen row.Tram co
                # san moi cot cua bang - chi boc them ra dict.
                #
                # ma_tinh: doc THANG cot, KHONG suy tu hau to ten tram (hau to
                # la ma TRUOC sap nhap, lech 37,8% so voi ma_tinh - xem chu y
                # day du o api/schemas/station_schemas.py).
                "ma_tinh": row.Tram.ma_tinh,
                # vendor: DA CHUAN HOA qua domain, KHONG tra ten_thiet_bi tho.
                # VI SAO khong tra tho: cot la VARCHAR(200) tu do khong rang
                # buoc - hom nay sach (dung 4 gia tri, da do 58.230 dong) nhung
                # lan sync RIMS toi co the ve " Nokia" hay mot vendor thu 5.
                # Tra tho thi moi noi tieu thu (FE, script, bao cao) phai tu
                # chuan hoa lai - tuc n ban sao cua cung mot luat, dung cai benh
                # ma GET /sessions/{id}/qos-cells da phai sinh ra de chua.
                # chuan_hoa_vendor() KHONG BAO GIO nem loi va tra UNKNOWN cho
                # gia tri la (khong nuot, khong doan) - an toan cho duong DOC
                # nay vi no chay 1 lan cho MOI dong tra ve.
                # .value: lay chuoi thuan cho DTO tang api/ (StationItem.vendor
                # khai str | None, khong phu thuoc kieu domain).
                "vendor": chuan_hoa_vendor(row.Tram.ten_thiet_bi).value,
                # khu_vuc: suy tu ma_tinh (KHONG phai cot rieng) - xem chu y
                # day du o domain/value_objects/khu_vuc.py. Tra None neu
                # ma_tinh rong/la (KHONG doan, giong vendor UNKNOWN o tren).
                "khu_vuc": khu_vuc_tu_ma_tinh(row.Tram.ma_tinh),
            }
            for row in result
        ]

    async def count_stations(
        self,
        q: str | None,
        status: str | None,
        vendor: list[str] | None = None,
        khu_vuc: list[str] | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(TramModel)
            .where(*self._station_filters(q, status, vendor, khu_vuc))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_by_tram_id(self, tram_id: str) -> dict | None:
        # KHOI 3a/5 (XuatPhieuUseCase) - xem chu y day du trong
        # domain/ports/outbound/repo_ports.py::IEnodebRepo.
        stmt = select(TramModel).where(TramModel.tram_id == tram_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "tram_name": row.tram_name,
            "ma_tinh": row.ma_tinh,
            "ma_csht": row.ma_csht,
            "ten_thiet_bi": row.ten_thiet_bi,
            "ten_quan_ly": row.ten_quan_ly,
        }

    async def get_all_with_coords(self) -> list[dict]:
        # BUOC 4b (08/10/2026) - xem chu y day du trong
        # domain/ports/outbound/repo_ports.py::IEnodebRepo. Loc o DB (WHERE
        # NOT NULL) thay vi tai het roi loc o Python - re hon cho bang 60k+
        # dong khi phan lon deu co toa do.
        # ma_tinh THEM BUOC 4c (10/10/2026) - can de loc theo tinh (GET
        # /stations/map?ma_tinh=...) ma KHONG phai truy van rieng lan 2; them
        # field la ADDITIVE (khong doi field cu), caller HO (BUOC 4b, trigger_
        # cr_use_case.py) khong doc field nay nen khong anh huong.
        stmt = select(
            TramModel.tram_id, TramModel.tram_name, TramModel.longitude,
            TramModel.latitude, TramModel.ten_thiet_bi, TramModel.ma_tinh,
        ).where(TramModel.longitude.is_not(None), TramModel.latitude.is_not(None))
        result = await self._session.execute(stmt)
        return [
            {
                "tram_id": row.tram_id,
                "tram_name": row.tram_name,
                "longitude": float(row.longitude),
                "latitude": float(row.latitude),
                "ten_thiet_bi": row.ten_thiet_bi,
                "ma_tinh": row.ma_tinh,
            }
            for row in result.all()
        ]
