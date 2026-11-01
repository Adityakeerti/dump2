import {
  type AudioPlayer,
  createAudioPlayer,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, Platform } from "react-native";
import { errorMessage } from "../api/client";
import { agentApi } from "../api/endpoints";
import { absoluteUrl } from "../config";
import { storage } from "../utils/storage";

/** Persisted speaker preference (Invariant 3: the citizen can always mute the agent's voice). */
const AUTO_PLAY_KEY = "voice_auto_play_enabled";

export type VoiceState = "idle" | "recording" | "transcribing";

/**
 * Voice I/O for the agent chat:
 *  - tap-to-record -> upload to /api/agent/voice (Sarvam saaras:v3 / Groq Whisper) -> transcript
 *  - reply playback via /api/agent/tts/clips (Sarvam bulbul:v3) unless the speaker is muted
 */
export function useVoice(language: string) {
  // Metering on: the UI draws waves that follow the citizen's voice level.
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });
  /** 0..1 live input level while recording (drives the wave animation). */
  const level = useRef(new Animated.Value(0)).current;
  const [state, setState] = useState<VoiceState>("idle");
  const [autoPlay, setAutoPlay] = useState(true);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const player = useRef<AudioPlayer | null>(null);
  // Bumped on every speak/stop/unmount: a clip that finishes downloading after it was superseded or
  // stopped must never start playing.
  const speakSeq = useRef(0);

  useEffect(() => {
    void storage.getItem(AUTO_PLAY_KEY).then((v) => v !== null && setAutoPlay(v === "1"));
    return () => {
      speakSeq.current++;
      player.current?.remove();
      player.current = null;
    };
  }, []);

  const stopSpeaking = useCallback(() => {
    speakSeq.current++;
    player.current?.pause();
    player.current?.remove();
    player.current = null;
    setSpeakingId(null);
  }, []);

  const toggleAutoPlay = useCallback(() => {
    setAutoPlay((prev) => {
      const next = !prev;
      void storage.setItem(AUTO_PLAY_KEY, next ? "1" : "0");
      // Best-effort server copy so the preference follows the citizen across devices.
      void agentApi.setAudioPreference({ auto_play: next, preferred_speaker: "aditya" }).catch(() => undefined);
      if (!next) stopSpeaking();
      return next;
    });
  }, [stopSpeaking]);

  /** Set (not toggle) the speaker preference, e.g. when the main agent is asked to mute. */
  const setAutoPlayPref = useCallback(
    (next: boolean) => {
      setAutoPlay(next);
      void storage.setItem(AUTO_PLAY_KEY, next ? "1" : "0");
      if (!next) stopSpeaking();
    },
    [stopSpeaking],
  );

  /** Speak one message. Throws only for unexpected errors; TTS outages degrade to text silently. */
  const speak = useCallback(
    async (id: string, text: string) => {
      stopSpeaking();
      const seq = ++speakSeq.current;
      setSpeakingId(id);
      try {
        const clip = await agentApi.speak(text, language);
        if (seq !== speakSeq.current) return; // stopped or replaced while the clip was being made
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
        if (seq !== speakSeq.current) return;
        const p = createAudioPlayer({ uri: absoluteUrl(clip.url) });
        player.current = p;
        p.addListener("playbackStatusUpdate", (s) => {
          if (s.didJustFinish) setSpeakingId((cur) => (cur === id ? null : cur));
        });
        p.play();
      } catch {
        if (seq === speakSeq.current) setSpeakingId(null);
      }
    },
    [language, stopSpeaking],
  );

  const startRecording = useCallback(async (): Promise<string | null> => {
    const perm = await requestRecordingPermissionsAsync();
    if (!perm.granted) return "Microphone permission is needed to talk to the assistant.";
    stopSpeaking();
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setState("recording");
    return null;
  }, [recorder, stopSpeaking]);

  // Poll the recorder's level (dBFS, about -60..0) and ease the shared Animated value towards it.
  useEffect(() => {
    if (state !== "recording") {
      Animated.timing(level, { toValue: 0, duration: 250, useNativeDriver: true }).start();
      return;
    }
    const id = setInterval(() => {
      const db = recorder.getStatus().metering;
      const v = typeof db === "number" ? Math.max(0, Math.min(1, (db + 55) / 50)) : 0.5;
      Animated.timing(level, { toValue: v, duration: 110, useNativeDriver: true }).start();
    }, 110);
    return () => clearInterval(id);
  }, [state, recorder, level]);

  /** Stops recording and returns the transcript (or throws with a user-facing message). */
  const stopAndTranscribe = useCallback(async (): Promise<string> => {
    await recorder.stop();
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
    const uri = recorder.uri;
    if (!uri) {
      setState("idle");
      throw new Error("No audio was captured");
    }
    setState("transcribing");
    try {
      const form = new FormData();
      if (Platform.OS === "web") {
        const blob = await (await fetch(uri)).blob();
        const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
        form.append("file", blob, `voice.${ext}`);
      } else {
        // React Native's FormData streams the file from disk given { uri, name, type }.
        form.append("file", { uri, name: "voice.m4a", type: "audio/m4a" } as unknown as Blob);
      }
      if (language === "hi" || language === "en") form.append("language", language);
      const res = await agentApi.transcribe(form);
      if (!res.text?.trim()) throw new Error("I couldn't hear anything — please try again");
      return res.text.trim();
    } catch (e) {
      throw new Error(errorMessage(e));
    } finally {
      setState("idle");
    }
  }, [language, recorder]);

  const cancelRecording = useCallback(async () => {
    if (state === "recording") await recorder.stop().catch(() => undefined);
    setState("idle");
  }, [recorder, state]);

  return { state, level, autoPlay, toggleAutoPlay, setAutoPlayPref, speak, stopSpeaking, speakingId, startRecording, stopAndTranscribe, cancelRecording };
}
