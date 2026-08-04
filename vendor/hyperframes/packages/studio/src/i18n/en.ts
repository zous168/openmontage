/**
 * 英文语言包(默认)。键与 en.ts 一一对应。
 */
export const en: Record<string, string> = {
  // ---- StudioHeader ----
  'brand.hyperframes': 'Hyperframes',
  'view.studio': 'Studio view',
  'action.undo': 'Undo',
  'action.redo': 'Redo',
  'panel.inspector': 'Inspector',
  'action.captureFrame': 'Capture current frame',
  'action.capturingFrame': 'Capturing frame',

  // ---- TimelineToolbar ----
  'tool.selection': 'Selection tool (V)',
  'tool.selectionShort': 'Selection tool',
  'tool.razor': 'Razor tool (B) — Shift+click splits all tracks',
  'tool.razorShort': 'Razor tool',
  'action.toggleSnapping': 'Toggle timeline snapping',
  'tool.snappingOn': 'Snapping on (N)',
  'tool.snappingOff': 'Snapping off (N)',
  'action.autoRecordKeyframes': 'Auto-record manual edits as keyframes',
  'action.splitAtPlayhead': 'Split at playhead',
  'action.addBeatAtPlayhead': 'Add beat at playhead',
  'action.fitTimeline': 'Fit timeline to width',
  'action.zoomOut': 'Zoom out',
  'action.timelineZoom': 'Timeline zoom',
  'action.zoomIn': 'Zoom in',
  'action.timelineZoomLevel': 'Timeline zoom level',

  // ---- StudioRightPanel ----
  'panel.tab.inspector': 'Inspector',
  'panel.tab.timeline': 'Timeline',

  // ---- StudioRightPanel ----
  'panel.resizeInspector': 'Resize inspector panel',
  'panel.tab.design': 'Design',
  'panel.tab.designTooltip': 'Element styles and properties',
  'panel.tab.layers': 'Layers',
  'panel.tab.layersTooltip': 'Composition layer stack',
  'panel.tab.renders': 'Renders',

  // ---- StudioLeftSidebar / 文件树 ----
  'sidebar.files': 'Files',
  'sidebar.assets': 'Assets',
  'sidebar.show': 'Show sidebar',
  'sidebar.resize': 'Resize sidebar',

  // ---- 模态框 ----
  'modal.lint.title': 'Lint results',
  'modal.askAgent.title': 'Ask agent',
  'lint.title': 'HyperFrame Lint Results',
  'lint.promptIntro': 'Fix these HyperFrames lint issues',
  'lint.allPassed': 'All checks passed',
  'lint.copyToAgent': 'Copy to Agent',
  'agent.copyPrompt': 'Copy prompt to AI agent',
  'agent.enterToCopy': '{key}+Enter to copy',
  'action.close': 'Close',

  // ---- 反馈条 / Toast ----
  'toast.saved': 'Saved',
  'feedback.giveFeedback': 'Give feedback',
  'toast.dismiss': 'Dismiss',

  // ---- PanelTabButton ----
  'panelTab.button': 'Panel',
};
