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

import itertools
from functools import cached_property
from warnings import warn

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.cm import get_cmap
from scipy.spatial import distance_matrix
from sklearn.cluster import DBSCAN
import dask.array as da

from hyperspy.signals import BaseSignal, Signal1D
from hyperspy._signals.lazy import LazySignal
from hyperspy.drawing._markers.points import Points
from hyperspy.misc.utils import isiterable

from pyxem.utils.signal import (
    transfer_navigation_axes_to_signal_axes,
)
from pyxem.utils.vector_utils import (
    detector_to_fourier,
    get_npeaks,
    filter_vectors_ragged,
    filter_vectors_edge_ragged,
    filter_vectors_near_basis,
)
from pyxem.utils.expt_utils import peaks_as_gvectors
from pyxem.signals.diffraction_vectors2d import DiffractionVectors2D
from pyxem.utils._deprecated import deprecated

"""
Signal class for diffraction vectors.

There are two cases that are supported:

1. A map of diffraction vectors, which will in general be a ragged signal of
signals. It the navigation dimensions of the map and contains a signal for each
peak at every position.

2. A list of diffraction vectors with dimensions < n | 2 > where n is the
number of peaks.
"""


def _reverse_pos(peaks, ind=2):
    """Reverses the position of the peaks in the signal.

    This is useful for plotting the peaks on top of a hyperspy signal as the returned peaks are in
    reverse order to the hyperspy markers. Only points up to the index are reversed.

    Parameters
    ----------
    peaks : np.array
        Array of peaks to be reversed.
    ind : int
        The index of the position to be reversed.

    """
    new_data = peaks.copy()
    for i in range(ind):
        sl = ind - i - 1
        new_data[..., i] = peaks[..., sl]
    return new_data


class ColumnSlicer:
    def __init__(self, signal):
        self.signal = signal

    def __getitem__(self, item):
        if isinstance(item, str):
            item = self.signal.column_names.index(item)
        elif isinstance(item, int):
            pass
        else:
            raise ValueError("item must be a string or an int")

        item = [
            item,
        ]
        slic = self.signal.map(
            lambda x, item: x[..., item], item=item, inplace=False, ragged=True
        )
        slic.offsets = self.signal.offsets[item[0]]
        slic.scales = self.signal.scales[item[0]]
        return slic

class BoolSlicer:
    def __init__(self, signal):
        self.signal = signal

    def __getitem__(self, item):
        slic = self.signal.map(lambda x, item: x[item], item=item, inplace=False, ragged=True)
        return slic



