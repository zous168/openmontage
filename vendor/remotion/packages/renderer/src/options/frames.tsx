import type {FrameRange} from '../frame-range';
import {validateFrameRange} from '../frame-range';
import type {AnyRemotionOption} from './option';

const cliFlag = 'frames' as const;

let frameRange: FrameRange | null = null;

const parseFrameRangeFromCli = (newFrameRange: string | number): FrameRange => {
	if (typeof newFrameRange === 'number') {
		if (newFrameRange < 0) {
			return [0, Math.abs(newFrameRange)];
		}

		return newFrameRange;
	}

	if (typeof newFrameRange === 'string') {
		if (newFrameRange.trim() === '') {
			throw new Error(
				'--frames flag must be a single number, or 2 numbers separated by `-`',
			);
		}

		const parts = newFrameRange.split('-');
		if (parts.length > 2 || parts.length <= 0) {
			throw new Error(
				`--frames flag must be a number or 2 numbers separated by '-', instead got ${parts.length} numbers`,
			);
		}

		if (parts.length === 1) {
			const value = Number(parts[0]);
			if (isNaN(value)) {
				throw new Error(
					'--frames flag must be a single number, or 2 numbers separated by `-`',
				);
			}

			return value;
		}

		const [firstPart, secondPart] = parts as [string, string];

		if (secondPart === '' && firstPart !== '') {
			const start = Number(firstPart);
			if (isNaN(start)) {
				throw new Error(
					'--frames flag must be a single number, or 2 numbers separated by `-`',
				);
			}

			return [start, null];
		}

		const parsed = parts.map((f) => Number(f));
		const [first, second] = parsed as [number, number];

		for (const value of parsed) {
			if (isNaN(value)) {
				throw new Error(
					'--frames flag must be a single number, or 2 numbers separated by `-`',
				);
			}
		}

		if (second < first) {
			throw new Error(
				'The second number of the --frames flag number should be greater or equal than first number',
			);
		}

		return [first, second];
	}

	throw new Error(
		'--frames flag must be a single number, or 2 numbers separated by `-`',
	);
};

export const framesOption = {
	name: 'Frame Range',
	cliFlag,
	description: () => (
		<>
			Render a subset of a video. Pass a single number to render a still, or a
			range (e.g. <code>0-9</code>) to render a subset of frames. Pass{' '}
			<code>100-</code> to render from frame 100 to the end.
		</>
	),
	ssrName: 'frameRange' as const,
	docLink: 'https://www.remotion.dev/docs/config#setframerange',
	type: null as FrameRange | null,
	getValue: ({commandLine}) => {
		if (commandLine[cliFlag] !== undefined) {
			const value = parseFrameRangeFromCli(
				commandLine[cliFlag] as string | number,
			);
			validateFrameRange(value);
			return {
				source: 'cli',
				value,
			};
		}

		return {
			source: 'config',
			value: frameRange,
		};
	},
	setConfig: (value: FrameRange | null) => {
		if (value !== null) {
			validateFrameRange(value);
		}

		frameRange = value;
	},
	id: cliFlag,
} satisfies AnyRemotionOption<FrameRange | null>;
