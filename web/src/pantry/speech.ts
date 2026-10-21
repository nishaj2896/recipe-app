import { useEffect, useRef, useState } from "react";

/** The slice of the Web Speech API the app uses; TypeScript's DOM lib lacks it. */
interface Recognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface RecognitionResultEvent extends Event {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}

interface RecognitionErrorEvent extends Event {
  error: string;
}

type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | undefined {
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition;
}

/**
 * Indian English for any English speaker: it hears "paneer", "jeera" and
 * "toor dal" far better than US or UK English does.
 */
export function speechLanguage(language: string): string {
  return !language || language.toLowerCase().startsWith("en") ? "en-IN" : language;
}

export type Listening =
  | { state: "idle" }
  | { state: "listening"; heard: string }
  | { state: "blocked" }
  | { state: "failed" };

/**
 * One spoken sentence through the browser's speech recognition. Browsers
 * without it get `supported: false`, and the app shows no mic. `onSentence`
 * gets the final text once the speaker stops.
 */
export function useSpeech(onSentence: (sentence: string) => void) {
  const [listening, setListening] = useState<Listening>({ state: "idle" });
  const current = useRef<Recognition | null>(null);
  const latest = useRef(onSentence);
  useEffect(() => {
    latest.current = onSentence;
  });

  // Leaving the screen mid-sentence delivers nothing: abort() still fires
  // "end", and a late sentence would fill the pantry after the user has gone.
  const left = useRef(false);
  useEffect(
    () => () => {
      left.current = true;
      current.current?.abort();
    },
    [],
  );

  const Recognition = recognitionClass();

  function start() {
    if (!Recognition || current.current) return;
    const recognition = new Recognition();
    recognition.lang = speechLanguage(navigator.language);
    recognition.interimResults = true;
    recognition.continuous = false;
    let final = "";
    let failed = false;

    recognition.addEventListener("result", (event) => {
      const { results } = event as RecognitionResultEvent;
      let heard = "";
      final = "";
      for (const result of Array.from(results)) {
        const text = result[0]?.transcript ?? "";
        heard += text;
        if (result.isFinal) final += text;
      }
      setListening({ state: "listening", heard });
    });
    recognition.addEventListener("error", (event) => {
      const { error } = event as RecognitionErrorEvent;
      // Silence ends a turn quietly; anything else is worth saying.
      if (error === "no-speech" || error === "aborted") return;
      failed = true;
      setListening({
        state:
          error === "not-allowed" || error === "service-not-allowed"
            ? "blocked"
            : "failed",
      });
    });
    recognition.addEventListener("end", () => {
      current.current = null;
      if (failed || left.current) return;
      setListening({ state: "idle" });
      if (final.trim()) latest.current(final.trim());
    });

    current.current = recognition;
    setListening({ state: "listening", heard: "" });
    recognition.start();
  }

  function stop() {
    current.current?.stop();
  }

  return { supported: Recognition !== undefined, listening, start, stop };
}
