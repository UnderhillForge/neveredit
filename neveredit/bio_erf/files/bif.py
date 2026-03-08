import os
import itertools
from collections import deque
from nwn.files.erf import ERFFile, ResourceInfo, _ResCollection
from nwn.data.field import Field
from nwn.common.bytes import copy_buf
from nwn.common.util import Log
from nwn.common.installation import normalize_winpath


class BIFResource(ResourceInfo):
	size_name = 16
	size_bif = 16 # Header data in the BIF
	size_bytes = 0 # No additional byte headers
	offset = None
	def __init__(self, name, type_res, resid = 0, *args, **kwargs):
		super().__init__(name, type_res, *args, **kwargs)
		self.resid = resid # Index into BIF tables

	def __str__(self):
		fmt = '{}'
		name = self.filename.ljust(self.size_name + 5)[:(self.size_name + 5)] # Allow for name, period, 4-char extension
		args = (name,)
		if hasattr(self, 'key'):
			fmt = fmt + '\tID: 0x{:06X}, BIF: {}'
			path_bif = (self.key.bifs[self.idx_bif].path if self.key.bifs else 'N/A')
			args = (name, self.bifid, path_bif)
		elif self.offset is not None:
			fmt = fmt + '\t(offset: 0x{:08X}, size: {})'
			args = (name, self.offset, self.filesize)
		return fmt.format(*args)

	@property
	def size(self):
		return 6 + self.size_name # Just the Header size
	@property
	def idx_bif(self):
		return self.bifid_split(self.resid)[0]
	@property
	def bifid(self):
		return self.bifid_split(self.resid)[1]
	@staticmethod
	def bifid_split(resid):
		return divmod(resid, (2**20))
	@classmethod
	def from_archive(cls, f_in):
		name = Field.CResRef.from_data(f_in).value
		file_type = Field.WORD.from_data(f_in).value
		resid = Field.DWORD.from_data(f_in).value
		return cls(name, file_type, resid)
	def read_data_info(self, *args):
		pass # We read everything we need in "from_archive"
	def read_data_bif(self, f_bif):
		bifid = Field.DWORD.from_data(f_bif).value
		if (self.bifid_split(bifid)[1] != self.bifid):
			Log.error('BIF ID mismatch: {} (Key: {})', self.bifid_split(bifid)[1], self.bifid)
		self.offset = Field.DWORD.from_data(f_bif).value
		self.filesize = Field.DWORD.from_data(f_bif).value
		res_type = Field.DWORD.from_data(f_bif).value
		if res_type != self.type:
			Log.error('Resource type mismatch: {} (Key: {})', res_type, self.type)
	def copy_data(self, key, f_out):
		bif = key.bifs[self.idx_bif]
		bif.file.seek(self.offset)
		copy_buf(bif.file, f_out, self.filesize)

	def generate_header(self, resid):
		return (self._write_name()
			+ Field.DWORD(self.type).write_to()
			+ Field.DWORD(resid).write_to()
			+ Field.DWORD(self.offset).write_to()
			+ Field.DWORD(self.filesize).write_to()
		)
	def generate_byte_header(self, *args, **kwargs):
		return bytes()


