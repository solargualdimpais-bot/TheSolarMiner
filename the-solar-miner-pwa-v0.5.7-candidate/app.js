import { CATEGORIES, DEMO_EQUIPMENT, classifyEquipment, formatReading, isSimulated, summarizeDataState } from "./app-core.js";
import { DEMO_CONTROL_CONFIG, createDemoControlState, updateDemoControl, toggleDemoControl } from "./demo-mode.js";
import { renderWorkspacePage, renderHomePreferenceLinks, renderHouseSearch, handleWorkspaceAction, handleWorkspaceChange, applyPreferences, getWorkspacePageLabel, workspace, getEditableEntity, saveEditableEntity, saveDemoWorkspace, hydrateWorkspacePhotos } from "./workspace-ui.js";
import { renderAutomationsPage, renderSolarProductionPage, renderDemoAdminPanel, handleFeatureAction, saveAutomationForm, addDemoUser, saveDemoUserEdit, saveSolarWeather, demoFeatures } from "./features-v053.js";
import { GatewayConnectionManager, CONNECTION_STATES, validateGatewayUrl, classifyEndpoint, inferHostedGatewayEndpoint, PRESENCE_API_STATUS } from "./gateway-connection.js";
import { bootstrapGatewayOwner, recoverGatewayOwner, parseOwnerRecoveryFile, readGatewayBootstrapStatus, loginGateway, loginGatewayWithPassword, sessionInfo, createGatewayInvite, listGatewayInvites, revokeGatewayInvite, listGatewayUsers, updateGatewayUserRole, updateGatewayUserStatus, logoutGateway, readGatewayEnergy, readGatewaySiteProfile, saveGatewaySiteProfile, saveGatewaySitePhoto, saveGatewayEnergyEngineConfig, presenceInfo, checkGatewayUpdate, readGatewayUpdateSource, readGatewayUpdateStatus, applyGatewayUpdate, readGatewayTailscale, readGatewayConsole, readGatewayTerminalDiagnostics, openGatewayTerminalSocket, configureGatewayTailscale, startGatewayTailscale, readGatewayHardwareIntegrationConfig, readGatewayHardwareProvider, saveGatewayHardwareIntegrationConfig, syncGatewayTuyaDevices, controlGatewayAntminer, controlGatewayTuyaSwitch, controlGatewayTuyaLevel, readGatewayTuyaDeviceEvents, runGatewayTuyaLanDiagnostics, discoverGatewayTuyaLanDevices, readGatewayHuaweiClients, readGatewayDeyeCloudStations, importGatewayDeyeCloudHistory, readGatewayTeslaEvConfig, saveGatewayTeslaEvConfig, readGatewayTeslaEvCharging } from "./gateway-auth.js";

