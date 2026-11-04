"""
NetworkGatewayFacade — implement INetworkGateway bang cach gop 3 adapter rieng
(CdsHttpAdapter/CtsHttpAdapter/EnodebHttpAdapter), moi adapter chi co 1 method.
Tu: ARCHITECTURE.md Section 5.1; TASK_LIST.md B8.1

Quyet dinh design: GAP phat hien tu B6.2 (xem chu y trong cds_http_adapter.py) —
INetworkGateway (domain/ports/outbound/gateway_ports.py, B2.7) la 1 ABC gom ca 3
method get_cell_neighbors/get_qos_metrics/get_enodeb_list, nhung ARCHITECTURE.md
SS5.1 lai chia 3 file adapter rieng — khong adapter nao du 3 method de instantiate
truc tiep INetworkGateway. Da xac nhan tu B6.2: se gop qua composite/facade o
B8.1 — day chinh la facade do. Chi delegate nguyen signature, KHONG tu them logic
(retry/sanitize/... da nam san trong tung adapter con).
"""

from datetime import datetime

from adapters.http.cds_http_adapter import CdsHttpAdapter
from adapters.http.cts_http_adapter import CtsHttpAdapter
from adapters.http.enodeb_http_adapter import EnodebHttpAdapter
from domain.ports.outbound.gateway_ports import INetworkGateway


class NetworkGatewayFacade(INetworkGateway):
    def __init__(
        self,
        cds_adapter: CdsHttpAdapter,
        cts_adapter: CtsHttpAdapter,
        enodeb_adapter: EnodebHttpAdapter,
    ):
        self._cds = cds_adapter
        self._cts = cts_adapter
        self._enodeb = enodeb_adapter

    async def get_cell_neighbors(
        self,
        tram_id: str,
        tram_name: str,
        action: str,
        timeout: int = 30,
        so_lan_thu: int = 3,
    ) -> list[dict]:
        # V6: chuyen tiep nguyen ven timeout/so_lan_thu - facade khong tu quyet
        # dinh gia tri nao (chi delegate, xem docstring dau file).
        return await self._cds.get_cell_neighbors(
            tram_id, tram_name, action, timeout=timeout, so_lan_thu=so_lan_thu
        )

    async def get_qos_metrics(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]:
        return await self._cts.get_qos_metrics(cell_names, from_dt, to_dt)

    async def get_enodeb_list(self, page: int, size: int) -> list[dict]:
        return await self._enodeb.get_enodeb_list(page, size)
