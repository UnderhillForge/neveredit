'''Classes for handling door objects, instances and blueprints'''

import logging
logger = logging.getLogger("neveredit")

import copy

from neveredit.game.SituatedObject import SituatedObject
from neveredit.game.SituatedObject import SituatedObjectInstance
from neveredit.game.SituatedObject import SituatedObjectBP
from neveredit.util import neverglobals

class Door(SituatedObject):
    _missing_model_warnings = set()
    doorPropList = {
        'AnimationState':'Integer,0-2',
        'LinkedTo':'CExoString',
        'LinkedToFlags':'Integer,0-2',
        'OnClick':'ResRef,NSS',
        'OnFailToOpen':'ResRef,NSS',
        'Appearance':'2daIndex,doortypes.2da,StringRefGame,strref,Label',
        'GenericType':'2daIndex,genericdoors.2da,Name,strref,Label',
        'LoadScreenID':'2daIndex,loadscreens.2da,StrRef,strref,Label'
        }

    def __init__ (self, gffEntry):        
        SituatedObject.__init__ (self, gffEntry)
        self.addPropList ('door', self.doorPropList, gffEntry)

    @staticmethod
    def _safe_index(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_model_name(twoda, index, *columns):
        if index is None or index < 0 or index >= twoda.getRowCount():
            return None
        for col in columns:
            try:
                val = twoda.getEntry(index, col)
            except Exception:
                continue
            if val and val not in ('****', 'NULL'):
                return str(val).lower() + '.mdl'
        return None
        
    def getModel(self,copy=False):
        if not copy and self.model:
            return self.model
        index = self._safe_index(self['Appearance'])
        model_name = None
        if index is not None and index >= 0:
            twoda = neverglobals.getResourceManager()\
                    .getResourceByName('doortypes.2da')
            model_name = self._safe_model_name(twoda, index, 'Model', 'ModelName')
        if not model_name:
            index = self._safe_index(self['GenericType'])
            twoda = neverglobals.getResourceManager()\
                    .getResourceByName('genericdoors.2da')
            model_name = self._safe_model_name(twoda, index, 'ModelName', 'Model')
        if not model_name:
            warning_key = (self['Appearance'], self['GenericType'])
            if warning_key not in Door._missing_model_warnings:
                Door._missing_model_warnings.add(warning_key)
                logger.warning('could not resolve door model from Appearance=%r GenericType=%r',
                               self['Appearance'], self['GenericType'])
            self.modelName = ''
            return None
        self.modelName = model_name
        model = neverglobals.getResourceManager()\
                .getResourceByName(self.modelName,copy)
        if not copy:
            self.model = model
        return model

class DoorBP(Door,SituatedObjectBP):
    def __init__(self,gffEntry):
        SituatedObjectBP.__init__(self,gffEntry)
        Door.__init__(self,gffEntry)        

    def toInstance(self):
        gff = self.makeInstanceGFF()
        gff.setType(DoorInstance.GFF_STRUCT_ID)
        return DoorInstance(gff)
    
class DoorInstance(Door,SituatedObjectInstance):

    GFF_STRUCT_ID = 8
    
    def __init__ (self, gffEntry):
        if gffEntry.getType() != DoorInstance.GFF_STRUCT_ID:
            logger.warning("created with gff struct type "
                           + repr(gffEntry.getType())
                           + " should be " + repr(DoorInstance.GFF_STRUCT_ID))     
        SituatedObjectInstance.__init__ (self, gffEntry)
        Door.__init__ (self, gffEntry)
