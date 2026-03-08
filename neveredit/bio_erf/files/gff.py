import io
from collections import deque
from nwn.data.field import Field
from nwn.common.bytes import copy_buf
from nwn.common.util import eprint, HandlesList

class GFFFile(HandlesList):
	version = 'V3.2'
	file_type = 'GFF '

	def __init__(self):
		self._clear()
		self._root = None
		self._data_stale = False
	def _clear(self):
		self.labels = self.LabelMap()
		self.structs = deque()
		self.fields = self.FieldsList()
		self.lists = io.BytesIO()
		with self:
			pass # Clear contexts and start over
		self.handles = [self.fields, self.lists]

	@classmethod
	def from_file(cls, f_in):
		inst = cls()
		inst.header = h = inst.Header(inst.file_type, inst.version)
		for h2 in h:
			h2.value = h2._read(f_in)

		inst.file_type = h.file_type.value.strip()
		inst.version = h.version.value
		f_in.seek(h.structs.offset.value) # Read structs
		for i in range(h.structs.count.value):
			inst.structs.append(cls.StructHeader.from_file(f_in))
		f_in.seek(h.fields.offset.value) # Read fields
		for i in range(h.fields.count.value):
			inst.fields.append(cls.FieldHeader.from_file(f_in))
		f_in.seek(h.labels.offset.value) # Read labels
		for i in range(h.labels.count.value):
			rref = Field.CResRef.from_data(f_in)
			inst.labels.add(rref.value)
		inst.fields.data_cache = [None] * h.fields.count.value
		f_in.seek(h.fields.data.offset.value) # Read field data
		copy_buf(f_in, inst.fields.data, h.fields.data.count.value)
		f_in.seek(h.fields.indices.offset.value) # Read field indices
		copy_buf(f_in, inst.fields.indices, h.fields.indices.count.value)
		f_in.seek(h.lists.offset.value) # Read lists
		copy_buf(f_in, inst.lists, h.lists.count.value)
		inst._data_stale = False
		h.verify()
		return inst

	def write_to(self, f_out):
		self.header = h = self.Header(self.file_type.ljust(4), self.version)

		if self._data_stale:
			self._clear()
			self.root.to_gff_data(self)

		h.structs.offset.value = h.size
		h.structs.count.value = len(self.structs)
		h.fields.offset.value = (h.structs.offset.value + (self.StructHeader.size * h.structs.count.value))
		h.fields.count.value = len(self.fields)
		h.labels.offset.value = (h.fields.offset.value + (self.FieldHeader.size * h.fields.count.value))
		h.labels.count.value = len(self.labels)
		h.fields.data.offset.value = (h.labels.offset.value + (Field.CResRef().size * h.labels.count.value))
		h.fields.data.count.value = self.fields.data.tell()
		h.fields.indices.offset.value = (h.fields.data.offset.value + h.fields.data.count.value)
		h.fields.indices.count.value = self.fields.indices.tell()
		h.lists.offset.value = (h.fields.indices.offset.value + h.fields.indices.count.value)
		h.lists.count.value = self.lists.tell()

		for h2 in h:
			h2.write_to(f_out)
		for s in self.structs:
			s.write_to(f_out)
		for f in self.fields:
			f.write_to(f_out)
		self.labels.write_to(f_out)
		self.fields.data.seek(0)
		copy_buf(self.fields.data, f_out, h.fields.data.count.value)
		self.fields.indices.seek(0)
		copy_buf(self.fields.indices, f_out, h.fields.indices.count.value)
		self.lists.seek(0)
		copy_buf(self.lists, f_out, h.lists.count.value)

	class Header(object):
		def __init__(self, file_type, version):
			self._headers = headers = deque()
			class H(object):
				def __init__(self):
					self.offset = Field.DWORD()
					headers.append(self.offset)
					self.count = Field.DWORD()
					headers.append(self.count)

			self.file_type = Field.CExoString(file_type, 4)
			headers.append(self.file_type)
			self.version = Field.CExoString(version, 4)
			headers.append(self.version)
			self.structs = H()
			self.fields = H()
			self.labels = H()
			self.fields.data = H()
			self.fields.indices = H()
			self.lists = H()

		@property
		def size(self):
			return sum(f.size for f in self._headers)
		def __iter__(self):
			return iter(self._headers)
		def __str__(self, indent = 0):
			ls = ['GFF metadata: {}{}'.format(self.file_type.value, self.version.value)
				, 'Structs: {} (offset: 0x{:08X})'.format(self.structs.count.value, self.structs.offset.value)
				, 'Fields: {} (offset: 0x{:08X}), data size: {} (offset: 0x{:08X}), indices: {} (offset: 0x{:08X})'.format(self.fields.count.value, self.fields.offset.value, self.fields.data.count.value, self.fields.data.offset.value, self.fields.indices.count.value, self.fields.indices.offset.value)
				, 'Labels: {} (offset: 0x{:08X})'.format(self.labels.count.value, self.labels.offset.value)
				, 'Lists:  {} (offset: 0x{:08X})'.format(self.lists.count.value, self.lists.offset.value)
			]
			indentation = '\t' * indent
			return indentation + ('\n\t' + indentation).join(ls)

		def verify(self, log = lambda s:()):
			def offset_test(msg, offset):
				msg = msg + ' offset difference'
				if offset < 0:
					raise Exception(msg + ': {}'.format(offset))
				elif offset > 0:
					log(msg.ljust(40) + ': {}'.format(offset))
			offset_test('Structs', (self.structs.offset.value - self.size))
			offset_test('Fields', (self.fields.offset.value - self.structs.offset.value - (self.structs.count.value * 12)))
			offset_test('Labels', (self.labels.offset.value - self.fields.offset.value - (self.fields.count.value * 12)))
			offset_test('Field Data', (self.fields.data.offset.value - self.labels.offset.value - (self.labels.count.value * 16)))
			offset_test('Field Indices', (self.fields.indices.offset.value - self.fields.data.offset.value - self.fields.data.count.value))
			offset_test('Lists', (self.lists.offset.value - self.fields.indices.offset.value - self.fields.indices.count.value))

	@property
	def root(self):
		if not self._root:
			self._root = s = Field.Struct()
			s.label = ''
			s.from_gff(self, 0)
		return self._root
	@root.setter
	def root(self, root):
		if not isinstance(root, Field.Struct):
			raise Exception('GFF must contain Struct as root node')
		self._root = root
		self._data_stale = True

	class LabelMap(object):
		_list = deque()
		_map = {}

		def __getitem__(self, idx):
			val = self.get(idx)
			if val is None:
				raise ValueError
			return val
		def get(self, idx, default = None):
			if hasattr(idx, '__getitem__'):
				return self._map.get(idx, default)
			return self._list[idx] if ((idx < len(self._list)) and (idx >= 0)) else default
		def add(self, string):
			pos = self.get(string)
			if pos is None:
				pos = len(self._list)
				self._list.append(string)
				self._map[string] = pos
			return pos
		def append(self, string):
			return self.add(string)
		def __contains__(self, string):
			return self.get(string) is not None
		def __iter__(self):
			return iter(self._list)
		def __len__(self):
			return len(self._list)
		def write_to(self, f):
			for s in self:
				Field.CResRef(s).write_to(f)

	class FieldsList(HandlesList):
		def __init__(self):
			self._list = deque()
			self.data = io.BytesIO()
			self.indices = io.BytesIO()
			self.handles = [self.data, self.indices]
		def __getitem__(self, idx):
			return self._list[idx]
		def __iter__(self):
			return iter(self._list)
		def __len__(self):
			return len(self._list)
		def append(self, field):
			self._list.append(field)

	class StructHeader(object):
		size = 12
		@classmethod
		def from_file(cls, f_in):
			inst = cls()
			inst.type = Field.DWORD.from_data(f_in).value
			inst.data = Field.DWORD.from_data(f_in).value
			inst.count = Field.DWORD.from_data(f_in).value
			return inst
		def write_to(self, f_out):
			Field.DWORD(self.type).write_to(f_out)
			Field.DWORD(self.data).write_to(f_out)
			Field.DWORD(self.count).write_to(f_out)
	class FieldHeader(object):
		size = 12
		@classmethod
		def from_file(cls, f_in):
			inst = cls()
			inst.type = Field.DWORD.from_data(f_in).value
			inst.label = Field.DWORD.from_data(f_in).value
			inst.data = Field.DWORD.from_data(f_in).value
			return inst
		def write_to(self, f_out):
			Field.DWORD(self.type).write_to(f_out)
			Field.DWORD(self.label).write_to(f_out)
			Field.DWORD(self.data).write_to(f_out)

