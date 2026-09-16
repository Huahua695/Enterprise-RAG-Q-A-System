"""一键推送：Gitee（origin）+ GitHub 双远端。

GitHub 直推失败（如本机访问不了 github.com）时，自动改走 GitHub Git Data API 兜底，
保证两个远端最终都对齐到同一个提交。

用法：
    python scripts/push_all.py            # 推送当前分支到两个远端
    python scripts/push_all.py --api-only # 只走 GitHub API 兜底（调试用）
    python scripts/push_all.py --branch master

返回码：0 = 两处都成功；1 = 有远端未成功。
"""
from __future__ import annotations

import argparse
import base64
import os
import pathlib
import subprocess
import sys

try:
    import httpx
except ImportError:
    sys.exit("缺少 httpx，请先执行: backend/.venv/Scripts/python.exe -m pip install httpx")

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
API = "https://api.github.com"
GITEE_REMOTE = "origin"
GITHUB_REMOTE = "github"


def github_repo_slug() -> str:
    """从 git remote 推导 owner/repo，避免写死。"""
    url = git("remote", "get-url", GITHUB_REMOTE)
    if url:
        tail = url.rstrip("/").removesuffix(".git")
        if tail.startswith("git@") and ":" in tail:
            tail = tail.split(":", 1)[1]
        elif "://" in tail:
            tail = tail.split("://", 1)[1].split("/", 1)[-1]
        parts = [p for p in tail.split("/") if p]
        if len(parts) >= 2:
            return "/".join(parts[-2:])
    raise SystemExit(f"无法从 remote '{GITHUB_REMOTE}' 推导仓库名，请检查 git remote 配置")


# ---------------------------------------------------------------- git helpers
def git(*args: str, binary: bool = False, check: bool = False):
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        capture_output=True,
        cwd=REPO_DIR,
    )
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:400])
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def uncommitted_changes() -> list[str]:
    out = git("status", "--porcelain")
    return [l for l in out.splitlines() if l.strip()]


