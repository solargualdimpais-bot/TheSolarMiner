import { CATEGORIES, DEMO_EQUIPMENT, classifyEquipment, formatReading, isSimulated, summarizeDataState } from "./app-core.js";
import { DEMO_CONTROL_CONFIG, createDemoControlState, updateDemoControl, toggleDemoControl } from "./demo-mode.js";
import { renderWorkspacePage, renderHomePreferenceLinks, renderHouseSearch, handleWorkspaceAction, handleWorkspaceChange, applyPreferences, getWorkspacePageLabel, workspace, getEditableEntity, saveEditableEntity, saveDemoWorkspace, hydrateWorkspacePhotos } from "./workspace-ui.js";
import { renderAutomationsPage, renderSolarProductionPage, renderDemoAdminPanel, handleFeatureAction, saveAutomationForm, addDemoUser, saveDemoUserEdit, saveSolarWeather, demoFeatures } from "./features-v053.js";
import { GatewayConnectionManager, CONNECTION_STATES, validateGatewayUrl, classifyEndpoint, inferHostedGatewayEndpoint, PRESENCE_API_STATUS } from "./gateway-connection.js";
import { bootstrapGatewayOwner, recoverGatewayOwner, parseOwnerRecoveryFile, readGatewayBootstrapStatus, loginGateway, loginGatewayWithPassword, sessionInfo, createGatewayInvite, listGatewayInvites, revokeGatewayInvite, listGatewayUsers, updateGatewayUserRole, updateGatewayUserStatus, logoutGateway, readGatewayEnergy, presenceInfo, checkGatewayUpdate, readGatewayUpdateSource, readGatewayUpdateStatus, applyGatewayUpdate, readGatewayTailscale, configureGatewayTailscale, startGatewayTailscale, readGatewayHardwareIntegrationConfig, saveGatewayHardwareIntegrationConfig, readGatewayHardwareIntegrations, readGatewayTeslaEvConfig, saveGatewayTeslaEvConfig, readGatewayTeslaEvCharging } from "./gateway-auth.js";

