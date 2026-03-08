import sys,string,math
import copy
import logging

from neveredit.util import Utils
Numeric = Utils.getNumPy()

from neveredit.file.NeverFile import NeverFile
from neveredit.file import BinaryDataHandler

from neveredit.util import neverglobals
from neveredit.openglcontext import utilities
from neveredit.openglcontext import quaternion

dataHandler = BinaryDataHandler.BinaryDataHandler()
logger = logging.getLogger('neveredit.file')


def _read_cstring(raw):
    if isinstance(raw, bytes):
        return raw.split(b'\0', 1)[0].decode('latin1', 'ignore')
    return str(raw).split('\0', 1)[0]

class GeometryHeader:
    def __init__(self):
        self.name = ''
        self.rootNodeOffset = 0
        self.nodeCount = 0
        self.refCount = 0
        self.type = 0

    def fromFile(self,f):
        f.seek(8,1)
        self.name = _read_cstring(f.read(64))
        #print 'name:',self.name
        rootPointer = dataHandler.readUIntFile(f)
        self.rootNodeOffset = MDLFile.modelPointerToOffset(rootPointer)
        self.nodeCount = dataHandler.readUIntFile(f)
        f.seek(24,1)
        self.refCount = dataHandler.readUIntFile(f)
        self.type = dataHandler.readUByteFile(f)
        f.seek(3,1)

class Controller:
    types = {'position':8,
             'orientation':20,
             'scale':36,
             'color':76,
             'radius':88,
             'shadowradius':96,
             'verticaldisplacement':100,
             'multiplier':140,
             'alphaend':80,
             'alphastart':84,
             'birthrate':88,
             'bounce_co':92,
             'colorend':96,
             'colorstart':108,
             'combinetime':120,
             'drag':124,
             'fps':128,
             'frameend':132,
             'framestart':136,
             'grav':140,
             'lifeexp':144,
             'mass':148,
             'p2p_bezier2':152,
             'p2p_bezier3':156,
             'particlerot':160,
             'randvel':164,
             'sizestart':168,
             'sizeend':172,
             'sizestart_y':176,
             'sizeend_y':180,
             'spread':184,
             'threshold':188,
             'velocity':192,
             'xsize':196,
             'ysize':200,
             'blurlength':204,
             'lightningdelay':208,
             'lightningradius':212,
             'lightningscale':216,
             'detonate':228,
             'alphamid':464,
             'colormid':468,
             'percentstart':480,
             'percentmid':481,
             'percentend':482,
             'sizemid':484,
             'sizemid_y':488,
             'selfillumcolor':100,
             'alpha':128
             }
    numTypes = dict(zip(list(types.values()),list(types.keys())))
     
    def __init__(self):
        self.data = []
        self.keys = []
        self.type = ''
        self.numColumns = 0
        self.numRows = 0
        self.firstTimeIndex = 0
        self.firstDataIndex = 0
        self.rotationMatrix = []
        
    def fromFile(self,f,controllerData):
        self.headerFromFile(f)
        self.grabData(controllerData)
        if self.type == 'orientation':
            quat = list(self.getValue())
            quat.insert(0,quat.pop())
            q = quaternion.Quaternion(quat)
            self.rotationMatrix = q.matrix()
            
    def headerFromFile(self,f):
        t = dataHandler.readUIntFile(f)
        try:
            self.type = Controller.numTypes[t]
        except KeyError:
            print('warning, unknown node controller type',t)            
        self.numRows = dataHandler.readUWordFile(f)
        self.firstTimeIndex = dataHandler.readUWordFile(f)
        self.firstDataIndex = dataHandler.readUWordFile(f)
        self.numColumns = dataHandler.readUByteFile(f)
        f.seek(1,1)
        
    def grabData(self,data):
        end = self.firstDataIndex + self.numRows * self.numColumns
        self.data = data[self.firstDataIndex:end]                         
        self.keys = data[end:end+self.numRows]

    def getTimeKeys(self):
        return self.keys

    def getValue(self,i=0):
        return self.data[self.numColumns*i:self.numColumns*i+self.numColumns+1]
    
    def typeAsString(self):
        return self.type
    
