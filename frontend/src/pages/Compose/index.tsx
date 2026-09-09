import { useCallback, useRef, useState } from "react";
import { ArrowLeft, ScanSearch, Sparkles, RefreshCw } from "lucide-react";
import { toast } from "sonner";
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
import { ThemeToggle } from "@/components/theme-toggle";

type DetectedObject = {
  bbox: [number, number, number, number];
  label: string;
  suggested_rotation: number;
};

type Props = {
  onBack: () => void;
  apiKey: string;
};

export default function ComposePage({ onBack, apiKey }: Props) {
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
      // 用 VLM 建议角度初始化（本地降级时全为 0）
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
                  ? "已根据包装文字方向自动建议旋转角度，可手动微调。"
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
      </div>
    </main>
  );
}