let automationEditingId = "";
const state = { page: "inicio", mode: "DISCONNECTED", dataStatus: "UNAVAILABLE", dataError: null, equipment: [], lastUpdated: null, lastMeasurementAt: null, refreshing: false, propertyPhoto: "", demoControls: createDemoControlState(), sky: "pouco nublado", favoriteDevices: [] };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const pageLabel = (id) => id === "inicio" ? "Visão geral" : id === "owner" ? "Owner" : (CATEGORIES.find(c => c.id === id)?.label || getWorkspacePageLabel(id) || "Mais áreas");
const timeLabel = (value) => value ? new Intl.DateTimeFormat("pt-PT", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value)) : "Sem atualização";
let editorContext=null, editorPhoto=undefined, editorPhotoFile=null;
function openContextEditor(type,id){
  const entity=getEditableEntity(type,id);if(!entity){return;}
  editorContext={type,id};editorPhoto=type==='house'?(entity.photo||''):type==='room'?(entity.customPhoto||''):(entity.customPhoto||'');editorPhotoFile=null;
  const title=({house:'Editar identidade da casa',room:'Editar divisão',device:'Editar dispositivo',floor:'Editar piso'})[type]||'Editar elemento';
  $('#context-editor-title').textContent=title;$('#context-editor-status').textContent='DEMO · alterações locais neste browser; sem gravação no Gateway.';
  const floorOptions=workspace.house.floors.map(f=>`<option value="${esc(f.id)}" ${f.id===(entity.__floorId||workspace.house.activeFloor)?'selected':''}>${esc(f.name)}</option>`).join('');
  let fields='';
  if(type==='house')fields=`<label class="ws-field">Nome da casa<input name="name" maxlength="100" required value="${esc(entity.name||'A Minha Casa')}"></label><label class="ws-field">Descrição (opcional)<textarea name="description" maxlength="300" rows="3">${esc(entity.description||'')}</textarea></label>`;
  if(type==='floor')fields=`<label class="ws-field">Nome do piso<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label>`;
  if(type==='room')fields=`<label class="ws-field">Nome da divisão<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label><label class="ws-field">Piso associado<select name="floorId">${floorOptions}</select></label>`;
  if(type==='device'){
    const roomOptions=workspace.house.floors.flatMap(f=>f.rooms.map(r=>`<option value="${esc(f.id)}|${esc(r.id)}" ${f.id===(entity.__floorId||'')&&r.id===(entity.__roomId||'')?'selected':''}>${esc(f.name)} / ${esc(r.name)}</option>`)).join('');
    fields=`<label class="ws-field">Nome apresentado<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label><label class="ws-field">Divisão associada<select name="roomTarget">${roomOptions}</select></label><p class="field-note">Tipo: ${esc(entity.type||'desconhecido')} · apenas identificação local. Não há campos de controlo real.</p>`;
  }
  if(type==='house'||type==='room'||type==='device')fields+=`<label class="ws-field">Imagem personalizada (JPEG, PNG, WebP; máximo 12 MB)<input id="context-editor-file" name="image" type="file" accept="image/jpeg,image/png,image/webp,image/*"></label><div class="dialog-actions"><button type="button" id="context-editor-remove-photo" class="button secondary">Remover imagem personalizada</button></div>`;
  $('#context-editor-fields').innerHTML=fields;
  const preview=$('#context-editor-preview'),img=$('#context-editor-preview-image');
  if(editorPhoto){img.src=editorPhoto;preview.hidden=false;}else{img.removeAttribute('src');preview.hidden=true;}
  $('#context-editor').showModal();
}
function readAndCompressImage(file){return new Promise((resolve,reject)=>{if(!file)return resolve(undefined);if(!/^image\/(jpeg|png|webp|gif|avif)$/i.test(file.type)||file.size>12*1024*1024)return reject(new Error('Escolhe uma imagem válida com menos de 12 MB.'));const reader=new FileReader();reader.onerror=()=>reject(new Error('Não foi possível ler a imagem.'));reader.onload=()=>{const image=new Image();image.onerror=()=>reject(new Error('O ficheiro não parece ser uma imagem válida.'));image.onload=()=>{const scale=Math.min(1,1400/Math.max(image.naturalWidth,image.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));const ctx=canvas.getContext('2d');if(!ctx)return reject(new Error('O browser não disponibilizou processamento local de imagem.'));ctx.drawImage(image,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/jpeg',.78);if(data.length>2_500_000)return reject(new Error('A imagem comprimida continua demasiado grande.'));resolve(data);};image.src=reader.result;};reader.readAsDataURL(file);});}
$('#context-editor-cancel').addEventListener('click',()=>$('#context-editor').close());
$('#context-editor-fields').addEventListener('change',async e=>{if(e.target.id!=='context-editor-file')return;const file=e.target.files?.[0];if(!file)return;try{editorPhoto=await readAndCompressImage(file);const img=$('#context-editor-preview-image');img.src=editorPhoto;$('#context-editor-preview').hidden=false;$('#context-editor-status').textContent='Pré-visualização pronta. Ainda não foi guardada.';}catch(error){$('#context-editor-status').textContent=error.message;}});
$('#context-editor-fields').addEventListener('click',e=>{if(e.target.id!=='context-editor-remove-photo')return;editorPhoto='';editorPhotoFile=null;$('#context-editor-preview').hidden=true;$('#context-editor-preview-image').removeAttribute('src');$('#context-editor-status').textContent='A imagem será removida quando guardares.';});
$('#context-editor-form').addEventListener('submit',e=>{e.preventDefault();if(!editorContext)return;const form=e.currentTarget;const values={name:form.elements.name?.value,description:form.elements.description?.value};if(editorContext.type==='room'){values.floorId=form.elements.floorId?.value;}if(editorContext.type==='device'){const pair=(form.elements.roomTarget?.value||'').split('|');values.floorId=pair[0];values.roomId=pair[1];}if(['house','room','device'].includes(editorContext.type))values.photo=editorPhoto;const ok=saveEditableEntity(editorContext.type,editorContext.id,values);if(ok){if(editorContext.type==='house'){state.propertyPhoto=workspace.house.photo||'';}$('#context-editor').close();render();const n=$('#notice');n.hidden=false;n.textContent='Alteração guardada apenas neste browser (DEMO). O Gateway não foi alterado.';setTimeout(()=>n.hidden=true,5000);}else $('#context-editor-status').textContent='Não foi possível guardar a alteração local.';});


const gatewayManager = new GatewayConnectionManager({ onState: updateGatewayStatus });
function updateGatewayStatus(connection) {
  const label = $("#gateway-status-label"), detail = $("#gateway-status-detail"), dot = $(".gateway-status-dot");
  if (!label || !detail) return;
  label.textContent = connection.state || CONNECTION_STATES.DEMO;
  if (connection.simulated) detail.textContent = "Os dados e dispositivos apresentados continuam simulados; não existe ligação ao Gateway.";
  else if (connection.reachable && connection.identityValidated) detail.textContent = "Identidade Ed25519 do Gateway validada nesta sessão. O método LAN/REMOTO e a presença física continuam desconhecidos.";
  else if (connection.reachable && !connection.identityValidated) detail.textContent = `${connection.gatewayProduct || "Gateway"} respondeu${connection.reportedVersion ? ` · versão ${connection.reportedVersion}` : ""}. Identidade não validada; LAN/REMOTO não confirmado.`;
  else if (connection.state === CONNECTION_STATES.UNASSOCIATED) detail.textContent = "Ainda não existe um Gateway associado. Usa um QR autorizado ou consulta a configuração.";
  else detail.textContent = "Não foi possível confirmar uma ligação segura. Verifica o endpoint e tenta novamente.";
  if (dot) dot.style.background = connection.simulated ? "#b9a477" : connection.reachable ? "#d6ad64" : "#b96c62";
}
function gatewayResult(message) { const el = $("#gateway-result"); if (el) el.textContent = message; }
const gatewayHostedOrigin = inferHostedGatewayEndpoint(location);
try {
  const savedEndpoint = localStorage.getItem("solarminer-gateway-endpoint-v1");
  const initialEndpoint = gatewayHostedOrigin || savedEndpoint;
  if (initialEndpoint) $("#gateway-endpoint").value = initialEndpoint;
} catch {}
function currentTimeLabel(value) { return value ? new Intl.DateTimeFormat("pt-PT", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value)) : "não confirmada"; }


function readStoredPhoto() {
  try { const value = localStorage.getItem("solar-miner-demo-property-photo-v1") || ""; return /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(value) ? value : ""; }
  catch { return ""; }
}
function demoTotals() {
  const read = (cat) => { const value = state.equipment.find(x => x.category === cat)?.readings?.[0]?.value; return typeof value === "number" && Number.isFinite(value) ? value : null; };
  return { solar: read("inversores"), battery: read("baterias"), miner: read("mineradoras"), ev: read("ev"), aqs: read("aqs"), floor: read("soalho-radiante") };
}
function freshness() {
  if (state.mode === "SIMULATED") {
    summarizeDataState({ mode: "SIMULATED", lastUpdated: null });
    $("#freshness-label").textContent = "Dados de demonstração · não são leituras reais";
    $("#mode-chip").textContent = "DEMO · SIMULATED";
    $("#mode-chip").className = "mode-chip simulated";
    $("#connection-title").textContent = "Demonstração ativa";
    $("#connection-detail").textContent = "Dados locais · sem ligação física";
    $("#connection-summary .pulse").style.background = "var(--gold)";
    return;
  }
  const labels = {
    LIVE: ["LIVE · GATEWAY", "Leituras recentes recebidas do Gateway autenticado", "Gateway autenticado", "Dados consultados agora; a confiança de cada leitura continua indicada individualmente", "#8fbd8a"],
    STALE: ["STALE · DESATUALIZADO", "Existem leituras antigas; não são apresentadas como atuais", "Dados desatualizados", "Última medição conhecida às " + currentTimeLabel(state.lastMeasurementAt), "#d6ad64"],
    UNKNOWN: ["UNKNOWN · SEM LEITURAS", "Gateway autenticado, mas não existem leituras válidas", "Sem leituras conhecidas", "A API respondeu; nenhum valor foi inventado", "#d6ad64"],
    UNAVAILABLE: ["UNAVAILABLE · SEM DADOS", "A consulta não confirmou dados atuais do Gateway", "Dados indisponíveis", state.dataError || "Repete a consulta quando a ligação estiver disponível", "#b96c62"]
  };
  const item = labels[state.dataStatus] || labels.UNKNOWN;
  $("#freshness-label").textContent = item[1];
  $("#mode-chip").textContent = item[0];
  $("#mode-chip").className = `mode-chip ${state.dataStatus.toLowerCase()}`;
  $("#connection-title").textContent = item[2];
  $("#connection-detail").textContent = item[3];
  $("#connection-summary .pulse").style.background = item[4];
}
function normalizeGatewayEquipment(items) {
  return items.map(item => ({
    ...item,
    source: "CODE02_API",
    readings: (Array.isArray(item.readings) ? item.readings : []).map(reading => ({
      ...reading, value: reading.value, observed_at: reading.observed_at,
      source: reading.source || "UNKNOWN", trust: reading.trust || "UNKNOWN"
    }))
  }));
}
function classifyGatewayReadings(items) {
  const readings = items.flatMap(item => item.readings || []);
  const measured = readings.filter(reading => ["LIVE_UNVERIFIED", "PHYSICALLY_CORROBORATED"].includes(reading.trust) && !["DEMO", "SIMULATED"].includes(String(reading.source || "").toUpperCase()));
  if (!measured.length) return "UNKNOWN";
  const times = measured.map(reading => Date.parse(reading.observed_at || "")).filter(Number.isFinite);
  if (!times.length) return "UNKNOWN";
  return Date.now() - Math.max(...times) > 5 * 60 * 1000 ? "STALE" : "LIVE";
}
async function refreshGatewayReadings() {
  if (!sessionInfo().authenticated) return false;
  state.refreshing = true;
  $("#refresh-button").disabled = true;
  try {
    const result = await readGatewayEnergy();
    state.equipment = normalizeGatewayEquipment(result.equipment);
    state.mode = "LIVE";
    state.dataStatus = classifyGatewayReadings(state.equipment);
    state.dataError = null;
    state.lastUpdated = result.fetchedAt;
    const measurementTimes = state.equipment.flatMap(item => item.readings || []).map(reading => Date.parse(reading.observed_at || "")).filter(Number.isFinite);
    state.lastMeasurementAt = measurementTimes.length ? new Date(Math.max(...measurementTimes)).toISOString() : null;
    render();
    return true;
  } catch (error) {
    state.mode = "LIVE";
    state.dataStatus = state.lastUpdated ? "STALE" : "UNAVAILABLE";
    state.dataError = error.status === 401 ? "Sessão expirada. Autentica novamente; não foram usados dados de demonstração como fallback." : `Consulta falhada: ${error.message}`;
    if (error.status === 401) updateSessionUi();
    render();
    return false;
  } finally {
    state.refreshing = false;
    $("#refresh-button").disabled = false;
  }
}
function resetToDemoAfterLogout() {
  state.mode = "DISCONNECTED"; state.dataStatus = "UNAVAILABLE"; state.dataError = null;
  state.equipment = []; state.lastUpdated = null; state.lastMeasurementAt = null; render();
}
function card(item) {
  const category = CATEGORIES.find(c => c.id === item.category) || { icon: "•", label: item.category };
  const reading = formatReading(item.readings?.[0]);
  const status = classifyEquipment(item);
  const pill = status === "CONNECTED" ? ["Ligado", "ok"] : status === "UNAVAILABLE" ? ["Indisponível", "off"] : status === "SIMULATED" ? ["DEMO", ""] : ["Não validado", ""];
  const model = [item.manufacturer, item.model].filter(Boolean).join(" · ") || "Perfil por configurar";
  const updated = item.last_communication_at ? timeLabel(item.last_communication_at) : "Sem leitura real";
  return `<article class="equipment-card"><div class="equipment-top"><div class="device-icon">${esc(category.icon)}</div><span class="state-pill ${pill[1]}">${esc(pill[0])}</span></div><h3>${esc(item.name || item.id)}</h3><div class="equipment-meta">${esc(model)}<br>ID: ${esc(item.id)}</div><div class="equipment-reading"><strong>${esc(reading.value)} <span>${esc(reading.unit)}</span></strong><span>${esc(item.readings?.[0]?.field || "Sem leitura")}</span></div><div class="equipment-bottom"><span>${esc(updated)}</span><span class="source-tag">${isSimulated(item) ? "SIMULATED" : esc(item.readings?.[0]?.trust || "SEM DADOS")}</span></div><button class="card-link" data-page="${esc(item.category)}">Explorar área <span>↗</span></button></article>`;
}
function metric(label, value, unit, icon, detail) {
  const safeDetail = state.mode !== "SIMULATED" && (value === null || value === undefined) ? "Sem leitura válida do Gateway" : detail;
  const formatted = typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(value)
    : value === null || value === undefined ? "—" : String(value);
  return `<article class="metric-card"><div class="metric-top"><span>${esc(label)}</span><span class="metric-symbol">${icon}</span></div><div class="metric-value">${esc(formatted)} <small>${esc(unit)}</small></div><div class="metric-sub">${esc(safeDetail)}</div></article>`;
}
function liveReadingMetric(label, categoryId, icon) {
  const equipment = state.equipment.find(item => item.category === categoryId && !isSimulated(item));
  const reading = equipment?.readings?.find(item => item && item.value !== null && item.value !== undefined);
  const value = reading ? reading.value : null;
  const detail = reading
    ? `${equipment.name || equipment.id} · ${reading.field || "leitura"} · ${reading.trust || "UNKNOWN"}`
    : "Sem leitura válida do Gateway";
  return metric(label, value, reading?.unit || "", icon, detail);
}
function chart() {
  if (state.mode !== "SIMULATED") return `<div class="empty-state">O Gateway atual não fornece uma série temporal para este gráfico. Não são inventados pontos de histórico.</div>`;
  return `<svg class="chart" viewBox="0 0 620 190" role="img" aria-label="Gráfico ilustrativo de produção solar simulada"><defs><linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#dcc99c" stop-opacity=".30"/><stop offset="100%" stop-color="#dcc99c" stop-opacity="0"/></linearGradient></defs><path class="chart-grid" d="M42 25H605 M42 65H605 M42 105H605 M42 145H605"/><path class="chart-area" d="M42 128 C75 125 90 111 122 118 S168 92 198 97 S245 70 276 82 S320 42 350 58 S399 72 430 47 S475 35 505 49 S565 28 605 37 L605 146 L42 146Z"/><path class="chart-line" d="M42 128 C75 125 90 111 122 118 S168 92 198 97 S245 70 276 82 S320 42 350 58 S399 72 430 47 S475 35 505 49 S565 28 605 37"/><g class="chart-label"><text x="42" y="166">08:00</text><text x="176" y="166">10:00</text><text x="309" y="166">12:00</text><text x="443" y="166">14:00</text><text x="575" y="166">16:00</text><text x="42" y="15">kW · CURVA ILUSTRATIVA</text></g></svg>`;
}
function flowPanel() {
  const totals = demoTotals();
  const rows = state.mode === "SIMULATED" ? [
    ["ϟ", "Produção solar", "Valor ilustrativo", `${totals.solar ?? "—"} kW`],
    ["▤", "Bateria", `Reserva pretendida ${state.demoControls.batteryReserve}%`, `${totals.battery ?? "—"}%`],
    ["▦", "Mineradora", `Carga demonstrativa ${state.demoControls.minerLoad}%`, `${totals.miner ?? "—"} kW`],
    ["↗", "Carregamento EV", state.demoControls.evEnabled ? "Simulação ativa" : "Simulação em pausa", `${totals.ev ?? "—"} kW`],
  ] : state.equipment.slice(0,4).map(x => [CATEGORIES.find(c=>c.id===x.category)?.icon || "•", x.name, x.connection_state || x.status || "Estado desconhecido", `${formatReading(x.readings?.[0]).value} ${formatReading(x.readings?.[0]).unit}`]);
  return `<div class="flow-list">${rows.map(r=>`<div class="flow-row"><div class="flow-icon">${esc(r[0])}</div><div><div class="flow-name">${esc(r[1])}</div><div class="flow-detail">${esc(r[2])}</div></div><div class="flow-value">${esc(r[3])}<small>${state.mode === "SIMULATED" ? "SIMULATED" : esc(state.dataStatus)}</small></div></div>`).join("")}</div>`;
}
function demoControlPanel(categoryId) {
  if (state.mode !== "SIMULATED") return "";
  const controls = DEMO_CONTROL_CONFIG[categoryId];
  if (!controls) return "";
  if (controls.toggle) {
    const on = state.demoControls[controls.key];
    return `<section class="panel demo-control-panel"><div class="panel-header"><div><p class="eyebrow">EXPERIÊNCIA INTERATIVA</p><h2>${esc(controls.title)}</h2></div><span class="demo-only-tag">LOCAL ONLY</span></div><div class="toggle-row"><div><strong>${esc(controls.label)}</strong><p>${esc(controls.note)}</p></div><button type="button" class="demo-toggle ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(controls.label)}" data-demo-toggle="${esc(controls.key)}"><span></span></button></div><p class="control-footnote">DEMO · NÃO É UM COMANDO REAL</p></section>`;
  }
  const value = state.demoControls[controls.key];
  return `<section class="panel demo-control-panel"><div class="panel-header"><div><p class="eyebrow">EXPERIÊNCIA INTERATIVA</p><h2>${esc(controls.title)}</h2></div><span class="demo-only-tag">LOCAL ONLY</span></div><div class="range-heading"><label for="control-${esc(controls.key)}">${esc(controls.label)}</label><output id="value-${esc(controls.key)}">${esc(value)} ${esc(controls.unit)}</output></div><input class="demo-range" id="control-${esc(controls.key)}" type="range" min="${controls.min}" max="${controls.max}" step="${controls.step}" value="${value}" data-demo-control="${esc(controls.key)}" aria-label="${esc(controls.label)}"><div class="range-scale"><span>${controls.min} ${esc(controls.unit)}</span><span>${controls.max} ${esc(controls.unit)}</span></div><p class="control-note">${esc(controls.note)}</p><p class="control-footnote">DEMO · NÃO É UM COMANDO REAL</p></section>`;
}
function skyData() {
  return ({"limpo":{icon:"☀️",temp:"24°",label:"Limpo",feel:"26° · 55% · 9 km/h"},"pouco nublado":{icon:"⛅",temp:"22°",label:"Pouco nublado",feel:"24° · 67% · 12 km/h"},"muito nublado":{icon:"☁️",temp:"19°",label:"Muito nublado",feel:"19° · 78% · 15 km/h"},"tempestade":{icon:"⛈️",temp:"17°",label:"Trovoada",feel:"16° · 88% · 22 km/h"}})[state.sky];
}
function miniChart() {
  return `<svg class="mini-chart" viewBox="0 0 300 58" role="img" aria-label="Gráfico ilustrativo de produção solar simulada"><path d="M0 51 C25 49 38 40 62 43 S100 20 128 30 S170 7 198 16 S240 27 300 5 L300 58 L0 58Z" fill="#dcc99c" fill-opacity=".13"/><path d="M0 51 C25 49 38 40 62 43 S100 20 128 30 S170 7 198 16 S240 27 300 5" fill="none" stroke="#dcc99c" stroke-width="1.8" stroke-linecap="round"/></svg>`;
}
function allDemoDevices(){return workspace.house.floors.flatMap(f=>f.rooms.flatMap(r=>r.devices.map(d=>({...d,room:r.name,floor:f.name,roomId:r.id,floorId:f.id}))));}
function favoriteDeviceCards() {
  const all=allDemoDevices(); const favorites=Array.isArray(workspace.prefs.favoriteDeviceIds)?workspace.prefs.favoriteDeviceIds:['dev-light-living','dev-blind-living'];
  workspace.prefs.favoriteDeviceIds=favorites.filter(id=>all.some(d=>d.id===id));
  const selected=all.filter(d=>workspace.prefs.favoriteDeviceIds.includes(d.id));
  const deviceIcon=d=>d.type==='blind'?'▥':d.type==='light'?'✦':d.type==='socket'?'⌁':d.type==='sensor'?'⌁':'⌂';
  const deviceState=d=>d.state===true?'Ligado':d.state===false?'Desligado':d.state==='open'?'Aberto':d.state==='closed'?'Fechado':'Sem estado';
  return `<div class="favorite-manage"><label for="home-favorite-add">Adicionar favorito</label><select id="home-favorite-add"><option value="">Escolher dispositivo…</option>${all.filter(d=>!workspace.prefs.favoriteDeviceIds.includes(d.id)).map(d=>`<option value="${esc(d.id)}">${esc(d.name)} · ${esc(d.room)}</option>`).join('')}</select><button type="button" class="button secondary" id="home-favorite-add-button">Adicionar</button></div>${selected.length?selected.map(d=>`<article class="favorite-device"><div class="favorite-device-icon" aria-hidden="true">${deviceIcon(d)}</div><div class="favorite-device-info"><strong>${esc(d.name)}</strong><span>${esc(d.room)} · ${esc(d.floor)}</span><small>DEMO · CONTROLO LOCAL</small></div><div class="favorite-device-actions"><span class="favorite-state ${d.state===true||d.state==='open'?'on':d.state===false||d.state==='closed'?'off':'unknown'}">${deviceState(d)}</span><button type="button" class="favorite-control" data-favorite-toggle="${esc(d.id)}" aria-label="${d.type==='blind'?'Alternar estore':'Alternar '+esc(d.name)}">${d.type==='blind'?(d.state==='open'?'Fechar':'Abrir'):(d.state===true?'Desligar':'Ligar')}</button></div><button type="button" class="favorite-remove" data-favorite-remove="${esc(d.id)}" aria-label="Remover ${esc(d.name)} dos favoritos">×</button></article>`).join(''):'<p class="field-note">Ainda não há favoritos. Escolhe um dispositivo acima.</p>'}`;
}
function openProductionDialog(){
  const dialog=$("#production-dialog");
  const body=dialog?.querySelector('.dialog-body');
  if(!dialog||!body)return;
  const template=document.createElement('template');
  template.innerHTML=renderSolarProductionPage();
  const kpis=template.content.querySelector('.ws-kpi-grid');
  const graph=template.content.querySelector('.feature-panel');
  body.replaceChildren();
  if(kpis)body.append(kpis.cloneNode(true));
  if(graph)body.append(graph.cloneNode(true));
  const heading=dialog.querySelector('.dialog-header h2');
  if(heading)heading.textContent='Produção detalhada';
  if(dialog.open)dialog.close();
  dialog.showModal();
}
function applyLiveFontScale(){
  const scale=({small:.9,normal:1,large:1.13,xlarge:1.27})[document.documentElement.dataset.font]||1;
  const nodes=[...document.querySelectorAll('.app-shell :is(h1,h2,h3,h4,p,span,strong,small,label,button,a,output,li,em,b,td,th,legend), dialog :is(h1,h2,h3,h4,p,span,strong,small,label,button,a,output,li,em,b,td,th,legend)')];
  for(const el of nodes){
    if(!el.dataset.fontBaseSize){el.dataset.fontBaseSize=getComputedStyle(el).fontSize;}
    const base=parseFloat(el.dataset.fontBaseSize);
    if(Number.isFinite(base))el.style.fontSize=`${Math.max(9,base*scale)}px`;
  }
}
function toggleFavoriteDevice(id){
  for(const floor of workspace.house.floors)for(const room of floor.rooms){
    const device=room.devices.find(d=>d.id===id);if(!device)continue;
    if(device.type==='blind')device.state=device.state==='open'?'closed':'open';
    else if(['light','socket','switch','plug'].includes(device.type))device.state=device.state===true?false:true;
    else return false;
    saveDemoWorkspace();render();return true;
  }
  return false;
}
function renderOverview() {
  if (state.mode !== "SIMULATED") {
    const cards = state.equipment.map(card).join("") || `<div class="empty-state">Ainda não há equipamentos ou leituras registados no Gateway. Não são apresentados valores de demonstração nesta PWA.</div>`;
    const updated = state.lastUpdated ? `Atualizado ${currentTimeLabel(state.lastUpdated)}` : "À espera de leituras";
    return `<div class="page-heading"><div><p class="eyebrow">ENERGIA DA PROPRIEDADE</p><h1>Home</h1><p>Produção solar, bateria, mineradoras e carregamento do veículo num só resumo.</p></div><div class="date-block"><strong>${esc(state.dataStatus)}</strong><br>${esc(updated)}</div></div>
      <div class="metric-grid">${liveReadingMetric("Inversor", "inversores", "ϟ")}${liveReadingMetric("Bateria", "baterias", "▤")}${liveReadingMetric("Mineradora", "mineradoras", "▦")}${liveReadingMetric("Veículo elétrico", "ev", "↗")}</div>
      <div class="content-grid"><section class="panel chart-panel"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO</p><h2>Fluxo de energia</h2><p>O Gateway ainda não fornece uma série temporal para o gráfico.</p></div><span class="source-tag">${esc(state.dataStatus)}</span></div>${chart()}</section><section class="panel flow-panel"><div class="panel-header"><div><p class="eyebrow">AGORA</p><h2>Equipamentos ativos</h2></div><button class="text-link" type="button" id="live-refresh">Atualizar ↻</button></div>${flowPanel()}</section></div>
      <div class="section-heading section-heading-spaced"><div><p class="eyebrow">INSTALAÇÃO</p><h2>Equipamentos e leituras</h2></div><span class="muted-inline">${state.equipment.length} equipamentos</span></div><div class="equipment-grid">${cards}</div>`;
  }
  const totals = demoTotals();
  const allCards = state.equipment.map(card).join("") || `<div class="empty-state">Ainda não existem equipamentos configurados no Gateway.</div>`;
  const photoStyle = state.propertyPhoto ? "has-property-photo" : "photo-placeholder";
  const sky = skyData();
  return `<section class="property-hero ${photoStyle}" id="property-hero" data-ws-editable="house" tabindex="0" aria-label="Casa. Duplo clique para abrir detalhe; mantenha premido para editar"><div class="hero-shade"></div><div class="hero-content"><div class="reference-hero-top"><span class="hero-kicker"><i></i> <span id="home-property-name">${esc(workspace.house.name || "A Minha Casa")}</span></span><button class="hero-photo-button" id="hero-photo-settings">EDITAR CASA</button></div><div><h1>${esc(workspace.house.name || "A Minha Casa")}</h1><p>${esc(workspace.house.description || "Identidade da propriedade · DEMO")}</p></div></div><div class="hero-caption"><span>DEMO ONLY</span><strong>${state.propertyPhoto ? "Fotografia personalizada" : "Personaliza a fotografia"}</strong></div></section>
  ${renderHomePreferenceLinks()}
  ${state.mode === "SIMULATED" ? `<div class="status-banner demo-banner"><span class="demo-stamp">DEMO</span><span><strong>Ambiente demonstrativo ativo.</strong> Todos os valores e controlos são simulados. Nada é enviado para equipamentos físicos, nem existem escritas Modbus.</span></div>` : ""}
  <div class="reference-home-grid"><button type="button" class="reference-card weather-card" id="open-weather"><span class="label">CLIMA · SIMULADO</span><strong class="reference-big" id="weather-temperature">${sky.temp}</strong><span class="weather-condition"><b id="weather-icon">${sky.icon}</b><span><strong id="weather-label">${sky.label}</strong><small id="weather-feels">Sensação ${sky.feel}</small></span></span><span class="weather-chip" id="weather-chip">${sky.label}</span></button><button type="button" class="reference-card production-card" id="open-production"><span class="label">PRODUÇÃO <small>detalhe ↗</small></span><strong class="production-value">4,2 <small>kW</small></strong><span class="label">AGORA · ${esc(sky.label.toUpperCase())}</span>${miniChart()}<span class="reference-demo-note">CURVA SIMULADA</span></button>
  <section class="reference-card favorite-card full"><div class="favorite-heading"><span class="label">DISPOSITIVOS FAVORITOS</span><span class="local-tag">LOCAL ONLY</span></div><div class="favorite-device-grid">${favoriteDeviceCards()}</div><p class="control-footnote">Controlos cenográficos: alteram apenas esta interface, sem ligação a dispositivos.</p></section></div>
  <div class="section-heading"><div><p class="eyebrow">RESUMO DO SISTEMA</p><h2>O seu balanço energético</h2></div><span class="live-label"><i></i>${state.mode === "SIMULATED" ? "DADOS SIMULADOS" : `${esc(state.dataStatus)} · GATEWAY`}</span></div>
  <div class="metric-grid">${metric("Produção solar", totals.solar, "kW", "ϟ", state.mode === "SIMULATED" ? "Exemplo · não é leitura real" : "Última leitura disponível")}${metric("Carga da bateria", totals.battery, "%", "▤", state.mode === "SIMULATED" ? "Valor ilustrativo" : "Última leitura disponível")}${metric("Consumo mineradoras", totals.miner, "kW", "▦", state.mode === "SIMULATED" ? "Valor ilustrativo" : "Última leitura disponível")}${metric("Carregamento EV", totals.ev, "kW", "↗", state.mode === "SIMULATED" ? "Sem ligação física" : "Última leitura disponível")}</div>
  <div class="content-grid"><section class="panel chart-panel"><div class="panel-header"><div><p class="eyebrow">FLUXO DE ENERGIA</p><h2>Produção ao longo do dia</h2><p>${state.mode === "SIMULATED" ? "Curva visual fictícia para explorar o design" : "Histórico indisponível no contrato API atual"}</p></div><span class="source-tag">${state.mode === "SIMULATED" ? "SIMULATED" : esc(state.dataStatus)}</span></div>${chart()}<div class="legend"><span><i></i>Produção solar</span><span><i class="blue-dot"></i>Consumo total</span></div></section><section class="panel flow-panel"><div class="panel-header"><div><p class="eyebrow">ESTADO ATUAL</p><h2>Onde está a energia</h2></div><button class="text-link" data-page="baterias">Ver sistema ↗</button></div>${flowPanel()}</section></div>
  <div class="section-heading section-heading-spaced"><div><p class="eyebrow">SEIS ÁREAS INTEGRADAS</p><h2>Explore a sua instalação</h2></div><span class="muted-inline">${state.equipment.length} perfis · ${state.mode}</span></div><div class="equipment-grid">${allCards}</div>
  ${state.mode === "SIMULATED" ? `<section class="panel demo-shortcuts"><div><p class="eyebrow">EXPERIMENTE</p><h2>Configure cenários sem risco</h2><p>Entre em qualquer área para experimentar os controlos locais. Os valores não são enviados para o Gateway.</p></div><button class="button secondary" data-page="ev">Experimentar controlos <span>↗</span></button></section>` : ""}`;
}
function renderCategory(categoryId) {
  const category = CATEGORIES.find(c => c.id === categoryId);
  const equipment = state.equipment.filter(item => item.category === categoryId);
  const item = equipment[0];
  const reading = item ? formatReading(item.readings?.[0]) : {value:"—",unit:"",valid:false};
  return `<div class="page-heading"><div><p class="eyebrow">A SUA PROPRIEDADE / ÁREAS</p><h1>${esc(category.label)}</h1><p>${esc(category.description)}. Explore os dados e o cenário associado.</p></div><div class="date-block"><strong>${equipment.length ? "Perfil demonstrativo" : "Sem perfil"}</strong><br>${state.mode}</div></div>
  ${state.mode === "SIMULATED" ? `<div class="status-banner demo-banner"><span class="demo-stamp">DEMO</span><span>Perfil ilustrativo, sem ligação física. Os valores não são leituras reais e os controlos abaixo só alteram a interface local.</span></div>` : state.dataStatus !== "LIVE" ? `<div class="status-banner demo-banner"><span class="demo-stamp">${esc(state.dataStatus)}</span><span>${state.dataStatus === "STALE" ? "A última leitura é antiga e não deve ser tratada como estado atual." : state.dataStatus === "UNKNOWN" ? "O Gateway respondeu, mas não existe uma leitura válida para este equipamento." : "A consulta ao Gateway não confirmou dados atuais."}</span></div>` : ""}
  <div class="category-feature"><div class="category-feature-icon">${esc(category.icon)}</div><div class="category-feature-main"><p class="eyebrow">${esc(category.label.toUpperCase())}</p><h2>${esc(item?.name || "Perfil por configurar")}</h2><p>${esc(item ? [item.manufacturer,item.model].filter(Boolean).join(" · ") : "O Gateway ainda não disponibiliza um equipamento nesta área.")}</p></div><div class="category-feature-value"><strong>${esc(reading.value)} <small>${esc(reading.unit)}</small></strong><span>${state.mode === "SIMULATED" ? "VALOR SIMULADO" : reading.valid ? "LEITURA DO GATEWAY" : "SEM LEITURA"}</span></div></div>
  ${demoControlPanel(categoryId)}
  <div class="section-heading section-heading-spaced"><div><p class="eyebrow">DETALHE</p><h2>Estado e proveniência</h2></div><span class="source-tag">${state.mode}</span></div>
  ${equipment.length ? equipment.map(item=>`<section class="panel detail-panel"><div class="panel-header"><div><h2>${esc(item.name)}</h2><p>Informação de origem e estado</p></div><span class="source-tag">${isSimulated(item)?"SIMULATED":esc(item.readings?.[0]?.trust||"UNKNOWN")}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Fabricante / modelo</small><strong>${esc([item.manufacturer,item.model].filter(Boolean).join(" · ")||"Não definido")}</strong></div><div class="detail-item"><small>Ligação</small><strong>${esc(item.connection_state||"UNKNOWN")}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(timeLabel(item.last_communication_at))}</strong></div><div class="detail-item"><small>Origem</small><strong>${esc(item.source||item.readings?.[0]?.source||"API_GATEWAY")}</strong></div><div class="detail-item"><small>Confiança</small><strong>${esc(item.readings?.[0]?.trust||"UNKNOWN")}</strong></div><div class="detail-item"><small>Última leitura</small><strong>${esc(reading.value)} ${esc(reading.unit)}</strong></div></div><div class="status-banner demo-banner"><span class="demo-stamp">INFO</span><span>Estado de comando: <strong>NÃO DISPONÍVEL</strong>. Esta PWA não disponibiliza controlos reais de equipamentos.</span></div></section>`).join("") : `<div class="empty-state">Não existem equipamentos nesta área no Gateway. Nenhum valor foi inventado.</div>`}`;
}
function render() {
  freshness();
  $("#breadcrumb").textContent = `A SUA PROPRIEDADE / ${pageLabel(state.page).toUpperCase()}`;
  const ownerPage = $("#gateway-owner-page");
  const isOwnerPage = state.page === "owner";
  if (ownerPage) ownerPage.hidden = !isOwnerPage;
  $("#page-content").hidden = isOwnerPage;
  if (isOwnerPage) {
    const info = sessionInfo();
    ownerPage.hidden = !info.authenticated || info.user.role !== "owner";
    if (ownerPage.hidden) { state.page = "inicio"; $("#page-content").hidden = false; }
    else {
      document.querySelectorAll("[data-page]").forEach(el => el.classList.toggle("active", el.dataset.page === "owner"));
      document.querySelectorAll("#mobile-nav button[data-action]").forEach(el => el.classList.toggle("active", el.dataset.action === "owner"));
      return;
    }
  }
  const workspacePage = renderWorkspacePage(state.page);
  const gatewayBackedPages = ["inicio", ...CATEGORIES.map(c => c.id)];
  let pageHtml;
  if (state.mode !== "SIMULATED" && !gatewayBackedPages.includes(state.page)) {
    pageHtml = `<div class="page-heading"><div><p class="eyebrow">FUNÇÃO NÃO DISPONÍVEL NO GATEWAY ATUAL</p><h1>${esc(pageLabel(state.page))}</h1><p>Esta área ainda não tem um contrato de dados ou comandos físicos no Gateway. Para evitar confusão, a sessão autenticada não apresenta controlos ou valores de demonstração aqui.</p></div></div><div class="empty-state">Sem dados reais fornecidos pelo Gateway para esta área. A administração está na página Owner.</div>`;
  } else {
    pageHtml = state.page === "inicio" ? renderOverview() : (workspacePage || (CATEGORIES.some(c=>c.id===state.page) ? renderCategory(state.page) : renderOverview()));
    if(state.page === "automatismos") pageHtml = renderAutomationsPage(workspace, automationEditingId);
    if(state.page === "producao") pageHtml = renderSolarProductionPage();
    if(state.page === "profile") pageHtml += renderDemoAdminPanel();
  }
  $("#page-content").innerHTML = pageHtml;
  applyPreferences();
  applyLiveFontScale();
  const hero = $("#property-hero");
  if (hero && (workspace.house.photo || state.propertyPhoto)) hero.style.backgroundImage = `linear-gradient(90deg, rgba(9,9,9,.88) 0%, rgba(9,9,9,.62) 58%, rgba(9,9,9,.22) 100%), url("${workspace.house.photo || state.propertyPhoto}")`;
  if (state.page === "casa" && workspace.house.photo) document.documentElement.style.setProperty("--house-background-image", `url("${workspace.house.photo}")`); else document.documentElement.style.removeProperty("--house-background-image");
  document.querySelectorAll("[data-page]").forEach(el => el.classList.toggle("active", el.dataset.page === state.page));
  const mobilePage = { home: "inicio", house: "casa", profile: "profile", energy: "energia", devices: "devices", automations: "automatismos", owner: "owner" };
  document.querySelectorAll("#mobile-nav button[data-action]").forEach(el => el.classList.toggle("active", mobilePage[el.dataset.action] === state.page));
  $("#refresh-button").disabled = state.refreshing;
  if (state.page === "ev") refreshTeslaEvConfig().catch(error => { const target = $("#ev-tesla-status"); if (target) target.textContent = "Não foi possível consultar a configuração Tesla: " + error.message; });
}
function navigate(page) {
  if (page === "mais") { populateMore(); $("#more-dialog").showModal(); return; }
  if (page === "owner" && (!sessionInfo().authenticated || sessionInfo().user.role !== "owner")) return;
  if (!["inicio", ...CATEGORIES.map(c=>c.id), "energia", "casa", "profile", "engine", "devices", "paineis-solares", "automatismos", "producao", "owner"].includes(page)) return;
  state.page = page; render(); if(page==="casa" && workspace.house.restoreScroll){const y=Number(workspace.house.returnScrollY||0);workspace.house.restoreScroll=false;requestAnimationFrame(()=>window.scrollTo({top:y,behavior:"auto"}));}else window.scrollTo({top:0,behavior:"smooth"});
}
function populateMore() { $("#more-links").innerHTML = [{id:"energia",label:"Energia",icon:"◉"},{id:"casa",label:"Casa",icon:"⌂"},{id:"engine",label:"Engine",icon:"⌘"},{id:"profile",label:"Profile",icon:"○"},{id:"devices",label:"Devices",icon:"⚙"},{id:"automatismos",label:"Automatismos",icon:"⟳"},{id:"producao",label:"Produção solar",icon:"☼"},...CATEGORIES,{id:"paineis-solares",label:"Painéis solares",icon:"☼"}].map(c=>`<button data-page="${esc(c.id)}"><span>${esc(c.icon)}</span>${esc(c.label)}<span class="more-arrow">↗</span></button>`).join("") + `<button id="more-settings"><span>⚙</span>Personalizar demonstração<span class="more-arrow">↗</span></button>`; $("#more-settings").addEventListener("click",()=>{$("#more-dialog").close();$("#settings-dialog").showModal();}); }

document.querySelectorAll(".sidebar [data-page]").forEach(el=>el.addEventListener("click",()=>navigate(el.dataset.page)));
window.addEventListener("solar-workspace-updated",(event)=>{if(event.detail?.photosHydrated){state.propertyPhoto=workspace.house.photo||state.propertyPhoto||readStoredPhoto();}render();if(event.detail?.persisted===false||event.detail?.photosPersisted===false){setTimeout(()=>{const notice=$("#notice");notice.hidden=false;notice.textContent="O browser não confirmou a gravação local. Mantém esta página aberta e verifica as permissões/armazenamento do browser.";},0);}});
let holdTimer=null, holdTarget=null, holdStart=null, suppressClickUntil=0;
function cancelHold(){if(holdTimer)clearTimeout(holdTimer);holdTimer=null;holdTarget=null;holdStart=null;}
function editTargetFrom(el){if(!el)return null;const type=el.dataset.wsEditable;if(type==='house')return {type:'house',id:'house'};if(type==='room')return {type:'room',id:el.dataset.room};if(type==='device')return {type:'device',id:el.dataset.device};if(type==='floor')return {type:'floor',id:el.dataset.floor};return null;}
$('#page-content').addEventListener('pointerdown',e=>{const target=e.target.closest('[data-ws-editable]');if(!target||(e.target.closest('button,input,select,textarea,a,[role="switch"]')&&!e.target.closest('.ws-room-image,.ws-device-open,.ws-floor-tabs [data-ws-editable],.ws-horizontal-tabs [data-ws-editable]')))return;cancelHold();holdTarget=target;holdStart={x:e.clientX,y:e.clientY};holdTimer=setTimeout(()=>{const context=editTargetFrom(holdTarget);if(context){suppressClickUntil=Date.now()+800;openContextEditor(context.type,context.id);}cancelHold();},2000);});
$('#page-content').addEventListener('pointermove',e=>{if(!holdStart)return;if(Math.abs(e.clientX-holdStart.x)>12||Math.abs(e.clientY-holdStart.y)>12)cancelHold();},{passive:true});
for(const eventName of ['pointerup','pointercancel','pointerleave'])$('#page-content').addEventListener(eventName,cancelHold,{passive:true});
window.addEventListener('scroll',cancelHold,{passive:true});
$('#page-content').addEventListener('contextmenu',e=>{const target=e.target.closest('[data-ws-editable]');if(!target)return;e.preventDefault();const context=editTargetFrom(target);if(context)openContextEditor(context.type,context.id);});
$('#page-content').addEventListener('keydown',e=>{if(e.key!=='F10'||!e.shiftKey)return;const target=e.target.closest('[data-ws-editable]');if(!target)return;e.preventDefault();const context=editTargetFrom(target);if(context)openContextEditor(context.type,context.id);});
$('#page-content').addEventListener('click',e=>{if(Date.now()<suppressClickUntil){e.preventDefault();e.stopImmediatePropagation();return;}const target=e.target.closest('[data-ws-editable]');if(!target||(e.target.closest('button,input,select,textarea,a,[role="switch"]')&&!e.target.closest('.ws-room-image,.ws-device-open,.ws-floor-tabs [data-ws-editable],.ws-horizontal-tabs [data-ws-editable]')))return;const context=editTargetFrom(target);if(!context)return;if(context.type==='room'){workspace.house.returnScrollY=window.scrollY;const floor=target.dataset.floor,room=target.dataset.room;handleWorkspaceAction('open-room',{dataset:{wsAction:'open-room',floor,room}});navigate('casa');}else if(context.type==='device'){workspace.house.returnScrollY=window.scrollY;const device=target.dataset.device;handleWorkspaceAction('open-device',{dataset:{wsAction:'open-device',device}});navigate('casa');}else if(context.type==='house')navigate('casa');},true);
$('#page-content').addEventListener('dblclick',e=>{const target=e.target.closest('[data-ws-editable]');if(!target)return;const context=editTargetFrom(target);if(context?.type==='room'){handleWorkspaceAction('open-room',{dataset:{wsAction:'open-room',floor:target.dataset.floor,room:target.dataset.room}});navigate('casa');}else if(context?.type==='device'){handleWorkspaceAction('open-device',{dataset:{wsAction:'open-device',device:target.dataset.device}});navigate('casa');}});
$('#page-content').addEventListener('click',e=>{const toggle=e.target.closest('[data-favorite-toggle]');if(toggle){toggleFavoriteDevice(toggle.dataset.favoriteToggle);return;}const remove=e.target.closest('[data-favorite-remove]');if(remove){workspace.prefs.favoriteDeviceIds=(workspace.prefs.favoriteDeviceIds||['dev-light-living','dev-blind-living']).filter(id=>id!==remove.dataset.favoriteRemove);saveDemoWorkspace();render();return;}if(e.target.closest('#home-favorite-add-button')){const select=$('#home-favorite-add');if(select?.value){workspace.prefs.favoriteDeviceIds=[...new Set([...(workspace.prefs.favoriteDeviceIds||['dev-light-living','dev-blind-living']),select.value])];saveDemoWorkspace();render();}return;}});

$("#mobile-nav").addEventListener("click", e => {
  const button=e.target.closest("button[data-action]"); if(!button) return;
  document.querySelectorAll("#mobile-nav button").forEach(b=>b.classList.toggle("active",b===button));
  const action=button.dataset.action;
  if(action==="home"){navigate("inicio");}
  else if(action==="house"){navigate("casa");}
  else if(action==="profile"){navigate("profile");}
  else if(action==="energy"){navigate("energia");}
  else if(action==="devices"){navigate("devices");}
  else if(action==="automations"){navigate("automatismos");}
  else if(action==="owner"){navigate("owner");}
});
$("#page-content").addEventListener("submit", e => {
  if(e.target.id === "auto-form") { e.preventDefault(); if(saveAutomationForm(e.target,workspace)){automationEditingId="";render();showFeatureNotice("Automatismo guardado na demonstração local. Nenhum comando foi enviado.");} return; }
  if(e.target.id === "demo-user-form") { e.preventDefault(); if(addDemoUser(e.target)){render();showFeatureNotice("Utilizador fictício adicionado. Não foi criada uma conta real.");} return; }
  const userEdit=e.target.closest('form[data-demo-user-edit]');if(userEdit){e.preventDefault();if(saveDemoUserEdit(userEdit,userEdit.dataset.demoUserEdit)){render();showFeatureNotice('Utilizador fictício atualizado localmente.');}return;}
});
function showFeatureNotice(message){const n=$("#notice");n.hidden=false;n.textContent=message;setTimeout(()=>n.hidden=true,4500);}
$("#page-content").addEventListener("change", e => {
  const fontPref=e.target.closest('[data-ws-field="prefs.font"]');if(fontPref){document.documentElement.dataset.font=fontPref.value;applyLiveFontScale();return;}
  const toggle=e.target.closest("[data-rule-toggle]"); if(toggle){const r=demoFeatures.automations.find(x=>x.id===toggle.dataset.ruleToggle);if(r){r.enabled=toggle.checked;localStorage.setItem('solar-miner-v053-demo-features-v1',JSON.stringify(demoFeatures));render();showFeatureNotice(r.enabled?'Automatismo ativado apenas na demonstração.':'Automatismo desativado.');}return;}
  if(e.target.id==='solar-weather'){saveSolarWeather(e.target.value);if($('#production-dialog')?.open)openProductionDialog();else render();}
  if(['conditionDevice','sourceType','targetDevice'].includes(e.target.name)){const form=e.target.closest('#auto-form');if(form){const ds=workspace.house.floors.flatMap(f=>f.rooms.flatMap(r=>r.devices));const device=ds.find(d=>d.id===form.elements.conditionDevice.value);const type=form.elements.sourceType.value;const opts=type==='device'?(device?.type==='blind'?[['open','Fica aberto'],['closed','Fica fechado']]:device?.type==='sensor'&&/temp/i.test(device?.name||'')?[['temperature','Temperatura acima/abaixo de limite']]:device?.type==='sensor'?[['motion','Deteta movimento'],['no-motion','Não deteta movimento']]:['light','socket'].includes(device?.type)?[['on','Fica ligado'],['off','Fica desligado']]:[['online','Estado online (se suportado)']]):type==='schedule'?[['time','Hora fixa'],['sunrise','Nascer do Sol'],['sunset','Pôr do Sol']]:type==='weather'?[['temperature','Temperatura exterior'],['rain','Chuva'],['cloud','Nebulosidade']]:[['arrive','Chegar a casa'],['leave','Sair de casa'],['nobody','Ninguém em casa']];if(e.target.name!=='targetDevice')form.elements.conditionType.innerHTML=opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');if(e.target.name==='targetDevice'){const target=ds.find(d=>d.id===form.elements.targetDevice.value);const t=(target?.type||'').toLowerCase(),n=(target?.name||'').toLowerCase();let actions=[['notify','Notificação local simulada']];if(t.includes('blind')||/estore/.test(n))actions=[['open','Abrir (simulado)'],['close','Fechar (simulado)'],...actions];else if(['light','socket','switch','plug'].some(x=>t.includes(x))||/luz|tomada/.test(n))actions=[['on','Ligar (simulado)'],['off','Desligar (simulado)'],...actions];form.elements.action.innerHTML=actions.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');}}}
});
$("#page-content").addEventListener("click", e => {
  const feature=e.target.closest('[data-feature-action]'); if(feature){const action=feature.dataset.featureAction,id=feature.dataset.id||'';if(action==='new-rule'){automationEditingId='';render();return;}if(action==='edit-rule'){automationEditingId=id;render();return;}if(action==='cancel-edit'){automationEditingId='';render();return;}if(action==='add-condition'){const box=$('#extra-conditions');if(box){const row=document.createElement('div');row.className='feature-extra-row';row.innerHTML='<label class="feature-field">Condição adicional<select name="extra"><option value="nobody">Não está ninguém em casa (simulado)</option><option value="weather">Temperatura exterior inferior a 12 °C (simulado)</option><option value="fresh">Dados atualizados (simulado)</option><option value="none">Sem condição adicional</option></select></label><button type="button" class="button secondary" data-feature-action="remove-condition">Remover</button>';box.appendChild(row);}return;}if(action==='remove-condition'){const row=feature.closest('.feature-extra-row');if(row&&$('#extra-conditions .feature-extra-row')?.parentElement?.children.length>1)row.remove();else if(row){const select=row.querySelector('select');if(select)select.value='none';}return;}const result=handleFeatureAction(action,id,workspace);if(result?.edit!==undefined){automationEditingId=result.edit;render();return;}if(result?.cancel){automationEditingId='';render();return;}if(result?.rerender)render();if(result?.message)showFeatureNotice(result.message);return;}
  const workspaceButton=e.target.closest("[data-ws-action]");
  if(workspaceButton){if(['open-room','open-device'].includes(workspaceButton.dataset.wsAction))workspace.house.returnScrollY=window.scrollY;const result=handleWorkspaceAction(workspaceButton.dataset.wsAction,workspaceButton);if(result?.edit)openContextEditor(result.edit.type,result.edit.id);if(result?.navigate)navigate(result.navigate);if(result?.message){const notice=$("#notice");notice.hidden=false;notice.textContent=result.message;setTimeout(()=>{notice.hidden=true;},3500);}if(result?.rerender)render();return;}
  if(e.target.closest("#open-weather")) $("#weather-dialog").showModal();
  if(e.target.closest("#open-production")) openProductionDialog();
  const toggle=e.target.closest("[data-fav-toggle]");
  if(toggle && state.mode==="SIMULATED") {const device=state.favoriteDevices.find(d=>d.id===toggle.dataset.favToggle);if(device){device.pct=device.pct>0?0:75;render();}}
  const photo=e.target.closest("#hero-photo-settings");if(photo) openContextEditor("house","house");
});
$("#page-content").addEventListener("input", e=>{
  const input=e.target.closest("[data-fav-range]");if(!input||state.mode!=="SIMULATED")return;
  const device=state.favoriteDevices.find(d=>d.id===input.dataset.favRange);if(!device)return;
  device.pct=Number(input.value);const card=input.closest(".favorite-device");const out=card.querySelector("output");if(out)out.textContent=`${device.pct}%`;
  const button=card.querySelector("[data-fav-toggle]");if(button){button.textContent=device.pct===0?"OFF":`${device.pct}%`;button.classList.toggle("on",device.pct>0);button.classList.toggle("off",device.pct===0);}
});
function setSky(value){if(!Object.hasOwn({limpo:1,"pouco nublado":1,"muito nublado":1,tempestade:1},value))return;state.sky=value;document.querySelectorAll("[data-sky]").forEach(b=>b.classList.toggle("selected",b.dataset.sky===value));render();}
document.querySelectorAll("[data-sky]").forEach(button=>button.addEventListener("click",()=>setSky(button.dataset.sky)));
$("#production-dialog").addEventListener("change",e=>{if(e.target.id!=="solar-weather")return;saveSolarWeather(e.target.value);openProductionDialog();});

$("#more-links").addEventListener("click",e=>{const btn=e.target.closest("[data-page]");if(btn){$("#more-dialog").close();navigate(btn.dataset.page);}});
$("#open-settings").addEventListener("click",()=>$("#settings-dialog").showModal());
$("#close-demo-settings").addEventListener("click",()=>$("#settings-dialog").close());
$("#refresh-button").addEventListener("click",()=>{if(sessionInfo().authenticated) refreshGatewayReadings(); else render();});
$("#page-content").addEventListener("input",e=>{
  const pref=e.target.closest('[data-ws-field^="prefs."]');if(pref){const field=pref.dataset.wsField.split(".")[1];if(field==="font"){document.documentElement.dataset.font=pref.value;applyLiveFontScale();}if(field==="theme")document.documentElement.dataset.theme=pref.value;if(field==="accent")document.documentElement.style.setProperty("--gold",pref.value);if(field==="menu")document.documentElement.style.setProperty("--gold-2",pref.value);if(field==="selected")document.documentElement.style.setProperty("--ws-selected",pref.value);return;}
  const search=e.target.closest("#ws-house-search");if(search){const term=search.value;const results=$("#ws-search-results");if(results){results.hidden=!term.trim();results.innerHTML=renderHouseSearch(term);}const grid=$("#ws-room-grid");if(grid)grid.hidden=Boolean(term.trim());return;}
  const input=e.target.closest("[data-demo-control]");
  if(!input || state.mode!=="SIMULATED") return;
  const key=input.dataset.demoControl;
  const numeric=Number(input.value);
  if(!updateDemoControl(state.mode,state.demoControls,key,numeric)) return;
  const output=$("#value-"+key);
  if(output) output.textContent=`${numeric} ${key==="aqsTarget"||key==="floorTarget"?"°C":key==="batteryReserve"||key==="minerLoad"?"%":"kW"}`;
  const label=$("#page-content .control-footnote");
  if(label) label.textContent="DEMO · ALTERAÇÃO LOCAL · NENHUM COMANDO ENVIADO";
});
$("#page-content").addEventListener("click",e=>{
  const toggle=e.target.closest("[data-demo-toggle]");
  if(!toggle || state.mode!=="SIMULATED") return;
  const key=toggle.dataset.demoToggle;
  if(!toggleDemoControl(state.mode,state.demoControls,key)) return;
  render();
});
$("#property-photo-file").addEventListener("change",async e=>{
  const file=e.target.files?.[0]; const result=$("#photo-result");
  if(!file) return;
  if(!file.type.startsWith("image/")){result.textContent="Escolhe um ficheiro de imagem válido.";return;}
  if(file.size>12*1024*1024){result.textContent="A imagem deve ter menos de 12 MB.";return;}
  try {
    const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error("Não foi possível ler a imagem."));reader.readAsDataURL(file);});
    const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error("O ficheiro não parece ser uma imagem válida."));img.src=dataUrl;});
    const scale=Math.min(1,1400/Math.max(image.naturalWidth,image.naturalHeight));
    const canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
    const context=canvas.getContext("2d");if(!context) throw new Error("O browser não disponibilizou o processamento local de imagem.");
    context.drawImage(image,0,0,canvas.width,canvas.height);
    const compressed=canvas.toDataURL("image/jpeg",.76);
    if(compressed.length>2_500_000) throw new Error("A imagem continua demasiado grande depois de comprimida. Escolhe uma fotografia mais pequena.");
    state.propertyPhoto=compressed;workspace.house.photo=compressed;const saved=saveDemoWorkspace();try{localStorage.removeItem("solar-miner-demo-property-photo-v1");}catch{}result.textContent=saved?"Fotografia guardada neste browser; usada também em CASA.":"A fotografia ficou apenas nesta sessão: o browser recusou guardar as preferências.";render();
  } catch(error){result.textContent=error.message||"Não foi possível guardar a fotografia.";}
});
$("#remove-property-photo").addEventListener("click",()=>{try{state.propertyPhoto="";workspace.house.photo="";try{localStorage.removeItem("solar-miner-demo-property-photo-v1");}catch{}const saved=saveDemoWorkspace();$("#photo-result").textContent=saved?"Fotografia removida deste browser.":"Fotografia removida da sessão; a persistência local não foi confirmada.";render();}catch{$("#photo-result").textContent="O browser não permitiu remover a fotografia.";}});
$("#page-content").addEventListener("click",e=>{
  if(e.target.closest("#live-refresh")){refreshGatewayReadings();return;}
  if(e.target.closest("#open-owner-management")){$("#gateway-dialog").showModal();return;}
  const btn=e.target.closest("[data-page]");if(btn)navigate(btn.dataset.page);
});
$("#page-content").addEventListener("change",e=>handleWorkspaceChange(e));
state.propertyPhoto=workspace.house.photo || readStoredPhoto(); if(state.propertyPhoto && !workspace.house.photo){workspace.house.photo=state.propertyPhoto;saveDemoWorkspace();}try{localStorage.removeItem("solar-miner-demo-property-photo-v1");}catch{}
$("#open-gateway-dialog").addEventListener("click",()=>$("#gateway-dialog").showModal());
$("#close-gateway-dialog").addEventListener("click",()=>$("#gateway-dialog").close());
$("#gateway-check").addEventListener("click",async()=>{
  const field=$("#gateway-endpoint");
  try {
    const primary=validateGatewayUrl(field.value,{allowLocalHttp:location.hostname==="localhost"||location.hostname==="127.0.0.1"});
    const candidates=[primary.origin];
    try {
      if(classifyEndpoint(primary.origin)==="CANDIDATE_LAN") localStorage.setItem("solarminer-gateway-lan-endpoint-v1",primary.origin);
      const localFallback=localStorage.getItem("solarminer-gateway-lan-endpoint-v1");
      if(localFallback&&localFallback!==primary.origin)candidates.push(validateGatewayUrl(localFallback).origin);
      const tailscaleFallback=localStorage.getItem("solarminer-gateway-tailscale-endpoint-v1");
      if(tailscaleFallback&&tailscaleFallback!==primary.origin&&new URL(tailscaleFallback).hostname.toLowerCase().endsWith(".ts.net"))candidates.push(validateGatewayUrl(tailscaleFallback).origin);
    } catch {}
    let endpoint=primary, result=null;
    for(const candidate of candidates){
      gatewayResult(candidate===primary.origin?"A verificar /api/v1/health e /api/v1/info…":"Endpoint LAN indisponível; a tentar o endereço Tailscale…");
      result=await gatewayManager.check(candidate);
      if(result.reachable){endpoint=validateGatewayUrl(candidate);break;}
    }
    field.value=endpoint.origin;
    try { localStorage.setItem("solarminer-gateway-endpoint-v1", endpoint.origin); } catch {}
    if(result.reachable) {
      try {
        const bootstrap = await readGatewayBootstrapStatus(endpoint.origin);
        if (["BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"].includes(bootstrap.state)) {
          gatewayResult("Gateway pronto para o primeiro Owner. Abre-se a configuração inicial.");
          if (!$("#gateway-bootstrap-dialog").open) $("#gateway-bootstrap-dialog").showModal();
        } else {
          try {
            const login = await loginGateway({ gatewayUrl: endpoint.origin });
            $("#gateway-password-login-form").hidden = true;
            gatewayResult(`Ligação autenticada neste dispositivo como ${login.user.username} (${login.user.role}).`);
            markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
          } catch (loginError) {
            $("#gateway-password-login-form").hidden = false;
            gatewayResult(`${result.state}. ${loginError.message} Introduz as credenciais de uma conta ativa para registar este browser.`);
          }
        }
      } catch (statusError) {
        gatewayResult(`Gateway respondeu, mas não foi possível consultar o estado de bootstrap: ${statusError.message}`);
      }
    }
    else gatewayResult(`${result.state}. Nenhuma identidade ou ligação foi confirmada. Código técnico: ${result.errorCode || "erro de rede"}. Não foram contornados erros TLS.`);
  } catch(error) { gatewayResult(error.message || "Endpoint inválido."); }
});
$("#gateway-password-login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const status = $("#gateway-session-status");
  const endpoint = $("#gateway-endpoint").value;
  const password = $("#gateway-login-password");
  status.textContent = "A validar credenciais no Gateway…";
  try {
    const login = await loginGatewayWithPassword({ gatewayUrl: endpoint,
      username: $("#gateway-login-username").value, password: password.value });
    password.value = "";
    $("#gateway-password-login-form").hidden = true;
    gatewayResult(`Sessão iniciada como ${login.user.username} (${login.user.role}).`);
    status.textContent = `Dispositivo autenticado como ${login.user.username}.`;
    markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
  } catch (error) {
    password.value = "";
    status.textContent = error.message || "Não foi possível iniciar sessão.";
  }
});
$("#gateway-clear").addEventListener("click",async()=>{
  try { await logoutGateway(); } catch {}
  try { localStorage.removeItem("solarminer-gateway-endpoint-v1"); localStorage.removeItem("solarminer-gateway-lan-endpoint-v1"); localStorage.removeItem("solarminer-gateway-tailscale-endpoint-v1"); } catch {}
  $("#gateway-endpoint").value=""; gatewayManager.clear(); updateSessionUi(); resetToDemoAfterLogout();
  $("#gateway-password-login-form").hidden = true;
  gatewayResult("Endpoint removido deste browser. A identidade do dispositivo permanece guardada para poderes voltar a ligar sem palavra-passe.");
});
try {
  if (localStorage.getItem("solarminer-gateway-endpoint-v1") || gatewayHostedOrigin) {
    setTimeout(() => $("#gateway-check").click(), 0);
  }
} catch {}
const invitePanel = $("#gateway-invite-management");
const userPanel = $("#gateway-user-management");
const updatePanel = $("#gateway-update-management");
const tailscalePanel = $("#gateway-tailscale-management");
const hardwarePanel = $("#gateway-hardware-management");
let verifiedGatewayUpdate = null;
let inviteQrObjectUrl = null;
let ownerRecoveryFingerprint = "";
function markGatewayAuthenticated() {
  const info = sessionInfo();
  if (!info.authenticated) return;
  gatewayManager.setState({ state: "GATEWAY AUTENTICADO", reachable: true, identityValidated: true,
    simulated: false, gatewayProduct: "SolarMiner Gateway", reportedVersion: "API autenticada",
    endpointKind: "CANDIDATE_UNCLASSIFIED", lastCommunicationAt: new Date().toISOString() });
}
function updateSessionUi() {
  const info = sessionInfo();
  const status = $("#gateway-session-status");
  const isOwner = Boolean(info.authenticated && info.user.role === "owner");
  $("#owner-nav-item").hidden = !isOwner;
  $("#owner-mobile-link").hidden = !isOwner;
  if (info.authenticated) {
    const presence = presenceInfo();
    status.textContent = `Sessão autenticada: ${info.user.username} (${info.user.role}) · token apenas em memória · presença da sessão: ${presence.state || "unknown"}; não prova presença física.`;
    invitePanel.hidden = info.user.role !== "owner";
    userPanel.hidden = info.user.role !== "owner";
    if (info.user.role === "owner") {
      refreshInviteList().catch(error => { $("#gateway-invite-list").textContent = `Não foi possível consultar convites: ${error.message}`; });
      refreshGatewayUsers().catch(error => { $("#gateway-user-list").textContent = `Não foi possível consultar utilizadores: ${error.message}`; });
    }
    if (updatePanel) {
      updatePanel.hidden = info.user.role !== "owner";
      if (info.user.role === "owner") {
        readGatewayUpdateSource().then(source => { const input = $("#gateway-update-repository"); if (input && source.repository_url) input.value = source.repository_url; })
          .catch(error => showGatewayUpdateMessage(`Não foi possível consultar a origem: ${error.message}`));
        refreshGatewayUpdateStatus().catch(error => showGatewayUpdateMessage(`Não foi possível consultar o estado: ${error.message}`));
      }
    }
    if (tailscalePanel) {
      tailscalePanel.hidden = info.user.role !== "owner";
      if (info.user.role === "owner") refreshGatewayTailscale().catch(error => {
        $("#gateway-tailscale-status").textContent = `Não foi possível consultar o Tailscale: ${error.message}`;
      });
    }
    if (hardwarePanel) {
      hardwarePanel.hidden = info.user.role !== "owner";
      if (info.user.role === "owner") refreshHardwareIntegrationConfig().catch(error => {
        $("#hardware-integrations-status").textContent = `Não foi possível carregar a configuração: ${error.message}`;
      });
    }
  } else {
    status.textContent = "Sem sessão ativa. Ao testar o endpoint, este dispositivo tenta autenticar-se pela identidade guardada.";
    invitePanel.hidden = true;
    userPanel.hidden = true;
    if (updatePanel) updatePanel.hidden = true;
    if (tailscalePanel) tailscalePanel.hidden = true;
    if (hardwarePanel) hardwarePanel.hidden = true;
    verifiedGatewayUpdate = null;
  }
}
async function refreshHardwareIntegrationConfig() {
  const config = await readGatewayHardwareIntegrationConfig();
  const deye = config.deye || {}, miner = config.antminer || {}, tuya = config.tuya || {};
  $("#hardware-deye-host").value = deye.host || "";
  $("#hardware-deye-port").value = deye.port || 502;
  $("#hardware-deye-unit").value = deye.unit_id ?? 1;
  $("#hardware-antminer-host").value = miner.host || "";
  $("#hardware-antminer-port").value = miner.port || 4028;
  $("#hardware-tuya-region").value = tuya.region || "eu_central";
  $("#hardware-tuya-client-id").value = tuya.client_id || "";
  $("#hardware-tuya-client-secret").value = "";
  $("#hardware-tuya-devices").value = (tuya.devices || []).map(device => `${device.device_id} | ${device.name}`).join("\n");
  $("#hardware-integrations-status").textContent = `Configuração carregada · Deye ${deye.host ? "definido" : "por configurar"} · Antminer ${miner.host ? "definido" : "por configurar"} · Tuya ${tuya.configured ? "configurado; segredo oculto" : "por configurar"}. Tesla é configurado apenas na área Carregador EV.`;
  return config;
}
function hardwareConnectionSummary(result) {
  const names = { deye: "Deye", antminer: "Antminer" };
  const stateText = {
    modbus_identity_response: "Modbus respondeu; mapa de dados ainda não validado",
    modbus_exception_response: "O equipamento respondeu por Modbus, mas rejeitou a consulta de identificação",
    modbus_timeout: "IP/porta acessíveis, mas sem resposta Modbus; confirmar Unit ID e serviço Modbus",
    invalid_modbus_response: "A porta respondeu, mas a resposta não correspondeu ao Modbus esperado",
    modbus_transport_error: "Falha de transporte durante a consulta Modbus",
    api_responded: "API da Antminer respondeu",
    tcp_reachable_api_failed: "Porta 4028 acessível, mas a API BOSminer não respondeu corretamente",
    tcp_unreachable: "Gateway não conseguiu abrir ligação TCP ao equipamento",
    failed: "Ligação falhou"
  };
  return ["deye", "antminer"].map(key => {
    const device = result[key], configured = result.configuration?.[key] === "configured";
    if (!configured) return `${names[key]}: IP ainda não guardado no Gateway`;
    const state = device?.connection_state || "failed";
    const reason = device?.reason ? ` (${device.reason})` : "";
    return `${names[key]}: ${stateText[state] || state}${reason}`;
  }).join(" · ");
}
$("#hardware-integrations-save").addEventListener("click", async () => {
  const info = sessionInfo(), button = $("#hardware-integrations-save"), status = $("#hardware-integrations-status");
  if (!info.authenticated || info.user.role !== "owner") { status.textContent = "Só o Owner autenticado pode alterar as ligações."; return; }
  button.disabled = true; status.textContent = "A guardar a configuração privada no Gateway…";
  try {
    const deyeHost = $("#hardware-deye-host").value.trim(), minerHost = $("#hardware-antminer-host").value.trim();
    const tuyaRows = $("#hardware-tuya-devices").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const tuyaDevices = tuyaRows.map(line => { const [device_id, ...nameParts] = line.split("|"); return { device_id: device_id.trim(), name: nameParts.join("|").trim() || `Tuya ${device_id.trim()}` }; });
    const tuyaClient = $("#hardware-tuya-client-id").value.trim(), tuyaSecret = $("#hardware-tuya-client-secret").value;
    const payload = {
      deye: { enabled: Boolean(deyeHost), host: deyeHost, port: Number($("#hardware-deye-port").value), unit_id: Number($("#hardware-deye-unit").value), model: "other" },
      antminer: { enabled: Boolean(minerHost), host: minerHost, port: Number($("#hardware-antminer-port").value), model: "S19K Pro" }
    };
    if (tuyaRows.length || tuyaClient || tuyaSecret) {
      payload.tuya = { region: $("#hardware-tuya-region").value, client_id: tuyaClient || undefined, client_secret: tuyaSecret || undefined, devices: tuyaDevices };
    }
    const saved = await saveGatewayHardwareIntegrationConfig(payload);
    $("#hardware-tuya-client-secret").value = "";
    status.textContent = `Ligações guardadas no Gateway. Segredos nunca são devolvidos à PWA. Tuya: ${saved.tuya?.configured ? "configurado" : "por configurar"}. Tesla é configurado na área Carregador EV.`;
  } catch (error) { status.textContent = `Não foi possível guardar: ${error.message}`; }
  finally { button.disabled = false; }
});
$("#hardware-integrations-read").addEventListener("click", async () => {
  const info = sessionInfo(), button = $("#hardware-integrations-read"), status = $("#hardware-integrations-status"), output = $("#hardware-integrations-result");
  if (!info.authenticated || info.user.role !== "owner") { status.textContent = "Só o Owner autenticado pode iniciar a leitura."; return; }
  button.disabled = true; output.hidden = true; status.textContent = "A consultar os equipamentos a partir do Gateway…";
  try {
    const result = await readGatewayHardwareIntegrations();
    output.textContent = JSON.stringify(result, null, 2);
    output.hidden = false;
    const summary = hardwareConnectionSummary(result);
    status.textContent = `${summary}${result.errors?.length ? ` · ${result.errors.length} erro(s) detalhado(s) abaixo` : ""}. Nenhum comando de controlo foi enviado.`;
    await refreshGatewayReadings();
  } catch (error) { status.textContent = `A leitura falhou: ${error.message}`; }
  finally { button.disabled = false; }
});
async function refreshTeslaEvConfig() {
  const status = $("#ev-tesla-status"), info = sessionInfo();
  if (!status) return;
  const save = $("#ev-tesla-save"), read = $("#ev-tesla-read");
  if (!info.authenticated || info.user.role !== "owner") {
    status.textContent = "Só o Owner autenticado pode configurar e consultar o Tesla.";
    if (save) save.disabled = true;
    if (read) read.disabled = true;
    return;
  }
  if (save) save.disabled = false;
  if (read) read.disabled = false;
  const config = await readGatewayTeslaEvConfig();
  $("#ev-tesla-region").value = config.region || "europe";
  $("#ev-tesla-client-id").value = config.client_id || "";
  $("#ev-tesla-refresh-token").value = "";
  $("#ev-tesla-vehicle-id").value = (config.vehicle_ids || [])[0] || "";
  status.textContent = config.configured
    ? "Tesla configurado no Gateway. O refresh token é privado. Esta ligação só lê o estado de carga."
    : "Tesla ainda não configurado. Indica a aplicação Fleet autorizada e o veículo.";
}

