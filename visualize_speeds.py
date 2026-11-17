import argparse
import glob
import os
import re
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Mute pandas datetime format warnings for cleaner terminal output
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define 508-compliant "traffic light" colors (Okabe-Ito palette)
sns.set_theme(style="whitegrid")
speed_palette = {
    "0-10 mph": "#009E73",   # Colorblind-safe Bluish Green
    "10-15 mph": "#E69F00",  # Colorblind-safe Orange
    "15+ mph": "#D55E00"     # Colorblind-safe Vermillion (Red)
}
speed_order = ["0-10 mph", "10-15 mph", "15+ mph"]

# Labels for the rounded x-axis hour segments
segment_order = ["Morning\n(7:00-9:00 AM)", "Mid-day\n(11:00 AM-1:00 PM)", "Late Afternoon\n(4:00-6:00 PM)"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(description="Generate bike speed profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_SPEEDS_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "speeds")),
        help="Directory containing source speed .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_SPEEDS_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "speed visuals")),
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

print(f"Found {len(file_paths)} Excel files. Generating Bike Speed Profiles...")

df_list = []
for path in file_paths:
    location_name = os.path.basename(path).replace(".xlsx", "").replace(" ALL_BikeSpeed", "")
    xls = pd.ExcelFile(path)
    temp_df = pd.read_excel(xls, sheet_name=0)
    temp_df["Location"] = location_name
    df_list.append(temp_df)

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
    # Strictly find the target speed bin columns
    speed_pattern = re.compile(r"^(NB|SB|EB|WB)_Speed_(0_10|10_15|15_Plus)$", flags=re.IGNORECASE)
    speed_cols = [c for c in full_df.columns if speed_pattern.match(str(c).strip())]

    keep_cols = ["Date", "Time_Segment", "Day_Type", "Location"] + speed_cols
    filtered_df = full_df[keep_cols].copy()
    
    # Drop rows that fall outside the 3 defined time blocks (the data collection gaps)
    filtered_df = filtered_df.dropna(subset=["Time_Segment"])

    df_long = pd.melt(
        filtered_df, id_vars=["Date", "Time_Segment", "Day_Type", "Location"],
        value_vars=speed_cols, var_name="Category", value_name="Count"
    )

    df_long["Count"] = pd.to_numeric(df_long["Count"], errors="coerce").fillna(0)
    df_long["Direction"] = df_long["Category"].apply(lambda x: str(x).split("_")[0].upper())
    
    # Standardize speed labels for charts
    speed_map = {"0_10": "0-10 mph", "10_15": "10-15 mph", "15_plus": "15+ mph"}
    df_long["Speed_Bin"] = df_long["Category"].apply(lambda x: "_".join(str(x).split("_")[2:]).lower())
    df_long["Speed_Label"] = df_long["Speed_Bin"].map(speed_map)
    df_long["Speed_Label"] = pd.Categorical(df_long["Speed_Label"], categories=speed_order, ordered=True)

    # -------------------------------------------------------------------------
    # 4. DASHBOARD GENERATION
    # -------------------------------------------------------------------------
    for loc in df_long["Location"].unique():
        loc_data = df_long[df_long["Location"] == loc].copy()
        
        # Determine valid active directions to plot
        dir_sums = loc_data.groupby("Direction")["Count"].sum()
        active_dirs = dir_sums[dir_sums > 0].index.tolist()
        loc_data = loc_data[loc_data["Direction"].isin(active_dirs)]
        
        # 1. Sum counts for each day
        daily_sums = loc_data.groupby(["Date", "Day_Type", "Time_Segment", "Direction", "Speed_Label"], observed=False)["Count"].sum().reset_index()
        # 2. Average counts across all days
        segment_avg = daily_sums.groupby(["Day_Type", "Time_Segment", "Direction", "Speed_Label"], observed=False)["Count"].mean().reset_index()

        if segment_avg.empty:
            continue

        num_rows = len(active_dirs)

        # --- Plotting Setup ---
        fig, axes = plt.subplots(num_rows, 2, figsize=(16, 6 * num_rows), sharey=True)
        fig.suptitle(f"Average Bike Volumes by Speed: {loc}", fontsize=24, fontweight="bold", y=0.98 if num_rows > 1 else 1.05)

        # Force axes into a 2D array if there's only 1 direction being plotted
        if num_rows == 1:
            axes = np.array([axes])

        for d_idx, direction in enumerate(active_dirs):
            for i, day_type in enumerate(["Weekday", "Weekend"]):
                ax = axes[d_idx, i]
                data = segment_avg[(segment_avg["Day_Type"] == day_type) & (segment_avg["Direction"] == direction)]
                
                if not data.empty:
                    sns.barplot(
                        data=data, x="Time_Segment", y="Count", hue="Speed_Label",
                        order=segment_order, hue_order=speed_order, palette=speed_palette, ax=ax
                    )
                
                # Format axes
                ax.set_title(f"{day_type} ({direction})", fontsize=16)
                ax.set_ylabel("Average Bike Count" if i == 0 else "", fontsize=13)
                ax.set_xlabel("")
                ax.tick_params(axis='x', labelsize=12)

                # Format Legend 
                if i == 1 and ax.get_legend() is not None:
                    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=12, title="Speed")
                elif ax.get_legend() is not None:
                    ax.get_legend().remove()

        plt.tight_layout(rect=[0, 0, 1, 0.95] if num_rows > 1 else [0, 0, 1, 1])
        
        safe_loc_name = loc.replace(".", "").replace(" ", "_").strip("_")
        output_path = os.path.join(output_folder, f"{safe_loc_name}_BikeSpeed_Profile.png")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close() 
        
        print(f"Saved: {output_path}")

    print("\nSuccessfully generated all Bike Speed profiles.")
else:
    print("No relevant data available to process.")
