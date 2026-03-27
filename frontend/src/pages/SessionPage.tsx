import { useState, useCallback } from "react";
import { Header } from "../components/layout/Header";
import { VoiceCard } from "../components/voice/VoiceCard";
import { TextInputCard } from "../components/voice/TextInputCard";
import { ImageUploadCard } from "../components/voice/ImageUploadCard";
import { LiveTranscript } from "../components/voice/LiveTranscript";
import { PipelineProgress } from "../components/voice/PipelineProgress";
import { ExportBar } from "../components/voice/ExportBar";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useTranscribeWebSocket } from "../hooks/useTranscribeWebSocket";
import { useSOAPStream } from "../hooks/useSOAPStream";
import { useSessionStore } from "../stores/sessionStore";

export default function SessionPage() {
  const [partialText, setPartialText] = useState("");
  const { transcript, isProcessing, pipelineStages, currentStage, documentation } =
    useSessionStore();

  const transcribeWS = useTranscribeWebSocket({
    onPartialTranscript: setPartialText,
    onFinalTranscript: () => setPartialText(""),
  });

  const soapStream = useSOAPStream();

  const recorder = useAudioRecorder({
    onAudioData: (blob) => transcribeWS.sendAudio(blob),
  });

  const handleStart = useCallback(async () => {
    transcribeWS.connect();
    await recorder.start();
  }, [recorder, transcribeWS]);

  const handleStop = useCallback(async () => {
    const audioBlob = await recorder.stop();
    transcribeWS.disconnect();

    // Trigger SOAP processing
    const sessionId = crypto.randomUUID();
    soapStream.connect(sessionId);
  }, [recorder, transcribeWS, soapStream]);

  const handleTextSubmit = useCallback(
    (text: string) => {
      useSessionStore.getState().setTranscript(
        transcript ? `${transcript}\n${text}` : text
      );
    },
    [transcript]
  );

  const handleImageUpload = useCallback((file: File) => {
    console.log("Image uploaded:", file.name);
  }, []);

  return (
    <>
      <Header
        title="Voice Assistant"
        subtitle="Record and document"
        actions={
          documentation && (
            <ExportBar
              onExportJSON={() => {}}
              onExportPDF={() => {}}
              onExportFHIR={() => {}}
              onPushEHR={() => {}}
            />
          )
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Left column — Voice input */}
            <div className="space-y-4">
              <VoiceCard
                onStart={handleStart}
                onStop={handleStop}
                onPause={recorder.pause}
                onResume={recorder.resume}
              />
              <TextInputCard onSubmit={handleTextSubmit} />
              <ImageUploadCard onUpload={handleImageUpload} />
            </div>

            {/* Right column — Transcript + processing */}
            <div className="space-y-4">
              <LiveTranscript
                transcript={transcript}
                partialText={partialText}
                isListening={recorder.isRecording}
              />
              {isProcessing && (
                <PipelineProgress
                  stages={pipelineStages}
                  currentStage={currentStage}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
