"""
GetQosSparklineUseCase — QoS theo ngay cho Widget F33 (Tab1) va chart preview CR
(nhieu ngay, Tab2). Tu: BUSINESS_RULES.md Section 9; API_CONTRACTS.md Section 2
(dung cho muc dich (1)); TASK_LIST.md C1.7

Bo sung o Nhom 2 (13072026, xac nhan voi user) - thin wrapper boc INetworkGateway.
get_qos_metrics() de router qos.py KHONG goi thang adapter (xem
domain/ports/inbound/use_case_ports.py::IGetQosSparklineUseCase).

days them sau (21072026, xac nhan voi user, KHONG tich hop CTS moi) - da verify
CtsHttpAdapter.get_qos_metrics() da tra duoc nhieu ngay khi window du rong (goi
8 ngay ra 6 diem that), nen chi can noi rong window thay vi hardcode 48h. Tai
dung dung method gateway co san, khong doi cach goi CTS.

from_dt/to_dt them Gap 1 (22072026, xac nhan voi user) - lay QoS quanh 1 ngay
CR TRONG QUA KHU (vd danh gia lai CR cu), "days" khong lam duoc vi luon neo
cung to_dt=hom qua. Uu tien from_dt/to_dt neu CA HAI duoc truyen, khong thi
tinh tu days nhu cu (KHONG doi hanh vi mac dinh, tranh pha FE dang dung days).
"""

from datetime import datetime, timedelta, timezone

from domain.ports.inbound.use_case_ports import IGetQosSparklineUseCase
from domain.ports.outbound.gateway_ports import INetworkGateway


class GetQosSparklineUseCase(IGetQosSparklineUseCase):
    def __init__(self, network_gw: INetworkGateway):
        self._network_gw = network_gw

    async def execute(
        self,
        cell_name: str,
        days: int = 7,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[dict]:
        if from_dt is not None and to_dt is not None:
            # Window TUONG MINH (Gap 1) - dung nguyen gia tri caller truyen,
            # KHONG tinh lai tu days. Chi ap dung khi CA HAI cung co - neu chi
            # 1 trong 2 duoc truyen (khong nen xay ra, router da chan truoc),
            # rot xuong nhanh "days" ben duoi thay vi dung 1 nua window sai.
            pass
        else:
            # to=yesterday 23:59:59Z (khong doi, giu logic goc) - CTS lag ~2
            # ngay, data hom nay thuong chua co; xin data hom nay se ra rong
            # hoac thieu ngay cuoi, gay hieu nham la loi (CtsHttpAdapter tu
            # chuan hoa gio thanh 23:59:59Z, xem adapters/http/cts_http_adapter.py).
            # from=to - days: days=7 -> 7 ngay lich su (mac dinh, phuc vu chart
            # preview CR). LUU Y: window nay khac ham cu (ham cu tinh from_dt=
            # now-48h doc lap voi to_dt=now-1d, thuc te chi rong ~24h dung "48h"
            # sai ten) - gio window rong dung "days" ngay tinh tu to_dt, ro rang hon.
            now = datetime.now(timezone.utc)
            to_dt = now - timedelta(days=1)
            from_dt = to_dt - timedelta(days=days)

        raw = await self._network_gw.get_qos_metrics([cell_name], from_dt, to_dt)
        for entry in raw:
            if entry.get("cell_name") == cell_name:
                return entry.get("metrics", [])
        return []
