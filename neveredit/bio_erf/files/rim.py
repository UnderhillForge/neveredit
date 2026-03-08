from nwn.files.erf import ERFFile, ResourceInfo, _ResCollection
from nwn.data.field import Field
from nwn.files import formats
from nwn.common.bytes import copy_buf


class RIMResource(ResourceInfo):
	size_name = 16
	size_bytes = 0 # No additional byte headers

	def __init__(self, name, type_res, path = None):
		self.name = name
		self.type = type_res
		self.path = path
		self.filesize = None

	@property
	def size(self):
		return 16 + self.size_name # Just the Header size
	@classmethod
	def from_archive(cls, f_in):
		name = Field.CResRef.from_data(f_in).value
		file_type = Field.DWORD.from_data(f_in).value
		resid = Field.DWORD.from_data(f_in).value
		inst = cls(name, file_type)
		inst.offset = Field.DWORD.from_data(f_in).value
		inst.filesize = Field.DWORD.from_data(f_in).value
		return inst
	def read_data_info(self, *args):
		pass # We read everything we need in "from_archive"
	def copy_data(self, erf, f_out):
		erf.file.seek(self.offset)
		copy_buf(erf.file, f_out, self.filesize)

	def generate_header(self, resid):
		return (self._write_name()
			+ Field.DWORD(self.type).write_to()
			+ Field.DWORD(resid).write_to()
			+ Field.DWORD(self.offset).write_to()
			+ Field.DWORD(self.filesize).write_to()
		)
	def generate_byte_header(self, *args, **kwargs):
		return bytes()


class RIMFile(ERFFile):
	file_type = 'RIM'
	version = 'V1.0'
	cls_resource = RIMResource
	description_strref = -1
	build_date = 'N/A'
	len_header = 120

	def _read_header(self, read_v):
		slocal_count = read_v() # Not sure what actually this field contains
		entry_count = read_v()
		resources_offset = read_v()
		slocal_offset = read_v() # Also not sure
		self.strings = _ResCollection([])
		self.resources = _ResCollection(entry_count, 0, resources_offset, self.cls_resource)
		self.resources.offset_list = resources_offset + (self.cls_resource('dummy', 0).size * entry_count)

	def _write_header(self, write_v):
		write_v(0)
		write_v(self.resources.count)
		write_v(self.resources.offset)
		write_v(0)


def __register_RIM():
	ERFFile._register_type('RIM', 'V1.0', RIMFile)
__register_RIM()

