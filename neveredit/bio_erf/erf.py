import sys
import io
import os
import argparse
import csv
import re
import fnmatch
import itertools
from collections import deque
from nwn.files.erf import ERFFile
import nwn.files.rim
import nwn.files.bif
from nwn.common.util import HandlesList, Log, LazyFormatter
from nwn.common.installation import Installation

def do_nothing(o, *args):
	return o

class ERFProcessor(object):
	def __init__(self, path_base, installation):
		self.path = path_base
		self.inst = installation

	@staticmethod
	def generate_files(files, file_strings, filename_strings = 'strings.csv'):
		# Allow for directories as arguments, but don't recurse subdirectories
		f_strings = [file_strings] if file_strings else []
		def expand_files():
			for f in files:
				if os.path.isdir(f):
					for name in os.listdir(f):
						path = os.path.join(f, name)
						if name.lower() == filename_strings:
							f_strings.append(path)
						else:
							yield path
				else:
					yield f
		files_flat = list(expand_files()) # Generate before return, in order to handle special strings file
		return f_strings, files_flat

	@staticmethod
	def generate_matchers(params, match_id_default = (lambda idx, total: True), match_name_default = do_nothing):
		match_id = lambda idx, total: True
		match_name = do_nothing
		if params:
			s_ids = params.get('ids', None)
			if s_ids:
				ids = list(split_ids(s_ids))
				match_id = lambda idx, total: match_in_ids(ids, idx, total)
			else:
				match_id = match_id_default

			pattern = params.get('name', None)
			if pattern is not None:
				pattern = pattern.lower()
			match_name = (match_name_default if pattern is None else
				lambda n: fnmatch.fnmatch(n.lower(), pattern))
			return match_id, match_name
		else:
			return match_id_default, match_name_default

	def _read_file(self, erf, handles, mode_list, mode_list_strings, mode_extract, filter_resources = None):
		def ensure_dir():
			if self.path and not os.path.exists(self.path):
				os.mkdir(self.path)

		if mode_extract:
			if self.path is None:
				self.path = ''
			handle_resource_header = do_nothing
			if mode_list or (not mode_list_strings):
				def extract_file(res):
					ensure_dir()
					name = res.filename
					with open(os.path.join(self.path, name), 'wb') as f_out:
						res.copy_data(erf, f_out)
						Log.info('Created {} ...', f_out.name)
				handle_resource = extract_file
			else:
				handle_resource = do_nothing

			if mode_list_strings:
				csv_strings = None
				def write_string(s):
					nonlocal csv_strings
					ensure_dir()
					if not csv_strings:
						f_strings = open(os.path.join(self.path, 'strings.csv'), 'w')
						handles.append(f_strings)
						csv_strings = csv.writer(f_strings, lineterminator='\n')
					csv_strings.writerow(s.as_tuple())
				handle_string = write_string
			else:
				handle_string = do_nothing
		else:
			mode_list = mode_list or (not mode_list_strings)
			handle_resource_header = (lambda r: print(r)) if mode_list else do_nothing
			handle_resource = None
			if mode_list_strings: # Do we want CSV, or a more human-readable format for printing?
				csv_strings = csv.writer(sys.stdout, lineterminator='\n')
				def print_string(s):
					csv_strings.writerow(s.as_tuple())
				handle_string = print_string
			else:
				handle_string = do_nothing

		match_id, match_name = self.generate_matchers(filter_resources)
		def handle_and_filter_resources(r, idx, total):
			if match_id(idx, total) and match_name(r.filename):
				handle_resource_header(r)
				return True
			else:
				return False

		try:
			erf.read(handle_string, handle_and_filter_resources, handle_resource)
		except BrokenPipeError: # Allow breaking of pipe (e.g. "... | head") to cause early exit without error for non-Extract command
			if mode_extract:
				raise

		Log.info('ERF metadata: {} {}', erf.file_type, erf.version)
		Log.info('\tLocalized Strings: {} (offset: 0x{:08X}, size: {})', erf.strings.count, erf.strings.offset, erf.strings.size)
		Log.info('\tEntries: {} (keys offset: 0x{:08X}, resources offset: 0x{:08X})', erf.resources.count, erf.resources.offset, erf.resources.offset_list if hasattr(erf.resources, 'offset_list') else -1)
		Log.info('\tDescription: 0x{:08X} (Build date: {})', erf.description_strref, erf.build_date)

	def read_file(self, f_in, mode_list, mode_list_strings, mode_extract, filter_resources = None):
		with ERFFile(f_in, 'r', installation = self.inst) as erf:
			with HandlesList() as handles:
				self._read_file(erf, handles.handles, mode_list, mode_list_strings, mode_extract, filter_resources)

	def _write_file(self, f_out, erf_type, erf_version, files, files_strings, strings_existing, resources_existing, description = None):

		def get_size(r):
			if r.path is None:
				return r.filesize
			return os.path.getsize(r.path)
		def write_data(r, cp):
			if hasattr(r, 'data'):
				cp(r.data)
			else:
				with open(r.path, 'rb') as f_in:
					cp(f_in)
					assert f_in.read(1) == b'', 'os.path.getsize lied to us; the file still has data left'
					Log.info('Added file {}', r.path)

		with ERFFile(f_out, 'w', erf_type, erf_version, installation = self.inst) as erf:
			def gen_resources():
				for f in files:
					r = erf.resource_from_file(f)
					r.path = f
					yield r
			def gen_strings():
				if description:
					#yield description
					pass
				for f in files_strings:
					with f if hasattr(f, 'read') else open(f, 'r') as f_csv:
						strings = csv.reader(f_csv)
						for l in strings:
							yield erf.new_string(*l)

			erf.write(
				itertools.chain(strings_existing, gen_strings())
				, itertools.chain(resources_existing, gen_resources())
				, get_size, write_data)

	def write_file(self, f_out, erf_type, erf_version, files, file_strings = None, description = None):
		files_strings, files_resources = self.generate_files(files, file_strings)
		self._write_file(f_out, erf_type, erf_version, files_resources, files_strings, [], [])

	def modify_file(self, f_in, f_out, archive_type, files, file_strings, filter_string, filter_file, overwrite_strings = False):
		version = None

		files_strings, files_resources = self.generate_files(files, file_strings)
		with HandlesList() as handles_resources:
			strings = deque()
			resources = deque()
			with ERFFile(f_in, 'r', installation = self.inst) as erf:
				def add_string(s):
					if filter_string(s):
						strings.append(s)
				def add_file(f):
					f.data = io.BytesIO()
					handles_resources.handles.append(f.data)
					f.copy_data(erf, f.data)
					f.data.seek(0)
					resources.append(f)

				erf.read((do_nothing if (overwrite_strings and files_strings) else add_string), filter_file, add_file)
				if not archive_type:
					archive_type = erf.file_type
				version = erf.version

			self._write_file(f_out, archive_type, version
				, files_resources, files_strings, strings, resources)

	def add_to_file(self, f_in, f_out, archive_type, files, file_strings, remove_dupes):
		if remove_dupes:
			files_strings, files = self.generate_files(files, file_strings)
			map_files_new = dict((os.path.basename(f), False) for f in files)
			match_files = (lambda r, *a: map_files_new.get(r.filename, True))
		else:
			match_files = do_nothing
		self.modify_file(f_in, f_out, archive_type, files, file_strings
			, do_nothing, match_files, remove_dupes)

	def remove_from_file(self, f_in, f_out, match_resources):
		do_not_match = (lambda *a: False)
		match_id, match_name = self.generate_matchers(match_resources, do_not_match, do_not_match)
		self.modify_file(f_in, f_out, None, [], None
			, do_nothing
			, (lambda r, idx, total: not (match_id(idx, total) or match_name(r))))

