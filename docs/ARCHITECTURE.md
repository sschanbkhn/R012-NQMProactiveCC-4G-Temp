# ARCHITECTURE.md — Hexagonal Architecture UC01

> Pattern: Hexagonal Architecture (Ports & Adapters)
> Nguyên tắc cốt lõi: Domain layer hoàn toàn độc lập với framework, DB, HTTP.
> Mọi phụ thuộc ngoài đều đi qua Port interface.

---

## 1. TẠI SAO HEXAGONAL

```
Vấn đề với Layered Architecture thông thường:
  Controller → Service → Repository → DB
  → Service biết về DB (import SQLModel)
  → Không thể test domain logic mà không có DB
  → Thay DB hoặc HTTP client → phải sửa nhiều chỗ

Hexagonal giải quyết:
  Domain (business logic) ở trung tâm
  Mọi thứ bên ngoài (DB, HTTP, SSH) đều là Adapter
  Domain chỉ biết về Port (interface) — không biết Adapter cụ thể
  → Test domain logic không cần DB, không cần HTTP
  → Thay adapter (VD: mock SOC → real SOC) không ảnh hưởng domain
```

---

## 2. SƠ ĐỒ TỔNG QUAN

```
          ┌─────────────────────────────────────────────────────┐
          │                   INBOUND                           │
          │   HTTP Request    SSE Stream    n8n Webhook         │
          │        │               │             │              │
          │   ┌────▼───────────────▼─────────────▼────┐        │
          │   │           API LAYER (FastAPI)          │        │
          │   │   routers/ schemas/ middleware/        │        │
          │   └────────────────┬───────────────────────┘        │
          └────────────────────│────────────────────────────────┘
                               │ calls Inbound Port
          ┌────────────────────▼────────────────────────────────┐
          │              APPLICATION LAYER                      │
          │   TriggerCrUseCase    EvaluateCrUseCase            │
          │   SyncEnodebUseCase   GetSessionsUseCase           │
          │           │                                         │
          │           │ calls Domain Services                   │
          │   ┌────────▼────────────────────────────┐          │
          │   │          DOMAIN LAYER               │          │
          │   │  entities/   value_objects/          │          │
          │   │  services/   errors.py               │          │
          │   │  ports/ (interfaces only)            │          │
          │   └────────────────────────────────────┘          │
          └──────────────────────────────────────────────────────┘
                               │ calls Outbound Port
          ┌────────────────────▼────────────────────────────────┐
          │                  OUTBOUND                           │
          │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
          │  │CDS HTTP  │ │NetAct SSH│ │  PostgreSQL Repo  │   │
          │  │Adapter   │ │Adapter   │ │  Adapters         │   │
          │  └──────────┘ └──────────┘ └──────────────────┘   │
          │       │              │               │              │
          │   CĐS/CTS API   NetAct SSH      PostgreSQL         │
          └─────────────────────────────────────────────────────┘
```

---

## 3. DOMAIN LAYER — TRUNG TÂM

### 3.1 Entities
```python
# domain/entities/cell.py
# Từ: BUSINESS_RULES.md — Section 2, 4
class Cell:
    cell_id:    str | None    # null từ CĐS → skip
    cell_name:  str
    dist_name:  str           # PLMN-PLMN/MRBTS-x/LNBTS-x/LNCEL-y
    priority:   int           # 1|2|3|4
    huong_id:   str | None    # XY format
    action_type: str          # rsboost|qrxlevmin|skip
    status:     str           # active|inactive

# domain/entities/tram.py
class Tram:
    tram_id:    str
    tram_name:  str
    longitude:  float | None
    latitude:   float | None
    trang_thai: str

# domain/entities/cr_session.py
class CrSession:
    id:         int
    tram_id:    str
    action:     str           # shutdown|cancel|relocate
    status:     CrStatus      # enum
    plan_name:  str | None
```

