"""Minimal LinearAlgebra compatibility shim backed by numpy.linalg."""

import numpy.linalg as _linalg

from numpy.linalg import *  # noqa: F401,F403

inverse = _linalg.inv
