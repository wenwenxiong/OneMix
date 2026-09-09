from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import gc
import io
import json
import logging
import os
import tempfile
import time
import zipfile
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db, init_db
from app.deps import (
    get_ark_api_key_optional,
    get_dashscope_api_key_optional,
    resolve_api_key,
)
from app.jobs_store import get_job, start_generate_job
from app.providers.dashscope_provider import DashScopeProvider
from app.ref_paths import default_ref_white_index
from app.routers import settings as settings_routes
from app.schemas import (
    BundleAllBody,
    ComposeOptions,
    CreateJobBody,
    DetectObjectsOut,
    DetectedObject,
    ExtractInfoOut,
    JobStatusOut,
    PlanSingleBody,
    PlanSlotsBody,
    PlanSlotsRow,
    BatchComposeOptions,
    BatchComposeOut,
    BatchComposeResultItem,
)
from onemix.services import dashscope_svc
from onemix.services import image_compose

_api_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="onemix_api")


def _write_temp_upload(data: bytes, suffix: str) -> Path:
    """写入临时文件并立即关闭句柄，避免 Windows 上 mkstemp 未关闭导致无法删除。"""
    fd, name = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return Path(name)


def _try_unlink(path: Path) -> None:
    """删除临时文件；若第三方 SDK 仍短暂占用，则重试。"""
    for i in range(12):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
            time.sleep(0.04 * (i + 1))
        except FileNotFoundError:
            return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def get_provider() -> DashScopeProvider:
    return DashScopeProvider()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OneMix API", version="0.1.0", lifespan=lifespan)
app.include_router(settings_routes.router, prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _run_blocking(call):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_api_pool, call)


