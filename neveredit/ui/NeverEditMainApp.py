"""Main neveredit application class."""

from neveredit.util import Loggers
import logging
logger = logging.getLogger("neveredit")
from neveredit.util import check_versions

import sys
if sys.version_info[0] < 2 or (sys.version_info[0] == 2 and sys.version_info[1] < 3):
    print("Sorry, neveredit needs python >= 2.3. Download from python.org", file=sys.stderr)
    sys.exit()

import tempfile

try:
    import wx
    import wx.adv
    import wx.html
    import wx.stc
except:
    print("Sorry,You don't seem to have a proper installation of wxPython.", file=sys.stderr)
    print("Get one from wxpython.org.", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit()

from neveredit.game import Module
from neveredit.game import Area
from neveredit.game import ResourceManager
from neveredit.game.ChangeNotification import PropertyChangeListener
from neveredit.game.Placeable import Placeable
from neveredit.game.Script import Script
from neveredit.game.Conversation import Conversation
from neveredit.game.Factions import Factions,FactionStruct
from neveredit.game.Sound import SoundBP
from neveredit.game.Trigger import TriggerBP
from neveredit.game.Encounter import EncounterBP
from neveredit.ui import MapWindow
from neveredit.ui import ConversationWindow
from neveredit.ui import ModelWindow
from neveredit.ui import ScriptEditor
from neveredit.ui import HelpViewer
from neveredit.ui import ToolPalette
from neveredit.ui import PreferencesDialog
from neveredit.ui import Notebook
from neveredit.ui import PropertiesDialogs
from neveredit.ui import SoundControl
from neveredit.ui import WxUtils
from neveredit.ui.FactionGridWindow import FactionGridWindow,FactionGrid
from neveredit.ui.ShaderWindow import ShaderWindow
from neveredit.util import Preferences
from neveredit.util import Utils
from neveredit.util import neverglobals

#images
from neveredit.resources.images import neveredit_logo_jpg
from neveredit.resources.images import neveredit_logo_init_jpg

import os
import threading
import time
Set = set
import gettext

gettext.install('neveredit','translations')

class MySplashScreen(wx.adv.SplashScreen):
    def __init__(self,pic):
        wx.adv.SplashScreen.__init__(self, pic,
                                     wx.adv.SPLASH_CENTRE_ON_SCREEN|
                                     wx.adv.SPLASH_NO_TIMEOUT,
                                     4000, None, -1,
                                     style = wx.SIMPLE_BORDER
                                     |wx.FRAME_NO_TASKBAR
                                     |wx.STAY_ON_TOP)

##\mainpage
class NeverEditMainWindow(wx.Frame,PropertyChangeListener):
    '''<html><body>

    <table width="100%" border=0>
    <tr>
    <td valign="top">
    <h2>neveredit</h2>
    </td><td align="right" valign="top">
    <img src="neveredit.jpg"></td></tr></table>

    <p>Welcome to neveredit. Neveredit strives to be an editor for files
    from the Bioware game Neverwinter Nights. One day it may have all of
    the functionality of the Bioware windows tools, and maybe more. For
    now, I am striving to achieve basic editing functionality on
    non-Windows platforms. This means that this is alpha quality
    software, and will at the current stage likely do bad things
    to your files. I am happy to receive bug reports, but take no
    responsibility for any damages incurred through the use of this
    software.</p>

    <p>I write neveredit in my spare time, but I try to respond to
    all reports and questions I get about it. Before you write, please
    see if what you want to know is covered at the neveredit homepage,
    <i> http://neveredit.sourceforge.net </i>. The page is a wiki, so feel
    free to add documentation there as you see fit. The wiki also
    has instructions for developers as to how to check out the source
    and contribute.

    <ul>
    <li>Thanks to Torlack for his script compiler and file format documentation.</li>
    <li>Thanks to Damon Law (damonDesign.com) for the neveredit image.</li>
    <li>Thanks to Mickael Leduque for a number of significant feature implementations (factions, sounds...)</li>
    <li>Thanks to Alan Schmitt for the beginnings of a conversation editor.</li>
    <li>Thanks to Sylvan_Elf for the neveredit splash screen.</li>
    <li>Thanks to the NWN Lexicon folks for letting me include the lexicon.</li>
    </ul>
    <p>Have fun,<br><i>sumpfork</i></p>

    </body></html>'''

    def _get_env_float(self, key, default):
        try:
            return float(os.environ.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _scale_size(self, width, height):
        return (int(width * self.uiScale), int(height * self.uiScale))

    def _apply_font_delta(self, window, delta):
        if not window:
            return
        try:
            font = window.GetFont()
            if font and font.IsOk():
                point_size = font.GetPointSize()
                if point_size > 0:
                    font.SetPointSize(max(6, point_size + delta))
                    window.SetFont(font)
        except Exception:
            return
        for child in window.GetChildren():
            self._apply_font_delta(child, delta)
    
    def __init__(self,parent,id,title):
        '''Constructor. Sets up static controls and menus.'''
        self.uiScale = max(1.0, self._get_env_float('NEVEREDIT_UI_SCALE', 1.25))
        self.uiFontDelta = int(self._get_env_float('NEVEREDIT_UI_FONT_DELTA', 2))
        if not wx.Image.FindHandler(wx.BITMAP_TYPE_PNG):
            wx.InitAllImageHandlers()
        self.splash = MySplashScreen(neveredit_logo_jpg.getBitmap())
        self.splash.Bind(wx.EVT_CLOSE, self.OnCloseSplash)
        
        self.splash.Show(True)

        wx.Frame.__init__(self,parent,-1,title,size=self._scale_size(1000,750))

        self.doInit = False
        self.fname = None
        self.doRead = False
        self.fileChanged = False

        self.map = None
        self.model = None
        self.helpviewer = None
        
        self.idToTreeItemMap = {}
        self.detachedMap = {}

        self.threadAlive = False
        self._restoringWindowState = False
        self._windowStates = {}
    
        self.selectThisItem = None
        
        #status bar
        self.CreateStatusBar(2)
        self.SetStatusWidths([-1,150])
        self.SetStatusText(_("Welcome to neveredit..."))
        self.statusProgress = wx.Gauge(self.GetStatusBar(),-1,100)
        self.setProgress(0)
                
        splitter_style = getattr(wx, 'NO_3D', 0) | getattr(wx, 'SP_3D', 0)
        splitter = wx.SplitterWindow(self,-1,style=splitter_style)
        self.splitter = splitter
        
        tID = wx.NewId()
        self.tree = wx.TreeCtrl(splitter,tID,wx.DefaultPosition,\
                               wx.DefaultSize,\
                               wx.TR_HAS_BUTTONS)
        # Apply dark-mode-aware colors to tree control
        self.tree.SetBackgroundColour(WxUtils.getPanelBackgroundColour(self.tree))
        self.tree.SetForegroundColour(WxUtils.getTextColour(self.tree))
        self.selectedTreeItem = None
        self.lastAreaItem = None
        
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.treeSelChanged)
        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.treeItemExpanding)
        self.tree.Bind(wx.EVT_TREE_ITEM_COLLAPSED, self.treeItemCollapsed)
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnTreeItemRightClick)

        self.notebook = Notebook.Notebook(splitter)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,self.OnNotebookPageChanged,
                  self.notebook)
        
        minw, minh = self._scale_size(750, 280)
        self.SetSizeHints(minW=minw,minH=minh)
        
        splitter.SplitVertically(self.tree,self.notebook,int(220 * self.uiScale))
        splitter.SetMinimumPaneSize(100)

        self.welcome = wx.html.HtmlWindow(self.notebook,-1,self._scale_size(520,520))
        self.notebook.AddPage(self.welcome,_("Welcome to neveredit"),'welcome')
        try:
            self.welcome.SetPage(self.__doc__)
        except:
            pass #html window likes to throw exceptions

        helps = [file for file in os.listdir(os.getcwd())
                 if (file[:5] == 'help_' and file[-4:] == '.zip')]
        self.helpviewer = HelpViewer.makeHelpViewer(helps,tempfile.gettempdir())

        self.toolPalette = None
        self.props = None
        self.shaderWindow = None
        
        self.setupMenus()
        
        self.scriptEditorFrame = wx.Frame(self,-1,"Script Editor",(int(100 * self.uiScale),int(100 * self.uiScale)))
        self.scriptEditor = ScriptEditor.ScriptEditor(self.scriptEditorFrame,-1)
        self.scriptEditorFrame.SetSize(self._scale_size(900,650))
        self.scriptEditor.setHelpViewer(self.helpviewer)
        ScriptEditor.EVT_SCRIPTADD(self.scriptEditor,self.OnScriptAdded)
        self.scriptEditorFrame._restored_state = False

        self.showScriptEditorFix = False

        self.scriptEditorFrame.Bind(wx.EVT_CLOSE, self.OnCloseWindow)

        self.readingERF = False
        self.RMThread = None

        self.prefs = None
        self.loadPrefs()

        self.ID_TIMER = 200
        self.timer = wx.Timer(self,self.ID_TIMER)
        self.Bind(wx.EVT_TIMER, self.kick, self.timer)
        self.timer.Start(200)
        self.Bind(wx.EVT_IDLE, self.idle)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MOVE, self.OnMove)

        tmp = self.splash
        self.splash = MySplashScreen(neveredit_logo_init_jpg.getBitmap())
        self.splash.Show(True)
        if tmp:
            tmp.Show(False)
            tmp.Destroy()

        # Scale up default text/UI density for modern displays.
        self._apply_font_delta(self, self.uiFontDelta)

    def initResourceManager(self):
        '''Initialize the resource manager object from the app dir path.
        Fails with a dialog warning if path does not exit. If it does
        exist, disables interface and starts the initialization thread.'''
        if not os.path.exists(self.prefs['NWNAppDir']):
            if self.splash:
                self.splash.Show(False)
                self.splash.Destroy()
            dlg = wx.MessageDialog(self,_('Directory does not exist: ')
                                  + self.prefs['NWNAppDir'] +
                                  '\n' + _('Please reset in Preferences'),
                                  _('Non-existent App Dir'),wx.OK|wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            self.Show(True)
            self._restorePersistedWindowState()
        else:
            self.Enable(False)
            self.SetStatusText(_("Initializing from NWN Application Directory..."))
            self.RMThread = threading.Thread(target=self.doInitResourceManager)
            self.threadAlive = True
            self.RMThread.start()

    def doInitResourceManager(self):
        '''This is the thread body for initializing the resource manager.Do
        not call any function that
        changes the interface from this method. You need to set a flag and call
        it from the main app thread, as otherwise things will get screwed up on
        linux.'''
        self.resourceManager = ResourceManager.ResourceManager()
        neverglobals.setResourceManager(self.resourceManager)
        self.resourceManager.setProgressDisplay(self)
        self.resourceManager.scanGameDir(self.prefs['NWNAppDir'])
        Script.init_nwscript_keywords()
        
    def setProgress(self,prog):
        '''Implementing the progress display interface'''
        self.progress = prog
        if not self.threadAlive and self.progress:
            self.statusProgress.Show(True)
            self.statusProgress.SetValue(int(self.progress))
            wx.YieldIfNeeded()

    def setStatus(self,s):
        '''Implementing the progress display interface'''
        self.SetStatusText(s)
        # Do NOT call wx.YieldIfNeeded() here.  setStatus() is called from
        # MapWindow.preprocess(), which runs inside a DrawGLScene() paint
        # handler.  Pumping the event loop from within a paint callback allows
        # stale wx.Timer objects to fire against already-freed C++ event
        # handlers (wxEvtHandler PAC fault / SIGSEGV on ARM).  Status-bar text
        # is cosmetic; the display will refresh at the next natural event loop
        # iteration without an explicit yield.
        
    def showScriptEditor(self):
        self.scriptEditorFrame.Show(True)
        if not self.scriptEditorFrame._restored_state:
            self._restoreWindowState(self.scriptEditorFrame, 'ScriptEditorState', self._scale_size(520, 360))
            self._trackWindowState(self.scriptEditorFrame, 'ScriptEditorState', self._scale_size(520, 360))
            self.scriptEditorFrame._restored_state = True
        self.scriptEditorFrame.Raise()

    def showToolPalette(self):
        if not self.toolPalette:
            self.toolPalette = ToolPalette.ToolFrame()
            self.toolPalette._restored_state = False
            self.toolPalette.GetToolBar().Enable(False)
            self._apply_font_delta(self.toolPalette, self.uiFontDelta)
            self.Bind(wx.EVT_CLOSE,self.OnCloseToolPalette,self.toolPalette)
        self.toolPalette.Show(True)
        if not self.toolPalette._restored_state:
            self._restoreWindowState(self.toolPalette, 'ToolPaletteState', (220, 320))
            self._trackWindowState(self.toolPalette, 'ToolPaletteState', (220, 320))
            self.toolPalette._restored_state = True
            if self.map:
                ToolPalette.EVT_TOOLSELECTION(self.toolPalette,
                                              self.map.toolSelected)
        self.toolPalette.Raise()

    def showShaderWindow(self):
        if not self.shaderWindow:
            self.shaderWindow = ShaderWindow(self)
            self.shaderWindow._restored_state = False
            self._apply_font_delta(self.shaderWindow, self.uiFontDelta)
            self.shaderWindow.Bind(wx.EVT_CLOSE, self.OnCloseShaderWindow)
        self._connectShaderWindow()
        self.shaderWindow.Show(True)
        if not self.shaderWindow._restored_state:
            self._restoreWindowState(self.shaderWindow, 'ShaderWindowState', (340, 520))
            self._trackWindowState(self.shaderWindow, 'ShaderWindowState', (340, 520))
            self.shaderWindow._restored_state = True
        self.shaderWindow.Raise()

    def _connectShaderWindow(self):
        if not self.shaderWindow:
            return
        shader_manager = None
        if self.map and hasattr(self.map, 'shader_manager'):
            shader_manager = self.map.shader_manager
        self.shaderWindow.set_shader_manager(shader_manager)
        self.shaderWindow.set_on_shader_changed_callback(self._onShaderSettingsChanged)

    def _applyShaderPreferences(self, shader_manager=None):
        if shader_manager is None:
            if not self.map or not hasattr(self.map, 'shader_manager'):
                return
            shader_manager = self.map.shader_manager
        shader_manager.configure(
            enabled_shaders=self.prefs['EnabledShaders'],
            current_shader=self.prefs['CurrentShader'],
            parameter_values=self.prefs['ShaderParameters'],
        )

    def _rememberShaderPreferences(self):
        if not self.map or not hasattr(self.map, 'shader_manager'):
            return
        state = self.map.shader_manager.serialize_state()
        self.prefs['EnabledShaders'] = [key for key in state['enabled_shaders'] if key != 'None']
        self.prefs['CurrentShader'] = state['current_shader']
        self.prefs['ShaderParameters'] = state['parameter_values']

    def _onShaderSettingsChanged(self, _shader_key=None):
        self._rememberShaderPreferences()
        if self.map:
            self.map.redrawRequested = True
            try:
                self.map.Refresh(False)
            except Exception:
                pass
    
    def OnCloseShaderWindow(self, event):
        if self.shaderWindow:
            self.shaderWindow.Show(False)
        if event and event.CanVeto():
            event.Veto()

    def setupMenus(self):
        '''set up the app menu bar'''
        self.ID_ABOUT = wx.NewId()
        self.ID_NEW_MODULE = wx.NewId()
        self.ID_OPEN  = wx.NewId()
        self.ID_SAVE  = wx.NewId()
        self.ID_SAVEAS = wx.NewId()
        self.ID_EXIT  = wx.NewId()
        self.ID_HELP = wx.NewId()
        self.ID_PREFS = wx.NewId()
        self.ID_ADD_ERF = wx.NewId()
        self.ID_ADD_RESOURCE = wx.NewId()
        self.ID_DETACH = wx.NewId()
        self.ID_PALETTE_WINDOW_MITEM = wx.NewId()
        self.ID_MAP_LAYER_WINDOW_MITEM = wx.NewId()
        self.ID_SCRIPT_WINDOW_MITEM = wx.NewId()
        self.ID_MAIN_WINDOW_MITEM = wx.NewId()
        self.ID_SHADER_WINDOW_MITEM = wx.NewId()
        self.ID_CUT = wx.NewId()
        self.ID_COPY = wx.NewId()
        self.ID_PASTE = wx.NewId()
        self.ID_DEL = wx.NewId()
        self.ID_BUILD_MODULE = wx.NewId()
        self.ID_TEST_MODULE = wx.NewId()
        self.ID_MODULE_PROPS = wx.NewId()
        self.ID_AREA_PROPS = wx.NewId()
        self.ID_TREE_AREA_PROPS = wx.NewId()
        self.ID_AREA_WIZARD = wx.NewId()

        if Utils.iAmOnMac():
            if hasattr(wx, 'App_SetMacExitMenuItemId'):
                wx.App_SetMacExitMenuItemId(self.ID_EXIT)
                wx.App_SetMacPreferencesMenuItemId(self.ID_PREFS)
                wx.App_SetMacAboutMenuItemId(self.ID_ABOUT)
            else:
                wx.App.SetMacExitMenuItemId(self.ID_EXIT)
                wx.App.SetMacPreferencesMenuItemId(self.ID_PREFS)
                wx.App.SetMacAboutMenuItemId(self.ID_ABOUT)

        #menus
        self.filemenu = wx.Menu()
        self.filemenu.Append(self.ID_NEW_MODULE, '&' + _('New Module...') + '\tCtrl+N',
                     _('Create a new blank module'))
        self.filemenu.Append(self.ID_OPEN, '&' + _('Open') + '\tCtrl+O',
                             _("Open a File"))
        self.filemenu.Append(self.ID_ADD_ERF, _('Add in ERF File...'),
                             _("Add all entries of another ERF file"))
        self.filemenu.Append(self.ID_ADD_RESOURCE, _('Add in resource file...'),
                             _("Add an NWN resource into module"))
        self.filemenu.AppendSeparator()
        self.filemenu.Append(self.ID_SAVE, '&' + _('Save') + '\tCtrl+S',
                             _("Save File"))
        self.filemenu.Append(self.ID_SAVEAS, '&' + _('Save As...') +
                             '\tShift+Ctrl+S',
                             _("Save File under a new name"))
        self.filemenu.AppendSeparator()
        self.filemenu.Append(self.ID_AREA_WIZARD,
                             _('Area Wizard...'),
                             _('Create a new blank area in this module'))
        self.filemenu.Enable(self.ID_AREA_WIZARD, False)
        self.filemenu.Append(self.ID_MODULE_PROPS,
                             _('Module Properties...'),
                             _('Edit module name, description, HAKs and event scripts'))
        self.filemenu.Enable(self.ID_MODULE_PROPS, False)
        if not Utils.iAmOnMac():
            self.filemenu.Append(self.ID_EXIT,_('E&xit') + '\tAlt-X',
                                 _("Quit neveredit"))
        self.filemenu.Enable(self.ID_SAVE,False)
        self.filemenu.Enable(self.ID_SAVEAS,False)
        self.filemenu.Enable(self.ID_ADD_ERF,False)
        self.filemenu.Enable(self.ID_ADD_RESOURCE,False)

        self.filehistory = wx.FileHistory()
        self.filehistory.UseMenu(self.filemenu)
        self.Bind(wx.EVT_MENU_RANGE, self.OnFileHistory,
              id=wx.ID_FILE1, id2=wx.ID_FILE9)

        self.editmenu = wx.Menu()
        self.editmenu.Append(self.ID_CUT, '&'+_('Cut'), _('cut'))
        self.editmenu.Append(self.ID_COPY, '&'+_('Copy'), _('copy'))
        self.editmenu.Append(self.ID_PASTE, '&'+_('Paste'), _('paste'))
        self.sep1=self.editmenu.AppendSeparator()
        self.editmenu.Append(self.ID_DEL, '&'+_('Delete'), _('del'))
        self.sep2=self.editmenu.AppendSeparator()
        self.editmenu.Append(self.ID_AREA_PROPS,
                             _('Area Properties...'),
                             _('Edit lighting, sound and scripts for the current area'))
        self.editmenu.Enable(self.ID_AREA_PROPS, False)
        self.editmenu.Append(self.ID_PREFS,'&' + _('Preferences...'),
                             _('neveredit preferences dialog'))
        self.Bind(wx.EVT_MENU, self.OnDelete, id=self.ID_DEL)
        self.Bind(wx.EVT_MENU, self.OnCut, id=self.ID_CUT)
        self.Bind(wx.EVT_MENU, self.OnCopy, id=self.ID_COPY)
        self.Bind(wx.EVT_MENU, self.OnPaste, id=self.ID_PASTE)
        self.editmenu.Bind(wx.EVT_MENU_OPEN, self.OnEditMenu)
        self.windowmenu = wx.Menu()
        self.windowmenu.Append(self.ID_MAIN_WINDOW_MITEM, _('Main Window'))
        self.windowmenu.Append(self.ID_MAP_LAYER_WINDOW_MITEM, _('Map Layer'))
        self.windowmenu.Append(self.ID_PALETTE_WINDOW_MITEM, _('Palette Window'))
        self.windowmenu.Append(self.ID_SCRIPT_WINDOW_MITEM, _('Script Editor'))
        self.windowmenu.Append(self.ID_SHADER_WINDOW_MITEM, _('Shaders'))

        self.toolsmenu = wx.Menu()
        self.toolsmenu.Append(self.ID_BUILD_MODULE, _('Build Module'),
                      _('Compile and validate module resources (placeholder)'))
        self.toolsmenu.Append(self.ID_TEST_MODULE, _('Test Module\tF9'),
                      _('Launch module test workflow (placeholder)'))
        self.toolsmenu.AppendSeparator()
        self.toolsmenu.Append(self.ID_SHADER_WINDOW_MITEM, _('Shaders...'),
                  _('Open the shader selection window'))
        
        helpmenu = wx.Menu()
        helpmenu.Append(self.ID_ABOUT, '&' + _('About...'), _("About neveredit"))
        helpmenu.Append(self.ID_HELP,'&'+ _('neveredit Help'), _("neveredit Help"))
        
        menuBar = wx.MenuBar()
        menuBar.Append(self.filemenu,"&" + _("File"))
        menuBar.Append(self.editmenu, "&" + _("Edit"))
        menuBar.Append(self.windowmenu, "&" + _("Window"))
        menuBar.Append(self.toolsmenu, "&" + _("Tools"))
        menuBar.Append(helpmenu, "&" + _("Help"))
        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_MENU, self.openFile, id=self.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnNewModule, id=self.ID_NEW_MODULE)
        self.Bind(wx.EVT_MENU, self.addERFFile, id=self.ID_ADD_ERF)
        self.Bind(wx.EVT_MENU, self.addResourceFile, id=self.ID_ADD_RESOURCE)
        self.Bind(wx.EVT_MENU, self.saveFile, id=self.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.saveFileAs, id=self.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self.about, id=self.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.OnPreferences, id=self.ID_PREFS)
        self.Bind(wx.EVT_MENU, self.exit, id=self.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.help, id=self.ID_HELP)
        self.Bind(wx.EVT_MENU, self.OnBuildModule, id=self.ID_BUILD_MODULE)
        self.Bind(wx.EVT_MENU, self.OnTestModule, id=self.ID_TEST_MODULE)
        self.Bind(wx.EVT_MENU, self.OnAreaWizard, id=self.ID_AREA_WIZARD)
        self.Bind(wx.EVT_MENU, self.OnModuleProperties, id=self.ID_MODULE_PROPS)
        self.Bind(wx.EVT_MENU, self.OnAreaProperties, id=self.ID_AREA_PROPS)
        self.Bind(wx.EVT_MENU, self.windowMenu, id=self.ID_MAIN_WINDOW_MITEM)
        self.Bind(wx.EVT_MENU, self.windowMenu, id=self.ID_MAP_LAYER_WINDOW_MITEM)
        self.Bind(wx.EVT_MENU, self.windowMenu, id=self.ID_SCRIPT_WINDOW_MITEM)
        self.Bind(wx.EVT_MENU, self.windowMenu, id=self.ID_PALETTE_WINDOW_MITEM)
        self.Bind(wx.EVT_MENU, self.windowMenu, id=self.ID_SHADER_WINDOW_MITEM)
        
        #wx.EVT_MENU(self,self.ID_DETACH,self.OnDetach)

    def OnPaste(self,event):
        '''Perform a paste operation'''
        inFocus = wx.Window.FindFocus()
        if not inFocus:            
            return
        if inFocus == self.scriptEditor.getCurrentEditor():
            self.scriptEditor.OnPaste(event)        
        if not wx.TheClipboard.Open():
            logger.error("Can't open system clipboard")
            return
        data = wx.TextDataObject()
        hasData = wx.TheClipboard.GetData(data)

        if hasData and data.GetText() and hasattr(inFocus,'Replace'):
            inFocus.Replace(inFocus.GetSelection()[0],inFocus.GetSelection()[1],data.GetText())
        wx.TheClipboard.Close()

    def OnCopy(self,event):
        '''Perform a copy operation'''
        selection,inFocus = self.getCurrentTextSelection()
        if inFocus == self.scriptEditor.getCurrentEditor():
            self.scriptEditor.OnCopy(event)
        if selection:
            if not wx.TheClipboard.Open():
                logger.error("Can't open system clipboard")
                return
            data = wx.TextDataObject(selection)
            wx.TheClipboard.AddData(data)
            wx.TheClipboard.Close()        

    def OnDelete(self,event):
        '''Perform a delete operation'''
        selection,inFocus = self.getCurrentTextSelection()
        if inFocus == self.scriptEditor.getCurrentEditor():
            self.scriptEditor.OnDelete(event)
        if selection and hasattr(inFocus,'Remove'):
            inFocus.Remove(inFocus.GetSelection()[0],inFocus.GetSelection()[1])

    def OnCut(self,event):
        '''Peform a cut operation'''
        selection,inFocus = self.getCurrentTextSelection()
        if inFocus == self.scriptEditor.getCurrentEditor():
            self.scriptEditor.OnCut(event)
        if selection:
            if not wx.TheClipboard.Open():
                logger.error("Can't open system clipboard")
                return
            data = wx.TextDataObject(selection)
            wx.TheClipboard.AddData(data)
            wx.TheClipboard.Close()
            if hasattr(inFocus,'Remove'):
                inFocus.Remove(inFocus.GetSelection()[0],inFocus.GetSelection()[1])
            
    def getCurrentTextSelection(self):
        inFocus = wx.Window.FindFocus()
        if not inFocus:
            return None,None
        selection = None
        if hasattr(inFocus,'GetStringSelection'):
            selection = inFocus.GetStringSelection()
        return selection,inFocus
    
    def OnEditMenu(self,event):
        self.editmenu.Enable(self.ID_CUT,False)
        self.editmenu.Enable(self.ID_COPY,False)
        self.editmenu.Enable(self.ID_PASTE,False)
        self.editmenu.Enable(self.ID_DEL,False)

        selection,inFocus = self.getCurrentTextSelection()
        if not inFocus:
            return
        if inFocus == self.scriptEditor.getCurrentEditor():
            self.scriptEditor.setEditMenu(self.editmenu)
            self.scriptEditor.OnEditMenu(event,self)
        
        # If we have highlighted text, enable the appropriate options
        if selection:
            self.editmenu.Enable(self.ID_COPY,True)
            if hasattr(inFocus,'WriteText'):
                self.editmenu.Enable(self.ID_CUT,True)
                self.editmenu.Enable(self.ID_DEL,True)

        if not wx.TheClipboard.Open():
            logger.error("Can't open system clipboard")
            return
        data = wx.TextDataObject()
        hasData = wx.TheClipboard.GetData(data)

        # if we can paste, enable the option
        if hasData and data.GetText() and hasattr(inFocus,'WriteText'):
            self.editmenu.Enable(self.ID_PASTE,True)

        wx.TheClipboard.Close()
        
    def treeFromERF(self):
        '''Make a new tree control from the erf file currently
        associated with the app. Does so in a new thread.'''
        self.selectedTreeItem = None
        self.tree.DeleteAllItems()
        self.treeRoot = self.tree.AddRoot(self.module.getName())
        self.tree.SetItemData(self.treeRoot,self.module)
        self._applyTreeItemStyle(self.treeRoot)
        wx.BeginBusyCursor()
        self.doTreeFromERF()
        self.treeFromERFDone()
        wx.EndBusyCursor()

    def doTreeFromERF(self):
        '''The thread body for loading an ERF file.
        Do not call any function that changes the interface
        from this method. You need to set a flag and call
        it from the main app thread, as otherwise things will get screwed up on
        linux.'''
        self.module.setProgressDisplay(self)
        self.areas = self.module.getAreas()

    def setFileChanged(self,fc=True):
        '''Call this when the loaded file has changed
        (someone used a control, usually).'''
        self.fileChanged = fc
        self.filemenu.Enable(self.ID_SAVE,fc)
        
    def treeFromERFDone(self):
        '''This gets called when we finish loading a new ERF file.
        It gets the interface into its final state and cleans up a bit.'''
        # Once a module is loaded, keep the notebook focused on editing pages.
        if self.notebook.getPageByTag('welcome'):
            self.notebook.deletePageByTag('welcome')
        if self.notebook.getPageByTag('props'):
            self.notebook.deletePageByTag('props')
        self.props = None

        self.setStatus("Preparing user interface...")
        self.areaRoot = self.tree.AppendItem(self.treeRoot,'Areas')
        self._applyTreeItemStyle(self.areaRoot)
        area_values = list(self.areas.values())
        area_total = len(area_values)
        area_start = time.time()
        for idx, area in enumerate(area_values, 1):
            if area_total > 0:
                elapsed = max(0.001, time.time() - area_start)
                rate = float(idx - 1) / elapsed if idx > 1 else 0.0
                remaining = (area_total - (idx - 1)) / rate if rate > 0 else 0.0
                mins, secs = divmod(max(0, int(remaining)), 60)
                eta = "%02d:%02d" % (mins, secs)
                self.setStatus("Building area tree %d/%d (ETA %s)" %
                               (idx - 1, area_total, eta))
                self.setProgress((float(idx - 1) / float(area_total)) * 100.0)
            self.makeAreaItem(self.areaRoot,area)
            wx.YieldIfNeeded()
        self.setProgress(0)
        self.scriptRoot = self.tree.AppendItem(self.treeRoot,_('Scripts'))
        self.addScripts()
        self.conversationRoot = self.tree.AppendItem(self.treeRoot,_('Conversations'))
        self.addConversations()
        self.factionRoot = self.tree.AppendItem(self.treeRoot,_('Factions'))
        self.addFactions()
        self.soundBPRoot = self.tree.AppendItem(self.treeRoot, _('Sounds'))
        self.addSoundBlueprints()
        self.triggerBPRoot = self.tree.AppendItem(self.treeRoot, _('Triggers'))
        self.addTriggerBlueprints()
        self.encounterBPRoot = self.tree.AppendItem(self.treeRoot, _('Encounters'))
        self.addEncounterBlueprints()
        self.notebook.Refresh()
        self.SetStatusText(_("Read ") + self.fname)
        self.filemenu.Enable(self.ID_SAVEAS,True)
        self.filemenu.Enable(self.ID_ADD_ERF,True)
        self.filemenu.Enable(self.ID_ADD_RESOURCE,True)
        self.filemenu.Enable(self.ID_AREA_WIZARD, True)
        self.filemenu.Enable(self.ID_MODULE_PROPS, True)
        self.fileChanged = False
        self.tree.Expand(self.treeRoot)
        self.tree.UnselectAll()
        self.tree.SelectItem(self.treeRoot)
        self.setStatus("Ready.")
        
    def OnFileHistory(self,event):
        '''Callback for someone selecting a file history menu item.'''
        fileNum = event.GetId() - wx.ID_FILE1
        self.readFile(self.filehistory.GetHistoryFile(fileNum))
        
    def OnSize(self,event):
        rect = self.GetStatusBar().GetFieldRect(1)
        self.statusProgress.SetPosition((rect.x+1,rect.y+1))
        self.statusProgress.SetSize((rect.width-2,rect.height-2))
        self._rememberWindowState(self, 'MainWindowState')
        event.Skip()

    def OnMove(self,event):
        self._rememberWindowState(self, 'MainWindowState')
        event.Skip()

    def addScripts(self):
        '''Add the scripts contained in our module to the interface.'''
        self.tree.DeleteChildren(self.scriptRoot)
        scripts = self.module.getScripts()
        scriptNames = list(scripts.keys())
        scriptNames.sort()
        for s in scriptNames:
            name = s.split('.')[0]
            scriptItem = self.tree.AppendItem(self.scriptRoot,name)
            scripts[s].setNWNDir(self.prefs['NWNAppDir'])
            scripts[s].setModule(self.fname)
            self.tree.SetItemData(scriptItem,scripts[s])

    def addConversations(self):
        '''Add the conversations contained in our module to the interface.'''

        self.tree.DeleteChildren(self.conversationRoot)
        conversations = self.module.getConversations()
        conversationNames = list(conversations.keys())
        conversationNames.sort()
        for c in conversationNames:
            name = c.split('.')[0]
            conversationItem = self.tree.AppendItem(self.conversationRoot,name)
            self.tree.SetItemData(conversationItem,Conversation(c,conversations[c]))

    def addFactions(self):
        '''Add the factions contained in our module to the interface'''
        self.tree.DeleteChildren(self.factionRoot)
        factions = self.module.getFactions()
        factionNames = list(factions.keys())
        factionNames.sort()
        for f in factionNames:
            factionItem = self.tree.AppendItem(self.factionRoot,f)
            self.tree.SetItemData(factionItem,factions[f])

    def addSoundBlueprints(self):
        '''Add module-level sound blueprints (.UTS) to the tree.'''
        self.tree.DeleteChildren(self.soundBPRoot)
        bps = self.module.getSoundBlueprints()
        for name in sorted(bps.keys()):
            try:
                bp = SoundBP(bps[name].getRoot())
            except Exception:
                bp = None
            if bp is None:
                continue
            item = self.tree.AppendItem(self.soundBPRoot, bp.getName() or name)
            self.tree.SetItemData(item, bp)

    def addTriggerBlueprints(self):
        '''Add module-level trigger blueprints (.UTT) to the tree.'''
        self.tree.DeleteChildren(self.triggerBPRoot)
        bps = self.module.getTriggerBlueprints()
        for name in sorted(bps.keys()):
            try:
                bp = TriggerBP(bps[name].getRoot())
            except Exception:
                bp = None
            if bp is None:
                continue
            item = self.tree.AppendItem(self.triggerBPRoot, bp.getName() or name)
            self.tree.SetItemData(item, bp)

    def addEncounterBlueprints(self):
        '''Add module-level encounter blueprints (.UTE) to the tree.'''
        self.tree.DeleteChildren(self.encounterBPRoot)
        bps = self.module.getEncounterBlueprints()
        for name in sorted(bps.keys()):
            try:
                bp = EncounterBP(bps[name].getRoot())
            except Exception:
                bp = None
            if bp is None:
                continue
            item = self.tree.AppendItem(self.encounterBPRoot, bp.getName() or name)
            self.tree.SetItemData(item, bp)

    def init(self):
        '''Schedule the the app init routine.'''
        self.doInit = True

    def kick(self,event):
        '''kick the idle func even without events'''
        wx.WakeUpIdle()

    def idle(self,event):
        '''Called on idle events. This is where the interface updates for
        other threads happen (they cannot update the interface themselves).
        For example, this handles updates to the progress bar and
        finishing up ERF file loading.'''
        if self.doInit:
            self.doInit = False
            self.initResourceManager()
        if self.RMThread and not self.RMThread.is_alive() and self.doRead:
            try:
                self.readFile(self.fname)
            except:
                pass
            self.doRead = False
        if self.RMThread and not self.RMThread.is_alive():
            if self.splash:
                self.splash.Show(False)
                self.splash.Destroy()
            self.showToolPalette()
            self.Show(True)
            self._restorePersistedWindowState()
            self.Enable(True)
            self.SetStatusText(_("Welcome to neveredit..."))
            self.RMThread = None
            self.threadAlive = False
        if self.progress > 0:
            self.setProgress(self.progress)
            self.statusProgress.Show(True)
            self.statusProgress.SetValue(int(self.progress))
        else:
            self.statusProgress.Show(False)
        if self.showScriptEditorFix:
            self.showScriptEditor();
            self.showScriptEditorFix = False
        if self.selectThisItem != None:
            if callable(self.selectThisItem):
                logger.warning('ignoring callable selectThisItem value: %r', self.selectThisItem)
            else:
                self.selectTreeItemById(self.selectThisItem)
            self.selectThisItem = None

    def selectTreeItemById(self,oid):
        '''try to find an item in the current module by object id and
        select the corresponding tree item'''
        if callable(oid):
            logger.warning('cannot select tree item for callable id value: %r', oid)
            return
        item = self.idToTreeItemMap.get(oid,None)
        if item:
            self.tree.EnsureVisible(item)
            self.tree.SelectItem(item)
        else:
            logger.warning('cannot find tree item with id %r', oid)
        
    def OnScriptAdded(self,event):
        """event handler for new script being added to module"""
        self.scriptEditor.addChangeListener(self.setFileChanged)
        data = self.getSelectedTreeItemData()
        reselect = False
        if data and data.__class__ == Script:
            self.unselectTreeItem()
            reselect = True
        self.addScripts()
        if reselect:
            self.tree.SelectItem(self.scriptRoot)

    def OnMapSelection(self,event):
        '''handle a map window selection event'''
        self.selectTreeItemById(event.getSelectedId())

    def OnMapMove(self,event):
        '''handle a map movement event'''
        self.setFileChanged(True)

    def OnMapThingAdded(self,event):
        '''handle the addition of a new item to the map'''
        self.unselectTreeItem()
        self.tree.DeleteChildren(self.lastAreaItem)
        self.subtreeFromArea(self.lastAreaItem,self.map.getArea())
        selected_id = event.getSelectedId()
        if selected_id is not None:
            self.selectThisItem = selected_id
        else:
            self.selectThisItem = None
        # removing this line prevents a crash - good as a *temporary*
        # fix, but the crash should be investigated
        # this also cause functionality loss (auto-selection of the thing added
        self.setFileChanged(True)

    def unselectTreeItem(self):
        """unselect the currently selected tree item."""
        self.maybeApplyPropControlValues()
        self.selectedTreeItem = None
        self.tree.Unselect()
        
    def makeAreaItem(self,item,area):
        '''Create the parent tree item for an area'''
        areaItem = self.tree.AppendItem(item,area.getName())
        self.tree.SetItemHasChildren(areaItem,True)
        self.tree.SetItemData(areaItem,area)
        self._applyTreeItemStyle(areaItem)
        return areaItem

    def addUnsupportedAreaCategory(self, areaItem, label):
        categoryItem = self.tree.AppendItem(areaItem, label)
        self._applyTreeItemStyle(categoryItem)
        noteItem = self.tree.AppendItem(categoryItem, _('(Not yet supported)'))
        self.tree.SetItemTextColour(noteItem, WxUtils.getMutedTextColour(self.tree))
        self.tree.Expand(categoryItem)

    def _safeTreeLabel(self, thing, fallbackLabel):
        label = ''
        try:
            label = thing.getName()
        except Exception:
            logger.exception('failed to get tree label from %s', repr(thing))

        if isinstance(label, bytes):
            label = label.decode('latin1', 'ignore')
        if label is None:
            label = ''
        label = str(label).split('\0', 1)[0].strip()
        if label:
            return label

        for key in ('Tag', 'TemplateResRef'):
            value = None
            try:
                value = thing[key]
            except Exception:
                value = None
            if isinstance(value, bytes):
                value = value.decode('latin1', 'ignore')
            if value is None:
                continue
            value = str(value).split('\0', 1)[0].strip()
            if value and value not in ('****', 'NULL'):
                return value

        object_id = None
        try:
            object_id = thing.getObjectId()
        except Exception:
            object_id = None
        if object_id is not None:
            return '%s #%s' % (fallbackLabel, str(object_id))

        return fallbackLabel

    def _applyTreeItemStyle(self, item):
        """Apply dark-mode-aware styling to a tree item."""
        try:
            self.tree.SetItemTextColour(item, WxUtils.getTextColour(self.tree))
        except Exception:
            pass

    def _appendAreaCategory(self, areaItem, categoryLabel, things, fallbackLabel):
        if not things:
            return
        parentItem = self.tree.AppendItem(areaItem, categoryLabel)
        self._applyTreeItemStyle(parentItem)
        for thing in things:
            label = self._safeTreeLabel(thing, fallbackLabel)
            thingItem = self.tree.AppendItem(parentItem, label)
            self._applyTreeItemStyle(thingItem)
            self.tree.SetItemData(thingItem, thing)
            try:
                self.idToTreeItemMap[thing.getNevereditId()] = thingItem
            except Exception:
                logger.exception('failed to index tree item for %s', repr(thing))
        
    def subtreeFromArea(self,areaItem,area):
        '''Create a new subtree for a module area.'''
        self.tree.DeleteChildren(areaItem)
        categories = [
            (_('Doors'), area.getDoors, _('Door')),
            (_('Placeables'), area.getPlaceables, _('Placeable')),
            (_('Creatures'), area.getCreatures, _('Creature')),
            (_('Items'), area.getItems, _('Item')),
            (_('WayPoints'), area.getWayPoints, _('Waypoint')),
            (_('Sounds'), area.getSounds, _('Sound')),
            (_('Triggers'), area.getTriggers, _('Trigger')),
            (_('Encounters'), area.getEncounters, _('Encounter')),
        ]
        for categoryLabel, getter, fallbackLabel in categories:
            try:
                things = getter()
            except Exception:
                logger.exception('failed to read area category %s for %s', categoryLabel, area.getName())
                continue
            self._appendAreaCategory(areaItem, categoryLabel, things, fallbackLabel)

    def isAreaItem(self,item):
        data = self.tree.GetItemData(item)
        return data and data.__class__ == Area.Area
    
    def getAreaForTreeItem(self,item):
        '''Get the area associated with this tree item'''
        item = self.getParentAreaItem(item)
        if item:
            return self.tree.GetItemData(item)
        else:
            return None

    def getParentAreaItem(self,item):
        '''Get the parent item in the tree that contains the area'''
        while item:
            data = self.tree.GetItemData(item)
            if data and data.__class__ == Area.Area:
                return item
            else:
                item = self.tree.GetItemParent(item)
        return None
    
    def treeItemExpanding(self,event):
        """Dynamically create the children of the currently expanding item."""
        item = event.GetItem()
        if self.isAreaItem(item):
            area = self.getAreaForTreeItem(item)
            self.setStatus('Loading area contents: %s' % area.getName())
            self.setProgress(10)
            wx.YieldIfNeeded()
            area.readContents()
            self.setProgress(70)
            wx.YieldIfNeeded()
            self.subtreeFromArea(item,area)
            self.setProgress(0)
            self.setStatus('Area ready: %s' % area.getName())

    def treeItemCollapsed(self,event):
        item = event.GetItem()
        if self.isAreaItem(item):
            self.getAreaForTreeItem(item).discardContents()
            self.tree.DeleteChildren(item)

    def getSelectedTreeItemData(self):
        '''
        get the data stored with the currently selected tree item
        @return: the stored data object of the current item
        '''
        return self.tree.GetItemData(self.tree.GetSelection())

    def OnNotebookPageChanged(self,event):
        '''Callback for notebook page changing event'''
        self.maybeApplyPropControlValues()
        self.syncDisplayedPage()
        
    def syncDisplayedPage(self):
        '''
        The main application notebook does a lazy update: only when
        the user actually switches to a page does the page content get
        created. This leads to longer switching times, but shorter
        time to select a new item in the module tree. This method
        is called when the notebook page changes and ensures that
        the content is loaded if it has not been loaded before.
        '''
        if not self.selectedTreeItem:
            return        
        data = self.tree.GetItemData(self.selectedTreeItem)
        area = self.getAreaForTreeItem(self.selectedTreeItem)
        tag = self.notebook.getSelectedTag()
        if not data and not area:
            return
        if not self.notebook.doesCurrentPageNeedSync():
            if tag == 'map' and self.toolPalette:
                self.toolPalette.GetToolBar().Enable(True)
            else:
                self.toolPalette.GetToolBar().Enable(False)
            return
        self.SetEvtHandlerEnabled(False)
        self.notebook.SetEvtHandlerEnabled(False)
        if self.toolPalette:
            self.toolPalette.GetToolBar().Enable(False)
        if tag == 'map':
            self.map.setArea(area)
            MapWindow.EVT_MAPSINGLESELECTION(self.map,
                                             self.OnMapSelection)
            MapWindow.EVT_MAPMOVE(self.map,self.OnMapMove)
            self.map.Bind(MapWindow.EVT_MAPTHINGADDED, self.OnMapThingAdded)
            if self.toolPalette:
                ToolPalette.EVT_TOOLSELECTION(self.toolPalette,
                                              self.map.toolSelected)
                self.toolPalette.GetToolBar().Enable(True)
                if data:
                    self.map.selectThingById(data.getNevereditId())
        elif tag == 'model':
            self.model.setModel(data.getModel(True))
        self.notebook.setCurrentPageSync(False)
        self.SetEvtHandlerEnabled(True)
        self.notebook.SetEvtHandlerEnabled(True)

    def treeSelChanged(self,event):
        '''Callback to handle the user changing the selection
        in the main tree.'''
        logger.info("treeSelChanged " + repr(event))
        self.maybeApplyPropControlValues()
        lastItem = self.selectedTreeItem
        self.selectedTreeItem = event.GetItem()
        if self.isAreaItem(event.GetItem()):
            self.tree.Expand(event.GetItem())
        if not self.selectedTreeItem:
            return
        data = self.tree.GetItemData(self.selectedTreeItem)
        notebookSelection = self.notebook.GetSelection()
        area = self.getAreaForTreeItem(self.selectedTreeItem)
        self.editmenu.Enable(self.ID_AREA_PROPS, bool(area))
        oldArea = self.getAreaForTreeItem(lastItem)
        if oldArea and area != oldArea:
            oldArea.discardTiles()
        if area:
            self.lastAreaItem = self.getParentAreaItem(self.selectedTreeItem)
        if area and not self.notebook.getPageByTag('map'):
            self.map = MapWindow.MapWindow(self.notebook)
            self.notebook.AddPage(self.map, _('Map'), 'map')
            self.map.setProgressDisplay(self)
            self._applyShaderPreferences(self.map.shader_manager)
            self._connectShaderWindow()
        elif not area and self.notebook.getPageByTag('map'):
            self.map.setArea(None)
            self.notebook.deletePageByTag('map')
            self.map = None
            self._connectShaderWindow()
        if area and self.toolPalette:
            self.toolPalette.toggleToolOn(ToolPalette.SELECTION_TOOL)
        
        if self.notebook.getPageByTag('model') and not hasattr(data,'getModel'):
            self.notebook.deletePageByTag('model')
        if hasattr(data,'getModel'):
            if not self.model:
                self.model = ModelWindow.ModelWindow(self.notebook)
                self.notebook.AddPage(self.model, _('Model'), 'model')

        if data:
            if data.__class__ == Script:
                self.scriptEditor.addScript(data)
                self.scriptEditor.addChangeListener(self.setFileChanged)
                self.selectedTreeItem = lastItem #we didn't actually change the main display
                self.showScriptEditor()
                self.showScriptEditorFix = True
                return
            if data.__class__ == Conversation:
                self.notebook.deletePageByTag('factions')
                if not self.notebook.getPageByTag('conversation'):
                    conversationPage = ConversationWindow\
                                       .ConversationWindow(self.notebook,
                                                           data)
                    conversationPage.addChangeListener(self.setFileChanged)
                    self.notebook.AddPage(conversationPage, _("Conversation"), 'conversation')
                else:
                    self.notebook.getPageByTag('conversation').setConversation(data)
            elif data.__class__ == FactionStruct:
                self.notebook.deletePageByTag('conversation')
                if self.notebook.getPageByTag('factions'):
                    # I destroy and rebuild, to keep in sync with the 'factionName' property
                    self.notebook.deletePageByTag('factions')
                facGrid = FactionGridWindow(self.notebook,self.module.facObject,self)
                self.notebook.AddPage(facGrid,_('Factions reactions'),'factions')
            else:
                self.notebook.deletePageByTag('factions')
                self.notebook.deletePageByTag('conversation')
        else:
            self.notebook.deletePageByTag('conversation')
            self.notebook.deletePageByTag('factions')

        page_count = self.notebook.GetPageCount()
        if page_count > 0 and notebookSelection >= 0 and notebookSelection < page_count:
            self.notebook.SetSelection(notebookSelection)
        elif self.notebook.getPageByTag('map'):
            self.notebook.selectPageByTag('map')
        elif page_count > 0:
            self.notebook.SetSelection(0)

        self.notebook.setSyncAllPages(True)
        self.syncDisplayedPage()

    def maybeApplyPropControlValues(self):
        '''
        Check if the selected item in the main module tree has
        data associated with it, and, if so, apply its control
        values by calling applyPropControlValues().
        '''
        # kill any thread playing BMU sound
        SoundControl.Event_Die.set()
        if self.selectedTreeItem:
            data = self.tree.GetItemData(self.selectedTreeItem)
            if data:
                if data.__class__ == Conversation:
                    self.notebook.getPageByTag('conversation').maybeApplyPropControlValues()
                self.applyPropControlValues()

    def applyPropControlValues(self):
        '''This method reads back in the values of currently
        displayed property controls and updates the actual
        module file to reflect these values.'''
        if self.props:
            # a PropWindow is in the tab list
            if self.props.applyPropControlValues(self.tree\
                                                 .GetItemData(self.selectedTreeItem)):
                self.setFileChanged(True)
        factions_notebook = self.notebook.getPageByTag('factions')
        if factions_notebook:
            # we have a faction window in the tabs
            if factions_notebook.applyPropControlValues(self.module.facObject):
                self.setFileChanged(True)
            
    def OnFileChanged(self,event):
        self.setFileChanged(True)
        
    def about(self,event):
        '''About menu item callback.'''
        dlg = wx.MessageDialog(self,_('neveredit v') + neveredit.__version__ +
                              _(''' by Sumpfork
Copyright 2003-2006'''),
                               _('About neveredit'),
                               wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def maybeSave(self):
        '''Ask whether we should save changes and do so if yes.
        @return: boolean indicating whether we can proceed
                 (data saved or discarded).
        '''
        self.maybeApplyPropControlValues()
        if self.fileChanged:
            dlg = wx.MessageDialog(self,_('Save Changes to ') + self.fname
                                  + '?',
                                  _("Changed File"),
                                   wx.YES_NO|wx.CANCEL|wx.ICON_QUESTION)
            answer = dlg.ShowModal ()
            if answer == wx.ID_YES:
                self.saveFile(None)
                return True
            elif answer == wx.ID_CANCEL:
                return False
            else:
                return True
        else:
            return True

    def OnCloseToolPalette(self,event):
        if self.toolPalette:
            self._rememberWindowState(self.toolPalette, 'ToolPaletteState')
        self.toolPalette = None
        event.Skip()
        
    def OnCloseSplash(self,event):
        self.splash = None

    def OnCloseWindow(self,event):
        self._rememberWindowState(self.scriptEditorFrame, 'ScriptEditorState')
        self.scriptEditorFrame.Show(False)
        event.Veto()

    def _trackWindowState(self, window, prefKey, minSize=None):
        if not window:
            return
        window._neveredit_pref_key = prefKey
        window._neveredit_min_size = minSize
        window.Bind(wx.EVT_MOVE, self._onTrackedWindowGeometryEvent)
        window.Bind(wx.EVT_SIZE, self._onTrackedWindowGeometryEvent)

    def _onTrackedWindowGeometryEvent(self, event):
        window = event.GetEventObject()
        pref_key = getattr(window, '_neveredit_pref_key', None)
        if pref_key:
            self._rememberWindowState(window, pref_key)
        event.Skip()

    def _rememberWindowState(self, window, prefKey):
        if self._restoringWindowState or not prefKey:
            return
        state = WxUtils.captureWindowState(window, self._windowStates.get(prefKey))
        if state:
            self._windowStates[prefKey] = state

    def _restoreWindowState(self, window, prefKey, minSize=None):
        from neveredit.util import plistlib
        state = self.prefs[prefKey]
        # Check for both dict and plistlib.Dict (custom dict wrapper from plist files)
        if not isinstance(state, (dict, plistlib.Dict)):
            state = None
        self._windowStates[prefKey] = state
        if not state:
            import sys
            print(f"[NeverEdit] No saved state for {prefKey}", file=sys.stderr)
            return
        import sys
        print(f"[NeverEdit] Restoring {prefKey}: {state}", file=sys.stderr)
        self._restoringWindowState = True
        try:
            WxUtils.applyWindowState(window, state, min_size=minSize)
        finally:
            self._restoringWindowState = False
        self._rememberWindowState(window, prefKey)

    def _restorePersistedWindowState(self):
        self._restoreWindowState(self, 'MainWindowState', self._scale_size(750, 280))
        # Note: Script editor state will be restored in showScriptEditor() 
        # after the window is first shown, not here in __init__
        sash = self.prefs['MainSplitterSashPosition']
        if sash is not None:
            try:
                self.splitter.SetSashPosition(int(sash))
            except Exception:
                pass
        
    def _performShutdown(self):
        # Stop periodic callbacks before tearing down windows.
        try:
            if self.timer and self.timer.IsRunning():
                self.timer.Stop()
        except Exception:
            pass

        # Unbind all event handlers from tool palette to prevent event callbacks
        # from firing after window destruction
        try:
            if self.toolPalette:
                self.toolPalette.Unbind(wx.EVT_TOOL)
        except Exception:
            pass

        # Remember window states before closing, in case they haven't been captured yet.
        self._rememberWindowState(self, 'MainWindowState')
        self._rememberWindowState(self.scriptEditorFrame, 'ScriptEditorState')
        try:
            if self.toolPalette:
                self._rememberWindowState(self.toolPalette, 'ToolPaletteState')
        except Exception:
            pass
        try:
            if self.shaderWindow:
                self._rememberWindowState(self.shaderWindow, 'ShaderWindowState')
        except Exception:
            pass

        self.savePrefs()

        # Destroy tool palette first (before map closes)
        try:
            if self.toolPalette:
                self.toolPalette.Destroy()
                self.toolPalette = None
        except Exception:
            pass

        # Destroy script editor next
        try:
            if self.scriptEditorFrame:
                self.scriptEditorFrame.Destroy()
        except Exception:
            pass

        try:
            if self.shaderWindow:
                self.shaderWindow.Destroy()
                self.shaderWindow = None
        except Exception:
            pass

        # Process any pending events to prevent them from firing after destruction
        try:
            wx.SafeYield()
        except Exception:
            pass

        # Finally destroy the main window
        self.Destroy()
        app = wx.GetApp()
        if app:
            app.ExitMainLoop()

    def OnClose(self,event):
        '''Window closing callback method for the main app.'''
        if self.maybeSave():
            self._performShutdown()
        else:
            if event:
                event.Veto()
            return False

    def reparent(self,window,newparent):
        for c in window.GetChildren():
            window.RemoveChild(c)
            window.AddChild(c)
            self.reparent(c,window)
            
    def OnDetach(self,event):
        page = self.notebook.GetPage(self.notebook.GetSelection())
        print(page)
        self.notebook.RemovePage(self.notebook.GetSelection())
        frame = wx.Frame(self,-1,self.notebook\
                         .GetPageText(self.notebook.GetSelection()))
        page.Reparent(frame)
        self.reparent(page,frame)
        frame.Show(True)

    def windowMenu(self,event):
        id = event.GetId()
        if id == self.ID_MAIN_WINDOW_MITEM:
            self.Show(True)
            self.Raise()
        elif id == self.ID_MAP_LAYER_WINDOW_MITEM:
            if self.map:
                self.map.showMapLayersWindow()
                self.map.Raise()
            else:
                self.SetStatusText(_('Map Layer window is available when an area map is open.'))
        elif id == self.ID_PALETTE_WINDOW_MITEM:
            self.showToolPalette()
            self.toolPalette.Raise()
        elif id == self.ID_SCRIPT_WINDOW_MITEM:
            self.showScriptEditor()
        elif id == self.ID_SHADER_WINDOW_MITEM:
            self.showShaderWindow()
            if self.shaderWindow:
                self.shaderWindow.Raise()
            
    def exit(self,event):
        '''Exit the Main app, asking about possible unsaved changes.'''
        self.Close(True)

    def help(self,event):
        self.helpviewer.DisplayContents()

    def OnBuildModule(self, event):
        self.SetStatusText(_('Build Module is not implemented yet (placeholder).'))
        wx.MessageBox(_('Build Module is currently a placeholder.\n'
                        'Compile/validation wiring will be added in a later phase.'),
                      _('Build Module'), wx.OK | wx.ICON_INFORMATION, self)

    def OnTestModule(self, event):
        self.SetStatusText(_('Test Module is not implemented yet (placeholder).'))
        wx.MessageBox(_('Test Module is currently a placeholder.\n'
                        'In-game launch/integration will be added in a later phase.'),
                      _('Test Module'), wx.OK | wx.ICON_INFORMATION, self)

    def OnModuleProperties(self, event):
        """Show the Module Properties dialog."""
        module = getattr(self, 'module', None)
        if not module:
            return
        if PropertiesDialogs.show_module_properties(self, module):
            self.setFileChanged(True)

    def OnAreaWizard(self, event):
        """Show the New Area wizard and add the area to the module on OK."""
        self._runAreaWizard()

    def _selectMapPageIfAvailable(self):
        if self.notebook.getPageByTag('map'):
            self.notebook.selectPageByTag('map')
            self.syncDisplayedPage()

    def _openAreaInViewer(self, area_item):
        if not area_item or not area_item.IsOk():
            return
        self.tree.EnsureVisible(area_item)
        self.tree.SelectItem(area_item)
        if self.notebook.getPageByTag('map'):
            self.notebook.selectPageByTag('map')
            self.syncDisplayedPage()
        else:
            wx.CallAfter(self._selectMapPageIfAvailable)

    def _runAreaWizard(self):
        from neveredit.ui import AreaWizard as _AreaWizardModule
        from neveredit.game.ResourceManager import ResourceManager as _RM
        module = getattr(self, 'module', None)
        if not module:
            return
        results = _AreaWizardModule.show_area_wizard(self)
        if not results:
            return
        existing = {_RM.normalizeResRef(n) for n in module.getAreaNames()}
        if results['resref'] in existing:
            wx.MessageBox(
                'An area with ResRef "%s" already exists in this module.'
                % results['resref'],
                'Duplicate ResRef', wx.OK | wx.ICON_WARNING, self)
            return
        try:
            area = module.createNewArea(
                name=results['name'],
                resref=results['resref'],
                tileset=results['tileset'],
                width=results['width'],
                height=results['height'],
            )
        except Exception as exc:
            wx.MessageBox('Failed to create area: %s' % str(exc),
                          'Error', wx.OK | wx.ICON_ERROR, self)
            return
        area_item = None
        if hasattr(self, 'areaRoot') and self.areaRoot.IsOk():
            area_item = self.makeAreaItem(self.areaRoot, area)
            self.tree.Expand(self.areaRoot)

        if results.get('launch_area_properties'):
            if PropertiesDialogs.show_area_properties(self, area):
                self.setFileChanged(True)

        if results.get('open_area_viewer'):
            self._openAreaInViewer(area_item)

        self.setFileChanged(True)
        self.SetStatusText('Created area "%s" (%s)' %
                           (results['name'], results['resref']))

    def OnNewModule(self, event):
        """Create a new blank module, then launch the Area Wizard."""
        if not self.maybeSave():
            return

        name_dlg = wx.TextEntryDialog(
            self,
            _('Enter the name for the new module:'),
            _('New Module'),
            _('New Module'))
        if name_dlg.ShowModal() != wx.ID_OK:
            name_dlg.Destroy()
            return
        module_name = name_dlg.GetValue().strip()
        name_dlg.Destroy()
        if not module_name:
            wx.MessageBox(_('Please enter a module name.'),
                          _('Validation'), wx.OK | wx.ICON_WARNING, self)
            return

        try:
            last_save_dir = self.prefs['LastSaveDir']
        except Exception:
            last_save_dir = os.path.join(self.prefs['NWNAppDir'], 'modules')

        default_filename = Module.Module._sanitize_resref(module_name, fallback='module') + '.mod'
        dlg = wx.FileDialog(
            self,
            _('Choose a .mod filename for the new module'),
            last_save_dir,
            default_filename,
            'MOD|*.mod|' + _('All Files') + '|*.*',
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        module_path = dlg.GetPath()
        dlg.Destroy()
        if not module_path.lower().endswith('.mod'):
            module_path += '.mod'

        try:
            Module.Module.createBlankModuleFile(module_path, module_name)
            self.doReadFile(module_path)
        except Exception as exc:
            wx.MessageBox(_('Failed to create module: %s') % str(exc),
                          _('Error'), wx.OK | wx.ICON_ERROR, self)
            return

        self.SetStatusText(_('Created module "%s".') % module_name)
        self._runAreaWizard()


    def OnAreaProperties(self, event):
        """Show the Area Properties dialog for the currently selected area."""
        area = self.getAreaForTreeItem(self.selectedTreeItem) if self.selectedTreeItem else None
        if not area:
            return
        if PropertiesDialogs.show_area_properties(self, area):
            self.setFileChanged(True)
    def OnTreeItemRightClick(self, event):
        """Show a context menu when the user right-clicks a tree item."""
        item = event.GetItem()
        if not item or not item.IsOk():
            return
        area = self.getAreaForTreeItem(item)
        if not self.isAreaItem(item) and not area:
            return

        # Resolve the area object (may come from area item directly or from a child)
        if self.isAreaItem(item):
            area = self.tree.GetItemData(item)

        menu = wx.Menu()

        props_id = wx.NewId()
        menu.Append(props_id, _('Area Properties...'))
        if area:
            def _on_props(evt, _area=area):
                if PropertiesDialogs.show_area_properties(self, _area):
                    self.setFileChanged(True)
            self.Bind(wx.EVT_MENU, _on_props, id=props_id)
        else:
            menu.Enable(props_id, False)

        menu.AppendSeparator()

        export_id = wx.NewId()
        menu.Append(export_id, _('Export Area for Godot...'))
        if area:
            def _on_export(evt, _area=area):
                self._onExportAreaForGodot(_area)
            self.Bind(wx.EVT_MENU, _on_export, id=export_id)
        else:
            menu.Enable(export_id, False)

        self.tree.PopupMenu(menu)
        menu.Destroy()

    def _onExportAreaForGodot(self, area):
        """Export *area* (doors, placeables, creatures, sounds) to Godot glTF format."""
        from neveredit.util import godot_area_export
        from neveredit.util.godot_area_export import BASE_DATA_DIR

        area_label = area.getName() or area.name or 'area'
        dlg = wx.MessageDialog(
            self,
            _('Export area "%s" for Godot?\n\nOutput will be written to:\n%s') % (
                area_label,
                os.path.join(BASE_DATA_DIR, godot_area_export._safe_dir_name(area.name or area_label))),
            _('Export Area for Godot'),
            wx.OK | wx.CANCEL | wx.ICON_INFORMATION)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dlg.Destroy()

        self.SetStatusText(_('Exporting area "%s" for Godot...') % area_label)
        try:
            result = godot_area_export.export_area(
                area,
                progress_callback=self.SetStatusText)
        except Exception as exc:
            logger.exception('Godot area export failed for %s', area_label)
            wx.MessageDialog(
                self,
                _('Export failed:\n%s') % str(exc),
                _('Export Error'),
                wx.OK | wx.ICON_ERROR).ShowModal()
            self.SetStatusText(_('Export failed for "%s".') % area_label)
            return

        msg = _('Exported "%s": %d model(s), %d sound(s)\n→ %s') % (
            area_label,
            result['gltf_count'],
            result['sound_count'],
            result['output_dir'])
        self.SetStatusText(_('Export complete: "%s"') % area_label)
        wx.MessageDialog(self, msg, _('Export Complete'), wx.OK | wx.ICON_INFORMATION).ShowModal()


    def OnPreferences(self,event):
        '''Display a prefs dialog.'''
        oldAppDir = self.prefs['NWNAppDir']
        d = PreferencesDialog.PreferencesDialog(self)
        if d.ShowAndInterpret():
            self.scriptEditor.prefsChanged()
            # Update the keys that correspond to the up, down, left and right.
            if self.model :
                self.model.UpdateKeys();
            if oldAppDir != self.prefs['NWNAppDir']:
                self.initResourceManager()
        
    def savePrefs(self):
        '''Save the current preferences settings.'''
        n = self.filehistory.GetCount()
        files = []
        for i in range(n):
            files.append(self.filehistory.GetHistoryFile(i))
        self.prefs['FileHistory'] = files
        self._rememberWindowState(self, 'MainWindowState')
        self._rememberWindowState(self.scriptEditorFrame, 'ScriptEditorState')
        if self.toolPalette:
            self._rememberWindowState(self.toolPalette, 'ToolPaletteState')
        if self.shaderWindow:
            self._rememberWindowState(self.shaderWindow, 'ShaderWindowState')
        self.prefs['MainWindowState'] = self._windowStates.get('MainWindowState')
        self.prefs['ScriptEditorState'] = self._windowStates.get('ScriptEditorState')
        self.prefs['ToolPaletteState'] = self._windowStates.get('ToolPaletteState')
        self.prefs['ShaderWindowState'] = self._windowStates.get('ShaderWindowState')
        self._rememberShaderPreferences()
        try:
            self.prefs['MainSplitterSashPosition'] = int(self.splitter.GetSashPosition())
        except Exception:
            self.prefs['MainSplitterSashPosition'] = None
        self.prefs.save()
        
    def loadPrefs(self):
        '''Load preferences from their standard location.'''
        self.prefs = Preferences.getPreferences()
        #print self.prefs.filehistory
        for f in self.prefs['FileHistory']:
            try:
                f.encode('ascii')
            except:
                print("not adding filename to file history to " +\
                      "work around wxWindow encoding bug", file=sys.stderr)
                continue
            #print 'trying to add',f.encode('utf8')
            self.filehistory.AddFileToHistory(f)
        
    def doReadFile(self,fname):
        '''Read in a file. Does not ask about unsaved changes.
        @param fname: name of file to read
        '''
        self.SetStatusText("Reading " + fname + "...")
        try:
            self.module = Module.Module(fname)
        except IOError as e:
            dlg = wx.MessageDialog(self,_("Error opening file (" + e.strerror
                                          + '): ' + fname),
                                   _("Error Opening File"),wx.OK|wx.ICON_ERROR)
            dlg.ShowModal()
            return
        if self.module.needSave:
            self.SetStatusText(_("Detected legacy module fields, converting to new style..."))
        neverglobals.getResourceManager().addModule(self.module)
        self.fname = fname
        self.treeFromERF()
        self.setFileChanged(False)
        if self.module.needSave:
            self.setFileChanged(True)
            self.SetStatusText(_("Read ") + self.fname + _(" (legacy fields converted)"))
        self.filehistory.AddFileToHistory(fname)
        self.scriptEditor.setModule(self.module)
        self.SetTitle('neveredit: ' + os.path.basename(self.module.getFileName()))
        
    def readFile(self,fname):
        '''Read in a file. Asks about unsaved changes.
        @param fname: name of file to read
        '''
        if self.maybeSave():
            self.doReadFile(fname)
        
    def openFile(self,event):
        '''Display a dialog to find a file, and load it if user says yes.'''
        try:
            lastOpenDir = self.prefs['LastOpenDir']
        except:
            lastOpenDir = os.path.join(self.prefs['NWNAppDir'],'modules')
        dlg = wx.FileDialog(self,_("Choose an ERF (mod/hak/nwm) File"),
                            lastOpenDir, '',
                           'MOD|*.mod|ERF|*.erf|HAK|*.hak|SAV|*.sav|'
                            +_('All Files')
                           +'|*.*',
                           wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.readFile(dlg.GetPath())
        dlg.Destroy()




    def addERFFile(self,event):
        '''Display a dialog to find a file and add its entries to
        the current one.'''
        dlg = wx.MessageDialog(self,_(
'''Merging in a an ERF will overwrite the file you have currently
loaded and save any changes you have made so far. Proceed?'''),
                              _("Merge ERF File"),wx.YES_NO|wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_NO:
            return
        try:
            lastERFDir = self.prefs['LastERFDir']
        except:
            lastERFDir = os.path.join(self.prefs['NWNAppDir'],'erf')

        dlg = wx.FileDialog(self,_("Choose an ERF (mod/hak/nwm) File to add"),
                           lastERFDir, '',
                           'ERF|*.erf|MOD|*.mod|HAK|*.hak|SAV|*.sav|'
                            +_('All Files')
                           +'|*.*',
                           wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.maybeApplyPropControlValues()
            self.notebook.SetSelection(0)
            self.tree.SelectItem(self.treeRoot)
            self.module.addERFFile(dlg.GetPath())
            self.treeFromERF()
        dlg.Destroy()

    def addResourceFile(self,event):
        '''Display a dialog to find a file and add it as a resource to
        the current module.'''
        dlg = wx.FileDialog(self,_("Choose a resource file (e.g. .dlg) to add"),
                           '', '',
                            _('All Files')
                           +'|*.*',
                           wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self.module.addResourceFile(dlg.GetPath())
                self.maybeApplyPropControlValues()
                self.treeFromERF()
                self.setFileChanged(True)
                dlg.Destroy()
            except ValueError:
                dlg.Destroy()
                dlg2 = wx.MessageDialog(self,_('"' + dlg.GetPath()
                                               + '" is not a valid nwn resource name'),
                                        _("Resource Name Error"),wx.OK|wx.ICON_ERROR)
                dlg2.ShowModal()
                dlg2.Destroy()

    def saveFile(self,event):
        '''Save the file to the file name we loaded it from.'''
        self.maybeApplyPropControlValues()
        self.module.saveToReadFile()
        self.setFileChanged(False)
        self.setStatus("Saved " + self.module.getFileName() + '.')

        
    def saveFileAs(self,event):
        try:
            lastSaveDir = self.prefs['LastSaveDir']
        except:
            lastSaveDir = os.path.join(self.prefs['NWNAppDir'],'modules')

        '''Save the file to a filename the users specifies in a file dialog.'''
        dlg = wx.FileDialog(self,_("Choose a an ERF (mod/hak/nwm)"
                                   " File Name for Saving"),
                            lastSaveDir, '',
                            'MOD|*.mod|HAK|*.hak|'+_('All Files') + '|*.*',
                            wx.FD_SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            self.maybeApplyPropControlValues()
            self.module.saveAs(dlg.GetPath())
            self.fname = dlg.GetPath()
        dlg.Destroy()
        self.setFileChanged(False)
        self.SetTitle('neveredit: ' + self.module.getFileName())
        self.setStatus("Saved " + self.module.getFileName() + '.')

    def simulateTreeSelChange(self):
        lastSelected = self.selectedTreeItem
        self.selectedTreeItem = None
        self.tree.SelectItem(lastSelected,False)
        self.tree.SelectItem(lastSelected,True)

    def propertyChanged(self,control,prop):
        if control.__class__ == wx.Button and control.GetName() == "Faction_addButton":
            # add a faction
            factionItem = self.tree.AppendItem(self.factionRoot,\
                prop.getName())
            self.tree.SetItemData(factionItem,prop)
            self.tree.Refresh()
            self.simulateTreeSelChange()
            self.setFileChanged(True)
        elif control.__class__ == wx.Button and control.GetName() == "Faction_delButton":
            # remove a faction
            pass
        elif prop.getName() == 'FactionName':
            # change a faction name
            # the modified item should be the one selected...
            item = self.tree.GetSelection()
            self.tree.SetItemText(item,control.control.GetValue())
            data = self.tree.GetItemData(item)
            data.setProperty('FactionName',control.control.GetValue())
            self.simulateTreeSelChange()
            self.setFileChanged(True)
        elif control.__class__ == FactionGrid:
            self.applyPropControlValues()
            self.setFileChanged(True)


def run(args=None):
    app = wx.App(False)
    app.SetVendorName('org.openknights')
    app.SetAppName('neveredit')
    frame = NeverEditMainWindow(None,-1,_("neveredit"))
    if args and len(args) > 0:
        frame.fname = args[0]
        frame.doRead = True
    frame.init()
    app.MainLoop()

def main():
    if len(os.path.dirname(sys.argv[0])) > 0:
        # mainly to find neveredit.jpg in mac os app bundle
        os.chdir(os.path.dirname(sys.argv[0]))
    run()

if __name__ == "__main__":
    main()
