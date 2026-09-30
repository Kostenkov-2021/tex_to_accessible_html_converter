import os
import sys

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
