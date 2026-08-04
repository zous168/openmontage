import {createRoot} from "react-dom/client";
import {StrictMode} from "react";
import "@xyflow/react/dist/style.css";
import "./flow.css";
import {FlowView} from "./FlowView";

const root = document.getElementById("flow-root")!;
createRoot(root).render(
  <StrictMode>
    <FlowView />
  </StrictMode>,
);
