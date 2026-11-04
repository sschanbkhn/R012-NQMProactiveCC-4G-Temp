#!/usr/bin/env bash
#
# Sinh file VERSION o goc repo de truy vet ban dang chay tren server.
#
# VI SAO CAN: server .196 khong co .git (deploy bang rsync/scp) nen tren do
# khong hoi duoc "dang chay commit nao". Script nay chay TREN MAY DEV (noi CO
# .git), ket qua di theo bundle sang server. Xem docs/DEPLOY.md.
#
# Chay:  bash scripts/make_version.sh
# Ban PowerShell tuong duong: scripts/make_version.ps1 (may dev la Windows)

set -euo pipefail

# Goc repo suy tu vi tri script, KHONG dung $PWD: script phai cho ra ket qua
# giong nhau du goi tu goc repo hay tu trong scripts/.
GOC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE_VERSION="$GOC_REPO/VERSION"

cd "$GOC_REPO"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "LOI: $GOC_REPO khong phai git repo." >&2
    echo "     Script nay chi chay tren MAY DEV. Tren server khong co .git -" >&2
    echo "     do chinh la ly do file VERSION ton tai. Xem docs/DEPLOY.md." >&2
    exit 1
fi

COMMIT="$(git rev-parse HEAD)"
COMMIT_SHORT="$(git rev-parse --short HEAD)"
# %cI = committer date dang ISO8601 nghiem ngat (co offset mui gio).
COMMIT_DATE="$(git log -1 --format=%cI)"
# date -u ... +%Y-%m-%dT%H:%M:%SZ: UTC, khop quy uoc luu thoi diem cua project
# (BUSINESS_RULES.md SS7.2 - DB luu UTC).
BUILD_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --porcelain: rong = sach. Tinh CA file chua track (untracked) - mot file .py
# moi chua `git add` van se duoc rsync mang len server, nen no PHAI lam dirty.
if [ -n "$(git status --porcelain)" ]; then
    DIRTY="true"
else
    DIRTY="false"
fi

cat > "$FILE_VERSION" <<EOF
commit=$COMMIT
commit_short=$COMMIT_SHORT
commit_date=$COMMIT_DATE
build_at=$BUILD_AT
dirty=$DIRTY
EOF

echo "Da ghi $FILE_VERSION"
cat "$FILE_VERSION"

if [ "$DIRTY" = "true" ]; then
    echo ""
    echo "CANH BAO: working tree BAN (dirty=true)."
    echo "  Dang dong goi ma nguon CHUA COMMIT -> commit $COMMIT_SHORT ghi trong"
    echo "  VERSION KHONG mo ta dung thu se chay tren server."
    echo "  Commit truoc roi chay lai script neu muon truy nguoc duoc."
    # KHONG exit 1: co luc can deploy gap ban va (hotfix). Canh bao that to,
    # nhung quyet dinh la cua nguoi deploy - va dirty=true da nam trong file
    # VERSION nen endpoint /api/v1/version se tu to cao.
fi
