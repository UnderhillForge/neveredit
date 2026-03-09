from neveredit.game.NeverData import LocatedNeverData, NeverInstance

import logging

logger = logging.getLogger("neveredit")


class Sound(LocatedNeverData):
    # Keep this conservative: only expose a few commonly present fields and
    # avoid assuming all UTS/GIT variants share identical schemas.
    soundPropList = {
        'Tag': 'CExoString',
        'LocName': 'CExoLocString',
        'TemplateResRef': 'ResRef,UTS',
        'SoundSet': 'ResRef,SSF',
        'SoundResRef': 'ResRef,WAV',
        'Positional': 'Boolean',
        'Continuous': 'Boolean',
        'Volume': 'Integer,0-127',
        'VolumeVrtn': 'Integer,0-127',
        'PitchVariation': 'Integer,0-100',
        'MaxDistance': 'Float',
        'MinDistance': 'Float',
        'RandomPosition': 'Boolean',
        'RandomRangeX': 'Float',
        'RandomRangeY': 'Float',
    }

    def __init__(self, gffEntry):
        LocatedNeverData.__init__(self)
        self.addPropList('main', self.soundPropList, gffEntry)

    def getModel(self, copy=False):
        return None

    def getName(self):
        loc_name = self['LocName']
        try:
            if loc_name:
                text = loc_name.getString()
                if text:
                    return text
        except Exception:
            pass
        tag = self['Tag']
        if tag:
            return tag
        return 'Ambient Sound'

    def clone(self):
        gff = self.getGFFStruct('main').clone()
        return self.__class__(gff)


class SoundInstance(Sound, NeverInstance):
    # GIT struct id is not strictly required for editor use, but we keep a
    # plausible default for diagnostics.
    GFF_STRUCT_ID = 6

    soundInstancePropList = {
        'XPosition': 'Hidden',
        'YPosition': 'Hidden',
        'ZPosition': 'Hidden',
        'XOrientation': 'Hidden',
        'YOrientation': 'Hidden',
    }

    def __init__(self, gffEntry):
        Sound.__init__(self, gffEntry)
        self.addPropList('instance', self.soundInstancePropList, gffEntry)

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
        # Direction is not meaningful for spherical ambient sound regions.
        return

    def getObjectId(self):
        return self['ObjectId']

    def getRadius(self):
        # Prefer explicit attenuation/range fields if present.
        for key in ('MaxDistance', 'Distance', 'Radius', 'RandomRange', 'RandomRangeX', 'RandomRangeY'):
            value = self[key]
            try:
                if value is not None:
                    radius = float(value)
                    if radius > 0.0:
                        return radius
            except (TypeError, ValueError):
                continue
        return 5.0

    def setRadius(self, radius):
        r = max(0.5, float(radius))
        for key in ('MaxDistance', 'Distance', 'Radius', 'RandomRange', 'RandomRangeX', 'RandomRangeY'):
            if self.hasProperty(key):
                self[key] = r
        if self.hasProperty('RandomRangeX'):
            self['RandomRangeX'] = r
        if self.hasProperty('RandomRangeY'):
            self['RandomRangeY'] = r
        # Fallback when schema is sparse.
        self['MaxDistance'] = r