def _decode_text_bytes(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_text_file(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    txt = _decode_text_bytes(data)
    if suffix == ".csv":
        rows = list(csv.reader(txt.splitlines()))
        return "\n".join(["\t".join(r) for r in rows if r])
    return txt


def _is_image_upload(name: str, content_type: str | None) -> bool:
    suf = Path(name).suffix.lower()
    if content_type and content_type.startswith("image/"):
        return True
    return suf in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@app.post("/api/ocr")
async def api_ocr(
    api_key: Annotated[str, Depends(resolve_api_key)],
    provider: Annotated[DashScopeProvider, Depends(get_provider)],
    image: UploadFile = File(...),
) -> dict[str, str]:
    suffix = Path(image.filename or "ocr.png").suffix or ".png"
    data = await image.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "图片过大")

    tmp_path = _write_temp_upload(data, suffix)
    try:

        def work() -> str:
            return provider.ocr_from_image(api_key=api_key, image_path=tmp_path)

        text = await _run_blocking(work)
    finally:
        _try_unlink(tmp_path)
    return {"text": text}


@app.post("/api/extract/key-info", response_model=ExtractInfoOut)
async def api_extract_key_info(
    api_key: Annotated[str, Depends(resolve_api_key)],
    files: list[UploadFile] = File(...),
) -> ExtractInfoOut:
    if not files:
        raise HTTPException(400, "请至少上传一个文件")

    merged_parts: list[str] = []
    image_count = 0
    text_count = 0
    temp_images: list[Path] = []
    try:
        for f in files:
            name = f.filename or "unknown"
            data = await f.read()
            if not data:
                continue
            if len(data) > 30 * 1024 * 1024:
                raise HTTPException(413, f"文件过大: {name}")
            if _is_image_upload(name, f.content_type):
                image_count += 1
                p = _write_temp_upload(data, Path(name).suffix or ".png")
                temp_images.append(p)

                def ocr_work() -> str:
                    return dashscope_svc.ocr_from_image(api_key=api_key, image_path=p)

                text = await _run_blocking(ocr_work)
                merged_parts.append(f"## 文件: {name}\n{text.strip()}")
            else:
                text_count += 1
                parsed = _parse_text_file(name, data).strip()
                if parsed:
                    merged_parts.append(f"## 文件: {name}\n{parsed}")
        merged_text = "\n\n".join([x for x in merged_parts if x.strip()]).strip()
        if not merged_text:
            raise HTTPException(400, "未解析出有效文本，请检查上传内容")

        def extract_work() -> dict:
            return dashscope_svc.extract_key_info_from_text(api_key=api_key, text=merged_text)

        extracted = await _run_blocking(extract_work)
        return ExtractInfoOut(
            merged_text=merged_text,
            extracted_json=extracted,
            source_stats={
                "file_count": len(files),
                "image_count": image_count,
                "text_count": text_count,
            },
        )
    finally:
        for p in temp_images:
            _try_unlink(p)


@app.post("/api/competitor")
async def api_competitor(
    api_key: Annotated[str, Depends(resolve_api_key)],
    provider: Annotated[DashScopeProvider, Depends(get_provider)],
    images: list[UploadFile] = File(...),
) -> dict[str, str]:
    paths: list[Path] = []
    try:
        for uf in images:
            data = await uf.read()
            if len(data) > 25 * 1024 * 1024:
                raise HTTPException(413, "单张图片过大")
            suf = Path(uf.filename or "c.png").suffix or ".png"
            paths.append(_write_temp_upload(data, suf))

        def work() -> str:
            return provider.competitor_to_prompt(api_key=api_key, image_paths=paths)

        text = await _run_blocking(work)
    finally:
        for p in paths:
            _try_unlink(p)
    return {"text": text}


@app.post("/api/plan/slots")
async def api_plan_slots(
    api_key: Annotated[str, Depends(resolve_api_key)],
    provider: Annotated[DashScopeProvider, Depends(get_provider)],
    plan: str = Form(...),
    whites: list[UploadFile] = File(default=[]),
) -> dict[str, object]:
    try:
        body = PlanSlotsBody.model_validate(json.loads(plan))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"plan 字段 JSON 无效: {e}") from e

    tmp_paths: list[Path] = []
    try:
        for uf in whites:
            data = await uf.read()
            if not data:
                continue
            if len(data) > 40 * 1024 * 1024:
                raise HTTPException(413, "单张白底图过大")
            suf = Path(uf.filename or "w.png").suffix or ".png"
            tmp_paths.append(_write_temp_upload(data, suf))
        if not tmp_paths:
            raise HTTPException(400, "请至少上传一张白底参考图，以便结合参考图生成提示词")
        n_whites = max(1, len(tmp_paths))

        def work() -> list[tuple[str, int, str]]:
            return provider.plan_background_prompts_for_slots(
                api_key=api_key,
                product_name=body.product_name,
                product_desc=body.product_desc,
                competitor_summary=body.competitor_summary,
                n_main=body.n_main,
                n_detail=body.n_detail,
                n_video=body.n_video,
                strategy=body.strategy,
                custom_template=body.custom_template,
                user_requirements=body.user_requirements,
                ref_image_paths=tmp_paths,
            )

        rows_raw = await _run_blocking(work)
    finally:
        for p in tmp_paths:
            _try_unlink(p)

    rows: list[PlanSlotsRow] = []
    for li, (kind, idx, prompt) in enumerate(rows_raw):
        rwi = default_ref_white_index(n_whites, kind, int(idx))
        rows.append(
            PlanSlotsRow(
                list_index=li,
                kind=kind,
                index=idx,
                prompt=prompt,
                ref_white_index=rwi,
            )
        )
    return {"slots": [r.model_dump() for r in rows]}


@app.post("/api/plan/single")
async def api_plan_single(
    api_key: Annotated[str, Depends(resolve_api_key)],
    provider: Annotated[DashScopeProvider, Depends(get_provider)],
    plan: str = Form(...),
    whites: list[UploadFile] = File(default=[]),
) -> dict[str, str]:
    try:
        body = PlanSingleBody.model_validate(json.loads(plan))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"plan 字段 JSON 无效: {e}") from e

    tmp_paths: list[Path] = []
    try:
        for uf in whites:
            data = await uf.read()
            if not data:
                continue
            if len(data) > 40 * 1024 * 1024:
                raise HTTPException(413, "单张白底图过大")
            suf = Path(uf.filename or "w.png").suffix or ".png"
            tmp_paths.append(_write_temp_upload(data, suf))
        if not tmp_paths:
            raise HTTPException(400, "请至少上传一张白底参考图，以便结合参考图重构提示词")

        def work() -> str:
            return provider.plan_single_slot_prompt(
                api_key=api_key,
                product_name=body.product_name,
                product_desc=body.product_desc,
                competitor_summary=body.competitor_summary,
                kind=body.kind,
                index=body.index,
                strategy=body.strategy,
                old_prompt=body.old_prompt,
                ref_image_paths=tmp_paths,
                primary_ref_index=body.ref_white_index,
            )

        text = await _run_blocking(work)
    finally:
        for p in tmp_paths:
            _try_unlink(p)

    return {"prompt": text}


