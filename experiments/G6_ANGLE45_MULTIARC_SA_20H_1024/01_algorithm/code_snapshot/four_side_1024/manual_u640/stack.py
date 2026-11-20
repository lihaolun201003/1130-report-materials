# -*- coding: utf-8 -*-
"""Logical layer stack for the manual-fixed-U 640-channel round.

The stack keeps the three concepts of the task strictly separate:

1. **data-source partition** ``z1`` / ``z2`` — the ``input_dataset`` column of the
   640-record CSV.  Both partitions use the same board and the same column
   coordinates, but ``z1`` sits on interface row 1 (physical height 0.0 mm) and
   ``z2`` on interface row 2 (physical height 0.5 mm).
2. **logical routing layer** ``L1..Ln`` — the layer numbers of the manual
   assignment (L1..L6) and of the automatic allocation (L7..).
3. **physical Z coordinate** — ``layer_z(layer_id, plane)``; L1 carries two
   heights (one per row), every routing layer is a single height.
"""
from __future__ import annotations

import math

from . import config as C


def transition_theta(dz_mm, radius=None):
    """Turning angle of one half of the elevation S-curve (existing D56 model)."""
    from four_side_1024.fsd25d import path3d
    return path3d.transition_theta(float(dz_mm),
                                   float(C.RADIUS_MM if radius is None else radius))


def transition_geometry(dz_mm, radius=None):
    """Elevation S-curve parameters for one height change ``dz_mm``.

    Same definition as :func:`four_side_1024.l3d.paths.transition_geometry`
    (two arcs of radius ``R``, ``theta = acos(1 - dz/(2R))``).
    """
    radius = float(C.RADIUS_MM if radius is None else radius)
    dz = abs(float(dz_mm))
    theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * radius))))
    return dict(dz_mm=dz, theta_rad=float(theta),
                footprint_mm=2.0 * radius * math.sin(theta),
                length_mm=2.0 * radius * theta)


class LayerStack:
    """Ordered L1..Ln stack built from :mod:`config`.

    ``L1`` is the interface layer and carries the two data-source rows; every
    ``L2..Lmax`` layer is one routing plane at
    ``BASE_ROUTING_Z_MM + (k - 2) * LAYER_PITCH_MM``.
    """

    def __init__(self, max_layer=C.MAX_LOGICAL_LAYERS):
        self.max_layer = int(max_layer)
        if not 2 <= self.max_layer <= C.MAX_LOGICAL_LAYERS:
            raise ValueError(f'max_layer must be in 2..{C.MAX_LOGICAL_LAYERS}')
        # validate the stack: routing planes strictly above both interface rows
        # and at least the centreline clearance apart.
        previous = max(C.Z1_MM, C.Z2_MM)
        for layer_id in range(2, self.max_layer + 1):
            height = C.layer_z(layer_id)
            if height - previous <= C.CLEARANCE_MM + 1e-12:
                raise ValueError(f'layer L{layer_id} is closer than the clearance '
                                 f'to the plane below')
            previous = height

    # -- queries ------------------------------------------------------------
    def z_for_layer(self, layer_id, row=None):
        """Physical height of ``layer_id``; ``row``/plane is needed for L1."""
        return C.layer_z(layer_id, row)

    def z_for_route_start(self, layer_id, plane):
        return C.layer_z(layer_id, plane)

    def interface_z(self, plane):
        return float(C.PLANE_Z_MM[plane])

    @property
    def routing_layer_ids(self):
        return list(range(2, self.max_layer + 1))

    @property
    def all_layer_ids(self):
        return [C.INTERFACE_LAYER_ID] + self.routing_layer_ids

    def layer_sequence_for(self, target_layer, plane):
        """Logical layer sequence ``[L1, Ltarget, L1]`` and its Z sequence."""
        target_layer = int(target_layer)
        if target_layer == C.INTERFACE_LAYER_ID:
            z0 = self.interface_z(plane)
            return [C.INTERFACE_LAYER_ID], [z0]
        z0 = self.interface_z(plane)
        z1 = C.layer_z(target_layer)
        return ([C.INTERFACE_LAYER_ID, target_layer, C.INTERFACE_LAYER_ID],
                [z0, z1, z0])

    def transition_footprint(self, target_layer, plane):
        """XY footprint of the two elevation S-curves of one lifted route."""
        target_layer = int(target_layer)
        if target_layer == C.INTERFACE_LAYER_ID:
            return 0.0
        z0 = self.interface_z(plane)
        return float(transition_geometry(C.layer_z(target_layer) - z0)['footprint_mm'])

    # -- serialisation ------------------------------------------------------
    def payload(self, max_layer=None):
        max_layer = self.max_layer if max_layer is None else int(max_layer)
        routing = list(range(2, max_layer + 1))
        all_ids = [C.INTERFACE_LAYER_ID] + routing
        allowed = {layer_id: list(all_ids) for layer_id in all_ids}
        layers = {
            str(C.INTERFACE_LAYER_ID): dict(
                layer_id=C.INTERFACE_LAYER_ID, layer_type='interface',
                physical_z_mm=None,
                interface_rows={'z1': C.Z1_MM, 'z2': C.Z2_MM},
                allowed_transitions=allowed[C.INTERFACE_LAYER_ID])}
        for layer_id in routing:
            layers[str(layer_id)] = dict(
                layer_id=int(layer_id), layer_type='routing',
                physical_z_mm=float(C.layer_z(layer_id)), interface_rows={},
                allowed_transitions=allowed[layer_id])
        return dict(
            schema='four_side_1024_v2_l3d_layer_stack_v1',
            provenance=C.PROVENANCE,
            formal_acceptance_allowed=False,
            note=C.STACK_NOTE,
            interface_layer=C.INTERFACE_LAYER_ID,
            layer_pitch_mm=C.LAYER_PITCH_MM,
            base_routing_z_mm=C.BASE_ROUTING_Z_MM,
            max_layer=int(max_layer),
            layers=layers,
            routing_heights_mm={str(layer_id): float(C.layer_z(layer_id))
                                for layer_id in routing})
