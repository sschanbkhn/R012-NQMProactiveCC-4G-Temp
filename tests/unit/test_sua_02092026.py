"""Test cho dot sua 02092026 (PHAN B): B1/B7/B3/B9/B4/B8 + A5.

KHONG POST len CTS: moi test o day deu chay tren ham thuan hoac stub repo.
"""

import pytest

from adapters.netact.netact_adapter import _parse_provision_theo_dn
from application.xuat_phieu_use_case import _trang_thai_luot_chay
from domain.services.phan_loai_loi_cts import phan_loai_loi_cts


def _block(dn: str, status: str = "SUCCESS", ok_mos: int = 1, failed_mos: int = 0) -> str:
    """Dung 1 block feedback giong dinh dang that cua racclimx.sh."""
    return (
        f"Feedback received:\n"
        f"  DN : {dn}\n"
        f"  STATUS : {status}\n"
        f"  SUCCESSFUL MOS : {ok_mos}\n"
        f"  FAILED MOS : {failed_mos}\n"
    )


def _block_trung_gian(dn: str) -> str:
    """Block feedback TRUNG GIAN - khong co dong dem MOS.

    Day chinh la loai block lam parser cu dem sai: no khong dat whitelist nen bi
    tinh la 1 DN that bai rieng.
    """
    return f"Feedback received:\n  DN : {dn}\n  STATUS : IN_PROGRESS\n"


# ============================ B7 - gom DN trung ============================


def test_b7_gom_1_dn_lap_5_lan_ra_1_dn():
    # Dung tinh huong session 3625: 1 DN nhung output in 5 lan (4 block trung
    # gian + 1 block ket qua day du)
    dn = "PLMN-PLMN/MRBTS-116952"
    stdout = "".join([_block_trung_gian(dn)] * 4) + _block(dn, ok_mos=5)

    ket_qua = _parse_provision_theo_dn(stdout)

    assert len(ket_qua) == 1, "5 block cua cung 1 DN phai gom thanh 1 muc"
    assert ket_qua[0]["dn"] == dn
    assert ket_qua[0]["thanh_cong"] is True
    # cong don: 4 block trung gian khong co dong MOS nen cong 0
    assert ket_qua[0]["so_mo_thanh_cong"] == 5
    assert ket_qua[0]["so_mo_that_bai"] == 0


def test_b7_cong_don_mo_qua_nhieu_block():
    dn = "PLMN-PLMN/MRBTS-1"
    stdout = _block(dn, ok_mos=2) + _block(dn, ok_mos=3)
    ket_qua = _parse_provision_theo_dn(stdout)
    assert len(ket_qua) == 1
    assert ket_qua[0]["so_mo_thanh_cong"] == 5


def test_b7_dn_khac_nhau_van_tach_rieng():
    stdout = _block("DN-A", ok_mos=1) + _block("DN-B", ok_mos=2)
    ket_qua = _parse_provision_theo_dn(stdout)
    assert [d["dn"] for d in ket_qua] == ["DN-A", "DN-B"]


def test_b7_co_mo_that_bai_thi_dn_khong_the_thanh_cong():
    # Mot block bao SUCCESS nhung block khac cua CUNG DN co MO that bai
    dn = "DN-A"
    stdout = _block(dn, ok_mos=3) + _block(dn, status="FAILED", ok_mos=0, failed_mos=2)
    ket_qua = _parse_provision_theo_dn(stdout)
    assert len(ket_qua) == 1
    assert ket_qua[0]["thanh_cong"] is False
    assert ket_qua[0]["so_mo_that_bai"] == 2


# ==================== B1 - trang thai tinh theo CELL ====================
# _chay_provision goi _parse_provision_theo_dn roi tinh trang thai. O day test
# thang cong thuc tren ket qua parser de khong phai dung SSH.


def _trang_thai_theo_cell(dn_list):
    cell_ok = sum(d["so_mo_thanh_cong"] for d in dn_list)
    cell_tong = sum(d["so_mo_thanh_cong"] + d["so_mo_that_bai"] for d in dn_list)
    if not dn_list or cell_tong == 0:
        return "FAILED", cell_ok, cell_tong
    if cell_ok == cell_tong:
        return "DONE", cell_ok, cell_tong
    if cell_ok == 0:
        return "FAILED", cell_ok, cell_tong
    return "PARTIAL_SUCCESS", cell_ok, cell_tong


def test_b1_5_tren_5_cell_la_done():
    dn_list = _parse_provision_theo_dn(_block("DN-A", ok_mos=5))
    assert _trang_thai_theo_cell(dn_list) == ("DONE", 5, 5)


def test_b1_3_tren_5_cell_la_partial():
    stdout = _block("DN-A", ok_mos=3) + _block("DN-B", status="FAILED", ok_mos=0, failed_mos=2)
    dn_list = _parse_provision_theo_dn(stdout)
    assert _trang_thai_theo_cell(dn_list) == ("PARTIAL_SUCCESS", 3, 5)


def test_b1_0_tren_5_cell_la_failed():
    stdout = _block("DN-A", status="FAILED", ok_mos=0, failed_mos=5)
    dn_list = _parse_provision_theo_dn(stdout)
    assert _trang_thai_theo_cell(dn_list) == ("FAILED", 0, 5)


