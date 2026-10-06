import json
import re
from subprocess import CompletedProcess

import pytest

import converter


@pytest.mark.parametrize('mismatch', [False, True])
def test_pipeline_uses_corrected_source_and_retains_formula_report(monkeypatch, tmp_path, mismatch):
    source = tmp_path / 'source.tex'
    source.write_text(r'\documentclass{article}\begin{document}$x^2$\end{document}', encoding='utf-8')
    output = source.with_suffix('.html')
    output.write_text('previous', encoding='utf-8')
    monkeypatch.setattr(converter, 'validate_latex_document', lambda *a, **k: [])
    monkeypatch.setattr(converter, 'find_make4ht', lambda _: 'make4ht.exe')

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        # A compatibility rewrite must not become the reference for verification.
        tex_file.write_text('$x^9$', encoding='utf-8')
        exponent = '3' if mismatch else '2'
        (build_dir / 'source.html').write_text(
            '<html><body><math><msup><mi>x</mi><mn>' + exponent + '</mn></msup></math></body></html>',
            encoding='utf-8',
        )
        return CompletedProcess([], 0, '', '')

    monkeypatch.setattr(converter, 'run_make4ht', fake_run)
    if mismatch:
        with pytest.raises(converter.ConversionError, match='Formula verification failed'):
            converter.convert_tex_to_accessible_html(source, keep_logs=True)
        assert output.read_text(encoding='utf-8') == 'previous'
    else:
        converter.convert_tex_to_accessible_html(source, keep_logs=True)
        html = output.read_text(encoding='utf-8')
        assert 'data-tex-formula-id="formula-1"' in html
        embedded = re.search(r'id="tex-formula-verification">(.*?)</script>', html)[1]
        assert json.loads(embedded)['status'] == 'confirmed'
    report_path = next(converter.logs_directory_for(output).glob('*/formula-verification.json'))
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['status'] == ('mismatch' if mismatch else 'confirmed')
    assert report['formulas'][0]['tex'] == 'x^2'
