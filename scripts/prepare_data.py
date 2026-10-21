"""
Clean the MCA National CSR Portal project-level file and write the compact dataset the API serves.

Input : data/raw/CSR_Report_2026-07-04.csv.gz  (628,701 project rows, FY2014-15 to FY2023-24)
Output: data/processed/csr.parquet             (company x year x state x sector x sub-sector, summed)

Cleaning
- Trims whitespace and unifies labels that differ only in case ("PAN INDIA" / "PAN India").
- PSU flag: "NON-PSU" -> "Non-PSU".
- Sector names shortened to readable labels (the official Schedule VII grouping is kept in `sector_official`).
- Amounts stay in INR crore as reported; zero and the 18 negative records are kept, as reported.

Run: python scripts/prepare_data.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "CSR_Report_2026-07-04.csv.gz"
OUT = ROOT / "data" / "processed" / "csr.parquet"

SECTOR_LABELS = {
    "education, differently abled, livelihood": "Education, Differently Abled & Livelihood",
    "health, eradicating hunger, poverty and malnutrition, safe drinking water , sanitation":
        "Health, Hunger, Poverty, Water & Sanitation",
    "nec/not mentioned": "Not Mentioned",
    "environment, animal welfare, conservation of resources": "Environment & Animal Welfare",
    "rural development": "Rural Development",
    "gender equality , women empowerment , old age homes , reducing inequalities":
        "Gender Equality & Reducing Inequalities",
    "prime minister's national relief fund": "PM National Relief Fund",
    "encouraging sports": "Sports",
    "heritage art and culture": "Heritage, Art & Culture",
    "any other fund": "Other Central Funds",
    "other sectors ( technology incubator and benefits to armed forces and admin overheads )":
        "Other (Tech Incubators, Armed Forces, Admin)",
    "swachh bharat kosh": "Swachh Bharat Kosh",
    "slum area development": "Slum Area Development",
    "clean ganga fund": "Clean Ganga Fund",
}

STATE_FIX = {
    "pan india": "PAN India", "nec/not mentioned": "Not Mentioned",
    "pan india (other centralized funds)": "PAN India (Central Funds)",
    "dadra and nagar haveli": "Dadra And Nagar Haveli", "daman and diu": "Daman And Diu",
    "jammu and kashmir": "Jammu And Kashmir", "jharkhand": "Jharkhand", "manipur": "Manipur",
}


def main() -> None:
    df = pd.read_csv(RAW)
    df.columns = ["company", "fy", "psu", "state", "sector_official", "sub_sector", "amount_cr"]
    for c in ["company", "fy", "psu", "state", "sector_official", "sub_sector"]:
        df[c] = df[c].astype(str).str.strip()
    df["company"] = df.company.str.upper().str.replace(r"\s+", " ", regex=True)
    df["psu"] = df.psu.str.upper().map({"PSU": "PSU", "NON-PSU": "Non-PSU"})
    key = df.sector_official.str.lower()
    unknown = sorted(set(key) - set(SECTOR_LABELS))
    assert not unknown, f"Unmapped sectors: {unknown}"
    df["sector"] = key.map(SECTOR_LABELS)
    df["sector_official"] = df.sector_official.str.title()
    df["sub_sector"] = df.sub_sector.str.lower().str.capitalize()
    df["state"] = df.state.map(lambda s: STATE_FIX.get(s.lower(), s))
    df["fy"] = df.fy.str.replace("FY ", "", regex=False)          # "2023-24"

    raw_total = df.amount_cr.sum()
    out = (df.groupby(["company", "fy", "psu", "state", "sector", "sector_official", "sub_sector"],
                      observed=True, dropna=False)
             .agg(amount_cr=("amount_cr", "sum"), projects=("amount_cr", "size"))
             .reset_index())
    assert abs(out.amount_cr.sum() - raw_total) < 1e-6
    for c in ["company", "fy", "psu", "state", "sector", "sector_official", "sub_sector"]:
        out[c] = out[c].astype("category")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{len(df):,} project rows -> {len(out):,} rows; total Rs {raw_total:,.2f} cr; "
          f"{df.company.nunique():,} companies; saved {OUT.name} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
