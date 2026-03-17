import logging
logger = logging.getLogger('neveredit.ui')

import wx
from wx import glcanvas
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL import error as gl_error
import math,sys

# Some systems ship PyOpenGL but not a working GLUT runtime.
# Keep startup alive and defer failures to GLUT-dependent paths.
if 'glutInit' in globals() and bool(glutInit):
    try:
        glutInit(sys.argv)  # must be initialized once and only once
    except Exception:
        pass

def _has_glut_text_support():
    return ('glutBitmapCharacter' in globals() and bool(glutBitmapCharacter) and
            'glutBitmapWidth' in globals() and bool(glutBitmapWidth))

Set = set

from neveredit.util import Utils
from neveredit.util import Preferences
from neveredit.util import neverglobals

Numeric = Utils.getNumPy()
LinearAlgebra = Utils.getLinAlg()
import time

class GLWindow(glcanvas.GLCanvas):
    def __init__(self,parent):
        glcanvas.GLCanvas.__init__(self, parent, -1)
        self._gl_context = None
        try:
            self._gl_context = glcanvas.GLContext(self)
        except Exception:
            self._gl_context = None
        self.init = False
        self.width = 0
        self.height = 0

        self.zoom = 50.0
        self.minZoom = 5.0
        self.maxZoom = 400.0
        self.lookingAtX = 0
        self.lookingAtY = 0
        self.lookingAtZ = 0
        self.viewAngleSky = 50.0
        self.viewAngleFloor = 90.0
        self.angleSpeed = 3.0

        self.viewX = 0
        self.viewY = 0
        self.viewZ = 0
        
        self.point = Numeric.zeros((1,4),typecode=Numeric.Float)
        
        self.clearCache()

        self.frustum = []
        self.viewMatrixInv = Numeric.identity(4,Numeric.Float)
        self.modelMatrix = None
        self.currentModelView = None

        self.redrawRequested = False
        self.preprocessed = False
        self.preprocessing = False
        self._lastPaintError = None
        self._loggedImmediateFallback = False
        self._skinCurrentMatrices = None
        self._skinRestMatrices = None
        self._skinRestInverseMatrices = None
        self._skinDeformedVertexCache = None
        self._skinDeformedNormalCache = None
        self._activePLTTintContext = None
        self._activeAnimationNodes = None
        self._superModelCache = {}
        self._loggedAnimationTrackBindings = set()
        self.animationsEnabled = True
        self.animationMode = 'idle'
        self.animationModes = ('idle', 'walk')
        self.animationSpeedByMode = {'idle': 1.0, 'walk': 1.8}
        self.animationTrackByMode = {
            'idle': ('pause1', 'pause', 'idle', 'ready1', 'default'),
            'walk': ('walk', 'walk01', 'walk1', 'run', 'run1'),
        }
        self._animationStartTime = time.time()
        self._animationTimeSeconds = 0.0
        self._destroying = False
        self._animationTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnAnimationTimer, self._animationTimer)
        self._animationTimer.Start(33)
        
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)

    def _stopAnimationTimer(self):
        timer = getattr(self, '_animationTimer', None)
        if timer is None:
            return
        try:
            if timer.IsRunning():
                timer.Stop()
        except Exception:
            pass
        try:
            self.Unbind(wx.EVT_TIMER, handler=self.OnAnimationTimer, source=timer)
        except Exception:
            pass
        self._animationTimer = None

    def Destroy(self):
        # Avoid use-after-free crashes from late timer callbacks while wx tears
        # down a GLCanvas.
        self._destroying = True
        self.animationsEnabled = False
        self._stopAnimationTimer()
        return glcanvas.GLCanvas.Destroy(self)

    def OnEraseBackground(self, event):
        pass

    def OnAnimationTimer(self, event):
        if self._destroying:
            return
        if not self.animationsEnabled:
            return
        if self.preprocessing:
            return
        self.requestRedraw()

    def getAnimationMode(self):
        return self.animationMode

    def setAnimationMode(self, mode):
        if mode not in self.animationModes:
            return self.animationMode
        self.animationMode = mode
        self._animationStartTime = time.time()
        self._loggedAnimationTrackBindings.clear()
        self.requestRedraw()
        return self.animationMode

    def _logAnimationTrackBinding(self, model, source, track_name, node_count):
        model_name = '<unknown>'
        if model is not None and hasattr(model, 'getName'):
            try:
                model_name = str(model.getName())
            except Exception:
                model_name = '<unknown>'

        key = (self.animationMode, model_name, source, str(track_name or '<none>'))
        if key in self._loggedAnimationTrackBindings:
            return
        self._loggedAnimationTrackBindings.add(key)

        logger.debug('animation bind mode=%s model=%s source=%s track=%s nodes=%s',
                     self.animationMode,
                     model_name,
                     source,
                     str(track_name or '<none>'),
                     str(node_count))

    def cycleAnimationMode(self):
        current = self.animationMode
        try:
            index = self.animationModes.index(current)
        except ValueError:
            index = -1
        next_mode = self.animationModes[(index + 1) % len(self.animationModes)]
        return self.setAnimationMode(next_mode)

    def makeCurrent(self):
        '''Activate GL context on wx versions that require an explicit context.'''
        if self._gl_context is not None:
            glcanvas.GLCanvas.SetCurrent(self, self._gl_context)
        else:
            glcanvas.GLCanvas.SetCurrent(self)

    def OnSize(self, event):
        size = self.GetClientSize()
        try:
            self.makeCurrent()
            self.ReSizeGLScene(size.width,size.height)
        except Exception:
            # Early resize events can happen before a GL context is fully ready.
            pass
        event.Skip()

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        #dc.ResetBoundingBox()
        try:
            self.makeCurrent()
        except Exception:
            return
        if not self.init:
            self.InitGL(self.GetClientSize().width,self.GetClientSize().height)
            self.init = True
        try:
            self.DrawGLScene()
        except (gl_error.Error, TypeError) as exc:
            # Some modern drivers expose a profile that lacks fixed-function
            # entry points; avoid hard-failing the paint loop.
            message = str(exc)
            if message != self._lastPaintError:
                logger.warning('GL paint skipped due to context/profile issue: %s', exc)
                self._lastPaintError = message

    def OnMouseDown(self, evt):
        pass #self.CaptureMouse()
    
    def OnMouseUp(self, evt):
        pass #self.ReleaseMouse()

    def OnKeyUp(self,evt):
        pass

    def OnKeyDown(self,evt):
        if self.preprocessing:
            return
        unicode_key = evt.GetUnicodeKey()
        if unicode_key is not None and unicode_key >= 0:
            key_char = chr(unicode_key)
        else:
            key_char = ''
        if evt.GetKeyCode() == wx.WXK_UP:
            self.adjustZoom(2.0)
        if evt.GetKeyCode() == wx.WXK_DOWN:
            self.adjustZoom(-2.0)
        if key_char == Preferences.getPreferences()['GLW_UP']:
            self.adjustPos(1,0)
        if key_char == Preferences.getPreferences()['GLW_DOWN']:
            self.adjustPos(-1,0)
        if key_char == Preferences.getPreferences()['GLW_RIGHT']:
            self.adjustPos(0,-1)
        if key_char == Preferences.getPreferences()['GLW_LEFT']:
            self.adjustPos(0,1)
        if evt.GetKeyCode() == wx.WXK_LEFT:
            self.adjustViewAngle(self.angleSpeed,0.0)
        if evt.GetKeyCode() == wx.WXK_RIGHT:
            self.adjustViewAngle(-self.angleSpeed,0.0)
        if evt.GetKeyCode() in (312,368): #pgdown
            self.adjustViewAngle(0.0,self.angleSpeed)
        if evt.GetKeyCode() in (313,369): #pgup
            self.adjustViewAngle(0.0,-self.angleSpeed)
        
    def OnMouseWheel(self,evt):
        if self.preprocessing:
            return
        wheel_delta = float(evt.GetWheelDelta() or 120.0)
        notches = float(evt.GetWheelRotation()) / wheel_delta
        # Use notch-based zoom so modern wheel delta values don't cause
        # huge jumps (e.g., +/-120 per single notch).
        self.adjustZoom(notches * 2.0)

    def OnMouseMotion(self,evt):
        pass
    
    def adjustViewAngle(self,floorAdjust, skyAdjust):
        self.viewAngleFloor += floorAdjust
        if self.viewAngleFloor > 360:
            self.viewAngleFloor -= 360
        elif self.viewAngleFloor < 0:
            self.viewAngleFloor += 360
        self.viewAngleSky += skyAdjust
        if self.viewAngleSky > 90:
            self.viewAngleSky = 89.9999
        elif self.viewAngleSky < 10:
            self.viewAngleSky = 10
        #self.SetupProjection()
        self.recomputeCamera()
        #self.Refresh(False)
        self.requestRedraw()

    def getBaseWidth(self):
        return 5.0

    def getBaseHeight(self):
        return 5.0
    
    def adjustPos(self,forwardBackward,sideways):
        w = self.getBaseWidth()
        h = self.getBaseHeight()
        dx = forwardBackward * math.cos((self.viewAngleFloor)*math.pi/180.0)
        dy = forwardBackward * math.sin((self.viewAngleFloor)*math.pi/180.0)
        dx += sideways * math.cos((self.viewAngleFloor+90.0)*math.pi/180.0)
        dy += sideways * math.sin((self.viewAngleFloor+90.0)*math.pi/180.0)
        adjust = True
        testX = self.lookingAtX + dx
        if testX > w:
            self.lookingAtX = w
            adjust = False
        elif testX < 0:
            self.lookingAtX = 0
            adjust = False        
        testY = self.lookingAtY + dy        
        if testY > h:
            self.lookingAtY = h
            adjust = False
        elif testY < 0:
            self.lookingAtY = 0
            adjust = False
        if adjust:
            self.lookingAtX = testX
            self.lookingAtY = testY
        #self.SetupProjection()
        self.recomputeCamera()
        #self.Refresh(False)
        self.requestRedraw()
        
    def adjustZoom(self,adjustment):
        self.zoom += float(adjustment)
        if self.zoom <= self.minZoom:
            self.zoom = self.minZoom
        elif self.zoom > self.maxZoom:
            self.zoom = self.maxZoom
        self.SetupProjection()
        self.recomputeCamera()
        #self.Refresh(False)
        self.requestRedraw()

    def doSelection(self,x,y):
        glSelectBuffer(100)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glMatrixMode(GL_MODELVIEW)
        glRenderMode(GL_SELECT)
        self.SetupProjection(True,x,y)
        self.DrawGLScene()
        buf = glRenderMode(GL_RENDER)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        return buf

    def output_text(self,x, y, text):
        if not _has_glut_text_support():
            return
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0.0, self.width, 0.0, self.height)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glRasterPos2f(float(x), float(y))
        for c in text:
            glutBitmapCharacter(GLUT_BITMAP_TIMES_ROMAN_10, ord(c))
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def clearCache(self):
        self.preprocessedNodes = Set()
        self.textureStore = {}

    def isRenderableMeshNode(self,node):
        if node is None:
            return False
        if not hasattr(node, 'hasMesh') or not node.hasMesh():
            return False
        if hasattr(node, 'renderFlag') and not bool(node.renderFlag):
            return False
        # AABB nodes are helper/collision geometry and should not be drawn.
        if hasattr(node, 'isAABBMesh') and node.isAABBMesh():
            return False
        if getattr(node, 'vertices', None) is None or len(node.vertices) == 0:
            return False
        vil = getattr(node, 'vertexIndexLists', None)
        if vil is None or len(vil) == 0:
            return False
        return True
    
    def preprocessNodes(self,model,tag,bbox=False):
        #if model.getPreprocessed():
        #    logger.warning("asked to preprocess already preprocessed model " +
        #                   model.getName())
        #    import traceback
        #    traceback.print_stack()
        if model is None:
            logger.warning('skipping preprocess for empty model (%s)', tag)
            return False
        root = model.getRootNode()
        if root is None:
            logger.warning('skipping preprocess for model with no root node (%s)', tag)
            return False
        previous_tint_context = self._activePLTTintContext
        self._activePLTTintContext = getattr(model, 'pltTintContext', None)
        try:
            self.preprocessNodesHelper(root,tag,0,model)
        finally:
            self._activePLTTintContext = previous_tint_context
        if bbox and not model.validBoundingBox:
            model.boundingBox = self.calculateNodeTreeBoundingBox(root)
            model.boundingSphere = [[0,0,0],0]
            model.boundingSphere[0] = (model.boundingBox[1]
                                       + model.boundingBox[0])/2.0
            r0 = model.boundingBox[0] - model.boundingSphere[0]
            r1 = model.boundingBox[1] - model.boundingSphere[0]        
            r = max(Numeric.dot(r0,r0),Numeric.dot(r1,r1))
            model.boundingSphere[1] = math.sqrt(r)
            model.validBoundingBox = True
        #model.setPreprocessed(True)
        return True
        
    def preprocessNodesHelper(self,node,tag,level,model=None):
        if node is None:
            return
        if model is not None:
            node._ownerModel = model
        node.controllerDisplayList = glGenLists(1)
        glNewList(node.controllerDisplayList,GL_COMPILE)
        self.processControllers(node)
        glEndList()
        if self.isRenderableMeshNode(node):
            node.colourDisplayList = glGenLists(1)
            glNewList(node.colourDisplayList,GL_COMPILE)
            self.processColours(node)
            glEndList()
            self._ensureNodeTextureGL(node,0)
            self._ensureNodeTextureGL(node,1)
                    
        for c in node.children:
            self.preprocessNodesHelper(c,tag,level+1,model)

    def _resolveAnimationNodesForModel(self, model):
        if model is None or not self.animationsEnabled:
            return None
        if not hasattr(model, 'resolveAnimationTrack'):
            return None
        preferred = self.animationTrackByMode.get(self.animationMode, ())
        track_name = model.resolveAnimationTrack(preferred)
        if track_name:
            nodes = model.getAnimationNodes(track_name)
            if nodes:
                self._logAnimationTrackBinding(model, 'model', track_name, len(nodes))
                return nodes

        # Fall back to supermodel track tables when available.
        super_name = str(getattr(model, 'superModelName', '') or '').strip().lower()
        if not super_name or super_name in ('null', '****'):
            return None

        if super_name not in self._superModelCache:
            rm = neverglobals.getResourceManager()
            candidates = [super_name]
            if not super_name.endswith('.mdl'):
                candidates.insert(0, super_name + '.mdl')

            loaded = None
            for candidate in candidates:
                loaded = rm.getResourceByName(candidate)
                if loaded is not None:
                    break
            self._superModelCache[super_name] = loaded

        super_model = self._superModelCache.get(super_name)
        if super_model is None or not hasattr(super_model, 'resolveAnimationTrack'):
            self._logAnimationTrackBinding(model, 'supermodel-missing', None, 0)
            return None
        super_track = super_model.resolveAnimationTrack(preferred)
        if not super_track:
            self._logAnimationTrackBinding(model, 'supermodel-no-track', None, 0)
            return None
        nodes = super_model.getAnimationNodes(super_track)
        if not nodes:
            self._logAnimationTrackBinding(model, 'supermodel-empty-track', super_track, 0)
            return None
        self._logAnimationTrackBinding(model, 'supermodel', super_track, len(nodes))
        return nodes

    def _getActiveControllerNode(self, node):
        if not self._activeAnimationNodes:
            return node
        name = getattr(node, 'name', None)
        if not name:
            return node
        track_node = self._activeAnimationNodes.get(name)
        if track_node is None:
            return node
        return track_node

    def _ensureNodeTextureGL(self,node,slot):
        tex_attr = 'texture%d' % slot
        name_attr = 'texture%dname' % slot
        gl_attr = 'glTexture%dName' % slot
        resname_attr = 'texture%dresname' % slot
        tex = getattr(node, tex_attr, None)
        if tex is None:
            return
        tex_name = getattr(node, resname_attr, None) or getattr(node, name_attr, None)
        if not tex_name:
            return

        store_key = tex_name
        if str(tex_name).lower().endswith('.plt') and self._activePLTTintContext:
            tint_signature = tuple(sorted(self._activePLTTintContext.items()))
            store_key = (tex_name, tint_signature)

            rm = neverglobals.getResourceManager()
            raw = rm.getRawResourceByName(tex_name)
            if raw:
                tinted = rm.decodePLT(raw, tintContext=self._activePLTTintContext)
                if tinted is not None:
                    tex = tinted
                    setattr(node, tex_attr, tex)

        if store_key not in self.textureStore:
            gl_name = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, gl_name)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            try:
                w, h, image = tex.size[0], tex.size[1], tex.tobytes('raw', 'RGBA', 0, -1)
            except (SystemError, ValueError, OSError):
                try:
                    w, h, image = tex.size[0], tex.size[1], tex.tobytes('raw', 'RGBX', 0, -1)
                except (SystemError, ValueError, OSError):
                    tex = tex.convert('RGBA')
                    setattr(node, tex_attr, tex)
                    w, h, image = tex.size[0], tex.size[1], tex.tobytes('raw', 'RGBA', 0, -1)

            assert w * h * 4 == len(image)
            gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RGBA, w, h, GL_RGBA,
                              GL_UNSIGNED_BYTE, image)
            self.textureStore[store_key] = gl_name
        setattr(node, gl_attr, self.textureStore[store_key])

    def mergeBoxes(self,boxResult,boxAdd):
        for i in range(3):
            boxResult[0][i] = min(boxResult[0][i],boxAdd[0][i])
            boxResult[1][i] = max(boxResult[1][i],boxAdd[1][i])
        return boxResult
    
    def calculateNodeTreeBoundingBoxHelper(self,node,bb):
        glPushMatrix()
        #first, position transform to this node's space
        glCallList(node.controllerDisplayList)
        #calculcate this node's world space bounding box
        mybb = Numeric.array([3*[float(sys.maxsize)],
                               3*[-float(sys.maxsize)]])
        if self.isRenderableMeshNode(node):
            for v in node.boundingBox:
                v = Numeric.transpose(self.transformPointModel(v))
                for i in range(3):
                    if v[i,0] < mybb[0][i]:
                        mybb[0][i] = v[i,0]
                    if v[i,0] > mybb[1][i]:
                        mybb[1][i] = v[i,0]
        else:
            mybb = Numeric.array([3*[0.0],3*[0.0]])
        #calculate the children's bboxes and merge them into ours
        for c in node.children:
            childbb = Numeric.array([3*[float(sys.maxsize)],
                                      3*[float(-sys.maxsize)]])
            self.calculateNodeTreeBoundingBoxHelper(c,childbb)
            self.mergeBoxes(mybb,childbb)
        #set the calculated bbox and calculate the bounding sphere
