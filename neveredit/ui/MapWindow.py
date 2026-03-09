import logging
logger = logging.getLogger('neveredit.ui')

from neveredit.util import Utils
Numeric = Utils.getNumPy()

import wx
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import sys
import io
import copy
import threading
import math
import os
import json
Set = set
import time
import profile
import copy

from neveredit.ui.GLWindow import GLWindow
from neveredit.ui import ToolPalette
from neveredit.game.Module import Module
from neveredit.game.Sound import SoundInstance
from neveredit.game.ResourceManager import ResourceManager
from neveredit.game.ChangeNotification import VisualChangeListener
from neveredit.util.Progressor import Progressor
from neveredit.util import neverglobals
from neveredit.file.GFFFile import GFFStruct
from neveredit.file import SoundSetFile

SINGLESELECTIONEVENT = wx.NewEventType()

def EVT_MAPSINGLESELECTION(window,function):
    '''notifies about the selection of a single object in the map'''
    window.Connect(-1,-1,SINGLESELECTIONEVENT,function)

class SingleSelectionEvent(wx.PyCommandEvent):
    eventType = SINGLESELECTIONEVENT
    def __init__(self,windowID,oid):
        wx.PyCommandEvent.__init__(self,self.eventType,windowID)
        self.objectID = oid

    def getSelectedId(self):
        return self.objectID
    
    def Clone(self):
        evt = self.__class__(self.GetId(),self.objectID)
        return evt
        

OBJECTSELECTIONEVENT = wx.NewEventType()

def EVT_MAPOBJECTSELECTION(window,function):
    '''notifies about the selection of a single object in the map'''
    window.Connect(-1,-1,OBJECTSELECTIONEVENT,function)

class ObjectSelectionEvent(SingleSelectionEvent):
    eventType = OBJECTSELECTIONEVENT

THINGADDEDEVENT = wx.NewEventType()
EVT_MAPTHINGADDED = wx.PyEventBinder(THINGADDEDEVENT, 0)

class ThingAddedEvent(wx.PyCommandEvent):
    eventType = THINGADDEDEVENT
    def __init__(self,windowID,oid):
        wx.PyCommandEvent.__init__(self,self.eventType,windowID)
        self.oid = oid
        
    def getSelectedId(self):
        return self.oid
    
    def Clone(self):
        evt = ThingAddedEvent(self.GetId(),self.oid)
        return evt

MOVEEVENT = wx.NewEventType()
def EVT_MAPMOVE(window,function):
    '''notifies about movement of objects in the map'''
    window.Connect(-1,-1,MOVEEVENT,function)

class MoveEvent(wx.PyCommandEvent):
    eventType = MOVEEVENT
    def __init__(self,windowID,oid,x,y,b):
        wx.PyCommandEvent.__init__(self,self.eventType,windowID)
        self.objectID = oid
        self.x = x
        self.y = y
        self.bearing = b
        
    def getObjectId(self):
        return self.objectID

    def getX(self):
        return self.x

    def getY(self):
        return self.y

    def getBearing(self):
        return self.bearing
    
    def Clone(self):
        evt = self.__class__(self.GetId(),self.objectID,self.x,self.y,self.bearing)
        return evt

class QuadTreeNode:
    def __init__(self):
        self.contents = {'things':[],'tiles':[]}
        self.boundingSphere = [[0,0,0],0]
        self.children = []
        self.xmin = 0
        self.xmax = 0
        self.ymin = 0
        self.ymax = 0
        
    def add(self,o):
        self.contents.append(o)

    def __str__(self):
        return '{xmin:' + repr(self.xmin) + ' xmax:' + repr(self.xmax)\
             + ' ymin:' + repr(self.ymin) + ' ymax:' + repr(self.ymax)\
             + repr(self.boundingSphere) + '}' # + ' - ' + `self.children` + '}'

    def __repr__(self):
        return self.__str__()

    def printNode(self):
        self.printHelper(self, '')
    
    def printHelper(self, node, indent):
        print(indent,repr(node))
        for row in node.children:
            for n in row:
                self.printHelper(n, indent + '  ')
                
class TextBox:
    def __init__(self):
        self.text = []

        self.fgcolour = (0.0,1.0,0.0,1.0)
        self.bgcolour = (0.0,0.0,0.0,0.55)
        
        self.red = 0.0
        self.blue = 0.0
        self.green = 0.0
        self.alpha = 0.55
        
        self.x = 0
        self.y = 0
        self.z = 0

        self.textWidth = 0
        self.textHeight = 0
        self.maxLine = ''
        
    def setText(self,text):
        self.text = text.split('\n')
        self.textWidth = 0
        for line in self.text:
            if len(line) > self.textWidth:
                self.textWidth = len(line)
                self.maxLine = line
        self.textHeight = len(self.text)
        
