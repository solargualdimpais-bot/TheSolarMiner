import { CATEGORIES, DEMO_EQUIPMENT, classifyEquipment, formatReading, isSimulated, summarizeDataState } from "./app-core.js";
import { DEMO_CONTROL_CONFIG, createDemoControlState, updateDemoControl, toggleDemoControl } from "./demo-mode.js";
import { renderWorkspacePage, renderHomePreferenceLinks, renderHouseSearch, handleWorkspaceAction, handleWorkspaceChange, applyPreferences, getWorkspacePageLabel, workspace, getEditableEntity, saveEditableEntity, saveDemoWorkspace, hydrateWorkspacePhotos } from "./workspace-ui.js";
import { renderAutomationsPage, renderSolarProductionPage, renderDemoAdminPanel, handleFeatureAction, saveAutomationForm, addDemoUser, saveDemoUserEdit, saveSolarWeather, demoFeatures } from "./features-v053.js";
import { GatewayConnectionManager, CONNECTION_STATES, parsePairingQr, parseInviteQr, probeGateway, validateGatewayUrl, PRESENCE_API_STATUS } from "./gateway-connection.js";
import { bootstrapGatewayOwner, redeemGatewayInvite, loginGateway, sessionInfo, createGatewayInvite, listGatewayInvites, revokeGatewayInvite, logoutGateway, readGatewayEnergy, presenceInfo } from "./gateway-auth.js";

