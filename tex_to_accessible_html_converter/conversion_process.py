"""Bounded execution of TeX tools with persistent diagnostic output."""

from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path


class ProcessTimeout(RuntimeError):
    """Report that a TeX process exceeded its configured deadline."""


def run_logged_process(
    command: list[str], *, cwd: Path, env: dict[str, str], log_dir: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Keep logs on disk and terminate descendants when the deadline expires."""
    if os.name != "nt":
        raise OSError("TeX to Accessible HTML Converter supports Windows only.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("The timeout must be greater than zero.")
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
        )
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
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
