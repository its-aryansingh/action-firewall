"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type VoiceState = "idle" | "recording" | "listening" | "transcribing";

type SpeechAlternativeLike = { transcript: string };
type SpeechResultLike = {
  length: number;
  isFinal: boolean;
  [index: number]: SpeechAlternativeLike;
};
type SpeechResultListLike = {
  length: number;
  [index: number]: SpeechResultLike;
};
type SpeechEventLike = { results: SpeechResultListLike };
type SpeechErrorLike = { error: string };
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechEventLike) => void) | null;
  onerror: ((event: SpeechErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

function speechConstructor(): SpeechRecognitionConstructor | undefined {
  if (typeof window === "undefined") return undefined;
  const speechWindow = window as SpeechWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
}

function recorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find(
    (candidate) => MediaRecorder.isTypeSupported(candidate),
  );
}

export function VoiceIntentInput({
  aiConfigured,
  disabled,
  onTranscript,
}: {
  aiConfigured: boolean;
  disabled: boolean;
  onTranscript: (text: string) => void;
}) {
  const [state, setState] = useState<VoiceState>("idle");
  const [browserFallback, setBrowserFallback] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setBrowserFallback(Boolean(speechConstructor()));
    return () => {
      recognitionRef.current?.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
    };
  }, []);

  function finishStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current);
    stopTimerRef.current = null;
  }

  async function startOpenAIVoice() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      startBrowserVoice();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = recorderMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const audioType = recorder.mimeType || chunksRef.current[0]?.type || "audio/webm";
        const audio = new Blob(chunksRef.current, { type: audioType });
        finishStream();
        setState("transcribing");
        try {
          const transcript = await api.transcribeVoice(audio);
          onTranscript(transcript.text);
          setMessage("AI transcript added as editable intent. No authority was created.");
        } catch (caught) {
          setMessage(`AI transcription failed: ${String(caught)}`);
        } finally {
          setState("idle");
          recorderRef.current = null;
        }
      };
      recorder.start();
      setMessage(null);
      setState("recording");
      stopTimerRef.current = setTimeout(() => recorder.stop(), 20_000);
    } catch {
      setMessage("Microphone permission was denied. You can still type the purchase goal.");
      setState("idle");
      finishStream();
    }
  }

  function startBrowserVoice() {
    const Recognition = speechConstructor();
    if (!Recognition) {
      setMessage("Voice input is unavailable in this browser. Type the purchase goal instead.");
      return;
    }
    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-IN";
    recognition.onresult = (event) => {
      const parts: string[] = [];
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.length > 0) parts.push(result[0].transcript);
      }
      const transcript = parts.join(" ").trim();
      if (transcript) {
        onTranscript(transcript);
        setMessage("Voice transcript added as editable intent. No authority was created.");
      }
    };
    recognition.onerror = (event) => {
      setMessage(`Device speech input stopped: ${event.error}. You can type the goal instead.`);
    };
    recognition.onend = () => {
      setState("idle");
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    setMessage(null);
    setState("listening");
    recognition.start();
  }

  function toggle() {
    if (state === "recording") {
      recorderRef.current?.stop();
      return;
    }
    if (state === "listening") {
      recognitionRef.current?.stop();
      return;
    }
    if (state !== "idle") return;
    if (aiConfigured) void startOpenAIVoice();
    else startBrowserVoice();
  }

  const active = state === "recording" || state === "listening";
  const unavailable = !aiConfigured && !browserFallback;
  const buttonLabel =
    state === "transcribing"
      ? "Transcribing intent…"
      : active
        ? "Stop listening"
        : aiConfigured
          ? "Speak purchase intent"
          : "Use device voice";

  return (
    <div className="rounded-2xl border border-brand/25 bg-brand/[0.06] p-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={active ? "voice-button voice-button-active" : "voice-button"}
          onClick={toggle}
          disabled={disabled || state === "transcribing" || unavailable}
          aria-label={buttonLabel}
        >
          <span className="voice-icon" aria-hidden="true">●</span>
          <span>{buttonLabel}</span>
          {active && (
            <span className="voice-wave" aria-hidden="true">
              <i /><i /><i /><i />
            </span>
          )}
        </button>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-slate-100">
            {aiConfigured ? "OpenAI voice-to-intent" : "Keyless voice fallback"}
          </p>
          <p className="mt-0.5 text-[11px] leading-4 text-muted">
            Transcript becomes editable goal text only. It can never approve or pay.
          </p>
        </div>
        <span className="rounded-full border border-edge bg-ink/60 px-2.5 py-1 font-mono text-[10px] text-muted">
          {aiConfigured ? "AI READY" : browserFallback ? "DEVICE MODE" : "TEXT ONLY"}
        </span>
      </div>
      {message && (
        <p className="mt-2 border-t border-edge/60 pt-2 text-[11px] leading-4 text-muted" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
