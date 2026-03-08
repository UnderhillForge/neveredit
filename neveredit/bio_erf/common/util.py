import sys
import logging
import types

def eprint(*msgs):
	for s in msgs:
		sys.stderr.write(s + '\n')

def eprint_indent(level, *msgs):
	for s in msgs:
		eprint('\t' * level + s)

class Log(object):
	@staticmethod
	def get_logger(name = None):
		log = logging.getLogger(name)
		if not hasattr(log, '_fstrings'):
			def get_message(record):
				msg = str(record.msg)
				args = record.args
				return (msg.format(*args if isinstance(args, tuple) else args) if args else msg)
			def wrap_handle(fx):
				def handle(record):
					record.getMessage = types.MethodType(get_message, record)
					return fx(record)
				return handle
			log.handle = wrap_handle(log.handle)
		log._fstrings = True
		return log

	DEBUG = logging.DEBUG
	INFO = logging.INFO
	WARNING = logging.WARNING
	ERROR = logging.ERROR
	CRITICAL = logging.CRITICAL

	@staticmethod
	def basicConfig(*args, **kwargs):
		logging.basicConfig(*args, **kwargs)
	@classmethod
	def debug(cls, *args, **kwargs):
		cls._logger_default.debug(*args, **kwargs)
	@classmethod
	def info(cls, *args, **kwargs):
		cls._logger_default.info(*args, **kwargs)
	@classmethod
	def warn(cls, *args, **kwargs):
		cls._logger_default.warn(*args, **kwargs)
	@classmethod
	def error(cls, *args, **kwargs):
		cls._logger_default.error(*args, **kwargs)
	@classmethod
	def exception(cls, *args, **kwargs):
		cls._logger_default.exception(*args, **kwargs)
	@classmethod
	def critical(cls, *args, **kwargs):
		cls._logger_default.critical(*args, **kwargs)

Log._logger_default = Log.get_logger('nwn')

class HandlesList(object):
	handles = () # Default to empty, static collection
	def __init__(self):
		self.handles = [] # But for instances that don't override __init__, provide modifiable collection
	def __enter__(self):
		return self
	def __exit__(self, *e):
		for o in self.handles:
			with o:
				pass # Do nothing but ensure we call the __exit__ method
		self.handles = []

class LazyFormatter(object):
	def __init__(self, o, fx):
		self._obj = o
		self._fx = fx
	def __str__(self):
		return self._fx() if self._obj is None else self._fx(self._obj)

class NumericValue(object):
	pass

def _gen_func(name):
	return lambda self, *p: getattr(self.value, name)(*p)
for name in ['int', 'float', 'complex'] + [n for n_base in
	['add', 'sub', 'mul', 'truediv', 'floordiv', 'mod', 'divmod',
	'pow', 'lshift', 'rshift', 'and', 'xor', 'or',]
	for n in (n_base, 'r' + n_base, 'i' + n_base)
]:
	name = '__' + name + '__'
	# Add all of the numeric operators to the NumericValue class
	setattr(NumericValue, name, _gen_func(name))

