/**
 * VENDORED PATCH — NOT part of upstream remotion source.
 *
 * Upstream builds with tsgo (TypeScript native compiler, 7.0-dev libs)
 * whose libs differ from plain tsc 5.9.3. These declarations only restore
 * type-level symbols so the vendored build type-checks with plain tsc.
 * Type-only — zero runtime impact (the JS output is identical either way).
 *
 * 1. `Timer` / `Headers.entries` — present in tsgo's libs, missing in tsc
 *    5.9.3's. The published 4.0.484 d.ts ships `number | Timer` unresolved.
 *
 * 2. Canvas `getContext("2d")` overloads — tsc 5.9.3 has a resolution bug:
 *    once a compilation unit contains `new OffscreenCanvas().getContext('2d')`
 *    (e.g. timeline-utils/src/audio-waveform/parse-color.ts), the "2d"
 *    literal overload of `(HTMLCanvasElement | OffscreenCanvas).getContext()`
 *    stops matching and falls back to the generic `RenderingContext` overload,
 *    whose members lack clearRect/createImageData/putImageData. Re-declaring
 *    the "2d" overloads in this file (declared after lib.dom) restores
 *    correct resolution.
 *
 * Sync note: re-check on every upstream upgrade / compiler upgrade; delete
 * whichever parts the toolchain no longer needs.
 */

interface Headers {
	entries(): IterableIterator<[string, string]>;
}

type Timer = ReturnType<typeof setTimeout>;

interface HTMLCanvasElement {
	getContext(contextId: '2d', options?: any): CanvasRenderingContext2D | null;
}

interface OffscreenCanvas {
	getContext(
		contextId: '2d',
		options?: any,
	): OffscreenCanvasRenderingContext2D | null;
}
