import os
import unittest

from order_manager import OrderManager


class OrderManagerTests(unittest.TestCase):

    def setUp(self) -> None:
        self.filename = "test_orders.json"
        self.manager = OrderManager(self.filename)

    def tearDown(self) -> None:
        if os.path.exists(self.filename):
            os.remove(self.filename)

    def test_save_and_load(self) -> None:
        orders = [{"id": 1, "price": 100}, {"id": 2, "price": 200}]
        self.manager.save_orders(orders)
        loaded = self.manager.load_orders()
        self.assertEqual(loaded, orders)

    def test_load_corrupted_file_returns_empty(self) -> None:
        with open(self.filename, "w", encoding="utf-8") as handle:
            handle.write("BŁĄD")
        loaded = self.manager.load_orders()
        self.assertEqual(loaded, [])


if __name__ == "__main__":
    unittest.main()
