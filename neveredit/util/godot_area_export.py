"""Export an NWN area (doors, placeables, creatures, sounds) to a Godot-ready
folder layout under /Users/jws/neveredit/data/<area_name>/.

Output structure::

    data/<area_name>/
        scene.json          — area manifest (positions, rotations, model refs)
        models/
            <object_tag_or_name>/
                <label>.gltf
                textures/   — textures used by this model
                metadata.json — source object data and resolved 2DA rows
        sounds/
            <sound_tag_or_name>.json — positional sound descriptor

The scene.json format is designed to be imported by a Godot 4 GDScript loader;
its schema is intentionally straightforward JSON so the Godot side requires no
compiled parser.
"""

import json
import logging
import os
import re

logger = logging.getLogger('neveredit.util.godot_area_export')

# Base directory for all exported areas.
BASE_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'data')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_dir_name(text):
    """Return a filesystem-safe directory name derived from *text*."""
    name = re.sub(r'[^\w.-]', '_', str(text or 'area')).strip('._')
    return name or 'area'


def _safe_file_name(text):
    name = re.sub(r'[^\w.-]', '_', str(text or 'object')).strip('._')
    return name or 'object'


def _clean_label(text):
    """Return a human-readable label with collapsed whitespace."""
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except Exception:
            text = text.decode('latin-1', 'ignore')
    label = re.sub(r'\s+', ' ', str(text or '')).strip()
    return label


def _json_safe(value):
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8')
        except Exception:
            value = value.decode('latin-1', 'ignore')
    get_string = getattr(value, 'getString', None)
    if callable(get_string):
        try:
            return get_string()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    if isinstance(value, str):
        return value.split('\0', 1)[0]
    return str(value)


def _parse_int_token(value):
    text = _clean_label(_json_safe(value)).split('\0', 1)[0].strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _first_non_empty(values):
    for value in values:
        cleaned = _clean_label(value)
        if cleaned:
            return cleaned
    return ''


def _get_thing_label(thing, category):
    """Choose a readable label for exported assets and scene nodes."""
    candidates = []
    try:
        candidates.append(thing.getName())
    except Exception:
        pass
    try:
        candidates.append(thing['Tag'])
    except Exception:
        pass
    candidates.append(getattr(thing, 'modelName', None))
    label = _first_non_empty(candidates)
    if label:
        return label
    return category.capitalize()


def _get_thing_stem_label(thing, fallback_name, category):
    """Choose a filename stem source, preferring stable identifiers."""
    try:
        tag = _clean_label(thing['Tag'])
        if tag:
            return tag
    except (AttributeError, KeyError, TypeError):
        pass
    if fallback_name:
        return fallback_name
    return category


def _make_unique_stem(preferred_label, used_stems):
    """Return a unique filename stem based on a readable label."""
    stem = _safe_file_name(preferred_label)
    if stem not in used_stems:
        used_stems.add(stem)
        return stem
    i = 2
    while True:
        candidate = '%s_%d' % (stem, i)
        if candidate not in used_stems:
            used_stems.add(candidate)
            return candidate
        i += 1


def _get_x(thing):
    try:
        return float(thing.getX() or 0.0)
    except Exception:
        return 0.0


def _get_y(thing):
    try:
        return float(thing.getY() or 0.0)
    except Exception:
        return 0.0


def _get_z(thing):
    try:
        return float(thing.getZ() or 0.0)
    except Exception:
        return 0.0


def _get_bearing(thing):
    """Return bearing in radians (0 = north / +Y axis, increasing clockwise)."""
    try:
        b = thing.getBearing()
        if b is not None:
            return float(b)
    except Exception:
        pass
    return 0.0


def _bearing_to_godot_rotation_y(bearing_radians):
    """Convert NWN bearing (radians, CCW from +Y) to Godot -Y rotation (radians)."""
    # NWN bearing 0 = facing +Y, increases counter-clockwise.
    # Godot rotation_y 0 = facing -Z, positive = CCW from above in right-hand.
    # NWN X/Y → Godot X/Z, so we need a 90° shift.
    return bearing_radians


