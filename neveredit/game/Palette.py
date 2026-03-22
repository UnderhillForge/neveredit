import logging
logger = logging.getLogger('neveredit')

from neveredit.util import neverglobals
from neveredit.game.NeverData import NeverData
from neveredit.game.Door import DoorBP
from neveredit.game.Placeable import PlaceableBP
from neveredit.game.Creature import CreatureBP
from neveredit.game.Item import ItemBP
from neveredit.game.WayPoint import WayPointBP
from neveredit.game.Trigger import TriggerBP
from neveredit.game.Encounter import EncounterBP
from neveredit.game.Sound import SoundBP
from neveredit.game.Store import StoreBP

class TreeNode:
    def __init__(self,nodeStruct,bptype):
        self.bptype = bptype
        self.blueprint = None
        
        if nodeStruct.hasEntry('STRREF') and nodeStruct['STRREF'] != 0xffffffff:
            self.name = neverglobals.getResourceManager()\
                        .getDialogString(nodeStruct['STRREF'])
        elif nodeStruct.hasEntry('NAME'):
            self.name = nodeStruct['NAME']
        elif nodeStruct.hasEntry('DELETE_ME'):
            self.name = nodeStruct['DELETE_ME']
            
        if nodeStruct.hasEntry('TYPE'):            
            self.type = nodeStruct['TYPE']
        else:
            self.type = 0
            
        if nodeStruct.hasEntry('ID'):
            self.nodeID = nodeStruct['ID']
        else:
            self.nodeID = -1

        if nodeStruct.hasEntry('RESREF'):
            self.resref = nodeStruct['RESREF']
        else:
            self.resref = None

        if nodeStruct.hasEntry('CR'):
            self.challengeRating = nodeStruct['CR']
            self.faction = nodeStruct['FACTION']
        else:
            self.challengeRating = -1.0
            self.faction = ''

        if nodeStruct.hasEntry('LIST'):
            self.children = [TreeNode(s,self.bptype) for s in nodeStruct['LIST']]
        else:
            self.children = []
            
    def getName(self):
        return self.name

    def getChildren(self):
        return self.children

    def getImage(self):
        bp = self.getBlueprint()
        if bp:
            return bp.getPortrait('t')
        else:
            return None
    
    def getBPType(self):
        return self.bptype
   
    def getBlueprint(self):
        if not self.resref:
            return None
        if self.blueprint:
            return self.blueprint
        if isinstance(self.resref, bytes):
            resref = self.resref.rstrip(b'\0').decode('latin1', 'ignore')
        else:
            resref = str(self.resref).strip('\0')
        if self.bptype != 'Store':
            resname = resref + '.UT' + self.bptype[0]
        else:
            resname = resref + '.UTM'
        gffroot = neverglobals.getResourceManager()\
                  .getResourceByName(resname).getRoot()
        if self.bptype == 'Creature':
            self.blueprint = CreatureBP(gffroot)
        elif self.bptype == 'Door':
            self.blueprint = DoorBP(gffroot)
        elif self.bptype == 'Item':
            self.blueprint = ItemBP(gffroot)
        elif self.bptype == 'Trigger':
            self.blueprint = TriggerBP(gffroot)
        elif self.bptype == 'Sound':
            self.blueprint = SoundBP(gffroot)
        elif self.bptype == 'Encounter':
            self.blueprint = EncounterBP(gffroot)
        elif self.bptype == 'Placeable':
            self.blueprint = PlaceableBP(gffroot)
        elif self.bptype == 'Store':
            self.blueprint = StoreBP(gffroot)
        elif self.bptype == 'Waypoint':
            #raise NotImplementedError("no waypoint blueprints yet")
            self.blueprint = WayPointBP(gffroot)
        return self.blueprint

    def getTypeAsString(self):
        extension = neverglobals.getResourceManager()\
                    .extensionFromResType(self.type)
        return extension
    
    def printTree(self,indent):
        print(indent + repr(self))
        for c in self.children:
            c.printTree(indent + '  ')
            
    def __str__(self):
        return ' '.join([str(self.name), repr(self.resref), self.bptype])

    def __repr__(self):
        return self.__str__()

class Palette(NeverData):
    palettePropList = {}
    PALETTE_TYPES = ['Creature','Door','Encounter','Item','Placeable',
                     'Sound','Store','Trigger','Waypoint']
    def __init__(self,gffEntry,bptype):
        NeverData.__init__(self)
        self.addPropList('main',self.palettePropList,gffEntry)
        self.type = self['RESTYPE']
        self.roots = [TreeNode(nodeStruct,bptype) for nodeStruct in self['MAIN']]
        #for r in self.roots:
        #    r.printTree('')

    def getRoots(self):
        return self.roots

    def getStandardPalette(typ):
        r = neverglobals.getResourceManager()
        return Palette(r.getResourceByName(typ.lower() + 'palstd.itp').getRoot(),typ)
    getStandardPalette = staticmethod(getStandardPalette)


