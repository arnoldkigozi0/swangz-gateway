"""Which build is running: the version and, when it can be known, the commit.

The commit comes from GATEWAY_COMMIT, else a COMMIT file beside the code (written by a deploy that copies the code
without its .git folder), else the checkout's own .git files, read directly: no git program is run and nothing leaves the machine. It is an identity
for operators ("is the fix live?"), never a secret and never an input to any decision. Unknown is "", not a guess."""
import os
import re
from pathlib import Path

from . import __version__

_HEX = re.compile(r"[0-9a-f]{7,40}")
SHORT = 12


def _clean(value):
    value = (value or "").strip().lower()
    return value[:SHORT] if _HEX.fullmatch(value) else ""


def _from_git(root):
    git = Path(root) / ".git"
    if git.is_file():  # a worktree: ".git" is a one-line pointer to the real folder
        pointer = git.read_text(errors="replace").strip()
        if not pointer.startswith("gitdir:"):
            return ""
        git = (git.parent / pointer[7:].strip()).resolve()
    if not git.is_dir():
        return ""
    head = (git / "HEAD").read_text(errors="replace").strip()
    if not head.startswith("ref:"):
        return _clean(head)
    ref = head[4:].strip()
    if ".." in ref or not ref.startswith("refs/"):
        return ""
    common = git
    if (git / "commondir").is_file():
        common = (git / (git / "commondir").read_text(errors="replace").strip()).resolve()
    for base in (git, common):
        if (base / ref).is_file():
            return _clean((base / ref).read_text(errors="replace"))
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(errors="replace").splitlines():
            sha, _, name = line.partition(" ")
            if name.strip() == ref:
                return _clean(sha)
    return ""


def commit(root=None, env=None):
    env = os.environ if env is None else env
    declared = _clean(env.get("GATEWAY_COMMIT"))
    if declared:
        return declared
    root = Path(root or Path(__file__).resolve().parents[1])
    try:
        stamp = root / "COMMIT"  # written by deploy/setup-gateway-server.sh, which copies the code without .git
        if stamp.is_file():
            return _clean(stamp.read_text(errors="replace")[:64])
        return _from_git(root)
    except (OSError, ValueError):
        return ""


_cached = None


def info():
    """{"version", "commit"}; read once per process, because it describes the code this process started with."""
    global _cached
    if _cached is None:
        _cached = {"version": __version__, "commit": commit()}
    return dict(_cached)
