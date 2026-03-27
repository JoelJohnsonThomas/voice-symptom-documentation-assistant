import { useCallback, useRef } from "react";
import { useSessionStore } from "../stores/sessionStore";

interface UseAudioRecorderOptions {
  onAudioData?: (blob: Blob) => void;
  onAudioLevel?: (level: number) => void;
  mimeType?: string;
  timeslice?: number;
}

export function useAudioRecorder(options: UseAudioRecorderOptions = {}) {
  const {
    onAudioData,
    onAudioLevel,
    mimeType = "audio/webm;codecs=opus",
    timeslice = 250,
  } = options;

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number>(0);

  const {
    isRecording,
    isPaused,
    startRecording: setStarted,
    stopRecording: setStopped,
    pauseRecording: setPaused,
    resumeRecording: setResumed,
    setRecordingDuration,
    setAudioLevel,
  } = useSessionStore();

  const monitorAudioLevel = useCallback(
    (analyser: AnalyserNode) => {
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const v = ((data[i] ?? 128) - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / data.length);
        const level = Math.min(1, rms * 3);
        setAudioLevel(level);
        onAudioLevel?.(level);
        animFrameRef.current = requestAnimationFrame(tick);
      };
      tick();
    },
    [setAudioLevel, onAudioLevel]
  );

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Audio analyser
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      // MediaRecorder
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          onAudioData?.(e.data);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start(timeslice);
      setStarted();

      // Duration timer
      timerRef.current = window.setInterval(() => {
        const store = useSessionStore.getState();
        if (!store.isPaused) {
          setRecordingDuration(store.recordingDuration + 1);
        }
      }, 1000);

      monitorAudioLevel(analyser);
    } catch (err) {
      console.error("Microphone access denied:", err);
      throw err;
    }
  }, [mimeType, timeslice, onAudioData, setStarted, setRecordingDuration, monitorAudioLevel]);

  const stop = useCallback((): Promise<Blob> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(new Blob(chunksRef.current, { type: mimeType }));
        return;
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        resolve(blob);
      };

      recorder.stop();
      setStopped();

      // Cleanup
      streamRef.current?.getTracks().forEach((t) => t.stop());
      cancelAnimationFrame(animFrameRef.current);
      clearInterval(timerRef.current);
      setAudioLevel(0);
    });
  }, [mimeType, setStopped, setAudioLevel]);

  const pause = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.pause();
      setPaused();
    }
  }, [setPaused]);

  const resume = useCallback(() => {
    if (mediaRecorderRef.current?.state === "paused") {
      mediaRecorderRef.current.resume();
      setResumed();
    }
  }, [setResumed]);

  return { start, stop, pause, resume, isRecording, isPaused };
}