def split_ids(s_ids):
	for i in re.split('[,;]', ''.join(s_ids.split())): # Strip all whitespace anywhere in "s_ids"
		if not len(i):
			continue
		indices = i.split('-')
		if len(indices) == 1: # "4"
			yield (int(indices[0]),)
		elif len(indices) == 2: # "4-7" or "-2"
			i2 = int(indices[1])
			if not len(indices[0]):
				yield (-i2,)
			else:
				i1 = int(indices[0])
				yield (i1, i2) if (i1 < i2) else (i2, i1)
		elif len(indices) == 3: # "3--1"
			if len(indices[1]):
				raise Exception('Invalid range: {}'.format(i))
			yield (int(indices[0]), -int(indices[2]))
		elif len(indices) == 4: # "-2--1"
			if len(indices[0]) or len(indices[2]):
				raise Exception('Invalid range: {}'.format(i))
			i1 = -int(indices[1])
			i2 = -int(indices[3])
			yield (i1, i2) if (i1 < i2) else (i2, i1)

def match_in_ids(ids, idx, total):
	pos_neg = idx - total
	for i in ids:
		if len(i) == 1:
			i1, = i
			if (idx == i1) or (pos_neg == i1):
				return True
		else:
			i1, i2 = i
			if i1 < 0:
				if pos_neg >= i1 and pos_neg <= i2:
					return True
			else:
				if idx >= i1:
					if i2 < 0:
						if pos_neg <= i2:
							return True
					elif idx <= i2:
						return True
	return False