### 3.2 Value Objects
```python
# domain/value_objects/rsboost_level.py
# Từ: BUSINESS_RULES.md — Section 5
RSBOOST_SCALE = [-3.0, 0.0, 3.0, 6.0]  # 4 bậc, bước +3dB

class RsboostLevel:
    value: float              # phải nằm trong RSBOOST_SCALE

    def next_level(self) -> "RsboostLevel":
        # Cộng cố định +3dB, cap tại 6.0
        # Từ: BUSINESS_RULES.md Section 5.2
        new_val = self.value + 3.0
        if new_val > 6.0:
            # đang ở cap — không thay đổi
            return self
        return RsboostLevel(value=new_val)


        # tăng 1 bậc, nếu đang ở cap → trả về self
        ...

    def to_xml_value(self) -> str:
        # f"{self.value:g}dB" → "3dB", "-3dB", "0dB"
        ...

    @classmethod
    def from_raw(cls, raw: float) -> "RsboostLevel":
        # parse giá trị từ NetAct, làm tròn về bậc gần nhất
        ...

# domain/value_objects/qrxlevmin.py
# Từ: BUSINESS_RULES.md — Section 6
QRXLEVMIN_FLOOR = -144

class Qrxlevmin:
    value: int                # dBm integer

    def decrease(self) -> "Qrxlevmin":
        # giảm 4 dBm, không xuống dưới -144
        ...

    def to_xml_value(self) -> str:
        return str(self.value)  # "-128", "-132"
```

### 3.3 Domain Services
```
band_priority_filter.py    → nhóm huong theo Y, chọn band ưu tiên cao nhất
neighbor_cell_service.py   → filter null/VNP-/duplicate, trả Cell list sạch
rsboost_calculator.py      → nhận Cell list → tính rsboost_new cho priority 1-2
qrxlevmin_calculator.py    → nhận Cell list → tính qrxlevmin_new cho priority 3-4
priority_assigner.py       → assign action_type cho từng cell
evaluation_service.py      → so sánh before/after, trả PASS|FAIL|INSUFFICIENT_DATA
```

### 3.4 Ports — Interfaces
```python
# domain/ports/inbound/ — Use Case interfaces
class ITriggerCrUseCase(ABC):
    async def execute(self, tram_id: str, tram_name: str, action: str) -> CrSession: ...

class IGetSessionsUseCase(ABC):
    async def execute(self, filters: SessionFilter) -> Page[CrSession]: ...

class IGetSessionDetailUseCase(ABC):
    async def execute(self, session_id: int) -> CrSessionDetail: ...

class IEvaluateCrUseCase(ABC):
    async def execute(self, session_id: int) -> EvaluationResult: ...

class ISyncEnodebUseCase(ABC):
    async def execute(self) -> SyncResult: ...

# domain/ports/outbound/ — Gateway interfaces
class INetworkGateway(ABC):
    async def get_cell_neighbors(self, tram_id: str, tram_name: str) -> list[dict]: ...
    async def get_qos_metrics(self, cell_names: list[str], from_dt: datetime, to_dt: datetime) -> list[dict]: ...
    async def get_enodeb_list(self, page: int, size: int) -> list[dict]: ...

class ISocGateway(ABC):
    async def get_qoe(self, cell_names: list[str], from_dt: datetime, to_dt: datetime) -> list[dict]: ...

class INetActGateway(ABC):
    async def submit_cr(self, xml_content: str, plan_name: str, backup_name: str) -> bool: ...

class ICrSessionRepo(ABC):
    async def create(self, session: CrSession) -> CrSession: ...
    async def update(self, session: CrSession) -> CrSession: ...
    async def get_by_id(self, id: int) -> CrSession | None: ...
    async def get_by_tram_id(self, tram_id: str) -> list[CrSession]: ...
    async def list(self, filters: SessionFilter) -> Page[CrSession]: ...

class ICellParamsRepo(ABC):
    async def upsert(self, params: list[CellParam]) -> None: ...
    async def get_by_tram_id(self, tram_id: str) -> list[CellParam]: ...
    async def snapshot_before_cr(self, session_id: int) -> None: ...

class IEnodebRepo(ABC):
    async def upsert_many(self, records: list[dict]) -> int: ...
    async def find(self, q: str) -> list[Tram]: ...
```

---

## 4. APPLICATION LAYER — USE CASES

### 4.1 TriggerCrUseCase — Flow chính
```python
# application/trigger_cr_use_case.py
# Từ: BUSINESS_RULES.md Section 1, WORKFLOW.md 18 bước

class TriggerCrUseCase(ITriggerCrUseCase):
    def __init__(
        self,
        network_gw: INetworkGateway,   # inject qua DI
        netact_gw:  INetActGateway,
        session_repo: ICrSessionRepo,
        cell_repo:  ICellParamsRepo,
        event_bus:  CrEventBus,        # SSE stream
        # domain services
        band_filter: BandPriorityFilter,
        neighbor_svc: NeighborCellService,
        priority_assigner: PriorityAssigner,
        rsboost_calc: RsboostCalculator,
        qrxlevmin_calc: QrxlevminCalculator,
        xml_builder: XmlBuilder,
        audit_svc: AuditService,
    ): ...

    async def execute(self, tram_id, tram_name, action) -> CrSession:
        # Step 1-18 — emit SSE event sau mỗi step
        # Xem WORKFLOW.md để biết chi tiết từng step
        ...
```

