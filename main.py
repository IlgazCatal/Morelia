import wx
import logging as log

log.basicConfig(filename='error.log', level=log.INFO, format='%(asctime)s %(message)s')

FONT_SIZE = 24


class Frame1(wx.Frame):

    def __init__(self):
        super().__init__(parent=None, title='Morelia Text Editor')
        self.Centre()
        self.InitUI()
        self.SetIcon(wx.Icon("icon.png"))

    def InitUI(self):
        self.panel = wx.Window(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        font1 = wx.Font(FONT_SIZE, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False)
        self.ctrl1 = wx.TextCtrl(self.panel, value="", pos=(5, 50), size=wx.Size(100, 1080), style=wx.TE_MULTILINE)
        self.ctrl1.SetFont(font1)
        self.ctrl1.SetFocus()
        self.sizer.Add(self.ctrl1, 0, wx.ALL | wx.EXPAND, 0)
        self.panel.SetSizer(self.sizer)
        self.Show()
        self.screen_size = self.ctrl1.GetScreenRect()

        global caret
        caret = wx.Caret(self.panel,width=10,height=20)
        self.panel.SetCaret(caret)
        caret.Move(0,0)
        caret.Show()

        menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        fileItem = fileMenu.Append(wx.ID_EXIT, 'Quit', 'Quit application')
        menubar.Append(fileMenu, '&File')
        actionsMenu = wx.Menu()
        saveItem = actionsMenu.Append(wx.ID_SAVE, "Save", "Save file...")
        openItem = actionsMenu.Append(wx.ID_OPEN, "Open", "Open File...")
        viewMenu = wx.Menu()
        zoomInItem = viewMenu.Append(wx.ID_ZOOM_IN, "Zoom (+)", "Zoom in")
        zoomOutItem = viewMenu.Append(wx.ID_ZOOM_OUT, "Zoom (-)", "Zoom out")
        menubar.Append(actionsMenu, "&Actions")
        menubar.Append(viewMenu, "&View")

        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, self.OnQuit, fileItem, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnSaveAs, saveItem, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.openFile, openItem, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.onZoomIn, zoomInItem, id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, self.onZoomOut, zoomOutItem, id=wx.ID_ZOOM_OUT)
        self.Bind(wx.EVT_CHAR_HOOK, self.autoTab)

        shortcuts = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('Q'), wx.ID_EXIT),  # ctrl+q to exit
            (wx.ACCEL_CTRL, ord('S'), wx.ID_SAVE),  # ctrl+s to save
            (wx.ACCEL_CTRL, ord('O'), wx.ID_OPEN),  # ctrl+o to save
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
            insertion_point = self.ctrl1.GetInsertionPoint()
            text_upto_cursor = self.ctrl1.GetValue()[:insertion_point]

            lines = text_upto_cursor.split('\n')
            current_line = lines[-1] if lines else ''

            leading_whitespace = current_line[:len(current_line) - len(current_line.lstrip())]
            trimmed_line = current_line.rstrip()

            if trimmed_line.endswith(':'):
                tab = '    '
                self.ctrl1.SetInsertionPoint(insertion_point)
                self.ctrl1.WriteText('\n' + leading_whitespace + tab)
            else:
                self.ctrl1.SetInsertionPoint(insertion_point)
                self.ctrl1.WriteText('\n' + leading_whitespace)
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

    def encodeLatin1(self, string):
        string.encode("latin-1", 'ignore')

    def openFile(self, event):
        openFileDialog = wx.FileDialog(self, "Open txt files", "", "",
                                       "txt files (*.txt)|*.txt", wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if openFileDialog.ShowModal() == wx.ID_CANCEL:
            return

        path = openFileDialog.GetPath()
        print(path)
        with open(path, "r") as p:
            self.ctrl1.write(p.read())

    def OnSaveAs(self, event):

        with wx.FileDialog(self, "Save txt file", wildcard="txt files (*.txt)|*.txt",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            try:
                with open(pathname, "w+") as file:
                    contents = self.ctrl1.GetValue()
                    file.write(contents)
                    file.close()

            except IOError:
                wx.LogError("Cannot save current data in file '%s'." % pathname)
            except UnicodeEncodeError:
                self.encodeLatin1(contents)


if __name__ == '__main__':
    app = wx.App(False)
    frame = Frame1()
    app.MainLoop()
