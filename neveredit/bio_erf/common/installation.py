"""
	Common functions to access information about a NWN installation
	Tries to use Wine if it can't use Windows APIs
"""
import sys
import os
import configparser
from collections import deque

try: # Try Windows
	from winreg import ConnectRegistry, OpenKey, QueryValue
	import winreg
	def get_registry_value(key, val):
		key_root, key_sub = key.split('\\', 1)
		if key_root in ['HKLM', 'HKEY_LOCAL_MACHINE']:
			hive = winreg.HKEY_LOCAL_MACHINE
		elif key_root in ['HKCU', 'HKEY_CURRENT_USER']:
			hive = winreg.HKEY_CURRENT_USER
		elif key_root in ['HKCR', 'HKEY_CLASSES_ROOT']:
			hive = winreg.HKEY_CLASSES_ROOT
		else:
			hive = winreg.HKEY_LOCAL_MACHINE

		with ConnectRegistry(None, hive) as reg: # "None" means the local machine
			with OpenKey(hive, key_sub) as k:
				v, t = QueryValueEx(k, val)
				return v

	def normalize_winpath(path, cwd = None):
		return path if cwd is None else os.path.normpath(os.path.join(cwd, path))

except ImportError: # Assume non-Windows
	import subprocess
	def get_registry_value(key, val):
		cmd = 'reg query {} /v {}'.format(key, val)
		process = subprocess.Popen(['wine', 'cmd', '/c', cmd]
			, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
		out, err = process.communicate()
		v = out.decode('utf-8').strip() # Returns output like below:
		"""
			HKEY_LOCAL_MACHINE\Path\To\Key
			  ValueName   REG_SZ    Value
		"""
		try:
			l1, l2, = v.splitlines()
			name, t, value = l2.split(maxsplit=2)
			return value
		except ValueError:
			return None

	def normalize_winpath(path_win, cwd = None):
		process = subprocess.Popen(['winepath', '-u', path_win], shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=cwd)
		out, err = process.communicate()
		return out.decode('utf-8')[:-1] # The output contains a trailing newline


class Installation(object):
	_root_path = None
	config = None
	_config_path = None
	_config_name = None
	_registry_value = 'Path'
	types = deque()

	@classmethod
	def _register_type(cls, abbr, cls_type):
		cls.types.append(cls_type)
		setattr(cls, abbr, cls_type)
		cls_type.abbr = abbr

	def __init__(self, path_root = None, path_config = None):
		self._root_path = path_root
		self._config_path = path_config
		self._paths = []

	@property
	def root_path(self):
		if not self._root_path:
			self._root_path = normalize_winpath(get_registry_value(self.registry_key, self._registry_value))
		return self._root_path

	def normalize_path(self, path):
		return normalize_winpath(path, self.root_path)
		# Will we support a native Linux installation?
		# Not sure how yet

	def get_config_value(self, section, name):
		if self.config is None:
			self.config = configparser.ConfigParser()
			if self._config_path:
				self.config.read(self._config_path)
			else:
				config_name = self._config_name.lower()
				path_base = (self.root_path or os.getcwd())
				try:
					filename = next((
							f for f in os.listdir(path_base)
							if f.lower() == config_name # Search in directory for file, case-insensitive
						), self._config_name)
					self.config.read(os.path.join(path_base, filename))
				except FileNotFoundError:
					return None
		try:
			return self.config[section][name]
		except KeyError:
			return None

	def get_path(self, idx):
		if idx < len(self._paths):
			return self._paths[idx]
		else:
			self._paths = self._paths + [None] * (idx - len(self._paths) - 1)
			p = self.get_config_value('Alias', 'HD{}'.format(idx))
			if p is not None:
				p = self.normalize_path(p)
			self._paths.append(p)
			return p
	def get_paths(self):
		idx = 0
		while True:
			p = self.get_path(idx)
			if p is None:
				break
			yield p
			idx += 1

def __extend_Installations():
	class InstallationNWN(Installation):
		registry_key = 'HKLM\\Software\\BioWare\\NWN\\Neverwinter'
		_config_name = 'nwn.ini'
	class InstallationKOTOR(Installation):
		registry_key = 'HKLM\\Software\\BioWare\\SW\\Kotor'
		_config_name = 'swkotor.ini'

	for t in [ ('NWN', InstallationNWN), ('KOTOR', InstallationKOTOR) ]:
		Installation._register_type(*t)


__extend_Installations()

