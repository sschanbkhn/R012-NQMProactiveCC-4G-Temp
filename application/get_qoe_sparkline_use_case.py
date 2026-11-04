"""
GetQoeSparklineUseCase — QoE theo ngay cho 1 cell.
Tu: yeu cau truc tiep user 16082026 (QoE danh gia PER-CELL, doc lap voi
qoe_result cap session).

Ban sao doi xung cua GetQosSparklineUseCase (application/
get_qos_sparkline_use_case.py) - CO Y giu giong het de 2 duong QoS/QoE khong
bao gio lech nhau ve cach tinh cua so. Chi khac 3 diem:
  1. Nguon: ISocGateway.get_qoe() thay vi INetworkGateway.get_qos_metrics()
  2. Key gia tri: "qoe" thay vi "qos" (nam trong tung diem, khong xu ly o day)
  3. Mac dinh to_dt = now - 2 NGAY (QoS dung 1 ngay) - xem comment trong execute()
"""

from datetime import datetime, timedelta, timezone

from domain.ports.inbound.use_case_ports import IGetQoeSparklineUseCase
from domain.ports.outbound.gateway_ports import ISocGateway

# CEM tre 2 NGAY - DO THAT (15/08, scripts/test_cem_qoe.py): goi voi date=hom qua
# tra ve data:[] du HTTP 200; phai lui ve T-2 moi co du lieu. CTS chi tre 1 ngay
# (xem GetQosSparklineUseCase) nen 2 con so nay KHONG duoc gop lam mot.
#
# Hau qua da biet: cua so QoE mac dinh LECH 1 NGAY so voi QoS. Chap nhan - tha
# lech 1 ngay con hon xin ngay chua co roi bao "khong co du lieu" nham.
_CEM_LAG_DAYS = 2


class GetQoeSparklineUseCase(IGetQoeSparklineUseCase):
    def __init__(self, soc_gw: ISocGateway):
        self._soc_gw = soc_gw

    async def execute(
        self,
        cell_name: str,
        days: int = 7,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict]:
        if from_dt is not None and to_dt is not None:
            # Window TUONG MINH - dung nguyen gia tri caller truyen, KHONG tinh
            # lai tu days. Chi ap dung khi CA HAI cung co (giong QoS).
            pass
        else:
            # to = hom nay - 2 ngay (KHONG phai -1 nhu QoS): xem _CEM_LAG_DAYS.
            now = datetime.now(timezone.utc)
            to_dt = now - timedelta(days=_CEM_LAG_DAYS)
            from_dt = to_dt - timedelta(days=days)

        # get_qoe() nhan MANG cell nen phai boc [cell_name] roi tach lai - giong
        # het cach GetQosSparklineUseCase lam voi get_qos_metrics().
        raw = await self._soc_gw.get_qoe([cell_name], from_dt, to_dt)
        for entry in raw:
            if entry.get("cell_name") == cell_name:
                return entry.get("metrics", [])
        return []
