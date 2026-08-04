import {
  createContext,
  useContext,
  type Dispatch,
  type MutableRefObject,
  type RefObject,
  type SetStateAction,
} from "react";
import type { TimelineElement } from "../../player";
import type { CompositionLevel } from "./CompositionBreadcrumb";

/**
 * Context module kept free of Provider logic so Vite HMR does not recreate the
 * context object when NLEProvider hot-reloads (which breaks useNLEContext).
 */
export interface NLEContextValue {
  projectId: string;
  iframeRef: MutableRefObject<HTMLIFrameElement | null>;
  togglePlay: () => void;
  seek: (time: number, options?: { keepPlaying?: boolean }) => boolean;
  refreshPlayer: () => void;
  onIframeLoad: () => void;
  compositionStack: CompositionLevel[];
  updateCompositionStack: Dispatch<SetStateAction<CompositionLevel[]>>;
  handleNavigateComposition: (index: number) => void;
  handleDrillDown: (element: TimelineElement) => void;
  compIdToSrc: Map<string, string>;
  timelineH: number;
  setTimelineH: Dispatch<SetStateAction<number>>;
  persistTimelineH: (height: number) => void;
  containerRef: RefObject<HTMLDivElement | null>;
  compositionLoading: boolean;
  setCompositionLoading: (loading: boolean) => void;
  timelineDisabled: boolean;
  timelineSessionEpoch: number;
  hasLoadedOnceRef: MutableRefObject<boolean>;
  previewCompositionSize: { width: number; height: number } | null;
  setPreviewCompositionSize: (size: { width: number; height: number } | null) => void;
}

export const NLEContext = createContext<NLEContextValue | null>(null);

export function useNLEContext(): NLEContextValue {
  const ctx = useContext(NLEContext);
  if (!ctx) throw new Error("useNLEContext must be used within an NLEProvider");
  return ctx;
}
