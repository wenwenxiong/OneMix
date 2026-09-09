"""图片组合工具：物品检测（VLM + 本地连通域降级）、旋转、布局、合成。

独立于 AI 生图流程，纯本地图像处理 + 可选 VLM 辅助检测。
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageChops

from onemix.services import dashscope_svc
from onemix.services import prompt_templates as prompts

logger = logging.getLogger(__name__)

# 布局候选模式
LAYOUT_MODES = ("auto", "horizontal", "vertical", "2h1v", "1h2v", "grid")
# 允许的旋转角度
ALLOWED_ANGLES = (90, 180, 270)
# 白底抠图阈值（复用 dashscope_svc 的默认值）
WHITE_THRESHOLD = 238
# 布局留白比例（相对最大物品尺寸）
PADDING_RATIO = 0.12
# 物品间距比例（相对最大物品尺寸）
GAP_RATIO = 0.08


def detect_objects_via_vlm(image_path: Path, api_key: str) -> list[dict[str, Any]]:
    """调用 qwen-vl-plus 识别图中每个独立物品，返回 bbox 列表。

    返回格式：[{"bbox": [x1, y1, x2, y2], "label": "..."}, ...]
    坐标基于原图像素，x1<y1<x2<y2。
    """
    raw = dashscope_svc.multimodal_text(
        api_key=api_key,
        image_paths=[image_path],
        user_prompt=prompts.OBJECT_DETECT_BBOX_PROMPT,
    )
    return _parse_bbox_json(raw)


def _parse_bbox_json(raw: str) -> list[dict[str, Any]]:
    """解析 VLM 返回的 bbox JSON，容错处理。"""
    txt = (raw or "").strip()
    if not txt:
        raise RuntimeError("VLM 未返回内容")

    # 尝试直接解析
    try:
        data = json.loads(txt)
        return _normalize_bbox_list(data)
    except json.JSONDecodeError:
        pass

    # markdown 代码块
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*\])\s*```", txt, flags=re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            return _normalize_bbox_list(data)
        except json.JSONDecodeError:
            pass

    # 回退：首个中括号片段
    s = txt.find("[")
    e = txt.rfind("]")
    if s >= 0 and e > s:
        try:
            data = json.loads(txt[s : e + 1])
            return _normalize_bbox_list(data)
        except json.JSONDecodeError:
            pass

    raise RuntimeError(f"无法解析 VLM 返回的 bbox JSON: {txt[:200]}")


def _normalize_bbox_list(data: Any) -> list[dict[str, Any]]:
    """将解析后的数据归一化为 [{bbox, label}, ...] 列表。"""
    if not isinstance(data, list):
        raise RuntimeError("VLM 返回非数组")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or item.get("box") or item.get("rectangle")
        if not bbox or len(bbox) != 4:
            continue
        try:
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
        except (TypeError, ValueError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        out.append({
            "bbox": [x1, y1, x2, y2],
            "label": str(item.get("label", f"物品{i + 1}")),
        })
    if not out:
        raise RuntimeError("VLM 未返回有效 bbox")
    return out


def detect_objects_local(image_path: Path, threshold: int = WHITE_THRESHOLD) -> list[dict[str, Any]]:
    """本地连通域分割：白底阈值抠图后找连通域，返回 bbox 列表。

    降级方案，无需 API Key。适用于白底图、物品间有清晰间隙的场景。
    """
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    # 二值化：非白像素为 1（前景），白像素为 0（背景）
    mask = Image.new("L", (w, h), 0)
    px = im.load()
    mask_px = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if not (r >= threshold and g >= threshold and b >= threshold):
                mask_px[x, y] = 1

    # 连通域标记（4 邻接，BFS）
    visited = Image.new("L", (w, h), 0)
    vis_px = visited.load()
    bboxes: list[tuple[int, int, int, int, int]] = []  # x1,y1,x2,y2,area
    for y in range(h):
        for x in range(w):
            if mask_px[x, y] == 1 and vis_px[x, y] == 0:
                # BFS 找连通域
                stack = [(x, y)]
                min_x, min_y, max_x, max_y = x, y, x, y
                area = 0
                while stack:
                    cx, cy = stack.pop()
                    if cx < 0 or cx >= w or cy < 0 or cy >= h:
                        continue
                    if vis_px[cx, cy] == 1 or mask_px[cx, cy] == 0:
                        continue
                    vis_px[cx, cy] = 1
                    area += 1
                    min_x = min(min_x, cx)
                    min_y = min(min_y, cy)
                    max_x = max(max_x, cx)
                    max_y = max(max_y, cy)
                    stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
                # 过滤过小区域（噪声）
                if area >= max(100, (w * h) * 0.005):
                    bboxes.append((min_x, min_y, max_x + 1, max_y + 1, area))

    if not bboxes:
        raise RuntimeError("本地连通域未检测到物品")

    # 按面积降序排序，保留前 10 个（避免噪声）
    bboxes.sort(key=lambda b: b[4], reverse=True)
    bboxes = bboxes[:10]

    out: list[dict[str, Any]] = []
    for i, (x1, y1, x2, y2, _area) in enumerate(bboxes):
        out.append({
            "bbox": [x1, y1, x2, y2],
            "label": f"物品{i + 1}",
        })
    return out


def crop_to_rgba_objects(image_path: Path, bboxes: list[dict[str, Any]]) -> list[Image.Image]:
    """按 bbox 裁剪原图，并对每个子图抠白底得到 RGBA 主体。"""
    im = Image.open(image_path).convert("RGB")
    out: list[Image.Image] = []
    for item in bboxes:
        x1, y1, x2, y2 = item["bbox"]
        # 边界保护
        x1 = max(0, min(x1, im.width - 1))
        y1 = max(0, min(y1, im.height - 1))
        x2 = max(x1 + 1, min(x2, im.width))
        y2 = max(y1 + 1, min(y2, im.height))
        crop = im.crop((x1, y1, x2, y2))
        rgba = _white_to_transparent(crop)
        # 裁掉透明边距，只保留主体
        rgba = _autocrop_transparent(rgba)
        out.append(rgba)
    return out


def _white_to_transparent(im: Image.Image, threshold: int = WHITE_THRESHOLD) -> Image.Image:
    """白底转透明（复用 dashscope_svc.rgba_base_from_white_product_image 逻辑）。"""
    rgb = im.convert("RGB")
    rgba = Image.new("RGBA", rgb.size)
    px = rgb.load()
    pr = rgba.load()
    w, h = rgb.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                pr[x, y] = (255, 255, 255, 0)
            else:
                pr[x, y] = (r, g, b, 255)
    return rgba


def _autocrop_transparent(im: Image.Image) -> Image.Image:
    """裁掉 RGBA 图片四周的透明像素，只保留主体区域。"""
    if im.mode != "RGBA":
        return im
    # 用 alpha 通道找 bounding box
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        return im.crop(bbox)
    return im


def rotate_object(rgba: Image.Image, angle: int) -> Image.Image:
    """旋转 RGBA 物品，angle ∈ {90, 180, 270}，expand=True 保持完整。"""
    if angle == 0:
        return rgba
    if angle not in ALLOWED_ANGLES:
        raise ValueError(f"angle 必须是 {ALLOWED_ANGLES} 之一")
    return rgba.rotate(angle, expand=True)


def layout_objects(
    rgba_objects: list[Image.Image],
    layout_mode: str = "auto",
    rotations: Optional[list[int]] = None,
    seed: Optional[int] = None,
    target_ratio: str = "1:1",
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """对多个 RGBA 物品应用旋转 + 布局，返回合成画布与每个物品的位置信息。

    Args:
        rgba_objects: 已抠白底的 RGBA 物品列表
        layout_mode: auto/horizontal/vertical/2h1v/1h2v/grid
        rotations: 每个物品的旋转角度列表（与 rgba_objects 等长），None 表示全 0
        seed: 随机种子，用于复现布局
        target_ratio: 目标画布宽高比（1:1 / 3:4 / 4:3）

    Returns:
        (canvas_rgb, positions) 其中 positions = [{"x", "y", "w", "h", "rotation"}, ...]
    """
    if not rgba_objects:
        raise RuntimeError("无物品可布局")

    rng = random.Random(seed)
    n = len(rgba_objects)

    # 应用旋转
    if rotations is None:
        rotations = [0] * n
    if len(rotations) != n:
        raise ValueError("rotations 长度与 rgba_objects 不一致")

    rotated: list[Image.Image] = []
    for img, ang in zip(rgba_objects, rotations):
        rotated.append(rotate_object(img, ang) if ang else img)

    # 枚举候选布局
    candidates = _enumerate_layouts(n, rotated, target_ratio)

    # 按 layout_mode 筛选
    if layout_mode == "auto":
        # 打分选最优
        scored = [(_score_layout(c, rotated, target_ratio), c) for c in candidates]
        scored.sort(key=lambda s: -s[0])
        chosen = scored[0][1]
    elif layout_mode == "horizontal":
        chosen = next((c for c in candidates if c["type"] == "horizontal"), candidates[0])
    elif layout_mode == "vertical":
        chosen = next((c for c in candidates if c["type"] == "vertical"), candidates[0])
    elif layout_mode == "2h1v":
        chosen = next((c for c in candidates if c["type"] == "2h1v"), candidates[0])
    elif layout_mode == "1h2v":
        chosen = next((c for c in candidates if c["type"] == "1h2v"), candidates[0])
    elif layout_mode == "grid":
        chosen = next((c for c in candidates if c["type"] == "grid"), candidates[0])
    else:
        chosen = candidates[0]

    # auto 模式下随机打乱候选顺序以增加多样性
    if layout_mode == "auto" and seed is not None:
        rng.shuffle(candidates)
        scored = [(_score_layout(c, rotated, target_ratio), c) for c in candidates]
        scored.sort(key=lambda s: -s[0])
        chosen = scored[0][1]

    return _render_layout(chosen, rotated, rotations)


def _enumerate_layouts(n: int, objects: list[Image.Image], target_ratio: str) -> list[dict[str, Any]]:
    """枚举所有可行布局方案。"""
    layouts: list[dict[str, Any]] = []

    # 全横排
    layouts.append({"type": "horizontal", "rows": [[i for i in range(n)]]})
    # 全竖排
    layouts.append({"type": "vertical", "rows": [[i] for i in range(n)]})

    if n == 3:
        # 2横1竖：上 2 下 1
        layouts.append({"type": "2h1v", "rows": [[0, 1], [2]]})
        layouts.append({"type": "2h1v", "rows": [[0, 2], [1]]})
        layouts.append({"type": "2h1v", "rows": [[1, 2], [0]]})
        # 1横2竖：上 1 下 2
        layouts.append({"type": "1h2v", "rows": [[0], [1, 2]]})
        layouts.append({"type": "1h2v", "rows": [[0], [1, 2]]})
        layouts.append({"type": "1h2v", "rows": [[1], [0, 2]]})

    if n >= 4:
        # 网格
        cols = int(n**0.5) + (1 if n % int(n**0.5) else 0)
        rows: list[list[int]] = []
        for i in range(0, n, cols):
            rows.append(list(range(i, min(i + cols, n))))
        layouts.append({"type": "grid", "rows": rows})

    return layouts


def _score_layout(layout: dict[str, Any], objects: list[Image.Image], target_ratio: str) -> float:
    """对布局方案打分，越高越美观。"""
    rows = layout["rows"]
    # 计算每行最大高度、总宽度
    row_heights: list[int] = []
    row_widths: list[int] = []
    for row in rows:
        if not row:
            continue
        max_h = max(objects[i].height for i in row)
        total_w = sum(objects[i].width for i in row)
        row_heights.append(max_h)
        row_widths.append(total_w)

    if not row_heights or not row_widths:
        return 0.0

    max_row_w = max(row_widths)
    total_h = sum(row_heights)

    # 目标宽高比
    ratio_map = {"1:1": 1.0, "3:4": 0.75, "4:3": 1.33}
    target = ratio_map.get(target_ratio, 1.0)
    actual = max_row_w / total_h if total_h > 0 else 1.0

    # 宽高比接近度（0~1）
    ratio_score = 1.0 - min(1.0, abs(actual - target) / max(target, actual))

    # 行宽均匀度（方差小更好）
    if len(row_widths) > 1:
        avg_w = sum(row_widths) / len(row_widths)
        variance = sum((w - avg_w) ** 2 for w in row_widths) / len(row_widths)
        uniformity = 1.0 - min(1.0, (variance ** 0.5) / max(avg_w, 1))
    else:
        uniformity = 1.0

    # 物品数量分布均衡（每行物品数接近）
    row_counts = [len(r) for r in rows]
    if len(row_counts) > 1:
        avg_c = sum(row_counts) / len(row_counts)
        count_var = sum((c - avg_c) ** 2 for c in row_counts) / len(row_counts)
        balance = 1.0 - min(1.0, count_var / max(avg_c, 1))
    else:
        balance = 1.0

    return ratio_score * 0.5 + uniformity * 0.3 + balance * 0.2


def _render_layout(
    layout: dict[str, Any], objects: list[Image.Image], rotations: list[int]
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """将布局方案渲染到白底画布，返回画布与位置信息。"""
    rows = layout["rows"]
    n = len(objects)

    # 计算最大物品尺寸，用于确定间距
    max_w = max(o.width for o in objects)
    max_h = max(o.height for o in objects)
    gap = int(max(max_w, max_h) * GAP_RATIO)
    padding = int(max(max_w, max_h) * PADDING_RATIO)

    # 每行缩放：行内物品等高，行间按最大行高
    # 先计算每行的目标高度（取行内最大高度）
    row_target_heights: list[int] = []
    for row in rows:
        if row:
            row_target_heights.append(max(objects[i].height for i in row))

    # 缩放每行内物品到行高
    scaled_objects: dict[int, Image.Image] = {}
    for row, row_h in zip(rows, row_target_heights):
        for i in row:
            obj = objects[i]
            if obj.height != row_h:
                scale = row_h / obj.height
                new_w = max(1, int(obj.width * scale))
                scaled_objects[i] = obj.resize((new_w, row_h), Image.Resampling.LANCZOS)
            else:
                scaled_objects[i] = obj

    # 计算每行宽度
    row_widths: list[int] = []
    for row in rows:
        w = sum(scaled_objects[i].width for i in row) + gap * (len(row) - 1)
        row_widths.append(w)

    canvas_w = max(row_widths) + padding * 2
    canvas_h = sum(row_target_heights) + gap * (len(rows) - 1) + padding * 2

    # 创建白底画布
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    positions: list[dict[str, Any]] = [{} for _ in range(n)]

    y_cursor = padding
    for row, row_h, row_w in zip(rows, row_target_heights, row_widths):
        # 行水平居中
        x_cursor = (canvas_w - row_w) // 2
        for i in row:
            obj = scaled_objects[i]
            # 物品在行内垂直居中
            y = y_cursor + (row_h - obj.height) // 2
            # paste 到画布
            canvas.paste(obj, (x_cursor, y), obj if obj.mode == "RGBA" else None)
            positions[i] = {
                "x": x_cursor,
                "y": y,
                "w": obj.width,
                "h": obj.height,
                "rotation": rotations[i] if i < len(rotations) else 0,
            }
            x_cursor += obj.width + gap
        y_cursor += row_h + gap

    return canvas, positions


def compose_image(
    image_path: Path,
    bboxes: list[dict[str, Any]],
    rotations: list[int],
    layout_mode: str = "auto",
    seed: Optional[int] = None,
    target_ratio: str = "1:1",
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """完整组合流程：裁剪 → 抠白底 → 旋转 → 布局 → 合成。

    Returns:
        (final_rgb_image, positions)
    """
    rgba_objects = crop_to_rgba_objects(image_path, bboxes)
    canvas, positions = layout_objects(
        rgba_objects,
        layout_mode=layout_mode,
        rotations=rotations,
        seed=seed,
        target_ratio=target_ratio,
    )
    return canvas, positions


def save_image(im: Image.Image, dest: Path, fmt: str = "JPG", quality: int = 92) -> None:
    """保存图片到目标路径。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt.upper() == "JPG":
        im.convert("RGB").save(dest, "JPEG", quality=quality, optimize=True)
    else:
        im.save(dest, "PNG", optimize=True)
