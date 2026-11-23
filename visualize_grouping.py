import argparse
import glob
import os
import re
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import MaxNLocator

# Mute pandas datetime format warnings for cleaner terminal output
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

# Set visual style and define 508-compliant Okabe-Ito colors for each direction
sns.set_theme(style="whitegrid")
dir_palette = {
    "NB": "#0072B2",  # Colorblind-safe Deep Blue
    "SB": "#009E73",  # Colorblind-safe Bluish Green
    "EB": "#D55E00",  # Colorblind-safe Vermillion
    "WB": "#E69F00",  # Colorblind-safe Warm Amber
}
dir_order = ["NB", "SB", "EB", "WB"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# -------------------------------------------------------------------------
# 1. PATHS & FOLDER SETUP
# -------------------------------------------------------------------------
DEFAULT_INPUT_DIR = os.path.join(SCRIPT_DIR, "data", "grouping")
DEFAULT_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "grouping visuals")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate network-wide bicycle grouping profile chart.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_GROUPING_INPUT_DIR", DEFAULT_INPUT_DIR),
        help="Directory containing source grouping .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_GROUPING_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
        help="Directory where chart images will be written.",
    )
    return parser.parse_args()


def in_observation_window(pt):
    """Restrict records to the active NDS data collection blocks (7-9 AM, 11 AM-1 PM, 4-6 PM)."""
    if pd.isna(pt):
        return False
    h, m = pt.hour, pt.minute
    return (
        (h == 7) or (h == 8 and m <= 45)
        or (h == 11) or (h == 12 and m <= 45)
        or (h == 16) or (h == 17 and m <= 45)
    )


args = parse_args()
target_folder = args.input_dir
output_folder = args.output_dir

os.makedirs(output_folder, exist_ok=True)
file_paths = sorted(glob.glob(os.path.join(target_folder, "*.xlsx")))

print(f"Found {len(file_paths)} Excel files. Generating Bicycle Grouping Profile...")

df_list = []
ordered_locations = []

for path in file_paths:
    raw_name = (
        os.path.basename(path)
        .replace(".xlsx", "")
        .replace(" ALL_BicycleGrouping", "")
        .replace(" ALL_BikeGrp", "")
        .replace(" ALL_Grp", "")
        .strip()
    )
    # Remove leading letter numbering (e.g., "B. Triangle East" -> "Triangle East")
    location_name = re.sub(r"^[A-Z]\.\s*", "", raw_name).strip()

    try:
        xls = pd.ExcelFile(path)
        temp_df = pd.read_excel(xls, sheet_name=0)
        temp_df["Location"] = location_name
        df_list.append(temp_df)
        if location_name not in ordered_locations:
            ordered_locations.append(location_name)
    except Exception as e:
        print(f"Could not read {path}: {e}")

if df_list:
    full_df = pd.concat(df_list, ignore_index=True)

    # -------------------------------------------------------------------------
    # 2. DATE & TIME PARSING
    # -------------------------------------------------------------------------
    date_col = [c for c in full_df.columns if "date" in str(c).lower() and "time" not in str(c).lower()][0]
    time_col = [c for c in full_df.columns if "time" in str(c).lower()][0]

    full_df["Date"] = pd.to_datetime(full_df[date_col], errors="coerce").dt.date
    full_df = full_df.dropna(subset=["Date"])

    parsed_time = pd.to_datetime(full_df[time_col].astype(str), format="mixed", errors="coerce").dt.time
    full_df["PlotTime"] = pd.to_datetime("2000-01-01 " + parsed_time.astype(str), errors="coerce")

    # Keep only active observation intervals across all days (Weekday and Weekend combined)
    full_df = full_df[full_df["PlotTime"].apply(in_observation_window)].copy()

    # -------------------------------------------------------------------------
    # 3. FILTERING, MELTING & AGGREGATION BY LOCATION AND DIRECTION
    # -------------------------------------------------------------------------
    grp_pattern = re.compile(r"^BikeGrp_(NB|SB|EB|WB)$", flags=re.IGNORECASE)
    grp_cols = [c for c in full_df.columns if grp_pattern.match(str(c).strip())]

    if not grp_cols:
        print("Error: Could not find matching BikeGrp columns (e.g., BikeGrp_NB). Please verify column names.")
    else:
        keep_cols = ["Date", "Location"] + grp_cols
        filtered_df = full_df[keep_cols].copy()

        df_long = pd.melt(
            filtered_df,
            id_vars=["Date", "Location"],
            value_vars=grp_cols,
            var_name="Category",
            value_name="Count",
        )

        df_long["Count"] = pd.to_numeric(df_long["Count"], errors="coerce").fillna(0)
        df_long["Direction"] = df_long["Category"].apply(lambda x: str(x).split("_")[-1].upper())

        # Normalize total counts by the exact number of unique observation days per location
        unique_days = filtered_df.groupby("Location")["Date"].nunique().to_dict()

        loc_dir_summary = df_long.groupby(["Location", "Direction"], observed=False)["Count"].sum().reset_index()
        loc_dir_summary["Avg_Daily_Count"] = loc_dir_summary.apply(
            lambda row: row["Count"] / unique_days.get(row["Location"], 1), axis=1
        )

        # Only include directions that appear in the dataset
        active_dirs = [
            d for d in dir_order
            if loc_dir_summary.loc[loc_dir_summary["Direction"] == d, "Avg_Daily_Count"].sum() > 0
        ]

        # -------------------------------------------------------------------------
        # 4. CHART GENERATION
        # -------------------------------------------------------------------------
        pivot_df = (
            loc_dir_summary.pivot(index="Location", columns="Direction", values="Avg_Daily_Count")
            .reindex(index=ordered_locations, columns=active_dirs, fill_value=0)
        )

        fig, ax = plt.subplots(figsize=(12, 6.5))
        fig.suptitle(
            "Average Daily Bicycle Grouping Incidents by Location",
            fontsize=20,
            fontweight="bold",
            y=0.98,
        )

        x = np.arange(len(ordered_locations))
        bar_width = 0.55
        bottom = np.zeros(len(pivot_df))

        for direction in active_dirs:
            vals = pivot_df[direction].values
            ax.bar(
                x,
                vals,
                width=bar_width,
                bottom=bottom,
                color=dir_palette[direction],
                label=direction,
                align="center",
            )
            bottom += vals

        max_stack = bottom.max()
        ax.set_ylim(0, max_stack * 1.12 if max_stack > 0 else 1)
        ax.set_ylabel("Average Daily Incidents", fontsize=13)
        ax.set_xticks(x)
        ax.set_xticklabels(ordered_locations, rotation=30, ha="right", rotation_mode="anchor", fontsize=11)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        # Unified top-center horizontal legend below the main title
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            fig.legend(
                handles,
                labels,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.91),
                ncol=len(handles),
                fontsize=11,
                title="Direction",
                title_fontsize=11,
                framealpha=0.9,
            )

        plt.tight_layout(rect=[0, 0, 1, 0.84])

        output_path = os.path.join(output_folder, "All_Locations_BikeGrouping_Profile.png")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Saved: {output_path}")
        print("\nSuccessfully generated the Bicycle Grouping profile.")
else:
    print("No relevant data available to process.")
