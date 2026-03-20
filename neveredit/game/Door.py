'''Classes for handling door objects, instances and blueprints'''

import logging
logger = logging.getLogger("neveredit")

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
    def _clean_token(value):
        if value is None:
            return ''
        if isinstance(value, bytes):
            value = value.decode('latin1', 'ignore')
        text = str(value).split('\0', 1)[0].strip()
        if not text or text in ('****', 'NULL'):
            return ''
        return text

    @staticmethod
    def _safe_index(value):
        value = Door._clean_token(value)
        if not value:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_model_name(twoda, index, *columns):
        if twoda is None:
            return None
        if index is None or index < 0 or index >= twoda.getRowCount():
            return None
        labels = set(getattr(twoda, 'columnLabels', []) or [])
        for col in columns:
            if labels and col not in labels:
                continue
            try:
                val = twoda.getEntry(index, col)
            except (AttributeError, IndexError, KeyError, TypeError, ValueError):
                continue
            model_token = Door._clean_token(val)
            if not model_token:
                continue
            if model_token.lower().endswith('.mdl'):
                return model_token.lower()
            return model_token.lower() + '.mdl'
        return None

    def _model_from_template(self, rm):
        """Resolve model from the referenced UTD template when needed."""
        try:
            template = self._clean_token(self['TemplateResRef'])
        except (AttributeError, KeyError, TypeError):
            return None
        if not template:
            return None
        try:
            utd = rm.getResourceByName(template.lower() + '.utd')
        except (AttributeError, TypeError, ValueError):
            return None
        if not utd:
            return None

        root = utd.getRoot()
        appearance_idx = self._safe_index(root['Appearance']) if 'Appearance' in root else None
        generic_idx = self._safe_index(root['GenericType']) if 'GenericType' in root else None

        doortypes = rm.getResourceByName('doortypes.2da')
        model_name = self._safe_model_name(doortypes, appearance_idx, 'Model', 'ModelName')
        if model_name:
            return model_name

        genericdoors = rm.getResourceByName('genericdoors.2da')
        return self._safe_model_name(genericdoors, generic_idx, 'ModelName', 'Model')
        
    def getModel(self,copy=False):
        if not copy and self.model:
            return self.model
        rm = neverglobals.getResourceManager()
        index = self._safe_index(self['Appearance'])
        model_name = None
        if index is not None and index >= 0:
            twoda = rm.getResourceByName('doortypes.2da')
            model_name = self._safe_model_name(twoda, index, 'Model', 'ModelName')
        if not model_name:
            index = self._safe_index(self['GenericType'])
            twoda = rm.getResourceByName('genericdoors.2da')
            model_name = self._safe_model_name(twoda, index, 'ModelName', 'Model')
        if not model_name:
            model_name = self._model_from_template(rm)
        if not model_name:
            warning_key = (self['Appearance'], self['GenericType'])
            if warning_key not in Door._missing_model_warnings:
                Door._missing_model_warnings.add(warning_key)
                logger.warning('could not resolve door model from Appearance=%r GenericType=%r',
                               self['Appearance'], self['GenericType'])
            self.modelName = ''
            return None
        self.modelName = model_name
        model = rm.getResourceByName(self.modelName,copy)
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
