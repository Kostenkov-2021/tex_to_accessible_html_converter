from __future__ import annotations

import importlib
import queue
import sys
from pathlib import Path
from types import ModuleType

import pytest


class FakeChoice:
    def __init__(self, selection: int) -> None:
        self.selection = selection

    def GetSelection(self) -> int:
        return self.selection


class FakeControl:
    def __init__(self) -> None:
        self.name = ""
        self.tooltip = ""
        self.help_text = ""
        self.enabled_values: list[bool] = []
        self.range_values: list[int] = []
        self.values: list[int] = []
        self.visible_values: list[bool] = []
        self.text = ""
        self.parent = None

    def SetName(self, name: str) -> None:
        self.name = name

    def SetToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def SetHelpText(self, help_text: str) -> None:
        self.help_text = help_text

    def Enable(self, enabled: bool) -> None:
        self.enabled_values.append(enabled)

    def Show(self, visible: bool) -> None:
        self.visible_values.append(visible)

    def GetParent(self):
        return self.parent

    def SetRange(self, value: int) -> None:
        self.range_values.append(value)

    def SetValue(self, value: int) -> None:
        self.values.append(value)

    def AppendText(self, text: str) -> None:
        self.text += text


class FakeRadio:
    def __init__(self, value: bool = False) -> None:
        self.value = value
        self.enabled_values: list[bool] = []

    def GetValue(self) -> bool:
        return self.value

    def SetValue(self, value: bool) -> None:
        self.value = value

    def Enable(self, enabled: bool) -> None:
        self.enabled_values.append(enabled)


class FakeParent:
    def __init__(self) -> None:
        self.layout_calls = 0

    def Layout(self) -> None:
        self.layout_calls += 1


class FakeKeyEvent:
    def __init__(self, key_code: int, unicode_key: int = 0) -> None:
        self.key_code = key_code
        self.unicode_key = unicode_key
        self.skipped = False

    def GetKeyCode(self) -> int:
        return self.key_code

    def GetUnicodeKey(self) -> int:
        return self.unicode_key

    def Skip(self) -> None:
        self.skipped = True


@pytest.fixture
def gui_module(monkeypatch):
    monkeypatch.setenv("TEX_ACCESSIBLE_HTML_LANGUAGE", "ru")
    fake_wx = ModuleType("wx")
    fake_wx.NOT_FOUND = -1
    fake_wx.Frame = type("Frame", (), {})
    fake_wx.App = type("App", (), {})
    fake_wx.Window = object
    fake_wx.Choice = object
    fake_wx.CommandEvent = object
    fake_wx.ID_OK = 1
    fake_wx.OK = 1
    fake_wx.ICON_WARNING = 2
    fake_wx.WXK_F1 = 112
    monkeypatch.setitem(sys.modules, "wx", fake_wx)
    sys.modules.pop("localization", None)
    sys.modules.pop("tex_to_accessible_html_gui", None)
    module = importlib.import_module("tex_to_accessible_html_gui")
    yield module
    sys.modules.pop("tex_to_accessible_html_gui", None)
    sys.modules.pop("localization", None)


def test_selected_value_returns_internal_value(gui_module):
    choice = FakeChoice(1)

    result = gui_module.selected_value(
        choice, [("Обычный", "default"), ("Быстрый", "draft")]
    )

    assert result == "draft"


def test_selected_value_falls_back_to_first_value(gui_module):
    choice = FakeChoice(gui_module.wx.NOT_FOUND)

    result = gui_module.selected_value(
        choice, [("Обычный", "default"), ("Быстрый", "draft")]
    )

    assert result == "default"


def test_documentation_path_selects_bundled_language_file(gui_module, tmp_path):
    executable = tmp_path / "app" / "TeXToAccessibleHTML.exe"
    docs = executable.parent / "docs"
    docs.mkdir(parents=True)
    english = docs / "README.html"
    russian = docs / "README_RU.html"
    english.write_text("English", encoding="utf-8")
    russian.write_text("Русский", encoding="utf-8")

    assert gui_module.documentation_path("en", executable=executable) == english
    assert gui_module.documentation_path("ru", executable=executable) == russian


def test_f1_opens_documentation_and_other_keys_continue(gui_module):
    frame = object.__new__(gui_module.ConverterFrame)
    calls = []
    frame.on_open_documentation = lambda _event=None: calls.append("open")
    f1 = FakeKeyEvent(gui_module.wx.WXK_F1)
    other = FakeKeyEvent(65, ord("A"))

    gui_module.ConverterFrame.on_help_key(frame, f1)
    gui_module.ConverterFrame.on_help_key(frame, other)

    assert calls == ["open"]
    assert not f1.skipped
    assert other.skipped


def test_set_accessible_text_sets_name_and_tooltip(gui_module):
    control = FakeControl()

    gui_module.set_accessible_text(
        control, "Журнал конвертации", "Сообщения о ходе работы"
    )

    assert control.name == "Журнал конвертации"
    assert control.tooltip == "Сообщения о ходе работы"
    assert control.help_text == "Сообщения о ходе работы"


def test_set_accessible_text_uses_name_as_default_tooltip(gui_module):
    control = FakeControl()

    gui_module.set_accessible_text(control, "Список файлов")

    assert control.name == "Список файлов"
    assert control.tooltip == "Список файлов"
    assert control.help_text == "Список файлов"


