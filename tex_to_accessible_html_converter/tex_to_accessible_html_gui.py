"""wxPython GUI for converting TeX files to accessible HTML."""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

from localization import localize_text
from localization import translate as _

try:
    import wx
except ImportError as error:  # pragma: no cover - depends on local GUI packages
    raise SystemExit(
        _(
            "wxPython is required for the graphical interface. Install it in the "
            "Python environment used to run this application."
        )
    ) from error

from converter import (
    ConversionError,
    convert_tex_to_accessible_html,
    logs_directory_for,
    output_file_for,
    temporary_directory_for,
)

ENGINE_CHOICES = [("LuaLaTeX", "lualatex"), ("XeLaTeX", "xelatex"), ("LaTeX", "latex")]
LANGUAGE_CHOICES = [("English", "en"), ("Русский", "ru")]


def tex_distribution_choices() -> list[tuple[str, str]]:
    """Return localized labels and internal TeX-distribution values."""
    return [(_("Automatic"), "auto"), ("MiKTeX", "miktex"), ("TeX Live", "texlive")]


def retention_choices() -> list[tuple[str, str]]:
    """Return localized labels and internal artifact-retention values."""
    return [
        (_("HTML files only"), "html"),
        (_("HTML files and logs"), "logs"),
        (_("HTML files and temporary files"), "temporary"),
        (_("HTML files, logs, and temporary files"), "all"),
    ]


_ACCESSIBLE_BASE = getattr(wx, "Accessible", None)

if _ACCESSIBLE_BASE is not None:

    class AccessibleText(_ACCESSIBLE_BASE):  # type: ignore[misc,valid-type]
        """Expose a control name and description through wx accessibility."""

        def __init__(self, window: wx.Window, name: str, description: str) -> None:
            """Initialize accessibility text for ``window``."""
            super().__init__(window)
            self.name = name
            self.description = description

        def GetName(self, child_id: int) -> tuple[int, str]:
            """Return the accessible name for the control itself."""
            if child_id == getattr(wx, "ACC_SELF", 0):
                return getattr(wx, "ACC_OK", 0), self.name
            return wx.ACC_NOT_IMPLEMENTED, ""

        def GetDescription(self, child_id: int) -> tuple[int, str]:
            """Return the accessible description for the control itself."""
            if child_id == getattr(wx, "ACC_SELF", 0):
                return getattr(wx, "ACC_OK", 0), self.description
            return wx.ACC_NOT_IMPLEMENTED, ""

    class AccessibleFileList(AccessibleText):
        """Expose each file's name and full path as its accessible name."""

        def GetName(self, child_id: int) -> tuple[int, str]:
            """Map one-based accessibility child IDs to current list rows."""
            window = self.GetWindow()
            if 1 <= child_id <= window.GetCount():
                path = Path(window.GetString(child_id - 1))
                return wx.ACC_OK, f"{path.name}, {path}"
            return super().GetName(child_id)

else:
    AccessibleText = None  # type: ignore[assignment,misc]
    AccessibleFileList = None  # type: ignore[assignment,misc]


def set_accessible_text(
    control: wx.Window, name: str, description: str | None = None
) -> None:
    """Set text that screen readers can use when a visible label is separate."""
    accessible_description = description or name
    control.SetName(name)
    control.SetToolTip(accessible_description)
    if hasattr(control, "SetHelpText"):
        control.SetHelpText(accessible_description)
    if AccessibleText is not None and hasattr(control, "SetAccessible"):
        try:
            accessible_class = (
                AccessibleFileList
                if isinstance(control, getattr(wx, "ListBox", ()))
                else AccessibleText
            )
            accessible = accessible_class(control, name, accessible_description)
            control.SetAccessible(accessible)
            control._accessible_text = accessible
        except (AttributeError, TypeError, RuntimeError):
            pass


def selected_value(choice: wx.Choice, values: list[tuple[str, str]]) -> str:
    """Return the internal value selected by a localized choice control."""
    selection = choice.GetSelection()
    if selection == wx.NOT_FOUND:
        selection = 0
    return values[selection][1]