@app.post("/api/jobs", response_model=JobStatusOut)
async def api_create_job(
    db: Annotated[Session, Depends(get_db)],
    x_dashscope_key: Annotated[str | None, Header(alias="X-DashScope-Key")] = None,
    x_ark_key: Annotated[str | None, Header(alias="X-Ark-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    whites: list[UploadFile] = File(...),
    job: str = Form(...),
) -> JobStatusOut:
    if not whites:
        raise HTTPException(400, "请至少上传一张白底商品图")
    try:
        body = CreateJobBody.model_validate(json.loads(job))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"job 字段 JSON 无效: {e}") from e

    dashscope_key = get_dashscope_api_key_optional(
        db=db, x_dashscope_key=x_dashscope_key, authorization=authorization
    )
    ark_key = get_ark_api_key_optional(db=db, x_ark_key=x_ark_key)
    if dashscope_svc.strategy_requires_ark(body.strategy):
        if not ark_key:
            raise HTTPException(
                401,
                "缺少 ARK API Key：请在前端保存豆包/即梦 Key，或通过请求头 X-Ark-Key / 环境变量 ARK_API_KEY 提供。",
            )
    elif dashscope_svc.strategy_requires_dashscope_for_gen(body.strategy):
        if not dashscope_key:
            raise HTTPException(
                401,
                "缺少 DashScope API Key：请在前端保存阿里百炼 Key，或通过请求头 X-DashScope-Key / Authorization 提供。",
            )
    elif not dashscope_key:
        raise HTTPException(
            401,
            "缺少 DashScope API Key：请在前端保存阿里百炼 Key，或通过请求头 X-DashScope-Key / Authorization 提供。",
        )

    tmp_paths: list[Path] = []
    try:
        for uf in whites:
            data = await uf.read()
            if len(data) > 40 * 1024 * 1024:
                raise HTTPException(413, "单张白底图过大")
            suf = Path(uf.filename or "w.png").suffix or ".png"
            tmp_paths.append(_write_temp_upload(data, suf))

        job_id = start_generate_job(
            dashscope_api_key=dashscope_key,
            ark_api_key=ark_key,
            white_sources=tmp_paths,
            body=body,
        )
    finally:
        for p in tmp_paths:
            _try_unlink(p)

    return JobStatusOut(id=job_id, status="pending", progress=0, total=0)


@app.get("/api/jobs/{job_id}", response_model=JobStatusOut)
def api_get_job(job_id: str) -> JobStatusOut:
    rec = get_job(job_id)
    if rec is None:
        # 开发态热重载会清空内存任务表；给前端返回可读状态，避免 404 打断轮询。
        exp = Path.home() / ".cache" / "OneMix" / "jobs" / job_id / "export"
        if exp.is_dir():
            return JobStatusOut(
                id=job_id,
                status="completed",
                progress=0,
                total=0,
                error=None,
                results=[],
                session_rel="export",
            )
        return JobStatusOut(
            id=job_id,
            status="failed",
            progress=0,
            total=0,
            error="任务状态已丢失（服务可能刚重启）。请重新发起生成任务。",
            results=[],
            session_rel=None,
        )
    results = rec.results
    session_rel = "export" if rec.export_session and rec.export_session.is_dir() else None
    return JobStatusOut(
        id=rec.id,
        status=rec.status,  # type: ignore[arg-type]
        progress=rec.progress,
        total=rec.total,
        error=rec.error,
        results=results,
        session_rel=session_rel,
    )


@app.get("/api/jobs/{job_id}/bundle")
def api_job_bundle(job_id: str) -> StreamingResponse:
    rec = get_job(job_id)
    exp = rec.work_dir / "export" if rec is not None else (Path.home() / ".cache" / "OneMix" / "jobs" / job_id / "export")
    if not exp.is_dir():
        raise HTTPException(400, "导出目录不存在")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(exp.rglob("*")):
            if p.is_file():
                arc = p.relative_to(exp).as_posix()
                zf.write(p, arcname=arc)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="onemix_{job_id}.zip"'},
    )


