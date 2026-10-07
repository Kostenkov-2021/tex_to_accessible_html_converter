from link_validation import repair_self_links, validate_links


def test_self_link_survives_output_rename_without_changing_external_links(tmp_path):
    html = '<a href="source.html#eq%201">Eq</a><i id="eq 1"></i><a href="https://example.org/source.html#eq%201">External</a>'
    fixed, repairs = repair_self_links(html, 'source.html')
    assert 'href="#eq%201"' in fixed
    assert 'href="https://example.org/source.html#eq%201"' in fixed
    assert len(repairs) == 1
    assert validate_links(fixed, tmp_path / 'renamed.html')['errors'] == []
    assert repair_self_links(fixed, 'source.html') == (fixed, [])


def test_fragment_ids_are_decoded_once_and_case_sensitive(tmp_path):
    html = '<i id="A B"></i><i id="A%20B"></i><a href="#A%20B">One</a><a href="#A%2520B">Two</a><a href="#a%20B">Bad</a>'
    report = validate_links(html, tmp_path / 'doc.html')
    assert [link['status'] for link in report['links']] == ['confirmed', 'confirmed', 'broken']


def test_cross_document_links_check_file_and_fragment(tmp_path):
    (tmp_path / 'other.html').write_text('<a name="legacy"></a>', encoding='utf-8')
    html = '<a href="other.html#legacy">Good</a><a href="other.html#wrong">Bad</a><a href="missing.html">Missing</a>'
    report = validate_links(html, tmp_path / 'main.html')
    assert [link['status'] for link in report['links']] == ['confirmed', 'broken', 'broken']


def test_base_url_is_respected_and_not_repaired(tmp_path):
    html = '<base href="https://example.org/"><a href="source.html#x">External</a><i id="x"></i>'
    assert repair_self_links(html, 'source.html') == (html, [])
    report = validate_links(html, tmp_path / 'source.html')
    assert report['links'][0]['status'] == 'external_not_checked'


def test_empty_href_and_first_empty_base_follow_document_url(tmp_path):
    html = '<base href><base href="https://example.org/"><a href>Top</a><a href="#x">Target</a><i id="x"></i>'
    report = validate_links(html, tmp_path / 'doc.html')
    assert [link['status'] for link in report['links']] == ['confirmed', 'confirmed']


def test_uncertain_self_link_is_not_guessed():
    html = '<a href="source.html#missing">Missing</a><a href="source.html?q=1#x">Query</a><a href="other/source.html#x">Other</a><i id="x"></i>'
    assert repair_self_links(html, 'source.html') == (html, [])


def test_multiple_repairs_preserve_other_attributes_and_newlines():
    html = '<i id="x"></i>\n<a data-href="source.html#other" href="source.html#x">One</a>\n<a href=source.html#x>Two</a>'
    fixed, repairs = repair_self_links(html, 'source.html')
    assert fixed == '<i id="x"></i>\n<a data-href="source.html#other" href="#x">One</a>\n<a href=#x>Two</a>'
    assert len(repairs) == 2


def test_auxiliary_label_targets_are_checked_without_executing_tex(tmp_path):
    aux = tmp_path / 'doc.aux'
    aux.write_text(r'\newlabel{eq:test}{{\rEfLiNK{x1}{2.1}}{\rEfLiNK{x1}{3}}}' + '\n' + r'\newlabel{eq:bad}{{\rEfLiNK{missing}{2.2}}}', encoding='utf-8')
    report = validate_links('<i id="x1"></i><a href="#x1">2.1</a>', tmp_path / 'doc.html', aux)
    assert report['labels'] == [{'label': 'eq:test', 'fragment': 'x1', 'status': 'confirmed'},
                                {'label': 'eq:bad', 'fragment': 'missing', 'status': 'missing_target'}]


def test_unresolved_tex_reference_is_reported_even_when_no_link_was_generated(tmp_path):
    aux = tmp_path / 'doc.aux'
    aux.write_text(r'\newlabel{eq:good}{{\rEfLiNK{x1}{1}}}', encoding='utf-8')
    source = r'\newcommand{\eq}[1]{(\ref{#1})}' + '\n' + r'\eq{eq:good} \ref{missing}' + '\n' + r'% \ref{ignored}'
    report = validate_links('<i id="x1"></i>', tmp_path / 'doc.html', aux, source)
    assert [ref['status'] for ref in report['references']] == ['label_target_confirmed', 'undefined_label']
    assert report['status'] == 'failed'


def test_unrecognized_auxiliary_reference_shape_is_not_guessed(tmp_path):
    aux = tmp_path / 'doc.aux'
    aux.write_text(r'\newlabel{eq:test}{{1}{2}}', encoding='utf-8')
    report = validate_links('', tmp_path / 'doc.html', aux, r'\ref{eq:test}')
    assert report['references'][0]['status'] == 'mapping_not_supported'
    assert not report['errors']
