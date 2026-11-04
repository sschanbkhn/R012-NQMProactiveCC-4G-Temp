# DEPLOY — R012-NQMProactiveCC-4G

Server BE: `10.155.43.196`, port **8080**, thu muc
`/home/auto/Python_Project/R012-NQMProactiveCC-4G`
Server FE: `10.155.43.197`, port 80

Service systemd: **`r012-nqmproactivecc`** (xac nhan 23/10/2026 bang `systemctl cat`):
```
WorkingDirectory=/home/auto/Python_Project/R012-NQMProactiveCC-4G
EnvironmentFile=/home/auto/Python_Project/R012-NQMProactiveCC-4G/.env
ExecStart=.../venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
```

### Quy tac `.env` tren .196

- Service nap `.env` bang **systemd `EnvironmentFile=`** (truoc ca `load_dotenv()`
  trong code, va `load_dotenv` KHONG ghi de bien systemd da nap).
- Vi vay `.env` phai giu **MOI BIEN 1 DONG**. **KHONG viet JSON nhieu dong** trong
  `.env` — systemd khong hieu gia tri nhieu dong, bien bi gan sai va app chet luc
  doc JSON.
- Sua `.env` **phai restart** service moi co hieu luc (bien moi truong chi nap luc
  khoi dong).
- Sua file JSON NetAct (`NETACT_SERVERS_FILE`, xem duoi): CR ke tiep da doc file
  moi (file doc lai moi lan chon OSS), nhung **van restart** de buoc kiem tra luc
  khoi dong chay lai va in trang thai tung NA — khong restart thi khong ai biet
  file vua sua co hop le khong.
- `.env` va file JSON NetAct **khong nam trong goi deploy** (`git archive` chi lay
  file trong git) — moi thay doi phai sua truc tiep tren .196.

---

## CAU HINH NETACT (`NETACT_SERVERS_FILE`, tu 23/10/2026)

Moi NA co mat khau / han mat khau RIENG (do 23/10/2026: mat khau moi vao duoc
NA09 + NA14, NA10/11/12 tu choi). Cau hinh NetAct tach ra 1 file JSON nhieu dong,
moi NA 1 khoi, moi mat khau xuat hien DUNG 1 LAN — doi mat khau NA nao sua dung
khoi NA do.

| Muc | Gia tri tren .196 |
|---|---|
| File | `/home/auto/secrets/r012_netact_servers.json` |
| Quyen | file `600`, thu muc `/home/auto/secrets` `700`, chu so huu `auto` |
| Khai bao trong `.env` | `NETACT_SERVERS_FILE=/home/auto/secrets/r012_netact_servers.json` |
| File mau trong repo | `netact_servers.example.json` (password de trong) |

**Thu tu uu tien:** `NETACT_SERVERS_FILE` → `NETACT_SERVERS` (JSON 1 dong trong
`.env`, giu de tuong thich nguoc / du phong). Khi FILE da chay on dinh qua vai CR
that, **co the xoa dong `NETACT_SERVERS`** khoi `.env` o lan sua sau.

**Bang NA** (dinh dang file: `instances` + `routes` khoa `"<ma_tinh>|NOKIA"`):

| NA | Host | NOC | Tinh (route) | So tinh |
|---|---|---|---|---|
| NA09 | 10.212.242.20 | NOC1 | HNI | 1 |
| NA10 | 10.212.243.20 | NOC2 | DNO, HCM, BPC, BTN, LDG, TNH, CTO, AGG, BTE, BDG, DNI | 11 |
| NA11 | 10.212.244.20 | NOC3 | DLK, GLI, KTM, NTN | 4 |
| NA12 | 10.212.245.20 | NOC2 | BLU, CMU, HUG, KGG, STG | 5 |
| NA14 | 10.212.247.20 | NOC1 | CBG, DBN, SLA, HGG, LCU, LSN, LCI | 7 |

Tat ca dung chung user `thembv`. Ten NA (`NA09`...) la khoa `netact` cua bang
`ho_neighbor` va gia tri `cr_session.oss_instance_id` — KHONG doi ten NA.

