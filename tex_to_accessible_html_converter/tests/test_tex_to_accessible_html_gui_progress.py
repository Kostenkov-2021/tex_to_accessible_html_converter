from __future__ import annotations

import importlib
import queue
import sys
from types import ModuleType

import pytest


class FakeControl:
    def __init__(self) -> None:
        self.range_values: list[int] = []
        self.values: list[int] = []
        self.text = ""
        self.pulses = 0

    def Pulse(self) -> None:
        self.pulses += 1

    def SetRange(self, value: int) -> None:
        self.range_values.append(value)

    def SetValue(self, value: int) -> None:
        self.values.append(value)

    def AppendText(self, text: str) -> None:
        self.text += text


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
    monkeypatch.setitem(sys.modules, "wx", fake_wx)
    sys.modules.pop("localization", None)
    sys.modules.pop("tex_to_accessible_html_gui", None)
    module = importlib.import_module("tex_to_accessible_html_gui")
    yield module
    sys.modules.pop("tex_to_accessible_html_gui", None)
    sys.modules.pop("localization", None)


def test_poll_results_updates_progress_log_and_summary(gui_module):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.results = queue.Queue()
    frame.results.put(("start", "2"))
    frame.results.put(("progress", "1|2|Converting file.tex"))
    frame.results.put(("ok", "out.html"))
    frame.results.put(("done", "1|0|2"))
    frame.progress = FakeControl()
    frame.log = FakeControl()
    statuses = []
    frame.SetStatusText = statuses.append
    frame.set_busy = lambda busy: statuses.append(f"busy={busy}")

    gui_module.ConverterFrame.poll_results(frame)

    assert frame.progress.range_values == [100]
    assert frame.progress.values == [0, 100]
    assert frame.progress.pulses == 0
    assert "2" in frame.log.text
    assert "Converting file.tex" in frame.log.text
    assert "out.html" in frame.log.text
    assert statuses[-2] == "busy=False"


@pytest.mark.parametrize("failures", [0, 1])
def test_progress_animates_without_worker_messages_and_stops_when_done(
    gui_module, failures
):
    frame = object.__new__(gui_module.ConverterFrame)
    frame.results = queue.Queue()
    frame.progress = FakeControl()
    frame.log = FakeControl()
    frame.SetStatusText = lambda status: None
    busy_values = []
    frame.set_busy = busy_values.append
    scheduled = []
    gui_module.wx.CallLater = lambda delay, callback: scheduled.append(
        (delay, callback)
    )

    frame.results.put(("start", "1"))
    frame.results.put(("progress", "0|1|Converting file.tex"))
    frame.poll_results()
    for _ in range(3):
        delay, callback = scheduled.pop(0)
        assert delay == 100
        callback()

    assert frame.progress.pulses == 4
    assert frame.progress.values == [0]
    frame.results.put(("done", f"{1 - failures}|{failures}|1"))
    scheduled.pop(0)[1]()
    assert frame.progress.values[-1] == 100
    assert frame.progress.pulses == 4
    assert busy_values == [False]
    assert scheduled == []