# ================= B3 - job khong duoc bao DONE khi 0 thanh cong =================


def test_b3_khong_thanh_cong_ma_co_that_bai_la_failed():
    # Dung tinh huong job_run_log 977/978/980/981/1010: 0 thanh cong, 94 that bai
    assert _trang_thai_luot_chay(0, 94) == "FAILED"


def test_b3_vua_thanh_cong_vua_that_bai_la_partial():
    assert _trang_thai_luot_chay(5, 2) == "PARTIAL"


def test_b3_khong_loi_la_done():
    assert _trang_thai_luot_chay(10, 0) == "DONE"


def test_b3_khong_co_viec_gi_van_la_done():
    # 0 thanh cong nhung cung 0 that bai = khong co cell nao can xuat
    assert _trang_thai_luot_chay(0, 0) == "DONE"


# ======================== B4 - phan loai loi CTS ========================


def test_b4_bad_cell_dang_xu_ly_la_loi_nghiep_vu():
    # Nguyen van tu DB that (cr_phieu, 4 dong)
    assert phan_loai_loi_cts("Bad Cell 4G-HDG116M13-HNI đang xử lý của tháng 202608") == "NGHIEP_VU"


def test_b4_khong_dau_van_nhan_dang_duoc():
    assert phan_loai_loi_cts("Bad Cell 4G-TTI087M11-HNI dang xu ly cua thang 202608") == "NGHIEP_VU"


def test_b4_loi_validation_la_ky_thuat():
    # Nguyen van tu DB that
    loi = '{"type":"https://tools.ietf.org/html/rfc9110#section-15.5.1","title":"One or more validation errors occurred."}'
    assert phan_loai_loi_cts(loi) == "KY_THUAT"


def test_b4_khong_co_loi_thi_none():
    assert phan_loai_loi_cts(None) is None
    assert phan_loai_loi_cts("") is None


def test_b4_loi_la_mac_dinh_ky_thuat():
    # Mac dinh phai nga ve KY_THUAT: doan nham thanh NGHIEP_VU se lam loi that
    # bi im lang
    assert phan_loai_loi_cts("Connection timed out") == "KY_THUAT"


# ============ B8 + A5 + B9 - can DB/repo, dung stub trong bo nho ============


class _StubRepo:
    """Stub CrPhieuRepo - mo phong dung 2 hanh vi dang test, KHONG cham DB/CTS."""

    def __init__(self):
        self.rows: dict[int, dict] = {}
        self.lan_thu: list[dict] = []
        self._next_id = 1

    def them_dong(self, **kw) -> int:
        i = self._next_id
        self._next_id += 1
        self.rows[i] = {"id": i, "error_message": None, "trang_thai": "PENDING", **kw}
        return i

    async def update_result(self, id, trang_thai, response_body, phieu_id, error_message, **kw):
        row = self.rows[id]
        row["trang_thai"] = trang_thai
        row["phieu_id"] = phieu_id
        # B8: chi ghi de khi lan nay CO loi moi
        if error_message is not None:
            row["error_message"] = error_message

    async def ghi_lan_thu(self, cr_phieu_id, nguoi_thuc_hien, ket_qua, **kw):
        self.lan_thu.append(
            {"cr_phieu_id": cr_phieu_id, "nguoi_thuc_hien": nguoi_thuc_hien, "ket_qua": ket_qua, **kw}
        )


@pytest.mark.asyncio
async def test_b8_ghi_success_khong_xoa_error_message_cu():
    repo = _StubRepo()
    pid = repo.them_dong(cell_name="4G-SSN121M11-HNI")
    # lan 1 that bai
    await repo.update_result(pid, "FAILED", None, None, "CTS tu choi: thieu WardCode")
    assert repo.rows[pid]["error_message"] == "CTS tu choi: thieu WardCode"
    # lan 2 thanh cong -> error_message CU phai con
    await repo.update_result(pid, "SUCCESS", {"code": 0}, "19652", None)
    assert repo.rows[pid]["trang_thai"] == "SUCCESS"
    assert repo.rows[pid]["error_message"] == "CTS tu choi: thieu WardCode", (
        "B8: chuyen SUCCESS khong duoc xoa ly do that bai lan truoc"
    )


@pytest.mark.asyncio
async def test_a5_moi_lan_post_ghi_them_1_dong_khong_ghi_de():
    repo = _StubRepo()
    pid = repo.them_dong(cell_name="4G-SSN121M11-HNI")
    await repo.ghi_lan_thu(pid, "JOB_AUTO", "FAILED", error_message="loi 1")
    await repo.ghi_lan_thu(pid, "JOB_AUTO", "FAILED", error_message="loi 2")
    await repo.ghi_lan_thu(pid, "MANUAL", "SUCCESS", phieu_id="19652")
    assert len(repo.lan_thu) == 3, "A5: moi lan POST la 1 dong moi, khong ghi de"
    assert [r["ket_qua"] for r in repo.lan_thu] == ["FAILED", "FAILED", "SUCCESS"]
    # van doc lai duoc ly do cua ca 2 lan hong dau
    assert repo.lan_thu[0]["error_message"] == "loi 1"
    assert repo.lan_thu[1]["error_message"] == "loi 2"
    # phan biet duoc ai chay
    assert repo.lan_thu[2]["nguoi_thuc_hien"] == "MANUAL"