# ---------------------------------------------------------------------------
# Model export helpers
# ---------------------------------------------------------------------------

def _is_renderable_mesh_node(node):
    if node is None:
        return False
    if not hasattr(node, 'hasMesh') or not node.hasMesh():
        return False
    if hasattr(node, 'renderFlag') and not bool(node.renderFlag):
        return False
    if hasattr(node, 'isAABBMesh') and node.isAABBMesh():
        return False
    if getattr(node, 'vertices', None) is None or len(node.vertices) == 0:
        return False
    vil = getattr(node, 'vertexIndexLists', None)
    if vil is None or len(vil) == 0:
        return False
    return True


_GL_TRIANGLES = 4
_GL_TRIANGLE_STRIP = 5


def _get_node_draw_mode(node):
    if getattr(node, 'indicesFromFaces', False):
        return _GL_TRIANGLES
    mode = getattr(node, 'triangleMode', None)
    if mode == 3:
        return _GL_TRIANGLES
    if mode == 4:
        return _GL_TRIANGLE_STRIP
    if mode in (_GL_TRIANGLES,):
        return _GL_TRIANGLES
    if mode in (_GL_TRIANGLE_STRIP, 5):
        return _GL_TRIANGLE_STRIP
    return _GL_TRIANGLES


def _export_model(model, model_file_stem, models_dir):
    """Export *model* into *models_dir/<model_file_stem>/.

    Returns a dict with keys:
      model_path, model_dir, file_stem, texture_count, animation_count
    or None if the model has no renderable geometry.
    """
    from neveredit.util import gltf_export
    safe = _safe_file_name(model_file_stem)
    model_output_dir = os.path.join(models_dir, safe)
    try:
        info = gltf_export.export_model_to_gltf_folder(
            model, model_output_dir, safe,
            _is_renderable_mesh_node, _get_node_draw_mode)
        return {
            'model_path': 'models/' + safe + '/' + safe + '.gltf',
            'model_dir': 'models/' + safe,
            'file_stem': safe,
            'texture_count': int(info.get('texture_count', 0)),
            'animation_count': int(info.get('animation_count', 0)),
        }
    except ValueError as exc:
        logger.debug('skipping model %s: %s', model_file_stem, exc)
        return None
    except Exception:
        logger.exception('failed to export model %s', model_file_stem)
        return None


def _collect_twoda_metadata(thing):
    """Extract 2DA-indexed properties and resolved row data for *thing*."""
    from neveredit.util import neverglobals

    rm = neverglobals.getResourceManager()
    if rm is None:
        return {
            'references': [],
            'rows': [],
        }
    references = []
    rows_by_key = {}
    prop_lists = getattr(thing, 'propListDict', {})

    for source, plist in prop_lists.items():
        for prop_name, spec in plist.items():
            parts = str(spec).split(',')
            if len(parts) < 2 or parts[0] != '2daIndex':
                continue

            table_name = _clean_label(parts[1]).lower()
            try:
                raw_value = thing[prop_name]
            except (AttributeError, KeyError, TypeError):
                raw_value = None
            index = _parse_int_token(raw_value)

            ref = {
                'property': prop_name,
                'source': source,
                'table': table_name,
                'raw_value': _json_safe(raw_value),
            }
            if index is not None:
                ref['index'] = index
            if len(parts) > 2:
                ref['label_column'] = parts[2]
            references.append(ref)

            if index is None:
                continue
            key = (table_name, index)
            if key in rows_by_key:
                continue

            row_info = {
                'table': table_name,
                'index': index,
                'columns': {},
            }

            twoda = rm.getResourceByName(table_name)
            if twoda is None:
                row_info['missing_table'] = True
                rows_by_key[key] = row_info
                continue

            if index < 0 or index >= twoda.getRowCount():
                row_info['missing_row'] = True
                rows_by_key[key] = row_info
                continue

            for col in getattr(twoda, 'columnLabels', []):
                if col == 'RowNumber':
                    row_info['columns'][col] = index
                    continue
                try:
                    value = twoda.getEntry(index, col)
                except (AttributeError, IndexError, KeyError, TypeError):
                    continue
                row_info['columns'][col] = _json_safe(value)
            rows_by_key[key] = row_info

    rows = [rows_by_key[k] for k in sorted(rows_by_key.keys())]
    return {
        'references': references,
        'rows': rows,
    }


