# Sinh file VERSION o goc repo de truy vet ban dang chay tren server.
#
# VI SAO CAN: server .196 khong co .git (deploy bang rsync/scp) nen tren do
# khong hoi duoc "dang chay commit nao". Script nay chay TREN MAY DEV (noi CO
# .git), ket qua di theo bundle sang server. Xem docs/DEPLOY.md.
#
# Chay:  powershell -ExecutionPolicy Bypass -File scripts\make_version.ps1
# Ban bash tuong duong: scripts/make_version.sh
#
# Ban PowerShell la ban CHINH tren may dev nay (Windows). Hai ban phai sinh ra
# file GIONG HET nhau - sua 1 ban thi sua ca ban kia.

$ErrorActionPreference = "Stop"

# Goc repo suy tu vi tri script, KHONG dung thu muc hien tai: script phai cho
# ket qua giong nhau du goi tu goc repo hay tu trong scripts\.
$GocRepo = Split-Path -Parent $PSScriptRoot
$FileVersion = Join-Path $GocRepo "VERSION"

Push-Location $GocRepo
try {
    git rev-parse --is-inside-work-tree 2>$null | Out-Null
    if (-not $?) {
        Write-Error "LOI: $GocRepo khong phai git repo. Script nay chi chay tren MAY DEV. Tren server khong co .git - do chinh la ly do file VERSION ton tai. Xem docs/DEPLOY.md."
        exit 1
    }

    $Commit      = (git rev-parse HEAD).Trim()
    $CommitShort = (git rev-parse --short HEAD).Trim()
    # %cI = committer date dang ISO8601 nghiem ngat (co offset mui gio).
    # Nhay DON bat buoc: khong co nhay thi PowerShell co the dien giai dau %;
    # va KHONG duoc dung token stop-parsing --% o day - no nuot ca phan con lai
    # cua dong nen dau ) dong ngoac bi mat (loi "Missing closing ')'").
    $CommitDate  = (git log -1 '--format=%cI').Trim()
    # UTC, khop quy uoc luu thoi diem cua project (BUSINESS_RULES.md SS7.2).
    $BuildAt     = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")

    # --porcelain: rong = sach. Tinh CA file chua track (untracked) - mot file
    # .py moi chua `git add` van se duoc copy len server, nen no PHAI lam dirty.
    $TrangThai = git status --porcelain
    if ([string]::IsNullOrWhiteSpace(($TrangThai -join ""))) {
        $Dirty = "false"
    } else {
        $Dirty = "true"
    }

    $NoiDung = @(
        "commit=$Commit",
        "commit_short=$CommitShort",
        "commit_date=$CommitDate",
        "build_at=$BuildAt",
        "dirty=$Dirty"
    )

    # -Encoding utf8 tuong minh: Set-Content mac dinh dung codepage ANSI cua he
    # thong, file se doc sai khi sang server Linux.
    # Xuong dong LF (khong CRLF): file nay duoc doc tren server Linux; parser
    # .strip() duoc \r nhung de LF cho sach khi `cat VERSION`.
    [System.IO.File]::WriteAllText($FileVersion, ($NoiDung -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))

    Write-Host "Da ghi $FileVersion"
    Get-Content $FileVersion

    if ($Dirty -eq "true") {
        Write-Host ""
        Write-Host "CANH BAO: working tree BAN (dirty=true)." -ForegroundColor Yellow
        Write-Host "  Dang dong goi ma nguon CHUA COMMIT -> commit $CommitShort ghi trong" -ForegroundColor Yellow
        Write-Host "  VERSION KHONG mo ta dung thu se chay tren server." -ForegroundColor Yellow
        Write-Host "  Commit truoc roi chay lai script neu muon truy nguoc duoc." -ForegroundColor Yellow
        # KHONG exit 1: co luc can deploy gap ban va (hotfix). Canh bao that to,
        # nhung quyet dinh la cua nguoi deploy - va dirty=true da nam trong file
        # VERSION nen endpoint /api/v1/version se tu to cao.
    }
}
finally {
    Pop-Location
}
