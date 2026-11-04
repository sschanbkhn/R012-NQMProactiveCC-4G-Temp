"""
CrEventBus - SSE pub/sub qua asyncio.Queue.
Tu: ARCHITECTURE.md Section 7.2; TASK_LIST.md B1.8

Singleton `event_bus` o cuoi file - register trong main.py lifespan (app.state.event_bus).
Luu y khi dung o router (C1.5): PHAI Depends(get_event_bus) tra ve singleton nay,
KHONG dung Depends() tran voi CrEventBus lam type - xem TODO known issue o TASK_LIST.md C1.5.

C1.5-fix (20072026): them buffer replay theo session_id - sua race condition da
bao cao o C1.4-fix (POST /cr/trigger tra 202 + chay CR o nen qua BackgroundTasks
- xem application/trigger_cr_use_case.py). Truoc day publish() chi day event vao
cac Queue DANG subscribe tai thoi diem goi - neu FE mo EventSource cham hon luc
run_cr_flow() da bat dau emit (vd buoc 3 CDS API rat nhanh), cac event dau MAT
VINH VIEN vi khong co gi luu lai. Gio moi session_id giu them 1 deque(maxlen=20)
buffer trong RAM - subscribe() moi se duoc replay lai toan bo buffer TRUOC khi
nhan event moi, dam bao FE khong bo lo event nao du subscribe tre.
"""
import asyncio
from collections import defaultdict, deque

# So event toi da giu lai/session de replay cho subscriber den tre.
# Ly do chon 20: flow chinh cua TriggerCrUseCase (application/trigger_cr_use_case.py)
# phat dung 18 event cho 1 lan CR thanh cong (buoc 1,2,4,5,6,7,8,9,10,11,12,17,18
# = 1 event/buoc, rieng buoc 3 phat 2 lan running+success, buoc 13 gop 13-16 cung
# phat 2 lan running+success -> 12 + 2 + 2*2 = 18, xem
# tests/unit/test_trigger_cr_use_case.py::test_18_buoc_chay_dung_thu_tu_va_dung_du_lieu).
# 20 = du cover TRON VEN ca flow thanh cong (khong bao gio bi cat mat event dau
# vi day het buffer), them 2 slot du phong cho cac bien the loi/canh bao trong
# tuong lai ma khong can doi hang so nay ngay lap tuc.
_BUFFER_MAXLEN = 20

# Thoi gian giu buffer sau khi session DONE/FAILED (giay) - du de FE reconnect/
# retry EventSource trong 1 khoang ngan sau khi CR ket thuc, nhung van don dep
# de RAM khong tich luy vo han theo so luong session da chay qua server.
_CLEANUP_DELAY_SECONDS = 300


class CrEventBus:
    def __init__(self):
        self._queues: dict[int, list[asyncio.Queue]] = defaultdict(list)
        # Buffer RAM thuan tuy (khong persist DB) - khac cr_logs[] o DB da biet
        # la TODO rieng, o day chi phuc vu live progress/replay ngan han.
        self._buffers: dict[int, deque[dict]] = defaultdict(lambda: deque(maxlen=_BUFFER_MAXLEN))
        # Giu reference toi cac task don dep - asyncio chi giu weak ref toi task
        # dang chay, khong luu lai co the bi garbage collect giua chung truoc khi
        # sleep() xong (canh bao chinh thuc cua asyncio docs).
        self._cleanup_tasks: set[asyncio.Task] = set()

    async def subscribe(self, session_id: int) -> asyncio.Queue:
        q = asyncio.Queue()
        # Replay buffer TRUOC KHI dang ky vao self._queues - dam bao thu tu
        # dung (publish() moi trong luc nay chua thay q trong self._queues nen
        # khong the chen event xen giua qua trinh replay, tranh dao thu tu).
        for buffered_event in self._buffers.get(session_id, ()):
            q.put_nowait(buffered_event)
        self._queues[session_id].append(q)
        return q

    async def publish(self, session_id: int, event: dict):
        # C1.4-fix6 (21072026): heartbeat (application/trigger_cr_use_case.py
        # _emit_heartbeat_loop) CHI de giu SSE stream song trong luc submit_cr()
        # chay lau, KHONG phai lich su tien trinh can replay. Neu luu ca
        # heartbeat vao buffer, buoc 13 chay qua nhieu heartbeat (vd 600s/lenh,
        # 30s/heartbeat) se day cac event tien trinh THAT (buoc 1-12) ra khoi
        # deque(maxlen=20), khien subscriber reconnect mat sach lich su that.
        # Vi vay CHI event tien trinh that (co step/status) moi vao buffer;
        # heartbeat chi bo thang vao queue cua subscriber DANG SONG.
        if event.get("type") != "heartbeat":
            # Luu vao buffer TRUOC - de subscriber den sau (ngay ca ngay sau
            # dong lenh nay) van thay duoc event nay qua replay o subscribe().
            self._buffers[session_id].append(event)
        for q in self._queues.get(session_id, []):
            await q.put(event)
        if event.get("done"):
            # CR da ket thuc (DONE/FAILED, xem application/trigger_cr_use_case.py
            # _emit(done=True)/_fail()) - don buffer sau 1 khoang tre thay vi
            # ngay lap tuc, tranh xoa buffer dung luc FE vua nhan 202 va chua kip
            # mo EventSource xong (rieng cho truong hop CR that bai rat nhanh).
            self._schedule_buffer_cleanup(session_id)

    async def unsubscribe(self, session_id: int, q: asyncio.Queue):
        self._queues[session_id].remove(q)

    def _schedule_buffer_cleanup(self, session_id: int) -> None:
        task = asyncio.create_task(self._cleanup_buffer_after_delay(session_id))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def _cleanup_buffer_after_delay(self, session_id: int) -> None:
        await asyncio.sleep(_CLEANUP_DELAY_SECONDS)
        # pop (khong phai del) - an toan neu key da bi don truoc do (khong the
        # xay ra trong flow hien tai vi chi co 1 task cleanup/session, nhung
        # tranh KeyError neu logic mo rong sau nay goi 2 lan).
        self._buffers.pop(session_id, None)
        self._queues.pop(session_id, None)


event_bus = CrEventBus()
