from neveredit.game.NeverData import *
from neveredit.file.GFFFile import GFFStruct

import logging
logger = logging.getLogger("neveredit")


class Encounter(LocatedNeverData):
    encounterPropList = {
        'Active': 'Boolean',
        'Difficulty': 'Integer',
        'DifficultyIndex': 'Integer',
        'Faction': 'Integer',
        'LocalizedName': 'CExoLocString',
        'MaxCreatures': 'Integer',
        'OnEntered': 'ResRef,NSS',
        'OnExit': 'ResRef,NSS',
        'OnExhausted': 'ResRef,NSS',
        'OnHeartbeat': 'ResRef,NSS',
        'OnUserDefined': 'ResRef,NSS',
        'PlayerOnly': 'Boolean',
        'RecCreatures': 'Integer',
        'Reset': 'Boolean',
        'ResetTime': 'Integer',
        'Respawns': 'Integer',
        'SpawnOption': 'Integer',
        'Tag': 'CExoString',
        'TemplateResRef': 'ResRef,UTE',
    }

    def __init__(self, gffEntry):
        LocatedNeverData.__init__(self)
        self.addPropList('main', self.encounterPropList, gffEntry)

    def getDescription(self):
        tag = self['Tag'] or ''
        name = self.getName() or 'Encounter'
        if tag:
            return 'Name: ' + name + '\nTag: ' + str(tag)
        return 'Name: ' + name

    def getName(self):
        loc_name = self.gffstructDict['main'].getInterpretedEntry('LocalizedName')
        if loc_name:
            try:
                name = loc_name.getString()
                if name:
                    return name
            except Exception:
                pass
        tag = self['Tag']
        if tag:
            return str(tag)
        return 'Encounter'

    def clone(self):
        gff = self.getGFFStruct('main').clone()
        return self.__class__(gff)

    def getModel(self, copy=False):
        return None


class EncounterBP(Encounter):
    encounterBPPropList = {
        'Comment': 'CExoString',
        'PaletteID': 'Integer,0-255',
        'TemplateResRef': 'ResRef,UTE',
    }

    def __init__(self, gffEntry):
        Encounter.__init__(self, gffEntry)
        self.addPropList('blueprint', self.encounterBPPropList, gffEntry)

    def toInstance(self):
        gff = self.gffstructDict['blueprint'].clone()

        for key in ('Comment', 'PaletteID'):
            if gff.hasEntry(key):
                del gff[key]

        if not gff.hasEntry('XPosition'):
            gff.add('XPosition', 0.0, 'FLOAT')
        if not gff.hasEntry('YPosition'):
            gff.add('YPosition', 0.0, 'FLOAT')
        if not gff.hasEntry('ZPosition'):
            gff.add('ZPosition', 0.0, 'FLOAT')
        if not gff.hasEntry('Geometry'):
            gff.add('Geometry', [], 'List')

        gff.setType(EncounterInstance.GFF_STRUCT_ID)

        instance = EncounterInstance(gff)
        instance.ensureDefaultGeometry()
        return instance


class EncounterInstance(Encounter, NeverInstance):
    GFF_STRUCT_ID = 7
    DEFAULT_GEOMETRY_POINTS = [
        (-1.5, -1.5, 0.0),
        (1.5, -1.5, 0.0),
        (1.5, 1.5, 0.0),
        (-1.5, 1.5, 0.0),
    ]
    encounterInstancePropList = {
        'Geometry': 'Hidden',
        'TemplateResRef': 'ResRef,UTE',
        'XPosition': 'Hidden',
        'YPosition': 'Hidden',
        'ZPosition': 'Hidden',
    }

    def __init__(self, gffEntry):
        if gffEntry.getType() != EncounterInstance.GFF_STRUCT_ID:
            logger.warning('created with gff struct type %r should be %r',
                           gffEntry.getType(),
                           EncounterInstance.GFF_STRUCT_ID)
        Encounter.__init__(self, gffEntry)
        self.addPropList('instance', self.encounterInstancePropList, gffEntry)

    def _ensureGeometryList(self):
        gff = self.getMainGFFStruct()
        geometry = self['Geometry']
        if geometry is not None:
            return geometry
        if gff.hasEntry('Geometry'):
            self['Geometry'] = []
        else:
            gff.add('Geometry', [], 'List')
        geometry = self['Geometry']
        if geometry is None:
            geometry = []
            self['Geometry'] = geometry
        return geometry

    def ensureDefaultGeometry(self):
        geometry = self._ensureGeometryList()
        if geometry:
            return
        for point in self.DEFAULT_GEOMETRY_POINTS:
            self.addPoint(*point)

    def getGeometryPoints(self):
        geometry = self['Geometry'] or []
        return [encounterPoint(pointStruct) for pointStruct in geometry]

    def getX(self):
        return float(self['XPosition'] or 0.0)

    def getY(self):
        return float(self['YPosition'] or 0.0)

    def getZ(self):
        return float(self['ZPosition'] or 0.0)

    def setX(self, x):
        self['XPosition'] = float(x)

    def setY(self, y):
        self['YPosition'] = float(y)

    def setZ(self, z):
        self['ZPosition'] = float(z)

    def getBearing(self):
        return 0.0

    def setBearing(self, b):
        return

    def getObjectId(self):
        return self['ObjectId']

    def getPoint(self, n):
        try:
            pointStruct = self['Geometry'][n]
        except ValueError:
            return None
        except (TypeError, IndexError):
            return None
        return encounterPoint(pointStruct)

    def addPoint(self, x, y, z):
        self._ensureGeometryList()
        s = GFFStruct()
        s.add('X', x, 'FLOAT')
        s.add('Y', y, 'FLOAT')
        s.add('Z', z, 'FLOAT')
        self['Geometry'].append(s)

    def removePoint(self, index):
        del self['Geometry'][index]


class encounterPoint(NeverData):
    pointPropList = {
        'X': 'Hidden',
        'Y': 'Hidden',
        'Z': 'Hidden',
    }

    def __init__(self, gffEntry):
        NeverData.__init__(self)
        self.addPropList('point', self.pointPropList, gffEntry)

    def getX(self):
        return self['X']

    def getY(self):
        return self['Y']

    def getZ(self):
        return self['Z']

    def getCoordinates(self):
        return self.getX(), self.getY(), self.getZ()

    def setCoordinates(self, x, y, z):
        self['X'] = x
        self['Y'] = y
        self['Z'] = z
