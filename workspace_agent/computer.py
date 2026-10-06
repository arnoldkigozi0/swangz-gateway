"""Swangz's company browsers on one of Swangz's own computers — a Windows PC or a Mac — instead of a server.

The same Workspace Agent (agent.py, beside this file) runs the browsers. This program looks after
everything around it, so the computer needs only Docker Desktop and Python:

  * a Cloudflare tunnel gives the browsers a public https address, although nothing on the internet can
    reach the computer itself — no public IP, no router settings;
  * the agent tells the gateway that address every minute and gets back which tools need browsers and the
    video relay to use, so staff can work in them from anywhere;
  * it starts whenever someone signs in to the computer, keeps the computer awake, and opens the tunnel
    again if it drops.

The console's Settings → Company browsers page gives each computer its key and the exact command:

  python  workspace_agent/computer.py setup --host windows --gateway https://swangz-ai.netlify.app --key <key>
  python3 workspace_agent/computer.py setup --host mac     --gateway https://swangz-ai.netlify.app --key <key>

then, any time:

  computer.py status     is it running, connected, in use
  computer.py stop       stop it and its browsers (it starts again at the next sign-in, or with `start`)
  computer.py start      start it again in the background
  computer.py remove     stop it, and no longer start it with the computer
  computer.py run        what starts with the computer: everything, in the foreground

Its files live in ~/swangz-workspace (agent.json — which holds the key —, the browsers' state, logs).
Standard library only; Python 3.9+.
"""

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from . import agent as agent_mod
except ImportError:  # run as a script: the agent is the file beside this one
    sys.path.insert(0, HERE)
    import agent as agent_mod  # noqa: E402

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
LABELS = {"windows": "Windows PC", "mac": "Mac"}
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "swangz-workspace")
STARTUP_NAME = "Swangz Workspace"  # Windows: the sign-in entry
MAC_LABEL = "com.swangz.workspace"  # Mac: the LaunchAgent
TUNNEL_LINK = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
NO_WINDOW = agent_mod.NO_WINDOW
DETACHED = 0x00000008 | 0x00000200  # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
# where Docker Desktop puts its command, which a program started at sign-in may not find on its own
DOCKER_DIRS = ([os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Docker", "Docker", "resources", "bin")]
               if IS_WINDOWS else ["/usr/local/bin", "/opt/homebrew/bin", "/Applications/Docker.app/Contents/Resources/bin"])
MAC_PATH = ":".join(DOCKER_DIRS + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"])


def say(message):
    print(message, flush=True)


def paths(folder):
    return {"dir": folder, "config": os.path.join(folder, "agent.json"), "data": os.path.join(folder, "data"),
            "logs": os.path.join(folder, "logs"), "run": os.path.join(folder, "run.json"),
            "bin": os.path.join(folder, "bin")}


# ---------------------------------------------------------------- the machine

def find_docker():
    found = shutil.which("docker")
    if found:
        return found
    for d in DOCKER_DIRS:
        candidate = os.path.join(d, "docker.exe" if IS_WINDOWS else "docker")
        if os.path.exists(candidate):
            return candidate
    return None


def docker_up(docker):
    try:
        return subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                              timeout=30, creationflags=NO_WINDOW).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def start_docker_desktop():
    if IS_WINDOWS:
        exe = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Docker", "Docker", "Docker Desktop.exe")
        if os.path.exists(exe):
            subprocess.Popen([exe], creationflags=DETACHED | NO_WINDOW, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_MAC:
        subprocess.run(["open", "-g", "-a", "Docker"], capture_output=True)


def wait_for_docker(docker, seconds=240):
    """Docker answering, starting Docker Desktop first if it isn't. -> True when it answers."""
    if docker_up(docker):
        return True
    start_docker_desktop()
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(5)
        if docker_up(docker):
            return True
    return False


def physical_memory_gb():
    try:
        if IS_WINDOWS:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            s = Status()
            s.dwLength = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return round(s.ullTotalPhys / 2 ** 30, 1)
        if IS_MAC:
            return round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2 ** 30, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except Exception:
        return 0.0


def browsers_that_fit(docker_gb):
    """How many browsers Docker's memory carries at once: about 2 GB each, with 2 GB kept for Docker itself."""
    return max(1, min(20, int((docker_gb - 2) // 2)))


def lan_ip():
    """This computer's address on its own network (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        return "" if ip.startswith("127.") else ip
    except OSError:
        return ""
    finally:
        s.close()


def keep_awake():
    """A computer that sleeps drops everyone in its browsers: stay awake while this runs."""
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    elif IS_MAC:
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- the tunnel

def find_cloudflared(bin_dir):
    name = "cloudflared.exe" if IS_WINDOWS else "cloudflared"
    for candidate in (os.path.join(bin_dir, name), shutil.which("cloudflared"),
                      os.path.join(os.path.expanduser("~"), ".local", "bin", name),
                      "/opt/homebrew/bin/cloudflared", "/usr/local/bin/cloudflared"):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def download_cloudflared(bin_dir):
    """Cloudflare's tunnel program, from its official GitHub releases, into our own folder."""
    os.makedirs(bin_dir, exist_ok=True)
    if IS_WINDOWS:
        target = os.path.join(bin_dir, "cloudflared.exe")
        fetch(CLOUDFLARED + "cloudflared-windows-amd64.exe", target)
        return target
    if not IS_MAC:
        raise SystemExit("On Linux, install cloudflared from Cloudflare's package repository first.")
    arch = "arm64" if platform.machine() == "arm64" else "amd64"
    archive = os.path.join(bin_dir, "cloudflared.tgz")
    fetch(CLOUDFLARED + f"cloudflared-darwin-{arch}.tgz", archive)
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if os.path.basename(m.name) == "cloudflared" and m.isfile())
        with tar.extractfile(member) as src, open(os.path.join(bin_dir, "cloudflared"), "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.remove(archive)
    target = os.path.join(bin_dir, "cloudflared")
    os.chmod(target, 0o755)
    return target


def fetch(url, target):
    tmp = target + ".part"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.URLError as exc:
        if IS_MAC and "CERTIFICATE_VERIFY_FAILED" in str(exc):
            raise SystemExit(https_help()) from None
        raise SystemExit(f"Couldn't download {url}: {getattr(exc, 'reason', exc)}") from None
    os.replace(tmp, target)


def https_help():
    return ("This Python can't check https certificates yet. If it came from python.org, open "
            "Applications → Python 3.x → Install Certificates.command, then run this again.")


class Tunnel:
    """cloudflared, opened again whenever it closes. A quick tunnel's address is new every time it opens;
    a named one (tunnel_token + public_url in agent.json) keeps its address for good."""

    def __init__(self, cloudflared, cfg, log_dir, on_address):
        self.cloudflared, self.cfg, self.log_dir, self.on_address = cloudflared, cfg, log_dir, on_address
        self.proc = None

    def run_forever(self):
        while True:
            self.open()
            self.proc.wait()
            agent_mod.log(f"the tunnel closed (exit {self.proc.returncode}); opening it again")
            time.sleep(5)

    def open(self):
        env = dict(os.environ)
        if self.cfg.get("tunnel_token"):  # the token goes in the environment, not on the command line
            env["TUNNEL_TOKEN"] = self.cfg["tunnel_token"]
            args = ["tunnel", "--no-autoupdate", "run"]
        else:
            args = ["tunnel", "--no-autoupdate", "--url", "http://" + self.cfg["listen"]]
        self.proc = subprocess.Popen([self.cloudflared, *args], env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        if self.cfg.get("tunnel_token"):
            self.on_address(self.cfg["public_url"])
        threading.Thread(target=self._read, args=(self.proc,), name="tunnel-log", daemon=True).start()

    def _read(self, proc):
        found = bool(self.cfg.get("tunnel_token"))
        with open(os.path.join(self.log_dir, "tunnel.log"), "a", encoding="utf-8") as out:
            for raw in proc.stderr:
                line = raw.decode("utf-8", "replace")
                out.write(line)
                out.flush()
                hit = None if found else TUNNEL_LINK.search(line)
                if hit:
                    found = True
                    self.on_address(hit.group(0))

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ---------------------------------------------------------------- the commands

def write_config(p, host, gateway, key, max_running):
    """agent.json for this computer, keeping anything already edited in it."""
    try:
        with open(p["config"], encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, ValueError):
        cfg = {"max_running": max_running, "screen": "1280x720@25", "image": agent_mod.DEFAULTS["image"]}
    cfg.update(token=key, gateway=gateway.rstrip("/"), host=host, data=p["data"], listen=agent_mod.DEFAULTS["listen"],
               max_running=max_running)
    os.makedirs(p["dir"], exist_ok=True)
    fd = os.open(p["config"] + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # it holds the key
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(p["config"] + ".tmp", p["config"])
    return agent_mod.check_config(cfg)


def setup(args):
    host = args.host or ("mac" if IS_MAC else "windows")
    p = paths(args.dir)
    label = LABELS[host]
    if not re.fullmatch(r"[0-9a-f]{64}", args.key or ""):
        raise SystemExit("--key is the 64-character key from the console: Settings → Company browsers → " + label)
    if not (args.gateway or "").startswith("https://"):
        raise SystemExit("--gateway is the address people open Swangz AI at, e.g. https://swangz-ai.netlify.app")
    say(f"Setting up this {label} for Swangz's company browsers (files in {p['dir']})")
    try:
        with urllib.request.urlopen(args.gateway.rstrip("/") + "/healthz", timeout=30) as resp:
            resp.read()
        say("· Gateway: " + args.gateway + " answers")
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            raise SystemExit(https_help()) from None
        raise SystemExit(f"Can't reach the gateway at {args.gateway} ({getattr(exc, 'reason', exc)}). "
                         "Check the address and this computer's internet, then run this again.") from None

    docker = find_docker()
    if not docker:
        raise SystemExit("Docker Desktop isn't installed. Install it first: "
                         + ("winget install -e --id Docker.DockerDesktop" if IS_WINDOWS
                            else "https://www.docker.com/products/docker-desktop/")
                         + " — open it once, accept its terms, then run this again.")
    say("· Docker: " + ("answering" if docker_up(docker) else "starting Docker Desktop…"))
    if not wait_for_docker(docker):
        raise SystemExit("Docker Desktop didn't start. Open it by hand, wait until it says it's running, and run this again.")
    info = agent_mod.Docker(docker).info()
    docker_gb, machine_gb = info.get("memory_gb", 0.0), physical_memory_gb()
    fits = browsers_that_fit(docker_gb)
    say(f"· Memory: Docker may use {docker_gb:g} GB of this computer's {machine_gb:g} GB — about {fits} browsers at once")
    if fits < 20 and machine_gb and docker_gb < machine_gb * 0.75:
        if IS_WINDOWS:
            give = max(8, int(machine_gb - 10))
            say(f"  To run more, give Docker more memory: put these two lines in {os.path.join(os.path.expanduser('~'), '.wslconfig')}\n"
                f"      [wsl2]\n      memory={give}GB\n"
                "  then run  wsl --shutdown , start Docker Desktop again, and run this setup again.")
        else:
            say("  To run more, give Docker more memory: Docker Desktop → Settings → Resources → Memory, then run this setup again.")

    cfg = write_config(p, host, args.gateway, args.key, fits)
    say(f"· Settings: {p['config']} — at most {cfg['max_running']} browsers at once (max_running)")

    cloudflared = find_cloudflared(p["bin"])
    if not cloudflared:
        say("· Downloading Cloudflare's tunnel program…")
        cloudflared = download_cloudflared(p["bin"])
    say("· Tunnel program: " + cloudflared)

    if not agent_mod.Docker(docker).image_present(cfg["image"]):
        say(f"· Downloading the browser ({cfg['image']}, about 1 GB — once)…")
        if subprocess.run([docker, "pull", cfg["image"]]).returncode != 0:
            raise SystemExit("Couldn't download the browser image. Check the internet connection and run this again.")

    stop(args, quiet=True)
    install_autostart(p)
    say("· Starts by itself whenever someone signs in to this computer")
    start(args, quiet=True)
    say("· Starting, and checking in with the gateway…")
    for _ in range(45):
        time.sleep(2)
        health = local_health(cfg)
        seen = (health or {}).get("gateway") or {}
        if seen.get("ok"):
            say(f"\nDone. This {label} is connected. In the console: Settings → Company browsers → {label} "
                + ("is in use." if seen.get("active") else "shows Online — choose Use this one when you're ready."))
            return
    seen = ((local_health(cfg) or {}).get("gateway") or {})
    say(f"\nIt's running but hasn't reached the gateway yet{': ' + seen['error'] if seen.get('error') else ''}.\n"
        f"Logs: {os.path.join(p['logs'], 'workspace.log')} — or run: computer.py status")


def run(args):
    p = paths(args.dir)
    os.makedirs(p["logs"], exist_ok=True)
    log_to_file(os.path.join(p["logs"], "workspace.log"))
    cfg = agent_mod.load_config(p["config"])
    docker = find_docker() or "docker"
    keep_awake()
    agent_mod.log(f"starting on this {LABELS.get(cfg['host'], 'computer')}")
    while not wait_for_docker(docker):
        agent_mod.log("Docker isn't answering yet; waiting for Docker Desktop")
    if not agent_mod.Docker(docker).image_present(cfg["image"]):
        agent_mod.log(f"downloading the browser image {cfg['image']}")
        subprocess.run([docker, "pull", "-q", cfg["image"]], capture_output=True, creationflags=NO_WINDOW)
    cfg["lan_ip"] = cfg["lan_ip"] or lan_ip()  # people on this network connect straight to it
    agent = agent_mod.Agent(cfg, agent_mod.Docker(docker))
    try:
        server = agent_mod.make_server(agent)
    except OSError:
        agent_mod.log(f"already running ({cfg['listen']} is taken)")
        return 1
    threading.Thread(target=server.serve_forever, name="agent", daemon=True).start()
    agent.start_sweeping()
    agent.start_hello()  # quiet until the tunnel has an address

    cloudflared = find_cloudflared(p["bin"]) or download_cloudflared(p["bin"])

    def on_address(url):
        agent.cfg["public_url"] = url.rstrip("/")
        agent_mod.log(f"browsers are at {url}")
        save_run(p, tunnel.proc.pid if tunnel.proc else None, url)
        agent.say_hello()

    tunnel = Tunnel(cloudflared, cfg, p["logs"], on_address)

    def bye(*_):
        tunnel.close()
        os._exit(0)

    signal.signal(signal.SIGTERM, bye)
    save_run(p, None, "")
    try:
        tunnel.run_forever()
    finally:
        tunnel.close()


def start(args, quiet=False):
    """In the background, now."""
    p = paths(args.dir)
    if IS_MAC and os.path.exists(plist_path()):
        subprocess.run(["launchctl", "load", "-w", plist_path()], capture_output=True)
    else:
        cmd = background_command(p)
        kwargs = {"creationflags": DETACHED | NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
        subprocess.Popen(cmd, cwd=HERE, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
    if not quiet:
        say("Started. computer.py status shows how it's doing.")


def stop(args, quiet=False):
    """Stop it and its browsers. People in them are dropped; their turns end at the gateway as usual."""
    p = paths(args.dir)
    if IS_MAC and os.path.exists(plist_path()):
        subprocess.run(["launchctl", "unload", plist_path()], capture_output=True)  # or launchd starts it again
    state = read_run(p)
    for pid in (state.get("tunnel_pid"), state.get("pid")):
        if pid and pid != os.getpid() and ours(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    docker = find_docker()
    if docker and docker_up(docker):
        ids = subprocess.run([docker, "ps", "-aq", "--filter", "label=swangz.workspace=1"], capture_output=True,
                             text=True, creationflags=NO_WINDOW).stdout.split()
        if ids:
            subprocess.run([docker, "rm", "-f", *ids], capture_output=True, creationflags=NO_WINDOW)
    if not quiet:
        say("Stopped. It starts again at the next sign-in to this computer, or with: computer.py start")


def remove(args):
    stop(args, quiet=True)
    uninstall_autostart()
    say("Stopped, and it no longer starts with this computer. Its settings and the browsers' sign-ins are kept "
        f"in {args.dir} and in Docker; setup brings it back.")


def status(args):
    p = paths(args.dir)
    try:
        cfg = agent_mod.load_config(p["config"])
    except (OSError, ValueError, agent_mod.ConfigError):
        raise SystemExit(f"Not set up yet ({p['config']}). Run setup with the key from the console.")
    label = LABELS.get(cfg["host"], "computer")
    health = local_health(cfg)
    if not health:
        say(f"Swangz Workspace on this {label}: NOT RUNNING — start it with: computer.py start")
        return
    seen = health.get("gateway") or {}
    ago = f"{int(time.time() - seen['at'])} s ago" if seen.get("at") else "not yet"
    say(f"Swangz Workspace on this {label}: running")
    say(f"  gateway:  {cfg['gateway']} — last check-in {ago}"
        + (": " + ("in use" if seen.get("active") else "standing by (another workspace is in use)") if seen.get("ok") else "")
        + (f" — {seen['error']}" if seen.get("error") else ""))
    say(f"  address:  {read_run(p).get('url') or 'waiting for the tunnel'}")
    say(f"  browsers: {health['browsers']} ({health['running']} running), at most {health['max_running'] or 'any number'} at once")
    say("  video:    " + ("through the relay — reachable from anywhere" if health.get("relay")
                         else "no relay yet (set GATEWAY_TURN_* on the gateway): only people on this computer's own network"))
    say(f"  docker:   {'ok' if health['docker'] else 'NOT ANSWERING'}")


# ---------------------------------------------------------------- bits

def local_health(cfg):
    req = urllib.request.Request(f"http://{cfg['listen']}/agent/health", headers={"Authorization": "Bearer " + cfg["token"]})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def save_run(p, tunnel_pid, url):
    with open(p["run"], "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "tunnel_pid": tunnel_pid, "url": url, "since": time.time()}, f)


def read_run(p):
    try:
        with open(p["run"], encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def ours(pid):
    """Is this process id still one of ours — python or cloudflared — and not a stranger that reused it?"""
    try:
        if IS_WINDOWS:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, creationflags=NO_WINDOW).stdout.lower()
        else:
            out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "comm="], capture_output=True, text=True).stdout.lower()
    except (OSError, ValueError):
        return False
    return "python" in out or "cloudflared" in out


class Tee:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s]

    def write(self, text):
        for s in self.streams:
            s.write(text)
            s.flush()

    def flush(self):
        pass


def log_to_file(path):
    """Everything the agent says goes to logs/workspace.log — and to the screen too, when there is one."""
    if os.path.exists(path) and os.path.getsize(path) > 5 * 2 ** 20:
        os.replace(path, path + ".old")
    f = open(path, "a", encoding="utf-8")
    screen = sys.stderr if sys.stderr is not None and sys.stderr.isatty() else None
    sys.stderr = Tee(f, screen)


def background_command(p):
    """How the computer starts it: no window (pythonw on Windows)."""
    python = sys.executable
    if IS_WINDOWS:
        quiet = os.path.join(os.path.dirname(python), "pythonw.exe")
        python = quiet if os.path.exists(quiet) else python
    return [python, os.path.abspath(__file__), "run", "--dir", p["dir"]]


def plist_path():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", MAC_LABEL + ".plist")


def install_autostart(p):
    cmd = background_command(p)
    if IS_WINDOWS:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
    elif IS_MAC:
        import plistlib

        os.makedirs(os.path.dirname(plist_path()), exist_ok=True)
        os.makedirs(p["logs"], exist_ok=True)
        with open(plist_path(), "wb") as f:
            plistlib.dump({"Label": MAC_LABEL, "ProgramArguments": cmd, "RunAtLoad": True, "KeepAlive": True,
                           "ThrottleInterval": 30, "EnvironmentVariables": {"PATH": MAC_PATH},
                           "StandardOutPath": os.path.join(p["logs"], "launchd.log"),
                           "StandardErrorPath": os.path.join(p["logs"], "launchd.log")}, f)
    else:
        raise SystemExit("Starting with the computer is set up for Windows and Mac; on Linux use the server set-up.")


def uninstall_autostart():
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, STARTUP_NAME)
        except FileNotFoundError:
            pass
    elif IS_MAC and os.path.exists(plist_path()):
        os.remove(plist_path())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="computer.py", description="Swangz company browsers on this computer")
    parser.add_argument("command", choices=("setup", "run", "start", "stop", "status", "remove"))
    parser.add_argument("--host", choices=("windows", "mac"), help="which computer this is in the console")
    parser.add_argument("--gateway", help="the address people open Swangz AI at, e.g. https://swangz-ai.netlify.app")
    parser.add_argument("--key", help="this computer's key, from the console")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"where its files live (default {DEFAULT_DIR})")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 9):
        raise SystemExit("Python 3.9 or newer is needed.")
    return {"setup": setup, "run": run, "start": start, "stop": stop, "status": status, "remove": remove}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
