#!/usr/bin/env python3
"""SSH work on a paired Windows PC, scoped to the peer's checkout of the current repository.

The peer's checkout is found by repository identity, not by path: its root commit must match this
checkout's, and its normalized origin (or, failing that, its folder name) breaks ties. Drive letters and
root folders may differ between PCs. Every remote command re-verifies that identity on the peer before it
runs, file paths must stay inside the checkout, and git is limited to read-only subcommands.

    python cross_pc_ssh.py --peer <ssh-alias> whoami
    python cross_pc_ssh.py --peer <ssh-alias> locate [--json]
    python cross_pc_ssh.py --peer <ssh-alias> status
    python cross_pc_ssh.py --peer <ssh-alias> ls [REL]
    python cross_pc_ssh.py --peer <ssh-alias> cat REL [--max-bytes N]
    python cross_pc_ssh.py --peer <ssh-alias> git log --oneline -5
    python cross_pc_ssh.py --peer <ssh-alias> agent --prompt-file PROMPT.md [--harness claude|codex] [--allow-edits]

The peer comes from --peer, then CROSS_PC_SSH_PEER, then "default_peer" in ~/.config/cross-pc-ssh.json.
Search roots on the peer come from that file ("peers": {"<alias>": {"roots": [...]}}), else every fixed
drive's Projects folder and the remote user's Projects folder. Windows peers with Windows PowerShell only.
Stdlib only; no network access except the ssh client.

Every remote script travels base64-encoded on stdin behind a fixed -EncodedCommand bootstrap, and every
string inside it (paths, git arguments, the prompt) is embedded as base64, so no quoting or command-line limit
applies. This is a guard rail for agents, not a security boundary: the SSH key itself grants a full shell.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
CONFIG = Path.home() / ".config" / "cross-pc-ssh.json"
CACHE = Path(os.environ.get("CROSS_PC_SSH_CACHE") or Path.home() / ".cache" / "cross-pc-ssh" / "locations.json")
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
MAX_ENCODED = 7000  # cmd.exe caps a command line at 8191 characters; only the fixed bootstrap goes there
EXIT_IDENTITY = 3
# Read-only agent: only these built-in tools exist in the session (so the peer's allow rules can't add Bash, Edit
# or Write), and no MCP servers start.
CLAUDE_READ_ONLY = ["--permission-mode", "dontAsk", "--strict-mcp-config", "--tools", "Read,Grep,Glob"]
# Names cat never returns, even inside the checkout; matched case-insensitively against each path segment.
SECRET_DIRS = {".git", ".ssh", ".gnupg", ".aws", ".azure", ".kube"}
SECRET_NAMES = [re.compile(p, re.I) for p in (
    r"^\.env(\..+)?$", r"^secrets?(\..+)?$", r"^credentials?(\..+)?$", r".*\.(pem|key|pfx|p12|kdbx|ppk)$",
    r"^id_(rsa|dsa|ecdsa|ed25519)(_sk)?(\.pub)?$", r"^\.(npmrc|pypirc|netrc|git-credentials)$",
    r"^settings\.local\.json$", r"^mcp\.json$", r"^\.claude\.json$", r"^\.envrc$", r".*\.env$", r"^auth\.json$")]
SAFE_NAMES = [re.compile(p, re.I) for p in (r"^\.env\.(example|sample|template)$",)]

READ_ONLY_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree", "describe", "blame",
                 "grep", "shortlog", "cat-file", "rev-list", "merge-base", "name-rev", "for-each-ref"}
# Long options that write files, run programs or read files outside the checkout. git accepts any unambiguous
# abbreviation (--outp, --open=), so an option is refused when it is a prefix of one of these.
GIT_DENIED_LONG = ("output", "open-files-in-pager", "exec", "ext-diff", "no-index", "contents", "config", "file",
                   "orderfile", "ignore-revs-file", "exclude-from", "pathspec-from-file", "upload-pack",
                   # read untracked or ignored files (secrets), or run programs from the peer's git config
                   "untracked", "no-exclude-standard", "textconv", "show-signature", "filters")
# Short option letters with the same effect, anywhere in a cluster (-nf, -Ofile). -O: pager or order file.
GIT_DENIED_SHORT = {"*": "O", "grep": "f", "blame": "S", "ls-files": "X"}


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- pure logic (unit-tested)

def repo_slug(url: str | None) -> str | None:
    """Normalize a git remote URL to host/owner/name, lowercase, without .git."""
    if not url:
        return None
    u = url.strip()
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", u)  # scp-like: git@host:owner/name
    if m:
        host, path = m.groups()
    else:
        m = re.match(r"^[a-z+]+://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", u, re.I)
        if not m:
            return None
        host, path = m.groups()
    path = path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return f"{host}/{path}".lower()


def safe_rel(rel: str | None) -> str:
    """Return a checkout-relative Windows path, or raise UsageError. '' means the checkout root."""
    if rel is None or rel.strip() in ("", "."):
        return ""
    r = rel.strip().replace("/", "\\")
    if any(ord(c) < 32 for c in r) or any(c in r for c in '*?"<>|'):
        raise UsageError(f"path has characters that are not allowed: {rel!r}")
    if r.startswith("\\") or re.match(r"^[A-Za-z]:", r) or ":" in r:
        raise UsageError(f"path must be relative to the checkout: {rel!r}")
    parts = [p for p in r.split("\\") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise UsageError(f"path must not leave the checkout: {rel!r}")
    # Windows drops trailing dots and spaces and resolves 8.3 short names (SECRET~1.JSO), so a name could
    # reach a different file than the one the local checks saw.
    if any(p.endswith((".", " ")) or re.search(r"~\d", p) for p in parts):
        raise UsageError(f"path segments may not end in a dot or space or be 8.3 short names: {rel!r}")
    if any(re.fullmatch(r"(con|prn|aux|nul|com\d|lpt\d)(\..*)?", p, re.I) for p in parts):
        raise UsageError(f"path segments may not be Windows device names: {rel!r}")
    return "\\".join(parts)


def check_readable(rel: str) -> None:
    """Refuse files that look like secrets or machine-local settings, and anything under .git or .ssh."""
    parts = rel.split("\\")
    for part in parts:
        if part.lower() in SECRET_DIRS:
            raise UsageError(f"refused {rel!r}: {part} is not readable through this helper")
    name = parts[-1]
    if not any(p.match(name) for p in SAFE_NAMES) and any(p.match(name) for p in SECRET_NAMES):
        raise UsageError(f"refused {rel!r}: it looks like a secret or machine-local settings file")


def check_git_args(args: list[str]) -> list[str]:
    if not args:
        raise UsageError("git needs a subcommand")
    if args[0] not in READ_ONLY_GIT:
        raise UsageError(f"git {args[0]} is not allowed; read-only subcommands: {', '.join(sorted(READ_ONLY_GIT))}")
    sub, letters = args[0], GIT_DENIED_SHORT["*"] + GIT_DENIED_SHORT.get(args[0], "")
    for a in args[1:]:
        # Windows PowerShell 5.1 drops embedded double quotes and lets a trailing backslash join the next
        # argument when it builds a native command line, so git would see another option than the one checked.
        if '"' in a or a.endswith("\\"):
            raise UsageError(f"git argument {a!r} has a double quote or ends in a backslash")
        if a == "--":
            continue
        if a.startswith("--"):
            name = a[2:].split("=", 1)[0].lower()
            if name and any(d.startswith(name) for d in GIT_DENIED_LONG):
                raise UsageError(f"git option {a} is not allowed (writes files, runs programs or reads outside the checkout)")
        elif a.startswith("-") and len(a) > 1:
            if a == "-c" or any(ch in a[1:] for ch in letters):
                raise UsageError(f"git option {a} is not allowed for git {sub}")
        elif path_escapes(a):
            raise UsageError(f"git argument {a!r} points outside the checkout")
        else:
            # A pathspec or rev:path must not name a file cat would refuse (git grep, show HEAD:.env, cat-file).
            spec = a.split(":", 1)[1] if re.match(r"^[^:/\\]*:", a) else a
            if spec:
                check_readable(spec.replace("/", "\\"))
    return args


def path_escapes(arg: str) -> bool:
    """True for an absolute, drive, UNC or parent-relative path; rev specs such as HEAD~2..main pass."""
    if re.match(r"^[A-Za-z]:", arg):  # C:\x and drive-relative C:x
        return True
    a = arg.split(":", 1)[1] if re.match(r"^[^:/\\]+:[^/\\]", arg) else arg  # HEAD:docs/x -> docs/x
    if re.match(r"^([A-Za-z]:|[/\\])", a):
        return True
    return any(seg == ".." for seg in re.split(r"[/\\]", a))


def choose(local: dict, candidates: list[dict], path: str | None = None) -> dict:
    """Pick the peer checkout of the local repository from the peer's candidates.

    A candidate must share a root commit. Then: a matching origin beats a matching folder name, and a main
    checkout beats a linked worktree. A tie, or no match, raises UsageError listing what was found.
    """
    roots = set(local["roots"])

    def same_repo(c: dict) -> bool:
        if roots & set(c.get("roots") or []):
            return True
        # A shallow clone's "roots" are its shallow boundary, not the real root: accept it by origin only.
        return bool((c.get("shallow") or local.get("shallow")) and local["slug"] and c.get("slug") == local["slug"])

    same = [c for c in candidates if same_repo(c)]
    if path is not None:
        hit = [c for c in same if c["path"].lower().rstrip("\\") == path.lower().rstrip("\\")]
        if not hit:
            raise UsageError(f"{path} is not a checkout of {local['slug'] or local['name']} on the peer")
        return hit[0]
    if not same:
        raise UsageError(f"no checkout of {local['slug'] or local['name']} (root {sorted(roots)[0][:12]}) "
                         f"under the peer's roots; searched {len(candidates)} repositories")

    def rank(c):
        return (c.get("slug") == local["slug"] and local["slug"] is not None,
                c["name"].lower() == local["name"].lower(),
                not c.get("worktree"))

    same.sort(key=rank, reverse=True)
    if len(same) > 1 and rank(same[0]) == rank(same[1]):
        listing = "; ".join(c["path"] for c in same if rank(c) == rank(same[0]))
        raise UsageError(f"several peer checkouts match equally: {listing}. Pass --path with one of them.")
    return same[0]


def cache_key(local: dict) -> str:
    """The repository's GitHub identity (normalized origin), else its root commit."""
    return local["slug"] or "root:" + local["roots"][0]


