# -*- coding: utf-8 -*-
"""XYZ joint router: true simultaneous XY+Z path search for the 1024-channel
three-dimensional optical waveguide router.

Public modules
--------------
``route_builder``    exact R15 route (re)construction (leads + fanout + body)
``world_adapter``    incremental exact world (D56 per physical height + true 3D)
``local_reroute``    local XY+Z candidate search / transactional reroute
``optimizer``        global optimisation loop and artifact writing
``paths``            run-directory layout and IO helpers
``motion_primitives``exact R15 line / arc / S-curve primitives and chains
``route_state``      heading-aware 3D search state
``corridor_search``  coarse XY corridor search on one physical height
``xyz_search``       joint XY+Z search over height plans and corridors
``manual_policy``    G1/G2/G3 manual-U contracts
``validate_xyz``     independent validation wrapper (manual policies)
``preflight_audit``  baseline consistency audit
"""
from . import paths  # noqa: F401
from . import route_builder  # noqa: F401
from . import world_adapter  # noqa: F401
from . import local_reroute  # noqa: F401
from . import optimizer  # noqa: F401

__all__ = ['paths', 'route_builder', 'world_adapter', 'local_reroute',
           'optimizer']
