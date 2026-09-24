"""MySQL integration tests for concurrent ticket purchases.

Set TEST_DATABASE_URL to a disposable MySQL database whose name ends in
``_test`` before running ``python -m unittest``. The tests clear sale and ticket
rows in that database.
"""

from __future__ import annotations

import asyncio
import os
import unittest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    # app.database constructs its engine during import.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from app.database import SessionLocal, init_db
from app.invariants import check_invariants
from app.main import BuyRequest, buy_ticket, get_status
from app.models import Sale, Ticket


_TEST_DB_IS_SAFE = bool(
    TEST_DATABASE_URL
    and make_url(TEST_DATABASE_URL).database
    and make_url(TEST_DATABASE_URL).database.lower().endswith("_test")
)


@unittest.skipUnless(
    _TEST_DB_IS_SAFE,
    "set TEST_DATABASE_URL to a disposable MySQL database ending in _test",
)
class ConcurrentBuyTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()

    def setUp(self) -> None:
        with SessionLocal.begin() as session:
            session.execute(delete(Ticket))
            session.execute(delete(Sale))
            session.add(Sale(total_tickets=30, sold_count=0))

    async def _concurrent_buys(self, count: int, request_id_factory):
        return await asyncio.gather(*(
            asyncio.to_thread(
                buy_ticket,
                BuyRequest(user_id=f"user-{i}", request_id=request_id_factory(i)),
            )
            for i in range(count)
        ), return_exceptions=True)

    async def test_parallel_buyers_never_oversell_or_duplicate_ticket_numbers(self) -> None:
        results = await self._concurrent_buys(80, lambda i: f"request-{i}")
        successes = [result for result in results if isinstance(result, dict)]
        sold_out = [result for result in results if isinstance(result, HTTPException)
                    and result.status_code == 409]

        self.assertEqual(len(successes), 30)
        self.assertEqual(len(sold_out), 50)
        snapshot = get_status()
        self.assertEqual(check_invariants(snapshot), [])
        self.assertEqual(len({result["ticket_number"] for result in successes}), 30)

    async def test_concurrent_duplicate_request_ids_issue_one_ticket(self) -> None:
        results = await self._concurrent_buys(40, lambda _i: "same-request")

        self.assertTrue(all(isinstance(result, dict) for result in results), results)
        self.assertEqual(len({result["ticket_number"] for result in results}), 1)
        snapshot = get_status()
        self.assertEqual(len(snapshot["issued_tickets"]), 1)
        self.assertEqual(check_invariants(snapshot), [])

    async def test_simultaneous_final_ticket_is_sold_once(self) -> None:
        with SessionLocal.begin() as session:
            sale = session.scalar(select(Sale).limit(1))
            self.assertIsNotNone(sale)
            sale.total_tickets = 1

        results = await self._concurrent_buys(40, lambda i: f"last-{i}")
        successes = [result for result in results if isinstance(result, dict)]
        sold_out = [result for result in results if isinstance(result, HTTPException)
                    and result.status_code == 409]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(sold_out), 39)
        self.assertEqual(check_invariants(get_status()), [])
if __name__ == "__main__":
    unittest.main()
