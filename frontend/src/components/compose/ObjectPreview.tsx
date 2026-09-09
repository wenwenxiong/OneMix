import { RotateCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type DetectedObject = {
  bbox: [number, number, number, number];
  label: string;
  suggested_rotation: number;
};

type Props = {
  imageUrl: string;
  objects: DetectedObject[];
  rotations: number[];
  imgSize: { w: number; h: number };
  onRotationChange: (index: number, angle: number) => void;
};

const ANGLES = [0, 90, 180, 270];

export function ObjectPreview({
  imageUrl,
  objects,
  rotations,
  imgSize,
  onRotationChange,
}: Props) {
  return (
    <div className="space-y-4">
      {/* bbox 可视化叠加 */}
      <div className="relative inline-block">
        <img
          src={imageUrl}
          alt="物品检测预览"
          className="max-h-80 rounded-lg border border-border/80"
        />
        <svg
          className="pointer-events-none absolute left-0 top-0 h-full w-full"
          viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {objects.map((obj, i) => {
            const [x1, y1, x2, y2] = obj.bbox;
            const colors = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"];
            const color = colors[i % colors.length];
            return (
              <g key={i}>
                <rect
                  x={x1}
                  y={y1}
                  width={x2 - x1}
                  height={y2 - y1}
                  fill="none"
                  stroke={color}
                  strokeWidth={Math.max(2, imgSize.w * 0.004)}
                  strokeDasharray={`${imgSize.w * 0.01} ${imgSize.w * 0.006}`}
                />
                <text
                  x={x1}
                  y={y1 - imgSize.h * 0.01}
                  fill={color}
                  fontSize={Math.max(14, imgSize.h * 0.025)}
                  fontWeight="bold"
                >
                  {obj.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* 每个物品的旋转角度选择 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {objects.map((obj, i) => {
          const current = rotations[i] ?? 0;
          const suggested = obj.suggested_rotation ?? 0;
          const isAuto = current === suggested;
          const isModified = suggested !== 0 && current !== suggested;
          return (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg border border-border/80 bg-card/50 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="truncate text-sm font-medium">
                    {obj.label} #{i + 1}
                  </p>
                  {isAuto && suggested !== 0 && (
                    <Badge variant="secondary" className="shrink-0 gap-0.5 text-[10px]">
                      <Sparkles className="h-2.5 w-2.5" />
                      自动
                    </Badge>
                  )}
                  {isModified && (
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      已微调
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {obj.bbox[2] - obj.bbox[0]} × {obj.bbox[3] - obj.bbox[1]} px
                  {suggested !== 0 && (
                    <span className="ml-1 text-primary/70">（建议 {suggested}°）</span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <RotateCw className="h-3.5 w-3.5 text-muted-foreground" />
                <div className="flex gap-1">
                  {ANGLES.map((ang) => (
                    <Button
                      key={ang}
                      variant={current === ang ? "default" : "outline"}
                      size="sm"
                      className="h-7 px-2 text-xs"
                      onClick={() => onRotationChange(i, ang)}
                    >
                      {ang}°
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