$("#page-content").addEventListener("click", async event => {
  const save = event.target.closest("#ev-tesla-save");
  const read = event.target.closest("#ev-tesla-read");
  if (!save && !read) return;
  event.preventDefault();
  const info = sessionInfo(), status = $("#ev-tesla-status"), output = $("#ev-tesla-result");
  if (!info.authenticated || info.user.role !== "owner") {
    status.textContent = "Só o Owner autenticado pode gerir a ligação Tesla.";
    return;
  }
  if (save) save.disabled = true;
  if (read) read.disabled = true;
  output.hidden = true;
  try {
    if (save) {
      const vehicleId = $("#ev-tesla-vehicle-id").value.trim();
      if (!vehicleId) throw new Error("Indica o ID Tesla ou VIN do veículo.");
      const config = await saveGatewayTeslaEvConfig({
        region: $("#ev-tesla-region").value,
        client_id: $("#ev-tesla-client-id").value.trim(),
        refresh_token: $("#ev-tesla-refresh-token").value,
        vehicle_ids: [vehicleId],
      });
      $("#ev-tesla-refresh-token").value = "";
      status.textContent = config.configured
        ? "Ligação Tesla guardada no Gateway; token removido do formulário."
        : "A configuração Tesla não ficou completa.";
    } else {
      status.textContent = "A consultar o estado de carregamento Tesla…";
      const result = await readGatewayTeslaEvCharging();
      output.textContent = result.vehicles?.length ? result.vehicles.map(vehicle => {
        const charge = vehicle.charge_state || {};
        const value = (key, suffix = "") => charge[key] === undefined || charge[key] === null ? "—" : String(charge[key]) + suffix;
        const plugged = charge.plugged_in === undefined ? "—" : charge.plugged_in ? "sim" : "não";
        return (vehicle.name || "Tesla") + (vehicle.vin_suffix ? " · VIN termina em " + vehicle.vin_suffix : "") +
          "\nBateria: " + value("battery_level", "%") + " · Estado: " + value("charging_state") + " · Ligado à tomada: " + plugged +
          "\nPotência: " + value("charger_power", " kW") + " · Taxa de carga: " + value("charge_rate") +
          " · Limite: " + value("charge_limit_soc", "%") + " · Tempo até cheio: " + value("time_to_full_charge", " h");
      }).join("\n\n") : "A API Tesla não devolveu o veículo selecionado.";
      output.hidden = false;
      status.textContent = "Leitura recebida · " + new Date(result.observed_at * 1000).toLocaleString("pt-PT") + " · LIVE_UNVERIFIED · nenhum comando enviado.";
    }
  } catch (error) {
    status.textContent = "Operação Tesla falhou: " + error.message;
  } finally {
    if (save) save.disabled = false;
    if (read) read.disabled = false;
  }
});

