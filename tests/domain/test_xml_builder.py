"""
Unit test cho XmlBuilder — so sanh CAU TRUC output (parse bang
xml.etree.ElementTree, KHONG so sanh string tho vi whitespace/format co the
khac giua lan build - dateTime luon doi) voi:
  1. Template that: adapters/netact/templates/cr_template.xml (copy nguyen
     file ucr012_cr_110548_hni_11072026_11048.xml da chay thanh cong tren
     NetAct that) — xac nhan <raml>, DOCTYPE, cmData khop chinh xac cau truc.
  2. BUSINESS_RULES.md Section 7.3 — thu tu rsboost truoc/qrxlevmin sau, loc
     "skip", khong co id/version tren managedObject moi.
Tu: ARCHITECTURE.md Section 10 (Testing Strategy); TASK_LIST.md B7.1
"""

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from adapters.netact.xml_builder import XmlBuilder
from domain.entities.xml_cell_data import XmlCellData
from domain.value_objects.qrxlevmin import Qrxlevmin
from domain.value_objects.rsboost_level import RsboostLevel

_NS = "raml20.xsd"
_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "adapters" / "netact" / "templates" / "cr_template.xml"
_DATETIME_GMT7_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+07:00$")


def _q(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _template_root() -> ET.Element:
    return ET.parse(_TEMPLATE_PATH).getroot()


def test_doctype_va_xml_declaration_khop_chinh_xac_template_that():
    # 2 dong dau la text tho, khong qua parser — phai byte-identical voi
    # template that (ET khong giu lai DOCTYPE khi serialize, builder phai tu
    # ghep lai dung y het).
    template_raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    template_header = "\n".join(template_raw.splitlines()[:2])

    xml = XmlBuilder().build_xml([], "R012_NQMProactiveCC_160000_20260712_143022")
    xml_header = "\n".join(xml.splitlines()[:2])

    assert xml_header == template_header
    assert xml_header == (
        '<?xml version="1.0" encoding="UTF-8"?>\n' "<!DOCTYPE raml SYSTEM 'raml20.dtd'>"
    )


def test_output_la_xml_hop_le_va_raml_root_khop_template_that():
    template_root = _template_root()
    xml = XmlBuilder().build_xml([], "R012_NQMProactiveCC_160000_20260712_143022")
    root = _parse(xml)  # raise neu khong well-formed

    assert root.tag == template_root.tag == _q("raml")
    assert root.attrib == template_root.attrib == {"version": "2.0"}


def test_cmdata_giu_nguyen_type_scope_tu_template_doi_name_va_xoa_han_id():
    template_cm_data = _template_root().find(_q("cmData"))
    plan_name = "R012_NQMProactiveCC_160000_20260712_143022"

    # Template that CO id (PlanExporter tu gan SAU KHI Import+Provision thanh
    # cong — file goc la ban export lai, khong phai input) — builder phai xoa
    # han attribute nay, de NetAct tu gan khi Import (dong nhat nguyen tac
    # "khong id/version" da xac nhan cho managedObject; xac nhan user 12072026).
    assert template_cm_data.get("id") == "PlanConfiguration( 8156 )"

    xml = XmlBuilder().build_xml([], plan_name)
    cm_data = _parse(xml).find(_q("cmData"))

    assert cm_data.get("type") == template_cm_data.get("type") == "plan"
    assert cm_data.get("scope") == template_cm_data.get("scope") == "all"
    assert cm_data.get("id") is None
    assert "id" not in cm_data.attrib
    # name la truong DUY NHAT con lai tren cmData bi doi so voi template
    assert cm_data.get("name") == plan_name
    assert cm_data.get("name") != template_cm_data.get("name")


def test_header_log_giu_nguyen_action_appinfo_text_chi_doi_datetime_theo_format_gmt7():
    template_log = _template_root().find(_q("cmData")).find(_q("header")).find(_q("log"))

    xml = XmlBuilder().build_xml([], "R012_NQMProactiveCC_160000_20260712_143022")
    log = _parse(xml).find(_q("cmData")).find(_q("header")).find(_q("log"))

    assert log.get("action") == template_log.get("action") == "created"
    assert log.get("appInfo") == template_log.get("appInfo") == "PlanExporter"
    assert log.text == template_log.text == "UIValues are used"

    # dateTime: dung format GMT+7 co millisecond giong file that (KHONG phai
    # UTC "Z" nhu BUSINESS_RULES.md SS7.1 ghi — xem chu y trong xml_builder.py),
    # nhung gia tri phai la thoi diem build MOI, khong copy nguyen tu template.
    assert _DATETIME_GMT7_RE.match(log.get("dateTime")), log.get("dateTime")
    assert log.get("dateTime") != template_log.get("dateTime")


def test_1_cell_rsboost_va_1_cell_qrxlevmin_dung_cau_truc_managedobject():
    cells = [
        XmlCellData(
            cell_id="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
            action_type="rsboost",
            rsboost_new=RsboostLevel(3.0),
            qrxlevmin_new=None,
        ),
        XmlCellData(
            cell_id="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-13",
            action_type="qrxlevmin",
            rsboost_new=None,
            qrxlevmin_new=Qrxlevmin(-132),
        ),
    ]

    xml = XmlBuilder().build_xml(cells, "R012_NQMProactiveCC_160000_20260712_143022")
    cm_data = _parse(xml).find(_q("cmData"))
    managed_objects = cm_data.findall(_q("managedObject"))

    assert len(managed_objects) == 2

    rsboost_mo = managed_objects[0]
    assert rsboost_mo.get("class") == "LNCEL_FDD"
    assert rsboost_mo.get("distName") == "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11/LNCEL_FDD-0"
    assert rsboost_mo.get("operation") == "update"
    assert rsboost_mo.get("id") is None
    assert rsboost_mo.get("version") is None
    p = rsboost_mo.find(_q("p"))
    assert p.get("name") == "dlRsBoost"
    assert p.text == "3dB"

    qrxlevmin_mo = managed_objects[1]
    assert qrxlevmin_mo.get("class") == "SIB"
    assert qrxlevmin_mo.get("distName") == "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-13/SIB-0"
    assert qrxlevmin_mo.get("operation") == "update"
    assert qrxlevmin_mo.get("id") is None
    assert qrxlevmin_mo.get("version") is None
    p = qrxlevmin_mo.find(_q("p"))
    assert p.get("name") == "qrxlevmin"
    assert p.text == "-132"


def test_cell_skip_bi_loai_khoi_output():
    cells = [
        XmlCellData(
            cell_id="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-99",
            action_type="skip",
            rsboost_new=RsboostLevel(6.0),
            qrxlevmin_new=None,
        ),
        XmlCellData(
            cell_id="PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11",
            action_type="rsboost",
            rsboost_new=RsboostLevel(3.0),
            qrxlevmin_new=None,
        ),
    ]
    xml = XmlBuilder().build_xml(cells, "R012_NQMProactiveCC_160000_20260712_143022")
    cm_data = _parse(xml).find(_q("cmData"))
    managed_objects = cm_data.findall(_q("managedObject"))

    assert len(managed_objects) == 1
    assert "LNCEL-99" not in xml
    assert managed_objects[0].get("distName") == "PLMN-PLMN/MRBTS-160000/LNBTS-160000/LNCEL-11/LNCEL_FDD-0"


def test_thu_tu_toan_bo_rsboost_truoc_toan_bo_qrxlevmin_sau_du_input_tron_lan():
    # Input co ca truoc/sau xen ke: qrxlevmin, rsboost, qrxlevmin, rsboost
    cells = [
        XmlCellData("cell-Q1", "qrxlevmin", None, Qrxlevmin(-128)),
        XmlCellData("cell-R1", "rsboost", RsboostLevel(0.0), None),
        XmlCellData("cell-Q2", "qrxlevmin", None, Qrxlevmin(-132)),
        XmlCellData("cell-R2", "rsboost", RsboostLevel(3.0), None),
    ]
    xml = XmlBuilder().build_xml(cells, "R012_NQMProactiveCC_160000_20260712_143022")
    cm_data = _parse(xml).find(_q("cmData"))
    managed_objects = cm_data.findall(_q("managedObject"))

    classes_in_order = [mo.get("class") for mo in managed_objects]
    dist_names_in_order = [mo.get("distName") for mo in managed_objects]

    assert classes_in_order == ["LNCEL_FDD", "LNCEL_FDD", "SIB", "SIB"]
    assert dist_names_in_order == [
        "cell-R1/LNCEL_FDD-0",
        "cell-R2/LNCEL_FDD-0",
        "cell-Q1/SIB-0",
        "cell-Q2/SIB-0",
    ]


def test_danh_sach_rong_tra_ve_cmdata_khong_co_managedobject_va_van_hop_le():
    xml = XmlBuilder().build_xml([], "R012_NQMProactiveCC_160000_20260712_143022")
    cm_data = _parse(xml).find(_q("cmData"))

    assert cm_data.findall(_q("managedObject")) == []
    assert cm_data.find(_q("header")) is not None
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert xml.endswith("</raml>\n")


def test_plan_name_dung_format_that_khong_bi_hong_trong_xml_attribute():
    # Format that duy nhat co the xay ra (BUSINESS_RULES.md SS7.2): chu/so/underscore
    plan_name = "R012_NQMProactiveCC_160000_20260712_143022"
    xml = XmlBuilder().build_xml([], plan_name)
    cm_data = _parse(xml).find(_q("cmData"))

    assert cm_data.get("name") == plan_name
