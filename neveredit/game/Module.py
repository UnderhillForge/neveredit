'''Classes for handling nwn modules'''

import logging
logger = logging.getLogger('neveredit')
import re
import os
import random
import hashlib

import neveredit.file.ERFFile
from neveredit.file.GFFFile import GFFStruct,GFFFile
from neveredit.file.CExoLocString import CExoLocString
from neveredit.game.Area import Area
from neveredit.game.NeverData import NeverData
import neveredit.game.Factions
from neveredit.util import neverglobals
from neveredit.util.Progressor import Progressor

from io import BytesIO
from os.path import basename
import time

class Module(Progressor,NeverData):    
    """A class the encapsulates an NWN module file and gives access
    to entities contained therein, such as doors and scripts."""
    ifoPropList = {
        "Mod_CustomTlk":"CExoString",
        "Mod_DawnHour":"Integer,0-23",
        "Mod_Description":"CExoLocString,4",
        "Mod_DuskHour":"Integer,0-23",
        "Mod_Entry_Area":"ResRef,ARE",
        "Mod_HakList":"List,HAKs",
        "Mod_Hak":"CheckList,HAK",
        "Mod_Name":"CExoLocString",
        "Mod_MinPerHour": "Integer,1-255",
        "Mod_OnAcquirItem": "ResRef,NSS",
        "Mod_OnActvtItem": "ResRef,NSS",
        "Mod_OnClientEntr": "ResRef,NSS",
        "Mod_OnClientLeav": "ResRef,NSS",
        "Mod_OnCutsnAbort": "ResRef,NSS",
        "Mod_OnHeartbeat": "ResRef,NSS",
        "Mod_OnModLoad": "ResRef,NSS",
        "Mod_OnModStart": "ResRef,NSS",
        "Mod_OnPlrDeath": "ResRef,NSS",
        "Mod_OnPlrDying": "ResRef,NSS",
        "Mod_OnPlrEqItm": "ResRef,NSS",
        "Mod_OnPlrLvlUp": "ResRef,NSS",
        "Mod_OnPlrRest": "ResRef,NSS",
        "Mod_OnPlrUnEqItm": "ResRef,NSS",
        "Mod_OnSpawnBtnDn": "ResRef,NSS",
        "Mod_OnUnAqreItem": "ResRef,NSS",
        "Mod_OnUsrDefined": "ResRef,NSS",
        "Mod_StartDay": "Integer,1-31",
        "Mod_StartHour": "Integer,0-23",
        "Mod_StartMonth": "Integer,1-24",
        "Mod_StartYear": "Integer,0-2000",
        "Mod_Tag": "CExoString",
        "Mod_XPScale": "Integer,0-255",
        "Mod_Area_list": "Hidden",
        "VarTable": "List,Vars"
        }

    SCENE_LIFE_BORDER_WIDTH = 2
    SCENE_LIFE_MARKER = 'neveredit_scene_life=1'
    SCENE_LIFE_NONCE_KEY = 'neveredit_scene_life_nonce='
    SCENE_LIFE_SEED_KEY = 'neveredit_scene_life_seed='

    SCENE_LIFE_THEME_PREFERRED = {
        'urban_castle': (
            'wall', 'tower', 'house', 'gate', 'battlement',
            'merchant', 'market', 'banner', 'city', 'castle', 'fort',
            'street', 'inn', 'slum',
        ),
        'rural_forest': (
            'tree', 'forest', 'rock', 'ruin', 'hill', 'fence',
            'bush', 'grass', 'garden', 'farm',
        ),
        'desert': (
            'dune', 'sand', 'cacti', 'cactus', 'ruin', 'rock',
            'obelisk', 'oasis',
        ),
        'snow': (
            'snow', 'ice', 'frost', 'drift', 'ruin', 'rock',
        ),
    }

    SCENE_LIFE_THEME_DEMOTED = {
        'urban_castle': ('tree', 'rock', 'bush', 'grass', 'farm'),
        'rural_forest': ('wall', 'tower', 'battlement', 'city', 'castle'),
        'desert': ('tree', 'forest', 'grass', 'bush'),
        'snow': ('cacti', 'cactus', 'dune', 'sand'),
    }

    SCENE_LIFE_BLACKLIST_NON_COASTAL = ('boat', 'ship', 'dock', 'gazebo')

    # Prefer explicit Aurora tileset-resref mapping over heuristic token guessing.
    SCENE_LIFE_TILESET_THEME_BY_RESREF = {
        'tcn01': 'urban_castle',
        'tce01': 'urban_castle',
        'tde001': 'urban_castle',  # City Exterior
        'tde006': 'urban_castle',  # Castle Exterior
        'tde003': 'rural_forest',  # Rural
        'tde010': 'rural_forest',  # Forest
        'ttr01': 'rural_forest',
        'tde013': 'desert',
        'tdn01': 'snow',
        'tde011': 'snow',
    }

    SCENE_LIFE_TILESET_RULES_BY_RESREF = {
        'tcn01': {
            'boost': ('wall', 'gate', 'market', 'house', 'city', 'slum', 'tower', 'banner'),
            'demote': ('tree', 'rock', 'farm', 'rural'),
            'blacklist': ('boat', 'ship', 'dock', 'gazebo'),
            'strict': True,
        },
        'tce01': {
            'boost': ('wall', 'gate', 'castle', 'tower', 'battlement', 'fort'),
            'demote': ('tree', 'rock', 'farm', 'rural'),
            'blacklist': ('boat', 'ship', 'dock', 'gazebo'),
            'strict': True,
        },
        'tde006': {
            'boost': ('wall', 'gate', 'castle', 'tower', 'battlement', 'fort'),
            'demote': ('tree', 'rock', 'farm', 'rural'),
            'blacklist': ('boat', 'ship', 'dock', 'gazebo'),
            'strict': True,
        },
        'ttr01': {
            'boost': ('tree', 'forest', 'rock', 'ruin', 'fence', 'hill', 'farm'),
            'demote': ('city', 'castle', 'tower', 'battlement', 'market'),
            'strict': True,
        },
        'tde003': {
            'boost': ('tree', 'forest', 'rock', 'ruin', 'fence', 'hill', 'farm'),
            'demote': ('city', 'castle', 'tower', 'battlement', 'market'),
            'strict': True,
        },
        'tde010': {
            'boost': ('tree', 'forest', 'rock', 'ruin', 'fence', 'hill'),
            'demote': ('city', 'castle', 'tower', 'battlement', 'market'),
            'strict': True,
        },
        'tde013': {
            'boost': ('dune', 'sand', 'cacti', 'cactus', 'ruin', 'rock', 'obelisk'),
            'demote': ('tree', 'forest', 'grass', 'bush', 'farm'),
            'strict': True,
        },
    }

    # Embedded toolset starter templates for exact create-time parity when
    # temp0 is unavailable. Each entry is a grid of "model:orientation" cells.
    TOOLSET_STARTER_TEMPLATES = {
        ('tcn01', 8, 8): (
            (
                'tcn01_c01_02:2', 'tcn01_c02_09:3', 'tcn01_c02_07:3', 'tcn01_c02_09:3',
                'tcn01_c02_09:3', 'tcn01_c02_05:3', 'tcn01_c02_07:3', 'tcn01_c01_03:3',
            ),
            (
                'tcn01_c02_05:2', 'tcn01_a20_01:2', 'tcn01_a20_01:0', 'tcn01_a20_02:2',
                'tcn01_a20_01:2', 'tcn01_a20_05:2', 'tcn01_a20_04:2', 'tcn01_c02_01:0',
            ),
            (
                'tcn01_c02_01:2', 'tcn01_a20_02:3', 'tcn01_a20_04:2', 'tcn01_a20_02:1',
                'tcn01_a20_02:2', 'tcn01_a20_02:1', 'tcn01_a20_03:1', 'tcn01_c02_05:0',
            ),
            (
                'tcn01_c02_02:2', 'tcn01_a20_05:1', 'tcn01_a20_02:3', 'tcn01_a20_01:1',
                'tcn01_a20_01:0', 'tcn01_a20_03:2', 'tcn01_a20_04:3', 'tcn01_c02_08:0',
            ),
            (
                'tcn01_c02_03:2', 'tcn01_a20_02:0', 'tcn01_a20_01:3', 'tcn01_a20_02:0',
                'tcn01_a20_01:2', 'tcn01_a20_01:2', 'tcn01_a20_02:2', 'tcn01_c02_03:0',
            ),
            (
                'tcn01_c02_03:2', 'tcn01_a20_04:0', 'tcn01_a20_05:1', 'tcn01_o01_01:1',
                'tcn01_a20_04:0', 'tcn01_a20_05:2', 'tcn01_o01_01:1', 'tcn01_c02_03:0',
            ),
            (
                'tcn01_c02_03:2', 'tcn01_a20_05:0', 'tcn01_a20_05:2', 'tcn01_a20_01:1',
                'tcn01_o01_01:3', 'tcn01_a20_03:1', 'tcn01_a20_03:0', 'tcn01_c02_04:0',
            ),
            (
                'tcn01_c01_03:1', 'tcn01_c02_03:1', 'tcn01_c02_09:1', 'tcn01_c02_01:1',
                'tcn01_c02_04:1', 'tcn01_c02_10:1', 'tcn01_c02_03:1', 'tcn01_c01_02:0',
            ),
        ),
    }

    @staticmethod
    def _entry_resref_name(entry):
        name = entry.name
        if isinstance(name, bytes):
            return name.rstrip(b'\0').decode('latin1', 'ignore')
        return str(name).strip('\0')

    @staticmethod
    def _format_eta(seconds):
        seconds = max(0, int(seconds))
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return "%d:%02d:%02d" % (hours, mins, secs)
        return "%02d:%02d" % (mins, secs)

    @staticmethod
    def _sanitize_resref(text, fallback='module'):
        value = re.sub(r'[^a-zA-Z0-9_]', '_', (text or '').lower())
        value = re.sub(r'_+', '_', value).strip('_')
        value = value[:16]
        if not value:
            value = fallback[:16]
        return value

    @staticmethod
    def _normalize_resref_value(value):
        if isinstance(value, bytes):
            return value.split(b'\0', 1)[0].decode('latin1', 'ignore').strip().lower()
        return str(value).split('\0', 1)[0].strip().lower()

    @staticmethod
    def _load_gff_from_path(path):
        gff = GFFFile()
        with open(path, 'rb') as handle:
            gff.fromFile(handle)
        return gff

    @staticmethod
    def _read_int_entry(struct, key, fallback):
        try:
            value = struct.getInterpretedEntry(key)
        except Exception:
            return fallback
        try:
            return int(value)
        except Exception:
            return fallback

    @staticmethod
    def _safe_text(value):
        if isinstance(value, bytes):
            return value.split(b'\0', 1)[0].decode('latin1', 'ignore').strip()
        return str(value or '').split('\0', 1)[0].strip()

    @staticmethod
    def _tokenize(text):
        base = Module._safe_text(text).lower()
        if not base:
            return []
        return [tok for tok in re.split(r'[^a-z0-9]+', base) if tok]

    @staticmethod
    def _is_border_cell(x, y, width, height, border_width):
        return (x < border_width or y < border_width or
                x >= (width - border_width) or y >= (height - border_width))

    @staticmethod
    def _iter_border_cells(width, height, border_width):
        for y in range(height):
            for x in range(width):
                if Module._is_border_cell(x, y, width, height, border_width):
                    yield (x, y)

    @staticmethod
    def _load_tileset_palette_root(tileset_resref):
        rm = neverglobals.getResourceManager()
        if not rm:
            return None
        for candidate in (tileset_resref.lower() + 'palstd.itp',
                          tileset_resref.lower() + 'pal.itp'):
            try:
                palette = rm.getResourceByName(candidate)
            except Exception:
                palette = None
            if palette:
                return palette.getRoot()
        return None

    @staticmethod
    def _extract_palette_resrefs(palette_root, section_index):
        if not palette_root or not palette_root.hasEntry('MAIN'):
            return []
        main = palette_root.getInterpretedEntry('MAIN') or []
        if section_index >= len(main):
            return []
        section = main[section_index]
        if not section or not section.hasEntry('LIST'):
            return []
        results = []
        for entry in section.getInterpretedEntry('LIST') or []:
            if not entry or not entry.hasEntry('RESREF'):
                continue
            resref = Module._normalize_resref_value(entry.getInterpretedEntry('RESREF'))
            if resref:
                results.append(resref)
        return results

    @staticmethod
    def _build_tileset_model_maps(tileset_file):
        model_to_tile_id = {}
        tile_id_to_model = {}
        try:
            tile_count = int(tileset_file.getTileCount())
        except Exception:
            return model_to_tile_id, tile_id_to_model
        for tid in range(tile_count):
            section = 'TILE' + str(tid)
            if not tileset_file.has_section(section):
                continue
            model = Module._safe_text(tileset_file.get(section, 'model', fallback='')).lower()
            if not model:
                continue
            tile_id_to_model[tid] = model
            if model not in model_to_tile_id:
                model_to_tile_id[model] = tid
        return model_to_tile_id, tile_id_to_model

    @staticmethod
    def _classify_tileset_theme(tileset_resref, tileset_file):
        normalized = Module._normalize_resref_value(tileset_resref)
        explicit = Module.SCENE_LIFE_TILESET_THEME_BY_RESREF.get(normalized)
        if explicit:
            return explicit

        tokens = set(Module._tokenize(tileset_resref))
        if tileset_file is not None:
            for key in ('Name', 'DisplayName'):
                try:
                    tokens.update(Module._tokenize(tileset_file.get('GENERAL', key, fallback='')))
                except Exception:
                    pass

        joined = ' '.join(sorted(tokens))
        if any(tok in tokens for tok in ('city', 'castle', 'fort', 'urban')) or 'tcn' in joined or 'tce' in joined:
            return 'urban_castle'
        if any(tok in tokens for tok in ('rural', 'forest', 'wilderness', 'swamp', 'jungle', 'village')) or 'ttr' in joined:
            return 'rural_forest'
        if any(tok in tokens for tok in ('desert', 'sand', 'dune')):
            return 'desert'
        if any(tok in tokens for tok in ('winter', 'snow', 'ice', 'arctic')):
            return 'snow'
        if any(tok in tokens for tok in ('coast', 'coastal', 'sea', 'shore', 'beach', 'dock', 'ship')):
            return 'coastal'
        return 'neutral'

    @staticmethod
    def _score_scene_life_candidate(profile, model_resref):
        theme = profile.get('theme', 'neutral')
        tokens = set(Module._tokenize(model_resref))
        if not tokens:
            return 1.0

        # Hard blacklist for obviously wrong content on non-coastal themes.
        blacklist = set(profile.get('blacklist', ()))
        if theme != 'coastal':
            blacklist.update(Module.SCENE_LIFE_BLACKLIST_NON_COASTAL)
        if blacklist and any(tok in tokens for tok in blacklist):
            return 0.0

        score = 1.0
        preferred = Module.SCENE_LIFE_THEME_PREFERRED.get(theme, ())
        demoted = Module.SCENE_LIFE_THEME_DEMOTED.get(theme, ())
        profile_boost = profile.get('boost', ())
        profile_demote = profile.get('demote', ())

        preferred_hit = bool(preferred and any(tok in tokens for tok in preferred))
        boost_hit = bool(profile_boost and any(tok in tokens for tok in profile_boost))

        # Strict mode keeps generic candidates but heavily favors explicit
        # theme/profile matches.
        strict_mode = bool(profile.get('strict'))

        if preferred_hit:
            score *= 2.4
        if boost_hit:
            score *= 1.8
        if demoted and any(tok in tokens for tok in demoted):
            score *= 0.35
        if profile_demote and any(tok in tokens for tok in profile_demote):
            score *= 0.30

        if strict_mode and not (preferred_hit or boost_hit):
            score *= 0.75

        return max(0.0, score)

    def _scene_life_profile_for_tileset(self, tileset_resref, tileset_file):
        normalized = self._normalize_resref_value(tileset_resref)
        theme = self._classify_tileset_theme(normalized, tileset_file)
        rules = self.SCENE_LIFE_TILESET_RULES_BY_RESREF.get(normalized, {})
        return {
            'resref': normalized,
            'theme': theme,
            'boost': tuple(rules.get('boost', ())),
            'demote': tuple(rules.get('demote', ())),
            'blacklist': tuple(rules.get('blacklist', ())),
            'strict': bool(rules.get('strict', theme != 'neutral')),
        }

    @staticmethod
    def _is_exterior_tileset(tileset_resref, tileset_file, palette_root):
        if tileset_file is not None:
            try:
                interior_flag = int(tileset_file.get('GENERAL', 'interior', fallback='0'))
                return interior_flag == 0
            except Exception:
                pass

        # Fallback heuristic from tileset palette terrain labels.
        terrain = set(Module._extract_palette_resrefs(palette_root, 2))
        interior_terms = {'corridor', 'doorway', 'inn', 'kitchen', 'livingroom', 'shop'}
        if terrain and any(t in terrain for t in interior_terms):
            return False

        name_tokens = set(Module._tokenize(tileset_resref))
        if any(tok in name_tokens for tok in ('city', 'castle', 'forest', 'rural', 'desert', 'snow', 'winter')):
            return True
        return False

    @staticmethod
    def _choose_weighted(rng, weighted_items):
        if not weighted_items:
            return None
        total = sum(max(0.0, float(item[0])) for item in weighted_items)
        if total <= 0.0:
            return rng.choice([item[1] for item in weighted_items])
        needle = rng.random() * total
        acc = 0.0
        for weight, value in weighted_items:
            acc += max(0.0, float(weight))
            if needle <= acc:
                return value
        return weighted_items[-1][1]

    @staticmethod
    def _apply_tile_to_struct(tile_struct, tile_id, orientation):
        if tile_struct.hasEntry('Tile_ID'):
            tile_struct.setInterpretedEntry('Tile_ID', int(tile_id))
        else:
            tile_struct.add('Tile_ID', int(tile_id), 'INT')

        if tile_struct.hasEntry('Tile_Orientation'):
            tile_struct.setInterpretedEntry('Tile_Orientation', int(orientation) % 4)
        else:
            tile_struct.add('Tile_Orientation', int(orientation) % 4, 'INT')

    @staticmethod
    def _extract_scene_life_nonce(are_struct):
        if are_struct is None or not are_struct.hasEntry('Comments'):
            return 0
        comments = Module._safe_text(are_struct.getInterpretedEntry('Comments'))
        m = re.search(r'neveredit_scene_life_nonce=(\d+)', comments)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except Exception:
            return 0

    @staticmethod
    def _mark_area_scene_life_generated(are_struct, source_label, seed_value, nonce_value):
        if are_struct is None:
            return

        existing = Module._safe_text(
            are_struct.getInterpretedEntry('Comments') if are_struct.hasEntry('Comments') else '')
        kept_lines = []
        for line in existing.splitlines():
            text = line.strip()
            if not text:
                continue
            if (text.startswith(Module.SCENE_LIFE_MARKER) or
                    text.startswith(Module.SCENE_LIFE_NONCE_KEY) or
                    text.startswith(Module.SCENE_LIFE_SEED_KEY)):
                continue
            kept_lines.append(text)

        kept_lines.append(Module.SCENE_LIFE_MARKER + ' (' + str(source_label) + ')')
        kept_lines.append(Module.SCENE_LIFE_NONCE_KEY + str(max(0, int(nonce_value))))
        kept_lines.append(Module.SCENE_LIFE_SEED_KEY + str(int(seed_value) & 0xFFFFFFFFFFFFFFFF))
        new_comments = '\n'.join(kept_lines)

        if are_struct.hasEntry('Comments'):
            are_struct.setInterpretedEntry('Comments', new_comments)
        else:
            are_struct.add('Comments', new_comments, 'CExoString')

    def _scene_life_seed(self, tileset_resref, width, height, area_resref,
                         mode, nonce_value=0):
        try:
            module_tag = self._safe_text(self['Mod_Tag'])
        except Exception:
            module_tag = ''
        payload = '|'.join([
            module_tag.lower(),
            self._normalize_resref_value(area_resref),
            self._normalize_resref_value(tileset_resref),
            str(int(width)),
            str(int(height)),
            self._safe_text(mode).lower(),
            str(max(0, int(nonce_value))),
        ])
        digest = hashlib.sha1(payload.encode('utf-8', 'ignore')).digest()
        return int.from_bytes(digest[:8], byteorder='big', signed=False)

    def _reset_border_to_default_tile(self, tiles, width, height, border_width, default_tile_id):
        for (x, y) in self._iter_border_cells(width, height, border_width):
            idx = y * width + x
            if idx < 0 or idx >= len(tiles):
                continue
            tile_struct = tiles[idx]
            if tile_struct is None:
                continue
            self._apply_tile_to_struct(tile_struct, default_tile_id, 0)

    def _feature_orientation_for_edge(self, x, y, width, height, border_width, rng):
        dists = {
            'left': x,
            'right': (width - 1) - x,
            'top': y,
            'bottom': (height - 1) - y,
        }
        edge = min(dists, key=dists.get)
        if dists[edge] >= border_width:
            return rng.randrange(4)

        # Bias to orientations parallel to the closest edge.
        if edge in ('top', 'bottom'):
            choices = [(0.45, 0), (0.45, 2), (0.05, 1), (0.05, 3)]
        else:
            choices = [(0.45, 1), (0.45, 3), (0.05, 0), (0.05, 2)]
        return self._choose_weighted(rng, choices)

    def _border_position_weight(self, x, y, width, height):
        ring = min(x, y, width - 1 - x, height - 1 - y)
        weight = 1.0
        if ring == 0:
            weight *= 1.9
        elif ring == 1:
            weight *= 1.25

        if ((x in (0, width - 1)) and (y in (0, height - 1))):
            weight *= 1.7
        elif (x in (0, width - 1) or y in (0, height - 1)):
            weight *= 1.2
        return weight

    @staticmethod
    def _rotated_group_cells(rows, cols, tile_ids, rotation):
        placed = []
        for sy in range(rows):
            for sx in range(cols):
                src_index = sy * cols + sx
                tile_id = tile_ids[src_index]
                if rotation == 0:
                    dx, dy = sx, sy
                elif rotation == 1:
                    dx, dy = rows - 1 - sy, sx
                elif rotation == 2:
                    dx, dy = cols - 1 - sx, rows - 1 - sy
                else:
                    dx, dy = sy, cols - 1 - sx
                placed.append((dx, dy, int(tile_id), int(rotation) % 4))
        return placed

    @staticmethod
    def _default_corner_terrains(tileset_file):
        if tileset_file is None:
            return set()
        try:
            default_tile_id = int(tileset_file.getDefaultTileID())
        except Exception:
            return set()
        return Module._tile_corner_terrains(tileset_file, default_tile_id)

    @staticmethod
    def _tile_corner_terrains(tileset_file, tile_id):
        if tileset_file is None:
            return set()
        section = 'TILE' + str(int(tile_id))
        terrains = set()
        for key in ('TopLeft', 'TopRight', 'BottomLeft', 'BottomRight'):
            try:
                value = Module._safe_text(tileset_file.get(section, key, fallback='')).lower()
            except Exception:
                value = ''
            if value:
                terrains.add(value)
        return terrains

    def _build_scene_life_feature_candidates(self, feature_resrefs, model_to_tile_id,
                                             tileset_file, default_corner_terrains,
                                             profile):
        candidates = []
        for resref in feature_resrefs:
            tile_id = model_to_tile_id.get(resref)
            if tile_id is None:
                continue

            # Hard reject feature tiles that don't match the default terrain
            # envelope for this tileset (for example water/building-transition
            # tiles in a cobble perimeter pass).
            if default_corner_terrains:
                tile_terrains = self._tile_corner_terrains(tileset_file, tile_id)
                if not tile_terrains or not tile_terrains.issubset(default_corner_terrains):
                    continue

            weight = self._score_scene_life_candidate(profile, resref)
            if weight <= 0.0:
                continue
            candidates.append({'tile_id': int(tile_id), 'resref': resref, 'weight': float(weight)})
        return candidates

    def _build_scene_life_group_candidates(self, group_resrefs, tileset_file,
                                           tile_id_to_model, default_corner_terrains,
                                           profile):
        group_models = set(group_resrefs)
        if not group_models or tileset_file is None:
            return []

        group_candidates = []
        try:
            group_count = int(tileset_file.getGroupCount())
        except Exception:
            group_count = 0

        for gi in range(group_count):
            section = 'GROUP' + str(gi)
            rows = tileset_file.getint(section, 'Rows', fallback=0)
            cols = tileset_file.getint(section, 'Columns', fallback=0)
            if rows <= 0 or cols <= 0:
                continue

            # Strict 2-tile border means groups larger than 2 in either axis
            # cannot be fully placed without entering the playable rectangle.
            if rows > self.SCENE_LIFE_BORDER_WIDTH or cols > self.SCENE_LIFE_BORDER_WIDTH:
                continue

            tile_ids = []
            for idx in range(rows * cols):
                tid = tileset_file.getint(section, 'Tile' + str(idx), fallback=-1)
                if tid < 0:
                    tile_ids = []
                    break
                tile_ids.append(int(tid))
            if not tile_ids:
                continue

            if default_corner_terrains:
                invalid_terrain = False
                for tid in tile_ids:
                    tile_terrains = self._tile_corner_terrains(tileset_file, tid)
                    if not tile_terrains or not tile_terrains.issubset(default_corner_terrains):
                        invalid_terrain = True
                        break
                if invalid_terrain:
                    continue

            member_models = [tile_id_to_model.get(tid, '') for tid in tile_ids]
            matching_models = [m for m in member_models if m in group_models]
            if not matching_models:
                continue

            score_samples = [self._score_scene_life_candidate(profile, m) for m in matching_models]
            weight = max(score_samples) if score_samples else 0.0
            if weight <= 0.0:
                continue

            group_candidates.append({
                'group_id': int(gi),
                'rows': int(rows),
                'cols': int(cols),
                'tile_ids': tile_ids,
                'weight': float(weight),
            })

        return group_candidates

    def _generate_border_scene_life(self, tiles, width, height, tileset_resref, tileset_file,
                                    border_width=2, reset_border=False,
                                    density_min=0.25, density_max=0.40,
                                    rng_seed=None):
        if not tiles or width <= 0 or height <= 0:
            return {'changed': False, 'reason': 'Area tile data is invalid.'}

        max_border = min(width // 2, height // 2)
        if max_border <= 0:
            return {'changed': False, 'reason': 'Area is too small for a 2-tile perimeter.'}
        border_width = min(int(border_width), int(max_border))

        palette_root = self._load_tileset_palette_root(tileset_resref)
        if not palette_root:
            return {'changed': False, 'reason': 'Tileset palette .itp was not found.'}

        if not self._is_exterior_tileset(tileset_resref, tileset_file, palette_root):
            return {'changed': False, 'reason': 'Perimeter scene life applies only to exterior areas.'}

        feature_resrefs = self._extract_palette_resrefs(palette_root, 0)
        group_resrefs = self._extract_palette_resrefs(palette_root, 1)
        if not feature_resrefs and not group_resrefs:
            return {'changed': False, 'reason': 'Tileset palette has no Features/Groups entries.'}

        model_to_tile_id, tile_id_to_model = self._build_tileset_model_maps(tileset_file)
        profile = self._scene_life_profile_for_tileset(tileset_resref, tileset_file)
        default_corner_terrains = self._default_corner_terrains(tileset_file)

        feature_candidates = self._build_scene_life_feature_candidates(
            feature_resrefs, model_to_tile_id, tileset_file, default_corner_terrains, profile)
        group_candidates = self._build_scene_life_group_candidates(
            group_resrefs, tileset_file, tile_id_to_model, default_corner_terrains, profile)

        if not feature_candidates and not group_candidates:
            return {'changed': False, 'reason': 'No valid feature/group tiles resolved for this tileset.'}

        if rng_seed is None:
            rng_seed = self._scene_life_seed(
                tileset_resref=tileset_resref,
                width=width,
                height=height,
                area_resref='',
                mode='scene-life',
                nonce_value=0,
            )
        rng = random.Random(int(rng_seed) & 0xFFFFFFFFFFFFFFFF)

        default_tile_id = 0
        if tileset_file is not None:
            try:
                default_tile_id = int(tileset_file.getDefaultTileID())
            except Exception:
                default_tile_id = 0

        if reset_border:
            self._reset_border_to_default_tile(tiles, width, height, border_width, default_tile_id)

        border_cells = list(self._iter_border_cells(width, height, border_width))
        if not border_cells:
            return {'changed': False, 'reason': 'No border cells available.'}

        target_ratio = max(0.40, min(0.60, rng.uniform(0.40, 0.60)))
        target_cells = int(round(len(border_cells) * target_ratio))
        target_cells = max(1, target_cells)

        occupied = set()
        reserved_gap = set()
        placements = 0

        def _reserve_gap(cells):
            if rng.random() > 0.10:
                return
            for (cx, cy) in cells:
                for nx in range(cx - 1, cx + 2):
                    for ny in range(cy - 1, cy + 2):
                        if (0 <= nx < width and 0 <= ny < height and
                                self._is_border_cell(nx, ny, width, height, border_width) and
                                (nx, ny) not in occupied):
                            reserved_gap.add((nx, ny))

        def _free_border_cells_weighted():
            options = []
            for (x, y) in border_cells:
                if (x, y) in occupied or (x, y) in reserved_gap:
                    continue
                options.append((self._border_position_weight(x, y, width, height), (x, y)))
            return options

        def _place_feature():
            feature = self._choose_weighted(rng, [(f['weight'], f) for f in feature_candidates])
            if not feature:
                return 0
            free_cells = _free_border_cells_weighted()
            if not free_cells:
                return 0
            x, y = self._choose_weighted(rng, free_cells)
            idx = y * width + x
            tile_struct = tiles[idx]
            if tile_struct is None:
                return 0
            orientation = self._feature_orientation_for_edge(x, y, width, height, border_width, rng)
            self._apply_tile_to_struct(tile_struct, feature['tile_id'], orientation)
            occupied.add((x, y))
            _reserve_gap([(x, y)])
            return 1

        def _group_placement_candidates(group):
            placements_out = []
            for rot in (0, 1, 2, 3):
                if rot % 2 == 0:
                    rw, rh = group['cols'], group['rows']
                else:
                    rw, rh = group['rows'], group['cols']

                if rw <= 0 or rh <= 0 or rw > width or rh > height:
                    continue

                rotated = self._rotated_group_cells(group['rows'], group['cols'],
                                                    group['tile_ids'], rot)
                for top in range(0, height - rh + 1):
                    for left in range(0, width - rw + 1):
                        cells = []
                        ok = True
                        for dx, dy, tile_id, orient in rotated:
                            x = left + dx
                            y = top + dy
                            if not self._is_border_cell(x, y, width, height, border_width):
                                ok = False
                                break
                            if (x, y) in occupied or (x, y) in reserved_gap:
                                ok = False
                                break
                            cells.append((x, y, tile_id, orient))
                        if not ok:
                            continue
                        avg_weight = sum(self._border_position_weight(x, y, width, height)
                                         for x, y, _tile_id, _orient in cells) / float(len(cells))
                        placements_out.append((avg_weight, cells))
            return placements_out

        attempts = 0
        max_attempts = max(2500, target_cells * 100)

        while len(occupied) < target_cells and attempts < max_attempts:
            attempts += 1
            remaining = target_cells - len(occupied)

            use_group = bool(group_candidates)
            if use_group:
                # Prefer Features when close to target to avoid overfilling.
                if remaining <= 2:
                    use_group = False
                else:
                    use_group = rng.random() < 0.65

            if use_group:
                group = self._choose_weighted(rng, [(g['weight'], g) for g in group_candidates])
                if not group:
                    continue
                options = _group_placement_candidates(group)
                if not options:
                    continue
                cells = self._choose_weighted(rng, options)
                if not cells:
                    continue
                for x, y, tile_id, orient in cells:
                    idx = y * width + x
                    tile_struct = tiles[idx]
                    if tile_struct is None:
                        continue
                    self._apply_tile_to_struct(tile_struct, tile_id, orient)
                    occupied.add((x, y))
                _reserve_gap([(x, y) for x, y, _tile_id, _orient in cells])
                placements += 1
                continue

            if feature_candidates:
                placed = _place_feature()
                if placed:
                    placements += 1

        report = {
            'changed': len(occupied) > 0,
            'placed_cells': len(occupied),
            'target_cells': target_cells,
            'placements': placements,
            'reason': ('Placed %d border tiles from Features/Groups.' % len(occupied))
            if len(occupied) > 0 else 'No valid border placements were found.',
        }

        # Defensive: force any accidental interior placements back to the
        # default fill tile so scene life cannot leak into the playable area.
        interior_changed = False
        for y in range(height):
            for x in range(width):
                if not self._is_border_cell(x, y, width, height, border_width):
                    idx = y * width + x
                    if 0 <= idx < len(tiles):
                        tile_struct = tiles[idx]
                        if tile_struct is not None:
                            current_id = self._read_int_entry(tile_struct, 'Tile_ID', default_tile_id)
                            if current_id != default_tile_id:
                                self._apply_tile_to_struct(tile_struct, default_tile_id, 0)
                                interior_changed = True
        if interior_changed:
            logger.warning('Interior tiles modified during scene life - auto-corrected to default')
            report['reason'] = (report.get('reason', '') + ' (interior safety reset applied)').strip()

        return report

    def _loadToolsetTemp0Template(self, tileset, width, height):
        """Load template defaults from sibling modules/temp0 if available.

        The original toolset writes generated area data into ``temp0`` while the
        wizard is active.  Reusing that data when it matches the requested
        tileset/size provides near-identical starter layouts and lighting.
        """
        try:
            module_path = self.getFileName()
        except Exception:
            module_path = None
        if not module_path:
            return None

        module_dir = os.path.dirname(module_path)
        if not module_dir:
            return None
        temp_dir = os.path.join(module_dir, 'temp0')
        if not os.path.isdir(temp_dir):
            return None

        are_path = None
        for candidate in ('area001.are', 'area001.ARE'):
            p = os.path.join(temp_dir, candidate)
            if os.path.exists(p):
                are_path = p
                break
        if not are_path:
            return None

        try:
            are_gff = self._load_gff_from_path(are_path)
            are_root = are_gff.rootStructure
        except Exception:
            return None

        template_tileset = self._normalize_resref_value(
            are_root.getInterpretedEntry('Tileset')
        )
        if template_tileset != self._normalize_resref_value(tileset):
            return None

        t_width = self._read_int_entry(are_root, 'Width', -1)
        t_height = self._read_int_entry(are_root, 'Height', -1)
        if t_width != int(width) or t_height != int(height):
            return None

        tile_list = are_root.getInterpretedEntry('Tile_List') or []
        if len(tile_list) != int(width) * int(height):
            return None

        tile_values = []
        for tile_struct in tile_list:
            tile_values.append({
                'Tile_AnimLoop1': self._read_int_entry(tile_struct, 'Tile_AnimLoop1', 0),
                'Tile_AnimLoop2': self._read_int_entry(tile_struct, 'Tile_AnimLoop2', 0),
                'Tile_AnimLoop3': self._read_int_entry(tile_struct, 'Tile_AnimLoop3', 0),
                'Tile_Height': self._read_int_entry(tile_struct, 'Tile_Height', 0),
                'Tile_ID': self._read_int_entry(tile_struct, 'Tile_ID', 0),
                'Tile_MainLight1': self._read_int_entry(tile_struct, 'Tile_MainLight1', 0),
                'Tile_MainLight2': self._read_int_entry(tile_struct, 'Tile_MainLight2', 0),
                'Tile_Orientation': self._read_int_entry(tile_struct, 'Tile_Orientation', 0),
                'Tile_SrcLight1': self._read_int_entry(tile_struct, 'Tile_SrcLight1', 0),
                'Tile_SrcLight2': self._read_int_entry(tile_struct, 'Tile_SrcLight2', 0),
            })

        git_defaults = {}
        for candidate in ('area001.GIT', 'area001.git'):
            git_path = os.path.join(temp_dir, candidate)
            if not os.path.exists(git_path):
                continue
            try:
                git_gff = self._load_gff_from_path(git_path)
                git_root = git_gff.rootStructure
                ap = git_root.getInterpretedEntry('AreaProperties')
                if ap is not None:
                    git_defaults = {
                        'AmbientSndDay': self._read_int_entry(ap, 'AmbientSndDay', 0),
                        'AmbientSndNight': self._read_int_entry(ap, 'AmbientSndNight', 0),
                        'MusicDay': self._read_int_entry(ap, 'MusicDay', 0),
                        'MusicNight': self._read_int_entry(ap, 'MusicNight', 0),
                    }
                break
            except Exception:
                continue

        are_defaults = {
            'DayNightCycle': self._read_int_entry(are_root, 'DayNightCycle', 1),
            'MoonAmbientColor': self._read_int_entry(are_root, 'MoonAmbientColor', 0x404040),
            'MoonDiffuseColor': self._read_int_entry(are_root, 'MoonDiffuseColor', 0x404040),
            'MoonFogColor': self._read_int_entry(are_root, 'MoonFogColor', 0x404040),
            'SunAmbientColor': self._read_int_entry(are_root, 'SunAmbientColor', 0xA0A0A0),
            'SunDiffuseColor': self._read_int_entry(are_root, 'SunDiffuseColor', 0xFFFFFF),
            'SunFogColor': self._read_int_entry(are_root, 'SunFogColor', 0xC8C8C8),
            'LoadScreenID': self._read_int_entry(are_root, 'LoadScreenID', 0),
        }

        return {
            'tile_values': tile_values,
            'are_defaults': are_defaults,
            'git_defaults': git_defaults,
            'template_source': 'temp0',
        }

    def _loadEmbeddedToolsetTemplate(self, tileset, width, height, tileset_file):
        key = (
            self._normalize_resref_value(tileset),
            int(width),
            int(height),
        )
        layout = self.TOOLSET_STARTER_TEMPLATES.get(key)
        if not layout or tileset_file is None:
            return None

        model_to_tile_id, _tile_id_to_model = self._build_tileset_model_maps(tileset_file)
        tile_values = []

        for row in layout:
            if len(row) != int(width):
                return None
            for cell in row:
                token = self._safe_text(cell)
                if not token:
                    return None

                if ':' in token:
                    model, orient_text = token.rsplit(':', 1)
                else:
                    model, orient_text = token, '0'

                model = self._normalize_resref_value(model)
                tile_id = model_to_tile_id.get(model)
                if tile_id is None:
                    return None

                try:
                    orientation = int(orient_text) % 4
                except Exception:
                    orientation = 0

                tile_values.append({
                    'Tile_AnimLoop1': 0,
                    'Tile_AnimLoop2': 0,
                    'Tile_AnimLoop3': 0,
                    'Tile_Height': 0,
                    'Tile_ID': int(tile_id),
                    'Tile_MainLight1': 0,
                    'Tile_MainLight2': 0,
                    'Tile_Orientation': int(orientation),
                    'Tile_SrcLight1': 0,
                    'Tile_SrcLight2': 0,
                })

        if len(tile_values) != int(width) * int(height):
            return None

        return {
            'tile_values': tile_values,
            'are_defaults': {},
            'git_defaults': {},
            'template_source': 'embedded-parity',
        }

    @classmethod
    def createBlankModuleFile(cls, file_path, module_name):
        """Create a minimal valid .MOD file with a blank IFO root."""
        display_name = (module_name or '').strip() or 'New Module'
        module_tag = cls._sanitize_resref(display_name, fallback='module')

        module_erf = neveredit.file.ERFFile.ERFFile('MOD')
        ifo_gff = GFFFile()
        ifo_gff.type = 'IFO '
        ifo_gff.version = 'V3.2'
        root = GFFStruct()

        root.add('Mod_Name', CExoLocString(value=display_name).toGFFEntry(), 'CExoLocString')
        root.add('Mod_Description', CExoLocString(value='').toGFFEntry(), 'CExoLocString')
        root.add('Mod_Tag', module_tag, 'CExoString')
        root.add('Mod_Entry_Area', '', 'ResRef')
        root.add('Mod_Area_list', [], 'List')
        root.add('Mod_HakList', [], 'List')
        root.add('Mod_CustomTlk', '', 'CExoString')
        root.add('VarTable', [], 'List')
        root.add('Mod_DawnHour', 6, 'INT')
        root.add('Mod_DuskHour', 18, 'INT')
        root.add('Mod_MinPerHour', 2, 'INT')
        root.add('Mod_StartDay', 1, 'INT')
        root.add('Mod_StartMonth', 1, 'INT')
        root.add('Mod_StartYear', 1372, 'INT')
        root.add('Mod_StartHour', 13, 'INT')
        root.add('Mod_XPScale', 100, 'INT')

        for script_prop in (
            'Mod_OnAcquirItem', 'Mod_OnActvtItem', 'Mod_OnClientEntr',
            'Mod_OnClientLeav', 'Mod_OnCutsnAbort', 'Mod_OnHeartbeat',
            'Mod_OnModLoad', 'Mod_OnModStart', 'Mod_OnPlrDeath',
            'Mod_OnPlrDying', 'Mod_OnPlrEqItm', 'Mod_OnPlrLvlUp',
            'Mod_OnPlrRest', 'Mod_OnPlrUnEqItm', 'Mod_OnSpawnBtnDn',
            'Mod_OnUnAqreItem', 'Mod_OnUsrDefined',
        ):
            root.add(script_prop, '', 'ResRef')

        ifo_gff.rootStructure = root
        module_erf.addResourceByName('module.IFO', ifo_gff)
        module_erf.toFile(file_path)
    
    def __init__(self,fname):
        Progressor.__init__(self)
        NeverData.__init__(self)
        self.needSave = False
        logger.debug("reading erf file %s",fname)
        self.erfFile = neveredit.file.ERFFile.ERFFile()
        self.erfFile.fromFile(fname)
        ifoEntry = self.erfFile.getEntryByNameAndExtension("module","IFO")
        if ifoEntry is None:
            ifo_entries = self.erfFile.getEntriesWithExtension('IFO')
            if ifo_entries:
                logger.warning('module IFO key "module.IFO" not found, falling back to first IFO entry')
                ifoEntry = ifo_entries[0]
            else:
                raise RuntimeError('No IFO entry found in module ERF file')
        self.addPropList('ifo',self.ifoPropList,
                         self.erfFile.getEntryContents(ifoEntry).getRoot())
        logger.debug("checking for old style Mod_Hak")
        prop = self['Mod_Hak']
        if prop != None:
            logger.info('Old-Style Mod_Hak found,'
                        'changing to new style Mod_HakList')
            new_prop = self['Mod_HakList']
            if not new_prop:
                self.getGFFStruct('ifo').add('Mod_HakList',[],'List')
                new_prop = self['Mod_HakList']
            if prop:
                new_prop.append(prop)
            self.needSave = True
            
        prop = self['Mod_CustomTlk']
        if prop == None:
            logger.info("Old (pre-1.59) module with no Mod_CustomTlk,"
                        "adding an empty one")
            self.getGFFStruct('ifo').add('Mod_CustomTlk',"",'CExoString')
            self.needSave = True
        prop = self['VarTable']
        if prop == None:
            logger.info("no VarTable found, adding an empty one")
            self.getGFFStruct('ifo').add('VarTable',[],'List')
            self.needSave = True

        self.scripts = None
        self.conversations = None
        self.areas = {}
        self.soundBlueprints = None
        self.triggerBlueprints = None
        self.encounterBlueprints = None

        try:
            self.facObject = neveredit.game.Factions.Factions(self.erfFile)
        except RuntimeError:
            self.facObject = None
        self.factions= {}
    
    def getFileName(self):
        return self.erfFile.filename
    
    def removeProperty(self,label):
        if label in self.ifoPropList:
            (s,t) = self.gffstructDict['ifo'].getTargetStruct(label)
            print('removing',t)
            s.removeEntry(t)

    def getHAKNames(self):
        if self['Mod_HakList'] != None:
            return [p['Mod_Hak'] + '.hak'
                    for p in self['Mod_HakList']]
        elif self['Mod_Hak'] != None:
            return [self['Mod_Hak']]
        else:
            return []
    
    def getName(self,lang=0):
        '''Looks up Mod_Name in the ifo file'''
        return self['Mod_Name'].getString(lang)
    
    def getAreaNames(self):
        '''Returns a list of area resref names
        @return: list of area resrefs
        '''
        return [a['Area_Name'] for a in self['Mod_Area_list']]

    def getArea(self,name):
        '''Get an area by its name
        @param name: name of the area object to return'''
        if name in self.areas:
            return self.areas[name]
        else:
            try:
                a = Area(self.erfFile,name)
            except Exception:
                logger.warning('skipping area with missing/broken resources: %r', name)
                return None
            self.areas[name] = a
            return a

    def getEntryArea(self):
        entry_area = self.getArea(self['Mod_Entry_Area'])
        if entry_area is not None:
            return entry_area
        for area in self.getAreas().values():
            return area
        return None
    
    def getAreas(self):
        """Get the areas in this ERF.
        @return: a dict of Area names (keys) and objects (values)."""
        names = self.getAreaNames()
        areas = {}
        total = len(names)
        if total == 0:
            self.setProgress(0)
            return areas
        start = time.time()
        for i, n in enumerate(names, 1):
            elapsed = max(0.001, time.time() - start)
            progress = (float(i - 1) / float(total)) * 100.0
            rate = float(i - 1) / elapsed if i > 1 else 0.0
            remaining = (total - (i - 1)) / rate if rate > 0 else 0.0
            self.setStatus('Loading areas %d/%d (ETA %s)' %
                           (i - 1, total, self._format_eta(remaining)))
            self.setProgress(progress)
            area = self.getArea(n)
            if area is not None:
                areas[n] = area
        self.setProgress(100.0)
        self.setStatus('Loaded %d area definitions' % len(areas))
        self.setProgress(0)
        return areas

    def getTags(self):
        """Get a dictionary of all tags in this module.
        The dictionary will look like this::
        
        {
        'module': <module_Tag>,
        'areas':  {<area_tag>: <tag_dict_for_area>}
        }

        Where <tag_dict_for_area> is the dictionary produced by
        L{neveredit.game.Area.Area.getTags} for the area in question.

        Note that this function needs to read all areas and their
        contents, and thus will be slow unless they're already
        loaded.
        
        @return: the tag dictionary for this module
        """
        
        tags = {}
        tags['module'] = self['Mod_Tag']
        tags['areas'] = {}
        for a in list(self.getAreas().values()):
            tags['areas'][a['Tag']] = a.getTags()
        return tags
    
    def getConversations(self):
        """Get the conversations in this ERF.
        @return: A dict of name:L{neveredit.game.Conversation.Conversation} objects."""
        if not self.conversations:
            entries = self.erfFile.getEntriesWithExtension('DLG')
            self.conversations = {}
            for s in entries:
                self.conversations[self._entry_resref_name(s)] = self.erfFile.getEntryContents(s)
        return self.conversations

    def getScripts(self):
        """Get the scripts in this ERF.
        @return: A dict of name:Script objects."""
        if not self.scripts:
            entries = self.erfFile.getEntriesWithExtension('NSS')
            self.scripts = {}
            for s in entries:
                self.scripts[self._entry_resref_name(s)] = self.erfFile.getEntryContents(s)
        return self.scripts

    def getFactions(self):
        """Get the factions in the module"""
        if self.facObject and not self.factions:            
            self.facObject.readContents()
            for f in self.facObject.factionList:
                self.factions[f.getName()] = f
        return self.factions

    def getSoundBlueprints(self):
        """Get .UTS sound blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.soundBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTS')
            self.soundBlueprints = {}
            for s in entries:
                self.soundBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.soundBlueprints

    def getTriggerBlueprints(self):
        """Get .UTT trigger blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.triggerBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTT')
            self.triggerBlueprints = {}
            for s in entries:
                self.triggerBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.triggerBlueprints

    def getEncounterBlueprints(self):
        """Get .UTE encounter blueprints stored in this module ERF.
        @return: dict of resref:GFFFile"""
        if self.encounterBlueprints is None:
            entries = self.erfFile.getEntriesWithExtension('UTE')
            self.encounterBlueprints = {}
            for s in entries:
                self.encounterBlueprints[self._entry_resref_name(s)] = \
                    self.erfFile.getEntryContents(s)
        return self.encounterBlueprints

    def addScript(self,s):
        if not self.scripts:
            self.getScripts()
        self.scripts[s.getName()[:-4]] = s
        self.commit()
        neverglobals.getResourceManager().moduleResourceListChanged()
        
    def commit(self):
        if self.scripts:
            for s in list(self.scripts.values()):
                self.erfFile.addResourceByName(s.getName(),s)
                if s.getCompiledScript():
                    self.erfFile.addResourceByName(s.getName()[:-4] + '.ncs',s.getCompiledScript())

    def updateReputeFac(self):
        # Blank/new modules may not have repute.fac yet.
        if not self.facObject:
            return

        try:
            repute_entry = self.erfFile.getEntryByNameAndExtension('repute', 'FAC')
            if not repute_entry:
                logger.warning('repute.fac not found; skipping faction table update')
                return

            raw_repute_fac = self.erfFile.getRawEntryContents(repute_entry)
            repute_gff = GFFFile()
            repute_gff.fromFile(BytesIO(raw_repute_fac))

            root = repute_gff.rootStructure
            if root.hasEntry('FactionList'):
                root.removeEntry('FactionList')
            if root.hasEntry('RepList'):
                root.removeEntry('RepList')

            self.facObject.readContents()
            repute_gff.add('FactionList', [x.getGFFStruct('factStruct')
                                           for x in self.facObject.factionList], 'List')
            repute_gff.add('RepList', [x.getGFFStruct('repStruct')
                                       for x in self.facObject.RepList], 'List')

            out_buffer = BytesIO()
            repute_gff.toFile(out_buffer)
            self.erfFile.addRawResourceByName('repute.FAC', out_buffer.getvalue())
        except Exception:
            logger.exception('failed to update repute.fac; continuing save')

    def saveToReadFile(self):
        self.commit()
        self.updateReputeFac()
        self.erfFile.saveToReadFile()

    def toFile(self,fpath):
        self.commit()
        self.erfFile.toFile(fpath)

    def saveAs(self,fpath):
        self.commit()
        self.erfFile.toFile(fpath)
        self.erfFile.reassignReadFile(fpath)

    def addResourceFile(self,fname):
        key = neveredit.game.ResourceManager.ResourceManager.keyFromName(\
                                                                basename(fname))
        resource = neverglobals.getResourceManager().interpretResourceContents(\
                                                key,open(fname,'rb').read())
        self.erfFile.addResource(key,resource)
        
    def addERFFile(self,fname):
        self.erfFile.addFile(fname)
        self.updateAreaList()

    def createNewArea(self, name, resref, tileset, width, height,
                      generate_border_scene_life=True):
        """Create a new blank area and register it in this module."""
        from neveredit.file.CExoLocString import CExoLocString as _CExoLocString

        resref = resref.strip().lower()[:16]

        # ── Read tileset-contextual defaults from .SET ──────────────────────
        _day_night_cycle = 1
        _music_day = 0
        _music_night = 0
        _ambient_day = 0
        _ambient_night = 0
        _moon_ambient_color = 0x404040
        _moon_diffuse_color = 0x404040
        _moon_fog_color = 0x404040
        _sun_ambient_color = 0xA0A0A0
        _sun_diffuse_color = 0xFFFFFF
        _sun_fog_color = 0xC8C8C8
        _loadscreen_id = 0
        _ts = neverglobals.getResourceManager().getResourceByName(tileset + '.set')
        if _ts is not None:
            try: _day_night_cycle = 0 if int(_ts.get('GENERAL', 'interior', fallback='0')) else 1
            except Exception: pass
            try:
                _music_day = int(_ts.get('GENERAL', 'defaultmusic', fallback='0'))
                _music_night = _music_day
            except Exception: pass
            try:
                _ambient_day = int(_ts.get('GENERAL', 'defaultenvmap', fallback='0'))
                _ambient_night = _ambient_day
            except Exception: pass

        _template = self._loadToolsetTemp0Template(tileset, width, height)
        if _template is None and _ts is not None:
            _template = self._loadEmbeddedToolsetTemplate(tileset, width, height, _ts)
        if _template:
            are_defaults = _template.get('are_defaults', {})
            git_defaults = _template.get('git_defaults', {})
            _day_night_cycle = int(are_defaults.get('DayNightCycle', _day_night_cycle))
            _moon_ambient_color = int(are_defaults.get('MoonAmbientColor', _moon_ambient_color))
            _moon_diffuse_color = int(are_defaults.get('MoonDiffuseColor', _moon_diffuse_color))
            _moon_fog_color = int(are_defaults.get('MoonFogColor', _moon_fog_color))
            _sun_ambient_color = int(are_defaults.get('SunAmbientColor', _sun_ambient_color))
            _sun_diffuse_color = int(are_defaults.get('SunDiffuseColor', _sun_diffuse_color))
            _sun_fog_color = int(are_defaults.get('SunFogColor', _sun_fog_color))
            _loadscreen_id = int(are_defaults.get('LoadScreenID', _loadscreen_id))
            _ambient_day = int(git_defaults.get('AmbientSndDay', _ambient_day))
            _ambient_night = int(git_defaults.get('AmbientSndNight', _ambient_night))
            _music_day = int(git_defaults.get('MusicDay', _music_day))
            _music_night = int(git_defaults.get('MusicNight', _music_night))

        # Determine the correct blank-fill tile for this tileset.  NWN's
        # toolset uses the first tile whose four corner terrain types all
        # match GENERAL.default (e.g. 'Wall' for interior tilesets).
        # Tile 0 is usually a corner transition piece and causes artefacts.
        _default_tile_id = 0
        if _ts is not None:
            try:
                _default_tile_id = _ts.getDefaultTileID()
            except Exception:
                pass

        # ── ARE ──────────────────────────────────────────────────────────────
        are_gff = GFFFile()
        are_gff.type = 'ARE '
        are_gff.version = 'V3.2'
        r = GFFStruct()

        loc_name = _CExoLocString(value=name, langID=0, gender=0)
        r.add('Name', loc_name.toGFFEntry(), 'CExoLocString')
        r.add('Tag', resref, 'CExoString')
        r.add('Tileset', tileset, 'ResRef')
        r.add('Width', width, 'INT')
        r.add('Height', height, 'INT')
        r.add('ChanceLightning', 0, 'BYTE')
        r.add('ChanceRain', 0, 'BYTE')
        r.add('ChanceSnow', 0, 'BYTE')
        r.add('DayNightCycle', _day_night_cycle, 'BYTE')
        r.add('IsNight', 0, 'BYTE')
        r.add('ModListenCheck', 0, 'INT')
        r.add('ModSpotCheck', 0, 'INT')
        r.add('MoonAmbientColor', _moon_ambient_color, 'DWORD')
        r.add('MoonDiffuseColor', _moon_diffuse_color, 'DWORD')
        r.add('MoonFogAmount', 0, 'BYTE')
        r.add('MoonFogColor', _moon_fog_color, 'DWORD')
        r.add('MoonShadows', 1, 'BYTE')
        r.add('NoRest', 0, 'BYTE')
        r.add('OnEnter', '', 'ResRef')
        r.add('OnExit', '', 'ResRef')
        r.add('OnHeartbeat', '', 'ResRef')
        r.add('OnUserDefined', '', 'ResRef')
        r.add('PlayerVsPlayer', 0, 'BYTE')
        r.add('ShadowOpacity', 100, 'BYTE')
        r.add('SunAmbientColor', _sun_ambient_color, 'DWORD')
        r.add('SunDiffuseColor', _sun_diffuse_color, 'DWORD')
        r.add('SunFogAmount', 0, 'BYTE')
        r.add('SunFogColor', _sun_fog_color, 'DWORD')
        r.add('SunShadows', 1, 'BYTE')
        r.add('WindPower', 0, 'BYTE')
        r.add('LoadScreenID', _loadscreen_id, 'WORD')
        r.add('ID', 0, 'DWORD')
        r.add('Flags', 0, 'DWORD')
        r.add('Comments', '', 'CExoString')
        r.add('Version', 1, 'DWORD')
        tiles = []
        template_tiles = None
        template_source = self._safe_text((_template or {}).get('template_source'))
        if _template:
            candidate = _template.get('tile_values')
            if candidate and len(candidate) == width * height:
                template_tiles = candidate

        if template_tiles:
            for src in template_tiles:
                t = GFFStruct(1)
                t.add('Tile_AnimLoop1', int(src.get('Tile_AnimLoop1', 0)), 'INT')
                t.add('Tile_AnimLoop2', int(src.get('Tile_AnimLoop2', 0)), 'INT')
                t.add('Tile_AnimLoop3', int(src.get('Tile_AnimLoop3', 0)), 'INT')
                t.add('Tile_Height', int(src.get('Tile_Height', 0)), 'INT')
                t.add('Tile_ID', int(src.get('Tile_ID', _default_tile_id)), 'INT')
                t.add('Tile_MainLight1', int(src.get('Tile_MainLight1', 0)), 'BYTE')
                t.add('Tile_MainLight2', int(src.get('Tile_MainLight2', 0)), 'BYTE')
                t.add('Tile_Orientation', int(src.get('Tile_Orientation', 0)), 'INT')
                t.add('Tile_SrcLight1', int(src.get('Tile_SrcLight1', 0)), 'INT')
                t.add('Tile_SrcLight2', int(src.get('Tile_SrcLight2', 0)), 'INT')
                tiles.append(t)
            logger.info('Using official template (%s) for exact parity - border already randomized',
                        template_source or 'template')
        else:
            for _ in range(width * height):
                t = GFFStruct(1)
                t.add('Tile_AnimLoop1', 0, 'INT')
                t.add('Tile_AnimLoop2', 0, 'INT')
                t.add('Tile_AnimLoop3', 0, 'INT')
                t.add('Tile_Height', 0, 'INT')
                t.add('Tile_ID', _default_tile_id, 'INT')
                t.add('Tile_MainLight1', 0, 'BYTE')
                t.add('Tile_MainLight2', 0, 'BYTE')
                t.add('Tile_Orientation', 0, 'INT')
                t.add('Tile_SrcLight1', 0, 'INT')
                t.add('Tile_SrcLight2', 0, 'INT')
                tiles.append(t)

            # Only use the fallback generator when no template tiles were available.
        if _ts is not None and not template_tiles and generate_border_scene_life:
            scene_life_seed = self._scene_life_seed(
                tileset_resref=tileset,
                width=width,
                height=height,
                area_resref=resref,
                mode='create',
                nonce_value=0,
            )
            report = self._generate_border_scene_life(
                tiles=tiles,
                width=width,
                height=height,
                tileset_resref=tileset,
                tileset_file=_ts,
                border_width=self.SCENE_LIFE_BORDER_WIDTH,
                reset_border=False,
                density_min=0.40,
                density_max=0.60,
                rng_seed=scene_life_seed,
            )
            if report.get('changed'):
                self._mark_area_scene_life_generated(r, 'create', scene_life_seed, 0)
            else:
                logger.info('Scene life fallback skipped: %s', report.get('reason', 'unknown'))

        r.add('Tile_List', tiles, 'List')
        are_gff.rootStructure = r

        # ── GIT ──────────────────────────────────────────────────────────────
        git_gff = GFFFile()
        git_gff.type = 'GIT '
        git_gff.version = 'V3.2'
        g = GFFStruct()
        ap = GFFStruct()
        ap.add('AmbientSndDay', _ambient_day, 'INT')
        ap.add('AmbientSndDayVol', 127, 'BYTE')
        ap.add('AmbientSndNight', _ambient_night, 'INT')
        ap.add('AmbientSndNitVol', 127, 'BYTE')
        ap.add('EnvAudio', 0, 'INT')
        ap.add('MusicBattle', 0, 'INT')
        ap.add('MusicDay', _music_day, 'INT')
        ap.add('MusicDelay', 0, 'INT')
        ap.add('MusicNight', _music_night, 'INT')
        g.add('AreaProperties', ap, 'Struct')
        g.add('Creature List', [], 'List')
        g.add('Door List', [], 'List')
        g.add('Encounter List', [], 'List')
        g.add('List', [], 'List')
        g.add('Placeable List', [], 'List')
        g.add('SoundList', [], 'List')
        g.add('Trigger List', [], 'List')
        g.add('WaypointList', [], 'List')
        git_gff.rootStructure = g

        # ── GIC ──────────────────────────────────────────────────────────────
        gic_gff = GFFFile()
        gic_gff.type = 'GIC '
        gic_gff.version = 'V3.2'
        gic_gff.rootStructure = GFFStruct()

        # ── Register in ERF ──────────────────────────────────────────────────
        self.erfFile.addResourceByName(resref + '.ARE', are_gff)
        self.erfFile.addResourceByName(resref + '.GIT', git_gff)
        self.erfFile.addResourceByName(resref + '.GIC', gic_gff)

        # ── Append to Mod_Area_list ───────────────────────────────────────────
        area_list = self.gffstructDict['ifo'].getInterpretedEntry('Mod_Area_list')
        if area_list is None:
            area_list = []
            self.gffstructDict['ifo'].add('Mod_Area_list', area_list, 'List')
        area_entry = GFFStruct()
        area_entry.add('Area_Name', resref, 'ResRef')
        area_list.append(area_entry)

        entry_area = self.gffstructDict['ifo'].getInterpretedEntry('Mod_Entry_Area')
        if not entry_area:
            self.gffstructDict['ifo'].setInterpretedEntry('Mod_Entry_Area', resref)

        neverglobals.getResourceManager().moduleResourceListChanged()
        self.needSave = True

        area = Area(self.erfFile, resref)
        self.areas[resref] = area
        return area

    def rerollAreaPerimeterSceneLife(self, area, border_width=2):
        """Reroll the random perimeter tiles for an existing exterior area.

        Returns a tuple ``(changed, reason)`` where ``changed`` is a bool and
        ``reason`` contains a short status message suitable for UI display.
        """
        if area is None:
            return (False, 'No area selected.')

        are_struct = area.getGFFStruct('are')
        if are_struct is None:
            return (False, 'Area data is missing.')

        try:
            width = int(are_struct.getInterpretedEntry('Width'))
            height = int(are_struct.getInterpretedEntry('Height'))
        except Exception:
            return (False, 'Area size is invalid.')

        if width <= 0 or height <= 0:
            return (False, 'Area dimensions are invalid.')

        tile_list = are_struct.getInterpretedEntry('Tile_List') or []
        if len(tile_list) != width * height:
            return (False, 'Area tile list is incomplete.')

        tileset_value = are_struct.getInterpretedEntry('Tileset')
        tileset_resref = self._normalize_resref_value(tileset_value)
        if not tileset_resref:
            return (False, 'Area tileset is missing.')

        rm = neverglobals.getResourceManager()
        if rm is None:
            return (False, 'Resource manager is not available.')

        tileset_file = rm.getResourceByName(tileset_resref + '.set')
        if tileset_file is None:
            return (False, 'Tileset data could not be loaded.')

        area_resref = getattr(area, 'name', '')
        next_nonce = self._extract_scene_life_nonce(are_struct) + 1
        scene_life_seed = self._scene_life_seed(
            tileset_resref=tileset_resref,
            width=width,
            height=height,
            area_resref=area_resref,
            mode='reroll',
            nonce_value=next_nonce,
        )

        report = self._generate_border_scene_life(
            tiles=tile_list,
            width=width,
            height=height,
            tileset_resref=tileset_resref,
            tileset_file=tileset_file,
            border_width=border_width,
            reset_border=True,
            density_min=0.25,
            density_max=0.40,
            rng_seed=scene_life_seed,
        )
        if not report.get('changed'):
            return (False, report.get('reason', 'No border placements were applied.'))

        self._mark_area_scene_life_generated(
            are_struct,
            source_label='reroll',
            seed_value=scene_life_seed,
            nonce_value=next_nonce,
        )
        area.discardTiles()
        self.needSave = True
        return (True, report.get('reason', 'Perimeter scene life rerolled.'))

    def getKeyList(self):
        return self.erfFile.getKeyList()

    def getERFFile(self):
        return self.erfFile
    
    def setProgressDisplay(self,p):
        self.erfFile.setProgressDisplay(p)

    def getEntriesWithExtension(self,ext):
        return self.erfFile.getEntriesWithExtension(ext)

    def setProgress(self,p):
        self.erfFile.setProgress(p)
