"""
XmlBuilder — parse template that (adapters/netact/templates/cr_template.xml,
copy nguyen file ucr012_cr_110548_hni_11072026_11048.xml da chay thanh cong
tren NetAct that) bang xml.etree.ElementTree (stdlib — KHONG dung lxml, server
production khong co internet nen tranh phai xin cai them package moi (server
offline); da verify ElementTree.parse() doc duoc DOCTYPE SYSTEM 'raml20.dtd'
+ namespace xmlns="raml20.xsd" cua file that, khong loi, khong can fetch DTD).
Tu: BUSINESS_RULES.md Section 7; TASK_LIST.md B7.1; template that da upload.

Quyet dinh design (khac ban dau B7.1 tu build string tay):
- Parse template → giu nguyen <raml>/<header>/<cmData>, doi cmData@name=
  plan_name va header/log@dateTime=now.
- cmData@id="PlanConfiguration( 8156 )" trong template la ID PlanExporter
  gan SAU KHI Import+Provision thanh cong (bang chung: appInfo="PlanExporter"
  trong <log> — file goc la ban EXPORT LAI cua 1 plan da ton tai, khong phai
  input dung de Import) — XOA HAN attribute nay khi build, de NetAct tu gan
  id khi Import, dong nhat nguyen tac "khong id/version" da xac nhan cho
  managedObject. Neu Import that bao loi thieu id (validate bat buoc), se
  phat hien o B7.2/B7.3 — luc do xu ly tiep, khong doan truoc (xac nhan voi
  user 12072026).
- dateTime dung format that trong file (vd "2026-07-08T19:46:51.000+07:00" —
  GMT+7 co millisecond, KHONG phai UTC "Z" nhu BUSINESS_RULES.md SS7.1 ghi
  ban dau). Giong pattern bug SHA-512 (B6.2): doc ghi sai timezone, file/API
  that moi dung. Da sua BUSINESS_RULES.md SS7.1 khop theo (xac nhan voi user
  12072026).
- Xoa toan bo managedObject mau co san trong cmData, roi append managedObject
  moi cho tung cell theo XmlCellData — KHONG co id/version tren managedObject
  moi (da xac nhan voi user, khac managedObject mau trong template co ca 2).
- rsboost blocks truoc, qrxlevmin blocks sau (BUSINESS_RULES.md SS7.3 dong
  330); action_type="skip" bi loai vi khong khop dieu kien loc nao.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.entities.xml_cell_data import XmlCellData

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "cr_template.xml"
_NS = "raml20.xsd"
_GMT7 = timezone(timedelta(hours=7))

ET.register_namespace("", _NS)


def _q(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


class XmlBuilder:
    def build_xml(self, cells: list[XmlCellData], plan_name: str) -> str:
        tree = ET.parse(_TEMPLATE_PATH)
        raml = tree.getroot()
        cm_data = raml.find(_q("cmData"))
        header = cm_data.find(_q("header"))
        log = header.find(_q("log"))

        cm_data.set("name", plan_name)
        # PlanExporter tu gan id nay SAU KHI Import+Provision thanh cong — khong
        # phai input, xem chu y timezone/id o dau file.
        if "id" in cm_data.attrib:
            del cm_data.attrib["id"]
        # Format giong file that: "%Y-%m-%dT%H:%M:%S.mmm+07:00" (GMT+7, 3 chu
        # so millisecond) — xem chu y timezone o dau file.
        now = datetime.now(_GMT7)
        log.set("dateTime", f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}+07:00")

        for mo in cm_data.findall(_q("managedObject")):
            cm_data.remove(mo)

        rsboost_cells = [c for c in cells if c.action_type == "rsboost"]
        qrxlevmin_cells = [c for c in cells if c.action_type == "qrxlevmin"]
        new_objects = [self._rsboost_element(c) for c in rsboost_cells] + [
            self._qrxlevmin_element(c) for c in qrxlevmin_cells
        ]

        if new_objects:
            for mo in new_objects[:-1]:
                mo.tail = "\n    "
            new_objects[-1].tail = "\n  "
            cm_data.extend(new_objects)
        else:
            # Khong con managedObject nao — can chinh lai tail cua header de
            # </cmData> dong dung indent (2 space), thay vi giu tail cu tro
            # toi vi tri managedObject mau da bi xoa (4 space).
            header.tail = "\n  "

        xml_body = ET.tostring(raml, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' "<!DOCTYPE raml SYSTEM 'raml20.dtd'>\n" f"{xml_body}\n"

    def _rsboost_element(self, cell: XmlCellData) -> ET.Element:
        # BUSINESS_RULES.md SS7.3 dong 316-321 — distName = cell_id + "/LNCEL_FDD-0"
        return self._managed_object(
            class_="LNCEL_FDD",
            dist_name=f"{cell.cell_id}/LNCEL_FDD-0",
            param_name="dlRsBoost",
            param_value=cell.rsboost_new.to_xml_value(),
        )

    def _qrxlevmin_element(self, cell: XmlCellData) -> ET.Element:
        # BUSINESS_RULES.md SS7.3 dong 323-328 — distName = cell_id + "/SIB-0"
        return self._managed_object(
            class_="SIB",
            dist_name=f"{cell.cell_id}/SIB-0",
            param_name="qrxlevmin",
            param_value=cell.qrxlevmin_new.to_xml_value(),
        )

    def _managed_object(self, class_: str, dist_name: str, param_name: str, param_value: str) -> ET.Element:
        mo = ET.Element(
            "managedObject",
            {"class": class_, "distName": dist_name, "operation": "update"},
        )
        mo.text = "\n      "
        p = ET.SubElement(mo, "p", {"name": param_name})
        p.text = param_value
        p.tail = "\n    "
        return mo
