import argparse
import glob
import os
import re
import warnings

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

# Mute pandas datetime format warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define elegant, 508-compliant colors
sns.set_theme(style="whitegrid")
mode_palette = {
    "Pedestrian": "#0072B2",  # Deep Ocean Blue
    "Bike": "#E69F00",        # Warm Amber/Orange
    "Other": "#CC79A7"        # Dusty Rose
}
mode_order = ["Pedestrian", "Bike", "Other"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(description="Generate bike and pedestrian count profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_COUNTS_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "counts")),
        help="Directory containing source count .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_COUNTS_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "count visuals")),
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

print(f"Found {len(file_paths)} Excel files. Generating Bike/Ped Count Profiles...")

df_list = []
for path in file_paths:
    location_name = os.path.basename(path).replace(".xlsx", "").replace(" ALL_PBC", "")
    xls = pd.ExcelFile(path)
    temp_df = pd.read_excel(xls, sheet_name=0)
    temp_df["Location"] = location_name
    df_list.append(temp_df)

if df_list:
    full_df = pd.concat(df_list, ignore_index=True)

    # -------------------------------------------------------------------------
    # 2. DATE & 15-MINUTE TIME PARSING
    # -------------------------------------------------------------------------
    date_col = [c for c in full_df.columns if "date" in str(c).lower() and "time" not in str(c).lower()][0]
    time_col = [c for c in full_df.columns if "time" in str(c).lower()][0]

    full_df["Date"] = pd.to_datetime(full_df[date_col]).dt.date
    full_df["Day_Type"] = pd.to_datetime(full_df[date_col]).dt.dayofweek.apply(
        lambda x: "Weekend" if x >= 5 else "Weekday"
    )

    parsed_time = pd.to_datetime(full_df[time_col].astype(str), format='mixed', errors="coerce").dt.time
    full_df["PlotTime"] = pd.to_datetime("2000-01-01 " + parsed_time.astype(str))

    # -------------------------------------------------------------------------
    # 3. FILTERING & MELTING 
    # -------------------------------------------------------------------------
    summary_pattern = re.compile(r"^(ped|pedestrian|bike|e_bike|e-bike|ebike|other)_(nb|sb|eb|wb)$", flags=re.IGNORECASE)
    summary_cols = [c for c in full_df.columns if summary_pattern.match(str(c).strip())]

    keep_cols = ["Date", "PlotTime", "Day_Type", "Location"] + summary_cols
    filtered_df = full_df[keep_cols].copy()

    df_long = pd.melt(
        filtered_df, id_vars=["Date", "PlotTime", "Day_Type", "Location"],
        value_vars=summary_cols, var_name="Category", value_name="Count"
    )

    df_long["Count"] = pd.to_numeric(df_long["Count"], errors="coerce").fillna(0)

    def parse_mode(cat_string):
        cat_lower = str(cat_string).lower()
        if "bike" in cat_lower or "ebike" in cat_lower or "e_bike" in cat_lower or "e-bike" in cat_lower: 
            return "Bike"
        elif "ped" in cat_lower: 
            return "Pedestrian"
        else: 
            return "Other"

    df_long["Mode"] = df_long["Category"].apply(parse_mode)
    df_long["Mode"] = pd.Categorical(df_long["Mode"], categories=mode_order, ordered=True)
    df_long["Direction"] = df_long["Category"].apply(lambda x: str(x).split("_")[-1].upper())

    def hour_fmt(x, pos):
        if pd.isna(x): return ""
        return mdates.num2date(x).strftime('%I:%M%p').lstrip('0')

    # -------------------------------------------------------------------------
    # 4. DASHBOARD GENERATION (LOCAL SCALING)
    # -------------------------------------------------------------------------
    for loc in df_long["Location"].unique():
        loc_data = df_long[df_long["Location"] == loc].copy()
        
        dir_sums = loc_data.groupby("Direction")["Count"].sum()
        active_dirs = dir_sums[dir_sums > 0].index.tolist()
        loc_data = loc_data[loc_data["Direction"].isin(active_dirs)]
        
        daily_totals = loc_data.groupby(["Date", "Day_Type", "Mode", "Direction"], observed=False)["Count"].sum().reset_index()
        daily_avg = daily_totals.groupby(["Day_Type", "Mode", "Direction"], observed=False)["Count"].mean().reset_index()
        
        interval_totals = loc_data.groupby(["Date", "Day_Type", "Mode", "Direction", "PlotTime"], observed=False)["Count"].sum().reset_index()
        interval_avg = interval_totals.groupby(["Day_Type", "Mode", "Direction", "PlotTime"], observed=False)["Count"].mean().reset_index()

        max_daily_y = daily_avg["Count"].max() * 1.05 if not daily_avg.empty else None
        
        if not interval_avg.empty:
            loc_interval_stacked = interval_avg.groupby(["Day_Type", "Direction", "PlotTime"], observed=False)["Count"].sum()
            max_interval_y = loc_interval_stacked.max() * 1.05
        else:
            max_interval_y = None

        has_two_dirs = len(active_dirs) > 1
        num_rows = 3 if has_two_dirs else 2
        
        fig, axes = plt.subplots(num_rows, 2, figsize=(18, 6 * num_rows))
        fig.suptitle(f"Bike/Ped Counts: {loc}", fontsize=24, fontweight="bold", y=0.97)

        if axes.ndim == 1:
            axes = np.array([axes])

        # ROW 1: Daily Bar Charts
        for i, day_type in enumerate(["Weekday", "Weekend"]):
            data_daily = daily_avg[daily_avg["Day_Type"] == day_type]
            if not data_daily.empty:
                sns.barplot(
                    data=data_daily, x="Direction", y="Count", hue="Mode", 
                    hue_order=mode_order, palette=mode_palette, ax=axes[0, i]
                )
            
            axes[0, i].set_title(f"Average Daily Volume - {day_type}", fontsize=16)
            axes[0, i].set_ylabel("Average Daily Count" if i == 0 else "", fontsize=13)
            axes[0, i].set_xlabel("")
            
            if pd.notna(max_daily_y): axes[0, i].set_ylim(0, max_daily_y)

            if i == 1 and axes[0, i].get_legend() is not None:
                axes[0, i].legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=12)
            elif axes[0, i].get_legend() is not None:
                axes[0, i].get_legend().remove()

        # ROWS 2 & 3: 15-Minute Stacked Bar Profiles
        for d_idx, direction in enumerate(active_dirs):
            row_idx = d_idx + 1
            
            for i, day_type in enumerate(["Weekday", "Weekend"]):
                ax = axes[row_idx, i]
                day_dir_data = interval_avg[(interval_avg["Day_Type"] == day_type) & (interval_avg["Direction"] == direction)]
                
                if not day_dir_data.empty:
                    pivot_df = day_dir_data.pivot(index="PlotTime", columns="Mode", values="Count").fillna(0)
                    ordered_cols = [m for m in mode_order if m in pivot_df.columns]
                    pivot_df = pivot_df[ordered_cols]
                    
                    bottom = np.zeros(len(pivot_df))
                    width = 1/(24*4) * 0.8
                    
                    for mode in ordered_cols:
                        ax.bar(pivot_df.index, pivot_df[mode], width=width, bottom=bottom, 
                               color=mode_palette[mode], label=mode, align="center")
                        bottom += pivot_df[mode]

                ax.set_title(f"15-Minute Traffic Profile - {day_type} ({direction})", fontsize=16)
                ax.set_ylabel("Average Count" if i == 0 else "", fontsize=13)
                ax.set_xlabel("Time of Day", fontsize=13)
                
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                ax.xaxis.set_major_formatter(FuncFormatter(hour_fmt))
                ax.tick_params(axis='x', rotation=45, labelsize=11)
                ax.set_xlim(pd.to_datetime("2000-01-01 06:45:00"), pd.to_datetime("2000-01-01 18:15:00")) 
                
                if pd.notna(max_interval_y): ax.set_ylim(0, max_interval_y)
                
                if i == 1 and ax.get_legend() is not None:
                    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=12)
                elif ax.get_legend() is not None:
                    ax.get_legend().remove()

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        
        safe_loc_name = loc.replace(".", "").replace(" ", "_").strip("_")
        output_path = os.path.join(output_folder, f"{safe_loc_name}_PBC_Profile.png")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close() 
        
        print(f"Saved: {output_path}")

    print("\nSuccessfully generated all Bike/Ped Count profiles.")
else:
    print("No relevant data available to process.")