def _resolve_result_file(
    job_id: str,
    list_index: int,
    *,
    kind: str | None = None,
    index: int | None = None,
) -> Path | None:
    """定位任务中某槽位的导出文件（内存结果优先，磁盘回退）。"""
    rec = get_job(job_id)
    if rec is not None and rec.results:
        target = next(
            (x for x in rec.results if int(x.get("list_index", -1)) == list_index),
            None,
        )
        if target:
            p = Path(str(target.get("export_path", ""))).expanduser().resolve()
            if p.is_file():
                return p
    exp = Path.home() / ".cache" / "OneMix" / "jobs" / job_id / "export"
    if rec is not None and rec.export_session and rec.export_session.is_dir():
        exp = rec.export_session
    if not exp.is_dir():
        return None
    # 按 kind + 展示序号匹配（export/主图/main_01.jpg）
    if kind and index is not None and index >= 1:
        prefix = {"main": "main", "detail": "detail", "video": "video"}.get(kind)
        folder = {"main": "主图", "detail": "详情", "video": "视频"}.get(kind)
        if prefix and folder:
            for cand in (
                exp / folder / f"{prefix}_{index:02d}.jpg",
                exp / folder / f"{prefix}_{index:02d}.jpeg",
                exp / folder / f"{prefix}_{index:02d}.png",
                exp / folder / f"{prefix}_{index:02d}.mp4",
            ):
                if cand.is_file():
                    return cand
            hits = sorted((exp / folder).glob(f"{prefix}_{index:02d}.*")) if (exp / folder).is_dir() else []
            if hits:
                return hits[0]
    candidates = (
        sorted(exp.rglob("*.jpg"))
        + sorted(exp.rglob("*.jpeg"))
        + sorted(exp.rglob("*.png"))
        + sorted(exp.rglob("*.mp4"))
    )
    if 0 <= list_index < len(candidates):
        return candidates[list_index]
    return None


@app.post("/api/jobs/bundle-all")
def api_jobs_bundle_all(body: BundleAllBody) -> StreamingResponse:
    """将主图 / 详情图 / 视频按分类打包为一个 ZIP。"""
    folder_by_kind = {"main": "主图", "detail": "详情", "video": "视频"}
    prefix_by_kind = {"main": "main", "detail": "detail", "video": "video"}
    default_ext = {"main": ".jpg", "detail": ".jpg", "video": ".mp4"}

    buf = io.BytesIO()
    packed = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in body.items:
            src = _resolve_result_file(
                item.job_id,
                item.list_index,
                kind=item.kind,
                index=item.index,
            )
            if src is None or not src.is_file():
                continue
            folder = folder_by_kind[item.kind]
            prefix = prefix_by_kind[item.kind]
            ext = src.suffix.lower() or default_ext[item.kind]
            base_name = f"{prefix}_{item.index:02d}{ext}"
            arc = f"{folder}/{base_name}"
            if arc in used_names:
                stem = f"{prefix}_{item.index:02d}"
                n = 2
                while f"{folder}/{stem}_{n}{ext}" in used_names:
                    n += 1
                arc = f"{folder}/{stem}_{n}{ext}"
            used_names.add(arc)
            zf.write(src, arcname=arc)
            packed += 1

    if packed == 0:
        raise HTTPException(400, "没有可打包的生成结果，请先完成主图/详情图/视频生成")

    safe_name = "".join(
        c if (c.isascii() and (c.isalnum() or c in "-_")) else "_"
        for c in (body.product_name or "onemix").strip()
    ).strip("_") or "onemix"
    # Content-Disposition 仅允许 latin-1；中文文件名由前端 a.download 指定
    filename = f"{safe_name}_all_assets.zip"
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/{job_id}/result/{list_index}")
def api_job_result_preview(job_id: str, list_index: int) -> FileResponse:
    rec = get_job(job_id)
    if rec is None:
        # 服务重启后内存结果丢失，退化为按目录与命名规则查找。
        exp = Path.home() / ".cache" / "OneMix" / "jobs" / job_id / "export"
        if not exp.is_dir():
            raise HTTPException(404, "任务不存在")
        candidates = (
            sorted(exp.rglob("*.jpg"))
            + sorted(exp.rglob("*.jpeg"))
            + sorted(exp.rglob("*.png"))
            + sorted(exp.rglob("*.mp4"))
        )
        if list_index < 0 or list_index >= len(candidates):
            raise HTTPException(404, "槽位结果不存在")
        p = candidates[list_index]
        media = "video/mp4" if p.suffix.lower() == ".mp4" else None
        return FileResponse(path=str(p), media_type=media) if media else FileResponse(path=str(p))
    if not rec.results:
        raise HTTPException(404, "任务结果不存在")

    target = next((x for x in rec.results if int(x.get("list_index", -1)) == list_index), None)
    if not target:
        raise HTTPException(404, "槽位结果不存在")

    p = Path(str(target.get("export_path", ""))).expanduser().resolve()
    if not p.is_file():
        raise HTTPException(404, "结果文件不存在")
    if p.suffix.lower() == ".mp4":
        return FileResponse(path=str(p), media_type="video/mp4")
    return FileResponse(path=str(p))


