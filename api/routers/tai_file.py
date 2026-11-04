"""
Tra file .xlsx + dat ten file (DOT 2, 18/10/2026) - dung chung cho
/hau-kiem/excel va /dashboard/*excel.

Ten tram co the chua ky tu la (dau cach, "/", dau tieng Viet) -> thay bang "_"
de ten file hop le tren moi he dieu hanh. Header co CA filename (ASCII, trinh
duyet cu) lan filename* (UTF-8, RFC 5987) de trinh duyet doc dung.
"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi.responses import Response

_GMT7 = timezone(timedelta(hours=7))
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def lam_sach(ten: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", ten or "").strip("_")


def dau_thoi_gian() -> str:
    return f"{datetime.now(_GMT7):%Y%m%d_%H%M}"


def tra_xlsx(noi_dung: bytes, ten_file: str) -> Response:
    ascii_ten = ten_file.encode("ascii", "replace").decode().replace("?", "_")
    return Response(
        content=noi_dung,
        media_type=_XLSX,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_ten}\"; filename*=UTF-8''{quote(ten_file)}"
        },
    )
