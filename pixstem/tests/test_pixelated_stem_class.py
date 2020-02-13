import pytest
import numpy as np
from numpy.random import randint
import dask.array as da
from skimage import morphology
from hyperspy.signals import Signal2D
from pixstem.pixelated_stem_class import PixelatedSTEM
from pixstem.pixelated_stem_class import LazyPixelatedSTEM
import pixstem.ransac_ellipse_tools as ret
import pixstem.make_diffraction_test_data as mdtd
import pixstem.dummy_data as dd
import pixstem.dask_test_data as dtd


class TestPixelatedStem:

    def test_create(self):
        array0 = np.zeros(shape=(10, 10, 10, 10))
        s0 = PixelatedSTEM(array0)
        assert array0.shape == s0.axes_manager.shape

        # This should fail due to PixelatedSTEM inheriting
        # signal2D, i.e. the data has to be at least
        # 2-dimensions
        with pytest.raises(ValueError):
            PixelatedSTEM(np.zeros(10))

        array1 = np.zeros(shape=(10, 10))
        s1 = PixelatedSTEM(array1)
        assert array1.shape == s1.axes_manager.shape


class TestPlotting:

    def test_simple_plot(self):
        s = PixelatedSTEM(np.zeros(shape=(3, 4, 6, 10)))
        s.plot()

    def test_navigation_signal_plot(self):
        s = PixelatedSTEM(np.zeros(shape=(3, 4, 6, 10)))
        s_nav = Signal2D(np.zeros((3, 4)))
        s.navigation_signal = s_nav
        s.plot()

    def test_navigation_signal_plot_argument(self):
        s = PixelatedSTEM(np.zeros(shape=(3, 4, 6, 10)))
        s_nav = Signal2D(np.zeros((3, 4)))
        s.plot(navigator=s_nav)


class TestPixelatedStemFlipDiffraction:

    def test_flip_x(self):
        array = np.zeros(shape=(3, 4, 6, 10))
        array[:, :, :, 5:] = 1
        s = PixelatedSTEM(array)
        assert (s.data[:, :, :, 5:] == 1).all()
        s_flip = s.flip_diffraction_x()
        assert (s_flip.data[:, :, :, 5:] == 0).all()
        assert (s_flip.data[:, :, :, :5] == 1).all()

    def test_flip_y(self):
        array = np.zeros(shape=(3, 4, 6, 10))
        array[:, :, 3:, :] = 1
        s = PixelatedSTEM(array)
        assert (s.data[:, :, 3:, :] == 1).all()
        s_flip = s.flip_diffraction_y()
        assert (s_flip.data[:, :, 3:, :] == 0).all()
        assert (s_flip.data[:, :, :3, :] == 1).all()


class TestAddPeakArrayAsMarkers:

    def test_simple(self):
        s = PixelatedSTEM(np.zeros((2, 3, 100, 100)))
        peak_array = np.empty((2, 3), dtype=np.object)
        for index in np.ndindex(peak_array.shape):
            islice = np.s_[index]
            peak_array[islice] = np.random.randint(20, 80, (100, 2))
        s.add_peak_array_as_markers(peak_array)

    def test_color(self):
        s = PixelatedSTEM(np.zeros((2, 3, 100, 100)))
        peak_array = np.empty((2, 3), dtype=np.object)
        for index in np.ndindex(peak_array.shape):
            islice = np.s_[index]
            peak_array[islice] = np.random.randint(20, 80, (100, 2))
        s.add_peak_array_as_markers(peak_array, color='blue')
        marker0 = list(s.metadata.Markers)[9][1]
        assert marker0.marker_properties['color'] == 'blue'

    def test_size(self):
        s = PixelatedSTEM(np.zeros((2, 3, 100, 100)))
        peak_array = np.empty((2, 3), dtype=np.object)
        for index in np.ndindex(peak_array.shape):
            islice = np.s_[index]
            peak_array[islice] = np.random.randint(20, 80, (100, 2))
        s.add_peak_array_as_markers(peak_array, size=13)
        marker0 = list(s.metadata.Markers)[9][1]
        assert marker0.get_data_position('size') == 13

    def test_3d_nav_dims(self):
        s = PixelatedSTEM(np.zeros((2, 3, 4, 100, 100)))
        peak_array = np.empty((2, 3, 4), dtype=np.object)
        for index in np.ndindex(peak_array.shape):
            islice = np.s_[index]
            peak_array[islice] = np.random.randint(20, 80, (100, 2))
        s.add_peak_array_as_markers(peak_array)
        marker = list(s.metadata.Markers)[0][1]
        assert marker.data['x1'][()].shape == (2, 3, 4)

    def test_1d_nav_dims(self):
        nav_dim = 3
        s = PixelatedSTEM(np.zeros((nav_dim, 100, 100)))
        peak_array = np.empty(nav_dim, dtype=np.object)
        for index in np.ndindex(peak_array.shape):
            islice = np.s_[index]
            peak_array[islice] = np.random.randint(20, 80, (100, 2))
        s.add_peak_array_as_markers(peak_array)
        marker = list(s.metadata.Markers)[0][1]
        assert marker.data['x1'][()].shape == (3, )

    def test_0d_nav_dims(self):
        s = PixelatedSTEM(np.zeros((100, 100)))
        peak_array = np.random.randint(20, 80, size=(1, 1, 100, 2))
        s.add_peak_array_as_markers(peak_array)
        marker = list(s.metadata.Markers)[0][1]
        assert marker.data['x1'].shape == ()


class TestAddEllipseArrayAsMarkers:

    def test_simple(self):
        s, parray = dd.get_simple_ellipse_signal_peak_array()
        ellipse_array, inlier_array = ret.get_ellipse_model_ransac(
                parray, xf=95, yf=95, rf_lim=20, semi_len_min=40,
                semi_len_max=100, semi_len_ratio_lim=5, max_trails=50)
        s.add_ellipse_array_as_markers(
                ellipse_array, inlier_array=inlier_array, peak_array=parray)

    def test_only_ellipse_array(self):
        s, parray = dd.get_simple_ellipse_signal_peak_array()
        s1 = s.deepcopy()
        ellipse_array, inlier_array = ret.get_ellipse_model_ransac(
                parray, xf=95, yf=95, rf_lim=20, semi_len_min=40,
                semi_len_max=100, semi_len_ratio_lim=5, max_trails=50)
        s.add_ellipse_array_as_markers(ellipse_array)
        s1.add_ellipse_array_as_markers(
                ellipse_array, inlier_array=inlier_array, peak_array=parray)
        assert len(list(s.metadata.Markers)) < len(list(s1.metadata.Markers))


class TestPixelatedSTEMThresholdAndMask:

    @pytest.mark.parametrize(
            "shape", [(9, 9, 9, 9), (4, 8, 6, 3), (6, 3, 2, 5)])
    def test_no_change(self, shape):
        s = PixelatedSTEM(np.zeros(shape))
        s1 = s.threshold_and_mask()
        assert (s.data == s1.data).all()

    @pytest.mark.parametrize("mask", [(3, 5, 1), (6, 8, 1), (4, 6, 1)])
    def test_mask(self, mask):
        s = PixelatedSTEM(np.ones((10, 10, 10, 10)))
        s1 = s.threshold_and_mask(mask=mask)
        slice0 = np.s_[:, :, mask[1]-mask[2]:mask[1]+mask[2]+1, mask[0]]
        assert (s1.data[slice0] == 1.).all()
        slice1 = np.s_[:, :, mask[1], mask[0]-mask[2]:mask[0]+mask[2]+1]
        assert (s1.data[slice1] == 1.).all()
        s1.data[slice0] = 0
        s1.data[slice1] = 0
        assert (s1.data == 0).all()

    @pytest.mark.parametrize("x, y", [(3, 5), (7, 5), (5, 2)])
    def test_threshold(self, x, y):
        s = PixelatedSTEM(np.random.randint(0, 10, size=(10, 10, 10, 10)))
        s.data[:, :, x, y] = 1000000
        s1 = s.threshold_and_mask(threshold=1)
        assert (s1.data[:, :, x, y] == 1.).all()
        s1.data[:, :, x, y] = 0
        assert (s1.data == 0).all()

    def test_threshold_mask(self):
        s = PixelatedSTEM(np.zeros((12, 11, 13, 10)))
        s.data[:, :, 1, 2] = 1000000
        s.data[:, :, 8, 6] = 10
        s1 = s.threshold_and_mask(threshold=1)
        assert (s1.data[:, :, 1, 2] == 1.).all()
        s1.data[:, :, 1, 2] = 0
        assert (s1.data == 0).all()

        s2 = s.threshold_and_mask(threshold=1, mask=(6, 8, 1))
        assert (s2.data[:, :, 8, 6] == 1.).all()
        s2.data[:, :, 8, 6] = 0
        assert (s2.data == 0).all()

    def test_lazy_exception(self):
        s = dd.get_disk_shift_simple_test_signal(lazy=True)
        with pytest.raises(NotImplementedError):
            s.threshold_and_mask()


