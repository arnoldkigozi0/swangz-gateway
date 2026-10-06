"""A stand-in for the docker CLI the Workspace Agent drives.

`run` reads the env file the agent wrote — the browser's new API token — and gives it to that browser's
stand-in Neko, which starts empty (a fresh container) and fails its health check `boot` times while it
"starts". `rm` empties it again. `down` makes every command fail, like a stopped Docker daemon.
"""

from workspace_agent.agent import DockerError


class FakeDocker:
    def __init__(self, nekos, boot=0):
        self.nekos = nekos  # browser slot -> FakeNeko
        self.boot = boot
        self.containers = {}  # name -> {"args": [...], "env": {...}}
        self.log = []  # (command, container name), in order
        self.down = False

    def _check(self):
        if self.down:
            raise DockerError("Cannot connect to the Docker daemon")

    def _neko(self, name):
        return self.nekos[name[len("swangz-ws-"):]]

    def ok(self):
        return not self.down

    def image_present(self, image):
        return True

    def info(self):
        return {"memory_gb": 31.2, "cpus": 16}

    def running(self, name):
        self._check()
        return name in self.containers

    def remove(self, name):
        self._check()
        self.log.append(("rm", name))
        if self.containers.pop(name, None) is not None:
            self._neko(name).reset()

    def run(self, name, args):
        self._check()
        self.log.append(("run", name))
        with open(args[args.index("--env-file") + 1], encoding="utf-8") as f:
            env = dict(line.split("=", 1) for line in f.read().splitlines() if line)
        self.containers[name] = {"args": args, "env": env}
        neko = self._neko(name)
        neko.reset()
        neko.token = env["NEKO_SESSION_API_TOKEN"]
        neko.booting = self.boot
