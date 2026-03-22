from neveredit.render.ecs import RenderWorldCache, snapshot_thing, snapshot_tile


class _FakeTile(object):
    modelName = 'tcn01a.mdl'

    def getTileHeight(self):
        return 2

    def getBearing(self):
        return 90.0


class _FakeThing(object):
    modelName = 'plc_tree.mdl'

    def getX(self):
        return 12.5

    def getY(self):
        return 25.0

    def getZ(self):
        return 1.5

    def getBearing(self):
        return 1.0

    def getNevereditId(self):
        return 42

    def usesGenericMarkerFallback(self):
        return False


def test_snapshot_tile_caches_world_transform_and_model():
    tile = snapshot_tile(_FakeTile(), tile_index=7, area_width=4, model='tile-model')

    assert tile is not None
    assert tile.tile_index == 7
    assert tile.modelName == 'tcn01a.mdl'
    assert (tile.x, tile.y, tile.z) == (35.0, 15.0, 10.0)
    assert tile.bearing_degrees == 90.0
    assert tile.model == 'tile-model'


def test_snapshot_thing_caches_entity_transform_and_model():
    thing = snapshot_thing(_FakeThing(), thing_index=3, model='thing-model')

    assert thing is not None
    assert thing.thing_index == 3
    assert thing.entity_id == 42
    assert thing.modelName == 'plc_tree.mdl'
    assert (thing.getX(), thing.getY(), thing.getZ()) == (12.5, 25.0, 1.5)
    assert thing.model == 'thing-model'
    assert thing.uses_generic_marker is False


def test_render_world_cache_set_and_get_entries():
    cache = RenderWorldCache()
    cache.reset(tile_count=2, thing_count=3)
    cache.set_tile(1, 'tile-entry')
    cache.set_thing(2, 'thing-entry')

    assert cache.get_tile(1) == 'tile-entry'
    assert cache.get_thing(2) == 'thing-entry'
    assert cache.get_tile(99) is None
    assert cache.get_thing(99) is None