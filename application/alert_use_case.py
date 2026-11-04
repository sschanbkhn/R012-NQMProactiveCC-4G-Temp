"""
AlertUseCase — tao alert_log khi phat hien degradation sau CR hoac EVAL_PENDING
qua lau.
Tu: BUSINESS_RULES.md Section 8.3 (QOE/QOS_DEGRADED), Section 8.4 + Section 13
(EVAL_PENDING_TOO_LONG); DB_SCHEMA.md Section 7 (alert_log); TASK_LIST.md C2.7

CO CAN CU RO RANG trong docs cho DIEU KIEN tao alert (khong phai TU GIA DINH):
  - qoe_result = FAIL -> alert_type=QOE_DEGRADED (BUSINESS_RULES.md dong 394)
  - qos_result = FAIL -> alert_type=QOS_DEGRADED (dong 397)
  - cr_session o EVAL_PENDING lien tuc > 30 ngay -> alert_type=
    EVAL_PENDING_TOO_LONG, severity=WARNING (dong 416-418 + dong 558)

Khong dung ABC/port rieng (khac cac use case khac trong domain/ports/inbound) -
class nay KHONG co endpoint HTTP nao goi truc tiep, chi la collaborator noi bo
cua EvaluateCrUseCase (giong cach EvaluationService khong co port rieng) - tranh
them ceremony khong can thiet.

TU GIA DINH - CAN XAC NHAN (docs KHONG noi ro):
  1. QUYET DINH TAM (13072026, xac nhan voi user - GHI RO day la tam thoi):
     severity cho CA QOE_DEGRADED va QOS_DEGRADED deu dung "WARNING" -
     BUSINESS_RULES.md/DB_SCHEMA.md KHONG noi ro muc do (chi
     EVAL_PENDING_TOO_LONG duoc noi ro la WARNING, dong 558), va HIEN CHUA CO
     CAN CU de phan biet muc do khac nhau giua 2 loai nay. CAN doi van hanh
     (Ops team) xac nhan lai muc do nghiem trong THAT sau khi co phan hoi
     thuc te (VD: qua nhieu QOS_DEGRADED co dan den incident khong, co can
     nang len CRITICAL khong) - KHONG tu nang len CRITICAL khi chua co du
     lieu/xac nhan.
  2. detail JSONB theo dung mau DB_SCHEMA.md dong 317-318 (before/after/delta)
     - CO CAN CU, khong phai doan.
  3. Nguong "30 ngay" (EVAL_PENDING_TOO_LONG_DAYS) tinh tu executed_at (ngay CR)
     - docs (BUSINESS_RULES.md dong 416-418) khong noi ro tinh tu executed_at
     hay tu luc chuyen sang EVAL_PENDING - gia dinh dung executed_at de nhat
     quan voi EVALUATION_DAYS (21 ngay) da dung o EvaluateCrUseCase.
  4. SUA (13072026, xac nhan voi user): CO dedupe cho EVAL_PENDING_TOO_LONG -
     truoc khi tao alert moi, kiem tra da co alert CUNG loai + CUNG
     cr_session_id dang o trang thai CHUA acknowledge chua
     (IAlertRepo.exists_unacknowledged(), dung LAI cot is_acknowledged co san
     trong alert_log, KHONG them cot moi). Neu da co -> bo qua, khong tao
     trung. Chi ap dung cho EVAL_PENDING_TOO_LONG (job chay lap lai hang
     ngay) - QOE_DEGRADED/QOS_DEGRADED KHONG can dedupe vi ban chat chi xay
     ra DUNG 1 LAN/session (session chuyen sang EVALUATED ngay sau do, khong
     con nam trong vong quet execute_all_pending() nua nen khong the goi
     trung).
  5. message text tu viet ngan gon bang tieng Viet - khong co mau cau docs quy dinh.
"""

import logging

from domain.ports.outbound.repo_ports import IAlertRepo

logger = logging.getLogger(__name__)

EVAL_PENDING_TOO_LONG_DAYS = 30  # BUSINESS_RULES.md SS8.4 dong 416, SS13 dong 558


class AlertUseCase:
    def __init__(self, alert_repo: IAlertRepo):
        self._alert_repo = alert_repo

    async def check_qoe_degraded(
        self, session_id: int, qoe_before: float | None, qoe_after: float | None
    ) -> None:
        # BUSINESS_RULES.md SS8.3 dong 394 - qoe_after < qoe_before -> FAIL -> alert
        delta = (qoe_after - qoe_before) if qoe_before is not None and qoe_after is not None else None
        await self._alert_repo.create(
            cr_session_id=session_id,
            alert_type="QOE_DEGRADED",
            severity="WARNING",  # gia dinh #1 - xem docstring dau file
            message=f"QoE giam sau CR (session #{session_id}): {qoe_before} -> {qoe_after}",
            detail={"qoe_before": qoe_before, "qoe_after": qoe_after, "delta": delta},
        )
        logger.info("Tao alert QOE_DEGRADED", extra={"session_id": session_id})

    async def check_qos_degraded(
        self, session_id: int, qos_before: float | None, qos_after: float | None
    ) -> None:
        # BUSINESS_RULES.md SS8.3 dong 397 - qos_after < qos_before -> FAIL -> alert
        delta = (qos_after - qos_before) if qos_before is not None and qos_after is not None else None
        await self._alert_repo.create(
            cr_session_id=session_id,
            alert_type="QOS_DEGRADED",
            severity="WARNING",  # gia dinh #1 - xem docstring dau file
            message=f"QoS giam sau CR (session #{session_id}): {qos_before} -> {qos_after}",
            detail={"qos_before": qos_before, "qos_after": qos_after, "delta": delta},
        )
        logger.info("Tao alert QOS_DEGRADED", extra={"session_id": session_id})

    async def check_eval_pending_too_long(self, session_id: int, days_pending: int) -> None:
        # BUSINESS_RULES.md SS8.4 dong 416-418 + SS13 dong 558 - EVAL_PENDING > 30
        # ngay -> notify admin, severity=WARNING (CO CAN CU, khong phai doan)
        #
        # Dedupe (gia dinh #4, sua 13072026) - job chay hang ngay, session van
        # con qua han se bi quet lai moi lan neu khong check truoc.
        already_alerted = await self._alert_repo.exists_unacknowledged(session_id, "EVAL_PENDING_TOO_LONG")
        if already_alerted:
            logger.info(
                "Da co alert EVAL_PENDING_TOO_LONG chua acknowledge cho session nay, bo qua (dedupe)",
                extra={"session_id": session_id, "days_pending": days_pending},
            )
            return

        await self._alert_repo.create(
            cr_session_id=session_id,
            alert_type="EVAL_PENDING_TOO_LONG",
            severity="WARNING",
            message=f"Session #{session_id} o trang thai EVAL_PENDING qua {days_pending} ngay",
            detail={"days_pending": days_pending},
        )
        logger.warning(
            "Tao alert EVAL_PENDING_TOO_LONG",
            extra={"session_id": session_id, "days_pending": days_pending},
        )
