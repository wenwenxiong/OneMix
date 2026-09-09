import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Props = {
  maxCount: number;
  layoutMode: string;
  targetRatio: string;
  onMaxCountChange: (v: number) => void;
  onLayoutModeChange: (v: string) => void;
  onTargetRatioChange: (v: string) => void;
};

const LAYOUT_OPTIONS = [
  { value: "auto", label: "自动（推荐）" },
  { value: "horizontal", label: "全横排" },
  { value: "vertical", label: "全竖排" },
  { value: "2h1v", label: "2横1竖" },
  { value: "1h2v", label: "1横2竖" },
  { value: "grid", label: "网格" },
];

const RATIO_OPTIONS = [
  { value: "1:1", label: "1:1（正方形）" },
  { value: "3:4", label: "3:4（竖图）" },
  { value: "4:3", label: "4:3（横图）" },
];

export function BatchControls({
  maxCount,
  layoutMode,
  targetRatio,
  onMaxCountChange,
  onLayoutModeChange,
  onTargetRatioChange,
}: Props) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <div className="space-y-2">
        <Label>每图布局变体数</Label>
        <Input
          type="number"
          min={1}
          max={20}
          value={maxCount}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            if (!isNaN(v) && v >= 1 && v <= 20) onMaxCountChange(v);
          }}
          className="w-full"
        />
        <p className="text-xs text-muted-foreground">范围 1-20，每张图生成多种布局变体，总结果上限 100 张</p>
      </div>
      <div className="space-y-2">
        <Label>布局模式</Label>
        <Select value={layoutMode} onValueChange={onLayoutModeChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LAYOUT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>画布比例</Label>
        <Select value={targetRatio} onValueChange={onTargetRatioChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RATIO_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