$("#gateway-bootstrap-form").addEventListener("submit", async event => {
  event.preventDefault();
  const passwordField = $("#gateway-bootstrap-password");
  try {
    const result = await bootstrapGatewayOwner({ gatewayUrl: $("#gateway-endpoint").value,
      username: $("#gateway-bootstrap-username").value.trim(), password: passwordField.value });
    passwordField.value = "";
    $("#gateway-bootstrap-recovery-key").value = result.recovery_key;
    ownerRecoveryFingerprint = result.gatewayFingerprint || "";
    $("#gateway-bootstrap-recovery").hidden = false;
    $("#gateway-endpoint").value = result.gatewayUrl;
    $("#gateway-bootstrap-result").textContent = "Owner registado. A palavra-passe de configuração foi consumida e este telemóvel ficou associado. Guarda a chave de recuperação offline.";
    markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
  } catch (error) { passwordField.value = ""; $("#gateway-bootstrap-result").textContent = `Registo inicial não concluído: ${error.message}`; }
});
$("#gateway-copy-recovery-key").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#gateway-bootstrap-recovery-key").value); $("#gateway-bootstrap-result").textContent = "Chave de recuperação copiada. Guarda-a offline."; }
  catch { $("#gateway-bootstrap-result").textContent = "A cópia automática foi recusada; seleciona a chave e guarda-a offline."; }
});
$("#gateway-download-recovery-key").addEventListener("click", () => {
  const key = $("#gateway-bootstrap-recovery-key").value;
  if (!key) return;
  downloadOwnerRecoveryFile(key, ownerRecoveryFingerprint, "solarminer-owner-recovery-key.txt");
  $("#gateway-bootstrap-result").textContent = "Ficheiro da chave de recuperação descarregado. Copia-o para a pen Owner e apaga as cópias temporárias do computador.";
});
function downloadOwnerRecoveryFile(key, fingerprint, filename) {
  if (!key) return;
  const blob = new Blob([`SolarMiner Owner Recovery Key\nGateway Ed25519 fingerprint: ${fingerprint || "not-recorded"}\nGuardar offline. Este segredo pode iniciar o fluxo de recuperação do Owner.\n\n${key}\n`], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("#open-owner-recovery").addEventListener("click", () => {
  $("#gateway-recovery-fingerprint").value = ownerRecoveryFingerprint || "";
  $("#gateway-owner-recovery-dialog").showModal();
});
$("#gateway-recovery-file").addEventListener("change", async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const contents = await file.text();
    const { key, fingerprint } = parseOwnerRecoveryFile(contents);
    $("#gateway-recovery-key").value = key;
    if (fingerprint) $("#gateway-recovery-fingerprint").value = fingerprint;
    $("#gateway-recovery-result").textContent = "Ficheiro lido. Confirma o utilizador e define uma nova palavra-passe para recuperar o Owner.";
  } catch (error) { $("#gateway-recovery-result").textContent = error.message; }
});
$("#gateway-owner-recovery-form").addEventListener("submit", async event => {
  event.preventDefault();
  const newPassword = $("#gateway-recovery-password").value;
  const repeat = $("#gateway-recovery-password-repeat").value;
  const output = $("#gateway-recovery-result");
  if (newPassword !== repeat) { output.textContent = "As novas palavras-passe não coincidem."; return; }
  output.textContent = "A verificar a identidade TLS e a concluir a recuperação no Gateway…";
  try {
    const result = await recoverGatewayOwner({ gatewayUrl: $("#gateway-endpoint").value,
      username: $("#gateway-recovery-username").value.trim(), recoveryKey: $("#gateway-recovery-key").value.trim(),
      newPassword, mac: $("#gateway-recovery-mac").value.trim(),
      expectedGatewayFingerprint: $("#gateway-recovery-fingerprint").value.trim() });
    ownerRecoveryFingerprint = result.gatewayFingerprint || "";
    $("#gateway-recovery-new-key").value = result.recovery_key;
    $("#gateway-recovery-new-key-panel").hidden = false;
    $("#gateway-recovery-password").value = "";
    $("#gateway-recovery-password-repeat").value = "";
    $("#gateway-recovery-key").value = "";
    $("#gateway-recovery-file").value = "";
    output.textContent = "Acesso Owner recuperado. A chave antiga foi consumida; descarrega e guarda já a chave nova na pen.";
    markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
  } catch (error) { $("#gateway-recovery-password").value = ""; $("#gateway-recovery-password-repeat").value = ""; output.textContent = `Recuperação não concluída: ${error.message}`; }
});
$("#gateway-download-new-recovery-key").addEventListener("click", () => {
  downloadOwnerRecoveryFile($("#gateway-recovery-new-key").value, ownerRecoveryFingerprint, "solarminer-owner-recovery-key.txt");
  $("#gateway-recovery-result").textContent = "Nova chave descarregada. Substitui o ficheiro antigo na pen; a chave antiga já não funciona.";
});
function gatewayUpdateFailureText(code) {
  const messages = {
    repository_url_invalid: "O URL do repositório é inválido.",
    repository_url_not_allowed: "Só são aceites URLs HTTPS de repositórios públicos no github.com.",
    repository_url_must_be_public_github_repository: "Indica a raiz de um repositório público, sem subpáginas.",
    repository_not_allowlisted: "Este repositório não foi autorizado pelo administrador do Gateway.",
    update_source_configuration_unavailable: "O Gateway não tem uma lista de repositórios autorizados disponível.",
    update_source_configuration_unsafe: "A configuração administrativa das origens não tem permissões seguras.",
    manifest_signature_invalid: "A assinatura Ed25519 do manifesto não é válida.",
    manifest_structure_invalid: "O manifesto de lançamento está malformado.",
    package_sha256_mismatch: "O hash do pacote não corresponde ao manifesto assinado.",
    package_size_mismatch: "O tamanho do pacote não corresponde ao manifesto assinado.",
    package_origin_not_authorized: "A origem do pacote não está autorizada pelo administrador.",
    manifest_origin_not_allowlisted: "A origem do manifesto não está autorizada pelo administrador.",
    redirect_origin_not_authorized: "O lançamento redireciona para uma origem HTTPS não autorizada.",
    package_redirect_origin_changed: "O pacote redirecionou para uma origem não autorizada.",
    installed_version_not_compatible: "Esta versão não é compatível com o Gateway instalado.",
    insufficient_disk_space: "Não existe espaço livre suficiente para preparar a atualização."
  };
  return messages[code] || "O Gateway rejeitou a verificação. Confirma a configuração da origem e consulta o estado operacional.";
}
function showGatewayUpdateMessage(message) {
  const target = $("#gateway-update-message");
  if (target) target.textContent = message;
}
function setGatewayUpdateDetails(result) {
  const details = $("#gateway-update-details");
  const apply = $("#gateway-update-apply");
  if (!details || !apply) return;
  details.textContent = "";
  if (result?.available_version || result?.latest_version) {
    const rows = [
      `Versão instalada: ${result.installed_version || "desconhecida"}`,
      result.available_version ? `Versão disponível: ${result.available_version}` : `Versão no GitHub: ${result.latest_version}`,
      `Assinatura: ${result.signature_valid ? "válida" : "não validada"}`,
      `Hash SHA-256: ${result.sha256 || "não disponível"}`,
      result.repository_url ? `Repositório: ${result.repository_url}` : ""
    ].filter(Boolean);
    details.textContent = rows.join("\\n");
  }
  const canApply = result?.status === "verified_staged" && result.signature_valid === true &&
    result.compatible === true && result.activation_available === true && Boolean(result.available_version);
  verifiedGatewayUpdate = canApply ? result : null;
  apply.disabled = !canApply;
  apply.hidden = !canApply;
}
async function refreshGatewayUpdateStatus() {
  const info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") throw new Error("Apenas o Owner pode consultar atualizações.");
  const result = await readGatewayUpdateStatus();
  const pipeline = result.details?.pipeline || {};
  const failure = pipeline.failure || result.details?.failure || result.details?.reason;
  const rollbackFailure = pipeline.rollback_failure || result.details?.rollback_failure;
  const diagnosticRows = [
    result.operation_id ? `Operação: ${result.operation_id}` : "",
    result.installed_version ? `Versão instalada: ${result.installed_version}` : "",
    result.target_version ? `Versão de destino: ${result.target_version}` : "",
    failure ? `Falha da atualização: ${failure}` : "",
    rollbackFailure ? `Falha ao recuperar a versão anterior: ${rollbackFailure}` : "",
    pipeline.recovery ? `Recuperação: ${pipeline.recovery}` : "",
    pipeline.finished_at_utc ? `Terminado em: ${pipeline.finished_at_utc}` : ""
  ].filter(Boolean);
  if (result.status === "VERIFIED" && result.target_version) {
    setGatewayUpdateDetails({
      status: "verified_staged", installed_version: result.installed_version,
      available_version: result.target_version, signature_valid: true, compatible: true,
      activation_available: result.activation_available,
      repository_url: result.details?.repository_url, sha256: result.details?.package_sha256
    });
  } else if (result.status === "CURRENT" && result.target_version) {
    setGatewayUpdateDetails({
      status: "current", installed_version: result.installed_version,
      latest_version: result.target_version, signature_valid: true, compatible: true,
      activation_available: false, repository_url: result.details?.repository_url
    });
  } else {
    setGatewayUpdateDetails(null);
  }
  const statusDetails = $("#gateway-update-details");
  if (statusDetails && diagnosticRows.length) statusDetails.textContent = diagnosticRows.join("\n");
  showGatewayUpdateMessage(result.status === "VERIFIED" && !result.activation_available
    ? "Pacote verificado; a aplicação está bloqueada pelo preflight de recuperação."
    : result.status === "CURRENT" ? `O Gateway já está atualizado. Versão verificada: ${result.target_version}.`
    : result.status === "RECOVERY_BLOCKED" ? "A recuperação automática não foi confirmada. Consulta abaixo os motivos registados; não repitas a aplicação."
    : result.status === "FAILED" ? `A última verificação falhou: ${gatewayUpdateFailureText(result.details?.reason)}`
    : `Estado da atualização: ${result.status || "desconhecido"}${result.target_version ? ` · destino ${result.target_version}` : ""}.`);
  return result;
}
$("#gateway-update-check").addEventListener("click", async () => {
  const info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") { showGatewayUpdateMessage("Só o Owner autenticado pode verificar atualizações."); return; }
  const button = $("#gateway-update-check");
  button.disabled = true;
  verifiedGatewayUpdate = null;
  setGatewayUpdateDetails(null);
  showGatewayUpdateMessage("A validar repositório permitido, manifesto, assinatura e pacote…");
  try {
    const result = await checkGatewayUpdate($("#gateway-update-repository").value.trim());
    setGatewayUpdateDetails(result);
    if (result.status === "verified_staged") {
      showGatewayUpdateMessage(result.activation_available
        ? "Pacote verificado e pronto. Revê a versão e confirma explicitamente para aplicar."
        : "Pacote assinado e transferido, mas o preflight de recuperação bloqueou a aplicação.");
    } else if (result.status === "current") {
      showGatewayUpdateMessage(`O Gateway já está atualizado. Versão verificada: ${result.latest_version}.`);
    } else {
      showGatewayUpdateMessage(`Atualização bloqueada: ${gatewayUpdateFailureText(result.message)}`);
    }
  } catch (error) {
    showGatewayUpdateMessage(`Não foi possível verificar a atualização: ${error.message}`);
  } finally { button.disabled = false; }
});
$("#gateway-update-refresh").addEventListener("click", () => refreshGatewayUpdateStatus()
  .catch(error => showGatewayUpdateMessage(`Não foi possível consultar o estado: ${error.message}`)));
