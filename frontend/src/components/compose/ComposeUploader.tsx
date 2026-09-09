import { type DragEvent, type RefObject } from "react";
import { Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  /** 单图模式的预览 URL（多图模式留空） */
  imageUrl?: string;
  /** 多图模式的预览 URL 列表 */
  imageUrls?: string[];
  fileInputRef: RefObject<HTMLInputElement | null>;
  /** 单图模式回调 */
  onFileSelect?: (file: File) => void;
  /** 多图模式回调 */
  onFilesSelect?: (files: File[]) => void;
  /** 单图模式移除 */
  onReset?: () => void;
  /** 多图模式移除指定索引 */
  onRemoveAt?: (index: number) => void;
  /** 是否多选模式 */
  multiple?: boolean;
};

export function ComposeUploader({
  imageUrl,
  imageUrls,
  fileInputRef,
  onFileSelect,
  onFilesSelect,
  onReset,
  onRemoveAt,
  multiple = false,
}: Props) {
  const onDragOver = (e: DragEvent<HTMLDivElement>) => e.preventDefault();
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files || []).filter((f) =>
      f.type.startsWith("image/"),
    );
    if (files.length === 0) return;
    if (multiple && onFilesSelect) {
      onFilesSelect(files);
    } else if (!multiple && onFileSelect) {
      onFileSelect(files[0]);
    }
  };

  const hasContent = multiple
    ? (imageUrls && imageUrls.length > 0)
    : !!imageUrl;

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef as React.RefObject<HTMLInputElement>}
        type="file"
        accept="image/*"
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length === 0) return;
          if (multiple && onFilesSelect) {
            onFilesSelect(files);
          } else if (!multiple && onFileSelect) {
            onFileSelect(files[0]);
          }
          // 清空 input value 以便重复选择同一文件
          e.target.value = "";
        }}
      />
      {!hasContent ? (
        <div
          onDragOver={onDragOver}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border/80 bg-muted/30 px-6 py-12 text-center transition hover:border-primary/50 hover:bg-muted/50"
        >
          <Upload className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">
            {multiple ? "点击或拖拽上传多张白底物品图" : "点击或拖拽上传白底物品图"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 JPG / PNG，{multiple ? "可多选" : "单张"}限 25MB
          </p>
        </div>
      ) : multiple ? (
        <div className="flex flex-wrap gap-3">
          {(imageUrls || []).map((url, i) => (
            <div key={i} className="relative">
              <img
                src={url}
                alt={`上传图 ${i + 1}`}
                className="h-32 w-32 rounded-lg border border-border/80 object-cover"
              />
              {onRemoveAt && (
                <Button
                  variant="destructive"
                  size="icon"
                  className="absolute right-1 top-1 h-6 w-6"
                  onClick={() => onRemoveAt(i)}
                  aria-label={`移除图 ${i + 1}`}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
              <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                {i + 1}
              </span>
            </div>
          ))}
          {/* 继续添加按钮 */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex h-32 w-32 items-center justify-center rounded-lg border-2 border-dashed border-border/80 text-muted-foreground transition hover:border-primary/50 hover:text-primary"
          >
            <Upload className="h-6 w-6" />
            <span className="ml-1 text-xs">继续添加</span>
          </button>
        </div>
      ) : (
        <div className="relative inline-block">
          <img
            src={imageUrl}
            alt="上传的物品图"
            className="max-h-80 rounded-lg border border-border/80 object-contain"
          />
          {onReset && (
            <Button
              variant="destructive"
              size="icon"
              className="absolute right-2 top-2 h-7 w-7"
              onClick={onReset}
              aria-label="移除图片"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
