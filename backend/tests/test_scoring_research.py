import datetime as dt

from app.db import Evidence, Niche, Opportunity, session_scope, get_setting, set_setting
from app.research import engine as R
from app.research.etsy_client import EtsyClient, EtsyNotConfigured, listing_metrics
from app.scoring import engine as S
from sqlalchemy import select
import pytest


def test_fees_match_etsy_schedule():
    # $0.20 listing + 6.5% + 3% + $0.25 on a $10 sale
    assert S.etsy_fees(10.0) == round(0.20 + 0.65 + 0.30 + 0.25, 2)
    assert S.profit_after_fees(10.0, 0.0) == round(10 - 1.40, 2)


def test_seasonal_window():
    v, why = S.seasonal_score("seasonal: Jan-Apr", dt.date(2026, 11, 15))
    assert v == 1.0 and "starts in" in why
    v2, _ = S.seasonal_score("seasonal: Jan-Apr", dt.date(2026, 7, 1))
    assert v2 < 0.5
    assert S.seasonal_score("evergreen")[0] == 0.75


def test_research_ranks_opportunities_with_required_fields():
    res = R.run_research(use_etsy=True)
    assert res["opportunities"] >= 10
    assert any("ETSY_API_KEY" in u for u in res["unavailable"])  # missing live data is reported, not faked
    with session_scope() as s:
        opps = s.scalars(select(Opportunity).order_by(Opportunity.score.desc())).all()
        top = opps[0]
        d = top.details
        for key in ("target_customer", "keywords", "price_range", "demand_evidence", "competition_assessment",
                    "estimated_production_cost", "suggested_price", "profit_per_sale", "design_style",
                    "why_attractive", "risks", "sources", "research_date"):
            assert key in d, key
        assert 0 <= top.score <= 100 and 0 <= top.confidence <= 100
        assert all(src["url"].startswith("http") for src in d["sources"])
        # no opportunity may claim observed prices when there are none
        for o in opps:
            if o.details["price_range"]["basis"] == "assumption":
                assert "ASSUMPTION" in o.details["price_range"]["note"]


def test_weights_change_ranking():
    base = get_setting("weights")
    set_setting("weights", {"demand": 0, "competition": 0, "profitability": 0, "automation": 100, "bundle": 0, "seasonal": 0})
    R.rank_all()
    with session_scope() as s:
        top = s.scalars(select(Opportunity).order_by(Opportunity.score.desc())).first()
        assert top.product_type == "budget_planner"  # highest automation feasibility
    set_setting("weights", base)
    R.rank_all()


def test_recommendations_are_producible_and_diverse():
    recs = R.recommend(5)
    assert recs and all(r["product_type"] != "not_supported_yet" for r in recs)


def test_csv_import_discovers_niche():
    csv = "keyword,searches,competition\nwedding seating chart template,8200,41000\nmushroom wall art print,5600,9000\n"
    res = R.import_keyword_csv(csv, "erank.csv")
    assert res["imported_rows"] == 2 and res["new_niches"] >= 1
    with session_scope() as s:
        n = s.scalar(select(Niche).where(Niche.slug == "mushroom-wall-art-print"))
        assert n is not None and n.discovered and n.parent_slug and n.analyst["product_types"] == ["wall_art_set"]


def test_etsy_metrics_from_api_response():
    now = 1_790_000_000
    resp = {"count": 45210, "results": [
        {"title": f"Item {i}", "url": f"https://www.etsy.com/listing/{i}", "price": {"amount": 1000 + i * 100, "divisor": 100},
         "num_favorers": 20 * i, "views": 300 * i, "tags": ["boho wall art", "printable art"], "type": "download",
         "original_creation_timestamp": now - 86400 * 30 * (i + 1)} for i in range(10)]}
    m = listing_metrics(resp, now=now)
    assert m["competing_listings"] == 45210 and m["price_median"] == 14.5
    assert m["top_tags"][0] in ("boho wall art", "printable art")
    assert "ESTIMATE" in m["estimated_monthly_sales_per_typical_listing"]["method"]


def test_etsy_client_requires_key():
    with pytest.raises(EtsyNotConfigured):
        EtsyClient()


def test_budget_blocks_overspend():
    from app.services import Budget, BudgetExceeded
    set_setting("budget", {"daily_usd": 0.05, "monthly_usd": 1.0})
    with pytest.raises(BudgetExceeded):
        Budget.check(0.10, "test image")
    Budget.check(0.01, "small call")
    set_setting("budget", {"daily_usd": 2.0, "monthly_usd": 20.0})


def test_research_with_mocked_etsy_api(monkeypatch):
    """Exercise the live-API path end to end with a recorded-style response (no network)."""
    import app.research.etsy_client as EC

    class Resp:
        status_code = 200
        text = ""
        def json(self):
            now = 1_790_000_000
            return {"count": 12000, "results": [
                {"title": f"Boho print {i}", "url": f"https://www.etsy.com/listing/{900 + i}",
                 "price": {"amount": 600 + i * 50, "divisor": 100}, "num_favorers": 40 + i * 10, "views": 900,
                 "tags": ["boho wall art", "terracotta sun print", "printable art"], "type": "download",
                 "original_creation_timestamp": now - 86400 * 200} for i in range(20)]}
    calls = []
    monkeypatch.setenv("ETSY_API_KEY", "testkey")
    monkeypatch.setattr(EC, "http_request", lambda *a, **k: calls.append(a) or Resp())
    res = R.run_research(use_etsy=True)
    assert any("etsy_api" in s for s in res["sources"]) and calls
    with session_scope() as s:
        n = s.scalar(select(Niche).where(Niche.slug == "abstract-boho-wall-art"))
        assert n.metrics["competing_listings"] == 12000 and n.metrics["price_median"]
        o = s.scalar(select(Opportunity).where(Opportunity.key == "abstract-boho-wall-art:wall_art_set"))
        assert o.details["price_range"]["basis"] == "observed" and o.confidence >= 50
        assert any(u.startswith("https://www.etsy.com/listing/9") for u in o.details["competitor_urls"])
        # recurring competitor tag discovered as a sub-niche
        assert s.scalar(select(Niche).where(Niche.slug == "terracotta-sun-print")) is not None
    monkeypatch.delenv("ETSY_API_KEY")
    from app.db import CacheEntry
    with session_scope() as s:
        s.query(CacheEntry).delete()