async function refreshGatewayTailscale() {
  const info=sessionInfo();
  if(!info.authenticated || info.user.role!=="owner") throw new Error("Apenas o Owner autenticado pode gerir Tailscale.");
  const result=await readGatewayTailscale();
  const field=$("#gateway-tailscale-endpoint");
  if(result.endpoint && field) field.value=result.endpoint;
  if(result.endpoint){try{localStorage.setItem("solarminer-gateway-tailscale-endpoint-v1",result.endpoint);}catch{}}
  else {try{localStorage.removeItem("solarminer-gateway-tailscale-endpoint-v1");}catch{}}
  const status=$("#gateway-tailscale-status");
  status.textContent=result.helper_available===false ? "O Gateway não conseguiu consultar o serviço Tailscale. Atualiza o Gateway para uma versão com o broker Tailscale ativo e volta a tentar." :
    !result.installed ? "Cliente Tailscale não instalado. Instala a versão SolarMiner preparada para Tailscale." :
    !result.connected ? "Tailscale instalado, mas o Gateway ainda não foi autorizado/ligado ao Tailnet. Conclui a autorização no terminal do Gateway." :
    !result.https_ready ? `Gateway ligado ao Tailnet (${result.dns_name}), mas o certificado HTTPS ainda não está pronto. Ativa MagicDNS e HTTPS Certificates no painel Tailscale e aguarda a emissão automática.` :
    `Tailscale ativo e HTTPS pronto: ${result.endpoint}. Não são necessárias portas no router.`;
  return result;
}
$("#gateway-tailscale-refresh").addEventListener("click",()=>refreshGatewayTailscale()
  .catch(error=>{$("#gateway-tailscale-status").textContent=`Não foi possível consultar o Tailscale: ${error.message}`;}));
