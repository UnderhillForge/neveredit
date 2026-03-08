"""
	Classes to interact with BioWare's ERF archive file type
	Provide an interface similar to Python's zipfile.ZipFile class
"""

import types
import struct
import sys
import os
from datetime import date, timedelta
from nwn.files import formats
from nwn.data.field import Field
from nwn.common.bytes import UnseekableReader, UnseekableWriter, copy_buf
from nwn.common.util import HandlesList, Log

class StringInfo(object): # A string within an ERF archive
	def __init__(self, langid, s):
		self.lang = int(langid)
		self.str = str(s)

	def __str__(self):
		return '0x{:04X}: {}'.format(self.lang, self.str)

	@classmethod
	def from_archive(cls, f_in):
		langid = Field.DWORD.from_data(f_in)
		size = Field.DWORD.from_data(f_in)
		return cls(langid, Field.CExoString.from_data(f_in, size = size))

	def __len__(self):
		return len(self.str)
	@property
	def size(self):
		return 8 + len(self)

	def as_tuple(self):
		return (self.lang, self.str)
	def as_bytes(self):
		return (Field.DWORD(self.lang).write_to()
			+ Field.DWORD(len(self)).write_to()
			+ Field.CExoString(self.str).write_to()
		)

class ResourceInfo(object): # An object within an ERF archive
	size_name = 0
	size_bytes = 8 # Size of bytes information (offset, size)

	def __init__(self, name, type_res, path = None):
		self.name = str(name)
		self.type = int(type_res)
		self.path = path
		self.filesize = None

	def __str__(self):
		fmt = '{}'
		name = self.filename
		args = (name,)
		if self.offset is not None:
			if self.size_name > 0:
				name = name.ljust(self.size_name + 5)[:(self.size_name + 5)] # Allow for name, period, 4-char extension
			fmt = fmt + '\t(offset: 0x{:08X}, size: {})'
			args = (name, self.offset, self.filesize)
		return fmt.format(*args)

	@property
	def filename(self):
		ext = formats.Formats.get(self.type, None)
		return  self.name + '.' + str(ext.extension if ext else self.type)

	@property
	def size(self):
		return 8 + self.size_name # Just the Header size
	@classmethod
	def from_archive(cls, f_in):
		name = Field.CResRef.from_data(f_in)
		resid = Field.DWORD.from_data(f_in)
		inst = cls(name, Field.DWORD.from_data(f_in))
		return inst
	def read_data_info(self, f_in = None):
		if f_in:
			self.offset = Field.DWORD.from_data(f_in).value
			self.filesize = Field.DWORD.from_data(f_in).value
	def copy_data(self, erf, f_out):
		erf.file.seek(self.offset)
		copy_buf(erf.file, f_out, self.filesize)

	def _write_name(self):
		name = Field.CResRef(self.name)
		b_name = name.write_to()
		if len(b_name) > name.size:
			raise Exception('Resource name too large: {}'.format(self.filename))
		return b_name
	def generate_header(self, resid):
		return (self._write_name()
			+ Field.DWORD(resid).write_to()
			+ Field.DWORD(self.type).write_to()
		)
	def generate_byte_header(self, offset = None, filesize = None):
		if offset is None:
			offset = self.offset
		if filesize is None:
			filesize = self.filesize
		return Field.DWORD(offset).write_to() + Field.DWORD(filesize).write_to()

