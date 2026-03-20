"""Curated tabbed properties dialogs for Area and Module.

These dialogs present the same NWN GFF data as PropWindow but organise it
into logical groups (Basic / Visual / Events / Advanced / Comments for areas;
General / Events / HAKs for modules) so users can find settings quickly
without scrolling through a single alphabetical list.
"""

import logging
logger = logging.getLogger('neveredit.ui')

import io
import json

import wx

from neveredit.ui.PropWindow import PropWindow


_AREA_TERRAIN_SITE_CHOICES = ('Exterior', 'Interior')
_AREA_TERRAIN_SURFACE_CHOICES = ('Artificial', 'Natural')
_AREA_TERRAIN_DEPTH_CHOICES = ('Above ground', 'Underground')

_AREA_FLAG_TERRAIN_INTERIOR = 0x01
_AREA_FLAG_TERRAIN_NATURAL = 0x02
_AREA_FLAG_TERRAIN_UNDERGROUND = 0x04
_AREA_FLAG_TERRAIN_MASK = (
    _AREA_FLAG_TERRAIN_INTERIOR |
    _AREA_FLAG_TERRAIN_NATURAL |
    _AREA_FLAG_TERRAIN_UNDERGROUND
)

_SCRIPT_SET_FILE_EXTENSION = 'nssset'
_SCRIPT_SET_SCHEMA = 'neveredit.area-script-set.v1'
_SCRIPT_SET_VERSION = 1
_SCRIPT_SET_KEYS = ('OnEnter', 'OnExit', 'OnHeartbeat', 'OnUserDefined')


# ---------------------------------------------------------------------------
# _TabData — filtered view of a NeverData object
# ---------------------------------------------------------------------------

class _DisplayProperty:
    """Property wrapper that exposes a display label while delegating values."""

    def __init__(self, display_label, wrapped_prop):
        self._display_label = display_label
        self._wrapped_prop = wrapped_prop

    def getName(self):
        return self._display_label

    def getValue(self):
        return self._wrapped_prop.getValue()

    def setValue(self, value):
        self._wrapped_prop.setValue(value)

    def getSpec(self):
        return self._wrapped_prop.getSpec()