def test_update_folder_controls_visibility_follows_custom_folder_radio(gui_module):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.folder_text = FakeControl()
    frame.folder_button = FakeControl()
    frame.custom_folder_radio = FakeRadio(False)
    parent = FakeParent()
    frame.folder_text.parent = parent
    frame_layout_calls = []
    frame.Layout = lambda: frame_layout_calls.append(True)

    gui_module.ConverterFrame.update_folder_controls_visibility(frame)
    frame.custom_folder_radio.SetValue(True)
    gui_module.ConverterFrame.update_folder_controls_visibility(frame)

    assert frame.folder_text.visible_values == [False, True]
    assert frame.folder_button.visible_values == [False, True]
    assert parent.layout_calls == 2
    assert frame_layout_calls == [True, True]


def test_file_list_key_down_allows_only_vertical_navigation(gui_module):
    gui_module.wx.WXK_UP = 1
    gui_module.wx.WXK_DOWN = 2
    gui_module.wx.WXK_TAB = 3
    gui_module.wx.WXK_HOME = 4

    up_event = FakeKeyEvent(gui_module.wx.WXK_UP)
    home_event = FakeKeyEvent(gui_module.wx.WXK_HOME)
    letter_event = FakeKeyEvent(ord("A"), ord("A"))

    gui_module.ConverterFrame.on_file_list_key_down(
        object.__new__(gui_module.ConverterFrame), up_event
    )
    gui_module.ConverterFrame.on_file_list_key_down(
        object.__new__(gui_module.ConverterFrame), home_event
    )
    gui_module.ConverterFrame.on_file_list_key_down(
        object.__new__(gui_module.ConverterFrame), letter_event
    )

    assert up_event.skipped is True
    assert home_event.skipped is False
    assert letter_event.skipped is False


def test_convert_files_pushes_success_and_done_messages(
    gui_module, monkeypatch, tmp_path
):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.results = queue.Queue()
    tex_file = tmp_path / "source.tex"
    output_dir = tmp_path / "html"

    def fake_convert_tex_to_accessible_html(
        tex_file,
        output_file,
        engine,
        mode,
        tex_distribution,
        timeout,
        keep_logs,
        keep_temporary_files,
    ):
        assert output_file == output_dir / "source.html"
        assert engine == "lualatex"
        assert mode == "draft"
        assert tex_distribution == "miktex"
        assert timeout == 300
        assert keep_logs is False
        assert keep_temporary_files is False
        return output_file

    monkeypatch.setattr(
        gui_module,
        "convert_tex_to_accessible_html",
        fake_convert_tex_to_accessible_html,
    )

    gui_module.ConverterFrame.convert_files(
        frame, [tex_file], output_dir, "lualatex", "draft", "miktex"
    )

    assert frame.results.get_nowait() == ("start", "1")
    assert frame.results.get_nowait()[0] == "progress"
    assert frame.results.get_nowait() == ("ok", str(output_dir / "source.html"))
    assert frame.results.get_nowait()[0] == "progress"
    assert frame.results.get_nowait() == ("done", "1|0|1")


def test_convert_files_pushes_error_and_done_messages(
    gui_module, monkeypatch, tmp_path
):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.results = queue.Queue()
    tex_file = tmp_path / "source.tex"

    def fake_convert_tex_to_accessible_html(**_kwargs):
        raise gui_module.ConversionError("failed")

    monkeypatch.setattr(
        gui_module,
        "convert_tex_to_accessible_html",
        fake_convert_tex_to_accessible_html,
    )

    gui_module.ConverterFrame.convert_files(
        frame, [tex_file], None, "lualatex", "draft"
    )

    assert frame.results.get_nowait() == ("start", "1")
    assert frame.results.get_nowait()[0] == "progress"
    kind, message = frame.results.get_nowait()
    assert kind == "error"
    assert str(tex_file) in message
    assert "failed" in message
    assert frame.results.get_nowait()[0] == "progress"
    assert frame.results.get_nowait() == ("done", "0|1|1")


def test_set_busy_disables_and_enables_interactive_controls(gui_module):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.convert_button = FakeControl()
    frame.add_button = FakeControl()
    frame.remove_button = FakeControl()
    frame.clear_button = FakeControl()
    frame.folder_button = FakeControl()
    frame.folder_text = FakeControl()
    frame.tex_distribution_choice = FakeControl()
    frame.engine_choice = FakeControl()
    frame.mode_choice = FakeControl()
    frame.timeout_input = FakeControl()
    statuses = []
    frame.SetStatusText = statuses.append

    gui_module.ConverterFrame.set_busy(frame, True)
    gui_module.ConverterFrame.set_busy(frame, False)

    assert frame.convert_button.enabled_values == [False, True]
    assert frame.add_button.enabled_values == [False, True]
    assert frame.remove_button.enabled_values == [False, True]
    assert frame.clear_button.enabled_values == [False, True]
    assert frame.tex_distribution_choice.enabled_values == [False, True]
    assert frame.engine_choice.enabled_values == [False, True]
    assert frame.mode_choice.enabled_values == [False, True]
    assert frame.timeout_input.enabled_values == [False, True]
    assert frame.folder_button.enabled_values == [False, True]
    assert frame.folder_text.enabled_values == [False, True]
    assert statuses == ["Конвертация...", "Готово"]


def test_worker_reports_unexpected_error_and_finishes(gui_module, monkeypatch):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.results = queue.Queue()

    def fail(**kwargs):
        raise ValueError("invalid input")

    monkeypatch.setattr(gui_module, "convert_tex_to_accessible_html", fail)
    frame.convert_files([Path("source.tex")], None, "lualatex", "default")
    messages = []
    while not frame.results.empty():
        messages.append(frame.results.get_nowait())
    assert messages[-1] == ("done", "0|1|1")
    assert any(
        kind == "error" and "ValueError" in message for kind, message in messages
    )
