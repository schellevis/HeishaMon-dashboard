/**
 * One command's lifecycle for the UI: confirm dialog, POST, status from the live `commands`
 * store, and the 422/429 rejections. The wear warning comes from the server record's
 * `eeprom_warning`; the hard stop is the 429 `rate_limited`.
 */
import { derived, writable } from 'svelte/store';
import { api } from '../api.js';
import { translate } from '../i18n/index.js';
import { askConfirm, commands } from '../stores.js';

function describeError(err) {
  return {
    code: err?.code || err?.message || 'failed',
    retryAfter: err?.body?.detail?.retry_after_s ?? null,
  };
}

/** Translated text for a rejection: a 429 names the wait, other codes are shown as sent by the server. */
export function errorMessage(error, lang) {
  if (!error) return '';
  if (error.code === 'rate_limited') {
    return translate(lang, 'common.commandErrorRateLimited', { seconds: error.retryAfter ?? '?' });
  }
  return error.code;
}

/** Wear warning text, shown when the server record carries `eeprom_warning`. */
export const warningMessage = (lang) => translate(lang, 'common.commandWarnEeprom');

/**
 * @param {string} name command name
 * @returns store of `{status, record, error, warning, pending}` plus `submit(value, {confirm})`
 *   and `reset()`. `confirm` is `{title, body}` for a dialog the user must accept first.
 */
export function createCommand(name) {
  const local = writable({ id: null, record: null, error: null, busy: false });

  const view = derived([local, commands], ([own, all]) => {
    const live = own.id != null ? all[own.id] : null;
    const record = live ?? own.record;
    let status = 'idle';
    if (own.error) status = 'failed';
    else if (own.busy) status = 'pending';
    else if (record) status = record.status;
    return {
      status,
      record,
      error: own.error,
      warning: Boolean(record?.eeprom_warning),
      busy: own.busy,
      pending: own.busy || record?.status === 'pending',
    };
  });

  async function submit(value, { confirm = null } = {}) {
    if (confirm && !(await askConfirm(confirm))) return null;
    local.update((s) => ({ ...s, error: null, busy: true }));
    try {
      const record = await api.command({ name, value, confirm: Boolean(confirm) });
      // a websocket update may have beaten the POST response; never overwrite it with the older record
      if (record?.id != null) commands.update((m) => (m[record.id] ? m : { ...m, [record.id]: record }));
      local.set({ id: record?.id ?? null, record: record ?? { name, status: 'pending' }, error: null, busy: false });
      return record;
    } catch (err) {
      local.update((s) => ({ ...s, error: describeError(err), busy: false }));
      return null;
    }
  }

  function reset() {
    local.set({ id: null, record: null, error: null, busy: false });
  }

  function clearError() {
    local.update((s) => ({ ...s, error: null }));
  }

  return { subscribe: view.subscribe, submit, reset, clearError };
}