class TestFindHotPixels:

    def test_2d(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_2d())
        s_hot_pixels = s.find_hot_pixels()
        assert s_hot_pixels._lazy
        s_hot_pixels.compute()
        assert s_hot_pixels.data.shape == s.data.shape
        assert s_hot_pixels.data[21, 11]
        assert s_hot_pixels.data[5, 38]
        s_hot_pixels.data[21, 11] = False
        s_hot_pixels.data[5, 38] = False
        assert not s_hot_pixels.data.any()

    def test_3d(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_3d())
        s_hot_pixels = s.find_hot_pixels()
        assert s_hot_pixels.data.shape == s.data.shape

    def test_4d(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_4d())
        s_hot_pixels = s.find_hot_pixels()
        assert s_hot_pixels.data.shape == s.data.shape

    def test_lazy_result(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_4d())
        s_hot_pixels = s.find_hot_pixels(lazy_result=True)
        assert s_hot_pixels._lazy

    def test_threshold_multiplier(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_4d())
        s_hot_pixels = s.find_hot_pixels(threshold_multiplier=1000000)
        assert not s_hot_pixels.data.any()

    def test_mask_array(self):
        s = LazyPixelatedSTEM(dtd._get_hot_pixel_test_data_2d())
        mask_array = np.ones_like(s.data, dtype=np.bool)
        s_hot_pixels = s.find_hot_pixels(mask_array=mask_array)
        assert not s_hot_pixels.data.any()

    def test_non_lazy_signal(self):
        data = dtd._get_hot_pixel_test_data_2d()
        s = PixelatedSTEM(data.compute())
        s_hot_pixels = s.find_hot_pixels()
        s_hot_pixels.compute()
        assert s_hot_pixels.data.shape == s.data.shape
        assert s_hot_pixels.data[21, 11]
        assert s_hot_pixels.data[5, 38]
        s_hot_pixels.data[21, 11] = False
        s_hot_pixels.data[5, 38] = False
        assert not s_hot_pixels.data.any()


class TestFindDeadPixels:

    def test_2d(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_2d())
        s_dead_pixels = s.find_dead_pixels()
        assert not s_dead_pixels._lazy
        assert s_dead_pixels.data.shape == s.data.shape
        assert s_dead_pixels.data[14, 42]
        assert s_dead_pixels.data[2, 12]
        s_dead_pixels.data[14, 42] = False
        s_dead_pixels.data[2, 12] = False
        assert not s_dead_pixels.data.any()

    def test_3d(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_3d())
        s_dead_pixels = s.find_dead_pixels()
        assert s_dead_pixels.data.shape == s.data.shape[-2:]

    def test_4d(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_4d())
        s_dead_pixels = s.find_dead_pixels()
        assert s_dead_pixels.data.shape == s.data.shape[-2:]

    def test_lazy_result(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_2d())
        s_dead_pixels = s.find_dead_pixels(lazy_result=True)
        assert s_dead_pixels._lazy

    def test_dead_pixel_value(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_2d())
        s_dead_pixels = s.find_dead_pixels(dead_pixel_value=-10)
        assert not s_dead_pixels.data.any()

    def test_mask_array(self):
        s = LazyPixelatedSTEM(dtd._get_dead_pixel_test_data_2d())
        mask_array = np.ones_like(s.data, dtype=np.bool)
        s_dead_pixels = s.find_dead_pixels(mask_array=mask_array)
        assert not s_dead_pixels.data.any()

    def test_non_lazy_signal(self):
        data = dtd._get_dead_pixel_test_data_2d()
        data.compute()
        s = PixelatedSTEM(data)
        s_dead_pixels = s.find_dead_pixels()
        assert s_dead_pixels.data.shape == s.data.shape
        assert s_dead_pixels.data[14, 42]
        assert s_dead_pixels.data[2, 12]
        s_dead_pixels.data[14, 42] = False
        s_dead_pixels.data[2, 12] = False
        assert not s_dead_pixels.data.any()


class TestCorrectBadPixels:

    def test_2d(self):
        data = np.ones((100, 90))
        data[41, 21] = 0
        data[9, 81] = 50000
        dask_array = da.from_array(data, chunks=(10, 10))
        s = LazyPixelatedSTEM(dask_array)
        s_dead_pixels = s.find_dead_pixels(lazy_result=True)
        s_hot_pixels = s.find_hot_pixels(lazy_result=True)
        s_bad_pixels = s_dead_pixels + s_hot_pixels
        s_corr = s.correct_bad_pixels(s_bad_pixels)
        assert s_dead_pixels.data.shape == data.shape
        assert s_dead_pixels._lazy
        s_corr.compute()
        assert (s_corr.data == 1.).all()

    def test_non_lazy_result(self):
        data = np.ones((100, 90))
        data[41, 21] = 0
        data[9, 81] = 50000
        dask_array = da.from_array(data, chunks=(10, 10))
        s = LazyPixelatedSTEM(dask_array)
        s_dead_pixels = s.find_dead_pixels(lazy_result=True)
        s_hot_pixels = s.find_hot_pixels(lazy_result=True)
        s_bad_pixels = s_dead_pixels + s_hot_pixels
        s_corr = s.correct_bad_pixels(s_bad_pixels, lazy_result=False)
        assert s_dead_pixels.data.shape == data.shape
        assert not s_corr._lazy
        assert (s_corr.data == 1.).all()

    def test_non_lazy_input(self):
        data = np.ones((100, 90))
        data[41, 21] = 0
        data[9, 81] = 50000
        s = PixelatedSTEM(data)
        s_dead_pixels = s.find_dead_pixels()
        s_hot_pixels = s.find_hot_pixels()
        s_bad_pixels = s_dead_pixels + s_hot_pixels
        s_corr = s.correct_bad_pixels(s_bad_pixels, lazy_result=False)
        assert s_dead_pixels.data.shape == data.shape
        assert not s_corr._lazy
        assert (s_corr.data == 1.).all()