def _write_model_metadata(models_dir, model_export, thing, category, name, model_key):
    """Write metadata.json next to an exported model and return relative path."""
    model_stem = model_export['file_stem']
    model_dir = os.path.join(models_dir, model_stem)
    metadata_rel = 'models/' + model_stem + '/metadata.json'
    metadata_path = os.path.join(model_dir, 'metadata.json')

    data = {
        'neveredit_export': True,
        'schema': 'godot_model_metadata_v1',
        'category': category,
        'label': name,
        'source_model_key': _json_safe(model_key),
        'resolved_model_name': _json_safe(getattr(thing, 'modelName', None)),
        'model_file': model_export['model_path'].split('/', 2)[-1],
        'texture_count': model_export.get('texture_count', 0),
        'animation_count': model_export.get('animation_count', 0),
        'twoda': _collect_twoda_metadata(thing),
    }

    try:
        tag = thing['Tag']
        if tag:
            data['tag'] = _json_safe(tag)
    except (AttributeError, KeyError, TypeError):
        pass

    with open(metadata_path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    return metadata_rel


# ---------------------------------------------------------------------------
# Object-type exporters
# ---------------------------------------------------------------------------

def _export_things_with_model(things, category, models_dir, used_model_stems):
    """Export models for a list of situated things that have a getModel().

    Returns a list of node dicts for scene.json.
    """
    nodes = []
    for thing in things:
        name = _get_thing_label(thing, category)

        # Try to get the model
        model = None
        model_key = None
        try:
            model = thing.getModel()
            model_key = getattr(thing, 'modelName', None) or name or 'unknown'
        except Exception:
            pass

        gltf_relative = None
        metadata_relative = None
        if model is not None and model_key:
            stem_source = _get_thing_stem_label(thing, name, category)
            model_file_stem = _make_unique_stem(stem_source, used_model_stems)
            model_export = _export_model(model, model_file_stem, models_dir)
            if model_export:
                gltf_relative = model_export['model_path']
                metadata_relative = _write_model_metadata(
                    models_dir, model_export, thing, category, name, model_key)

        node = {
            'type': category,
            'name': name,
            'position': [_get_x(thing), _get_y(thing), _get_z(thing)],
            'bearing_radians': _get_bearing(thing),
        }
        if gltf_relative:
            node['model'] = gltf_relative
        if metadata_relative:
            node['model_metadata'] = metadata_relative

        # Tag for scripting cross-reference
        try:
            tag = thing['Tag']
            if tag:
                node['tag'] = str(tag)
        except Exception:
            pass

        nodes.append(node)
    return nodes


def _export_sounds(sounds, sounds_dir):
    """Return scene nodes for area sounds and write per-sound descriptors."""
    nodes = []
    used_sound_stems = set()
    for sound in sounds:
        name = ''
        try:
            name = str(sound.getName() or '')
        except Exception:
            pass

        node = {
            'type': 'sound',
            'name': name,
            'position': [_get_x(sound), _get_y(sound), _get_z(sound)],
        }

        # Gather useful sound properties for the Godot loader
        for prop in ('SoundResRef', 'MaxDistance', 'MinDistance',
                     'Volume', 'Continuous', 'Positional', 'Tag'):
            try:
                val = sound[prop]
                if val is not None:
                    node[prop.lower()] = str(val) if isinstance(val, bytes) else val
            except Exception:
                pass

        sound_ref = _first_non_empty([
            node.get('tag'),
            name,
            node.get('soundresref'),
            'sound',
        ])
        sound_stem = _make_unique_stem(sound_ref, used_sound_stems)
        descriptor_rel = 'sounds/' + sound_stem + '.json'
        descriptor_path = os.path.join(sounds_dir, sound_stem + '.json')

        descriptor = {
            'neveredit_export': True,
            'schema': 'godot_sound_metadata_v1',
            'name': name,
            'type': 'sound',
            'position': node['position'],
            'properties': {
                'soundresref': node.get('soundresref'),
                'maxdistance': node.get('maxdistance'),
                'mindistance': node.get('mindistance'),
                'volume': node.get('volume'),
                'continuous': node.get('continuous'),
                'positional': node.get('positional'),
                'tag': node.get('tag'),
            },
        }
        with open(descriptor_path, 'w', encoding='utf-8') as fh:
            json.dump(descriptor, fh, indent=2, ensure_ascii=False)

        node['sound_file'] = descriptor_rel

        nodes.append(node)
    return nodes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_area(area, progress_callback=None):
    """Export *area* to data/<area_tag_or_name>/.

    Parameters
    ----------
    area:
        An ``Area`` instance (readContents() will be called if needed).
    progress_callback:
        Optional callable(message: str) for UI status updates.

    Returns
    -------
    dict with keys:
        'output_dir': str — absolute path of the created directory
        'gltf_count': int
        'sound_count': int
        'node_count': int
    """
    def _report(msg):
        logger.info(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    # Make sure area contents are loaded.
    area.readContents()

    # Decide on directory name.  Prefer the internal file name (area.name)
    # which is always ASCII-safe, falling back to the translated display name.
    area_dir_name = _safe_dir_name(area.name or area.getName())
    output_dir = os.path.join(BASE_DATA_DIR, area_dir_name)
    models_dir = os.path.join(output_dir, 'models')
    sounds_dir = os.path.join(output_dir, 'sounds')

    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(sounds_dir, exist_ok=True)

    _report('Exporting area "%s" → %s' % (area.getName(), output_dir))

    used_model_stems = set()
    scene_nodes = []

    # --- Doors ---
    doors = area.getDoors() or []
    _report('Exporting %d door(s)...' % len(doors))
    scene_nodes += _export_things_with_model(
        doors, 'door', models_dir, used_model_stems)

    # --- Placeables ---
    placeables = area.getPlaceables() or []
    _report('Exporting %d placeable(s)...' % len(placeables))
    scene_nodes += _export_things_with_model(
        placeables, 'placeable', models_dir, used_model_stems)

    # --- Creatures ---
    creatures = area.getCreatures() or []
    _report('Exporting %d creature(s)...' % len(creatures))
    scene_nodes += _export_things_with_model(
        creatures, 'creature', models_dir, used_model_stems)

    # --- Sounds ---
    sounds = area.getSounds() or []
    _report('Exporting %d sound(s)...' % len(sounds))
    sound_nodes = _export_sounds(sounds, sounds_dir)
    scene_nodes += sound_nodes

    # --- Write scene.json ---
    gltf_count = sum(1 for node in scene_nodes if 'model' in node)

    scene = {
        'neveredit_export': True,
        'area_name': area.getName(),
        'area_tag': str(area['Tag'] or ''),
        'area_dir': area_dir_name,
        'node_count': len(scene_nodes),
        'nodes': scene_nodes,
    }

    scene_path = os.path.join(output_dir, 'scene.json')
    with open(scene_path, 'w', encoding='utf-8') as fh:
        json.dump(scene, fh, indent=2, ensure_ascii=False)

    _report('Export complete: %d models, %d sounds, %d total nodes' %
            (gltf_count, len(sound_nodes), len(scene_nodes)))

    return {
        'output_dir': output_dir,
        'gltf_count': gltf_count,
        'sound_count': len(sound_nodes),
        'node_count': len(scene_nodes),
    }
