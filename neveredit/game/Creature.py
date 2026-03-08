'''Classes for handling creature objects, instances and blueprints'''

import logging
logger = logging.getLogger("neveredit")

import math

from neveredit.game.NeverData import LocatedNeverData
from neveredit.game.NeverData import NeverInstance
from neveredit.util import neverglobals

class Creature(LocatedNeverData):
    _missing_model_warnings = set()
    creaturePropList = {
        'Appearance_Type':'2daIndex,appearance.2da,STRING_REF,strref,LABEL',
        'BodyBag':'2daIndex,bodybag.2da,Name,strref,Label',
        'Cha': 'Integer,0-50',
#        'ChallengeRating': 'Integer,0-50', ###This is actually a float
        'Con': 'Integer,0-50',
        'Conversation': 'ResRef,DLG',
        'CRAdjust': 'Integer,0-30',
        'CurrentHitPoints': 'Integer,0-1000',
        'Description': 'CExoLocString,4',
        'Dex': 'Integer,0-50',
        'Disarmable': 'Boolean',
        'FactionID': 'Integer,0-1000',
        'FirstName': 'CExoLocString',
        'fortbonus': 'Integer,0-20',
        'Gender': '2daIndex,gender.2da,NAME,strref',
        'GoodEvil': 'Integer, 0-100',
        'HitPoints': 'Integer,0-1000',
        'Int': 'Integer,0-50',
        'Interruptable': 'Boolean',
#        'IsImmortal': 'Boolean',   ### looks like it's only in saved game instances
        'IsPC': 'Boolean',
        'LastName': 'CExoLocString',
        'LawfulChaotic': 'Integer,0-100',
#        'Lootable': 'Boolean',,    ### again, only in saved game instances
        'MaxHitPoints': 'Integer,0-1000',
        'NaturalAC': 'Integer,0-50',
        'NoPermDeath': 'Boolean',
        'PerceptionRange': '2daIndex,ranges.2da,Name,strref,Label',        
        'Plot': 'Boolean',
        'Race': '2daIndex,racialtypes.2da,Name,strref,Label',
        'ScriptAttacked': 'ResRef,NSS',
        'ScriptDamaged': 'ResRef,NSS',
        'ScriptDeath': 'ResRef,NSS',
        'ScriptDialogue': 'ResRef,NSS',
        'ScriptDisturbed': 'ResRef,NSS',
        'ScriptEndRound': 'ResRef,NSS',
        'ScriptHeartbeat': 'ResRef,NSS',
        'ScriptOnBlocked': 'ResRef,NSS',
        'ScriptOnNotice': 'ResRef,NSS',
        'ScriptRested': 'ResRef,NSS',
        'ScriptSpawn': 'ResRef,NSS',
        'ScriptSpellAt': 'ResRef,NSS',
        'ScriptUserDefine': 'ResRef,NSS',
        'SoundSetFile': '2daIndex,soundset.2da,STRREF,strref,LABEL',
#        'StartingPackage': '2daIndex,packages.2da,Name,strref,Label', ### missing
        'Str': 'Integer,0-50',
        'Subrace': 'CExoString',
        'Tail': '2daIndex,tailmodel.2da,LABEL,string',
        'Tag': 'CExoString',
        'WalkRate': '2daIndex,creaturespeed.2da,Name,strref,Label',
        'willbonus': 'Integer,0-30',
        'Wings': '2daIndex,wingmodel.2da,LABEL,string',
        }
            
    def __init__(self,gffEntry):
        LocatedNeverData.__init__(self)
        self.addPropList('main',self.creaturePropList,gffEntry)
        
    def getName(self):
        """Return first and last name of this creature as a single string"""
        return self['FirstName'].getString () + ' ' + self['LastName'].getString ()
    
    def getModel(self,copy=False):
        if not copy and self.model:
            return self.model
        rm = neverglobals.getResourceManager()
        twoda = rm.getResourceByName('appearance.2da')
        try:
            index = int(self['Appearance_Type'])
            if index < 0 or index >= twoda.getRowCount():
                return None
        except (TypeError, ValueError):
            return None
        t = str(twoda.getEntry(index,'MODELTYPE')).strip().upper()

        model_name = None
        if t == 'P':
            # Player-style entries: prefer explicit model columns when present.
            for col in ('MODEL_A', 'MODEL_B', 'MODEL', 'RACE'):
                try:
                    raw = twoda.getEntry(index, col)
                except Exception:
                    continue
                if raw is None:
                    continue
                candidate = str(raw).strip()
                if not candidate or candidate in ('****', 'NULL'):
                    continue
                model_name = candidate.lower() + '.mdl'
                break
        else:
            race = twoda.getEntry(index,'RACE')
            if race and race not in ('****', 'NULL'):
                model_name = str(race).lower() + '.mdl'

        if not model_name:
            warning_key = ('missing-creature-model', index, t)
            if warning_key not in Creature._missing_model_warnings:
                Creature._missing_model_warnings.add(warning_key)
                logger.warning('could not resolve creature model for Appearance_Type=%s (MODELTYPE=%s)', index, t)
            return None

        self.modelName = model_name
        model = rm.getResourceByName(self.modelName,copy)
        if model is None:
            warning_key = ('missing-creature-resource', index, self.modelName)
            if warning_key not in Creature._missing_model_warnings:
                Creature._missing_model_warnings.add(warning_key)
                logger.warning('creature model resource missing for Appearance_Type=%s: %s', index, self.modelName)
            return None
        if not copy:
            self.model = model
        return model

    def getPLTTintContext(self):
        """Return per-creature PLT tint indices when present.

        These fields are available on many creature instances and drive
        player-style PLT coloration in the game.
        """
        field_map = (
            ('Color_Skin', 'skin'),
            ('Color_Hair', 'hair'),
            ('Color_Tattoo1', 'tattoo1'),
            ('Color_Tattoo2', 'tattoo2'),
        )
        context = {}
        for field_name, key in field_map:
            try:
                value = self[field_name]
            except Exception:
                continue
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                context[key] = value
        return context

    def clone(self):
        gff = self.getGFFStruct('main').clone()
        return self.__class__(gff)
    
