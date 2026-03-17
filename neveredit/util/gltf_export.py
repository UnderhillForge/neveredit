import base64
import io
import json
import os
import re
import struct

GL_TRIANGLES = 0x0004
GL_TRIANGLE_STRIP = 0x0005
GL_TRIANGLE_FAN = 0x0006


class _GLTFBuilder:
    def __init__(self):
        self.buffer = bytearray()
        self.buffer_views = []
        self.accessors = []

    def _append_bytes(self, payload, target=None):
        start = len(self.buffer)
        self.buffer.extend(payload)
        while len(self.buffer) % 4:
            self.buffer.append(0)
        view = {
            'buffer': 0,
            'byteOffset': start,
            'byteLength': len(payload),
        }
        if target is not None:
            view['target'] = int(target)
        view_index = len(self.buffer_views)
        self.buffer_views.append(view)
        return view_index

    def add_float_accessor(self, rows, accessor_type, include_min_max=False, animation=False):
        """Add a float accessor.  Pass animation=True for animation data (no buffer target)."""
        flattened = []
        for row in rows:
            for value in row:
                flattened.append(float(value))

        if flattened:
            payload = struct.pack('<%sf' % len(flattened), *flattened)
        else:
            payload = b''
        target = None if animation else 34962
        view_index = self._append_bytes(payload, target=target)

        accessor = {
            'bufferView': view_index,
            'componentType': 5126,
            'count': len(rows),
            'type': accessor_type,
        }

        if include_min_max and rows:
            width = len(rows[0])
            mins = [float(rows[0][i]) for i in range(width)]
            maxs = [float(rows[0][i]) for i in range(width)]
            for row in rows[1:]:
                for i in range(width):
                    value = float(row[i])
                    if value < mins[i]:
                        mins[i] = value
                    if value > maxs[i]:
                        maxs[i] = value
            accessor['min'] = mins
            accessor['max'] = maxs

        accessor_index = len(self.accessors)
        self.accessors.append(accessor)
        return accessor_index

    def add_uint_accessor(self, values):
        if values:
            payload = struct.pack('<%sI' % len(values), *[int(v) for v in values])
        else:
            payload = b''
        view_index = self._append_bytes(payload, target=34963)

        accessor = {
            'bufferView': view_index,
            'componentType': 5125,
            'count': len(values),
            'type': 'SCALAR',
        }
        if values:
            accessor['min'] = [int(min(values))]
            accessor['max'] = [int(max(values))]

        accessor_index = len(self.accessors)
        self.accessors.append(accessor)
        return accessor_index

    def add_time_accessor(self, time_keys):
        """Add a SCALAR float accessor for animation TIME input (no buffer target, min/max required)."""
        times = [float(t) for t in time_keys]
        payload = struct.pack('<%sf' % len(times), *times)
        view_index = self._append_bytes(payload, target=None)

        accessor = {
            'bufferView': view_index,
            'componentType': 5126,
            'count': len(times),
            'type': 'SCALAR',
            'min': [min(times)],
            'max': [max(times)],
        }
        accessor_index = len(self.accessors)
        self.accessors.append(accessor)
        return accessor_index


