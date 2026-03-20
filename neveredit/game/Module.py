'''Classes for handling nwn modules'''

import logging
logger = logging.getLogger('neveredit')
import re

import neveredit.file.ERFFile
from neveredit.file.GFFFile import GFFStruct,GFFFile
from neveredit.file.CExoLocString import CExoLocString
from neveredit.game.Area import Area
from neveredit.game.NeverData import NeverData
import neveredit.game.Factions
from neveredit.util import neverglobals
from neveredit.util.Progressor import Progressor

from io import StringIO
from os.path import basename
import time

class Module(Progressor,NeverData):    
    """A class the encapsulates an NWN module file and gives access
    to entities contained therein, such as doors and scripts."""
    ifoPropList = {
        "Mod_CustomTlk":"CExoString",
        "Mod_DawnHour":"Integer,0-23",
        "Mod_Description":"CExoLocString,4",
        "Mod_DuskHour":"Integer,0-23",
        "Mod_Entry_Area":"ResRef,ARE",
        "Mod_HakList":"List,HAKs",
        "Mod_Hak":"CheckList,HAK",
        "Mod_Name":"CExoLocString",
        "Mod_MinPerHour": "Integer,1-255",
        "Mod_OnAcquirItem": "ResRef,NSS",
        "Mod_OnActvtItem": "ResRef,NSS",
        "Mod_OnClientEntr": "ResRef,NSS",
        "Mod_OnClientLeav": "ResRef,NSS",
        "Mod_OnCutsnAbort": "ResRef,NSS",
        "Mod_OnHeartbeat": "ResRef,NSS",
        "Mod_OnModLoad": "ResRef,NSS",
        "Mod_OnModStart": "ResRef,NSS",
        "Mod_OnPlrDeath": "ResRef,NSS",
        "Mod_OnPlrDying": "ResRef,NSS",
        "Mod_OnPlrEqItm": "ResRef,NSS",
        "Mod_OnPlrLvlUp": "ResRef,NSS",
        "Mod_OnPlrRest": "ResRef,NSS",
        "Mod_OnPlrUnEqItm": "ResRef,NSS",
        "Mod_OnSpawnBtnDn": "ResRef,NSS",
        "Mod_OnUnAqreItem": "ResRef,NSS",
        "Mod_OnUsrDefined": "ResRef,NSS",
        "Mod_StartDay": "Integer,1-31",
        "Mod_StartHour": "Integer,0-23",
        "Mod_StartMonth": "Integer,1-24",
        "Mod_StartYear": "Integer,0-2000",
        "Mod_Tag": "CExoString",
        "Mod_XPScale": "Integer,0-255",
        "Mod_Area_list": "Hidden",
        "VarTable": "List,Vars"
        }

    @staticmethod
    def _entry_resref_name(entry):
        name = entry.name
        if isinstance(name, bytes):
            return name.rstrip(b'\0').decode('latin1', 'ignore')
        return str(name).strip('\0')

    @staticmethod
    def _format_eta(seconds):
        seconds = max(0, int(seconds))
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return "%d:%02d:%02d" % (hours, mins, secs)
        return "%02d:%02d" % (mins, secs)

    @staticmethod
    def _sanitize_resref(text, fallback='module'):
        value = re.sub(r'[^a-zA-Z0-9_]', '_', (text or '').lower())
        value = re.sub(r'_+', '_', value).strip('_')
        value = value[:16]
        if not value:
            value = fallback[:16]
        return value

    @classmethod
    def createBlankModuleFile(cls, file_path, module_name):
        """Create a minimal valid .MOD file with a blank IFO root."""
        display_name = (module_name or '').strip() or 'New Module'
        module_tag = cls._sanitize_resref(display_name, fallback='module')

        module_erf = neveredit.file.ERFFile.ERFFile('MOD')
        ifo_gff = GFFFile()
        ifo_gff.type = 'IFO '
        ifo_gff.version = 'V3.2'
        root = GFFStruct()

        root.add('Mod_Name', CExoLocString(value=display_name).toGFFEntry(), 'CExoLocString')
        root.add('Mod_Description', CExoLocString(value='').toGFFEntry(), 'CExoLocString')
        root.add('Mod_Tag', module_tag, 'CExoString')
        root.add('Mod_Entry_Area', '', 'ResRef')
        root.add('Mod_Area_list', [], 'List')
        root.add('Mod_HakList', [], 'List')
        root.add('Mod_CustomTlk', '', 'CExoString')
        root.add('VarTable', [], 'List')
        root.add('Mod_DawnHour', 6, 'INT')
        root.add('Mod_DuskHour', 18, 'INT')
        root.add('Mod_MinPerHour', 2, 'INT')
        root.add('Mod_StartDay', 1, 'INT')
        root.add('Mod_StartMonth', 1, 'INT')
        root.add('Mod_StartYear', 1372, 'INT')
        root.add('Mod_StartHour', 13, 'INT')
        root.add('Mod_XPScale', 100, 'INT')

        for script_prop in (
            'Mod_OnAcquirItem', 'Mod_OnActvtItem', 'Mod_OnClientEntr',
            'Mod_OnClientLeav', 'Mod_OnCutsnAbort', 'Mod_OnHeartbeat',
            'Mod_OnModLoad', 'Mod_OnModStart', 'Mod_OnPlrDeath',
            'Mod_OnPlrDying', 'Mod_OnPlrEqItm', 'Mod_OnPlrLvlUp',
            'Mod_OnPlrRest', 'Mod_OnPlrUnEqItm', 'Mod_OnSpawnBtnDn',
            'Mod_OnUnAqreItem', 'Mod_OnUsrDefined',
        ):
            root.add(script_prop, '', 'ResRef')

        ifo_gff.rootStructure = root
        module_erf.addResourceByName('module.IFO', ifo_gff)
        module_erf.toFile(file_path)
    
    def __init__(self,fname):
        Progressor.__init__(self)
        NeverData.__init__(self)
        self.needSave = False
        logger.debug("reading erf file %s",fname)
        self.erfFile = neveredit.file.ERFFile.ERFFile()
        self.erfFile.fromFile(fname)
        ifoEntry = self.erfFile.getEntryByNameAndExtension("module","IFO")
        if ifoEntry is None:
            ifo_entries = self.erfFile.getEntriesWithExtension('IFO')
            if ifo_entries:
                logger.warning('module IFO key "module.IFO" not found, falling back to first IFO entry')
                ifoEntry = ifo_entries[0]
            else:
                raise RuntimeError('No IFO entry found in module ERF file')
        self.addPropList('ifo',self.ifoPropList,
                         self.erfFile.getEntryContents(ifoEntry).getRoot())
        logger.debug("checking for old style Mod_Hak")
        prop = self['Mod_Hak']
        if prop != None:
            logger.info('Old-Style Mod_Hak found,'
                        'changing to new style Mod_HakList')
            new_prop = self['Mod_HakList']
            if not new_prop:
                self.getGFFStruct('ifo').add('Mod_HakList',[],'List')
                new_prop = self['Mod_HakList']
            if prop:
                new_prop.append(prop)
            self.needSave = True
            
        prop = self['Mod_CustomTlk']
        if prop == None:
            logger.info("Old (pre-1.59) module with no Mod_CustomTlk,"
                        "adding an empty one")
            self.getGFFStruct('ifo').add('Mod_CustomTlk',"",'CExoString')
            self.needSave = True
        prop = self['VarTable']
        if prop == None:
            logger.info("no VarTable found, adding an empty one")
            self.getGFFStruct('ifo').add('VarTable',[],'List')
            self.needSave = True

        self.scripts = None
        self.conversations = None
        self.areas = {}
        self.soundBlueprints = None
        self.triggerBlueprints = None
        self.encounterBlueprints = None

        try:
            self.facObject = neveredit.game.Factions.Factions(self.erfFile)
        except RuntimeError:
            self.facObject = None
        self.factions= {}
    
    def getFileName(self):
        return self.erfFile.filename
    
    def removeProperty(self,label):
        if label in self.ifoPropList:
            (s,t) = self.gffstructDict['ifo'].getTargetStruct(label)
            print('removing',t)
            s.removeEntry(t)

    def getHAKNames(self):
        if self['Mod_HakList'] != None:
            return [p['Mod_Hak'] + '.hak'
                    for p in self['Mod_HakList']]
        elif self['Mod_Hak'] != None:
            return [self['Mod_Hak']]
        else:
            return []
    
    def getName(self,lang=0):
        '''Looks up Mod_Name in the ifo file'''
        return self['Mod_Name'].getString(lang)
    
    def getAreaNames(self):
        '''Returns a list of area resref names
        @return: list of area resrefs
        '''
        return [a['Area_Name'] for a in self['Mod_Area_list']]

    def getArea(self,name):
        '''Get an area by its name
        @param name: name of the area object to return'''
        if name in self.areas:
            return self.areas[name]
        else:
            try:
                a = Area(self.erfFile,name)
            except Exception:
                logger.warning('skipping area with missing/broken resources: %r', name)
                return None
            self.areas[name] = a
            return a

    def getEntryArea(self):
        entry_area = self.getArea(self['Mod_Entry_Area'])
        if entry_area is not None:
            return entry_area
        for area in self.getAreas().values():
            return area
        return None
    
    def getAreas(self):
        """Get the areas in this ERF.
        @return: a dict of Area names (keys) and objects (values)."""
        names = self.getAreaNames()
        areas = {}
        total = len(names)
        if total == 0:
            self.setProgress(0)
            return areas
        start = time.time()
        for i, n in enumerate(names, 1):
            elapsed = max(0.001, time.time() - start)
            progress = (float(i - 1) / float(total)) * 100.0
            rate = float(i - 1) / elapsed if i > 1 else 0.0
            remaining = (total - (i - 1)) / rate if rate > 0 else 0.0
            self.setStatus('Loading areas %d/%d (ETA %s)' %
                           (i - 1, total, self._format_eta(remaining)))
            self.setProgress(progress)
            area = self.getArea(n)
            if area is not None:
                areas[n] = area
        self.setProgress(100.0)
        self.setStatus('Loaded %d area definitions' % len(areas))
        self.setProgress(0)
        return areas

    def getTags(self):
        """Get a dictionary of all tags in this module.
        The dictionary will look like this::
        
        {
        'module': <module_Tag>,
        'areas':  {<area_tag>: <tag_dict_for_area>}
        }

        Where <tag_dict_for_area> is the dictionary produced by
        L{neveredit.game.Area.Area.getTags} for the area in question.

        Note that this function needs to read all areas and their
        contents, and thus will be slow unless they're already
        loaded.
        
        @return: the tag dictionary for this module
        """
        
        tags = {}
        tags['module'] = self['Mod_Tag']
        tags['areas'] = {}
        for a in list(self.getAreas().values()):
            tags['areas'][a['Tag']] = a.getTags()
        return tags
    
    def getConversations(self):
        """Get the conversations in this ERF.
        @return: A dict of name:L{neveredit.game.Conversation.Conversation} objects."""
        if not self.conversations:
            entries = self.erfFile.getEntriesWithExtension('DLG')
            self.conversations = {}
            for s in entries:
                self.conversations[self._entry_resref_name(s)] = self.erfFile.getEntryContents(s)
        return self.conversations

    def getScripts(self):
        """Get the scripts in this ERF.
        @return: A dict of name:Script objects."""
        if not self.scripts:
            entries = self.erfFile.getEntriesWithExtension('NSS')
            self.scripts = {}
            for s in entries:
                self.scripts[self._entry_resref_name(s)] = self.erfFile.getEntryContents(s)
        return self.scripts

    def getFactions(self):
        """Get the factions in the module"""
        if self.facObject and not self.factions:            
            self.facObject.readContents()
            for f in self.facObject.factionList:
                self.factions[f.getName()] = f
        return self.factions

    def getSoundBlueprints(self):
        """Get .UTS sound blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.soundBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTS')
            self.soundBlueprints = {}
            for s in entries:
                self.soundBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.soundBlueprints

    def getTriggerBlueprints(self):
        """Get .UTT trigger blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.triggerBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTT')
            self.triggerBlueprints = {}
            for s in entries:
                self.triggerBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.triggerBlueprints

    def getEncounterBlueprints(self):
        """Get .UTE encounter blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.encounterBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTE')
            self.encounterBlueprints = {}
            for s in entries:
                self.encounterBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.encounterBlueprints

    def addScript(self,s):
        if not self.scripts:
            self.getScripts()
        self.scripts[s.getName()[:-4]] = s
        self.commit()
        neverglobals.getResourceManager().moduleResourceListChanged()
        
    def commit(self):
        if self.scripts:
            for s in list(self.scripts.values()):
                self.erfFile.addResourceByName(s.getName(),s)
                if s.getCompiledScript():
                    self.erfFile.addResourceByName(s.getName()[:-4] + '.ncs',s.getCompiledScript())

    def updateReputeFac(self):
        raw_repute_fac = self.erfFile.getRawEntryContents(self.erfFile.\
                    getEntryByNameAndExtension('repute','FAC'))
        repute_gff = GFFFile()
        repute_gff.fromFile(StringIO(raw_repute_fac))
        repute_gff.rootStructure.removeEntry('FactionList')
        repute_gff.rootStructure.removeEntry('RepList')
        repute_gff.add('FactionList',[x.getGFFStruct('factStruct') for x\
                                                 in self.facObject.factionList],'List')
        repute_gff.add('RepList',[x.getGFFStruct('repStruct') for x in\
                                                self.facObject.RepList],'List')
        f = StringIO()
        repute_gff.toFile(f)
        raw_repute_fac = f.getvalue()
        f.close()
        self.erfFile.addRawResourceByName(('repute.FAC'),raw_repute_fac)        

    def saveToReadFile(self):
        self.commit()
        self.updateReputeFac()
        self.erfFile.saveToReadFile()

    def toFile(self,fpath):
        self.commit()
        self.erfFile.toFile(fpath)

    def saveAs(self,fpath):
        self.commit()
        self.erfFile.toFile(fpath)
        self.erfFile.reassignReadFile(fpath)

    def addResourceFile(self,fname):
        key = neveredit.game.ResourceManager.ResourceManager.keyFromName(\
                                                                basename(fname))
        resource = neverglobals.getResourceManager().interpretResourceContents(\
                                                key,open(fname,'rb').read())
        self.erfFile.addResource(key,resource)
        
    def addERFFile(self,fname):
        self.erfFile.addFile(fname)
        self.updateAreaList()

    def createNewArea(self, name, resref, tileset, width, height):
        """Create a new blank area and register it in this module."""
        from neveredit.file.CExoLocString import CExoLocString as _CExoLocString

        resref = resref.strip().lower()[:16]

        # ── Read tileset-contextual defaults from .SET ──────────────────────
        _day_night_cycle = 1
        _music = 0
        _ambient = 0
        _ts = neverglobals.getResourceManager().getResourceByName(tileset + '.set')
        if _ts is not None:
            try: _day_night_cycle = 0 if int(_ts.get('GENERAL', 'interior', fallback='0')) else 1
            except Exception: pass
            try: _music = int(_ts.get('GENERAL', 'defaultmusic', fallback='0'))
            except Exception: pass
            try: _ambient = int(_ts.get('GENERAL', 'defaultenvmap', fallback='0'))
            except Exception: pass

        # ── ARE ──────────────────────────────────────────────────────────────
        are_gff = GFFFile()
        are_gff.type = 'ARE '
        are_gff.version = 'V3.2'
        r = GFFStruct()

        loc_name = _CExoLocString(value=name, langID=0, gender=0)
        r.add('Name', loc_name.toGFFEntry(), 'CExoLocString')
        r.add('Tag', resref, 'CExoString')
        r.add('Tileset', tileset, 'ResRef')
        r.add('Width', width, 'INT')
        r.add('Height', height, 'INT')
        r.add('ChanceLightning', 0, 'BYTE')
        r.add('ChanceRain', 0, 'BYTE')
        r.add('ChanceSnow', 0, 'BYTE')
        r.add('DayNightCycle', _day_night_cycle, 'BYTE')
        r.add('IsNight', 0, 'BYTE')
        r.add('ModListenCheck', 0, 'INT')
        r.add('ModSpotCheck', 0, 'INT')
        r.add('MoonAmbientColor', 0x404040, 'DWORD')
        r.add('MoonDiffuseColor', 0x404040, 'DWORD')
        r.add('MoonFogAmount', 0, 'BYTE')
        r.add('MoonFogColor', 0x404040, 'DWORD')
        r.add('MoonShadows', 1, 'BYTE')
        r.add('NoRest', 0, 'BYTE')
        r.add('OnEnter', '', 'ResRef')
        r.add('OnExit', '', 'ResRef')
        r.add('OnHeartbeat', '', 'ResRef')
        r.add('OnUserDefined', '', 'ResRef')
        r.add('PlayerVsPlayer', 0, 'BYTE')
        r.add('ShadowOpacity', 100, 'BYTE')
        r.add('SunAmbientColor', 0xA0A0A0, 'DWORD')
        r.add('SunDiffuseColor', 0xFFFFFF, 'DWORD')
        r.add('SunFogAmount', 0, 'BYTE')
        r.add('SunFogColor', 0xC8C8C8, 'DWORD')
        r.add('SunShadows', 1, 'BYTE')
        r.add('WindPower', 0, 'BYTE')
        r.add('LoadScreenID', 0, 'WORD')
        r.add('ID', 0, 'DWORD')
        r.add('Flags', 0, 'DWORD')
        r.add('Comments', '', 'CExoString')
        r.add('Version', 1, 'DWORD')
        tiles = []
        for _ in range(width * height):
            t = GFFStruct(1)
            t.add('Tile_AnimLoop1', 0, 'INT')
            t.add('Tile_AnimLoop2', 0, 'INT')
            t.add('Tile_AnimLoop3', 0, 'INT')
            t.add('Tile_Height', 0, 'INT')
            t.add('Tile_ID', 0, 'INT')
            t.add('Tile_MainLight1', 0, 'BYTE')
            t.add('Tile_MainLight2', 0, 'BYTE')
            t.add('Tile_Orientation', 0, 'INT')
            t.add('Tile_SrcLight1', 0, 'INT')
            t.add('Tile_SrcLight2', 0, 'INT')
            tiles.append(t)
        r.add('Tile_List', tiles, 'List')
        are_gff.rootStructure = r

        # ── GIT ──────────────────────────────────────────────────────────────
        git_gff = GFFFile()
        git_gff.type = 'GIT '
        git_gff.version = 'V3.2'
        g = GFFStruct()
        ap = GFFStruct()
        ap.add('AmbientSndDay', _ambient, 'INT')
        ap.add('AmbientSndDayVol', 127, 'BYTE')
        ap.add('AmbientSndNight', _ambient, 'INT')
        ap.add('AmbientSndNitVol', 127, 'BYTE')
        ap.add('EnvAudio', 0, 'INT')
        ap.add('MusicBattle', 0, 'INT')
        ap.add('MusicDay', _music, 'INT')
        ap.add('MusicDelay', 0, 'INT')
        ap.add('MusicNight', _music, 'INT')
        g.add('AreaProperties', ap, 'Struct')
        g.add('Creature List', [], 'List')
        g.add('Door List', [], 'List')
        g.add('Encounter List', [], 'List')
        g.add('List', [], 'List')
        g.add('Placeable List', [], 'List')
        g.add('SoundList', [], 'List')
        g.add('Trigger List', [], 'List')
        g.add('WaypointList', [], 'List')
        git_gff.rootStructure = g

        # ── GIC ──────────────────────────────────────────────────────────────
        gic_gff = GFFFile()
        gic_gff.type = 'GIC '
        gic_gff.version = 'V3.2'
        gic_gff.rootStructure = GFFStruct()

        # ── Register in ERF ──────────────────────────────────────────────────
        self.erfFile.addResourceByName(resref + '.ARE', are_gff)
        self.erfFile.addResourceByName(resref + '.GIT', git_gff)
        self.erfFile.addResourceByName(resref + '.GIC', gic_gff)

        # ── Append to Mod_Area_list ───────────────────────────────────────────
        area_list = self.gffstructDict['ifo'].getInterpretedEntry('Mod_Area_list')
        if area_list is None:
            area_list = []
            self.gffstructDict['ifo'].add('Mod_Area_list', area_list, 'List')
        area_entry = GFFStruct()
        area_entry.add('Area_Name', resref, 'ResRef')
        area_list.append(area_entry)

        entry_area = self.gffstructDict['ifo'].getInterpretedEntry('Mod_Entry_Area')
        if not entry_area:
            self.gffstructDict['ifo'].setInterpretedEntry('Mod_Entry_Area', resref)

        neverglobals.getResourceManager().moduleResourceListChanged()
        self.needSave = True

        area = Area(self.erfFile, resref)
        self.areas[resref] = area
        return area

    def getKeyList(self):
        return self.erfFile.getKeyList()

    def getERFFile(self):
        return self.erfFile
    
    def setProgressDisplay(self,p):
        self.erfFile.setProgressDisplay(p)

    def getEntriesWithExtension(self,ext):
        return self.erfFile.getEntriesWithExtension(ext)

    def setProgress(self,p):
        self.erfFile.setProgress(p)
