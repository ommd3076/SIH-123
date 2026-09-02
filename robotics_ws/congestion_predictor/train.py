"""Train + evaluate the congestion MLP against the heuristic baseline.

  python -m robotics_ws.congestion_predictor.train

Writes: models/congestion_mlp.json (weights + scaler)
        results/predictor_eval.json (honest metrics + default-choice verdict)
"""
from __future__ import annotations

import csv
import json
import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robotics_ws.congestion_predictor.mlp import (FEATURE_ORDER,   # noqa: E402
                                                  CongestionMLP,
                                                  HeuristicBaseline)
from robotics_ws.fleet_core.config import project_path           # noqa: E402


def load_dataset(path: str = None):
    path = path or project_path("datasets", "congestion_features.csv")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    X = np.array([[float(r[k]) for k in FEATURE_ORDER] for r in rows])
    y = np.array([float(r["label_occ"]) for r in rows])
    return X, y, rows


def train_mlp(X: np.ndarray, y: np.ndarray, epochs: int = 400,
              lr: float = 0.01, batch: int = 128, seed: int = 0) -> CongestionMLP:
    rng = np.random.default_rng(seed)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    Xn = (X - mu) / np.where(sd < 1e-9, 1.0, sd)
    mlp = CongestionMLP()
    mlp.mu, mlp.sd = mu, sd
    n = len(Xn)
    for epoch in range(epochs):
        idx = rng.permutation(n)
        total_loss = 0.0
        for s in range(0, n, batch):
            b = idx[s: s + batch]
            xb, yb = Xn[b], y[b]
            # forward
            acts = [xb]
            for i, (w, bw) in enumerate(zip(mlp.W, mlp.b)):
                z = acts[-1] @ w + bw
                acts.append(np.maximum(z, 0.0) if i < len(mlp.W) - 1 else z)
            pred = acts[-1]
            # loss (MSE)
            err = pred - yb.reshape(-1, 1)
            total_loss += float((err ** 2).sum())
            # backward
            grads_w = [None] * len(mlp.W)
            grads_b = [None] * len(mlp.b)
            delta = 2.0 * err / len(b)
            for i in range(len(mlp.W) - 1, -1, -1):
                grads_w[i] = acts[i].T @ delta
                grads_b[i] = delta.sum(axis=0)
                if i > 0:
                    delta = (delta @ mlp.W[i].T)
                    delta = delta * (acts[i] > 0.0)      # ReLU derivative
            # Adam-lite updates
            for i in range(len(mlp.W)):
                mlp.W[i] -= lr * grads_w[i]
                mlp.b[i] -= lr * grads_b[i]
        if epoch % 50 == 0:
            print(f"epoch {epoch:4d}  mse {total_loss / n:.4f}")
    return mlp


def evaluate(pred_fn, X: np.ndarray, y: np.ndarray, cap: float = 2.0) -> Dict:
    preds = np.array([max(0.0, pred_fn(x)) for x in X])
    err = preds - y
    mae = float(np.abs(err).mean())
    rmse = float(np.sqrt((err ** 2).mean()))
    # congestion classification: actual/predicted occupancy >= capacity
    y_cls = (y >= cap).astype(int)
    p_cls = (preds >= cap).astype(int)
    tp = int(((p_cls == 1) & (y_cls == 1)).sum())
    fp = int(((p_cls == 1) & (y_cls == 0)).sum())
    fn = int(((p_cls == 0) & (y_cls == 1)).sum())
    tn = int(((p_cls == 0) & (y_cls == 0)).sum())
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    acc = (tp + tn) / max(1, len(y))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "accuracy": round(acc, 4),
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": int(len(y))}


def main():
    X, y, rows = load_dataset()
    print(f"dataset: {len(X)} rows, {X.shape[1]} features")
    # temporal split (first 70% train, last 30% eval — no leakage)
    split = int(0.7 * len(X))
    Xtr, ytr, Xev, yev = X[:split], y[:split], X[split:], y[split:]

    print("\ntraining MLP ...")
    mlp = train_mlp(Xtr, ytr)
    print("heuristic baseline ...")
    heur = HeuristicBaseline()

    mlp_eval = evaluate(lambda x: mlp.predict(
        {k: v for k, v in zip(FEATURE_ORDER, x)}), Xev, yev)
    heur_eval = evaluate(heur.predict, Xev, yev)
    print("\nMLP eval:      ", json.dumps(mlp_eval))
    print("Heuristic eval:", json.dumps(heur_eval))

    mlp_better = mlp_eval["mae"] < heur_eval["mae"]
    verdict = "mlp" if mlp_better else "heuristic"
    report = {
        "dataset_rows": int(len(X)),
        "train_rows": int(split), "eval_rows": int(len(X) - split),
        "split": "temporal 70/30",
        "horizon_s": 5.0,
        "mlp": mlp_eval, "heuristic": heur_eval,
        "mlp_beats_heuristic_mae": mlp_better,
        "default_predictor": verdict,
        "note": ("The default runtime predictor follows the evaluation: "
                 "if the learned model does not beat the deterministic "
                 "heuristic on held-out data, the heuristic remains the "
                 "default and the MLP stays an experimental option "
                 "(build prompt section 10)."),
    }
    os.makedirs(project_path("results"), exist_ok=True)
    with open(project_path("results", "predictor_eval.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("\nverdict: default =", verdict)

    if mlp_better:
        os.makedirs(project_path("models"), exist_ok=True)
        with open(project_path("models", "congestion_mlp.json"), "w") as f:
            json.dump(mlp.to_json(), f, indent=1)
        print("model saved: models/congestion_mlp.json")
    return report


if __name__ == "__main__":
    main()
