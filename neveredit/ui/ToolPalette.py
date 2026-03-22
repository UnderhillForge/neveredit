"""A set of GUI classes showing blueprint palettes and a toolbar"""
import string
import logging

import wx
import os

from neveredit.game.Palette import Palette, TilesetPalette
from neveredit.ui import WxUtils

logger = logging.getLogger('neveredit')

#images via resourcepackage
from neveredit.resources.images import select_icon_png
from neveredit.resources.images import select_icon_sel_png
from neveredit.resources.images import paint_icon_png
from neveredit.resources.images import paint_icon_sel_png
from neveredit.resources.images import rotate_icon_png
from neveredit.resources.images import rotate_icon_sel_png

class PaletteWindow(wx.TreeCtrl):
    """A tree control representing a blueprint palette."""
    def __init__(self,parent,id):
        wx.TreeCtrl.__init__(self,parent,id,
                             style=wx.TR_DEFAULT_STYLE|wx.TR_HIDE_ROOT)
        self.AddRoot("Blueprint Palette")        
        self.palette = None
        self.imagelist = wx.ImageList(16,26)
        self.SetImageList(self.imagelist)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING,self.itemExpanding)
        self.Bind(wx.EVT_TREE_SEL_CHANGING,self.selectionChanging)
        self.Bind(wx.EVT_TREE_ITEM_GETTOOLTIP,self.supplyToolTip)
        
    def fromPalette(self,palette):
        self.fromPaletteHelper(self.GetRootItem(),palette.getRoots())
        self.palette = palette
        
    def fromPaletteHelper(self,parentNode,childSpecs):
        for r in childSpecs:
            r.childrenReady = False
            label = r.getName() or '<unnamed>'
            node = self.AppendItem(parentNode,label)
            self.SetItemData(node,r)
            image = r.getImage()
            if image:
                image = image.crop((0,0,16,26))
                index = self.imagelist.Add(WxUtils.bitmapFromImage(image))
                self.SetItemImage(node,index)
            if r.getChildren():
                self.SetItemHasChildren(node,True)

    def itemExpanding(self,event):
        item = event.GetItem()
        data = self.GetItemData(item)
        if data and not data.childrenReady:
            self.fromPaletteHelper(item,data.getChildren())
            data.childrenReady = True

    def selectionChanging(self,event):
        if event.GetItem().IsOk() and\
           self.GetItemData(event.GetItem()) and\
           not self.GetItemData(event.GetItem()).getBlueprint():
            event.Veto()
            
    def supplyToolTip(self,event):
        if event.GetItem().IsOk() and\
           self.GetItemData(event.GetItem()):
            bp = self.GetItemData(event.GetItem()).getBlueprint()
            if bp:                
                event.SetToolTip(bp.getDescription())
    
    def get_standalone(cls, pname=None):
        class MyApp(wx.App):
            def OnInit(self):
                #if not pname:
                pname = 'creaturepalstd.itp'
                frame = wx.MiniFrame(None, -1, "Palette",
                                     wx.DefaultPosition, wx.Size(200,400))
                self.win = PaletteWindow(frame,-1)
                self.win.fromPalette(Palette.getStandardPalette('Creature'))
                frame.Show(True)
                self.SetTopWindow(frame)
                return True
        cls.app = MyApp(0)
        return cls.app.win
    get_standalone = classmethod(get_standalone)

    def start_standalone(cls):
        cls.app.MainLoop()
    start_standalone = classmethod(start_standalone)


