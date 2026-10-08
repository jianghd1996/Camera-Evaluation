# Camera-Evaluation

比较 COLMAP `images.txt` 中相同图片的相机位姿。支持单组评估和直接编辑 main() 的批量测试。

```bash
pip install -r requirements.txt
python batch_evaluate.py
```

## 批量测试：直接编辑 main()

打开 `batch_evaluate.py`，修改 `main()` 中的 `cases` 和选项：

```python
cases = [
    ("apple_1", "/path/raw/sparse/0", "/path/result1/colmap_final"),
    ("apple_2", "/path/raw/images.txt", "/path/result2/images.txt"),
]
output_dir = "batch_results"
align = "se3"
match = "stem"
no_plots = False
```

每组三项分别为名称、before、after。路径支持 `images.txt` 文件或包含它的文件夹，也支持中文和 `~`；相对路径以脚本所在目录为基准。名称必须唯一且不能包含路径分隔符。

也可以在自己的 Python 脚本中调用：

```python
from batch_evaluate import evaluate_cases

evaluate_cases([
    ("apple", "/path/before/sparse/0", "/path/after/colmap_final"),
], output_dir="results", align="se3", match="stem", no_plots=True)
```

每个任务输出 `per_image.csv`、`summary.json`、`pose_changes.png`、`camera_centers.png`；总表为 `batch_results/batch_summary.csv`。CSV 仅用于输出，无需准备输入 CSV。失败任务记录错误并继续其他任务，存在失败时命令返回非零退出码。再次运行会覆盖成功任务对应的输出；以当前总表中的 status 判断结果，失败目录可能有旧结果。

单组命令行入口仍可用：

```bash
python evaluate_colmap_poses.py --before colmap_raw.txt --after colmap1.txt --align se3 --match stem --output-dir pose_evaluation
```

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