class _TabData:
    """Wraps a NeverData object and exposes only a specified subset of its
    properties to PropWindow, while delegating all mutations back to the
    original object so they are persisted in the GFF structs.
    """

    def __init__(self, wrapped, labels):
        self._wrapped = wrapped
        self._entries = []
        self._display_to_real = {}
        for entry in labels:
            if isinstance(entry, tuple):
                display_name, real_name = entry
            else:
                display_name, real_name = entry, entry
            self._entries.append((display_name, real_name))
            self._display_to_real[display_name] = real_name

    # --- iteration (consumed by PropWindow.makePropsForItem) ---

    def __iter__(self):
        return self.iterateProperties()

    def iterateProperties(self):
        for display_name, real_name in self._entries:
            if self._wrapped.hasProperty(real_name):
                yield _DisplayProperty(display_name,
                                       self._wrapped.getProperty(real_name))

    # --- property access / mutation (called by PropWindow internals) ---

    def getProperty(self, name):
        real_name = self._display_to_real.get(name, name)
        wrapped_prop = self._wrapped.getProperty(real_name)
        if name != real_name:
            return _DisplayProperty(name, wrapped_prop)
        return wrapped_prop

    def hasProperty(self, name):
        real_name = self._display_to_real.get(name, name)
        return self._wrapped.hasProperty(real_name)

    def setProperty(self, name, value):
        real_name = self._display_to_real.get(name, name)
        return self._wrapped.setProperty(real_name, value)

    def removeProperty(self, name):
        real_name = self._display_to_real.get(name, name)
        if hasattr(self._wrapped, 'removeProperty'):
            self._wrapped.removeProperty(real_name)

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

    def __init__(self, parent, title, tabs_spec, data_object, tab_builders=None):
        wx.Dialog.__init__(self, parent, -1, title,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._data = data_object
        self._changed = False
        self._prop_windows = []   # list of (PropWindow, _TabData)
        self._extra_apply_handlers = []
        self._tab_builders = tab_builders or {}

        nb = wx.Notebook(self, -1)

        for tab_label, labels in tabs_spec:
            tab_panel = wx.Panel(nb, -1)
            tab_sizer = wx.BoxSizer(wx.VERTICAL)
            tab_data = _TabData(data_object, labels)
            pw = PropWindow(tab_panel)
            try:
                pw.makePropsForItem(tab_data, observer=None)
            except Exception:
                logger.exception('Error building props tab "%s"', tab_label)
            tab_sizer.Add(pw, 1, wx.EXPAND)

            builder = self._tab_builders.get(tab_label)
            if builder is not None:
                try:
                    extra_apply = builder(tab_panel, tab_sizer, pw, tab_data,
                                          data_object)
                    if callable(extra_apply):
                        self._extra_apply_handlers.append(extra_apply)
                except Exception:
                    logger.exception('Error building custom tab content for "%s"', tab_label)

            tab_panel.SetSizer(tab_sizer)
            nb.AddPage(tab_panel, tab_label)
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

    def _on_ok(self, _evt):
        """Apply all PropWindow values back to the NeverData GFF structs."""
        changed = False
        for pw, tab_data in self._prop_windows:
            # Mark as changed so applyPropControlValues actually writes.
            pw.propsChanged = True
            if pw.applyPropControlValues(tab_data):
                changed = True
        for apply_handler in self._extra_apply_handlers:
            if apply_handler():
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
    ('Basic', [
        ('Name', 'Name'),
        ('Tileset', 'Tileset'),
        ('Length', 'Height'),
        ('Width', 'Width'),
    ]),
    ('Visual', [
        ('Day - Ambient Sound', 'AreaProperties.AmbientSndDay'),
        ('Night - Ambient Sound', 'AreaProperties.AmbientSndNight'),
        ('Day Volume - Ambient Sound', 'AreaProperties.AmbientSndDayVol'),
        ('Night Volume - Ambient Sound', 'AreaProperties.AmbientSndNitVol'),
        ('Environmental Audio Effects', 'AreaProperties.EnvAudio'),
        ('Battle - Music', 'AreaProperties.MusicBattle'),
        ('Day - Music', 'AreaProperties.MusicDay'),
        ('Night - Music', 'AreaProperties.MusicNight'),
        ('Playing Delay', 'AreaProperties.MusicDelay'),
    ]),
    ('Events', [
        ('OnEnter', 'OnEnter'),
        ('OnExit', 'OnExit'),
        ('OnHeartbeat', 'OnHeartbeat'),
        ('OnUserDefined', 'OnUserDefined'),
    ]),
    ('Advanced', [
        ('Listen - Check Modifier', 'ModListenCheck'),
        ('Spot - Check Modifier', 'ModSpotCheck'),
        ('Loading Screen', 'LoadScreenID'),
        ('No Rest', 'NoRest'),
        ('Player vs Player', 'PlayerVsPlayer'),
        ('Tag', 'Tag'),
        ('Variables', 'VarTable'),
    ]),
    ('Comments', [
        ('Comments', 'Comments'),
    ]),
]


