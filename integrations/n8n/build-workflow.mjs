import { writeFileSync } from 'node:fs';
import * as agent from './src/agent.mjs';

const nodes = [], connections = {};
function add(name, type, version, parameters, x, y, extra = {}) {
  nodes.push({ id: name.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-'),
    name, type: `n8n-nodes-base.${type}`, typeVersion: version, position: [x, y], parameters, ...extra });
}
function link(from, to, branch = 0) {
  const outputs = (connections[from] ??= { main: [] }).main;
  while (outputs.length <= branch) outputs.push([]);
  outputs[branch].push({ node: to, type: 'main', index: 0 });
}
function code(name, functions, body, x, y) {
  add(name, 'code', 2, { mode: 'runOnceForAllItems', jsCode: 'const $json = $input.first().json;\n' + functions.map(fn => fn.toString()).join('\n\n') + '\n' + body }, x, y);
}
function http(name, url, body, credential, x, y, extra = {}) {
  add(name, 'httpRequest', 4.2, { method: 'POST', url, authentication: 'genericCredentialType',
    genericAuthType: 'httpHeaderAuth', sendBody: true, specifyBody: 'json', jsonBody: body,
    options: { timeout: 30000 } }, x, y,
  { credentials: { httpHeaderAuth: { name: credential } }, retryOnFail: false, ...extra });
}
function condition(name, expression, x, y) {
  add(name, 'if', 2.2, { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
    conditions: [{ id: name, leftValue: expression, rightValue: true,
      operator: { type: 'boolean', operation: 'true', singleValue: true } }], combinator: 'and' }, options: {} }, x, y);
}

add('Cadastro do aplicativo', 'webhook', 2, { httpMethod: 'POST', path: 'nutri-app-registration',
  authentication: 'headerAuth', responseMode: 'lastNode', options: {} }, 0, 0,
{ webhookId: 'nutri-app-registration', credentials: { httpHeaderAuth: { name: 'Nutri - entrada do servidor' } } });
add('Mensagem da Evolution', 'webhook', 2, { httpMethod: 'POST', path: 'nutri-evolution-inbound',
  authentication: 'headerAuth', responseMode: 'lastNode', options: {} }, 0, 260,
{ webhookId: 'nutri-evolution-inbound', credentials: { httpHeaderAuth: { name: 'Nutri - entrada Evolution' } } });
code('Validar cadastro', [agent.normalizeApp], 'return [{json: normalizeApp($json.body)}];', 240, 0);
code('Filtrar mensagem', [agent.normalizeEvolution],
  'const event = normalizeEvolution($json.body); return [{json: event ?? {kind: "ignored"}}];', 240, 260);
code('Configurar conexões', [], `
// Edite somente estes valores. As chaves ficam nas credenciais do n8n.
const config = {
  enabled: false,
  backendBaseUrl: 'https://API-DO-APLICATIVO.example',
  evolutionBaseUrl: 'https://SUA-EVOLUTION.example',
  instance: 'nutri',
  model: 'CONFIGURE_MODEL',
};
if ($json.kind === 'ignored') return [{json: {...$json, config}}];
if (!config.enabled) throw new Error('Configure as conexões e habilite enabled antes de testar com contas reais.');
for (const key of ['backendBaseUrl', 'evolutionBaseUrl']) {
  if (!config[key].startsWith('https://') || config[key].includes('.example')) throw new Error('Configure HTTPS em ' + key);
  if (config[key].endsWith('/')) config[key] = config[key].slice(0, -1);
}
if (!/^[\\p{L}\\p{M}\\p{N}_-]{1,100}$/u.test(config.instance)) throw new Error('Instância inválida');
if ($json.kind === 'incoming' && $json.instance !== config.instance) throw new Error('Instância não autorizada');
return [{json: {...$json, config}}];`, 480, 130);
condition('Evento aceito?', '={{ $json.kind !== "ignored" }}', 700, 130);
http('Consultar servidor do aplicativo', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/events/collect" }}',
  '={{ JSON.stringify({event: Object.fromEntries(Object.entries($("Configurar conexões").first().json).filter(([key]) => key !== "config"))}) }}',
  'Nutri - API do aplicativo', 940, 40);
code('Aplicar autorização', [agent.routeJob],
  'const original = $("Configurar conexões").first().json; const event = original.mediaType ? $("Unir mídia ao diálogo").first().json.event : original; return [{json: routeJob($json, event)}];', 1180, 40);
