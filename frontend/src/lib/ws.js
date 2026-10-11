/** WebSocket client for spec §4.4 `/api/ws`. The socket is read-only. */

export function wsUrl(loc = globalThis.location) {
  const protocol = loc?.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = loc?.host || 'localhost';
  return `${protocol}//${host}/api/ws`;
}

/**
 * Drop every non-hello message until hello, and every message with `seq <= hello.seq`.
 * A new connection waits for its own hello, which replaces the previous snapshot.
 */
export function createWsClient({
  url = '/api/ws',
  WebSocketImpl = globalThis.WebSocket,
  onHello = () => {},
  onMessage = () => {},
  onDrop = () => {},
  onConnection = () => {},
  backoffMs = (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  schedule = (fn, ms) => setTimeout(fn, ms),
  clearSchedule = (id) => clearTimeout(id),
} = {}) {
  let socket = null;
  let helloSeq = null;
  let ready = false;
  let stopped = false;
  let attempt = 0;
  let timer = null;

  function ingest(msg, mine) {
    if (mine !== socket) return;
    if (!msg || typeof msg.seq !== 'number' || typeof msg.type !== 'string') return;
    if (msg.type === 'hello') {
      helloSeq = msg.seq;
      ready = true;
      onHello(msg);
      return;
    }
    if (!ready || msg.seq <= helloSeq) {
      onDrop(msg);
      return;
    }
    onMessage(msg);
  }

  function connect() {
    const mine = new WebSocketImpl(url);
    socket = mine;
    ready = false;
    helloSeq = null;
    mine.onopen = () => {
      if (mine !== socket) return;
      attempt = 0;
      onConnection('open');
    };
    mine.onmessage = (event) => {
      if (mine !== socket) return;
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      ingest(msg, mine);
    };
    mine.onclose = () => {
      if (mine !== socket || stopped) return;
      ready = false;
      onConnection('closed');
      const wait = backoffMs(attempt);
      attempt += 1;
      timer = schedule(() => {
        if (!stopped) connect();
      }, wait);
    };
  }

  return {
    start() {
      stopped = false;
      connect();
    },
    stop() {
      stopped = true;
      if (timer != null) clearSchedule(timer);
      timer = null;
      const mine = socket;
      socket = null;
      ready = false;
      try {
        mine?.close();
      } catch {
        /* already closed */
      }
    },
    get helloSeq() {
      return helloSeq;
    },
  };
}