class MapWindow(GLWindow,Progressor,VisualChangeListener):
    def __init__(self,parent):
        GLWindow.__init__(self, parent)
        Progressor.__init__(self)
        
        self.zoom = 20
        self.maxZoom = 600
        
        self.players = {}
        self.area = None
        self.placeables = None
        self.doors = None
        self.creatures = None
        self.waypoints = None
        self.sounds = []
        self.lock = threading.Lock()
        self.highlight = None
        self.beingDragged = None
        self.beingPainted = None
        self.selected = []
        self.mode = ToolPalette.SELECTION_TOOL
        
        self.textBoxes = {}
        self.highlightBox = None
        
        self.fps = 0.0
        self.showFPS = False
        self.quadTreeRoot = None
        self.holdZ = 0
        self.lastX = 0
        self.lastY = 0
        self.Zmax = 0
        self.previewNightLighting = None
        self.ambientPreviewEnabled = False
        self.ambientUse3DDistance = False
        self._ambientPreviewLastUpdate = 0.0
        self._ambientPreviewMixerReady = False
        self._ambientPreviewActiveVoices = {}
        self._ambientPreviewMaxVoices = 4
        self._ambientPreviewDebugVoices = []
        self._ambientPreviewRawCache = {}
        self._ambientPreviewSSFCountCache = {}
        self.soundRadiusEditing = None

        # In-memory 2D drafting overlay for top-down terrain/height/object planning.
        self.map2DCells = {}
        self.map2DCellSize = 2.0
        self.map2DBrushRadius = 1
        self.map2DTerrainBrush = 0
        self.map2DAssetBrush = 1
        self.map2DHeightStep = 0.25
        self.map2DShowGrid = True
        self.map2DShowOcclusion = True

        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightMouseDown)

        neverglobals.getResourceManager().addVisualChangeListener(self)
        self.toPreprocess = None
        self._missingSelectionWarnings = set()
        self._missingModelWarnings = set()
        
    def Destroy(self):
        self._save2DDraftForCurrentArea()
        self._stopAmbientPreview()
        neverglobals.getResourceManager().removeVisualChangeListener(self)
        GLWindow.Destroy(self)
        
    def toolSelected(self,evt):
        self.mode = evt.getToolType()
        if self.mode == ToolPalette.PAINT_TOOL:
            self.beingPainted = evt.getData()
            if self.beingPainted and self.beingPainted.getModel():
                self.preprocessNodes(self.beingPainted.getModel(),
                                     'beingPainted',bbox=True)
                self.preprocessedModels.add(self.beingPainted.modelName)
            self.dragOffset = (10,10)
        elif self.mode == ToolPalette.AMBIENT_SOUND_TOOL:
            self.beingPainted = self._newAmbientSoundInstance()
            self.dragOffset = (10,10)
        elif self.mode == ToolPalette.MAP2D_DRAW_TOOL:
            self.beingPainted = None
        else:
            self.beingPainted = None

    def _newAmbientSoundInstance(self):
        gff = GFFStruct(SoundInstance.GFF_STRUCT_ID)
        gff.add('Tag', 'sound_region', 'CExoString')
        gff.add('LocName', '', 'CExoLocString')
        gff.add('TemplateResRef', '', 'ResRef')
        gff.add('SoundSet', '', 'ResRef')
        gff.add('SoundSetEvent', 1, 'INT')
        gff.add('SoundResRef', '', 'ResRef')
        gff.add('AttenuationModel', 0, 'INT')
        gff.add('Positional', 1, 'BYTE')
        gff.add('Continuous', 1, 'BYTE')
        gff.add('RandomPosition', 0, 'BYTE')
        gff.add('Volume', 127, 'INT')
        gff.add('VolumeVrtn', 0, 'INT')
        gff.add('PitchVariation', 0, 'INT')
        gff.add('MaxDistance', 6.0, 'FLOAT')
        gff.add('MinDistance', 0.5, 'FLOAT')
        gff.add('RandomRangeX', 0.0, 'FLOAT')
        gff.add('RandomRangeY', 0.0, 'FLOAT')
        gff.add('XPosition', 0.0, 'FLOAT')
        gff.add('YPosition', 0.0, 'FLOAT')
        gff.add('ZPosition', 0.0, 'FLOAT')
        gff.add('XOrientation', 0.0, 'FLOAT')
        gff.add('YOrientation', 0.0, 'FLOAT')
        return SoundInstance(gff)

    def visualChanged(self,v):
        self.toPreprocess = v

    def OnRightMouseDown(self,evt):
        if self.mode == ToolPalette.MAP2D_DRAW_TOOL and self.area:
            x, y = self.mouseToPointOnBasePlane(float(evt.GetX()), float(self.height - evt.GetY()))
            self._cycle2DAssetAt(x, y)
            self.requestRedraw()
            return
        if self.highlight != None:
            self.selectHighlighted(evt)
            self.popup = wx.Menu()
            thing = self.getThingHit(self.highlight)
            tag = thing['Tag']
            location = 'X:%.2f Y:%.2f Z:%.2f' % (thing.getX(),thing.getY(),thing.getZ())
            try:
                info = 'ID: %d' % thing.getObjectId()
            except:
                info = None
            if not hasattr(self,'COPY_TAG_ID'):
                self.COPY_TAG_ID = wx.NewId()
                self.Bind(wx.EVT_MENU, self.OnCopyTag, id=self.COPY_TAG_ID)        
                self.LOCATION_ID = wx.NewId()
                self.INFO_ID = wx.NewId()
            self.popup.Append(self.COPY_TAG_ID,'Copy Object Tag "%s" to Clipboard' % tag)
            self.popup.Append(self.LOCATION_ID,'Location: ' + location)
            if info:
                self.popup.Append(self.INFO_ID,info)
            self.popup.Enable(self.LOCATION_ID,False)
            self.PopupMenu(self.popup, evt.GetPosition())
            self.popup.Destroy()
            self.beingDragged = None
            self.popup = None

    def OnCopyTag(self,evt):
        if not wx.TheClipboard.Open():
            logger.error("Can't open system clipboard")
            return
        data = wx.TextDataObject(self.getThingHit(self.highlight)['Tag'])
        wx.TheClipboard.AddData(data)
        wx.TheClipboard.Close()        

    def selectHighlighted(self,evt):
        self.selected = [self.highlight]
        self.beingDragged = self.getThingHit(self.highlight)
        event = SingleSelectionEvent(self.GetId(),
                                     self.beingDragged.getNevereditId())
        # to remove if AddPending event clones the event
        self.GetEventHandler().AddPendingEvent(event.Clone())
        try:
            objectid = self.beingDragged.getObjectId()
            event = ObjectSelectionEvent(self.GetId(),objectid)
            # to remove if AddPending event clones the event
            self.GetEventHandler().AddPendingEvent(event.Clone())
        except:
            # that's fine, this is only for uses
            # other than neveredit itself                    
            pass 
        self.dragStart = (evt.GetX(),self.height-evt.GetY())
        self.setupCamera()
        x,y,z = self.project(self.beingDragged.getX(),
                             self.beingDragged.getY(),
                             0.0)
        self.dragOffset = (self.dragStart[0] - x,
                           self.dragStart[1] - y)
        
    def OnMouseDown(self, evt):
        if self.preprocessing:
            return
        self.SetFocus()
        self.makeCurrent()
        if self.mode == ToolPalette.MAP2D_DRAW_TOOL and self.area:
            if evt.LeftIsDown():
                x, y = self.mouseToPointOnBasePlane(float(evt.GetX()), float(self.height - evt.GetY()))
                self._apply2DDrawAt(x, y, evt)
                self.requestRedraw()
            return
        if self.mode == ToolPalette.SELECTION_TOOL or\
           self.mode == ToolPalette.ROTATE_TOOL:
            if self.highlight != None:
                thing = self.getThingHit(self.highlight)
                if self.mode == ToolPalette.SELECTION_TOOL and self._isNearSoundRadiusHandle(thing, evt):
                    self.soundRadiusEditing = thing
                    self.selected = [self.highlight]
                    self.requestRedraw()
                    return
                self.selectHighlighted(evt)
                self.requestRedraw()
            else:
                if self.selected:
                    self.selected = []
                    self.requestRedraw()
        elif (self.mode == ToolPalette.PAINT_TOOL or self.mode == ToolPalette.AMBIENT_SOUND_TOOL) and\
             self.beingPainted:
            self.area.addThing(self.beingPainted)
            self.refreshThingList()
            id = self.fullThingList.index(self.beingPainted)
            self.selected = [id]
            contents = self.getContentsForPoint(self.beingPainted.getX(),
                                                self.beingPainted.getY())
            contents['things'].append((self.beingPainted,id))
            event = ThingAddedEvent(self.GetId(),
                                    self.beingPainted.getNevereditId())
            self.beingPainted = self.beingPainted.clone()
            if self.beingPainted.getModel():
                self.preprocessNodes(self.beingPainted.getModel(),
                                     'beingPainted',
                                     bbox=True)
            self.GetEventHandler().AddPendingEvent(event)

    def OnMouseUp(self, evt):
        self.soundRadiusEditing = None
        self.beingDragged = None

    def OnMouseMotion(self, evt):
        if not self.area or not self.preprocessed or\
               self.preprocessing:
            return
        self.makeCurrent()
        currentX = evt.GetX()
        currentY = self.height - evt.GetY()

        if self.mode == ToolPalette.MAP2D_DRAW_TOOL and self.area:
            if evt.Dragging() and evt.LeftIsDown():
                x, y = self.mouseToPointOnBasePlane(float(evt.GetX()), float(self.height - evt.GetY()))
                self._apply2DDrawAt(x, y, evt)
                self.requestRedraw()
            self.lastX = currentX
            self.lastY = currentY
            return

        if self.soundRadiusEditing is not None and evt.Dragging() and evt.LeftIsDown():
            x, y = self.mouseToPointOnBasePlane(float(evt.GetX()), float(self.height - evt.GetY()))
            sx = float(self.soundRadiusEditing.getX())
            sy = float(self.soundRadiusEditing.getY())
            radius = math.sqrt((x - sx) * (x - sx) + (y - sy) * (y - sy))
            self.soundRadiusEditing.setRadius(radius)
            self.setStatus('Sound radius: %.2f' % max(0.25, radius))
            self.requestRedraw()
            self.lastX = currentX
            self.lastY = currentY
            return

        # Camera controls independent of object edit tools:
        # - Right drag: orbit camera angles.
        # - Middle drag (or Shift+Right drag): pan in world plane.
        if evt.Dragging() and not self.beingDragged:
            dx = float(currentX - self.lastX)
            dy = float(currentY - self.lastY)
            if evt.MiddleIsDown() or (evt.RightIsDown() and evt.ShiftDown()):
                self.adjustPos(dy * 0.08, -dx * 0.08)
                self.lastX = currentX
                self.lastY = currentY
                return
            if evt.RightIsDown():
                self.adjustViewAngle(-dx * 0.35, -dy * 0.25)
                self.lastX = currentX
                self.lastY = currentY
                return

        if self.mode == ToolPalette.SELECTION_TOOL or\
           self.mode == ToolPalette.ROTATE_TOOL and\
           not self.beingDragged:
            ray = self.rayToBasePlane(float(evt.GetX()),
                                      float(self.height-evt.GetY()))            
            x,y = self.rayPointOnBasePlane(ray)
            contents = self.getContentsForPoint(x,y)['things']
            closestIntersect = sys.maxsize
            toHighlight = -1
            for thing,id in contents:
                if thing.getModel():
                    sphere = [Numeric.array(thing.getModel().boundingSphere[0]),
                              thing.getModel().boundingSphere[1]]
                    sphere[0][0] += thing.getX()
                    sphere[0][1] += thing.getY()
                    sphere[0][2] += thing.getZ()
                    intersect = self.checkRaySphereIntersection(ray,sphere)
                    if intersect and intersect < closestIntersect:
                        toHighlight = id
                        closestIntersect = intersect
                elif hasattr(thing, 'getRadius'):
                    dx = thing.getX() - x
                    dy = thing.getY() - y
                    radial = math.sqrt(dx*dx + dy*dy)
                    radius = max(0.1, float(thing.getRadius()))
                    if radial <= radius and radial < closestIntersect:
                        toHighlight = id
                        closestIntersect = radial
            if toHighlight != -1:
                thing = self.fullThingList[toHighlight]
                before = self.highlight
                if before != toHighlight:
                    self.setHighlightBox(toHighlight)
                    self.requestRedraw()
            else:
                before = self.highlight
                self.highlight = None
                if before:
                    self.requestRedraw()
        if self.mode == ToolPalette.SELECTION_TOOL and\
           self.beingDragged:
            # TODO: remove this and make Z manipulation automatic.
            if self.holdZ == 1:
                dragX = float(evt.GetX() - self.dragOffset[0])
                dragY = float(self.height-evt.GetY() - self.dragOffset[1])
                oldX = self.beingDragged.getX()
                x = oldX
                oldY = self.beingDragged.getY()
                y = oldY
                oldZ = self.beingDragged.getZ()
                lastY = self.lastY - self.dragOffset[1]

                if dragY > lastY:
                    z = oldZ + 0.1
                elif dragY < lastY:
                    z = oldZ - 0.1
                else:
                    z = oldZ

                if z <= 0.0: #prevents the model from going below the map
                    z = 0.0
                if z > 25.0:  #according to the 'ARE' documentation, tile height is only 5 levels and it seems that they are multiples of 5 in the coordinate system.  5 * 5 is 25.  This is how far we go up.
                    z = 25.0
                self.updateZmax(z) # We update the maximum Z-component so that we can effectively do two plane points for the mouse.

            else:
                dragX = float(evt.GetX() - self.dragOffset[0])
                dragY = float(self.height-evt.GetY() - self.dragOffset[1])
                x,y = self.mouseToPointOnBasePlane(dragX,dragY)
                oldX = self.beingDragged.getX()
                oldY = self.beingDragged.getY()
                oldZ = self.beingDragged.getZ()
                z = oldZ

                if (int(oldX)/10 != int(x)/10) or (int(oldY)/10 != int(y)/10):
                    oldContents = self.getContentsForPoint(oldX,oldY)
                    newContents = self.getContentsForPoint(x,y)
                    try:
                        index = [t[0] for t in oldContents['things']]\
                                .index(self.beingDragged)
                        newContents['things'].append(oldContents['things'][index])
                        oldContents['things'].remove(oldContents['things'][index])
                    except ValueError:
                        newContents['things'].append((self.beingDragged,
                                                      self.fullThingList\
                                                      .index(self.beingDragged)))
                self.beingDragged.setX(x)
                self.beingDragged.setY(y)

            self.beingDragged.setZ(z)
            event = MoveEvent(self.GetId(),
                              self.beingDragged.getNevereditId(),
                              x,y,
                              self.beingDragged.getBearing())
            # Clone() to remove if AddPendingEvent clones the event
            self.GetEventHandler().AddPendingEvent(event.Clone())

            self.requestRedraw()

        elif self.mode == ToolPalette.ROTATE_TOOL and\
           self.beingDragged:
            self.beingDragged.setBearing((self.beingDragged.getBearing() +
                                          float(evt.GetX() - self.lastX)/60.0)
                                         % (2.0*math.pi))
            event = MoveEvent(self.GetId(),
                              self.beingDragged.getNevereditId(),
                              self.beingDragged.getX(),
                              self.beingDragged.getY(),
                              self.beingDragged.getBearing())
            # Clone() to remove if AddPendingEvent clones the event
            self.GetEventHandler().AddPendingEvent(event.Clone())
            self.requestRedraw()
        elif self.mode == ToolPalette.PAINT_TOOL and\
           self.beingPainted:
            dragX = float(evt.GetX() - self.dragOffset[0])
            dragY = float(self.height-evt.GetY() - self.dragOffset[1])
            x,y = self.mouseToPointOnBasePlane(dragX,dragY)
            self.beingPainted.setX(x)
            self.beingPainted.setY(y)
            self.requestRedraw()
            
        self.lastX = currentX
        self.lastY = currentY

    def _isNearSoundRadiusHandle(self, thing, evt):
        if thing is None or not hasattr(thing, 'getRadius'):
            return False
        try:
            x, y = self.mouseToPointOnBasePlane(float(evt.GetX()),
                                                float(self.height - evt.GetY()))
            sx = float(thing.getX())
            sy = float(thing.getY())
            radius = max(0.25, float(thing.getRadius()))
        except Exception:
            return False
        distance = math.sqrt((x - sx) * (x - sx) + (y - sy) * (y - sy))
        tolerance = max(0.5, radius * 0.08)
        return abs(distance - radius) <= tolerance

    def OnKeyUp(self,evt):
        self.holdZ = 0

    def OnMouseWheel(self,evt):
        if self.mode == ToolPalette.MAP2D_DRAW_TOOL:
            delta = evt.GetWheelRotation()
            if delta > 0:
                self.map2DBrushRadius = min(8, self.map2DBrushRadius + 1)
            else:
                self.map2DBrushRadius = max(1, self.map2DBrushRadius - 1)
            self.setStatus('2D brush radius: %d' % self.map2DBrushRadius)
            self.requestRedraw()
            return
        if self.mode == ToolPalette.AMBIENT_SOUND_TOOL and self.beingPainted and hasattr(self.beingPainted, 'getRadius'):
            delta = evt.GetWheelRotation()
            step = 0.5 if delta > 0 else -0.5
            self.beingPainted.setRadius(self.beingPainted.getRadius() + step)
            self.requestRedraw()
            return
        GLWindow.OnMouseWheel(self, evt)

    def OnKeyDown(self,evt):
        global Numeric
        GLWindow.OnKeyDown(self,evt)        
        unicode_key = evt.GetUnicodeKey()
        if unicode_key is not None and unicode_key >= 0:
            key_char = chr(unicode_key).lower()
        else:
            key_char = ''

        if self.mode == ToolPalette.MAP2D_DRAW_TOOL:
            if key_char == 't':
                self.map2DTerrainBrush = (self.map2DTerrainBrush + 1) % 6
                self.setStatus('2D terrain brush: %s' % self._get2DTerrainName(self.map2DTerrainBrush))
                self.requestRedraw()
                return
            if key_char == 'u':
                self.map2DAssetBrush = (self.map2DAssetBrush + 1) % 5
                self.setStatus('2D asset brush: %s' % self._get2DAssetName(self.map2DAssetBrush))
                self.requestRedraw()
                return
            if key_char == 'g':
                self.map2DShowGrid = not self.map2DShowGrid
                self.setStatus('2D grid: %s' % ('on' if self.map2DShowGrid else 'off'))
                self.requestRedraw()
                return
            if key_char == 'o':
                self.map2DShowOcclusion = not self.map2DShowOcclusion
                self.setStatus('2D occlusion borders: %s' % ('on' if self.map2DShowOcclusion else 'off'))
                self.requestRedraw()
                return
            if key_char == 'c':
                self.map2DCells = {}
                self._save2DDraftForCurrentArea()
                self.setStatus('2D overlay cleared')
                self.requestRedraw()
                return
            if key_char == 'x':
                if self._export2DDraftForCurrentArea():
                    self.requestRedraw()
                return
            if key_char == 'i':
                if self._import2DDraftForCurrentArea():
                    self.requestRedraw()
                return
            if key_char in ['+', '=']:
                self.map2DBrushRadius = min(8, self.map2DBrushRadius + 1)
                self.setStatus('2D brush radius: %d' % self.map2DBrushRadius)
                self.requestRedraw()
                return
            if key_char in ['-', '_']:
                self.map2DBrushRadius = max(1, self.map2DBrushRadius - 1)
                self.setStatus('2D brush radius: %d' % self.map2DBrushRadius)
                self.requestRedraw()
                return

        if key_char == 'a':
            mode = self.cycleAnimationMode()
            self.setStatus('Animation mode: %s' % mode)
            return

        if key_char == 'l':
            self.previewNightLighting = not self._isNightInAreaData()
            if self.previewNightLighting:
                self.setStatus('Lighting preview: night')
            else:
                self.setStatus('Lighting preview: day')
            self.requestRedraw()
            return

        if key_char == 'k':
            self.ambientPreviewEnabled = not self.ambientPreviewEnabled
            if self.ambientPreviewEnabled:
                self.setStatus('Ambient preview: on')
            else:
                self.setStatus('Ambient preview: off')
                self._stopAmbientPreview()
            self.requestRedraw()
            return

        if key_char == 'e':
            target = None
            if self.selected:
                target = self.getThingHit(self.selected[0])
            elif self.highlight is not None:
                target = self.getThingHit(self.highlight)
            if target is not None and hasattr(target, 'hasProperty') and target.hasProperty('SoundSet'):
                if self._cycleSoundSetEvent(target):
                    self._stopAmbientPreview()
                    self.requestRedraw()
            return

        if key_char == 'm':
            target = None
            if self.selected:
                target = self.getThingHit(self.selected[0])
            elif self.highlight is not None:
                target = self.getThingHit(self.highlight)
            if target is not None and hasattr(target, 'hasProperty') and target.hasProperty('AttenuationModel'):
                model = self._cycleAttenuationModel(target)
                self.setStatus('Attenuation model: %s' % self._attenuationModelName(model))
                self.requestRedraw()
            return

        if key_char == 'z':
            self.ambientUse3DDistance = not self.ambientUse3DDistance
            self.setStatus('Ambient distance mode: %s' % ('3D' if self.ambientUse3DDistance else '2D'))
            self.requestRedraw()
            return

        if evt.GetKeyCode() == 308: #ctrl
            self.holdZ = 1
        # if evt.GetKeyCode() == wx.WXK_SPACE:
