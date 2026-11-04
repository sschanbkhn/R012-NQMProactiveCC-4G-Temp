"""
PreviewCrUseCase — POST /cr/preview: chay buoc 3-10 cua CR flow (HO + Delaunay tu 18/10/2026, truoc la CDS -> filter
-> tinh gia tri rsboost/qrxlevmin) NHUNG KHONG SSH, KHONG tao cr_session,
KHONG ghi DB - de FE xem truoc cell/tram bi anh huong truoc khi trigger that.
Tu: docs/DEV_LOG.md muc [C1.4-fix11] (21072026, xac nhan voi user).

Thiet ke: COMPOSE 1 TriggerCrUseCase da wire san (KHONG ke thua/duplicate
constructor deps) de goi lai _prepare_plan()/_resolve_tram_id() - 2 method
"internal" (tien to _) nhung duoc chia se CO CHU DICH cho class nay, dung
domain services THAT (NeighborCellFilter/PriorityAssigner/RsboostCalculator/
QrxlevminCalculator) - KHONG viet lai logic filter/tinh gia tri o day.

22072026 (xac nhan voi user, sau khi trace tay tram 110548 - 368 cell CDS ->
2 nhanh): PreviewResult tra CA 2 nhanh, thay the hoan toan "tram_lan_can" cu
(SAI - truoc day suy tu 12 cell CHAY CR, khong phai tu pham vi anh huong that):
  - cells_bi_anh_huong / tram_bi_anh_huong: Nhanh A (danh gia RF, 47 cell voi
    110548) - suy tu PlanResult.affected_cells (NeighborCellFilter.filter_affected(),
    da loai cell tram goc tu ben trong _prepare_plan(), xem trigger_cr_use_case.py).
  - cells_chay_cr: Nhanh B (12 cell voi 110548, co gia tri rsboost/qrxlevmin
    that su duoc dieu chinh trong CR) - suy tu plan.rsboost_results +
    plan.qrxlevmin_results, y het cach cu (chi doi ten field cho ro nghia).
"""

import logging
from dataclasses import dataclass, field

from application.trigger_cr_use_case import TriggerCrUseCase
from domain.entities.cell_param import CellParam
from domain.errors import CrNoNeighborCellError
from domain.ports.outbound.repo_ports import IEnodebRepo
from domain.services.dist_name import extract_lnbts
from domain.value_objects.oss_instance import OssInstance

logger = logging.getLogger(__name__)



@dataclass
class PreviewTramGoc:
    tram_id: str
    tram_name: str | None
    longitude: float | None
    latitude: float | None


@dataclass
class AffectedCellItem:
    # Nhanh A (danh gia RF, KHONG loc huong/band) - CHI can biet cell nao bi
    # anh huong + thuoc tram nao, KHONG can gia tri rsboost/qrxlevmin (chi
    # Nhanh B/cells_chay_cr moi tinh gia tri, xem BUOC 2 xac nhan voi user).
    #
    # cell_name: str | None (SUA BUOC 4b, 08/10/2026) - nhanh HO co the co cell
    # CAN_GHEP_TEN (vendor khac Nokia hoac chua sync cell_infor, KHONG resolve
    # duoc ten/DN) - van PHAI tra ra de nguoi dung "biet" (yeu cau truc tiep
    # user), chi KHONG ghi cr_affected_cells (xem domain/services/ho_cell_selector.py
    # CellUngVien.can_ghep_ten). Nhanh CDS KHONG BAO GIO tra None o day (filter_affected()
    # luon co cell_name that) - widen kieu la LOOSEN AN TOAN, khong doi hanh vi cu.
    cell_name: str | None
    huong_id: str | None
    tram_id: str | None  # LNBTS, suy tu Cell.dist_name - None cho cell CAN_GHEP_TEN (khong co dist_name)
    # 5 field OPTIONAL THEM (BUOC 4b, 08/10/2026, yeu cau truc tiep user) - CHI
    # co gia tri o nhanh HO (None cho nhanh CDS, GIU NGUYEN hanh vi cu). Xem
    # TriggerCrUseCase.PlanResult.ho_extra.
    pct_ho: float | None = None
    so_ho: int | None = None
    sr: float | None = None
    layer: str | None = None  # "L1"|"L1_CUNG_SITE"|"L2"|"Z"|"KHONG_XAC_DINH"
    co: list[str] = field(default_factory=list)  # "BAT_THUONG"|"CAN_GHEP_TEN"
    # sector/sectors_khac THEM (12/10/2026, yeu cau truc tiep user) - FE truoc
    # day KHONG biet pct_ho/so_ho dang tinh tren MAU SO sector nao (cell co
    # the nhan HO tu nhieu sector cua X, pct_ho/so_ho o day CHI la cua sector
    # "thang" - xem GD4/GD1 o domain/services/ho_cell_selector.py), tuong lam
    # sai lech %HO/so_ho khi so sanh giua cac cell khac sector.
    sector: int | None = None
    sectors_khac: list[int] = field(default_factory=list)


