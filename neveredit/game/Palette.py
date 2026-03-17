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