**Kiem tra luc khoi dong** (`adapters/netact/oss_router_env.py::kiem_tra_khi_khoi_dong`),
log mong doi khi du 5 NA:
```
NetAct: nguon cau hinh NETACT_SERVERS_FILE=/home/auto/secrets/r012_netact_servers.json, 5 NA, 28 route
NetAct NA09 host=10.212.242.20 user=thembv noc=NOC1 so_tinh=1 trang_thai=OK
NetAct NA10 host=10.212.243.20 user=thembv noc=NOC2 so_tinh=11 trang_thai=OK
... (NA11 4, NA12 5, NA14 7 - ca 5 trang_thai=OK)
```
- File khai bao ma khong ton tai / JSON sai cu phap → **app khong len**
  (`systemctl status` bao loi, ghi ten bien + duong dan, khong in noi dung file).
- 1 NA thieu host/user/password, hoac route tro toi NA khong co → app VAN len, log
  `WARNING NetAct cau hinh: ...`; CR vao tinh thuoc NA do bi tu choi voi
  `ma_loi=CAU_HINH_NETACT_LOI`, message dang `NA14 cau hinh loi: thieu password`
  (chi ten NA, khong host/IP, khong mat khau).

---

## DOI MAT KHAU NETACT

Ap dung moi lan doi mat khau `thembv` tren 1 hay nhieu NA. Chi doi NA nao vua
doi — loc theo **host** (cac NA khac giu nguyen, moi NA mat khau rieng). Dung
`scripts/doi_mat_khau_netact.py`: nhap mat khau bang getpass (khong nam tren dong
lenh, khong in ra), tu backup moi file truoc khi ghi (`.bak_<thoi_gian>`, quyen
600). **Khong sua tay bang nano** — de go sai dau ngoac/phay hoac sua nham NA.

```bash
cd /home/auto/Python_Project/R012-NQMProactiveCC-4G

# 1. Doi password cho host vua doi (vd NA14), CA file JSON lan dong du phong trong .env
venv/bin/python scripts/doi_mat_khau_netact.py --host 10.212.247.20 \
    --file /home/auto/secrets/r012_netact_servers.json --env .env
#    bang in ra: dung NA cua host do "DA DOI", cac NA khac "giu nguyen"

# 2. Restart + cho ~10s + xem log khoi dong (5 NA, 28 route, ca 5 OK)
sudo systemctl restart r012-nqmproactivecc && sleep 10
journalctl -u r012-nqmproactivecc -n 80 --no-pager | grep NetAct

# 3. Thu SSH tu .196 toi NA vua doi (go mat khau bang tay, 1 LAN)
ssh thembv@10.212.247.20 hostname

# 4. Sau khi 1 CR that chay on: xoa backup
rm /home/auto/secrets/r012_netact_servers.json.bak_* .env.bak_*
```
Thu SSH tay **1 lan** moi NA — nhieu lan sai co the khoa tai khoan `thembv` dung
chung cho ca 5 NA.

| NA | Host (dung cho `--host`) |
|---|---|
| NA09 | 10.212.242.20 |
| NA10 | 10.212.243.20 |
| NA11 | 10.212.244.20 |
| NA12 | 10.212.245.20 |
| NA14 | 10.212.247.20 |

---

## CHUYEN SANG `NETACT_SERVERS_FILE` LAN DAU TREN .196 (23/10/2026)

Lam 1 lan. Nguyen tac:
- Chay convert tu **`.env` cua chinh .196** (dang o dinh dang moi, du 5 NA).
  **KHONG copy file JSON tu may dev** — `.env` may dev la ban THIEU (chi NA09 +
  NA14), copy len se lam mat NA10/11/12.
- Chi doi password **NA09 va NA14** (2 NA da doi mat khau moi), bang script
  getpass. **NA10/11/12 giu nguyen**.
- Log khoi dong phai la **5 NA, 28 route, ca 5 `trang_thai=OK`**. Khong dung thi
  **rollback** (muc duoi).

