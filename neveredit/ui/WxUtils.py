import wx

def bitmapFromImage(i):
    rgb = i.convert('RGB')
    image = wx.Image(rgb.size[0], rgb.size[1])
    image.SetData(rgb.tobytes())
    return wx.Bitmap(image)


def blendColours(base, target, ratio):
    ratio = max(0.0, min(1.0, float(ratio)))
    return wx.Colour(
        int(round(base.Red() + ((target.Red() - base.Red()) * ratio))),
        int(round(base.Green() + ((target.Green() - base.Green()) * ratio))),
        int(round(base.Blue() + ((target.Blue() - base.Blue()) * ratio)))
    )


def _safeSystemColour(system_id, fallback):
    if system_id is None:
        return fallback
    try:
        colour = wx.SystemSettings.GetColour(system_id)
        if colour and colour.IsOk():
            return colour
    except Exception:
        pass
    return fallback


def getWindowBackgroundColour(window=None):
    fallback = wx.Colour(255, 255, 255)
    if window:
        try:
            colour = window.GetBackgroundColour()
            if colour and colour.IsOk():
                fallback = colour
        except Exception:
            pass
    return _safeSystemColour(getattr(wx, 'SYS_COLOUR_WINDOW', None), fallback)


def getPanelBackgroundColour(window=None):
    fallback = getWindowBackgroundColour(window)
    return _safeSystemColour(getattr(wx, 'SYS_COLOUR_BTNFACE', None), fallback)


def getTextColour(window=None):
    fallback = wx.Colour(0, 0, 0)
    if window:
        try:
            colour = window.GetForegroundColour()
            if colour and colour.IsOk():
                fallback = colour
        except Exception:
            pass
    return _safeSystemColour(getattr(wx, 'SYS_COLOUR_WINDOWTEXT', None), fallback)


def _luminance(colour):
    return ((0.2126 * float(colour.Red())) +
            (0.7152 * float(colour.Green())) +
            (0.0722 * float(colour.Blue())))


def isDarkMode(window=None):
    try:
        appearance = wx.SystemSettings.GetAppearance()
        if appearance and hasattr(appearance, 'IsDark'):
            return bool(appearance.IsDark())
    except Exception:
        pass
    return _luminance(getWindowBackgroundColour(window)) < 128.0


def getMutedTextColour(window=None):
    text = getTextColour(window)
    background = getWindowBackgroundColour(window)
    return blendColours(text, background, 0.45 if isDarkMode(window) else 0.35)


def getWarningBackgroundColour(window=None):
    background = getWindowBackgroundColour(window)
    warning = wx.Colour(255, 220, 220)
    return blendColours(background, warning, 0.34 if isDarkMode(window) else 0.82)


def captureWindowState(window, current_state=None):
    if not window:
        return current_state
    state = dict(current_state or {})
    try:
        state['maximized'] = bool(window.IsMaximized())
    except Exception:
        state['maximized'] = False
    try:
        if not window.IsIconized() and not window.IsMaximized():
            rect = window.GetRect()
            state.update({
                'x': int(rect.x),
                'y': int(rect.y),
                'w': int(rect.width),
                'h': int(rect.height),
            })
    except Exception:
        pass
    return state or None


def applyWindowState(window, state, min_size=None):
    from neveredit.util import plistlib
    if not window or not isinstance(state, (dict, plistlib.Dict)):
        return False
    import sys
    try:
        x = int(state.get('x'))
        y = int(state.get('y'))
        w = int(state.get('w'))
        h = int(state.get('h'))
        print(f"[WxUtils.applyWindowState] x={x} y={y} w={w} h={h}", file=sys.stderr)
    except Exception as e:
        x = y = w = h = None
        print(f"[WxUtils.applyWindowState] Failed to extract coords from {state}: {e}", file=sys.stderr)

    min_w = 0
    min_h = 0
    if min_size:
        try:
            min_w = int(min_size[0])
            min_h = int(min_size[1])
        except Exception:
            min_w = 0
            min_h = 0
    else:
        try:
            current_min = window.GetMinSize()
            min_w = int(max(0, current_min.width))
            min_h = int(max(0, current_min.height))
        except Exception:
            pass

    if w is not None and h is not None:
        w = max(min_w, w)
        h = max(min_h, h)

    if None not in (x, y, w, h):
        try:
            display_index = wx.Display.GetFromPoint(wx.Point(x, y))
            if display_index == wx.NOT_FOUND:
                display_index = wx.Display.GetFromWindow(window)
            if display_index == wx.NOT_FOUND:
                display_index = 0
            bounds = wx.Display(display_index).GetClientArea()
            max_x = bounds.x + max(0, bounds.width - w)
            max_y = bounds.y + max(0, bounds.height - h)
            x = min(max(x, bounds.x), max_x)
            y = min(max(y, bounds.y), max_y)
            print(f"[WxUtils.applyWindowState] Setting to x={x} y={y} w={w} h={h}", file=sys.stderr)
            window.SetSize(wx.Rect(x, y, w, h))
        except Exception as e:
            print(f"[WxUtils.applyWindowState] Error: {e}", file=sys.stderr)
            window.SetSize((w, h))

    try:
        if state.get('maximized'):
            window.Maximize(True)
    except Exception:
        pass
    return True
    