condition('Responder?', '={{ $json.action !== "ignore" }}', 1400, 40);
condition('Usar IA?', '={{ $json.action === "assistant" }}', 1620, -40);
code('Preparar contexto da IA', [agent.makePrompt], `
const model = $('Configurar conexões').first().json.config.model;
if (!model || model === 'CONFIGURE_MODEL') throw new Error('Selecione um modelo disponível na sua conta.');
return [{json: makePrompt($json, model)}];`, 1840, -180);
http('Consultar IA', 'https://api.openai.com/v1/chat/completions', '={{ JSON.stringify($json) }}',
  'Nutri - IA (Authorization)', 2060, -180, { onError: 'continueRegularOutput' });
// Use n8n's native OpenAI credential so it builds the Authorization header.
const aiNode = nodes.find(n => n.name === 'Consultar IA');
aiNode.parameters.authentication = 'predefinedCredentialType';
aiNode.parameters.nodeCredentialType = 'openAiApi';
delete aiNode.parameters.genericAuthType;
aiNode.credentials = { openAiApi: { name: 'Nutri - OpenAI' } };
code('Ler resposta da IA', [agent.parseAssistantResult],
  'return [{json: {...$("Aplicar autorização").first().json, ...parseAssistantResult($json)}}];', 2280, -180);
http('Autorizar e reservar envio', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/dispatches/reserve" }}',
  '={{ JSON.stringify({eventId: $json.eventId, userId: $json.userId, phone: $json.phone, kind: $json.action, candidate: $json.candidate, record: $json.record ?? null}) }}',
  'Nutri - API do aplicativo', 2520, -40);
condition('Envio liberado?', '={{ $json.approved === true }}', 2740, -40);
code('Validar destinatário', [agent.validateDispatch], `
return [{json: validateDispatch($json, $('Aplicar autorização').first().json,
  $('Configurar conexões').first().json.config)}];`, 2960, -120);
http('Enviar pela Evolution', '={{ $("Configurar conexões").first().json.config.evolutionBaseUrl + "/message/sendText/" + encodeURIComponent($json.instance) }}',
  '={{ JSON.stringify({number: $json.number, text: $json.text, linkPreview: false}) }}',
  'Nutri - Evolution (apikey)', 3180, -120, { onError: 'continueRegularOutput' });
code('Classificar resultado do envio', [agent.deliveryReceipt],
  'return [{json: deliveryReceipt($json, $("Validar destinatário").first().json.dispatchId)}];', 3400, -120);
http('Salvar resultado no servidor', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/dispatches/result" }}',
  '={{ JSON.stringify($json) }}', 'Nutri - API do aplicativo', 3620, -120);
code('Concluir evento', [], 'return [{json: {ok: true}}];', 3860, 160);
add('Leia antes de ativar', 'stickyNote', 1, { content: `## Nutri + Evolution API v2\n**Importação desativada.**\n1. Leia README.md e deploy/EASYPANEL.md na raiz.\n2. Publique o servidor server/app.py e configure seu volume.\n3. Configure credenciais e URLs nos nós.\n4. Escolha o modelo de IA e habilite enabled no nó Configurar conexões.\n5. Teste com seu próprio número antes de publicar.\n\nO servidor usa respostas fixas por padrão; AI_RESPONSES_ENABLED=true libera conversa geral. A IA propõe refeições, água, peso e observações. A API v7 registra automaticamente sem confirmação. Fotos e áudios são autorizados antes da leitura; porções médias têm referência IBGE. Nutrientes vêm da TACO e de produtos Open Food Facts; aproximações são identificadas. Parágrafos viram mensagens curtas. Sugestões gerais exigem autorização e preferências. Não há prescrição. SAIR é persistido antes da confirmação.`, width: 570, height: 360 }, 0, -450);

// Collect bursts in SQLite; no global workflow static data or cross-patient buffers.
nodes.find(n => n.name === 'Consultar servidor do aplicativo').parameters.options.timeout = 60000;
nodes.find(n => n.name === 'Mensagem da Evolution').parameters.responseMode = 'onReceived';
code('Preparar partes', [], `const parts = $json.parts;
if (!Array.isArray(parts) || !parts.length || parts.length > 10) throw new Error('Atualize a API para habilitar o envio em partes.');
return parts.map(part => ({json: part, pairedItem: {item: 0}}));`, 3150, -120);
add('Enviar uma parte por vez', 'splitInBatches', 3, {batchSize: 1, options: {}}, 3380, -120);
http('Revalidar parte', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/dispatches/part" }}',
  '={{ JSON.stringify({dispatchId: $json.dispatchId, index: $json.index}) }}', 'Nutri - API do aplicativo', 3600, -120);