$("#gateway-tailscale-connect").addEventListener("click",async()=>{
  const button=$("#gateway-tailscale-connect"), status=$("#gateway-tailscale-status");
  button.disabled=true; status.textContent="A pedir ao Gateway para iniciar a ligação Tailscale…";
  try {
    const result=await startGatewayTailscale();
    if(result.auth_url){
      status.replaceChildren(document.createTextNode("Abre este link e aprova o Gateway na tua conta Tailscale: "));
      const link=document.createElement("a"); link.href=result.auth_url; link.target="_blank"; link.rel="noopener noreferrer"; link.textContent="Autorizar Gateway no Tailscale";
      status.append(link);
    } else status.textContent="O Gateway já está ligado ao Tailscale. Toca em Detetar estado para confirmar o endereço HTTPS.";
  } catch(error){status.textContent=`O Gateway não conseguiu iniciar o Tailscale: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#gateway-tailscale-save").addEventListener("click",async()=>{
  const button=$("#gateway-tailscale-save"), status=$("#gateway-tailscale-status"), field=$("#gateway-tailscale-endpoint");
  const value=field.value.trim();
  button.disabled=true; status.textContent="A guardar o endereço Tailscale no Gateway…";
  try {
    const result=await configureGatewayTailscale(value || null);
    if(result.endpoint){try{localStorage.setItem("solarminer-gateway-tailscale-endpoint-v1",result.endpoint);}catch{}}
    else {try{localStorage.removeItem("solarminer-gateway-tailscale-endpoint-v1");}catch{}}
    status.textContent=value ? `Endereço guardado no Gateway: ${result.endpoint}.` : "Endereço manual removido; será usada a deteção automática quando estiver disponível.";
  } catch(error){status.textContent=`Não foi possível guardar o endereço: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#gateway-tailscale-use").addEventListener("click",()=>{
  const field=$("#gateway-tailscale-endpoint"), endpoint=field.value.trim();
  if(!endpoint){$("#gateway-tailscale-status").textContent="Deteta ou guarda primeiro o endereço Tailscale.";return;}
  try {
    const normalized=validateGatewayUrl(endpoint).origin;
    $("#gateway-endpoint").value=normalized;
    try{localStorage.setItem("solarminer-gateway-endpoint-v1",normalized);}catch{}
    $("#gateway-dialog").close(); $("#gateway-check").click();
  } catch(error){$("#gateway-tailscale-status").textContent=error.message||"Endereço Tailscale inválido.";}
});
$("#gateway-update-apply").addEventListener("click", async () => {
  const info = sessionInfo(), update = verifiedGatewayUpdate;
  if (!info.authenticated || info.user.role !== "owner" || !update?.available_version || !update.activation_available) {
    showGatewayUpdateMessage("Não há pacote verificado e aplicável nesta sessão Owner.");
    return;
  }
  if (!confirm(`Aplicar a versão ${update.available_version}? O Gateway fará backup, ativação e health check, com rollback se falhar.`)) return;
  const button = $("#gateway-update-apply");
  button.disabled = true;
  showGatewayUpdateMessage(`A enfileirar a atualização ${update.available_version}…`);
  try {
    const result = await applyGatewayUpdate(update.available_version);
    verifiedGatewayUpdate = null;
    showGatewayUpdateMessage(`Atualização aceite pelo Gateway: ${result.status || "APPLY_QUEUED"} · operação ${result.operation_id || "sem identificador"}. Usa “Atualizar estado” para acompanhar.`);
    await refreshGatewayUpdateStatus();
  } catch (error) {
    showGatewayUpdateMessage(`A aplicação foi bloqueada ou falhou: ${error.message}`);
  } finally { button.disabled = false; }
});

async function refreshInviteList() {
  const target = $("#gateway-invite-list");
  target.textContent = "A consultar convites…";
  const result = await listGatewayInvites();
  if (!result.invites?.length) { target.textContent = "Não existem convites registados."; return; }
  target.innerHTML = result.invites.map(item => `<div class="invite-row"><div><strong>${esc(item.label)}</strong><p>${esc(item.role)} · ${esc(item.state)} · expira ${esc(currentTimeLabel(new Date(item.expires_at * 1000).toISOString()))}</p></div>${item.state === "pending" ? `<button type="button" class="button secondary" data-revoke-invite="${esc(item.invite_id)}">Revogar</button>` : ""}</div>`).join("");
}
async function refreshGatewayUsers() {
  const target = $("#gateway-user-list");
  target.textContent = "A consultar utilizadores reais no Gateway…";
  const { users = [] } = await listGatewayUsers();
  if (!users.length) { target.textContent = "O Gateway não devolveu utilizadores."; return; }
  target.innerHTML = users.map(user => {
    const self = user.id === sessionInfo().user?.id;
    const availableRoles = user.role === "owner" ? ["owner", "admin", "operator", "viewer"] : ["admin", "operator", "viewer"];
    const roleOptions = availableRoles.map(role => `<option value="${role}" ${user.role === role ? "selected" : ""}>${role}</option>`).join("");
    const statusOptions = ["active", "revoked"].map(status => `<option value="${status}" ${user.status === status ? "selected" : ""}>${status === "active" ? "Ativo" : "Revogado"}</option>`).join("");
    return `<div class="invite-row gateway-user-row" data-gateway-user="${esc(user.id)}"><div><strong>${esc(user.username)}</strong><p>${esc(user.role)} · ${user.status === "active" ? "Ativo" : "Revogado"}${self ? " · sessão atual" : ""}</p></div><label>Papel<select data-user-role ${self ? "disabled" : ""}>${roleOptions}</select><button type="button" class="button secondary" data-save-role ${self ? "disabled" : ""}>Guardar papel</button></label><label>Estado<select data-user-status ${self ? "disabled" : ""}>${statusOptions}</select><button type="button" class="button secondary" data-save-status ${self ? "disabled" : ""}>Guardar estado</button></label></div>`;
  }).join("");
}
$("#gateway-refresh-users").addEventListener("click", () => refreshGatewayUsers().catch(error => { $("#gateway-user-list").textContent = `Erro: ${error.message}`; }));
$("#gateway-user-list").addEventListener("click", async event => {
  const button = event.target.closest("[data-save-role], [data-save-status]");
  if (!button || button.disabled) return;
  const row = button.closest("[data-gateway-user]");
  const userId = row.dataset.gatewayUser;
  const isRoleChange = button.hasAttribute("data-save-role");
  const role = row.querySelector("[data-user-role]").value;
  const status = row.querySelector("[data-user-status]").value;
  if (isRoleChange && role === "owner" && !confirm("Dar papel Owner concede controlo administrativo completo. Confirmas?")) return;
  if (!isRoleChange && status === "revoked" && !confirm("Revogar este utilizador e invalidar as sessões?")) return;
  const currentPassword = window.prompt("Confirma a palavra-passe atual do Owner para guardar esta alteração:");
  if (currentPassword === null || !currentPassword) return;
  button.disabled = true;
  try {
    if (isRoleChange) await updateGatewayUserRole(userId, role, currentPassword);
    else await updateGatewayUserStatus(userId, status, currentPassword);
    gatewayResult("Acesso atualizado no Gateway e registado na auditoria.");
    await refreshGatewayUsers();
  } catch (error) {
    gatewayResult(`Não foi possível guardar os acessos: ${error.message}`);
    await refreshGatewayUsers().catch(() => {});
  } finally { button.disabled = false; }
});
$("#gateway-refresh-invites").addEventListener("click", () => refreshInviteList().catch(error => { $("#gateway-invite-list").textContent = `Erro: ${error.message}`; }));
$("#gateway-create-invite-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const result = await createGatewayInvite({ role: $("#gateway-invite-role").value, label: $("#gateway-invite-label").value.trim() });
    if (inviteQrObjectUrl) URL.revokeObjectURL(inviteQrObjectUrl);
    inviteQrObjectUrl = URL.createObjectURL(new Blob([result.qr_svg], { type: "image/svg+xml" }));
    $("#gateway-invite-qr").src = inviteQrObjectUrl;
    $("#gateway-invite-payload").value = JSON.stringify(result.qr_payload);
    $("#gateway-invite-expiry").textContent = `Expira em ${currentTimeLabel(new Date(result.expires_at * 1000).toISOString())}. Papel: ${result.role}. O segredo só é apresentado nesta resposta.`;
    $("#gateway-invite-created").hidden = false;
    await refreshInviteList();
  } catch (error) { gatewayResult(`Não foi possível criar convite: ${error.message}`); }
});
$("#gateway-invite-list").addEventListener("click", async event => {
  const button = event.target.closest("[data-revoke-invite]");
  if (!button || !confirm("Revogar este convite pendente? Esta ação não pode ser desfeita.")) return;
  button.disabled = true;
  try { await revokeGatewayInvite(button.dataset.revokeInvite); await refreshInviteList(); }
  catch (error) { button.disabled = false; gatewayResult(`Revogação não confirmada: ${error.message}`); }
});
$("#gateway-copy-invite").addEventListener("click", async () => {
  const text = $("#gateway-invite-payload").value;
  try { await navigator.clipboard.writeText(text); gatewayResult("Conteúdo do convite copiado. Trata-o como um segredo até expirar ou ser consumido."); }
  catch { gatewayResult("O browser recusou a cópia automática; seleciona e copia o conteúdo manualmente."); }
});
updateSessionUi();
updateGatewayStatus(gatewayManager.state);
if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("./service-worker.js").catch(()=>{});
render();
hydrateWorkspacePhotos();
