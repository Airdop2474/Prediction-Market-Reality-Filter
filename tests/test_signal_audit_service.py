import unittest

from app.services.signal_audit_service import attach_audit_fields, audit_bucket


class SignalAuditServiceTests(unittest.TestCase):
    def test_strong_signal_with_clean_evidence_becomes_high_trust_audit(self):
        analysis = attach_audit_fields({
            "signal": "STRONG_LONG",
            "confidence_score": 0.72,
            "news_quality_score": 0.7,
            "evidence_strength": 0.5,
            "resolution_relevance_score": 0.5,
            "evidence_conflict_score": 0.2,
            "priced_in_risk_score": 40,
        })

        self.assertEqual(analysis["audit_verdict"], "HIGH_TRUST")
        self.assertEqual(audit_bucket(analysis), "review_queue")

    def test_trade_signal_with_weak_audit_dimensions_needs_review(self):
        analysis = attach_audit_fields({
            "signal": "LONG",
            "confidence_score": 0.55,
            "news_quality_score": 0.42,
            "evidence_strength": 0.22,
            "resolution_relevance_score": 0.25,
            "evidence_conflict_score": 0.55,
            "priced_in_risk_score": 75,
        })

        self.assertEqual(analysis["audit_verdict"], "REVIEW")
        self.assertEqual(audit_bucket(analysis), "review_queue")

    def test_watchlist_stays_observation_only(self):
        analysis = attach_audit_fields({"signal": "WATCHLIST"})

        self.assertEqual(analysis["audit_verdict"], "OBSERVE")
        self.assertEqual(audit_bucket(analysis), "observation_queue")


if __name__ == "__main__":
    unittest.main()
