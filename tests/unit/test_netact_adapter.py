"""
Unit test cho NetActAdapter — MOCK SshExecutor hoan toan, KHONG SSH that.
Tu: TASK_LIST.md B7.3 (chua test SSH that, chi mock truoc - yeu cau user 12072026)

15072026: NetActAdapter gio ghi file XML that + execution.log vao
docs/logs/netact_runs/{DDMMYYYY_HHMM}/ (thay tempfile+os.unlink() truoc day) -
fixture netact_env redirect _PROJECT_ROOT sang tmp_path de test KHONG ghi file
that vao repo that moi lan chay pytest (adapter dung Path(__file__) tinh
duong dan tuyet doi, khong doc tu cwd, nen phai monkeypatch thang bien module).
"""

import os
import re
from unittest.mock import MagicMock, patch

import pytest

from adapters.netact.netact_adapter import (
    NetActAdapter,
    _parse_provision_theo_dn,
    _tom_tat_provision,
)
from domain.errors import SshConnectionError
from domain.value_objects.oss_instance import OssInstance

# SUA 27092026 (Giai doan 1 buoc 2, dinh tuyen OSS theo tung cell) - NetActAdapter
# KHONG con doc NETACT_SERVERS/tu tra cuu credential (chuyen sang OssRouterEnv,
# xem tests/unit/test_oss_router_env.py) - submit_cr() nhan THANG OssInstance.
# 2 test cu "ma_tinh khong co trong NETACT_SERVERS"/"credentials placeholder"
# (raise SshConnectionError) đã CHUYEN sang test_oss_router_env.py (kiem tra
# OssRouterEnv.chon_oss() tra None cho 2 tinh huong do), vi NetActAdapter
# gio KHONG con lam viec nay nua.
_OSS_HNI = OssInstance(instance_id="HNI", host="10.212.242.20", user="test_user", password="test_password")

# DDMMYYYY_HHMM - khop dung format timestamp NetActAdapter._submit_cr_sync() sinh ra
_TIMESTAMP_RE = r"\d{8}_\d{4}"


@pytest.fixture(autouse=True)
def netact_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NETACT_UPLOAD_PATH", "/d/oss/upload/")
    monkeypatch.setenv("NETACT_SSH_TIMEOUT", "30")
    monkeypatch.setenv("NETACT_CMD_TIMEOUT", "120")
    # co lap test khoi docs/logs/netact_runs/ that cua repo - xem docstring dau file
    monkeypatch.setattr("adapters.netact.netact_adapter._PROJECT_ROOT", tmp_path)
    return tmp_path


def _fake_executor(exec_command_results: list[tuple[int, str, str]]) -> MagicMock:
    executor = MagicMock()
    executor.exec_command.side_effect = exec_command_results
    return executor