@dataclass
class AffectedTramItem:
    tram_id: str
    tram_name: str | None
    longitude: float | None
    latitude: float | None


@dataclass
class CrCellItem:
    # Nhanh B (12 cell voi 110548) - co gia tri rsboost/qrxlevmin that su se
    # dieu chinh trong CR. tram_id them (khac PreviewCellItem cu) de FE biet
    # cell nay thuoc tram nao ma khong can nested duoi 1 cay tram rieng.
    cell_name: str
    tram_id: str
    huong_id: str | None
    priority: int | None
    action_type: str | None
    rsboost_cu: float | None
    rsboost_moi: float | None
    qrxlevmin_cu: int | None
    qrxlevmin_moi: int | None
    # 2 field THEM (quyet dinh 03/10/2026, luat chon cell CR moi) - band cua
    # CHINH CELL ("1800 F1"/"1800 F2", suy tu LNCEL trong DN) + sector cua
    # TRAM TAT (Y=huong_id%10) - copy tu CellParam.band/CellParam.sector (xem
    # domain/services/neighbor_cell_filter.py::filter_for_cr()).
    band: str | None
    sector: int | None
    # 4 field OPTIONAL THEM (BUOC 4b, 08/10/2026) - CUNG y nghia voi
    # AffectedCellItem o tren, CHI khac KHONG co "co" rieng (BAT_THUONG khong
    # ap dung cho cell DA o trong B - mot cell vao B nghia la KHONG BAT_THUONG;
    # CAN_GHEP_TEN cung khong ap dung - cell o B luon co ten, xem
    # TriggerCrUseCase._cell_ung_vien_to_cell()).
    pct_ho: float | None = None
    so_ho: int | None = None
    sr: float | None = None
    layer: str | None = None


