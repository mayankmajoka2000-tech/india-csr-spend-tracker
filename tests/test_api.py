import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# MCA, Rajya Sabha written reply, PIB 10 Feb 2026
PIB = {"2019-20": 24965.82, "2020-21": 26210.95, "2021-22": 27141.45, "2022-23": 30932.08, "2023-24": 34908.75}


def test_every_get_endpoint_without_params():
    for path in ["/", "/health", "/overview", "/sectors", "/states", "/top", "/unspent",
                 "/livelihood/case", "/companies/search?q=TATA"]:
        assert client.get(path).status_code == 200, path


def test_totals_match_government_figures():
    years = {y["fy"]: y["total_cr"] for y in client.get("/overview").json()["years"]}
    for fy, v in PIB.items():
        assert abs(years[fy] - v) < 0.01, fy
    assert abs(sum(PIB[f] for f in PIB) - 144159.05) < 0.01


def test_sector_shares_sum_to_one():
    b = client.get("/sectors", params={"fy": "2023-24"}).json()
    assert abs(sum(i["share"] for i in b["items"]) - 1) < 1e-3
    assert abs(b["total_cr"] - PIB["2023-24"]) < 0.01
    sub = client.get("/sectors", params={"fy": "2023-24", "level": "sub_sector"}).json()
    assert abs(sub["total_cr"] - b["total_cr"]) < 0.01


def test_bad_inputs():
    assert client.get("/sectors", params={"fy": "2030-31"}).status_code == 400
    assert client.get("/states", params={"sector": "Nope"}).status_code == 400
    assert client.get("/companies/ZZZZ NO SUCH CO").status_code == 404


def test_states_per_capita():
    b = client.get("/states", params={"fy": "2023-24"}).json()
    mh = next(i for i in b["items"] if i["state"] == "Maharashtra")
    assert mh["inr_per_resident"] == round(mh["amount_cr"] * 1e7 / 112374333, 1)
    pan = next(i for i in b["items"] if i["state"] == "PAN India")
    assert pan["inr_per_resident"] is None


def test_company_profile_and_benchmark():
    name = client.get("/top", params={"fy": "2023-24", "limit": 1}).json()["items"][0]["company"]
    prof = client.get(f"/companies/{name}", params={"fy": "2023-24"}).json()
    assert prof["total_cr"] > 0 and abs(sum(s["share"] for s in prof["sectors"]) - 1) < 1e-3
    bm = client.get("/benchmark", params={"company": name, "fy": "2023-24"}).json()
    assert bm["rank_among_all_companies"] == 1
    assert bm["peer_count"] == 99
    assert abs(sum(r["company_share"] for r in bm["sector_comparison"]) - 1) < 1e-3
    assert abs(sum(r["peer_share"] for r in bm["sector_comparison"]) - 1) < 1e-3


def test_top_filters():
    b = client.get("/top", params={"fy": "2023-24", "psu": "PSU", "limit": 5}).json()
    assert len(b["items"]) == 5
    amts = [i["amount_cr"] for i in b["items"]]
    assert amts == sorted(amts, reverse=True)


def test_unspent():
    b = client.get("/unspent").json()
    assert b["count"] == 8
    assert b["items"][0]["company"].startswith("Gujarat Narmada")  # 17.32/22.54 = 77%
    for r in b["items"]:
        assert r["unspent_transferred_cr"] <= r["obligation_cr"]


def test_livelihood_case_numbers():
    k = client.get("/livelihood/case").json()["kpis"]
    assert k["placement_rate_of_job_seekers"] == round(857 / 910, 4)
    assert k["placement_rate_of_trained"] == round(857 / 1007, 4)
    assert k["cost_per_placement_inr"] == round(14.99e7 / 857)
    assert k["income_change"] == round(15000 / 7000, 4)


def test_livelihood_evaluate():
    body = {"total_cost_cr": 2.5, "csr_contribution_cr": 1.5, "trained": 400, "placed": 260,
            "seeking_job": 350, "income_before_monthly_inr": 6000, "income_after_monthly_inr": 14000}
    b = client.post("/livelihood/evaluate", json=body).json()
    assert b["kpis"]["cost_per_placement_inr"] == round(2.5e7 / 260)
    assert "sdi_bhubaneswar" in b["vs_reference_case"]["placement_rate_of_trained"]
    bad = {**body, "placed": 500}
    assert client.post("/livelihood/evaluate", json=bad).status_code == 422


def test_cofunding_defaults_and_model():
    for pr in ("awd", "agroforestry"):
        assert client.get("/cofunding/defaults", params={"practice": pr}).status_code == 200
        b = client.post("/cofunding/model", json={"practice": pr}).json()
        rows = b["years"]
        assert len(rows) == 10 and rows[0]["credits_sold_t"] == 0      # nothing sold before first issuance
        s = b["summary"]
        assert s["csr_total_needed_inr"] == sum(r["csr_needed_inr"] for r in rows) or \
            abs(s["csr_total_needed_inr"] - sum(r["csr_needed_inr"] for r in rows)) <= 10
        for r in rows:   # farmers get their share of revenue exactly
            assert abs(r["farmer_payments_inr"] - 0.6 * r["credit_revenue_inr"]) <= 1


def test_awd_credits_follow_ipcc_defaults():
    s = client.post("/cofunding/model", json={"practice": "awd"}).json()["summary"]
    expected = 0.85 * 110 * (1 - 0.55) / 1000 * 28 * 0.8 * (1 - 0.15)
    assert abs(s["credits_per_ha_per_year_t"] - round(expected, 3)) < 1e-6


def test_cofunding_breakeven_consistent():
    s = client.post("/cofunding/model", json={"practice": "agroforestry"}).json()["summary"]
    be = s["breakeven_price_usd"]
    above = client.post("/cofunding/model", json={"practice": "agroforestry", "price_usd": be + 1, "years": 20}).json()
    assert above["years"][-1]["csr_needed_inr"] == 0
    below = client.post("/cofunding/model", json={"practice": "agroforestry", "price_usd": be - 1, "years": 20}).json()
    assert below["years"][-1]["csr_needed_inr"] > 0


def test_cofunding_override_and_validation():
    hi = client.post("/cofunding/model", json={"practice": "awd", "credits_per_ha_override": 5}).json()["summary"]
    lo = client.post("/cofunding/model", json={"practice": "awd"}).json()["summary"]
    assert hi["csr_total_needed_inr"] < lo["csr_total_needed_inr"]
    assert client.post("/cofunding/model", json={"practice": "awd", "farmer_share": 1.5}).status_code == 422
    assert client.post("/cofunding/model", json={"practice": "awd", "first_issuance_year": 40}).status_code == 422
    sc = client.get("/cofunding/scenarios", params={"practice": "awd"}).json()
    assert len(sc["rows"]) == 15


def test_calculator_page():
    r = client.get("/calculator")
    assert r.status_code == 200 and "Farmer Carbon Co-Funding Calculator" in r.text