# ------------------------------------------------------------------- token
def get_token() -> str | None:
    """优先环境变量，其次从 git 凭据管理器读取。"""
    for k in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(k, "").strip():
            return os.environ[k].strip()

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    try:
        r = subprocess.run(
            ["git", "-c", "credential.interactive=false", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=REPO_DIR,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("password="):
            return line.partition("=")[2].strip() or None
    return None


# --------------------------------------------------------- GitHub API 兜底
class GithubApiPusher:
    def __init__(self, token: str, repo: str):
        self.repo = repo
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "rag-push-all",
        }
        self.client = httpx.Client(timeout=60, follow_redirects=True)

    def close(self):
        self.client.close()

    def _tree_of(self, sha: str) -> str:
        r = self.client.get(f"{API}/repos/{self.repo}/git/commits/{sha}", headers=self.headers)
        r.raise_for_status()
        return r.json()["tree"]["sha"]

    def _blob(self, content: bytes) -> str:
        r = self.client.post(
            f"{API}/repos/{self.repo}/git/blobs",
            headers=self.headers,
            json={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
        )
        r.raise_for_status()
        return r.json()["sha"]

    def _meta(self, commit: str):
        a = git("show", "-s", "--format=%an%x00%ae%x00%aI", commit).split("\x00")
        c = git("show", "-s", "--format=%cn%x00%ce%x00%cI", commit).split("\x00")
        msg = git("show", "-s", "--format=%B", commit) + "\n"
        return (
            {"name": a[0], "email": a[1], "date": a[2]},
            {"name": c[0], "email": c[1], "date": c[2]},
            msg,
        )

    def push(self, branch: str) -> bool:
        r = self.client.get(f"{API}/repos/{self.repo}/git/ref/heads/{branch}", headers=self.headers)
        r.raise_for_status()
        parent = r.json()["object"]["sha"]

        # 远端提交必须是本地对象，否则算不出差异
        if git("cat-file", "-t", parent) != "commit":
            print("    远端提交不在本地，尝试 fetch…")
            subprocess.run(["git", "fetch", GITHUB_REMOTE], capture_output=True, cwd=REPO_DIR)
            if git("cat-file", "-t", parent) != "commit":
                print(f"    ✗ 本地缺少远端提交 {parent[:7]}，无法计算差异。请先手动同步该远端后再试。")
                return False

        base_tree = self._tree_of(parent)

        commits = [l for l in git("rev-list", "--reverse", f"{parent}..HEAD").splitlines() if l]
        if not commits:
            print("  GitHub：已是最新，无需提交")
            return True
        print(f"  GitHub：需推送 {len(commits)} 个提交")

        for idx, c in enumerate(commits, 1):
            parent_local = git("rev-parse", f"{c}^")
            raw = git("diff-tree", "-r", "-z", "--no-commit-id", "--name-status", parent_local, c, binary=True)
            parts = [p.decode("utf-8", "replace") for p in raw.split(b"\x00") if p]

            entries = []
            for status, path in zip(parts[0::2], parts[1::2]):
                if status == "D":
                    entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                    continue
                entries.append(
                    {
                        "path": path,
                        "mode": git("ls-tree", c, "--", path).split()[0],
                        "type": "blob",
                        "sha": self._blob(git("show", f"{c}:{path}", binary=True)),
                    }
                )

            tr = self.client.post(
                f"{API}/repos/{self.repo}/git/trees",
                headers=self.headers,
                json={"base_tree": base_tree, "tree": entries},
            )
            tr.raise_for_status()
            new_tree = tr.json()["sha"]

            author, committer, message = self._meta(c)
            cr = self.client.post(
                f"{API}/repos/{self.repo}/git/commits",
                headers=self.headers,
                json={
                    "message": message,
                    "tree": new_tree,
                    "parents": [parent],
                    "author": author,
                    "committer": committer,
                },
            )
            cr.raise_for_status()
            new_sha = cr.json()["sha"]
            print(f"    [{idx}/{len(commits)}] {c[:7]} -> {new_sha[:7]}  {'sha 一致' if new_sha == c else '已重建'}")

            if idx == len(commits):
                ur = self.client.patch(
                    f"{API}/repos/{self.repo}/git/refs/heads/{branch}",
                    headers=self.headers,
                    json={"sha": new_sha, "force": False},
                )
                if ur.status_code >= 300:
                    print("    更新失败:", ur.text[:300])
                    return False

            parent, base_tree = new_sha, new_tree

        local_tree = git("rev-parse", "HEAD^{tree}")
        final = self.client.get(f"{API}/repos/{self.repo}/git/ref/heads/{branch}", headers=self.headers).json()["object"]["sha"]
        ok = self._tree_of(final) == local_tree
        print(f"  GitHub：远端 {final[:7]} / 本地 {git('rev-parse','HEAD')[:7]} -> {'内容一致' if ok else '内容不一致'}")
        return ok


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default=None, help="默认当前分支")
    ap.add_argument("--api-only", action="store_true", help="只走 GitHub API（跳过直推）")
    args = ap.parse_args()

    branch = args.branch or current_branch()
    print(f"仓库：{REPO_DIR}")
    print(f"分支：{branch}")

    dirty = uncommitted_changes()
    if dirty:
        print(f"\n注意：有 {len(dirty)} 项未提交改动，本次只推送已提交的内容：")
        for d in dirty[:10]:
            print("   ", d)
        if len(dirty) > 10:
            print(f"    …还有 {len(dirty) - 10} 项")

    results: dict[str, bool] = {}

    # ---- 1) Gitee ----
    print(f"\n[1/2] 推送 Gitee（{GITEE_REMOTE}）…")
    r = subprocess.run(["git", "push", GITEE_REMOTE, branch], capture_output=True, cwd=REPO_DIR)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    results["Gitee"] = r.returncode == 0
    for line in out.splitlines()[-4:]:
        print("   ", line)

    # ---- 2) GitHub ----
    print(f"\n[2/2] 推送 GitHub（{GITHUB_REMOTE}）…")
    gh_ok = False
    if not args.api_only:
        r = subprocess.run(["git", "push", GITHUB_REMOTE, branch], capture_output=True, cwd=REPO_DIR, timeout=300)
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        gh_ok = r.returncode == 0
        if gh_ok:
            for line in out.splitlines()[-3:]:
                print("   ", line)
        else:
            print("    直推失败：", out.splitlines()[-1][:150] if out else "(无输出)")
            # 直推失败但可能因为「已是最新」，用远端 sha 判断
            ls = git("ls-remote", GITHUB_REMOTE, f"refs/heads/{branch}")
            if ls and ls.split()[0] == git("rev-parse", "HEAD"):
                print("    （远端已与本地一致，实为无需推送）")
                gh_ok = True

    if not gh_ok:
        print("    改用 GitHub API 兜底…")
        token = get_token()
        if not token:
            print("    ✗ 未取到 GitHub 令牌：请设置环境变量 GH_TOKEN，或确认 git 凭据管理器已保存 github.com 凭据")
            results["GitHub"] = False
        else:
            try:
                pusher = GithubApiPusher(token, github_repo_slug())
                try:
                    results["GitHub"] = pusher.push(branch)
                finally:
                    pusher.close()
            except Exception as e:  # noqa: BLE001
                print("    ✗ API 推送异常：", type(e).__name__, str(e)[:200])
                results["GitHub"] = False
    else:
        results["GitHub"] = True

    # ---- 汇总 ----
    print("\n=== 结果 ===")
    for name, ok in results.items():
        print(f"  {name}: {'成功' if ok else '失败'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
