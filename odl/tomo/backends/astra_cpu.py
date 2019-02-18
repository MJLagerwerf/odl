# Copyright 2014-2019 The ODL contributors
#
# This file is part of ODL.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at https://mozilla.org/MPL/2.0/.

"""Backend for ASTRA using CPU."""

from __future__ import absolute_import, division, print_function

import numpy as np

from odl.discr import DiscreteLp, DiscreteLpElement
from odl.tomo.backends.astra_setup import (
    astra_algorithm, astra_data, astra_projection_geometry, astra_projector,
    astra_volume_geometry)
from odl.tomo.geometry import (
    DivergentBeamGeometry, Geometry, ParallelBeamGeometry)
from odl.util import writable_array

try:
    import astra
except ImportError:
    pass


__all__ = ('astra_cpu_forward_projector', 'astra_cpu_back_projector')


# TODO: is magnification scaling at the right place?


def _default_proj_type(geom):
    """Return the default projector type for a given geometry."""
    if isinstance(geom, ParallelBeamGeometry):
        return 'line' if geom.ndim == 2 else 'linear3d'
    elif isinstance(geom, DivergentBeamGeometry):
        return 'line_fanflat' if geom.ndim == 2 else 'linearcone'
    else:
        raise TypeError(
            'no default exists for {}, `proj_type` must be given explicitly'
            ''.format(type(geom))
        )


def astra_cpu_forward_projector(vol_data, geometry, proj_space, out=None,
                                proj_type=None):
    """Run an ASTRA forward projection on the given data using the CPU.

    Parameters
    ----------
    vol_data : `DiscreteLpElement`
        Volume data to which the forward projector is applied.
    geometry : `Geometry`
        Geometry defining the tomographic setup.
    proj_space : `DiscreteLp`
        Space to which the calling operator maps.
    out : ``proj_space`` element, optional
        Element of the projection space to which the result is written. If
        ``None``, an element in ``proj_space`` is created.
    proj_type : str, optional
        Type of projector that should be used. See `the ASTRA documentation
        <http://www.astra-toolbox.com/docs/proj2d.html>`_ for details.
        By default, a suitable projector type for the given geometry is
        selected.

    Returns
    -------
    out : ``proj_space`` element
        Projection data resulting from the application of the projector.
        If ``out`` was provided, the returned object is a reference to it.
    """
    if not isinstance(vol_data, DiscreteLpElement):
        raise TypeError('volume data {!r} is not a `DiscreteLpElement` '
                        'instance.'.format(vol_data))
    if vol_data.space.impl != 'numpy':
        raise TypeError("`vol_data.space.impl` must be 'numpy', got {!r}"
                        "".format(vol_data.space.impl))
    if not isinstance(geometry, Geometry):
        raise TypeError('geometry  {!r} is not a Geometry instance'
                        ''.format(geometry))
    if not isinstance(proj_space, DiscreteLp):
        raise TypeError('`proj_space` {!r} is not a DiscreteLp '
                        'instance.'.format(proj_space))
    if proj_space.impl != 'numpy':
        raise TypeError("`proj_space.impl` must be 'numpy', got {!r}"
                        "".format(proj_space.impl))
    if vol_data.ndim != geometry.ndim:
        raise ValueError('dimensions {} of volume data and {} of geometry '
                         'do not match'
                         ''.format(vol_data.ndim, geometry.ndim))
    if out is None:
        out = proj_space.element()
    else:
        if out not in proj_space:
            raise TypeError('`out` {} is neither None nor a '
                            'DiscreteLpElement instance'.format(out))

    ndim = vol_data.ndim

    # Create astra geometries
    vol_geom = astra_volume_geometry(vol_data.space)
    proj_geom = astra_projection_geometry(geometry)

    # Create projector
    if proj_type is None:
        proj_type = _default_proj_type(geometry)
    proj_id = astra_projector(proj_type, vol_geom, proj_geom, ndim)

    # Create ASTRA data structures
    vol_data_arr = np.asarray(vol_data)
    vol_id = astra_data(vol_geom, datatype='volume', data=vol_data_arr,
                        allow_copy=True)

    with writable_array(out, dtype='float32', order='C') as out_arr:
        sino_id = astra_data(proj_geom, datatype='projection', data=out_arr,
                             ndim=proj_space.ndim)

        # Create algorithm
        algo_id = astra_algorithm('forward', ndim, vol_id, sino_id, proj_id,
                                  impl='cpu')

        # Run algorithm
        astra.algorithm.run(algo_id)

    # Delete ASTRA objects
    astra.algorithm.delete(algo_id)
    astra.data2d.delete((vol_id, sino_id))
    astra.projector.delete(proj_id)

    return out


