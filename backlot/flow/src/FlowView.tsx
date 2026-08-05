import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  useEdgesState,
  useNodesState,
  type EdgeChange,
  type NodeChange,
  type EdgeTypes,
  type NodeTypes,
  type Viewport,
  type XYPosition,
} from "@xyflow/react";
import type {BoardState, ProjectSettings} from "./types";
import {getJSON, patchJSON, postJSON} from "./api";
import {buildGraph, INPUT_NODE_ID} from "./graph";
import {FlowEdge} from "./FlowEdge";
import {StageNode} from "./StageNode";
import {InputNode} from "./InputNode";
import {StageDrawer} from "./StageDrawer";
import {FlowProgressBar} from "./FlowProgressBar";
import {FlowEdgeLegend} from "./FlowEdgeLegend";
import {maybeAutoRunNextStage} from "./runControl";
import {STRINGS} from "./labels";

const nodeTypes: NodeTypes = {stage: StageNode, projectInput: InputNode};
const edgeTypes: EdgeTypes = {flow: FlowEdge};
const LAYOUT_SAVE_MS = 500;

function projectIdFromPath(): string {
  const m = window.location.pathname.match(/\/flow\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

function applySavedLayout(
  layoutRef: {current: Map<string, XYPosition>},
  stages: Record<string, {x?: number; y?: number}> | undefined,
) {
  for (const [name, pos] of Object.entries(stages ?? {})) {
    if (!pos || typeof pos !== "object") continue;
    const x = Number(pos.x);
    const y = Number(pos.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    layoutRef.current.set(name, {x, y});
  }
}

export function FlowView() {
  const projectId = useMemo(projectIdFromPath, []);
  const [state, setState] = useState<BoardState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [didInit, setDidInit] = useState(false);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [projectSettings, setProjectSettings] = useState<ProjectSettings | null>(null);
  const [savedViewport, setSavedViewport] = useState<Viewport | null>(null);
  const layoutRef = useRef<Map<string, XYPosition>>(new Map());
  const viewportRef = useRef<Viewport | null>(null);
  const draggingRef = useRef(false);
  const layoutLoadedRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    const s = await getJSON(`/api/project/${encodeURIComponent(projectId)}/state`);
    setState(s);
    setError(null);
    setLoading(false);
  }, [projectId]);

  const persistLayout = useCallback(async () => {
    if (!projectId || !layoutLoadedRef.current) return;
    const stages: Record<string, XYPosition> = {};
    for (const [name, pos] of layoutRef.current.entries()) {
      stages[name] = pos;
    }
    const body: {stages: Record<string, XYPosition>; viewport?: Viewport} = {stages};
    const vp = viewportRef.current;
    if (vp) body.viewport = vp;
    try {
      await patchJSON(`/api/project/${encodeURIComponent(projectId)}/flow-layout`, body);
    } catch {
      /* 布局保存失败时不打断编辑 */
    }
  }, [projectId]);

  const schedulePersistLayout = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      void persistLayout();
    }, LAYOUT_SAVE_MS);
  }, [persistLayout]);

  const persistLayoutRef = useRef(persistLayout);
  persistLayoutRef.current = persistLayout;

  useEffect(() => {
    if (!projectId) {
      setLoading(false);
      setError("URL 缺少项目 ID: /flow/{project_id}");
      return;
    }
    let cancelled = false;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const staticMode = new URLSearchParams(window.location.search).has("static");

    const boot = async () => {
      setLoading(true);
      setError(null);
      const [s, layout, ps] = await Promise.all([
        getJSON(`/api/project/${encodeURIComponent(projectId)}/state`),
        getJSON(`/api/project/${encodeURIComponent(projectId)}/flow-layout`).catch(() => ({stages: {}})),
        getJSON(`/api/project/${encodeURIComponent(projectId)}/settings`).catch(() => null),
      ]);
      if (cancelled) return;
      if (ps) {
        setProjectSettings(ps);
        const pi = ps.production_inputs ?? {};
        setSettings((prev) => ({
          ...prev,
          ...(pi.preferred_video_provider != null
            ? {preferred_video_provider: pi.preferred_video_provider}
            : {}),
        }));
      }
      applySavedLayout(layoutRef, layout?.stages);
      if (layout?.viewport && typeof layout.viewport === "object") {
        const x = Number(layout.viewport.x);
        const y = Number(layout.viewport.y);
        const zoom = Number(layout.viewport.zoom);
        if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(zoom)) {
          const vp = {x, y, zoom};
          viewportRef.current = vp;
          setSavedViewport(vp);
        }
      }
      layoutLoadedRef.current = true;
      setState(s);
      setError(null);
      setLoading(false);
    };

    boot().catch((e) => {
      if (cancelled) return;
      setLoading(false);
      setError(String((e as Error).message || e));
    });

    if (!staticMode) {
      es = new EventSource(`/api/project/${encodeURIComponent(projectId)}/events`);
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data?.type !== "change") return;
        } catch {
          return;
        }
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => {
          refresh().catch((e) => setError(String((e as Error).message || e)));
        }, 250);
      };
      es.onerror = () => {
        /* SSE 断开不影响已加载状态；下次 refresh 会重试 */
      };
    }

    return () => {
      cancelled = true;
      es?.close();
      if (timer) clearTimeout(timer);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      void persistLayoutRef.current();
    };
  }, [projectId, refresh]);

  const onOpen = useCallback((name: string) => setSelected(name), []);

  const onNodeDragStop = useCallback(
    (_: unknown, node: {id: string; position: XYPosition}) => {
      const stageName = node.id.replace(/^n_/, "");
      if (stageName) layoutRef.current.set(stageName, node.position);
      schedulePersistLayout();
    },
    [schedulePersistLayout],
  );

  const graph = useMemo(
    () => (state ? buildGraph(state, layoutRef, selected, onOpen, projectSettings) : {nodes: [], edges: []}),
    [state, selected, onOpen, projectSettings],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let dragEnded = false;
      for (const change of changes) {
        if (change.type !== "position") continue;
        draggingRef.current = change.dragging ?? false;
        if (!change.dragging && change.position) {
          const stageName = change.id.replace(/^n_/, "");
          if (stageName) layoutRef.current.set(stageName, change.position);
          dragEnded = true;
        }
      }
      onNodesChange(changes);
      if (dragEnded) schedulePersistLayout();
    },
    [onNodesChange, schedulePersistLayout],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);
    },
    [onEdgesChange],
  );

  const handleMoveEnd = useCallback(
    (_: unknown, viewport: Viewport) => {
      viewportRef.current = viewport;
      schedulePersistLayout();
    },
    [schedulePersistLayout],
  );

  // SSE 刷新时合并最新阶段状态,拖拽过程中不打断用户摆放
  useEffect(() => {
    if (draggingRef.current) return;
    setNodes((current) =>
      graph.nodes.map((gn) => {
        const prev = current.find((n) => n.id === gn.id);
        if (!prev) return gn;
        return {
          ...prev,
          ...gn,
          position: prev.position,
          data: gn.data,
          selected: gn.selected,
        };
      }),
    );
    setEdges(graph.edges);
  }, [graph, setNodes, setEdges]);

  // 批准后或 SSE 刷新：若下一阶段仍 pending，自动启动（与 board.js 一致）
  useEffect(() => {
    if (!state) return;
    void maybeAutoRunNextStage(state, refresh);
  }, [state, refresh]);

  // 选中态:输入节点(特殊)或阶段节点
  const isInputSelected = selected === INPUT_NODE_ID;
  const selectedStage = isInputSelected ? null : (state?.stages?.find((s) => s.name === selected) ?? null);

  const resetPipeline = async () => {
    if (!window.confirm(STRINGS.resetConfirm)) return;
    try {
      await postJSON(`/api/project/${encodeURIComponent(projectId)}/pipeline/reset`, {});
      refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  };

  if (error && !state) {
    return (
      <div className="fs-page fs-empty">
        <div className="fs-empty-title">{error}</div>
        <div className="fs-empty-actions">
          <a className="fs-link" href="/">← {STRINGS.back}项目库</a>
          {projectId && <a className="fs-link" href={`/p/${encodeURIComponent(projectId)}`}>{STRINGS.openBoard}</a>}
          <button className="fs-btn" onClick={() => { setError(null); refresh().catch((e) => setError(String((e as Error).message || e))); }}>
            {STRINGS.retry}
          </button>
        </div>
      </div>
    );
  }

  if (loading && !state) {
    return <div className="fs-page fs-empty">{STRINGS.loadingProject}</div>;
  }

  if (!state) {
    return (
      <div className="fs-page fs-empty">
        <div className="fs-empty-title">{STRINGS.loadFailed}</div>
        {error && <div className="fs-muted">{error}</div>}
        <div className="fs-empty-actions">
          <a className="fs-link" href="/">← {STRINGS.back}项目库</a>
          {projectId && <a className="fs-link" href={`/p/${encodeURIComponent(projectId)}`}>{STRINGS.openBoard}</a>}
          <button className="fs-btn" onClick={() => { setLoading(true); setError(null); refresh().catch((e) => setError(String((e as Error).message || e))); }}>
            {STRINGS.retry}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fs-page">
      {/* 顶部工具栏 */}
      <div className="fs-toolbar">
        <a className="fs-link" href="/">← {STRINGS.back}</a>
        <a className="fs-link" href={`/p/${encodeURIComponent(projectId)}`}>{STRINGS.switchToBoard}</a>
        <span className="fs-title">{state.title ?? projectId}</span>
        {state.pipeline?.label_zh && <span className="fs-chip">{state.pipeline.label_zh}</span>}
        <span className={`fs-live${state.live ? " live" : ""}`}>{state.live ? "● live" : "○ idle"}</span>
        <FlowProgressBar state={state} />
        <FlowEdgeLegend />
        <span className="fs-spacer" />
        <button className="fs-btn fs-btn--danger" onClick={resetPipeline}>{STRINGS.resetPipeline}</button>
      </div>

      {/* 流程图 */}
      <div className="fs-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          fitView={!didInit && !savedViewport}
          fitViewOptions={{padding: 0.2}}
          defaultViewport={savedViewport ?? undefined}
          onInit={() => setDidInit(true)}
          onNodeClick={(_, n) => {
            const name =
              (n.data as {kind?: string}).kind === "input"
                ? INPUT_NODE_ID
                : (n.data as {stage?: {name?: string}}).stage?.name ?? null;
            if (name) setSelected(name);
          }}
          onPaneClick={() => setSelected(null)}
          onNodeDragStop={onNodeDragStop}
          onMoveEnd={handleMoveEnd}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          panOnDrag
          panOnScroll
          zoomOnScroll
          zoomOnPinch
          defaultEdgeOptions={{markerEnd: {type: MarkerType.ArrowClosed}, style: {strokeWidth: 2}}}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{hideAttribution: false}}
        >
          <Background gap={28} size={1.5} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {/* 底部操作框(RunHub 式,选中节点浮出) */}
      {(selectedStage || isInputSelected) && (
        <StageDrawer
          state={state}
          stage={selectedStage}
          isInput={isInputSelected}
          projectSettings={projectSettings}
          settings={settings}
          onSettingsChange={setSettings}
          onClose={() => setSelected(null)}
          onChanged={() => refresh().catch((e) => setError(String((e as Error).message || e)))}
        />
      )}
    </div>
  );
}