def want_roots(local: dict, target: dict) -> list[str]:
    """Root commits the guard accepts on the peer: this checkout's, plus the peer's own when either side is
    shallow (a shallow boundary was matched by origin, so only those commits prove it is the same clone)."""
    extra = (target.get("roots") or []) if (target.get("shallow") or local.get("shallow")) else []
    return list(dict.fromkeys([*local["roots"], *extra]))


def recalled_target(cache: dict, local: dict, peer: str) -> dict | None:
    """The remembered peer checkout as a target, or None. A shallow match is never served from the cache: its
    guard roots come from the peer itself, and roots read from a cache file could point at another repo."""
    path = recall(cache, local, peer)
    if not path or local.get("shallow") or cache[cache_key(local)]["peers"][peer].get("shallow"):
        return None
    return {"path": path}


def recall(cache: dict, local: dict, peer: str) -> str | None:
    """The remembered peer path for this repository, if the entry still has the same root commit."""
    entry = cache.get(cache_key(local)) or {}
    if entry.get("root") not in local["roots"]:
        return None
    return ((entry.get("peers") or {}).get(peer) or {}).get("path")


def remember(cache: dict, local: dict, peer: str, remote_path: str, when: str, found: dict | None = None) -> None:
    entry = cache.setdefault(cache_key(local), {})
    entry.update({"github": local["origin"], "root": local["roots"][0], "local": local["path"]})
    record: dict = {"path": remote_path, "found": when}
    if found and (found.get("shallow") or local.get("shallow")):
        record["shallow"] = True  # remembered only so the next call searches again
    entry.setdefault("peers", {})[peer] = record


