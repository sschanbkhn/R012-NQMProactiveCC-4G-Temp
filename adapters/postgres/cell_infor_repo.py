"""
CellInforRepo — doc du lieu tham chieu tu bang cell_infor (Admin CLI export).
Tu: quyet dinh 12/07/2026 — match bang LIKE tren dn_fdd/dn_sib, khong dua
vao dn_lncel cua cell_infor (co the lech dong voi dn_fdd/dn_sib cung dong).

upsert_from_csv() them o C2.6 (13072026, Nhom 2) - boc lai NGUYEN VEN logic
(parser read_csv() + SQL upsert) tu adapters/netact/import_4G_cell_infor.py
(script da chay that thanh cong 27763 dong) - chi doi tu asyncpg.connect()
rieng cua script sang self._conn duoc DI (khop pattern cua repo nay).
"""

from pathlib import Path

from adapters.netact.import_4G_cell_infor import read_csv
from domain.ports.outbound.repo_ports import ICellInforRepo
from domain.services.dist_name import LNBTS_LNCEL_RE
from domain.value_objects.rsboost_level import RsboostLevel
from domain.value_objects.qrxlevmin import Qrxlevmin


class CellInforRepo(ICellInforRepo):
    def __init__(self, conn):
        self._conn = conn  # asyncpg connection/pool

    async def get_rsboost_by_neighbor_dns(
        self, neighbor_dns: list[str]
    ) -> dict[str, RsboostLevel]:
        result: dict[str, RsboostLevel] = {}
        for dn in neighbor_dns:
            pattern = f"{dn}/LNCEL_FDD%"
            rows = await self._conn.fetch(
                "SELECT dn_fdd, rsboost_current FROM system_nsn_nqmproactivecc.cell_infor "
                "WHERE dn_fdd LIKE $1",
                pattern,
            )
            if not rows:
                continue  # khong tim thay -> use case tu xu ly case "chua sync"
            if len(rows) > 1:
                # nhieu dong cell_infor cung match 1 neighbor_dn - du lieu nguon
                # co the trung/loi. Lay dong dau, nhung phai canh bao ro rang
                # thay vi am tham chon sai.
                print(
                    f"[WARN] {len(rows)} dong cell_infor cung match dn_fdd cho "
                    f"neighbor {dn} — dang lay dong dau tien: {[r['dn_fdd'] for r in rows]}"
                )
            row = rows[0]
            if row["rsboost_current"] is None:
                continue
            # C1.4-fix12 (21072026) - GIU NGUYEN gia tri that tu DB (vd 1.77),
            # KHONG snap ve RSBOOST_SCALE khi doc - do la dB THAT dang chay
            # tren mang, RsboostLevel constructor chap nhan gia tri bat ky
            # (xem domain/value_objects/rsboost_level.py). Chi RsboostLevel.
            # next_level() moi snap ve buoc chuan, va CHI khi tinh gia tri MOI.
            result[dn] = RsboostLevel(float(row["rsboost_current"]))
        return result

    async def get_qrxlevmin_by_neighbor_dns(
        self, neighbor_dns: list[str]
    ) -> dict[str, Qrxlevmin]:
        result: dict[str, Qrxlevmin] = {}
        for dn in neighbor_dns:
            pattern = f"{dn}/SIB%"
            rows = await self._conn.fetch(
                "SELECT dn_sib, qrxlevmin_current FROM system_nsn_nqmproactivecc.cell_infor "
                "WHERE dn_sib LIKE $1",
                pattern,
            )
            if not rows:
                continue
            if len(rows) > 1:
                print(
                    f"[WARN] {len(rows)} dong cell_infor cung match dn_sib cho "
                    f"neighbor {dn} — dang lay dong dau tien: {[r['dn_sib'] for r in rows]}"
                )
            row = rows[0]
            if row["qrxlevmin_current"] is None:
                continue
            result[dn] = Qrxlevmin(row["qrxlevmin_current"])

        return result

    async def get_dn_map_theo_enb_lcr(self) -> dict[tuple[int, int], dict]:
        # BUOC 4b (08/10/2026) - xem chu y day du trong
        # domain/ports/outbound/repo_ports.py::ICellInforRepo. Tai TOAN BO
        # bang (~87.913 dong, da do thuc te) 1 LAN - re hon N truy van rieng
        # theo (enb,lcr) khi mot phien xem truoc/chay CR can tra cuu NHIEU
        # cap cung luc (ca danh sach A + B).
        #
        # SUA 10/10/2026 (yeu cau truc tiep user): tra cuu theo LNBTS (KHONG
        # phai MRBTS) - "enb" trong ho_neighbor.target_enb giai ma tu ECI
        # CHINH LA LNBTS, da chung minh bang toan hoc (eNB ID ECI toi da 20
        # bit = 1.048.575, MRBTS co the vuot qua gia tri nay) + du lieu that
        # (xem domain/services/dist_name.py::LNBTS_LNCEL_RE). Truoc sua dung
        # MRBTS lam mat 223/27.202 cap NA09 vendor NOKIA (2,67% dong cell_infor
        # co MRBTS != LNBTS).
        rows = await self._conn.fetch(
            "SELECT dn_lncel, cell_name FROM system_nsn_nqmproactivecc.cell_infor"
        )
        ket_qua: dict[tuple[int, int], dict] = {}
        for row in rows:
            m = LNBTS_LNCEL_RE.search(row["dn_lncel"] or "")
            if not m:
                continue  # dn_lncel khong dung mau - bo qua, KHONG raise (xem port)
            enb, lcr = int(m.group(1)), int(m.group(2))
            ket_qua[(enb, lcr)] = {"dn_lncel": row["dn_lncel"], "cell_name": row["cell_name"]}
        return ket_qua

    async def upsert_from_csv(self, file_path: str) -> int:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"Khong tim thay file: {file_path}")

        rows = read_csv(path)
        if not rows:
            return 0

        # SQL y nguyen tu adapters/netact/import_4G_cell_infor.py::upsert_all()
        # (da chay that thanh cong) - KHONG doi logic, chi doi nguon connection.
        upsert_sql = """
            INSERT INTO system_nsn_nqmproactivecc.cell_infor
                (dn_lncel, name, cell_name, dn_fdd, rsboost_current,
                 dn_sib, qrxlevmin_current, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (dn_lncel) DO UPDATE SET
                name = EXCLUDED.name,
                cell_name = EXCLUDED.cell_name,
                dn_fdd = EXCLUDED.dn_fdd,
                rsboost_current = EXCLUDED.rsboost_current,
                dn_sib = EXCLUDED.dn_sib,
                qrxlevmin_current = EXCLUDED.qrxlevmin_current,
                updated_at = now()
        """
        args = [
            (r["dn_lncel"], r["name"], r["cell_name"], r["dn_fdd"],
             r["rsboost_current"], r["dn_sib"], r["qrxlevmin_current"])
            for r in rows
        ]
        async with self._conn.transaction():
            await self._conn.executemany(upsert_sql, args)
        return len(rows)