#        print 'setting bounding box for',node.name,'to',mybb
        node.boundingBox = Numeric.array(mybb)
        node.boundingSphere = [[0,0,0],0]
        node.boundingSphere[0] = (node.boundingBox[1]
                                  + node.boundingBox[0])/2.0
        r0 = node.boundingBox[0] - node.boundingSphere[0]
        r1 = node.boundingBox[1] - node.boundingSphere[0]        
        r = max(Numeric.dot(r0,r0),Numeric.dot(r1,r1))
        node.boundingSphere[1] = math.sqrt(r)
        #finally, merge our box with the passed in one
        self.mergeBoxes(bb,mybb)
        glPopMatrix()
        
    def calculateNodeTreeBoundingBox(self,node):
        self.modelMatrix = None
        self.viewMatrixInv = Numeric.identity(4)
        boundingBox = Numeric.array([3*[0.0],#float(sys.maxint)],
                                     3*[0.0]])#float(-sys.maxint)]])
        glPushMatrix()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        self.calculateNodeTreeBoundingBoxHelper(node,boundingBox)
        glPopMatrix()
        self.SetupProjection()
        return boundingBox

    def fixMatrixToNumPy(self,matrix):
        numpymatrix = Numeric.array(matrix,'d')
        return numpymatrix

    def processControllers(self,node,animationTime=None):
        controller_node = self._getActiveControllerNode(node)
        controller_map = getattr(controller_node, 'controllers', None)

        if animationTime is not None and hasattr(node, 'getAnimatedPositionFromMap'):
            p = node.getAnimatedPositionFromMap(controller_map, animationTime)
        else:
            p = node.position
        if p is not None:
            glTranslate(p[0],p[1],p[2])

        if animationTime is not None and hasattr(node, 'getAnimatedOrientationMatrixFromMap'):
            orientation = node.getAnimatedOrientationMatrixFromMap(controller_map, animationTime)
        else:
            orientation = node.orientation
        if orientation is not None:
            orientation = self.fixMatrixToNumPy(orientation)
            glMultMatrixf(orientation)

        if animationTime is not None and hasattr(node, 'getAnimatedScaleFromMap'):
            s = node.getAnimatedScaleFromMap(controller_map, animationTime)
        else:
            s = node.scale
        if s:
            glScalef(s,s,s)

    def processColours(self,node):
        if node.shininess:
            glMaterialf(GL_FRONT,GL_SHININESS,node.shininess)
        glMaterialfv(GL_FRONT,GL_AMBIENT,node.ambientColour)
        glMaterialfv(GL_FRONT,GL_DIFFUSE,node.diffuseColour)
        glMaterialfv(GL_FRONT,GL_SPECULAR,node.specularColour)

    def solidColourOn(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glShadeModel(GL_FLAT)
        glEnable(GL_POLYGON_OFFSET_LINE)
        glPolygonOffset(1.0, 1.0)

    def solidColourOff(self):
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glDisable(GL_POLYGON_OFFSET_LINE)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)

    def wireOn(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_ONE,GL_ONE)
        glShadeModel(GL_FLAT)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glEnable(GL_POLYGON_OFFSET_LINE)
        glPolygonOffset(1.0, 1.0)

    def wireOff(self):
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_LINE)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    def transparentColourOn(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glShadeModel(GL_FLAT)
        glEnable(GL_POLYGON_OFFSET_LINE)

    def transparentColourOff(self):
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_LINE)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glShadeModel(GL_SMOOTH)
        
    def glColorf(self,colour):
        #FIXME: glColorf is not defined, changing to glColor3f
        glColor3f(colour[0],colour[1],colour[2])

    def renderHighlightBoxOutline(self,box,colour=(0.1,1.0,0.1,0.5),
                                  thickness=3.0):
        self.solidColourOn()
        self.glColorf(colour)
        glLineWidth(thickness)
        self.renderBox(box)
        glLineWidth(1.0)
        self.solidColourOff()

    def renderArrowOutline(self,size,colour=(0.1,1.0,0.1,1.0)):
        self.solidColourOn()
        self.glColorf(colour)
        glLineWidth(3.0)
        self.renderArrow(size)
        glLineWidth(1.0)
        self.solidColourOff()
        
    def renderHighlightBoxTransparent(self,box,colour=(0.1,1.0,0.1,0.5)):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        self.glColorf(colour)
        glShadeModel(GL_FLAT)
        glEnable(GL_POLYGON_OFFSET_LINE)
        glPolygonOffset(1.0, 1.0)
        self.renderBox(box,fill=True)
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_LINE)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glShadeModel(GL_SMOOTH)

    def renderSphereTransparent(self,sphere,colour=(0.1,1.0,0.1,0.5)):
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        self.glColorf(colour)
        glShadeModel(GL_FLAT)
        glEnable(GL_POLYGON_OFFSET_LINE)
        glPolygonOffset(1.0, 1.0)
        glPushMatrix()
        glTranslatef(sphere[0][0],
                     sphere[0][1],
                     sphere[0][2])
        glutSolidSphere(sphere[1],20,20)
        glPopMatrix()
        glEnable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_POLYGON_OFFSET_LINE)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glShadeModel(GL_SMOOTH)

    def renderArrow(self,size,fill=False):
        type = GL_LINE_STRIP
        if fill:
            type = GL_TRIANGLE_STRIP
        glBegin(type)
        glVertex3f(-size,-size,0)
        glVertex3f(size,-size,0)
        glVertex3f(size,-size,size)
        glVertex3f(-size,-size,size)        
        glVertex3f(-size,-size,0)
        glVertex3f(0,2*size,0)
        glVertex3f(0,2*size,size)
        glVertex3f(-size,-size,size)

        glEnd()

        glBegin(type)
        glVertex3f(0,2*size,0)
        glVertex3f(0,2*size,size)
        glVertex3f(size,-size,size)
        glVertex3f(size,-size,0)
        glEnd()
        
    def renderBox(self,box,fill=False):
        if fill:
            glBegin(GL_QUADS)
        else:
            glBegin(GL_LINE_STRIP)
        glVertex3f(box[0][0],box[0][1],box[0][2])
        glVertex3f(box[0][0],box[0][1],box[1][2])
        glVertex3f(box[0][0],box[1][1],box[1][2])
        glVertex3f(box[0][0],box[1][1],box[0][2])
            
        glVertex3f(box[0][0],box[0][1],box[0][2])
        glVertex3f(box[0][0],box[1][1],box[0][2])
        glVertex3f(box[1][0],box[1][1],box[0][2])
        glVertex3f(box[1][0],box[0][1],box[0][2])

        glVertex3f(box[0][0],box[0][1],box[0][2])
        glVertex3f(box[0][0],box[0][1],box[1][2])
        glVertex3f(box[1][0],box[0][1],box[1][2])
        glVertex3f(box[1][0],box[0][1],box[0][2])
        
        glVertex3f(box[1][0],box[0][1],box[1][2])
        glVertex3f(box[1][0],box[0][1],box[0][2])
        glVertex3f(box[1][0],box[1][1],box[0][2])
        glVertex3f(box[1][0],box[1][1],box[1][2])
            
        glVertex3f(box[1][0],box[1][1],box[1][2])
        glVertex3f(box[1][0],box[0][1],box[1][2])
        glVertex3f(box[0][0],box[0][1],box[1][2])
        glVertex3f(box[0][0],box[1][1],box[1][2])

        glVertex3f(box[1][0],box[1][1],box[1][2])
        glVertex3f(box[1][0],box[1][1],box[0][2])
        glVertex3f(box[0][0],box[1][1],box[0][2])
        glVertex3f(box[0][0],box[1][1],box[1][2])
        glEnd()

    def processTextures(self,node):
        if node.texture0:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D,node.glTexture0Name)
            if hasattr(node,'texture0Vertices') and \
               node.texture0Vertices is not None and \
               len(node.texture0Vertices) > 0:
                try:
                    glTexCoordPointerf(node.texture0Vertices)
                    glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                except (gl_error.Error, TypeError):
                    # Fall back to untextured geometry if texcoord arrays are
                    # unavailable in the active GL profile.
                    glDisableClientState(GL_TEXTURE_COORD_ARRAY)
                    glDisable(GL_TEXTURE_2D)
                    return False
            else:
                glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        else:
            glDisable(GL_TEXTURE_2D)
            #print node.name,'does not have texture'
            return False

    def processTexturesImmediate(self,node):
        if node.texture0:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D,node.glTexture0Name)
            return True
        glDisable(GL_TEXTURE_2D)
        return False

    def sendVertices(self,node):
        # Fallback rendering paths may disable client arrays; always restore
        # vertex-array state before pointer submission.
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointerf(self.getNodeVerticesForDraw(node))

    def _captureSkinMatricesHelper(self,node,matrix_map):
        if node is None:
            return
        glPushMatrix()
        try:
            self.processControllers(node, self._animationTimeSeconds)
            node_id = getattr(node, 'nodeNumber', None)
            if node_id is not None:
                mv = Numeric.array(glGetDoublev(GL_MODELVIEW_MATRIX), 'd')
                matrix_map[int(node_id)] = Numeric.dot(mv, self.viewMatrixInv)
            for c in getattr(node, 'children', []):
                self._captureSkinMatricesHelper(c, matrix_map)
        finally:
            glPopMatrix()

    def _prepareSkinningState(self,root_node):
        self._skinCurrentMatrices = {}
        self._skinDeformedVertexCache = {}
        self._skinDeformedNormalCache = {}
        self._captureSkinMatricesHelper(root_node, self._skinCurrentMatrices)

        if not hasattr(root_node, '_skinRestMatrices') and self._skinCurrentMatrices:
            root_node._skinRestMatrices = {}
            root_node._skinRestInverseMatrices = {}
            for bone_id, mat in list(self._skinCurrentMatrices.items()):
                rest = Numeric.array(mat, 'd')
                root_node._skinRestMatrices[int(bone_id)] = rest
                try:
                    root_node._skinRestInverseMatrices[int(bone_id)] = LinearAlgebra.inverse(rest)
                except Exception:
                    pass

        self._skinRestMatrices = getattr(root_node, '_skinRestMatrices', None)
        self._skinRestInverseMatrices = getattr(root_node, '_skinRestInverseMatrices', None)

    def _getSkinDeltaByBone(self):
        if (self._skinCurrentMatrices is None or self._skinRestInverseMatrices is None):
            return None
        deltas = {}
        for bone_id, current in list(self._skinCurrentMatrices.items()):
            inv_rest = self._skinRestInverseMatrices.get(int(bone_id))
            if inv_rest is None:
                continue
            deltas[int(bone_id)] = Numeric.dot(inv_rest, current)
        return deltas

    def _computeSkinnedVertices(self,node):
        if node is None:
            return None
        if not hasattr(node, 'skinWeights') or not hasattr(node, 'skinBoneIds'):
            return None
        if node.skinWeights is None or node.skinBoneIds is None:
            return None
        if node.vertices is None or len(node.vertices) == 0:
            return None

        try:
            vertex_count = int(len(node.vertices))
            if node.skinWeights.shape[0] != vertex_count or node.skinBoneIds.shape[0] != vertex_count:
                return None
        except Exception:
            return None

        deltas = self._getSkinDeltaByBone()
        if not deltas:
            return None

        out = Numeric.array(node.vertices, 'f')
        weights = node.skinWeights
        bone_ids = node.skinBoneIds
        for i in range(vertex_count):
            base = node.vertices[i]
            p4 = Numeric.array([base[0], base[1], base[2], 1.0], 'f')
            accum = Numeric.zeros((3,), 'f')
            used_w = 0.0
            for j in range(4):
                w = float(weights[i][j])
                if w <= 0.0:
                    continue
                bone_id = int(bone_ids[i][j])
                delta = deltas.get(bone_id)
                if delta is None:
                    continue
                tp = Numeric.dot(p4, delta)
                accum += (w * Numeric.array(tp[:3], 'f'))
                used_w += w
            if used_w > 0.0:
                if used_w < 1.0:
                    accum += (1.0 - used_w) * Numeric.array(base, 'f')
                out[i] = accum
        return out

    def _computeSkinnedNormals(self,node):
        if node is None or node.normals is None or len(node.normals) == 0:
            return None
        if not hasattr(node, 'skinWeights') or not hasattr(node, 'skinBoneIds'):
            return None
        if node.skinWeights is None or node.skinBoneIds is None:
            return None

        try:
            normal_count = int(len(node.normals))
            if node.skinWeights.shape[0] != normal_count or node.skinBoneIds.shape[0] != normal_count:
                return None
        except Exception:
            return None

        deltas = self._getSkinDeltaByBone()
        if not deltas:
            return None

        out = Numeric.array(node.normals, 'f')
        weights = node.skinWeights
        bone_ids = node.skinBoneIds
        for i in range(normal_count):
            base = node.normals[i]
            n4 = Numeric.array([base[0], base[1], base[2], 0.0], 'f')
            accum = Numeric.zeros((3,), 'f')
            used_w = 0.0
            for j in range(4):
                w = float(weights[i][j])
                if w <= 0.0:
                    continue
                bone_id = int(bone_ids[i][j])
                delta = deltas.get(bone_id)
                if delta is None:
                    continue
                tn = Numeric.dot(n4, delta)
                accum += (w * Numeric.array(tn[:3], 'f'))
                used_w += w
            if used_w > 0.0:
                if used_w < 1.0:
                    accum += (1.0 - used_w) * Numeric.array(base, 'f')
                length = math.sqrt(float(Numeric.dot(accum, accum)))
                if length > 1.0e-8:
                    accum /= length
                out[i] = accum
        return out

    def getNodeVerticesForDraw(self,node):
        if node is None:
            return None
        if self._skinDeformedVertexCache is None:
            return node.vertices
        cache_key = id(node)
        if cache_key in self._skinDeformedVertexCache:
            return self._skinDeformedVertexCache[cache_key]
        deformed = None
        if getattr(node, 'isSkinMesh', None) and node.isSkinMesh():
            deformed = self._computeSkinnedVertices(node)
        if deformed is None:
            deformed = node.vertices
        self._skinDeformedVertexCache[cache_key] = deformed
        return deformed

    def getNodeNormalsForDraw(self,node):
        if node is None:
            return None
        if self._skinDeformedNormalCache is None:
            return node.normals
        cache_key = id(node)
        if cache_key in self._skinDeformedNormalCache:
            return self._skinDeformedNormalCache[cache_key]
        deformed = None
        if getattr(node, 'isSkinMesh', None) and node.isSkinMesh():
            deformed = self._computeSkinnedNormals(node)
        if deformed is None:
            deformed = node.normals
        self._skinDeformedNormalCache[cache_key] = deformed
        return deformed

    def getNodeDrawMode(self, node):
        if getattr(node, 'indicesFromFaces', False):
            return GL_TRIANGLES
        mode = getattr(node, 'triangleMode', None)
        # NWN binary MDL triangleMode is not a GL enum:
        # 3 = triangles, 4 = triangle strip.
        if mode == 3:
            return GL_TRIANGLES
        if mode == 4:
            return GL_TRIANGLE_STRIP
        # Keep tolerant handling for potential pre-normalized GL enum values.
        if mode in (GL_TRIANGLES,):
            return GL_TRIANGLES
        if mode in (GL_TRIANGLE_STRIP, 5):
            return GL_TRIANGLE_STRIP
        if mode in (GL_TRIANGLE_FAN, 6):
            return GL_TRIANGLE_FAN
        return GL_TRIANGLES

    def doNormals(self,node):
        normals = self.getNodeNormalsForDraw(node)
        if normals is not None and len(normals) > 0:
            glNormalPointerf(normals)
            glEnableClientState(GL_NORMAL_ARRAY)
        else:
            glDisableClientState(GL_NORMAL_ARRAY)

    def drawVertices(self,node,l):
        glDrawElementsus(self.getNodeDrawMode(node),l)
        
    def drawVertexLists(self,node):
        for l in node.vertexIndexLists:
            self.drawVertices(node,l)
        
    def processVertices(self,node):
        self.sendVertices(node)
        self.doNormals(node)
        self.drawVertexLists(node)

    def processVerticesImmediate(self,node,withTextures=False):
        vertices = self.getNodeVerticesForDraw(node)
        normals = self.getNodeNormalsForDraw(node)
        hasNormals = normals is not None and len(normals) > 0
        hasTexcoords = withTextures and hasattr(node,'texture0Vertices') and \
            node.texture0Vertices is not None and len(node.texture0Vertices) > 0
        draw_mode = self.getNodeDrawMode(node)

        for index_list in node.vertexIndexLists:
            glBegin(draw_mode)
            for raw_index in index_list:
                i = int(raw_index)
                if hasNormals:
                    n = normals[i]
                    glNormal3f(float(n[0]), float(n[1]), float(n[2]))
                if hasTexcoords:
                    t = node.texture0Vertices[i]
                    glTexCoord2f(float(t[0]), float(t[1]))
                v = vertices[i]
                glVertex3f(float(v[0]), float(v[1]), float(v[2]))
            glEnd()
        
    def processNode(self,node,boxOnly=False):
        if boxOnly and node.boundingBox[1][0]:
            self.renderBox(node.boundingBox)
            return True
        try:
            textured = self.processTextures(node)
            glCallList(node.colourDisplayList)
            self.processVertices(node)
            self.drawSecondaryTexturePass(node)
            return True
        except (gl_error.Error, TypeError, ValueError, IndexError):
            # Some drivers/PyOpenGL combinations fail client-array setup despite
            # a valid context. Fall back to immediate-mode drawing so map geometry
            # still renders.
            if not self._loggedImmediateFallback:
                logger.warning('GL client-array path unavailable; using immediate-mode fallback rendering')
                self._loggedImmediateFallback = True
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
            textured = self.processTexturesImmediate(node)
            glCallList(node.colourDisplayList)
            self.processVerticesImmediate(node,withTextures=textured)
            self.drawSecondaryTexturePass(node,forceImmediate=True)
        return True

    def drawSecondaryTexturePass(self,node,forceImmediate=False):
        if node is None or not getattr(node, 'texture1', None):
            return
        gl_tex1 = getattr(node, 'glTexture1Name', None)
        if not gl_tex1:
            return
        texcoords = getattr(node, 'texture1Vertices', None)
        if texcoords is None or len(texcoords) == 0:
            texcoords = getattr(node, 'texture0Vertices', None)
        if texcoords is None or len(texcoords) == 0:
            return

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, gl_tex1)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDepthMask(GL_FALSE)
        glColor4f(1.0, 1.0, 1.0, 0.45)
        used_client_path = False
        try:
            if not forceImmediate:
                glTexCoordPointerf(texcoords)
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                self.sendVertices(node)
                self.drawVertexLists(node)
                used_client_path = True
        except (gl_error.Error, TypeError, ValueError, IndexError):
            pass
        try:
            if not used_client_path:
                vertices = self.getNodeVerticesForDraw(node)
                draw_mode = self.getNodeDrawMode(node)
                for index_list in node.vertexIndexLists:
                    glBegin(draw_mode)
                    for raw_index in index_list:
                        i = int(raw_index)
                        t = texcoords[i]
                        glTexCoord2f(float(t[0]), float(t[1]))
                        v = vertices[i]
                        glVertex3f(float(v[0]), float(v[1]), float(v[2]))
                    glEnd()
        finally:
            glDepthMask(GL_TRUE)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LIGHTING)

    def drawBoundingBoxes(self,node):
        if Numeric.alltrue(Numeric.equal(node.boundingBox[1],[0,0,0])):
            return
        self.renderBox(node.boundingBox)
        for c in node.children:
            self.drawBoundingBoxes(c)

    def drawBoundingSpheres(self,node):
        for c in node.children:
            self.drawBoundingSpheresHelper(c)
            
    def drawBoundingSpheresHelper(self,node):
        if Numeric.alltrue(Numeric.equal(node.boundingBox[1],[0,0,0])):
            return
        if self.sphereInFrustum(self.transformPointModel(node.boundingSphere[0]),
                                node.boundingSphere[1]):
            #print 'bounding sphere for',node.name,'is IN frustum'
            glPushMatrix()
            glTranslate(node.boundingSphere[0][0],
                        node.boundingSphere[0][1],
                        node.boundingSphere[0][2])
            glutSolidSphere(node.boundingSphere[1],30,30)
            glPopMatrix()
        for c in node.children:
            self.drawBoundingSpheres(c)

    def handleNode(self,node,
                   frustumCull=False,
                   boxOnly=False,
                   selected=False):
        if node is None:
            return
        previous_current = self._skinCurrentMatrices
        previous_rest = self._skinRestMatrices
        previous_rest_inv = self._skinRestInverseMatrices
        previous_vertex_cache = self._skinDeformedVertexCache
        previous_normal_cache = self._skinDeformedNormalCache
        previous_animation_nodes = self._activeAnimationNodes

        owner_model = getattr(node, '_ownerModel', None)
        self._activeAnimationNodes = self._resolveAnimationNodesForModel(owner_model)

        self._prepareSkinningState(node)
        if frustumCull:
            self.modelMatrix =  Numeric.dot(glGetDoublev(GL_MODELVIEW_MATRIX),
                                             self.viewMatrixInv)
        else:
            self.modelMatrix = None
        try:
            drewSomething = self.handleNodeHelper(node,frustumCull,boxOnly,selected)
            if (not drewSomething) and hasattr(node, 'boundingBox'):
                self.renderHighlightBoxOutline(node.boundingBox)
        finally:
            self.modelMatrix = None
            self._skinCurrentMatrices = previous_current
            self._skinRestMatrices = previous_rest
            self._skinRestInverseMatrices = previous_rest_inv
            self._skinDeformedVertexCache = previous_vertex_cache
            self._skinDeformedNormalCache = previous_normal_cache
            self._activeAnimationNodes = previous_animation_nodes
            
    def handleNodeHelper(self,node,
                   frustumCull=False,
                   boxOnly=False,
                   selected=False):
        if node is None:
            return False
        glPushMatrix()
        try:
            self.processControllers(node, self._animationTimeSeconds)
            drewSomething = False
            if frustumCull and hasattr(node, 'boundingBox') and node.boundingBox[1][0]:
                #print node.name,self.transformPointModel(node.boundingSphere[0]),
                #node.boundingSphere[1]
                if not self.sphereInFrustum(self.transformPointModel(node.boundingSphere[0]),
                                            node.boundingSphere[1]):
                    #print node.name,'is OUTSIDE the frustum'
                    return True
            if self.isRenderableMeshNode(node):
                drewSomething = self.processNode(node,boxOnly)
                if selected:
                    glPushMatrix()
                    try:
                        glScalef(1.2,1.2,1.2)
                        #glBlendFunc(GL_ONE,GL_ONE)
                        glColor4f(0.1,0.9,0.1,0.6)
                        glDisable(GL_LIGHTING)
                        #self.renderBox(self.model.boundingBox)
                        self.processNode(node,False)
                    finally:
                        glPopMatrix()
                        #glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
                        glEnable(GL_LIGHTING)
            for c in getattr(node, 'children', []):
                drewSomething |= self.handleNodeHelper(c,frustumCull,boxOnly,selected)
            return drewSomething
        finally:
            glPopMatrix()
            


    def isBoxVisible(self,box):
        return self.boxInFrustum(box)

    def isVisible(self,object):
        if not hasattr(object,'boundingSphere'):
            return True
        return self.isSphereVisible(object.boundingSphere)
    
    def isSphereVisible(self,sphere):
        centre = self.transformPointModelView(sphere[0])
        return self.sphereInFrustum(centre,sphere[1])
    
    def getTotalMatrix(self):
        pm = glGetDoublev(GL_PROJECTION_MATRIX)
        mvm = glGetDoublev(GL_MODELVIEW_MATRIX)
        return Numeric.dot(mvm,pm)

    def transformPointInverseModelView(self,p):
        p = Numeric.resize(p,(1,4))
        p[0,3] = 1.0
        mvm = Numeric.array(glGetDoublev(GL_MODELVIEW_MATRIX))
        mvminv = LinearAlgebra.inverse(mvm)
        p = Numeric.dot(p,mvminv)
        p /= p[0,3]
        return p

    def transformPointModel(self,p):
        p = Numeric.resize(p,(1,4))
        p[0,3] = 1.0
        if self.modelMatrix is not None:
            p = Numeric.matrixmultiply(p,self.modelMatrix)
        else:
            p = Numeric.dot(p,glGetDoublev(GL_MODELVIEW_MATRIX))
            p = Numeric.dot(p,self.viewMatrixInv)
        p /= p[0,3]
        return p

    def cacheModelView(self):
        self.currentModelView = glGetDoublev(GL_MODELVIEW_MATRIX)

    def clearModelView(self):
        self.currentModelView = None
        
    def transformPointModelView(self,p):
        self.point[0,:3] = p
        self.point[0,3] = 1.0
        #p = Numeric.resize(p,(1,4))
        #p[0,3] = 1.0
        if self.currentModelView is None:
            mvm = glGetDoublev(GL_MODELVIEW_MATRIX)
        else:
            mvm = self.currentModelView
        r = Numeric.dot(self.point,mvm)
        r /= r[0,3]
        return r
    
    def transformPoint(self,p):
        p = Numeric.resize(p,(1,4))
        p[0,3] = 1.0
        p = Numeric.dot(p,glGetDoublev(GL_MODELVIEW_MATRIX))
        p = Numeric.dot(p,glGetDoublev(GL_PROJECTION_MATRIX))
        p /= p[0,3]
        return p

    def drawFrustum(self):
        #right-bottom-front
        p1 = -self.triplePlaneIntersect(self.frustum[0],
                                       self.frustum[2],
                                       self.frustum[5])
        #right-bottom-back
        p2 = -self.triplePlaneIntersect(self.frustum[0],
                                       self.frustum[2],
                                       self.frustum[4])
        #right-top-front
        p3 = -self.triplePlaneIntersect(self.frustum[0],
                                       self.frustum[3],
                                       self.frustum[5])
        #right-top-back
        p4 = -self.triplePlaneIntersect(self.frustum[0],
                                       self.frustum[3],
                                       self.frustum[4])
        #left-bottom-front
        p5 = -self.triplePlaneIntersect(self.frustum[1],
                                       self.frustum[2],
                                       self.frustum[5])
        #left-bottom-back
        p6 = -self.triplePlaneIntersect(self.frustum[1],
                                       self.frustum[2],
                                       self.frustum[4])
        #left-top-front        
        p7 = -self.triplePlaneIntersect(self.frustum[1],
                                       self.frustum[3],
                                       self.frustum[5])
        #left-top-back        
        p8 = -self.triplePlaneIntersect(self.frustum[1],
                                       self.frustum[3],
                                       self.frustum[4])

        print(p1)
        print(p3)
        print(p5)
        print(p7)
        print(p2)
        print(p4)
        print(p6)
        print(p8)
       
        glBegin(GL_LINE_STRIP)
        glVertexf(p1)
        glVertexf(p2)
        glVertexf(p4)
        glVertexf(p3)
        glVertexf(p1)
        glVertexf(p5)
        glVertexf(p6)
        glVertexf(p8)
        glVertexf(p7)
        glVertexf(p5)
        glEnd()
        glBegin(GL_LINES)
        glVertexf(p7)
        glVertexf(p3)
        glVertexf(p8)
        glVertexf(p4)
        glVertexf(p6)
        glVertexf(p2)
        glEnd()
        glColor3f(1.0,0.0,0.0)
        glBegin(GL_QUADS)
        glVertex(p2)
        glVertex(p4)
        glVertex(p8)
        glVertex(p6)
        glEnd()
