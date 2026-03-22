import logging
logger = logging.getLogger('neveredit.ui')

import wx
from wx import glcanvas
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL import error as gl_error
import math,sys
import ctypes
import os
import weakref

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
from neveredit.ui.ShaderManager import ShaderManager

Numeric = Utils.getNumPy()
LinearAlgebra = Utils.getLinAlg()
import time


def _decode_gl_string(value):
    if value is None:
        return '<none>'
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8', 'replace')
        except Exception:
            return repr(value)
    return str(value)


CORE_MODEL_VERTEX_SHADER = '''
#version 330 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;
layout(location = 3) in vec4 aInstanceCol0;
layout(location = 4) in vec4 aInstanceCol1;
layout(location = 5) in vec4 aInstanceCol2;
layout(location = 6) in vec4 aInstanceCol3;

uniform mat4 uViewProj;
uniform mat4 uModel;
uniform int uUseInstancing;

out vec3 vNormal;
out vec2 vTexCoord;
out vec3 vWorldPos;

void main() {
    mat4 model = uModel;
    if (uUseInstancing == 1) {
        model = mat4(aInstanceCol0, aInstanceCol1, aInstanceCol2, aInstanceCol3);
    }
    vec4 worldPos = model * vec4(aPosition, 1.0);
    mat3 normalMat = mat3(transpose(inverse(model)));
    vNormal = normalize(normalMat * aNormal);
    vTexCoord = aTexCoord;
    vWorldPos = worldPos.xyz;
    gl_Position = uViewProj * worldPos;
}
'''

CORE_MODEL_FRAGMENT_SHADER = '''
#version 330 core
in vec3 vNormal;
in vec2 vTexCoord;
in vec3 vWorldPos;

uniform vec4 uBaseColor;
uniform vec3 uLightDir;
uniform vec3 uCameraPos;
uniform sampler2D uTexture0;
uniform int uUseTexture;
uniform vec3 uAmbientColor;   // set once per frame from area lighting
uniform vec3 uDiffuseColor;   // set once per frame from area lighting
uniform vec3 uFogColor;
uniform float uFogNear;
uniform float uFogFar;
uniform float uDistanceDesatStrength;
uniform int uUseFog;
uniform int uUseToon;
uniform float uToonBands;
uniform float uToonRimStrength;
uniform int uTwoSidedLighting;

out vec4 fragColor;

void main() {
    vec3 n = normalize(vNormal);
    float ndotl = dot(n, normalize(-uLightDir));
    if (uTwoSidedLighting == 1) {
        ndotl = abs(ndotl);
    } else {
        ndotl = max(ndotl, 0.0);
    }
    vec3 lit = clamp(uAmbientColor + uDiffuseColor * ndotl, vec3(0.0), vec3(1.35));
    if (uUseToon == 1) {
        float bands = max(uToonBands, 2.0);
        float q = floor(ndotl * bands) / bands;
        vec3 coolTint = vec3(0.78, 0.87, 1.03);
        vec3 warmTint = vec3(1.08, 1.02, 0.91);
        vec3 rampTint = mix(coolTint, warmTint, q);
        vec3 toonLit = clamp(uAmbientColor + uDiffuseColor * (0.36 + 0.94 * q), vec3(0.0), vec3(1.45));
        vec3 viewDir = normalize(uCameraPos - vWorldPos);
        float rim = pow(clamp(1.0 - max(dot(n, viewDir), 0.0), 0.0, 1.0), 2.7);
        lit = toonLit * rampTint;
        lit += vec3(0.10, 0.09, 0.07) * rim * uToonRimStrength;
    }

    vec4 color = uBaseColor;
    if (uUseTexture == 1) {
        vec4 texel = texture(uTexture0, vTexCoord);
        // Keep a bit of base albedo to avoid overly dark maps from low-value textures.
        color.rgb *= mix(vec3(1.0), texel.rgb, 0.9);
        color.a *= texel.a;
    }

    vec3 shaded = min(color.rgb * lit * 1.05, vec3(1.0));
    if (uUseFog == 1) {
        float fogRange = max(uFogFar - uFogNear, 0.001);
        float fogFactor = clamp((distance(vWorldPos, uCameraPos) - uFogNear) / fogRange, 0.0, 1.0);
        fogFactor = smoothstep(0.0, 1.0, fogFactor);
        float luma = dot(shaded, vec3(0.299, 0.587, 0.114));
        shaded = mix(shaded, vec3(luma), fogFactor * uDistanceDesatStrength);
        shaded = mix(shaded, uFogColor, fogFactor);
    }

    fragColor = vec4(shaded, color.a);
}
'''

CORE_LINE_VERTEX_SHADER = '''
#version 330 core
layout(location = 0) in vec3 aPosition;
uniform mat4 uViewProj;

void main() {
    gl_Position = uViewProj * vec4(aPosition, 1.0);
}
'''

CORE_LINE_FRAGMENT_SHADER = '''
#version 330 core
uniform vec4 uColor;
out vec4 fragColor;

void main() {
    fragColor = uColor;
}
'''

