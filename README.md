# Camera-Evaluation

比较 COLMAP `images.txt` 中相同图片的相机位姿。支持单组评估和 CSV 清单批量测试。

```bash
pip install -r requirements.txt

# 仓库中两组数据分别与 raw 对比
python batch_evaluate.py --manifest comparisons.csv --align se3 --match stem

# 单组对比
python evaluate_colmap_poses.py --before colmap_raw.txt --after colmap1.txt --align se3 --match stem --output-dir pose_evaluation
```

## 批量测试

编辑 `comparisons.csv`，每行一个对比任务：

```csv
case,before,after
apple_1,/absolute/path/raw/images.txt,/absolute/path/refined1/images.txt
apple_2,/absolute/path/raw/images.txt,/absolute/path/refined2/images.txt
```

路径可为绝对路径，或相对于 CSV 所在目录的路径；包含逗号的路径需要 CSV 引号。case 必须唯一，不能包含路径分隔符。中文路径支持。

```bash
python batch_evaluate.py --manifest comparisons.csv --output-dir batch_results --align se3 --match stem
# 只输出数值，批量更快
python batch_evaluate.py --manifest comparisons.csv --no-plots
```

每个任务输出 `per_image.csv`、`summary.json`、`pose_changes.png`、`camera_centers.png`；总表为 `batch_results/batch_summary.csv`。失败任务记录错误并继续其他任务，存在失败时命令返回非零退出码。再次运行会覆盖成功任务对应的输出；以当前总表中的 status 判断结果，失败目录可能有旧结果。

## 指标和选项

- COLMAP 的 quaternion 为 WXYZ，变换是 world-to-camera；世界坐标中的相机中心使用 `C = -R.T @ t`。
- 位置差为对应相机中心的欧氏距离；旋转差为相对旋转角度（度）。输出 mean、median、RMSE、P95、min、max。
- `--match exact`：完整图片名匹配，单组脚本默认。
- `--match stem`：忽略扩展名，例如 `000.png` 对应 `000.jpg`，批量默认。仅在它们确实是同一张图片时使用；重名会报错。
- `--align none`：直接比较，单组默认，适用于同坐标系的优化前后。
- `--align se3`：根据匹配相机中心拟合整体旋转和平移，将 after 对齐到 before，再比较；批量默认。
- `--align sim3`：额外拟合尺度。尺度为 after 到 before 的转换比例。
- SE3/Sim3 需要至少 3 个匹配相机，且中心不能共线；朝向使用同一个对齐旋转变换。
- 对齐时也保留未对齐的 raw 指标。位置单位是 before 重建单位，未必是米。指标衡量改动，不能证明优化后精度更高。
- 每个任务按其共有图片独立匹配、拟合，匹配帧不同会影响统计与对齐结果。图中按文件名字符串排序，不保证时间顺序。

仓库示例中 raw/colmap1/colmap2 分别有 164/42/40 个位姿。SE3 对齐后，colmap1 的位置 RMSE 约 0.00399181、旋转均值约 0.484715 度；colmap2 的位置 RMSE 约 8.21e-8、旋转均值约 6.26e-6 度。colmap1 多出 `080` 和 `livephoto_020` 两帧，因此这里不是完全相同的采样集合。
