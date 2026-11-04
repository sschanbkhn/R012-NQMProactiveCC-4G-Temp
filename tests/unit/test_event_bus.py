"""
Unit test cho CrEventBus — buffer/replay theo session_id.
Tu: TASK_LIST.md C1.5-fix, docs/DEV_LOG.md muc [C1.5-fix] (20072026)

Muc tieu: xac nhan subscriber den SAU khi event da publish van nhan du,
KHONG mat event nao (sua race condition SSE da bao cao o C1.4-fix - FE co
the mo EventSource cham hon luc run_cr_flow() da bat dau emit).
"""

import asyncio

import pytest

import infrastructure.event_bus as event_bus_module
from infrastructure.event_bus import CrEventBus

SESSION_ID = 999


class TestBufferReplay:
    async def test_publish_truoc_khi_subscribe_van_duoc_replay_du_theo_dung_thu_tu(self):
        bus = CrEventBus()
        e1 = {"step": 1, "msg": "buoc 1"}
        e2 = {"step": 2, "msg": "buoc 2"}
        e3 = {"step": 3, "msg": "buoc 3"}

        # publish CA 3 event TRUOC khi co subscriber nao - mo phong dung tinh
        # huong bug that: run_cr_flow() da chay xong vai buoc truoc khi FE kip
        # mo EventSource (BackgroundTasks chi bat dau SAU KHI response 202 da
        # gui, nhung FE can them 1 vong round-trip network moi subscribe kip).
        await bus.publish(SESSION_ID, e1)
        await bus.publish(SESSION_ID, e2)
        await bus.publish(SESSION_ID, e3)

        queue = await bus.subscribe(SESSION_ID)

        # 3 event cu PHAI co san ngay trong queue, dung thu tu da publish -
        # subscribe() replay tu buffer TRUOC khi dang ky nhan event moi.
        assert queue.get_nowait() == e1
        assert queue.get_nowait() == e2
        assert queue.get_nowait() == e3
        assert queue.empty()

        # Sau khi replay xong, event MOI publish van phai toi duoc subscriber
        # nay binh thuong (khong chi replay 1 lan roi ngung nhan tiep).
        e4 = {"step": 4, "msg": "buoc 4"}
        await bus.publish(SESSION_ID, e4)
        assert await asyncio.wait_for(queue.get(), timeout=1) == e4


class TestHeartbeatKhongVaoBuffer:
    async def test_heartbeat_xen_ke_khong_lam_loang_buffer_nhung_subscriber_song_van_nhan_du(self):
        # C1.4-fix6 (21072026) - mo phong dung tinh huong bug da phat hien:
        # buoc 13 (submit_cr) chay lau, _emit_heartbeat_loop() publish nhieu
        # heartbeat XEN KE giua cac event tien trinh that. Truoc fix, heartbeat
        # cung vao buffer deque(maxlen=20) va co the day event tien trinh that
        # ra ngoai khi buoc 13 chay du lau.
        bus = CrEventBus()
        queue = await bus.subscribe(SESSION_ID)  # subscriber dang song tu dau

        e1 = {"step": 1, "status": "success", "msg": "buoc 1"}
        hb1 = {"type": "heartbeat", "msg": "dang xu ly... (30s)"}
        e2 = {"step": 2, "status": "success", "msg": "buoc 2"}
        hb2 = {"type": "heartbeat", "msg": "dang xu ly... (60s)"}
        hb3 = {"type": "heartbeat", "msg": "dang xu ly... (90s)"}
        e3 = {"step": 13, "status": "running", "msg": "buoc 13"}

        for event in (e1, hb1, e2, hb2, hb3, e3):
            await bus.publish(SESSION_ID, event)

        # Buffer CHI duoc chua event tien trinh that - khong heartbeat nao
        # lot vao, du publish xen ke lien tuc.
        assert list(bus._buffers[SESSION_ID]) == [e1, e2, e3]

        # Subscriber DANG SONG van phai nhan DU CA 6 event (ca heartbeat) -
        # heartbeat chi bi loai khoi buffer replay, khong bi loai khoi luong
        # SSE truc tiep (van can giu ket noi song cho subscriber nay).
        for expected in (e1, hb1, e2, hb2, hb3, e3):
            assert queue.get_nowait() == expected
        assert queue.empty()

        # Subscriber MOI (reconnect SAU khi buoc 13 da chay qua nhieu
        # heartbeat) phai replay dung 3 event tien trinh that, KHONG dinh
        # heartbeat nao xen vao giua - dung muc tieu cua fix nay.
        late_queue = await bus.subscribe(SESSION_ID)
        assert late_queue.get_nowait() == e1
        assert late_queue.get_nowait() == e2
        assert late_queue.get_nowait() == e3
        assert late_queue.empty()


class TestBufferCleanup:
    async def test_buffer_tu_don_dep_sau_khi_session_done(self, monkeypatch):
        # Rut ngan _CLEANUP_DELAY_SECONDS (mac dinh 300s) xuong 0 chi cho test
        # nay - khong the doi that 5 phut trong unit test.
        monkeypatch.setattr(event_bus_module, "_CLEANUP_DELAY_SECONDS", 0)
        bus = CrEventBus()

        await bus.publish(SESSION_ID, {"step": 18, "done": True})
        assert SESSION_ID in bus._buffers  # buffer con ngay sau publish

        # Task don dep chay qua asyncio.create_task() - nhuong quyen dieu
        # khien cho event loop de task do kip chay xong (sleep(0) da patch).
        await asyncio.sleep(0.05)

        assert SESSION_ID not in bus._buffers
        assert SESSION_ID not in bus._queues
