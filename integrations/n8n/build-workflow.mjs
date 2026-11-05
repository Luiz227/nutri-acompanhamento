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
if (!/^[\\w-]{1,100}$/.test(config.instance)) throw new Error('Instância inválida');
if ($json.kind === 'incoming' && $json.instance !== config.instance) throw new Error('Instância não autorizada');
return [{json: {...$json, config}}];`, 480, 130);
condition('Evento aceito?', '={{ $json.kind !== "ignored" }}', 700, 130);
http('Consultar servidor do aplicativo', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/events/ingest" }}',
  '={{ JSON.stringify({event: Object.fromEntries(Object.entries($("Configurar conexões").first().json).filter(([key]) => key !== "config"))}) }}',
  'Nutri - API do aplicativo', 940, 40);
code('Aplicar autorização', [agent.routeJob],
  'const event = $("Configurar conexões").first().json; return [{json: routeJob($json, event)}];', 1180, 40);
condition('Responder?', '={{ $json.action !== "ignore" }}', 1400, 40);
condition('Usar IA?', '={{ $json.action === "assistant" }}', 1620, -40);
code('Preparar contexto da IA', [agent.makePrompt], `
const model = $('Configurar conexões').first().json.config.model;
if (!model || model === 'CONFIGURE_MODEL') throw new Error('Selecione um modelo disponível na sua conta.');
return [{json: makePrompt($json, model)}];`, 1840, -180);
http('Consultar IA', 'https://api.openai.com/v1/chat/completions', '={{ JSON.stringify($json) }}',
  'Nutri - IA (Authorization)', 2060, -180, { onError: 'continueRegularOutput' });
code('Ler resposta da IA', [agent.parseReply],
  'return [{json: {...$("Aplicar autorização").first().json, candidate: parseReply($json)}}];', 2280, -180);
http('Autorizar e reservar envio', '={{ $("Configurar conexões").first().json.config.backendBaseUrl + "/v1/nutri/dispatches/reserve" }}',
  '={{ JSON.stringify({eventId: $json.eventId, userId: $json.userId, phone: $json.phone, kind: $json.action, candidate: $json.candidate}) }}',
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
add('Leia antes de ativar', 'stickyNote', 1, { content: `## Nutri + Evolution API v2\n**Importação desativada.**\n1. Leia README.md e deploy/EASYPANEL.md na raiz.\n2. Publique o servidor server/app.py e configure seu volume.\n3. Configure credenciais e URLs nos nós.\n4. Escolha o modelo de IA e habilite enabled no nó Configurar conexões.\n5. Teste com seu próprio número antes de publicar.\n\nO servidor usa respostas fixas por padrão; AI_RESPONSES_ENABLED=true libera conversa geral. A IA não prescreve, calcula nutrientes ou salva refeições neste fluxo. SAIR é persistido antes da confirmação.`, width: 570, height: 360 }, 0, -450);

link('Cadastro do aplicativo', 'Validar cadastro'); link('Mensagem da Evolution', 'Filtrar mensagem');
link('Validar cadastro', 'Configurar conexões'); link('Filtrar mensagem', 'Configurar conexões');
link('Configurar conexões', 'Evento aceito?'); link('Evento aceito?', 'Consultar servidor do aplicativo');
link('Evento aceito?', 'Concluir evento', 1); link('Consultar servidor do aplicativo', 'Aplicar autorização');
link('Aplicar autorização', 'Responder?'); link('Responder?', 'Usar IA?'); link('Responder?', 'Concluir evento', 1);
link('Usar IA?', 'Preparar contexto da IA'); link('Usar IA?', 'Autorizar e reservar envio', 1);
link('Preparar contexto da IA', 'Consultar IA'); link('Consultar IA', 'Ler resposta da IA');
link('Ler resposta da IA', 'Autorizar e reservar envio'); link('Autorizar e reservar envio', 'Envio liberado?');
link('Envio liberado?', 'Validar destinatário'); link('Envio liberado?', 'Concluir evento', 1);
link('Validar destinatário', 'Enviar pela Evolution'); link('Enviar pela Evolution', 'Classificar resultado do envio');
link('Classificar resultado do envio', 'Salvar resultado no servidor'); link('Salvar resultado no servidor', 'Concluir evento');

const workflow = { name: 'Nutri - Aplicativo + Evolution API + IA', nodes, connections, active: false,
  settings: { executionOrder: 'v1', timezone: 'America/Sao_Paulo',
    saveDataSuccessExecution: 'none', saveDataErrorExecution: 'none',
    saveManualExecutions: false, saveExecutionProgress: false, executionTimeout: 180 },
  pinData: {}, tags: [] };
writeFileSync(new URL('./nutri-evolution.json', import.meta.url), JSON.stringify(workflow, null, 2) + '\n');
console.log(`Gerado: ${nodes.length} nós. Fluxo desativado, sem segredos.`);
