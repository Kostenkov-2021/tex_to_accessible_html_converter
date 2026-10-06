from subprocess import CompletedProcess

import pytest

import converter
import latex_validation


@pytest.mark.parametrize("returncode, log, failed", [
    (0, "normal log", False), (0, "! Undefined control sequence.\n", True),
    (1, "normal log", True), (0, None, True),
])
def test_native_validation_checks_exit_and_log(monkeypatch, tmp_path, returncode, log, failed):
    (tmp_path / "latex.exe").touch()
    source = tmp_path / "document.tex"
    source.write_text("text", encoding="utf-8")

    def fake_run(command, **kwargs):
        assert command[0] == str(tmp_path / "latex.exe")
        assert "-halt-on-error" in command
        assert kwargs["cwd"] == tmp_path
        if log is not None:
            (kwargs["log_dir"] / "document.log").write_text(log, encoding="utf-8")
        return CompletedProcess(command, returncode, "out", "err")

    monkeypatch.setattr(latex_validation, "run_logged_process", fake_run)
    errors = latex_validation.validate_latex_document(
        source, engine="latex", make4ht=str(tmp_path / "make4ht.exe"),
        log_dir=tmp_path / "logs", timeout=10,
    )
    assert bool(errors) == failed


def test_repairs_separate_copy_and_revalidates(monkeypatch, tmp_path):
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    source = original_dir / "document.tex"
    original = r'$a \), \( b$'
    source.write_text(original, encoding="utf-8")
    diagnostics = tmp_path / "logs"
    diagnostics.mkdir()
    calls = []

    def validate(path, **kwargs):
        calls.append(path)
        return ["! Bad delimiter"] if len(calls) == 1 else []

    monkeypatch.setattr(converter, "find_make4ht", lambda _: "make4ht.exe")
    monkeypatch.setattr(converter, "validate_latex_document", validate)
    converter.prepare_validated_source(source, tmp_path / "corrected", diagnostics,
                                       "latex", "auto", 10)
    assert calls == [source, tmp_path / "corrected/document.tex"]
    assert source.read_text(encoding="utf-8") == original
    assert calls[-1].read_text(encoding="utf-8") == r'$a $, $ b$'
    assert (diagnostics / "source.original.tex").read_text(encoding="utf-8") == original


def test_unresolved_tex_errors_stop_before_conversion(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("\\bad", encoding="utf-8")
    output = source.with_suffix(".html")
    output.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(converter, "find_make4ht", lambda _: "make4ht.exe")
    monkeypatch.setattr(converter, "validate_latex_document", lambda *a, **k: ["! Undefined control sequence."])

    def unexpected(*args, **kwargs):
        pytest.fail("make4ht must not run after failed validation")

    monkeypatch.setattr(converter, "run_make4ht", unexpected)
    with pytest.raises(converter.ConversionError, match="Unresolved TeX"):
        converter.convert_tex_to_accessible_html(source)
    assert output.read_text(encoding="utf-8") == "previous"


def test_unchanged_source_does_not_repeat_native_compilation(monkeypatch, tmp_path):
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    source = original_dir / "document.tex"
    original = b"text\r\n"
    source.write_bytes(original)
    diagnostics = tmp_path / "logs"
    diagnostics.mkdir()
    calls = []

    def validate(path, **kwargs):
        calls.append(path)
        return []

    monkeypatch.setattr(converter, "find_make4ht", lambda _: "make4ht.exe")
    monkeypatch.setattr(converter, "validate_latex_document", validate)
    converter.prepare_validated_source(source, tmp_path / "corrected", diagnostics,
                                       "latex", "auto", 10)
    assert calls == [source]
    assert (tmp_path / "corrected/document.tex").read_bytes() == original
