"""Curated tabbed properties dialogs for Area and Module.

These dialogs present the same NWN GFF data as PropWindow but organise it
into logical groups (General / Lighting / Sound / Scripts for areas;
General / Events / HAKs for modules) so users can find settings quickly
without scrolling through a single alphabetical list.
"""

import logging
logger = logging.getLogger('neveredit.ui')

import wx

from neveredit.ui.PropWindow import PropWindow


# ---------------------------------------------------------------------------
# _TabData — filtered view of a NeverData object
# ---------------------------------------------------------------------------

class _TabData:
    """Wraps a NeverData object and exposes only a specified subset of its
    properties to PropWindow, while delegating all mutations back to the
    original object so they are persisted in the GFF structs.
    """

    def __init__(self, wrapped, labels):
        self._wrapped = wrapped
        self._labels = set(labels)

    # --- iteration (consumed by PropWindow.makePropsForItem) ---

    def __iter__(self):
        return self.iterateProperties()

    def iterateProperties(self):
        for prop in self._wrapped.iterateProperties():
            if prop.getName() in self._labels:
                yield prop

    # --- property access / mutation (called by PropWindow internals) ---

    def getProperty(self, name):
        return self._wrapped.getProperty(name)

    def hasProperty(self, name):
        return name in self._labels and self._wrapped.hasProperty(name)

    def setProperty(self, name, value):
        return self._wrapped.setProperty(name, value)

    def removeProperty(self, name):
        if hasattr(self._wrapped, 'removeProperty'):
            self._wrapped.removeProperty(name)

    # --- ancillary interface expected by PropWindow ---

    def getMainGFFStruct(self):
        return self._wrapped.getMainGFFStruct()

    def getNevereditId(self):
        return self._wrapped.getNevereditId()

    def getName(self):
        return self._wrapped.getName()

    def forceModelReload(self):
        if hasattr(self._wrapped, 'forceModelReload'):
            self._wrapped.forceModelReload()


# ---------------------------------------------------------------------------
# _PropertiesDialog — generic tabbed dialog hosting PropWindow pages
# ---------------------------------------------------------------------------

class _PropertiesDialog(wx.Dialog):
    """A resizable dialog that hosts a wx.Notebook whose pages are
    PropWindow instances, each showing a filtered subset of a NeverData object's
    properties.

    Parameters
    ----------
    parent : wx.Window
    title  : str
    tabs_spec : list of (str, list[str])
        Each element is (tab_label, list_of_property_labels).
    data_object : NeverData
        The Area or Module whose properties are being edited.
    """

    _MIN_SIZE = (680, 540)

    def __init__(self, parent, title, tabs_spec, data_object):
        wx.Dialog.__init__(self, parent, -1, title,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._data = data_object
        self._prop_windows = []   # list of (PropWindow, _TabData)

        nb = wx.Notebook(self, -1)

        for tab_label, labels in tabs_spec:
            tab_data = _TabData(data_object, labels)
            pw = PropWindow(nb)
            try:
                pw.makePropsForItem(tab_data, observer=None)
            except Exception:
                logger.exception('Error building props tab "%s"', tab_label)
            nb.AddPage(pw, tab_label)
            self._prop_windows.append((pw, tab_data))

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        ok_btn.SetDefault()
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM | wx.RIGHT, 10)
        self.SetSizer(sizer)
        self.SetMinSize(self._MIN_SIZE)
        self.SetSize(self._MIN_SIZE)
        self.Layout()
        self.CentreOnParent()

    def _on_ok(self, evt):
        """Apply all PropWindow values back to the NeverData GFF structs."""
        changed = False
        for pw, tab_data in self._prop_windows:
            # Mark as changed so applyPropControlValues actually writes.
            pw.propsChanged = True
            if pw.applyPropControlValues(tab_data):
                changed = True
        self._changed = changed
        self.EndModal(wx.ID_OK)

    def wasChanged(self):
        """Return True if at least one value was written back."""
        return getattr(self, '_changed', False)


# ---------------------------------------------------------------------------
# Tab definitions
# ---------------------------------------------------------------------------

_AREA_TABS = [
    ('General', [
        'Name',
        'Tag',
        'Tileset',
        'DayNightCycle',
        'IsNight',
        'NoRest',
        'ChanceLightning',
        'ChanceRain',
        'ChanceSnow',
        'WindPower',
        'ModListenCheck',
        'ModSpotCheck',
        'PlayerVsPlayer',
        'LoadScreenID',
    ]),
    ('Lighting', [
        'SunFogAmount',
        'MoonFogAmount',
        'SunShadows',
        'MoonShadows',
        'ShadowOpacity',
        'MoonAmbientColor',
        'MoonDiffuseColor',
        'SunDiffuseColor',
        'SunFogColor',
        'MoonFogColor',
    ]),
    ('Sound', [
        'AreaProperties.AmbientSndDay',
        'AreaProperties.AmbientSndNight',
        'AreaProperties.AmbientSndDayVol',
        'AreaProperties.AmbientSndNitVol',
        'AreaProperties.MusicDay',
        'AreaProperties.MusicNight',
        'AreaProperties.MusicBattle',
        'AreaProperties.MusicDelay',
        'AreaProperties.EnvAudio',
    ]),
    ('Scripts', [
        'OnEnter',
        'OnExit',
        'OnHeartbeat',
        'OnUserDefined',
    ]),
]

_MODULE_TABS = [
    ('General', [
        'Mod_Name',
        'Mod_Description',
        'Mod_Tag',
        'Mod_XPScale',
        'Mod_CustomTlk',
        'Mod_Entry_Area',
        'Mod_DawnHour',
        'Mod_DuskHour',
        'Mod_MinPerHour',
        'Mod_StartDay',
        'Mod_StartMonth',
        'Mod_StartYear',
        'Mod_StartHour',
    ]),
    ('Events', [
        'Mod_OnAcquirItem',
        'Mod_OnActvtItem',
        'Mod_OnClientEntr',
        'Mod_OnClientLeav',
        'Mod_OnCutsnAbort',
        'Mod_OnHeartbeat',
        'Mod_OnModLoad',
        'Mod_OnModStart',
        'Mod_OnPlrDeath',
        'Mod_OnPlrDying',
        'Mod_OnPlrEqItm',
        'Mod_OnPlrLvlUp',
        'Mod_OnPlrRest',
        'Mod_OnPlrUnEqItm',
        'Mod_OnSpawnBtnDn',
        'Mod_OnUnAqreItem',
        'Mod_OnUsrDefined',
    ]),
    ('HAKs & Vars', [
        'Mod_HakList',
        'VarTable',
    ]),
]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def show_area_properties(parent, area):
    """Show the Area Properties dialog.

    Returns True if the user clicked OK (properties may have been changed).
    """
    dlg = _PropertiesDialog(parent,
                            'Area Properties — %s' % area.getName(),
                            _AREA_TABS,
                            area)
    result = dlg.ShowModal()
    changed = dlg.wasChanged()
    dlg.Destroy()
    return result == wx.ID_OK and changed


def show_module_properties(parent, module):
    """Show the Module Properties dialog.

    Returns True if the user clicked OK (properties may have been changed).
    """
    dlg = _PropertiesDialog(parent,
                            'Module Properties — %s' % module.getName(),
                            _MODULE_TABS,
                            module)
    result = dlg.ShowModal()
    changed = dlg.wasChanged()
    dlg.Destroy()
    return result == wx.ID_OK and changed