class DiffractionVectors(BaseSignal):
    """Class for diffraction vectors in reciprocal space.

    Diffraction vectors are defined as the vectors from the center of the
    diffraction pattern to the diffraction peaks.

    Attributes
    ----------
    cartesian : np.array()
        Array of 3-vectors describing Cartesian coordinates associated with
        each diffraction vector.
    hkls : np.array()
        Array of Miller indices associated with each diffraction vector
        following indexation.
    """

    _signal_dimension = 0
    _signal_type = "diffraction_vectors"

    def __init__(self, *args, **kwargs):
        _scales = kwargs.pop("scales", None)
        _offsets = kwargs.pop("offsets", None)
        _detector_shape = kwargs.pop("detector_shape", None)
        _column_names = kwargs.pop("column_names", None)

        super().__init__(*args, **kwargs)

        self.metadata.add_node("VectorMetadata")
        if _scales is not None or "scales" not in self.metadata.VectorMetadata:
            self.metadata.VectorMetadata["scales"] = _scales
        if _offsets is not None or "offsets" not in self.metadata.VectorMetadata:
            self.metadata.VectorMetadata["offsets"] = _offsets
        if (
            _detector_shape is not None
            or "detector_shape" not in self.metadata.VectorMetadata
        ):
            self.metadata.VectorMetadata["detector_shape"] = _detector_shape

        if (
                _column_names is not None
                or "column_names" not in self.metadata.VectorMetadata
        ):
            self.metadata.VectorMetadata["detector_shape"] = _detector_shape
        self.cartesian = None
        self.hkls = None
        self.is_real_units = False
        self.has_intensity = False
        self.icol = ColumnSlicer(self)
        self.irow = BoolSlicer(self)

    @classmethod
    def from_peaks(cls, peaks, center=None, calibration=None, column_names=None):
        """Takes a list of peak positions (pixel coordinates) and returns
        an instance of `Diffraction2D`

        Parameters
        ----------
        peaks : Signal
            Signal containing lists (np.array) of pixel coordinates specifying
            the reflection positions
        center : np.array or None
            Diffraction pattern center in array indices.
        calibration : np.array or None
            Calibration in reciprocal Angstroms per pixels for each of the dimensions.

        Returns
        -------
        vectors : :obj:`pyxem.signals.diffraction_vectors.DiffractionVectors`
            List of diffraction vectors
        """
        if center is None and peaks.metadata.has_item("Peaks.signal_axes"):
            center = [
                -ax.offset / ax.scale for ax in peaks.metadata.Peaks.signal_axes[::-1]
            ]
        elif center is not None:
            pass  # center is already set
        else:
            raise ValueError(
                "A center and calibration must be provided unless the"
                "peaks.metadata.Peaks.signal_axes is set."
            )
        if calibration is None and peaks.metadata.has_item("Peaks.signal_axes"):
            calibration = [ax.scale for ax in peaks.metadata.Peaks.signal_axes[::-1]]
        elif calibration is not None:
            pass  # calibration is already set
        else:
            raise ValueError(
                "A center and calibration must be provided unless the"
                "peaks.metadata.Peaks.signal_axes is set."
            )

        if column_names is None and peaks.metadata.has_item("Peaks.signal_axes"):
            column_names = [ax.name for ax in peaks.metadata.Peaks.signal_axes[::-1]]
        elif column_names is not None:
            pass
        else:
            column_names = ["x", "y"]

        if not isiterable(calibration):
            calibration = [
                calibration,
                calibration,
            ]  # same calibration for both dimensions

        if isinstance(peaks, LazySignal):
            num_cols = peaks.data[(0,) * peaks.data.ndim].compute().shape[1]
        else:
            num_cols = peaks.data[(0,) * peaks.data.ndim].shape[1]
        if num_cols == len(calibration) + 1:
            # account for the intensity column
            center = list(center) + [
                0,
            ]
            calibration = list(calibration) + [
                1,
            ]
            has_intensity = True
        else:
            has_intensity = False

        if peaks.data[(0,) * peaks.data.ndim].shape[1] == len(column_names)+1:
            column_names = list(column_names) + ["intensity"]

        gvectors = peaks.map(
            lambda x, cen, cal: (x - cen) * cal,
            cal=calibration,
            cen=center,
            inplace=False,
            ragged=True,
        )
        vectors = cls(gvectors)
        if isinstance(peaks, LazySignal):
            vectors = vectors.as_lazy()
        vectors.scales = calibration
        vectors.center = center  # set calibration first
        vectors.has_intensity = has_intensity
        vectors.column_names = column_names
        return vectors


    @property
    def pixel_vectors(self):
        """Returns the diffraction vectors in pixel coordinates."""
        if self.scales is None or self.center is None:
            raise ValueError(
                "The pixel vectors cannot be calculated without a calibration."
            )
        pixels = self.map(
            lambda x, cen, cal: x / cal + self.center,
            cal=self.scales,
            cen=self.center,
            inplace=False,
            ragged=True,
        )
        return pixels.data

    @cached_property
    def num_columns(self):
        if isinstance(self.data, da.Array):
            shape = self.data[self.data.ndim * (0,)].compute().shape
        else:
            shape = self.data[self.data.ndim * (0,)].shape
        if shape is None:
            return 0
        else:
            return shape[1]

    @property
    def scales(self):
        return self.metadata.VectorMetadata["scales"]

    @scales.setter
    def scales(self, value):
        if isiterable(value) and len(value) == self.num_columns:
            self.metadata.VectorMetadata["scales"] = value
        elif isiterable(value) and len(value) != self.num_columns:
            raise ValueError(
                "The len of the scales parameter must equal the number of"
                "columns in the underlying vector data."
            )
        else:
            self.metadata.VectorMetadata["scales"] = [
                value,
            ] * self.num_columns

    @property
    def column_names(self):
        return self.metadata.VectorMetadata["column_names"]

    @column_names.setter
    def column_names(self, value):
        if len(value) != self.num_columns:
            raise ValueError(
                "The len of the scales parameter must equal the number of"
                "columns in the underlying vector data."
            )

        self.metadata.VectorMetadata["column_names"] = value
    @property
    def offsets(self):
        return self.metadata.VectorMetadata["offsets"]

    @offsets.setter
    def offsets(self, value):
        if isiterable(value) and len(value) == self.num_columns:
            self.metadata.VectorMetadata["offsets"] = value
        elif isiterable(value) and len(value) != self.num_columns:
            raise ValueError(
                "The len of the scales parameter must equal the number of"
                "columns in the underlying vector data."
            )
        else:
            self.metadata.VectorMetadata["offsets"] = [
                value,
            ] * self.num_columns

    def __lt__(self, other):
        return self.map(lambda x,other: x < other, other=other, inplace=False, ragged=True)

    def __le__(self, other):
        return self.map(lambda x,other: x <= other, other=other, inplace=False, ragged=True)

    def __gt__(self, other):
        return self.map(lambda x,other: x > other, other=other, inplace=False, ragged=True)
    def __ge__(self, other):
        return self.map(lambda x,other: x >= other, other=other, inplace=False, ragged=True)



    @property
    def center(self):
        """The center of the diffraction pattern in pixels."""
        return np.divide(self.offsets, self.scales)

    @center.setter
    def center(self, value):
        self.offsets = np.multiply(value, self.scales)

    @property
    @deprecated(
        since="0.15",
        alternative="pyxem.signals.DiffractionVectors.scales",
        removal="1.0.0",
    )
    def pixel_calibration(self):
        return self.scales

    @pixel_calibration.setter
    @deprecated(
        since="0.15",
        alternative="pyxem.signals.DiffractionVectors.scales",
        removal="1.0.0",
    )
    def pixel_calibration(self, value):
        self.scales = value

    @property
    def detector_shape(self):
        return self.metadata.VectorMetadata["detector_shape"]

    @detector_shape.setter
    def detector_shape(self, value):
        self.metadata.VectorMetadata["detector_shape"] = value

    def _get_navigation_positions(self, flatten=False, real_units=True):
        nav_indexes = np.array(
            list(np.ndindex(self.axes_manager._navigation_shape_in_array))
        )
        if not real_units:
            scales = [1 for a in self.axes_manager.navigation_axes]
            offsets = [0 for a in self.axes_manager.navigation_axes]
        else:
            scales = [a.scale for a in self.axes_manager.navigation_axes]
            offsets = [a.offset for a in self.axes_manager.navigation_axes]

        if flatten:
            real_nav = np.array(
                [
                    np.array(ind) * scales + offsets
                    for ind in np.array(list(nav_indexes))
                ]
            )
        else:
            real_nav = np.reshape(
                [
                    np.array(ind) * scales + offsets
                    for ind in np.array(list(nav_indexes))
                ],
                self.axes_manager._navigation_shape_in_array + (-1,),
            )
        return real_nav

    def flatten_diffraction_vectors(
        self,
        real_units=True,
    ):
        """Flattens the diffraction vectors into a `DiffractionVector2D` object.

        Each navigation axis is transformed into a vector defined by the scale and offset.
        This method allows purely vector based actions like filtering or determining unique
        values.

        Parameters
        ----------
        real_units: bool
            If the navigation dimension should be flattened based on the pixel position
            or the real value as determined by the scale and offset.
        """
        nav_positions = self._get_navigation_positions(
            flatten=True, real_units=real_units
        )

        vectors = np.vstack(
            [
                np.hstack([np.tile(nav_pos, (len(self.data[ind]), 1)), self.data[ind]])
                for ind, nav_pos in zip(np.ndindex(self.data.shape), nav_positions)
            ]
        )

        if real_units:
            scales = [a.scale for a in self.axes_manager.navigation_axes]
            offsets = [a.offset for a in self.axes_manager.navigation_axes]
        else:
            scales = [1 for a in self.axes_manager.navigation_axes]
            offsets = [0 for a in self.axes_manager.navigation_axes]

        if self.offsets is None:
            column_offsets = [
                None,
            ] * (vectors.shape[1] - len(self.axes_manager.navigation_axes))
        else:
            column_offsets = self.offsets

        if self.scales is None:
            column_scale = [
                None,
            ] * (vectors.shape[1] - len(self.axes_manager.navigation_axes))
        else:
            column_scale = self.scales

        column_offsets = np.append(column_offsets, offsets)
        column_scale = np.append(column_scale, scales)

        return DiffractionVectors2D(
            vectors, column_offsets=column_offsets, column_scale=column_scale
        )

    def plot_diffraction_vectors(
        self,
        xlim=1.0,
        ylim=1.0,
        unique_vectors=None,
        distance_threshold=0.01,
        method="distance_comparison",
        min_samples=1,
        image_to_plot_on=None,
        image_cmap="gray",
        plot_label_colors=False,
        distance_threshold_all=0.005,
    ):  # pragma: no cover
        """Plot the unique diffraction vectors.

        Parameters
        ----------
        xlim : float
            The maximum x coordinate to be plotted.
        ylim : float
            The maximum y coordinate in reciprocal Angstroms to be plotted.
        unique_vectors : DiffractionVectors, optional
            The unique vectors to be plotted (optional). If not given, the
            unique vectors will be found by get_unique_vectors.
        distance_threshold : float, optional
            The minimum distance in reciprocal Angstroms between diffraction
            vectors for them to be considered unique diffraction vectors.
            Will be passed to get_unique_vectors if no unique vectors are
            given.
        method : str
            The method to use to determine unique vectors, if not given.
            Valid methods are 'strict', 'distance_comparison' and 'DBSCAN'.
            'strict' returns all vectors that are strictly unique and
            corresponds to distance_threshold=0.
            'distance_comparison' checks the distance between vectors to
            determine if some should belong to the same unique vector,
            and if so, the unique vector is iteratively updated to the
            average value.
            'DBSCAN' relies on the DBSCAN [1] clustering algorithm, and
            uses the Eucledian distance metric.
        min_samples : int, optional
            The minimum number of not identical vectors within one cluster
            for it to be considered a core sample, i.e. to not be considered
            noise. Will be passed to get_unique_vectors if no unique vectors
            are given. Only used if method=='DBSCAN'.
        image_to_plot_on : BaseSignal, optional
            If provided, the vectors will be plotted on top of this image.
            The image must be calibrated in terms of offset and scale.
        image_cmap : str, optional
            The colormap to plot the image in.
        plot_label_colors : bool, optional
            If True (default is False), also the vectors contained within each
            cluster will be plotted, with colors according to their
            cluster membership. If True, the unique vectors will be
            calculated by get_unique_vectors. Requires on method=='DBSCAN'.
        distance_threshold_all : float, optional
            The minimum distance, in calibrated units, between diffraction
            vectors inside one cluster for them to be plotted. Only used if
            plot_label_colors is True and requires method=='DBSCAN'.

        Returns
        -------
        fig : matplotlib figure
            The plot as a matplotlib figure.

        """
        fig = plt.figure()
        ax = fig.add_subplot(111)
        offset, scale = 0.0, 1.0
        if image_to_plot_on is not None:
            offset = image_to_plot_on.axes_manager[-1].offset
            scale = image_to_plot_on.axes_manager[-1].scale
            ax.imshow(image_to_plot_on, cmap=image_cmap)
        else:
            ax.set_xlim(-xlim, xlim)
            ax.set_ylim(ylim, -ylim)
            ax.set_aspect("equal")

        if plot_label_colors is True and method == "DBSCAN":
            clusters = self.get_unique_vectors(
                distance_threshold,
                method="DBSCAN",
                min_samples=min_samples,
                return_clusters=True,
            )[1]
            labs = clusters.labels_[clusters.core_sample_indices_]
            # Get all vectors from the clustering not considered noise
            cores = clusters.components_
            if cores.size == 0:
                warn(
                    "No clusters were found. Check parameters, or "
                    "use plot_label_colors=False."
                )
            else:
                peaks = DiffractionVectors(cores)
                peaks.transpose(signal_axes=1)
                # Since this original number of vectors can be huge, we
                # find a reduced number of vectors that should be plotted, by
                # running a new clustering on all the vectors not considered
                # noise, considering distance_threshold_all.
                peaks = peaks.get_unique_vectors(
                    distance_threshold_all, min_samples=1, return_clusters=False
                )
                peaks_all_len = peaks.data.shape[0]
                labels_to_plot = np.zeros(peaks_all_len)
                peaks_to_plot = np.zeros((peaks_all_len, 2))
                # Find the labels of each of the peaks to plot by referring back
                # to the list of labels for the original vectors.
                for n, peak in zip(np.arange(peaks_all_len), peaks):
                    index = distance_matrix([peak.data], cores).argmin()
                    peaks_to_plot[n] = cores[index]
                    labels_to_plot[n] = labs[index]
                # Assign a color value to each label, and shuffle these so that
                # adjacent clusters hopefully get distinct colors.
                cmap_lab = get_cmap("gist_rainbow")
                lab_values_shuffled = np.arange(np.max(labels_to_plot) + 1)
                np.random.shuffle(lab_values_shuffled)
                labels_steps = np.array(
                    list(map(lambda n: lab_values_shuffled[int(n)], labels_to_plot))
                )
                labels_steps = labels_steps / (np.max(labels_to_plot) + 1)
                # Plot all peaks
                for lab, peak in zip(labels_steps, peaks_to_plot):
                    ax.plot(
                        (peak[0] - offset) / scale,
                        (peak[1] - offset) / scale,
                        ".",
                        color=cmap_lab(lab),
                    )
        if unique_vectors is None:
            unique_vectors = self.get_unique_vectors(
                distance_threshold, method=method, min_samples=min_samples
            )
        # Plot the unique vectors
        ax.plot(
            (unique_vectors.data.T[1] - offset) / scale,
            (unique_vectors.data.T[0] - offset) / scale,
            "kx",
        )
        plt.tight_layout()
        plt.axis("off")
        return fig

    def to_markers(self, **kwargs):
        new = self.map(reverse_pos, inplace=False, ragged=True)
        return Points(offsets=new.data.T, **kwargs)

    @deprecated(
        since="0.17.0",
        removal="1.0.0",
        alternative="pyxem.signals.DiffractionVectors.to_markers",
    )
    def plot_diffraction_vectors_on_signal(self, signal, *args, **kwargs):
        """Plot the diffraction vectors on a signal.

        Parameters
        ----------
        signal : ElectronDiffraction2D
            The ElectronDiffraction2D signal object on which to plot the peaks.
            This signal must have the same navigation dimensions as the peaks.
        *args :
            Arguments passed to signal.plot()
        **kwargs :
            Keyword arguments passed to signal.plot()
        """
        signal.plot(*args, **kwargs)
        marker = self.to_markers(
            color=[
                "red",
            ]
        )
        signal.add_marker(marker, plot_marker=True, permanent=False)

    def get_magnitudes(self, *args, **kwargs):
        """Calculate the magnitude of diffraction vectors.

        Parameters
        ----------
        *args:
            Arguments to be passed to map().
        **kwargs:
            Keyword arguments to map().

        Returns
        -------
        magnitudes : BaseSignal
            A signal with navigation dimensions as the original diffraction
            vectors containg an array of gvector magnitudes at each
            navigation position.

        """
        magnitudes = self.map(
            np.linalg.norm, inplace=False, axis=-1, ragged=True, *args, **kwargs
        )

        return magnitudes

    def get_magnitude_histogram(self, bins, *args, **kwargs):
        """Obtain a histogram of gvector magnitudes.

        Parameters
        ----------
        bins : numpy array
            The bins to be used to generate the histogram.
        *args:
            Arguments to get_magnitudes().
        **kwargs:
            Keyword arguments to get_magnitudes().

        Returns
        -------
        ghis : Signal1D
            Histogram of gvector magnitudes.

        """
        gmags = self.get_magnitudes(*args, **kwargs)

        if len(self.axes_manager.signal_axes) == 0:
            glist = []
            for i in gmags._iterate_signal():
                for j in np.arange(len(i[0])):
                    glist.append(i[0][j])
            gs = np.asarray(glist)
            gsig = Signal1D(gs)
            ghis = gsig.get_histogram(bins=bins)

        else:
            ghis = gmags.get_histogram(bins=bins)

        ghis.axes_manager.signal_axes[0].name = "k"
        ghis.axes_manager.signal_axes[0].units = "$A^{-1}$"

        return ghis

    def get_unique_vectors(self, *args, **kwargs):
        """Returns diffraction vectors considered unique by:
        strict comparison, distance comparison with a specified
        threshold, or by clustering using DBSCAN [1].

        Parameters
        ----------
        distance_threshold : float
            The minimum distance between diffraction vectors for them to
            be considered unique diffraction vectors. If
            distance_threshold==0, the unique vectors will be determined
            by strict comparison.
        method : str
            The method to use to determine unique vectors. Valid methods
            are 'strict', 'distance_comparison' and 'DBSCAN'.
            'strict' returns all vectors that are strictly unique and
            corresponds to distance_threshold=0.
            'distance_comparison' checks the distance between vectors to
            determine if some should belong to the same unique vector,
            and if so, the unique vector is iteratively updated to the
            average value.
            'DBSCAN' relies on the DBSCAN [1] clustering algorithm, and
            uses the Eucledian distance metric.
        min_samples : int, optional
            The minimum number of not strictly identical vectors within
            one cluster for the cluster to be considered a core sample,
            i.e. to not be considered noise. Only used for method='DBSCAN'.
        return_clusters : bool, optional
            If True (False is default), the DBSCAN clustering result is
            returned. Only used for method='DBSCAN'.

        References
        ----------
        [1] https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html

        Returns
        -------
        unique_peaks : DiffractionVectors
            The unique diffraction vectors.
        clusters : DBSCAN
            The results from the clustering, given as class DBSCAN.
            Only returned if method='DBSCAN' and return_clusters=True.
        """
        real_units = self.is_real_units
        flattened_vectors = self.flatten_diffraction_vectors(real_units=real_units)

        return flattened_vectors.get_unique_vectors(*args, **kwargs)

    def filter_magnitude(self, min_magnitude, max_magnitude, *args, **kwargs):
        """Filter the diffraction vectors to accept only those with a magnitude
        within a user specified range.

        Parameters
        ----------
        min_magnitude : float
            Minimum allowed vector magnitude.
        max_magnitude : float
            Maximum allowed vector magnitude.
        *args:
            Arguments to be passed to map().
        **kwargs:
            Keyword arguments to map().

        Returns
        -------
        filtered_vectors : DiffractionVectors
            Diffraction vectors within allowed magnitude tolerances.
        """
        # If ragged the signal axes will not be defined
        filtered_vectors = self.map(
            filter_vectors_ragged,
            min_magnitude=min_magnitude,
            max_magnitude=max_magnitude,
            inplace=False,
            ragged=True,
            *args,
            **kwargs
        )
        return filtered_vectors

    def filter_basis(self, basis, distance=0.5, **kwargs):
        """
        Filter vectors to only the set of vectors which is close
        to a basis set of vectors. If there is no vector within the `distance`
        parameter of the vector np.`nan` will be returned.

        Parameters
        ----------
        basis: array-like or BaseSignal
            The set of vectors to be compared.
        distance: float
            The distance between vectors and basis which detemine if the vector
            is associated with the basis vector. If no vector is inside the
            distance np.nan will be returned.
        kwargs: dict
            Any other parameters passed to the `hyperspy.BaseSignal.Map` function.
        Returns
        -------
        vectors: DiffractionVectors or DiffractionVectors2D
            The filtered list of diffraction vectors.  If basis is
            an instance of hyperspy.Signals.BaseSignal and instance of the
            DiffractionVectors class will be returned otherwise an instance
            of the DiffractionVectors2D class will be returned.
        """
        ragged = isinstance(basis, BaseSignal) and (
            basis.axes_manager.navigation_shape == self.axes_manager.navigation_shape
        )
        kwargs["ragged"] = ragged
        if not ragged:
            kwargs["output_signal_size"] = np.shape(basis)
            kwargs["output_dtype"] = float

        filtered_vectors = self.map(
            filter_vectors_near_basis, basis=basis, distance=distance, **kwargs
        )
        return filtered_vectors

    def filter_detector_edge(self, exclude_width, *args, **kwargs):
        """Filter the diffraction vectors to accept only those not within a
        user specified proximity to the detector edge.

        Parameters
        ----------
        exclude_width : int
            The width of the region adjacent to the detector edge from which
            vectors will be excluded.
        *args:
            Arguments to be passed to map().
        **kwargs:
            Keyword arguments to map().

        Returns
        -------
        filtered_vectors : DiffractionVectors
            Diffraction vectors within allowed detector region.
        """
        x_threshold = (
            self.scales[0] * (self.detector_shape[0] / 2)
            - self.scales[0] * exclude_width
        )
        y_threshold = (
            self.scales[1] * (self.detector_shape[1] / 2)
            - self.scales[1] * exclude_width
        )
        filtered_vectors = self.map(
            filter_vectors_edge_ragged,
            x_threshold=x_threshold,
            y_threshold=y_threshold,
            inplace=False,
            ragged=True,
            *args,
            **kwargs
        )
        return filtered_vectors

    def get_diffracting_pixels_map(self, in_range=None, binary=False):
        """Map of the number of vectors at each navigation position.

        Parameters
        ----------
        in_range : tuple
            Tuple (min_magnitude, max_magnitude) the minimum and maximum
            magnitude of vectors to be used to form the map.
        binary : boolean
            If True a binary image with diffracting pixels taking value == 1 is
            returned.

        Returns
        -------
        crystim : Signal2D
            2D map of diffracting pixels.
        """
        if in_range:
            filtered = self.filter_magnitude(in_range[0], in_range[1])
            xim = filtered.map(get_npeaks, inplace=False, ragged=False).as_signal2D(
                (0, 1)
            )
        else:
            xim = self.map(get_npeaks, inplace=False, ragged=False).as_signal2D((0, 1))
        # Make binary if specified
        if binary is True:
            xim = xim >= 1.0
        # Set properties
        xim = transfer_navigation_axes_to_signal_axes(xim, self)
        xim.change_dtype("float")
        xim.set_signal_type("signal2d")
        xim.metadata.General.title = "Diffracting Pixels Map"

        return xim

    def calculate_cartesian_coordinates(
        self, accelerating_voltage, camera_length, *args, **kwargs
    ):
        """Get cartesian coordinates of the diffraction vectors.

        Parameters
        ----------
        accelerating_voltage : float
            The acceleration voltage with which the data was acquired.
        camera_length : float
            The camera length in meters.
        """
        # Imported here to avoid circular dependency
        from diffsims.utils.sim_utils import get_electron_wavelength

        wavelength = get_electron_wavelength(accelerating_voltage)
        self.cartesian = self.map(
            detector_to_fourier,
            wavelength=wavelength,
            camera_length=camera_length * 1e10,
            inplace=False,
            ragged=True,
            *args,
            **kwargs
        )


class LazyDiffractionVectors(LazySignal, DiffractionVectors):
    pass
