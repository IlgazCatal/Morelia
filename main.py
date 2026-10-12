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
MIN_FONT_SIZE = 6

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


def fuzzyScore(query, text):
    """Subsequence match score for a case-insensitive fuzzy query.

    Higher is better; returns None when the query's characters do not all
    appear in text in order. Consecutive hits and hits at a word boundary
    (start of line or just after a separator) score best.
    """
    if not query:
        return 0
    query = query.lower()
    lowered = text.lower()
    score = 0
    matched = 0
    last = -2
    for i, ch in enumerate(lowered):
        if ch == query[matched]:
            score += 15 if last == i - 1 else 1
            if i == 0 or lowered[i - 1] in ' \t._-/(':
                score += 10
            last = i
            matched += 1
            if matched == len(query):
                break
    if matched < len(query):
        return None
    return score


def fuzzyFilter(query, lines, limit=200):
    """Rank lines against a fuzzy query. Returns (score, lineno, text) tuples.

    An empty query lists every line in document order (up to limit); otherwise
    results are sorted best-score-first, ties broken by line number.
    """
    results = []
    for lineno, text in enumerate(lines):
        score = fuzzyScore(query, text)
        if score is not None:
            results.append((score, lineno, text))
    if query:
        results.sort(key=lambda item: (-item[0], item[1]))
    return results[:limit]


