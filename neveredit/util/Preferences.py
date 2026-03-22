"""The neveredit preferences system."""
import logging
logger = logging.getLogger("neveredit")

import os,os.path,sys,time
import encodings, codecs

from neveredit.util import Utils
from neveredit.util import plistlib

globalPrefs = None

def getPreferences():
    """Get the gloal prefs object. Load it if non-existent.
    @return: the global preferences object.
    """
    global globalPrefs
    if not globalPrefs:
        globalPrefs = Preferences()
        globalPrefs.load()
    return globalPrefs

class Preferences:
    """A class to load and store user level cross-platform
    preferences for neveredit."""
    def __init__(self):
        if 'HOME' in os.environ:
            self.prefPath = os.environ['HOME']
        else:
            self.prefPath = os.path.dirname(sys.argv[0])
            
        if Utils.iAmOnMac():
            self.prefPath = os.path.join(self.prefPath,
                                         'Library','Preferences',
                                         'org.openknights.neveredit.plist')
        elif sys.platform.find('linux') >= 0:
            self.prefPath = os.path.join(self.prefPath,'.neveredit')
        else:
            self.prefPath = os.path.join(self.prefPath,'neveredit.prefs')

        # Updated to include preferences for control of the model
        # window.
        self.values = {'NWNAppDir':None,
                       'ScriptAntiAlias':False,
                       'ScriptAutoCompile':True,
                       "DefaultLocStringLang":0,        # english=0
                       'FileHistory':[],
                       'MainWindowState':None,
                       'MainSplitterSashPosition':None,
                       'ScriptEditorState':None,
                       'ToolPaletteState':None,
                       'ShaderWindowState':None,
                       'EnabledShaders':None,
                       'CurrentShader':'None',
                       'ShaderParameters':{},
                       'RenderLiveTuning': {
                           'ToonEnabled': False,
                           'ToonBands': 7.0,
                           'ToonRimStrength': 0.28,
                           'DistanceDesatStrength': 0.12,
                       },
                       'RenderDepthLOD': {
                           'FogEnabled': True,
                           'FogNearDistance': 120.0,
                           'FogFarDistance': 250.0,
                           'TileLodDistance': 140.0,
                           'ThingLodDistance': 110.0,
                           'SmallThingLodDistance': 80.0,
                           'DecorCullDistance': 210.0,
                       },
                       'GLW_UP':'w',
                       'GLW_DOWN': 's',
                       'GLW_RIGHT': 'e',
                       'GLW_LEFT': 'q'}


    def __getitem__(self,key):
        return self.values[key]

    def __setitem__(self,key,value):
        self.values[key] = value
        
    def load(self):
        '''Load preferences from their standard location.'''
        #defaults
        if not self.values['NWNAppDir']:
            if sys.platform == 'darwin':
                self['NWNAppDir'] = '/Applications/Neverwinter Nights/'
            elif sys.platform.find('linux') >= 0:
                self['NWNAppDir'] = '/usr/local/games/nwn/'
            else:
                self['NWNAppDir'] = '/Program Files/NWN/'                

        codecs.register(encodings.search_function)
        if os.path.exists(self.prefPath):
            try:
                pl = plistlib.Plist.fromFile(self.prefPath)
                for key in self.values:
                    if key in pl:
                        self.values[key] = getattr(pl,key)
            except Exception as exc:
                # Could be out of date or malformed/truncated.
                logger.warning("while reading preferences file: %s", exc)
                self._quarantineCorruptPrefsFile()

    def _quarantineCorruptPrefsFile(self):
        if not os.path.exists(self.prefPath):
            return
        backup_path = self.prefPath + '.corrupt'
        if os.path.exists(backup_path):
            backup_path = '%s.corrupt.%d' % (self.prefPath, int(time.time()))
        try:
            os.replace(self.prefPath, backup_path)
            logger.warning("moved unreadable preferences file to %s", backup_path)
        except Exception:
            logger.exception("unable to move unreadable preferences file")
                
                
    def save(self):
        '''Save the current preferences settings.'''
        codecs.register(encodings.search_function)
        pref_dir = os.path.dirname(self.prefPath)
        if pref_dir and not os.path.isdir(pref_dir):
            try:
                os.makedirs(pref_dir)
            except OSError:
                pass

        pl = plistlib.Plist()
        pl.update(self._sanitize_for_plist(self.values))
        tmp_path = self.prefPath + '.tmp'
        try:
            pl.write(tmp_path)
            os.replace(tmp_path, self.prefPath)
            return True
        except Exception:
            logger.exception("while writing preferences file")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

    def _sanitize_for_plist(self, value):
        '''Remove None values recursively because the legacy plist writer
        cannot serialize NoneType.'''
        if value is None:
            return None
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                cleaned_item = self._sanitize_for_plist(item)
                if cleaned_item is None:
                    continue
                cleaned[key] = cleaned_item
            return cleaned
        if isinstance(value, (list, tuple)):
            cleaned = []
            for item in value:
                cleaned_item = self._sanitize_for_plist(item)
                if cleaned_item is None:
                    continue
                cleaned.append(cleaned_item)
            return cleaned
        return value

    def update(self,valueDict):
        self.values.update(valueDict)
        

