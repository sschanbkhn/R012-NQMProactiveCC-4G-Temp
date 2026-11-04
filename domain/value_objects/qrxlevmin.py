"""
Qrxlevmin value object — QRXLEVMIN_FLOOR, decrease(), to_xml_value().
Tu: ARCHITECTURE.md Section 3.2; BUSINESS_RULES.md Section 6; TASK_LIST.md B2.3
"""

from dataclasses import dataclass

QRXLEVMIN_FLOOR = -144  # BUSINESS_RULES.md SS6.1 dong 256


@dataclass(frozen=True)
class Qrxlevmin:
    value: int

    def decrease(self) -> "Qrxlevmin":
        # BUSINESS_RULES.md SS6.1 dong 254-263 — giam tuyen tinh 4dBm, khong phai
        # discrete scale nhu rsboost nen khong can from_raw()/snap ve bac gan nhat.
        # value - 4 < FLOOR bao trum ca 2 truong hop no-op: da bang floor
        # (-144 - 4 = -148 < -144), hoac tru 4 se vuot floor (VD -142 - 4 = -146).
        if self.value - 4 < QRXLEVMIN_FLOOR:
            return Qrxlevmin(QRXLEVMIN_FLOOR)
        return Qrxlevmin(self.value - 4)

    def to_xml_value(self) -> str:
        # BUSINESS_RULES.md SS6.2 dong 268-271 — integer thuan, khong don vi
        return str(int(self.value))
