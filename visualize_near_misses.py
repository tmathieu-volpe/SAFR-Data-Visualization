import argparse
import glob
import os
import textwrap
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import MaxNLocator

# Mute pandas datetime format warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Set visual style and define an extended, high-contrast palette
sns.set_theme(style="whitegrid")
custom_palette = [
    "#0072B2", # Deep Blue
    "#E69F00", # Orange
    "#009E73", # Bluish Green
    "#D55E00", # Vermillion
    "#CC79A7", # Dusty Rose
    "#56B4E9", # Light Blue
    "#004D40", # Dark Teal (Replacing Yellow for better contrast)
    "#990000", # Brick Red
    "#000055", # Navy
    "#000000"  # Black
]

segment_order = ["Morning\n(7:00-9:00 AM)", "Mid-day\n(11:00 AM-1:00 PM)", "Late Afternoon\n(4:00-6:00 PM)"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(description="Generate near-miss profile charts.")
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("SAFR_NEARMISS_INPUT_DIR", os.path.join(SCRIPT_DIR, "data", "near_miss")),
        help="Directory containing source near-miss .xlsx files.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SAFR_NEARMISS_OUTPUT_DIR", os.path.join(SCRIPT_DIR, "near miss visuals")),
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

print(f"Found {len(file_paths)} Excel files. Pre-scanning for consistent classification colors...")

# -------------------------------------------------------------------------
# 2. PRE-SCAN, SUB-SETTING & GLOBAL COLOR MAPPING
# -------------------------------------------------------------------------
valid_dfs = {}
all_classes = set()

for path in file_paths:
    location_name = os.path.basename(path).replace(".xlsx", "").replace(" ALL_NearMiss", "").strip()
    try:
        xls = pd.ExcelFile(path)
        df = pd.read_excel(xls, sheet_name=0)
        
        if all(col in df.columns for col in ["Date", "Day_Type", "Time", "Classification"]):
            df["Classification"] = df["Classification"].astype(str).str.title().str.strip()
            
            # --- DYNAMIC REGEX SUB-SETTING LOGIC ---
            notes_col = next((c for c in df.columns if 'activity' in c.lower() or 'note' in c.lower() or 'obs' in c.lower()), None)
            
            if notes_col:
                cod_mask = df["Classification"].str.contains('Change Of Direction', case=False, na=False)
                subset_notes = df.loc[cod_mask, notes_col].astype(str)
                
                # Regex patterns (Scooter removed to default to 'Other')
                ped_pattern = r'avoid.*ped|due to.*ped|ped.*in front|ped.*suddenly|kids suddenly'
                bike_pattern = r'avoid.*bik|avoid.*bicycle|due to.*bik|due to.*bicycle'
                car_pattern = r'avoid.*car|due to.*car|avoid.*veh|due to.*veh|avoid.*auto'
                
                df.loc[cod_mask, "Classification"] = np.select(
                    [
                        subset_notes.str.contains(ped_pattern, case=False, regex=True, na=False),
                        subset_notes.str.contains(bike_pattern, case=False, regex=True, na=False),
                        subset_notes.str.contains(car_pattern, case=False, regex=True, na=False)
                    ],
                    [
                        'Change Of Direction (Avoid Pedestrian)',
                        'Change Of Direction (Avoid Bicycle)',
                        'Change Of Direction (Avoid Car)'
                    ],
                    default='Change Of Direction (Other)'
                )
            
            all_classes.update(df["Classification"].unique())
            valid_dfs[location_name] = df
        else:
            print(f"Skipping {location_name} - Missing required columns.")
            
    except Exception as e:
        print(f"Could not read {path}: {e}")

# Map each unique classification to a set color alphabetically
class_color_map = {
    cls: custom_palette[i % len(custom_palette)] 
    for i, cls in enumerate(sorted(list(all_classes)))
}

# -------------------------------------------------------------------------
# 3. DATA PROCESSING & VISUALIZATION
# -------------------------------------------------------------------------
print("Generating Near Miss Profiles...")

