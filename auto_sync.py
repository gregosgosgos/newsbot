"""
auto_sync.py — 로컬 폴더 변화를 감시해 자동으로 git commit + push.

내(코워크/클로드)가 이 폴더 파일을 고치면, 변경이 멈춘 뒤 ~30초 안에
자동으로 커밋하고 GitHub(origin main)로 올린다. push 인증은 이 컴퓨터에
저장된 git 로그인을 그대로 사용한다(별도 토큰 불필요).

사용법 (한 번만 실행해두면 됨):
    1) 터미널(Git Bash / cmd / PowerShell) 을 연다
    2) cd C:\\projects\\newsbot
    3) python auto_sync.py    (안 되면:  py auto_sync.py)
    4) 창을 그대로 켜 둔다. 종료하려면 Ctrl+C.

동작:
  - 15초마다 변경을 확인하고, 변경이 '멈춘' 것을 확인한 뒤에만 커밋(작업 중간 상태 방지).
  - GitHub Actions가 output/ 이미지 커밋을 올려도 충돌 없이 흡수(pull --rebase).
  - .gitignore 대상(tmpimg/·output/*.jpg 등)은 자동 제외.
"""
import os
import time
import subprocess
from datetime import datetime

REPO = os.path.dirname(os.path.abspath(__file__))
POLL_SEC = 15      # 변경 확인 주기(초)
STABLE_N = 2       # 연속 N회 동일하면 '변경 멈춤'으로 보고 커밋 → 약 30초 디바운스


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO,
                          capture_output=True, text=True)


def dirty():
    """스테이징/미스테이징 변경 요약(.gitignore 제외). 없으면 ''."""
    return git("status", "--porcelain").stdout.strip()


def sync_once():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    git("add", "-A")
    c = git("commit", "-m", f"auto: {ts}")
    if c.returncode != 0:
        # 커밋할 게 없거나(경합) 실패 → 조용히 넘어감
        return
    # 원격에 Actions 이미지 커밋 등이 있으면 먼저 흡수(다른 파일이라 충돌 없음)
    pr = git("pull", "--rebase", "--autostash")
    if pr.returncode != 0:
        git("rebase", "--abort")
    p = git("push")
    if p.returncode == 0:
        print(f"[auto-sync] ✅ commit + push 완료  ({ts})")
    else:
        print(f"[auto-sync] ⚠️ push 실패: {p.stderr.strip()[:200]}")


def main():
    if git("rev-parse", "--git-dir").returncode != 0:
        print(f"[auto-sync] ❌ git 저장소가 아닙니다: {REPO}")
        return
    print(f"[auto-sync] 감시 시작 → {REPO}")
    print("[auto-sync] 파일이 바뀌면 변경이 멈춘 뒤 자동으로 commit + push 합니다.")
    print("[auto-sync] 종료: Ctrl+C\n")
    last, stable = None, 0
    while True:
        try:
            d = dirty()
            if d:
                stable = stable + 1 if d == last else 0
                last = d
                if stable >= STABLE_N:
                    sync_once()
                    last, stable = None, 0
            else:
                last, stable = None, 0
        except Exception as e:
            print(f"[auto-sync] 오류(계속 진행): {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[auto-sync] 종료했습니다.")
