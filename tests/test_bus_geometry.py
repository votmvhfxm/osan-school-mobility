import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from bus_geometry import align_stations, cumulative_lengths, distances

def stations(points):
    return [{"seq": i + 1, "y": y, "x": x} for i, (y, x) in enumerate(points)]

class RouteGeometryTests(unittest.TestCase):
    def test_outbound_and_return_on_same_road_stay_in_sequence(self):
        shape = [[37, 127], [37, 127.001], [37, 127.002], [37, 127.001], [37, 127]]
        aligned = align_stations(stations(shape), shape)
        self.assertEqual(list(aligned.values()), [0, 1, 2, 3, 4])

    def test_loop_does_not_snap_final_stop_to_start(self):
        shape = [[37, 127], [37.001, 127], [37.001, 127.001], [37, 127.001], [37, 127]]
        self.assertEqual(align_stations(stations(shape), shape)[5], 4)

    def test_far_or_absent_geometry_is_not_fabricated(self):
        self.assertEqual(align_stations(stations([[37, 127]]), []), {})
        self.assertEqual(align_stations(stations([[38, 128]]), [[37, 127], [37.001, 127]]), {})

    def test_ride_distance_follows_road_bend_instead_of_diagonal(self):
        shape = [[37, 127], [37.001, 127], [37.001, 127.001]]
        along_road = cumulative_lengths(shape)[-1]
        diagonal = distances(shape[0], [shape[-1]])[0]
        self.assertGreater(along_road, diagonal * 1.3)

