"""图片组合工具：物品检测（VLM + 本地连通域降级）、旋转、布局、合成。

独立于 AI 生图流程，纯本地图像处理 + 可选 VLM 辅助检测。
"""

from __future__ import annotations

import json
import logging
import random
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageChops

from onemix.services import dashscope_svc
from onemix.services import prompt_templates as prompts

logger = logging.getLogger(__name__)

# 布局候选模式
LAYOUT_MODES = ("auto", "horizontal", "vertical", "2h1v", "1h2v", "grid")
# 允许的旋转角度（0 表示不旋转，单独处理）
ALLOWED_ANGLES = (90, 180, 270)
# 白底抠图阈值（复用 dashscope_svc 的默认值）
WHITE_THRESHOLD = 238
# 布局留白比例（相对统一目标高度）
PADDING_RATIO = 0.12
# 物品间距比例（相对统一目标高度）
GAP_RATIO = 0.08
# 单物品批量模式的比例变体
SINGLE_OBJECT_RATIO_VARIANTS = ("1:1", "3:4", "4:3")


def detect_objects_via_vlm(image_path: Path, api_key: str) -> list[dict[str, Any]]:
    """调用 qwen-vl-plus 识别图中每个独立物品，返回 bbox 列表。

    分两步：
    1) 第一步：检测所有物品的 bbox + label（不判断角度）
    2) 后处理：对大 bbox（面积 > 原图 40%）做白线切割 + 宽度突变切割，
       处理 VLM 把相邻/叠放物品合并的情况
    3) 第二步：裁剪每个物品，单独调 VLM 判断旋转角度（单物品判断更准）

    返回格式：[{"bbox": [x1, y1, x2, y2], "label": "...", "suggested_rotation": 0}, ...]
    坐标基于原图像素，x1<y1<x2<y2。
    """
    # 第一步：检测 bbox
    raw = dashscope_svc.multimodal_text(
        api_key=api_key,
        image_paths=[image_path],
        user_prompt=prompts.OBJECT_DETECT_BBOX_PROMPT,
    )
    objects = _parse_bbox_json(raw)

    # 后处理：对大 bbox（面积 > 原图 40%）做白线切割 + 宽度突变切割
    im = Image.open(image_path).convert("RGB")
    img_area = im.width * im.height
    split_objects: list[dict[str, Any]] = []
    for obj in objects:
        x1, y1, x2, y2 = obj["bbox"]
        bbox_area = (x2 - x1) * (y2 - y1)
        if bbox_area > img_area * 0.4:
            # 大 bbox，先尝试白线切割（并排相邻场景）
            sub_bboxes = _split_bbox_by_white_lines(im, (x1, y1, x2, y2))
            if len(sub_bboxes) == 1:
                # 白线切割失败，尝试宽度突变切割（叠放场景）
                sub_bboxes = _split_bbox_by_width_change(im, (x1, y1, x2, y2))
            if len(sub_bboxes) > 1:
                # 切割成功，替换为多个子 bbox
                for j, sub in enumerate(sub_bboxes):
                    split_objects.append({
                        "bbox": list(sub),
                        "label": f"{obj['label']}{j + 1}",
                        "suggested_rotation": 0,
                    })
            else:
                split_objects.append(obj)
        else:
            split_objects.append(obj)

    objects = split_objects if split_objects else objects

    # 第二步：裁剪每个物品，单独调 VLM 判断角度
    rgba_objects = crop_to_rgba_objects(image_path, objects)
    for i, rgba in enumerate(rgba_objects):
        try:
            objects[i]["suggested_rotation"] = detect_rotation_via_vlm(rgba, api_key)
        except Exception as e:
            logger.warning("物品 %d 角度判断失败，默认 0: %s", i, e)
            objects[i]["suggested_rotation"] = 0
    return objects


