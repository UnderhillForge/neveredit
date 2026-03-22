"""Lightweight ECS-style adapter for renderable world objects.

The current game model objects under ``game/`` remain authoritative.
This module provides cached render snapshots that decouple queue/culling
logic from data-model classes.
"""

import math

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class RenderWorldCache:
    """Mutable cache of render snapshots used by queue building."""

    tile_entries: List[Optional["RenderTile"]] = field(default_factory=list)
    thing_entries: List[Optional["RenderThing"]] = field(default_factory=list)

    def reset(self, tile_count=0, thing_count=0):
        self.tile_entries = [None] * int(max(0, tile_count))
        self.thing_entries = [None] * int(max(0, thing_count))

    def set_tile(self, index, entry):
        if index < 0:
            return
        if index >= len(self.tile_entries):
            self.tile_entries.extend([None] * (index + 1 - len(self.tile_entries)))
        self.tile_entries[index] = entry

    def set_thing(self, index, entry):
        if index < 0:
            return
        if index >= len(self.thing_entries):
            self.thing_entries.extend([None] * (index + 1 - len(self.thing_entries)))
        self.thing_entries[index] = entry

    def get_tile(self, index):
        if index < 0 or index >= len(self.tile_entries):
            return None
        return self.tile_entries[index]

    def get_thing(self, index):
        if index < 0 or index >= len(self.thing_entries):
            return None
        return self.thing_entries[index]


@dataclass(frozen=True)
class RenderTile:
    """Renderable snapshot for a tile."""

    tile_index: int
    modelName: str
    x: float
    y: float
    z: float
    bearing_degrees: float
    model: Optional[Any]


@dataclass(frozen=True)
class RenderThing:
    """Renderable snapshot for a world thing."""

    thing_index: int
    entity_id: Optional[int]
    modelName: str
    x: float
    y: float
    z: float
    bearing: float
    bearing_degrees: float
    model: Optional[Any]
    uses_generic_marker: bool = False

    def getX(self):
        return self.x

    def getY(self):
        return self.y

    def getZ(self):
        return self.z

    def getBearing(self):
        return self.bearing


def snapshot_tile(tile, tile_index, area_width, model=None) -> Optional[RenderTile]:
    """Extract a render snapshot from a tile instance."""
    if tile is None:
        return None
    try:
        width = max(1, int(area_width))
        x = int(tile_index) % width
        y = int(tile_index) // width
        tx = x * 10.0 + 5.0
        ty = y * 10.0 + 5.0
        tz = float(tile.getTileHeight()) * 5.0
        bearing_degrees = float(tile.getBearing())
        model_name = str(getattr(tile, 'modelName', '') or '')
        return RenderTile(tile_index=int(tile_index),
                          modelName=model_name,
                          x=tx,
                          y=ty,
                          z=tz,
                          bearing_degrees=bearing_degrees,
                          model=model)
    except (AttributeError, TypeError, ValueError):
        return None


def snapshot_thing(thing, thing_index=-1, model=None) -> Optional[RenderThing]:
    """Extract a render snapshot from a game thing instance.

    Returns ``None`` when required transform/model fields cannot be read.
    """
    if thing is None:
        return None
    try:
        model_name = str(getattr(thing, 'modelName', '') or '')
        x = float(thing.getX())
        y = float(thing.getY())
        z = float(thing.getZ())
        bearing = float(thing.getBearing())
        bearing_degrees = bearing * 180.0 / math.pi
        entity_id = None
        if hasattr(thing, 'getNevereditId'):
            entity_id = thing.getNevereditId()
        uses_generic_marker = False
        if hasattr(thing, 'usesGenericMarkerFallback'):
            uses_generic_marker = bool(thing.usesGenericMarkerFallback())
        return RenderThing(thing_index=int(thing_index),
                           entity_id=entity_id,
                           modelName=model_name,
                           x=x,
                           y=y,
                           z=z,
                           bearing=bearing,
                           bearing_degrees=bearing_degrees,
                           model=model,
                           uses_generic_marker=uses_generic_marker)
    except (AttributeError, TypeError, ValueError):
        return None
