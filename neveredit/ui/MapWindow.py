import logging
logger = logging.getLogger('neveredit.ui')

from neveredit.util import Utils
Numeric = Utils.getNumPy()
LinearAlgebra = Utils.getLinAlg()

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
import string
import re
import weakref
Set = set
import time
import profile
import copy

from neveredit.ui.GLWindow import GLWindow
from neveredit.ui import ToolPalette
from neveredit.ui.MapLayersWindow import MapLayersWindow
from neveredit.game.Module import Module
from neveredit.game.Sound import SoundInstance
from neveredit.game.Trigger import TriggerInstance
from neveredit.game.Encounter import EncounterInstance
from neveredit.game.ResourceManager import ResourceManager
from neveredit.game.ChangeNotification import VisualChangeListener
from neveredit.util.Progressor import Progressor
from neveredit.util import neverglobals
from neveredit.util import gltf_export
from neveredit.render.ecs import RenderWorldCache, snapshot_thing, snapshot_tile
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
        # Initialize render world cache BEFORE GLWindow.__init__, since GLWindow calls clearCache()
        self._render_world_cache = RenderWorldCache()
        self._destroyed = False
        self._teardown_done = False
        
        GLWindow.__init__(self, parent)
        Progressor.__init__(self)
        
        self.zoom = 20
        self.maxZoom = 600
        
        self.players = {}
        self.area = None
        self.placeables = None
        self.doors = None
        self.creatures = None
        self.items = None
        self.encounters = None
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
        self._thingClipboard = None
        self._contextMenuThing = None
        self._contextMenuPoint = None

        # In-memory 2D drafting overlay for top-down terrain/height/object planning.
        self.map2DCells = {}
        self.map2DCellSize = 2.0
        self.map2DBrushRadius = 1
        self.map2DTerrainBrush = 0
        self.map2DAssetBrush = 1
        self.map2DHeightStep = 0.25
        self.map2DShowGrid = True
        self.map2DShowOcclusion = True
        self.map2DTileSelection = None
        self.map2DTileOrientation = 0
        self._map2DTilesetCacheKey = None
        self._map2DModelToTileId = {}
        self._map2DGroupByModel = {}

        self.layerVisibility = {
            'showGrid': True,
            'showCreatures': True,
            'showDoors': True,
            'showEncounters': True,
            'showItems': True,
            'showMerchants': True,
            'showPlaceables': True,
            'showSounds': True,
            'showWaypoints': True,
            'showStartLocation': True,
        }
        self.mapLayersWindowGeometry = None
        self.mapLayersWindowVisible = True
        self._loadLayerVisibility()
        self.map2DShowGrid = bool(self.layerVisibility.get('showGrid', self.map2DShowGrid))
        self.mapLayersWindow = None

        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightMouseDown)

        neverglobals.getResourceManager().addVisualChangeListener(self)
        self.toPreprocess = None
        self._missingSelectionWarnings = set()
        self._missingModelWarnings = set()
        self.Bind(wx.EVT_WINDOW_DESTROY, self._onMapWindowDestroy)
        wx.CallAfter(MapWindow._safeSyncMapLayersWindowVisibility, weakref.ref(self))

        # Toon (cel) shader
        self._toonProgram = None
        self._toonShaderFailed = False
        self.toonShading = False
        self.coreBatchingEnabled = True
        self.coreInstancingMinBatch = 5
        self.coreLodDistance = 170.0
        self.coreTileLodDistance = 140.0
        self.coreThingLodDistance = 110.0
        self.coreSmallThingLodDistance = 80.0
        self.coreDecorCullDistance = 210.0
        self.coreFogEnabled = True
        self.coreFogNearDistance = 120.0
        self.coreFogFarDistance = 250.0
        self.coreDistanceDesatStrength = 0.12
        self.coreToonBands = 7.0
        self.coreToonRimStrength = 0.28
        self.coreLodModelSuffixes = ('_lod', '_low', '_l')
        self._coreLodModelCache = {}
        self._coreLodPrepared = Set()
        
    _TOON_VERT = '''
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat3 uNormalMatrix;
varying vec3 Normal;
varying vec3 ViewDir;
void main() {
    vec4 viewPos = uModelViewMatrix * gl_Vertex;
    Normal = normalize(uNormalMatrix * gl_Normal);
    ViewDir = normalize(-viewPos.xyz);
    gl_Position = uProjectionMatrix * viewPos;
}
'''
    _TOON_FRAG = '''
varying vec3 Normal;
varying vec3 ViewDir;
uniform vec3 LightPosition;
void main() {
    vec3 n = normalize(Normal);
    vec3 lightDir = normalize(LightPosition);
    vec3 viewDir = normalize(ViewDir);
    float intensity = max(dot(lightDir, n), 0.0);
    float rim = pow(clamp(1.0 - max(dot(n, viewDir), 0.0), 0.0, 1.0), 2.6);

    vec3 ramp;
    if      (intensity > 0.98) ramp = vec3(1.18, 1.14, 1.06);
    else if (intensity > 0.90) ramp = vec3(1.06, 1.02, 0.96);
    else if (intensity > 0.78) ramp = vec3(0.94, 0.89, 0.82);
    else if (intensity > 0.62) ramp = vec3(0.82, 0.77, 0.70);
    else if (intensity > 0.46) ramp = vec3(0.68, 0.64, 0.60);
    else if (intensity > 0.30) ramp = vec3(0.52, 0.54, 0.58);
    else if (intensity > 0.16) ramp = vec3(0.38, 0.41, 0.47);
    else                       ramp = vec3(0.27, 0.30, 0.36);

    vec3 base = gl_FrontMaterial.diffuse.rgb;
    base = mix(base, vec3(dot(base, vec3(0.299, 0.587, 0.114))), 0.12);
    vec3 color = base * ramp;
    color += vec3(0.08, 0.07, 0.05) * rim;
    color += vec3(0.04, 0.04, 0.05);
    gl_FragColor = vec4(min(color, vec3(1.0)), gl_FrontMaterial.diffuse.a);
}
'''

    def _build_toon_shader(self):
        """Compile and link the toon shader program. Returns the GL program id
        or 0 if shaders are not supported or compilation failed."""
        try:
            from OpenGL.GL import (glCreateShader, glShaderSource,
                                   glCompileShader, glGetShaderiv,
                                   glGetShaderInfoLog, glCreateProgram,
                                   glAttachShader, glLinkProgram,
                                   glGetProgramiv, glGetProgramInfoLog,
                                   GL_VERTEX_SHADER, GL_FRAGMENT_SHADER,
                                   GL_COMPILE_STATUS, GL_LINK_STATUS)
            def _compile(src, kind):
                s = glCreateShader(kind)
                glShaderSource(s, src)
                glCompileShader(s)
                if not glGetShaderiv(s, GL_COMPILE_STATUS):
                    raise RuntimeError(glGetShaderInfoLog(s))
                return s
            vert = _compile(self._TOON_VERT, GL_VERTEX_SHADER)
            frag = _compile(self._TOON_FRAG, GL_FRAGMENT_SHADER)
            prog = glCreateProgram()
            glAttachShader(prog, vert)
            glAttachShader(prog, frag)
            glLinkProgram(prog)
            if not glGetProgramiv(prog, GL_LINK_STATUS):
                raise RuntimeError(glGetProgramInfoLog(prog))
            return prog
        except Exception as e:
            logger.warning('Toon shader build failed: %s', e)
            return 0

    def _toon_use(self):
        """Activate toon shader if available, building it lazily.
        Returns True if the shader program is active."""
        if self._toonShaderFailed:
            return False
        if self._toonProgram is None:
            prog = self._build_toon_shader()
            if not prog:
                self._toonShaderFailed = True
                return False
            self._toonProgram = prog
        try:
            from OpenGL.GL import (glUseProgram, glGetUniformLocation, glUniform3f,
                                   glGetFloatv, glUniformMatrix4fv, glUniformMatrix3fv,
                                   GL_FALSE, GL_PROJECTION_MATRIX, GL_MODELVIEW_MATRIX,
                                   GL_NORMAL_MATRIX)
            glUseProgram(self._toonProgram)

            proj = Numeric.array(glGetFloatv(GL_PROJECTION_MATRIX), 'f').reshape((4, 4))
            model = Numeric.array(glGetFloatv(GL_MODELVIEW_MATRIX), 'f').reshape((4, 4))
            normal = Numeric.array(glGetFloatv(GL_NORMAL_MATRIX), 'f').reshape((3, 3))

            loc = glGetUniformLocation(self._toonProgram, 'uProjectionMatrix')
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, proj.T.flatten())
            loc = glGetUniformLocation(self._toonProgram, 'uModelViewMatrix')
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, model.T.flatten())
            loc = glGetUniformLocation(self._toonProgram, 'uNormalMatrix')
            if loc >= 0:
                glUniformMatrix3fv(loc, 1, GL_FALSE, normal.T.flatten())

            loc = glGetUniformLocation(self._toonProgram, 'LightPosition')
            if loc >= 0:
                glUniform3f(loc, 0.38, 0.52, 0.76)
            return True
        except Exception as e:
            logger.warning('Toon shader activation failed; disabling toon mode: %s', e)
            self._toonShaderFailed = True
            self.toonShading = False
            return False

    def _toon_unuse(self):
        try:
            from OpenGL.GL import glUseProgram
            glUseProgram(0)
        except Exception:
            pass

    def Destroy(self):
        logger.info(f"[MAP] Destroy()")
        self._teardownMapWindow()
        GLWindow.Destroy(self)

    @staticmethod
    def _safeSyncMapLayersWindowVisibility(window_ref):
        win = window_ref()
        if win is None:
            return
        try:
            # Avoid IsBeingDeleted() calls here: during C++ teardown they can
            # themselves race and crash. Stick to Python-side guard flags.
            if getattr(win, '_destroyed', False):
                return
            win._syncMapLayersWindowVisibility()
        except Exception:
            # Ignore callbacks that race with window shutdown.
            return

    def _onMapWindowDestroy(self, event):
        try:
            if event.GetEventObject() is self:
                self._teardownMapWindow()
        except Exception:
            pass
        event.Skip()

    def _teardownMapWindow(self):
        if self._teardown_done:
            return
        logger.info(f"[MAP] Teardown starting")
        sys.stdout.flush()
        self._teardown_done = True
        self._destroyed = True
        # Disable animations immediately to prevent any deferred callbacks
        logger.info(f"[MAP] Disabling animations...")
        sys.stdout.flush()
        self.animationsEnabled = False
        logger.info(f"[MAP] Stopping timer...")
        sys.stdout.flush()
        if hasattr(self, '_stopAnimationTimer'):
            try:
                self._stopAnimationTimer()
                logger.info(f"[MAP] Timer stopped")
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"[MAP] Timer stop failed: {e}")
                sys.stdout.flush()
        # CRITICAL: Process all pending deferred callbacks before any cleanup
        # This ensures requestRedraw() calls complete safely before teardown
        try:
            logger.info(f"[MAP] Processing pending events...")
            sys.stdout.flush()
            import wx as wx_module
            wx_module.GetApp().ProcessPendingEvents()
            logger.info(f"[MAP] Pending events processed")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"[MAP] ProcessPendingEvents error: {e}")
            sys.stdout.flush()
        self._save2DDraftForCurrentArea()
        logger.info(f"[MAP] Saved 2D draft")
        sys.stdout.flush()
        if self.mapLayersWindow is not None:
            try:
                logger.info(f"[MAP] Syncing layers geometry...")
                sys.stdout.flush()
                self._onMapLayersGeometryChanged(self.mapLayersWindow.getWindowGeometry())
                self.mapLayersWindowVisible = bool(self.mapLayersWindow.IsShown())
                logger.info(f"[MAP] Layers geometry synced")
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"[MAP] Layers sync error: {e}")
                sys.stdout.flush()
        self._saveLayerVisibility()
        logger.info(f"[MAP] Saved layer visibility")
        sys.stdout.flush()
        if self.mapLayersWindow is not None:
            try:
                logger.info(f"[MAP] Destroying mapLayersWindow...")
                sys.stdout.flush()
                self.mapLayersWindow.Destroy()
                logger.info(f"[MAP] mapLayersWindow destroyed")
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"[MAP] mapLayersWindow.Destroy() error: {e}")
                sys.stdout.flush()
            self.mapLayersWindow = None
        logger.info(f"[MAP] Stopping ambient preview...")
        sys.stdout.flush()
        self._stopAmbientPreview()
        logger.info(f"[MAP] Stopped ambient preview")
        sys.stdout.flush()
        try:
            logger.info(f"[MAP] Removing visual change listener...")
            sys.stdout.flush()
            neverglobals.getResourceManager().removeVisualChangeListener(self)
            logger.info(f"[MAP] Visual change listener removed")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"[MAP] removeVisualChangeListener error: {e}")
            sys.stdout.flush()
        logger.info(f"[MAP] Teardown complete")

    def _ensureMapLayersWindow(self):
        if self._destroyed:
            return None
        if self.mapLayersWindow is None:
            self.mapLayersWindow = MapLayersWindow(None,
                                                  self._onMapLayerVisibilityChanged,
                                                  self.layerVisibility,
                                                  self._onMapLayersGeometryChanged,
                                                  self._onMapLayersVisibilityChanged)
            if self.mapLayersWindowGeometry:
                self.mapLayersWindow.applyWindowGeometry(self.mapLayersWindowGeometry)
            else:
                try:
                    p = self.GetScreenPosition()
                    self.mapLayersWindow.SetPosition(wx.Point(int(p.x + 24), int(p.y + 24)))
                except Exception:
                    pass
        return self.mapLayersWindow

    def _syncMapLayersWindowVisibility(self):
        if self._destroyed:
            return
        win = self._ensureMapLayersWindow()
        if win is None:
            return
        win.setLayers(self.layerVisibility)
        if self.mapLayersWindowVisible:
            if not win.IsShown():
                win.Show(True)
            win.Raise()
        else:
            if win.IsShown():
                win.Hide()

    def showMapLayersWindow(self):
        self.mapLayersWindowVisible = True
        self._syncMapLayersWindowVisibility()
        self._saveLayerVisibility()

    def hideMapLayersWindow(self):
        self.mapLayersWindowVisible = False
        self._syncMapLayersWindowVisibility()
        self._saveLayerVisibility()

    def toggleMapLayersWindow(self):
        self.mapLayersWindowVisible = not self.mapLayersWindowVisible
        self._syncMapLayersWindowVisibility()
        self._saveLayerVisibility()
        return self.mapLayersWindowVisible

    def _onMapLayerVisibilityChanged(self, layerState):
        for key, value in list(layerState.items()):
            if key in self.layerVisibility:
                self.layerVisibility[key] = bool(value)
        self.map2DShowGrid = bool(self.layerVisibility.get('showGrid', self.map2DShowGrid))
        self._pruneSelectionForLayerVisibility()
        self._saveLayerVisibility()
        self.requestRedraw()

    def _onMapLayersVisibilityChanged(self, isVisible):
        self.mapLayersWindowVisible = bool(isVisible)
        self._saveLayerVisibility()

    def _onMapLayersGeometryChanged(self, geometry):
        if not isinstance(geometry, dict):
            return
        self.mapLayersWindowGeometry = {
            'x': int(geometry.get('x', 0)),
            'y': int(geometry.get('y', 0)),
            'w': int(geometry.get('w', 250)),
            'h': int(geometry.get('h', 250)),
        }
        self._saveLayerVisibility()

    def _getLayerVisibilityPath(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        return os.path.join(repo_root, '.neveredit_map_layers.json')

    def _loadLayerVisibility(self):
        path = self._getLayerVisibilityPath()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r') as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return
            layer_payload = payload.get('layers', payload)
            if isinstance(layer_payload, dict):
                self._migrateLegacyLayerVisibility(layer_payload)
                for key in list(self.layerVisibility.keys()):
                    if key in layer_payload:
                        self.layerVisibility[key] = bool(layer_payload[key])
            geom = payload.get('mapLayersWindow')
            if isinstance(geom, dict):
                self.mapLayersWindowGeometry = {
                    'x': int(geom.get('x', 0)),
                    'y': int(geom.get('y', 0)),
                    'w': int(geom.get('w', 250)),
                    'h': int(geom.get('h', 250)),
                }
            if 'mapLayersWindowVisible' in payload:
                self.mapLayersWindowVisible = bool(payload.get('mapLayersWindowVisible'))
        except Exception:
            logger.debug('failed to load map layer visibility settings', exc_info=True)

    def _migrateLegacyLayerVisibility(self, layer_payload):
        if not isinstance(layer_payload, dict):
            return
        if 'showAmbient' in layer_payload and 'showSounds' not in layer_payload:
            layer_payload['showSounds'] = bool(layer_payload.get('showAmbient'))
        if 'showWaypoints' in layer_payload and 'showStartLocation' not in layer_payload:
            layer_payload['showStartLocation'] = bool(layer_payload.get('showWaypoints'))
        if 'showObjects' in layer_payload:
            objects_visible = bool(layer_payload.get('showObjects'))
            for key in ('showCreatures', 'showDoors', 'showEncounters',
                        'showItems', 'showMerchants', 'showPlaceables'):
                layer_payload.setdefault(key, objects_visible)
        if 'showGrid' not in layer_payload:
            layer_payload['showGrid'] = True

    def _saveLayerVisibility(self):
        path = self._getLayerVisibilityPath()
        try:
            with open(path, 'w') as f:
                payload = {
                    'layers': self.layerVisibility,
                    'mapLayersWindow': self.mapLayersWindowGeometry,
                    'mapLayersWindowVisible': self.mapLayersWindowVisible,
                }
                json.dump(payload, f, indent=2, sort_keys=True)
            return True
        except Exception:
            logger.debug('failed to save map layer visibility settings', exc_info=True)
            return False
        
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
            self.map2DTileSelection = evt.getData()
        else:
            self.beingPainted = None
            self.map2DTileSelection = None

    def refreshChangedTiles(self, changed_indices):
        if not self.area:
            return
        self.tiles = self.area.getTiles()
        if not self.tiles:
            self.requestRedraw()
            return

        if self.preprocessed and not self.preprocessing:
            for index in changed_indices:
                if index < 0 or index >= len(self.tiles):
                    continue
                tile = self.tiles[index]
                model = self._getModelSafe(tile, 'tile')
                if model and tile.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model, 't' + repr(index), bbox=True)
                    self.preprocessedModels.add(tile.modelName)
                elif not model:
                    self._warnMissingModelOnce('tile', tile.getName())

        self.makeQuadTree()
        if self.preprocessed and not self.preprocessing:
            self._rebuildRenderWorldCache()
        else:
            self._render_world_cache.reset(len(self.tiles or []), len(self.fullThingList or []))
        self.requestRedraw()

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
            thing = self.getThingHit(self.highlight)
            if not self._isThingSelectableForLayers(thing):
                self.highlight = None
                self.highlightBox = None
                self.requestRedraw()
                return
            self.selectHighlighted(evt)
            self._ensureContextMenuIds()
            self._contextMenuThing = thing
            try:
                self._contextMenuPoint = self.mouseToPointOnBasePlane(float(evt.GetX()),
                                                                       float(self.height - evt.GetY()))
            except Exception:
                self._contextMenuPoint = (float(thing.getX()), float(thing.getY()))

            menu = wx.Menu()
            menu.Append(self.EDIT_THING_ID, 'Edit')
            menu.Append(self.COPY_THING_ID, 'Copy')
            menu.Append(self.PASTE_THING_ID, 'Paste')
            menu.Append(self.SAVE_CUSTOM_THING_ID, 'Save Custom')
            menu.Append(self.REMOVE_THING_ID, 'Remove')
            menu.AppendSeparator()
            menu.Append(self.EXPORT_WEB_THING_ID, 'Export for Web (glTF)')
            menu.Enable(self.PASTE_THING_ID, self._thingClipboard is not None)
            menu.Enable(self.EXPORT_WEB_THING_ID, bool(thing.getModel()))

            self.PopupMenu(menu, evt.GetPosition())
            menu.Destroy()
            self.beingDragged = None
            self._contextMenuThing = None

    def _ensureContextMenuIds(self):
        if hasattr(self, 'EDIT_THING_ID'):
            return
        self.EDIT_THING_ID = wx.NewId()
        self.COPY_THING_ID = wx.NewId()
        self.PASTE_THING_ID = wx.NewId()
        self.SAVE_CUSTOM_THING_ID = wx.NewId()
        self.REMOVE_THING_ID = wx.NewId()
        self.EXPORT_WEB_THING_ID = wx.NewId()

        self.Bind(wx.EVT_MENU, self.OnContextEditThing, id=self.EDIT_THING_ID)
        self.Bind(wx.EVT_MENU, self.OnContextCopyThing, id=self.COPY_THING_ID)
        self.Bind(wx.EVT_MENU, self.OnContextPasteThing, id=self.PASTE_THING_ID)
        self.Bind(wx.EVT_MENU, self.OnContextSaveCustomThing, id=self.SAVE_CUSTOM_THING_ID)
        self.Bind(wx.EVT_MENU, self.OnContextRemoveThing, id=self.REMOVE_THING_ID)
        self.Bind(wx.EVT_MENU, self.OnContextExportThingForWeb, id=self.EXPORT_WEB_THING_ID)

    def _getContextMenuThing(self):
        thing = self._contextMenuThing
        if thing is not None:
            return thing
        if self.highlight is None:
            return None
        return self.getThingHit(self.highlight)

    def _notifyThingListChanged(self, selectedThing=None):
        selected_id = None
        if selectedThing is not None:
            selected_id = selectedThing.getNevereditId()
        event = ThingAddedEvent(self.GetId(), selected_id)
        self.GetEventHandler().AddPendingEvent(event.Clone())

    def _assignFreshObjectId(self, thing):
        if thing is None or not hasattr(thing, 'hasProperty'):
            return
        if not thing.hasProperty('ObjectId'):
            return
        max_id = 0
        for existing in self.fullThingList:
            if not hasattr(existing, 'hasProperty') or not existing.hasProperty('ObjectId'):
                continue
            try:
                object_id = int(existing.getObjectId())
            except Exception:
                continue
            if object_id > max_id:
                max_id = object_id
        thing['ObjectId'] = max_id + 1

    def _normalizeResRef(self, value):
        if value is None:
            return ''
        if isinstance(value, bytes):
            text = value.decode('latin1', 'ignore')
        else:
            text = str(value)
        text = text.strip().strip('\0').lower()
        out = []
        for ch in text:
            if ch in string.ascii_lowercase or ch in string.digits or ch == '_':
                out.append(ch)
            else:
                out.append('_')
        text = ''.join(out)
        while '__' in text:
            text = text.replace('__', '_')
        return text[:16].strip('_')

    def _defaultBlueprintResRef(self, thing):
        if thing is None:
            return 'custom_asset'
        template_resref = None
        if hasattr(thing, 'hasProperty') and thing.hasProperty('TemplateResRef'):
            template_resref = thing['TemplateResRef']
        candidate = self._normalizeResRef(template_resref)
        if candidate:
            return candidate
        candidate = self._normalizeResRef(thing['Tag'])
        if candidate:
            return candidate
        return 'custom_asset'

    def _trySwitchToPropsPage(self):
        notebook = self.GetParent()
        if notebook and hasattr(notebook, 'selectPageByTag'):
            notebook.selectPageByTag('props')
            if hasattr(notebook, 'setPageSyncByTag'):
                notebook.setPageSyncByTag('props', True)

    def OnContextEditThing(self,evt):
        thing = self._getContextMenuThing()
        if thing is None:
            return
        self.selectThingById(thing.getNevereditId())
        self._trySwitchToPropsPage()

    def OnContextCopyThing(self,evt):
        thing = self._getContextMenuThing()
        if thing is None or not self._isThingSelectableForLayers(thing):
            return
        try:
            self._thingClipboard = thing.clone()
        except Exception:
            logger.exception('failed to copy thing')
            self._thingClipboard = None
            self.setStatus('Copy failed.')
            return
        self.setStatus('Copied "%s".' % thing.getName())

    def OnContextPasteThing(self,evt):
        if self._thingClipboard is None:
            self.setStatus('Nothing to paste.')
            return
        if not self.area:
            self.setStatus('No active area for paste.')
            return
        try:
            thing = self._thingClipboard.clone()
        except Exception:
            logger.exception('failed to clone clipboard thing for paste')
            self.setStatus('Paste failed.')
            return

        if hasattr(thing, 'setX') and hasattr(thing, 'setY'):
            if self._contextMenuPoint:
                x, y = self._contextMenuPoint
            else:
                x, y = self.lookingAtX, self.lookingAtY
            thing.setX(float(x))
            thing.setY(float(y))
        self._assignFreshObjectId(thing)

        before = len(self.fullThingList)
        self.area.addThing(thing)
        self.refreshThingList()
        if len(self.fullThingList) <= before:
            self.setStatus('Paste is not supported for this object type.')
            return

        self.makeQuadTree()
        self.selected = []
        self.highlight = None
        try:
            index = self.fullThingList.index(thing)
            self.selected = [index]
            self.highlight = index
            self.setHighlightBox(index)
        except Exception:
            pass
        self.requestRedraw()
        self._notifyThingListChanged(thing)
        self.setStatus('Pasted "%s".' % thing.getName())

    def OnContextSaveCustomThing(self,evt):
        thing = self._getContextMenuThing()
        if thing is None or not self.area:
            return
        default_resref = self._defaultBlueprintResRef(thing)
        dlg = wx.TextEntryDialog(self,
                                 'Enter blueprint resref (max 16 chars):',
                                 'Save Custom',
                                 default_resref)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            resref = self._normalizeResRef(dlg.GetValue())
        finally:
            dlg.Destroy()

        if not resref:
            self.setStatus('Invalid blueprint resref.')
            return

        ok, message = self.area.saveThingAsBlueprint(thing, resref)
        if not ok:
            self.setStatus(message)
            return

        neverglobals.getResourceManager().moduleResourceListChanged()
        self.setStatus('Saved custom blueprint: %s' % message)

    def OnContextRemoveThing(self,evt):
        thing = self._getContextMenuThing()
        if thing is None or not self.area:
            return
        if not self.area.removeThing(thing):
            self.setStatus('Remove failed.')
            return

        self.refreshThingList()
        self.makeQuadTree()
        self.selected = []
        self.highlight = None
        self.highlightBox = None
        self.beingDragged = None
        self.requestRedraw()
        self._notifyThingListChanged(None)
        self.setStatus('Removed "%s".' % thing.getName())

    def OnContextExportThingForWeb(self,evt):
        thing = self._getContextMenuThing()
        if thing is None:
            return
        model = thing.getModel()
        if not model:
            self.setStatus('Export for Web is only available for model-based assets.')
            return

        model_name = self._defaultBlueprintResRef(thing) or 'asset'

        dlg = wx.DirDialog(self,
                           'Choose export folder for "%s"' % model_name,
                           style=wx.DD_DEFAULT_STYLE)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            output_dir = dlg.GetPath()
        finally:
            dlg.Destroy()

        try:
            result = gltf_export.export_model_to_gltf_folder(
                model,
                output_dir,
                model_name,
                self.isRenderableMeshNode,
                self.getNodeDrawMode)
        except Exception:
            logger.exception('failed to export for %s', thing.getName())
            self.setStatus('Export for Web failed.')
            return

        parts = ['Exported %s.gltf' % model_name]
        if result.get('texture_count', 0):
            parts.append('%d texture(s)' % result['texture_count'])
        if result.get('animation_count', 0):
            parts.append('%d animation(s)' % result['animation_count'])
        self.setStatus(' — '.join(parts) + '  →  ' + output_dir)

    _SELECT_HINT = ('Selected: drag to move  |  Ctrl+drag: raise/lower Z  |  Rotate tool: drag to rotate  '
                    '|  Arrow keys: nudge XY  |  PgUp/PgDn: nudge Z  |  [/]: rotate 15\xb0')

    def selectHighlighted(self,evt):
        thing = self.getThingHit(self.highlight)
        if thing is None or not self._isThingSelectableForLayers(thing):
            return
        self.selected = [self.highlight]
        self.setStatus(self._SELECT_HINT)
        self.beingDragged = thing
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
        if self._isCoreProfileContext():
            _proj, _view, view_proj = self._buildCameraMatrices()
            x, y, z = self._projectWithViewProjection((self.beingDragged.getX(),
                                                       self.beingDragged.getY(),
                                                       0.0),
                                                      view_proj)
        else:
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
                if thing is None or not self._isThingSelectableForLayers(thing):
                    self.highlight = None
                    self.highlightBox = None
                    self.requestRedraw()
                    return
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

        if getattr(self, '_core_profile_stub_mode', False):
            if not getattr(self, '_logged_core_stub_input_warning', False):
                logger.warning('Core profile mode: using matrix-based picking path; legacy matrix-stack interaction path disabled')
                self._logged_core_stub_input_warning = True

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
                if not self._isThingSelectableForLayers(thing):
                    continue
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
                elif self._isPolygonRegionThing(thing):
                    if self._isPointInsideTrigger(thing, x, y):
                        center_x, center_y = self._getTriggerCentroid(thing)
                        intersect = math.sqrt((center_x - x) * (center_x - x) +
                                              (center_y - y) * (center_y - y))
                        if intersect < closestIntersect:
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
                elif self._canUseGenericThingMarker(thing):
                    dx = thing.getX() - x
                    dy = thing.getY() - y
                    radial = math.sqrt(dx*dx + dy*dy)
                    marker_radius = 0.8
                    if radial <= marker_radius and radial < closestIntersect:
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

            self._updateRenderWorldThingEntry(self.beingDragged)

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
            self._updateRenderWorldThingEntry(self.beingDragged)
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
            if key_char == 'r':
                self.map2DTileOrientation = (self.map2DTileOrientation + 1) % 4
                self.setStatus('2D tile rotation: %d°' % (self.map2DTileOrientation * 90))
                self.requestRedraw()
                return
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
                self.layerVisibility['showGrid'] = self.map2DShowGrid
                if self.mapLayersWindow is not None:
                    self.mapLayersWindow.setLayers(self.layerVisibility)
                self._saveLayerVisibility()
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
                self._notify2DDraftChanged()
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

        if key_char == 's':
            self.toonShading = not self.toonShading
            if self.toonShading:
                self.setStatus('Toon shading: on  (press S to toggle)')
            else:
                self.setStatus('Toon shading: off')
            self.requestRedraw()
            return

        if key_char == 'v':
            self.mapLayersWindowVisible = not self.mapLayersWindowVisible
            self._syncMapLayersWindowVisibility()
            if self.mapLayersWindowVisible:
                self.setStatus('Map Layers window: shown')
            else:
                self.setStatus('Map Layers window: hidden')
            self._saveLayerVisibility()
            return

        # ── Keyboard object transforms ──────────────────────────────────────
        if self.mode in (ToolPalette.SELECTION_TOOL, ToolPalette.ROTATE_TOOL) and self.selected:
            thing = self.getThingHit(self.selected[0])
            if thing is not None:
                kc = evt.GetKeyCode()
                _nudge = 0.1
                _rot_step = math.pi / 12.0  # 15 degrees
                moved = False
                if kc == wx.WXK_LEFT:
                    thing.setX(thing.getX() - _nudge); moved = True
                elif kc == wx.WXK_RIGHT:
                    thing.setX(thing.getX() + _nudge); moved = True
                elif kc == wx.WXK_UP:
                    thing.setY(thing.getY() + _nudge); moved = True
                elif kc == wx.WXK_DOWN:
                    thing.setY(thing.getY() - _nudge); moved = True
                elif kc == wx.WXK_PAGEUP:
                    z = min(25.0, thing.getZ() + _nudge)
                    thing.setZ(z); moved = True
                elif kc == wx.WXK_PAGEDOWN:
                    z = max(0.0, thing.getZ() - _nudge)
                    thing.setZ(z); moved = True
                elif key_char == ']':
                    thing.setBearing((thing.getBearing() + _rot_step) % (2.0 * math.pi)); moved = True
                elif key_char == '[':
                    thing.setBearing((thing.getBearing() - _rot_step) % (2.0 * math.pi)); moved = True
                if moved:
                    event = MoveEvent(self.GetId(), thing.getNevereditId(),
                                      thing.getX(), thing.getY(), thing.getBearing())
                    self.GetEventHandler().AddPendingEvent(event.Clone())
                    self._updateRenderWorldThingEntry(thing)
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

    def _getModelSafe(self, thing, category, want_copy=False):
        """Return thing model, swallowing lookup exceptions so map rendering continues."""
        try:
            return thing.getModel(copy=want_copy)
        except Exception as exc:
            key = ('model-error', category, getattr(thing, 'getNevereditId', lambda: id(thing))())
            if key not in self._missingModelWarnings:
                self._missingModelWarnings.add(key)
                logger.exception('model lookup failed for %s (%s): %s',
                                 getattr(thing, 'getName', lambda: 'unknown')(),
                                 category,
                                 exc)
            return None

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
        if self._isCoreProfileContext():
            _proj, _view, view_proj = self._buildCameraMatrices()
            inv_view_proj = LinearAlgebra.inverse(view_proj)
            near = Numeric.array(self._unprojectWithViewProjectionInverse(x, y, 0.0, inv_view_proj), 'f')
            far = Numeric.array(self._unprojectWithViewProjectionInverse(x, y, 1.0, inv_view_proj), 'f')
            return near, far

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

    def _boundsToTileCoverage(self, min_x, min_y, max_x, max_y):
        if not self.area:
            return []
        area_width = max(0, self.area.getWidth() - 1)
        area_height = max(0, self.area.getHeight() - 1)
        start_x = int(math.floor(float(min_x) / 10.0))
        start_y = int(math.floor(float(min_y) / 10.0))
        end_x = int(math.floor(float(max_x) / 10.0))
        end_y = int(math.floor(float(max_y) / 10.0))
        start_x = max(0, min(area_width, start_x))
        start_y = max(0, min(area_height, start_y))
        end_x = max(0, min(area_width, end_x))
        end_y = max(0, min(area_height, end_y))
        coverage = []
        for y in range(start_y, end_y + 1):
            for x in range(start_x, end_x + 1):
                coverage.append((x, y))
        return coverage

    def _getTriggerLocalPoints(self, thing):
        points = []
        if hasattr(thing, 'getGeometryPoints'):
            try:
                geometry_points = thing.getGeometryPoints()
            except Exception:
                geometry_points = []
            for point in geometry_points:
                try:
                    points.append((float(point.getX()),
                                   float(point.getY()),
                                   float(point.getZ())))
                except Exception:
                    continue
        if points:
            return points
        return list(getattr(thing, 'DEFAULT_GEOMETRY_POINTS', []))

    def _isPolygonRegionThing(self, thing):
        return isinstance(thing, (TriggerInstance, EncounterInstance))

    def _getTriggerWorldPoints(self, thing):
        angle = float(thing.getBearing() or 0.0)
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        origin_x = float(thing.getX())
        origin_y = float(thing.getY())
        origin_z = float(thing.getZ())
        world_points = []
        for local_x, local_y, local_z in self._getTriggerLocalPoints(thing):
            world_points.append((origin_x + local_x * cos_angle - local_y * sin_angle,
                                 origin_y + local_x * sin_angle + local_y * cos_angle,
                                 origin_z + local_z))
        return world_points

    def _getTriggerBounds(self, thing):
        points = self._getTriggerWorldPoints(thing)
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)

    def _getTriggerCentroid(self, thing):
        points = self._getTriggerWorldPoints(thing)
        if not points:
            return float(thing.getX()), float(thing.getY())
        count = float(len(points))
        return (sum([point[0] for point in points]) / count,
                sum([point[1] for point in points]) / count)

    def _distancePointToSegment(self, px, py, ax, ay, bx, by):
        dx = bx - ax
        dy = by - ay
        if dx == 0.0 and dy == 0.0:
            return math.sqrt((px - ax) * (px - ax) + (py - ay) * (py - ay))
        t = ((px - ax) * dx + (py - ay) * dy) / float(dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        nx = ax + t * dx
        ny = ay + t * dy
        return math.sqrt((px - nx) * (px - nx) + (py - ny) * (py - ny))

    def _isPointInsideTrigger(self, thing, x, y):
        points = self._getTriggerWorldPoints(thing)
        if len(points) < 3:
            return False
        inside = False
        for i in range(len(points)):
            x1, y1, _ = points[i]
            x2, y2, _ = points[(i + 1) % len(points)]
            intersects = ((y1 > y) != (y2 > y)) and \
                         (x < (x2 - x1) * (y - y1) / float((y2 - y1) or 1e-9) + x1)
            if intersects:
                inside = not inside
        if inside:
            return True
        for i in range(len(points)):
            x1, y1, _ = points[i]
            x2, y2, _ = points[(i + 1) % len(points)]
            if self._distancePointToSegment(x, y, x1, y1, x2, y2) <= 0.35:
                return True
        return False

    def _getThingTileCoverage(self, thing):
        if not self.area:
            return []
        if self._isPolygonRegionThing(thing):
            bounds = self._getTriggerBounds(thing)
            if bounds is not None:
                return self._boundsToTileCoverage(bounds[0], bounds[1], bounds[2], bounds[3])
        if hasattr(thing, 'getRadius'):
            radius = max(0.1, float(thing.getRadius()))
            return self._boundsToTileCoverage(float(thing.getX()) - radius,
                                              float(thing.getY()) - radius,
                                              float(thing.getX()) + radius,
                                              float(thing.getY()) + radius)
        x = int(math.floor(float(thing.getX()) / 10.0))
        y = int(math.floor(float(thing.getY()) / 10.0))
        if x >= self.area.getWidth():
            x = self.area.getWidth() - 1
        if y >= self.area.getHeight():
            y = self.area.getHeight() - 1
        x = max(0, x)
        y = max(0, y)
        return [(x, y)]

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
        self._render_world_cache.reset()

    def _rebuildRenderWorldCache(self):
        tile_count = len(self.tiles or [])
        thing_count = len(self.fullThingList or [])
        self._render_world_cache.reset(tile_count, thing_count)
        if not self.area:
            return

        area_width = self.area.getWidth()
        for tile_index, tile in enumerate(self.tiles or []):
            model = self._getModelSafe(tile, 'tile') if self.preprocessed else getattr(tile, 'model', None)
            self._render_world_cache.set_tile(tile_index, snapshot_tile(tile, tile_index, area_width, model=model))

        for thing_index, thing in enumerate(self.fullThingList or []):
            model = self._getModelSafe(thing, 'thing') if self.preprocessed else getattr(thing, 'model', None)
            self._render_world_cache.set_thing(thing_index, snapshot_thing(thing, thing_index=thing_index, model=model))

    def _ensureRenderWorldCache(self):
        if len(self._render_world_cache.tile_entries) != len(self.tiles or []):
            self._rebuildRenderWorldCache()
            return
        if len(self._render_world_cache.thing_entries) != len(self.fullThingList or []):
            self._rebuildRenderWorldCache()

    def _updateRenderWorldThingEntry(self, thing):
        if thing is None:
            return
        try:
            thing_index = self.fullThingList.index(thing)
        except (AttributeError, ValueError):
            return
        model = self._getModelSafe(thing, 'thing') if self.preprocessed else getattr(thing, 'model', None)
        self._render_world_cache.set_thing(
            thing_index,
            snapshot_thing(thing, thing_index=thing_index, model=model)
        )

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
            model = self._getModelSafe(d, 'door')
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
            model = self._getModelSafe(p, 'placeable')
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
            base_model = self._getModelSafe(c, 'creature')
            if not base_model:
                if not getattr(c, 'usesGenericMarkerFallback', lambda: False)():
                    self._warnMissingModelOnce('creature', c.getName())
                continue

            tint_context = self._getCreatureTintContext(c)
            tint_signature = self._normalizeTintSignature(tint_context)
            part_context = self._getCreatureBodyPartContext(c)
            part_signature = self._normalizePartSignature(part_context)
            variant_key = ('creature', c.modelName, tint_signature, part_signature)

            model = self.creatureModelVariants.get(variant_key)
            if model is None:
                if tint_signature:
                    model = self._getModelSafe(c, 'creature', want_copy=True)
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
            model = self._getModelSafe(t, 'tile')
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
            model = self._getModelSafe(w, 'waypoint')
            if model:
                if w.modelName not in self.preprocessedModels:
                    self.preprocessNodes(model,'w'+repr(i),bbox=True)
                    self.preprocessedModels.add(w.modelName)
            else:
                self._warnMissingModelOnce('waypoint', w.getName())
        logger.info('preprocess phase waypoints: %.3fs', time.perf_counter() - phase_start)
        self.setProgress(0)
        self.setStatus("Map display prepared.")
        self.preprocessed = True
        self._rebuildRenderWorldCache()
        logger.info('preprocess total: %.3fs', time.perf_counter() - preprocess_start)
        
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
            for x, y in self._getThingTileCoverage(thing):
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
            self.items = None
            self.encounters = None
            self.tiles = None
            self.triggers = None
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
            self.items = area.getItems()
            self.tiles = area.getTiles()
            self.triggers = area.getTriggers()
            self.encounters = area.getEncounters()
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
        self.fullThingList = ((self.doors or []) +
                              (self.placeables or []) +
                              (self.creatures or []) +
                              (self.items or []) +
                              (self.triggers or []) +
                              (self.encounters or []) +
                              (self.waypoints or []) +
                              (self.sounds or []))
        self.doorIdSet = Set([d.getNevereditId() for d in (self.doors or [])])
        self.placeableIdSet = Set([p.getNevereditId() for p in (self.placeables or [])])
        self.creatureIdSet = Set([c.getNevereditId() for c in (self.creatures or [])])
        self.itemIdSet = Set([i.getNevereditId() for i in (self.items or [])])
        self.merchantIdSet = Set([c.getNevereditId() for c in (self.creatures or [])
                                  if self._looksLikeMerchant(c)])
        self.triggerIdSet = Set([t.getNevereditId() for t in (self.triggers or [])])
        self.encounterIdSet = Set([e.getNevereditId() for e in (self.encounters or [])])
        self.waypointIdSet = Set([w.getNevereditId() for w in (self.waypoints or [])])
        self.startLocationIdSet = Set([w.getNevereditId() for w in (self.waypoints or [])
                                       if self._looksLikeStartLocation(w)])
        self.soundIdSet = Set([s.getNevereditId() for s in (self.sounds or [])])
        if getattr(self, 'preprocessed', False) and not getattr(self, 'preprocessing', False):
            self._rebuildRenderWorldCache()
        else:
            self._render_world_cache.reset(len(self.tiles or []), len(self.fullThingList or []))

    def _thingText(self, thing, key):
        if not hasattr(thing, 'hasProperty'):
            return ''
        if not thing.hasProperty(key):
            return ''
        try:
            value = thing[key]
        except Exception:
            return ''
        if value is None:
            return ''
        if hasattr(value, 'getString'):
            try:
                value = value.getString()
            except Exception:
                value = ''
        if isinstance(value, bytes):
            value = value.decode('latin1', 'ignore')
        return str(value).strip().strip('\0')

    def _looksLikeMerchant(self, thing):
        merged = ' '.join([
            self._thingText(thing, 'Tag'),
            self._thingText(thing, 'TemplateResRef'),
            self._thingText(thing, 'Conversation'),
            self._thingText(thing, 'FirstName'),
            self._thingText(thing, 'LastName'),
        ]).lower()
        if not merged:
            return False
        return bool(re.search(r'\b(merchant|shop|store|vendor|trader)\b', merged))

    def _looksLikeStartLocation(self, thing):
        merged = ' '.join([
            self._thingText(thing, 'Tag'),
            self._thingText(thing, 'TemplateResRef'),
            self._thingText(thing, 'MapNote'),
            self._thingText(thing, 'LocalizedName'),
        ]).lower()
        if not merged:
            return False
        return bool(re.search(r'\b(start|spawn|entry)\b', merged))

    def _isThingSelectableForLayers(self, thing):
        return self._isThingVisibleForLayers(thing)

    def _pruneSelectionForLayerVisibility(self):
        changed = False

        if self.highlight is not None:
            highlighted = self.getThingHit(self.highlight)
            if not self._isThingSelectableForLayers(highlighted):
                self.highlight = None
                self.highlightBox = None
                changed = True

        if self.selected:
            filtered = []
            for sid in self.selected:
                thing = self.getThingHit(sid)
                if thing is not None and self._isThingSelectableForLayers(thing):
                    filtered.append(sid)
            if filtered != self.selected:
                self.selected = filtered
                changed = True

        if self.beingDragged is not None and not self._isThingSelectableForLayers(self.beingDragged):
            self.beingDragged = None
            changed = True

        if self.soundRadiusEditing is not None and not self._isThingSelectableForLayers(self.soundRadiusEditing):
            self.soundRadiusEditing = None
            changed = True

        return changed

    def _isThingVisibleForLayers(self, thing):
        if thing is None:
            return False
        tid = getattr(thing, 'entity_id', None)
        if tid is None and hasattr(thing, 'getNevereditId'):
            tid = thing.getNevereditId()
        if tid is None:
            return True
        if tid in getattr(self, 'soundIdSet', Set()):
            return bool(self.layerVisibility.get('showSounds', True))
        if tid in getattr(self, 'doorIdSet', Set()):
            return bool(self.layerVisibility.get('showDoors', True))
        if tid in getattr(self, 'placeableIdSet', Set()):
            return bool(self.layerVisibility.get('showPlaceables', True))
        if tid in getattr(self, 'itemIdSet', Set()):
            return bool(self.layerVisibility.get('showItems', True))
        if tid in getattr(self, 'encounterIdSet', Set()):
            return bool(self.layerVisibility.get('showEncounters', True))
        if tid in getattr(self, 'creatureIdSet', Set()):
            if tid in getattr(self, 'merchantIdSet', Set()):
                return bool(self.layerVisibility.get('showMerchants', True))
            return bool(self.layerVisibility.get('showCreatures', True))
        if tid in getattr(self, 'waypointIdSet', Set()):
            if tid in getattr(self, 'startLocationIdSet', Set()):
                return bool(self.layerVisibility.get('showStartLocation', True))
            return bool(self.layerVisibility.get('showWaypoints', True))
        return True
        
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
        lines = self._getAmbientLegendLines()
        if not lines:
            return

        y = self.height - 18
        glColor3f(1.0, 0.95, 0.7)
        for line in lines:
            self.output_text(14, y, line)
            y -= 14

    def _getAmbientLegendLines(self):
        highlighted = self.getThingHit(self.highlight) if self.highlight is not None else None
        selected = self.getThingHit(self.selected[0]) if self.selected else None
        target = selected if selected is not None else highlighted
        show = (self.mode == ToolPalette.AMBIENT_SOUND_TOOL or
                (highlighted is not None and hasattr(highlighted, 'getRadius')) or
                (selected is not None and hasattr(selected, 'getRadius')))
        if not show:
            return []

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
        return lines

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

    def _get2DAreaTileCoord(self, x, y):
        if not self.area:
            return (0, 0)
        tx = int(math.floor(float(x) / 10.0))
        ty = int(math.floor(float(y) / 10.0))
        tx = max(0, min(self.area.getWidth() - 1, tx))
        ty = max(0, min(self.area.getHeight() - 1, ty))
        return (tx, ty)

    def _get2DCellAreaTileCoord(self, cell_key):
        cx, cy = cell_key
        world_x = (float(cx) + 0.5) * self.map2DCellSize
        world_y = (float(cy) + 0.5) * self.map2DCellSize
        return self._get2DAreaTileCoord(world_x, world_y)

    def _ensure2DTilesetPlacementCache(self):
        if not self.area:
            self._map2DTilesetCacheKey = None
            self._map2DModelToTileId = {}
            self._map2DGroupByModel = {}
            return
        tileset = self.area.getTileSet()
        if tileset is None:
            self._map2DTilesetCacheKey = None
            self._map2DModelToTileId = {}
            self._map2DGroupByModel = {}
            return

        cache_key = id(tileset)
        if self._map2DTilesetCacheKey == cache_key:
            return

        model_to_tile_id, tile_id_to_model = Module._build_tileset_model_maps(tileset)
        group_by_model = {}
        try:
            group_count = int(tileset.getGroupCount())
        except Exception:
            group_count = 0
        for group_id in range(group_count):
            section = 'GROUP' + str(group_id)
            rows = tileset.getint(section, 'Rows', fallback=0)
            cols = tileset.getint(section, 'Columns', fallback=0)
            if rows <= 0 or cols <= 0:
                continue
            tile_ids = []
            for idx in range(rows * cols):
                tile_id = tileset.getint(section, 'Tile' + str(idx), fallback=-1)
                if tile_id < 0:
                    tile_ids = []
                    break
                tile_ids.append(int(tile_id))
            if not tile_ids:
                continue
            for tile_id in tile_ids:
                model_name = tile_id_to_model.get(tile_id)
                if model_name and model_name not in group_by_model:
                    group_by_model[model_name] = {
                        'rows': int(rows),
                        'cols': int(cols),
                        'tile_ids': list(tile_ids),
                    }

        self._map2DTilesetCacheKey = cache_key
        self._map2DModelToTileId = model_to_tile_id
        self._map2DGroupByModel = group_by_model

    def _resolve2DTileSelection(self):
        selection = self.map2DTileSelection
        if selection is None or not hasattr(selection, 'getResRef') or not hasattr(selection, 'getSectionName'):
            return None
        resref = str(selection.getResRef() or '').strip().lower()
        if not resref:
            return None

        self._ensure2DTilesetPlacementCache()
        if not self._map2DModelToTileId and not self._map2DGroupByModel:
            return None

        section = str(selection.getSectionName() or '')
        tile_id = self._map2DModelToTileId.get(resref)
        if section != 'Groups' and tile_id is not None:
            return {
                'kind': 'tile',
                'name': selection.getName(),
                'tile_id': int(tile_id),
                'orientation': int(self.map2DTileOrientation) % 4,
            }

        group = self._map2DGroupByModel.get(resref)
        if group is not None:
            return {
                'kind': 'group',
                'name': selection.getName(),
                'rows': int(group['rows']),
                'cols': int(group['cols']),
                'tile_ids': list(group['tile_ids']),
                'orientation': int(self.map2DTileOrientation) % 4,
            }

        if tile_id is not None:
            return {
                'kind': 'tile',
                'name': selection.getName(),
                'tile_id': int(tile_id),
                'orientation': int(self.map2DTileOrientation) % 4,
            }
        return None

    def _apply2DRealTilePaintAt(self, x, y):
        if not self.area:
            return False
        selection = self._resolve2DTileSelection()
        if selection is None:
            return False

        replacements = []
        if selection['kind'] == 'group':
            base_tx, base_ty = self._get2DAreaTileCoord(x, y)
            for dx, dy, tile_id, orient in Module._rotated_group_cells(
                    selection['rows'], selection['cols'], selection['tile_ids'], selection['orientation']):
                tx = base_tx + dx
                ty = base_ty + dy
                if tx < 0 or ty < 0 or tx >= self.area.getWidth() or ty >= self.area.getHeight():
                    continue
                replacements.append((ty * self.area.getWidth() + tx, int(tile_id), int(orient) % 4))
        else:
            changed_tiles = set()
            base = self._get2DCellKey(x, y)
            for key in self._iter2DBrushCells(base):
                changed_tiles.add(self._get2DCellAreaTileCoord(key))
            for tx, ty in sorted(changed_tiles):
                replacements.append((ty * self.area.getWidth() + tx,
                                     int(selection['tile_id']),
                                     int(selection['orientation']) % 4))

        if not replacements:
            return False

        frame = wx.GetTopLevelParent(self)
        if not frame or not hasattr(frame, 'applyAreaTileEdits'):
            return False
        changed = frame.applyAreaTileEdits(self.area, replacements, self)
        if changed:
            self.setStatus('2D tile paint: %s (%d°)' % (selection['name'], selection['orientation'] * 90))
        return bool(changed)

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
        if not evt.ControlDown() and not evt.AltDown() and not evt.ShiftDown():
            if self._apply2DRealTilePaintAt(x, y):
                return
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
        self._notify2DDraftChanged()

    def _cycle2DAssetAt(self, x, y):
        key = self._get2DCellKey(x, y)
        cell = self._ensure2DCell(key)
        cell['asset'] = (int(cell.get('asset', 0)) + 1) % 5
        self.setStatus('2D asset @%d,%d: %s' % (key[0], key[1], self._get2DAssetName(cell['asset'])))
        self._save2DDraftForCurrentArea()
        self._notify2DDraftChanged()

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

    def _notify2DDraftChanged(self):
        area = self.area
        if not area:
            return
        frame = wx.GetTopLevelParent(self)
        if not frame or not hasattr(frame, 'syncArea2DDraft'):
            return
        try:
            frame.syncArea2DDraft(area, self)
        except Exception:
            logger.debug('failed to sync 2D draft between map views', exc_info=True)

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
            self._notify2DDraftChanged()
            self.setStatus('2D draft imported: %s' % os.path.basename(path))
            return True
        except Exception:
            logger.debug('failed to import 2D draft', exc_info=True)
            self.setStatus('2D import failed')
            return False

    def _draw2DGridAndPaintOverlay(self):
        if not self.area:
            return
        show_grid = bool(self.layerVisibility.get('showGrid', self.map2DShowGrid))
        if not self.map2DCells and not show_grid:
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

        if show_grid:
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
        lines = self._get2DLegendLines()
        if not lines:
            return

        y = self.height - 76
        glColor3f(0.82, 0.98, 0.85)
        for line in lines:
            self.output_text(14, y, line)
            y -= 14

    def _get2DLegendLines(self):
        show = (self.mode == ToolPalette.MAP2D_DRAW_TOOL)
        if not show:
            return []
        lines = [
            '2D Draw: LMB stamp selected tile | Ctrl+LMB raise | Alt+LMB lower | Shift+LMB toggle block',
            'RMB cycle asset at cell | Wheel +/- brush radius | C clear | X export | I import',
            'T terrain=%s  U asset=%s  R rot=%d°  G grid=%s  O occlusion=%s  Radius=%d'
            % (self._get2DTerrainName(self.map2DTerrainBrush),
               self._get2DAssetName(self.map2DAssetBrush),
               self.map2DTileOrientation * 90,
               'on' if self.layerVisibility.get('showGrid', self.map2DShowGrid) else 'off',
               'on' if self.map2DShowOcclusion else 'off',
               self.map2DBrushRadius)
        ]
        selection = self._resolve2DTileSelection()
        if selection is not None:
            lines.append('Selected tile: %s [%s]' % (selection['name'], selection['kind']))
        return lines

    def _queueCoreTextOverlays(self):
        if self.showFPS:
            self.output_text(15, 15, 'fps: %.2f' % self.fps)

        ambient_lines = self._getAmbientLegendLines()
        y = self.height - 18
        for line in ambient_lines:
            self.output_text(14, y, line)
            y -= 14

        legend_lines = self._get2DLegendLines()
        y = self.height - 76
        for line in legend_lines:
            self.output_text(14, y, line)
            y -= 14

        if self.highlight is not None:
            thing = self.getThingHit(self.highlight)
            if thing is not None:
                self.output_text(14, 52, 'Highlight: %s' % thing.getName())

        if self.selected:
            thing = self.getThingHit(self.selected[0])
            if thing is not None:
                self.output_text(14, 36, 'Selected: %s' % thing.getName())

    def _canUseGenericThingMarker(self, thing):
        return bool(thing and hasattr(thing, 'getX') and hasattr(thing, 'getY') and
                    not self._isPolygonRegionThing(thing) and not hasattr(thing, 'getRadius'))

    def _getGenericThingMarkerColour(self, thing, name):
        if name in self.selected:
            return (0.2, 0.95, 0.2, 0.95)
        if self.highlight == name:
            return (0.1, 0.1, 1.0, 0.95)

        tid = thing.getNevereditId()
        if tid in getattr(self, 'creatureIdSet', Set()):
            return (0.95, 0.35, 0.35, 0.9)
        if tid in getattr(self, 'itemIdSet', Set()):
            return (0.42, 0.85, 0.95, 0.9)
        if tid in getattr(self, 'placeableIdSet', Set()):
            return (0.95, 0.8, 0.2, 0.9)
        if tid in getattr(self, 'doorIdSet', Set()):
            return (0.9, 0.55, 0.2, 0.9)
        return (0.85, 0.85, 0.85, 0.9)

    def _drawGenericThingMarker(self, thing, name):
        size = 0.35
        self.solidColourOn()
        try:
            self.glColorf(self._getGenericThingMarkerColour(thing, name))
            glLineWidth(2.0 if (name in self.selected or self.highlight == name) else 1.0)
            glBegin(GL_LINES)
            glVertex3f(-size, 0.0, 0.05)
            glVertex3f(size, 0.0, 0.05)
            glVertex3f(0.0, -size, 0.05)
            glVertex3f(0.0, size, 0.05)
            glEnd()
            glLineWidth(1.0)
            if name in self.selected or self.highlight == name:
                self._drawSoundCircle(size * 1.8, filled=False, segments=20)
        finally:
            self.solidColourOff()

    def drawThing(self,thing,name):
        model = thing.getModel()
        if not model:
            if self._isPolygonRegionThing(thing):
                self._drawTriggerThing(thing, name)
            elif hasattr(thing, 'getRadius'):
                self._drawSoundThing(thing, name)
            elif self._canUseGenericThingMarker(thing):
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
                    self._drawGenericThingMarker(thing, name)
                finally:
                    glPopMatrix()
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

    def _drawTriggerThing(self, thing, name):
        points = self._getTriggerLocalPoints(thing)
        if len(points) < 3:
            return
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
            glRotatef(thing.getBearing() * 180 / math.pi, 0, 0, 1)

            self.solidColourOn()
            try:
                if name in self.selected:
                    self.glColorf((0.15, 0.9, 0.15, 0.95))
                elif self.highlight == name:
                    self.glColorf((0.1, 0.1, 1.0, 0.9))
                else:
                    self.glColorf((0.95, 0.55, 0.1, 0.85))

                glLineWidth(2.0 if (name in self.selected or self.highlight == name) else 1.0)
                glBegin(GL_LINE_LOOP)
                for point_x, point_y, point_z in points:
                    glVertex3f(point_x, point_y, point_z + 0.05)
                glEnd()
                glLineWidth(1.0)

                self.glColorf((1.0, 0.9, 0.2, 1.0))
                glBegin(GL_LINES)
                glVertex3f(-0.3, 0.0, 0.06)
                glVertex3f(0.3, 0.0, 0.06)
                glVertex3f(0.0, -0.3, 0.06)
                glVertex3f(0.0, 0.3, 0.06)
                glEnd()
            finally:
                self.solidColourOff()
        finally:
            glPopMatrix()

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

    def _makeCoreBaseMatrix(self, tx, ty, tz, bearing_degrees=0.0):
        base = Numeric.identity(4, 'f')
        base[0, 3] = float(tx)
        base[1, 3] = float(ty)
        base[2, 3] = float(tz)
        angle = math.radians(float(bearing_degrees))
        c = math.cos(angle)
        s = math.sin(angle)
        rot = Numeric.identity(4, 'f')
        rot[0, 0] = c
        rot[0, 1] = -s
        rot[1, 0] = s
        rot[1, 1] = c
        return Numeric.dot(base, rot)

    def _drawTileCore(self, t, i, model_override=None):
        model = model_override if model_override is not None else t.getModel()
        if not model:
            return False
        root = model.getRootNode()
        if root is None:
            return False
        x = i % self.area.getWidth()
        y = i // self.area.getWidth()
        tx = x * 10.0 + 5.0
        ty = y * 10.0 + 5.0
        tz = t.getTileHeight() * 5.0
        base = self._makeCoreBaseMatrix(tx, ty, tz, float(t.getBearing()))
        return self.drawModelCorePath(root, base_matrix=base)

    def _drawThingCore(self, thing, model_override=None):
        model = model_override if model_override is not None else thing.getModel()
        if not model:
            return False
        root = model.getRootNode()
        if root is None:
            return False
        bearing_degrees = float(thing.getBearing()) * 180.0 / math.pi
        base = self._makeCoreBaseMatrix(thing.getX(), thing.getY(), thing.getZ(), bearing_degrees)
        return self.drawModelCorePath(root, base_matrix=base)

    def _distanceToCamera(self, x, y, z):
        dx = float(x) - float(self.viewX)
        dy = float(y) - float(self.viewY)
        dz = float(z) - float(self.viewZ)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _findFirstRenderableNodeForRoot(self, root):
        if root is None:
            return None
        stack = [root]
        while stack:
            node = stack.pop()
            if self.isRenderableMeshNode(node):
                return node
            children = getattr(node, 'children', None)
            if children:
                stack.extend(children)
        return None

    def _coreSortKeyForRoot(self, root):
        node = self._findFirstRenderableNodeForRoot(root)
        if node is None:
            return (0, 0, 0, 0, 0, 0, id(root))
        tex0 = int(self._getNodeGLTextureName(node, 0) or 0)
        tex1 = int(self._getNodeGLTextureName(node, 1) or 0)
        diffuse = getattr(node, 'diffuseColour', (1.0, 1.0, 1.0, 1.0))
        r = int(max(0, min(255, int(float(diffuse[0]) * 255.0))))
        g = int(max(0, min(255, int(float(diffuse[1]) * 255.0))))
        b = int(max(0, min(255, int(float(diffuse[2]) * 255.0))))
        return (0, tex0, tex1, r, g, b, id(root))

    def _isThingInstancingCandidate(self, thing, thing_index, snapshot=None):
        if thing is None and snapshot is None:
            return False
        if thing_index in self.selected or thing_index == self.highlight:
            return False
        tid = None
        if snapshot is not None:
            tid = snapshot.entity_id
        elif hasattr(thing, 'getNevereditId'):
            tid = thing.getNevereditId()
        if tid in getattr(self, 'placeableIdSet', Set()):
            return True
        model_name = ''
        if snapshot is not None:
            model_name = str(getattr(snapshot, 'modelName', '') or '').lower()
        else:
            model_name = str(getattr(thing, 'modelName', '') or '').lower()
        return ('tree' in model_name or 'grass' in model_name or 'bush' in model_name)

    def _resolveLodModelForName(self, model_name):
        if not model_name:
            return None
        base_name = str(model_name).strip().lower()
        if base_name.endswith('.mdl'):
            base_name = base_name[:-4]
        if base_name in self._coreLodModelCache:
            return self._coreLodModelCache[base_name]

        rm = neverglobals.getResourceManager()
        resolved = None
        for suffix in self.coreLodModelSuffixes:
            candidate = base_name + suffix
            resolved = rm.getResourceByName(candidate + '.mdl')
            if resolved is None:
                resolved = rm.getResourceByName(candidate)
            if resolved is not None:
                break

        self._coreLodModelCache[base_name] = resolved
        if resolved is not None:
            prep_key = id(resolved)
            if prep_key not in self._coreLodPrepared:
                self.preprocessNodes(resolved, 'lod-' + base_name, bbox=True)
                self._coreLodPrepared.add(prep_key)
        return resolved

    def _getModelRootRadius(self, model):
        if model is None:
            return None
        try:
            root = model.getRootNode()
        except Exception:
            return None
        if root is None:
            return None
        sphere = getattr(root, 'boundingSphere', None)
        if not sphere or len(sphere) < 2:
            return None
        try:
            return float(sphere[1])
        except Exception:
            return None

    def _computeLodDistanceForModel(self, model, base_distance):
        radius = self._getModelRootRadius(model)
        if radius is None:
            return float(base_distance)
        scale = max(0.55, min(1.75, radius / 8.0))
        return float(base_distance) * scale

    def _isDecorativeFarCullCandidate(self, thing):
        model_name = str(getattr(thing, 'modelName', '') or '').lower()
        return ('grass' in model_name or 'bush' in model_name or 'fern' in model_name or
                'weed' in model_name or 'reed' in model_name or 'plant' in model_name)

    def _selectLodModelForTile(self, tile, model, x, y, z):
        if model is None:
            return None
        lod_distance = self._computeLodDistanceForModel(model, self.coreTileLodDistance)
        if self._distanceToCamera(x, y, z) <= lod_distance:
            return model
        lod = self._resolveLodModelForName(getattr(tile, 'modelName', ''))
        return lod if lod is not None else model

    def _selectLodModelForThing(self, thing, model):
        if model is None:
            return None
        distance = self._distanceToCamera(thing.getX(), thing.getY(), thing.getZ())
        base_distance = self.coreThingLodDistance
        if self._isThingInstancingCandidate(thing, None):
            base_distance = self.coreSmallThingLodDistance
        lod_distance = self._computeLodDistanceForModel(model, base_distance)
        if distance <= lod_distance:
            return model
        lod = self._resolveLodModelForName(getattr(thing, 'modelName', ''))
        if lod is None and self._isDecorativeFarCullCandidate(thing) and distance > self.coreDecorCullDistance:
            return None
        return lod if lod is not None else model

    def _queueCoreTileEntry(self, queue, tile_entry):
        if tile_entry is None:
            return
        model = tile_entry.model
        if not model:
            return
        model = self._selectLodModelForTile(tile_entry, model, tile_entry.x, tile_entry.y, tile_entry.z)
        root = model.getRootNode() if model is not None else None
        if root is None:
            return
        base = self._makeCoreBaseMatrix(tile_entry.x, tile_entry.y, tile_entry.z, tile_entry.bearing_degrees)
        sort_key = self._coreSortKeyForRoot(root)
        instance_key = ('tile', sort_key)
        queue.append({
            'root': root,
            'base': base,
            'sort_key': sort_key,
            'instance_key': instance_key,
        })

    def _queueCoreThingEntry(self, queue, thing_entry):
        if thing_entry is None or not self._isThingVisibleForLayers(thing_entry):
            return
        model = thing_entry.model
        if not model:
            return
        model = self._selectLodModelForThing(thing_entry, model)
        root = model.getRootNode() if model is not None else None
        if root is None:
            return
        base = self._makeCoreBaseMatrix(thing_entry.getX(), thing_entry.getY(), thing_entry.getZ(),
                                        thing_entry.bearing_degrees)
        sort_key = self._coreSortKeyForRoot(root)
        instance_key = None
        if self._isThingInstancingCandidate(thing_entry, thing_entry.thing_index, snapshot=thing_entry):
            instance_key = ('thing', sort_key)
        queue.append({
            'root': root,
            'base': base,
            'sort_key': sort_key,
            'instance_key': instance_key,
        })

    def _collectCoreRenderQueueFromTree(self, node, queue, useFrustumCull=True):
        if node is None:
            return
        sphere = getattr(node, 'boundingSphere', None)
        if useFrustumCull and sphere is not None:
            if not self.sphereInFrustumWorld(sphere[0], sphere[1]):
                return
        if len(node.children) > 0:
            for halves in node.children:
                for c in halves:
                    self._collectCoreRenderQueueFromTree(c, queue, useFrustumCull)
            return

        for _tile, tile_index in node.contents.get('tiles', []):
            self._queueCoreTileEntry(queue, self._render_world_cache.get_tile(tile_index))
        for _thing, thing_index in node.contents.get('things', []):
            self._queueCoreThingEntry(queue, self._render_world_cache.get_thing(thing_index))

    def _drawCoreRenderQueue(self, queue):
        if not queue:
            return False
        if self.coreBatchingEnabled:
            queue.sort(key=lambda item: item['sort_key'])

        drew = False
        i = 0
        while i < len(queue):
            entry = queue[i]
            instance_key = entry.get('instance_key')
            if instance_key is None:
                drew = self.drawModelCorePath(entry['root'], base_matrix=entry['base']) or drew
                i += 1
                continue

            j = i + 1
            while j < len(queue) and queue[j].get('instance_key') == instance_key:
                j += 1
            run = queue[i:j]

            if len(run) >= max(2, int(self.coreInstancingMinBatch)):
                instance_matrices = [item['base'] for item in run]
                if self.drawModelCoreInstancedPath(entry['root'], instance_matrices):
                    drew = True
                    i = j
                    continue

            for item in run:
                drew = self.drawModelCorePath(item['root'], base_matrix=item['base']) or drew
            i = j
        return drew

    def _getAreaAmbientRgb(self):
        """Extract MoonAmbientColor from the area as (r, g, b) floats in [0,1]."""
        try:
            v = self.area.getPropertyValue('MoonAmbientColor')
            return ((v & 0xff) / 255.0, ((v >> 8) & 0xff) / 255.0, ((v >> 16) & 0xff) / 255.0)
        except Exception:
            return (0.58, 0.58, 0.58)

    def _getAreaDiffuseRgb(self):
        """Extract SunDiffuseColor from the area as (r, g, b) floats in [0,1]."""
        try:
            v = self.area.getPropertyValue('SunDiffuseColor')
            return ((v & 0xff) / 255.0, ((v >> 8) & 0xff) / 255.0, ((v >> 16) & 0xff) / 255.0)
        except Exception:
            return (0.72, 0.72, 0.72)

    def _getAreaFogRgb(self):
        """Extract the active fog color from the area as (r, g, b) floats in [0,1]."""
        try:
            fog_key = 'MoonFogColor' if self.area.getPropertyValue('IsNight') else 'SunFogColor'
            v = self.area.getPropertyValue(fog_key)
            return ((v & 0xff) / 255.0, ((v >> 8) & 0xff) / 255.0, ((v >> 16) & 0xff) / 255.0)
        except Exception:
            ambient = self._getAreaAmbientRgb()
            return tuple(min(1.0, c * 0.9 + 0.1) for c in ambient)

    def _getCoreFogDistances(self):
        near_distance = min(self.coreFogNearDistance, self.coreDecorCullDistance * 0.8)
        far_distance = max(self.coreFogFarDistance, near_distance + 40.0)
        return near_distance, far_distance

    def _drawTreeCore(self):
        if not self.quadTreeRoot:
            return False
        self._ensureRenderWorldCache()
        if self.area:
            self.setCoreFrameLightUniforms(self._getAreaAmbientRgb(), self._getAreaDiffuseRgb())
            fog_near, fog_far = self._getCoreFogDistances()
            self.setCoreFrameFogUniforms(self.coreFogEnabled, self._getAreaFogRgb(), fog_near, fog_far,
                                         self.coreDistanceDesatStrength)
            self.setCoreFrameToonUniforms(self.toonShading, self.coreToonBands, self.coreToonRimStrength)
        else:
            self.setCoreFrameFogUniforms(False)
            self.setCoreFrameToonUniforms(False)
        _proj, _view, view_proj = self._buildCameraMatrices()
        self.updateFrustumFromViewProjection(view_proj)
        useFrustumCull = self.sphereInFrustumWorld(self.quadTreeRoot.boundingSphere[0],
                                                   self.quadTreeRoot.boundingSphere[1])
        queue = []
        self._collectCoreRenderQueueFromTree(self.quadTreeRoot, queue, useFrustumCull)
        return self._drawCoreRenderQueue(queue)

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
            if self._isThingVisibleForLayers(t[0]):
                self.drawThing(t[0],t[1])

    def _drawWaypointPaths(self):
        if not self.layerVisibility.get('showWaypoints', True):
            return
        if not self.waypoints:
            return

        by_tag = {}
        for w in self.waypoints:
            tag = w['Tag']
            if tag:
                by_tag[str(tag)] = w

        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        self.glColorf((0.95, 0.6, 0.1, 0.85))
        glLineWidth(2.0)
        glBegin(GL_LINES)
        for src in self.waypoints:
            linked = src['LinkedTo']
            if not linked:
                continue
            dst = by_tag.get(str(linked))
            if dst is None:
                continue
            glVertex3f(float(src.getX()), float(src.getY()), float(src.getZ()) + 0.15)
            glVertex3f(float(dst.getX()), float(dst.getY()), float(dst.getZ()) + 0.15)
        glEnd()
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)

    def _drawWaypointPathsCore(self):
        if not self.layerVisibility.get('showWaypoints', True):
            return
        if not self.waypoints:
            return

        by_tag = {}
        for w in self.waypoints:
            tag = w['Tag']
            if tag:
                by_tag[str(tag)] = w

        segments = []
        for src in self.waypoints:
            linked = src['LinkedTo']
            if not linked:
                continue
            dst = by_tag.get(str(linked))
            if dst is None:
                continue
            segments.append(((float(src.getX()), float(src.getY()), float(src.getZ()) + 0.15),
                             (float(dst.getX()), float(dst.getY()), float(dst.getZ()) + 0.15)))

        if segments:
            self.drawCoreLineSegments(segments, color=(0.95, 0.6, 0.1, 0.85), line_width=2.0)

    def _transformPointWithMatrix(self, matrix, point3):
        v = Numeric.array([float(point3[0]), float(point3[1]), float(point3[2]), 1.0], 'f')
        out = Numeric.dot(matrix, v)
        w = float(out[3])
        if abs(w) > 1.0e-8:
            out = out / w
        return (float(out[0]), float(out[1]), float(out[2]))

    def _appendTransformedBoxSegments(self, out_segments, box, matrix):
        if box is None:
            return
        mins = box[0]
        maxs = box[1]
        corners = [
            (mins[0], mins[1], mins[2]),
            (maxs[0], mins[1], mins[2]),
            (maxs[0], maxs[1], mins[2]),
            (mins[0], maxs[1], mins[2]),
            (mins[0], mins[1], maxs[2]),
            (maxs[0], mins[1], maxs[2]),
            (maxs[0], maxs[1], maxs[2]),
            (mins[0], maxs[1], maxs[2]),
        ]
        transformed = [self._transformPointWithMatrix(matrix, c) for c in corners]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        for i0, i1 in edges:
            out_segments.append((transformed[i0], transformed[i1]))

    def _appendCoreCrossMarker(self, out_segments, x, y, z, size=0.45):
        out_segments.append(((x - size, y, z), (x + size, y, z)))
        out_segments.append(((x, y - size, z), (x, y + size, z)))

    def _appendThingSelectionSegmentsCore(self, out_segments, thing):
        if thing is None:
            return
        model = thing.getModel() if hasattr(thing, 'getModel') else None
        if model is not None:
            root = model.getRootNode()
            if root is not None:
                box = self._getHighlightBoundingBox(model, root)
                if box is not None:
                    bearing_degrees = float(thing.getBearing()) * 180.0 / math.pi
                    base = self._makeCoreBaseMatrix(thing.getX(), thing.getY(), thing.getZ(), bearing_degrees)
                    self._appendTransformedBoxSegments(out_segments, box, base)
                    return

        if self._isPolygonRegionThing(thing):
            points = self._getTriggerWorldPoints(thing)
            if len(points) >= 2:
                for i in range(len(points)):
                    p0 = points[i]
                    p1 = points[(i + 1) % len(points)]
                    out_segments.append(((float(p0[0]), float(p0[1]), float(p0[2]) + 0.08),
                                         (float(p1[0]), float(p1[1]), float(p1[2]) + 0.08)))
                return

        self._appendCoreCrossMarker(out_segments,
                                    float(thing.getX()),
                                    float(thing.getY()),
                                    float(thing.getZ()) + 0.12,
                                    size=0.45)

    def _drawCoreSelectionOverlays(self):
        selected_segments = []
        highlight_segments = []

        selected_ids = [sid for sid in self.selected if sid is not None]
        selected_id_set = Set(selected_ids)

        for sid in selected_ids:
            thing = self.getThingHit(sid)
            if thing is None or not self._isThingVisibleForLayers(thing):
                continue
            self._appendThingSelectionSegmentsCore(selected_segments, thing)

        if self.highlight is not None and self.highlight not in selected_id_set:
            thing = self.getThingHit(self.highlight)
            if thing is not None and self._isThingVisibleForLayers(thing):
                self._appendThingSelectionSegmentsCore(highlight_segments, thing)

        if highlight_segments:
            self.drawCoreLineSegments(highlight_segments,
                                      color=(0.12, 0.35, 1.0, 0.95),
                                      line_width=2.0)
        if selected_segments:
            self.drawCoreLineSegments(selected_segments,
                                      color=(0.18, 0.95, 0.2, 0.98),
                                      line_width=2.4)
                
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
        if getattr(self, '_core_profile_stub_mode', False):
            if self.toPreprocess:
                self.preprocessNodes(self.toPreprocess.getModel(),'tag',bbox=True)
                self.preprocessedModels.add(self.toPreprocess.modelName)
                self.toPreprocess = None
            if not self.preprocessed:
                return
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            drew = False
            if self.area:
                self.beginCoreDrawFrame()
                drew = self._drawTreeCore()
                if self.beingPainted:
                    drew = self._drawThingCore(self.beingPainted) or drew
                self._drawWaypointPathsCore()
                self._drawCoreSelectionOverlays()
            if not drew and not getattr(self, '_logged_core_stub_map_warning', False):
                logger.warning('Core profile mode: map geometry path is active but no drawable core-ready meshes were found this frame')
                self._logged_core_stub_map_warning = True
            self._updateAmbientPreview()
            self._queueCoreTextOverlays()
            self.SwapBuffers()
            return
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

            if hasattr(self, 'shader_manager'):
                self.shader_manager.set_scene_lighting(
                    ambient=[ambient[0], ambient[1], ambient[2], 1.0],
                    diffuse=[diffuse[0], diffuse[1], diffuse[2], 1.0],
                    specular=[1.0, 1.0, 1.0, 1.0],
                    position=[self.viewX, self.viewY, self.viewZ, 1.0],
                )

            w = self.area.getWidth()*10.0
            h = self.area.getHeight()*10.0

            name = 0
            toon_active = False
            if self.toonShading:
                toon_active = self._toon_use()
            shader_render_state = False
            
            # Apply shader if available
            if hasattr(self, 'shader_manager') and self._shaders_compiled:
                shader_render_state = self.shader_manager.apply_render_state()
                self.shader_manager.sync_matrix_state_from_gl()
                self.shader_manager.use_current_shader()
            
            self.drawTree()
            
            # Disable shader after drawing
            if hasattr(self, 'shader_manager') and self._shaders_compiled:
                glUseProgram(0)
                self.shader_manager.restore_render_state(shader_render_state)
            
            if toon_active:
                self._toon_unuse()
            self._drawWaypointPaths()
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


