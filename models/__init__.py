"""
SQLModel table models — biet ve DB (tablename, FK, Column). KHONG import vao domain/.
Tu: ARCHITECTURE.md Section 9 (Mapping Rule); DB_SCHEMA.md
"""

from sqlmodel import SQLModel

# Ca 8 bang R012 nam trong schema rieng "system_nsn_nqmproactivecc" - dung quy uoc
# multi-system da co san tren instance Postgres dung chung (system_nsn_had,
# system_nsn_prbsloadcell, ...: moi he thong 1 schema doc lap).
#
# Chon set 1 lan qua SQLModel.metadata.schema thay vi lap __table_args__ =
# {"schema": ...} o ca 8 file model: gon hon, khong the quen o 1 file nao do.
# Da verify bang code that: Table khong tu khai bao schema rieng se ke thua
# metadata.schema nay, VA cac ForeignKey khong-qualified san co trong 8 model
# (vd sa.ForeignKey("tram.tram_id"), sa.ForeignKey("cr_session.id") self-ref)
# van tu resolve dung sang cung schema — khong can sua chuoi ForeignKey nao.
#
# QUAN TRONG: dong nay phai chay TRUOC khi bat ky class SQLModel table nao duoc
# dinh nghia. Dat o day (models/__init__.py) dam bao dieu do: Python luon chay
# package __init__.py truoc khi import submodule (vd `from models.tram import
# Tram` -> chay models/__init__.py truoc, roi moi chay models/tram.py).
SQLModel.metadata.schema = "system_nsn_nqmproactivecc"
