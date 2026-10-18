import os
import sys
import time

import pytest

from conversion_process import ProcessTimeout, run_logged_process


def test_process_preserves_stdout_stderr_and_exit_code(tmp_path):
    result = run_logged_process(
        [
            sys.executable,
            "-c",
            "import sys; print('output'); print('error', file=sys.stderr); sys.exit(3)",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        log_dir=tmp_path,
        timeout=10,
    )
    assert result.returncode == 3
    assert result.stdout.strip() == "output"
    assert result.stderr.strip() == "error"
    assert (tmp_path / "stdout.txt").read_text().strip() == "output"


def test_timeout_reports_failure_and_preserves_partial_log(tmp_path):
    # Restricted Windows environments may deny taskkill. Both the successful
    # termination and explicit diagnostic branches are valid outcomes.
    with pytest.raises(ProcessTimeout, match="timed out"):
        run_logged_process(
            [
                sys.executable,
                "-u",
                "-c",
                "import time; print('started'); time.sleep(60)",
            ],
            cwd=tmp_path,
            env=os.environ.copy(),
            log_dir=tmp_path,
            timeout=1,
        )
    assert (tmp_path / "stdout.txt").read_text().strip() == "started"


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_timeout_stops_descendants_that_ignore_sigterm(tmp_path):
    marker = tmp_path / "child-survived"
    child = (
        "import signal,time,pathlib; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"time.sleep(3); pathlib.Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "print('child started', flush=True); time.sleep(60)"
    )
    with pytest.raises(ProcessTimeout, match="timed out"):
        run_logged_process(
            [sys.executable, "-c", parent], cwd=tmp_path,
            env=os.environ.copy(), log_dir=tmp_path, timeout=1,
        )
    assert "child started" in (tmp_path / "stdout.txt").read_text()
    time.sleep(3)
    assert not marker.exists(), "A descendant survived the conversion timeout"
    assert "SIGKILL" in (tmp_path / "termination.txt").read_text()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_does_not_launch_process(tmp_path, timeout):
    with pytest.raises(ValueError):
        run_logged_process(
            ["nonexistent-command"], cwd=tmp_path, env={},
            log_dir=tmp_path, timeout=timeout,
        )
    assert not (tmp_path / "stdout.txt").exists()


@pytest.mark.parametrize("original", [None, "", "/system/custom-libs"])
def test_frozen_linux_restores_library_path_for_tex_only(monkeypatch, tmp_path, original):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = "/bundled/libs"
    env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is not None:
        env["LD_LIBRARY_PATH_ORIG"] = original
    before = env.copy()
    result = run_logged_process(
        [sys.executable, "-c", "import os; print(repr(os.environ.get('LD_LIBRARY_PATH')))"],
        cwd=tmp_path, env=env, log_dir=tmp_path, timeout=10,
    )
    assert result.stdout.strip() == repr(original)
    assert env == before
