import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Props = {
  layoutMode: string;
  targetRatio: string;
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

export function LayoutSelector({
  layoutMode,
  targetRatio,
  onLayoutModeChange,
  onTargetRatioChange,
}: Props) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
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