class TestPixelatedStemCenterOfMass:

    def test_center_of_mass_0d(self):
        x0, y0 = 2, 3
        array0 = np.zeros(shape=(7, 9))
        array0[y0, x0] = 1
        s0 = PixelatedSTEM(array0)
        s_com0 = s0.center_of_mass()
        assert (s_com0.inav[0].data == x0).all()
        assert (s_com0.inav[1].data == y0).all()
        assert s_com0.axes_manager.navigation_shape == (2, )
        assert s_com0.axes_manager.signal_shape == ()

    def test_center_of_mass_1d(self):
        x0, y0 = 2, 3
        array0 = np.zeros(shape=(5, 6, 4))
        array0[:, y0, x0] = 1
        s0 = PixelatedSTEM(array0)
        s_com0 = s0.center_of_mass()
        assert (s_com0.inav[0].data == x0).all()
        assert (s_com0.inav[1].data == y0).all()
        assert s_com0.axes_manager.navigation_shape == (2, )
        assert s_com0.axes_manager.signal_shape == (5, )

    def test_center_of_mass(self):
        x0, y0 = 5, 7
        array0 = np.zeros(shape=(10, 10, 10, 10))
        array0[:, :, y0, x0] = 1
        s0 = PixelatedSTEM(array0)
        s_com0 = s0.center_of_mass()
        assert (s_com0.inav[0].data == x0).all()
        assert (s_com0.inav[1].data == y0).all()

        array1 = np.zeros(shape=(10, 10, 10, 10))
        x1_array = np.random.randint(0, 10, size=(10, 10))
        y1_array = np.random.randint(0, 10, size=(10, 10))
        for i in range(10):
            for j in range(10):
                array1[i, j, y1_array[i, j], x1_array[i, j]] = 1
        s1 = PixelatedSTEM(array1)
        s_com1 = s1.center_of_mass()
        assert (s_com1.data[0] == x1_array).all()
        assert (s_com1.data[1] == y1_array).all()

    def test_center_of_mass_different_shapes(self):
        array1 = np.zeros(shape=(5, 10, 15, 8))
        x1_array = np.random.randint(1, 7, size=(5, 10))
        y1_array = np.random.randint(1, 14, size=(5, 10))
        for i in range(5):
            for j in range(10):
                array1[i, j, y1_array[i, j], x1_array[i, j]] = 1
        s1 = PixelatedSTEM(array1)
        s_com1 = s1.center_of_mass()
        assert (s_com1.inav[0].data == x1_array).all()
        assert (s_com1.inav[1].data == y1_array).all()

    def test_center_of_mass_different_shapes2(self):
        psX, psY = 11, 9
        s = mdtd.generate_4d_data(
                probe_size_x=psX, probe_size_y=psY, ring_x=None)
        s_com = s.center_of_mass()
        assert s_com.axes_manager.shape == (2, psX, psY)

    def test_different_shape_no_blur_no_downscale(self):
        y, x = np.mgrid[75:83:9j, 85:95:11j]
        s = mdtd.generate_4d_data(
                probe_size_x=11, probe_size_y=9, ring_x=None,
                image_size_x=160, image_size_y=140, disk_x=x, disk_y=y,
                disk_r=40, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s_com = s.center_of_mass()
        assert (s_com.inav[0].data == x).all()
        assert (s_com.inav[1].data == y).all()

    def test_different_shape_no_downscale(self):
        y, x = np.mgrid[75:83:9j, 85:95:11j]
        s = mdtd.generate_4d_data(
                probe_size_x=11, probe_size_y=9, ring_x=None,
                image_size_x=160, image_size_y=140, disk_x=x, disk_y=y,
                disk_r=40, disk_I=20, blur=True, blur_sigma=1,
                downscale=False)
        s_com = s.center_of_mass()
        np.testing.assert_allclose(s_com.inav[0].data, x)
        np.testing.assert_allclose(s_com.inav[1].data, y)

    def test_mask(self):
        y, x = np.mgrid[75:83:9j, 85:95:11j]
        s = mdtd.generate_4d_data(
                probe_size_x=11, probe_size_y=9, ring_x=None,
                image_size_x=160, image_size_y=140, disk_x=x, disk_y=y,
                disk_r=40, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s.data[:, :, 15, 10] = 1000000
        s_com0 = s.center_of_mass()
        s_com1 = s.center_of_mass(mask=(90, 79, 60))
        assert not (s_com0.inav[0].data == x).all()
        assert not (s_com0.inav[1].data == y).all()
        assert (s_com1.inav[0].data == x).all()
        assert (s_com1.inav[1].data == y).all()

    def test_mask_2(self):
        x, y = 60, 50
        s = mdtd.generate_4d_data(
                probe_size_x=5, probe_size_y=5, ring_x=None,
                image_size_x=120, image_size_y=100, disk_x=x, disk_y=y,
                disk_r=20, disk_I=20, blur=False, downscale=False)
        # Add one large value
        s.data[:, :, 50, 30] = 200000  # Large value to the left of the disk

        # Center of mass should not be in center of the disk, due to the
        # large value.
        s_com0 = s.center_of_mass()
        assert not (s_com0.inav[0].data == x).all()
        assert (s_com0.inav[1].data == y).all()

        # Here, the large value is masked
        s_com1 = s.center_of_mass(mask=(60, 50, 25))
        assert (s_com1.inav[0].data == x).all()
        assert (s_com1.inav[1].data == y).all()

        # Here, the large value is right inside the edge of the mask
        s_com3 = s.center_of_mass(mask=(60, 50, 31))
        assert not (s_com3.inav[0].data == x).all()
        assert (s_com3.inav[1].data == y).all()

        # Here, the large value is right inside the edge of the mask
        s_com4 = s.center_of_mass(mask=(59, 50, 30))
        assert not (s_com4.inav[0].data == x).all()
        assert (s_com4.inav[1].data == y).all()

        s.data[:, :, 50, 30] = 0
        s.data[:, :, 80, 60] = 200000  # Large value under the disk

        # The large value is masked
        s_com5 = s.center_of_mass(mask=(60, 50, 25))
        assert (s_com5.inav[0].data == x).all()
        assert (s_com5.inav[1].data == y).all()

        # The large value just not masked
        s_com6 = s.center_of_mass(mask=(60, 50, 31))
        assert (s_com6.inav[0].data == x).all()
        assert not (s_com6.inav[1].data == y).all()

        # The large value just not masked
        s_com7 = s.center_of_mass(mask=(60, 55, 25))
        assert (s_com7.inav[0].data == x).all()
        assert not (s_com7.inav[1].data == y).all()

    def test_threshold(self):
        x, y = 60, 50
        s = mdtd.generate_4d_data(
                probe_size_x=4, probe_size_y=3, ring_x=None,
                image_size_x=120, image_size_y=100, disk_x=x, disk_y=y,
                disk_r=20, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s.data[:, :, 0:30, 0:30] = 5

        # The extra values are ignored due to thresholding
        s_com0 = s.center_of_mass(threshold=2)
        assert (s_com0.inav[0].data == x).all()
        assert (s_com0.inav[1].data == y).all()

        # The extra values are not ignored
        s_com1 = s.center_of_mass(threshold=1)
        assert not (s_com1.inav[0].data == x).all()
        assert not (s_com1.inav[1].data == y).all()

        # The extra values are not ignored
        s_com2 = s.center_of_mass()
        assert not (s_com2.inav[0].data == x).all()
        assert not (s_com2.inav[1].data == y).all()

    def test_threshold_and_mask(self):
        x, y = 60, 50
        s = mdtd.generate_4d_data(
                probe_size_x=4, probe_size_y=3, ring_x=None,
                image_size_x=120, image_size_y=100, disk_x=x, disk_y=y,
                disk_r=20, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s.data[:, :, 0:30, 0:30] = 5
        s.data[:, :, 1, -2] = 60

        # The extra values are ignored due to thresholding and mask
        s_com0 = s.center_of_mass(threshold=2, mask=(60, 50, 50))
        assert (s_com0.inav[0].data == x).all()
        assert (s_com0.inav[1].data == y).all()

        # The extra values are not ignored
        s_com1 = s.center_of_mass(mask=(60, 50, 50))
        assert not (s_com1.inav[0].data == x).all()
        assert not (s_com1.inav[1].data == y).all()

        # The extra values are not ignored
        s_com3 = s.center_of_mass(threshold=2)
        assert not (s_com3.inav[0].data == x).all()
        assert not (s_com3.inav[1].data == y).all()

        # The extra values are not ignored
        s_com4 = s.center_of_mass()
        assert not (s_com4.inav[0].data == x).all()
        assert not (s_com4.inav[1].data == y).all()

    def test_1d_signal(self):
        x = np.arange(45, 45+9).reshape((1, 9))
        y = np.arange(55, 55+9).reshape((1, 9))
        s = mdtd.generate_4d_data(
                probe_size_x=9, probe_size_y=1, ring_x=None,
                image_size_x=120, image_size_y=100, disk_x=x, disk_y=y,
                disk_r=20, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s_com = s.inav[:, 0].center_of_mass()
        assert (s_com.inav[0].data == x).all()
        assert (s_com.inav[1].data == y).all()

    def test_0d_signal(self):
        x, y = 40, 51
        s = mdtd.generate_4d_data(
                probe_size_x=1, probe_size_y=1, ring_x=None,
                image_size_x=120, image_size_y=100, disk_x=x, disk_y=y,
                disk_r=20, disk_I=20, blur=False, blur_sigma=1,
                downscale=False)
        s_com = s.inav[0, 0].center_of_mass()
        assert (s_com.inav[0].data == x).all()
        assert (s_com.inav[1].data == y).all()

    def test_lazy(self):
        y, x = np.mgrid[75:83:9j, 85:95:11j]
        s = mdtd.generate_4d_data(
                probe_size_x=11, probe_size_y=9, ring_x=None,
                image_size_x=160, image_size_y=140, disk_x=x, disk_y=y,
                disk_r=40, disk_I=20, blur=True, blur_sigma=1,
                downscale=False)
        s_lazy = LazyPixelatedSTEM(
                da.from_array(s.data, chunks=(1, 1, 140, 160)))
        s_lazy_com = s_lazy.center_of_mass()
        np.testing.assert_allclose(s_lazy_com.inav[0].data, x)
        np.testing.assert_allclose(s_lazy_com.inav[1].data, y)

    def test_compare_lazy_and_nonlazy(self):
        y, x = np.mgrid[75:83:9j, 85:95:11j]
        s = mdtd.generate_4d_data(
                probe_size_x=11, probe_size_y=9, ring_x=None,
                image_size_x=160, image_size_y=140, disk_x=x, disk_y=y,
                disk_r=40, disk_I=20, blur=True, blur_sigma=1,
                downscale=False)
        s_lazy = LazyPixelatedSTEM(
                da.from_array(s.data, chunks=(1, 1, 140, 160)))
        s_com = s.center_of_mass()
        s_lazy_com = s_lazy.center_of_mass()
        np.testing.assert_equal(s_com.data, s_lazy_com.data)

        com_nav_extent = s_com.axes_manager.navigation_extent
        lazy_com_nav_extent = s_lazy_com.axes_manager.navigation_extent
        assert com_nav_extent == lazy_com_nav_extent

        com_sig_extent = s_com.axes_manager.signal_extent
        lazy_com_sig_extent = s_lazy_com.axes_manager.signal_extent
        assert com_sig_extent == lazy_com_sig_extent

    def test_lazy_result(self):
        data = da.ones((10, 10, 20, 20), chunks=(10, 10, 10, 10))
        s_lazy = LazyPixelatedSTEM(data)
        s_lazy_com = s_lazy.center_of_mass(lazy_result=True)
        assert s_lazy_com._lazy


class TestPixelatedStemRadialIntegration:

    def test_simple(self):
        array0 = np.ones(shape=(10, 10, 40, 40))
        s0 = PixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert (s0_r.data[:, :, :-1] == 1).all()

        data_shape = 2, 2, 11, 11
        array1 = np.zeros(data_shape)
        array1[:, :, 5, 5] = 1
        s1 = PixelatedSTEM(array1)
        s1.axes_manager.signal_axes[0].offset = -5
        s1.axes_manager.signal_axes[1].offset = -5
        s1_r = s1.radial_integration()
        assert np.all(s1_r.data[:, :, 0] == 1)
        assert np.all(s1_r.data[:, :, 1:] == 0)

    def test_different_shape(self):
        array = np.ones(shape=(7, 9, 30, 40))
        s = PixelatedSTEM(array)
        s_r = s.radial_integration()
        assert (s_r.data[:, :, :-2] == 1).all()

    def test_nav_0(self):
        data_shape = (40, 40)
        array0 = np.ones(shape=data_shape)
        s0 = PixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert s0_r.axes_manager.navigation_dimension == 0
        assert (s0_r.data[:-1] == 1).all()

    def test_nav_1(self):
        data_shape = (5, 40, 40)
        array0 = np.ones(shape=data_shape)
        s0 = PixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert s0_r.axes_manager.navigation_shape == data_shape[:1]
        assert (s0_r.data[:, :-1] == 1).all()

    def test_big_value(self):
        data_shape = (5, 40, 40)
        big_value = 50000000
        array0 = np.ones(shape=data_shape)*big_value
        s0 = PixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert s0_r.axes_manager.navigation_shape == data_shape[:1]
        assert (s0_r.data[:, :-1] == big_value).all()

    def test_correct_radius_simple(self):
        x, y, r, px, py = 40, 51, 30, 4, 5
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_I=0, ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        s.axes_manager.signal_axes[0].offset = -x
        s.axes_manager.signal_axes[1].offset = -y
        s_r = s.radial_integration()
        assert s_r.axes_manager.navigation_shape == (px, py)
        assert (s_r.data.argmax(axis=-1) == 30).all()

    def test_correct_radius_random(self):
        x, y, px, py = 56, 48, 4, 5
        r = np.random.randint(20, 40, size=(py, px))
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_I=0, ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        s.axes_manager.signal_axes[0].offset = -x
        s.axes_manager.signal_axes[1].offset = -y
        s_r = s.radial_integration()
        assert (s_r.data.argmax(axis=-1) == r).all()

    def test_correct_disk_x_y_and_radius_random(self):
        x, y, px, py = 56, 48, 4, 5
        x, y = randint(45, 55, size=(py, px)), randint(45, 55, size=(py, px))
        r = randint(20, 40, size=(py, px))
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_x=x, disk_y=y, disk_r=5, disk_I=20,
                ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        s_com = s.center_of_mass()
        s_r = s.radial_integration(
                centre_x=s_com.inav[0].data, centre_y=s_com.inav[1].data)
        s_r = s_r.isig[15:]  # Do not include the disk
        r -= 15  # Need to shift the radius, due to not including the disk
        assert (s_r.data.argmax(axis=-1) == r).all()


class TestPixelatedStemRadialIntegrationLazy:

    def test_simple(self):
        array0 = da.ones(shape=(10, 10, 40, 40), chunks=(5, 5, 5, 5))
        s0 = LazyPixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert (s0_r.data[:, :, :-1] == 1).all()

        data_shape = 2, 2, 11, 11
        array1 = np.zeros(data_shape)
        array1[:, :, 5, 5] = 1
        dask_array = da.from_array(array1, chunks=(1, 1, 1, 1))
        s1 = LazyPixelatedSTEM(dask_array)
        s1.axes_manager.signal_axes[0].offset = -5
        s1.axes_manager.signal_axes[1].offset = -5
        s1_r = s1.radial_integration()
        assert np.all(s1_r.data[:, :, 0] == 1)
        assert np.all(s1_r.data[:, :, 1:] == 0)

    def test_different_shape(self):
        array = da.ones(shape=(7, 9, 30, 40), chunks=(3, 3, 5, 5))
        s = LazyPixelatedSTEM(array)
        s_r = s.radial_integration()
        assert (s_r.data[:, :, :-2] == 1).all()

    def test_nav_1(self):
        data_shape = (5, 40, 40)
        array0 = da.ones(shape=data_shape, chunks=(5, 5, 5))
        s0 = LazyPixelatedSTEM(array0)
        s0_r = s0.radial_integration()
        assert s0_r.axes_manager.navigation_shape == data_shape[:1]
        assert (s0_r.data[:, :-1] == 1).all()

    def test_big_value(self):
        data_shape = (5, 40, 40)
        big_value = 50000000
        array0 = np.ones(shape=data_shape)*big_value
        dask_array = da.from_array(array0, chunks=(2, 10, 10))
        s0 = LazyPixelatedSTEM(dask_array)
        s0_r = s0.radial_integration()
        assert s0_r.axes_manager.navigation_shape == data_shape[:1]
        assert (s0_r.data[:, :-1] == big_value).all()

    def test_correct_radius_simple(self):
        x, y, r, px, py = 40, 51, 30, 4, 5
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_I=0, ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        dask_array = da.from_array(s.data, chunks=(4, 4, 50, 50))
        s = LazyPixelatedSTEM(dask_array)
        s.axes_manager.signal_axes[0].offset = -x
        s.axes_manager.signal_axes[1].offset = -y
        s_r = s.radial_integration()
        assert s_r.axes_manager.navigation_shape == (px, py)
        assert (s_r.data.argmax(axis=-1) == 30).all()

    def test_correct_radius_random(self):
        x, y, px, py = 56, 48, 4, 5
        r = np.random.randint(20, 40, size=(py, px))
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_I=0, ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        dask_array = da.from_array(s.data, chunks=(4, 4, 50, 50))
        s = LazyPixelatedSTEM(dask_array)
        s.axes_manager.signal_axes[0].offset = -x
        s.axes_manager.signal_axes[1].offset = -y
        s_r = s.radial_integration()
        assert (s_r.data.argmax(axis=-1) == r).all()

    def test_correct_disk_x_y_and_radius_random(self):
        x, y, px, py = 56, 48, 4, 5
        x, y = randint(45, 55, size=(py, px)), randint(45, 55, size=(py, px))
        r = randint(20, 40, size=(py, px))
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_x=x, disk_y=y, disk_r=5, disk_I=20,
                ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        dask_array = da.from_array(s.data, chunks=(4, 4, 50, 50))
        s = LazyPixelatedSTEM(dask_array)
        s_com = s.center_of_mass()
        s_r = s.radial_integration(
                centre_x=s_com.inav[0].data, centre_y=s_com.inav[1].data)
        s_r = s_r.isig[15:]  # Do not include the disk
        r -= 15  # Need to shift the radius, due to not including the disk
        assert (s_r.data.argmax(axis=-1) == r).all()


class TestPixelatedStemAngleSector:

    def test_get_angle_sector_mask_simple(self):
        array = np.zeros((10, 10, 10, 10))
        array[:, :, 0:5, 0:5] = 1
        s = PixelatedSTEM(array)
        s.axes_manager.signal_axes[0].offset = -4.5
        s.axes_manager.signal_axes[1].offset = -4.5
        mask = s.angular_mask(0.0, 0.5*np.pi)
        assert mask[:, :, 0:5, 0:5].all()
        assert not mask[:, :, 5:, :].any()
        assert not mask[:, :, :, 5:].any()

    def test_get_angle_sector_mask_radial_integration1(self):
        x, y = 4.5, 4.5
        array = np.zeros((10, 10, 10, 10))
        array[:, :, 0:5, 0:5] = 1
        centre_x_array = np.ones_like(array)*x
        centre_y_array = np.ones_like(array)*y
        s = PixelatedSTEM(array)
        s.axes_manager.signal_axes[0].offset = -x
        s.axes_manager.signal_axes[1].offset = -y
        mask0 = s.angular_mask(0.0, 0.5*np.pi)
        s_r0 = s.radial_integration(
                centre_x=centre_x_array, centre_y=centre_y_array,
                mask_array=mask0)
        assert np.all(s_r0.isig[0:6].data == 1.)

        mask1 = s.angular_mask(0, np.pi)
        s_r1 = s.radial_integration(
                centre_x=centre_x_array, centre_y=centre_y_array,
                mask_array=mask1)
        assert np.all(s_r1.isig[0:6].data == 0.5)

        mask2 = s.angular_mask(0.0, 2*np.pi)
        s_r2 = s.radial_integration(
                centre_x=centre_x_array, centre_y=centre_y_array,
                mask_array=mask2)
        assert np.all(s_r2.isig[0:6].data == 0.25)

        mask3 = s.angular_mask(np.pi, 2*np.pi)
        s_r3 = s.radial_integration(
                centre_x=centre_x_array, centre_y=centre_y_array,
                mask_array=mask3)
        assert np.all(s_r3.data == 0.0)

    def test_com_angle_sector_mask(self):
        x, y = 4, 7
        array = np.zeros((5, 4, 10, 20))
        array[:, :, y, x] = 1
        s = PixelatedSTEM(array)
        s_com = s.center_of_mass()
        s.angular_mask(
                0.0, 0.5*np.pi,
                centre_x_array=s_com.inav[0].data,
                centre_y_array=s_com.inav[1].data)


class TestAngularSliceRadialIntegration:

    def test_same_radius(self):
        x, y, r, px, py, angleN = 56, 48, 20, 4, 5, 20
        s = mdtd.generate_4d_data(
                probe_size_x=px, probe_size_y=py,
                image_size_x=120, image_size_y=100,
                disk_I=0, ring_x=x, ring_y=y, ring_r=r, ring_I=5,
                blur=True, downscale=False)
        s_ar = s.angular_slice_radial_integration(
                centre_x=x, centre_y=y, angleN=20)
        assert s_ar.axes_manager.navigation_shape, (x, y, angleN)
        assert (s_ar.data.argmax(-1) == r).all()

    def test_different_radius(self):
        x, y, r, px, py, iX, iY = 50, 50, 20, 6, 5, 100, 100
        kwrds = {
                'probe_size_x': px, 'probe_size_y': py,
                'image_size_x': iX, 'image_size_y': iY, 'disk_I': 0,
                'ring_x': x, 'ring_y': y, 'ring_r': r, 'ring_I': 5,
                'blur': True, 'downscale': False}
        r0, r1, r2, r3 = 20, 25, 30, 27
        kwrds['ring_r'] = r0
        s = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r1
        s1 = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r2
        s2 = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r3
        s3 = mdtd.generate_4d_data(**kwrds)

        s.data[:, :, :y, x:] = s1.data[:, :, :y, x:]
        s.data[:, :, y:, x:] = s2.data[:, :, y:, x:]
        s.data[:, :, y:, :x] = s3.data[:, :, y:, :x]

        s_ar = s.angular_slice_radial_integration(
                centre_x=x, centre_y=y, angleN=4)
        assert (s_ar.inav[:, :, 0].data.argmax(axis=-1) == r0).all()
        assert (s_ar.inav[:, :, 1].data.argmax(axis=-1) == r1).all()
        assert (s_ar.inav[:, :, 2].data.argmax(axis=-1) == r2).all()
        assert (s_ar.inav[:, :, 3].data.argmax(axis=-1) == r3).all()

    def test_different_radius_not_square_image(self):
        x, y, r, px, py, iX, iY = 40, 55, 20, 6, 5, 120, 100
        kwrds = {
                'probe_size_x': px, 'probe_size_y': py,
                'image_size_x': iX, 'image_size_y': iY, 'disk_I': 0,
                'ring_x': x, 'ring_y': y, 'ring_r': r, 'ring_I': 5,
                'blur': True, 'downscale': False}
        r0, r1, r2, r3 = 20, 25, 30, 27
        kwrds['ring_r'] = r0
        s = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r1
        s1 = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r2
        s2 = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r3
        s3 = mdtd.generate_4d_data(**kwrds)

        s.data[:, :, :y, x:] = s1.data[:, :, :y, x:]
        s.data[:, :, y:, x:] = s2.data[:, :, y:, x:]
        s.data[:, :, y:, :x] = s3.data[:, :, y:, :x]

        s_ar = s.angular_slice_radial_integration(
                centre_x=x, centre_y=y, angleN=4)
        assert (s_ar.inav[:, :, 0].data.argmax(axis=-1) == r0).all()
        assert (s_ar.inav[:, :, 1].data.argmax(axis=-1) == r1).all()
        assert (s_ar.inav[:, :, 2].data.argmax(axis=-1) == r2).all()
        assert (s_ar.inav[:, :, 3].data.argmax(axis=-1) == r3).all()

    def test_slice_overlap(self):
        x, y, r, px, py, iX, iY = 40, 55, 20, 6, 5, 120, 100
        kwrds = {
                'probe_size_x': px, 'probe_size_y': py,
                'image_size_x': iX, 'image_size_y': iY, 'disk_I': 0,
                'ring_x': x, 'ring_y': y, 'ring_r': r, 'ring_I': 5,
                'blur': True, 'downscale': False}
        r0, r1 = 20, 30
        kwrds['ring_r'] = r0
        s = mdtd.generate_4d_data(**kwrds)
        kwrds['ring_r'] = r1
        kwrds['ring_I'] = 500
        s1 = mdtd.generate_4d_data(**kwrds)

        s.data[:, :, y:, :] = s1.data[:, :, y:, :]

        s_ar = s.angular_slice_radial_integration(
                centre_x=x, centre_y=y, angleN=2)
        assert (s_ar.inav[:, :, 0].data.argmax(axis=-1) == r0).all()
        assert (s_ar.inav[:, :, 1].data.argmax(axis=-1) == r1).all()

        s_ar1 = s.angular_slice_radial_integration(
                centre_x=x, centre_y=y, angleN=2, slice_overlap=0.1)
        assert (s_ar1.inav[:, :, 0].data.argmax(axis=-1) == r1).all()
        assert (s_ar1.inav[:, :, 1].data.argmax(axis=-1) == r1).all()

        with pytest.raises(ValueError):
            s.angular_slice_radial_integration(slice_overlap=1.2)
        with pytest.raises(ValueError):
            s.angular_slice_radial_integration(slice_overlap=-0.2)


class TestPixelatedStemVirtualAnnularDarkField:

    def test_simple(self):
        shape = (5, 9, 12, 14)
        s = PixelatedSTEM(np.zeros(shape))
        s1 = s.virtual_annular_dark_field(cx=6, cy=6, r_inner=2, r=5)
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])
        assert s1.data.sum() == 0.

    def test_one_value(self):
        shape = (5, 9, 12, 14)
        s = PixelatedSTEM(np.zeros(shape))
        s.data[:, :, 9, 9] = 1
        s1 = s.virtual_annular_dark_field(cx=6, cy=6, r_inner=2, r=5)
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])
        assert (s1.data == 1.).all()

    def test_lazy(self):
        shape = (5, 9, 12, 14)
        data = da.zeros((5, 9, 12, 14), chunks=(10, 10, 10, 10))
        s = LazyPixelatedSTEM(data)
        s1 = s.virtual_annular_dark_field(cx=6, cy=6, r_inner=2, r=5)
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])


