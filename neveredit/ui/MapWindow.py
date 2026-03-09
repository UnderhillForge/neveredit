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
        self._ambientPreviewLastUpdate = 0.0
        self._ambientPreviewSoundKey = None
        self._ambientPreviewMixerReady = False
        self._ambientPreviewChannel = None
        self._ambientPreviewSoundObj = None
        self._ambientPreviewRawCache = {}
        self.soundRadiusEditing = None

        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightMouseDown)

        neverglobals.getResourceManager().addVisualChangeListener(self)
        self.toPreprocess = None
        self._missingSelectionWarnings = set()
        self._missingModelWarnings = set()
        
    def Destroy(self):
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
        else:
            self.beingPainted = None

    def _newAmbientSoundInstance(self):
        gff = GFFStruct(SoundInstance.GFF_STRUCT_ID)
        gff.add('Tag', 'sound_region', 'CExoString')
        gff.add('LocName', '', 'CExoLocString')
        gff.add('TemplateResRef', '', 'ResRef')
        gff.add('SoundSet', '', 'ResRef')
        gff.add('SoundResRef', '', 'ResRef')
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
            finally:
                glPopMatrix()
                glMatrixMode(GL_PROJECTION)
        finally:
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)

        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)

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
                self.output_text(lpx + 6, lpy - 10, 'Gain=%.2f %s' % (listener_gain, '(in)' if listener_in_range else '(out)'))
        finally:
            glPopMatrix()

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
        lx, ly, _ = self._getListenerPosition()
        sx = float(sound.getX())
        sy = float(sound.getY())
        dx = sx - lx
        dy = sy - ly
        distance = math.sqrt(dx * dx + dy * dy)
        if distance >= outer_radius:
            return 0.0
        if distance <= inner_radius:
            return 1.0
        span = max(0.001, outer_radius - inner_radius)
        t = (distance - inner_radius) / span
        return max(0.0, min(1.0, 1.0 - t))

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
                    return (float(x), float(y), 0.0)
        return (float(self.lookingAtX), float(self.lookingAtY), 0.0)

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
                    entry = ssf.getEntryData(1)
                    if entry and len(entry) > 0:
                        return self._normalizeResRef(entry[0])
                except Exception:
                    logger.debug('failed to resolve ssf preview sound for %s', sound_set, exc_info=True)
        return ''

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
            self._ambientPreviewMixerReady = True
            return True
        except Exception:
            logger.debug('ambient preview mixer init failed', exc_info=True)
            return False

    def _stopAmbientPreview(self):
        self._ambientPreviewSoundKey = None
        try:
            if self._ambientPreviewChannel is not None:
                self._ambientPreviewChannel.stop()
        except Exception:
            pass
        self._ambientPreviewChannel = None
        self._ambientPreviewSoundObj = None

    def _playAmbientPreviewRaw(self, sound_key, raw_wav):
        if not raw_wav:
            self._stopAmbientPreview()
            return
        if not self._ensureAmbientMixer():
            return
        try:
            import pygame.mixer
            snd = pygame.mixer.Sound(io.BytesIO(raw_wav))
            channel = snd.play(loops=-1)
            self._ambientPreviewSoundObj = snd
            self._ambientPreviewChannel = channel
            self._ambientPreviewSoundKey = sound_key
        except Exception:
            logger.debug('ambient preview playback failed', exc_info=True)
            self._stopAmbientPreview()

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

        lx, ly, _ = self._getListenerPosition()
        best_sound = None
        best_distance = None

        for sound in self.sounds:
            try:
                sx = float(sound.getX())
                sy = float(sound.getY())
                radius = max(0.25, float(sound.getRadius()))
            except Exception:
                continue
            dx = sx - lx
            dy = sy - ly
            distance = math.sqrt(dx*dx + dy*dy)
            if distance <= radius:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_sound = sound

        if best_sound is None:
            self._stopAmbientPreview()
            return

        wav_resref = self._resolvePreviewWavResRef(best_sound)
        if not wav_resref:
            self._stopAmbientPreview()
            return

        sound_key = (best_sound.getNevereditId(), wav_resref)
        if self._ambientPreviewSoundKey == sound_key and self._ambientPreviewChannel is not None:
            return

        self._stopAmbientPreview()
        raw_wav = self._loadPreviewRawWav(wav_resref)
        self._playAmbientPreviewRaw(sound_key, raw_wav)

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
    
