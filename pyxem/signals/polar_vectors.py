# -*- coding: utf-8 -*-
# Copyright 2016-2023 The pyXem developers
#
# This file is part of pyXem.
#
# pyXem is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyXem is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyXem.  If not, see <http://www.gnu.org/licenses/>.

from hyperspy._signals.lazy import LazySignal

from pyxem.signals.diffraction_vectors import DiffractionVectors
from pyxem.utils.labeled_vector_utils import get_three_angles
from pyxem.utils.vector_utils import to_cart_three_angles, polar_to_cartesian


class PolarVectors(DiffractionVectors):
    """
    Class for representing polar vectors in reciprocal space. The first
    two columns are the polar coordinates of the vectors, (r, theta).
    """

    _signal_dimension = 0
    _signal_type = "polar_vectors"

    def get_angles(
        self,
        intensity_index=2,
        intensity_threshold=None,
        accept_threshold=0.05,
        min_k=0.05,
        min_angle=None,
    ):
        """Calculate the angles between pairs of 3 diffraction vectors.

        Parameters
        ----------
        *args:
            Arguments to be passed to map().
        **kwargs:
            Keyword arguments to map().

        Returns
        -------
        angles : BaseSignal
            A signal with navigation dimensions as the original diffraction
            vectors containg an array of inscribed angles at each
            navigation position.

        """
        angles = self.map(
            get_three_angles,
            k_index=0,
            angle_index=1,
            intensity_index=intensity_index,
            intensity_threshold=intensity_threshold,
            accept_threshold=accept_threshold,
            min_k=min_k,
            min_angle=min_angle,
            inplace=False,
            ragged=True,
        )
        # set the column names
        col_names = ["k", "delta phi", "min-angle", "intensity", "reduced-angle"]

        # Maybe we should pass any other vector columns through?
        angles.column_names = col_names
        angles.units = ["nm^-1", "rad", "rad", "a.u.", "rad"]
        return angles

    @property
    def delta_phi(self):
        """Return the delta phi column."""
        return self.column_names[1] == "delta phi"

    def to_cartesian(self, delta_angle=None):
        """Convert the vectors to cartesian coordinates.

        Parameters
        ----------
        delta_angle : bool
            If True, the vectors are in the form (r, delta phi, min-angle).  If False,
            the vectors are in the form (r, theta).

        Returns
        -------
        DiffractionVectors
            The vectors in cartesian coordinates.
        """
        if delta_angle is None:
            delta_angle = self.delta_phi
        if delta_angle:
            cartesian_vectors = self.map(
                to_cart_three_angles,
                inplace=False,
                ragged=True,
            )
        else:
            cartesian_vectors = self.map(
                polar_to_cartesian,
                inplace=False,
                ragged=True,
            )
        cartesian_vectors.column_names = ["x", "y"]
        cartesian_vectors.units = [self.units[0], self.units[0]]
        cartesian_vectors.set_signal_type("diffraction_vectors")
        return cartesian_vectors

    def to_markers(self, delta_angle=None, cartesian=True, **kwargs):
        """Convert the vectors to markers to be plotted on a signal.

        Parameters
        ----------
        delta_angle : bool, optional
            If the vectors are polar in the form (r, theta), then this parameter should
            be set to False.  If the vectors are in the form (r, delta phi, min-angle), then
            this parameter should be set to True.  The default is None which will infer
            the format from the column names.
        cartesian : bool, optional
            If True, the vectors will be converted to cartesian coordinates before plotting.
            The default is True.
        **kwargs :
            Keyword arguments to be passed to the :class:`hyperspy.api.plot.markers.Point` class.

        Returns
        -------
        :class:`hyperspy.api.plot.markers.Point`
            A Point object containing the markers.
        """
        if cartesian:
            vectors = self.to_cartesian(delta_angle=delta_angle)
        else:
            vectors = self
        return vectors.to_markers(**kwargs)


class LazyPolarVectors(LazySignal, PolarVectors):
    pass
