from neveredit.game.Creature import Creature
from neveredit.util import neverglobals


class _FakeTwoDA(object):
    def getRowCount(self):
        return 1

    def getEntry(self, index, column):
        assert index == 0
        values = {
            'MODELTYPE': 'P',
            'MODEL_A': 'g',
            'MODEL_B': 'h',
            'MODEL': 'o',
            'RACE': 'e',
        }
        return values[column]


class _FakeResourceManager(object):
    RESOURCETYPES = {'MDL': 2002}

    def __init__(self):
        self.resource_lookups = []
        self.name_queries = []

    def getResourceByName(self, name, copy=False):
        if name == 'appearance.2da':
            return _FakeTwoDA()
        self.resource_lookups.append((name, copy))
        raise AssertionError('player-part candidates should not be loaded as standalone MDLs')

    def getKeysWithName(self, name):
        self.name_queries.append(name)
        return []


class _DummyCreature(Creature):
    def __getitem__(self, key):
        if key == 'Appearance_Type':
            return 0
        raise KeyError(key)


def test_player_style_creature_part_prefixes_skip_missing_resource_lookups(monkeypatch):
    fake_rm = _FakeResourceManager()
    monkeypatch.setattr(neverglobals, 'getResourceManager', lambda: fake_rm)

    creature = _DummyCreature.__new__(_DummyCreature)
    creature.model = None

    assert creature.getModel(copy=False) is None
    assert creature.usesGenericMarkerFallback() is True
    assert fake_rm.resource_lookups == []
    assert fake_rm.name_queries == []