class VarTable(object):
	LABEL_NAME = 'Name'
	LABEL_TYPE = 'Type'
	LABEL_VALUE = 'Value'

	def __init__(self, field_list = deque()):
		self._list = field_list
		self._map = {}
		self._load()

	def _load(self):
		for v in self._list:
			if not isinstance(v, Field.Struct) or v.type != 0:
				pass # Error?
			field_label = None
			field_type = None
			field_value = None
			for f in v.value:
				if f.label == self.LABEL_NAME:
					field_label = f
				elif f.label == self.LABEL_TYPE:
					field_type = f
				elif f.label == self.LABEL_VALUE:
					field_value = f
			self._map[field_label.value] = (v, field_label, field_type, field_value)
	def _get_fields(self, key):
		return self._map.get(key, (None, None, None, None))
	def get_field(self, key):
		f_struct, f_name, f_type, f_value = self._get_fields(key)
		return f_value
	def get(self, key, val_default = None):
		f_value = self.get_field(key)
		return f_value.value if f_value else val_default
	def __getitem__(self, key):
		val = self.get(key)
		if val is None:
			raise ValueError
		return val
	def __setitem__(self, key, value):
		f_struct, f_name, f_type, f_value = self._get_fields(key)
		if f_value is None:
			self.add(key, value)
		elif isinstance(value, Field):
			f_value.value = value.value
		else:
			f_value.value = value
	def __len__(self):
		return len(self._list)
	@staticmethod
	def _change(f_struct, f_type, value):
		f_type.label = self.LABEL_TYPE
		if isinstance(value, Field):
			f_type = Field.DWORD(value.code) #TODO: Map type to Var Type
			f_value = value
		elif hasattr(value, '__getitem__'):
			f_type = Field.DWORD(3)
			f_value = Field.CExoString(value)
		elif False: # Is Location?
			f_type.value = 5
		else:
			f_type = Field.DWORD(1)
			f_value = Field.INT(value)
		f_value.label = self.LABEL_VALUE
		self._replace_field(f_struct, f_value)
		return f_value
	@staticmethod
	def _replace_field(f_struct, f_new):
		f_old = next((f for f in f_struct if f.label == f_new.label), None)
		if f_old:
			f_struct.value.remove(f_old)
		f_struct.value.append(f_new)
	def add(self, key, value):
		f_struct = Field.Struct()
		f_name = Field.CExoString(key)
		f_name.label = self.LABEL_NAME
		f_type = Field.DWORD()
		f_value = self._change(f_struct, f_type, value)
		self._list.append(f_struct)
		self._map[key] = (f_struct, f_name, f_type, f_value)
	def change(self, key, value):
		f_struct, f_name, f_type, f_value = self._get_fields(key)
		f_value = self._change(f_struct, f_type, value)
		self._map[key] = (f_struct, f_name, f_type, f_value)
