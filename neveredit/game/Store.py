"""Store/merchant blueprint classes for the NWN palette."""
import logging
logger = logging.getLogger('neveredit')

from neveredit.game.NeverData import NeverData


class Store(NeverData):
    storePropList = {
        'LocalizedName': 'CExoLocString',
        'Tag': 'CExoString',
        'TemplateResRef': 'ResRef,UTM',
        'StoreGold': 'Integer',
        'WillNotBuy': 'List,ItemTypes',
        'WillOnlyBuy': 'List,ItemTypes',
        'OnOpenStore': 'ResRef,NSS',
        'OnCloseStore': 'ResRef,NSS',
    }

    def __init__(self, gffEntry):
        NeverData.__init__(self)
        self.addPropList('main', self.storePropList, gffEntry)

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
        return 'Store'

    def getPortrait(self, size):
        return None

    def getDescription(self):
        name = self.getName() or 'Store'
        tag = self['Tag'] or ''
        if tag:
            return 'Name: ' + name + '\nTag: ' + str(tag)
        return 'Name: ' + name

    def clone(self):
        gff = self.getGFFStruct('main').clone()
        return self.__class__(gff)


class StoreBP(Store):
    """Blueprint loaded from a .UTM resource (store palette entry)."""
    storeBPPropList = {
        'Comment': 'CExoString',
        'PaletteID': 'Integer,0-255',
        'TemplateResRef': 'ResRef,UTM',
    }

    def __init__(self, gffEntry):
        Store.__init__(self, gffEntry)
        self.addPropList('blueprint', self.storeBPPropList, gffEntry)

    def toInstance(self):
        # Stores are not placed directly on a map area in NWN.
        return None