condition('Parte autorizada?', '={{ $json.approved === true }}', 3820, -120);
const classify = nodes.find(n => n.name === 'Classificar resultado do envio');
classify.parameters.jsCode = `const response = $input.first().json;
const part = $('Revalidar parte').item.json;
return [{json: {partId: part.partId, status: typeof response?.key?.id === 'string' && response.key.id ? 'accepted' : 'uncertain', providerMessageId: response?.key?.id ?? null}, pairedItem: {item: 0}}];`;
const receiptNode = nodes.find(n => n.name === 'Salvar resultado no servidor');
receiptNode.parameters.url = '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/dispatches/part-result" }}';
condition('Continuar partes?', '={{ $json.continue === true }}', 4700, -120);
add('Pausa entre partes', 'wait', 1.1, {resume: 'timeInterval', amount: 2, unit: 'seconds'}, 4900, 120, {webhookId: 'nutri-pausa-partes'});
nodes.find(n => n.name === 'Enviar pela Evolution').position = [4050, -120];
classify.position = [4260, -120]; receiptNode.position = [4480, -120];

// Media is authorized by the backend before any provider download or AI cost.
condition('Tem mídia?', '={{ ["image","audio"].includes($json.mediaType) }}', 820, 400);
http('Autorizar leitura de mídia', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/media/authorize" }}',
  '={{ JSON.stringify({event: $("Configurar conexões").first().json}) }}', 'Nutri - API do aplicativo', 1040, 400);
condition('Mídia autorizada?', '={{ $json.approved === true }}', 1260, 400);
http('Baixar mídia da Evolution', '={{ $("Configurar conexões").first().json.config.evolutionBaseUrl + "/chat/getBase64FromMediaMessage/" + encodeURIComponent($("Configurar conexões").first().json.config.instance) }}',
  '={{ JSON.stringify({message:{key:$("Configurar conexões").first().json.mediaKey}, convertToMp4:true}) }}',
  'Nutri - Evolution (apikey)', 1480, 400, {onError:'continueRegularOutput'});
code('Validar arquivo recebido', [agent.validateMedia], 'return [{json:validateMedia($json, $("Configurar conexões").first().json)}];', 1700, 400);
condition('Arquivo válido?', '={{ $json.valid === true }}', 1920, 400);
condition('É áudio?', '={{ $json.mediaType === "audio" }}', 2140, 400);
add('Preparar arquivo de áudio', 'convertToFile', 1.1, {operation:'toBinary',sourceProperty:'base64',binaryPropertyName:'data',
  options:{fileName:'={{ $json.fileName }}',mimeType:'={{ $json.mimeType }}'}},2360,300);
add('Transcrever áudio', 'httpRequest', 4.2, {method:'POST',url:'https://api.openai.com/v1/audio/transcriptions',
  authentication:'predefinedCredentialType',nodeCredentialType:'openAiApi',sendBody:true,contentType:'multipart-form-data',
  bodyParameters:{parameters:[{name:'model',value:'gpt-transcribe'},
    {parameterType:'formBinaryData',name:'file',inputDataFieldName:'data'}]},options:{timeout:60000}},2580,300,
  {credentials:{openAiApi:{name:'Nutri - OpenAI'}},retryOnFail:false,onError:'continueRegularOutput'});
code('Preparar leitura da foto', [agent.visionPrompt], 'return [{json:visionPrompt($json, $("Configurar conexões").first().json, $("Configurar conexões").first().json.config.model)}];',2360,540);
http('Ler foto com IA', 'https://api.openai.com/v1/chat/completions', '={{ JSON.stringify($json) }}', 'unused',2580,540,{onError:'continueRegularOutput'});
const visionNode=nodes.find(n=>n.name==='Ler foto com IA');
visionNode.parameters.authentication='predefinedCredentialType';visionNode.parameters.nodeCredentialType='openAiApi';
delete visionNode.parameters.genericAuthType;visionNode.credentials={openAiApi:{name:'Nutri - OpenAI'}};
visionNode.parameters.options.timeout=60000;
code('Unir mídia ao diálogo', [agent.mediaText], 'const event=$("Configurar conexões").first().json; const text=mediaText($json,event); const command=event.mediaType === "audio" && ["SAIR","PARAR","CANCELAR","STOP"].includes(text.trim().toUpperCase()) ? "stop" : null; return [{json:{event:{...event,text,command},mediaToken:$("Autorizar leitura de mídia").first().json.mediaToken}}];',2820,400);
http('Concluir leitura e agrupar', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/media/complete" }}',
  '={{ JSON.stringify($json) }}', 'Nutri - API do aplicativo',3040,400);