class TestPixelatedStemVirtualBrightField:

    def test_simple(self):
        shape = (5, 9, 12, 14)
        s = PixelatedSTEM(np.zeros(shape))
        s1 = s.virtual_bright_field()
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])
        assert s1.data.sum() == 0.

    def test_one_value(self):
        shape = (5, 9, 12, 14)
        s = PixelatedSTEM(np.zeros(shape))
        s.data[:, :, 10, 13] = 1
        s1 = s.virtual_bright_field()
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])
        assert (s1.data == 1.).all()

        s2 = s.virtual_bright_field(6, 6, 2)
        assert s2.axes_manager.signal_shape == (shape[1], shape[0])
        assert s2.data.sum() == 0

    def test_lazy(self):
        shape = (5, 9, 12, 14)
        data = da.zeros((5, 9, 12, 14), chunks=(10, 10, 10, 10))
        s = LazyPixelatedSTEM(data)
        s1 = s.virtual_bright_field(cx=6, cy=6, r=5)
        assert s1.axes_manager.signal_shape == (shape[1], shape[0])

    def test_lazy_result(self):
        data = da.ones((10, 10, 20, 20), chunks=(10, 10, 10, 10))
        s = LazyPixelatedSTEM(data)
        s_out = s.virtual_bright_field(lazy_result=True)
        assert s_out._lazy


