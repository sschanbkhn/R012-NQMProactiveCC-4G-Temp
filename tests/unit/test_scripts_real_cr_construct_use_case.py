"""
Test scripts/run_real_cr.py va scripts/checkpoint_real_cr.py khoi tao duoc
TriggerCrUseCase voi DU tham so bat buoc cua constructor hien tai - KHONG
goi NetAct/DB that (chi phan tich SOURCE CODE bang ast + import module,
KHONG thuc thi main() - main() moi lam I/O that).

Tu: quyet dinh 02/10/2026 (item 3) - 2 script nay thieu affected_cells_repo/
cr_log_repo tu 22/07/2026 (TriggerCrUseCase them 2 tham so do, 2 script
KHONG duoc cap nhat theo) - da BO SUNG, test nay la luoi an toan chan
regression neu TriggerCrUseCase them tham so bat buoc moi ma quen sua script.
"""

import ast
import importlib
import inspect
from pathlib import Path

from application.trigger_cr_use_case import TriggerCrUseCase

_SCRIPTS = ["scripts/run_real_cr.py", "scripts/checkpoint_real_cr.py"]


def _keyword_args_cua_loi_goi_dau_tien(source: str, ten_class: str) -> set[str]:
    """Tra tap ten tham so KEYWORD duoc truyen trong loi goi ClassName(...) DAU
    TIEN tim thay trong source (ast.parse - chi doc cu phap, KHONG thuc thi)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == ten_class:
            return {kw.arg for kw in node.keywords if kw.arg is not None}
    raise AssertionError(f"Khong tim thay loi goi {ten_class}(...) trong source")


def _tham_so_bat_buoc(cls) -> set[str]:
    sig = inspect.signature(cls.__init__)
    return {
        name
        for name, param in sig.parameters.items()
        if name != "self" and param.default is inspect.Parameter.empty
    }


def test_2_script_truyen_du_tham_so_bat_buoc_cho_TriggerCrUseCase():
    bat_buoc = _tham_so_bat_buoc(TriggerCrUseCase)
    for duong_dan in _SCRIPTS:
        source = Path(duong_dan).read_text(encoding="utf-8")
        da_truyen = _keyword_args_cua_loi_goi_dau_tien(source, "TriggerCrUseCase")
        thieu = bat_buoc - da_truyen
        assert not thieu, f"{duong_dan} thieu tham so bat buoc cho TriggerCrUseCase: {thieu}"


def test_scripts_import_duoc_khong_loi_cu_phap():
    # Import MODULE (KHONG goi main()) - main() moi lam I/O that (DB/CDS/
    # NetAct that), o day CHI xac nhan khong co loi cu phap/import thieu.
    importlib.import_module("scripts.run_real_cr")
    importlib.import_module("scripts.checkpoint_real_cr")