class Frame1(wx.Frame):

    def __init__(self):
        super().__init__(parent=None, title='Morelia Text Editor')
        self.Centre()
        # Path of the file currently open, or None for an unsaved buffer.
        # Ctrl+S writes here; with None it falls back to Save As.
        self.pathname = None
        # Last search, so F3 / Shift+F3 work without the dialog on screen.
        self.search_dialog = None
        self.search_text = ''
        self.search_match_case = False
        self.search_wrap = True
        # Fuzzy search is a separate palette over the document's lines.
        self.fuzzy_dialog = None
        self.fuzzy_query = ''
        self.InitUI()
        self.SetIcon(wx.Icon("icon.png"))

    def InitUI(self):
        self.panel = wx.Window(self)
        self.SetBackgroundColour(CHROME)
        self.panel.SetBackgroundColour(CHROME)
        font1 = wx.Font(FONT_SIZE, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False)
        self.splitter = wx.SplitterWindow(self.panel, style=wx.SP_LIVE_UPDATE)
        self.splitter.SetMinimumPaneSize(150)
        self.tree = wx.TreeCtrl(self.splitter, style=wx.TR_DEFAULT_STYLE | wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT)
        self.tree.SetBackgroundColour(BACKGROUND)
        self.tree.SetForegroundColour(TEXT)
        self.file_panel = wx.Panel(self.splitter)
        self.ctrl1 = stc.StyledTextCtrl(self.file_panel, style=wx.TE_MULTILINE)
        self.ctrl1.StyleSetFont(stc.STC_STYLE_DEFAULT, font1)
        self.ctrl1.SetLexer(stc.STC_LEX_PYTHON)
        self.ctrl1.SetKeyWords(0, " ".join(keyword.kwlist))
        self.ctrl1.SetKeyWords(1, " ".join(ERROR_KEYWORDS))
        for style in DARK_STYLES:
            self.ctrl1.StyleSetBackground(style, BACKGROUND)
            self.ctrl1.StyleSetForeground(style, TEXT)
        self.ctrl1.StyleSetBackground(stc.STC_STYLE_DEFAULT, BACKGROUND)
        self.ctrl1.StyleSetForeground(stc.STC_STYLE_DEFAULT, TEXT)
        self.ctrl1.SetCaretForeground(wx.Colour(255, 255, 255))
        self.ctrl1.StyleSetForeground(stc.STC_P_WORD, KEYWORD)
        self.ctrl1.StyleSetForeground(stc.STC_P_WORD2, ERROR)
        for margin in range(self.ctrl1.GetMarginCount()):
            self.ctrl1.SetMarginWidth(margin, 0)
        self.ctrl1.AutoCompSetIgnoreCase(True)
        self.ctrl1.AutoCompSetAutoHide(True)
        self.ctrl1.AutoCompSetMaxHeight(12)
        self.ctrl1.AutoCompSetCancelAtStart(True)
        self.completions = " ".join(sorted(set(keyword.kwlist) | set(dir(builtins))))
        file_sizer = wx.BoxSizer(wx.VERTICAL)
        file_sizer.Add(self.ctrl1, 1, wx.ALL | wx.EXPAND, 0)
        self.file_panel.SetSizer(file_sizer)
        self.splitter.SplitVertically(self.tree, self.file_panel, 200)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.splitter, 1, wx.ALL | wx.EXPAND, 0)
        self.panel.SetSizer(self.sizer)
        self.populateTree()
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onTreeItemActivated)
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
        searchMenu = wx.Menu()
        findItem = searchMenu.Append(wx.ID_FIND, "Find...", "Find text")
        findNextItem = searchMenu.Append(wx.ID_ANY, "Find Next", "Find next occurrence")
        findPrevItem = searchMenu.Append(wx.ID_ANY, "Find Previous", "Find previous occurrence")
        searchMenu.AppendSeparator()
        fuzzyItem = searchMenu.Append(wx.ID_ANY, "Fuzzy Find...", "Fuzzy search lines")
        viewMenu = wx.Menu()
        zoomInItem = viewMenu.Append(wx.ID_ZOOM_IN, "Zoom (+)", "Zoom in")
        zoomOutItem = viewMenu.Append(wx.ID_ZOOM_OUT, "Zoom (-)", "Zoom out")
        menubar.Append(actionsMenu, "&Actions")
        menubar.Append(searchMenu, "&Search")
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
        self.Bind(wx.EVT_MENU, self.onFind, findItem, id=wx.ID_FIND)
        self.Bind(wx.EVT_MENU, self.onFindNext, findNextItem)
        self.Bind(wx.EVT_MENU, self.onFindPrev, findPrevItem)
        self.Bind(wx.EVT_MENU, self.onFuzzyFind, fuzzyItem)
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
            (wx.ACCEL_CTRL, ord('2'), wx.ID_ZOOM_OUT),  # ctrl+2 to zoom out
            (wx.ACCEL_CTRL, ord('F'), wx.ID_FIND),  # ctrl+f to find
            (wx.ACCEL_NORMAL, wx.WXK_F3, findNextItem.GetId()),  # f3 for find next
            (wx.ACCEL_SHIFT, wx.WXK_F3, findPrevItem.GetId()),  # shift+f3 for find previous
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('F'), fuzzyItem.GetId())  # ctrl+shift+f for fuzzy find
        ])

        self.SetAcceleratorTable(shortcuts)

        self.SetSize((1024, 768))
        self.SetTitle('Morelia Text Editor')
        self.Centre()

    def populateTree(self, path=None):
        if path is None:
            path = os.getcwd()
        self.tree.DeleteAllItems()
        self.tree_root = self.tree.AddRoot(path)
        self._addTreeNodes(self.tree_root, path)
        self.tree.Expand(self.tree_root)

    def _addTreeNodes(self, parent_item, dirname):
        try:
            entries = sorted(os.listdir(dirname))
        except Exception:
            return
        for entry in entries:
            if entry.startswith('.'):
                continue
            full_path = os.path.join(dirname, entry)
            if os.path.isdir(full_path):
                item = self.tree.AppendItem(parent_item, entry)
                self._addTreeNodes(item, full_path)
            else:
                self.tree.AppendItem(parent_item, entry)

    def onTreeItemActivated(self, event):
        item = event.GetItem()
        if not item.IsOk():
            return
        full_path = self._getTreeItemPath(item)
        if full_path and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as p:
                    self.ctrl1.AutoCompCancel()
                    self.ctrl1.SetText(p.read())
                self.pathname = full_path
                self.SetTitle("%s - Morelia Text Editor" % os.path.basename(full_path))
            except Exception as e:
                wx.LogError("Cannot open file '%s': %s" % (full_path, e))

    def _getTreeItemPath(self, item):
        path_parts = []
        while item and item.IsOk() and item != self.tree_root:
            path_parts.append(self.tree.GetItemText(item))
            item = self.tree.GetItemParent(item)
        path_parts.reverse()
        if path_parts:
            return os.path.join(os.getcwd(), *path_parts)
        return os.getcwd()


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
                self.ctrl1.AddText(' ')
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

    def _editorFontSize(self):
        """Point size the editor is currently rendered at.

        Read from STC_STYLE_DEFAULT rather than GetFont(): SetFont() only
        changes the widget font and the text is painted from the styles, so
        the widget font still reports the GTK default (10pt) while the editor
        is at 24pt. Zooming off the widget font therefore starts from the
        wrong base and, worse, every zoom step gets lost.
        """
        return self.ctrl1.StyleGetFont(stc.STC_STYLE_DEFAULT).GetPointSize()

    def _setEditorFontSize(self, pointSize):
        # STC_STYLE_DEFAULT is enough: the lexer styles inherit from it and
        # none of them carries an explicit font. Do not also SetFont() on the
        # control -- that is what made the old zoom a no-op for the text. Nor
        # StyleClearAll(): it resets the per-style foreground/background set
        # up in InitUI, which would drop the syntax colouring.
        font = wx.Font(pointSize, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_BOLD, False)
        self.ctrl1.StyleSetFont(stc.STC_STYLE_DEFAULT, font)
        self.ctrl1.Update()

    def onZoomIn(self, event):
        self._setEditorFontSize(self._editorFontSize() + 2)

    def onZoomOut(self, event):
        self._setEditorFontSize(max(self._editorFontSize() - 2, MIN_FONT_SIZE))

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
        raw = event.GetKeyCode()

        # WXK_NONE and every special key (WXK_LEFT, WXK_HOME, ...) sit at or
        # above WXK_START. Some of those values are valid codepoints (WXK_LEFT
        # is 314, and chr(314) is an alnum letter), so the range must be
        # checked before chr().
        if keycode == wx.WXK_NONE or keycode >= wx.WXK_START or raw >= wx.WXK_START:
            event.Skip()
            return

        # Also skip control characters
        if keycode < 32:
            event.Skip()
            return

        try:
            char = chr(keycode)
        except Exception:
            event.Skip()
            return

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
            # SetSelection, not SetCurrentPos: SetCurrentPos is
            # SCI_SETCURRENTPOS, which moves the caret but keeps the old
            # selection anchor. The auto-inserted closer would come out
            # selected and the next typed character would replace it.
            self.ctrl1.SetSelection(pos + 1, pos + 1)
            return

        if not (char.isalnum() or char == '_' or char in '()[]{}"\'`'):
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

    def onFind(self, event):
        # Reuse the open dialog instead of stacking a second one.
        if self.search_dialog:
            self.search_dialog.Raise()
            self.search_dialog.find_ctrl.SetFocus()
            return
        self.search_dialog = SearchDialog(self)
        self.search_dialog.Show()

    def onFindNext(self, event):
        self._repeatFind(True)

    def onFindPrev(self, event):
        self._repeatFind(False)

    def _repeatFind(self, forward):
        # F3 with nothing searched yet falls back to opening the dialog.
        if not self.search_text:
            self.onFind(None)
            return
        self.findText(self.search_text, forward,
                      self.search_match_case, self.search_wrap)

    def findText(self, text, forward=True, match_case=False, wrap=True):
        """Select the next/previous occurrence of text. Returns True if found."""
        if not text:
            return False
        self.search_text = text
        self.search_match_case = match_case
        self.search_wrap = wrap
        flags = stc.STC_FIND_MATCHCASE if match_case else 0

        pos = self._searchFromAnchor(text, forward, flags)
        if pos == -1 and wrap:
            # SCI_SEARCHNEXT/PREV never wrap, so retry from the far end. Restore
            # the caret if the text is nowhere in the document.
            first, last = self.ctrl1.GetSelection()
            if forward:
                self.ctrl1.SetSelection(0, 0)
            else:
                self.ctrl1.SetSelection(self.ctrl1.GetTextLength(),
                                        self.ctrl1.GetTextLength())
            pos = self._searchFromAnchor(text, forward, flags)
            if pos == -1:
                self.ctrl1.SetSelection(first, last)
        if pos == -1:
            wx.Bell()
            return False
        self.ctrl1.EnsureCaretVisible()
        return True

    def _searchFromAnchor(self, text, forward, flags):
        # The search anchor is the *start* of the selection, so after a match is
        # selected a forward search would just re-find it. Collapse the caret to
        # the end (forward) or the start (backward) first -- SetSelection, not
        # SetCurrentPos, which leaves the old anchor in place.
        first, last = self.ctrl1.GetSelection()
        self.ctrl1.SetSelection(last if forward else first,
                                last if forward else first)
        self.ctrl1.SearchAnchor()
        if forward:
            return self.ctrl1.SearchNext(flags, text)
        return self.ctrl1.SearchPrev(flags, text)

    def onFuzzyFind(self, event):
        # Keep one palette alive; a second Ctrl+Shift+F just refocuses it.
        if self.fuzzy_dialog:
            self.fuzzy_dialog.Raise()
            self.fuzzy_dialog.query_ctrl.SetFocus()
            return
        self.fuzzy_dialog = FuzzyDialog(self)
        self.fuzzy_dialog.Show()

    def fuzzyGotoLine(self, lineno):
        # GotoLine is 0-based and puts the caret at the start of the line.
        self.ctrl1.GotoLine(lineno)
        self.ctrl1.EnsureCaretVisible()
        self.ctrl1.SetFocus()

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
        super().__init__(parent, title=title, size=(600, 140))
        self.SetMinSize((500, 120))
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
        self.Layout()
        self.Fit()
        self.args_ctrl.SetFocus()

    def getArgs(self):
        return self.args_ctrl.GetValue()


class SearchDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Find")
        self.frame = parent
        sizer = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Find:"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.find_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.find_ctrl.SetValue(parent.search_text)
        row.Add(self.find_ctrl, 1, wx.EXPAND)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 10)

        self.match_case = wx.CheckBox(self, label="Match case")
        self.match_case.SetValue(parent.search_match_case)
        self.wrap = wx.CheckBox(self, label="Wrap around")
        self.wrap.SetValue(parent.search_wrap)
        sizer.Add(self.match_case, 0, wx.LEFT | wx.RIGHT, 10)
        sizer.Add(self.wrap, 0, wx.ALL, 10)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        prev_btn = wx.Button(self, label="Find Previous")
        next_btn = wx.Button(self, label="Find Next")
        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        btns.Add(prev_btn, 0, wx.RIGHT, 5)
        btns.Add(next_btn, 0, wx.RIGHT, 5)
        btns.Add(close_btn, 0)
        sizer.Add(btns, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizer(sizer)
        self.SetMinSize((360, 190))
        self.Fit()

        self.Bind(wx.EVT_BUTTON, lambda e: self._search(False), prev_btn)
        self.Bind(wx.EVT_BUTTON, lambda e: self._search(True), next_btn)
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), close_btn)
        self.Bind(wx.EVT_TEXT_ENTER, lambda e: self._search(True), self.find_ctrl)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.find_ctrl.SetFocus()

    def _search(self, forward):
        self.frame.findText(self.find_ctrl.GetValue(), forward,
                            self.match_case.GetValue(), self.wrap.GetValue())

    def onClose(self, event):
        # Drop the frame's reference so onFind builds a fresh dialog next time.
        self.frame.search_dialog = None
        self.Destroy()


