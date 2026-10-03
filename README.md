# Morelia Text Editor

A small Python text editor built on wxPython and Scintilla. The whole application
is one file, [`main.py`](main.py) — 342 lines, no build step, no test suite.

## What it does

**Syntax colouring.** Python highlighting via Scintilla's Python lexer. Plain text is
white, keywords are red, and the built-in error names — `ValueError`, `TypeError`,
`KeyError`, `FileNotFoundError`, the rest of the exception hierarchy, 70 of them — are
yellow. The editor is black with dark grey window chrome.

**Error names come from the second word list.** They are derived from the running
interpreter (`ERROR_KEYWORDS` in `main.py`), so they track whatever Python you run
under, and they are handed to the lexer as word list 1 so they get their own style
instead of being coloured as ordinary identifiers.

**Autocomplete.** A popup offers Python keywords plus the builtins
(`keyword.kwlist | dir(builtins)`, 191 entries). It opens once you have typed at
least two characters of a word, filters as you keep typing, and stays shut inside
strings and comments. **Enter accepts the highlighted item** — Scintilla does not do
that on Return, so `autoTab` intercepts it. With no item highlighted, Enter still
starts a new line. *Actions → Autocomplete* opens the list on demand from any
prefix length.

**Bracket and quote pairing.** Typing `(`, `[`, `{`, `"`, `'` or `` ` `` inserts the
closing character and puts the caret between the two. Skipped inside strings and
comments. There is no type-over: typing the closing character yourself inserts a
second one, so `()` becomes `())`.

**Indentation.** Enter keeps the current line's leading whitespace. After a line
ending in `:` it adds one four-space level.

**Backspace deletes exactly one character.** Scintilla normally throws away a whole
indentation when the caret sits in leading whitespace; `autoTab` deletes the range
itself so one Backspace undoes one Tab press. An open completion is dismissed first.

**Files.** Open, Save, Save As. Ctrl+S writes straight back to the file you opened;
with nothing open yet it falls through to Save As. Files are read and written as
UTF-8, and the file dialogs filter on `*.py`. The window title follows the open file.

**Zoom.** Ctrl+1 and Ctrl+2 change the text size, floored at 6pt.

## Keyboard

| Shortcut | Action |
| --- | --- |
| `Ctrl+Q` | Quit |
| `Ctrl+S` | Save (Save As when nothing is open) |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+O` | Open |
| `Ctrl+1` | Zoom in |
| `Ctrl+2` | Zoom out |

## Running it

Requires Python 3.13 and wxPython 4.2.2 — the only third-party dependency, pinned in
[`requirements.txt`](requirements.txt). Run from the repository root:

```bash
./linux/run.sh
```

or, by hand:

```bash
source linux/activate.sh && python main.py
```

On Windows there are `win\setup.bat` and `win\run.bat` scripts, but both currently
assume the wrong working directory and fail; installing from `requirements.txt` and
running `python main.py` is the reliable route there. `AGENTS.md` has the details.

## Known rough edges

- The popup only opens for some prefixes — 27 of the 48 sampled — and typing the
  closing character of a pair does not skip over it.
- No member completion after `.`, and names defined in the open file are not offered.
- The file dialogs accept `*.py` only, with no "all files" option.
- `AGENTS.md` documents the Scintilla and wx behaviours behind all of this, including
  the traps that cost the most time (`WriteText` silently replaces the document,
  `STC_STYLE_DEFAULT` does not feed the lexer styles, backspace unindents).