import { useState, useMemo } from "react";

export function useApiKeys() {
  const [apiKey, setApiKey] = useState("");
  const [arkKey, setArkKey] = useState("");
  const [gptImageKey, setGptImageKey] = useState("");
  const headers = useMemo(() => {
    const h: Record<string, string> = {};
    if (apiKey.trim()) h["X-DashScope-Key"] = apiKey.trim();
    if (arkKey.trim()) h["X-Ark-Key"] = arkKey.trim();
    if (gptImageKey.trim()) h["X-OpenAI-Key"] = gptImageKey.trim();
    return h;
  }, [apiKey, arkKey, gptImageKey]);
  return {
    apiKey,
    setApiKey,
    arkKey,
    setArkKey,
    gptImageKey,
    setGptImageKey,
    headers,
  };
}