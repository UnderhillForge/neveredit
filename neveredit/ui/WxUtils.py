import wx

def bitmapFromImage(i):
    rgb = i.convert('RGB')
    image = wx.Image(rgb.size[0], rgb.size[1])
    image.SetData(rgb.tobytes())
    return wx.Bitmap(image)
    
