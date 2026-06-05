import React from "react";
import { createRoot } from "react-dom/client";
import Workspace from "./Workspace";
import { IdentityProvider } from "./state/IdentityProvider";
import "./theme.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <IdentityProvider>
      <Workspace />
    </IdentityProvider>
  </React.StrictMode>
);
