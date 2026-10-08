#!/usr/bin/env python3
"""Compare COLMAP images.txt poses by exact image name.
Dependencies: numpy; matplotlib for plots. Before is the reference coordinate frame.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def read_poses(path, match="exact"):
    poses = {}
    expecting_pose = True
    with open(path, encoding='utf-8-sig') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith('#'):
                continue
            if not expecting_pose:
                expecting_pose = True  # consume POINTS2D line, including an empty line
                continue
            if not line:
                continue
            parts = line.split(maxsplit=9)
            try:
                if len(parts) != 10:
                    raise ValueError('expected 10 fields')
                int(parts[0]); int(parts[8])
                values = np.array([float(v) for v in parts[1:8]])
                if not np.all(np.isfinite(values)):
                    raise ValueError('non-finite pose')
                q = values[:4]
                norm = np.linalg.norm(q)
                if norm < 1e-12:
                    raise ValueError('zero quaternion')
                w, x, y, z = q / norm
                R = np.array([
                    [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                    [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                    [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
                name = Path(parts[9]).stem if match == "stem" else parts[9]
                if name in poses:
                    raise ValueError('duplicate image name: ' + name)
                poses[name] = (-R.T @ values[4:], R.T)
            except ValueError as e:
                raise ValueError(f'{path}:{lineno}: {e}') from e
            expecting_pose = False
    if not poses:
        raise ValueError(f'No poses in {path}')
    return poses


def align_centers(source, target, mode):
    if mode == 'none':
        return 1., np.eye(3), np.zeros(3)
    if len(source) < 3:
        raise ValueError('Alignment requires at least 3 matched cameras')
    a = source - source.mean(0)
    b = target - target.mean(0)
    if np.linalg.matrix_rank(a) < 2 or np.linalg.matrix_rank(b) < 2:
        raise ValueError('Camera centers are collinear/coincident; alignment rotation is ambiguous')
    U, singular, Vt = np.linalg.svd(b.T @ a / len(a))
    correction = np.ones(3)
    correction[-1] = 1 if np.linalg.det(U @ Vt) >= 0 else -1
    rotation = U @ np.diag(correction) @ Vt
    scale = float(np.sum(singular * correction) / np.mean(np.sum(a*a, axis=1))) if mode == 'sim3' else 1.
    if scale <= 0:
        raise ValueError('Invalid alignment scale')
    translation = target.mean(0) - scale * rotation @ source.mean(0)
    return scale, rotation, translation


def rotation_errors(before, after):
    relative = before @ np.transpose(after, (0, 2, 1))
    return np.degrees(np.arccos(np.clip((np.trace(relative, axis1=1, axis2=2)-1)/2, -1, 1)))


def stats(values):
    return {k: float(v) for k, v in {
        'mean': np.mean(values), 'median': np.median(values),
        'rmse': np.sqrt(np.mean(values**2)), 'p95': np.percentile(values, 95),
        'max': np.max(values), 'min': np.min(values)}.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', required=True, help='Before optimization images.txt')
    p.add_argument('--after', required=True, help='After optimization images.txt')
    p.add_argument('--output-dir', default='pose_evaluation')
    p.add_argument('--align', choices=['none', 'se3', 'sim3'], default='none',
                   help='Align AFTER centers to BEFORE: rigid SE3 or similarity Sim3; default compares raw poses')
    p.add_argument('--match', choices=['exact', 'stem'], default='exact', help='stem ignores extensions; matching names must refer to the same image')
    p.add_argument('--no-plots', action='store_true')
    args = p.parse_args()
    before, after = read_poses(args.before, args.match), read_poses(args.after, args.match)
    names = sorted(before.keys() & after.keys())
    if not names:
        raise ValueError('No matching image names')
    C0, Q0 = map(np.stack, zip(*(before[n] for n in names)))
    C1, Q1 = map(np.stack, zip(*(after[n] for n in names)))
    scale, rotation, translation = align_centers(C1, C0, args.align)
    aligned = scale * C1 @ rotation.T + translation
    Qaligned = rotation @ Q1
    raw_pos = np.linalg.norm(C1-C0, axis=1)
    raw_rot = rotation_errors(Q0, Q1)
    pos = np.linalg.norm(aligned-C0, axis=1)
    rot = rotation_errors(Q0, Qaligned)
    radius = float(np.sqrt(np.mean(np.sum((C0-C0.mean(0))**2, axis=1))))
    summary = {
        'matching': args.match, 'before_file': str(Path(args.before).resolve()), 'after_file': str(Path(args.after).resolve()),
        'matched_images': len(names), 'before_images': len(before), 'after_images': len(after),
        'only_before': sorted(before.keys()-after.keys()), 'only_after': sorted(after.keys()-before.keys()),
        'position_unit': 'input reconstruction units (meters only if reconstruction has metric scale)',
        'rotation_unit': 'degrees', 'reference_center_rms_radius': radius,
        'raw_position': stats(raw_pos), 'raw_rotation_deg': stats(raw_rot),
        'alignment': {'mode': args.align, 'after_to_before_scale': scale,
                      'rotation': rotation.tolist(), 'translation': translation.tolist()},
        'evaluated_position': stats(pos), 'evaluated_rotation_deg': stats(rot),
        'position_rmse_over_reference_radius': float(np.sqrt(np.mean(pos**2))/radius) if radius > 1e-12 else None,
        'largest_position_change': names[int(np.argmax(pos))],
        'largest_rotation_change': names[int(np.argmax(rot))],
        'note': 'Pose changes, not ground-truth accuracy. Alignment removes global frame changes and may hide global pose updates.'}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out/'per_image.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'raw_position_delta', 'raw_rotation_deg', 'evaluated_position_delta',
                         'evaluated_rotation_deg', 'dx', 'dy', 'dz',
                         'before_cx', 'before_cy', 'before_cz', 'after_cx', 'after_cy', 'after_cz',
                         'aligned_after_cx', 'aligned_after_cy', 'aligned_after_cz'])
        for i, name in enumerate(names):
            writer.writerow([name, raw_pos[i], raw_rot[i], pos[i], rot[i],
                             *(aligned[i]-C0[i]), *C0[i], *C1[i], *aligned[i]])
    (out/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    if not args.no_plots:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            print('matplotlib unavailable: CSV/JSON saved; install matplotlib to enable plots.')
        else:
            fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
            for ax, raw, evaluated, ylabel in zip(axes, [raw_pos, raw_rot], [pos, rot],
                                                ['Center displacement (input units)', 'Rotation change (degrees)']):
                ax.plot(raw, label='Raw', alpha=.7)
                if args.align != 'none':
                    ax.plot(evaluated, label='Aligned')
                ax.set_ylabel(ylabel); ax.grid(alpha=.25); ax.legend()
            ticks = np.unique(np.linspace(0, len(names)-1, min(12, len(names)), dtype=int))
            axes[-1].set_xticks(ticks, [names[i] for i in ticks], rotation=45, ha='right')
            axes[-1].set_xlabel('Image name (lexicographic order)')
            fig.tight_layout(); fig.savefig(out/'pose_changes.png', dpi=160); plt.close(fig)
            fig = plt.figure(figsize=(9, 8)); ax = fig.add_subplot(111, projection='3d')
            ax.scatter(*C0.T, label='Before', s=18)
            ax.scatter(*aligned.T, label='After ('+args.align+')', s=18)
            for a, b in zip(C0, aligned):
                ax.plot(*np.stack([a,b]).T, color='gray', alpha=.4, linewidth=.7)
            combined = np.concatenate([C0, aligned])
            center = (combined.min(0)+combined.max(0))/2
            half = max(float(np.ptp(combined, axis=0).max())/2, 1e-6)
            ax.set_xlim(center[0]-half, center[0]+half)
            ax.set_ylim(center[1]-half, center[1]+half)
            ax.set_zlim(center[2]-half, center[2]+half)
            ax.set_box_aspect((1,1,1)); ax.set_xlabel('X'); ax.set_ylabel('Y'); ax.set_zlabel('Z')
            ax.legend(); fig.tight_layout(); fig.savefig(out/'camera_centers.png', dpi=160); plt.close(fig)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print('Saved results to', out.resolve())


if __name__ == '__main__':
    main()
