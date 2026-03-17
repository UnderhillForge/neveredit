"""Classes to find resources in modules, hak packs and the game directory
and delegate their interpretation. Also contains change notification
mechanisms and various resource name/key conversion functions."""

#standard lib
import os,os.path,sys
import io
import logging
logger = logging.getLogger("neveredit.game")
Set = set

#external lib
from PIL import Image

#neveredit
from neveredit.util.Progressor import Progressor
import neveredit.file.MDLFile
import neveredit.file.KeyFile
import neveredit.file.ERFFile
import neveredit.file.GFFFile
import neveredit.file.TalkTableFile
import neveredit.file.TwoDAFile
import neveredit.file.TileSetFile
from neveredit.game.ChangeNotification import VisualChangeNotifier
from neveredit.game.ChangeNotification import ResourceListChangeNotifier
import neveredit.game.Module
import neveredit.game.Script

class ResourceManager(Progressor,VisualChangeNotifier,ResourceListChangeNotifier):
    '''The resource manager is a global object that takes care of loading
    an interpreting resources from the nwn install dir. You can get
    the instance of this class from neverglobals.getResourceManager().'''
    RESOURCETYPES = {
        'INVALID' : 0xFFFF,
        'BMP'     : 1,
        'TGA'     : 3,
        'WAV'     : 4,
        'PLT'     : 6,
        'INI'     : 7,
        'TXT'     : 10,
        'MDL'     : 2002,
        'NSS'     : 2009,
        'NCS'     : 2010,
        'ARE'     : 2012,
        'SET'     : 2013,
        'IFO'     : 2014,
        'BIC'     : 2015,
        'WOK'     : 2016,
        '2DA'     : 2017,
        'TXI'     : 2022,
        'GIT'     : 2023,
        'UTI'     : 2025,
        'UTC'     : 2027,
        'DLG'     : 2029,
        'ITP'     : 2030,
        'UTT'     : 2032,
        'DDS'     : 2033,
        'UTS'     : 2035,
        'LTR'     : 2036,
        'GFF'     : 2037,
        'FAC'     : 2038,
        'UTE'     : 2040,
        'UTD'     : 2042,
        'UTP'     : 2044,
        'DFT'     : 2045,
        'GIC'     : 2046,
        'GUI'     : 2047,
        'UTM'     : 2051,
        'DWK'     : 2052,
        'PWK'     : 2053,
        'JRL'     : 2056,
        'UTW'     : 2058,
        'SSF'     : 2060,
        'NDB'     : 2064,
        'PTM'     : 2065,
        'PTT'     : 2066}

    RESOURCEEXTENSIONS = dict(zip(list(RESOURCETYPES.values()),list(RESOURCETYPES.keys())))

    GFFFILETYPES = ['ARE','IFO','BIC','GIT','UTI','UTC','DLG','ITP','UTT',
                    'UTS','GFF','FAC','UTE','UTD','UTP','GIC','GUI','UTM',
                    'JRL','UTW','PTM','PTT']

    KEYFILES = ['chitin.key','patch.key','xp1.key','xp1patch.key',
                'xp2.key','xp2patch.key',
                'nwn_base.key','nwn_retail.key']

    QUIET_MISSING_TGA_RESREFS = set(['deepwater', 'nonwalk', 'stone', 'w_stone', 'wood'])
    # Fallback tint colors for PLT layers when no appearance-specific palette
    # mapping is available in this legacy renderer.
    PLT_LAYER_BASE = {
        0: (214, 171, 136),  # skin
        1: (86, 62, 44),     # hair
        2: (150, 150, 165),  # metal1
        3: (120, 90, 60),    # leather
        4: (130, 130, 145),  # metal2
        5: (92, 92, 124),    # minor
        6: (128, 110, 90),   # major
    }
    PLT_LAYER_PALETTES = {
        0: 'pal_skin01',
        1: 'pal_hair01',
        2: 'pal_armor01',
        3: 'pal_leath01',
        4: 'pal_armor02',
        5: 'pal_cloth01',
        6: 'pal_cloth01',
    }
    
    appDir = ''

    def __init__(self):
        """
        Create a new resource manager object. This will not load the
        info from a game dir. You need to call L{scanGameDir} for that.
        Instead of manually making a resource manager, it is recommended
        you call L{neveredit.util.neverglobals.getResourceManager} which
        will use the user's preference settings to find the game dir and
        initialize the manager.
        """
        Progressor.__init__(self)
        VisualChangeNotifier.__init__(self)
        ResourceListChangeNotifier.__init__(self)
        self.cache = {}
        self._missingResourceWarnings = set()
        self._pltPaletteCache = {}
        self.clear()
        self.module = None
        
    def clear(self):
        '''Discard all info this resource manager has loaded.'''
        self._missingResourceWarnings = set()
        self.keyResourceKeys = {}
        self.dirResourceKeys = {}
        self.hakResourceKeys = {}
        self.resourcesByType = {}
        self.hakFileNames = []
        self.hakFilePaths = {}
        self.hakDirectories = []
        self.mainDialogFile = None
        self.customTlkFile = None
        self.modMap = {}
        self.module = None
        self.BMUFileNames = []
        self.ambientSoundFileNames = []
        self._pltPaletteCache = {}

    def _logMissingResource(self, key):
        if key in self._missingResourceWarnings:
            return
        self._missingResourceWarnings.add(key)

        resref = ResourceManager.normalizeResRef(key[0]) if isinstance(key, tuple) and len(key) == 2 else ''
        rtype = key[1] if isinstance(key, tuple) and len(key) == 2 else None
        if rtype == self.RESOURCETYPES['TGA'] and resref in self.QUIET_MISSING_TGA_RESREFS:
            logger.debug('optional tile texture not found for ' + repr(key))
            return
        logger.error('cannot find resource for ' + repr(key) + 'in any added lists')

    def resTypeFromExtension(cls,ext):
        '''Class method that converts a resource type into a string extension'''
        return cls.RESOURCETYPES[ext.upper()]
    resTypeFromExtension = classmethod(resTypeFromExtension)
    
    def extensionFromResType(cls,type):
        '''Class method that converts a three letter string extension
        into a numerical resource type.'''
        try:
            return cls.RESOURCEEXTENSIONS[type]
        except KeyError:
            logger.error('type ' + repr(type) + 'unknown resource type')
            return 'UNK'
    extensionFromResType = classmethod(extensionFromResType)

    def normalizeResRef(cls, raw):
        if isinstance(raw, bytes):
            # NWN resrefs are NUL-terminated in a fixed-width field.
            # Truncate at the first NUL to ignore padding/garbage bytes.
            return raw.split(b'\0', 1)[0].decode('latin1', 'ignore').strip().lower()
        return str(raw).split('\0', 1)[0].strip().lower()
    normalizeResRef = classmethod(normalizeResRef)
    
    def nameFromKey(cls,key):
        '''Class method that converts a key into a filename.
        @param key: the key to convert
                    (16 byte resref,numerical resource type tuple)
        @return: the corresponding filename with extension
        '''
        return cls.normalizeResRef(key[0]) + '.' + cls.extensionFromResType(key[1])
    nameFromKey = classmethod(nameFromKey)
    
    def keyFromName(cls,name):
        '''Class method that converts a filename into a key.
        @param name: the filename (including extension) to convert
        @return: (16 byte resref,numerical resource type).'''
        parts = name.split('.')
        resref = cls.normalizeResRef(parts[0])
        k1 = resref[:16] + (16-len(resref[:16]))*'\0'
        try:
            k2 = cls.resTypeFromExtension(parts[1])
        except KeyError:
            #logger.error('unknown extension "' + parts[1].upper() + '"')
            raise ValueError('unknown nwn extension .' + parts[1])
        return (k1,k2)
    keyFromName = classmethod(keyFromName)

    def _candidateResourceKeys(self, key):
        """Return equivalent key spellings for tolerant lookups."""
        if not isinstance(key, tuple) or len(key) != 2:
            return [key]
        resref, rtype = key
        normalized = ResourceManager.normalizeResRef(resref)
        text16 = (normalized[:16] + (16 - len(normalized[:16])) * '\0')
        byte16 = text16.encode('latin1', 'ignore')

        candidates = [key, (text16, rtype), (normalized, rtype)]
        if isinstance(resref, bytes):
            candidates.append((normalized.encode('latin1', 'ignore'), rtype))
        else:
            candidates.append((byte16, rtype))

        unique = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique

    def _findProviderAndKey(self, key):
        for candidate in self._candidateResourceKeys(key):
            if candidate in self.hakResourceKeys:
                return (self.hakResourceKeys[candidate], candidate)
            if candidate in self.dirResourceKeys:
                return (self.dirResourceKeys[candidate], candidate)
            if candidate in self.keyResourceKeys:
                return (self.keyResourceKeys[candidate], candidate)
        return (None, None)

    def getResourceFromCache(self,key):
        """Return a cached resource based on its key.
        @return: the resource, 'None' if no such resource cached."""
        return self.cache.get(key,None)
    
    def addResourceToCache(self,key,r):
        """Add a resource to this manager's cache. Will not replace
        if resource with this key already in cache.
        @param key: the key to add the resource under
        @param r: the resource to add
        """
        self.cache.setdefault(key,r)

    def clearCache(self):
        """Clear this manager's cache"""
        self.cache = {}

    def clearResourceCacheByExtension(self,ext):
        t = ResourceManager.resTypeFromExtension(ext)
        for key in self.cache:
            if t == key[1]:
                del self.cache[key]

    def interpretResourceContents(self,key,data):
        '''Take the raw binary data associated with a key and interpret it.
        This method will return a neveredit object instance such as
        a L{neveredit.file.GFFFile.GFFFile},
        L{neveredit.file.TwoDAFile.TwoDAFile},
        L{neveredit.file.MDLFile.Model} or similar.'''
        #could alternatively go by 'type' header field for many types...
        extension = ResourceManager.extensionFromResType(key[1])
        logger.debug('interpreting resource "' +
                     ResourceManager.nameFromKey(key) + '"')
        resource = None
        if extension in ResourceManager.GFFFILETYPES:
            resource = neveredit.file.GFFFile.GFFFile()
            resource.fromFile(io.BytesIO(data),0)
        elif extension == 'NSS':
            if isinstance(data, bytes):
                data = data.decode('latin1')
            resource = neveredit.game.Script\
                       .Script(ResourceManager.nameFromKey(key),data)
        elif extension == '2DA':
            resource = neveredit.file.TwoDAFile.TwoDAFile()
            resource.fromFile(io.StringIO(data.decode('latin1')))
        elif extension in ('TGA', 'DDS'):
            resource = Image.open(io.BytesIO(data))
        elif extension == 'PLT':
            resource = self.decodePLT(data)
        elif extension == 'MDL':
            f = neveredit.file.MDLFile.MDLFile()
            f.fromFile(io.BytesIO(data))
            resource = f.getModel()
        elif extension == 'SET':
            resource = neveredit.file.TileSetFile.TileSetFile()
            resource.fromFile(io.StringIO(data.decode('latin1')))
        else:
            return data
        self.addResourceToCache(key,resource)
        return resource

    def decodePLT(self, data, tintContext=None):
        """Decode NWN PLT (palette texture) into a displayable RGBA PIL image.

        This is a conservative decoder intended for editor rendering fidelity.
        It supports common 2-byte (layer,intensity) or (intensity,layer)
        pixels, and a tolerant 3-byte variant with alpha.
        """
        if not data or len(data) < 16:
            return None

        try:
            header = data[:4]
            if header != b'PLT ':
                return None

            # NWN EE PLT commonly uses "PLT V1  " with width/height at 16/20
            # and pixel payload starting at offset 24.
            width = int.from_bytes(data[16:20], 'little', signed=False)
            height = int.from_bytes(data[20:24], 'little', signed=False)
            payload_offset = 24
            if width <= 0 or height <= 0:
                # Legacy fallback: some tools describe width/height at 8/12.
                width = int.from_bytes(data[8:12], 'little', signed=False)
                height = int.from_bytes(data[12:16], 'little', signed=False)
                payload_offset = 16
            if width <= 0 or height <= 0 or width > 4096 or height > 4096:
                return None

            payload = data[payload_offset:]
            pixel_count = width * height
            if pixel_count <= 0:
                return None

            bytes_per_pixel = 0
            if len(payload) >= pixel_count * 2:
                bytes_per_pixel = 2
            if len(payload) >= pixel_count * 3 and (len(payload) % 3 == 0):
                # Prefer exact 2-byte if both fit exactly.
                if len(payload) != pixel_count * 2:
                    bytes_per_pixel = 3
            if bytes_per_pixel == 0:
                return None

            rgba = bytearray(pixel_count * 4)

            if bytes_per_pixel == 2:
                # Detect whether ordering is (layer,intensity) or reversed.
                sample = payload[:min(len(payload), 4096)]
                first_small = 0
                second_small = 0
                for i in range(0, len(sample) - 1, 2):
                    if sample[i] <= 7:
                        first_small += 1
                    if sample[i + 1] <= 7:
                        second_small += 1
                layer_first = first_small >= second_small

                for px in range(pixel_count):
                    i = px * 2
                    a = payload[i]
                    b = payload[i + 1]
                    if layer_first:
                        layer, intensity = int(a), int(b)
                    else:
                        intensity, layer = int(a), int(b)
                    r, g, bl, alpha = self._pltColor(layer, intensity, 255, tintContext)
                    o = px * 4
                    rgba[o] = r
                    rgba[o + 1] = g
                    rgba[o + 2] = bl
                    rgba[o + 3] = alpha
            else:
                for px in range(pixel_count):
                    i = px * 3
                    layer = int(payload[i])
                    intensity = int(payload[i + 1])
                    alpha = int(payload[i + 2])
                    r, g, bl, out_a = self._pltColor(layer, intensity, alpha, tintContext)
                    o = px * 4
                    rgba[o] = r
                    rgba[o + 1] = g
                    rgba[o + 2] = bl
                    rgba[o + 3] = out_a

            return Image.frombytes('RGBA', (width, height), bytes(rgba))
        except Exception:
            logger.debug('failed to decode PLT resource', exc_info=True)
            return None

    def _pltColor(self, layer, intensity, alpha, tintContext=None):
        if layer >= 255:
            return (0, 0, 0, 0)

        i = max(0.0, min(1.0, float(intensity) / 255.0))
        # Stretch contrast so low intensities retain visible detail.
        shade = 0.25 + 0.75 * i
        base = self._pltLayerBaseColour(layer, tintContext)
        if base is None:
            # Unknown/high layers are usually shadow/detail-like.
            v = int(max(0.0, min(255.0, 35.0 + 200.0 * i)))
            out_alpha = max(0, min(255, int(alpha)))
            return (v, v, v, out_alpha)

        r = int(max(0.0, min(255.0, base[0] * shade)))
        g = int(max(0.0, min(255.0, base[1] * shade)))
        b = int(max(0.0, min(255.0, base[2] * shade)))
        out_alpha = max(0, min(255, int(alpha)))
        return (r, g, b, out_alpha)

    def _pltLayerBaseColour(self, layer, tintContext):
        base = self.PLT_LAYER_BASE.get(layer)
        if base is None or not tintContext:
            return base

        tint_index = self._pltTintIndexForLayer(layer, tintContext)
        if tint_index is None:
            return base

        palette_name = self.PLT_LAYER_PALETTES.get(layer)
        # Creature tattoo layers map better to tattoo palette when available.
        if layer in (5, 6):
            if ('tattoo1' in tintContext) or ('tattoo2' in tintContext):
                palette_name = 'pal_tattoo01'

        sampled = self._samplePLTPaletteColour(palette_name, tint_index)
        if sampled is not None:
            return sampled
        return base

    def _samplePLTPaletteColour(self, palette_name, tint_index):
        if not palette_name:
            return None
        image = self._getPLTPaletteImage(palette_name)
        if image is None:
            return None

        width, height = image.size
        if width <= 0 or height <= 0:
            return None

        index = max(0, min(255, int(tint_index)))

        # Canonical NWN palette textures are 256x176 and encode 256 tint
        # entries as a 16x16 swatch grid where each swatch is 16x11 px.
        if width >= 256 and height >= 176:
            cell_x = index % 16
            cell_y = index // 16
            x = min(width - 1, cell_x * 16 + 8)
            y = min(height - 1, cell_y * 11 + 5)
        else:
            # Fallback for non-standard palette dimensions.
            x = int(round((float(index) / 255.0) * float(width - 1)))
            y = 0

        r, g, b, _ = image.getpixel((x, y))
        return (int(r), int(g), int(b))

    def _getPLTPaletteImage(self, palette_name):
        cached = self._pltPaletteCache.get(palette_name)
        if cached is not None:
            return cached

        for extension in ('.tga', '.dds'):
            try:
                image = self.getResourceByName(palette_name + extension)
            except Exception:
                image = None
            if image is None:
                continue
            rgba = image.convert('RGBA')
            self._pltPaletteCache[palette_name] = rgba
            return rgba

        self._pltPaletteCache[palette_name] = None
        return None

    def _pltTintIndexForLayer(self, layer, tintContext):
        names = {
            0: ('skin',),
            1: ('hair',),
            2: ('metal1',),
            3: ('leather1', 'leather'),
            4: ('metal2',),
            5: ('minor', 'tattoo1'),
            6: ('major', 'tattoo2'),
        }.get(layer, ())

        candidates = [layer]
        candidates.extend(names)
        for key in candidates:
            if key not in tintContext:
                continue
            try:
                value = int(tintContext[key])
            except (TypeError, ValueError):
                continue
            if value >= 0:
                return value
        return None
    
    def scanGameDir(self,dirname):
        '''Scan an NWN install dir and store all the resource keys and
        hak files in it.
        @param dirname: the name of the directory to be scanned '''
        print('initializing resource manager from "',dirname,'"', end=' ', file=sys.stderr)
        sys.stderr.flush()
        self.clear()

        # Support NWN:EE layouts where key files live under a "data" subdir.
        scan_dir = dirname
        data_dir = os.path.join(dirname, 'data')
        if os.path.isdir(data_dir):
            legacy_key = os.path.join(dirname, 'chitin.key')
            ee_key = os.path.join(data_dir, 'nwn_base.key')
            if not os.path.exists(legacy_key) and os.path.exists(ee_key):
                scan_dir = data_dir

        self.setAppDir(scan_dir)
        if not os.path.exists(self.getAppDir()):
            logger.warning('dir given to resource manager does not exist')
            raise IOError("invalid path to NWN dir")
        c = 0.0
        loaded_key_paths = Set()
        for f in ResourceManager.KEYFILES:
            key_path = os.path.join(self.getAppDir(),f)
            if os.path.exists(key_path):
                print('.', end=' ', file=sys.stderr)
                sys.stderr.flush()
                self.addKeyFile(key_path)
                loaded_key_paths.add(os.path.abspath(key_path))
                c += 1
                self.setProgress((c/len(ResourceManager.KEYFILES))*100.0)

        # Fallback discovery for layouts with additional/nested key files.
        for root, _dirs, files in os.walk(self.getAppDir()):
            for filename in files:
                if not filename.lower().endswith('.key'):
                    continue
                key_path = os.path.abspath(os.path.join(root, filename))
                if key_path in loaded_key_paths:
                    continue
                try:
                    self.addKeyFile(key_path)
                    loaded_key_paths.add(key_path)
                except Exception:
                    logger.warning('skipping unreadable key file: %s', key_path)
        def _try_load_main_tlk(path):
            if not path or not os.path.exists(path):
                return False
            try:
                tt = neveredit.file.TalkTableFile.TalkTableFile()
                tt.fromFile(path)
                self.mainDialogFile = tt
                logger.info('loaded main dialog TLK: %s', path)
                return True
            except Exception:
                logger.warning('failed loading TLK file: %s', path)
                return False

        files = os.listdir(self.getAppDir())
        for f in files:
            if f == 'dialog.tlk':
                _try_load_main_tlk(os.path.join(self.getAppDir(),f))
            elif f == 'tlk':
                # NWN:EE stores TLK files in a dedicated tlk/ folder.
                tlk_dir = os.path.join(self.getAppDir(), f)
                if os.path.isdir(tlk_dir):
                    tlk_candidates = ['dialog.tlk']
                    for candidate in tlk_candidates:
                        candidate_path = os.path.join(tlk_dir, candidate)
                        if _try_load_main_tlk(candidate_path):
                            break
            if f == 'override':
                for over in os.listdir(os.path.join(self.getAppDir(),f)):
                    pass #should add override files here
            if f in ('hak', 'hk'):
                hak_dir = os.path.join(self.getAppDir(), f)
                if os.path.isdir(hak_dir):
                    self.hakDirectories.append(hak_dir)
                    for hak in os.listdir(hak_dir):
                        if hak.lower().endswith('.hak'):
                            self.hakFileNames.append(hak)
                            self.hakFilePaths.setdefault(hak.lower(), os.path.join(hak_dir, hak))
            if f == 'modules':
                for mod in os.listdir(os.path.join(self.getAppDir(),f)):
                    if mod[-4:] == '.mod':
                        #self.addMODFile(os.path.join(self.getAppDir(),f,mod))
                        self.modMap[os.path.basename(f)] = os.path.join(self.getAppDir(),f)
            if f == 'music':
                for mus in os.listdir(os.path.join(self.getAppDir(),f)):
                    if mus[-4:] == '.bmu':
                        self.BMUFileNames.append(mus)
            if f == 'ambient':
                for ambsound in os.listdir(os.path.join(self.getAppDir(),f)):
                    if ambsound[-4:] == '.wav':
                        self.ambientSoundFileNames.append(ambsound)

        if not self.mainDialogFile:
            # NWN:EE can be configured either from the install root or directly from data/.
            normalized_dir = os.path.normpath(dirname)
            if os.path.basename(normalized_dir).lower() == 'data':
                tlk_search_roots = [os.path.dirname(normalized_dir), normalized_dir]
            else:
                tlk_search_roots = [normalized_dir, self.getAppDir()]

            deduped_roots = []
            for root in tlk_search_roots:
                if root not in deduped_roots:
                    deduped_roots.append(root)

            tlk_search_paths = []
            for root in deduped_roots:
                tlk_search_paths.extend([
                    os.path.join(root, 'lang', 'en', 'data', 'dialog.tlk'),
                    os.path.join(root, 'data', 'tlk', 'dialog.tlk'),
                    os.path.join(root, 'data', 'tlk', 'dla_bio.tlk'),
                    os.path.join(root, 'tlk', 'dialog.tlk'),
                    os.path.join(root, 'tlk', 'dla_bio.tlk'),
                ])

            for root in deduped_roots:
                lang_dir = os.path.join(root, 'lang')
                if not os.path.isdir(lang_dir):
                    continue
                for locale in os.listdir(lang_dir):
                    tlk_search_paths.append(
                        os.path.join(lang_dir, locale, 'data', 'dialog.tlk')
                    )

            for tlk_path in tlk_search_paths:
                if _try_load_main_tlk(tlk_path):
                    break

        self.setProgress(0)
        print(file=sys.stderr)
        if not self.mainDialogFile:
            logger.warning('"' + self.getAppDir() +
                           '"' + " does not look like a valid NWN dir")

    def getDialogString(self,strref):
        '''look up a strref in dialog.tlk and return as a python string'''
        if not self.mainDialogFile:
            print('not initialized, cannot return dialog string', file=sys.stderr)
            return None
        else:
            if strref is None:
                return None
            try:
                strref = int(strref)
            except (TypeError, ValueError):
                return None
            strref &= 0xFFFFFFFF
            special = (strref & 0xFF000000) >> 24
            alternate = special & 0x01
            if alternate:
                basevalue = strref & 0x00FFFFFF
                if self.customTlkFile:
                    ctlkstring = self.customTlkFile.getString(basevalue)
                    if not ctlkstring:
                        # then we should fall back to the main tlk string - according to Bioware
                        return self.mainDialogFile.getString(basevalue)
                    else:
                        return ctlkstring
                else:
                    # then we should fall back to the main tlk string - according to Bioware
                    return self.mainDialogFile.getString(basevalue)
            else:
                return self.mainDialogFile.getString(strref)
        
    def getHAKFileNames(self):
        '''return a list of all hak file names found in the game install'''
        return self.hakFileNames

    def getBMUFileNames(self):
        '''return a list of all bmu (music) file names found in the game install'''
        return self.BMUFileNames

    def getAmbSoundFileNames(self):
        '''return a list of all bmu (music) file names found in the game install'''
        return self.ambientSoundFileNames

    def loadHAKsForModule(self,mod):
        '''Given a module, add all the resources in its hak files to the
        resource manager lookup tables. This will ignore the capitalization
        of both the hak file names stored in the module and of the hak files
        in the nwn installation directory.'''
        logger.debug('loading haks for "' + mod.getName() + '"')
        haks = [h.lower() for h in mod.getHAKNames()]
        haks.reverse() #reverse as later haks have lower priority
        lowerHakNames = [f.lower() for f in self.hakFileNames]
        for hak in haks:
            if not hak:
                continue
            if hak not in lowerHakNames:
                logger.warning('Could not find hak ' + hak
                               + ' amongst installed haks')
            else:
                hakName = self.hakFileNames[lowerHakNames.index(hak)]
                hakPath = self.hakFilePaths.get(hakName.lower())
                if not hakPath:
                    # Fallback for legacy behavior if no precomputed path exists.
                    for hak_dir in self.hakDirectories:
                        candidate = os.path.join(hak_dir, hakName)
                        if os.path.exists(candidate):
                            hakPath = candidate
                            break
                if hakPath:
                    self.addHAKFile(hakPath)
                else:
                    logger.warning('Could not resolve hak path for %s', hakName)
                
    def addKeyFile(self,keyf):
        keyFile = neveredit.file.KeyFile.KeyFile(self.getAppDir())
        keyFile.fromFile(keyf)
        keyList = keyFile.getKeyList()
        for key in keyList:
            self.keyResourceKeys[key] = keyFile
        self.buildResourceTable()

    def addHAKFile(self,hak):
        logger.debug('adding hak "' + hak + '"')
        hakFile = neveredit.file.ERFFile.ERFFile()
        hakFile.fromFile(hak)
        keyList = hakFile.getKeyList()
        for key in keyList:
            self.hakResourceKeys[key] = hakFile

    def getMODPath(self,m):
        return self.modMap.get(m,m)
    
    def addMODFile(self,erf):
        mod = neveredit.game.Module.Module(erf)
        self.addModule(mod)

    def addModule(self,mod):
        self.cleanMODandHAKKeys()
        self.module = mod
        keyList = mod.getKeyList()
        for key in keyList:
            self.dirResourceKeys[key] = mod.getERFFile()
        self.loadHAKsForModule(mod)
        self.buildResourceTable()
        tlkfile = self.module['Mod_CustomTlk']
        if len(tlkfile)>0:
            self.addCustomTlkFile(os.path.join(self.getAppDir(),'tlk',tlkfile + '.tlk'))
        
    def addCustomTlkFile(self,tlk):
        if len(tlk)>0:
            ctlkFile = neveredit.file.TalkTableFile.TalkTableFile()
            try:
                ctlkFile.fromFile(tlk)
                self.customTlkFile = ctlkFile
            except IOError:
                logger.error(_("specified tlk file %s not found - I will ignore it"),tlk)
                self.customTlkFile = None
        else:
            self.customTlkFile = None

    def buildResourceTable(self):
        for key in list(self.hakResourceKeys.keys()) +\
            list(self.dirResourceKeys.keys()) +\
            list(self.keyResourceKeys.keys()):
            self.resourcesByType.setdefault(key[1],Set()).add(key)
            
    def cleanMODandHAKKeys(self):
        self.dirResources = {}
        self.hakResources = {}
        self.buildResourceTable()
        self.clearCache()
        
    def getRawResource(self,key):
        provider, lookupKey = self._findProviderAndKey(key)
        if provider:
            return provider.getRawResource(lookupKey)
        else:
            self._logMissingResource(key)
            return None

    def getRawResourceByName(self,name):        
        key = ResourceManager.keyFromName(name)
        return self.getRawResource(key)

    def getResource(self,key,copy=False):
        provider, lookupKey = self._findProviderAndKey(key)
        cacheKey = lookupKey or key
        r = self.getResourceFromCache(cacheKey)
        if not copy and r:
            return r
        deleteCache = copy and not r
        resource = None
        if provider:
            resource = provider.getResource(lookupKey)
        else:
            self._logMissingResource(key)
        if resource and deleteCache:
            del self.cache[cacheKey]
        return resource

    def getResourceByName(self,name,copy=False):
        '''This method take a filename and returns an interpreted resource
        if such a resource exists.'''
        key = ResourceManager.keyFromName(name)
        return self.getResource(key,copy)

    def getKeysWithName(self,name):
        normalized_name = ResourceManager.normalizeResRef(name)
        keys = []
        for keySet in list(self.resourcesByType.values()):
            keys.extend([key for key in keySet
                         if ResourceManager.normalizeResRef(key[0]) == normalized_name])
        return keys
    
    def getKeysWithType(self,type):
        return self.resourcesByType[type]
    
    def getKeysWithExtensions(self,ext):
        return self.resourcesByType[ResourceManager.resTypeFromExtension(ext)]

    def getDirKeysWithExtensions(self,ext):
        keys = self.getKeysWithExtensions(ext)
        normalized = []
        for resref, rtype in keys:
            if (resref, rtype) not in self.dirResourceKeys:
                continue
            normalized.append((ResourceManager.normalizeResRef(resref), rtype))
        return normalized
    
    def getTextScriptKeys(self):
        return self.getKeysWithExtensions('nss')

    def getAppDir(cls):
        return cls.appDir
    getAppDir = classmethod(getAppDir)

    def setAppDir(cls,dir):
        cls.appDir = dir
    setAppDir = classmethod(setAppDir)

    def getPortraitByIndex(self,index,size):
        twoda = self.getResourceByName('portraits.2da')
        entry = twoda.getEntry(index,'BaseResRef').lower()
        if not entry or entry == '****':
            logger.warning('empty portrait entry for ' + repr(index) + ' ' +
                           repr(size))
            return None
        name = 'po_' + entry + size + '.tga'
        return self.getResourceByName(name)

    def getPortraitNameList(self):
        portraits = Set()
        for key in self.getKeysWithExtensions('TGA'):
            resref = ResourceManager.normalizeResRef(key[0])
            if resref[:3] == 'po_':
                portraits.add(resref[:-1])
        return list(portraits)
    