class Node:
    indent = 0
    def __init__(self):
        self.texture0 = None
        self.texture1 = None
        self.texture2 = None
        self.texture3 = None
        self.texture0resname = None
        self.texture1resname = None
        self.texture2resname = None
        self.texture3resname = None
        self.flags = 0
        self.name = ''
        self.children = []
        self.controllers = {}
        self.alpha = 1.0
        self.normals = []
        self.position = None
        self.scale = None
        self.orientation = None
        self.boundingBox = Numeric.array([3*[0.0],3*[0.0]])
        self.shininess = None
        self.ambientColour = None
        self.diffuseColour = None
        self.specularColour = None
        self.faces = None
        self.vertexIndexLists = None
        self.inheritColour = None
        self.nodeNumber = None
        self.tm = None
        self.indicesFromFaces = False
        
        self.parentGeomPointer = None
        self.parentNodePointer = None
        self.childrenArray = None
        self.controllerKeysArray = None
        self.controllerVArray = None
        self.skinRawData = None
        self.skinUInts = None
        self.skinMeta = {}
        self.skinWeights = None
        self.skinBoneIds = None
        
    def getName(self):
        return self.name
    
    def fromFile(self,mdlFile,offset):
        f = mdlFile.file
        f.seek(offset)
        self.headerFromFile(mdlFile)
        if self.hasMesh():
            self.meshHeaderFromFile(mdlFile)
        if self.hasSkin():
            self.skinHeaderFromFile(mdlFile)
        self.readChildren(mdlFile)
        self.readControllers(f)
            
    def headerFromFile(self,mdlFile):
        f = mdlFile.file
        f.seek(24,1)
        self.inheritColour = dataHandler.readUIntFile(f)
        self.nodeNumber = dataHandler.readUIntFile(f)
        self.name = _read_cstring(f.read(32))
        self.parentGeomPointer = dataHandler.readUIntFile(f)
        self.parentNodePointer = dataHandler.readUIntFile(f)
        self.childrenArray = MDLFile.arrayFromFile(f)
        self.controllerKeysArray = MDLFile.arrayFromFile(f)
        self.controllerVArray = MDLFile.arrayFromFile(f)
        self.flags = dataHandler.readUIntFile(f)
        self.cacheTrimeshType()

    def cacheTrimeshType(self):
        self.tm = self.flags == 0x21 #cache
        
    def readChildren(self,mdlFile):
        f = mdlFile.file
        f.seek(self.childrenArray.offset)
        childOffsets = dataHandler.readUIntsFile(f,self.childrenArray.size)
        childOffsets = [MDLFile.modelPointerToOffset(p) for p in childOffsets]
        self.children = []
        Node.indent += 4
        for o in childOffsets:
            n = Node()
            n.fromFile(mdlFile,o)
            self.children.append(n)
        Node.indent -= 4
        self.childrenArray = None

    def readControllers(self,f):
        f.seek(self.controllerVArray.offset)
        controllerData = dataHandler.readFloatsFile(f,
                                                    self.controllerVArray.size)
        f.seek(self.controllerKeysArray.offset)
        self.controllers = {}
        for i in range(self.controllerKeysArray.size):
            c = Controller()
            c.fromFile(f,controllerData)
            self.addController(c)
        if self.hasMesh():
            self.ambientColour += [self.alpha]
            self.diffuseColour += [self.alpha]
            self.specularColour += [self.alpha]

    def addController(self,c):
        ctype = c.typeAsString()
        if ctype not in self.controllers:
            self.controllers[ctype] = [c]
        else:
            self.controllers[ctype].append(c)
        if ctype == 'alpha':
            self.alpha = c.getValue(0)[0]
        elif ctype == 'position':
            self.position = c.getValue()
        elif ctype == 'orientation':
            self.orientation = c.rotationMatrix
        elif ctype == 'scale':
            self.scale = c.getValue()[0]
            
    def hasController(self,ctype):
        return ctype in self.controllers
    
    def getControllers(self,ctype):
        return self.controllers.get(ctype,[])
    
    def controllersAsString(self):
        strings = []
        for cl in list(self.controllers.values()):
            for c in cl:
                strings.append(c.typeAsString())
        return '-'.join(strings)
    
    def printNodeStructure(self):
        print(self.nodeStructureAsString())

    def nodeStructureAsString(self):
        strings = []        
        self.nodeStructureAsStringHelper(strings)
        return '\n'.join(strings)
    
    def nodeStructureAsStringHelper(self,strings):
        strings.append((Node.indent*' ') + '"' + self.name
                       + '" ' + self.typeAsString()\
                       + ' (' + self.controllersAsString() + ')')
        Node.indent += 4
        for c in self.children:
            c.nodeStructureAsStringHelper(strings)
        Node.indent -= 4
        
    def meshHeaderFromFile(self,mdlFile):
        f = mdlFile.file
        f.seek(8,1)
        self.faceArray = MDLFile.arrayFromFile(f)
        values = dataHandler.readFromFile('<ffffffffffffffffffffIIII',f)        
        self.boundingBox = Numeric.array([values[0:3],values[3:6]])
        self.alpha = 1.0 #changeable via controller
        self.radius = values[6]
        self.centreOfMass = values[7:10]
        self.diffuseColour = list(values[10:13])
        self.ambientColour = list(values[13:16])
        self.specularColour = list(values[16:19])
        (self.shininess,
         self.shadowFlag,
         self.beamingFlag,
         self.renderFlag,
         self.transparencyHint) = values[19:24]
        f.seek(4,1)
        self.texture0name = _read_cstring(f.read(64))
        r = neverglobals.getResourceManager()
        if self.texture0name and self.texture0name != 'NULL':
            self.texture0, self.texture0resname = self._resolveTextureResource(r, self.texture0name)
        self.texture1name = _read_cstring(f.read(64))
        if self.texture1name and self.texture1name != 'NULL':
            self.texture1, self.texture1resname = self._resolveTextureResource(r, self.texture1name)
        self.texture2name = _read_cstring(f.read(64))
        if self.texture2name and self.texture2name != 'NULL':
            self.texture2, self.texture2resname = self._resolveTextureResource(r, self.texture2name)
        self.texture3name = _read_cstring(f.read(64))
        if self.texture3name and self.texture3name != 'NULL':
            self.texture3, self.texture3resname = self._resolveTextureResource(r, self.texture3name)
        self.tileFade = dataHandler.readUIntFile(f)
        f.seek(24,1)
        self.vertexIndexCountArray = MDLFile.arrayFromFile(f)
        self.rawVertexOffsetArray = MDLFile.arrayFromFile(f)
        f.seek(8,1)
        self.triangleMode = dataHandler.readUByteFile(f)
        f.seek(7,1)
        self.vertexDataRawPointer = dataHandler.readUIntFile(f)
        self.vertexCount = dataHandler.readUWordFile(f)
        self.textureCount = dataHandler.readUWordFile(f)
        self.texture0VertexDataPointer = dataHandler.readUIntFile(f)
        self.texture1VertexDataPointer = dataHandler.readUIntFile(f)
        self.texture2VertexDataPointer = dataHandler.readUIntFile(f)
        self.texture3VertexDataPointer = dataHandler.readUIntFile(f)
        self.vertexNormalDataPointer = dataHandler.readUIntFile(f)
        mesh_struct_end = f.tell()
        
        self.processMeshData(mdlFile)
        # Restore stream to end of mesh struct so contiguous optional blocks
        # (skin/anim/dangly/aabb) can be parsed in-order from node data.
        f.seek(mesh_struct_end)

    def skinHeaderFromFile(self, mdlFile):
        f = mdlFile.file
        # NWN skin extension block is a fixed 0x64 bytes in binary node data.
        raw = f.read(0x64)
        if len(raw) != 0x64:
            self.skinRawData = None
            self.skinUInts = None
            return
        self.skinRawData = raw
        self.skinUInts = dataHandler.readFromBuf('<25I', raw)
        self.skinMeta = {}
        self._extractSkinArrays(mdlFile)

    def _readRawFloats(self, mdlFile, pointer, count):
        if pointer in (None, 0xFFFFFFFF) or count <= 0:
            return None
        try:
            offset = mdlFile.rawDataOffset + int(pointer) + 0xC
            end = offset + (4 * int(count))
            raw_limit = mdlFile.rawDataOffset + mdlFile.rawDataSize + 0xC
            if offset < mdlFile.rawDataOffset or end > raw_limit:
                return None
            f = mdlFile.file
            current = f.tell()
            try:
                f.seek(offset)
                vals = dataHandler.readFloatsFile(f, int(count))
            finally:
                f.seek(current)
            return Numeric.array(vals, 'f')
        except Exception:
            return None

    def _extractSkinArrays(self, mdlFile):
        # Heuristic extraction only: we keep this conservative and optional.
        # Full semantic decoding of the skin block can be layered later.
        if self.skinUInts is None or self.vertexCount <= 0:
            return

        vertex4 = int(self.vertexCount) * 4
        candidates = []
        vals = self.skinUInts
        self.skinMeta['raw_uints'] = [int(v) for v in vals]
        for i in range(len(vals) - 1):
            ptr = int(vals[i])
            cnt = int(vals[i + 1])
            if ptr == 0xFFFFFFFF:
                continue
            if cnt <= 0 or cnt > vertex4:
                continue
            arr = self._readRawFloats(mdlFile, ptr, cnt)
            if arr is None:
                continue
            candidates.append((i, ptr, cnt, arr))

        self.skinMeta['candidate_pairs'] = [
            {'pair_index': int(i), 'pointer': int(ptr), 'count': int(cnt)}
            for (i, ptr, cnt, arr) in candidates
        ]

        if not candidates:
            return

        weight_candidate = None
        bone_candidate = None

        for i, ptr, cnt, arr in candidates:
            if cnt != vertex4:
                continue

            # Likely weights: mostly in [0,1], grouped sums near 1.
            in_range = Numeric.logical_and(arr >= -0.001, arr <= 1.001)
            ratio_in_range = float(Numeric.add.reduce(in_range.astype('f'))) / float(len(arr))
            grouped = Numeric.reshape(arr, (int(self.vertexCount), 4))
            sums = Numeric.add.reduce(grouped, 1)
            mean_sum = float(Numeric.add.reduce(sums)) / float(len(sums))
            if ratio_in_range > 0.90 and 0.4 <= mean_sum <= 1.6:
                weight_candidate = grouped
                self.skinMeta['weights_pair_index'] = int(i)
                continue

            # Likely bone ids: mostly integral, non-negative, reasonably small.
            rounded = Numeric.floor(arr + 0.5)
            int_like = Numeric.absolute(arr - rounded) < 0.001
            ratio_int = float(Numeric.add.reduce(int_like.astype('f'))) / float(len(arr))
            max_val = float(arr.max()) if len(arr) else 0.0
            min_val = float(arr.min()) if len(arr) else 0.0
            if ratio_int > 0.95 and min_val >= -0.001 and max_val < 512.0:
                bone_candidate = Numeric.reshape(rounded, (int(self.vertexCount), 4)).astype('i')
                self.skinMeta['bone_ids_pair_index'] = int(i)

        if weight_candidate is not None:
            self.skinWeights = weight_candidate
            self.skinMeta['weights_shape'] = (int(self.skinWeights.shape[0]), int(self.skinWeights.shape[1]))
        if bone_candidate is not None:
            self.skinBoneIds = bone_candidate
            self.skinMeta['bone_ids_shape'] = (int(self.skinBoneIds.shape[0]), int(self.skinBoneIds.shape[1]))

        if self.hasSkin():
            logger.debug(
                'skin node "%s": vtx=%d candidates=%d weights=%s bones=%s',
                self.name,
                int(self.vertexCount),
                len(self.skinMeta.get('candidate_pairs', [])),
                bool(self.skinWeights is not None),
                bool(self.skinBoneIds is not None),
            )

    def processMeshData(self,mdlFile):
        f = mdlFile.file
        if self.vertexDataRawPointer != 0xFFFFFFFF:
            f.seek(mdlFile.rawDataOffset + self.vertexDataRawPointer + 0xC)
            b = f.read(self.vertexCount*12)
            self.vertices = Numeric.array([dataHandler.readFloatsBuf(b[i*12:(i+1)*12],3)
                             for i in range(self.vertexCount)],'f')
        else:
            self.vertices = []
        if self.vertexNormalDataPointer != 0xFFFFFFFF:
            f.seek(mdlFile.rawDataOffset + self.vertexNormalDataPointer + 0xC)
            self.normals = Numeric.array([dataHandler.readFloatsFile(f,3)
                            for i in range(self.vertexCount)],'f')
        else:
            self.normals = []
        if self.texture0VertexDataPointer != 0xFFFFFFFF:
            f.seek(mdlFile.rawDataOffset + self.texture0VertexDataPointer + 0xC)
            self.texture0Vertices = Numeric.array([dataHandler.readFloatsFile(f,2)
                                     for i in range(self.vertexCount)],'f')
        else:
            self.texture0Vertices = []
        if self.texture1VertexDataPointer != 0xFFFFFFFF:
            f.seek(mdlFile.rawDataOffset + self.texture1VertexDataPointer + 0xC)
            self.texture1Vertices = Numeric.array([dataHandler.readFloatsFile(f,2)
                                     for i in range(self.vertexCount)],'f')
        else:
            self.texture1Vertices = []
        self.vertexIndexLists = []
        f.seek(self.rawVertexOffsetArray.offset)
        pointers = [dataHandler.readUIntFile(f) for i
                    in range(self.rawVertexOffsetArray.size)]
        f.seek(self.vertexIndexCountArray.offset)        
        lengths = [dataHandler.readUIntFile(f) for i
                   in range(self.vertexIndexCountArray.size)]
        for p,l in zip(pointers,lengths):
            offset = mdlFile.rawDataOffset + p + 0xC
            f.seek(offset)
            self.vertexIndexLists.append(dataHandler.readUWordsFile(f,l))

        # Skin/anim mesh variants can carry index buffers in layouts that don't
        # match the simple raw-vertex-offset interpretation above. If the parsed
        # indices are invalid, rebuild topology from the face array instead.
        if (not self._indexListsValid()) or (self.hasSkin() and self.faceArray and self.faceArray.size):
            rebuilt = self._buildIndexListsFromFaceArray(mdlFile)
            if rebuilt:
                self.vertexIndexLists = rebuilt
                self.indicesFromFaces = True

        if self._shouldRebuildNormals():
            rebuilt_normals = self._buildVertexNormalsFromFaceArray(mdlFile)
            if rebuilt_normals is not None:
                self.normals = rebuilt_normals
        #print 'vertexIndexList for node',self.name,self.vertexIndexLists

    def _resolveTextureResource(self, resourceManager, texture_name):
        if not texture_name:
            return (None, None)
        base = texture_name.lower()
        for ext in ('tga', 'dds', 'plt'):
            resname = base + '.' + ext
            tex = resourceManager.getResourceByName(resname)
            if tex is not None:
                return (tex, resname)
        return (None, None)

    def _shouldRebuildNormals(self):
        if self.vertexCount <= 0:
            return False
        if self.normals is None or len(self.normals) != self.vertexCount:
            return True
        # Skin meshes often carry normals that don't line up with interpreted
        # topology in this legacy loader; prefer rebuilt normals for consistency.
        if self.hasSkin():
            return True
        return False

    def _buildVertexNormalsFromFaceArray(self, mdlFile):
        if not self.faceArray or self.faceArray.size <= 0:
            return None
        if self.vertices is None or len(self.vertices) != self.vertexCount:
            return None

        f = mdlFile.file
        current_pos = f.tell()
        try:
            f.seek(self.faceArray.offset)
            accum = Numeric.zeros((self.vertexCount, 3), 'f')
            counts = Numeric.zeros((self.vertexCount,), 'f')

            for i in range(self.faceArray.size):
                vals = dataHandler.readFromFile('<ffffIhhhHHH', f)
                tri = (int(vals[8]), int(vals[9]), int(vals[10]))
                if tri[0] >= self.vertexCount or tri[1] >= self.vertexCount or tri[2] >= self.vertexCount:
                    continue

                # Prefer geometric normal from triangle vertices. If degenerate,
                # fall back to the stored face normal from the face record.
                v0 = self.vertices[tri[0]]
                v1 = self.vertices[tri[1]]
                v2 = self.vertices[tri[2]]
                edge1 = v1 - v0
                edge2 = v2 - v0
                fn = Numeric.array(utilities.crossProduct(edge1, edge2), 'f')
                mag2 = Numeric.dot(fn, fn)
                if mag2 <= 1.0e-10:
                    fn = Numeric.array([vals[0], vals[1], vals[2]], 'f')
                    mag2 = Numeric.dot(fn, fn)
                    if mag2 <= 1.0e-10:
                        continue
                fn = fn / math.sqrt(mag2)

                for idx in tri:
                    accum[idx] += fn
                    counts[idx] += 1.0

            for idx in range(self.vertexCount):
                if counts[idx] > 0.0:
                    n = accum[idx]
                    mag2 = Numeric.dot(n, n)
                    if mag2 > 1.0e-10:
                        accum[idx] = n / math.sqrt(mag2)
                    else:
                        accum[idx] = Numeric.array([0.0, 0.0, 1.0], 'f')
                else:
                    accum[idx] = Numeric.array([0.0, 0.0, 1.0], 'f')

            return accum
        except Exception:
            return None
        finally:
            f.seek(current_pos)

    def _indexListsValid(self):
        if not self.vertexIndexLists:
            return False
        if self.vertexCount <= 0:
            return False
        saw_index = False
        for index_list in self.vertexIndexLists:
            if not index_list:
                continue
            saw_index = True
            for idx in index_list:
                if idx < 0 or idx >= self.vertexCount:
                    return False
        return saw_index

    def _buildIndexListsFromFaceArray(self, mdlFile):
        if not self.faceArray or self.faceArray.size <= 0:
            return None

        f = mdlFile.file
        # Preserve caller's file position.
        current_pos = f.tell()
        try:
            f.seek(self.faceArray.offset)
            faces = []
            for i in range(self.faceArray.size):
                # NWN binary face layout (32 bytes):
                # 3x float normal, 1x float plane distance,
                # 1x uint32 smoothing group,
                # 3x int16 adjacent faces,
                # 3x uint16 vertex indices.
                vals = dataHandler.readFromFile('<ffffIhhhHHH', f)
                tri = (int(vals[8]), int(vals[9]), int(vals[10]))
                if tri[0] < self.vertexCount and tri[1] < self.vertexCount and tri[2] < self.vertexCount:
                    faces.extend(tri)
            if faces:
                return [tuple(faces)]
            return None
        except Exception:
            return None
        finally:
            f.seek(current_pos)

    def maxBoundingBox(self,nodelist):
        self.boundingBox = Numeric.array([3*[float(sys.maxsize)],3*[-float(sys.maxsize)]])
        for n in nodelist:
            for i in range(3):
                if n.boundingBox[0][i] < self.boundingBox[0][i]:
                    self.boundingBox[0][i] = n.boundingBox[0][i]
                if n.boundingBox[1][i] > self.boundingBox[1][i]:
                    self.boundingBox[1][i] = n.boundingBox[1][i]
                    
    def recalculateBoundingBox(self):
        mesh_with_vertices = self.hasMesh() and \
            (not self.isAABBMesh()) and \
            self.vertices is not None and len(self.vertices) > 0
        if not mesh_with_vertices:
            self.maxBoundingBox(self.children)
        else:
            self.boundingBox = Numeric.array([3*[float(sys.maxsize)],3*[-float(sys.maxsize)]])
            for v in self.vertices:
                for i in range(3):
                    if v[i] < self.boundingBox[0][i]:
                        self.boundingBox[0][i] = v[i]
                    if v[i] > self.boundingBox[1][i]:
                        self.boundingBox[1][i] = v[i]
        self.boundingSphere = [[0,0,0],0]
        self.boundingSphere[0] = (self.boundingBox[1] + self.boundingBox[0])/2.0
        r = self.boundingBox[0] - self.boundingSphere[0]
        r = Numeric.dot(r,r)
        self.boundingSphere[1] = math.sqrt(r)
        
    def isDummy(self):
        return self.flags == 0x1

    def isLight(self):
        return self.flags == 0x3

    def isEmitter(self):
        return self.flags == 0x5

    def isReference(self):
        return self.flags == 0x11

    def isTriMesh(self):
        return self.tm

    def isSkinMesh(self):
        return self.flags == 0x61

    def isAnimMesh(self):
        return self.flags == 0xA1

    def isDanglyMesh(self):
        return self.flags == 0x121

    def isAABBMesh(self):
        return self.flags == 0x221

    def hasAnim(self):
        return self.flags & 0x80
    
    def hasMesh(self):        
        return self.flags & 0x20

    def hasDangly(self):
        return self.flags & 0x120

    def hasSkin(self):
        return self.flags & 0x40
    
    def typeAsString(self):
        sl = []
        if self.isDummy():
            sl.append("Dummy")
        if self.isLight():
            sl.append("Light")
        if self.isEmitter():
            sl.append("Emitter")
        if self.isReference():
            sl.append("Reference")
        if self.isTriMesh():
            sl.append("Tri")
        if self.isSkinMesh():
            sl.append("Skin")
        if self.isAnimMesh():
            sl.append("Anim")
        if self.isDanglyMesh():
            sl.append("Dangly")
        if self.isAABBMesh():
            sl.append("AABB")
        if self.hasMesh():
            sl.append("Mesh")
        return '-'.join(sl)