def astra_cpu_back_projector(proj_data, geometry, reco_space, out=None,
                             proj_type=None):
    """Run an ASTRA back-projection on the given data using the CPU.

    Parameters
    ----------
    proj_data : `DiscreteLpElement`
        Projection data to which the back-projector is applied.
    geometry : `Geometry`
        Geometry defining the tomographic setup.
    reco_space : `DiscreteLp`
        Space to which the calling operator maps.
    out : ``reco_space`` element, optional
        Element of the reconstruction space to which the result is written.
        If ``None``, an element in ``reco_space`` is created.
    proj_type : str, optional
        Type of projector that should be used. See `the ASTRA documentation
        <http://www.astra-toolbox.com/docs/proj2d.html>`_ for details.
        By default, a suitable projector type for the given geometry is
        selected.

    Returns
    -------
    out : ``reco_space`` element
        Reconstruction data resulting from the application of the backward
        projector. If ``out`` was provided, the returned object is a
        reference to it.
    """
    if not isinstance(proj_data, DiscreteLpElement):
        raise TypeError('projection data {!r} is not a DiscreteLpElement '
                        'instance'.format(proj_data))
    if proj_data.space.impl != 'numpy':
        raise TypeError('`proj_data` must be a `numpy.ndarray` based, '
                        "container got `impl` {!r}"
                        "".format(proj_data.space.impl))
    if not isinstance(geometry, Geometry):
        raise TypeError('geometry  {!r} is not a Geometry instance'
                        ''.format(geometry))
    if not isinstance(reco_space, DiscreteLp):
        raise TypeError('reconstruction space {!r} is not a DiscreteLp '
                        'instance'.format(reco_space))
    if reco_space.impl != 'numpy':
        raise TypeError("`reco_space.impl` must be 'numpy', got {!r}"
                        "".format(reco_space.impl))
    if reco_space.ndim != geometry.ndim:
        raise ValueError('dimensions {} of reconstruction space and {} of '
                         'geometry do not match'.format(
                             reco_space.ndim, geometry.ndim))
    if out is None:
        out = reco_space.element()
    else:
        if out not in reco_space:
            raise TypeError('`out` {} is neither None nor a '
                            'DiscreteLpElement instance'.format(out))

    ndim = proj_data.ndim

    # Create astra geometries
    vol_geom = astra_volume_geometry(reco_space)
    proj_geom = astra_projection_geometry(geometry)

    # Create ASTRA data structure
    sino_id = astra_data(proj_geom, datatype='projection', data=proj_data,
                         allow_copy=True)

    # Create projector
    if proj_type is None:
        proj_type = _default_proj_type(geometry)
    proj_id = astra_projector(proj_type, vol_geom, proj_geom, ndim)

    # Convert out to correct dtype and order if needed.
    with writable_array(out, dtype='float32', order='C') as out_arr:
        vol_id = astra_data(vol_geom, datatype='volume', data=out_arr,
                            ndim=reco_space.ndim)
        # Create algorithm
        algo_id = astra_algorithm('backward', ndim, vol_id, sino_id, proj_id,
                                  impl='cpu')

        # Run algorithm
        astra.algorithm.run(algo_id)

    # Weight the adjoint by appropriate weights
    scaling_factor = float(proj_data.space.weighting.const)
    scaling_factor /= float(reco_space.weighting.const)

    out *= scaling_factor

    # Delete ASTRA objects
    astra.algorithm.delete(algo_id)
    astra.data2d.delete((vol_id, sino_id))
    astra.projector.delete(proj_id)

    return out


if __name__ == '__main__':
    from odl.util.testutils import run_doctests
    run_doctests()