def _clean_resref(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('latin1', 'ignore').strip('\0').strip()
    return str(value).strip('\0').strip()


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decode_terrain_triplet_from_flags(flags_value):
    flags = _to_int(flags_value, 0)
    site_idx = 1 if (flags & _AREA_FLAG_TERRAIN_INTERIOR) else 0
    surface_idx = 1 if (flags & _AREA_FLAG_TERRAIN_NATURAL) else 0
    depth_idx = 1 if (flags & _AREA_FLAG_TERRAIN_UNDERGROUND) else 0
    return site_idx, surface_idx, depth_idx


def _encode_terrain_triplet_to_flags(site_idx, surface_idx, depth_idx):
    bits = 0
    if int(site_idx) == 1:
        bits |= _AREA_FLAG_TERRAIN_INTERIOR
    if int(surface_idx) == 1:
        bits |= _AREA_FLAG_TERRAIN_NATURAL
    if int(depth_idx) == 1:
        bits |= _AREA_FLAG_TERRAIN_UNDERGROUND
    return bits


def _terrain_triplet_text(site_idx, surface_idx, depth_idx):
    site = _AREA_TERRAIN_SITE_CHOICES[int(site_idx)]
    surface = _AREA_TERRAIN_SURFACE_CHOICES[int(surface_idx)]
    depth = _AREA_TERRAIN_DEPTH_CHOICES[int(depth_idx)]
    return '%s / %s / %s' % (site, surface, depth)


def _build_script_set_payload(area, scripts):
    return {
        'schema': _SCRIPT_SET_SCHEMA,
        'version': _SCRIPT_SET_VERSION,
        'area_resref': _clean_resref(area.getGFFStruct('are').getInterpretedEntry('ResRef')),
        'scripts': dict(scripts),
    }


def _validate_script_set_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Script set file must contain a JSON object.')

    schema = payload.get('schema')
    if schema != _SCRIPT_SET_SCHEMA:
        raise ValueError('Unsupported script set schema: %r' % schema)

    version = payload.get('version')
    if version != _SCRIPT_SET_VERSION:
        raise ValueError('Unsupported script set version: %r' % version)

    scripts = payload.get('scripts')
    if not isinstance(scripts, dict):
        raise ValueError('Script set payload is missing a valid "scripts" object.')

    unknown_script_keys = sorted(k for k in scripts.keys() if k not in _SCRIPT_SET_KEYS)
    if unknown_script_keys:
        raise ValueError('Unknown script keys: %s' % ', '.join(unknown_script_keys))

    missing_keys = [k for k in _SCRIPT_SET_KEYS if k not in scripts]
    if missing_keys:
        raise ValueError('Missing required script keys: %s' % ', '.join(missing_keys))

    normalized = {}
    for key in _SCRIPT_SET_KEYS:
        value = scripts.get(key, '')
        if value is None:
            value = ''
        if not isinstance(value, (str, bytes)):
            raise ValueError('Script value for %s must be text.' % key)
        normalized[key] = _clean_resref(value)

    return normalized


def _get_terrain_type_summary(area):
    return _terrain_triplet_text(*_decode_terrain_triplet_from_flags(area['Flags']))


def _build_area_events_extras(parent, tab_sizer, prop_window, _tab_data, _area):
    script_keys = _SCRIPT_SET_KEYS

    row = wx.BoxSizer(wx.HORIZONTAL)
    load_btn = wx.Button(parent, -1, 'Load Script Set')
    save_btn = wx.Button(parent, -1, 'Save Script Set')
    row.Add(load_btn, 0, wx.RIGHT, 8)
    row.Add(save_btn, 0)
    tab_sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

    def _save_script_set(_event):
        data = {}
        for key in script_keys:
            control = prop_window.getControlByPropName(key)
            if control is not None:
                data[key] = _clean_resref(control.GetValue())
            else:
                data[key] = _clean_resref(_area[key])

        dlg = wx.FileDialog(parent,
                            'Save Script Set',
                            '',
                            'area_scripts.%s' % _SCRIPT_SET_FILE_EXTENSION,
                            'Neveredit Script Set (*.%s)|*.%s|JSON files (*.json)|*.json|All Files|*.*'
                            % (_SCRIPT_SET_FILE_EXTENSION, _SCRIPT_SET_FILE_EXTENSION),
                            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        payload = _build_script_set_payload(_area, data)

        try:
            with io.open(path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except (IOError, OSError, TypeError, ValueError) as exc:
            wx.MessageBox('Failed to save script set: %s' % str(exc),
                          'Save Script Set', wx.OK | wx.ICON_ERROR, parent)

    def _load_script_set(_event):
        dlg = wx.FileDialog(parent,
                            'Load Script Set',
                            '',
                            '',
                            'Neveredit Script Set (*.%s)|*.%s|JSON files (*.json)|*.json|All Files|*.*'
                            % (_SCRIPT_SET_FILE_EXTENSION, _SCRIPT_SET_FILE_EXTENSION),
                            wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        try:
            with io.open(path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
        except (IOError, OSError, TypeError, ValueError) as exc:
            wx.MessageBox('Failed to load script set: %s' % str(exc),
                          'Load Script Set', wx.OK | wx.ICON_ERROR, parent)
            return

        try:
            script_values = _validate_script_set_payload(data)
        except ValueError as exc:
            wx.MessageBox('Invalid script set file: %s' % str(exc),
                          'Load Script Set', wx.OK | wx.ICON_ERROR, parent)
            return

        changed = False
        for key in script_keys:
            control = prop_window.getControlByPropName(key)
            if control is not None:
                control.SetValue(_clean_resref(script_values.get(key, '')))
                changed = True

        if changed:
            prop_window.propsChanged = True

    load_btn.Bind(wx.EVT_BUTTON, _load_script_set)
    save_btn.Bind(wx.EVT_BUTTON, _save_script_set)


def _build_area_advanced_extras(parent, tab_sizer, _prop_window, _tab_data, area):
    terrain_box = wx.StaticBoxSizer(wx.StaticBox(parent, -1, 'Terrain Type'), wx.VERTICAL)
    terrain_grid = wx.FlexGridSizer(3, 2, 6, 8)

    current_site, current_surface, current_depth = _decode_terrain_triplet_from_flags(area['Flags'])

    terrain_grid.Add(wx.StaticText(parent, -1, 'Type 1:'), 0,
                     wx.ALIGN_CENTER_VERTICAL)
    site_choice = wx.Choice(parent, -1,
                            choices=[str(v) for v in _AREA_TERRAIN_SITE_CHOICES])
    site_choice.SetSelection(current_site)
    terrain_grid.Add(site_choice, 0, wx.EXPAND)

    terrain_grid.Add(wx.StaticText(parent, -1, 'Type 2:'), 0,
                     wx.ALIGN_CENTER_VERTICAL)
    surface_choice = wx.Choice(parent, -1,
                               choices=[str(v) for v in _AREA_TERRAIN_SURFACE_CHOICES])
    surface_choice.SetSelection(current_surface)
    terrain_grid.Add(surface_choice, 0, wx.EXPAND)

    terrain_grid.Add(wx.StaticText(parent, -1, 'Type 3:'), 0,
                     wx.ALIGN_CENTER_VERTICAL)
    depth_choice = wx.Choice(parent, -1,
                             choices=[str(v) for v in _AREA_TERRAIN_DEPTH_CHOICES])
    depth_choice.SetSelection(current_depth)
    terrain_grid.Add(depth_choice, 0, wx.EXPAND)

    terrain_box.Add(terrain_grid, 0, wx.ALL | wx.EXPAND, 6)
    tab_sizer.Add(terrain_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

    info = wx.StaticBoxSizer(wx.StaticBox(parent, -1, 'Area Metadata'), wx.VERTICAL)
    resref = _clean_resref(area.getGFFStruct('are').getInterpretedEntry('ResRef'))
    info.Add(wx.StaticText(parent, -1,
                           'Check Modifier: Use Listen/Spot check modifiers above.'),
             0, wx.ALL, 4)
    info.Add(wx.StaticText(parent, -1, 'ResRef: %s' % (resref or '<none>')),
             0, wx.ALL, 4)
    info.Add(wx.StaticText(parent, -1,
                           'Terrain Flags (bitmask): %d' % _to_int(area['Flags'], 0)),
             0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
    tab_sizer.Add(info, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

    def _apply_terrain_changes():
        old_flags = _to_int(area['Flags'], 0)
        new_triplet_flags = _encode_terrain_triplet_to_flags(site_choice.GetSelection(),
                                                             surface_choice.GetSelection(),
                                                             depth_choice.GetSelection())
        new_flags = (old_flags & ~_AREA_FLAG_TERRAIN_MASK) | new_triplet_flags
        if new_flags == old_flags:
            return False
        area.setProperty('Flags', new_flags)
        return True

    return _apply_terrain_changes

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
                            area,
                            tab_builders={
                                'Events': _build_area_events_extras,
                                'Advanced': _build_area_advanced_extras,
                            })
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
