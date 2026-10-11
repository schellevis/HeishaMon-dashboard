import catalogData from '$catalog';

/** The build-time catalog. This module is the only production import of `$catalog`. */
export const catalog = catalogData;

export function topicByKey(key) {
  return catalog.topics.find((topic) => topic.key === key) ?? null;
}

export function commandByName(name) {
  return catalog.commands.find((command) => command.name === name) ?? null;
}

export function inputByPath(path) {
  return (catalog.inputs ?? []).find((input) => input.path === path) ?? null;
}
