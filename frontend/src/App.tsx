import { useState } from "react";
import Home from "@/pages/Home";
import ComposePage from "@/pages/Compose";

type Page = "home" | "compose";

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [apiKey, setApiKey] = useState("");

  if (page === "compose") {
    return (
      <ComposePage
        apiKey={apiKey}
        onBack={() => setPage("home")}
      />
    );
  }
  return (
    <Home
      onNavigateCompose={() => setPage("compose")}
      onApiKeyChange={setApiKey}
    />
  );
}
