"""Minimal numarray compatibility shim backed by NumPy."""

import numpy as _np
from numpy import *  # noqa: F401,F403

__version__ = _np.__version__


class _ErrorCompat:
    @staticmethod
    def setMode(**kwargs):
        return None


Error = _ErrorCompat()


def array(obj, typecode=None):
    return _np.array(obj, dtype=typecode)


def asarray(obj, typecode=None):
    return _np.asarray(obj, dtype=typecode)


def zeros(shape, typecode='d'):
    return _np.zeros(shape, dtype=typecode)


def reshape(a, newshape):
    return _np.reshape(a, newshape)


def add(a, b, out=None):
    result = _np.add(a, b)
    if out is not None:
        out[...] = result
        return out
    return result


def sqrt(a, out=None):
    result = _np.sqrt(a)
    if out is not None:
        out[...] = result
        return out
    return result


def divide(a, b):
    return _np.divide(a, b)
