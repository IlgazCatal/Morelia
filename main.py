import builtins
import keyword
import logging as log
import os
import shlex
import subprocess
import sys
import tempfile

import wx
import wx.stc as stc

log.basicConfig(filename='error.log', level=log.INFO, format='%(asctime)s %(message)s')

FONT_SIZE = 24
MIN_COMPLETE_LENGTH = 2

# Dark theme. CHROME paints the window corners around the editor, BACKGROUND
# the editor itself, TEXT the default foreground, KEYWORD the Python keywords
# (STC_P_WORD) and ERROR the error names (STC_P_WORD2).
CHROME = wx.Colour(64, 64, 64)
BACKGROUND = wx.Colour(0, 0, 0)
TEXT = wx.Colour(255, 255, 255)
KEYWORD = wx.Colour(255, 0, 0)
ERROR = wx.Colour(255, 255, 0)

# Every style the Python lexer paints with. STC_STYLE_DEFAULT is not one of
# them: it does not feed the lexer styles, so they all need explicit colours.
DARK_STYLES = (
    stc.STC_P_DEFAULT,
    stc.STC_P_WORD,
    stc.STC_P_COMMENTLINE,
    stc.STC_P_COMMENTBLOCK,
    stc.STC_P_NUMBER,
    stc.STC_P_STRING,
    stc.STC_P_STRINGEOL,
    stc.STC_P_CHARACTER,
    stc.STC_P_TRIPLE,
    stc.STC_P_TRIPLEDOUBLE,
    stc.STC_P_IDENTIFIER,
    stc.STC_P_WORD2,
    stc.STC_P_CLASSNAME,
    stc.STC_P_DEFNAME,
    stc.STC_P_DECORATOR,
    stc.STC_P_OPERATOR,
)

# The error names, i.e. the built-in exception hierarchy. They go into the
# lexer's second word list so they get their own style; otherwise the lexer
# treats them as ordinary identifiers. Leading underscores are left out:
# _IncompleteInputError is a parser internal, not something anyone types.
ERROR_KEYWORDS = sorted(
    name for name in dir(builtins)
    if isinstance(getattr(builtins, name), type)
    and issubclass(getattr(builtins, name), BaseException)
    and not name.startswith('_')
)

# Don't offer completions while the caret sits inside literals or comments.
IGNORED_STYLES = {
    stc.STC_P_STRING,
    stc.STC_P_STRINGEOL,
    stc.STC_P_CHARACTER,
    stc.STC_P_TRIPLE,
    stc.STC_P_TRIPLEDOUBLE,
    stc.STC_P_COMMENTLINE,
    stc.STC_P_COMMENTBLOCK,
}



