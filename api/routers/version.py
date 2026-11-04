"""
GET /version — tra ban dang chay tren server.

=== VI SAO CAN ENDPOINT NAY ===
Server .196 chay tai /home/auto/Python_Project/R012-NQMProactiveCC-4G va KHONG
co thu muc .git (deploy bang rsync/scp, copy tay). Nghia la tren server khong
co cach nao hoi "dang chay commit nao" - khong `git log`, khong `git rev-parse`.

Hau qua THAT da xay ra (13092026): BE_AUDIT.md muc J ket luan "6 commit chua
deploy" dua tren gia dinh .196 = a3c0656. FE_AUDIT.md do live thay openapi khai
20 path, trong khi a3c0656 chi co 18 - tuc .196 that ra da o beccf98 hoac moi
hon. Ket luan sai, va sai theo huong nguy hiem: bao "chua deploy" cho thu DA
deploy roi.

File VERSION do scripts/make_version.* sinh ra LUC BUILD (tren may dev, noi CO
.git) roi di theo bundle sang server. Endpoint nay chi doc lai file do.

=== VI SAO KHONG BAO GIO DUOC TRA 500 ===
Day la endpoint CHAN DOAN. Khi co su co, day la cho dau tien nguoi truc goi de
biet server dang chay gi. Neu no tu gay loi khi thieu file thi dung luc can
nhat lai khong dung duoc - va cai "thieu file VERSION" chinh no DA LA mot cau
tra loi co ich ("ban nay deploy khong qua script"). Nen thieu file -> 200 kem
warning, KHONG phai 404/500.

=== KHONG CHAM DB, KHONG CHAM USE CASE ===
Co y khong Depends() gi. Endpoint chan doan phai tra loi duoc NGAY CA KHI DB
sap - neu no phu thuoc DB thi luc DB hong se khong ai biet server chay ban nao.
"""

import logging
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

logger = logging.getLogger(__name__)

# parents[2] = goc repo: api/routers/version.py -> api/routers -> api -> goc.
# Cung cach api/routers/sessions.py:36 dang lam, giu nguyen de 2 cho khong lech
# nhau khi ai do doi cau truc thu muc.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VERSION_FILE = _PROJECT_ROOT / "VERSION"

# 5 khoa scripts/make_version.* sinh ra. Liet ke tuong minh de response LUON du
# 5 khoa (dien None cho khoa thieu) - FE/script giam sat khong phai doan xem
# khoa nao co the vang.
_KHOA = ("commit", "commit_short", "commit_date", "build_at", "dirty")


def _doc_file_version() -> dict:
    """Parse file VERSION dang key=value thanh dict. KHONG nem loi.

    Moi nhanh loi deu tra dict co "warning" - xem docstring dau file ve ly do
    endpoint chan doan khong duoc phep that bai."""
    if not _VERSION_FILE.exists():
        # KHONG log level error: thieu VERSION la tinh huong BINH THUONG khi
        # chay tu source tren may dev (file bi .gitignore). Chi bat thuong khi
        # o server - ma cho do thi warning nay se lap lai moi lan goi, du de
        # phat hien.
        return {
            **dict.fromkeys(_KHOA),
            "warning": (
                "Khong tim thay file VERSION. Ban nay deploy KHONG qua "
                "scripts/make_version - khong truy nguoc duoc commit. "
                "Xem docs/DEPLOY.md."
            ),
        }

    try:
        noi_dung = _VERSION_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Khong doc duoc file VERSION", extra={"loi": str(exc)})
        return {
            **dict.fromkeys(_KHOA),
            "warning": f"File VERSION ton tai nhung khong doc duoc: {exc}",
        }

    ket_qua: dict = dict.fromkeys(_KHOA)
    for dong in noi_dung.splitlines():
        dong = dong.strip()
        # Bo dong rong va dong comment - de sau nay them chu thich vao VERSION
        # ma khong pha parser.
        if not dong or dong.startswith("#") or "=" not in dong:
            continue
        # split("=", 1): gia tri co the chua dau "=" (vd build_at ISO8601 thi
        # khong, nhung khoa them sau co the co) - chi tach o dau "=" DAU TIEN.
        khoa, _, gia_tri = dong.partition("=")
        ket_qua[khoa.strip()] = gia_tri.strip()

    # dirty la canh bao van hanh: deploy code chua commit thi commit hash ghi
    # trong file KHONG mo ta dung thu dang chay. Chuyen chuoi -> bool o day de
    # script giam sat khong phai so sanh chuoi "true"/"True"/"1".
    if ket_qua.get("dirty") is not None:
        ket_qua["dirty"] = str(ket_qua["dirty"]).strip().lower() == "true"

    if ket_qua.get("commit") is None:
        ket_qua["warning"] = "File VERSION co nhung thieu khoa 'commit' - file hong hoac sinh sai."
    elif ket_qua.get("dirty") is True:
        ket_qua["warning"] = (
            "Ban nay build tu working tree BAN (dirty=true): co thay doi chua "
            "commit. Commit hash duoi day KHONG mo ta dung ma nguon dang chay."
        )

    return ket_qua


@router.get("/version")
async def get_version() -> dict:
    """Ban dang chay tren server nay.

    LUON tra 200. Thieu/hong file VERSION cung tra 200 kem "warning" - xem
    docstring dau module.

    Kiem sau khi deploy:
        curl -s http://10.155.43.196:8080/api/v1/version
    """
    return _doc_file_version()