class ERFFile(HandlesList):
	file_type = 'ERF'
	version = ''
	cls_resource = ResourceInfo
	cls_string = StringInfo
	len_header = 160
	description_strref = -1

	@staticmethod
	def __new__(cls, fileio, mode = 'r', file_type = '', version = '', **kwargs):
		with HandlesList() as h: # In case something goes wrong during instantiation
			if mode == 'r':
				if hasattr(fileio, 'read'):
					fd = (fileio if fileio.seekable() else UnseekableReader(fileio))
				else:
					fd = open(fileio, 'rb')
					h.handles.append(fd)

				file_type = str(Field.CExoString.from_data(fd, size = 4)).strip()
				version = str(Field.CExoString.from_data(fd, size = 4))
			elif mode == 'w':
				if hasattr(fileio, 'write'):
					fd = (fileio if fileio.seekable() else UnseekableWriter(fileio))
				else:
					fd = open(fileio, 'wb')
					h.handles.append(fd)
					if not file_type:
						p, ext = os.path.splitext(fileio)
						file_type = ext[1:].upper() if len(ext) > 1 else ''
			else:
				raise Exception('Unrecognized file mode ({})'.format(mode))

			Log.debug('Types: {}\nDefault: {}', cls.types, cls.version_default)
			clsNew = cls._class_from_type_version(file_type, version)
			inst = super(ERFFile, cls).__new__(clsNew)
			if file_type:
				inst.file_type = file_type
			inst.file = fd
			inst.handles = h.handles # Handoff to new Context Handler
			h.handles = ()
			return inst

	def __init__(self, fileio, mode = 'r', file_type = '', version = '', **kwargs):
		if mode == 'r':
			self._read_header(lambda: Field.DWORD.from_data(self.file).value)
		elif mode != 'w':
			raise Exception('Invalid File IO mode: ' + mode)

	def _header_handle_extra(self, bytes):
		pass

	def new_string(self, *args):
		return self.cls_string(*args)

	def resource_from_file(self, path):
		if os.path.isdir(path):
			raise Exception('Cannot create Resource from subdirectory: {}'.format(path))
		name = os.path.basename(path)
		name, ext = os.path.splitext(name)
		if len(ext) < 2:
			raise Exception('Cannot determine file type for file without extension: {}'.format(path))
		restype = formats.Formats.get(ext[1:], None)
		if not restype:
			try:
				restype = formats.FileFormat(int(ext[1:]), '???')
			except ValueError:
				raise Exception('Unable to determine file type for file: {}'.format(path))
		return self.cls_resource(name, restype.type, path = path)

	types = {}
	version_default = {}

	@classmethod
	def _register_type(cls, name, version, t, **kwargs):
		if (name is None):
			version_map = cls.version_default
		else:
			version_map = cls.types.get(name, None)
			if not version_map:
				version_map = {}
				cls.types[name] = version_map
		version_map[version] = t

	@classmethod
	def _class_from_type_version(cls, file_type, version):
		version_map = cls.types.get(file_type, cls.version_default)
		clsInst = version_map.get(version, None)
		if not clsInst:
			clsInst = version_map.get(None, None)
			if not clsInst:
				raise Exception('Invalid file type and version: {}{}'.format(file_type, version))
		return clsInst

	@staticmethod
	def date_from_yearday(v_year, v_day):
		return (date(1900 + v_year, 1, 1) + timedelta(days = v_day))
	@staticmethod
	def yearday_from_date(d):
		return ((d.year - 1900), (d - date(d.year, 1, 1)).days)

	def _read_header(self, read_v):
		# Assume we've already read the Type+Version header
		slocal_count = read_v()
		slocal_size = read_v()
		entry_count = read_v()
		slocal_offset = read_v()
		self.strings = _ResCollection(slocal_count, slocal_size, slocal_offset, self.cls_string)
		keys_offset = read_v()
		resources_offset = read_v()
		self.resources = _ResCollection(entry_count, 0, keys_offset, self.cls_resource)
		self.resources.offset_list = resources_offset
		self.build_date = self.date_from_yearday(read_v(), read_v())
		self.description_strref = read_v()

	def _write_header(self, write_v):
		write_v(self.strings.count)
		write_v(self.strings.size)
		write_v(self.resources.count)
		write_v(self.strings.offset)
		write_v(self.resources.offset)
		write_v(self.resources.offset_list)
		y, d = self.yearday_from_date(date.today())
		write_v(y)
		write_v(d)
		self.description_strref = 0
		write_v(self.description_strref)

	def _prepare_resources(self, resources):
		resources.sort(key=(lambda r: r.offset))

	def read(self, handle_string, handle_resource_header, handle_resource):
		"""
			Support interacting with the archive's data.
			Do our best to read sequentially in cases
				where the data is not truly Seekable (e.g. from STDIN).
		"""
		if handle_string:
			for s in self.strings.get_objects(self.file):
				handle_string(s)
		if handle_resource_header or handle_resource:
			resources = self.resources.get_objects(self.file)
			if hasattr(self.resources, 'offset_list'):
				self.file.seek(self.resources.offset_list)
			def gen_resources():
				for i, r in enumerate(resources):
					r.read_data_info(self.file)
					if handle_resource_header(r, i, len(resources)):
						yield r
			resources = list(gen_resources())
			if handle_resource:
				self._prepare_resources(resources)
				for r in resources:
					self.file.seek(r.offset)
					handle_resource(r)

	def write(self, strings, files, get_filesize, write_data):
		strings = list(strings) if strings else []
		self.strings = _ResCollection(strings)
		self.strings.offset = self.len_header

		files = list(files) if files else []
		Log.info('Files count: {}', len(files))
		self.resources = _ResCollection(files)

		self.resources.offset = self.strings.offset + self.strings.size
		self.resources.offset_list = self.resources.offset + self.resources.size

		if not self.version:
			raise Exception('Unspecified version for archive') # Error, or provide default?

		file_type = self.file_type or 'ERF'
		b_header = Field.CExoString(file_type.ljust(4) + self.version).write_to()
		if len(b_header) != 8:
			raise Exception('Invalid archive header: {}{}'.format(file_type, self.version))
		self.file.write(b_header)

		self._write_header(lambda i: Field.DWORD(i).write_to(self.file))

		self.file.write(bytes(self.strings.offset - self.file.tell()))
		for s in strings:
			self.file.write(s.as_bytes())
		Log.info('Added {} Strings', len(strings))

		self.file.write(bytes(self.resources.offset - self.file.tell()))
		offset = self.resources.offset_list + (len(files) * self.cls_resource.size_bytes)
		for i, f in enumerate(files):
			f.filesize = get_filesize(f)
			f.offset = offset
			self.file.write(f.generate_header(i))
			offset = offset + f.filesize
		self.file.write(bytes(self.resources.offset_list - self.file.tell()))
		for f in files:
			self.file.write(f.generate_byte_header())

		for f in files:
			write_data(f, lambda d: copy_buf(d, self.file, f.filesize))

	def __iter__(self):
		return iter(self.resources.get_objects(self.file))


