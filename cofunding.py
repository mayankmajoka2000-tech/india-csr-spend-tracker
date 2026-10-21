"""
CSR + carbon co-funding model for farmer carbon projects.

Question it answers: how much CSR money does a farmer carbon project need, and for how long,
before carbon-credit revenue can carry it?

Two practices:
- "awd"         Alternate wetting and drying in irrigated rice (cuts methane).
- "agroforestry" Trees on farm land (removes CO2).

Every parameter has a default with a source or an explicit "assumption" label, and every default
can be overridden by the caller. Money in INR; carbon price in USD converted at `fx_inr_per_usd`.

CSR rule built in: under Rule 7(2) of the Companies (CSR Policy) Rules 2014 (as amended 2021) and
MCA FAQ 55, any surplus arising from CSR activities cannot become the company's business profit;
it must be ploughed back into the project, moved to the Unspent CSR Account or a Schedule VII fund.
So in this model credit revenue first repays nothing to the company: it goes to farmers (their
share) and then to the project's own costs; anything left is reported as surplus to plough back.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

SOURCES = {
    "ipcc_awd": ("Gold Standard methodology 'Methane emission reduction by adjusted water management practice in "
                 "rice cultivation' v1.0 (IPCC 2019 Refinement defaults): India baseline 0.85 kg CH4/ha/day; "
                 "scaling factor 0.55 for multiple drainage (AWD); GWP 28; 15% uncertainty deduction. "
                 "https://globalgoals.goldstandard.org/standards/437_V1.0_LUF_AGR_Methane-emission-reduction-by-AWM-practice-in-rice-cultivation.pdf"),
    "rmi_rice": ("RMI, 'Technical explainer: carbon credits for improved rice cultivation': AWD cuts methane ~53%; "
                 "newer methodologies projected at 4-6 credits per hectare; Verra invalidated 37 rice projects "
                 "(4.5 mn credits) on additionality. https://rmi.org/technical-explainer-carbon-credits-for-improved-rice-cultivation/"),
    "rice_price": ("Quantum Commodity Intelligence, 7 Mar 2024: legacy rice credits $5-12/t; next-generation "
                   "(remote-sensing verified) $20-25/t. https://www.qcintel.com/carbon/article/analysis-next-generation-rice-methane-carbon-credits-set-to-double-in-price-22192.html"),
    "crida": ("ICAR-CRIDA, 'Promotion of dryland horticulture for higher carbon credits' (Verra VM0047 project "
              "description, Chitradurga, Karnataka): 15,600 mango/cashew/guava/tamarind trees, 1,373 tCO2e/yr, "
              "first partial year 573 t; planting Rs 200/tree, management Rs 50/tree. "
              "https://www.icar-crida.res.in/assets_c/img/Research/Externally_Funded/Pilot-project-VCM-2025.pdf"),
    "rajasthan": ("Chavan et al. (2021), Environment, Development and Sustainability 23(3): traditional "
                  "agroforestry on Rajasthan farms averages 0.95 tCO2e/ha/yr. "
                  "https://ideas.repec.org/a/spr/endesu/v23y2021i3d10.1007_s10668-020-00788-w.html"),
    "verra_fees": "Verra fee schedule: $2,500 registration review; $0.20 per VCU issued. https://verra.org/verra-publishes-updated-fee-schedules/",
    "csr_surplus": ("Companies (CSR Policy) Rules 2014, Rule 7(2) as amended 22 Jan 2021; MCA CSR FAQ Q.55: surplus "
                    "from CSR activities shall not form part of business profit. "
                    "https://taxguru.in/company-law/faqs-csr-22-jan-2021-amenments-mca.html"),
}


@dataclass
class Params:
    practice: str = "awd"                      # "awd" | "agroforestry"
    hectares: float = 2000.0
    farmers: int = 1500
    years: int = 10
    # carbon
    price_usd: float = 15.0                    # mid of $5-12 legacy and $20-25 next-gen [rice_price]
    price_growth: float = 0.0                  # annual real price change (assumption)
    fx_inr_per_usd: float = 88.0               # assumption, Oct 2026
    buffer_share: float = 0.0                  # set by practice below unless given
    first_issuance_year: int = 2               # credits for year t are sold in year t + (this - 1)  (assumption)
    farmer_share: float = 0.6                  # share of credit revenue paid to farmers (assumption)
    # AWD
    baseline_ch4_kg_ha_day: float = 0.85       # [ipcc_awd] India
    awd_scaling_factor: float = 0.55           # [ipcc_awd]
    season_days: int = 110                     # flooded days per season (assumption)
    seasons_per_year: int = 1                  # kharif only (assumption)
    gwp_ch4: float = 28.0                      # [ipcc_awd]
    uncertainty_deduction: float = 0.15        # [ipcc_awd]
    adoption_rate: float = 0.8                 # share of enrolled area actually practising AWD (assumption)
    # agroforestry
    trees_per_ha: int = 100                    # orchard spacing ~10 m x 10 m (assumption)
    tco2e_per_tree_yr: float = 1373 / 15600    # [crida] = 0.088
    tree_survival: float = 0.8                 # (assumption)
    years_to_full_sequestration: int = 3       # linear ramp-up (assumption)
    # costs (INR)
    upfront_per_ha: float | None = None        # set by practice below unless given
    annual_per_ha: float | None = None
    project_development: float = 1_500_000     # feasibility, PDD, baseline, legal (assumption)
    validation: float = 1_200_000              # one-off VVB validation (assumption)
    verification_per_event: float = 900_000    # per issuance (assumption)
    registry_fixed_usd: float = 2_500          # [verra_fees]
    registry_per_credit_usd: float = 0.20      # [verra_fees]
    credits_per_ha_override: float | None = None  # net t/ha/yr; replaces the calculation (e.g. measured baselines)
    csr_budget: float | None = None            # optional: check if a stated CSR budget is enough
    notes: list = field(default_factory=list)

    def resolve(self) -> "Params":
        p = self.practice
        if p not in ("awd", "agroforestry"):
            raise ValueError("practice must be 'awd' or 'agroforestry'")
        if self.buffer_share == 0.0:
            self.buffer_share = 0.0 if p == "awd" else 0.15      # AFOLU non-permanence buffer (assumption)
        if self.upfront_per_ha is None:
            # AWD: field water tubes, training, farmer onboarding (assumption).
            # Agroforestry: Rs 200/tree planting [crida] x trees_per_ha, + fencing/irrigation assumption Rs 5,000/ha.
            self.upfront_per_ha = 1_500.0 if p == "awd" else 200.0 * self.trees_per_ha + 5_000.0
        if self.annual_per_ha is None:
            # AWD: extension + remote-sensing MRV (assumption). Agroforestry: Rs 50/tree management [crida].
            self.annual_per_ha = 800.0 if p == "awd" else 50.0 * self.trees_per_ha
        for name in ("farmer_share", "buffer_share", "uncertainty_deduction", "adoption_rate", "tree_survival"):
            v = getattr(self, name)
            if not 0 <= v <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.years < 1 or self.years > 30:
            raise ValueError("years must be 1-30")
        if self.first_issuance_year < 1 or self.first_issuance_year > self.years:
            raise ValueError("first_issuance_year must be within the horizon")
        return self


def credits_per_ha(p: Params, year: int) -> float:
    """Net creditable tCO2e per hectare generated in project year `year` (1-based)."""
    if p.credits_per_ha_override is not None:
        return p.credits_per_ha_override
    if p.practice == "awd":
        reduction_kg = p.baseline_ch4_kg_ha_day * p.season_days * p.seasons_per_year * (1 - p.awd_scaling_factor)
        gross = reduction_kg / 1000 * p.gwp_ch4 * p.adoption_rate
        return gross * (1 - p.uncertainty_deduction) * (1 - p.buffer_share)
    ramp = min(year / p.years_to_full_sequestration, 1.0)
    gross = p.trees_per_ha * p.tree_survival * p.tco2e_per_tree_yr * ramp
    return gross * (1 - p.buffer_share)


def run(params: Params) -> dict:
    p = params.resolve()
    lag = p.first_issuance_year - 1
    generated = [credits_per_ha(p, y) * p.hectares for y in range(1, p.years + 1)]
    rows, cum_gap, cum_csr, max_gap = [], 0.0, 0.0, 0.0
    total = {k: 0.0 for k in ("costs", "revenue", "farmer_payments", "csr_needed", "surplus", "credits_sold")}
    breakeven_year = None
    for y in range(1, p.years + 1):
        sold = generated[y - 1 - lag] if y - 1 - lag >= 0 else 0.0
        price_inr = p.price_usd * (1 + p.price_growth) ** (y - 1) * p.fx_inr_per_usd
        revenue = sold * price_inr
        verification = p.verification_per_event if sold > 0 else 0.0
        registry = (p.registry_per_credit_usd * sold + (p.registry_fixed_usd if y == p.first_issuance_year else 0)) * p.fx_inr_per_usd
        costs = (p.upfront_per_ha * p.hectares if y == 1 else 0.0) + p.annual_per_ha * p.hectares \
            + (p.project_development + p.validation if y == 1 else 0.0) + verification + registry
        farmer_pay = revenue * p.farmer_share
        to_project = revenue - farmer_pay
        gap = costs - to_project                  # >0: CSR must fund; <0: surplus
        csr = max(gap, 0.0)
        surplus = max(-gap, 0.0)
        if breakeven_year is None and sold > 0 and to_project >= costs:
            breakeven_year = y
        cum_csr += csr
        rows.append({"year": y, "credits_generated_t": round(generated[y - 1], 1), "credits_sold_t": round(sold, 1),
                     "price_inr_per_t": round(price_inr), "credit_revenue_inr": round(revenue),
                     "farmer_payments_inr": round(farmer_pay), "project_costs_inr": round(costs),
                     "csr_needed_inr": round(csr), "surplus_to_plough_back_inr": round(surplus),
                     "cumulative_csr_inr": round(cum_csr)})
        for k, v in (("costs", costs), ("revenue", revenue), ("farmer_payments", farmer_pay), ("csr_needed", csr),
                     ("surplus", surplus), ("credits_sold", sold)):
            total[k] += v
    unsold_after_horizon = sum(generated[p.years - lag:]) if lag else 0.0
    gen_total = sum(generated)
    summary = {
        "csr_total_needed_inr": round(total["csr_needed"]),
        "csr_total_needed_cr": round(total["csr_needed"] / 1e7, 2),
        "csr_years_needed": sum(1 for r in rows if r["csr_needed_inr"] > 0),
        "self_sustaining_from_year": breakeven_year,
        "credits_generated_t": round(gen_total),
        "credits_sold_within_horizon_t": round(total["credits_sold"]),
        "credits_pending_after_horizon_t": round(unsold_after_horizon),
        "credits_per_ha_per_year_t": round(credits_per_ha(p, p.years), 3),
        "farmer_income_total_inr": round(total["farmer_payments"]),
        "farmer_income_per_farmer_per_year_inr": round(total["farmer_payments"] / p.farmers / p.years),
        "farmer_income_per_ha_per_year_inr": round(total["farmer_payments"] / p.hectares / p.years),
        "csr_cost_per_tco2e_inr": round(total["csr_needed"] / gen_total) if gen_total else None,
        "csr_per_farmer_inr": round(total["csr_needed"] / p.farmers),
        "surplus_to_plough_back_inr": round(total["surplus"]),
        "breakeven_price_usd": breakeven_price(p),
    }
    if p.csr_budget is not None:
        summary["csr_budget_inr"] = p.csr_budget
        summary["csr_budget_sufficient"] = p.csr_budget >= total["csr_needed"]
    return {"params": asdict(p), "summary": summary, "years": rows, "csr_rule": SOURCES["csr_surplus"]}


def breakeven_price(p: Params) -> float | None:
    """Carbon price (USD/t) at which the project needs no CSR money after year 1 set-up costs (bisection)."""
    def ongoing_gap(price: float) -> float:
        q = Params(**{**asdict(p), "price_usd": price, "csr_budget": None})
        lag = q.first_issuance_year - 1
        gen = [credits_per_ha(q, y) * q.hectares for y in range(1, q.years + 1)]
        y = q.years   # steady-state year
        sold = gen[y - 1 - lag]
        if sold <= 0:
            return float("inf")
        rev = sold * price * q.fx_inr_per_usd * (1 - q.farmer_share)
        cost = q.annual_per_ha * q.hectares + q.verification_per_event + q.registry_per_credit_usd * sold * q.fx_inr_per_usd
        return cost - rev
    lo, hi = 0.0, 1000.0
    if ongoing_gap(hi) > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if ongoing_gap(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


def scenarios(practice: str) -> dict:
    """Sensitivity to the cited price bands, and for AWD to credit yield (IPCC default vs RMI's 4-6 t/ha)."""
    prices = (("legacy low", 5), ("legacy high", 12), ("mid", 15), ("next-gen low", 20), ("next-gen high", 25))
    yields = [("IPCC default" if practice == "awd" else "ICAR-CRIDA rate", None)]
    if practice == "awd":
        yields += [("RMI low (4 t/ha)", 4.0), ("RMI high (6 t/ha)", 6.0)]
    out = []
    for ylabel, y in yields:
        for plabel, price in prices:
            s = run(Params(practice=practice, price_usd=price, credits_per_ha_override=y))["summary"]
            out.append({"credit_yield": ylabel, "price": f"{plabel} (${price})", "price_usd": price,
                        "credits_per_ha_per_year_t": s["credits_per_ha_per_year_t"],
                        "csr_total_needed_cr": s["csr_total_needed_cr"],
                        "self_sustaining_from_year": s["self_sustaining_from_year"],
                        "farmer_income_per_farmer_per_year_inr": s["farmer_income_per_farmer_per_year_inr"]})
    return {"practice": practice, "defaults": "2,000 ha, 1,500 farmers, 10 years, 60% farmer share",
            "breakeven_price_usd": run(Params(practice=practice))["summary"]["breakeven_price_usd"],
            "rows": out}
