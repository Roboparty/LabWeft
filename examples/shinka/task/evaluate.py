"""Frozen synthetic evaluator implementing Shinka's local job contract."""
import argparse
import json
import math
from pathlib import Path
import runpy


def evaluate(program_path, results_dir):
    output = Path(results_dir)
    output.mkdir(parents=True, exist_ok=True)
    error = None
    try:
        predict = runpy.run_path(str(program_path))["predict"]
        cases = [-3, -2, -1, 0, 1, 2, 3]
        values = [float(predict(x)) for x in cases]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Nonfinite prediction")
        mse = sum((value - x * x) ** 2 for x, value in zip(cases, values)) / len(cases)
        metrics = {"combined_score": 1 / (1 + mse), "public": {"mse": mse, "cases": len(cases)},
                   "private": {}, "text_feedback": "Synthetic target is x squared; higher combined_score is better."}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        metrics = {"combined_score": 0, "public": {}, "private": {"error": error},
                   "text_feedback": "Synthetic evaluator could not compute a finite prediction."}
    (output / "metrics.json").write_text(json.dumps(metrics, allow_nan=False), encoding="utf-8")
    (output / "correct.json").write_text(json.dumps({"correct": error is None, "error": error}), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", required=True, type=Path)
    parser.add_argument("--results_dir", required=True, type=Path)
    args = parser.parse_args()
    evaluate(args.program_path, args.results_dir)