class FuzzyDialog(wx.Dialog):
    """Modeless palette: type a fuzzy query, pick a line, jump to it."""

    def __init__(self, parent):
        super().__init__(parent, title="Fuzzy Find", size=(560, 420))
        self.frame = parent
        self.result_lines = []
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.query_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.query_ctrl.SetHint("Fuzzy query (characters in order)")
        sizer.Add(self.query_ctrl, 0, wx.ALL | wx.EXPAND, 10)

        self.list_box = wx.ListBox(self)
        sizer.Add(self.list_box, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        self.status = wx.StaticText(self, label="")
        sizer.Add(self.status, 0, wx.ALL, 10)

        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        sizer.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(sizer)
        self.SetMinSize((420, 320))

        self.query_ctrl.Bind(wx.EVT_TEXT, self.onQuery)
        # Arrow keys are handled on the query box so focus can stay there and
        # the user can keep typing while moving through the results. Bind on
        # the controls themselves: EVT_KEY_DOWN is not a command event, so
        # `self.Bind(evt, handler, control)` would put the handler on the
        # dialog's chain and it would never fire (key events do not propagate).
        self.query_ctrl.Bind(wx.EVT_KEY_DOWN, self.onQueryKey)
        self.list_box.Bind(wx.EVT_KEY_DOWN, self.onListKey)
        self.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.accept(), self.list_box)
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), close_btn)
        self.Bind(wx.EVT_CLOSE, self.onClose)

        self.query_ctrl.SetValue(parent.fuzzy_query)
        self.refilter()
        self.query_ctrl.SetFocus()

    @staticmethod
    def _label(lineno, text):
        return "%5d  %s" % (lineno + 1, text.strip()[:120].replace('\t', '    '))

    def onQuery(self, event):
        self.frame.fuzzy_query = self.query_ctrl.GetValue()
        self.refilter()

    def refilter(self):
        query = self.query_ctrl.GetValue()
        results = fuzzyFilter(query, self.frame.ctrl1.GetValue().split('\n'))
        self.result_lines = [lineno for _score, lineno, _text in results]
        self.list_box.Set([self._label(lineno, text)
                           for _score, lineno, text in results])
        if self.result_lines:
            self.list_box.SetSelection(0)
        count = len(self.result_lines)
        self.status.SetLabel("%d match%s" % (count, "" if count == 1 else "es"))

    def _moveSelection(self, delta):
        count = self.list_box.GetCount()
        if not count:
            return
        index = self.list_box.GetSelection()
        if index == wx.NOT_FOUND:
            index = -1 if delta > 0 else count
        index = max(0, min(count - 1, index + delta))
        self.list_box.SetSelection(index)

    def onQueryKey(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_DOWN:
            self._moveSelection(1)
        elif key == wx.WXK_UP:
            self._moveSelection(-1)
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.accept()
        elif key == wx.WXK_ESCAPE:
            self.Close()
        else:
            event.Skip()

    def onListKey(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.accept()
            return
        if key == wx.WXK_ESCAPE:
            self.Close()
            return
        unicode_key = event.GetUnicodeKey()
        if 32 <= unicode_key < 127:
            # Focus can reach the list by clicking it; route typing back to the
            # query box so the user never has to click there manually. wxGTK
            # reports the physical (usually upper-case) letter in the key-down
            # event, so fold it down unless Shift or Caps Lock is active.
            char = chr(unicode_key)
            if char.isalpha() and not event.ShiftDown() and not wx.GetKeyState(wx.WXK_CAPITAL):
                char = char.lower()
            self.query_ctrl.SetFocus()
            self.query_ctrl.WriteText(char)
            return
        event.Skip()

    def accept(self):
        index = self.list_box.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self.result_lines):
            return
        self.frame.fuzzyGotoLine(self.result_lines[index])
        self.Close()

    def onClose(self, event):
        # Drop the frame's reference so Ctrl+Shift+F builds a fresh palette.
        self.frame.fuzzy_dialog = None
        self.Destroy()


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
