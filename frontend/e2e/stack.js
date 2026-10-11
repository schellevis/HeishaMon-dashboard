// Starts / stops the test stack: embedded broker (ephemeral port) -> simulator -> app on 8765.
// Teardown runs in reverse order. Nothing here reads `.env`.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, '../..');
export const PYTHON = path.join(ROOT, '.venv/bin/python');
export const DIST = process.env.E2E_STATIC_DIR || path.join(ROOT, 'frontend/dist');
export const PORT = 8765;
export const URL = `http://localhost:${PORT}`;

const PIDFILE = path.join(os.tmpdir(), 'hm-e2e-pids.json');
let running = []; // spawned children, start order
let tmp = null;

// Playwright restarts the worker after a failed test, which loses the module state above, so the
// children are also recorded in a pid file and reaped by the next down().
function recordPids() {
  fs.writeFileSync(PIDFILE, JSON.stringify({ pids: running.map((c) => c.pid), tmp }));
}

function reapRecorded() {
  try {
    const { pids, tmp: old } = JSON.parse(fs.readFileSync(PIDFILE, 'utf8'));
    for (const pid of [...pids].reverse()) {
      try { process.kill(pid, 'SIGKILL'); } catch { /* already gone */ }
    }
    if (old) fs.rmSync(old, { recursive: true, force: true });
    fs.rmSync(PIDFILE, { force: true });
  } catch { /* no pid file */ }
}

function launch(args, env, name) {
  const child = spawn(PYTHON, args, {
    cwd: tmp,
    env: { PATH: process.env.PATH, HOME: tmp, PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1', ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.name = name;
  child.output = '';
  child.stdout.on('data', (d) => { child.output += d; });
  child.stderr.on('data', (d) => { child.output += d; });
  running.push(child);
  recordPids();
  return child;
}

async function until(fn, ms, what) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if (await fn()) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`${what} not ready within ${ms} ms\n${running.map((c) => `--- ${c.name}\n${c.output}`).join('\n')}`);
}

function stopChild(child) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(() => child.kill('SIGKILL'), 20_000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    child.kill('SIGTERM');
  });
}

/** Start the stack for one simulator preset. `faults` is a list of `NAME=MODE` strings. */
export async function up(preset, faults = []) {
  await down();
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hm-e2e-'));
  const broker = launch([path.join(here, 'broker.py')], {}, 'broker');
  await until(() => /PORT \d+/.test(broker.output), 10_000, 'broker');
  const brokerPort = broker.output.match(/PORT (\d+)/)[1];

  const sim = [path.join(ROOT, 'tools/simulator.py'), '--host', '127.0.0.1', '--port', brokerPort, '--preset', preset];
  for (const f of faults) sim.push('--fault', f);
  const simulator = launch(sim, { PYTHONPATH: path.join(ROOT, 'tools') + path.delimiter + path.join(ROOT, 'backend') }, 'simulator');
  await new Promise((r) => setTimeout(r, 1500)); // let the retained snapshot reach the broker
  if (simulator.exitCode !== null) throw new Error(`simulator exited early\n${simulator.output}`);

  launch(['-m', 'heishamon_dashboard'], {
    PYTHONPATH: path.join(ROOT, 'backend'),
    MQTT_HOST: '127.0.0.1',
    MQTT_PORT: brokerPort,
    DATA_DIR: path.join(tmp, 'data'),
    HTTP_PORT: String(PORT),
    STATIC_DIR: DIST,
  }, 'app');
  await until(async () => (await fetch(`${URL}/api/system`)).ok, 10_000, 'GET /api/system');
  // the profile needs the retained snapshot to have been ingested
  await until(async () => {
    const s = await (await fetch(`${URL}/api/state`)).json();
    return Object.keys(s.topics ?? {}).length > 10 && s.device_online === 'online';
  }, 20_000, 'state ingest and device online');
}

/** Stop in reverse start order (app, simulator, broker). */
export async function down() {
  const list = running.reverse();
  running = [];
  for (const child of list) await stopChild(child);
  reapRecorded();
  if (tmp) { fs.rmSync(tmp, { recursive: true, force: true }); tmp = null; }
}
