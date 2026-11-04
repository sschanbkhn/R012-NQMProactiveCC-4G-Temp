"""
Ve file Excel cho dashboard (DOT 2, 18/10/2026, yeu cau truc tiep user):
  - ve_chi_tiet(): 1 sheet dong chi tiet cua 1 card (cung du lieu
    GET /dashboard/chi-tiet, khong phan trang).
  - ve_tong_hop(): sheet Tong quan / Theo nhom / Xu huong / Can xu ly tu JSON
    GET /dashboard/tong-quan.
CUNG bang mau voi file hau kiem (adapters/excel/kieu.py). Chi trinh bay - so
lieu da tinh xong o DashboardUseCase.
"""

from io import BytesIO

from openpyxl import Workbook

from adapters.excel.kieu import bang, sheet_chu_giai

# (khoa trong dong API, tieu de cot) theo tung loai card.
_COT_CHI_TIET = {
    "cr": [("session_id", "Session"), ("ngay_cr", "Ngay CR"), ("tram_id", "Ma tram"),
           ("tram_name", "Ten tram"), ("ten_tinh", "Tinh"), ("khu_vuc", "KV"),
           ("vendor_tram", "Vendor tram"), ("status", "Trang thai"), ("so_cell_cr", "So cell CR"),
           ("so_cell_anh_huong", "So cell anh huong"), ("ma_loi", "Ma loi")],
    "cell": [("session_id", "Session"), ("ngay_cr", "Ngay CR"), ("tram_name", "Tram tat"),
             ("cell_name", "Cell"), ("vendor_cell", "Vendor cell"), ("tb_truoc", "TB truoc"),
             ("tb_sau", "TB sau"), ("lech", "Lech"), ("ket_qua", "Ket qua"), ("ly_do", "Ly do"),
             ("so_ngay_co_du_lieu", "So ngay co DL sau CR"), ("ma_phieu", "Ma phieu")],
    "phieu": [("ma_phieu", "Ma phieu"), ("session_id", "Session"), ("cell_name", "Cell"),
              ("vendor_cell", "Vendor cell"), ("phuong_an", "Phuong an"),
              ("trang_thai", "Trang thai"), ("ngay_xuat", "Ngay xuat")],
    "can_xu_ly": [("loai", "Loai"), ("session_id", "Session"), ("tram_id", "Ma tram"),
                  ("tram_name", "Ten tram"), ("status", "Trang thai"), ("ngay", "Ngay"),
                  ("ma_loi", "Ma loi")],
}
_PHUONG_AN = {"1": "He thong", "2": "Hien truong"}


def _luu(wb) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ve_chi_tiet(loai: str, dong: list[dict], luat: list[str]) -> bytes:
    cot = _COT_CHI_TIET["cell" if loai in ("qos", "qoe") else loai]
    khoa = [k for k, _ in cot]
    du_lieu = []
    for d in dong:
        hang = [d.get(k) for k in khoa]
        if loai == "phieu":
            hang[khoa.index("phuong_an")] = _PHUONG_AN.get(d.get("phuong_an"), d.get("phuong_an"))
        du_lieu.append(hang)
    wb = Workbook()
    ws = wb.active
    ws.title = loai.upper() if loai != "can_xu_ly" else "Can xu ly"
    bang(
        ws, [t for _, t in cot], du_lieu,
        cot_danh_gia={khoa.index("ket_qua") + 1} if "ket_qua" in khoa else set(),
        cot_phieu={khoa.index("ma_phieu") + 1} if "ma_phieu" in khoa else set(),
        dinh_dang_so={khoa.index(k) + 1: "0.00" for k in ("tb_truoc", "tb_sau", "lech") if k in khoa},
    )
    sheet_chu_giai(wb, luat)
    return _luu(wb)


