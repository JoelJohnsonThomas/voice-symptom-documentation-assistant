import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { registerVoxDocSW } from "./pwa/registerSW";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

if (import.meta.env.DEV) {
  void import("@axe-core/react").then(({ default: axe }) => {
    axe(React, ReactDOM, 1000);
  });
}

if (!import.meta.env.DEV) {
  registerVoxDocSW();
}