def detect_rotation_via_vlm(rgba: Image.Image, api_key: str) -> int:
    """对单个裁剪出的 RGBA 物品调 VLM 判断旋转角度。

    保存到临时 PNG 文件，调 qwen-vl-plus 返回 {"rotation": N}。
    失败时返回 0。
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="onemix_rot_")
    tmp_file = Path(tmp_path)
    try:
        import os as _os

        _os.close(tmp_fd)
        rgba.save(tmp_file, "PNG")
        raw = dashscope_svc.multimodal_text(
            api_key=api_key,
            image_paths=[tmp_file],
            user_prompt=prompts.OBJECT_ROTATION_PROMPT,
        )
        return _parse_rotation_json(raw)
    finally:
        try:
            tmp_file.unlink(missing_ok=True)
        except Exception:
            pass


def _parse_rotation_json(raw: str) -> int:
    """解析 VLM 返回的 {"rotation": N}，容错处理。"""
    txt = (raw or "").strip()
    if not txt:
        return 0

    # 尝试直接解析
    try:
        data = json.loads(txt)
        if isinstance(data, dict):
            rot = int(data.get("rotation", 0))
            return rot if rot in ALLOWED_ANGLES or rot == 0 else 0
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # markdown 代码块
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", txt, flags=re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                rot = int(data.get("rotation", 0))
                return rot if rot in ALLOWED_ANGLES or rot == 0 else 0
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # 回退：首个大括号片段
    s = txt.find("{")
    e = txt.rfind("}")
    if s >= 0 and e > s:
        try:
            data = json.loads(txt[s : e + 1])
            if isinstance(data, dict):
                rot = int(data.get("rotation", 0))
                return rot if rot in ALLOWED_ANGLES or rot == 0 else 0
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # 最后回退：正则提取 rotation 数字
    m = re.search(r'"rotation"\s*:\s*(\d+)', txt)
    if m:
        try:
            rot = int(m.group(1))
            return rot if rot in ALLOWED_ANGLES or rot == 0 else 0
        except ValueError:
            pass

    logger.warning("无法解析旋转角度 JSON，默认 0: %s", txt[:200])
    return 0


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
    """将解析后的数据归一化为 [{bbox, label, suggested_rotation}, ...] 列表。

    注意：第一步 VLM 不再返回 suggested_rotation，这里统一初始化为 0，
    由 detect_objects_via_vlm 第二步单独调 VLM 填充。
    """
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
            "suggested_rotation": 0,
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

    # 对每个连通域 bbox 做白线扫描切割 + 宽度突变切割（处理相邻/叠放物品被合并的情况）
    final_bboxes: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2, _area in bboxes:
        # 先尝试白线切割（并排相邻场景）
        sub_bboxes = _split_bbox_by_white_lines(im, (x1, y1, x2, y2))
        if len(sub_bboxes) == 1:
            # 白线切割失败，尝试宽度突变切割（叠放场景）
            sub_bboxes = _split_bbox_by_width_change(im, (x1, y1, x2, y2))
        final_bboxes.extend(sub_bboxes)

    out: list[dict[str, Any]] = []
    for i, (x1, y1, x2, y2) in enumerate(final_bboxes):
        out.append({
            "bbox": [x1, y1, x2, y2],
            "label": f"物品{i + 1}",
            "suggested_rotation": 0,
        })
    return out


def _find_white_runs(is_white: list[bool], min_thickness: int) -> list[tuple[int, int]]:
    """找出连续白线段的起止位置（宽度 >= min_thickness）。

    Args:
        is_white: 每个位置是否为白色的布尔列表
        min_thickness: 白线最小宽度（像素）

    Returns:
        [(start, end), ...] 每个白线段的起止索引（end 为 exclusive）
    """
    runs: list[tuple[int, int]] = []
    i = 0
    n = len(is_white)
    while i < n:
        if is_white[i]:
            start = i
            while i < n and is_white[i]:
                i += 1
            end = i
            if end - start >= min_thickness:
                runs.append((start, end))
        else:
            i += 1
    return runs


def _split_bbox_by_white_lines(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    threshold: int = WHITE_THRESHOLD,
    min_white_thickness: int = 2,
) -> list[tuple[int, int, int, int]]:
    """检查 bbox 内部是否有全白行/列（宽度 >= min_white_thickness），
    如果有则在白线处切割成多个子 bbox。

    用于处理 VLM/连通域把相邻物品合并成一个大 bbox 的情况。
    优先按垂直白线切割（左右分割），再按水平白线切割（上下分割）。

    Args:
        image: 原图（RGB）
        bbox: (x1, y1, x2, y2)
        threshold: 白底阈值
        min_white_thickness: 白线最小宽度（像素）

    Returns:
        切割后的子 bbox 列表。如果无需切割，返回原 bbox 单元素列表。
    """
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w <= 5 or h <= 5:
        return [bbox]

    crop = image.crop((x1, y1, x2, y2)).convert("RGB")
    px = crop.load()

    # 扫描全白列（垂直白线）：列上所有像素都是白色
    is_white_col = [all(px[i, j][0] >= threshold and px[i, j][1] >= threshold and px[i, j][2] >= threshold for j in range(h)) for i in range(w)]
    white_col_runs = _find_white_runs(is_white_col, min_white_thickness)

    # 优先按垂直白线切割（左右分割）
    if white_col_runs:
        sub_bboxes: list[tuple[int, int, int, int]] = []
        prev_x = x1
        for run_start, run_end in white_col_runs:
            sub_x2 = x1 + run_start
            if sub_x2 > prev_x:
                sub_bboxes.append((prev_x, y1, sub_x2, y2))
            prev_x = x1 + run_end
        if x2 > prev_x:
            sub_bboxes.append((prev_x, y1, x2, y2))
        # 过滤过小的子 bbox
        valid = [b for b in sub_bboxes if (b[2] - b[0]) > 5 and (b[3] - b[1]) > 5]
        if len(valid) > 1:
            return valid
        # 切割后只剩 1 个有效区域，等于没切
        return [bbox]

    # 再按水平白线切割（上下分割）
    is_white_row = [all(px[i, j][0] >= threshold and px[i, j][1] >= threshold and px[i, j][2] >= threshold for i in range(w)) for j in range(h)]
    white_row_runs = _find_white_runs(is_white_row, min_white_thickness)

    if white_row_runs:
        sub_bboxes = []
        prev_y = y1
        for run_start, run_end in white_row_runs:
            sub_y2 = y1 + run_start
            if sub_y2 > prev_y:
                sub_bboxes.append((x1, prev_y, x2, sub_y2))
            prev_y = y1 + run_end
        if y2 > prev_y:
            sub_bboxes.append((x1, prev_y, x2, y2))
        valid = [b for b in sub_bboxes if (b[2] - b[0]) > 5 and (b[3] - b[1]) > 5]
        if len(valid) > 1:
            return valid
        return [bbox]

    # 无白线，返回原 bbox
    return [bbox]


def _split_bbox_by_width_change(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    threshold: int = WHITE_THRESHOLD,
    min_width_ratio: float = 0.3,
    min_segment_size: int = 20,
) -> list[tuple[int, int, int, int]]:
    """扫描 bbox 内前景的行/列宽度，在宽度突变处切割。

    用于叠放物品外轮廓有阶梯状变化的情况（白线切割无法处理的场景）。
    原理：叠放物品在叠放处的前景宽度会突变（如阶梯状边缘、L 形外轮廓）。

    算法：
    1. 裁剪 bbox 区域，生成前景掩码（非白像素）
    2. 行扫描：计算每行前景的左右边界和宽度
    3. 找宽度突变点（相邻行宽度差 > 最大宽度 * min_width_ratio）
    4. 在突变点切割成上下两个子 bbox
    5. 行方向无突变时，尝试列方向切割

    Args:
        image: 原图（RGB）
        bbox: (x1, y1, x2, y2)
        threshold: 白底阈值
        min_width_ratio: 宽度突变阈值（相对于最大宽度）
        min_segment_size: 切割后每段最小尺寸（像素）

    Returns:
        切割后的子 bbox 列表。如果无需切割，返回原 bbox 单元素列表。
    """
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w <= min_segment_size or h <= min_segment_size:
        return [bbox]

    crop = np.array(image.crop((x1, y1, x2, y2)).convert("RGB"))
    # 前景掩码：非白像素为 True
    fg = ~(
        (crop[:, :, 0] >= threshold)
        & (crop[:, :, 1] >= threshold)
        & (crop[:, :, 2] >= threshold)
    )

    # 行扫描：每行前景的左右边界和宽度
    row_has_fg = fg.any(axis=1)
    if not row_has_fg.any():
        return [bbox]

    # 每行前景的左右边界
    row_left = np.full(h, w, dtype=int)
    row_right = np.full(h, 0, dtype=int)
    for i in range(h):
        fg_cols = np.where(fg[i])[0]
        if len(fg_cols) > 0:
            row_left[i] = fg_cols[0]
            row_right[i] = fg_cols[-1]

    row_width = np.where(row_has_fg, row_right - row_left + 1, 0)
    max_width = int(row_width.max())
    if max_width < min_segment_size:
        return [bbox]

    # 找宽度突变点：相邻行宽度差 > max_width * min_width_ratio
    width_diff = np.abs(np.diff(row_width.astype(float)))
    split_threshold = max_width * min_width_ratio
    split_rows = np.where(width_diff > split_threshold)[0]

    if len(split_rows) > 0:
        # 在第一个突变处切割
        split_y = int(split_rows[0]) + 1  # +1 因为 diff 偏移
        if split_y < min_segment_size or split_y > h - min_segment_size:
            # 切割点太靠边，无效
            pass
        else:
            sub_bboxes = [
                (x1, y1, x2, y1 + split_y),
                (x1, y1 + split_y, x2, y2),
            ]
            valid = [
                b for b in sub_bboxes
                if (b[2] - b[0]) > min_segment_size and (b[3] - b[1]) > min_segment_size
            ]
            if len(valid) > 1:
                return valid

    # 行方向无有效突变，尝试列方向切割
    col_has_fg = fg.any(axis=0)
    if not col_has_fg.any():
        return [bbox]

    col_top = np.full(w, h, dtype=int)
    col_bottom = np.full(w, 0, dtype=int)
    for j in range(w):
        fg_rows = np.where(fg[:, j])[0]
        if len(fg_rows) > 0:
            col_top[j] = fg_rows[0]
            col_bottom[j] = fg_rows[-1]

    col_height = np.where(col_has_fg, col_bottom - col_top + 1, 0)
    max_height = int(col_height.max())
    if max_height < min_segment_size:
        return [bbox]

    height_diff = np.abs(np.diff(col_height.astype(float)))
    split_threshold_col = max_height * min_width_ratio
    split_cols = np.where(height_diff > split_threshold_col)[0]

    if len(split_cols) > 0:
        split_x = int(split_cols[0]) + 1
        if split_x < min_segment_size or split_x > w - min_segment_size:
            return [bbox]
        sub_bboxes = [
            (x1, y1, x1 + split_x, y2),
            (x1 + split_x, y1, x2, y2),
        ]
        valid = [
            b for b in sub_bboxes
            if (b[2] - b[0]) > min_segment_size and (b[3] - b[1]) > min_segment_size
        ]
        if len(valid) > 1:
            return valid

    # 无突变，返回原 bbox
    return [bbox]


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
    """枚举所有可行布局方案，按物品数自适应。

    返回顺序：横排 → 竖排 → 网格变体（按物品数选择合适的网格）。
    单物品(n=1)时只返回横排（=居中），多比例变体在 batch_compose_single_image 中处理。
    """
    layouts: list[dict[str, Any]] = []

    # 全横排（1 行 N 列）
    layouts.append({"type": "horizontal", "rows": [list(range(n))]})
    # 全竖排（N 行 1 列）
    layouts.append({"type": "vertical", "rows": [[i] for i in range(n)]})

    if n == 1:
        # 单物品：横排和竖排效果一样（居中），不额外加布局
        pass
    elif n == 2:
        # 2 个物品：横排 + 竖排已覆盖
        pass
    elif n == 3:
        # 3 个物品：2横1竖（上2下1）、1横2竖（上1下2）
        layouts.append({"type": "2h1v", "rows": [[0, 1], [2]]})
        layouts.append({"type": "1h2v", "rows": [[0], [1, 2]]})
    elif n == 4:
        # 4 个物品：2x2 网格
        layouts.append({"type": "grid", "rows": [[0, 1], [2, 3]]})
    elif n == 5:
        # 5 个物品：2x3（上3下2）、3x2（上2下2下1）
        layouts.append({"type": "grid", "rows": [[0, 1, 2], [3, 4]]})
        layouts.append({"type": "grid", "rows": [[0, 1], [2, 3], [4]]})
    elif n == 6:
        # 6 个物品：2x3 网格、3x2 网格
        layouts.append({"type": "grid", "rows": [[0, 1, 2], [3, 4, 5]]})
        layouts.append({"type": "grid", "rows": [[0, 1], [2, 3], [4, 5]]})
    elif n <= 9:
        # 7-9 个物品：3 列网格
        cols = 3
        rows = [list(range(i, min(i + cols, n))) for i in range(0, n, cols)]
        layouts.append({"type": "grid", "rows": rows})
    else:
        # 10+ 个物品：4 列网格
        cols = 4
        rows = [list(range(i, min(i + cols, n))) for i in range(0, n, cols)]
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
    """将布局方案渲染到白底画布，返回画布与位置信息。

    电商详情页风格：所有物品统一缩放到同一目标高度（保持宽高比），
    均匀间距，行内水平居中，整体在白底画布上居中排列。
    """
    rows = layout["rows"]
    n = len(objects)

    # 统一目标高度：取所有物品的最大高度，所有物品等高（保比例缩放宽度）
    max_h = max(o.height for o in objects)
    target_h = max_h

    # 缩放每个物品到 target_h（保持宽高比）
    scaled_objects: dict[int, Image.Image] = {}
    for i, obj in enumerate(objects):
        if obj.height != target_h and obj.height > 0:
            scale = target_h / obj.height
            new_w = max(1, int(obj.width * scale))
            scaled_objects[i] = obj.resize((new_w, target_h), Image.Resampling.LANCZOS)
        else:
            scaled_objects[i] = obj

    # 间距和留白（相对统一目标高度）
    gap = int(target_h * GAP_RATIO)
    padding = int(target_h * PADDING_RATIO)

    # 计算每行宽度（行内物品等高，宽度按比例）
    row_widths: list[int] = []
    for row in rows:
        if row:
            w = sum(scaled_objects[i].width for i in row) + gap * (len(row) - 1)
            row_widths.append(w)
        else:
            row_widths.append(0)

    canvas_w = max(row_widths) + padding * 2
    canvas_h = target_h * len(rows) + gap * (len(rows) - 1) + padding * 2

    # 创建白底画布
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    positions: list[dict[str, Any]] = [{} for _ in range(n)]

    y_cursor = padding
    for row, row_w in zip(rows, row_widths):
        # 行水平居中
        x_cursor = (canvas_w - row_w) // 2
        for i in row:
            obj = scaled_objects[i]
            # 物品在行内垂直居中（等高时 y = y_cursor）
            y = y_cursor + (target_h - obj.height) // 2
            # paste 到画布（RGBA 用 alpha 蒙版）
            canvas.paste(obj, (x_cursor, y), obj if obj.mode == "RGBA" else None)
            positions[i] = {
                "x": x_cursor,
                "y": y,
                "w": obj.width,
                "h": obj.height,
                "rotation": rotations[i] if i < len(rotations) else 0,
            }
            x_cursor += obj.width + gap
        y_cursor += target_h + gap

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


def batch_compose_single_image(
    image_path: Path,
    bboxes: list[dict[str, Any]],
    max_count: int = 6,
    layout_mode: str = "auto",
    target_ratio: str = "1:1",
    fmt: str = "JPG",
) -> list[dict[str, Any]]:
    """对单张图枚举布局变体，批量生成多张组合图。

    改进后逻辑：
    - 角度：用 suggested_rotation（VLM 分两步校正后的最佳值），不再枚举角度
    - 多物品：枚举多种布局变体（横排/竖排/网格等，按物品数自适应）
    - 单物品：固定 2 种摆放变体（竖放 + 横放），不受 max_count 限制

    Args:
        image_path: 原图路径
        bboxes: 检测结果列表，每个含 bbox/label/suggested_rotation
        max_count: 最大布局变体数（仅多物品生效，单物品固定 2 张）
        layout_mode: 布局模式（auto 时枚举所有，指定时只生成对应类型）
        target_ratio: 画布比例
        fmt: 输出格式 JPG/PNG

    Returns:
        [{"image_base64": str, "filename": str}, ...]
    """
    import base64
    import io as _io

    n = len(bboxes)
    if n == 0:
        raise RuntimeError("无物品可组合")

    # 角度：用 suggested_rotation（VLM 校正后的最佳值）
    rotations = [int(item.get("suggested_rotation", 0)) for item in bboxes]
    # 校验角度合法性
    rotations = [r if r in ALLOWED_ANGLES or r == 0 else 0 for r in rotations]

    # 裁剪+抠白底+旋转（只做一次，复用）
    rgba_objects = crop_to_rgba_objects(image_path, bboxes)
    rotated: list[Image.Image] = []
    for img, ang in zip(rgba_objects, rotations):
        rotated.append(rotate_object(img, ang) if ang else img)

    ext = "jpg" if fmt.upper() == "JPG" else "png"

    def _encode(canvas: Image.Image) -> str:
        buf = _io.BytesIO()
        if fmt.upper() == "JPG":
            canvas.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
        else:
            canvas.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    results: list[dict[str, Any]] = []

    if n == 1:
        # 单物品：2 种摆放变体（竖放 + 横放）
        # 竖放 = suggested_rotation（VLM 建议角度，文字正向）
        # 横放 = (suggested + 90) % 360（在竖放基础上再转 90°，文字朝侧正常）
        suggested = rotations[0]
        variants = [
            ("竖放", suggested),
            ("横放", (suggested + 90) % 360),
        ]
        for idx, (label, angle) in enumerate(variants):
            obj = rgba_objects[0] if angle == 0 else rotate_object(rgba_objects[0], angle)
            canvas, _positions = _render_layout(
                {"type": "horizontal", "rows": [[0]]},
                [obj],
                [angle],
            )
            results.append({
                "image_base64": _encode(canvas),
                "filename": f"组合{idx + 1:02d}_{label}.{ext}",
            })
        return results

    # 多物品：枚举布局变体
    all_layouts = _enumerate_layouts(n, rotated, target_ratio)

    # 如果 layout_mode 不是 auto，只保留对应类型（无匹配则用全部）
    if layout_mode != "auto":
        filtered = [l for l in all_layouts if l["type"] == layout_mode]
        if filtered:
            all_layouts = filtered

    # 截取前 max_count 个布局
    chosen_layouts = all_layouts[:max_count]

    for idx, layout in enumerate(chosen_layouts):
        canvas, _positions = _render_layout(layout, rotated, rotations)
        # 文件名包含布局类型便于区分
        layout_label = _layout_type_label(layout["type"])
        results.append({
            "image_base64": _encode(canvas),
            "filename": f"组合{idx + 1:02d}_{layout_label}.{ext}",
        })

    return results


def _layout_type_label(layout_type: str) -> str:
    """布局类型转中文标签（用于文件名）。"""
    labels = {
        "horizontal": "横排",
        "vertical": "竖排",
        "2h1v": "上2下1",
        "1h2v": "上1下2",
        "grid": "网格",
    }
    return labels.get(layout_type, layout_type)
