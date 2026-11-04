"""
RA SOAT PHIEU THUA - CHI DOC, KHONG SUA GI.

Boi canh: truoc 16082026, tieu chi xuat phieu CHI xet delta
(avg_after - avg_before < threshold -> KHONG DAT -> xuat phieu). Tu 16082026 co
them ve "avg_after >= MUC_TOT (4.0) -> van DAT" (domain/services/
evaluation_service.py). Nghia la cell "tut qua dung sai NHUNG chat luong con lai
van tot" da tung bi danh FAIL va CO THE DA XUAT PHIEU THUA len TTS.

Script nay tinh lai QoS cua tung phieu THAT da xuat, doi chieu LUAT CU vs LUAT
MOI, va chi ra phieu nao la THUA.

=== AN TOAN ===
- CHI SELECT. KHONG INSERT/UPDATE/DELETE bat ky bang nao.
- KHONG goi SaveCellClm (WRITE API tao phieu that tren TTS). Chi goi CTS de DOC
  QoS (read-only), qua dung duong ma XuatPhieuUseCase dung.
- Ket qua chi de NGUOI doc va quyet dinh - script khong tu xu ly gi.

Chay:
    python scripts/ra_soat_phieu_thua.py
    python scripts/ra_soat_phieu_thua.py --phieu 19207 19428 19652
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

from adapters.http.cts_http_adapter import CtsHttpAdapter
from application.get_qos_sparkline_use_case import GetQosSparklineUseCase

# Dung LAI dung 2 thu XuatPhieuUseCase dung, KHONG chep lai cong thuc:
#   _daily_averages          - gop diem hourly cua CTS thanh 1 TB/ngay
#   _XUAT_PHIEU_QOS_THRESHOLD_DELTA - dung sai -0.2 rieng cua xuat phieu
# Import ten "private" (_) la CO Y: chep lai se co ngay lech voi production va
# ra soat se cho ket qua sai - dieu toi ky trong mot script dung de ket luan
# "phieu nay thua".
from application.xuat_phieu_use_case import (  # noqa: PLC2701
    _XUAT_PHIEU_QOS_THRESHOLD_DELTA,
    _daily_averages,
)
from domain.services.evaluation_service import MUC_TOI_THIEU, EvaluationService

load_dotenv()

SCHEMA = "system_nsn_nqmproactivecc"

# Tien to du lieu test - BO QUA, khong phai phieu that tren TTS.
# "TEST_UI_" theo scripts/cleanup_ui_test_data.py; "MOCK" theo
# scripts/seed_mock_process_data.py.
#
# PHAI loc tren CA HAI cot (phat hien khi chay that 16082026): du lieu mock dat
# tien to o PHIEU_ID ("MOCK-90001") con cell_name thi trong nhu that
# ("4G-LDG999M11-HNI"). Loc moi cell_name -> 24 dong mock lot vao bang ra soat.
TIEN_TO_BO_QUA = ("TEST_UI_%", "MOCK%")

_GMT7 = timezone(timedelta(hours=7))


def _to_gmt7(dt) -> datetime:
    """Doi executed_at sang gio VN - GIONG _to_gmt7() cua XuatPhieuUseCase.

    Khac 1 diem: chap nhan CA datetime naive (UTC ngam dinh, du lieu cu) LAN
    aware (cot TIMESTAMPTZ sau C1.4-fix10, asyncpg tra ve aware). Ban trong
    use case chi xu ly naive vi repo cua no da chuan hoa san; o day doc THANG
    tu asyncpg nen phai tu lo.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_GMT7)


