"""
FastAPI app entry point.
Tu: ARCHITECTURE.md Section 8; TASK_LIST.md B1.5, B8.1

B1.5 skeleton - CHUA include router that (Part C1, router chua code). CORS dung
wildcard tam (OQ-15).

B8.1 (12072026, xac nhan voi user): noi lifespan that - DB engine/logger/
event_bus. KI-05 (B1.5) da xu ly xong phan lifespan.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.middleware.error_handler import register_exception_handlers
from api.routers import cr, dashboard, hau_kiem, jobs, phieu, qoe, qos, sessions, sse, stations, version
from adapters.netact.oss_router_env import kiem_tra_khi_khoi_dong
from infrastructure.db import engine
from infrastructure.event_bus import event_bus
from infrastructure.logger import setup_logger
from infrastructure.scheduler import dung_scheduler, khoi_tao_scheduler

setup_logger()  # KI-05 - setup 1 lan luc import module, truoc khi app nhan request nao
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # engine (infrastructure/db.py) la singleton tao san luc import - KHONG tao
    # engine moi o day, chi tham chieu lai + dispose dung luc shutdown.
    app.state.event_bus = event_bus  # cho router (C1.x) truy cap qua request.app.state
    # JOB TU DONG buoc 3/4 - dat trong lifespan (KHONG dung @app.on_event
    #("startup") da deprecated): app nay da dung lifespan cho DB engine tu
    # B8.1, them 1 co che khoi dong thu hai se kho theo doi thu tu chay.
    # SCHEDULER_ENABLED=false -> khoi_tao_scheduler() tra None, khong dang ky gi.
    khoi_tao_scheduler()
    # 23/10/2026: kiem cau hinh NetAct NGAY luc khoi dong (log tung NA, khong
    # log mat khau). Hong toan bo (file khong ton tai / JSON sai) -> raise,
    # app khong len: thay loi o `systemctl status` thay vi giua 1 CR that.
    kiem_tra_khi_khoi_dong()
    logger.info("App startup: DB engine + logger + event_bus da san sang")
    yield
    # Dung scheduler TRUOC khi dispose engine - job dang chay con can DB.
    dung_scheduler()
    await engine.dispose()
    logger.info("App shutdown: DB engine da dispose")


app = FastAPI(
    title="UC01 R012-NQMProactiveCC",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: thay bang FE origin that khi co (chua co bien .env tuong ung)
    allow_methods=["*"],
    allow_headers=["*"],
    # FE khac origin goi thang .196:8080, trinh duyet chi cho JS doc 6 header
    # an toan -> thieu dong nay FE khong doc duoc ten file (Content-Disposition).
    expose_headers=["Content-Disposition"],
)

# BUOC 4c (10/10/2026, yeu cau truc tiep user) - GET /stations/map?ma_tinh=HNI
# tra ~6.200 tram (toan bo tinh HNI), JSON co the vuot 500 KB. GZipMiddleware
# cua Starlette KHONG the gioi han theo 1 ROUTE cu the (chi co minimum_size,
# ap dung TOAN APP) - nhung day la LUA CHON HOP LY: moi route KHAC trong app
# nay deu phan trang/tra it du lieu, KHONG co route nao khac co kha nang vuot
# nguong 500.000 byte nay tren thuc te, nen hieu ung "chi anh huong route
# nay" van dung tren thuc te du co che la global.
app.add_middleware(GZipMiddleware, minimum_size=500_000)

register_exception_handlers(app)  # C1.2 - format chuan {error_code, message, session_id}

# Moi router dung chung prefix /api/v1: khi can doi contract (v2) chi them nhom
# include moi voi prefix khac, FE dang goi v1 khong bi vo trong luc chuyen doi.

app.include_router(stations.router, prefix="/api/v1", tags=["stations"])
app.include_router(cr.router, prefix="/api/v1", tags=["cr"])
app.include_router(sse.router, prefix="/api/v1", tags=["sse"])
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(qos.router, prefix="/api/v1", tags=["qos"])
# QoE per-cell (16082026) - GET /qoe/{cell_name} + GET /sessions/{id}/qoe-cells.
# Router RIENG (khong gop vao sessions.py): 2 endpoint deu doc CEM, tach ra de
# thay ngay cai gi cham vao CEM khi doc log/openapi.
app.include_router(qoe.router, prefix="/api/v1", tags=["qoe"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(phieu.router, prefix="/api/v1", tags=["phieu"])  # KHOI 4a/5 - POST /phieu (xuat phieu SaveCellClm)
# GET /dashboard/tong-quan (18/10/2026) - so lieu tong hop, chi doc DB.
app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])
# GET /hau-kiem/excel (18/10/2026) - xuat bang hau kiem ra .xlsx.
app.include_router(hau_kiem.router, prefix="/api/v1", tags=["hau-kiem"])
# GET /version (14092026) - truy vet ban dang chay. Server .196 khong co .git
# nen day la CACH DUY NHAT hoi duoc "server dang chay commit nao".
# Dat CUOI cung va KHONG Depends() gi: endpoint chan doan phai tra loi duoc
# ngay ca khi DB sap - xem docstring api/routers/version.py.
app.include_router(version.router, prefix="/api/v1", tags=["version"])
# NOTE: jobs.py CHI co POST /jobs/evaluate-cr (C2.2) - sync-rims/sync-netact/
# sync-status CHUA code (application/sync_enodeb_use_case.py,
# sync_cell_params_use_case.py van la stub rong, C2.5/C2.6, ngoai pham vi hom nay)
