import gettext
import json
from pathlib import Path

import localization
from localization import DOMAIN, Translator


def test_english_is_the_fallback_source_language():
    translator = Translator("en")

    assert translator("Convert") == "Convert"
    assert (
        translator("Processed: {current} of {total}", current=2, total=3)
        == "Processed: 2 of 3"
    )


def test_russian_catalog_translates_interface_and_backend_messages():
    translator = Translator("ru")

    assert translator("Convert") == "Конвертировать"
    assert (
        translator("Processed: {current} of {total}", current=2, total=3)
        == "Обработано: 2 из 3"
    )
    assert (
        translator.text("The source file does not exist: example.tex")
        == "Исходный файл не существует: example.tex"
    )


def test_russian_gettext_catalog_can_be_loaded():
    locale_dir = Path(__file__).with_name("locales")
    catalog = gettext.translation(DOMAIN, localedir=locale_dir, languages=["ru"])

    assert catalog.gettext("Convert") == "Конвертировать"


def test_saved_language_is_used_and_can_be_changed(monkeypatch, tmp_path):
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(localization, "settings_path", lambda: settings)
    monkeypatch.delenv("TEX_ACCESSIBLE_HTML_LANGUAGE", raising=False)

    localization.save_language("ru")
    assert json.loads(settings.read_text(encoding="utf-8")) == {"language": "ru"}
    assert localization.detect_language() == "ru"

    translator = Translator("en")
    translator.set_language("ru", persist=True)
    assert translator.language == "ru"
    assert translator("Language:") == "Язык:"
