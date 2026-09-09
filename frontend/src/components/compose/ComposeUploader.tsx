import { type DragEvent, type RefObject } from "react";
import { Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  imageUrl: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileSelect: (file: File) => void;
  onReset: () => void;
};

export function ComposeUploader({ imageUrl, fileInputRef, onFileSelect, onReset }: Props) {
  const onDragOver = (e: DragEvent<HTMLDivElement>) => e.preventDefault();
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith("image/")) onFileSelect(file);
  };

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef as React.RefObject<HTMLInputElement>}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelect(file);
        }}
      />
      {!imageUrl ? (
        <div
          onDragOver={onDragOver}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border/80 bg-muted/30 px-6 py-12 text-center transition hover:border-primary/50 hover:bg-muted/50"
        >
          <Upload className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">点击或拖拽上传白底物品图</p>
          <p className="text-xs text-muted-foreground">支持 JPG / PNG，单张限 25MB</p>
        </div>
      ) : (
        <div className="relative inline-block">
          <img
            src={imageUrl}
            alt="上传的物品图"
            className="max-h-80 rounded-lg border border-border/80 object-contain"
          />
          <Button
            variant="destructive"
            size="icon"
            className="absolute right-2 top-2 h-7 w-7"
            onClick={onReset}
            aria-label="移除图片"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
