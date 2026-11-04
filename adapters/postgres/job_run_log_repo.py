"""
JobRunLogRepo — implement IJobRunLogRepo.
Tu: yeu cau truc tiep user (JOB TU DONG buoc 1/4) - lich su moi lan job chay.

Cau truc bam theo adapters/postgres/cr_phieu_repo.py (bang audit + list co
filter/phan trang/sort) - KHONG tu nghi cach lam moi.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.ports.outbound.repo_ports import IJobRunLogRepo
from models.job_run_log import JobRunLog as JobRunLogModel

# Whitelist sort - KHOP CHINH XAC voi Literal se dat o router (buoc 4). Router
# chua ton tai nhung adapter van tu whitelist ngay tu bay gio: repo khong duoc
# tin tuyet doi caller da validate (co the bi goi tu script/use case buoc 3) -
# cung nguyen tac _PHIEU_SORT_WHITELIST/_SESSION_SORT_WHITELIST da dung.
_JOB_RUN_SORT_WHITELIST = {"id", "job_type", "started_at", "finished_at", "trang_thai"}


def _to_dict(row: JobRunLogModel) -> dict:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "trang_thai": row.trang_thai,
        "so_session_quet": row.so_session_quet,
        "so_phieu_thanh_cong": row.so_phieu_thanh_cong,
        "so_phieu_that_bai": row.so_phieu_that_bai,
        "so_cell_vuot_gioi_han": row.so_cell_vuot_gioi_han,
        "error_message": row.error_message,
        "chi_tiet": row.chi_tiet,
    }


# V3a (12/08) - 10/11 cot cua bang, CO Y thieu chi_tiet. Liet ke cot
# tuong minh thay vi select(JobRunLogModel) roi xoa key: SELECT chi 10 cot thi
# JSONB chi_tiet KHONG bao gio duoc doc len tu Postgres, con cach kia van keo ca
# vai tram KB qua day roi moi vut di.
_COT_DANH_SACH = (
    JobRunLogModel.id,
    JobRunLogModel.job_type,
    JobRunLogModel.started_at,
    JobRunLogModel.finished_at,
    JobRunLogModel.trang_thai,
    JobRunLogModel.so_session_quet,
    JobRunLogModel.so_phieu_thanh_cong,
    JobRunLogModel.so_phieu_that_bai,
    JobRunLogModel.so_cell_vuot_gioi_han,
    JobRunLogModel.error_message,
)


class JobRunLogRepo(IJobRunLogRepo):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def insert(self, log: dict) -> dict:
        # C1.4-fix9 pattern - started_at set qua Python datetime.now(timezone.utc),
        # KHONG server_default=now() (xem models/job_run_log.py). Adapter tu set
        # (khong nhan tu caller) de moi noi goi khong tu tinh gio moi kieu.
        row = JobRunLogModel(
            job_type=log["job_type"],
            trang_thai=log["trang_thai"],
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_dict(row)

    async def update_result(
        self,
        id: int,
        trang_thai: str,
        finished_at: datetime,
        so_session_quet: int = 0,
        so_phieu_thanh_cong: int = 0,
        so_phieu_that_bai: int = 0,
        so_cell_vuot_gioi_han: int = 0,
        error_message: str | None = None,
        chi_tiet: dict | None = None,
    ) -> None:
        row = await self._session.get(JobRunLogModel, id)
        if row is None:
            # Im lang bo qua giong CrPhieuRepo.update_result() - dong nay chi la
            # ban ghi phu tro, khong duoc lam job that crash chi vi id sai.
            return
        row.trang_thai = trang_thai
        row.finished_at = finished_at
        row.so_session_quet = so_session_quet
        row.so_phieu_thanh_cong = so_phieu_thanh_cong
        row.so_phieu_that_bai = so_phieu_that_bai
        row.so_cell_vuot_gioi_han = so_cell_vuot_gioi_han
        row.error_message = error_message
        row.chi_tiet = chi_tiet
        await self._session.commit()

    def _filter_conditions(
        self,
        job_type: str | None,
        trang_thai: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
    ) -> list:
        # Tach rieng de list_job_runs()/count_job_runs() dung CHUNG dieu kien -
        # neu viet 2 lan se co ngay total lech voi data khi sua 1 ben quen ben kia.
        conditions = []
        if job_type is not None:
            conditions.append(JobRunLogModel.job_type == job_type)
        if trang_thai is not None:
            conditions.append(JobRunLogModel.trang_thai == trang_thai)
        # Nua khoang [tu_ngay, den_ngay) - xem IJobRunLogRepo.list_job_runs().
        # Loc theo started_at (KHONG phai finished_at): dong RUNNING chua co
        # finished_at, loc theo cot do se lam luot dang chay bien mat khoi man
        # hinh - dung luc nguoi van hanh can thay no nhat.
        if tu_ngay is not None:
            conditions.append(JobRunLogModel.started_at >= tu_ngay)
        if den_ngay is not None:
            conditions.append(JobRunLogModel.started_at < den_ngay)
        return conditions

    async def list_job_runs(
        self,
        job_type: str | None,
        page: int,
        size: int,
        sort_by: str | None = None,
        order: str = "desc",
        trang_thai: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
    ) -> list[dict]:
        # sort_by=None hoac ngoai whitelist -> started_at DESC: luot moi nhat
        # truoc, dung dung index idx_job_run_log_started (DESC) da tao o migration.
        if sort_by is not None and sort_by in _JOB_RUN_SORT_WHITELIST:
            # getattr() tren model column, KHONG noi chuoi SQL - an toan vi
            # sort_by da qua whitelist ngay tren.
            sort_column = getattr(JobRunLogModel, sort_by)
            order_clause = sort_column.asc() if order == "asc" else sort_column.desc()
        else:
            order_clause = JobRunLogModel.started_at.desc()

        # ORDER BY dat TRUOC offset/limit trong CUNG 1 cau SQL - Postgres sort
        # toan bo tap khop filter roi moi cat trang (khong phai sort trong trang).
        offset = (page - 1) * size
        stmt = (
            select(*_COT_DANH_SACH)
            .where(*self._filter_conditions(job_type, trang_thai, tu_ngay, den_ngay))
            .order_by(order_clause)
            .offset(offset)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        # .mappings() vi day la SELECT theo cot roi (khong con ORM entity) - moi
        # dong da la mapping ten_cot -> gia tri, dict() la du.
        return [dict(row) for row in result.mappings().all()]

    async def count_job_runs(
        self,
        job_type: str | None,
        trang_thai: str | None = None,
        tu_ngay: datetime | None = None,
        den_ngay: datetime | None = None,
    ) -> int:
        # COUNT rieng, KHONG dung len(items) sau khi da LIMIT - len() chi ra so
        # dong cua 1 trang, FE se tinh sai so trang.
        stmt = (
            select(func.count())
            .select_from(JobRunLogModel)
            .where(*self._filter_conditions(job_type, trang_thai, tu_ngay, den_ngay))
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def get_by_id(self, id: int) -> dict | None:
        # session.get() dung primary key - KHONG viet select().where(id==) tay,
        # va _to_dict() (ban DAY DU, co chi_tiet) dung lai nguyen ven o day.
        row = await self._session.get(JobRunLogModel, id)
        return None if row is None else _to_dict(row)
