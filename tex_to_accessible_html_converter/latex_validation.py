"""Validate a staged LaTeX document with the selected distribution's engine."""

import os
import re
from pathlib import Path

from conversion_process import run_logged_process


def validate_latex_document(
    tex_file: Path, *, engine: str, make4ht: str, log_dir: Path, timeout: float
) -> list[str]:
    """Compile without TeX4ht adaptations, keeping diagnostic files isolated."""
    log_dir.mkdir(parents=True, exist_ok=True)
    executable = Path(make4ht).parent / f"{engine}.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"LaTeX validation engine was not found: {executable}")
    env = os.environ.copy()
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    result = run_logged_process(
        [str(executable), "-interaction=nonstopmode", "-halt-on-error",
         f"-output-directory={log_dir}", tex_file.name],
        cwd=tex_file.parent, env=env, log_dir=log_dir, timeout=timeout,
    )
    log = log_dir / f"{tex_file.stem}.log"
    errors = re.findall(
        r"^!.*$", log.read_text(encoding="utf-8", errors="replace"), re.MULTILINE
    ) if log.is_file() else []
    if result.returncode and not errors:
        errors.append(f"LaTeX validation failed (exit code {result.returncode}):\n"
                      + result.stdout[-4000:] + result.stderr[-4000:])
    if not log.is_file() and not errors:
        errors.append("LaTeX validation did not produce a log file.")
    return errors