class ParameterizedHelpAction(argparse.Action):
	def __init__(self, option_strings, dest, help_params = {}, **kwargs):
		super().__init__(option_strings, dest, **kwargs)
		for k, v in help_params.items():
			setattr(self, k, LazyFormatter(None, v))
	def __call__(self, parser, namespace, values, option_string):
		setattr(namespace, self.dest, values)


if __name__ == '__main__':
	parser = argparse.ArgumentParser(add_help=False, conflict_handler='resolve')
	parser.add_argument('-l', '--files', dest='include_files', action='store_true', help="""Include files from archive (default unless also including strings)""")
	parser.add_argument('-d', '--dir', dest='outdir', default=None, metavar='DIR'
		, help="""
			Interact with archive at root of DIR instead of
			current directory (e.g. extract to DIR or add from DIR)
		""")
	parser.add_argument('-g', '--game', dest='game', metavar='GAME'
		, default=None, action=ParameterizedHelpAction
		, help_params={
			'game_list': lambda: ', '.join([t.abbr for t in Installation.types])
		}
		, help="""
			Specify for application to treat files as coming from GAME
			or with GAME as the root directory of a game installation
			(Try matching GAME as a directory first, then game identifier.
			The game identifier option will attempt to read system
			installation information from the Windows Registry or otherwise.
			Default to NWN. Games: %(game_list)s)
		""")
	parser.add_argument('-v', '--verbose', dest='verbose', action='store_true'
		, help="""Verbose mode (output more information)""")

	parser_main = argparse.ArgumentParser(parents=[parser], description="""
			View and extract data from ERF Archives (including HAK, MOD, SAV)
		""")
	parser.add_argument('archive', metavar='ARCHIVE', nargs='?'
		, help="""ERF archive (default to STDIN if no file)""")

	subparsers = parser_main.add_subparsers(title='actions', dest='command')
	def add_sub(name, **kwargs):
		return subparsers.add_parser(name, **kwargs)
	parser_read = argparse.ArgumentParser(add_help=False, parents=[parser])
	parser_read.add_argument('-s', '--add-strings', dest='include_strings'
		, action='store_true', help="""Include strings from archive""")
	parser_read.add_argument('--ids', dest='ids', default=None
		, help="""
			Select only the specified Resource IDs (as a single ID or range, IDs
			starting at 0, with negative numbers denoting position relative to
			the end of the archive, e.g. "3,5-9,-1")
		""")
	parser_read.add_argument('--name', metavar='PATTERN', dest='filter_name'
		, default=None, help="""
			Filter the Resources by PATTERN (Shell syntax, with "*" and "?" as
			wildcard characters; don't forget to escape the "*" character with
			quotes or a backslash so that the Shell itself doesn't expand it.)
		""")
	add_sub('list', parents=[parser_read]
		, help="""LIST the contents of the archive (default command)""")

	parser_extract = add_sub('extract', parents=[parser_read]
		, help="""EXTRACT the contents of the archive""")
	parser_extract.add_argument('outdir', metavar='DIR', nargs='?'
		, help="""Extract files to DIR""", default=argparse.SUPPRESS)

	parser_add = argparse.ArgumentParser(add_help=False, parents=[parser])
	parser_add.add_argument('files', metavar='FILE', nargs='*'
		, help="""FILEs to add to archive""")
	parser_add.add_argument('-s', '--strings', metavar='FILE', dest='file_strings'
		, help="""Add strings from FILE (CSV format)""")
	parser_add.add_argument('-t', '--type', dest='type', default=None
		, help="""
			Specify type of archive to write
			(default to infer from file extension)
		""")

	parser_create = add_sub('create', parents=[parser_add]
		, help="""CREATE an archive from FILES""", add_help=False)
	parser_create.add_argument('-1', '--v1', action='store_true'
		, dest='v_erf1', help="""Create ERF 1.0 (NWN) Archive (default)""")
	parser_create.add_argument('-2', '--v2', action='store_true'
		, dest='v_erf1_1', help="""Create ERF 1.1 (NWN2) Archive""")
	#parser_create.add_argument('--description', metavar='STRING'
	#	, help="""Add STRING as archive description""")

	parser_inplace = argparse.ArgumentParser(add_help=False)
	parser_inplace.add_argument('-o', '--output', dest='outfile', default=None
		, metavar='FILE', help="""Write to FILE instead of archive in-place""")

	parser_add_inplace = add_sub('add', parents=[parser_add, parser_inplace]
		, help="""ADD resources to an archive""")
	parser_add_inplace.add_argument('-r', '--replace', dest='mode_replace'
		, action='store_true', help="""
			Replace files with same name in archive
			(and add those that don't match)
		""")

	parser_remove = add_sub('remove', parents=[parser_read, parser_inplace]
		, help="""REMOVE resources from an archive""")

	args = parser_main.parse_args()
	outdir = None if args.outdir == '' else args.outdir
	Log.basicConfig(stream = (sys.stderr if args.command == 'list' else sys.stdout), level = (Log.INFO if args.verbose else Log.WARNING))

	if args.game is None:
		installation = Installation.NWN()
	elif os.path.isdir(args.game):
		installation = args.game
	else:
		installation = getattr(Installation, args.game.upper())()

	driver = ERFProcessor(outdir, installation)

	if args.command == 'create':
		driver.write_file(
			(sys.stdout.buffer if args.archive is None else args.archive)
			, args.type, 'V1.1' if args.v_erf1_1 else 'V1.0'
			, (args.files or [outdir or os.getcwd()])
			, file_strings = (sys.stdin if args.file_strings == '-' else args.file_strings)
			, description = (args.description if hasattr(args, 'description') else None)
		)
	elif args.command == 'add':
		if args.archive == '-':
			args.archive = None
		driver.add_to_file(
			(sys.stdin.buffer if args.archive is None else args.archive)
			, (sys.stdout.buffer if args.archive is None else args.archive) if args.outfile is None else args.outfile
			, args.type , args.files
			, (sys.stdin if args.file_strings == '-' else args.file_strings)
			, args.mode_replace
		)
	elif args.command == 'remove':
		driver.remove_from_file(
			(sys.stdin.buffer if args.archive is None else args.archive)
			, (sys.stdout.buffer if args.archive is None else args.archive) if args.outfile is None else args.outfile
			, {'ids': args.ids, 'name': args.filter_name}
		)
	else:
		if (outdir is None):
			# Default to creating a directory with the same name as the Archive file
			if args.archive and ((not args.include_strings) or args.include_files):
				d, ext = os.path.splitext(args.archive)
				driver.path = os.path.basename(d)
		driver.read_file(
			(sys.stdin.buffer if args.archive is None else args.archive)
			, args.include_files, args.include_strings, args.command == 'extract'
			, {'ids': args.ids, 'name': args.filter_name}
		)
