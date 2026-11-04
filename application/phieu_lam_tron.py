"""
Gan co "vuot_luat_lam_tron" cho phieu SUCCESS (18/10/2026, quyet dinh user).

=== VI SAO TINH LUC DOC, KHONG THEM COT ===
Tu 18/10/2026 TB/lech lam tron 2 chu so truoc khi so nguong (domain/services/
evaluation_service.py::LAM_TRON_SO_THAP_PHAN). Phieu da xuat truoc do KHONG sua
/xoa - chi danh dau de FE ghi "xuat theo luat cu". Do tren DB that luc doi luat:
2/145 phieu SUCCESS (32084, 25366). Tinh tu snapshot DA LUU (chinh so lieu luc
danh gia) nen khong can cot moi + migration; GIONG tien le vuot_2_phieu_sector
(gan nhan luc doc, khong sua du lieu cu).

Ket qua: {cr_phieu.id: bool} chi cho dong SUCCESS. Cell khong co snapshot ->
False (khong co can cu de noi phieu sai luat).
"""

from application.get_qoe_cells_use_case import _QOE_CELL_THRESHOLD_DELTA  # noqa: PLC2701
from application.xuat_phieu_use_case import _XUAT_PHIEU_QOS_THRESHOLD_DELTA  # noqa: PLC2701
from domain.ports.outbound.repo_ports import IQoeSnapshotRepo, IQosSnapshotRepo
from domain.services.evaluation_service import EvaluationService, doi_ket_luan_do_lam_tron


def _diem(rows: list[dict], cell: str, period: str, cot: str) -> list[float]:
    return [r[cot] for r in rows if r["cell_name"] == cell and r["period"] == period]


async def co_vuot_luat_lam_tron(
    rows: list[dict], qos_snapshot_repo: IQosSnapshotRepo, qoe_snapshot_repo: IQoeSnapshotRepo
) -> dict[int, bool]:
    ket_qua: dict[int, bool] = {}
    snapshot_theo_session: dict[int, tuple[list, list]] = {}
    ev = EvaluationService()
    for r in rows:
        if r.get("trang_thai") != "SUCCESS":
            continue
        sid = r["cr_session_id"]
        # 1 lan doc snapshot / session (1 trang phieu thuong cung vai session).
        if sid not in snapshot_theo_session:
            snapshot_theo_session[sid] = (
                await qos_snapshot_repo.get_by_session_id(sid),
                await qoe_snapshot_repo.get_by_session_id(sid),
            )
        qos_rows, qoe_rows = snapshot_theo_session[sid]
        co_doi = False
        con_khong_dat = False
        for snap, cot, nguong in (
            (qos_rows, "qos_score", _XUAT_PHIEU_QOS_THRESHOLD_DELTA),
            (qoe_rows, "qoe_score", _QOE_CELL_THRESHOLD_DELTA),
        ):
            truoc = _diem(snap, r["cell_name"], "before", cot)
            sau = _diem(snap, r["cell_name"], "after", cot)
            co_doi = co_doi or doi_ket_luan_do_lam_tron(truoc, sau, nguong)
            con_khong_dat = con_khong_dat or ev.evaluate(truoc, sau, threshold=nguong).result == "FAIL"
        # Chi so kia VAN KHONG DAT thi phieu van dung luat moi -> khong danh dau.
        ket_qua[r["id"]] = co_doi and not con_khong_dat
    return ket_qua
