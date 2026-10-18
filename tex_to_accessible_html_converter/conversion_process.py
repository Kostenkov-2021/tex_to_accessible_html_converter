"""Bounded execution of TeX tools with persistent diagnostic output."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
from pathlib import Path


class ProcessTimeout(RuntimeError):
    """Report that a TeX process exceeded its configured deadline."""


def run_logged_process(
    command: list[str], *, cwd: Path, env: dict[str, str], log_dir: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Keep logs on disk and terminate descendants when the deadline expires."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("The timeout must be greater than zero.")
    if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
        # System TeX tools must not load the frozen application's libraries.
        # Keep the caller's environment intact (the GUI also uses it).
        env = env.copy()
        original_library_path = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original_library_path is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original_library_path
    stdout_path = log_dir / "stdout.txt"
    stderr_path = log_dir / "stderr.txt"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
        )
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            if os.name != "nt":
                # Kill the group even if its leader exited after wait timed out:
                # make4ht's TeX children can still be running in that group.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=20)
                (log_dir / "termination.txt").write_text(
                    "Sent SIGKILL to the isolated process group.\n", encoding="utf-8"
                )
                raise ProcessTimeout(
                    f"The conversion timed out after {timeout:g} seconds. "
                    "The processes were stopped."
                ) from error
            stopped = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=20,
                check=False,
            )
            (log_dir / "termination.txt").write_bytes(stopped.stdout + stopped.stderr)
            if stopped.returncode and process.poll() is None:
                raise ProcessTimeout(
                    f"The conversion timed out after {timeout:g} seconds. "
                    f"Windows could not stop process {process.pid}. "
                    f"Diagnostics: {log_dir}"
                ) from error
            process.wait(timeout=20)
            raise ProcessTimeout(
                f"The conversion timed out after {timeout:g} seconds. "
                "The processes were stopped."
            ) from error
    return subprocess.CompletedProcess(
        command,
        code,
        stdout_path.read_text(encoding="utf-8", errors="replace"),
        stderr_path.read_text(encoding="utf-8", errors="replace"),
    )