class TilePaletteWindow(wx.TreeCtrl):
    """A tree control representing a tileset palette with Features, Groups, and Tiles sections."""
    def __init__(self, parent, id):
        wx.TreeCtrl.__init__(self, parent, id,
                             style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT)
        self.AddRoot("Tileset Palette")
        self.tileset_palette = None
        self.imagelist = wx.ImageList(16, 26)
        self.SetImageList(self.imagelist)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.itemExpanding)
        self.Bind(wx.EVT_TREE_SEL_CHANGING, self.selectionChanging)
        
    def fromTilesetPalette(self, tileset_palette):
        """Load a tileset palette into the tree view."""
        # Clear existing items except root
        root = self.GetRootItem()
        self.DeleteChildren(root)
        
        self.tileset_palette = tileset_palette
        sections = tileset_palette.getSections()
        
        # Add the three sections as root items
        for section_name in TilesetPalette.SECTION_NAMES:
            tiles = sections.get(section_name, [])
            if tiles:
                section_label = f"{section_name} ({len(tiles)})"
                section_item = self.AppendItem(root, section_label)
                self.SetItemData(section_item, None)  # No data for section headers
                
                # Add tiles under this section
                for tile in tiles:
                    tile_label = tile.getName()
                    tile_item = self.AppendItem(section_item, tile_label)
                    self.SetItemData(tile_item, tile)
    
    def itemExpanding(self, event):
        # Tiles are already expanded, nothing to do on demand
        pass
    
    def selectionChanging(self, event):
        # Allow selection of tiles (which have data)
        # Don't allow selection of section headers (which have no data)
        if event.GetItem().IsOk():
            data = self.GetItemData(event.GetItem())
            if data is None:
                # This is a section header, prevent selection
                event.Veto()
    
    def GetSelection(self):
        """Get the currently selected item (for compatibility with PaletteWindow)."""
        return wx.TreeCtrl.GetSelection(self)
    
    def Unselect(self):
        """Deselect current item."""
        self.UnselectAll()
    
    def SelectItem(self, item):
        """Select an item."""
        if item and item.IsOk():
            wx.TreeCtrl.SelectItem(self, item)