class Frame1(wx.Frame):

    def __init__(self):
        super().__init__(parent=None, title='Morelia Text Editor')
        self.Centre()
        # Path of the file currently open, or None for an unsaved buffer.
        # Ctrl+S writes here; with None it falls back to Save As.
        self.pathname = None
        self.InitUI()
        self.SetIcon(wx.Icon("icon.png"))

    def InitUI(self):
        self.panel = wx.Window(self)
        self.SetBackgroundColour(CHROME)
        self.panel.SetBackgroundColour(CHROME)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        font1 = wx.Font(FONT_SIZE, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False)
        self.ctrl1 = stc.StyledTextCtrl(self.panel, style=wx.TE_MULTILINE)
        self.ctrl1.StyleSetFont(stc.STC_STYLE_DEFAULT, font1)
        self.ctrl1.SetLexer(stc.STC_LEX_PYTHON)
        self.ctrl1.SetKeyWords(0, " ".join(keyword.kwlist))
        # Word list 1 is the lexer's second list and styles as STC_P_WORD2.
        self.ctrl1.SetKeyWords(1, " ".join(ERROR_KEYWORDS))
        # STC_STYLE_DEFAULT does not feed the styles the lexer paints with:
        # plain text is style 0 and every token style keeps its own attributes,
        # so each one is given the black background and the white text.
        for style in DARK_STYLES:
            self.ctrl1.StyleSetBackground(style, BACKGROUND)
            self.ctrl1.StyleSetForeground(style, TEXT)
        self.ctrl1.StyleSetBackground(stc.STC_STYLE_DEFAULT, BACKGROUND)
        self.ctrl1.StyleSetForeground(stc.STC_STYLE_DEFAULT, TEXT)
        self.ctrl1.SetCaretForeground(wx.Colour(255, 255, 255))
        self.ctrl1.StyleSetForeground(stc.STC_P_WORD, KEYWORD)
        self.ctrl1.StyleSetForeground(stc.STC_P_WORD2, ERROR)
        # The lexer creates a 16px text margin that nothing ever puts text in
        # (MarginGetText is empty for every line) and GTK paints it with the
        # widget background, which stayed white. Drop the margins.
        for margin in range(self.ctrl1.GetMarginCount()):
            self.ctrl1.SetMarginWidth(margin, 0)
        self.ctrl1.AutoCompSetIgnoreCase(True)
        self.ctrl1.AutoCompSetAutoHide(True)
        self.ctrl1.AutoCompSetMaxHeight(12)
        self.ctrl1.AutoCompSetCancelAtStart(True)
        self.completions = " ".join(sorted(set(keyword.kwlist) | set(dir(builtins))))
        self.ctrl1.SetFocus()
        self.sizer.Add(self.ctrl1, 1, wx.ALL | wx.EXPAND, 0)
        self.panel.SetSizer(self.sizer)
        self.Show()
        self.screen_size = self.ctrl1.GetScreenRect()

        menubar = wx.MenuBar()
        menubar.SetBackgroundColour(CHROME)
        menubar.SetForegroundColour(TEXT)
        fileMenu = wx.Menu()
        fileItem = fileMenu.Append(wx.ID_EXIT, 'Quit', 'Quit application')
        menubar.Append(fileMenu, '&File')
        actionsMenu = wx.Menu()
        saveItem = actionsMenu.Append(wx.ID_SAVE, "Save", "Save file...")
        saveAsItem = actionsMenu.Append(wx.ID_SAVEAS, "Save As", "Save file under a new name...")
        openItem = actionsMenu.Append(wx.ID_OPEN, "Open", "Open File...")
        completeItem = actionsMenu.Append(wx.ID_ANY, "Autocomplete", "Show autocomplete list")
        runItem = actionsMenu.Append(wx.ID_EXECUTE, "Run with Parameters...", "Run current code with custom arguments")
        viewMenu = wx.Menu()
        zoomInItem = viewMenu.Append(wx.ID_ZOOM_IN, "Zoom (+)", "Zoom in")
        zoomOutItem = viewMenu.Append(wx.ID_ZOOM_OUT, "Zoom (-)", "Zoom out")
        menubar.Append(actionsMenu, "&Actions")
        menubar.Append(viewMenu, "&View")

        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, self.OnQuit, fileItem, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.onSave, saveItem, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnSaveAs, saveAsItem, id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self.openFile, openItem, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.onZoomIn, zoomInItem, id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, self.onZoomOut, zoomOutItem, id=wx.ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, self.onAutocomplete, completeItem)
        self.Bind(wx.EVT_MENU, self.onRun, runItem, id=wx.ID_EXECUTE)
        # EVT_CHAR must be bound to the editor itself. A binding on the Frame
        # never sees keystrokes that ctrl1 consumes.
        self.ctrl1.Bind(wx.EVT_CHAR, self.autoComplete)
        self.Bind(wx.EVT_CHAR_HOOK, self.autoTab)

        shortcuts = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('Q'), wx.ID_EXIT),  # ctrl+q to exit
            (wx.ACCEL_CTRL, ord('S'), wx.ID_SAVE),  # ctrl+s to save
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('S'), wx.ID_SAVEAS),  # ctrl+shift+s for save as
            (wx.ACCEL_CTRL, ord('O'), wx.ID_OPEN),  # ctrl+o to open
            (wx.ACCEL_CTRL, ord('R'), wx.ID_EXECUTE),  # ctrl+r to run
            (wx.ACCEL_CTRL, ord('1'), wx.ID_ZOOM_IN),  # ctrl+1 to zoom in
            (wx.ACCEL_CTRL, ord('2'), wx.ID_ZOOM_OUT)  # ctrl+2 to zoom out
        ])

        self.SetAcceleratorTable(shortcuts)

        self.SetSize((1024, 768))
        self.SetTitle('Morelia Text Editor')
        self.Centre()

    def autoTab(self, event):
        keycode = event.GetKeyCode()

        if keycode == wx.WXK_RETURN:
            # Scintilla accepts a completion on Tab or a fillup character, never
            # on Return, so Enter has to do it here. Without this the key is
            # swallowed by the auto-indent below and a newline lands in the
            # buffer instead of the selected word. A highlighted item is
            # required; with nothing selected Enter still starts a new line.
            if self.ctrl1.AutoCompActive() and self.ctrl1.AutoCompGetCurrent() >= 0:
                self.ctrl1.AutoCompComplete()
                event.Skip()
                return

            insertion_point = self.ctrl1.GetInsertionPoint()
            text_upto_cursor = self.ctrl1.GetValue()[:insertion_point]

            lines = text_upto_cursor.split('\n')
            current_line = lines[-1] if lines else ''

            leading_whitespace = current_line[:len(current_line) - len(current_line.lstrip())]
            trimmed_line = current_line.rstrip()

            # AddText, not WriteText: on StyledTextCtrl WriteText is a SetText
            # alias, so it would throw away the buffer instead of inserting.
            if trimmed_line.endswith(':'):
                tab = '    '
                self.ctrl1.SetInsertionPoint(insertion_point)
                self.ctrl1.AddText('\n' + leading_whitespace + tab)
            else:
                self.ctrl1.SetInsertionPoint(insertion_point)
                self.ctrl1.AddText('\n' + leading_whitespace)
        elif keycode == wx.WXK_BACK:
            # Scintilla's backspace unindents: with the caret inside the
            # leading whitespace it drops the whole indentation, so one
            # Backspace undoes several Tab presses. DeleteBackNotLine()
            # obeys the same rule, so delete the range ourselves.
            # Any completion goes first: the key is consumed, so Scintilla
            # never refreshes the popup and its selection would go stale
            # against the shortened word.
            self.ctrl1.AutoCompCancel()
            first, last = self.ctrl1.GetSelection()
            if first != last:
                start, end = first, last
            else:
                end = self.ctrl1.GetCurrentPos()
                start = end - 1
            if start < 0:
                return
            self.ctrl1.SetTargetStart(start)
            self.ctrl1.SetTargetEnd(end)
            self.ctrl1.ReplaceTarget('')
            self.ctrl1.TargetWholeDocument()
        else:
            event.Skip()

    def onZoomIn(self, event):
        font = self.ctrl1.GetFont()
        size = font.GetPointSize()
        font.SetPointSize(size + 2)
        self.ctrl1.SetFont(font)
        self.ctrl1.Update()

    def onZoomOut(self, event):
        font = self.ctrl1.GetFont()
        size = font.GetPointSize()
        font.SetPointSize(max(size - 2, 6))
        self.ctrl1.SetFont(font)
        self.ctrl1.Update()

    def OnQuit(self, e):
        self.Close()

    def currentWord(self):
        pos = self.ctrl1.GetCurrentPos()
        # WordStartPosition takes (pos, onlyWordCharacters) and returns a
        # single int, not a tuple.
        start = self.ctrl1.WordStartPosition(pos, False)
        return pos - start, self.ctrl1.GetTextRange(start, pos)

    def onAutocomplete(self, event):
        length, word = self.currentWord()
        if word:
            self.ctrl1.AutoCompShow(length, self.completions)

    def autoComplete(self, event):
        keycode = event.GetUnicodeKey()

        # WXK_NONE and every special key (WXK_LEFT, WXK_HOME, ...) sit at or
        # above WXK_START. Some of those values are valid codepoints (WXK_LEFT
        # is 314, and chr(314) is an alnum letter), so the range must be
        # checked before chr().
        if keycode == wx.WXK_NONE or keycode >= wx.WXK_START:
            event.Skip()
            return

        char = chr(keycode)

        # Auto-pairing for common brackets and quotes
        pos = self.ctrl1.GetCurrentPos()
        # Don't pair if inside comments/strings (follow same style check as autocomplete)
        in_ignored = pos > 0 and self.ctrl1.GetStyleAt(pos - 1) in IGNORED_STYLES
        pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '"': '"',
            "'": "'",
            '`': '`',
        }
        if char in pairs and not in_ignored:
            close = pairs[char]
            self.ctrl1.AddText(char + close)
            self.ctrl1.SetCurrentPos(pos + 1)
            return

        if not (char.isalnum() or char == '_'):
            event.Skip()
            return

        if self.ctrl1.AutoCompActive():
            event.Skip()
            return

        if in_ignored:
            event.Skip()
            return

        # EVT_CHAR is delivered *before* Scintilla inserts the character, so
        # currentWord() here only sees the letters typed so far and the popup
        # lags one keystroke behind. Let Scintilla insert the character first,
        # then open the popup from an idle callback where the buffer is
        # accurate.
        event.Skip()
        wx.CallAfter(self.showAutocomplete)

    def showAutocomplete(self):
        length, word = self.currentWord()
        if word and length >= MIN_COMPLETE_LENGTH:
            self.ctrl1.AutoCompShow(length, self.completions)


    def openFile(self, event):
        with wx.FileDialog(self, "Open Python file", "", "",
                           "py files (*.py)|*.py", wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as openFileDialog:

            if openFileDialog.ShowModal() == wx.ID_CANCEL:
                return

            path = openFileDialog.GetPath()

        with open(path, "r", encoding="utf-8") as p:
            # Drop any open completion first. SetText leaves the popup active
            # with a stale selection, and the next Return would then complete
            # that selection over the freshly loaded text.
            self.ctrl1.AutoCompCancel()
            self.ctrl1.SetText(p.read())

        self.pathname = path
        self.SetTitle("%s - Morelia Text Editor" % os.path.basename(path))

    def writeFile(self, pathname):
        contents = self.ctrl1.GetValue()
        try:
            with open(pathname, "w", encoding="utf-8") as file:
                file.write(contents)
        except IOError:
            wx.LogError("Cannot save current data in file '%s'." % pathname)
            return False
        self.pathname = pathname
        self.SetTitle("%s - Morelia Text Editor" % os.path.basename(pathname))
        return True

    def onSave(self, event):
        # Ctrl+S: write straight back to the current file. With no file open
        # yet there is nothing to overwrite, so fall through to Save As.
        if not self.pathname:
            self.OnSaveAs(event)
            return
        self.writeFile(self.pathname)

    def OnSaveAs(self, event):

        with wx.FileDialog(self, "Save Python file", wildcard="py files (*.py)|*.py",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            self.writeFile(fileDialog.GetPath())

    def _writeTempIfNeeded(self):
        """Write current buffer to a temp file if not saved, else save to pathname."""
        if self.pathname:
            self.writeFile(self.pathname)
            return self.pathname
        fd, temp_path = tempfile.mkstemp(suffix='.py', prefix='morelia_')
        os.close(fd)
        contents = self.ctrl1.GetValue()
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(contents)
        return temp_path

    def runCurrentCode(self, args_str=''):
        """Run the current Python file with user-provided arguments."""
        script_path = self._writeTempIfNeeded()
        args = []
        if args_str.strip():
            try:
                args = shlex.split(args_str, posix=(os.name != 'nt'))
            except Exception:
                args = args_str.split()
        cmd = [sys.executable, script_path] + args
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=os.path.dirname(script_path) or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            out, err = proc.communicate(timeout=120)
            return proc.returncode, out, err, script_path
        except subprocess.TimeoutExpired as e:
            if e.stdout:
                out = e.stdout.decode('utf-8', errors='replace') if hasattr(e.stdout, 'decode') else str(e.stdout)
            else:
                out = ''
            if e.stderr:
                err = e.stderr.decode('utf-8', errors='replace') if hasattr(e.stderr, 'decode') else str(e.stderr)
            else:
                err = ''
            try:
                proc.kill()
            except Exception:
                pass
            return -1, out, err + '\n[Timeout after 120s]', script_path
        except Exception as e:
            return -2, '', str(e), script_path

    def onRun(self, event):
        dlg = RunArgsDialog(self, "Run with Parameters")
        if dlg.ShowModal() == wx.ID_OK:
            args = dlg.getArgs()
            dlg.Destroy()
            code, out, err, sp = self.runCurrentCode(args)
            outwin = RunOutputFrame(self, "Run Output", code, out, err, sp)
            outwin.Show()
            return
        dlg.Destroy()


class RunArgsDialog(wx.Dialog):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, size=(600, 120))
        sizer = wx.BoxSizer(wx.VERTICAL)
        arg_sizer = wx.BoxSizer(wx.HORIZONTAL)
        arg_sizer.Add(wx.StaticText(self, label="Arguments:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.args_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.args_ctrl.SetHint("e.g. input.txt --flag value")
        arg_sizer.Add(self.args_ctrl, 1, wx.EXPAND)
        sizer.Add(arg_sizer, 0, wx.ALL | wx.EXPAND, 10)
        btns = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALL | wx.EXPAND, 10)
        self.SetSizer(sizer)
        self.args_ctrl.SetFocus()

    def getArgs(self):
        return self.args_ctrl.GetValue()


class RunOutputFrame(wx.Frame):
    def __init__(self, parent, title, returncode, stdout, stderr, script_path):
        super().__init__(parent, title=title, size=(900, 600))
        self.Centre()
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        info = wx.StaticText(panel, label=f"Return code: {returncode} | Script: {script_path}")
        sizer.Add(info, 0, wx.ALL, 5)
        self.output = wx.stc.StyledTextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.output.StyleSetFont(stc.STC_STYLE_DEFAULT, wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.output.SetText(f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}")
        self.output.StyleClearAll()
        self.output.StyleSetBackground(stc.STC_STYLE_DEFAULT, wx.Colour(0, 0, 0))
        self.output.StyleSetForeground(stc.STC_STYLE_DEFAULT, wx.Colour(255, 255, 255))
        self.output.SetReadOnly(True)
        sizer.Add(self.output, 1, wx.ALL | wx.EXPAND, 5)
        btn = wx.Button(panel, wx.ID_CLOSE, "Close")
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), btn)
        sizer.Add(btn, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        panel.SetSizer(sizer)
        self.Show()


if __name__ == '__main__':
    app = wx.App(False)
    frame = Frame1()
    app.MainLoop()
