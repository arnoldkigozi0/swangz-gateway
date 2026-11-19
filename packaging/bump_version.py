"""Raise the Swangz app's version in every place that states it, in one reviewed commit.

    python3 packaging/bump_version.py 0.2.0                 # app version + the version the Hub advertises as latest
    python3 packaging/bump_version.py 0.2.0 --minimum 0.2.0 # also refuse older apps (only when they must update)
    python3 packaging/bump_version.py --check               # print where the versions stand, change nothing

Places: `swangz_client/__init__.py __version__` (the app, the DMG and installer names, the updater's comparison) and
`gateway/enroll.py CLIENT_LATEST` (what the Hub tells devices is the newest). `CLIENT_MINIMUM` changes only with
--minimum, because raising it stops every older app at its next check-in. The build workflows still raise PATCH by
the run number (0.2.0 -> 0.2.<run>), so RC builds of 0.2.0 sort above it. Versions are MAJOR.MINOR.PATCH only
(swangz_client/updater.py). It never commits, tags or publishes: review the diff, run the tests, open a PR.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "swangz_client" / "__init__.py"
ENROLL = ROOT / "gateway" / "enroll.py"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PLACES = {"__version__": APP, "CLIENT_LATEST": ENROLL, "CLIENT_MINIMUM": ENROLL}


def parse(v):
    m = SEMVER.match(v or "")
    if not m:
        raise ValueError(f"{v!r} is not MAJOR.MINOR.PATCH")
    return tuple(int(x) for x in m.groups())


def pattern(name):
    return re.compile(rf'^({re.escape(name)} = )"([^"]*)"$', re.M)


def read(root=ROOT):
    out = {}
    for name, path in PLACES.items():
        path = root / path.relative_to(ROOT)
        found = pattern(name).findall(path.read_text(encoding="utf-8"))
        if len(found) != 1:
            raise SystemExit(f"{path.relative_to(root)}: expected one `{name} = \"...\"` line, found {len(found)}")
        out[name] = found[0][1]
    return out


def bump(version, minimum=None, root=ROOT):
    """Write the new values; -> {name: (old, new)} for what changed. Refuses a version that is not higher."""
    parse(version)
    now = read(root)
    if parse(version) <= parse(now["__version__"]):
        raise SystemExit(f"{version} is not higher than the current {now['__version__']}")
    want = {"__version__": version, "CLIENT_LATEST": version}
    if minimum:
        if parse(minimum) > parse(version):
            raise SystemExit(f"--minimum {minimum} is above the new version {version}")
        if parse(minimum) < parse(now["CLIENT_MINIMUM"]):
            raise SystemExit(f"--minimum {minimum} would lower the current minimum {now['CLIENT_MINIMUM']}")
        want["CLIENT_MINIMUM"] = minimum
    changed = {}
    for name, value in want.items():
        path = root / PLACES[name].relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        path.write_text(pattern(name).sub(lambda m: f'{m.group(1)}"{value}"', text), encoding="utf-8")
        if now[name] != value:
            changed[name] = (now[name], value)
    return changed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("version", nargs="?")
    p.add_argument("--minimum", help="also raise gateway/enroll.py CLIENT_MINIMUM (older apps must update)")
    p.add_argument("--check", action="store_true", help="print the current values and change nothing")
    args = p.parse_args(argv)
    if args.check or not args.version:
        for name, value in read().items():
            print(f"{name} = {value}")
        return 0 if args.check else 2
    try:
        changed = bump(args.version, args.minimum)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    for name, (old, new) in changed.items():
        print(f"{name}: {old} -> {new}")
    print("Next: python3 -m unittest discover -s tests -t . , then a PR. Nothing was committed or published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
