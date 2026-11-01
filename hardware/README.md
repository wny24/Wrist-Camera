# Wrist Camera 硬件文件

组装步骤见 [中文硬件组装指南](../docs/hardware-assembly-zh.md)。本目录包含打印件、可编辑模型，以及生成装配图所需的全部场景和网格。无需访问仓库以外的 CAD 目录。

## 文件

| 文件 | 用途 | 单位 |
| --- | --- | --- |
| [cad/recessed_camera_plate.stl](cad/recessed_camera_plate.stl) | 打印一体腕部支架，包含相机安装座和开发板卡槽 | mm |
| [cad/recessed_camera_plate.step](cad/recessed_camera_plate.step) | 修改支架的实体几何 | mm |
| [simulation/assembled.xml](simulation/assembled.xml) | 装配完成状态的 MuJoCo 场景 | m |
| [simulation/exploded.xml](simulation/exploded.xml) | 拉开部件、说明安装关系的 MuJoCo 场景 | m |
| [simulation/meshes/](simulation/meshes/) | 腕部、夹爪和相机 PCB 的显示网格，不用于打印 | m |
| [simulation/sources.json](simulation/sources.json) | 显示网格来源、上游版本和 SHA-256 | — |
| [tools/render_assembly.py](tools/render_assembly.py) | 重新生成带中文标注的装配图 | — |

STL 包围盒为 **155.15 × 91.20 × 66.63 mm**，包含 17,428 个三角面。校验值：

```text
3066b0534c5af87d29cd663e8b8c51f703b38d5f54dba6f3886f1b89e5cc6539
```

STEP 为可编辑实体，不包含参数化建模历史。MuJoCo 场景通过相对路径直接引用同一个打印 STL，并用 `scale=".001 .001 .001"` 换算到米；修改 STL 后重新渲染即可更新支架外形。

## 查看与重新生成装配图

在仓库根目录为硬件工具创建独立环境：

```bash
python3 -m venv hardware/.venv
hardware/.venv/bin/python -m pip install -r hardware/requirements-render.txt
```

在有图形桌面的环境中打开任一场景，可旋转、缩放查看：

```bash
hardware/.venv/bin/python -m mujoco.viewer --mjcf=hardware/simulation/exploded.xml
hardware/.venv/bin/python -m mujoco.viewer --mjcf=hardware/simulation/assembled.xml
```

Linux 下渲染文档插图：

```bash
MUJOCO_GL=egl hardware/.venv/bin/python hardware/tools/render_assembly.py
```

需要可用的 EGL / OpenGL 运行环境。脚本通过 `fc-match` 查找 Noto Sans CJK 中文字体；也可用 `WRIST_CAM_FONT` 指定本机字体文件。没有 EGL 时，可在安装 OSMesa 的环境中设置 `MUJOCO_GL=osmesa`。

输出为 [装配图](../docs/assets/hardware/assembled.png)和[爆炸图](../docs/assets/hardware/exploded.png)。图中标注位置对应脚本的固定视角；修改视角后应同步调整标注。

## 模型说明

- 支架采用打印 STL 原始几何；相机、开发板及紧固件采用简化显示模型。开发板实际用热熔胶点粘在卡槽中，胶点与排线没有建模。
- 爆炸图通过平移部件展示安装关系，不是机器人控制轨迹。场景用于几何展示，没有运行装配动力学或验证承载能力。
- 紧固件模型只表示位置与轴向，采购长度以实物为准。装配完成视图不代表已经通过碰撞验收；安装时应确认夹爪与腕部原安装面能正常贴合。

## 第三方模型来源

腕部与夹爪的 8 个显示网格已逐一与 [UFACTORY xarm_ros](https://github.com/xArm-Developer/xarm_ros) 上游文件核对，内容一致。具体文件、固定提交版本和校验值见 [sources.json](simulation/sources.json)，保留的上游许可证见 [UFACTORY BSD 3-Clause](licenses/UFACTORY-BSD-3-Clause.txt)。该许可证对应这些第三方网格，不替代本项目其他文件的许可声明。
