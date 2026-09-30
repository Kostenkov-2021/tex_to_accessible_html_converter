import tex_to_accessible_html_cli as cli


def test_collect_tex_files_handles_folders_recursion_and_duplicates(tmp_path):
    first = tmp_path / "a.tex"
    first.write_text("", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    second = nested / "b.TEX"
    second.write_text("", encoding="utf-8")

    assert cli.collect_tex_files([str(tmp_path), str(first)]) == [first]
    assert cli.collect_tex_files([str(tmp_path)], recursive=True) == [first, second]


def test_main_converts_folder_and_passes_retention(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.tex"
    source.write_text("", encoding="utf-8")
    output_dir = tmp_path / "output"
    calls = []

    def fake_convert(**kwargs):
        calls.append(kwargs)
        return kwargs["output_file"]

    monkeypatch.setattr(cli, "convert_tex_to_accessible_html", fake_convert)
    result = cli.main([str(tmp_path), "-o", str(output_dir), "--keep", "all"])

    assert result == 0
    assert calls[0]["output_file"] == output_dir / "source.html"
    assert calls[0]["keep_logs"] is True
    assert calls[0]["keep_temporary_files"] is True
    assert str(output_dir / "source.html") in capsys.readouterr().out


def test_main_returns_two_when_no_tex_files(tmp_path, capsys):
    assert cli.main([str(tmp_path)]) == 2
    assert "No .tex files" in capsys.readouterr().err