def forget(cache: dict, local: dict, peer: str) -> None:
    ((cache.get(cache_key(local)) or {}).get("peers") or {}).pop(peer, None)


def load_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # missing or damaged: the next search rebuilds it


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def ps_quote(s: str) -> str:
    """A PowerShell expression that evaluates to s. The text is embedded as base64, because a single-quoted
    literal is also closed by U+2018..U+201B, which would let a path or argument run code on the peer."""
    b64 = base64.b64encode(str(s).encode("utf-8")).decode("ascii")
    return f"([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}')))"


def encode(script: str) -> str:
    b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    if len(b64) > MAX_ENCODED:
        raise UsageError(f"remote script too long for cmd.exe ({len(b64)} encoded characters)")
    return b64


PRELUDE = "$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
# The only text on the remote command line: read the real script from stdin (base64 UTF-8) and run it.
BOOT = ("$s=[Console]::In.ReadToEnd();"
        "& ([scriptblock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($s.Trim()))))")


def guard(path: str, roots: list[str]) -> str:
    """PowerShell that enters the checkout and stops with exit 3 unless it is still the same repository."""
    want = ",".join(ps_quote(r) for r in roots)
    return (PRELUDE + f"$c={ps_quote(path)};try{{Set-Location -LiteralPath $c -ErrorAction Stop}}catch{{"
            f"[Console]::Error.WriteLine('not found: '+$c);exit {EXIT_IDENTITY}}};"
            f"$w=@({want});$r=@(git rev-list --max-parents=0 --all 2>$null);"
            "$t=(git rev-parse --show-toplevel 2>$null) -replace '/','\\';"
            "if(-not($r|Where-Object{$w -contains $_}) -or $t -ne $c){"
            "[Console]::Error.WriteLine('identity check failed: '+$c+' is not the expected checkout');"
            f"exit {EXIT_IDENTITY}}};")