### 4.2 EvaluateCrUseCase
```python
# Từ: BUSINESS_RULES.md Section 8
# Gọi bởi: n8n POST /jobs/evaluate-cr (hàng ngày)

class EvaluateCrUseCase(IEvaluateCrUseCase):
    async def execute(self, session_id: int) -> EvaluationResult:
        # 1. Lấy session → kiểm tra đủ 21 ngày chưa
        # 2. Gọi SOC: get_qoe() → before + after data
        # 3. Gọi CTS: get_qos_metrics() → before + after data
        # 4. evaluation_service.evaluate() → PASS|FAIL|INSUFFICIENT_DATA
        # 5. Lưu qoe_snapshot, qos_snapshot vào DB
        # 6. Cập nhật cr_session.qoe_result, qos_result
        # 7. Nếu FAIL → tạo alert_log
        ...
```

---

## 5. ADAPTER LAYER

### 5.1 HTTP Adapters
```
adapters/http/
  sha512_auth.py          ← helper build 4 headers (dùng chung CĐS + CTS)
  cds_http_adapter.py     ← implement INetworkGateway.get_cell_neighbors()
  cts_http_adapter.py     ← implement INetworkGateway.get_qos_metrics()
  enodeb_http_adapter.py  ← implement INetworkGateway.get_enodeb_list()
  soc_http_adapter.py     ← implement ISocGateway.get_qoe() — MOCK hiện tại
```

### 5.2 NetAct Adapters
```
adapters/netact/
  xml_builder.py          ← build Nokia RAML 2.0 XML
  ssh_executor.py         ← Paramiko SSH: SFTP + Import + Provision
  netact_adapter.py       ← implement INetActGateway, orchestrate xml+ssh
```

### 5.3 PostgreSQL Adapters
```
adapters/postgres/
  cr_session_repo.py      ← implement ICrSessionRepo
  cell_params_repo.py     ← implement ICellParamsRepo
  enodeb_repo.py          ← implement IEnodebRepo
```

---

## 6. API LAYER

### 6.1 Routers
```
api/routers/
  stations.py   GET /stations
  cr.py         POST /cr/trigger
  sse.py        GET /cr/stream/{session_id}
  sessions.py   GET /sessions, GET /sessions/{id}
  qos.py        GET /qos/{cell_name}
  jobs.py       POST /jobs/sync-*, POST /jobs/evaluate-cr
```

### 6.2 SSE Implementation
```python
# api/routers/sse.py
from fastapi.responses import StreamingResponse
from infrastructure.event_bus import CrEventBus
import json, asyncio

@router.get("/cr/stream/{session_id}")
async def cr_stream(session_id: int, bus: CrEventBus = Depends()):
    async def event_generator():
        queue = await bus.subscribe(session_id)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done"):
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'status': 'timeout'})}\n\n"
        finally:
            await bus.unsubscribe(session_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 6.3 Middleware
```python
# api/middleware/error_handler.py
# Global exception handler → format chuẩn
{
  "error_code": "...",
  "message": "...",
  "session_id": null
}
```

---

## 7. INFRASTRUCTURE LAYER

### 7.1 DI Wiring (dependencies.py)
```python
# infrastructure/dependencies.py
# Wire Port interface → Adapter implementation

from fastapi import Depends
from adapters.http.cds_http_adapter import CdsHttpAdapter
from adapters.http.cts_http_adapter import CtsHttpAdapter
from adapters.http.enodeb_http_adapter import EnodebHttpAdapter
from adapters.http.soc_http_adapter import SocHttpAdapter
from adapters.netact.netact_adapter import NetActAdapter
from adapters.postgres.cr_session_repo import CrSessionRepo
from adapters.postgres.cell_params_repo import CellParamsRepo
from adapters.postgres.enodeb_repo import EnodebRepo
from domain.services.band_priority_filter import BandPriorityFilter
from domain.services.neighbor_cell_service import NeighborCellService
from domain.services.priority_assigner import PriorityAssigner
from domain.services.rsboost_calculator import RsboostCalculator
from domain.services.qrxlevmin_calculator import QrxlevminCalculator
from application.trigger_cr_use_case import TriggerCrUseCase

