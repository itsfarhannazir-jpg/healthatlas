'use strict';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const number = (value) => Number(value || 0).toLocaleString('en-PK');
const pct = (value) => `${Number(value || 0).toFixed(1)}%`;
const safe = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const toCap = (value) => String(value || 'Unknown').replace(/_/g, ' ').replace(/\b\w/g, x => x.toUpperCase());
const regionNames = {punjab:'Punjab', sindh:'Sindh', kp:'Khyber Pakhtunkhwa', balochistan:'Balochistan', islamabad:'Islamabad Capital Territory', ajk:'Azad Jammu & Kashmir', gb:'Gilgit-Baltistan'};
const state = {view:'overview', summary:null, status:null, facilities:[], page:1, pages:1, total:0, limit:12, filters:{q:'', province:'', facility_type:'', ownership:''}, jobTimer:null, finishedJob:null, initialJobLoaded:false, debounce:null, toastTimeout:null};

async function api(path, options={}) {
  const response = await fetch(path, {headers:{'Accept':'application/json', ...(options.body ? {'Content-Type':'application/json'} : {})}, ...options});
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    let detail = body?.detail || `HTTP ${response.status}`;
    if (typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new Error(detail);
  }
  return body;
}

function toast(message, error=false) {
  const el = $('#toast');
  if (!el) return;
  clearTimeout(state.toastTimeout);
  el.textContent = message;
  el.classList.toggle('error', error);
  el.classList.add('show');
  state.toastTimeout = setTimeout(() => el.classList.remove('show'), 5100);
}

function setApiStatus(online) {
  const pill = $('.status-pill');
  pill.classList.toggle('error', !online);
  $('#apiStatus').textContent = online ? 'Connected' : 'Disconnected';
}