def documentation_path(language: str, *, executable: Path | None = None) -> Path:
    """Locate the bundled or repository documentation for a language."""
    filename = "README_RU.html" if language == "ru" else "README.html"
    executable = executable or Path(sys.executable)
    candidates = (
        executable.resolve().parent / "docs" / filename,
        Path(__file__).resolve().parent.parent / "docs" / filename,
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


class ConverterFrame(wx.Frame):
    """Present conversion settings and coordinate background conversions."""

    def __init__(self, state: dict[str, object] | None = None) -> None:
        """Build the main window and restore optional interface ``state``."""
        super().__init__(None, title=_("TeX to Accessible HTML"), size=(800, 600))
        state = state or {}
        stored_files = state.get("files", [])
        self.files: list[Path] = (
            list(stored_files)
            if isinstance(stored_files, list)
            and all(isinstance(path, Path) for path in stored_files)
            else []
        )
        self.worker: threading.Thread | None = None
        self.results: queue.Queue[tuple[str, str]] = queue.Queue()
        self.tex_distribution_choices = tex_distribution_choices()
        self.retention_choices = retention_choices()

        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        language_row = wx.BoxSizer(wx.HORIZONTAL)
        language_row.Add(
            wx.StaticText(panel, label=_("Language:")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )
        self.language_choice = wx.Choice(
            panel, choices=[label for label, _value in LANGUAGE_CHOICES]
        )
        self.language_choice.SetSelection(
            next(i for i, item in enumerate(LANGUAGE_CHOICES) if item[1] == _.language)
        )
        set_accessible_text(
            self.language_choice,
            _("Interface language"),
            _("Change the application interface language."),
        )
        language_row.Add(self.language_choice, 0)
        root.Add(language_row, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        file_label = wx.StaticText(panel, label=_("TeX files"))
        root.Add(file_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

        self.file_list = wx.ListBox(panel, style=wx.LB_EXTENDED)
        set_accessible_text(
            self.file_list,
            _("TeX files"),
            _("Files that will be converted to HTML."),
        )
        root.Add(self.file_list, 1, wx.EXPAND | wx.ALL, 12)
        for path in self.files:
            self.file_list.Append(str(path))

        file_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.add_button = wx.Button(panel, label=_("Add .tex"))
        self.add_folder_button = wx.Button(panel, label=_("Add folder"))
        self.remove_button = wx.Button(panel, label=_("Remove selected"))
        self.clear_button = wx.Button(panel, label=_("Clear"))
        file_buttons.Add(self.add_button, 0, wx.RIGHT, 8)
        file_buttons.Add(self.add_folder_button, 0, wx.RIGHT, 8)
        file_buttons.Add(self.remove_button, 0, wx.RIGHT, 8)
        file_buttons.Add(self.clear_button, 0)
        root.Add(file_buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        output_group = wx.StaticBox(panel, label=_("HTML output"))
        output_box = wx.StaticBoxSizer(output_group, wx.VERTICAL)
        self.same_folder_radio = wx.RadioButton(
            output_group,
            label=_("In the same folder as each .tex file"),
            style=wx.RB_GROUP,
        )
        self.custom_folder_radio = wx.RadioButton(
            output_group, label=_("In the selected folder:")
        )
        output_box.Add(self.same_folder_radio, 0, wx.ALL, 8)

        folder_row = wx.BoxSizer(wx.HORIZONTAL)
        self.folder_text = wx.TextCtrl(output_group)
        self.folder_button = wx.Button(output_group, label=_("Browse..."))
        set_accessible_text(
            self.folder_text,
            _("HTML output folder"),
            _("Folder used for HTML files when the selected-folder option is enabled."),
        )
        folder_row.Add(
            self.custom_folder_radio, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8
        )
        folder_row.Add(self.folder_text, 1, wx.EXPAND | wx.RIGHT, 8)
        folder_row.Add(self.folder_button, 0)
        output_box.Add(folder_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        root.Add(output_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        options_row = wx.BoxSizer(wx.HORIZONTAL)
        options_row.Add(
            wx.StaticText(panel, label=_("Engine:")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            6,
        )
        self.engine_choice = wx.Choice(
            panel, choices=[label for label, _value in ENGINE_CHOICES]
        )
        self.engine_choice.SetSelection(0)
        set_accessible_text(
            self.engine_choice, _("TeX engine"), _("TeX engine used by make4ht.")
        )
        options_row.Add(self.engine_choice, 0, wx.RIGHT, 18)
        options_row.Add(
            wx.StaticText(panel, label="TeX:"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            6,
        )
        self.tex_distribution_choice = wx.Choice(
            panel, choices=[label for label, _value in self.tex_distribution_choices]
        )
        self.tex_distribution_choice.SetSelection(0)
        set_accessible_text(
            self.tex_distribution_choice,
            _("TeX distribution"),
            _("Choose automatic detection, MiKTeX, or TeX Live for make4ht."),
        )
        options_row.Add(self.tex_distribution_choice, 0, wx.RIGHT, 18)
        root.Add(options_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        timeout_row = wx.BoxSizer(wx.HORIZONTAL)
        timeout_row.Add(
            wx.StaticText(panel, label=_("Time limit per file (seconds):")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            8,
        )
        self.timeout_input = wx.SpinCtrl(panel, min=1, max=86400, initial=300)
        set_accessible_text(
            self.timeout_input,
            _("Conversion time limit"),
            _(
                "Maximum processing time for one file. TeX processes are stopped when the limit expires."
            ),
        )
        timeout_row.Add(self.timeout_input, 0)
        root.Add(timeout_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.retention_box = wx.RadioBox(
            panel,
            label=_("Files to keep"),
            choices=[label for label, _value in self.retention_choices],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        self.retention_box.SetSelection(0)
        set_accessible_text(
            self.retention_box,
            _("Files to keep"),
            _(
                "Choose whether to keep only HTML, logs, temporary files, or both logs and temporary files."
            ),
        )
        root.Add(self.retention_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        set_accessible_text(
            self.log, _("Conversion log"), _("Conversion progress and error messages.")
        )
        root.Add(self.log, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.progress = wx.Gauge(panel, range=100)
        set_accessible_text(
            self.progress,
            _("Conversion progress"),
            _(
                "A moving indicator means conversion is running. The number of processed files is shown in the status bar."
            ),
        )
        root.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.documentation_button = wx.Button(panel, label=_("Open documentation"))
        self.convert_button = wx.Button(panel, label=_("Convert"))
        self.close_button = wx.Button(panel, label=_("Close"))
        set_accessible_text(
            self.documentation_button,
            _("Open documentation"),
            _(
                "Open the documentation for the current interface language. Keyboard shortcut: F1."
            ),
        )
        action_row.Add(self.documentation_button, 0, wx.RIGHT, 8)
        action_row.AddStretchSpacer()
        action_row.Add(self.convert_button, 0, wx.RIGHT, 8)
        action_row.Add(self.close_button, 0)
        root.Add(action_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(root)
        self.same_folder_radio.SetValue(True)
        self.update_folder_controls_visibility()
        self.CreateStatusBar()
        self.SetStatusText(_("Ready"))

        self.add_button.Bind(wx.EVT_BUTTON, self.on_add_files)
        self.add_folder_button.Bind(wx.EVT_BUTTON, self.on_add_folder)
        self.remove_button.Bind(wx.EVT_BUTTON, self.on_remove_selected)
        self.clear_button.Bind(wx.EVT_BUTTON, self.on_clear)
        self.convert_button.Bind(wx.EVT_BUTTON, self.on_convert)
        self.close_button.Bind(wx.EVT_BUTTON, lambda _event: self.Close())
        self.folder_button.Bind(wx.EVT_BUTTON, self.on_choose_folder)
        self.folder_text.Bind(wx.EVT_TEXT, self.on_custom_folder_selected)
        self.same_folder_radio.Bind(
            wx.EVT_RADIOBUTTON, self.on_output_folder_mode_changed
        )
        self.custom_folder_radio.Bind(
            wx.EVT_RADIOBUTTON, self.on_output_folder_mode_changed
        )
        self.file_list.Bind(wx.EVT_KEY_DOWN, self.on_file_list_key_down)
        self.language_choice.Bind(wx.EVT_CHOICE, self.on_language_changed)
        self.documentation_button.Bind(wx.EVT_BUTTON, self.on_open_documentation)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_help_key)

        self.restore_state(state)

    @staticmethod
    def select_value(
        control: wx.Choice, choices: list[tuple[str, str]], value: object
    ) -> None:
        """Select the item whose internal value equals ``value``."""
        for index, (_label, candidate) in enumerate(choices):
            if candidate == value:
                control.SetSelection(index)
                return

    def restore_state(self, state: dict[str, object]) -> None:
        """Restore conversion settings after rebuilding the localized window."""
        self.select_value(self.engine_choice, ENGINE_CHOICES, state.get("engine"))
        self.select_value(
            self.tex_distribution_choice,
            self.tex_distribution_choices,
            state.get("distribution"),
        )
        timeout = state.get("timeout")
        if isinstance(timeout, int):
            self.timeout_input.SetValue(timeout)
        self.select_value(
            self.retention_box, self.retention_choices, state.get("retention")
        )
        if state.get("custom_folder"):
            self.custom_folder_radio.SetValue(True)
            self.folder_text.SetValue(str(state.get("folder", "")))
        self.update_folder_controls_visibility()

    def on_language_changed(self, _event: wx.CommandEvent) -> None:
        """Rebuild the window in the newly selected language."""
        language = selected_value(self.language_choice, LANGUAGE_CHOICES)
        if language == _.language:
            return
        state = {
            "files": list(self.files),
            "engine": selected_value(self.engine_choice, ENGINE_CHOICES),
            "distribution": selected_value(
                self.tex_distribution_choice, self.tex_distribution_choices
            ),
            "timeout": self.timeout_input.GetValue(),
            "retention": selected_value(self.retention_box, self.retention_choices),
            "custom_folder": self.custom_folder_radio.GetValue(),
            "folder": self.folder_text.GetValue(),
        }
        _.set_language(language, persist=True)
        replacement = ConverterFrame(state)
        replacement.Show()
        self.Destroy()

    def on_open_documentation(self, _event: wx.CommandEvent | None = None) -> None:
        """Open local documentation for the active interface language."""
        path = documentation_path(_.language)
        if not path.is_file() or not wx.LaunchDefaultApplication(str(path)):
            wx.MessageBox(
                _("Documentation could not be opened: {path}", path=path),
                _("Documentation unavailable"),
                wx.OK | wx.ICON_ERROR,
            )

    def on_help_key(self, event: wx.KeyEvent) -> None:
        """Open documentation for F1 and pass other keys to wxPython."""
        if event.GetKeyCode() == wx.WXK_F1:
            self.on_open_documentation()
            return
        event.Skip()

    def on_add_files(self, _event: wx.CommandEvent) -> None:
        """Add unique TeX files selected in a file dialog."""
        with wx.FileDialog(
            self,
            message=_("Select .tex files"),
            wildcard=_("TeX files (*.tex)|*.tex"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            existing = {path.resolve() for path in self.files}
            for filename in dialog.GetPaths():
                path = Path(filename).resolve()
                if path not in existing:
                    self.files.append(path)
                    existing.add(path)
                    self.file_list.Append(str(path))

    def on_add_folder(self, _event: wx.CommandEvent) -> None:
        """Add unique TeX files located directly in a selected folder."""
        with wx.DirDialog(
            self, message=_("Select a folder containing .tex files")
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            folder = Path(dialog.GetPath()).resolve()
        files = sorted(
            (
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.casefold() == ".tex"
            ),
            key=lambda path: path.name.casefold(),
        )
        if not files:
            wx.MessageBox(
                _("The selected folder contains no .tex files."),
                _("No TeX files found"),
                wx.OK | wx.ICON_WARNING,
            )
            return
        existing = {path.resolve() for path in self.files}
        for path in files:
            path = path.resolve()
            if path not in existing:
                self.files.append(path)
                existing.add(path)
                self.file_list.Append(str(path))

    def on_remove_selected(self, _event: wx.CommandEvent) -> None:
        """Remove selected entries from the conversion list."""
        for index in reversed(self.file_list.GetSelections()):
            self.file_list.Delete(index)
            del self.files[index]

    def on_clear(self, _event: wx.CommandEvent) -> None:
        """Clear the conversion list and displayed progress log."""
        self.files.clear()
        self.file_list.Clear()
        self.log.Clear()
        self.SetStatusText(_("Ready"))

    def on_choose_folder(self, _event: wx.CommandEvent) -> None:
        """Select and activate a custom HTML output folder."""
        with wx.DirDialog(self, message=_("Select an HTML output folder")) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.folder_text.SetValue(dialog.GetPath())
            self.custom_folder_radio.SetValue(True)
            self.update_folder_controls_visibility()

    def on_custom_folder_selected(self, _event: wx.CommandEvent) -> None:
        """Activate custom output when its text field changes."""
        self.custom_folder_radio.SetValue(True)
        self.update_folder_controls_visibility()

    def on_output_folder_mode_changed(self, _event: wx.CommandEvent) -> None:
        """Update folder controls after the output mode changes."""
        self.update_folder_controls_visibility()

    def update_folder_controls_visibility(self) -> None:
        """Show and enable custom-folder controls only when applicable."""
        show_folder_controls = self.is_custom_folder_selected()
        self.folder_text.Show(show_folder_controls)
        self.folder_button.Show(show_folder_controls)
        parent = (
            self.folder_text.GetParent()
            if hasattr(self.folder_text, "GetParent")
            else None
        )
        if parent is not None and hasattr(parent, "Layout"):
            parent.Layout()
        if hasattr(self, "Layout"):
            self.Layout()

    def is_custom_folder_selected(self) -> bool:
        """Return whether output should use the custom folder."""
        if not hasattr(self, "custom_folder_radio"):
            return True
        return self.custom_folder_radio.GetValue()

    def on_file_list_key_down(self, event: wx.KeyEvent) -> None:
        """Allow useful list navigation while suppressing type-to-select."""
        key_code = event.GetKeyCode()
        allowed_keys = self.wx_key_codes(
            "WXK_UP", "WXK_DOWN", "WXK_NUMPAD_UP", "WXK_NUMPAD_DOWN", "WXK_TAB"
        )
        blocked_navigation_keys = self.wx_key_codes(
            "WXK_LEFT",
            "WXK_RIGHT",
            "WXK_NUMPAD_LEFT",
            "WXK_NUMPAD_RIGHT",
            "WXK_HOME",
            "WXK_END",
            "WXK_PAGEUP",
            "WXK_PAGEDOWN",
            "WXK_NUMPAD_HOME",
            "WXK_NUMPAD_END",
            "WXK_NUMPAD_PAGEUP",
            "WXK_NUMPAD_PAGEDOWN",
        )

        if key_code in allowed_keys:
            event.Skip()
            return
        if key_code in blocked_navigation_keys or self.is_printable_key(event):
            return
        event.Skip()

    @staticmethod
    def wx_key_codes(*names: str) -> set[int]:
        """Return available integer wx key codes for ``names``."""
        return {
            code for name in names if isinstance((code := getattr(wx, name, None)), int)
        }

    @staticmethod
    def is_printable_key(event: wx.KeyEvent) -> bool:
        """Return whether ``event`` represents a printable character."""
        if not hasattr(event, "GetUnicodeKey"):
            return False
        unicode_key = event.GetUnicodeKey()
        return unicode_key >= 32

    def on_convert(self, _event: wx.CommandEvent) -> None:
        """Validate settings and start conversion in a worker thread."""
        if not self.files:
            wx.MessageBox(
                _("Select at least one .tex file."),
                _("No files selected"),
                wx.OK | wx.ICON_WARNING,
            )
            return

        output_dir = None
        if self.custom_folder_radio.GetValue():
            folder = self.folder_text.GetValue()
            if not folder:
                wx.MessageBox(
                    _("Select a folder for the HTML output."),
                    _("No folder selected"),
                    wx.OK | wx.ICON_WARNING,
                )
                return
            output_dir = Path(folder)

        self.set_busy(True)
        self.log.Clear()
        self.progress.SetRange(100)
        self.progress.SetValue(0)
        self.progress.Pulse()
        self.SetStatusText(_("Converting: 0 of {total}", total=len(self.files)))
        self.log.AppendText(_("Conversion started.") + "\n")

        self.worker = threading.Thread(
            target=self.convert_files,
            args=(
                list(self.files),
                output_dir,
                selected_value(self.engine_choice, ENGINE_CHOICES),
                selected_value(
                    self.tex_distribution_choice, self.tex_distribution_choices
                ),
                self.timeout_input.GetValue(),
                selected_value(self.retention_box, self.retention_choices)
                in {"logs", "all"},
                selected_value(self.retention_box, self.retention_choices)
                in {"temporary", "all"},
            ),
            daemon=True,
        )
        self.worker.start()
        wx.CallLater(100, self.poll_results)

    def convert_files(
        self,
        files: list[Path],
        output_dir: Path | None,
        engine: str,
        tex_distribution: str = "auto",
        timeout: float = 300,
        keep_logs: bool = False,
        keep_temporary_files: bool = False,
    ) -> None:
        """Convert files sequentially and publish progress through the queue."""
        total = len(files)
        successes = 0
        failures = 0
        self.results.put(("start", str(total)))
        for index, tex_file in enumerate(files, start=1):
            self.results.put(
                (
                    "progress",
                    f"{index - 1}|{total}|" + _("Converting: {path}", path=tex_file),
                )
            )
            try:
                output_file = output_file_for(tex_file, output_dir)
                result = convert_tex_to_accessible_html(
                    tex_file=tex_file,
                    output_file=output_file,
                    engine=engine,
                    tex_distribution=tex_distribution,
                    timeout=timeout,
                    keep_logs=keep_logs,
                    keep_temporary_files=keep_temporary_files,
                )
            except ConversionError as error:
                failures += 1
                self.results.put(("error", f"{tex_file}\n{localize_text(str(error))}"))
            except OSError as error:
                failures += 1
                self.results.put(("error", f"{tex_file}\n{localize_text(str(error))}"))
            except Exception as error:  # noqa: BLE001 - keep the GUI worker recoverable
                # An unexpected worker error must not leave the GUI polling
                # forever with its controls disabled.
                failures += 1
                self.results.put(
                    (
                        "error",
                        f"{tex_file}\n"
                        + _(
                            "Unexpected error: {type}: {error}",
                            type=type(error).__name__,
                            error=error,
                        ),
                    )
                )
            else:
                successes += 1
                self.results.put(("ok", str(result)))
            self.results.put(
                (
                    "progress",
                    f"{index}|{total}|"
                    + _("Processed: {current} of {total}", current=index, total=total),
                )
            )
        self.results.put(("done", f"{successes}|{failures}|{total}"))

    def poll_results(self) -> None:
        """Consume worker messages and update the main window."""
        keep_polling = True
        while True:
            try:
                kind, message = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "start":
                total = int(message)
                self.progress.SetRange(100)
                self.progress.SetValue(0)
                self.log.AppendText(_("Files to convert: {total}", total=total) + "\n")
            elif kind == "progress":
                _current_text, _total_text, status = message.split("|", 2)
                self.SetStatusText(status)
                self.log.AppendText(status + "\n")
            elif kind == "ok":
                self.log.AppendText(_("Done: {path}", path=message) + "\n")
                retention = (
                    selected_value(self.retention_box, self.retention_choices)
                    if hasattr(self, "retention_box")
                    else "html"
                )
                if retention in {"logs", "all"}:
                    self.log.AppendText(
                        _("Logs: {path}", path=logs_directory_for(Path(message))) + "\n"
                    )
                if retention in {"temporary", "all"}:
                    self.log.AppendText(
                        _(
                            "Temporary files: {path}",
                            path=temporary_directory_for(Path(message)),
                        )
                        + "\n"
                    )
            elif kind == "error":
                self.log.AppendText(_("Error: {message}", message=message) + "\n")
            elif kind == "done":
                successes, failures, total_text = message.split("|", 2)
                keep_polling = False
                self.set_busy(False)
                self.progress.SetValue(100)
                summary = _(
                    "Finished. Successful: {successes}. Errors: {failures}. Total: {total}.",
                    successes=successes,
                    failures=failures,
                    total=total_text,
                )
                self.log.AppendText(summary + "\n")
                self.SetStatusText(summary)

        if keep_polling:
            # make4ht does not expose a reliable completion percentage. Keep
            # animating even when the worker has no new messages to report.
            self.progress.Pulse()
            wx.CallLater(100, self.poll_results)

    def set_busy(self, busy: bool) -> None:
        """Toggle interactive controls for an active conversion."""
        self.convert_button.Enable(not busy)
        self.add_button.Enable(not busy)
        if hasattr(self, "add_folder_button"):
            self.add_folder_button.Enable(not busy)
        self.remove_button.Enable(not busy)
        self.clear_button.Enable(not busy)
        if hasattr(self, "same_folder_radio"):
            self.same_folder_radio.Enable(not busy)
        if hasattr(self, "custom_folder_radio"):
            self.custom_folder_radio.Enable(not busy)
        if hasattr(self, "tex_distribution_choice"):
            self.tex_distribution_choice.Enable(not busy)
        for name in (
            "engine_choice",
            "timeout_input",
            "retention_box",
            "language_choice",
            "documentation_button",
        ):
            if hasattr(self, name):
                getattr(self, name).Enable(not busy)
        folder_controls_enabled = not busy and self.is_custom_folder_selected()
        self.folder_button.Enable(folder_controls_enabled)
        self.folder_text.Enable(folder_controls_enabled)
        self.SetStatusText(_("Converting...") if busy else _("Ready"))


class ConverterApp(wx.App):
    """Create and own the converter's main wxPython window."""

    def OnInit(self) -> bool:
        """Create the main frame when wxPython initializes the application."""
        frame = ConverterFrame()
        frame.Show()
        return True


def main() -> int:
    """Run the graphical application and return a process exit status."""
    app = ConverterApp(False)
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
