import unittest

from pricing import apply_discount, line_total


class LineTotalTest(unittest.TestCase):
    def test_multiplies_price_by_quantity(self):
        self.assertEqual(line_total(250, 4), 1000)


class ApplyDiscountTest(unittest.TestCase):
    def test_takes_percentage_off(self):
        self.assertEqual(apply_discount(1000, 10), 900)


if __name__ == "__main__":
    unittest.main()