function setView(view) {
  if (!['overview','facilities','insights','pipeline'].includes(view)) return;
  state.view = view;
  $$('.view').forEach(el => el.classList.toggle('active-view', el.id === `view-${view}`));
  $$('.nav-link[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  const title = {overview:'Overview',facilities:'Facilities explorer',insights:'Data insights',pipeline:'ETL pipeline'}[view];
  $('#pageCrumb').textContent = title;
  $('#sidebar').classList.remove('open');
  window.scrollTo({top:0,behavior:'smooth'});
  if (view === 'facilities') loadFacilities();
}

function noData(text='No data available yet. Go to ETL pipeline to fetch and process records.') {
  return `<div class="placeholder-bars">${safe(text)}</div>`;
}

function qualityLines(quality) {
  return [
    ['Facility name', Number(quality?.named_pct || 0)],
    ['City / district', Number(quality?.city_pct || 0)],
    ['Ownership source tag', Number(quality?.operator_pct || 0)]
  ].map(([name, percent]) => `<div class="quality-line"><div class="quality-label"><span>${safe(name)}</span><b>${pct(percent)}</b></div><div class="quality-track"><div class="quality-fill" style="width:${Math.max(0,Math.min(100,percent))}%"></div></div></div>`).join('');
}

function renderSummary() {
  const data = state.summary;
  if (!data) return;
  const total = data.total || 0;
  $('#statTotal').textContent = number(total);
  $('#statRegions').textContent = `${data.mapped_regions || 0} / 7`;
  $('#statRate').textContent = Number(data.national_per_100k || 0).toFixed(2);
  $('#statQuality').textContent = pct(data.quality?.city_pct);
  $('#donutTotal').textContent = number(total);
  const types = Object.entries(data.types || {}).sort((a,b)=>b[1]-a[1]);
  const top = types.slice(0,7);
  const maximum = Math.max(...top.map(x=>x[1]),1);
  $('#typeChart').innerHTML = top.length ? top.map(([name,value]) => `<div class="bar-item"><span class="bar-label">${safe(toCap(name))}</span><div class="bar-track"><div class="bar-fill" style="width:${value/maximum*100}%"></div></div><span class="bar-count">${number(value)}</span></div>`).join('') : noData();

  const colors = {public:'#16bfa7', private:'#6283e9', unknown:'#dfe6ee'};
  const ownership = data.ownership || {};
  let position = 0;
  const parts = ['public','private','unknown'].map(key => {
    const value = Number(ownership[key] || 0);
    const start = position;
    position += total ? value / total * 100 : 0;
    return `${colors[key]} ${start}% ${position}%`;
  });
  $('#ownershipDonut').style.background = total ? `conic-gradient(${parts.join(',')})` : '#e9eff4';
  $('#ownershipLegend').innerHTML = ['public','private','unknown'].map(key => `<div class="legend-line"><span class="legend-color" style="background:${colors[key]}"></span><span>${toCap(key)}</span><b>${number(ownership[key])}</b></div>`).join('');

  const regions = data.regions || [];
  const largest = Math.max(...regions.map(r=>r.count),1);
  $('#overviewRegions').innerHTML = regions.some(x=>x.count) ? regions.slice(0,5).map((r,i) => `<div class="region-row"><div class="region-initial">${String(i+1).padStart(2,'0')}</div><div class="region-info"><div class="region-title"><span>${safe(r.name)}</span><strong>${number(r.count)}</strong></div><div class="region-track"><div style="width:${r.count/largest*100}%"></div></div></div></div>`).join('') : noData();
  $('#qualityBars').innerHTML = qualityLines(data.quality);
  $('#insightsQuality').innerHTML = qualityLines(data.quality);
  renderInsights(data);
}

function renderInsights(data) {
  const regions = [...(data.regions || [])].sort((a,b)=>b.per_100k-a.per_100k);
  const largest = Math.max(...regions.map(x=>x.per_100k), 1);
  $('#rateChart').innerHTML = data.total ? regions.map(r => `<div class="rate-row"><span title="${safe(r.name)}">${safe(r.name)}</span><div class="rate-track"><div style="width:${r.per_100k/largest*100}%"></div></div><strong>${Number(r.per_100k).toFixed(2)}</strong></div>`).join('') : noData();
  $('#regionalTable').innerHTML = regions.map(r => `<tr><td><strong>${safe(r.name)}</strong></td><td>${number(r.count)}</td><td>${number(r.population)}</td><td><strong>${Number(r.per_100k).toFixed(2)}</strong></td></tr>`).join('');
}

function facilityCell(item) {
  const display = item.name || 'Unnamed facility';
  const city = item.city || 'City not provided';
  return `<div class="facility-name"><span class="facility-avatar"><svg class="icon"><use href="#i-hospital"/></svg></span><span>${safe(display)}<small class="facility-meta">${safe(city)}</small></span></div>`;
}

function rowMarkup(item, directory=false) {
  const type = String(item.facility_type || 'other').toLowerCase();
  const owner = String(item.ownership || 'unknown').toLowerCase();
  const lat = Number(item.latitude), lon = Number(item.longitude);
  const coords = Number.isFinite(lat) && Number.isFinite(lon) ? `<a class="coords-link" title="See location on OpenStreetMap" href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(lat)}&mlon=${encodeURIComponent(lon)}#map=14/${encodeURIComponent(lat)}/${encodeURIComponent(lon)}" target="_blank" rel="noopener noreferrer">${lat.toFixed(3)}, ${lon.toFixed(3)}</a>` : '—';
  return `<tr><td>${facilityCell(item)}</td><td>${safe(item.province)}</td><td><span class="tag ${['hospital','clinic','doctors','pharmacy','dentist','laboratory'].includes(type) ? type : 'other'}">${safe(toCap(type))}</span></td><td><span class="owner-tag ${['public','private'].includes(owner) ? owner : ''}">${safe(toCap(owner))}</span></td>${directory ? `<td>${coords}</td>` : ''}</tr>`;
}

async function loadPreview() {
  try {
    const result = await api('/facilities?limit=5');
    $('#previewRows').innerHTML = result.facilities.length ? result.facilities.map(item=>rowMarkup(item)).join('') : '<tr><td colspan="4" class="empty-table">No facilities yet. Run the ETL pipeline to populate your directory.</td></tr>';
  } catch (error) {
    $('#previewRows').innerHTML = `<tr><td colspan="4" class="empty-table">${safe(error.message)}</td></tr>`;
  }
}

async function loadFacilities() {
  const params = new URLSearchParams({limit:String(state.limit),page:String(state.page)});
  Object.entries(state.filters).forEach(([key, value]) => {if(value) params.set(key,value);});
  try {
    const result = await api(`/facilities?${params.toString()}`);
    state.facilities = result.facilities;
    state.total = result.total;
    state.pages = result.pages;
    $('#directoryRows').innerHTML = result.facilities.length ? result.facilities.map(item=>rowMarkup(item,true)).join('') : '<tr><td colspan="5" class="empty-table">No matching facilities. Try different filters, or load records through the pipeline.</td></tr>';
    $('#resultsCounter').textContent = `${number(result.total)} records`;
    $('#pageSummary').textContent = result.total ? `Showing ${number((result.page-1)*result.limit+1)}–${number((result.page-1)*result.limit+result.count)} of ${number(result.total)} records` : '0 results';
    $('#pageNumber').textContent = `${result.page} / ${result.pages}`;
    $('#prevPage').disabled = result.page <= 1;
    $('#nextPage').disabled = result.page >= result.pages;
  } catch (error) {
    $('#directoryRows').innerHTML = `<tr><td colspan="5" class="empty-table">${safe(error.message)}</td></tr>`;
    toast(`Could not load facilities: ${error.message}`,true);
  }
}

function renderStatus(status) {
  state.status = status;
  const count = status.raw_count || 0;
  $('#rawIndicator').textContent = count ? `${count} / 7 regions cached` : 'No cached regions';
  $('#outputRaw').textContent = `${count} / 7 regions`;
  $('#outputCsv').textContent = status.csv_available ? 'Available' : 'Not created';
  $('#outputCharts').textContent = status.charts_available ? 'Available' : 'Not created';
  $('#outputReport').textContent = status.report_available ? 'Available' : 'Not created';
  renderJob(status.job);
}

function setButtonsRunning(running) {
  $$('[data-action="all"],[data-action="fetch"],[data-action="clean"],[data-action="analyze"],[data-action="report"]').forEach(el => {el.disabled=running;});
}

function renderJob(job) {
  const banner = $('#jobBanner');
  if (!job) {
    banner.classList.add('hidden');
    $('#taskBadge').textContent = 'Idle';
    $('#taskDetails').textContent = 'No task has run in this server session. Choose a workflow stage to begin.';
    setButtonsRunning(false);
    return;
  }
  const busy = ['queued','running'].includes(job.status);
  setButtonsRunning(busy);
  banner.classList.remove('hidden');
  $('#jobTitle').textContent = job.status === 'completed' ? 'Pipeline completed successfully' : job.status === 'completed_with_warnings' ? 'Pipeline completed with warnings' : job.status === 'failed' ? 'Pipeline failed' : 'Pipeline in progress';
  $('#jobDescription').textContent = job.status === 'failed' ? (job.error || 'Unknown error') : (job.stage || 'Processing');
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  $('#jobPercent').textContent = `${progress}%`;
  $('#jobProgressFill').style.width = `${progress}%`;
  $('#jobSpinner').className = 'job-spinner' + (['completed','completed_with_warnings'].includes(job.status) ? ' done' : job.status === 'failed' ? ' failed' : '');
  const started = job.started_at ? new Date(job.started_at).toLocaleString() : '—';
  $('#taskBadge').textContent = toCap(job.status);
  $('#taskDetails').innerHTML = `<div class="task-summary"><strong>${safe(toCap(job.action))} · ${safe(job.province ? regionNames[job.province] : 'All regions')}</strong><span>Started: ${safe(started)}</span><span>${safe(job.stage || '')}</span>${job.error ? `<em class="error-text">${safe(job.error)}</em>` : ''}${(job.warnings || []).length ? `<em class="error-text">Download warnings: ${(job.warnings || []).map(safe).join(' | ')}</em>` : ''}${['completed','completed_with_warnings'].includes(job.status) ? '<span>Completed outputs are ready to review.</span>' : ''}</div>`;

  if (busy && !state.jobTimer) state.jobTimer = setInterval(pollJob, 1500);
  if (!busy && state.jobTimer) {clearInterval(state.jobTimer);state.jobTimer=null;}
  if (state.initialJobLoaded && !busy && job.id !== state.finishedJob) {
    state.finishedJob = job.id;
    toast(job.status === 'completed' ? 'Pipeline completed. Dashboard data has been refreshed.' : job.status === 'completed_with_warnings' ? 'Pipeline completed, but some regions failed to download. Check task details.' : `Pipeline failed: ${job.error || 'unknown error'}`, job.status !== 'completed');
    refreshData();
  }
  if (!state.initialJobLoaded) {
    state.initialJobLoaded = true;
    if (!busy) state.finishedJob = job.id;
  }
}

async function pollJob() {
  try {
    const result = await api('/api/jobs/current');
    renderJob(result.job);
  } catch (error) {setApiStatus(false);}
}

async function refreshData() {
  try {
    const [summary, status] = await Promise.all([api('/api/summary'), api('/api/status')]);
    state.summary = summary;
    renderSummary();
    renderStatus(status);
    setApiStatus(true);
    loadPreview();
    if (state.view === 'facilities') loadFacilities();
  } catch (error) {
    setApiStatus(false);
    toast(`Connection error: ${error.message}`,true);
  }
}

async function startJob(action) {
  const province = $('#pipelineProvince').value || null;
  try {
    const job = await api('/api/jobs', {method:'POST',body:JSON.stringify({action, province: action === 'analyze' || action === 'report' ? null : province})});
    toast(`Started ${action === 'all' ? 'full pipeline' : action} task.`);
    renderJob(job);
    if (state.view !== 'pipeline') setView('pipeline');
  } catch (error) {
    toast(`Could not start task: ${error.message}`, true);
  }
}

function handleAction(action) {
  switch (action) {
    case 'go-pipeline':setView('pipeline');break;
    case 'download-csv':
      if (state.status?.csv_available) window.location.assign('/download-csv');
      else toast('No CSV yet. Clean and save your fetched records first.', true);
      break;
    case 'download-report':
      if (state.status?.report_available) window.location.assign('/download-report');
      else toast('No report yet. Generate a findings report in the pipeline.', true);
      break;
    default: if (['all','fetch','clean','analyze','report'].includes(action)) startJob(action);
  }
}

function wire() {
  $$('#sidebar [data-view], .page-content [data-view]').forEach(el => el.addEventListener('click',()=>setView(el.dataset.view)));
  $$('[data-action]').forEach(el => el.addEventListener('click',()=>handleAction(el.dataset.action)));
  $('#refreshButton').addEventListener('click',()=>{refreshData();toast('Refreshing dashboard data.');});
  $('#menuToggle').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
  $('#clearFilters').addEventListener('click',()=>{
    $('#facilitySearch').value='';$('#provinceFilter').value='';$('#typeFilter').value='';$('#ownerFilter').value='';
    state.filters={q:'',province:'',facility_type:'',ownership:''};state.page=1;loadFacilities();
  });
  const setFilter = (name,value) => {state.filters[name]=value;state.page=1;loadFacilities();};
  $('#facilitySearch').addEventListener('input',(event)=>{
    clearTimeout(state.debounce);
    state.debounce=setTimeout(()=>setFilter('q',event.target.value.trim()),280);
  });
  $('#provinceFilter').addEventListener('change',e=>setFilter('province',e.target.value));
  $('#typeFilter').addEventListener('change',e=>setFilter('facility_type',e.target.value));
  $('#ownerFilter').addEventListener('change',e=>setFilter('ownership',e.target.value));
  $('#prevPage').addEventListener('click',()=>{if(state.page>1){state.page--;loadFacilities();}});
  $('#nextPage').addEventListener('click',()=>{if(state.page<state.pages){state.page++;loadFacilities();}});
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 760 && !e.target.closest('#sidebar') && !e.target.closest('#menuToggle')) $('#sidebar').classList.remove('open');
  });
}

function fillRegions() {
  const entries = Object.entries(regionNames).map(([key,name])=>`<option value="${key}">${safe(name)}</option>`).join('');
  $('#provinceFilter').insertAdjacentHTML('beforeend',entries);
  $('#pipelineProvince').insertAdjacentHTML('beforeend',entries);
}

function init() {
  $('#footerYear').textContent = String(new Date().getFullYear());
  $('#todayLabel').textContent = new Intl.DateTimeFormat('en-PK',{day:'numeric',month:'short',year:'numeric'}).format(new Date());
  fillRegions();
  wire();
  refreshData();
}

document.addEventListener('DOMContentLoaded',init);
