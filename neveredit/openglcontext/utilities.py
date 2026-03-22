'''Simple utility functions that should really be in a C module'''
from math import *
import numpy as np
from . import vectorutilities

def rotMatrix(rotation):
        """Given rotation as x,y,z,a (a in radians), return rotation matrix

        Returns a 4x4 rotation matrix for the given rotation,
        the matrix is a Numeric Python array.
        
        x,y,z should be a unit vector.
        """
        (x,y,z,a) = rotation
        c = cos( a )
        s = sin( a )
        t = 1-c
        R = np.array([
                [ t*x*x+c, t*x*y+s*z, t*x*z-s*y, 0],
                [ t*x*y-s*z, t*y*y+c, t*y*z+s*x, 0],
                [ t*x*z+s*y, t*y*z-s*x, t*z*z+c, 0],
                [ 0,        0,        0,         1]
        ] )
        return R
def crossProduct( first, second ):
        """Given 2 4-item vectors, return the cross product as a 4-item vector"""
        x,y,z = vectorutilities.crossProduct( first, second )[0]
        return [x,y,z,0]
def magnitude( vector ):
        """Given a 3 or 4-item vector, return the vector's magnitude"""
        return vectorutilities.magnitude( vector[:3] )[0]
def normalise( vector ):
        """Given a 3 or 4-item vector, return a 3-item unit vector"""
        return vectorutilities.normalise( vector[:3] )[0]

def pointNormal2Plane( point, normal ):
        """Create parametric equation of plane from point and normal
        """
        point = np.asarray(point, 'd')
        normal = normalise(normal)
        result = np.zeros((4,), 'd')
        result[:3] = normal
        result[3] = - np.dot(normal, point)
        return result

def plane2PointNormal(plane):
        """Get a point and normal from a plane equation"""
        (a,b,c,d) = plane
        return np.asarray((-d * a, -d * b, -d * c), 'd'), np.asarray((a, b, c), 'd')

if __name__ == "__main__":
        for p,n in [
                ([0,1,0], [0,-1,0]),
                ([1,0,0], [1,0,0]),
                ([0,0,1], [0,0,1]),
        ]:
                plane = pointNormal2Plane(p,n)
                print('plane', plane)
                p1,n1 = plane2PointNormal(plane)
                print('p', p, p1)
                print('n', n, n1)
                assert np.allclose(p, p1)
                assert np.allclose(n, n1)
        
