"""
GET /cr/stream/{session_id} — SSE stream.
Tu: ARCHITECTURE.md Section 6.1, 6.2; API_CONTRACTS.md Section 6; TASK_LIST.md C1.5

KI-01 (TASK_LIST.md dong 693-698) da xu ly: dung Depends(get_event_bus) - tra ve
singleton event_bus (infrastructure/event_bus.py) - KHONG dung Depends() tran voi
CrEventBus lam type (se tao instance MOI moi request, subscribe/publish se khong
cung 1 bus voi TriggerCrUseCase).

C1.4-fix5 (20072026): idle-gap timeout giam tu 120s -> 90s. Truoc day 120s la
muc "cho tam on" cho buoc SSH cham (khong emit gi giua chung) - nhung buoc 13
(submit_cr) da tung mat >120s thuc te, khien timeout nay CAT NHAM ket noi FE
dang theo doi 1 CR van chay dung. Gio TriggerCrUseCase.run_cr_flow() da tu
emit event heartbeat moi 30s trong luc cho submit_cr() (xem
application/trigger_cr_use_case.py::_emit_heartbeat_loop) nen idle-gap that su
CHI xay ra khi heartbeat NGUNG han (task/process chet that) - 90s = gap 3 lan
heartbeat lien tiep bi mat, du du de ket luan ket noi/CR da chet, KHONG con
can nguong 120s rong rai nhu truoc (luc chua co heartbeat).
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from infrastructure.dependencies import get_event_bus
from infrastructure.event_bus import CrEventBus

router = APIRouter()
logger = logging.getLogger(__name__)

# Xem giai thich day du o docstring dau file - 90s la luoi an toan SAU KHI da
# co heartbeat 30s tu TriggerCrUseCase, khong phai gia tri doc lap.
_IDLE_GAP_TIMEOUT_SECONDS = 90


@router.get("/cr/stream/{session_id}")
async def cr_stream(session_id: int, bus: CrEventBus = Depends(get_event_bus)) -> StreamingResponse:
    async def event_generator():
        queue = await bus.subscribe(session_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_IDLE_GAP_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    # WORKFLOW.md SS6 khong dinh nghia event "timeout" rieng -
                    # giu nguyen mau ARCHITECTURE.md SS6.2, dong stream sau khi bao
                    yield f"data: {json.dumps({'status': 'timeout'})}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done"):
                    break
        finally:
            await bus.unsubscribe(session_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