for location_name, df in valid_dfs.items():
    
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df["PlotTime"] = pd.to_datetime(df["Time"].astype(str), format='mixed', errors="coerce").dt.time

    def get_segment(pt):
        if pd.isna(pt): return None
        h = pt.hour
        if h in [7, 8]: return "Morning\n(7:00-9:00 AM)"
        elif h in [11, 12]: return "Mid-day\n(11:00 AM-1:00 PM)"
        elif h in [16, 17]: return "Late Afternoon\n(4:00-6:00 PM)"
        return None
        
    df["Time_Segment"] = df["PlotTime"].apply(get_segment)
    unique_dates = df.groupby("Day_Type")["Date"].nunique().to_dict()

    global_max_y = 0
    for day_type in ["Weekday", "Weekend"]:
        day_data = df[df["Day_Type"] == day_type]
        if not day_data.empty:
            num_days = unique_dates.get(day_type, 1)
            segment_counts = day_data.groupby("Time_Segment").size().reset_index(name="Total")
            segment_counts["Average"] = segment_counts["Total"] / num_days
            max_val = segment_counts["Average"].max()
            if pd.notna(max_val) and max_val > global_max_y:
                global_max_y = max_val

    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    fig.suptitle(f"Near Miss Profile: {location_name}", fontsize=24, fontweight="bold", y=0.98)

    for i, day_type in enumerate(["Weekday", "Weekend"]):
        day_data = df[df["Day_Type"] == day_type].copy()
        
        # --- TOP ROW (BAR) ---
        ax_bar = axes[0, i]
        if not day_data.empty:
            num_days = unique_dates.get(day_type, 1)
            segment_counts = day_data.groupby("Time_Segment").size().reset_index(name="Total")
            segment_counts["Average"] = segment_counts["Total"] / num_days
            
            sns.barplot(
                data=segment_counts, x="Time_Segment", y="Average", 
                order=segment_order, color="#0072B2", ax=ax_bar
            )
            if global_max_y > 0:
                ax_bar.set_ylim(0, global_max_y * 1.15)
                
            ax_bar.yaxis.set_major_locator(MaxNLocator(integer=True))
        
        ax_bar.set_title(f"Average Near Misses by Time of Day - {day_type}", fontsize=16, pad=15)
        ax_bar.set_ylabel("Average Near Misses per Day" if i == 0 else "", fontsize=13)
        ax_bar.set_xlabel("")
        ax_bar.tick_params(axis='x', labelsize=12)

        # --- BOTTOM ROW (PIE) ---
        ax_pie = axes[1, i]
        if not day_data.empty:
            class_counts = day_data["Classification"].value_counts()
            
            def custom_autopct(pct):
                return f"{pct:.1f}%" if pct >= 4.0 else ""
            
            pie_colors = [class_color_map[cls] for cls in class_counts.index]
            
            wedges, texts, autotexts = ax_pie.pie(
                class_counts, 
                labels=None, 
                autopct=custom_autopct,
                startangle=90, 
                colors=pie_colors,
                radius=0.9,          
                center=(0.4, -0.1),  
                textprops={'fontsize': 10}
            )
            
            ax_pie.axis('equal') 
            ax_pie.set_xlim(-1.4, 1.4)
            ax_pie.set_ylim(-1.2, 1.0)
            
            # Reverted back to standard clean bold white text without path effects
            for autotext in autotexts:
                autotext.set_fontweight('bold')
                autotext.set_color('white')

            ax_pie.set_title(f"Near Miss Breakdown - {day_type}", fontsize=16, pad=15)
            
            legend_labels = []
            for idx, val in class_counts.items():
                wrapped_text = textwrap.fill(idx, width=25) 
                legend_labels.append(f"{wrapped_text} ({val/class_counts.sum()*100:.1f}%)")

            ax_pie.legend(
                wedges, legend_labels, 
                title="Classification", 
                loc="upper left",
                bbox_to_anchor=(0.0, 1.0), 
                fontsize=10,
                title_fontsize=11
            )
            
        else:
            ax_pie.axis('off')
            ax_pie.text(0.5, 0.5, f"No Near Miss Data for {day_type}s", 
                        ha='center', va='center', fontsize=14, color='gray')
            ax_bar.text(0.5, 0.5, f"No Data", ha='center', va='center', fontsize=14, color='gray')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    
    safe_loc_name = location_name.replace(".", "").replace(" ", "_").strip("_")
    output_path = os.path.join(output_folder, f"{safe_loc_name}_NearMiss_Profile.png")
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close() 
    
    print(f"Saved: {output_path}")

print("\nSuccessfully generated all Near Miss profiles.")
