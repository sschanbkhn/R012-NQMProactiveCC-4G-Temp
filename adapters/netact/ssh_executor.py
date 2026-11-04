"""
SshExecutor — Paramiko SSH: connect/sftp_upload/exec_command/close toi NetAct.
Tu: API_CONTRACTS.md Section 5; ARCHITECTURE.md Section 5.2; TASK_LIST.md B7.2

Quyet dinh design (xac nhan voi user 12072026):
- Moi loi ha tang (connect fail, SFTP fail sau 3 lan retry, exec_command
  timeout/mat ket noi) deu RAISE SshConnectionError — khong nuot loi thanh
  gia tri sentinel, khop pattern CdsApiError da dung o B6.2. Loi nghiep vu
  cua racclimx.sh (exit_code!=0 hoac ERROR keyword) KHONG xu ly o day — do la
  viec cua NetActAdapter (B7.3) parse tuple (exit_code, stdout, stderr) tra ve.
- sftp_upload() retry 3 lan (backoff 1s/2s/4s, giong pattern CDS B6.2) vi CHUA
  tac dong thiet bi (API_CONTRACTS.md SS5 Buoc 1). exec_command() KHONG retry
  (da gui lenh la khong undo / tac dong live network — API_CONTRACTS.md SS5
  Buoc 2-3).
- SFTP session mo lazy, giu tren self de tai su dung giua cac lan goi
  sftp_upload() (thuc te chi goi 1 lan/CR o B7.3, nhung ho tro nhieu file neu
  can sau nay); close() dong ca sftp lan ssh (yeu cau minh thi cua user).
- paramiko.AutoAddPolicy() dung dung theo API_CONTRACTS.md SS5 (mang noi bo
  VNPT, khong phai host cong khai) — khong tu doi sang policy chat hon.

TODO: CHUA test voi SSH NetAct that (B8.x) — logic connect/upload/exec dung
dung API_CONTRACTS.md SS5, nhung CHUA co bang chung thuc te nhu XML builder
(B7.1) da co. Rui ro chap nhan duoc o buoc nay (user yeu cau code truoc, test
SSH that sau khi da xac nhan an toan).
"""

import logging
import time

import paramiko

from domain.errors import SshConnectionError

logger = logging.getLogger(__name__)

_SFTP_RETRY_DELAYS = [1, 2, 4]  # giong backoff CDS (B6.2)


class SshExecutor:
    def __init__(self):
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def connect(self, host: str, user: str, password: str, timeout: int = 30) -> None:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=host,
                username=user,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
            )
        except Exception as e:
            raise SshConnectionError(f"Khong ket noi duoc NetAct SSH {host}: {e}", host=host) from e
        self._ssh = ssh

    def sftp_upload(self, local_path: str, remote_path: str) -> None:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if self._sftp is None:
                    self._sftp = self._ssh.open_sftp()
                self._sftp.put(local_path, remote_path)
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "SFTP upload fail, retry %d/3", attempt + 1, extra={"remote_path": remote_path}
                )
                # session co the da hong sau loi — bo, mo lai session moi o lan sau
                self._sftp = None
                if attempt < 2:
                    time.sleep(_SFTP_RETRY_DELAYS[attempt])
        raise SshConnectionError(
            f"SFTP upload that bai sau 3 lan retry: {last_error}", remote_path=remote_path
        )

    def exec_command(self, cmd: str, timeout: int = 120) -> tuple[int, str, str]:
        try:
            _stdin, stdout, stderr = self._ssh.exec_command(cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode()
            err = stderr.read().decode()
        except Exception as e:
            raise SshConnectionError(f"exec_command that bai: {e}", cmd=cmd) from e
        return exit_code, out, err

    def close(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None