#        glColor3f(0.0,1.0,0.0)
#        glBegin(GL_QUADS)
#        glVertex(p1)
#        glVertex(p3)
#        glVertex(p7)
#        glVertex(p5)
#        glEnd()
        
    def computeFrustum(self):
        self.frustum = []
        #clip = self.getTotalMatrix()
        clip = Numeric.array(glGetDoublev(GL_PROJECTION_MATRIX))
        
        #print 'total',clip        
        self.frustum.append(clip[:,3]-clip[:,0]) # right
        self.frustum.append(clip[:,3]+clip[:,0]) # left
        self.frustum.append(clip[:,3]+clip[:,1]) # bottom        
        self.frustum.append(clip[:,3]-clip[:,1]) # top
        #self.frustum.append(clip[:,3]-clip[:,2]) # back
        #self.frustum.append(clip[:,3]+clip[:,2]) # front
        self.frustum = self.fixMatrixToNumPy(self.frustum)
        #print 'frustum',self.frustum        

        for plane in self.frustum:
            plane /= math.sqrt(Numeric.dot(plane[:3],plane[:3]))
            
    def pointInFrustum(self,p):
        for plane in self.frustum:
            if (Numeric.dot(p,plane)) <= 0:
                return False
        return True

    def sphereInFrustum(self,centre,radius):
        for plane in self.frustum[:4]:
            #print centre[0,:3],plane[3]
            #print centre,plane,Numeric.dot(centre,plane)[0],-radius
            if centre[0,0]*plane[0] + centre[0,1]*plane[1] +\
               centre[0,2]*plane[2] + plane[3] < -radius:
                #Numeric.dot(centre[0,:3],plane[:3]) + plane[3] < -radius:
                #print 'frustum cull failed on plane',i
                return False
        return True
        
    def boxInFrustum(self,box):
        boxMin = box[0]
        boxMax = box[1]
        #print self.pointInFrustum(boxMin)
        #print self.pointInFrustum(boxMax)
        #print self.pointInFrustum([boxMin[0],boxMax[1],boxMax[2]])
        #print self.pointInFrustum([boxMin[0],boxMin[1],boxMax[2]])
        #print self.pointInFrustum([boxMax[0],boxMin[1],boxMin[2]])
        #print self.pointInFrustum([boxMax[0],boxMax[1],boxMin[2]])
        #print self.pointInFrustum([boxMin[0],boxMax[1],boxMin[2]])
        #print self.pointInFrustum([boxMax[0],boxMin[1],boxMax[2]])

        return self.pointInFrustum(boxMin) or\
               self.pointInFrustum(boxMax) or\
               self.pointInFrustum([boxMin[0],boxMax[1],boxMax[2]]) or\
               self.pointInFrustum([boxMin[0],boxMin[1],boxMax[2]]) or\
               self.pointInFrustum([boxMax[0],boxMin[1],boxMin[2]]) or\
               self.pointInFrustum([boxMax[0],boxMax[1],boxMin[2]]) or\
               self.pointInFrustum([boxMin[0],boxMax[1],boxMin[2]]) or\
               self.pointInFrustum([boxMax[0],boxMin[1],boxMax[2]])
               
               
               
    def InitGL(self,Width, Height):
        '''A general OpenGL initialization function.
        Sets all of the initial parameters. '''
        self.width = Width
        self.height = Height
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClearDepth(1.0)             # Enables clearing of depth buffer
        glDepthFunc(GL_LESS)          # The Type Of Depth Test To Do
        glEnable(GL_DEPTH_TEST)       # Enables Depth Testing
        glDisable(GL_DITHER)
        glDisable(GL_CULL_FACE)
        glShadeModel(GL_SMOOTH)       # Enables Smooth Color Shading
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glEnable(GL_ALPHA_TEST)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnableClientState (GL_VERTEX_ARRAY)
        glEnableClientState (GL_TEXTURE_COORD_ARRAY)
        glDisableClientState (GL_COLOR_ARRAY)
        glDisableClientState (GL_EDGE_FLAG_ARRAY)
        glDisableClientState (GL_INDEX_ARRAY)
        glDisableClientState (GL_NORMAL_ARRAY)
        glTexEnvf (GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)
        glEnable(GL_TEXTURE_2D)
        glAlphaFunc (GL_GREATER, 0.1)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glHint(GL_PERSPECTIVE_CORRECTION_HINT, GL_NICEST)
        glInitNames()

        self.SetupProjection()
    ##self.wireOn()
