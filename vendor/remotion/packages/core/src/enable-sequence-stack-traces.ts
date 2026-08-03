const componentsToAddStacksTo: unknown[] = [];

export const getComponentsToAddStacksTo = () => componentsToAddStacksTo;

export const addSequenceStackTraces = (component: unknown) => {
	componentsToAddStacksTo.push(component);
};
