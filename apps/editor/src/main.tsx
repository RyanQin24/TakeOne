import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/takeone-tokens.css";
import "./styles/app.css";

const container = document.getElementById("root");
if (!container) throw new Error("The editor needs a #root element to mount into");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