#        self.recomputeCamera()

    # The function called when our window is resized
    def ReSizeGLScene(self,Width, Height):
        self.width = Width
        self.height = Height
        if Height == 0:    # Prevent A Divide By Zero If The Window Is Too Small 
            Height = 1
        # Reset The Current Viewport And Perspective Transformation
        glViewport(0, 0, Width, Height)
        self.SetupProjection()
        
    def SetupProjection(self,pick=False,x=0,y=0):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if pick:
            gluPickMatrix(x,y,5,5,None)
        # Keep near plane conservative to avoid clipping model interiors when
        # zoomed close, while still preserving depth precision.
        near_clip = max(0.25, min(self.minZoom / 8.0, 2.0))
        scene_extent = max(float(self.getBaseWidth()), float(self.getBaseHeight()))
        far_clip = max(self.maxZoom + 32.0, scene_extent * 1.8 + 64.0)
        gluPerspective(45.0, float(self.width)/float(self.height),
                       near_clip, far_clip)
        glMatrixMode(GL_MODELVIEW)
        if not pick:
            self.recomputeFrustum = True

    def project(self,x,y,z):
        vm = glGetDoublev(GL_MODELVIEW_MATRIX)
        pm = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        return gluProject(x,y,z,vm,pm,vp)

    def unproject(self,x,y,z):
        vm = glGetDoublev(GL_MODELVIEW_MATRIX)
        pm = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        return gluUnProject(x,y,z,vm,pm,vp)

    def linePlaneIntersect(self,plane,linep1,linep2):
        u = Numeric.dot(plane[:3],linep1) + plane[3]
        u /= Numeric.dot(plane[:3],linep1-linep2)
        return linep1 + u * (linep2-linep1)

    def triplePlaneIntersect(self,plane1,plane2,plane3):
        m = Numeric.array([plane1[:3],plane2[:3],plane3[:3]])
        m = LinearAlgebra.inverse(m)
        v = Numeric.array([[plane1[3],plane2[3],plane3[3]]],shape=(3,1))
        return Numeric.dot(m,v)
        
    
    def quadricErrorCallback(self,arg):
        print(gluErrorString(arg))
        
    def drawRoundedRect(self,width,height):
        cornersize = 5
        quadric = gluNewQuadric()
        gluQuadricDrawStyle(quadric,GLU_FILL)
        gluQuadricNormals(quadric,GLU_SMOOTH)
        glPushMatrix()
        glTranslatef(cornersize,cornersize,0)
        gluPartialDisk(quadric,0,cornersize,5,5,180,90)
        glTranslatef(width-2*cornersize,0,0)
        gluPartialDisk(quadric,0,cornersize,5,5,90,90)
        glTranslatef(0,height-2*cornersize,0)
        gluPartialDisk(quadric,0,cornersize,5,5,0,90)
        glTranslatef(-width+2*cornersize,0,0)
        gluPartialDisk(quadric,0,cornersize,5,5,270,90)        
        gluDeleteQuadric(quadric)
        glTranslatef(-cornersize,0,0)
        glBegin(GL_QUADS)
        glVertex3f(0,0,0)
        glVertex3f(width,0,0)
        glVertex3f(width,-height+2*cornersize,0)
        glVertex3f(0,-height+2*cornersize,0)
        glVertex3f(cornersize,cornersize,0)
        glVertex3f(width-cornersize,cornersize,0)
        glVertex3f(width-cornersize,0,0)
        glVertex3f(cornersize,0,0)
        glVertex3f(cornersize,-height+2*cornersize,0)
        glVertex3f(width-cornersize,-height+2*cornersize,0)
        glVertex3f(width-cornersize,-height+cornersize,0)
        glVertex3f(cornersize,-height+cornersize,0)
        glEnd()        
        glPopMatrix()

    def recomputeCamera(self):
        self.viewX = self.lookingAtX
        self.viewY = self.lookingAtY
        distance = 400.0/self.zoom
        self.viewZ = math.sin((180.0-self.viewAngleSky)
                              *math.pi/180.0) * distance
        floorDistance = math.cos((180.0-self.viewAngleSky)
                                 *math.pi/180.0) * distance
        self.viewX += math.cos(self.viewAngleFloor
                               *math.pi/180.0) * floorDistance
        self.viewY += math.sin(self.viewAngleFloor
                               *math.pi/180.0) * floorDistance
        self.recomputeFrustum = True
        
    def setupCamera(self):
        glLoadIdentity()           # Reset The View
        gluLookAt(self.viewX,self.viewY,self.viewZ,
                  self.lookingAtX,self.lookingAtY,self.lookingAtZ,
                  0,0,1)
        mvm = Numeric.array(glGetDoublev(GL_MODELVIEW_MATRIX))
        self.viewMatrixInv = LinearAlgebra.inverse(mvm)
        if self.recomputeFrustum:
            self.computeFrustum()
            self.recomputeFrustum = False

    def requestRedraw(self):
        if self.redrawRequested:
            return
        else:
            self.redrawRequested = True
            # wxPython Phoenix does not accept an int constructor arg for PaintEvent.
            # Refresh schedules a paint event on the UI loop.
            wx.CallAfter(self.Refresh, False)

    def preprocess(self):
        '''override this routine to do preprocessing on visuals
        with the graphics context active.'''
        raise NotImplementedError('preprocess must be overriden in subclass')
    
    def DrawGLScene(self):
        self.redrawRequested = False
        self.makeCurrent()
        if self.animationsEnabled:
            elapsed = max(0.0, time.time() - self._animationStartTime)
            speed = self.animationSpeedByMode.get(self.animationMode, 1.0)
            self._animationTimeSeconds = elapsed * speed
        else:
            self._animationTimeSeconds = 0.0
        if self.preprocessing:
            return
        if not self.preprocessed:
            self.preprocessing = True
            now = time.time()
            #import profile
            #p = profile.Profile()
            #p.runcall(self.preprocess)
            self.preprocess()
            if self.preprocessed:
                print('preprocessing took %.2f seconds' % (time.time()-now))
                #p.dump_stats('prep.prof')
                self.recomputeCamera()
            self.preprocessing = False
