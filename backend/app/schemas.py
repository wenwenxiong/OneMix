from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SlotJobIn(BaseModel):
    list_index: int
    kind: Literal["main", "detail", "video"]
    index: int
    prompt: str
    export_path: Optional[str] = None
    ref_image_path: Optional[str] = None
    ref_white_index: Optional[int] = Field(
        default=None,
        description="白底图序号（从 0 起）；为空时按主窗口规则自动选。",
    )
    aspect_ratio: Optional[str] = Field(
        default="1:1",
        description="宽高比（须为当前模型官方推荐表中的值）。",
    )
    resolution: Optional[str] = Field(
        default="2K",
        description="分辨率档位：依模型而定（如 Seedream 的 2K/3K，Seedance 的 480p/720p）。",
    )
    duration: Optional[int] = Field(
        default=None,
        description="视频时长（秒），仅 kind=video 时使用；Seedance 支持 4–15。",
    )


class PlanSlotsBody(BaseModel):
    product_name: str
    product_desc: str = ""
    competitor_summary: str = ""
    n_main: int = 5
    n_detail: int = 10
    n_video: int = 0
    strategy: str = "background_v2"
    n_white_images: int = Field(default=1, ge=1, description="用于计算每张槽位默认参考的白底图数量（与实际上传张数一致即可）。")
    custom_template: str = ""
    user_requirements: str = ""


class PlanSlotsRow(BaseModel):
    list_index: int
    kind: str
    index: int
    prompt: str
    ref_white_index: int


class PlanSingleBody(BaseModel):
    product_name: str
    product_desc: str = ""
    competitor_summary: str = ""
    kind: Literal["main", "detail", "video"]
    index: int
    strategy: str = "background_v2"
    old_prompt: str = ""
    ref_white_index: Optional[int] = Field(
        default=None,
        description="本槽主参考白底图下标（对应 whites 列表，从 0 起）。",
    )


class CreateJobBody(BaseModel):
    slot_jobs: list[SlotJobIn]
    fmt: str = "JPG"
    strategy: str = "background_v2"
    only_indices: Optional[list[int]] = None
    skip_done: bool = True
    # 兼容旧客户端字段（已忽略：详情图不再按 750 规格后处理）
    dw: Optional[int] = None
    dh: Optional[int] = None
    detail_platform: Optional[str] = None
    detail_max_kb: Optional[int] = None

class JobStatusOut(BaseModel):
    id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress: int = 0
    total: int = 0
    error: Optional[str] = None
    results: Optional[list[dict]] = None
    session_rel: Optional[str] = None


class DashScopeKeyIn(BaseModel):
    api_key: str = Field(min_length=1, description="写入 SQLite 的 DashScope API Key")


class ArkKeyIn(BaseModel):
    api_key: str = Field(min_length=1, description="写入 SQLite 的 ARK API Key")


class GptImageKeyIn(BaseModel):
    api_key: str = Field(min_length=1, description="写入 SQLite 的 GPT-image-2 / OpenAI API Key")


class SettingsOut(BaseModel):
    has_dashscope_key: bool
    dashscope_key_preview: Optional[str] = Field(
        default=None, description="仅展示末尾若干字符，不全文返回"
    )
    dashscope_key_updated_at: Optional[str] = Field(
        default=None, description="ISO8601 时间（UTC 存库为 naive 时按本地展示）"
    )
    has_ark_key: bool = False
    ark_key_preview: Optional[str] = Field(
        default=None, description="仅展示末尾若干字符，不全文返回"
    )
    ark_key_updated_at: Optional[str] = Field(
        default=None, description="ISO8601 时间（UTC 存库为 naive 时按本地展示）"
    )
    has_gpt_image_key: bool = False
    gpt_image_key_preview: Optional[str] = Field(
        default=None, description="仅展示末尾若干字符，不全文返回"
    )
    gpt_image_key_updated_at: Optional[str] = Field(
        default=None, description="ISO8601 时间（UTC 存库为 naive 时按本地展示）"
    )


class ArkSeedreamModelOut(BaseModel):
    strategy: str
    label: str
    model_id: str
    owned: bool = True
    status: str = Field(
        default="open",
        description="open=已开通推理 / closed=未开通 / unknown=无法判断",
    )


class ArkSeedreamModelsOut(BaseModel):
    models: list[ArkSeedreamModelOut]
    source: str = "ark:/v3/models"


class DashScopeQwenImageModelOut(BaseModel):
    strategy: str
    label: str
    model_id: str
    owned: bool = True


class DashScopeQwenImageModelsOut(BaseModel):
    models: list[DashScopeQwenImageModelOut]
    source: str = "dashscope:/api/v1/models"


class ExtractInfoOut(BaseModel):
    merged_text: str
    extracted_json: dict
    source_stats: dict[str, int]


class BundleAllItemIn(BaseModel):
    job_id: str
    list_index: int
    kind: Literal["main", "detail", "video"]
    index: int = Field(ge=1, description="展示序号，用于 ZIP 内文件名")


class BundleAllBody(BaseModel):
    items: list[BundleAllItemIn] = Field(min_length=1)
    product_name: str = ""


class DetectedObject(BaseModel):
    bbox: list[int] = Field(min_length=4, max_length=4, description="[x1, y1, x2, y2] 像素坐标")
    label: str = "物品"


class DetectObjectsOut(BaseModel):
    objects: list[DetectedObject]
    source: str = Field(description="vlm 或 local")
    image_width: int
    image_height: int


class ComposeOptions(BaseModel):
    bboxes: list[DetectedObject] = Field(description="物品 bbox 列表（来自 detect-objects 或前端手动构造）")
    rotations: list[int] = Field(
        default_factory=list,
        description="每个物品的旋转角度（0/90/180/270），长度须与 bboxes 一致",
    )
    layout_mode: str = Field(
        default="auto",
        description="布局模式：auto/horizontal/vertical/2h1v/1h2v/grid",
    )
    seed: Optional[int] = Field(default=None, description="随机种子，用于复现布局")
    target_ratio: str = Field(default="1:1", description="目标画布宽高比：1:1/3:4/4:3")
    fmt: str = Field(default="JPG", description="输出格式：JPG 或 PNG")
