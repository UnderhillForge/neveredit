import numpy as np

from neveredit.util import Utils
from neveredit.openglcontext import vectorutilities


def test_utils_uses_numpy_backend():
    numeric = Utils.getNumPy()
    linear_algebra = Utils.getLinAlg()
    assert numeric.__version__ == np.__version__
    assert numeric.Float == np.float64
    assert numeric.zeros((1, 4), typecode=numeric.Float).dtype == np.float64
    assert np.all(numeric.alltrue(np.array([True, True])))
    shaped = numeric.array([1.0, 2.0, 3.0], shape=(3, 1))
    assert shaped.shape == (3, 1)
    inverse = linear_algebra.inverse(np.array([[1.0, 2.0], [3.0, 5.0]]))
    assert np.allclose(inverse, np.linalg.inv(np.array([[1.0, 2.0], [3.0, 5.0]])))


def test_vectorutilities_cross_and_normalise_numpy():
    a = [[1.0, 0.0, 0.0]]
    b = [[0.0, 1.0, 0.0]]
    cp = vectorutilities.crossProduct(a, b)
    assert np.allclose(cp[0], [0.0, 0.0, 1.0])

    n = vectorutilities.normalise([[3.0, 0.0, 0.0]])
    assert np.allclose(n[0], [1.0, 0.0, 0.0])
