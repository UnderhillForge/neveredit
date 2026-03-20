"""Area creation wizard (NWN Toolset style flow)."""

import re

import wx
import wx.adv

from neveredit.ui import WxUtils
from neveredit.util import neverglobals


_PREFERRED_TILESET_ORDER = [
    'barrows interior',
    'beholder caves',
    'castle exterior',
    'rural',
    'castle interior',
    'castle interior 2',
    'city exterior',
    'city interior',
    'city interior 2',
    'crypt',
    'desert',
    'drow interior',
    'dungeon',
    'early winter2',
    'forest',
    'forest - facelift',
    'fort interior',
    'lizardfolk interior',
    'medieval city 2',
    'medieval rural 2',
    'microset',
    'mines and caverns',
    'ruins',
    'rural winter',
    'rural winter - facelift',
    'sea caves',
    'sea ships',
    'sewers',
    'steamworks',
    'tropical',
    'underdark',
]

_TILESET_FRIENDLY_OVERRIDES = {
    'tde001': 'City Exterior',
    'tde002': 'City Interior',
    'tde003': 'Rural',
    'tde004': 'Castle Interior',
    'tde005': 'Dungeon',
    'tde006': 'Castle Exterior',
    'tde007': 'Crypt',
    'tde008': 'Mines and Caverns',
    'tde009': 'Sewers',
    'tde010': 'Forest',
    'tde013': 'Desert',
}


def _to_resref(name):
    text = re.sub(r'[^a-zA-Z0-9_]', '_', (name or '').lower())
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:16]


