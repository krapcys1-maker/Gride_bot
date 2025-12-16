import unittest

from grid_logic import GridCalculator


class GridCalculatorTests(unittest.TestCase):

    def test_normal_grid(self):
        calc = GridCalculator(lower_price=100.0, upper_price=200.0, grid_levels=4)
        result = calc.calculate_levels()
        self.assertEqual(len(result), 5)
        self.assertEqual(result, [100.0, 125.0, 150.0, 175.0, 200.0])

    def test_float_precision(self):
        calc = GridCalculator(lower_price=0.1, upper_price=0.2, grid_levels=5)
        result = calc.calculate_levels()
        self.assertEqual(len(result), 6)
        for value in result:
            # Ensure there aren't spurious floating-point artifacts
            self.assertEqual(value, round(value, 10))
        self.assertEqual(result[0], 0.1)
        self.assertEqual(result[-1], 0.2)

    def test_validation_errors(self):
        with self.assertRaises(ValueError):
            GridCalculator(lower_price=-1.0, upper_price=1.0, grid_levels=3)
        with self.assertRaises(ValueError):
            GridCalculator(lower_price=5.0, upper_price=4.0, grid_levels=3)
        with self.assertRaises(ValueError):
            GridCalculator(lower_price=1.0, upper_price=2.0, grid_levels=0)

    def test_single_level(self):
        calc = GridCalculator(lower_price=50.0, upper_price=60.0, grid_levels=1)
        result = calc.calculate_levels()
        self.assertEqual(result, [50.0, 60.0])


if __name__ == "__main__":
    unittest.main()