def inside(rel: str) -> str:
    """PowerShell that resolves REL under the checkout and refuses reparse points on the way."""
    return (f"$p=$c;foreach($s in ({ps_quote(rel)} -split '\\\\'|Where-Object{{$_}})){{$p=Join-Path $p $s;"
            "$i=Get-Item -LiteralPath $p -Force -ErrorAction Stop;"
            "if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){"
            "[Console]::Error.WriteLine('refused: '+$p+' is a link');exit 4}};")


LOCATE = PRELUDE + (
    "$roots=@(%s);if(-not $roots.Count){$roots=@(Get-PSDrive -PSProvider FileSystem|"
    "ForEach-Object{Join-Path $_.Root 'Projects'})+@(Join-Path $HOME 'Projects')};"
    "$o=foreach($r in ($roots|Where-Object{Test-Path -LiteralPath $_}|Select-Object -Unique)){"
    "Get-ChildItem -LiteralPath $r -Directory -Force -ErrorAction SilentlyContinue|"
    "Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName '.git')}|ForEach-Object{"
    "$g=Get-Item -LiteralPath (Join-Path $_.FullName '.git') -Force;"
    "[pscustomobject]@{path=$_.FullName;name=$_.Name;worktree=-not $g.PSIsContainer;"
    "origin=(git -C $_.FullName remote get-url origin 2>$null);"
    "roots=@(git -C $_.FullName rev-list --max-parents=0 --all 2>$null);"
    "shallow=((git -C $_.FullName rev-parse --is-shallow-repository 2>$null) -eq 'true')}}};"
    "ConvertTo-Json -Compress -Depth 3 @($o)"
)


# ---------------------------------------------------------------- local side

