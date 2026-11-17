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

# Mute pandas datetime format warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define a 508-compliant primary color
sns.set_theme(style="whitegrid")
primary_color = "#0072B2"  # Colorblind-safe Deep Blue

segment_order = ["Morning\n(7:00-9:00 AM)", "Mid-day\n(11:00 AM-1:00 PM)", "Late Afternoon\n(4:00-6:00 PM)"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(description="Generate bicycle grouping profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_GROUPING_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "grouping")),
        help="Directory containing source grouping .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_GROUPING_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "grouping visuals")),
        help="Directory where chart images will be written.",
    )
    return parser.parse_args()

# -------------------------------------------------------------------------
# 1. PATHS & FOLDER SETUP
# -------------------------------------------------------------------------
args = parse_args()
target_folder = args.input_dir
output_folder = args.output_dir

os.makedirs(output_folder, exist_ok=True)
file_paths = glob.glob(os.path.join(target_folder, "*.xlsx"))

print(f"Found {len(file_paths)} Excel files. Generating Bicycle Grouping Profiles...")

df_list = []
for path in file_paths:
    # Safely strip out all possible grouping variations from the file name
    location_name = os.path.basename(path).replace(".xlsx", "").replace(" ALL_BicycleGrouping", "").replace(" ALL_BikeGrp", "").replace(" ALL_Grp", "").strip()
    try:
        xls = pd.ExcelFile(path)
        temp_df = pd.read_excel(xls, sheet_name=0)
        temp_df["Location"] = location_name
        df_list.append(temp_df)
    except Exception as e:
        print(f"Could not read {path}: {e}")

if df_list:
    full_df = pd.concat(df_list, ignore_index=True)

    # -------------------------------------------------------------------------
    # 2. DATE & TIME SEGMENT PARSING
    # -------------------------------------------------------------------------
    date_col = [c for c in full_df.columns if "date" in str(c).lower() and "time" not in str(c).lower()][0]
    time_col = [c for c in full_df.columns if "time" in str(c).lower()][0]

    full_df["Date"] = pd.to_datetime(full_df[date_col]).dt.date
    full_df["Day_Type"] = pd.to_datetime(full_df[date_col]).dt.dayofweek.apply(
        lambda x: "Weekend" if x >= 5 else "Weekday"
    )

    parsed_time = pd.to_datetime(full_df[time_col].astype(str), format='mixed', errors="coerce").dt.time
    full_df["PlotTime"] = pd.to_datetime("2000-01-01 " + parsed_time.astype(str))

    def get_segment(pt):
        """Map actual data times (up to :45) into the requested rounded hour blocks."""
        if pd.isna(pt): return None
        h, m = pt.hour, pt.minute
        if (h == 7) or (h == 8 and m <= 45): return "Morning\n(7:00-9:00 AM)"
        elif (h == 11) or (h == 12 and m <= 45): return "Mid-day\n(11:00 AM-1:00 PM)"
        elif (h == 16) or (h == 17 and m <= 45): return "Late Afternoon\n(4:00-6:00 PM)"
        return None
        
    full_df["Time_Segment"] = full_df["PlotTime"].apply(get_segment)

    # -------------------------------------------------------------------------
    # 3. FILTERING & MELTING 
    # -------------------------------------------------------------------------
    grp_pattern = re.compile(r"^BikeGrp_(NB|SB|EB|WB)$", flags=re.IGNORECASE)
    grp_cols = [c for c in full_df.columns if grp_pattern.match(str(c).strip())]

    if not grp_cols:
        print("Error: Could not find matching BikeGrp columns (e.g., BikeGrp_NB). Please verify column names.")
    else:
        keep_cols = ["Date", "Time_Segment", "Day_Type", "Location"] + grp_cols
        filtered_df = full_df[keep_cols].copy()
        
        filtered_df = filtered_df.dropna(subset=["Time_Segment"])

        df_long = pd.melt(
            filtered_df, id_vars=["Date", "Time_Segment", "Day_Type", "Location"],
            value_vars=grp_cols, var_name="Category", value_name="Count"
        )

        df_long["Count"] = pd.to_numeric(df_long["Count"], errors="coerce").fillna(0)
        df_long["Direction"] = df_long["Category"].apply(lambda x: str(x).split("_")[-1].upper())

        # -------------------------------------------------------------------------
        # 4. DASHBOARD GENERATION
        # -------------------------------------------------------------------------
        for loc in df_long["Location"].unique():
            loc_data = df_long[df_long["Location"] == loc].copy()
            
            dir_sums = loc_data.groupby("Direction")["Count"].sum()
            active_dirs = dir_sums[dir_sums > 0].index.tolist()
            loc_data = loc_data[loc_data["Direction"].isin(active_dirs)]
            
            daily_sums = loc_data.groupby(["Date", "Day_Type", "Time_Segment", "Direction"], observed=False)["Count"].sum().reset_index()
            segment_avg = daily_sums.groupby(["Day_Type", "Time_Segment", "Direction"], observed=False)["Count"].mean().reset_index()

            if segment_avg.empty:
                continue

            num_rows = len(active_dirs)

            # sharey=True synchronizes the y-axis limit across the entire figure
            fig, axes = plt.subplots(num_rows, 2, figsize=(16, 6 * num_rows), sharey=True)
            fig.suptitle(f"Average Bicycle Grouping Incidents: {loc}", fontsize=24, fontweight="bold", y=0.98 if num_rows > 1 else 1.05)

            if num_rows == 1:
                axes = np.array([axes])

            for d_idx, direction in enumerate(active_dirs):
                for i, day_type in enumerate(["Weekday", "Weekend"]):
                    ax = axes[d_idx, i]
                    data = segment_avg[(segment_avg["Day_Type"] == day_type) & (segment_avg["Direction"] == direction)]
                    
                    if not data.empty:
                        sns.barplot(
                            data=data, x="Time_Segment", y="Count", 
                            order=segment_order, color=primary_color, ax=ax
                        )
                    
                    ax.set_title(f"{day_type} ({direction})", fontsize=16)
                    ax.set_ylabel("Average Daily Grouping Incidents" if i == 0 else "", fontsize=13)
                    ax.set_xlabel("")
                    ax.tick_params(axis='x', labelsize=12)
                    
                    # Force y-axis to only show integer increments
                    ax.yaxis.set_major_locator(MaxNLocator(integer=True))

            plt.tight_layout(rect=[0, 0, 1, 0.95] if num_rows > 1 else [0, 0, 1, 1])
            
            safe_loc_name = loc.replace(".", "").replace(" ", "_").strip("_")
            output_path = os.path.join(output_folder, f"{safe_loc_name}_BikeGrouping_Profile.png")
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            plt.close() 
            
            print(f"Saved: {output_path}")

        print("\nSuccessfully generated all Bicycle Grouping profiles.")
else:
    print("No relevant data available to process.")
