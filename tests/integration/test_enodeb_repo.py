"""
Integration test cho EnodebRepo — can DB that (schema system_nsn_nqmproactivecc).
Tu: ARCHITECTURE.md Section 10; TASK_LIST.md B5.1
"""

from sqlalchemy import delete, func, select

from adapters.postgres.enodeb_repo import EnodebRepo
from domain.value_objects.khu_vuc import khu_vuc_tu_ma_tinh
from models.tram import Tram as TramModel

TEST_ENODEB_ID = "TEST_B5_ENODEB_1"


async def _cleanup(db_session):
    await db_session.execute(delete(TramModel).where(TramModel.tram_id == TEST_ENODEB_ID))
    await db_session.commit()


async def test_upsert_many_insert_moi_sanitize_toa_do_0(db_session):
    await _cleanup(db_session)
    repo = EnodebRepo(db_session)
    try:
        raw = [
            {
                "enodeb_id": TEST_ENODEB_ID,
                "ten_he_thong": "4G-TESTB5-001",
                "ma_tinh": "01",
                "longitude": 0,  # API_CONTRACTS.md SS4 dong 302 - 0 -> luu NULL
                "latitude": 20.9876,
                "ma_csht": "CSHT-TEST-B5",
                "ten_thiet_bi": "Nokia AirScale",
            }
        ]
        count = await repo.upsert_many(raw)
        assert count == 1

        row = (
            await db_session.execute(select(TramModel).where(TramModel.tram_id == TEST_ENODEB_ID))
        ).scalar_one()
        assert row.tram_name == "4G-TESTB5-001"
        assert row.longitude is None
        assert float(row.latitude) == 20.9876
        assert row.ma_csht == "CSHT-TEST-B5"
    finally:
        await _cleanup(db_session)