def git_local(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def local_identity(repo: Path) -> dict:
    top = git_local(repo, "rev-parse", "--show-toplevel")
    if not top:
        raise UsageError(f"{repo} is not inside a git checkout")
    origin = git_local(repo, "remote", "get-url", "origin") or None
    # Every ref's roots, not only HEAD's: the checked-out branch may have an unrelated history.
    roots = sorted(set(git_local(repo, "rev-list", "--max-parents=0", "--all").split()))
    if not roots:
        raise UsageError("this checkout has no commits")
    return {"path": top, "name": Path(top).name, "origin": origin, "slug": repo_slug(origin), "roots": roots,
            "shallow": git_local(repo, "rev-parse", "--is-shallow-repository") == "true",
            "head": git_local(repo, "rev-parse", "HEAD"), "branch": git_local(repo, "rev-parse", "--abbrev-ref", "HEAD")}


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise UsageError(f"cannot read {CONFIG}: {e}")


def resolve_peer(arg: str | None, cfg: dict) -> str:
    peer = arg or os.environ.get("CROSS_PC_SSH_PEER") or cfg.get("default_peer")
    if not peer:
        raise UsageError("no peer: pass --peer <ssh alias>, set CROSS_PC_SSH_PEER, or set default_peer in " + str(CONFIG))
    if not re.fullmatch(r"[A-Za-z0-9][\w.@-]*", peer):
        raise UsageError(f"peer must be an ssh alias or user@host, got {peer!r}")
    return peer


def ssh_argv(peer: str) -> list[str]:
    return ["ssh", *SSH_OPTS, peer, "powershell -NoProfile -NonInteractive -EncodedCommand " + encode(BOOT)]


def ssh(peer: str, script: str, timeout: int = 120, capture: bool = True):
    # The script goes on stdin, which then closes, so a nested ssh inside the session can't wait on it.
    try:
        return subprocess.run(ssh_argv(peer), input=base64.b64encode(script.encode("utf-8")),
                              capture_output=capture, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UsageError(f"ssh to {peer} timed out after {timeout}s")


def agent_body(harness: str, allow_edits: bool, prompt: str) -> str:
    """PowerShell that pipes the prompt (embedded as base64) into a headless agent in the checkout ($c)."""
    if harness == "claude":
        cmd = "& $x -p --output-format text " + (
            "--permission-mode acceptEdits" if allow_edits else " ".join(CLAUDE_READ_ONLY))
    elif harness == "codex":
        cmd = "& $x exec -C $c -s " + ("workspace-write" if allow_edits else "read-only") + " -"
    else:
        raise UsageError(f"unknown harness {harness!r}")
    # Applications only (.exe/.cmd): an npm .ps1 shim is blocked by the default execution policy, and the
    # error would not change PowerShell's exit code.
    return ("$OutputEncoding=[Text.Encoding]::UTF8;"
            f"$x=(Get-Command {harness} -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1).Source;"
            f"if(-not $x){{[Console]::Error.WriteLine('{harness} is not on PATH in the ssh session');exit 5}};"
            f"{ps_quote(prompt)}|{cmd};exit $LASTEXITCODE")


def clean_err(b: bytes) -> str:
    lines = b.decode("utf-8", "replace").splitlines()
    return "\n".join(l for l in lines if l.strip() and not l.startswith("#< CLIXML") and not l.startswith("** ")
                     and "post-quantum" not in l and "store now, decrypt later" not in l and "openssh.com/pq" not in l)


def locate(peer: str, local: dict, cfg: dict, path: str | None) -> dict:
    roots = (cfg.get("peers", {}).get(peer, {}) or {}).get("roots", [])
    r = ssh(peer, LOCATE % ",".join(ps_quote(x) for x in roots))
    if r.returncode != 0:
        raise UsageError(f"ssh {peer} failed (exit {r.returncode}): {clean_err(r.stderr)}")
    text = r.stdout.decode("utf-8", "replace").strip() or "[]"
    try:
        found = json.loads(text)
    except ValueError:
        raise UsageError(f"unexpected answer from {peer}: {text[:200]!r}")
    found = [found] if isinstance(found, dict) else (found or [])
    found = [c for c in found if isinstance(c, dict) and c.get("path")]
    for c in found:
        c["slug"] = repo_slug(c.get("origin"))
        c["roots"] = c.get("roots") or []
    return choose(local, found, path)


# ---------------------------------------------------------------- commands

def run_payload(peer: str, target: dict, local: dict, body: str,
                timeout: int = 120, stream: bool = False, retry: bool = False) -> int:
    script = guard(target["path"], want_roots(local, target)) + body
    r = ssh(peer, script, timeout=timeout, capture=not stream)
    if retry and r.returncode == EXIT_IDENTITY:
        return r.returncode  # the caller searches again; nothing ran
    if not stream:
        sys.stdout.flush()
        sys.stdout.buffer.write(r.stdout)
        sys.stdout.buffer.flush()
        err = clean_err(r.stderr)
        if err:
            print(err, file=sys.stderr)
    if r.returncode == EXIT_IDENTITY:
        print("stopped: the peer checkout no longer matches this repository", file=sys.stderr)
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SSH work on a paired Windows PC, scoped to the peer's checkout of this repository.")
    ap.add_argument("--peer", help="ssh alias of the other PC (default: CROSS_PC_SSH_PEER, then config)")
    ap.add_argument("--repo", default=".", help="a path inside the local checkout (default: current directory)")
    ap.add_argument("--path", help="the peer checkout to use when several match (still verified)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami", help="this checkout's identity: path, origin, root commit, HEAD")
    p = sub.add_parser("locate", help="find the peer's checkout of this repository (cached)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--rescan", action="store_true", help="ignore the cache and search the peer again")
    sub.add_parser("status", help="branch, HEAD and git status on the peer, compared with this checkout")
    p = sub.add_parser("ls", help="list a folder inside the peer checkout")
    p.add_argument("rel", nargs="?", default="")
    p = sub.add_parser("cat", help="print a text file inside the peer checkout (secret-looking files refused)")
    p.add_argument("rel")
    p.add_argument("--max-bytes", type=int, default=200_000)
    p = sub.add_parser("git", help="a read-only git subcommand in the peer checkout")
    p.add_argument("args", nargs=argparse.REMAINDER)
    p = sub.add_parser("agent", help="run a headless agent in the peer checkout, read-only unless --allow-edits")
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--harness", choices=("claude", "codex"), default="claude")
    p.add_argument("--allow-edits", action="store_true",
                   help="claude acceptEdits / codex workspace-write instead of read-only; needs the user's approval")
    p.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)

    try:
        local = local_identity(Path(a.repo))
        if a.cmd == "whoami":
            print(json.dumps({k: local[k] for k in ("path", "origin", "slug", "roots", "branch", "head")}, indent=1))
            return 0
        cfg = load_config()
        peer = resolve_peer(a.peer, cfg)
        cache = load_cache(CACHE)
        cached = None if a.path or getattr(a, "rescan", False) else recalled_target(cache, local, peer)

        def search() -> dict:
            found = locate(peer, local, cfg, a.path)
            remember(cache, local, peer, found["path"], datetime.now(timezone.utc).isoformat(timespec="seconds"), found)
            save_cache(CACHE, cache)
            return found

        def with_target(run) -> int:
            """Run against the cached path; if it is gone or no longer this repository, search once and rerun."""
            nonlocal target
            if cached:
                rc = run(target, True)
                if rc != EXIT_IDENTITY:
                    return rc
                print(f"cached location {target['path']} no longer matches; searching {peer} again", file=sys.stderr)
                forget(cache, local, peer)
                save_cache(CACHE, cache)
                target = search()
            return run(target, False)

        target = cached or search()
        if a.cmd == "locate":
            if cached:
                rc = with_target(lambda t, retry: run_payload(peer, t, local, "", retry=retry))
                if rc != 0:
                    return rc
            info = {"peer": peer, "path": target["path"], "origin": target.get("origin"),
                    "origin_matches": target.get("slug") == local["slug"] if "slug" in target else None,
                    "worktree": bool(target.get("worktree")), "root": local["roots"][0],
                    "from_cache": "slug" not in target}
            how = ("cached, verified" if info["from_cache"] else
                   f"origin {'matches' if info['origin_matches'] else 'differs: ' + str(target.get('origin'))}")
            print(json.dumps(info, indent=1) if a.json else f"{peer}: {target['path']}  ({how}, root {info['root'][:12]})")
            return 0
        if a.cmd == "status":
            print(f"local: {local['branch']} {local['head'][:12]}", flush=True)
            return with_target(lambda t, retry: run_payload(peer, t, local,
                               "\"peer:  $(git rev-parse --abbrev-ref HEAD) $((git rev-parse HEAD).Substring(0,12))\";"
                               "git --no-pager status -sb;git --no-pager log -1 --format='%h %cI %s'", retry=retry))
        if a.cmd == "ls":
            rel = safe_rel(a.rel)
            return with_target(lambda t, retry: run_payload(peer, t, local, inside(rel) +
                               "Get-ChildItem -LiteralPath $p -Force|ForEach-Object{"
                               "'{0,-4} {1,12} {2:yyyy-MM-dd HH:mm} {3}' -f $(if($_.PSIsContainer){'dir'}else{''}),"
                               "$(if($_.PSIsContainer){''}else{$_.Length}),$_.LastWriteTime,$_.Name}", retry=retry))
        if a.cmd == "cat":
            rel = safe_rel(a.rel)
            if not rel:
                raise UsageError("cat needs a file path")
            check_readable(rel)
            return with_target(lambda t, retry: run_payload(peer, t, local, inside(rel) +
                               f"$b=[IO.File]::ReadAllBytes($p);$n=[Math]::Min($b.Length,{int(a.max_bytes)});"
                               "[Console]::Out.Write([Text.Encoding]::UTF8.GetString($b,0,$n));"
                               "if($b.Length -gt $n){[Console]::Error.WriteLine(\"[truncated at $n of $($b.Length) bytes]\")}", retry=retry))
        if a.cmd == "git":
            args = check_git_args(a.args[1:] if a.args[:1] == ["--"] else a.args)
            return with_target(lambda t, retry: run_payload(peer, t, local, "$env:GIT_PAGER='cat';& git --no-pager " +
                               " ".join(ps_quote(x) for x in args), retry=retry))
        if a.cmd == "agent":
            body = agent_body(a.harness, a.allow_edits, Path(a.prompt_file).read_text(encoding="utf-8"))
            print(f"[{peer} {a.harness} {'edits allowed' if a.allow_edits else 'read-only'}]", file=sys.stderr, flush=True)
            return with_target(lambda t, retry: run_payload(peer, t, local, body, timeout=a.timeout, retry=retry))
    except UsageError as e:
        print(f"cross_pc_ssh: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
