# India CSR Spend Tracker API

Benchmark any Indian company's CSR spending against its peers. The API serves the Ministry of
Corporate Affairs' **National CSR Portal** data, FY2014-15 to FY2023-24 (55,800+ companies,
Rs 2.2 lakh crore, 6.3 lakh projects), broken down by development sector, sub-sector, state and
PSU status. It also includes a curated table of unspent CSR transfers and a livelihood & skilling
outcomes calculator built on a published impact assessment.

🚀 **Live API:** https://india-csr-spend-api.onrender.com · 📚 **Docs:** https://india-csr-spend-api.onrender.com/docs · 🧮 **Calculator:** https://india-csr-spend-api.onrender.com/calculator

🧪 15 tests · ✅ totals reconcile to MCA's figures to the paisa

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /overview` | National CSR spend by year, companies reporting, PSU share, growth |
| `GET /sectors?fy=&level=&psu=` | Spend and share by development sector or sub-sector |
| `GET /states?fy=&sector=` | Spend by state, with rupees per resident (Census 2011) |
| `GET /top?fy=&sector=&state=&psu=` | Largest spenders for any slice |
| `GET /companies/search?q=` | Find a company's exact registered name |
| `GET /companies/{name}?fy=` | A company's CSR trend, sector mix, sub-sectors and states |
| `GET /benchmark?company=&fy=&peers=` | Company vs peer group (top 100, all, PSU, non-PSU or a named list): sector over/under-weights, rank, peer median, concentration |
| `GET /unspent` | Unspent CSR moved to Unspent CSR Accounts under Section 135(6), per company, with sources |
| `GET /livelihood/case` | SDI Bhubaneswar (IndianOil-led CSR): placement, cost per placement, income change, payback, partner-level results |
| `POST /livelihood/evaluate` | Enter any skilling programme's numbers, get the same KPIs side by side with the SDI case |
| `GET /cofunding/defaults` | Assumptions for a farmer carbon project (rice water-saving or agroforestry), each with its source or marked as an assumption |
| `POST /cofunding/model` | Year-by-year CSR need, credit revenue, farmer income and break-even price for any project you describe |
| `GET /cofunding/scenarios` | Sensitivity to carbon price and, for rice, to credit yield |
| `GET /calculator` | The same model as an interactive page |

## What the data shows (FY2023-24 unless stated)

1. **CSR spending is growing about 15% a year.** It rose from Rs 10,066 crore in FY2014-15 to Rs 34,909 crore in
   FY2023-24 (14.8% a year), reported by 26,982 companies. PSUs account for 14% of it.
2. **Education and health take almost three-quarters.** Education, differently abled & livelihood gets 47% and
   health, hunger, water & sanitation 26%. Environment gets 10%. Within those, vocational skills is 4.0% and
   livelihood enhancement 6.8%.
3. **The money concentrates where companies sit, not where need is.** Maharashtra receives Rs 540 per resident and
   Delhi Rs 1,162, against Rs 77 in Uttar Pradesh. Five states take 55% of the spend that can be placed on a map.
   Another 23% is reported only as "PAN India" or not located at all.
4. **The top 20 spenders account for 24% of all CSR, and the top 5 for 11%.** HDFC Bank (Rs 922 cr), Reliance (Rs 899 cr),
   TCS (Rs 813 cr), ONGC (Rs 612 cr) and Tata Steel (Rs 573 cr) lead.
5. **Benchmarking example:** Tata Steel spends 99% of its located CSR in Odisha and Jharkhand, where it operates.
   It is 5.5 points overweight on education and livelihood and 6 points underweight on environment compared
   with the other top-100 spenders.
6. **Unspent money can be most of the obligation.** In the curated sample, GNFC moved 77% of its FY2025-26
   obligation to an Unspent CSR Account and Bharat Electronics 70% (Rs 75 cr), both for multi-year projects.

## Livelihood & skilling module

Built on IndianOil's published impact assessment of the **Skill Development Institute, Bhubaneswar** (FY2022-23):

| KPI | Value |
|---|---|
| Placement rate: of trainees seeking jobs / of all trained | 94% / 85% |
| Alumni in salaried work (survey, n = 200) | 70% |
| Cost per trainee / per placement | Rs 1.49 lakh / Rs 1.75 lakh |
| CSR grant per placement | Rs 58,343 |
| Monthly income, before → after | Rs 7,000 → Rs 22,000 (+214%) |
| Months of extra earnings to recover cost per placement | about 12 |

**The definition matters:** the same programme can be reported as 94%, 85% or 70% "placed". The API shows all three
and lets you run any programme through the same calculation (`POST /livelihood/evaluate`).

## CSR + carbon co-funding model

**The question:** how much CSR money does a farmer carbon project need, and for how long, before carbon
credits can carry it? It covers two practices: alternate wetting and drying (AWD) in irrigated rice, which cuts
methane, and agroforestry, which removes CO2.

**Sources:**
- AWD: IPCC 2019 defaults via the Gold Standard rice methodology (India baseline 0.85 kg CH4/ha/day,
  AWD scaling factor 0.55, GWP 28, 15% uncertainty).
- Agroforestry: ICAR-CRIDA's Verra VM0047 project in Chitradurga (1,373 tCO2e/yr from 15,600 trees;
  Rs 200 planting and Rs 50 management per tree).
- Prices: legacy rice credits $5-12/t, next-generation $20-25/t (Quantum Commodity Intelligence).
- Fees: Verra registry fees.
- Everything unsourced (verification costs, issuance lag, farmer share, adoption) is a labelled default you can change.

**CSR rule built in:** surplus from CSR activities cannot become company profit (CSR Rule 7(2), MCA FAQ 55), so
credit revenue goes to farmers (60% by default) and the project's own costs. Anything left over is reported as
surplus to plough back.

**What it shows (2,000 ha, 1,500 farmers, 10 years):**

| | Rice water-saving (AWD) | Agroforestry |
|---|---|---|
| Net credits per ha per year | 0.8 t (IPCC defaults) | 6.0 t |
| CSR needed over 10 years at $15/t | Rs 2.27 cr | Rs 11.21 cr |
| Carbon price at which credits cover running costs | about $45/t | about $26/t |
| Farmer income from credits, per farmer per year | Rs 761 | Rs 5,056 |

- **At IPCC default factors, rice water-saving does not pay for itself at any price seen so far.** CSR is a
  long-term co-funder, not a bridge.
- **With measured baselines the picture flips.** At RMI's 4-6 credits per hectare from newer methodologies,
  the same project needs CSR only for year-1 set-up (Rs 73 lakh) and is self-sustaining from year 2 at $12/t or more.
- **Agroforestry can graduate off CSR** if it sells at next-generation prices above about $26/t.

## Data and method

- **Source:** MCA National CSR Portal, project-level disclosures (e-form AOC-4 / CSR-2), portal export of
  4 July 2026, archived in [2509Vaid/CSR-Analysis-CJSJ](https://github.com/2509Vaid/CSR-Analysis-CJSJ). The portal's own
  reports sit behind a CAPTCHA, so this archived export is used and included unchanged in `data/raw/`.
- **Check:** FY2019-20 to FY2023-24 totals equal the Rs 1,44,159.05 crore MCA gave the Rajya Sabha
  ([PIB, 10 Feb 2026](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2226018&reg=3&lang=2)); a test enforces this.
- **Cleaning** (`scripts/prepare_data.py`): trims whitespace, merges names and labels that differ only in case
  (77,928 raw names become 55,831 companies), shortens sector labels, and keeps zero and negative records as reported.
- **Per-resident spend** uses Census 2011 population.
- **Unspent CSR:** MCA publishes no bulk company-wise unspent data. The 8 rows are company annual-report disclosures
  collected via India CSR, each with its link. Check against the annual report before citing.

## Limitations

- **No district data.** The portal export used here stops at state level.
- **Latest year is FY2023-24.** Companies file a year or more after year-end, so FY2024-25 is incomplete on the portal.
- Company names are as filed. Group companies are not consolidated, so use `/companies/search` to find subsidiaries.
- The unspent table is a sample, not a census.

## Run

```bash
pip install -r requirements.txt
python scripts/prepare_data.py       # only if you change the raw file
uvicorn api.main:app --reload        # http://127.0.0.1:8000/docs
pytest -q
```

Deploy: `render.yaml` (Render free tier) or `Dockerfile`.

---
*Mayank Majoka, October 2026. Data © Ministry of Corporate Affairs, Government of India.*
