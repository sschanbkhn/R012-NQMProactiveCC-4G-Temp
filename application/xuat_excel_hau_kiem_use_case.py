"""
XuatExcelHauKiemUseCase - du lieu cho GET /hau-kiem/excel (18/10/2026, yeu cau
truc tiep user, doi chieu file mau Check_4G-TXN250M-HNI.xlsx).

=== CHI GOM DU LIEU, KHONG DANH GIA ===
Ket luan Dat/Khong dat lay NGUYEN tu GetQosCellsUseCase/GetQoeCellsUseCase (bang
hau kiem tren UI) - cung ham danh gia, cung nguon so lieu (snapshot luc danh
gia). Excel KHONG duoc co ban luat thu 2.

=== DONG = CELL ANH HUONG DA LUU ===
Moi session 1 khoi, 1 dong / cell trong cr_affected_cells (giu thu tu luc chay
CR, 1-1 voi bang hau kiem). Cot E dat cung dong voi cell trung ten trong
cell_params cua CHINH session (cell R012 da chay CR). Viec ve file (gop o, vien)
la cua adapters/excel/hau_kiem_xlsx.py.
"""

from datetime import date, timedelta, timezone

from domain.errors import CrSessionNotFoundError
from domain.ports.outbound.repo_ports import (
    ICellParamsRepo,
    ICrAffectedCellsRepo,
    ICrPhieuRepo,
    ICrSessionRepo,
    IDashboardRepo,
    IEnodebRepo,
)
from domain.value_objects.khu_vuc import ma_tinh_theo_khu_vuc
from domain.value_objects.trang_thai_phieu import ten_phuong_an

_GMT7 = timezone(timedelta(hours=7))

_DANH_GIA = {"PASS": "Dat", "FAIL": "Khong dat", "INSUFFICIENT_DATA": "Thieu du lieu"}



def _n_tren_7(so_ngay_co_du_lieu: int, n: int) -> str | None:
    # 0 ngay du lieu -> de trong (khong ghi "0/7"): o so khong co du lieu phai
    # TRONG, khong ghi 0 (yeu cau user).
    return f"{n}/7" if so_ngay_co_du_lieu else None


def _chi_so(item, eval_attr: str) -> dict:
    """1 nhom QoS hoac QoE cua 1 dong - doc tu ket qua bang hau kiem."""
    if item is None:
        return {"tb_truoc": None, "tb_sau": None, "lech": None, "danh_gia": _DANH_GIA["INSUFFICIENT_DATA"],
                "so_ngay_co_dl_truoc": None, "so_ngay_co_dl": None, "so_ngay_dat": None, "thieu": True}
    e = getattr(item, eval_attr)
    return {
        # TB truoc + so ngay truoc (19/10/2026, yeu cau user): Lech va "Thieu
        # du lieu" phu thuoc CA ve truoc - thieu cot nay nguoi doc khong tu
        # kiem lai duoc ket luan. Cung lay tu snapshot nhu TB sau.
        "tb_truoc": e.avg_before,
        "tb_sau": e.avg_after,
        # item.delta = MetricEvaluation.lech = round(TB tho truoc - TB tho sau, 2)
        # - KHONG tru 2 TB da tron, de khop so man hinh va so da so nguong.
        "lech": item.delta,
        "danh_gia": _DANH_GIA.get(e.result, e.result),
        "so_ngay_co_dl_truoc": _n_tren_7(item.so_ngay_before, item.so_ngay_before),
        "so_ngay_co_dl": _n_tren_7(item.so_ngay_after, item.so_ngay_after),
        # Thong ke THAM KHAO (khong dung de danh gia): so ngay sau CR diem >= 3.
        "so_ngay_dat": _n_tren_7(item.so_ngay_after, e.so_ngay_dat_sau),
        "thieu": e.result == "INSUFFICIENT_DATA",
    }