# -----------------------------------------------------------------------------
# 图片组合工具：物品检测 + 旋转/布局/合成（独立于 AI 生图流程）
# -----------------------------------------------------------------------------


@app.post("/api/image/detect-objects", response_model=DetectObjectsOut)
async def api_detect_objects(
    db: Annotated[Session, Depends(get_db)],
    x_dashscope_key: Annotated[str | None, Header(alias="X-DashScope-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
    image: UploadFile = File(...),
    mode: str = Form("auto"),
) -> DetectObjectsOut:
    """识别单张白底图中的多个独立物品，返回每个物品的 bbox。

    mode:
      - "vlm"：强制使用 qwen-vl-plus（需 DashScope Key）
      - "local"：强制使用本地连通域分割（无需 Key）
      - "auto"（默认）：有 Key 用 VLM，失败/无 Key 降级到本地
    """
    data = await image.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "图片过大（限 25MB）")
    suf = Path(image.filename or "img.png").suffix or ".png"
    tmp = _write_temp_upload(data, suf)
    try:
        from PIL import Image as _PILImage

        with _PILImage.open(tmp) as _im:
            img_w, img_h = _im.size

        objects: list[dict] = []
        source = "local"

        if mode in ("vlm", "auto"):
            dashscope_key = get_dashscope_api_key_optional(
                db=db, x_dashscope_key=x_dashscope_key, authorization=authorization
            )
            if dashscope_key:
                try:
                    def work_vlm() -> list[dict]:
                        return image_compose.detect_objects_via_vlm(tmp, dashscope_key)

                    objects = await _run_blocking(work_vlm)
                    source = "vlm"
                except Exception as e:
                    logger.warning("VLM 检测失败，降级到本地连通域: %s", e)
                    if mode == "vlm":
                        raise HTTPException(500, f"VLM 检测失败: {e}")
                    objects = []
            elif mode == "vlm":
                raise HTTPException(401, "VLM 模式需要 DashScope API Key")

        if not objects and mode in ("local", "auto"):
            try:
                def work_local() -> list[dict]:
                    return image_compose.detect_objects_local(tmp)

                objects = await _run_blocking(work_local)
                source = "local"
            except Exception as e:
                raise HTTPException(500, f"物品检测失败: {e}")

        if not objects:
            raise HTTPException(500, "未检测到任何物品")

        return DetectObjectsOut(
            objects=[DetectedObject(**o) for o in objects],
            source=source,
            image_width=img_w,
            image_height=img_h,
        )
    finally:
        _try_unlink(tmp)


@app.post("/api/image/compose")
async def api_compose_image(
    image: UploadFile = File(...),
    options: str = Form(...),
) -> StreamingResponse:
    """根据 bbox + 旋转角度 + 布局模式，合成最终图片。

    options 为 JSON 字符串，对应 ComposeOptions 模型。
    """
    try:
        body = ComposeOptions.model_validate(json.loads(options))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"options JSON 无效: {e}") from e

    data = await image.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "图片过大（限 25MB）")
    suf = Path(image.filename or "img.png").suffix or ".png"
    tmp = _write_temp_upload(data, suf)
    try:
        bboxes = [o.model_dump() for o in body.bboxes]
        rotations = body.rotations if body.rotations else [0] * len(bboxes)
        if len(rotations) != len(bboxes):
            raise HTTPException(400, "rotations 长度须与 bboxes 一致")

        def work() -> tuple[bytes, str]:
            from PIL import Image as _PILImage
            import io as _io

            canvas, _positions = image_compose.compose_image(
                image_path=tmp,
                bboxes=bboxes,
                rotations=rotations,
                layout_mode=body.layout_mode,
                seed=body.seed,
                target_ratio=body.target_ratio,
            )
            buf = _io.BytesIO()
            if body.fmt.upper() == "JPG":
                canvas.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
                mime = "image/jpeg"
                ext = "jpg"
            else:
                canvas.save(buf, "PNG", optimize=True)
                mime = "image/png"
                ext = "png"
            return buf.getvalue(), f"compose.{ext}"

        img_bytes, filename = await _run_blocking(work)
    finally:
        _try_unlink(tmp)

    return StreamingResponse(
        io.BytesIO(img_bytes),
        media_type="image/jpeg" if body.fmt.upper() == "JPG" else "image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/image/batch-compose", response_model=BatchComposeOut)
