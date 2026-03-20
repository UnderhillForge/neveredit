import wx


class MapLayersWindow(wx.MiniFrame):
    """Small layer-visibility panel for map rendering toggles."""

    def __init__(self, parent, onLayersChanged, initialLayers=None, onGeometryChanged=None, onVisibilityChanged=None):
        wx.MiniFrame.__init__(self, parent, -1, "Map Layers", wx.DefaultPosition, wx.Size(250, 280))
        self._onLayersChanged = onLayersChanged
        self._onGeometryChanged = onGeometryChanged
        self._onVisibilityChanged = onVisibilityChanged
        self._checkboxes = {}

        panel = wx.Panel(self, -1)
        sizer = wx.BoxSizer(wx.VERTICAL)

        if initialLayers is None:
            initialLayers = {}

        specs = [
            ("showGrid", "Show Grid"),
            ("showCreatures", "Show Creatures"),
            ("showDoors", "Show Doors"),
            ("showEncounters", "Show Encounters"),
            ("showItems", "Show Items"),
            ("showMerchants", "Show Merchants"),
            ("showPlaceables", "Show Placeables"),
            ("showSounds", "Show Sounds"),
            ("showWaypoints", "Show Waypoints"),
            ("showStartLocation", "Show Start Location"),
        ]

        for key, label in specs:
            cb = wx.CheckBox(panel, -1, label)
            cb.SetValue(bool(initialLayers.get(key, True)))
            cb.Bind(wx.EVT_CHECKBOX, self._emitChange)
            sizer.Add(cb, 0, wx.ALL, 6)
            self._checkboxes[key] = cb

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        show_all = wx.Button(panel, -1, "Show All")
        show_none = wx.Button(panel, -1, "Show None")
        show_all.Bind(wx.EVT_BUTTON, self._onShowAll)
        show_none.Bind(wx.EVT_BUTTON, self._onShowNone)
        buttons.Add(show_all, 1, wx.RIGHT, 6)
        buttons.Add(show_none, 1)
        sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(sizer)
        self.SetMinSize(wx.Size(220, 250))
        self.Bind(wx.EVT_MOVE, self._onWindowGeometryEvent)
        self.Bind(wx.EVT_SIZE, self._onWindowGeometryEvent)
        self.Bind(wx.EVT_CLOSE, self._onClose)

    def _emitChange(self, _evt=None):
        if not self._onLayersChanged:
            return
        state = {}
        for key, cb in list(self._checkboxes.items()):
            state[key] = bool(cb.GetValue())
        self._onLayersChanged(state)

    def _setAll(self, enabled):
        for cb in list(self._checkboxes.values()):
            cb.SetValue(bool(enabled))
        self._emitChange()

    def _onShowAll(self, _evt):
        self._setAll(True)

    def _onShowNone(self, _evt):
        self._setAll(False)

    def _onWindowGeometryEvent(self, evt):
        self._emitGeometryChange()
        evt.Skip()

    def _emitGeometryChange(self):
        if not self._onGeometryChanged:
            return
        self._onGeometryChanged(self.getWindowGeometry())

    def _emitVisibilityChange(self, visible):
        if not self._onVisibilityChanged:
            return
        self._onVisibilityChanged(bool(visible))

    def _onClose(self, evt):
        # Keep the panel reusable; hide instead of destroying on close button.
        if evt.CanVeto():
            self.Hide()
            self._emitVisibilityChange(False)
            evt.Veto()
        else:
            evt.Skip()

    def getWindowGeometry(self):
        pos = self.GetPosition()
        size = self.GetSize()
        return {
            "x": int(pos.x),
            "y": int(pos.y),
            "w": int(size.width),
            "h": int(size.height),
        }

    def applyWindowGeometry(self, geometry):
        if not isinstance(geometry, dict):
            return
        try:
            x = int(geometry.get("x", self.GetPosition().x))
            y = int(geometry.get("y", self.GetPosition().y))
            w = int(geometry.get("w", self.GetSize().width))
            h = int(geometry.get("h", self.GetSize().height))
        except Exception:
            return
        w = max(220, w)
        h = max(250, h)

        display_index = wx.Display.GetFromPoint(wx.Point(x, y))
        if display_index == wx.NOT_FOUND:
            display_index = wx.Display.GetFromWindow(self)
        if display_index == wx.NOT_FOUND:
            display_index = 0
        bounds = wx.Display(display_index).GetClientArea()

        max_x = bounds.x + max(0, bounds.width - w)
        max_y = bounds.y + max(0, bounds.height - h)
        x = min(max(x, bounds.x), max_x)
        y = min(max(y, bounds.y), max_y)
        self.SetSize(wx.Rect(x, y, w, h))

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