class XuatExcelHauKiemUseCase:
    def __init__(
        self,
        session_repo: ICrSessionRepo,
        dashboard_repo: IDashboardRepo,
        affected_cells_repo: ICrAffectedCellsRepo,
        cell_params_repo: ICellParamsRepo,
        cr_phieu_repo: ICrPhieuRepo,
        enodeb_repo: IEnodebRepo,
        qos_cells_use_case,
        qoe_cells_use_case,
    ):
        self._session_repo = session_repo
        self._dashboard_repo = dashboard_repo
        self._affected_cells_repo = affected_cells_repo
        self._cell_params_repo = cell_params_repo
        self._cr_phieu_repo = cr_phieu_repo
        self._enodeb_repo = enodeb_repo
        self._qos = qos_cells_use_case
        self._qoe = qoe_cells_use_case

    async def execute(
        self,
        session_id: int | None = None,
        tu_ngay: date | None = None,
        den_ngay: date | None = None,
        ma_tinh: list[str] | None = None,
        khu_vuc: list[str] | None = None,
        trang_thai: list[str] | None = None,
    ) -> list[dict]:
        if session_id is not None:
            s = await self._session_repo.get_by_id(session_id)
            if s is None:
                raise CrSessionNotFoundError(f"cr_session id={session_id} khong ton tai", session_id=session_id)
            sessions = [{"id": s.id, "tram_id": s.tram_id, "tram_name": s.tram_name or s.tram_id,
                         "executed_at": s.executed_at}]
        else:
            # khu_vuc + ma_tinh cung loc tram.ma_tinh -> lay GIAO, giong dashboard.
            loc_ma_tinh = ma_tinh or None
            if khu_vuc:
                theo_kv = ma_tinh_theo_khu_vuc(khu_vuc)
                loc_ma_tinh = [m for m in theo_kv if m in ma_tinh] if ma_tinh else theo_kv
            sessions = await self._dashboard_repo.loc_session(tu_ngay, den_ngay, loc_ma_tinh, trang_thai)
        return [await self._khoi(s) for s in sessions if s["executed_at"] is not None]

    async def phieu(self, session_ids: list[int]) -> list[dict]:
        """Dong cho sheet "Phieu" - CUNG ham repo voi GET /phieu/excel de 2 file
        ra cung so. Chi phieu cua cac session dang xuat."""
        if not session_ids:
            return []
        return await self._cr_phieu_repo.dong_excel(session_ids=session_ids)

    async def _khoi(self, s: dict) -> dict:
        sid = s["id"]
        affected = await self._affected_cells_repo.get_by_cr_session_id(sid)
        qos = {r.cell_name: r for r in await self._qos.execute(sid)}
        qoe = {r.cell_name: r for r in await self._qoe.execute(sid)}
        cell_cr = [cp.cell_name for cp in await self._cell_params_repo.get_by_cr_session_id(sid)]

        # 19/10/2026 (yeu cau user): 3 cot Ma phieu | Phuong an | Trang thai
        # thay 2 cot Hien truong/He thong - hien MOI trang thai (ca FAILED,
        # KHONG_XUAT_*) de nguoi doc biet cell khong dat da duoc xu ly toi dau,
        # khong chi cell co phieu SUCCESS. UNIQUE (session, cell) nen <= 1 dong.
        phieu: dict[str, dict] = {}
        for p in await self._cr_phieu_repo.get_by_cr_session_id(sid):
            if p.get("deleted_at") is not None:
                continue
            phieu[p["cell_name"]] = {
                "ma": str(p["phieu_id"]) if p.get("phieu_id") else None,
                "phuong_an": ten_phuong_an((p.get("request_payload") or {}).get("PhuongAnXuLyDuKien")),
                "trang_thai": p["trang_thai"],
            }

        # Ten site cua cell anh huong (cot C) - DISTINCT theo thu tu xuat hien.
        tram_ids = list(dict.fromkeys(a["tram_id"] for a in affected if a.get("tram_id")))
        ten_tram = {t.tram_id: t.tram_name for t in await self._enodeb_repo.get_by_tram_ids(tram_ids)}
        sites = list(dict.fromkeys(ten_tram.get(t) or t for t in tram_ids))

        ten_aff = [a["cell_name"] for a in affected]
        dong = []
        for ten in ten_aff:
            q, e = _chi_so(qos.get(ten), "qos_eval"), _chi_so(qoe.get(ten), "qoe_eval")
            dong.append({
                "cell_anh_huong": ten,
                "cell_cr": ten if ten in cell_cr else None,
                "cell_hau_kiem": ten,
                "qos": q,
                "qoe": e,
                "phieu": phieu.get(ten),
                "ghi_chu": "Thieu du lieu" if q["thieu"] or e["thieu"] else None,
            })
        # Cell da chay CR nhung KHONG nam trong danh sach anh huong (DB 18/10:
        # 0 session) - van ghi ra cuoi khoi, khong am tham bo mat.
        for ten in cell_cr:
            if ten not in ten_aff:
                dong.append({"cell_anh_huong": None, "cell_cr": ten, "cell_hau_kiem": None,
                             "qos": None, "qoe": None, "phieu": None, "ghi_chu": None})
        for i, site in enumerate(sites):
            if i < len(dong):
                dong[i]["site"] = site
        return {
            "session_id": sid,
            "ngay_cr": s["executed_at"].astimezone(_GMT7).strftime("%d/%m/%Y"),
            # tram chua sync RIMS (khong co ten) -> ghi tram_id, khong de trong.
            "tram": s.get("tram_name") or s.get("tram_id"),
            # Ma tram cho ten file 1 session (DOT 2): hau_kiem_<ma>_<ten>_<ts>.
            "tram_id": s.get("tram_id"),
            "dong": dong,
        }
