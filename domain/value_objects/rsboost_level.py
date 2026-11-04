"""
RsboostLevel value object — RSBOOST_SCALE, next_level(), from_raw(), to_xml_value().
Tu: ARCHITECTURE.md Section 3.2; BUSINESS_RULES.md Section 5; TASK_LIST.md B2.2
"""

from dataclasses import dataclass

# BUSINESS_RULES.md SS5.1 dong 188 — 4 phan tu, da xac nhan voi user.
# Luu y: VD tie-break (SS5.2 dong 212) va DB/XML example (SS5.3 dong 218/221) trong
# doc tham chieu them -6.0 — xac nhan la loi danh may cua doc, khong ap dung o day.
RSBOOST_SCALE = [-3.0, 0.0, 3.0, 6.0]


@dataclass(frozen=True)
class RsboostLevel:
    # C1.4-fix12 (21072026, xac nhan voi user - bug that: session #198/tram
    # 111139, rsboost_current=1.77 crash ValueError): value la dB THAT dang
    # chay tren mang, doc tu cell_infor/cell_params - CO THE la bat ky so
    # lien tuc nao (vd 1.77), KHONG chi rieng 4 buoc cua RSBOOST_SCALE.
    # RSBOOST_SCALE CHI la cac buoc CHUAN de TINH gia tri MOI khi lam CR
    # (xem next_level() ben duoi), KHONG phai tap gia tri hop le cua "gia
    # tri hien tai". Constructor KHONG (va KHONG duoc) ep value phai nam
    # tren scale - luu dung gia tri that de hien thi/luu tru.
    value: float

    def next_level(self) -> "RsboostLevel":
        # BUSINESS_RULES.md SS5.2 — tang 1 bac theo discrete scale, khong cong
        # dBm truc tiep. SUA (C1.4-fix12): KHONG dung RSBOOST_SCALE.index(self.value)
        # nua - crash ValueError neu gia tri hien tai KHONG nam dung tren 1
        # trong 4 buoc (truong hop that: 1.77dB, gia tri lien tuc tu mang that).
        # Thay bang: tim buoc CHUAN nho nhat LON HON gia tri hien tai (vd 1.77
        # -> 3.0) - neu gia tri hien tai DA dung 1 buoc chuan (vd 0.0), ket qua
        # tu nhien la buoc KE TIEP (0.0 khong "lon hon chinh no") nen hanh vi cu
        # (0.0->3.0, 3.0->6.0, -3.0->0.0) GIU NGUYEN, khong regression.
        higher_steps = [level for level in RSBOOST_SCALE if level > self.value]
        if not higher_steps:
            # da o hoac vuot buoc cao nhat (6dB) - khong tang them (an toan
            # mang, giu dung hanh vi cu khi value=6.0)
            return RsboostLevel(self.value)
        return RsboostLevel(min(higher_steps))

    @classmethod
    def from_raw(cls, raw: float) -> "RsboostLevel":
        # BUSINESS_RULES.md SS5.2 — chon bac gan nhat (min abs distance);
        # tie (nam chinh giua) -> chon bac THAP HON (an toan mang)
        nearest = min(RSBOOST_SCALE, key=lambda level: (abs(level - raw), level))
        return cls(nearest)

    def to_xml_value(self) -> str:
        # BUSINESS_RULES.md SS5.3 — bo trailing zero: 3.0 -> "3dB", khong phai "3.0dB"
        return f"{self.value:g}dB"
