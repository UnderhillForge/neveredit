'''Some common (non-wx related) util functions'''
import sys
import numpy
import numpy.linalg

from PIL import Image, ImageEnhance

# Compatibility flag retained for legacy callers; backend is always numpy now.
use_numeric = True


class _NumericCompat(object):
    """Compatibility facade that exposes legacy Numeric APIs via NumPy."""

    Float = numpy.float64
    Int = numpy.int32

    _TYPECODE_MAP = {
        'f': numpy.float32,
        'd': numpy.float64,
        'i': numpy.int32,
        'l': numpy.int64,
        'h': numpy.int16,
        'b': numpy.int8,
        'B': numpy.uint8,
        'H': numpy.uint16,
        'I': numpy.uint32,
        'F': numpy.complex64,
        'D': numpy.complex128,
    }

    def _resolve_dtype(self, typecode=None, dtype=None):
        if dtype is not None:
            return numpy.dtype(dtype)
        if typecode is None:
            return None
        if isinstance(typecode, str):
            mapped = self._TYPECODE_MAP.get(typecode)
            if mapped is not None:
                return mapped
            return numpy.dtype(typecode)
        return numpy.dtype(typecode)

    def array(self, sequence, typecode=None, copy=1, savespace=0, dtype=None, shape=None):
        # Legacy Numeric accepted positional typecode and optional shape kwarg.
        _ = savespace
        resolved_dtype = self._resolve_dtype(typecode=typecode, dtype=dtype)
        if copy:
            arr = numpy.array(sequence, dtype=resolved_dtype, copy=True)
        else:
            arr = numpy.asarray(sequence, dtype=resolved_dtype)
        if shape is not None:
            arr = numpy.reshape(arr, shape)
        return arr

    def zeros(self, shape, typecode=None, dtype=None):
        resolved_dtype = self._resolve_dtype(typecode=typecode, dtype=dtype)
        return numpy.zeros(shape, dtype=resolved_dtype)

    def identity(self, n, typecode=None, dtype=None):
        resolved_dtype = self._resolve_dtype(typecode=typecode, dtype=dtype)
        return numpy.identity(n, dtype=resolved_dtype)

    def alltrue(self, values, axis=None):
        return numpy.all(values, axis=axis)

    def matrixmultiply(self, a, b):
        return numpy.matmul(a, b)

    def __getattr__(self, name):
        return getattr(numpy, name)


_numeric_compat = _NumericCompat()


class _LinearAlgebraCompat(object):
    """Compatibility facade that exposes legacy LinearAlgebra APIs via NumPy."""

    def inverse(self, matrix):
        return numpy.linalg.inv(matrix)

    def __getattr__(self, name):
        return getattr(numpy.linalg, name)


_linear_algebra_compat = _LinearAlgebraCompat()

def iAmOnMac():
    return sys.platform == 'darwin'

def iAmOnLinux():
    return 'linux' in sys.platform

def getNumPy():
    return _numeric_compat

def getLinAlg():
    return _linear_algebra_compat

def resizeSquareImage(image,size):
    image = image.resize((size,size),Image.ANTIALIAS)
    e = ImageEnhance.Sharpness(image)
    image = e.enhance(13)
    return image

