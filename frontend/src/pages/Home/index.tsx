import type { DragEvent } from "react";
import { useOneMixApp } from "@/hooks/useOneMixApp";
import { AppHeader } from "@/components/layout/AppHeader";
import { BusyOverlay } from "@/components/layout/BusyOverlay";
import { StepProgress } from "@/components/layout/StepProgress";
import { SettingsDialog } from "@/components/settings/SettingsDialog";
import { LogDialog } from "@/components/log/LogDialog";
import { ImagePreviewDialog } from "@/components/preview/ImagePreviewDialog";
import { OcrDialog } from "@/components/ocr/OcrDialog";
import { MainImageLibraryDialog } from "@/components/images/MainImageLibraryDialog";
import { DetailImageLibraryDialog } from "@/components/images/DetailImageLibraryDialog";
import { StepExtract } from "@/components/steps/StepExtract";
import { StepMain } from "@/components/steps/StepMain";
import { StepDetail } from "@/components/steps/StepDetail";
import { StepVideo } from "@/components/steps/StepVideo";
import {
  buildDetailResults,
  buildMainResults,
  buildVideoResults,
  previewErrorHandler,
} from "./helpers";

export default function Home() {
  const app = useOneMixApp();

  return (
    <main className="min-h-screen" aria-busy={app.busy}>
      <BusyOverlay busy={app.busy} />

      <ImagePreviewDialog
        url={app.previewImageUrl}
        name={app.previewImageName}
        onClose={app.onClosePreview}
      />

      <SettingsDialog
        open={app.showSettings}
        onOpenChange={app.setShowSettings}
        serverSettings={app.serverSettings}
        apiKey={app.apiKey}
        setApiKey={app.setApiKey}
        arkKey={app.arkKey}
        setArkKey={app.setArkKey}
        gptImageKey={app.gptImageKey}
        setGptImageKey={app.setGptImageKey}
        editingKey={app.editingKey}
        setEditingKey={app.setEditingKey}
        onSaveDashScope={app.onSaveKeyToServer}
        onClearDashScope={app.onClearServerKey}
        onSaveArk={app.onSaveArkKeyToServer}
        onClearArk={app.onClearArkServerKey}
        onSaveGptImage={app.onSaveGptImageKeyToServer}
        onClearGptImage={app.onClearGptImageServerKey}
        onSyncArkModels={app.onSyncArkSeedreamModels}
        onSyncQwenModels={app.onSyncQwenImageModels}
        syncingArkModels={app.syncingStrategies}
        syncingQwenModels={app.syncingStrategies}
        busy={app.busy}
      />

      <LogDialog open={app.showLog} onOpenChange={app.setShowLog} log={app.log} />

      <OcrDialog
        open={app.showOcrModal}
        onOpenChange={(open) => (open ? app.onOpenOcrModal() : app.onCloseOcrModal())}
        imageItems={app.ocrImageItems}
        result={app.ocrResult}
        onResultChange={app.setOcrResult}
        dragOver={app.isOcrDragOver}
        busy={app.busy}
        onDragEnter={app.onOcrDragEnter}
        onDragOver={app.onOcrDragOver}
        onDragLeave={app.onOcrDragLeave}
        onDrop={app.onOcrDrop}
        onFileInputChange={app.onOcrFileInputChange}
        onRemoveImage={app.onRemoveOcrImageAt}
        onRecognize={app.onOcrRecognize}
        onConfirm={app.onConfirmOcr}
      />

      <MainImageLibraryDialog
        open={app.showMainImageLibrary}
        onOpenChange={(open) =>
          open ? app.onOpenMainImageLibrary() : app.onCloseMainImageLibrary()
        }
        activeTab={app.activeImageTab}
        onTabGenerated={app.onMainImageTabGenerated}
        onTabUploaded={app.onMainImageTabUploaded}
        generatedItems={app.generatedMainItems}
        uploadedItems={app.whiteImageItems}
        selectedIndices={app.selectedMainImages}
        onToggleSelection={app.onToggleMainImageSelection}
        onConfirm={app.onConfirmMainImageLibrary}
      />

      <DetailImageLibraryDialog
        open={app.showDetailImageLibrary}
        onOpenChange={(open) =>
          open ? app.onOpenDetailImageLibrary() : app.onCloseDetailImageLibrary()
        }
        activeTab={app.activeDetailImageTab}
        onTabChange={app.onDetailImageTabChange}
        generatedMainItems={app.generatedMainItems}
        generatedDetailItems={app.generatedDetailItems}
        uploadedItems={app.detailWhiteImageItems}
        selectedIndices={app.selectedDetailImages}
        onToggleSelection={app.onToggleDetailImageSelection}
        onConfirm={app.onConfirmDetailImageLibrary}
      />

      <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8 md:py-10">
        <AppHeader
          onSettings={() => app.setShowSettings(true)}
          onLog={() => app.setShowLog(true)}
        />
        <StepProgress currentStep={app.currentStep} />

        {app.currentStep === 1 && (
          <StepExtract
            mergedText={app.mergedText}
            onMergedTextChange={app.setMergedText}
            keyJson={app.keyJson}
            resultViewMode={app.resultViewMode}
            onResultViewModeChange={app.setResultViewMode}
            busy={app.busy}
            onUploadTextFiles={app.onUploadTextFilesClick}
            onOpenOcr={app.onOpenOcrModal}
            onExtract={app.onExtractKeyInfo}
            onNext={() => app.setCurrentStep(2)}
          />
        )}

        {app.currentStep === 2 && (
          <StepMain
            name={app.name}
            strategy={app.strategy}
            nMainInput={app.nMainInput}
            onNameChange={app.setName}
            onStrategyChange={app.setStrategy}
            onCountChange={app.onNMainInputChange}
            strategyGroups={app.strategyGroups}
            syncingStrategies={app.syncingStrategies}
            onSyncStrategies={app.onSyncGenerationModels}
            whiteImageItems={app.whiteImageItems}
            isDragOver={app.isStep2DragOver}
            onDragEnter={app.onStep2DragEnter}
            onDragOver={app.onStep2DragOver}
            onDragLeave={app.onStep2DragLeave}
            onDrop={(e: DragEvent<HTMLDivElement>) => void app.onDropToWhites(e, "main")}
            onSelectWhiteFiles={app.onSelectWhiteFiles}
            onRemoveWhite={app.onRemoveWhiteFileAt}
            onReplaceWhite={app.onReplaceWhiteFileAt}
            onPreview={app.onOpenPreview}
            busy={app.busy}
            activePlanKind={app.activePlanKind}
            mainSlots={app.mainSlots}
            collapsePanel={app.collapseMainPanel}
            onToggleCollapse={() => app.setCollapseMainPanel((v) => !v)}
            onPlan={() => app.onPlanByKind("main")}
            onGenerateAll={() => app.onGenerate("main")}
            onDownloadZip={() => app.onDownloadZip("main")}
            onDownloadOneResult={(item) => app.onDownloadOneResult("main", item)}
            mainJob={app.mainJob}
            resultItems={buildMainResults(app.mainSlots, app.mainResultMap)}
            onMainResultDragStart={app.onMainResultDragStart}
            onAddGeneratedToWhites={(url, name) =>
              void app.addGeneratedImageToWhites("main", url, name)
            }
            getRefWhiteItems={app.getRefWhiteItems}
            getRefWhiteIndex={app.getRefWhiteIndex}
            onPromptChange={app.updateSlotPrompt}
            onRefChange={app.updateSlotRef}
            onAspectChange={app.updateSlotAspect}
            onResolutionChange={app.updateSlotResolution}
            onBatchImageSizeChange={(aspect, resolution) =>
              app.batchUpdateSlotImageSize("main", aspect, resolution)
            }
            onRefine={app.onRefineSlotPrompt}
            onGenerateOne={(i) => void app.onGenerate("main", [i])}
            onPreviewError={(slot, i) => previewErrorHandler(app, slot, i)}
            hasWhiteFiles={app.whiteFiles.length > 0}
            onBack={() => app.setCurrentStep(1)}
            onNext={() => app.setCurrentStep(3)}
          />
        )}

        {app.currentStep === 3 && (
          <StepDetail
            name={app.name}
            strategy={app.strategy}
            nDetailInput={app.nDetailInput}
            onNameChange={app.setName}
            onStrategyChange={app.setStrategy}
            onCountChange={app.onNDetailInputChange}
            strategyGroups={app.strategyGroups}
            syncingStrategies={app.syncingStrategies}
            onSyncStrategies={app.onSyncGenerationModels}
            detailWhiteImageItems={app.detailWhiteImageItems}
            isDragOver={app.isStep3DragOver}
            onDragEnter={app.onStep3DragEnter}
            onDragOver={app.onStep3DragOver}
            onDragLeave={app.onStep3DragLeave}
            onDrop={app.onStep3Drop}
            onSelectDetailWhiteFiles={app.onSelectDetailWhiteFiles}
            onRemoveDetailWhite={app.onRemoveDetailWhiteAt}
            onReplaceDetailWhite={app.onReplaceDetailWhiteAt}
            onOpenMainImageLibrary={app.onOpenMainImageLibrary}
            onPreview={app.onOpenPreview}
            busy={app.busy}
            activePlanKind={app.activePlanKind}
            detailSlots={app.detailSlots}
            collapsePanel={app.collapseDetailPanel}
            onToggleCollapse={() => app.setCollapseDetailPanel((v) => !v)}
            onPlan={() => app.onPlanByKind("detail")}
            onGenerateAll={() => app.onGenerate("detail")}
            onDownloadZip={() => app.onDownloadZip("detail")}
            onDownloadOneResult={(item) => app.onDownloadOneResult("detail", item)}
            detailJob={app.detailJob}
            resultItems={buildDetailResults(app.detailSlots, app.detailResultMap)}
            onDetailResultDragStart={app.onDetailResultDragStart}
            onAddGeneratedToWhites={(url, name) =>
              void app.addGeneratedImageToWhites("detail", url, name)
            }
            getRefWhiteItems={app.getRefWhiteItems}
            getRefWhiteIndex={app.getRefWhiteIndex}
            onPromptChange={app.updateSlotPrompt}
            onRefChange={app.updateSlotRef}
            onAspectChange={app.updateSlotAspect}
            onResolutionChange={app.updateSlotResolution}
            onBatchImageSizeChange={(aspect, resolution) =>
              app.batchUpdateSlotImageSize("detail", aspect, resolution)
            }
            onRefine={app.onRefineSlotPrompt}
            onGenerateOne={(i) => void app.onGenerate("detail", [i])}
            onPreviewError={(slot, i) => previewErrorHandler(app, slot, i)}
            canGenerate={app.detailWhiteFiles.length > 0 || app.whiteFiles.length > 0}
            onBack={() => app.setCurrentStep(2)}
            onNext={() => app.setCurrentStep(4)}
          />
        )}

        {app.currentStep === 4 && (
          <StepVideo
            name={app.name}
            strategy={app.videoStrategy}
            nVideoInput={app.nVideoInput}
            onNameChange={app.setName}
            onStrategyChange={app.setVideoStrategy}
            onCountChange={app.onNVideoInputChange}
            strategyGroups={app.videoStrategyGroups}
            videoRefImageItems={app.videoRefImageItems}
            isDragOver={app.isStep4DragOver}
            onDragEnter={app.onStep4DragEnter}
            onDragOver={app.onStep4DragOver}
            onDragLeave={app.onStep4DragLeave}
            onDrop={app.onStep4Drop}
            onSelectVideoRefFiles={app.onSelectVideoRefFiles}
            onRemoveVideoRef={app.onRemoveVideoRefAt}
            onReplaceVideoRef={app.onReplaceVideoRefAt}
            onOpenDetailImageLibrary={app.onOpenDetailImageLibrary}
            onPreview={app.onOpenPreview}
            busy={app.busy}
            activePlanKind={app.activePlanKind}
            videoSlots={app.videoSlots}
            collapsePanel={app.collapseVideoPanel}
            onToggleCollapse={() => app.setCollapseVideoPanel((v) => !v)}
            onPlan={() => app.onPlanByKind("video")}
            onGenerateAll={() => app.onGenerate("video")}
            onDownloadZip={() => app.onDownloadZip("video")}
            onDownloadOneResult={(item) => app.onDownloadOneResult("video", item)}
            videoJob={app.videoJob}
            resultItems={buildVideoResults(app.videoSlots, app.videoResultMap)}
            onVideoResultDragStart={app.onVideoResultDragStart}
            getRefWhiteItems={app.getRefWhiteItems}
            getRefWhiteIndex={app.getRefWhiteIndex}
            onPromptChange={app.updateSlotPrompt}
            onRefChange={app.updateSlotRef}
            onAspectChange={app.updateSlotAspect}
            onResolutionChange={app.updateSlotResolution}
            onBatchImageSizeChange={(aspect, resolution) =>
              app.batchUpdateSlotImageSize("video", aspect, resolution)
            }
            onRefine={app.onRefineSlotPrompt}
            onGenerateOne={(i) => void app.onGenerate("video", [i])}
            onPreviewError={(slot, i) => previewErrorHandler(app, slot, i)}
            canGenerate={
              app.videoRefFiles.length > 0 ||
              app.detailWhiteFiles.length > 0 ||
              app.whiteFiles.length > 0
            }
            canFinishPackage={
              Object.keys(app.mainResultRefs).length > 0 ||
              Object.keys(app.detailResultRefs).length > 0 ||
              Object.keys(app.videoResultRefs).length > 0
            }
            onBack={() => app.setCurrentStep(3)}
            onFinishPackage={app.onDownloadAllPackage}
          />
        )}
      </div>
    </main>
  );
}
