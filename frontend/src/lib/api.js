/** REST client for the spec §4.4 `/api` contract. */

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body ?? null;
    this.code = body?.error ?? null;
  }
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.set(key, Array.isArray(value) ? value.join(',') : String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export function createApi({ fetch: fetchImpl = globalThis.fetch, base = '' } = {}) {
  async function request(method, path, body) {
    const headers = {};
    const init = { method, headers };
    if (body !== undefined) {
      headers['content-type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const response = await fetchImpl(`${base}${path}`, init);
    const text = await response.text();
    let parsed = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = { error: 'bad_type', message: text, detail: null };
      }
    }
    if (!response.ok) throw new ApiError(response.status, parsed);
    return parsed;
  }

  return {
    state: () => request('GET', '/api/state'),
    profile: () => request('GET', '/api/profile'),
    history: (params) => request('GET', `/api/history${query(params)}`),
    historyCsvUrl: (params) => `${base}/api/history.csv${query(params)}`,
    command: ({ name, value, confirm = false }) => request('POST', '/api/command', { name, value, confirm }),
    commandStatus: (uuid) => request('GET', `/api/commands/${encodeURIComponent(uuid)}`),
    commands: (params = {}) => request('GET', `/api/commands${query(params)}`),
    events: (params = {}) => request('GET', `/api/events${query(params)}`),
    prefs: () => request('GET', '/api/prefs'),
    putPrefs: (prefs) => request('PUT', '/api/prefs', prefs),
    system: () => request('GET', '/api/system'),
    overlay: (params) => request('GET', `/api/overlay${query(params)}`),
    energy: (params) => request('GET', `/api/energy${query(params)}`),
    flush: () => request('POST', '/api/system/flush', {}),
  };
}

export const api = createApi();
