#!/usr/bin/env bash
# Regenerate the congestion-prediction dataset and train/evaluate the MLP.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m robotics_ws.congestion_predictor.dataset
python3 -m robotics_ws.congestion_predictor.train
