import argparse
import glob
import os
import warnings

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

# Mute pandas datetime format warnings for cleaner terminal output
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define 508-compliant colors (Okabe-Ito palette)
sns.set_theme(style="whitegrid")
vol_color = "#0072B2"  # Colorblind-safe Deep Blue for Volume (Bars)
spd_color = "#D55E00"  # Colorblind-safe Vermillion/Red for Speed (Line)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Custom formatter to remove leading zeros from hour labels (e.g., 02 PM -> 2 PM)
def hour_fmt(x, pos):
    if pd.isna(x): return ""
    return mdates.num2date(x).strftime('%I %p').lstrip('0')

def parse_args():
    parser = argparse.ArgumentParser(description="Generate ADT profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_ADT_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "adt")),
        help="Directory containing source ADT .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_ADT_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "adt visuals")),
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

print(f"Found {len(file_paths)} Excel files. Generating ADT Profiles...")

# -------------------------------------------------------------------------
# 2. DATA PROCESSING & VISUALIZATION
# -------------------------------------------------------------------------
for path in file_paths:
    location_name = os.path.basename(path).replace(".xlsx", "").replace(" ALL_ADT", "").strip()
    
    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"Could not read {path}: {e}")
        continue
        
    # --- DYNAMIC COLUMN PARSING ---
    try:
        speed_col = next(c for c in df.columns if 'speed' in str(c).lower() or 'mph' in str(c).lower())
        
        possible_lanes = [c for c in df.columns if 'lane' in str(c).lower() or 'dir' in str(c).lower()]
        if possible_lanes:
            lane_col = possible_lanes[0]
        else:
            lane_col = next(c for c in df.columns if df[c].astype(str).str.contains('bound', case=False, na=False).any())
        
        dt_cols = [c for c in df.columns if c not in [speed_col, lane_col]]
        
    except StopIteration:
        print(f"Skipping {location_name} - Could not identify required Lane or Speed columns.")
        continue
    
    # Safely construct the DateTime object
    df['Raw_DT'] = df[dt_cols].astype(str).agg(' '.join, axis=1)
    df['DateTime'] = pd.to_datetime(df['Raw_DT'], errors='coerce')
    df = df.dropna(subset=['DateTime']) 
    
    df[lane_col] = df[lane_col].astype(str).str.title().str.strip()
    df[speed_col] = pd.to_numeric(df[speed_col], errors='coerce')
    
    # --- HOURLY AGGREGATION SETUP ---
    df['Date'] = df['DateTime'].dt.date
    df['Hour'] = df['DateTime'].dt.hour
    df['PlotTime'] = pd.to_datetime("2000-01-01 " + df['Hour'].astype(str).str.zfill(2) + ":00:00")
    df['Day_Type'] = df['DateTime'].dt.dayofweek.apply(lambda x: 'Weekend' if x >= 5 else 'Weekday')
    
    unique_days = df.groupby('Day_Type')['Date'].nunique().to_dict()
    
    # Aggregate to Hourly Averages
    stats = df.groupby(['Day_Type', lane_col, 'PlotTime']).agg(
        Total_Volume=(speed_col, 'count'),
        Avg_Speed=(speed_col, 'mean')
    ).reset_index()
    
    stats['Avg_Volume'] = stats.apply(lambda row: row['Total_Volume'] / unique_days.get(row['Day_Type'], 1), axis=1)
    
    active_dirs = stats[lane_col].unique()
    num_rows = len(active_dirs)
    
    if num_rows == 0:
        continue

    # --- CALCULATE GLOBAL Y-AXIS LIMITS ---
    max_vol = stats['Avg_Volume'].max()
    max_spd = stats['Avg_Speed'].max()
    
    # Add 15% headroom above the highest value so charts don't hit the absolute ceiling
    y_lim_vol = max_vol * 1.15 if pd.notna(max_vol) and max_vol > 0 else 10
    y_lim_spd = max_spd * 1.15 if pd.notna(max_spd) and max_spd > 0 else 25
    
    # --- Plotting Setup ---
    fig, axes = plt.subplots(num_rows, 2, figsize=(18, 6 * num_rows), squeeze=False)
    
    # Centered Title
    fig.suptitle(f"Average Hourly Traffic (ADT): {location_name}", fontsize=24, fontweight="bold", x=0.48, ha='center', y=0.98 if num_rows > 1 else 1.05)
        
    for d_idx, direction in enumerate(active_dirs):
        for i, day_type in enumerate(["Weekday", "Weekend"]):
            ax_vol = axes[d_idx, i]
            data = stats[(stats['Day_Type'] == day_type) & (stats[lane_col] == direction)].sort_values('PlotTime')
            
            if not data.empty:
                # 1. Plot Volume as a Bar Chart (Primary Y-Axis)
                ax_vol.bar(data['PlotTime'], data['Avg_Volume'], width=1/24*0.8, color=vol_color, alpha=0.85, label="Avg Volume")
                ax_vol.set_ylabel("Volume (Vehicles)" if i == 0 else "", color=vol_color, fontsize=13, fontweight="bold")
                
                # Apply labelsize here, not in setp
                ax_vol.tick_params(axis='y', labelcolor=vol_color)
                ax_vol.set_ylim(0, y_lim_vol) # Apply Uniform Volume Scale
                
                # 2. Plot Speed as a Line Chart (Secondary Y-Axis)
                ax_spd = ax_vol.twinx()
                ax_spd.plot(data['PlotTime'], data['Avg_Speed'], color=spd_color, linewidth=2.5, marker='o', markersize=4, label="Avg Speed")
                ax_spd.set_ylabel("Speed (mph)" if i == 1 else "", color=spd_color, fontsize=13, fontweight="bold")
                ax_spd.tick_params(axis='y', labelcolor=spd_color)
                ax_spd.set_ylim(0, y_lim_spd) # Apply Uniform Speed Scale
                ax_spd.grid(False) 
                
                # Format X-axis with custom FuncFormatter for clean hours
                ax_vol.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                ax_vol.xaxis.set_major_formatter(FuncFormatter(hour_fmt))
                
                # Apply labelsize via tick_params, but handle rotation via setp
                ax_vol.tick_params(axis='x', labelsize=11)
                plt.setp(ax_vol.xaxis.get_majorticklabels(), rotation=45, ha='right', rotation_mode='anchor')
                
                # Cut the X-axis off exactly after the 11 PM data point (removes the trailing 12 AM label)
                ax_vol.set_xlim(pd.to_datetime("1999-12-31 23:20:00"), pd.to_datetime("2000-01-01 23:45:00"))
            else:
                ax_vol.axis('off')
                ax_vol.text(0.5, 0.5, f"No Data for {day_type}", ha='center', va='center', fontsize=14, color='gray')
            
            ax_vol.set_title(f"{day_type} ({direction})", fontsize=16)
            ax_vol.set_xlabel("Time of Day" if d_idx == num_rows - 1 else "", fontsize=13)
            
            # Format combined Legend inside the top-right corner of ALL graphs
            if not data.empty:
                lines1, labels1 = ax_vol.get_legend_handles_labels()
                lines2, labels2 = ax_spd.get_legend_handles_labels()
                ax_spd.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=11, framealpha=0.9)
                
    # Since legends are now internal, expand the charts to use the full image width
    plt.tight_layout(rect=[0, 0, 1, 0.95] if num_rows > 1 else [0, 0, 1, 1])
    
    safe_loc_name = location_name.replace(".", "").replace(" ", "_").strip("_")
    output_path = os.path.join(output_folder, f"{safe_loc_name}_ADT_Profile.png")
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    
    print(f"Successfully Saved: {output_path}")

print("\nAnalysis Complete: Successfully generated all ADT profiles.")
