import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import trade_journal_service as journal


class TradeJournalServiceTests(unittest.TestCase):
    def test_yes_trade_uses_yes_exit_price_for_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "trade_journal.json")
            with patch.object(journal, "_journal_path", return_value=path):
                trade = journal.open_trade(
                    market_question="Will BTC hit 100k?",
                    signal="LONG",
                    direction="YES",
                    entry_price=0.40,
                    amount_usd=100,
                    system_divergence=12,
                    system_confidence=0.7,
                    market_probability=40,
                    ai_probability=52,
                )

                closed = journal.close_trade(trade["id"], exit_price=0.70)

        self.assertEqual(closed["pnl_usd"], 75.0)
        self.assertEqual(closed["outcome"], "WIN")

    def test_no_trade_uses_inverse_yes_price_for_shares_and_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "trade_journal.json")
            with patch.object(journal, "_journal_path", return_value=path):
                trade = journal.open_trade(
                    market_question="Will BTC hit 100k?",
                    signal="SHORT",
                    direction="NO",
                    entry_price=0.70,
                    amount_usd=90,
                    system_divergence=-20,
                    system_confidence=0.8,
                    market_probability=70,
                    ai_probability=50,
                )

                closed = journal.close_trade(trade["id"], exit_price=0.20)

        self.assertEqual(trade["position_price"], 0.30)
        self.assertEqual(trade["shares"], 300.0)
        self.assertEqual(closed["exit_value_price"], 0.80)
        self.assertEqual(closed["pnl_usd"], 150.0)
        self.assertEqual(closed["outcome"], "WIN")


if __name__ == "__main__":
    unittest.main()
