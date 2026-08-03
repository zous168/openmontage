/**
 * NLE live preview entry — used by Backlot's interactive timeline editor.
 *
 * Runs inside an iframe served by the preview-server webpack dev server.
 * Polls the Backlot NLE draft endpoint and feeds the current draft into
 * @remotion/player so timeline edits show up ~instantly.
 *
 * The Backlot API base is derived from document.referrer (the board page
 * embeds this iframe); falls back to localhost:4750 (BACKLOT default port).
 */
import {Player} from '@remotion/player';
import {createElement as h, useEffect, useRef, useState} from 'react';
import {registerRoot} from 'remotion';
import {Explainer} from './Explainer';

const POLL_MS = 1500;
const BACKLOT_FALLBACK = 'http://localhost:4750';

// Renderer families that map to the Explainer composition (see
// video_compose.RENDERER_FAMILY_MAP). Atelier/bespoke and presenter
// compositions have different props contracts — no NLE preview for them.
const EXPLAINER_FAMILIES = new Set([
  'explainer-data',
  'explainer-teacher',
  'product-reveal',
  'animation-first',
  'screen-demo',
]);

type DraftProps = {
  props: Record<string, unknown> | null;
  duration_seconds: number;
};

function apiBase(): string {
  try {
    const ref = document.referrer;
    if (ref) {
      const origin = new URL(ref).origin;
      if (origin) return origin;
    }
  } catch {
    // ignore malformed referrer
  }
  return BACKLOT_FALLBACK;
}

function durationFromCuts(cuts: Array<{out_seconds?: number}> | undefined): number {
  const lastEnd = (cuts ?? []).reduce((max, c) => Math.max(max, Number(c.out_seconds) || 0), 0);
  return lastEnd + 1;
}

function NlePreviewRoot() {
  const params = new URLSearchParams(window.location.search);
  const projectId = params.get('projectId') ?? '';
  const [draft, setDraft] = useState<DraftProps>({props: null, duration_seconds: 0});
  const [error, setError] = useState<string | null>(null);
  const lastJson = useRef('');

  useEffect(() => {
    if (!projectId) {
      setError('缺少 projectId 参数');
      return;
    }
    const url = `${apiBase()}/api/project/${encodeURIComponent(projectId)}/nle-edit/draft-props`;
    const poll = async () => {
      try {
        const res = await fetch(url, {cache: 'no-store'});
        if (!res.ok) {
          setError(`draft-props HTTP ${res.status}`);
          return;
        }
        const data = (await res.json()) as DraftProps;
        const json = JSON.stringify(data);
        if (json !== lastJson.current) {
          lastJson.current = json;
          setDraft(data);
          setError(null);
        }
      } catch (err) {
        setError(`无法连接 Backlot（${(err as Error).message}）`);
      }
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [projectId]);

  if (error && !draft.props) {
    return h('div', {style: {color: '#f87171', padding: 16, fontFamily: 'sans-serif'}}, error);
  }
  if (!draft.props) {
    return h(
      'div',
      {style: {display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontFamily: 'sans-serif', color: '#94a3b8', fontSize: 14}},
      '等待编辑草稿…（在时间线上拖拽 cut 后点「预览草稿」）',
    );
  }
  const props = draft.props as {
    cuts?: Array<{out_seconds?: number}>;
    renderer_family?: string;
    composition_mode?: string;
  };
  if (props.composition_mode === 'atelier' || !EXPLAINER_FAMILIES.has(props.renderer_family ?? '')) {
    return h(
      'div',
      {style: {display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontFamily: 'sans-serif', color: '#f59e0b', fontSize: 14, padding: 16, textAlign: 'center'}},
      `当前 composition（${props.renderer_family ?? '未知'}）不支持 NLE 实时预览`,
    );
  }
  // Prefer the server-computed duration; fall back to a local lastEnd+1.
  const duration = Math.max(
    1,
    draft.duration_seconds || durationFromCuts(props.cuts),
  );
  return h(
    'div',
    {style: {width: '100%', height: '100%', background: '#000'}},
    h(Player, {
      component: Explainer,
      inputProps: draft.props,
      fps: 30,
      durationInFrames: duration * 30,
      compositionWidth: 1280,
      compositionHeight: 720,
      style: {width: '100%', height: '100%'},
      controls: true,
      loop: true,
    }),
  );
}

registerRoot(NlePreviewRoot);