```bash
# --- 1. Backup thu muc BE (khong venv) + .env; kiem commit dang chay ---
TS=$(date +%Y%m%d_%H%M); echo $TS            # GHI LAI, dung cho cac buoc sau
mkdir -p /home/auto/backup && chmod 700 /home/auto/backup
cd /home/auto/Python_Project/R012-NQMProactiveCC-4G
tar -czf /home/auto/backup/be_truoc_$TS.tar.gz --exclude=./venv --exclude=__pycache__ .
chmod 600 /home/auto/backup/be_truoc_$TS.tar.gz          # backup co .env -> chua mat khau
cp -p .env .env.bak_$TS && chmod 600 .env.bak_$TS
curl -s http://127.0.0.1:8080/api/v1/version | python3 -c "import sys,json;print(json.load(sys.stdin).get('commit_short'))"
#   KET QUA PHAI LA 43d259e. Khac -> DUNG, chua lam buoc 2, bao lai.

# --- 2. Giai nen goi moi (ghi de code; .env, venv khong nam trong goi) ---
tar -xzf /tmp/r012_be_<hash>.tar.gz
cat VERSION                                              # commit_short = <hash>

# --- 3. Convert NETACT_SERVERS cua .196 -> file JSON (quyen 600) ---
mkdir -p /home/auto/secrets && chmod 700 /home/auto/secrets
venv/bin/python scripts/convert_netact_servers.py \
    --env .env --out /home/auto/secrets/r012_netact_servers.json
#   Bang in ra PHAI co NA09 1 | NA10 11 | NA11 4 | NA12 5 | NA14 7 tinh, password "co".
#   Thieu NA / so tinh lech / bao LOI -> DUNG, bao lai.

# --- 4. Doi password NA09 + NA14 (getpass), ca file JSON lan dong du phong trong .env ---
venv/bin/python scripts/doi_mat_khau_netact.py \
    --host 10.212.242.20 --host 10.212.247.20 \
    --file /home/auto/secrets/r012_netact_servers.json --env .env
#   PHAI thay: NA09, NA14 "DA DOI"; NA10, NA11, NA12 "giu nguyen" (ca [file] lan [env])

# --- 5. Them NETACT_SERVERS_FILE vao .env (khong them trung, dam bao xuong dong) ---
if grep -q '^NETACT_SERVERS_FILE=' .env; then
    echo "da co NETACT_SERVERS_FILE - khong them"
else
    [ -n "$(tail -c1 .env)" ] && echo >> .env
    echo 'NETACT_SERVERS_FILE=/home/auto/secrets/r012_netact_servers.json' >> .env
fi
grep -n '^NETACT_SERVERS_FILE=' .env                     # dung 1 dong
sudo systemctl restart r012-nqmproactivecc && sleep 10
sudo systemctl status r012-nqmproactivecc --no-pager | head -5
journalctl -u r012-nqmproactivecc -n 80 --no-pager | grep NetAct
#   PHAI thay: "nguon cau hinh NETACT_SERVERS_FILE=..., 5 NA, 28 route"
#              5 dong NA09..NA14 trang_thai=OK, khong co WARNING NetAct
curl -s http://127.0.0.1:8080/api/v1/version             # commit_short = <hash>

# --- 6. Kiem tra tren FE ---
#   a) Xem truoc + Trigger 1 CR tram HNI: "NetAct se dung: NA09" -> DONE/PARTIAL_SUCCESS;
#      Lich su CR: oss_instance_id = NA09.
#   b) CHI Xem truoc (KHONG Trigger) 1 tram NA14 (vd tinh HGG/CBG): "NetAct se dung: NA14",
#      khong loi CAU_HINH_NETACT_LOI.
#   c) CHI Xem truoc (KHONG Trigger) 1 tram NA10 (vd tinh HCM/DNI): "NetAct se dung: NA10",
#      khong loi CAU_HINH_NETACT_LOI.
#   (Xem truoc chi doc HO trong DB, KHONG SSH len NetAct - khong ton luot dang nhap.)
```

**Rollback phuong an 1 — chi `.env`** (log khong du 5 NA OK, app khong len vi
cau hinh NetAct). `.env.bak_<TS>` la ban TRUOC khi doi mat khau -> NA09/NA14 con
mat khau CU, khoi phuc xong phai doi lai 2 host do roi moi restart:
```bash
cd /home/auto/Python_Project/R012-NQMProactiveCC-4G
cp -p .env.bak_<TS> .env                                 # bo NETACT_SERVERS_FILE
venv/bin/python scripts/doi_mat_khau_netact.py \
    --host 10.212.242.20 --host 10.212.247.20 --env .env  # NA09/NA14 -> mat khau moi
sudo systemctl restart r012-nqmproactivecc && sleep 10
journalctl -u r012-nqmproactivecc -n 80 --no-pager | grep NetAct   # nguon = NETACT_SERVERS
```
Code moi van doc `NETACT_SERVERS` khi khong co `NETACT_SERVERS_FILE`.