async def test_upsert_many_conflict_update_khong_tao_duplicate(db_session):
    await _cleanup(db_session)
    repo = EnodebRepo(db_session)
    try:
        raw = [
            {
                "enodeb_id": TEST_ENODEB_ID,
                "ten_he_thong": "4G-TESTB5-001",
                "ma_tinh": "01",
                "longitude": 105.8412,
                "latitude": 20.9876,
                "ma_csht": "CSHT-TEST-B5",
                "ten_thiet_bi": "Nokia AirScale",
            }
        ]
        await repo.upsert_many(raw)

        raw[0]["ten_he_thong"] = "4G-TESTB5-001-RENAMED"
        await repo.upsert_many(raw)

        rows = (
            (await db_session.execute(select(TramModel).where(TramModel.tram_id == TEST_ENODEB_ID)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].tram_name == "4G-TESTB5-001-RENAMED"
    finally:
        await _cleanup(db_session)


async def test_find_theo_q_tra_ve_tram_domain_entity(db_session):
    await _cleanup(db_session)
    repo = EnodebRepo(db_session)
    try:
        await repo.upsert_many(
            [
                {
                    "enodeb_id": TEST_ENODEB_ID,
                    "ten_he_thong": "4G-TESTB5-001",
                    "ma_tinh": "01",
                    "longitude": 105.8412,
                    "latitude": 20.9876,
                    "ma_csht": "CSHT-TEST-B5",
                    "ten_thiet_bi": "Nokia AirScale",
                }
            ]
        )

        found = await repo.find("TEST_B5_ENODEB")
        assert len(found) == 1
        tram = found[0]
        assert tram.tram_id == TEST_ENODEB_ID
        assert tram.tram_name == "4G-TESTB5-001"
        assert tram.trang_thai == "active"
    finally:
        await _cleanup(db_session)


# --- sort_by/order (22072026) cho GET /stations ---
_SORT_TEST_IDS = ["TEST_B5_ST_1", "TEST_B5_ST_2", "TEST_B5_ST_3", "TEST_B5_ST_4"]
# tram_name CO CHU Y xao tron so voi thu tu tram_id (ST_1..ST_4) - de phan
# biet ro sort_by=tram_name THAT SU sort lai, khong phai trung hop giong thu
# tu mac dinh (tram_id tang dan).
_SORT_TEST_NAMES = {
    "TEST_B5_ST_1": "4G-ZZZ-HNI",  # tram_id nho nhat nhung ten LON NHAT
    "TEST_B5_ST_2": "4G-AAA-HNI",  # ten NHO NHAT
    "TEST_B5_ST_3": "4G-MMM-HNI",
    "TEST_B5_ST_4": "4G-BBB-HNI",
}


async def _cleanup_sort_test(db_session):
    for tram_id in _SORT_TEST_IDS:
        await db_session.execute(delete(TramModel).where(TramModel.tram_id == tram_id))
    await db_session.commit()


async def _seed_sort_test(repo: EnodebRepo):
    await repo.upsert_many(
        [
            {
                "enodeb_id": tram_id,
                "ten_he_thong": _SORT_TEST_NAMES[tram_id],
                "ma_tinh": "01",
                "longitude": 105.8,
                "latitude": 21.0,
                "ma_csht": None,
                "ten_thiet_bi": "Nokia AirScale",
            }
            for tram_id in _SORT_TEST_IDS
        ]
    )


async def test_find_stations_sort_by_tram_name_asc(db_session):
    await _cleanup_sort_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_sort_test(repo)
        rows = await repo.find_stations("TEST_B5_ST_", None, 0, 10, sort_by="tram_name", order="asc")
        names = [r["tram_name"] for r in rows]
        assert names == ["4G-AAA-HNI", "4G-BBB-HNI", "4G-MMM-HNI", "4G-ZZZ-HNI"]
    finally:
        await _cleanup_sort_test(db_session)


async def test_find_stations_sort_by_tram_name_desc(db_session):
    await _cleanup_sort_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_sort_test(repo)
        rows = await repo.find_stations("TEST_B5_ST_", None, 0, 10, sort_by="tram_name", order="desc")
        names = [r["tram_name"] for r in rows]
        assert names == ["4G-ZZZ-HNI", "4G-MMM-HNI", "4G-BBB-HNI", "4G-AAA-HNI"]
    finally:
        await _cleanup_sort_test(db_session)


async def test_find_stations_khong_truyen_sort_by_giu_nguyen_tram_id_tang_dan(db_session):
    # KHONG regression - hanh vi mac dinh TRUOC khi co task nay la
    # TramModel.tram_id TANG DAN (khong phai desc), phai giu nguyen y het.
    await _cleanup_sort_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_sort_test(repo)
        rows = await repo.find_stations("TEST_B5_ST_", None, 0, 10)  # khong truyen sort_by/order
        ids = [r["tram_id"] for r in rows]
        assert ids == _SORT_TEST_IDS  # dung thu tu tang dan cu, khong bi doi
    finally:
        await _cleanup_sort_test(db_session)


async def test_find_stations_sort_ap_truoc_phan_trang(db_session):
    # Muc dich CHINH cua task: page 1 (offset=0, limit=2) sort theo tram_name
    # asc phai tra dung 2 ban ghi DAU cua TOAN BO 4 ban ghi da sort (AAA, BBB)
    # - KHONG phai 2 ban ghi dau theo thu tu tram_id roi moi sort trong do.
    await _cleanup_sort_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_sort_test(repo)
        page1 = await repo.find_stations("TEST_B5_ST_", None, 0, 2, sort_by="tram_name", order="asc")
        names_page1 = [r["tram_name"] for r in page1]
        assert names_page1 == ["4G-AAA-HNI", "4G-BBB-HNI"]

        page2 = await repo.find_stations("TEST_B5_ST_", None, 2, 2, sort_by="tram_name", order="asc")
        names_page2 = [r["tram_name"] for r in page2]
        assert names_page2 == ["4G-MMM-HNI", "4G-ZZZ-HNI"]
    finally:
        await _cleanup_sort_test(db_session)


async def test_find_stations_sort_by_ngoai_whitelist_khong_crash_giu_mac_dinh(db_session):
    # Repo tu whitelist (an toan 2 lop, khong chi tin router da Literal-
    # validate) - neu bi goi truc tiep voi sort_by khong hop le (vd tu code
    # khac ngoai router trong tuong lai), KHONG duoc getattr() mu vao
    # TramModel (AttributeError kho hieu neu field khong ton tai) - phai roi
    # ve default order (tram_id tang dan) thay vi crash.
    await _cleanup_sort_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_sort_test(repo)
        rows = await repo.find_stations("TEST_B5_ST_", None, 0, 10, sort_by="trang_thai", order="asc")
        ids = [r["tram_id"] for r in rows]
        assert ids == _SORT_TEST_IDS  # roi ve default (tram_id tang dan), khong crash
    finally:
        await _cleanup_sort_test(db_session)


# --- khu_vuc (KV1/KV2/KV3, 04/10/2026) cho GET /stations ---
# Moi KV seed 1 tram ma_tinh MOI + 1 tram ma_tinh CU, dai dien day du ca 2
# dang du lieu RIMS co the tra (xem chu y o domain/value_objects/khu_vuc.py).
_KV_TEST_SEED = [
    ("TEST_B5_KV_1A", "HNI", "KV1"),  # ma moi
    ("TEST_B5_KV_1B", "HDG", "KV1"),  # ma cu (Ha Dong/Ha Tay)
    ("TEST_B5_KV_2A", "HCM", "KV2"),  # ma moi
    ("TEST_B5_KV_2B", "VTU", "KV2"),  # ma cu (Ba Ria-Vung Tau)
    ("TEST_B5_KV_3A", "DLC", "KV3"),  # ma moi (Dak Lak moi)
    ("TEST_B5_KV_3B", "DLK", "KV3"),  # ma cu (Dak Lak cu)
    ("TEST_B5_KV_X", "XYZ", None),  # ma la - khong thuoc KV nao
]
_KV_TEST_IDS = [row[0] for row in _KV_TEST_SEED]


async def _cleanup_kv_test(db_session):
    for tram_id in _KV_TEST_IDS:
        await db_session.execute(delete(TramModel).where(TramModel.tram_id == tram_id))
    await db_session.commit()


async def _seed_kv_test(repo: EnodebRepo):
    await repo.upsert_many(
        [
            {
                "enodeb_id": tram_id,
                "ten_he_thong": f"4G-{tram_id}",
                "ma_tinh": ma_tinh,
                "longitude": 105.8,
                "latitude": 21.0,
                "ma_csht": None,
                "ten_thiet_bi": "Nokia AirScale",
            }
            for tram_id, ma_tinh, _kv in _KV_TEST_SEED
        ]
    )


async def test_find_stations_khu_vuc_field_suy_tu_ma_tinh(db_session):
    await _cleanup_kv_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_kv_test(repo)
        rows = await repo.find_stations("TEST_B5_KV_", None, 0, 20)
        kv_theo_id = {r["tram_id"]: r["khu_vuc"] for r in rows}
        for tram_id, _ma_tinh, kv_ky_vong in _KV_TEST_SEED:
            assert kv_theo_id[tram_id] == kv_ky_vong
    finally:
        await _cleanup_kv_test(db_session)


async def test_find_stations_loc_1_khu_vuc(db_session):
    await _cleanup_kv_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_kv_test(repo)
        rows = await repo.find_stations("TEST_B5_KV_", None, 0, 20, khu_vuc=["KV1"])
        ids = {r["tram_id"] for r in rows}
        assert ids == {"TEST_B5_KV_1A", "TEST_B5_KV_1B"}

        total = await repo.count_stations("TEST_B5_KV_", None, khu_vuc=["KV1"])
        assert total == 2
    finally:
        await _cleanup_kv_test(db_session)


async def test_find_stations_loc_2_khu_vuc(db_session):
    await _cleanup_kv_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_kv_test(repo)
        rows = await repo.find_stations("TEST_B5_KV_", None, 0, 20, khu_vuc=["KV1", "KV3"])
        ids = {r["tram_id"] for r in rows}
        assert ids == {"TEST_B5_KV_1A", "TEST_B5_KV_1B", "TEST_B5_KV_3A", "TEST_B5_KV_3B"}

        total = await repo.count_stations("TEST_B5_KV_", None, khu_vuc=["KV1", "KV3"])
        assert total == 4
    finally:
        await _cleanup_kv_test(db_session)


async def test_find_stations_khong_truyen_khu_vuc_khong_loc(db_session):
    await _cleanup_kv_test(db_session)
    repo = EnodebRepo(db_session)
    try:
        await _seed_kv_test(repo)
        rows = await repo.find_stations("TEST_B5_KV_", None, 0, 20)
        assert len(rows) == len(_KV_TEST_SEED)  # ca ma la (TEST_B5_KV_X) cung tra ve
    finally:
        await _cleanup_kv_test(db_session)


async def test_sql_that_tong_3_kv_khop_tong_tram_hop_le(db_session):
    # Kiem tra DOC lai toan bo bang tram THAT (khong phai du lieu seed) - tong
    # so tram cua 3 KV cong lai PHAI bang tong so tram co ma_tinh hop le (khong
    # NULL va khong phai ma la). Khoa nhat quan giua bang anh xa (Python) va du
    # lieu THAT, tranh regression neu co ma_tinh moi xuat hien sau nay.
    rows = (await db_session.execute(select(TramModel.ma_tinh, func.count()).group_by(TramModel.ma_tinh))).all()

    tong_theo_kv = {"KV1": 0, "KV2": 0, "KV3": 0}
    tong_ma_la = 0
    tong_null = 0
    for ma_tinh, so_luong in rows:
        if ma_tinh is None:
            tong_null += so_luong
            continue
        kv = khu_vuc_tu_ma_tinh(ma_tinh)
        if kv is None:
            tong_ma_la += so_luong
        else:
            tong_theo_kv[kv] += so_luong

    # Khao sat 04/10/2026 (xac nhan voi user): 0 ma la, KV1=21312/KV2=24622/
    # KV3=13982, tong 3 KV=59916, NULL=86. Assert tong_ma_la==0 (bat buoc,
    # dung hanh vi "KHONG tu doan") - KHONG assert cung so tuyet doi vi du
    # lieu RIMS co the thay doi theo thoi gian (tram moi duoc them/xoa).
    assert tong_ma_la == 0, f"Phat hien ma_tinh LA chua co trong bang anh xa: tong {tong_ma_la} tram"

    tong_tram_that = sum(so_luong for _ma_tinh, so_luong in rows)
    assert sum(tong_theo_kv.values()) + tong_null == tong_tram_that


async def test_get_all_with_coords_chi_tra_tram_co_toa_do(db_session):
    # BUOC 4b (08/10/2026) - xem domain/ports/outbound/repo_ports.py::IEnodebRepo.
    # Chen 1 tram KHONG toa do (longitude/latitude NULL) de xac nhan bi LOC o
    # SQL (WHERE NOT NULL), khong xuat hien trong ket qua.
    await db_session.execute(delete(TramModel).where(TramModel.tram_id == TEST_ENODEB_ID))
    await db_session.commit()
    row = TramModel(tram_id=TEST_ENODEB_ID, tram_name="4G-TESTB5-KHONG-TOADO", trang_thai="active")
    db_session.add(row)
    await db_session.commit()
    try:
        repo = EnodebRepo(db_session)
        ket_qua = await repo.get_all_with_coords()

        assert TEST_ENODEB_ID not in {r["tram_id"] for r in ket_qua}
        assert len(ket_qua) > 0
        mau = ket_qua[0]
        # ma_tinh THEM (BUOC 4c, 10/10/2026) - xem IEnodebRepo.get_all_with_coords().
        assert set(mau) == {"tram_id", "tram_name", "longitude", "latitude", "ten_thiet_bi", "ma_tinh"}
        assert all(r["longitude"] is not None and r["latitude"] is not None for r in ket_qua)
    finally:
        await db_session.execute(delete(TramModel).where(TramModel.tram_id == TEST_ENODEB_ID))
        await db_session.commit()
