"""
OssInstance — 1 may chu NetAct/OSS cu the (host + credential SSH).
Tu: Giai doan 1 buoc 2 (27/09/2026) - dinh tuyen OSS theo tung cell lan can,
khac voi thiet ke cu (1 CR = 1 ma_tinh cua tram tat = 1 server co dinh).

# Quyet dinh design: dinh tuyen OSS theo TUNG CELL (khong theo tram tat)
# Tai sao: CR sua rsboost/qrxlevmin tren CELL LAN CAN, khong phai tren tram
# tat - cell lan can co the thuoc tram vat ly O TINH CU KHAC tram tat (giap
# ranh tinh). Chon server theo tram tat se gui NHAM XML len OSS khong quan ly
# cell do. instance_id la TEN GOI (vd "NA09"/"NA14") - dung de SO SANH xem
# nhieu cell co CUNG 1 OSS hay khong (gop nhom, phat hien CR_NHIEU_OSS), va
# de HIEN trong thong bao loi/preview - KHONG duoc chua secret nen tach rieng
# host/user/password, va API/log CHI duoc lo instance_id + host, KHONG BAO GIO
# user/password (xem api/schemas/cr_schemas.py::OssSeDung).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OssInstance:
    # frozen=True: dung lam KHOA dict (gom cell theo OSS, dem so OSS khac
    # nhau de phat hien CR_NHIEU_OSS) - can __eq__/__hash__ tu dong cua
    # dataclass, khong duoc mutable.
    instance_id: str
    host: str
    # repr=False: OssInstance nam trong PlanResult/PreviewResult - bat ky
    # log/exception message/pytest assert nao in nguyen doi tuong (vd
    # f"{plan}" hoac AssertionError khi so sanh sai) se lo mat khau NetAct
    # neu khong tat repr o day. user cung tat vi cung la credential nhay cam.
    user: str = field(repr=False)
    password: str = field(repr=False)
    # noc (02/10/2026) - NOC (don vi van hanh) quan ly OSS nay, de
    # cr_session luu lai "session nay chay tren NetAct nao / NOC nao" phuc
    # vu tra lich su (xem trigger_cr_use_case.py, models/cr_session.py).
    # Optional (default None) - KHONG duoc lam truong BAT BUOC: dinh dang .env
    # CU (phang) khong co khoa nay trong tung instance (OssRouterEnv tu gan
    # "NOC1" cho TOAN BO instance kieu cu thay vi doc tu day), va cac noi da
    # dung OssInstance(...) truoc 02/10/2026 (test, netact_adapter...) KHONG
    # truyen tham so nay - them field BAT BUOC se vo het cac cho do.
    noc: str | None = None
