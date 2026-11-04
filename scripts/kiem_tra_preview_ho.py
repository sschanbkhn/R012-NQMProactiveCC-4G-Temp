"""
scripts/kiem_tra_preview_ho.py — chay PreviewCrUseCase.execute() THAT (DB that,
NEIGHBOR_SOURCE=HO) cho 1 vai tram mau - CHI DOC, KHONG SSH (preview khong bao
gio goi SSH/NetAct - xem application/preview_cr_use_case.py), KHONG ghi DB.

Tu: BUOC 4b (08/10/2026, yeu cau truc tiep user) - "TEST: xem truoc tram
117903 qua API (DB that) -> B = 6 cell nhu cu; 117713 (CRAN) -> co
TOA_DO_DUNG_CHUNG, B theo HO; tram NA10 bat ky -> 422 KHONG_CO_DU_LIEU_HO".

Chay:
    python -m scripts.kiem_tra_preview_ho
"""

import asyncio
import json
from dataclasses import asdict

import asyncpg

from application.preview_cr_use_case import PreviewCrUseCase
from application.trigger_cr_use_case import TriggerCrUseCase
from domain.errors import HoNoDataError
from infrastructure import dependencies as deps
from infrastructure.db import AsyncSessionLocal, _ASYNCPG_DSN

# 117903 (test bat buoc, B phai = 6 cell nhu da xac nhan cac lan truoc).
# 117713 (4G-CGY025B-HNI, Cau Giay) - tram TOA_DO_DUNG_CHUNG (CRAN, xem
# scripts/kiem_gia_thuyet_cran.py).
_TRAM_CAN_KIEM = [
    ("117903", "noi thanh - Cau Giay, test bat buoc B=6 cell"),
    ("117713", "CRAN - TOA_DO_DUNG_CHUNG"),
]
# Tram THAT ngoai NA09/HNI (160000 = 4G-BLC001M-CBG, tinh CBG -> route NA14
# theo .env NETACT_SERVERS) - CHUA tung nap du lieu HO cho NA14 (chi NA09 da
# nap, xem docs/DEV_LOG.md) nen ky vong 422 KHONG_CO_DU_LIEU_HO. Dai dien cho
# "tram NA10 bat ky" trong yeu cau goc - du an nay KHONG co NetAct ten "NA10"
# that (chi NA09/NA14, xem .env.example), dung 1 tram ngoai NA09 la du de
# kiem dung dieu kien "chua nap du lieu cho NetAct do".
_TRAM_KHONG_CO_DU_LIEU = "160000"


def _rut_gon(result) -> dict:
    # CANH BAO QUAN TRONG: dataclasses.asdict() BO QUA repr=False (chuyen DI
    # CA user/password cua OssInstance ra plain dict) - KHONG BAO GIO dung
    # truc tiep tren PreviewResult. Tu xay dict TAY, CHI lo instance_id (giong
    # dung cach api/routers/cr.py lam qua OssSeDung) - xem domain/value_objects/
    # oss_instance.py ve ly do repr=False.
    d = asdict(result)
    for key in ("cells_bi_anh_huong", "cells_chay_cr", "tram_bi_anh_huong", "quan_he_day_du"):
        full = d.get(key, [])
        d[key] = {"so_luong": len(full), "vi_du_3": full[:3]}
    d["oss_instance"] = {"instance_id": result.oss_instance.instance_id} if result.oss_instance else None
    # BUOC 4c (10/10/2026) - ban_do khong co credential gi, nhung l1/l2/
    # tram_bi_anh_huong co the dai (vai chuc tram) - rut gon de in cho de doc,
    # KHONG anh huong du lieu THAT tra ve qua API (chi rut gon o script bao cao).
    ban_do = d.get("ban_do")
    if ban_do:
        for key in ("l1", "l2", "tram_bi_anh_huong"):
            full = ban_do.get(key) or []
            ban_do[key] = {"so_luong": len(full), "vi_du_3": full[:3]}
        # duong_bao (10/10/2026) - DA GIAC HINH SAO, KHONG con la list[lat,lon]
        # (xem domain/services/geo_utils.py::duong_bao_hinh_sao()) - rut gon
        # "polygon"/"doan" rieng, GIU x_tren_vien NGUYEN (bool nho, khong can rut gon).
        db = ban_do.get("duong_bao") or {}
        for key in ("polygon", "doan"):
            full = db.get(key) or []
            db[key] = {"so_luong": len(full), "vi_du_3": full[:3]}
        # l1_vong/l2_vong (THEM 15/10/2026) - dang {"danh_sach":, "x_tren_vien":},
        # GIU x_tren_vien NGUYEN, rut gon RIENG "danh_sach".
        for key in ("l1_vong", "l2_vong"):
            vong = ban_do.get(key) or {}
            full = vong.get("danh_sach") or []
            vong["danh_sach"] = {"so_luong": len(full), "vi_du_3": full[:3]}
    return d