async def lay_phieu_that(conn, phieu_ids: list[str] | None) -> list[dict]:
    """Doc cac dong cr_phieu la PHIEU THAT da len TTS.

    Dieu kien: trang_thai=SUCCESS VA phieu_id khong rong. Chi 1 trong 2 la
    khong du - dong SUCCESS ma phieu_id rong nghia la chua trich duoc id tu
    response CTS, khong doi chieu duoc voi phieu that.
    """
    sql = f"""
        SELECT p.id, p.phieu_id, p.cell_name, p.cr_session_id,
               p.created_at, s.executed_at, s.tram_id
        FROM {SCHEMA}.cr_phieu p
        JOIN {SCHEMA}.cr_session s ON s.id = p.cr_session_id
        WHERE p.trang_thai = 'SUCCESS'
          AND p.phieu_id IS NOT NULL
          AND btrim(p.phieu_id) <> ''
          AND p.cell_name NOT LIKE $1
          AND p.cell_name NOT LIKE $2
          AND p.phieu_id NOT LIKE $1
          AND p.phieu_id NOT LIKE $2
    """
    params = list(TIEN_TO_BO_QUA)
    if phieu_ids:
        sql += " AND p.phieu_id = ANY($3)"
        params.append(phieu_ids)
    sql += " ORDER BY p.phieu_id"

    return [dict(r) for r in await conn.fetch(sql, *params)]


async def danh_gia_lai(sparkline: GetQosSparklineUseCase, cell_name: str, executed_at) -> dict:
    """Tinh lai QoS truoc/sau CR cho 1 cell va cham diem theo CA HAI luat.

    Cua so T-7..T-1 / T+1..T+7 sao chep dung cach tinh cua
    XuatPhieuUseCase._danh_gia_qos_cell() (ngay lich GMT+7 cua executed_at).
    """
    executed_at_vn = _to_gmt7(executed_at)
    cr_day_start = datetime(executed_at_vn.year, executed_at_vn.month, executed_at_vn.day)

    before_from, before_to = cr_day_start - timedelta(days=7), cr_day_start - timedelta(days=1)
    after_from, after_to = cr_day_start + timedelta(days=1), cr_day_start + timedelta(days=7)

    before_points = await sparkline.execute(cell_name, from_dt=before_from, to_dt=before_to)
    after_points = await sparkline.execute(cell_name, from_dt=after_from, to_dt=after_to)

    before_daily = _daily_averages(before_points)
    after_daily = _daily_averages(after_points)

    service = EvaluationService()

    # LUAT MOI - goi binh thuong (muc_tot mac dinh = MUC_TOT).
    moi = service.evaluate(before_daily, after_daily, threshold=_XUAT_PHIEU_QOS_THRESHOLD_DELTA)

    # LUAT CU - CUNG MOT HAM, chi vo hieu hoa ve moi bang muc_tot=+vo cuc
    # (avg_after >= inf khong bao gio dung). Lam vay thay vi viet lai
    # "if delta <= threshold -> PASS" bang tay (SUA 03/10/2026: delta =
    # avg_before - avg_after, DUONG = tut - xem domain/services/
    # evaluation_service.py): dam bao phan con lai cua luat (nguong 5 ngay,
    # cach tinh avg) GIONG HET nhau, khac biet duy nhat dung la ve moi.
    # LUU Y (phat hien 03/10/2026, KHONG sua - ngoai pham vi hom nay):
    # evaluate() hien tai KHONG CON tham so "muc_tot" (da doi ten thanh
    # "muc_toi_thieu" tu 04/09/2026) - dong goi duoi day co the dang raise
    # TypeError tren ban code hien tai. Script nay la CHI DOC/audit, khong
    # nam trong pytest suite, da hong truoc khi co thay doi hom nay.
    cu = service.evaluate(
        before_daily, after_daily, threshold=_XUAT_PHIEU_QOS_THRESHOLD_DELTA, muc_tot=float("inf")
    )

    return {
        "so_ngay_before": len(before_daily),
        "so_ngay_after": len(after_daily),
        "avg_before": moi.avg_before,
        "avg_after": moi.avg_after,
        "diem_thap_nhat_sau": moi.diem_thap_nhat_sau,
        "so_ngay_dat_sau": moi.so_ngay_dat_sau,
        "ket_qua_cu": cu.result,
        "ket_qua_moi": moi.result,
        # THUA = luat cu ket toi (FAIL -> da xuat phieu) nhung luat moi tha
        # (PASS). Chi so sanh dung 2 trang thai nay - INSUFFICIENT_DATA hai ben
        # deu khong ket luan duoc gi.
        "thua": cu.result == "FAIL" and moi.result == "PASS",
    }