@dataclass
class PreviewResult:
    tram_goc: PreviewTramGoc
    cells_bi_anh_huong: list[AffectedCellItem]
    tram_bi_anh_huong: list[AffectedTramItem]
    cells_chay_cr: list[CrCellItem]
    # Cell CDS KHONG quan ly (cell_id dang phang) - da bi loai khoi 2 nhanh
    # tren. Them 07092026.
    #
    # BAT BUOC TRA RA, KHONG duoc im lang: ket qua preview THIEU cell ma nguoi
    # dung tuong la du con nguy hiem hon loi 500 - ho se trigger CR that dua
    # tren pham vi anh huong khong day du.
    cell_ngoai_pham_vi: list[str] = field(default_factory=list)
    # Ban CHI TIET (V8, 09/2026) - THEM SONG SONG, xem
    # TriggerCrUseCase.PlanResult.cell_ngoai_pham_vi_chi_tiet.
    cell_ngoai_pham_vi_chi_tiet: list[dict] = field(default_factory=list)
    # OSS se dung (Giai doan 1 buoc 2, 27/09/2026) - de nguoi dung THAY truoc
    # khi bam nut chay that, xem TriggerCrUseCase.PlanResult.oss_instance.
    oss_instance: OssInstance | None = None
    # 2 field OPTIONAL THEM (BUOC 4b, 08/10/2026, yeu cau truc tiep user) -
    # CHI co gia tri o nhanh HO (None/[] cho nhanh CDS). Xem
    # TriggerCrUseCase.PlanResult.ho_extra.
    # (nguon_du_lieu: str | None - DA BO 14/10/2026, yeu cau truc tiep user:
    # khong muon hien dong nay tren man xem truoc - xem docs/BUSINESS_RULES.md).
    x_co: list[str] = field(default_factory=list)  # "TOA_DO_DUNG_CHUNG"|"HO_DI_XA"|"IT_DU_LIEU"
    quan_he_day_du: list[dict] = field(default_factory=list)
    # BUOC 4c (10/10/2026, yeu cau truc tiep user) - du lieu ban do (X/L1/L2/
    # tram bi anh huong/duong bao) - CHI co gia tri o nhanh HO
    # (None cho nhanh CDS). Xem TriggerCrUseCase._xay_du_lieu_ban_do().
    ban_do: dict | None = None
    # THEM cho FE (yeu cau truc tiep user) - sector cua X duoi N_MIN_HO_SECTOR
    # (du lieu HO qua it de tin cay - xem domain/services/ho_cell_selector.py)
    # DA CO SAN o tang application (ho_extra["sectors_it_du_lieu"], tu BUOC
    # 08/10/2026), truoc day CHUA lo ra API - rong neu khong co sector nao/
    # nhanh CDS.
    sectors_it_du_lieu: list[int] = field(default_factory=list)


