import wx


class MapLayersWindow(wx.MiniFrame):
    """Small layer-visibility panel for map rendering toggles."""

    def __init__(self, parent, onLayersChanged, initialLayers=None):
        wx.MiniFrame.__init__(self, parent, -1, "Map Layers", wx.DefaultPosition, wx.Size(250, 250))
        self._onLayersChanged = onLayersChanged
        self._checkboxes = {}

        panel = wx.Panel(self, -1)
        sizer = wx.BoxSizer(wx.VERTICAL)

        if initialLayers is None:
            initialLayers = {}

        specs = [
            ("showTiles", "Show Tiles"),
            ("showObjects", "Show Objects"),
            ("showAmbient", "Show Ambient Sounds"),
            ("showGrid", "Show Grid Overlay"),
            ("showWaypoints", "Show Waypoints"),
            ("showPaths", "Show Paths"),
        ]

        for key, label in specs:
            cb = wx.CheckBox(panel, -1, label)
            cb.SetValue(bool(initialLayers.get(key, True)))
            cb.Bind(wx.EVT_CHECKBOX, self._emitChange)
            sizer.Add(cb, 0, wx.ALL, 6)
            self._checkboxes[key] = cb

        panel.SetSizer(sizer)
        self.SetMinSize(wx.Size(220, 220))

    def _emitChange(self, _evt=None):
        if not self._onLayersChanged:
            return
        state = {}
        for key, cb in list(self._checkboxes.items()):
            state[key] = bool(cb.GetValue())
        self._onLayersChanged(state)

    def setLayers(self, layers):
        for key, value in list(layers.items()):
            cb = self._checkboxes.get(key)
            if cb is not None:
                cb.SetValue(bool(value))

    def getLayers(self):
        result = {}
        for key, cb in list(self._checkboxes.items()):
            result[key] = bool(cb.GetValue())
        return result
