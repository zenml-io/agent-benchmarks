#!/bin/bash
# Download Snorkel's underwriting datasets (Apache-2.0) and the Census NAICS files, then rebuild the environment.
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
HF=https://huggingface.co/datasets/snorkelai
mkdir -p data_raw/data data_raw/codegen env/census
curl -fsSL -o data_raw/data/train-00000-of-00001.parquet "$HF/Multi-Turn-Insurance-Underwriting/resolve/main/data/train-00000-of-00001.parquet"
curl -fsSL -o data_raw/insurance_underwriting_train_data.parquet "$HF/Multi-Turn-Insurance-Underwriting/resolve/main/insurance_underwriting_train_data.parquet"
curl -fsSL -o data_raw/codegen/train.parquet "$HF/Multi-Turn-Insurance-Underwriting-Code-Gen/resolve/main/data/train-00000-of-00001.parquet"
C=https://www.census.gov/naics
curl -fsSL -o env/census/descriptions.xlsx "$C/2022NAICS/2022_NAICS_Descriptions.xlsx"
curl -fsSL -o env/census/codes.xlsx "$C/2022NAICS/2-6%20digit_2022_Codes.xlsx"
curl -fsSL -o env/census/c2022_2017.xlsx "$C/concordances/2022_to_2017_NAICS.xlsx"
curl -fsSL -o env/census/c2012_2017.xlsx "$C/concordances/2012_to_2017_NAICS.xlsx"
$PY -I env/extract.py data_raw env/extracted.json
$PY env/build_db.py env/extracted.json env/census env/insurance.db env/guidelines.txt
$PY env/oracle.py env/extracted.json env/insurance.db env/tasks.json
