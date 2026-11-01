"""Render the repository-local MuJoCo assembly scenes (no dynamics are run)."""
import os
os.environ.setdefault('MUJOCO_GL', 'egl')
from pathlib import Path
import subprocess
import mujoco
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT = os.environ.get('WRIST_CAM_FONT')
if not FONT:
    FONT = subprocess.check_output(
        ['fc-match', '-f', '%{file}', 'Noto Sans CJK SC'], text=True
    ).strip()
def font(size):
    return ImageFont.truetype(FONT, size)

def render(name):
    model = mujoco.MjModel.from_xml_path(str(ROOT / 'hardware/simulation' / (name + '.xml')))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [-.025, 0, .16 if name == 'exploded' else .04]
    cam.distance = .70 if name == 'exploded' else .46
    cam.azimuth = 45
    cam.elevation = -18
    with mujoco.Renderer(model, height=1000, width=1400) as renderer:
        renderer.update_scene(data, camera=cam)
        pixels = renderer.render()
    canvas = Image.new('RGB', (1400, 1200), '#f4f6f8')
    canvas.paste(Image.fromarray(pixels), (0, 100))
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 25), '腕部相机 / ' + ('装配爆炸图' if name == 'exploded' else '装配完成视图'), font=font(38), fill='#172c40')
    def callout(text, xy, target):
        box = draw.textbbox(xy, text, font=font(27))
        start = (box[2] + 14, (box[1] + box[3]) // 2) if xy[0] < target[0] else (xy[0] - 14, (box[1] + box[3]) // 2)
        draw.line([start, target], fill='#78c9e8', width=3)
        draw.ellipse((target[0]-5, target[1]-5, target[0]+5, target[1]+5), fill='#78c9e8')
        draw.text(xy, text, font=font(27), fill='white')
    if name == 'exploded':
        callout('① xArm 腕部', (930, 870), (779, 870))
        callout('② 一体打印支架', (910, 645), (768, 726))
        callout('③ G2 夹爪（整体取下 / 装回）', (900, 315), (801, 400))
        callout('④ SC3336 相机 + M2 螺钉', (65, 510), (646, 556))
        callout('⑤ Pico Mini：插入卡槽后点胶', (40, 795), (508, 740))
        callout('⑥ M3 夹紧螺栓 / 螺母', (920, 755), (814, 721))
        # Arrowheads show the bracket sliding toward the wrist and the board entering its rails.
        draw.line([(865, 737), (865, 835)], fill='#ffcb66', width=5)
        draw.polygon([(855, 820), (875, 820), (865, 840)], fill='#ffcb66')
        draw.line([(535, 760), (590, 730)], fill='#ffcb66', width=5)
        draw.polygon([(590, 730), (568, 733), (579, 748)], fill='#ffcb66')
    else:
        callout('夹爪装回原来的腕部法兰', (900, 385), (806, 525))
        callout('相机朝向夹爪工作区', (65, 510), (584, 594))
        callout('开发板粘在侧面卡槽中', (50, 790), (514, 688))
        callout('支架套环抱住腕部外侧', (900, 815), (797, 761))
    draw.text((45, 1125), 'MuJoCo 几何示意 · 紧固件与电子元件简化 · 排线和热熔胶未绘出', font=font(25), fill='#405568')
    canvas.save(ROOT / 'docs/assets/hardware' / (name + '.png'))

if __name__ == '__main__':
    for name in ('assembled', 'exploded'):
        render(name)