class TestPixelatedStemTemplateMatchDisk:

    def test_simple(self):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 20, 20)))
        s_template = s.template_match_disk()
        assert s.data.shape == s_template.data.shape
        assert s_template._lazy is True

    def test_axes_manager_copy(self):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 20, 20)))
        ax_sa = s.axes_manager.signal_axes
        ax_na = s.axes_manager.navigation_axes
        ax_sa[0].name, ax_sa[1].name = 'Detector x', 'Detector y'
        ax_sa[0].scale, ax_sa[1].scale = 0.2, 0.2
        ax_sa[0].offset, ax_sa[1].offset = 10, 20
        ax_sa[0].units, ax_sa[1].units = 'mrad', 'mrad'
        ax_na[0].name, ax_na[1].name = 'Probe x', 'Probe y'
        ax_na[0].scale, ax_na[1].scale = 35, 35
        ax_na[0].offset, ax_na[1].offset = 54, 12
        ax_na[0].units, ax_na[1].units = 'nm', 'nm'
        s_temp = s.template_match_disk()
        assert s.data.shape == s_temp.data.shape
        ax_sa_t = s_temp.axes_manager.signal_axes
        ax_na_t = s_temp.axes_manager.navigation_axes
        assert ax_sa[0].name == ax_sa_t[0].name
        assert ax_sa[1].name == ax_sa_t[1].name
        assert ax_sa[0].scale == ax_sa_t[0].scale
        assert ax_sa[1].scale == ax_sa_t[1].scale
        assert ax_sa[0].offset == ax_sa_t[0].offset
        assert ax_sa[1].offset == ax_sa_t[1].offset
        assert ax_sa[0].units == ax_sa_t[0].units
        assert ax_sa[1].units == ax_sa_t[1].units

        assert ax_na[0].name == ax_na_t[0].name
        assert ax_na[1].name == ax_na_t[1].name
        assert ax_na[0].scale == ax_na_t[0].scale
        assert ax_na[1].scale == ax_na_t[1].scale
        assert ax_na[0].offset == ax_na_t[0].offset
        assert ax_na[1].offset == ax_na_t[1].offset
        assert ax_na[0].units == ax_na_t[0].units
        assert ax_na[1].units == ax_na_t[1].units

    def test_non_lazy(self):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 20, 20)))
        s_template = s.template_match_disk(lazy_result=False)
        assert s.data.shape == s_template.data.shape
        assert s._lazy is False

    def test_lazy_input(self):
        s = LazyPixelatedSTEM(da.random.randint(
            100, size=(5, 5, 20, 20), chunks=(1, 1, 10, 10)))
        s_template = s.template_match_disk()
        assert s.data.shape == s_template.data.shape
        assert s._lazy is True

    def test_disk_radius(self):
        s = LazyPixelatedSTEM(da.random.randint(
            100, size=(5, 5, 30, 30), chunks=(1, 1, 10, 10)))
        s_template0 = s.template_match_disk(disk_r=2, lazy_result=False)
        s_template1 = s.template_match_disk(disk_r=4, lazy_result=False)
        assert s.data.shape == s_template0.data.shape
        assert s.data.shape == s_template1.data.shape
        assert not (s_template0.data == s_template1.data).all()

    @pytest.mark.parametrize("nav_dims", [0, 1, 2, 3, 4])
    def test_different_dimensions(self, nav_dims):
        shape = list(np.random.randint(2, 6, size=nav_dims))
        shape.extend([50, 50])
        s = PixelatedSTEM(np.random.random(size=shape))
        st = s.template_match_disk(disk_r=4, lazy_result=False)
        assert st.data.shape == tuple(shape)


