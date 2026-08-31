import { Check } from "lucide-react";
import type { WhiteImageItem } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

type GeneratedImageItem = {
  listIndex: number;
  displayIndex: number;
  jobId: string;
  imageUrl: string;
};

export type VideoRefLibraryTab = "main" | "detail" | "uploaded";

type DetailImageLibraryDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeTab: VideoRefLibraryTab;
  onTabChange: (tab: VideoRefLibraryTab) => void;
  generatedMainItems: GeneratedImageItem[];
  generatedDetailItems: GeneratedImageItem[];
  uploadedItems: WhiteImageItem[];
  selectedIndices: number[];
  onToggleSelection: (index: number) => void;
  onConfirm: () => void | Promise<void>;
};

function SelectableThumb({
  src,
  alt,
  selected,
  onClick,
}: {
  src: string;
  alt: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-lg border-2 p-1 transition-colors",
        selected ? "border-primary bg-primary/5" : "border-border bg-muted/30",
      )}
    >
      <img src={src} alt={alt} className="aspect-square w-full rounded object-cover" />
      {selected && (
        <span className="absolute inset-0 flex items-center justify-center bg-primary/20">
          <Check className="h-8 w-8 text-primary" />
        </span>
      )}
    </button>
  );
}

export function DetailImageLibraryDialog({
  open,
  onOpenChange,
  activeTab,
  onTabChange,
  generatedMainItems,
  generatedDetailItems,
  uploadedItems,
  selectedIndices,
  onToggleSelection,
  onConfirm,
}: DetailImageLibraryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>选择视频参考图</DialogTitle>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(v) => onTabChange(v as VideoRefLibraryTab)}
        >
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="main">已生成主图</TabsTrigger>
            <TabsTrigger value="detail">已生成详情图</TabsTrigger>
            <TabsTrigger value="uploaded">已上传参考图</TabsTrigger>
          </TabsList>

          <TabsContent value="main">
            {generatedMainItems.length > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                {generatedMainItems.map((item, index) => (
                  <SelectableThumb
                    key={`main-${item.jobId}-${item.listIndex}`}
                    src={item.imageUrl}
                    alt={`生成主图 ${item.displayIndex}`}
                    selected={selectedIndices.includes(index)}
                    onClick={() => onToggleSelection(index)}
                  />
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                暂无生成的主图，请先完成步骤二
              </p>
            )}
          </TabsContent>

          <TabsContent value="detail">
            {generatedDetailItems.length > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                {generatedDetailItems.map((item, index) => (
                  <SelectableThumb
                    key={`detail-${item.jobId}-${item.listIndex}`}
                    src={item.imageUrl}
                    alt={`生成详情图 ${item.displayIndex}`}
                    selected={selectedIndices.includes(index)}
                    onClick={() => onToggleSelection(index)}
                  />
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                暂无生成的详情图，请先完成步骤三
              </p>
            )}
          </TabsContent>

          <TabsContent value="uploaded">
            {uploadedItems.length > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                {uploadedItems.map((item, index) => (
                  <SelectableThumb
                    key={`uploaded-ref-${item.file.name}-${index}`}
                    src={item.url}
                    alt={`参考图 ${index + 1}`}
                    selected={selectedIndices.includes(index)}
                    onClick={() => onToggleSelection(index)}
                  />
                ))}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                暂无已上传参考图
              </p>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button
            type="button"
            className="w-full sm:w-auto"
            disabled={selectedIndices.length === 0}
            onClick={() => void onConfirm()}
          >
            确认选择（{selectedIndices.length} 张）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
