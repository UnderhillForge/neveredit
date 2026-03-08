import struct

def dump_hex_array(bytes):
	return ' '.join('{:02X}'.format(b) for b in bytes)

def to_signed(val, size=4):
	threshold = (0x80 << (8 * (size - 1)))
	return (((val + threshold) & ((1 << (size * 8)) - 1)) - threshold)
def to_unsigned(val, size=4):
	return ((1 << (size * 8)) + val) if (val < 0) else val

def read_uint(source, size=4):
	s = source.read(size) if hasattr(source, 'read') else source
	val, = struct.unpack('<I', (s[0:4] if len(s) >= 4 else (s + struct.pack('x' * (4 - len(s))))))
	return val
def read_int(source, size=4):
	return to_signed(read_uint(source, size), 4) # Pad to 4 bytes
def read_str(source, size):
	size = int(size)
	return str(source.read(size), 'cp1252') if size > 0 else ''
def read_str0(source, size):
	s = read_str(source, size)
	idx_0 = s.find('\x00')
	return s if (idx_0 < 0) else s[:idx_0]

def _write_val(val, fmt, dest, size):
	b = struct.pack(fmt, val)
	b = b[0:size] if size < 4 else b
	if hasattr(dest, 'write'):
		dest.write(b)
	return b
def write_uint(val, dest=None, size=4):
	return _write_val(val, '<I', dest, size)
def write_int(val, dest=None, size=4):
	return _write_val(val, '<i', dest, size)
def write_str(s, dest=None):
	b = s.encode('cp1252') # It hurts my heart, but I can't change a game from 2003
	return write_bytes(b, dest)
def write_bytes(b, dest=None):
	if hasattr(dest, 'write'):
		dest.write(b)
	return b

def copy_buf(f_in, f_out, size, size_chunk = 4096):
	count_bytes = 0
	while count_bytes < size:
		remaining = size - count_bytes
		data = f_in.read(size_chunk if remaining > size_chunk else remaining)
		if data == b'':
			raise Exception('Reached end of file attempting copy: {} ({} of {})'.format(f_in.name or '-', count_bytes, size))
		count_bytes = count_bytes + len(data)
		f_out.write(data)

class UnseekableWrapper(object):
	def __init__(self, fd):
		self.pos = 0
		self.fd = fd
	def read(self, length):
		data = self.fd.read(length)
		self.pos = self.pos + len(data)
		return data
	def write(self, data):
		count = self.fd.write(data)
		self.pos = self.pos + count
		return count
	def tell(self):
		return self.pos
	def seek(self, pos, whence = 0): # Replace default seek method
		if whence > 0:
			fd.seek(pos, whence)
			return
		assert pos >= self.pos
		count = (pos - self.pos)
		while (count > 0):
			ln = self._seek(count if (count < 4096) else 4096)
			if ln <= 0:
				raise IOError('Reached end of file (0x{:08X}) trying to seek to posision: 0x{:08X}'.format(self.tell(), pos))
			count = (count - ln)
	#@abstractmethod - Future Python feature
	def _seek(self, count):
		raise NotImplementedError # abstract
	def fileno(self):
		return self.fd.fileno()
	def __enter__(self):
		return self
	def __exit__(self):
		pass # No context to manage

class UnseekableReader(UnseekableWrapper):
	def _seek(self, count):
		return len(self.read(count))
class UnseekableWriter(UnseekableWrapper):
	def _seek(self, count):
		return self.write(bytes(count))