class GLWindow(glcanvas.GLCanvas):
    def __init__(self,parent):
        self._gl_context = None
        self._gl_context_mode = 'unknown'
        self._gl_info_logged = False
        self._gl_caps = {}
        self._core_profile_stub_mode = False
        self._logged_core_shader_skip = False
        self._logged_core_mesh_skip = False
        self._core_model_program = None
        self._core_model_program_ready = False
        self._core_model_uniforms = {}
        self._core_model_attribs = {}
        self._logged_core_model_program_failure = False
        self._core_line_program = None
        self._core_line_program_ready = False
        self._core_line_uniforms = {}
        self._core_line_vao = 0
        self._core_line_vbo = 0
        self._logged_core_line_program_failure = False
        self._core_line_width_range_checked = False
        self._core_line_width_min = 1.0
        self._core_line_width_max = 1.0
        self._logged_core_line_width_clamp = False
        self._core_instance_vbo = 0
        self._core_instancing_supported = None
        self._core_last_bound_texture0 = None
        self._core_frame_uniforms_set = False
        self._core_frame_ambient = (0.58, 0.58, 0.58)
        self._core_frame_diffuse = (0.72, 0.72, 0.72)
        self._core_frame_fog_enabled = False
        self._core_frame_fog = (0.5, 0.5, 0.5)
        self._core_frame_fog_near = 140.0
        self._core_frame_fog_far = 260.0
        self._core_frame_desat_strength = 0.12
        self._core_frame_use_toon = False
        self._core_frame_toon_bands = 7.0
        self._core_frame_toon_rim = 0.28
        self._max_aniso = None
        self._aniso_enum = 0
        self._gpu_mesh_capabilities_checked = False
        self._vbo_supported = False
        self._vao_supported = False
        self._gpu_mesh_cache_disabled = False

        # Keep compatibility context as the default while fixed-function
        # rendering paths are still present. Core profile can be forced for
        # migration testing via NEVEREDIT_GL_FORCE_CORE=1.
        self._init_gl_canvas(parent)
        self._gl_context = None
        self._create_gl_context()
        self._gpuMeshContextKey = int(id(self._gl_context))
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
        self._pendingWxOverlayText = []
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
        self._pinnedAnimationTrackName = None
        self.animationsEnabled = True
        # Periodic timer-driven redraws are crash-prone across rapid wx
        # destroy/recreate cycles. Keep manual redraws enabled and require
        # explicit opt-in for periodic animation ticks.
        self.enableAnimationTimer = False
        self.animationMode = 'idle'
        self.animationModes = ('idle', 'walk')
        self.animationSpeedByMode = {'idle': 1.0, 'walk': 1.8}
        self.animationTrackByMode = {
            'idle': ('idle', 'pause1', 'pause', 'ready1', 'default'),
            'walk': ('walk', 'walk01', 'walk1', 'run', 'run1'),
        }
        self._animationStartTime = time.time()
        self._animationTimeSeconds = 0.0
        self._destroying = False
        self._animationTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnAnimationTimer, self._animationTimer)
        # Do NOT start timer yet - defer until after GL context is ready
        # self._animationTimer.Start(33)  # Started in InitGL() after GL context ready

        # Initialize shader manager (will compile shaders after GL context ready)
        self.shader_manager = ShaderManager()
        self._shaders_compiled = False

        # Belt-and-suspenders: stop the animation timer whenever the C++ window
        # object is torn down, regardless of *how* destruction was initiated
        # (explicit Destroy(), notebook DeletePage(), parent frame close, etc.).
        # wxEVT_DESTROY fires from wxWindowBase::~wxWindowBase() before C++
        # memory is released, so the timer owner is still valid at this point.
        self.Bind(wx.EVT_WINDOW_DESTROY, self._onWindowDestroy)
        self.Bind(wx.EVT_SHOW, self.OnShow)

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)

    def _init_gl_canvas(self, parent):
        if hasattr(glcanvas, 'GLAttributes'):
            try:
                disp_attrs = glcanvas.GLAttributes()
                disp_attrs.PlatformDefaults().RGBA().DoubleBuffer().Depth(24).Stencil(8).EndList()
                glcanvas.GLCanvas.__init__(self, parent, dispAttrs=disp_attrs, id=-1)
                return
            except Exception as exc:
                logger.warning('Falling back to legacy GLCanvas init: %s', exc)
        glcanvas.GLCanvas.__init__(self, parent, -1)

    def _create_gl_context(self):
        force_core = str(os.environ.get('NEVEREDIT_GL_FORCE_CORE', '')).strip().lower() in (
            '1', 'true', 'yes', 'on'
        )

        if force_core and hasattr(glcanvas, 'GLContextAttrs'):
            try:
                ctx_attrs = glcanvas.GLContextAttrs()
                ctx_attrs.PlatformDefaults().OGLVersion(3, 3).CoreProfile()
                if hasattr(ctx_attrs, 'ForwardCompatible'):
                    ctx_attrs.ForwardCompatible()
                ctx_attrs.EndList()
                self._gl_context = glcanvas.GLContext(self, ctxAttrs=ctx_attrs)
                self._gl_context_mode = 'core-3.3'
                return
            except Exception as exc:
                logger.warning('OpenGL 3.3 core context request failed; falling back to compatibility context: %s', exc)

        if not force_core:
            try:
                # Default path: legacy/compatibility context for fixed-function
                # rendering until the core-profile migration is complete.
                self._gl_context = glcanvas.GLContext(self)
                self._gl_context_mode = 'legacy-default'
                return
            except Exception as exc:
                logger.warning('Default legacy GLContext request failed; retrying with fallback path: %s', exc)

        try:
            self._gl_context = glcanvas.GLContext(self)
            self._gl_context_mode = 'legacy-fallback'
        except Exception as exc:
            logger.error('Failed to create OpenGL context: %s', exc)
            self._gl_context = None
            self._gl_context_mode = 'unavailable'

    def _log_gl_context_info(self):
        if self._gl_info_logged:
            return
        self._gl_info_logged = True

        version = _decode_gl_string(glGetString(GL_VERSION))
        renderer = _decode_gl_string(glGetString(GL_RENDERER))
        vendor = _decode_gl_string(glGetString(GL_VENDOR))
        shading = _decode_gl_string(glGetString(GL_SHADING_LANGUAGE_VERSION))

        major = 0
        minor = 0
        try:
            major = int(glGetIntegerv(GL_MAJOR_VERSION))
            minor = int(glGetIntegerv(GL_MINOR_VERSION))
        except Exception:
            try:
                token = version.split()[0]
                pieces = token.split('.')
                if len(pieces) >= 2:
                    major = int(pieces[0])
                    minor = int(pieces[1])
            except Exception:
                major = 0
                minor = 0

        profile_mask = 0
        is_core_profile = False
        profile_mask_enum = globals().get('GL_CONTEXT_PROFILE_MASK')
        profile_core_bit = globals().get('GL_CONTEXT_CORE_PROFILE_BIT')
        if profile_mask_enum is not None and profile_core_bit is not None:
            try:
                profile_mask = int(glGetIntegerv(profile_mask_enum))
                is_core_profile = bool(profile_mask & int(profile_core_bit))
            except Exception:
                profile_mask = 0

        if self._gl_context_mode == 'core-3.3' and not is_core_profile:
            # Some drivers do not expose profile-mask query reliably.
            is_core_profile = True

        self._gl_caps = {
            'version': version,
            'major': major,
            'minor': minor,
            'vendor': vendor,
            'renderer': renderer,
            'shading_language': shading,
            'profile_mask': profile_mask,
            'is_core_profile': is_core_profile,
            'context_mode': self._gl_context_mode,
        }

        logger.info(
            'OpenGL context mode=%s version=%s core=%s profile_mask=%s renderer=%s vendor=%s GLSL=%s',
            self._gl_context_mode,
            version,
            is_core_profile,
            profile_mask,
            renderer,
            vendor,
            shading,
        )

        if major < 3 or (major == 3 and minor < 3):
            logger.warning('OpenGL version %d.%d detected; 3.3+ target required for full core-profile migration', major, minor)

    def _stopAnimationTimer(self):
        timer = getattr(self, '_animationTimer', None)
        if timer is None:
            return
        try:
            if timer.IsRunning():
                logger.info(f"[GL] Timer.Stop()")
                sys.stdout.flush()
                timer.Stop()
                logger.info(f"[GL] Timer stopped")
                sys.stdout.flush()
        except Exception as e:
            logger.error(f"[GL] Timer.Stop() failed: {e}")
            sys.stdout.flush()
        try:
            logger.info(f"[GL] Unbinding timer...")
            sys.stdout.flush()
            self.Unbind(wx.EVT_TIMER, handler=self.OnAnimationTimer, source=timer)
            logger.info(f"[GL] Timer unbound")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"[GL] Unbind failed: {e}")
            sys.stdout.flush()
        self._animationTimer = None

    def _onWindowDestroy(self, event):
        """Fired by wx from the C++ destructor chain before canvas memory is
        freed.  Stops the animation timer unconditionally so it can never
        dispatch into a freed wxEvtHandler, regardless of how the window was
        torn down (DeletePage, parent close, explicit Destroy(), etc.)."""
        if event.GetEventObject() is self:
            # Set flag FIRST to block any pending callbacks
            self._destroying = True
            self.animationsEnabled = False
            logger.info(f"[GL] Destroy")
            # Then stop the timer immediately
            self._stopAnimationTimer()
        event.Skip()

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
        # Double-check destroying flag before doing anything
        if getattr(self, '_destroying', False):
            return
        if not self.animationsEnabled:
            return
        if self.preprocessing:
            return
        try:
            self.requestRedraw()
        except Exception:
            pass

    @staticmethod
    def _safeDeferredRefresh(window_ref, erase_background):
        try:
            window = window_ref()
            if window is None:
                return
            if getattr(window, '_destroying', False):
                return
            if getattr(window, '_destroyed', False):
                return
            # Extra safety: don't try to refresh if not shown
            if not window.IsShown():
                return
            window.Refresh(erase_background)
        except Exception:
            return

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

    def setAnimationTrackByName(self, track_name):
        """Pin to a specific animation track by name, bypassing mode-based resolution.
        Pass None to resume mode-based selection."""
        self._pinnedAnimationTrackName = track_name if track_name else None
        self._animationStartTime = time.time()
        self._loggedAnimationTrackBindings.clear()
        self.requestRedraw()

    def getAvailableAnimationTrackNames(self, model):
        """Return sorted list of all animation track names from model and its supermodel."""
        if model is None:
            return []
        names = set()
        if hasattr(model, 'getAnimationNames'):
            names.update(model.getAnimationNames())
        super_name = str(getattr(model, 'superModelName', '') or '').strip().lower()
        if super_name and super_name not in ('null', '****'):
            if super_name not in self._superModelCache:
                try:
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
                except Exception:
                    pass
            super_model = self._superModelCache.get(super_name)
            if super_model is not None and hasattr(super_model, 'getAnimationNames'):
                names.update(super_model.getAnimationNames())
        return sorted(names)

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
        # Late paint events can arrive during wx teardown/recreate cycles.
        # Skip immediately for canvases marked as destroying/destroyed.
        if getattr(self, '_destroying', False) or getattr(self, '_destroyed', False):
            return
        dc = wx.PaintDC(self)
        self._pendingWxOverlayText = []
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
        self._drawWxOverlayText(dc)

    def _queueWxOverlayText(self, x, y, text):
        try:
            sx = int(float(x))
            sy = int(float(y))
            self._pendingWxOverlayText.append((sx, sy, str(text)))
        except Exception:
            pass

    def _drawWxOverlayText(self, dc):
        if not self._pendingWxOverlayText:
            return
        try:
            dc.SetTextForeground(wx.Colour(245, 245, 245))
        except Exception:
            pass
        for x, y, text in self._pendingWxOverlayText:
            # GL text helpers use bottom-left origin; wx DC uses top-left.
            wx_y = int(max(0, self.height - y - 12))
            try:
                dc.DrawText(text, int(x), wx_y)
            except Exception:
                continue

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
        if self._isCoreProfileContext():
            return []
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
        if self._isCoreProfileContext():
            self._queueWxOverlayText(x, y, text)
            return
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

    def _checkGpuMeshCapabilities(self):
        if self._gpu_mesh_capabilities_checked:
            return
        self._gpu_mesh_capabilities_checked = True

        self._vbo_supported = bool(globals().get('glGenBuffers')) and \
            bool(globals().get('glBindBuffer')) and \
            bool(globals().get('glBufferData'))
        self._vao_supported = bool(globals().get('glGenVertexArrays')) and \
            bool(globals().get('glBindVertexArray'))

        if not self._vbo_supported:
            logger.warning('VBO APIs unavailable; mesh rendering will use legacy client arrays')
            return

        try:
            probe_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, probe_vbo)
            glBufferData(GL_ARRAY_BUFFER, Numeric.array([0.0, 0.0, 0.0], 'f'), GL_STATIC_DRAW)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glDeleteBuffers(1, [int(probe_vbo)])
        except Exception as exc:
            self._vbo_supported = False
            self._vao_supported = False
            logger.warning('VBO probe failed; disabling GPU mesh cache: %s', exc)
            return

        if self._vao_supported:
            try:
                probe_vao = glGenVertexArrays(1)
                glBindVertexArray(probe_vao)
                glBindVertexArray(0)
                glDeleteVertexArrays(1, [int(probe_vao)])
            except Exception:
                self._vao_supported = False

    def beginCoreDrawFrame(self):
        self._core_last_bound_texture0 = None
        self._core_frame_uniforms_set = False

    def setCoreFrameLightUniforms(self, ambient_rgb=(0.58, 0.58, 0.58), diffuse_rgb=(0.72, 0.72, 0.72)):
        """Update the per-frame ambient/diffuse color state used by the core shader.

        Call once per frame before the draw queue runs.  The actual GL uniform
        uploads are deferred to the first node draw (so the shader program need
        not be bound at call time).
        """
        self._core_frame_ambient = ambient_rgb
        self._core_frame_diffuse = diffuse_rgb
        self._core_frame_uniforms_set = False

    def setCoreFrameFogUniforms(self, enabled=False, fog_rgb=(0.5, 0.5, 0.5), near_distance=140.0, far_distance=260.0, desat_strength=0.12):
        self._core_frame_fog_enabled = bool(enabled)
        self._core_frame_fog = fog_rgb
        self._core_frame_fog_near = float(near_distance)
        self._core_frame_fog_far = max(float(far_distance), float(near_distance) + 0.001)
        self._core_frame_desat_strength = max(0.0, float(desat_strength))
        self._core_frame_uniforms_set = False

    def setCoreFrameToonUniforms(self, enabled=False, bands=7.0, rim_strength=0.28):
        self._core_frame_use_toon = bool(enabled)
        self._core_frame_toon_bands = max(2.0, float(bands))
        self._core_frame_toon_rim = max(0.0, float(rim_strength))
        self._core_frame_uniforms_set = False

    def _probeAnisotropicFiltering(self):
        """Query driver support for anisotropic filtering; result is cached."""
        try:
            from OpenGL.GL.EXT.texture_filter_anisotropic import (
                GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT,
                GL_TEXTURE_MAX_ANISOTROPY_EXT,
            )
            val = glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT)
            self._max_aniso = float(val[0]) if hasattr(val, '__len__') else float(val)
            self._aniso_enum = int(GL_TEXTURE_MAX_ANISOTROPY_EXT)
        except Exception:
            self._max_aniso = 0.0
            self._aniso_enum = 0

    def _checkCoreInstancingSupport(self):
        if self._core_instancing_supported is not None:
            return self._core_instancing_supported
        self._checkGpuMeshCapabilities()
        self._core_instancing_supported = bool(self._vbo_supported and
                                               self._vao_supported and
                                               bool(globals().get('glDrawElementsInstanced')) and
                                               bool(globals().get('glVertexAttribDivisor')))
        if not self._core_instancing_supported:
            logger.info('Core instancing unavailable; duplicate model batches will use non-instanced draws')
        return self._core_instancing_supported

    def _nodeHasDynamicGeometry(self, node):
        return bool(getattr(node, 'isSkinMesh', None) and node.isSkinMesh())

    def _toFloatArray(self, values, width):
        if values is None:
            return None
        try:
            arr = Numeric.array(values, 'f')
            if len(arr) == 0:
                return None
            return arr.reshape((-1, width))
        except Exception:
            return None

    def _toIndexArray(self, indices):
        try:
            raw = Numeric.array(indices)
            if len(raw) == 0:
                return None, None
            raw = raw.reshape((-1,))
            max_idx = int(raw.max())
            if max_idx <= 65535:
                return Numeric.array(raw, 'H'), GL_UNSIGNED_SHORT
            return Numeric.array(raw, 'I'), GL_UNSIGNED_INT
        except Exception:
            return None, None

    def _createArrayBuffer(self, data, usage=GL_STATIC_DRAW):
        if data is None:
            return 0
        buf = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, buf)
        glBufferData(GL_ARRAY_BUFFER, data, usage)
        return int(buf)

    def _createElementBuffer(self, data, usage=GL_STATIC_DRAW):
        if data is None:
            return 0
        buf = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, buf)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, data, usage)
        return int(buf)

    def _bindNodeTexture(self, node, slot):
        tex_attr = 'texture%d' % slot
        if not getattr(node, tex_attr, None):
            glDisable(GL_TEXTURE_2D)
            return False
        gl_name = self._getNodeGLTextureName(node, slot)
        if not gl_name:
            glDisable(GL_TEXTURE_2D)
            return False
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, gl_name)
        return True

    def _bindMeshClientState(self, cache, texcoord_slot=0):
        glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_positions'])
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, ctypes.c_void_p(0))

        if cache.get('vbo_normals'):
            glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_normals'])
            glEnableClientState(GL_NORMAL_ARRAY)
            glNormalPointer(GL_FLOAT, 0, ctypes.c_void_p(0))
        else:
            glDisableClientState(GL_NORMAL_ARRAY)

        tex_vbo = cache.get('vbo_tex0')
        if texcoord_slot == 1 and cache.get('vbo_tex1'):
            tex_vbo = cache.get('vbo_tex1')

        if tex_vbo:
            if 'glClientActiveTexture' in globals() and bool(glClientActiveTexture):
                glClientActiveTexture(GL_TEXTURE0)
            glBindBuffer(GL_ARRAY_BUFFER, tex_vbo)
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glTexCoordPointer(2, GL_FLOAT, 0, ctypes.c_void_p(0))
        else:
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)

    def _ensureNodeGeometryCache(self, node):
        if node is None or not self.isRenderableMeshNode(node):
            return None
        if self._gpu_mesh_cache_disabled:
            return None

        cached = getattr(node, '_gpuMeshCache', None)
        if cached and cached.get('ready'):
            # Node/model objects are shared via resource caches across
            # map windows. A cache built in a different GL context can carry
            # stale VBO/EBO names and crash glDrawElements.
            if cached.get('context_key') != self._gpuMeshContextKey:
                node._gpuMeshCache = None
                node._gpuMeshCacheFailed = False
                cached = None
        if cached and cached.get('ready'):
            return cached
        if getattr(node, '_gpuMeshCacheFailed', False):
            return None
        if self._nodeHasDynamicGeometry(node):
            return None

        self._checkGpuMeshCapabilities()
        if not self._vbo_supported:
            return None

        try:
            positions = self._toFloatArray(getattr(node, 'vertices', None), 3)
            if positions is None:
                return None
            normals = self._toFloatArray(getattr(node, 'normals', None), 3)
            tex0 = self._toFloatArray(getattr(node, 'texture0Vertices', None), 2)
            tex1 = self._toFloatArray(getattr(node, 'texture1Vertices', None), 2)
            weights = self._toFloatArray(getattr(node, 'skinWeights', None), 4)
            bone_ids = self._toFloatArray(getattr(node, 'skinBoneIds', None), 4)

            draw_mode = self.getNodeDrawMode(node)
            index_batches = []
            for index_list in getattr(node, 'vertexIndexLists', []):
                index_data, gl_index_type = self._toIndexArray(index_list)
                if index_data is None:
                    continue
                ebo = self._createElementBuffer(index_data)
                index_batches.append({
                    'ebo': ebo,
                    'count': int(len(index_data)),
                    'index_type': gl_index_type,
                })

            if not index_batches:
                return None

            cache = {
                'ready': True,
                'context_key': self._gpuMeshContextKey,
                'draw_mode': draw_mode,
                'index_batches': index_batches,
                'vbo_positions': self._createArrayBuffer(positions),
                'vbo_normals': self._createArrayBuffer(normals),
                'vbo_tex0': self._createArrayBuffer(tex0),
                'vbo_tex1': self._createArrayBuffer(tex1),
                'vbo_skin_weights': self._createArrayBuffer(weights),
                'vbo_skin_bone_ids': self._createArrayBuffer(bone_ids),
                'vao': 0,
            }

            if self._vao_supported:
                vao = int(glGenVertexArrays(1))
                glBindVertexArray(vao)
                if not self._isCoreProfileContext():
                    self._bindMeshClientState(cache, texcoord_slot=0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
                glBindVertexArray(0)
                cache['vao'] = vao

            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            node._gpuMeshCache = cache
            return cache
        except Exception as exc:
            node._gpuMeshCacheFailed = True
            logger.warning('Failed to build GPU mesh cache for node %s: %s', getattr(node, 'name', '<unnamed>'), exc)
            return None

    def _drawNodeGeometryCached(self, node, texcoord_slot=0):
        if self._isCoreProfileContext():
            return False
        cache = self._ensureNodeGeometryCache(node)
        if not cache:
            return False

        try:
            vao = cache.get('vao', 0)
            if vao:
                glBindVertexArray(vao)
            self._bindMeshClientState(cache, texcoord_slot=texcoord_slot)
            for batch in cache.get('index_batches', []):
                ebo = int(batch.get('ebo', 0) or 0)
                count = int(batch.get('count', 0) or 0)
                if ebo <= 0 or count <= 0:
                    continue
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
                glDrawElements(cache['draw_mode'],
                               count,
                               batch['index_type'],
                               ctypes.c_void_p(0))
            if vao:
                glBindVertexArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            return True
        except Exception as exc:
            node._gpuMeshCacheFailed = True
            logger.warning('GPU mesh draw failed for node %s; falling back: %s', getattr(node, 'name', '<unnamed>'), exc)
            return False

    def _compileCoreModelProgramIfNeeded(self):
        if self._core_model_program_ready:
            return True
        if self._core_model_program is not None:
            return False
        try:
            vert = glCreateShader(GL_VERTEX_SHADER)
            glShaderSource(vert, CORE_MODEL_VERTEX_SHADER)
            glCompileShader(vert)
            if not glGetShaderiv(vert, GL_COMPILE_STATUS):
                logger.error('Core model vertex shader compilation failed: %s', glGetShaderInfoLog(vert).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                self._core_model_program = None
                return False

            frag = glCreateShader(GL_FRAGMENT_SHADER)
            glShaderSource(frag, CORE_MODEL_FRAGMENT_SHADER)
            glCompileShader(frag)
            if not glGetShaderiv(frag, GL_COMPILE_STATUS):
                logger.error('Core model fragment shader compilation failed: %s', glGetShaderInfoLog(frag).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                glDeleteShader(frag)
                self._core_model_program = None
                return False

            program = glCreateProgram()
            glAttachShader(program, vert)
            glAttachShader(program, frag)
            glLinkProgram(program)
            if not glGetProgramiv(program, GL_LINK_STATUS):
                logger.error('Core model shader linking failed: %s', glGetProgramInfoLog(program).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                glDeleteShader(frag)
                glDeleteProgram(program)
                self._core_model_program = None
                return False

            glDeleteShader(vert)
            glDeleteShader(frag)

            self._core_model_program = int(program)
            self._core_model_uniforms = {
                'uViewProj': glGetUniformLocation(self._core_model_program, 'uViewProj'),
                'uModel': glGetUniformLocation(self._core_model_program, 'uModel'),
                'uUseInstancing': glGetUniformLocation(self._core_model_program, 'uUseInstancing'),
                'uBaseColor': glGetUniformLocation(self._core_model_program, 'uBaseColor'),
                'uLightDir': glGetUniformLocation(self._core_model_program, 'uLightDir'),
                'uCameraPos': glGetUniformLocation(self._core_model_program, 'uCameraPos'),
                'uTexture0': glGetUniformLocation(self._core_model_program, 'uTexture0'),
                'uUseTexture': glGetUniformLocation(self._core_model_program, 'uUseTexture'),
                'uAmbientColor': glGetUniformLocation(self._core_model_program, 'uAmbientColor'),
                'uDiffuseColor': glGetUniformLocation(self._core_model_program, 'uDiffuseColor'),
                'uFogColor': glGetUniformLocation(self._core_model_program, 'uFogColor'),
                'uFogNear': glGetUniformLocation(self._core_model_program, 'uFogNear'),
                'uFogFar': glGetUniformLocation(self._core_model_program, 'uFogFar'),
                'uDistanceDesatStrength': glGetUniformLocation(self._core_model_program, 'uDistanceDesatStrength'),
                'uUseFog': glGetUniformLocation(self._core_model_program, 'uUseFog'),
                'uUseToon': glGetUniformLocation(self._core_model_program, 'uUseToon'),
                'uToonBands': glGetUniformLocation(self._core_model_program, 'uToonBands'),
                'uToonRimStrength': glGetUniformLocation(self._core_model_program, 'uToonRimStrength'),
                'uTwoSidedLighting': glGetUniformLocation(self._core_model_program, 'uTwoSidedLighting'),
            }
            self._core_model_attribs = {
                'aPosition': 0,
                'aNormal': 1,
                'aTexCoord': 2,
                'aInstanceCol0': 3,
                'aInstanceCol1': 4,
                'aInstanceCol2': 5,
                'aInstanceCol3': 6,
            }
            self._core_model_program_ready = True
            logger.info('Compiled core-profile model shader program')
            return True
        except Exception as exc:
            if not self._logged_core_model_program_failure:
                logger.warning('Failed to initialize core-profile model program: %s', exc)
                self._logged_core_model_program_failure = True
            self._core_model_program = None
            self._core_model_program_ready = False
            return False

    def _compileCoreLineProgramIfNeeded(self):
        if self._core_line_program_ready:
            return True
        if self._core_line_program is not None:
            return False
        try:
            vert = glCreateShader(GL_VERTEX_SHADER)
            glShaderSource(vert, CORE_LINE_VERTEX_SHADER)
            glCompileShader(vert)
            if not glGetShaderiv(vert, GL_COMPILE_STATUS):
                logger.error('Core line vertex shader compilation failed: %s', glGetShaderInfoLog(vert).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                self._core_line_program = None
                return False

            frag = glCreateShader(GL_FRAGMENT_SHADER)
            glShaderSource(frag, CORE_LINE_FRAGMENT_SHADER)
            glCompileShader(frag)
            if not glGetShaderiv(frag, GL_COMPILE_STATUS):
                logger.error('Core line fragment shader compilation failed: %s', glGetShaderInfoLog(frag).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                glDeleteShader(frag)
                self._core_line_program = None
                return False

            program = glCreateProgram()
            glAttachShader(program, vert)
            glAttachShader(program, frag)
            glLinkProgram(program)
            if not glGetProgramiv(program, GL_LINK_STATUS):
                logger.error('Core line shader linking failed: %s', glGetProgramInfoLog(program).decode('utf-8', 'replace'))
                glDeleteShader(vert)
                glDeleteShader(frag)
                glDeleteProgram(program)
                self._core_line_program = None
                return False

            glDeleteShader(vert)
            glDeleteShader(frag)

            self._core_line_program = int(program)
            self._core_line_uniforms = {
                'uViewProj': glGetUniformLocation(self._core_line_program, 'uViewProj'),
                'uColor': glGetUniformLocation(self._core_line_program, 'uColor'),
            }
            self._core_line_program_ready = True
            logger.info('Compiled core-profile line shader program')
            return True
        except Exception as exc:
            if not self._logged_core_line_program_failure:
                logger.warning('Failed to initialize core-profile line program: %s', exc)
                self._logged_core_line_program_failure = True
            self._core_line_program = None
            self._core_line_program_ready = False
            return False

    def drawCoreLineSegments(self, segments, color=(1.0, 1.0, 1.0, 1.0), line_width=1.0):
        if not segments or not self._isCoreProfileContext():
            return False
        self._checkGpuMeshCapabilities()
        if not self._vbo_supported or not self._vao_supported:
            return False
        if not self._compileCoreLineProgramIfNeeded():
            return False

        points = []
        for seg in segments:
            if not seg or len(seg) != 2:
                continue
            p0, p1 = seg
            points.extend([[float(p0[0]), float(p0[1]), float(p0[2])],
                           [float(p1[0]), float(p1[1]), float(p1[2])]])
        if not points:
            return False

        data = Numeric.array(points, 'f').reshape((-1, 3))
        try:
            if not self._core_line_width_range_checked:
                self._core_line_width_range_checked = True
                try:
                    rng = glGetFloatv(GL_ALIASED_LINE_WIDTH_RANGE)
                    self._core_line_width_min = float(rng[0])
                    self._core_line_width_max = float(rng[1])
                except Exception:
                    self._core_line_width_min = 1.0
                    self._core_line_width_max = 1.0

            if not self._core_line_vao:
                self._core_line_vao = int(glGenVertexArrays(1))
            if not self._core_line_vbo:
                self._core_line_vbo = int(glGenBuffers(1))

            _proj, _view, view_proj = self._buildCameraMatrices()

            glUseProgram(self._core_line_program)
            vp_loc = self._core_line_uniforms.get('uViewProj', -1)
            if vp_loc >= 0:
                glUniformMatrix4fv(vp_loc, 1, GL_FALSE, view_proj.T.flatten())

            col_loc = self._core_line_uniforms.get('uColor', -1)
            if col_loc >= 0:
                glUniform4f(col_loc, float(color[0]), float(color[1]), float(color[2]), float(color[3]))

            glBindVertexArray(self._core_line_vao)
            glBindBuffer(GL_ARRAY_BUFFER, self._core_line_vbo)
            glBufferData(GL_ARRAY_BUFFER, data, GL_DYNAMIC_DRAW)

            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

            requested_width = max(1.0, float(line_width))
            safe_width = max(self._core_line_width_min,
                             min(self._core_line_width_max, requested_width))
            if abs(safe_width - requested_width) > 1.0e-4 and not self._logged_core_line_width_clamp:
                logger.warning('Core line width %.2f unsupported; clamping to %.2f', requested_width, safe_width)
                self._logged_core_line_width_clamp = True
            glLineWidth(float(safe_width))
            glDrawArrays(GL_LINES, 0, int(len(data)))

            glLineWidth(1.0)
            glDisableVertexAttribArray(0)
            glBindVertexArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glUseProgram(0)
            return True
        except Exception as exc:
            logger.warning('Core line draw failed: %s', exc)
            try:
                glLineWidth(1.0)
                glBindVertexArray(0)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                glUseProgram(0)
            except Exception:
                pass
            return False

    def _normalizeVec3(self, v):
        vec = Numeric.array(v, 'f').reshape((3,))
        length = math.sqrt(float(Numeric.dot(vec, vec)))
        if length <= 1.0e-8:
            return Numeric.array([0.0, 0.0, 1.0], 'f')
        return vec / length

    def _makePerspectiveMatrix(self, fov_degrees, aspect, near_clip, far_clip):
        f = 1.0 / math.tan(math.radians(float(fov_degrees)) * 0.5)
        m = Numeric.zeros((4, 4), 'f')
        m[0, 0] = f / max(float(aspect), 1.0e-6)
        m[1, 1] = f
        m[2, 2] = (far_clip + near_clip) / (near_clip - far_clip)
        m[2, 3] = (2.0 * far_clip * near_clip) / (near_clip - far_clip)
        m[3, 2] = -1.0
        return m

    def _getCameraClipPlanes(self):
        near_clip = max(0.25, min(self.minZoom / 8.0, 2.0))
        scene_extent = max(float(self.getBaseWidth()), float(self.getBaseHeight()))
        far_clip = max(self.maxZoom + 32.0, scene_extent * 1.8 + 64.0)
        return near_clip, far_clip

    def _buildCameraMatrices(self):
        aspect = float(self.width) / max(float(self.height), 1.0)
        near_clip, far_clip = self._getCameraClipPlanes()
        proj = self._makePerspectiveMatrix(45.0, aspect, near_clip, far_clip)
        eye = Numeric.array([self.viewX, self.viewY, self.viewZ], 'f')
        target = Numeric.array([self.lookingAtX, self.lookingAtY, self.lookingAtZ], 'f')
        view = self._makeLookAtMatrix(eye, target, Numeric.array([0.0, 0.0, 1.0], 'f'))
        view_proj = Numeric.dot(proj, view)
        return proj, view, view_proj

    def _unprojectWithViewProjectionInverse(self, x, y, depth01, inv_view_proj):
        # x,y are expected in window coordinates with origin at bottom-left.
        nx = (2.0 * float(x) / max(float(self.width), 1.0)) - 1.0
        ny = (2.0 * float(y) / max(float(self.height), 1.0)) - 1.0
        nz = (2.0 * float(depth01)) - 1.0
        clip = Numeric.array([nx, ny, nz, 1.0], 'f')
        world = Numeric.dot(inv_view_proj, clip)
        if abs(float(world[3])) > 1.0e-8:
            world = world / float(world[3])
        return world[:3]

    def _projectWithViewProjection(self, point3, view_proj):
        world = Numeric.array([float(point3[0]), float(point3[1]), float(point3[2]), 1.0], 'f')
        clip = Numeric.dot(view_proj, world)
        w = float(clip[3])
        if abs(w) <= 1.0e-8:
            return 0.0, 0.0, 1.0
        ndc = clip / w
        sx = (float(ndc[0]) * 0.5 + 0.5) * max(float(self.width), 1.0)
        sy = (float(ndc[1]) * 0.5 + 0.5) * max(float(self.height), 1.0)
        sz = float(ndc[2]) * 0.5 + 0.5
        return sx, sy, sz

    def _makeLookAtMatrix(self, eye, target, up):
        eye = Numeric.array(eye, 'f').reshape((3,))
        target = Numeric.array(target, 'f').reshape((3,))
        up = self._normalizeVec3(up)

        forward = self._normalizeVec3(target - eye)
        side = self._normalizeVec3(Numeric.cross(forward, up))
        true_up = Numeric.cross(side, forward)

        m = Numeric.identity(4, 'f')
        m[0, 0:3] = side
        m[1, 0:3] = true_up
        m[2, 0:3] = -forward
        m[0, 3] = -float(Numeric.dot(side, eye))
        m[1, 3] = -float(Numeric.dot(true_up, eye))
        m[2, 3] = float(Numeric.dot(forward, eye))
        return m

    def _getNodeLocalTransformMatrix(self, node, animationTime=None):
        transform = Numeric.identity(4, 'f')
        controller_node = self._getActiveControllerNode(node)
        controller_map = getattr(controller_node, 'controllers', None)

        if animationTime is not None and hasattr(node, 'getAnimatedPositionFromMap'):
            p = node.getAnimatedPositionFromMap(controller_map, animationTime)
        else:
            p = getattr(node, 'position', None)
        if p is not None:
            transform[0, 3] = float(p[0])
            transform[1, 3] = float(p[1])
            transform[2, 3] = float(p[2])

        if animationTime is not None and hasattr(node, 'getAnimatedOrientationMatrixFromMap'):
            orientation = node.getAnimatedOrientationMatrixFromMap(controller_map, animationTime)
        else:
            orientation = getattr(node, 'orientation', None)
        if orientation is not None:
            ori = Numeric.array(orientation, 'f')
            if ori.size == 9:
                ori = ori.reshape((3, 3))
                ori4 = Numeric.identity(4, 'f')
                ori4[:3, :3] = ori
                ori = ori4
            else:
                ori = ori.reshape((4, 4))
            transform = Numeric.dot(transform, ori)

        if animationTime is not None and hasattr(node, 'getAnimatedScaleFromMap'):
            s = node.getAnimatedScaleFromMap(controller_map, animationTime)
        else:
            s = getattr(node, 'scale', None)
        if s:
            scale_mat = Numeric.identity(4, 'f')
            scale_mat[0, 0] = float(s)
            scale_mat[1, 1] = float(s)
            scale_mat[2, 2] = float(s)
            transform = Numeric.dot(transform, scale_mat)

        return transform

    def _drawNodeGeometryCore(self, node, world_matrix, view_projection_matrix):
        if node is None or self._nodeHasDynamicGeometry(node):
            return False
        if not self._compileCoreModelProgramIfNeeded():
            return False

        cache = self._ensureNodeGeometryCache(node)
        if not cache:
            return False

        try:
            vao = int(cache.get('vao', 0) or 0)
            if vao == 0 and self._vao_supported:
                vao = int(glGenVertexArrays(1))
                cache['vao'] = vao
            if vao == 0:
                logger.warning('Core mesh draw skipped for node %s: VAO unavailable in core profile', getattr(node, 'name', '<unnamed>'))
                return False

            glBindVertexArray(vao)
            glUseProgram(self._core_model_program)
            loc = self._core_model_uniforms.get('uViewProj', -1)
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, view_projection_matrix.T.flatten())
            loc = self._core_model_uniforms.get('uModel', -1)
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, world_matrix.T.flatten())
            loc = self._core_model_uniforms.get('uUseInstancing', -1)
            if loc >= 0:
                glUniform1i(loc, 0)

            diffuse = getattr(node, 'diffuseColour', (0.8, 0.8, 0.8, 1.0))
            if len(diffuse) < 4:
                diffuse = list(diffuse[:3]) + [1.0]
            loc = self._core_model_uniforms.get('uBaseColor', -1)
            if loc >= 0:
                glUniform4f(loc, float(diffuse[0]), float(diffuse[1]), float(diffuse[2]), float(diffuse[3]))
            if not self._core_frame_uniforms_set:
                camera_pos = Numeric.array([float(self.viewX), float(self.viewY), float(self.viewZ)], 'f')
                loc = self._core_model_uniforms.get('uLightDir', -1)
                if loc >= 0:
                    lx = float(self.viewX - self.lookingAtX)
                    ly = float(self.viewY - self.lookingAtY)
                    lz = float(self.viewZ - self.lookingAtZ)
                    glUniform3f(loc, lx, ly, lz)
                loc = self._core_model_uniforms.get('uCameraPos', -1)
                if loc >= 0:
                    glUniform3f(loc, float(camera_pos[0]), float(camera_pos[1]), float(camera_pos[2]))
                loc = self._core_model_uniforms.get('uAmbientColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_ambient)
                loc = self._core_model_uniforms.get('uDiffuseColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_diffuse)
                loc = self._core_model_uniforms.get('uFogColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_fog)
                loc = self._core_model_uniforms.get('uFogNear', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_fog_near)
                loc = self._core_model_uniforms.get('uFogFar', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_fog_far)
                loc = self._core_model_uniforms.get('uDistanceDesatStrength', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_desat_strength)
                loc = self._core_model_uniforms.get('uUseFog', -1)
                if loc >= 0:
                    glUniform1i(loc, int(self._core_frame_fog_enabled))
                loc = self._core_model_uniforms.get('uUseToon', -1)
                if loc >= 0:
                    glUniform1i(loc, int(self._core_frame_use_toon))
                loc = self._core_model_uniforms.get('uToonBands', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_toon_bands)
                loc = self._core_model_uniforms.get('uToonRimStrength', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_toon_rim)
                self._core_frame_uniforms_set = True
            loc = self._core_model_uniforms.get('uTwoSidedLighting', -1)
            if loc >= 0:
                glUniform1i(loc, 1)

            use_texture = 0
            if getattr(node, 'texture0', None) and cache.get('vbo_tex0'):
                gl_tex0 = self._getNodeGLTextureName(node, 0)
                if gl_tex0:
                    glActiveTexture(GL_TEXTURE0)
                    if self._core_last_bound_texture0 != int(gl_tex0):
                        glBindTexture(GL_TEXTURE_2D, gl_tex0)
                        self._core_last_bound_texture0 = int(gl_tex0)
                    use_texture = 1
            loc = self._core_model_uniforms.get('uTexture0', -1)
            if loc >= 0:
                glUniform1i(loc, 0)
            loc = self._core_model_uniforms.get('uUseTexture', -1)
            if loc >= 0:
                glUniform1i(loc, int(use_texture))

            pos_loc = self._core_model_attribs['aPosition']
            glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_positions'])
            glEnableVertexAttribArray(pos_loc)
            glVertexAttribPointer(pos_loc, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

            normal_loc = self._core_model_attribs['aNormal']
            if cache.get('vbo_normals'):
                glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_normals'])
                glEnableVertexAttribArray(normal_loc)
                glVertexAttribPointer(normal_loc, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
            else:
                glDisableVertexAttribArray(normal_loc)
                glVertexAttrib3f(normal_loc, 0.0, 0.0, 1.0)

            tex_loc = self._core_model_attribs['aTexCoord']
            if use_texture and cache.get('vbo_tex0'):
                glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_tex0'])
                glEnableVertexAttribArray(tex_loc)
                glVertexAttribPointer(tex_loc, 2, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
            else:
                glDisableVertexAttribArray(tex_loc)
                glVertexAttrib2f(tex_loc, 0.0, 0.0)

            for batch in cache.get('index_batches', []):
                ebo = int(batch.get('ebo', 0) or 0)
                count = int(batch.get('count', 0) or 0)
                if ebo <= 0 or count <= 0:
                    continue
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
                glDrawElements(cache['draw_mode'], count, batch['index_type'], ctypes.c_void_p(0))

            glDisableVertexAttribArray(pos_loc)
            glDisableVertexAttribArray(normal_loc)
            glDisableVertexAttribArray(tex_loc)
            glDisableVertexAttribArray(self._core_model_attribs.get('aInstanceCol0', 3))
            glDisableVertexAttribArray(self._core_model_attribs.get('aInstanceCol1', 4))
            glDisableVertexAttribArray(self._core_model_attribs.get('aInstanceCol2', 5))
            glDisableVertexAttribArray(self._core_model_attribs.get('aInstanceCol3', 6))
            glBindVertexArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            glUseProgram(0)
            return True
        except Exception as exc:
            logger.warning('Core mesh draw failed for node %s: %s', getattr(node, 'name', '<unnamed>'), exc)
            try:
                glUseProgram(0)
                glBindVertexArray(0)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            except Exception:
                pass
            return False

    def _drawNodeGeometryCoreInstanced(self, node, world_matrices, view_projection_matrix):
        if node is None or self._nodeHasDynamicGeometry(node):
            return False
        if not world_matrices or len(world_matrices) < 2:
            return False
        if not self._checkCoreInstancingSupport():
            return False
        if not self._compileCoreModelProgramIfNeeded():
            return False

        cache = self._ensureNodeGeometryCache(node)
        if not cache:
            return False

        try:
            vao = int(cache.get('vao', 0) or 0)
            if vao == 0:
                return False

            if not self._core_instance_vbo:
                self._core_instance_vbo = int(glGenBuffers(1))

            instance_count = len(world_matrices)
            packed = Numeric.zeros((instance_count, 4, 4), 'f')
            for i, matrix in enumerate(world_matrices):
                packed[i] = Numeric.array(matrix, 'f').reshape((4, 4)).T
            packed = packed.reshape((instance_count, 16))

            glBindVertexArray(vao)
            glUseProgram(self._core_model_program)

            loc = self._core_model_uniforms.get('uViewProj', -1)
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, view_projection_matrix.T.flatten())
            loc = self._core_model_uniforms.get('uModel', -1)
            if loc >= 0:
                glUniformMatrix4fv(loc, 1, GL_FALSE, Numeric.identity(4, 'f').T.flatten())
            loc = self._core_model_uniforms.get('uUseInstancing', -1)
            if loc >= 0:
                glUniform1i(loc, 1)

            diffuse = getattr(node, 'diffuseColour', (0.8, 0.8, 0.8, 1.0))
            if len(diffuse) < 4:
                diffuse = list(diffuse[:3]) + [1.0]
            loc = self._core_model_uniforms.get('uBaseColor', -1)
            if loc >= 0:
                glUniform4f(loc, float(diffuse[0]), float(diffuse[1]), float(diffuse[2]), float(diffuse[3]))

            if not self._core_frame_uniforms_set:
                camera_pos = Numeric.array([float(self.viewX), float(self.viewY), float(self.viewZ)], 'f')
                light_dir = self._normalizeVec3(camera_pos - Numeric.array([float(self.lookingAtX), float(self.lookingAtY), float(self.lookingAtZ)], 'f'))
                loc = self._core_model_uniforms.get('uLightDir', -1)
                if loc >= 0:
                    glUniform3f(loc, float(light_dir[0]), float(light_dir[1]), float(light_dir[2]))
                loc = self._core_model_uniforms.get('uCameraPos', -1)
                if loc >= 0:
                    glUniform3f(loc, float(camera_pos[0]), float(camera_pos[1]), float(camera_pos[2]))
                loc = self._core_model_uniforms.get('uAmbientColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_ambient)
                loc = self._core_model_uniforms.get('uDiffuseColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_diffuse)
                loc = self._core_model_uniforms.get('uFogColor', -1)
                if loc >= 0:
                    glUniform3f(loc, *self._core_frame_fog)
                loc = self._core_model_uniforms.get('uFogNear', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_fog_near)
                loc = self._core_model_uniforms.get('uFogFar', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_fog_far)
                loc = self._core_model_uniforms.get('uDistanceDesatStrength', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_desat_strength)
                loc = self._core_model_uniforms.get('uUseFog', -1)
                if loc >= 0:
                    glUniform1i(loc, int(self._core_frame_fog_enabled))
                loc = self._core_model_uniforms.get('uUseToon', -1)
                if loc >= 0:
                    glUniform1i(loc, int(self._core_frame_use_toon))
                loc = self._core_model_uniforms.get('uToonBands', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_toon_bands)
                loc = self._core_model_uniforms.get('uToonRimStrength', -1)
                if loc >= 0:
                    glUniform1f(loc, self._core_frame_toon_rim)
                self._core_frame_uniforms_set = True
            loc = self._core_model_uniforms.get('uTwoSidedLighting', -1)
            if loc >= 0:
                glUniform1i(loc, 1)

            use_texture = 0
            if getattr(node, 'texture0', None) and cache.get('vbo_tex0'):
                gl_tex0 = self._getNodeGLTextureName(node, 0)
                if gl_tex0:
                    glActiveTexture(GL_TEXTURE0)
                    if self._core_last_bound_texture0 != int(gl_tex0):
                        glBindTexture(GL_TEXTURE_2D, gl_tex0)
                        self._core_last_bound_texture0 = int(gl_tex0)
                    use_texture = 1
            loc = self._core_model_uniforms.get('uTexture0', -1)
            if loc >= 0:
                glUniform1i(loc, 0)
            loc = self._core_model_uniforms.get('uUseTexture', -1)
            if loc >= 0:
                glUniform1i(loc, int(use_texture))

            pos_loc = self._core_model_attribs['aPosition']
            glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_positions'])
            glEnableVertexAttribArray(pos_loc)
            glVertexAttribPointer(pos_loc, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

            normal_loc = self._core_model_attribs['aNormal']
            if cache.get('vbo_normals'):
                glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_normals'])
                glEnableVertexAttribArray(normal_loc)
                glVertexAttribPointer(normal_loc, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
            else:
                glDisableVertexAttribArray(normal_loc)
                glVertexAttrib3f(normal_loc, 0.0, 0.0, 1.0)

            tex_loc = self._core_model_attribs['aTexCoord']
            if use_texture and cache.get('vbo_tex0'):
                glBindBuffer(GL_ARRAY_BUFFER, cache['vbo_tex0'])
                glEnableVertexAttribArray(tex_loc)
                glVertexAttribPointer(tex_loc, 2, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))
            else:
                glDisableVertexAttribArray(tex_loc)
                glVertexAttrib2f(tex_loc, 0.0, 0.0)

            glBindBuffer(GL_ARRAY_BUFFER, self._core_instance_vbo)
            glBufferData(GL_ARRAY_BUFFER, packed, GL_DYNAMIC_DRAW)

            stride = 16 * 4
            c0 = self._core_model_attribs.get('aInstanceCol0', 3)
            c1 = self._core_model_attribs.get('aInstanceCol1', 4)
            c2 = self._core_model_attribs.get('aInstanceCol2', 5)
            c3 = self._core_model_attribs.get('aInstanceCol3', 6)
            glEnableVertexAttribArray(c0)
            glVertexAttribPointer(c0, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
            glVertexAttribDivisor(c0, 1)
            glEnableVertexAttribArray(c1)
            glVertexAttribPointer(c1, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(16))
            glVertexAttribDivisor(c1, 1)
            glEnableVertexAttribArray(c2)
            glVertexAttribPointer(c2, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(32))
            glVertexAttribDivisor(c2, 1)
            glEnableVertexAttribArray(c3)
            glVertexAttribPointer(c3, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(48))
            glVertexAttribDivisor(c3, 1)

            for batch in cache.get('index_batches', []):
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, batch['ebo'])
                glDrawElementsInstanced(cache['draw_mode'],
                                        batch['count'],
                                        batch['index_type'],
                                        ctypes.c_void_p(0),
                                        int(instance_count))

            glVertexAttribDivisor(c0, 0)
            glVertexAttribDivisor(c1, 0)
            glVertexAttribDivisor(c2, 0)
            glVertexAttribDivisor(c3, 0)
            glDisableVertexAttribArray(c0)
            glDisableVertexAttribArray(c1)
            glDisableVertexAttribArray(c2)
            glDisableVertexAttribArray(c3)
            glDisableVertexAttribArray(pos_loc)
            glDisableVertexAttribArray(normal_loc)
            glDisableVertexAttribArray(tex_loc)
            glBindVertexArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
            glUseProgram(0)
            return True
        except Exception as exc:
            logger.warning('Core instanced draw failed for node %s: %s', getattr(node, 'name', '<unnamed>'), exc)
            try:
                glBindVertexArray(0)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
                glUseProgram(0)
            except Exception:
                pass
            return False

    def _drawNodeTreeCore(self, node, view_projection_matrix, parent_matrix):
        if node is None:
            return False

        local = self._getNodeLocalTransformMatrix(node, self._animationTimeSeconds)
        world = Numeric.dot(parent_matrix, local)
        drew = False

        if self.isRenderableMeshNode(node):
            drew = self._drawNodeGeometryCore(node, world, view_projection_matrix)

        for child in getattr(node, 'children', []):
            drew = self._drawNodeTreeCore(child, view_projection_matrix, world) or drew

        return drew

    def drawModelCorePath(self, root_node, base_translate=None, base_matrix=None):
        if root_node is None:
            return False
        self._checkGpuMeshCapabilities()
        if not self._vbo_supported:
            return False
        if not self._compileCoreModelProgramIfNeeded():
            return False

        _proj, _view, view_proj = self._buildCameraMatrices()

        if base_matrix is not None:
            base = Numeric.array(base_matrix, 'f').reshape((4, 4))
        else:
            base = Numeric.identity(4, 'f')
            if base_translate is not None:
                base[0, 3] = float(base_translate[0])
                base[1, 3] = float(base_translate[1])
                base[2, 3] = float(base_translate[2])

        previous_animation_nodes = self._activeAnimationNodes
        owner_model = getattr(root_node, '_ownerModel', None)
        self._activeAnimationNodes = self._resolveAnimationNodesForModel(owner_model)
        try:
            return self._drawNodeTreeCore(root_node, view_proj, base)
        finally:
            self._activeAnimationNodes = previous_animation_nodes

    def drawModelCoreInstancedPath(self, root_node, base_matrices):
        if root_node is None or not base_matrices:
            return False
        if len(base_matrices) == 1:
            return self.drawModelCorePath(root_node, base_matrix=base_matrices[0])
        if getattr(root_node, 'children', None):
            return False
        if not self.isRenderableMeshNode(root_node):
            return False

        self._checkGpuMeshCapabilities()
        if not self._vbo_supported:
            return False
        if not self._compileCoreModelProgramIfNeeded():
            return False

        _proj, _view, view_proj = self._buildCameraMatrices()
        previous_animation_nodes = self._activeAnimationNodes
        owner_model = getattr(root_node, '_ownerModel', None)
        self._activeAnimationNodes = self._resolveAnimationNodesForModel(owner_model)
        try:
            return self._drawNodeGeometryCoreInstanced(root_node, base_matrices, view_proj)
        finally:
            self._activeAnimationNodes = previous_animation_nodes

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
        self._ensureNodeRenderData(node)
                    
        for c in node.children:
            self.preprocessNodesHelper(c,tag,level+1,model)

    def _ensureNodeRenderData(self,node):
        if node is None:
            return
        if self.isRenderableMeshNode(node):
            self._ensureNodeTextureGL(node,0)
            self._ensureNodeTextureGL(node,1)
            self._ensureNodeGeometryCache(node)

    # Deprecated compatibility alias during migration; call sites should use
    # _ensureNodeRenderData directly.
    def _ensureNodeDisplayLists(self,node):
        self._ensureNodeRenderData(node)

    def _resolveAnimationNodesForModel(self, model):
        if model is None or not self.animationsEnabled:
            return None
        if not hasattr(model, 'resolveAnimationTrack'):
            return None
        if self._pinnedAnimationTrackName:
            preferred = (self._pinnedAnimationTrackName,)
        else:
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
            if self._max_aniso is None:
                self._probeAnisotropicFiltering()
            try:
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, image)
                glGenerateMipmap(GL_TEXTURE_2D)
            except Exception:
                gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RGBA, w, h, GL_RGBA, GL_UNSIGNED_BYTE, image)
            if self._aniso_enum and self._max_aniso and self._max_aniso > 1.0:
                try:
                    glTexParameterf(GL_TEXTURE_2D, self._aniso_enum, min(self._max_aniso, 8.0))
                except Exception:
                    pass
            self.textureStore[store_key] = gl_name
        setattr(node, gl_attr, self.textureStore[store_key])

    def _getNodeGLTextureName(self,node,slot):
        gl_attr = 'glTexture%dName' % slot
        gl_name = getattr(node, gl_attr, None)
        if gl_name:
            return gl_name

        legacy_gl_attr = 'gltexture%dname' % slot
        gl_name = getattr(node, legacy_gl_attr, None)
        if gl_name:
            return gl_name

        tex_attr = 'texture%d' % slot
        if getattr(node, tex_attr, None) is None:
            return None

        # Lazily create GL texture handles for nodes parsed with valid
        # texture metadata but without precomputed glTexture*Name attributes.
        try:
            self._ensureNodeTextureGL(node, slot)
        except Exception:
            return None
        return getattr(node, gl_attr, None) or getattr(node, legacy_gl_attr, None)

    def mergeBoxes(self,boxResult,boxAdd):
        for i in range(3):
            boxResult[0][i] = min(boxResult[0][i],boxAdd[0][i])
            boxResult[1][i] = max(boxResult[1][i],boxAdd[1][i])
        return boxResult
    
    def calculateNodeTreeBoundingBoxHelper(self,node,bb):
        glPushMatrix()
        #first, position transform to this node's space
        self.processControllers(node)
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
            gl_tex0 = self._getNodeGLTextureName(node, 0)
            if not gl_tex0:
                glDisable(GL_TEXTURE_2D)
                glDisableClientState(GL_TEXTURE_COORD_ARRAY)
                return False
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D,gl_tex0)
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
            gl_tex0 = self._getNodeGLTextureName(node, 0)
            if not gl_tex0:
                glDisable(GL_TEXTURE_2D)
                return False
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D,gl_tex0)
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
        
    def processNode(self,node,boxOnly=False,preferImmediate=False):
        if boxOnly and node.boundingBox[1][0]:
            self.renderBox(node.boundingBox)
            return True
        self._ensureNodeRenderData(node)
        if hasattr(self, 'shader_manager') and self._shaders_compiled:
            self.shader_manager.set_material_state(
                ambient=getattr(node, 'ambientColour', (0.2, 0.2, 0.2)),
                diffuse=getattr(node, 'diffuseColour', (0.8, 0.8, 0.8)),
                specular=getattr(node, 'specularColour', (1.0, 1.0, 1.0)),
                shininess=getattr(node, 'shininess', 32.0),
            )
            self.shader_manager.sync_matrix_state_from_gl()
            self.shader_manager.use_current_shader()
        try:
            self.processColours(node)
            textured = False
            used_cached = False
            if not preferImmediate and not self._nodeHasDynamicGeometry(node):
                textured = self._bindNodeTexture(node, 0)
                used_cached = self._drawNodeGeometryCached(node, texcoord_slot=0)
            if not used_cached:
                textured = self.processTextures(node)
                if preferImmediate or self._nodeHasDynamicGeometry(node):
                    self.processVerticesImmediate(node,withTextures=textured)
                else:
                    self.processVertices(node)
            self.drawSecondaryTexturePass(node,forceImmediate=(preferImmediate or self._nodeHasDynamicGeometry(node)))
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
            self.processColours(node)
            self.processVerticesImmediate(node,withTextures=textured)
            self.drawSecondaryTexturePass(node,forceImmediate=True)
        return True

    def drawSecondaryTexturePass(self,node,forceImmediate=False):
        if node is None or not getattr(node, 'texture1', None):
            return
        gl_tex1 = self._getNodeGLTextureName(node, 1)
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
                if self._drawNodeGeometryCached(node, texcoord_slot=1):
                    used_client_path = True
                else:
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
                drewSomething = self.processNode(node,boxOnly,preferImmediate=selected)
                if selected:
                    glPushMatrix()
                    try:
                        glScalef(1.2,1.2,1.2)
                        #glBlendFunc(GL_ONE,GL_ONE)
                        glColor4f(0.1,0.9,0.1,0.6)
                        glDisable(GL_LIGHTING)
                        #self.renderBox(self.model.boundingBox)
                        self.processNode(node,False,preferImmediate=True)
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
        
    def _extractFrustumPlanesFromClipMatrix(self, clip):
        planes = [
            clip[:,3] - clip[:,0],  # right
            clip[:,3] + clip[:,0],  # left
            clip[:,3] + clip[:,1],  # bottom
            clip[:,3] - clip[:,1],  # top
            clip[:,3] - clip[:,2],  # far
            clip[:,3] + clip[:,2],  # near
        ]
        planes = self.fixMatrixToNumPy(planes)
        for plane in planes:
            normal_len = math.sqrt(max(1.0e-12, float(Numeric.dot(plane[:3], plane[:3]))))
            plane /= normal_len
        return planes

    def updateFrustumFromViewProjection(self, view_projection_matrix):
        clip = Numeric.array(view_projection_matrix, 'd').reshape((4, 4))
        self.frustum = self._extractFrustumPlanesFromClipMatrix(clip)
        return self.frustum

    def computeFrustum(self):
        # Legacy visibility path uses eye-space centres; projection-only planes
        # remain compatible while still adding near/far clipping planes.
        clip = Numeric.array(glGetDoublev(GL_PROJECTION_MATRIX))
        self.frustum = self._extractFrustumPlanesFromClipMatrix(clip)
            
    def pointInFrustum(self,p):
        try:
            x = float(p[0,0])
            y = float(p[0,1])
            z = float(p[0,2])
        except Exception:
            x = float(p[0])
            y = float(p[1])
            z = float(p[2])
        for plane in self.frustum:
            if x * plane[0] + y * plane[1] + z * plane[2] + plane[3] <= 0.0:
                return False
        return True

    def sphereInFrustum(self,centre,radius):
        if hasattr(centre, 'shape') and len(centre.shape) >= 2:
            x = float(centre[0,0])
            y = float(centre[0,1])
            z = float(centre[0,2])
        else:
            x = float(centre[0])
            y = float(centre[1])
            z = float(centre[2])
        radius = float(radius)
        for plane in self.frustum:
            if x * plane[0] + y * plane[1] + z * plane[2] + plane[3] < -radius:
                return False
        return True

    def sphereInFrustumWorld(self, centre, radius):
        x = float(centre[0])
        y = float(centre[1])
        z = float(centre[2])
        radius = float(radius)
        for plane in self.frustum:
            if x * plane[0] + y * plane[1] + z * plane[2] + plane[3] < -radius:
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

    def _isCoreProfileContext(self):
        if self._gl_caps:
            return bool(self._gl_caps.get('is_core_profile', False))
        return self._gl_context_mode == 'core-3.3'

    def _compileShadersIfNeeded(self):
        if self._shaders_compiled:
            return
        if self._isCoreProfileContext():
            if not self._compileCoreModelProgramIfNeeded() and not self._logged_core_shader_skip:
                logger.warning('Core profile mode: core-model shader unavailable; keeping stub fallback active')
                self._logged_core_shader_skip = True
            self._shaders_compiled = False
            return
        try:
            self.shader_manager.compile_all()
            self._shaders_compiled = True
            logger.info('Shaders compiled successfully')
        except Exception as e:
            logger.warning('Failed to compile shaders: %s', e)
            self._shaders_compiled = False

    def _initGLLegacyState(self):
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

    def _initGLCoreSafeState(self):
        # Core profile path avoids fixed-function state that triggers INVALID_OPERATION.
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClearDepth(1.0)
        glDepthFunc(GL_LESS)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_DITHER)
        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glViewport(0, 0, self.width, self.height)
        logger.warning('Core profile initialization running in compatibility-stub mode until fixed-function rendering is fully removed')
               
               
               
    def InitGL(self,Width, Height):
        '''A general OpenGL initialization function.
        Sets all of the initial parameters. '''
        self.width = Width
        self.height = Height
        self._log_gl_context_info()
        if self._isCoreProfileContext():
            self._core_profile_stub_mode = True
            self._initGLCoreSafeState()
            self._compileShadersIfNeeded()
        else:
            self._core_profile_stub_mode = False
            self._initGLLegacyState()
            self._compileShadersIfNeeded()
            self.SetupProjection()
        # Defer animation timer start - don't start until window is shown
        # This ensures GL context, shaders, and window state are fully ready
    ##self.wireOn()
#        self.recomputeCamera()

    def OnShow(self, event):
        """Called when window is shown - start animations here."""
        try:
            if (event.IsShown() and self.enableAnimationTimer and
                    self.animationsEnabled and
                    not self._animationTimer.IsRunning()):
                self._animationTimer.Start(33)
        except Exception:
            pass
        event.Skip()

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
        if self._isCoreProfileContext():
            if not pick:
                self.recomputeFrustum = True
            return
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
        # Absolute zero-tolerance for drawing during destruction
        if getattr(self, '_destroying', False):
            return
        if not getattr(self, 'animationsEnabled', False):
            return
        if self.redrawRequested:
            return
        else:
            self.redrawRequested = True
            # wxPython Phoenix does not accept an int constructor arg for PaintEvent.
            # Refresh schedules a paint event on the UI loop. Use a weakref so
            # the deferred callback cannot dispatch into a deleted GLCanvas.
            try:
                wx.CallAfter(GLWindow._safeDeferredRefresh, weakref.ref(self), False)
            except Exception:
                pass

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