class TileNode:
    """Represents a single tile entry (Feature, Group, or Terrain) in a tileset palette."""
    def __init__(self, nodeStruct, section_name):
        """
        Initialize a TileNode from a GFF structure.
        
        Args:
            nodeStruct: GFFStruct with STRREF and RESREF entries
            section_name: 'Features', 'Groups', or 'Tiles'
        """
        self.section_name = section_name
        self.resref = None
        self.name = None
        
        # Get the display name from STRREF (string reference to talk table)
        if nodeStruct.hasEntry('STRREF'):
            strref = nodeStruct['STRREF']
            if strref != 0xffffffff:
                self.name = neverglobals.getResourceManager().getDialogString(strref)
        
        # Get the actual resource reference (model/group name)
        if nodeStruct.hasEntry('RESREF'):
            self.resref = nodeStruct['RESREF']
            if isinstance(self.resref, bytes):
                self.resref = self.resref.rstrip(b'\0').decode('latin1', 'ignore')
            else:
                self.resref = str(self.resref).strip('\0')
        
        # Fallback: use resref as name if no STRREF
        if not self.name and self.resref:
            self.name = self.resref
    
    def getName(self):
        """Get the display name of this tile."""
        return self.name or '<unnamed>'
    
    def getResRef(self):
        """Get the resource reference (model/group name)."""
        return self.resref
    
    def getSectionName(self):
        """Get the section this tile belongs to ('Features', 'Groups', or 'Tiles')."""
        return self.section_name
    
    def getBlueprint(self):
        """
        Return None - TileNode represents reference scenery that cannot be painted like objects.
        This prevents crashes when the UI tries to get a blueprint for painting.
        """
        return None
    
    def __str__(self):
        return f'{self.getName()} ({self.section_name})'
    
    def __repr__(self):
        return self.__str__()


class TilesetPalette:
    """
    Represents a tileset-specific palette loaded from a tileset's .itp file.
    These palettes have three sections: Features, Groups, and Tiles (Terrain).
    """
    
    SECTION_NAMES = ['Features', 'Groups', 'Tiles']
    
    def __init__(self, gffRoot, tileset_resref):
        """
        Initialize a TilesetPalette from a tileset's .itp GFF file.
        
        Args:
            gffRoot: GFFStruct (root of the .itp file)
            tileset_resref: The tileset resource reference (e.g., 'tcn01')
        """
        self.tileset_resref = tileset_resref
        self.sections = {}
        
        if gffRoot and gffRoot.hasEntry('MAIN'):
            main_list = gffRoot.getInterpretedEntry('MAIN')
            
            # MAIN should have exactly 3 sections: Features, Groups, Tiles
            for idx, section in enumerate(main_list):
                if idx < len(self.SECTION_NAMES):
                    section_name = self.SECTION_NAMES[idx]
                    
                    # Each section is a GFFStruct with a LIST entry
                    if section.hasEntry('LIST'):
                        tiles = section.getInterpretedEntry('LIST')
                        self.sections[section_name] = [
                            TileNode(tile_struct, section_name) 
                            for tile_struct in tiles
                        ]
                    else:
                        self.sections[section_name] = []
    
    def getTilesetResRef(self):
        """Get the tileset resource reference."""
        return self.tileset_resref
    
    def getSections(self):
        """Get dict of all sections: {'Features': [...], 'Groups': [...], 'Tiles': [...]}"""
        return self.sections
    
    def getTilesForSection(self, section_name):
        """
        Get tiles for a specific section.
        
        Args:
            section_name: 'Features', 'Groups', or 'Tiles'
        
        Returns:
            List of TileNode objects
        """
        return self.sections.get(section_name, [])
    
    @staticmethod
    def getTilesetPalette(tileset_resref):
        """
        Load a tileset's palette from game data.
        
        Args:
            tileset_resref: The tileset resource reference (e.g., 'tcn01')
        
        Returns:
            TilesetPalette object, or None if not found
        """
        try:
            rm = neverglobals.getResourceManager()
            # Try the standard palstd naming: tcn01palstd.itp
            itp_name = tileset_resref.lower() + 'palstd.itp'
            gff = rm.getResourceByName(itp_name)
            if gff:
                return TilesetPalette(gff.getRoot(), tileset_resref)
        except Exception as e:
            logger.warning(f'Failed to load tileset palette for {tileset_resref}: {e}')
        
        return None
