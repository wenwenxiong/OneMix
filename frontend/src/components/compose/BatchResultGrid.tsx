import { Download, Package } from "lucide-react";
import { Button } from "@/components/ui/button";

type ResultItem = {
  url: string;
  filename: string;
  imageIndex: number;
};

type Props = {
  results: ResultItem[];
  onDownloadOne: (item: ResultItem) => void;
  onDownloadAllZip: () => void;
  zipping?: boolean;
};

export function BatchResultGrid({
  results,
  onDownloadOne,
  onDownloadAllZip,
  zipping = false,
}: Props) {
  if (results.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          共 {results.length} 张组合图
        </p>
        <Button onClick={onDownloadAllZip} disabled={zipping} size="sm">
          <Package className="h-4 w-4" />
          {zipping ? "打包中..." : "全部下载 ZIP"}
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {results.map((item, i) => (
          <div
            key={i}
            className="group relative overflow-hidden rounded-lg border border-border/80 bg-card"
          >
            <img
              src={item.url}
              alt={item.filename}
              className="aspect-square w-full object-contain"
            />
            <div className="flex items-center justify-between gap-1 px-2 py-1.5">
              <span className="truncate text-xs text-muted-foreground" title={item.filename}>
                {item.filename}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => onDownloadOne(item)}
                aria-label={`下载 ${item.filename}`}
              >
                <Download className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
