import type {AnyRemotionOption} from './option';

let rspackEnabled = false;

const cliFlag = 'experimental-rspack' as const;

export const rspackOption = {
	name: 'Experimental Rspack',
	cliFlag,
	description: () => (
		<>Uses Rspack instead of Webpack as the bundler for the Studio or bundle.</>
	),
	ssrName: null,
	docLink: null,
	type: false as boolean,
	getValue: ({commandLine}) => {
		if (commandLine[cliFlag] !== undefined) {
			rspackEnabled = true;
			return {
				value: commandLine[cliFlag] as boolean,
				source: 'cli',
			};
		}

		return {
			value: rspackEnabled,
			source: 'config',
		};
	},
	setConfig(value) {
		rspackEnabled = value;
	},
	id: cliFlag,
} satisfies AnyRemotionOption<boolean>;
