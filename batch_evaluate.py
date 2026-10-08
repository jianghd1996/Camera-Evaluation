#!/usr/bin/env python3
"""Edit main() to run camera-pose comparisons on files or folders."""
import csv
import json
from pathlib import Path
import subprocess
import sys


def main():
    # Edit these paths. Each path can be an images.txt file or its parent folder.
    # Relative paths resolve relative to this script.
    cases = [
        ("raw_vs_colmap1", "colmap_raw.txt", "colmap1.txt"),
        ("raw_vs_colmap2", "colmap_raw.txt", "colmap2.txt"),
        # ("apple", "/path/before/sparse/0", "/path/after/colmap_final"),
    ]
    output_dir = "batch_results"
    align = "se3"       # none / se3 / sim3
    match = "stem"      # exact / stem (ignore filename extension)
    no_plots = False
    return evaluate_cases(cases, output_dir, align, match, no_plots)


def evaluate_cases(cases, output_dir="batch_results", align="se3", match="stem", no_plots=False):
    """Reusable batch API: cases is a list of (case_name, before_path, after_path)."""
    if align not in {"none", "se3", "sim3"} or match not in {"exact", "stem"}:
        raise ValueError("Invalid alignment or matching mode")
    if not cases:
        raise ValueError("No comparison cases configured")
    base = Path(__file__).resolve().parent
    def resolve_pose(path):
        path = Path(path).expanduser()
        if not path.is_absolute():
            path = base / path
        return path / "images.txt" if path.is_dir() else path
    rows = [{"case": case, "before": str(before), "after": str(after)}
            for case, before, after in cases]
    used = set()
    for row in rows:
        case = row['case']
        if not case or case in {'.', '..'} or '/' in case or '\\' in case or case in used:
            raise ValueError(f'Invalid or duplicate case name: {case!r}')
        used.add(case)
    root = (base / Path(output_dir).expanduser()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for row in rows:
        dest = root / row['case']
        command = [sys.executable, str(Path(__file__).with_name('evaluate_colmap_poses.py')),
                   '--before', str(resolve_pose(row['before'])),
                   '--after', str(resolve_pose(row['after'])),
                   '--output-dir', str(dest), '--align', align, '--match', match]
        if no_plots:
            command.append('--no-plots')
        run = subprocess.run(command, capture_output=True, text=True)
        result = {'case': row['case'], 'status': 'ok' if run.returncode == 0 else 'failed',
                  'before': row['before'], 'after': row['after'], 'align': align, 'match': match}
        if run.returncode:
            result['error'] = run.stderr.strip() or run.stdout.strip()
            print(f"FAILED {row['case']}: {result['error']}", file=sys.stderr)
        else:
            s = json.loads((dest / 'summary.json').read_text())
            result['matched_images'] = s['matched_images']
            result['scale'] = s['alignment']['after_to_before_scale']
            for prefix, key in [('position', 'evaluated_position'), ('rotation_deg', 'evaluated_rotation_deg'),
                                ('raw_position', 'raw_position'), ('raw_rotation_deg', 'raw_rotation_deg')]:
                for metric, value in s[key].items():
                    result[prefix + '_' + metric] = value
            result['largest_position_change'] = s['largest_position_change']
            result['largest_rotation_change'] = s['largest_rotation_change']
            print(f"OK {row['case']}: {s['matched_images']} images, position RMSE={s['evaluated_position']['rmse']:.6g}, rotation mean={s['evaluated_rotation_deg']['mean']:.6g} deg")
        results.append(result)
    fields = list(dict.fromkeys(key for row in results for key in row))
    with (root / 'batch_summary.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(results)
    print('Saved:', root / 'batch_summary.csv')
    return 1 if any(r['status'] == 'failed' for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