class TestPixelatedStemTemplateMatchRing:

    def test_simple(self):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 20, 20)))
        s_template = s.template_match_ring(r_inner=3, r_outer=5)
        assert s.data.shape == s_template.data.shape
        assert s_template._lazy is True

    def test_wrong_input(self):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 20, 20)))
        with pytest.raises(ValueError):
            s.template_match_ring(r_inner=5, r_outer=3)
        with pytest.raises(ValueError):
            s.template_match_ring(r_inner=3, r_outer=3)


class TestPixelatedStemTemplateWithBinaryImage:

    def test_square_and_disk(self):
        s = PixelatedSTEM(np.zeros((2, 2, 100, 100)))

        square_image = np.zeros((9, 9))
        square_image[2:-2, 2:-2] = 1
        s.data[:, :, 20:29, 40:49] = square_image

        disk = morphology.disk(4, s.data.dtype)
        s.data[:, :, 60:69, 50:59] = disk

        s_st = s.template_match_with_binary_image(square_image,
                                                  lazy_result=False)
        s_dt = s.template_match_with_binary_image(disk, lazy_result=False)

        st_ind = np.unravel_index(
                np.argmax(s_st.data, axis=None), s_st.data.shape)[-2:]
        dt_ind = np.unravel_index(
                np.argmax(s_dt.data, axis=None), s_dt.data.shape)[-2:]

        assert st_ind == (24, 44)
        assert dt_ind == (64, 54)
        assert s.data.shape == s_st.data.shape
        assert s.data.shape == s_dt.data.shape

    def test_wrong_binary_image_input(self):
        s = PixelatedSTEM(np.random.randint(0, 1000, (2, 2, 20, 20)))
        template = np.zeros(10)
        with pytest.raises(ValueError):
            s.template_match_with_binary_image(template)

        template = np.zeros((10, 5, 5))
        with pytest.raises(ValueError):
            s.template_match_with_binary_image(template)

        template = np.zeros((10, 5, 5, 3))
        with pytest.raises(ValueError):
            s.template_match_with_binary_image(template)


class TestPixelatedStemFindPeaks:

    method1 = ['dog', 'log']

    @pytest.mark.parametrize('methods', method1)
    def test_simple(self, methods):
        s = PixelatedSTEM(np.random.randint(100, size=(3, 2, 10, 20)))
        peak_array = s.find_peaks(method=methods)
        assert s.data.shape[:2] == peak_array.shape
        assert hasattr(peak_array, 'compute')

    @pytest.mark.parametrize('methods', method1)
    def test_lazy_input(self, methods):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks(method=methods)
        assert s.data.shape[:2] == peak_array.shape
        assert hasattr(peak_array, 'compute')

    @pytest.mark.parametrize('methods', method1)
    def test_lazy_output(self, methods):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks(method=methods, lazy_result=False)
        assert s.data.shape[:2] == peak_array.shape
        assert not hasattr(peak_array, 'compute')

    def test_with_data(self):
        data = np.zeros(shape=(2, 3, 200, 100), dtype=np.float64)
        data[0, 0, 50, 20] = 100
        data[0, 1, 51, 21] = 100
        data[0, 2, 52, 22] = 100
        data[1, 0, 53, 23] = 100
        data[1, 1, 54, 24] = 100
        data[1, 2, 55, 25] = 100
        s = PixelatedSTEM(data)
        min_sigma, max_sigma, sigma_ratio = 0.08, 1, 1.76
        threshold, overlap = 0.06, 0.01
        peaks = s.find_peaks(
                min_sigma=min_sigma, max_sigma=max_sigma,
                sigma_ratio=sigma_ratio, threshold=threshold, overlap=overlap)
        peaks = peaks.compute()
        assert peaks[0, 0][0].tolist() == [50, 20]
        assert peaks[0, 1][0].tolist() == [51, 21]
        assert peaks[0, 2][0].tolist() == [52, 22]
        assert peaks[1, 0][0].tolist() == [53, 23]
        assert peaks[1, 1][0].tolist() == [54, 24]
        assert peaks[1, 2][0].tolist() == [55, 25]

    def test_threshold(self):
        data = np.zeros(shape=(2, 3, 200, 100), dtype=np.float64)
        data[:, :, 54, 29] = 100
        data[:, :, 123, 54] = 20
        s = PixelatedSTEM(data)
        min_sigma, max_sigma, sigma_ratio, overlap = 2, 5, 5, 1
        peaks0 = s.find_peaks(
                min_sigma=min_sigma, max_sigma=max_sigma,
                sigma_ratio=sigma_ratio, threshold=0.01, overlap=overlap,
                lazy_result=False)
        for ix, iy in np.ndindex(peaks0.shape):
            assert len(peaks0[ix, iy]) == 2
        peaks1 = s.find_peaks(
                min_sigma=min_sigma, max_sigma=max_sigma,
                sigma_ratio=sigma_ratio, threshold=0.05, overlap=overlap,
                lazy_result=False)
        for ix, iy in np.ndindex(peaks1.shape):
            assert len(peaks1[ix, iy]) == 1

    @pytest.mark.parametrize('methods', method1)
    def test_normalize_value(self, methods):
        data = np.zeros((2, 3, 100, 100), dtype=np.uint16)
        data[:, :, 49:52, 49:52] = 100
        data[:, :, 19:22, 9:12] = 10
        s = PixelatedSTEM(data)
        peak_array0 = s.find_peaks(method=methods,
                                   normalize_value=100, lazy_result=False)
        peak_array1 = s.find_peaks(method=methods,
                                   normalize_value=10, lazy_result=False)
        for ix, iy in np.ndindex(peak_array0.shape):
            assert (peak_array0[ix, iy] == [[50, 50]]).all()
            assert (peak_array1[ix, iy] == [[50, 50], [20, 10]]).all()

    @pytest.mark.parametrize("nav_dims", [0, 1, 2, 3, 4])
    @pytest.mark.parametrize('methods', method1)
    def test_different_dimensions(self, nav_dims, methods):
        shape = list(np.random.randint(2, 6, size=nav_dims))
        shape.extend([50, 50])
        s = PixelatedSTEM(np.random.random(size=shape))
        peak_array = s.find_peaks(method=methods, lazy_result=False)
        assert peak_array.shape == tuple(shape[:-2])


