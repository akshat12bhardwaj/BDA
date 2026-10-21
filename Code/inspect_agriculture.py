import pandas as pd
from pathlib import Path

# ============================================================
# DATASET 3 - AGRICULTURE DATASET AUDIT
# ============================================================

CSV_PATH = Path(
    r"C:\Users\aksha_q43exq6\OneDrive\Documents\BDA\Dataset\crop-wise-area-production-yield.csv"
)

print("\nFound dataset at:")
print(CSV_PATH)

# ============================================================
# LOAD DATASET
# ============================================================

print("\nLoading dataset...")

df = pd.read_csv(CSV_PATH)

print("Dataset loaded successfully!")

# ============================================================
# 1. BASIC INFORMATION
# ============================================================

print("\n" + "=" * 70)
print("1. BASIC INFORMATION")
print("=" * 70)

print("Rows:", f"{len(df):,}")
print("Columns:", len(df.columns))

# ============================================================
# 2. COLUMN NAMES
# ============================================================

print("\n" + "=" * 70)
print("2. COLUMN NAMES")
print("=" * 70)

for i, col in enumerate(df.columns, 1):
    print(f"{i:2}. {col}")

# ============================================================
# 3. DATA TYPES
# ============================================================

print("\n" + "=" * 70)
print("3. DATA TYPES")
print("=" * 70)

print(df.dtypes.to_string())

# ============================================================
# 4. SAMPLE RECORDS
# ============================================================

print("\n" + "=" * 70)
print("4. SAMPLE RECORDS")
print("=" * 70)

print(df.head(10).to_string(index=False))

# ============================================================
# 5. MISSING VALUES
# ============================================================

print("\n" + "=" * 70)
print("5. MISSING VALUES")
print("=" * 70)

missing = df.isnull().sum()

missing_table = pd.DataFrame({
    "Missing": missing,
    "Missing %": (missing / len(df) * 100).round(2)
})

print(missing_table.to_string())

# ============================================================
# 6. DUPLICATE ROWS
# ============================================================

print("\n" + "=" * 70)
print("6. DUPLICATE ROWS")
print("=" * 70)

print("Duplicate rows:", f"{df.duplicated().sum():,}")

# ============================================================
# 7. UNIQUE VALUES
# ============================================================

print("\n" + "=" * 70)
print("7. UNIQUE VALUES")
print("=" * 70)

for col in [
    "year",
    "state_name",
    "state_code",
    "district_name",
    "district_code",
    "crop_name",
    "crop_code",
    "crop_type",
    "season"
]:
    if col in df.columns:
        print(f"{col}: {df[col].nunique():,}")

# ============================================================
# 8. YEAR COVERAGE
# ============================================================

print("\n" + "=" * 70)
print("8. YEAR COVERAGE")
print("=" * 70)

if "year" in df.columns:
    years = sorted(df["year"].dropna().unique())

    print("Number of years:", len(years))
    print("Years:")
    print(years)

# ============================================================
# 9. SEASONS
# ============================================================

print("\n" + "=" * 70)
print("9. SEASONS")
print("=" * 70)

if "season" in df.columns:
    print(df["season"].value_counts(dropna=False).to_string())

# ============================================================
# 10. CROP TYPES
# ============================================================

print("\n" + "=" * 70)
print("10. CROP TYPES")
print("=" * 70)

if "crop_type" in df.columns:
    print(df["crop_type"].value_counts(dropna=False).to_string())

# ============================================================
# 11. ALL CROP NAMES
# ============================================================

print("\n" + "=" * 70)
print("11. ALL CROP NAMES")
print("=" * 70)

if "crop_name" in df.columns:
    print(
        df["crop_name"]
        .value_counts()
        .to_string()
    )

# ============================================================
# 12. TOP CROP AUDIT
# ============================================================

print("\n" + "=" * 70)
print("12. TOP CROP AUDIT")
print("=" * 70)

crop_clean = (
    df["crop_name"]
    .astype(str)
    .str.strip()
    .str.lower()
)

TOP_CROPS = {
    "Tomato": ["tomato", "tomatoes"],
    "Onion": ["onion", "onions"],
    "Potato": ["potato", "potatoes"]
}

for target, names in TOP_CROPS.items():

    crop_df = df[crop_clean.isin(names)]

    print("\n" + "-" * 70)
    print(target.upper())
    print("-" * 70)

    print("Records:", f"{len(crop_df):,}")

    if len(crop_df) == 0:
        print("✗ NOT FOUND")
        continue

    print("✓ FOUND")

    # Coverage
    for col in [
        "year",
        "state_name",
        "district_name",
        "season"
    ]:
        if col in crop_df.columns:
            print(
                f"{col} unique:",
                crop_df[col].nunique()
            )

    # Missing
    print("\nMissing values:")
    print(crop_df.isnull().sum().to_string())

    # Duplicates
    print(
        "\nDuplicate rows:",
        f"{crop_df.duplicated().sum():,}"
    )

    # Statistics
    numeric_cols = [
        "area",
        "production",
        "yield"
    ]

    available = [
        col for col in numeric_cols
        if col in crop_df.columns
    ]

    if available:
        print("\nNumeric statistics:")
        print(
            crop_df[available]
            .describe()
            .round(2)
            .to_string()
        )

    # Years
    print("\nRecords by year:")

    print(
        crop_df["year"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    # States
    print("\nTop 15 states:")

    print(
        crop_df["state_name"]
        .value_counts()
        .head(15)
        .to_string()
    )

    # Districts
    print(
        "\nNumber of districts:",
        crop_df["district_name"].nunique()
    )

# ============================================================
# 13. SANITY CHECKS
# ============================================================

print("\n" + "=" * 70)
print("13. SANITY CHECKS")
print("=" * 70)

for col in [
    "area",
    "production",
    "yield"
]:

    if col not in df.columns:
        continue

    values = pd.to_numeric(
        df[col],
        errors="coerce"
    )

    print("\n" + col)

    print("Negative:", int((values < 0).sum()))
    print("Zero:", int((values == 0).sum()))
    print("Missing:", int(values.isna().sum()))
    print("Minimum:", values.min())
    print("Maximum:", values.max())

# ============================================================
# 14. UNIT CHECK
# ============================================================

print("\n" + "=" * 70)
print("14. UNIT CHECK")
print("=" * 70)

for col in [
    "area_unit",
    "production_unit",
    "yield_unit"
]:

    if col in df.columns:

        print("\n" + col)

        print(
            df[col]
            .value_counts(dropna=False)
            .to_string()
        )

# ============================================================
# 15. PROJECT COMPATIBILITY
# ============================================================

print("\n" + "=" * 70)
print("15. PROJECT COMPATIBILITY")
print("=" * 70)

required = [
    "year",
    "state_name",
    "district_name",
    "crop_name",
    "season",
    "area",
    "production",
    "yield"
]

for col in required:

    if col in df.columns:
        print(f"✓ {col}")
    else:
        print(f"✗ {col}")

print("\nPotential integration key:")
print("State + District + Year + Crop")

print("\nAgricultural features:")
print("Area + Production + Yield + Season")

# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)