def get_trigger_cr_use_case(
    session: AsyncSession = Depends(get_session)
) -> TriggerCrUseCase:
    # Network gateway gộp CĐS + CTS + eNodeB
    network_gw = NetworkGateway(
        cds=CdsHttpAdapter(),
        cts=CtsHttpAdapter(),
        enodeb=EnodebHttpAdapter(),
    )
    return TriggerCrUseCase(
        network_gw=network_gw,
        netact_gw=NetActAdapter(),
        session_repo=CrSessionRepo(session),
        cell_repo=CellParamsRepo(session),
        event_bus=get_event_bus(),
        band_filter=BandPriorityFilter(),
        neighbor_svc=NeighborCellService(),
        priority_assigner=PriorityAssigner(),
        rsboost_calc=RsboostCalculator(),
        qrxlevmin_calc=QrxlevminCalculator(),
        xml_builder=XmlBuilder(),
        audit_svc=AuditService(session),
    )
```

### 7.2 CrEventBus (SSE)
```python
# infrastructure/event_bus.py
import asyncio
from collections import defaultdict

class CrEventBus:
    def __init__(self):
        self._queues: dict[int, list[asyncio.Queue]] = defaultdict(list)

    async def subscribe(self, session_id: int) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues[session_id].append(q)
        return q

    async def publish(self, session_id: int, event: dict):
        for q in self._queues.get(session_id, []):
            await q.put(event)

    async def unsubscribe(self, session_id: int, q: asyncio.Queue):
        self._queues[session_id].remove(q)

# Singleton — register trong main.py lifespan
event_bus = CrEventBus()
```

### 7.3 Logger
```python
# infrastructure/logger.py
import logging, sys

def setup_logger():
    fmt = "[%(levelname)s] %(asctime)s [%(name)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)]
    )

# Dùng trong mỗi module:
import logging
logger = logging.getLogger(__name__)

# Luôn kèm context:
logger.info("Step 3 done", extra={
    "session_id": session_id,
    "tram_id": tram_id,
    "cells_found": 9
})
```

---

## 8. MAIN.PY — ENTRY POINT

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.db import engine
from infrastructure.logger import setup_logger
from infrastructure.event_bus import event_bus
from api.routers import stations, cr, sse, sessions, qos, jobs
from sqlmodel import SQLModel

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logger()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    app.state.event_bus = event_bus
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title="UC01 R012-NQMProactiveCC",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://FE_SERVER_IP"],  # từ .env
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stations.router, prefix="/api/v1", tags=["stations"])
app.include_router(cr.router,       prefix="/api/v1", tags=["cr"])
app.include_router(sse.router,      prefix="/api/v1", tags=["sse"])
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(qos.router,      prefix="/api/v1", tags=["qos"])
app.include_router(jobs.router,     prefix="/api/v1", tags=["jobs"])
```

---

## 9. DEPENDENCY RULES — BẮT BUỘC

```
domain/        KHÔNG import: fastapi, sqlmodel, httpx, paramiko
               CHỈ import: Python stdlib + domain/ nội bộ

application/   CÓ THỂ import: domain/
               KHÔNG import: fastapi, sqlmodel, httpx, paramiko, adapters/

adapters/      CÓ THỂ import: domain/ports/, sqlmodel, httpx, paramiko
               KHÔNG import: application/, api/

api/           CÓ THỂ import: application/, infrastructure/
               KHÔNG import: adapters/ trực tiếp (qua DI)

infrastructure/ CÓ THỂ import: tất cả (đây là wiring layer)
```



