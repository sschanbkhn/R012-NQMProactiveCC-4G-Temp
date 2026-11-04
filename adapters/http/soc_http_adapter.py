"""
SocHttpAdapter — implement ISocGateway.get_qoe() — MOCK (auth chua xac nhan, xem OQ-01).
Tu: ARCHITECTURE.md Section 5.1; CONTEXT.md Section 5.2; TASK_LIST.md B6.5
"""

import logging
from datetime import datetime

from domain.ports.outbound.gateway_ports import ISocGateway

logger = logging.getLogger(__name__)


class SocHttpAdapter(ISocGateway):
    # OQ-01 (TASK_LIST.md) - SOC auth chua xac nhan, chua the goi that. MOCK theo
    # dung shape response du kien API_CONTRACTS.md SS3 dong 210-224 de flow phia
    # tren (EvaluateCrUseCase, chua lam) test duoc voi data gia lap.
    # Signature khop ISocGateway.get_qoe() (B2.7, domain/ports) - KHONG co tham so
    # granularity nhu code mau API_CONTRACTS.md SS3 dong 232-238 (vi dung mo ta
    # minh hoa, port that da chot 3 tham so tu B2.7).
    async def get_qoe(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]:
        logger.warning("SocHttpAdapter dung MOCK data", extra={"cells": len(cell_names)})
        return [
            {
                "cell_name": name,
                "metrics": [{"time": from_dt.isoformat(), "qoe": 3.5}],
            }
            for name in cell_names
        ]
