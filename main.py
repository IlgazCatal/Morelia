import wx
import logging as log
import keyword

log.basicConfig(filename='error.log', level=log.INFO, format='%(asctime)s %(message)s')

FONT_SIZE = 24


class TextEditorPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.InitUI()

    def InitUI(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        font1 = wx.Font(FONT_SIZE, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False)

        self.ctrl1 = wx.TextCtrl(self, value="", style=wx.TE_MULTILINE)
        self.ctrl1.SetFont(font1)
        self.ctrl1.SetFocus()

        self.sizer.Add(self.ctrl1, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.sizer)



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

    def encodeLatin1(self, string):
        return string.encode("latin-1", 'ignore')


class NotebookApp(wx.Frame):

    def __init__(self):
        super().__init__(parent=None, title='Morelia Text Editor')
        self.Centre()
        self.InitUI()
        self.SetIcon(wx.Icon("icon.png"))

    def InitUI(self):
        self.notebook = wx.Notebook(self)
        self.AddNewTab("Untitled")

        menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        newTabItem = fileMenu.Append(wx.ID_NEW, "New Tab", "Create new tab")
        fileItem = fileMenu.Append(wx.ID_EXIT, 'Quit', 'Quit application')

        actionsMenu = wx.Menu()
        saveItem = actionsMenu.Append(wx.ID_SAVE, "Save", "Save file...")
        openItem = actionsMenu.Append(wx.ID_OPEN, "Open", "Open File...")
        viewMenu = wx.Menu()
        zoomInItem = viewMenu.Append(wx.ID_ZOOM_IN, "Zoom (+)", "Zoom in")
        zoomOutItem = viewMenu.Append(wx.ID_ZOOM_OUT, "Zoom (-)", "Zoom out")

        menubar.Append(fileMenu, '&File')
        menubar.Append(actionsMenu, "&Actions")
        menubar.Append(viewMenu, "&View")

        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self.OnQuit, fileItem, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnNewTab, newTabItem, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.OnSaveAs, saveItem, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.openFile, openItem, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, TextEditorPanel.onZoomIn, zoomInItem, id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, TextEditorPanel.onZoomOut, zoomOutItem, id=wx.ID_ZOOM_OUT)

        shortcuts = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('Q'), wx.ID_EXIT),  # ctrl+q to exit
            (wx.ACCEL_CTRL, ord('S'), wx.ID_SAVE),  # ctrl+s to save
            (wx.ACCEL_CTRL, ord('O'), wx.ID_OPEN),  # ctrl+o to save
            (wx.ACCEL_CTRL, ord('1'), wx.ID_ZOOM_IN),  # ctrl+1 to zoom in
            (wx.ACCEL_CTRL, ord('2'), wx.ID_ZOOM_OUT)  # ctrl+2 to zoom out
        ])

        self.SetAcceleratorTable(shortcuts)

        self.SetSize((1024, 768))
        self.Centre()
        self.Show()

    def AddNewTab(self, title):
        panel = TextEditorPanel(self.notebook)
        self.notebook.AddPage(panel, title)


    def OnNewTab(self, event):
        self.AddNewTab(f"Tab {self.notebook.GetPageCount() + 1}")

    def OnQuit(self, e):
        self.Close()

    def openFile(self, event):
        openFileDialog = wx.FileDialog(self, "Open txt files", "", "", "txt files (*.txt)|*.txt", wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if openFileDialog.ShowModal() == wx.ID_CANCEL:
            return

        path = openFileDialog.GetPath()
        current_panel = self.notebook.GetCurrentPage()

        with open(path, "r") as p:
            current_panel.ctrl1.SetValue(p.read())

    def OnSaveAs(self, event):
        current_panel = self.notebook.GetCurrentPage()

        with wx.FileDialog(self, "Save txt file", wildcard="txt files (*.txt)|*.txt",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            try:
                with open(pathname, "w+") as file:
                    contents = current_panel.ctrl1.GetValue()
                    file.write(contents)

            except IOError:
                wx.LogError("Cannot save current data in file '%s'." % pathname)
            except UnicodeEncodeError:
                current_panel.ctrl1.SetValue(current_panel.encodeLatin1(contents))

            self.notebook.SetPageText(self.notebook.GetSelection(),pathname)

    def autoTab(self, event):
        #TODO: rewrite this using wx.Notebook


        keycode = event.GetKeyCode()

        if keycode == wx.WXK_RETURN:
            pass
        else:
            event.Skip()

    def AutoHighlight(self,event):
        text = self.notebook.GetPageText(self.notebook.GetSelection())
        keywords = keyword.kwlist


if __name__ == '__main__':
    app = wx.App(False)
    frame = NotebookApp()
    app.MainLoop()
