"""
Unit test cho SshExecutor — MOCK paramiko.SSHClient hoan toan, KHONG SSH that.
Tu: TASK_LIST.md B7.2 (chua test SSH that, chi mock truoc - yeu cau user 12072026)
"""

from unittest.mock import MagicMock, call, patch

import pytest

from adapters.netact.ssh_executor import SshExecutor
from domain.errors import SshConnectionError


def _make_exec_result(exit_code: int, out: str = "", err: str = ""):
    stdout = MagicMock()
    stdout.channel.recv_exit_status.return_value = exit_code
    stdout.read.return_value = out.encode()
    stderr = MagicMock()
    stderr.read.return_value = err.encode()
    return MagicMock(), stdout, stderr  # stdin, stdout, stderr


@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_connect_goi_dung_tham_so_va_auto_add_policy(mock_ssh_client_cls):
    mock_ssh = mock_ssh_client_cls.return_value
    executor = SshExecutor()

    executor.connect("10.212.242.20", "thembv", "secret", timeout=30)

    mock_ssh.set_missing_host_key_policy.assert_called_once()
    mock_ssh.connect.assert_called_once_with(
        hostname="10.212.242.20",
        username="thembv",
        password="secret",
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
    )


@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_connect_fail_raise_sshconnectionerror(mock_ssh_client_cls):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_ssh.connect.side_effect = Exception("timed out")
    executor = SshExecutor()

    with pytest.raises(SshConnectionError):
        executor.connect("10.212.242.20", "thembv", "secret")


@patch("adapters.netact.ssh_executor.time.sleep")
@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_sftp_upload_thanh_cong_lan_dau_khong_retry(mock_ssh_client_cls, mock_sleep):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_sftp = mock_ssh.open_sftp.return_value
    executor = SshExecutor()
    executor.connect("host", "user", "pass")

    executor.sftp_upload("/tmp/local.xml", "/remote/path.xml")

    mock_sftp.put.assert_called_once_with("/tmp/local.xml", "/remote/path.xml")
    mock_sleep.assert_not_called()


@patch("adapters.netact.ssh_executor.time.sleep")
@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_sftp_upload_fail_2_lan_dau_thanh_cong_lan_3(mock_ssh_client_cls, mock_sleep):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_sftp = mock_ssh.open_sftp.return_value
    mock_sftp.put.side_effect = [Exception("fail1"), Exception("fail2"), None]
    executor = SshExecutor()
    executor.connect("host", "user", "pass")

    executor.sftp_upload("/tmp/local.xml", "/remote/path.xml")  # khong raise

    assert mock_sftp.put.call_count == 3
    mock_sleep.assert_has_calls([call(1), call(2)])


@patch("adapters.netact.ssh_executor.time.sleep")
@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_sftp_upload_fail_ca_3_lan_raise_sshconnectionerror(mock_ssh_client_cls, mock_sleep):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_sftp = mock_ssh.open_sftp.return_value
    mock_sftp.put.side_effect = Exception("always fail")
    executor = SshExecutor()
    executor.connect("host", "user", "pass")

    with pytest.raises(SshConnectionError):
        executor.sftp_upload("/tmp/local.xml", "/remote/path.xml")

    assert mock_sftp.put.call_count == 3


@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_exec_command_tra_ve_tuple_exit_code_stdout_stderr(mock_ssh_client_cls):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_ssh.exec_command.return_value = _make_exec_result(0, out="OK done", err="")
    executor = SshExecutor()
    executor.connect("host", "user", "pass")

    exit_code, out, err = executor.exec_command("racclimx.sh -op Import", timeout=120)

    assert exit_code == 0
    assert out == "OK done"
    assert err == ""
    mock_ssh.exec_command.assert_called_once_with("racclimx.sh -op Import", timeout=120)


@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_exec_command_khong_retry_khi_fail(mock_ssh_client_cls):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_ssh.exec_command.side_effect = Exception("connection lost")
    executor = SshExecutor()
    executor.connect("host", "user", "pass")

    with pytest.raises(SshConnectionError):
        executor.exec_command("racclimx.sh -op Import")

    mock_ssh.exec_command.assert_called_once()  # KHONG retry (tac dong live network)


@patch("adapters.netact.ssh_executor.paramiko.SSHClient")
def test_close_dong_ca_sftp_va_ssh(mock_ssh_client_cls):
    mock_ssh = mock_ssh_client_cls.return_value
    mock_sftp = mock_ssh.open_sftp.return_value
    executor = SshExecutor()
    executor.connect("host", "user", "pass")
    executor.sftp_upload("/tmp/local.xml", "/remote/path.xml")

    executor.close()

    mock_sftp.close.assert_called_once()
    mock_ssh.close.assert_called_once()


def test_close_an_toan_khi_chua_connect():
    executor = SshExecutor()
    executor.close()  # khong raise
