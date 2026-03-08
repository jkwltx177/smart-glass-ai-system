# Prediction Model Weights

Place model files for predictive inference in this directory.

Supported filenames:
- `lgbm_failure.txt`
- `lgbm_rul.txt`
- `xgb_failure.json`
- `xgb_rul.json`
- `tcn_failure.pt`
- `tcn_rul.pt`

Notes:
- If none of the files exist, the service falls back to `heuristic-v1`.
- You can override this path with `PREDICTION_MODEL_DIR` in `.env`.
