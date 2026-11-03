import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Fontes empacotadas no build (o painel funciona sem acesso ao Google Fonts).
import "@fontsource/archivo/latin-400.css";
import "@fontsource/archivo/latin-500.css";
import "@fontsource/archivo/latin-600.css";
import "@fontsource/archivo/latin-700.css";
import "@fontsource/lora/latin-500.css";
import "@fontsource/lora/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