#             self.SetCurrent()
#             print 'profiling to draw.prof'
#             import profilewrap
#             #tmpNum = Numeric
#             #Numeric = profilewrap.wrap(Numeric)
#             tmpGL = {}
#             for func in globals():
#                 if func[:2] == 'gl' and hasattr(globals()[func],'__call__'):
#                     tmpGL[func] = globals()[func]
#                     globals()[func] = profilewrap.wrap(globals()[func])
#             p = profile.Profile()
#             p.runcall(self.DrawGLScene)
#             #Numeric = tmpNum
#             for func in tmpGL:
#                 globals()[func] = tmpGL[func]
#             p.dump_stats('draw.prof')

    def getThingHit(self,name):
        try:
            return self.fullThingList[name]
        except:
            return None

    def selectThingById(self,id):
        didSelect = False
        for i,thing in enumerate(self.fullThingList):
            if thing.getNevereditId() == id:
                if i not in self.selected:
                    self.highlight = None
                    self.selected = [i]
                    self.centreThing(thing)
                    self.requestRedraw()
                didSelect = True
        if not didSelect:
            if id not in self._missingSelectionWarnings:
                self._missingSelectionWarnings.add(id)
                logger.debug(__name__+' cannot find thing with id %i' % id)

    def _warnMissingModelOnce(self, category, name):
        key = (category, name)
        if key in self._missingModelWarnings:
            return
        self._missingModelWarnings.add(key)
        logger.warning('no model for %s (%s)' % (name, category))

    def lookAt(self,x,y):
        self.lookingAtX = x
        self.lookingAtY = y
    
    def lookWith(self,id):
        thing = self.fullThingMap[id]
        self.viewAngleFloor = thing.getBearing()+90
        self.centreThing(thing)
        self.recomputeCamera()
        
    def centreThingById(self,id):
        thing = self.fullThingMap[id]
        self.centreThing(thing)
            
    def centreThing(self,thing):
        self.lock.acquire()
        self.lookingAtX = thing.getX()
        self.lookingAtY = thing.getY()
        self.lock.release()
        self.requestRedraw()

    def checkRaySphereIntersection(self,ray,sphere):
        direction = Numeric.array(ray[1]) - Numeric.array(ray[2])
        diff = Numeric.array(ray[1]) - Numeric.array(sphere[0])
        a = Numeric.dot(direction,direction)
        b = 2.0*Numeric.dot(direction,diff)
        c = Numeric.dot(diff,diff) - sphere[1] ** 2
        r = b**2 - 4*a*c
        if r < 0:
            return False
        else:
            sr_over_2a = math.sqrt(r)/(2.0*a)
            t = -b - sr_over_2a
            if t > 0:
                return t
            else:
                return -b + sr_over_2a

    def rayFromMouse(self,x,y):
        glPushMatrix()
        try:
            self.setupCamera()
            near = Numeric.array(self.unproject(x,y,0.0))
            far = Numeric.array(self.unproject(x,y,1.0))
        finally:
            # Always balance matrix stack even if unproject/setup fails.
            glPopMatrix()
        return near,far
    
    def rayToPlane(self,x,y,plane):
        near,far = self.rayFromMouse(x,y)
        N = Numeric.array([0.0,0.0,1.0]) # normal
        P = Numeric.array(plane) # plane must be of values e.g. [1.0,1.0,0.0]
        u = Numeric.dot(N,P-near)/Numeric.dot(N,far-near)
        return u,near,far
    
    def rayToBasePlane(self,x,y):        
        near,far = self.rayFromMouse(x,y)
        N = Numeric.array([0.0,0.0,1.0]) #this is normal to the area plane
        P = Numeric.array([1.0,1.0,0.0]) #this is on the area plane
        u = Numeric.dot(N,P-near)/Numeric.dot(N,far-near)
        return u,near,far

    def mouseToPointonMaxZPlane(self,x,y):
        Zmax = self.Zmax
        P = Numeric.array([1.0,1.0,Zmax])
        ray = self.rayToPlane(x,y,P)
        return self.rayPointOnPlane(ray,P)

    def rayPointOnPlane(self,ray,plane):        
        #FIXME: STUB
    
        #u,near,far = ray
        #intersect = near + u * (far-near)
        #px = intersect[0]
        #py = intersect[1]
        #if px < 0:
        #    px = 0
        #if px > self.area.getWidth()*10.0:
        #    px = self.area.getWidth()*10.0
        #if py < 0:
        #    py = 0
        #if py > self.area.getHeight()*10.0:
        #    py = self.area.getHeight()*10.0                
        #return px,py
        return

    def mouseToPointOnBasePlane(self,x,y):
        ray = self.rayToBasePlane(x,y)
        return self.rayPointOnBasePlane(ray)

    def rayPointOnBasePlane(self,ray):        
        u,near,far = ray
        intersect = near + u * (far-near)
        px = intersect[0]
        py = intersect[1]
        if px < 0:
            px = 0
        if px > self.area.getWidth()*10.0:
            px = self.area.getWidth()*10.0
        if py < 0:
            py = 0
        if py > self.area.getHeight()*10.0:
            py = self.area.getHeight()*10.0                
        return px,py

    def getContentsForPointSimplifiedHelper(self,x,y,node):
        #track the max Z.  We will have a range of values interval (Zmax and Baseplane)
        #if the value of the creature falls inbetween the point from Zmax and Baseplane)
        #we pass to the sphere intersection test.

        #we will return it if it aligns with xmin,xmax or ymin,ymax
        if not node.children:
            return node.contents
        else:
            for row in node.children:
                for c in row:
                    if (x >= c.xmin and x <= c.xmax) and \
                       (y >= c.ymin and y <= c.ymax):
                        return self.getContentsForPointSimplifiedHelper(x,y,c)
            return node.contents

    def updateZmax(self,newZ):
        # We will iterate through the quadtree looking for the object with the maximum Z component.
        return self.updateZmaxHelper(newZ,self.quadTreeRoot)
        
    def updateZmaxHelper(self,newZ,node):
        if not node.children:
            if newZ > 0:
                self.Zmax = newZ
            return self.Zmax
        value = newZ
        for row in node.children:
            for c in row:
                if not c.children:
                    # Iterate through contents and get the biggest Z value.
                    contents_thing = c.contents['things']
                    for thing,id in contents_thing:
                        if thing.getModel():
                            testZ = thing.getZ()
                            if testZ > value:
                                value = testZ
        self.Zmax = value
        return self.Zmax

    
    def getContentsForPoint(self,x,y):
        return self.getContentsForPointSimplifiedHelper(x,y,self.quadTreeRoot)

    def getContentsForPointHelper(self,x,y,node):
        if not node.children:
            return node.contents
        else:
            for row in node.children:
                for c in row:
                    if x >= c.xmin and x <= c.xmax and\
                       y >= c.ymin and y <= c.ymax:
                        return self.getContentsForPointHelper(x,y,c)
            return node.contents
        
    def clearCache(self):
        GLWindow.clearCache(self)
        self.preprocessedModels = Set()
        self.creatureModelVariants = {}
        self._missingModelWarnings = set()

    def _getCreatureTintContext(self, creature):
        if not hasattr(creature, 'getPLTTintContext'):
            return {}
        try:
            tint_context = creature.getPLTTintContext()
        except Exception:
            return {}
        if not isinstance(tint_context, dict):
            return {}
        return dict(tint_context)

    def _normalizeTintSignature(self, tint_context):
        if not tint_context:
            return ()
        normalized = []
        for key, value in list(tint_context.items()):
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                continue
            if ivalue < 0:
                continue
            normalized.append((str(key), ivalue))
        normalized.sort()
        return tuple(normalized)

    def _getCreatureBodyPartContext(self, creature):
        if not hasattr(creature, 'getBodyPartContext'):
            return {}
        try:
            part_context = creature.getBodyPartContext()
        except Exception:
            return {}
        if not isinstance(part_context, dict):
            return {}
        return dict(part_context)

    def _normalizePartSignature(self, part_context):
        if not part_context:
            return ()
        normalized = []
        for key, value in list(part_context.items()):
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                continue
            if ivalue < 0:
                continue
            normalized.append((str(key), ivalue))
        normalized.sort()
        return tuple(normalized)

    def setStatus(self,status):
        Progressor.setStatus(self,status)
        print(status)
    
    def preprocess(self):
        if not self.area:
            return
        preprocess_start = time.perf_counter()
        phase_start = preprocess_start
        self.makeCurrent()
        self.clearCache()
        self.makeQuadTree()
        logger.info('preprocess phase makeQuadTree: %.3fs', time.perf_counter() - phase_start)

        phase_start = time.perf_counter()
        self.setStatus("Preparing door display...")
        self.setProgress(10)
        for i,d in enumerate(self.doors):
            model = d.getModel()
            if model:
                if d.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model,'d'+repr(i),bbox=True)
                    self.preprocessedModels.add(d.modelName)
            else:
                self._warnMissingModelOnce('door', d.getName())
        logger.info('preprocess phase doors: %.3fs', time.perf_counter() - phase_start)

        phase_start = time.perf_counter()
        self.setProgress(30)
        self.setStatus("Preparing placeable display...")
        for i,p in enumerate(self.placeables):
            model = p.getModel()
            if model:
                if p.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model,'p'+repr(i),bbox=True)
                    self.preprocessedModels.add(p.modelName)
            else:
                self._warnMissingModelOnce('placeable', p.getName())
        logger.info('preprocess phase placeables: %.3fs', time.perf_counter() - phase_start)

        phase_start = time.perf_counter()
        self.setProgress(50)
        self.setStatus("Preparing creature display...")
        for i,c in enumerate(self.creatures):
            base_model = c.getModel()
            if not base_model:
                continue

            tint_context = self._getCreatureTintContext(c)
            tint_signature = self._normalizeTintSignature(tint_context)
            part_context = self._getCreatureBodyPartContext(c)
            part_signature = self._normalizePartSignature(part_context)
            variant_key = ('creature', c.modelName, tint_signature, part_signature)

            model = self.creatureModelVariants.get(variant_key)
            if model is None:
                if tint_signature:
                    model = c.getModel(copy=True)
                else:
                    model = base_model
                if not model:
                    continue

                if tint_signature:
                    model.pltTintContext = dict(tint_signature)
                elif hasattr(model, 'pltTintContext'):
                    delattr(model, 'pltTintContext')
                if part_signature:
                    model.creaturePartContext = dict(part_signature)
                elif hasattr(model, 'creaturePartContext'):
                    delattr(model, 'creaturePartContext')
                self.creatureModelVariants[variant_key] = model

            c.model = model
            if model:
                if variant_key not in self.preprocessedModels:
                    self.preprocessNodes(model,'c'+repr(i),bbox=True)
                    self.preprocessedModels.add(variant_key)
            else:
                pass # I know I'm not handling all model types here yet
        logger.info('preprocess phase creatures: %.3fs', time.perf_counter() - phase_start)

        phase_start = time.perf_counter()
        self.setProgress(70)
        self.setStatus("Preparing tile display...")
        for i,t in enumerate(self.tiles):
            model = t.getModel()
            if model:
                if t.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model,'t'+repr(i),bbox=True)
                    self.preprocessedModels.add(t.modelName)
            else:
                self._warnMissingModelOnce('tile', t.getName())
        logger.info('preprocess phase tiles: %.3fs', time.perf_counter() - phase_start)

        phase_start = time.perf_counter()
        self.setProgress(90)
        self.setStatus("Preparing waypoint display...")
        for i,w in enumerate(self.waypoints):
            model = w.getModel()
            if model:
                if w.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model,'w'+repr(i),bbox=True)
                    self.preprocessedModels.add(w.modelName)
            else:
                self._warnMissingModelOnce('waypoint', w.getName())
        logger.info('preprocess phase waypoints: %.3fs', time.perf_counter() - phase_start)
        self.setProgress(0)
        self.setStatus("Map display prepared.")
        logger.info('preprocess total: %.3fs', time.perf_counter() - preprocess_start)
        self.preprocessed = True
        
    def makeQuadTree(self):
        """
        This makes the map quad tree, which splits the map recursively
        into 4 equal pieces down to the level of tiles, and computes
        the bounding sphere of each piece. These can later be checked
        against the viewing frustrum in a top-down manner to quickly
        determine which parts of the map are visible and need to be
        drawn. Alongside, this also determines which objects are on
        which tile, so that only objects on visible tiles are drawn.
        """
        self.quadTreeRoot = QuadTreeNode()
        self.quadTreeRoot.boundingSphere[0][0] = float(5.0*self.area.getWidth())
        self.quadTreeRoot.boundingSphere[0][1] = float(5.0*self.area.getHeight())
        self.quadTreeRoot.boundingSphere[1] = math.sqrt(2) *\
                                              self.quadTreeRoot.boundingSphere[0][0]
                                         
        for i in range(self.area.getHeight()):
            for j in range(self.area.getWidth()):
                self.thingMap[i][j] = {'tiles':[],'things':[]}
        for i,thing in enumerate(self.fullThingList):
            x = int(math.floor(thing.getX() / 10.0))
            y = int(math.floor(thing.getY() / 10.0))
            if x == self.area.getWidth(): # doors can be at the edges
                x -= 1
            if y == self.area.getHeight():
                y -= 1
            self.thingMap[y][x]['things'].append((thing,i))
        for i,tile in enumerate(self.tiles):
            x = i % self.area.getWidth()
            y = i // self.area.getWidth()
            self.thingMap[y][x]['tiles'].append((tile,i))

        self.makeQuadTreeHelper(self.quadTreeRoot,0,0,
                                self.area.getWidth(),
                                self.area.getHeight())
        #self.quadTreeRoot.printNode()
        
    def makeQuadTreeHelper(self,node,xmin,ymin,xmax,ymax):
        w = xmax - xmin
        h = ymax - ymin
        if w > 1:
            if h > 1:
                node.children = [[QuadTreeNode(),QuadTreeNode()],
                                 [QuadTreeNode(),QuadTreeNode()]]
            else:
                node.children = [[QuadTreeNode(),QuadTreeNode()]]        
        else:
            if h > 1:
                node.children = [[QuadTreeNode()],[QuadTreeNode()]]
            else:
                node.children = []
                node.contents = self.thingMap[ymin][xmin]
                return

        fxmin = 10.0*float(xmin)
        fymin = 10.0*float(ymin)
        fxmax = 10.0*float(xmax)
        fymax = 10.0*float(ymax)
        
        if w > 1:
            c1w = w // 2
            c2w = w-c1w
            for l in node.children:
                l[0].boundingSphere[0][0] = fxmin + 5.0 * float(c1w)
                l[1].boundingSphere[0][0] = fxmax - float(c2w)*5.0
        else:
            cw = 5.0*float(w)
            for l in node.children:
                l[0].boundingSphere[0][0] = fxmin + cw
        if h > 1:
            c1h = h // 2
            c2h = h-c1h
            for l in node.children[0]:
                l.boundingSphere[0][1] = fymin + 5.0 * float(c1h)
            for l in node.children[1]:
                l.boundingSphere[0][1] = fymax - float(c2h)*5.0
        else:
            ch = 5.0*float(h)
            for l in node.children[0]:
                l.boundingSphere[0][1] = fymin + ch

        if w > 1:
            c1w = w // 2
            c2w = w-c1w
            wsplit = xmin + c1w
            if h > 1:
                c1h = h // 2
                c2h = h-c1h
                hsplit = ymin + c1h
                r = math.sqrt((5.0*float(c1w)) ** 2 + (5.0*float(c1h)) ** 2)
                node.children[0][0].boundingSphere[1] = r
                node.children[0][0].xmin = xmin*10
                node.children[0][0].xmax = wsplit*10
                node.children[0][0].ymin = ymin*10
                node.children[0][0].ymax = hsplit*10
                self.makeQuadTreeHelper(node.children[0][0],xmin,ymin,
                                        wsplit,hsplit)
                r = math.sqrt((5.0*float(c2w)) ** 2 + (5.0*float(c1h)) ** 2)
                node.children[0][1].boundingSphere[1] = r
                node.children[0][1].xmin = wsplit*10
                node.children[0][1].xmax = xmax*10
                node.children[0][1].ymin = ymin*10
                node.children[0][1].ymax = hsplit*10
                self.makeQuadTreeHelper(node.children[0][1],wsplit,ymin,
                                        xmax,hsplit)
                r = math.sqrt((5.0*float(c1w)) ** 2 + (5.0*float(c2h)) ** 2)
                node.children[1][0].boundingSphere[1] = r
                node.children[1][0].xmin = xmin*10
                node.children[1][0].xmax = wsplit*10
                node.children[1][0].ymin = hsplit*10
                node.children[1][0].ymax = ymax*10                
                self.makeQuadTreeHelper(node.children[1][0],xmin,hsplit,
                                        wsplit,ymax)
                r = math.sqrt((5.0*float(c2w)) ** 2 + (5.0*float(c2h)) ** 2)
                node.children[1][1].boundingSphere[1] = r
                node.children[1][1].xmin = wsplit*10
                node.children[1][1].xmax = xmax*10
                node.children[1][1].ymin = hsplit*10
                node.children[1][1].ymax = ymax*10                
                self.makeQuadTreeHelper(node.children[1][1],wsplit,hsplit,
                                        xmax,ymax)
            else:
                r = math.sqrt((5.0*float(c1w)) ** 2 + 25.0)
                node.children[0][0].boundingSphere[1] = r
                node.children[0][0].xmin = xmin*10
                node.children[0][0].xmax = wsplit*10
                node.children[0][0].ymin = ymin*10
                node.children[0][0].ymax = ymax*10                
                self.makeQuadTreeHelper(node.children[0][0],xmin,ymin,
                                        wsplit,ymax)
                r = math.sqrt((5.0*float(c2w)) ** 2 + 25.0)
                node.children[0][1].boundingSphere[1] = r
                node.children[0][1].xmin = wsplit*10
                node.children[0][1].xmax = xmax*10
                node.children[0][1].ymin = ymin*10
                node.children[0][1].ymax = ymax*10
                self.makeQuadTreeHelper(node.children[0][1],wsplit,ymin,
                                        xmax,ymax)
        else:
            if h > 1:
                c1h = h // 2
                c2h = h-c1h
                hsplit = ymin + c1h
                r = math.sqrt(25.0 + (5.0*float(c1h)) ** 2)
                node.children[0][0].boundingSphere[1] = r
                node.children[0][0].xmin = xmin*10
                node.children[0][0].xmax = xmax*10
                node.children[0][0].ymin = ymin*10
                node.children[0][0].ymax = hsplit*10                
                self.makeQuadTreeHelper(node.children[0][0],xmin,ymin,xmax,hsplit)
                r = math.sqrt(25.0 + (5.0*float(c2h)) ** 2)
                node.children[1][0].boundingSphere[1] = r
                node.children[1][0].xmin = xmin*10
                node.children[1][0].xmax = xmax*10
                node.children[1][0].ymin = hsplit*10
                node.children[1][0].ymax = ymax*10                
                self.makeQuadTreeHelper(node.children[1][0],xmin,hsplit,xmax,ymax)
            else:
                pass

    def getArea(self):
        return self.area
    
    def setArea(self,area):
        if self.area == area:
            return
        self._save2DDraftForCurrentArea()
        self.map2DCells = {}
        self.beingPainted = None
        self.area = None
        self.lock.acquire()
        self.selected = []
        self.highlight = None
        if not area:
            self.selected = []
            self.placeables = None
            self.doors = None
            self.creatures = None
            self.tiles = None
            self.waypoints = None
            self.sounds = None
        else:
            self.thingMap = [area.getWidth()*[None]
                             for i in range(area.getHeight())]
            self.setProgress(0)
            self.setStatus('Reading area contents...')
            area.readContents()
            self.setProgress(50)
            self.setStatus('Reading area tiles...')
            area.readTiles()
            self.lookingAtX = area.getWidth()*5.0
            self.lookingAtY = area.getHeight()*5.0        
            self.placeables = area.getPlaceables()
            self.doors = area.getDoors()
            self.creatures = area.getCreatures()
            self.tiles = area.getTiles()
            self.waypoints = area.getWayPoints()
            self.sounds = area.getSounds()
            self.preprocessed = False
            self.setProgress(0)
            self.refreshThingList()
            if self.fullThingList and self.fullThingList[0].getObjectId() != None:
                self.fullThingMap = dict([(thing.getObjectId(),thing) for thing in self.fullThingList])
            else:
                self.fullThingMap = {}
            
        self.area = area
        if area is None:
            self.previewNightLighting = None
            self._stopAmbientPreview()
        else:
            self.previewNightLighting = bool(self._isNightInAreaData())
            self._load2DDraftForArea(area)
        self.lock.release()
        self.requestRedraw()

    def refreshThingList(self):
        self.fullThingList = (self.doors or []) + (self.placeables or []) + (self.creatures or []) + (self.waypoints or []) + (self.sounds or [])
        
    def getBaseWidth(self):
        if self.area:
            return self.area.getWidth()*10.0
        else:
            return 1.0

    def getBaseHeight(self):
        if self.area:
            return self.area.getHeight()*10.0
        else:
            return 1.0

    def setPlayer(self,p):
        self.lock.acquire()
        self.players[p.playerID2] = copy.copy(p)
        self.fullThingMap[p.playerID2] = self.players[p.playerID2]
        self.lock.release()
        self.requestRedraw()
        #self.Refresh(False)

    def removePlayer(self,pid):
        self.lock.acquire()
        print('removing player',pid)
        del self.players[pid]
        self.lock.release()
        self.requestRedraw()
        #self.Refresh(False)

    def setHighlightBox(self,hid):
        self.highlight = hid
        self.highlightBox = TextBox()
        target = self.getThingHit(hid)
        if target:
            self.highlightBox.setText(target.getName())

    def setTextBox(self,oid,text,
                   fgcolour=(0.0,1.0,0.0,1.0),
                   bgcolour=(0.0,0.0,0.0,1.0)):
        if not text:
            if oid in self.textBoxes:
                del self.textBoxes[oid]
            return
        b = TextBox()
        self.textBoxes[oid] = b
        b.setText(text)
        b.bgcolour = bgcolour
        b.fgcolour = fgcolour
        self.requestRedraw()

    def drawTextBox(self,b):
        if not b.maxLine:
            return
        glPushMatrix()
        try:
            self.glColorf(b.bgcolour)
            glTranslatef(b.x+5,b.y+5,0)
            if 'glutBitmapWidth' in globals() and bool(glutBitmapWidth):
                w = sum([glutBitmapWidth(GLUT_BITMAP_TIMES_ROMAN_10,ord(c)) for c in b.maxLine])
            else:
                # Approximate width for systems without usable GLUT bitmap APIs.
                w = 7 * len(b.maxLine)
            # w = glutBitmapLength(GLUT_BITMAP_TIMES_ROMAN_10,b.maxLine)
            rectWidth = w + 7
            rectHeight = 12*b.textHeight + 8
            self.drawRoundedRect(rectWidth + 5,rectHeight)
            glDisable(GL_BLEND)
            for i,line in enumerate(b.text):
                height = b.y + (rectHeight - i*12) - 7
                glColor4f(0,0,0,1)
                self.output_text(b.x+15,height,line)
                self.glColorf(b.fgcolour)
                self.output_text(b.x+14,height+1,line)
            glEnable(GL_BLEND)
        finally:
            glPopMatrix()
        
    def drawOverlays(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        try:
            glLoadIdentity()
            gluOrtho2D(0,self.width,0,self.height)
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            try:
                glLoadIdentity()
                if self.showFPS:
                    glColor3f(1,1,1)
                    self.output_text(15,15,'fps: %.2f' % self.fps)
                for b in list(self.textBoxes.values()):
                    self.drawTextBox(b)
                if self.highlight != None:
                    b = self.highlightBox
                    self.drawTextBox(b)
                self._drawAmbientLegendOverlay()
                self._draw2DLegendOverlay()
            finally:
                glPopMatrix()
                glMatrixMode(GL_PROJECTION)
        finally:
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)

        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)

    def _drawAmbientLegendOverlay(self):
        highlighted = self.getThingHit(self.highlight) if self.highlight is not None else None
        selected = self.getThingHit(self.selected[0]) if self.selected else None
        target = selected if selected is not None else highlighted
        show = (self.mode == ToolPalette.AMBIENT_SOUND_TOOL or
                (highlighted is not None and hasattr(highlighted, 'getRadius')) or
                (selected is not None and hasattr(selected, 'getRadius')))
        if not show:
            return

        model_text = 'linear'
        if target is not None and hasattr(target, 'hasProperty') and target.hasProperty('AttenuationModel'):
            model_text = self._attenuationModelName(self._getAttenuationModel(target))

        lines = [
            'Ambient Tool: edge-drag resize | wheel adjust new radius',
            'K: preview %s  L: lighting %s  E: cycle SSF event'
            % ('on' if self.ambientPreviewEnabled else 'off',
               'night' if self.previewNightLighting else 'day'),
            'M: attenuation model (%s)  Z: distance %s'
            % (model_text, '3D' if self.ambientUse3DDistance else '2D')
        ]

        if self.ambientPreviewEnabled:
            lines.append('Active voices: %d' % len(self._ambientPreviewDebugVoices))
            for voice_line in self._ambientPreviewDebugVoices[:3]:
                lines.append('  ' + voice_line)

        y = self.height - 18
        glColor3f(1.0, 0.95, 0.7)
        for line in lines:
            self.output_text(14, y, line)
            y -= 14

    def _get2DTerrainName(self, idx):
        names = ['grass', 'stone', 'water', 'dirt', 'sand', 'cliff']
        if idx < 0 or idx >= len(names):
            return 'unknown'
        return names[idx]

    def _get2DAssetName(self, idx):
        names = ['none', 'tree', 'rock', 'building', 'decoration']
        if idx < 0 or idx >= len(names):
            return 'unknown'
        return names[idx]

    def _get2DCellKey(self, x, y):
        if not self.area:
            return (0, 0)
        max_x = max(0, int((self.area.getWidth() * 10.0) / self.map2DCellSize) - 1)
        max_y = max(0, int((self.area.getHeight() * 10.0) / self.map2DCellSize) - 1)
        cx = int(math.floor(float(x) / self.map2DCellSize))
        cy = int(math.floor(float(y) / self.map2DCellSize))
        if cx < 0:
            cx = 0
        if cy < 0:
            cy = 0
        if cx > max_x:
            cx = max_x
        if cy > max_y:
            cy = max_y
        return (cx, cy)

    def _iter2DBrushCells(self, cell_key):
        cx, cy = cell_key
        r = max(1, int(self.map2DBrushRadius))
        for ox in range(-r, r + 1):
            for oy in range(-r, r + 1):
                if ox * ox + oy * oy > r * r:
                    continue
                yield (cx + ox, cy + oy)

    def _ensure2DCell(self, cell_key):
        if cell_key not in self.map2DCells:
            self.map2DCells[cell_key] = {
                'terrain': 0,
                'height': 0.0,
                'asset': 0,
                'blocked': False,
            }
        return self.map2DCells[cell_key]

    def _apply2DDrawAt(self, x, y, evt):
        base = self._get2DCellKey(x, y)
        for key in self._iter2DBrushCells(base):
            cell = self._ensure2DCell(key)
            if evt.ControlDown():
                cell['height'] = min(5.0, cell['height'] + self.map2DHeightStep)
            elif evt.AltDown():
                cell['height'] = max(-5.0, cell['height'] - self.map2DHeightStep)
            elif evt.ShiftDown():
                cell['blocked'] = not cell.get('blocked', False)
            else:
                cell['terrain'] = self.map2DTerrainBrush
                cell['asset'] = self.map2DAssetBrush
        self._save2DDraftForCurrentArea()

    def _cycle2DAssetAt(self, x, y):
        key = self._get2DCellKey(x, y)
        cell = self._ensure2DCell(key)
        cell['asset'] = (int(cell.get('asset', 0)) + 1) % 5
        self.setStatus('2D asset @%d,%d: %s' % (key[0], key[1], self._get2DAssetName(cell['asset'])))
        self._save2DDraftForCurrentArea()

    def _get2DDraftPath(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        return os.path.join(repo_root, '.neveredit_2d_drafts.json')

    def _sanitize2DFileStem(self, value):
        text = str(value or 'area').strip()
        if not text:
            text = 'area'
        out = []
        for ch in text:
            if ch.isalnum() or ch in ['-', '_']:
                out.append(ch)
            else:
                out.append('_')
        stem = ''.join(out)
        while '__' in stem:
            stem = stem.replace('__', '_')
        return stem[:80]

    def _get2DExportDir(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        return os.path.join(repo_root, '.neveredit_2d_drafts')

    def _get2DAreaExternalDraftPath(self, area=None):
        area_key = self._get2DDraftAreaKey(area)
        stem = self._sanitize2DFileStem(area_key)
        return os.path.join(self._get2DExportDir(), stem + '.json')

    def _get2DDraftAreaKey(self, area=None):
        target = area or self.area
        if not target:
            return ''
        try:
            area_name = str(getattr(target, 'name', '') or '')
        except Exception:
            area_name = ''
        if not area_name:
            try:
                area_name = str(target.getName() or '')
            except Exception:
                area_name = 'unknown_area'
        return area_name

    def _load2DDraftStore(self):
        path = self._get2DDraftPath()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            logger.debug('failed to load 2D draft store', exc_info=True)
        return {}

    def _save2DDraftStore(self, store):
        path = self._get2DDraftPath()
        try:
            with open(path, 'w') as f:
                json.dump(store, f, indent=2, sort_keys=True)
            return True
        except Exception:
            logger.debug('failed to save 2D draft store', exc_info=True)
            return False

    def _serialize2DCells(self):
        payload = {
            'cell_size': float(self.map2DCellSize),
            'cells': []
        }
        for key, cell in list(self.map2DCells.items()):
            try:
                cx = int(key[0])
                cy = int(key[1])
                payload['cells'].append({
                    'x': cx,
                    'y': cy,
                    'terrain': int(cell.get('terrain', 0)),
                    'height': float(cell.get('height', 0.0)),
                    'asset': int(cell.get('asset', 0)),
                    'blocked': bool(cell.get('blocked', False)),
                })
            except Exception:
                continue
        return payload

    def _deserialize2DCells(self, payload):
        cells = {}
        if not isinstance(payload, dict):
            return cells
        entries = payload.get('cells', [])
        if not isinstance(entries, list):
            return cells
        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                cx = int(item.get('x', 0))
                cy = int(item.get('y', 0))
            except Exception:
                continue
            cells[(cx, cy)] = {
                'terrain': int(item.get('terrain', 0) or 0),
                'height': float(item.get('height', 0.0) or 0.0),
                'asset': int(item.get('asset', 0) or 0),
                'blocked': bool(item.get('blocked', False)),
            }
        if 'cell_size' in payload:
            try:
                self.map2DCellSize = max(1.0, min(4.0, float(payload['cell_size'])))
            except Exception:
                pass
        return cells

    def _load2DDraftForArea(self, area):
        key = self._get2DDraftAreaKey(area)
        if not key:
            self.map2DCells = {}
            return
        store = self._load2DDraftStore()
        payload = store.get(key)
        if payload is None:
            self.map2DCells = {}
            return
        self.map2DCells = self._deserialize2DCells(payload)

    def _save2DDraftForCurrentArea(self):
        key = self._get2DDraftAreaKey(self.area)
        if not key:
            return
        store = self._load2DDraftStore()
        if not self.map2DCells:
            if key in store:
                del store[key]
                self._save2DDraftStore(store)
            return
        store[key] = self._serialize2DCells()
        self._save2DDraftStore(store)

    def _export2DDraftForCurrentArea(self):
        if not self.area:
            self.setStatus('2D export skipped: no area loaded')
            return False
        if not self.map2DCells:
            self.setStatus('2D export skipped: overlay is empty')
            return False
        export_dir = self._get2DExportDir()
        try:
            os.makedirs(export_dir)
        except OSError:
            pass
        path = self._get2DAreaExternalDraftPath(self.area)
        payload = self._serialize2DCells()
        payload['area_key'] = self._get2DDraftAreaKey(self.area)
        payload['version'] = 1
        try:
            with open(path, 'w') as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            self.setStatus('2D draft exported: %s' % os.path.basename(path))
            return True
        except Exception:
            logger.debug('failed to export 2D draft', exc_info=True)
            self.setStatus('2D export failed')
            return False

    def _import2DDraftForCurrentArea(self):
        if not self.area:
            self.setStatus('2D import skipped: no area loaded')
            return False
        path = self._get2DAreaExternalDraftPath(self.area)
        if not os.path.exists(path):
            self.setStatus('2D import file not found: %s' % os.path.basename(path))
            return False
        try:
            with open(path, 'r') as f:
                payload = json.load(f)
            self.map2DCells = self._deserialize2DCells(payload)
            self._save2DDraftForCurrentArea()
            self.setStatus('2D draft imported: %s' % os.path.basename(path))
            return True
        except Exception:
            logger.debug('failed to import 2D draft', exc_info=True)
            self.setStatus('2D import failed')
            return False

    def _draw2DGridAndPaintOverlay(self):
        if not self.area:
            return
        if not self.map2DCells and not self.map2DShowGrid and self.mode != ToolPalette.MAP2D_DRAW_TOOL:
            return

        terrain_colours = {
            0: (0.22, 0.62, 0.25, 0.28),
            1: (0.45, 0.45, 0.47, 0.28),
            2: (0.12, 0.35, 0.75, 0.30),
            3: (0.48, 0.32, 0.2, 0.28),
            4: (0.72, 0.64, 0.34, 0.28),
            5: (0.36, 0.28, 0.22, 0.30),
        }

        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        s = float(self.map2DCellSize)

        for (cx, cy), cell in list(self.map2DCells.items()):
            x0 = cx * s
            y0 = cy * s
            x1 = x0 + s
            y1 = y0 + s

            colour = terrain_colours.get(int(cell.get('terrain', 0)), terrain_colours[0])
            h = float(cell.get('height', 0.0))
            tint = max(-0.25, min(0.25, h * 0.04))
            self.glColorf((max(0.0, min(1.0, colour[0] + tint)),
                           max(0.0, min(1.0, colour[1] + tint)),
                           max(0.0, min(1.0, colour[2] + tint)),
                           colour[3]))
            glBegin(GL_QUADS)
            glVertex3f(x0, y0, 0.06)
            glVertex3f(x1, y0, 0.06)
            glVertex3f(x1, y1, 0.06)
            glVertex3f(x0, y1, 0.06)
            glEnd()

            if int(cell.get('asset', 0)) > 0:
                cxm = x0 + 0.5 * s
                cym = y0 + 0.5 * s
                self.glColorf((1.0, 0.95, 0.2, 0.8))
                glBegin(GL_LINES)
                glVertex3f(cxm - 0.28 * s, cym, 0.08)
                glVertex3f(cxm + 0.28 * s, cym, 0.08)
                glVertex3f(cxm, cym - 0.28 * s, 0.08)
                glVertex3f(cxm, cym + 0.28 * s, 0.08)
                glEnd()

            if self.map2DShowOcclusion and bool(cell.get('blocked', False)):
                self.glColorf((1.0, 0.15, 0.15, 0.95))
                glBegin(GL_LINE_LOOP)
                glVertex3f(x0, y0, 0.09)
                glVertex3f(x1, y0, 0.09)
                glVertex3f(x1, y1, 0.09)
                glVertex3f(x0, y1, 0.09)
                glEnd()

        if self.map2DShowGrid or self.mode == ToolPalette.MAP2D_DRAW_TOOL:
            self.glColorf((0.82, 0.82, 0.82, 0.24))
            max_x = self.area.getWidth() * 10.0
            max_y = self.area.getHeight() * 10.0
            glBegin(GL_LINES)
            gx = 0.0
            while gx <= max_x + 0.001:
                glVertex3f(gx, 0.0, 0.05)
                glVertex3f(gx, max_y, 0.05)
                gx += s
            gy = 0.0
            while gy <= max_y + 0.001:
                glVertex3f(0.0, gy, 0.05)
                glVertex3f(max_x, gy, 0.05)
                gy += s
            glEnd()

        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)

    def _draw2DLegendOverlay(self):
        show = (self.mode == ToolPalette.MAP2D_DRAW_TOOL)
        if not show:
            return
        lines = [
            '2D Draw: LMB paint | Ctrl+LMB raise | Alt+LMB lower | Shift+LMB toggle block',
            'RMB cycle asset at cell | Wheel +/- brush radius | C clear | X export | I import',
            'T terrain=%s  U asset=%s  G grid=%s  O occlusion=%s  Radius=%d'
            % (self._get2DTerrainName(self.map2DTerrainBrush),
               self._get2DAssetName(self.map2DAssetBrush),
               'on' if self.map2DShowGrid else 'off',
               'on' if self.map2DShowOcclusion else 'off',
               self.map2DBrushRadius)
        ]
        y = self.height - 76
        glColor3f(0.82, 0.98, 0.85)
        for line in lines:
            self.output_text(14, y, line)
            y -= 14

    def drawThing(self,thing,name):
        model = thing.getModel()
        if not model:
            if hasattr(thing, 'getRadius'):
                self._drawSoundThing(thing, name)
            return
        root = model.getRootNode()
        if root is None:
            return
        glPushMatrix()
        try:
            glTranslatef(thing.getX(),thing.getY(),thing.getZ())
            if self.highlight == name:
                (self.highlightBox.x,
                 self.highlightBox.y,
                 self.highlightBox.z) = self.project(0,0,0)
            if thing.getObjectId() in self.textBoxes:
                box = self.textBoxes[thing.getObjectId()]
                (box.x,box.y,box.z) = self.project(0,0,0)
            glRotatef(thing.getBearing() * 180/math.pi,0,0,1)
            #glPushName(name)
            self.handleNode(root,
                            selected=(name in self.selected))
            if self.highlight == name:
                box = self._getHighlightBoundingBox(model, root)
                if box is not None:
                    self.renderHighlightBoxOutline(box,
                                                   colour=(0.1,0.1,1.0),
                                                   thickness=2.0)
        finally:
            #glPopName()
            glPopMatrix()

    def _drawSoundCircle(self, radius, filled=False, segments=32):
        if radius <= 0.0:
            return
        primitive = GL_POLYGON if filled else GL_LINE_LOOP
        glBegin(primitive)
        for i in range(segments):
            theta = (2.0 * math.pi * float(i)) / float(segments)
            glVertex3f(math.cos(theta) * radius,
                       math.sin(theta) * radius,
                       0.0)
        glEnd()

    def _drawSoundThing(self, thing, name):
        radius = max(0.25, float(thing.getRadius()))
        inner_radius = self._getSoundInnerRadius(thing, radius)
        listener_gain = self._estimateSoundGainAtListener(thing, radius, inner_radius)
        listener_in_range = listener_gain > 0.0
        glPushMatrix()
        try:
            glTranslatef(thing.getX(), thing.getY(), thing.getZ())
            if self.highlight == name:
                (self.highlightBox.x,
                 self.highlightBox.y,
                 self.highlightBox.z) = self.project(0,0,0)
            if thing.getObjectId() in self.textBoxes:
                box = self.textBoxes[thing.getObjectId()]
                (box.x,box.y,box.z) = self.project(0,0,0)

            self.solidColourOn()
            try:
                if name in self.selected:
                    self.glColorf((0.15, 0.9, 0.15, 0.8))
                    self._drawSoundCircle(radius * 1.02, filled=False, segments=48)
                if self.highlight == name:
                    self.glColorf((0.1, 0.1, 1.0, 0.8))
                    self._drawSoundCircle(radius, filled=False, segments=48)
                else:
                    self.glColorf((0.1, 0.75, 0.9, 0.7))
                    self._drawSoundCircle(radius, filled=False, segments=32)

                if inner_radius > 0.0 and inner_radius < radius:
                    self.glColorf((0.95, 0.45, 0.1, 0.8))
                    self._drawSoundCircle(inner_radius, filled=False, segments=40)

                if name in self.selected or self.highlight == name:
                    self.glColorf((1.0, 0.85, 0.15, 1.0))
                    self._drawSoundCircle(0.25, filled=False, segments=20)
                    glPushMatrix()
                    glTranslatef(radius, 0.0, 0.0)
                    self._drawSoundCircle(0.25, filled=False, segments=20)
                    glPopMatrix()
            finally:
                self.solidColourOff()

            if self.soundRadiusEditing is thing or name in self.selected or self.highlight == name:
                px, py, _ = self.project(radius, 0.0, 0.0)
                self.output_text(px + 6, py + 6, 'R=%.2f' % radius)
                if inner_radius > 0.0 and inner_radius < radius:
                    ipx, ipy, _ = self.project(inner_radius, 0.0, 0.0)
                    self.output_text(ipx + 6, ipy + 6, 'I=%.2f' % inner_radius)
                lpx, lpy, _ = self.project(0.0, 0.0, 0.0)
                model_name = self._attenuationModelName(self._getAttenuationModel(thing))
                self.output_text(lpx + 6, lpy - 10, 'Gain=%.2f %s' % (listener_gain, '(in)' if listener_in_range else '(out)'))
                self.output_text(lpx + 6, lpy - 24, 'Attn=%s' % model_name)
                if thing.hasProperty('SoundSet') and self._normalizeResRef(thing['SoundSet']):
                    self.output_text(lpx + 6, lpy - 38, 'Evt=%d' % self._getSoundSetEventIndex(thing))
        finally:
            glPopMatrix()

    def _getAttenuationModel(self, sound):
        if sound is None:
            return 0
        try:
            raw = sound['AttenuationModel']
            if raw is None:
                return 0
            value = int(raw)
            if value < 0:
                return 0
            if value > 1:
                return 1
            return value
        except Exception:
            return 0

    def _attenuationModelName(self, model):
        if int(model) == 1:
            return 'inverse'
        return 'linear'

    def _cycleAttenuationModel(self, sound):
        current = self._getAttenuationModel(sound)
        nxt = 0 if current == 1 else 1
        if hasattr(sound, 'setAttenuationModel'):
            sound.setAttenuationModel(nxt)
        else:
            sound['AttenuationModel'] = nxt
        return nxt

    def _getSoundInnerRadius(self, sound, outer_radius):
        if sound is None:
            return 0.0
        for key in ('MinDistance', 'InnerRadius'):
            value = sound[key]
            try:
                if value is not None:
                    radius = float(value)
                    if radius > 0.0:
                        return min(radius, outer_radius)
            except (TypeError, ValueError):
                continue
        return min(0.5, outer_radius)

    def _estimateSoundGainAtListener(self, sound, outer_radius, inner_radius):
        if sound is None:
            return 0.0
        distance = self._getSoundDistanceToListener(sound)
        if distance >= outer_radius:
            return 0.0
        if distance <= inner_radius:
            return 1.0
        span = max(0.001, outer_radius - inner_radius)
        t = (distance - inner_radius) / span
        linear = max(0.0, min(1.0, 1.0 - t))
        model = self._getAttenuationModel(sound)
        if model == 1:
            # Inverse-ish falloff for tuning contrast while staying stable.
            return max(0.0, min(1.0, linear * linear))
        return linear

    def _bgrToRgbFloat(self, bgrValue, defaultColour):
        try:
            value = int(bgrValue)
        except (TypeError, ValueError):
            return defaultColour
        blue = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        red = value & 0xFF
        return (red / 255.0, green / 255.0, blue / 255.0)

    def _isNightInAreaData(self):
        if not self.area:
            return False
        try:
            return bool(int(self.area['IsNight']))
        except (TypeError, ValueError):
            return bool(self.area['IsNight'])

    def _getLightingPreview(self):
        isNight = bool(self.previewNightLighting)
        if isNight:
            ambient = self._bgrToRgbFloat(self.area['MoonAmbientColor'], (0.18, 0.18, 0.24))
            diffuse = self._bgrToRgbFloat(self.area['MoonDiffuseColor'], (0.55, 0.58, 0.62))
        else:
            # NWN stores ambient for night; day ambience is approximated from fog.
            ambient = self._bgrToRgbFloat(self.area['SunFogColor'], (0.22, 0.22, 0.22))
            diffuse = self._bgrToRgbFloat(self.area['SunDiffuseColor'], (0.95, 0.95, 0.9))
        return ambient, diffuse

    def _getListenerPosition(self):
        if self.players:
            for p in list(self.players.values()):
                x = getattr(p, 'x', None)
                y = getattr(p, 'y', None)
                if x is not None and y is not None:
                    z = getattr(p, 'z', 0.0)
                    try:
                        z = float(z)
                    except Exception:
                        z = 0.0
                    return (float(x), float(y), z)
        return (float(self.lookingAtX), float(self.lookingAtY), 0.0)

    def _getSoundDistanceToListener(self, sound):
        lx, ly, lz = self._getListenerPosition()
        sx = float(sound.getX())
        sy = float(sound.getY())
        sz = 0.0
        if hasattr(sound, 'getZ'):
            try:
                sz = float(sound.getZ())
            except Exception:
                sz = 0.0
        dx = sx - lx
        dy = sy - ly
        if self.ambientUse3DDistance:
            dz = sz - lz
            return math.sqrt(dx * dx + dy * dy + dz * dz)
        return math.sqrt(dx * dx + dy * dy)

    def _normalizeResRef(self, value):
        if value is None:
            return ''
        if isinstance(value, bytes):
            return value.decode('latin1', 'ignore').strip('\0').strip().lower()
        return str(value).strip('\0').strip().lower()

    def _resolvePreviewWavResRef(self, sound):
        # Prefer explicit per-instance sound resource.
        direct = self._normalizeResRef(sound['SoundResRef'])
        if direct:
            return direct

        # Fall back to first entry in referenced SSF set when present.
        sound_set = self._normalizeResRef(sound['SoundSet'])
        if sound_set:
            rm = neverglobals.getResourceManager()
            raw_ssf = rm.getRawResourceByName(sound_set + '.ssf')
            if raw_ssf:
                try:
                    ssf = SoundSetFile.SoundSetFile()
                    ssf.fromFile(io.BytesIO(raw_ssf))
                    entry_count = int(getattr(ssf, 'EntryCount', 0) or 0)
                    requested = self._getSoundSetEventIndex(sound)
                    if entry_count > 0:
                        requested = max(1, min(requested, entry_count))
                    entry = ssf.getEntryData(requested)
                    if entry and len(entry) > 0:
                        return self._normalizeResRef(entry[0])
                except Exception:
                    logger.debug('failed to resolve ssf preview sound for %s', sound_set, exc_info=True)
        return ''

    def _getSoundSetEventIndex(self, sound):
        value = 1
        if sound is None:
            return value
        try:
            raw = sound['SoundSetEvent']
            if raw is not None:
                value = int(raw)
        except Exception:
            value = 1
        return max(1, value)

    def _getSoundSetEntryCount(self, sound_set):
        if not sound_set:
            return 0
        sound_set = self._normalizeResRef(sound_set)
        if not sound_set:
            return 0
        if sound_set in self._ambientPreviewSSFCountCache:
            return self._ambientPreviewSSFCountCache[sound_set]
        count = 0
        rm = neverglobals.getResourceManager()
        raw_ssf = rm.getRawResourceByName(sound_set + '.ssf')
        if raw_ssf:
            try:
                ssf = SoundSetFile.SoundSetFile()
                ssf.fromFile(io.BytesIO(raw_ssf))
                count = int(getattr(ssf, 'EntryCount', 0) or 0)
            except Exception:
                count = 0
        self._ambientPreviewSSFCountCache[sound_set] = count
        return count

    def _cycleSoundSetEvent(self, sound):
        sound_set = self._normalizeResRef(sound['SoundSet'])
        if not sound_set:
            self.setStatus('SoundSet is empty; set SSF resref first')
            return False
        count = self._getSoundSetEntryCount(sound_set)
        if count <= 0:
            self.setStatus('Could not read SSF entries for %s' % sound_set)
            return False
        current = self._getSoundSetEventIndex(sound)
        next_event = current + 1
        if next_event > count:
            next_event = 1
        if hasattr(sound, 'setSoundSetEvent'):
            sound.setSoundSetEvent(next_event)
        else:
            sound['SoundSetEvent'] = next_event
        self.setStatus('SoundSetEvent: %d/%d' % (next_event, count))
        return True

    def _loadPreviewRawWav(self, wav_resref):
        if not wav_resref:
            return None
        if wav_resref in self._ambientPreviewRawCache:
            return self._ambientPreviewRawCache[wav_resref]
        rm = neverglobals.getResourceManager()
        raw = rm.getRawResourceByName(wav_resref + '.wav')
        self._ambientPreviewRawCache[wav_resref] = raw
        return raw

    def _ensureAmbientMixer(self):
        if self._ambientPreviewMixerReady:
            return True
        try:
            import pygame.mixer
            pygame.mixer.init(22050, -16, True, 1024)
            pygame.mixer.set_num_channels(16)
            self._ambientPreviewMixerReady = True
            return True
        except Exception:
            logger.debug('ambient preview mixer init failed', exc_info=True)
            return False

    def _stopAmbientPreview(self):
        for _key, voice in list(self._ambientPreviewActiveVoices.items()):
            channel = None
            try:
                _snd, channel = voice
            except Exception:
                channel = None
            if channel is not None:
                try:
                    channel.stop()
                except Exception:
                    pass
        self._ambientPreviewActiveVoices = {}
        self._ambientPreviewDebugVoices = []

    def _playAmbientPreviewRaw(self, sound_key, raw_wav, gain):
        if not raw_wav:
            return
        if not self._ensureAmbientMixer():
            return
        try:
            import pygame.mixer
            snd = pygame.mixer.Sound(io.BytesIO(raw_wav))
            channel = snd.play(loops=-1)
            if channel is None:
                return
            channel.set_volume(max(0.0, min(1.0, float(gain))))
            self._ambientPreviewActiveVoices[sound_key] = (snd, channel)
        except Exception:
            logger.debug('ambient preview playback failed', exc_info=True)

    def _refreshAmbientPreviewVoices(self, entries):
        target = {}
        for entry in entries:
            target[entry[0]] = entry

        for sound_key, voice in list(self._ambientPreviewActiveVoices.items()):
            if sound_key in target:
                continue
            channel = None
            try:
                _snd, channel = voice
            except Exception:
                channel = None
            if channel is not None:
                try:
                    channel.stop()
                except Exception:
                    pass
            self._ambientPreviewActiveVoices.pop(sound_key, None)

        for entry in entries:
            sound_key = entry[0]
            wav_resref = entry[1]
            gain = entry[2]
            clamped = max(0.0, min(1.0, float(gain)))
            if sound_key in self._ambientPreviewActiveVoices:
                channel = None
                try:
                    _snd, channel = self._ambientPreviewActiveVoices[sound_key]
                except Exception:
                    channel = None
                if channel is not None:
                    try:
                        channel.set_volume(clamped)
                        continue
                    except Exception:
                        pass
                self._ambientPreviewActiveVoices.pop(sound_key, None)

            raw_wav = self._loadPreviewRawWav(wav_resref)
            if raw_wav:
                self._playAmbientPreviewRaw(sound_key, raw_wav, clamped)

    def _updateAmbientPreview(self):
        if not self.ambientPreviewEnabled:
            return
        if not self.area or not self.sounds:
            self._stopAmbientPreview()
            return

        now = time.time()
        if now - self._ambientPreviewLastUpdate < 0.25:
            return
        self._ambientPreviewLastUpdate = now

        candidates = []

        for sound in self.sounds:
            try:
                radius = max(0.25, float(sound.getRadius()))
            except Exception:
                continue
            distance = self._getSoundDistanceToListener(sound)
            if distance > radius:
                continue

            wav_resref = self._resolvePreviewWavResRef(sound)
            if not wav_resref:
                continue

            gain = self._estimateSoundGainAtListener(sound, radius, self._getSoundInnerRadius(sound, radius))
            if gain <= 0.01:
                continue
            sound_key = (sound.getNevereditId(), wav_resref)
            descriptor = '#%s %s g=%.2f' % (str(sound.getNevereditId()), wav_resref, gain)
            sound_set = self._normalizeResRef(sound['SoundSet'])
            if sound_set:
                descriptor += ' e=%d' % self._getSoundSetEventIndex(sound)
            candidates.append((sound_key, wav_resref, gain, descriptor))

        if not candidates:
            self._stopAmbientPreview()
            return

        candidates.sort(key=lambda item: item[2], reverse=True)
        top_entries = candidates[:self._ambientPreviewMaxVoices]
        self._ambientPreviewDebugVoices = [entry[3] for entry in top_entries]
        self._refreshAmbientPreviewVoices(top_entries)

    def _isUsableBoundingBox(self, box):
        if box is None:
            return False
        try:
            mins = box[0]
            maxs = box[1]
            for i in range(3):
                if maxs[i] < mins[i]:
                    return False
            return True
        except Exception:
            return False

    def _getHighlightBoundingBox(self, model, root):
        # Prefer live node bounds over model-level bounds for highlight fidelity.
        if self._isUsableBoundingBox(getattr(root, 'boundingBox', None)):
            return root.boundingBox
        if self._isUsableBoundingBox(getattr(model, 'boundingBox', None)):
            return model.boundingBox
        try:
            box = self.calculateNodeTreeBoundingBox(root)
            if self._isUsableBoundingBox(box):
                return box
        except Exception:
            logger.debug('failed to recompute highlight bounding box',
                         exc_info=True)
        return None

    def drawTile(self,t,i):
        model = t.getModel()
        if not model:
            return
        root = model.getRootNode()
        if root is None:
            return
        x = i % self.area.getWidth()
        y = i // self.area.getWidth()
        tx = x*10.0+5.0
        ty = y*10.0+5.0
        h = t.getTileHeight()
        glPushMatrix()
        try:
            glTranslatef(tx,ty,h*5)
            glRotatef(t.getBearing(),0,0,1)
            self.handleNode(root)
        finally:
            glPopMatrix()

    def drawThings(self,things):
        for t in things['tiles']:
            self.drawTile(t[0],t[1])
        for t in things['things']:
            self.drawThing(t[0],t[1])
                
    def drawTree(self):
        #self.vCheckCount = 0
        self.cacheModelView()
        if not self.quadTreeRoot:
            self.clearModelView()
            return
        # Frustum tests occasionally misfire during rapid camera/view changes.
        # If the root sphere appears invisible, draw without culling this frame
        # to avoid temporary black frames.
        useFrustumCull = self.isSphereVisible(self.quadTreeRoot.boundingSphere)
        self.drawTreeHelper(self.quadTreeRoot,useFrustumCull)
        self.clearModelView()
        #print self.vCheckCount,'visibility checks for',\
        #      len(self.doors + self.placeables + self.creatures + self.tiles),\
        #      'things'
        
    def drawTreeHelper(self,node,useFrustumCull=True):
        #self.vCheckCount += 1
        if (not useFrustumCull) or self.isSphereVisible(node.boundingSphere):
            if len(node.children) > 0:
                for halves in node.children:
                    for c in halves:
                        self.drawTreeHelper(c,useFrustumCull)
            else:
                self.drawThings(node.contents)
        
        
    # The main drawing function. 
    def DrawGLScene(self):        
        GLWindow.DrawGLScene(self)
        if self.toPreprocess:
            self.preprocessNodes(self.toPreprocess.getModel(),'tag',bbox=True)
            self.preprocessedModels.add(self.toPreprocess.modelName)
            self.toPreprocess = None
        if not self.preprocessed:
            return
        cl = time.perf_counter()
        try:
            # Clear The Screen And The Depth Buffer
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            if not self.area:
                return
            self.setupCamera()

            ambient, diffuse = self._getLightingPreview()
            glLightfv(GL_LIGHT0,GL_AMBIENT,[ambient[0], ambient[1], ambient[2], 1.0])
            glLightfv(GL_LIGHT0,GL_DIFFUSE,[diffuse[0], diffuse[1], diffuse[2], 1.0])
            glLightfv(GL_LIGHT0,GL_SPECULAR,[1.0,1.0,1.0,1.0])
            glLightfv(GL_LIGHT0,GL_POSITION,[self.viewX,
                                             self.viewY,
                                             self.viewZ,
                                             1.0])

            w = self.area.getWidth()*10.0
            h = self.area.getHeight()*10.0

            name = 0
            self.drawTree()
            self._draw2DGridAndPaintOverlay()

            if self.beingPainted:
                self.drawThing(self.beingPainted,len(self.fullThingList))
                
            for p in list(self.players.values()):
                self.lock.acquire()
                x = p.x
                y = p.y
                a = (float(p.angle)/225.0)*360.0
                self.lock.release()
                glPushMatrix()
                glTranslatef(x,y,0.0)
                glRotate(a,0,0,1)
                if p.getObjectId() in self.textBoxes:
                    b = self.textBoxes[p.getObjectId()]
                    (b.x,b.y,b.z) = self.project(0.0,0.0,0.0)
                self.renderArrowOutline(0.6,colour=(1.0,0.1,0.1,1.0))
                glPopMatrix()

            self._updateAmbientPreview()
            self.drawOverlays()
            self.SwapBuffers()
            
        except KeyboardInterrupt:
            print('shutting down')
            sys.exit()
        if self.showFPS:
            d = time.perf_counter()-cl
            if d:
                self.fps = 1.0/d
        
    def get_standalone(cls, mod=None, icon=None):
        class MyApp(wx.App):
            def OnInit(self):
                frame = wx.Frame(None, -1, "Map", wx.DefaultPosition, wx.Size(400,400))
                if icon:
                    ic = wx.Icon(icon,wx.BITMAP_TYPE_GIF)
                    frame.SetIcon(ic)
                    #frame.tbicon = wx.TaskBarIcon()
                    #frame.tbicon.SetIcon(ic)
                self.win = MapWindow(frame)
                if mod:
                    m = Module(mod)
                    area = m.getArea(m['Mod_Entry_Area'])
                    self.win.setArea(area)
                frame.Show(True)
                self.SetTopWindow(frame)
                return True
        cls.app = MyApp(0)
        return cls.app.win
    get_standalone = classmethod(get_standalone)

    def start_standalone(cls):
        cls.app.MainLoop()
    start_standalone = classmethod(start_standalone)
    

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: ' + sys.argv[0] + ' <modfile>')
        sys.exit(1)

    #w = MapWindow.get_standalone()
    #w.makeQuadTreeHelper(QuadTreeNode(),0,0,4,4)
    MapWindow.get_standalone(sys.argv[1])
    MapWindow.start_standalone()
    
