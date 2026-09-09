import { Download, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  resultUrl: string;
  onDownload: () => void;
  onBack: () => void;
};

export function ResultPanel({ resultUrl, onDownload, onBack }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex justify-center rounded-lg border border-border/80 bg-muted/20 p-4">
        <img
          src={resultUrl}
          alt="组合结果"
          className="max-h-96 rounded-lg object-contain"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={onDownload}>
          <Download className="h-4 w-4" />
          下载图片
        </Button>
        <Button variant="outline" onClick={onBack}>
          <Home className="h-4 w-4" />
          返回首页生图
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        提示：下载后可在首页「步骤二：生成主图」中上传此图作为白底参考图，继续 AI 生图流程。
      </p>
    </div>
  );
}
