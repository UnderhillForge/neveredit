import logging
logger = logging.getLogger("neveredit.ui")

import string

import wx
import wx.lib.scrolledpanel as scrolled
import wx.lib.rcsizer as rcs
from wx.lib.buttons import GenButton

from neveredit.ui import WxUtils
from neveredit.ui.HAKListControl import HAKListControl
from neveredit.ui.SoundControl import SoundControl
from neveredit.ui.VarTableControl import VarListControl

from neveredit.game.ChangeNotification import ResourceListChangeListener
from neveredit.game.ChangeNotification import PropertyChangeNotifier

from neveredit.file.GFFFile import GFFStruct
import neveredit.file.Language

from neveredit.util import neverglobals
import neveredit.util.Preferences

def cleanstr(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('latin1', 'ignore')
    return str(value)
#    import string
#    allchars = string.maketrans('','')
#    delchars = ''.join([c for c in allchars if c not in string.printable])
#    return str.translate(allchars,delchars)

class NoCaseString(str):
    def __init__(self,s):
        str.__init__(self,s)
        self.low = s.lower()

    def __eq__(self,s):
        return self.low.__eq__(s.lower())

    def __hash__(self):
        return self.low.__hash__()
    
class PropControl(PropertyChangeNotifier):
    def __init__(self,control):
        PropertyChangeNotifier.__init__(self)
        self.control = control

class CExoLocStringControl(wx.BoxSizer):
    def __init__(self,typeSpec,prop,propWindow, defaultlang=0):
        # the defaultlang parameter should be the BIOWARE code for the language
        # see file/Language or Bioware documentation for those codes
        wx.BoxSizer.__init__(self,wx.VERTICAL)

        langChoices = neveredit.file.Language.BIOorderedLangs
        genderChoices = ['Default', 'Female']

        # TODO change this to use some default value fetched from preferences
        self.langID = defaultlang
        self.gender = 0
        self.prop = prop

        insideHorizSizer = wx.BoxSizer(wx.VERTICAL)
        choiceSizer = wx.BoxSizer(wx.VERTICAL)

        if len(typeSpec) > 1 and int(typeSpec[1]) > 1:
            self.textCtrl = wx.TextCtrl(propWindow,-1,'',
                                       wx.DefaultPosition,
                                       (250,int(typeSpec[1])*24),
                                       style=wx.TE_MULTILINE)
        else:
            self.textCtrl = wx.TextCtrl(propWindow,-1,'',
                                       wx.DefaultPosition,
                                       (250,24))                
        self.textCtrl.Bind(wx.EVT_TEXT, propWindow.controlUsed)

        self.label = wx.StaticText(propWindow,-1,'')

        self.langIDChoice = wx.Choice(propWindow,-1,choices=langChoices)
        self.langIDChoice.SetSelection(
            neveredit.file.Language.convertFromBIOCode(self.langID))
        self.langIDChoice.Bind(wx.EVT_CHOICE, self.langSelection)

        self.genderChoice = wx.Choice(propWindow,-1,choices=genderChoices)
        self.genderChoice.SetSelection(self.gender)
        self.genderChoice.Bind(wx.EVT_CHOICE, self.langSelection)

        choiceSizer.Add(self.langIDChoice, 0, wx.ALL, 5)
        choiceSizer.Add(self.genderChoice, 0, wx.ALL, 5)

        self.fetchText()

        insideHorizSizer.Add(self.textCtrl, 0, wx.EXPAND | wx.ALL, 0)
        insideHorizSizer.Add(choiceSizer)
        self.Add(self.label, 0, wx.ALL, 5)
        self.Add(insideHorizSizer, 0, wx.EXPAND | wx.ALL, 0)

    def fetchText(self):
        (text,index) = self.prop.getValue().getStringAndIndex(self.langID,self.gender)
        exp_index = self.langID * 2 + self.gender
        if exp_index != index:
            self.label.SetLabel("This is a stock NWN application string.")
        else:
            self.label.SetLabel("This is a string from the current module.")
        self.textCtrl.SetValue(text)
  
    def langSelection(self,event):
        self.langID = neveredit.file.Language.convertToBIOCode(self.langIDChoice.GetSelection())
        self.gender = self.genderChoice.GetSelection()
        self.fetchText()

    def Destroy(self):
        self.label.Destroy()
        self.textCtrl.Destroy()
        self.langIDChoice.Destroy()
        self.genderChoice.Destroy()
        wx.BoxSizer.Destroy(self)

    def GetValue(self):
        return self.textCtrl.GetValue()

    def applyPropControlValue(self):
        self.prop.getValue().setString(self.GetValue(),self.langID,self.gender)

    def GetId(self):
        return self.textCtrl.GetId()

class PropWindow(scrolled.ScrolledPanel, ResourceListChangeListener):
    propControls = {}
    propLabels = []

    def __init__(self,parent):
        scrolled.ScrolledPanel.__init__(self,parent,-1)
        self.propGrid = wx.GridBagSizer()
        self.propGrid.AddGrowableCol(0)
        self.SetSizer(self.propGrid)
        self.SetAutoLayout(True)
        self.SetupScrolling(scroll_x=False)        
        self.propsChanged = False
        self.changeObserver = None
        self.item = None
        self.visualChanged = False
        
        self.propLabels = []
        self.lines = []
        self.propControls = {}        
        # get default language preference for CEXOLocStrings
        p = neveredit.util.Preferences.getPreferences()
        self.defaultlang = p['DefaultLocStringLang']
         
    def getControlByPropName(self,name):
        for propControl,prop in list(self.propControls.values()):
            if prop.getName() == name:
                return propControl
        return None

    def resourceListChanged(self):
        self.updateControls()

    def updateControls(self):
        for propControl,prop in list(self.propControls.values()):
            typeSpec = prop.getSpec()
            if typeSpec[0] == "ResRef":
                self.updateResRefControl(propControl.control,typeSpec,prop)
                self.updateSoundSetControlState(propControl.control, typeSpec, prop)
            elif typeSpec[0] == "CExoString" and len(typeSpec) > 1:
                self.updateCustomChoiceControl(propControl.control,typeSpec,prop)

    def isSoundSetResRef(self, typeSpec, prop):
        if not typeSpec or typeSpec[0] != 'ResRef':
            return False
        if len(typeSpec) > 1 and str(typeSpec[1]).upper() == 'SSF':
            return True
        name = str(prop.getName() or '').lower()
        return name == 'soundset'

    def isAttenuationModelProp(self, typeSpec, prop):
        if not typeSpec or typeSpec[0] != 'Integer':
            return False
        if len(typeSpec) < 2 or str(typeSpec[1]) != '0-1':
            return False
        name = str(prop.getName() or '').lower()
        return name == 'attenuationmodel'

    def isSoundSetEventProp(self, typeSpec, prop):
        if not typeSpec or typeSpec[0] != 'Integer':
            return False
        name = str(prop.getName() or '').lower()
        return name == 'soundsetevent'

    def ensureIntegerEntry(self, prop, value):
        if not self.item or not hasattr(self.item, 'getMainGFFStruct'):
            return int(value)
        gff = self.item.getMainGFFStruct()
        key = prop.getName()
        if not gff.hasEntry(key):
            gff.add(key, int(value), 'INT')
        return int(value)

    def makeAttenuationModelChoiceControl(self, prop, parent):
        choices = ['Linear', 'Inverse']
        control = wx.Choice(parent, -1, choices=choices)
        try:
            value = int(prop.getValue())
        except Exception:
            value = 0
        if value < 0:
            value = 0
        if value > 1:
            value = 1
        control.SetSelection(value)
        control.Bind(wx.EVT_CHOICE, self.controlUsed)
        return control

    def _normalizeResRefValue(self, value):
        if value is None:
            return ''
        if isinstance(value, bytes):
            return value.decode('latin1', 'ignore').strip('\0').strip()
        return str(value).strip('\0').strip()

    def _soundSetExists(self, resref):
        if not resref:
            return True
        rm = neverglobals.getResourceManager()
        candidates = [resref]
        if not resref.lower().endswith('.ssf'):
            candidates.insert(0, resref + '.ssf')
        for candidate in candidates:
            try:
                if rm.getResourceByName(candidate) is not None:
                    return True
            except Exception:
                continue
        return False

    def updateSoundSetControlState(self, control, typeSpec, prop):
        if control is None or not self.isSoundSetResRef(typeSpec, prop):
            return

        if not hasattr(control, '_neveredit_default_bg'):
            control._neveredit_default_bg = control.GetBackgroundColour()

        value = self._normalizeResRefValue(control.GetValue())
        if not value:
            control.SetToolTip('Optional SSF sound set resref.')
            control.SetBackgroundColour(control._neveredit_default_bg)
            control.Refresh()
            return

        exists = self._soundSetExists(value)
        if exists:
            control.SetToolTip('SSF found: %s' % value)
            control.SetBackgroundColour(control._neveredit_default_bg)
        else:
            control.SetToolTip('Missing SSF resource: %s' % value)
            control.SetBackgroundColour(wx.Colour(255, 220, 220))
        control.Refresh()
    
    def makePropsForItem(self,item,observer=None):
        '''Make all property controls for a given item.
        The item must be implementing the NeverData interface.'''
        logger.debug("making props for " + repr(item))
        self.cleanPropPage()
        neverglobals.getResourceManager().addResourceListChangeListener(self)
        self.changeObserver = observer
        first = True
        minWidth = 0
        self.item = item
        for p in item:
            if p.getValue() == None:
                logger.debug('empty prop for "' + p.getName() + '"')
                continue
            if p.getName() == 'Mod_Hak':
                item.removeProperty(p.getName())
            else:
                (label,propControl) = self.makeControlForProp(p,self)
                control = propControl.control
                if control:
                    # add here specific notification cases
                    spec = p.getSpec()
                    if len(spec)>1:
                        if p.getSpec()[1] == 'FactionName':
                            propControl.addPropertyChangeListener(self.mainAppWindow)
                if control:
                    logger.debug("made control for " + p.getName())
                    self.propControls[control.GetId()] = (propControl,p)
                    if first:
                        line = wx.StaticLine(self,-1,
                                             style=wx.LI_HORIZONTAL)
                        self.propGrid.Add(line,pos=(0,0),
                                          span=(1,3),flag=wx.EXPAND)
                        self.lines.append(line)
                        first = False
                        
                    r = 2*len(self.propControls)
                    self.propGrid.Add(label, pos=(r,0),
                                      flag=wx.ALIGN_LEFT|wx.LEFT, border=10)                    
                    self.propLabels.append(label)
                    self.propGrid.Add(control, pos=(r,2),
                                      flag=wx.ALIGN_RIGHT|wx.RIGHT, border=10)
                    line = wx.StaticLine(self,-1,style=wx.LI_HORIZONTAL)
                    self.propGrid.Add(line,pos=(r+1,0),span=(1,3),flag=wx.EXPAND)
                    self.lines.append(line)
                elif not p.getSpec()[0] == 'Hidden':
                    print('Error: unhandled prop type',p.getSpec())
                    if label:
                        label.Destroy()
            if control:
                width = control.GetSize()[0] + label.GetSize()[0] + 10
                if width > minWidth:
                    minWidth = width
        self.propsChanged = False
        self.propGrid.Layout()
        #self.propGrid.SetVirtualSizeHints(self)
        self.FitInside()
        logger.debug("done making props")
        
    def applyPropControlValues(self,item):
        '''This method reads back in the values of currently displayed
        property controls and updates the actual module file to reflect
        these values.'''
        if not self.propsChanged:
            return False
        logger.debug('applying prop control values')
        for propControl in list(self.propControls.values()):
            control = propControl[0].control
            prop = propControl[1]
            typeSpec = prop.getSpec()
            pName = typeSpec[0]
            if pName == 'CExoLocString':
                control.applyPropControlValue()
            elif pName == 'CExoString':
                if len(typeSpec) > 1:
                    prop.setValue(control.GetStringSelection())
                else:
                    prop.setValue(control.GetValue())
            elif pName == 'Percentage':
                prop.setValue(control.GetValue())
            elif pName == 'Boolean':
                prop.setValue(int(control.GetValue()))
            elif pName == 'Integer':
                if self.isAttenuationModelProp(typeSpec, prop):
                    value = self.ensureIntegerEntry(prop, int(control.GetSelection()))
                    prop.setValue(value)
                elif self.isSoundSetEventProp(typeSpec, prop):
                    value = self.ensureIntegerEntry(prop, int(control.GetValue()))
                    prop.setValue(value)
                else:
                    prop.setValue(int(control.GetValue()))
            elif pName == 'BGRColour':
                c = control.GetBackgroundColour()
                prop.setValue((c.Blue() << 16) | (c.Green() << 8) | c.Red())
            elif pName == 'ResRef':
                prop.setValue(control.GetValue())
            elif pName == 'Script':
                s = control.getScript(prop.getName())
                prop.setValue(s.replace('\n','\r\n'))
            elif pName == 'List':
                type = prop.getSpec()[1]
                sel_list = []
                if type == 'HAKs':
                    haknames = control.GetStringSelections()
                    for hakFileName in haknames:
                        s = GFFStruct()
                        s.add('Mod_Hak',hakFileName,'CExoString')
                        logger.info(repr(s)+" "+s['Mod_Hak'])
                        sel_list.append(s)
                elif type == 'Vars':
                    sel_list = control.GetData()
                prop.setValue(sel_list)
            elif pName == 'CheckList':
                type = prop.getSpec()[1]
                checkedList = []
#                if type == 'HAKs':
#                    for i in range(control.GetCount()):
#                        if control.IsChecked(i):
#                            hakFileName = control.GetString(i)
#                            s = GFFStruct()
#                            s.add('Mod_Hak',hakFileName, "CExoString")
#                            print s,s['Mod_Hak']
#                            checkedList.append(s)
                prop.setValue(checkedList)
            elif pName == '2daIndex':
                prop.setValue(int(control.GetSelection()))
            elif pName == 'Hidden' or pName == 'Portrait':
                pass
            else:
                print(_('error, unknown prop type:'),pName)
            item.setProperty(prop.getName(),prop.getValue())
        if self.visualChanged:
            self.item.forceModelReload()
            neverglobals.getResourceManager().visualChanged(self.item)
        tmp = self.propsChanged
        self.propsChanged = False
        self.visualChanged = False
        return tmp
        
    def makeControlForProp(self,prop,parent):
        '''Make a wxWindows control for the given NWN property and add
        it to the given parent wxWindow.'''
        control = None
        typeSpec = prop.getSpec()
        type = typeSpec[0]
        if type == 'CExoLocString':
            control = CExoLocStringControl(typeSpec,prop,self,self.defaultlang)
        elif type == 'CExoString':
            if len(typeSpec) > 1:
                if typeSpec[1] != 'FactionName':
                    control = self.makeCustomChoiceControl(typeSpec, prop, parent)
                else:
                    control = wx.TextCtrl(parent,-1,prop.getValue(),wx.DefaultPosition,\
                                                        (250,24),style=wx.TE_PROCESS_ENTER)
                    control.Bind(wx.EVT_TEXT_ENTER, self.controlUsed)
            else:
                control = wx.TextCtrl(parent,-1,prop.getValue(),wx.DefaultPosition,(250,24))
                control.Bind(wx.EVT_TEXT, self.controlUsed)
        elif type == 'Percentage':
            control = wx.SpinCtrl(parent,-1)
            control.SetRange(0,100)
            control.SetValue(prop.getValue())
            control.Bind(wx.EVT_SPINCTRL, self.controlUsed)
            #control.SetTickFreq(5,0)
        elif type == 'Boolean':
            control = wx.CheckBox(parent,-1,'')
            control.SetValue(prop.getValue())
            control.Bind(wx.EVT_CHECKBOX, self.controlUsed)
        elif type == 'Integer':
            if self.isAttenuationModelProp(typeSpec, prop):
                control = self.makeAttenuationModelChoiceControl(prop, parent)
            else:
                min = 0
                max = 100
                if len(typeSpec) > 1:
                    maxMin = typeSpec[1].split('-')
                    min = int(maxMin[0])
                    max = int(maxMin[1])
                control = wx.SpinCtrl(parent,-1)
                control.SetRange(min,max)
                try:
                    control.SetValue(prop.getValue())
                except OverflowError:
                    # I got that with some factions that have 0xFFFFFFFF as parents
                    # and as they shouldn't be edited anyway..
                    control.SetValue(-1)
                    control.Disable()
                control.Bind(wx.EVT_SPINCTRL, self.controlUsed)
                control.Bind(wx.EVT_TEXT, self.controlUsed)
        elif type == "ResRef":
            control = self.makeResRefControl(typeSpec, prop, parent)
            self.updateSoundSetControlState(control, typeSpec, prop)
        elif type == "BGRColour":
            blue = prop.getValue() >> 16
            green = (prop.getValue() >> 8) & (0xff)
            red = prop.getValue() & (0xff)            
            control = GenButton(parent,-1,'',wx.DefaultPosition,
                                  wx.Size(40,40))
            control.SetBezelWidth(0)
            control.SetForegroundColour(wx.Colour(red,green,blue))
            control.SetBackgroundColour(wx.Colour(red,green,blue))
            control.Bind(wx.EVT_BUTTON, self.handleColourButton)
        elif type == "List":
            if typeSpec[1] == 'HAKs':
                control = HAKListControl(prop, parent)
            elif typeSpec[1] == 'Vars':
                control = VarListControl(prop,parent)
        elif type == "CheckList":
            choices = []
#            if typeSpec[1] == 'HAKs':
#                choices = [x['Mod_Hak'].lower()
#                           for x in prop.getValue()]
#                choices.extend([x.split('.')[0].lower() for x in
#                                neverglobals.getResourceManager().getHAKFileNames()
#                                if x.split('.')[0].lower() not in choices])
            control = wx.CheckListBox(parent,-1,
                                     wx.DefaultPosition,(200,200),choices)
            for i in range(len(choices)):
                control.Check(i,False)
#            for n in prop.getValue():
#                control.Check(choices.index(n['Mod_Hak'].lower()))
            control.Bind(wx.EVT_CHECKLISTBOX, self.controlUsed)
        elif type == '2daIndex':
            twoda = neverglobals.getResourceManager().getResourceByName(typeSpec[1])
            choices = []
            col = typeSpec[2]
            if typeSpec[3] == 'strref':
                for i in range(twoda.getRowCount()):
                    entry = 'invalid'
                    try:
                        raw_strref = twoda.getEntry(i,col)
                        strref = int(raw_strref)
                        entry = neverglobals.getResourceManager().getDialogString(strref)
                        if entry is None:
                            # Keep rows selectable even when dialog.tlk has no matching string.
                            entry = 'StrRef %d' % strref
                    except (TypeError, ValueError):
                        if len(typeSpec) > 4:
                            entry = twoda.getEntry(i,typeSpec[4])
                    if entry is None:
                        entry = 'invalid'
                    choices.append(entry)
            else:
                choices = [twoda.getEntry(i,col)
                           for i in range(twoda.getRowCount())]
            if typeSpec[1] in ['ambientmusic.2da','ambientsound.2da','soundset.2da']:
                # may be used for other 2das in the future
                control = SoundControl(prop,parent,choices,typeSpec[1])
            else:
                control = wx.Choice(parent,-1,choices=[cleanstr(s) for s in choices])
            control.SetSelection(prop.getValue())
                
        elif type == 'Portrait':
            p = neverglobals.getResourceManager().getPortraitByIndex(prop.getValue(),'s')
            if p:
                control = wx.BitmapButton(parent,-1,WxUtils.bitmapFromImage(p))
                control.Bind(wx.EVT_BUTTON, self.handlePortraitButton)
            else:
                logger.error('unknown portrait index:'+str(prop.getValue()))
                from PIL import Image, ImageDraw, ImageFont
                image = Image.new("1",(32,64))
                font = ImageFont.load_default()
                draw = ImageDraw.Draw(image)
                draw.text((3,3),"portrait not found",font=font)
                control = wx.BitmapButton(parent,-1,WxUtils.bitmapFromImage(image))
                control.Bind(wx.EVT_BUTTON, self.handlePortraitButton)
        if control:
            label = wx.StaticText(self,-1,prop.getName().split('.')[-1])
        else:
            label = None
        return (label,PropControl(control))


    def makeCustomChoiceControl(self, typeSpec, prop, parent):
        keyList, index = self.getCustomChoiceList(typeSpec, prop)
        control = wx.Choice(parent,-1,choices=keyList)                
        control.SetSelection(index)
        control.Bind(wx.EVT_CHOICE, self.controlUsed)
        return control

    def updateCustomChoiceControl(self, control, typeSpec, prop):        
        keyList, index = self.getCustomChoiceList(typeSpec, prop)
        control.Clear()
        control.AppendItems(keyList)
        control.SetSelection(index)
    
    def getCustomChoiceList(self, typeSpec, prop):
        tags = []
        if typeSpec[1] == "Creature_Tags":
            module = neverglobals.getResourceManager().module
            if module:
                for ctags in [d['creatures'] for d in list(module.getTags()['areas'].values())]:
                    tags.extend(ctags)
        selection = prop.getValue()
        try:
            index = tags.index(selection)
        except ValueError:
            tags.append(selection)
            index = len(tags) - 1
        return tags, index

    def makeResRefControl(self, typeSpec, prop, parent):
        if len(typeSpec) > 1:
            keyList, index = self.getResRefList(typeSpec, prop)
            control = wx.ComboBox(parent, -1, choices=keyList,
                                  style=wx.CB_DROPDOWN)
            if len(prop.getValue()) > 0:
                control.SetSelection(index)
            else:
                control.SetSelection(0)
            control.Bind(wx.EVT_COMBOBOX, self.controlUsed)
            control.Bind(wx.EVT_TEXT, self.controlUsed)
        else:
            control = wx.TextCtrl(parent,-1,prop.getValue())
            control.Bind(wx.EVT_TEXT, self.controlUsed)
        return control

    def updateResRefControl(self, control, typeSpec, prop):        
        if len(typeSpec) > 1:
            keyList, index = self.getResRefList(typeSpec, prop)
            control.Clear()
            control.AppendItems(keyList)
            if len(prop.getValue()) > 0:
                control.SetSelection(index)
            else:
                control.SetSelection(0)
    
    def getResRefList(self, typeSpec, prop):
        keys = neverglobals.getResourceManager().getDirKeysWithExtensions(typeSpec[1])
        keyList = [''] #can leave empty
        for key in keys:
            resref = key[0]
            if isinstance(resref, bytes):
                resref = resref.rstrip(b'\0').decode('latin1', 'ignore')
            else:
                resref = str(resref).strip('\0')
            keyList.append(resref)
        selection = prop.getValue()
        try:
            index = keyList.index(selection)
        except ValueError:
            keyList.append(selection)
            index = len(keyList) - 1
        return keyList, index

    def handleColourButton(self,event):
        '''Callback for the colour selection button.'''
        if not event.GetId() in self.propControls:
            #happens during construction
            return
        control = self.propControls[event.GetId()][0].control
        cd = wx.ColourData()
        cd.SetColour(control.GetBackgroundColour())
        dlg = wx.ColourDialog(self,cd)
        if dlg.ShowModal() == wx.ID_OK:
            cd = dlg.GetColourData()
            control.SetBackgroundColour(cd.GetColour())
            self.controlUsed(event)
            
    def handlePortraitButton(self,event):
        '''Callback for the portrait selection button'''
        portraits = neverglobals.getResourceManager().getPortraitNameList()
        # not finished!

    def cleanPropPage(self):
        '''Clean up the prop page, removing all labels and controls.'''
        for l in self.propLabels:
            self.propGrid.Detach(l)
            l.Destroy()
        for l in self.lines:
            self.propGrid.Detach(l)
            l.Destroy()
        for c,p in list(self.propControls.values()):
            self.propGrid.Detach(c.control)
            c.control.Destroy()
        self.propControls = {}
        self.propLabels = []
        self.lines = []
        #self.propGrid.AddGrowableCol(1)
        neverglobals.getResourceManager().removeResourceListChangeListener(self)

    def controlUsed(self,event):
        '''Callback for a control being used. Sets a dirty flag.'''
        if not event.GetId() in self.propControls:
            #happens during construction
            return
        propControl,prop = self.propControls[event.GetId()]
        self.updateSoundSetControlState(propControl.control, prop.getSpec(), prop)
        if prop.getName().find('Appearance') != -1:
            self.visualChanged = True
        self.propsChanged = True
        propControl.propertyChanged(propControl,prop)
        if self.changeObserver:
            self.changeObserver.setFileChanged(True)

