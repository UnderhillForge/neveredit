"""Area Wizard dialog for creating a new, blank NWN area."""

import re
import wx

from neveredit.util import neverglobals

# Friendly display names for well-known NWN 1.69 tilesets
_TILESET_NAMES = {
    'tde001': 'City Exterior',
    'tde002': 'City Interior',
    'tde003': 'Rural Exterior',
    'tde004': 'Rural Interior',
    'tde005': 'Dungeon',
    'tde006': 'Castle Exterior',
    'tde007': 'Castle Interior',
    'tde008': 'Mines',
    'tde009': 'Crypts',
    'tde010': 'Sewers',
    'tde011': 'Forest',
    'tde012': 'Rural Underground',
    'tde013': 'Desert Exterior',
    'tde014': 'Desert Interior',
    'tde015': 'Shore',
    'tde016': 'Water',
    'tde017': 'Harbor',
    'tde018': 'Ice',
    'tde019': 'Ice Cave',
    'tde020': 'Canyon',
    'tde021': 'Cave',
    'tbi001': 'Bioware Interior',
}


def _to_resref(name):
    """Derive a valid ResRef from a display name."""
    s = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:16]


class AreaWizard(wx.Dialog):
    """Single-page dialog that collects inputs for a new blank area."""

    SIZES = [8, 16, 24, 32]

    def __init__(self, parent):
        super().__init__(parent, title='New Area Wizard',
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._tilesets = []        # [(label, resref), ...]
        self._last_auto_resref = ''
        self._build_ui()
        self._populate_tilesets()
        self.Fit()
        self.SetMinSize(self.GetSize())

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        # Display name
        grid.Add(wx.StaticText(self, label='Display Name:'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.name_ctrl = wx.TextCtrl(self, size=(280, -1))
        self.name_ctrl.Bind(wx.EVT_TEXT, self._on_name_changed)
        grid.Add(self.name_ctrl, 1, wx.EXPAND)

        # ResRef
        grid.Add(wx.StaticText(self, label='ResRef (internal ID):'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.resref_ctrl = wx.TextCtrl(self, size=(280, -1))
        grid.Add(self.resref_ctrl, 1, wx.EXPAND)

        hint = wx.StaticText(self,
                             label='  Max 16 chars; letters, digits and _ only')
        hint.SetForegroundColour(wx.Colour(100, 100, 100))
        grid.Add(wx.StaticText(self, label=''), 0)
        grid.Add(hint, 0)

        # Tileset
        grid.Add(wx.StaticText(self, label='Tileset:'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.tileset_combo = wx.ComboBox(self, style=wx.CB_READONLY)
        self.tileset_combo.Bind(wx.EVT_COMBOBOX, self._on_tileset_changed)
        grid.Add(self.tileset_combo, 1, wx.EXPAND)

        # Tileset preview (metadata only; no rendered map image)
        grid.Add(wx.StaticText(self, label='Tileset Preview:'),
             0, wx.ALIGN_TOP)
        self.tileset_preview = wx.StaticText(self, label='')
        self.tileset_preview.SetForegroundColour(wx.Colour(60, 60, 60))
        grid.Add(self.tileset_preview, 1, wx.EXPAND)

        # Width
        grid.Add(wx.StaticText(self, label='Width (tiles):'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.width_combo = wx.ComboBox(
            self, choices=[str(s) for s in self.SIZES], style=wx.CB_READONLY)
        self.width_combo.SetSelection(0)   # default 8
        grid.Add(self.width_combo, 1, wx.EXPAND)

        # Height
        grid.Add(wx.StaticText(self, label='Height (tiles):'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.height_combo = wx.ComboBox(
            self, choices=[str(s) for s in self.SIZES], style=wx.CB_READONLY)
        self.height_combo.SetSelection(0)  # default 8
        grid.Add(self.height_combo, 1, wx.EXPAND)

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 12)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        self.SetSizer(outer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    # ----------------------------------------------------------- population --

    def _populate_tilesets(self):
        """Populate the tileset combo from the ResourceManager, with fallback."""
        rm = neverglobals.getResourceManager()
        self._tilesets = []
        if rm is not None:
            try:
                keys = rm.getKeysWithExtensions('SET')
                seen = set()
                for resref, _rtype in sorted(keys):
                    r = rm.normalizeResRef(resref)
                    if r and r not in seen:
                        seen.add(r)
                        friendly = _TILESET_NAMES.get(r, '')
                        label = '%s - %s' % (r, friendly) if friendly else r
                        self._tilesets.append((label, r))
            except Exception:
                pass

        if not self._tilesets:
            # Fallback: hardcoded well-known tilesets
            for resref in sorted(_TILESET_NAMES):
                label = '%s - %s' % (resref, _TILESET_NAMES[resref])
                self._tilesets.append((label, resref))

        self.tileset_combo.Clear()
        for label, _r in self._tilesets:
            self.tileset_combo.Append(label)
        if self._tilesets:
            self.tileset_combo.SetSelection(0)
            self._update_tileset_preview(0)

    def _lookup_tileset_metadata(self, resref):
        """Fetch lightweight metadata from a .SET resource when available."""
        meta = {}
        rm = neverglobals.getResourceManager()
        if not rm:
            return meta

        try:
            ts = rm.getResourceByName(resref + '.set')
        except Exception:
            ts = None
        if not ts:
            return meta

        try:
            meta['tile_count'] = ts.getTileCount()
        except Exception:
            pass
        try:
            meta['group_count'] = ts.getGroupCount()
        except Exception:
            pass
        for section in ('GENERAL', 'General'):
            try:
                if ts.has_option(section, 'DisplayName'):
                    name = ts.get(section, 'DisplayName').strip()
                    if name:
                        meta['display_name'] = name
                        break
            except Exception:
                pass
        return meta

    def _update_tileset_preview(self, idx):
        if idx == wx.NOT_FOUND or idx < 0 or idx >= len(self._tilesets):
            self.tileset_preview.SetLabel('')
            return

        label, resref = self._tilesets[idx]
        meta = self._lookup_tileset_metadata(resref)

        lines = [
            'Selected: %s' % label,
            'ResRef: %s' % resref,
        ]
        if 'display_name' in meta:
            lines.append('Display Name: %s' % meta['display_name'])
        if 'tile_count' in meta:
            lines.append('Tiles: %d' % meta['tile_count'])
        if 'group_count' in meta:
            lines.append('Groups: %d' % meta['group_count'])
        if len(lines) == 2:
            lines.append('No additional metadata available.')

        self.tileset_preview.SetLabel('\n'.join(lines))
        self.Layout()

    # --------------------------------------------------------------- events --

    def _on_name_changed(self, event):
        name = self.name_ctrl.GetValue()
        auto = _to_resref(name)
        current = self.resref_ctrl.GetValue()
        if current == '' or current == self._last_auto_resref:
            self.resref_ctrl.ChangeValue(auto)
            self._last_auto_resref = auto
        event.Skip()

    def _on_tileset_changed(self, event):
        self._update_tileset_preview(self.tileset_combo.GetSelection())
        event.Skip()

    def _on_ok(self, event):
        name = self.name_ctrl.GetValue().strip()
        resref = self.resref_ctrl.GetValue().strip().lower()

        if not name:
            wx.MessageBox('Please enter a display name.', 'Validation',
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not resref:
            wx.MessageBox('Please enter a ResRef.', 'Validation',
                          wx.OK | wx.ICON_WARNING, self)
            return
        if len(resref) > 16:
            wx.MessageBox('ResRef must be 16 characters or less.', 'Validation',
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not re.match(r'^[a-z0-9_]+$', resref):
            wx.MessageBox(
                'ResRef may only contain letters, digits and underscores.',
                'Validation', wx.OK | wx.ICON_WARNING, self)
            return
        if self.tileset_combo.GetSelection() == wx.NOT_FOUND:
            wx.MessageBox('Please select a tileset.', 'Validation',
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.EndModal(wx.ID_OK)

    # ---------------------------------------------------------------- query --

    def getResults(self):
        """Return a dict with name/resref/tileset/width/height, or None."""
        idx = self.tileset_combo.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._tilesets):
            return None
        _, tileset_resref = self._tilesets[idx]
        width = self.SIZES[self.width_combo.GetSelection()]
        height = self.SIZES[self.height_combo.GetSelection()]
        return {
            'name': self.name_ctrl.GetValue().strip(),
            'resref': self.resref_ctrl.GetValue().strip().lower(),
            'tileset': tileset_resref,
            'width': width,
            'height': height,
        }


def show_area_wizard(parent):
    """Show the Area Wizard.  Returns a results dict on OK, or None on cancel."""
    dlg = AreaWizard(parent)
    try:
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.getResults()
        return None
    finally:
        dlg.Destroy()
