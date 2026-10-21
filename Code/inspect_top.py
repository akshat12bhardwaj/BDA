import pandas as pd
import os

# Dataset location relative to the code folder
DATA_FOLDER = "../Dataset/India Commodity Wise Mandi Dataset"

crops = ["Tomato", "Onion", "Potato"]

for crop in crops:

    file_path = os.path.join(DATA_FOLDER, f"{crop}.csv")

    print("\n" + "=" * 70)
    print(f" {crop.upper()}")
    print("=" * 70)

    if not os.path.exists(file_path):
        print(f"❌ File not found:")
        print(file_path)
        continue

    # Read dataset
    df = pd.read_csv(file_path)

    print(f"\n✓ File found")
    print(f"Records: {len(df):,}")

    # ------------------------------------------------
    # Columns
    # ------------------------------------------------

    print("\nColumns:")
    for i, col in enumerate(df.columns, 1):
        print(f"{i}. {col}")

    # ------------------------------------------------
    # Date
    # ------------------------------------------------

    df["Reported Date"] = pd.to_datetime(
        df["Reported Date"],
        errors="coerce"
    )

    print("\nDate range:")
    print("Start:", df["Reported Date"].min())
    print("End  :", df["Reported Date"].max())

    # ------------------------------------------------
    # Unique locations
    # ------------------------------------------------

    print("\nUnique locations:")
    print("States   :", df["State Name"].nunique())
    print("Districts:", df["District Name"].nunique())
    print("Markets  :", df["Market Name"].nunique())

    # ------------------------------------------------
    # Varieties
    # ------------------------------------------------

    print("\nNumber of varieties:", df["Variety"].nunique())

    print("\nTop 20 varieties:")
    print(df["Variety"].value_counts().head(20).to_string())

    # ------------------------------------------------
    # Markets
    # ------------------------------------------------

    print("\nTop 20 markets:")
    print(df["Market Name"].value_counts().head(20).to_string())

    # ------------------------------------------------
    # States
    # ------------------------------------------------

    print("\nStates:")
    print(df["State Name"].value_counts().to_string())

    # ------------------------------------------------
    # Missing values
    # ------------------------------------------------

    print("\nMissing values:")
    print(df.isnull().sum().to_string())

    # ------------------------------------------------
    # Duplicate rows
    # ------------------------------------------------

    print("\nDuplicate rows:", df.duplicated().sum())

    # ------------------------------------------------
    # Basic statistics
    # ------------------------------------------------

    print("\nPrice statistics:")
    print(
        df[
            [
                "Arrivals (Tonnes)",
                "Min Price (Rs./Quintal)",
                "Max Price (Rs./Quintal)",
                "Modal Price (Rs./Quintal)"
            ]
        ].describe().round(2)
    )

print("\n" + "=" * 70)
print("INSPECTION COMPLETE")
print("=" * 70)