def _identity_matrix4():
    return [[1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _transpose4(matrix):
    return [[float(matrix[r][c]) for r in range(4)] for c in range(4)]


def _mul4(a, b):
    out = []
    for r in range(4):
        row = []
        for c in range(4):
            row.append(sum([float(a[r][k]) * float(b[k][c]) for k in range(4)]))
        out.append(row)
    return out


def _to_matrix4(value):
    if value is None:
        return None
    try:
        rows = []
        for r in range(4):
            rows.append([float(value[r][c]) for c in range(4)])
        return rows
    except Exception:
        return None


def _build_local_matrix(node):
    position = getattr(node, 'position', None)
    scale = getattr(node, 'scale', None)
    orientation = _to_matrix4(getattr(node, 'orientation', None))

    has_transform = bool(position is not None or scale or orientation is not None)
    if not has_transform:
        return None

    translation = _identity_matrix4()
    if position is not None and len(position) >= 3:
        translation[0][3] = float(position[0])
        translation[1][3] = float(position[1])
        translation[2][3] = float(position[2])

    if orientation is not None:
        rotation = _transpose4(orientation)
    else:
        rotation = _identity_matrix4()

    scaling = _identity_matrix4()
    if scale:
        try:
            s = float(scale)
        except Exception:
            s = 1.0
        scaling[0][0] = s
        scaling[1][1] = s
        scaling[2][2] = s

    matrix = _mul4(translation, _mul4(rotation, scaling))
    # glTF matrices are serialized in column-major order.
    return [float(matrix[r][c]) for c in range(4) for r in range(4)]


def _to_vec_rows(values, width):
    if values is None:
        return []
    rows = []
    for value in values:
        try:
            row = [float(value[i]) for i in range(width)]
        except Exception:
            continue
        rows.append(row)
    return rows


def _triangulate_indices(index_lists, mode):
    triangles = []
    for index_list in index_lists or []:
        indices = [int(i) for i in index_list]
        if len(indices) < 3:
            continue

        if mode == GL_TRIANGLE_STRIP:
            for i in range(len(indices) - 2):
                a = indices[i]
                b = indices[i + 1]
                c = indices[i + 2]
                if i % 2:
                    a, b = b, a
                if a != b and b != c and a != c:
                    triangles.extend((a, b, c))
        elif mode == GL_TRIANGLE_FAN:
            anchor = indices[0]
            for i in range(1, len(indices) - 1):
                a = anchor
                b = indices[i]
                c = indices[i + 1]
                if a != b and b != c and a != c:
                    triangles.extend((a, b, c))
        else:
            for i in range(0, len(indices) - 2, 3):
                a = indices[i]
                b = indices[i + 1]
                c = indices[i + 2]
                if a != b and b != c and a != c:
                    triangles.extend((a, b, c))
    return triangles


def _extract_mesh_payload(node, is_renderable_mesh_node, get_node_draw_mode):
    if not is_renderable_mesh_node(node):
        return None

    positions = _to_vec_rows(getattr(node, 'vertices', None), 3)
    if not positions:
        return None

    normals = _to_vec_rows(getattr(node, 'normals', None), 3)
    if len(normals) != len(positions):
        normals = None

    texcoords = _to_vec_rows(getattr(node, 'texture0Vertices', None), 2)
    if len(texcoords) != len(positions):
        texcoords = None

    mode = int(get_node_draw_mode(node))
    indices = _triangulate_indices(getattr(node, 'vertexIndexLists', None), mode)
    if not indices:
        # Last-resort fallback for malformed index lists.
        for i in range(0, len(positions) - 2, 3):
            indices.extend((i, i + 1, i + 2))

    max_index = len(positions) - 1
    filtered = []
    for i in range(0, len(indices), 3):
        a = int(indices[i])
        b = int(indices[i + 1])
        c = int(indices[i + 2])
        if a < 0 or b < 0 or c < 0:
            continue
        if a > max_index or b > max_index or c > max_index:
            continue
        filtered.extend((a, b, c))

    if not filtered:
        return None

    return {
        'positions': positions,
        'normals': normals,
        'texcoords': texcoords,
        'indices': filtered,
    }


def _safe_node_name(node, fallback_index):
    name = getattr(node, 'name', None)
    if not name:
        return 'Node_%d' % int(fallback_index)
    return str(name)


def _safe_filename(name):
    """Return a filesystem-safe version of name (alphanumeric, underscore, hyphen, dot)."""
    cleaned = re.sub(r'[^\w.-]', '_', str(name)).strip('._')
    return cleaned or 'unnamed'


def _get_node_tex_key(node):
    """Return a normalised texture key for slot 0 of the node, or None."""
    resname = getattr(node, 'texture0resname', None) or getattr(node, 'texture0name', None)
    if not resname or str(resname).upper() == 'NULL':
        return None
    key = str(resname).lower()
    for ext in ('.tga', '.dds', '.png', '.txi'):
        if key.endswith(ext):
            key = key[:-len(ext)]
            break
    return key or None


def _collect_textures(root_node):
    """Walk the node tree and return {tex_key: PIL_image} for every unique texture found."""
    textures = {}

    def walk(node):
        for slot in range(4):
            img = getattr(node, 'texture%d' % slot, None)
            if img is None:
                continue
            resname = (getattr(node, 'texture%dresname' % slot, None) or
                       getattr(node, 'texture%dname' % slot, None))
            if not resname or str(resname).upper() == 'NULL':
                continue
            key = str(resname).lower()
            for ext in ('.tga', '.dds', '.png', '.txi'):
                if key.endswith(ext):
                    key = key[:-len(ext)]
                    break
            if key and key not in textures:
                textures[key] = img
        for child in getattr(node, 'children', []) or []:
            walk(child)

    walk(root_node)
    return textures


def _save_texture_png(pil_image, dest_path):
    """Save a PIL Image as PNG, converting colour mode if necessary."""
    img = pil_image
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA')
    img.save(dest_path, format='PNG')


def _ensure_diffuse_material(node, gltf_materials):
    """Add (or reuse) an untextured PBR material driven by the node's diffuseColour."""
    diffuse = getattr(node, 'diffuseColour', None)
    if diffuse is None:
        return None
    try:
        r, g, b = float(diffuse[0]), float(diffuse[1]), float(diffuse[2])
    except Exception:
        return None
    alpha = float(getattr(node, 'alpha', 1.0) or 1.0)
    # Skip near-default grey — not worth creating a material for.
    if abs(r - 0.8) < 0.02 and abs(g - 0.8) < 0.02 and abs(b - 0.8) < 0.02:
        return None
    mat_name = 'diffuse_%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))
    for idx, mat in enumerate(gltf_materials):
        if mat.get('name') == mat_name:
            return idx
    mat_idx = len(gltf_materials)
    gltf_materials.append({
        'name': mat_name,
        'pbrMetallicRoughness': {
            'baseColorFactor': [r, g, b, alpha],
            'metallicFactor': 0.0,
            'roughnessFactor': 0.5,
        },
        'doubleSided': True,
    })
    return mat_idx


def _export_animations(model, node_name_to_index, builder):
    """Build the glTF 'animations' array from all tracks in *model*."""
    gltf_animations = []

    for track_name in sorted(model.getAnimationNames()):
        anim_nodes = model.getAnimationNodes(track_name)
        if not anim_nodes:
            continue

        samplers = []
        channels = []

        for node_name in sorted(anim_nodes.keys()):
            anim_node = anim_nodes[node_name]
            gltf_node_idx = node_name_to_index.get(str(node_name))
            if gltf_node_idx is None:
                continue

            ctrl_map = getattr(anim_node, 'controllers', {})
            if not ctrl_map:
                continue

            # (NWN controller type, glTF target path, expected output component count)
            channel_specs = (
                ('position',    'translation', 3),
                ('orientation', 'rotation',    4),
                ('scale',       'scale',        3),
            )

            for ctrl_type, gltf_path, num_components in channel_specs:
                controllers = ctrl_map.get(ctrl_type, [])
                if not controllers:
                    continue
                controller = controllers[0]

                row_count = controller.getRowCount()
                if row_count <= 0:
                    continue

                try:
                    raw_keys = controller.getTimeKeys()
                    time_keys = [float(raw_keys[i]) for i in range(row_count)]
                except Exception:
                    continue

                value_rows = []
                for i in range(row_count):
                    try:
                        raw_v = controller.getValue(i)
                    except Exception:
                        break
                    if ctrl_type == 'scale':
                        # NWN uses uniform scale scalar; glTF needs VEC3
                        s = float(raw_v[0]) if raw_v else 1.0
                        value_rows.append([s, s, s])
                    elif ctrl_type == 'orientation':
                        # NWN stores quaternion as [x, y, z, w]; glTF also uses [x, y, z, w]
                        if len(raw_v) >= 4:
                            value_rows.append([float(raw_v[j]) for j in range(4)])
                        else:
                            value_rows.append([0.0, 0.0, 0.0, 1.0])
                    else:
                        row = [float(raw_v[j]) for j in range(min(num_components, len(raw_v)))]
                        while len(row) < num_components:
                            row.append(0.0)
                        value_rows.append(row)

                if len(value_rows) != row_count:
                    continue

                accessor_type = 'VEC4' if ctrl_type == 'orientation' else 'VEC3'
                time_acc = builder.add_time_accessor(time_keys)
                val_acc = builder.add_float_accessor(value_rows, accessor_type, animation=True)

                sampler_idx = len(samplers)
                samplers.append({
                    'input': time_acc,
                    'interpolation': 'LINEAR',
                    'output': val_acc,
                })
                channels.append({
                    'sampler': sampler_idx,
                    'target': {
                        'node': gltf_node_idx,
                        'path': gltf_path,
                    },
                })

        if channels:
            gltf_animations.append({
                'name': track_name,
                'samplers': samplers,
                'channels': channels,
            })

    return gltf_animations


def export_model_to_gltf_folder(model, output_dir, model_name,
                                is_renderable_mesh_node, get_node_draw_mode):
    """Export *model* into *output_dir* as a glTF 2.0 asset bundle.

    Files written:
      <output_dir>/<model_name>.gltf   — main glTF manifest
      <output_dir>/textures/*.png      — extracted textures (when present)

    Returns a dict::
        {'gltf_path': str, 'texture_count': int, 'animation_count': int}
    """
    if model is None:
        raise ValueError('No model provided for glTF export')

    root = model.getRootNode()
    if root is None:
        raise ValueError('Model has no root node')

    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Phase 1 — textures                                                   #
    # ------------------------------------------------------------------ #
    raw_textures = _collect_textures(root)
    tex_dir = os.path.join(output_dir, 'textures')
    tex_relative_uris = {}      # {tex_key: 'textures/<safe_name>.png'}

    if raw_textures:
        os.makedirs(tex_dir, exist_ok=True)
        for tex_key, pil_img in raw_textures.items():
            safe_name = _safe_filename(tex_key) + '.png'
            dest = os.path.join(tex_dir, safe_name)
            try:
                _save_texture_png(pil_img, dest)
                tex_relative_uris[tex_key] = 'textures/' + safe_name
            except Exception:
                pass  # skip unwritable textures but continue

    # Build glTF images / textures / samplers / materials arrays
    gltf_samplers = []
    gltf_images = []
    gltf_textures_arr = []
    gltf_materials = []
    tex_key_to_material_idx = {}

    if tex_relative_uris:
        gltf_samplers = [{
            'magFilter': 9729,    # LINEAR
            'minFilter': 9987,    # LINEAR_MIPMAP_LINEAR
            'wrapS': 10497,       # REPEAT
            'wrapT': 10497,       # REPEAT
        }]
        for tex_key, uri in tex_relative_uris.items():
            img_idx = len(gltf_images)
            gltf_images.append({'uri': uri, 'name': tex_key})
            tex_idx = len(gltf_textures_arr)
            gltf_textures_arr.append({'sampler': 0, 'source': img_idx})
            mat_idx = len(gltf_materials)
            gltf_materials.append({
                'name': 'mat_' + tex_key,
                'pbrMetallicRoughness': {
                    'baseColorTexture': {'index': tex_idx},
                    'metallicFactor': 0.0,
                    'roughnessFactor': 0.5,
                },
                'doubleSided': True,
            })
            tex_key_to_material_idx[tex_key] = mat_idx

    # ------------------------------------------------------------------ #
    # Phase 2 — geometry                                                   #
    # ------------------------------------------------------------------ #
    builder = _GLTFBuilder()
    gltf_nodes = []
    gltf_meshes = []
    node_name_to_index = {}

    def collect(node, parent_index=None):
        node_index = len(gltf_nodes)
        node_name = _safe_node_name(node, node_index)
        gltf_node = {'name': node_name}

        orig_name = getattr(node, 'name', None)
        if orig_name:
            node_name_to_index[str(orig_name)] = node_index

        matrix = _build_local_matrix(node)
        if matrix is not None:
            gltf_node['matrix'] = matrix

        mesh_payload = _extract_mesh_payload(node, is_renderable_mesh_node, get_node_draw_mode)
        if mesh_payload is not None:
            pos_acc = builder.add_float_accessor(mesh_payload['positions'],
                                                 'VEC3', include_min_max=True)
            idx_acc = builder.add_uint_accessor(mesh_payload['indices'])
            primitive = {
                'attributes': {'POSITION': pos_acc},
                'indices': idx_acc,
                'mode': 4,
            }
            if mesh_payload['normals'] is not None:
                primitive['attributes']['NORMAL'] = builder.add_float_accessor(
                    mesh_payload['normals'], 'VEC3')
            if mesh_payload['texcoords'] is not None:
                primitive['attributes']['TEXCOORD_0'] = builder.add_float_accessor(
                    mesh_payload['texcoords'], 'VEC2')

            # Wire up material
            tex_key = _get_node_tex_key(node)
            if tex_key and tex_key in tex_key_to_material_idx:
                primitive['material'] = tex_key_to_material_idx[tex_key]
            else:
                mat_idx = _ensure_diffuse_material(node, gltf_materials)
                if mat_idx is not None:
                    primitive['material'] = mat_idx

            mesh_idx = len(gltf_meshes)
            gltf_meshes.append({'name': node_name + '_mesh', 'primitives': [primitive]})
            gltf_node['mesh'] = mesh_idx

        gltf_nodes.append(gltf_node)

        if parent_index is not None:
            parent = gltf_nodes[parent_index]
            if 'children' not in parent:
                parent['children'] = []
            parent['children'].append(node_index)

        for child in getattr(node, 'children', []) or []:
            collect(child, node_index)

        return node_index

    root_index = collect(root)

    if not gltf_meshes:
        raise ValueError('Model does not contain renderable mesh geometry')

    # ------------------------------------------------------------------ #
    # Phase 3 — animations                                                 #
    # ------------------------------------------------------------------ #
    gltf_animations = _export_animations(model, node_name_to_index, builder)

    # ------------------------------------------------------------------ #
    # Phase 4 — assemble and write glTF JSON                              #
    # ------------------------------------------------------------------ #
    payload = bytes(builder.buffer)
    encoded = base64.b64encode(payload).decode('ascii')

    gltf = {
        'asset': {
            'version': '2.0',
            'generator': 'neveredit glTF exporter',
        },
        'scene': 0,
        'scenes': [{'nodes': [root_index]}],
        'nodes': gltf_nodes,
        'meshes': gltf_meshes,
        'accessors': builder.accessors,
        'bufferViews': builder.buffer_views,
        'buffers': [{
            'byteLength': len(payload),
            'uri': 'data:application/octet-stream;base64,' + encoded,
        }],
    }

    if gltf_samplers:
        gltf['samplers'] = gltf_samplers
    if gltf_images:
        gltf['images'] = gltf_images
    if gltf_textures_arr:
        gltf['textures'] = gltf_textures_arr
    if gltf_materials:
        gltf['materials'] = gltf_materials
    if gltf_animations:
        gltf['animations'] = gltf_animations

    safe_name = _safe_filename(model_name or 'model')
    gltf_path = os.path.join(output_dir, safe_name + '.gltf')
    with open(gltf_path, 'w') as handle:
        json.dump(gltf, handle, indent=2)

    return {
        'gltf_path': gltf_path,
        'texture_count': len(tex_relative_uris),
        'animation_count': len(gltf_animations),
    }


# ---------------------------------------------------------------------------
# Legacy single-file entry point (kept for compatibility)
# ---------------------------------------------------------------------------
def export_model_to_gltf(model, output_path, is_renderable_mesh_node, get_node_draw_mode):
    """Export to a single .gltf file (no separate textures).

    Prefer export_model_to_gltf_folder for full asset export.
    """
    out_dir = os.path.dirname(os.path.abspath(output_path))
    basename = os.path.splitext(os.path.basename(output_path))[0]
    result = export_model_to_gltf_folder(model, out_dir, basename,
                                         is_renderable_mesh_node,
                                         get_node_draw_mode)
    return result['gltf_path']
