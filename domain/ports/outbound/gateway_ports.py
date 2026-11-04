"""
INetworkGateway, ISocGateway, INetActGateway.
Tu: ARCHITECTURE.md Section 3.4; TASK_LIST.md B2.7
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from domain.value_objects.oss_instance import OssInstance
from domain.value_objects.vendor import Vendor


class INetworkGateway(ABC):
    @abstractmethod
    async def get_cell_neighbors(
        self,
        tram_id: str,
        tram_name: str,
        action: str,
        timeout: int = 30,
        so_lan_thu: int = 3,
    ) -> list[dict]: ...
    # timeout/so_lan_thu them o V6 (12/08, yeu cau truc tiep user) - 2 luong
    # dung chung method nay co yeu cau NGUOC NHAU (preview dong bo can 1 lan goi
    # lau; CR that chay nen can retry nhieu lan ngan). Mac dinh 30s x 3 = hanh
    # vi CU, moi noi goi khong truyen gi deu giu nguyen. Xem ly do day du trong
    # adapters/http/cds_http_adapter.py.
    # action: str duoc them so voi ARCHITECTURE.md dong 175 (pseudocode chi co
    # tram_id, tram_name). Ly do: API_CONTRACTS.md SS1 dong 40-47, request body
    # CDS that can 4 field (tramId, tramName, action, technology). "action"
    # (shutdown|cancel|relocate) thay doi moi lan goi, khong hardcode duoc nhu
    # "technology" (luon co dinh "4G" theo CONTEXT.md — hardcode trong adapter,
    # khong can lam tham so port).

    @abstractmethod
    async def get_qos_metrics(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]: ...

    @abstractmethod
    async def get_enodeb_list(self, page: int, size: int) -> list[dict]: ...


class ISocGateway(ABC):
    @abstractmethod
    async def get_qoe(
        self, cell_names: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[dict]: ...


class INetActGateway(ABC):
    @abstractmethod
    async def submit_cr(
        self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance
    ) -> dict: ...
    # SUA 18082026 - tra dict thay vi bool:
    #   {ok, trang_thai, buoc_loi, dn_list, tom_tat}
    # bool khong du: caller can biet (1) BUOC nao hong (import vs provision - 2
    # tinh huong rat khac nhau, Import hong thi thiet bi CHUA doi gi) va (2) DN
    # nao hong, de dat PARTIAL_SUCCESS va ghi cr_log buoc 13 theo tung DN.
    # trang_thai: "DONE" | "PARTIAL_SUCCESS" | "FAILED" - khop CrStatus.
    # 1 method duy nhat bao tron Upload (WORKFLOW.md buoc 13) + Import (buoc 14)
    # + Provision (buoc 15) — SshExecutor la chi tiet noi bo cua adapter, khong
    # lo ra port (WORKFLOW.md dong 216: "Port: INetActGateway.submit_cr()").
    #
    # SUA 27092026 (Giai doan 1 buoc 2, dinh tuyen OSS theo tung cell): tham so
    # doi tu ma_tinh: str -> oss: OssInstance. LY DO: dinh tuyen theo tram tat
    # (1 ma_tinh duy nhat cho ca CR) SAI khi cell lan can thuoc tram O TINH CU
    # KHAC (giap ranh tinh) - viec CHON OSS nao gio la trach nhiem cua use
    # case (goi IOssRouter.chon_oss() cho TUNG cell, gom nhom, xem
    # application/trigger_cr_use_case.py), adapter nay CHI con nhan OssInstance
    # DA CHON SAN va thuc thi SSH - khong con tu tra cuu/kiem tra credential
    # (IOssRouter.chon_oss() da lam, tra None cho truong hop chua cau hinh nen
    # use case KHONG goi submit_cr() cho truong hop do).


class IOssRouter(ABC):
    # Giai doan 1 buoc 2 (27/09/2026) - PORT rieng, TACH khoi INetActGateway:
    # chon_oss() la 1 QUYET DINH thuan (tra cuu cau hinh tinh/vendor -> OSS),
    # KHONG lam I/O mang (khac submit_cr() la goi SSH that) - de SYNC (khong
    # async) va de TEST doc lap (mock/fake khong can await).
    @abstractmethod
    def chon_oss(self, ma_tinh_cu: str, vendor: Vendor) -> OssInstance | None: ...
    # Tra None (KHONG raise) khi: (1) khong co route cho (ma_tinh_cu, vendor)
    # nay, HOAC (2) co route nhung credential con la placeholder "???" (7 tinh
    # Netact14 - KI-08). Ly do tra None thay vi raise: day la 1 CELL trong ca
    # CR, phai duoc XU LY nhu 1 dieu kien loai (ly do OSS_CHUA_CAU_HINH,
    # domain/services/neighbor_cell_filter.py), KHONG duoc lam crash ca
    # request - giong tinh than CELL_ID_PHANG/TEN_CELL_SAI_MAU.

    def ly_do_khong_chon(self, ma_tinh_cu: str, vendor: Vendor) -> str | None:
        """Cau giai thich VI SAO chon_oss() tra None (vd "NA14 cau hinh loi:
        thieu password"), None neu chon duoc. THEM 23/10/2026: moi NA giu mat
        khau/han rieng, 1 NA thieu password ma loi CR chi ghi "OSS chua cau
        hinh" thi nguoi van hanh khong biet sua NA nao. KHONG abstract (mac
        dinh None) de cac fake/mock cu khong phai sua. KHONG chua mat khau."""
        return None


class ISaveCellClmGateway(ABC):
    # payload: Any (KHONG import SaveCellClmPayload tu adapters/http truc tiep) -
    # ARCHITECTURE.md SS9 "domain/ CHI import Python stdlib + domain/ noi bo",
    # payload la Pydantic model dinh nghia o adapters/http/save_cell_clm_adapter.py
    # (DTO khop nguyen ten field API ben ngoai, khong phai khai niem nghiep vu domain
    # nhu Cell/Tram) - domain import nguoc adapters se pha huong phu thuoc Hexagonal.
    # KHOI 3a/5 (application/xuat_phieu_use_case.py) CUNG khong duoc import
    # adapters/ (ARCHITECTURE.md SS9 "application/ KHONG import adapters/") -
    # nen luon truyen dict thuan (28 field). Adapter tu validate qua
    # SaveCellClmPayload noi bo (xem save_cell_clm_adapter.py).
    @abstractmethod
    async def save_cell_clm(self, payload: Any) -> dict: ...
    # V2 (12/08, yeu cau truc tiep user) - da BO tham so dry_run. MOI lan goi
    # deu POST THAT vao CTS/TTS (day la WRITE API, ten bat dau "Save" -> ghi
    # record that). Khong con che do preview nao trong adapter.
    #
    # Tra ve dict: {status_code, isError, code, message, data, totalRecord} va
    # them "raw_body" khi CTS tu choi. Loi MANG/timeout -> raise
    # SaveCellClmApiError (KHONG tra dict). Caller phan loai loi de quyet dinh
    # co thu lai khong - xem XuatPhieuUseCase._nen_thu_lai().