```
Kiểm tra vi phạm:
  grep -r "import fastapi" domain/      → phải trống
  grep -r "import sqlmodel" domain/     → phải trống
  grep -r "import paramiko" domain/     → phải trống
  grep -r "import httpx" domain/        → phải trống

MAPPING RULE — models/ vs domain/entities/:
  models/          → SQLModel classes (biết về DB, có tablename, FK)
                     NẰM NGOÀI domain/ — domain không import models/

  domain/entities/ → Pure Python classes (không biết về DB)
                     Không có SQLModel, không có Column, không có tablename

  Adapter phụ trách mapping 2 chiều:
    DB → Domain:  Adapter đọc SQLModel record → tạo domain Entity
    Domain → DB:  Adapter nhận domain Entity → tạo SQLModel record → save

  Ví dụ trong CrSessionRepo:
    async def get_by_id(self, id: int) -> CrSession:       # trả Domain entity
        record = await self.session.get(CrSessionModel, id) # SQLModel model
        return CrSession(                                    # map sang domain
            id=record.id,
            tram_id=record.tram_id,
            status=CrStatus(record.status),
            ...
        )

  Quy tắc:
    → Use Case chỉ nhận/trả Domain entities
    → Adapter nhận Domain entity → convert → SQLModel → lưu DB
    → Adapter đọc SQLModel → convert → Domain entity → trả Use Case
    → KHÔNG bao giờ trả SQLModel object ra ngoài Adapter layer


```



---

## 10. TESTING STRATEGY

```
Unit Test (pytest) — không cần DB, không cần HTTP:
  tests/domain/test_rsboost_calculator.py
  tests/domain/test_qrxlevmin_calculator.py
  tests/domain/test_band_priority_filter.py
  tests/domain/test_neighbor_cell_service.py
  tests/domain/test_xml_builder.py

  → Mock tất cả Port interfaces
  → Chỉ test domain logic thuần

Integration Test — cần DB/HTTP thật:
  tests/integration/test_cds_adapter.py      (gọi CĐS API thật)
  tests/integration/test_cts_adapter.py      (gọi CTS API thật)
  tests/integration/test_cr_session_repo.py  (cần PostgreSQL)

E2E Test:
  tests/e2e/test_trigger_cr_flow.py          (full flow, sandbox NetAct)
```

---

## 11. FILE STRUCTURE — ĐẦY ĐỦ

```
R012-NQMProactiveCC/
├── docs/
├── .env + .env.example
├── requirements.txt
├── alembic.ini
├── alembic/versions/
├── main.py
│
├── domain/
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── cell.py
│   │   ├── tram.py
│   │   └── cr_session.py
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── rsboost_level.py
│   │   └── qrxlevmin.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── band_priority_filter.py
│   │   ├── neighbor_cell_service.py
│   │   ├── rsboost_calculator.py
│   │   ├── qrxlevmin_calculator.py
│   │   ├── priority_assigner.py
│   │   └── evaluation_service.py
│   ├── ports/
│   │   ├── inbound/
│   │   │   ├── __init__.py
│   │   │   └── use_case_ports.py
│   │   └── outbound/
│   │       ├── __init__.py
│   │       └── gateway_ports.py
│   └── errors.py
│
├── application/
│   ├── __init__.py
│   ├── trigger_cr_use_case.py
│   ├── evaluate_cr_use_case.py
│   ├── get_sessions_use_case.py
│   ├── get_session_detail_use_case.py
│   ├── sync_enodeb_use_case.py
│   ├── sync_cell_params_use_case.py
│   └── alert_use_case.py
│
├── adapters/
│   ├── http/
│   │   ├── __init__.py
│   │   ├── sha512_auth.py
│   │   ├── cds_http_adapter.py
│   │   ├── cts_http_adapter.py
│   │   ├── enodeb_http_adapter.py
│   │   └── soc_http_adapter.py
│   ├── netact/
│   │   ├── __init__.py
│   │   ├── xml_builder.py
│   │   ├── ssh_executor.py
│   │   └── netact_adapter.py
│   └── postgres/
│       ├── __init__.py
│       ├── cr_session_repo.py
│       ├── cell_params_repo.py
│       └── enodeb_repo.py
│
├── api/
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── stations.py
│   │   ├── cr.py
│   │   ├── sse.py
│   │   ├── sessions.py
│   │   ├── qos.py
│   │   └── jobs.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── cr_schemas.py
│   │   ├── session_schemas.py
│   │   └── station_schemas.py
│   └── middleware/
│       ├── __init__.py
│       └── error_handler.py
│
├── models/
│   ├── __init__.py
│   ├── tram.py
│   ├── cell_params.py
│   ├── cr_session.py
│   ├── cr_log.py
│   ├── qoe_snapshot.py
│   ├── qos_snapshot.py
│   ├── alert_log.py
│   └── audit_log.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── dependencies.py
│   ├── db.py
│   ├── event_bus.py
│   └── logger.py
│
└── tests/
    ├── domain/
    ├── integration/
    └── e2e/
```