def _fmt(v, nd: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def in_bang(rows: list[dict]) -> None:
    headers = [
        "phieu_id", "cell_name", "session", "avg_before", "avg_after",
        "delta", "LUAT CU", "LUAT MOI", "THUA?",
    ]
    data = []
    for r in rows:
        if r.get("loi"):
            data.append([
                r["phieu_id"], r["cell_name"], str(r["cr_session_id"]),
                "-", "-", "-", "LOI", "LOI", f"? ({r['loi']})",
            ])
            continue
        ab, aa = r["avg_before"], r["avg_after"]
        # SUA 03/10/2026: delta = before - after (DUONG = tut), dong bo voi
        # domain/services/evaluation_service.py (truoc day la aa - ab, AM = tut).
        delta = (ab - aa) if (ab is not None and aa is not None) else None
        data.append([
            r["phieu_id"], r["cell_name"], str(r["cr_session_id"]),
            _fmt(ab), _fmt(aa), _fmt(delta),
            r["ket_qua_cu"], r["ket_qua_moi"],
            "*** THUA ***" if r["thua"] else "",
        ])

    widths = [max(len(headers[i]), *(len(row[i]) for row in data)) for i in range(len(headers))]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in data:
        print(" | ".join(c.ljust(widths[i]) for i, c in enumerate(row)))


async def main() -> int:
    p = argparse.ArgumentParser(description="Ra soat phieu xuat THUA theo luat moi (CHI DOC)")
    p.add_argument("--phieu", nargs="*", default=None, help="Loc theo phieu_id cu the")
    args = p.parse_args()

    import os

    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("Thieu DATABASE_URL trong .env")
        return 1

    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=15)
    except Exception as exc:  # noqa: BLE001 - script test
        print(f"KHONG KET NOI DUOC DB: {type(exc).__name__}: {exc}")
        print(f"DSN host: {dsn.split('@')[-1] if '@' in dsn else '?'}")
        return 1

    try:
        phieu = await lay_phieu_that(conn, args.phieu)
    finally:
        await conn.close()

    print(f"So phieu THAT can ra soat: {len(phieu)}")
    if not phieu:
        print("Khong co dong cr_phieu nao thoa dieu kien (SUCCESS + phieu_id khac rong).")
        return 0
    print()

    sparkline = GetQosSparklineUseCase(CtsHttpAdapter())

    ket_qua = []
    for row in phieu:
        try:
            danh_gia = await danh_gia_lai(sparkline, row["cell_name"], row["executed_at"])
            ket_qua.append({**row, **danh_gia})
        except Exception as exc:  # noqa: BLE001 - 1 cell loi KHONG duoc giet ca luot
            print(f"[LOI] {row['phieu_id']} / {row['cell_name']}: {type(exc).__name__}: {exc}")
            ket_qua.append({**row, "loi": type(exc).__name__})

    print()
    in_bang(ket_qua)

    thua = [r for r in ket_qua if r.get("thua")]
    loi = [r for r in ket_qua if r.get("loi")]

    print()
    print("=" * 60)
    print("KET LUAN")
    print("=" * 60)
    print(f"Tong phieu ra soat : {len(ket_qua)}")
    print(f"Khong danh gia duoc: {len(loi)}")
    print(f"PHIEU THUA         : {len(thua)}")
    if thua:
        print()
        print(f"MUC_TOT dang dung = {MUC_TOT}. Cac phieu duoi day theo luat CU la KHONG DAT")
        print("nen da duoc xuat, nhung theo luat MOI la DAT (chat luong con lai van tot)")
        print("-> la phieu THUA, le ra khong can xuat:")
        for r in thua:
            print(
                f"  - phieu {r['phieu_id']} | {r['cell_name']} | session {r['cr_session_id']} "
                f"| avg_after={_fmt(r['avg_after'])} >= {MUC_TOT} "
                f"| diem thap nhat sau={_fmt(r['diem_thap_nhat_sau'])}"
            )
        print()
        print("Script KHONG sua gi. Viec huy/thu hoi phieu tren TTS la quyet dinh cua nguoi")
        print("van hanh - can bao lai team CTS/TTS neu muon xu ly.")
    else:
        print()
        print("KHONG co phieu nao thua - moi phieu da xuat deu van KHONG DAT theo luat moi.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
