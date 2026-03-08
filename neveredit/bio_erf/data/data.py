import struct
from collections import deque
from nwn.common.bytes import to_signed, to_unsigned \
	, read_uint, read_str, read_str0 \
	, write_uint, write_str, write_bytes, copy_buf, dump_hex_array
from nwn.common.util import NumericValue

class Field(object):
	_map = {}
	types = []
	def __init__(self, val = None):
		self._value = val

	@property
	def size(self):
		return self._size
	@property
	def value(self):
		return self._value
	@value.setter
	def value(self, val):
		self._value = val

	@property
	def stacktrace(self):
		if not hasattr(self, 'stack') or (len(self.stack) < 1):
			return ''
		return '.'.join(f.label for f in self.stack) + '.'
	def gff_add_field_data(self, gff): # The value for the "Field" Array in the GFF
		return self.value
	def gff_add(self, gff):
		id_label = gff.labels.add(self.label)
		id_field = len(gff.fields)
		gff.fields.append((self.code, id_label, self.field_data(gff)))
	def from_gff(self, gff, data):
		self.value = data # "Simple" data types
	def to_gff_data(self, gff):
		return self.value

	@classmethod
	def from_data(cls, f_in, *args, **kwargs):
		inst = cls(*args, **kwargs)
		inst._value = inst._read(f_in)
		return inst
	def write_to(self, f_out = None):
		return self._write(self.value, f_out)

	def _read(self, f_in):
		return read_uint(f_in, self.size)
	def _write(self, val, f_out):
		return write_uint(val, f_out, self.size)
	def __str__(self):
		return str(self.value)

	@classmethod
	def register(cls, clsSub):
		cls.types.append(clsSub)
		if clsSub:
			cls._map[clsSub.name] = clsSub
			setattr(cls, clsSub.name, clsSub) # Create reverse lookup