class _ResCollection(object): # A collection of resources (or strings)
	def __init__(self, objects, size = 0, offset = 0, cls = None):
		if hasattr(objects, '__len__'):
			self.objects = objects
			self.count = len(objects)
			self.size = sum(o.size for o in objects)
			self.cls_object = cls or (type(next(iter(objects))) if self.count > 0 else None)
		else:
			self.objects = None
			self.count = objects
			self.size = size
			self.cls_object = cls
		self.offset = offset

	def get_objects(self, f_in):
		if self.objects is None:
			f_in.seek(self.offset)
			self.objects = [self.cls_object.from_archive(f_in) for n in range(self.count)]
		return self.objects

def _Extend_ERF():
	class StringInfoV1(StringInfo):
		@staticmethod
		def read_s(f_in, size):
			return Field.CExoString.from_data(f_in, size = size)

		def __init__(self, langid, fl_gender, s):
			lang = (int(langid) * 2 + (1 if fl_gender == 'F' else 0))
			super().__init__(lang, s)
		def as_tuple(self):
			lang, gender = self.lang_to_id_gender(self.lang)
			return (lang, gender, self.str)
		@classmethod
		def from_archive(cls, f_in):
			lang, gender =  cls.lang_to_id_gender(int(Field.DWORD.from_data(f_in)))
			size = Field.DWORD.from_data(f_in).value
			return cls(lang, gender, cls.read_s(f_in, size))
		@staticmethod
		def lang_to_id_gender(langid):
			return ((langid // 2), 'F' if (langid % 2) else 'M')

	class StringZInfoV1(StringInfoV1):
		@staticmethod
		def read_s(f_in, size):
			s = StringInfoV1.read_s(f_in, size)
			if len(s) == size:
				raise Exception('String has no NULL terminator: {}'.format(s))
			return s
		def __len__(self):
			return len(self.str) + 1 # Account for NULL terminator
		def as_bytes(self):
			return super().as_bytes() + bytes(1)

	class ResourceInfoV1(ResourceInfo):
		size_name = 16

	class ERFv1(ERFFile): # ERF v1.0 (NWN)
		version = 'V1.0'
		cls_string = StringInfoV1
		cls_resource = ResourceInfoV1
	class ERFv1_SZ(ERFv1):
		cls_string = StringZInfoV1 # The types that use a NULL-termination byte for their strings

	class ERFv1_1(ERFFile): # ERF v1.1 (NWN2)
		version = 'V1.1'

	for t in [ 'MOD', 'SAV' ]:
		ERFFile._register_type(t, ERFv1.version, ERFv1)
	for c in [ ERFv1_SZ, ERFv1_1 ]:
		ERFFile._register_type(None, c.version, c)

_Extend_ERF() # Add additional methods and classes to ERFFile class

