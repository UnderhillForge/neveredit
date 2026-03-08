class __FormatsCollection:
	_map = {}
	def _register_format(cls, f):
		cls._map[f.type] = f
		cls._map[f.extension] = f
	def __getitem__(cls, key):
		return cls._map[key]
	def get(cls, key, v_default):
		return cls._map.get(key, v_default)
Formats = __FormatsCollection()

class FileFormat:
	def __init__(self, restype, ext, type_content = None, description = ''):
		self.type = restype
		self.extension = ext
		self.type_content = type_content
		self.description = description

def _register_formats():
	for t, ext, desc in [
		(0xFFFF, '', 'Invalid resource type'),
		(1, 'bmp', 'Windows BMP file'),
		(3, 'tga', 'TGA image format'),
		(4, 'wav', 'WAV sound file'),
		(6, 'plt', 'Bioware Packed Layered Texture, used for player character skins, allows for multiple color layers'),
		(7, 'ini', 'Windows INI file format'),
		# Why use decimal instead of hex? BioWare listed the decimal values in the doc
		(10, 'txt', 'Text file'),
		(2002, 'mdl', 'Aurora model'),
		(2009, 'nss', 'NWScript Source'),
		(2010, 'ncs', 'NWScript Compiled Script'),
		(2012, 'are', 'BioWare Aurora Engine Area file. Contains information on what tiles are located in an area, as well as other static area properties that cannot change via scripting.\nFor each .area file in a .mod, there must also be a corresponding .git and .gic file having the same ResRef.'),
		(2013, 'set', 'BioWare Aurora Engine Tileset'),
		(2014, 'ifo', 'Module Info File. Set the IFO Format document.'),
		(2015, 'bic', 'Character/Creature'),
		(2016, 'wok', 'Walkmesh'),
		(2017, '2da', '2-D Array'),
		(2022, 'txi', 'Extra Texture Info'),
		(2023, 'git', 'Game Instance File. Contains information for all object instances in an area, and all area properties that can change via scripting.'),
		(2025, 'uti', 'Item Blueprint'),
		(2027, 'utc', 'Creature Blueprint'),
		(2029, 'dlg', 'Conversation File'),
		(2030, 'itp', 'Tile/Blueprint Palette File'),
		(2032, 'utt', 'Trigger Blueprint'),
		(2033, 'dds', 'Compresse texture file'),
		(2035, 'uts', 'Sound Blueprint'),
		(2036, 'ltr', 'Letter-combo probability info for name generation'),
		(2037, 'gff', 'Generic File Format. Used when undesirable to create a new file extension for a resource, but the resource is a GFF. (Examples of GFFs include itp, utc, uti, ifo, are, git)'),
		(2038, 'fac', 'Faction File'),
		(2040, 'ute', 'Encounter Blueprint'),
		(2042, 'utd', 'Door Blueprint'),
		(2044, 'utp', 'Placeable Object Blueprint'),
		(2045, 'dft', 'Default Values file. Used by area properties dialog'),
		(2046, 'gic', 'Game Instance Comments. Comments on instances area not used by the game, only the toolset, so they are stored in a gic instead of in the git with the other instance properties.'),
		(2047, 'gui', 'Grapical User Interface layout used by game'),
		(2051, 'utm', 'Store/Merchant Blueprint'),
		(2052, 'dwk', 'Door walkmesh'),
		(2053, 'pwk', 'Placeable Object walkmesh'),
		(2056, 'jrl', 'Journal File'),
		(2058, 'utw', 'Waypoint Blueprint. See Waypoint GFF document.'),
		(2060, 'ssf', 'Sound Set File. See Sound Set File Format document.'),
		(2064, 'ndb', 'Script Debugger File'),
		(2065, 'ptm', 'Plot Manager file/Plot Instance'),
		(2066, 'ptt', 'Plot Wizard Blueprint'),
	]:
		Formats._register_format(FileFormat(t, ext, None, desc))
_register_formats()

