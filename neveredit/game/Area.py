import logging
logger = logging.getLogger("neveredit")

from neveredit.game import NeverData
from neveredit.game.Door import DoorInstance
from neveredit.game.Placeable import PlaceableInstance
from neveredit.game.Item import ItemInstance
from neveredit.game.Creature import CreatureInstance
from neveredit.game.Tile import Tile
from neveredit.game.WayPoint import WayPointInstance
from neveredit.game.Sound import SoundInstance
from neveredit.util import neverglobals

class Area (NeverData.NeverData):
    arePropList = {
        'Name': 'CExoLocString',
        'ChanceLightning': 'Percentage',
        'ChanceRain': 'Percentage',
        'ChanceSnow': 'Percentage',
        'DayNightCycle': 'Boolean',
        'IsNight': 'Boolean',
        'ModListenCheck': 'Integer',
        'ModSpotCheck': 'Integer',
        'MoonFogAmount': 'Integer,0-15',
        'MoonShadows': 'Boolean',
        'NoRest': 'Boolean',
        'ShadowOpacity': 'Percentage',
        'SunFogAmount': 'Integer,0-15',
        'SunShadows': 'Boolean',
        'WindPower': 'Integer,0-2',
        'OnEnter': 'ResRef,NSS',
        'OnExit': 'ResRef,NSS',
        'OnHeartbeat': 'ResRef,NSS',
        'OnUserDefined': 'ResRef,NSS',
        'MoonAmbientColor': 'BGRColour',
        'MoonDiffuseColor': 'BGRColour',
        'SunDiffuseColor': 'BGRColour',
        'SunDiffuseColor': 'BGRColour',
        'SunFogColor': 'BGRColour',
        'MoonFogColor': 'BGRColour',
        'Tag': 'CExoString',
        'PlayerVsPlayer': '2daIndex,pvpsettings.2da,strref,strref',
        'LoadScreenID': '2daIndex,loadscreens.2da,StrRef,strref,Label'
        }

    gitPropList = {
        'AreaProperties.AmbientSndDayVol': 'Integer,0-127',
        'AreaProperties.AmbientSndNitVol': 'Integer,0-127',
        'AreaProperties.AmbientSndDay':
        '2daIndex,ambientsound.2da,Description,strref,DisplayName',
        'AreaProperties.AmbientSndNight':
        '2daIndex,ambientsound.2da,Description,strref,DisplayName',
        'AreaProperties.EnvAudio':
        '2daIndex,soundeax.2da,Description,strref,Label',
        'AreaProperties.MusicBattle':
        '2daIndex,ambientmusic.2da,Description,strref,DisplayName',
        'AreaProperties.MusicDay':
        '2daIndex,ambientmusic.2da,Description,strref,DisplayName',        
        'AreaProperties.MusicDelay':
        '2daIndex,ambientmusic.2da,Description,strref,DisplayName',
        'AreaProperties.MusicNight':
        '2daIndex,ambientmusic.2da,Description,strref,DisplayName',
        }

    gicPropList = {}
    
    def __init__(self,erfFile,areaName):
        NeverData.NeverData.__init__(self)
        if isinstance(areaName, bytes):
            area_name_bytes = areaName.rstrip(b'\0')
            area_name_text = area_name_bytes.decode('latin1', 'ignore')
        else:
            area_name_text = str(areaName).strip('\0')
            area_name_bytes = area_name_text.encode('latin1', 'ignore')

        self.name = area_name_text
        area = erfFile.getEntryByNameAndExtension(area_name_text,'ARE')
        if not area:
            area = erfFile.getEntryByNameAndExtension(area_name_bytes,'ARE')
        if not area:
            raise RuntimeError("couldn't find area for " + area_name_text)

        git = erfFile.getEntryByNameAndExtension(area_name_text,'GIT')
        if not git:
            git = erfFile.getEntryByNameAndExtension(area_name_bytes,'GIT')

        gic = erfFile.getEntryByNameAndExtension(area_name_text,'GIC')
        if not gic:
            gic = erfFile.getEntryByNameAndExtension(area_name_bytes,'GIC')
        
        self.addPropList('are',self.arePropList,
                         erfFile.getEntryContents(area).getRoot())
        self.addPropList('gic',self.gicPropList,
                         erfFile.getEntryContents(gic).getRoot())
        self.addPropList('git',self.gitPropList,
                         erfFile.getEntryContents(git).getRoot())
        self.creatureList = None
        self.doorList = None
        self.placeableList = None
        self.itemList = None
        self.tileList = None
        self.waypointList = None
        self.soundList = None
        
    def readContents(self):
        if self.creatureList == None:
            creatures = self.gffstructDict['git'].getInterpretedEntry('Creature List') or []
            self.creatureList = [CreatureInstance(creature) for creature in creatures]
            doors = self.gffstructDict['git'].getInterpretedEntry('Door List') or []
            self.doorList = [DoorInstance(door) for door in doors]
            placeables = self.gffstructDict['git'].getInterpretedEntry('Placeable List') or []
            self.placeableList = [PlaceableInstance(placeable) for placeable in placeables]
            items = self.gffstructDict['git'].getInterpretedEntry('List') or []
            self.itemList = [ItemInstance(item) for item in items]
            waypoints = self.gffstructDict['git'].getInterpretedEntry('WaypointList') or []
            self.waypointList = [WayPointInstance(waypoint) for waypoint in waypoints]
            sounds = self.getSoundListStructs()
            self.soundList = [SoundInstance(sound) for sound in sounds]

    def getSoundListStructs(self):
        git = self.gffstructDict['git']
        for label in ('SoundList', 'Sounds', 'Sound List'):
            value = git.getInterpretedEntry(label)
            if value is not None:
                return value or []
        return []

    def getSoundListLabel(self):
        git = self.gffstructDict['git']
        for label in ('SoundList', 'Sounds', 'Sound List'):
            if git.getInterpretedEntry(label) is not None:
                return label
        return 'SoundList'

    def _ensureGitList(self, label):
        git = self.gffstructDict['git']
        value = git.getInterpretedEntry(label)
        if value is not None:
            return value
        if git.hasEntry(label):
            git.setInterpretedEntry(label, [])
        else:
            git.add(label, [], 'List')
        return git.getInterpretedEntry(label) or []

    def discardContents(self):
        self.creatureList = None
        self.doorList = None
        self.placeableList = None
        self.itemList = None
        self.waypointList = None
        self.soundList = None
        
    def readTiles(self):
        if not self.tileList:
            tileSet = self.getTileSet()
            tiles = self.gffstructDict['are'].getInterpretedEntry('Tile_List')
            self.tileList = [Tile(tileSet,s) for s in tiles]

    def discardTiles(self):
        self.tileList = None

    def getTags(self):
        """Get a dictionary of all tags in this area.
        The dictionary will look like this::
        
        {
        'creatures': [<creature_tag_1>,<creature_tag_2>...],
        'doors': [<door_tag_1>,<door_tag_2>...],
        'items': [<item_tag_1>,<item_tag_2>...],
        'placeables': [<placeable_tag_1>,<placeable_tag_2>...],
        'waypoints':[<waypoint_tag_1>,<waypoint_tag_1>...]
        }
        
        @return: the tag dictionary for this area
        """
        tags = {}
        tags['creatures'] = [c['Tag'] for c in self.getCreatures()]
        tags['doors'] = [d['Tag'] for d in self.getDoors()]
        tags['placeables'] = [p['Tag'] for p in self.getPlaceables()]
        tags['items'] = [i['Tag'] for i in self.getItems()]
        tags['waypoints']=[w['Tag'] for w in self.getWayPoints()]
        return tags
    
    def getCreatures(self):
        self.readContents()
        return self.creatureList

    def getDoors(self):
        self.readContents()
        return self.doorList

    def getPlaceables(self):
        self.readContents()
        return self.placeableList
    
    def getItems(self):
        self.readContents()
        return self.itemList

    def getWayPoints(self):
        self.readContents()
        return self.waypointList

    def getSounds(self):
        self.readContents()
        return self.soundList

    def addThing(self,thing):
        logger.info('trying to add thing ' + repr(thing.getNevereditId()) + ' (class ' + repr(thing.__class__) + ') to area')
        gff = thing.getMainGFFStruct()
        if not gff:
            logger.error("could'nt get a main GFF struct for " + repr(thing) + ' - not added.')
            return
        self.readContents()
        if isinstance(thing, CreatureInstance):
            self._ensureGitList('Creature List').append(gff)
            self.creatureList.append(thing)
        elif isinstance(thing, ItemInstance):
            self._ensureGitList('List').append(gff)
            self.itemList.append(thing)
        elif isinstance(thing, DoorInstance):
            self._ensureGitList('Door List').append(gff)
            self.doorList.append(thing)
        elif isinstance(thing, PlaceableInstance):
            self._ensureGitList('Placeable List').append(gff)
            self.placeableList.append(thing)
        elif isinstance(thing, WayPointInstance):
            self._ensureGitList('WaypointList').append(gff)
            self.waypointList.append(thing)
        elif isinstance(thing, SoundInstance):
            self._ensureGitList(self.getSoundListLabel()).append(gff)
            self.soundList.append(thing)
        
    def getTileSet(self):
        resref = self.gffstructDict['are'].getInterpretedEntry('Tileset')
        if isinstance(resref, bytes):
            resref = resref.rstrip(b'\0').decode('latin1', 'ignore')
        elif resref is None:
            resref = ''
        else:
            resref = str(resref).strip('\0')
        name = resref + '.set'
        return neverglobals.getResourceManager().getResourceByName(name)

    def getTiles(self):
        return self.tileList

    def getTile(self,x,y):
        return self.tileList[y*self.getWidth()+x]
    
    def getName(self):
        name = self['Name'].getString()
        if name and not str(name).startswith('StrRef '):
            return name
        tag = self['Tag']
        if tag:
            return tag
        return self.name

    def getHeight(self):
        """
        Get the area height.
        @return: this area's height (in tiles)
        """
        return self.getGFFStruct('are')['Height']

    def getWidth(self):
        """
        Get the area width.
        @return: this area's width (in tiles)
        """
        return self.getGFFStruct('are')['Width']




    

    