class TopDownMapWindow(MapWindow):
    """A dedicated top-down map page that keeps camera pitch locked.

    This reuses the full MapWindow pipeline while presenting a stable 2D-style
    overhead view for planning and layout work.
    """

    def __init__(self, parent):
        MapWindow.__init__(self, parent)
        self._topDownLocked = True
        self.mode = ToolPalette.MAP2D_DRAW_TOOL
        self.map2DShowGrid = True
        self._applyTopDownCamera()

    def OnMouseDown(self, evt):
        self.lastX = evt.GetX()
        self.lastY = self.height - evt.GetY()
        MapWindow.OnMouseDown(self, evt)

    def _applyTopDownCamera(self):
        # Keep camera looking straight down while preserving zoom/pan behavior.
        self.viewAngleSky = 89.999
        self.viewAngleFloor = 90.0
        self.lookingAtZ = 0.0
        self.recomputeCamera()

    def setArea(self, area):
        MapWindow.setArea(self, area)
        self._applyTopDownCamera()

    def toolSelected(self, evt):
        MapWindow.toolSelected(self, evt)
        self._applyTopDownCamera()

    def adjustViewAngle(self, floorAdjust, skyAdjust):
        # Lock orbiting for this view; keep pan/zoom active.
        if getattr(self, '_topDownLocked', False):
            self._applyTopDownCamera()
            self.requestRedraw()
            return
        MapWindow.adjustViewAngle(self, floorAdjust, skyAdjust)

    def OnMouseMotion(self, evt):
        if not self.area or not self.preprocessed or self.preprocessing:
            return

        currentX = evt.GetX()
        currentY = self.height - evt.GetY()

        # In top-down mode, right-drag and middle-drag pan instead of orbiting.
        if evt.Dragging() and not self.beingDragged:
            dx = float(currentX - self.lastX)
            dy = float(currentY - self.lastY)
            if evt.RightIsDown() or evt.MiddleIsDown() or (evt.LeftIsDown() and evt.AltDown()):
                self.adjustPos(dy * 0.08, -dx * 0.08)
                self.lastX = currentX
                self.lastY = currentY
                return

        MapWindow.OnMouseMotion(self, evt)

    def OnMouseWheel(self, evt):
        # Default wheel behavior in the 2D tab is zoom. Hold Ctrl/Cmd or Alt
        # to adjust the 2D brush radius instead.
        if evt.ControlDown() or evt.CmdDown() or evt.AltDown():
            MapWindow.OnMouseWheel(self, evt)
            return
        GLWindow.OnMouseWheel(self, evt)
    

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: ' + sys.argv[0] + ' <modfile>')
        sys.exit(1)

    #w = MapWindow.get_standalone()
    #w.makeQuadTreeHelper(QuadTreeNode(),0,0,4,4)
    MapWindow.get_standalone(sys.argv[1])
    MapWindow.start_standalone()
    
