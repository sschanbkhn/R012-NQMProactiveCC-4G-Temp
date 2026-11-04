"""
NetActAdapter — implement INetActGateway.submit_cr(): orchestrate ghi file XML
local (docs/logs/netact_runs/{timestamp}/) + SSH mkdir remote + SFTP upload +
racclimx.sh Import + racclimx.sh Provision qua SshExecutor.
Tu: API_CONTRACTS.md Section 5; ARCHITECTURE.md Section 5.2; WORKFLOW.md Buoc
13-16; TASK_LIST.md B7.3

Quyet dinh design (xac nhan voi user 12072026):
- submit_cr() them tham so oss: OssInstance (khac ABC goc B2.7 chi co
  xml_content/plan_name/backup_name) - server NetAct la multi-vung (KI-08).
  SUA 27092026 (Giai doan 1 buoc 2): tham so nay TRUOC LA ma_tinh: str, adapter
  tu doc NETACT_SERVERS + tu raise SshConnectionError neu thieu/placeholder.
  Gio viec CHON OSS (theo TUNG CELL, khong phai theo tram tat) da chuyen sang
  OssRouterEnv (adapters/netact/oss_router_env.py, implement IOssRouter) - xem
  file do de biet ly do dinh tuyen doi. Adapter nay CHI con nhan OssInstance
  DA CHON SAN va thuc thi SSH, khong con tu tra cuu/kiem credential.
- Loi ha tang (connect/sftp/exec_command fail) tu SshExecutor (B7.2) RAISE
  SshConnectionError, KHONG bi nuot o day — propagate thang ra ngoai
  submit_cr(), khop pattern CdsApiError (B6.2). return False CHI danh cho loi
  nghiep vu racclimx.sh: script chay duoc (exec_command tra ve tuple binh
  thuong) nhung exit_code!=0 hoac co ERROR keyword — API_CONTRACTS.md SS5
  "Parse Ket Qua SSH".
- SshExecutor (B7.2) la thu vien DONG BO (Paramiko khong ho tro asyncio
  native) nhung INetActGateway.submit_cr() la async (domain/ports/outbound/
  gateway_ports.py). Dung asyncio.to_thread() de khong block event loop
  FastAPI trong luc cho SSH/Import/Provision (co the toi vai phut — SFTP
  retry + Import 120s + Provision 120s). Day la pattern ky thuat chuan cho
  blocking I/O trong app async, khong phai business rule can hoi lai.
- filename = f"{plan_name}.xml" (BUSINESS_RULES.md SS7.2: filename va
  plan_name dung chung 1 prefix, filename chi them ".xml") — khong can tham
  so rieng cho filename.
- Import that bai (return False) → DUNG NGAY, KHONG chay Provision (yeu cau
  user — tranh Provision tren 1 plan Import loi/khong day du).
- KHONG ghi audit_log DB truc tiep trong adapter nay — adapter khong duoc
  inject repo nao (dung logging chuan, infrastructure/logger.py, cho tung
  buoc: connect/sftp_upload/import/provision). audit_log DB thuc su la viec
  cua TriggerCrUseCase (C2.1, chua code) sau khi goi submit_cr() — khop
  pattern da thiet lap o cac adapter B6.x (khong adapter HTTP nao tu ghi
  audit_log ca).
- File XML tam: dung tempfile.NamedTemporaryFile, xoa trong finally (ke ca
  khi loi giua chung) — tranh rac file tam tren local server. (DA THAY —
  xem muc 15072026 ben duoi, quyet dinh doi sang giu file vinh vien).

15072026 (dieu tra session CR that #195, xac nhan voi user): tram 111134
trigger THAT qua FE khong tao duoc folder/log nao vi NetActAdapter truoc day
CHI dung tempfile roi xoa ngay — KHONG co buoc nao ghi XML/log ra dia lau dai
trong production path (chi 2 script test ben ngoai — run_real_cr.py/
checkpoint_real_cr.py — co tu lam viec nay, sai convention va khong duoc
router goi toi). Sua lai NetActAdapter (dung boi ca production path va 2
script test) theo quy uoc CHINH THUC:
- Local: docs/logs/netact_runs/{DDMMYYYY_HHMM}/{filename}.xml + execution.log
- Remote: {NETACT_UPLOAD_PATH}/{DDMMYYYY_HHMM}/{filename}.xml (SSH mkdir -p
  truoc khi SFTP upload, dung lai ket noi SSH da mo o buoc connect())
Timestamp folder dung gio dia phuong VN (GMT+7), KHAC quy uoc luu DB la UTC
(BUSINESS_RULES.md SS7.2) — vi day la TEN THU MUC tren dia de nguoi van hanh
doi chieu thu cong bang mat, khong phai gia tri nghiep vu can dong bo
timezone giua cac he thong.

TODO: CHUA test voi SSH NetAct that (B8.x) — xem TODO tuong tu trong
ssh_executor.py.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from adapters.netact.ssh_executor import SshExecutor
from domain.errors import SshConnectionError
from domain.value_objects.oss_instance import OssInstance
from infrastructure.logger import KeyValueFormatter


def _an_host(thong_bao: str, oss: OssInstance) -> str:
    """Thay host cua OSS bang ten NA trong cau loi tra ra cr_log/API."""
    return thong_bao.replace(oss.host, oss.instance_id) if oss.host else thong_bao

load_dotenv()

logger = logging.getLogger(__name__)

# adapters/netact/netact_adapter.py -> adapters/netact -> adapters -> root
# (3 cap cha) — tinh duong dan tuyet doi docs/logs/netact_runs/ bat ke thu
# muc dang chay lenh (cwd) la o dau
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# === PARSE KET QUA PROVISION THEO TUNG DN (18082026) ===
#
# VI SAO VIET LAI HOAN TOAN: ban cu dung BLACKLIST - quet ca stdout tim 4
# keyword (ERROR/FAILED/Exception/error), co gi khop la coi nhu that bai. Sai
# CA HAI CHIEU, da gay su co that:
#
#   BAO HONG KHI THANH CONG: moi chuoi vo hai chua keyword deu gay fail -
#   "0 errors", "No errors found", "FAILED MRBTS : 0" (regex cu chi go dung
#   "FAILED MOS"), "Operation finished without error". Keyword "error" chu
#   thuong la qua min: no la substring cua "errors", nen MOI cau noi "khong co
#   loi" deu dinh. Bug session #194 (13/07) da va 1 lo (FAILED MOS), CR 18/08
#   lai dinh lo khac - cung mot lop loi.
#
#   BAO THANH CONG KHI HONG: "STATUS : FAILURE" khong khop "FAILED" nen LOT;
#   provision khong in gi ma exit 0 cung LOT.
#
# Va tieu chi da chot tu dau - "phai co Status received: Finished VA FAILED MOS
# : 0" - CHUA BAO GIO duoc cai vao code (chuoi "Status received" truoc 18/08
# chi ton tai trong test fixture).
#
# Nay doi sang WHITELIST theo TUNG DN: chi chap nhan DAU HIEU THANH CONG DUONG,
# vang mat dau hieu = that bai. Blacklist khong bao gio du keyword - luon co
# thong bao loi moi ma ta chua nghi ra; whitelist thi nguoc lai, cai gi la thi
# bi coi la hong, huong an toan.

# Moi DN la 1 block bat dau bang "Feedback received:".
_DN_RE = re.compile(r"DN\s*:\s*(\S+)")
_STATUS_RE = re.compile(r"STATUS\s*:\s*(\w+)")
# \s+ (KHONG phai dau cach cung) giua FAILED/SUCCESSFUL va MOS: NetAct CAN COT
# bang nhieu dau cach, ban cu dung " " cung nen "FAILED  MOS : 0" khong khop ->
# lot xuong blacklist -> bao loi oan.
_SUCCESSFUL_MOS_RE = re.compile(r"SUCCESSFUL\s+MOS\s*:\s*(\d+)")
_FAILED_MOS_RE = re.compile(r"FAILED\s+MOS\s*:\s*(\d+)")
_TYPE_ERROR_RE = re.compile(r"Type\s*:\s*Error", re.IGNORECASE)
_DETAILS_RE = re.compile(r"Details\s*:\s*(.+)")

# Dau hieu lenh CHAY XONG (cap toan lenh, KHONG phai cap DN). Thieu no nghia la
# lenh chua ket thuc - timeout, dut SSH, racclimx chet giua chung. KHAC HAN
# "chay xong nhung co DN loi": mot ben khong biet gi da xay ra, mot ben biet ro.
_HOAN_TAT = "Status received: Finished"

# Blacklist HEP cho Import/mkdir - cac lenh KHONG co cau truc block DN nen
# khong parse whitelist duoc, van can 1 luoi an toan ngoai exit_code.
#
# CHI 2 keyword, va CHI CHU HOA:
#   "ERROR"     - NetAct in ERROR khi that bai that; "0 errors"/"No errors
#                 found" chu thuong KHONG khop (day chinh la qua min cua ban cu)
#   "Exception" - stack trace Java
# DA BO "error" (chu thuong - substring cua "errors", moi cau "khong co loi"
# deu dinh) va "FAILED" (khop nham dong dem "FAILED MRBTS : 0").
_IMPORT_FATAL = ("ERROR", "Exception")


def _parse_provision_theo_dn(stdout: str) -> list[dict]:
    """Tach stdout thanh tung block DN -> danh gia RIENG tung DN.

    Tra list[dict]: {dn, thanh_cong, so_mo_thanh_cong, so_mo_that_bai, ly_do_loi}

    LUAT WHITELIST cho 1 DN duoc coi la THANH CONG - phai DU CA HAI:
        STATUS : SUCCESS   (dung chu SUCCESS, khong phai "khong thay FAILED")
        FAILED MOS : 0     (dem = 0)
    Thieu 1 trong 2, hoac co "Type: Error", deu la THAT BAI.
    """
    # split giu lai noi dung tu "Feedback received:" tro di; phan dau (banner,
    # "provision started"...) khong thuoc DN nao nen bo.
    blocks = stdout.split("Feedback received:")[1:]
    ket_qua = []
    for block in blocks:
        dn_match = _DN_RE.search(block)
        if dn_match is None:
            # Block khong xac dinh duoc DN -> khong the quy trach nhiem cho
            # tram nao. Bo qua thay vi doan bua.
            continue

        status_match = _STATUS_RE.search(block)
        failed_match = _FAILED_MOS_RE.search(block)
        ok_match = _SUCCESSFUL_MOS_RE.search(block)

        so_mo_that_bai = int(failed_match.group(1)) if failed_match else 0
        so_mo_thanh_cong = int(ok_match.group(1)) if ok_match else 0

        # WHITELIST: phai CO status SUCCESS VA co dong dem FAILED MOS = 0.
        # failed_match is None -> KHONG co dong dem -> KHONG du dau hieu duong
        # -> that bai (khong suy dien "khong thay loi tuc la khong loi").
        thanh_cong = (
            status_match is not None
            and status_match.group(1).upper() == "SUCCESS"
            and failed_match is not None
            and so_mo_that_bai == 0
            and not _TYPE_ERROR_RE.search(block)
        )

        ly_do_loi = None
        if not thanh_cong:
            details = _DETAILS_RE.search(block)
            if details:
                ly_do_loi = details.group(1).strip()
            elif status_match:
                ly_do_loi = f"STATUS: {status_match.group(1)}"
            else:
                ly_do_loi = "Khong xac dinh duoc ket qua tu output"

        ket_qua.append(
            {
                "dn": dn_match.group(1),
                "thanh_cong": thanh_cong,
                "so_mo_thanh_cong": so_mo_thanh_cong,
                "so_mo_that_bai": so_mo_that_bai,
                "ly_do_loi": ly_do_loi,
            }
        )
    # B7 (02092026) - GOM cac block CUNG MOT DN lai truoc khi tra ve.
    return _gom_block_trung_dn(ket_qua)


def _gom_block_trung_dn(blocks: list[dict]) -> list[dict]:
    """Gom nhieu block cua CUNG 1 DN thanh 1 muc, cong don so MO.

    === VI SAO CAN (loi that, session 3625) ===
    Output NetAct in LAP LAI cung 1 MRBTS nhieu lan trong 1 luot chay (feedback
    theo tien trinh, khong phai 1 DN 1 block). Parser cu coi moi block la 1 DN
    rieng nen 3 DN that bi tach thanh 15 muc -> bao "3/15 DN thanh cong" trong
    khi 5/5 MO deu OK.
    Hau qua THAT: nguoi dung tuong CR hong, chay lai lan 2 -> sinh session trung
    3626 (da phai xoa tay).

    === BANG CHUNG cua ty le lap 5 lan ===
    17 dong cr_session ghi nhan truoc khi sua deu co dang 3/15, 4/20, 5/25 -
    mau so DUNG GAP 5 LAN tu so, va tu so bang dung so DN that. Tuc la trong 5
    block cua cung 1 DN chi co DUNG 1 block dat whitelist (block feedback cuoi,
    co day du STATUS + dong dem MOS), 4 block con lai la feedback trung gian
    khong co dong dem nen bi tinh la that bai.

    === LUAT GOM ===
    - so_mo_thanh_cong / so_mo_that_bai: CONG DON qua cac block. Cac block trung
      gian khong co dong "SUCCESSFUL MOS"/"FAILED MOS" nen regex khong khop va
      cong vao 0 - tong cuoi cung chinh la so cua block day du, khong bi thoi len.
    - thanh_cong: CO IT NHAT 1 block dat whitelist VA tong FAILED MOS = 0 VA
      khong block nao co "Type: Error".
      KHONG dung "moi block deu phai dat" - do chinh la luat cu va la nguyen nhan
      sinh ra bug: 4/5 block trung gian khong bao gio dat duoc.
      Van giu tinh than whitelist: phai THAY tin hieu SUCCESS duong, va phai
      khong co MO nao that bai; vang mat tin hieu van la that bai.
    - ly_do_loi: giu ly do dau tien tim duoc trong cac block cua DN do.

    === CHUA DOI CHIEU DUOC VOI LOG THAT ===
    docs/logs/netact_runs/ dang RONG (chua co co che luu - chinh la viec A6/B6
    dot nay), nen luat tren suy tu du lieu cr_session chu khong tu doc log NetAct
    that. Sau khi B6 ghi log, PHAI mo 1 file log that ra doi chieu lai.
    """
    theo_dn: dict[str, dict] = {}
    for b in blocks:
        dn = b["dn"]
        if dn not in theo_dn:
            # copy de khong sua vao dict goc cua caller
            theo_dn[dn] = {
                "dn": dn,
                "thanh_cong": b["thanh_cong"],
                "so_mo_thanh_cong": b["so_mo_thanh_cong"],
                "so_mo_that_bai": b["so_mo_that_bai"],
                "ly_do_loi": b["ly_do_loi"],
            }
            continue
        g = theo_dn[dn]
        g["so_mo_thanh_cong"] += b["so_mo_thanh_cong"]
        g["so_mo_that_bai"] += b["so_mo_that_bai"]
        # OR: chi can 1 block bao SUCCESS la du (xem luat gom o docstring)
        g["thanh_cong"] = g["thanh_cong"] or b["thanh_cong"]
        if g["ly_do_loi"] is None:
            g["ly_do_loi"] = b["ly_do_loi"]

    # Chot lai sau khi da cong don: co MO that bai thi DN do KHONG the la thanh
    # cong, du da tung co 1 block bao SUCCESS
    for g in theo_dn.values():
        if g["so_mo_that_bai"] > 0:
            g["thanh_cong"] = False
            if g["ly_do_loi"] is None:
                g["ly_do_loi"] = f"{g['so_mo_that_bai']} MO that bai"
        elif g["thanh_cong"]:
            # da thanh cong that thi khong giu ly do loi cua block trung gian -
            # de lai se lam nguoi doc tuong DN nay co van de
            g["ly_do_loi"] = None
    # dict giu thu tu chen (Python 3.7+) nen thu tu DN dung nhu trong output
    return list(theo_dn.values())


def _tom_tat_provision(dn_list: list[dict]) -> str:
    """Chuoi nhieu dong ghi vao cr_log buoc 13 - nguoi truc doc la biet ngay
    tram nao doi duoc tham so, tram nao chua."""
    so_ok = sum(1 for d in dn_list if d["thanh_cong"])
    mo_ok = sum(d["so_mo_thanh_cong"] for d in dn_list if d["thanh_cong"])
    mo_tong = sum(d["so_mo_thanh_cong"] + d["so_mo_that_bai"] for d in dn_list)
    dong = [f"Provision {so_ok}/{len(dn_list)} DN thanh cong ({mo_ok}/{mo_tong} MO)"]
    for d in dn_list:
        ten = d["dn"].rsplit("/", 1)[-1]  # PLMN-PLMN/MRBTS-116952 -> MRBTS-116952
        if d["thanh_cong"]:
            dong.append(f"OK   {ten} ({d['so_mo_thanh_cong']} MO)")
        else:
            tong_mo = d["so_mo_thanh_cong"] + d["so_mo_that_bai"]
            dong.append(f"LOI  {ten} ({d['so_mo_thanh_cong']}/{tong_mo} MO): {d['ly_do_loi']}")
    return "\n".join(dong)


class NetActAdapter:
    def __init__(self):
        # NETACT_SERVERS KHONG con doc o day (SUA 27092026, Giai doan 1
        # buoc 2) - chuyen sang OssRouterEnv (adapters/netact/oss_router_env.py).
        # Adapter nay CHI con lo SSH/SFTP/Import/Provision, nhan OssInstance
        # DA CHON SAN tu use case (IOssRouter.chon_oss() da tra cuu + kiem
        # credential placeholder truoc do rieng, xem docstring submit_cr()).
        self._upload_path = os.getenv("NETACT_UPLOAD_PATH", "")
        self._ssh_timeout = int(os.getenv("NETACT_SSH_TIMEOUT", "30"))
        self._cmd_timeout = int(os.getenv("NETACT_CMD_TIMEOUT", "120"))

    async def submit_cr(self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance) -> dict:
        # SUA 27092026 - KHONG con tu tra cuu NETACT_SERVERS/kiem placeholder
        # o day (truoc day raise SshConnectionError neu thieu credentials) -
        # use case CHI goi ham nay SAU KHI IOssRouter.chon_oss() da tra ve
        # OssInstance hop le (khong None). Neu chua cau hinh, use case da tu
        # loai cell do (ly do OSS_CHUA_CAU_HINH) TRUOC khi toi day.
        #
        # SshExecutor dong bo (Paramiko) — chay trong thread rieng de khong
        # block event loop FastAPI (xem chu y o dau file).
        return await asyncio.to_thread(self._submit_cr_sync, xml_content, plan_name, backup_name, oss)

    def _submit_cr_sync(self, xml_content: str, plan_name: str, backup_name: str, oss: OssInstance) -> bool:
        executor = SshExecutor()
        filename = f"{plan_name}.xml"

        # gio dia phuong VN (GMT+7) CHI cho TEN THU MUC — khac quy uoc luu DB
        # (UTC, BUSINESS_RULES.md SS7.2) vi day la thu muc tren dia de nguoi
        # van hanh doi chieu thu cong, khong phai gia tri nghiep vu (xem chu y
        # dau file, muc 15072026)
        timestamp = datetime.now(timezone(timedelta(hours=7))).strftime("%d%m%Y_%H%M")
        run_dir = _PROJECT_ROOT / "docs" / "logs" / "netact_runs" / timestamp
        # exist_ok=True — nhieu tram/nhieu buoc co the roi vao cung 1 phut,
        # tao lai thu muc da co san khong duoc bao loi
        os.makedirs(run_dir, exist_ok=True)

        local_xml_path = run_dir / filename
        remote_dir = f"{self._upload_path}{timestamp}/"
        remote_path = f"{remote_dir}{filename}"

        # ghi THANG vao vi tri luu vinh vien — thay tempfile+os.unlink() truoc
        # day, giu lai file XML that da gui de audit/debug sau nay (yeu cau user)
        local_xml_path.write_text(xml_content, encoding="utf-8")

        # execution.log rieng 1 file/thu muc timestamp — dung chung
        # KeyValueFormatter voi log he thong (infrastructure/logger.py) de
        # dong bo dinh dang, de grep chung
        log_path = run_dir / "execution.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(KeyValueFormatter())
        run_logger = logging.getLogger(f"{__name__}.run")
        run_logger.setLevel(logging.INFO)
        run_logger.addHandler(file_handler)

        # None = chua ket thuc (loi ha tang/exception giua chung) — phan biet
        # ro voi False (loi nghiep vu racclimx.sh, ket thuc binh thuong)
        # dict thay vi bool (18082026): caller can biet BUOC NAO hong (import vs
        # provision - 2 tinh huong rat khac nhau) va DN NAO hong (de dat
        # PARTIAL_SUCCESS + ghi cr_log buoc 13 theo tung DN).
        result: dict = {
            "ok": False,
            "trang_thai": "FAILED",
            "buoc_loi": None,
            "dn_list": [],
            # None = chua chay toi provision nen KHONG BIET ty le, khac 0/0.
            # B1 (02092026) - dem theo CELL (MO) thay vi theo DN: CR tac dong len
            # CELL, 1 managedObject trong XML = 1 LNCEL. MRBTS chi la noi cell cam
            # vao nen "3/4 tram" khong noi len duoc bao nhieu cell that su doi duoc
            # tham so.
            "so_cell_thanh_cong": None,
            "so_cell_tong": None,
            # A6/B6 (02092026) - duong dan file execution.log cua CHINH luot chay
            # nay, de ghi vao cr_session.duong_dan_log. Gan NGAY tu dau (truoc
            # khoi try) chu khong doi den luc thanh cong: luot chay HONG moi la
            # luot can doc log nhat, ma nhanh hong lai la nhanh de bo sot nhat.
            # Luu duong dan TUONG DOI so voi goc project - duong dan tuyet doi se
            # sai ngay khi deploy sang may khac (dev Windows vs server Linux).
            "duong_dan_log": None,
            "tom_tat": "",
        }
        # Gan NGAY sau khi tao result (log_path da tinh o tren): luot chay HONG
        # moi la luot can doc log nhat, ma nhanh hong lai la nhanh de bo sot -
        # gan o day thi moi duong ra deu mang theo duong dan log.
        # Luu duong dan TUONG DOI so voi goc project: duong dan tuyet doi se sai
        # ngay khi deploy sang may khac (dev Windows vs server Linux).
        result["duong_dan_log"] = str(log_path.relative_to(_PROJECT_ROOT).as_posix())
        try:
            # KHONG log oss.password (xem docstring dau file - IOssRouter/
            # OssInstance khong duoc lo credential ra ngoai).
            run_logger.info(
                "Bat dau ket noi SSH NetAct",
                extra={"host": oss.host, "oss_instance": oss.instance_id, "plan_name": plan_name},
            )
            try:
                executor.connect(oss.host, oss.user, oss.password, timeout=self._ssh_timeout)
            except SshConnectionError as e:
                # 23/10/2026: cau loi nay len cr_log/API - thay host/IP bang TEN
                # NA (vd "NA14"): nguoi van hanh sua cau hinh theo ten NA, va
                # khong lo dia chi ha tang ra UI. Ca text exception cua paramiko
                # cung co the chua IP -> thay het. Log file (run_logger) van co host.
                raise SshConnectionError(
                    _an_host(str(e), oss), oss_instance=oss.instance_id
                ) from e
            logger.info("NetAct SSH connect OK", extra={"plan_name": plan_name, "step": "connect"})
            run_logger.info("SSH connect thanh cong", extra={"host": oss.host, "oss_instance": oss.instance_id})

            # SSH mkdir remote TRUOC upload — dung lai ket noi SSH da mo o
            # executor.connect() ben tren, KHONG mo connection rieng cho mkdir.
            # "mkdir -p" khong bao loi neu thu muc da ton tai (truong hop chay
            # lai cung phut) — xu ly graceful, khong crash
            run_logger.info("Chuan bi SSH mkdir remote", extra={"remote_dir": remote_dir})
            mkdir_exit_code, mkdir_out, mkdir_err = executor.exec_command(f"mkdir -p {remote_dir}")
            mkdir_ok = mkdir_exit_code == 0
            run_logger.info(
                "SSH mkdir remote ket qua",
                extra={
                    "remote_dir": remote_dir,
                    "exit_code": mkdir_exit_code,
                    "status": "success" if mkdir_ok else "failed",
                },
            )
            if not mkdir_ok:
                # khong the tiep tuc SFTP upload vao thu muc co the chua ton
                # tai — day la loi ha tang (quyen/duong dan), khop pattern
                # SshConnectionError cua cac buoc infra khac (connect/sftp)
                run_logger.error(
                    "SSH mkdir remote that bai stdout/stderr", extra={"stdout": mkdir_out, "stderr": mkdir_err}
                )
                raise SshConnectionError(f"SSH mkdir remote that bai: {mkdir_err or mkdir_out}", remote_dir=remote_dir)

            run_logger.info(
                "Chuan bi SFTP upload", extra={"local_path": str(local_xml_path), "remote_path": remote_path}
            )
            executor.sftp_upload(str(local_xml_path), remote_path)
            logger.info(
                "SFTP upload OK", extra={"plan_name": plan_name, "step": "sftp_upload", "remote_path": remote_path}
            )
            run_logger.info("SFTP upload thanh cong", extra={"remote_path": remote_path})

            # API_CONTRACTS.md SS5 Buoc 2
            import_cmd = (
                f"racclimx.sh -op Import -type plan -planName {plan_name} "
                f"-inputFile {remote_path} -UIValues true -v"
            )
            if not self._run_step(executor, import_cmd, plan_name, "import", run_logger):
                logger.error(
                    "Import that bai — DUNG, khong chay Provision",
                    extra={"plan_name": plan_name, "step": "import", "status": "failed"},
                )
                result = {
                    **result,
                    "buoc_loi": "import",
                    "tom_tat": "Import plan vao NetAct that bai - CHUA chay Provision",
                }
                return result

            # API_CONTRACTS.md SS5 Buoc 3
            provision_cmd = (
                f"racclimx.sh -op Provision -planName {plan_name} -v "
                f"-createBackupPlan true -provisioningOperation activate "
                f"-backupPlanName {backup_name}"
            )
            result = self._chay_provision(executor, provision_cmd, plan_name, run_logger)
            return result
        finally:
            # ghi KE CA khi loi/exception giua chung (vd SshConnectionError tu
            # connect/mkdir/sftp) — try/finally dam bao khong bao gio bo qua
            # dong log ket qua cuoi cung, du thanh cong hay that bai
            run_logger.info("Ket qua cuoi cung submit_cr", extra={"result": result})
            run_logger.removeHandler(file_handler)
            file_handler.close()
            executor.close()

    def _chay_provision(
        self, executor: SshExecutor, cmd: str, plan_name: str, run_logger: logging.Logger
    ) -> dict:
        """Chay Provision + danh gia THEO TUNG DN.

        Tra dict: {ok, trang_thai, buoc_loi, dn_list, tom_tat}
            trang_thai = DONE (tat ca DN OK) | PARTIAL_SUCCESS (hon hop)
                       | FAILED (tat ca hong, hoac lenh chua chay xong)

        VI SAO CAN PARTIAL_SUCCESS: CR that 18/08 co 4 DN, 3 thanh cong (6 MO da
        doi tham so RF THAT len thiet bi) va 1 hong (NoRouteToHost). Bao ca CR
        la FAILED la NOI SAI SU THAT - nguoi van hanh tuong khong co gi xay ra
        va chay lai ca 4, trong khi 3 tram kia DA doi roi.
        """
        exit_code, stdout, stderr = executor.exec_command(cmd, timeout=self._cmd_timeout)

        # CAP TOAN LENH truoc: thieu "Status received: Finished" nghia la lenh
        # CHUA CHAY XONG (timeout / dut SSH / racclimx chet giua chung) - khac
        # HAN "chay xong nhung co DN loi". Truong hop nay KHONG duoc bao
        # PARTIAL_SUCCESS: ta khong biet nhung DN chua co feedback da doi hay
        # chua, doan bua la nguy hiem.
        if exit_code != 0 or _HOAN_TAT not in stdout:
            ly_do = (
                f"exit_code={exit_code}"
                if exit_code != 0
                else f"stdout thieu '{_HOAN_TAT}' - lenh chua chay xong"
            )
            ket_qua = {
                "ok": False,
                "trang_thai": "FAILED",
                "buoc_loi": "provision",
                "dn_list": [],
                # None (KHONG phai 0/0): lenh chua chay xong nen ta KHONG BIET
                # co bao nhieu cell, cung khong biet cell nao da doi. 0/0 se bi
                # doc nham thanh "da dem, khong cell nao thanh cong".
                "so_cell_thanh_cong": None,
                "so_cell_tong": None,
                "tom_tat": f"Provision khong hoan tat: {ly_do}",
            }
        else:
            dn_list = _parse_provision_theo_dn(stdout)
            # B1 (02092026) - TRANG THAI TINH THEO CELL, khong theo DN.
            # Truoc day: 1 DN hong trong 4 DN -> PARTIAL_SUCCESS, du DN do co the
            # chi chua 1 cell trong tong 20 cell. Con so nguoi van hanh can la
            # "bao nhieu CELL that su doi duoc tham so".
            cell_ok = sum(d["so_mo_thanh_cong"] for d in dn_list)
            cell_tong = sum(d["so_mo_thanh_cong"] + d["so_mo_that_bai"] for d in dn_list)
            if not dn_list or cell_tong == 0:
                # Lenh chay xong nhung KHONG co feedback nao / khong dem duoc cell
                # nao -> khong co dau hieu thanh cong duong. Whitelist: vang mat
                # la that bai, KHONG suy dien "khong thay loi tuc la khong loi".
                trang_thai = "FAILED"
            elif cell_ok == cell_tong:
                trang_thai = "DONE"
            elif cell_ok == 0:
                trang_thai = "FAILED"
            else:
                trang_thai = "PARTIAL_SUCCESS"
            ket_qua = {
                "ok": trang_thai in ("DONE", "PARTIAL_SUCCESS"),
                "trang_thai": trang_thai,
                "buoc_loi": None if trang_thai == "DONE" else "provision",
                "dn_list": dn_list,
                # 2 con so ghi thang vao cr_session, khoi phai parse lai chuoi
                # tom tat trong cr_log. Lay tu SUCCESSFUL MOS / FAILED MOS.
                "so_cell_thanh_cong": cell_ok,
                "so_cell_tong": cell_tong,
                "tom_tat": _tom_tat_provision(dn_list) if dn_list else
                           "Provision chay xong nhung khong co feedback DN nao",
            }

        logger.info(
            "racclimx.sh provision ket qua",
            extra={
                "plan_name": plan_name,
                "step": "provision",
                "exit_code": exit_code,
                "status": ket_qua["trang_thai"],
                "so_dn": len(ket_qua["dn_list"]),
            },
        )
        if not ket_qua["ok"]:
            logger.error(
                "racclimx.sh provision stdout/stderr",
                extra={"plan_name": plan_name, "stdout": stdout, "stderr": stderr},
            )
        run_logger.info(
            "provision ket qua day du",
            extra={
                "exit_code": exit_code,
                "status": ket_qua["trang_thai"],
                "tom_tat": ket_qua["tom_tat"],
                "stdout": stdout,
                "stderr": stderr,
            },
        )
        return ket_qua

    def _run_step(
        self,
        executor: SshExecutor,
        cmd: str,
        plan_name: str,
        step: str,
        run_logger: logging.Logger,
    ) -> bool:
        exit_code, stdout, stderr = executor.exec_command(cmd, timeout=self._cmd_timeout)
        # Dung cho mkdir/Import - cac lenh KHONG co cau truc block DN de parse
        # whitelist. Giu 1 luoi an toan HEP (_IMPORT_FATAL) thay vi blacklist 4
        # keyword cu: van bat duoc loi that ("ERROR", stack trace) nhung khong
        # con bao oan tren "0 errors"/"FAILED MRBTS : 0". Provision co duong
        # rieng _chay_provision() voi whitelist theo tung DN.
        loi_nghiem_trong = any(k in stdout or k in stderr for k in _IMPORT_FATAL)
        ok = exit_code == 0 and not loi_nghiem_trong
        logger.info(
            "racclimx.sh %s ket qua",
            step,
            extra={
                "plan_name": plan_name,
                "step": step,
                "exit_code": exit_code,
                "status": "success" if ok else "failed",
            },
        )
        if not ok:
            logger.error(
                "racclimx.sh %s stdout/stderr", step, extra={"plan_name": plan_name, "stdout": stdout, "stderr": stderr}
            )
        # execution.log ghi full stdout/stderr CA KHI thanh cong (khac logger
        # he thong o tren chi dump full luc that bai) — yeu cau audit day du
        # tung buoc Import/Provision, khong chi khi loi
        run_logger.info(
            "%s ket qua day du",
            step,
            extra={"exit_code": exit_code, "status": "success" if ok else "failed", "stdout": stdout, "stderr": stderr},
        )
        return ok
