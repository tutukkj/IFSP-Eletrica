'use strict';
const $ = id => document.getElementById(id);
const number = (value, digits = 1) => value == null ? '—' : Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const dateLabel = value => value ? new Date(value).toLocaleDateString('pt-BR') : '—';
const timeLabel = value => value ? new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const state = { metadata: null, charts: {}, page: 1, pages: 0, params: null, controller: null, tableController: null, generation: 0 };
const intervals = { minute: 'minuto', '15min': '15 minutos', hour: 'hora', day: 'dia' };

function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = message ? `notice${error ? ' error' : ''}` : 'notice hidden';
}
async function getJSON(path, params, signal) {
  const response = await fetch(`/api/${path}?${params || ''}`, { signal });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível consultar os dados.');
  return result;
}
function td(value) { const cell = document.createElement('td'); cell.textContent = value; return cell; }
function initializeMetadata(metadata) {
  state.metadata = metadata;
  $('database-label').textContent = metadata.database === 'postgresql' ? 'PostgreSQL conectado' : 'SQLite · ambiente local';
  $('station').replaceChildren(...metadata.stations.map(station => new Option(station, station)));
  $('start').value = (metadata.start || '').slice(0, 10);
  $('end').value = (metadata.end || '').slice(0, 10);
  for (const id of ['start', 'end']) { $(id).min = (metadata.start || '').slice(0, 10); $(id).max = (metadata.end || '').slice(0, 10); }
  $('quality-rules').replaceChildren(...metadata.quality_rules.map(rule => { const li = document.createElement('li'); li.textContent = rule; return li; }));
  $('dictionary').replaceChildren(...Object.entries(metadata.metrics).map(([key, spec]) => { const row = document.createElement('tr'); row.append(td(key), td(spec.label), td(spec.unit)); return row; }));
  const headers = ['Instante', 'Estação', 'Qualidade', ...Object.values(metadata.metrics).map(spec => `${spec.label} (${spec.unit})`), 'Arquivo de origem'];
  const row = document.createElement('tr');
  headers.forEach(label => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; row.append(th); });
  $('table-head').replaceChildren(row);
}
function renderKPIs(summary) {
  const metrics = summary.metrics;
  const percent = summary.total ? 100 * summary.quality_rows / summary.total : 0;
  const cards = [
    ['Leituras no período', number(summary.total, 0), '', 'Registros de um minuto', '▦'],
    ['Pico de radiação · S1', number(metrics.solar1.max), 'W/m²*', `${number(metrics.solar1.count, 0)} valores considerados`, '☀'],
    ['Temperatura ambiente', number(metrics.temperature.avg), '°C*', 'Média do período selecionado', '°'],
    ['Pico de temperatura · contato', number(metrics.contact_temperature.max), '°C*', 'Maior leitura de superfície', '↗'],
    ['Umidade média', number(metrics.humidity.avg), '%*', 'Média do período selecionado', '◉'],
    ['Leituras com alertas', number(summary.quality_rows, 0), '', `${number(percent)}% com ao menos uma marcação`, '◇'],
  ];
  $('kpis').replaceChildren(...cards.map(([label, value, unit, foot, icon], index) => {
    const card = document.createElement('article'); card.className = `kpi${index === 5 ? ' alert' : ''}`;
    const top = document.createElement('div'); top.className = 'kpi-top';
    const name = document.createElement('span'); name.textContent = label;
    const glyph = document.createElement('span'); glyph.className = 'kpi-icon'; glyph.textContent = icon; glyph.setAttribute('aria-hidden', 'true'); top.append(name, glyph);
    const val = document.createElement('div'); val.className = 'kpi-value'; val.textContent = value;
    const unitSpan = document.createElement('span'); unitSpan.className = 'kpi-unit'; unitSpan.textContent = unit; val.append(unitSpan);
    const note = document.createElement('div'); note.className = 'kpi-foot'; note.textContent = foot; card.append(top, val, note); return card;
  }));
  $('coverage').textContent = summary.total ? `${dateLabel(summary.start)} — ${dateLabel(summary.end)} · ${number(summary.total, 0)} leituras` : 'Nenhuma leitura no período selecionado';
  const rain = metrics.precipitation;
  $('precipitation-note').textContent = rain.count ? `Precipitação absoluta: ${number(rain.min)} a ${number(rain.max)}. ${rain.min === rain.max ? 'O canal permanece constante neste período; confirme se é um contador acumulado ou se não houve atualização.' : 'Confira se o canal é acumulado antes de calcular chuva por intervalo.'} A unidade não foi informada.` : 'Precipitação absoluta: sem valores disponíveis.';
  $('validity-note').textContent = `Albedo: ${number(metrics.albedo.count, 0)} valores considerados de ${number(summary.total, 0)} leituras. ${summary.clean ? 'Filtragem de suspeitos ativada.' : 'Exibindo também valores suspeitos.'}`;
}
function renderChart(id, points, definitions, unit, config = {}) {
  if (typeof Chart === 'undefined') throw new Error('A biblioteca de gráficos não carregou. Confira o arquivo estático Chart.js.');
  Chart.defaults.font.family = 'Open Sans, Arial, sans-serif';
  const labels = points.map(point => point.timestamp);
  const datasets = definitions.map(([key, color]) => ({
    label: state.metadata.metrics[key].label, data: points.map(point => point[key]),
    borderColor: color, backgroundColor: `${color}12`, borderWidth: 1.7,
    pointRadius: points.length < 30 ? 2 : 0, pointHoverRadius: 4,
    tension: 0.15, fill: definitions.length === 1, spanGaps: false,
  }));
  if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; }
  const oneDay = points.length && points[0].timestamp.slice(0, 10) === points.at(-1).timestamp.slice(0, 10);
  state.charts[id] = new Chart($(id), {
    type: 'line', data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: definitions.length > 1, position: 'bottom', align: 'start', labels: { color: '#59635b', usePointStyle: true, pointStyle: 'circle', boxWidth: 6, boxHeight: 6, padding: 17, font: { size: 10 } } },
        tooltip: { backgroundColor: '#202820', padding: 12, callbacks: { title: items => timeLabel(items[0]?.label), label: context => `${context.dataset.label}: ${number(context.parsed.y, context.dataset.label === 'Albedo' ? 3 : 1)} ${unit}` } },
      },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { color: '#637269', maxTicksLimit: 6, maxRotation: 0, font: { size: 9 }, callback: function(value) { const date = new Date(this.getLabelForValue(value)); return oneDay ? date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }); } } },
        y: { ...config, border: { display: false }, grid: { color: '#e7ede6' }, ticks: { color: '#637269', maxTicksLimit: 5, font: { size: 9 } } },
      },
    },
  });
}
function renderSeries(series) {
  $('aggregation-label').textContent = `Média por ${intervals[series.interval] || 'intervalo'} · ${number(series.points.length, 0)} pontos`;
  const p = series.points;
  renderChart('solar-chart', p, [['solar1', '#2f9e41'], ['solar2', '#cd191e'], ['solar3', '#52645a']], 'W/m²*');
  renderChart('temperature-chart', p, [['contact_temperature', '#cd191e'], ['temperature', '#247a33'], ['dew_point', '#7a827c']], '°C*');
  renderChart('humidity-chart', p, [['humidity', '#287c72']], '%*');
  renderChart('pressure-chart', p, [['pressure', '#637582']], 'hPa*');
  renderChart('wind-chart', p, [['wind_speed', '#247a33'], ['wind_gust', '#52645a']], '(unidade não informada)');
  renderChart('albedo-chart', p, [['albedo', '#2f9e41']], '');
}
async function loadTable() {
  if (!state.params) return;
  state.tableController?.abort();
  const controller = new AbortController(); state.tableController = controller;
  const params = new URLSearchParams(state.params); params.set('page', state.page); params.set('page_size', 25);
  $('previous').disabled = true; $('next').disabled = true;
  try {
    const result = await getJSON('readings', params, controller.signal);
    state.pages = result.pages;
    $('table-body').replaceChildren(...result.rows.map(reading => {
      const row = document.createElement('tr'); row.append(td(timeLabel(reading.timestamp)), td(reading.station));
      const quality = td(''); const badge = document.createElement('span'); badge.className = `badge${reading.has_quality_issue ? ' warning' : ''}`; badge.textContent = reading.has_quality_issue ? 'Atenção' : 'Sem marcação'; quality.append(badge); row.append(quality);
      Object.keys(state.metadata.metrics).forEach(key => row.append(td(number(reading[key], key === 'albedo' ? 3 : 1))));
      row.append(td(reading.source_file)); return row;
    }));
    if (!result.rows.length) { const row = document.createElement('tr'); const cell = td('Nenhuma leitura encontrada.'); cell.colSpan = Object.keys(state.metadata.metrics).length + 4; cell.className = 'empty-cell'; row.append(cell); $('table-body').append(row); }
    $('page-label').textContent = result.total ? `Página ${result.page} de ${number(result.pages, 0)} · ${number(result.total, 0)} registros` : 'Nenhum registro';
    $('previous').disabled = state.page <= 1; $('next').disabled = state.page >= result.pages;
  } catch (error) { if (error.name !== 'AbortError') notice(error.message, true); }
}
async function refresh() {
  if (!$('filters').reportValidity()) return;
  if ($('start').value > $('end').value) { notice('A data inicial deve ser anterior ou igual à data final.', true); return; }
  state.controller?.abort(); state.tableController?.abort();
  const generation = ++state.generation;
  const controller = new AbortController(); state.controller = controller;
  const params = new URLSearchParams({ station: $('station').value, start: $('start').value, end: $('end').value, interval: $('interval').value, clean: $('clean').checked ? '1' : '0' });
  $('apply').disabled = true; $('export').setAttribute('aria-disabled', 'true');
  document.querySelector('main').setAttribute('aria-busy', 'true'); notice('Atualizando indicadores e gráficos…');
  try {
    const [summary, series] = await Promise.all([getJSON('summary', params, controller.signal), getJSON('series', params, controller.signal)]);
    renderKPIs(summary); renderSeries(series);
    state.params = params; state.page = 1;
    $('export').href = `/api/export.csv?${params}`; $('export').setAttribute('aria-disabled', 'false');
    notice(summary.total ? '' : 'Não há leituras para a estação e o período selecionados.');
    await loadTable();
  } catch (error) {
    if (error.name !== 'AbortError') notice(error.message + ' Os gráficos anteriores, se houver, não foram atualizados.', true);
  } finally {
    if (generation === state.generation) { $('apply').disabled = false; document.querySelector('main').setAttribute('aria-busy', 'false'); }
  }
}
$('filters').addEventListener('submit', event => { event.preventDefault(); refresh(); });
$('previous').addEventListener('click', () => { if (state.page > 1) { state.page--; loadTable(); } });
$('next').addEventListener('click', () => { if (state.page < state.pages) { state.page++; loadTable(); } });
document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('.nav-link').forEach(item => item.classList.remove('active')); link.classList.add('active'); }));
(async function initialize() {
  try {
    const metadata = await getJSON('metadata'); initializeMetadata(metadata);
    if (!metadata.total) { notice('Banco vazio. Importe a planilha usando o comando indicado no README.'); $('apply').disabled = true; return; }
    await refresh();
  } catch (error) { notice(error.message, true); $('database-label').textContent = 'Conexão indisponível'; }
})();