let automationEditingId = "";
const state = { page: "inicio", mode: "DISCONNECTED", dataStatus: "UNAVAILABLE", dataError: null, equipment: [], energyEngine: null, siteProfile: null, tuyaDevices: [], tuyaReadings: [], lastUpdated: null, lastMeasurementAt: null, refreshing: false, demoControls: createDemoControlState(), sky: "pouco nublado", favoriteDevices: [], engineHistoryChart: { open: false, dateKey: "", loading: false, error: null } };
let houseView={tab:"overview",floorId:null,roomId:null,planEditing:false};
let housePlanPointer=null;
let lastTuyaReadAt=0;
let operationDialogResolve=null;
let gatewayUpdateNotice=null;
let gatewayAutoUpdateSuppressed=false;
let gatewayUpdateCheckInProgress=false;
let gatewayOwnerAutoCheckStarted=false;
const $ = (selector) => document.querySelector(selector);
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
  const version=result?.installed_version||result?.target_version||"";
  if(status==="COMMITTED")return `Atualização concluída${version?` para a versão ${version}`:""}.`;
  if(status==="ROLLED_BACK")return `A atualização falhou e o Gateway recuperou a versão anterior${version?` (${version})`:""}.`;
  if(status==="FAILED"||status==="RECOVERY_BLOCKED")return `A atualização não foi concluída${version?`. Versão de destino: ${version}`:"."} Consulta a Consola para ver o diagnóstico.`;
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
const userFacingSaveError = (error) => { const message=String(error?.message||""); if(message.includes("site_location_not_found")) return "O Gateway não encontrou essa cidade. Escreve cidade e país, por exemplo, Coimbra, Portugal."; if(message.includes("site_location_lookup_failed")) return "O Gateway não conseguiu consultar o serviço de localização. Verifica a ligação à Internet e tenta novamente."; return message||"Não foi possível guardar as alterações."; };
const pageLabel = (id) => id === "inicio" ? "Visão geral" : id === "owner" ? "Owner" : (CATEGORIES.find(c => c.id === id)?.label || getWorkspacePageLabel(id) || "Mais áreas");
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
function isHeicPhoto(file){return /\.(?:heic|heif)$/i.test(file?.name||'')||/^image\/hei[cf]/i.test(file?.type||'');}
function loadHeicConverter(){if(typeof window.heic2any==='function')return Promise.resolve(window.heic2any);if(heicConverterLoad)return heicConverterLoad;heicConverterLoad=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('./assets/heic2any-0.0.4.min.js',import.meta.url).href;script.onload=()=>typeof window.heic2any==='function'?resolve(window.heic2any):reject(new Error('O conversor HEIC não ficou disponível.'));script.onerror=()=>{heicConverterLoad=null;reject(new Error('Não foi possível carregar o conversor HEIC. Confirma a ligação e tenta novamente.'));};document.head.append(script);});return heicConverterLoad;}
async function isJpegPhoto(file){if(/^image\/jpeg(?:$|;)/i.test(file?.type||''))return true;if(!file?.slice)return false;try{const header=new Uint8Array(await file.slice(0,3).arrayBuffer());return header[0]===0xff&&header[1]===0xd8&&header[2]===0xff;}catch{return false;}}
async function makeBrowserReadablePhoto(file){if(await isJpegPhoto(file)||!isHeicPhoto(file))return file;const convert=await loadHeicConverter();const converted=await convert({blob:file,toType:'image/jpeg',quality:.92});const jpeg=Array.isArray(converted)?converted[0]:converted;if(!(jpeg instanceof Blob)||jpeg.size===0)throw new Error('Não foi possível converter esta fotografia HEIC.');return jpeg;}
function readAndCompressImage(file){return new Promise((resolve,reject)=>{if(!file)return resolve(undefined);if((file.type&&!/^image\//i.test(file.type))||file.size>40*1024*1024)return reject(new Error('Escolhe uma fotografia com menos de 40 MB.'));const image=new Image();const sourceUrl=URL.createObjectURL(file);const finish=()=>URL.revokeObjectURL(sourceUrl);image.onerror=()=>{finish();reject(new Error('O browser não conseguiu descodificar esta imagem.'));};image.onload=async()=>{try{const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');if(!ctx)throw new Error('O browser não disponibilizou processamento local de imagem.');let maxDimension=1800;for(let attempt=0;attempt<14;attempt++){const scale=Math.min(1,maxDimension/Math.max(image.naturalWidth,image.naturalHeight));canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);for(const quality of [.82,.72,.62,.52,.42]){const blob=await new Promise(done=>canvas.toBlob(done,'image/jpeg',quality));if(blob&&blob.size<=1_800_000){const reader=new FileReader();reader.onerror=()=>reject(new Error('Não foi possível preparar a fotografia.'));reader.onload=()=>resolve(reader.result);reader.readAsDataURL(blob);finish();return;}}maxDimension=Math.round(maxDimension*.8);}throw new Error('Não foi possível comprimir a fotografia abaixo do limite de 1,8 MB. Escolhe uma fotografia mais pequena.');}catch(error){finish();reject(error);}};image.src=sourceUrl;});}
$('#context-editor-cancel').addEventListener('click',()=>$('#context-editor').close());
$('#context-editor-fields').addEventListener('change',async e=>{if(e.target.id!=='context-editor-file')return;const file=e.target.files?.[0];if(!file)return;const img=$('#context-editor-preview-image'),preview=$('#context-editor-preview'),submit=$('#context-editor-form [type="submit"]'),heic=isHeicPhoto(file);if(editorPreviewObjectUrl){URL.revokeObjectURL(editorPreviewObjectUrl);editorPreviewObjectUrl=null;}if(!heic){editorPreviewObjectUrl=URL.createObjectURL(file);img.src=editorPreviewObjectUrl;preview.hidden=false;updateHousePhotoPreview();}editorPhotoProcessing=true;submit.disabled=true;$('#context-editor-status').textContent=heic?'A converter a fotografia HEIC e a preparar a pré-visualização…':'A preparar a pré-visualização da fotografia…';try{const readable=await makeBrowserReadablePhoto(file);if(heic){editorPreviewObjectUrl=URL.createObjectURL(readable);img.src=editorPreviewObjectUrl;preview.hidden=false;updateHousePhotoPreview();}editorPhoto=await readAndCompressImage(readable);$('#context-editor-status').textContent='Pré-visualização pronta. Ainda não foi guardada.';}catch(error){$('#context-editor-status').textContent=error.message;$('#context-editor-file').value='';if(editorPhoto){img.src=editorPhoto;preview.hidden=false;}else{img.removeAttribute('src');preview.hidden=true;}}finally{editorPhotoProcessing=false;submit.disabled=false;}});
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
      const payload={...current,name:form.elements.name?.value||current.name,photo_data_url:editorPhoto===undefined?(current.photo_data_url||null):(editorPhoto||null),photo_opacity:editorPhotoSettings.opacity,photo_position_x:editorPhotoSettings.x,photo_position_y:editorPhotoSettings.y,photo_zoom:editorPhotoSettings.zoom,photo_vignette:editorPhotoSettings.vignette};
      const locationName=form.elements.siteLocationName?.value.trim()||'';
      const oldLocation=state.energyEngine?.configuration?.site_location_name||'';
      if(locationName&&locationName!==oldLocation){const cfg=await saveGatewayEnergyEngineConfig({site_location_name:locationName});state.siteLocationName=cfg.site_location_name||locationName;}
      state.siteProfile=await saveGatewaySiteProfile(payload);state.propertyName=state.siteProfile.name;
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
        const hardware = await readGatewayHardwareIntegrationConfig(); state.tuyaDevices = hardware.tuya?.devices || [];
        if (state.tuyaDevices.length && Date.now()-lastTuyaReadAt>=300_000) { const readings = await readGatewayHardwareProvider("tuya"); state.tuyaReadings = readings.tuya || []; lastTuyaReadAt=Date.now(); }
        else if(!state.tuyaDevices.length) { state.tuyaReadings = []; lastTuyaReadAt=0; }
      } catch { /* Keep last successful values visible with their original timestamp. */ }
    }
    state.mode = "LIVE";
    state.dataStatus = classifyGatewayReadings(state.equipment, Math.max(90 * 1000, (result.engine?.sampling_interval_seconds || 30) * 3 * 1000));
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
  return `<div class="engine-history-toolbar"><button class="button secondary" data-engine-history-day="-1" ${dayKey<=oldestKey?"disabled":""} aria-label="Dia anterior">‹ Dia anterior</button><strong>${esc(dayLabel)}</strong><button class="button secondary" data-engine-history-day="1" ${dayKey>=todayKey?"disabled":""} aria-label="Dia seguinte">Dia seguinte ›</button></div>${loading?`<div class="empty-state">A carregar os cálculos e medições guardados desse dia…</div>`:error?`<div class="empty-state">Não foi possível carregar este dia: ${esc(error)}</div>`:empty?`<div class="empty-state">Não há amostras guardadas neste dia. Usa os botões para escolher outro.</div>`:`<section class="engine-forecast-comparison"><h3>Previsão do dia comparada com a produção medida</h3><p>As duas linhas mostram, ao longo do dia, o total final previsto e a energia FV medida até cada hora.</p><div class="engine-history-plot"><svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Previsão de energia FV e produção medida em ${esc(dayLabel)}"><path class="chart-grid" d="M42 40H578 M42 88H578 M42 136H578 M42 188H578"/><path class="engine-chart-measured" d="${actualPath}" fill="none"/><path class="engine-chart-forecast" d="${forecastPath}" fill="none"/><path class="engine-chart-potential" d="${potentialPath}" fill="none"/><g class="chart-label"><text x="42" y="210">00:00</text><text x="300" y="210">12:00</text><text x="545" y="210">24:00</text></g></svg></div><div class="engine-history-legend"><span><i class="engine-chart-measured"></i>FV medido acumulado</span><span><i class="engine-chart-forecast"></i>Previsão diária</span><span><i class="engine-chart-potential"></i>Potencial ajustado</span></div><div class="ws-kpi-grid engine-history-totals"><article class="ws-kpi"><small>Produção FV medida · último registo</small><strong>${fmt(latestActual)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Última previsão do total diário</small><strong>${fmt(latestForecast)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Potencial máximo ajustado</small><strong>${fmt(latestPotential)} <em>kWh</em></strong></article><article class="ws-kpi"><small>Previsto ainda por produzir</small><strong>${fmt(latestForecast==null||latestActual==null?null:Math.max(0,latestForecast-latestActual))} <em>kWh</em></strong></article><article class="ws-kpi"><small>Ajuste da previsão no dia</small><strong>${fmt(forecastRevision)} <em>kWh</em></strong></article></div>${recordedStatus}<details class="engine-power-history"><summary>Ver potência instantânea, consumo e bateria</summary><div class="engine-history-plot"><svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Potência FV, consumo e bateria em ${esc(dayLabel)}"><path class="chart-grid" d="M42 40H578 M42 88H578 M42 136H578 M42 188H578"/><path class="engine-chart-zero" d="M42 ${powerY(0).toFixed(1)}H578"/>${powerPaths}<g class="chart-label"><text x="42" y="210">00:00</text><text x="300" y="210">12:00</text><text x="545" y="210">24:00</text></g></svg></div><div class="engine-history-legend"><span><i class="engine-chart-pv"></i>Produção FV</span><span><i class="engine-chart-load"></i>Consumo da casa</span><span><i class="engine-chart-battery"></i>Bateria · positivo = descarga</span></div></details><p class="field-note">A produção medida vem do contador diário do inversor. O previsto ainda por produzir é a diferença entre a previsão atual e a energia medida até à hora do último registo; compara essa curva com o total conhecido no fecho do dia para avaliar o erro final.</p></section>`}`;
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
  const autonomy=current.battery_autonomy_forecast||{};
  const number = (value, digits=1) => Number.isFinite(value) ? Number(value).toFixed(digits) : "—";
  const series = data.history?.pv_total_power || [];
  const points = series.map((item, i) => ({ x: i, y: Number(item.value) / (item.unit === "W" ? 1000 : 1) })).filter(p => Number.isFinite(p.y));
  const max = Math.max(1, ...points.map(p => p.y), Number(forecast.one_hour_value) || 0);
  const path = points.map((p,i)=>`${i?'L':'M'}${40+(points.length>1?p.x/(points.length-1)*540:0)} ${180-p.y/max*140}`).join(" ");
  const time = data.updated_at ? timeLabel(data.updated_at) : "Sem leitura";
  const ownerConfig = sessionInfo().user?.role === "owner";
  const forecastLabel = forecast.confidence === "LOW_INDICATIVE" ? "Tendência indicativa · apenas histórico" : "Histórico insuficiente para projeção";
  const readingTile=(field,label)=>{const item=readings[field];return `<div class="detail-item"><small>${esc(label)}</small><strong>${item?`${esc(item.value)} ${esc(item.unit||"")}`:"—"}</strong><small>${item?`${esc(item.trust)} · ${esc(timeLabel(item.observed_at))}`:"Sem leitura"}</small></div>`;};
  const dispatchRows=(data.dispatch?.actions||[]).map(action=>`<div class="detail-item"><small>${esc(action.name||action.load_id)}</small><strong>${esc(action.state)}</strong><small>${Number.isFinite(action.target_power_w)?`${esc(action.target_power_w)} W · `:""}${esc(action.control_type||"")}</small></div>`).join("");
  const execution=data.dispatch_execution;
  const solarSiteConfig="";
  const solarDay=data.forecast?.solar_day||{};
  const solarForecastConfidence=solarDay.confidence==="MEDIUM_INDICATIVE"?"MÉDIA":solarDay.confidence==="LOW_INDICATIVE"?"BAIXA":solarDay.confidence||"SEM DADOS";
  const solarExpectedRemaining=solarDay.state==="ESTIMATED"?solarDay.remaining_estimate_kwh:null;
  const solarPotentialRemaining=solarDay.state==="ESTIMATED"?solarDay.potential_max_remaining_kwh:null;
  const expectedLoadRemaining=solarDay.state==="ESTIMATED"?solarDay.expected_load_remaining_kwh:null;
  const netEnergyBalance=solarDay.state==="ESTIMATED"?solarDay.net_energy_balance_kwh:null;
  const solarEngineCards=`<section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">PREVISÃO SOLAR · ENGINE</p><h2>Até ao fim do dia</h2></div><span class="source-tag">${esc(solarForecastConfidence)}</span></div><div class="energy-outlook-grid engine-solar-outlook"><article class="ws-kpi solar-day-forecast-card"><small>Solar restante</small><strong>${solarExpectedRemaining!=null?number(Number(solarExpectedRemaining),2):"—"} <em>kWh</em></strong><span>${solarDay.state==="ESTIMATED"?`Total previsto hoje: ${number(Number(solarDay.estimated_total_kwh),2)} kWh`:esc(solarDay.reason||"A aguardar dados")}</span></article><article class="ws-kpi solar-day-forecast-card"><small>Potencial restante</small><strong>${solarPotentialRemaining!=null?number(Number(solarPotentialRemaining),2):"—"} <em>kWh</em></strong><span>Referência ajustada ao histórico</span></article><article class="ws-kpi solar-day-forecast-card"><small>Saldo após consumo</small><strong>${netEnergyBalance!=null?number(Number(netEnergyBalance),2):"—"} <em>kWh</em></strong><span>${netEnergyBalance!=null?`${netEnergyBalance>=0?"Disponível estimado":"Défice previsto"} · consumo ${number(Number(expectedLoadRemaining),2)} kWh`:"A aguardar leituras de consumo"}</span></article></div><p class="field-note">Atualizado com produção e consumo recentes · confiança do consumo ${esc(solarDay.load_forecast_confidence||"baixa")}.</p></section>`;
  return `<div class="page-heading"><div><p class="eyebrow">ENERGY / ENGINE</p><h1>Engine energético</h1><p>Dados e cálculos processados no Gateway. Leituras do mapa Deye permanecem LIVE_UNVERIFIED.</p></div><button class="button secondary" id="engine-refresh">Atualizar ↻</button></div>
  ${solarSiteConfig}
  ${solarEngineCards}
  <div class="ws-kpi-grid"><article class="ws-kpi"><small>SOC da bateria</small><strong>${number(current.battery_soc_percent,1)} <em>%</em></strong><span>${esc(current.battery_soc_estimate?.state||"A aguardar estimativa")} · ${current.battery_soc_percent==null?"O Engine só confirma 100% após tensão alta e estabilização da carga.":`${esc(data.trust)} · ${esc(time)}`}${current.battery_at_configured_maximum?" · LIMITE MÁXIMO ATINGIDO":""}</span></article><article class="ws-kpi"><small>Energia acima do SOC mínimo</small><strong>${number(current.battery_energy_available_kwh_above_minimum,2)} <em>kWh</em></strong><span>${current.battery_capacity_kwh == null ? "Configura capacidade total para calcular" : `Espaço até máximo: ${number(current.battery_charge_headroom_kwh_to_maximum,2)} kWh · reserva ${number(current.minimum_soc_percent,0)}–${number(current.maximum_soc_percent,0)}%`}</span></article><article class="ws-kpi battery-autonomy-card"><small>Autonomia até ao corte · sem solar</small><strong>${number(autonomy.hours,1)} <em>h</em></strong><span>${autonomy.state==="ESTIMATED"?`Corte provável ${autonomy.estimated_cutoff_at?esc(timeLabel(autonomy.estimated_cutoff_at)):"—"} · confiança ${esc(autonomy.confidence||"BAIXA")} · perfil ${esc(autonomy.history_days_used??0)} dias + consumo atual`:`A aguardar energia disponível e leituras de consumo`}</span></article><article class="ws-kpi"><small>Produção FV atual</small><strong>${number(current.pv_power_w == null ? null : current.pv_power_w/1000,2)} <em>kW</em></strong><span>PV1 + PV2 · medida</span></article><article class="ws-kpi"><small>Consumo atual</small><strong>${number(current.load_power_w == null ? null : current.load_power_w/1000,2)} <em>kW</em></strong><span>Canal de cargas Deye</span></article></div>
  <section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO GUARDADO NO GATEWAY · ÚLTIMAS 24 H</p><h2>Produção e tendência de FV · kW</h2></div><span class="source-tag">${esc(series.length)} amostras</span></div><button type="button" class="engine-chart-open" id="engine-chart-open" aria-label="Abrir e percorrer o gráfico diário do Engine">${points.length?`<svg viewBox="0 0 620 220" class="chart solar-potential-chart" role="img" aria-label="Histórico de potência fotovoltaica lido pelo Gateway"><path class="chart-grid" d="M40 35H600 M40 80H600 M40 125H600 M40 180H600"/><path d="${path}" class="chart-line" fill="none"/><g class="chart-label"><text x="40" y="202">mais antigo</text><text x="510" y="202">agora</text></g></svg>`:`<div class="empty-state">Ainda não há amostras recentes. Abre o gráfico para consultar outros dias guardados.</div>`}<span>Abre o gráfico para percorrer os dias com histórico · FV, consumo e bateria</span></button><div class="ws-kpi-grid"><article class="ws-kpi"><small>Potência FV estimada +1 h</small><strong>${number(forecast.one_hour_value,2)} <em>kW</em></strong><span>${esc(forecastLabel)}</span></article><article class="ws-kpi"><small>Potência FV estimada +3 h</small><strong>${number(forecast.three_hour_value,2)} <em>kW</em></strong><span>Regressão linear · limitada a 15 kW</span></article><article class="ws-kpi"><small>Consumo estimado +1 h</small><strong>${number(data.forecast?.load_power?.one_hour_value,2)} <em>kW</em></strong><span>Histórico de cargas · baixa confiança</span></article><article class="ws-kpi"><small>SOC estimado +1 h</small><strong>${number(data.forecast?.battery_soc?.one_hour_value,1)} <em>%</em></strong><span>Tendência histórica simples · baixa confiança</span></article></div><p class="field-note">${esc(data.forecast?.notice || "")} ${esc(data.limits?.notice || "")}</p></section>
  <section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">MAPA DE REGISTOS DEYE · LEITURAS RECENTES</p><h2>FV, bateria e contadores</h2></div><span class="source-tag">LIVE_UNVERIFIED</span></div><div class="device-detail-grid telemetry-grid">${readingTile("pv1_input_power","Potência FV 1")}${readingTile("pv1_voltage","Tensão FV 1")}${readingTile("pv1_current","Corrente FV 1")}${readingTile("pv2_input_power","Potência FV 2")}${readingTile("pv2_voltage","Tensão FV 2")}${readingTile("pv2_current","Corrente FV 2")}${readingTile("battery_voltage","Tensão bateria")}${readingTile("battery_output_current","Corrente bateria")}${readingTile("battery_output_power","Potência bateria")}${readingTile("battery_temperature","Temperatura bateria")}${readingTile("pv_daily_energy","Energia FV hoje")}${readingTile("pv_total_energy","Energia FV acumulada")}${readingTile("load_daily_energy","Consumo hoje")}${readingTile("load_total_energy","Consumo acumulado")}${readingTile("battery_daily_charge_energy","Carga da bateria hoje")}${readingTile("battery_daily_discharge_energy","Descarga da bateria hoje")}${readingTile("battery_max_charge_current","Limite configurado de carga")}${readingTile("battery_max_discharge_current","Limite configurado de descarga")}<div class="detail-item"><small>Potência máxima de carga calculada</small><strong>${number(current.battery_configured_max_charge_power_kw,2)} kW</strong><small>Estimativa a partir da tensão e limite configurado</small></div><div class="detail-item"><small>Potência máxima de descarga calculada</small><strong>${number(current.battery_configured_max_discharge_power_kw,2)} kW</strong><small>Estimativa a partir da tensão e limite configurado</small></div></div><p class="field-note">As potências derivadas multiplicam tensão medida pelos limites configurados no inversor; são estimativas de configuração, não limites dinâmicos do BMS. O mapa candidato continua por validar para o firmware exato.</p></section>
  <section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">DESPACHO DE CARGAS</p><h2>${esc(data.dispatch?.state||"DISABLED")}</h2></div><span class="source-tag">${execution?.occurred_at?`Último ciclo ${esc(timeLabel(execution.occurred_at))}`:"Sem ciclo executado"}</span></div><p class="field-note">${esc(data.dispatch?.reason||"")} ${execution?.state?`· Último resultado: ${esc(execution.state)}`:""}</p><div class="device-detail-grid">${dispatchRows||"<div class=\"empty-state\">Sem ações planeadas.</div>"}</div><p class="field-note">O ciclo automático usa a cadência configurada, com mínimo de 5 minutos. Cada alteração Tuya exige leitura e confirmação; um relé não confirmado bloqueia o minerador dependente.</p></section>
  ${ownerConfig?`<section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO OWNER · GUARDADA NO GATEWAY</p><h2>Capacidade e reserva da bateria</h2></div></div><p>O Gateway inicia uma âncora de tensão pelo pico dos últimos 30 dias, guarda-a no Gateway e integra cada nova amostra de carga/descarga uma só vez; não usa o SOC do inversor no cálculo operacional. Define a capacidade online e o SOC mínimo de corte.</p><div class="ws-config-grid"><label class="feature-field">Capacidade total (kWh)<input id="engine-battery-capacity" type="number" min="0" max="10000" step="0.1" value="${esc(data.configuration?.battery_capacity_kwh ?? "")}" placeholder="Ex.: 15"></label><label class="feature-field">SOC mínimo de reserva (%)<input id="engine-minimum-soc" type="number" min="0" max="99.9" step="1" value="${esc(data.configuration?.minimum_soc_percent ?? 20)}"></label><label class="feature-field">SOC máximo de carga (%)<input id="engine-maximum-soc" type="number" min="0.1" max="100" step="1" value="${esc(data.configuration?.maximum_soc_percent ?? 100)}"></label></div><div class="ws-actions"><button class="button primary" id="engine-save-config">Guardar bateria</button><span id="engine-config-status" class="ws-inline-note"></span></div></section><section class="panel feature-panel"><div class="panel-header"><div><p class="eyebrow">CARGAS FLEXÍVEIS · ATÉ 64</p><h2>Mineradora, AQS e aquecimento</h2></div><span class="source-tag">OWNER</span></div><p>Configura várias baterias e cargas sem alterar código: mineradora, cada AQS (smart ou por disjuntor Tuya), carregador EV, soalho radiante/toalheiro e cargas genéricas. Guarda as listas como JSON. Os códigos e IDs Tuya têm de corresponder a dispositivos configurados acima.</p><label class="feature-field">Bancos de bateria<input id="engine-banks-json" type="text" value="${esc(JSON.stringify(data.configuration?.battery_banks || []))}" aria-describedby="engine-json-help"></label><label class="feature-field">Cargas flexíveis<textarea id="engine-loads-json" rows="12" spellcheck="false">${esc(JSON.stringify(data.configuration?.loads || [], null, 2))}</textarea></label><p id="engine-json-help" class="field-note">Cada banco usa id, name, capacity_kwh, minimum_soc_percent, maximum_soc_percent e active (true online; false offline). Bancos em paralelo partilham tensão; por exemplo, três bancos de 15 kWh online somam 45 kWh. Cada carga usa id, name, kind, control_type, rated_power_w, priority, enabled e automatic. A lista aceita 64 cargas e 8 bancos.</p><fieldset><legend>Comissionamento e automatização</legend><label><input id="engine-deye-map-verified" type="checkbox" ${data.configuration?.automation?.deye_map_verified ? "checked" : ""}> Confirmo que validei no local o mapa Deye, os sinais de carga/descarga e o sentido dos CTs.</label><label><input id="engine-commissioned" type="checkbox" ${data.configuration?.automation?.commissioned ? "checked" : ""}> Confirmo que configurei limites, potência nominal e prioridades das cargas.</label><label><input id="engine-automation-enabled" type="checkbox" ${data.configuration?.automation?.enabled ? "checked" : ""}> Permitir despacho automático do Gateway.</label><label class="feature-field">Margem de excedente (W)<input id="engine-surplus-margin" type="number" min="0" max="10000" step="50" value="${esc(data.configuration?.automation?.surplus_margin_w ?? 250)}"></label><p class="field-note">Até à validação física, o despacho permanece bloqueado. As decisões usam telemetria Deye a cada 30 s e o ciclo de decisão tem mínimo de 5 min.</p></fieldset><div class="ws-actions"><button class="button primary" id="engine-save-equipment-config">Guardar cargas e automatização</button><span id="engine-equipment-config-status" class="ws-inline-note"></span></div></section>`:""}${renderEngineHistoryDialog()}`;
}
function renderLoadBuilder() {
  const devices = (state.tuyaDevices||[]).flatMap(device=>{
    const switches=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase()));
    return switches.length?switches.map((item,index)=>({device,code:item.code,label:device.capability_labels?.[item.code]||device.channel_labels?.[item.code]||item.name||`Canal ${index+1}`})):(device.switch_code?[{device,code:device.switch_code,label:"Interruptor"}]:[]);
  });
  const loads = state.energyEngine?.configuration?.loads || [];
  const relays = loads.filter(load => load.enabled && load.automatic && ["tuya_smart", "tuya_breaker"].includes(load.control_type));
  return `<section class="panel"><h3>Adicionar equipamento</h3><div class="ws-config-grid"><label class="feature-field">Nome<input id="engine-load-name" maxlength="120" placeholder="Ex.: AQS 2"></label><label class="feature-field">Tipo<select id="engine-load-kind"><option value="water_heater">AQS</option><option value="underfloor_heating">Soalho radiante / toalheiro</option><option value="miner">Mineradora</option><option value="ev_charger">Carregador EV</option><option value="generic">Outra carga</option></select></label><label class="feature-field">Comando<select id="engine-load-control"><option value="tuya_smart">Interruptor smart Tuya</option><option value="tuya_breaker">Disjuntor Tuya</option><option value="antminer_braiins">Braiins OS</option><option value="manual">Manual</option><option value="tesla_fleet">Tesla Fleet (leitura apenas)</option></select></label><label class="feature-field">Potência nominal (W)<input id="engine-load-rated" type="number" min="1" max="100000" step="1" value="1500"></label><label class="feature-field">Potência mínima (W, mineradora)<input id="engine-load-minimum" type="number" min="1" max="2900" step="1" value="800"></label><label class="feature-field">Potência máxima (W, mineradora)<input id="engine-load-maximum" type="number" min="1" max="2900" step="1" value="2500"></label><label class="feature-field">Prioridade (menor número primeiro)<input id="engine-load-priority" type="number" min="1" max="100" value="10"></label><label class="feature-field">Dispositivo e canal Tuya<select id="engine-load-tuya-device"><option value="">${devices.length ? "Escolhe dispositivo e canal" : "Sincroniza os interruptores Tuya no Owner primeiro"}</option>${devices.map(item=>`<option value="${esc(item.device.device_id)}" data-code="${esc(item.code)}">${esc(item.device.name)} · ${esc(item.label)} · ${esc(item.code)}</option>`).join("")}</select></label><label class="feature-field">Relé de alimentação mineradora<select id="engine-load-miner-relay"><option value="">Escolhe uma carga Tuya automática</option>${relays.map(load=>`<option value="${esc(load.id)}">${esc(load.name)} · ${esc(load.id)}</option>`).join("")}</select></label><label class="feature-field"><input id="engine-load-automatic" type="checkbox"> Elegível para automatização</label></div><div class="ws-actions"><button class="button secondary" id="engine-add-load" type="button">Adicionar à lista</button><span class="ws-inline-note">O equipamento só é guardado quando carregares em “Guardar cargas e automatização”.</span></div></section>`;
}
function card(item) {
  const category = CATEGORIES.find(c => c.id === item.category) || { icon: "•", label: item.category };
  const reading = formatReading(preferredGatewayReading(item));
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
  const equipment = state.equipment.find(item => item.category === "inversores" && !isSimulated(item));
  const reading = liveMetricReading(equipment, "pv_total_power");
  return liveHomeMetric("Painéis", reading?.value, reading?.unit || "W", "ϟ",
    reading ? `Produção FV · ${reading.trust || "UNKNOWN"}` : "Sem leitura de produção FV do Gateway", "", "paineis-solares");
}
function liveBatteryHomeMetric() {
  const equipment = state.equipment.find(item => item.category === "baterias" && !isSimulated(item));
  // Home and Energy must show the same operational SOC. The Deye-reported
  // percentage remains available in the engine diagnostics, but is not the
  // Gateway's voltage-anchor plus signed-power estimate.
  const integratedSoc = state.energyEngine?.current?.battery_soc_percent;
  const soc = typeof integratedSoc === "number" && Number.isFinite(integratedSoc) ? {value:integratedSoc,trust:"Estimativa integrada do Gateway"} : null;
  const rawPower = liveMetricReading(equipment, "battery_output_power");
  // The Deye candidate map reports negative while charging and positive while discharging.
  // Home presents the user-requested convention: charge positive, discharge negative.
  const signedPower = typeof rawPower?.value === "number" ? -rawPower.value : null;
  const flowClass = signedPower === null ? "" : signedPower < 0 ? "discharge" : signedPower > 0 ? "charge" : "idle";
  const flowLabel = signedPower === null ? "Potência da bateria sem leitura"
    : `${signedPower > 0 ? "+" : ""}${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 1 }).format(signedPower)} ${rawPower.unit || "W"} · ${signedPower < 0 ? "a descarregar" : signedPower > 0 ? "a carregar" : "sem fluxo"}`;
  const formattedSoc = typeof soc?.value === "number" ? new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 1 }).format(soc.value) : "—";
  const trust = soc?.trust || rawPower?.trust || "UNKNOWN";
  return `<button type="button" class="metric-card home-metric-link" data-page="baterias" aria-label="Abrir área Baterias"><span class="metric-top"><span>Bateria</span><span class="metric-symbol">▤</span></span><span class="metric-value">${esc(formattedSoc)} <small>${soc ? "%" : ""}</small></span><span class="metric-sub">${esc(soc ? trust : "Estimativa do Gateway indisponível")}</span><span class="metric-sub battery-flow ${flowClass}">${esc(flowLabel)}</span></button>`;
}
function liveMinerHomeMetric() {
  const equipment = state.equipment.find(item => item.category === "mineradoras" && !isSimulated(item));
  const currentHash = liveMetricReading(equipment, "miner_hashrate_5s_ghs") || liveMetricReading(equipment, "miner_hashrate_avg_ghs");
  const hashThs = typeof currentHash?.value === "number" ? currentHash.value / 1000 : null;
  const hashUnit = hashThs === null ? "" : "TH/s";
  const minerPower = liveMetricReading(equipment, "miner_power_w");
  const powerLimit = liveMetricReading(equipment, "miner_power_limit_w");
  const sub = [
    minerPower ? `Consumo ${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 0 }).format(minerPower.value)} W` : null,
    powerLimit ? `Limite reportado ${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 0 }).format(powerLimit.value)} W` : null,
    !currentHash && equipment?.connection_state === "CONNECTED" ? "API ligada · hashrate indisponível" : null,
    !equipment ? "Sem leitura da Antminer" : null,
  ].filter(Boolean).join(" · ");
  const detail = currentHash ? `${currentHash.field === "miner_hashrate_5s_ghs" ? "Taxa atual" : "Taxa média"} · ${currentHash.trust || "UNKNOWN"}` : "Hashrate sem leitura do Gateway";
  const extra = sub ? `<span class="metric-sub miner-power-details">${esc(sub)}</span>` : "";
  return liveHomeMetric("Mineradora", hashThs, hashUnit, "▦", detail, extra, "mineradoras");
}
function chart() {
  if (state.mode !== "SIMULATED") {
    const engine=state.energyEngine||{},history=engine.history||{},forecast=engine.forecast||{},now=Date.now(),start=now-3*3600000,end=now+6*3600000;
    const point=(item,forcedUnit)=>{const stamp=Date.parse(item.observed_at||item.forecast_at||"");let value=Number(item.value);if(!Number.isFinite(stamp)||!Number.isFinite(value))return null;if((item.unit||forcedUnit)==="W")value/=1000;return {stamp,value};};
    const historical=field=>(history[field]||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=start&&p.stamp<=now);
    const future=items=>(items||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=now&&p.stamp<=end);
    const pvActual=historical("pv_total_power").sort((a,b)=>a.stamp-b.stamp);
    const pvForecast=future(forecast.solar_expected?.hourly_values).sort((a,b)=>a.stamp-b.stamp);
    const loadActual=historical("load_total_power").sort((a,b)=>a.stamp-b.stamp);
    const loadForecast=future(forecast.load_power?.hourly_values).sort((a,b)=>a.stamp-b.stamp);
    const potential=(forecast.solar_potential?.hourly_values||[]).map(item=>point(item)).filter(p=>p&&p.stamp>=start&&p.stamp<=end).sort((a,b)=>a.stamp-b.stamp);
    const all=[...pvActual,...pvForecast,...loadActual,...loadForecast,...potential];
    if(!all.length)return `<div class="empty-state">Ainda não há leituras ou previsão. Configura a localização e a potência FV na área Owner.</div>`;
    const max=Math.max(1,...all.map(p=>p.value)),x=stamp=>45+Math.max(0,Math.min(1,(stamp-start)/(end-start)))*555,y=value=>235-Math.max(0,value)/max*190;
    const path=items=>items.map((p,i)=>`${i?"L":"M"}${x(p.stamp).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
    const hourly=items=>{const bins=new Map();for(const p of items){const hour=Math.floor(p.stamp/3600000)*3600000;const bin=bins.get(hour)||{stamp:hour,total:0,count:0};bin.total+=p.value;bin.count++;bins.set(hour,bin);}return [...bins.values()].map(b=>({stamp:b.stamp,value:b.total/b.count})).sort((a,b)=>a.stamp-b.stamp);};
    const loadHistoryBars=hourly(loadActual).map(p=>({...p,future:false})),loadForecastBars=hourly(loadForecast).map(p=>({...p,future:true}));
    const bars=items=>items.map(p=>`<rect x="${(x(p.stamp)-26).toFixed(1)}" y="${y(p.value).toFixed(1)}" width="52" height="${Math.max(0,235-y(p.value)).toFixed(1)}" rx="2" fill="${p.future?'transparent':'#a9c7d9'}" stroke="#a9c7d9" stroke-width="1.5" ${p.future?'stroke-dasharray="2 2"':''}><title>${new Date(p.stamp).toLocaleTimeString("pt-PT",{hour:"2-digit"})} · ${p.future?'consumo previsto':'consumo medido'} ${p.value.toFixed(2)} kW</title></rect>`).join("");
    const actualLine=path(pvActual),forecastLine=path(pvForecast.length&&pvActual.length?[pvActual.at(-1),...pvForecast]:pvForecast),historicalPotential=potential.filter(p=>p.stamp<=now),futurePotential=potential.filter(p=>p.stamp>=now);
    const hourStart=Math.floor(start/3600000)*3600000,hourEnd=Math.ceil(end/3600000)*3600000,valueAt=(items,hour)=>hourly(items).find(p=>p.stamp===hour)?.value;
    const hitTargets=[];for(let hour=hourStart;hour<=hourEnd;hour+=3600000){const loadValue=valueAt([...loadActual,...loadForecast],hour),pvValue=valueAt([...pvActual,...pvForecast],hour),potentialValue=valueAt(potential,hour);if(loadValue===undefined&&pvValue===undefined&&potentialValue===undefined)continue;hitTargets.push(`<rect class="solar-chart-hit" x="${Math.max(45,x(hour)-28).toFixed(1)}" y="34" width="56" height="203" tabindex="0" role="button" data-hour="${hour}" data-load="${loadValue??''}" data-pv="${pvValue??''}" data-potential="${potentialValue??''}" data-future="${hour>now}" aria-label="Ver valores das ${new Date(hour).toLocaleTimeString('pt-PT',{hour:'2-digit'})}"><title>Ver valores das ${new Date(hour).toLocaleTimeString('pt-PT',{hour:'2-digit'})}</title></rect>`);}
    const yTicks=[0,.25,.5,.75,1].map(f=>`<text x="4" y="${(235-f*190+4).toFixed(0)}">${(max*f).toFixed(1)} kW</text>`).join("");
    return `<div class="solar-chart-wrap"><svg class="chart solar-window-chart" viewBox="0 0 620 310" preserveAspectRatio="none" role="group" aria-label="Consumo em barras; Produção efetiva: linha azul; Produção potencial calculada: linha dourada. Eixo vertical em quilowatts; passado sólido, previsão pontilhada."><path class="chart-grid" d="M45 45H600 M45 92H600 M45 140H600 M45 187H600 M45 235H600"/><g class="chart-label solar-y-axis">${yTicks}</g><g>${bars(loadHistoryBars)}${bars(loadForecastBars)}</g>${actualLine?`<path d="${actualLine}" fill="none" stroke="#79bce8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:''}${forecastLine?`<path d="${forecastLine}" fill="none" stroke="#79bce8" stroke-width="3" stroke-dasharray="3 6" stroke-linecap="round" stroke-linejoin="round"/>`:''}${historicalPotential.length?`<path d="${path(historicalPotential)}" fill="none" stroke="#dcc99c" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:''}${futurePotential.length?`<path d="${path(futurePotential.length&&historicalPotential.length?[historicalPotential.at(-1),...futurePotential]:futurePotential)}" fill="none" stroke="#dcc99c" stroke-width="3" stroke-dasharray="3 6" stroke-linecap="round" stroke-linejoin="round"/>`:''}<path d="M230 34V240" stroke="#8f897a" stroke-dasharray="3 4"/><g class="chart-label solar-x-axis"><text x="45" y="275">−3 h</text><text x="218" y="275">agora</text><text x="414" y="275">+3 h</text><text x="570" y="275">+6 h</text></g><g>${hitTargets.join('')}</g></svg><div class="solar-chart-tooltip" role="status" aria-live="polite" hidden></div></div><div class="solar-chart-legend"><span><i class="solar-legend-load"></i>Consumo</span><span><i class="solar-legend-pv"></i>Produção</span><span><i class="solar-legend-potential"></i>Produção potencial</span></div>`;
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
function favoriteDeviceCards() {
  const canUsePwa=sessionInfo().authenticated,canControl=canUsePwa&&sessionInfo().user?.role==="owner";
  if(state.mode!=="LIVE")return `<div class="favorite-device-grid"><p class="field-note">Os dispositivos favoritos aparecem aqui quando o Gateway está ligado.</p></div>`;
  const tuya=(state.tuyaDevices||[]).map(device=>({id:device.device_id,name:device.name,kind:"tuya",device}));
  const registered=(state.equipment||[]).map(device=>({id:device.id,name:device.name,kind:"equipment",device}));
  const all=[...registered,...tuya].filter((item,index,items)=>items.findIndex(other=>other.id===item.id)===index);
  const favorites=Array.isArray(workspace.prefs.favoriteDeviceIds)?workspace.prefs.favoriteDeviceIds:[];
  workspace.prefs.favoriteDeviceIds=favorites.filter(id=>all.some(item=>item.id===id));
  const meta=favoriteMeta(),readings=state.tuyaReadings||[];
  const rows=all.filter(item=>workspace.prefs.favoriteDeviceIds.includes(item.id)).map(item=>{
    const {device,kind,id}=item,details=meta[id]||{};
    if(kind==="equipment")return {id,kind,device,details,reading:preferredGatewayReading(device)};
    const status=readings.find(entry=>entry.device_id===id),values=status?.status||[];
    const codes=[...new Set([...(device.switch_channels||[]),...(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase())).map(item=>item.code),device.switch_code].filter(Boolean))];
    const channels=codes.map(code=>({code,value:values.find(item=>item.code===code)?.value,label:device.channel_labels?.[code]||device.capability_labels?.[code]||code}));
    const level=values.find(entry=>entry.code===device.level_code)?.value,isLevel=Boolean(device.level_code);
    const percent=isLevel&&Number.isFinite(Number(level))?Math.max(0,Math.min(100,Math.round((Number(level)-Number(device.level_min??0))/(Number(device.level_max??100)-Number(device.level_min??0))*100))):null;
    return {id,kind,device,details,status,channels,isLevel,percent};
  });
  const powerGlyph=`<svg viewBox="0 0 28 28" aria-hidden="true" focusable="false"><path d="M19.25 4.9a10.5 10.5 0 1 1-10.5 0"/><path d="M14 2.4v10.2"/></svg>`;
  const stateSymbol=(id,channel,enabled)=>`<button type="button" class="favorite-state-symbol ${channel.value===true?"on":channel.value===false?"off":"unknown"}" data-favorite-toggle="${esc(id)}" data-favorite-code="${esc(channel.code)}" aria-pressed="${channel.value===true}" aria-label="${esc(channel.label)}: ${channel.value===true?"ligado":channel.value===false?"desligado":"sem leitura"}" title="${esc(channel.label)}" ${!enabled||typeof channel.value!=="boolean"?"disabled":""}>${powerGlyph}</button>`;
  return `<div class="favorite-manage"><span>Os dispositivos configurados no Gateway podem ser fixados aqui.</span>${canUsePwa?`<button type="button" class="favorite-add-button" id="home-favorite-plus" aria-label="Adicionar dispositivo ou favorito" title="Adicionar">＋</button>`:""}</div><div class="favorite-device-grid">${rows.map(({id,kind,device,details,status,channels,isLevel,percent,reading})=>{
    const label=details.label||device.name,place=[details.room||device.room,details.floor||device.floor].filter(Boolean).join(" · ")||device.logical_location||"Localização por definir";
    const channelButtons=kind==="tuya"?channels.map(channel=>stateSymbol(id,channel,canControl&&status?.connection_state==="local_responded")).join(""):"";
    return `<article class="favorite-device" data-favorite-device="${esc(id)}" data-device-kind="${kind}" aria-label="${esc(label)}"><div class="favorite-device-info"><strong class="favorite-device-name">${esc(label)}</strong><span>${esc(place)}</span></div><div class="favorite-device-actions">${kind==="tuya"?(channelButtons||`<span class="favorite-state-symbol unknown" aria-label="Estado indisponível">${powerGlyph}</span>`):`<span class="favorite-state-symbol unknown" title="${esc(reading?.field||"Estado não disponível")}">${powerGlyph}</span>`}</div></article>`;
  }).join("")}${!rows.length?`<p class="field-note">Ainda não há dispositivos favoritos. Usa ＋ para escolher um equipamento registado no Gateway.</p>`:""}</div>`;
}
function openFavoriteDialog(){
  const devices=[...(state.equipment||[]).map(device=>({id:device.id,name:device.name,kind:"equipment",category:device.category})),...(state.tuyaDevices||[]).map(device=>({id:device.device_id,name:device.name,kind:"tuya",category:"Tuya / MOES"}))];
  const favorites=workspace.prefs.favoriteDeviceIds||[], available=devices.filter((device,index)=>!favorites.includes(device.id)&&devices.findIndex(other=>other.id===device.id)===index);
  const owner=sessionInfo().authenticated&&sessionInfo().user?.role==="owner";
  const dialog=document.createElement("dialog"); dialog.className="home-device-dialog"; dialog.innerHTML=`<form method="dialog" class="home-device-dialog-card"><button class="home-dialog-close" aria-label="Fechar">×</button><p class="eyebrow">DISPOSITIVOS FAVORITOS</p><h2>Adicionar dispositivo</h2><div class="home-device-actions"><button type="button" class="button secondary" id="home-existing-device">Adicionar favorito existente</button>${owner?`<button type="button" class="button primary" id="home-new-device">Configurar novo Tuya / MOES</button>`:""}</div><div id="home-favorite-existing" hidden><label>Dispositivo registado no Gateway<select id="home-favorite-select"><option value="">Escolher dispositivo…</option>${available.map(device=>`<option value="${esc(device.id)}">${esc(device.name)} · ${esc(device.category||device.kind)}</option>`).join("")}</select></label><label>Divisão<input id="home-favorite-room" maxlength="80" placeholder="Sala de estar"></label><label>Piso<input id="home-favorite-floor" maxlength="80" placeholder="Rés-do-chão"></label><button type="button" class="button primary" id="home-add-existing">Adicionar aos meus favoritos</button></div>${owner?`<div id="home-favorite-new" hidden><label>ID do dispositivo Tuya<input id="home-new-id" maxlength="128" autocomplete="off"></label><label>Nome<input id="home-new-name" maxlength="120" placeholder="Luz do teto"></label><label>Tipo<select id="home-new-kind"><option value="switch">Interruptor / disjuntor</option><option value="dimmer">Luz regulável</option><option value="blind">Estore / persiana</option></select></label><label>Código ON/OFF (opcional)<input id="home-new-switch-code" maxlength="64" placeholder="switch_1"></label><label>Código de nível / posição<input id="home-new-level-code" maxlength="64" placeholder="bright_value ou position"></label><div class="home-level-range"><label>Valor mínimo Tuya<input id="home-new-level-min" type="number" min="0" max="99999" value="0"></label><label>Valor máximo Tuya<input id="home-new-level-max" type="number" min="1" max="100000" value="100"></label></div><label>Divisão<input id="home-new-room" maxlength="80" placeholder="Sala de estar"></label><label>Piso<input id="home-new-floor" maxlength="80" placeholder="Rés-do-chão"></label><button type="button" class="button primary" id="home-register-device">Guardar no Gateway e adicionar</button></div>`:""}<p id="home-device-dialog-status" role="status"></p></form>`;
  $("#page-content").append(dialog); dialog.addEventListener("close",()=>dialog.remove()); dialog.showModal();
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
    return `<div class="page-heading home-page-heading"><div><p class="eyebrow">ENERGIA DA PROPRIEDADE</p><h1>Home</h1></div><div class="date-block"><strong>${esc(state.dataStatus)}</strong><br>${esc(updated)}</div></div><div class="home-weather-row">${renderHomeWeatherCard()}${renderHomeProductionCard()}</div>
      <section class="panel home-favorites"><div class="favorite-heading"><div><p class="eyebrow">CONTROLO RÁPIDO</p><h2>Dispositivos favoritos</h2></div></div>${favoriteDeviceCards()}</section>
      <div class="metric-grid">${liveSolarHomeMetric()}${liveBatteryHomeMetric()}${liveMinerHomeMetric()}${liveReadingMetric("Veículo elétrico", "ev", "↗")}</div>
      <div class="content-grid"><section class="panel chart-panel"><div class="panel-header"><div><p class="eyebrow">HISTÓRICO + PREVISÃO</p><h2>Energia · 3 h medidas + 6 h previstas</h2><p>Produção FV, consumo e potencial solar calculado.</p></div><span class="source-tag">${esc(state.dataStatus)}</span></div>${chart()}</section><section class="panel flow-panel"><div class="panel-header"><div><p class="eyebrow">AGORA</p><h2>Equipamentos ativos</h2></div><button class="text-link" type="button" id="live-refresh">Atualizar ↻</button></div>${flowPanel()}</section></div>
      <div class="section-heading section-heading-spaced"><div><p class="eyebrow">INSTALAÇÃO</p><h2>Equipamentos e leituras</h2></div><span class="muted-inline">${state.equipment.length} equipamentos</span></div><div class="equipment-grid">${cards}</div>`;
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
  ${equipment.length ? equipment.map(item=>`<section class="panel detail-panel"><div class="panel-header"><div><h2>${esc(item.name)}</h2><p>Informação de origem e estado</p></div><span class="source-tag">${isSimulated(item)?"SIMULATED":esc(item.readings?.[0]?.trust||"UNKNOWN")}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Fabricante / modelo</small><strong>${esc([item.manufacturer,item.model].filter(Boolean).join(" · ")||"Não definido")}</strong></div><div class="detail-item"><small>Ligação</small><strong>${esc(item.connection_state||"UNKNOWN")}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(timeLabel(item.last_communication_at))}</strong></div><div class="detail-item"><small>Origem</small><strong>${esc(item.source||item.readings?.[0]?.source||"API_GATEWAY")}</strong></div><div class="detail-item"><small>Confiança</small><strong>${esc(item.readings?.[0]?.trust||"UNKNOWN")}</strong></div><div class="detail-item"><small>Leitura principal</small><strong>${esc(reading.value)} ${esc(reading.unit)}</strong></div></div><div class="status-banner demo-banner"><span class="demo-stamp">INFO</span><span>Leituras registadas pelo Gateway. Valores Deye identificados como LIVE_UNVERIFIED até validação adicional do modelo e logger.</span></div>${item.readings?.length ? `<div class="device-detail-grid telemetry-grid">${item.readings.map(value=>`<div class="detail-item"><small>${esc(value.evidence?.label || value.field)}</small><strong>${esc(formatReading(value).value)} ${esc(value.unit || "")}</strong><small>${esc(value.field)}${value.evidence?.register ? ` · registo ${esc(value.evidence.register)}` : ""}</small></div>`).join("")}</div>` : ""}</section>`).join("") : `<div class="empty-state">Não existem equipamentos nesta área no Gateway. Nenhum valor foi inventado.</div>`}`;
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
  return `<dialog id="pv-string-dialog" class="settings-dialog"><form id="pv-string-form" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">CONFIGURAÇÃO FV · GATEWAY</p><h2 id="pv-string-title">Adicionar string</h2></div><button type="button" class="icon-button" data-pv-string-close aria-label="Fechar">×</button></div><label>Nome da string<input name="name" maxlength="120" required></label><label>Fabricante<input name="manufacturer" maxlength="120" required></label><div class="ws-config-grid"><label>Número de painéis<input name="panel_count" type="number" min="1" max="2000" step="1" required></label><label>Potência por painel (W)<input name="panel_power_w" type="number" min="1" max="2500" step="1" required></label></div><label>Entrada<select name="mppt"><option value="1">MPPT 1</option><option value="2">MPPT 2</option></select></label><label><input name="active" type="checkbox" checked> String online</label><input name="id" type="hidden"><p class="field-note" id="pv-string-total-power" aria-live="polite">Potência total calculada: —</p><p class="field-note" id="pv-string-status" role="status"></p><div class="dialog-actions"><button type="button" class="button danger" id="pv-string-remove" hidden>Remover</button><span class="dialog-actions-spacer"></span><button type="button" class="button secondary" data-pv-string-close>Cancelar</button><button type="submit" class="button primary">Guardar</button></div></form></dialog>`;
}
function renderAqsDialog(){
  const channels=(state.tuyaDevices||[]).flatMap(device=>(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase())).map(item=>({device,channel:item})));
  return `<dialog id="aqs-dialog" class="settings-dialog"><form id="aqs-form" class="dialog-body"><div class="dialog-header"><div><p class="eyebrow">EQUIPAMENTO · AQS</p><h2 id="aqs-title">Adicionar AQS</h2></div><button type="button" class="icon-button" data-aqs-close aria-label="Fechar">×</button></div><label>Nome<input name="name" maxlength="120" required placeholder="Ex.: Termoacumulador"></label><label>Fabricante<input name="manufacturer" maxlength="120" required></label><div class="ws-config-grid"><label>Volume (litros)<input name="volume_l" type="number" min="1" max="100000" step="1" required></label><label>Potência nominal (W)<input name="rated_power_w" type="number" min="1" max="100000" step="1" required></label></div><label>Disjuntor Tuya associado<select name="tuya_binding"><option value="">Sem associação</option>${channels.map(({device,channel})=>`<option value="${esc(device.device_id)}|${esc(channel.code)}">${esc(device.name)} · ${esc(tuyaFriendlyCapabilityLabel(channel,device)||channel.name||channel.code)}</option>`).join("")}</select></label><p class="field-note">A associação apenas guarda o dispositivo e o canal escolhidos. Não liga nem desliga o disjuntor.</p><input name="id" type="hidden"><p class="field-note" id="aqs-status" role="status"></p><div class="dialog-actions"><button type="button" class="button danger" id="aqs-remove" hidden>Remover</button><span class="dialog-actions-spacer"></span><button type="button" class="button secondary" data-aqs-close>Cancelar</button><button type="submit" class="button primary">Guardar</button></div></form></dialog>`;
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
function openPvStringDialog(item=null){
  const dialog=$("#pv-string-dialog"),form=$("#pv-string-form");if(!dialog||!form)return;
  form.elements.name.value=item?.name||`String ${(state.energyEngine?.configuration?.pv_strings||[]).length+1}`;
  form.elements.manufacturer.value=item?.manufacturer||"";form.elements.panel_count.value=item?.panel_count??"";form.elements.panel_power_w.value=item?.panel_power_w??"";
  form.elements.mppt.value=String(item?.mppt||1);
  form.elements.active.checked=item?.active!==false;form.elements.id.value=item?.id||"";
  updatePvStringTotalPower(form);
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
function openAqsDialog(item=null){
  const dialog=$("#aqs-dialog"),form=$("#aqs-form");if(!dialog||!form)return;
  form.elements.name.value=item?.name||"";form.elements.manufacturer.value=item?.manufacturer||"";
  form.elements.volume_l.value=item?.volume_l??"";form.elements.rated_power_w.value=item?.rated_power_w??"";
  form.elements.tuya_binding.value=item?.tuya_device_id&&item?.tuya_switch_code?`${item.tuya_device_id}|${item.tuya_switch_code}`:"";
  form.elements.id.value=item?.id||"";$("#aqs-title").textContent=item?`Editar ${item.name}`:"Adicionar AQS";
  $("#aqs-remove").hidden=!item;$("#aqs-status").textContent="";dialog.dataset.mode=item?"edit":"add";
  if(!dialog.open)dialog.showModal();
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
  const equipmentCards=page==="baterias"?batteryEquipmentCard:page==="paineis-solares"?`${panelReadings||`<div class="empty-state">O Deye ainda não forneceu leituras de MPPT.</div>`}${renderPvStringsSection(config,isOwner)}`:page==="aqs"?renderAqsSection(config,isOwner):items.map(item=>`<section class="panel detail-panel gateway-area-device"><div class="panel-header"><div><p class="eyebrow">${esc(item.manufacturer||"EQUIPAMENTO")}${item.model?` · ${esc(item.model)}`:""}</p><h2>${esc(item.name)}</h2></div><span class="source-tag">${esc(item.connection_state||item.status||"UNKNOWN")}</span></div><div class="device-detail-grid"><div class="detail-item"><small>Ligação</small><strong>${esc(item.connection_state||"Desconhecida")}</strong></div><div class="detail-item"><small>Última comunicação</small><strong>${esc(timeLabel(item.last_communication_at))}</strong></div><div class="detail-item"><small>Protocolo</small><strong>${esc(item.protocol||"Não indicado")}</strong></div></div>${deyeReadings}${item.readings?.length&&page!=="inversores"&&page!=="paineis-solares"?`<div class="device-detail-grid telemetry-grid">${item.readings.map(value=>`<div class="detail-item"><small>${esc(value.evidence?.label||value.field)}</small><strong>${esc(formatReading(value).value)} ${esc(value.unit||"")}</strong></div>`).join("")}</div>`:""}</section>`).join("");
  const description=page==="paineis-solares"?"Strings configuradas e leituras fotovoltaicas agregadas por MPPT.":page==="inversores"?"Estado do inversor, tensões de saída e potência entregue às cargas.":page==="baterias"?"SOC, potência assinada e limites que o Gateway observou.":page==="aqs"?"Termoacumuladores, potência nominal e associação opcional a um canal Tuya.":"Dados e leituras atuais fornecidos pelo Gateway autenticado.";
  const solarDay=engine.forecast?.solar_day||{};
  const solarDayCard=page==="energia"?`<article class="ws-kpi solar-day-forecast-card"><small>Produção solar prevista até ao fim do dia</small><strong>${solarDay.state==="ESTIMATED"&&Number.isFinite(Number(solarDay.estimated_total_kwh))?esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.estimated_total_kwh))):"—"} <em>kWh</em></strong><span>${solarDay.state==="ESTIMATED"?`${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.actual_today_kwh)||0))} kWh produzidos · ${esc(new Intl.NumberFormat("pt-PT",{maximumFractionDigits:1}).format(Number(solarDay.remaining_estimate_kwh)||0))} kWh previstos · recalcula em até 10 min`:`Previsão indisponível: ${esc(solarDay.reason||"a aguardar dados do Gateway")}${solarDay.reason?.includes("potência nominal FV")?" Abre Owner → Produção → Previsão solar adaptativa e indica a potência total dos painéis em kWp.":""}`}</span></article>`:"";
  const energyOutlookCard="";
  return `${page!=="energia"?`<div class="ws-horizontal-tabs energy-tabs" role="tablist" aria-label="Áreas energéticas">${[["inversores","Inversores"],["baterias","Baterias"],["paineis-solares","Painéis"],["ev","Carregador EV"],["aqs","AQS"],["mineradoras","Mineradoras"],["soalho-radiante","Soalho radiante"]].map(([id,label])=>`<button role="tab" aria-selected="${page===id}" class="${page===id?"selected":""}" data-page="${id}">${label}</button>`).join("")}</div>`:""}<div class="page-heading"><div><p class="eyebrow">GATEWAY · DADOS REAIS</p><h1>${esc(labels[page]||page)}</h1><p>${esc(description)}</p></div>${page==="energia"?"":`<button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button>`}</div><div class="ws-kpi-grid">${metrics.map(metricCard).join("")}</div>${energyOutlookCard}${page==="energia"?`<section class="panel"><div class="panel-header"><div><p class="eyebrow">INSTALAÇÃO</p><h2>Explorar áreas</h2></div></div><div class="ws-area-grid">${[["engine","Engine energético"],["inversores","Inversores"],["baterias","Baterias"],["paineis-solares","Painéis solares"],["mineradoras","Mineradoras"],["ev","Carregador EV"],["aqs","AQS"],["soalho-radiante","Soalho radiante"]].map(([id,label])=>`<button class="ws-area-card" data-page="${id}"><span class="ws-area-icon">◉</span><span><strong>${label}</strong><small>${id==="engine"?"Histórico, previsões e estado energético":"Ver estado e leituras do Gateway"}</small></span><span class="ws-arrow">↗</span></button>`).join("")}</div></section>`:""}${batteryConfig}${page!=="energia"?(equipmentCards||`<div class="empty-state">O Gateway ainda não forneceu equipamentos ou leituras para esta área. Confirma a configuração correspondente na página Owner e volta a atualizar.</div>`):""}`;
}
function renderGatewayUtilityPage(page){
  if(page==="automatismos"){
    const automation=state.energyEngine?.configuration?.automation||{};
    const active=automation.enabled===true&&automation.commissioned===true&&automation.deye_map_verified===true;
    return `<div class="page-heading"><div><p class="eyebrow">GATEWAY · REGRAS</p><h1>Automatismos</h1><p>Estado das regras executadas pelo Gateway.</p></div><button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button></div><section class="panel"><div class="panel-header"><div><p class="eyebrow">EXECUÇÃO</p><h2>${active?"Ativa":"Pausada"}</h2></div><span class="source-tag">${active?"GATEWAY":"SEM EXECUÇÃO"}</span></div><p class="field-note">O Engine energético, com previsões e histórico, está em Energia → Engine. As regras só executam quando estão configuradas e comissionadas no Gateway.</p>${automation.enabled?`<div class="device-detail-grid"><div class="detail-item"><small>Intervalo de avaliação</small><strong>${esc(String(automation.decision_interval_seconds||300))} s</strong></div><div class="detail-item"><small>Mapa do inversor</small><strong>${automation.deye_map_verified?"Verificado":"Por verificar"}</strong></div><div class="detail-item"><small>Comissionamento</small><strong>${automation.commissioned?"Concluído":"Pendente"}</strong></div></div>`:`<div class="empty-state">Não há automatismos ativos no Gateway.</div>`}</section>`;
  }
  if(page==="producao")return renderLiveEnergyEngine();
  if(page==="casa")return renderGatewayHousePage();
  const items=state.equipment||[];
  const user=sessionInfo().user||{};
  if(page==="profile")return `<div class="page-heading"><div><p class="eyebrow">CONTA DO GATEWAY</p><h1>Perfil</h1><p>Identidade e permissões confirmadas pelo Gateway nesta sessão.</p></div></div><section class="panel"><div class="device-detail-grid"><div class="detail-item"><small>Utilizador</small><strong>${esc(user.username||"—")}</strong></div><div class="detail-item"><small>Papel</small><strong>${esc(user.role||"—")}</strong></div><div class="detail-item"><small>Sessão</small><strong>${sessionInfo().authenticated?"Autenticada":"Sem sessão"}</strong></div><div class="detail-item"><small>Gateway</small><strong>${esc(state.mode==="LIVE"?"Ligado":"Indisponível")}</strong></div></div><p class="field-note">Permissões, utilizadores e dispositivos autorizados são geridos no Gateway. Preferências visuais deste browser não alteram essas permissões.</p><button class="button secondary" id="profile-open-gateway" type="button">Gerir ligação</button></section>`;
  const cards=items.filter(item=>page!=="devices"||! ["inversores","baterias"].includes(item.category)).map(item=>`<article class="panel detail-panel"><div class="panel-header"><div><p class="eyebrow">${esc(item.category||"EQUIPAMENTO")}</p><h2>${esc(item.name)}</h2></div><span class="source-tag">${esc(item.connection_state||item.status||"UNKNOWN")}</span></div><p>${esc([item.manufacturer,item.model,item.protocol].filter(Boolean).join(" · ")||"Sem detalhes de fabricante/modelo")}</p>${item.readings?.length?`<div class="device-detail-grid telemetry-grid">${item.readings.map(reading=>`<div class="detail-item"><small>${esc(reading.evidence?.label||reading.field)}</small><strong>${esc(formatReading(reading).value)} ${esc(reading.unit||"")}</strong><small>${esc(reading.trust||"UNKNOWN")}</small></div>`).join("")}</div>`:`<div class="empty-state">Sem leituras registadas.</div>`}</article>`).join("");
  const controlledInventory=page==="devices"?"<p>Equipamentos nesta lista podem ser controlados pelo Gateway. O Deye, as baterias e outros equipamentos de leitura ficam nas áreas de Energia.</p>":"<p>Equipamentos recebidos da base de dados do Gateway, agrupados nesta vista.</p>";
  const tuyaCards=page==="devices"?(state.tuyaDevices||[]).map(device=>{const channels=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase()));const identity=[device.category,device.product_name].filter(Boolean).join(" · ");const glyph=tuyaDeviceGlyph(device);return `<button type="button" class="panel detail-panel tuya-inventory-card" data-edit-tuya-device="${esc(device.device_id)}"><div class="panel-header"><div class="tuya-device-glyph" aria-hidden="true">${glyph}</div><div><p class="eyebrow">TUYA / MOES${identity?` · ${esc(identity)}`:""}</p><h2>${esc(device.name)}</h2></div><span class="source-tag">${device.online===true?"ONLINE":device.online===false?"OFFLINE":"TUYA"}</span></div><p>${channels.length?`${channels.length} canal${channels.length===1?"":"is"} · `:""}${esc(device.room||"Sem divisão atribuída")}${device.floor?` · ${esc(device.floor)}`:""}</p><span class="text-link">Ver características e editar ↗</span></button>`;}).join(""):"";
  const emptyInventory=!cards&&!tuyaCards?`<div class="empty-state">Ainda não existem dispositivos registados no Gateway. Os inversores e baterias ficam nas áreas de Energia.</div>`:"";
  return `<div class="page-heading"><div><p class="eyebrow">${page==="devices"?"CONTROLO · GATEWAY":"INVENTÁRIO · GATEWAY"}</p><h1>${page==="casa"?"Casa":"Dispositivos"}</h1>${controlledInventory}</div>${page==="energia"?"":`<button class="button secondary" id="gateway-area-refresh">Atualizar ↻</button>`}</div>${page==="devices"&&sessionInfo().user?.role==="owner"?`<section class="panel"><div class="panel-header"><div><p class="eyebrow">CONFIGURAÇÃO</p><h2>Dispositivos sincronizados</h2></div><button class="button secondary" data-page="owner">Abrir gestão Owner</button></div><p class="field-note">Toca num dispositivo para editar os nomes dos canais e atribuir uma divisão. Estas alterações ficam no Gateway e não mudam nomes na conta Tuya.</p></section>`:""}<div class="equipment-grid">${cards}${tuyaCards}${emptyInventory}</div>`;
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
  const gatewayBackedPages = ["inicio", "engine", ...CATEGORIES.map(c => c.id), ...liveAreaPages, ...liveUtilityPages];
  let pageHtml;
  if (state.mode !== "SIMULATED" && !gatewayBackedPages.includes(state.page)) {
    pageHtml = `<div class="page-heading"><div><p class="eyebrow">FUNÇÃO NÃO DISPONÍVEL NO GATEWAY ATUAL</p><h1>${esc(pageLabel(state.page))}</h1><p>Esta área ainda não tem um contrato de dados ou comandos físicos no Gateway. Para evitar confusão, a sessão autenticada não apresenta controlos ou valores de demonstração aqui.</p></div></div><div class="empty-state">Sem dados reais fornecidos pelo Gateway para esta área. A administração está na página Owner.</div>`;
  } else {
    pageHtml = state.page === "inicio" ? renderOverview() : state.mode!=="SIMULATED"&&liveAreaPages.includes(state.page)?renderGatewayArea(state.page):state.mode!=="SIMULATED"&&liveUtilityPages.includes(state.page)?renderGatewayUtilityPage(state.page):state.page === "engine" && state.mode !== "SIMULATED" ? renderLiveEnergyEngine() : (workspacePage || (CATEGORIES.some(c=>c.id===state.page) ? renderCategory(state.page) : renderOverview()));
    if (state.page === "engine" && sessionInfo().user?.role === "owner") pageHtml = pageHtml.replace('<label class="feature-field">Cargas flexíveis', `${renderLoadBuilder()}<label class="feature-field">Cargas flexíveis`);
    if(state.mode === "SIMULATED" && state.page === "automatismos") pageHtml = renderAutomationsPage(workspace, automationEditingId);
    if(state.mode === "SIMULATED" && state.page === "producao") pageHtml = renderSolarProductionPage();
    if(state.mode === "SIMULATED" && state.page === "profile") pageHtml += renderDemoAdminPanel();
  }
  const energyTabScroll=$("#page-content .energy-tabs")?.scrollLeft||0;
  $("#page-content").innerHTML = pageHtml;
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
  if (!["inicio", ...CATEGORIES.map(c=>c.id), "energia", "casa", "profile", "engine", "devices", "inversores", "baterias", "paineis-solares", "ev", "aqs", "mineradoras", "soalho-radiante", "automatismos", "producao", "owner"].includes(page)) return;
  const enteringEnergy=page==="energia"&&state.page!=="energia";state.page = page; render(); if(enteringEnergy&&sessionInfo().authenticated)refreshGatewayReadings(); if(page==="casa" && workspace.house.restoreScroll){const y=Number(workspace.house.returnScrollY||0);workspace.house.restoreScroll=false;requestAnimationFrame(()=>window.scrollTo({top:y,behavior:"auto"}));}else window.scrollTo({top:0,behavior:"smooth"});
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
$('#page-content').addEventListener('dblclick',e=>{if(e.target.closest('button,a,input,select,textarea'))return;const card=e.target.closest('.favorite-device[data-device-kind="tuya"]');if(!card)return;const device=state.tuyaDevices.find(item=>item.device_id===card.dataset.favoriteDevice);if(device)openTuyaDeviceEditor(device);});
$('#page-content').addEventListener('click',async e=>{
  if(e.target.closest('#profile-open-gateway')){$('#gateway-dialog').showModal();return;}
  const toggle=e.target.closest('[data-favorite-toggle]');
  if(toggle){
    if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode controlar dispositivos.");return;}
    const deviceId=toggle.dataset.favoriteToggle,code=toggle.dataset.favoriteCode,device=state.tuyaDevices.find(item=>item.device_id===deviceId),reading=state.tuyaReadings.find(item=>item.device_id===deviceId),value=(reading?.status||[]).find(item=>item.code===code)?.value;
    if(typeof value!=="boolean"){showFeatureNotice("O estado atual do dispositivo não está disponível; atualiza a leitura antes de comandar.");return;}
    toggle.disabled=true;try{const result=await controlGatewayTuyaSwitch(deviceId,!value,code);if(!result.state_confirmed)showFeatureNotice("O comando LAN foi enviado, mas o Gateway ainda não confirmou o estado físico.");lastTuyaReadAt=0;await refreshGatewayReadings();}catch(error){showFeatureNotice(`Falha no controlo LAN: ${error.message}`);}finally{toggle.disabled=false;}return;
  }
  const remove=e.target.closest('[data-favorite-remove]');if(remove){workspace.prefs.favoriteDeviceIds=(workspace.prefs.favoriteDeviceIds||[]).filter(id=>id!==remove.dataset.favoriteRemove);saveDemoWorkspace();render();return;}
  if(e.target.closest('#home-favorite-plus')){if(!sessionInfo().authenticated){showFeatureNotice("Inicia sessão para gerir os teus favoritos.");return;}openFavoriteDialog();return;}
  const levelOpen=e.target.closest('[data-favorite-level-open]');if(levelOpen){if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode controlar dispositivos.");return;}const slider=$(`[data-favorite-level="${CSS.escape(levelOpen.dataset.favoriteLevelOpen)}"]`);if(slider){slider.hidden=false;slider.focus();}return;}
  if(e.target.closest('#home-existing-device')){$('#home-favorite-existing').hidden=false;$('#home-favorite-new').hidden=true;return;}
  if(e.target.closest('#home-new-device')){$('#home-favorite-new').hidden=false;$('#home-favorite-existing').hidden=true;return;}
  if(e.target.closest('#home-add-existing')){const id=$('#home-favorite-select').value;if(!id){$('#home-device-dialog-status').textContent="Escolhe um dispositivo.";return;}const details=favoriteMeta();details[id]={...(details[id]||{}),room:$('#home-favorite-room').value.trim(),floor:$('#home-favorite-floor').value.trim()};saveFavoriteMeta(details);workspace.prefs.favoriteDeviceIds=[...new Set([...(workspace.prefs.favoriteDeviceIds||[]),id])];saveDemoWorkspace();e.target.closest('dialog')?.close();render();return;}
  if(e.target.closest('#home-register-device')){
    if(sessionInfo().user?.role!=="owner"){showFeatureNotice("Só o Owner pode registar ou configurar dispositivos no Gateway.");return;}
    const status=$('#home-device-dialog-status'),id=$('#home-new-id').value.trim(),name=$('#home-new-name').value.trim(),kind=$('#home-new-kind').value,switchCode=$('#home-new-switch-code').value.trim(),levelCode=$('#home-new-level-code').value.trim();
    if(!id||!name||(!switchCode&&!levelCode)){status.textContent="Indica o ID, o nome e pelo menos um código de função Tuya.";return;}
    if((kind==="dimmer"||kind==="blind")&&!levelCode){status.textContent="Para dimmer ou estore, indica o código Tuya do nível/posição.";return;}
    const min=Number($('#home-new-level-min').value),max=Number($('#home-new-level-max').value);if(levelCode&&(!Number.isInteger(min)||!Number.isInteger(max)||min<0||max<=min)){status.textContent="O intervalo Tuya mínimo e máximo é inválido.";return;}
    status.textContent="A guardar a configuração no Gateway…";
    try{const config=await readGatewayHardwareIntegrationConfig();const devices=[...(config.tuya?.devices||[]).filter(item=>item.device_id!==id),{device_id:id,name,...(switchCode?{switch_code:switchCode}:{}),...(levelCode?{level_code:levelCode,level_min:min,level_max:max}:{})}];await saveGatewayHardwareIntegrationConfig({tuya:{region:config.tuya?.region||"eu_central",client_id:config.tuya?.client_id||undefined,devices}});const details=favoriteMeta();details[id]={label:name,kind,room:$('#home-new-room').value.trim(),floor:$('#home-new-floor').value.trim()};saveFavoriteMeta(details);workspace.prefs.favoriteDeviceIds=[...new Set([...(workspace.prefs.favoriteDeviceIds||[]),id])];saveDemoWorkspace();lastTuyaReadAt=0;e.target.closest('dialog')?.close();await refreshGatewayReadings();}catch(error){status.textContent=`Não foi possível guardar no Gateway: ${error.message}`;}return;
  }
});
const favoriteLevelTimers=new Map();
$('#page-content').addEventListener('input',e=>{const slider=e.target.closest('[data-favorite-level]');if(!slider)return;const id=slider.dataset.favoriteLevel;clearTimeout(favoriteLevelTimers.get(id));favoriteLevelTimers.set(id,setTimeout(async()=>{slider.hidden=true;if(sessionInfo().user?.role!=="owner")return;slider.disabled=true;const status=$(`[data-favorite-status="${CSS.escape(id)}"]`);if(status)status.textContent=`A enviar nível ${slider.value}%…`;try{const result=await controlGatewayTuyaLevel(id,Number(slider.value));if(status)status.textContent=`Comando ${result.command_accepted?"aceite":"não confirmado"}; estado físico aguarda nova leitura.`;lastTuyaReadAt=0;}catch(error){if(status)status.textContent=`Falha no comando: ${error.message}`;}finally{slider.disabled=false;await refreshGatewayReadings();}},1000));});

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
  if(e.target.id === "pv-string-form") { e.preventDefault(); savePvStringForm(e.target); return; }
  if(e.target.id === "aqs-form") { e.preventDefault(); saveAqsForm(e.target); return; }
  if(e.target.id === "auto-form") { e.preventDefault(); if(saveAutomationForm(e.target,workspace)){automationEditingId="";render();showFeatureNotice("Automatismo guardado na demonstração local. Nenhum comando foi enviado.");} return; }
  if(e.target.id === "demo-user-form") { e.preventDefault(); if(addDemoUser(e.target)){render();showFeatureNotice("Utilizador fictício adicionado. Não foi criada uma conta real.");} return; }
  const userEdit=e.target.closest('form[data-demo-user-edit]');if(userEdit){e.preventDefault();if(saveDemoUserEdit(userEdit,userEdit.dataset.demoUserEdit)){render();showFeatureNotice('Utilizador fictício atualizado localmente.');}return;}
});
async function savePvStringForm(form){
  const status=$("#pv-string-status"),button=form.querySelector('[type="submit"]');
  if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode alterar as strings.";return;}
  const name=form.elements.name.value.trim(),manufacturer=form.elements.manufacturer.value.trim(),panelCount=Number(form.elements.panel_count.value),panelPower=Number(form.elements.panel_power_w.value),mppt=Number(form.elements.mppt.value),nominal=panelCount*panelPower/1000,id=form.elements.id.value||`pv-string-${Date.now().toString(36)}`;
  if(!name||name.length>120||!manufacturer||manufacturer.length>120||![1,2].includes(mppt)||!Number.isInteger(panelCount)||panelCount<1||panelCount>2000||!Number.isFinite(panelPower)||panelPower<1||panelPower>2500||!Number.isFinite(nominal)||nominal>1000){status.textContent="Confirma o nome, fabricante, número de painéis, potência por painel e entrada MPPT.";return;}
  const strings=[...(state.energyEngine?.configuration?.pv_strings||[])],index=strings.findIndex(item=>item.id===id);
  if(form.closest("dialog").dataset.mode==="edit"&&index<0){status.textContent="A string já não consta na configuração. Atualiza e tenta novamente.";return;}
  const value={id,name,manufacturer,panel_count:panelCount,panel_power_w:panelPower,mppt,nominal_power_kw:nominal,active:form.elements.active.checked};if(index>=0)strings[index]=value;else strings.push(value);
  button.disabled=true;status.textContent="A guardar no Gateway…";
  try{
    const saved=await saveGatewayEnergyEngineConfig({pv_strings:strings});
    const savedStrings=Array.isArray(saved?.pv_strings)?saved.pv_strings:null;
    const persisted=savedStrings?.find(item=>item.id===id);
    if(!persisted||persisted.name!==name||persisted.mppt!==mppt||persisted.panel_count!==panelCount||Number(persisted.panel_power_w)!==panelPower){
      throw new Error("O Gateway não confirmou a gravação desta string. Mantive o formulário aberto.");
    }
    state.energyEngine={...(state.energyEngine||{}),configuration:saved};
    form.closest("dialog").close();render();
    const refreshed=await refreshGatewayReadings();
    if(!refreshed)showFeatureNotice("String guardada no Gateway. A leitura atual falhou; os dados guardados continuam visíveis.");
    else if(!(state.energyEngine?.configuration?.pv_strings||[]).some(item=>item.id===id))showFeatureNotice("O Gateway confirmou a gravação. A lista ainda não atualizou; volta a abrir Painéis para consultar.");
  }
  catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
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
  const previous=index>=0?loads[index]:{};const value={...previous,id,name,manufacturer,volume_l:volume,kind:"water_heater",control_type:deviceId?"tuya_breaker":"manual",rated_power_w:rated,minimum_power_w:0,maximum_power_w:rated,priority:previous.priority||10,enabled:previous.enabled!==false,automatic:previous.automatic===true,tuya_device_id:deviceId,tuya_switch_code:switchCode};
  if(index>=0)loads[index]=value;else loads.push(value);
  button.disabled=true;status.textContent="A guardar no Gateway…";
  try{await saveGatewayEnergyEngineConfig({loads});form.closest("dialog").close();await refreshGatewayReadings();}
  catch(error){status.textContent=`Não foi possível guardar: ${error.message}`;}
  finally{button.disabled=false;}
}
function showFeatureNotice(message){const n=$("#notice");n.hidden=false;n.textContent=message;setTimeout(()=>n.hidden=true,4500);}
$("#page-content").addEventListener("change", e => {
  if(e.target.matches('#pv-string-form [name="panel_count"], #pv-string-form [name="panel_power_w"]'))updatePvStringTotalPower(e.target.form);
  const fontPref=e.target.closest('[data-ws-field="prefs.font"]');if(fontPref){document.documentElement.dataset.font=fontPref.value;applyLiveFontScale();return;}
  const toggle=e.target.closest("[data-rule-toggle]"); if(toggle){const r=demoFeatures.automations.find(x=>x.id===toggle.dataset.ruleToggle);if(r){r.enabled=toggle.checked;localStorage.setItem('solar-miner-v053-demo-features-v1',JSON.stringify(demoFeatures));render();showFeatureNotice(r.enabled?'Automatismo ativado apenas na demonstração.':'Automatismo desativado.');}return;}
  if(e.target.id==='solar-weather'){saveSolarWeather(e.target.value);if($('#production-dialog')?.open)openProductionDialog();else render();}
  if(['conditionDevice','sourceType','targetDevice'].includes(e.target.name)){const form=e.target.closest('#auto-form');if(form){const ds=workspace.house.floors.flatMap(f=>f.rooms.flatMap(r=>r.devices));const device=ds.find(d=>d.id===form.elements.conditionDevice.value);const type=form.elements.sourceType.value;const opts=type==='device'?(device?.type==='blind'?[['open','Fica aberto'],['closed','Fica fechado']]:device?.type==='sensor'&&/temp/i.test(device?.name||'')?[['temperature','Temperatura acima/abaixo de limite']]:device?.type==='sensor'?[['motion','Deteta movimento'],['no-motion','Não deteta movimento']]:['light','socket'].includes(device?.type)?[['on','Fica ligado'],['off','Fica desligado']]:[['online','Estado online (se suportado)']]):type==='schedule'?[['time','Hora fixa'],['sunrise','Nascer do Sol'],['sunset','Pôr do Sol']]:type==='weather'?[['temperature','Temperatura exterior'],['rain','Chuva'],['cloud','Nebulosidade']]:[['arrive','Chegar a casa'],['leave','Sair de casa'],['nobody','Ninguém em casa']];if(e.target.name!=='targetDevice')form.elements.conditionType.innerHTML=opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');if(e.target.name==='targetDevice'){const target=ds.find(d=>d.id===form.elements.targetDevice.value);const t=(target?.type||'').toLowerCase(),n=(target?.name||'').toLowerCase();let actions=[['notify','Notificação local simulada']];if(t.includes('blind')||/estore/.test(n))actions=[['open','Abrir (simulado)'],['close','Fechar (simulado)'],...actions];else if(['light','socket','switch','plug'].some(x=>t.includes(x))||/luz|tomada/.test(n))actions=[['on','Ligar (simulado)'],['off','Desligar (simulado)'],...actions];form.elements.action.innerHTML=actions.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');}}}
});
$("#page-content").addEventListener("input", e => {
  if(e.target.matches('#pv-string-form [name="panel_count"], #pv-string-form [name="panel_power_w"]'))updatePvStringTotalPower(e.target.form);
});
$("#page-content").addEventListener("click", async e => {
  if(e.target.closest("#engine-chart-open")){await loadEngineHistoryDay(localDayKey());return;}
  if(e.target.closest("[data-engine-history-close]")){e.target.closest("#engine-history-dialog")?.close();return;}
  const historyStep=e.target.closest("[data-engine-history-day]");
  if(historyStep){const d=localDayBounds(state.engineHistoryChart.dateKey||localDayKey()).start;d.setDate(d.getDate()+Number(historyStep.dataset.engineHistoryDay));await loadEngineHistoryDay(localDayKey(d));return;}
  if(e.target.closest("#engine-refresh")){refreshGatewayReadings();return;}
  if(e.target.closest("#gateway-area-refresh")){refreshGatewayReadings();return;}
  if(e.target.closest("#pv-string-add")){openPvStringDialog();return;}
  if(e.target.closest("[data-pv-string-close]")){e.target.closest("#pv-string-dialog")?.close();return;}
  if(e.target.closest("#pv-string-remove")){
    const form=$("#pv-string-form"),status=$("#pv-string-status"),id=form.elements.id.value;if(!id||!window.confirm("Remover esta string da configuração do Gateway?"))return;
    if(!sessionInfo().authenticated||sessionInfo().user?.role!=="owner"){status.textContent="Só o Owner pode remover strings.";return;}
    const strings=(state.energyEngine?.configuration?.pv_strings||[]).filter(item=>item.id!==id),button=e.target.closest("#pv-string-remove");button.disabled=true;status.textContent="A remover a string…";
    try{await saveGatewayEnergyEngineConfig({pv_strings:strings});form.closest("dialog").close();await refreshGatewayReadings();}catch(error){status.textContent=`Não foi possível remover: ${error.message}`;}finally{button.disabled=false;}return;
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
  if(e.target.closest("#engine-add-load")){
    const status=$("#engine-equipment-config-status");
    try{
      const loads=JSON.parse($("#engine-loads-json").value||"[]");
      if(!Array.isArray(loads)||loads.length>=64)throw new Error("A lista tem de ser válida e pode conter até 64 cargas.");
      const kind=$("#engine-load-kind").value,control=$("#engine-load-control").value;
      const rated=Number($("#engine-load-rated").value),priority=Number($("#engine-load-priority").value);
      const name=$("#engine-load-name").value.trim();
      if(!name||!Number.isInteger(rated)||rated<1||!Number.isInteger(priority)||priority<1||priority>100)throw new Error("Indica nome, potência nominal e prioridade válidos.");
      const load={id:`load-${Date.now().toString(36)}`,name,kind,control_type:control,rated_power_w:rated,priority,enabled:true,automatic:$("#engine-load-automatic").checked};
      if(control==="tuya_smart"||control==="tuya_breaker"){
        const option=$("#engine-load-tuya-device").selectedOptions[0],device_id=option?.value,switch_code=option?.dataset.code;
        if(!device_id||!switch_code)throw new Error("Configura e seleciona um interruptor Tuya registado no Gateway.");
        load.tuya_device_id=device_id;load.tuya_switch_code=switch_code;
      }
      if(control==="antminer_braiins"){
        const minimum=Number($("#engine-load-minimum").value),maximum=Number($("#engine-load-maximum").value);
        if(!Number.isInteger(minimum)||!Number.isInteger(maximum)||minimum<1||maximum>2900||minimum>maximum)throw new Error("Define mínimo e máximo da mineradora entre 1 e 2900 W.");
        load.minimum_power_w=minimum;load.maximum_power_w=maximum;
        if(load.automatic){const dependency=$("#engine-load-miner-relay").value;if(!dependency)throw new Error("Escolhe primeiro um relé Tuya automático para alimentar a mineradora.");load.requires_load_id=dependency;}
      }
      $("#engine-loads-json").value=JSON.stringify([...loads,load],null,2);
      $("#engine-load-name").value="";
      status.textContent=`${name} adicionada à lista. Guarda a configuração no Gateway.`;
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
    finally{const current=$("#engine-save-equipment-config");if(current)current.disabled=false;}
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
$("#mode-chip").addEventListener("click",()=>$("#gateway-dialog").showModal());
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
    if (tab.dataset.ownerTab === "gateway") refreshGatewayConsole();
  }
});
document.querySelector(".owner-device-tabs")?.addEventListener("click", event => {
  const tab = event.target.closest("[data-owner-device]");
  if (tab) selectOwnerDevice(tab.dataset.ownerDevice);
});
$("#owner-open-gateway")?.addEventListener("click", () => $("#gateway-dialog").showModal());
$("#owner-gateway-status").textContent = "Configura e autentica a ligação pelo botão acima.";
$("#owner-nav-item").addEventListener("click", () => selectOwnerTab(activeOwnerTab));
let gatewayConsoleRefreshInFlight = false;
let gatewayConsoleServices = {};
const gatewayConsoleServiceLabels = {
  gateway: "SolarMiner Gateway", nginx: "Nginx", tailscale: "Tailscale",
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
}
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
        const diagnostic = await readGatewayTerminalDiagnostics();
        if (!diagnostic.available) {
          detail = !diagnostic.pty_available
            ? "A API do Gateway respondeu, mas este sistema não disponibiliza o terminal PTY."
            : "A API do Gateway respondeu, mas a shell do terminal não está instalada.";
        } else {
          detail = "A API do Gateway responde e o terminal está disponível, mas a ligação WebSocket falhou. O bloqueio está no encaminhamento HTTPS/Tailscale ou na configuração do proxy; esta verificação não executou comandos.";
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
      if (info.user.role === "owner") refreshHardwareIntegrationConfig().catch(error => {
        $("#deye-status").textContent = `Não foi possível carregar a configuração: ${error.message}`;
      });
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
async function refreshHardwareIntegrationConfig() {
  const config = await readGatewayHardwareIntegrationConfig();
  const deye = config.deye || {}, miner = config.antminer || {}, tuya = config.tuya || {};
  const deyeCloud=config.deye_cloud||{};
  state.tuyaDevices=tuya.devices||[];
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
  $("#hardware-antminer-username").value = "";
  $("#hardware-antminer-password").value = "";
  $("#hardware-tuya-region").value = tuya.region || "eu_central";
  $("#hardware-tuya-client-id").value = tuya.client_id || "";
  $("#hardware-tuya-uid").value = tuya.uid || "";
  $("#hardware-tuya-client-secret").value = "";
  $("#huawei-router-host").value = config.huawei_router?.host || "192.168.8.1";
  $("#huawei-router-password").value = "";
  $("#hardware-tuya-devices").value = (tuya.devices || []).map(device => `${device.device_id} | ${device.name}${device.switch_code ? ` | ${device.switch_code}` : ""}${device.level_code ? ` | ${device.level_code} | ${device.level_min ?? 0} | ${device.level_max ?? 100}` : ""}`).join("\n");
  $("#deye-status").textContent = deye.host ? `Deye configurado em ${deye.host}:${deye.port || 502}, Unit ID ${deye.unit_id ?? 1}.` : "Deye ainda não configurado.";
  $("#antminer-status").textContent = miner.host ? `Antminer configurada em ${miner.host}:${miner.port || 4028}. Credenciais de controlo ${config.antminer_control_configured ? "guardadas no Gateway" : "por configurar"}.` : "Antminer ainda não configurada.";
  const importedCount = (tuya.devices || []).filter(device => device.cloud_source === "TUYA_PROJECT" || device.local_key_available).length;
  $("#tuya-status").textContent = tuya.configured ? `Conta Tuya configurada; segredo oculto no Gateway. ${importedCount} dispositivo(s) sincronizado(s).` : "Conta Tuya ainda não configurada.";
  $("#huawei-router-status").textContent = config.huawei_router?.configured
    ? `Huawei configurado em ${config.huawei_router.host}; palavra-passe guardada apenas no Gateway.`
    : "Indica o IP e as credenciais locais do Huawei para tentar ler a lista de clientes.";
  $("#deye-cloud-status").textContent=deyeCloud.configured?"Acesso Deye Cloud guardado no Gateway. Os segredos não são devolvidos à PWA.":"Configura a aplicação de developer Deye e a conta para importar o histórico.";
  renderTuyaDeviceCards(tuya.devices || []);
  return config;
}
function tuyaDeviceGlyph(device) {
  const identity = `${device.category || ""} ${device.product_name || ""}`.toLowerCase();
  if (/breaker|circuit|disjuntor|circuito/.test(identity)) return "▤";
  if (/switch|relay|interruptor|rele/.test(identity) || (device.functions || []).filter(item => ["bool", "boolean"].includes(String(item.type || "").toLowerCase())).length > 1) return "⏻";
  if (/sensor|temperature|humidity|motion/.test(identity)) return "◉";
  return "⌁";
}
function tuyaFriendlyCapabilityLabel(item, device){
  const code=String(item.code||""),custom=device.capability_labels?.[code]||device.channel_labels?.[code];
  if(custom)return custom;
  const known={switch:"Interruptor",switch_led:"Luz",cur_power:"Potência atual",cur_voltage:"Tensão atual",cur_current:"Corrente atual",add_ele:"Energia acumulada",temp_current:"Temperatura",humidity_value:"Humidade",doorcontact_state:"Estado da porta",va_temperature:"Temperatura",bright_value:"Brilho",brightness:"Brilho",colour_data:"Cor",work_state:"Modo de funcionamento",relay_status:"Estado do relé"};
  if(known[code])return known[code];
  const channel=code.match(/^switch_(\d+)$/);if(channel)return `Canal ${channel[1]}`;
  if(/[\u3400-\u9fff]/.test(String(item.name||"")))return `Função Tuya · ${code||"sem código"}`;
  return item.name||code||"Função sem nome";
}
function setupTuyaEditorTabs(dialog){
  const form=dialog.querySelector("#tuya-device-edit-form"),children=[...form.children],first=children.findIndex(node=>node.tagName==="H3"),status=children.find(node=>node.id==="tuya-device-edit-status");
  if(first<0||!status)return;
  const end=children.indexOf(status),groups=[{title:"Geral",nodes:children.slice(0,first)}];let current=null;
  for(const node of children.slice(first,end)){if(node.tagName==="H3"){current={title:node.textContent.trim(),nodes:[node]};groups.push(current);}else if(current)current.nodes.push(node);}
  const tabs=document.createElement("nav");tabs.className="tuya-editor-tabs";tabs.setAttribute("aria-label","Secções do dispositivo");const panels=document.createElement("div");panels.className="tuya-editor-panels";
  groups.forEach((group,index)=>{const id=`tuya-editor-tab-${index}`,button=document.createElement("button"),panel=document.createElement("section");button.type="button";button.className="tuya-editor-tab";button.textContent=group.title;button.setAttribute("aria-controls",id);button.setAttribute("aria-selected",String(index===0));panel.id=id;panel.className="tuya-editor-panel";panel.hidden=index!==0;group.nodes.forEach(node=>panel.append(node));tabs.append(button);panels.append(panel);button.addEventListener("click",()=>{tabs.querySelectorAll("button").forEach((tab,i)=>tab.setAttribute("aria-selected",String(i===index)));panels.querySelectorAll("section").forEach((section,i)=>section.hidden=i!==index);});});
  form.insertBefore(tabs,form.children[first]);form.insertBefore(panels,status);
}
function renderTuyaDeviceCards(devices) {
  const list = $("#tuya-device-list");
  if (!list) return;
  list.innerHTML = devices.length ? devices.map(device => {const functions=Array.isArray(device.functions)?device.functions:[];const statuses=Array.isArray(device.status_spec)?device.status_spec:[];const schema=[...functions.map(item=>`ordem ${item.code} (${item.type})`),...statuses.map(item=>`leitura ${item.code} (${item.type})`)].slice(0,12).join(" · ");return `<article class="tuya-device-card" data-tuya-device="${esc(device.device_id)}"><h4><span class="tuya-device-glyph" aria-hidden="true">${tuyaDeviceGlyph(device)}</span> ${esc(device.name)}</h4><p class="field-note">${esc(device.device_id)}${device.category?` · ${esc(device.category)}`:""}${device.online===true?" · online":device.online===false?" · offline":""}${device.local_key_available?" · chave local guardada no Gateway":" · chave local indisponível"}</p>${device.product_name?`<p class="field-note">${esc(device.product_name)}</p>`:""}${schema?`<p class="field-note">${esc(schema)}</p>`:""}<div class="dialog-actions"><button type="button" class="button secondary" data-edit-tuya-device="${esc(device.device_id)}">Características e editar</button><button type="button" class="button secondary" data-tuya-read="${esc(device.device_id)}">Ler este dispositivo</button>${device.switch_code ? `<button type="button" class="button secondary" data-tuya-switch="on" data-device-id="${esc(device.device_id)}">Ligar</button><button type="button" class="button secondary" data-tuya-switch="off" data-device-id="${esc(device.device_id)}">Desligar</button>` : ""}</div><div class="connection-result" data-tuya-status="${esc(device.device_id)}" role="status" aria-live="polite">Sem leitura recente.</div><pre class="integration-result" data-tuya-result="${esc(device.device_id)}" hidden></pre></article>`;}).join("") : `<p class="field-note">Ainda não há dispositivos Tuya configurados.</p>`;
}
function openTuyaDeviceEditor(device){
  if(sessionInfo().user?.role!=="owner")return;
  const channels=(device.functions||[]).filter(item=>["bool","boolean"].includes(String(item.type||"").toLowerCase()));
  const allFunctions=Array.isArray(device.functions)?device.functions:[],statuses=Array.isArray(device.status_spec)?device.status_spec:[];
  const glyph=tuyaDeviceGlyph(device);
  const localLabel= item=>tuyaFriendlyCapabilityLabel(item,device);
  const defaultDps=code=>/^switch_(\d+)$/.test(code)?code.match(/^switch_(\d+)$/)[1]:code==="switch"?"1":"";
  const channelRows=channels.map((item,index)=>`<label class="tuya-channel-edit"><span><strong>${esc(localLabel(item)||`Canal ${index+1}`)}</strong><small>${esc(item.code)} · ${esc(item.type||"interruptor")}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item)||`Canal ${index+1}`)}" aria-label="Nome do canal ${esc(index+1)}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(device.local_dps_map?.[item.code]||defaultDps(item.code))}" aria-label="DPS local do canal ${esc(index+1)}" placeholder="DPS"></label>`).join("");
  const capabilityRows=allFunctions.filter(item=>!channels.includes(item)).map(item=>`<label class="tuya-capability-row"><span><strong>${esc(item.name||item.code||"Função")}</strong><small>${esc(item.code||"")} · ${esc(item.type||"tipo desconhecido")} · ${esc(typeof item.values==="string"?item.values:JSON.stringify(item.values??{}))}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item))}" aria-label="Nome local da característica ${esc(item.name||item.code||"")}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(device.local_dps_map?.[item.code]||"")}" aria-label="DPS local de ${esc(item.name||item.code||"")}" placeholder="DPS"></label>`).join("");
  const statusRows=statuses.map(item=>`<label class="tuya-capability-row"><span><strong>${esc(item.name||item.code||"Leitura")}</strong><small>${esc(item.code||"")} · ${esc(item.type||"tipo desconhecido")}</small></span><input type="text" maxlength="80" data-tuya-capability-label="${esc(item.code)}" value="${esc(localLabel(item))}" aria-label="Nome local da leitura ${esc(item.name||item.code||"")}"><input type="number" min="1" max="65535" data-tuya-dps="${esc(item.code)}" value="${esc(device.local_dps_map?.[item.code]||"")}" aria-label="DPS local da leitura ${esc(item.name||item.code||"")}" placeholder="DPS"></label>`).join("");
  const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-device-editor";
  dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">${glyph} · ${esc(device.category||device.product_name||"TUYA / MOES")}</p><h2>${esc(device.name)}</h2></div><button class="icon-button" value="cancel" aria-label="Fechar">×</button></form><form class="dialog-body" id="tuya-device-edit-form"><p class="field-note">Os nomes, o endereço, o MAC, o protocolo e o mapa DPS ficam guardados no Gateway. A descoberta tenta cruzar o ID Tuya ou o MAC com a rede local. Se não encontrar o endereço, podes indicar o IP privado manualmente. A cloud só é usada quando pedes sincronização do inventário.</p><div class="device-detail-grid"><div class="detail-item"><small>Tipo / categoria</small><strong>${esc(device.category||"Não identificado")}</strong></div><div class="detail-item"><small>Canais digitais</small><strong>${channels.length}</strong></div><div class="detail-item"><small>Ligação LAN</small><strong>${esc(device.local_control_state||"Por verificar")}</strong></div><div class="detail-item"><small>Chave local</small><strong>${device.local_key_available?"Disponível no Gateway":"Não disponível"}</strong></div></div><label>Nome do dispositivo<input name="name" maxlength="120" required value="${esc(device.name)}"></label><div class="ws-config-grid"><label>Piso<input name="floor" maxlength="120" value="${esc(device.floor||"")}" placeholder="Ex.: Rés-do-chão"></label><label>Divisão<input name="room" maxlength="120" value="${esc(device.room||"")}" placeholder="Ex.: Luzes canteiros frente"></label></div><div class="ws-config-grid"><label>MAC local<input name="local_mac" maxlength="17" value="${esc(device.local_mac||"")}" placeholder="AA:BB:CC:11:22:33" autocapitalize="characters" spellcheck="false"></label><label>IP local<input name="local_ip" maxlength="64" value="${esc(device.local_ip||"")}" placeholder="192.168.1.20" inputmode="decimal"></label></div><label>Protocolo Tuya LAN<select name="local_protocol">${["3.1","3.2","3.3","3.4","3.5"].map(value=>`<option value="${value}" ${(device.local_protocol||"3.3")===value?"selected":""}>${value}</option>`).join("")}</select></label><h3>Canais disponíveis</h3>${channels.length?`<p class="field-note">Define o nome e o número DPS de cada saída. Para switch_1, switch_2, etc., o Gateway sugere o número convencional; confirma com o esquema do teu aparelho.</p><div class="tuya-channel-list">${channelRows}</div>`:`<p class="field-note">A Tuya não indicou canais digitais para este equipamento.</p>`}<h3>Outras funções recebidas</h3><div class="tuya-capability-list">${capabilityRows||`<p class="field-note">Sem outras funções no esquema recebido.</p>`}</div><h3>Leituras recebidas</h3><div class="tuya-capability-list">${statusRows||`<p class="field-note">Sem leituras no esquema recebido.</p>`}</div><h3>Registo do dispositivo</h3><p class="field-note">Mostra alterações ON/OFF, disponibilidade na LAN, comandos e ações automáticas. O registo começa quando esta versão faz as primeiras leituras; a hora depende do intervalo de leitura. Ainda não há alarmes de limite de watts configuráveis neste ecrã.</p><button type="button" class="button secondary" data-tuya-events="${esc(device.device_id)}">Abrir registo</button><div class="tuya-event-list" data-tuya-event-list="${esc(device.device_id)}" aria-live="polite">Carrega em “Abrir registo” para consultar os eventos guardados.</div><p class="connection-result" id="tuya-device-edit-status" role="status" aria-live="polite"></p><div class="dialog-actions"><button type="button" class="button secondary" data-tuya-editor-cancel>Cancelar</button><button type="submit" class="button primary">Guardar no Gateway</button></div></form>`;
  setupTuyaEditorTabs(dialog);
  const favoriteIds=workspace.prefs.favoriteDeviceIds||[],isFavorite=favoriteIds.includes(device.device_id),favoriteButton=document.createElement("button");
  favoriteButton.type="button";favoriteButton.className="button secondary tuya-favorite-action";favoriteButton.textContent=isFavorite?"Remover dos favoritos":"Adicionar aos favoritos";
  favoriteButton.addEventListener("click",()=>{workspace.prefs.favoriteDeviceIds=isFavorite?favoriteIds.filter(id=>id!==device.device_id):[...new Set([...favoriteIds,device.device_id])];saveDemoWorkspace();dialog.close("favorite-updated");render();});
  dialog.querySelector(".dialog-actions").prepend(favoriteButton);
  document.body.append(dialog);dialog.addEventListener("close",()=>dialog.remove());dialog.querySelector("[data-tuya-editor-cancel]").addEventListener("click",()=>dialog.close("cancel"));
  dialog.querySelector("#tuya-device-edit-form").addEventListener("submit",async event=>{event.preventDefault();const form=event.currentTarget,save=form.querySelector('[type="submit"]'),status=form.querySelector("#tuya-device-edit-status");save.disabled=true;status.textContent="A guardar alterações locais no Gateway…";try{const config=await readGatewayHardwareIntegrationConfig(),labels={},dpsMap={};for(const input of form.querySelectorAll("[data-tuya-capability-label]"))labels[input.dataset.tuyaCapabilityLabel]=input.value.trim();for(const input of form.querySelectorAll("[data-tuya-dps]"))if(input.value.trim())dpsMap[input.dataset.tuyaDps]=input.value.trim();const next=(config.tuya?.devices||[]).map(item=>item.device_id===device.device_id?{...item,name:form.elements.name.value.trim(),name_source:"local",room:form.elements.room.value.trim(),floor:form.elements.floor.value.trim(),local_ip:form.elements.local_ip.value.trim(),local_mac:form.elements.local_mac.value.trim().toUpperCase(),local_protocol:form.elements.local_protocol.value,local_dps_map:dpsMap,channel_labels:Object.fromEntries(channels.map(channel=>[channel.code,labels[channel.code]||""])),capability_labels:labels}:item);if(!next.some(item=>item.device_id===device.device_id))throw new Error("O dispositivo deixou de constar na configuração do Gateway.");const saved=await saveGatewayHardwareIntegrationConfig({tuya:{devices:next}}),persisted=(saved.tuya?.devices||[]).find(item=>item.device_id===device.device_id),requestedIp=form.elements.local_ip.value.trim();if(!persisted||String(persisted.local_ip||"").trim()!==requestedIp)throw new Error("O Gateway não confirmou o IP local deste dispositivo. As alterações não foram fechadas; atualiza a lista e tenta novamente.");await refreshHardwareIntegrationConfig();const confirmed=state.tuyaDevices.find(item=>item.device_id===device.device_id);if(!confirmed||String(confirmed.local_ip||"").trim()!==requestedIp)throw new Error("O IP guardado não apareceu na lista atualizada do Gateway. Reabre o dispositivo antes de medir a LAN.");dialog.close("saved");render();}catch(error){status.textContent=`Não foi possível guardar no Gateway: ${error.message}`;save.disabled=false;}});
  dialog.showModal();
}
function setProviderResult(provider, result) {
  const payload = result[provider];
  const output = $(`#${provider}-result`), status = $(`#${provider}-status`);
  if (output) { output.textContent = JSON.stringify(payload ?? result, null, 2); output.hidden = false; }
  if (status) {
    const stateText = payload?.connection_state || (provider === "tuya" && payload?.length ? "api_responded" : "failed");
    const reason = payload?.reason ? ` · ${payload.reason}` : "";
    const metricText = provider === "deye" && payload?.metrics ? ` · ${payload.metrics.length} leituras recebidas; não validadas pelo fabricante` : "";
    const minerText = provider === "antminer" && payload?.responses ? " · API respondeu; comandos não enviados" : "";
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
  saveHardwareProvider("antminer", { enabled: Boolean(host), host, port: Number($("#hardware-antminer-port").value), rest_port: Number($("#hardware-antminer-rest-port").value), username: $("#hardware-antminer-username").value.trim(), password: $("#hardware-antminer-password").value, model: "S19K Pro" }, event.currentTarget, "antminer-status");
});
$("#tuya-save").addEventListener("click", event => {
  const devices = parseTuyaDevices();
  saveHardwareProvider("tuya", { region: $("#hardware-tuya-region").value, client_id: $("#hardware-tuya-client-id").value.trim() || undefined, client_secret: $("#hardware-tuya-client-secret").value || undefined, uid: $("#hardware-tuya-uid").value.trim() || undefined, devices }, event.currentTarget, "tuya-status");
});
$("#huawei-router-save").addEventListener("click", async event => {
  const button=event.currentTarget,status=$("#huawei-router-status");
  if(!ownerCanManageHardware("#tuya-status"))return;
  button.disabled=true;
  try{
    const host=$("#huawei-router-host").value.trim(),username="admin",password=$("#huawei-router-password").value;
    const saved=await saveGatewayHardwareIntegrationConfig({huawei_router:{host,username,...(password?{password}:{})}});
    $("#huawei-router-password").value="";
    status.textContent=saved.huawei_router?.configured?`Acesso local guardado no Gateway para ${saved.huawei_router.host}.`:`Endereço guardado; introduz a palavra-passe antes de consultar.`;
  }catch(error){status.textContent=`Não foi possível guardar o acesso local: ${error.message}`;}
  finally{button.disabled=false;}
});
$("#huawei-router-read").addEventListener("click", async event => {
  const button=event.currentTarget,status=$("#huawei-router-status");
  if(!ownerCanManageHardware("#tuya-status"))return;
  button.disabled=true;
  const finished=showOperationDialog({title:"Consulta local do Huawei",message:"A ler a lista de clientes do router. Esta operação é apenas de leitura; não altera o Huawei nem envia comandos aos Tuya.",locked:true,progress:true});
  try{
    const host=$("#huawei-router-host").value.trim(),username=$("#huawei-router-username").value.trim(),password=$("#huawei-router-password").value;
    const saved=await saveGatewayHardwareIntegrationConfig({huawei_router:{host,username,...(password?{password}:{})}});
    $("#huawei-router-password").value="";
    if(!saved.huawei_router?.configured)throw new Error("Introduz a palavra-passe do router e guarda o acesso local.");
    const report=await readGatewayHuaweiClients();
    await refreshHardwareIntegrationConfig();
    updateOperationDialog({title:"Consulta Huawei concluída",message:`Foram lidos ${report.client_count} clientes; ${report.matched_count} MAC/IP foram associados aos Tuya configurados.`,actions:[{label:"Ver lista",value:"report",primary:true}]});
    await finished;
    const rows=(report.clients||[]).map(item=>`<tr><td>${esc(item.name||"Sem nome")}</td><td>${esc(item.mac)}</td><td>${esc(item.ip)}</td></tr>`).join("");
    const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-diagnostic-dialog";
    dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">HUAWEI · CONSULTA LOCAL</p><h2>MACs e IPs encontrados</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></form><div class="dialog-body"><p class="field-note">O router devolveu ${esc(report.client_count)} cliente(s); ${esc(report.matched_count)} dispositivo(s) Tuya foram associados com os MACs/IPs já configurados. Os restantes podem ser associados manualmente ao editar cada dispositivo.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Nome no router</th><th>MAC</th><th>IP privado</th></tr></thead><tbody>${rows||'<tr><td colspan="3">O Huawei não devolveu clientes ligados.</td></tr>'}</tbody></table></div><div class="dialog-actions"><button class="button primary" type="button" data-huawei-close>OK</button></div></div>`;
    dialog.addEventListener("close",()=>dialog.remove());document.body.append(dialog);dialog.querySelector("[data-huawei-close]").addEventListener("click",()=>dialog.close("ok"));dialog.showModal();
    status.textContent=`Consulta concluída: ${report.client_count} cliente(s), ${report.matched_count} associação(ões) Tuya. Os valores continuam editáveis em cada dispositivo.`;
  }catch(error){
    updateOperationDialog({title:"Consulta Huawei falhou",message:error.message||"O Gateway não conseguiu ler os clientes do router.",actions:[{label:"OK",value:"ok",primary:true}]});
    await finished;status.textContent=`Consulta Huawei falhou: ${error.message||"verifica o IP, a ligação e as credenciais"}`;
  }finally{button.disabled=false;}
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
    await refreshHardwareIntegrationConfig();
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
    const rows=(report.devices||[]).map(item=>{const ip=String(item.local_ip||"").trim(),duplicate=ip&&ipCounts.get(ip)>1;return `<tr><th scope="row">${esc(item.name)}<small class="diagnostic-device-id">ID Tuya: ${esc(item.device_id)}</small></th><td>${ip?`${esc(ip)}${duplicate?" · partilhado":""}`:"Não configurado"}</td><td>${item.local_key_configured?"Configurada":"Em falta"}</td><td>${item.success_count}/${item.rounds}</td><td>${item.average_latency_ms==null?"—":`${esc(item.average_latency_ms)} ms`}</td><td>${item.worst_latency_ms==null?"—":`${esc(item.worst_latency_ms)} ms`}</td><td>${item.power_telemetry_configured?"Declarada":"Não identificada"}</td><td>${item.reason?esc(tuyaLanReasonText(item.reason)):"—"}</td></tr>`;}).join("");
    const sweeps=report.sweep_times_ms||[];
    const worstSweep=sweeps.length?Math.max(...sweeps):null;
    const dialog=document.createElement("dialog");dialog.className="settings-dialog tuya-diagnostic-dialog";
    dialog.innerHTML=`<form method="dialog" class="dialog-header"><div><p class="eyebrow">DIAGNÓSTICO LAN · SÓ LEITURA</p><h2>Resposta dos dispositivos</h2></div><button class="icon-button" value="close" aria-label="Fechar">×</button></form><div class="dialog-body"><p class="field-note">Foram medidas ${esc(report.rounds)} rondas em ${esc(report.configured_count)} dispositivos configurados; ${esc(report.lan_testable_count)} têm um IP privado e chave local válidos para consulta. O ID, IP efetivamente guardado e presença da chave aparecem por dispositivo para detetar configurações cruzadas.</p><p class="diagnostic-cycle-summary">Duração das rondas: ${sweeps.map(value=>`${esc(value)} ms`).join(" · ")||"sem leituras"}. Pior ciclo: ${worstSweep==null?"—":`${esc(worstSweep)} ms`}. Tempo total: ${esc(report.elapsed_ms)} ms. Só as respostas válidas entram nos tempos médio e pior.</p><p class="field-note">“Potência declarada” indica apenas que o esquema Tuya contém uma função/leitura com nome relacionado com potência. Não confirma que a leitura esteja calibrada nem que seja atual. “IP partilhado” assinala que vários IDs têm o mesmo host guardado; confirma se são dispositivos independentes ou subdispositivos de um hub.</p><div class="diagnostic-table-wrap"><table class="diagnostic-table"><thead><tr><th>Dispositivo / ID</th><th>IP guardado</th><th>Chave local</th><th>Respostas</th><th>Média</th><th>Pior</th><th>Potência</th><th>Diagnóstico</th></tr></thead><tbody>${rows||'<tr><td colspan="8">Não há dispositivos configurados.</td></tr>'}</tbody></table></div><p class="field-note">Este resultado mede consultas de leitura no estado atual da rede. Não garante um ciclo de um segundo nem tempo de corte; isso exigiria um ensaio prolongado dos dispositivos com potência e regras ativas.</p><div class="dialog-actions"><button class="button primary" type="button" data-diagnostic-close>OK</button></div></div>`;
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
  if (!ownerCanManageHardware(statusSelector)) return;
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
  } catch (error) { status.textContent = `Leitura falhou: ${error.message}`; }
}
function tuyaLanReasonText(reason){
  const messages={private_lan_target_required:"IP local não configurado ou inválido. Abre o dispositivo, edita o IP local e guarda.",tuya_local_key_missing:"A chave local não está disponível no Gateway.",tuya_lan_driver_unavailable:"O controlador LAN não está disponível nesta instalação.",tuya_local_datapoint_mapping_required:"Falta mapear o canal do equipamento para o respetivo DPS local.",tuya_lan_status_unavailable:"O equipamento não devolveu leituras LAN válidas.",tuya_connection_failed:"O Gateway não conseguiu obter resposta do equipamento pela rede local.",tuya_lan_read_unavailable:"Não foi possível obter uma resposta LAN deste equipamento."};
  return messages[reason]||String(reason).replaceAll("_"," ");
}
$("#deye-read").addEventListener("click", () => readHardwareProvider("deye"));
$("#antminer-read").addEventListener("click", () => readHardwareProvider("antminer"));
$("#tuya-device-list").addEventListener("click", async event => {
  const edit = event.target.closest("[data-edit-tuya-device]"), read = event.target.closest("[data-tuya-read]"), toggle = event.target.closest("[data-tuya-switch]");
  if (edit) { const device=state.tuyaDevices.find(item=>item.device_id===edit.dataset.editTuyaDevice); if(device)openTuyaDeviceEditor(device); return; }
  if (read) {
    const id = read.dataset.tuyaRead;
    read.disabled = true;
    await readHardwareProvider("tuya", id, `[data-tuya-status="${CSS.escape(id)}"]`, `[data-tuya-result="${CSS.escape(id)}"]`);
    read.disabled = false;
  } else if (toggle) await sendTuyaSwitch(toggle.dataset.deviceId, toggle.dataset.tuyaSwitch === "on", toggle);
});
async function sendAntminerControl(action) {
  const status = $("#antminer-status");
  if (!ownerCanManageHardware("#antminer-status")) return;
  const labels = { set_power_target: "alterar o alvo de potência", pause: "pausar a mineração", stop: "parar a mineração", start: "iniciar a mineração" };
  const watt = Number($("#hardware-antminer-watt").value);
  if (action === "set_power_target" && (!Number.isInteger(watt) || watt < 1 || watt > 2900)) { status.textContent = "Indica um alvo entre 1 e 2900 W."; return; }
  const prompt = action === "set_power_target" ? `Enviar ao Antminer a ordem para definir o alvo de potência em ${watt} W?` : `Confirmas que queres ${labels[action]} no Antminer?`;
  if (!confirm(prompt)) return;
  const buttons = ["antminer-power-target", "antminer-pause", "antminer-stop", "antminer-start"].map(id => $("#" + id));
  buttons.forEach(button => { button.disabled = true; });
  status.textContent = `A enviar o comando “${labels[action]}” ao Antminer…`;
  try {
    const result = await controlGatewayAntminer(action, watt);
    status.textContent = action === "set_power_target" ? `Comando aceite pelo Braiins OS: alvo aplicado ${result.applied_watt} W.` : `Comando “${labels[action]}” aceite pelo Braiins OS.`;
  } catch (error) { status.textContent = `O Gateway não conseguiu executar o comando: ${error.message}`; }
  finally { buttons.forEach(button => { button.disabled = false; }); }
}
$("#antminer-power-target").addEventListener("click", () => sendAntminerControl("set_power_target"));
$("#antminer-pause").addEventListener("click", () => sendAntminerControl("pause"));
$("#antminer-stop").addEventListener("click", () => sendAntminerControl("stop"));
$("#antminer-start").addEventListener("click", () => sendAntminerControl("start"));
async function sendTuyaSwitch(deviceId, on, button) {
  if (!ownerCanManageHardware("#tuya-status")) return;
  const card = button.closest(".tuya-device-card"), name = card.querySelector("h4")?.textContent || deviceId;
  if (!window.confirm(`Confirmas que queres ${on ? "ligar" : "desligar"} ${name}?`)) return;
  const buttons = [...card.querySelectorAll("button[data-tuya-switch]")]; buttons.forEach(item => { item.disabled = true; });
  const status = card.querySelector("[data-tuya-status]"); status.textContent = `A enviar comando para ${name}…`;
  try {
    const result = await controlGatewayTuyaSwitch(deviceId, on);
    status.textContent = result.state_confirmed ? `Estado confirmado: ${name} está ${on ? "ligado" : "desligado"}.` : `Comando aceite para ${name}, mas o estado físico não foi confirmado.`;
  } catch (error) { status.textContent = `Falha no comando Tuya: ${error.message}`; }
  finally { buttons.forEach(item => { item.disabled = false; }); }
}

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
  const tuyaCard=event.target.closest("[data-edit-tuya-device]");
  if(tuyaCard){const device=state.tuyaDevices.find(item=>item.device_id===tuyaCard.dataset.editTuyaDevice);if(device)openTuyaDeviceEditor(device);return;}
  const tuyaEvents=event.target.closest("[data-tuya-events]");
  if(tuyaEvents){const id=tuyaEvents.dataset.tuyaEvents,list=$(`[data-tuya-event-list="${CSS.escape(id)}"]`);tuyaEvents.disabled=true;if(list)list.textContent="A carregar registo local do Gateway…";try{const result=await readGatewayTuyaDeviceEvents(id);const events=result.events||[];const on=value=>value===true?"ON":value===false?"OFF":value===null?"—":String(value);list.innerHTML=events.length?events.map(item=>{const when=new Date(item.occurred_at).toLocaleString("pt-PT",{dateStyle:"short",timeStyle:"short"});const text=item.event_type==="availability"?(item.new_value?"Dispositivo disponível na LAN":"Dispositivo indisponível na LAN"):item.event_type==="switch_state"?`${item.channel_code}: ${on(item.old_value)} → ${on(item.new_value)}`:item.event_type==="automation_action"?`Ação automática · ${item.channel_code} ${on(item.new_value)}`:item.event_type==="command_confirmed"?`Comando LAN confirmado · ${item.channel_code} ${on(item.new_value)}`:`Comando LAN enviado, sem confirmação · ${item.channel_code} ${on(item.new_value)}`;return `<div class="tuya-event-row"><time>${esc(when)}</time><strong>${esc(text)}</strong></div>`;}).join(""):`<p class="field-note">Ainda não há eventos registados. O Gateway começa a registar alterações depois das leituras locais.</p>`;}catch(error){if(list)list.textContent=`Não foi possível abrir o registo: ${error.message}`;}finally{tuyaEvents.disabled=false;}return;}
  const chartPoint=event.target.closest(".solar-chart-hit");
  if(chartPoint){
    const tooltip=chartPoint.closest(".solar-chart-wrap")?.querySelector(".solar-chart-tooltip");
    if(tooltip){const hour=Number(chartPoint.dataset.hour),when=new Date(hour).toLocaleTimeString("pt-PT",{hour:"2-digit",minute:"2-digit"}),isFuture=chartPoint.dataset.future==="true",kind=isFuture?"previsto":"medido",fmt=value=>value===""?"—":`${Number(value).toLocaleString("pt-PT",{maximumFractionDigits:2})} kW`;tooltip.innerHTML=`<strong>${esc(when)} · ${kind}</strong><span>Consumo: ${fmt(chartPoint.dataset.load)}</span><span>${isFuture?"Produção prevista":"Produção efetiva"}: ${fmt(chartPoint.dataset.pv)}</span><span>Produção potencial: ${fmt(chartPoint.dataset.potential)}</span>`;tooltip.hidden=false;}
    return;
  }
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
        const choice=automatic?await showOperationDialog(prompt):(renderOperationDialog(prompt),await checking);
        if(choice==="apply"){gatewayUpdateNotice=null;try{localStorage.removeItem("solarminer-gateway-update-notice-v1");}catch{}renderGatewayUpdateBanner();await applyVerifiedGatewayUpdate(result);}
        else {gatewayUpdateNotice=result;renderGatewayUpdateBanner();}
      } else {
        renderOperationDialog({title:"Atualização bloqueada",message:"O pacote foi verificado, mas a verificação de recuperação bloqueou a instalação.",actions:[{label:"OK",value:"ok",primary:true}]});
        gatewayUpdateNotice=result;gatewayAutoUpdateSuppressed=true;renderGatewayUpdateBanner();if(!automatic)await checking;else await new Promise(resolve=>{$("#operation-dialog").addEventListener("close",resolve,{once:true});});
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
if (sessionInfo().authenticated) refreshGatewayReadings();
setInterval(() => {
  const lastRefresh=Date.parse(state.lastUpdated||"");
  if (document.visibilityState === "visible" && sessionInfo().authenticated && !state.refreshing && (state.page==="energia" || !Number.isFinite(lastRefresh) || Date.now()-lastRefresh>=30_000)) {
    refreshGatewayReadings();
  }
}, 10_000);
setInterval(() => {
  const info=sessionInfo();
  if(document.visibilityState!=="visible"||!info.authenticated||info.user?.role!=="owner"||gatewayAutoUpdateSuppressed||gatewayUpdateCheckInProgress||$("#operation-dialog")?.open)return;
  runGatewayUpdateCheck({automatic:true});
},60_000);
