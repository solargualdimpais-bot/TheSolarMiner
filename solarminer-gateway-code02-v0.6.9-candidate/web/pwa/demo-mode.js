/**
 * Pure local-only state for the visual demo. This module deliberately has no
 * fetch, API client, authentication, service-worker or device dependencies.
 */
export const DEMO_CONTROL_CONFIG = Object.freeze({
  inversores: Object.freeze({title:"Limite solar ilustrativo",key:"solarLimit",label:"Limite visual",min:1,max:10,step:.5,unit:"kW",note:"Só altera o valor-alvo apresentado nesta demonstração."}),
  baterias: Object.freeze({title:"Reserva de bateria",key:"batteryReserve",label:"Reserva pretendida",min:10,max:100,step:5,unit:"%",note:"Objetivo fictício; não altera carregamento nem descarga."}),
  mineradoras: Object.freeze({title:"Intensidade de cálculo",key:"minerLoad",label:"Carga demonstrativa",min:0,max:100,step:5,unit:"%",note:"Controlo cenográfico; não comunica com mineradoras."}),
  ev: Object.freeze({title:"Carregamento EV",key:"evEnabled",label:"Simular carregamento",toggle:true,note:"Interruptor local de demonstração. Nenhum carregador é acionado."}),
  aqs: Object.freeze({title:"Temperatura AQS",key:"aqsTarget",label:"Objetivo ilustrativo",min:35,max:65,step:1,unit:"°C",note:"Valor de demonstração; não comanda resistências nem bombas."}),
  "soalho-radiante": Object.freeze({title:"Conforto térmico",key:"floorTarget",label:"Temperatura pretendida",min:17,max:25,step:.5,unit:"°C",note:"Ajuste puramente local; não envia instruções a termóstatos."})
});

export function createDemoControlState() {
  return {solarLimit:5,batteryReserve:20,minerLoad:70,evEnabled:false,aqsTarget:48,floorTarget:21.5};
}

export function updateDemoControl(mode, state, key, value) {
  if (mode !== "SIMULATED" || !state || !Object.hasOwn(state,key)) return false;
  if (key === "evEnabled") {
    if (typeof value !== "boolean") return false;
    state[key] = value;
    return true;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) return false;
  const config = Object.values(DEMO_CONTROL_CONFIG).find(item => item.key === key);
  if (!config || config.toggle || value < config.min || value > config.max) return false;
  const steps = (value - config.min) / config.step;
  if (Math.abs(steps - Math.round(steps)) > 1e-8) return false;
  state[key] = value;
  return true;
}

export function toggleDemoControl(mode, state, key) {
  if (mode !== "SIMULATED" || !state || key !== "evEnabled" || typeof state[key] !== "boolean") return false;
  state[key] = !state[key];
  return true;
}