class KeyBIF(ERFFile):
	file_type = 'KEY'
	version = 'V1  '
	cls_resource = BIFResource
	len_header = 64

	def __init__(self, *args, installation = None, **kwargs):
		self._resmap = {}
		self.bifs = deque()
		self.handles = deque(self.handles)
		self.inst = installation # Support an Installation object, or a path
		super().__init__(*args, **kwargs)
		self.cls_resource.key = self

	def _read_header(self, read_v):
		"""
			With Key/BIF files, we have additional wrinkles.
			A Key file references all of the resources in multiple BIFs
				(up to 2^14).
			So, the key file is essentially one big header, which we want
				to read here. The BIFs have additional header data, like
				the offset and size of each resource.
			In an effort to minimize disk reads, we don't read the data in
				the BIFs here, but on-demand when we want to read the actual
				data (like for a file copy). So, for any given BIF, on the
				first file copy for a resource in that BIF, we will read the
				entire header for that particular BIF.
			Additionally, we still want object-oriented, modular code.
		"""
		entry_count = read_v()
		key_count = read_v()
		entry_offset = read_v()
		key_offset = read_v()
		self.build_date = self.date_from_yearday(read_v(), read_v())
		self.strings = _ResCollection([])
		self.resources = _ResCollection(key_count, 0, key_offset, self.cls_resource)
		self.resources.offset_list = key_offset + (self.cls_resource('dummy', 0).size * key_count)

		# Build the BIF file table
		self.file.seek(entry_offset)

		for i in range(entry_count):
			bif = BIFFile(self, read_v())
			self.handles.append(bif)
			bif.name_offset = read_v()
			bif.name_size = Field.WORD.from_data(self.file).value
			bif.drive = Field.WORD.from_data(self.file).value
			self.bifs.append(bif)
		for bif in sorted(self.bifs, key=(lambda b: b.name_offset)):
			self.file.seek(bif.name_offset)
			bif._read_path(self.file)

	def read(self, *args, **kwargs):
		resources = self.resources.get_objects(self.file)
		idx_selector = lambda r: r.idx_bif
		resources.sort(key=idx_selector)
		for idx, g in itertools.groupby(resources, idx_selector):
			bif = self.bifs[idx]
			bif.strings = self.strings
			bif.resources = _ResCollection(list(g))
			with bif: # Close the handle?
				bif.read(*args, **kwargs)

	def _write_header(self, write_v):
		raise NotImplementedError('No support for writing Key/BIF files')


class BIFFile(ERFFile):
	file_type = 'BIFF'
	version = 'V1  '
	cls_resource = BIFResource
	len_header = 20
	_map = None
	file = None

	@staticmethod
	def __new__(cls, *args, **kwargs):
		return super(ERFFile, cls).__new__(cls) # Bypass special ERF instantiation logic
	def __init__(self, key, size, drive = 0, path = None):
		self.key = key
		self.size = size
		self.drive = drive
		self.path = path
		self.handles = []

	def _prepare_resources(self, resources):
		if len(resources) == 0: # Don't open file if not necessary
			return
		if not self._open():
			raise Exception('Failed to open BIF: {}'.format(self.path))
		file_type = Field.CExoString.from_data(self.file, size = 4).value
		if file_type != self.file_type:
			Log.error('Unknown file type for BIF: {}', file_type)
		version = Field.CExoString.from_data(self.file, size = 4).value
		if version != self.version:
			Log.error('Unsupported version for BIF: {}', version)

		resources.sort(key = (lambda r: r.bifid))
		self._read_header(lambda: Field.DWORD.from_data(self.file).value)
		for r in resources:
			self.file.seek(self.resources.offset + (r.size_bif * r.bifid))
			r.read_data_bif(self.file)
		resources.sort(key = (lambda r: r.offset))

	def _read_header(self, read_v):
		resources_variable_count = read_v()
		resources_fixed_count = read_v()
		resources_variable_offset = read_v()
		if resources_variable_offset < self.len_header:
			raise Exception('Invalid value in Resource offset: 0x{:04X} (file: {})'.format(resources_variable_offset, self.file.name if self.file else '{None}'))
		elif resources_variable_offset > self.len_header:
			Log.warn('Non-standard value in Resource offset: 0x{:08X} (file: {})', resources_variable_offset, self.file.name if self.file else '{None}')
		self.resources = _ResCollection(resources_variable_count, 0, resources_variable_offset, self.cls_resource)
		# BioWare didn't support the fixed header resources, so we won't either

	def _read_path(self, f_in):
		f_in.seek(self.name_offset)
		self.path = Field.CExoString.from_data(f_in, size = self.name_size).value

	def _open(self):
		def open_path(path):
			path = normalize_winpath(self.path, path)
			try:
				self.file = open(path, 'rb')
				self.handles.append(self.file)
				size = os.fstat(self.file.fileno()).st_size
				if size != self.size:
					Log.error('BIF size mismatch: {} (Key: {}): {}', size, self.size, path)
				else:
					Log.debug('Opened BIF: {}', path)
				return self.file
			except IOError:
				return None

		if hasattr(self.key.inst, 'get_path'):
			for i in range(Field.WORD(0).size):
				if ((self.drive >> i) % 2):
					if open_path(self.key.inst.get_path(i)):
						return self.file
		elif (self.drive % 2): # For anything but Drive 0, we don't know what to do
			if open_path(self.key.inst or os.getcwd()):
				return self.file
		return None


def __register_BIF():
	ERFFile._register_type(KeyBIF.file_type, KeyBIF.version, KeyBIF)
__register_BIF()