class TestPixelatedStemRotateDiffraction:

    def test_rotate_diffraction_keep_shape(self):
        shape = (7, 5, 4, 15)
        s = PixelatedSTEM(np.zeros(shape))
        s_rot = s.rotate_diffraction(angle=45)
        assert s.axes_manager.shape == s_rot.axes_manager.shape

        s_lazy = LazyPixelatedSTEM(da.zeros(shape, chunks=(1, 1, 1, 1)))
        s_rot_lazy = s_lazy.rotate_diffraction(angle=45)
        assert s_lazy.axes_manager.shape == s_rot_lazy.axes_manager.shape

    def test_rotate_diffraction_values(self):
        data = np.zeros((10, 5, 12, 14))
        data[:, :, 6:, 7:] = 1
        s = PixelatedSTEM(data)
        s_rot = s.rotate_diffraction(angle=180)
        np.testing.assert_almost_equal(
                s.data[0, 0, :6, :7], np.zeros_like(s.data[0, 0, :6, :7]))
        np.testing.assert_almost_equal(
                s_rot.data[0, 0, :6, :7],
                np.ones_like(s_rot.data[0, 0, :6, :7]))
        s_rot.data[:, :, :6, :7] = 0
        np.testing.assert_almost_equal(s_rot.data, np.zeros_like(s.data))


class TestPixelatedStemShiftDiffraction:

    @pytest.mark.parametrize("shift_x,shift_y", [(2, 5), (-6, -1), (2, -4)])
    def test_single_shift(self, shift_x, shift_y):
        s = PixelatedSTEM(np.zeros((10, 10, 30, 40)))
        x, y = 20, 10
        s.data[:, :, y, x] = 1
        s_shift = s.shift_diffraction(shift_x=shift_x, shift_y=shift_y)
        assert s_shift.data[0, 0, y - shift_y, x - shift_x] == 1
        s_shift.data[:, :, y - shift_y, x - shift_x] = 0
        assert s_shift.data.sum() == 0

    @pytest.mark.parametrize("centre_x,centre_y", [(25, 25), (30, 20)])
    def test_random_shifts(self, centre_x, centre_y):
        y, x = np.mgrid[20:30:7j, 20:30:5j]
        s = mdtd.generate_4d_data(
                probe_size_x=5, probe_size_y=7,
                disk_x=x, disk_y=y, disk_r=1, blur=True, ring_x=None)
        s_com = s.center_of_mass()
        s_com.data[0] -= centre_x
        s_com.data[1] -= centre_y
        s_shift = s.shift_diffraction(
                shift_x=s_com.inav[0].data, shift_y=s_com.inav[1].data)
        s_shift_c = s_shift.center_of_mass()
        np.testing.assert_allclose(
                s_shift_c.data[0], np.ones_like(s_shift_c.data[0])*centre_x)
        np.testing.assert_allclose(
                s_shift_c.data[1], np.ones_like(s_shift_c.data[1])*centre_y)

    def test_inplace(self):
        s = PixelatedSTEM(np.zeros((10, 10, 30, 40)))
        x, y, shift_x, shift_y = 20, 10, 4, -3
        s.data[:, :, y, x] = 1
        s.shift_diffraction(shift_x=shift_x, shift_y=shift_y, inplace=True)
        assert s.data[0, 0, y - shift_y, x - shift_x] == 1
        s.data[:, :, y - shift_y, x - shift_x] = 0
        assert s.data.sum() == 0

    def test_lazy(self):
        data = np.zeros((10, 10, 30, 30))
        x, y = 20, 10
        data[:, :, y, x] += 1
        data = da.from_array(data, chunks=(5, 5, 5, 5))
        s = LazyPixelatedSTEM(data)
        shift_x, shift_y = 4, 3
        s_shift = s.shift_diffraction(shift_x=shift_x, shift_y=shift_y)
        s_shift.compute()
        assert s_shift.data[0, 0, y - shift_y, x - shift_x] == 1
        s_shift.data[:, :, y - shift_y, x - shift_x] = 0
        assert s_shift.data.sum() == 0


class TestSubtractingDiffractionBackground():

    method1 = ['difference of gaussians', 'median kernel', 'radial median']

    @pytest.mark.parametrize('methods', method1)
    def test_simple(self, methods):
        s = PixelatedSTEM(np.random.randint(100, size=(3, 2, 200, 150)))
        s_rem = s.subtract_diffraction_background(method=methods)
        assert s_rem.data.shape == s.data.shape
        assert hasattr(s_rem.data, 'compute')

    @pytest.mark.parametrize('methods', method1)
    def test_lazy_input(self, methods):
        data = np.random.randint(100, size=(3, 2, 200, 150))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 20, 10)))
        s_rem = s.subtract_diffraction_background(method=methods)
        assert s.data.shape == s_rem.data.shape
        assert hasattr(s_rem.data, 'compute')

    @pytest.mark.parametrize('methods', method1)
    def test_lazy_output(self, methods):
        data = np.random.randint(100, size=(3, 2, 200, 150))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 20, 20)))
        s_rem = s.subtract_diffraction_background(
            method=methods, lazy_result=False)
        assert s.data.shape == s_rem.data.shape
        assert not hasattr(s_rem.data, 'compute')

    @pytest.mark.parametrize('methods', method1)
    def test_axes_manager_copy(self, methods):
        s = PixelatedSTEM(np.random.randint(100, size=(5, 5, 200, 200)))
        ax_sa = s.axes_manager.signal_axes
        ax_na = s.axes_manager.navigation_axes
        ax_sa[0].name, ax_sa[1].name = 'Detector x', 'Detector y'
        ax_sa[0].scale, ax_sa[1].scale = 0.2, 0.2
        ax_sa[0].offset, ax_sa[1].offset = 10, 20
        ax_sa[0].units, ax_sa[1].units = 'mrad', 'mrad'
        ax_na[0].name, ax_na[1].name = 'Probe x', 'Probe y'
        ax_na[0].scale, ax_na[1].scale = 35, 35
        ax_na[0].offset, ax_na[1].offset = 54, 12
        ax_na[0].units, ax_na[1].units = 'nm', 'nm'
        s_temp = s.subtract_diffraction_background(method=methods)
        assert s.data.shape == s_temp.data.shape
        ax_sa_t = s_temp.axes_manager.signal_axes
        ax_na_t = s_temp.axes_manager.navigation_axes
        assert ax_sa[0].name == ax_sa_t[0].name
        assert ax_sa[1].name == ax_sa_t[1].name
        assert ax_sa[0].scale == ax_sa_t[0].scale
        assert ax_sa[1].scale == ax_sa_t[1].scale
        assert ax_sa[0].offset == ax_sa_t[0].offset
        assert ax_sa[1].offset == ax_sa_t[1].offset
        assert ax_sa[0].units == ax_sa_t[0].units
        assert ax_sa[1].units == ax_sa_t[1].units

        assert ax_na[0].name == ax_na_t[0].name
        assert ax_na[1].name == ax_na_t[1].name
        assert ax_na[0].scale == ax_na_t[0].scale
        assert ax_na[1].scale == ax_na_t[1].scale
        assert ax_na[0].offset == ax_na_t[0].offset
        assert ax_na[1].offset == ax_na_t[1].offset
        assert ax_na[0].units == ax_na_t[0].units
        assert ax_na[1].units == ax_na_t[1].units

    @pytest.mark.parametrize("nav_dims", [0, 1, 2, 3, 4])
    @pytest.mark.parametrize('methods', method1)
    def test_different_dimensions(self, nav_dims, methods):
        shape = list(np.random.randint(2, 6, size=nav_dims))
        shape.extend([200, 200])
        s = PixelatedSTEM(np.random.random(size=shape))
        st = s.subtract_diffraction_background(method=methods)
        assert st.data.shape == tuple(shape)


