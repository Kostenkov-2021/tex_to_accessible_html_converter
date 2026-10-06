"""GNU gettext localization with English source strings."""

from __future__ import annotations

import gettext
import json
import locale
import os
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = ("en", "ru")
DOMAIN = "tex_to_accessible_html"
LOCALE_DIR = Path(__file__).with_name("locales")


def settings_path() -> Path:
    """Return the per-user settings file without depending on wxPython."""
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "TeXToAccessibleHTML" / "settings.json"


def saved_language() -> str | None:
    """Return the saved supported language, or ``None`` when unavailable."""
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8")).get(
            "language", ""
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return value if value in SUPPORTED_LANGUAGES else None


def save_language(language: str) -> None:
    """Persist a supported interface language for future launches.

    Raise ``ValueError`` when ``language`` is not supported.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": language}, indent=2), encoding="utf-8")


BACKEND_MESSAGE_FRAGMENTS = (
    "TeX Live make4ht was not found. Install TeX Live with TeX4ht support and add its bin directory to PATH.",
    "make4ht was not found. Install MiKTeX with the make4ht and TeX4ht packages.",
    "make4ht was not found. Install TeX Live or MiKTeX with TeX4ht support.",
    "The timeout must be a positive finite number.",
    "The timeout must be greater than zero.",
    "TeX errors occurred while creating HTML:",
    "make4ht did not create the expected file:",
    "The MathML structure is invalid:",
    "The HTML structure is invalid:",
    "The output file must differ from the TeX source file.",
    "Unresolved TeX source errors:",
    "The build source directory must not contain the original TeX file.",
    "LaTeX validation engine was not found:",
    "Formula verification failed:",
    "The conversion timed out after",
    "Windows could not stop process",
    "The processes were stopped.",
    "The source file does not exist:",
    "Unknown TeX distribution:",
    "Unknown TeX engine:",
    "Diagnostics saved to:",
    "Temporary files saved to:",
    "Could not copy logs:",
    "Could not copy temporary files:",
    "Build directory:",
    "Program output:",
    "Error output:",
    "Diagnostics:",
    "make4ht failed.",
    "seconds.",
)


def detect_language() -> str:
    """Return an explicitly selected or system language."""
    requested = os.environ.get("TEX_ACCESSIBLE_HTML_LANGUAGE", "").lower()
    if requested[:2] in SUPPORTED_LANGUAGES:
        return requested[:2]
    preferred = saved_language()
    if preferred:
        return preferred
    system_locale = locale.getlocale()[0] or ""
    return "ru" if system_locale.lower().startswith("ru") else "en"


class Translator:
    """Translate interface strings and completed backend messages."""

    def __init__(self, language: str | None = None) -> None:
        """Initialize the translator with an explicit or detected language."""
        self.set_language(language or detect_language())

    def set_language(self, language: str, *, persist: bool = False) -> None:
        """Select a supported language and optionally persist the selection.

        Raise ``ValueError`` when ``language`` is not supported.
        """
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language
        self.catalog = gettext.translation(
            DOMAIN,
            localedir=LOCALE_DIR,
            languages=[self.language],
            fallback=True,
        )
        if persist:
            save_language(language)

    def __call__(self, source: str, **values: Any) -> str:
        """Translate ``source`` and interpolate the supplied named values."""
        return self.catalog.gettext(source).format(**values)

    def text(self, message: str) -> str:
        """Translate known fragments in a completed backend message."""
        for source in sorted(BACKEND_MESSAGE_FRAGMENTS, key=len, reverse=True):
            message = message.replace(source, self.catalog.gettext(source))
        return message


translate = Translator()
localize_text = translate.text