class PreviewCrUseCase:
    def __init__(self, trigger_use_case: TriggerCrUseCase, enodeb_repo: IEnodebRepo):
        self._trigger_uc = trigger_use_case
        self._enodeb_repo = enodeb_repo

    async def execute(self, tram_id: str, tram_name: str, action: str) -> PreviewResult:
        # Validate action - GIONG buoc 1a/1d cua TriggerCrUseCase.prepare_session()
        # (action khong hop le -> ValueError; action="cancel" la Rollback Flow
        # rieng, WORKFLOW.md SS3, KHONG goi CDS neighbor-lookup kieu shutdown/
        # relocate) - preview KHONG goi lai prepare_session() (se tao cr_session
        # that) nen phai tu kiem tra rieng o day, GIU NGUYEN thong diep loi.
        if action not in ("shutdown", "cancel", "relocate"):
            raise ValueError(f"action khong hop le: {action!r} (phai la shutdown|cancel|relocate)")
        if action == "cancel":
            raise NotImplementedError(
                "Rollback flow (action=cancel) khong co preview - xem WORKFLOW.md SS3"
            )

        # Resolve tram_id truoc (giong buoc 1c cua flow trigger that) - dung
        # CHUNG method voi TriggerCrUseCase.prepare_session(), KHONG viet lai.
        # KHONG goi guard RUNNING/DONE (prepare_session() lam rieng, gan voi
        # viec tao session that) - preview van xem truoc duoc du tram dang co
        # CR RUNNING/DONE, day la tinh nang XEM, khong phai TAO CR.
        resolved_tram_id = await self._trigger_uc._resolve_tram_id(tram_id, tram_name)

        # Buoc 3-10 THUAN (khong SSH/khong ghi DB) - dung CHUNG code path voi
        # run_cr_flow() (xem application/trigger_cr_use_case.py::_prepare_plan).
        # _prepare_plan() tu goi filter_affected()/filter_for_cr() voi
        # resolved_tram_id, DA loai cell cua chinh tram goc o CA 2 nhanh -
        # KHONG can tu loc lai o day nua (khac ban truoc 21072026, luc do
        # NeighborCellFilter chua biet tram_goc_id).
        # BO CDS (18/10/2026): khong con timeout/retry CDS rieng cho preview -
        # nhanh HO doc DB + tinh trong memory.
        plan = await self._trigger_uc._prepare_plan(resolved_tram_id, tram_name, action)
        all_params: list[CellParam] = plan.rsboost_results + plan.qrxlevmin_results

        if not plan.affected_cells:
            # Nhanh A (pham vi anh huong RF) rong - tram thuc su khong co
            # neighbor nao hop le (0 huong, hoac toan bo cell bi loai boi
            # dedup/prefix/tram-goc). Dung Nhanh A (khong phai Nhanh B) lam
            # dieu kien loi vi day la khai niem RONG hon - Nhanh B rong nhung
            # Nhanh A con cell van la ket qua HOP LE (preview van huu ich, chi
            # khong co cell nao du dieu kien dieu chinh rsboost/qrxlevmin).
            #
            # BO CDS (18/10/2026): bo nhanh CrCdsNoNeighborDataError ("CDS
            # khong co du lieu") - nhanh HO tu raise HoNoDataError (422) khi
            # khong co du lieu HO, khong toi duoc day voi 0 cell nguon.
            # Den day: CO cell nguon nhung bi loc het. Neu trong so do co cell
            # ngoai pham vi quan ly R012 (cell_id phang, xem
            # neighbor_cell_filter.py:144) thi PHAI noi ra - do thuong la ly do
            # that su khien danh sach rong, va nguoi dung khong the doan duoc
            # tu con so tong.
            so_cell_ngoai_pham_vi = len(plan.cell_ngoai_pham_vi)
            message = (
                f"Tram {resolved_tram_id}: HO co {plan.n_cell_goc} cell nguon "
                "nhung khong cell nao du dieu kien preview"
            )
            if so_cell_ngoai_pham_vi:
                # CHI liet ke 3 ten: tram 280003 co 114 cell ngoai pham vi -
                # do het vao message thi khong ai doc, va no tran ca o thong bao
                # tren UI. 3 ten la du de nguoi dung nhan ra dang cell nao.
                vi_du = ", ".join(plan.cell_ngoai_pham_vi[:3])
                message += (
                    f"; {so_cell_ngoai_pham_vi} cell ngoai pham vi quan ly R012 "
                    f"(vd: {vi_du})"
                )
            # K == 0 thi KHONG nhac gi den pham vi quan ly - them mot menh de
            # "0 cell ngoai pham vi" chi lam nguoi doc di tim mot van de khong
            # ton tai.
            raise CrNoNeighborCellError(message, tram_id=resolved_tram_id)

        # BUOC 4b (08/10/2026) - theo_cell_name/khong_ghep_ten rong {}/[] cho
        # nhanh CDS (plan.ho_extra la None) - .get() duoi day luon tra None an
        # toan, KHONG doi hanh vi cu.
        theo_cell_name: dict[str, dict] = (plan.ho_extra or {}).get("theo_cell_name", {})
        khong_ghep_ten: list[dict] = (plan.ho_extra or {}).get("khong_ghep_ten", [])

        # --- Nhanh A: cells_bi_anh_huong + tram_bi_anh_huong ---
        cells_bi_anh_huong = [
            AffectedCellItem(
                cell_name=c.cell_name,
                huong_id=c.huong_id,
                tram_id=extract_lnbts(c.dist_name),
                **theo_cell_name.get(c.cell_name, {}),
            )
            for c in plan.affected_cells
        ]
        # Cell CAN_GHEP_TEN (HO, khong resolve duoc ten/DN qua cell_infor) -
        # KHONG nam trong plan.affected_cells (thieu dist_name, xem
        # TriggerCrUseCase._cell_ung_vien_to_cell()) nhung PHAI tra ra de
        # nguoi dung "biet" (yeu cau truc tiep user, BUOC 4b muc 3/4) -
        # cell_name/tram_id/huong_id deu None (khong co gi de dien).
        cells_bi_anh_huong += [
            AffectedCellItem(
                cell_name=None, huong_id=None, tram_id=None,
                pct_ho=d["pct_ho"], so_ho=d["so_ho"], sr=d["sr"], layer=d["layer"], co=d["co"],
                sector=d["sector"], sectors_khac=d["sectors_khac"],
            )
            for d in khong_ghep_ten
        ]
        affected_tram_ids = {c.tram_id for c in cells_bi_anh_huong if c.tram_id is not None}

        # --- Nhanh B: cells_chay_cr (giu nguyen field/gia tri nhu truoc) ---
        cells_chay_cr = [
            CrCellItem(
                cell_name=p.cell_name,
                tram_id=p.tram_id,
                huong_id=p.huong_id,
                priority=p.priority,
                action_type=p.action_type,
                rsboost_cu=p.rsboost_current.value if p.rsboost_current else None,
                rsboost_moi=p.rsboost_new.value if p.rsboost_new else None,
                qrxlevmin_cu=p.qrxlevmin_current.value if p.qrxlevmin_current else None,
                qrxlevmin_moi=p.qrxlevmin_new.value if p.qrxlevmin_new else None,
                band=p.band,
                sector=p.sector,
                # "co" DA co p.sector rieng (B); "sector"/"sectors_khac" (THEM
                # 12/10/2026 cho RIENG bang A/AffectedCellItem - xem dac ta o
                # tren) PHAI loai khoi day, khac se dung keyword voi sector=p.sector.
                **{k: v for k, v in theo_cell_name.get(p.cell_name, {}).items() if k not in ("co", "sector", "sectors_khac")},
            )
            for p in all_params
        ]

        # Join bang tram 1 LAN cho CA tram_goc VA tram_bi_anh_huong (tu Nhanh
        # A, RONG HON tap tram cua Nhanh B) - tranh N+1 query.
        all_tram_ids = list({resolved_tram_id, *affected_tram_ids})
        tram_rows = await self._enodeb_repo.get_by_tram_ids(all_tram_ids)
        tram_by_id = {t.tram_id: t for t in tram_rows}

        for missing_id in affected_tram_ids - set(tram_by_id):
            # Edge case (LNBTS khong join duoc bang tram - site chua duoc RIMS
            # sync) - KHONG loai bo cell/tram do khoi response, chi log canh
            # bao, tram_name/toa do se la None.
            logger.warning(
                "tram_id bi anh huong khong join duoc bang tram (co the chua sync RIMS)",
                extra={"tram_id": missing_id},
            )

        tram_goc_info = tram_by_id.get(resolved_tram_id)
        tram_goc = PreviewTramGoc(
            tram_id=resolved_tram_id,
            tram_name=tram_goc_info.tram_name if tram_goc_info else None,
            longitude=tram_goc_info.longitude if tram_goc_info else None,
            latitude=tram_goc_info.latitude if tram_goc_info else None,
        )

        tram_bi_anh_huong = [
            AffectedTramItem(
                tram_id=t_id,
                tram_name=tram_by_id[t_id].tram_name if t_id in tram_by_id else None,
                longitude=tram_by_id[t_id].longitude if t_id in tram_by_id else None,
                latitude=tram_by_id[t_id].latitude if t_id in tram_by_id else None,
            )
            for t_id in sorted(affected_tram_ids)
        ]

        return PreviewResult(
            tram_goc=tram_goc,
            cells_bi_anh_huong=cells_bi_anh_huong,
            tram_bi_anh_huong=tram_bi_anh_huong,
            cells_chay_cr=cells_chay_cr,
            cell_ngoai_pham_vi=plan.cell_ngoai_pham_vi,
            cell_ngoai_pham_vi_chi_tiet=plan.cell_ngoai_pham_vi_chi_tiet,
            oss_instance=plan.oss_instance,
            # BUOC 4b (08/10/2026) - None/[] khi plan.ho_extra None (nhanh CDS,
            # GIU NGUYEN hanh vi cu).
            x_co=(plan.ho_extra or {}).get("x_co", []),
            quan_he_day_du=(plan.ho_extra or {}).get("quan_he_day_du", []),
            ban_do=(plan.ho_extra or {}).get("ban_do"),
            sectors_it_du_lieu=(plan.ho_extra or {}).get("sectors_it_du_lieu", []),
        )
