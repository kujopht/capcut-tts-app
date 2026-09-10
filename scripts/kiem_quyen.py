#!/usr/bin/env python3
"""Hồ sơ quyền HIỆU LỰC — định nghĩa, áp dụng, và kiểm bằng máy.

VẤN ĐỀ THẬT ĐÃ ĐO ĐƯỢC (2026-09-10), và nó không phải chuyện luật viết sai

Claude Code chỉ nạp `<kho>/.claude/settings.json` và hook `PreToolUse` của
kho **khi thư mục đó đã được TIN**. Đo trực tiếp: một thư mục mới có
`hasTrustDialogAccepted = false` trong `~/.claude.json`, và trong đó

    cat khoa.pem                  -> CHẠY   (đáng ra phải DENY)
    python -c "print(1)"          -> CHẠY   (hook đáng ra chặn)
    sed -i 's/a/b/' README.md     -> CHẠY   (đáng ra phải DENY)
    find . -name "*.py" -delete   -> CHẠY   (đáng ra phải DENY)
    reg add HKCU\\... /f          -> CHẠY   (đáng ra phải DENY)
    ssh ... "sudo systemctl restart fanfic-farmer"  -> CHẠY  (!!)

trong khi `cat .env` và `git reset --hard` VẪN bị chặn — vì hai cái đó
cũng có luật ở tầng NGƯỜI DÙNG. Nói cách khác: cả `settings.json` 241
allow/513 deny của kho và cả 43 KB logic của `guard_indirect_exec.py`
đều **im lặng biến mất** ở một thư mục chưa được tin.

Và "thư mục chưa được tin" đúng là nơi làm việc tự động: mỗi worktree
Router V4 vừa dựng là một thư mục mới.

HỆ QUẢ CHO KIẾN TRÚC — hai nửa, không phải một:

    ~/.claude/settings.json    LUÔN có hiệu lực. Đây là nơi đặt
                               (a) tầng ĐỌC/TÌM an toàn, và
                               (b) tầng CẤM đầy đủ.
    <kho>/.claude/settings.json  chỉ có hiệu lực khi thư mục được tin.
                               Giữ phần đặc thù kho ở đây.

Tệp này giữ ĐỊNH NGHĨA của nửa thứ nhất dưới dạng dữ liệu Python, nên bài
kiểm `import` được đúng thứ đã áp dụng — không có bản JSON thứ hai để
lệch nhau.

VÌ SAO KHÔNG ĐƠN GIẢN THÊM `Bash(grep:*)` VÀO TẦNG NGƯỜI DÙNG

Đã đo (2026-08-28): Claude Code tự cho phép một tập lệnh chỉ-đọc **KÈM
kiểm cờ** — `find` chặn `-delete`/`-exec`, `sed` chỉ nhận biểu thức
chỉ-đọc. Viết `Bash(find:*)` vào `allow` **thay** phép cho-phép-có-kiểm
đó bằng một phép cho-phép vô điều kiện; xác nhận nó mở lại `find -delete`
và `sed -i` thật. Nên tầng người dùng ở đây **cố ý không** mang
`grep/rg/find/sed/cat/head/tail`. Nhu cầu tìm được đáp bằng hai thứ
CHỨNG MINH ĐƯỢC PHẠM VI theo cấu tạo:

    python scripts/tim.py ...   -> xem `scripts/tim.py`
    git grep ...                -> chỉ thấy tệp git theo dõi

DÙNG

    python scripts/kiem_quyen.py --kiem      # báo cáo, mã thoát 0/1
    python scripts/kiem_quyen.py --ap-dung   # ghi tầng thiếu vào ~/.claude
    python scripts/kiem_quyen.py --ma-tran   # in ma trận quyết định
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

GOC = Path(__file__).resolve().parents[1]
NGUOI_DUNG = Path(os.environ.get("CLAUDE_CONFIG_DIR")
                  or (Path.home() / ".claude"))
CAU_HINH_NGUOI_DUNG = NGUOI_DUNG / "settings.json"
CAU_HINH_KHO = GOC / ".claude" / "settings.json"
HOOK_KHO = GOC / ".claude" / "hooks" / "guard_indirect_exec.py"
HOOK_NGUOI_DUNG = NGUOI_DUNG / "hooks" / "guard_indirect_exec.py"

RA = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                      errors="replace", line_buffering=True)

# ============================================================ TẦNG CHO PHÉP ==

#: Gốc kho được coi là "phạm vi phát triển". Luật neo theo ĐƯỜNG TUYỆT ĐỐI
#: nên chúng không nới rộng cho một kho nào khác trên máy.
GOC_PHAT_TRIEN = (
    "C:/FanficWorkers", "C:\\FanficWorkers", "/c/FanficWorkers",
    "C:/Users/nguye/Documents/CapCut-TTS-App",
    "/c/Users/nguye/Documents/CapCut-TTS-App",
)


def _luat_tim() -> List[str]:
    """`tim.py` — một cửa TÌM/ĐỌC duy nhất, không cần `cd`.

    Cả dạng tương đối (chạy từ trong kho) và dạng tuyệt đối (chạy từ bất
    kỳ đâu), vì cái sau là thứ làm `cd` trở nên vô nghĩa thay vì bị cấm.
    """
    ra = [f"Bash({v} scripts/tim.py:*)"
          for v in ("python", "python3", "py -3", "py")]
    for g in GOC_PHAT_TRIEN:
        nhanh = "\\" if "\\" in g else "/"
        ra.append(f"Bash(python {g}{nhanh}*{nhanh}scripts{nhanh}tim.py*)")
        ra.append(f"Bash(python {g}{nhanh}scripts{nhanh}tim.py*)")
    return ra


#: `git` CHỈ-ĐỌC. An toàn để khai tường minh: không một lệnh con nào dưới
#: đây ghi được vào kho, nên luật rộng ở đây không nới thêm quyền nào —
#: khác hẳn `Bash(find:*)`.
GIT_CHI_DOC = (
    "git status", "git diff", "git log", "git show", "git rev-parse",
    "git rev-list", "git merge-base", "git merge-tree", "git ls-files",
    "git ls-tree", "git ls-remote", "git cat-file", "git check-ignore",
    "git blame", "git shortlog", "git describe", "git count-objects",
    "git worktree list", "git grep", "git config --get",
    "git branch --list", "git branch -a", "git branch -r", "git branch -v",
    "git stash list", "git remote -v", "git remote get-url",
    "git for-each-ref", "git symbolic-ref", "git verify-commit",
)

#: Việc phát triển thường ngày. `pytest`/`compileall`/`node --check` không
#: có đường ghi ra ngoài kho, `git worktree add`/`checkout -b` là tạo chứ
#: không phải xoá.
PHAT_TRIEN = (
    "pytest", "python -m pytest", "python3 -m pytest", "py -3 -m pytest",
    "python -m unittest", "python3 -m unittest", "py -3 -m unittest",
    "python -m compileall", "python3 -m compileall",
    "python -m pip list", "python -m pip show", "python -m pip freeze",
    "python -m json.tool",
    "node --check", "npm test", "npm run lint", "npm run typecheck",
    "npm run build", "npm ci", "npx tsc", "npx eslint",
    "git worktree add", "git checkout -b", "git switch -c",
    "git add", "git commit", "git stash list",
    "wc", "sort", "uniq", "comm", "tr", "date", "tasklist", "sha256sum",
    "md5sum", "basename", "dirname", "printf", "echo", "true", "false",
)

#: Script build/nghiệm thu của chính kho này — tên cố định, đường tương đối.
SCRIPT_KHO = (
    "python scripts/tim.py", "python scripts/kiem_quyen.py",
    "python scripts/build_desktop_exe.py",
    "python scripts/control_center_desktop_acceptance.py",
    "python scripts/control_center_v05_acceptance.py",
    "python scripts/control_center_v06_acceptance.py",
    "python scripts/control_center_web_smoke.py",
    "python scripts/control_center_web_anh.py",
    "python scripts/control_center_allowlist_proof.py",
    "python scripts/control_center_attachment_proof.py",
    "python scripts/ai_router_quota_check.py",
)


def tang_cho_phep() -> List[str]:
    ra = _luat_tim()
    ra += [f"Bash({x}:*)" for x in GIT_CHI_DOC]
    ra += ["Bash(git branch)", "Bash(git branch --show-current)"]
    ra += [f"Bash({x}:*)" for x in PHAT_TRIEN]
    ra += [f"Bash({x}:*)" for x in SCRIPT_KHO]
    return ra


# ================================================================ TẦNG CẤM ==

#: Động từ mà TOÁN HẠNG ĐẦU là một ĐƯỜNG DẪN. Chỉ những động từ này được
#: neo bằng glob.
#:
#: `grep`/`rg`/`sed`/`awk` KHÔNG có ở đây, và đó là điểm chính. Toán hạng
#: đầu của chúng là MỘT MẪU, không phải đường dẫn, nên glob
#: `Bash(grep * *.env*)` chặn luôn `grep -c '\\* \\*\\.env' settings.json`
#: — một lệnh tìm CHUỖI ".env" trong một tệp hoàn toàn bình thường. Đo
#: được: chính lệnh đó bị chặn khi chẩn đoán hồ sơ này.
#:
#: Nhóm mẫu-trước được `guard_indirect_exec.secret_file_read()` lo, và nó
#: lo đúng vì nó bỏ qua toán hạng mẫu (`PATTERN_FIRST_OPERAND`). Đây là
#: ranh giới giữa hai lớp: glob cho thứ glob diễn đạt CHÍNH XÁC, hook cho
#: thứ cần biết cấu trúc lệnh.
_DOC_DUONG_DAU = (
    "cat", "bat", "head", "tail", "more", "less", "type", "nl", "od",
    "xxd", "hexdump", "strings", "tac", "base64", "gzip", "tar",
    "cp", "copy", "mv", "move", "tee", "dd", "scp", "rsync", "clip",
    "code", "notepad",
)

#: Động từ mẫu-trước — glob cho chúng là QUÁ RỘNG, bị gỡ khi áp dụng.
_DOC_MAU_TRUOC = ("grep", "egrep", "fgrep", "rg", "ag", "ack", "sed",
                  "awk", "gawk", "cut")

#: BÍ MẬT — chặn theo hình dạng ĐƯỜNG DẪN cho công cụ tệp...
CAM_DOC = (
    "**/.env", "**/.env.*", "**/*.env", "**/.credentials.json",
    "**/credentials.json", "**/.git-credentials", "**/.npmrc",
    "**/.pypirc", "**/.netrc", "**/_netrc",
    "**/id_rsa*", "**/id_ed25519*", "**/id_ecdsa*", "**/id_dsa*",
    "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx", "**/*.ppk",
    "**/*.jks", "**/*.keystore", "**/*.kdbx", "**/*.asc", "**/*.gpg",
    "**/.ssh/**", "**/.aws/**", "**/.azure/**", "**/.gnupg/**",
    "**/.wrangler/**", "**/.docker/config.json", "**/.kube/config",
    "**/gh/hosts.yml", "**/rclone.conf",
    "**/Login Data", "**/Login Data For Account", "**/Cookies",
    "**/Web Data", "**/service-account*.json",
)

#: ...và theo hình dạng CHUỖI LỆNH cho shell. Một luật ở đây chặn cùng lúc
#: `cat`/`head`/`tail`/`grep`/`sed`/`type`/`more`/`Get-Content` — vì nó
#: khớp CẢ chuỗi lệnh chứ không neo vào một động từ nào.
CAM_LENH_BI_MAT = (
    "*.pem*", "*.ppk*", "*.p12*", "*.pfx*", "*.kdbx*",
    "*id_rsa*", "*id_ed25519*", "*id_ecdsa*", "*id_dsa*",
    "*.ssh/*", "*\\.ssh\\*", "*.aws/credentials*", "*.aws\\credentials*",
    "*.gnupg/*", "*.git-credentials*", "*.netrc*", "*.npmrc*", "*.pypirc*",
    "*rclone.conf*", "*credentials.json*", "*gh/hosts.yml*",
    "*worker-prod.env*",
    # `.env` ĐƯỢC NEO THEO ĐỘNG TỪ, không theo hình dạng đường dẫn.
    #
    # Đây là bài học đã đo: một glob neo theo ĐƯỜNG (`*/.env`) chặn cả
    # `git check-ignore -v server/.env`, còn glob neo theo ĐỘNG TỪ thì
    # không — vì `git` không nằm trong danh sách động từ đọc. Cái giá là
    # danh sách dài hơn; cái được là không chặn oan.
    #
    # Lỗ mà cách neo-động-từ để lại (`cd x && cat .env`) do
    # `guard_indirect_exec.secret_file_read()` bịt, và nó bịt CHÍNH XÁC
    # hơn vì nó tách được động từ khỏi toán hạng.
    *[f"{v}{h}" for v in _DOC_DUONG_DAU
      for h in (" *.env", " *.env *", " * *.env", " * *.env *",
                " *.env.*", " * *.env.*")],
    "*Get-Content*.env*", "*Select-String*.env*", "*Import-Csv*.env*",
    "*Default/Cookies*", "*Default\\Cookies*", "*Network/Cookies*",
    "*Network\\Cookies*", "*User Data*Cookies*", "*Login Data*",
    "*cmdkey*", "*VaultCmd*", "*vaultcmd*", "*PasswordVault*",
    "*Get-Credential*", "*Get-StoredCredential*", "*CredentialManager*",
    "*ConvertFrom-SecureString*", "*Export-PfxCertificate*",
    "security find-generic-password*", "gh auth token*",
    "gh secret set*", "gh secret delete*",
)

#: PHÁ HUỶ — hệ tệp và git.
#:
#: `rm -fr` / `rm -r ` có mặt ở đây vì `rm -rf *` MỘT MÌNH là một lỗ:
#: `rm -fr x`, `rm -r -f x`, `rm --recursive --force x` đều là cùng một
#: lệnh mà không khớp luật đó.
CAM_PHA_HUY = (
    "rm -rf *", "rm -fr *", "rm -r *", "rm -f *", "rm --recursive*",
    "rm --force*", "rmdir /s*", "rmdir /S*", "del /s*", "del /f*",
    "del /q*", "*Remove-Item*-Recurse*", "*Remove-Item*-Force*",
    "*rd /s*", "shred *", "*Clear-Disk*", "format *",
    "sed*-i*", "sed*--in-place*",
    "find*-delete*", "find*-exec*", "find*-execdir*", "find*-fprint*",
    "find*-fls*", "find*-ok*",
    "git reset --hard*", "git reset --merge*", "git clean -f*",
    "git clean -d*", "git clean -x*",
    "git branch -D*", "git branch -d*", "git branch --delete*",
    "git branch -M*", "git branch -m*", "git branch --move*",
    "git tag -d*", "git tag --delete*",
    "git worktree remove*", "git worktree prune*",
    "git reflog delete*", "git reflog expire*",
    "git filter-branch*", "git filter-repo*", "git update-ref -d*",
    "git rebase*", "git checkout --orphan*", "git gc --prune=now*",
    "git push --force*", "git push * --force*",
    "git push --force-with-lease*", "git push * --force-with-lease*",
    "git push -f *", "git push * -f *", "git push * -f",
    "git push * +*", "git push --delete*", "git push * --delete*",
    "git push *:*", "git push --mirror*", "git push * --mirror*",
)

#: HỆ THỐNG / AN NINH. Không thứ nào ở đây được xảy ra không người trông,
#: và vài thứ (Smart App Control) KHÔNG hoàn tác được — xem `CLAUDE.md`.
CAM_HE_THONG = (
    "reg add*", "reg delete*", "reg import*", "reg load*",
    "REG ADD*", "REG DELETE*", "REG IMPORT*", "regedit*",
    "*Set-ItemProperty*HKLM*", "*Set-ItemProperty*HKCU*",
    "*New-ItemProperty*HKLM*", "*New-ItemProperty*HKCU*",
    "*Remove-ItemProperty*HK*", "*Remove-Item*HKLM*",
    "*Set-MpPreference*", "*Add-MpPreference*", "*Remove-MpPreference*",
    "*Set-ExecutionPolicy*", "*Set-ProcessMitigation*",
    "*SmartAppControl*", "*VerifiedAndReputablePolicyState*",
    "netsh advfirewall*", "netsh firewall*", "*Set-NetFirewall*",
    "*New-NetFirewallRule*", "*Remove-NetFirewallRule*",
    "sc config*", "sc delete*", "sc stop*", "sc start*",
    "*Stop-Service*", "*Set-Service*", "*Restart-Service*",
    "schtasks /create*", "schtasks /delete*", "schtasks /change*",
    "bcdedit*", "*Disable-WindowsOptionalFeature*",
    "*takeown*", "icacls * /grant*", "*Set-Acl*",
    "sudo *", "* sudo *", "ssh*sudo*", "doas *",
)

#: SẢN XUẤT. Nhánh này phản chiếu mục 4 của yêu cầu: AWS/Appwrite/R2/Drive
#: và mọi đường deploy.
CAM_SAN_XUAT = (
    "*sudo systemctl restart*", "*sudo systemctl stop*",
    "*sudo systemctl start*", "*sudo systemctl disable*",
    "*sudo systemctl enable*", "*sudo service *",
    "aws s3 rm*", "aws s3 rb*", "aws s3 cp*", "aws s3 sync*",
    "aws s3api delete*", "aws s3api put*", "aws iam *",
    "aws ec2 terminate-instances*", "aws ec2 stop-instances*",
    "aws rds delete*", "aws lambda delete*", "aws lambda update*",
    "*wrangler deploy*", "*wrangler delete*", "*wrangler secret*",
    "*wrangler r2 bucket delete*", "*wrangler r2 object delete*",
    "*wrangler kv:namespace delete*", "*wrangler kv:key delete*",
    "*wrangler d1 delete*", "*wrangler d1 execute*",
    "*cf:deploy*", "*npm run deploy*",
    "*appwrite databases delete*", "*appwrite databases create*",
    "*appwrite databases update*", "*appwrite users delete*",
    "*appwrite storage delete*", "*appwrite functions delete*",
    "*drive.files.delete*", "*files.delete*",
    "gcloud compute instances delete*", "gcloud compute instances stop*",
    "az vm delete*", "az vm deallocate*",
)

#: THI HÀNH GIÁN TIẾP. Đây là lớp GLOB thô; phần tinh nằm ở
#: `guard_indirect_exec.py` (được đăng ký ở tầng người dùng bên dưới, vì
#: đúng là lớp này mà một thư mục chưa được tin làm mất).
CAM_GIAN_TIEP = (
    "python -c*", "python3 -c*", "py -c*", "py -3 -c*", "python -c *",
    "node -e*", "node --eval*", "perl -e*", "perl -E*", "ruby -e*",
    "*powershell -Command*", "*powershell -c *", "*pwsh -Command*",
    # Dang CAN BANG ngoac `(*)*`: mot than luat co `(` khong dong bi Claude
    # Code bo lang le luc khoi dong (do duoc 2026-08-28, va lai 2026-09-10
    # khi `--kiem` bao thieu dung hai luat nay sau mot phien moi).
    "*-EncodedCommand*", "*-enc *", "*Invoke-Expression*", "*IEX(*)*",
    "cmd /c*", "cmd.exe /c*", "cmd /k*",
    "*| bash*", "*|bash*", "*| sh -*", "*|sh -*", "*| sh\n*",
    "*curl* | *", "*wget* | *", "*Invoke-WebRequest*|*",
    "awk*system(*)*", "awk*|*getline*",
    "*Start-Process*-Verb RunAs*",
)


#: Luật QUÁ RỘNG — bị GỠ khi áp dụng, kèm lý do.
#:
#: Ba luật dưới đây từng nằm trong tầng cấm và đã bị đo thấy chặn oan
#: `git check-ignore -v .env` — một lệnh KHÔNG đọc byte nội dung nào, chỉ
#: trả lời "tệp này có bị `.gitignore` bỏ hay không", và nằm ngay trong
#: danh sách AN TOÀN mà người dùng yêu cầu.
#:
#: Chúng bị gỡ chứ không bị nới, vì thứ chúng định chặn (`cd x && cat
#: .env`) giờ được `guard_indirect_exec.secret_file_read()` chặn CHÍNH
#: XÁC HƠN: hàm đó tách được ĐỘNG TỪ khỏi TOÁN HẠNG, còn glob thì không.
#: Đây là ranh giới đúng giữa hai lớp — glob cho thứ glob diễn đạt đúng,
#: hook cho thứ cần biết cấu trúc lệnh.
LUAT_QUA_RONG = {
    "Bash(* *.env)": "chặn oan `git check-ignore -v .env`",
    "Bash(* *.env *)": "chặn oan mọi lệnh chỉ nhắc tên tệp",
    "Bash(*.env.*)": "chặn oan `git check-ignore -v .env.example`",
    "Bash(*/.env)": "chặn oan `git check-ignore -v server/.env`",
    "Bash(*/.env *)": "chặn oan lệnh chỉ nhắc đường dẫn",
    "Bash(*\\.env)": "chặn oan đường Windows chỉ được nhắc tên",
    # Nhóm mẫu-trước: toán hạng đầu là MẪU, không phải đường dẫn.
    **{f"Bash({v}{h})": "toán hạng đầu là MẪU tìm, không phải đường dẫn"
       for v in _DOC_MAU_TRUOC
       for h in (" *.env", " *.env *", " * *.env", " * *.env *",
                 " *.env.*", " * *.env.*", " *.env*", " * *.env*")},
    # Cùng lý do, cho các mẫu bí mật khác mà hồ sơ kho đã neo theo động từ
    # mẫu-trước.
    **{f"Bash({v}{h})": "toán hạng đầu là MẪU tìm, không phải đường dẫn"
       for v in _DOC_MAU_TRUOC
       for h in (" *credentials*", " * *credentials*", " *id_rsa*",
                 " * *id_rsa*", " *id_ed25519*", " * *id_ed25519*",
                 " *.pem", " * *.pem", " *.git-credentials*",
                 " * *.git-credentials*")},
}


def tang_cam() -> List[str]:
    ra = [f"Read({x})" for x in CAM_DOC]
    for nhom in (CAM_LENH_BI_MAT, CAM_PHA_HUY, CAM_HE_THONG,
                 CAM_SAN_XUAT, CAM_GIAN_TIEP):
        ra += [f"Bash({x})" for x in nhom]
    return ra


# ======================================================== khớp / quyết định ==

def khop(mau: str, lenh: str) -> bool:
    """Một luật `Bash(...)` với một chuỗi lệnh.

    Hai dạng, đúng như chính tệp cấu hình đã dựa vào:
        `x:*`  -> TIỀN TỐ lệnh
        còn lại -> GLOB trên CẢ chuỗi lệnh
    """
    if mau.endswith(":*"):
        goc = mau[:-2]
        return lenh == goc or lenh.startswith(goc + " ")
    return mau == lenh or fnmatch.fnmatchcase(lenh, mau)


def _hook():
    """Nạp `guard_indirect_exec` theo ĐƯỜNG DẪN, hoặc `None`.

    Nạp theo đường vì tệp đó ở `.claude/hooks/`, không phải một gói
    Python — và vì đúng bản đang được ĐĂNG KÝ mới là bản có hiệu lực.
    """
    import importlib.util
    for p in (HOOK_NGUOI_DUNG, HOOK_KHO):
        if not p.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                "cc_guard_kiem", str(p))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)                  # type: ignore
            return m
        except Exception:                               # noqa: BLE001
            continue
    return None


_HOOK = None


def hook_chan(g, lenh: str) -> Optional[str]:
    """Lý do hook chặn `lenh`, hoặc `None` — CHIA ĐOẠN ĐÚNG NHƯ `main()`.

    `expand()` MỘT MÌNH là chưa đủ, và chỗ này từng sai: nó tách thân
    `$(...)`/backtick, chứ KHÔNG tách `&&`. Nên `evaluate()` gọi trên
    nguyên chuỗi `cd /tmp && cat .env` chỉ thấy nhị phân `cd` và trả
    `None`, trong khi hook THẬT chặn — vì `main()` còn chạy
    `SEGMENT_SPLIT.split(chunk)` một tầng nữa.

    Một bản mô hình chia đoạn khác bản thật sẽ báo an toàn ở đúng chỗ hệ
    thống thật đang chặn (hoặc ngược lại), nên phép chia phải giống hệt.
    """
    for chunk in g.expand(lenh):
        for doan in g.SEGMENT_SPLIT.split(chunk):
            if not doan.strip():
                continue
            r = g.evaluate(doan)
            if r:
                return r
    return None


def quyet_dinh(lenh: str, p: Dict[str, Sequence[str]]) -> str:
    """`deny` | `ask` | `allow` | `hoi` — đúng thứ tự ưu tiên.

    HOOK ĐƯỢC TÍNH VÀO, và phải được tính vào để bản mô hình này không
    nói dối. Đo được (2026-09-10): một lệnh KHÔNG khớp luật nào rơi xuống
    bộ phân loại nội tại của Claude Code, và bộ đó **cho chạy** phần lớn
    — `sed -i`, `find -delete`, `reg add`, `ssh ... "sudo systemctl
    restart"` đều chạy thật. Nên `hoi` không phải một rào, và một ma trận
    chỉ đọc glob sẽ báo an toàn ở đúng chỗ hệ thống thật đang hở.

    Một `deny` của hook thắng cả `allow` và cả `bypassPermissions` (đo
    trực tiếp trên 2.1.231), nên nó được xét TRƯỚC.
    """
    global _HOOK
    if _HOOK is None:
        _HOOK = _hook() or False
    if _HOOK:
        try:
            if hook_chan(_HOOK, lenh):
                return "deny"
        except Exception:                               # noqa: BLE001
            pass
    for muc in ("deny", "ask", "allow"):
        for r in p.get(muc, []) or []:
            if r.startswith("Bash(") and r.endswith(")"):
                if khop(r[5:-1], lenh):
                    return muc
    return "hoi"


def _doc(p: Path) -> dict:
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ho_so(*, gom_kho: bool) -> Dict[str, List[str]]:
    """Hồ sơ HIỆU LỰC. `gom_kho=False` = thư mục CHƯA ĐƯỢC TIN."""
    nd = _doc(CAU_HINH_NGUOI_DUNG).get("permissions", {}) or {}
    ra = {k: list(nd.get(k, []) or []) for k in ("allow", "ask", "deny")}
    if gom_kho:
        kh = _doc(CAU_HINH_KHO).get("permissions", {}) or {}
        for k in ra:
            ra[k] += list(kh.get(k, []) or [])
    return ra


# ==================================================================== áp dụng ==

def ap_dung(*, that: bool = True) -> Tuple[int, int, bool]:
    """Ghi tầng còn thiếu vào `~/.claude/settings.json`. Chỉ THÊM.

    Không bao giờ xoá luật của người dùng: một luật lạ có thể do họ thêm
    có chủ đích, và tệp này không có cách nào biết.
    """
    d = _doc(CAU_HINH_NGUOI_DUNG)
    d.setdefault("permissions", {})
    for k in ("allow", "ask", "deny"):
        d["permissions"].setdefault(k, [])
    co_allow = set(d["permissions"]["allow"])
    co_deny = set(d["permissions"]["deny"])
    them_a = [r for r in tang_cho_phep() if r not in co_allow]
    them_d = [r for r in tang_cam() if r not in co_deny]
    go = [r for r in LUAT_QUA_RONG if r in co_deny]
    d["permissions"]["allow"] = sorted(co_allow | set(them_a))
    d["permissions"]["deny"] = sorted((co_deny | set(them_d)) - set(go))

    # HOOK Ở TẦNG NGƯỜI DÙNG. Đây là nửa mà `${CLAUDE_PROJECT_DIR}` không
    # với tới được: một thư mục chưa được tin không nạp hook của kho, nên
    # bản sao này phải sống ở đường TUYỆT ĐỐI ngoài mọi nhánh git.
    hook_moi = False
    if that:
        HOOK_NGUOI_DUNG.parent.mkdir(parents=True, exist_ok=True)
        if HOOK_KHO.is_file():
            cu = (HOOK_NGUOI_DUNG.read_bytes()
                  if HOOK_NGUOI_DUNG.is_file() else b"")
            if cu != HOOK_KHO.read_bytes():
                shutil.copy2(HOOK_KHO, HOOK_NGUOI_DUNG)
                hook_moi = True
    hooks = d.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    da_co = any("guard_indirect_exec" in json.dumps(x) for x in pre)
    if not da_co:
        pre.append({
            "matcher": "Bash",
            "hooks": [{
                "type": "command", "command": "python",
                "args": [str(HOOK_NGUOI_DUNG).replace("\\", "/")],
                "timeout": 15,
                "statusMessage": ("Checking command against the "
                                  "indirect-execution guard"),
            }],
        })
        hook_moi = True
    if that and (them_a or them_d or go or hook_moi):
        bs = CAU_HINH_NGUOI_DUNG.with_suffix(".json.truoc-kiem-quyen")
        if CAU_HINH_NGUOI_DUNG.is_file() and not bs.is_file():
            shutil.copy2(CAU_HINH_NGUOI_DUNG, bs)
        CAU_HINH_NGUOI_DUNG.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if go:
        RA.write("gỡ luật quá rộng (người dùng): "
                 + ", ".join(f"{r} ({LUAT_QUA_RONG[r]})" for r in go) + "\n")

    # CẢ TỆP KHO. Cùng ba luật đó cũng nằm ở tầng kho, nên một thư mục ĐÃ
    # ĐƯỢC TIN vẫn chặn oan `git check-ignore -v .env` nếu chỉ dọn một
    # bên. Ở đây CHỈ GỠ, không bao giờ thêm: phần đặc thù kho do người
    # viết, tệp này không có quyền đoán thay.
    dk = _doc(CAU_HINH_KHO)
    if that and dk.get("permissions"):
        cam_kho = list(dk["permissions"].get("deny", []) or [])
        go_kho = [r for r in LUAT_QUA_RONG if r in cam_kho]
        if go_kho:
            dk["permissions"]["deny"] = [r for r in cam_kho
                                         if r not in set(go_kho)]
            bs = CAU_HINH_KHO.with_suffix(".json.truoc-kiem-quyen")
            if not bs.is_file():
                shutil.copy2(CAU_HINH_KHO, bs)
            CAU_HINH_KHO.write_text(
                json.dumps(dk, ensure_ascii=False, indent=2),
                encoding="utf-8")
            RA.write("gỡ luật quá rộng (kho): "
                     + ", ".join(go_kho) + "\n")
    return len(them_a), len(them_d), hook_moi


# ================================================================== tin cậy ==

DUONG_TIN_CAY = Path.home() / ".claude.json"


def _duoi_goc_phat_trien(p: Path) -> bool:
    q = str(p.resolve()).replace("\\", "/").lower()
    for g in GOC_PHAT_TRIEN:
        gg = g.replace("\\", "/").lower().rstrip("/")
        if q == gg or q.startswith(gg + "/"):
            return True
    return False


def trang_thai_tin_cay(p: Path) -> Optional[bool]:
    """`True`/`False` đã ghi, hoặc `None` nếu chưa có bản ghi nào."""
    d = _doc(DUONG_TIN_CAY)
    khoa = str(Path(p).resolve()).replace("\\", "/")
    muc = (d.get("projects") or {}).get(khoa)
    if muc is None:
        return None
    return bool(muc.get("hasTrustDialogAccepted"))


def tin_cay(p: Path, *, that: bool = True) -> Tuple[bool, str]:
    """Đánh dấu một thư mục là ĐƯỢC TIN — có hai chốt an toàn.

    VÌ SAO CẦN. Chính Claude Code nói ra cơ chế, nguyên văn:

        Ignoring 241 permissions.allow entries from .claude/settings.json:
        this workspace has not been trusted. Run Claude Code interactively
        here once and accept the trust dialog, or set
        projects["<đường>"].hasTrustDialogAccepted: true in
        C:\\Users\\<u>\\.claude.json.

    Mỗi worktree Router V4 vừa dựng là một thư mục MỚI, nên nó khởi đầu ở
    trạng thái đó: hồ sơ của kho bị bỏ qua, hook của kho không chạy. Một
    phiên không người trông thì không có ai bấm hộp thoại tin cậy.

    HAI CHỐT, vì "tin cậy" là một quyết định an ninh chứ không phải một
    tiện nghi:

      1. đường phải nằm DƯỚI một gốc phát triển đã biết
         (`GOC_PHAT_TRIEN`) — không tin cậy một thư mục bất kỳ;
      2. `deny` của hồ sơ tại đó phải PHỦ tầng cấm bắt buộc. Tin cậy một
         thư mục là KÍCH HOẠT tệp `settings.json` nằm trong đó; nếu tệp
         đó cấm ít hơn tầng bắt buộc thì tin cậy nó là NỚI rào, và đó
         đúng là thứ không được làm lặng lẽ.
    """
    p = Path(p).resolve()
    if not p.is_dir():
        return False, f"không phải thư mục: {p}"
    if not _duoi_goc_phat_trien(p):
        return False, (f"TỪ CHỐI: {p} không nằm dưới một gốc phát triển đã "
                       f"biết ({', '.join(GOC_PHAT_TRIEN[:3])}…)")
    ct = p / ".claude" / "settings.json"
    if ct.is_file():
        cam = set((_doc(ct).get("permissions", {}) or {}).get("deny", []))
        thieu = [r for r in tang_cam() if r not in cam]
        # Tầng người dùng vẫn luôn có hiệu lực, nên phần thiếu ở đây được
        # tầng đó phủ. Chỉ CHẶN khi hồ sơ tại đó có `allow` mà tầng cấm
        # bắt buộc không chặn lại được — tức là nó tự mở thêm.
        mo = [r for r in (_doc(ct).get("permissions", {})
                          or {}).get("allow", [])
              if r.startswith("Bash(") and r.endswith(")")
              and quyet_dinh(r[5:-1].replace(":*", " x"),
                             {"deny": tang_cam()}) != "deny"
              and any(k in r.lower() for k in ("sudo", "rm -", "reg add",
                                               "--force", "deploy",
                                               "credential", ".pem",
                                               ".env"))]
        if mo:
            return False, (f"TỪ CHỐI: hồ sơ tại {p} có luật `allow` đáng "
                           f"ngờ: {mo[:5]}")
        if thieu:
            RA.write(f"  lưu ý: hồ sơ tại đó thiếu {len(thieu)} luật cấm "
                     f"— tầng người dùng phủ chúng\n")
    d = _doc(DUONG_TIN_CAY)
    khoa = str(p).replace("\\", "/")
    pr = d.setdefault("projects", {})
    muc = pr.setdefault(khoa, {})
    if muc.get("hasTrustDialogAccepted") is True:
        return True, f"đã được tin từ trước: {khoa}"
    muc["hasTrustDialogAccepted"] = True
    muc.setdefault("allowedTools", [])
    muc.setdefault("hasClaudeMdExternalIncludesApproved", False)
    if that:
        bs = DUONG_TIN_CAY.with_suffix(".json.truoc-kiem-quyen")
        if DUONG_TIN_CAY.is_file() and not bs.is_file():
            shutil.copy2(DUONG_TIN_CAY, bs)
        DUONG_TIN_CAY.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, f"đã đánh dấu ĐƯỢC TIN: {khoa}"


# ==================================================================== ma trận ==

#: AN TOÀN: phải KHÔNG hỏi, kể cả ở thư mục chưa được tin.
MA_TRAN_AN_TOAN = (
    'python scripts/tim.py "TrangThai"',
    'python scripts/tim.py "def thu" scripts/control_center',
    'python scripts/tim.py "khoa" --glob "*.py" -i -C 2',
    "python scripts/tim.py --doc scripts/control_center/store.py --tu 1 --den 60",
    "python scripts/tim.py --kiem",
    'git grep -n "KHONG_DUOC_CO"',
    'git grep -n "TrangThai" -- scripts/',
    "git status --porcelain",
    "git diff --stat",
    "git log --oneline -5",
    "git show --stat HEAD",
    "git branch --show-current",
    "git rev-parse HEAD",
    "git check-ignore -v .router/control_center/control.db",
    "git status --porcelain --ignored",
    # TÌM CHUỖI ".env" qua cửa an toàn — không phải ĐỌC tệp `.env`.
    'python scripts/tim.py "\\.env" --glob "*.py"',
    # HẠN CHẾ ĐÃ BIẾT, cố ý giữ: `Bash(*.pem*)` và họ của nó (`*.ppk*`,
    # `*.p12*`, `*.pfx*`, `*.kdbx*`) là glob THÔ trên cả chuỗi lệnh, nên
    # một lệnh chỉ NHẮC phần mở rộng — `python scripts/tim.py "*.pem"` —
    # cũng bị chặn. Với `.env` thì cách neo-thô đã được gỡ; với khoá
    # riêng thì KHÔNG, vì cái giá của một lần lọt là một khoá production
    # bị đọc, còn cái giá của lần chặn oan là đổi mẫu tìm thành `pem`.
    # Ghi ở đây để nó là một quyết định, không phải một điều bất ngờ.
    'python scripts/tim.py "pem" --chi-ten',
    "git ls-files scripts/control_center",
    "git worktree list",
    "git worktree add ../wt-probe -b probe/x",
    "git checkout -b feat/v06-project-memory",
    "git add scripts/tim.py",
    'git commit -m "feat: tim.py"',
    "python -m pytest scripts/tests/test_observability.py -q",
    "python -m compileall -q scripts/control_center",
    "python scripts/build_desktop_exe.py --dist dist-v06",
    "python scripts/control_center_v06_acceptance.py",
    "python scripts/kiem_quyen.py --kiem",
    "node --check scripts/control_center/web/app.js",
    "wc -l scripts/control_center/store.py",
    "sha256sum dist-v05/x.exe",
)

#: AN TOÀN NHƯNG DỰA VÀO LỚP NỀN của Claude Code: chỉ đòi KHÔNG bị `deny`.
#:
#: `grep`/`rg`/`cat`/`head`/`tail`/`find`/`sed` **cố ý** không có luật
#: `allow` ở tầng người dùng — xem đầu tệp: viết `Bash(find:*)` vào
#: `allow` THAY phép cho-phép-có-kiểm-cờ của Claude Code bằng một phép
#: vô điều kiện, và đã đo được nó mở lại `find -delete` và `sed -i` thật.
#:
#: Nên hợp đồng cho nhóm này hẹp hơn và trung thực hơn: hồ sơ không được
#: CHẶN chúng. Việc chúng chạy không cần duyệt do lớp nền lo, và điều đó
#: được xác nhận bằng bộ đo THẬT (`perm_probe`), không bằng mô hình này.
MA_TRAN_AN_TOAN_NEN = (
    'grep -rn "TrangThai" scripts/control_center/',
    "grep -c '\\* \\*\\.env' .claude/settings.json",
    'grep -rn "\\.env" scripts/tests/test_claude_permission_policy.py',
    'rg "TrangThai" scripts/',
    "cat README.md",
    "head -40 scripts/control_center/store.py",
    "tail -20 docs/HANDOFF.md",
    "sed -n '1,40p' scripts/control_center/leader.py",
    "ls scripts/control_center",
    'find scripts -name "*.py"',
    "cd C:/FanficWorkers/router-control-center && git status --porcelain",
    'cd C:/FanficWorkers/router-control-center && grep -rn "x" scripts/',
)

#: KHÔNG SỬA ĐƯỢC BẰNG HỒ SƠ — và vì sao. Danh sách này là DỮ LIỆU, không
#: phải một ghi chú, để nó không lặng lẽ trở thành một điều bất ngờ lúc
#: 2 giờ sáng.
#:
#: ĐO ĐƯỢC (2026-09-10, thư mục chưa được tin, mỗi dòng là một phiên
#: `claude -p` thật):
#:
#:     git check-ignore -v README.md            -> ALLOW
#:     git check-ignore -v .env                 -> DENIED
#:     git check-ignore -v khoa.pem             -> DENIED
#:     ls -la .env                              -> DENIED
#:     stat .env                                -> DENIED
#:     test -f .env                             -> DENIED   (đọc 0 byte!)
#:     git log --oneline -- .env                -> DENIED
#:     git status --porcelain --ignored          -> ALLOW
#:
#: CƠ CHẾ: Claude Code phân giải những ĐƯỜNG DẪN mà một lệnh Bash NHẮC
#: TÊN, rồi đối chiếu với các luật `Read(...)`. Nó không quan tâm động từ
#: là gì — `test -f` không đọc byte nào mà vẫn bị chặn. Và vì `deny`
#: thắng `allow`, một luật `Bash(git check-ignore:*)` trong `allow` KHÔNG
#: cứu được.
#:
#: Đây cũng CHÍNH LÀ cơ chế sinh ra thông điệp mà người dùng báo — "một
#: luật `Read()` deny đang được cấu hình". Khi một `cd` làm đường dẫn
#: không phân giải được TĨNH, nó không chứng minh được đường đó KHÔNG bị
#: deny, nên nó hạ xuống ASK thay vì DENY.
#:
#: VÌ SAO KHÔNG SỬA: cách duy nhất là gỡ `Read(**/.env)` và họ của nó —
#: tức là mở đúng thứ phải đóng. Cái giá phải trả đúng chỗ này là nhỏ và
#: có đường đi vòng thật:
#:
#:     muốn biết một đường có bị bỏ qua -> git status --porcelain --ignored
#:     muốn biết tệp nào bị loại trừ    -> python scripts/tim.py --kiem
#:
#: Và đây là lý do KIẾN TRÚC của `tim.py`: nó KHÔNG BAO GIỜ nhắc tên một
#: đường bí mật trong argv và KHÔNG cần `cd`, nên nó không chạm vào cơ
#: chế này một lần nào.
KHONG_SUA_DUOC = {
    "git check-ignore -v .env":
        "Read(**/.env) deny — đường dẫn bị nhắc tên trong argv",
    "git check-ignore -v khoa.pem":
        "Read(**/*.pem) deny — đường dẫn bị nhắc tên trong argv",
    "git check-ignore -v cai_dat/credentials.json":
        "Read(**/credentials.json) deny",
    "ls -la .env": "Read(**/.env) deny",
    "stat .env": "Read(**/.env) deny",
    "test -f .env": "Read(**/.env) deny — đọc 0 byte mà vẫn bị chặn",
    "git log --oneline -- .env": "Read(**/.env) deny",
}

#: NGUY HIỂM: phải KHÔNG BAO GIỜ `allow`.
MA_TRAN_NGUY_HIEM = (
    "cat .env",
    "cat server/.env",
    "head -5 .env",
    'grep -rn "TOKEN" .env',
    "sed -n '1,2p' .env",
    "cat khoa.pem",
    "tail -3 khoa.pem",
    "cat C:/Users/nguye/.ssh/fanficappwrite.pem",
    "cat /c/Users/nguye/.aws/credentials",
    "cat ~/.git-credentials",
    "cat cai_dat/credentials.json",
    "cmdkey /list",
    'powershell -Command "Get-Credential"',
    "gh auth token",
    "git reset --hard HEAD~1",
    "git clean -fdx",
    "git clean -fd",
    "git push --force origin main",
    "git push -f origin main",
    "git push origin --delete main",
    "git branch -D main",
    "git worktree remove ../wt-probe",
    "rm -rf scripts",
    "rm -fr scripts",
    "rm -r scripts",
    "rm -f khoa.pem",
    "sed -i 's/a/b/' README.md",
    'find . -name "*.py" -delete',
    'find . -name "*.py" -exec rm {} ;',
    'python -c "print(1)"',
    'node -e "console.log(1)"',
    "awk 'BEGIN{system(\"echo x\")}'",
    'reg add "HKCU\\Software\\X" /v a /d b /f',
    "netsh advfirewall set allprofiles state off",
    'powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $true"',
    "aws s3 rm s3://bucket --recursive",
    "npx wrangler r2 bucket delete x",
    "npx wrangler deploy",
    "npm run cf:deploy:production",
    'ssh ubuntu@13.212.224.218 "sudo systemctl restart fanfic-farmer"',
    "sudo systemctl stop fanfic-farmer",
)


def ma_tran(*, gom_kho: bool):
    p = ho_so(gom_kho=gom_kho)
    an = [(c, quyet_dinh(c, p)) for c in MA_TRAN_AN_TOAN]
    nen = [(c, quyet_dinh(c, p)) for c in MA_TRAN_AN_TOAN_NEN]
    ng = [(c, quyet_dinh(c, p)) for c in MA_TRAN_NGUY_HIEM]
    return an, nen, ng


def _in_ma_tran(nhan: str, *, gom_kho: bool) -> int:
    an, nen, ng = ma_tran(gom_kho=gom_kho)
    RA.write(f"\n===== {nhan} =====\n")
    xau = 0
    RA.write("-- AN TOÀN, ĐƯỢC BẢO ĐẢM (phải 'allow') --\n")
    for c, q in an:
        ok = q == "allow"
        xau += 0 if ok else 1
        RA.write(f"  {'PASS' if ok else 'FAIL'}  {q:<6}  {c}\n")
    RA.write("-- AN TOÀN, DỰA LỚP NỀN (chỉ cần KHÔNG 'deny') --\n")
    for c, q in nen:
        ok = q != "deny"
        xau += 0 if ok else 1
        RA.write(f"  {'PASS' if ok else 'FAIL'}  {q:<6}  {c}\n")
    # BAR LA `deny`, KHONG PHAI "khac allow".
    #
    # Do that (2026-09-10) o mot thu muc chua duoc tin: nhung lenh KHONG
    # khop luat nao roi xuong bo phan loai noi tai cua Claude Code, va bo
    # do CHO CHAY phan lon — `cat khoa.pem`, `sed -i`, `find -delete`,
    # `reg add`, `ssh ... "sudo systemctl restart fanfic-farmer"` deu
    # CHAY THAT. Nen "khong nam trong allow" khong phai mot rao; chi
    # `deny` moi la rao.
    RA.write("-- NGUY HIỂM (phải là 'deny') --\n")
    for c, q in ng:
        ok = q == "deny"
        xau += 0 if ok else 1
        RA.write(f"  {'PASS' if ok else 'FAIL'}  {q:<6}  {c}\n")
    tong = len(an) + len(nen) + len(ng)
    RA.write(f"-- {tong - xau}/{tong} PASS\n")
    RA.write(f"-- {len(KHONG_SUA_DUOC)} lệnh KHÔNG sửa được bằng hồ sơ "
             f"(cơ chế của Claude Code, xem `KHONG_SUA_DUOC`)\n")
    return xau


def kiem() -> int:
    xau = 0
    nd = _doc(CAU_HINH_NGUOI_DUNG).get("permissions", {}) or {}
    thieu_a = [r for r in tang_cho_phep()
               if r not in set(nd.get("allow", []) or [])]
    thieu_d = [r for r in tang_cam()
               if r not in set(nd.get("deny", []) or [])]
    RA.write(f"tệp người dùng   : {CAU_HINH_NGUOI_DUNG}"
             f"  ({'có' if CAU_HINH_NGUOI_DUNG.is_file() else 'KHÔNG CÓ'})\n")
    RA.write(f"tệp kho          : {CAU_HINH_KHO}"
             f"  ({'có' if CAU_HINH_KHO.is_file() else 'KHÔNG CÓ'})\n")
    RA.write(f"tầng cho phép    : {len(tang_cho_phep())} luật, "
             f"thiếu {len(thieu_a)}\n")
    RA.write(f"tầng cấm         : {len(tang_cam())} luật, "
             f"thiếu {len(thieu_d)}\n")
    for r in thieu_a[:10]:
        RA.write(f"   thiếu allow: {r}\n")
    for r in thieu_d[:10]:
        RA.write(f"   thiếu deny : {r}\n")
    xau += len(thieu_a) + len(thieu_d)
    con = [r for r in LUAT_QUA_RONG
           if r in set(nd.get("deny", []) or [])]
    RA.write(f"luật quá rộng    : {len(con)} còn sót\n")
    for r in con:
        RA.write(f"   còn: {r}  — {LUAT_QUA_RONG[r]}\n")
    xau += len(con)

    hook_ok = (HOOK_NGUOI_DUNG.is_file() and HOOK_KHO.is_file()
               and HOOK_NGUOI_DUNG.read_bytes() == HOOK_KHO.read_bytes())
    RA.write(f"hook người dùng  : "
             f"{'KHỚP bản kho' if hook_ok else 'THIẾU hoặc LỆCH'}"
             f"  ({HOOK_NGUOI_DUNG})\n")
    xau += 0 if hook_ok else 1
    pre = json.dumps((_doc(CAU_HINH_NGUOI_DUNG).get("hooks", {})
                      or {}).get("PreToolUse", []))
    dk = "guard_indirect_exec" in pre
    RA.write(f"hook đã đăng ký  : {'CÓ' if dk else 'CHƯA'}\n")
    xau += 0 if dk else 1

    tt = trang_thai_tin_cay(GOC)
    NHAN_TIN = {True: "CÓ", False: "KHÔNG", None: "CHƯA CÓ BẢN GHI"}
    RA.write(f"kho này được tin : {NHAN_TIN[tt]}\n")
    if tt is not True:
        RA.write("   -> hồ sơ KHO sẽ bị bỏ qua ở đây. Sửa: "
                 "`python scripts/kiem_quyen.py --tin-cay .`\n")
        RA.write("   -> tầng NGƯỜI DÙNG vẫn có hiệu lực, nên phần an toàn "
                 "được bảo đảm vẫn chạy.\n")

    xau += _in_ma_tran("THƯ MỤC CHƯA ĐƯỢC TIN (chỉ tầng người dùng)",
                       gom_kho=False)
    xau += _in_ma_tran("THƯ MỤC ĐÃ ĐƯỢC TIN (người dùng + kho)",
                       gom_kho=True)
    RA.write(f"\n=> {'ĐẠT' if xau == 0 else f'{xau} vấn đề'}\n")
    return 0 if xau == 0 else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="kiem_quyen.py")
    ap.add_argument("--kiem", action="store_true")
    ap.add_argument("--ap-dung", action="store_true")
    ap.add_argument("--ma-tran", action="store_true")
    ap.add_argument("--thu", action="store_true",
                    help="in việc sẽ làm, KHÔNG ghi")
    ap.add_argument("--tin-cay", default="", metavar="ĐƯỜNG",
                    help="đánh dấu thư mục (hoặc worktree mới) là ĐƯỢC TIN")
    a = ap.parse_args(list(argv) if argv is not None else None)
    if a.tin_cay:
        ok, td = tin_cay(Path(a.tin_cay), that=not a.thu)
        RA.write(td + "\n")
        return 0 if ok else 2
    if a.ap_dung or a.thu:
        na, nd, hk = ap_dung(that=not a.thu)
        RA.write(f"{'SẼ thêm' if a.thu else 'đã thêm'}: {na} allow, "
                 f"{nd} deny, hook {'cập nhật' if hk else 'không đổi'}\n")
        if a.thu:
            return 0
    if a.ma_tran:
        x = _in_ma_tran("CHƯA ĐƯỢC TIN", gom_kho=False)
        x += _in_ma_tran("ĐÃ ĐƯỢC TIN", gom_kho=True)
        return 0 if x == 0 else 1
    return kiem()


if __name__ == "__main__":
    raise SystemExit(main())