nodes.find(n=>n.name==='Concluir leitura e agrupar').parameters.options.timeout=110000;
nodes.find(n=>n.name==='Consultar servidor do aplicativo').parameters.options.timeout=110000;
link('Tem mídia?', 'Autorizar leitura de mídia'); link('Tem mídia?', 'Consultar servidor do aplicativo',1);
link('Autorizar leitura de mídia','Mídia autorizada?');link('Mídia autorizada?','Baixar mídia da Evolution');
link('Mídia autorizada?','Concluir evento',1);link('Baixar mídia da Evolution','Validar arquivo recebido');
link('Validar arquivo recebido','Arquivo válido?');link('Arquivo válido?','É áudio?');
link('Arquivo válido?','Unir mídia ao diálogo',1);link('É áudio?','Preparar arquivo de áudio');
link('É áudio?','Preparar leitura da foto',1);link('Preparar arquivo de áudio','Transcrever áudio');
link('Transcrever áudio','Unir mídia ao diálogo');link('Preparar leitura da foto','Ler foto com IA');
link('Ler foto com IA','Unir mídia ao diálogo');link('Unir mídia ao diálogo','Concluir leitura e agrupar');
link('Concluir leitura e agrupar','Aplicar autorização');

link('Cadastro do aplicativo', 'Validar cadastro'); link('Mensagem da Evolution', 'Filtrar mensagem');
link('Validar cadastro', 'Configurar conexões'); link('Filtrar mensagem', 'Configurar conexões');
link('Configurar conexões', 'Evento aceito?'); link('Evento aceito?', 'Tem mídia?');
link('Evento aceito?', 'Concluir evento', 1); link('Consultar servidor do aplicativo', 'Aplicar autorização');
link('Aplicar autorização', 'Responder?'); link('Responder?', 'Usar IA?'); link('Responder?', 'Concluir evento', 1);
link('Usar IA?', 'Preparar contexto da IA'); link('Usar IA?', 'Autorizar e reservar envio', 1);
link('Preparar contexto da IA', 'Consultar IA'); link('Consultar IA', 'Ler resposta da IA');
link('Ler resposta da IA', 'Autorizar e reservar envio'); link('Autorizar e reservar envio', 'Envio liberado?');
link('Envio liberado?', 'Validar destinatário'); link('Envio liberado?', 'Concluir evento', 1);
link('Validar destinatário', 'Preparar partes');
link('Preparar partes', 'Enviar uma parte por vez');
link('Enviar uma parte por vez', 'Concluir evento', 0);
link('Enviar uma parte por vez', 'Revalidar parte', 1);
link('Revalidar parte', 'Parte autorizada?');
link('Parte autorizada?', 'Enviar pela Evolution');
link('Parte autorizada?', 'Concluir evento', 1); link('Enviar pela Evolution', 'Classificar resultado do envio');
link('Classificar resultado do envio', 'Salvar resultado no servidor'); link('Salvar resultado no servidor', 'Continuar partes?');
link('Continuar partes?', 'Pausa entre partes');
link('Continuar partes?', 'Concluir evento', 1);
link('Pausa entre partes', 'Enviar uma parte por vez');

const workflow = { name: 'Nutri - Aplicativo + Evolution API + IA', nodes, connections, active: false,
  settings: { executionOrder: 'v1', timezone: 'America/Sao_Paulo',
    saveDataSuccessExecution: 'none', saveDataErrorExecution: 'none',
    saveManualExecutions: false, saveExecutionProgress: false, executionTimeout: 240 },
  pinData: {}, tags: [] };
writeFileSync(new URL('./nutri-evolution.json', import.meta.url), JSON.stringify(workflow, null, 2) + '\n');
console.log(`Gerado: ${nodes.length} nós. Fluxo desativado, sem segredos.`);