def _dong_chi_so(ten, x: dict) -> list:
    t, hk, ph = x["tong"], x["hau_kiem"], x["phieu"]
    return [
        ten, t["so_session"], t["so_tram"], t["so_cell_cr"],
        hk["qos"]["so_cell"], hk["qos"]["dat"]["ty_le"], hk["qos"]["khong_dat"]["so"],
        hk["qoe"]["so_cell"], hk["qoe"]["dat"]["ty_le"], hk["qoe"]["khong_dat"]["so"],
        ph["success"], ph["he_thong"], ph["hien_truong"], ph["cho_xuat_tay"], ph["loi"],
    ]


_TIEU_DE_CHI_SO = [
    "Nhom", "So session", "So tram", "So cell CR",
    "QoS so cell", "QoS % dat", "QoS khong dat", "QoE so cell", "QoE % dat", "QoE khong dat",
    "Phieu SUCCESS", "Phieu He thong", "Phieu Hien truong", "Cho xuat tay", "Phieu loi",
]


def ve_tong_hop(tq: dict, luat: list[str]) -> bytes:
    wb = Workbook()

    ws = wb.active
    ws.title = "Tong quan"
    tong = []
    tong.append(["Khoang", f"{tq['tu_ngay']} den {tq['den_ngay']}"])
    tong.append(["So session", tq["tong"]["so_session"]])
    for k, v in tq["tong"]["theo_trang_thai"].items():
        tong.append([f"  Trang thai {k}", v])
    tong.append(["So tram", tq["tong"]["so_tram"]])
    tong.append(["So cell chay CR", tq["tong"]["so_cell_cr"]])
    for p, ten in (("qos", "QoS"), ("qoe", "QoE")):
        h = tq["hau_kiem"][p]
        tong += [
            [f"{ten} so cell danh gia", h["so_cell"]],
            [f"{ten} Dat (so / %)", f"{h['dat']['so']} / {h['dat']['ty_le']}"],
            [f"{ten} Khong dat (so / %)", f"{h['khong_dat']['so']} / {h['khong_dat']['ty_le']}"],
            [f"{ten}   TB sau < muc", h["khong_dat"]["tb_sau_duoi_muc"]],
            [f"{ten}   Lech > nguong", h["khong_dat"]["lech_qua_nguong"]],
            [f"{ten} Thieu du lieu (so / %)", f"{h['thieu_du_lieu']['so']} / {h['thieu_du_lieu']['ty_le']}"],
        ]
    for k, v in tq["phieu"].items():
        tong.append([f"Phieu {k}", v])
    bang(ws, ["Chi so", "Gia tri"], tong)

    ws = wb.create_sheet("Theo nhom")
    dong = []
    for nhom, ten in (("khu_vuc", "KV"), ("ma_tinh", "Tinh"), ("vendor", "Vendor")):
        for x in tq["theo_nhom"][nhom]:
            nhan = x["gia_tri"] if nhom != "ma_tinh" else f"{x['gia_tri']} {x.get('ten_tinh') or ''}".strip()
            dong.append([ten, *_dong_chi_so(nhan, x)])
    bang(ws, ["Loai nhom", *_TIEU_DE_CHI_SO], dong)

    ws = wb.create_sheet("Xu huong")
    bang(ws, ["Moc", "So CR", "So phieu", "% dat QoS", "% dat QoE",
              "Cell khong dat QoS", "Cell khong dat QoE"],
         [[d["moc"], d["so_cr"], d["so_phieu"], d["ty_le_dat_qos"], d["ty_le_dat_qoe"],
           d["so_cell_khong_dat_qos"], d["so_cell_khong_dat_qoe"]] for d in tq["xu_huong"]])

    ws = wb.create_sheet("Can xu ly")
    can = tq["can_xu_ly"]
    dong = [["Qua han xuat phieu", s["id"], s["tram_id"], s["tram_name"], s.get("ngay_cr"), None]
            for s in can["qua_han_xuat_phieu"]["sessions"]]
    dong += [["KHONG_CHAY", s["id"], s["tram_id"], s["tram_name"], s.get("created_at"), s.get("ma_loi")]
             for s in can["khong_chay"]["sessions"]]
    bang(ws, ["Loai", "Session", "Ma tram", "Ten tram", "Ngay", "Ma loi"], dong)

    sheet_chu_giai(wb, luat)
    return _luu(wb)
