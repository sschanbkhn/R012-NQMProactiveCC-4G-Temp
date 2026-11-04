"""
SyncCellParamsUseCase — dong bo tham so RF hien tai cua cell tu file CSV export
Admin CLI (NetAct) vao bang cell_infor.
Tu: BUSINESS_RULES.md Section 10.2; TASK_LIST.md C2.6

LUU Y TEN GOI (khong doi ten file/class de khop TASK_LIST.md C2.6 +
ISyncCellParamsUseCase da co san tu B2.9): BUSINESS_RULES.md SS10.2 mo ta dich
la bang "cell_params", nhung quyet dinh THAT da xac nhan voi user truoc do (C2.1,
quyet dinh 12/07/2026 - xem docstring application/trigger_cr_use_case.py diem 7): toan bo
flow trigger CR da CHUYEN HOAN TOAN sang doc/ghi qua bang cell_infor MOI (du lieu
tho tu Admin CLI export), KHONG con dung cell_params cho muc dich "gia tri RF
hien tai" nua (cell_params gio chi con dung de luu snapshot before/new gan voi
1 CR session cu the). Vi vay use case nay THAT SU sync vao cell_infor, khop voi
nguon du lieu ma TriggerCrUseCase dang doc (ICellInforRepo).

Boc lai logic cua adapters/netact/import_4G_cell_infor.py (script thu cong, da
chay THAT thanh cong 27763 dong) - KHONG viet lai parser/SQL, chi goi qua
ICellInforRepo.upsert_from_csv() (moi them C2.6, adapters/postgres/
cell_infor_repo.py) - parsing file (read_csv(), import truc tiep tu module cu)
+ SQL upsert nam TRON VEN trong adapter, dung nguyen ven logic da chay that.
application/ KHONG import adapters/ truc tiep (ARCHITECTURE.md SS9 dependency
rule) - day la ly do KHONG goi read_csv()/upsert SQL truc tiep tai day.

TU GIA DINH - CAN XAC NHAN: khong co dinh nghia HTTP contract nao trong docs cho
input cua job nay. BUSINESS_RULES.md SS10.2 chi noi "Nguon: NetAct (SSH export
hoac API - can xac nhan method)" - KHONG noi ro co upload file qua HTTP hay
khong, va thuc te script hien co lai doc TU FILE CSV local (khong phai SSH/API
tu dong nhu doc goc du kien). execute(file_path: str) nhan DUONG DAN file CSV
DA CO SAN tren server BE (KHONG PHAI file upload multipart qua HTTP) - vi n8n
(ben trigger job nay theo CONTEXT.md SS5.5) duoc mo ta la "chi trigger, KHONG
xu ly logic", khong phu hop voi flow n8n tu upload file nhi phan. Gia dinh file
CSV da duoc dat san o 1 duong dan tren server BE (boi 1 co che export/copy file
rieng CHUA duoc mo ta trong docs) truoc khi n8n goi job nay kem duong dan do.
"""

import logging

from domain.ports.inbound.use_case_ports import ISyncCellParamsUseCase, SyncResult
from domain.ports.outbound.repo_ports import ICellInforRepo

logger = logging.getLogger(__name__)


class SyncCellParamsUseCase(ISyncCellParamsUseCase):
    def __init__(self, cell_infor_repo: ICellInforRepo):
        self._cell_infor_repo = cell_infor_repo

    async def execute(self, file_path: str) -> SyncResult:
        total_synced = await self._cell_infor_repo.upsert_from_csv(file_path)
        logger.info(
            "Sync cell_infor tu CSV hoan thanh",
            extra={"file_path": file_path, "total_synced": total_synced},
        )
        return SyncResult(total_synced=total_synced)
