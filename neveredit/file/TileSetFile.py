import logging
logger = logging.getLogger("neveredit")
import configparser,io
Set = set

from neveredit.util import neverglobals
from neveredit.game.Tile import Tile

class TileSetFile(configparser.ConfigParser):
    def __init__(self):
        configparser.ConfigParser.__init__(self)
        self.groupTiles = None
        self.tiles = None
        
    def fromFile(self,f):        
        self.read_file(f)

    def getTileCount(self):
        return self.getint('TILES','Count')

    def getGroupCount(self):
        return self.getint('GROUPS','Count')

    def getAllGroupTileIDs(self):
        if self.groupTiles:
            return self.groupTiles
        self.groupTiles = Set()
        for i in range(self.getGroupCount()):
            self.groupTiles.update(self.getGroupTileIDs(i))
        return self.groupTiles

    def isTileInGroup(self,tile):
        tiles = self.getAllGroupTileIDs()
        return tile.getId() in tiles
    
    def getGroupTileIDs(self,group):
        tiles = []
        gname = 'GROUP' + repr(group)
        rows = self.getint(gname,'Rows')
        cols = self.getint(gname,'Columns')
        for i in range(rows*cols):
            tiles.append(self.getint(gname,'Tile'+repr(i)))
        return tiles

    def getStandardTiles(self):
        if not self.tiles:
            self.tiles = [self.makeNewTile(i)
                          for i in range(self.getTileCount())
                          if i not in self.getAllGroupTileIDs()]
        return self.tiles
    
    def makeNewTile(self,tid):
        t = Tile(tid=tid,tileset=self)
        return t
    
    def getTileInfo(self,tid):
        return self.items('TILE'+repr(tid))
    
    def __getitem__(self,key):
        section,entry = key.split('.')
        return self.get(section,entry)

    def getDefaultTileID(self):
        """Return the tile ID used to fill a blank new area.

        The NWN toolset initialises every tile to the first tile whose four
        corner-terrain fields all match the terrain type named by
        ``GENERAL.default`` (e.g. 'Wall' for most interior tilesets,
        'Grass' for rural exterior, etc.).  Tile 0 is typically a *corner*
        transition piece, not a flat fill tile, so using it produces visible
        seam artefacts.  Falls back to 0 only when the search fails.
        """
        try:
            default_type = self.get('GENERAL', 'default', fallback='').strip().lower()
            if not default_type:
                return 0
            tile_count = self.getint('TILES', 'Count')
            best = None
            best_score = None
            for tid in range(tile_count):
                section = 'TILE' + str(tid)
                if not self.has_section(section):
                    continue

                corners = [
                    self.get(section, 'topleft',     fallback='').strip().lower(),
                    self.get(section, 'topright',    fallback='').strip().lower(),
                    self.get(section, 'bottomleft',  fallback='').strip().lower(),
                    self.get(section, 'bottomright', fallback='').strip().lower(),
                ]
                if not all(c == default_type for c in corners):
                    continue

                edges = [
                    self.get(section, 'top', fallback='').strip().lower(),
                    self.get(section, 'right', fallback='').strip().lower(),
                    self.get(section, 'bottom', fallback='').strip().lower(),
                    self.get(section, 'left', fallback='').strip().lower(),
                ]
                has_crossers = any(edges)
                doors = self.getint(section, 'doors', fallback=0)
                pathnode = self.get(section, 'pathnode', fallback='').strip().upper()
                path_rank = 0 if pathnode == 'A' else (1 if pathnode in ('B', 'C', 'O') else 2)

                score = (1 if has_crossers else 0,
                         1 if doors > 0 else 0,
                         path_rank,
                         tid)
                if best_score is None or score < best_score:
                    best_score = score
                    best = tid

            if best is not None:
                return best
        except Exception:
            pass
        return 0
    
    def __str__(self):
        buffer = io.StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __repr__(self):
        return self.__str__()
    
if __name__ == '__main__':
    import neveredit.util.Loggers
    import sys
    t = TileSetFile()
    t.fromFile(open(sys.argv[1]))
    for i in t.items('GENERAL'):
        print(i)
        