**Rollback phuong an 2 — ve code cu** (code moi co loi KHAC, khong lien quan
NetAct: app khong len, API loi...):
```bash
cd /home/auto/Python_Project
sudo systemctl stop r012-nqmproactivecc
mv R012-NQMProactiveCC-4G R012-NQMProactiveCC-4G.loi_<TS>
mkdir R012-NQMProactiveCC-4G
tar -xzf /home/auto/backup/be_truoc_<TS>.tar.gz -C R012-NQMProactiveCC-4G   # backup KHONG co venv
mv R012-NQMProactiveCC-4G.loi_<TS>/venv R012-NQMProactiveCC-4G/              # dung lai venv
cp -p R012-NQMProactiveCC-4G.loi_<TS>/.env.bak_<TS> R012-NQMProactiveCC-4G/.env
# Code cu KHONG co script doi mat khau -> goi script tu thu muc code moi (.loi_<TS>),
# script chi dung stdlib nen chay duoc voi venv nao cung duoc:
R012-NQMProactiveCC-4G/venv/bin/python R012-NQMProactiveCC-4G.loi_<TS>/scripts/doi_mat_khau_netact.py \
    --host 10.212.242.20 --host 10.212.247.20 --env R012-NQMProactiveCC-4G/.env
sudo systemctl start r012-nqmproactivecc && sleep 10
curl -s http://127.0.0.1:8080/api/v1/version             # = 43d259e
```
File `/home/auto/secrets/r012_netact_servers.json` de nguyen (code cu khong doc).

**File JSON bi sua hong khi app dang chay:** router giu cau hinh hop le GAN NHAT
trong bo nho, log `ERROR NetAct cau hinh HONG, dung ban hop le gan nhat` (khong in
noi dung file), CR van chay. Restart voi file hong thi app KHONG len — sua file
truoc khi restart. Chua tung doc duoc lan nao → CR/preview tra 422
`CAU_HINH_NETACT_LOI`.

---

## VI SAO CO FILE VERSION

Server `.196` **khong co thu muc `.git`** — deploy bang `rsync`/`scp`, copy tay.
Nghia la dung tren server thi khong co cach nao hoi "dang chay commit nao":
khong `git log`, khong `git rev-parse`, khong `git status`.

Day khong phai lo ngai ly thuyet. **Da dan den ket luan sai that (13/09/2026):**
`docs/audit/BE_AUDIT.md` muc J ket luan *"6 commit chua deploy"* dua tren gia dinh
`.196` = `a3c0656`. Nhung `docs/audit/FE_AUDIT.md` do live thay OpenAPI khai **20
path**, trong khi `a3c0656` chi co **18** — tuc `.196` that ra da o `beccf98` hoac
moi hon. Ket luan sai theo huong nguy hiem: bao "chua deploy" cho thu **da deploy roi**.

File `VERSION` do `scripts/make_version.*` sinh ra **luc build tren may dev** (noi
co `.git`), roi **di theo bundle** sang server. `GET /api/v1/version` chi doc lai
file do.

`VERSION` nam trong `.gitignore` — noi dung khac nhau moi lan build, khong phai ma nguon.

---

## 3 BUOC DEPLOY

### Buoc 1 — Sinh VERSION (tren may dev)

