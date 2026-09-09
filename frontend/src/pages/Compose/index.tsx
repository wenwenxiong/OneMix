import { useCallback, useRef, useState } from "react";
import { ArrowLeft, ScanSearch, Sparkles, RefreshCw, Layers, Images } from "lucide-react";
import { toast } from "sonner";
import JSZip from "jszip";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ComposeUploader } from "@/components/compose/ComposeUploader";
import { ObjectPreview } from "@/components/compose/ObjectPreview";
import { LayoutSelector } from "@/components/compose/LayoutSelector";
import { ResultPanel } from "@/components/compose/ResultPanel";
import { BatchControls } from "@/components/compose/BatchControls";
import { BatchResultGrid } from "@/components/compose/BatchResultGrid";
import { ThemeToggle } from "@/components/theme-toggle";

type DetectedObject = {
  bbox: [number, number, number, number];
  label: string;
  suggested_rotation: number;
};

type BatchResultItem = {
  url: string;
  filename: string;
  imageIndex: number;
};

type Props = {
  onBack: () => void;
  apiKey: string;
};

type Mode = "single" | "batch";

export default function ComposePage({ onBack, apiKey }: Props) {
  const [mode, setMode] = useState<Mode>("single");

  // ===== 单图模式 state =====
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string>("");
  const [objects, setObjects] = useState<DetectedObject[]>([]);
  const [detectSource, setDetectSource] = useState<string>("");
  const [imgSize, setImgSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [rotations, setRotations] = useState<number[]>([]);
  const [layoutMode, setLayoutMode] = useState<string>("auto");
  const [targetRatio, setTargetRatio] = useState<string>("1:1");
  const [resultUrl, setResultUrl] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ===== 批量模式 state =====
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchUrls, setBatchUrls] = useState<string[]>([]);
  const [batchObjects, setBatchObjects] = useState<DetectedObject[][]>([]);
  const [batchDetectSources, setBatchDetectSources] = useState<string[]>([]);
  const [batchDetecting, setBatchDetecting] = useState(false);
  const [batchResults, setBatchResults] = useState<BatchResultItem[]>([]);
  const [maxCount, setMaxCount] = useState<number>(6);
  const [batchLayoutMode, setBatchLayoutMode] = useState<string>("auto");
  const [batchTargetRatio, setBatchTargetRatio] = useState<string>("1:1");
  const [zipping, setZipping] = useState(false);
  const batchFileInputRef = useRef<HTMLInputElement>(null);

  // ===== 单图模式 handlers =====
  const onFileSelect = useCallback((file: File) => {
    setImageFile(file);
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setImageUrl(URL.createObjectURL(file));
    setObjects([]);
    setRotations([]);
    setResultUrl("");
  }, [imageUrl]);

  const onDetect = useCallback(async () => {
    if (!imageFile) {
      toast.error("请先上传图片");
      return;
    }
    setDetecting(true);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("image", imageFile);
      fd.append("mode", "auto");
      const headers: Record<string, string> = {};
      if (apiKey) headers["X-DashScope-Key"] = apiKey;
      const r = await fetch("/api/image/detect-objects", {
        method: "POST",
        headers,
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as {
        objects: DetectedObject[];
        source: string;
        image_width: number;
        image_height: number;
      };
      setObjects(data.objects);
      setDetectSource(data.source);
      setImgSize({ w: data.image_width, h: data.image_height });
      setRotations(data.objects.map((o) => o.suggested_rotation ?? 0));
      const autoCount = data.objects.filter((o) => (o.suggested_rotation ?? 0) !== 0).length;
      toast.success(
        `检测到 ${data.objects.length} 个物品（${data.source === "vlm" ? "VLM" : "本地"}）` +
          (autoCount > 0 ? `，${autoCount} 个已自动校正角度` : ""),
      );
    } catch (err) {
      toast.error(`检测失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setDetecting(false);
      setBusy(false);
    }
  }, [imageFile, apiKey]);

  const onRotationChange = useCallback((index: number, angle: number) => {
    setRotations((prev) => {
      const next = [...prev];
      next[index] = angle;
      return next;
    });
  }, []);

  const onCompose = useCallback(async () => {
    if (!imageFile || objects.length === 0) {
      toast.error("请先上传图片并检测物品");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("image", imageFile);
      fd.append(
        "options",
        JSON.stringify({
          bboxes: objects,
          rotations: rotations.length === objects.length ? rotations : new Array(objects.length).fill(0),
          layout_mode: layoutMode,
          target_ratio: targetRatio,
          fmt: "JPG",
        }),
      );
      const r = await fetch("/api/image/compose", {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      if (resultUrl) URL.revokeObjectURL(resultUrl);
      setResultUrl(URL.createObjectURL(blob));
      toast.success("组合完成");
    } catch (err) {
      toast.error(`组合失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }, [imageFile, objects, rotations, layoutMode, targetRatio, resultUrl]);

  const onDownload = useCallback(() => {
    if (!resultUrl) return;
    const a = document.createElement("a");
    a.href = resultUrl;
    a.download = `onemix-compose-${Date.now()}.jpg`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [resultUrl]);

  const onReset = useCallback(() => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    if (resultUrl) URL.revokeObjectURL(resultUrl);
    setImageFile(null);
    setImageUrl("");
    setObjects([]);
    setRotations([]);
    setResultUrl("");
    setDetectSource("");
  }, [imageUrl, resultUrl]);

  // ===== 批量模式 handlers =====
  const onBatchFilesSelect = useCallback((files: File[]) => {
    const newUrls = files.map((f) => URL.createObjectURL(f));
    setBatchFiles((prev) => [...prev, ...files]);
    setBatchUrls((prev) => [...prev, ...newUrls]);
    setBatchObjects([]);
    setBatchDetectSources([]);
    setBatchResults([]);
  }, []);

  const onBatchRemoveAt = useCallback((index: number) => {
    setBatchFiles((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next;
    });
    setBatchUrls((prev) => {
      const url = prev[index];
      if (url) URL.revokeObjectURL(url);
      return prev.filter((_, i) => i !== index);
    });
    setBatchObjects((prev) => prev.filter((_, i) => i !== index));
    setBatchDetectSources((prev) => prev.filter((_, i) => i !== index));
    setBatchResults([]);
  }, []);

  const onBatchReset = useCallback(() => {
    batchUrls.forEach((u) => URL.revokeObjectURL(u));
    batchResults.forEach((r) => URL.revokeObjectURL(r.url));
    setBatchFiles([]);
    setBatchUrls([]);
    setBatchObjects([]);
    setBatchDetectSources([]);
    setBatchResults([]);
  }, [batchUrls, batchResults]);

  const onBatchDetect = useCallback(async () => {
    if (batchFiles.length === 0) {
      toast.error("请先上传图片");
      return;
    }
    setBatchDetecting(true);
    setBusy(true);
    setBatchResults([]);
    try {
      const headers: Record<string, string> = {};
      if (apiKey) headers["X-DashScope-Key"] = apiKey;

      // 并行检测所有图
      const detectPromises = batchFiles.map(async (file, idx) => {
        const fd = new FormData();
        fd.append("image", file);
        fd.append("mode", "auto");
        const r = await fetch("/api/image/detect-objects", { method: "POST", headers, body: fd });
        if (!r.ok) throw new Error(`图${idx + 1}: ${await r.text()}`);
        const data = (await r.json()) as {
          objects: DetectedObject[];
          source: string;
          image_width: number;
          image_height: number;
        };
        return { objects: data.objects, source: data.source };
      });

      const results = await Promise.all(detectPromises);
      setBatchObjects(results.map((r) => r.objects));
      setBatchDetectSources(results.map((r) => r.source));

      const totalObjects = results.reduce((sum, r) => sum + r.objects.length, 0);
      const vlmCount = results.filter((r) => r.source === "vlm").length;
      toast.success(
        `${batchFiles.length} 张图检测完成，共 ${totalObjects} 个物品` +
          (vlmCount > 0 ? `（${vlmCount} 张用 VLM）` : ""),
      );
    } catch (err) {
      toast.error(`批量检测失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBatchDetecting(false);
      setBusy(false);
    }
  }, [batchFiles, apiKey]);

  const onBatchCompose = useCallback(async () => {
    if (batchFiles.length === 0 || batchObjects.length === 0) {
      toast.error("请先上传图片并检测物品");
      return;
    }
    // 校验总量
    const total = batchFiles.length * maxCount;
    if (total > 100) {
      toast.error(`总结果数 ${total} 超过上限 100，请减少图片数或最大张数`);
      return;
    }
    setBusy(true);
    // 清理旧结果
    batchResults.forEach((r) => URL.revokeObjectURL(r.url));
    setBatchResults([]);
    try {
      const fd = new FormData();
      // 按顺序 append 每张图
      batchFiles.forEach((f) => fd.append("images", f));
      fd.append(
        "options",
        JSON.stringify({
          items: batchObjects.map((objs) => ({ bboxes: objs })),
          max_count: maxCount,
          layout_mode: batchLayoutMode,
          target_ratio: batchTargetRatio,
          fmt: "JPG",
        }),
      );

      const r = await fetch("/api/image/batch-compose", { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as {
        results: { image_base64: string; filename: string; image_index: number }[];
        total: number;
      };

      // base64 转 blob URL
      const items: BatchResultItem[] = data.results.map((item) => {
        const byteChars = atob(item.image_base64);
        const byteArrays: number[] = [];
        for (let i = 0; i < byteChars.length; i++) byteArrays.push(byteChars.charCodeAt(i));
        const blob = new Blob([new Uint8Array(byteArrays)], { type: "image/jpeg" });
        return {
          url: URL.createObjectURL(blob),
          filename: item.filename,
          imageIndex: item.image_index,
        };
      });
      setBatchResults(items);
      toast.success(`批量生成完成，共 ${items.length} 张`);
    } catch (err) {
      toast.error(`批量生成失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }, [batchFiles, batchObjects, maxCount, batchLayoutMode, batchTargetRatio, batchResults]);

  const onBatchDownloadOne = useCallback((item: BatchResultItem) => {
    const a = document.createElement("a");
    a.href = item.url;
    a.download = item.filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, []);

  const onBatchDownloadAllZip = useCallback(async () => {
    if (batchResults.length === 0) return;
    setZipping(true);
    try {
      const zip = new JSZip();
      // 按 imageIndex 分文件夹
      for (const item of batchResults) {
        const resp = await fetch(item.url);
        const blob = await resp.blob();
        const folderName = `图${item.imageIndex}`;
        zip.file(`${folderName}/${item.filename}`, blob);
      }
      const zipBlob = await zip.generateAsync({ type: "blob" });
      const zipUrl = URL.createObjectURL(zipBlob);
      const a = document.createElement("a");
      a.href = zipUrl;
      a.download = `onemix-batch-compose-${Date.now()}.zip`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(zipUrl);
      toast.success("ZIP 打包下载完成");
    } catch (err) {
      toast.error(`ZIP 打包失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setZipping(false);
    }
  }, [batchResults]);

  const allBatchDetected = batchObjects.length === batchFiles.length && batchObjects.length > 0;

  return (
    <main className="min-h-screen bg-background" aria-busy={busy}>
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border/80 px-6 py-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={onBack} aria-label="返回首页">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <p className="text-xl font-semibold tracking-tight">图片组合工具</p>
            <p className="text-sm text-muted-foreground">
              上传白底物品图 → 识别物品 → 旋转/布局 → 生成组合图
            </p>
          </div>
        </div>
        <ThemeToggle />
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {/* 模式切换 Tab */}
        <div className="flex gap-2">
          <Button
            variant={mode === "single" ? "default" : "outline"}
            onClick={() => setMode("single")}
            className="gap-1.5"
          >
            <Images className="h-4 w-4" />
            单图模式
          </Button>
          <Button
            variant={mode === "batch" ? "default" : "outline"}
            onClick={() => setMode("batch")}
            className="gap-1.5"
          >
            <Layers className="h-4 w-4" />
            批量模式
          </Button>
        </div>

        {mode === "single" ? (
          <>
            {/* 步骤 1：上传 */}
            <Card>
              <CardHeader>
                <CardTitle>步骤 1：上传白底物品图</CardTitle>
                <CardDescription>
                  上传一张含一个或多个物品的白底展示图。物品间建议有清晰间隙以提升识别精度。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ComposeUploader
                  imageUrl={imageUrl}
                  fileInputRef={fileInputRef}
                  onFileSelect={onFileSelect}
                  onReset={onReset}
                />
                {imageFile && (
                  <div className="mt-4 flex gap-2">
                    <Button onClick={onDetect} disabled={detecting}>
                      <ScanSearch className="h-4 w-4" />
                      {detecting ? "识别中..." : "识别物品"}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 步骤 2：物品预览 + 旋转设置 */}
            {objects.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>步骤 2：旋转校正</CardTitle>
                <CardDescription>
                  检测到 {objects.length} 个物品（来源：{detectSource === "vlm" ? "VLM" : "本地连通域"}）。
                  {detectSource === "vlm"
                    ? "VLM 分两步检测：先识别物品，再逐个判断文字朝向自动校正角度，可手动微调。"
                    : "本地模式无法自动判断文字方向，请手动选择旋转角度使文字正向。"}
                </CardDescription>
                </CardHeader>
                <CardContent>
                  <ObjectPreview
                    imageUrl={imageUrl}
                    objects={objects}
                    rotations={rotations}
                    imgSize={imgSize}
                    onRotationChange={onRotationChange}
                  />
                </CardContent>
              </Card>
            )}

            {/* 步骤 3：布局选择 */}
            {objects.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>步骤 3：布局与生成</CardTitle>
                  <CardDescription>选择布局模式和画布比例，然后生成组合图。</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <LayoutSelector
                    layoutMode={layoutMode}
                    targetRatio={targetRatio}
                    onLayoutModeChange={setLayoutMode}
                    onTargetRatioChange={setTargetRatio}
                  />
                  <div className="flex gap-2">
                    <Button onClick={onCompose} disabled={busy}>
                      <Sparkles className="h-4 w-4" />
                      {busy ? "生成中..." : "生成组合图"}
                    </Button>
                    <Button variant="outline" onClick={onCompose} disabled={busy}>
                      <RefreshCw className="h-4 w-4" />
                      换一个布局
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 步骤 4：结果 */}
            {resultUrl && (
              <Card>
                <CardHeader>
                  <CardTitle>组合结果</CardTitle>
                  <CardDescription>预览组合效果，可下载后手动上传到首页进行 AI 生图。</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResultPanel resultUrl={resultUrl} onDownload={onDownload} onBack={onBack} />
                </CardContent>
              </Card>
            )}
          </>
        ) : (
          <>
            {/* 批量模式 - 步骤 1：上传多张图 */}
            <Card>
              <CardHeader>
                <CardTitle>步骤 1：上传多张白底物品图</CardTitle>
                <CardDescription>
                  可一次上传多张图，每张图独立检测物品并生成多种布局变体。总结果上限 100 张。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ComposeUploader
                  multiple
                  imageUrls={batchUrls}
                  fileInputRef={batchFileInputRef}
                  onFilesSelect={onBatchFilesSelect}
                  onRemoveAt={onBatchRemoveAt}
                />
                {batchFiles.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={onBatchDetect} disabled={batchDetecting}>
                      <ScanSearch className="h-4 w-4" />
                      {batchDetecting ? "识别中..." : `批量识别（${batchFiles.length} 张）`}
                    </Button>
                    <Button variant="outline" onClick={onBatchReset} disabled={batchDetecting}>
                      清空
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 批量模式 - 步骤 2：检测结果汇总 */}
            {batchObjects.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>步骤 2：检测结果汇总</CardTitle>
                  <CardDescription>
                    {batchFiles.length} 张图共检测到 {batchObjects.reduce((s, o) => s + o.length, 0)} 个物品。
                    角度已通过 VLM 分两步自动校正。
                    {batchObjects.every((objs) => objs.length === 1)
                      ? "单物品将生成 2 种摆放变体（竖放 + 横放）。"
                      : "多物品将枚举多种布局变体（横排/竖排/网格等）。"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {batchObjects.map((objs, imgIdx) => (
                      <div
                        key={imgIdx}
                        className="rounded-lg border border-border/80 bg-card/50 p-3"
                      >
                        <div className="mb-2 flex items-center gap-2">
                          <span className="rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
                            图 {imgIdx + 1}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {batchDetectSources[imgIdx] === "vlm" ? "VLM" : "本地"} · {objs.length} 个物品
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {objs.map((obj, i) => (
                            <span
                              key={i}
                              className="rounded bg-muted px-1.5 py-0.5 text-[10px]"
                              title={obj.label}
                            >
                              {obj.label}
                              {obj.suggested_rotation !== 0 && (
                                <span className="ml-0.5 text-primary">↻{obj.suggested_rotation}°</span>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 批量模式 - 步骤 3：参数设置 + 生成 */}
            {allBatchDetected && (
              <Card>
                <CardHeader>
                  <CardTitle>步骤 3：批量生成参数</CardTitle>
                  <CardDescription>
                    设置每张图的布局变体数和布局参数，然后批量生成。角度已自动校正。
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <BatchControls
                    maxCount={maxCount}
                    layoutMode={batchLayoutMode}
                    targetRatio={batchTargetRatio}
                    onMaxCountChange={setMaxCount}
                    onLayoutModeChange={setBatchLayoutMode}
                    onTargetRatioChange={setBatchTargetRatio}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={onBatchCompose} disabled={busy}>
                      <Sparkles className="h-4 w-4" />
                      {busy ? "生成中..." : `批量生成（最多 ${batchFiles.length * maxCount} 张）`}
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      预计最多 {batchFiles.length} × {maxCount} = {batchFiles.length * maxCount} 张布局变体
                    </span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 批量模式 - 步骤 4：结果网格 */}
            {batchResults.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>批量组合结果</CardTitle>
                  <CardDescription>
                    共 {batchResults.length} 张组合图，可单张下载或全部打包下载。
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <BatchResultGrid
                    results={batchResults}
                    onDownloadOne={onBatchDownloadOne}
                    onDownloadAllZip={onBatchDownloadAllZip}
                    zipping={zipping}
                  />
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </main>
  );
}
