# SAFR Visual Profiles

Python scripts to generate SAFR chart images from Excel exports.

## What this repo includes

- Data-to-chart scripts:
  - `visualize_counts.py`
  - `visualize_adt.py`
  - `visualize_grouping.py`
  - `visualize_near_misses.py`
  - `visualize_speeds.py`
  - `visualize_parking.py`

## What is intentionally not included

- Local machine paths
- Raw Excel files
- Generated charts and other local outputs

The scripts now accept portable command-line arguments and environment-variable defaults.

## Requirements

- Python 3.10+
- Packages listed in `requirements.txt`

Install:

```bash
pip install -r requirements.txt
```

## Input and output paths

Each script supports:

- `--input-dir` for source `.xlsx` files
- `--output-dir` for generated `.png` files

If omitted, each script uses defaults relative to this repository.

## Example usage

```bash
python visualize_counts.py --input-dir "data/counts" --output-dir "count visuals"
python visualize_adt.py --input-dir "data/adt" --output-dir "adt visuals"
python visualize_grouping.py --input-dir "data/grouping" --output-dir "grouping visuals"
python visualize_near_misses.py --input-dir "data/near_miss" --output-dir "near miss visuals"
python visualize_speeds.py --input-dir "data/speeds" --output-dir "speed visuals"
python visualize_parking.py --input-dir "data/parking" --output-dir "parking visuals"
```

## Environment variable overrides (optional)

- `SAFR_COUNTS_INPUT_DIR`, `SAFR_COUNTS_OUTPUT_DIR`
- `SAFR_ADT_INPUT_DIR`, `SAFR_ADT_OUTPUT_DIR`
- `SAFR_GROUPING_INPUT_DIR`, `SAFR_GROUPING_OUTPUT_DIR`
- `SAFR_NEARMISS_INPUT_DIR`, `SAFR_NEARMISS_OUTPUT_DIR`
- `SAFR_SPEEDS_INPUT_DIR`, `SAFR_SPEEDS_OUTPUT_DIR`
- `SAFR_PARKING_INPUT_DIR`, `SAFR_PARKING_OUTPUT_DIR`

## Notes

- The scripts expect field names similar to your current SAFR exports.
- If a source file uses different column names, that script may skip or fail parsing.