Windows (may dev hien tai):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_version.ps1
```

Linux/macOS/Git Bash:
```bash
bash scripts/make_version.sh
```

Ket qua — file `VERSION` o goc repo, dung 5 dong:
```
commit=2838d5b1f4c8e9a03b7d5e2f1a6c4d8b9e0f3a21
commit_short=2838d5b
commit_date=2026-09-07T16:42:10+07:00
build_at=2026-09-14T03:15:22Z
dirty=false
```

> **`dirty=true` la canh bao, khong phai loi.** No nghia la dang dong goi ma nguon
> **chua commit** (ke ca file moi chua `git add`). Khi do `commit_short` ghi trong
> file **KHONG mo ta dung** thu se chay tren server — khong truy nguoc duoc. Neu
> khong phai hotfix gap: commit truoc, chay lai script.

### Buoc 2 — Copy len server

`VERSION` **phai nam trong bo file mang di**. Neu dong goi bundle thu cong, kiem
lai la no co trong danh sach — file bi `.gitignore` nen cac lenh dong goi dua tren
`git archive` / `git ls-files` se **bo sot no**.

```bash
rsync -av --exclude venv --exclude __pycache__ --exclude .git \
      ./ auto@10.155.43.196:/home/auto/Python_Project/R012-NQMProactiveCC-4G/
```

### Buoc 3 — Restart service (tren server)

```bash
sudo systemctl restart r012-nqmproactivecc
sleep 10
sudo systemctl status  r012-nqmproactivecc
journalctl -u r012-nqmproactivecc -n 50 --no-pager   # xem log khoi dong
```

---

## KIEM TRA SAU DEPLOY

```bash
curl -s http://10.155.43.196:8080/api/v1/version
```

**Dung — ban sach, truy nguoc duoc:**
```json
{
  "commit": "2838d5b1f4c8e9a03b7d5e2f1a6c4d8b9e0f3a21",
  "commit_short": "2838d5b",
  "commit_date": "2026-09-07T16:42:10+07:00",
  "build_at": "2026-09-14T03:15:22Z",
  "dirty": false
}
```

Doi chieu voi repo tren may dev:
```bash
git log --oneline -1 2838d5b        # commit do la gi
git log --oneline 2838d5b..HEAD     # con bao nhieu commit chua len server
```

**Ban build tu working tree ban:**
```json
{ "commit": "...", "dirty": true, "warning": "Ban nay build tu working tree BAN (dirty=true)..." }
```
-> `commit` **khong dang tin**. Phai hoi nguoi deploy da sua gi.

**Thieu file VERSION:**
```json
{ "commit": null, "commit_short": null, "commit_date": null, "build_at": null,
  "dirty": null,
  "warning": "Khong tim thay file VERSION. Ban nay deploy KHONG qua scripts/make_version..." }
```
-> Ban nay deploy **khong qua quy trinh**. Khong truy nguoc duoc; phai deploy lai theo 3 buoc tren.

Ba truong hop deu tra **HTTP 200**. Endpoint chan doan co y **khong bao gio tra
500** — luc su co la luc can no nhat, va "thieu file VERSION" tu no da la mot cau
tra loi co ich. Endpoint cung **khong cham DB, khong goi use case** nen tra loi
duoc ngay ca khi DB sap.

---

## CHECKLIST NGAN

- [ ] `git status` sach (neu khong: chap nhan `dirty=true` va ghi ro ly do)
- [ ] Chay `make_version.ps1` / `make_version.sh`
- [ ] Doc lai file `VERSION` — dung commit dinh deploy, `dirty=false`
- [ ] Copy len server, **co ca file `VERSION`**
- [ ] Restart service
- [ ] `curl .../api/v1/version` — khop `commit_short` vua sinh
- [ ] `git log --oneline <commit>..HEAD` — xac nhan dung so commit con lai

---

## GHI CHU

- **Package offline:** server khong co internet. Cai them thu vien:
  ```bash
  pip3 install --no-index \
    --find-links=/home/auto/Python_Project/Package/python_packages/ \
    --break-system-packages <package>
  ```
  Them dependency moi thi phai copy tay wheel sang thu muc do truoc — xem muc
  DEPLOY trong `docs/DEV_LOG.md`.

- **Migration:** `alembic upgrade` **khong** nam trong 3 buoc tren. Chay migration
  la viec rieng, phai duoc duyet truoc. Luu y `cell_infor` (27.763 dong du lieu RF
  that) **khong co migration** va duoc bao ve boi `include_object()` trong
  `alembic/env.py:103` — dung tat filter do.

- **FE (`.197`):** deploy rieng, khong dung file `VERSION` nay. Bundle FE nhung
  `R012_API_URL` **luc build** (`webpack.config.js:122-124`) nen doi dia chi BE
  la phai build lai bundle FE.
