"""
India CSR Spend Tracker API.

Company-wise CSR spending reported to the Ministry of Corporate Affairs (National CSR Portal),
FY2014-15 to FY2023-24, by development sector, sub-sector, state and PSU status; peer
benchmarking; a curated table of unspent CSR transfers; and a livelihood & skilling
outcomes module built on a published impact assessment.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DF = pd.read_parquet(ROOT / "data" / "processed" / "csr.parquet")
POP = pd.read_csv(ROOT / "data" / "raw" / "census2011_population.csv").set_index("state_key")["population_2011"]
UNSPENT = pd.read_csv(ROOT / "data" / "unspent_csr.csv")
CASE = json.loads((ROOT / "data" / "skilling_case.json").read_text())
YEARS = sorted(DF.fy.cat.categories)
LATEST = YEARS[-1]
SECTORS = sorted(DF.sector.cat.categories)
NON_GEO = {"PAN India", "PAN India (Central Funds)", "Not Mentioned"}
VERSION = "1.0.0"
SOURCE = {
    "publisher": "Ministry of Corporate Affairs, Government of India",
    "portal": "National CSR Portal, https://www.csr.gov.in",
    "basis": "Project-level disclosures in e-form AOC-4 / CSR-2 (Section 135, Companies Act 2013)",
    "snapshot": "Portal export of 4 July 2026, as archived in github.com/2509Vaid/CSR-Analysis-CJSJ",
    "check": "FY2019-20 to FY2023-24 totals equal the Rs 1,44,159 crore stated by MCA in Rajya Sabha (PIB, 10 Feb 2026)",
}

app = FastAPI(
    title="India CSR Spend Tracker API",
    version=VERSION,
    description=(
        "Benchmark any Indian company's CSR spending against its peers. Data: Ministry of Corporate Affairs "
        "National CSR Portal, FY2014-15 to FY2023-24 (55,000+ companies, Rs 2.2 lakh crore), by development "
        "sector, sub-sector, state and PSU status. Also: curated unspent-CSR transfers and a livelihood & "
        "skilling outcomes calculator. Amounts in INR crore."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

FY = Query(None, description=f"Financial year, e.g. {LATEST}. Default: all years.", pattern=r"^\d{4}-\d{2}$")


def _fy(fy: str | None) -> pd.DataFrame:
    if fy is None:
        return DF
    if fy not in YEARS:
        raise HTTPException(400, f"Unknown fy '{fy}'. Available: {YEARS}")
    return DF[DF.fy == fy]


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def _share(s: pd.Series) -> list[dict]:
    tot = s.sum()
    return [{"name": k, "amount_cr": _r(v), "share": _r(v / tot, 4) if tot else None}
            for k, v in s.sort_values(ascending=False).items() if v != 0]


def _company(name: str) -> pd.DataFrame:
    q = name.strip().upper()
    sub = DF[DF.company == q]
    if sub.empty:
        cands = [c for c in DF.company.cat.categories if q in c]
        if len(cands) == 1:
            sub = DF[DF.company == cands[0]]
        else:
            raise HTTPException(404, {"error": f"No exact match for '{name}'",
                                      "did_you_mean": sorted(cands, key=len)[:10]})
    return sub


# ------------------------------------------------------------------------------- system
@app.get("/", tags=["System"])
def root():
    return {"name": "India CSR Spend Tracker API", "version": VERSION, "status": "operational", "docs": "/docs",
            "years": YEARS, "companies": int(DF.company.nunique()),
            "total_cr": _r(DF.amount_cr.sum()), "source": SOURCE,
            "endpoints": ["/overview", "/sectors", "/states", "/companies/search", "/companies/{name}",
                          "/benchmark", "/top", "/unspent", "/livelihood/case", "/livelihood/evaluate"]}


@app.get("/health", tags=["System"])
def health():
    return {"status": "healthy", "version": VERSION}


# ------------------------------------------------------------------------------- market
@app.get("/overview", tags=["Market"], summary="National CSR spend by year, with PSU split and growth")
def overview():
    rows = []
    prev = None
    for fy in YEARS:
        d = DF[DF.fy == fy]
        tot = float(d.amount_cr.sum())
        psu = float(d[d.psu == "PSU"].amount_cr.sum())
        rows.append({"fy": fy, "total_cr": _r(tot), "companies": int(d.company.nunique()),
                     "projects": int(d.projects.sum()), "psu_share": _r(psu / tot, 4),
                     "yoy": _r(tot / prev - 1, 4) if prev else None})
        prev = tot
    cagr = (rows[-1]["total_cr"] / rows[0]["total_cr"]) ** (1 / (len(rows) - 1)) - 1
    return {"years": rows, "cagr": _r(cagr, 4), "source": SOURCE}


@app.get("/sectors", tags=["Market"], summary="Spend by development sector (or sub-sector)")
def sectors(fy: str | None = FY, level: Literal["sector", "sub_sector"] = "sector",
            psu: Literal["PSU", "Non-PSU"] | None = None):
    d = _fy(fy)
    if psu:
        d = d[d.psu == psu]
    return {"fy": fy or "all", "level": level, "psu": psu or "all",
            "total_cr": _r(d.amount_cr.sum()),
            "items": _share(d.groupby(level, observed=True).amount_cr.sum())}


@app.get("/states", tags=["Market"], summary="Spend by state, with per-resident spend (Census 2011)")
def states(fy: str | None = FY, sector: str | None = Query(None, description="Sector name from /sectors")):
    d = _fy(fy)
    if sector:
        if sector not in SECTORS:
            raise HTTPException(400, f"Unknown sector. Valid: {SECTORS}")
        d = d[d.sector == sector]
    s = d.groupby("state", observed=True).amount_cr.sum()
    tot = s.sum()
    items = []
    for state, v in s.sort_values(ascending=False).items():
        pop = POP.get(state.lower())
        items.append({"state": state, "amount_cr": _r(v), "share": _r(v / tot, 4) if tot else None,
                      "inr_per_resident": _r(v * 1e7 / pop, 1) if pop and state not in NON_GEO else None})
    geo = [i for i in items if i["state"] not in NON_GEO]
    top5 = sum(i["amount_cr"] for i in geo[:5])
    return {"fy": fy or "all", "sector": sector or "all", "total_cr": _r(tot),
            "not_location_specific_share": _r(sum(i["amount_cr"] for i in items if i["state"] in NON_GEO) / tot, 4),
            "top5_states_share_of_located_spend": _r(top5 / sum(i["amount_cr"] for i in geo), 4) if geo else None,
            "items": items,
            "note": "District-level data is not in the portal export used here; PAN India and Not Mentioned "
                    "are reported by companies and cannot be placed in a state."}


@app.get("/top", tags=["Market"], summary="Largest CSR spenders, filterable")
def top(fy: str | None = Query(LATEST, pattern=r"^\d{4}-\d{2}$"), sector: str | None = None,
        state: str | None = None, psu: Literal["PSU", "Non-PSU"] | None = None,
        limit: int = Query(20, ge=1, le=200)):
    d = _fy(fy)
    if sector:
        d = d[d.sector == sector]
    if state:
        d = d[d.state.astype(str).str.lower() == state.lower()]
    if psu:
        d = d[d.psu == psu]
    s = d.groupby("company", observed=True).amount_cr.sum().sort_values(ascending=False)
    tot = s.sum()
    return {"fy": fy or "all", "filters": {"sector": sector, "state": state, "psu": psu},
            "companies_in_filter": int((s > 0).sum()), "total_cr": _r(tot),
            "top_n_share": _r(s.head(limit).sum() / tot, 4) if tot else None,
            "items": [{"rank": i + 1, "company": c, "amount_cr": _r(v)} for i, (c, v) in enumerate(s.head(limit).items())]}


# ------------------------------------------------------------------------------- companies
@app.get("/companies/search", tags=["Companies"], summary="Find a company's exact name")
def search(q: str = Query(..., min_length=3, examples=["TATA STEEL"]), limit: int = Query(20, ge=1, le=100)):
    qq = q.strip().upper()
    names = [c for c in DF.company.cat.categories if qq in c]
    totals = DF[DF.company.isin(names)].groupby("company", observed=True).amount_cr.sum()
    names.sort(key=lambda c: -totals.get(c, 0))
    return {"query": q, "count": len(names),
            "items": [{"company": c, "total_cr_all_years": _r(totals.get(c, 0))} for c in names[:limit]]}


@app.get("/companies/{name}", tags=["Companies"], summary="A company's CSR profile: trend, sectors, states")
def company(name: str, fy: str | None = FY):
    sub = _company(name)
    cname = str(sub.company.iloc[0])
    trend = sub.groupby("fy", observed=True).amount_cr.sum()
    d = sub if fy is None else sub[sub.fy == fy]
    if d.empty:
        raise HTTPException(404, f"{cname} reported no CSR projects in {fy}. Years with data: {list(trend.index)}")
    return {"company": cname, "psu": str(sub.psu.mode().iloc[0]), "fy": fy or "all",
            "total_cr": _r(d.amount_cr.sum()), "projects": int(d.projects.sum()),
            "trend": [{"fy": k, "amount_cr": _r(v)} for k, v in trend.items()],
            "sectors": _share(d.groupby("sector", observed=True).amount_cr.sum()),
            "sub_sectors": _share(d.groupby("sub_sector", observed=True).amount_cr.sum())[:10],
            "states": _share(d.groupby("state", observed=True).amount_cr.sum())[:15],
            "source": SOURCE["portal"]}


@app.get("/benchmark", tags=["Companies"], summary="Compare a company's CSR mix with its peers")
def benchmark(company: str = Query(..., examples=["TATA STEEL LIMITED"]),
              fy: str = Query(LATEST, pattern=r"^\d{4}-\d{2}$"),
              peers: Literal["top100", "all", "psu", "non_psu"] = "top100",
              peer_companies: str | None = Query(None, description="Comma-separated exact names; overrides `peers`")):
    d = _fy(fy)
    sub = _company(company)
    cname = str(sub.company.iloc[0])
    mine = d[d.company == cname]
    if mine.empty:
        raise HTTPException(404, f"{cname} reported no CSR projects in {fy}")
    by_co = d.groupby("company", observed=True).amount_cr.sum().sort_values(ascending=False)
    if peer_companies:
        names = [p.strip().upper() for p in peer_companies.split(",") if p.strip()]
        missing = [n for n in names if n not in by_co.index]
        if missing:
            raise HTTPException(404, f"Not found in {fy}: {missing}. Use /companies/search")
        group, label = names, f"{len(names)} named peers"
    elif peers == "top100":
        group, label = list(by_co.head(100).index), f"top 100 spenders in {fy}"
    elif peers == "psu":
        group, label = list(d[d.psu == "PSU"].company.unique()), f"all PSUs in {fy}"
    elif peers == "non_psu":
        group, label = list(d[d.psu == "Non-PSU"].company.unique()), f"all non-PSUs in {fy}"
    else:
        group, label = list(by_co.index), f"all companies in {fy}"
    group = [g for g in group if g != cname]
    peer = d[d.company.isin(group)]

    def mix(x, col):
        s = x.groupby(col, observed=True).amount_cr.sum()
        return s / s.sum() if s.sum() else s

    m_sec, p_sec = mix(mine, "sector"), mix(peer, "sector")
    secs = sorted(set(m_sec.index) | set(p_sec.index), key=lambda k: -(m_sec.get(k, 0) + p_sec.get(k, 0)))
    sector_cmp = [{"sector": s, "company_share": _r(m_sec.get(s, 0), 4), "peer_share": _r(p_sec.get(s, 0), 4),
                   "difference_pp": _r((m_sec.get(s, 0) - p_sec.get(s, 0)) * 100, 1)} for s in secs]
    over = max(sector_cmp, key=lambda r: r["difference_pp"])
    under = min(sector_cmp, key=lambda r: r["difference_pp"])
    m_st = mix(mine[~mine.state.isin(NON_GEO)], "state")
    total = float(mine.amount_cr.sum())
    peer_totals = by_co[by_co.index.isin(group)]
    return {
        "company": cname, "fy": fy, "peer_group": label, "peer_count": len(group),
        "company_total_cr": _r(total),
        "rank_among_all_companies": int((by_co > total).sum()) + 1,
        "peer_median_cr": _r(peer_totals.median()) if len(peer_totals) else None,
        "sector_comparison": sector_cmp,
        "most_overweight": {"sector": over["sector"], "pp": over["difference_pp"]},
        "most_underweight": {"sector": under["sector"], "pp": under["difference_pp"]},
        "company_sector_concentration_hhi": _r(float((m_sec ** 2).sum()), 3),
        "company_top_states": [{"state": k, "share": _r(v, 4)} for k, v in m_st.sort_values(ascending=False).head(5).items()],
        "not_location_specific_share": _r(float(mine[mine.state.isin(NON_GEO)].amount_cr.sum()) / total, 4) if total else None,
    }


# ------------------------------------------------------------------------------- unspent
@app.get("/unspent", tags=["Unspent CSR"], summary="Curated unspent CSR transfers (Section 135(6))")
def unspent(psu: Literal["PSU", "Non-PSU"] | None = None):
    u = UNSPENT if psu is None else UNSPENT[UNSPENT.psu == psu]
    rows = []
    for r in u.itertuples():
        rows.append({"company": r.company, "fy": r.fy, "sector": r.sector, "psu": r.psu,
                     "obligation_cr": r.obligation_cr, "spent_cr": r.spent_cr,
                     "unspent_transferred_cr": r.unspent_transferred_cr,
                     "unspent_share_of_obligation": _r(r.unspent_transferred_cr / r.obligation_cr, 3),
                     "transfer_date": r.transfer_date, "reason": r.reason,
                     "primary_source": r.primary_source, "source_url": r.report_url})
    rows.sort(key=lambda x: -x["unspent_share_of_obligation"])
    return {
        "count": len(rows),
        "total_unspent_cr": _r(sum(r["unspent_transferred_cr"] for r in rows)),
        "rule": ("Section 135(6): CSR money not spent on an ongoing project by year-end must be moved to an "
                 "Unspent CSR Account within 30 days and spent within 3 years; other unspent money goes to a "
                 "Schedule VII fund within 6 months."),
        "coverage_note": ("MCA publishes no bulk company-wise unspent data. These are individual company "
                          "disclosures, collected from annual reports via India CSR; check each against the "
                          "company's annual report before citing."),
        "items": rows,
    }


# ------------------------------------------------------------------------------- livelihood
def _kpis(opex_cr, trained, placed, seeking=None, inc_before=None, inc_after=None, csr_cr=None):
    out = {
        "placement_rate_of_trained": _r(placed / trained, 4) if trained else None,
        "placement_rate_of_job_seekers": _r(placed / seeking, 4) if seeking else None,
        "cost_per_trainee_inr": _r(opex_cr * 1e7 / trained, 0) if trained else None,
        "cost_per_placement_inr": _r(opex_cr * 1e7 / placed, 0) if placed else None,
    }
    if csr_cr is not None and placed:
        out["csr_cost_per_placement_inr"] = _r(csr_cr * 1e7 / placed, 0)
    if inc_before is not None and inc_after is not None:
        gain = inc_after - inc_before
        out["monthly_income_gain_inr"] = _r(gain, 0)
        out["income_change"] = _r(gain / inc_before, 4) if inc_before else None
        out["annual_income_gain_per_placed_inr"] = _r(gain * 12, 0)
        if placed and gain > 0:
            out["payback_months_on_cost_per_placement"] = _r(opex_cr * 1e7 / placed / gain, 1)
            out["first_year_income_gain_per_rupee_spent"] = _r(gain * 12 * placed / (opex_cr * 1e7), 2)
    return out


@app.get("/livelihood/case", tags=["Livelihood & skilling"],
         summary="Published case: SDI Bhubaneswar (IndianOil-led CSR), outcomes and costs")
def livelihood_case():
    i = CASE["inputs"]
    k = _kpis(i["opex_cr"], i["trained"], i["placed"], i["seeking_job"],
              i["income_before_monthly_inr"], i["income_after_monthly_inr"], i["csr_grant_cr"])
    partners = []
    for p in CASE["partners"]:
        partners.append({**p, "placement_rate_of_job_seekers": _r(p["placed"] / p["seeking_job"], 4),
                         "placement_rate_of_trained": _r(p["placed"] / p["trained"], 4)})
    ret = CASE["retention_working_alumni"]
    over_1y = (ret["1_2y"] + ret["2_3y"] + ret["gt_3y"]) / ret["n"]
    return {
        "programme": CASE["programme"], "funder": CASE["funder"], "location": CASE["location"], "year": CASE["year"],
        "inputs": i, "kpis": k, "partners": partners,
        "retention": {**ret, "share_employed_over_1_year": _r(over_1y, 3)},
        "reading_the_numbers": [
            f"The headline placement rate ({k['placement_rate_of_job_seekers']:.0%}) counts placements against "
            f"trainees who sought jobs; against everyone trained it is {k['placement_rate_of_trained']:.0%}, and "
            f"the alumni survey found {i['alumni_employed_share']:.0%} in salaried work.",
            f"Total cost per placement is Rs {k['cost_per_placement_inr']:,.0f}; the CSR grant alone covered "
            f"Rs {k['csr_cost_per_placement_inr']:,.0f} of it; course fees, other income and gap funding covered the rest.",
            f"At a Rs {k['monthly_income_gain_inr']:,.0f} monthly income gain, cost per placement is recovered "
            f"in about {k['payback_months_on_cost_per_placement']:.0f} months of the trainee's extra earnings.",
            "Cisco courses placed 5 of 23 job-seekers (22%), far below every other partner.",
        ],
        "source": CASE["source"],
    }


class Programme(BaseModel):
    name: str = Field("My skilling programme")
    total_cost_cr: float = Field(..., gt=0, description="Programme cost in INR crore", examples=[2.5])
    csr_contribution_cr: float | None = Field(None, ge=0, examples=[1.5])
    trained: int = Field(..., gt=0, examples=[400])
    placed: int = Field(..., ge=0, examples=[260])
    seeking_job: int | None = Field(None, gt=0, examples=[350])
    income_before_monthly_inr: float | None = Field(None, ge=0, examples=[6000])
    income_after_monthly_inr: float | None = Field(None, ge=0, examples=[14000])


@app.post("/livelihood/evaluate", tags=["Livelihood & skilling"],
          summary="Compute outcome KPIs for any programme and compare with the SDI case")
def livelihood_evaluate(p: Programme):
    if p.placed > p.trained:
        raise HTTPException(422, "placed cannot exceed trained")
    if p.seeking_job and p.placed > p.seeking_job:
        raise HTTPException(422, "placed cannot exceed seeking_job")
    mine = _kpis(p.total_cost_cr, p.trained, p.placed, p.seeking_job,
                 p.income_before_monthly_inr, p.income_after_monthly_inr, p.csr_contribution_cr)
    i = CASE["inputs"]
    ref = _kpis(i["opex_cr"], i["trained"], i["placed"], i["seeking_job"],
                i["income_before_monthly_inr"], i["income_after_monthly_inr"], i["csr_grant_cr"])
    cmp_ = {k: {"yours": v, "sdi_bhubaneswar": ref.get(k)} for k, v in mine.items() if v is not None}
    return {"programme": p.name, "kpis": mine, "vs_reference_case": cmp_,
            "reference": CASE["programme"] + ", " + CASE["year"]}