class Model:
    def __init__(self):
        self.classification = "Unknown"
        self.rootNode = None
        self.boundingBox = Numeric.array([[0.0,0.0,0.0],[1.0,1.0,1.0]])
        self.validBoundingBox = False
        self.animScale = 1.0
        self.nodeCount = 0
        self.preprocessed = False

    def getName(self):
        root = self.getRootNode()
        if root is None:
            return '<unnamed model>'
        return root.getName()
    
    def getRootNode(self):
        return self.rootNode

    def recalculateBoundingBoxes(self):
        root = self.getRootNode()
        if root is None:
            self.validBoundingBox = False
            return
        self.recalculateBoundingBoxHelper(root)
        
    def recalculateBoundingBoxHelper(self,node):
        if node is None:
            return
        node.recalculateBoundingBox()
        for n in node.children:
            self.recalculateBoundingBoxHelper(n)

    def setPreprocessed(self,p):
        self.preprocessed = p

    def getPreprocessed(self):
        return self.preprocessed
    
    def __str__(self):
        strings = []
        strings.append("class: " + self.classification)
        strings.append('bbox: ' + repr(self.boundingBox))
        strings.append('animScale: ' + repr(self.animScale))
        if self.rootNode:
            strings.append(self.rootNode.nodeStructureAsString())
        return '\n'.join(strings)
    
    def __repr__(self):
        return self.__str__()

