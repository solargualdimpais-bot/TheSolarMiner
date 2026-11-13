import { CATEGORIES, DEMO_EQUIPMENT, classifyEquipment, formatReading, isSimulated, summarizeDataState } from "./app-core.js";
import { DEMO_CONTROL_CONFIG, createDemoControlState, updateDemoControl, toggleDemoControl } from "./demo-mode.js";
import { renderWorkspacePage, renderHomePreferenceLinks, renderHouseSearch, handleWorkspaceAction, handleWorkspaceChange, applyPreferences, getWorkspacePageLabel, workspace, getEditableEntity, saveEditableEntity, saveDemoWorkspace, hydrateWorkspacePhotos } from "./workspace-ui.js";
import { renderAutomationsPage, renderSolarProductionPage, renderDemoAdminPanel, handleFeatureAction, saveAutomationForm, addDemoUser, saveDemoUserEdit, saveSolarWeather, demoFeatures } from "./features-v053.js";
const PWA_INVITE_LANDING_URL = "https://solargualdimpais-bot.github.io/TheSolarMiner/";
import { GatewayConnectionManager, CONNECTION_STATES, validateGatewayUrl, classifyEndpoint, inferHostedGatewayEndpoint, buildInviteLandingUrl, readInviteLandingHash, PRESENCE_API_STATUS, storeGatewayProbeDiagnostics, takeGatewayProbeDiagnostics, acknowledgeGatewayProbeDiagnostics } from "./gateway-connection.js";
import { isHeicPhoto } from "./photo-format.js";
import { addFavoriteId, normalizeFavoriteIds, reorderFavoriteIds } from "./favorite-list.js";
import { bootstrapGatewayOwner, recoverGatewayOwner, parseOwnerRecoveryFile, readGatewayBootstrapStatus, loginGateway, loginGatewayWithPassword, redeemGatewayInvite, sessionInfo, createGatewayInvite, listGatewayInvites, revokeGatewayInvite, listGatewayUsers, updateGatewayUserRole, updateGatewayUserStatus, logoutGateway, readGatewayEnergy, readGatewaySiteProfile, saveGatewaySiteProfile, saveGatewaySitePhoto, saveGatewayEnergyEngineConfig, readGatewayEnergyEngineConfig, readGatewayUserAutomations, createGatewayUserAutomation, updateGatewayUserAutomation, deleteGatewayUserAutomation, dryRunGatewayUserAutomation, presenceInfo, checkGatewayUpdate, readGatewayUpdateSource, readGatewayUpdateStatus, applyGatewayUpdate, readGatewayTailscale, readGatewayConsole, readGatewayDiagnosticsUpload, saveGatewayDiagnosticsUploadToken, disableGatewayDiagnosticsUpload, sendGatewayDiagnosticsReport, setGatewayWatchdogEnabled, reportGatewayClientDiagnostics, readGatewayTerminalDiagnostics, openGatewayTerminalSocket, configureGatewayTailscale, startGatewayTailscale, readGatewayHardwareIntegrationConfig, readGatewayHardwareProvider, saveGatewayHardwareIntegrationConfig, syncGatewayTuyaDevices, syncGatewayTuyaSubdevices, previewGatewayTuyaProductImport, applyGatewayTuyaProductImport, saveGatewayTuyaProductMetadata, controlGatewayAntminer, testGatewayAntminerControl, readGatewayAntminerManagement, writeGatewayAntminerManagement, controlGatewayTuyaSwitch, controlGatewayTuyaLevel, controlGatewayTuyaSetting, saveGatewayTuyaProductDpsDescription, saveGatewayTuyaPidDpsMap, readGatewayDeviceCards, saveGatewayDeviceCard, readGatewayTuyaDeviceEvents, runGatewayTuyaLanDiagnostics, testGatewayTuyaLanReachability, discoverGatewayTuyaLanDevices, scanGatewayLocalNetwork, readGatewayDeviceInventory, readGatewaySmartProductCatalog, readGatewayShellyProductProfiles, readGatewayShellyDevices, discoverGatewayShellyDevices, registerGatewayShellyDevice, renameGatewayShellyDevice, readGatewayShellySettings, saveGatewayShellySettings, registerGatewayShellyBluDevice, discoverGatewayShellyBluDevices, controlGatewayShellySwitch, controlGatewayShellyLight, applyGatewayLocalNetworkMatches, saveGatewayLocalNetworkDevice, readGatewayDeyeCloudStations, importGatewayDeyeCloudHistory, readGatewayTeslaEvConfig, startGatewayTeslaOAuth, completeGatewayTeslaOAuth, saveGatewayTeslaRelay, saveGatewayTeslaEvConfig, readGatewayTeslaEvCharging, readGatewayTeslaLocalPresence } from "./gateway-auth.js";

let automationEditingId = "";
let energyEngineActiveTab="summary";
let surplusActiveTab="status";
let antminerActiveSubmenu="state";
let antminerActiveEquipmentId="";
const state = { page: "inicio", devicesTab: "confirmed", deviceCards: [], deviceCardsLoaded: false, mode: "DISCONNECTED", dataStatus: "UNAVAILABLE", dataError: null, equipment: [], energyEngine: null, siteProfile: null, tuyaDevices: [], shellyDevices: [], shellyDiscovered: [], shellyReadings: [], shellyProductProfiles: [], shellyProfilesLoaded: false, shellyRefreshing: false, gatewayDeviceInventory: [], smartProductCatalog: [], tuyaReadings: [], tuyaInventorySignature: "", lastUpdated: null, lastMeasurementAt: null, refreshing: false, tuyaInventoryRefreshing: false, pendingLiveRender: false, energyConfigStatus: "", demoControls: createDemoControlState(), sky: "pouco nublado", favoriteDevices: [], engineHistoryChart: { open: false, dateKey: "", loading: false, error: null } };
state.userAutomations = { loading: false, error: "", rules: [], history: [], capabilities: { triggers: [], targets: [] } };
let userAutomationEditingId = "";
let userAutomationLoadPromise = null;
let userAutomationMenuView = "";
let userAutomationPreviewTrigger = "";
let userAutomationStatusFilter = "favorites";
let userAutomationConditionDraft = null;
let userAutomationPreviewConditions = [];
let userAutomationConditionMode = "any";
let userAutomationModeMenuOpen = false;
let userAutomationPreviewActions = [];
let userAutomationActionReturnView = "status-conditions";
let lastLocalNetworkScanReport = null;
let lastLocalNetworkScanFilter = "all";
let inventoryCardClickTimer = null;
let favoriteCardClickTimer = null;
let favoriteReorderPressTimer=null,favoriteReorder=null,favoriteDragSuppressClickUntil=0;
let houseView={tab:"overview",floorId:null,roomId:null,planEditing:false};
let housePlanPointer=null;
let lastTuyaReadAt=0;
const pendingTuyaSwitchStates=new Map();
const pendingTuyaReadbacks=new Map();
const recentTuyaSwitchCommands=new Map();
const pendingShellyCommands=new Map();
const shellyBrightnessTimers=new Map();
let operationDialogResolve=null;
let gatewayUpdateNotice=null;
let gatewayAutoUpdateSuppressed=false;
let gatewayUpdateCheckInProgress=false;
let gatewayOwnerAutoCheckStarted=false;
const $ = (selector) => document.querySelector(selector);
function openGatewayConnectionDialog(){
  const dialog=$("#gateway-dialog");
  if(!dialog||dialog.open)return;
  try{dialog.showModal();}
  catch{dialog.setAttribute("open","");}
}
async function submitPendingGatewayProbeDiagnostics() {
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner") return;
  const events = takeGatewayProbeDiagnostics();
  if (!events.length) return;
  try {
    await reportGatewayClientDiagnostics(events);
    acknowledgeGatewayProbeDiagnostics(events);
  } catch { /* Keep the bounded local queue for the next authenticated connection. */ }
}
document.addEventListener("click",event=>{
  const target=event.target?.closest?.("#mode-chip, #owner-open-gateway, #profile-open-gateway, #open-owner-management");
  if(target){event.preventDefault();openGatewayConnectionDialog();}
});
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
function renderOperationDialog({title,message,actions=[],locked=false,progress=false,link=null}={}){
  const dialog=$("#operation-dialog"),messageNode=$("#operation-dialog-message"),linkNode=$("#operation-dialog-link"),actionsNode=$("#operation-dialog-actions");
  if(!dialog||!messageNode||!actionsNode)return;
  $("#operation-dialog-title").textContent=title||"SolarMiner";
  messageNode.textContent=message||"";
  messageNode.dataset.progress=String(Boolean(progress));
  dialog.dataset.locked=String(Boolean(locked));
  linkNode.replaceChildren();
  linkNode.hidden=!link;
  if(link){const anchor=document.createElement("a");anchor.className="button secondary";anchor.href=link.href;anchor.target="_blank";anchor.rel="noopener noreferrer";anchor.textContent=link.label||"Abrir ligação";linkNode.append(anchor);}
  actionsNode.replaceChildren();
  for(const action of actions){
    const button=document.createElement("button");button.type="button";button.className=`button ${action.primary?"primary":"secondary"}`;button.textContent=action.label;
    button.addEventListener("click",()=>dialog.close(action.value||"ok"));actionsNode.append(button);
  }
  dialog.oncancel=event=>{if(dialog.dataset.locked==="true")event.preventDefault();};
  if(!dialog.open)dialog.showModal();
}
function showOperationDialog(options={}){
  const dialog=$("#operation-dialog");
  if(!dialog)return Promise.resolve("ok");
  return new Promise(resolve=>{
    operationDialogResolve=resolve;
    const onClose=()=>{dialog.removeEventListener("close",onClose);const result=dialog.returnValue||"dismiss";operationDialogResolve=null;resolve(result);};
    dialog.addEventListener("close",onClose);
    renderOperationDialog(options);
  });
}
function updateOperationDialog(options={}){renderOperationDialog(options);}
async function showOperationResult(title,message){return showOperationDialog({title,message,actions:[{label:"OK",value:"ok",primary:true}]});}
const terminalUpdateStates=new Set(["COMMITTED","FAILED","ROLLED_BACK","RECOVERY_BLOCKED","CURRENT"]);
function updateStatusMessage(result){
  const status=String(result?.status||"UNKNOWN").toUpperCase();
  const version=status==="COMMITTED"
    ? result?.target_version||result?.details?.pipeline?.target_version||result?.installed_version||""
    : result?.installed_version||result?.target_version||"";
  if(status==="COMMITTED"){
    const previous=result?.installed_version;
    return `Atualização concluída${version?`: versão ${previous&&previous!==version?`${previous} → `:""}${version}`:""}.`;
  }
  const details=result?.details||{},pipeline=details.pipeline||{},lastPipeline=result?.last_pipeline_diagnostic||{};
  const diagnostic=pipeline.failure||pipeline.rollback_failure||lastPipeline.failure||lastPipeline.rollback_failure||details.failure||details.reason||"";
  const diagnosticText=diagnostic?` Motivo registado: ${String(diagnostic).replace(/[_-]+/g," ")}.`:" Consulta a Consola para ver o diagnóstico.";
  if(status==="ROLLED_BACK")return `A atualização falhou e o Gateway recuperou a versão anterior${version?` (${version})`:""}.${diagnosticText}`;
  if(status==="FAILED"||status==="RECOVERY_BLOCKED")return `A atualização não foi concluída${version?`. Versão de destino: ${version}`:"."}${diagnosticText}`;
  if(status==="CURRENT")return `O Gateway já está atualizado${version?` com a versão ${version}`:""}.`;
  return `A atualização continua em curso${version?` para a versão ${version}`:""}.`;
}
async function watchGatewayUpdate({initial=null,timeoutMs=12*60*1000}={}){
  let result=initial,started=Date.now();
  updateOperationDialog({title:"Atualização do Gateway",message:updateStatusMessage(result||{}),locked:true,progress:true});
  while(Date.now()-started<timeoutMs){
    if(result&&terminalUpdateStates.has(String(result.status||"").toUpperCase()))return result;
    await new Promise(resolve=>setTimeout(resolve,2500));
    try{result=await readGatewayUpdateStatus();updateOperationDialog({title:"Atualização do Gateway",message:updateStatusMessage(result),locked:true,progress:true});}
    catch{updateOperationDialog({title:"Atualização do Gateway",message:"O Gateway está a reiniciar. A aguardar que volte a responder…",locked:true,progress:true});}
  }
  return result;
}
async function applyVerifiedGatewayUpdate(update){
  const button=$("#gateway-update-apply");if(button)button.disabled=true;
  const progress=showOperationDialog({title:"Atualização do Gateway",message:`A iniciar a atualização para a versão ${update.available_version}…`,locked:true,progress:true});
  try{
    const accepted=await applyGatewayUpdate(update.available_version);verifiedGatewayUpdate=null;
    const final=await watchGatewayUpdate({initial:accepted});
    const committed=String(final?.status||"").toUpperCase()==="COMMITTED";
    renderOperationDialog({title:committed?"Atualização concluída":"Atualização terminada",message:updateStatusMessage(final),actions:[{label:"OK",value:"ok",primary:true}]});
  }catch(error){renderOperationDialog({title:"Falha na atualização",message:error.message||"O Gateway não conseguiu aplicar a atualização.",actions:[{label:"OK",value:"ok",primary:true}]});}
  finally{if(button)button.disabled=false;}
  await progress;
}
const userFacingSaveError = (error) => { const message=String(error?.message||""); if(message.includes("site_location_not_found")) return "O Gateway não encontrou essa cidade. Escreve cidade e país, por exemplo, Coimbra, Portugal."; if(message.includes("site_location_lookup_failed")) return "O Gateway não conseguiu consultar o serviço de localização. Verifica a ligação à Internet e tenta novamente."; if(message.includes("site_photo_not_confirmed")) return "O Gateway respondeu, mas não confirmou que a fotografia ficou guardada. Mantive este ecrã aberto para poderes tentar novamente."; if(message.includes("invalid_site_photo_size_or_format")||message.includes("site_photo_must_be_jpeg_data_url")) return "A fotografia não está num formato aceite ou excede 1,8 MB depois da compressão. Escolhe outra fotografia e tenta novamente."; if(message.includes("invalid_site_photo_base64")) return "A fotografia chegou corrompida ao Gateway. Volta a escolher o ficheiro e tenta novamente."; if(error?.status===413) return "O Gateway rejeitou o envio por exceder o limite de dados. Escolhe uma fotografia mais pequena."; return message||"Não foi possível guardar as alterações."; };
const pageLabel = (id) => id === "inicio" ? "Visão geral" : id === "owner" ? "Owner" : id === "gestao-excedentes" ? "Gestão de excedentes" : (CATEGORIES.find(c => c.id === id)?.label || getWorkspacePageLabel(id) || "Mais áreas");
const timeLabel = (value) => value ? new Intl.DateTimeFormat("pt-PT", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value)) : "Sem atualização";
let editorContext=null, editorPhoto=undefined, editorPhotoFile=null, editorPreviewObjectUrl=null, editorPhotoProcessing=false;
let editorPhotoSettings={x:50,y:50,zoom:1,vignette:.35,opacity:.38}, editorDrag=null;
function openContextEditor(type,id){
  if(editorPreviewObjectUrl){URL.revokeObjectURL(editorPreviewObjectUrl);editorPreviewObjectUrl=null;}
  editorPhotoProcessing=false;
  const entity=getEditableEntity(type,id);if(!entity){return;}
  editorContext={type,id};editorPhoto=type==='house'?(state.siteProfile?.photo_data_url||''):type==='room'?(entity.customPhoto||''):(entity.customPhoto||'');editorPhotoFile=null;
  if(type==='house')editorPhotoSettings={x:Number(state.siteProfile?.photo_position_x??50),y:Number(state.siteProfile?.photo_position_y??50),zoom:Number(state.siteProfile?.photo_zoom??1),vignette:Number(state.siteProfile?.photo_vignette??.35),opacity:Number(state.siteProfile?.photo_opacity??.38)};
  const title=({house:'Casa',room:'Editar divisão',device:'Editar dispositivo',floor:'Editar piso'})[type]||'Editar elemento';
  $('#context-editor-title').textContent=title;$('#context-editor-status').textContent=type==='house'?'Os dados partilhados da casa são guardados no Gateway.':'';
  $('#context-editor .dialog-header .eyebrow').textContent=type==='house'?'CASA · LOCALIZAÇÃO · FOTOGRAFIA':'PERSONALIZAÇÃO';
  $('#context-editor-form .field-note').textContent=type==='house'?'Altera os três dados da propriedade. A localização é usada pelo Gateway para identificar o local do inversor, dos painéis e do próprio Gateway.':'Pré-visualiza e confirma antes de guardar. As alterações ficam apenas neste browser/instalação PWA; não são enviadas ao Gateway.';
  $('#context-editor-form [type="submit"]').textContent=type==='house'?'Guardar':'Guardar localmente';
  const floorOptions=workspace.house.floors.map(f=>`<option value="${esc(f.id)}" ${f.id===(entity.__floorId||workspace.house.activeFloor)?'selected':''}>${esc(f.name)}</option>`).join('');
  let fields='';
  if(type==='house'){
    const cfg=state.energyEngine?.configuration||{}, owner=sessionInfo().authenticated&&sessionInfo().user?.role==='owner';
    const transparency=Math.round((1-Math.max(0,Math.min(1,Number(state.siteProfile?.photo_opacity??0.38))))*100);
    fields=`<label class="ws-field">Nome da casa<input name="name" maxlength="100" required value="${esc(state.siteProfile?.name||entity.name||'Solar Energy')}" ${owner?'':'disabled'}></label>${owner?`<label class="ws-field">Cidade ou localidade<input name="siteLocationName" type="text" maxlength="120" value="${esc(cfg.site_location_name??'')}" placeholder="Ex.: Coimbra, Portugal" autocomplete="address-level2"></label><p class="field-note">O Gateway converte a cidade em coordenadas para consultar meteorologia e calcular o potencial solar.</p><label class="ws-field photo-opacity-field">Transparência da fotografia <output id="photo-opacity-value">${transparency}%</output><input name="photoTransparency" id="photo-opacity" type="range" min="0" max="100" step="1" value="${transparency}" aria-label="Transparência da fotografia da casa"></label><label class="ws-field">Zoom da fotografia <output id="photo-zoom-value">${editorPhotoSettings.zoom.toFixed(1)}×</output><input name="photoZoom" id="photo-zoom" type="range" min="1" max="3" step="0.05" value="${editorPhotoSettings.zoom}" aria-label="Zoom da fotografia"></label><label class="ws-field">Vinheta nas bordas <output id="photo-vignette-value">${Math.round(editorPhotoSettings.vignette*100)}%</output><input name="photoVignette" id="photo-vignette" type="range" min="0" max="100" step="1" value="${Math.round(editorPhotoSettings.vignette*100)}" aria-label="Intensidade da vinheta"></label><small class="field-note">Arrasta a fotografia para a enquadrar. Os ajustes ficam partilhados no Gateway.</small>`:`<p class="field-note">Só o Owner pode alterar os dados partilhados da propriedade.</p>`}`;
  }
  if(type==='floor')fields=`<label class="ws-field">Nome do piso<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label>`;
  if(type==='room')fields=`<label class="ws-field">Nome da divisão<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label><label class="ws-field">Piso associado<select name="floorId">${floorOptions}</select></label>`;
  if(type==='device'){
    const roomOptions=workspace.house.floors.flatMap(f=>f.rooms.map(r=>`<option value="${esc(f.id)}|${esc(r.id)}" ${f.id===(entity.__floorId||'')&&r.id===(entity.__roomId||'')?'selected':''}>${esc(f.name)} / ${esc(r.name)}</option>`)).join('');
    fields=`<label class="ws-field">Nome apresentado<input name="name" maxlength="100" required value="${esc(entity.name||'')}"></label><label class="ws-field">Divisão associada<select name="roomTarget">${roomOptions}</select></label><p class="field-note">Tipo: ${esc(entity.type||'desconhecido')} · apenas identificação local. Não há campos de controlo real.</p>`;
  }
  if(type==='house'&&sessionInfo().authenticated&&sessionInfo().user?.role==='owner')fields+=`<label class="ws-field">Fotografia partilhada da propriedade (JPEG, PNG, WebP ou HEIC; até 40 MB antes da compressão; JPEG até 1,8 MB no Gateway)<input id="context-editor-file" name="image" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,image/*"></label><div class="dialog-actions"><button type="button" id="context-editor-remove-photo" class="button secondary">Remover fotografia da casa</button></div>`;
  else if(['room','device'].includes(type))fields+=`<label class="ws-field">Imagem personalizada (guardada neste browser)<input id="context-editor-file" name="image" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,image/*"></label><div class="dialog-actions"><button type="button" id="context-editor-remove-photo" class="button secondary">Remover imagem personalizada</button></div>`;
  $('#context-editor-fields').innerHTML=fields;
  const preview=$('#context-editor-preview'),img=$('#context-editor-preview-image');
  if(editorPhoto){img.src=editorPhoto;preview.hidden=false;}else{img.removeAttribute('src');preview.hidden=true;}
  updateHousePhotoPreview();
  $('#context-editor').showModal();
}
function updateHousePhotoPreview(){
  const img=$('#context-editor-preview-image'),shade=$('#context-editor-preview-vignette');if(!img)return;
  img.style.objectPosition=`${editorPhotoSettings.x}% ${editorPhotoSettings.y}%`;
  img.style.transform=`scale(${editorPhotoSettings.zoom})`;
  img.style.opacity=String(editorPhotoSettings.opacity);
  if(shade)shade.style.background=`radial-gradient(ellipse at center, transparent ${Math.max(0,65-editorPhotoSettings.vignette*38)}%, rgba(0,0,0,${editorPhotoSettings.vignette}) 120%)`;
}
let heicConverterLoad=null;
function loadHeicConverter(){if(typeof window.heic2any==='function')return Promise.resolve(window.heic2any);if(heicConverterLoad)return heicConverterLoad;heicConverterLoad=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('./assets/heic2any-0.0.4.min.js',import.meta.url).href;script.onload=()=>typeof window.heic2any==='function'?resolve(window.heic2any):reject(new Error('O conversor HEIC não ficou disponível.'));script.onerror=()=>{heicConverterLoad=null;reject(new Error('Não foi possível carregar o conversor HEIC. Confirma a ligação e tenta novamente.'));};document.head.append(script);});return heicConverterLoad;}
async function isJpegPhoto(file){if(/^image\/jpeg(?:$|;)/i.test(file?.type||''))return true;if(!file?.slice)return false;try{const header=new Uint8Array(await file.slice(0,3).arrayBuffer());return header[0]===0xff&&header[1]===0xd8&&header[2]===0xff;}catch{return false;}}
async function makeBrowserReadablePhoto(file){if(await isJpegPhoto(file)||!await isHeicPhoto(file))return file;const convert=await loadHeicConverter();const converted=await convert({blob:file,toType:'image/jpeg',quality:.92});const jpeg=Array.isArray(converted)?converted[0]:converted;if(!(jpeg instanceof Blob)||jpeg.size===0)throw new Error('Não foi possível converter esta fotografia HEIC.');return jpeg;}
function readAndCompressImage(file){return new Promise((resolve,reject)=>{if(!file)return resolve(undefined);if((file.type&&!/^image\//i.test(file.type))||file.size>40*1024*1024)return reject(new Error('Escolhe uma fotografia com menos de 40 MB.'));const image=new Image();const sourceUrl=URL.createObjectURL(file);const finish=()=>URL.revokeObjectURL(sourceUrl);image.onerror=()=>{finish();reject(new Error('O browser não conseguiu descodificar esta imagem.'));};image.onload=async()=>{try{const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');if(!ctx)throw new Error('O browser não disponibilizou processamento local de imagem.');let maxDimension=1800;for(let attempt=0;attempt<14;attempt++){const scale=Math.min(1,maxDimension/Math.max(image.naturalWidth,image.naturalHeight));canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);for(const quality of [.82,.72,.62,.52,.42]){const blob=await new Promise(done=>canvas.toBlob(done,'image/jpeg',quality));if(blob&&blob.size<=1_800_000){const reader=new FileReader();reader.onerror=()=>reject(new Error('Não foi possível preparar a fotografia.'));reader.onload=()=>resolve(reader.result);reader.readAsDataURL(blob);finish();return;}}maxDimension=Math.round(maxDimension*.8);}throw new Error('Não foi possível comprimir a fotografia abaixo do limite de 1,8 MB. Escolhe uma fotografia mais pequena.');}catch(error){finish();reject(error);}};image.src=sourceUrl;});}
$('#context-editor-cancel').addEventListener('click',()=>$('#context-editor').close());
$('#context-editor-fields').addEventListener('change',async e=>{if(e.target.id!=='context-editor-file')return;const file=e.target.files?.[0];if(!file)return;const img=$('#context-editor-preview-image'),preview=$('#context-editor-preview'),submit=$('#context-editor-form [type="submit"]');if(editorPreviewObjectUrl){URL.revokeObjectURL(editorPreviewObjectUrl);editorPreviewObjectUrl=null;}editorPhotoProcessing=true;submit.disabled=true;$('#context-editor-status').textContent='A identificar e preparar a fotografia…';try{const heic=await isHeicPhoto(file);if(!heic){editorPreviewObjectUrl=URL.createObjectURL(file);img.src=editorPreviewObjectUrl;preview.hidden=false;updateHousePhotoPreview();}const readable=await makeBrowserReadablePhoto(file);if(heic){editorPreviewObjectUrl=URL.createObjectURL(readable);img.src=editorPreviewObjectUrl;preview.hidden=false;updateHousePhotoPreview();}editorPhoto=await readAndCompressImage(readable);$('#context-editor-status').textContent='Pré-visualização pronta. Ainda não foi guardada.';}catch(error){$('#context-editor-status').textContent=error.message;$('#context-editor-file').value='';if(editorPhoto){img.src=editorPhoto;preview.hidden=false;}else{img.removeAttribute('src');preview.hidden=true;}}finally{editorPhotoProcessing=false;submit.disabled=false;}});
$('#context-editor-fields').addEventListener('input',e=>{
  const t=e.target;
  if(t.id==='photo-opacity'){editorPhotoSettings.opacity=1-Number(t.value)/100;$('#photo-opacity-value').value=`${t.value}%`;$('#photo-opacity-value').textContent=`${t.value}%`;}
  if(t.id==='photo-zoom'){editorPhotoSettings.zoom=Number(t.value);$('#photo-zoom-value').value=`${Number(t.value).toFixed(1)}×`;$('#photo-zoom-value').textContent=`${Number(t.value).toFixed(1)}×`;}
  if(t.id==='photo-vignette'){editorPhotoSettings.vignette=Number(t.value)/100;$('#photo-vignette-value').value=`${t.value}%`;$('#photo-vignette-value').textContent=`${t.value}%`;}
  updateHousePhotoPreview();
});
$('#context-editor-preview').addEventListener('pointerdown',e=>{if(!editorPhoto||editorContext?.type!=='house')return;editorDrag={x:e.clientX,y:e.clientY,px:editorPhotoSettings.x,py:editorPhotoSettings.y};e.currentTarget.setPointerCapture(e.pointerId);});
$('#context-editor-preview').addEventListener('pointermove',e=>{if(!editorDrag)return;const rect=e.currentTarget.getBoundingClientRect();editorPhotoSettings.x=Math.max(0,Math.min(100,editorDrag.px-(e.clientX-editorDrag.x)/Math.max(1,rect.width)*100));editorPhotoSettings.y=Math.max(0,Math.min(100,editorDrag.py-(e.clientY-editorDrag.y)/Math.max(1,rect.height)*100));updateHousePhotoPreview();});
$('#context-editor-preview').addEventListener('pointerup',()=>{editorDrag=null;});
$('#context-editor-fields').addEventListener('click',e=>{if(e.target.id!=='context-editor-remove-photo')return;editorPhoto='';editorPhotoFile=null;$('#context-editor-preview').hidden=true;$('#context-editor-preview-image').removeAttribute('src');$('#context-editor-status').textContent='A imagem será removida quando guardares.';});
$('#context-editor-form').addEventListener('submit',async e=>{
  e.preventDefault();if(!editorContext)return;if(editorPhotoProcessing){$('#context-editor-status').textContent='Aguarda que a fotografia termine de preparar.';return;}
  const form=e.currentTarget,submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try{
    if(editorContext.type==='house'){
      if(sessionInfo().user?.role!=='owner')throw new Error('Só o Owner pode alterar os dados partilhados da propriedade.');
      const current=state.siteProfile||{name:'Solar Energy',photo_data_url:null,floors:[]};
      const photoChanged=editorPhoto!==undefined;
      const payload={...current,name:form.elements.name?.value||current.name,photo_data_url:current.photo_data_url||null,photo_opacity:editorPhotoSettings.opacity,photo_position_x:editorPhotoSettings.x,photo_position_y:editorPhotoSettings.y,photo_zoom:editorPhotoSettings.zoom,photo_vignette:editorPhotoSettings.vignette};
      const locationName=form.elements.siteLocationName?.value.trim()||'';
      const oldLocation=state.energyEngine?.configuration?.site_location_name||'';
      if(locationName&&locationName!==oldLocation){const cfg=await saveGatewayEnergyEngineConfig({site_location_name:locationName});state.siteLocationName=cfg.site_location_name||locationName;}
      const profileFieldsChanged=['name','photo_opacity','photo_position_x','photo_position_y','photo_zoom','photo_vignette','floors'].some(key=>JSON.stringify(payload[key]??null)!==JSON.stringify(current[key]??null));
      let savedProfile=profileFieldsChanged?await saveGatewaySiteProfile(payload):current;
      if(photoChanged){
        savedProfile=await saveGatewaySitePhoto({kind:'house',floorId:'',roomId:'',photoDataUrl:editorPhoto||null});
        if((savedProfile.photo_data_url||null)!==(editorPhoto||null))throw new Error('site_photo_not_confirmed');
      }
      state.siteProfile=savedProfile;state.propertyName=state.siteProfile.name;
      workspace.house.name=state.siteProfile.name;
      $('#context-editor').close();render();
      const n=$('#notice');n.hidden=false;n.textContent='Nome e fotografia guardados no Gateway e partilhados com as outras PWA.';setTimeout(()=>n.hidden=true,5000);
      if(locationName&&locationName!==oldLocation)await refreshGatewayReadings();
      return;
    }
    const values={name:form.elements.name?.value,description:form.elements.description?.value??getEditableEntity(editorContext.type,editorContext.id)?.description};
    if(editorContext.type==='room')values.floorId=form.elements.floorId?.value;
    if(editorContext.type==='device'){const pair=(form.elements.roomTarget?.value||'').split('|');values.floorId=pair[0];values.roomId=pair[1];}
    if(['room','device'].includes(editorContext.type))values.photo=editorPhoto;
    const ok=saveEditableEntity(editorContext.type,editorContext.id,values);if(!ok)throw new Error('Não foi possível guardar as alterações.');
    $('#context-editor').close();render();
  }catch(error){$('#context-editor-status').textContent=userFacingSaveError(error);}finally{submit.disabled=false;}
});


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
function preferredGatewayReading(item) {
  const readings = Array.isArray(item?.readings) ? item.readings : [];
  const preferred = item?.category === "baterias" ? ["battery_output_power", "battery_voltage"]
    : item?.category === "inversores" ? ["pv_total_power", "inverter_power_total", "load_total_power"] : [];
  return preferred.map(field => readings.find(reading => reading?.field === field)).find(Boolean)
    || readings.find(reading => reading && reading.value !== null && reading.value !== undefined)
    || null;
}
function classifyGatewayReadings(items, allowedAgeMs = 5 * 60 * 1000) {
  const readings = items.flatMap(item => item.readings || []);
  const measured = readings.filter(reading => ["LIVE_UNVERIFIED", "PHYSICALLY_CORROBORATED"].includes(reading.trust) && !["DEMO", "SIMULATED"].includes(String(reading.source || "").toUpperCase()));
  if (!measured.length) return "UNKNOWN";
  const times = measured.map(reading => Date.parse(reading.observed_at || "")).filter(Number.isFinite);
  if (!times.length) return "UNKNOWN";
  return Date.now() - Math.max(...times) > allowedAgeMs ? "STALE" : "LIVE";
}
function refreshHomeLiveCards(){
  const host=$("#page-content");if(!host||state.page!=="inicio")return;
  const template=document.createElement("template");template.innerHTML=renderOverview();
  const date=host.querySelector(".home-page-heading .date-block"),nextDate=template.content.querySelector(".home-page-heading .date-block");
  if(date&&nextDate){const currentStrong=date.querySelector("strong"),nextStrong=nextDate.querySelector("strong");if(currentStrong&&nextStrong)currentStrong.textContent=nextStrong.textContent;const currentBreak=date.querySelector("br"),nextBreak=nextDate.querySelector("br");if(currentBreak&&nextBreak){let currentText=currentBreak.nextSibling,nextText=nextBreak.nextSibling;if(currentText?.nodeType===Node.TEXT_NODE&&nextText?.nodeType===Node.TEXT_NODE)currentText.textContent=nextText.textContent;}}
  const weather=host.querySelector(".home-weather-card"),nextWeather=template.content.querySelector(".home-weather-card");
  if(weather&&nextWeather){const pairs=[[".home-weather-values > strong",".home-weather-values > strong"],[".home-weather-details",".home-weather-details"]];for(const [selector,nextSelector] of pairs){const current=weather.querySelector(selector),next=nextWeather.querySelector(nextSelector);if(current&&next&&current.textContent!==next.textContent)current.textContent=next.textContent;}const currentCondition=weather.querySelector(".home-weather-condition"),nextCondition=nextWeather.querySelector(".home-weather-condition"),currentIcon=currentCondition?.querySelector("svg"),nextIcon=nextCondition?.querySelector("svg"),currentLabel=currentCondition?.querySelector("span"),nextLabel=nextCondition?.querySelector("span");if(currentIcon&&nextIcon&&currentIcon.outerHTML!==nextIcon.outerHTML)currentIcon.replaceWith(nextIcon.cloneNode(true));if(currentLabel&&nextLabel&&currentLabel.textContent!==nextLabel.textContent)currentLabel.textContent=nextLabel.textContent;}
  const production=host.querySelector(".home-production-card"),nextProduction=template.content.querySelector(".home-production-card");
  if(production&&nextProduction){for(const selector of [".home-production-value",".home-production-load strong"]){const current=production.querySelector(selector),next=nextProduction.querySelector(selector);if(current&&next&&current.textContent!==next.textContent)current.textContent=next.textContent;}const currentChart=production.querySelector(".home-production-chart,.home-production-chart-empty"),nextChart=nextProduction.querySelector(".home-production-chart,.home-production-chart-empty");if(currentChart&&nextChart&&currentChart.matches("svg")&&nextChart.matches("svg")){const currentPaths=[...currentChart.querySelectorAll("path")],nextPaths=[...nextChart.querySelectorAll("path")];for(let index=0;index<Math.min(currentPaths.length,nextPaths.length);index++){const d=nextPaths[index].getAttribute("d")||"";if(currentPaths[index].getAttribute("d")!==d)currentPaths[index].setAttribute("d",d);}}else if(currentChart&&nextChart&&currentChart.matches(".home-production-chart-empty")&&nextChart.matches(".home-production-chart-empty")){if(currentChart.textContent!==nextChart.textContent)currentChart.textContent=nextChart.textContent;}else if(currentChart&&nextChart)currentChart.replaceWith(nextChart.cloneNode(true));}
  const metrics=host.querySelector(".metric-grid"),nextMetrics=template.content.querySelector(".metric-grid");
  if(metrics&&nextMetrics){const currentCards=[...metrics.children],nextCards=[...nextMetrics.children];for(let index=0;index<Math.min(currentCards.length,nextCards.length);index++){const current=currentCards[index],next=nextCards[index],currentValue=current.querySelector(".metric-value"),nextValue=next.querySelector(".metric-value"),currentNumber=currentValue?.firstChild,nextNumber=nextValue?.firstChild;if(currentNumber?.nodeType===Node.TEXT_NODE&&nextNumber?.nodeType===Node.TEXT_NODE&&currentNumber.nodeValue!==nextNumber.nodeValue)currentNumber.nodeValue=nextNumber.nodeValue;const currentUnit=currentValue?.querySelector("small"),nextUnit=nextValue?.querySelector("small");if(currentUnit&&nextUnit&&currentUnit.textContent!==nextUnit.textContent)currentUnit.textContent=nextUnit.textContent;const currentSubs=[...current.querySelectorAll(".metric-sub")],nextSubs=[...next.querySelectorAll(".metric-sub")];for(let sub=0;sub<Math.min(currentSubs.length,nextSubs.length);sub++){if(currentSubs[sub].textContent!==nextSubs[sub].textContent)currentSubs[sub].textContent=nextSubs[sub].textContent;if(currentSubs[sub].className!==nextSubs[sub].className)currentSubs[sub].className=nextSubs[sub].className;}}}
  for(const device of state.tuyaDevices||[]){updateVisibleTuyaCard(device.device_id);updateOpenTuyaDeviceDialog(device.device_id);}
}
function renderAfterLiveRefresh() {
  const now=Date.now(),recentIds=new Set([...recentTuyaSwitchCommands].filter(([,expiresAt])=>expiresAt>now).map(([deviceId])=>deviceId));
  for(const [deviceId,expiresAt] of recentTuyaSwitchCommands)if(expiresAt<=now)recentTuyaSwitchCommands.delete(deviceId);
  const activeDialog=document.querySelector('dialog[open][data-tuya-device-id]');
  if(state.page==="inicio"){state.pendingLiveRender=false;refreshHomeLiveCards();return;}
  if(state.page==="devices"){
    state.pendingLiveRender=false;
    if(document.querySelector("dialog[open]")){state.pendingLiveRender=true;return;}
    for(const device of state.tuyaDevices||[]){updateVisibleTuyaCard(device.device_id);updateOpenTuyaDeviceDialog(device.device_id);}
    return;
  }
  if((recentIds.size||activeDialog)&&["inicio","devices"].includes(state.page)){
    state.pendingLiveRender=false;
    const deviceIds=new Set([...recentIds,...favoriteControlPending,...(activeDialog?[activeDialog.dataset.tuyaDeviceId]:[])]);
    for(const deviceId of deviceIds){updateVisibleTuyaCard(deviceId);updateOpenTuyaDeviceDialog(deviceId);}
    return;
  }
  if (document.querySelector("dialog[open]")) { state.pendingLiveRender = true; return; }
  state.pendingLiveRender = false;
  render();
}
document.addEventListener("close", () => {
  if (state.pendingLiveRender && !document.querySelector("dialog[open]")) {
    state.pendingLiveRender = false;
    render();
  }
}, true);
function normalizeTuyaInventoryDevice(device) {
  if(!device||typeof device!=="object"||Array.isArray(device))return null;
  const objectRows=value=>Array.isArray(value)?value.filter(item=>item&&typeof item==="object"&&!Array.isArray(item)):[];
  return {...device,functions:objectRows(device.functions),status_spec:objectRows(device.status_spec),current_status:objectRows(device.current_status),switch_channels:Array.isArray(device.switch_channels)?device.switch_channels.filter(value=>typeof value==="string"):[],capability_labels:device.capability_labels&&typeof device.capability_labels==="object"&&!Array.isArray(device.capability_labels)?device.capability_labels:{},channel_labels:device.channel_labels&&typeof device.channel_labels==="object"&&!Array.isArray(device.channel_labels)?device.channel_labels:{}};
}
function normalizeTuyaInventory(devices){return Array.isArray(devices)?devices.map(normalizeTuyaInventoryDevice).filter(Boolean):[];}
function normalizeTuyaReading(reading){
  if(!reading||typeof reading!=="object"||Array.isArray(reading))return null;
  return {...reading,status:Array.isArray(reading.status)?reading.status.filter(item=>item&&typeof item==="object"&&!Array.isArray(item)):[]};
}
function shellyObservationMs(device){const raw=device?.observed_at,numeric=Number(raw);if(Number.isFinite(numeric)&&numeric>0)return numeric<1e12?numeric*1000:numeric;const parsed=Date.parse(raw||"");return Number.isFinite(parsed)?parsed:0;}
function shellyDeviceComponent(device,name,channel){return (device?.components||[]).find(item=>item.component===name&&Number(item.id)===Number(channel))||null;}
function shellyComponentState(component){const value=component?.status?.output??component?.status?.ison;return typeof value==="boolean"?value:undefined;}
function shellyComponentPower(device,component){const status=component?.status||{},meter=shellyDeviceComponent(device,"meter",Number(component?.id)||0)?.status||shellyDeviceComponent(device,"meter",0)?.status||{};const value=status.apower??status.power??meter.apower??meter.power;return value!==null&&value!==undefined&&Number.isFinite(Number(value))?Number(value):null;}
function shellyPendingKey(deviceId,component,channel){return `${deviceId}::${component}::${Number(channel)||0}`;}
function shellyReadingMerge(incoming){
  const previousById=new Map((state.shellyDevices||[]).map(device=>[device.device_id,device])),now=Date.now();
  return (Array.isArray(incoming)?incoming:[]).map(device=>{
    const previous=previousById.get(device.device_id),oldAt=shellyObservationMs(previous),newAt=shellyObservationMs(device);
    const previousGood=previous?.connection_state==="connected"&&Array.isArray(previous.components)&&previous.components.length>0;
    const incomingGood=device?.connection_state==="connected"&&Array.isArray(device.components)&&device.components.length>0;
    if(previousGood&&(!incomingGood||newAt<=oldAt)&&now-oldAt<15_000)return {...previous,stale:!incomingGood,latest_read_error:device?.reason||""};
    return {...device,stale:!incomingGood};
  });
}
function updateVisibleShellyCard(deviceId){
  const device=state.shellyDevices.find(item=>item.device_id===deviceId);if(!device)return;
  const connected=device.connection_state==="connected",components=device.components||[],card=[...document.querySelectorAll('[data-smart-provider="shelly"]')].find(item=>item.dataset.smartDevice===deviceId),details=[...document.querySelectorAll('dialog[data-shelly-device-id]')].find(item=>item.dataset.shellyDeviceId===deviceId);
  if(!card&&!details)return;
  card?.classList.add("is-confirmed");card?.classList.toggle("is-fault",!connected);card?.classList.toggle("is-stale",Boolean(device.stale));
  const primary=components.find(item=>["switch","relay","light","rgb","rgbw","cct","color"].includes(item.component)),primaryState=shellyComponentState(primary),stateNode=card?.querySelector(`[data-shelly-card-state="${CSS.escape(deviceId)}"]`);
  if(stateNode)stateNode.textContent=connected?(primaryState===true?"Ligado":primaryState===false?"Desligado":device.stale?"Última leitura · antiga":"Online"):"Sem leitura";
  const feedback=card?.querySelector("[data-shelly-card-feedback]");if(feedback&&!pendingShellyCommands.has(shellyPendingKey(deviceId,primary?.component,primary?.id)))feedback.textContent=device.stale?"A mostrar a última leitura válida":"";
  const buttons=[...(card?.querySelectorAll("[data-shelly-switch],[data-shelly-light-on]")||[]),...(details?.querySelectorAll("[data-shelly-switch],[data-shelly-light-on]")||[])];
  for(const button of buttons){
    const componentName=button.hasAttribute("data-shelly-light-on")?button.dataset.shellyComponent:"switch",channel=Number(button.dataset.shellyChannel),component=shellyDeviceComponent(device,componentName,channel)||shellyDeviceComponent(device,"relay",channel)||shellyDeviceComponent(device,"light",channel),key=shellyPendingKey(deviceId,component?.component||componentName,channel),pending=pendingShellyCommands.get(key),observed=shellyComponentState(component),value=pending&&!pending.timedOut?pending.value:observed;
    button.classList.toggle("on",value===true);button.classList.toggle("off",value===false);button.classList.toggle("unknown",typeof value!=="boolean");button.classList.toggle("pending",Boolean(pending&&!pending.timedOut));button.dataset.shellyTarget=value===true?"off":"on";button.setAttribute("aria-pressed",String(value===true));button.disabled=!connected||Boolean(pending&&!pending.timedOut);
    if(pending&&!pending.timedOut&&feedback)feedback.textContent=pending.outcomeUnknown?"Sem resposta do Gateway; a confirmar pela leitura LAN…":"Ordem enviada; a confirmar pela leitura LAN…";
  }
  const detailState=details?.querySelector("[data-shelly-status]");if(detailState&&primary)detailState.textContent=connected?(primaryState===true?"Ligado":primaryState===false?"Desligado":"Online"):(device.reason||"Sem leitura");
  const groupButton=details?.querySelector("[data-shelly-group-toggle]");if(groupButton){const dimmers=components.filter(item=>["light","rgb","rgbw","cct","color"].includes(item.component)),anyOn=dimmers.some(item=>shellyComponentState(item)===true),label=anyOn?"Desligar tudo":"Ligar tudo";groupButton.dataset.shellyTarget=anyOn?"off":"on";groupButton.textContent=label;groupButton.classList.toggle("on",anyOn);groupButton.classList.toggle("off",!anyOn);groupButton.disabled=!connected;const caption=groupButton.parentElement?.querySelector("strong");if(caption)caption.textContent=label;}
  for(const channel of details?.querySelectorAll(".reference-channel")||[]){const component=shellyDeviceComponent(device,channel.dataset.shellyComponent,channel.dataset.shellyChannel),status=component?.status||{},rawBrightness=status.brightness,hasBrightness=rawBrightness!==null&&rawBrightness!==undefined&&Number.isFinite(Number(rawBrightness)),brightness=hasBrightness?Number(rawBrightness):null;channel.classList.toggle("is-on",shellyComponentState(component)===true);channel.classList.toggle("is-off",shellyComponentState(component)!==true);const fill=channel.querySelector(".reference-slider-fill"),input=channel.querySelector("[data-shelly-brightness]"),caption=channel.querySelector("[data-shelly-brightness-value]");if(brightness!==null){if(fill)fill.style.setProperty("--level",`${Math.max(0,Math.min(100,brightness))}%`);if(input)input.value=String(Math.max(0,Math.min(100,brightness)));if(caption)caption.textContent=`${Math.round(brightness)}%`;if(input)input.disabled=!connected||shellyComponentState(component)!==true;}const button=channel.querySelector("[data-shelly-light-on]");if(button&&!pendingShellyCommands.has(shellyPendingKey(deviceId,component?.component,component?.id))){const on=shellyComponentState(component)===true;button.dataset.shellyTarget=on?"off":"on";button.classList.toggle("on",on);button.classList.toggle("off",!on);button.setAttribute("aria-pressed",String(on));button.disabled=!connected;}}
  const brightnessSummary=details?.querySelector("[data-shelly-brightness-summary]");if(brightnessSummary){const value=components.find(item=>["light","rgb","rgbw","cct","color"].includes(item.component))?.status?.brightness;brightnessSummary.textContent=value!==null&&value!==undefined&&Number.isFinite(Number(value))?`${Math.round(Number(value))}%`:"Sem leitura";}
  const powerSummary=details?.querySelector("[data-shelly-power-summary]");if(powerSummary){const dimmer=components.find(item=>["light","rgb","rgbw","cct","color"].includes(item.component)),value=shellyComponentPower(device,dimmer);powerSummary.textContent=value!==null?`${value.toLocaleString("pt-PT")} W`:"Sem leitura";}
  const metricsNode=card?.querySelector("[data-shelly-card-metrics]");if(metricsNode){const status=primary?.status||{},pairs=[["Tensão",status.voltage,"V"],["Corrente",status.current,"A"],["Potência",shellyComponentPower(device,primary),"W"]],text=pairs.filter(([,value])=>value!==null&&value!==undefined&&Number.isFinite(Number(value))).map(([label,value,unit])=>`${label} ${new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(Number(value))} ${unit}`);metricsNode.textContent=text.length?text.join(" · "):device.stale?"Última medição válida":"Sem medição";}
}
async function refreshGatewayReadings() {
  if (!sessionInfo().authenticated || state.refreshing) return false;
  state.refreshing = true;
  $("#refresh-button").disabled = true;
  try {
    const result = await readGatewayEnergy();
    state.equipment = normalizeGatewayEquipment(result.equipment);
    state.energyEngine = result.engine || null;
    state.siteProfile = result.siteProfile || null;
    if (result.siteProfile) {
      state.propertyName = result.siteProfile.name || "Solar Energy";
    }
    if (sessionInfo().user?.role === "owner") {
      try {
        const hardware = await readGatewayHardwareIntegrationConfig(); state.tuyaDevices = normalizeTuyaInventory(hardware.tuya?.devices);
        state.tuyaReadings = mergeTuyaReadings(tuyaReadingsFromConfig(state.tuyaDevices));
        if(!state.tuyaDevices.length) lastTuyaReadAt=0;
      } catch { /* Keep last successful values visible with their original timestamp. */ }
      try { const inventory=await readGatewayDeviceInventory(); state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[]; }
      catch { /* Keep the last successful central inventory. */ }
    }
    state.mode = "LIVE";
    state.dataStatus = classifyGatewayReadings(state.equipment, Math.max(90 * 1000, (result.engine?.sampling_interval_seconds || 30) * 3 * 1000));
    state.dataError = null;
    state.lastUpdated = result.fetchedAt;
    const measurementTimes = state.equipment.flatMap(item => item.readings || []).map(reading => Date.parse(reading.observed_at || "")).filter(Number.isFinite);
    state.lastMeasurementAt = measurementTimes.length ? new Date(Math.max(...measurementTimes)).toISOString() : null;
    renderAfterLiveRefresh();
    return true;
  } catch (error) {
    state.mode = "LIVE";
    state.dataStatus = state.lastUpdated ? "STALE" : "UNAVAILABLE";
    state.dataError = error.status === 401 ? "Sessão expirada. Autentica novamente; não foram usados dados de demonstração como fallback." : `Consulta falhada: ${error.message}`;
    if (error.status === 401) updateSessionUi();
    renderAfterLiveRefresh();
    return false;
  } finally {
    state.refreshing = false;
    $("#refresh-button").disabled = false;
  }
}
async function refreshShellyInventoryStatus({ quiet = false } = {}) {
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner" || state.shellyRefreshing) return false;
  state.shellyRefreshing = true;
  try {
    const result = await readGatewayShellyDevices();
    state.shellyDevices = shellyReadingMerge(result.devices);
    state.shellyReadings = state.shellyDevices;
    if(!state.shellyProfilesLoaded){try{const profiles=await readGatewayShellyProductProfiles();state.shellyProductProfiles=Array.isArray(profiles.profiles)?profiles.profiles:[];}catch{state.shellyProductProfiles=[];}finally{state.shellyProfilesLoaded=true;}}
    for(const device of state.shellyDevices){
      for(const [key,pending] of pendingShellyCommands){
        if(pending.deviceId!==device.device_id)continue;
        const component=shellyDeviceComponent(device,pending.component,pending.channel),observed=shellyComponentState(component),observedAt=shellyObservationMs(device);
        if(observedAt<=pending.requestedAt||observedAt<=pending.lastObservedAt)continue;
        pending.lastObservedAt=observedAt;
        if(observed===pending.value){pendingShellyCommands.delete(key);continue;}
        pending.mismatchCount=(pending.mismatchCount||0)+1;
        if(pending.timedOut||pending.mismatchCount>=4){pendingShellyCommands.delete(key);const feedback=document.querySelector(`[data-smart-device="${CSS.escape(device.device_id)}"] [data-shelly-card-feedback]`);if(feedback)feedback.textContent=`A leitura LAN ainda mostra ${observed===true?"ligado":"desligado"}; a ordem não foi confirmada.`;}
      }
      updateVisibleShellyCard(device.device_id);
      const dialog=document.querySelector(`dialog[open][data-shelly-device-id="${CSS.escape(device.device_id)}"]`);
      if(dialog){
        const isOnline=device.connection_state==="connected",stateNode=dialog.querySelector("[data-shelly-dialog-state]");
        if(stateNode)stateNode.textContent=isOnline?(device.stale?"Última leitura · antiga":"Online"):"Sem leitura";
        const connectionNode=dialog.querySelector(".shelly-device-connection");
        if(connectionNode){connectionNode.textContent=isOnline?"Online":"Offline";connectionNode.classList.toggle("is-online",isOnline);connectionNode.classList.toggle("is-offline",!isOnline);}
        const status=dialog.querySelector(`[data-shelly-status="${CSS.escape(device.device_id)}"]`);
        if(status&&device.stale)status.textContent="A mostrar a última leitura válida; a aguardar atualização LAN.";
        for(const button of dialog.querySelectorAll("[data-shelly-switch],[data-shelly-light-on]")){
          const componentName=button.hasAttribute("data-shelly-light-on")?button.dataset.shellyComponent:(shellyDeviceComponent(device,"switch",button.dataset.shellyChannel)?"switch":"relay"),channel=Number(button.dataset.shellyChannel),component=shellyDeviceComponent(device,componentName,channel),key=shellyPendingKey(device.device_id,componentName,channel),pending=shellyPendingCommands.get(key),observed=shellyComponentState(component),value=pending&&!pending.timedOut?pending.value:observed;
          button.classList.toggle("on",value===true);button.classList.toggle("off",value===false);button.classList.toggle("pending",Boolean(pending&&!pending.timedOut));button.dataset.shellyTarget=value===true?"off":"on";button.setAttribute("aria-pressed",String(value===true));button.disabled=!isOnline||Boolean(pending&&!pending.timedOut);
        }
        for(const metrics of dialog.querySelectorAll("[data-shelly-light-metrics]")){
          const lightComponent=(device.components||[]).find(item=>item.component===metrics.dataset.shellyComponent&&Number(item.id)===Number(metrics.dataset.shellyChannel));
          const lightStatus=lightComponent?.status||{},measuredBrightness=Number(lightStatus.brightness);
          const brightnessBadge=metrics.querySelector("[data-shelly-badge-brightness]");
          if(brightnessBadge)brightnessBadge.textContent=Number.isFinite(measuredBrightness)?`${Math.max(0,Math.min(100,measuredBrightness))}%`:"—";
          // Keep each thumb and its caption at the user's target. Only measured
          // values in this channel's top badges follow the LAN readback.
          const measuredPower=lightStatus.apower??lightStatus.power??(device.bthome_values||[]).find(item=>String(item?.name||"").toLowerCase()==="power")?.value;
          const powerOutput=metrics.querySelector("[data-shelly-measured-power]");
          if(powerOutput&&measuredPower!==undefined&&measuredPower!==null&&Number.isFinite(Number(measuredPower)))powerOutput.textContent=`${Number(measuredPower).toLocaleString("pt-PT")} W`;
          const colorDot=metrics.querySelector("[data-shelly-color-dot]"),rgb=Array.isArray(lightStatus.rgb)&&lightStatus.rgb.length>=3?lightStatus.rgb.map(value=>Math.max(0,Math.min(255,Math.round(Number(value)||0)))):(Number.isFinite(Number(lightStatus.red))&&Number.isFinite(Number(lightStatus.green))&&Number.isFinite(Number(lightStatus.blue))?[lightStatus.red,lightStatus.green,lightStatus.blue].map(value=>Math.max(0,Math.min(255,Math.round(Number(value))))):null);
          if(colorDot&&rgb){colorDot.style.setProperty("--lamp-rgb",rgb.join(","));const colorBadge=colorDot.closest(".shelly-color-badge");if(colorBadge){colorBadge.title="Cor reportada pela lâmpada";colorBadge.setAttribute("aria-label",colorBadge.title);}}
        }
      }
    }
    if(!quiet){const status=$("#shelly-register-status");if(status)status.textContent="Leitura concluída pela LAN; os cartões foram atualizados sem redesenhar a página.";}
    return true;
  } catch (error) {
    if (!quiet) showFeatureNotice(`Não foi possível ler os Shelly pela LAN: ${error.message}`);
    return false;
  } finally { state.shellyRefreshing = false; }
}
async function refreshSmartProductCatalog({ quiet = true } = {}) {
  if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner")return false;
  try{const result=await readGatewaySmartProductCatalog();state.smartProductCatalog=Array.isArray(result.tuya_profiles)?result.tuya_profiles:[];return true;}
  catch(error){if(!quiet)showFeatureNotice(`Não foi possível carregar o catálogo local de produtos: ${error.message}`);return false;}
}
function tuyaCachedReadings(devices){
  return (Array.isArray(devices)?devices:[]).map(device=>{
    const status=Array.isArray(device.current_status)?device.current_status:[];
    const online=device.current_connection_state==="local_responded"&&device.local_control_state==="ready";
    const latency=device.last_latency_ms;
    return {device_id:device.device_id,name:device.name||"Tuya",status,connection_state:online?"local_responded":device.local_control_state==="unavailable"||device.local_verified?"failed":"stored_status",reason:device.current_status_reason||device.last_read_error||undefined,observed_at:device.last_status_at||undefined,attempted_at:device.last_read_attempt_at||undefined,latency_ms:latency!==null&&latency!==undefined&&Number.isFinite(Number(latency))?Number(latency):undefined,source:"TUYA_LAN",trust:online?"LIVE_UNVERIFIED":"UNAVAILABLE"};
  });
}
function tuyaReadingsFromConfig(devices){
  // The Gateway's periodic DPS observation is authoritative for switch state.
  // A previous TCP-only probe (or manual diagnostic) must never shadow newer engine data.
  return tuyaCachedReadings(devices);
}
function tuyaReadingTimestamp(reading){
  const value=reading?.observed_at;if(typeof value==="number"&&Number.isFinite(value))return value<1e12?value*1000:value;
  const parsed=Date.parse(value||"");return Number.isFinite(parsed)?parsed:0;
}
function tuyaReadingAttemptTimestamp(reading){
  const value=reading?.attempted_at||reading?.checked_at||reading?.observed_at;
  if(typeof value==="number"&&Number.isFinite(value))return value<1e12?value*1000:value;
  const parsed=Date.parse(value||"");return Number.isFinite(parsed)?parsed:0;
}
function tuyaReadingAgeLabel(reading){
  const observedAt=tuyaReadingTimestamp(reading);if(!observedAt)return "idade desconhecida";
  const seconds=Math.max(0,Math.floor((Date.now()-observedAt)/1000));
  return seconds<2?"agora":seconds<60?`há ${seconds} s`:`há ${Math.floor(seconds/60)} min`;
}
function tuyaConnectionSummary(reading){
  const hasLatency=reading?.latency_ms!==null&&reading?.latency_ms!==undefined&&Number.isFinite(Number(reading.latency_ms));
  const latency=hasLatency?`última resposta LAN ${Number(reading.latency_ms).toLocaleString("pt-PT",{maximumFractionDigits:1})} ms`:"latência indisponível";
  return reading?.connection_state==="local_responded"?`Online · ${latency} · leitura ${tuyaReadingAgeLabel(reading)}`:`Sem confirmação LAN agora · ${latency} · última leitura ${tuyaReadingAgeLabel(reading)}`;
}
function mergeTuyaReadings(incoming){
  const merged=new Map((state.tuyaReadings||[]).map(reading=>[reading.device_id,reading]));
  for(const reading of Array.isArray(incoming)?incoming:[]){if(!reading?.device_id)continue;const previous=merged.get(reading.device_id);if(previous&&tuyaReadingAttemptTimestamp(reading)<tuyaReadingAttemptTimestamp(previous))continue;const hasNewerGoodStatus=!previous||tuyaReadingTimestamp(reading)>=tuyaReadingTimestamp(previous);merged.set(reading.device_id,{...previous,...reading,status:hasNewerGoodStatus&&Array.isArray(reading.status)&&reading.status.length?reading.status:(previous?.status||reading.status||[]),observed_at:hasNewerGoodStatus?reading.observed_at:previous?.observed_at});}
  return [...merged.values()];
}
function settlePendingTuyaSwitchStates(devices,readings){
  const settled=[];
  for(const [key,pending] of pendingTuyaSwitchStates){
    const reading=readings.find(item=>item.device_id===pending.deviceId);
    const device=devices.find(item=>item.device_id===pending.deviceId);
    const observed=device&&reading?tuyaSwitchState(device,reading,pending.code,true):undefined;
    const observedAt=tuyaReadingTimestamp(reading);if(reading?.connection_state!=="local_responded"||observedAt<=pending.requestedAt)continue;
    if(observed===pending.value){pendingTuyaSwitchStates.delete(key);settled.push(pending.deviceId);continue;}
    if(typeof observed!=="boolean")continue;
    if(pending.timedOut&&observedAt>Number(pending.lastObservedAt||pending.requestedAt)){pending.lastObservedAt=observedAt;pending.mismatchCount=(pending.mismatchCount||0)+1;if(pending.mismatchCount>=4){pendingTuyaSwitchStates.delete(key);settled.push(pending.deviceId);}}
    if(pending.timedOut&&pending.mismatchCount>=4){
      const wanted=pending.value?"ligado":"desligado",actual=observed?"ligado":"desligado";
      document.querySelectorAll(`dialog[open][data-tuya-device-id="${CSS.escape(pending.deviceId)}"] [data-tuya-quick-status],dialog[open][data-tuya-device-id="${CSS.escape(pending.deviceId)}"] [data-tuya-detail-lan-status]`).forEach(node=>{node.textContent=`Falha ao confirmar a ordem: o dispositivo continua ${actual}.`;});
    }
  }
  return settled;
}
async function refreshTuyaInventoryStatus(){
  if(!["devices","inicio"].includes(state.page)||document.visibilityState!=="visible"||!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"||state.tuyaInventoryRefreshing)return;
  state.tuyaInventoryRefreshing=true;
  try{
    const hardware=await readGatewayHardwareIntegrationConfig();
    // Navigation may change while the request is in flight; background polls
    // must not redraw a different page when they complete.
    const devices=normalizeTuyaInventory(hardware.tuya?.devices);
    const signatureRows=devices.map(device=>[device.device_id,device.current_connection_state,device.local_control_state,device.current_status_reason,device.current_status,device.last_status_at,device.last_latency_ms,device.last_read_attempt_at]);
    let previousRows=[];try{previousRows=JSON.parse(state.tuyaInventorySignature||"[]");}catch{}
    const previousById=new Map(previousRows.map(row=>[row[0],JSON.stringify(row.slice(1))]));
    const changedIds=signatureRows.filter(row=>previousById.get(row[0])!==JSON.stringify(row.slice(1))).map(row=>row[0]);
    const readings=mergeTuyaReadings(tuyaReadingsFromConfig(devices));
    const settledIds=settlePendingTuyaSwitchStates(devices,readings);
    const changedSet=new Set([...changedIds,...settledIds]);
    const changed=changedSet.size>0;
    state.tuyaInventorySignature=JSON.stringify(signatureRows);
    state.tuyaDevices=devices;
    state.tuyaReadings=readings;
    if(["devices","inicio"].includes(state.page)){
      changedSet.forEach(deviceId=>updateVisibleTuyaCard(deviceId));
      // Refresh only the open Tuya detail dialog on every poll. This lets its
      // five-second stale-reading timer advance without rebuilding the page.
      for(const dialog of document.querySelectorAll('dialog[open][data-tuya-device-id]'))updateOpenTuyaDeviceDialog(dialog.dataset.tuyaDeviceId);
    }
  }catch{/* Keep the last confirmed state and its timestamp visible if this poll fails. */}
  finally{state.tuyaInventoryRefreshing=false;}
}
function updateVisibleTuyaCard(deviceId){
  if(state.page==="inicio"){
    const current=document.querySelector(`.home-favorites .favorite-device[data-favorite-device="${CSS.escape(deviceId)}"]`);
    if(!current)return;
    const template=document.createElement("template");template.innerHTML=favoriteDeviceCards();
    const updated=[...template.content.querySelectorAll(".favorite-device[data-favorite-device]")].find(card=>card.dataset.favoriteDevice===deviceId);
    const currentToggle=current.querySelector("[data-favorite-toggle]"),nextToggle=updated?.querySelector("[data-favorite-toggle]");
    if(currentToggle&&nextToggle){currentToggle.className=nextToggle.className;for(const name of ["aria-pressed","aria-label","title","disabled"]){if(nextToggle.hasAttribute(name))currentToggle.setAttribute(name,nextToggle.getAttribute(name));else currentToggle.removeAttribute(name);}}
    return;
  }
  if(state.page==="devices"){
    const current=[...document.querySelectorAll(".device-inventory-content [data-inventory-device]")].find(card=>card.dataset.inventoryDevice===deviceId);
    if(!current)return;
    const template=document.createElement("template");template.innerHTML=renderDeviceInventoryPage();
    const updated=[...template.content.querySelectorAll("[data-inventory-device]")].find(card=>card.dataset.inventoryDevice===deviceId);
    if(!updated)return;
    current.className=updated.className;current.setAttribute("aria-label",updated.getAttribute("aria-label")||"");
    const currentToggle=current.querySelector("[data-favorite-toggle]"),nextToggle=updated.querySelector("[data-favorite-toggle]");
    if(currentToggle&&nextToggle){currentToggle.className=nextToggle.className;for(const name of ["aria-pressed","aria-label","title","disabled"]){if(nextToggle.hasAttribute(name))currentToggle.setAttribute(name,nextToggle.getAttribute(name));else currentToggle.removeAttribute(name);}}
    const currentStatus=current.querySelector(".favorite-device-info > span"),nextStatus=updated.querySelector(".favorite-device-info > span");if(currentStatus&&nextStatus&&currentStatus.textContent!==nextStatus.textContent)currentStatus.textContent=nextStatus.textContent;
    const currentMetrics=current.querySelector(".inventory-device-metrics"),nextMetrics=updated.querySelector(".inventory-device-metrics");if(currentMetrics&&nextMetrics&&currentMetrics.innerHTML!==nextMetrics.innerHTML)currentMetrics.innerHTML=nextMetrics.innerHTML;
  }
}
function updateOpenTuyaDeviceDialog(deviceId){
  const rawDevice=state.tuyaDevices.find(item=>item.device_id===deviceId),device=tuyaDeviceWithPidMap(rawDevice),reading=state.tuyaReadings.find(item=>item.device_id===deviceId);
  if(!device||!reading)return;
  document.querySelectorAll(`dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"]`).forEach(dialog=>{
    const connectionNode=dialog.querySelector("[data-reference-status]");if(connectionNode)connectionNode.textContent=`${tuyaDeviceState(device,reading)} · ${tuyaConnectionSummary(reading)}`;
    dialog.querySelectorAll("[data-tuya-detail-lan-status]").forEach(node=>{if(!node.textContent||node.textContent.includes("a aguardar a leitura LAN normal"))node.textContent=tuyaConnectionSummary(reading);});
    dialog.querySelectorAll("[data-tuya-quick-toggle],[data-breaker-detail-toggle],.reference-power[data-favorite-toggle]").forEach(button=>{
      const code=button.dataset.tuyaQuickToggle||button.dataset.breakerDetailToggle||button.dataset.favoriteCode,pending=pendingTuyaSwitchStates.get(`${deviceId}::${code}`),value=pending?.timedOut?undefined:pending?.value??tuyaSwitchState(device,reading,code);
      button.classList.remove("on","off","unknown");button.classList.add(value===true?"on":value===false?"off":"unknown");button.classList.toggle("pending",pendingTuyaSwitchStates.has(`${deviceId}::${code}`));
      button.setAttribute("aria-pressed",String(value===true));
      if(button.hasAttribute("data-tuya-quick-toggle")){
        const label=dialog.querySelector(`[data-tuya-channel-label="${CSS.escape(code)}"] strong`)?.textContent||code;
        button.setAttribute("aria-label",`${label} · ${value===true?"ligado":value===false?"desligado":"estado por confirmar no varrimento"}`);
        if(!button.querySelector("svg"))button.textContent=value===true?"ON":value===false?"OFF":"—";
      }else button.setAttribute("aria-label",value===true?"Desligar":value===false?"Ligar":"Estado por confirmar");
    });
    if(tuyaIsBreaker(device)){
      const metrics=tuyaSimpleReadings(device,reading),metricByLabel=new Map(metrics.map(item=>[item.label,item.value]));
      dialog.querySelectorAll("[data-breaker-live-metric]").forEach(node=>{node.textContent=metricByLabel.get(node.dataset.breakerLiveMetric)||tuyaBreakerMetricFallback(device,reading);});
      dialog.querySelectorAll("[data-reference-metric]").forEach(node=>{const value=metricByLabel.get(node.dataset.referenceMetric);node.textContent=value!==undefined&&value!==null&&value!==""?value:"Sem leitura";});
      const code=tuyaPrimarySwitchCode(device,tuyaSwitchCodes(device)),value=code?tuyaSwitchState(device,reading,code):undefined,stateNode=dialog.querySelector("[data-breaker-live-state]");
      if(stateNode)stateNode.textContent=value===true?"Ligado":value===false?"Desligado":"Estado por confirmar";
    }
    const referenceState=dialog.querySelector("[data-reference-main-state]");if(referenceState){const channels=tuyaSwitchChannelCodes(device),code=channels[0]||tuyaPrimarySwitchCode(device,tuyaSwitchCodes(device)),value=code?tuyaSwitchState(device,reading,code):undefined;referenceState.textContent=value===true?"Ligado":value===false?"Desligado":"Sem leitura";}
    dialog.querySelectorAll("[data-reference-channel-state]").forEach(node=>{const value=tuyaSwitchState(device,reading,node.dataset.referenceChannelState);node.textContent=value===true?"Ligado":value===false?"Desligado":"Sem leitura";});
    const liveMetrics=tuyaSimpleReadings(device,reading),livePower=liveMetrics.find(item=>item.label==="Potência");const powerNode=dialog.querySelector("[data-reference-power-watts]");if(powerNode)powerNode.textContent=livePower?.value??"Sem leitura";
    const observedStatus=Array.isArray(reading.status)?reading.status:[];
    dialog.querySelectorAll("[data-reference-brightness]").forEach(input=>{if(document.activeElement===input)return;const code=input.dataset.referenceBrightness,spec=tuyaDeviceSpecs(device).find(item=>item?.code===code),item=observedStatus.find(entry=>entry?.code===code);if(!spec||item?.value===undefined||item?.value===null)return;let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}const min=Number(values.min??device.level_min??0),max=Number(values.max??device.level_max??100),scale=Number(values.scale||0),numeric=Number(item.value)/(10**scale);if(!Number.isFinite(numeric)||max<=min)return;const level=Math.max(0,Math.min(100,Math.round((numeric-min)/(max-min)*100)));input.value=String(level);input.parentElement.style.setProperty("--level",`${level}%`);const caption=input.closest(".reference-channel")?.querySelector(".reference-channel-brightness strong");if(caption)caption.textContent=`${level}%`;if(input.dataset.referenceChannel==="0"){const summary=dialog.querySelector("[data-reference-brightness-summary]");if(summary)summary.textContent=`${level}%`;}});
  });
}
function resetToDemoAfterLogout() {
  state.mode = "DISCONNECTED"; state.dataStatus = "UNAVAILABLE"; state.dataError = null; state.energyEngine = null;
  state.equipment = []; state.tuyaDevices=[];state.tuyaReadings=[];lastTuyaReadAt=0;state.lastUpdated = null; state.lastMeasurementAt = null; render();
}
function localDayKey(date=new Date()) { return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`; }
function localDayBounds(dayKey) {
  const [year,month,day]=dayKey.split("-").map(Number),start=new Date(year,month-1,day),end=new Date(year,month-1,day+1);
  return {start,end,hours:(end-start)/3_600_000};
}
function energyHistoryChartMarkup(history,dayKey,loading,error) {
  const {start,end}=localDayBounds(dayKey),chartStart=start.getTime(),chartEnd=end.getTime();
  const keyFor=stamp=>{const d=new Date(stamp);return Number.isFinite(d.getTime())?localDayKey(d):"";};
  const actual=(history?.pv_daily_energy||[]).filter(item=>keyFor(item.observed_at)===dayKey&&Number.isFinite(Number(item.value))).map(item=>({stamp:Date.parse(item.observed_at),kwh:Number(item.value)/(item.unit==="Wh"?1000:1)})).sort((a,b)=>a.stamp-b.stamp);
  const forecasts=(history?.solar_day_forecast||[]).filter(item=>keyFor(item.observed_at)===dayKey&&Number.isFinite(Number(item.value))).map(item=>({stamp:Date.parse(item.observed_at),kwh:Number(item.value)})).sort((a,b)=>a.stamp-b.stamp);
  const potentials=(history?.solar_day_forecast||[]).filter(item=>keyFor(item.observed_at)===dayKey&&Number.isFinite(Number(item.potential_max_total_kwh))).map(item=>({stamp:Date.parse(item.observed_at),kwh:Number(item.potential_max_total_kwh)})).sort((a,b)=>a.stamp-b.stamp);
  const maxKwh=Math.max(1,...actual.map(point=>point.kwh),...forecasts.map(point=>point.kwh),...potentials.map(point=>point.kwh)),x=stamp=>42+(stamp-chartStart)/(chartEnd-chartStart)*536,y=value=>188-value/maxKwh*148;
  const pathFor=points=>points.map((point,index)=>`${index?"L":"M"}${x(point.stamp).toFixed(1)} ${y(point.kwh).toFixed(1)}`).join(" ");
  const actualPath=pathFor(actual),forecastPath=pathFor(forecasts),potentialPath=pathFor(potentials),latestActual=actual.at(-1)?.kwh??null,latestForecast=forecasts.at(-1)?.kwh??null,latestPotential=potentials.at(-1)?.kwh??null,forecastRevision=latestForecast==null||forecasts.length<2?null:latestForecast-forecasts[0].kwh;
  const fmt=value=>value==null?"—":new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(value);
  const dayLabel=new Intl.DateTimeFormat("pt-PT",{weekday:"long",day:"numeric",month:"long",year:"numeric"}).format(start);
  const oldest=new Date();oldest.setHours(0,0,0,0);oldest.setDate(oldest.getDate()-89);const oldestKey=localDayKey(oldest),todayKey=localDayKey();
  const powerFields=[["pv_total_power","FV","engine-chart-pv"],["load_total_power","Consumo da casa","engine-chart-load"],["battery_output_power","Bateria · + a descarregar","engine-chart-battery"]];
  const power=powerFields.map(([field,label,className])=>({field,label,className,points:(history?.[field]||[]).filter(item=>keyFor(item.observed_at)===dayKey&&Number.isFinite(Number(item.value))).map(item=>({stamp:Date.parse(item.observed_at),kw:Number(item.value)/(item.unit==="kW"?1:1000)})).sort((a,b)=>a.stamp-b.stamp)}));
  const powerValues=power.flatMap(line=>line.points.map(point=>point.kw)).filter(Number.isFinite),powerLo=Math.min(0,...powerValues),powerHi=Math.max(.2,...powerValues),powerSpan=Math.max(.2,powerHi-powerLo),powerY=value=>188-(value-powerLo)/powerSpan*148;
  const powerPaths=power.map(line=>`<path class="${line.className}" d="${line.points.map((point,index)=>`${index?"L":"M"}${x(point.stamp).toFixed(1)} ${powerY(point.kw).toFixed(1)}`).join(" ")}" fill="none"/>`).join("");
  const empty=!actual.length&&!forecasts.length&&!potentials.length;
  const recordedStatus=!forecasts.length?`<p class="field-note">Ainda não existem previsões guardadas para este dia. O Gateway começa a guardar a evolução da previsão nesta versão; os dias anteriores mostram apenas a produção medida disponível.</p>`:"";
  return `<div class="engine-history-toolbar"><strong>${esc(dayLabel)}</strong></div>${loading?`<div class="empty-state">A carregar os cálculos e medições guardados desse dia…</div>`:error?`<div class="empty-state">Não foi possível carregar este dia: ${esc(error)}</div>`:empty?`<div class="empty-state">Não há amostras guardadas neste dia. Usa os botões para escolher outro.</div>`:`<section class="engine-forecast-comparison"><h3>Previsão do dia comparada com a produção medida</h3><p>As duas linhas mostram, ao longo do dia, o total final previsto e a energia FV medida até cada hora.</p><div class="engine-history-plot"><button type="button" class="engine-history-arrow left" data-engine-history-day="-1" ${dayKey<=oldestKey||loading?"disabled":""} aria-label="Retroceder 24 horas">‹</button><svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Previsão de energia FV e produção medida em ${esc(dayLabel)}"><path class="chart-grid" d="M42 40H578 M42 88H578 M42 136H578 M42 188H578"/><path class="engine-chart-measured" d="${actualPath}" fill="none"/><path class="engine-chart-forecast" d="${forecastPath}" fill="none"/><path class="engine-chart-potential" d="${potentialPath}" fill="none"/><g class="chart-label"><text x="42" y="210">00:00</text><text x="300" y="210">12:00</text><text x="545" y="210">24:00</text></g></svg><button type="button" class="engine-history-arrow right" data-engine-history-day="1" ${dayKey>=todayKey||loading?"disabled":""} aria-label="Avançar 24 horas">›</button></div><div class="engine-history-legend"><span><i class="engine-chart-measured"></i>FV medido acumulado</span><span><i class="engine-chart-forecast"></i>Previsão diária</span><span><i class="engine-chart-potential"></i>Potencial ajustado</span></div><div class="ws-kpi-grid engine-history-totals"><article class="ws-kpi"><small>Produção FV medida · último registo</small><strong>${fmt(latestActual)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Última previsão do total diário</small><strong>${fmt(latestForecast)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Potencial máximo ajustado</small><strong>${fmt(latestPotential)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Previsto ainda por produzir</small><strong>${fmt(latestForecast==null||latestActual==null?null:Math.max(0,latestForecast-latestActual))} <em>kWh</em></strong></article><article class="ws-kpi"><small>Ajuste da previsão no dia</small><strong>${fmt(forecastRevision)} <em>kWh</em></strong></article></div>${recordedStatus}<details class="engine-power-history" open><summary>Ver potência instantânea, consumo e bateria</summary><div class="engine-history-plot"><button type="button" class="engine-history-arrow left" data-engine-history-day="-1" ${dayKey<=oldestKey||loading?"disabled":""} aria-label="Retroceder 24 horas">‹</button><svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Potência FV, consumo e bateria em ${esc(dayLabel)}"><path class="chart-grid" d="M42 40H578 M42 88H578 M42 136H578 M42 188H578"/><path class="engine-chart-zero" d="M42 ${powerY(0).toFixed(1)}H578"/>${powerPaths}<g class="chart-label"><text x="42" y="210">00:00</text><text x="300" y="210">12:00</text><text x="545" y="210">24:00</text></g></svg><button type="button" class="engine-history-arrow right" data-engine-history-day="1" ${dayKey>=todayKey||loading?"disabled":""} aria-label="Avançar 24 horas">›</button></div><div class="engine-history-legend"><span><i class="engine-chart-pv"></i>Produção FV</span><span><i class="engine-chart-load"></i>Consumo da casa</span><span><i class="engine-chart-battery"></i>Bateria · positivo = descarga</span></div></details><p class="field-note">A produção medida vem do contador diário do inversor. O previsto ainda por produzir é a diferença entre a previsão atual e a energia medida até à hora do último registo; compara essa curva com o total conhecido no fecho do dia para avaliar o erro final.</p></section>`}`;
}
function renderEngineHistoryDialog() {
  const chart=state.engineHistoryChart;if(!chart.open)return "";
  return `<dialog id="engine-history-dialog" class="engine-history-dialog"><div class="engine-history-dialog-head"><div><p class="eyebrow">ENGINE · HISTÓRICO GUARDADO</p><h2>Produção, consumo e bateria</h2></div><button type="button" class="icon-button" data-engine-history-close aria-label="Fechar gráfico">×</button></div>${energyHistoryChartMarkup(state.energyEngine?.history,chart.dateKey||localDayKey(),chart.loading,chart.error)}</dialog>`;
}
async function loadEngineHistoryDay(dayKey) {
  const chart=state.engineHistoryChart;chart.open=true;chart.dateKey=dayKey;chart.loading=true;chart.error=null;render();
  try {
    const {start,end}=localDayBounds(dayKey),until=end.getTime()>Date.now()?new Date():end;
    const hours=Math.max(1,Math.min(168,Math.ceil((until-start)/3_600_000)));
    const result=await readGatewayEnergy(hours,until.toISOString());
    state.energyEngine=result.engine||state.energyEngine;chart.loading=false;chart.error=null;
  } catch(error) { chart.loading=false;chart.error=error.message||"erro de consulta"; }
  render();
}
function renderLiveEnergyEngine() {
  const data = state.energyEngine;
  if (!data) return `<div class="empty-state">O Gateway ainda não forneceu o resumo energético. Atualiza os dados.</div>`;
  const current = data.current || {}, forecast = data.forecast?.solar_power || {}, readings=data.latest_readings||{};
  const reportedSocOnly=current.battery_soc_percent==null&&current.battery_inverter_reported_soc_percent!=null;
  const displayedSoc=current.battery_soc_percent??current.battery_inverter_reported_soc_percent;
  const autonomy=current.battery_autonomy_forecast||{};
  const number = (value, digits=1) => Number.isFinite(value) ? Number(value).toFixed(digits) : "—";
  const series = data.history?.pv_total_power || [];
  const points = series.map((item, i) => ({ x: i, y: Number(item.value) / (item.unit === "W" ? 1000 : 1) })).filter(p => Number.isFinite(p.y));
  const max = Math.max(1, ...points.map(p => p.y), Number(forecast.one_hour_value) || 0);
  const path = points.map((p,i)=>`${i?'L':'M'}${40+(points.length>1?p.x/(points.length-1)*540:0)} ${180-p.y/max*140}`).join(" ");
  const time = data.updated_at ? timeLabel(data.updated_at) : "Sem leitura";
  const ownerConfig = sessionInfo().user?.role === "owner";
  const forecastLabel = forecast.confidence === "LOW_INDICATIVE" ? "Tendência indicativa · apenas histórico" : "Histórico insuficiente para projeção";
  const socReasons={BATTERY_CAPACITY_NOT_CONFIGURED:'Configura a capacidade total das baterias.',NO_BATTERY_VOLTAGE_HISTORY:'Ainda não há histórico de tensão local para ancorar o SOC.',FRESH_CHARGE_DISCHARGE_HISTORY_REQUIRED:'Falta uma amostra local recente de potência de carga/descarga.',FULL_CHARGE_STABILIZATION_NOT_CONFIRMED:'O Gateway ainda não confirmou uma carga completa estável pela tensão e potência.',POWER_HISTORY_DOES_NOT_COVER_VOLTAGE_ANCHOR:'O histórico de potência não cobre o momento em que a bateria estabilizou no máximo.',GAP_IN_POWER_HISTORY:'Há um intervalo demasiado grande no histórico de potência para integrar o SOC.',GAP_IN_POWER_HISTORY_REANCHOR_REQUIRED:'O histórico recente tem uma lacuna; é preciso confirmar nova âncora de carga completa.'};
  const socEstimateReason=socReasons[current.battery_soc_estimate?.reason]||'A aguardar tensão e potência locais recentes; o SOC comunicado pelo inversor não é usado como estimativa.';
  const socAnchorLabel=current.battery_soc_estimate?.anchor_source==="DEYE_CLOUD_HISTORY_VOLTAGE_AND_SIGNED_POWER"?"Âncora obtida por tensão e potência do histórico; percentagem Deye ignorada.":"Âncora de carga confirmada pelo Gateway.";
  const readingTile=(field,label)=>{const item=readings[field];return `<div class="detail-item"><small>${esc(label)}</small><strong>${item?`${esc(item.value)} ${esc(item.unit||"")}`:"—"}</strong><small>${item?`${esc(item.trust)} · ${esc(timeLabel(item.observed_at))}`:"Sem leitura"}</small></div>`;};
  const dispatchRows=(data.dispatch?.actions||[]).map(action=>`<div class="detail-item"><small>${esc(action.name||action.load_id)}</small><strong>${esc(action.state)}</strong><small>${Number.isFinite(action.target_power_w)?`${esc(action.target_power_w)} W · `:""}${esc(action.control_type||"")}</small></div>`).join("");
  const meterEntries=Object.entries(current.tuya_load_telemetry||{}),meterUseCounts=meterEntries.reduce((counts,[,meter])=>{if(meter.device_id)counts[meter.device_id]=(counts[meter.device_id]||0)+1;return counts;},{}),seenMeters=new Set();
  const meterRows=meterEntries.filter(([,meter])=>{const key=meter.device_id||meter.name;if(!key)return true;if(seenMeters.has(key))return false;seenMeters.add(key);return true;}).map(([id,meter])=>{const metrics=meter.metrics||{},measurements=[ ["Potência",metrics.power,"W"],["Tensão",metrics.voltage,"V"],["Corrente",metrics.current,"A"],["Consumo hoje",metrics.energy,"kWh"] ].filter(([,item])=>item&&Number.isFinite(Number(item.value))).map(([label,item,unit])=>`<span>${label}: ${new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(item.value)} ${unit}</span>`).join(" · "),switchState=typeof meter.switch_on==="boolean"?`Disjuntor ${meter.switch_on?"ligado":"desligado"}`:"Estado do disjuntor sem leitura",shared=meter.device_id&&meterUseCounts[meter.device_id]>1?` · Medição partilhada por ${meterUseCounts[meter.device_id]} cargas`:"";return `<div class="detail-item"><small>${esc(meter.name||id)}</small><strong>${meter.fresh?"Leitura recente":meter.verified?"Sem leitura recente":"Por confirmar"}</strong><small>${switchState}${measurements?` · ${measurements}`:" · Sem medições DPS reconhecidas com unidade validada"}${shared}${meter.observed_at?` · ${esc(timeLabel(meter.observed_at))}`:""}</small></div>`;}).join("");
  const execution=data.dispatch_execution;
  const solarSiteConfig="";
  const solarDay=data.forecast?.solar_day||{};
  const solarForecastConfidence=solarDay.confidence==="MEDIUM_INDICATIVE"?"MÉDIA":solarDay.confidence==="LOW_INDICATIVE"?"BAIXA":solarDay.confidence||"SEM DADOS";
  const solarExpectedRemaining=solarDay.state==="ESTIMATED"?solarDay.remaining_estimate_kwh:null;
  const solarPotentialRemaining=solarDay.state==="ESTIMATED"?solarDay.potential_max_remaining_kwh:null;
  const expectedLoadRemaining=solarDay.state==="ESTIMATED"?solarDay.expected_load_remaining_kwh:null;
  const netEnergyBalance=solarDay.state==="ESTIMATED"?solarDay.net_energy_balance_kwh:null;
  const curtailment=current.curtailment_assessment||{};
  const curtailmentLabel=curtailment.state==="POSSIBLE_CURTAILMENT"?"Possível limitação FV":curtailment.state==="NO_CURRENT_EVIDENCE"?"Sem indício atual de limitação":"A avaliar limitação FV";
  const solarEngineCards=`<section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">PREVISÃO SOLAR · ENGINE</p><h2>Até ao fim do dia</h2></div><span class="source-tag">${esc(solarForecastConfidence)}</span></div><div class="energy-outlook-grid engine-solar-outlook"><article class="ws-kpi solar-day-forecast-card"><small>Solar restante</small><strong>${solarExpectedRemaining!=null?number(Number(solarExpectedRemaining),2):"—"} <em>kWh</em></strong><span>${solarDay.state==="ESTIMATED"?`Total previsto hoje: ${number(Number(solarDay.estimated_total_kwh),2)} kWh`:esc(solarDay.reason||"A aguardar dados")}</span></article><article class="ws-kpi solar-day-forecast-card"><small>Potencial restante</small><strong>${solarPotentialRemaining!=null?number(Number(solarPotentialRemaining),2):"—"} <em>kWh</em></strong><span>Referência ajustada ao histórico</span></article><article class="ws-kpi solar-day-forecast-card"><small>Saldo após consumo</small><strong>${netEnergyBalance!=null?number(Number(netEnergyBalance),2):"—"} <em>kWh</em></strong><span>${netEnergyBalance!=null?`${netEnergyBalance>=0?"Disponível estimado":"Défice previsto"} · consumo ${number(Number(expectedLoadRemaining),2)} kWh`:"A aguardar leituras de consumo"}</span></article></div><p class="field-note">${esc(curtailmentLabel)} · ${esc(curtailment.reason||"Atualizado com produção e consumo recentes.")} · confiança do consumo ${esc(solarDay.load_forecast_confidence||"baixa")}.</p></section>`;
  return `<div class="page-heading"><div><p class="eyebrow">ENERGY / ENGINE</p><h1>Medições e previsões</h1><p>Produção, bateria, leituras e histórico do sistema energético.</p></div><button class="button secondary" id="engine-refresh">Atualizar ↻</button></div><nav class="ws-horizontal-tabs energy-engine-tabs" role="tablist" aria-label="Secções do Engine energético"><button type="button" role="tab" data-engine-tab="summary" aria-controls="engine-panel-summary" aria-selected="${energyEngineActiveTab==="summary"}" class="${energyEngineActiveTab==="summary"?"selected":""}">Resumo</button><button type="button" role="tab" data-engine-tab="readings" aria-controls="engine-panel-readings" aria-selected="${energyEngineActiveTab==="readings"}" class="${energyEngineActiveTab==="readings"?"selected":""}">Leituras</button><button type="button" role="tab" data-engine-tab="history" aria-controls="engine-panel-history" aria-selected="${energyEngineActiveTab==="history"}" class="${energyEngineActiveTab==="history"?"selected":""}">${ownerConfig?"Histórico":"Histórico"}</button></nav><div id="engine-panel-summary" role="tabpanel" data-engine-tab-panel="summary">
  ${solarSiteConfig}
  ${solarEngineCards}
  <div class="ws-kpi-grid"><article class="ws-kpi"><small>SOC da bateria</small><strong>${number(displayedSoc,1)} <em>%</em></strong><span>${reportedSocOnly?`Reportado pelo inversor · ${esc(current.battery_inverter_reported_soc_trust||"origem não verificada")} · não usado nos cálculos de energia`:current.battery_soc_percent==null?esc(socEstimateReason):`${esc(current.battery_soc_estimate?.state||"SOC estimado")} · ${esc(data.trust)} · ${esc(time)} · ${esc(socAnchorLabel)}`}${current.battery_at_configured_maximum?" · LIMITE MÁXIMO ATINGIDO":""}</span></article><article class="ws-kpi"><small>Energia acima do SOC mínimo</small><strong>${number(current.battery_energy_available_kwh_above_minimum,2)} <em>kWh</em></strong><span>${current.battery_capacity_kwh == null ? "Configura capacidade total para calcular" : `Espaço até máximo: ${number(current.battery_charge_headroom_kwh_to_maximum,2)} kWh · reserva ${number(current.minimum_soc_percent,0)}–${number(current.maximum_soc_percent,0)}%`}</span></article><article class="ws-kpi battery-autonomy-card"><small>Autonomia até ao corte · sem solar</small><strong>${number(autonomy.hours,1)} <em>h</em></strong><span>${autonomy.state==="ESTIMATED"?`Corte provável ${autonomy.estimated_cutoff_at?esc(timeLabel(autonomy.estimated_cutoff_at)):"—"} · confiança ${esc(autonomy.confidence||"BAIXA")} · perfil ${esc(autonomy.history_days_used??0)} dias + consumo atual`:`A aguardar energia disponível e leituras de consumo`}</span></article><article class="ws-kpi"><small>Produção FV atual</small><strong>${number(current.pv_power_w == null ? null : current.pv_power_w/1000,2)} <em>kW</em></strong><span>PV1 + PV2 · medida</span></article><article class="ws-kpi"><small>Consumo atual</small><strong>${number(current.load_power_w == null ? null : current.load_power_w/1000,2)} <em>kW</em></strong><span>Canal de cargas Deye</span></article></div>
  </div><div id="engine-panel-history" role="tabpanel" data-engine-tab-panel="history" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO GUARDADO NO GATEWAY · ÚLTIMAS 24 H</p><h2>Produção e tendência de FV · kW</h2></div><span class="source-tag">${esc(series.length)} amostras</span></div><button type="button" class="engine-chart-open" id="engine-chart-open" aria-label="Abrir e percorrer o gráfico diário do Engine">${points.length?`<svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Histórico de potência fotovoltaica lido pelo Gateway"><path class="chart-grid" d="M40 35H600 M40 80H600 M40 125H600 M40 180H600"/><path d="${path}" class="chart-line" fill="none"/><g class="chart-label"><text x="40" y="202">mais antigo</text><text x="510" y="202">agora</text></g></svg>`:`<div class="empty-state">Ainda não há amostras recentes. Abre o gráfico para consultar outros dias guardados.</div>`}<span>Abre o gráfico para percorrer os dias com histórico · FV, consumo e bateria</span></button><div class="ws-kpi-grid"><article class="ws-kpi"><small>Potência FV estimada +1 h</small><strong>${number(forecast.one_hour_value,2)} <em>kW</em></strong><span>${esc(forecastLabel)}</span></article><article class="ws-kpi"><small>Potência FV estimada +3 h</small><strong>${number(forecast.three_hour_value,2)} <em>kW</em></strong><span>Regressão linear · limitada a 15 kW</span></article><article class="ws-kpi"><small>Consumo estimado +1 h</small><strong>${number(data.forecast?.load_power?.one_hour_value,2)} <em>kW</em></strong><span>Histórico de cargas · baixa confiança</span></article><article class="ws-kpi"><small>SOC estimado +1 h</small><strong>${number(data.forecast?.battery_soc?.one_hour_value,1)} <em>%</em></strong><span>Tendência histórica simples · baixa confiança</span></article></div><p class="field-note">${esc(data.forecast?.notice || "")} ${esc(data.limits?.notice || "")}</p></section>
  </div><div id="engine-panel-readings" role="tabpanel" data-engine-tab-panel="readings" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">MAPA DE REGISTOS DEYE · LEITURAS RECENTES</p><h2>FV, bateria e contadores</h2></div><span class="source-tag">LIVE_UNVERIFIED</span></div><div class="device-detail-grid telemetry-grid">${readingTile("pv1_input_power","Potência FV 1")}${readingTile("pv1_voltage","Tensão FV 1")}${readingTile("pv1_current","Corrente FV 1")}${readingTile("pv2_input_power","Potência FV 2")}${readingTile("pv2_voltage","Tensão FV 2")}${readingTile("pv2_current","Corrente FV 2")}${readingTile("battery_voltage","Tensão bateria")}${readingTile("battery_output_current","Corrente bateria")}${readingTile("battery_output_power","Potência bateria")}${readingTile("battery_temperature","Temperatura bateria")}${readingTile("pv_daily_energy","Energia FV hoje")}${readingTile("pv_total_energy","Energia FV acumulada")}${readingTile("load_daily_energy","Consumo hoje")}${readingTile("load_total_energy","Consumo acumulado")}${readingTile("battery_daily_charge_energy","Carga da bateria hoje")}${readingTile("battery_daily_discharge_energy","Descarga da bateria hoje")}${readingTile("battery_max_charge_current","Limite configurado de carga")}${readingTile("battery_max_discharge_current","Limite configurado de descarga")}<div class="detail-item"><small>Potência máxima de carga calculada</small><strong>${number(current.battery_configured_max_charge_power_kw,2)} kW</strong><small>Estimativa a partir da tensão e limite configurado</small></div><div class="detail-item"><small>Potência máxima de descarga calculada</small><strong>${number(current.battery_configured_max_discharge_power_kw,2)} kW</strong><small>Estimativa a partir da tensão e limite configurado</small></div></div><p class="field-note">As potências derivadas multiplicam tensão medida pelos limites configurados no inversor; são estimativas de configuração, não limites dinâmicos do BMS. O mapa candidato continua por validar para o firmware exato.</p></section>
  <section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">DESPACHO DE CARGAS</p><h2>${esc(data.dispatch?.state||"DISABLED")}</h2></div><span class="source-tag">${execution?.occurred_at?`Último ciclo ${esc(timeLabel(execution.occurred_at))}`:"Sem ciclo executado"}</span></div><p class="field-note">${esc(data.dispatch?.reason||"")} ${execution?.state?`· Último resultado: ${esc(execution.state)}`:""}</p><div class="device-detail-grid">${dispatchRows||"<div class=\"empty-state\">Sem ações planeadas.</div>"}</div><p class="field-note">O ciclo automático usa a cadência configurada, com mínimo de 5 minutos. Cada alteração Tuya exige leitura e confirmação; um relé não confirmado bloqueia o minerador dependente.</p></section>
  <section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">MEDIÇÕES INDIVIDUAIS · TUYA / DPS</p><h2>Consumo das cargas associadas</h2></div></div><p class="field-note">As leituras são ligadas ao disjuntor Tuya selecionado para a carga. Só aparecem unidades identificadas no esquema do dispositivo; dados antigos ficam assinalados como sem leitura recente.</p><div class="device-detail-grid">${meterRows||"<div class=\"empty-state\">Ainda não há cargas com DPS de medição Tuya reconhecidas.</div>"}</div></section>
  </div>${renderEngineHistoryDialog()}`;
}
function renderMinerBreakerAssociation(activeEquipmentId=null) {
  const devices=(state.tuyaDevices||[]).flatMap(device=>{
    const switches=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase())&&typeof item.code==="string");
    const primary=switches.find(item=>item.code===device.switch_code)||(switches.length===1?switches[0]:switches.find(item=>["switch","switch_1"].includes(item.code)));
    return primary?[{device,code:primary.code}]:[];
  });
  const allMinerLoads=(state.energyEngine?.configuration?.loads||[]).filter(load=>load.kind==="miner"&&load.control_type==="antminer_braiins");
  const miners=activeEquipmentId?allMinerLoads.filter(load=>load.equipment_id===activeEquipmentId||(!load.equipment_id&&allMinerLoads.length===1)):allMinerLoads;
  const minerIdentities=(state.gatewayDeviceInventory||[]).filter(item=>item?.mac&&["miner","mineradora","antminer"].includes(String(item.device_type||"").toLowerCase()));
  const notice=state.energyConfigStatus||"";
  return miners.length?`<section id="engine-miner-breaker" class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO DA MINERADORA</p><h2>Disjuntor de alimentação e medição</h2></div></div><p>O nome e as características são guardados na ficha da mineradora. A associação abaixo liga um disjuntor separado para leitura de potência.</p>${miners.map(miner=>`<div class="miner-load-config" data-miner-binding="${esc(miner.id)}"><h3>${esc(miner.name)}</h3><details class="miner-load-editor" open><summary>Editar nome, potência e prioridade</summary><div class="ws-config-grid"><label class="feature-field">Device físico da mineradora (MAC)<select data-miner-load-identity><option value="">${minerIdentities.length?"Selecionar MAC da mineradora":"Sem MAC de mineradora no inventário; a ligação será feita quando estiver disponível"}</option>${minerIdentities.map(item=>`<option value="${esc(item.device_key)}" ${item.device_key===miner.device_key?"selected":""}>${esc(item.name)} · ${esc(item.mac)}</option>`).join("")}</select></label><label class="feature-field">Nome<input data-miner-load-name maxlength="120" value="${esc(miner.name)}"></label><label class="feature-field">Potência nominal (W)<input data-miner-load-rated type="number" min="1" max="100000" step="1" value="${miner.rated_power_w}"></label><label class="feature-field">Potência mínima (W)<input data-miner-load-minimum type="number" min="0" max="2900" step="1" value="${miner.minimum_power_w}"></label><label class="feature-field">Potência máxima (W)<input data-miner-load-maximum type="number" min="1" max="2900" step="1" value="${miner.maximum_power_w}"></label><label class="feature-field">Prioridade (menor número primeiro)<input data-miner-load-priority type="number" min="1" max="100" value="${miner.priority}"></label><label class="feature-field"><input data-miner-load-automatic type="checkbox" ${miner.automatic?"checked":""}> Elegível para automatização</label></div><button type="button" class="button secondary" data-miner-load-save="${esc(miner.id)}">Guardar alterações</button></details><div class="ws-config-grid miner-breaker-binding"><label class="feature-field">Disjuntor Tuya para medição<select data-miner-breaker-device><option value="">${devices.length?"Escolher pelo nome":"Sincroniza os Tuya em Owner → Equipamentos primeiro"}</option>${devices.map(item=>`<option value="${esc(item.device.device_id)}" data-code="${esc(item.code)}" ${item.device.device_id===miner.tuya_device_id?"selected":""}>${esc(item.device.name)}</option>`).join("")}</select></label><button type="button" class="button secondary" data-miner-breaker-save="${esc(miner.id)}">Guardar associação</button></div></div>`).join("")}<p class="ws-inline-note" id="engine-miner-breaker-status" role="status" aria-live="polite">${esc(notice)}</p></section>`:`<section id="engine-miner-breaker" class="panel feature-panel"><h2>Disjuntor de alimentação e medição</h2><p>A mineradora ainda não está registada como carga. Podes criar a carga aqui e associar o disjuntor à parte.</p>${renderLoadBuilder("miner")}<p class="field-note">Guardar esta associação não envia comandos físicos à mineradora nem ao disjuntor.</p><p class="ws-inline-note" id="engine-miner-breaker-status" role="status" aria-live="polite">${esc(notice)}</p></section>`;
}
function equipmentConnectionIsLive(item,maxAgeMs=90_000){
  if(!item||! ["CONNECTED","ONLINE","OK","ACTIVE"].includes(String(item.connection_state||item.status||"").toUpperCase()))return false;
  const stamp=Date.parse(item.last_communication_at||"");
  return Number.isFinite(stamp)&&Date.now()-stamp>=-5_000&&Date.now()-stamp<=maxAgeMs;
}
function renderLoadBuilder(mode="all") {
  const devices = (state.tuyaDevices||[]).flatMap(device=>{
    const switches=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase())&&typeof item.code==="string");
    const primary=switches.find(item=>item.code===device.switch_code)||(switches.length===1?switches[0]:switches.find(item=>["switch","switch_1"].includes(item.code)));
    return primary?[{device,code:primary.code}]:[];
  });
  const kindOptions=mode==="miner"?`<option value="miner">Mineradora</option>`:`<option value="water_heater">AQS</option><option value="underfloor_heating">Soalho radiante / toalheiro</option><option value="miner">Mineradora</option><option value="ev_charger">Carregador EV</option><option value="generic">Outra carga</option>`;
  const controlOptions=mode==="miner"?`<option value="antminer_braiins">Mineradora · Braiins OS</option>`:`<option value="tuya_smart">Interruptor smart Tuya</option><option value="tuya_breaker">Disjuntor Tuya</option><option value="antminer_braiins">Mineradora · Braiins OS</option><option value="manual">Manual</option><option value="tesla_fleet">Tesla Fleet (leitura apenas)</option>`;
  return `<details class="engine-add-load"><summary>${mode==="miner"?"Associar disjuntor e registar mineradora":"Adicionar carga"}</summary><section class="panel"><h3>${mode==="miner"?"Registar alimentação da mineradora":"Nova carga"}</h3><div class="ws-config-grid"><label class="feature-field">Nome<input id="engine-load-name" maxlength="120" placeholder="Ex.: Antminer S19K Pro" required></label><label class="feature-field">Tipo<select id="engine-load-kind">${kindOptions}</select></label><label class="feature-field">Controlo<select id="engine-load-control">${controlOptions}</select></label><label class="feature-field">Potência nominal (W)<input id="engine-load-rated" type="number" min="1" max="100000" step="1" required></label><label class="feature-field">Potência mínima (W, mineradora)<input id="engine-load-minimum" type="number" min="0" max="2900" step="1" value="800"></label><label class="feature-field">Potência máxima (W, mineradora)<input id="engine-load-maximum" type="number" min="1" max="2900" step="1" value="2500"></label><label class="feature-field">Prioridade (menor número primeiro)<input id="engine-load-priority" type="number" min="1" max="100" value="10"></label><label class="feature-field">Disjuntor Tuya (associação opcional)<select id="engine-load-tuya-device"><option value="">${devices.length ? "Escolher dispositivo pelo nome" : "Sincroniza os dispositivos Tuya em Owner → Equipamentos"}</option>${devices.map(item=>`<option value="${esc(item.device.device_id)}" data-code="${esc(item.code)}">${esc(item.device.name)}</option>`).join("")}</select><small>O Gateway usa apenas os canais de estado e medição disponíveis no perfil desse disjuntor.</small></label><label class="feature-field"><input id="engine-load-automatic" type="checkbox"> Elegível para automatização</label></div><div class="ws-actions"><button class="button primary" id="engine-add-load" type="button">Guardar carga</button><span class="ws-inline-note">A gravação é feita no Gateway. A automatização continua desativada até ser configurada e comissionada.</span></div></section></details>`;
}
function card(item) {
  const category = CATEGORIES.find(c => c.id === item.category) || { icon: "•", label: item.category };
  const reading = formatReading(preferredGatewayReading(item));
  const status = item.category==="mineradoras" ? (equipmentConnectionIsLive(item)?"CONNECTED":"UNAVAILABLE") : classifyEquipment(item);
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
function liveReadingMetric(label, categoryId, icon, targetPage = categoryId) {
  const equipment = state.equipment.find(item => item.category === categoryId && !isSimulated(item));
  const reading = equipment ? preferredGatewayReading(equipment) : null;
  const value = reading ? reading.value : null;
  const detail = reading
    ? `${equipment.name || equipment.id} · ${reading.field || "leitura"} · ${reading.trust || "UNKNOWN"}`
    : "Sem leitura válida do Gateway";
  const formatted = typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(value)
    : value === null || value === undefined ? "—" : String(value);
  return `<button type="button" class="metric-card home-metric-link" data-page="${esc(targetPage)}" aria-label="Abrir área ${esc(label)}"><span class="metric-top"><span>${esc(label)}</span><span class="metric-symbol">${icon}</span></span><span class="metric-value">${esc(formatted)} <small>${esc(reading?.unit || "")}</small></span><span class="metric-sub">${esc(detail)}</span></button>`;
}
function liveMetricReading(equipment, field) {
  return (equipment?.readings || []).find(reading => reading?.field === field) || null;
}
function liveHomeMetric(label, value, unit, icon, detail, extra = "", targetPage = "energia") {
  const formatted = typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(value)
    : value === null || value === undefined ? "—" : String(value);
  return `<button type="button" class="metric-card home-metric-link" data-page="${esc(targetPage)}" aria-label="Abrir área ${esc(label)}"><span class="metric-top"><span>${esc(label)}</span><span class="metric-symbol">${icon}</span></span><span class="metric-value">${esc(formatted)} <small>${esc(unit)}</small></span><span class="metric-sub">${esc(detail)}</span>${extra}</button>`;
}
function liveSolarHomeMetric() {
  const current = state.energyEngine?.current || {};
  const value = current.pv_power_w;
  return liveHomeMetric("Painéis", value, "W", "ϟ",
    Number.isFinite(value) ? "Produção FV · Engine energético" : "Sem leitura de produção FV do Gateway", "", "paineis-solares");
}
function liveBatteryHomeMetric() {
  const current = state.energyEngine?.current || {};
  // Home and Energy must show the same operational SOC. The Deye-reported
  // percentage remains available in the engine diagnostics, but is not the
  // Gateway's voltage-anchor plus signed-power estimate.
  const integratedSoc = state.energyEngine?.current?.battery_soc_percent;
  const soc = typeof integratedSoc === "number" && Number.isFinite(integratedSoc) ? {value:integratedSoc,trust:"Estimativa integrada do Gateway"} : null;
  // Match Energy's displayed convention and value exactly.
  const signedPower = typeof current.battery_power_w === "number" ? -current.battery_power_w : null;
  const flowClass = signedPower === null ? "" : signedPower < 0 ? "discharge" : signedPower > 0 ? "charge" : "idle";
  const flowLabel = signedPower === null ? "Potência da bateria sem leitura"
    : `${signedPower > 0 ? "+" : ""}${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 1 }).format(signedPower)} W · ${signedPower < 0 ? "a descarregar" : signedPower > 0 ? "a carregar" : "sem fluxo"}`;
  const formattedSoc = typeof soc?.value === "number" ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 1 }).format(soc.value) : "—";
  const trust = soc?.trust || "UNKNOWN";
  return `<button type="button" class="metric-card home-metric-link" data-page="baterias" aria-label="Abrir área Baterias"><span class="metric-top"><span>Bateria</span><span class="metric-symbol">▤</span></span><span class="metric-value">${esc(formattedSoc)} <small>${soc ? "%" : ""}</small></span><span class="metric-sub">${esc(soc ? trust : "Estimativa do Gateway indisponível")}</span><span class="metric-sub battery-flow ${flowClass}">${esc(flowLabel)}</span></button>`;
}
function liveMinerHomeMetric() {
  const equipment = state.equipment.find(item => item.category === "mineradoras" && !isSimulated(item));
  const minerOnline = equipmentConnectionIsLive(equipment);
  const currentHash = minerOnline ? (liveMetricReading(equipment, "miner_hashrate_5s_ghs") || liveMetricReading(equipment, "miner_hashrate_avg_ghs")) : null;
  const hashThs = typeof currentHash?.value === "number" ? currentHash.value / 1000 : null;
  const hashUnit = hashThs === null ? "" : "TH/s";
  const energyCurrent=state.energyEngine?.current||{},allMinerLoads=(state.energyEngine?.configuration?.loads||[]).filter(item=>item.kind==="miner"&&item.control_type==="antminer_braiins"),minerLoads=equipment?.id?allMinerLoads.filter(item=>item.equipment_id===equipment.id||(!item.equipment_id&&allMinerLoads.length===1)):(allMinerLoads.length===1?allMinerLoads:[]),meterGroups=new Map();
  let completeMinerMeterSet=minerLoads.length>0;
  for(const load of minerLoads){
    const deviceId=load.tuya_device_id||energyCurrent.tuya_load_telemetry?.[load.id]?.device_id;
    if(!deviceId){completeMinerMeterSet=false;continue;}
    const group=meterGroups.get(deviceId)||{count:0,power:null};group.count++;
    const meter=energyCurrent.tuya_load_telemetry?.[load.id]||Object.values(energyCurrent.tuya_load_telemetry||{}).find(item=>item.device_id===deviceId);
    const value=meter?.fresh&&meter.metrics?.power?.unit==="W"&&Number.isFinite(Number(meter.metrics.power.value))?Number(meter.metrics.power.value):null;
    if(value===null)completeMinerMeterSet=false;else if(group.power===null)group.power=value;
    meterGroups.set(deviceId,group);
  }
  const measuredPower=completeMinerMeterSet&&meterGroups.size?Array.from(meterGroups.values()).every(group=>group.power!==null)?Array.from(meterGroups.values()).reduce((sum,group)=>sum+group.power,0):null:null;
  const sharedMinerMeterCount=Math.max(0,...Array.from(meterGroups.values(),group=>group.count));
  const estimatedMinerPower=minerOnline?liveMetricReading(equipment, "miner_power_w"):null;
  const minerPower=measuredPower!==null?{value:measuredPower,trust:"Leitura real do disjuntor Tuya"}:estimatedMinerPower;
  const powerLimit = liveMetricReading(equipment, "miner_power_limit_w");
  const sub = [
    minerPower ? `${measuredPower!==null?(sharedMinerMeterCount>1?`Disjuntor · potência agregada (${sharedMinerMeterCount} mineradoras)`:"Disjuntor · potência medida"):"Potência reportada pela mineradora"} ${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 0 }).format(minerPower.value)} W` : "Disjuntor · sem leitura recente",
    powerLimit ? `Limite reportado ${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 0 }).format(powerLimit.value)} W` : null,
    !minerOnline && equipment ? "Ligação não confirmada · leitura antiga ocultada" : null,
    !currentHash && minerOnline ? "API ligada · hashrate indisponível" : null,
    !equipment ? "Sem leitura da Antminer" : null,
  ].filter(Boolean).join(" · ");
  const detail = !minerOnline && equipment ? "Mineradora offline · taxa não apresentada" : currentHash ? `${currentHash.field === "miner_hashrate_5s_ghs" ? "Taxa atual" : "Taxa média"} · ${currentHash.trust || "UNKNOWN"}` : "Hashrate sem leitura do Gateway";
  const extra = sub ? `<span class="metric-sub miner-power-details">${esc(sub)}</span>` : "";
  return liveHomeMetric("Mineradora", hashThs, hashUnit, "▦", detail, extra, "mineradoras");
}
function renderSolarDayBalance(projection) {
  const point=projection.find(item=>Number.isFinite(item.item?.solar_expected_remaining_to_day_end_kwh));
  const fmt=value=>Number(value).toLocaleString("pt-PT",{minimumFractionDigits:2,maximumFractionDigits:2});
  const when=point?new Date(point.stamp).toLocaleTimeString("pt-PT",{hour:"2-digit",minute:"2-digit"}):"—";
  const pv=point?fmt(point.item.solar_expected_remaining_to_day_end_kwh):"—";
  return `<section class="solar-day-balance" data-solar-day-balance aria-label="FV restante até ao fim do dia"><div class="solar-day-balance-title"><strong>FV restante até ao fim do dia</strong><span data-balance-time>${point?`a partir das ${when}`:"sem previsão neste horário"}</span></div><div class="solar-day-balance-values"><b data-balance-pv>${pv} kWh</b></div></section>`;
}function chart() {
  if (state.mode !== "SIMULATED") {
    const engine=state.energyEngine||{},history=engine.history||{},forecast=engine.forecast||{},now=Date.now(),start=now-3*3600000,end=now+6*3600000;
    const point=(item,forcedUnit)=>{const stamp=Date.parse(item.observed_at||item.forecast_at||"");let value=Number(item.value);if(!Number.isFinite(stamp)||!Number.isFinite(value))return null;if((item.unit||forcedUnit)==="W")value/=1000;return {stamp,value};};
    const historical=field=>(history[field]||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=start&&p.stamp<=now);
    const future=items=>(items||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=now&&p.stamp<=end);
    const projection=(forecast.solar_projection_15m?.values||[]).map(item=>({stamp:Date.parse(item.forecast_at),load:item.load_power_kw,pv:item.solar_expected_power_kw,potential:item.solar_potential_power_kw,item})).filter(item=>Number.isFinite(item.stamp)&&item.stamp>=now&&item.stamp<=end).sort((a,b)=>a.stamp-b.stamp);
    const pvActual=historical("pv_total_power").sort((a,b)=>a.stamp-b.stamp);
    const pvForecast=(projection.length?projection.filter(p=>Number.isFinite(p.pv)).map(p=>({stamp:p.stamp,value:p.pv})):future(forecast.solar_expected?.hourly_values)).sort((a,b)=>a.stamp-b.stamp);
    const loadActual=historical("load_total_power").sort((a,b)=>a.stamp-b.stamp);
    const loadForecast=(projection.length?projection.filter(p=>Number.isFinite(p.load)).map(p=>({stamp:p.stamp,value:p.load})):future(forecast.load_power?.hourly_values)).sort((a,b)=>a.stamp-b.stamp);
    const historicalPotential=(forecast.solar_potential?.hourly_values||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=start&&p.stamp<=now).sort((a,b)=>a.stamp-b.stamp);
    const potential=(projection.length?[...historicalPotential,...projection.filter(p=>Number.isFinite(p.potential)).map(p=>({stamp:p.stamp,value:p.potential}))]:(forecast.solar_potential?.hourly_values||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=start&&p.stamp<=end)).sort((a,b)=>a.stamp-b.stamp);
    const all=[...pvActual,...pvForecast,...loadActual,...loadForecast,...potential];
    if(!all.length)return `<div class="empty-state">Ainda não há leituras ou previsão. Configura a localização e a potência FV na área Owner.</div>`;
    const max=Math.max(1,...all.map(p=>p.value)),x=stamp=>45+Math.max(0,Math.min(1,(stamp-start)/(end-start)))*555,y=value=>235-Math.max(0,value)/max*190;
    const path=items=>items.map((p,i)=>`${i?"L":"M"}${x(p.stamp).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
    const quarterHour=15*60*1000,quarterly=items=>{const bins=new Map();for(const p of items){const bucket=Math.floor(p.stamp/quarterHour)*quarterHour,bin=bins.get(bucket)||{stamp:bucket,total:0,count:0};bin.total+=p.value;bin.count++;bins.set(bucket,bin);}return [...bins.values()].map(b=>({stamp:b.stamp,value:b.total/b.count})).sort((a,b)=>a.stamp-b.stamp);};
    const loadHistoryBars=quarterly(loadActual).map(p=>({...p,future:false})),loadForecastBars=quarterly(loadForecast).map(p=>({...p,future:true}));
    const bars=items=>items.map(p=>{const width=555*(quarterHour/(end-start));return `<rect x="${(x(p.stamp)-width/2).toFixed(1)}" y="${y(p.value).toFixed(1)}" width="${width.toFixed(1)}" height="${Math.max(0,235-y(p.value)).toFixed(1)}" rx="2" fill="${p.future?'rgba(188,169,190,.08)':'rgba(188,169,190,.30)'}" stroke="rgba(188,169,190,.48)" stroke-width=".65" ${p.future?'stroke-dasharray="2 2"':''}><title>${new Date(p.stamp).toLocaleTimeString("pt-PT",{hour:"2-digit",minute:"2-digit"})} · ${p.future?'consumo previsto':'consumo medido'} ${p.value.toFixed(2)} kW</title></rect>`;}).join("");
    const actualLine=path(pvActual),forecastLine=path(pvForecast.length&&pvActual.length?[pvActual.at(-1),...pvForecast]:pvForecast),futurePotential=potential.filter(p=>p.stamp>=now);
    const quarterStart=Math.ceil(start/quarterHour)*quarterHour,quarterEnd=Math.floor(end/quarterHour)*quarterHour;
    const valueAt=(items,stamp)=>{const ordered=items.filter(p=>Number.isFinite(p.value)).sort((a,b)=>a.stamp-b.stamp);if(!ordered.length)return undefined;let before=null,after=null;for(const p of ordered){if(p.stamp===stamp)return p.value;if(p.stamp<stamp)before=p;else{after=p;break;}}if(before&&after){const ratio=(stamp-before.stamp)/(after.stamp-before.stamp);return before.value+(after.value-before.value)*ratio;}return before?.value;};
    const loadSeries=[...loadActual,...loadForecast],pvSeries=[...pvActual,...pvForecast];
    const projectionByStamp=new Map(projection.map(item=>[item.stamp,item.item]));
    const hitTargets=[];for(let stamp=quarterStart;stamp<=quarterEnd;stamp+=quarterHour){const loadValue=valueAt(loadSeries,stamp),pvValue=valueAt(pvSeries,stamp),potentialValue=valueAt(potential,stamp),point=projectionByStamp.get(stamp);if(loadValue===undefined&&pvValue===undefined&&potentialValue===undefined)continue;hitTargets.push(`<rect class="solar-chart-hit" x="${Math.max(45,x(stamp)-7).toFixed(1)}" y="34" width="14" height="203" tabindex="0" role="button" data-hour="${stamp}" data-load="${loadValue??''}" data-pv="${pvValue??''}" data-potential="${potentialValue??''}" data-net="${point?.expected_net_remaining_kwh_6h??''}" data-daily="${point?.estimated_daily_pv_kwh??''}" data-pv-day="${point?.solar_expected_remaining_to_day_end_kwh??''}" data-load-day="${point?.load_remaining_to_day_end_kwh??''}" data-net-day="${point?.solar_available_after_load_to_day_end_kwh??''}" data-future="${stamp>now}" aria-label="Ver valores das ${new Date(stamp).toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'})}"><title>Ver valores das ${new Date(stamp).toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'})}</title></rect>`);}
    const yTicks=[0,.25,.5,.75,1].map(f=>`<text x="4" y="${(235-f*190+4).toFixed(0)}">${(max*f).toFixed(1)} kW</text>`).join("");
    return `<div class="solar-chart-wrap"><svg class="chart solar-window-chart" viewBox="0 0 620 310" preserveAspectRatio="none" role="group" aria-label="Consumo em barras de quinze minutos; produção efetiva, prevista e potencial em linhas. Previsão do Engine em intervalos de quinze minutos."><path class="chart-grid" d="M45 45H600 M45 92H600 M45 140H600 M45 187H600 M45 235H600"/><g class="chart-label solar-y-axis">${yTicks}</g><g>${bars(loadHistoryBars)}${bars(loadForecastBars)}</g>${actualLine?`<path d="${actualLine}" fill="none" stroke="#79bce8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:''}${forecastLine?`<path d="${forecastLine}" fill="none" stroke="#79bce8" stroke-width="3" stroke-dasharray="3 6" stroke-linecap="round" stroke-linejoin="round"/>`:''}${historicalPotential.length?`<path d="${path(historicalPotential)}" fill="none" stroke="#dcc99c" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:''}${futurePotential.length?`<path d="${path(futurePotential.length&&historicalPotential.length?[historicalPotential.at(-1),...futurePotential]:futurePotential)}" fill="none" stroke="#dcc99c" stroke-width="3" stroke-dasharray="3 6" stroke-linecap="round" stroke-linejoin="round"/>`:''}<line class="solar-chart-selection" x1="0" x2="0" y1="34" y2="240" visibility="hidden"/><g class="chart-label solar-x-axis"><text x="45" y="275">−3 h</text><text x="218" y="275">agora</text><text x="414" y="275">+3 h</text><text x="570" y="275">+6 h</text></g><g>${hitTargets.join('')}</g></svg><div class="solar-chart-tooltip" role="status" aria-live="polite" hidden></div></div><div class="solar-chart-legend"><span><i class="solar-legend-load"></i>Consumo</span><span><i class="solar-legend-pv"></i>Produção</span><span><i class="solar-legend-potential"></i>Produção potencial</span></div>${renderSolarDayBalance(projection)}`;
  }
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
function favoriteMeta(){try{return JSON.parse(localStorage.getItem("solarminer.home-favorite-meta.v1")||"{}")}catch{return {}}}
function saveFavoriteMeta(value){localStorage.setItem("solarminer.home-favorite-meta.v1",JSON.stringify(value))}
function addHomeFavoriteId(id){workspace.prefs.favoriteDeviceIds=addFavoriteId(workspace.prefs.favoriteDeviceIds,id);return workspace.prefs.favoriteDeviceIds;}
function equipmentIconType(device,kind=""){
  const identity=[device?.device_kind_override,device?.device_kind,device?.category,device?.product_name,device?.model,device?.name,kind].filter(Boolean).join(" ").toLowerCase();
  if(/charger|carregador|vehicle|ve[ií]culo|\bev\b/.test(identity))return "ev-charger";
  if(/3\s*p\s*\+?\s*n|3pn|four.?pole|4.?pole|4p\b|tripolar|tetrapolar|3.?phase/.test(identity))return "breaker-3pn";
  if(/breaker|circuit|disjuntor|circuito|\bdj\b/.test(identity))return "breaker";
  const declared=Array.isArray(device?.switch_channels)?device.switch_channels.length:0;
  const functions=Array.isArray(device?.functions)?device.functions:[];
  const channelCodes=new Set(functions.filter(item=>item&&/^(switch|switch_\d+|switch_all)$/i.test(String(item.code||""))&&["bool","boolean"].includes(String(item.type||"").toLowerCase())).map(item=>String(item.code).toLowerCase()));
  const count=Math.max(declared,[...channelCodes].filter(code=>/^switch_\d+$/.test(code)).length,channelCodes.has("switch")?1:0);
  if(count>=6)return "switch-six";
  if(count>=2)return "switch-double";
  if(/switch|relay|interruptor|rele|light|luz/.test(identity))return "switch-single";
  return "generic";
}
function equipmentIconSvg(device,kind=""){
  const type=equipmentIconType(device,kind),label=({"switch-single":"Interruptor simples","switch-double":"Interruptor duplo","switch-six":"Interruptor de seis canais",breaker:"Disjuntor","breaker-3pn":"Disjuntor 3P+N","ev-charger":"Carregador de veículo elétrico",generic:"Equipamento"})[type];
  const common=`class="device-type-icon ${type}" viewBox="0 0 48 48" role="img" aria-label="${label}" focusable="false"`;
  if(type==="switch-six")return `<svg ${common}><rect x="5" y="3" width="38" height="42" rx="7"/><g>${[0,1,2].map(row=>[0,1].map(col=>`<circle cx="17" cy="${14+row*11}" r="3.5"/><path d="M25 ${14+row*11}h6"/>`).join("")).join("")}</g></svg>`;
  if(type==="switch-double")return `<svg ${common}><rect x="7" y="4" width="34" height="40" rx="7"/><rect x="13" y="10" width="9" height="27" rx="4.5"/><rect x="26" y="10" width="9" height="27" rx="4.5"/><path d="M17.5 23v7m13-16v7"/></svg>`;
  if(type==="switch-single")return `<svg ${common}><rect x="8" y="3" width="32" height="42" rx="7"/><rect x="15" y="9" width="18" height="30" rx="9"/><path d="M24 17v8"/></svg>`;
  if(type==="breaker-3pn")return `<svg ${common}><rect x="4" y="7" width="40" height="34" rx="4"/><path d="M8 13h32M8 35h32"/><g>${[0,1,2,3].map(index=>`<rect x="${9+index*8}" y="17" width="6" height="14" rx="1.5"/><path d="M${12+index*8} 20v6"/>`).join("")}</g><text x="24" y="46" text-anchor="middle">3P+N</text></svg>`;
  if(type==="breaker")return `<svg ${common}><rect x="8" y="3" width="32" height="42" rx="4"/><path d="M12 9h24m-24 30h24"/><rect x="15" y="14" width="18" height="20" rx="2"/><path d="m19 29 10-10m-9 0h9v9"/></svg>`;
  if(type==="ev-charger")return `<svg ${common}><path d="M11 5h20a5 5 0 0 1 5 5v28H8V10a5 5 0 0 1 3-5Z"/><path d="M15 12h12v9H15zM22 22l-5 8h5l-1 6 6-9h-5l1-5Z"/><path d="M36 18h4v9a5 5 0 0 1-5 5m-3 5h5"/></svg>`;
  return `<svg ${common}><rect x="7" y="7" width="34" height="34" rx="8"/><path d="M15 24h18M24 15v18"/></svg>`;
}
const favoriteControlPending=new Set();
function tuyaDeviceSpecs(device){const sources=[device?.functions,device?.status_spec,device?.category_functions,device?.category_status_spec,device?.product_profile?.functions,device?.product_profile?.status_spec],rows=sources.flatMap(source=>Array.isArray(source)?source:[]),byCode=new Map();for(const row of rows)if(row&&typeof row.code==="string"&&!byCode.has(row.code))byCode.set(row.code,row);return [...byCode.values()];}
function tuyaSwitchCodes(device){
  if(tuyaIsEvCharger(device)){const category=String(device?.category||"").toLowerCase().replace(/[^a-z0-9]/g,"");if(category==="qccdz"){const declared=(Array.isArray(device?.functions)?device.functions:[]).filter(item=>item&&typeof item.code==="string"&&["bool","boolean"].includes(String(item.type||"").toLowerCase())&&/^switch(?:_1)?$/i.test(item.code)).map(item=>item.code);return [...new Set([...declared,device?.switch_code||"switch"])]}return (Array.isArray(device?.functions)?device.functions:[]).filter(item=>item&&typeof item.code==="string"&&["bool","boolean"].includes(String(item.type||"").toLowerCase())&&/(charge|charging|start.?charge|stop.?charge|charger)/i.test(`${item.code} ${item.name||""} ${item.desc||""}`)&&device.local_dps_map?.[item.code]).map(item=>item.code)}
  const switchCode=/^(?:switch(?:_all|_[1-9]\d*)?|switch_led|switch_usb[1-9]\d*)$/i;
  const fromSchema=(Array.isArray(device?.functions)?device.functions:[]).filter(item=>item&&typeof item.code==="string"&&switchCode.test(item.code)&&["bool","boolean"].includes(String(item.type||"").toLowerCase())).map(item=>item.code);
  const configured=(Array.isArray(device?.switch_channels)?device.switch_channels:[]).filter(code=>typeof code==="string"&&switchCode.test(code));
  const explicit=typeof device?.switch_code==="string"&&device.switch_code? [device.switch_code]:[];
  return [...new Set([...configured,...fromSchema,...explicit])];
}
function tuyaSwitchChannelCodes(device,codes=tuyaSwitchCodes(device)){
  return codes.filter(code=>/^switch_[1-9]\d*$/i.test(code)).sort((a,b)=>Number(a.match(/\d+/)?.[0])-Number(b.match(/\d+/)?.[0]));
}
function tuyaPrimarySwitchCode(device,codes=tuyaSwitchCodes(device)){
  if(tuyaSwitchChannelCodes(device,codes).length>1)return "switch_all";
  if(codes.includes("switch_all"))return "switch_all";
  if(codes.includes("switch")&&codes.some(code=>/^switch_\d+$/i.test(code)))return "switch";
  return device?.switch_code&&codes.includes(device.switch_code)?device.switch_code:codes.find(code=>/^switch(?:_\d+|_led|_usb\d+)?$/i.test(code))||codes[0]||"";
}
function tuyaSwitchState(device,reading,code,ignorePending=false){
  const pending=ignorePending?null:pendingTuyaSwitchStates.get(`${device?.device_id}::${code}`);if(pending)return pending.timedOut?undefined:pending.value;
  if(!Object.prototype.hasOwnProperty.call(device?.local_dps_map||{},code)&&(device?.dps_knowledge?.mapping_conflicts||[]).some(conflict=>(conflict?.codes||[]).includes(code)))return undefined;
  const status=Array.isArray(reading?.status)?reading.status:[];
  const directItem=status.find(item=>item?.code===code);
  const boolValue=value=>typeof value==="boolean"?value:typeof value==="number"&&(value===0||value===1)?Boolean(value):typeof value==="string"&&/^(true|false|0|1)$/i.test(value)?value.toLowerCase()==="true"||value==="1":undefined;
  const direct=boolValue(directItem?.value);
  if(typeof direct==="boolean")return direct;
  const spec=[...(device?.functions||[]),...(device?.status_spec||[])].find(item=>item?.code===code);
  const kgMatch=tuyaIsKgHybrid(device)&&String(code||"").match(/^switch_([1-6])$/i);
  const dpId=spec?tuyaSpecDpsId(device,spec):Number.isInteger(Number(device?.local_dps_map?.[code]))?Number(device.local_dps_map[code]):kgMatch?Number(kgMatch[1]):tuyaIsKgHybrid(device)&&code==="switch_all"?13:null;
  if(dpId!==null){const byId=boolValue(status.find(item=>Number(item?.dps_id??item?.dp_id)===dpId||item?.code===`dps_${dpId}`)?.value);if(typeof byId==="boolean")return byId;}
  if(code==="switch_all"){
    const values=tuyaSwitchChannelCodes(device).map(channel=>tuyaSwitchState(device,reading,channel)).filter(value=>typeof value==="boolean");
    return values.length?values.some(Boolean):undefined;
  }
  return undefined;
}
function tuyaSwitchCodeHasLocalMapping(device,code){
  if(device?.local_dps_map&&Object.prototype.hasOwnProperty.call(device.local_dps_map,code))return true;
  if((device?.dps_knowledge?.mapping_conflicts||[]).some(conflict=>(conflict?.codes||[]).includes(code)))return false;
  const spec=(device?.functions||[]).find(item=>item?.code===code);
  if(Number.isInteger(spec?.dp_id)||Number.isInteger(spec?.dpId))return true;
  if(tuyaIsKgHybrid(device)&&code==="switch_all")return true;
  if(tuyaIsKgHybrid(device)&&/^switch_[1-6]$/.test(code))return true;
  const multi=(Number(device?.channel_count)>1||device?.device_kind==="multi_switch"||(device?.switch_channels||[]).length>1||(device?.functions||[]).filter(item=>/^switch_[1-9]\d*$/i.test(String(item?.code||""))&&["bool","boolean"].includes(String(item?.type||"").toLowerCase())).length>1);
  return !multi&&code==="switch";
}
function tuyaIsKgHybrid(device){
  const category=String(device?.category||"").toLowerCase().replace(/[^a-z0-9]/g,"");
  const channels=tuyaSwitchChannelCodes(device);
  return (category==="kg"||device?.dps_knowledge?.preset_id==="six_channel_hybrid")&&channels.length>=6;
}
function tuyaSpecDpsId(device,spec){
  const mapped=device?.local_dps_map?.[spec?.code];
  if(Number.isInteger(Number(mapped))&&Number(mapped)>0)return Number(mapped);
  if((device?.dps_knowledge?.mapping_conflicts||[]).some(conflict=>(conflict?.codes||[]).includes(spec?.code)))return null;
  const direct=spec?.dp_id??spec?.dpId;
  if(Number.isInteger(Number(direct))&&Number(direct)>0)return Number(direct);
  const catalog=[...(device?.product_profile?.dps||[]),...(device?.dps_knowledge?.dps||[])];
  const entry=catalog.find(item=>item?.function_code===spec?.code||item?.semantic_code===spec?.code);
  const catalogId=Number(entry?.dps_id);
  return Number.isInteger(catalogId)&&catalogId>0?catalogId:null;
}
function tuyaKgPairModeSpecs(device){
  if(!tuyaIsKgHybrid(device))return [];
  return [113,114,115].map((dpId,index)=>{
    const spec=(device.functions||[]).find(item=>tuyaSpecDpsId(device,item)===dpId);
    let values=spec?.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}
    const range=Array.isArray(values?.range)?values.range:[];
    const supported=Boolean(spec&&String(spec.type||"").toLowerCase()==="enum"&&range.includes("switch")&&range.includes("curtain")&&tuyaSpecDpsId(device,spec)===dpId);
    const status=state.tuyaReadings?.find(item=>item.device_id===device.device_id)?.status||[];
    const current=status.find(item=>item?.code===spec?.code||Number(item?.dps_id??item?.dp_id)===dpId||item?.code===`dps_${dpId}`)?.value;
    return {pair:index+1,dpId,code:spec?.code||"",current,range,supported};
  });
}
async function setTuyaSwitchGroup(device,desired){
  const channels=tuyaSwitchChannelCodes(device),masterMapped=tuyaSwitchCodeHasLocalMapping(device,"switch_all");
  if(masterMapped){
    const result=await controlGatewayTuyaSwitch(device.device_id,desired,"switch_all");
    return {results:[result],codes:["switch_all"]};
  }
  if(channels.length<2)throw new Error("O comando geral não tem mapeamento local confirmado.");
  const missing=channels.filter(code=>!tuyaSwitchCodeHasLocalMapping(device,code));
  if(missing.length)throw new Error(`Falta mapear os DPS locais de ${missing.join(", ")}.`);
  const results=[];
  for(const code of channels)results.push(await controlGatewayTuyaSwitch(device.device_id,desired,code));
  return {results,codes:channels};
}
async function sendTuyaSwitchCommand(device,code,desired){
  const pendingCodes=code==="switch_all"&&tuyaSwitchChannelCodes(device).length>1&&!tuyaSwitchCodeHasLocalMapping(device,"switch_all")?tuyaSwitchChannelCodes(device):[code];
  const requestedAt=Date.now();
  recentTuyaSwitchCommands.set(device.device_id,requestedAt+5_000);
  for(const pendingCode of pendingCodes)pendingTuyaSwitchStates.set(`${device.device_id}::${pendingCode}`,{deviceId:device.device_id,code:pendingCode,value:desired,requestedAt});
  updateVisibleTuyaCard(device.device_id);updateOpenTuyaDeviceDialog(device.device_id);
  try{const started=performance.now(),result=code==="switch_all"?await setTuyaSwitchGroup(device,desired):{results:[await controlGatewayTuyaSwitch(device.device_id,desired,code)],codes:[code]},deviceCommandMs=result.results?.reduce((sum,item)=>sum+(Number(item?.device_command_latency_ms)||0),0),commandRoundTripMs=performance.now()-started,statusNode=document.querySelector(`dialog[open][data-tuya-device-id="${CSS.escape(device.device_id)}"] [data-tuya-quick-status],dialog[open][data-tuya-device-id="${CSS.escape(device.device_id)}"] [data-tuya-detail-lan-status]`)||document.querySelector(`[data-favorite-status="${CSS.escape(device.device_id)}"]`);refreshTuyaDeviceAfterAction(device.device_id,statusNode,requestedAt,commandRoundTripMs,"Ordem enviada",deviceCommandMs);confirmTuyaCommandInBackground(device,requestedAt,pendingCodes,desired,commandRoundTripMs,deviceCommandMs);return result;}
  catch(error){
    const transportUncertain=error instanceof TypeError||/load failed|failed to fetch|networkerror/i.test(String(error?.message||""));
    if(!transportUncertain)for(const pendingCode of pendingCodes)pendingTuyaSwitchStates.delete(`${device.device_id}::${pendingCode}`);
    updateVisibleTuyaCard(device.device_id);updateOpenTuyaDeviceDialog(device.device_id);
    if(transportUncertain){const uncertain=new Error("O Gateway não devolveu resposta; a ordem pode ter chegado. Aguardo a próxima leitura LAN para confirmar.");uncertain.outcomeUnknown=true;throw uncertain;}
    throw error;
  }
}
function favoriteDeviceCards() {
  const canUsePwa=sessionInfo().authenticated,canControl=canUsePwa&&sessionInfo().user?.role==="owner";
  if(state.mode!=="LIVE")return `<div class="favorite-device-grid"><p class="field-note">Os dispositivos favoritos aparecem aqui quando o Gateway está ligado.</p></div>`;
  const tuya=(state.tuyaDevices||[]).map(raw=>{const device=tuyaDeviceWithPidMap(raw);return {id:device.device_id,name:device.name,kind:"tuya",device};});
  const registered=(state.equipment||[]).map(device=>({id:device.id,name:device.name,kind:"equipment",device}));
  const shelly=(state.shellyDevices||[]).filter(device=>!String(device.device_id||"").startsWith("shelly-blu:")).map(device=>({id:device.device_id,name:device.name||device.model||"Shelly",kind:"shelly",device}));
  const all=[...registered,...tuya,...shelly].filter((item,index,items)=>items.findIndex(other=>other.id===item.id)===index);
  const favorites=Array.isArray(workspace.prefs.favoriteDeviceIds)?workspace.prefs.favoriteDeviceIds:[];
  // Keep favorites whose inventory is temporarily unavailable; the Gateway list can load after this render.
  workspace.prefs.favoriteDeviceIds=normalizeFavoriteIds(favorites);
  const meta=favoriteMeta(),readings=state.tuyaReadings||[];
  const allById=new Map(all.map(item=>[item.id,item]));
  const rows=workspace.prefs.favoriteDeviceIds.map(id=>allById.get(id)).filter(Boolean).map(item=>{
    const {device,kind,id}=item,details=meta[id]||{};
    if(kind==="equipment")return {id,kind,device,details,reading:preferredGatewayReading(device)};
    if(kind==="shelly")return {id,kind,device,details,reading:device};
    const status=readings.find(entry=>entry.device_id===id),values=status?.status||[];
    let codes=tuyaSwitchCodes(device);
    if((device.device_kind_override||device.device_kind)==="breaker")codes=[device.switch_code||codes.find(code=>code==="switch"||code==="switch_1")||codes[0]].filter(Boolean);
    const channels=codes.map(code=>{const pending=pendingTuyaSwitchStates.get(`${id}::${code}`);return {code,value:pending?.timedOut?undefined:pending?.value??tuyaSwitchState(device,status,code),label:device.channel_labels?.[code]||device.capability_labels?.[code]||code};});
    if(tuyaSwitchChannelCodes(device,codes).length>1&&!channels.some(channel=>channel.code==="switch_all"))channels.push({code:"switch_all",value:tuyaSwitchState(device,status,"switch_all"),label:"Todos"});
    const level=values.find(entry=>entry.code===device.level_code)?.value,isLevel=Boolean(device.level_code);
    const percent=isLevel&&Number.isFinite(Number(level))?Math.max(0,Math.min(100,Math.round((Number(level)-Number(device.level_min??0))/(Number(device.level_max??100)-Number(device.level_min??0))*100))):null;
    return {id,kind,device,details,status,codes,channels,isLevel,percent};
  });
  const powerGlyph=`<svg viewBox="0 0 28 28" aria-hidden="true" focusable="false"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg>`;
    const stateSymbol=(id,channel,enabled)=>{const pending=pendingTuyaSwitchStates.get(`${id}::${channel.code}`),pendingLabel=pending?.timedOut?"sem confirmação; estado incerto":"ordem enviada; a confirmar pela LAN";return `<button type="button" class="favorite-state-symbol ${channel.value===true?"on":channel.value===false?"off":"unknown"}${pending?" pending":""}" data-favorite-toggle="${esc(id)}" data-favorite-code="${esc(channel.code)}" data-reference-power aria-pressed="${channel.value===true}" aria-label="${esc(channel.label)}: ${pending?pendingLabel:channel.value===true?"ligado":channel.value===false?"desligado":"estado por confirmar no varrimento"}" title="${pending?pendingLabel:channel.value===undefined?"A aguardar estado do varrimento":esc(channel.label)}" ${!enabled||favoriteControlPending.has(id)?"disabled":""}>${powerGlyph}</button>`;};
  return `<div class="favorite-manage"><span>Podes adicionar todos os dispositivos registados no Gateway; não há limite de favoritos. Mantém premido e arrasta para mudar a posição.</span>${canUsePwa?`<button type="button" class="favorite-add-button" id="home-favorite-plus" aria-label="Adicionar dispositivo ou favorito" title="Adicionar">＋</button>`:""}</div><div class="favorite-device-grid">${rows.map(({id,kind,device,details,status,codes,channels,isLevel,percent,reading})=>{
    const label=details.label||device.name,place=[details.room||device.room,details.floor||device.floor].filter(Boolean).join(" · ")||device.logical_location||"Localização por definir";
    const primaryCode=kind==="tuya"?tuyaPrimarySwitchCode(device,codes):"",primaryChannel=channels.find(channel=>channel.code===primaryCode),channelButtons=kind==="tuya"&&primaryChannel?stateSymbol(id,primaryChannel,canControl):"";
    const shellyTarget=kind==="shelly"?(device.components||[]).find(item=>["switch","relay","light","rgb","rgbw","cct","color"].includes(item.component)):null,shellyOn=shellyTarget?shellyComponentState(shellyTarget):undefined,shellyChannel=Number(shellyTarget?.id)||0,shellyLight=shellyTarget&&["light","rgb","rgbw","cct","color"].includes(shellyTarget.component),shellyToggle=shellyTarget?`<button type="button" class="favorite-state-symbol ${shellyOn===true?"on":shellyOn===false?"off":"unknown"}" ${shellyLight?`data-shelly-light-on="${esc(id)}" data-shelly-component="${esc(shellyTarget.component)}"`:`data-shelly-switch="${esc(id)}"`} data-shelly-channel="${shellyChannel}" data-shelly-target="${shellyOn===true?"off":"on"}" aria-pressed="${shellyOn===true}" aria-label="${shellyOn===true?"Desligar":"Ligar"} ${esc(label)}" ${!canControl||device.connection_state!=="connected"?"disabled":""}>${powerGlyph}</button>`:"";
    return `<article class="favorite-device" data-favorite-device="${esc(id)}" data-device-kind="${kind}" aria-label="${esc(label)}" title="Toque para abrir; usa Opções para ver os controlos"><span class="favorite-device-icon" aria-hidden="true">${equipmentIconSvg(device,kind)}</span><div class="favorite-device-info"><strong class="favorite-device-name">${esc(label)}</strong><span>${esc(place)}</span></div><div class="favorite-device-actions">${kind==="tuya"?(channelButtons||`<span class="favorite-state-symbol unknown" aria-label="Estado indisponível">${powerGlyph}</span>`):kind==="shelly"?(shellyToggle||`<span class="favorite-state-symbol unknown" aria-label="Estado indisponível">${powerGlyph}</span>`):`<span class="favorite-state-symbol unknown" title="${esc(reading?.field||"Estado não disponível")}">${powerGlyph}</span>`}${kind==="tuya"?`<button type="button" class="favorite-expand" data-favorite-expand="${esc(id)}" aria-label="Opções de ${esc(label)}" title="Opções">⌄</button>`:kind==="shelly"?`<button type="button" class="favorite-expand" data-shelly-expand="${esc(id)}" aria-label="Opções de ${esc(label)}" title="Opções">⌄</button>`:""}</div></article>`;
  }).join("")}${!rows.length?`<p class="field-note">Ainda não há dispositivos favoritos. Usa ＋ para escolher um equipamento registado no Gateway.</p>`:""}</div>`;
}
function referenceDimmerGroupAction({deviceId,isOn,provider="tuya",enabled=true}){
  const icon='<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0M14 2.4v10.2"/></svg>';
  const buttonAttrs=provider==="shelly"
    ?`data-shelly-group-toggle="${esc(deviceId)}" data-shelly-target="${isOn?"off":"on"}"`
    :`data-favorite-toggle="${esc(deviceId)}" data-favorite-code="switch_all"`;
  const label=isOn?"Desligar tudo":"Ligar tudo";
  return `<div class="reference-group-action"><button type="button" class="reference-power reference-power-group ${isOn?"on":"off"}" ${buttonAttrs} data-reference-power aria-pressed="${isOn}" aria-label="${label}" ${enabled?"":"disabled"}>${icon}</button><strong>${label}</strong></div>`;
}
function openTuyaReferenceDeviceCard(deviceId){
  const raw=state.tuyaDevices.find(item=>item.device_id===deviceId),device=tuyaDeviceWithPidMap(raw);if(!device)return;
  const reading=state.tuyaReadings.find(item=>item.device_id===deviceId)||{status:device.current_status||[],connection_state:"stored_status"};
  const status=Array.isArray(reading.status)?reading.status:[],metrics=(()=>{try{return tuyaSimpleReadings(device,reading)}catch{return []}})();
  const extraSwitchCodes=tuyaDeviceSpecs(device).filter(item=>/^switch_[1-9]\d*$/i.test(String(item?.code||""))&&["bool","boolean"].includes(String(item?.type||"").toLowerCase())).map(item=>item.code),switchCodes=[...new Set([...tuyaSwitchCodes(device),...extraSwitchCodes])],switches=tuyaSwitchChannelCodes(device,switchCodes),channels=(switches.length?switches:switchCodes.filter(code=>code!=="switch_all")).map((code,index)=>({code,index,value:tuyaSwitchState(device,reading,code),label:device.channel_labels?.[code]||device.capability_labels?.[code]||`Canal ${index+1}`}));
  const brightnessSpecs=tuyaDeviceSpecs(device).filter(item=>/bright|brightness|dimmer|level/i.test(`${item.code||""} ${item.name||""}`));
  const brightnessForChannel=channel=>{
    const suffix=String(channel.index+1),specific=brightnessSpecs.find(item=>new RegExp(`(?:_|-)${suffix}$`).test(String(item.code||"")));
    const generic=brightnessSpecs.find(item=>!/[_-]\d+$/.test(String(item.code||"")));
    const ordered=channels.length>1&&brightnessSpecs.length===channels.length?[...brightnessSpecs].sort((a,b)=>{
      const ai=Number(String(a.code||"").match(/[_-](\d+)$/)?.[1])||1,bi=Number(String(b.code||"").match(/[_-](\d+)$/)?.[1])||1;
      return ai-bi;
    })[channel.index]:null;
    const single=channels.length<=1?generic:null;
    const fallback=device.level_code&&channels.length<=1?{code:device.level_code,values:{min:device.level_min??0,max:device.level_max??100}}:null;
    return specific||single||ordered||fallback;
  };
  const multi=channels.length>1,isBreaker=tuyaIsBreaker(device),power=metrics.find(item=>item.label==="Potência");
  const brightnessReading=spec=>{
    if(!spec)return null;
    const value=status.find(item=>item.code===spec.code)?.value;
    let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}
    const min=Number(values.min??device.level_min??0),max=Number(values.max??device.level_max??100),scale=Number(values.scale||0),numeric=Number(value);
    if(value===undefined||value===null||!Number.isFinite(numeric)||max<=min)return null;
    const normalized=numeric/(10**scale);
    return Math.max(0,Math.min(100,Math.round((normalized-min)/(max-min)*100)));
  };
  const glyphs={bell:'<path d="M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0"/>',chart:'<path d="M4 4v16h16M7 15l4-4 3 3 5-6"/>',book:'<path d="M7 3h11a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7zM7 3v18M4 8h3M4 12h3M4 16h3"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',moon:'<path d="M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z"/>',link:'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',web:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',auto:'<circle cx="9" cy="9" r="3"/><circle cx="9" cy="9" r="6" stroke-dasharray="2.4 2.4"/><circle cx="16.5" cy="16.5" r="2"/><circle cx="16.5" cy="16.5" r="4" stroke-dasharray="2 2"/>',share:'<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6m-7.6 6 7.6 3.6"/>',settings:'<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.2 2-2 2-2-1.2-.2.1a7.7 7.7 0 0 1-1.5.6l-.5 2.3h-2.8l-.5-2.3a7.7 7.7 0 0 1-1.5-.6l-.2-.1-2 1.2-2-2 1.2-2-.1-.2a7.7 7.7 0 0 1-.6-1.5L2 13.8V11l2.3-.5a7.7 7.7 0 0 1 .6-1.5l.1-.2-1.2-2 2-2 2 1.2.2-.1a7.7 7.7 0 0 1 1.5-.6L11 3h2.8l.5 2.3a7.7 7.7 0 0 1 1.5.6l.2.1 2-1.2 2 2-1.2 2 .1.2a7.7 7.7 0 0 1 .6 1.5l2.3.5v2.8l-2.3.5a7.7 7.7 0 0 1-.6 1.5Z"/>'};
  const menuOrder=deviceCardPopupMenuOrder(deviceCardTemplate("tuya",device.product_id)),rail=[['bell','Notificações','notifications'],['chart','Gráficos','charts'],['book','Registo','log'],['clock','Horário','timer'],['cal','Calendário','calendar'],['moon','Modo noite','night'],['link','Ligações','links'],['web','Web','web'],['auto','Automações','automations'],['share','Partilha','share'],['settings','Definições','settings']].sort((a,b)=>menuOrder.indexOf(a[2])-menuOrder.indexOf(b[2])).map(([key,label])=>`<button type="button" data-reference-menu="${key}" aria-label="${label}" title="${label}"><svg viewBox="0 0 24 24" aria-hidden="true">${glyphs[key]}</svg></button>`).join("");
  const statusLabel=tuyaDeviceState(device,reading),admin=sessionInfo().user?.role==="owner",powerIcon='<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0M14 2.4v10.2"/></svg>';
  const channelButton=channel=>`<button type="button" class="reference-power ${isBreaker?"reference-power-large":""} ${channel.value===true?"on":"off"}" data-favorite-toggle="${esc(deviceId)}" data-favorite-code="${esc(channel.code)}" data-reference-power aria-pressed="${channel.value===true}" aria-label="${channel.value===true?"Desligar":"Ligar"} ${esc(channel.label)}" ${!admin||!tuyaSwitchCodeHasLocalMapping(device,channel.code)||typeof channel.value!=="boolean"?"disabled":""}>${powerIcon}</button>`;
  const isDimmable=channels.some(channel=>Boolean(brightnessForChannel(channel)));
  const channelMarkup=channel=>{const dimmer=brightnessForChannel(channel),brightnessValue=brightnessReading(dimmer),hasMapping=Boolean(dimmer&&Number.isInteger(tuyaSpecDpsId(device,dimmer)));return `<section class="reference-channel ${channel.value===true?"is-on":"is-off"}">${dimmer?`<label class="reference-vertical-slider ${channel.value===true?"":"is-off"}"><input type="range" min="0" max="100" value="${brightnessValue??0}" data-reference-brightness="${esc(dimmer.code)}" data-reference-channel="${channel.index}" aria-label="Luminosidade ${esc(channel.label)}" ${!admin||!hasMapping||channel.value!==true||brightnessValue===null?"disabled":""}><span class="reference-slider-fill" style="--level:${brightnessValue??0}%"></span></label><span class="reference-channel-brightness">Luminosidade <strong>${brightnessValue===null?"Sem leitura":`${brightnessValue}%`}</strong></span>`:""}${channelButton(channel)}<strong class="reference-channel-name">${esc(channel.label)}</strong>${!dimmer&&multi?`<span class="reference-channel-state" data-reference-channel-state="${esc(channel.code)}">${channel.value===true?"Ligado":channel.value===false?"Desligado":"Sem leitura"}</span>`:""}</section>`};
  const isOn=channels.some(channel=>channel.value===true),mainSwitch=channels[0],mainControl=isDimmable?`<div class="reference-dimmer-layout ${multi?"is-multi":""}">${channels.map(channelMarkup).join("")}</div>`:multi?`<div class="reference-channel-grid ${channels.length===2?"is-two":""}">${channels.map(channelMarkup).join("")}</div>`:mainSwitch?`<section class="reference-single-control"><button type="button" class="reference-power reference-power-large ${mainSwitch.value===true?"on":"off"}" data-favorite-toggle="${esc(deviceId)}" data-favorite-code="${esc(mainSwitch.code)}" data-reference-power aria-pressed="${mainSwitch.value===true}" aria-label="${mainSwitch.value===true?"Desligar":"Ligar"}" ${!admin||!tuyaSwitchCodeHasLocalMapping(device,mainSwitch.code)||typeof mainSwitch.value!=="boolean"?"disabled":""}>${powerIcon}</button><strong data-reference-main-state>${mainSwitch.value===true?"Ligado":mainSwitch.value===false?"Desligado":"Sem leitura"}</strong><small>Toque para alternar</small></section>`:`<p class="reference-no-control">Sem controlo ON/OFF declarado.</p>`;
  const metricLabels=["Tensão","Corrente","Potência","Consumo diário"];
  const readings=metricLabels.map(label=>{const metric=metrics.find(item=>item.label===label);const value=metric&&metric.value!==null&&metric.value!==undefined&&metric.value!==""?metric.value:"Sem leitura";return `<div class="reference-metric"><small>${label}</small><strong data-reference-metric="${label}">${esc(value)}</strong></div>`}).join("");
  const groupAction=multi?referenceDimmerGroupAction({deviceId,isOn,provider:"tuya",enabled:admin&&channels.every(channel=>tuyaSwitchCodeHasLocalMapping(device,channel.code))}):"";
  const dialog=document.createElement("dialog");dialog.className="settings-dialog reference-smart-card-dialog";dialog.dataset.tuyaDeviceId=deviceId;
  dialog.innerHTML=`<div class="reference-card"><nav class="reference-rail" aria-label="Opções do dispositivo">${rail}</nav><main class="reference-main"><header class="reference-heading"><div><p class="eyebrow">${isBreaker?"DISJUNTOR":"DISPOSITIVO"} · ${esc(device.category||"TUYA")}</p><h2>${esc(device.name||"Dispositivo")}</h2></div><button type="button" class="reference-edit-name" aria-label="Editar nome" title="Editar nome">✎</button><button type="button" class="reference-close" aria-label="Fechar">×</button></header><p class="reference-subtitle">Controlos principais · ${esc(device.room||device.floor||"Localização por definir")}</p><div class="reference-pills"><span>⚡ <b data-reference-power-watts>${power?esc(power.value):"Sem leitura"}</b></span>${isDimmable?`<span>◐ <b data-reference-brightness-summary>${esc(brightnessReading(brightnessForChannel(channels[0]||{index:0}))===null?"Sem leitura":`${brightnessReading(brightnessForChannel(channels[0]||{index:0}))}%`)}</b></span>`:""}</div>${isBreaker&&!isDimmable?`<div class="reference-breaker-state">${channelButton(mainSwitch||{code:"",value:undefined,label:"Interruptor"})}<strong data-reference-main-state>${mainSwitch?.value===true?"Ligado":mainSwitch?.value===false?"Desligado":"Sem leitura"}</strong></div><div class="reference-metrics">${readings}</div>`:mainControl}${groupAction}<p class="reference-status" data-reference-status>${esc(statusLabel)} · ${esc(tuyaConnectionSummary(reading))}</p></main></div>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector(".reference-close").addEventListener("click",()=>dialog.close());
  dialog.querySelector(".reference-edit-name").addEventListener("click",()=>{dialog.close();openTuyaDeviceEditor(device);});
  dialog.querySelectorAll("[data-reference-menu]").forEach(button=>button.addEventListener("click",()=>{const selected=button.dataset.referenceMenu;dialog.querySelectorAll("[data-reference-menu]").forEach(item=>item.classList.toggle("active",item===button));if(selected==="settings"&&admin){dialog.close();openTuyaDeviceSettings(device);return;}const note=dialog.querySelector("[data-reference-status]");note.textContent=selected==="settings"?"Definições disponíveis para o Owner autenticado.":`${button.getAttribute("aria-label")} · sem conteúdo disponível para este equipamento.`;}));
  dialog.querySelectorAll("[data-reference-brightness]").forEach(input=>{input.addEventListener("input",()=>{input.parentElement.style.setProperty("--level",`${input.value}%`);const channel=input.closest(".reference-channel"),caption=channel?.querySelector(".reference-channel-brightness strong");if(caption)caption.textContent=`${input.value}%`;if(input.dataset.referenceChannel==="0"){const pill=dialog.querySelector(".reference-pills span:nth-child(2) b");if(pill)pill.textContent=`${input.value}%`;}});input.addEventListener("change",async()=>{const spec=brightnessSpecs.find(item=>item.code===input.dataset.referenceBrightness)||{code:input.dataset.referenceBrightness,values:{min:device.level_min??0,max:device.level_max??100}},bounds=(()=>{let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}return {min:Number(values.min??device.level_min??0),max:Number(values.max??device.level_max??100),scale:Number(values.scale||0),step:Number(values.step||1)}})(),raw=bounds.min+(Number(input.value)/100)*(bounds.max-bounds.min),encoded=Math.round(raw/(10**bounds.scale)/bounds.step)*bounds.step;input.disabled=true;dialog.querySelector("[data-reference-status]").textContent="A enviar nível de brilho…";try{await sendGatewayTuyaSetting(deviceId,input.dataset.referenceBrightness,encoded);dialog.querySelector("[data-reference-status]").textContent="Nível enviado; a leitura LAN confirmará o valor.";}catch(error){dialog.querySelector("[data-reference-status]").textContent=`Falha ao ajustar o brilho: ${error.message}`;}finally{input.disabled=false;}});});
  dialog.showModal();
}
function openFavoriteDeviceDetails(deviceId,kind){
  if(kind==="shelly"){openShellyDeviceDetails(deviceId);return;}
  const isTuya=kind==="tuya",rawDevice=isTuya?state.tuyaDevices.find(item=>item.device_id===deviceId):state.equipment.find(item=>item.id===deviceId),device=isTuya?tuyaDeviceWithPidMap(rawDevice):rawDevice;
  if(!device)return;
  if(isTuya){openTuyaReferenceDeviceCard(deviceId);return;}
  const dialog=document.createElement("dialog");dialog.className="settings-dialog favorite-device-details";if(isTuya)dialog.dataset.tuyaDeviceId=deviceId;
  const row=(label,value)=>`<div class="detail-item"><small>${esc(label)}</small><strong>${esc(value==null||value===""?"—":String(value))}</strong></div>`;
  let details="";const breaker=isTuya&&tuyaIsBreaker(device);
  if(isTuya){
    const live=state.tuyaReadings.find(item=>item.device_id===deviceId)||{status:device.current_status||[],connection_state:"stored_status",reason:device.local_control_state==="unavailable"?"tuya_connection_failed":undefined},status=Array.isArray(live?.status)&&live.status.length?live.status:(Array.isArray(device.current_status)?device.current_status:[]);
    const metrics=(()=>{try{return tuyaSimpleReadings(device,live)}catch(error){console.warn("Could not map optional Tuya detail metrics",device.device_id,error);return []}})(),knowledge=device.dps_knowledge&&typeof device.dps_knowledge==="object"?device.dps_knowledge:{},knowledgeRows=(Array.isArray(knowledge.dps)?knowledge.dps:[]).filter(item=>item&&typeof item==="object").map(item=>row(`DPS ${item.dps_id??"—"} · ${item.display_name||"DPS"}`,`${item.semantic_code||""} · ${item.confidence||"UNKNOWN"}${item.raw_value!==undefined?` · valor bruto ${JSON.stringify(item.raw_value)}`:""}`)).join("");
    const fault=tuyaFault(device,live),breakerCode=breaker?tuyaPrimarySwitchCode(device,tuyaSwitchCodes(device)):"",breakerState=breakerCode?tuyaSwitchState(device,live,breakerCode):undefined;
    const linkLabel=live?.connection_state==="lan_reachable"?`Host respondeu na LAN · ${Math.round(Number(live.latency_ms)||0)} ms · teste sem leitura DPS`:live?.connection_state==="local_responded"?`Leitura DPS local · ${Number(live.success_count)||1}/${Number(live.rounds)||1} respostas · média ${Math.round(Number(live.latency_ms)||0)} ms`:device.online===true?"Tuya Cloud online · sem confirmação LAN":"Sem confirmação LAN";
    const specs=Array.isArray(device.status_spec)?device.status_spec:[],declaredDps=specs.map(spec=>{const entry=status.find(item=>item?.code===spec?.code);let value=entry?.value;if(value&&typeof value==="object")value=JSON.stringify(value);return row(`${tuyaFriendlyCapabilityLabel(spec,device)} · ${spec?.code||"DPS"}`,entry?value:"Sem leitura LAN atual");}),extraDps=status.filter(entry=>!specs.some(spec=>spec?.code===entry?.code)).map(entry=>{let value=entry?.value;if(value&&typeof value==="object")value=JSON.stringify(value);return row(`${entry?.code||"DPS"} · valor recebido`,value);}),dps=[...declaredDps,...extraDps].join("");
    const breakerMetricFallback=tuyaBreakerMetricFallback(device,live),breakerMetrics=["Tensão","Corrente","Potência","Consumo diário"].map(label=>{const metric=metrics.find(item=>item.label===label);return `<div class="detail-item"><small>${label}</small><strong data-breaker-live-metric="${label}">${esc(metric?.value||breakerMetricFallback)}</strong></div>`}).join("");
    const breakerToggle=breakerCode?`<button type="button" class="favorite-state-symbol breaker-detail-power ${breakerState===true?"on":breakerState===false?"off":"unknown"}" data-breaker-detail-toggle="${esc(breakerCode)}" aria-pressed="${breakerState===true}" aria-label="${breakerState===true?"Desligar":breakerState===false?"Ligar":"Estado por confirmar"}" ${breakerState===undefined||!tuyaSwitchCodeHasLocalMapping(device,breakerCode)||sessionInfo().user?.role!=="owner"?"disabled":""}><svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg></button>`:`<p class="empty-state">O esquema não declarou um controlo ON/OFF mapeado.</p>`;
    details=breaker?`<section class="breaker-detail-view"><div class="breaker-detail-state">${breakerToggle}<strong data-breaker-live-state>${breakerState===true?"Ligado":breakerState===false?"Desligado":"Estado por confirmar"}</strong></div><div class="device-detail-grid breaker-detail-metrics" data-breaker-live-metrics>${breakerMetrics}</div><p class="field-note">As leituras mostram os valores recebidos pela LAN.</p><div class="breaker-detail-settings"><button type="button" class="button secondary" data-breaker-detail-settings>Definições</button></div></section>`:`<div class="device-detail-grid">${row("Estado",fault?fault.label:tuyaDeviceState(device,live))}${row("Ligação",linkLabel)}${metrics.map(metric=>row(metric.label,metric.value)).join("")}</div>${live?.reason?`<p class="empty-state">${esc(tuyaLanReasonText(live.reason))}</p>`:""}`;
  }else{
    const readings=(device.readings||[]).map(value=>row(value.evidence?.label||value.field,`${formatReading(value).value} ${value.unit||""}`)).join("");
    details=`<div class="device-detail-grid">${row("Categoria",device.category)}${row("Fabricante",device.manufacturer)}${row("Modelo",device.model)}${row("Ligação",device.connection_state||device.status)}${row("Última comunicação",timeLabel(device.last_communication_at))}</div><h3>Leituras disponíveis</h3>${readings?`<div class="device-detail-grid telemetry-grid">${readings}</div>`:`<p class="empty-state">Ainda não há leituras disponíveis para este dispositivo.</p>`}`;
  }
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">FAVORITO · INFORMAÇÃO DO DISPOSITIVO</p><h2>${esc(device.name||deviceId)}</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></div>${details}${isTuya?`<p class="connection-result" data-tuya-detail-lan-status role="status" aria-live="polite"></p>`:""}<div class="dialog-actions">${isTuya&&sessionInfo().user?.role==="owner"?(breaker?"":`<button class="button secondary" type="button" data-tuya-detail-read>Testar resposta LAN</button><button class="button secondary" type="button" data-tuya-detail-read-status>Ler estado DPS local</button><button class="button secondary" type="button" data-tuya-detail-settings>Settings</button><button class="button secondary" type="button" data-tuya-detail-connection>IP, MAC e DPS</button>`):""}${isTuya&&breaker&&sessionInfo().user?.role==="owner"?"":"<button class=\"button secondary\" value=\"close\">Fechar</button>"}</div></form>`;
  if(isTuya){dialog.querySelector("[data-tuya-detail-settings],[data-breaker-detail-settings]")?.addEventListener("click",()=>{dialog.close();openTuyaDeviceSettings(device);});dialog.querySelector("[data-tuya-detail-connection]")?.addEventListener("click",()=>{dialog.close();openTuyaDeviceEditor(device);});}
  if(isTuya&&breaker)dialog.querySelector("[data-breaker-detail-toggle]")?.addEventListener("click",async event=>{const button=event.currentTarget,statusNode=dialog.querySelector("[data-tuya-detail-lan-status]"),code=button.dataset.breakerDetailToggle,current=tuyaSwitchState(device,state.tuyaReadings.find(item=>item.device_id===deviceId),code);button.disabled=true;try{if(typeof current!=="boolean"||!tuyaSwitchCodeHasLocalMapping(device,code))throw new Error("Ainda não existe um estado e mapeamento local confirmados para este interruptor.");await sendTuyaSwitchCommand(device,code,!current);statusNode.textContent="Ordem enviada; o estado será atualizado pela leitura periódica independente.";}catch(error){statusNode.textContent=error.outcomeUnknown?error.message:`Falha ao enviar a ordem: ${error.message}`;}finally{button.disabled=false;}});
  if(isTuya)dialog.querySelector("[data-tuya-detail-read-status]")?.addEventListener("click",async event=>{const button=event.currentTarget,statusNode=dialog.querySelector("[data-tuya-detail-lan-status]");button.disabled=true;statusNode.textContent="A consultar os estados DPS pela ligação local…";try{const {reading,result}=await testTuyaLanDevice(deviceId);state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==deviceId),reading];render();const count=Array.isArray(reading.status)?reading.status.length:0;statusNode.textContent=reading.connection_state==="local_responded"?`Leitura DPS local recebida: ${count} estados; ${Number(result.average_latency_ms)||0} ms de média. Sem consulta à cloud.`:`A ligação ou leitura DPS local falhou: ${tuyaLanReasonText(reading.reason||"tuya_lan_status_unavailable")}.`;}catch(error){statusNode.textContent=`A leitura DPS local falhou: ${error.message}`;}finally{button.disabled=false;}});
  if(isTuya)dialog.querySelector("[data-tuya-detail-read]")?.addEventListener("click",async event=>{const button=event.currentTarget,statusNode=dialog.querySelector("[data-tuya-detail-lan-status]");button.disabled=true;statusNode.textContent="A testar apenas a ligação LAN deste equipamento…";let probe;try{probe=await testTuyaLanReachability(deviceId);}catch(error){statusNode.textContent=`Teste LAN falhou: ${error.message}`;button.disabled=false;return;}const {reading,result}=probe;state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==deviceId),reading];statusNode.textContent=result.connection_state==="lan_reachable"?`O IP e a porta local responderam em ${Number(result.latency_ms)||0} ms. Este teste não consultou DPS; o estado e as medições são lidos separadamente.`:result.connection_state==="lan_host_responded"?"O IP respondeu, mas a porta local do Tuya não está a aceitar ligações; dispositivo ainda não confirmado.":`Sem resposta LAN · ${tuyaLanReasonText(result.reason||"tuya_connection_failed")}`;try{render();}catch(error){statusNode.textContent+=` A resposta LAN foi recebida; houve uma falha ao atualizar o cartão: ${error.message}`;}finally{button.disabled=false;}});
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.showModal();
}
function openNetworkInventoryDeviceDetails(deviceKey){
  const device=(state.gatewayDeviceInventory||[]).find(item=>item.device_key===deviceKey);
  if(!device)return;
  const providerId=String(device.source_device_id||"");
  if(device.source_provider==="tuya"&&state.tuyaDevices.some(item=>item.device_id===providerId)){
    openFavoriteDeviceDetails(providerId,"tuya");return;
  }
  const dialog=document.createElement("dialog");dialog.className="settings-dialog favorite-device-details";
  const readings=[device.manufacturer,device.model,device.last_ip,device.mac].filter(Boolean);
  const identified=device.confirmation_status==="confirmed";
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">${identified?"EQUIPAMENTO IDENTIFICADO":"EQUIPAMENTO · POR CONFIRMAR"}</p><h2>${esc(device.name||"Dispositivo")}</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></div><p>${identified?"O Gateway confirmou o IP e o MAC na rede. A ligação de controlo e as leituras DPS são verificações separadas.":"O Gateway guardou a identidade deste equipamento, mas ainda não confirmou um IP único."}</p>${readings.length?`<p class="field-note">${readings.map(esc).join(" · ")}</p>`:""}<p class="field-note">Para ler ou controlar um Tuya, o Gateway também precisa de associar este MAC ao dispositivo Tuya sincronizado, com a chave local. A pesquisa de rede não fornece essa chave.</p><div class="dialog-actions"><button class="button secondary" value="close">Fechar</button></div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.showModal();
}
function tuyaIsEvCharger(device){
  const kind=device?.device_kind_override||device?.device_kind||"",text=[device?.category,device?.product_name,device?.name].filter(Boolean).join(" ").toLowerCase();
  return kind==="ev_charger"||String(device?.category||"").toLowerCase().replace(/[^a-z0-9]/g,"")==="qccdz"||/\bevse\b|\bew charger\b|\belectric vehicle charger\b|\bwallbox\b|carregador\s+(?:ev|de veículo|de veiculo)/i.test(text);
}
function tuyaIsBreaker(device){
  if(!device||tuyaIsEvCharger(device)||tuyaIsKgHybrid(device))return false;
  return ["breaker","breaker-3pn"].includes(equipmentIconType(device,"tuya"));
}
async function refreshTuyaSchemaIfNeeded(deviceId,config){
  const initial=(config?.tuya?.devices||[]).find(item=>item.device_id===deviceId);
  if(!initial)return {device:null,queried:false,found:false};
  if((initial.functions||[]).length||(initial.status_spec||[]).length)return {device:initial,queried:false,found:true};
  if(!config?.tuya?.configured)return {device:initial,queried:false,found:false};
  const sync=await syncGatewayTuyaDevices(),devices=normalizeTuyaInventory(sync.inventory?.devices||[]);
  state.tuyaDevices=devices;
  const device=devices.find(item=>item.device_id===deviceId)||initial;
  return {device,queried:true,found:Boolean((device.functions||[]).length||(device.status_spec||[]).length),schemaFailures:sync.schema_failures||0};
}
function tuyaEditableSettings(device){
  const status=Array.isArray(state.tuyaReadings?.find(item=>item.device_id===device.device_id)?.status)?state.tuyaReadings.find(item=>item.device_id===device.device_id).status:[];
  const allowed=/(count.?down|child.?lock|maintenance.?lock|light.?mode|relay.?status|power.?on.?state|switch.?led|led.?type|indicator.?light|backlight|alarm|over.?power|under.?power|over.?current|under.?current|over.?voltage|under.?voltage|trip)/i,kgOnly=/(switch.?type|io.?set|scene|number)/i,kgHybrid=tuyaIsKgHybrid(device);
  return (Array.isArray(device.functions)?device.functions:[]).flatMap(spec=>{
    const descriptor=`${spec?.code||""} ${spec?.name||""} ${spec?.desc||""}`;
    const evAllowed=/(charge|charging|charger|current.?limit|start.?charge|stop.?charge|charge.?mode)/i.test(descriptor);
    if(!spec||typeof spec.code!=="string")return [];
    let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{return []}}
    const type=String(spec.type||"").toLowerCase(),dpId=tuyaSpecDpsId(device,spec),range=Array.isArray(values?.range)?values.range:[],kgGlobal=(kgHybrid&&type==="enum"&&(dpId===14&&["off","on","memory"].every(value=>range.includes(value))||dpId===107&&range.length>0));
    if(tuyaIsEvCharger(device)?!evAllowed:!allowed.test(descriptor)&&!(kgHybrid&&kgOnly.test(descriptor))&&!kgGlobal)return [];
    const current=status.find(row=>row.code===spec.code||Number(row?.dps_id??row?.dp_id??row?.dpId)===Number(dpId))?.value,localDpsMapped=Boolean(device.local_dps_map?.[spec.code])||Number.isInteger(dpId)||spec.code==="switch"||/^switch_[1-9]\d*$/.test(spec.code)||/^\d+$/.test(spec.code);
    if(["bool","boolean"].includes(type))return [{...spec,kind:"boolean",current,values,localDpsMapped}];
    if(["integer","int","number"].includes(type)&&Number.isInteger(Number(values.min))&&Number.isInteger(Number(values.max))&&values.min<=values.max)return [{...spec,kind:"integer",current,values,localDpsMapped}];
    if(type==="enum"&&Array.isArray(values.range)&&values.range.every(value=>typeof value==="string"))return [{...spec,kind:"enum",current,values,localDpsMapped}];
    return [];
  });
}
function tuyaUnmappedSettingChange(editable,inputs){
  return editable.find(item=>!item.localDpsMapped&&inputs.some(input=>{
    if(input.dataset.tuyaSetting!==item.code)return false;
    const value=item.kind==="boolean"?input.value==="true":item.kind==="integer"?Number(input.value):input.value;
    return value!==item.current;
  }));
}
function openTuyaDeviceSettings(device){
  const evCharger=tuyaIsEvCharger(device),kgHybrid=tuyaIsKgHybrid(device),editable=tuyaEditableSettings(device),kgSettings=editable.filter(item=>![113,114,115].includes(tuyaSpecDpsId(device,item))),groups=evCharger?[["Carregamento",editable]]:kgHybrid?[["Comportamento após falha de energia",kgSettings.filter(item=>tuyaSpecDpsId(device,item)===14||/relay.?status|power.?on.?state/i.test(`${item.code} ${item.name||""}`))],["Configuração global",kgSettings.filter(item=>tuyaSpecDpsId(device,item)===107||/switch.?type|io.?set/i.test(`${item.code} ${item.name||""}`))],["Cenas e outras opções",kgSettings.filter(item=>/scene|number/i.test(`${item.code} ${item.name||""}`))],["Outras definições declaradas",kgSettings.filter(item=>!/relay.?status|power.?on.?state|switch.?type|io.?set|scene|number/i.test(`${item.code} ${item.name||""}`)&&![14,107].includes(tuyaSpecDpsId(device,item)))]]:[["Countdown",editable.filter(item=>/count.?down/i.test(item.code+" "+item.name))],["Lock e modo de luz",editable.filter(item=>/lock|light.?mode|relay.?status|power.?on.?state/i.test(item.code+" "+item.name))],["Luzes indicadoras",editable.filter(item=>/switch.?led|led.?type|indicator.?light|backlight/i.test(item.code+" "+item.name))],["Alarmes",editable.filter(item=>/alarm|over.?power|under.?power|over.?current|under.?current|over.?voltage|under.?voltage|trip/i.test(item.code+" "+item.name))]];
  const control=item=>item.kind==="boolean"?`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}><option value="true" ${item.current===true?"selected":""}>Ativo / ligado</option><option value="false" ${item.current===false?"selected":""}>Inativo / desligado</option></select>`:item.kind==="integer"?`<input type="number" data-tuya-setting="${esc(item.code)}" min="${Number(item.values.min)}" max="${Number(item.values.max)}" step="${Number(item.values.step)||1}" value="${Number.isInteger(Number(item.current))?Number(item.current):Number(item.values.min)}" ${item.localDpsMapped?"":"disabled"}>`:`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}>${item.values.range.map(value=>`<option value="${esc(value)}" ${value===item.current?"selected":""}>${esc(value)}</option>`).join("")}</select>`;
  const content=groups.map(([label,items])=>items.length?`<section class="tuya-settings-group"><h3>${label}</h3>${items.map(item=>`<label class="tuya-setting-row"><span><strong>${esc(item.name||item.code)}</strong><small>${esc(item.code)} · ${esc(item.type)}${item.localDpsMapped?"":" · DPS local por mapear"}</small></span>${control(item)}</label>`).join("")}</section>`:"").join("");
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-capability-settings";
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">SETTINGS · DPS DECLARADOS</p><h2>${esc(device.name)}</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></div><p class="field-note">Só aparecem funções editáveis que a Tuya declarou para este equipamento. Limites e opções vêm do próprio esquema DPS.</p>${content||`<div class="empty-state">${evCharger?"Carregador EV. Não aplicamos countdown, child lock, modo de luz ou alarmes de disjuntor. Só aparecem controlos de carregamento declarados pela Tuya e mapeados para controlo local.":"Este equipamento não declarou funções editáveis de countdown, lock, modo ou alarmes. As leituras e alarmes atuais continuam disponíveis no detalhe."}</div>`}<p class="connection-result" data-tuya-settings-status role="status" aria-live="polite"></p><div class="dialog-actions"><button class="button secondary" value="close">Fechar</button>${content?`<button class="button primary" type="button" data-tuya-settings-save>Guardar definições</button>`:""}</div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});
  dialog.querySelector("[data-tuya-settings-save]")?.addEventListener("click",async event=>{
    const button=event.currentTarget,status=dialog.querySelector("[data-tuya-settings-status]"),inputs=[...dialog.querySelectorAll("[data-tuya-setting]")];button.disabled=true;status.textContent="A guardar apenas as funções DPS alteradas…";
    const unmapped=tuyaUnmappedSettingChange(editable,inputs);if(unmapped){status.textContent=`Não foi enviado qualquer comando: a função ${unmapped.code} precisa do DPS local correto. Abre IP, MAC e DPS para o mapear.`;button.disabled=false;return;}
    try{for(const input of inputs){const spec=editable.find(item=>item.code===input.dataset.tuyaSetting);if(!spec)continue;let value=input.value;if(spec.kind==="boolean")value=value==="true";else if(spec.kind==="integer")value=Number(value);if(value===spec.current)continue;await sendGatewayTuyaSetting(device.device_id,spec.code,value);spec.current=value;}
      status.textContent="Comandos de definição enviados. O estado será atualizado pelo varrimento independente.";
    }catch(error){status.textContent=`Não foi possível confirmar a definição: ${error.message}`;}finally{button.disabled=false;}
  });
  dialog.showModal();
}
function openTuyaQuickControls(device){
  device=tuyaDeviceWithPidMap(device);
  const live=state.tuyaReadings.find(item=>item.device_id===device.device_id),status=Array.isArray(live?.status)?live.status:[],codes=tuyaSwitchCodes(device),editable=tuyaEditableSettings(device),evCharger=tuyaIsEvCharger(device),physicalBreaker=tuyaIsBreaker(device);
  const channelCodes=tuyaSwitchChannelCodes(device,codes),multi=channelCodes.length>=2,kgHybrid=tuyaIsKgHybrid(device),pairModes=tuyaKgPairModeSpecs(device);
  const master=multi?"":(codes.includes("switch_all")?"switch_all":(codes.includes("switch")&&codes.some(code=>/^switch_\d+$/i.test(code))?"switch":"")),masterValue=master?tuyaSwitchState(device,live,master):undefined;
  const channels=(multi?channelCodes:codes.filter(code=>code!=="switch_all"&&code!==master)).map(code=>{const spec=(device.functions||[]).find(item=>item?.code===code),fallback=code.match(/^switch_(\d+)$/i)?.[1]?`Canal ${code.match(/^switch_(\d+)$/i)[1]}`:code;return {code,label:device.channel_labels?.[code]||device.capability_labels?.[code]||spec?.name||fallback,value:tuyaSwitchState(device,live,code)};});
  const toggle=(code,label,value)=>`<div class="tuya-quick-channel"><button type="button" class="favorite-state-symbol ${value===true?"on":value===false?"off":"unknown"}" data-tuya-quick-toggle="${esc(code)}" aria-pressed="${value===true}" aria-label="${esc(label)} · ${value===true?"ligado":value===false?"desligado":"estado por confirmar no varrimento"}" ${sessionInfo().user?.role!=="owner"?"disabled":""}>${value===true?"ON":value===false?"OFF":"—"}</button><span data-tuya-channel-label="${esc(code)}" title="Duplo clique para alterar o nome"><strong>${esc(label)}</strong></span></div>`;
  const kgTile=(item,curtain=false)=>`<div class="tuya-kg-channel-tile"><button type="button" class="tuya-kg-channel-control ${item.value===true?"on":item.value===false?"off":"unknown"}" data-tuya-quick-toggle="${esc(item.code)}" aria-pressed="${item.value===true}" aria-label="${esc(item.label)} · ${item.value===true?"ligado":item.value===false?"desligado":"estado por confirmar no varrimento"}" ${curtain||sessionInfo().user?.role!=="owner"?"disabled":""}><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M22.4 5.9a12 12 0 1 1-12.8 0M16 3v12"/></svg></button><span data-tuya-channel-label="${esc(item.code)}" title="Duplo toque para alterar o nome"><strong>${esc(item.label)}</strong>${curtain?`<small>Comando de cortina não declarado</small>`:""}</span></div>`;
  const pairPanel=pairModes.map(pair=>{
    const pairChannels=channels.slice((pair.pair-1)*2,pair.pair*2),mode=pair.current==="curtain"?"curtain":pair.current==="switch"?"switch":"";
    const selector=`<div class="tuya-pair-mode" role="group" aria-label="Modo do par ${pair.pair}"><button type="button" data-tuya-pair-mode="${pair.pair}" data-mode="switch" aria-pressed="${mode==="switch"}" ${!pair.supported||sessionInfo().user?.role!=="owner"?"disabled":""}>Switch mode</button><button type="button" data-tuya-pair-mode="${pair.pair}" data-mode="curtain" aria-pressed="${mode==="curtain"}" ${!pair.supported||sessionInfo().user?.role!=="owner"?"disabled":""}>Curtain mode</button></div>`;
    const content=mode==="switch"?`<div class="tuya-kg-channel-grid">${pairChannels.map(item=>kgTile(item)).join("")}</div>`:mode==="curtain"?`<div class="tuya-kg-channel-grid">${pairChannels.map(item=>kgTile(item,true)).join("")}</div>`:`<div class="tuya-kg-channel-grid">${pairChannels.map(item=>`<div class="tuya-kg-channel-tile"><span data-tuya-channel-label="${esc(item.code)}" title="Duplo toque para alterar o nome"><strong>${esc(item.label)}</strong><small>A aguardar leitura do modo deste par</small></span></div>`).join("")}</div>`;
    return `<section class="tuya-kg-pair"><h3>Par ${pair.pair} · ${esc(pairChannels.map(item=>item.label).join(" / ")||`K${pair.pair*2-1} / K${pair.pair*2}`)}</h3>${selector}${content}${!pair.supported?`<small class="field-note">O modo deste par ainda não está declarado como opção editável no esquema Tuya.</small>`:""}</section>`;
  }).join("");
  const kgGlobalSettings=editable.filter(item=>[14,107].includes(tuyaSpecDpsId(device,item))||/relay.?status|power.?on.?state|switch.?type|io.?set|scene|number/i.test(`${item.code} ${item.name||""}`));
  const breakerCountdown=editable.find(item=>/count.?down/i.test(`${item.code} ${item.name||""}`)&&item.kind==="integer"),breakerLocks=editable.filter(item=>/(child.?lock|maintenance.?lock)/i.test(`${item.code} ${item.name||""}`)),quickPanelDevice=Boolean(!kgHybrid&&!evCharger&&channels.length===1&&(physicalBreaker||breakerCountdown||breakerLocks.length));
  const breaker=quickPanelDevice;
  const quickEditable=breaker?[...(breakerCountdown?[breakerCountdown]:[]),...breakerLocks]:kgHybrid?kgGlobalSettings:editable;
  const quickSettingRows=quickEditable.map(item=>`<label class="tuya-setting-row"><span><strong>${esc(item.name||item.code)}</strong></span>${item.kind==="boolean"?`<select data-tuya-setting="${esc(item.code)}"><option value="true" ${item.current===true?"selected":""}>Ligado</option><option value="false" ${item.current===false?"selected":""}>Desligado</option></select>`:item.kind==="enum"?`<select data-tuya-setting="${esc(item.code)}">${item.values.range.map(value=>`<option value="${esc(value)}" ${value===item.current?"selected":""}>${esc(value)}</option>`).join("")}</select>`:`<input type="number" data-tuya-setting="${esc(item.code)}" min="${Number(item.values.min)}" max="${Number(item.values.max)}" step="${Number(item.values.step)||1}" value="${Number.isInteger(Number(item.current))?Number(item.current):Number(item.values.min)}">`}</label>`).join("");
  const settingControl=item=>item.kind==="boolean"?`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}><option value="true" ${item.current===true?"selected":""}>Ativo</option><option value="false" ${item.current===false?"selected":""}>Inativo</option></select>`:item.kind==="integer"?`<label class="tuya-countdown-picker"><button type="button" data-step="-1" aria-label="Diminuir">−</button><input type="range" data-tuya-setting="${esc(item.code)}" min="${Number(item.values.min)}" max="${Number(item.values.max)}" step="${Number(item.values.step)||1}" value="${Number.isInteger(Number(item.current))?Number(item.current):Number(item.values.min)}"><output data-countdown-value>${Number.isInteger(Number(item.current))?Number(item.current):Number(item.values.min)} s</output><button type="button" data-step="1" aria-label="Aumentar">＋</button></label>`:`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}>${item.values.range.map(value=>`<option value="${esc(value)}" ${value===item.current?"selected":""}>${esc(value)}</option>`).join("")}</select>`;
  const settingRows=editable.map(item=>`<label class="tuya-setting-row"><span><strong>${esc(item.name||item.code)}</strong><small>${esc(item.code)}</small></span>${settingControl(item)}</label>`).join("");
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-quick-controls";dialog.dataset.tuyaDeviceId=device.device_id;
  const powerIcon=`<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg>`;
  const lockState=breakerLocks.find(item=>item.kind==="boolean"),lockItems=breakerLocks.filter(item=>item.localDpsMapped),breakerSettings=editable.filter(item=>!breakerLocks.includes(item)&&/(relay.?status|power.?on.?state|alarm|over.?power|under.?power|over.?current|under.?current|over.?voltage|under.?voltage|trip)/i.test(`${item.code} ${item.name||""}`));
  const settingField=item=>`<label class="tuya-setting-row tuya-quick-setting"><span><strong>${esc(tuyaFriendlyCapabilityLabel(item,device))}</strong></span>${item.kind==="boolean"?`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}><option value="true" ${item.current===true?"selected":""}>Ligado</option><option value="false" ${item.current===false?"selected":""}>Desligado</option></select>`:item.kind==="enum"?`<select data-tuya-setting="${esc(item.code)}" ${item.localDpsMapped?"":"disabled"}>${item.values.range.map(value=>`<option value="${esc(value)}" ${value===item.current?"selected":""}>${esc(tuyaEnumValuePt(value))}</option>`).join("")}</select>`:`<input type="number" data-tuya-setting="${esc(item.code)}" min="${Number(item.values.min)}" max="${Number(item.values.max)}" step="${Number(item.values.step)||1}" value="${Number.isInteger(Number(item.current))?Number(item.current):Number(item.values.min)}" ${item.localDpsMapped?"":"disabled"}>`}</label>`;
  const durationLabel=value=>{const seconds=Math.max(0,Number(value)||0),hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),remainder=Math.floor(seconds%60);return hours?`${hours} h ${minutes} min`:minutes?`${minutes} min ${remainder} s`:`${remainder} s`;};
  const breakerPanel=key=>`<section class="tuya-breaker-panel" data-breaker-panel="${key}" ${key!=="switch"?"hidden":""}>${key==="switch"?channels[0]?`<button type="button" class="breaker-quick-power ${channels[0].value===true?"on":channels[0].value===false?"off":"unknown"}" data-tuya-quick-toggle="${esc(channels[0].code)}" aria-pressed="${channels[0].value===true}" aria-label="${channels[0].value===true?"Desligar":channels[0].value===false?"Ligar":"Estado por confirmar"}" ${channels[0].value===undefined||!tuyaSwitchCodeHasLocalMapping(device,channels[0].code)||sessionInfo().user?.role!=="owner"?"disabled":""}>${powerIcon}<span>${channels[0].value===true?"Ligado":channels[0].value===false?"Desligado":"Por confirmar"}</span></button>`:`<p class="field-note">Controlo ON/OFF não declarado.</p>`:key==="countdown"?breakerCountdown?`<div class="breaker-countdown-control"><label for="breaker-countdown-slider">Temporizador</label><output class="breaker-countdown-value" data-countdown-value>${durationLabel(Number.isInteger(Number(breakerCountdown.current))?Number(breakerCountdown.current):Number(breakerCountdown.values.min))}</output><input id="breaker-countdown-slider" type="range" data-tuya-setting="${esc(breakerCountdown.code)}" min="${Number(breakerCountdown.values.min)}" max="${Number(breakerCountdown.values.max)}" step="${Number(breakerCountdown.values.step)||1}" value="${Number.isInteger(Number(breakerCountdown.current))?Number(breakerCountdown.current):Number(breakerCountdown.values.min)}" ${breakerCountdown.localDpsMapped&&sessionInfo().user?.role==="owner"?"":"disabled"}><button type="button" class="button primary" data-breaker-countdown-save ${breakerCountdown.localDpsMapped&&sessionInfo().user?.role==="owner"?"":"disabled"}>Aplicar temporizador</button></div>`:`<p class="field-note">Este equipamento não declarou um temporizador.</p>`:[...lockItems,...breakerSettings].length?`<div class="breaker-lock-controls">${[...lockItems,...breakerSettings].map(item=>settingField(item)).join("")}</div>`:`<p class="field-note">Este equipamento não declarou bloqueios ou definições adicionais.</p>`}</section>`;
  const settingsAvailable=breakerSettings.length>0||lockItems.length>0;
  const breakerMenu=breaker?`<nav class="tuya-breaker-tabs" aria-label="Controlos do dispositivo"><button type="button" data-breaker-tab="switch" aria-label="Ligar ou desligar" title="Ligar / desligar" aria-pressed="true">${powerIcon}</button><button type="button" data-breaker-tab="countdown" aria-label="Temporizador" title="Temporizador" aria-pressed="false" ${breakerCountdown?"":"disabled"}><svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="15" r="9"/><path d="M14 10v5l4 2M10 3h8"/></svg></button><button type="button" data-breaker-tab="lock" aria-label="${lockItems.length?"Bloqueio":"Definições"}" title="${lockItems.length?"Bloqueio":"Definições"}" aria-pressed="false" ${settingsAvailable?"":"disabled"}><svg viewBox="0 0 28 28" aria-hidden="true">${lockItems.length?`<rect x="5" y="12" width="18" height="13" rx="2"/><path d="M9 12V8a5 5 0 0 1 10 0v4"/>`:`<circle cx="14" cy="14" r="3"/><path d="M14 2v3M14 23v3M2 14h3M23 14h3M5.5 5.5l2.2 2.2m12.6 12.6 2.2 2.2m0-17-2.2 2.2M7.7 20.3l-2.2 2.2"/>`}</svg></button></nav>${breakerPanel("switch")}${breakerPanel("countdown")}${breakerPanel("lock")}`:"";
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">${kgHybrid?"CANAIS · MODOS POR PAR":breaker?"CONTROLO DO DISPOSITIVO":evCharger?"CARREGAMENTO":"CANAIS"}</p><h2>${esc(device.name)}</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></div>${breaker?breakerMenu:kgHybrid?pairPanel:channels.length?`<div class="tuya-quick-channel-list">${channels.map(item=>toggle(item.code,item.label,item.value)).join("")}</div>`:`<p class="field-note">${evCharger?"Este carregador não declarou canais de comando locais.":"Não foram encontrados canais ON/OFF neste dispositivo."}</p>`}${!breaker&&kgHybrid?`<button type="button" class="button secondary tuya-kg-settings-button" data-tuya-quick-settings>Definições</button>`:!breaker&&editable.length?`<section><h3>${evCharger?"Controlos de carregamento":"Temporizador e definições declaradas"}</h3>${settingRows}<button type="button" class="button primary" data-tuya-quick-save>Guardar definições</button></section>`:""}<p class="connection-result" data-tuya-quick-status role="status" aria-live="polite"></p>${!breaker&&!kgHybrid?`<div class="dialog-actions"><button type="button" class="button secondary" data-tuya-quick-settings>Definições</button><button class="button secondary" value="close">Fechar</button></div>`:!breaker?`<div class="dialog-actions"><button class="button secondary" value="close">Fechar</button></div>`:""}</form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});
  dialog.querySelectorAll("[data-tuya-quick-toggle]").forEach(button=>button.addEventListener("click",async()=>{
    const code=button.dataset.tuyaQuickToggle;button.disabled=true;const output=dialog.querySelector("[data-tuya-quick-status]");output.textContent="A enviar o comando independente da leitura…";
    try{const currentDevice=state.tuyaDevices.find(item=>item.device_id===device.device_id)||device,currentReading=state.tuyaReadings.find(item=>item.device_id===device.device_id)||live,current=tuyaSwitchState(currentDevice,currentReading,code);if(typeof current!=="boolean")throw new Error("Ainda não há estado ON/OFF confirmado pelo varrimento independente.");if(!tuyaSwitchCodeHasLocalMapping(currentDevice,code))throw new Error("Falta o mapeamento DPS local exato deste canal.");await sendTuyaSwitchCommand(currentDevice,code,!current);output.textContent="Ordem enviada. O estado será atualizado pela próxima leitura LAN.";}catch(error){output.textContent=error.outcomeUnknown?error.message:`Falha ao enviar comando: ${error.message}`;}finally{button.disabled=false;}
  }));
  dialog.querySelectorAll("[data-tuya-pair-mode]").forEach(button=>button.addEventListener("click",async()=>{
    const pair=Number(button.dataset.tuyaPairMode),mode=button.dataset.mode,spec=pairModes[pair-1],output=dialog.querySelector("[data-tuya-quick-status]");
    if(!spec?.supported||!spec.code)return;
    dialog.querySelectorAll(`[data-tuya-pair-mode="${pair}"]`).forEach(item=>item.disabled=true);output.textContent=`A enviar ${mode==="switch"?"Switch mode":"Curtain mode"} para o par ${pair}…`;
    try{await sendGatewayTuyaSetting(device.device_id,spec.code,mode);output.textContent="Modo enviado. A seleção será confirmada pela próxima leitura do motor.";}
    catch(error){output.textContent=`Não foi possível alterar o modo do par: ${error.message}`;}
    finally{dialog.querySelectorAll(`[data-tuya-pair-mode="${pair}"]`).forEach(item=>item.disabled=false);}
  }));
  dialog.querySelectorAll("[data-tuya-channel-label]").forEach(label=>label.addEventListener("dblclick",async()=>{if(sessionInfo().user?.role!=="owner")return;const code=label.dataset.tuyaChannelLabel,current=device.channel_labels?.[code]||label.textContent.trim(),next=window.prompt("Nome deste canal",current);if(next===null||!next.trim())return;try{const config=await readGatewayHardwareIntegrationConfig(),devices=(config.tuya?.devices||[]).map(item=>item.device_id===device.device_id?{...item,channel_labels:{...(item.channel_labels||{}),[code]:next.trim()}}:item);await saveGatewayHardwareIntegrationConfig({tuya:{devices}});device.channel_labels={...(device.channel_labels||{}),[code]:next.trim()};label.querySelector("strong").textContent=next.trim();render();}catch(error){dialog.querySelector("[data-tuya-quick-status]").textContent=`O nome do canal não foi guardado: ${error.message}`;}}));
  dialog.querySelectorAll("[data-breaker-tab]").forEach(button=>button.addEventListener("click",()=>{const key=button.dataset.breakerTab;dialog.querySelectorAll("[data-breaker-tab]").forEach(tab=>tab.setAttribute("aria-pressed",String(tab===button)));dialog.querySelectorAll("[data-breaker-panel]").forEach(panel=>panel.hidden=panel.dataset.breakerPanel!==key);}));
  dialog.querySelectorAll("[data-tuya-setting][type=range]").forEach(input=>input.addEventListener("input",()=>{const output=input.parentElement.querySelector("[data-countdown-value]");if(output)output.textContent=durationLabel(input.value);}));
  dialog.querySelector("[data-breaker-countdown-save]")?.addEventListener("click",async event=>{const button=event.currentTarget,input=dialog.querySelector("#breaker-countdown-slider"),output=dialog.querySelector("[data-tuya-quick-status]");button.disabled=true;try{await sendGatewayTuyaSetting(device.device_id,breakerCountdown.code,Number(input.value));output.textContent="Countdown enviado; o Gateway atualizará o estado na leitura periódica.";}catch(error){output.textContent=`Não foi possível enviar o countdown: ${error.message}`;}finally{button.disabled=false;}});
  dialog.querySelectorAll("[data-breaker-lock-code]").forEach(button=>button.addEventListener("click",async()=>{const output=dialog.querySelector("[data-tuya-quick-status]"),code=button.dataset.breakerLockCode,spec=breakerLocks.find(item=>item.code===code);if(!spec?.localDpsMapped)return;const value=spec.kind==="boolean"?button.dataset.breakerLockValue==="true":button.dataset.breakerLockValue;dialog.querySelectorAll(`[data-breaker-lock-code="${CSS.escape(code)}"]`).forEach(item=>item.disabled=true);try{await sendGatewayTuyaSetting(device.device_id,code,value);output.textContent="Lock enviado; a leitura periódica confirmará o estado.";}catch(error){output.textContent=`Não foi possível alterar o lock: ${error.message}`;}finally{dialog.querySelectorAll(`[data-breaker-lock-code="${CSS.escape(code)}"]`).forEach(item=>item.disabled=false);}}));
  dialog.querySelectorAll("[data-step]").forEach(button=>button.addEventListener("click",()=>{const input=button.parentElement.querySelector("input"),step=Number(input.step)||1;input.value=String(Math.min(Number(input.max),Math.max(Number(input.min),Number(input.value)+Number(button.dataset.step)*step)));input.dispatchEvent(new Event("input",{bubbles:true}));}));
  dialog.querySelectorAll("[data-tuya-quick-save],[data-breaker-settings-save]").forEach(saveButton=>saveButton.addEventListener("click",async event=>{const button=event.currentTarget,output=dialog.querySelector("[data-tuya-quick-status]"),scope=button.dataset.breakerSettingsSave,inputs=[...dialog.querySelectorAll("[data-tuya-setting]")].filter(input=>!scope||quickEditable.find(item=>item.code===input.dataset.tuyaSetting&&((scope==="countdown"&&breakerCountdown.includes(item))||(scope==="lock"&&breakerLocks.includes(item)))));button.disabled=true;output.textContent="A guardar apenas os valores DPS alterados…";const unmapped=tuyaUnmappedSettingChange(quickEditable,inputs);if(unmapped){output.textContent=`Não foi enviado qualquer comando: a função ${unmapped.code} precisa do DPS local correto.`;button.disabled=false;return;}try{for(const input of inputs){const spec=quickEditable.find(item=>item.code===input.dataset.tuyaSetting);if(!spec||!spec.localDpsMapped)continue;let value=input.value;if(spec.kind==="boolean")value=value==="true";else if(spec.kind==="integer")value=Number(value);if(value===spec.current)continue;await sendGatewayTuyaSetting(device.device_id,spec.code,value);}output.textContent="Definições enviadas pela ligação local.";}catch(error){output.textContent=`Definição não confirmada: ${error.message}`;}finally{button.disabled=false;}}));
  dialog.querySelector("[data-tuya-quick-settings]")?.addEventListener("click",()=>{dialog.close();openTuyaDeviceSettings(device);});dialog.showModal();
}
function tuyaReadingConfirmed(reading){return Boolean(reading&&["local_responded","lan_reachable"].includes(reading.connection_state));}
async function testTuyaLanDevice(deviceId,rounds=3){
  const report=await runGatewayTuyaLanDiagnostics(rounds,deviceId),result=(Array.isArray(report.devices)?report.devices:[]).find(item=>item?.device_id===deviceId);
  if(!result)throw new Error("O Gateway não devolveu o resultado do teste LAN para este dispositivo.");
  const reading={device_id:deviceId,name:result.name||"Tuya",status:Array.isArray(result.status)?result.status:[],connection_state:result.connection_state||"failed",reason:result.reason||undefined,latency_ms:result.average_latency_ms,local_protocol:result.local_protocol,source:"TUYA_LAN",lan_probe:true,checked_at:new Date().toISOString(),trust:result.connection_state==="local_responded"?"LIVE_UNVERIFIED":"UNAVAILABLE",success_count:result.success_count,rounds:result.rounds,power_telemetry_configured:result.power_telemetry_configured};
  return {reading,result};
}
function refreshTuyaDeviceAfterAction(deviceId,statusNode,commandStartedAt,commandRoundTripMs,label="Comando enviado",deviceCommandMs=null){
  clearTimeout(pendingTuyaReadbacks.get(deviceId));
  const timer=window.setTimeout(async()=>{
    try{
      const {reading,result}=await testTuyaLanDevice(deviceId,1);
      state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==deviceId),reading];
      settlePendingTuyaSwitchStates(state.tuyaDevices||[],state.tuyaReadings);
      updateVisibleTuyaCard(deviceId);updateOpenTuyaDeviceDialog(deviceId);
      const elapsed=Math.max(0,Date.now()-commandStartedAt),lanValue=Number(result.average_latency_ms??reading.latency_ms),lanMs=Number.isFinite(lanValue)?`${lanValue.toLocaleString("pt-PT",{maximumFractionDigits:1})} ms`:"indisponível";
      const devicePart=Number.isFinite(Number(deviceCommandMs))?` · Gateway→equipamento ${Math.round(Number(deviceCommandMs))} ms`:"";
      if(statusNode)statusNode.textContent=reading.connection_state==="local_responded"?`${label}; leitura LAN atualizada · app→Gateway ${Math.round(commandRoundTripMs)} ms${devicePart} · leitura ${lanMs} · total ${elapsed} ms.`:`${label}; leitura LAN não confirmou o estado · app→Gateway ${Math.round(commandRoundTripMs)} ms${devicePart}.`;
    }catch(error){if(statusNode)statusNode.textContent=`${label}; confirmação LAN pendente: ${error.message}`;}
    finally{if(pendingTuyaReadbacks.get(deviceId)===timer)pendingTuyaReadbacks.delete(deviceId);}
  },120);
  pendingTuyaReadbacks.set(deviceId,timer);
}
function confirmTuyaCommandInBackground(device,requestedAt,codes,desired,commandRoundTripMs,deviceCommandMs=null){
  const deviceId=device.device_id;
  window.setTimeout(async()=>{
    const devicePart=Number.isFinite(Number(deviceCommandMs))?` · Gateway→equipamento ${Math.round(Number(deviceCommandMs))} ms`:"";
    const timing=`app→Gateway ${Math.round(commandRoundTripMs)} ms${devicePart}`;
    document.querySelectorAll(`dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"] [data-tuya-quick-status],dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"] [data-tuya-detail-lan-status]`).forEach(node=>{node.textContent=`Ordem aceite; a aguardar a leitura LAN normal. ${timing}`;});
  },0);
  window.setTimeout(()=>{let changed=false;for(const code of codes){const key=`${deviceId}::${code}`,pending=pendingTuyaSwitchStates.get(key);if(pending?.requestedAt===requestedAt&&!pending.timedOut){pending.timedOut=true;pending.mismatchCount=0;pending.lastObservedAt=Math.max(pending.requestedAt,tuyaReadingTimestamp(state.tuyaReadings.find(item=>item.device_id===deviceId)));changed=true;}}if(changed){updateVisibleTuyaCard(deviceId);updateOpenTuyaDeviceDialog(deviceId);document.querySelectorAll(`dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"] [data-tuya-quick-status],dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"] [data-tuya-detail-lan-status]`).forEach(node=>{if(node.textContent.includes("aguardar a leitura LAN normal"))node.textContent="Ainda sem confirmação LAN; estado temporariamente desconhecido.";});}},8_000);
}
async function sendGatewayTuyaSetting(deviceId,code,value){
  const requestedAt=Date.now(),started=performance.now(),result=await controlGatewayTuyaSetting(deviceId,code,value),elapsed=performance.now()-started;
  const statusNode=document.querySelector(`dialog[open][data-tuya-device-id="${CSS.escape(deviceId)}"] [data-tuya-quick-status]`);
  refreshTuyaDeviceAfterAction(deviceId,statusNode,requestedAt,elapsed,"Definição enviada",result.device_command_latency_ms);
  return result;
}
async function sendGatewayTuyaLevel(deviceId,percent){
  const requestedAt=Date.now(),started=performance.now(),result=await controlGatewayTuyaLevel(deviceId,percent),elapsed=performance.now()-started;
  const statusNode=document.querySelector(`[data-favorite-status="${CSS.escape(deviceId)}"]`);
  refreshTuyaDeviceAfterAction(deviceId,statusNode,requestedAt,elapsed,"Nível enviado",result.device_command_latency_ms);
  return result;
}
async function testTuyaLanReachability(deviceId){
  const result=await testGatewayTuyaLanReachability(deviceId),reading={device_id:deviceId,name:"Tuya",status:[],connection_state:result.connection_state||"failed",reason:result.reason||undefined,latency_ms:result.latency_ms,local_ip:result.local_ip,local_mac:result.local_mac,source:"TUYA_LAN_TCP",lan_probe:true,status_read:false,dps_read:false,cloud_requested:false,checked_at:new Date().toISOString()};
  return {reading,result};
}
function favoriteReadingConfirmed(item){return item?.kind==="tuya"?tuyaReadingConfirmed(item.status):Boolean(item?.reading&&Array.isArray(item.reading.readings)&&item.reading.readings.some(value=>value.value!=null&&Number.isFinite(Number(value.value))));}
function tuyaDeviceState(device,reading){
  const status=Array.isArray(reading?.status)?reading.status.filter(item=>item&&typeof item==="object"):[],code=device?.switch_code||status.find(item=>typeof item.value==="boolean")?.code;
  const value=status.find(item=>item.code===code)?.value;
  // A short freshness gap must not erase a known ON/OFF datapoint and make the card flicker.
  if(typeof value==="boolean")return reading?.connection_state==="local_responded"?(value?"Ligado":"Desligado"):`Último estado: ${value?"Ligado":"Desligado"}`;
  if(reading?.connection_state==="lan_reachable")return `Resposta LAN · ${Number(reading.latency_ms).toLocaleString("pt-PT")} ms · estado não consultado`;
  if(reading?.connection_state==="lan_host_responded")return "IP respondeu na LAN · porta Tuya fechada";
  if(reading?.connection_state==="failed")return device?.online===false?"Offline segundo a Tuya":"ON/OFF por confirmar";
  if(reading?.connection_state==="stored_status")return device?.online===false?"Offline segundo a Tuya":"ON/OFF por confirmar";
  return tuyaReadingConfirmed(reading)?"Online · sem estado ON/OFF":"Por confirmar";
}
function tuyaFault(device,reading){
  const specs=[...(Array.isArray(device?.status_spec)?device.status_spec:[]),...(Array.isArray(device?.functions)?device.functions:[])].filter(item=>item&&typeof item==="object"),labels=device?.capability_labels&&typeof device.capability_labels==="object"?device.capability_labels:{};
  for(const item of Array.isArray(reading?.status)?reading.status.filter(value=>value&&typeof value==="object"):[]){
    const spec=specs.find(candidate=>candidate.code===item.code),text=`${item.code||""} ${spec?.name||""} ${labels[item.code]||""}`.toLowerCase();
    if(!/(trip|fault|alarm|error|over.?voltage|under.?voltage|over.?current|under.?current|sobretens|subtens|sobrecorr|subcorr)/i.test(text))continue;
    const active=item.value===true||item.value===1||item.value==="1"||item.value==="true"||item.value==="alarm";
    if(active)return {code:item.code,label:spec?.name||labels[item.code]||tuyaFriendlyCapabilityLabel(spec||{code:item.code},device)||"Alarme ativo"};
  }
  return null;
}
function tuyaMetricSchema(device,code){
  const spec=[...(Array.isArray(device?.status_spec)?device.status_spec:[]),...(Array.isArray(device?.functions)?device.functions:[])].find(item=>item&&typeof item==="object"&&item.code===code)||{};
  let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}
  return {spec,unit:String(values?.unit||"").trim().toLowerCase(),scale:Number.isFinite(Number(values?.scale))?Number(values.scale):0,
    text:`${code||""} ${spec.name||""} ${device?.capability_labels?.[code]||""}`};
}
function tuyaMeasurementCodes(device){
  const status=Array.isArray(device?.current_status)?device.current_status:[],schema=[...(Array.isArray(device?.status_spec)?device.status_spec:[]),...(Array.isArray(device?.functions)?device.functions:[])].filter(item=>item&&typeof item==="object"&&!Array.isArray(item)),kinds={voltage:/(^|_)(cur_)?voltage($|_)/i,current:/(^|_)(cur_)?current($|_)/i,power:/(^|_)(cur_)?power($|_)/i,energy:/(^|_)(add_ele|total_energy|energy_total|electricity|energy)($|_)/i};
  const result={};
  for(const [kind,pattern] of Object.entries(kinds)){const item=schema.find(entry=>{const meta=tuyaMetricSchema(device,entry.code);const known=/voltage|tension|tensao/i.test(meta.text)||/current|corrente/i.test(meta.text)||/power|potencia|watt/i.test(meta.text)||/energy|energia|electricity|consumo/i.test(meta.text);return pattern.test(meta.text)&&known&&Boolean(meta.unit);});if(item)result[kind]=item.code;}
  return result;
}
function tuyaSimpleReadings(device,reading){
  const observedAt=tuyaReadingTimestamp(reading),sampleAge=observedAt?Date.now()-observedAt:Infinity;
  if(!Array.isArray(reading?.status)||sampleAge<0||sampleAge>120_000)return [];
  const status=Array.isArray(reading?.status)?reading.status.filter(item=>item&&typeof item==="object"):[],specs=[...(Array.isArray(device?.status_spec)?device.status_spec:[]),...(Array.isArray(device?.functions)?device.functions:[])].filter(item=>item&&typeof item==="object");
  const mapRows=Array.isArray(device?.dps_knowledge?.dps)?device.dps_knowledge.dps:[],kinds=[{key:"voltage",label:"Tensão",unit:"V",semantics:["voltage","voltage_phase_a","voltage_phase_b","voltage_phase_c"],match:/(^|_)(cur_)?voltage($|_)/i},{key:"current",label:"Corrente",unit:"A",semantics:["current","current_phase_a","current_phase_b","current_phase_c"],match:/(^|_)(cur_)?current($|_)/i},{key:"power",label:"Potência",unit:"W",semantics:["power","active_power","active_power_phase_a","active_power_phase_b","active_power_phase_c"],match:/(^|_)(cur_)?(active_)?power($|_)/i},{key:"daily_energy",label:"Consumo diário",unit:"kWh",semantics:["daily_accumulated_energy","daily_energy"],match:/(^|_)(daily_energy|today_energy|energy_today)($|_)/i},{key:"incremental_energy",label:"Energia incremental",unit:"kWh",semantics:["energy_incremental"],match:/(^|_)(add_ele|energy_incremental)($|_)/i},{key:"total_energy",label:"Energia acumulada",unit:"kWh",semantics:["total_energy","energy_total","accumulated_energy"],match:/(^|_)(total_energy|energy_total|accumulated_energy)($|_)/i},{key:"energy_import",label:"Energia importada",unit:"kWh",semantics:["energy_import"],match:/(^|_)energy_import($|_)/i},{key:"energy_export",label:"Energia exportada",unit:"kWh",semantics:["energy_export"],match:/(^|_)energy_export($|_)/i},{key:"energy_session",label:"Energia da sessão",unit:"kWh",semantics:["energy_session"],match:/(^|_)energy_session($|_)/i}];
  return kinds.flatMap(kind=>{
    const definitions=mapRows.filter(item=>kind.semantics.includes(item?.semantic_code)&&(item?.confidence==="OWNER_CUSTOM"||item?.confidence==="CONFIRMED"||item?.confidence==="SCHEMA_INFERRED"||item?.validation_status==="category_reference_product_schema_resolved")),mapped=definitions.map(definition=>({definition,entry:status.find(item=>Number(item?.dps_id??item?.dp_id??item?.dpId)===Number(definition.dps_id)||definition.function_code&&item?.code===definition.function_code)})).find(item=>item.entry),fallback=status.map(entry=>({entry,definition:null})).find(({entry})=>{const spec=specs.find(candidate=>candidate.code===entry.code),text=`${entry.code||""} ${spec?.name||""} ${device?.capability_labels?.[entry.code]||""}`;return kind.match.test(text);}),selected=mapped||fallback,entry=selected?.entry,definition=selected?.definition;
    if(!entry||entry.value==null||typeof entry.value==="boolean"||!Number.isFinite(Number(entry.value)))return [];
    const meta=tuyaMetricSchema(device,entry.code),units={voltage:{v:1,volt:1,volts:1,mv:.001},current:{a:1,amp:1,amps:1,ma:.001},power:{w:1,watt:1,watts:1,kw:1000},daily_energy:{kwh:1,wh:.001},incremental_energy:{kwh:1,wh:.001},total_energy:{kwh:1,wh:.001},energy_import:{kwh:1,wh:.001},energy_export:{kwh:1,wh:.001},energy_session:{kwh:1,wh:.001}}[kind.key],unitFactor=definition?.unit?units?.[String(definition.unit).toLowerCase()]:units?.[meta.unit],schemaScale=definition?.confidence==="SCHEMA_INFERRED"||definition?.validation_status==="category_reference_product_schema_resolved",scale=definition&&Number.isFinite(Number(definition.scale))?(schemaScale?10**Number(definition.scale):Number(definition.scale)):10**meta.scale;
    if(definition&&(!definition.unit||!Number.isFinite(scale)||scale<=0))return [];
    if(unitFactor==null)return [];
    const value=Number(entry.value)/(scale||1)*unitFactor,unit=kind.key.includes("energy")?"kWh":kind.unit;
    const stale=reading.connection_state!=="local_responded"||sampleAge>15_000;
    return [{label:kind.label,value:`${new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(value)} ${unit}${stale?" · última leitura":""}`,code:entry.code,stale}];
  });
}
function tuyaDeviceWithPidMap(device){
  if(!device||typeof device!=="object"||!device.product_id)return device;
  const profile=(state.smartProductCatalog||[]).find(item=>String(item?.product_id||"")===String(device.product_id));
  if(!profile)return device;
  const rows=Array.isArray(profile.dps)?profile.dps.filter(row=>row&&Number.isInteger(Number(row.dps_id))&&Number(row.dps_id)>0):[];
  if(!rows.length)return device;
  const functions=(device.functions||[]).map(item=>({...item})),statuses=(device.status_spec||[]).map(item=>({...item})),localMap={...(device.local_dps_map||{})},schemaById=new Map();
  for(const row of rows){
    const id=Number(row.dps_id),source=row.source_kind||row.source||row.origin,code=String(row.function_code||row.code||"");
    if(!code||!Number.isInteger(id)||id<1)continue;
    const target=source==="function"?functions:source==="status"?statuses:null;
    if(!target)continue;
    const spec=target.find(item=>item.code===code);
    if(spec){spec.dp_id=id;spec.dpId=id;if(spec.values==null&&row.values!=null)spec.values=row.values;}
    let values=spec?.values||row.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}
    if(values&&typeof values==="object")schemaById.set(id,{unit:values.unit,scale:values.scale,values});
    if(source==="function")localMap[code]=String(id);
  }
  const knowledgeRows=new Map((device.dps_knowledge?.dps||[]).map(row=>[Number(row.dps_id),{...row}]));
  for(const row of rows){
    const id=Number(row.dps_id),previous=knowledgeRows.get(id)||{};
    const code=String(row.function_code||row.code||previous.function_code||"").toLowerCase();
    const semantic=row.semantic_code||({cur_voltage:"voltage",voltage:"voltage",cur_current:"current",current:"current",cur_power:"power",active_power:"power",power:"power",energy_today:"daily_accumulated_energy",today_energy:"daily_accumulated_energy",add_ele:"energy_incremental",total_forward_energy:"total_energy",countdown:"countdown",countdown_1:"countdown",relay_status:"relay_status",child_lock:"child_lock",switch:"switch",switch_1:"switch",switch_led:"switch"})[code];
    const schema=schemaById.get(id)||{};
    knowledgeRows.set(id,{...previous,...row,dps_id:id,function_code:row.function_code||row.code||previous.function_code,
      display_name:row.display_name||row.description||previous.display_name||row.function_code||row.code||`DPS ${id}`,semantic_code:semantic||previous.semantic_code,
      confidence:row.confidence||previous.confidence||(semantic?"SCHEMA_INFERRED":undefined),unit:row.unit??previous.unit??schema.unit,scale:row.scale??previous.scale??schema.scale,values:row.values||previous.values||schema.values});
  }
  const profileRows=new Map((device.product_profile?.dps||[]).map(row=>[Number(row.dps_id),{...row}]));
  for(const row of rows){const id=Number(row.dps_id);profileRows.set(id,{...profileRows.get(id),...row,dps_id:id,function_code:row.function_code||row.code||profileRows.get(id)?.function_code});}
  return {...device,functions,status_spec:statuses,local_dps_map:localMap,
    switch_channels:[...new Set([...(device.switch_channels||[]),...functions.filter(item=>/^switch(?:_[1-9]\d*)?$/i.test(String(item.code||""))&&["bool","boolean"].includes(String(item.type||"").toLowerCase())).map(item=>item.code)])],
    dps_knowledge:{...(device.dps_knowledge||{}),dps:[...knowledgeRows.values()]},
    product_profile:{...(device.product_profile||{}),dps:[...profileRows.values()]}};
}
function tuyaBreakerMetricFallback(device,reading){
  const observedAt=tuyaReadingTimestamp(reading);
  if(observedAt&&Date.now()-observedAt>15_000)return "Sem leitura recente há mais de 15 s";
  return "Sem leitura DPS mapeada";
}
async function openFavoriteDialog(){
  if(sessionInfo().authenticated&&sessionInfo().user?.role==="owner")await refreshShellyInventoryStatus({quiet:true});
  const devices=[...(state.equipment||[]).map(device=>({id:device.id,name:device.name,kind:"equipment",category:device.category})),...(state.tuyaDevices||[]).map(device=>({id:device.device_id,name:device.name,kind:"tuya",category:"Tuya / MOES"})),...(state.shellyDevices||[]).filter(device=>!String(device.device_id||"").startsWith("shelly-blu:")).map(device=>({id:device.device_id,name:device.name||device.model,kind:"shelly",category:"Shelly"}))];
  const favorites=workspace.prefs.favoriteDeviceIds||[], available=devices.filter((device,index)=>!favorites.includes(device.id)&&devices.findIndex(other=>other.id===device.id)===index);
  const owner=sessionInfo().authenticated&&sessionInfo().user?.role==="owner";
  const dialog=document.createElement("dialog"); dialog.className="home-device-dialog"; dialog.innerHTML=`<form method="dialog" class="home-device-dialog-card"><button class="home-dialog-close" aria-label="Fechar">×</button><p class="eyebrow">DISPOSITIVOS FAVORITOS</p><h2>Adicionar dispositivo</h2><div class="home-device-actions"><button type="button" class="button secondary" id="home-existing-device">Adicionar favorito existente</button>${owner?`<button type="button" class="button primary" id="home-new-device">Configurar novo Tuya / MOES</button>`:""}</div><div id="home-favorite-existing" hidden><label>Dispositivo registado no Gateway<select id="home-favorite-select"><option value="">Escolher dispositivo…</option>${available.map(device=>`<option value="${esc(device.id)}">${esc(device.name)} · ${esc(device.category||device.kind)}</option>`).join("")}</select></label><label>Divisão<input id="home-favorite-room" maxlength="80" placeholder="Sala de estar"></label><label>Piso<input id="home-favorite-floor" maxlength="80" placeholder="Rés-do-chão"></label><button type="button" class="button primary" id="home-add-existing">Adicionar aos meus favoritos</button></div>${owner?`<div id="home-favorite-new" hidden><label>ID do dispositivo Tuya<input id="home-new-id" maxlength="128" autocomplete="off"></label><label>Nome<input id="home-new-name" maxlength="120" placeholder="Luz do teto"></label><label>IP local<input id="home-new-ip" maxlength="64" placeholder="192.168.8.85" inputmode="decimal"></label><label>MAC local<input id="home-new-mac" maxlength="17" placeholder="AA:BB:CC:11:22:33" autocapitalize="characters" spellcheck="false"></label><label>Tipo<select id="home-new-kind"><option value="switch">Interruptor / disjuntor</option><option value="dimmer">Luz regulável</option><option value="blind">Estore / persiana</option><option value="ev_charger">Carregador EV</option></select></label><label>Código ON/OFF (opcional)<input id="home-new-switch-code" maxlength="64" placeholder="switch_1"></label><label>Código de nível / posição<input id="home-new-level-code" maxlength="64" placeholder="bright_value ou position"></label><div class="home-level-range"><label>Valor mínimo Tuya<input id="home-new-level-min" type="number" min="0" max="99999" value="0"></label><label>Valor máximo Tuya<input id="home-new-level-max" type="number" min="1" max="100000" value="100"></label></div><label>Divisão<input id="home-new-room" maxlength="80" placeholder="Sala de estar"></label><label>Piso<input id="home-new-floor" maxlength="80" placeholder="Rés-do-chão"></label><button type="button" class="button primary" id="home-register-device">Guardar no Gateway e testar LAN</button></div>`:""}<p id="home-device-dialog-status" role="status"></p></form>`;
  $("#page-content").append(dialog); dialog.addEventListener("close",()=>{dialog.remove();render();}); dialog.showModal();
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
    const updated = state.lastUpdated ? `Atualizado ${currentTimeLabel(state.lastUpdated)}` : "À espera de leituras";
    return `<div class="page-heading home-page-heading"><div><p class="eyebrow">ENERGIA DA PROPRIEDADE</p><h1>Home</h1></div><div class="date-block"><strong>${esc(state.dataStatus)}</strong><br>${esc(updated)}</div></div><div class="home-weather-row">${renderHomeWeatherCard()}${renderHomeProductionCard()}</div>
      <section class="panel home-favorites"><div class="favorite-heading"><div><p class="eyebrow">CONTROLO RÁPIDO</p><h2>Dispositivos favoritos</h2></div></div>${favoriteDeviceCards()}</section>
      <div class="metric-grid">${liveSolarHomeMetric()}${liveBatteryHomeMetric()}${liveMinerHomeMetric()}${liveReadingMetric("Veículo elétrico", "ev", "↗")}</div>
      `;
  }
  const totals = demoTotals();
  const allCards = state.equipment.map(card).join("") || `<div class="empty-state">Ainda não existem equipamentos configurados no Gateway.</div>`;
  const sky = skyData();
  return `${renderHomePreferenceLinks()}
  <div class="reference-home-grid"><button type="button" class="reference-card weather-card" id="open-weather"><span class="label">CLIMA · SIMULADO</span><strong class="reference-big" id="weather-temperature">${sky.temp}</strong><span class="weather-condition"><b id="weather-icon">${sky.icon}</b><span><strong id="weather-label">${sky.label}</strong><small id="weather-feels">Sensação ${sky.feel}</small></span></span><span class="weather-chip" id="weather-chip">${sky.label}</span></button><button type="button" class="reference-card production-card" id="open-production"><span class="label">PRODUÇÃO <small>detalhe ↗</small></span><strong class="production-value">4,2 <small>kW</small></strong><span class="label">AGORA · ${esc(sky.label.toUpperCase())}</span>${miniChart()}<span class="reference-demo-note">CURVA SIMULADA</span></button>
  <section class="reference-card favorite-card full"><div class="favorite-heading"><span class="label">DISPOSITIVOS FAVORITOS</span><span class="local-tag">LOCAL ONLY</span></div><div class="favorite-device-grid">${favoriteDeviceCards()}</div><p class="control-footnote">Controlos cenográficos: alteram apenas esta interface, sem ligação a dispositivos.</p></section></div>
  <div class="section-heading"><div><p class="eyebrow">RESUMO DO SISTEMA</p><h2>O seu balanço energético</h2></div><span class="live-label"><i></i>${state.mode === "SIMULATED" ? "DADOS SIMULADOS" : `${esc(state.dataStatus)} · GATEWAY`}</span></div>
  <div class="metric-grid">${metric("Produção solar", totals.solar, "kW", "ϟ", state.mode === "SIMULATED" ? "Exemplo · não é leitura real" : "Última leitura disponível")}${metric("Carga da bateria", totals.battery, "%", "▤", state.mode === "SIMULATED" ? "Valor ilustrativo" : "Última leitura disponível")}${metric("Consumo mineradoras", totals.miner, "kW", "▦", state.mode === "SIMULATED" ? "Valor ilustrativo" : "Última leitura disponível")}${metric("Carregamento EV", totals.ev, "kW", "↗", state.mode === "SIMULATED" ? "Sem ligação física" : "Última leitura disponível")}</div>
  <div class="content-grid"><section class="panel chart-panel"><div class="panel-header"><div><p class="eyebrow">FLUXO DE ENERGIA</p><h2>Produção ao longo do dia</h2><p>${state.mode === "SIMULATED" ? "Curva visual fictícia para explorar o design" : "Histórico indisponível no contrato API atual"}</p></div><span class="source-tag">${state.mode === "SIMULATED" ? "SIMULATED" : esc(state.dataStatus)}</span></div>${chart()}<div class="legend"><span><i></i>Produção solar</span><span><i class="blue-dot"></i>Consumo total</span></div></section><section class="panel flow-panel"><div class="panel-header"><div><p class="eyebrow">ESTADO ATUAL</p><h2>Onde está a energia</h2></div><button class="text-link" data-page="baterias">Ver sistema ↗</button></div>${flowPanel()}</section></div>
  <div class="section-heading section-heading-spaced"><div><p class="eyebrow">SEIS ÁREAS INTEGRADAS</p><h2>Explore a sua instalação</h2></div><span class="muted-inline">${state.equipment.length} perfis · ${state.mode}</span></div><div class="equipment-grid">${allCards}</div>
  ${state.mode === "SIMULATED" ? `<section class="panel demo-shortcuts"><div><p class="eyebrow">EXPERIMENTE</p><h2>Configure cenários sem risco</h2><p>Entre em qualquer área para experimentar os controlos locais. Os valores não são enviados para o Gateway.</p></div><button class="button secondary" data-page="ev">Experimentar controlos <span>↗</span></button></section>` : ""}`;
}
function renderHomePhotoHero(menuTitle = "Home") {
  const photo = state.siteProfile?.photo_data_url || "";
  const photoStyle = photo ? "has-property-photo" : "photo-placeholder";
  const owner = sessionInfo().authenticated && sessionInfo().user?.role === "owner";
  const opacity=Math.max(0,Math.min(1,Number(state.siteProfile?.photo_opacity??0.38)));
  const imageStyle = photo ? ` style="--property-photo-opacity:${opacity};--property-position-x:${Number(state.siteProfile?.photo_position_x??50)}%;--property-position-y:${Number(state.siteProfile?.photo_position_y??50)}%;--property-zoom:${Number(state.siteProfile?.photo_zoom??1)};--property-vignette:${Number(state.siteProfile?.photo_vignette??.35)}"` : "";
  return `<section class="property-hero ${photoStyle} live-property-hero shared-property-hero" id="property-hero" aria-label="${esc(menuTitle)} · ${esc(state.propertyName || workspace.house.name || "Solar Energy")}"${imageStyle}>${photo?`<img class="property-hero-image" src="${esc(photo)}" alt="" aria-hidden="true">`:""}<div class="hero-shade"></div><div class="hero-content"><div><p class="shared-property-name">${esc(menuTitle)}</p><h1 class="home-property-name">${esc(state.propertyName || workspace.house.name || "Solar Energy")}</h1></div></div>${owner?`<button class="home-edit-trigger" id="hero-photo-settings" type="button" aria-label="Editar nome, localização e fotografia da propriedade" title="Editar propriedade">✎</button>`:""}</section>`;
}
function weatherConditionLabel(code) {
  const labels = {0:"Céu limpo",1:"Maioritariamente limpo",2:"Parcialmente nublado",3:"Encoberto",45:"Nevoeiro",48:"Nevoeiro com geada",51:"Chuvisco ligeiro",53:"Chuvisco moderado",55:"Chuvisco intenso",56:"Chuvisco gelado ligeiro",57:"Chuvisco gelado intenso",61:"Chuva ligeira",63:"Chuva moderada",65:"Chuva intensa",66:"Chuva gelada ligeira",67:"Chuva gelada intensa",71:"Neve ligeira",73:"Neve moderada",75:"Neve intensa",77:"Grãos de neve",80:"Aguaceiros ligeiros",81:"Aguaceiros moderados",82:"Aguaceiros violentos",85:"Queda de neve ligeira",86:"Queda de neve intensa",95:"Trovoada",96:"Trovoada com granizo ligeiro",99:"Trovoada com granizo intenso"};
  return Number.isInteger(code) ? (labels[code] || "Condição indisponível") : "Condição indisponível";
}
function weatherIcon(code){
  const n=Number(code),sun='<circle class="weather-sun-core" cx="17" cy="17" r="6"/><path class="weather-sun-rays" d="M17 4v3m0 20v3M4 17h3m20 0h3M7.8 7.8l2.1 2.1m14.2 14.2 2.1 2.1m0-16.4-2.1 2.1M9.9 24.1l-2.1 2.1"/>',cloud='<path class="weather-cloud" d="M13.1 35h22a7.1 7.1 0 0 0 .6-14.17 11.35 11.35 0 0 0-21.55-.46A7.35 7.35 0 0 0 13.1 35Z"/>';
  let kind="cloudy",art=cloud;
  if(n===0){kind="clear";art=sun;}
  else if(n===1||n===2){kind="partly-cloudy";art=`${sun}${cloud}`;}
  else if(n===45||n===48){kind="fog";art=`${cloud}<path class="weather-fog-line" d="M8 39h32M13 44h25"/>`;}
  else if(n>=95){kind="storm";art=`${cloud}<path class="weather-lightning" d="m25 29-6 9h6l-2 8 9-12h-7l3-5Z"/>`;}
  else if(n>=71&&n<=77||n===85||n===86){kind="snow";art=`${cloud}<circle class="weather-snowflake" cx="15" cy="42" r="1.8"/><circle class="weather-snowflake" cx="25" cy="44" r="1.8"/><circle class="weather-snowflake" cx="35" cy="41" r="1.8"/>`;}
  else if(n>=51&&n<=67||n>=80&&n<=82){kind="rain";art=`${cloud}<path class="weather-rain-line" d="m16 39-2 5m12-5-2 5m12-5-2 5"/>`;}
  return `<svg class="weather-condition-icon weather-icon-${kind}" viewBox="0 0 48 48" aria-hidden="true">${art}</svg>`;
}
function renderHomeWeatherCard() {
  const weather = state.energyEngine?.forecast?.weather, current = weather?.current;
  const temperature = Number.isFinite(current?.temperature_c) ? `${Number(current.temperature_c).toLocaleString("pt-PT", {maximumFractionDigits:1})} °C` : "— °C";
  const condition = current ? weatherConditionLabel(current.weather_code) : weather?.state === "location_not_configured" ? "Configura a localização" : "A aguardar previsão";
  const details=[];
  if(Number.isFinite(current?.apparent_temperature_c))details.push(`Sensação ${Number(current.apparent_temperature_c).toLocaleString("pt-PT",{maximumFractionDigits:1})} °C`);
  if(Number.isFinite(current?.relative_humidity_percent))details.push(`Humidade ${Math.round(current.relative_humidity_percent)}%`);
  if(Number.isFinite(current?.cloud_cover_percent))details.push(`Nuvens ${Math.round(current.cloud_cover_percent)}%`);
  if(Number.isFinite(current?.wind_speed_kmh))details.push(`Vento ${Number(current.wind_speed_kmh).toLocaleString("pt-PT",{maximumFractionDigits:0})} km/h`);
  return `<article class="home-weather-card" aria-label="Previsão meteorológica do Gateway"><p class="eyebrow">METEOROLOGIA · GATEWAY</p><div class="home-weather-values"><strong>${esc(temperature)}</strong><span class="home-weather-condition">${weatherIcon(current?.weather_code)}<span>${esc(condition)}</span></span></div><p class="home-weather-details">${details.length?details.map(esc).join(" · "):"Sem detalhes meteorológicos disponíveis"}</p></article>`;
}
function renderHomeProductionCard() {
  const engine=state.energyEngine||{},current=engine.current||{},raw=Number(current.pv_power_w);
  const power=Number.isFinite(raw)?`${(raw/1000).toLocaleString("pt-PT",{minimumFractionDigits:2,maximumFractionDigits:2})} kW`:"— kW";
  const cutoff=Date.now()-3*60*60*1000;
  const samples=new Map(),addSeries=(field,key)=>{for(const item of engine.history?.[field]||[]){const stamp=Date.parse(item.observed_at),value=Number(item.value);if(!Number.isFinite(stamp)||stamp<cutoff||!Number.isFinite(value))continue;const minute=Math.round(stamp/60000),point=samples.get(minute)||{};point[key]=value/(item.unit==="W"?1000:1);samples.set(minute,point);}};
  addSeries("pv_total_power","pv");addSeries("load_total_power","load");
  const points=[...samples.entries()].sort((a,b)=>a[0]-b[0]).map(([,point])=>point).filter(point=>Number.isFinite(point.pv)&&Number.isFinite(point.load));
  const max=Math.max(.1,...points.flatMap(point=>[point.pv,point.load]).filter(Number.isFinite)),x=index=>points.length>1?Math.round(index/(points.length-1)*236)+2:120,y=value=>48-Math.max(0,value)/max*40;
  const seriesPath=key=>points.map((point,index)=>Number.isFinite(point[key])?`${index?"L":"M"}${x(index)} ${y(point[key])}`:"").filter(Boolean).join(" ");
  const areaPath=key=>{const coords=points.map((point,index)=>({x:x(index),y:y(point[key])})),last=coords[coords.length-1];return coords.length>1?`M${coords[0].x} 48 L${coords.map(point=>`${point.x} ${point.y}`).join(" L")} L${last.x} 48 Z`:"";};
  const surplusPath=()=>{const pieces=[];for(let i=0;i<points.length-1;i++){const a=points[i],b=points[i+1];if(![a.pv,a.load,b.pv,b.load].every(Number.isFinite))continue;let x1=x(i),x2=x(i+1),p1=y(a.pv),p2=y(b.pv),l1=y(a.load),l2=y(b.load),d1=a.pv-a.load,d2=b.pv-b.load;if(d1<=0&&d2<=0)continue;if(d1*d2<0){const ratio=d1/(d1-d2),crossX=x1+(x2-x1)*ratio,crossY=p1+(p2-p1)*ratio;if(d1>0){x2=crossX;p2=crossY;l2=crossY;}else{x1=crossX;p1=crossY;l1=crossY;}}pieces.push(`M${x1} ${p1} L${x2} ${p2} L${x2} ${l2} L${x1} ${l1} Z`);}return pieces.join(" ");};
  const load=Number(current.load_power_w),loadText=Number.isFinite(load)?`${(load/1000).toLocaleString("pt-PT",{minimumFractionDigits:2,maximumFractionDigits:2})} kW`:"— kW";
  return `<article class="home-production-card" aria-label="Produção solar e carga UPS"><p class="eyebrow">PRODUÇÃO</p><strong class="home-production-value">${esc(power)}</strong><div class="home-production-load"><span>CARGA · UPS</span><strong>${esc(loadText)}</strong></div>${points.length>1?`<svg class="home-production-chart" viewBox="0 0 240 54" role="img" aria-label="Produção solar dourada, carga UPS branca, área colorida entre ambas para o excedente"><path class="pv-area" d="${areaPath("pv")}"/><path class="load-area" d="${areaPath("load")}"/><path class="surplus-area" d="${surplusPath()}"/><path class="pv-trend" d="${seriesPath("pv")}"/><path class="load-trend" d="${seriesPath("load")}"/></svg>`:`<div class="home-production-chart-empty">${points.length?"A recolher tendência":"À espera de histórico do Gateway"}</div>`}</article>`;
}
function renderCategory(categoryId) {
  const category = CATEGORIES.find(c => c.id === categoryId);
  const equipment = state.equipment.filter(item => item.category === categoryId);
  const item = equipment[0];
  const reading = item ? formatReading(preferredGatewayReading(item)) : {value:"—",unit:"",valid:false};
  return `<div class="page-heading"><div><p class="eyebrow">A SUA PROPRIEDADE / ÁREAS</p><h1>${esc(category.label)}</h1><p>${esc(category.description)}. Explore os dados e o cenário associado.</p></div><div class="date-block"><strong>${equipment.length ? "Perfil demonstrativo" : "Sem perfil"}</strong><br>${state.mode}</div></div>
  ${state.mode === "SIMULATED" ? `<div class="status-banner demo-banner"><span class="demo-stamp">DEMO</span><span>Perfil ilustrativo, sem ligação física. Os valores não são leituras reais e os controlos abaixo só alteram a interface local.</span></div>` : state.dataStatus !== "LIVE" ? `<div class="status-banner demo-banner"><span class="demo-stamp">${esc(state.dataStatus)}</span><span>${state.dataStatus === "STALE" ? "A última leitura é antiga e não deve ser tratada como estado atual." : state.dataStatus === "UNKNOWN" ? "O Gateway respondeu, mas não existe uma leitura válida para este equipamento." : "A consulta ao Gateway não confirmou dados atuais."}</span></div>` : ""}
  <div class="category-feature"><div class="category-feature-icon">${esc(category.icon)}</div><div class="category-feature-main"><p class="eyebrow">${esc(category.label.toUpperCase())}</p><h2>${esc(item?.name || "Perfil por configurar")}</h2><p>${esc(item ? [item.manufacturer,item.model].filter(Boolean).join(" · ") : "O Gateway ainda não disponibiliza um equipamento nesta área.")}</p></div><div class="category-feature-value"><strong>${esc(reading.value)} <small>${esc(reading.unit)}</small></strong><span>${state.mode === "SIMULATED" ? "VALOR SIMULADO" : reading.valid ? "LEITURA DO GATEWAY" : "SEM LEITURA"}</span></div></div>
  ${demoControlPanel(categoryId)}
  <div class="section-heading section-heading-spaced"><div><p class="eyebrow">DETALHE</p><h2>Estado e proveniência</h2></div><span class="source-tag">${state.mode}</span></div>
  ${equipment.length ? equipment.map(item=>`<section class="panel detail-panel"><div class="panel-header"><div><h2>${esc(item.name)}</h2><p>Informação de origem e estado</p></div><span class="source-tag">${isSimulated(item)?"SIMULATED":esc(item.readings?.[0]?.trust||"UNKNOWN")}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Fabricante / modelo</small><strong>${esc([item.manufacturer,item.model].filter(Boolean).join(" · ")||"Não definido")}</strong></div><div class="detail-item"><small>Ligação</small><strong>${esc(item.category==="mineradoras"?(equipmentConnectionIsLive(item)?"CONNECTED":"DISCONNECTED · leitura desatualizada"):(item.connection_state||"UNKNOWN"))}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(timeLabel(item.last_communication_at))}</strong></div><div class="detail-item"><small>Origem</small><strong>${esc(item.source||item.readings?.[0]?.source||"API_GATEWAY")}</strong></div><div class="detail-item"><small>Confiança</small><strong>${esc(item.readings?.[0]?.trust||"UNKNOWN")}</strong></div><div class="detail-item"><small>Leitura principal</small><strong>${esc(reading.value)} ${esc(reading.unit)}</strong></div></div><div class="status-banner demo-banner"><span class="demo-stamp">INFO</span><span>Leituras registadas pelo Gateway. Valores Deye identificados como LIVE_UNVERIFIED até validação adicional do modelo e logger.</span></div>${item.readings?.length ? `<div class="device-detail-grid telemetry-grid">${item.readings.map(value=>`<div class="detail-item"><small>${esc(value.evidence?.label || value.field)}</small><strong>${esc(formatReading(value).value)} ${esc(value.unit || "")}</strong><small>${esc(value.field)}${value.evidence?.register ? ` · registo ${esc(value.evidence.register)}` : ""}</small></div>`).join("")}</div>` : ""}</section>`).join("") : `<div class="empty-state">Não existem equipamentos nesta área no Gateway. Nenhum valor foi inventado.</div>`}`;
}
function renderBatteryBankRow(bank={},index=0){
  const id=bank.id||`battery-bank-${index+1}`;
  return `<div class="battery-bank-row ws-config-grid" data-battery-bank-row><label class="feature-field">Nome do banco<input data-bank-name value="${esc(bank.name||`Banco ${index+1}`)}" maxlength="120"></label><label class="feature-field">Capacidade nominal (kWh)<input data-bank-capacity type="number" min="0.1" max="10000" step="0.1" value="${esc(bank.capacity_kwh??"")}"></label><label class="battery-bank-online"><input data-bank-active type="checkbox" ${bank.active!==false?"checked":""}> Banco online</label><input data-bank-id type="hidden" value="${esc(id)}"><button class="button subtle" type="button" data-battery-bank-remove>Remover</button></div>`;
}
function renderBatteryBankDialog(){
  return `<dialog id="area-battery-bank-dialog" class="settings-dialog" aria-labelledby="area-battery-bank-title"><form id="area-battery-bank-form" class="settings-form" novalidate><div class="dialog-header"><div><p class="eyebrow">CONFIGURAÇÃO OWNER · GATEWAY</p><h2 id="area-battery-bank-title">Adicionar banco</h2></div></div><label class="ws-field">Nome do banco<input id="area-battery-bank-name" maxlength="120" required></label><label class="ws-field">Capacidade nominal (kWh)<input id="area-battery-bank-capacity" type="number" min="0.1" max="10000" step="0.1" required></label><label class="battery-bank-online"><input id="area-battery-bank-active" type="checkbox"> Banco online</label><input id="area-battery-bank-id" type="hidden"><p id="area-battery-bank-status" class="field-note" role="status" aria-live="polite"></p><div class="dialog-actions"><button class="button danger" id="area-battery-bank-delete" type="button" hidden>Remover</button><span class="dialog-actions-spacer"></span><button class="button secondary" type="button" data-battery-bank-close>Cancelar</button><button class="button primary" id="area-battery-bank-save" type="button">Adicionar</button></div></form></dialog>`;
}
function openBatteryBankDialog(bank=null,index=0){
  const dialog=$("#area-battery-bank-dialog");if(!dialog)return;
  const editing=Boolean(bank);
  $("#area-battery-bank-title").textContent=editing?`Editar ${bank.name||`Banco ${index+1}`}`:"Adicionar banco";
  $("#area-battery-bank-name").value=bank?.name||`Banco ${(state.energyEngine?.configuration?.battery_banks||[]).length+1}`;
  $("#area-battery-bank-capacity").value=bank?.capacity_kwh??"";
  $("#area-battery-bank-active").checked=bank?.active===true;
  $("#area-battery-bank-id").value=bank?.id||"";
  $("#area-battery-bank-status").textContent="";
  $("#area-battery-bank-delete").hidden=!editing;
  $("#area-battery-bank-save").textContent=editing?"Guardar":"Adicionar";
  dialog.dataset.mode=editing?"edit":"add";
  if(!dialog.open)dialog.showModal();
  $("#area-battery-bank-name").focus();
}
function renderPvStringDialog(){
  return `<dialog id="pv-string-dialog" class="settings-dialog"><form id="pv-string-form" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">CONFIGURAÇÃO FV · GATEWAY</p><h2 id="pv-string-title">Adicionar string</h2></div><button type="button" class="icon-button" data-pv-string-close aria-label="Fechar">×</button></div><label>Nome da string<input name="name" maxlength="120" required></label><label>Fabricante<input name="manufacturer" maxlength="120" required></label><div class="ws-config-grid"><label>Número de painéis<input name="panel_count" type="number" min="1" max="2000" step="1" required></label><label>Potência por painel (W)<input name="panel_power_w" type="number" min="1" max="2500" step="1" required></label></div><label>Entrada<select name="mppt"><option value="1">MPPT 1</option><option value="2">MPPT 2</option></select></label><label><input name="active" type="checkbox" checked> String online</label><input name="id" type="hidden"><p class="field-note" id="pv-string-total-power" aria-live="polite">Potência total calculada: —</p><p class="field-note" id="pv-string-status" role="status"></p><div class="dialog-actions"><button type="button" class="button danger" id="pv-string-remove" hidden>Remover</button><span class="dialog-actions-spacer"></span><button type="button" class="button secondary" data-pv-string-close>Cancelar</button><button type="submit" class="button primary" disabled>Guardar</button></div></form></dialog>`;
}
function renderAqsDialog(){
  const devicesById=new Map();
  for(const device of state.tuyaDevices||[]){
    if(!device?.device_id||devicesById.has(device.device_id))continue;
    const channels=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase())&&typeof item.code==="string");
    const channel=channels.find(item=>item.code===device.switch_code)
      ||(channels.length===1?channels[0]:channels.find(item=>["switch","switch_1"].includes(item.code)));
    if(channel)devicesById.set(device.device_id,{device,channel});
  }
  const channels=[...devicesById.values()];
  return `<dialog id="aqs-dialog" class="settings-dialog"><form id="aqs-form" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">EQUIPAMENTO · AQS</p><h2 id="aqs-title">Adicionar AQS</h2></div><button type="button" class="icon-button" data-aqs-close aria-label="Fechar">×</button></div><label>Nome<input name="name" maxlength="120" required placeholder="Ex.: Termoacumulador"></label><label>Fabricante<input name="manufacturer" maxlength="120" required></label><div class="ws-config-grid"><label>Volume (litros)<input name="volume_l" type="number" min="1" max="100000" step="1" required></label><label>Potência nominal (W)<input name="rated_power_w" type="number" min="1" max="100000" step="1" required></label></div><label>Disjuntor Tuya associado<select name="tuya_binding"><option value="">Sem associação</option>${channels.map(({device,channel})=>`<option value="${esc(device.device_id)}|${esc(channel.code)}">${esc(device.name)}</option>`).join("")}</select></label><p class="field-note">A associação guarda o dispositivo selecionado e o seu canal de controlo principal. Não liga nem desliga o disjuntor.</p><input name="id" type="hidden"><p class="field-note" id="aqs-status" role="status"></p><div class="dialog-actions"><button type="button" class="button danger" id="aqs-remove" hidden>Remover</button><span class="dialog-actions-spacer"></span><button type="button" class="button secondary" data-aqs-close>Cancelar</button><button type="submit" class="button primary" disabled>Guardar</button></div></form></dialog>`;
}
function renderPvStringsSection(config,isOwner){
  const strings=Array.isArray(config.pv_strings)?config.pv_strings:[];
  const activeStrings=strings.filter(item=>item.active!==false);
  const activeCapacityKw=activeStrings.reduce((sum,item)=>{const configured=Number(item.nominal_power_kw),derived=Number(item.panel_count)*Number(item.panel_power_w)/1000;return sum+(Number.isFinite(configured)&&configured>0?configured:Number.isFinite(derived)&&derived>0?derived:0);},0);
  return `<section class="panel detail-panel pv-strings-panel"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO FV · GATEWAY</p><h2>Strings fotovoltaicas</h2></div>${isOwner?`<button class="button primary" id="pv-string-add" type="button">+ Adicionar string</button>`:""}</div><p class="field-note">A potência nominal total é calculada pelo número de painéis e pela potência de cada painel. O estado online/offline é a configuração da string.</p><div class="device-detail-grid pv-string-summary"><div class="detail-item"><small>Potência nominal ativa</small><strong>${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(activeCapacityKw))} kWp</strong><small>${activeStrings.length} de ${strings.length} strings online</small></div><div class="detail-item"><small>Strings registadas</small><strong>${strings.length}</strong><small>Guardadas na configuração do Gateway</small></div></div>${strings.length?`<div class="equipment-grid pv-string-grid">${strings.map((item,index)=>`<button class="detail-item pv-string-card" type="button" data-pv-string-edit="${esc(item.id)}" aria-label="${esc(item.name)}, MPPT ${item.mppt}, ${item.active===false?"offline":"online"}; duplo clique para editar"><small>${esc(item.name)}</small><strong>MPPT ${esc(item.mppt)} · ${item.active===false?"OFFLINE":"ONLINE"}</strong><span>${esc(item.manufacturer||"Fabricante não indicado")} · ${Number(item.panel_count)||0} painéis × ${Number(item.panel_power_w)||0} W</span><span>${Number(item.nominal_power_kw)>0?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(Number(item.nominal_power_kw)))} kWp total`:"Potência nominal por indicar"}</span><span>Duplo clique para editar</span></button>`).join("")}</div>`:`<div class="empty-state">Ainda não há strings registadas.${isOwner?" Adiciona uma para identificar fabricante, painéis, MPPT e estado.":""}</div>`}${isOwner?renderPvStringDialog():""}</section>`;
}
function renderAqsSection(config,isOwner){
  const loads=(Array.isArray(config.loads)?config.loads:[]).filter(item=>item.kind==="water_heater");
  const cards=loads.map(item=>{const bound=state.tuyaDevices.find(device=>device.device_id===item.tuya_device_id);const channel=bound?.functions?.find(value=>value.code===item.tuya_switch_code);return `<button class="detail-item aqs-card" type="button" data-aqs-edit="${esc(item.id)}" aria-label="${esc(item.name)}, duplo clique para editar"><small>${esc(item.name)}</small><strong>${esc(item.manufacturer||"Fabricante não indicado")} · ${Number(item.volume_l)||0} L</strong><span>${Number(item.rated_power_w)||0} W · ${bound?`${esc(bound.name)} · ${esc(tuyaFriendlyCapabilityLabel(channel||{code:item.tuya_switch_code},bound))}`:"Sem disjuntor associado"}</span><span>${item.enabled===false?"DESATIVADO":"REGISTADO"} · duplo clique para editar</span></button>`;});
  return `<section class="panel detail-panel aqs-management-panel"><div class="panel-header"><div><p class="eyebrow">ÁGUA QUENTE SANITÁRIA</p><h2>Termoacumuladores</h2></div>${isOwner?`<button class="button primary" id="aqs-add" type="button">+ Adicionar AQS</button>`:""}</div><p class="field-note">Cada AQS guarda fabricante, volume, potência nominal e, opcionalmente, um canal de disjuntor Tuya. A configuração não comanda o equipamento.</p>${cards.length?`<div class="equipment-grid aqs-card-grid">${cards.join("")}</div>`:`<div class="empty-state">Ainda não há AQS registadas.${isOwner?" Adiciona uma para configurar os dados e o disjuntor.":""}</div>`}${isOwner?renderAqsDialog():""}</section>`;
}
function renderEvSection(config,isOwner){
  return `<section class="panel detail-panel"><div class="panel-header"><div><p class="eyebrow">VEÍCULO ELÉTRICO · TESLA FLEET</p><h2>Estado e presença do veículo</h2></div><span class="source-tag">${isOwner?"OWNER":"LEITURA"}</span></div><p>A ligação Tesla Fleet é configurada em Owner → Equipamentos → Tesla Fleet. Esta área mostra leituras e presença local; ainda não envia comandos de carregamento.</p><div class="ws-actions">${isOwner?`<button class="button primary" id="ev-tesla-read" type="button">Ler estado do veículo</button>`:""}</div><div class="connection-result" id="ev-tesla-read-status" role="status" aria-live="polite">A leitura Fleet só está disponível ao Owner autenticado.</div>${isOwner?`<div class="ws-actions"><button class="button secondary" id="ev-tesla-presence" type="button">Verificar presença na rede</button></div><div class="connection-result" id="ev-tesla-presence-status" role="status" aria-live="polite">Presença local ainda não consultada.</div><pre id="ev-tesla-result" class="connection-result" hidden></pre>`:`<div class="empty-state">A configuração e leitura Tesla estão disponíveis apenas ao Owner.</div>`}</section>`;
}

function openPvStringDialog(item=null){
  const dialog=$("#pv-string-dialog"),form=$("#pv-string-form");if(!dialog||!form)return;
  dialog.dataset.returnPage=state.page;
  form.elements.name.value=item?.name||`String ${(state.energyEngine?.configuration?.pv_strings||[]).length+1}`;
  form.elements.manufacturer.value=item?.manufacturer||"";form.elements.panel_count.value=item?.panel_count??"";form.elements.panel_power_w.value=item?.panel_power_w??"";
  form.elements.mppt.value=String(item?.mppt||1);
  form.elements.active.checked=item?.active!==false;form.elements.id.value=item?.id||"";
  updatePvStringTotalPower(form);
  updatePvStringSaveButton(form);
  $("#pv-string-title").textContent=item?`Editar ${item.name}`:"Adicionar string";$("#pv-string-remove").hidden=!item;$("#pv-string-status").textContent="";
  dialog.dataset.mode=item?"edit":"add";if(!dialog.open)dialog.showModal();
}
function updatePvStringTotalPower(form){
  const count=Number(form.elements.panel_count.value), watts=Number(form.elements.panel_power_w.value), label=$("#pv-string-total-power");
  if(!label)return;
  label.textContent=Number.isInteger(count)&&count>0&&Number.isFinite(watts)&&watts>0
    ?`Potência total calculada: ${new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(count*watts/1000)} kWp`
    :"Potência total calculada: indica o número de painéis e a potência por painel.";
}
function updatePvStringSaveButton(form){
  const button=form?.querySelector('[type="submit"]');
  if(!button)return;
  const name=form.elements.name.value.trim(),manufacturer=form.elements.manufacturer.value.trim();
  button.disabled=!form.checkValidity()||!name||!manufacturer;
}
function openAqsDialog(item=null){
  const dialog=$("#aqs-dialog"),form=$("#aqs-form");if(!dialog||!form)return;
  dialog.dataset.returnPage=state.page;
  form.elements.name.value=item?.name||"";form.elements.manufacturer.value=item?.manufacturer||"";
  form.elements.volume_l.value=item?.volume_l??"";form.elements.rated_power_w.value=item?.rated_power_w??"";
  form.elements.tuya_binding.value=item?.tuya_device_id&&item?.tuya_switch_code?`${item.tuya_device_id}|${item.tuya_switch_code}`:"";
  form.elements.id.value=item?.id||"";$("#aqs-title").textContent=item?`Editar ${item.name}`:"Adicionar AQS";
  $("#aqs-remove").hidden=!item;$("#aqs-status").textContent="";dialog.dataset.mode=item?"edit":"add";updateAqsSaveButton(form);
  if(!dialog.open)dialog.showModal();
}
function updateAqsSaveButton(form){
  const button=form?.querySelector('[type="submit"]');
  if(!button)return;
  button.disabled=!form.checkValidity()||!form.elements.name.value.trim()||!form.elements.manufacturer.value.trim();
}
const antminerReadOperations=[["api_version","Versão da API"],["details","Identificação e estado"],["errors","Erros do minerador"],["hashboards","Hashboards"],["stats","Estatísticas, hashrate e potência"],["configuration","Configuração geral"],["constraints","Limites suportados"],["cooling","Ventoinhas e temperaturas"],["network_details","Rede e interfaces"],["locate_state","Estado da luz de localização"],["tuner","Potência"],["performance_mode","Modo de desempenho"],["target_profiles","Perfis de potência e hashrate"],["efficiency_profile","Perfil de eficiência"],["pools","Pools e grupos"],["advanced_settings","Definições avançadas"],["advanced_schema","Esquema das definições avançadas"],["network","Configuração de rede"],["auto_upgrade","Atualização automática"],["license","Licença"]];
const antminerReadCategories=[["Estado e atividade","◉",["details","errors","stats","hashboards","cooling","pools"]],["Potência","ϟ",["tuner"]],["Configuração e sistema","⚙",["api_version","configuration","constraints","network_details","network","advanced_settings","auto_upgrade","license","locate_state"]]];
const antminerWriteOperations=[["set_power_target","Potência"],["power_target_default","Potência predefinida"],["power_target_increment","Aumentar potência"],["power_target_decrement","Reduzir potência"],["power_target_relative","Potência relativa"],["set_hashrate_target","Hashrate"],["hashrate_target_default","Hashrate predefinido"],["hashrate_target_increment","Aumentar hashrate"],["hashrate_target_decrement","Reduzir hashrate"],["hashrate_target_relative","Hashrate relativo"],["performance_mode","Modo de desempenho"],["dps","DPS"],["quick_ramping","Rampa rápida"],["quick_ramping_default","Rampa predefinida"],["reset_tuned_profiles","Repor perfis do tuner (reinicia mineração)"],["cooling_mode","Refrigeração"],["advanced_settings","Definições avançadas"],["network","Rede"],["hashboards","Hashboards"],["auto_upgrade","Atualização automática"],["pools_batch","Substituir grupos de pools"],["create_pool_group","Criar grupo de pools"],["update_pool_group","Atualizar grupo de pools"],["delete_pool_group","Apagar grupo de pools"],["locate","Luz de localização"],["api_call","Explorador da API Braiins"]];
async function confirmAntminerAction(title,message){return (await showOperationDialog({title,message,actions:[{label:"Cancelar",value:"cancel"},{label:"Confirmar",value:"confirm",primary:true}]}))==="confirm";}
async function runAntminerAction(title,description,action){
  const started=performance.now();
  const pending=showOperationDialog({title,message:description,locked:true,progress:true});
  try{const result=await action(),elapsed=Math.round(performance.now()-started);updateOperationDialog({title,message:`${result} · resposta recebida em ${elapsed} ms.`,actions:[{label:"OK",value:"ok",primary:true}]});await pending;return true;}
  catch(error){updateOperationDialog({title:`${title} · falhou`,message:error.message||"O Gateway não conseguiu concluir a operação.",actions:[{label:"OK",value:"ok",primary:true}]});await pending;return false;}
}
function summarizeAntminerState(results){
  const poolsResult=results?.pools;
  const groups=poolsResult?.data;
  if(poolsResult?.error||!Array.isArray(groups))return "Estado da pool indisponível; a leitura da Braiins não confirmou atividade da pool.";
  const pools=groups.flatMap(group=>Array.isArray(group?.pools)?group.pools:[]);
  if(!pools.length)return "A Braiins não devolveu pools configuradas.";
  const enabled=pools.filter(pool=>pool?.enabled===true);
  const alive=enabled.filter(pool=>pool?.alive===true);
  const active=enabled.filter(pool=>pool?.active===true);
  const shares=enabled.reduce((total,pool)=>total+Number(pool?.stats?.accepted_shares||0),0);
  if(!enabled.length)return "As pools devolvidas estão desativadas.";
  if(!alive.length)return "Nenhuma pool ativa está a responder neste momento.";
  if(!active.length)return "A pool responde, mas a Braiins não a indica como ativa.";
  if(shares>0)return `A pool está ativa e reporta ${shares} shares aceites no período indicado pela Braiins.`;
  return "A pool está ativa, mas não reporta shares aceites; isso não confirma hashing nem trabalho válido.";
}
const antminerFieldLabels={rpm:"Rotação",target_speed_ratio:"Velocidade definida",highest_temperature:"Temperatura máxima",temperature:"Temperatura",fans:"Ventoinhas",position:"Ventoinha",watt:"Alvo de potência",current_target:"Alvo atual",power_target:"Alvo de potência",hashrate:"Hashrate",accepted_shares:"Shares aceites",rejected_shares:"Shares rejeitadas",active:"Ativa",alive:"A responder",enabled:"Ativada",state:"Estado",status:"Estado",model:"Modelo",bos_version:"Versão Braiins OS",hostname:"Nome na rede",serial_number:"Número de série",overall_tuner_state:"Estado do tuner",profile:"Perfil",created:"Criado",estimated_power_consumption:"Consumo estimado",measured_hashrate:"Hashrate medido",pool_stats:"Estatísticas da pool",miner_stats:"Estatísticas da mineradora",power_stats:"Estatísticas de potência",errors:"Erros",message:"Mensagem",code:"Código",name:"Nome",type:"Tipo",contract_name:"Contrato",dev_fee:"Taxa de desenvolvimento"};
function antminerHumanLabel(key){return antminerFieldLabels[key]||String(key).replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase());}
function antminerHumanValue(key,value){
  if(value===null||value===undefined)return "Não indicado";
  if(typeof value==="boolean")return value?"Sim":"Não";
  if(key==="target_speed_ratio"&&Number.isFinite(Number(value)))return `${Math.round(Number(value)*100)}%`;
  if(key==="watt"&&Number.isFinite(Number(value)))return `${Number(value).toLocaleString("pt-PT")} W`;
  if(typeof value==="number")return Number.isFinite(value)?value.toLocaleString("pt-PT"):"Não indicado";
  if(typeof value==="string")return value;
  return "";
}
function antminerDetailMarkup(value,depth=0){
  if(value===null||value===undefined)return `<span class="antminer-value-muted">Não indicado</span>`;
  if(Array.isArray(value))return value.length?`<div class="antminer-detail-list">${value.map((entry,index)=>`<article class="antminer-detail-card"><h4>${antminerHumanLabel(entry?.name||entry?.position||`item_${index+1}`)}</h4>${antminerDetailMarkup(entry,depth+1)}</article>`).join("")}</div>`:`<p class="antminer-value-muted">Sem itens registados.</p>`;
  if(typeof value!=="object")return `<span>${esc(antminerHumanValue("",value))}</span>`;
  const entries=Object.entries(value).filter(([key])=>!/(password|secret|token|contract_key|authorization)/i.test(key));
  return `<div class="antminer-detail-grid">${entries.map(([key,entry])=>{
    const label=antminerHumanLabel(key);
    if(entry&&typeof entry==="object")return `<section class="antminer-detail-item antminer-detail-nested"><small>${esc(label)}</small>${antminerDetailMarkup(entry,depth+1)}</section>`;
    return `<section class="antminer-detail-item"><small>${esc(label)}</small><strong>${esc(antminerHumanValue(key,entry))}</strong></section>`;
  }).join("")}</div>`;
}
function antminerAdvancedEditorMarkup(schema,current){
  const properties=schema?.properties||schema?.schema?.properties||{};
  const currentValues=current&&typeof current==="object"&&!Array.isArray(current)?current:{};
  const fields=Object.entries(properties).filter(([,spec])=>spec&&typeof spec==="object"&&spec.readOnly!==true);
  if(!fields.length)return `<p class="antminer-value-muted">A mineradora não disponibilizou opções editáveis neste esquema.</p>${antminerDetailMarkup(current)}`;
  return `<p class="antminer-section-intro">Campos com caixa podem ser alterados. Os restantes dados são apenas leitura.</p><div class="antminer-setting-grid">${fields.map(([key,spec])=>{
    const type=Array.isArray(spec.type)?(spec.type.find(item=>item!=="null")||"string"):spec.type;
    const value=currentValues[key]??spec.default??"", label=spec.title||antminerHumanLabel(key), description=spec.description||"";
    let control;
    if(type==="boolean")control=`<select data-antminer-setting="${esc(key)}" data-setting-type="boolean" data-current="${esc(JSON.stringify(value))}"><option value="true" ${value===true?"selected":""}>Ativado</option><option value="false" ${value===false?"selected":""}>Desativado</option></select>`;
    else if(Array.isArray(spec.enum))control=`<select data-antminer-setting="${esc(key)}" data-setting-type="enum" data-current="${esc(JSON.stringify(value))}">${spec.enum.map(option=>`<option value="${esc(JSON.stringify(option))}" ${JSON.stringify(option)===JSON.stringify(value)?"selected":""}>${esc(String(option))}</option>`).join("")}</select>`;
    else if(type==="integer"||type==="number")control=`<input data-antminer-setting="${esc(key)}" data-setting-type="${type}" data-current="${esc(JSON.stringify(value))}" type="number" ${Number.isFinite(spec.minimum)?`min="${spec.minimum}"`:""} ${Number.isFinite(spec.maximum)?`max="${spec.maximum}"`:""} ${type==="integer"?`step="1"`:`step="any"`} value="${esc(String(value))}">`;
    else if(type==="object"||type==="array")control=`<textarea data-antminer-setting="${esc(key)}" data-setting-type="${type}" data-current="${esc(JSON.stringify(value))}" rows="3">${esc(JSON.stringify(value))}</textarea>`;
    else control=`<input data-antminer-setting="${esc(key)}" data-setting-type="string" data-current="${esc(JSON.stringify(value))}" value="${esc(String(value))}">`;
    return `<label class="antminer-setting"><span><strong>${esc(label)}</strong>${description?`<small>${esc(description)}</small>`:""}</span>${control}</label>`;
  }).join("")}</div><div class="dialog-actions"><button class="button primary" type="button" id="antminer-settings-save">Guardar alterações</button></div>`;
}
function openAntminerSectionDialog(title,content,raw=""){
  const existing=$("#antminer-section-dialog");existing?.remove();
  const dialog=document.createElement("dialog");dialog.id="antminer-section-dialog";dialog.className="settings-dialog antminer-section-dialog";
  dialog.innerHTML=`<form method="dialog" class="antminer-section-card"><div class="dialog-header"><div><p class="eyebrow">BRAIINS OS · ESTADO E CONFIGURAÇÃO</p><h2>${esc(title)}</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><div class="antminer-section-content">${content}</div>${raw?`<details class="antminer-raw-details"><summary>Detalhes técnicos</summary><pre>${esc(raw)}</pre></details>`:""}<div class="dialog-actions"><span class="dialog-actions-spacer"></span><button class="button primary" value="ok">Fechar</button></div></form>`;
  (document.querySelector("#page-content")||document.body).append(dialog);dialog.addEventListener("close",()=>dialog.remove());dialog.showModal();
}
function showAntminerReadResult(operation,data,rawData){
  data=data?.data??data;
  const label=antminerReadOperations.find(([key])=>key===operation)?.[1]||antminerHumanLabel(operation);
  if(data?.error){openAntminerSectionDialog(label,`<div class="antminer-error-card"><strong>Não foi possível consultar esta informação.</strong><p>${esc(data.error)}</p><small>As outras leituras podem continuar disponíveis.</small></div>`,rawData);return;}
  if(operation==="advanced_settings"){
    openAntminerSectionDialog("Definições avançadas",antminerAdvancedEditorMarkup(data?.schema,data?.current),rawData);return;
  }
  if(operation==="cooling"&&Array.isArray(data?.fans)){
    const cards=data.fans.map((fan,index)=>`<article class="antminer-fan-card"><span class="antminer-fan-icon" aria-hidden="true">✣</span><div><strong>Ventoinha ${index+1}</strong><span>${antminerHumanValue("rpm",fan?.rpm)} RPM</span>${fan?.target_speed_ratio!=null?`<small>Velocidade definida: ${antminerHumanValue("target_speed_ratio",fan.target_speed_ratio)}</small>`:""}</div></article>`).join("");
    openAntminerSectionDialog(label,`<div class="antminer-fan-grid">${cards||`<p class="antminer-value-muted">Sem ventoinhas reportadas.</p>`}</div>${data.highest_temperature?`<section class="antminer-detail-item"><small>Temperatura máxima</small><strong>${antminerDetailMarkup(data.highest_temperature)}</strong></section>`:""}`,rawData);return;
  }
  if(operation==="power_target"){
    const target=antminerCurrentPowerTarget(data);
    if(target.current!=null){const watt=Number(target.current),profileWatt=Number(target.profile);openAntminerSectionDialog(label,`<div class="antminer-target-card"><small>Alvo atual comunicado pela mineradora</small><strong>${Number.isFinite(watt)?`${watt.toLocaleString("pt-PT")} W`:esc(String(target.current))}</strong>${Number.isFinite(profileWatt)&&profileWatt!==watt?`<p>Perfil guardado: ${profileWatt.toLocaleString("pt-PT")} W. Este valor é diferente do alvo atual.</p>`:""}<p>O alvo é um limite configurado, não a potência real nem uma confirmação de hashing.</p></div><label class="antminer-setting"><span><strong>Novo alvo de potência (W)</strong><small>Editável · será enviado à Braiins OS</small></span><input id="antminer-section-watt" type="number" min="1" max="100000" step="1" value="${Number.isFinite(watt)?watt:""}"></label><div class="dialog-actions"><button class="button primary" type="button" id="antminer-section-apply-watt">Aplicar alvo</button></div>`,rawData);return;}
    if(target.profile!=null){openAntminerSectionDialog(label,`<div class="antminer-target-card"><small>Alvo do perfil guardado</small><strong>${esc(String(target.profile))} W</strong><p>A API não devolveu o alvo atual nesta resposta; o valor do perfil não confirma que esteja aplicado.</p></div>`,rawData);return;}
  }
  if(operation==="tuner"){
    const target=antminerCurrentPowerTarget(data),mode=data?.mode_state||data?.modeState||{},power=mode?.power_target_mode_state||mode?.powerTargetModeState||mode?.powertargetmodestate||{},profile=power?.profile||{};
    const profileTarget=profile?.target?.watt??profile?.power_target?.watt??target.profile;
    const currentTarget=target.current;
    const measured=profile?.measured_hashrate?.gigahash_per_second??profile?.measuredHashrate?.gigahashPerSecond;
    const estimated=profile?.estimated_power_consumption?.watt??profile?.estimatedPowerConsumption?.watt;
    const created=profile?.created;
    const displayWatt=value=>{const n=Number(value);return Number.isFinite(n)?`${n.toLocaleString("pt-PT")} W`:"Não comunicado";};
    const hashDisplay=Number.isFinite(Number(measured))?`${(Number(measured)/1000).toLocaleString("pt-PT",{maximumFractionDigits:2})} TH/s`:"Não comunicado";
    openAntminerSectionDialog("Potência",`<div class="antminer-profile-summary"><article><small>Perfil criado</small><strong>${created?esc(String(created)):"Não indicado"}</strong></article><article><small>Alvo do perfil</small><strong>${displayWatt(profileTarget)}</strong></article><article><small>Alvo ativo agora</small><strong>${displayWatt(currentTarget)}</strong></article><article><small>Hashrate médio</small><strong>${hashDisplay}</strong></article><article><small>Consumo estimado pelo tuner</small><strong>${displayWatt(estimated)}</strong></article></div><p>O campo editável altera o alvo do perfil. “Alvo ativo agora” é uma leitura separada: o Dynamic Performance Scaling da Braiins ou a automatização do Gateway podem mantê-lo temporariamente abaixo do alvo configurado.</p><label class="antminer-setting"><span><strong>Alvo de potência (W)</strong><small>Único campo editável · o valor enviado fica visível separado do alvo ativo</small></span><input id="antminer-section-watt" type="number" min="1" max="100000" step="1" value="${esc(String(profileTarget??currentTarget??""))}"></label><div class="dialog-actions"><button class="button primary" type="button" id="antminer-section-apply-watt">Guardar alvo</button></div>`,rawData);return;
  }
  if(operation==="target_profiles"&&Array.isArray(data?.power_target_profiles)){
    const power=data.power_target_profiles,hash=data.hashrate_target_profiles||[];
    openAntminerSectionDialog(label,`<div class="antminer-profile-summary"><article><small>Perfis de potência</small><strong>${power.length}</strong></article><article><small>Perfis de hashrate</small><strong>${hash.length}</strong></article></div>${[...power.map(item=>({kind:"Potência",item})),...hash.map(item=>({kind:"Hashrate",item}))].map(({kind,item})=>`<article class="antminer-detail-card"><h4>Perfil de ${kind.toLowerCase()}</h4>${antminerDetailMarkup(item)}</article>`).join("")||`<p class="antminer-value-muted">A mineradora não devolveu perfis guardados.</p>`}`,rawData);return;
  }
  const summary=operation==="tuner"?`<div class="antminer-target-card"><small>Estado comunicado pelo afinador</small><strong>${esc(antminerHumanValue("overall_tuner_state",data?.overall_tuner_state))}</strong>${data?.mode_state?antminerDetailMarkup(data.mode_state):""}</div>`:antminerDetailMarkup(data);
  openAntminerSectionDialog(label,summary||`<p class="antminer-value-muted">Sem informação disponível.</p>`,rawData);
}

function antminerCurrentPowerTarget(data){
  const object=value=>value&&typeof value==="object"&&!Array.isArray(value)?value:{};
  const root=object(data),mode=object(root.mode_state||root.modeState);
  const powerState=object(mode.power_target_mode_state||mode.powerTargetModeState||mode.powertargetmodestate);
  const current=powerState.current_target??powerState.currentTarget??root.current_target??root.currentTarget??root.watt;
  const profile=powerState.profile?.target??powerState.profile?.power_target??root.profile?.target;
  const currentWatt=object(current).watt??current;
  const profileWatt=object(profile).watt??profile;
  return {current:currentWatt??null,profile:profileWatt??null};
}
function antminerSetPowerResponseWatt(result){
  const data=result?.data??result;
  const value=data?.watt??data?.power_target?.watt??data?.powerTarget?.watt;
  const watt=typeof value==="string"&&/^\d+(?:\.\d+)?$/.test(value)?Number(value):value;
  return typeof watt==="number"&&Number.isFinite(watt)&&watt>=0?watt:null;
}
function minerAssociatedBreakerReading(miner, loads, registeredMinerCount) {
  if (!miner) return null;
  const matches = (loads || []).filter(load => load.equipment_id === miner.id);
  const load = matches.length === 1 ? matches[0]
    : matches.length === 0 && registeredMinerCount === 1 && (loads || []).length === 1 && !loads[0].equipment_id ? loads[0]
    : null;
  if (!load) return { fresh: false, reason: matches.length > 1 ? "ambiguous_association" : "no_association" };
  const telemetry = state.energyEngine?.current?.tuya_load_telemetry || {};
  const meter = telemetry[load.id] || (load.tuya_device_id
    ? Object.values(telemetry).find(item => item.device_id === load.tuya_device_id)
    : null);
  const power = meter?.metrics?.power;
  const fresh = Boolean(meter?.fresh && power?.unit === "W" && Number.isFinite(Number(power.value)));
  return { fresh, value: fresh ? Number(power.value) : null, unit: power?.unit || "W",
    meterName: meter?.name || "", deviceId: meter?.device_id || load.tuya_device_id || "",
    reason: matches.length > 1 ? "ambiguous_association" : meter?.fresh ? "power_not_mapped" : "no_recent_telemetry" };
}
function renderAntminerManagementPanel(isOwner){
  if(!isOwner)return `<section class="panel detail-panel"><h2>Gestão da Mineradora</h2><p>As configurações e comandos Braiins OS estão disponíveis na sessão Owner autenticada.</p></section>`;
  const registeredMiners=(state.equipment||[]).filter(item=>item?.category==="mineradoras");
  if(!antminerActiveEquipmentId||!registeredMiners.some(item=>item.id===antminerActiveEquipmentId))antminerActiveEquipmentId=registeredMiners[0]?.id||"";
  const activeMiner=registeredMiners.find(item=>item.id===antminerActiveEquipmentId)||null;
  const minerLoads=(state.energyEngine?.configuration?.loads||[]).filter(load=>load.kind==="miner"&&load.control_type==="antminer_braiins");
  const breakerReading=minerAssociatedBreakerReading(activeMiner,minerLoads,registeredMiners.length);
  const breakerPowerMarkup=`<div class="detail-item"><small>Potência · disjuntor Tuya</small><strong>${breakerReading?.fresh?`${new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(breakerReading.value)} ${esc(breakerReading.unit)}`:breakerReading?.reason==="ambiguous_association"?"Associação ambígua":breakerReading?.reason==="no_association"?"Sem disjuntor associado":"Sem leitura recente"}</strong>${breakerReading?.meterName?`<small>${esc(breakerReading.meterName)}</small>`:""}</div>`;
  const managedEquipmentId=minerLoads.length===1?(minerLoads[0].equipment_id||(registeredMiners.length===1?registeredMiners[0]?.id:null)):null;
  const canManage=Boolean(activeMiner&&registeredMiners.length===1||activeMiner&&managedEquipmentId===activeMiner.id);
  const equipmentTabs=registeredMiners.length?`<nav class="ws-horizontal-tabs miner-equipment-tabs" aria-label="Mineradoras registadas">${registeredMiners.map(item=>`<button type="button" data-miner-equipment-select="${esc(item.id)}" aria-selected="${item.id===activeMiner?.id}" class="${item.id===activeMiner?.id?"selected":""}">${esc(item.name)}</button>`).join("")}</nav>`:"";
  if(registeredMiners.length>1&&!canManage){
    const last=activeMiner?.last_communication_at?timeLabel(activeMiner.last_communication_at):"Sem comunicação registada";
    const readings=(activeMiner?.readings||[]).filter(item=>!["miner_power_w","miner_power"].includes(String(item.field||"").toLowerCase())).slice(0,6).map(item=>`<div class="detail-item"><small>${esc(item.field)}</small><strong>${esc(formatReading(item).value)} ${esc(item.unit||"")}</strong></div>`).join("");
    return `<section class="panel detail-panel antminer-management-panel">${equipmentTabs}<nav class="ws-horizontal-tabs antminer-subtabs" aria-label="Secções da mineradora"><button type="button" data-miner-submenu="state" aria-selected="${antminerActiveSubmenu==="state"}" class="${antminerActiveSubmenu==="state"?"selected":""}">Situação</button><button type="button" data-miner-submenu="braiins" aria-selected="${antminerActiveSubmenu==="braiins"}" class="${antminerActiveSubmenu==="braiins"?"selected":""}">Braiins OS</button><button type="button" data-miner-submenu="commands" aria-selected="${antminerActiveSubmenu==="commands"}" class="${antminerActiveSubmenu==="commands"?"selected":""}">Comandos</button><button type="button" data-miner-submenu="config" aria-selected="${antminerActiveSubmenu==="config"}" class="${antminerActiveSubmenu==="config"?"selected":""}">Configuração e sistema</button></nav><div data-miner-section="state" ${antminerActiveSubmenu!=="state"?"hidden":""}><div class="panel-header"><div><p class="eyebrow">SITUAÇÃO DA MINERADORA</p><h2>${esc(activeMiner?.name||"Mineradora")}</h2></div><span class="source-tag">${equipmentConnectionIsLive(activeMiner)?"CONNECTED":"UNAVAILABLE"}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Última comunicação</small><strong>${esc(last)}</strong></div><div class="detail-item"><small>Protocolo</small><strong>${esc(activeMiner?.protocol||"Não identificado")}</strong></div>${readings}${breakerPowerMarkup}</div></div><div data-miner-section="braiins" ${antminerActiveSubmenu!=="braiins"?"hidden":""}><p class="field-note">Este Gateway ainda não tem um conector Braiins independente associado a esta mineradora. Os dados e operações desta secção não estão disponíveis para este equipamento.</p></div><div data-miner-section="commands" ${antminerActiveSubmenu!=="commands"?"hidden":""}><p class="field-note">Este Gateway ainda não tem um conector Braiins independente associado a esta mineradora; não são apresentados comandos que poderiam atingir outra máquina.</p></div><div data-miner-section="config" ${antminerActiveSubmenu!=="config"?"hidden":""}>${renderMinerBreakerAssociation(activeMiner?.id)}<p class="field-note">As definições desta mineradora ficam separadas dos comandos e das leituras.</p></div></section>`;
  }
  const panel=`<section id="antminer-management-panel" class="panel detail-panel antminer-management-panel"><nav class="ws-horizontal-tabs antminer-subtabs" aria-label="Secções da mineradora"><button type="button" data-miner-submenu="state" aria-selected="${antminerActiveSubmenu==="state"}" class="${antminerActiveSubmenu==="state"?"selected":""}">Situação</button><button type="button" data-miner-submenu="braiins" aria-selected="${antminerActiveSubmenu==="braiins"}" class="${antminerActiveSubmenu==="braiins"?"selected":""}">Braiins OS</button><button type="button" data-miner-submenu="commands" aria-selected="${antminerActiveSubmenu==="commands"}" class="${antminerActiveSubmenu==="commands"?"selected":""}">Comandos</button><button type="button" data-miner-submenu="config" aria-selected="${antminerActiveSubmenu==="config"}" class="${antminerActiveSubmenu==="config"?"selected":""}">Configuração e sistema</button></nav><div data-miner-section="state" ${antminerActiveSubmenu!=="state"?"hidden":""}><div class="panel-header"><div><p class="eyebrow">SITUAÇÃO DA MINERADORA · ${esc(activeMiner?.protocol||"Protocolo não identificado")}</p><h2>${esc(activeMiner?.name||"Mineradora")}</h2></div><span class="source-tag">${equipmentConnectionIsLive(activeMiner)?"CONNECTED":"UNAVAILABLE"}</span><button class="button primary" id="antminer-refresh-management" type="button">Ler estado completo</button></div><div class="device-detail-grid"><div class="detail-item"><small>Ligação</small><strong>${equipmentConnectionIsLive(activeMiner)?"Ligado":"Offline"}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(activeMiner?.last_communication_at?timeLabel(activeMiner.last_communication_at):"Sem comunicação registada")}</strong></div><div class="detail-item"><small>Protocolo</small><strong>${esc(activeMiner?.protocol||"Não identificado")}</strong></div>${(activeMiner?.readings||[]).filter(item=>!["miner_power_w","miner_power"].includes(String(item.field||"").toLowerCase())).map(item=>`<div class="detail-item"><small>${esc(item.field)}</small><strong>${esc(formatReading(item).value)} ${esc(item.unit||"")}</strong></div>`).join("")}${breakerPowerMarkup}</div><p class="field-note">A ligação, a última comunicação, o protocolo e as leituras pertencem à situação deste equipamento.</p><div id="antminer-management-status" class="connection-result" role="status" aria-live="polite">Ainda não foi consultado o estado da Braiins OS.</div><div id="antminer-management-diagnosis" class="connection-result" role="status" aria-live="polite">O diagnóstico da pool aparece após a leitura completa.</div></div><div class="antminer-read-categories" data-miner-section="braiins" ${antminerActiveSubmenu!=="braiins"?"hidden":""}>${antminerReadCategories.map(([title,icon,operations])=>`<details class="antminer-read-category"><summary><span class="antminer-category-icon">${icon}</span><span>${title}</span><span class="antminer-category-count">${operations.length}</span></summary><div class="antminer-management-read-grid">${operations.map(op=>{const label=antminerReadOperations.find(([key])=>key===op)?.[1]||antminerHumanLabel(op);return `<button class="button secondary" type="button" data-antminer-read="${op}">${label}</button>`;}).join("")}</div></details>`).join("")}</div><details class="antminer-raw-details antminer-inline-raw"><summary>Dados técnicos (JSON)</summary><pre id="antminer-management-output" class="antminer-json-output" aria-live="polite">Usa “Ler estado completo” para consultar as secções suportadas.</pre></details><div class="antminer-command-grid" data-miner-section="commands" ${antminerActiveSubmenu!=="commands"?"hidden":""}><label class="feature-field"><span>Alvo de potência (W)</span><input id="antminer-section-watt" type="number" min="1" max="100000" step="1"></label><button class="button primary" type="button" id="antminer-section-apply-watt">Aplicar potência</button><button class="button primary" type="button" data-antminer-write="start">Iniciar</button><button class="button secondary" type="button" data-antminer-write="resume">Retomar</button><button class="button secondary" type="button" data-antminer-write="pause">Pausar</button><button class="button secondary" type="button" data-antminer-write="stop">Parar</button><button class="button secondary" type="button" data-antminer-write="restart">Reiniciar mineração</button><button class="button secondary" type="button" data-antminer-write="reboot">Reiniciar mineradora</button></div><div data-miner-section="config" ${antminerActiveSubmenu!=="config"?"hidden":""}>${renderMinerBreakerAssociation(activeMiner?.id)}<details class="antminer-config-editor"><summary>Configuração técnica manual</summary><p>Para operações avançadas documentadas. Alterações podem interromper a mineração ou bloquear o acesso remoto.</p><label class="feature-field">Operação<select id="antminer-management-operation">${antminerWriteOperations.map(([op,label])=>`<option value="${op}">${label} · ${op}</option>`).join("")}</select></label><label class="feature-field">Método API<select id="antminer-management-method"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label><label class="feature-field">Caminho API Braiins<input id="antminer-management-path" maxlength="256" placeholder="/api/v1/…"></label><label class="feature-field">Parâmetros de consulta JSON<input id="antminer-management-query" maxlength="1024" placeholder='{"include_default":"true"}'></label><label class="feature-field">ID do grupo de pools<input id="antminer-management-resource-id" maxlength="128"></label><label class="feature-field">Corpo JSON<textarea id="antminer-management-payload" rows="8" spellcheck="false" placeholder='Ex.: {"watt":2500}'></textarea></label><div class="dialog-actions"><button class="button primary" id="antminer-management-submit" type="button">Enviar à Mineradora</button></div></details></div></section>`;
  const inserted=panel.replace('<section id="antminer-management-panel" class="panel detail-panel antminer-management-panel">','<section id="antminer-management-panel" class="panel detail-panel antminer-management-panel">'+equipmentTabs);
  return inserted.replace('<h2>Painel da Mineradora</h2>',`<h2>${esc(activeMiner?.name||"Painel da Mineradora")}</h2>`);
}

function renderGatewayArea(page) {
  const labels={energia:"Energia",inversores:"Inversores",baterias:"Baterias","paineis-solares":"Painéis solares",mineradoras:"Mineradoras",ev:"Carregador EV",aqs:"AQS","soalho-radiante":"Soalho radiante"};
  const categories=page==="paineis-solares"?["inversores"]:[page], items=state.equipment.filter(item=>categories.includes(item.category));
  const engine=state.energyEngine||{}, readings=engine.latest_readings||{}, config=engine.configuration||{}, isOwner=sessionInfo().authenticated&&sessionInfo().user?.role==="owner";
  const battery=engine.current||{};
  const energyBatteryPower=battery.battery_power_w==null?null:-Number(battery.battery_power_w);
  const batteryFlowClass=Number(battery.battery_charge_power_w)>0?"charge":Number(battery.battery_discharge_power_w)>0?"discharge":energyBatteryPower>0?"charge":energyBatteryPower<0?"discharge":"idle";
  const metrics=page==="energia"?[
    ["Produção FV",engine.current?.pv_power_w,"W"],["Consumo",engine.current?.load_power_w,"W"],["SOC bateria",engine.current?.battery_soc_percent,"%"],["Potência bateria",energyBatteryPower,"W",`battery-flow-kpi ${batteryFlowClass}`]
  ]:page==="paineis-solares"?[
    ["Produção FV",engine.current?.pv_power_w,"W"],["MPPT 1 · potência",readings.pv1_input_power?.value,readings.pv1_input_power?.unit||"W"],["MPPT 2 · potência",readings.pv2_input_power?.value,readings.pv2_input_power?.unit||"W"],["Potencial solar",engine.forecast?.solar_potential?.hourly_values?.find(point=>point.segment==="forecast")?.value,"kW"]
  ]:page==="baterias"?[
    ["SOC",engine.current?.battery_soc_percent,"%"],["Potência assinada",engine.current?.battery_power_w,"W"],["A carregar",engine.current?.battery_charge_power_w,"W"],["A descarregar",engine.current?.battery_discharge_power_w,"W"]
  ]:page==="inversores"?[
    ["Saída do inversor",readings.inverter_power_total?.value,readings.inverter_power_total?.unit||"W"],["Consumo das cargas",engine.current?.load_power_w,"W"],["Estado",items[0]?.connection_state||"Sem equipamento"]
  ]:[];
  const metricCard=([name,value,unit,extraClass=""])=>`<article class="ws-kpi ${esc(extraClass)}"><small>${esc(name)}</small><strong>${value===null||value===undefined||!Number.isFinite(Number(value))?"—":esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:name.toLowerCase().includes("soc")?1:2,minimumFractionDigits:name.toLowerCase().includes("soc")?1:0}).format(Number(value)))} <em>${esc(unit||"")}</em></strong>${name==="Potência bateria"?`<span>${batteryFlowClass==="charge"?"A carregar":batteryFlowClass==="discharge"?"A descarregar":"Sem fluxo de bateria"}</span>`:name==="SOC bateria"?`<span>Energia disponível até ao corte: ${Number.isFinite(Number(battery.battery_energy_available_kwh_above_minimum))?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(Number(battery.battery_energy_available_kwh_above_minimum)))} kWh`:`— kWh`}</span>`:""}</article>`;
  const batteryConfig=isOwner&&page==="baterias"?`<section class="panel feature-panel battery-area-config"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO OWNER · GATEWAY</p><h2>Gerir bancos</h2></div><button class="button primary" id="area-battery-add-bank" type="button">+ Adicionar banco</button></div><p class="field-note">Os bancos aparecem no resumo agregado abaixo. Faz duplo clique num banco para editar ou remover. Cada banco online contribui para a capacidade usada pelo Gateway.</p><details class="battery-limits-details"><summary>Limites de descarga e capacidade</summary><p>O corte é definido pelo SOC mínimo. Se não houver bancos registados, podes indicar uma capacidade agregada manual.</p><div class="ws-config-grid"><label class="feature-field">Capacidade de carga (kWh, sem bancos)<input id="area-battery-capacity" type="number" min="0" max="10000" step="0.1" value="${esc(config.battery_capacity_kwh??"")}"></label><label class="feature-field">SOC mínimo / corte (%)<input id="area-battery-minimum" type="number" min="0" max="99.9" step="1" value="${esc(config.minimum_soc_percent??20)}"></label><label class="feature-field">SOC máximo (%)<input id="area-battery-maximum" type="number" min="0.1" max="100" step="1" value="${esc(config.maximum_soc_percent??100)}"></label></div><div class="ws-actions"><button class="button primary" id="area-battery-save">Guardar limites</button><span id="area-battery-status" class="ws-inline-note"></span></div></details></section>${renderBatteryBankDialog()}`:"";
  const normalizeName=(reading)=>reading.evidence?.label||reading.field||"Leitura";
  const metricValue=(reading)=>`${esc(formatReading(reading).value)} ${esc(reading.unit||"")}`;
  const row=(title,fields,extraClass="")=>{const found=fields.map(field=>readings[field]).filter(Boolean);return found.length?`<section class="gateway-reading-row ${extraClass}"><h3>${esc(title)}</h3><div class="device-detail-grid telemetry-grid">${found.map((reading,index)=>{const phase={ups_load_power_a:"L1",ups_load_power_b:"L2",ups_load_power_c:"L3"}[reading.field];const label=phase?`${title.split(" · ")[0]} ${phase}`:normalizeName(reading);return `<div class="detail-item"><small>${esc(label)}</small><strong>${metricValue(reading)}</strong></div>`;}).join("")}</div></section>`:"";};
  const deyeReadings=page==="inversores"?[
    row("Tensões de carga",["load_voltage_a","load_voltage_b","load_voltage_c"],"three-phase-row"),
    row("MPPT 1",["pv1_current","pv1_voltage","pv1_input_power"]),
    row("MPPT 2",["pv2_current","pv2_voltage","pv2_input_power"]),
    row("Energia e potência FV",["pv_total_energy","pv_total_power"]),
    row("Potência de saída · fases",["ups_load_power_a","ups_load_power_b","ups_load_power_c"],"three-phase-row"),
    row("Potência total de saída UPS",["ups_load_power_total"],"full-width-row")
  ].filter(Boolean).join(""):"";
  const panelReadings=page==="paineis-solares"?[
    row("MPPT 1",["pv1_current","pv1_voltage","pv1_input_power"]),
    row("MPPT 2",["pv2_current","pv2_voltage","pv2_input_power"]),
    row("Energia e potência FV",["pv_total_energy","pv_total_power"])
  ].filter(Boolean).join(""):"";
  const batteryBanks=config.battery_banks||[];
  const batteryTelemetry=["battery_voltage","battery_temperature"].map(field=>readings[field]).filter(Boolean);
  const batteryEquipmentCard=page==="baterias"?`<section class="panel detail-panel gateway-area-device"><div class="panel-header"><div><p class="eyebrow">RESUMO AGREGADO DO GATEWAY</p><h2>Bateria Deye · conjunto</h2></div><span class="source-tag">${batteryBanks.filter(bank=>bank.active!==false).length} ONLINE</span></div><p class="field-note">Este resumo representa o conjunto ligado ao inversor Deye. O Gateway combina as leituras agregadas de tensão e carga/descarga com a capacidade dos bancos online. Faz duplo clique num banco para editar ou remover.</p>${batteryBanks.length?`<div class="battery-available-kwh"><small>Capacidade nominal dos bancos online</small><strong>${battery.battery_capacity_kwh!=null&&Number.isFinite(Number(battery.battery_capacity_kwh))?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(battery.battery_capacity_kwh)))} kWh`:"—"}</strong></div><div class="battery-bank-summary">${batteryBanks.map((bank,index)=>`<button class="detail-item battery-bank-card" type="button" data-battery-bank-edit="${esc(bank.id)}" aria-label="${esc(bank.name||`Banco ${index+1}`)}, ${bank.active===false?"offline":"online"}, duplo clique para editar"><small>${esc(bank.name||`Banco ${index+1}`)} · ${bank.active===false?"OFFLINE":"ONLINE"}</small><strong>${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(bank.capacity_kwh)||0))} kWh</strong><span>Duplo clique para editar</span></button>`).join("")}</div>`:`<div class="empty-state">Ainda não configuraste bancos. O Owner pode adicionar um banco.</div>`}${batteryTelemetry.length?`<div class="device-detail-grid telemetry-grid">${batteryTelemetry.map(value=>`<div class="detail-item"><small>${esc(value.evidence?.label||value.field)} · inversor</small><strong>${esc(formatReading(value).value)} ${esc(value.unit||"")}</strong></div>`).join("")}</div>`:""}<div class="battery-available-kwh"><small>Energia disponível até ao SOC de corte · estimativa do Gateway</small><strong>${engine.current?.battery_energy_available_kwh_above_minimum!=null&&Number.isFinite(Number(engine.current.battery_energy_available_kwh_above_minimum))?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:2}).format(Number(engine.current.battery_energy_available_kwh_above_minimum)))} kWh`:"A aguardar estimativa do Gateway"}</strong></div></section>`:"";
  const equipmentCards=page==="baterias"?batteryEquipmentCard:page==="paineis-solares"?`${panelReadings||`<div class="empty-state">O Deye ainda não forneceu leituras de MPPT.</div>`}${renderPvStringsSection(config,isOwner)}`:page==="aqs"?renderAqsSection(config,isOwner):page==="ev"?renderEvSection(config,isOwner):`${items.map(item=>`<section class="panel detail-panel gateway-area-device" ${page==="inversores"?`data-energy-equipment="${esc(item.id)}" tabindex="0" role="button" aria-label="Abrir ${esc(item.name)}"`:""}><div class="panel-header"><div><p class="eyebrow">${page==="inversores"?"INVERSOR":"EQUIPAMENTO"}</p><h2>${esc(item.name)}</h2></div><span class="source-tag">${esc(item.connection_state||item.status||"UNKNOWN")}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Ligação</small><strong>${esc(item.connection_state||"Desconhecida")}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(timeLabel(item.last_communication_at))}</strong></div><div class="detail-item"><small>Protocolo</small><strong>${esc(item.protocol||"Não indicado")}</strong></div></div>${deyeReadings}${item.readings?.length&&page!=="inversores"&&page!=="paineis-solares"?`<div class="device-detail-grid telemetry-grid">${item.readings.map(value=>`<div class="detail-item"><small>${esc(value.evidence?.label||value.field)}</small><strong>${esc(formatReading(value).value)} ${esc(value.unit||"")}</strong></div>`).join("")}</div>`:""}</section>`).join("")}${page==="mineradoras"?renderAntminerManagementPanel(isOwner):""}`;
  const description=page==="paineis-solares"?"Strings configuradas e leituras fotovoltaicas agregadas por MPPT.":page==="inversores"?"Estado do inversor, tensões de saída e potência entregue às cargas.":page==="baterias"?"SOC, potência assinada e limites que o Gateway observou.":page==="aqs"?"Termoacumuladores, potência nominal e associação opcional a um canal Tuya.":"Dados e leituras atuais fornecidos pelo Gateway autenticado.";
  const solarDay=engine.forecast?.solar_day||{};
  const solarDayCard=page==="energia"?`<article class="ws-kpi solar-day-forecast-card"><small>Produção solar prevista até ao fim do dia</small><strong>${solarDay.state==="ESTIMATED"&&Number.isFinite(Number(solarDay.estimated_total_kwh))?esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.estimated_total_kwh))):"—"} <em>kWh</em></strong><span>${solarDay.state==="ESTIMATED"?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.actual_today_kwh)||0))} kWh produzidos · ${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.remaining_estimate_kwh)||0))} kWh previstos · recalcula em até 10 min`:`Previsão indisponível: ${esc(solarDay.reason||"a aguardar dados do Gateway")}${solarDay.reason?.includes("potência nominal FV")?" Abre Owner → Produção → Previsão solar adaptativa e indica a potência total dos painéis em kWp.":""}`}</span></article>`:"";
  const energyOutlookCard="";
  const energyForecastHistory=page==="energia"?`<section class="panel chart-panel energy-forecast-history"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO + PREVISÃO</p><h2>Produção, consumo e potencial</h2><p>Leituras recentes e projeção do Engine a cada 15 min · meteorologia horária.</p></div><span class="source-tag">${esc(state.dataStatus)}</span></div>${chart()}</section><section class="panel energy-daily-explorer"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO GUARDADO</p><h2>Exploração diária</h2></div></div><p class="field-note">Percorre os dias disponíveis e compara produção medida, previsão e potencial ajustado.</p><button type="button" class="button secondary" id="engine-chart-open">Explorar dias guardados ↗</button>${renderEngineHistoryDialog()}</section>`:"";
  return `${page!=="energia"?`<div class="ws-horizontal-tabs energy-tabs" role="tablist" aria-label="Áreas energéticas">${[["inversores","Inversores"],["baterias","Baterias"],["paineis-solares","Painéis"],["ev","Carregador EV"],["aqs","AQS"],["mineradoras","Mineradoras"],["soalho-radiante","Soalho radiante"],["gestao-excedentes","Gestão de excedentes"]].map(([id,label])=>`<button role="tab" aria-selected="${page===id}" class="${page===id?"selected":""}" data-page="${id}">${label}</button>`).join("")}</div>`:""}<div class="page-heading"><div><p class="eyebrow">GATEWAY · DADOS REAIS</p><h1>${esc(labels[page]||page)}</h1><p>${esc(description)}</p></div>${page==="energia"?"":`<button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button>`}</div><div class="ws-kpi-grid">${metrics.map(metricCard).join("")}</div>${energyOutlookCard}${energyForecastHistory}${page==="energia"?`<section class="panel"><div class="panel-header"><div><p class="eyebrow">INSTALAÇÃO</p><h2>Explorar áreas</h2></div></div><div class="ws-area-grid">${[["engine","Medições e previsões"],["gestao-excedentes","Gestão de excedentes"],["inversores","Inversores"],["baterias","Baterias"],["paineis-solares","Painéis solares"],["mineradoras","Mineradoras"],["ev","Carregador EV"],["aqs","AQS"],["soalho-radiante","Soalho radiante"]].map(([id,label])=>`<button class="ws-area-card" data-page="${id}"><span class="ws-area-icon">◉</span><span><strong>${label}</strong><small>${id==="engine"?"Leituras, previsões e histórico":id==="gestao-excedentes"?"Prioridades, previsão e controlos automáticos":"Ver estado e leituras do Gateway"}</small></span><span class="ws-arrow">↗</span></button>`).join("")}</div></section>`:""}${batteryConfig}${page!=="energia"?(equipmentCards||`<div class="empty-state">O Gateway ainda não forneceu equipamentos ou leituras para esta área. Confirma a configuração correspondente na página Owner e volta a atualizar.</div>`):""}`;
}

function renderSurplusManager() {
  const live=state.mode!=="SIMULATED",engine=state.energyEngine||{},config=engine.configuration||{},manager=config.surplus_manager||{},automation=config.automation||{},plan=engine.dispatch||{},summary=engine.surplus_manager||{},isOwner=sessionInfo().authenticated&&sessionInfo().user?.role==="owner";
  const profile=manager.priority_profile||"tesla_home",presence=manager.tesla_presence||{state:"UNKNOWN"},loads=(config.loads||[]).filter(load=>["miner","ev_charger","water_heater","underfloor_heating","generic"].includes(load.kind)),devices=state.tuyaDevices||[];
  const demo=state.surplusDemo||{profile:"tesla_home",potential:3600,house:900,battery:88},current=engine.current||{},actions=plan.actions||[],actionByLoad=new Map(actions.map(action=>[action.load_id,action]));
  const labels={miner:"Mineradora",ev_charger:"Carregador EV",water_heater:"AQS",underfloor_heating:"Aquecimento",generic:"Outra carga"},protocolLabels={antminer_braiins:"Braiins OS",tuya_breaker:"Tuya · disjuntor",tuya_smart:"Tuya · interruptor",tesla_fleet:"Tesla · apenas leitura",manual:"Manual"};
  const rank={tesla_home:{ev_charger:0,water_heater:1,underfloor_heating:2,generic:3,miner:4},tesla_away:{miner:0,water_heater:1,underfloor_heating:2,generic:3,ev_charger:4},custom:{ev_charger:0,water_heater:0,underfloor_heating:0,generic:0,miner:0}}[profile]||{};
  const ordered=[...loads].sort((a,b)=>(rank[a.kind]??3)-(rank[b.kind]??3)||(a.priority||100)-(b.priority||100));
  const stateLabels={DISABLED:"Desativado",MANUAL_OVERRIDE:"Pausado por controlo manual",BLOCKED_NOT_COMMISSIONED:"Precisa de configuração inicial",BLOCKED_STALE_TELEMETRY:"À espera de leituras recentes",BLOCKED_UNTRUSTED_TELEMETRY:"Leituras por validar",BLOCKED_MISSING_TELEMETRY:"Faltam leituras necessárias",BLOCKED_BATTERY_CONFIGURATION:"Falta configurar a bateria",BLOCKED_FORECAST_UNAVAILABLE:"Previsão indisponível",WAITING_FOR_BATTERY_RESERVE:"A proteger a reserva da bateria",WAITING_FOR_BATTERY:"A carregar a bateria antes das cargas",PLAN_READY:"Pronto para gerir cargas",BLOCKED_INTEGRATION_READ:"Um dispositivo não respondeu",COMPLETED:"Ciclo concluído"};
  const actionLabels={ON:"Ligado",TARGET:"Ajustar potência",WAITING_FOR_SURPLUS:"À espera de excedente",BELOW_MINIMUM_SURPLUS:"Excedente abaixo do mínimo",BLOCKED_RELAY_NOT_READY:"Interruptor por confirmar",BLOCKED_RELAY_UNCONFIRMED:"Interruptor não confirmou",BLOCKED_STATE_UNKNOWN:"Estado desconhecido",BLOCKED_SHARED_METER:"Medidor partilhado",STOP_FOR_BATTERY:"Parado para carregar a bateria",OFF_FOR_BATTERY:"Desligado para carregar a bateria",STOP_FOR_TESLA_HOME:"Parado enquanto Tesla está em casa",OFF_FOR_TESLA_HOME:"Desligado enquanto Tesla está em casa",OFF_TESLA_AWAY:"Desligado · Tesla ausente",BLOCKED_CONTROL_UNAVAILABLE:"Controlo indisponível",SKIPPED_MANUAL:"Controlo manual",FAILED:"Falhou",APPLIED:"Aplicado",UNCONFIRMED:"Sem confirmação",UNCHANGED:"Sem alteração",ALREADY_AT_TARGET:"Já está nesse estado"};
  const status=live?(stateLabels[plan.state]||plan.state||"Sem avaliação"):"Demonstração local";
  const forecastW=live?summary.forecast_surplus_w:Math.max(0,Number(demo.potential)-Number(demo.house));
  const usableSurplus=Number.isFinite(Number(current.pv_power_w))&&Number.isFinite(Number(current.load_power_w))?Math.max(0,Number(current.pv_power_w)-Number(current.load_power_w)+Number(current.battery_power_w||0)-Number(automation.surplus_margin_w||0)):null;
  const fmt=(value,digits=0)=>value==null||!Number.isFinite(Number(value))?"—":new Intl.NumberFormat("pt-PT",{maximumFractionDigits:digits}).format(Number(value));
  const humanAction=action=>actionLabels[action.state]||String(action.state||"Sem estado").replaceAll("_"," ").toLowerCase();
  const latestActions=actions.length?`<div class="surplus-action-list">${actions.map(action=>`<article class="surplus-action-row"><strong>${esc(action.name||loads.find(load=>load.id===action.load_id)?.name||action.load_id)}</strong><span>${esc(humanAction(action))}</span><small>${Number.isFinite(action.target_power_w)?`${fmt(action.target_power_w)} W`:esc(action.reason||protocolLabels[action.control_type]||"")}</small></article>`).join("")}</div>`:`<div class="empty-state">Ainda não há uma decisão do motor.</div>`;
  const loadRows=loads.length?`<div class="surplus-load-list">${loads.map((load,index)=>{const action=actionByLoad.get(load.id);return `<article class="surplus-load-row"><span class="surplus-load-order">${index+1}</span><div><strong>${esc(load.name)}</strong><small>${esc(labels[load.kind]||load.kind)} · ${fmt(load.rated_power_w)} W nominal</small></div><div class="surplus-load-state"><strong>${load.enabled===false?"Desativada":load.automatic?"Automática":"Manual"}</strong><small>${action?esc(humanAction(action)):"Sem alteração recente"}</small></div></article>`}).join("")}</div>`:`<div class="empty-state">Ainda não existem cargas flexíveis configuradas. As AQS que já estão guardadas em Energy aparecerão aqui.</div>`;
  const linksRows=loads.length?`<div class="surplus-load-list">${loads.map(load=>{const device=devices.find(item=>item.device_id===load.tuya_device_id),codeMap=load.tuya_measurement_codes||{},mapping=Object.entries(codeMap).map(([field,code])=>`${esc({voltage:"Tensão",current:"Corrente",power:"Potência",energy:"Energia"}[field]||field)} · ${esc(code)}`).join(" · ");return `<article class="surplus-load-row"><div><strong>${esc(load.name)}</strong><small>Protocolo: ${esc(protocolLabels[load.control_type]||load.control_type||"Por indicar")}</small><small>Comando: ${device?esc(device.name):load.tuya_device_id?"Dispositivo sem nome local":"Sem dispositivo associado"}${load.tuya_switch_code?` · Canal ${esc(load.tuya_switch_code)}`:""}</small><small>Mapa de leituras: ${mapping||"Sem grandezas confirmadas"}</small></div><span class="source-tag">${load.tuya_device_id?"ASSOCIADO":"POR CONFIGURAR"}</span></article>`}).join("")}</div>`:`<div class="empty-state">As ligações e mapas aparecem quando uma carga já tiver um dispositivo associado.</div>`;
  const orderedRows=ordered.length?`<ol class="surplus-priority-list">${ordered.map(load=>`<li><span>${esc(labels[load.kind]||load.kind)}</span><strong>${esc(load.name)}</strong>${live&&isOwner?`<label class="feature-field">Prioridade<input type="number" min="1" max="100" step="1" value="${esc(String(load.priority||10))}" data-load-priority="${esc(load.id)}"></label>`:""}<small>${load.kind==="ev_charger"?"Tesla ainda sem controlo de carregamento":load.automatic&&load.enabled?"Elegível quando as condições permitem":"Registada, mas fora da gestão automática"}</small></li>`).join("")}</ol>${live&&isOwner?`<div class="ws-actions"><button type="button" class="button primary" id="surplus-save-priorities">Guardar prioridades</button><span id="surplus-priority-status" class="ws-inline-note" role="status" aria-live="polite"></span></div>`:""}`:`<div class="empty-state">Configura primeiro as cargas em Gestão de excedentes → Cargas. O motor não inventa equipamentos nem prioridades.</div>`;
  const tabs=[["status","Estado"],["loads","Cargas"],["links","Ligações e mapas"],["priority","Prioridades"],["rules","Regras"]];
  return `<div class="page-heading"><div><p class="eyebrow">ENERGY · CONTROLO AUTOMÁTICO</p><h1>Gestão de excedentes</h1><p>O Engine mede e prevê; este motor decide quando gerir as cargas configuradas.</p></div>${live?`<button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button>`:`<span class="source-tag">DEMO · SEM COMANDOS</span>`}</div>
  <nav class="ws-horizontal-tabs surplus-tabs" role="tablist" aria-label="Secções da gestão de excedentes">${tabs.map(([id,label])=>`<button type="button" role="tab" data-surplus-tab="${id}" aria-controls="surplus-panel-${id}" aria-selected="${surplusActiveTab===id}" class="${surplusActiveTab===id?"selected":""}">${label}</button>`).join("")}</nav>
  <section id="surplus-panel-status" role="tabpanel" data-surplus-panel="status"><section class="panel feature-panel surplus-status-card"><div class="panel-header"><div><p class="eyebrow">ESTADO DO MOTOR</p><h2>${esc(status)}</h2></div><span class="source-tag">${live&&manager.enabled&&automation.enabled?"AUTOMÁTICO":"PAUSADO"}</span></div><p>${esc(plan.reason|| (live?"Sem bloqueios reportados pelo Gateway.":"A demonstração não comunica com equipamentos."))}</p>${live?`<div class="surplus-input-summary"><div><small>Excedente previsto</small><strong>${fmt(forecastW)} W</strong></div><div><small>Excedente medido disponível</small><strong>${fmt(usableSurplus)} W</strong></div><div><small>Reserva da bateria</small><strong>${fmt(manager.battery_reserve_soc_percent??70)}%</strong></div><div><small>Tesla na rede</small><strong>${presence.state==="DETECTED"?"Detetado":presence.state==="NOT_DETECTED"?"Ausente":"Sem confirmação"}</strong></div></div>`:`<p>Os valores da simulação são locais e não enviam comandos.</p>`}</section><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">ÚLTIMO PLANO</p><h2>${esc(stateLabels[plan.state]||plan.state||"Sem plano")}</h2></div><span class="source-tag">${engine.dispatch_execution?.occurred_at?`Atualizado ${esc(timeLabel(engine.dispatch_execution.occurred_at))}`:"A aguardar ciclo"}</span></div>${latestActions}</section>${!live?`<section class="panel feature-panel"><h2>Simular condições</h2><div class="ws-config-grid"><label class="feature-field">Perfil<select id="surplus-demo-profile"><option value="tesla_home" ${demo.profile==="tesla_home"?"selected":""}>Tesla em casa</option><option value="tesla_away" ${demo.profile==="tesla_away"?"selected":""}>Tesla ausente</option></select></label><label class="feature-field">FV potencial (W)<input id="surplus-demo-pv" type="number" min="0" max="30000" step="100" value="${esc(String(demo.potential))}"></label><label class="feature-field">Consumo previsto da casa (W)<input id="surplus-demo-house" type="number" min="0" max="30000" step="100" value="${esc(String(demo.house))}"></label><label class="feature-field">SOC da bateria (%)<input id="surplus-demo-soc" type="number" min="0" max="100" step="1" value="${esc(String(demo.battery))}"></label></div><div class="ws-actions"><button class="button primary" id="surplus-demo-run">Simular decisão</button><span id="surplus-demo-result" class="ws-inline-note" aria-live="polite">A simulação só altera esta página.</span></div></section>`:""}</section>
  <section id="surplus-panel-loads" role="tabpanel" data-surplus-panel="loads" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">IDENTIFICAÇÃO E LIGAÇÕES</p><h2>Cargas configuradas</h2></div><span class="source-tag">${loads.length} CONFIGURADAS</span></div><p class="field-note">Aqui podes consultar e acrescentar cargas; as alterações são guardadas diretamente no Gateway.</p>${loadRows}${live&&isOwner?renderLoadBuilder():""}<p id="engine-equipment-config-status" class="ws-inline-note" role="status" aria-live="polite"></p></section></section><section id="surplus-panel-links" role="tabpanel" data-surplus-panel="links" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">PROTOCOLOS E MAPAS</p><h2>Ligações usadas pelo motor</h2></div></div><p class="field-note">Consulta que protocolo, interruptor e mapa de leituras o Gateway usa para cada carga.</p>${linksRows}</section></section>
  <section id="surplus-panel-priority" role="tabpanel" data-surplus-panel="priority" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">ORDEM APLICADA PELO GATEWAY</p><h2>Prioridades das cargas</h2></div></div>${live&&isOwner?`<label class="feature-field">Perfil de prioridade<select id="surplus-profile"><option value="tesla_home" ${profile==="tesla_home"?"selected":""}>Tesla em casa · conforto primeiro</option><option value="tesla_away" ${profile==="tesla_away"?"selected":""}>Tesla ausente · mineradora primeiro</option><option value="custom" ${profile==="custom"?"selected":""}>Personalizada · usar os números abaixo</option></select><small>No perfil Personalizada, os menores números têm prioridade e a deteção Tesla não altera a tua ordem.</small></label>`:`<p class="field-note">Perfil em uso: ${esc(summary.effective_priority_profile||profile)}.</p>`}<p class="field-note">Podes editar a prioridade de cada carga. No perfil Personalizada, a ordem numérica é usada diretamente pelo Gateway.</p>${orderedRows}</section></section>
  <section id="surplus-panel-rules" role="tabpanel" data-surplus-panel="rules" hidden><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">CONDIÇÕES PARA LIGAR CARGAS</p><h2>Regras e proteções</h2></div></div>${live&&!isOwner?`<div class="empty-state">Só o Owner pode alterar estas regras.</div>`:`<div class="ws-config-grid"><label class="feature-field">Excedente previsto mínimo (W)<input id="surplus-minimum" type="number" min="0" max="100000" step="100" value="${live?esc(String(manager.minimum_potential_surplus_w??800)):"1000"}" ${isOwner?"":"disabled"}><small>Abaixo deste valor, o motor não inicia cargas automáticas.</small></label><label class="feature-field">Reserva mínima da bateria (%)<input id="surplus-reserve" type="number" min="0" max="100" step="1" value="${live?esc(String(manager.battery_reserve_soc_percent??70)):"70"}" ${isOwner?"":"disabled"}><small>O motor protege primeiro esta reserva.</small></label><label class="feature-field">Margem de segurança (W)<input id="surplus-margin" type="number" min="0" max="10000" step="50" value="${live?esc(String(automation.surplus_margin_w??250)):"300"}" ${isOwner?"":"disabled"}><small>Descontada ao excedente antes de qualquer ordem.</small></label></div><fieldset class="surplus-enable"><legend>Ativação e comissionamento</legend><label><input id="surplus-enabled" type="checkbox" ${manager.enabled?"checked":""} ${isOwner?"":"disabled"}> Permitir gestão automática</label><label><input id="surplus-commissioned" type="checkbox" ${automation.commissioned?"checked":""} ${isOwner?"":"disabled"}> Confirmo que as cargas e limites foram configurados</label><label><input id="surplus-map-verified" type="checkbox" ${automation.deye_map_verified?"checked":""} ${isOwner?"":"disabled"}> Confirmo que validei o mapa Deye e o sentido dos sinais</label></fieldset><div class="ws-actions"><button class="button primary" id="surplus-save" ${isOwner?"":"disabled"}>Guardar regras</button>${manager.manual_override?`<button class="button secondary" id="surplus-resume" ${isOwner?"":"disabled"}>Retomar automático</button>`:""}<span id="surplus-save-status" class="ws-inline-note" role="status"></span></div>`}</section><section class="panel feature-panel"><h2>Quando o motor não executa</h2><p class="field-note">O Gateway bloqueia ordens quando faltam leituras atuais, configuração da bateria, margem de segurança, mapa Deye validado ou confirmação do dispositivo. O carregador Tesla permanece apenas em leitura até existir controlo suportado.</p></section></section>`;
}
async function loadGatewayUserAutomations({quiet=false}={}){
  if(!sessionInfo().authenticated||state.mode==="SIMULATED"||state.userAutomations.loading)return userAutomationLoadPromise;
  state.userAutomations.loading=true;state.userAutomations.error="";if(!quiet)render();
  userAutomationLoadPromise=(async()=>{try{const result=await readGatewayUserAutomations();state.userAutomations={loading:false,error:"",rules:Array.isArray(result.rules)?result.rules:[],history:Array.isArray(result.history)?result.history:[],capabilities:result.capabilities||{triggers:[],targets:[]},engine:result.engine||{}};}catch(error){state.userAutomations={...state.userAutomations,loading:false,error:error.message||"Consulta falhada"};}finally{userAutomationLoadPromise=null;if(state.page==="automatismos")render();}})();
  return userAutomationLoadPromise;
}
function renderUserAutomationForm(){
  const data=state.userAutomations||{},rules=data.rules||[],caps=data.capabilities||{},triggers=caps.triggers||[],targets=caps.targets||[],isOwner=sessionInfo().user?.role==="owner",editing=rules.find(item=>item.id===userAutomationEditingId),schedule=editing?.trigger?.type==="schedule",triggerId=schedule?"schedule":editing?`tuya|${editing.trigger.device_id}|${editing.trigger.code}`:"",actions=editing?.actions?.length?editing.actions:editing?.action?[editing.action]:[{}];
  const triggerOptions=[`<option value="schedule" ${schedule?"selected":""}>Horário local do Gateway</option>`,...triggers.map(item=>`<option value="${esc(item.id)}" data-type="${esc(item.type)}" ${triggerId===item.id?"selected":""}>${esc(item.name)} · ${esc(item.label)} (${esc(item.code)})</option>`)].join("");
  const renderActionRow=action=>{const selectedId=action?.target_type==="tuya"?`tuya|${action.device_id}|${action.code}`:action?.operation==="brightness"?`shelly-light|${action.device_id}|${action.component}|${action.channel}`:action?.target_type?`shelly|${action.device_id}|${action.channel}`:(targets[0]?.id||""),targetOptions=targets.map(item=>`<option value="${esc(item.id)}" data-kind="${esc(item.type)}" ${selectedId===item.id?"selected":""}>${esc(item.label)}</option>`).join(""),brightness=action?.operation==="brightness"||(!action?.target_type&&targets[0]?.type==="shelly_light");return `<div data-auto-action-row class="feature-extra-row"><label class="feature-field">Destino<select data-auto-target required>${targetOptions||"<option value=\"\">Sem saídas locais disponíveis</option>"}</select></label><div data-auto-row-switch ${brightness?"hidden":""} class="feature-field"><label>Comando<select data-auto-switch-state><option value="on" ${action?.on===true?"selected":""}>Ligar</option><option value="off" ${action?.on===false?"selected":""}>Desligar</option></select></label></div><div data-auto-row-brightness ${brightness?"":"hidden"} class="feature-field"><label>Definir luminosidade (%)<input data-auto-percent type="number" min="0" max="100" step="1" value="${esc(String(action?.percent??50))}"></label></div>${actions.length>1?`<button class="button secondary" type="button" data-user-auto="remove-action">Remover ação</button>`:""}</div>`;};
  const weekdays=["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"],days=editing?.trigger?.weekdays||[0,1,2,3,4,5,6];
  return `<section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">CRIAR REGRA</p><h2>${editing?"Editar automatismo":"Novo automatismo"}</h2></div><span class="source-tag">${isOwner?"GUARDADO NO GATEWAY":"SÓ DE LEITURA"}</span></div>${isOwner?`<form id="gateway-auto-rule-form" class="ws-config-grid"><label class="feature-field">Nome<input name="automation-name" maxlength="100" required value="${esc(editing?.name||"")}" placeholder="Ex.: luz do corredor à noite"></label><label class="feature-field">Quando<select name="automation-trigger" required>${triggerOptions}</select><small>Por estado usa uma leitura Tuya LAN recente e confirmada; por horário usa a hora local configurada no Debian.</small></label><div data-auto-state-fields ${schedule?"hidden":""} class="feature-field"><label>Comparação<select name="automation-operator"><option value="eq" ${editing?.trigger?.operator==="eq"?"selected":""}>é igual a</option><option value="ne" ${editing?.trigger?.operator==="ne"?"selected":""}>é diferente de</option><option value="gt" ${editing?.trigger?.operator==="gt"?"selected":""}>é maior que</option><option value="gte" ${editing?.trigger?.operator==="gte"?"selected":""}>é pelo menos</option><option value="lt" ${editing?.trigger?.operator==="lt"?"selected":""}>é menor que</option><option value="lte" ${editing?.trigger?.operator==="lte"?"selected":""}>é no máximo</option></select></label><label class="feature-field">Valor observado<input name="automation-value" maxlength="128" value="${esc(String(editing?.trigger?.value??"true"))}" required><small>Booleanos: true ou false. Estados enumerados: texto exato. Leituras numéricas: número.</small></label><label class="feature-field">Manter a condição por (segundos)<input name="automation-for" type="number" min="0" max="86400" step="1" value="${esc(String(editing?.trigger?.for_seconds??0))}"></label></div><div data-auto-schedule-fields ${schedule?"":"hidden"} class="feature-field"><label class="feature-field">Hora<input name="automation-time" type="time" value="${esc(editing?.trigger?.at||"20:00")}"></label><fieldset class="surplus-enable"><legend>Dias da semana</legend>${weekdays.map((day,index)=>`<label><input type="checkbox" name="automation-day" value="${index}" ${days.includes(index)?"checked":""}> ${day}</label>`).join("")}</fieldset></div><div class="feature-field"><strong>Então executar estas ações, por ordem</strong><small>Máximo de oito ações; o Gateway guarda e regista cada ciclo.</small><div data-auto-action-list>${actions.map(renderActionRow).join("")}</div><button class="button secondary" type="button" data-user-auto="add-action">Adicionar outra ação</button></div><label class="feature-field"><span><input name="automation-enabled" type="checkbox" ${editing?.enabled?"checked":""}> Ativar assim que guardar</span><small>Regras novas ficam desligadas, a menos que escolhas ativar.</small></label><div class="ws-actions"><button class="button secondary" type="button" id="gateway-auto-dry-run">Simular condição</button><button class="button primary" type="submit">${editing?"Guardar alterações":"Criar automatismo"}</button>${editing?`<button class="button secondary" type="button" data-user-auto="cancel-edit">Cancelar edição</button>`:""}<span id="gateway-auto-form-status" class="ws-inline-note" role="status" aria-live="polite"></span></div></form>`:`<div class="empty-state">Só o Owner pode criar, editar ou ativar automatismos.</div>`}</section>`;
}
const AUTOMATION_MENU_TRIGGERS=[
  {id:"tap",title:"TOCAR PARA EXECUTAR",icon:"▣",ready:true},
  {id:"status",title:"QUANDO O STATUS DO DISPOSITIVO MUDA",icon:"◉",ready:true},
  {id:"schedule",title:"AGENDA",icon:"◷"},
  {id:"weather",title:"QUANDO O TEMPO MUDA",icon:"☼"},
  {id:"location",title:"QUANDO A LOCALIZAÇÃO MUDA",icon:"⌖"},
  {id:"alarm",title:"QUANDO O ALARME É ACIONADO",icon:"♧"},
  {id:"disaster",title:"AVISO DE CATÁSTROFE",icon:"⚠"}
];
function automationPreviewNotice(){return `<p class="field-note automation-prototype-note">Pré-visualização do submenu. As escolhas ainda não guardam nem executam automatismos.</p>`;}
function automationMenuHeader(title,back="create",next=""){
  return `<div class="automation-prototype-header"><button type="button" class="button secondary automation-prototype-back" data-automation-menu="${back}" aria-label="Voltar" title="Voltar"><span aria-hidden="true">‹</span></button><h2>${esc(title)}</h2>${next?`<button type="button" class="automation-prototype-next" data-automation-menu="${next}" aria-label="Próximo" title="Próximo"><span aria-hidden="true">›</span></button>`:`<span class="automation-prototype-next-spacer" aria-hidden="true"></span>`}</div>`;
}
function automationMenuRows(rows,{disabled=true}={}){
  return `<div class="automation-prototype-list">${rows.map((row,index)=>`<button type="button" class="automation-prototype-row" ${disabled?"disabled":""} ${row.action?`data-automation-menu="${esc(row.action)}"`:""}><span>${row.icon?`<span class="automation-prototype-icon" aria-hidden="true">${row.icon}</span>`:""}<strong>${esc(row.title)}</strong>${row.subtitle?`<small>${esc(row.subtitle)}</small>`:""}</span><span class="automation-prototype-chevron" aria-hidden="true">›</span></button>`).join("")}</div>`;
}
function renderAutomationPrototypeMenu(){
  const view=userAutomationMenuView;
  if(view==="create"){
    const rows=AUTOMATION_MENU_TRIGGERS.map(item=>({title:item.title,icon:item.icon,subtitle:item.ready?"": "Pré-visualização ainda não preparada",action:item.ready?`open:${item.id}`:""}));
    return `${automationMenuHeader("CRIAR AUTOMAÇÃO","list")}<section class="panel feature-panel"><p class="field-note">Escolhe o que inicia a automatização.</p>${automationMenuRows(rows,{disabled:false})}</section>${automationPreviewNotice()}`;
  }
  if(view==="tap"){
    const actionRows=userAutomationPreviewActions.map((action,index)=>`<button type="button" class="automation-condition-row" data-automation-remove-action="${index}"><span><strong>${esc(action.title)}</strong><small>${esc(action.summary)}</small></span><span class="automation-prototype-chevron" aria-hidden="true">×</span></button>`).join("");
    return `${automationMenuHeader("CRIAR TOCAR PARA EXECUTAR")}<section class="panel feature-panel automation-tap-task"><button type="button" class="automation-tap-action-heading" data-automation-menu="tap-actions"><span>Então</span><span class="automation-prototype-chevron" aria-hidden="true">›</span></button><button type="button" class="button primary" data-automation-menu="tap-actions" aria-label="Adicionar tarefa">+</button>${actionRows||`<button type="button" class="automation-task-placeholder" data-automation-menu="tap-actions">Adic. Tarefa</button>`}</section><section class="panel feature-panel"><button type="button" class="automation-prototype-row" data-automation-menu="tap-area"><strong>Mostrar área</strong><span class="automation-prototype-chevron">›</span></button></section><button type="button" class="button primary automation-prototype-save" disabled>Guardar</button>${automationPreviewNotice()}`;
  }
  if(view==="tap-actions"){
    const rows=[
      {id:"device",title:"Controlar um dispositivo",subtitle:"Ligar, desligar ou alterar um dispositivo",icon:"💡"},
      {id:"scene",title:"Selecionar / ativar automatismos",subtitle:"Ativar ou desativar outros automatismos",icon:"✓"},
      {id:"delay",title:"Atrasar a ação",subtitle:"Adicionar um temporizador antes da próxima ação",icon:"◷"},
      {id:"notification",title:"Enviar notificação",subtitle:"Enviar um aviso",icon:"✉"},
      {id:"activation",title:"Alterar modo de ativação",subtitle:"Mudar o modo de ativação",icon:"✓"}
    ];
    return `${automationMenuHeader("Adicionar tarefa",userAutomationActionReturnView)}<section class="panel feature-panel">${automationMenuRows(rows.map(row=>({...row,action:`action-select:${row.id}`})),{disabled:false})}</section>${automationPreviewNotice()}`;
  }
  if(view==="tap-area"){
    const areas=["Não agrupado","Sala Verde","Rússia","São Tomé","Cozinha","Copa","Exterior","Escadas/Corredor","Sala da Música","WC Grande","Equipamentos"];
    return `${automationMenuHeader("Área de exibição","tap")}<section class="panel feature-panel"><h3>Não agrupado</h3>${automationMenuRows(areas.map(title=>({title})))}</section><button type="button" class="button primary automation-prototype-save" disabled>Concluído</button>${automationPreviewNotice()}`;
  }
  if(view==="status-device"){
    const triggerIds=new Set((state.userAutomations?.capabilities?.triggers||[]).map(item=>item.device_id));
    const devices=(state.tuyaDevices||[]).map(tuyaDeviceWithPidMap).filter(device=>triggerIds.has(device.device_id));
    const favoriteIds=new Set(workspace.prefs.favoriteDeviceIds||[]),meta=favoriteMeta(),divisionFor=device=>String(meta[device.device_id]?.room||device.room||device.location||device.area||"").trim(),divisions=[...new Set(devices.map(divisionFor).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pt")),allButton=(id,label)=>`<button type="button" class="automation-filter-pill ${userAutomationStatusFilter===id?"selected":""}" data-automation-menu="status-filter:${encodeURIComponent(id)}" aria-pressed="${userAutomationStatusFilter===id}">${esc(label)}</button>`,tabs=[allButton("favorites","Favoritos"),...divisions.map(division=>allButton(`division:${division}`,division)),allButton("all","Todos os dispositivos")],visibleDevices=userAutomationStatusFilter==="all"?devices:userAutomationStatusFilter.startsWith("division:")?devices.filter(device=>divisionFor(device)===userAutomationStatusFilter.slice("division:".length)):devices.filter(device=>favoriteIds.has(device.device_id)),rows=visibleDevices.map(device=>({title:device.name||device.device_id,action:`device:${device.device_id}`})),emptyText=devices.length?userAutomationStatusFilter==="favorites"?"Ainda não tens favoritos com estados disponíveis para usar como trigger. Escolhe uma divisão ou “Todos os dispositivos”.":"Não há dispositivos com estados disponíveis nesta seleção.":"Não há dispositivos com estados Tuya Cloud legíveis registados no Gateway.";
    return `${automationMenuHeader("Selecionar dispositivo","create")}<section class="panel feature-panel"><nav class="automation-filter-pills" aria-label="Filtrar dispositivos">${tabs.join("")}</nav>${rows.length?automationMenuRows(rows,{disabled:false}):`<div class="empty-state">${emptyText}</div>`}</section>${automationPreviewNotice()}`;
  }
  if(view.startsWith("status-functions:")){
    const deviceId=view.slice("status-functions:".length),device=tuyaDeviceWithPidMap((state.tuyaDevices||[]).find(item=>item.device_id===deviceId)),triggers=(state.userAutomations?.capabilities?.triggers||[]).filter(item=>item.device_id===deviceId);
    const specs=[...(device?.status_spec||[])];
    const rows=triggers.map(trigger=>{const spec=specs.find(item=>item.code===trigger.code);if(!spec)return null;let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}const limits=values.range??spec.range??(Number.isFinite(Number(values.min))&&Number.isFinite(Number(values.max))?values:undefined),declared=Array.isArray(limits)?limits.length>0:typeof limits==="string"?limits.trim().length>0:!!(limits&&typeof limits==="object"&&Number.isFinite(Number(limits.min))&&Number.isFinite(Number(limits.max)));if(!declared)return null;const label=tuyaFriendlyCapabilityLabel({...spec,code:spec.code||trigger.code,name:spec.name||trigger.label||trigger.code},device);return {title:label,action:`function:${deviceId}|${trigger.code}`};}).filter(Boolean);
    return `${automationMenuHeader("Selecione a função","status-device")}<section class="panel feature-panel">${rows.length?automationMenuRows(rows,{disabled:false}):`<div class="empty-state">A Cloud não declarou estados compatíveis para este dispositivo.</div>`}</section>${automationPreviewNotice()}`;
  }
  if(view.startsWith("status-value:")){
    const [deviceId,code]=view.slice("status-value:".length).split("|");
    const device=tuyaDeviceWithPidMap((state.tuyaDevices||[]).find(item=>item.device_id===deviceId)),spec=(device?.status_spec||[]).find(item=>item.code===code)||{},type=String(spec.type||"").toLowerCase();
    let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}
    let declaredRange=values.range??spec.range??values.enum_range??(Number.isFinite(Number(values.min))&&Number.isFinite(Number(values.max))?values:[]);if(typeof declaredRange==="string"){try{declaredRange=JSON.parse(declaredRange)}catch{declaredRange=[];}}
    const isNumeric=["value","integer","number","numeric"].includes(type),isBoolean=["bool","boolean"].includes(type),bounds=declaredRange&&typeof declaredRange==="object"&&!Array.isArray(declaredRange)?declaredRange:values&&typeof values==="object"?values:{};
    const draft=userAutomationConditionDraft||{},numericBounds=Number.isFinite(Number(bounds.min))&&Number.isFinite(Number(bounds.max)),rangeMin=numericBounds?Number(bounds.min):0,rangeMax=numericBounds?Number(bounds.max):100,rangeStep=Number(bounds.step)||1,currentValue=draft.value??(Array.isArray(declaredRange)&&declaredRange.length?declaredRange[0]:rangeMin),selectedOperator=draft.operator||"lt";
    let control="";
    if(Array.isArray(declaredRange)&&declaredRange.length){control=automationMenuRows(declaredRange.map(value=>({title:tuyaEnumValuePt(value),action:`status-enum:${encodeURIComponent(String(value))}`})),{disabled:false});}
    else if(isNumeric&&numericBounds){
      const operators=[["lt","Menor que"],["eq","Igual"],["gt","Maior que"]];
      control=`<section class="automation-range-preview"><div class="automation-operator-list" role="group" aria-label="Comparação">${operators.map(([value,label])=>`<button type="button" class="${selectedOperator===value?"selected":""}" data-automation-operator="${value}" aria-pressed="${selectedOperator===value}">${label}</button>`).join("")}</div><label><span>Valor</span><output data-preview-range-value>${esc(String(currentValue))}</output> <span>${esc(String(bounds.unit||""))}</span><input type="range" data-automation-range min="${esc(String(rangeMin))}" max="${esc(String(rangeMax))}" step="${esc(String(rangeStep))}" value="${esc(String(currentValue))}" aria-label="Valor do trigger"></label></section>`;
    }else if(isBoolean){control=`<div class="empty-state">A Cloud declarou um valor booleano, mas não forneceu um range explícito de opções. Este submenu não cria opções por inferência.</div>`;}
    else{control=`<div class="empty-state">A Tuya Cloud não declarou opções ou limites utilizáveis para esta função.</div>`;}
    const title=tuyaFriendlyCapabilityLabel({...spec,code:spec.code||code},device);
    return `${automationMenuHeader(title,`status-functions:${deviceId}`,"status-next")}<section class="panel feature-panel">${control}</section>${automationPreviewNotice()}`;
  }
  if(view==="status-conditions"){
    const conditions=userAutomationPreviewConditions,modeLabel=userAutomationConditionMode==="all"?"Quando todas as condições forem cumpridas":"Quando qualquer condição for cumprida",modeOptions=userAutomationModeMenuOpen?`<div class="automation-condition-mode-options"><button type="button" data-automation-mode="all">Quando todas as condições forem cumpridas</button><button type="button" data-automation-mode="any">Quando qualquer condição for cumprida</button></div>`:"";
    const conditionRows=conditions.map((condition,index)=>`<button type="button" class="automation-condition-row" data-automation-edit-condition="${index}"><span><strong>${esc(condition.deviceName)}</strong><small>${esc(condition.functionLabel)} · ${esc(condition.operatorLabel)} ${esc(String(condition.value))}${condition.unit?` ${esc(condition.unit)}`:""}</small></span><span class="automation-prototype-chevron" aria-hidden="true">›</span></button>`).join("");
    const actionRows=userAutomationPreviewActions.map((action,index)=>`<button type="button" class="automation-condition-row" data-automation-remove-action="${index}"><span><strong>${esc(action.title)}</strong><small>${esc(action.summary)}</small></span><span class="automation-prototype-chevron" aria-hidden="true">×</span></button>`).join("");
    return `${automationMenuHeader("Criar cena","create")}<section class="panel feature-panel automation-condition-section"><div class="panel-header"><div><h2>Se</h2><button type="button" class="automation-condition-mode" data-automation-menu="status-mode-toggle" aria-expanded="${userAutomationModeMenuOpen}">${esc(modeLabel)} <span aria-hidden="true">⌄</span></button>${modeOptions}</div><button type="button" class="button primary" data-automation-menu="status-add" aria-label="Adicionar condição">+</button></div>${conditionRows||`<div class="empty-state">Ainda não há condições.</div>`}</section><section class="panel feature-panel automation-tap-task"><button type="button" class="automation-tap-action-heading" data-automation-menu="tap-actions"><span>Então</span><span class="automation-prototype-chevron" aria-hidden="true">›</span></button><button type="button" class="button primary" data-automation-menu="tap-actions" aria-label="Adicionar tarefa">+</button>${actionRows||`<button type="button" class="automation-task-placeholder" data-automation-menu="tap-actions">Adic. Tarefa</button>`}</section><section class="panel feature-panel"><button type="button" class="automation-prototype-row" data-automation-menu="tap-area"><strong>Âmbito de validade</strong><span>Dia todo</span><span class="automation-prototype-chevron">›</span></button></section><section class="panel feature-panel"><button type="button" class="automation-prototype-row" data-automation-menu="tap-area"><strong>Mostrar área</strong><span class="automation-prototype-chevron">›</span></button></section><button type="button" class="button primary automation-prototype-save" disabled>Guardar</button>${automationPreviewNotice()}`;
  }
  return "";
}
function renderUserAutomationPage(){
  const data=state.userAutomations||{},rules=data.rules||[],history=data.history||[],engine=data.engine||{},status=rules.filter(item=>item.enabled).length;
  if(data.loading)return `<div class="page-heading"><div><p class="eyebrow">GATEWAY · REGRAS PESSOAIS</p><h1>Automatismos</h1><p>A carregar regras e equipamentos locais…</p></div></div>`;
  if(userAutomationMenuView)return `<div class="page-heading"><div><p class="eyebrow">GATEWAY · REGRAS PESSOAIS</p><h1>Automatismos</h1></div></div>${renderAutomationPrototypeMenu()}`;
  if(userAutomationEditingId)return `<div class="page-heading"><div><p class="eyebrow">GATEWAY · REGRAS PESSOAIS</p><h1>Automatismos</h1></div></div>${renderUserAutomationForm()}`;
  const rows=rules.length?rules.map(rule=>{const when=rule.trigger?.type==="schedule"?`Agenda · ${rule.trigger.at||"hora definida"}`:`${rule.trigger?.code||"Estado do dispositivo"} ${({eq:"=",ne:"≠",gt:">",gte:"≥",lt:"<",lte:"≤"})[rule.trigger?.operator]||"="} ${String(rule.trigger?.value??"")}`,actions=(rule.actions||[rule.action]).filter(Boolean).map(action=>action?.target_type==="tuya"?`Tuya ${action.on?"ligar":"desligar"} · ${action.code}`:action?.operation==="brightness"?`Shelly luminosidade ${action.percent}%`:`Shelly ${action?.on?"ligar":"desligar"} · canal ${(action?.channel??0)+1}`).join(" → ");return `<article class="panel user-automation-card"><div class="user-automation-card-top"><span class="user-automation-trigger-icon" aria-hidden="true">${rule.trigger?.type==="schedule"?"☼":"◉"}</span><button class="user-automation-edit" type="button" data-user-auto="edit" data-id="${esc(rule.id)}" aria-label="Editar ${esc(rule.name)}">›</button></div><div class="user-automation-card-copy"><h2>${esc(rule.name)}</h2><p>${esc(when)}</p>${actions?`<small>${esc(actions)}</small>`:""}</div><div class="user-automation-card-bottom"><span class="source-tag">${rule.enabled?"ATIVA":"DESLIGADA"}</span>${sessionInfo().user?.role==="owner"?`<label class="user-automation-switch" aria-label="${rule.enabled?"Desativar":"Ativar"} ${esc(rule.name)}"><input type="checkbox" data-user-auto-toggle="${esc(rule.id)}" ${rule.enabled?"checked":""}><span></span></label>`:`<span class="source-tag">SÓ LEITURA</span>`}</div></article>`;}).join(""):`<div class="empty-state">Ainda não há automatismos. Usa + para explorar os submenus de criação em pré-visualização.</div>`;
  const events=history.length?`<div class="surplus-load-list">${history.map(item=>`<article class="surplus-load-row"><div><strong>${esc(item.rule_name)} · ${esc(item.outcome)}</strong><small>${esc(timeLabel(item.occurred_at))} · ${esc(item.reason)}</small></div><span class="source-tag">${esc(item.outcome.toUpperCase())}</span></article>`).join("")}</div>`:`<div class="empty-state">O histórico de execução aparecerá aqui.</div>`;
  return `<div class="page-heading user-automation-heading"><div><p class="eyebrow">GATEWAY · REGRAS PESSOAIS</p><h1>Automatismos</h1><p>Cenas e regras do utilizador. Este motor é independente da Gestão de excedentes.</p></div><div class="user-automation-heading-actions"><button class="button secondary" id="gateway-area-refresh" aria-label="Atualizar">↻</button><button class="button primary automation-add-button" type="button" data-automation-menu="create" aria-label="Adicionar automatismo">+</button></div></div>${data.error?`<section class="panel"><p class="field-note">Não foi possível carregar automatismos: ${esc(data.error)}</p></section>`:""}<section class="user-automation-list">${rows}</section><details class="panel feature-panel automation-engine-details"><summary>Motor local · ${status} ativa(s) · ${rules.length} / 100 regras</summary><p>O Gateway avalia as regras a cada ${esc(String(engine.evaluation_interval_seconds||5))} segundos, sem depender da PWA. Leitura máxima: ${esc(String(engine.stale_reading_limit_seconds||60))} s. ${data.capabilities?.triggers?.length||0} estados Tuya e ${data.capabilities?.targets?.length||0} saídas LAN disponíveis.</p></details>${rules.length?`<section class="panel feature-panel"><div class="panel-header"><h2>Execuções recentes</h2><span class="source-tag">${history.length} REGISTOS</span></div>${events}</section>`:""}`;
}
function renderGatewayUtilityPage(page){
  if(page==="devices")return renderDeviceInventoryPage();
  if(page==="automatismos"){
    if(!state.userAutomations.loading&&!state.userAutomations.engine&&!state.userAutomations.error&&sessionInfo().authenticated)queueMicrotask(()=>{if(state.page==="automatismos")void loadGatewayUserAutomations({quiet:true});});
    return renderUserAutomationPage();
  }
  if(page==="producao")return renderLiveEnergyEngine();
  if(page==="casa")return renderGatewayHousePage();
  const items=state.equipment||[];
  const user=sessionInfo().user||{};
  if(page==="profile")return `<div class="page-heading"><div><p class="eyebrow">CONTA DO GATEWAY</p><h1>Perfil</h1><p>Identidade e permissões confirmadas pelo Gateway nesta sessão.</p></div></div><section class="panel"><div class="device-detail-grid"><div class="detail-item"><small>Utilizador</small><strong>${esc(user.username||"—")}</strong></div><div class="detail-item"><small>Papel</small><strong>${esc(user.role||"—")}</strong></div><div class="detail-item"><small>Sessão</small><strong>${sessionInfo().authenticated?"Autenticada":"Sem sessão"}</strong></div><div class="detail-item"><small>Gateway</small><strong>${esc(state.mode==="LIVE"?"Ligado":"Indisponível")}</strong></div></div><p class="field-note">Permissões, utilizadores e dispositivos autorizados são geridos no Gateway. Preferências visuais deste browser não alteram essas permissões.</p><button class="button secondary" id="profile-open-gateway" type="button">Gerir ligação</button></section>`;
  const cards=items.filter(item=>page!=="devices"||! ["inversores","baterias"].includes(item.category)).map(item=>`<article class="panel detail-panel"><div class="panel-header"><div><p class="eyebrow">${esc(item.category||"EQUIPAMENTO")}</p><h2>${esc(item.name)}</h2></div><span class="source-tag">${esc(item.connection_state||item.status||"UNKNOWN")}</span></div><p>${esc([item.manufacturer,item.model,item.protocol].filter(Boolean).join(" · ")||"Sem detalhes de fabricante/modelo")}</p>${item.readings?.length?`<div class="device-detail-grid telemetry-grid">${item.readings.map(reading=>`<div class="detail-item"><small>${esc(reading.evidence?.label||reading.field)}</small><strong>${esc(formatReading(reading).value)} ${esc(reading.unit||"")}</strong><small>${esc(reading.trust||"UNKNOWN")}</small></div>`).join("")}</div>`:`<div class="empty-state">Sem leituras registadas.</div>`}</article>`).join("");
  const controlledInventory=page==="devices"?"<p>Equipamentos nesta lista podem ser controlados pelo Gateway. O Deye, as baterias e outros equipamentos de leitura ficam nas áreas de Energia.</p>":"<p>Equipamentos recebidos da base de dados do Gateway, agrupados nesta vista.</p>";
  const tuyaCards=page==="devices"?(state.tuyaDevices||[]).map(device=>{const channels=(Array.isArray(device.functions)?device.functions:[]).filter(item=>item&&["bool","boolean"].includes(String(item.type||"").toLowerCase()));const glyph=tuyaDeviceGlyph(device);return `<button type="button" class="panel detail-panel tuya-inventory-card" data-edit-tuya-device="${esc(device.device_id)}"><div class="panel-header"><div class="tuya-device-glyph" aria-hidden="true">${glyph}</div><div><p class="eyebrow">TUYA / MOES</p><h2>${esc(device.name)}</h2></div><span class="source-tag">${device.online===true?"ONLINE":device.online===false?"OFFLINE":"TUYA"}</span></div><p>${channels.length?`${channels.length} canal${channels.length===1?"":"is"} · `:""}${esc(device.room||"Sem divisão atribuída")}${device.floor?` · ${esc(device.floor)}`:""}</p><span class="text-link">Ver características e editar ↗</span></button>`;}).join(""):"";
  const emptyInventory=!cards&&!tuyaCards?`<div class="empty-state">Ainda não existem dispositivos registados no Gateway. Os inversores e baterias ficam nas áreas de Energia.</div>`:"";
  return `<div class="page-heading"><div><p class="eyebrow">${page==="devices"?"CONTROLO · GATEWAY":"INVENTÁRIO · GATEWAY"}</p><h1>${page==="casa"?"Casa":"Dispositivos"}</h1>${controlledInventory}</div>${page==="energia"?"":`<button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button>`}</div>${page==="devices"&&sessionInfo().user?.role==="owner"?`<section class="panel"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO</p><h2>Dispositivos sincronizados</h2></div><button class="button secondary" data-page="owner">Abrir gestão Owner</button></div><p class="field-note">Toca num dispositivo para editar os nomes dos canais e atribuir uma divisão. Estas alterações ficam no Gateway e não mudam nomes na conta Tuya.</p></section>`:""}<div class="equipment-grid">${cards}${tuyaCards}${emptyInventory}</div>`;
}
function isShellyBluBridge(device){
  const identity=[device?.device_type,device?.model,device?.name].filter(Boolean).join(" ").toLowerCase();
  return ["smart_blugw","smart_gateway"].includes(String(device?.device_type||""))||/blu\s*gateway|blu\s*gw|blugw|gwf-kz01|sn[\s-]*gw[\s-]*bt01|sngw-bt01/.test(identity);
}
function openShellyDimmerReference(device){
  const dimmers=(device.components||[]).filter(item=>["light","rgb","rgbw","cct","color"].includes(item.component));
  if(!dimmers.length)return false;
  const dialog=document.createElement("dialog"),admin=sessionInfo().user?.role==="owner",connected=device.connection_state==="connected",menuOrder=deviceCardPopupMenuOrder(deviceCardTemplate("shelly",device.model||device.device_type||""));
  const glyphs={notifications:'<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',charts:'<path d="M4 19V5M4 19h16M7 15l4-4 3 3 5-6"/>',log:'<rect x="6" y="3" width="13" height="18" rx="2"/><path d="M9 7h7M9 11h7M9 15h5M4 6v14"/>',timer:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/>',calendar:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 9h16"/>',night:'<path d="M19.2 15.3A8 8 0 0 1 8.7 4.8a8.5 8.5 0 1 0 10.5 10.5Z"/>',links:'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',web:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',automations:'<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.5m-7.6 7.9 7.6 4.5"/>',share:'<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6m-7.6 6 7.6 3.6"/>',settings:'<circle cx="12" cy="12" r="3"/><path d="m19 15 2 2-3 3-2-1-2 1-1 2H9l-1-2-2-1-2 1-2-3 2-2v-2l-2-1V9l2-1 1-2-1-2 3-2 2 2h2l1-2h4l1 2 2 1 2-1 2 3-2 2v2l2 1v3z"/>'};
  const rail=[['notifications','Notificações','charts_activity'],['charts','Gráficos','charts_activity'],['log','Registo','charts_activity'],['timer','Horário','timer'],['calendar','Calendário','weekly_schedule'],['night','Modo noite','night_mode'],['links','Ligações','internet_security'],['web','Web','internet_security'],['automations','Automações','actions'],['share','Partilha','actions'],['settings','Definições','settings']].sort((a,b)=>menuOrder.indexOf(a[0])-menuOrder.indexOf(b[0])).map(([icon,label,section])=>`<button type="button" data-shelly-settings="${esc(device.device_id)}" data-shelly-section="${esc(section)}" aria-label="${label}" title="${label}"><svg viewBox="0 0 24 24" aria-hidden="true">${glyphs[icon]}</svg></button>`).join("");
  const channels=dimmers.map((item,index)=>{const channel=Number(item.id)||0,status=item.status||{},rawBrightness=status.brightness,hasBrightness=rawBrightness!==null&&rawBrightness!==undefined&&Number.isFinite(Number(rawBrightness)),brightness=hasBrightness?Math.max(0,Math.min(100,Number(rawBrightness))):null,on=shellyComponentState(item)===true;return `<section class="reference-channel ${on?"is-on":"is-off"}" data-shelly-light-controls="${esc(device.device_id)}" data-shelly-component="${esc(item.component)}" data-shelly-channel="${channel}"><label class="reference-vertical-slider ${on?"":"is-off"}"><input type="range" min="0" max="100" value="${brightness??0}" data-shelly-brightness data-shelly-device="${esc(device.device_id)}" data-shelly-component="${esc(item.component)}" data-shelly-channel="${channel}" aria-label="Luminosidade canal ${channel+1}" ${!admin||!connected||!on||brightness===null?"disabled":""}><span class="reference-slider-fill" style="--level:${brightness??0}%"></span></label><span class="reference-channel-brightness">Luminosidade <strong data-shelly-brightness-value>${brightness===null?"Sem leitura":`${brightness}%`}</strong></span><button type="button" class="reference-power ${on?"on":"off"}" data-shelly-light-on="${esc(device.device_id)}" data-shelly-component="${esc(item.component)}" data-shelly-channel="${channel}" data-shelly-target="${on?"off":"on"}" data-reference-power aria-pressed="${on}" aria-label="${on?"Desligar":"Ligar"} ${esc(device.name||"lâmpada")}" ${!admin||!connected?"disabled":""}><svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0M14 2.4v10.2"/></svg></button><strong class="reference-channel-name">${dimmers.length>1?`Canal ${channel+1}`:"Luz"}</strong></section>`;}).join("");
  const power=shellyComponentPower(device,dimmers[0]),summary=power!==null?`${power.toLocaleString("pt-PT")} W`:"Sem leitura",primaryBrightness=dimmers[0]?.status?.brightness,hasPrimaryBrightness=primaryBrightness!==null&&primaryBrightness!==undefined&&Number.isFinite(Number(primaryBrightness)),isOn=dimmers.some(item=>shellyComponentState(item)===true),groupAction=dimmers.length>1?referenceDimmerGroupAction({deviceId:device.device_id,isOn,provider:"shelly",enabled:admin&&connected}):"";
  dialog.className="settings-dialog reference-smart-card-dialog";dialog.dataset.shellyDeviceId=device.device_id;
  dialog.innerHTML=`<div class="reference-card"><nav class="reference-rail" aria-label="Opções do dispositivo">${rail}</nav><main class="reference-main"><header class="reference-heading"><div><p class="eyebrow">DISPOSITIVO · SHELLY VINTAGE</p><h2>${esc(device.name||"Lâmpada")}</h2></div><button type="button" class="reference-edit-name" data-shelly-rename="${esc(device.device_id)}" aria-label="Editar nome" title="Editar nome">✎</button><button type="button" class="reference-close" aria-label="Fechar">×</button></header><p class="reference-subtitle">Controlos principais · ${esc(device.room||device.location||"Localização por definir")}</p><div class="reference-pills"><span>⚡ <b data-shelly-power-summary>${esc(summary)}</b></span><span>◐ <b data-shelly-brightness-summary>${hasPrimaryBrightness?`${Math.round(Number(primaryBrightness))}%`:"Sem leitura"}</b></span></div><div class="reference-dimmer-layout ${dimmers.length>1?"is-multi":""}">${channels}</div>${groupAction}<p class="reference-status" data-shelly-status="${esc(device.device_id)}">${connected?(shellyComponentState(dimmers[0])===true?"Ligado":shellyComponentState(dimmers[0])===false?"Desligado":"Sem leitura"):esc(device.reason||"Sem leitura")}</p></main></div>`;
  $("#page-content").append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector(".reference-close").addEventListener("click",()=>dialog.close());
  dialog.querySelector("[data-shelly-rename]")?.addEventListener("click",()=>{
    const editor=document.createElement("dialog");editor.className="settings-dialog shelly-rename-dialog";editor.innerHTML=`<form class="dialog-body"><div class="dialog-header"><h2>Editar dispositivo</h2><button type="button" class="icon-button" data-name-close aria-label="Fechar">×</button></div><label>Nome<input name="name" maxlength="120" required value="${esc(device.name||"")}"></label><label>Divisão / piso<input name="room" maxlength="120" value="${esc(device.room||"")}"></label><p class="connection-result" data-name-status role="status"></p><div class="dialog-actions"><button type="button" class="button secondary" data-name-close>Cancelar</button><button type="submit" class="button primary">Guardar</button></div></form>`;
    $("#page-content").append(editor);editor.addEventListener("close",()=>editor.remove(),{once:true});editor.querySelectorAll("[data-name-close]").forEach(button=>button.addEventListener("click",()=>editor.close()));editor.querySelector("form").addEventListener("submit",async event=>{event.preventDefault();const submit=editor.querySelector('[type="submit"]'),status=editor.querySelector("[data-name-status]"),name=editor.elements.name.value.trim(),room=editor.elements.room.value.trim();submit.disabled=true;try{await renameGatewayShellyDevice(device.device_id,name,room);device.name=name;device.room=room;const title=dialog.querySelector(".reference-heading h2");if(title)title.textContent=name;const cardName=document.querySelector(`[data-smart-device="${CSS.escape(device.device_id)}"] .favorite-device-name`);if(cardName)cardName.textContent=name;status.textContent="Nome e divisão atualizados.";setTimeout(()=>editor.close(),400);}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;submit.disabled=false;}});editor.showModal();
  });
  dialog.querySelectorAll("[data-shelly-brightness]").forEach(input=>input.addEventListener("input",()=>{input.parentElement.querySelector(".reference-slider-fill")?.style.setProperty("--level",`${input.value}%`);const caption=input.closest(".reference-channel")?.querySelector("[data-shelly-brightness-value]");if(caption)caption.textContent=`${input.value}%`;if(input.dataset.shellyChannel===String(dimmers[0]?.id??0)){const summary=dialog.querySelector("[data-shelly-brightness-summary]");if(summary)summary.textContent=`${input.value}%`;}}));
  dialog.showModal();return true;
}
function openShellyDeviceDetails(deviceId){
  const device=state.shellyDevices.find(item=>item.device_id===deviceId);
  const card=Array.from(document.querySelectorAll('[data-smart-provider="shelly"]')).find(item=>item.dataset.smartDevice===deviceId);
  if(!device)return;
  if(!state.shellyProductProfiles.length)readGatewayShellyProductProfiles().then(result=>{state.shellyProductProfiles=Array.isArray(result.profiles)?result.profiles:[];}).catch(()=>{});
  const dialog=document.createElement("dialog"),connected=device.connection_state==="connected";
  const components=Array.isArray(device.components)?device.components:[];
  const primaryLight=components.find(item=>["light","rgb","rgbw","cct","color"].includes(item.component));
  if(primaryLight&&openShellyDimmerReference(device))return;
  const stateOf=item=>item.status?.output??item.status?.ison;
  const isBridge=isShellyBluBridge(device);
  const identity=[device.model,device.name].filter(Boolean).join(" ").toLowerCase();
  const deviceLocation=device.location||device.room||"Divisão / piso não definidos";
  const canEditLocation=!String(deviceId).startsWith("shelly-blu:");
  const profileCode=isBridge?"shelly_blu_gateway_gwf_kz01":/vintage|shblb-1|shvin-1/.test(identity)?"shelly_vintage_gen1":"";
  const productProfile=state.shellyProductProfiles.find(item=>item.product_code===profileCode);
  const toggle=(item,light=false)=>{const on=stateOf(item),channel=Number(item.id)||0,component=item.component,attrs=light?`data-shelly-light-on="${esc(deviceId)}" data-shelly-component="${esc(component)}" data-shelly-channel="${channel}"`:`data-shelly-switch="${esc(deviceId)}" data-shelly-channel="${channel}"`;return light?`<div class="shelly-power-dock"><button type="button" class="favorite-state-symbol breaker-detail-power ${on===true?"on":"off"}" ${attrs} data-shelly-target="${on===true?"off":"on"}" aria-pressed="${on===true}" aria-label="${on===true?"Desligar":"Ligar"} lâmpada" ${!connected?"disabled":""}><svg viewBox="0 0 28 28" aria-hidden="true"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg></button></div>`:`<button type="button" class="button ${on===true?"secondary":"primary"}" ${attrs} data-shelly-target="${on===true?"off":"on"}" ${!connected?"disabled":""}>${on===true?"Desligar":"Ligar"} · canal ${channel}</button>`;};
  const dimmableComponents=components.filter(item=>["light","rgb","rgbw","cct","color"].includes(item.component));
  const controls=components.filter(item=>!["light","rgb","rgbw","cct","color"].includes(item.component)).map(item=>{
    const status=item.status||{},channel=Number(item.id)||0,component=item.component;
    if(["switch","relay"].includes(component))return `<section class="shelly-detail-control"><h3>Canal ${channel}</h3>${toggle(item)}</section>`;
    const metrics=Object.entries(status).filter(([,value])=>value!==null&&value!==undefined&&["string","number","boolean"].includes(typeof value)).slice(0,6).map(([key,value])=>`<div class="detail-item"><small>${esc(key)}</small><strong>${esc(value)}</strong></div>`).join("");
    return metrics?`<section class="shelly-detail-control"><h3>${esc(component)} · ${channel}</h3><div class="device-detail-grid">${metrics}</div></section>`:"";
  }).join("");
  const dimmerControls=dimmableComponents.map(item=>{
    const status=item.status||{},channel=Number(item.id)||0,component=item.component;
    const reportedBrightness=Number.isFinite(Number(status.brightness))&&status.brightness!==null&&status.brightness!==undefined?Math.max(0,Math.min(100,Number(status.brightness))):null;
    const brightness=reportedBrightness??0,lightIsOn=stateOf(item)===true;
    const power=status.apower??status.power??(device.bthome_values||[]).find(value=>String(value?.name||"").toLowerCase()==="power")?.value;
    const slider=`<label class="shelly-brightness-control"><span class="shelly-slider-track ${lightIsOn?"":"is-off"}" style="--brightness-level:${brightness}%"><span class="shelly-slider-fill"></span><input type="range" min="0" max="100" value="${brightness}" data-shelly-brightness data-shelly-device="${esc(deviceId)}" data-shelly-component="${esc(component)}" data-shelly-channel="${channel}" aria-label="Brilho da lâmpada, canal ${channel}" ${!connected||!lightIsOn?"disabled":""}></span><output class="shelly-brightness-caption" data-shelly-brightness-value>${reportedBrightness===null?"Sem leitura":`${reportedBrightness}%`}</output></label>`;
    const rgb=Array.isArray(status.rgb)&&status.rgb.length>=3?status.rgb.map(value=>Math.max(0,Math.min(255,Math.round(Number(value)||0)))):(Number.isFinite(Number(status.red))&&Number.isFinite(Number(status.green))&&Number.isFinite(Number(status.blue))?[status.red,status.green,status.blue].map(value=>Math.max(0,Math.min(255,Math.round(Number(value))))):null);
    const reportedTemp=Number(status.color_temperature??status.ct??status.temp),fixedVintage=/vintage|shblb-1|shvin-1/.test(identity),warmVintage=fixedVintage?[255,190,128]:null;
    const lampRgb=rgb||warmVintage||null,colorStyle=lampRgb?` style="--lamp-rgb:${lampRgb.join(",")}"`:"",colorTitle=rgb?"Cor reportada pela lâmpada":Number.isFinite(reportedTemp)&&reportedTemp>0?`${Math.round(reportedTemp)} K`:fixedVintage?"Branco quente · 2700 K, perfil Shelly Vintage":"Cor não reportada pela lâmpada";
    const badges=`<div class="shelly-light-metric-strip" data-shelly-light-metrics data-shelly-component="${esc(component)}" data-shelly-channel="${channel}"><span class="shelly-light-badge shelly-color-badge" title="${esc(colorTitle)}" aria-label="${esc(colorTitle)}"><span class="shelly-light-color-indicator" data-shelly-color-dot${colorStyle}></span><svg class="shelly-color-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5a7.5 7.5 0 1 0 0 15h1.1a1.8 1.8 0 0 0 1.4-2.9 1.2 1.2 0 0 1 .9-2h1.1A4.5 4.5 0 0 0 19 8.1c0-3.1-4-5.6-9-5.6Z"/><circle cx="6.4" cy="9" r=".8"/><circle cx="9.4" cy="6.3" r=".8"/><circle cx="13" cy="6.8" r=".8"/></svg></span><span class="shelly-light-badge shelly-meter-badge"><svg class="shelly-light-power-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M13.5 2.5 5 13h6l-.5 8.5L19 11h-6z"/></svg><output data-shelly-measured-power>${power!==undefined&&power!==null&&Number.isFinite(Number(power))?`${esc(Number(power).toLocaleString("pt-PT"))} W`:"— W"}</output></span><span class="shelly-light-badge shelly-percent-badge"><output data-shelly-badge-brightness>${reportedBrightness===null?"—":`${reportedBrightness}%`}</output></span></div>`;
    return `<section class="shelly-detail-control smart-light-controls shelly-dimmer-panel" id="shelly-light-controls-${esc(deviceId)}-${channel}" data-shelly-light-controls="${esc(deviceId)}" data-shelly-component="${esc(component)}" data-shelly-channel="${channel}">${dimmableComponents.length>1?`<h3 class="shelly-dimmer-channel-label">Canal ${channel}</h3>`:""}${badges}<div class="shelly-dimmer-stage">${slider}</div>${toggle(item,true)}</section>`;
  }).join("");
  const bthomeUnits={temperature:"°C",humidity:"%",battery:"%",illuminance:"lx",voltage:"V",current:"A",power:"W",energy:"kWh",moisture:"%",pressure:"hPa",co2:"ppm",pm2_5:"µg/m³"};
  const visibleBthomeMetrics=new Set(Object.keys(bthomeUnits));
  const bthomeMetrics=(Array.isArray(device.bthome_values)?device.bthome_values:[]).filter(item=>item&&item.value!==null&&item.value!==undefined&&visibleBthomeMetrics.has(String(item.name||"").toLowerCase())).map(item=>`<div class="detail-item"><small>${esc(item.name||"Sensor")}</small><strong>${esc(item.value)} ${esc(item.unit||bthomeUnits[String(item.name||"").toLowerCase()]||"")}</strong></div>`).join("");
  const discover=isBridge?`<button type="button" class="button primary" data-shelly-blu-discover="${esc(deviceId)}">Procurar sensores BLU</button>`:"";
  const settingsButton=`<button type="button" class="button secondary" data-shelly-settings="${esc(deviceId)}">Definições</button>`;
  dialog.className=`settings-dialog favorite-device-details shelly-device-dialog${primaryLight?" shelly-light-device-dialog":""}`;dialog.dataset.shellyDeviceId=deviceId;
  const summary=`<div class="device-detail-grid">${`<div class="detail-item"><small>Estado</small><strong data-shelly-dialog-state>${connected?"Online":"Offline"}</strong></div>`}<div class="detail-item"><small>Ligação</small><strong>${connected?"Disponível":"Indisponível"}</strong></div></div>`;
  const actions=[discover,settingsButton].filter(Boolean).join("");
  const profileIcon={timer:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2M9 2h6"/>',weekly_schedule:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 9h16"/>',night_mode:'<path d="M19.2 15.3A8 8 0 0 1 8.7 4.8a8.5 8.5 0 1 0 10.5 10.5Z"/>',actions:'<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.5m-7.6 7.9 7.6 4.5"/>',internet_security:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',settings:'<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 15 .1.1 1.2 2-2 2-2-1.2-.2.1a7.7 7.7 0 0 1-1.5.6l-.5 2.3h-2.8l-.5-2.3a7.7 7.7 0 0 1-1.5-.6l-.2-.1-2 1.2-2-2 1.2-2-.1-.2a7.7 7.7 0 0 1-.6-1.5L2 13.8V11l2.3-.5a7.7 7.7 0 0 1 .6-1.5l.1-.2-1.2-2 2-2 2 1.2.2-.1a7.7 7.7 0 0 1 1.5-.6L11 3h2.8l.5 2.3a7.7 7.7 0 0 1 1.5.6l.2.1 2-1.2 2 2-1.2 2 .1.2a7.7 7.7 0 0 1 .6 1.5l2.3.5v2.8l-2.3.5a7.7 7.7 0 0 1-.6 1.5Z"/>',charts_activity:'<path d="M4 19V5M4 19h16M7 15l4-4 3 3 5-6"/>'};
  Object.assign(profileIcon,{notifications:'<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',record:'<rect x="6" y="3" width="13" height="18" rx="2"/><path d="M9 7h7M9 11h7M9 15h5M4 6v14"/>',links:'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',share:'<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6m-7.6 6 7.6 3.6"/>'});
  const railIcon=(key)=>`<svg viewBox="0 0 24 24" aria-hidden="true">${profileIcon[key]||profileIcon.settings}</svg>`;
  const menuOrder=deviceCardPopupMenuOrder(deviceCardTemplate(isBridge?"shelly_blu":"shelly",device.model||device.device_type||"")),shellyMenu=[['notifications','Notificações','notifications'],['charts_activity','Gráficos','charts'],['record','Registo','log'],['timer','Horário','timer'],['weekly_schedule','Calendário','calendar'],['night_mode','Modo noite','night'],['links','Ligações','links'],['internet_security','Web','web'],['actions','Automações','automations'],['share','Partilha','share'],['settings','Definições','settings']].sort((a,b)=>menuOrder.indexOf(a[2])-menuOrder.indexOf(b[2]));
  const profileRail=shellyMenu.map(([key,label])=>{const section=productProfile?.settings_sections?.find(item=>item.key===key||item.label?.toLowerCase()===label.toLowerCase());return `<button type="button" data-shelly-option="${esc(key)}" ${section?`data-shelly-settings="${esc(deviceId)}" data-shelly-section="${esc(section.key)}"`:key==="settings"?`data-shelly-settings="${esc(deviceId)}"`:`data-shelly-option-label="${esc(label)}"`} aria-label="${esc(label)}" title="${esc(label)}">${railIcon(key)}</button>`;}).join("");
  const lightShell=primaryLight?`<div class="shelly-device-workspace"><nav class="shelly-device-rail" aria-label="Opções do dispositivo">${profileRail}</nav><main id="shelly-light-controls-${esc(deviceId)}" class="shelly-device-main${dimmableComponents.length>1?" is-multi-dimmer":""}">${dimmerControls}${controls||""}</main></div>`:"";
  dialog.innerHTML=`<form method="dialog" class="dialog-body ${primaryLight?"shelly-light-dialog-body":""}">${primaryLight?`<div class="shelly-device-heading"><div class="shelly-device-heading-icon">${equipmentIconSvg(device,"shelly")}</div><div class="shelly-device-title"><h2>${esc(device.name||"Equipamento")}</h2><p class="shelly-device-location">${esc(deviceLocation)}</p><p class="shelly-device-connection ${connected?"is-online":"is-offline"}">${connected?"Online":"Offline"}</p></div><button type="button" class="shelly-name-edit-plain" data-shelly-rename="${esc(deviceId)}" aria-label="Alterar nome" title="Alterar nome">✎</button><button class="icon-button shelly-close-button" type="submit" value="close" aria-label="Fechar">×</button></div>${lightShell}`:`<div class="dialog-header"><div><p class="eyebrow">INFORMAÇÃO DO DISPOSITIVO</p><h2>${esc(device.name||"Equipamento")} <button type="button" class="icon-button shelly-name-edit" data-shelly-rename="${esc(deviceId)}" aria-label="Alterar nome">✎</button></h2></div><button class="icon-button" type="submit" value="close" aria-label="Fechar">×</button></div><div class="shelly-device-workspace"><nav class="shelly-device-rail" aria-label="Opções do dispositivo">${profileRail}</nav><main class="shelly-device-main">${summary}${bthomeMetrics?`<h3>Leituras disponíveis</h3><div class="device-detail-grid telemetry-grid" aria-label="Leituras disponíveis">${bthomeMetrics}</div>`:""}<div class="shelly-detail-controls">${controls||`<p class="field-note">Este equipamento não anunciou controlos físicos. ${isBridge?"Podes procurar sensores pela ponte abaixo.":""}</p>`}</div><p class="field-note" data-shelly-status="${esc(deviceId)}">${connected?"Ligação confirmada.":esc(device.reason||"Sem resposta recente.")}</p></main></div><div class="dialog-actions">${actions}<button class="button secondary" type="submit" value="close">Fechar</button></div>`}</form>`;
  $("#page-content").append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.showModal();
  dialog.querySelectorAll("[data-shelly-scroll]").forEach(button=>button.addEventListener("click",()=>{const section=dialog.querySelector(`#${CSS.escape(button.dataset.shellyScroll)}`);section?.scrollIntoView({behavior:"smooth",block:"start"});dialog.querySelectorAll(".shelly-device-rail button").forEach(item=>item.classList.toggle("active",item===button));}));
  dialog.querySelectorAll("[data-shelly-option-label]").forEach(button=>button.addEventListener("click",()=>showFeatureNotice(`${button.dataset.shellyOptionLabel}: este item é informativo; as opções suportadas estão em Horário, Calendário, Modo noite, Automações e Definições.`)));
  dialog.querySelector("[data-shelly-rename]")?.addEventListener("click",()=>{
    const rename=document.createElement("dialog");rename.className="settings-dialog shelly-rename-dialog";rename.innerHTML=`<form class="dialog-body"><div class="dialog-header"><h2>Editar dispositivo</h2><button type="button" class="icon-button" data-rename-close aria-label="Fechar">×</button></div><label>Nome<input data-shelly-new-name maxlength="120" required value="${esc(device.name||"")}"></label>${canEditLocation?`<label>Divisão / piso<input data-shelly-device-room maxlength="120" value="${esc(device.room||"")}" placeholder="Cozinha / CAVE"></label>`:""}<p class="connection-result" data-shelly-rename-status role="status"></p><div class="dialog-actions"><button type="button" class="button secondary" data-rename-close>Cancelar</button><button class="button primary" type="submit">Guardar</button></div></form>`;
    document.body.append(rename);rename.addEventListener("close",()=>rename.remove(),{once:true});rename.querySelectorAll("[data-rename-close]").forEach(button=>button.addEventListener("click",()=>rename.close()));
    rename.querySelector("form").addEventListener("submit",async event=>{event.preventDefault();const button=rename.querySelector("button[type=submit]"),status=rename.querySelector("[data-shelly-rename-status]"),name=rename.querySelector("[data-shelly-new-name]").value.trim(),room=rename.querySelector("[data-shelly-device-room]")?.value.trim();button.disabled=true;try{await renameGatewayShellyDevice(deviceId,name,room);device.name=name;if(room!==undefined)device.room=room;const heading=dialog.querySelector(".dialog-header h2,.shelly-device-title h2");if(heading)heading.firstChild.textContent=name;const locationNode=dialog.querySelector(".shelly-device-location");if(locationNode&&room!==undefined)locationNode.textContent=room||"Divisão / piso não definidos";const cardName=document.querySelector(`[data-smart-device="${CSS.escape(deviceId)}"] .favorite-device-info h3, [data-smart-device="${CSS.escape(deviceId)}"] .favorite-device-info strong`);if(cardName)cardName.textContent=name;status.textContent="Alterações guardadas no Gateway.";setTimeout(()=>rename.close(),500);}catch(error){status.textContent=`Não foi possível guardar as alterações: ${error.message}`;button.disabled=false;}});rename.showModal();
  });
}
function openShellySettings(deviceId, requestedSection=""){
  if(!state.shellyProductProfiles.length){readGatewayShellyProductProfiles().then(result=>{state.shellyProductProfiles=Array.isArray(result.profiles)?result.profiles:[];openShellySettings(deviceId,requestedSection);}).catch(error=>showFeatureNotice(`Não foi possível carregar o perfil Shelly: ${error.message}`));return;}
  const device=state.shellyDevices.find(item=>item.device_id===deviceId);
  const identity=[device?.model,device?.name].filter(Boolean).join(" ").toLowerCase();
  const productCode=isShellyBluBridge(device)?"shelly_blu_gateway_gwf_kz01":/vintage|shblb-1|shvin-1/.test(identity)?"shelly_vintage_gen1":"";
  const profile=state.shellyProductProfiles.find(item=>item.product_code===productCode);
  if(!device||!profile){showFeatureNotice("Ainda não existe um perfil confirmado para este modelo Shelly.");return;}
  const dialog=document.createElement("dialog");dialog.className="settings-dialog favorite-device-details";
  const sections=Array.isArray(profile.settings_sections)?profile.settings_sections:[];
  const selectedSection=sections.some(section=>section.key===requestedSection)?requestedSection:sections[0]?.key;
  const tabs=sections.map(section=>{const selected=section.key===selectedSection;return `<button type="button" class="device-inventory-tab ${selected?"active":""}" role="tab" aria-selected="${selected}" data-shelly-setting-tab="${esc(section.key)}">${esc(section.label)}</button>`;}).join("");
  dialog.innerHTML=`<div class="dialog-header"><div><p class="eyebrow">EQUIPAMENTO · ${esc(device.name||profile.product_name)}</p><h2>Opções do Shelly Vintage</h2></div><button class="icon-button" type="button" data-shelly-detail-close aria-label="Fechar">×</button></div><nav class="device-inventory-tabs" role="tablist" aria-label="Definições Shelly">${tabs}</nav><div class="dialog-body" data-shelly-settings-body><p class="field-note">A carregar definições locais do equipamento…</p></div><footer class="field-note">Alterações enviadas pela LAN. Fontes: ${profile.sources.map(source=>`<a href="${esc(source)}" target="_blank" rel="noopener noreferrer">Shelly</a>`).join(" · ")}</footer>`;
  $("#page-content").append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});
  const body=dialog.querySelector("[data-shelly-settings-body]"),canWrite=sessionInfo().user?.role==="owner";
  const settingRoot=(key,data)=>key==="night_mode"?(data.night_mode||data):data;
  const valuesFor=(key,data)=>{
    const values=settingRoot(key,data),light=Array.isArray(data.lights)?data.lights[0]||{}:{};
    if(key==="actions")return data.actions||{};
    if(key==="settings")return {...data,...light};
    return values||{};
  };
  const textValue=value=>value===undefined||value===null?"":String(value);
  const renderForm=(section,data)=>{
    const values=valuesFor(section.key,data),readOnly=!section.writable||!canWrite;
    let fields="",payload=section.key;
    if(section.key==="timer")fields=`<label>Auto on · ligar após desligar<input name="auto_on" type="number" min="0" max="86400" step="1" value="${esc(textValue(values.auto_on))}" ${readOnly?"disabled":""}><small>Segundos; 0 desativa.</small></label><label>Auto off · desligar após ligar<input name="auto_off" type="number" min="0" max="86400" step="1" value="${esc(textValue(values.auto_off))}" ${readOnly?"disabled":""}><small>Segundos; 0 desativa.</small></label>`;
    else if(section.key==="weekly_schedule")fields=`<label class="shelly-setting-check"><input name="schedule" type="checkbox" ${values.schedule===true?"checked":""} ${readOnly?"disabled":""}> Ativar horário semanal</label><label>Regras semanais · até 20<textarea name="schedule_rules" rows="6" maxlength="1200" ${readOnly?"disabled":""} placeholder="HHMM-dias-on ou HHMM-dias-off">${esc(Array.isArray(values.schedule_rules)?values.schedule_rules.join("\n"):"")}</textarea><small>Uma regra por linha. Exemplo documentado: 0730-01234-on (07:30, segunda a sexta). Horários do nascer/pôr do sol e ajuste de brilho não são suportados por esta versão do editor.</small></label>`;
    else if(section.key==="night_mode")fields=`<label class="shelly-setting-check"><input name="enabled" type="checkbox" ${values.enabled===true?"checked":""} ${readOnly?"disabled":""}> Ativar modo noite</label><div class="home-level-range"><label>Início<input name="start_time" type="time" value="${esc(textValue(values.start_time)||"00:00")}" ${readOnly?"disabled":""}></label><label>Fim<input name="end_time" type="time" value="${esc(textValue(values.end_time)||"00:00")}" ${readOnly?"disabled":""}></label></div><label>Brilho noturno · ${esc(textValue(values.brightness)||"0")}%<input name="brightness" type="range" min="0" max="100" step="1" value="${esc(textValue(values.brightness)||"0")}" ${readOnly?"disabled":""}></label>`;
    else if(section.key==="actions"){const actionList=key=>{const first=values[key]?.[0];return Array.isArray(first?.urls)?first.urls.join("\n"):"";};fields=`<label>Output switched on URL · uma por linha<textarea name="out_on_url" rows="4" maxlength="1200" ${readOnly?"disabled":""}>${esc(actionList("out_on_url"))}</textarea><small>Até 5 endereços HTTP/HTTPS.</small></label><label>Output switched off URL · uma por linha<textarea name="out_off_url" rows="4" maxlength="1200" ${readOnly?"disabled":""}>${esc(actionList("out_off_url"))}</textarea><small>Até 5 endereços HTTP/HTTPS.</small></label>`;}
    else if(section.key==="settings")fields=`<label>Power on default mode<select name="default_state" ${readOnly?"disabled":""}>${[["on","Ligado"],["off","Desligado"],["last","Último estado"]].map(([value,label])=>`<option value="${value}" ${values.default_state===value?"selected":""}>${label}</option>`).join("")}</select></label><label>Transition time · ms<input name="transition" type="number" min="0" max="5000" step="1" value="${esc(textValue(data.transition))}" ${readOnly?"disabled":""}></label><label>Channel name<input name="name" maxlength="64" value="${esc(textValue(values.name))}" ${readOnly?"disabled":""}></label><p class="field-note">Nome do equipamento, fuso horário e localização são editados nos controlos do dispositivo. Firmware, reinício e reposição de fábrica não são expostos para evitar alterações disruptivas.</p>`;
    else if(section.key==="internet_security"){const wifi=data.wifi_sta||data.wifi||{},cloud=data.cloud||{};fields=`<div class="device-detail-grid"><div class="detail-item"><small>Wi-Fi ativo</small><strong>${wifi.enabled===true?"Sim":wifi.enabled===false?"Não":"Sem leitura"}</strong></div><div class="detail-item"><small>Rede</small><strong>${esc(textValue(wifi.ssid)||"Não declarada")}</strong></div><div class="detail-item"><small>Cloud Shelly</small><strong>${cloud.enabled===true?"Ativa":cloud.enabled===false?"Inativa":"Sem leitura"}</strong></div></div><p class="field-note">As credenciais de Wi-Fi e as definições de segurança não são mostradas nem alteradas pela PWA.</p>`;}
    else if(section.key==="charts_activity"){const status=Object.values(data.meters||{})[0]||{};fields=`<div class="device-detail-grid"><div class="detail-item"><small>Potência</small><strong>${status.power!==undefined?`${esc(status.power)} W`:"Sem leitura"}</strong></div><div class="detail-item"><small>Energia total</small><strong>${status.total!==undefined?`${esc(status.total)} Wh`:"Sem leitura"}</strong></div><div class="detail-item"><small>Brilho</small><strong>${data.lights?.[0]?.brightness!==undefined?`${esc(data.lights[0].brightness)}%`:"Sem leitura"}</strong></div></div><p class="field-note">A API local do Vintage não fornece histórico gráfico nem registo de eventos neste endpoint.</p>`;}
    else fields=section.note?`<p class="field-note">${esc(section.note)}</p>`:`<p class="field-note">Consulta informativa.</p>`;
    const save=section.writable&&canWrite?`<div class="dialog-actions"><button type="submit" class="button primary">Guardar no dispositivo</button></div>`:"";
    body.innerHTML=`<form data-shelly-settings-form="${esc(section.key)}"><section class="panel"><h3>${esc(section.label)}</h3><p class="field-note">${esc(section.note||"Definições atuais lidas diretamente pela LAN.")}</p>${fields}<p class="connection-result" data-shelly-settings-status role="status"></p>${save}</section></form>`;
    const form=body.querySelector("form");form.addEventListener("submit",async event=>{event.preventDefault();const submit=form.querySelector('[type="submit"]'),status=form.querySelector("[data-shelly-settings-status]"),values={};if(!submit)return;submit.disabled=true;status.textContent="A guardar na lâmpada pela LAN…";
      if(section.key==="timer"){values.auto_on=Number(form.elements.auto_on.value);values.auto_off=Number(form.elements.auto_off.value);}
      else if(section.key==="night_mode"){values.enabled=form.elements.enabled.checked;values.start_time=form.elements.start_time.value;values.end_time=form.elements.end_time.value;values.brightness=Number(form.elements.brightness.value);}
      else if(section.key==="weekly_schedule"){values.schedule=form.elements.schedule.checked;values.schedule_rules=form.elements.schedule_rules.value.split(/[\n,]+/).map(rule=>rule.trim()).filter(Boolean);}
      else if(section.key==="actions"){values.out_on_url=form.elements.out_on_url.value.split(/[\n,]+/).map(url=>url.trim()).filter(Boolean);values.out_off_url=form.elements.out_off_url.value.split(/[\n,]+/).map(url=>url.trim()).filter(Boolean);}
      else if(section.key==="settings"){values.default_state=form.elements.default_state.value;values.transition=Number(form.elements.transition.value);values.name=form.elements.name.value;}
      try{await saveGatewayShellySettings(deviceId,section.key,values);status.textContent="Guardado no Shelly. A reler os valores confirmados…";const fresh=await readGatewayShellySettings(deviceId,section.key);renderForm(section,fresh.settings||{});const message=body.querySelector("[data-shelly-settings-status]");if(message)message.textContent="Alterações guardadas e relidas do dispositivo.";void refreshShellyInventoryStatus({quiet:true});}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;submit.disabled=false;}
    });
  };
  const loadSection=async key=>{const section=sections.find(item=>item.key===key);if(!section)return;body.innerHTML=`<section class="panel"><h3>${esc(section.label)}</h3><p class="field-note">A consultar a lâmpada pela rede local…</p></section>`;try{const result=await readGatewayShellySettings(deviceId,key);renderForm(section,result.settings||{});}catch(error){body.innerHTML=`<section class="panel"><h3>${esc(section.label)}</h3><p class="empty-state">Não foi possível ler este menu pela LAN: ${esc(error.message)}</p></section>`;}};
  dialog.querySelector("[data-shelly-detail-close]").addEventListener("click",()=>dialog.close());
  dialog.querySelectorAll("[data-shelly-setting-tab]").forEach(tab=>tab.addEventListener("click",()=>{dialog.querySelectorAll("[data-shelly-setting-tab]").forEach(item=>{const active=item===tab;item.classList.toggle("active",active);item.setAttribute("aria-selected",String(active));});void loadSection(tab.dataset.shellySettingTab);}));
  void loadSection(selectedSection);dialog.showModal();
}
function renderDeviceCardsPanel(){
  const groups=new Map();for(const card of state.deviceCards||[]){const manufacturer=card.manufacturer||"Outros";if(!groups.has(manufacturer))groups.set(manufacturer,[]);groups.get(manufacturer).push(card);}
  return `<section class="panel device-cards-panel"><div class="panel-header"><div><p class="eyebrow">MODELOS DE POP-UP · POR FABRICANTE</p><h2>Menus dos dispositivos</h2></div><button type="button" class="button secondary" data-cards-refresh>Atualizar</button></div><p class="field-note">Toca no código para abrir o mesmo pop-up do dispositivo. O lápis edita a ordem das opções do menu para este modelo/PID.</p>${groups.size?[...groups].map(([name,cards])=>`<h3>${esc(name)}</h3><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Modelo</th><th>PID / código</th><th>Protocolo</th><th>Estado</th><th></th></tr></thead><tbody>${cards.map(card=>`<tr><th><button type="button" class="text-link" data-card-open="${esc(card.card_code)}">${esc(card.product_name||card.card_code)}</button></th><td>${esc(card.product_id||"—")}<small class="field-note">${esc(card.card_code)}</small></td><td>${esc(card.protocol)}</td><td>${card.available?"Disponível":"Oculto"}</td><td><button type="button" class="icon-button" data-card-edit="${esc(card.card_code)}" aria-label="Editar menu do pop-up">✎</button></td></tr>`).join("")}</tbody></table></div>`).join(""):'<p class="field-note">Sincroniza dispositivos Tuya/Shelly para listar os menus associados aos modelos existentes.</p>'}</section>`;
}
const DEVICE_POPUP_MENU_OPTIONS=[['notifications','Notificações'],['charts','Gráficos'],['log','Registo'],['timer','Horário'],['calendar','Calendário'],['night','Modo noite'],['links','Ligações'],['web','Web'],['automations','Automações'],['share','Partilha'],['settings','Definições']];
function deviceCardPopupMenuOrder(card){const defaults=DEVICE_POPUP_MENU_OPTIONS.map(([key])=>key),saved=card?.layout?.popup_menu?.order;return [...(Array.isArray(saved)?saved.filter(key=>defaults.includes(key)&&defaults.indexOf(key)===saved.indexOf(key)):[]),...defaults.filter(key=>!Array.isArray(saved)||!saved.includes(key))];}
function openDeviceCardPreview(card){
  if(!card){showFeatureNotice("Este cartão já não está disponível.");return;}
  const protocol=String(card.protocol||"tuya").toLowerCase(),isShelly=protocol.startsWith("shelly");
  if(isShelly){const device=(state.shellyDevices||[]).find(item=>String(item.model||item.device_type||"")===String(card.product_id));if(!device){showFeatureNotice("Não há um equipamento Shelly deste modelo disponível para abrir o pop-up.");return;}openShellyDeviceDetails(device.device_id);return;}
  const device=(state.tuyaDevices||[]).find(item=>String(item.product_id||"")===String(card.product_id));if(!device){showFeatureNotice("Não há um equipamento Tuya deste PID disponível para abrir o pop-up.");return;}openFavoriteDeviceDetails(device.device_id,"tuya");
}
function openDevicePopupMenuEditor(card){
  if(!card){showFeatureNotice("Este modelo já não está disponível.");return;}
  let order=deviceCardPopupMenuOrder(card),dialog=document.createElement("dialog");dialog.className="settings-dialog device-popup-menu-editor";
  const draw=()=>{const list=dialog.querySelector("[data-popup-menu-order]");if(!list)return;list.innerHTML=order.map((key,index)=>{const option=DEVICE_POPUP_MENU_OPTIONS.find(([id])=>id===key);return `<li><span>${esc(option?.[1]||key)}</span><span class="device-popup-menu-order-actions"><button type="button" class="button secondary" data-popup-menu-move="up" data-popup-menu-index="${index}" aria-label="Mover ${esc(option?.[1]||key)} para cima" ${index===0?"disabled":""}>↑</button><button type="button" class="button secondary" data-popup-menu-move="down" data-popup-menu-index="${index}" aria-label="Mover ${esc(option?.[1]||key)} para baixo" ${index===order.length-1?"disabled":""}>↓</button></span></li>`;}).join("");};
  dialog.innerHTML=`<div class="dialog-header"><div><p class="eyebrow">MENU DO DISPOSITIVO · ${esc(card.manufacturer||"")}</p><h2>${esc(card.product_name||card.card_code)}</h2></div><button type="button" class="icon-button" data-popup-menu-close aria-label="Fechar">×</button></div><p class="field-note">PID/modelo: ${esc(card.product_id||"—")} · opções partilhadas por todos os dispositivos deste PID. O conteúdo de controlos e leituras continua a ser gerado pelas funções e DPS conhecidos.</p><ol class="device-popup-menu-order" data-popup-menu-order></ol><p class="connection-result" data-popup-menu-status role="status"></p><div class="dialog-actions"><button type="button" class="button secondary" data-popup-menu-close>Cancelar</button><button type="button" class="button primary" data-popup-menu-save>Guardar menu</button></div>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});draw();dialog.addEventListener("click",async event=>{const move=event.target.closest("[data-popup-menu-move]");if(move){const index=Number(move.dataset.popupMenuIndex),next=move.dataset.popupMenuMove==="up"?index-1:index+1;if(next>=0&&next<order.length){[order[index],order[next]]=[order[next],order[index]];draw();}return;}if(event.target.closest("[data-popup-menu-close]")){dialog.close();return;}const save=event.target.closest("[data-popup-menu-save]");if(!save)return;save.disabled=true;const status=dialog.querySelector("[data-popup-menu-status]"),layout={...(card.layout||{}),popup_menu:{...(card.layout?.popup_menu||{}),order:[...order]}};try{await saveGatewayDeviceCard(card.card_code,{code:card.card_code,manufacturer:card.manufacturer,protocol:card.protocol,product_id:card.product_id,product_name:card.product_name||"",available:card.available!==false,layout});const result=await readGatewayDeviceCards();state.deviceCards=result.cards||[];status.textContent="Menu do pop-up guardado para este modelo.";render();dialog.close();}catch(error){status.textContent=`Não foi possível guardar o menu: ${error.message}`;save.disabled=false;}});dialog.showModal();
}
async function refreshDeviceCards(){try{const [result,catalog]=await Promise.all([readGatewayDeviceCards(),readGatewaySmartProductCatalog()]);state.deviceCards=result.cards||[];state.smartProductCatalog=catalog.tuya_profiles||[];}catch(error){state.deviceCards=[];console.warn("Device cards could not be loaded",error);}finally{state.deviceCardsLoaded=true;}}
function deviceCardTemplate(protocol,productId){return (state.deviceCards||[]).find(card=>card.protocol===protocol&&String(card.product_id)===String(productId)&&card.available!==false);}
function renderDeviceCardFromTemplate(card,device,statusText,metricMarkup,switchButton,provider="tuya",reading={}){
  const layout=card?.layout;if(!card||!Array.isArray(layout?.items)||!layout.items.length)return null;
  const canvasWidth=Math.max(240,Math.min(520,Number(layout.width)||360)),canvasHeight=Math.max(320,Math.min(760,Number(layout.height)||520));
  const readDps=id=>{const rows=[...(reading.status||[]),...(device.current_status||[])];const row=rows.find(item=>Number(item.dps_id??item.dp_id??item.dpId??item.id)===Number(id)||String(item.code||"")===`dps_${id}`);return row?.value??row?.current_value??row?.raw_value??"—";};
   const items=layout.items.filter(item=>item.visible!==false).map(item=>{const role=item.type==="text"&&item.id==="title"?"title":item.type||item.id;let content="";if(role==="title")content=`<strong class="favorite-device-name" ${provider==="shelly"?`data-shelly-name="${esc(device.device_id)}"`: `data-device-name="${esc(device.device_id)}"`}>${esc(device.name||card.product_name||"Dispositivo")}</strong>`;else if(role==="status")content=provider==="shelly"?`<span data-shelly-card-state="${esc(device.device_id)}">${esc(statusText)}</span>`:esc(statusText);else if(role==="metrics")content=metricMarkup||"Sem leituras";else if(role==="controls")content=switchButton||"";else if(role==="icon")content=equipmentIconSvg(device,provider);else if(role==="dps")content=`<span>${esc(item.label||"Leitura")}</span><strong>${esc(readDps(item.dps_id))}</strong>`;else if(role==="submenu")content=`<button type="button" class="device-card-submenu" data-card-submenu="${esc(item.id)}" data-card-submenu-dps="${esc(item.dps_id||"")}">${esc(item.icon||"")} ${esc(item.label||"Abrir")}</button>`;else content=`${esc(item.icon||"")} ${esc(item.label||"")}`;
    const x=Math.max(0,Number(item.x)||0),y=Math.max(0,Number(item.y)||0),width=Math.max(24,Number(item.width)||120),height=Math.max(24,Number(item.height)||48),fontSize=Math.max(10,Math.min(48,Number(item.font_size)||16));
    const style=`position:absolute;left:${x/ canvasWidth*100}%;top:${y/canvasHeight*100}%;width:${width/canvasWidth*100}%;height:${height/canvasHeight*100}%;color:${esc(item.color||"inherit")};font-size:clamp(10px,${fontSize/canvasWidth*100}cqw,48px);border-width:${Math.max(1,Math.min(8,Number(item.border_width)||1))}px;overflow:hidden`;
    return `<div class="device-card-runtime-item device-card-runtime-${esc(role)} ${role==="title"?"favorite-device-info":""}" style="${style}" data-runtime-item="${esc(item.id)}">${content}</div>`;
  }).join("");
   const id=esc(device.device_id||""),providerAttrs=provider==="tuya"?`data-inventory-device="${id}" data-smart-device="${id}" data-smart-provider="tuya"`:provider==="shelly"?`data-smart-device="${id}" data-smart-provider="shelly"`:"",isShellyFavorite=(workspace.prefs.favoriteDeviceIds||[]).includes(device.device_id),expand=provider==="shelly"?`<button type="button" class="shelly-inventory-favorite ${isShellyFavorite?"is-favorite":""}" data-shelly-favorite-toggle="${id}" aria-pressed="${isShellyFavorite}" aria-label="${isShellyFavorite?"Remover dos":"Adicionar aos"} favoritos" title="${isShellyFavorite?"Remover dos":"Adicionar aos"} favoritos">${isShellyFavorite?"★":"☆"}</button><button type="button" class="favorite-expand device-card-runtime-expand" data-shelly-expand="${id}" aria-label="Opções" title="Opções">⌄</button><small class="shelly-card-feedback" data-shelly-card-feedback aria-live="polite"></small>`:"";
   return `<article class="favorite-device inventory-device device-card-runtime ${provider==="tuya"?"is-confirmed":provider==="shelly"&&statusText==="Offline"?"is-fault":"is-confirmed"}" data-card-code="${esc(card.card_code)}" ${providerAttrs} style="--runtime-card-width:${canvasWidth}px;--runtime-card-height:${canvasHeight}px;position:relative;display:block;width:100%;max-width:520px;aspect-ratio:${canvasWidth}/${canvasHeight};height:auto;min-height:0;padding:0;box-sizing:border-box;overflow:hidden;container-type:inline-size" aria-label="${esc(device.name||card.product_name)} · cartão ${esc(card.card_code)}">${items}${expand}<small class="device-card-runtime-code">${esc(card.card_code)}</small></article>`;
}
function openDeviceCardSubmenu(card,item,device){
  const reading=(state.tuyaReadings||[]).find(row=>row.device_id===device?.device_id)||{},rows=[...(reading.status||[]),...(device?.current_status||[])],dpsRow=rows.find(row=>Number(row.dps_id??row.dp_id??row.dpId??row.id)===Number(item.dps_id)),value=dpsRow?.value??dpsRow?.raw_value??"Sem leitura";
  const dialog=document.createElement("dialog");dialog.className="settings-dialog";dialog.innerHTML=`<div class="dialog-header"><div><p class="eyebrow">${esc(card.card_code)} · ${esc(device?.name||card.product_name)}</p><h2>${esc(item.label||"Detalhes")}</h2></div><button type="button" class="icon-button" data-card-submenu-close aria-label="Fechar">×</button></div><div class="dialog-body"><p>${esc(item.submenu_content||"Detalhes associados ao mapa DPS deste PID.")}</p><p><strong>DPS ${esc(item.dps_id||"—")}</strong> · ${esc(value)}</p></div>`;document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector("[data-card-submenu-close]").onclick=()=>dialog.close();dialog.showModal();
}
function renderDeviceInventoryPage(){
  const user=sessionInfo().user||{},owner=user.role==="owner",devices=normalizeTuyaInventory(state.tuyaDevices).map(tuyaDeviceWithPidMap),readings=(Array.isArray(state.tuyaReadings)?state.tuyaReadings:[]).map(normalizeTuyaReading).filter(Boolean);
  const readingByDevice=new Map(readings.map(reading=>[reading.device_id,reading]));
  const confirmed=device=>device.local_verified===true||tuyaReadingConfirmed(readingByDevice.get(device.device_id));
  const confirmedDevices=devices.filter(confirmed),pendingDevices=devices.filter(device=>!confirmed(device));
  if(!state.deviceCardsLoaded){state.deviceCardsLoaded=true;void refreshDeviceCards().then(()=>{if(state.page==="devices")render();});}
  const shellyDevices=Array.isArray(state.shellyDevices)?state.shellyDevices:[];
  const shellyCards=list=>list.map(device=>{
    const connected=device.connection_state==="connected",components=Array.isArray(device.components)?device.components:[];
    const target=components.find(item=>["switch","relay","light","rgb","rgbw","cct","color"].includes(item.component));
    const isLight=!!target&&["light","rgb","rgbw","cct","color"].includes(target.component),channel=Number(target?.id)||0,current=target?(target.status?.output??target.status?.ison):null,id=esc(device.device_id);
    const glyph='<svg viewBox="0 0 28 28" aria-hidden="true" focusable="false"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg>';
    const toggle=target&&current!==null?'<div data-shelly-light-controls="'+id+'" data-shelly-component="'+esc(target.component)+'" data-shelly-channel="'+channel+'"><button class="favorite-state-symbol '+(current===true?'on':'off')+'" type="button" '+(isLight?'data-shelly-light-on="'+id+'" data-shelly-component="'+esc(target.component)+'"':'data-shelly-switch="'+id+'"')+' data-shelly-channel="'+channel+'" data-shelly-target="'+(current===true?'off':'on')+'" aria-pressed="'+(current===true)+'" aria-label="'+(current===true?'Desligar':'Ligar')+' '+esc(device.name)+'" '+(!connected?'disabled':'')+'>'+glyph+'</button></div>':'';
    const label=esc(device.name||device.model||'Dispositivo'),stateLabel=connected?(current===true?'Ligado':current===false?'Desligado':'Online'):'Offline';
     const protocol=isShellyBluBridge(device)?"shelly_blu":"shelly",template=deviceCardTemplate(protocol,device.model||device.device_type||"");
     const customized=renderDeviceCardFromTemplate(template,device,stateLabel,'<small class="inventory-device-metrics" data-shelly-card-metrics>Sem medição</small>',toggle,"shelly");
     if(customized)return customized;
     const isFavorite=(workspace.prefs.favoriteDeviceIds||[]).includes(device.device_id),favoriteButton='<button type="button" class="shelly-inventory-favorite '+(isFavorite?'is-favorite':'')+'" data-shelly-favorite-toggle="'+id+'" aria-pressed="'+isFavorite+'" aria-label="'+(isFavorite?'Remover dos':'Adicionar aos')+' favoritos" title="'+(isFavorite?'Remover dos':'Adicionar aos')+' favoritos">'+(isFavorite?'★':'☆')+'</button>';
     return '<article class="favorite-device inventory-device is-confirmed '+(!connected?'is-fault':'')+'" data-smart-device="'+id+'" data-smart-provider="shelly" tabindex="0" aria-label="'+label+' · '+stateLabel+'"><span class="favorite-device-icon" aria-hidden="true">'+equipmentIconSvg(device,"shelly")+'</span><div class="favorite-device-info"><strong class="favorite-device-name" data-shelly-name="'+id+'">'+label+'</strong><span data-shelly-card-state="'+id+'">'+stateLabel+'</span><small class="shelly-card-feedback" data-shelly-card-feedback aria-live="polite"></small><small class="inventory-device-metrics" data-shelly-card-metrics>Sem medição</small></div><div class="favorite-device-actions">'+favoriteButton+toggle+'<button type="button" class="favorite-expand" data-shelly-expand="'+id+'" aria-label="Opções de '+label+'" title="Opções">⌄</button></div></article>';
  }).join("");
  // A Shelly already present in the Gateway's registered-device response is
  // confirmed inventory. LAN reachability is volatile and must affect only
  // its online/offline status, never make the device jump between tabs.
  const networkInventory=(Array.isArray(state.gatewayDeviceInventory)?state.gatewayDeviceInventory:[]).filter(item=>item&&item.source_provider==="network"),networkPending=networkInventory.filter(item=>item.confirmation_status!=="confirmed"),networkIdentified=networkInventory.filter(item=>item.confirmation_status==="confirmed");
  const activeTab=["confirmed","pending","add","cards"].includes(state.devicesTab)?state.devicesTab:"confirmed";
  const tabs=`<nav class="device-inventory-tabs" aria-label="Separadores de dispositivos">${[["confirmed",`Confirmados (${confirmedDevices.length+networkIdentified.length})`],["pending",`Por confirmar (${pendingDevices.length+networkPending.length})`],["add","Adicionar / sincronizar"],["cards","Cartões"]].map(([id,label])=>`<button type="button" class="device-inventory-tab ${activeTab===id?"active":""}" data-device-tab="${id}" aria-selected="${activeTab===id}">${label}</button>`).join("")}</nav>`;
  const cards=list=>list.map(device=>{try{
    const reading=readingByDevice.get(device.device_id)||{status:Array.isArray(device.current_status)?device.current_status:[],connection_state:"stored_status"};
    const isConfirmed=confirmed(device),fault=tuyaFault(device,reading),offline=reading?.lan_probe?reading.connection_state==="failed"&&device.online===false:device.online===false;
    const statusText=fault?fault.label:offline?"Offline":tuyaDeviceState(device,reading);
    const metrics=(()=>{try{return tuyaSimpleReadings(device,reading)}catch(error){console.warn("Could not map optional Tuya metrics",device.device_id,error);return []}})(),power=metrics.find(metric=>metric.label==="Potência"),voltage=metrics.find(metric=>metric.label==="Tensão"),switchCode=tuyaPrimarySwitchCode(device);
    const metricMarkup=power||voltage?`<small class="inventory-device-metrics"><span>${power?`Potência ${esc(power.value)}`:""}</span><span>${voltage?`Tensão ${esc(voltage.value)}`:""}</span></small>`:"";
    const switchValue=tuyaSwitchState(device,reading,switchCode),powerGlyph='<svg viewBox="0 0 28 28" aria-hidden="true" focusable="false"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg>';
    const switchButton=switchCode?`<button class="favorite-state-symbol ${switchValue===true?"on":switchValue===false?"off":"unknown"}${pendingTuyaSwitchStates.has(`${device.device_id}::${switchCode}`)?" pending":""}" type="button" data-favorite-toggle="${esc(device.device_id)}" data-favorite-code="${esc(switchCode)}" aria-pressed="${switchValue===true}" aria-label="${switchValue===true?"Ligado":switchValue===false?"Desligado":"Sem leitura; tocar para consultar e controlar"} · ${esc(device.name)}">${powerGlyph}</button>`:"";
    const modelCard=renderDeviceCardFromTemplate(deviceCardTemplate("tuya",device.product_id),device,statusText,metricMarkup,switchButton,"tuya",reading);if(modelCard)return modelCard;
    return `<article class="favorite-device inventory-device ${fault||offline?"is-fault":""} ${isConfirmed?"is-confirmed":"is-pending"}" data-inventory-device="${esc(device.device_id)}" data-smart-device="${esc(device.device_id)}" data-smart-provider="tuya" tabindex="0" aria-label="${esc(device.name)} · ${esc(statusText)}"><span class="favorite-device-icon" aria-hidden="true">${equipmentIconSvg(device,"tuya")}</span><div class="favorite-device-info"><strong class="favorite-device-name" data-device-name="${esc(device.device_id)}" title="Toque para informação; duplo clique para configurar">${esc(device.name)}</strong><span>${esc(device.room||device.floor||statusText)}</span>${metricMarkup}</div><div class="favorite-device-actions">${switchButton}<button type="button" class="favorite-expand" data-inventory-expand="${esc(device.device_id)}" aria-label="Opções de ${esc(device.name)}" title="Opções">⌄</button></div></article>`;
  }catch(error){console.warn("Could not render Tuya inventory card",device?.device_id,error);return `<article class="favorite-device inventory-device is-pending"><span class="favorite-device-info"><strong>${esc(device?.name||"Dispositivo Tuya")}</strong><span>Leitura ou dados incompletos</span></span></article>`;}}).join("");
  const equipmentCards=(Array.isArray(state.equipment)?state.equipment:[]).filter(item=>item&&typeof item==="object"&&!Array.isArray(item)&&!["inversores","baterias"].includes(item.category)).map(item=>{const active=Array.isArray(item.readings)&&item.readings.some(reading=>reading&&reading.value!=null&&Number.isFinite(Number(reading.value)));const metrics=(Array.isArray(item.readings)?item.readings:[]).slice(0,3).filter(Boolean).map(reading=>`${esc(reading.evidence?.label||reading.field)} ${esc(formatReading(reading).value)} ${esc(reading.unit||"")}`).join(" · ");return `<article class="favorite-device inventory-device ${active?"is-confirmed":"is-pending"}" data-inventory-equipment="${esc(item.id)}" tabindex="0"><span class="favorite-device-icon" aria-hidden="true">⌁</span><span class="favorite-device-info"><strong>${esc(item.name)}</strong><span>${esc(item.connection_state||item.status||"Registado")}</span><small>${metrics||"Sem medições disponíveis"}</small></span></article>`;}).join("");
  let content="";
  if(activeTab==="confirmed")content=confirmedDevices.length||equipmentCards||shellyDevices.length||networkIdentified.length?`<div class="home-favorites"><div class="favorite-device-grid inventory-device-grid">${cards(confirmedDevices)}${equipmentCards}${shellyCards(shellyDevices)}${networkIdentified.map(item=>`<article class="favorite-device inventory-device is-confirmed" data-network-inventory-device="${esc(item.device_key)}" tabindex="0" role="button" aria-label="Abrir ${esc(item.name||"Equipamento identificado")}"><span class="favorite-device-icon" aria-hidden="true">⌁</span><span class="favorite-device-info"><strong>${esc(item.name||"Dispositivo")}</strong><span>Identificado na rede · ligação de controlo por verificar</span></span><span class="favorite-expand" aria-hidden="true">⌄</span></article>`).join("")}</div></div>`:`<div class="empty-state">Ainda não há equipamentos identificados na rede.</div>`;
  else if(activeTab==="pending")content=pendingDevices.length||networkPending.length?`<div class="home-favorites"><div class="favorite-device-grid inventory-device-grid">${cards(pendingDevices)}${networkPending.map(item=>`<article class="favorite-device inventory-device is-pending" data-network-inventory-device="${esc(item.device_key)}" tabindex="0" role="button" aria-label="Abrir ${esc(item.name||"Dispositivo por confirmar")}"><span class="favorite-device-icon" aria-hidden="true">⌁</span><span class="favorite-device-info"><strong>${esc(item.name||"Dispositivo")}</strong><span>Por confirmar · descoberto na rede</span></span><span class="favorite-expand" aria-hidden="true">⌄</span></article>`).join("")}</div></div>`:`<div class="empty-state">Não há dispositivos por confirmar neste momento.</div>`;
  else if(activeTab==="cards")content=renderDeviceCardsPanel();
  else content=`<section class="panel"><h2>Adicionar equipamento</h2><p>O Gateway procura na rede e reconhece automaticamente os equipamentos que consegue identificar. Não precisas de escolher a ligação ou o protocolo.</p><div class="dialog-actions"><button id="device-add-scan" class="button primary" type="button" ${owner?"":"disabled"}>Procurar equipamentos</button></div><p class="field-note" id="device-add-status" role="status">Quando encontrar um equipamento, abre a linha para confirmar o nome, fabricante e modelo. Sensores Shelly BLU são procurados separadamente na ficha da ponte compatível; a pesquisa LAN não espera por uma varredura Bluetooth. A configuração inicial pela rede Wi-Fi própria do dispositivo ainda não está disponível.</p><div id="device-add-results" class="local-network-results" aria-live="polite" hidden></div></section><section class="panel"><h2>Equipamentos já conhecidos</h2>${shellyDevices.length?`<div class="home-favorites"><div class="favorite-device-grid inventory-device-grid">${shellyCards(shellyDevices)}</div></div>`:`<p class="field-note">Os equipamentos encontrados e guardados aparecem no inventário Devices.</p>`}</section>`;
  return `<div class="page-heading"><div><p class="eyebrow">CONTROLO · GATEWAY</p><h1>Dispositivos</h1><p>Toca num cartão para ver o resumo; faz duplo clique no nome para editar.</p></div><button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button></div>${tabs}<section class="device-inventory-content home-favorites" data-device-tab-content="${activeTab}">${content}</section>`;
}
function renderGatewayHousePage(){
  const profile=state.siteProfile||{floors:[]}, owner=sessionInfo().authenticated&&sessionInfo().user?.role==="owner";
  const floors=profile.floors||[], selected=floors.find(item=>item.id===houseView.floorId), activeTab=houseView.tab;
  const totalRooms=floors.reduce((sum,item)=>sum+(item.rooms||[]).length,0), rooms=selected?.rooms||[];
  const floorButtons=`<button type="button" class="gateway-house-floor-chip ${!selected?"active":""}" data-house-general="true" data-house-view="overview">Geral</button>${floors.map(floor=>`<button type="button" class="gateway-house-floor-chip ${floor.id===selected?.id?"active":""}" data-house-select-floor="${esc(floor.id)}" data-house-view="overview">${esc(floor.name)}</button>`).join("")}`;
  const floorList=floors.map(floor=>`<button type="button" class="gateway-house-floor-row" data-house-select-floor="${esc(floor.id)}" data-house-tab="floor"><span class="gateway-house-icon">⌂</span><span><strong>${esc(floor.name)}</strong><small>${(floor.rooms||[]).length} divisões</small></span><span class="gateway-house-arrow">›</span></button>`).join("");
  const planColumns=Math.max(1,Math.ceil(Math.sqrt(rooms.length||1))),planRows=Math.max(1,Math.ceil((rooms.length||1)/planColumns)),planEditing=owner&&houseView.planEditing;
  const roomTiles=rooms.map((room,index)=>{const box=room.plan_rect||{},col=index%planColumns,row=Math.floor(index/planColumns),x=Number.isFinite(Number(box.x))?Number(box.x):col*100/planColumns+1.5,y=Number.isFinite(Number(box.y))?Number(box.y):row*100/planRows+1.5,w=Number.isFinite(Number(box.w))?Number(box.w):100/planColumns-3,h=Number.isFinite(Number(box.h))?Number(box.h):100/planRows-3;return `<button type="button" class="gateway-house-room-tile${planEditing?" is-editing":""}" data-house-select-room="${esc(room.id)}" style="--room-x:${x}%;--room-y:${y}%;--room-w:${w}%;--room-h:${h}%"><span class="gateway-house-room-name">${esc(room.name)}</span><small>Divisão</small>${planEditing?`<span class="gateway-house-room-resize" aria-label="Redimensionar ${esc(room.name)}"></span>`:""}</button>`;}).join("");
  const allRoomGroups=floors.map(floor=>`<section class="gateway-house-room-group"><div class="gateway-house-section-head"><h2>${esc(floor.name)}</h2></div><div class="gateway-house-room-list">${(floor.rooms||[]).map(room=>`<button class="gateway-house-room-row" type="button" data-house-select-room="${esc(room.id)}" data-house-room-floor="${esc(floor.id)}"><span class="gateway-house-icon">⌂</span><strong>${esc(room.name)}</strong><span class="gateway-house-arrow">›</span></button>`).join("")||`<div class="empty-state">Ainda não há divisões neste piso.</div>`}</div></section>`).join("");
  const selectedPhoto=selected?.photo_data_url?`style="--floor-photo:url('${esc(selected.photo_data_url)}')"`:"";
  const planImage=selected?.plan_data_url||null;
  const planZoom=Number(selected?.plan_zoom||1);
  const floorTabs=`<nav class="gateway-house-floor-tabs" aria-label="Conteúdo do piso">${[["floor","⌂","Visão geral"],["floor-photo","▧","Fotografia"],["plan","▦","Planta"],["rooms","♧","Divisões"],["config","⚙","Configuração"]].map(([id,icon,label])=>`<button type="button" class="${activeTab===id?"active":""}" data-house-tab="${id}"><span aria-hidden="true">${icon}</span>${label}</button>`).join("")}</nav>`;
  const controls=owner?`<div class="gateway-house-owner-actions"><button class="button secondary" data-site-action="add-floor">＋ Adicionar piso</button>${selected?`<button class="text-link" data-site-action="rename-floor" data-floor-id="${esc(selected.id)}">Editar piso</button><button class="text-link danger-link" data-site-action="remove-floor" data-floor-id="${esc(selected.id)}">Remover</button>`:""}</div>`:"";
  const overview=`<nav class="gateway-house-floor-nav" aria-label="Navegação por piso"><div class="gateway-house-floor-chips">${floorButtons}</div></nav>${selected?`<div class="gateway-house-section-head"><div><h2>${esc(selected.name)} · Divisões</h2><small>${rooms.length} divisões</small></div>${owner?`<button class="button secondary" data-site-action="add-room" data-floor-id="${esc(selected.id)}">＋ Adicionar divisão</button>`:""}</div><div class="gateway-house-room-list">${rooms.map(room=>`<button class="gateway-house-room-row" type="button" data-house-select-room="${esc(room.id)}" data-house-room-floor="${esc(selected.id)}"><span class="gateway-house-icon">⌂</span><strong>${esc(room.name)}</strong><span class="gateway-house-arrow">›</span></button>`).join("")||`<div class="empty-state">Ainda não há divisões neste piso.</div>`}</div>${owner?`<div class="gateway-house-owner-actions"><button class="button secondary" data-house-tab="floor-photo">${selected.photo_data_url?"Fotografia":"Adicionar fotografia"}</button><button class="button secondary" data-house-tab="plan">Planta</button><button class="text-link" data-house-tab="config">Configurar piso</button></div>`:""}`:`<div class="gateway-house-section-head"><h2>Divisões de todos os pisos</h2>${owner?`<button class="text-link" data-site-action="add-floor">＋ Adicionar piso</button>`:""}</div>${allRoomGroups||`<div class="empty-state">Adiciona o primeiro piso para começar a organizar a casa.</div>`}`}`;
  const floorOverview=selected?`<section class="gateway-house-floor-hero" ${selectedPhoto}><span>PISO</span><h1>${esc(selected.name)}</h1><div>${owner?`<button class="button secondary" data-site-action="upload-floor-photo" data-floor-id="${esc(selected.id)}">Substituir fotografia</button><button class="button secondary" data-site-action="upload-plan" data-floor-id="${esc(selected.id)}">${selected.plan_data_url?"Substituir planta":"Adicionar planta"}</button>`:""}</div></section><div class="gateway-house-section-head"><h2>Divisões</h2>${owner?`<button class="button secondary" data-site-action="add-room" data-floor-id="${esc(selected.id)}">＋ Adicionar divisão</button>`:""}</div><div class="gateway-house-room-list">${rooms.map(room=>`<button class="gateway-house-room-row" type="button" data-house-select-room="${esc(room.id)}"><span class="gateway-house-icon">⌂</span><strong>${esc(room.name)}</strong><span class="gateway-house-arrow">›</span></button>`).join("")||`<div class="empty-state">Ainda não há divisões neste piso.</div>`}</div>${controls}`:`<div class="empty-state">Adiciona o primeiro piso para começar a organizar a casa.</div>`;
  const planView=selected?`<div class="gateway-house-section-head"><div><small>CASA › ${esc(selected.name)}</small><h1>Planta do piso</h1></div><div><button class="text-link" data-house-tab="overview">← Casa</button>${owner?`<button class="text-link" data-site-action="upload-plan" data-floor-id="${esc(selected.id)}">${planImage?"Substituir planta":"＋ Adicionar planta"}</button>`:""}</div></div>${owner&&!planImage?`<section class="gateway-house-plan-empty"><span aria-hidden="true">▦</span><div><strong>Adiciona a planta deste piso</strong><small>A imagem fica no fundo; podes depois organizar e ajustar cada divisão.</small></div><button class="button secondary" data-site-action="upload-plan" data-floor-id="${esc(selected.id)}">Escolher imagem</button></section>`:""}${owner&&rooms.length?`<div class="gateway-house-plan-tools"><button type="button" class="${planEditing?"active":""}" data-house-plan-edit="true">${planEditing?"Concluir disposição":"Ajustar divisões"}</button>${planEditing?`<small>Arrasta uma divisão para a mover; usa o canto para ajustar o tamanho.</small>`:""}</div>`:""}<section class="gateway-house-plan${planImage?" has-image":""}" style="--plan-zoom:${planZoom}">${planImage?`<div class="gateway-house-plan-image" style="background-image:url('${esc(planImage)}')"></div>`:""}<div class="gateway-house-plan-tiles${planEditing?" is-editing":""}">${roomTiles}</div>${!rooms.length?`<div class="gateway-house-plan-no-rooms"><span>⌂</span><strong>As divisões aparecem aqui</strong><small>Adiciona as divisões deste piso para as organizar na planta.</small></div>`:""}</section>${owner&&planImage?`<label class="gateway-house-zoom">Tamanho da planta <output id="house-plan-zoom-value">${planZoom.toFixed(1)}×</output><input type="range" min="1" max="2.5" step=".05" value="${planZoom}" data-site-plan-zoom="${esc(selected.id)}"></label>`:""}<div class="gateway-house-section-head"><h2>Divisões</h2>${owner?`<button class="button secondary" data-site-action="add-room" data-floor-id="${esc(selected.id)}">＋ Adicionar divisão</button>`:""}</div><div class="gateway-house-room-list">${rooms.map(room=>`<button class="gateway-house-room-row" type="button" data-house-select-room="${esc(room.id)}"><span class="gateway-house-icon">⌂</span><strong>${esc(room.name)}</strong><span class="gateway-house-arrow">›</span></button>`).join("")}</div>${controls}`:`<div class="empty-state">Seleciona um piso.</div>`;
  const photoView=selected?`<div class="gateway-house-section-head"><div><small>CASA › ${esc(selected.name)}</small><h1>Fotografia do piso</h1></div><div><button class="text-link" data-house-tab="overview">← Casa</button>${owner?`<button class="button secondary" data-site-action="upload-floor-photo" data-floor-id="${esc(selected.id)}">${selected.photo_data_url?"Substituir fotografia":"Adicionar fotografia"}</button>`:""}</div></div>${selected.photo_data_url?`<div class="gateway-house-photo-view" style="background-image:url('${esc(selected.photo_data_url)}')"></div>`:`<div class="empty-state">Ainda não foi adicionada uma fotografia a este piso.</div>`}`:`<div class="empty-state">Seleciona um piso.</div>`;
  const configView=selected?`<div class="gateway-house-section-head"><div><small>CASA › ${esc(selected.name)}</small><h1>Configuração · ${esc(selected.name)}</h1></div><button class="text-link" data-house-tab="overview">← Casa</button></div><section class="gateway-house-config-card"><label>Nome do piso</label><div><strong>${esc(selected.name)}</strong>${owner?`<button class="button secondary" data-site-action="rename-floor" data-floor-id="${esc(selected.id)}">Renomear</button>`:""}</div></section><section class="gateway-house-config-card"><label>Fotografia do piso</label>${selected.photo_data_url?`<div class="gateway-house-photo-thumb" style="background-image:url('${esc(selected.photo_data_url)}')"></div>`:`<p class="field-note">Sem fotografia.</p>`}${owner?`<button class="button secondary" data-site-action="upload-floor-photo" data-floor-id="${esc(selected.id)}">${selected.photo_data_url?"Substituir fotografia":"Adicionar fotografia"}</button>`:""}</section><section class="gateway-house-config-card"><label>Planta e divisões (${rooms.length})</label><p class="field-note">A planta é guardada no Gateway e partilhada entre sessões.</p>${owner?`<button class="button secondary" data-site-action="upload-plan" data-floor-id="${esc(selected.id)}">${planImage?"Substituir planta":"Adicionar planta"}</button><button class="button secondary" data-site-action="add-room" data-floor-id="${esc(selected.id)}">＋ Adicionar divisão</button>`:""}${rooms.map(room=>`<div class="gateway-house-config-room"><span>${esc(room.name)}</span>${owner?`<button class="text-link" data-site-action="upload-room-photo" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">${room.photo_data_url?"Substituir foto":"Adicionar foto"}</button><button class="text-link" data-site-action="rename-room" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">Renomear</button><button class="text-link danger-link" data-site-action="remove-room" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">Remover</button>`:""}</div>`).join("")}</section>`:`<div class="empty-state">Seleciona um piso.</div>`;
  const room=rooms.find(item=>item.id===houseView.roomId);
  const roomView=room?`<div class="gateway-house-section-head"><div><small>${esc(selected?.name||"Piso")} › DIVISÃO</small><h1>${esc(room.name)}</h1></div><button class="text-link" data-house-tab="overview">← Casa</button></div>${room.photo_data_url?`<div class="gateway-house-photo-view room-photo" style="background-image:url('${esc(room.photo_data_url)}')"></div>`:`<div class="gateway-house-photo-empty"><span>⌂</span><p>Ainda não foi adicionada uma fotografia a esta divisão.</p></div>`}<section class="gateway-house-room-detail"><h2>${esc(room.name)}</h2><p>Os dispositivos desta divisão aparecerão aqui quando forem associados a esta divisão.</p>${owner?`<button class="button secondary" data-site-action="upload-room-photo" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">${room.photo_data_url?"Substituir fotografia":"Adicionar fotografia"}</button><button class="text-link" data-site-action="rename-room" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">Renomear divisão</button><button class="text-link danger-link" data-site-action="remove-room" data-floor-id="${esc(selected.id)}" data-room-id="${esc(room.id)}">Remover divisão</button>`:""}</section>`:`<div class="empty-state">Seleciona uma divisão.</div>`;
  const content=activeTab==="room"?roomView:activeTab==="plan"?planView:activeTab==="floor-photo"?photoView:activeTab==="config"?configView:overview;
  const isFloorView=["floor","floor-photo","plan","config"].includes(activeTab);
  return `<div class="gateway-house-page"><main class="gateway-house-content">${content}</main><input class="visually-hidden" type="file" accept="image/*" data-house-photo-input hidden></div>`;
}
async function handleSiteStructureAction(button){
  if(sessionInfo().user?.role!=="owner")return;
  const current=state.siteProfile||{name:"Solar Energy",photo_data_url:null,floors:[]}, floors=structuredClone(current.floors||[]), action=button.dataset.siteAction, floor=floors.find(item=>item.id===button.dataset.floorId), room=floor?.rooms.find(item=>item.id===button.dataset.roomId);
  const ask=(label,value="")=>{const name=prompt(label,value);return typeof name==="string"?name.trim():null;};
  if(action==="add-floor"){const name=ask("Nome do piso (ex.: Rés do chão):");if(!name)return;floors.push({id:`floor-${crypto.randomUUID()}`,name,rooms:[]});}
  else if(action==="rename-floor"){if(!floor)return;const name=ask("Novo nome do piso:",floor.name);if(!name)return;floor.name=name;}
  else if(action==="remove-floor"){if(!floor||!confirm(`Remover o piso “${floor.name}” e as suas divisões?`))return;floors.splice(floors.indexOf(floor),1);}
  else if(action==="add-room"){if(!floor)return;const name=ask("Nome da divisão:");if(!name)return;floor.rooms.push({id:`room-${crypto.randomUUID()}`,name});}
  else if(action==="rename-room"){if(!floor||!room)return;const name=ask("Novo nome da divisão:",room.name);if(!name)return;room.name=name;}
  else if(action==="remove-room"){if(!floor||!room||!confirm(`Remover a divisão “${room.name}”?`))return;floor.rooms.splice(floor.rooms.indexOf(room),1);}
  else if(action==="upload-floor-photo"||action==="upload-plan"||action==="upload-room-photo"){const input=document.querySelector("[data-house-photo-input]");if(!input)return;input.dataset.photoKind=action==="upload-plan"?"plan":action==="upload-room-photo"?"room":"floor";input.dataset.floorId=floor?.id||"";input.dataset.roomId=room?.id||button.dataset.roomId||"";input.click();return;}
  else return;
  const saved=await saveGatewaySiteProfile({...current,floors});state.siteProfile=saved;render();
}
function render() {
  freshness();
  $("#breadcrumb").textContent = `A SUA PROPRIEDADE / ${pageLabel(state.page).toUpperCase()}`;
  const propertyHost=$("#property-hero-host");
  if(propertyHost)propertyHost.innerHTML=renderHomePhotoHero(state.page==="inicio"?"Home":pageLabel(state.page));
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
  const liveAreaPages=["energia","inversores","baterias","paineis-solares","mineradoras","ev","aqs","soalho-radiante"];
  const liveUtilityPages=["casa","devices","profile","automatismos","producao"];
  const gatewayBackedPages = ["inicio", "engine", "gestao-excedentes", ...CATEGORIES.map(c => c.id), ...liveAreaPages, ...liveUtilityPages];
  let pageHtml;
  try {
    if (state.mode !== "SIMULATED" && !gatewayBackedPages.includes(state.page)) {
      pageHtml = `<div class="page-heading"><div><p class="eyebrow">FUNÇÃO NÃO DISPONÍVEL NO GATEWAY ATUAL</p><h1>${esc(pageLabel(state.page))}</h1><p>Esta área ainda não tem um contrato de dados ou comandos físicos no Gateway. Para evitar confusão, a sessão autenticada não apresenta controlos ou valores de demonstração aqui.</p></div></div><div class="empty-state">Sem dados reais fornecidos pelo Gateway para esta área. A administração está na página Owner.</div>`;
    } else {
      pageHtml = state.page === "inicio" ? renderOverview() : state.page === "gestao-excedentes" ? renderSurplusManager() : state.mode!=="SIMULATED"&&liveAreaPages.includes(state.page)?renderGatewayArea(state.page):state.mode!=="SIMULATED"&&liveUtilityPages.includes(state.page)?renderGatewayUtilityPage(state.page):state.page === "engine" && state.mode !== "SIMULATED" ? renderLiveEnergyEngine() : (workspacePage || (CATEGORIES.some(c=>c.id===state.page) ? renderCategory(state.page) : renderOverview()));
      if(state.mode === "SIMULATED" && state.page === "automatismos") pageHtml = renderAutomationsPage(workspace, automationEditingId);
      if(state.mode === "SIMULATED" && state.page === "producao") pageHtml = renderSolarProductionPage();
      if(state.mode === "SIMULATED" && state.page === "profile") pageHtml += renderDemoAdminPanel();
    }
  } catch (error) {
    console.error(`Could not render SolarMiner page: ${state.page}`, error);
    pageHtml = `<div class="page-heading"><div><p class="eyebrow">GATEWAY · INTERFACE</p><h1>${esc(pageLabel(state.page))}</h1></div></div><section class="panel"><h2>Não foi possível abrir esta área</h2><p class="field-note">A navegação continua disponível. Os dados guardados no Gateway não foram alterados.</p><p class="field-note">Detalhe para diagnóstico: ${esc(String(error?.message||"Erro sem detalhe"))}</p></section>`;
  }
  const energyTabScroll=$("#page-content .energy-tabs")?.scrollLeft||0;
  $("#page-content").innerHTML = pageHtml;
  const enginePanels=$("#page-content").querySelectorAll("[data-engine-tab-panel]");
  if(enginePanels.length){
    if(!Array.from(enginePanels).some(panel=>panel.dataset.engineTabPanel===energyEngineActiveTab))energyEngineActiveTab="summary";
    enginePanels.forEach(panel=>{panel.hidden=panel.dataset.engineTabPanel!==energyEngineActiveTab;});
    $("#page-content").querySelectorAll("[data-engine-tab]").forEach(tab=>{const selected=tab.dataset.engineTab===energyEngineActiveTab;tab.setAttribute("aria-selected",String(selected));tab.classList.toggle("selected",selected);});
  }
  const surplusPanels=$("#page-content").querySelectorAll("[data-surplus-panel]");
  if(surplusPanels.length){
    if(!Array.from(surplusPanels).some(panel=>panel.dataset.surplusPanel===surplusActiveTab))surplusActiveTab="status";
    surplusPanels.forEach(panel=>{panel.hidden=panel.dataset.surplusPanel!==surplusActiveTab;});
    $("#page-content").querySelectorAll("[data-surplus-tab]").forEach(tab=>{const selected=tab.dataset.surplusTab===surplusActiveTab;tab.setAttribute("aria-selected",String(selected));tab.classList.toggle("selected",selected);});
  }
  const pvStringForm=$("#pv-string-form");
  pvStringForm?.addEventListener("submit",event=>{event.preventDefault();event.stopImmediatePropagation();void savePvStringForm(pvStringForm);});
  const aqsForm=$("#aqs-form");
  aqsForm?.addEventListener("submit",event=>{event.preventDefault();event.stopImmediatePropagation();void saveAqsForm(aqsForm);});
  const engineChartDialog=$("#engine-history-dialog");
  if(engineChartDialog){engineChartDialog.addEventListener("close",()=>{state.engineHistoryChart.open=false;});if(state.engineHistoryChart.open&&!engineChartDialog.open)engineChartDialog.showModal();}
  const newEnergyTabs=$("#page-content .energy-tabs");if(newEnergyTabs)newEnergyTabs.scrollLeft=energyTabScroll;
  applyPreferences();
  applyLiveFontScale();
  const hero = $("#property-hero");
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
  if (!["inicio", ...CATEGORIES.map(c=>c.id), "energia", "casa", "profile", "engine", "gestao-excedentes", "devices", "inversores", "baterias", "paineis-solares", "ev", "aqs", "mineradoras", "soalho-radiante", "automatismos", "producao", "owner"].includes(page)) return;
  const enteringEnergy=page==="energia"&&state.page!=="energia",enteringDevices=page==="devices"&&state.page!=="devices";state.page = page; render();
  if(page==="automatismos"&&sessionInfo().authenticated)void loadGatewayUserAutomations({quiet:true});
  if(enteringEnergy&&sessionInfo().authenticated)refreshGatewayReadings();
  if(enteringDevices&&sessionInfo().user?.role==="owner"){refreshGatewayReadings();void refreshTuyaInventoryStatus();void refreshShellyInventoryStatus({quiet:true});void refreshSmartProductCatalog();}
  if(page==="casa" && workspace.house.restoreScroll){const y=Number(workspace.house.returnScrollY||0);workspace.house.restoreScroll=false;requestAnimationFrame(()=>window.scrollTo({top:y,behavior:"auto"}));}else window.scrollTo({top:0,behavior:"auto"});
}
function buildUserAutomationPayload(form){
  const caps=state.userAutomations.capabilities||{},triggerChoice=form.elements["automation-trigger"].value,name=form.elements["automation-name"].value.trim();let trigger;
  if(triggerChoice==="schedule"){
    const weekdays=[...form.querySelectorAll('input[name="automation-day"]:checked')].map(item=>Number(item.value));
    trigger={type:"schedule",at:form.elements["automation-time"].value,weekdays};
  }else{
    const source=(caps.triggers||[]).find(item=>item.id===triggerChoice);if(!source)throw new Error("Escolhe uma condição Tuya que esteja disponível no Gateway.");
    const raw=form.elements["automation-value"].value.trim();let value=raw;
    if(["bool","boolean"].includes(source.type)){if(!["true","false"].includes(raw.toLowerCase()))throw new Error("Para um estado booleano, escreve true ou false.");value=raw.toLowerCase()==="true";}
    else if(["value","integer","number"].includes(source.type)){value=Number(raw);if(!raw||!Number.isFinite(value))throw new Error("Indica um valor numérico válido.");}
    trigger={type:"tuya_state",device_id:source.device_id,code:source.code,operator:form.elements["automation-operator"].value,value,for_seconds:Number(form.elements["automation-for"].value||0)};
  }
  const actions=[...form.querySelectorAll("[data-auto-action-row]")].map(row=>{const target=(caps.targets||[]).find(item=>item.id===row.querySelector("[data-auto-target]")?.value);if(!target)throw new Error("Escolhe uma saída local para cada ação.");if(target.type==="tuya")return {target_type:"tuya",operation:"switch",device_id:target.device_id,code:target.code,on:row.querySelector("[data-auto-switch-state]").value==="on"};if(target.type==="shelly_light"){const percent=Number(row.querySelector("[data-auto-percent]").value);if(!Number.isInteger(percent)||percent<0||percent>100)throw new Error("A luminosidade tem de ficar entre 0 e 100%.");return {target_type:"shelly",operation:"brightness",device_id:target.device_id,component:target.component,channel:target.channel,percent};}return {target_type:"shelly",operation:"switch",device_id:target.device_id,channel:target.channel,on:row.querySelector("[data-auto-switch-state]").value==="on"};});
  if(!actions.length||actions.length>8)throw new Error("Define entre uma e oito ações.");
  return {name,trigger,actions,enabled:form.elements["automation-enabled"].checked};
}
function updateUserAutomationFormVisibility(form){
  const trigger=form.elements["automation-trigger"],scheduled=trigger?.value==="schedule";
  const stateFields=form.querySelector("[data-auto-state-fields]"),scheduleFields=form.querySelector("[data-auto-schedule-fields]");if(stateFields)stateFields.hidden=scheduled;if(scheduleFields)scheduleFields.hidden=!scheduled;
  form.querySelectorAll("[data-auto-action-row]").forEach(row=>{const target=(state.userAutomations.capabilities?.targets||[]).find(item=>item.id===row.querySelector("[data-auto-target]")?.value),brightness=target?.type==="shelly_light",switchFields=row.querySelector("[data-auto-row-switch]"),brightnessFields=row.querySelector("[data-auto-row-brightness]");if(switchFields)switchFields.hidden=brightness;if(brightnessFields)brightnessFields.hidden=!brightness;});
}
function appendUserAutomationActionRow(form){
  const list=form.querySelector("[data-auto-action-list]"),targets=state.userAutomations.capabilities?.targets||[];if(!list||list.children.length>=8)return;
  const row=document.createElement("div");row.className="feature-extra-row";row.dataset.autoActionRow="";
  const label=document.createElement("label");label.className="feature-field";label.append("Destino");const target=document.createElement("select");target.dataset.autoTarget="";target.required=true;
  for(const item of targets){const option=document.createElement("option");option.value=item.id;option.textContent=item.label;target.append(option);}label.append(target);row.append(label);
  const commandBox=document.createElement("div");commandBox.dataset.autoRowSwitch="";commandBox.className="feature-field";const commandLabel=document.createElement("label");commandLabel.append("Comando");const command=document.createElement("select");command.dataset.autoSwitchState="";for(const [value,text] of [["on","Ligar"],["off","Desligar"]]){const option=document.createElement("option");option.value=value;option.textContent=text;command.append(option);}commandLabel.append(command);commandBox.append(commandLabel);row.append(commandBox);
  const brightnessBox=document.createElement("div");brightnessBox.dataset.autoRowBrightness="";brightnessBox.hidden=true;brightnessBox.className="feature-field";const brightnessLabel=document.createElement("label");brightnessLabel.append("Definir luminosidade (%)");const percent=document.createElement("input");percent.type="number";percent.min="0";percent.max="100";percent.step="1";percent.value="50";percent.dataset.autoPercent="";brightnessLabel.append(percent);brightnessBox.append(brightnessLabel);row.append(brightnessBox);
  const remove=document.createElement("button");remove.type="button";remove.className="button secondary";remove.dataset.userAuto="remove-action";remove.textContent="Remover ação";row.append(remove);list.append(row);
  list.querySelectorAll('[data-user-auto="remove-action"]').forEach(button=>button.hidden=list.children.length<2);updateUserAutomationFormVisibility(form);
}
async function saveUserAutomationForm(form){
  const status=form.querySelector("#gateway-auto-form-status"),button=form.querySelector('[type="submit"]');try{const payload=buildUserAutomationPayload(form);button.disabled=true;status.textContent="A guardar a regra no Gateway…";if(userAutomationEditingId)await updateGatewayUserAutomation(userAutomationEditingId,payload);else await createGatewayUserAutomation(payload);userAutomationEditingId="";showFeatureNotice(payload.enabled?"Automatismo guardado e ativado no Gateway.":"Automatismo guardado desligado. Ativa-o quando estiveres pronto.");await loadGatewayUserAutomations({quiet:true});}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}finally{if(button)button.disabled=false;}
}
async function dryRunUserAutomation(form){
  const status=form.querySelector("#gateway-auto-form-status");try{const result=await dryRunGatewayUserAutomation(buildUserAutomationPayload(form));status.textContent=`Simulação: ${result.matched?"condição satisfeita":"não executaria"} · ${result.reason}. Nenhum comando foi enviado.`;}catch(error){status.textContent=`Não foi possível simular: ${error.message}`;}
}
function populateMore() { $("#more-links").innerHTML = [{id:"energia",label:"Energia",icon:"◉"},{id:"casa",label:"Casa",icon:"⌂"},{id:"profile",label:"Profile",icon:"○"},{id:"devices",label:"Dispositivos",icon:"⚙"},{id:"automatismos",label:"Automatismos",icon:"⟳"},...CATEGORIES,{id:"paineis-solares",label:"Painéis solares",icon:"☼"}].map(c=>`<button data-page="${esc(c.id)}"><span>${esc(c.icon)}</span>${esc(c.label)}<span class="more-arrow">↗</span></button>`).join("") + (state.mode==="SIMULATED"?`<button id="more-settings"><span>⚙</span>Personalizar demonstração<span class="more-arrow">↗</span></button>`:""); $("#more-settings")?.addEventListener("click",()=>{$("#more-dialog").close();$("#settings-dialog").showModal();}); }

document.querySelectorAll(".sidebar [data-page]").forEach(el=>el.addEventListener("click",()=>navigate(el.dataset.page)));
window.addEventListener("solar-workspace-updated",(event)=>{render();if(event.detail?.persisted===false||event.detail?.photosPersisted===false){setTimeout(()=>{const notice=$("#notice");notice.hidden=false;notice.textContent="O browser não confirmou a gravação local. Mantém esta página aberta e verifica as permissões/armazenamento do browser.";},0);}});
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
$('#page-content').addEventListener('pointerdown',e=>{
  const card=e.target.closest('.home-favorites .favorite-device[data-favorite-device]');
  if(!card||e.target.closest('button,a,input,select,textarea'))return;
  clearTimeout(favoriteReorderPressTimer);favoriteReorderPressTimer=null;
  card.style.touchAction="none";
  favoriteReorderPressTimer=setTimeout(()=>{
    if(!card.isConnected)return;
    favoriteReorder={card,pointerId:e.pointerId,grid:card.closest('.favorite-device-grid')};
    card.classList.add('is-reordering');
    try{card.setPointerCapture(e.pointerId);}catch{}
  },450);
},{passive:true});
$('#page-content').addEventListener('pointermove',e=>{
  if(!favoriteReorder||favoriteReorder.pointerId!==e.pointerId)return;
  const {card,grid}=favoriteReorder,target=document.elementFromPoint(e.clientX,e.clientY)?.closest('.home-favorites .favorite-device[data-favorite-device]');
  if(!target||target===card||target.closest('.favorite-device-grid')!==grid)return;
  const rect=target.getBoundingClientRect(),after=e.clientY>rect.top+rect.height/2;
  grid.insertBefore(card,after?target.nextSibling:target);
  e.preventDefault();
},{passive:false});
function finishFavoriteReorder(e){
  clearTimeout(favoriteReorderPressTimer);favoriteReorderPressTimer=null;
  if(!favoriteReorder){const card=e.target.closest?.('.home-favorites .favorite-device[data-favorite-device]');if(card)card.style.touchAction="";return;}
  if(e.pointerId!==favoriteReorder.pointerId)return;
  const {card,grid}=favoriteReorder;favoriteReorder=null;card.classList.remove('is-reordering');card.style.touchAction="";favoriteDragSuppressClickUntil=Date.now()+700;
  const visibleOrder=[...grid.querySelectorAll('.favorite-device[data-favorite-device]')].map(item=>item.dataset.favoriteDevice);
  workspace.prefs.favoriteDeviceIds=reorderFavoriteIds(workspace.prefs.favoriteDeviceIds,visibleOrder);saveDemoWorkspace();
}
for(const eventName of ['pointerup','pointercancel','lostpointercapture'])$('#page-content').addEventListener(eventName,finishFavoriteReorder,{passive:true});
$('#page-content').addEventListener('dblclick',e=>{if(e.target.closest('button,a,input,select,textarea'))return;const card=e.target.closest('.favorite-device[data-favorite-device]');if(!card||!e.target.closest('.favorite-device-info'))return;clearTimeout(favoriteCardClickTimer);favoriteCardClickTimer=null;if(card.dataset.deviceKind==="tuya"){const device=state.tuyaDevices.find(item=>item.device_id===card.dataset.favoriteDevice);if(device){openTuyaDeviceEditor(device);return;}}openFavoriteDeviceDetails(card.dataset.favoriteDevice,card.dataset.deviceKind);});
$('#page-content').addEventListener('click',async e=>{
  if(Date.now()<favoriteDragSuppressClickUntil){e.preventDefault();e.stopImmediatePropagation();return;}
  const expand=e.target.closest("[data-favorite-expand],[data-inventory-expand]");if(expand){const id=expand.dataset.favoriteExpand||expand.dataset.inventoryExpand,device=state.tuyaDevices.find(item=>item.device_id===id);if(device)openTuyaQuickControls(device);return;}
  const favoriteCard=e.target.closest('.favorite-device[data-favorite-device]');
  if(favoriteCard&&!e.target.closest('button,a,input,select,textarea')){clearTimeout(favoriteCardClickTimer);favoriteCardClickTimer=setTimeout(()=>{favoriteCardClickTimer=null;openFavoriteDeviceDetails(favoriteCard.dataset.favoriteDevice,favoriteCard.dataset.deviceKind);},340);return;}
  if(e.target.closest('#profile-open-gateway')){$('#gateway-dialog').showModal();return;}
  const toggle=e.target.closest('[data-favorite-toggle]');
  if(toggle){
    if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode controlar dispositivos.");return;}
    const deviceId=toggle.dataset.favoriteToggle,code=toggle.dataset.favoriteCode;
    if(favoriteControlPending.has(deviceId))return;
    favoriteControlPending.add(deviceId);document.querySelectorAll('[data-favorite-toggle]').forEach(button=>{if(button.dataset.favoriteToggle===deviceId)button.disabled=true;});
    try{
      const device=tuyaDeviceWithPidMap(state.tuyaDevices.find(item=>item.device_id===deviceId));
      const live=state.tuyaReadings.find(item=>item.device_id===deviceId),current=device?tuyaSwitchState(device,live,code):undefined;
      if(typeof current!=="boolean")throw new Error(device&&!tuyaSwitchCodeHasLocalMapping(device,code)?"Falta o mapeamento DPS local exato deste canal.":"Ainda não há estado ON/OFF confirmado pelo varrimento independente.");
      if(!device||!tuyaSwitchCodeHasLocalMapping(device,code))throw new Error("Falta o mapeamento DPS local exato deste canal.");
      await sendTuyaSwitchCommand(device,code,!current);
    }catch(error){showFeatureNotice(`Falha no controlo LAN: ${error.message}`);}
    finally{favoriteControlPending.delete(deviceId);document.querySelectorAll(`[data-favorite-toggle="${CSS.escape(deviceId)}"]`).forEach(button=>{button.disabled=false;button.removeAttribute("aria-busy");});}
    return;
  }
  const remove=e.target.closest('[data-favorite-remove]');if(remove){workspace.prefs.favoriteDeviceIds=(workspace.prefs.favoriteDeviceIds||[]).filter(id=>id!==remove.dataset.favoriteRemove);saveDemoWorkspace();render();return;}
  if(e.target.closest('#home-favorite-plus')){if(!sessionInfo().authenticated){showFeatureNotice("Inicia sessão para gerir os teus favoritos.");return;}openFavoriteDialog();return;}
  const levelOpen=e.target.closest('[data-favorite-level-open]');if(levelOpen){if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode controlar dispositivos.");return;}const slider=$(`[data-favorite-level="${CSS.escape(levelOpen.dataset.favoriteLevelOpen)}"]`);if(slider){slider.hidden=false;slider.focus();}return;}
  if(e.target.closest('#home-existing-device')){$('#home-favorite-existing').hidden=false;$('#home-favorite-new').hidden=true;return;}
  if(e.target.closest('#home-new-device')){$('#home-favorite-new').hidden=false;$('#home-favorite-existing').hidden=true;return;}
  if(e.target.closest('#home-add-existing')){const id=$('#home-favorite-select').value;if(!id){$('#home-device-dialog-status').textContent="Escolhe um dispositivo.";return;}const details=favoriteMeta(),isShelly=(state.shellyDevices||[]).some(device=>device.device_id===id);details[id]={...(details[id]||{}),kind:isShelly?"shelly":details[id]?.kind,room:$('#home-favorite-room').value.trim(),floor:$('#home-favorite-floor').value.trim()};saveFavoriteMeta(details);addHomeFavoriteId(id);saveDemoWorkspace();e.target.closest('dialog')?.close();render();return;}
  if(e.target.closest('#home-register-device')){
    if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode registar ou configurar dispositivos no Gateway.");return;}
    const status=$('#home-device-dialog-status'),id=$('#home-new-id').value.trim(),name=$('#home-new-name').value.trim(),localIp=$('#home-new-ip').value.trim(),localMac=$('#home-new-mac').value.trim().toUpperCase(),kind=$('#home-new-kind').value,switchCode=$('#home-new-switch-code').value.trim(),levelCode=$('#home-new-level-code').value.trim();
    if(!id||!name){status.textContent="Indica o ID e o nome do equipamento. O esquema DPS é consultado na sincronização Tuya quando disponível.";return;}
    if(!localIp||!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(localIp)||!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(localMac)){status.textContent="Indica o IP local e o MAC do dispositivo para testar apenas a ligação LAN.";return;}
    if((kind==="dimmer"||kind==="blind")&&!levelCode){status.textContent="Para dimmer ou estore, indica o código Tuya do nível/posição.";return;}
    const min=Number($('#home-new-level-min').value),max=Number($('#home-new-level-max').value);if(levelCode&&(!Number.isInteger(min)||!Number.isInteger(max)||min<0||max<=min)){status.textContent="O intervalo Tuya mínimo e máximo é inválido.";return;}
    status.textContent="A guardar a configuração no Gateway…";
    try{const config=await readGatewayHardwareIntegrationConfig(),previous=(config.tuya?.devices||[]).find(item=>item.device_id===id)||{},device={...previous,device_id:id,name,device_kind_override:kind,local_ip:localIp,local_mac:localMac,...(switchCode?{switch_code:switchCode}:{}),...(levelCode?{level_code:levelCode,level_min:min,level_max:max}:{})},devices=[...(config.tuya?.devices||[]).filter(item=>item.device_id!==id),device];const saved=await saveGatewayHardwareIntegrationConfig({tuya:{region:config.tuya?.region||"eu_central",client_id:config.tuya?.client_id||undefined,devices}});let schemaInfo={queried:false,found:Boolean(previous.functions?.length||previous.status_spec?.length)};try{schemaInfo=await refreshTuyaSchemaIfNeeded(id,saved);}catch(error){schemaInfo={queried:true,found:false,error};}const {reading,result}=await testTuyaLanReachability(id);if(!schemaInfo.queried)state.tuyaDevices=normalizeTuyaInventory(saved.tuya?.devices||devices);state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==id),reading];const details=favoriteMeta();details[id]={label:name,kind,room:$('#home-new-room').value.trim(),floor:$('#home-new-floor').value.trim()};saveFavoriteMeta(details);addHomeFavoriteId(id);saveDemoWorkspace();status.textContent=result.connection_state==="lan_reachable"?`Guardado. Resposta LAN em ${Number(result.latency_ms).toLocaleString("pt-PT")} ms. ${schemaInfo.queried?(schemaInfo.found?"Esquema DPS e funções atualizado a partir da Tuya.":"A Tuya não devolveu o esquema DPS deste equipamento."):"Esquema DPS existente mantido."}`:result.connection_state==="lan_host_responded"?"Guardado. O IP respondeu na LAN, mas a porta do equipamento está fechada.":`Guardado, mas sem resposta LAN: ${tuyaLanReasonText(result.reason||"tuya_connection_failed")}`;}catch(error){status.textContent=`Falha ao guardar ou testar a ligação LAN: ${error.message}`;}return;
  }
});
const favoriteLevelTimers=new Map();
$('#page-content').addEventListener('input',e=>{const slider=e.target.closest('[data-favorite-level]');if(!slider)return;const id=slider.dataset.favoriteLevel;clearTimeout(favoriteLevelTimers.get(id));favoriteLevelTimers.set(id,setTimeout(async()=>{slider.hidden=true;if(sessionInfo().user?.role!=="owner")return;slider.disabled=true;const status=$(`[data-favorite-status="${CSS.escape(id)}"]`);if(status)status.textContent=`A enviar nível ${slider.value}%…`;try{const started=performance.now(),result=await sendGatewayTuyaLevel(id,Number(slider.value)),sentMs=Math.round(performance.now()-started);if(status)status.textContent=`Comando ${result.command_accepted?"aceite":"não confirmado"} · envio ${sentMs} ms; a confirmar pela LAN.`;}catch(error){if(status)status.textContent=`Falha no comando: ${error.message}`;}finally{slider.disabled=false;}},150));});

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
  if(e.target.id === "area-battery-bank-form") { e.preventDefault(); $("#area-battery-bank-save")?.click(); return; }
  if(e.target.id === "gateway-auto-rule-form") { e.preventDefault(); void saveUserAutomationForm(e.target); return; }
  if(e.target.id === "auto-form") { e.preventDefault(); if(saveAutomationForm(e.target,workspace)){automationEditingId="";render();showFeatureNotice("Automatismo guardado na demonstração local. Nenhum comando foi enviado.");} return; }
  if(e.target.id === "demo-user-form") { e.preventDefault(); if(addDemoUser(e.target)){render();showFeatureNotice("Utilizador fictício adicionado. Não foi criada uma conta real.");} return; }
  const userEdit=e.target.closest('form[data-demo-user-edit]');if(userEdit){e.preventDefault();if(saveDemoUserEdit(userEdit,userEdit.dataset.demoUserEdit)){render();showFeatureNotice('Utilizador fictício atualizado localmente.');}return;}
});
async function savePvStringForm(form){
  const status=$("#pv-string-status"),button=form.querySelector('[type="submit"]');
  if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){const message="Só o Owner pode alterar as strings.";status.textContent=message;window.alert(message);return;}
  const name=form.elements.name.value.trim(),manufacturer=form.elements.manufacturer.value.trim(),panelCount=Number(form.elements.panel_count.value),panelPower=Number(form.elements.panel_power_w.value),mppt=Number(form.elements.mppt.value),nominal=panelCount*panelPower/1000,id=form.elements.id.value||`pv-string-${Date.now().toString(36)}`;
  if(!name||name.length>120||!manufacturer||manufacturer.length>120||![1,2].includes(mppt)||!Number.isInteger(panelCount)||panelCount<1||panelCount>2000||!Number.isFinite(panelPower)||panelPower<1||panelPower>2500||!Number.isFinite(nominal)||nominal>1000){const message="Confirma o nome, fabricante, número de painéis, potência por painel e entrada MPPT.";status.textContent=message;window.alert(message);return;}
  const returnPage=form.closest("dialog").dataset.returnPage||state.page,scrollBeforeSave=window.scrollY;
  button.disabled=true;status.textContent="A guardar no Gateway…";
  try{
    // Build on the authoritative Gateway copy, not a possibly stale PWA cache.
    const current=await readGatewayEnergyEngineConfig();
    const strings=Array.isArray(current?.pv_strings)?[...current.pv_strings]:[];
    const index=strings.findIndex(item=>item.id===id);
    if(form.closest("dialog").dataset.mode==="edit"&&index<0)throw new Error("A string já não consta na configuração atual do Gateway. Atualiza a página e tenta novamente.");
    const value={id,name,manufacturer,panel_count:panelCount,panel_power_w:panelPower,mppt,nominal_power_kw:nominal,active:form.elements.active.checked};
    if(index>=0)strings[index]=value;else strings.push(value);
    await saveGatewayEnergyEngineConfig({pv_strings:strings});
    const saved=await readGatewayEnergyEngineConfig();
    const savedStrings=Array.isArray(saved?.pv_strings)?saved.pv_strings:null;
    const persisted=savedStrings?.find(item=>item.id===id);
    if(!persisted||persisted.name!==name||persisted.mppt!==mppt||persisted.panel_count!==panelCount||Number(persisted.panel_power_w)!==panelPower){
      throw new Error("O Gateway não confirmou a gravação desta string. Mantive o formulário aberto.");
    }
    state.energyEngine={...(state.energyEngine||{}),configuration:saved};
    form.closest("dialog").close();
    // Update the same page in place; never route to Home after this popup action.
    state.page=returnPage;
    render();window.scrollTo({top:scrollBeforeSave,behavior:"auto"});
    window.alert(`String “${name}” guardada no Gateway.`);
    await refreshGatewayReadings();
  }
  catch(error){const message=`Não foi possível guardar a string “${name}”: ${error.message}`;status.textContent=message;window.alert(message);}
  finally{button.disabled=false;}
}
async function saveAqsForm(form){
  const status=$("#aqs-status"),button=form.querySelector('[type="submit"]');
  if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode alterar a configuração AQS.";return;}
  const name=form.elements.name.value.trim(),manufacturer=form.elements.manufacturer.value.trim(),volume=Number(form.elements.volume_l.value),rated=Number(form.elements.rated_power_w.value),id=form.elements.id.value||`aqs-${Date.now().toString(36)}`;
  if(!name||!manufacturer||name.length>120||manufacturer.length>120||!Number.isInteger(volume)||volume<1||volume>100000||!Number.isInteger(rated)||rated<1||rated>100000){status.textContent="Indica nome, fabricante, volume em litros e potência nominal válidos.";return;}
  const binding=form.elements.tuya_binding.value;let deviceId=null,switchCode=null;
  if(binding){[deviceId,switchCode]=binding.split("|");const device=state.tuyaDevices.find(item=>item.device_id===deviceId),channel=device?.functions?.find(item=>item.code===switchCode);if(!channel||! ["bool","boolean"].includes(String(channel.type||"").toLowerCase())){status.textContent="O canal Tuya selecionado já não está disponível; atualiza os dispositivos e escolhe-o novamente.";return;}}
  const loads=[...(state.energyEngine?.configuration?.loads||[])],index=loads.findIndex(item=>item.id===id);
  if(form.closest("dialog").dataset.mode==="edit"&&index<0){status.textContent="Esta AQS já não consta na configuração. Atualiza e tenta novamente.";return;}
  const previous=index>=0?loads[index]:{},meterDevice=deviceId?state.tuyaDevices.find(item=>item.device_id===deviceId):null;const value={...previous,id,name,manufacturer,volume_l:volume,kind:"water_heater",control_type:deviceId?"tuya_breaker":"manual",rated_power_w:rated,minimum_power_w:0,maximum_power_w:rated,priority:previous.priority||10,enabled:previous.enabled!==false,automatic:previous.automatic===true,tuya_device_id:deviceId,tuya_switch_code:switchCode,tuya_measurement_codes:meterDevice?tuyaMeasurementCodes(meterDevice):{}};
  if(index>=0)loads[index]=value;else loads.push(value);
  const returnPage=form.closest("dialog").dataset.returnPage||state.page,scrollBeforeSave=window.scrollY;
  button.disabled=true;status.textContent="A guardar no Gateway…";
  try{
    await saveGatewayEnergyEngineConfig({loads});
    const saved=await readGatewayEnergyEngineConfig(),savedLoads=Array.isArray(saved?.loads)?saved.loads:null;
    const persisted=savedLoads?.find(item=>item.id===id);
    if(!persisted||persisted.name!==name||persisted.manufacturer!==manufacturer||persisted.volume_l!==volume||persisted.rated_power_w!==rated||persisted.tuya_device_id!==(deviceId||null)||persisted.tuya_switch_code!==(switchCode||null)){
      throw new Error("O Gateway não confirmou a gravação desta AQS. Mantive o formulário aberto.");
    }
    state.energyEngine={...(state.energyEngine||{}),configuration:saved};
    form.closest("dialog").close();
    state.page=returnPage;
    render();window.scrollTo({top:scrollBeforeSave,behavior:"auto"});
    showFeatureNotice(`AQS “${name}” guardada no Gateway.`);
    await refreshGatewayReadings();
  }
  catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
  finally{button.disabled=false;}
}
function showFeatureNotice(message){const n=$("#notice");n.hidden=false;n.textContent=message;setTimeout(()=>n.hidden=true,4500);}
$("#page-content").addEventListener("change", e => {
  const shellyBrightness=e.target.closest("[data-shelly-brightness]");
  if(shellyBrightness){
    const box=shellyBrightness.closest("[data-shelly-light-controls]"),deviceId=box?.dataset.shellyLightControls,device=state.shellyDevices.find(item=>item.device_id===deviceId);
    if(device&&box){
      const channel=Number(box.dataset.shellyChannel)||0,component=box.dataset.shellyComponent,brightness=Number(shellyBrightness.value),key=`${deviceId}:${component}:${channel}`;
      const label=$(`[data-shelly-status="${CSS.escape(deviceId)}"]`);
      const prior=shellyBrightnessTimers.get(key);if(prior)clearTimeout(prior);
      // A release/change event fires when the user stops dragging. Wait one
      // second so the command is sent once, after the final selected value.
      shellyBrightnessTimers.set(key,setTimeout(()=>{
        shellyBrightnessTimers.delete(key);
        if(label)label.textContent="A enviar brilho pela LAN…";
        controlGatewayShellyLight(deviceId,component,channel,{brightness}).then(result=>{
          if(label)label.textContent=result.command_confirmed?"Brilho confirmado pela leitura LAN.":"Ordem enviada; a leitura LAN ainda não confirmou o brilho.";
          else showFeatureNotice(result.command_confirmed?`Brilho ${brightness}% confirmado pela lâmpada.`:`Ordem de brilho ${brightness}% enviada; a lâmpada ainda não a confirmou.`);
          void refreshShellyInventoryStatus({quiet:true});
        }).catch(error=>{if(label)label.textContent=`Falha no brilho: ${error.message}`;else showFeatureNotice(`Não foi possível enviar o brilho: ${error.message}`);});
      },1000));
    }
    return;
  }
  if(e.target.closest("#gateway-auto-rule-form"))updateUserAutomationFormVisibility($("#gateway-auto-rule-form"));
  if(e.target.matches('#pv-string-form [name="panel_count"], #pv-string-form [name="panel_power_w"]'))updatePvStringTotalPower(e.target.form);
  if(e.target.matches('#pv-string-form input, #pv-string-form select'))updatePvStringSaveButton(e.target.form);
  if(e.target.matches('#aqs-form input, #aqs-form select'))updateAqsSaveButton(e.target.form);
  const fontPref=e.target.closest('[data-ws-field="prefs.font"]');if(fontPref){document.documentElement.dataset.font=fontPref.value;applyLiveFontScale();return;}
  const toggle=e.target.closest("[data-rule-toggle]"); if(toggle){const r=demoFeatures.automations.find(x=>x.id===toggle.dataset.ruleToggle);if(r){r.enabled=toggle.checked;localStorage.setItem('solar-miner-v053-demo-features-v1',JSON.stringify(demoFeatures));render();showFeatureNotice(r.enabled?'Automatismo ativado apenas na demonstração.':'Automatismo desativado.');}return;}
  if(e.target.id==='solar-weather'){saveSolarWeather(e.target.value);if($('#production-dialog')?.open)openProductionDialog();else render();}
  if(['conditionDevice','sourceType','targetDevice'].includes(e.target.name)){const form=e.target.closest('#auto-form');if(form){const ds=workspace.house.floors.flatMap(f=>f.rooms.flatMap(r=>r.devices));const device=ds.find(d=>d.id===form.elements.conditionDevice.value);const type=form.elements.sourceType.value;const opts=type==='device'?(device?.type==='blind'?[['open','Fica aberto'],['closed','Fica fechado']]:device?.type==='sensor'&&/temp/i.test(device?.name||'')?[['temperature','Temperatura acima/abaixo de limite']]:device?.type==='sensor'?[['motion','Deteta movimento'],['no-motion','Não deteta movimento']]:['light','socket'].includes(device?.type)?[['on','Fica ligado'],['off','Fica desligado']]:[['online','Estado online (se suportado)']]):type==='schedule'?[['time','Hora fixa'],['sunrise','Nascer do Sol'],['sunset','Pôr do Sol']]:type==='weather'?[['temperature','Temperatura exterior'],['rain','Chuva'],['cloud','Nebulosidade']]:[['arrive','Chegar a casa'],['leave','Sair de casa'],['nobody','Ninguém em casa']];if(e.target.name!=='targetDevice')form.elements.conditionType.innerHTML=opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');if(e.target.name==='targetDevice'){const target=ds.find(d=>d.id===form.elements.targetDevice.value);const t=(target?.type||'').toLowerCase(),n=(target?.name||'').toLowerCase();let actions=[['notify','Notificação local simulada']];if(t.includes('blind')||/estore/.test(n))actions=[['open','Abrir (simulado)'],['close','Fechar (simulado)'],...actions];else if(['light','socket','switch','plug'].some(x=>t.includes(x))||/luz|tomada/.test(n))actions=[['on','Ligar (simulado)'],['off','Desligar (simulado)'],...actions];form.elements.action.innerHTML=actions.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');}}}
});
$("#page-content").addEventListener("input", e => {
  const automationRange=e.target.closest("[data-automation-range]");if(automationRange){if(userAutomationConditionDraft)userAutomationConditionDraft.value=Number(automationRange.value);const output=automationRange.parentElement.querySelector("[data-preview-range-value]");if(output)output.textContent=automationRange.value;return;}
  const shellyBrightness=e.target.closest("[data-shelly-brightness]");if(shellyBrightness){shellyBrightness.closest(".shelly-slider-track")?.style.setProperty("--brightness-level",`${shellyBrightness.value}%`);const value=shellyBrightness.closest(".shelly-brightness-control")?.querySelector("[data-shelly-brightness-value]");if(value)value.textContent=`${shellyBrightness.value}%`;}
  if(e.target.matches('#pv-string-form [name="panel_count"], #pv-string-form [name="panel_power_w"]'))updatePvStringTotalPower(e.target.form);
  if(e.target.matches('#pv-string-form input, #pv-string-form select'))updatePvStringSaveButton(e.target.form);
  if(e.target.matches('#aqs-form input, #aqs-form select'))updateAqsSaveButton(e.target.form);
});
$("#page-content").addEventListener("click", async e => {
  const engineTab=e.target.closest("[data-engine-tab]");
  if(engineTab){
    energyEngineActiveTab=engineTab.dataset.engineTab;
    $("#page-content").querySelectorAll("[data-engine-tab-panel]").forEach(panel=>{panel.hidden=panel.dataset.engineTabPanel!==energyEngineActiveTab;});
    $("#page-content").querySelectorAll("[data-engine-tab]").forEach(tab=>{const selected=tab.dataset.engineTab===energyEngineActiveTab;tab.setAttribute("aria-selected",String(selected));tab.classList.toggle("selected",selected);});
    return;
  }
  const surplusTab=e.target.closest("[data-surplus-tab]");
  if(surplusTab){
    surplusActiveTab=surplusTab.dataset.surplusTab;
    $("#page-content").querySelectorAll("[data-surplus-panel]").forEach(panel=>{panel.hidden=panel.dataset.surplusPanel!==surplusActiveTab;});
    $("#page-content").querySelectorAll("[data-surplus-tab]").forEach(tab=>{const selected=tab.dataset.surplusTab===surplusActiveTab;tab.setAttribute("aria-selected",String(selected));tab.classList.toggle("selected",selected);});
    return;
  }
  if(e.target.closest("#surplus-save-priorities")){
    const button=e.target.closest("#surplus-save-priorities"),status=$("#surplus-priority-status");
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){if(status)status.textContent="Só o Owner pode alterar prioridades.";return;}
    const priorityFields=[...document.querySelectorAll("[data-load-priority]")],priorities=new Map();
    for(const field of priorityFields){const value=Number(field.value);if(!Number.isInteger(value)||value<1||value>100){if(status)status.textContent="Cada prioridade tem de ser um número inteiro entre 1 e 100.";field.focus();return;}priorities.set(field.dataset.loadPriority,value);}
    button.disabled=true;if(status)status.textContent="A guardar prioridades no Gateway…";
    try{
      const current=await readGatewayEnergyEngineConfig(),loads=Array.isArray(current?.loads)?current.loads.map(load=>priorities.has(load.id)?{...load,priority:priorities.get(load.id)}:load):[];
      if(!loads.length&&priorityFields.length)throw new Error("O Gateway não devolveu a lista atual de cargas.");
      const surplusManager={...(current?.surplus_manager||{}),priority_profile:$("#surplus-profile")?.value||"tesla_home"};
      await saveGatewayEnergyEngineConfig({loads,surplus_manager:surplusManager});
      const saved=await readGatewayEnergyEngineConfig(),savedById=new Map((saved?.loads||[]).map(load=>[load.id,load]));
      if([...priorities].some(([id,value])=>savedById.get(id)?.priority!==value)||saved?.surplus_manager?.priority_profile!==surplusManager.priority_profile)throw new Error("O Gateway não confirmou as prioridades escolhidas.");
      state.energyEngine={...(state.energyEngine||{}),configuration:saved};
      showFeatureNotice("Prioridades guardadas no Gateway.");
      await refreshGatewayReadings();
    }catch(error){if(status)status.textContent=`Não foi possível guardar: ${error.message}`;}
    finally{button.disabled=false;}
    return;
  }
  if(e.target.closest("#surplus-demo-run")){
    const potential=Number($("#surplus-demo-pv")?.value),house=Number($("#surplus-demo-house")?.value),soc=Number($("#surplus-demo-soc")?.value),profile=$("#surplus-demo-profile")?.value||"tesla_home",minimum=1000,reserve=70;
    state.surplusDemo={potential,house,battery:soc,profile};
    const result=$("#surplus-demo-result"),surplus=Math.max(0,potential-house);
    if(!Number.isFinite(potential)||!Number.isFinite(house)||!Number.isFinite(soc)){result.textContent="Introduz valores numéricos válidos.";return;}
    result.textContent=soc<reserve?`Simulação: aguardar; o SOC (${soc}%) está abaixo da reserva (${reserve}%).` : surplus<minimum?`Simulação: não ligar cargas; excedente potencial ${surplus} W, abaixo do mínimo de ${minimum} W.` : profile==="tesla_home"?`Simulação: prioridade Tesla/AQS/soalho; mineradora parada. Excedente indicativo ${surplus} W. A Tesla real não recebe ordem nesta demonstração.`:`Simulação: mineradora elegível até ${surplus} W indicativos; no Gateway, telemetria real e dispositivos configurados continuam a limitar o comando.`;
    return;
  }
  if(e.target.closest("#surplus-save")||e.target.closest("#surplus-resume")){
    const button=e.target.closest("#surplus-save,#surplus-resume"),status=$("#surplus-save-status"),cfg=state.energyEngine?.configuration||{},oldManager=cfg.surplus_manager||{},oldAutomation=cfg.automation||{};
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode guardar regras.";return;}
    const threshold=Number($("#surplus-minimum")?.value),reserve=Number($("#surplus-reserve")?.value),margin=Number($("#surplus-margin")?.value),resume=button.id==="surplus-resume";
    if(!Number.isInteger(threshold)||threshold<0||threshold>100000||!Number.isFinite(reserve)||reserve<0||reserve>100||!Number.isInteger(margin)||margin<0||margin>10000){status.textContent="Verifica o excedente mínimo, a reserva (0–100%) e a margem (0–10000 W).";return;}
    const manager={...oldManager,enabled:resume?true:$("#surplus-enabled").checked,manual_override:resume?false:Boolean(oldManager.manual_override),minimum_potential_surplus_w:threshold,battery_reserve_soc_percent:reserve,priority_profile:$("#surplus-profile")?.value||"tesla_home"};
    const automation={...oldAutomation,enabled:manager.enabled,commissioned:$("#surplus-commissioned")?.checked??Boolean(oldAutomation.commissioned),deye_map_verified:$("#surplus-map-verified")?.checked??Boolean(oldAutomation.deye_map_verified),surplus_margin_w:margin,decision_interval_seconds:Math.max(300,Number(oldAutomation.decision_interval_seconds)||300)};
    button.disabled=true;status.textContent="A guardar as regras no Gateway…";
    try{await saveGatewayEnergyEngineConfig({surplus_manager:manager,automation});status.textContent="Regras guardadas. Atualiza para ver o estado do motor.";await refreshGatewayReadings();}
    catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
    finally{button.disabled=false;}
    return;
  }
  const minerEquipment=e.target.closest("[data-miner-equipment-select]");if(minerEquipment){antminerActiveEquipmentId=minerEquipment.dataset.minerEquipmentSelect;antminerActiveSubmenu="state";render();return;}
  const minerSubmenu=e.target.closest("[data-miner-submenu]");if(minerSubmenu){antminerActiveSubmenu=minerSubmenu.dataset.minerSubmenu;document.querySelectorAll("[data-miner-submenu]").forEach(button=>{const active=button.dataset.minerSubmenu===antminerActiveSubmenu;button.setAttribute("aria-selected",String(active));button.classList.toggle("selected",active);});document.querySelectorAll("[data-miner-section]").forEach(section=>{section.hidden=section.dataset.minerSection!==antminerActiveSubmenu;});return;}
  const antminerStatus=$("#antminer-management-status"),antminerOutput=$("#antminer-management-output");
  const readAntminer=async (operations,{verifyControl=false}={})=>{if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){if(antminerStatus)antminerStatus.textContent="Inicia sessão Owner para consultar a Braiins OS.";return;}if(antminerStatus)antminerStatus.textContent="A consultar a Mineradora através do Gateway…";const results=await Promise.all(operations.map(async operation=>{try{return [operation,await readGatewayAntminerManagement(operation)];}catch(error){return [operation,{error:error.message}];}}));const snapshot=Object.fromEntries(results);if(operations.includes("advanced_settings")&&!snapshot.advanced_settings?.error){try{snapshot.advanced_settings={current:snapshot.advanced_settings?.data||snapshot.advanced_settings,schema:(await readGatewayAntminerManagement("advanced_schema"))?.data||null};}catch(error){snapshot.advanced_settings={current:snapshot.advanced_settings?.data||snapshot.advanced_settings,schema:null,schema_error:error.message};}}if(operations.includes("power_target")&&snapshot.power_target?.error){try{const tunerResult=snapshot.tuner||await readGatewayAntminerManagement("tuner"),tuner=tunerResult?.data||tunerResult,mode=tuner?.mode_state||tuner?.modeState,power=mode?.powertargetmodestate||mode?.power_target_mode_state||mode?.powerTargetModeState,target=power?.current_target||power?.currentTarget;if(target?.watt!=null)snapshot.power_target={operation:"power_target",state:"read",data:{watt:target.watt,source:"tuner"}};}catch{}}if(verifyControl){try{snapshot.control_test=await testGatewayAntminerControl();}catch(error){snapshot.control_test={error:error.message,order_sent:false};}}if(antminerOutput)antminerOutput.textContent=JSON.stringify(snapshot,null,2);const diagnosis=$("#antminer-management-diagnosis");if(diagnosis)diagnosis.textContent=summarizeAntminerState(snapshot);if(antminerStatus){const good=results.filter(([,value])=>!value.error).length,bad=results.length-good,control=snapshot.control_test;antminerStatus.textContent=`Braiins: ${good} secções respondidas${bad?`, ${bad} indisponíveis`:""}. ${verifyControl?(control?.error?`Teste de controlo não concluído: ${control.error}.`:control?.connection_state==="control_verified"?"Controlo confirmado sem alterar o alvo.":"Controlo respondeu, mas o alvo aplicado não coincidiu."):"Teste de controlo não executado."} Senhas e chaves são ocultadas.`;}if(operations.length===1){const operation=operations[0],data=snapshot[operation];showAntminerReadResult(operation,data,JSON.stringify(snapshot,null,2));}else if(verifyControl){const good=results.filter(([,value])=>!value.error).length,bad=results.length-good;openAntminerSectionDialog("Resumo da mineradora",`<div class="antminer-profile-summary"><article><small>Consultas respondidas</small><strong>${good}</strong></article><article><small>Indisponíveis</small><strong>${bad}</strong></article></div><p class="antminer-section-intro">${esc(diagnosis?.textContent||"")}</p><p>${snapshot.control_test?.error?`Teste de controlo não concluído: ${esc(snapshot.control_test.error)}.`:snapshot.control_test?.connection_state==="control_verified"?"O Gateway confirmou a ordem de controlo sem alterar o alvo.":"O teste de controlo não foi confirmado."}</p><p>Usa os cartões abaixo para abrir cada leitura em linguagem simples. Os dados completos ficam em “Dados técnicos (JSON)”.</p>`,JSON.stringify(snapshot,null,2));}};
  const readAll=e.target.closest("#antminer-refresh-management");if(readAll){await readAntminer(antminerReadOperations.map(([operation])=>operation),{verifyControl:true});await refreshGatewayReadings();return;}
  const readOne=e.target.closest("[data-antminer-read]");if(readOne){await readAntminer([readOne.dataset.antminerRead]);if(readOne.dataset.antminerRead==="tuner")await refreshGatewayReadings();return;}
  if(e.target.closest("#antminer-settings-save")){const dialog=$("#antminer-section-dialog"),fields=[...(dialog?.querySelectorAll("[data-antminer-setting]")||[])],changed={};for(const field of fields){let value;if(field.dataset.settingType==="boolean")value=field.value==="true";else if(field.dataset.settingType==="enum"){try{value=JSON.parse(field.value);}catch{value=field.value;}}else if(field.dataset.settingType==="integer")value=field.value===""?null:Number.parseInt(field.value,10);else if(field.dataset.settingType==="number")value=field.value===""?null:Number(field.value);else if(field.dataset.settingType==="object"||field.dataset.settingType==="array"){try{value=JSON.parse(field.value);}catch{openAntminerSectionDialog("Verificar definição",`<p>O campo “${esc(field.dataset.antminerSetting)}” tem de conter JSON válido.</p>`);return;}}else value=field.value;let original;try{original=JSON.parse(field.dataset.current||"null");}catch{original=null;}if(JSON.stringify(value)!==JSON.stringify(original))changed[field.dataset.antminerSetting]=value;}if(!Object.keys(changed).length){openAntminerSectionDialog("Sem alterações","<p>Não alteraste nenhum campo.</p>");return;}if(!await confirmAntminerAction("Guardar definições avançadas",`Enviar ${Object.keys(changed).length} alteração(ões) à mineradora?`))return;const success=await runAntminerAction("Definições avançadas","A guardar as opções alteradas e a aguardar a confirmação da Braiins OS.",async()=>{await writeGatewayAntminerManagement("advanced_settings",changed);return `A Braiins OS respondeu ao pedido. ${Object.keys(changed).length} opção(ões) enviadas.`;});if(success){dialog?.close();await readAntminer(["advanced_settings"]);}return;}
  if(e.target.closest("#antminer-section-apply-watt")){const input=$("#antminer-section-watt"),watt=Number(input?.value);if(!Number.isInteger(watt)||watt<1||watt>100000){openAntminerSectionDialog("Valor inválido","<p>Introduz um alvo de potência válido em watts.</p>");return;}if(!await confirmAntminerAction("Confirmar alvo de potência",`Enviar o alvo de ${watt} W à mineradora?`))return;const success=await runAntminerAction("Definir alvo de potência",`A enviar ${watt} W à Braiins OS.`,async()=>{const result=await writeGatewayAntminerManagement("set_power_target",{watt}),reported=antminerSetPowerResponseWatt(result);if(reported===null)return `A Braiins OS respondeu, mas não devolveu o alvo aplicado. O pedido foi ${watt} W; consulta o estado atual do tuner.`;if(reported!==watt)return `Pediste ${watt} W, mas a resposta da Braiins indica ${reported} W. O comando chegou; o valor aplicado foi limitado ou normalizado. Consulta os limites suportados e a configuração automática.`;return `A resposta da Braiins confirma ${reported} W. Vou consultar o estado atual do tuner para confirmar se permanece aplicado.`;});if(success)await readAntminer(["tuner"]);return;}
  const setWatt=e.target.closest("#antminer-management-set-watt");if(setWatt){const watt=Number($("#antminer-management-watt")?.value);if(!Number.isInteger(watt)||watt<1||watt>10000){if(antminerStatus)antminerStatus.textContent="O alvo deve estar entre 1 e 10000 W.";return;}if(!await confirmAntminerAction("Confirmar potência",`Enviar o alvo de ${watt} W à Mineradora?`))return;setWatt.disabled=true;await runAntminerAction("Definir potência",`A enviar o alvo de ${watt} W e a confirmar a resposta da Braiins OS.`,async()=>{const result=await writeGatewayAntminerManagement("set_power_target",{watt}),reported=antminerSetPowerResponseWatt(result);if(antminerOutput)antminerOutput.textContent=JSON.stringify(result,null,2);await readAntminer(["tuner","power_target","constraints","stats"]);if(reported===null)return `A Braiins respondeu, mas não devolveu o alvo aplicado. O pedido foi ${watt} W; consulta o estado atual do tuner.`;if(reported!==watt)return `Pediste ${watt} W, mas a resposta da Braiins indica ${reported} W aplicados. O valor foi limitado ou normalizado; consulta os limites suportados e a configuração automática.`;return `A resposta da Braiins confirma ${reported} W. A leitura seguinte confirma se o tuner mantém esse alvo.`;});if(antminerStatus)antminerStatus.textContent="Operação de potência concluída; resultado mostrado na janela.";setWatt.disabled=false;return;}
  const minerAction=e.target.closest("[data-antminer-write]");if(minerAction){const operation=minerAction.dataset.antminerWrite,label=minerAction.textContent.trim();if(!await confirmAntminerAction(`Confirmar ${label}`,`Enviar “${label}” à Mineradora? Esta operação pode alterar ou interromper a mineração.`))return;minerAction.disabled=true;const success=await runAntminerAction(`Mineradora · ${label}`,`A enviar o comando através do Gateway e a aguardar a resposta da Braiins OS.`,async()=>{const result=await writeGatewayAntminerManagement(operation);if(antminerOutput)antminerOutput.textContent=JSON.stringify(result,null,2);return `A API da Braiins OS respondeu ao comando “${label}”. A resposta não confirma, por si só, que a mineração esteja ativa.`;});if(antminerStatus)antminerStatus.textContent=success?`Resposta recebida para “${label}”.`:`A operação “${label}” falhou; consulta a janela de resultado.`;minerAction.disabled=false;if(success)await readAntminer(["details","errors","stats","tuner","pools"]);return;}
  const advancedSubmit=e.target.closest("#antminer-management-submit");if(advancedSubmit){if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){if(antminerStatus)antminerStatus.textContent="Inicia sessão Owner para alterar a Mineradora.";return;}const operation=$("#antminer-management-operation")?.value,raw=$("#antminer-management-payload")?.value.trim(),resourceId=$("#antminer-management-resource-id")?.value.trim()||undefined;let payload;if(raw){try{payload=JSON.parse(raw);}catch{if(antminerStatus)antminerStatus.textContent="O corpo JSON não é válido.";return;}}if(operation==="api_call"){const path=$("#antminer-management-path")?.value.trim(),method=$("#antminer-management-method")?.value,queryRaw=$("#antminer-management-query")?.value.trim();let query;if(!path){if(antminerStatus)antminerStatus.textContent="Indica o caminho API que consta no catálogo OpenAPI.";return;}if(queryRaw){try{query=JSON.parse(queryRaw);}catch{if(antminerStatus)antminerStatus.textContent="Os parâmetros de consulta não são JSON válido.";return;}}payload={method,path,...(raw?{body:payload}:{}),...(query?{query}:{})};}if(!await confirmAntminerAction(`Confirmar operação · ${operation}`,"Enviar esta alteração à Braiins OS? Operações de rede, pools e desempenho podem interromper a mineração ou bloquear o acesso remoto."))return;advancedSubmit.disabled=true;const success=await runAntminerAction(`Mineradora · ${operation}`,"A enviar a alteração através do Gateway e a aguardar resposta da Braiins OS.",async()=>{const result=await writeGatewayAntminerManagement(operation,payload,resourceId);if(antminerOutput)antminerOutput.textContent=JSON.stringify(result,null,2);return "Resposta recebida da Braiins OS. Atualiza a leitura correspondente para confirmar o estado efetivo.";});if(antminerStatus)antminerStatus.textContent=success?"Operação concluída; resposta apresentada na janela.":"Operação falhada; consulta a janela de resultado.";advancedSubmit.disabled=false;return;}
  if(e.target.closest("#engine-chart-open")){await loadEngineHistoryDay(localDayKey());return;}
  if(e.target.closest("[data-engine-history-close]")){e.target.closest("#engine-history-dialog")?.close();return;}
  const historyStep=e.target.closest("[data-engine-history-day]");
  if(historyStep){const d=localDayBounds(state.engineHistoryChart.dateKey||localDayKey()).start;d.setDate(d.getDate()+Number(historyStep.dataset.engineHistoryDay));await loadEngineHistoryDay(localDayKey(d));return;}
  if(e.target.closest("#engine-refresh")){refreshGatewayReadings();return;}
  if(e.target.closest("#gateway-area-refresh")){if(state.page==="automatismos"){void loadGatewayUserAutomations({quiet:true});return;}refreshGatewayReadings();return;}
  const automationOperator=e.target.closest("[data-automation-operator]");if(automationOperator){if(userAutomationConditionDraft)userAutomationConditionDraft.operator=automationOperator.dataset.automationOperator;render();return;}
  const automationMode=e.target.closest("[data-automation-mode]");if(automationMode){userAutomationConditionMode=automationMode.dataset.automationMode;userAutomationModeMenuOpen=false;render();return;}
  const automationCondition=e.target.closest("[data-automation-edit-condition]");if(automationCondition){const index=Number(automationCondition.dataset.automationEditCondition),condition=userAutomationPreviewConditions[index];if(condition){userAutomationConditionDraft={...condition};userAutomationPreviewConditions.splice(index,1);userAutomationMenuView=`status-value:${condition.deviceId}|${condition.code}`;render();}return;}
  const removePreviewAction=e.target.closest("[data-automation-remove-action]");if(removePreviewAction){userAutomationPreviewActions.splice(Number(removePreviewAction.dataset.automationRemoveAction),1);render();return;}
  const automationMenuAction=e.target.closest("[data-automation-menu]");if(automationMenuAction){const destination=automationMenuAction.dataset.automationMenu;if(destination==="list"){userAutomationMenuView="";userAutomationEditingId="";}else if(destination.startsWith("open:")){userAutomationMenuView=destination.slice(5)==="status"?"status-device":"tap";if(userAutomationMenuView==="status-device"){userAutomationStatusFilter="favorites";userAutomationConditionDraft=null;userAutomationPreviewConditions=[];userAutomationPreviewActions=[];userAutomationConditionMode="any";userAutomationModeMenuOpen=false;}}else if(destination.startsWith("status-filter:")){userAutomationStatusFilter=decodeURIComponent(destination.slice("status-filter:".length));}else if(destination.startsWith("device:")){const deviceId=destination.slice(7);userAutomationConditionDraft={deviceId};userAutomationMenuView=`status-functions:${deviceId}`;}else if(destination.startsWith("function:")){const key=destination.slice(9),separator=key.indexOf("|"),deviceId=key.slice(0,separator),code=key.slice(separator+1),device=tuyaDeviceWithPidMap((state.tuyaDevices||[]).find(item=>item.device_id===deviceId)),spec=(device?.status_spec||[]).find(item=>item.code===code)||{};let values=spec.values||{};if(typeof values==="string"){try{values=JSON.parse(values)}catch{values={}}}const range=values.range??spec.range??values.enum_range;userAutomationConditionDraft={deviceId,code,functionLabel:tuyaFriendlyCapabilityLabel({...spec,code},device),deviceName:device?.name||deviceId,unit:String(values.unit||spec.unit||""),operator:"lt",value:Array.isArray(range)&&range.length?range[0]:Number(values.min??0)};userAutomationMenuView=`status-value:${deviceId}|${code}`;}else if(destination.startsWith("status-enum:")){if(userAutomationConditionDraft)userAutomationConditionDraft.value=decodeURIComponent(destination.slice("status-enum:".length));}else if(destination==="status-next"){const draft=userAutomationConditionDraft;if(draft?.deviceId&&draft?.code&&draft.value!==undefined){const device=tuyaDeviceWithPidMap((state.tuyaDevices||[]).find(item=>item.device_id===draft.deviceId)),spec=(device?.status_spec||[]).find(item=>item.code===draft.code)||{},operator=draft.operator||"eq";userAutomationPreviewConditions.push({...draft,deviceName:device?.name||draft.deviceId,functionLabel:tuyaFriendlyCapabilityLabel({...spec,code:draft.code},device),operator,operatorLabel:({lt:"Menor que",eq:"Igual",gt:"Maior que"})[operator]||"Igual",unit:String(draft.unit||"")});userAutomationConditionDraft=null;userAutomationMenuView="status-conditions";}}else if(destination==="status-add"){userAutomationConditionDraft=null;userAutomationMenuView="status-device";}else if(destination==="status-mode-toggle"){userAutomationModeMenuOpen=!userAutomationModeMenuOpen;}else if(destination==="tap-actions"){userAutomationActionReturnView=userAutomationMenuView==="tap"?"tap":"status-conditions";userAutomationMenuView="tap-actions";}else if(destination.startsWith("action-select:")){const id=destination.slice("action-select:".length),catalog={device:["Controlar um dispositivo","Escolher dispositivo e definir a ação"],scene:["Selecionar / ativar automatismos","Escolher automatismos e ativar ou desativar"],delay:["Atrasar a ação","Definir o temporizador"],notification:["Enviar notificação","Configurar o aviso"],activation:["Alterar modo de ativação","Escolher o modo de ativação"]},[title,summary]=catalog[id]||["Ação",""] ;userAutomationPreviewActions.push({id,title,summary});userAutomationMenuView=userAutomationActionReturnView;}else userAutomationMenuView=destination;render();return;}
  const userAutoAction=e.target.closest("[data-user-auto]");if(userAutoAction){const action=userAutoAction.dataset.userAuto,id=userAutoAction.dataset.id,rule=(state.userAutomations.rules||[]).find(item=>item.id===id);if(action==="add-action"){const form=$("#gateway-auto-rule-form");if(form)appendUserAutomationActionRow(form);return;}if(action==="remove-action"){const row=userAutoAction.closest("[data-auto-action-row]"),list=row?.parentElement;if(row&&list?.children.length>1){row.remove();list.querySelectorAll('[data-user-auto="remove-action"]').forEach(button=>button.hidden=list.children.length<2);}return;}if(action==="cancel-edit"){userAutomationEditingId="";render();return;}if(action==="edit"&&rule){userAutomationEditingId=id;render();return;}if(action==="delete"&&rule){if(!window.confirm(`Eliminar o automatismo “${rule.name}”?`))return;try{await deleteGatewayUserAutomation(id);userAutomationEditingId="";await loadGatewayUserAutomations({quiet:true});}catch(error){showFeatureNotice(`Não foi possível eliminar: ${error.message}`);}return;}return;}
  const autoToggle=e.target.closest("[data-user-auto-toggle]");if(autoToggle){const rule=(state.userAutomations.rules||[]).find(item=>item.id===autoToggle.dataset.userAutoToggle);if(!rule)return;autoToggle.disabled=true;try{await updateGatewayUserAutomation(rule.id,{name:rule.name,enabled:autoToggle.checked,trigger:rule.trigger,actions:rule.actions||[rule.action]});await loadGatewayUserAutomations({quiet:true});}catch(error){autoToggle.checked=!autoToggle.checked;autoToggle.disabled=false;showFeatureNotice(`Não foi possível alterar o estado: ${error.message}`);}return;}
  if(e.target.closest("#gateway-auto-dry-run")){const form=$("#gateway-auto-rule-form");if(form)await dryRunUserAutomation(form);return;}
  if(e.target.closest("#pv-string-add")){openPvStringDialog();return;}
  if(e.target.closest("[data-pv-string-close]")){e.target.closest("#pv-string-dialog")?.close();return;}
  if(e.target.closest("#pv-string-remove")){
    const form=$("#pv-string-form"),status=$("#pv-string-status"),id=form.elements.id.value;if(!id||!window.confirm("Remover esta string da configuração do Gateway?"))return;
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode remover strings.";return;}
    const button=e.target.closest("#pv-string-remove");button.disabled=true;status.textContent="A remover a string…";
    try{const current=await readGatewayEnergyEngineConfig(),strings=Array.isArray(current?.pv_strings)?current.pv_strings:[];if(!strings.some(item=>item.id===id))throw new Error("A string já não consta na configuração atual do Gateway.");const remaining=strings.filter(item=>item.id!==id);const saved=await saveGatewayEnergyEngineConfig({pv_strings:remaining});if(!Array.isArray(saved?.pv_strings)||saved.pv_strings.some(item=>item.id===id))throw new Error("O Gateway não confirmou a remoção da string.");state.energyEngine={...(state.energyEngine||{}),configuration:saved};form.closest("dialog").close();await refreshGatewayReadings();}catch(error){status.textContent=`Não foi possível remover: ${error.message}`;}finally{button.disabled=false;}return;
  }
  if(e.target.closest("#aqs-add")){openAqsDialog();return;}
  if(e.target.closest("[data-aqs-close]")){e.target.closest("#aqs-dialog")?.close();return;}
  if(e.target.closest("#aqs-remove")){
    const form=$("#aqs-form"),status=$("#aqs-status"),id=form.elements.id.value;if(!id||!window.confirm("Remover esta AQS da configuração do Gateway?"))return;
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode remover AQS.";return;}
    const loads=(state.energyEngine?.configuration?.loads||[]).filter(item=>item.id!==id),button=e.target.closest("#aqs-remove");button.disabled=true;status.textContent="A remover a AQS…";
    try{await saveGatewayEnergyEngineConfig({loads});form.closest("dialog").close();await refreshGatewayReadings();}catch(error){status.textContent=`Não foi possível remover: ${error.message}`;}finally{button.disabled=false;}return;
  }
  if(e.target.closest("#area-battery-add-bank")){
    const banks=state.energyEngine?.configuration?.battery_banks||[];if(banks.length>=8){showFeatureNotice("O Gateway permite configurar até 8 bancos de bateria.");return;}openBatteryBankDialog();return;
  }
  if(e.target.closest("[data-battery-bank-close]")){e.target.closest("#area-battery-bank-dialog")?.close();return;}
  if(e.target.closest("#area-battery-bank-save")){
    const button=e.target.closest("#area-battery-bank-save"),dialog=$("#area-battery-bank-dialog"),status=$("#area-battery-bank-status");
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode alterar os bancos.";return;}
    const name=$("#area-battery-bank-name").value.trim(),capacity=Number($("#area-battery-bank-capacity").value),active=$("#area-battery-bank-active").checked,bankId=$("#area-battery-bank-id").value,config=state.energyEngine?.configuration||{};
    if(!name||name.length>120||!Number.isFinite(capacity)||capacity<0.1||capacity>10000){status.textContent="Indica um nome e uma capacidade entre 0,1 e 10 000 kWh.";return;}
    const banks=[...(config.battery_banks||[])],index=banks.findIndex(bank=>bank.id===bankId);
    if(dialog.dataset.mode==="edit"&&index<0){status.textContent="Este banco já não aparece na configuração atual. Atualiza a página e tenta de novo.";return;}
    const previous=index>=0?banks[index]:{};
    const bank={id:bankId||`bank-${Date.now().toString(36)}`,name,capacity_kwh:capacity,minimum_soc_percent:previous.minimum_soc_percent??config.minimum_soc_percent??20,maximum_soc_percent:previous.maximum_soc_percent??config.maximum_soc_percent??100,soc_source:previous.soc_source||"deye_aggregate",active};
    if(index>=0)banks[index]=bank;else banks.push(bank);
    button.disabled=true;status.textContent="A guardar no Gateway…";
    try{await saveGatewayEnergyEngineConfig({battery_banks:banks,...(banks.length?{}:{battery_capacity_kwh:null})});dialog.close();await refreshGatewayReadings();}
    catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
    finally{if($("#area-battery-bank-save"))$("#area-battery-bank-save").disabled=false;}
    return;
  }
  if(e.target.closest("#area-battery-bank-delete")){
    const dialog=$("#area-battery-bank-dialog"),status=$("#area-battery-bank-status"),bankId=$("#area-battery-bank-id").value;
    if(!bankId||!window.confirm("Remover este banco da configuração guardada no Gateway?"))return;
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode remover bancos.";return;}
    const banks=(state.energyEngine?.configuration?.battery_banks||[]).filter(bank=>bank.id!==bankId);
    const button=e.target.closest("#area-battery-bank-delete");button.disabled=true;status.textContent="A remover o banco do Gateway…";
    try{await saveGatewayEnergyEngineConfig({battery_banks:banks,...(banks.length?{}:{battery_capacity_kwh:null})});dialog.close();await refreshGatewayReadings();}
    catch(error){status.textContent=`Não foi possível remover: ${error.message}`;}
    finally{if($("#area-battery-bank-delete"))$("#area-battery-bank-delete").disabled=false;}
    return;
  }
  if(e.target.closest("#area-battery-save")){
    const button=e.target.closest("#area-battery-save"),status=$("#area-battery-status");
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode alterar a configuração da bateria.";return;}
    const capacity=Number($("#area-battery-capacity").value),minimum=Number($("#area-battery-minimum").value),maximum=Number($("#area-battery-maximum").value);
    try{
      if(!Number.isFinite(capacity)||capacity<0.1||capacity>10000||!Number.isFinite(minimum)||!Number.isFinite(maximum)||minimum<0||maximum>100||minimum>=maximum)throw new Error("Confirma capacidade agregada e SOC mínimo/máximo válidos.");
      button.disabled=true;status.textContent="A guardar no Gateway…";
      await saveGatewayEnergyEngineConfig({battery_capacity_kwh:capacity,minimum_soc_percent:minimum,maximum_soc_percent:maximum});
      status.textContent="Limites de descarga guardados no Gateway.";const details=$(".battery-limits-details");if(details)details.open=false;await refreshGatewayReadings();
    }catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
    finally{const current=$("#area-battery-save");if(current)current.disabled=false;}
    return;
  }
  const bindMinerBreaker=e.target.closest("[data-miner-breaker-save]");
  const editMiner=e.target.closest("[data-miner-load-save]");
  if(editMiner){
    const row=editMiner.closest("[data-miner-binding]"),loadId=editMiner.dataset.minerLoadSave;
    editMiner.disabled=true;state.energyConfigStatus="A guardar o nome e as características da mineradora no inventário…";const liveStatus=$("#engine-miner-breaker-status");if(liveStatus)liveStatus.textContent=state.energyConfigStatus;
    try{
      const name=row?.querySelector("[data-miner-load-name]")?.value.trim(),rated=Number(row?.querySelector("[data-miner-load-rated]")?.value),minimum=Number(row?.querySelector("[data-miner-load-minimum]")?.value),maximum=Number(row?.querySelector("[data-miner-load-maximum]")?.value),priority=Number(row?.querySelector("[data-miner-load-priority]")?.value),automatic=Boolean(row?.querySelector("[data-miner-load-automatic]")?.checked);
      if(!name||name.length>120||!Number.isInteger(rated)||rated<1||!Number.isInteger(minimum)||minimum<0||!Number.isInteger(maximum)||maximum<1||minimum>maximum||maximum>2900||!Number.isInteger(priority)||priority<1||priority>100)throw new Error("Confirma o nome, a potência, os limites e a prioridade.");
      const current=await readGatewayEnergyEngineConfig(),loads=Array.isArray(current?.loads)?[...current.loads]:[],load=loads.find(item=>item.id===loadId);
      if(!load||load.kind!=="miner"||load.control_type!=="antminer_braiins")throw new Error("Esta mineradora já não consta da configuração atual.");
      const identitySelect=row?.querySelector("[data-miner-load-identity]"),deviceKey=identitySelect?.value;
      if(identitySelect&&identitySelect.options.length>1&&!deviceKey)throw new Error("Seleciona o MAC correspondente à mineradora.");
      if(deviceKey)load.device_key=deviceKey;
      Object.assign(load,{name,rated_power_w:rated,minimum_power_w:minimum,maximum_power_w:maximum,priority,automatic});
      await saveGatewayEnergyEngineConfig({loads});
      const saved=await readGatewayEnergyEngineConfig(),persisted=saved?.loads?.find(item=>item.id===loadId);
      if(!persisted||persisted.name!==name||persisted.rated_power_w!==rated||persisted.minimum_power_w!==minimum||persisted.maximum_power_w!==maximum||persisted.priority!==priority||persisted.automatic!==automatic)throw new Error("O Gateway não confirmou todas as alterações.");
      state.energyEngine={...(state.energyEngine||{}),configuration:saved};state.energyConfigStatus=`${name}: nome e características guardados no dispositivo e no inventário.`;
      try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* Name remains persisted in the energy equipment record. */}
      const linked=saved?.loads?.find(item=>item.id===loadId),canonicalId=linked?.equipment_id;
      for(const item of state.equipment||[])if(item.category==="mineradoras"&&(!canonicalId||item.id===canonicalId))item.name=name;
      if(canonicalId){const minerTab=$(`[data-miner-equipment-select="${CSS.escape(canonicalId)}"]`);if(minerTab)minerTab.textContent=name;}
      if(linked?.device_key){const identity=state.gatewayDeviceInventory.find(item=>item.device_key===linked.device_key);if(identity)identity.name=name;}
      row?.querySelector("h3")?.replaceChildren(document.createTextNode(name));
      const areaTitle=$("#page-content .gateway-area-device .panel-header h2");if(areaTitle&&state.page==="mineradoras")areaTitle.textContent=name;
      const visibleStatus=$("#engine-miner-breaker-status");if(visibleStatus)visibleStatus.textContent=state.energyConfigStatus;
    }catch(error){state.energyConfigStatus=`Não foi possível guardar: ${error.message}`;const currentStatus=$("#engine-miner-breaker-status");if(currentStatus)currentStatus.textContent=state.energyConfigStatus;}
    finally{const currentButton=$(`[data-miner-load-save="${CSS.escape(loadId)}"]`);if(currentButton)currentButton.disabled=false;}
    return;
  }
  if(bindMinerBreaker){
    const status=$("#engine-miner-breaker-status"),row=bindMinerBreaker.closest("[data-miner-binding]"),loadId=bindMinerBreaker.dataset.minerBreakerSave;
    bindMinerBreaker.disabled=true;if(status)status.textContent="A guardar a associação no Gateway…";
    try{
      const current=await readGatewayEnergyEngineConfig(),loads=Array.isArray(current?.loads)?[...current.loads]:[],load=loads.find(item=>item.id===loadId),option=row?.querySelector("[data-miner-breaker-device]")?.selectedOptions?.[0],deviceId=option?.value,switchCode=option?.dataset.code;
      if(!load||load.kind!=="miner"||load.control_type!=="antminer_braiins")throw new Error("Esta mineradora já não está na configuração atual.");
      if(!deviceId||!switchCode)throw new Error("Escolhe um disjuntor Tuya com canal de controlo disponível.");
      const breaker=state.tuyaDevices.find(item=>item.device_id===deviceId);if(!breaker)throw new Error("Sincroniza novamente os dispositivos Tuya e tenta outra vez.");
      load.tuya_device_id=deviceId;load.tuya_switch_code=switchCode;load.tuya_measurement_codes=tuyaMeasurementCodes(breaker);delete load.requires_load_id;
      await saveGatewayEnergyEngineConfig({loads});
      const saved=await readGatewayEnergyEngineConfig(),persisted=saved?.loads?.find(item=>item.id===loadId);
      if(!persisted||persisted.tuya_device_id!==deviceId||persisted.tuya_switch_code!==switchCode)throw new Error("O Gateway não confirmou a associação. Atualiza e tenta novamente.");
      state.energyEngine={...(state.energyEngine||{}),configuration:saved};state.energyConfigStatus=`${load.name}: associação guardada. O Gateway usa as próximas leituras confirmadas do disjuntor.`;if(status)status.textContent=state.energyConfigStatus;
    }catch(error){if(status)status.textContent=`Não foi possível associar: ${error.message}`;}
    finally{bindMinerBreaker.disabled=false;}
    return;
  }
  if(e.target.closest("#engine-add-load")){
    const status=$("#engine-equipment-config-status")||$("#engine-miner-breaker-status");
    try{
      const current=await readGatewayEnergyEngineConfig(),loads=Array.isArray(current?.loads)?[...current.loads]:[];
      if(!Array.isArray(loads)||loads.length>=64)throw new Error("A lista tem de ser válida e pode conter até 64 cargas.");
      const kind=$("#engine-load-kind").value,control=$("#engine-load-control").value;
      const rated=Number($("#engine-load-rated").value),priority=Number($("#engine-load-priority").value);
      const name=$("#engine-load-name").value.trim();
      if(!name||!Number.isInteger(rated)||rated<1||!Number.isInteger(priority)||priority<1||priority>100)throw new Error("Indica nome, potência nominal e prioridade válidos.");
      const load={id:`load-${Date.now().toString(36)}`,name,kind,control_type:control,rated_power_w:rated,priority,enabled:true,automatic:$("#engine-load-automatic").checked};
      if(control==="tuya_smart"||control==="tuya_breaker"){
        const option=$("#engine-load-tuya-device").selectedOptions[0],device_id=option?.value,switch_code=option?.dataset.code;
        if(!device_id||!switch_code)throw new Error("Configura e seleciona um interruptor Tuya registado no Gateway.");
        load.tuya_device_id=device_id;load.tuya_switch_code=switch_code;const meterDevice=state.tuyaDevices.find(item=>item.device_id===device_id);load.tuya_measurement_codes=meterDevice?tuyaMeasurementCodes(meterDevice):{};
      }
      if(control==="antminer_braiins"){
        const minimum=Number($("#engine-load-minimum").value),maximum=Number($("#engine-load-maximum").value);
        if(!Number.isInteger(minimum)||!Number.isInteger(maximum)||minimum<1||maximum>2900||minimum>maximum)throw new Error("Define mínimo e máximo da mineradora entre 1 e 2900 W.");
        load.minimum_power_w=minimum;load.maximum_power_w=maximum;
        const option=$("#engine-load-tuya-device").selectedOptions[0],device_id=option?.value,switch_code=option?.dataset.code;
        if(device_id&&switch_code){
          const breaker=state.tuyaDevices.find(item=>item.device_id===device_id);
          load.tuya_device_id=device_id;load.tuya_switch_code=switch_code;load.tuya_measurement_codes=breaker?tuyaMeasurementCodes(breaker):{};
        }
      }
      await saveGatewayEnergyEngineConfig({loads:[...loads,load]});
      const saved=await readGatewayEnergyEngineConfig(),persisted=saved?.loads?.find(item=>item.id===load.id);
      if(!persisted||persisted.name!==name)throw new Error("O Gateway não confirmou que a carga ficou guardada.");
      state.energyEngine={...(state.energyEngine||{}),configuration:saved};state.energyConfigStatus=`${name} foi guardada no Gateway.`;
      status.textContent=`${name} foi guardada no Gateway. A carga está registada; associa o disjuntor separadamente.`;
      if(state.page==="mineradoras"){const host=$("#engine-miner-breaker");if(host)host.outerHTML=renderMinerBreakerAssociation();}
    }catch(error){status.textContent=error.message;}
    return;
  }
  if(e.target.closest("#engine-save-equipment-config")){
    const button=e.target.closest("#engine-save-equipment-config"), status=$("#engine-equipment-config-status");
    button.disabled=true;status.textContent="A validar e guardar no Gateway…";
    try{
      const banks=JSON.parse($("#engine-banks-json").value||"[]"),loads=JSON.parse($("#engine-loads-json").value||"[]");
      const margin=Number($("#engine-surplus-margin").value);
      if(!Array.isArray(banks)||!Array.isArray(loads)||!Number.isInteger(margin)||margin<0||margin>10000)throw new Error("Usa listas JSON válidas e margem entre 0 e 10000 W.");
      await saveGatewayEnergyEngineConfig({battery_banks:banks,loads,automation:{enabled:$("#engine-automation-enabled").checked,commissioned:$("#engine-commissioned").checked,deye_map_verified:$("#engine-deye-map-verified").checked,surplus_margin_w:margin,decision_interval_seconds:300}});
      status.textContent="Cargas e automatização guardadas no Gateway. O estado efetivo pode continuar bloqueado por segurança.";
      await refreshGatewayReadings();
    }catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
    finally{button.disabled=false;}
    return;
  }
  if(e.target.closest("#engine-save-config")){
    const button=e.target.closest("#engine-save-config"), capacityField=$("#engine-battery-capacity"), minimumField=$("#engine-minimum-soc"), maximumField=$("#engine-maximum-soc"), status=$("#engine-config-status");
    button.disabled=true; status.textContent="A guardar no Gateway…";
    const raw=capacityField.value.trim(), capacity=raw===""?null:Number(raw), minimum=Number(minimumField.value), maximum=Number(maximumField.value);
    if((capacity!==null&&(!Number.isFinite(capacity)||capacity<0.1||capacity>10000))||!Number.isFinite(minimum)||!Number.isFinite(maximum)||minimum<0||maximum>100||minimum>=maximum){status.textContent="Verifica a capacidade (0,1–10000 kWh) e os limites SOC (mínimo abaixo do máximo até 100%).";button.disabled=false;return;}
    saveGatewayEnergyEngineConfig({battery_capacity_kwh:capacity,minimum_soc_percent:minimum,maximum_soc_percent:maximum}).then(async()=>{status.textContent="Configuração guardada no Gateway.";await refreshGatewayReadings();}).catch(error=>{status.textContent=`Não foi possível guardar: ${error.message}`;}).finally(()=>{const current=$("#engine-save-config");if(current)current.disabled=false;});return;
  }
  if(e.target.closest("#engine-save-site-config")){
    const button=e.target.closest("#engine-save-site-config"),status=$("#engine-site-config-status");
    const capacityText=$("#engine-pv-capacity").value.trim(),capacity=capacityText===""?null:Number(capacityText);
    if(capacity!==null&&(!Number.isFinite(capacity)||capacity<0.1||capacity>1000)){status.textContent="Indica a potência FV entre 0,1 e 1000 kWp.";return;}
    button.disabled=true;status.textContent="A guardar configuração no Gateway…";
    saveGatewayEnergyEngineConfig({pv_capacity_kw:capacity}).then(async()=>{status.textContent="Potência FV guardada no Gateway.";await refreshGatewayReadings();}).catch(error=>{status.textContent=`Não foi possível guardar: ${error.message}`;}).finally(()=>{const current=$("#engine-save-site-config");if(current)current.disabled=false;});return;
  }
  const feature=e.target.closest('[data-feature-action]'); if(feature){const action=feature.dataset.featureAction,id=feature.dataset.id||'';if(action==='new-rule'){automationEditingId='';render();return;}if(action==='edit-rule'){automationEditingId=id;render();return;}if(action==='cancel-edit'){automationEditingId='';render();return;}if(action==='add-condition'){const box=$('#extra-conditions');if(box){const row=document.createElement('div');row.className='feature-extra-row';row.innerHTML='<label class="feature-field">Condição adicional<select name="extra"><option value="nobody">Não está ninguém em casa (simulado)</option><option value="weather">Temperatura exterior inferior a 12 °C (simulado)</option><option value="fresh">Dados atualizados (simulado)</option><option value="none">Sem condição adicional</option></select></label><button type="button" class="button secondary" data-feature-action="remove-condition">Remover</button>';box.appendChild(row);}return;}if(action==='remove-condition'){const row=feature.closest('.feature-extra-row');if(row&&$('#extra-conditions .feature-extra-row')?.parentElement?.children.length>1)row.remove();else if(row){const select=row.querySelector('select');if(select)select.value='none';}return;}const result=handleFeatureAction(action,id,workspace);if(result?.edit!==undefined){automationEditingId=result.edit;render();return;}if(result?.cancel){automationEditingId='';render();return;}if(result?.rerender)render();if(result?.message)showFeatureNotice(result.message);return;}
  const workspaceButton=e.target.closest("[data-ws-action]");
  if(workspaceButton){if(['open-room','open-device'].includes(workspaceButton.dataset.wsAction))workspace.house.returnScrollY=window.scrollY;const result=handleWorkspaceAction(workspaceButton.dataset.wsAction,workspaceButton);if(result?.edit)openContextEditor(result.edit.type,result.edit.id);if(result?.navigate)navigate(result.navigate);if(result?.message){const notice=$("#notice");notice.hidden=false;notice.textContent=result.message;setTimeout(()=>{notice.hidden=true;},3500);}if(result?.rerender)render();return;}
  if(e.target.closest("#open-weather")) $("#weather-dialog").showModal();
  if(e.target.closest("#open-production")) openProductionDialog();
  const toggle=e.target.closest("[data-fav-toggle]");
  if(toggle && state.mode==="SIMULATED") {const device=state.favoriteDevices.find(d=>d.id===toggle.dataset.favToggle);if(device){device.pct=device.pct>0?0:75;render();}}
});
$("#property-hero-host").addEventListener("click",e=>{if(e.target.closest("#hero-photo-settings")&&sessionInfo().user?.role==="owner")openContextEditor("house","house");});
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
$("#open-settings").addEventListener("click",()=>state.mode==="SIMULATED"?$("#settings-dialog").showModal():navigate("profile"));
$("#close-demo-settings").addEventListener("click",()=>$("#settings-dialog").close());
$("#refresh-button").addEventListener("click",()=>{if(sessionInfo().authenticated) refreshGatewayReadings(); else render();});
$("#page-content").addEventListener("input",e=>{
  const planZoom=e.target.closest("[data-site-plan-zoom]");if(planZoom){const zoom=Number(planZoom.value),plan=$("#page-content .gateway-house-plan"),out=$("#house-plan-zoom-value");if(plan)plan.style.setProperty("--plan-zoom",String(zoom));if(out)out.textContent=`${zoom.toFixed(1)}×`;return;}
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
$("#page-content").addEventListener("click",e=>{
  if(e.target.closest("#live-refresh")){refreshGatewayReadings();return;}
  if(e.target.closest("#open-owner-management")){$("#gateway-dialog").showModal();return;}
  const houseTab=e.target.closest("[data-house-tab]");
  const planEdit=e.target.closest("[data-house-plan-edit]");
  const houseGeneral=e.target.closest("[data-house-general]");
  const houseFloor=e.target.closest("[data-house-select-floor]");
  const houseRoom=e.target.closest("[data-house-select-room]");
  if(planEdit){houseView.planEditing=!houseView.planEditing;render();return;}
  if(houseGeneral){houseView.floorId=null;houseView.roomId=null;houseView.tab="overview";render();return;}
  if(houseView.planEditing&&houseRoom?.closest(".gateway-house-plan-tiles"))return;
  if(houseRoom){if(houseRoom.dataset.houseRoomFloor)houseView.floorId=houseRoom.dataset.houseRoomFloor;houseView.roomId=houseRoom.dataset.houseSelectRoom;houseView.tab="room";render();return;}
  if(houseFloor){houseView.floorId=houseFloor.dataset.houseSelectFloor;houseView.tab=houseFloor.dataset.houseView||houseFloor.dataset.houseTab||"overview";houseView.roomId=null;render();return;}
  if(houseTab){houseView.tab=houseTab.dataset.houseTab;houseView.roomId=null;render();return;}
  if(e.target.closest('[data-action="edit-house"]')){openContextEditor("house","house");return;}
  const siteAction=e.target.closest("[data-site-action]");if(siteAction){handleSiteStructureAction(siteAction).catch(error=>{const notice=$("#notice");notice.hidden=false;notice.textContent=`Não foi possível guardar a estrutura no Gateway: ${error.message}`;});return;}
  const btn=e.target.closest("[data-page]");if(btn)navigate(btn.dataset.page);
});
function finishHousePlanPointer(e){
  const session=housePlanPointer;if(!session||session.pointerId!==e.pointerId)return;
  housePlanPointer=null;session.tile.releasePointerCapture?.(e.pointerId);
  if(!session.moved)return;
  houseView.suppressRoomClickUntil=Date.now()+500;
  const rect={x:Number(session.tile.style.getPropertyValue("--room-x").replace("%","")),y:Number(session.tile.style.getPropertyValue("--room-y").replace("%","")),w:Number(session.tile.style.getPropertyValue("--room-w").replace("%","")),h:Number(session.tile.style.getPropertyValue("--room-h").replace("%",""))};
  const current=state.siteProfile||{name:"Solar Energy",floors:[]},floors=structuredClone(current.floors||[]),floor=floors.find(item=>item.id===houseView.floorId),room=floor?.rooms.find(item=>item.id===session.tile.dataset.houseSelectRoom);if(!room)return;
  room.plan_rect=rect;
  saveGatewaySiteProfile({...current,floors}).then(saved=>{state.siteProfile=saved;showFeatureNotice(`Disposição de ${room.name} guardada.`);}).catch(error=>showFeatureNotice(`Não foi possível guardar a disposição: ${error.message}`));
}
$("#page-content").addEventListener("pointerdown",e=>{
  const tile=e.target.closest(".gateway-house-plan-tiles.is-editing .gateway-house-room-tile");if(!tile||!houseView.planEditing)return;
  const board=tile.closest(".gateway-house-plan-tiles"),bounds=board.getBoundingClientRect(),read=(name)=>Number(tile.style.getPropertyValue(name).replace("%",""));
  housePlanPointer={tile,pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,bounds,start:{x:read("--room-x"),y:read("--room-y"),w:read("--room-w"),h:read("--room-h")},mode:e.target.closest(".gateway-house-room-resize")?"resize":"move",moved:false};
  tile.setPointerCapture?.(e.pointerId);e.preventDefault();
});
$("#page-content").addEventListener("pointermove",e=>{
  const s=housePlanPointer;if(!s||s.pointerId!==e.pointerId)return;const dx=(e.clientX-s.startX)/s.bounds.width*100,dy=(e.clientY-s.startY)/s.bounds.height*100;if(Math.abs(dx)+Math.abs(dy)>0.6)s.moved=true;
  const min=14;let {x,y,w,h}=s.start;if(s.mode==="resize"){w=Math.max(min,Math.min(100-x,s.start.w+dx));h=Math.max(min,Math.min(100-y,s.start.h+dy));}else{x=Math.max(0,Math.min(100-w,s.start.x+dx));y=Math.max(0,Math.min(100-h,s.start.y+dy));}
  s.tile.style.setProperty("--room-x",`${x}%`);s.tile.style.setProperty("--room-y",`${y}%`);s.tile.style.setProperty("--room-w",`${w}%`);s.tile.style.setProperty("--room-h",`${h}%`);
});
$("#page-content").addEventListener("pointerup",finishHousePlanPointer);
$("#page-content").addEventListener("pointercancel",finishHousePlanPointer);
$("#page-content").addEventListener("change",e=>handleWorkspaceChange(e));
$("#page-content").addEventListener("change",async e=>{
  const photoInput=e.target.closest("[data-house-photo-input]");
  if(photoInput){
    const file=photoInput.files?.[0], kind=photoInput.dataset.photoKind, floorId=photoInput.dataset.floorId, roomId=photoInput.dataset.roomId;
    photoInput.value="";if(!file||sessionInfo().user?.role!=="owner")return;
    try{const readable=await makeBrowserReadablePhoto(file),photo=await readAndCompressImage(readable),saved=await saveGatewaySitePhoto({kind,floorId,roomId,photoDataUrl:photo}),floor=saved.floors?.find(item=>item.id===floorId);if(!floor)throw new Error("O Gateway não confirmou o piso atualizado.");if(kind==="plan")floor.plan_data_url=photo;else if(kind==="room"){const room=floor.rooms?.find(item=>item.id===roomId);if(!room)throw new Error("O Gateway não confirmou a divisão atualizada.");room.photo_data_url=photo;}else floor.photo_data_url=photo;state.siteProfile=saved;render();showFeatureNotice(kind==="plan"?"Planta guardada no Gateway.":kind==="room"?"Fotografia da divisão guardada no Gateway.":"Fotografia do piso guardada no Gateway.");}
    catch(error){showFeatureNotice(`Não foi possível guardar a imagem: ${error.message}`);}return;
  }
  const zoom=e.target.closest("[data-site-plan-zoom]");if(zoom){const current=state.siteProfile||{floors:[]},floors=structuredClone(current.floors||[]),floor=floors.find(item=>item.id===zoom.dataset.sitePlanZoom);if(!floor)return;floor.plan_zoom=Number(zoom.value);const out=$("#house-plan-zoom-value");if(out)out.textContent=`${Number(zoom.value).toFixed(1)}×`;try{state.siteProfile=await saveGatewaySiteProfile({...current,floors});}catch(error){showFeatureNotice(`Não foi possível guardar o tamanho da planta: ${error.message}`);}return;}
});
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
    let endpoint=primary, result=null, lastEndpointKind="Other";
    for(const candidate of candidates){
      gatewayResult(candidate===primary.origin?"A verificar /api/v1/health e /api/v1/info…":"Endpoint LAN indisponível; a tentar o endereço Tailscale…");
      result=await gatewayManager.check(candidate);
      const endpointKind = candidate === location.origin && location.hostname.endsWith("github.io") ? "Hosted"
        : new URL(candidate).hostname.toLowerCase().endsWith(".ts.net") ? "Tailscale"
          : classifyEndpoint(candidate) === "CANDIDATE_LAN" ? "LAN" : "Other";
      lastEndpointKind=endpointKind;
      storeGatewayProbeDiagnostics(endpointKind, result);
      if(result.reachable){endpoint=validateGatewayUrl(candidate);break;}
    }
    field.value=endpoint.origin;
    try { localStorage.setItem("solarminer-gateway-endpoint-v1", endpoint.origin); } catch {}
    if(result.reachable) {
      let bootstrapStartedAt = Date.now();
      try {
        bootstrapStartedAt = Date.now();
        const bootstrap = await readGatewayBootstrapStatus(endpoint.origin);
        storeGatewayProbeDiagnostics(lastEndpointKind, { probeSteps: [{ occurred_at: new Date().toISOString(),
          route: "/api/v1/bootstrap/status", outcome: "success", http_status: 200,
          latency_ms: Date.now() - bootstrapStartedAt }] });
        if (["BOOTSTRAP_PENDING", "OWNER_SETUP_REQUIRED"].includes(bootstrap.state)) {
          gatewayResult("Gateway pronto para o primeiro Owner. Abre-se a configuração inicial.");
          if (!$("#gateway-bootstrap-dialog").open) $("#gateway-bootstrap-dialog").showModal();
        } else {
          try {
            const login = await loginGateway({ gatewayUrl: endpoint.origin });
            $("#gateway-password-login-form").hidden = true;
            gatewayResult(`Ligação autenticada neste dispositivo como ${login.user.username} (${login.user.role}).`);
            markGatewayAuthenticated(); updateSessionUi(); await submitPendingGatewayProbeDiagnostics(); await refreshGatewayReadings();
          } catch (loginError) {
            $("#gateway-password-login-form").hidden = false;
            gatewayResult(`${result.state}. ${loginError.message} Introduz as credenciais de uma conta ativa para registar este browser.`);
          }
        }
      } catch (statusError) {
        storeGatewayProbeDiagnostics(lastEndpointKind, { probeSteps: [{ occurred_at: new Date().toISOString(),
          route: "/api/v1/bootstrap/status", outcome: statusError?.name === "AbortError" ? "timeout"
            : statusError?.name === "TypeError" ? "browser_network_error" : "request_error",
          error_name: ["AbortError", "TypeError"].includes(statusError?.name) ? statusError.name : "Error",
          latency_ms: Date.now() - bootstrapStartedAt }] });
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
    markGatewayAuthenticated(); updateSessionUi(); await submitPendingGatewayProbeDiagnostics(); await refreshGatewayReadings();
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
  const savedEndpoint=localStorage.getItem("solarminer-gateway-endpoint-v1")||gatewayHostedOrigin;
  if (savedEndpoint) {
    setTimeout(() => $("#gateway-check").click(), 0);
  } else if(!sessionInfo().authenticated&&!localStorage.getItem("solarminer-first-connection-prompted-v1")) {
    localStorage.setItem("solarminer-first-connection-prompted-v1","1");
    setTimeout(openGatewayConnectionDialog,0);
  }
} catch {}
const invitePanel = $("#gateway-invite-management");
const userPanel = $("#gateway-user-management");
const updatePanel = $("#gateway-update-management");
const tailscalePanel = $("#gateway-tailscale-management");
const hardwarePanel = $("#gateway-hardware-management");
let activeOwnerTab = "access";
let activeOwnerDevice = "deye";
function selectOwnerTab(name) {
  activeOwnerTab = name;
  document.querySelectorAll("[data-owner-tab]").forEach(button => {
    const selected = button.dataset.ownerTab === name;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  document.querySelectorAll("[data-owner-panel]").forEach(panel => {
    panel.hidden = panel.dataset.ownerPanel !== name || !sessionInfo().authenticated || sessionInfo().user.role !== "owner";
  });
}
function selectOwnerDevice(name) {
  activeOwnerDevice = name;
  document.querySelectorAll("[data-owner-device]").forEach(button => {
    const selected = button.dataset.ownerDevice === name;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  document.querySelectorAll("[data-device-panel]").forEach(panel => { panel.hidden = panel.dataset.devicePanel !== name; });
}
document.querySelector(".owner-tabs")?.addEventListener("click", event => {
  const tab = event.target.closest("[data-owner-tab]");
  if (tab) {
    selectOwnerTab(tab.dataset.ownerTab);
    if (tab.dataset.ownerTab === "gateway") { refreshGatewayConsole(); refreshDiagnosticsUploadStatus(); }
  }
});
document.querySelector(".owner-device-tabs")?.addEventListener("click", event => {
  const tab = event.target.closest("[data-owner-device]");
  if (tab) {
    selectOwnerDevice(tab.dataset.ownerDevice);
    if (tab.dataset.ownerDevice === "tesla") {
      const origin = window.location.origin;
      const callback = teslaGatewayCallbackUrl();
      const developerUrl = $("#ev-tesla-help-developer-url"); if (developerUrl) developerUrl.value = "https://developer.tesla.com/";
      for (const id of ["ev-tesla-origin", "ev-tesla-help-origin"]) { const field = $("#" + id); if (field) field.value = origin; }
      for (const id of ["ev-tesla-callback", "ev-tesla-help-callback"]) { const field = $("#" + id); if (field) field.value = callback; }
    }
  }
});
let teslaOAuthPopup = null;
let teslaOAuthState = "";
let teslaOAuthOrigin = "";
let teslaOAuthRelayMode = false;
let teslaOAuthCompleting = false;
let teslaConfiguredCallback = "";
let teslaHelpStep = 0;
function teslaGatewayCallbackUrl() {
  try {
    if (teslaConfiguredCallback) return teslaConfiguredCallback;
    const gatewayUrl = sessionInfo().gatewayUrl;
    return gatewayUrl ? new URL("/api/integration/tesla/callback", gatewayUrl).toString() : "";
  } catch { return ""; }
}
function showTeslaHelpStep(step) {
  teslaHelpStep = Math.max(0, Math.min(6, step));
  document.querySelectorAll("[data-tesla-help-step]").forEach(panel => { panel.hidden = Number(panel.dataset.teslaHelpStep) !== teslaHelpStep; });
  const count = $("#ev-tesla-help-count"); if (count) count.textContent = `Passo ${teslaHelpStep + 1} de 7`;
  const prev = $("#ev-tesla-help-prev"), next = $("#ev-tesla-help-next");
  if (prev) prev.disabled = teslaHelpStep === 0;
  if (next) next.textContent = teslaHelpStep === 6 ? "Concluir" : "Seguinte";
}
$("#ev-tesla-help-open")?.addEventListener("click", () => {
  const origin = window.location.origin, callback = teslaGatewayCallbackUrl();
  const developerUrl = $("#ev-tesla-help-developer-url"); if (developerUrl) developerUrl.value = "https://developer.tesla.com/";
  for (const id of ["ev-tesla-origin", "ev-tesla-help-origin"]) { const field = $("#" + id); if (field) field.value = origin; }
  for (const id of ["ev-tesla-callback", "ev-tesla-help-callback"]) { const field = $("#" + id); if (field) field.value = callback; }
  showTeslaHelpStep(0); $("#ev-tesla-help-dialog")?.showModal();
});
$("#ev-tesla-help-close")?.addEventListener("click", () => $("#ev-tesla-help-dialog")?.close());
$("#ev-tesla-help-prev")?.addEventListener("click", () => showTeslaHelpStep(teslaHelpStep - 1));
$("#ev-tesla-help-next")?.addEventListener("click", () => {
  if (teslaHelpStep === 6) $("#ev-tesla-help-dialog")?.close(); else showTeslaHelpStep(teslaHelpStep + 1);
});
for (const [buttonId, inputId] of [["ev-tesla-copy-origin", "ev-tesla-help-origin"], ["ev-tesla-copy-callback", "ev-tesla-help-callback"], ["ev-tesla-copy-developer", "ev-tesla-help-developer-url"]]) {
  $("#" + buttonId)?.addEventListener("click", async () => {
    const value = $("#" + inputId)?.value || "";
    const developerLink = inputId === "ev-tesla-help-developer-url";
    try { await navigator.clipboard.writeText(value); $("#ev-tesla-help-count").textContent = developerLink ? "Endereço copiado. Abre o browser e cola-o; o guia fica aberto no SolarMiner." : "Endereço copiado. Cola-o no campo correspondente da Tesla Developer."; }
    catch { $("#" + inputId)?.select(); $("#ev-tesla-help-count").textContent = developerLink ? "Endereço selecionado. Copia-o e cola-o no browser; o guia fica aberto no SolarMiner." : "Endereço selecionado. Copia-o e cola-o no campo correspondente da Tesla Developer."; }
  });
}
document.querySelector("#gateway-hardware-management")?.addEventListener("click", async event => {
  const button = event.target.closest("#ev-tesla-relay-save"); if (!button) return;
  event.preventDefault();
  const status = $("#ev-tesla-relay-status"), url = $("#ev-tesla-relay-url").value.trim(), key = $("#ev-tesla-relay-key").value;
  const info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") { status.textContent = "Só o Owner autenticado pode configurar o relay."; return; }
  if (!url || !key) { status.textContent = "Indica o domínio HTTPS da VM e a chave gerada durante a instalação."; return; }
  button.disabled = true; status.textContent = "A testar ligação HTTPS à VM…";
  try {
    const result = await saveGatewayTeslaRelay({relay_url: url, api_key: key});
    $("#ev-tesla-relay-key").value = "";
    status.textContent = "Relay ligado e autenticado. Callback Tesla confirmado: " + result.oauth_redirect_uri;
    await refreshTeslaEvConfig();
  } catch (error) { status.textContent = "Relay não guardado: " + error.message + ". Confirma domínio, certificado, porta HTTPS e chave."; }
  finally { button.disabled = false; }
});
$("#ev-tesla-oauth-start")?.addEventListener("click", async event => {
  const button = event.currentTarget, status = $("#ev-tesla-status"), info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") { status.textContent = "Só o Owner autenticado pode autorizar Tesla Fleet."; return; }
  const clientId = $("#ev-tesla-client-id").value.trim(), clientSecret = $("#ev-tesla-client-secret").value;
  const mac = $("#ev-tesla-local-mac").value.trim().toUpperCase();
  if (!clientId || !clientSecret) { status.textContent = "Preenche o Client ID e o Client Secret da aplicação Tesla Developer."; return; }
  if (mac && !/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac)) { status.textContent = "O MAC deve ter o formato AA:BB:CC:11:22:33."; return; }
  const popup = window.open("about:blank", "solarminerTeslaOAuth", "popup,width=600,height=760");
  if (!popup) { status.textContent = "O browser bloqueou a janela Tesla. Permite pop-ups para esta PWA e tenta novamente."; return; }
  button.disabled = true; status.textContent = "A preparar a autorização segura com a Tesla…";
  try {
    const flow = await startGatewayTeslaOAuth({region: $("#ev-tesla-region").value, client_id: clientId, client_secret: clientSecret, local_mac: mac});
    const callback = new URL(flow.redirect_uri);
    if (callback.protocol !== "https:" || !["/oauth/callback", "/api/integration/tesla/callback"].includes(callback.pathname)) throw new Error("O Gateway devolveu um callback Tesla inválido.");
    teslaConfiguredCallback = flow.redirect_uri;
    for (const id of ["ev-tesla-callback", "ev-tesla-help-callback"]) { const field = $("#" + id); if (field) field.value = flow.redirect_uri; }
    $("#ev-tesla-client-secret").value = "";
    teslaOAuthPopup = popup; teslaOAuthState = flow.state; teslaOAuthOrigin = callback.origin; teslaOAuthRelayMode = Boolean(flow.relay_mode);
    popup.location.replace(flow.authorize_url);
    status.textContent = "Autoriza a conta na janela Tesla. Esta página mantém-se aberta.";
  } catch (error) {
    popup.close(); status.textContent = "Não foi possível iniciar OAuth Tesla: " + error.message;
  } finally { button.disabled = false; }
});
window.addEventListener("message", async event => {
  const result = event.data;
  if (!teslaOAuthPopup || event.source !== teslaOAuthPopup || event.origin !== teslaOAuthOrigin
      || !result || result.state !== teslaOAuthState) return;
  let finalResult = result;
  if (result.type === "solarminer-tesla-relay" && teslaOAuthRelayMode) {
    if (teslaOAuthCompleting) return;
    teslaOAuthCompleting = true;
    try { finalResult = await completeGatewayTeslaOAuth(teslaOAuthState); }
    catch (error) { $("#ev-tesla-status").textContent = `Recebi o retorno Tesla, mas o Gateway não concluiu a autorização: ${error.message}`; return; }
    finally { teslaOAuthCompleting = false; }
    if (!finalResult.ready) { $("#ev-tesla-status").textContent = "Retorno recebido. A aguardar o código seguro no Gateway…"; return; }
  }
  if (!finalResult || finalResult.type !== "solarminer-tesla-oauth-result" || finalResult.state !== teslaOAuthState) return;
  teslaOAuthPopup = null; teslaOAuthState = ""; teslaOAuthRelayMode = false;
  const status = $("#ev-tesla-status");
  if (!finalResult.ok) { status.textContent = finalResult.message || "A autorização Tesla falhou."; return; }
  const select = $("#ev-tesla-vehicle-select"), vehicles = Array.isArray(finalResult.vehicles) ? finalResult.vehicles : [];
  select.replaceChildren(new Option("Seleciona o veículo Tesla", ""));
  for (const vehicle of vehicles) {
    if (!vehicle || !/^\d+$/.test(String(vehicle.id))) continue;
    const suffix = vehicle.vin_suffix ? ` · VIN …${vehicle.vin_suffix}` : "";
    select.add(new Option(`${vehicle.name || "Tesla"}${suffix}`, String(vehicle.id)));
  }
  $("#ev-tesla-vehicle-save-wrap").hidden = vehicles.length === 0;
  status.textContent = vehicles.length ? "Conta Tesla autorizada. Escolhe o veículo e guarda a seleção." : "Conta autorizada, mas a Tesla não devolveu veículos elegíveis para esta conta.";
});
setInterval(async () => {
  if (!teslaOAuthPopup || !teslaOAuthRelayMode || teslaOAuthCompleting || document.visibilityState !== "visible") return;
  teslaOAuthCompleting = true;
  try {
    const result = await completeGatewayTeslaOAuth(teslaOAuthState);
    if (!result.ready || result.state !== teslaOAuthState) return;
    window.dispatchEvent(new MessageEvent("message", {data: result, origin: teslaOAuthOrigin, source: teslaOAuthPopup}));
  } catch { /* A relay can be temporarily unreachable; retry while the Owner returns to the PWA. */ }
  finally { teslaOAuthCompleting = false; }
}, 2000);
$("#ev-tesla-vehicle-save")?.addEventListener("click", async event => {
  const button = event.currentTarget, status = $("#ev-tesla-status"), vehicleId = $("#ev-tesla-vehicle-select").value;
  if (!vehicleId) { status.textContent = "Escolhe primeiro um veículo Tesla."; return; }
  button.disabled = true; status.textContent = "A guardar o veículo autorizado no Gateway…";
  try {
    $("#ev-tesla-vehicle-id").value = vehicleId;
    const clientId = $("#ev-tesla-client-id").value.trim(), mac = $("#ev-tesla-local-mac").value.trim().toUpperCase();
    const config = await saveGatewayTeslaEvConfig({region: $("#ev-tesla-region").value, client_id: clientId, vehicle_ids: [vehicleId], ...(mac ? {local_mac: mac} : {})});
    if (!config.configured) throw new Error("O Gateway não confirmou a configuração Fleet.");
    status.textContent = "Veículo Tesla guardado. A testar leitura Fleet…";
    const result = await readGatewayTeslaEvCharging();
    const inventory = await readGatewayDeviceInventory(); state.gatewayDeviceInventory = Array.isArray(inventory.devices) ? inventory.devices : [];
    status.textContent = `Ligação guardada e testada: ${(result.vehicles || []).length} veículo(s) consultado(s). O refresh token fica privado no Gateway; não foram enviados comandos ao carro.`;
  } catch (error) { status.textContent = "Não foi possível guardar/testar o veículo: " + error.message; }
  finally { button.disabled = false; }
});
$("#owner-gateway-status").textContent = "Configura e autentica a ligação pelo botão acima.";
$("#owner-nav-item").addEventListener("click", () => selectOwnerTab(activeOwnerTab));
let gatewayConsoleRefreshInFlight = false;
let gatewayConsoleServices = {};
const gatewayConsoleServiceLabels = {
  gateway: "SolarMiner Gateway", nginx: "Nginx", tailscale: "Tailscale",
  gateway_watchdog: "Watchdog",
  daily_update_check: "Verificação diária de atualizações",
  privileged_update_broker: "Broker de atualização privilegiado",
  tailscale_certificate_renewal: "Renovação do certificado Tailscale",
};
function gatewayConsoleBytes(value) {
  if (!Number.isFinite(value) || value < 0) return "indisponível";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let scaled = value, index = 0;
  while (scaled >= 1024 && index < units.length - 1) { scaled /= 1024; index++; }
  return `${scaled.toLocaleString("pt-PT", { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}
function renderGatewayConsoleMetrics(result) {
  const servicesHost = $("#gateway-console-services"), resourcesHost = $("#gateway-console-resources");
  if (!servicesHost || !resourcesHost) return;
  servicesHost.replaceChildren();
  const services = result.services && typeof result.services === "object" ? result.services : {};
  gatewayConsoleServices = services;
  for (const [key, label] of Object.entries(gatewayConsoleServiceLabels)) {
    const row = document.createElement("div"), name = document.createElement("span"), state = document.createElement("span");
    const value = ["active", "inactive", "failed"].includes(services[key]) ? services[key] : "unknown";
    row.className = "gateway-console-service";
    name.textContent = label;
    state.className = `gateway-console-state ${value}`;
    state.textContent = value === "active" ? "Ativo" : value === "inactive" ? "Parado" : value === "failed" ? "Falhou" : "Desconhecido";
    row.append(name, state);
    servicesHost.append(row);
  }
  resourcesHost.replaceChildren();
  const resources = result.resources && typeof result.resources === "object" ? result.resources : {};
  const memory = resources.memory || {}, disk = resources.disk || {};
  const metrics = [
    ["CPU", Number.isFinite(resources.cpu_percent) ? `${resources.cpu_percent.toLocaleString("pt-PT", { maximumFractionDigits: 1 })}%` : "indisponível"],
    ["RAM", Number.isFinite(memory.used_percent) ? `${memory.used_percent.toLocaleString("pt-PT", { maximumFractionDigits: 1 })}% · ${gatewayConsoleBytes(memory.used_bytes)} / ${gatewayConsoleBytes(memory.total_bytes)}` : "indisponível"],
    ["Armazenamento", Number.isFinite(disk.used_percent) ? `${disk.used_percent.toLocaleString("pt-PT", { maximumFractionDigits: 1 })}% · ${gatewayConsoleBytes(disk.used_bytes)} / ${gatewayConsoleBytes(disk.total_bytes)}` : "indisponível"],
  ];
  for (const [label, value] of metrics) {
    const row = document.createElement("div"), name = document.createElement("span"), amount = document.createElement("strong");
    row.className = "gateway-console-resource"; name.textContent = label; amount.textContent = value;
    row.append(name, amount); resourcesHost.append(row);
  }
  const watchdogButton = $("#gateway-watchdog-toggle"), watchdogStatus = $("#gateway-watchdog-status");
  const watchdog = services.gateway_watchdog;
  if (watchdogButton) {
    watchdogButton.disabled = !["active", "inactive", "failed"].includes(watchdog);
    watchdogButton.textContent = watchdog === "active" ? "Desativar Watchdog" : "Ativar Watchdog";
  }
  if (watchdogStatus) watchdogStatus.textContent = watchdog === "active"
    ? "Ativo; as verificações do Watchdog estão ligadas."
    : watchdog === "inactive" ? "Desativado; podes ativá-lo manualmente aqui."
      : watchdog === "failed" ? "O temporizador do Watchdog está em falha."
        : "Estado do Watchdog desconhecido.";
}
$("#gateway-watchdog-toggle")?.addEventListener("click", async event => {
  const button = event.currentTarget, status = $("#gateway-watchdog-status");
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner") return;
  const enable = gatewayConsoleServices.gateway_watchdog !== "active";
  button.disabled = true;
  status.textContent = enable ? "A ativar o Watchdog…" : "A desativar o Watchdog…";
  try {
    const result = await setGatewayWatchdogEnabled(enable);
    status.textContent = result.enabled ? "Watchdog ativado manualmente." : "Watchdog desativado manualmente.";
    await refreshGatewayConsole({ silent: true });
  } catch (error) {
    status.textContent = `Não foi possível alterar o Watchdog: ${error.message}`;
    button.disabled = false;
  }
});
async function refreshGatewayConsole({ silent = false } = {}) {
  const status = $("#gateway-console-status"), output = $("#gateway-console-output");
  if (!status || !output || gatewayConsoleRefreshInFlight) return;
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner") {
    if (!silent) status.textContent = "Só o Owner autenticado pode consultar a consola.";
    return;
  }
  gatewayConsoleRefreshInFlight = true;
  if (!silent) status.textContent = "A consultar a saída recente do Gateway…";
  try {
    const result = await readGatewayConsole();
    gatewayConsoleServices = result.services && typeof result.services === "object" ? result.services : {};
    renderGatewayConsoleMetrics(result);
    gatewayConsoleLogs = result.logs || "Sem saída recente dos serviços autorizados.";
    renderGatewayConsoleLogs({ preserveScroll: true });
    renderGatewayConsoleErrors();
    status.textContent = `Atualizado ${timeLabel(result.captured_at)} · registos mais recentes no fim${result.truncated ? " · conteúdo limitado" : ""}.`;
  } catch (error) {
    status.textContent = `Não foi possível consultar a consola: ${error.message}`;
  } finally {
    gatewayConsoleRefreshInFlight = false;
  }
}
let gatewayConsoleLogs = "";
const gatewayConsoleErrorPattern = /\b(error|err|failed|failure|fatal|emerg|critical|exception|traceback)\b|\[emerg\]/i;
const gatewayConsoleServicePatterns = {
  gateway: /solarminer[-_ ]gateway|uvicorn|fastapi/i,
  nginx: /nginx|current nginx configuration validation/i,
  tailscale: /tailscale|tailscale-cert/i,
  updates: /solarminer-update|recovery|rollback|preflight|update-apply|broker/i,
};
function gatewayConsoleLineService(line) {
  return Object.entries(gatewayConsoleServicePatterns).find(([, pattern]) => pattern.test(line))?.[0] || "unknown";
}
function gatewayConsoleDetectedErrorServices() {
  const detected = new Set(Object.entries(gatewayConsoleServices).filter(([, state]) => state === "failed").map(([name]) => name));
  for (const line of gatewayConsoleLogs.split("\n")) {
    if (gatewayConsoleErrorPattern.test(line)) {
      const service = gatewayConsoleLineService(line);
      detected.add(service);
    }
  }
  return detected;
}
function renderGatewayConsoleErrors() {
  const host = $("#gateway-console-errors");
  if (!host) return;
  const failed = Object.entries(gatewayConsoleServices).filter(([, state]) => state === "failed");
  const errors = gatewayConsoleLogs.split("\n").filter(line => gatewayConsoleErrorPattern.test(line)).slice(-5);
  host.replaceChildren();
  if (!failed.length && !errors.length) {
    host.classList.remove("has-errors");
    host.textContent = "Sem falhas ou erros explícitos nos serviços e registos consultados.";
    return;
  }
  host.classList.add("has-errors");
  const title = document.createElement("strong");
  title.textContent = "Possíveis erros detetados";
  host.append(title);
  const summary = document.createElement("p");
  summary.textContent = failed.length
    ? `Serviços marcados como falhados: ${failed.map(([name]) => gatewayConsoleServiceLabels[name] || name).join(", ")}.`
    : "Há linhas de erro nos registos; o estado dos serviços não indica falha ativa.";
  host.append(summary);
  if (errors.length) {
    const list = document.createElement("ul");
    for (const line of errors) {
      const item = document.createElement("li");
      const service = gatewayConsoleLineService(line);
      const label = gatewayConsoleServiceLabels[service] || (service === "unknown" ? "Serviço não identificado" : service);
      item.textContent = `${label}: ${line}`;
      list.append(item);
    }
    host.append(list);
  }
}
$("#gateway-console-send-report")?.addEventListener("click", async event => {
  const button = event.currentTarget, status = $("#gateway-console-send-report-status");
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner") return;
  button.disabled = true;
  status.textContent = "A enviar o snapshot atual e a fila de erros para o repositório privado…";
  try {
    const result = await sendGatewayDiagnosticsReport();
    status.replaceChildren(document.createTextNode("Relatório enviado para o destino privado. "));
    if (typeof result.issue_url === "string" && result.issue_url.startsWith("https://github.com/")) {
      const link = document.createElement("a"); link.href = result.issue_url; link.target = "_blank";
      link.rel = "noopener noreferrer"; link.textContent = "Abrir relatório"; status.append(link);
    }
  } catch (error) {
    status.textContent = error.message?.includes("github_diagnostics_not_configured")
      ? "Configura primeiro o token privado do GitHub na secção Relatórios automáticos."
      : `Não foi possível enviar o relatório: ${error.message}`;
  } finally { button.disabled = false; }
});
function renderGatewayConsoleLogs({ preserveScroll = false } = {}) {
  const output = $("#gateway-console-output");
  if (!output) return;
  const previousScrollTop = output.scrollTop;
  const service = $("#gateway-console-service-filter")?.value || "all";
  const level = $("#gateway-console-level-filter")?.value || "all";
  const lines = gatewayConsoleLogs.split("\n");
  const datedLines = [], otherLines = [];
  for (const [index, line] of lines.entries()) {
    const match = line.match(/^(\d{4}-\d{2}-\d{2}[T ][^\s]+)/);
    const timestamp = match ? Date.parse(match[1]) : NaN;
    if (Number.isFinite(timestamp)) datedLines.push({ line, timestamp, index });
    else otherLines.push({ line, index });
  }
  datedLines.sort((a, b) => a.timestamp - b.timestamp || a.index - b.index);
  const chronologicalLines = [...otherLines, ...datedLines].map(entry => entry.line);
  const levelPatterns = {
    error: /\b(error|err|failed|failure|fatal|emerg|critical)\b|\[emerg\]/i,
    warning: /\b(warn|warning)\b/i,
    info: /\b(info|notice)\b/i,
  };
  const filtered = chronologicalLines.filter(line =>
    (service === "all" || (service === "errors"
      ? gatewayConsoleErrorPattern.test(line) && gatewayConsoleDetectedErrorServices().has(gatewayConsoleLineService(line))
      : gatewayConsoleServicePatterns[service]?.test(line))) &&
    (level === "all" || levelPatterns[level]?.test(line))
  );
  output.textContent = filtered.join("\n") || "Sem registos para estes filtros.";
  if (preserveScroll) output.scrollTop = previousScrollTop;
}
$("#gateway-console-service-filter")?.addEventListener("change", () => renderGatewayConsoleLogs());
$("#gateway-console-level-filter")?.addEventListener("change", () => renderGatewayConsoleLogs());
$("#gateway-console-refresh")?.addEventListener("click", refreshGatewayConsole);
async function refreshDiagnosticsUploadStatus() {
  const status = $("#gateway-diagnostics-upload-status");
  if (!status || !sessionInfo().authenticated || sessionInfo().user?.role !== "owner") return;
  status.textContent = "A consultar configuração…";
  try {
    const result = await readGatewayDiagnosticsUpload();
    status.textContent = result.configured
      ? `Envio ativo para o repositório privado ${result.destination}. O token não é devolvido à PWA.`
      : `Envio desativado. Os erros ficam na fila local até configurares um token para ${result.destination}.`;
  } catch (error) { status.textContent = `Não foi possível consultar a configuração: ${error.message}`; }
}
$("#gateway-diagnostics-upload-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  const input = $("#gateway-diagnostics-upload-token"), status = $("#gateway-diagnostics-upload-status"), button = event.currentTarget.querySelector('button[type="submit"]');
  const token = input?.value || "";
  if (!token) return;
  button.disabled = true;
  status.textContent = "A guardar o token apenas no Gateway…";
  try {
    const result = await saveGatewayDiagnosticsUploadToken(token);
    input.value = "";
    status.textContent = result.configured ? `Token guardado. Envio ativo para ${result.destination}; a credencial não é mostrada nem incluída nos relatórios.` : "O Gateway não confirmou a configuração.";
  } catch (error) {
    input.value = "";
    status.textContent = `Não foi possível guardar o token: ${error.message}`;
  } finally { button.disabled = false; }
});
$("#gateway-diagnostics-upload-disable")?.addEventListener("click", async event => {
  const button = event.currentTarget, status = $("#gateway-diagnostics-upload-status");
  button.disabled = true;
  try {
    const result = await disableGatewayDiagnosticsUpload();
    status.textContent = result.configured ? "O envio continua configurado." : "Envio desativado. Os novos relatórios permanecem apenas no Gateway.";
  } catch (error) { status.textContent = `Não foi possível desativar o envio: ${error.message}`; }
  finally { button.disabled = false; }
});
let gatewayTerminalSocket = null;
function appendGatewayTerminalOutput(value) {
  const output = $("#gateway-terminal-output");
  if (!output) return;
  output.textContent = `${output.textContent === "Terminal desligado." ? "" : output.textContent}${value}`.slice(-100000);
  output.scrollTop = output.scrollHeight;
}
function setGatewayTerminalConnected(connected) {
  $("#gateway-terminal-connect").disabled = connected;
  $("#gateway-terminal-disconnect").disabled = !connected;
  $("#gateway-terminal-command").disabled = !connected;
  $("#gateway-terminal-send").disabled = !connected;
  if (connected) $("#gateway-terminal-command").focus();
}
async function connectGatewayTerminal() {
  const status = $("#gateway-terminal-status"), button = $("#gateway-terminal-connect");
  if (!status || gatewayTerminalSocket) return;
  if (!sessionInfo().authenticated || sessionInfo().user?.role !== "owner") {
    status.textContent = "Só o Owner autenticado pode abrir o terminal.";
    return;
  }
  button.disabled = true;
  status.textContent = "A abrir sessão segura no Gateway…";
  $("#gateway-terminal-output").textContent = "";
  try {
    const socket = await openGatewayTerminalSocket();
    gatewayTerminalSocket = socket;
    // openGatewayTerminalSocket resolves only after receiving the Gateway's
    // authenticated "ready" message. The WebSocket's "open" event has already
    // fired by then, so enable the input here instead of waiting for that event.
    setGatewayTerminalConnected(true);
    status.textContent = "Terminal ligado ao Gateway.";
    socket.addEventListener("open", () => {
      setGatewayTerminalConnected(true);
      status.textContent = "A ligar ao terminal do Gateway…";
    });
    socket.addEventListener("message", event => {
      let message;
      try { message = JSON.parse(event.data); } catch { appendGatewayTerminalOutput(String(event.data)); return; }
      if (message.type === "output") appendGatewayTerminalOutput(message.data || "");
      else if (message.type === "ready") { status.textContent = message.data || "Terminal ligado."; appendGatewayTerminalOutput(`${message.data || "Terminal ligado."}\r\n`); }
      else if (message.type === "error") { status.textContent = message.data || "Erro no terminal."; appendGatewayTerminalOutput(`\r\n${message.data || "Erro no terminal."}\r\n`); }
      else if (message.type === "exit") appendGatewayTerminalOutput(`\r\n[processo terminou${message.code == null ? "" : ` · código ${message.code}`} ]\r\n`);
    });
    socket.addEventListener("close", () => {
      gatewayTerminalSocket = null;
      setGatewayTerminalConnected(false);
      status.textContent = "Terminal desligado.";
    });
    socket.addEventListener("error", () => { status.textContent = "Não foi possível manter ligação ao terminal do Gateway."; });
  } catch (error) {
    gatewayTerminalSocket = null;
    button.disabled = false;
    let detail = error.message;
    if (error.code === "websocket_handshake_failed" || error.code?.startsWith("close_1006") || error.code === "timeout") {
      try {
        const [diagnostic, tailscale] = await Promise.all([
          readGatewayTerminalDiagnostics(), readGatewayTailscale()
        ]);
        if (!diagnostic.available) {
          detail = !diagnostic.pty_available
            ? "A API do Gateway respondeu, mas este sistema não disponibiliza o terminal PTY."
            : "A API do Gateway respondeu, mas a shell do terminal não está instalada.";
        } else if (!tailscale.https_ready) {
          const failedChecks = Object.entries(tailscale.checks || {}).filter(([, ok]) => !ok).map(([name]) => name);
          detail = `A API e o terminal estão disponíveis, mas o HTTPS do Tailscale não está pronto${failedChecks.length ? ` (verificação: ${failedChecks.join(", ")})` : ""}. O endereço guardado não consegue encaminhar o WebSocket até o Gateway.`;
        } else {
          detail = `A API, o terminal e o HTTPS do Tailscale estão prontos em ${tailscale.endpoint}, mas o handshake WebSocket falhou. O problema está no encaminhamento WebSocket do proxy, não na shell; esta verificação não executou comandos.`;
        }
      } catch (diagnosticError) {
        detail = `${error.message} A verificação autenticada da API também falhou: ${diagnosticError.message}`;
      }
    }
    status.textContent = `Não foi possível abrir o terminal: ${detail}`;
    appendGatewayTerminalOutput(`\r\n[Diagnóstico] ${detail}\r\n`);
  }
}
function disconnectGatewayTerminal() {
  const socket = gatewayTerminalSocket;
  gatewayTerminalSocket = null;
  if (socket?.readyState === WebSocket.OPEN) {
    try { socket.send(JSON.stringify({ type: "close" })); } catch { /* Closing the socket below is sufficient. */ }
  }
  socket?.close();
  setGatewayTerminalConnected(false);
  const status = $("#gateway-terminal-status");
  if (status) status.textContent = "Terminal desligado.";
}
$("#gateway-terminal-connect")?.addEventListener("click", () => connectGatewayTerminal());
$("#gateway-terminal-disconnect")?.addEventListener("click", disconnectGatewayTerminal);
$("#gateway-terminal-form")?.addEventListener("submit", event => {
  event.preventDefault();
  const socket = gatewayTerminalSocket, input = $("#gateway-terminal-command");
  if (!socket || socket.readyState !== WebSocket.OPEN || !input.value) return;
  socket.send(JSON.stringify({ type: "input", data: `${input.value}\n` }));
  input.value = "";
});
$("#gateway-terminal-command")?.addEventListener("keydown", event => {
  if (event.ctrlKey && event.key.toLowerCase() === "c" && gatewayTerminalSocket?.readyState === WebSocket.OPEN) {
    event.preventDefault();
    gatewayTerminalSocket.send(JSON.stringify({ type: "input", data: "\u0003" }));
  }
});
window.addEventListener("pagehide", disconnectGatewayTerminal);
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
  renderGatewayUpdateBanner();
  if (info.authenticated) {
    const presence = presenceInfo();
    status.textContent = `Sessão autenticada: ${info.user.username} (${info.user.role}) · token apenas em memória · presença da sessão: ${presence.state || "unknown"}; não prova presença física.`;
    invitePanel.hidden = info.user.role !== "owner";
    userPanel.hidden = info.user.role !== "owner";
    if (info.user.role === "owner") {
      if(!gatewayOwnerAutoCheckStarted){gatewayOwnerAutoCheckStarted=true;setTimeout(()=>runGatewayUpdateCheck({automatic:true}),1200);}
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
      if (info.user.role === "owner") { refreshHardwareIntegrationConfig().catch(error => {
        $("#deye-status").textContent = `Não foi possível carregar a configuração: ${error.message}`;
      }); refreshTeslaEvConfig().catch(error => { const target = $("#ev-tesla-status"); if (target) target.textContent = `Não foi possível carregar Tesla Fleet: ${error.message}`; }); }
    }
  } else {
    gatewayOwnerAutoCheckStarted=false;
    status.textContent = "Sem sessão ativa. Ao testar o endpoint, este dispositivo tenta autenticar-se pela identidade guardada.";
    invitePanel.hidden = true;
    userPanel.hidden = true;
    if (updatePanel) updatePanel.hidden = true;
    if (tailscalePanel) tailscalePanel.hidden = true;
    if (hardwarePanel) hardwarePanel.hidden = true;
    verifiedGatewayUpdate = null;
  }
  selectOwnerTab(activeOwnerTab);
  selectOwnerDevice(activeOwnerDevice);
}
async function refreshHardwareIntegrationConfig({signal}={}) {
  const config = await readGatewayHardwareIntegrationConfig({signal});
  const deye = config.deye || {}, miner = config.antminer || {}, tuya = config.tuya || {};
  const deyeCloud=config.deye_cloud||{};
  state.tuyaDevices=normalizeTuyaInventory(tuya.devices);
  $("#hardware-deye-host").value = deye.host || "";
  $("#hardware-deye-port").value = deye.port || 502;
  $("#hardware-deye-unit").value = deye.unit_id ?? 1;
  $("#deye-cloud-center").value=deyeCloud.data_center||"eu";
  $("#deye-cloud-app-id").value=deyeCloud.app_id||"";
  $("#deye-cloud-email").value=deyeCloud.email||"";
  $("#deye-cloud-app-secret").value="";$("#deye-cloud-password").value="";
  $("#hardware-antminer-host").value = miner.host || "";
  $("#hardware-antminer-port").value = miner.port || 4028;
  $("#hardware-antminer-rest-port").value = miner.rest_port || 80;
  $("#hardware-antminer-password").value = "";
  $("#hardware-tuya-region").value = tuya.region || "eu_central";
  $("#hardware-tuya-client-id").value = tuya.client_id || "";
  $("#hardware-tuya-uid").value = tuya.uid || "";
  $("#hardware-tuya-client-secret").value = "";
  $("#hardware-tuya-devices").value = (tuya.devices || []).map(device => `${device.device_id} | ${device.name}${device.switch_code ? ` | ${device.switch_code}` : ""}${device.level_code ? ` | ${device.level_code} | ${device.level_min ?? 0} | ${device.level_max ?? 100}` : ""}`).join("\n");
  $("#deye-status").textContent = deye.host ? `Deye configurado em ${deye.host}:${deye.port || 502}, Unit ID ${deye.unit_id ?? 1}.` : "Deye ainda não configurado.";
  $("#antminer-status").textContent = miner.host ? `Antminer configurada em ${miner.host}:${miner.port || 4028}. Credenciais de controlo ${config.antminer_control_configured ? "guardadas no Gateway" : "por configurar"}.` : "Antminer ainda não configurada.";
  const importedCount = (tuya.devices || []).filter(device => device.cloud_source === "TUYA_PROJECT" || device.local_key_available).length;
  $("#tuya-status").textContent = tuya.configured ? `Conta Tuya configurada; segredo oculto no Gateway. ${importedCount} dispositivo(s) sincronizado(s).` : "Conta Tuya ainda não configurada.";
  $("#deye-cloud-status").textContent=deyeCloud.configured?"Acesso Deye Cloud guardado no Gateway. Os segredos não são devolvidos à PWA.":"Configura a aplicação de developer Deye e a conta para importar o histórico.";
  renderTuyaDeviceCards(tuya.devices || []);
  return config;
}
function tuyaDeviceGlyph(device) {
  return equipmentIconSvg(device,"tuya");
}
function tuyaFriendlyCapabilityLabel(item, device){
  const code=String(item.code||""),custom=device.capability_labels?.[code]||device.channel_labels?.[code];
  if(custom)return custom;
  const known={switch:"Interruptor",switch_led:"Luz",cur_power:"Potência atual",cur_voltage:"Tensão atual",cur_current:"Corrente atual",add_ele:"Energia acumulada",temp_current:"Temperatura",humidity_value:"Humidade",doorcontact_state:"Estado da porta",va_temperature:"Temperatura",bright_value:"Brilho",brightness:"Brilho",colour_data:"Cor",work_state:"Modo de funcionamento",relay_status:"Estado do relé",online_state:"Estado online",light_mode:"Modo da luz",countdown_1:"Contagem decrescente",countdown:"Contagem decrescente",cycle_time:"Temporizador",alarm_set_1:"Alarme",alarm_set_2:"Alarme"};
  if(known[code])return known[code];
  const normalized=code.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"");if(typeof TUYA_DPS_CODE_PT!=="undefined"&&TUYA_DPS_CODE_PT[normalized])return TUYA_DPS_CODE_PT[normalized];
  const channel=code.match(/^switch_(\d+)$/);if(channel)return `Canal ${channel[1]}`;
  const chinese=String(item.name||item.desc||"");if(/断路器|空气开关|漏电保护/.test(chinese))return "Disjuntor";if(/窗帘|卷帘|百叶/.test(chinese))return "Estore";if(/插座/.test(chinese))return "Tomada";if(/温度/.test(chinese))return "Temperatura";if(/湿度/.test(chinese))return "Humidade";if(/电压/.test(chinese))return "Tensão";if(/电流/.test(chinese))return "Corrente";if(/功率/.test(chinese))return "Potência";if(/开关|继电器/.test(chinese))return "Interruptor";if(/亮度/.test(chinese))return "Brilho";if(/灯|照明/.test(chinese))return "Luz";
  if(/[\u3400-\u9fff]/.test(String(item.name||item.desc||""))){const translated=typeof tuyaDpsPt==="function"?tuyaDpsPt({name:item.name||item.desc,code},0):"";if(translated&&translated!=="Ponto de dados 0")return translated;return `Função Tuya · ${code||"sem código"}`;}
  return item.name||code||"Função sem nome";
}
function tuyaEnumValuePt(value){const key=String(value??"").trim().toLowerCase();return ({power_off:"Desligado",power_on:"Ligado",last:"Último estado",off:"Desligado",on:"Ligado",memory:"Memória",relay:"Relé",pos:"Posição",none:"Nenhum",online:"Online",offline:"Offline",auto:"Automático",manual:"Manual",open:"Aberto",closed:"Fechado",lock:"Bloqueado",unlock:"Desbloqueado"})[key]||String(value??"");}
function setupTuyaEditorTabs(dialog){
  const form=dialog.querySelector("#tuya-device-edit-form"),children=[...form.children],first=children.findIndex(node=>node.tagName==="H3"),status=children.find(node=>node.id==="tuya-device-edit-status");
  if(first<0||!status)return;
  const end=children.indexOf(status),groups=[{title:"Geral",nodes:children.slice(0,first)}];let current=null;
  for(const node of children.slice(first,end)){if(node.tagName==="H3"){current={title:node.textContent.trim(),nodes:[node]};groups.push(current);}else if(current)current.nodes.push(node);}
  const tabs=document.createElement("nav");tabs.className="tuya-editor-tabs";tabs.setAttribute("aria-label","Secções do dispositivo");const panels=document.createElement("div");panels.className="tuya-editor-panels";
  groups.forEach((group,index)=>{const id=`tuya-editor-tab-${index}`,button=document.createElement("button"),panel=document.createElement("section");button.type="button";button.className="tuya-editor-tab";button.textContent=group.title;button.setAttribute("aria-controls",id);button.setAttribute("aria-selected",String(index===0));panel.id=id;panel.className="tuya-editor-panel";panel.hidden=index!==0;group.nodes.forEach(node=>panel.append(node));tabs.append(button);panels.append(panel);button.addEventListener("click",()=>{tabs.querySelectorAll("button").forEach((tab,i)=>tab.setAttribute("aria-selected",String(i===index)));panels.querySelectorAll("section").forEach((section,i)=>section.hidden=i!==index);});});
  form.insertBefore(tabs,form.children[first]);form.insertBefore(panels,status);
}
function openTuyaDpsDescriptionEditor(device,dpsId,currentLabel,onSaved,initial={}){
  const editor=document.createElement("dialog");editor.className="tuya-dps-label-dialog";
  editor.innerHTML=`<form class="dialog-body"><p class="eyebrow">MAPA DO PRODUTO · ${esc(device.product_name||device.product_id||device.category||"Tuya")}</p><h2>Identificar DPS ${esc(dpsId)}</h2><p class="field-note">Escolhe a característica e os detalhes deste DPS. O mapa fica associado ao Product ID, ao Product Tuya, à categoria e ao tipo funcional e é partilhado apenas com dispositivos que correspondam exatamente.</p><label>Característica normalizada<select name="semantic"><option value="custom_label">Informação descritiva · sem cálculo</option><option value="voltage">Tensão</option><option value="current">Corrente</option><option value="power">Potência instantânea</option><option value="daily_accumulated_energy">Consumo diário</option><option value="total_energy">Energia acumulada</option><option value="switch">Estado do disjuntor</option><option value="countdown">Temporizador</option><option value="child_lock">Bloqueio</option></select></label><label>Descrição visível<input name="description" maxlength="80" required value="${esc(currentLabel||"")}" autocomplete="off"></label><label>Unidade após aplicar o divisor<select name="unit"><option value="">Sem unidade</option><option>V</option><option>mV</option><option>A</option><option>mA</option><option>W</option><option>kW</option><option>Wh</option><option>kWh</option><option>s</option></select></label><label>Divisor do valor bruto<input name="scale" type="number" min="1" max="1000000000" step="any" value="${esc(initial.scale??1)}"><small>Exemplo: 25321 dividido por 1000 = 25,321 na unidade escolhida. Usa 1 se o valor já estiver na unidade indicada.</small></label><p class="connection-result" data-dps-label-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-dps-label-cancel>Cancelar</button><button type="submit" class="button primary">Guardar mapa do produto</button></div></form>`;
  const semanticField=editor.querySelector('[name="semantic"]'),descriptionField=editor.querySelector('[name="description"]'),unitField=editor.querySelector('[name="unit"]');
  semanticField.value=initial.semantic_code||"custom_label";unitField.value=initial.unit||"";
  const standardDpsLabels={voltage:["Tensão","V"],current:["Corrente","A"],power:["Potência instantânea","W"],daily_accumulated_energy:["Consumo diário","kWh"],total_energy:["Energia acumulada","kWh"],switch:["Estado do disjuntor",""],countdown:["Temporizador","s"],child_lock:["Bloqueio",""]};
  semanticField.addEventListener("change",()=>{const standard=standardDpsLabels[semanticField.value];if(!standard)return;descriptionField.value=standard[0];unitField.value=standard[1];});
  if(semanticField.value!="custom_label"&&!unitField.value&&standardDpsLabels[semanticField.value])unitField.value=standardDpsLabels[semanticField.value][1];
  // The Gateway publishes the normalized semantic vocabulary inside every
  // exact Product ID profile. Build the editor from that profile so additions
  // to the catalog appear without another hard-coded PWA list.
  const fallbackCharacteristics=[{code:"custom_label",label:"Informação descritiva",data_type:"unknown",units:[""]},{code:"switch",label:"Estado ON/OFF",data_type:"boolean",units:[""]},{code:"voltage",label:"Tensão",data_type:"number",units:["V","mV"]},{code:"current",label:"Corrente",data_type:"number",units:["A","mA"]},{code:"power",label:"Potência instantânea",data_type:"number",units:["W","kW"]},{code:"daily_accumulated_energy",label:"Consumo diário",data_type:"number",units:["Wh","kWh"]},{code:"total_energy",label:"Energia acumulada",data_type:"number",units:["Wh","kWh"]}];
  const characteristics=Array.isArray(device.product_profile?.normalized_characteristics)&&device.product_profile.normalized_characteristics.length?device.product_profile.normalized_characteristics:fallbackCharacteristics;
  semanticField.replaceChildren(...characteristics.map(item=>{const option=document.createElement("option");option.value=item.code;option.textContent=`${item.label} · ${item.data_type||"unknown"}`;return option;}));
  const updateCharacteristicUnits=(preserve=true)=>{const selected=characteristics.find(item=>item.code===semanticField.value)||{},units=Array.isArray(selected.units)?selected.units:[""],wanted=preserve?unitField.value:"";unitField.replaceChildren(...[...new Set(units)].map(unit=>{const option=document.createElement("option");option.value=unit;option.textContent=unit||"Sem unidade";return option;}));unitField.value=units.includes(wanted)?wanted:(units[0]||"");};
  semanticField.value=characteristics.some(item=>item.code===initial.semantic_code)?initial.semantic_code:(characteristics.some(item=>item.code==="custom_label")?"custom_label":characteristics[0]?.code||"");updateCharacteristicUnits(false);if(initial.unit&&[...unitField.options].some(option=>option.value===initial.unit))unitField.value=initial.unit;
  semanticField.addEventListener("change",()=>{const selected=characteristics.find(item=>item.code===semanticField.value);updateCharacteristicUnits(false);if(selected&&selected.code!=="custom_label")descriptionField.value=selected.label||descriptionField.value;});
  document.body.append(editor);editor.addEventListener("close",()=>editor.remove());editor.querySelector("[data-dps-label-cancel]").addEventListener("click",()=>editor.close());editor.showModal();
  editor.querySelector("form").addEventListener("submit",async event=>{event.preventDefault();const form=event.currentTarget,button=editor.querySelector('[type="submit"]'),status=editor.querySelector("[data-dps-label-status]"),mapping={semantic_code:form.elements.semantic.value,unit:form.elements.unit.value,scale:Number(form.elements.scale.value)};button.disabled=true;status.textContent="A guardar descrição, característica e escala no mapa do produto…";try{const result=await saveGatewayTuyaProductDpsDescription(device.device_id,dpsId,form.elements.description.value,mapping),mapped={dps_id:dpsId,display_name:result.description,semantic_code:result.semantic_code,unit:result.unit||null,scale:result.scale??null,confidence:"OWNER_CUSTOM",source:"Gateway Product ID mapping",data_type:result.semantic_code==="switch"?"boolean":result.semantic_code==="power"||result.semantic_code==="voltage"||result.semantic_code==="current"?"number":"unknown"};for(const collection of [device.dps_knowledge?.dps,device.product_profile?.dps]){if(!Array.isArray(collection))continue;const row=collection.find(item=>Number(item.dps_id)===dpsId);if(row)Object.assign(row,mapped);else collection.push({...mapped});}status.textContent=`Mapa guardado para ${result.affected_device_count} dispositivo(s) deste Product ID.`;onSaved(result);render();window.setTimeout(()=>editor.close(),500);}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;button.disabled=false;}});
}
async function loadTuyaDpsSnapshot(device,container){
  if(!container||container.dataset.loading==="true")return;container.dataset.loading="true";container.textContent="A ler os DPS deste dispositivo pela LAN…";
  try{
    const report=await runGatewayTuyaLanDiagnostics(1,device.device_id),result=(report.devices||[]).find(item=>item?.device_id===device.device_id);
    if(!result||result.connection_state!=="local_responded")throw new Error(result?.reason||"O dispositivo não respondeu na LAN.");
    const savedConfig=await readGatewayHardwareIntegrationConfig();
    state.tuyaDevices=normalizeTuyaInventory(savedConfig.tuya?.devices||state.tuyaDevices);
    try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* The confirmed status is saved by the Gateway; refresh Devices on the next view. */}
    const live=Array.isArray(result.status)?result.status:[],observed=new Map();for(const item of live){const id=Number(item?.dps_id??item?.dp_id??item?.dpId??(/^dps_\d+$/.test(String(item?.code||""))?String(item.code).slice(4):NaN));if(Number.isInteger(id)&&id>0)observed.set(id,item);}
    const suggestions=new Map();for(const item of [...(device.dps_knowledge?.dps||[]),...(device.product_profile?.dps||[])]){const id=Number(item?.dps_id);if(Number.isInteger(id)&&id>0&&!suggestions.has(id))suggestions.set(id,item);}
    for(const item of [...(device.functions||[]),...(device.status_spec||[])]){const id=Number(item?.dp_id??item?.dpId);if(Number.isInteger(id)&&id>0&&!suggestions.has(id))suggestions.set(id,{dps_id:id,display_name:item.name||item.code||"Por identificar",semantic_code:item.code||"unknown"});}
    const ids=[...new Set([...observed.keys(),...suggestions.keys()])].sort((a,b)=>a-b);
    if(!ids.length){container.innerHTML='<p class="field-note">A leitura respondeu, mas não forneceu DPS identificáveis.</p>';return;}
    const draw=()=>{container.innerHTML=ids.map(id=>{const item=observed.get(id),suggestion=suggestions.get(id)||{},mapped=(device.dps_knowledge?.dps||[]).find(row=>Number(row.dps_id)===id),label=mapped?.display_name||suggestion.display_name||`DPS ${id} · Por identificar`,value=item?`Valor bruto: ${JSON.stringify(item.value)}`:"Não devolvido nesta leitura";return `<article class="tuya-dps-row"><strong>DPS ${id}</strong><button type="button" class="tuya-dps-description" data-dps-description="${id}" aria-label="Duplo clique para editar o mapa de ${esc(label)}">${esc(label)} <small>duplo clique para atribuir característica</small></button><span>${esc(value)}</span></article>`;}).join("");for(const button of container.querySelectorAll("[data-dps-description]")){let lastTap=0;button.addEventListener("click",()=>{const now=Date.now();if(now-lastTap<480){lastTap=0;const id=Number(button.dataset.dpsDescription),row=(device.dps_knowledge?.dps||[]).find(item=>Number(item.dps_id)===id),suggestion=suggestions.get(id);openTuyaDpsDescriptionEditor(device,id,row?.display_name||suggestion?.display_name||`DPS ${id}`,result=>{if(row){row.display_name=result.description;row.semantic_code=result.semantic_code;row.unit=result.unit||null;row.scale=result.scale??row.scale;row.confidence="OWNER_CUSTOM";}draw();},{semantic_code:row?.semantic_code||suggestion?.semantic_code,unit:row?.unit||suggestion?.unit,scale:row?.scale??suggestion?.scale??1});}else lastTap=now;});}};
    for(const item of live){const id=Number(item?.dps_id??item?.dp_id??item?.dpId??(/^dps_\d+$/.test(String(item?.code||""))?String(item.code).slice(4):NaN)),row=(device.dps_knowledge?.dps||[]).find(entry=>Number(entry.dps_id)===id);if(row&&item&&Object.prototype.hasOwnProperty.call(item,"value"))row.raw_value=item.value;}
    draw();
  }catch(error){container.innerHTML=`<p class="field-note">Falha na leitura LAN: ${esc(error.message)}</p><button type="button" class="button secondary" data-tuya-dps-retry>Tentar novamente</button>`;container.querySelector("[data-tuya-dps-retry]")?.addEventListener("click",()=>{container.dataset.loading="false";loadTuyaDpsSnapshot(device,container);});}
  finally{container.dataset.loading="false";}
}
function renderTuyaDeviceCards(devices) {
  const list=$("#tuya-device-list");
  if(!list)return;
  const isConfirmed=device=>device.local_verified===true||tuyaReadingConfirmed((state.tuyaReadings||[]).find(item=>item.device_id===device.device_id));
  const ordered=[...devices].sort((a,b)=>Number(isConfirmed(b))-Number(isConfirmed(a)));
  list.innerHTML=ordered.length?ordered.map(device=>{
    const reading=(state.tuyaReadings||[]).find(item=>item.device_id===device.device_id),liveConfirmed=tuyaReadingConfirmed(reading),confirmed=device.local_verified===true||liveConfirmed,metrics=tuyaSimpleReadings(device,reading),savedConfirmation=confirmed&&!liveConfirmed;
    const metricHtml=metrics.map(item=>'<span class="tuya-simple-metric"><small>'+esc(item.label)+'</small><strong>'+esc(item.value)+'</strong></span>').join('');
    const switches=device.switch_code?'<button type="button" class="button secondary" data-tuya-switch="on" data-device-id="'+esc(device.device_id)+'">Ligar</button><button type="button" class="button secondary" data-tuya-switch="off" data-device-id="'+esc(device.device_id)+'">Desligar</button>':'';
    return '<article class="tuya-device-card" data-tuya-device="'+esc(device.device_id)+'" tabindex="0" aria-label="'+esc(device.name)+', '+(confirmed?'ligação validada':'por confirmar')+'"><div class="tuya-device-card-heading"><h4><span class="tuya-device-glyph" aria-hidden="true">'+tuyaDeviceGlyph(device)+'</span> '+esc(device.name)+'</h4><span class="tuya-read-state '+(confirmed?'confirmed':'pending')+'">'+(confirmed?'Confirmado':'Por confirmar')+'</span></div><p class="field-note">'+esc(savedConfirmation?'Ligação local validada anteriormente · à espera da próxima leitura':tuyaDeviceState(device,reading))+'</p>'+(metricHtml?'<div class="tuya-simple-metrics">'+metricHtml+'</div>':'')+'<div class="dialog-actions"><button type="button" class="button secondary" data-edit-tuya-device="'+esc(device.device_id)+'">Configurar</button><button type="button" class="button secondary" data-tuya-read="'+esc(device.device_id)+'">Ler agora</button>'+switches+'</div><div class="connection-result" data-tuya-status="'+esc(device.device_id)+'" role="status" aria-live="polite">'+(reading?.reason?esc(tuyaLanReasonText(reading.reason)):liveConfirmed?'Leitura LAN válida':savedConfirmation?'Confirmação guardada no Gateway':'Guarda IP/MAC para testar a ligação')+'</div></article>';
  }).join(''):'<p class="field-note">Ainda não há dispositivos Tuya configurados.</p>';
}
function openTuyaDeviceEditor(device){
  if(sessionInfo().user?.role!=="owner")return;
  const channels=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase()));
  const allFunctions=Array.isArray(device.functions)?device.functions:[],statuses=Array.isArray(device.status_spec)?device.status_spec:[];
  const isGatewayChild=device.transport==="tuya_gateway"&&typeof device.parent_device_id==="string";
  const glyph=tuyaDeviceGlyph(device);
  const localLabel= item=>tuyaFriendlyCapabilityLabel(item,device);
  const multiSwitch=Number(device.channel_count)>1||device.device_kind==="multi_switch"||(device.switch_channels||[]).length>1||device.functions?.filter(item=>/^switch_[1-9]\d*$/i.test(String(item?.code||""))&&["bool","boolean"].includes(String(item?.type||"").toLowerCase())).length>1;
  const kgStandard="".concat(String(device.category||"").toLowerCase()).replace(/[^a-z0-9]/g,"")==="kg",defaultDps=item=>device.local_dps_map?.[item.code]||item.dp_id||item.dpId||(kgStandard&&/^switch_([1-6])$/.test(item.code)?item.code.match(/^switch_([1-6])$/)[1]:!multiSwitch&&/^switch_(\d+)$/.test(item.code)?item.code.match(/^switch_(\d+)$/)[1]:!multiSwitch&&item.code==="switch"?"1":"");
  const channelRows=channels.map((item,index)=>`<label class="tuya-channel-edit"><span><strong>${esc(localLabel(item)||`Canal ${index+1}`)}</strong><small>${esc(item.code)} · ${esc(item.type||"interruptor")}${item.dp_id||item.dpId?` · DPS Tuya ${esc(item.dp_id||item.dpId)}`:""}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item)||`Canal ${index+1}`)}" aria-label="Nome do canal ${esc(index+1)}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(defaultDps(item))}" aria-label="DPS local do canal ${esc(index+1)}" placeholder="DPS"></label>`).join("");
  const capabilityRows=allFunctions.filter(item=>!channels.includes(item)).map(item=>`<label class="tuya-capability-row"><span><strong>${esc(item.name||item.code||"Função")}</strong><small>${esc(item.code||"")} · ${esc(item.type||"tipo desconhecido")} · ${esc(typeof item.values==="string"?item.values:JSON.stringify(item.values??{}))}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item))}" aria-label="Nome local da característica ${esc(item.name||item.code||"")}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(device.local_dps_map?.[item.code]||"")}" aria-label="DPS local de ${esc(item.name||item.code||"")}" placeholder="DPS"></label>`).join("");
  const statusRows=statuses.map(item=>`<label class="tuya-capability-row"><span><strong>${esc(item.name||item.code||"Leitura")}</strong><small>${esc(item.code||"")} · ${esc(item.type||"tipo desconhecido")}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item))}" aria-label="Nome local da leitura ${esc(item.name||item.code||"")}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(device.local_dps_map?.[item.code]||"")}" aria-label="DPS local da leitura ${esc(item.name||item.code||"")}" placeholder="DPS"></label>`).join("");
  const categoryReference=[...(Array.isArray(device.category_functions)?device.category_functions.map(item=>({...item,kind:"Função"})):[]),...(Array.isArray(device.category_status_spec)?device.category_status_spec.map(item=>({...item,kind:"Estado"})):[])].map(item=>`<div class="tuya-capability-row"><span><strong>${esc(item.name||item.code||item.kind)}</strong><small>${esc(item.kind)} de referência · ${esc(item.code||"")} · ${esc(item.type||"tipo desconhecido")}</small></span></div>`).join("");
  const dpsKnowledge=device.dps_knowledge||{},dpsKnowledgeRows=(dpsKnowledge.dps||[]).map(item=>`<div class="tuya-capability-row"><span><strong>DPS ${esc(item.dps_id)} · ${esc(item.display_name)}</strong><small>${esc(item.semantic_code)} · ${esc(item.data_type)} · ${esc(item.unit||"sem unidade")} · escala ${esc(item.scale??"desconhecida")} · ${esc(item.confidence)} · ${esc(item.source||"sem fonte")}</small></span><span>${item.raw_value===undefined?"Sem valor actual":"Bruto: "+esc(JSON.stringify(item.raw_value))}</span></div>`).join("");

  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-device-editor";
  dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">${glyph} · ${esc(device.product_name_pt||device.product_name||device.product||device.model||"Tuya")}</p><h2>${esc(device.name)}</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></form><form class="dialog-body" id="tuya-device-edit-form"><p class="field-note">Os nomes, o endereço, o MAC, o protocolo e o mapa DPS ficam guardados no Gateway. A descoberta tenta cruzar o ID Tuya ou o MAC com a rede local. Se não encontrar o endereço, podes indicar o IP privado manualmente. A cloud só é usada quando pedes sincronização do inventário.</p><div class="device-detail-grid"><div class="detail-item"><small>Tipo Tuya</small><strong>${esc(device.product_name_pt||device.product_name||device.product||device.model||"Produto sem nome na cloud")}</strong></div><div class="detail-item"><small>Tipo de equipamento</small><strong>${esc(device.device_kind_label||"Equipamento Tuya")}</strong></div><div class="detail-item"><small>Canais digitais</small><strong>${channels.length||device.channel_count||0}</strong></div><div class="detail-item"><small>Estado do controlo local</small><strong>${esc(device.local_control_state||"Por verificar")}</strong></div><div class="detail-item"><small>Ligação local</small><strong>${isGatewayChild?"Através do painel associado":device.local_key_available?"Disponível no Gateway":"Por configurar"}</strong></div></div><label>Nome do dispositivo<input name="name" maxlength="120" required value="${esc(device.name)}"></label><div class="ws-config-grid"><label>Piso<input name="floor" maxlength="120" value="${esc(device.floor||"")}" placeholder="Ex.: Rés-do-chão"></label><label>Divisão<input name="room" maxlength="120" value="${esc(device.room||"")}" placeholder="Ex.: Luzes canteiros frente"></label></div><div class="ws-config-grid"><label>MAC local<input name="local_mac" maxlength="17" value="${esc(device.local_mac||"")}" placeholder="AA:BB:CC:11:22:33" autocapitalize="characters" spellcheck="false"></label><label>IP local<input name="local_ip" maxlength="64" value="${esc(device.local_ip||"")}" placeholder="192.168.1.20" inputmode="decimal"></label></div><label>Protocolo Tuya LAN<select name="local_protocol">${["3.1","3.2","3.3","3.4","3.5"].map(value=>`<option value="${value}" ${(device.local_protocol||"3.3")===value?"selected":""}>${value}</option>`).join("")}</select></label><h3>Dispositivo e canal Tuya</h3>${channels.length?`<p class="field-note">Em switches multicanal, o número no nome do código (switch_1, switch_2…) não garante o número DPS. O Gateway usa o ID fornecido pelo esquema ou o mapa local guardado; sem esse mapeamento, bloqueia o comando em vez de enviar ao canal errado.</p><div class="tuya-channel-list">${channelRows}</div>`:`<p class="field-note">A Tuya não indicou canais digitais para este equipamento.</p>`}${dpsKnowledgeRows?`<h3>Mapa DPS do produto Tuya</h3><p class="field-note">O mapa DPS é partilhado por todos os equipamentos com este Product ID.</p><div class="tuya-capability-list">${dpsKnowledgeRows}</div>`:""}<h3>Lista DPS</h3><p class="field-note">Os valores são lidos pela LAN apenas quando abres esta aba. Toca duas vezes numa descrição para editar o mapa partilhado por este Product ID.</p><div class="tuya-dps-snapshot" data-tuya-dps-snapshot aria-live="polite">Abre esta aba para pedir uma leitura DPS ao Gateway.</div><h3>Outras funções recebidas</h3><div class="tuya-capability-list">${capabilityRows||`<p class="field-note">Sem outras funções no esquema recebido.</p>`}</div><h3>Leituras recebidas</h3><div class="tuya-capability-list">${statusRows||`<p class="field-note">Sem leituras no esquema recebido.</p>`}</div><h3>Registo do dispositivo</h3><p class="field-note">Mostra alterações ON/OFF, disponibilidade na LAN, comandos e ações automáticas. O registo começa quando esta versão faz as primeiras leituras; a hora depende do intervalo de leitura. Ainda não há alarmes de limite de watts configuráveis neste ecrã.</p><button type="button" class="button secondary" data-tuya-events="${esc(device.device_id)}">Abrir registo</button><div class="tuya-event-list" data-tuya-event-list="${esc(device.device_id)}" aria-live="polite">Carrega em “Abrir registo” para consultar os eventos guardados.</div><p class="connection-result" id="tuya-device-edit-status" role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-tuya-editor-cancel>Cancelar</button><button type="submit" class="button primary">Guardar no Gateway</button></div></form>`;
  setupTuyaEditorTabs(dialog);
  const dpsTab=[...dialog.querySelectorAll(".tuya-editor-tab")].find(tab=>tab.textContent.trim()==="Lista DPS");
  dpsTab?.addEventListener("click",()=>loadTuyaDpsSnapshot(device,dialog.querySelector("[data-tuya-dps-snapshot]")));
  const favoriteIds=workspace.prefs.favoriteDeviceIds||[],isFavorite=favoriteIds.includes(device.device_id),favoriteButton=document.createElement("button");
  favoriteButton.type="button";favoriteButton.className="button secondary tuya-favorite-action";favoriteButton.textContent=isFavorite?"Remover dos favoritos":"Adicionar aos favoritos";
  favoriteButton.addEventListener("click",()=>{if(isFavorite)workspace.prefs.favoriteDeviceIds=favoriteIds.filter(id=>id!==device.device_id);else addHomeFavoriteId(device.device_id);saveDemoWorkspace();dialog.close("favorite-updated");render();});
  dialog.querySelector(".dialog-actions").prepend(favoriteButton);
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove());dialog.querySelector("[data-tuya-editor-cancel]").addEventListener("click",()=>dialog.close("cancel"));
  const editorForm=dialog.querySelector("#tuya-device-edit-form");
  if(isGatewayChild){
    editorForm.elements.local_ip.closest(".ws-config-grid").hidden=true;
    editorForm.elements.local_protocol.closest("label").hidden=true;
    const section=document.createElement("section");section.innerHTML=`<h3>Ligado através de ${esc((state.tuyaDevices||[]).find(item=>item.device_id===device.parent_device_id)?.name||"painel Tuya")}</h3><p class="field-note">Este equipamento Zigbee utiliza a ligação local do painel. O SolarMiner guarda apenas a associação comunicada pela Tuya e usa-a nas leituras LAN.</p>`;
    editorForm.insertBefore(section,editorForm.querySelector("#tuya-device-edit-status"));
  }
  const subdeviceSection=document.createElement("section");subdeviceSection.innerHTML=`<h3>Dispositivos ligados ao painel</h3><p class="field-note">Pede à Tuya a lista de equipamentos associados a este painel. Esta operação só importa nomes e associação; não envia comandos aos equipamentos.</p><button type="button" class="button secondary" data-tuya-subdevice-sync>Procurar dispositivos ligados</button><p class="connection-result" data-tuya-subdevice-status role="status" aria-live="polite"></p>`;
  if(!isGatewayChild)editorForm.insertBefore(subdeviceSection,editorForm.querySelector("#tuya-device-edit-status"));
  subdeviceSection.querySelector("[data-tuya-subdevice-sync]").addEventListener("click",async event=>{
    const button=event.currentTarget,status=subdeviceSection.querySelector("[data-tuya-subdevice-status]");button.disabled=true;status.textContent="A consultar a lista de dispositivos ligados na Tuya…";
    try{const result=await syncGatewayTuyaSubdevices(device.device_id);const config=await readGatewayHardwareIntegrationConfig();state.tuyaDevices=normalizeTuyaInventory(config.tuya?.devices||[]);const count=Number(result.device_count)||0,cloudCount=Number(result.cloud_subdevice_count)||0,missingNode=Number(result.node_ids_missing)||0;status.textContent=count?`${count} dispositivo${count===1?"":"s"} associado${count===1?"":"s"} de ${cloudCount} recebido${cloudCount===1?"":"s"} da Tuya. ${missingNode?`${missingNode} sem identificador Zigbee e não associado. `:""}As leituras locais começam na próxima consulta do Gateway.`:cloudCount?`A Tuya devolveu ${cloudCount} dispositivo${cloudCount===1?"":"s"}, mas ${missingNode} não tem node_id utilizável. O inventário anterior foi mantido.`:"A Tuya não devolveu filhos para este painel. O inventário existente foi mantido.";render();}
    catch(error){status.textContent=`Não foi possível consultar os dispositivos ligados: ${error.message}`;}
    finally{button.disabled=false;}
  });
  if(isGatewayChild)editorForm.addEventListener("submit",async event=>{event.preventDefault();event.stopImmediatePropagation();const save=editorForm.querySelector('[type="submit"]'),status=editorForm.querySelector("#tuya-device-edit-status");save.disabled=true;status.textContent="A guardar os dados do dispositivo no Gateway…";try{const config=await readGatewayHardwareIntegrationConfig(),name=editorForm.elements.name.value.trim(),labels={},dpsMap={};for(const input of editorForm.querySelectorAll("[data-tuya-capability-label]"))labels[input.dataset.tuyaCapabilityLabel]=input.value.trim();for(const input of editorForm.querySelectorAll("[data-tuya-dps]"))if(input.value.trim())dpsMap[input.dataset.tuyaDps]=input.value.trim();const devices=(config.tuya?.devices||[]).map(item=>item.device_id===device.device_id?{...item,name,name_source:"local",local_name:name,room:editorForm.elements.room.value.trim(),floor:editorForm.elements.floor.value.trim(),local_dps_map:dpsMap,capability_labels:labels,channel_labels:Object.fromEntries(channels.map(channel=>[channel.code,labels[channel.code]||""]))}:item);const saved=await saveGatewayHardwareIntegrationConfig({tuya:{devices}});state.tuyaDevices=normalizeTuyaInventory(saved.tuya?.devices||devices);status.textContent="Nome, divisão e mapa DPS guardados. A ligação local continua a usar o painel associado.";dialog.close("saved");render();}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;save.disabled=false;}});
  editorForm.addEventListener("submit",async event=>{
    event.preventDefault();const form=event.currentTarget,save=form.querySelector('[type="submit"]'),status=form.querySelector("#tuya-device-edit-status");let requestedIp=form.elements.local_ip.value.trim(),requestedMac=form.elements.local_mac.value.trim().toUpperCase();if(!requestedIp&&!requestedMac){status.textContent="Indica o IP ou o MAC local para identificar o equipamento na rede.";return;}const compactRequestedMac=String(requestedMac||"").replace(/[^0-9a-f]/gi,"").toUpperCase();if(requestedMac&&compactRequestedMac.length!==12){status.textContent="O MAC local tem de conter 12 dígitos hexadecimais.";return;}if(requestedMac)requestedMac=compactRequestedMac.match(/.{2}/g).join(":");const previouslyVerified=device.local_verified===true&&requestedIp===String(device.local_ip||"").trim()&&requestedMac===String(device.local_mac||"").trim().toUpperCase();save.disabled=true;status.textContent=requestedIp&&requestedMac?"A guardar IP e MAC já indicados…":"A procurar na rede o dado em falta…";
    let saved,schemaInfo={queried:false,found:Boolean(device.functions?.length||device.status_spec?.length)};
    try{
      if(!requestedIp||!requestedMac){
        const scan=await scanGatewayLocalNetwork();
        const compactMac=value=>String(value||"").replace(/[^0-9a-f]/gi,"").toUpperCase();
        const matches=(scan.hosts||[]).filter(host=>(requestedMac&&compactMac(host.mac)===compactMac(requestedMac))||(requestedIp&&String(host.ip||"").trim()===requestedIp));
        const candidateIps=new Set(matches.flatMap(host=>[host.ip,...(host.ip_candidates||[])].filter(Boolean)));
        const candidateMacs=new Set(matches.map(host=>compactMac(host.mac)).filter(value=>value.length===12));
        if(matches.some(host=>host.mac_ip_conflict)||candidateIps.size>1||candidateMacs.size>1)throw new Error("O Gateway encontrou mais de uma correspondência possível; não escolheu IP nem MAC.");
        if(candidateIps.size!==1||candidateMacs.size!==1)throw new Error("O Gateway não encontrou na rede o IP ou MAC em falta.");
        if(requestedIp&&candidateIps.has(requestedIp)===false)throw new Error("O IP indicado não corresponde ao MAC encontrado na rede.");
        if(requestedMac&&[...candidateMacs][0]!==compactMac(requestedMac))throw new Error("O MAC indicado não corresponde ao IP encontrado na rede.");
        requestedIp=[...candidateIps][0];requestedMac=[...candidateMacs][0].match(/.{2}/g).join(":");
        form.elements.local_ip.value=requestedIp;form.elements.local_mac.value=requestedMac;
      }
      status.textContent="MAC localizado; a guardar o IP encontrado e a configuração no Gateway…";
      const config=await readGatewayHardwareIntegrationConfig(),labels={},dpsMap={};
      for(const input of form.querySelectorAll("[data-tuya-capability-label]"))labels[input.dataset.tuyaCapabilityLabel]=input.value.trim();
      for(const input of form.querySelectorAll("[data-tuya-dps]"))if(input.value.trim())dpsMap[input.dataset.tuyaDps]=input.value.trim();
      const next=(config.tuya?.devices||[]).map(item=>item.device_id===device.device_id?{...item,name:form.elements.name.value.trim(),name_source:"local",room:form.elements.room.value.trim(),floor:form.elements.floor.value.trim(),local_ip:requestedIp,local_mac:requestedMac,local_protocol:form.elements.local_protocol.value,local_dps_map:dpsMap,channel_labels:Object.fromEntries(channels.map(channel=>[channel.code,labels[channel.code]||""])),capability_labels:labels}:item);
      if(!next.some(item=>item.device_id===device.device_id))throw new Error("O dispositivo deixou de constar na configuração do Gateway.");
      saved=await saveGatewayHardwareIntegrationConfig({tuya:{devices:next}});
      const persisted=(saved.tuya?.devices||[]).find(item=>item.device_id===device.device_id);
      if(!persisted||String(persisted.local_mac||"").trim().toUpperCase()!==requestedMac)throw new Error("O Gateway não confirmou o MAC local deste dispositivo.");
      if(requestedIp&&String(persisted.local_ip||"").trim()!==requestedIp)throw new Error("O Gateway não confirmou o IP/MAC local deste dispositivo.");
      if(!schemaInfo.found&&!previouslyVerified){try{schemaInfo=await refreshTuyaSchemaIfNeeded(device.device_id,saved);}catch(error){schemaInfo={queried:true,found:false,error};}}
    }catch(error){status.textContent=`Falha ao guardar no Gateway: ${error.message}`;save.disabled=false;return;}
    if(previouslyVerified){
      state.tuyaDevices=normalizeTuyaInventory(saved.tuya?.devices||state.tuyaDevices);
      try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* The saved edit is retained; the inventory refreshes on the next view. */}
      status.textContent="Alterações guardadas. A ligação local já estava confirmada; não repeti os testes.";dialog.close("saved");render();return;
    }
    status.textContent="Configuração guardada. A confirmar leitura DPS autenticada na LAN…";
    try{
      if(!schemaInfo.queried)state.tuyaDevices=normalizeTuyaInventory(saved.tuya?.devices||state.tuyaDevices);
      const confirmed=state.tuyaDevices.find(item=>item.device_id===device.device_id),requestedIp=form.elements.local_ip.value.trim(),requestedMac=form.elements.local_mac.value.trim().toUpperCase();
      if(!confirmed||String(confirmed.local_ip||"").trim()!==requestedIp||String(confirmed.local_mac||"").trim().toUpperCase()!==requestedMac)throw new Error("O Gateway guardou a configuração, mas a lista atualizada ainda não confirmou IP e MAC.");
      const report=await runGatewayTuyaLanDiagnostics(1,device.device_id),result=(report.devices||[]).find(item=>item?.device_id===device.device_id),reading=result||null;
      if(reading)state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==device.device_id),reading];
      if(!reading||reading.connection_state!=="local_responded"||!Array.isArray(reading.status)||!reading.status.length){status.textContent=`IP e MAC guardados, mas sem leitura DPS local autenticada; o equipamento continua por confirmar. ${tuyaLanReasonText(reading?.reason||"tuya_lan_status_unavailable")}`;save.disabled=false;return;}
      const confirmedConfig=await readGatewayHardwareIntegrationConfig();state.tuyaDevices=normalizeTuyaInventory(confirmedConfig.tuya?.devices||state.tuyaDevices);
      try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* Gateway confirmation is persisted; next Devices refresh reloads inventory. */}
      const schemaNote=schemaInfo.queried?(schemaInfo.found?" Esquema DPS e funções atualizado a partir da Tuya.":" A Tuya não devolveu o esquema DPS deste equipamento."):" Esquema DPS existente mantido.";
      status.textContent=`Configuração guardada. Leitura DPS local confirmada (${reading.status.length} estados); equipamento confirmado.${schemaNote}`;dialog.close("saved");render();
    }catch(error){status.textContent=`Configuração guardada, mas o teste de resposta LAN falhou: ${error.message}`;save.disabled=false;}
  });
  dialog.showModal();
}
function setProviderResult(provider, result) {
  const payload = result[provider];
  const output = $(`#${provider}-result`), status = $(`#${provider}-status`);
  if (output) { output.textContent = JSON.stringify(payload ?? result, null, 2); output.hidden = false; }
  if (status) {
    const rawState = payload?.connection_state || (provider === "tuya" && payload?.length ? "api_responded" : "failed");
    const stateText = provider === "antminer" && rawState === "api_responded" ? "ligação de leitura ativa" : rawState;
    const reason = payload?.reason ? ` · ${payload.reason}` : "";
    const metricText = provider === "deye" && payload?.metrics ? ` · ${payload.metrics.length} leituras recebidas; não validadas pelo fabricante` : "";
    let minerText = provider === "antminer" && payload?.responses ? " · telemetria em leitura; comandos disponíveis pela API Braiins OS separada" : "";
    if(provider==="antminer"&&payload?.connection_state==="api_responded"){
      const data=payload.data||{},summaryRows=data.summary?.SUMMARY,tunerRows=data.tunerstatus?.TUNERSTATUS;
      const summary=Array.isArray(summaryRows)?summaryRows.find(row=>row&&typeof row==="object")||{}:{};
      const tuner=Array.isArray(tunerRows)?tunerRows.find(row=>row&&typeof row==="object")||{}:{};
      let hash=Number(summary["GHS 5s"]);if(!Number.isFinite(hash)){const mhs=Number(summary["MHS 5s"]);hash=Number.isFinite(mhs)?mhs/1000:Number(summary["GHS av"]);}
      const hashObserved=Number.isFinite(hash)&&hash>=0,hashRate=hashObserved?new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(hash/1000)+" TH/s":"hashrate não reportado",miningState=hashObserved?(hash>0?"hashing reportado":"hashrate zero; ligado mas sem hashing reportado"):"hashrate não reportado";
      const watts=Number(tuner.ApproximateMinerPowerConsumption),power=Number.isFinite(watts)&&watts>=0?" · potência reportada "+new Intl.NumberFormat("pt-PT",{maximumFractionDigits:0}).format(watts)+" W":"";
      minerText=" · telemetria confirmada em "+payload.host+":"+payload.port+"; "+miningState+" ("+hashRate+")"+power+"; controlo disponível pela API Braiins OS: iniciar, pausar, parar e definir potência.";
    }
    status.textContent = `${provider === "deye" ? "Deye" : provider === "antminer" ? "Antminer" : "Tuya"}: ${stateText}${reason}${metricText}${minerText}`;
  }
}
function ownerCanManageHardware(statusSelector) {
  const info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") {
    const status = $(statusSelector);
    if (status) status.textContent = "Só o Owner autenticado pode gerir este equipamento.";
    return false;
  }
  return true;
}
async function saveHardwareProvider(provider, payload, button, statusId) {
  if (!ownerCanManageHardware(`#${statusId}`)) return;
  button.disabled = true;
  $(`#${statusId}`).textContent = "A guardar apenas esta configuração no Gateway…";
  try {
    const saved = await saveGatewayHardwareIntegrationConfig({ [provider]: payload });
    if (provider === "antminer") $("#hardware-antminer-password").value = "";
    if (provider === "tuya") $("#hardware-tuya-client-secret").value = "";
    $(`#${statusId}`).textContent = provider === "antminer"
      ? `Antminer guardada. Credenciais de controlo ${saved.antminer_control_configured ? "configuradas no Gateway" : "por configurar"}.`
      : provider === "tuya" ? "Configuração Tuya guardada no Gateway; segredo oculto." : "Configuração Deye guardada no Gateway.";
    if (provider === "tuya") await refreshHardwareIntegrationConfig();
  } catch (error) { $(`#${statusId}`).textContent = `Não foi possível guardar: ${error.message}`; }
  finally { button.disabled = false; }
}
function parseTuyaDevices() {
  return $("#hardware-tuya-devices").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
    const [rawId, rawName, rawCode, rawLevelCode, rawLevelMin, rawLevelMax] = line.split("|");
    const device_id = (rawId || "").trim();
    return { device_id, name: (rawName || "").trim() || `Tuya ${device_id}`, ...(rawCode?.trim() ? { switch_code: rawCode.trim() } : {}), ...(rawLevelCode?.trim() ? { level_code: rawLevelCode.trim(), level_min: Number(rawLevelMin?.trim() || 0), level_max: Number(rawLevelMax?.trim() || 100) } : {}) };
  });
}
let tuyaProductImportPreview=null;
function setupTuyaManagementSections(){
  const fieldset=$("#tuya-device-card");if(!fieldset||fieldset.dataset.managementReady)return;fieldset.dataset.managementReady="true";
  const legend=fieldset.querySelector("legend"),nav=document.createElement("nav"),panels=document.createElement("div");nav.className="tuya-editor-tabs tuya-management-tabs";nav.setAttribute("aria-label","Secções Tuya");panels.className="tuya-management-panels";
  const names=[["account","Conta cloud"],["devices","Dispositivos"],["products","Product IDs"],["dps","DPS"]],sections={};
  names.forEach(([key,label],index)=>{const button=document.createElement("button"),section=document.createElement("section");button.type="button";button.className="tuya-editor-tab";button.textContent=label;button.setAttribute("aria-selected",String(index===0));button.dataset.tuyaSection=key;section.className="tuya-editor-panel";section.dataset.tuyaPanel=key;section.hidden=index!==0;sections[key]=section;nav.append(button);panels.append(section);button.addEventListener("click",()=>{nav.querySelectorAll("button").forEach(item=>item.setAttribute("aria-selected",String(item===button)));Object.entries(sections).forEach(([id,panel])=>panel.hidden=id!==key);if(key==="products"||key==="dps")void refreshTuyaProductCatalogViews();});});
  const original=[...fieldset.childNodes].filter(node=>node!==legend);for(const node of original){if(node.nodeType===Node.TEXT_NODE&&!node.textContent.trim())continue;let target="account";
    const id=node.nodeType===Node.ELEMENT_NODE?node.id:"";
    if(node.matches?.("label")){const field=node.htmlFor||"";if(field==="hardware-tuya-devices")target="devices";else if(field.startsWith("hardware-tuya-"))target="account";}
    if(["hardware-tuya-devices","tuya-lan-discovery","tuya-lan-diagnostics","tuya-device-list"].includes(id))target="devices";
    if(id==="tuya-status")target="account";
    if(node.matches?.("p.field-note"))target="devices";
    if(node.matches?.(".dialog-actions")){
      const accountActions=document.createElement("div"),deviceActions=document.createElement("div");accountActions.className=deviceActions.className="dialog-actions";
      for(const button of [...node.querySelectorAll("button")])(button.id==="tuya-save"||button.id==="tuya-sync"?accountActions:deviceActions).append(button);
      if(accountActions.childElementCount)sections.account.append(accountActions);if(deviceActions.childElementCount)sections.devices.append(deviceActions);node.remove();continue;
    }
    sections[target].append(node);
  }
  fieldset.append(nav,panels);
  sections.products.innerHTML=`<p class="field-note">Catálogo local de Product IDs e esquemas DPS, indexados pelo identificador exato. Importar apenas prepara uma comparação; nada é guardado antes de confirmares.</p><div class="dialog-actions"><label class="button secondary" for="tuya-product-file">Carregar documento</label><input id="tuya-product-file" type="file" accept=".json,.csv,.tsv,.html,.htm,.txt,.xlsx,application/json,text/csv,text/html,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden><input id="tuya-product-url" type="url" maxlength="2048" placeholder="https://… documento ou tabela pública"><button id="tuya-product-url-preview" class="button secondary" type="button">Ler URL</button></div><p class="field-note">Formatos suportados: JSON estruturado, CSV/TSV com Product ID e DPS/schema em JSON, tabelas HTML ou primeira folha de Excel (.xlsx). Limite de 2 MB. Conteúdo não reconhecido é rejeitado sem gravação.</p><div id="tuya-product-catalog-list" class="tuya-product-import-list" aria-live="polite">A carregar Product IDs…</div><div id="tuya-product-import-status" class="connection-result" role="status" aria-live="polite"></div><div id="tuya-product-import-preview" class="tuya-product-import-preview"></div>`;
  sections.dps.innerHTML=`<p class="field-note">Mapas DPS associados a Product IDs exatos. Referências importadas ficam identificadas como externas e não habilitam comandos de escrita automaticamente.</p><div id="tuya-product-dps-list" class="tuya-product-import-list" aria-live="polite">A carregar mapas DPS…</div>`;
  $("#tuya-product-file").addEventListener("change",async event=>{const file=event.currentTarget.files?.[0];event.currentTarget.value="";if(!file)return;if(file.size>2_000_000){$("#tuya-product-import-status").textContent="O documento excede 2 MB; não foi enviado.";return;}try{if(file.name.toLowerCase().endsWith(".xlsx")){const bytes=new Uint8Array(await file.arrayBuffer());let binary="";for(let offset=0;offset<bytes.length;offset+=0x8000)binary+=String.fromCharCode(...bytes.subarray(offset,offset+0x8000));await previewTuyaProductImport({content_base64:btoa(binary),filename:file.name});}else{const content=await file.text();await previewTuyaProductImport({content,filename:file.name});}}catch(error){$("#tuya-product-import-status").textContent=`Não foi possível analisar o documento: ${error.message}`;}});
  $("#tuya-product-url-preview").addEventListener("click",async event=>{const button=event.currentTarget,url=$("#tuya-product-url").value.trim();if(!url){$("#tuya-product-import-status").textContent="Indica primeiro um URL público.";return;}button.disabled=true;try{await previewTuyaProductImport({url});}catch(error){$("#tuya-product-import-status").textContent=`Não foi possível ler o URL: ${error.message}`;}finally{button.disabled=false;}});
  void refreshTuyaProductCatalogViews();
}
async function refreshTuyaProductCatalogViews(){
  const list=$("#tuya-product-catalog-list"),dpsList=$("#tuya-product-dps-list");if(!list||!dpsList)return;
  try{const [config,known]=await Promise.all([readGatewayHardwareIntegrationConfig(),readGatewaySmartProductCatalog()]),catalog=config.tuya?.product_catalog||{},products=new Map(Object.entries(catalog));state.smartProductCatalog=known.tuya_profiles||[];for(const canonical of known.tuya_profiles||[]){const id=canonical.product_id;if(!id)continue;const previous=products.get(id)||{};products.set(id,{...previous,...canonical,dps_profile:{...(previous.dps_profile||{}),dps:canonical.dps||[]},functions:canonical.functions?.length?canonical.functions:(previous.functions||[]),status_spec:canonical.status_spec?.length?canonical.status_spec:(previous.status_spec||[])});}for(const item of known.products||[]){if(item.protocol!=="tuya"||!item.product_code)continue;if(!products.has(item.product_code))products.set(item.product_code,{product_name:item.product_name||"",category:item.device_kind||"",device_kind:item.device_kind||"unknown",schema_source:item.source||"registado no inventário",functions:[],status_spec:[],dps_profile:{dps:[]}});}for(const [id,profile] of products){const device=state.tuyaDevices.find(item=>item.product_id===id);if(device){profile.product_name_pt=device.product_name_pt||profile.product_name_pt||"";profile.cloud_product=device.product||profile.cloud_product||"";profile.category=device.category||profile.category||"";profile.device_kind=device.device_kind||profile.device_kind||"unknown";profile.sample_device_id=device.device_id;}}const entries=[...products.entries()].sort(([a],[b])=>a.localeCompare(b));
    list.innerHTML=entries.length?`<p class="field-note">Duplo clique num produto para editar o nome apresentado, a classificação funcional e o mapa DPS. O mapa é partilhado por todos os equipamentos com o mesmo Product ID. Capacidades cloud sem número DPS aparecem separadas no menu DPS e não contam como IDs numéricos observados.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Product ID</th><th>Product Tuya / nome apresentado</th><th>DPS numéricos · capacidades cloud</th><th>Fonte</th></tr></thead><tbody>${entries.map(([id,profile])=>{const count=new Set([...(profile.functions||[]),...(profile.status_spec||[]),...(profile.dps||[]),...(profile.dps_profile?.dps||[]),...(profile.dps_profile?.reference_dps||[])].map(row=>Number(row.dp_id??row.dpId??row.dps_id??row.id)).filter(Number.isInteger)).size,capabilities=(profile.functions||[]).length+(profile.status_spec||[]).length;return `<tr data-tuya-product-edit="${esc(id)}" tabindex="0" title="Duplo clique para editar produto e mapa DPS"><th>${esc(id)}</th><td>${esc(profile.product_name_pt||profile.product_name||profile.cloud_product||"Não identificado")}${profile.cloud_product?`<small class="field-note">Cloud: ${esc(profile.cloud_product)}</small>`:""}</td><td>${count} · ${capabilities}</td><td>${esc(profile.schema_source||"guardado no Gateway")}</td></tr>`;}).join("")}</tbody></table></div>`:"<p class=\"field-note\">Ainda não há Product IDs registados. A sincronização Tuya ou uma importação aprovada pode acrescentá-los.</p>";
    list.ondblclick=event=>{const row=event.target.closest("[data-tuya-product-edit]");if(!row)return;const entry=products.get(row.dataset.tuyaProductEdit);if(entry)openTuyaProductMetadataEditor(row.dataset.tuyaProductEdit,entry);};
    dpsList.innerHTML=entries.length?entries.map(([id,profile])=>{const rows=tuyaPidRows(profile),cloudRows=tuyaPidCloudCapabilities(profile,rows);return `<details class="tuya-product-dps-item"><summary>${esc(profile.product_name_pt||profile.product_name||id)} · ${esc(id)} · ${rows.length} DPS mapeados · ${cloudRows.length} códigos cloud por associar <button type="button" class="button secondary" data-tuya-pid-read="${esc(id)}">Ler num equipamento</button><button type="button" class="button secondary" data-tuya-pid-edit="${esc(id)}">Editar mapa DPS</button></summary><p class="field-note">As funções da cloud são ordens; os estados da cloud são leituras. Os códigos cloud são guardados aqui mesmo quando ainda não têm número DPS. Lê um equipamento online deste PID para descobrir os IDs e associá-los às funções/estados no mapa central.</p>${cloudRows.length?`<h3>Capacidades recebidas da cloud · ainda sem ID numérico</h3><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Uso</th><th>Código Tuya</th><th>Nome em português</th><th>Tipo</th><th>Valores declarados</th></tr></thead><tbody>${cloudRows.map(row=>`<tr><td>${row.source==="function"?"Ordem · função":"Leitura · estado"}</td><td>${esc(row.code)}</td><td>${esc(row.label)}</td><td>${esc(row.data_type)}</td><td>${esc(row.details||"—")}</td></tr>`).join("")}</tbody></table></div>`:""}<div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Uso</th><th>DPS</th><th>Nome em português / código Tuya</th><th>Tipo</th><th>Unidade</th><th>Detalhes / valores lidos</th></tr></thead><tbody>${rows.map(row=>{const details=tuyaDpsMeaningDetail(row);return `<tr><td>${row.origin==="function"?"Ordem · função":row.origin==="status"?"Leitura · estado":row.origin==="reference"?"Referência externa":"Por classificar"}</td><td>${row.dps_id}</td><td>${esc(row.label_pt)}<small class="field-note">${esc(row.code_pt)}</small></td><td>${esc(row.data_type||row.type||"—")}</td><td>${esc(row.unit||"—")}</td><td>${esc(row.raw_value===undefined?details||"—":`${details?details+" · ":""}Valor lido: ${JSON.stringify(row.raw_value)}`)}</td></tr>`;}).join("")||'<tr><td colspan="6">Ainda sem IDs DPS. Lê um equipamento deste PID para importar os IDs e depois associa-os às funções/estados da cloud.</td></tr>'}</tbody></table></div></details>`;}).join(""):"<p class=\"field-note\">Ainda não há mapas DPS registados.</p>";
    dpsList.onclick=event=>{const readButton=event.target.closest("[data-tuya-pid-read]");if(readButton){const productId=readButton.dataset.tuyaPidRead,profile=products.get(productId);if(profile)openTuyaPidDpsReadDialog(productId,profile);return;}const button=event.target.closest("[data-tuya-pid-edit]");if(!button)return;const productId=button.dataset.tuyaPidEdit,profile=products.get(productId);if(profile)openTuyaPidDpsMapEditor(productId,profile,()=>refreshTuyaProductCatalogViews());};
  }catch(error){list.textContent=dpsList.textContent=`Não foi possível ler o catálogo do Gateway: ${error.message}`;}
}
const TUYA_DPS_PT={"开关":"Interruptor","开关状态":"Estado do interruptor","通断":"Estado do interruptor","电量":"Energia","电压":"Tensão","电流":"Corrente","功率":"Potência","总电量":"Energia total","总功率":"Potência total","亮度":"Brilho","亮度值":"Brilho","色温":"Temperatura da cor","倒计时":"Contagem decrescente","故障告警":"Alarme de falha","漏电保护":"Proteção contra fuga de corrente","过压保护":"Proteção contra sobretensão","欠压保护":"Proteção contra subtensão","过流保护":"Proteção contra sobrecorrente","温度":"Temperatura","湿度":"Humidade","功率因数":"Fator de potência","剩余电量":"Energia restante","剩余容量":"Capacidade restante","电量百分比":"Nível de bateria","电池电量":"Nível de bateria","电池电压":"Tensão da bateria","当前温度":"Temperatura atual","目标温度":"Temperatura definida","设定温度":"Temperatura definida","环境温度":"Temperatura ambiente","工作模式":"Modo de funcionamento","运行模式":"Modo de funcionamento","风速":"Velocidade da ventoinha","风量":"Caudal de ar","风向":"Direção do ar","摆风":"Oscilação","定时":"Temporizador","童锁":"Bloqueio infantil","儿童锁":"Bloqueio infantil","背光":"Retroiluminação","屏幕亮度":"Brilho do ecrã","屏幕":"Ecrã","电源":"Alimentação","电源开关":"Interruptor de alimentação","继电器":"Relé","继电器状态":"Estado do relé","设备状态":"Estado do equipamento","在线状态":"Estado de ligação","网络状态":"Estado da rede","信号强度":"Intensidade do sinal","信号":"Sinal","告警":"Alarme","报警":"Alarme","故障":"Falha","保护":"Proteção","过载保护":"Proteção contra sobrecarga","短路保护":"Proteção contra curto-circuito","功率限制":"Limite de potência","电量清零":"Repor energia","复位":"Repor","重置":"Repor","校准":"Calibração","单位":"Unidade","模式":"Modo","状态":"Estado","开":"Ligado","关":"Desligado","启用":"Ativado","禁用":"Desativado","打开":"Abrir","关闭":"Fechar","高":"Alto","中":"Médio","低":"Baixo","自动":"Automático","手动":"Manual","制冷":"Arrefecimento","制热":"Aquecimento","除湿":"Desumidificação","送风":"Ventilação","舒适":"Conforto","节能":"Poupança de energia","白色":"Branco","彩色":"Cor","颜色":"Cor","红色":"Vermelho","绿色":"Verde","蓝色":"Azul","场景":"Cena","通道":"Canal","方向":"Direção","计量":"Medição","累计":"Acumulado","今日":"Hoje","昨日":"Ontem","电价":"Tarifa de energia","上限":"Limite máximo","下限":"Limite mínimo","最大":"Máximo","最小":"Mínimo","时间":"Tempo","日期":"Data","分钟":"Minutos","小时":"Horas","秒":"Segundos","百分比":"Percentagem","数值":"Valor","参数":"Parâmetro"};
const TUYA_DPS_CODE_PT={switch_led:"Interruptor",switch:"Interruptor",switch_1:"Interruptor do canal 1",switch_2:"Interruptor do canal 2",switch_3:"Interruptor do canal 3",cur_voltage:"Tensão",cur_current:"Corrente",cur_power:"Potência",add_ele:"Energia acumulada",total_forward_energy:"Energia total",bright_value:"Brilho",bright_value_v2:"Brilho",temp_value:"Temperatura da cor",countdown:"Contagem decrescente",countdown_1:"Contagem decrescente",fault:"Falha",relay_status:"Estado do relé",child_lock:"Bloqueio infantil",overcharge_switch:"Proteção contra sobrecarga",battery_percentage:"Nível de bateria",battery_state:"Estado da bateria",temperature:"Temperatura",humidity:"Humidade",voltage:"Tensão",current:"Corrente",power:"Potência",energy:"Energia",energy_total:"Energia total",energy_today:"Consumo diário",power_factor:"Fator de potência",work_mode:"Modo de funcionamento",mode:"Modo",state:"Estado",switch_type:"Tipo de interruptor",backlight:"Retroiluminação",brightness:"Brilho",color_temperature:"Temperatura da cor",temperature_set:"Temperatura definida",target_temperature:"Temperatura definida",local_temperature:"Temperatura ambiente",fan_speed:"Velocidade da ventoinha",wind_speed:"Velocidade do ar",timer:"Temporizador",countdown_time:"Contagem decrescente",overcurrent:"Proteção contra sobrecorrente",overvoltage:"Proteção contra sobretensão",undervoltage:"Proteção contra subtensão",leakage_current:"Corrente de fuga",alarm:"Alarme",alarm_set_1:"Alarme",alarm_set_2:"Alarme",online_state:"Estado online",light_mode:"Modo da luz",cycle_time:"Temporizador",fault_code:"Código de falha",signal_strength:"Intensidade do sinal",linkquality:"Qualidade da ligação"};
const TUYA_DPS_HAN_PARTS=Object.entries(TUYA_DPS_PT).sort((a,b)=>b[0].length-a[0].length);
function tuyaDpsPt(row,id){const code=String(row.code||row.function_code||row.name||"").trim().toLowerCase(),raw=String(row.label_pt||row.display_name||row.description||row.name||row.code||"").trim();if(row.label_pt&&!/[\u3400-\u9fff]/.test(row.label_pt))return row.label_pt;if(TUYA_DPS_CODE_PT[code])return TUYA_DPS_CODE_PT[code];if(raw&&/[\u3400-\u9fff]/.test(raw)){let rest=raw,parts=[];for(const [han,pt] of TUYA_DPS_HAN_PARTS){if(rest.includes(han)){parts.push(pt);rest=rest.split(han).join(" ");}}if(parts.length)return [...new Set(parts)].join(" · ");return `Ponto de dados ${id}`;}return raw||TUYA_DPS_CODE_PT[code]||`Ponto de dados ${id}`;}
function tuyaDpsCodePt(value,id){const raw=String(value||"").trim();if(!raw)return `Código do ponto ${id}`;if(/[\u3400-\u9fff]/.test(raw))return `Código Tuya · ${tuyaDpsPt({name:raw},id)}`;const normalized=raw.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"");return TUYA_DPS_CODE_PT[normalized]||raw;}
function tuyaPidRows(profile){const rows=[...(profile.functions||[]).map(row=>({...row,origin:"function"})),...(profile.status_spec||[]).map(row=>({...row,origin:"status"})),...(profile.dps||[]),...(profile.dps_profile?.dps||[]),...(profile.dps_profile?.reference_dps||[])],byId=new Map();for(const row of rows){const id=Number(row.dps_id??row.dp_id??row.dpId??row.id);if(!Number.isInteger(id)||id<1||id>65535)continue;const previous=byId.get(id)||{...row,dps_id:id},declared=row.source_kind||row.source,origin=["function","status","unknown"].includes(declared)?declared:["function","status","reference"].includes(row.origin)?row.origin:previous.origin||"unknown";byId.set(id,{...previous,...row,dps_id:id,origin});}return [...byId.values()].sort((a,b)=>a.dps_id-b.dps_id).map(row=>({...row,label_pt:tuyaDpsPt(row,row.dps_id),code_pt:tuyaDpsCodePt(row.function_code||row.code||row.name,row.dps_id),data_type:({boolean:"bool",bool:"bool",numeric:"value",integer:"value",number:"value",value:"value",enum:"enum",enumeration:"enum",fault:"fault",failure:"fault",string:"string",char:"string",raw:"raw"})[String(row.data_type||row.type||"unknown").toLowerCase()]||"unknown"}));}
function tuyaPidCloudCapabilities(profile,mapped){const known=new Set(mapped.map(row=>`${row.origin}:${row.function_code||row.code||""}`)),items=[];for(const [source,list] of [["function",profile.functions||[]],["status",profile.status_spec||[]]])for(const item of list){const code=String(item?.code||"");if(!code||known.has(`${source}:${code}`))continue;items.push({source,code,label:tuyaFriendlyCapabilityLabel(item,{...profile,capability_labels:{}}),data_type:String(item.type||"unknown"),details:typeof item.values==="string"?item.values:JSON.stringify(item.values||{}),read_supported:source==="status",write_supported:source==="function"});}return items;}
function parseTuyaPidDpsPaste(text,profile,rows){
  const capabilities=[...(profile.functions||[]).map(item=>({...item,_source:"function"})),...(profile.status_spec||[]).map(item=>({...item,_source:"status"}))].filter(item=>item&&typeof item.code==="string"),sourceRows=[];
  const semanticOf=value=>{const text=String(value||"").toLowerCase();for(const [semantic,pattern] of [["voltage",/voltag|tens[aã]o|cur_voltage/],["current",/corrente|amper|cur_current/],["power",/pot[eê]ncia|\bpower\b|cur_power/],["countdown",/count.?down|temporizador|contagem decrescente/],["switch",/interruptor|\bswitch\b|estado do rel[eé]/],["daily_accumulated_energy",/consumo di[aá]rio|energia de hoje|energy_today/],["total_energy",/energia total|energia acumulada|total.*energy/]])if(pattern.test(text))return semantic;return "unknown";};
  const normalizeType=value=>({"booleano":"bool","boolean":"bool","bool":"bool","valor numérico":"value","valor numerico":"value","numérico":"value","numerico":"value","integer":"value","number":"value","value":"value","enumeração":"enum","enumeracao":"enum","enum":"enum","falha":"fault","fault":"fault","texto":"string","string":"string","dados binários":"raw","dados binarios":"raw","raw":"raw","desconhecido":"unknown","desconhecida":"unknown","unknown":"unknown"})[String(value||"").trim().toLowerCase()]||"unknown";
  try{const parsed=JSON.parse(String(text||"")),items=Array.isArray(parsed)?parsed:(Array.isArray(parsed?.dps)?parsed.dps:Array.isArray(parsed?.rows)?parsed.rows:[]);sourceRows.push(...items);}catch{}
  if(!sourceRows.length){for(const line of String(text||"").split(/\r?\n/).map(value=>value.trim()).filter(Boolean)){const match=line.match(/(?:DPS\s*)?(\d{1,5})\s*(?:[|;\t,]\s*|\s+-\s+)(.+)/i);if(!match)continue;const parts=match[2].split(/[|;\t,]/).map(value=>value.trim()),entry={dps_id:Number(match[1]),label_pt:parts[0]||""};if(parts.length>=6){const capabilityText=parts[1]||"",codeMatch=capabilityText.match(/(?:^|[•·\s])([a-z][a-z0-9_]{1,95})\s*$/i),code=codeMatch?.[1]||"",cap=capabilities.find(item=>item.code.toLowerCase()===code.toLowerCase()),semantic=semanticOf(`${parts[0]} ${capabilityText} ${parts[2]||""}`),scaleText=parts[5]||"";entry.data_type=normalizeType(parts[3]);entry.unit=["—","-"].includes(parts[4])?"":parts[4];entry.scale=scaleText&&!["—","-"].includes(scaleText)&&Number.isFinite(Number(scaleText))?Number(scaleText):null;entry.semantic_code=semanticOf(parts[2])==="unknown"?semantic:semanticOf(parts[2]);if(cap){entry.code=cap.code;entry.source=cap._source;entry.data_type=normalizeType(parts[3])==="unknown"?normalizeType(cap.type):normalizeType(parts[3]);entry.details=typeof cap.values==="string"?cap.values:JSON.stringify(cap.values||{});}}else{const semantic=semanticOf(line),cap=capabilities.find(item=>line.toLowerCase().includes(item.code.toLowerCase()))||capabilities.find(item=>semantic!=="unknown"&&semanticOf(`${item.code} ${item.name||""} ${item.label||""}`)===semantic);if(cap){entry.code=cap.code;entry.source=cap._source;entry.data_type=normalizeType(cap.type);entry.details=typeof cap.values==="string"?cap.values:JSON.stringify(cap.values||{});}entry.semantic_code=semantic;}const unit=parts.find(value=>/^(V|mV|A|mA|W|kW|Wh|kWh|s|min|%|°C)$/i.test(value));if(unit)entry.unit=unit;sourceRows.push(entry);}}
  const existing=new Map(rows.map(row=>[Number(row.dps_id),{...row}])),mapped=[];
  for(const item of sourceRows){if(!item||typeof item!=="object")continue;const id=Number(item.dps_id??item.dp_id??item.dpId??item.id);if(!Number.isInteger(id)||id<1||id>65535||!existing.has(id))continue;const row=existing.get(id),code=String(item.code??item.function_code??item.tuya_code??"").trim(),description=[item.semantic_code,item.semantic,item.label_pt,item.label,item.name,code].filter(Boolean).join(" "),semantic=semanticOf(description),cap=capabilities.find(candidate=>candidate.code===code)||capabilities.find(candidate=>semantic!=="unknown"&&semanticOf(`${candidate.code} ${candidate.name||""} ${candidate.label||""}`)===semantic)||capabilities.find(candidate=>candidate._source===String(item.source||item.origin||"")&&candidate.code===row.code);if(code&&!cap&&semantic==="unknown")continue;const source=cap?cap._source:String(item.source||item.origin||row.source||"unknown");Object.assign(row,{source,code:cap?.code||"",label_pt:String(item.label_pt||item.label||item.name||row.label_pt||"").slice(0,120),data_type:normalizeType(item.data_type||item.type||cap?.type||row.data_type||"unknown"),unit:String(item.unit??row.unit??"").replace(/^[—-]$/,"" ).slice(0,24),scale:item.scale===undefined?row.scale:item.scale,details:String(item.details??item.values??cap?.values??row.details??"").slice(0,512),semantic_code:String(item.semantic_code||item.semantic||semantic||row.semantic_code||"unknown")});existing.set(id,row);mapped.push(id);}
  const mappedIds=[...new Set(mapped)];return {rows:[...existing.values()].sort((a,b)=>a.dps_id-b.dps_id),updatedRows:[...existing.values()].filter(row=>mappedIds.includes(Number(row.dps_id))),mapped:mappedIds};
}
function tuyaDpsMeaningDetail(row){let explicit=String(row.details||row.description||row.values||"").trim(),code=String(row.function_code||row.code||row.name||"").toLowerCase(),values=explicit;if(explicit){try{const parsed=JSON.parse(explicit);values=JSON.stringify(parsed);const range=parsed?.range||parsed?.values;if(Array.isArray(range)){const labels=range.map(value=>String(value).replace(/^power_off$/,"desligado").replace(/^power_on$/,"ligado").replace(/^last$/,"último estado").replace(/^memory$/,"memória"));values=`Valores declarados: ${labels.join(" · ")}`;if(/relay/.test(code)&&range.every(value=>typeof value==="number")&&range.length===3)values+=`. O esquema só declara três valores numéricos; o significado de cada um não está rotulado.`;if(/memory/.test(code)||range.some(value=>String(value).toLowerCase()==="memory"))values+=" A opção ‘memória’ normalmente indica recuperar o último estado após ligar; confirmar no aparelho.";}}catch{}return /[\u3400-\u9fff]/.test(explicit)?tuyaDpsPt({description:explicit},row.dps_id):values;}if(/count.?down|timer/.test(code))return "Contagem decrescente / temporizador. A cloud identifica a função; unidade e limites dependem do esquema.";if(/memory/.test(code))return "Código relacionado com memória. Sugestão: estado de arranque; confirmar com o domínio enum e uma leitura observada.";if(/relay/.test(code))return "Estado ou modo do relé. Se só houver 0/1/2 sem rótulos cloud, os valores continuam por identificar; compara leituras antes/depois de alterar o equipamento.";return "";}
function analyzeTuyaPidDpsPaste(text,profile,rows){
  const parsed=parseTuyaPidDpsPaste(text,profile,rows),capabilities=[...(profile.functions||[]).map(item=>({...item,_source:"function"})),...(profile.status_spec||[]).map(item=>({...item,_source:"status"}))],byId=new Map(parsed.rows.map(row=>[Number(row.dps_id),row]));let jsonValid=false;try{const value=JSON.parse(String(text||""));jsonValid=Array.isArray(value)||Array.isArray(value?.dps)||Array.isArray(value?.rows);}catch{}if(jsonValid)return {parsed,records:[{id:`${parsed.mapped.length} DPS em JSON`,original:String(text||""),suggestion:String(text||""),issues:parsed.mapped.length?[]:["O JSON não contém DPS válidos para este PID."]}]};const records=String(text||"").split(/\r?\n/).map(line=>line.trim()).filter(Boolean).map((line,index)=>{
    const match=line.match(/^\s*(?:DPS\s*)?(\d{1,5})\s*[|;\t,]/i),id=match?Number(match[1]):null,parts=match?line.slice(match[0].length).split(/[|;\t,]/).map(value=>value.trim()):[],row=id?byId.get(id):null,issues=[];
    if(!id)issues.push("Não foi possível identificar o número DPS nesta linha.");else if(!rows.some(item=>Number(item.dps_id)===id))issues.push(`DPS ${id} não está na lista deste PID.`);
    if(parts.length>=6){const rawType=parts[3]||"",normalized={"booleano":"bool","boolean":"bool","bool":"bool","valor numérico":"value","valor numerico":"value","numérico":"value","numerico":"value","integer":"value","number":"value","value":"value","enumeração":"enum","enumeracao":"enum","enum":"enum","falha":"fault","fault":"fault","texto":"string","string":"string","dados binários":"raw","dados binarios":"raw","raw":"raw","desconhecido":"unknown","desconhecida":"unknown","unknown":"unknown"}[rawType.toLowerCase()];if(rawType&&!normalized)issues.push(`Tipo de dado “${rawType}” não reconhecido.`);const scale=parts[5]||"";if(scale&&!/[—-]/.test(scale)&&!Number.isFinite(Number(scale)))issues.push(`Escala “${scale}” não é numérica.`);const capability=parts[1]?.split(/[•·]/).map(value=>value.trim()).at(-1)||"";if(capability&&!capabilities.some(item=>item.code.toLowerCase()===capability.toLowerCase()))issues.push(`Código Tuya “${capability}” não existe no esquema deste PID.`);}
    const code=row?.code||row?.function_code||"",source=row?.source||"unknown",type=row?.data_type||"unknown",unit=row?.unit||"",scale=row?.scale,semantic=parts.length>=6?(parts[2]||"Por identificar"):"Por identificar",suggestion=parts.length>=6&&row?`DPS ${id} | ${row.label_pt||parts[0]} | ${source==="function"?"Ordem":"Leitura"} • ${code||"Sem associação"} | ${semantic} | ${type} | ${unit||"—"} | ${scale??"—"}`:line;
    return {id:id||`linha ${index+1}`,original:line,suggestion,issues};
  });
  const counts=new Map();for(const record of records){const match=record.suggestion.match(/\|\s*(?:Ordem|Leitura)\s*•\s*([^|]+)/i),code=match?.[1]?.split(/[•·]/).map(value=>value.trim()).at(-1);if(code&&code!=="Sem associação")counts.set(code,(counts.get(code)||0)+1);}for(const record of records){const match=record.suggestion.match(/\|\s*(?:Ordem|Leitura)\s*•\s*([^|]+)/i),code=match?.[1]?.split(/[•·]/).map(value=>value.trim()).at(-1);if(code&&counts.get(code)>1)record.issues.push(`Código Tuya “${code}” repetido nesta lista.`);}
  return {parsed,records};
}
function openTuyaPidDpsPasteReview(text,profile,rows,onConfirm){
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-dps-paste-review";dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">REVISÃO DO MAPA DPS</p><h2 data-review-title></h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><label>Texto inserido<textarea data-review-original readonly></textarea></label><p class="tuya-dps-review-errors" data-review-errors role="alert"></p><label>Sugestão corrigida · pode editar<textarea data-review-corrected></textarea></label><div class="dialog-actions tuya-dps-review-nav"><button type="button" class="button secondary" data-review-prev>← Anterior</button><button type="button" class="button secondary" data-review-next>Seguinte →</button></div><p class="connection-result" data-review-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-review-cancel>Cancelar</button><button type="button" class="button primary" data-review-save>Gravar correções</button></div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});let analysis=analyzeTuyaPidDpsPaste(text,profile,rows),index=0;
  const render=()=>{const record=analysis.records[index];dialog.querySelector("[data-review-title]").textContent=`DPS ${record.id} · ${index+1}/${analysis.records.length}`;const original=dialog.querySelector("[data-review-original]");original.value=record.original;original.classList.toggle("has-error",record.issues.length>0);const errors=dialog.querySelector("[data-review-errors]");errors.textContent=record.issues.length?record.issues.join(" "):"Sem erro detetado nesta linha.";errors.classList.toggle("has-error",record.issues.length>0);dialog.querySelector("[data-review-corrected]").value=record.suggestion;dialog.querySelector("[data-review-prev]").disabled=index<=0;dialog.querySelector("[data-review-next]").disabled=index>=analysis.records.length-1;};
  const save=dialog.querySelector("[data-review-save]");dialog.querySelector("[data-review-cancel]").onclick=()=>dialog.close();dialog.querySelector("[data-review-prev]").onclick=()=>{analysis.records[index].suggestion=dialog.querySelector("[data-review-corrected]").value;index=Math.max(0,index-1);render();};dialog.querySelector("[data-review-next]").onclick=()=>{analysis.records[index].suggestion=dialog.querySelector("[data-review-corrected]").value;index=Math.min(analysis.records.length-1,index+1);render();};
  save.onclick=async()=>{analysis.records[index].suggestion=dialog.querySelector("[data-review-corrected]").value;const status=dialog.querySelector("[data-review-status]"),candidateText=analysis.records.map(record=>record.suggestion).join("\n"),checked=analyzeTuyaPidDpsPaste(candidateText,profile,rows),errors=checked.records.filter(record=>record.issues.length);if(errors.length){analysis=checked;index=Math.max(0,analysis.records.findIndex(record=>record.issues.length));render();dialog.querySelector("[data-review-status]").textContent=`Ainda há ${errors.length} linha(s) com erro. Corrige a sugestão assinalada a vermelho.`;return;}save.disabled=true;status.textContent="A gravar o mapa revisto deste PID…";try{await onConfirm(checked.parsed);dialog.close();}catch(error){status.textContent=`Erro no mapa DPS — ${tuyaPidDpsSaveErrorText(error)}`;save.disabled=false;}};
  if(!analysis.records.length){analysis.records=[{id:"texto",original:String(text||""),suggestion:String(text||""),issues:["Não foi possível identificar linhas de DPS neste texto."]}];}render();dialog.showModal();return dialog;
}
function openTuyaPidDpsReadDialog(productId,profile){
  const candidates=(state.tuyaDevices||[]).filter(device=>String(device.product_id||"")===String(productId)&&(device.online===true||device.local_verified===true||tuyaReadingConfirmed((state.tuyaReadings||[]).find(item=>item.device_id===device.device_id)))&&device.local_key_available&&(device.local_ip||device.local_mac));
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-pid-read-dialog";
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">LEITURA LAN · PID ${esc(productId)}</p><h2>Escolher equipamento</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><p class="field-note">A leitura consulta apenas um equipamento deste PID, pela LAN. Não envia ordens. Os IDs encontrados serão acrescentados ao mapa central para os associares às funções (ordens) e estados (leituras) da cloud.</p><label>Equipamento<select data-tuya-pid-read-device ${candidates.length?"":"disabled"}>${candidates.map(device=>`<option value="${esc(device.device_id)}">${esc(device.name||device.device_id)} · ${esc(device.local_ip||"IP não indicado")} · ${device.online===true?"Online cloud":"LAN confirmada"}</option>`).join("")||'<option value="">Não há equipamento online deste PID</option>'}</select></label><p class="connection-result" data-tuya-pid-read-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-tuya-pid-read-cancel>Cancelar</button><button type="button" class="button primary" data-tuya-pid-read-start ${candidates.length?"":"disabled"}>Ler DPS</button></div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector("[data-tuya-pid-read-cancel]").onclick=()=>dialog.close();
  dialog.querySelector("[data-tuya-pid-read-start]").onclick=async event=>{const button=event.currentTarget,select=dialog.querySelector("[data-tuya-pid-read-device]"),status=dialog.querySelector("[data-tuya-pid-read-status]"),deviceId=select?.value;button.disabled=true;status.textContent="A consultar os DPS do equipamento selecionado pela LAN…";try{const report=await runGatewayTuyaLanDiagnostics(1,deviceId),result=(report.devices||[]).find(item=>item?.device_id===deviceId);if(!result||result.connection_state!=="local_responded")throw new Error(tuyaLanReasonText(result?.reason||"tuya_lan_status_unavailable"));const observed=Array.isArray(result.status)?result.status:[],byId=new Map(tuyaPidRows(profile).map(row=>[row.dps_id,row]));let found=0;for(const item of observed){const id=Number(item?.dps_id??item?.dp_id??item?.dpId??(/^dps_\d+$/.test(String(item?.code||""))?String(item.code).slice(4):NaN));if(!Number.isInteger(id)||id<1||id>65535)continue;found++;const row=byId.get(id)||{dps_id:id,code:"",function_code:"",display_name:"",semantic_code:"unknown",data_type:typeof item.value==="boolean"?"bool":typeof item.value==="number"?"value":typeof item.value==="string"?"string":"raw",source_kind:"unknown",confidence:"OBSERVED_LAN",source:"Leitura LAN do equipamento"};row.raw_value=item.value;row.read_supported=true;row.observed_from=deviceId;byId.set(id,row);}if(!found)throw new Error("A leitura respondeu, mas não trouxe IDs DPS utilizáveis.");profile.dps_profile={...(profile.dps_profile||{}),dps:[...byId.values()].sort((a,b)=>a.dps_id-b.dps_id)};profile.dps=profile.dps_profile.dps;status.textContent=`Leitura concluída: ${found} DPS observados. A abrir o mapa central do PID para os classificar.`;window.setTimeout(()=>{dialog.close();openTuyaPidDpsMapEditor(productId,profile,()=>refreshTuyaProductCatalogViews());},400);}catch(error){status.textContent=`A leitura LAN falhou: ${error.message}`;button.disabled=false;}};
  dialog.showModal();
}
function tuyaPidDpsSaveErrorText(error){
  const detail=String(error?.message||error||"Erro desconhecido"),match=detail.match(/^([a-z0-9_]+)\|row=(\d+)\|dps=([^|]+)\|field=([^|]+)\|reason=([^|]+)$/i);
  if(/load failed|failed to fetch|networkerror/i.test(detail))return "O browser não recebeu resposta do Gateway ao gravar o mapa DPS. É uma falha de ligação ou CORS, não um erro de uma linha; confirma se o Gateway está acessível e volta a abrir o mapa para verificar o resultado antes de repetir.";
  if(!match){if(/tuya_pid_dps_row_invalid/.test(detail))return "O Gateway rejeitou uma linha do mapa DPS, mas a versão instalada não informou qual. Atualiza o Gateway para receber o número da linha e o campo inválido.";return detail;}
  const [,code,row,dps,field,reason]=match,fields={dps_id:"número DPS",code:"código Tuya",label_pt:"nome em português",source:"origem",data_type:"tipo de dado",unit:"unidade",scale:"escala",semantic_code:"característica"},fieldNames=field.split(",").map(name=>fields[name]||name).join(", ");
  const reasons={unsupported_value:"valor não aceite",unexpected_field:"campo inesperado",object_expected:"esperava um objeto DPS",invalid_or_repeated:"número ausente, inválido ou repetido",must_be_text_up_to_96_chars:"deve ser texto até 96 caracteres",must_be_text_up_to_120_chars:"deve ser texto até 120 caracteres",must_be_text_up_to_24_chars:"deve ser texto até 24 caracteres",must_be_finite_number_or_empty:"deve ser um número finito ou ficar vazio",function_not_declared_for_pid:"função não declarada para este PID",status_not_declared_for_pid:"estado não declarado para este PID"};
  let message=`Linha ${row} da lista DPS (DPS ${dps}), campo ${fieldNames}: ${reasons[reason]||reason.replaceAll("_"," ")}.`;
  if(code==="tuya_pid_dps_cloud_code_mapped_more_than_once")message=`Código Tuya duplicado neste PID — ${message} Já aparece na linha ${reason.replace("already_used_on_row_","")}.`;
  return message;
}
function openTuyaPidDpsMapEditor(productId,profile,onSaved=()=>{}){
  const rows=tuyaPidRows(profile).map(row=>({...row,source:["function","status"].includes(row.origin)?row.origin:["function","status"].includes(row.source)?row.source:["function","status"].includes(row.source_kind)?row.source_kind:"unknown",code:String(row.code||row.function_code||""),label_pt:String(row.label_pt||""),unit:String(row.unit||""),scale:row.scale??"",details:String(row.details||row.description||"")}));
  let capabilities=[...(profile.functions||[]).map(item=>({...item,_source:"function"})),...(profile.status_spec||[]).map(item=>({...item,_source:"status"}))].filter(item=>item&&typeof item.code==="string");
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-dps-map-editor";
  const keyOf=row=>row.code?String(row.code).trim():"";
  const duplicates=()=>{const counts=new Map();for(const row of rows){const key=keyOf(row);if(key)counts.set(key,(counts.get(key)||0)+1);}return new Set([...counts].filter(([,count])=>count>1).map(([key])=>key));};
  const rowIncongruent=row=>{const name=String(row.label_pt||row.name||row.code_pt||"").toLowerCase(),code=String(row.code||row.function_code||"").toLowerCase(),semantic=String(row.semantic_code||"").toLowerCase(),signals=[[/voltag|tens[aã]o|voltage|cur_voltage/,"voltage"],[/corrente|amper|current|cur_current/,"current"],[/pot[eê]ncia|power|cur_power/,"power"],[/countdown|temporizador|timer/,"countdown"],[/energia|energy|consumo/,"energy"]],fromName=signals.find(([pattern])=>pattern.test(name))?.[1],fromCode=signals.find(([pattern])=>pattern.test(code))?.[1];return Boolean(fromName&&fromCode&&fromName!==fromCode||semantic&&fromCode&&semantic!==fromCode);};
  const render=()=>{const dup=duplicates();dialog.querySelector("[data-dps-list]").innerHTML=`<div class="tuya-dps-compact-head"><span>Número DPS</span><span>Nome · função/estado</span></div>${rows.map((row,index)=>{const conflict=keyOf(row)&&dup.has(keyOf(row)),incongruent=rowIncongruent(row),ambiguous=!row.code||row.source==="unknown"||conflict||incongruent;return `<div class="tuya-dps-compact-row ${ambiguous?"is-ambiguous":""} ${conflict?"is-conflict":""}" data-dps-id="${row.dps_id}"><span class="tuya-dps-number">DPS ${row.dps_id}</span><button type="button" class="tuya-dps-name-button" data-edit-row="${index}">${esc(row.label_pt||tuyaDpsPt(row,row.dps_id)||"Por identificar")}<small>${conflict?"Associação duplicada · corrigir":incongruent?"Incongruência · confirmar associação":row.code?`${row.source==="function"?"Ordem":"Leitura"} · ${esc(row.code)}`:"Toque para associar função/estado"}</small></button></div>`;}).join("")||'<p class="field-note">Este PID ainda não tem DPS numéricos observados. Use “Ler num equipamento” para acrescentar.</p>'}`;};
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">TUYA · ESQUEMA DO PID</p><h2>Mapa DPS · ${esc(productId)}</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><p class="field-note">Toque no nome para editar. Amarelo indica informação por identificar; vermelho indica o mesmo código Tuya associado mais do que uma vez.</p><button type="button" class="button secondary" data-dps-cloud-refresh>Reler funções e estados da Tuya Cloud</button><p class="field-note">Atualiza as declarações cloud deste inventário; mantém o mapa DPS e as associações guardadas.</p><div class="tuya-dps-compact-list" data-dps-list></div><section class="tuya-dps-paste"><h3>Importar informação por texto</h3><p class="field-note">Cole linhas com DPS, nome, código Tuya, unidade e escala ou JSON. A análise só associa códigos declarados para este PID.</p><textarea data-dps-paste aria-label="Texto com informações conhecidas dos DPS" placeholder="Exemplo: DPS 20 | Tensão | cur_voltage | V | 0.1"></textarea><button type="button" class="button secondary" data-dps-paste-apply>Analisar texto e guardar</button><p class="connection-result" data-paste-status role="status" aria-live="polite"></p></section><p class="connection-result" data-dps-map-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-dps-map-close>Fechar</button></div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector("[data-dps-map-close]").onclick=()=>dialog.close();render();
  const cloudRefresh=dialog.querySelector("[data-dps-cloud-refresh]");cloudRefresh.onclick=async()=>{const status=dialog.querySelector("[data-dps-map-status]");cloudRefresh.disabled=true;status.textContent="A reler as funções e estados Tuya da conta cloud…";try{const sync=await syncGatewayTuyaDevices();await refreshHardwareIntegrationConfig();await refreshTuyaProductCatalogViews();const refreshed=state.smartProductCatalog.find(item=>item.product_id===productId);if(!refreshed)throw new Error("O Gateway não devolveu o esquema atualizado para este PID.");profile.functions=Array.isArray(refreshed.functions)?refreshed.functions:[];profile.status_spec=Array.isArray(refreshed.status_spec)?refreshed.status_spec:[];capabilities=[...profile.functions.map(item=>({...item,_source:"function"})),...profile.status_spec.map(item=>({...item,_source:"status"}))].filter(item=>item&&typeof item.code==="string");status.textContent=`Lista cloud atualizada: ${profile.functions.length} funções e ${profile.status_spec.length} estados. O mapa DPS foi mantido.${sync.schema_failures?` A sincronização reportou ${sync.schema_failures} falha(s) na recolha cloud; algumas declarações podem continuar em cache.`:""}`;}catch(error){status.textContent=`Não foi possível reler a lista Tuya: ${error.message}`;}finally{cloudRefresh.disabled=false;}};

  dialog.addEventListener("click",event=>{const button=event.target.closest("[data-edit-row]");if(!button)return;const index=Number(button.dataset.editRow),row=rows[index],value=row.code?`${row.source}::${row.code}`:"",dup=duplicates(),live=row.raw_value!==undefined?row.raw_value:(state.tuyaReadings||[]).find(item=>String(item.device_id||"")===String(row.observed_from||"")&&Number(item.dps_id??item.dp_id)===row.dps_id)?.value;
    const opts=capabilities.map(item=>{const key=`${item._source}::${item.code}`,taken=rows.some((other,otherIndex)=>otherIndex!==index&&keyOf(other)===String(item.code).trim());return `<option value="${esc(key)}" ${key===value?"selected":""} ${taken?"disabled":""}>${item._source==="function"?"Ordem":"Leitura"} · ${esc(tuyaFriendlyCapabilityLabel(item,{...profile,capability_labels:{}}))} · ${esc(item.code)}${taken?" · já associado":""}</option>`;}).join("");
    const popup=document.createElement("dialog");popup.className="settings-dialog tuya-dps-item-editor";popup.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">EDITAR DPS ${row.dps_id}</p><h2>${esc(productId)}</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><div class="tuya-dps-live-value"><small>Último valor lido pela LAN</small><strong>${live===undefined?"Sem leitura recente":esc(typeof live==="string"?live:JSON.stringify(live))}</strong></div><div class="tuya-dps-edit-grid"><label>Nome em português<input data-edit-label maxlength="120" value="${esc(row.label_pt)}"></label><label>Função/estado Tuya<select data-edit-capability><option value="">Sem associação</option>${opts}</select></label><label>Característica<select data-edit-semantic>${[["unknown","Por identificar"],["voltage","Tensão"],["current","Corrente"],["power","Potência"],["daily_accumulated_energy","Consumo diário"],["total_energy","Energia acumulada"],["switch","Interruptor"],["countdown","Temporizador"],["relay_status","Estado/modo do relé"],["power_on_state","Memória de arranque"],["child_lock","Bloqueio infantil"],["brightness","Brilho"],["color_temperature","Temperatura da cor"]].map(([v,l])=>`<option value="${v}" ${v===(row.semantic_code||"unknown")?"selected":""}>${l}</option>`).join("")}</select></label><label>Tipo<select data-edit-type>${[["unknown","Desconhecido"],["bool","Booleano"],["value","Valor numérico"],["enum","Enumeração"],["fault","Falha"],["string","Texto"],["raw","Dados binários"]].map(([v,l])=>`<option value="${v}" ${v===row.data_type?"selected":""}>${l}</option>`).join("")}</select></label><label>Unidade<input data-edit-unit maxlength="24" value="${esc(row.unit)}" placeholder="V, A, W, s…"></label><label>Escala<input data-edit-scale type="number" step="any" value="${esc(row.scale)}"></label><label class="span-2">Detalhes da codificação<textarea data-edit-details maxlength="512">${esc(row.details)}</textarea></label></div><p class="connection-result" data-edit-status role="status"></p><div class="dialog-actions"><button type="button" class="button secondary" data-edit-cancel>Cancelar</button><button type="button" class="button primary" data-edit-ok>OK · Guardar</button></div></form>`;
    document.body.append(popup);popup.addEventListener("close",()=>popup.remove(),{once:true});popup.querySelector("[data-edit-cancel]").onclick=()=>popup.close();popup.querySelector("[data-edit-ok]").onclick=async e=>{const save=e.currentTarget,status=popup.querySelector("[data-edit-status]"),selection=popup.querySelector("[data-edit-capability]").value,[source,code]=selection.split("::");if(code&&rows.some((other,otherIndex)=>otherIndex!==index&&keyOf(other)===selection)){status.classList.add("tuya-dps-error");status.textContent="Erro no mapa DPS — este código Tuya já está associado a outro DPS deste PID.";return;}save.disabled=true;row.label_pt=popup.querySelector("[data-edit-label]").value.trim();row.source=source||"unknown";row.code=code||"";row.function_code=code||"";row.semantic_code=popup.querySelector("[data-edit-semantic]").value;row.data_type=popup.querySelector("[data-edit-type]").value;row.unit=popup.querySelector("[data-edit-unit]").value.trim();row.scale=popup.querySelector("[data-edit-scale]").value===""?null:Number(popup.querySelector("[data-edit-scale]").value);row.details=popup.querySelector("[data-edit-details]").value.trim();status.classList.remove("tuya-dps-error");status.textContent=`A guardar apenas o DPS ${row.dps_id}…`;try{const result=await saveGatewayTuyaPidDpsMap(productId,[row],{partial:true});profile.dps_profile={...(profile.dps_profile||{}),dps:rows};profile.dps=rows;dialog.querySelector("[data-dps-map-status]").textContent=`DPS ${row.dps_id} guardado. Mapa do PID: ${result.dps_count} DPS.`;render();await onSaved();popup.close();}catch(error){status.classList.add("tuya-dps-error");status.textContent=`Erro no mapa DPS — ${tuyaPidDpsSaveErrorText(error)}`;save.disabled=false;}};popup.showModal();});
  dialog.querySelector("[data-dps-paste-apply]").onclick=event=>{const button=event.currentTarget,status=dialog.querySelector("[data-paste-status]"),text=dialog.querySelector("[data-dps-paste]").value;button.disabled=true;status.classList.remove("tuya-dps-error");status.textContent="A analisar o texto DPS…";openTuyaPidDpsPasteReview(text,profile,rows,async parsed=>{try{const updates=parsed.updatedRows||[],updatingIds=new Set(updates.map(row=>Number(row.dps_id))),seen=new Set();let ambiguous=0;for(const row of updates){const key=keyOf(row),conflicts=key&&(seen.has(key)||rows.some(other=>!updatingIds.has(Number(other.dps_id))&&keyOf(other)===key));if(conflicts){row.source="unknown";row.code="";row.function_code="";ambiguous++;}else if(key)seen.add(key);}const result=await saveGatewayTuyaPidDpsMap(productId,updates,{partial:true});for(const update of updates){const current=rows.find(row=>Number(row.dps_id)===Number(update.dps_id));if(current)Object.assign(current,update);else rows.push(update);}profile.dps_profile={...(profile.dps_profile||{}),dps:rows};profile.dps=rows;render();await onSaved();status.textContent=`${updates.length-ambiguous} DPS atualizado(s) apenas nesta importação.${ambiguous?` ${ambiguous} associação(ões) repetida(s) ficaram por identificar a amarelo.`:""} Mapa do PID: ${result.dps_count} DPS.`;button.disabled=false;return result;}catch(error){button.disabled=false;throw error;}});button.disabled=false;};
  dialog.showModal();
}
function openTuyaProductMetadataEditor(productId,profile){
  const device=state.tuyaDevices.find(item=>item.product_id===productId),dpsRows=tuyaPidRows(profile).map(row=>({id:row.dps_id,name:row.label_pt,type:row.data_type,source:row.source||profile.schema_source||"Esquema Tuya"}));
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-product-editor";
  const kinds=[["unknown","Não classificado"],["breaker","Disjuntor"],["switch","Interruptor"],["multi_switch","Interruptor com vários canais"],["dimmer","Regulador de intensidade"],["blind","Estore"],["socket","Tomada"],["light","Lâmpada"],["sensor","Sensor"],["ev_charger","Carregador elétrico"]];
  dialog.innerHTML=`<form method="dialog" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">CATÁLOGO TUYA · MAPA PARTILHADO POR PID</p><h2>Editar produto Tuya</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></div><label>Product ID<input value="${esc(productId)}" readonly></label><label>Product original da cloud<input value="${esc(profile.cloud_product||profile.product_name||"")}" readonly></label><label>Nome apresentado em português<input data-tuya-product-name maxlength="160" value="${esc(profile.product_name_pt||profile.product_name||profile.cloud_product||"")}" placeholder="Nome reconhecível, por exemplo: Disjuntor Wi-Fi"></label><label>Tipo funcional<select data-tuya-product-kind>${kinds.map(([value,label])=>`<option value="${value}" ${value===(profile.device_kind||"unknown")?"selected":""}>${label}</option>`).join("")}</select></label><div class="device-detail-grid"><div class="detail-item"><small>Categoria Tuya</small><strong>${esc(profile.category||"Não indicada")}</strong></div><div class="detail-item"><small>Fonte do esquema</small><strong>${esc(profile.schema_source||"Tuya / Gateway")}</strong></div><div class="detail-item"><small>Equipamentos afetados</small><strong>${state.tuyaDevices.filter(item=>item.product_id===productId).length}</strong></div></div><h3>Mapa DPS deste PID</h3><p class="field-note">O nome e o tipo funcional ajudam a identificar o produto. O mapa DPS permanece associado apenas ao Product ID.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>DPS</th><th>Nome/função</th><th>Tipo</th><th>Fonte</th><th></th></tr></thead><tbody>${dpsRows.map(row=>`<tr><td>${row.id}</td><td>${esc(row.name)}</td><td>${esc(row.type)}</td><td>${esc(row.source)}</td><td><button type="button" class="button secondary" data-tuya-edit-dps="${row.id}">Editar mapa</button></td></tr>`).join("")||'<tr><td colspan="5">A Tuya ainda não forneceu pontos DPS para este produto.</td></tr>'}</tbody></table></div><p class="connection-result" data-tuya-product-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-tuya-product-cancel>Fechar</button><button type="button" class="button primary" data-tuya-product-save>Guardar produto</button></div></form>`;
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove(),{once:true});dialog.querySelector("[data-tuya-product-cancel]").addEventListener("click",()=>dialog.close());
  dialog.querySelectorAll("[data-tuya-edit-dps]").forEach(button=>button.addEventListener("click",()=>openTuyaPidDpsMapEditor(productId,profile,()=>refreshTuyaProductCatalogViews())));
  dialog.querySelector("[data-tuya-product-save]").addEventListener("click",async event=>{const button=event.currentTarget,status=dialog.querySelector("[data-tuya-product-status]");button.disabled=true;status.textContent="A guardar este produto para todos os aparelhos com o mesmo PID…";try{const saved=await saveGatewayTuyaProductMetadata({product_id:productId,product_name_pt:dialog.querySelector("[data-tuya-product-name]").value,device_kind:dialog.querySelector("[data-tuya-product-kind]").value});status.textContent=`Guardado. Aplicado a ${saved.affected_device_count} equipamento(s).`;await refreshTuyaProductCatalogViews();await refreshHardwareIntegrationConfig();}catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;button.disabled=false;}});
  dialog.showModal();
}
async function previewTuyaProductImport(source){
  const status=$("#tuya-product-import-status"),preview=$("#tuya-product-import-preview");status.textContent="A analisar a origem e a comparar com o catálogo local…";preview.replaceChildren();
  try{const result=await previewGatewayTuyaProductImport(source);tuyaProductImportPreview=result;const changes=result.changes||[];
    status.textContent=`Pré-visualização: ${result.source_count} Product IDs interpretados; ${changes.filter(row=>row.status==="added").length} novos, ${changes.filter(row=>row.status==="changed").length} alterados e ${result.unchanged_count} iguais. Nada foi gravado.`;
    const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-import-dialog";dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">REVISÃO DO CATÁLOGO · NÃO GRAVADO</p><h2>Product IDs encontrados</h2></div><button class="icon-button" value="cancel" aria-label="Cancelar">×</button></form><div class="dialog-body"><p class="field-note">Assinala as linhas com incongruências para as preservar como estão. Por omissão, todos os Product IDs novos ou alterados serão aplicados; os iguais não precisam de atualização.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Preservar atual</th><th>Estado</th><th>Product ID</th><th>Nome atual → proposto</th><th>DPS/funções</th></tr></thead><tbody>${changes.map(row=>`<tr><td><input type="checkbox" data-import-exclude="${esc(row.product_id)}" ${row.status==="unchanged"?"checked disabled":""} aria-label="Preservar o Product ID atual ${esc(row.product_id)}"></td><td>${row.status==="added"?"Novo":row.status==="changed"?"Alterado":"Sem alteração"}</td><td>${esc(row.product_id)}</td><td>${esc(row.current_name||"—")} → ${esc(row.proposed_name||"—")}</td><td>${row.current_dps_count} → ${row.proposed_dps_count}</td></tr>`).join("")}</tbody></table></div><p class="connection-result" data-import-confirm-status role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-import-cancel>Cancelar</button><button type="button" class="button primary" data-import-apply>Atualizar catálogo</button></div></div>`;
    document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove());dialog.querySelector("[data-import-cancel]").addEventListener("click",()=>dialog.close("cancel"));dialog.querySelector("[data-import-apply]").addEventListener("click",async event=>{const button=event.currentTarget,confirmStatus=dialog.querySelector("[data-import-confirm-status]"),excluded=[...dialog.querySelectorAll("[data-import-exclude]:checked")].map(input=>input.dataset.importExclude);button.disabled=true;confirmStatus.textContent="A guardar apenas os itens aprovados…";try{const saved=await applyGatewayTuyaProductImport(result.profiles,excluded);confirmStatus.textContent=`Atualização concluída: ${saved.applied_count} aplicados e ${saved.excluded_count} ignorados.`;status.textContent=confirmStatus.textContent;await refreshTuyaProductCatalogViews();setTimeout(()=>dialog.close("applied"),700);}catch(error){confirmStatus.textContent=`Não foi possível guardar: ${error.message}`;button.disabled=false;}});dialog.showModal();
  }catch(error){tuyaProductImportPreview=null;status.textContent=`A origem não foi importada: ${error.message}`;}
}
setupTuyaManagementSections();
$("#deye-save").addEventListener("click", event => {
  const host = $("#hardware-deye-host").value.trim();
  saveHardwareProvider("deye", { enabled: Boolean(host), host, port: Number($("#hardware-deye-port").value), unit_id: Number($("#hardware-deye-unit").value), model: "SUN-15K-SG05LP3-EU-SM2" }, event.currentTarget, "deye-status");
});
$("#deye-cloud-save").addEventListener("click",async event=>{
  const button=event.currentTarget,status=$("#deye-cloud-status");if(!ownerCanManageHardware("#deye-cloud-status"))return;
  button.disabled=true;status.textContent="A guardar as credenciais apenas no Gateway…";
  try{
    const existing=await readGatewayHardwareIntegrationConfig(),previous=existing.deye_cloud||{};
    const payload={data_center:$("#deye-cloud-center").value,app_id:$("#deye-cloud-app-id").value.trim()||previous.app_id,email:$("#deye-cloud-email").value.trim()||previous.email};
    if($("#deye-cloud-app-secret").value)payload.app_secret=$("#deye-cloud-app-secret").value;
    if($("#deye-cloud-password").value)payload.password=$("#deye-cloud-password").value;
    const saved=await saveGatewayHardwareIntegrationConfig({deye_cloud:payload});
    $("#deye-cloud-app-secret").value="";$("#deye-cloud-password").value="";
    status.textContent=saved.deye_cloud?.configured?"Acesso à Deye Cloud guardado no Gateway. Segredos ocultos.":"Configuração incompleta.";
  }catch(error){status.textContent=`Não foi possível guardar o acesso Deye Cloud: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#deye-cloud-stations").addEventListener("click",async event=>{
  const button=event.currentTarget,status=$("#deye-cloud-status"),select=$("#deye-cloud-station");if(!ownerCanManageHardware("#deye-cloud-status"))return;
  button.disabled=true;status.textContent="A autenticar e a consultar as estações Deye…";
  try{const result=await readGatewayDeyeCloudStations();select.innerHTML='<option value="">Seleciona a estação</option>'+(result.stations||[]).map(item=>`<option value="${esc(item.station_id)}">${esc(item.name)} · ${esc(item.station_id)}</option>`).join("");status.textContent=`Foram encontradas ${(result.stations||[]).length} estação(ões). As credenciais continuam apenas no Gateway.`;}
  catch(error){status.textContent=`Não foi possível consultar a Deye Cloud: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#deye-cloud-import").addEventListener("click",async event=>{
  const button=event.currentTarget,status=$("#deye-cloud-status"),progress=$("#deye-cloud-progress"),progressBar=$("#deye-cloud-progress-bar"),progressLabel=$("#deye-cloud-progress-label"),stationId=$("#deye-cloud-station").value;if(!ownerCanManageHardware("#deye-cloud-status"))return;
  if(!stationId){status.textContent="Lê as estações e seleciona uma antes de importar.";return;}
  button.disabled=true;if(progress)progress.hidden=false;if(progressBar)progressBar.value=0;if(progressLabel)progressLabel.textContent="A contactar a Deye Cloud…";status.textContent="A importação pode demorar alguns minutos. As amostras locais serão preservadas…";
  try{const result=await importGatewayDeyeCloudHistory(stationId,job=>{if(progressBar)progressBar.value=Number(job.progress)||0;if(progressLabel)progressLabel.textContent=job.message||"A importar histórico…";});status.textContent=`Importação concluída: ${result.readings_added} leituras novas de ${result.source_rows} amostras. Histórico local preservado.`;await refreshGatewayReadings();}
  catch(error){const detail=error.status===504?"O Gateway/proxy expirou à espera da resposta da importação de 90 dias. Isto não confirma que a Deye tenha recusado o acesso; verifica se surgiram novas amostras antes de repetir.":error.message;status.textContent=`A importação do histórico falhou: ${detail}`;}
  finally{button.disabled=false;if(progress)progress.hidden=true;}
});
$("#antminer-save").addEventListener("click", event => {
  const host = $("#hardware-antminer-host").value.trim();
  saveHardwareProvider("antminer", { enabled: Boolean(host), host, port: Number($("#hardware-antminer-port").value), rest_port: Number($("#hardware-antminer-rest-port").value), password: $("#hardware-antminer-password").value, model: "S19K Pro" }, event.currentTarget, "antminer-status");
});
$("#tuya-save").addEventListener("click", event => {
  const devices = parseTuyaDevices();
  saveHardwareProvider("tuya", { region: $("#hardware-tuya-region").value, client_id: $("#hardware-tuya-client-id").value.trim() || undefined, client_secret: $("#hardware-tuya-client-secret").value || undefined, uid: $("#hardware-tuya-uid").value.trim() || undefined, devices }, event.currentTarget, "tuya-status");
});
$("#tuya-sync").addEventListener("click", async event => {
  const status = $("#tuya-status"), button = event.currentTarget;
  if (!ownerCanManageHardware("#tuya-status")) return;
  const controller=new AbortController();
  const dialogClosed=showOperationDialog({title:"Sincronização Tuya",message:"A sincronizar dispositivos e capacidades da Tuya Cloud. Podes cancelar; o Gateway interrompe a sincronização entre pedidos.",progress:true,actions:[{label:"Cancelar",value:"cancel"}]});
  dialogClosed.then(result=>{if(result==="cancel"||result==="dismiss")controller.abort();});
  button.disabled = true;
  status.textContent = "";
  try {
    const current = await readGatewayHardwareIntegrationConfig();
    await saveGatewayHardwareIntegrationConfig({tuya:{region:$("#hardware-tuya-region").value,client_id:$("#hardware-tuya-client-id").value.trim()||current.tuya?.client_id,client_secret:$("#hardware-tuya-client-secret").value||undefined,uid:$("#hardware-tuya-uid").value.trim()||current.tuya?.uid,devices:parseTuyaDevices().length?parseTuyaDevices():current.tuya?.devices||[]}});
    $("#hardware-tuya-client-secret").value="";
    if(controller.signal.aborted)throw new DOMException("Sincronização cancelada.","AbortError");
    const result=await syncGatewayTuyaDevices({signal:controller.signal});
    updateOperationDialog({title:"Sincronização concluída",message:`Foram sincronizados ${result.device_count} dispositivos. ${result.schema_failures ? `${result.schema_failures} consultas de capacidades não responderam.` : "As capacidades foram consultadas."}`,actions:[{label:"OK",value:"ok",primary:true}]});
    await dialogClosed;
    await refreshHardwareIntegrationConfig(); await refreshTuyaProductCatalogViews();
  } catch(error) {
    if(error?.name==="AbortError")await showOperationResult("Sincronização cancelada","O Gateway interrompeu a sincronização. A configuração da conta ficou guardada.");
    else {updateOperationDialog({title:"Sincronização Tuya falhou",message:error.message||"O Gateway não conseguiu sincronizar os dispositivos.",actions:[{label:"OK",value:"ok",primary:true}]});await dialogClosed;}
  }
  finally { button.disabled=false; }
});
$("#tuya-lan-diagnostics").addEventListener("click", async event => {
  const button=event.currentTarget;
  if(!ownerCanManageHardware("#tuya-status"))return;
  button.disabled=true;
  const finished=showOperationDialog({title:"Medição da resposta LAN",message:"A medir três rondas de leitura dos dispositivos Tuya configurados. É uma operação só de leitura; nenhum comando será enviado.",locked:true,progress:true});
  try{
    const report=await runGatewayTuyaLanDiagnostics(3);
    updateOperationDialog({title:"Medição concluída",message:"O relatório detalhado está pronto.",actions:[{label:"Ver relatório",value:"report",primary:true}]});
    await finished;
    const ipCounts=new Map();for(const item of report.devices||[]){const ip=String(item.local_ip||"").trim();if(ip)ipCounts.set(ip,(ipCounts.get(ip)||0)+1);}
    const rows=(report.devices||[]).map(item=>{const ip=String(item.local_ip||"").trim(),duplicate=ip&&ipCounts.get(ip)>1;const ipAction=item.ip_refreshed_by_mac?"Atualizado pelo MAC":item.ip_cleared_missing_mac?"Removido: MAC ausente":"—";return `<tr><th scope="row">${esc(item.name)}<small class="diagnostic-device-id">ID Tuya: ${esc(item.device_id)}</small></th><td>${ip?`${esc(ip)}${duplicate?" · partilhado":""}`:"Não configurado"}</td><td>${ipAction}</td><td>${item.local_key_configured?"Configurada":"Em falta"}</td><td>${item.success_count}/${item.rounds}</td><td>${item.average_latency_ms==null?"—":`${esc(item.average_latency_ms)} ms`}</td><td>${item.worst_latency_ms==null?"—":`${esc(item.worst_latency_ms)} ms`}</td><td>${item.power_telemetry_configured?"Declarada":"Não identificada"}</td><td>${item.reason?esc(tuyaLanReasonText(item.reason)):"—"}</td></tr>`;}).join("");
    const sweeps=report.sweep_times_ms||[];
    const worstSweep=sweeps.length?Math.max(...sweeps):null;
    const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-diagnostic-dialog";
    dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">DIAGNÓSTICO LAN · SÓ LEITURA</p><h2>Resposta dos dispositivos</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></form><div class="dialog-body"><p class="field-note">Foram medidas ${esc(report.rounds)} rondas em ${esc(report.configured_count)} dispositivos configurados; ${esc(report.lan_testable_count)} têm um IP ou MAC e chave local configurados para consulta. O ID, IP guardado, atualizações automáticas por MAC e presença da chave aparecem por dispositivo.</p><p class="diagnostic-cycle-summary">Duração das rondas: ${sweeps.map(value=>`${esc(value)} ms`).join(" · ")||"sem leituras"}. Pior ciclo: ${worstSweep==null?"—":`${esc(worstSweep)} ms`}. Tempo total: ${esc(report.elapsed_ms)} ms. Só as respostas válidas entram nos tempos médio e pior.</p><p class="field-note">“Potência declarada” indica apenas que o esquema Tuya contém uma função/leitura com nome relacionado com potência. Não confirma que a leitura esteja calibrada nem que seja atual. “IP partilhado” assinala que vários IDs têm o mesmo host guardado; confirma se são dispositivos independentes ou subdispositivos de um hub.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Dispositivo / ID</th><th>IP guardado</th><th>Atualização de IP</th><th>Chave local</th><th>Respostas</th><th>Média</th><th>Pior</th><th>Potência</th><th>Diagnóstico</th></tr></thead><tbody>${rows||'<tr><td colspan="9">Não há dispositivos configurados.</td></tr>'}</tbody></table></div><p class="field-note">Este resultado mede consultas de leitura no estado atual da rede. Não garante um ciclo de um segundo nem tempo de corte; isso exigiria um ensaio prolongado dos dispositivos com potência e regras ativas.</p><div class="dialog-actions"><button class="button primary" type="button" data-diagnostic-close>OK</button></div></div>`;
    document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove());dialog.querySelector("[data-diagnostic-close]").addEventListener("click",()=>dialog.close("ok"));dialog.showModal();
  }catch(error){
    updateOperationDialog({title:"Medição LAN falhou",message:error.message||"O Gateway não conseguiu concluir o diagnóstico.",actions:[{label:"OK",value:"ok",primary:true}]});
    await finished;
  }finally{button.disabled=false;}
});
$("#tuya-lan-discovery").addEventListener("click", async event => {
  const button=event.currentTarget;
  if(!ownerCanManageHardware("#tuya-status"))return;
  button.disabled=true;
  const finished=showOperationDialog({title:"Descoberta Tuya na rede local",message:"O Gateway está a escutar anúncios dos dispositivos na LAN durante alguns segundos. Esta operação não usa a cloud nem envia comandos.",locked:true,progress:true});
  try{
    const result=await discoverGatewayTuyaLanDevices();
    await refreshHardwareIntegrationConfig();
    const found=(result.devices||[]).map(item=>`${esc(item.name)} · ${esc(item.ip)}${item.local_key_available?"":" · falta chave local"}`).join("\n");
    const unmatched=Math.max(0,Number(result.scanned_count||0)-Number(result.matched_count||0));
    const message=result.matched_count
      ? `O Gateway detetou ${result.scanned_count} Tuya na rede e guardou o IP local de ${result.matched_count} dispositivo(s) configurado(s).${result.scan_error?" A descoberta por anúncio falhou; os IPs apresentados vieram da tabela local de vizinhos, quando disponíveis.":""}${unmatched?` ${unmatched} detetado(s) não correspondem à lista importada.`:""}\n\n${found}`
      : `O Gateway detetou ${result.scanned_count} Tuya, mas nenhum correspondeu aos dispositivos configurados. Confirma que estão na mesma rede Wi-Fi/LAN e que a rede permite descoberta local.`;
    updateOperationDialog({title:"Descoberta concluída",message,actions:[{label:"OK",value:"ok",primary:true}]});
    await finished;
  }catch(error){
    updateOperationDialog({title:"Descoberta LAN falhou",message:error.message||"O Gateway não conseguiu procurar dispositivos Tuya na rede local.",actions:[{label:"OK",value:"ok",primary:true}]});
    await finished;
  }finally{button.disabled=false;}
});
async function readHardwareProvider(provider, deviceId = undefined, statusSelector = `#${provider}-status`, resultSelector = `#${provider}-result`) {
  if (!ownerCanManageHardware(statusSelector)) return "Só o Owner autenticado pode gerir este equipamento.";
  const status = $(statusSelector), output = $(resultSelector);
  status.textContent = `A consultar apenas ${provider === "deye" ? "o Deye" : provider === "antminer" ? "a Antminer" : "o dispositivo Tuya selecionado"}…`;
  if (output) output.hidden = true;
  try {
    const result = await readGatewayHardwareProvider(provider, deviceId);
    if (provider === "tuya") {
      const device = result.tuya?.[0];
      status.textContent = `${device?.name || "Tuya"}: ${device?.connection_state || "sem resposta"}${device?.reason ? ` · ${tuyaLanReasonText(device.reason)}` : ""}`;
      if (output) { output.textContent = JSON.stringify(device || result, null, 2); output.hidden = false; }
    } else setProviderResult(provider, result);
    if (provider === "deye" || provider === "antminer") await refreshGatewayReadings();
    return status.textContent;
  } catch (error) {
    status.textContent = `Leitura falhou: ${error.message}`;
    return status.textContent;
  }
}
function tuyaLanReasonText(reason){
  if(String(reason).startsWith("tuya_protocol_probe_failed:"))return "O dispositivo não respondeu às leituras de teste Tuya LAN 3.3, 3.4 nem 3.5. Confirma se a chave local corresponde ao dispositivo e se está acessível na rede.";
  const messages={private_lan_target_required:"Configura o IP local ou o MAC do dispositivo.",tuya_local_ip_unresolved_from_mac:"Não foi possível descobrir o IP local a partir do MAC. Confirma que o dispositivo e o Gateway estão na mesma rede.",tuya_local_ip_not_found_for_mac:"O MAC não foi encontrado numa resposta única da rede; o IP antigo foi removido e o dispositivo fica offline.",tuya_local_ip_refresh_failed:"A pesquisa local falhou; o dispositivo fica offline até ser possível confirmar o MAC e o IP.",tuya_local_key_missing:"A chave local não está disponível no Gateway.",tuya_lan_driver_unavailable:"O controlador LAN não está disponível nesta instalação.",tuya_local_datapoint_mapping_required:"Falta mapear o canal do equipamento para o respetivo DPS local.",tuya_lan_status_unavailable:"O equipamento não devolveu leituras LAN válidas.",tuya_connection_failed:"O Gateway não conseguiu obter resposta do equipamento pela rede local.",tuya_lan_read_unavailable:"Não foi possível obter uma resposta LAN deste equipamento.",lan_response_timeout:"O dispositivo não respondeu na LAN dentro do limite de espera.",tuya_lan_port_closed:"O IP respondeu, mas a porta Tuya está fechada."};
  return messages[reason]||String(reason).replaceAll("_"," ");
}
function renderLocalNetworkResults(report){
  lastLocalNetworkScanReport=report;
  const conflicts=new Set((report.mac_ip_conflicts||[]).map(item=>String(item.mac||"").toUpperCase()));
  const stageFor=host=>{
    const mac=String(host.mac||"").toUpperCase();
    if(host.mac_ip_conflict||(mac&&conflicts.has(mac)))return "ambiguous";
    if((host.matched_devices||[]).length)return "integrated";
    if(host.manufacturer||host.model||host.protocol||host.shelly_generation)return "identified";
    return "detected";
  };
  const stageLabel={integrated:"Associado · controlo não testado",identified:"Identidade provável",detected:"Só detetado",ambiguous:"Ambíguo · rever IP/MAC"};
  const stageCounts={all:(report.hosts||[]).length,integrated:0,identified:0,detected:0,ambiguous:0};
  for(const host of report.hosts||[])stageCounts[stageFor(host)]++;
  const hostRows=(report.hosts||[]).map((host,index)=>{
    const matches=(host.matched_devices||[]).map(device=>`${esc(device.name)}${device.device_id?` · ${esc(device.device_id)}`:""}`).join("<br>")||"—";
    const conflict=host.mac&&conflicts.has(String(host.mac).toUpperCase());
    const stage=stageFor(host);
    const methods=(host.discovery_methods||[]).map(method=>({arp_sweep:"ARP ativo · resposta capturada",tcp:"TCP",icmp:"Ping",ssdp:"SSDP/UPnP",mdns:"mDNS/DNS-SD",arp_neighbor:"Tabela de vizinhos · IP respondeu"}[method]||method)).join(", ")||"—";
    const ipLabel=host.mac_ip_conflict?`IP ambíguo: ${(host.ip_candidates||[]).map(esc).join(", ")}`:esc(host.ip);
    return `<tr${conflict?' class="warning-row"':''} data-network-device-row="${index}" data-network-stage="${stage}"${lastLocalNetworkScanFilter!=="all"&&lastLocalNetworkScanFilter!==stage?' hidden':''}><td><span class="network-stage network-stage-${stage}">${stageLabel[stage]}</span></td><td>${ipLabel}${host.is_router?' <span class="source-tag">Router</span>':''}</td><td>${esc(host.mac||"MAC não visível")}${conflict?' <span class="source-tag">MAC em vários IPs</span>':''}</td><td>${esc(host.friendly_name||host.hostname||"—")}</td><td>${esc(host.manufacturer||"—")}</td><td>${esc(host.model||"—")}</td><td>${matches}</td><td>${esc(methods)}</td><td>${(host.open_ports||[]).map(port=>esc(port)).join(", ")||"—"}</td><td><button type="button" class="button secondary" data-network-device-open="${index}">${stage==="integrated"?"Ver associado":"Abrir / adicionar"}</button></td></tr>`;
  }).join("");
  const bluetoothRows=(report.blu_devices||[]).map((device,index)=>`<tr data-blu-device-row="${index}"><td>Via ponte · ${esc(device.bridge_name||device.bridge_model||"Shelly BLU Gateway")}</td><td>${esc(device.mac)}</td><td>${esc(device.name||"Sensor Bluetooth")}</td><td>${esc(device.manufacturer||"Shelly")}</td><td>${esc(device.model||"Shelly BLU")}</td><td>Sensor Bluetooth · ${esc(device.rssi??"—")} dBm</td><td>Bluetooth pela ponte</td><td>—</td><td><button type="button" class="button secondary" data-blu-device-open="${index}">Abrir / adicionar</button></td></tr>`).join("");
  const bridgeNotes=(report.blu_bridges||[]).map(item=>`${esc(item.name||"Ponte Shelly")}: ${item.state==="scanned"?"pesquisa concluída":item.reason||"não disponível"}`).join(" · ");
  const networks=(report.networks||[]).map(item=>`${esc(item.network)} · ${esc(item.interface)}`).join("; ")||"Nenhuma rede local IPv4 encontrada.";
  const interfaceAddresses=(report.interface_addresses||[]).map(item=>`${esc(item.interface)}: ${esc(item.address)} · ${esc(item.network)}`).join("; ");
  const skipped=(report.skipped_networks||[]).length?` Redes ignoradas por exceder o limite de ${esc(report.address_limit)} endereços: ${(report.skipped_networks||[]).map(esc).join(", ")}.`:"";
  const scanError=report.scan_error==="interface_discovery_failed"?"O Gateway não conseguiu ler as interfaces IPv4 do sistema, nem pelo comando de rede nem pela alternativa do sistema.":report.scan_error==="no_ipv4_address_on_interfaces"?"O Gateway não tem nenhum endereço IPv4 atribuído às interfaces de rede.":report.scan_error==="no_eligible_private_ipv4_network"?"O Gateway tem IPv4, mas não encontrou uma rede local privada diretamente ligada que possa varrer.":report.scan_error?`A pesquisa terminou com diagnóstico: ${esc(report.scan_error)}.`:"";
  const scanWarnings=(report.scan_warnings||[]).includes("active_arp_unavailable")?"O Gateway não conseguiu abrir a varredura ARP Ethernet nesta interface; os resultados podem ficar incompletos.":"";
  const matchedMacs=new Set((report.hosts||[]).filter(host=>host.mac&&!conflicts.has(String(host.mac).toUpperCase())&&(host.matched_devices||[]).length===1).map(host=>String(host.mac).toUpperCase()));
  const conflictNote=conflicts.size?`<p class="field-note" role="status">${conflicts.size} MAC(s) aparecem associados a vários IPs. Esses casos não serão guardados automaticamente; confirma a causa antes de corrigir a associação.</p>`:"";
  const box=(state.page==="devices"&&$("#device-add-results"))||$("#local-network-results");
  const routers=(report.router_ips||[]).map(esc).join(", ")||"Não identificado pela tabela de rotas do Gateway.";
  const filters=[["all","Todos"],["integrated","Associados"],["identified","Identidade provável"],["detected","Só detetados"],["ambiguous","Ambíguos"]].map(([key,label])=>`<button type="button" class="network-discovery-filter${lastLocalNetworkScanFilter===key?" active":""}" data-network-filter="${key}" aria-pressed="${lastLocalNetworkScanFilter===key}">${label} <span>${stageCounts[key]}</span></button>`).join("");
  box.innerHTML=`<p class="field-note">Redes verificadas: ${networks}. Endereços verificados: ${esc(report.scanned_count)}; dispositivos que responderam: ${esc(report.responsive_count)}. Router de saída indicado pela rota: ${routers}.${skipped}</p>${interfaceAddresses?`<p class="field-note">IPv4 atribuídos às interfaces: ${interfaceAddresses}.</p>`:""}${scanError?`<p class="field-note" role="status">${scanError}</p>`:""}${scanWarnings?`<p class="field-note" role="status">${scanWarnings}</p>`:""}${conflictNote}<div class="network-discovery-filters" role="group" aria-label="Filtrar dispositivos encontrados">${filters}</div><p class="field-note">“Associado” significa que o MAC corresponde a um dispositivo configurado ou guardado; esta pesquisa não testa o seu controlo. “Identidade provável” vem de anúncios/protocolos ou fabricante detetado. A confirmação do modelo e do controlo acontece ao abrir e validar o dispositivo.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Estado no SolarMiner</th><th>IP</th><th>MAC</th><th>Nome / hostname</th><th>Fabricante</th><th>Modelo</th><th>Device associado</th><th>Detetado por</th><th>Portas abertas</th><th>Ação</th></tr></thead><tbody>${hostRows||'<tr><td colspan="10">Nenhum dispositivo respondeu nesta pesquisa.</td></tr>'}${bluetoothRows}</tbody></table></div>${bridgeNotes?`<p class="field-note">Pontes Bluetooth: ${bridgeNotes}.</p>`:""}<p class="field-note">Usa “Abrir / adicionar” para rever e guardar. Equipamentos guardados continuam no inventário mesmo quando não aparecem numa pesquisa posterior. O scanner usa ARP ativo, ICMP, TCP, SSDP/UPnP e mDNS/DNS-SD; pesquisa endereços IPv4 diretamente ligados ao Gateway. Sensores Shelly BLU só aparecem aqui se tiverem sido observados recentemente; para nova pesquisa, usa a opção na ficha da ponte compatível.</p>`;
  box.hidden=false;
  box.querySelectorAll("[data-network-filter]").forEach(button=>button.addEventListener("click",event=>{event.preventDefault();event.stopPropagation();lastLocalNetworkScanFilter=button.dataset.networkFilter||"all";renderLocalNetworkResults(lastLocalNetworkScanReport);}));
  box.querySelectorAll("[data-network-device-open]").forEach(button=>button.addEventListener("click",event=>{event.preventDefault();event.stopPropagation();try{openLocalNetworkDeviceDetails(Number(button.dataset.networkDeviceOpen));}catch(error){const status=$(state.page==="devices"?"#device-add-status":"#local-network-status");if(status)status.textContent=`Não foi possível abrir o equipamento: ${error.message||"erro da interface."}`;}}));
  box.querySelectorAll("[data-blu-device-open]").forEach(button=>button.addEventListener("click",event=>{event.preventDefault();event.stopPropagation();try{openBluDeviceDetails(Number(button.dataset.bluDeviceOpen));}catch(error){const status=$(state.page==="devices"?"#device-add-status":"#local-network-status");if(status)status.textContent=`Não foi possível abrir o sensor: ${error.message||"erro da interface."}`;}}));
  return matchedMacs.size;
}
function openLocalNetworkDeviceDetails(index,hostOverride=null){
  const host=hostOverride||lastLocalNetworkScanReport?.hosts?.[index];
  if(!host)return;
  const dialog=$("#network-device-detail-dialog");
  // A double-click emits two click events. The first opens this modal; ignore
  // the second instead of calling showModal() on an already-open dialog.
  if(dialog.open)return;
  dialog.dataset.transport=host.transport||"lan";
  $("#network-device-detail-ip-label").hidden=false;$("#network-device-detail-ip-input").hidden=false;
  $("#network-device-detail-bridge").hidden=false;
  const ip=host.mac_ip_conflict?`Ambíguo: ${(host.ip_candidates||[]).join(", ")||"vários IPs"}`:(host.ip||"—");
  const match=(host.matched_devices||[])[0]||{};
  $("#network-device-detail-ip").textContent=ip;
  $("#network-device-detail-mac").textContent=host.mac||"Não visível na descoberta; podes introduzir o MAC manualmente.";
  $("#network-device-detail-mac-source").textContent=host.mac_source==="active_arp"?"Resposta ARP capturada nesta pesquisa":host.mac_source==="neighbor_table"?"Tabela de vizinhos; o IP respondeu nesta pesquisa":"Sem MAC confirmado nesta pesquisa";
  $("#network-device-detail-discovery").textContent=(host.discovery_methods||[]).map(method=>({arp_sweep:"ARP ativo",tcp:"TCP",icmp:"Ping",ssdp:"SSDP/UPnP",mdns:"mDNS/DNS-SD",arp_neighbor:"Tabela de vizinhos"}[method]||method)).join(", ")||"—";
  $("#network-device-detail-name").value=match.name||host.friendly_name||host.hostname||"";
  $("#network-device-detail-ip-input").value=host.mac_ip_conflict?"":host.ip||"";
  $("#network-device-detail-mac-input").value=host.mac||"";
  const matchedTuya=state.tuyaDevices.find(device=>device.device_id===(match.device_id||match.source_device_id));
  const detectedManufacturer=String(host.manufacturer||matchedTuya?.manufacturer||"").toLowerCase();
  const maker=$("#network-device-detail-manufacturer");
  maker.value=/shelly/.test(detectedManufacturer)?"Shelly":/tuya/.test(detectedManufacturer)?"Tuya":/moes/.test(detectedManufacturer)?"MOES":/deye/.test(detectedManufacturer)?"Deye":/antminer|bitmain/.test(detectedManufacturer)?"Antminer":"";
  const typeSelector=$("#network-device-detail-type");
  const updateProductChoices=()=>{
    $("#network-device-shelly-credentials").hidden=maker.value!=="Shelly";
    const groups={
      "Shelly":[["smart_relay","Relé inteligente"],["smart_metered_relay","Relé com medição"],["smart_dimmer","Dimmer de luz"],["smart_rgb_light","Luz RGB/RGBW"],["smart_cct_light","Luz branca regulável"],["smart_sensor","Sensor"],["smart_blugw","Gateway de sensores BLU"]],
      "Tuya":[["smart_breaker_metered","Disjuntor com medição"],["smart_relay","Relé/interruptor"],["smart_socket_metered","Tomada com medição"],["smart_dimmer","Dimmer"],["smart_rgb_light","Lâmpada RGB/RGBW"],["smart_cct_light","Lâmpada branca regulável"],["smart_sensor","Sensor"],["smart_hub","Hub/gateway"]],
      "MOES":[["smart_breaker_metered","Disjuntor com medição"],["smart_relay","Relé/interruptor"],["smart_dimmer","Dimmer"],["smart_rgb_light","Lâmpada RGB/RGBW"],["smart_sensor","Sensor"],["smart_hub","Hub/gateway"]],
      "Deye":[["inverter","Inversor"],["smart_meter","Medidor de energia"],["smart_battery","Bateria"]],
      "Antminer":[["miner","Mineradora ASIC"]],"Braiins":[["miner","Mineradora ASIC"]],
      "Outro":[["smart","Dispositivo inteligente"],["router","Router"],["computer","Computador"],["phone","Telemóvel"],["printer","Impressora"],["other","Outro"]]
    };
    const manufacturer=maker.value,choices=groups[manufacturer]||[["smart","Dispositivo inteligente"],["router","Router"],["other","Outro"]],previous=match.device_type||typeSelector.value;
    typeSelector.innerHTML=`<option value="unknown">Por identificar</option>${choices.map(([value,label])=>`<option value="${value}">${label}</option>`).join("")}`;
    if(choices.some(([value])=>value===previous))typeSelector.value=previous;else if(host.is_router)typeSelector.value="router";
    const catalogSelect=$("#network-device-detail-catalog-product"),catalog=Array.isArray(state.smartProductCatalog)?state.smartProductCatalog:[];
    const isTuyaProtocol=["Tuya","MOES"].includes(manufacturer);
    const products=catalog.filter(item=>isTuyaProtocol?String(item.protocol||"").toLowerCase()==="tuya":String(item.manufacturer||"").toLowerCase()===manufacturer.toLowerCase());
    const selectedProduct=catalogSelect.value;
    catalogSelect.innerHTML=`<option value="">Seleciona um produto conhecido ou introduz o modelo abaixo</option>${products.map(item=>`<option value="${esc(item.product_code)}">${esc(item.product_name||item.product_code)}${item.confidence==="family_only"?" · família":""}</option>`).join("")}`;
    if(products.some(item=>String(item.product_code)===selectedProduct))catalogSelect.value=selectedProduct;
    catalogSelect.onchange=()=>{const item=products.find(entry=>String(entry.product_code)===catalogSelect.value);if(!item)return;$("#network-device-detail-model").value=item.product_name||item.product_code;const option=Array.from(typeSelector.options).find(entry=>entry.value===item.device_kind);if(option)typeSelector.value=item.device_kind;if(String(item.protocol||"").toLowerCase()==="tuya")$("#network-device-detail-product-id").value=item.product_code;};
    $("#network-device-product-id-wrap").hidden=!(["Tuya","MOES"].includes(manufacturer));
    $("#network-device-detail-model").placeholder=manufacturer==="Shelly"?"Ex.: Shelly Plus 1PM, Dimmer, RGBW2":"Modelo comercial ou família do produto";
  };
  maker.onchange=updateProductChoices;updateProductChoices();
  // The catalog is fetched asynchronously when entering Devices. Refresh it
  // for this editor too, then repopulate a still-open product selector.
  if(sessionInfo().user?.role==="owner")void refreshSmartProductCatalog().then(ok=>{if(ok&&dialog.open)updateProductChoices();});
  $("#network-device-detail-model").value=host.model||matchedTuya?.model||"";
  $("#network-device-detail-product-id").value=matchedTuya?.product_id||matchedTuya?.productId||"";
  $("#network-device-detail-detected-manufacturer").textContent=host.manufacturer||"—";
  $("#network-device-detail-detected-model").textContent=host.model||"—";
  const bridge=host.shelly_bluetooth_bridge;
  const bridgeStatus=bridge?.bthome_discovery_api==="available"?"Ponte Bluetooth local confirmada. O Gateway pode procurar sensores.":bridge?.bthome_discovery_api==="authentication_required"?"A ponte exige autenticação para verificar a API BTHome; a pesquisa BLE é verificada separadamente.":bridge?.bthome_discovery_api==="probe_failed"?"O Gateway identificou uma possível ponte, mas não conseguiu verificar a API BTHome. Isto não confirma falha da pesquisa BLE.":bridge?.bthome_discovery_api==="not_supported"?"A API BTHome não foi confirmada. Isto não prova que o scanner BLE por script não funcione; a compatibilidade é verificada ao procurar sensores.":bridge?.candidate?"A ponte foi identificada; a compatibilidade da pesquisa BLE é verificada ao procurar sensores.":"Não foi identificada uma ponte de sensores compatível neste endereço.";
  if($("#network-device-detail-bridge"))$("#network-device-detail-bridge").textContent=bridgeStatus;
  $("#network-device-detail-recognized").textContent=match.name?(match.device_id?`${match.name} · ${match.device_id}`:match.name):"Ainda não associado a um equipamento guardado.";
  $("#network-device-detail-save").disabled=false;
  dialog.dataset.hostIndex=String(index);
  dialog.showModal();
}
function openBluDeviceDetails(index){
  const device=lastLocalNetworkScanReport?.blu_devices?.[index];
  if(!device)return;
  const host={transport:"blu",ip:"",mac:device.mac,manufacturer:device.manufacturer==="Shelly"?"Shelly":"",model:device.model||"Shelly BLU",protocol:device.protocol,
    discovery_methods:["shelly_blu_gateway_ble"],friendly_name:device.name||device.model||"Sensor Shelly BLU",device_type:device.device_type||"smart_sensor",
    bridge_mac:device.bridge_mac,bridge_name:device.bridge_name,matched_devices:[{device_type:device.device_type||"smart_sensor"}]};
  openLocalNetworkDeviceDetails(-1,host);
  const dialog=$("#network-device-detail-dialog");dialog.dataset.transport="blu";dialog.dataset.bluMac=device.mac;dialog.dataset.bridgeMac=device.bridge_mac||"";
  $("#network-device-detail-ip-label").hidden=true;$("#network-device-detail-ip-input").hidden=true;
  $("#network-device-detail-ip").textContent=`Sensor recebido pela ponte ${device.bridge_name||"Shelly BLU Gateway"}; não tem IP próprio.`;
  $("#network-device-detail-mac-source").textContent="Anúncio Bluetooth recebido pela ponte Shelly";
  $("#network-device-detail-bridge").hidden=true;
  $("#network-device-shelly-credentials").hidden=true;
  $("#network-device-detail-save").disabled=false;
}
$("#local-network-results").addEventListener("click",event=>{
  const row=event.target.closest("[data-network-device-row]");
  if(row)openLocalNetworkDeviceDetails(Number(row.dataset.networkDeviceRow));
  const blu=event.target.closest("[data-blu-device-row]");
  if(blu)openBluDeviceDetails(Number(blu.dataset.bluDeviceRow));
});
$("#local-network-results").addEventListener("keydown",event=>{
  if(!["Enter"," "].includes(event.key))return;
  const row=event.target.closest("[data-network-device-row]");
  if(row){event.preventDefault();openLocalNetworkDeviceDetails(Number(row.dataset.networkDeviceRow));return;}
  const blu=event.target.closest("[data-blu-device-row]");
  if(blu){event.preventDefault();openBluDeviceDetails(Number(blu.dataset.bluDeviceRow));}
});
$("#network-device-detail-close").addEventListener("click",()=>$("#network-device-detail-dialog").close());
$("#network-device-detail-cancel").addEventListener("click",()=>$("#network-device-detail-dialog").close());
$("#network-device-detail-save").addEventListener("click",async event=>{
  const button=event.currentTarget,dialog=$("#network-device-detail-dialog"),statusSelector=$("#local-network-status")?"#local-network-status":"#device-add-status",status=$(statusSelector);
  const host=dialog.dataset.transport==="blu"?
    (lastLocalNetworkScanReport?.blu_devices||[]).find(item=>String(item.mac||"").toUpperCase()===String(dialog.dataset.bluMac||"").toUpperCase()):
    lastLocalNetworkScanReport?.hosts?.[Number(dialog.dataset.hostIndex)];
  const manufacturer=$("#network-device-detail-manufacturer").value;
  const ip=$("#network-device-detail-ip-input").value.trim(),mac=$("#network-device-detail-mac-input").value.trim().toUpperCase();
  const deviceType=$("#network-device-detail-type").value,model=$("#network-device-detail-model").value.trim(),productId=$("#network-device-detail-product-id").value.trim();
  if(dialog.dataset.transport==="blu"){
    if(!ownerCanManageHardware(statusSelector))return;
    button.disabled=true;button.textContent="A confirmar pela ponte…";
    try{const saved=await registerGatewayShellyBluDevice({mac:host.mac,name:$("#network-device-detail-name").value||host.friendly_name,device_type:deviceType,bridge_mac:host.bridge_mac});
      host.matched_devices=[{name:saved.device.name,device_id:saved.device.source_device_id,provider:"shelly_blu",device_type:saved.device.device_type,manufacturer:"Shelly",model:saved.device.model}];
      try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* Sensor registration succeeded; refresh the common inventory later. */}
      await refreshShellyInventoryStatus({quiet:true});
      renderLocalNetworkResults(lastLocalNetworkScanReport);status.textContent=`Sensor guardado no inventário pelo MAC ${saved.device.mac}; ponte ${saved.bridge.name}.`;
      dialog.close();
    }catch(error){status.textContent=`Não foi possível registar o sensor Bluetooth: ${error.message||"a ponte não confirmou o dispositivo."}`;}
    finally{button.disabled=false;button.textContent="Guardar equipamento";}
    return;
  }
  if(!ip||!mac){status.textContent="Preenche o IP e o MAC. O Gateway voltará a confirmar o par antes de guardar.";return;}
  if(["Tuya","MOES"].includes(manufacturer)&&!productId){status.textContent="Para adicionar como Tuya/MOES com suporte ao mapa, indica o Product ID exato. Sem ele não aplico nem infiro nenhum mapa DPS.";return;}
  if(manufacturer==="Shelly"){
    if(!ownerCanManageHardware(statusSelector))return;
    button.disabled=true;button.textContent="A identificar Shelly…";
    try{const saved=await registerGatewayShellyDevice({name:$("#network-device-detail-name").value||host.friendly_name||host.hostname||"Shelly",host:ip,mac,device_type:deviceType,username:$("#network-device-detail-shelly-username").value,password:$("#network-device-detail-shelly-password").value});$("#network-device-detail-shelly-password").value="";host.mac=saved.device.mac;host.ip=saved.device.last_ip||ip;host.manufacturer="Shelly";host.model=saved.device.model||model||host.model;host.mac_source="shelly_device_info";host.matched_devices=[{name:saved.device.name,device_id:saved.device.source_device_id,provider:"shelly",device_type:deviceType,manufacturer:"Shelly",model:saved.device.model}];const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];await refreshShellyInventoryStatus({quiet:true});renderLocalNetworkResults(lastLocalNetworkScanReport);status.textContent=`Teste LAN confirmado: Shelly identificado por MAC ${saved.device.mac}; protocolo ${saved.reading.protocol||"detetado"}.`;dialog.close();}
    catch(error){status.textContent=`Não foi possível identificar/registar o Shelly: ${error.message}`;}
    finally{button.disabled=false;button.textContent="Guardar equipamento";}
    return;
  }
  if(!ownerCanManageHardware(statusSelector))return;
  button.disabled=true;button.textContent="A guardar…";
  try{
    const result=await saveGatewayLocalNetworkDevice({mac,ip,name:$("#network-device-detail-name").value,device_type:deviceType,manufacturer,model,product_id:productId});
    host.matched_devices=[{name:result.device.name,device_id:result.device.source_device_id||null,provider:result.device.source_provider||"local",device_type:result.device.device_type,local_mac:result.device.mac}];
    if(!host.mac_ip_conflict&&result.device.last_ip)host.ip=result.device.last_ip;
    try{const inventory=await readGatewayDeviceInventory();state.gatewayDeviceInventory=Array.isArray(inventory.devices)?inventory.devices:[];}catch{/* The save succeeded; the next Devices refresh will reload the inventory. */}
    renderLocalNetworkResults(lastLocalNetworkScanReport);
    const lanProbe=result.tuya_lan_probe,association=result.tuya_association;
    const tuyaResult=association?.state==="verified"?" Leitura DPS local validada; o equipamento está associado e pronto para controlo.":association?.state==="dps_read_failed"?" A identidade foi guardada, mas a leitura DPS com a chave sincronizada falhou; o controlo continua indisponível.":association?.state==="ambiguous_key_match"?" A identidade foi guardada, mas mais de uma chave local respondeu; não foi feita uma associação automática.":association?.state==="too_many_cloud_candidates"?" A identidade foi guardada, mas há demasiados dispositivos cloud compatíveis para escolher uma chave com segurança.":association?.state==="cloud_sync_unavailable"?" A identidade foi guardada, mas não foi possível sincronizar a conta Tuya para obter a chave local.":association?.state==="no_local_key"||association?.state==="no_matching_cloud_device"?" A identidade foi guardada, mas não foi encontrada uma chave local sincronizada compatível; o controlo continua indisponível.":lanProbe?(lanProbe.state==="lan_reachable"?" A porta Tuya respondeu; falta validar uma chave local para ler DPS e controlar.":lanProbe.state==="lan_host_responded"?" O IP respondeu, mas a porta Tuya está fechada.":" A pesquisa confirmou o IP/MAC, mas a porta Tuya não respondeu."):"";
    status.textContent=result.ambiguous_ip?"Nome guardado. O MAC foi encontrado, mas o Gateway viu vários IPs possíveis; o IP não foi confirmado.":`Equipamento identificado e guardado. IP ${result.device.last_ip||ip} e MAC ${mac} confirmados.${tuyaResult}`;
    dialog.close();
  }catch(error){status.textContent=`Não foi possível guardar o equipamento: ${error.message||"falha na gravação local."}`;}
  finally{button.disabled=false;button.textContent="Guardar equipamento";}
});
$("#local-network-scan").addEventListener("click",async event=>{
  const button=event.currentTarget,status=$("#local-network-status"),results=$("#local-network-results");
  if(!ownerCanManageHardware("#local-network-status"))return;
  button.disabled=true;results.hidden=true;status.textContent="A verificar a LAN e a atualizar IPs por MAC único…";
  try{
    const report=await scanGatewayLocalNetwork();
    const matched=renderLocalNetworkResults(report);
    const updated=Number(report.configured_ip_update_count)||0,ambiguous=Number(report.ambiguous_configured_mac_count)||0;
    status.textContent=`Pesquisa concluída: ${report.responsive_count||0} dispositivo(s) responderam; ${matched} correspondência(s) por MAC; ${updated} IP(s) atualizado(s) automaticamente${ambiguous?`; ${ambiguous} MAC(s) ambíguos ignorados`:""}.`;
  }catch(error){status.textContent=`A pesquisa falhou: ${error.message||"o Gateway não conseguiu verificar a rede."}`;}
  finally{button.disabled=false;}
});
$("#deye-read").addEventListener("click", () => readHardwareProvider("deye"));
$("#tuya-device-list").addEventListener("click", async event => {
  const card=event.target.closest('.tuya-device-card');
  if(card&&!event.target.closest('button')){openFavoriteDeviceDetails(card.dataset.tuyaDevice,"tuya");return;}
  const edit = event.target.closest("[data-edit-tuya-device]"), read = event.target.closest("[data-tuya-read]"), toggle = event.target.closest("[data-tuya-switch]");
  if (edit) { const device=state.tuyaDevices.find(item=>item.device_id===edit.dataset.editTuyaDevice); if(device)openTuyaDeviceEditor(device); return; }
  if (read) {
    const id = read.dataset.tuyaRead, status=$(`[data-tuya-status="${CSS.escape(id)}"]`);
    read.disabled = true;if(status)status.textContent="A testar apenas a resposta LAN deste equipamento…";
    try{const {reading,result}=await testTuyaLanReachability(id);state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==id),reading];if(status)status.textContent=result.connection_state==="lan_reachable"?`Resposta LAN confirmada · ${Number(result.latency_ms)||0} ms · sem leitura DPS`:result.connection_state==="lan_host_responded"?"O IP respondeu, mas a porta Tuya está fechada.":`Sem resposta LAN · ${tuyaLanReasonText(result.reason||"tuya_connection_failed")}`;renderTuyaDeviceCards(state.tuyaDevices||[]);}catch(error){if(status)status.textContent=`Falha ao testar resposta LAN: ${error.message}`;}finally{read.disabled=false;}
  } else if (toggle) await sendTuyaSwitch(toggle.dataset.deviceId, toggle.dataset.tuyaSwitch === "on", toggle);
});
$("#tuya-device-list").addEventListener("keydown",event=>{if(!["Enter"," "].includes(event.key)||event.target.closest("button"))return;const card=event.target.closest(".tuya-device-card");if(!card)return;event.preventDefault();openFavoriteDeviceDetails(card.dataset.tuyaDevice,"tuya");});
async function sendTuyaSwitch(deviceId, on, button) {
  if (!ownerCanManageHardware("#tuya-status")) return;
  const card = button.closest(".tuya-device-card"), name = card.querySelector("h4")?.textContent || deviceId;
  if (!window.confirm(`Confirmas que queres ${on ? "ligar" : "desligar"} ${name}?`)) return;
  const buttons = [...card.querySelectorAll("button[data-tuya-switch]")]; buttons.forEach(item => { item.disabled = true; });
  const status = card.querySelector("[data-tuya-status]"); status.textContent = `A enviar comando para ${name}…`;
  try {
    const device=state.tuyaDevices.find(item=>item.device_id===deviceId),code=device?.switch_code||"switch";
    if(!device)throw new Error("Dispositivo não encontrado no inventário atual.");
    const result = await sendTuyaSwitchCommand(device,code,on);
    if(!result.command_accepted)throw new Error("O Gateway não aceitou o comando.");
    status.textContent = `Ordem de ${on?"ligar":"desligar"} enviada para ${name}. O estado será atualizado pelo varrimento independente.`;
  } catch (error) { status.textContent = `Falha no comando Tuya: ${error.message}`; }
  finally { buttons.forEach(item => { item.disabled = false; }); }
}

async function refreshTeslaEvConfig() {
  const info = sessionInfo(), status = $("#ev-tesla-status"), readStatus = $("#ev-tesla-read-status");
  const save = $("#ev-tesla-fleet-save"), read = $("#ev-tesla-read"), presence = $("#ev-tesla-presence");
  if (!info.authenticated || info.user.role !== "owner") {
    if (status) status.textContent = "Só o Owner autenticado pode configurar Tesla Fleet.";
    if (readStatus) readStatus.textContent = "A leitura Tesla está disponível apenas ao Owner autenticado.";
    if (save) save.disabled = true; if (read) read.disabled = true; if (presence) presence.disabled = true; return;
  }
  if (save) save.disabled = false; if (read) read.disabled = false; if (presence) presence.disabled = false;
  const config = await readGatewayTeslaEvConfig();
  teslaConfiguredCallback = config.oauth_redirect_uri || "";
  for (const id of ["ev-tesla-callback", "ev-tesla-help-callback"]) { const field = $("#" + id); if (field) field.value = teslaGatewayCallbackUrl(); }
  const localMac = $("#ev-tesla-local-mac"); if (localMac) localMac.value = config.local_mac || "";
  const relayUrl = $("#ev-tesla-relay-url"), relayStatus = $("#ev-tesla-relay-status"); if (relayUrl && config.relay_url) relayUrl.value = config.relay_url; if (relayStatus) relayStatus.textContent = config.relay_configured ? "Relay HTTPS configurado. A chave fica privada no Gateway." : "Relay ainda não configurado. A VM e o certificado HTTPS são necessários antes do OAuth.";
  const presenceStatus = $("#ev-tesla-presence-status"); if (presenceStatus && config.local_presence) presenceStatus.textContent = teslaPresenceText(config.local_presence);
  const region = $("#ev-tesla-region"), client = $("#ev-tesla-client-id"), token = $("#ev-tesla-refresh-token"), vehicle = $("#ev-tesla-vehicle-id");
  if (region) region.value = config.region || "europe"; if (client) client.value = config.client_id || "";
  if (token) { token.value = ""; token.placeholder = config.configured ? "Token guardado; deixa vazio para manter" : "Refresh token autorizado"; } if (vehicle) vehicle.value = (config.vehicle_ids || [])[0] || "";
  const message = config.configured ? "Tesla Fleet configurado no Gateway. O token é privado e não é devolvido à PWA." : "Tesla Fleet ainda não configurado. Indica a aplicação Fleet autorizada e o veículo.";
  if (status) status.textContent = message; if (readStatus) readStatus.textContent = config.configured ? "Ligação Tesla Fleet pronta para consultar o estado do veículo." : message;
}

document.querySelector("#gateway-hardware-management")?.addEventListener("click", async event => {
  const button = event.target.closest("#ev-tesla-fleet-save"); if (!button) return;
  event.preventDefault();
  const status = $("#ev-tesla-status"), info = sessionInfo();
  if (!status) return;
  if (!info.authenticated || info.user.role !== "owner") { status.textContent = "Só o Owner autenticado pode guardar Tesla Fleet."; return; }
  const clientId = $("#ev-tesla-client-id").value.trim(), vehicleId = $("#ev-tesla-vehicle-id").value.trim();
  const refreshToken = $("#ev-tesla-refresh-token").value;
  const mac = $("#ev-tesla-local-mac").value.trim().toUpperCase();
  if (!clientId) { status.textContent = "Indica o Client ID da aplicação Tesla Fleet."; return; }
  if (!vehicleId) { status.textContent = "Indica o ID Tesla ou VIN do veículo."; return; }
  if (mac && !/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac)) { status.textContent = "O MAC deve ter o formato AA:BB:CC:11:22:33."; return; }
  button.disabled = true; status.textContent = "A guardar a configuração Fleet e a associar o MAC ao inventário…";
  let saved = false;
  try {
    const config = await saveGatewayTeslaEvConfig({region: $("#ev-tesla-region").value, client_id: clientId, refresh_token: refreshToken, vehicle_ids: [vehicleId], ...(mac ? {local_mac: mac} : {})});
    saved = true; $("#ev-tesla-refresh-token").value = "";
    if (!config.configured) throw new Error("O Gateway não confirmou a configuração como completa.");
    let inventoryMessage = mac ? " O MAC foi guardado e o inventário será atualizado." : " Indica o MAC Wi-Fi para listar o Tesla em Devices.";
    try { const inventory = await readGatewayDeviceInventory(); state.gatewayDeviceInventory = Array.isArray(inventory.devices) ? inventory.devices : []; const linked = Boolean(mac && state.gatewayDeviceInventory.some(item => item.source_provider === "tesla" && String(item.mac || "").toUpperCase() === mac)); if (linked) inventoryMessage = " O Tesla também foi associado ao inventário Devices pelo MAC."; } catch { inventoryMessage = mac ? " O MAC ficou guardado; não foi possível atualizar agora a lista Devices." : inventoryMessage; }
    status.textContent = "Configuração guardada. A testar agora a ligação Fleet…";
    const result = await readGatewayTeslaEvCharging();
    const vehicles = Array.isArray(result.vehicles) ? result.vehicles : [];
    status.textContent = "Guardado e ligação Fleet testada: " + vehicles.length + " veículo(s) consultado(s)." + inventoryMessage + " Não foram enviados comandos ao carro.";
  } catch (error) {
    status.textContent = saved ? "Configuração guardada, mas o teste Fleet falhou: " + error.message + ". A configuração permanece no Gateway." : "Não foi possível guardar a ligação Tesla Fleet: " + error.message;
  } finally { button.disabled = false; }
});

function teslaPresenceText(result) {
  const messages = {
    DETECTED: "Tesla encontrado na rede local" + (result.ip ? " · IP " + result.ip : ""),
    NOT_DETECTED: "O Gateway não aprendeu o MAC na rede local; o Tesla pode estar em repouso.",
    NOT_CONFIGURED: "Introduz e guarda o MAC Wi-Fi do Tesla primeiro.",
    UNKNOWN: "O Gateway não conseguiu confirmar a presença na rede local."
  };
  return (messages[result.state] || "Presença sem confirmação") + (result.checked_at ? " · " + new Date(result.checked_at).toLocaleString("pt-PT") : "");
}

$("#page-content").addEventListener("click", async event => {
  const addScan=event.target.closest("#device-add-scan");
  if(addScan){
    if(!ownerCanManageHardware("#device-add-status"))return;
    const status=$("#device-add-status"),results=$("#device-add-results");
    addScan.disabled=true;results.hidden=true;status.textContent="A procurar na rede e a ouvir as pontes Shelly BLU até 30 segundos. Mantém o sensor perto da ponte e ativa-o durante a procura; em sensores com botão, carrega uma vez.";
    try{const report=await scanGatewayLocalNetwork();const matches=renderLocalNetworkResults(report);status.textContent=`Pesquisa concluída: ${Number(report.responsive_count)||0} equipamentos LAN e ${(report.blu_devices||[]).length} sensores Bluetooth; ${matches} já correspondem ao inventário. Abre uma linha para guardar.`;}
    catch(error){status.textContent=`Não foi possível concluir a pesquisa: ${error.message||"o Gateway não respondeu."}`;}
    finally{if(addScan.isConnected)addScan.disabled=false;}
    return;
  }
  const bluBridgeDiscover=event.target.closest("[data-shelly-blu-discover]");
  if(bluBridgeDiscover){
    if(!ownerCanManageHardware("#device-add-status"))return;
    const bridge=state.shellyDevices.find(item=>item.device_id===bluBridgeDiscover.dataset.shellyBluDiscover);
    if(!bridge)return;
    state.devicesTab="add";render();
    const status=$("#device-add-status"),results=$("#device-add-results");
    if(!status||!results)return;
    results.hidden=true;status.textContent=`A ouvir ${bridge.name||"esta ponte Shelly BLU"} até 30 segundos. Mantém o sensor perto da ponte e ativa-o durante a procura; em sensores com botão, carrega uma vez.`;
    try{
      const result=await discoverGatewayShellyBluDevices(bridge.device_id);
      const report={hosts:[],blu_devices:Array.isArray(result.devices)?result.devices:[],blu_bridges:[result.bridge||{}],
        networks:[],skipped_networks:[],scanned_count:0,responsive_count:0};
      renderLocalNetworkResults(report);
      const count=report.blu_devices.length,reason=result.bridge?.reason,diagnostic=result.bridge?.diagnostic||{};
      const diagnosticText=[diagnostic.scanner_is_running!==undefined?`scanner ativo: ${diagnostic.scanner_is_running}`:"",diagnostic.start_result?`pedido de pesquisa: ${diagnostic.start_result}`:"",diagnostic.failed_stage?`falhou em: ${diagnostic.failed_stage}`:"",diagnostic.error?`erro: ${diagnostic.error}`:"",diagnostic.rpc_code!==undefined?`RPC ${diagnostic.rpc_code}${diagnostic.rpc_message?` · ${diagnostic.rpc_message}`:""}`:"",diagnostic.advertisement_count!==undefined?`anúncios BLE: ${diagnostic.advertisement_count}`:"",diagnostic.matching_advertisement_count!==undefined?`anúncios compatíveis: ${diagnostic.matching_advertisement_count}`:""].filter(Boolean).join(" · ");
      status.textContent=count?`${count} sensor${count===1?"":"es"} encontrado${count===1?"":"s"} por ${bridge.name||"esta ponte"}. Abre uma linha para guardar.`:
        `A ponte ${bridge.name||"Shelly BLU"} respondeu, mas não recebeu anúncios do sensor. A pesquisa já dura até 30 segundos; aproxima e ativa o sensor durante a procura.${reason?` Resultado: ${reason.replaceAll("_"," ")}.`:""}${diagnosticText?` Detalhe da ponte: ${diagnosticText}.`:""}`;
    }catch(error){status.textContent=`Não foi possível procurar sensores pela ponte ${bridge.name||"Shelly BLU"}: ${error.message||"o Gateway não respondeu."}`;}
    return;
  }
  const addBluRow=event.target.closest("#device-add-results [data-blu-device-row]");
  if(addBluRow){openBluDeviceDetails(Number(addBluRow.dataset.bluDeviceRow));return;}
  const addScanRow=event.target.closest("#device-add-results [data-network-device-row]");
  if(addScanRow){openLocalNetworkDeviceDetails(Number(addScanRow.dataset.networkDeviceRow));return;}
  const shellyDiscover=event.target.closest("#shelly-discover");
  if(shellyDiscover){const status=$("#shelly-register-status");shellyDiscover.disabled=true;if(status)status.textContent="A procurar Shelly nas redes diretamente ligadas ao Gateway…";try{const result=await discoverGatewayShellyDevices();state.shellyDiscovered=Array.isArray(result.devices)?result.devices:[];render();const nextStatus=$("#shelly-register-status");if(nextStatus)nextStatus.textContent=`Pesquisa LAN concluída: ${state.shellyDiscovered.length} Shelly encontrados. Seleciona um IP para preencher o registo.`;}catch(error){if(status)status.textContent=`A descoberta Shelly falhou: ${error.message}`;}finally{const button=$("#shelly-discover");if(button)button.disabled=false;}return;}
  const shellyCandidate=event.target.closest("[data-shelly-candidate]");
  if(shellyCandidate){const item=state.shellyDiscovered[Number(shellyCandidate.dataset.shellyCandidate)];if(item){$("#shelly-register-host").value=item.ip||"";$("#shelly-register-name").value=item.friendly_name||item.model||"Shelly";$("#shelly-register-status").textContent=`IP ${item.ip} selecionado. O Gateway vai confirmar o MAC diretamente no Shelly ao guardar.`;$("#shelly-register-name").focus();}return;}
  const shellyFavorite=event.target.closest("[data-shelly-favorite-toggle]");
  if(shellyFavorite){if(!sessionInfo().authenticated){showFeatureNotice("Inicia sessão para gerir os teus favoritos.");return;}const id=shellyFavorite.dataset.shellyFavoriteToggle,favorites=workspace.prefs.favoriteDeviceIds||[],isFavorite=favorites.includes(id),metadata=favoriteMeta();if(isFavorite)workspace.prefs.favoriteDeviceIds=favorites.filter(item=>item!==id);else{addHomeFavoriteId(id);metadata[id]={...(metadata[id]||{}),kind:"shelly"};saveFavoriteMeta(metadata);}saveDemoWorkspace();render();return;}
  const shellyRefresh=event.target.closest("#shelly-refresh");
  if(shellyRefresh){const status=$("#shelly-register-status");shellyRefresh.disabled=true;if(status)status.textContent="A ler estados reais pela LAN…";const ok=await refreshShellyInventoryStatus();if(status)status.textContent=ok?"Leitura concluída pelo Gateway. Estados e medições foram atualizados.":"A leitura falhou. Confirma se o Gateway alcança a LAN do Shelly.";shellyRefresh.disabled=false;return;}
  const shellySwitch=event.target.closest("[data-shelly-switch]");
  if(shellySwitch){
    if(!ownerCanManageHardware("#shelly-register-status"))return;
    const deviceId=shellySwitch.dataset.shellySwitch,channel=Number(shellySwitch.dataset.shellyChannel),on=shellySwitch.dataset.shellyTarget==="on",device=state.shellyDevices.find(item=>item.device_id===deviceId);
    if(!device)return;
    const componentName=shellyDeviceComponent(device,"switch",channel)?"switch":"relay",key=shellyPendingKey(deviceId,componentName,channel),pending={deviceId,component:componentName,channel,value:on,requestedAt:Date.now(),lastObservedAt:shellyObservationMs(device),mismatchCount:0};pendingShellyCommands.set(key,pending);updateVisibleShellyCard(deviceId);
    const started=performance.now();try{const result=await controlGatewayShellySwitch(deviceId,channel,on),sentMs=Math.round(performance.now()-started),deviceMs=Math.round(Number(result.device_command_latency_ms)||0),readMs=Math.round(Number(result.readback_latency_ms)||0),current=pendingShellyCommands.get(key);if(current){current.inFlight=false;current.gatewayAccepted=true;}const feedback=document.querySelector(`[data-smart-device="${CSS.escape(deviceId)}"] [data-shelly-card-feedback]`);if(feedback)feedback.textContent=result.command_confirmed?`Gateway confirmou; a aguardar a próxima leitura LAN · ${deviceMs} ms`:`Ordem enviada · ${deviceMs} ms · a confirmar pela LAN`;void refreshShellyInventoryStatus({quiet:true});}
    catch(error){const current=pendingShellyCommands.get(key);if(current){current.inFlight=false;current.outcomeUnknown=true;}const feedback=document.querySelector(`[data-smart-device="${CSS.escape(deviceId)}"] [data-shelly-card-feedback]`);if(feedback)feedback.textContent="Gateway sem resposta; ordem possivelmente enviada, a confirmar pela leitura LAN.";void refreshShellyInventoryStatus({quiet:true});}
    window.setTimeout(()=>{const current=pendingShellyCommands.get(key);if(current?.requestedAt===pending.requestedAt&&!current.timedOut){current.timedOut=true;updateVisibleShellyCard(deviceId);const feedback=document.querySelector(`[data-smart-device="${CSS.escape(deviceId)}"] [data-shelly-card-feedback]`);if(feedback)feedback.textContent="Sem confirmação ainda; o símbolo mostra a última leitura recebida.";}},10_000);return;
  }
  const shellyGroup=event.target.closest("[data-shelly-group-toggle]");
  if(shellyGroup){if(!ownerCanManageHardware("[data-shelly-status]"))return;const deviceId=shellyGroup.dataset.shellyGroupToggle,device=state.shellyDevices.find(item=>item.device_id===deviceId),dimmers=(device?.components||[]).filter(item=>["light","rgb","rgbw","cct","color"].includes(item.component)),on=shellyGroup.dataset.shellyTarget==="on",status=document.querySelector(`[data-shelly-status="${CSS.escape(deviceId)}"]`);if(!dimmers.length)return;shellyGroup.disabled=true;if(status)status.textContent=on?"A ligar todos os canais…":"A desligar todos os canais…";try{for(const item of dimmers)await controlGatewayShellyLight(deviceId,item.component,Number(item.id)||0,{on});if(status)status.textContent=on?"Ordem de ligar enviada; a confirmar pela LAN.":"Ordem de desligar enviada; a confirmar pela LAN.";void refreshShellyInventoryStatus({quiet:true});}catch(error){if(status)status.textContent=`Não foi possível alterar todos os canais: ${error.message}`;}finally{shellyGroup.disabled=false;}return;}
  const shellyLightButton=event.target.closest("[data-shelly-light-on], [data-shelly-apply-brightness], [data-shelly-apply-color], [data-shelly-apply-ct]");
  if(shellyLightButton){
    if(!ownerCanManageHardware("#shelly-register-status"))return;
    const box=shellyLightButton.closest("[data-shelly-light-controls]"),deviceId=box?.dataset.shellyLightControls,component=box?.dataset.shellyComponent,channel=Number(box?.dataset.shellyChannel),device=state.shellyDevices.find(item=>item.device_id===deviceId);
    if(!device||!box)return;
    const settings={};
    if(shellyLightButton.hasAttribute("data-shelly-light-on"))settings.on=shellyLightButton.dataset.shellyTarget==="on";
    if(shellyLightButton.hasAttribute("data-shelly-apply-brightness"))settings.brightness=Number(box.querySelector("[data-shelly-brightness]")?.value);
    if(shellyLightButton.hasAttribute("data-shelly-apply-color")){const hex=box.querySelector("[data-shelly-color]")?.value||"#000000";settings.rgb=[1,3,5].map(index=>parseInt(hex.slice(index,index+2),16));}
    if(shellyLightButton.hasAttribute("data-shelly-apply-ct"))settings.color_temperature=Number(box.querySelector("[data-shelly-ct]")?.value);
    const summary=typeof settings.on==="boolean"?`luz ${settings.on?"ligada":"desligada"}`:settings.rgb?`cor RGB ${settings.rgb.join(", ")}`:settings.color_temperature?`${settings.color_temperature} K`: `brilho ${settings.brightness}%`;
    if(typeof settings.on!=="boolean"&&!settings.rgb&&!settings.color_temperature&&!Number.isFinite(settings.brightness))return;
    const key=shellyPendingKey(deviceId,component,channel),pending=typeof settings.on==="boolean"?{deviceId,component,channel,value:settings.on,requestedAt:Date.now(),lastObservedAt:shellyObservationMs(device),mismatchCount:0}:null;
    if(pending){pendingShellyCommands.set(key,pending);updateVisibleShellyCard(deviceId);}
    shellyLightButton.disabled=true;const label=$(`[data-shelly-status="${CSS.escape(deviceId)}"]`),cardFeedback=document.querySelector(`[data-smart-device="${CSS.escape(deviceId)}"] [data-shelly-card-feedback]`);if(label)label.textContent="A aplicar e a verificar pela LAN…";if(cardFeedback)cardFeedback.textContent=`A aplicar ${summary}; a confirmar pela LAN…`;
    const started=performance.now();try{const result=await controlGatewayShellyLight(deviceId,component,channel,settings),sentMs=Math.round(performance.now()-started),deviceMs=Math.round(Number(result.device_command_latency_ms)||0),readMs=Math.round(Number(result.readback_latency_ms)||0);if(pending){const current=pendingShellyCommands.get(key);if(current)current.inFlight=false;}const message=result.command_confirmed?`Alteração confirmada pelo Gateway · ${deviceMs} ms`:`Ordem enviada · ${deviceMs} ms · a confirmar pela LAN`;if(label)label.textContent=message;if(cardFeedback)cardFeedback.textContent=message;void refreshShellyInventoryStatus({quiet:true});}
    catch(error){if(pending){const current=pendingShellyCommands.get(key);if(current){current.inFlight=false;current.outcomeUnknown=true;}}if(label)label.textContent="Sem resposta do Gateway; a confirmar pela leitura LAN.";if(cardFeedback)cardFeedback.textContent="Sem resposta do Gateway; alteração possivelmente enviada, a confirmar pela leitura LAN.";}
    finally{shellyLightButton.disabled=false;}
    if(pending)window.setTimeout(()=>{const current=pendingShellyCommands.get(key);if(current?.requestedAt===pending.requestedAt&&!current.timedOut){current.timedOut=true;updateVisibleShellyCard(deviceId);if(cardFeedback)cardFeedback.textContent="Sem confirmação ainda; o símbolo mostra a última leitura recebida.";}},10_000);
    return;
  }
  const tab=event.target.closest("[data-device-tab]");
  if(tab){state.devicesTab=tab.dataset.deviceTab;if(state.devicesTab==="cards")await refreshDeviceCards();render();return;}
  const cardRefresh=event.target.closest("[data-cards-refresh]");if(cardRefresh){cardRefresh.disabled=true;await refreshDeviceCards();render();return;}
  const cardOpen=event.target.closest("[data-card-open]");if(cardOpen){const card=(state.deviceCards||[]).find(item=>item.card_code===cardOpen.dataset.cardOpen);openDeviceCardPreview(card);return;}
  const cardEdit=event.target.closest("[data-card-edit]");if(cardEdit){const card=(state.deviceCards||[]).find(item=>item.card_code===cardEdit.dataset.cardEdit);openDevicePopupMenuEditor(card);return;}
  const cardSubmenu=event.target.closest("[data-card-submenu]");if(cardSubmenu){const host=cardSubmenu.closest("[data-card-code]"),card=(state.deviceCards||[]).find(item=>item.card_code===host?.dataset.cardCode),item=card?.layout?.items?.find(entry=>entry.id===cardSubmenu.dataset.cardSubmenu),device=state.tuyaDevices.find(entry=>entry.product_id===card?.product_id);if(card&&item)openDeviceCardSubmenu(card,item,device);return;}
  const networkInventoryCard=event.target.closest("[data-network-inventory-device]");
  if(networkInventoryCard&&!event.target.closest("button,a,input,select,textarea")){openNetworkInventoryDeviceDetails(networkInventoryCard.dataset.networkInventoryDevice);return;}
  const energyEquipmentCard=event.target.closest("[data-energy-equipment]");
  if(energyEquipmentCard&&!event.target.closest("button,a,input,select,textarea")){openFavoriteDeviceDetails(energyEquipmentCard.dataset.energyEquipment,"equipment");return;}
  const inventoryCard=event.target.closest("[data-inventory-device]");
  if(inventoryCard&&!event.target.closest("button")){clearTimeout(inventoryCardClickTimer);const deviceId=inventoryCard.dataset.inventoryDevice;inventoryCardClickTimer=setTimeout(()=>{inventoryCardClickTimer=null;openFavoriteDeviceDetails(deviceId,"tuya");},280);return;}
  const smartShellyCard=event.target.closest('[data-smart-provider="shelly"]');
  const shellyExpand=event.target.closest("[data-shelly-expand]");
  if(shellyExpand){openShellyDeviceDetails(shellyExpand.dataset.shellyExpand);return;}
  const shellySettings=event.target.closest("[data-shelly-settings]");
  if(shellySettings){openShellySettings(shellySettings.dataset.shellySettings,shellySettings.dataset.shellySection);return;}
  const shellySettingTab=event.target.closest("[data-shelly-setting-tab]");
  if(shellySettingTab){const dialog=shellySettingTab.closest("dialog"),key=shellySettingTab.dataset.shellySettingTab;dialog?.querySelectorAll("[data-shelly-setting-panel]").forEach(panel=>panel.hidden=panel.dataset.shellySettingPanel!==key);dialog?.querySelectorAll("[data-shelly-setting-tab]").forEach(tab=>{const selected=tab.dataset.shellySettingTab===key;tab.classList.toggle("active",selected);tab.setAttribute("aria-selected",String(selected));});return;}
  if(smartShellyCard&&!event.target.closest("button,input")){openShellyDeviceDetails(smartShellyCard.dataset.smartDevice);return;}
  const closeShellyDetails=event.target.closest("[data-shelly-detail-close]");
  if(closeShellyDetails){closeShellyDetails.closest("dialog")?.close();return;}
  const inventoryEquipment=event.target.closest("[data-inventory-equipment]");
  if(inventoryEquipment){openFavoriteDeviceDetails(inventoryEquipment.dataset.inventoryEquipment,"equipment");return;}
  const inventoryRead=event.target.closest("[data-inventory-read]");
  if(inventoryRead){inventoryRead.disabled=true;try{const id=inventoryRead.dataset.inventoryRead,{reading}=await testTuyaLanReachability(id);state.tuyaReadings=[...(state.tuyaReadings||[]).filter(item=>item.device_id!==id),reading];render();if(!tuyaReadingConfirmed(reading))window.alert(`Sem resposta LAN: ${tuyaLanReasonText(reading.reason||"tuya_connection_failed")}`);}catch(error){window.alert("O teste de resposta LAN falhou: "+error.message);}finally{inventoryRead.disabled=false;}return;}
  const inventoryToggle=event.target.closest("[data-inventory-toggle]");
  if(inventoryToggle){const device=state.tuyaDevices.find(item=>item.device_id===inventoryToggle.dataset.inventoryToggle);if(!device||!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){window.alert("Só o Owner autenticado pode controlar este equipamento.");return;}inventoryToggle.disabled=true;try{const code=tuyaPrimarySwitchCode(device),live=state.tuyaReadings.find(item=>item.device_id===device.device_id),observed=tuyaSwitchState(device,live,code);if(!code||typeof observed!=="boolean")throw new Error("Ainda não há estado ON/OFF confirmado pelo varrimento independente.");if(!tuyaSwitchCodeHasLocalMapping(device,code))throw new Error("O DPS local deste interruptor ainda não está mapeado.");await sendTuyaSwitchCommand(device,code,!observed);showFeatureNotice("Ordem enviada. O estado será atualizado pelo próximo varrimento LAN.");}catch(error){window.alert("Não foi possível enviar a ordem: "+error.message);}finally{inventoryToggle.disabled=false;}return;}
  const tuyaCard=event.target.closest("[data-edit-tuya-device]");
  if(tuyaCard){const device=state.tuyaDevices.find(item=>item.device_id===tuyaCard.dataset.editTuyaDevice);if(device)openTuyaDeviceEditor(device);return;}
  const tuyaEvents=event.target.closest("[data-tuya-events]");
  if(tuyaEvents){const id=tuyaEvents.dataset.tuyaEvents,list=$(`[data-tuya-event-list="${CSS.escape(id)}"]`);tuyaEvents.disabled=true;if(list)list.textContent="A carregar registo local do Gateway…";try{const result=await readGatewayTuyaDeviceEvents(id);const events=result.events||[];const on=value=>value===true?"ON":value===false?"OFF":value===null?"—":String(value);list.innerHTML=events.length?events.map(item=>{const when=new Date(item.occurred_at).toLocaleString("pt-PT",{dateStyle:"short",timeStyle:"short"});const text=item.event_type==="availability"?(item.new_value?"Dispositivo disponível na LAN":"Dispositivo indisponível na LAN"):item.event_type==="switch_state"?`${item.channel_code}: ${on(item.old_value)} → ${on(item.new_value)}`:item.event_type==="automation_action"?`Ação automática · ${item.channel_code} ${on(item.new_value)}`:item.event_type==="command_confirmed"?`Comando LAN confirmado · ${item.channel_code} ${on(item.new_value)}`:`Comando LAN enviado, sem confirmação · ${item.channel_code} ${on(item.new_value)}`;return `<div class="tuya-event-row"><time>${esc(when)}</time><strong>${esc(text)}</strong></div>`;}).join(""):`<p class="field-note">Ainda não há eventos registados. O Gateway começa a registar alterações depois das leituras locais.</p>`;}catch(error){if(list)list.textContent=`Não foi possível abrir o registo: ${error.message}`;}finally{tuyaEvents.disabled=false;}return;}
  const chartPoint=event.target.closest(".solar-chart-hit");
  if(chartPoint){
    const tooltip=chartPoint.closest(".solar-chart-wrap")?.querySelector(".solar-chart-tooltip");
    const selection=chartPoint.closest("svg")?.querySelector(".solar-chart-selection");
    if(selection){const x=Number(chartPoint.getAttribute("x"))+Number(chartPoint.getAttribute("width"))/2;selection.setAttribute("x1",x);selection.setAttribute("x2",x);selection.setAttribute("visibility","visible");}
    const balance=chartPoint.closest(".solar-chart-wrap")?.parentElement?.querySelector("[data-solar-day-balance]");if(balance){const fmtBalance=value=>value===""?"—":`${Number(value).toLocaleString("pt-PT",{minimumFractionDigits:2,maximumFractionDigits:2})} kWh`,whenBalance=new Date(Number(chartPoint.dataset.hour)).toLocaleTimeString("pt-PT",{hour:"2-digit",minute:"2-digit"});balance.querySelector("[data-balance-time]").textContent=chartPoint.dataset.pvDay===""?"sem previsão neste horário":`a partir das ${whenBalance}`;balance.querySelector("[data-balance-pv]").textContent=fmtBalance(chartPoint.dataset.pvDay);balance.classList.toggle("is-unavailable",chartPoint.dataset.pvDay==="");}
    if(tooltip){const stamp=Number(chartPoint.dataset.hour),when=new Date(stamp).toLocaleTimeString("pt-PT",{hour:"2-digit",minute:"2-digit"}),isFuture=chartPoint.dataset.future==="true",kind=isFuture?"previsto":"medido",fmt=value=>value===""?"—":`${Number(value).toLocaleString("pt-PT",{maximumFractionDigits:2})} kW`,fmtEnergy=value=>value===""?"—":`${Number(value).toLocaleString("pt-PT",{maximumFractionDigits:2})} kWh`;tooltip.innerHTML=`<strong>${esc(when)} · ${kind}</strong><span>Consumo: ${fmt(chartPoint.dataset.load)}</span><span>${isFuture?"Produção prevista":"Produção efetiva"}: ${fmt(chartPoint.dataset.pv)}</span><span>Produção potencial: ${fmt(chartPoint.dataset.potential)}</span>${isFuture&&chartPoint.dataset.net!==""?`<span>Saldo restante no horizonte 6 h: ${fmtEnergy(chartPoint.dataset.net)}</span><span>Produção total estimada hoje: ${fmtEnergy(chartPoint.dataset.daily)}</span>`:""}`;tooltip.hidden=false;const wrap=chartPoint.closest(".solar-chart-wrap"),bounds=wrap?.getBoundingClientRect(),point=chartPoint.getBoundingClientRect();if(bounds){const width=tooltip.offsetWidth,height=tooltip.offsetHeight,pad=10,pointX=point.left+point.width/2-bounds.left,pointY=point.top+point.height/2-bounds.top;let left=pointX<bounds.width/2?pointX+18:pointX-width-18,top=pointY<bounds.height/2?pointY+18:pointY-height-18;left=Math.max(pad,Math.min(left,bounds.width-width-pad));top=Math.max(pad,Math.min(top,bounds.height-height-pad));if(Math.abs(left+width/2-pointX)<width/2+16)left=pointX<bounds.width/2?Math.min(bounds.width-width-pad,pointX+26):Math.max(pad,pointX-width-26);if(Math.abs(top+height/2-pointY)<height/2+16)top=pointY<bounds.height/2?Math.min(bounds.height-height-pad,pointY+26):Math.max(pad,pointY-height-26);tooltip.style.left=`${left}px`;tooltip.style.top=`${top}px`;}}
    return;
  }
  const openChartTooltip=$(".solar-chart-tooltip:not([hidden])");if(openChartTooltip)openChartTooltip.hidden=true;
  document.querySelectorAll(".solar-chart-selection[visibility='visible']").forEach(line=>line.setAttribute("visibility","hidden"));
  const save = event.target.closest("#ev-tesla-fleet-save");
  const read = event.target.closest("#ev-tesla-read");
  const saveLocal = event.target.closest("#ev-tesla-save");
  const checkPresence = event.target.closest("#ev-tesla-presence");
  if (!save && !read && !saveLocal && !checkPresence) return;
  event.preventDefault();
  const info = sessionInfo(), status = save ? $("#ev-tesla-status") : $("#ev-tesla-read-status") || $("#ev-tesla-status"), output = $("#ev-tesla-result"), presenceStatus = $("#ev-tesla-presence-status");
  if (!info.authenticated || info.user.role !== "owner") {
    status.textContent = "Só o Owner autenticado pode gerir a ligação Tesla.";
    return;
  }
  if (save) save.disabled = true;
  if (read) read.disabled = true;
  if (saveLocal) saveLocal.disabled = true;
  if (checkPresence) checkPresence.disabled = true;
  output.hidden = true;
  try {
    if (save) {
      const vehicleId = $("#ev-tesla-vehicle-id")?.value.trim() || "";
      if (!vehicleId) throw new Error("Indica o ID Tesla ou VIN do veículo.");
      const config = await saveGatewayTeslaEvConfig({
        region: $("#ev-tesla-region").value,
        client_id: $("#ev-tesla-client-id").value.trim(),
        refresh_token: $("#ev-tesla-refresh-token").value,
        vehicle_ids: [vehicleId],
        local_mac: $("#ev-tesla-local-mac")?.value.trim() || "",
      });
      $("#ev-tesla-refresh-token").value = "";
      status.textContent = config.configured
        ? "Ligação Tesla guardada no Gateway; token removido do formulário."
        : "A configuração Tesla não ficou completa.";
    } else if (saveLocal) {
      const mac = $("#ev-tesla-local-mac").value.trim();
      if (!/^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/.test(mac)) throw new Error("Introduz o MAC Wi-Fi completo do Tesla no formato AA:BB:CC:11:22:33.");
      const config = await saveGatewayTeslaEvConfig({ local_mac: mac });
      presenceStatus.textContent = config.local_mac
        ? "MAC local guardado no Gateway. Agora podes testar a presença."
        : "MAC local não guardado.";
    } else if (checkPresence) {
      presenceStatus.textContent = "A consultar os vizinhos locais do Gateway…";
      const result = await readGatewayTeslaLocalPresence();
      presenceStatus.textContent = teslaPresenceText(result);
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
    const target = saveLocal || checkPresence ? presenceStatus : status;
    target.textContent = "Operação Tesla falhou: " + error.message;
  } finally {
    if (save) save.disabled = false;
    if (read) read.disabled = false;
    if (saveLocal) saveLocal.disabled = false;
    if (checkPresence) checkPresence.disabled = false;
  }
});
$("#page-content").addEventListener("submit",async event=>{
  const form=event.target.closest("#shelly-register-form");if(!form)return;event.preventDefault();
  if(!ownerCanManageHardware("#shelly-register-status"))return;
  const button=form.querySelector('[type="submit"]'),status=$("#shelly-register-status");button.disabled=true;status.textContent="A identificar o Shelly e a verificar o MAC fornecido pelo equipamento…";
  try{const result=await registerGatewayShellyDevice({name:form.elements.name.value,host:form.elements.host.value,username:form.elements.username.value,password:form.elements.password.value});form.elements.password.value="";status.textContent=`Registado no inventário pelo MAC ${result.device.mac}. Modelo ${result.device.model||"não indicado"} · ${result.reading.protocol||"protocolo detetado"}.`;await refreshShellyInventoryStatus({quiet:true});}
  catch(error){status.textContent=`Não foi possível identificar ou guardar o Shelly: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#page-content").addEventListener("dblclick",event=>{const card=event.target.closest("[data-inventory-device]");if(!card||!event.target.closest(".favorite-device-info"))return;clearTimeout(inventoryCardClickTimer);inventoryCardClickTimer=null;const device=state.tuyaDevices.find(item=>item.device_id===card.dataset.inventoryDevice);if(device)openTuyaDeviceEditor(device);});
$("#page-content").addEventListener("keydown",event=>{if(!["Enter"," "].includes(event.key)||event.target.closest("button"))return;const card=event.target.closest("[data-inventory-device]");if(!card)return;event.preventDefault();openFavoriteDeviceDetails(card.dataset.inventoryDevice,"tuya");});
$("#page-content").addEventListener("keydown",event=>{if(!["Enter"," "].includes(event.key)||event.target.closest("button"))return;const pending=event.target.closest("[data-network-inventory-device]");if(pending){event.preventDefault();openNetworkInventoryDeviceDetails(pending.dataset.networkInventoryDevice);return;}const equipment=event.target.closest("[data-energy-equipment]");if(equipment){event.preventDefault();openFavoriteDeviceDetails(equipment.dataset.energyEquipment,"equipment");}});
document.addEventListener("click",event=>{if(event.target.closest(".solar-chart-wrap"))return;document.querySelectorAll(".solar-chart-tooltip:not([hidden])").forEach(tooltip=>{tooltip.hidden=true;});});

$("#page-content").addEventListener("dblclick",e=>{
  const card=e.target.closest("[data-battery-bank-edit]");if(!card)return;
  const banks=state.energyEngine?.configuration?.battery_banks||[],index=banks.findIndex(bank=>bank.id===card.dataset.batteryBankEdit);
  if(index>=0)openBatteryBankDialog(banks[index],index);
});
$("#page-content").addEventListener("dblclick",e=>{
  const stringCard=e.target.closest("[data-pv-string-edit]");if(stringCard){const item=(state.energyEngine?.configuration?.pv_strings||[]).find(value=>value.id===stringCard.dataset.pvStringEdit);if(item)openPvStringDialog(item);return;}
  const aqsCard=e.target.closest("[data-aqs-edit]");if(aqsCard){const item=(state.energyEngine?.configuration?.loads||[]).find(value=>value.id===aqsCard.dataset.aqsEdit&&value.kind==="water_heater");if(item)openAqsDialog(item);}
});
$("#page-content").addEventListener("keydown",event=>{
  const bankCard=event.target.closest("[data-battery-bank-edit]");if(bankCard&&["Enter"," "].includes(event.key)){event.preventDefault();const banks=state.energyEngine?.configuration?.battery_banks||[],index=banks.findIndex(bank=>bank.id===bankCard.dataset.batteryBankEdit);if(index>=0)openBatteryBankDialog(banks[index],index);return;}
  const stringCard=event.target.closest("[data-pv-string-edit]");if(stringCard&&["Enter"," "].includes(event.key)){event.preventDefault();const item=(state.energyEngine?.configuration?.pv_strings||[]).find(value=>value.id===stringCard.dataset.pvStringEdit);if(item)openPvStringDialog(item);return;}
  const aqsCard=event.target.closest("[data-aqs-edit]");if(aqsCard&&["Enter"," "].includes(event.key)){event.preventDefault();const item=(state.energyEngine?.configuration?.loads||[]).find(value=>value.id===aqsCard.dataset.aqsEdit&&value.kind==="water_heater");if(item)openAqsDialog(item);return;}
  const point=event.target.closest(".solar-chart-hit");if(!point||!['Enter',' '].includes(event.key))return;
  event.preventDefault();point.dispatchEvent(new MouseEvent('click',{bubbles:true}));
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
function renderGatewayUpdateBanner(){
  const banner=$("#gateway-update-banner"),label=$("#gateway-update-banner-label");
  if(!banner||!label)return;
  if(!gatewayUpdateNotice){try{const version=localStorage.getItem("solarminer-gateway-update-notice-v1");if(version)gatewayUpdateNotice={available_version:version};}catch{}}
  const currentSession=sessionInfo(),owner=Boolean(currentSession.authenticated&&currentSession.user?.role==="owner");
  banner.hidden=!owner||!gatewayUpdateNotice;
  if(gatewayUpdateNotice)label.textContent=`Atualização ${gatewayUpdateNotice.available_version} disponível · toca para verificar novamente`;
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
      result.preflight_reason ? `Bloqueio da recuperação: ${result.preflight_reason}` : "",
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
  const lastPipeline = result.last_pipeline_diagnostic || {};
  const failure = pipeline.failure || lastPipeline.failure || result.details?.failure || result.details?.reason;
  const rollbackFailure = pipeline.rollback_failure || lastPipeline.rollback_failure || result.details?.rollback_failure;
  const diagnosticRows = [
    result.operation_id ? `Operação: ${result.operation_id}` : "",
    result.installed_version ? `Versão instalada: ${result.installed_version}` : "",
    result.target_version ? `Versão de destino: ${result.target_version}` : "",
    failure ? `Falha da atualização: ${failure}` : "",
    rollbackFailure ? `Falha ao recuperar a versão anterior: ${rollbackFailure}` : "",
    result.details?.preflight_reason ? `Preflight de recuperação: ${result.details.preflight_reason}` : "",
    pipeline.recovery ? `Recuperação: ${pipeline.recovery}` : "",
    pipeline.finished_at_utc ? `Terminado em: ${pipeline.finished_at_utc}` : ""
  ].filter(Boolean);
  if (result.status === "VERIFIED" && result.target_version) {
    setGatewayUpdateDetails({
      status: "verified_staged", installed_version: result.installed_version,
      available_version: result.target_version, signature_valid: true, compatible: true,
      activation_available: result.activation_available,
      preflight_reason: result.details?.preflight_reason,
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
async function runGatewayUpdateCheck({automatic=false}={}) {
  const info = sessionInfo();
  if (!info.authenticated || info.user.role !== "owner") { if(!automatic)showGatewayUpdateMessage("Só o Owner autenticado pode verificar atualizações."); return; }
  if(gatewayUpdateCheckInProgress)return;
  gatewayUpdateCheckInProgress=true;
  const button = $("#gateway-update-check");
  if(button)button.disabled = true;
  verifiedGatewayUpdate = null;
  setGatewayUpdateDetails(null);
  const checking=automatic?null:showOperationDialog({title:"Verificar atualização",message:"A verificar o pacote e a assinatura…",locked:true,progress:true});
  try {
    let repositoryUrl=$("#gateway-update-repository")?.value.trim()||"";
    if(!repositoryUrl){const source=await readGatewayUpdateSource();repositoryUrl=source.repository_url||"";if(repositoryUrl&&$("#gateway-update-repository"))$("#gateway-update-repository").value=repositoryUrl;}
    if(!repositoryUrl)throw new Error("Não há um repositório de atualização autorizado configurado no Gateway.");
    const result = await checkGatewayUpdate(repositoryUrl);
    setGatewayUpdateDetails(result);
    if (result.status === "verified_staged") {
      if(result.activation_available){
        gatewayUpdateNotice=result;gatewayAutoUpdateSuppressed=true;try{localStorage.setItem("solarminer-gateway-update-notice-v1",result.available_version);}catch{}renderGatewayUpdateBanner();
        const prompt={title:"Atualização verificada",message:`Versão instalada: ${result.installed_version||"desconhecida"}. Nova versão: ${result.available_version}. Queres aplicar agora?`,actions:[{label:"Cancelar",value:"cancel"},{label:"Atualizar",value:"apply",primary:true}]};
        if(automatic){
          gatewayUpdateNotice=result;
          renderGatewayUpdateBanner();
        } else {
          renderOperationDialog(prompt);
          const choice=await checking;
          if(choice==="apply"){gatewayUpdateNotice=null;try{localStorage.removeItem("solarminer-gateway-update-notice-v1");}catch{}renderGatewayUpdateBanner();await applyVerifiedGatewayUpdate(result);}
          else {gatewayUpdateNotice=result;renderGatewayUpdateBanner();}
        }
      } else {
        if(!automatic){
          renderOperationDialog({title:"Atualização bloqueada",message:`O pacote foi verificado, mas a verificação de recuperação bloqueou a instalação.${result.preflight_reason?` Motivo: ${result.preflight_reason}.`:" O Gateway não devolveu o motivo detalhado."}`,actions:[{label:"OK",value:"ok",primary:true}]});
          await checking;
        }
        gatewayUpdateNotice=result;gatewayAutoUpdateSuppressed=true;renderGatewayUpdateBanner();
      }
    } else if (result.status === "current") {
      gatewayUpdateNotice=null;gatewayAutoUpdateSuppressed=false;try{localStorage.removeItem("solarminer-gateway-update-notice-v1");}catch{}renderGatewayUpdateBanner();
      if(!automatic){renderOperationDialog({title:"Gateway atualizado",message:`Versão verificada: ${result.latest_version||result.installed_version||"atual"}.`,actions:[{label:"OK",value:"ok",primary:true}]});await checking;}
    } else {
      if(!automatic){renderOperationDialog({title:"Verificação falhou",message:gatewayUpdateFailureText(result.message),actions:[{label:"OK",value:"ok",primary:true}]});await checking;}
    }
  } catch (error) {
    if(!automatic){renderOperationDialog({title:"Verificação falhou",message:error.message||"Não foi possível verificar a atualização.",actions:[{label:"OK",value:"ok",primary:true}]});await checking;}
  } finally { gatewayUpdateCheckInProgress=false;if(button)button.disabled=false; }
}
$("#gateway-update-check").addEventListener("click", () => runGatewayUpdateCheck());
$("#gateway-update-banner").addEventListener("click", () => runGatewayUpdateCheck());
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
    !result.checks?.certificate_valid ? `Tailscale ligado (${result.dns_name}), mas falta um certificado HTTPS válido para este nome. Confirma MagicDNS/HTTPS Certificates; a Consola Owner mostra os registos do serviço.` :
    !result.checks?.nginx_config_valid ? `O certificado está válido, mas a configuração Nginx falha. Abre Owner → Consola para ver o erro e os serviços afetados.` :
    !result.checks?.nginx_active ? "O certificado e a configuração estão válidos, mas o serviço Nginx não está ativo. Consulta Owner → Consola." :
    !result.checks?.gateway_active ? "O Nginx está ativo, mas o serviço Gateway não está ativo; isso pode causar 502. Consulta Owner → Consola." :
    !result.https_ready ? `O endpoint HTTPS de Tailscale não passou todas as verificações (${result.dns_name}). Consulta Owner → Consola.` :
    `Tailscale ativo e HTTPS pronto: ${result.endpoint}. Não são necessárias portas no router.`;
  return result;
}
$("#gateway-tailscale-refresh").addEventListener("click",async()=>{
  const pending=showOperationDialog({title:"Verificar Tailscale",message:"A consultar o estado e o HTTPS…",locked:true,progress:true});
  try{const result=await refreshGatewayTailscale();renderOperationDialog({title:result.https_ready?"Acesso remoto pronto":"Verificação do Tailscale",message:$("#gateway-tailscale-status").textContent,actions:[{label:"OK",value:"ok",primary:true}]});}
  catch(error){renderOperationDialog({title:"Falha no Tailscale",message:error.message||"Não foi possível consultar o estado.",actions:[{label:"OK",value:"ok",primary:true}]});}
  await pending;
});
$("#gateway-tailscale-connect").addEventListener("click",async()=>{
  const button=$("#gateway-tailscale-connect"), status=$("#gateway-tailscale-status");
  button.disabled=true; const pending=showOperationDialog({title:"Ligar ao Tailscale",message:"A pedir ao Gateway para iniciar a ligação…",locked:true,progress:true});
  try {
    const result=await startGatewayTailscale();
    if(result.auth_url){
      status.replaceChildren(document.createTextNode("Abre este link e aprova o Gateway na tua conta Tailscale: "));
      const link=document.createElement("a"); link.href=result.auth_url; link.target="_blank"; link.rel="noopener noreferrer"; link.textContent="Autorizar Gateway no Tailscale";
      status.append(link);
      renderOperationDialog({title:"Autorizar Gateway",message:"Abre a página do Tailscale e aprova o Gateway. Depois volta aqui e toca em Detetar estado.",link:{href:result.auth_url,label:"Abrir autorização Tailscale"},actions:[{label:"OK",value:"ok",primary:true}]});
    } else {status.textContent="O Gateway já está ligado ao Tailscale. Toca em Detetar estado para confirmar o endereço HTTPS.";renderOperationDialog({title:"Tailscale",message:status.textContent,actions:[{label:"OK",value:"ok",primary:true}]});}
  } catch(error){status.textContent=`O Gateway não conseguiu iniciar o Tailscale: ${error.message}`;renderOperationDialog({title:"Falha no Tailscale",message:status.textContent,actions:[{label:"OK",value:"ok",primary:true}]});}
  finally{button.disabled=false;} await pending;
});
$("#gateway-tailscale-save").addEventListener("click",async()=>{
  const button=$("#gateway-tailscale-save"), status=$("#gateway-tailscale-status"), field=$("#gateway-tailscale-endpoint");
  const value=field.value.trim();
  button.disabled=true; const pending=showOperationDialog({title:"Guardar Tailscale",message:"A guardar o endereço no Gateway…",locked:true,progress:true});
  try {
    const result=await configureGatewayTailscale(value || null);
    if(result.endpoint){try{localStorage.setItem("solarminer-gateway-tailscale-endpoint-v1",result.endpoint);}catch{}}
    else {try{localStorage.removeItem("solarminer-gateway-tailscale-endpoint-v1");}catch{}}
    status.textContent=value ? `Endereço guardado no Gateway: ${result.endpoint}.` : "Endereço manual removido; será usada a deteção automática quando estiver disponível.";
    renderOperationDialog({title:"Tailscale guardado",message:value?"O endereço foi guardado no Gateway.":"O endereço manual foi removido.",actions:[{label:"OK",value:"ok",primary:true}]});
  } catch(error){status.textContent=`Não foi possível guardar o endereço: ${error.message}`;renderOperationDialog({title:"Falha ao guardar",message:error.message||"Não foi possível guardar o endereço.",actions:[{label:"OK",value:"ok",primary:true}]});}
  finally{button.disabled=false;} await pending;
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
  const confirmation=showOperationDialog({title:"Confirmar atualização",message:`Versão instalada: ${update.installed_version||"desconhecida"}. Nova versão: ${update.available_version}. Queres aplicar?`,actions:[{label:"Cancelar",value:"cancel"},{label:"Atualizar",value:"apply",primary:true}]});
  if(await confirmation!=="apply")return;
  await applyVerifiedGatewayUpdate(update);
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
  let created = null, inviteReady = false;
  try {
    const result = created = await createGatewayInvite({ role: $("#gateway-invite-role").value, label: $("#gateway-invite-label").value.trim() });
    // Invitations use only the Gateway's publicly trusted MagicDNS HTTPS name.
    // LAN IP certificates are self-signed and would force every invitee to
    // install/trust a certificate manually, which a PWA cannot do for them.
    let tailscale;
    try { tailscale = await readGatewayTailscale(); }
    catch { throw new Error("Não foi possível confirmar o acesso HTTPS seguro do Tailscale. Confirma que o Gateway está ligado ao Tailnet e tenta novamente."); }
    if (tailscale?.https_ready !== true || !tailscale.endpoint) {
      throw new Error("O acesso HTTPS do Tailscale ainda não está pronto. Liga o Gateway ao Tailnet e ativa MagicDNS e HTTPS Certificates; depois volta a criar o convite.");
    }
    const gateways = [tailscale.endpoint];
    const activationUrl = buildInviteLandingUrl({ pwaUrl: PWA_INVITE_LANDING_URL, gatewayUrls: gateways,
      token: result.invite_code.token, fingerprint: result.invite_code.fp, expiresAt: result.invite_code.exp });
    if (!globalThis.qrcode) throw new Error("O gerador de QR da PWA não carregou. Atualiza a página e tenta novamente.");
    const qr = globalThis.qrcode(0, "M"); qr.addData(activationUrl); qr.make();
    if (inviteQrObjectUrl) URL.revokeObjectURL(inviteQrObjectUrl);
    inviteQrObjectUrl = URL.createObjectURL(new Blob([qr.createSvgTag(8, 4)], { type: "image/svg+xml" }));
    $("#gateway-invite-qr").src = inviteQrObjectUrl;
    $("#gateway-invite-payload").value = activationUrl;
    $("#gateway-invite-expiry").textContent = `Expira em ${currentTimeLabel(new Date(result.expires_at * 1000).toISOString())}. Papel: ${result.role}. O QR contém um código único de ativação.`;
    $("#gateway-invite-created").hidden = false;
    inviteReady = true;
  } catch (error) {
    if (!inviteReady && created?.invite_id) { try { await revokeGatewayInvite(created.invite_id); } catch {} }
    gatewayResult(`Não foi possível criar convite: ${error.message}`);
  }
  if (inviteReady) refreshInviteList().catch(error => { $("#gateway-invite-list").textContent = `Convite criado; não foi possível atualizar a lista: ${error.message}`; });
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
let inviteActivationHash = null, inviteActivationError = "";
try { inviteActivationHash = readInviteLandingHash(location.hash); }
catch (error) { if (location.hash.startsWith("#invite=")) inviteActivationError = error.message; }
if (inviteActivationHash) {
  $("#gateway-invite-activation-dialog").showModal();
  $("#gateway-invite-activation-form").addEventListener("submit", async event => {
    event.preventDefault();
    const status = $("#gateway-invite-activation-status"), button = $("#gateway-invite-activate");
    const password = $("#gateway-invite-password"), repeat = $("#gateway-invite-password-repeat");
    if (password.value !== repeat.value) { status.textContent = "As palavras-passe não coincidem."; repeat.focus(); return; }
    button.disabled = true; status.textContent = "A validar o convite e a registar este dispositivo no Gateway…";
    try {
      const result = await redeemGatewayInvite({ qrText: inviteActivationHash,
        username: $("#gateway-invite-username").value.trim(), password: password.value,
        mac: "00:00:00:00:00:00" });
      password.value = ""; repeat.value = "";
      history.replaceState(null, "", `${location.pathname}${location.search}`);
      status.textContent = `Acesso criado como ${result.user.username} (${result.user.role}). Este dispositivo já está registado.`;
      markGatewayAuthenticated(); updateSessionUi(); await refreshGatewayReadings();
      setTimeout(() => { const dialog = $("#gateway-invite-activation-dialog"); if (dialog.open) dialog.close(); }, 900);
    } catch (error) {
      password.value = ""; repeat.value = "";
      status.textContent = error.message || "Não foi possível ativar o convite. Confirma a ligação e tenta novamente.";
      button.disabled = false;
    }
  });
} else if (inviteActivationError || location.hash.startsWith("#invite=")) {
  $("#gateway-invite-activation-dialog").showModal();
  $("#gateway-invite-activation-status").textContent = inviteActivationError || "O link de ativação está inválido ou expirou. Pede ao Owner um novo QR Code.";
  $("#gateway-invite-activation-form").hidden = true;
}
updateSessionUi();
updateGatewayStatus(gatewayManager.state);
if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("./service-worker.js").catch(()=>{});
render();
hydrateWorkspacePhotos();
if (sessionInfo().authenticated) refreshGatewayReadings();
setInterval(() => {
  const lastRefresh=Date.parse(state.lastUpdated||"");
  if (document.visibilityState === "visible" && !["mineradoras","gestao-excedentes"].includes(state.page) && sessionInfo().authenticated && !state.refreshing && (!Number.isFinite(lastRefresh) || Date.now()-lastRefresh>=10_000)) {
    refreshGatewayReadings();
  }
}, 5_000);
setInterval(() => { if(document.visibilityState==="visible")void refreshTuyaInventoryStatus(); },5_000);
setInterval(() => { if(state.page==="devices"&&document.visibilityState==="visible")void refreshShellyInventoryStatus({quiet:true}); },15_000);
setInterval(() => {
  const info=sessionInfo();
  if(document.visibilityState!=="visible"||!info.authenticated||info.user?.role!=="owner"||gatewayAutoUpdateSuppressed||gatewayUpdateCheckInProgress||$("#operation-dialog")?.open)return;
  runGatewayUpdateCheck({automatic:true});
},60_000);



