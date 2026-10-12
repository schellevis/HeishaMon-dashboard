/** Local date/time formatting. Uses the browser time zone; 24-hour clock for Dutch. */

function locale(lang) {
  return lang === 'nl' ? 'nl-NL' : 'en-GB';
}

export function formatDateTime(ms, lang = 'en', { timeZone } = {}) {
  if (ms == null || !Number.isFinite(Number(ms))) return '';
  return new Intl.DateTimeFormat(locale(lang), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZone,
  }).format(new Date(Number(ms)));
}

/** uPlot `fmtDate` replacement: format templates are ignored, Intl decides per locale. */
export function axisFormatter(lang = 'en', { timeZone } = {}) {
  const loc = locale(lang);
  const time = new Intl.DateTimeFormat(loc, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone });
  const day = new Intl.DateTimeFormat(loc, { day: 'numeric', month: 'short', timeZone });
  const month = new Intl.DateTimeFormat(loc, { month: 'short', year: 'numeric', timeZone });
  const year = new Intl.DateTimeFormat(loc, { year: 'numeric', timeZone });
  return { time, day, month, year };
}