class TestPixelatedStemIntensityPeaks:

    def test_simple(self):
        s = PixelatedSTEM(np.random.randint(100, size=(3, 2, 10, 20)))
        peak_array = s.find_peaks()
        intensity_array = s.intensity_peaks(peak_array)
        assert s.data.shape[:2] == intensity_array.shape
        assert hasattr(intensity_array, 'compute')

    def test_lazy_input(self):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks()
        intensity_array = s.intensity_peaks(peak_array)
        assert s.data.shape[:2] == intensity_array.shape
        assert hasattr(intensity_array, 'compute')

    def test_lazy_output(self):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks()
        intensity_array = s.intensity_peaks(peak_array, lazy_result=False)
        assert s.data.shape[:2] == intensity_array.shape
        assert not hasattr(intensity_array, 'compute')

    def test_with_data(self):
        data = np.zeros(shape=(2, 3, 200, 100), dtype=np.float64)
        data[0, 0, 50, 20] = 100
        data[0, 1, 51, 21] = 200
        data[0, 2, 52, 22] = 100
        data[1, 0, 53, 23] = 200
        data[1, 1, 54, 24] = 100
        data[1, 2, 55, 25] = 200
        s = PixelatedSTEM(data)
        min_sigma, max_sigma, sigma_ratio = 0.08, 1, 1.76
        threshold, overlap = 0.06, 0.01
        peaks = s.find_peaks(
                min_sigma=min_sigma, max_sigma=max_sigma,
                sigma_ratio=sigma_ratio, threshold=threshold, overlap=overlap)
        intensity_array = s.intensity_peaks(peaks, disk_r=1)
        intensity_array = intensity_array.compute()
        np.testing.assert_almost_equal(intensity_array[0, 0][0][2], 100/9)
        np.testing.assert_almost_equal(intensity_array[0, 1][0][2], 200 / 9)
        np.testing.assert_almost_equal(intensity_array[0, 2][0][2], 100 / 9)
        np.testing.assert_almost_equal(intensity_array[1, 0][0][2], 200 / 9)
        np.testing.assert_almost_equal(intensity_array[1, 1][0][2], 100 / 9)
        np.testing.assert_almost_equal(intensity_array[1, 2][0][2], 200 / 9)

    @pytest.mark.parametrize("nav_dims", [0, 1, 2, 3, 4])
    def test_different_dimensions(self, nav_dims):
        shape = list(np.random.randint(2, 6, size=nav_dims))
        shape.extend([50, 50])
        s = PixelatedSTEM(np.random.random(size=shape))
        peak_array = s.find_peaks()
        intensity_array = s.intensity_peaks(peak_array, disk_r=1)
        assert intensity_array.shape == tuple(shape[:-2])


class TestPixelatedStemPeakPositionRefinement:

    def test_simple(self):
        s = PixelatedSTEM(np.random.randint(100, size=(3, 2, 10, 20)))
        peak_array = s.find_peaks()
        refined_peak_array = s.peak_position_refinement_com(peak_array, 4)
        assert s.data.shape[:2] == refined_peak_array.shape
        assert hasattr(peak_array, 'compute')

    def test_wrong_square_size(self):
        s = PixelatedSTEM(np.random.randint(100, size=(3, 2, 10, 20)))
        peak_array = s.find_peaks()
        with pytest.raises(ValueError):
            s.peak_position_refinement_com(peak_array, square_size=5)

    def test_lazy_input(self):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks()
        refined_peak_array = s.peak_position_refinement_com(peak_array, 4)
        assert s.data.shape[:2] == refined_peak_array.shape
        assert hasattr(refined_peak_array, 'compute')

    def test_lazy_output(self):
        data = np.random.randint(100, size=(3, 2, 10, 20))
        s = LazyPixelatedSTEM(da.from_array(data, chunks=(1, 1, 5, 10)))
        peak_array = s.find_peaks()
        refined_peak_array = s.peak_position_refinement_com(
            peak_array, 4, lazy_result=False)
        assert s.data.shape[:2] == refined_peak_array.shape
        assert not hasattr(refined_peak_array, 'compute')

    def test_with_data(self):
        data = np.zeros(shape=(2, 3, 200, 100), dtype=np.float64)
        data[0, 0, 50, 20] = 100
        data[0, 1, 51, 21] = 100
        data[0, 2, 52, 22] = 100
        data[1, 0, 53, 23] = 100
        data[1, 1, 54, 24] = 100
        data[1, 2, 55, 25] = 100
        s = PixelatedSTEM(data)
        min_sigma, max_sigma, sigma_ratio = 0.08, 1, 1.76
        threshold, overlap = 0.06, 0.01
        peaks = s.find_peaks(
                min_sigma=min_sigma, max_sigma=max_sigma,
                sigma_ratio=sigma_ratio, threshold=threshold, overlap=overlap)
        refined_peaks = s.peak_position_refinement_com(peaks,
                                                       4, lazy_result=False)
        assert refined_peaks[0, 0][0].tolist() == [50., 20.]
        assert refined_peaks[0, 1][0].tolist() == [51., 21.]
        assert refined_peaks[0, 2][0].tolist() == [52., 22.]
        assert refined_peaks[1, 0][0].tolist() == [53., 23.]
        assert refined_peaks[1, 1][0].tolist() == [54., 24.]
        assert refined_peaks[1, 2][0].tolist() == [55., 25.]

    @pytest.mark.parametrize("nav_dims", [0, 1, 2, 3, 4])
    def test_different_dimensions(self, nav_dims):
        shape = list(np.random.randint(2, 6, size=nav_dims))
        shape.extend([50, 50])
        s = PixelatedSTEM(np.random.random(size=shape))
        peak_array = s.find_peaks()
        refined_peak_array = s.peak_position_refinement_com(
            peak_array, 4, lazy_result=False)
        assert refined_peak_array.shape == tuple(shape[:-2])


class TestComputeAndAsLazy:

    def test_2d_data_compute(self):
        dask_array = da.random.random((100, 150), chunks=(50, 50))
        s = LazyPixelatedSTEM(dask_array)
        scale0, scale1, metadata_string = 0.5, 1.5, 'test'
        s.axes_manager[0].scale = scale0
        s.axes_manager[1].scale = scale1
        s.metadata.Test = metadata_string
        s.compute()
        assert s.__class__ == PixelatedSTEM
        assert not hasattr(s.data, 'compute')
        assert s.axes_manager[0].scale == scale0
        assert s.axes_manager[1].scale == scale1
        assert s.metadata.Test == metadata_string
        assert dask_array.shape == s.data.shape

    def test_5d_data_compute(self):
        dask_array = da.random.random((2, 3, 4, 10, 15),
                                      chunks=(1, 1, 1, 10, 15))
        s = LazyPixelatedSTEM(dask_array)
        s.compute()
        assert s.__class__ == PixelatedSTEM
        assert dask_array.shape == s.data.shape

    def test_2d_data_as_lazy(self):
        data = np.random.random((100, 150))
        s = PixelatedSTEM(data)
        scale0, scale1, metadata_string = 0.5, 1.5, 'test'
        s.axes_manager[0].scale = scale0
        s.axes_manager[1].scale = scale1
        s.metadata.Test = metadata_string
        s_lazy = s.as_lazy()
        assert s_lazy.__class__ == LazyPixelatedSTEM
        assert hasattr(s_lazy.data, 'compute')
        assert s_lazy.axes_manager[0].scale == scale0
        assert s_lazy.axes_manager[1].scale == scale1
        assert s_lazy.metadata.Test == metadata_string
        assert data.shape == s_lazy.data.shape

    def test_5d_data_as_lazy(self):
        data = np.random.random((2, 3, 4, 10, 15))
        s = PixelatedSTEM(data)
        s_lazy = s.as_lazy()
        assert s_lazy.__class__ == LazyPixelatedSTEM
        assert data.shape == s_lazy.data.shape
