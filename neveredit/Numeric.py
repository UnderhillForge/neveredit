"""Minimal Numeric compatibility shim backed by NumPy."""

import numpy as _np
from numpy import *  # noqa: F401,F403

Float = _np.float64
__version__ = _np.__version__


def array(obj, typecode=None):
    return _np.array(obj, dtype=typecode)


def asarray(obj, typecode=None):
    return _np.asarray(obj, dtype=typecode)


def zeros(shape, typecode=Float):
    return _np.zeros(shape, dtype=typecode)


def identity(n, typecode=Float):
    return _np.identity(n, dtype=typecode)