def _extend_Field():
	class Field_Numeric(Field, NumericValue):
		pass
	class Field_Signed(Field_Numeric):
		@property
		def value(self):
			return self._value
		@value.setter
		def value(self, val):
			self._value = to_signed(val, self.size)
		def to_gff_data(self, gff):
			return to_unsigned(self.value, self.size)

	class Field_Complex(Field): # Not "complex" as in "complex number", but in that data won't fit in a DWORD
		def from_gff(self, gff, data):
			gff.fields.data.seek(data)
			self.value = self._read(gff.fields.data)
		def to_gff_data(self, gff):
			offset = gff.fields.data.tell()
			self.write_to(gff.fields.data)
			return offset
	class Field_Pointer(Field_Complex):
		field_length = Field()
		def from_gff(self, gff, data):
			gff.fields.data.seek(data)
			self._size = read_uint(gff.fields.data, self.field_length.size)
			self.value = self._read(gff.fields.data)
		def to_gff_data(self, gff):
			offset = gff.fields.data.tell()
			write_uint(self.size, gff.fields.data, self.field_length.size)
			self.write_to(gff.fields.data)
			return offset

	class Field_String(Field_Pointer):
		def _read(self, f_in):
			return read_str0(f_in, self.size)
		def _write(self, val, f_out):
			b = write_str(val, f_out)
			if not self.size is None and len(b) < self.size:
				b = b + write_bytes(bytes(self.size - len(b)), f_out)
			return b
		def __len__(self):
			return len(self.value)

	class Field_64Bit(Field_Complex, Field_Numeric):
		s_format = ''
		_size = 8
		def _read(self, f_in):
			val, = struct.unpack(self.s_format, f_in.read(self._size))
			return val
		def _write(self, val, f_out):
			return write_bytes(struct.pack(self.s_format, val), f_out)

	class FieldBYTE(Field_Numeric):
		'Unsigned single byte (0 to 255)'
		name = 'BYTE'
		_size = 1

	class FieldCHAR(Field):
		'Single character byte'
		name = 'CHAR'
		_size = 1

	class FieldDOUBLE(Field_64Bit):
		'Double-precision floating point value'
		name = 'DOUBLE'
		s_format = '<d'
	class FieldDWORD(Field_Numeric):
		'Unsigned integer (0 to 4294967296)'
		name = 'DWORD'
		_size = 4
	class FieldDWORD64(Field_64Bit):
		'Unsigned integer (0 to roughly 18E18)'
		name = 'DWORD64'
		s_format = '<Q'
	class FieldFLOAT(Field_Numeric):
		'Floating point value'
		name = 'FLOAT'
		_size = 4
	class FieldINT(Field_Signed):
		'Signed integer (-2147483648 to 2147483647)'
		name = 'INT'
		_size = 4
	class FieldINT64(Field_64Bit, Field_Signed):
		'Signed integer (roughly -9E18 to +9E18)'
		name = 'INT64'
		s_format = '<q'
	class FieldSHORT(Field_Signed):
		'Signed integer (-32768 to 32767)'
		name = 'SHORT'
		_size = 2

	class FieldCResRef(Field_String):
		"""Filename of a game resource. Max length is 16 characters. Unused characters are nulls."""
		name = 'CResRef'
		_size = 16
		field_length = FieldBYTE()

	class FieldCExoLocString(Field_Pointer):
		"""Localized string. Contains a StringRef DWORD, and a number of CExoStrings, each having their own language ID."""
		name = 'CExoLocString'
		field_length = FieldDWORD()
		def _read(self, f_in):
			strref = FieldDWORD.from_data(f_in)
			count = FieldDWORD.from_data(f_in)
			strings = deque()
			for i in range(count.value):
				lang = FieldDWORD.from_data(f_in)
				s = FieldCExoString.from_data(f_in, size = FieldDWORD.from_data(f_in).value, label = self.label)
				strings.append((lang.value, s.value))
			return (strref.value, strings)
		def _write(self, val, f_out):
			strref, strings = val
			field_dw = FieldDWORD()
			b_header = field_dw._write(strref, f_out) + field_dw._write(len(strings), f_out)
			def write_str(lang, s):
				b = field_dw._write(lang, f_out) + field_dw._write(len(s), f_out)
				return b + FieldCExoString(s).write_to(f_out)
			return b_header + bytes().join(write_str(lang, s) for lang, s in strings)
		def __str__(self):
			strref, strings = self.value
			for lang, s in strings:
				return '({}) [{}:{}] {}'.format(len(strings), lang // 2, lang % 2, s)
			return '{}: NULL'.format(strref)

	class FieldCExoString(Field_String):
		'Non-localized string'
		name = 'CExoString'
		field_length = FieldDWORD()
		def __init__(self, string = None, size = None, label = None):
			super().__init__(string)
			self._size = size
			self.label = label
		@property
		def size(self):
			return self._size if self.value is None else len(self.value)

	class FieldVOID(Field_Pointer):
		'Variable-length arbitrary data'
		name = 'VOID'
		field_length = FieldDWORD()
		def _read(self, f_in):
			return f_in.read(self.size)
		def _write(self, val, f_out):
			return write_bytes(val, f_out)

	class FieldWORD(Field_Numeric):
		'Unsigned integer value (0 to 65535)'
		name = 'WORD'
		_size = 2
	class FieldStruct(Field):
		"""A complex data type that can contain any number of any of the other data types, including other Structs."""
		name = 'Struct'
		_size = 12
		stack = []
		def __init__(self):
			self._value = deque()

		def from_gff(self, gff, data):
			def add_field(idx):
				v = gff.fields.data_cache[idx] # Do we need to support duplicate data?
				if v is None:
					f = gff.fields[idx]
					v = Field.types[f.type]()
					v.stack = self.stack
					v.label = gff.labels[f.label]
					v.from_gff(gff, f.data)
					gff.fields.data_cache[idx] = v
				self._value.append(v)

			s = gff.structs[data]
			self.type = s.type
			if s.count < 1:
				pass
			elif s.count > 1:
				gff.fields.indices.seek(s.data)
				# Read all indices at once so that we don't have to worry about a moving pointer
				indices = [Field.DWORD.from_data(gff.fields.indices) for i in range(s.count)]
				for idx in indices:
					add_field(idx.value)
			else:
				add_field(s.data)
		def to_gff_data(self, gff):
			pos = len(gff.structs)
			def add_field(field):
				fld = gff.FieldHeader()
				fld.type = field.code
				fld.label = gff.labels.append(field.label)
				fld.data = field.to_gff_data(gff)
				idx = len(gff.fields)
				gff.fields.append(fld)
				return idx
			struct = gff.StructHeader()
			gff.structs.append(struct)
			struct.type = self.type
			struct.count = len(self.value)
			if struct.count < 1:
				struct.data = 0
			elif struct.count > 1:
				indices = [add_field(f) for f in self.value]
				struct.data = gff.fields.indices.tell()
				for idx in indices:
					FieldDWORD(idx).write_to(gff.fields.indices)
			else:
				for f in self.value:
					struct.data = add_field(f)
			return pos

	class FieldList(Field):
		'A list of Structs.'
		name = 'List'
		def __init__(self):
			self._value = deque()
		@property
		def size(self):
			raise NotImplementedError
		def from_gff(self, gff, data):
			gff.lists.seek(data)
			count = Field.DWORD.from_data(gff.lists)
			indices = [Field.DWORD.from_data(gff.lists) for i in range(count.value)]
			for i, idx in enumerate(indices):
				s = Field.Struct()
				s.stack = self.stack + [s]
				s.label = '{}[{}]'.format(self.label, i)
				s.from_gff(gff, idx.value)
				self._value.append(s)
		def to_gff_data(self, gff):
			indices = [struct.to_gff_data(gff) for struct in self.value]
			pos = gff.lists.tell()
			Field.DWORD(len(self.value)).write_to(gff.lists)
			for idx in indices:
				Field.DWORD(idx).write_to(gff.lists)
			return pos

	for i, t in enumerate([
		FieldBYTE,
		FieldCHAR,
		FieldWORD,
		FieldSHORT,
		FieldDWORD,
		FieldINT,
		FieldDWORD64,
		FieldINT64,
		FieldFLOAT,
		FieldDOUBLE,
		FieldCExoString,
		FieldCResRef,
		FieldCExoLocString,
		FieldVOID,
		FieldStruct,
		FieldList,
	]):
		t.code = i
		Field.register(t)

_extend_Field()