let automationEditingId = "";
const state = { page: "inicio", mode: "SIMULATED", dataStatus: "DEMO", dataError: null, equipment: DEMO_EQUIPMENT, lastUpdated: null, lastMeasurementAt: null, refreshing: false, propertyPhoto: "", demoControls: createDemoControlState(), sky: "pouco nublado", favoriteDevices: [{id:"luz_sala",name:"Luz teto",room:"Sala de estar",floor:"RDC",pct:78},{id:"estor_sala",name:"Estore",room:"Sala de estar",floor:"RDC",pct:60},{id:"luz_coz",name:"Luz teto",room:"Cozinha",floor:"RDC",pct:0},{id:"estor_coz",name:"Estore",room:"Cozinha",floor:"RDC",pct:0}] };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const pageLabel = (id) => id === "inicio" ? "Visão geral" : (CATEGORIES.find(c => c.id === id)?.label || getWorkspacePageLabel(id) || "Mais áreas");
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
let qrCandidate = null;
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
  state.mode = "SIMULATED"; state.dataStatus = "DEMO"; state.dataError = null;
  state.equipment = DEMO_EQUIPMENT; state.lastUpdated = null; state.lastMeasurementAt = null; render();
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
  return `<article class="metric-card"><div class="metric-top"><span>${esc(label)}</span><span class="metric-symbol">${icon}</span></div><div class="metric-value">${value === null || value === undefined ? "—" : esc(new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(value))} <small>${esc(unit)}</small></div><div class="metric-sub">${esc(safeDetail)}</div></article>`;
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
  const workspacePage = renderWorkspacePage(state.page);
  let pageHtml = state.page === "inicio" ? renderOverview() : (workspacePage || (CATEGORIES.some(c=>c.id===state.page) ? renderCategory(state.page) : renderOverview()));
  if(state.page === "automatismos") pageHtml = renderAutomationsPage(workspace, automationEditingId);
  if(state.page === "producao") pageHtml = renderSolarProductionPage();
  if(state.page === "profile") pageHtml += renderDemoAdminPanel();
  $("#page-content").innerHTML = pageHtml;
  applyPreferences();
  applyLiveFontScale();
  const hero = $("#property-hero");
  if (hero && (workspace.house.photo || state.propertyPhoto)) hero.style.backgroundImage = `linear-gradient(90deg, rgba(9,9,9,.88) 0%, rgba(9,9,9,.62) 58%, rgba(9,9,9,.22) 100%), url("${workspace.house.photo || state.propertyPhoto}")`;
  if (state.page === "casa" && workspace.house.photo) document.documentElement.style.setProperty("--house-background-image", `url("${workspace.house.photo}")`); else document.documentElement.style.removeProperty("--house-background-image");
  document.querySelectorAll("[data-page]").forEach(el => el.classList.toggle("active", el.dataset.page === state.page));
  $("#refresh-button").disabled = state.refreshing;
}
function navigate(page) {
  if (page === "mais") { populateMore(); $("#more-dialog").showModal(); return; }
  if (!["inicio", ...CATEGORIES.map(c=>c.id), "energia", "casa", "profile", "engine", "devices", "paineis-solares", "automatismos", "producao"].includes(page)) return;
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
$("#page-content").addEventListener("click",e=>{const btn=e.target.closest("[data-page]");if(btn)navigate(btn.dataset.page);});
$("#page-content").addEventListener("change",e=>handleWorkspaceChange(e));
state.propertyPhoto=workspace.house.photo || readStoredPhoto(); if(state.propertyPhoto && !workspace.house.photo){workspace.house.photo=state.propertyPhoto;saveDemoWorkspace();}try{localStorage.removeItem("solar-miner-demo-property-photo-v1");}catch{}
$("#open-gateway-dialog").addEventListener("click",()=>$("#gateway-dialog").showModal());
$("#close-gateway-dialog").addEventListener("click",()=>$("#gateway-dialog").close());
$("#gateway-check").addEventListener("click",async()=>{
  const field=$("#gateway-endpoint");
  try {
    const endpoint=validateGatewayUrl(field.value,{allowLocalHttp:location.hostname==="localhost"||location.hostname==="127.0.0.1"});
    gatewayResult("A verificar /api/v1/health e /api/v1/info…");
    const result=await gatewayManager.check(endpoint.origin);
    if(result.reachable) gatewayResult(`${result.state}. Última resposta: ${currentTimeLabel(result.lastCommunicationAt)}. Método: endpoint HTTPS consultado. Identidade do Gateway: NÃO VALIDADA. O estado LAN/REMOTO não pode ser confirmado pelo contrato atual.`);
    else gatewayResult(`${result.state}. Nenhuma identidade ou ligação foi confirmada. Código técnico: ${result.errorCode || "erro de rede"}. Não foram contornados erros TLS.`);
  } catch(error) { gatewayResult(error.message || "Endpoint inválido."); }
});
$("#gateway-clear").addEventListener("click",async()=>{qrCandidate=null;$("#gateway-endpoint").value="";$("#gateway-qr-text").value="";try{await logoutGateway();}catch{}gatewayManager.clear();updateSessionUi();resetToDemoAfterLogout();gatewayResult("Gateway desassociado nesta sessão. O token de sessão foi descartado; não foram apagados dados históricos nem enviados comandos físicos.");});
function parseQrIntoCandidate(raw) {
  try {
    qrCandidate=parseInviteQr(raw,{allowLocalHttp:location.hostname==="localhost"||location.hostname==="127.0.0.1"});
    $("#gateway-endpoint").value=qrCandidate.gatewayUrl;
    gatewayResult(`Formato do convite CODE02 válido. Endpoint: ${qrCandidate.gatewayUrl}. Expira em ${currentTimeLabel(new Date(qrCandidate.expiresAt*1000).toISOString())}. A identidade ainda tem de ser verificada por desafio Ed25519 antes do resgate.`);
    return;
  } catch (inviteError) {
    try {
      qrCandidate=parsePairingQr(raw,{allowLocalHttp:location.hostname==="localhost"||location.hostname==="127.0.0.1"});
      $("#gateway-endpoint").value=qrCandidate.gatewayUrl;
      gatewayResult(`QR legado reconhecido, mas não é compatível com o endpoint de convites CODE02 v0.6.7. Não foi consumido.`);
    } catch(error) { qrCandidate=null;gatewayResult(error.message||inviteError.message||"Não foi possível validar o QR Code."); }
  }
}
$("#gateway-qr-parse").addEventListener("click",()=>parseQrIntoCandidate($("#gateway-qr-text").value));
$("#gateway-qr-file").addEventListener("change",async event=>{
  const file=event.target.files?.[0];if(!file)return;
  if(typeof BarcodeDetector==="undefined"){gatewayResult("Este Safari/browser não disponibiliza BarcodeDetector. Usa outro dispositivo para ler o QR e cola aqui o conteúdo; nenhuma permissão de segurança será contornada.");return;}
  try {
    const detector=new BarcodeDetector({formats:["qr_code"]});
    const bitmap=await createImageBitmap(file);const codes=await detector.detect(bitmap);bitmap.close?.();
    if(!codes.length) throw new Error("Não foi encontrado um QR Code nesta imagem.");
    $("#gateway-qr-text").value=codes[0].rawValue;parseQrIntoCandidate(codes[0].rawValue);
  } catch(error) { gatewayResult(error.message||"Não foi possível ler a imagem do QR Code."); }
});
const invitePanel = $("#gateway-invite-management");
const bootstrapPanel = $("#gateway-bootstrap-panel");
bootstrapPanel.hidden = !["localhost", "127.0.0.1", "::1"].includes(location.hostname.replace(/^\[|\]$/g, ""));
let inviteQrObjectUrl = null;
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
  const logout = $("#gateway-logout");
  if (info.authenticated) {
    const presence = presenceInfo();
    status.textContent = `Sessão autenticada: ${info.user.username} (${info.user.role}) · token apenas em memória · presença da sessão: ${presence.state || "unknown"}; não prova presença física.`;
    logout.disabled = false;
    invitePanel.hidden = info.user.role !== "owner";
    if (info.user.role === "owner") refreshInviteList().catch(error => { $("#gateway-invite-list").textContent = `Não foi possível consultar convites: ${error.message}`; });
  } else {
    status.textContent = "Sem sessão autenticada nesta aba. O token não é persistido entre recarregamentos.";
    logout.disabled = true;
    invitePanel.hidden = true;
  }
}
$("#gateway-bootstrap-form").addEventListener("submit", async event => {
  event.preventDefault();
  const tokenField = $("#gateway-bootstrap-token"), passwordField = $("#gateway-bootstrap-password");
  try {
    const result = await bootstrapGatewayOwner({ gatewayUrl: $("#gateway-endpoint").value, bootstrapToken: tokenField.value,
      username: $("#gateway-bootstrap-username").value.trim(), password: passwordField.value, mac: $("#gateway-bootstrap-mac").value.trim() });
    tokenField.value = ""; passwordField.value = "";
    $("#gateway-bootstrap-recovery-key").value = result.recovery_key;
    $("#gateway-bootstrap-recovery").hidden = false;
    $("#gateway-endpoint").value = result.gatewayUrl;
    gatewayResult("Owner criado localmente. Guarda a chave de recuperação offline antes de fechar esta janela.");
    markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
  } catch (error) { tokenField.value = ""; passwordField.value = ""; gatewayResult(`Bootstrap local não concluído: ${error.message}`); }
});
$("#gateway-copy-recovery-key").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#gateway-bootstrap-recovery-key").value); gatewayResult("Chave de recuperação copiada. Guarda-a num local offline seguro."); }
  catch { gatewayResult("A cópia automática foi recusada; seleciona a chave e guarda-a offline."); }
});
$("#gateway-login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const username = $("#gateway-login-username").value.trim();
  const passwordField = $("#gateway-login-password");
  try {
    const result = await loginGateway({ gatewayUrl: $("#gateway-endpoint").value, username, password: passwordField.value });
    passwordField.value = "";
    $("#gateway-endpoint").value = result.gatewayUrl;
    gatewayResult(`Autenticação concluída para ${result.user.username}. A identidade do Gateway foi verificada durante o convite; a API de leitura será consultada agora.`);
    markGatewayAuthenticated();
    updateSessionUi();
    await refreshGatewayReadings();
  } catch (error) { passwordField.value = ""; $("#gateway-session-status").textContent = `Autenticação não concluída: ${error.message}`; }
});
$("#gateway-logout").addEventListener("click", async () => {
  try { await logoutGateway(); gatewayResult("Sessão terminada. O token foi descartado da memória."); }
  catch (error) { gatewayResult(`A sessão local foi descartada; o servidor pode não ter confirmado o logout: ${error.message}`); }
  updateSessionUi();
  gatewayManager.clear();
  resetToDemoAfterLogout();
});
$("#gateway-redeem-form").addEventListener("submit", async event => {
  event.preventDefault();
  const passwordField = $("#gateway-redeem-password");
  try {
    const result = await redeemGatewayInvite({ qrText: $("#gateway-qr-text").value, username: $("#gateway-redeem-username").value.trim(), password: passwordField.value, mac: $("#gateway-redeem-mac").value.trim() });
    passwordField.value = "";
    $("#gateway-endpoint").value = result.gatewayUrl;
    gatewayResult(`Convite consumido com sucesso. Utilizador ${result.user.username}; papel ${result.user.role}. A chave privada não exportável foi guardada no IndexedDB e o token permanece só em memória.`);
    markGatewayAuthenticated();
    updateSessionUi();
    await refreshGatewayReadings();
  } catch (error) { passwordField.value = ""; gatewayResult(`Resgate não concluído: ${error.message}. O convite pode ter expirado ou já ter sido consumido.`); }
});
async function refreshInviteList() {
  const target = $("#gateway-invite-list");
  target.textContent = "A consultar convites…";
  const result = await listGatewayInvites();
  if (!result.invites?.length) { target.textContent = "Não existem convites registados."; return; }
  target.innerHTML = result.invites.map(item => `<div class="invite-row"><div><strong>${esc(item.label)}</strong><p>${esc(item.role)} · ${esc(item.state)} · expira ${esc(currentTimeLabel(new Date(item.expires_at * 1000).toISOString()))}</p></div>${item.state === "pending" ? `<button type="button" class="button secondary" data-revoke-invite="${esc(item.invite_id)}">Revogar</button>` : ""}</div>`).join("");
}
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