class MDLArray:
    def __init__(self,offset,size,entriesAlloc):        
        self.offset = offset
        self.size = size
        self.entriesAllocated = entriesAlloc
        
class MDLFile(NeverFile):
    def __init__(self):
        NeverFile.__init__(self)
        self.rawDataOffset = 0
        self.rawDataSize = 0
        self.totalSize = 0
        self.model = Model()
        
    def arrayFromFile(f):
        a = MDLArray(offset=MDLFile.modelPointerToOffset(dataHandler.readUIntFile(f)),
                     size=dataHandler.readUIntFile(f),
                     entriesAlloc = dataHandler.readUIntFile(f))
        return a

    arrayFromFile = staticmethod(arrayFromFile)

    def rawArrayFromFile(self,f):
        class Array:
            pass
        a = Array()
        a.offset = self.rawDataOffset + dataHandler.readUIntFile(f) + 0xC
        a.size = dataHandler.readUIntFile(f)
        a.entriesAllocated = dataHandler.readUIntFile(f)
        return a

    def headerFromFile(self,f):
        self.rawDataOffset = dataHandler.readUIntFile(f)
        self.rawDataSize = dataHandler.readUIntFile(f)

    def geometryHeaderFromFile(self,f):
        gh = GeometryHeader()
        gh.fromFile(f)
        return gh

    def modelHeaderFromFile(self,f):
        self.mdlGeometryHeader = self.geometryHeaderFromFile(f)
        f.seek(2,1)
        classification = dataHandler.readUByteFile(f)
        if classification == 0x01:
            self.model.classification = "Effect"
        elif classification == 0x02:
            self.model.classification = "Tile"
        elif classification == 0x04:
            self.model.classification = "Character"
        elif classification == 0x08:
            self.model.classification = "Door"
        else:
            #print "unknown model classification:",classification
            self.model.classification = "None"
            # this seems to include waypoint models 
            # - probably whenever no model displayed in-game
        self.model.fogged = dataHandler.readUByteFile(f)
        f.seek(4,1)
        self.animationHeaderPointers = self.arrayFromFile(f)
        self.parentPointer = dataHandler.readUIntFile(f)
        self.model.boundingBox = Numeric.array([dataHandler.readFloatsFile(f,3),
                                                dataHandler.readFloatsFile(f,3)])
        self.model.radius = dataHandler.readFloatFile(f)
        self.model.animScale = dataHandler.readFloatFile(f)
        self.superModelName = _read_cstring(f.read(64))
        #print 'supermodel:',self.superModelName

    def nodeFromFile(self,pointer):
        n = Node()
        n.fromFile(self,pointer)
        return n

    def modelPointerToOffset(p):
        return p + 0xC
    modelPointerToOffset = staticmethod(modelPointerToOffset)
    
    def fromFile(self,f):
        self.file = f
        firstVal = dataHandler.readUIntFile(f)
        if firstVal == 0:
            self.headerFromFile(f)
            self.modelHeaderFromFile(f)
            #print self.mdlGeometryHeader.nodeCount,'nodes'
            self.model.nodeCount = self.mdlGeometryHeader.nodeCount
            self.model.rootNode = self.nodeFromFile(self.mdlGeometryHeader.rootNodeOffset)
            #print self.model
        else:
            self.readASCIIModel(f)
        self.model.recalculateBoundingBoxes()