async def test_import_va_provision_deu_ok_tra_ve_true_dung_thu_tu(tmp_path):
    adapter = NetActAdapter()
    # 3 exec_command: mkdir remote, Import, Provision (dung thu tu)
    # SUA 18082026: provision stdout PHAI la output THAT (co block DN +
    # "Status received: Finished"). Chuoi gia "Provision OK" truoc day duoc
    # coi la thanh cong vi ban cu chi kiem "khong co keyword loi" - dung cai
    # lo hong "provision khong in gi ma exit 0 van thanh cong".
    _PROVISION_OK = """Status received: Started
Feedback received:
    DN: PLMN-PLMN/MRBTS-160000
    STATUS            : SUCCESS
    SUCCESSFUL MOS    : 3
    FAILED MOS        : 0
Status received: Finished"""
    fake_executor = _fake_executor([(0, "", ""), (0, "Import OK", ""), (0, _PROVISION_OK, "")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "R012_NQMProactiveCC_160000_x", "R012_backup_160000_x", oss=_OSS_HNI)

    assert result["ok"] is True
    fake_executor.connect.assert_called_once_with("10.212.242.20", "test_user", "test_password", timeout=30)
    fake_executor.sftp_upload.assert_called_once()
    local_path, remote_path = fake_executor.sftp_upload.call_args[0]
    assert re.fullmatch(rf"/d/oss/upload/{_TIMESTAMP_RE}/R012_NQMProactiveCC_160000_x\.xml", remote_path)
    # file XML gio ghi vinh vien vao docs/logs/netact_runs/{timestamp}/ - KHONG con xoa nhu tempfile truoc day
    assert os.path.exists(local_path)
    assert local_path.startswith(str(tmp_path))

    assert fake_executor.exec_command.call_count == 3
    mkdir_cmd = fake_executor.exec_command.call_args_list[0][0][0]
    import_cmd = fake_executor.exec_command.call_args_list[1][0][0]
    provision_cmd = fake_executor.exec_command.call_args_list[2][0][0]
    assert mkdir_cmd.startswith("mkdir -p /d/oss/upload/") and re.search(_TIMESTAMP_RE, mkdir_cmd)
    assert "-op Import" in import_cmd and "R012_NQMProactiveCC_160000_x" in import_cmd
    assert "-op Provision" in provision_cmd and "R012_backup_160000_x" in provision_cmd

    # execution.log phai duoc tao cung thu muc voi file XML
    run_dir = os.path.dirname(local_path)
    assert os.path.exists(os.path.join(run_dir, "execution.log"))

    fake_executor.close.assert_called_once()


async def test_import_fail_exit_code_khac_0_dung_ngay_khong_chay_provision():
    adapter = NetActAdapter()
    # mkdir OK, Import fail
    fake_executor = _fake_executor([(0, "", ""), (1, "", "some error")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    assert result["ok"] is False
    assert fake_executor.exec_command.call_count == 2  # mkdir + Import, Provision KHONG duoc goi
    fake_executor.close.assert_called_once()  # van cleanup


async def test_import_exit_code_0_nhung_co_error_keyword_van_tinh_la_fail():
    adapter = NetActAdapter()
    # mkdir OK, Import "thanh cong" ve exit_code nhung co keyword ERROR
    fake_executor = _fake_executor([(0, "", ""), (0, "Something ERROR happened", "")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    assert result["ok"] is False
    assert fake_executor.exec_command.call_count == 2


async def test_provision_thanh_cong_that_co_dong_FAILED_MOS_0_khong_bi_hieu_nham_la_fail():
    # Bug that phat hien tren CR session #194 (13072026, tram 110548): output
    # that cua racclimx.sh Provision THANH CONG co dong dem "FAILED MOS : 0"
    # lap lai nhieu lan (1 lan/DN) - truoc day bi hieu nham la loi vi substring
    # "FAILED" khop nham. Phai tra True vi day la thanh cong that.
    adapter = NetActAdapter()
    provision_stdout = (
        "Status received: Started\n"
        "Feedback received:\n"
        "\tDN: PLMN-PLMN/MRBTS-114820\n"
        "\tOperation succeeds.\n"
        "\tSTATUS            : SUCCESS\n"
        "\tSUCCESSFUL MOS    : 3\n"
        "\tFAILED MOS        : 0\n"
        "Feedback received:\n"
        "\tDN: PLMN-PLMN/MRBTS-112761\n"
        "\tOperation succeeds.\n"
        "\tSTATUS            : SUCCESS\n"
        "\tSUCCESSFUL MOS    : 1\n"
        "\tFAILED MOS        : 0\n"
        "Operation report.\n"
        "Details: Plan provisioning was successful for all MRBTSs in the operation scope.\n"
        "Status received: Finished"
    )
    # mkdir OK, Import OK, Provision (dong dem FAILED MOS : 0 khong bi hieu nham)
    fake_executor = _fake_executor([(0, "", ""), (0, "Import OK", ""), (0, provision_stdout, "")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    assert result["ok"] is True


async def test_provision_that_bai_that_FAILED_MOS_lon_hon_0_van_tra_ve_false():
    adapter = NetActAdapter()
    provision_stdout = (
        "Feedback received:\n"
        "\tDN: PLMN-PLMN/MRBTS-114820\n"
        "\tOperation fails.\n"
        "\tSTATUS            : SUCCESS\n"
        "\tSUCCESSFUL MOS    : 2\n"
        "\tFAILED MOS        : 1\n"
    )
    fake_executor = _fake_executor([(0, "", ""), (0, "Import OK", ""), (0, provision_stdout, "")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    assert result["ok"] is False


async def test_import_ok_provision_fail_tra_ve_false():
    adapter = NetActAdapter()
    # mkdir OK, Import OK, Provision fail
    fake_executor = _fake_executor([(0, "", ""), (0, "Import OK", ""), (1, "", "provision failed")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        result = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    assert result["ok"] is False
    assert fake_executor.exec_command.call_count == 3
    fake_executor.close.assert_called_once()


async def test_loi_ha_tang_tu_ssh_executor_propagate_khong_bi_nuot_thanh_false():
    adapter = NetActAdapter()
    fake_executor = MagicMock()
    fake_executor.connect.side_effect = SshConnectionError("khong ket noi duoc", host="10.212.242.20")

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        with pytest.raises(SshConnectionError):
            await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    fake_executor.close.assert_called_once()  # finally van chay du connect loi


async def test_ssh_mkdir_remote_that_bai_raise_khong_chay_sftp_upload(tmp_path):
    # mkdir -p that bai (vd quyen thu muc) - phai raise SshConnectionError,
    # KHONG duoc am tham tiep tuc SFTP upload vao thu muc co the chua ton tai
    adapter = NetActAdapter()
    fake_executor = _fake_executor([(1, "", "Permission denied")])

    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        with pytest.raises(SshConnectionError):
            await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    fake_executor.sftp_upload.assert_not_called()
    fake_executor.close.assert_called_once()  # finally van chay du mkdir loi

    # execution.log van phai duoc ghi ke ca khi loi giua chung (try/finally)
    log_files = list(tmp_path.rglob("execution.log"))
    assert len(log_files) == 1
    assert "SSH mkdir remote that bai" in log_files[0].read_text(encoding="utf-8")


# === PARSE PROVISION THEO TUNG DN + PARTIAL_SUCCESS (18082026) ===

_STDOUT_18_08 = """Status received: Started
5G/LTE/SRAN plan provision started
Feedback received:
    DN: PLMN-PLMN/MRBTS-116952
    Type: Info
    Operation succeeds.
    STATUS            : SUCCESS
    SUCCESSFUL MOS    : 1
    FAILED MOS        : 0
Feedback received:
    DN: PLMN-PLMN/MRBTS-113975
    Type: Info
    STATUS            : SUCCESS
    SUCCESSFUL MOS    : 4
    FAILED MOS        : 0
Feedback received:
    DN: PLMN-PLMN/MRBTS-112685
    Type: Info
    STATUS            : SUCCESS
    SUCCESSFUL MOS    : 1
    FAILED MOS        : 0
Feedback received:
    DN: PLMN-PLMN/MRBTS-113508
    Type: Error
    5G/LTE/SRAN plan provision failed.
    Details: java.net.NoRouteToHostException: No route to host
    SUCCESSFUL MOS    : 0
    FAILED MOS        : 6
Status received: Finished"""


def _stdout_n_dn(so_ok: int, so_loi: int) -> str:
    khoi = ["Status received: Started"]
    for i in range(so_ok):
        khoi += ["Feedback received:", f"    DN: PLMN-PLMN/MRBTS-{100 + i}",
                 "    STATUS            : SUCCESS", "    SUCCESSFUL MOS    : 2",
                 "    FAILED MOS        : 0"]
    for i in range(so_loi):
        khoi += ["Feedback received:", f"    DN: PLMN-PLMN/MRBTS-{200 + i}",
                 "    Type: Error", "    Details: No route to host",
                 "    SUCCESSFUL MOS    : 0", "    FAILED MOS        : 2"]
    khoi.append("Status received: Finished")
    return chr(10).join(khoi)


class TestParseTheoDN:
    def test_output_that_18_08_ra_3_ok_1_loi(self):
        dn = _parse_provision_theo_dn(_STDOUT_18_08)
        assert len(dn) == 4
        assert [d["thanh_cong"] for d in dn] == [True, True, True, False]
        assert [d["dn"].rsplit("/", 1)[-1] for d in dn] == [
            "MRBTS-116952", "MRBTS-113975", "MRBTS-112685", "MRBTS-113508",
        ]
        loi = dn[3]
        assert loi["so_mo_that_bai"] == 6
        assert "NoRouteToHostException" in loi["ly_do_loi"]

    def test_tom_tat_dung_dinh_dang_ghi_cr_log(self):
        tom_tat = _tom_tat_provision(_parse_provision_theo_dn(_STDOUT_18_08))
        assert tom_tat.splitlines()[0] == "Provision 3/4 DN thanh cong (6/12 MO)"
        assert "OK   MRBTS-116952 (1 MO)" in tom_tat
        assert "LOI  MRBTS-113508 (0/6 MO): java.net.NoRouteToHostException" in tom_tat

    def test_STATUS_FAILURE_PHAI_bat_duoc(self):
        # Blacklist cu BO SOT: "FAILURE" != "FAILED" nen loi that lot qua thanh
        # cong. Whitelist bat duoc vi status != SUCCESS.
        out = chr(10).join([
            "Feedback received:", "    DN: PLMN-PLMN/MRBTS-1",
            "    STATUS            : FAILURE", "    FAILED MOS        : 0",
        ])
        dn = _parse_provision_theo_dn(out)
        assert dn[0]["thanh_cong"] is False
        assert "FAILURE" in dn[0]["ly_do_loi"]

    def test_thieu_dong_dem_FAILED_MOS_la_that_bai(self):
        # Whitelist: vang mat dau hieu duong = that bai. KHONG suy dien
        # "khong thay loi tuc la khong loi".
        out = chr(10).join([
            "Feedback received:", "    DN: PLMN-PLMN/MRBTS-1",
            "    STATUS            : SUCCESS",
        ])
        assert _parse_provision_theo_dn(out)[0]["thanh_cong"] is False


class TestChuoiVoHaiKhongGayFail:
    def test_cac_chuoi_tung_gay_bao_loi_oan_gio_khong_con(self):
        # Day la nhung chuoi lam blacklist cu bao HONG oan tren CR THANH CONG.
        for vo_hai in [
            "    0 errors",
            "    No errors found",
            "    FAILED MRBTS      : 0",
            "    FAILED  MOS       : 0",
            "    Operation finished without error",
        ]:
            out = chr(10).join([
                "Feedback received:", "    DN: PLMN-PLMN/MRBTS-1",
                "    STATUS            : SUCCESS", "    SUCCESSFUL MOS    : 2",
                "    FAILED MOS        : 0", vo_hai,
            ])
            dn = _parse_provision_theo_dn(out)
            assert dn[0]["thanh_cong"] is True, f"bi bao loi oan boi: {vo_hai!r}"

    def test_FAILED_MOS_nhieu_dau_cach_van_doc_duoc_so(self):
        # Regex cu dung dau cach CUNG nen "FAILED  MOS" khong khop -> lot xuong
        # blacklist -> bao loi oan. Gio dung \s+.
        out = chr(10).join([
            "Feedback received:", "    DN: PLMN-PLMN/MRBTS-1",
            "    STATUS            : SUCCESS", "    SUCCESSFUL   MOS   : 2",
            "    FAILED   MOS      : 3",
        ])
        dn = _parse_provision_theo_dn(out)
        assert dn[0]["so_mo_that_bai"] == 3
        assert dn[0]["thanh_cong"] is False


class TestTrangThaiTongHop:
    async def _chay(self, provision_stdout, exit_code=0):
        adapter = NetActAdapter()
        fake = _fake_executor([(0, "", ""), (0, "Import OK", ""), (exit_code, provision_stdout, "")])
        with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake):
            return await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)

    async def test_3_ok_1_loi_ra_PARTIAL_SUCCESS(self):
        kq = await self._chay(_STDOUT_18_08)
        assert kq["trang_thai"] == "PARTIAL_SUCCESS"
        assert kq["ok"] is True  # CR van tiep tuc - 3 tram DA doi that
        assert len(kq["dn_list"]) == 4

    async def test_tat_ca_OK_ra_DONE(self):
        kq = await self._chay(_stdout_n_dn(so_ok=4, so_loi=0))
        assert kq["trang_thai"] == "DONE"
        assert kq["buoc_loi"] is None

    async def test_tat_ca_LOI_ra_FAILED(self):
        kq = await self._chay(_stdout_n_dn(so_ok=0, so_loi=4))
        assert kq["trang_thai"] == "FAILED"
        assert kq["ok"] is False

    async def test_thieu_Status_received_Finished_la_that_bai_cap_toan_lenh(self):
        # Lenh CHUA CHAY XONG (timeout/dut SSH) - KHAC "chay xong nhung co DN
        # loi". Khong duoc bao PARTIAL_SUCCESS: ta khong biet DN chua co
        # feedback da doi hay chua.
        thieu = _stdout_n_dn(so_ok=3, so_loi=0).replace("Status received: Finished", "")
        kq = await self._chay(thieu)
        assert kq["trang_thai"] == "FAILED"
        assert "chua chay xong" in kq["tom_tat"]
        assert kq["dn_list"] == []

    async def test_provision_khong_in_gi_ma_exit_0_KHONG_con_lot(self):
        # Lo hong cu: blacklist khong thay keyword nao -> bao thanh cong.
        kq = await self._chay("")
        assert kq["trang_thai"] == "FAILED"

    async def test_import_hong_thi_buoc_loi_la_import(self):
        adapter = NetActAdapter()
        fake = _fake_executor([(0, "", ""), (1, "", "loi")])
        with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake):
            kq = await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=_OSS_HNI)
        assert kq["buoc_loi"] == "import"
        assert "CHUA chay Provision" in kq["tom_tat"]


async def test_loi_ket_noi_ssh_chi_ghi_ten_na_khong_lo_host_ip():
    # THEM 23/10/2026 - cau loi len cr_log/API: ten NA, KHONG host/IP (ke ca IP
    # nam trong text exception cua paramiko).
    oss = OssInstance(instance_id="NA14", host="10.212.247.20", user="u", password="p")
    adapter = NetActAdapter()
    fake_executor = MagicMock()
    fake_executor.connect.side_effect = SshConnectionError(
        "Khong ket noi duoc NetAct SSH 10.212.247.20: Unable to connect to port 22 on 10.212.247.20",
        host="10.212.247.20",
    )
    with patch("adapters.netact.netact_adapter.SshExecutor", return_value=fake_executor):
        with pytest.raises(SshConnectionError) as exc:
            await adapter.submit_cr("<xml/>", "plan_1", "backup_1", oss=oss)
    assert "NA14" in str(exc.value) and "10.212." not in str(exc.value)
    assert "host" not in exc.value.context
