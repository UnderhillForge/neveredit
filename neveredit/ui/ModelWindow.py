'''
A class to display a single NWN 3D model.
'''
import sys
import logging

import wx
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *

from neveredit.ui.GLWindow import GLWindow
from neveredit.file import MDLFile
from neveredit.game.ChangeNotification import VisualChangeListener
from neveredit.util import neverglobals

logger = logging.getLogger('neveredit.ui')

class ModelWindow(GLWindow, VisualChangeListener):
    __doc__ = globals()['__doc__']
    def __init__(self,parent):
        GLWindow.__init__(self, parent)
        self.model = None
        self.lookingAtZ = 1.5
        neverglobals.getResourceManager().addVisualChangeListener(self)

    def visualChanged(self,v):
        self.setModel(v.getModel(copy=True))
        
    def setModel(self,m):
        self.model = m
        self.clearCache()
        if not m:
            return
        self.lookingAtX = self.getBaseWidth()/2.0
        self.lookingAtY = self.getBaseHeight()/2.0
        self.lookingAtZ = self.model.getRootNode().boundingBox[1][2]/2.0
        self.preprocessed = False
        self.requestRedraw()
        
    def DrawGLScene(self):
        GLWindow.DrawGLScene(self)
        self.makeCurrent()
        if not self.model or not self.preprocessed:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self.SwapBuffers()
            return

        if self._isCoreProfileContext():
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            root = self.model.getRootNode() if self.model else None
            self.beginCoreDrawFrame()
            drew = self.drawModelCorePath(
                root,
                base_translate=(self.getBaseWidth()/2.0, self.getBaseHeight()/2.0, 0.0),
            )
            if not drew and not getattr(self, '_logged_core_stub_model_warning', False):
                logger.warning('Core profile mode: model draw path not ready for this model; rendering fallback clear only')
                self._logged_core_stub_model_warning = True
            self.SwapBuffers()
            return

        try:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self.setupCamera()
            glLightfv(GL_LIGHT0,GL_AMBIENT,[1.0,1.0,1.0,1.0])
            glLightfv(GL_LIGHT0,GL_DIFFUSE,[1.0,1.0,1.0,1.0])
            glLightfv(GL_LIGHT0,GL_SPECULAR,[1.0,1.0,1.0,1.0])
            glLightfv(GL_LIGHT0,GL_POSITION,[self.viewX,self.viewY,self.viewZ,1.0])
            if hasattr(self, 'shader_manager'):
                self.shader_manager.set_scene_lighting(
                    ambient=[1.0, 1.0, 1.0, 1.0],
                    diffuse=[1.0, 1.0, 1.0, 1.0],
                    specular=[1.0, 1.0, 1.0, 1.0],
                    position=[self.viewX, self.viewY, self.viewZ, 1.0],
                )

            shader_render_state = False
            if hasattr(self, 'shader_manager') and self._shaders_compiled:
                shader_render_state = self.shader_manager.apply_render_state()
                self.shader_manager.sync_matrix_state_from_gl()
                self.shader_manager.use_current_shader()

            glTranslate(self.getBaseWidth()/2.0,self.getBaseHeight()/2.0,0)
            self.handleNode(self.model.getRootNode(),boxOnly=False,
                            frustumCull=False,selected=False)
            if hasattr(self, 'shader_manager') and self._shaders_compiled:
                glUseProgram(0)
                self.shader_manager.restore_render_state(shader_render_state)
            self.SwapBuffers()
            
        except KeyboardInterrupt:
            print('shutting down')
            sys.exit()

    def preprocess(self):        
        if self.model:
            self.makeCurrent()
            self.preprocessNodes(self.model,'modelviewer',bbox=True)
            self.lookingAtZ = (self.model.boundingBox[1][2] -
                               self.model.boundingBox[0][2])/2.0
            self.preprocessed = True
            self.recomputeCamera()
            
    def Destroy(self):
        neverglobals.getResourceManager().removeVisualChangeListener(self)
        GLWindow.Destroy(self)
        
    def get_standalone(cls, modelfile):
        win = None
        class MyApp(wx.App):
            def OnInit(self):
                m = MDLFile.MDLFile()
                m.fromFile(open(modelfile))
                frame = wx.Frame(None, -1, "Model " + modelfile, wx.DefaultPosition, wx.Size(400,400))
                sizer = wx.BoxSizer(wx.VERTICAL)
                sizer.Add((100,100))
                b = wx.Button(frame,-1,"test")
                sizer.Add(b,True,wx.EXPAND)
                win = ModelWindow(frame)
                frame.SetSizer(sizer)
                win.SetSize((200,200))
                sizer.Add(win,False,wx.ALIGN_BOTTOM|wx.ALIGN_RIGHT)
                win.setModel(m.getModel())
                frame.Show(True)
                self.SetTopWindow(frame)
                return True
        cls.app = MyApp(0)
        return win
    get_standalone = classmethod(get_standalone)

    def start_standalone(cls):
        cls.app.MainLoop()
    start_standalone = classmethod(start_standalone)
    

def run(args):
    ModelWindow.get_standalone(args[0])
    ModelWindow.start_standalone()
    
# Print message to console, and kick off the main to get it rolling.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: ' + sys.argv[0] + ' <modelfile>')
        sys.exit(1)
    run(sys.argv[1:])