async def main() -> None:
    asyncpg_conn = await asyncpg.connect(_ASYNCPG_DSN)
    try:
        async with AsyncSessionLocal() as session:
            cds_adapter = deps.get_cds_adapter()
            cts_adapter = deps.get_cts_adapter()
            enodeb_http_adapter = deps.get_enodeb_http_adapter()
            network_gw = deps.get_network_gateway(cds_adapter, cts_adapter, enodeb_http_adapter)
            enodeb_repo = deps.get_enodeb_repo(session)

            trigger_uc = TriggerCrUseCase(
                network_gw=network_gw,
                netact_gw=deps.get_netact_gateway(),
                session_repo=deps.get_cr_session_repo(session),
                cell_repo=deps.get_cell_params_repo(session),
                cell_infor_repo=deps.get_cell_infor_repo(asyncpg_conn),
                enodeb_repo=enodeb_repo,
                event_bus=deps.get_event_bus(),
                rsboost_calc=deps.get_rsboost_calculator(),
                qrxlevmin_calc=deps.get_qrxlevmin_calculator(),
                xml_builder=deps.get_xml_builder(),
                affected_cells_repo=deps.get_cr_affected_cells_repo(session),
                cr_log_repo=deps.get_cr_log_repo(session),
                oss_router=deps.get_oss_router(),
                ho_neighbor_repo=deps.get_ho_neighbor_repo(session),
                # BUOC 4c (10/10/2026) - can de preview tra duoc ban_do.x.
                # vi_tri_uoc_luong_cell/ban_do.tram_bi_anh_huong[].cells[].lat/lon
                # cho tram CRAN (khong co se cran_map={} , ban_do van chay
                # duoc nhung thieu vi tri CRAN - xem _xay_du_lieu_ban_do()).
                cell_vi_tri_uoc_luong_repo=deps.get_cell_vi_tri_uoc_luong_repo(session),
            )
            preview_uc = PreviewCrUseCase(trigger_use_case=trigger_uc, enodeb_repo=enodeb_repo)

            for tram_id, nhan in _TRAM_CAN_KIEM:
                print("=" * 78)
                print(f"Tram {tram_id} ({nhan})")
                try:
                    result = await preview_uc.execute(tram_id=tram_id, tram_name="", action="shutdown")
                except HoNoDataError as e:
                    print(f"  HoNoDataError (422 KHONG_CO_DU_LIEU_HO): {e}")
                    continue
                print(json.dumps(_rut_gon(result), ensure_ascii=False, indent=2, default=str))
                print(f"\n  >>> So cell trong B (cells_chay_cr): {len(result.cells_chay_cr)}")
                print(f"  >>> x_co: {result.x_co}")
                if result.ban_do:
                    bd = result.ban_do
                    print(f"  >>> ban_do.x: {json.dumps(bd['x'], ensure_ascii=False, default=str)}")
                    print(f"  >>> ban_do.l1 so luong: {len(bd['l1'])}, l2 so luong: {len(bd['l2'])}")
                    print(f"  >>> ban_do.l1_vong x_tren_vien={bd['l1_vong']['x_tren_vien']}, l2_vong x_tren_vien={bd['l2_vong']['x_tren_vien']}")
                    print(f"  >>> ban_do.tram_bi_anh_huong so luong: {len(bd['tram_bi_anh_huong'])}")
                    db = bd["duong_bao"]
                    so_dinh = len(db["polygon"]) if db["polygon"] is not None else len(db["doan"])
                    print(f"  >>> ban_do.duong_bao: so dinh={so_dinh} (polygon={db['polygon'] is not None}) x_tren_vien={db['x_tren_vien']}")

            print("=" * 78)
            print(f"Tram {_TRAM_KHONG_CO_DU_LIEU} (gia lap, ky vong 422 KHONG_CO_DU_LIEU_HO)")
            try:
                await preview_uc.execute(tram_id=_TRAM_KHONG_CO_DU_LIEU, tram_name="", action="shutdown")
                print("  DUNG: khong raise loi nhu ky vong!")
            except HoNoDataError as e:
                print(f"  OK - HoNoDataError (422 KHONG_CO_DU_LIEU_HO): {e}")
    finally:
        await asyncpg_conn.close()


if __name__ == "__main__":
    asyncio.run(main())