def _normalize_name(name):
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def _friendly_name_from_resref(resref):
    """Derive a readable fallback label from a tileset resref."""
    text = (resref or '').strip().replace('_', ' ').replace('-', ' ')
    # Strip common NWN tileset prefixes (e.g. tde, tcn) and leading digits.
    text = re.sub(r'^[a-z]{2,4}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\d+', '', text)
    text = re.sub(r'\d+$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return (resref or '').upper()
    return text.title()


class AreaWizard(wx.adv.Wizard):
    """Multi-step wizard for creating a blank area."""

    SIZE_PRESETS = [
        ('Tiny', 8, 8),
        ('Small', 16, 16),
        ('Medium', 24, 24),
        ('Large', 32, 32),
        ('Custom', None, None),
    ]

    def __init__(self, parent):
        wx.adv.Wizard.__init__(self, parent, title='Area Wizard')
        self._completed = False
        self._last_auto_resref = ''
        self.state = {
            'name': '',
            'resref': '',
            'tileset': '',
            'width': 8,
            'height': 8,
            'launch_area_properties': False,
            'open_area_viewer': True,
        }
        self._tilesets = self._discover_tilesets()

        self.page_name = wx.adv.WizardPageSimple(self)
        self.page_tileset = wx.adv.WizardPageSimple(self)
        self.page_size = wx.adv.WizardPageSimple(self)
        self.page_finish = wx.adv.WizardPageSimple(self)
        wx.adv.WizardPageSimple.Chain(self.page_name, self.page_tileset)
        wx.adv.WizardPageSimple.Chain(self.page_tileset, self.page_size)
        wx.adv.WizardPageSimple.Chain(self.page_size, self.page_finish)

        self._build_name_page()
        self._build_tileset_page()
        self._build_size_page()
        self._build_finish_page()
        self.GetPageAreaSizer().Add(self.page_name)

        self.Bind(wx.adv.EVT_WIZARD_PAGE_CHANGING, self._on_page_changing)
        self.Bind(wx.adv.EVT_WIZARD_PAGE_CHANGED, self._on_page_changed)
        self.Bind(wx.adv.EVT_WIZARD_FINISHED, self._on_wizard_finished)

    def getResults(self):
        if not self._completed:
            return None
        return dict(self.state)

    def _build_name_page(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(wx.StaticText(self.page_name,
                                label='Enter a name for the new area.'),
                  0, wx.ALL, 8)

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self.page_name, label='Area Name:'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.name_ctrl = wx.TextCtrl(self.page_name, size=(320, -1))
        self.name_ctrl.Bind(wx.EVT_TEXT, self._on_name_changed)
        grid.Add(self.name_ctrl, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self.page_name, label='ResRef (internal):'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.resref_ctrl = wx.TextCtrl(self.page_name, size=(320, -1))
        grid.Add(self.resref_ctrl, 1, wx.EXPAND)

        hint = wx.StaticText(self.page_name,
                             label='Max 16 chars; letters, digits and _ only.')
        hint.SetForegroundColour(WxUtils.getMutedTextColour(self.page_name))
        grid.Add(wx.StaticText(self.page_name, label=''), 0)
        grid.Add(hint, 0)

        outer.Add(grid, 0, wx.ALL | wx.EXPAND, 8)
        self.page_name.SetSizer(outer)

    def _build_tileset_page(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(wx.StaticText(self.page_tileset,
                                label='Choose a tileset for this area.'),
                  0, wx.ALL, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self.page_tileset, label='Tileset:'),
                0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.tileset_combo = wx.ComboBox(self.page_tileset, style=wx.CB_READONLY)
        for entry in self._tilesets:
            self.tileset_combo.Append(entry['label'])
        if self._tilesets:
            self.tileset_combo.SetSelection(0)
        self.tileset_combo.Bind(wx.EVT_COMBOBOX, self._on_tileset_changed)
        row.Add(self.tileset_combo, 1, wx.EXPAND)
        outer.Add(row, 0, wx.ALL | wx.EXPAND, 8)

        self.tileset_preview = wx.StaticText(self.page_tileset, label='')
        self.tileset_preview.SetForegroundColour(WxUtils.getMutedTextColour(self.page_tileset))
        outer.Add(self.tileset_preview, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        self.page_tileset.SetSizer(outer)
        self._update_tileset_preview(self.tileset_combo.GetSelection())

    def _build_size_page(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(wx.StaticText(self.page_size,
                                label='Choose area size by preset or custom Width/Height.'),
                  0, wx.ALL, 8)

        choices = [label for label, _w, _h in self.SIZE_PRESETS]
        self.size_choice = wx.RadioBox(self.page_size,
                                       label='Size Preset',
                                       choices=choices,
                                       majorDimension=1,
                                       style=wx.RA_SPECIFY_COLS)
        self.size_choice.SetSelection(0)
        self.size_choice.Bind(wx.EVT_RADIOBOX, self._on_size_preset_changed)
        outer.Add(self.size_choice, 0, wx.ALL, 8)

        grid = wx.FlexGridSizer(rows=0, cols=2, vgap=6, hgap=8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self.page_size, label='Width:'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.width_spin = wx.SpinCtrl(self.page_size, min=4, max=64, initial=8)
        grid.Add(self.width_spin, 0)

        grid.Add(wx.StaticText(self.page_size, label='Height:'),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.height_spin = wx.SpinCtrl(self.page_size, min=4, max=64, initial=8)
        grid.Add(self.height_spin, 0)

        outer.Add(grid, 0, wx.ALL, 8)
        self.page_size.SetSizer(outer)
        self._apply_size_preset()

    def _build_finish_page(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        self.finish_summary = wx.StaticText(self.page_finish, label='')
        outer.Add(self.finish_summary, 0, wx.ALL | wx.EXPAND, 8)

        self.launch_props_check = wx.CheckBox(
            self.page_finish,
            label='Launch Area Properties Dialog')
        self.open_viewer_check = wx.CheckBox(
            self.page_finish,
            label='Open Area in the Area Viewer')
        self.open_viewer_check.SetValue(True)
        outer.Add(self.launch_props_check, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        outer.Add(self.open_viewer_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.page_finish.SetSizer(outer)

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

    def _on_size_preset_changed(self, event):
        self._apply_size_preset()
        event.Skip()

    def _apply_size_preset(self):
        idx = self.size_choice.GetSelection()
        _label, width, height = self.SIZE_PRESETS[idx]
        custom = width is None or height is None
        self.width_spin.Enable(custom)
        self.height_spin.Enable(custom)
        if not custom:
            self.width_spin.SetValue(width)
            self.height_spin.SetValue(height)

    def _on_page_changing(self, event):
        if not event.GetDirection():
            return

        page = event.GetPage()
        if page == self.page_name:
            name = self.name_ctrl.GetValue().strip()
            resref = self.resref_ctrl.GetValue().strip().lower()
            if not name:
                wx.MessageBox('Please enter an area name.', 'Validation',
                              wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            if not resref:
                wx.MessageBox('Please enter a ResRef.', 'Validation',
                              wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            if len(resref) > 16:
                wx.MessageBox('ResRef must be 16 characters or less.', 'Validation',
                              wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            if not re.match(r'^[a-z0-9_]+$', resref):
                wx.MessageBox('ResRef may only contain letters, digits and underscores.',
                              'Validation', wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            self.state['name'] = name
            self.state['resref'] = resref

        elif page == self.page_tileset:
            idx = self.tileset_combo.GetSelection()
            if idx == wx.NOT_FOUND or idx < 0 or idx >= len(self._tilesets):
                wx.MessageBox('Please choose a tileset.', 'Validation',
                              wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            self.state['tileset'] = self._tilesets[idx]['resref']

        elif page == self.page_size:
            width = int(self.width_spin.GetValue())
            height = int(self.height_spin.GetValue())
            if width < 4 or height < 4:
                wx.MessageBox('Width and Height must be at least 4.', 'Validation',
                              wx.OK | wx.ICON_WARNING, self)
                event.Veto()
                return
            self.state['width'] = width
            self.state['height'] = height

    def _on_page_changed(self, event):
        if event.GetPage() == self.page_finish:
            self._refresh_finish_summary()
        event.Skip()

    def _on_wizard_finished(self, event):
        self.state['launch_area_properties'] = bool(self.launch_props_check.GetValue())
        self.state['open_area_viewer'] = bool(self.open_viewer_check.GetValue())
        self._completed = True
        event.Skip()

    def _refresh_finish_summary(self):
        lines = [
            'This area is now ready to be created.',
            'Click Finish to add the area to your module.',
            '',
            'Name: %s' % self.state.get('name', ''),
            'ResRef: %s' % self.state.get('resref', ''),
            'Tileset: %s' % self.state.get('tileset', ''),
            'Size: %sx%s' % (self.state.get('width', 0), self.state.get('height', 0)),
        ]
        self.finish_summary.SetLabel('\n'.join(lines))
        self.page_finish.Layout()

    def _tileset_sort_key(self, entry):
        preferred = _normalize_name(entry.get('friendly_name', ''))
        try:
            order = _PREFERRED_TILESET_ORDER.index(preferred)
        except ValueError:
            order = len(_PREFERRED_TILESET_ORDER) + 1
        return (order, preferred, entry['resref'])

    def _discover_tilesets(self):
        result = []
        rm = neverglobals.getResourceManager()
        seen = set()

        if rm is not None:
            try:
                keys = sorted(rm.getKeysWithExtensions('SET'))
            except Exception:
                keys = []

            for resref, _rtype in keys:
                r = rm.normalizeResRef(resref)
                if not r or r in seen:
                    continue
                seen.add(r)
                meta = self._lookup_tileset_metadata(r)
                friendly = (meta.get('display_name') or
                            _TILESET_FRIENDLY_OVERRIDES.get(r) or
                            _friendly_name_from_resref(r))
                # Keep chooser text clean and user-facing; resref remains in preview.
                label = friendly
                result.append({
                    'resref': r,
                    'friendly_name': friendly,
                    'label': label,
                    'meta': meta,
                })

        if not result:
            for resref in sorted(_TILESET_FRIENDLY_OVERRIDES.keys()):
                friendly = _TILESET_FRIENDLY_OVERRIDES[resref]
                result.append({
                    'resref': resref,
                    'friendly_name': friendly,
                    'label': friendly,
                    'meta': {},
                })

        result.sort(key=self._tileset_sort_key)
        return result

    def _lookup_tileset_metadata(self, resref):
        meta = {}
        rm = neverglobals.getResourceManager()
        if not rm:
            return meta

        try:
            tileset = rm.getResourceByName(resref + '.set')
        except Exception:
            tileset = None

        if not tileset:
            return meta

        try:
            meta['tile_count'] = int(tileset.getTileCount())
        except Exception:
            pass
        try:
            meta['group_count'] = int(tileset.getGroupCount())
        except Exception:
            pass

        for section in ('GENERAL', 'General'):
            for key in ('DisplayName', 'Name'):
                try:
                    if tileset.has_option(section, key):
                        value = tileset.get(section, key).strip()
                        if value:
                            meta['display_name'] = value
                            return meta
                except Exception:
                    continue
        return meta

    def _update_tileset_preview(self, idx):
        if idx == wx.NOT_FOUND or idx < 0 or idx >= len(self._tilesets):
            self.tileset_preview.SetLabel('')
            return

        entry = self._tilesets[idx]
        meta = entry.get('meta', {})
        lines = [
            'Selected: %s' % entry['friendly_name'],
            'ResRef: %s' % entry['resref'],
        ]
        if 'tile_count' in meta:
            lines.append('Tiles: %d' % meta['tile_count'])
        if 'group_count' in meta:
            lines.append('Groups: %d' % meta['group_count'])
        if len(lines) == 2:
            lines.append('No additional metadata available.')
        self.tileset_preview.SetLabel('\n'.join(lines))
        self.page_tileset.Layout()


def show_area_wizard(parent):
    """Show the Area Wizard. Returns results dict on finish, or None."""
    wizard = AreaWizard(parent)
    try:
        if wizard.RunWizard(wizard.page_name):
            return wizard.getResults()
        return None
    finally:
        wizard.Destroy()
