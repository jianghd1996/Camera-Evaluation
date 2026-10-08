#!/usr/bin/env python3
"""Run evaluations from a CSV manifest; paths resolve relative to the CSV."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, help='CSV columns: case,before,after')
    p.add_argument('--output-dir', default='batch_results')
    p.add_argument('--align', choices=['none', 'se3', 'sim3'], default='se3')
    p.add_argument('--match', choices=['exact', 'stem'], default='stem')
    p.add_argument('--no-plots', action='store_true')
    args = p.parse_args()
    manifest = Path(args.manifest).resolve()
    with manifest.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'case', 'before', 'after'} <= set(reader.fieldnames or []):
            p.error('Manifest must have case,before,after columns')
        rows = list(reader)
    if not rows:
        p.error('Manifest is empty')
    used = set()
    for row in rows:
        case = row['case']
        if not case or case in {'.', '..'} or '/' in case or '\\' in case or case in used:
            p.error(f'Invalid or duplicate case name: {case!r}')
        used.add(case)
    root = Path(args.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for row in rows:
        dest = root / row['case']
        command = [sys.executable, str(Path(__file__).with_name('evaluate_colmap_poses.py')),
                   '--before', str(manifest.parent / row['before']),
                   '--after', str(manifest.parent / row['after']),
                   '--output-dir', str(dest), '--align', args.align, '--match', args.match]
        if args.no_plots:
            command.append('--no-plots')
        run = subprocess.run(command, capture_output=True, text=True)
        result = {'case': row['case'], 'status': 'ok' if run.returncode == 0 else 'failed',
                  'before': row['before'], 'after': row['after'], 'align': args.align, 'match': args.match}
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