class PlaceholderPalettePage(wx.Panel):
    """Notebook page used to expose not-yet-implemented palette types."""

    def __init__(self, parent, paletteType, message):
        wx.Panel.__init__(self, parent, -1)
        self.paletteType = paletteType

        sizer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(self, -1, paletteType)
        detail = wx.StaticText(self, -1, message)
        detail.Wrap(220)

        title_font = title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        detail.SetForegroundColour(WxUtils.getMutedTextColour(self))

        sizer.Add(title, 0, wx.ALL, 10)
        sizer.Add(detail, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.AddStretchSpacer()
        self.SetSizer(sizer)

    def GetSelection(self):
        return wx.TreeItemId()

    def Unselect(self):
        return None

    def SelectItem(self, item):
        return None

    def GetItemData(self, item=None):
        return None

TOOLSELECTIONEVENT = wx.NewEventType()

def EVT_TOOLSELECTION(window,function):
    '''notifies about the selection of a tool in the palette'''
    window.Connect(-1,-1,TOOLSELECTIONEVENT,function)

class ToolSelectionEvent(wx.PyCommandEvent):
    eventType = TOOLSELECTIONEVENT
    def __init__(self,windowID,tooltype):
        wx.PyCommandEvent.__init__(self,self.eventType,windowID)
        self.tooltype = tooltype
        self.data = None

    def setData(self,data):
        self.data = data

    def getData(self):
        return self.data
    
    def getToolType(self):
        return self.tooltype
    
    def Clone(self):
        clone = self.__class__(self.GetId(),self.tooltype)
        clone.data = self.data
        return clone

SELECTION_TOOL = wx.NewId()
ROTATE_TOOL = wx.NewId()
PAINT_TOOL = wx.NewId()
AMBIENT_SOUND_TOOL = wx.NewId()
MAP2D_DRAW_TOOL = wx.NewId()

class ToolFrame(wx.MiniFrame):
    def __init__(self):
        from PIL import Image
        from neveredit.ui import WxUtils
        try:
            ui_scale = float(os.environ.get('NEVEREDIT_UI_SCALE', '1.25'))
        except (TypeError, ValueError):
            ui_scale = 1.25
        ui_scale = max(1.0, ui_scale)
        pos = (int(805 * ui_scale), int(25 * ui_scale))
        size = (int(340 * ui_scale), int(680 * ui_scale))
        wx.MiniFrame.__init__(self,None,-1,"Tools",pos,size)
        panel_bg = WxUtils.getPanelBackgroundColour(self)
        self.SetBackgroundColour(panel_bg)
        self.CreateStatusBar()
        self.toolbar = self.CreateToolBar(wx.TB_FLAT | wx.NO_BORDER | wx.TB_HORIZONTAL)
        self.toolbar.SetBackgroundColour(panel_bg)
        self.toolbar.SetToolBitmapSize((26,24))
        self.selectId = SELECTION_TOOL
        self.toolbar.AddTool(self.selectId,
                     "Select/Move",
                     select_icon_png.getBitmap(),
                     select_icon_sel_png.getBitmap(),
                     kind=wx.ITEM_RADIO,
                     shortHelp=('Select Object'),
                     longHelp='Select and Move objects on Map')
        self.paintId = PAINT_TOOL        
        self.toolbar.AddTool(self.paintId,
                     "Paint",
                     paint_icon_png.getBitmap(),
                     paint_icon_sel_png.getBitmap(),
                     kind=wx.ITEM_RADIO,
                     shortHelp='Paint Objects',
                     longHelp='Paint selected objects onto Map Display')
        self.rotateId = ROTATE_TOOL        
        self.toolbar.AddTool(self.rotateId,
                     "Rotate",
                     rotate_icon_png.getBitmap(),
                     rotate_icon_sel_png.getBitmap(),
                     kind=wx.ITEM_RADIO,
                     shortHelp=('Rotate Object'),
                     longHelp=('Rotate object shown on Map'))
        self.soundId = AMBIENT_SOUND_TOOL
        self.toolbar.AddTool(self.soundId,
                 "Ambient Sound",
                 paint_icon_png.getBitmap(),
                 paint_icon_sel_png.getBitmap(),
                 kind=wx.ITEM_RADIO,
                 shortHelp='Place Ambient Sound Region',
                 longHelp='Place and move ambient sound radius regions')
        self.map2dId = MAP2D_DRAW_TOOL
        self.toolbar.AddTool(self.map2dId,
             "2D Draw",
             paint_icon_png.getBitmap(),
             paint_icon_sel_png.getBitmap(),
             kind=wx.ITEM_RADIO,
             shortHelp='2D Map Drawing',
             longHelp='Paint terrain, height, and object marks on a 2D grid overlay')
        self.Bind(wx.EVT_TOOL,self.toolSelected)
        self.toolbar.AddSeparator()
        self.toolbar.Realize()
        self.toolIds = [self.selectId,self.paintId,self.rotateId,self.soundId,self.map2dId]

        self.stdPalettes = {}
        for _ptype in Palette.PALETTE_TYPES:
            try:
                self.stdPalettes[_ptype] = Palette.getStandardPalette(_ptype)
            except Exception as _e:
                import logging
                logging.getLogger('neveredit').warning(
                    'Palette load failed for %s: %s', _ptype, _e)
        self.notebook = wx.Notebook(self,-1,style=wx.NB_LEFT)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPalettePageChanged)
        placeholderPages = {}
        for type in Palette.PALETTE_TYPES:
            palette = self.stdPalettes.get(type)
            if palette is not None:
                pw = PaletteWindow(self.notebook,-1)
                pw.fromPalette(palette)
                self.notebook.AddPage(pw,type)
                pw.Bind(wx.EVT_TREE_SEL_CHANGED,self.treeItemSelected)
                continue
            placeholder = placeholderPages.get(type)
            if placeholder is not None:
                self.notebook.AddPage(placeholder, type)

        self.toggleToolOn(self.selectId)
        self.lastPaletteSelection = None
        self.currentTileset = None
        self.tilesetPaletteWindow = None
        self.tilesetPalettePageIndex = None
        
    def getActivePaletteWindow(self):
        return self.notebook.GetPage(self.notebook.GetSelection())
    
    def setActiveTileset(self, tileset_resref):
        """
        Set the active tileset and load its palette.
        
        Args:
            tileset_resref: The tileset resource reference (e.g., 'tcn01'), or None to clear
        """
        if tileset_resref == self.currentTileset:
            return  # No change needed
        
        self.currentTileset = tileset_resref
        
        if not tileset_resref:
            # Remove the tileset palette tab if no tileset
            self._removeTilesetPaletteTab()
            return
        
        # Load the tileset palette
        try:
            tileset_palette = TilesetPalette.getTilesetPalette(tileset_resref)
            if tileset_palette:
                self._updateTilesetPaletteTab(tileset_palette)
            else:
                logger.warning(f'Could not load palette for tileset {tileset_resref}')
                self._removeTilesetPaletteTab()
        except Exception as e:
            logger.warning(f'Error loading tileset palette: {e}')
            self._removeTilesetPaletteTab()
    
    def _updateTilesetPaletteTab(self, tileset_palette):
        """Update or create the tileset palette tab."""
        # Create the palette window if it doesn't exist
        if not self.tilesetPaletteWindow:
            self.tilesetPaletteWindow = TilePaletteWindow(self.notebook, -1)
            self.tilesetPaletteWindow.Bind(wx.EVT_TREE_SEL_CHANGED, self.treeItemSelected)
            
            # Check if we already have a Tiles tab (from standard palettes)
            tile_tab_exists = False
            for i in range(self.notebook.GetPageCount()):
                if self.notebook.GetPageText(i) == 'Tiles':
                    # Replace it with our tileset version
                    self.notebook.RemovePage(i)
                    self.notebook.InsertPage(i, self.tilesetPaletteWindow, 'Tiles (Tileset)')
                    self.tilesetPalettePageIndex = i
                    tile_tab_exists = True
                    break
            
            if not tile_tab_exists:
                # Add as a new tab at the beginning
                self.notebook.InsertPage(0, self.tilesetPaletteWindow, 'Tiles (Tileset)')
                self.tilesetPalettePageIndex = 0
        
        # Load the palette into the window
        self.tilesetPaletteWindow.fromTilesetPalette(tileset_palette)
    
    def _removeTilesetPaletteTab(self):
        """Remove the tileset palette tab."""
        if self.tilesetPaletteWindow and self.tilesetPalettePageIndex is not None:
            self.notebook.RemovePage(self.tilesetPalettePageIndex)
            self.tilesetPaletteWindow = None
            self.tilesetPalettePageIndex = None
        
    
    def toggleToolOn(self,id):
        for tid in self.toolIds:
            self.toolbar.ToggleTool(tid,tid==id)
        newEvent = ToolSelectionEvent(self.GetId(),id)
        if id != self.paintId:
            active = self.getActivePaletteWindow()
            if hasattr(active, 'GetSelection'):
                self.lastPaletteSelection = active.GetSelection()
            if hasattr(active, 'Unselect'):
                active.Unselect()
        else:
            if self.lastPaletteSelection:
                self.getActivePaletteWindow().SelectItem(self.lastPaletteSelection)
                self.lastPaletteSelection = None
            bp = self.getSelectedBlueprint()
            if bp:
                try:
                    newEvent.setData(bp.toInstance())
                except Exception as e:
                    logger.warning('failed to create paint instance from blueprint: %s', e)
        self.GetEventHandler().AddPendingEvent(newEvent)        

    def onPalettePageChanged(self,event):
        # Keep paint payload synced with active tab so stale placeables are
        # not reused when switching to creatures/doors/etc.
        if self.toolbar.GetToolState(self.paintId):
            self.toggleToolOn(self.paintId)
        event.Skip()
            
    def treeItemSelected(self,event):
        if self.getActivePaletteWindow().GetItemData(event.GetItem()):
            self.toggleToolOn(self.paintId)
        event.Skip()

    def getSelectedBlueprint(self):
        palette = self.getActivePaletteWindow()
        if not hasattr(palette, 'GetSelection') or not hasattr(palette, 'GetItemData'):
            return None
        data = palette.GetItemData(palette.GetSelection())
        if data:
            try:
                return data.getBlueprint()
            except Exception as e:
                logger.warning('failed to resolve selected blueprint: %s', e)
                return None
        
    def toolSelected(self,event):
        self.toggleToolOn(event.GetId())
        event.Skip()

if __name__ == "__main__":
    class MyApp(wx.App):
        def OnInit(self):
            wx.InitAllImageHandlers()            
            f = ToolFrame()
            f.Show(True)
            self.SetTopWindow(f)
            return True
    app = MyApp(0)
    app.MainLoop()
    
            
