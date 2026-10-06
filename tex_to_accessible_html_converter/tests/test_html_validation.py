import pytest

from html_validation import validate_html_structure


@pytest.mark.parametrize("text", [
    '<html><body><p>one<p>two<br><div>ok</div></body></html>',
    '<table><tr><td>one<td>two</table>',
    '<script>const x = "<div>";</script><!-- <span> -->',
    '<math><mtext><span>text</span></mtext><mspace /></math>',
])
def test_accepts_optional_tags_literals_and_foreign_content(text):
    assert validate_html_structure(text) == []


@pytest.mark.parametrize("text", [
    '<div><span>x</div></span>', '<main>unfinished',
    '<div id="x"></div><span id="x"></span>',
    '<div class="one" class="two"></div>',
    '<math xmlns="incorrect"><mi>x</mi></math>',
])
def test_reports_targeted_errors(text):
    assert validate_html_structure(text)
