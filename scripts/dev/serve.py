"""Run owned local dev processes together; stop both on interrupt or child failure."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dev", "backend", "frontend"))
    mode = parser.parse_args().mode
    root = Path(__file__).resolve().parents[2]
    backend_port = int(os.environ.get("E_AGENT_DEV_BACKEND_PORT", "8787"))
    frontend_port = int(os.environ.get("E_AGENT_DEV_FRONTEND_PORT", "5173"))
    if not all(1 <= port <= 65535 for port in (backend_port, frontend_port)):
        parser.error("ports must be between 1 and 65535")
    if backend_port == frontend_port:
        parser.error("backend and frontend require different ports")
    backend = ["uv", "run", "e-agent"]
    if profile := os.environ.get("E_AGENT_DEV_PROFILE"):
        backend += ["--profile", profile]
    backend += [
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(backend_port),
        "--static",
        "ui/dist/web",
    ]
    frontend = [
        "pnpm",
        "--dir",
        "ui",
        "dev",
        "--host",
        "127.0.0.1",
        "--port",
        str(frontend_port),
        "--strictPort",
    ]
    commands = {"backend": backend, "frontend": frontend}
    selected = commands if mode == "dev" else {mode: commands[mode]}
    env = {**os.environ, "E_AGENT_DEV_API_URL": f"http://127.0.0.1:{backend_port}"}
    children: list[tuple[str, subprocess.Popen[bytes]]] = []

    def interrupt(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        for name, command in selected.items():
            port = backend_port if name == "backend" else frontend_port
            print(f"Starting {name}: http://127.0.0.1:{port}", flush=True)
            children.append(
                (name, subprocess.Popen(command, cwd=root, env=env, start_new_session=True))
            )
        print("Ctrl+C stops the processes started by this command.", flush=True)
        while True:
            for name, process in children:
                if (code := process.poll()) is not None:
                    print(f"{name} exited ({code}); stopping this dev session.", file=sys.stderr)
                    return code if code >= 0 else 128 - code
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        for _, process in children:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        for _, process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