#        print 'recalculated bounding box for',self.model.rootNode.name,self.model.boundingBox

    def readASCIIModel(self,f):
        line = f.readline()
        nodes = {}
        firstNode = True
        while line:
            parts = line.split()
            if not parts:
                line = f.readline()
                continue
            if parts[0] == 'classification':
                self.model.classification = parts[1]
            elif parts[0] == 'node':
                n = self.readASCIINode(parts[1],parts[2],nodes,f)
                self.model.nodeCount += 1
                if firstNode:
                    self.model.rootNode = n
                    firstNode = False
                nodes[n.name] = n
            elif parts[0] == 'newmodel':
                self.name = parts[1]
            line = f.readline()

    def readASCIINode(self,type,name,nodes,f):
        n = Node()
        if type == 'dummy':
            n.flags |= 0x1
        elif type == 'reference':
            n.flags |= 0x11
        elif type == 'trimesh':
            n.flags |= 0x21
        elif type == 'light':
            n.flags |= 0x3
        elif type == 'emitter':
            n.flags |= 0x5
        elif type == 'skinmesh':
            n.flags |= 0x61
        elif type == 'animmesh':
            n.flags |= 0xa1
        elif type == 'danglymesh':
            n.flags |= 0x121
        elif type == 'aabb':
            n.flags |= 0x221
        else:
            print('Unknown node type:',type)
        n.cacheTrimeshType()
        
        n.name = name
        n.faces = None
        
        parts = f.readline().split()
        while parts[0] != 'endnode':
            if parts[0] == 'parent':
                if parts[1] in nodes:
                    nodes[parts[1]].children.append(n)
                elif parts[1] != 'NULL':
                    print('cannot find parent node for',n.name,':',parts[1])
            elif parts[0] == 'ambient':
                n.ambientColour = [float(parts[1]),float(parts[2]),
                                   float(parts[3])]
            elif parts[0] == 'diffuse':
                n.diffuseColour = [float(parts[1]),float(parts[2]),
                                   float(parts[3])]
            elif parts[0] == 'specular':
                n.specularColour = [float(parts[1]),float(parts[2]),
                                   float(parts[3])]
            elif parts[0] == 'shininess':
                n.shininess = float(parts[1])
            elif parts[0] == 'bitmap':
                n.texture0name = parts[1]
                if n.texture0name != 'NULL':
                    r = neverglobals.getResourceManager()
                    n.texture0, n.texture0resname = n._resolveTextureResource(r, n.texture0name)

            elif parts[0] in Controller.types:
                c = Controller()
                c.type = parts[0]
                if parts[0] == 'position':
                    c.numColumns = 3
                    c.data = [float(parts[1]),float(parts[2]),float(parts[3])]
                elif parts[0] == 'alpha':
                    c.numColumns = 1
                    c.data = [float(parts[1])]
                elif parts[0] == 'orientation':
                    c.numColumns = 4
                    c.data = [float(parts[1]),float(parts[2]),
                              float(parts[3]),float(parts[4])]
                    if c.data[0] == c.data[1] == c.data[2] == c.data[3] == 0.0:
                        #this is strange. in ASCII models they seem to specify
                        #quaternions with elements all 0?
                        c.data[3] = 1.0
                    quat = copy.copy(c.data)
                    quat.insert(0,quat.pop())
                    q = quaternion.Quaternion(quat)
                    c.rotationMatrix = q.matrix()
                elif parts[0] == 'scale':
                    c.numColumns = 1
                    c.data = [float(parts[1])]
                n.addController(c)
            elif parts[0] == 'verts':
                num = int(parts[1])
                n.vertices = []
                for i in range(num):
                    n.vertices.append(Numeric.array([float(val)
                                                     for val
                                                     in f.readline().split()]))
                n.vertices = Numeric.array(n.vertices,'d')
            elif parts[0] == 'faces':
                num = int(parts[1])
                n.faces = []
                for i in range(num):
                    face = [int(val)
                         for val in f.readline().split()]
                    n.faces.append([face[:3],face[3],face[4:7],face[7]])
            elif parts[0] == 'tverts':
                num = int(parts[1])
                n.texture0Vertices = []
                for i in range(num):
                    n.texture0Vertices.append([float(val)
                                               for val
                                               in f.readline().split()][:2])
                n.texture0Vertices = Numeric.array(n.texture0Vertices,'f')
            parts = f.readline().split()
        if n.faces:
            n.vertexIndexLists = [[]]
            n.normals = []
            for f in n.faces:
                points = [n.vertices[i] for i in f[0]]
                n.vertexIndexLists[0].extend(f[0])
                #tpoints = [n.texture0Vertices[i] for i in f[2]]
                normal = Numeric.array(utilities.crossProduct(points[2]
                                                              -points[1],
                                                              points[0]
                                                              -points[1]))
                normal /= math.sqrt(Numeric.dot(normal,normal))
                n.normals.append(normal)
                
                
        return n
        
    def getModel(self):
        return self.model
    
if __name__ == '__main__':
    
    mdl = MDLFile()
    f = open(sys.argv[1],'rb')
    mdl.fromFile(f)
    
