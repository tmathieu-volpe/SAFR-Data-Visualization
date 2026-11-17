import argparse
import glob
import os
import warnings

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter, PercentFormatter

# Mute pandas datetime format warnings for cleaner terminal output
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define 508-compliant colors (Okabe-Ito palette)
sns.set_theme(style="whitegrid")
visitor_color = "#0072B2"  # Colorblind-safe Deep Blue for Visitor Parking
nps_color = "#D55E00"      # Colorblind-safe Vermillion (Red) for NPS/Gov't Parking
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Custom formatter to remove leading zeros from hour labels (e.g., 02 PM -> 2 PM)
def hour_fmt(x, pos):
    if pd.isna(x): return ""
    return mdates.num2date(x).strftime('%I %p').lstrip('0')

def parse_args():
    parser = argparse.ArgumentParser(description="Generate parking profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_PARKING_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "parking")),
        help="Directory containing source parking .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_PARKING_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "parking visuals")),
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

print(f"Found {len(file_paths)} Excel files. Pre-scanning for uniform axes...")

# Dictionary to hold the combined capacities for both sides of the street
capacities = {
    "H. Jefferson Street": {
        "Visitor": 16 + 10,  # North + South
        "NPS": 0 + 13        # North + South
    },
    "K. Van Ness": {
        "Visitor": 56 + 19,  # East + West
        "NPS": 0 + 28        # East + West
    }
}

# -------------------------------------------------------------------------
# 2. PRE-SCAN & DATA PROCESSING
# -------------------------------------------------------------------------
global_max_y = 100 # Baseline set to 100% capacity
processed_stats = {} # Store processed data so we don't have to read the files twice

for path in file_paths:
    file_name = os.path.basename(path)
    location_name = file_name.replace(".xlsx", "").replace("_Parking", "").strip()
    
    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"Could not read {path}: {e}")
        continue
    
    matched_loc = None
    for loc in capacities.keys():
        if loc in location_name:
            matched_loc = loc
            break
            
    if not matched_loc:
        print(f"Skipping {location_name} - Could not match to a known capacity definition.")
        continue
    
    # --- DYNAMIC COLUMN PARSING ---
    nps_col = next((c for c in df.columns if 'nps' in str(c).lower() and 'use' in str(c).lower()), None)
    gov_col = next((c for c in df.columns if 'gov' in str(c).lower() and 'use' in str(c).lower()), None)
    visitor_col = next((c for c in df.columns if 'visitor' in str(c).lower() and 'use' in str(c).lower()), None)
    time_col = next((c for c in df.columns if 'time' in str(c).lower()), 'Time')
    date_col = next((c for c in df.columns if 'date' in str(c).lower()), 'Date')
    daytype_col = next((c for c in df.columns if 'day type' in str(c).lower() or 'day_type' in str(c).lower()), 'Day Type')
    
    df['NPS_Gov_Use'] = df[nps_col].fillna(0) + df[gov_col].fillna(0)
    df['Visitor_Use'] = df[visitor_col].fillna(0)
    
    df['Day_Type'] = df[daytype_col].astype(str).str.strip().str.title()
    
    parsed_time = pd.to_datetime(df[time_col].astype(str), format='mixed', errors='coerce').dt.time
    df['PlotTime'] = pd.to_datetime("2000-01-01 " + parsed_time.astype(str))
    df = df.dropna(subset=['PlotTime'])
    
    # --- AGGREGATION SETUP ---
    daily_sums = df.groupby([date_col, 'Day_Type', 'PlotTime'])[['Visitor_Use', 'NPS_Gov_Use']].sum().reset_index()
    stats = daily_sums.groupby(['Day_Type', 'PlotTime'])[['Visitor_Use', 'NPS_Gov_Use']].mean().reset_index()
    
    cap_visitor = capacities[matched_loc]["Visitor"]
    cap_nps = capacities[matched_loc]["NPS"]
    
    stats['Visitor_Occ_Pct'] = (stats['Visitor_Use'] / cap_visitor) * 100 if cap_visitor > 0 else 0
    stats['NPS_Occ_Pct'] = (stats['NPS_Gov_Use'] / cap_nps) * 100 if cap_nps > 0 else 0
    
    local_max = max(stats['Visitor_Occ_Pct'].max() if not stats.empty else 0, 
                    stats['NPS_Occ_Pct'].max() if not stats.empty else 0)
    
    if local_max > global_max_y:
        global_max_y = local_max
        
    processed_stats[matched_loc] = stats

# Apply a 5% visual margin above the absolute highest capacity found across all files
global_y_lim = max(100, global_max_y * 1.05) 

# -------------------------------------------------------------------------
# 3. DASHBOARD GENERATION
# -------------------------------------------------------------------------
print("Generating Uniform Parking Occupancy Profiles...")

for matched_loc, stats in processed_stats.items():
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=True)
    
    # Position the main title at the very top
    fig.suptitle(f"Average Parking Occupancy: {matched_loc}", fontsize=24, fontweight="bold", y=0.98)
    
    has_data = False
    
    for i, day_type in enumerate(["Weekday", "Weekend"]):
        ax = axes[i]
        data = stats[stats['Day_Type'] == day_type].sort_values('PlotTime')
        
        if not data.empty:
            has_data = True
            ax.plot(data['PlotTime'], data['Visitor_Occ_Pct'], color=visitor_color, linewidth=3.5, marker='o', markersize=6, label="Visitor Parking")
            ax.plot(data['PlotTime'], data['NPS_Occ_Pct'], color=nps_color, linewidth=3.5, marker='o', markersize=6, label="NPS/Gov't Parking")
            
            ax.set_ylim(0, global_y_lim)
            ax.yaxis.set_major_formatter(PercentFormatter(100)) 
            
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            ax.xaxis.set_major_formatter(FuncFormatter(hour_fmt))
            
            ax.tick_params(axis='x', labelsize=11)
            ax.tick_params(axis='y', labelsize=11)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', rotation_mode='anchor')
            
            ax.set_xlim(pd.to_datetime("2000-01-01 05:00:00"), pd.to_datetime("2000-01-01 22:00:00"))
            ax.set_ylabel("Average Occupancy" if i == 0 else "", fontsize=13, fontweight="bold")
        else:
            ax.axis('off')
            ax.text(0.5, 0.5, f"No Data for {day_type}", ha='center', va='center', fontsize=14, color='gray')
            
        ax.set_title(f"{day_type}", fontsize=16)
        ax.set_xlabel("Time of Day", fontsize=13)
        
    # --- UNIFIED TOP-CENTER LEGEND ---
    if has_data:
        # Extract the handles and labels from the first populated axis
        handles, labels = axes[0].get_legend_handles_labels() if len(axes[0].get_lines()) > 0 else axes[1].get_legend_handles_labels()
        
        # Place the legend centered horizontally, sitting just below the main title
        fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 0.88), ncol=2, fontsize=12, framealpha=0.9)
            
    # Adjust tight_layout to leave room at the top for both the title and the new horizontal legend
    plt.tight_layout(rect=[0, 0, 1, 0.83])
    
    safe_loc_name = matched_loc.replace(".", "").replace(" ", "_").strip("_")
    output_path = os.path.join(output_folder, f"{safe_loc_name}_Parking_Profile.png")
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    
    print(f"Successfully Saved: {output_path}")

print("\nAnalysis Complete: Successfully generated all Parking profiles.")