class CreatureBP (Creature):
    creatureBPPropList = {
        'Comment': 'CExoString',
#        'PaletteID': 'Integer,0-20',
        'TemplateResRef': 'ResRef,UTC',
        }
            
    def __init__(self,gffEntry):
        Creature.__init__(self, gffEntry)
        self.addPropList('blueprint',self.creatureBPPropList,gffEntry)        

    def toInstance(self):
        gff = self.gffstructDict['blueprint'].clone()

        del gff['Comment']
        del gff['PaletteID']
        
        gff.add('XPosition',0.0,'FLOAT')
        gff.add('YPosition',0.0,'FLOAT')
        gff.add('ZPosition',0.0,'FLOAT')
        gff.add('XOrientation',0.0,'FLOAT')
        gff.add('YOrientation',0.0,'FLOAT')

        gff.setType(CreatureInstance.GFF_STRUCT_ID)
        
        return CreatureInstance(gff)

class CreatureInstance (Creature, NeverInstance):
    '''This class represents a creature object stored in a module or saved game.'''
    
    GFF_STRUCT_ID = 4

    creatureInstPropList = {
        'TemplateResRef': 'ResRef,UTC',
        'XOrientation': 'Hidden',
        'YOrientation': 'Hidden',
        'XPosition': 'Hidden',
        'YPosition': 'Hidden',
        'ZPosition': 'Hidden',
        }
            
    def __init__(self,gffEntry):
        if gffEntry.getType() != CreatureInstance.GFF_STRUCT_ID:
            logger.warning("created with gff struct type " 
                           + repr(gffEntry.getType())
                           + " should be " + repr(CreatureInstance.GFF_STRUCT_ID))
        Creature.__init__(self, gffEntry)
        self.addPropList('instance',self.creatureInstPropList,gffEntry)

    def getX(self):
        return self['XPosition']

    def getY(self):
        return self['YPosition']

    def getZ(self):
        return self['ZPosition']

    def setX(self,x):
        self['XPosition'] = x

    def setY(self,y):
        self['YPosition'] = y

    def setZ(self,z):
        self['ZPosition'] = z

    def getBearing(self):        
        return math.atan2(self.getYOrientation(),self.getXOrientation())

    def setBearing(self,b):        
        self['XOrientation'] = math.cos(b)
        self['YOrientation'] = math.sin(b)
        
    def getXOrientation(self):
        return self['XOrientation']

    def getYOrientation(self):
        return self['YOrientation']

    def getObjectId(self):
        return self['ObjectId']