async def api_batch_compose_image(
    options: str = Form(...),
    images: list[UploadFile] = File(...),
) -> BatchComposeOut:
    """批量组合生图：对多张图各自枚举角度组合，返回 base64 图片数组。

    options 为 JSON 字符串，对应 BatchComposeOptions 模型。
    images 为多张上传图片，顺序须与 options.items 对应。
    """
    try:
        body = BatchComposeOptions.model_validate(json.loads(options))
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(400, f"options JSON 无效: {e}") from e

    if not images:
        raise HTTPException(400, "至少上传 1 张图片")
    if len(images) != len(body.items):
        raise HTTPException(400, f"图片数({len(images)})与检测结果数({len(body.items)})不一致")

    # 总量封顶 100 张
    total_max = len(images) * body.max_count
    if total_max > 100:
        raise HTTPException(
            400,
            f"总结果数上限 100 张，当前配置最多 {total_max} 张（{len(images)} 图 × {body.max_count} 张/图），请减少图片数或最大张数",
        )

    # 读取所有图片到临时文件
    tmp_files: list[Path] = []
    try:
        for img_upload in images:
            data = await img_upload.read()
            if len(data) > 25 * 1024 * 1024:
                raise HTTPException(413, f"图片 {img_upload.filename or ''} 过大（限 25MB）")
            suf = Path(img_upload.filename or "img.png").suffix or ".png"
            tmp_files.append(_write_temp_upload(data, suf))

        def work() -> list[dict]:
            all_results: list[dict] = []
            for img_idx, (tmp, item) in enumerate(zip(tmp_files, body.items)):
                bboxes = [o.model_dump() for o in item.bboxes]
                if not bboxes:
                    continue
                single_results = image_compose.batch_compose_single_image(
                    image_path=tmp,
                    bboxes=bboxes,
                    max_count=body.max_count,
                    layout_mode=body.layout_mode,
                    target_ratio=body.target_ratio,
                    fmt=body.fmt,
                )
                for r in single_results:
                    all_results.append({
                        "image_base64": r["image_base64"],
                        "filename": f"图{img_idx + 1}_{r['filename']}",
                        "image_index": img_idx + 1,
                    })
            return all_results

        results_raw = await _run_blocking(work)
    finally:
        for tmp in tmp_files:
            _try_unlink(tmp)

    return BatchComposeOut(
        results=[BatchComposeResultItem(**r) for r in results_raw],
        total=len(results_raw),
    )
