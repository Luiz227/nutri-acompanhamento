import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { normalizeApp, normalizeEvolution, routeJob, makePrompt, parseReply, parseAssistantResult,
  validateDispatch, deliveryReceipt, validateMedia, mediaText, visionPrompt } from '../src/agent.mjs';

const inbound = (text = 'Olá') => ({ event: 'messages.upsert', instance: 'nutri',
  data: { key: { id: 'msg-123', remoteJid: '5511999999999@s.whatsapp.net', fromMe: false },
    message: { conversation: text } } });

test('authenticated reminder notification retains its kind and uses server text', () => {
  const event = normalizeApp({kind:'reminder',eventId:'reminder:patient-1:20261106T0900',userId:'patient-1',phone:'5511999999999',
    consent:{granted:true,version:'test',at:new Date().toISOString()}});
  assert.equal(event.kind,'reminder');
  const routed=routeJob({...event,action:'reply',verified:true,consentActive:true,text:'Oi, lembrete de água.'},event);
  assert.equal(routed.candidate,'Oi, lembrete de água.');
});

test('structured meal keeps explicit category and user context for deterministic server calculation', () => {
  const record={kind:'meal',text:'Queijo, mozarela',quantity:7,unit:'g',mealType:'breakfast'};
  const parsed=parseAssistantResult({choices:[{finish_reason:'stop',message:{content:JSON.stringify({reply:'Vamos conferir seu café da manhã.',record})}}]});
  assert.deepEqual(parsed.record,record);
  const prompt=JSON.stringify(makePrompt({message:'7 gramas',context:{displayName:'Luiz',waterReminders:'Desativados'},history:[]},'model-test'));
  assert.match(prompt,/Luiz/);
  assert.match(prompt,/mealType/);
  assert.match(prompt,/Desativados/);
});

test('prompt receives the latest structured app objective, gender and daily targets', () => {
  const prompt = makePrompt({message:'Qual minha meta?',context:{appProfile:{gender:'male',goal:'gainWeight',activityLevel:'active',dailyGoals:{energyKcal:2500,proteinG:150}}},history:[]},'model-test');
  const text=JSON.stringify(prompt);
  assert.match(text, /2500/);
  assert.match(text, /gainWeight/);
  assert.match(text, /male/);
  assert.match(text, /Não repita perguntas sobre idade/);
});

test('accented instance is preserved and unsafe instance names are rejected', () => {
  const body = { ...inbound(), instance: 'Nutrição' };
  const event = normalizeEvolution(body);
  assert.equal(event.instance, 'Nutrição');
  assert.equal(event.eventId, 'evo:Nutrição:msg-123');
  for (const instance of ['../nutri', 'nutri/test', 'nutri\n', '', 'a'.repeat(101)]) {
    assert.equal(normalizeEvolution({ ...body, instance }), null);
  }
});
const job = () => ({ eventId: 'event-12345678', action: 'assistant',
  userId: 'patient-1', phone: '5511999999999', verified: true, consentActive: true,
  message: 'Meu almoço foi arroz e feijão', context: {}, history: [] });

test('app event requires consent and sends no health profile', () => {
  const result = normalizeApp({ eventId: 'registration-123', userId: 'patient-1',
    phone: '+55 (11) 99999-9999', consent: { granted: true, version: '2026-11-01',
      at: '2026-11-01T12:00:00Z' }, weight: 80 });
  assert.equal(result.phone, '5511999999999');
  assert.equal(result.weight, undefined);
  assert.throws(() => normalizeApp({ ...result, consent: { granted: false } }));
});
test('Evolution accepts personal text and records exact opt-out intent', () => {
  const event = normalizeEvolution(inbound('  SAIR  '));
  assert.equal(event.command, 'stop');
  assert.equal(event.phone, '5511999999999');
  assert.equal(event.messageId, 'msg-123');
  assert.equal(normalizeEvolution(inbound('não quero sair da dieta')).command, null);
});
test('ignores outgoing, group, status, historic, LID and unsupported messages', () => {
  for (const mutate of [
    p => p.data.key.fromMe = true,
    p => p.data.key.remoteJid = '123@g.us',
    p => p.data.key.remoteJid = 'status@broadcast',
    p => p.data.key.remoteJid = '123@lid',
    p => p.event = 'messages.set',
    p => p.data.message = { stickerMessage: {} },
  ]) {
    const p = inbound(); mutate(p); assert.equal(normalizeEvolution(p), null);
  }
});
test('extended text works, invalid sender and missing message IDs fail closed', () => {
  const p = inbound(); p.data.message = { extendedTextMessage: { text: 'Bom dia' } };
  assert.equal(normalizeEvolution(p).text, 'Bom dia');
  delete p.data.key.id; assert.equal(normalizeEvolution(p), null);
});
test('backend cannot release AI for unverified or unsubscribed patients', () => {
  assert.throws(() => routeJob({ ...job(), verified: false }, {}));
  assert.throws(() => routeJob({ ...job(), consentActive: false }, {}));
  assert.throws(() => routeJob(job(), { command: 'stop' }));
  assert.equal(routeJob({ action: 'ignore' }, {}).action, 'ignore');
});
test('SAIR requires persisted opt-out before sending acknowledgement', () => {
  assert.throws(() => routeJob({ ...job(), action: 'reply' }, { command: 'stop' }));
  const result = routeJob({ ...job(), action: 'reply', consentActive: false,
    optOutPersisted: true }, { command: 'stop' });
  assert.match(result.candidate, /interrompidas/);
});
test('welcome does not expose any patient information before verification', () => {
  const result = routeJob({ ...job(), action: 'welcome', verified: false,
    context: { displayName: 'PRIVATE', weight: 80 } }, {});
  assert.doesNotMatch(result.candidate, /PRIVATE|80/);
  assert.match(result.candidate, /assistente virtual/);
});
test('model receives no phone, user IDs or arbitrary context fields', () => {
  const j = { ...job(), context: { displayName: 'Ana', approvedGoal: 'Registrar refeições',
    secret: 'PRIVATE' }, history: [{ role: 'system', content: 'INJECT' },
      { role: 'user', content: 'Bom dia' }] };
  const prompt = makePrompt(j, 'modelo-configurado');
  assert.equal(prompt.model, 'modelo-configurado');
  assert.equal(prompt.store, false);
  const text = JSON.stringify(prompt);
  assert.doesNotMatch(text, /5511999999999|patient-1|PRIVATE|INJECT/);
  assert.match(text, /Não invente/);
});
test('invalid or oversized model outputs use an explicit unavailable response', () => {
  assert.match(parseReply({ choices: [] }), /indisponível/);
  assert.match(parseReply({ choices: [{ message: { content: 'a'.repeat(2000) } }] }), /indisponível/);
  assert.equal(parseReply({ choices: [{ message: { content: 'Como foi seu almoço?' },
    finish_reason: 'stop' }] }), 'Como foi seu almoço?');
});
test('dispatch requires a fresh server authorization, matching identity and instance', () => {
  const d = { approved: true, dispatchId: 'dispatch-123', eventId: job().eventId,
    userId: job().userId, phone: job().phone, instance: 'nutri', text: 'Olá',
    expiresAt: new Date(Date.now() + 30000).toISOString() };
  assert.equal(validateDispatch(d, job(), { instance: 'nutri' }).dispatchId, d.dispatchId);
  for (const patch of [{ approved: false }, { phone: '5521999999999' },
    { instance: 'other' }, { eventId: 'other' }, { expiresAt: '2000-01-01' }]) {
    assert.throws(() => validateDispatch({ ...d, ...patch }, job(), { instance: 'nutri' }));
  }
});
test('Evolution acceptance is not represented as delivery to patient', () => {
  assert.equal(deliveryReceipt({ key: { id: 'out-1' } }, 'dispatch-1').status, 'accepted');
  assert.equal(deliveryReceipt({ error: 'timeout' }, 'dispatch-1').status, 'uncertain');
});
test('workflow has authenticated triggers, no embedded keys, valid links and no send retries', () => {
  const flow = JSON.parse(readFileSync(new URL('../nutri-evolution.json', import.meta.url)));
  assert.equal(flow.active, false);
  const nodes = new Map(flow.nodes.map(n => [n.name, n]));
  for (const n of flow.nodes.filter(n => n.type.endsWith('.webhook'))) {
    assert.equal(n.parameters.authentication, 'headerAuth');
  }
  assert.equal(nodes.get('Enviar pela Evolution').retryOnFail, false);
  assert.equal(flow.settings.saveDataSuccessExecution, 'none');
  assert.equal(flow.settings.saveDataErrorExecution, 'none');
  for (const [name, outputs] of Object.entries(flow.connections)) {
    assert.ok(nodes.has(name));
    for (const group of outputs.main ?? []) for (const edge of group) assert.ok(nodes.has(edge.node));
  }
  assert.doesNotMatch(JSON.stringify(flow), /sk-[A-Za-z0-9]{20}/);
});

test('every exported Code node compiles, including escaped config regexes', () => {
  const flow = JSON.parse(readFileSync(new URL('../nutri-evolution.json', import.meta.url)));
  for (const node of flow.nodes.filter(n => n.type.endsWith('.code'))) {
    assert.doesNotThrow(() => new vm.Script('(function(){' + node.parameters.jsCode + '\n})'), node.name);
  }
});


test('photos and short audio retain only safe identifiers; view-once and groups never enter media AI',()=>{
  const p=inbound();p.data.message={imageMessage:{caption:'Meu almoço',url:'https://untrusted.example',mediaKey:'not-forwarded'}};
  const e=normalizeEvolution(p);assert.equal(e.mediaType,'image');assert.equal(e.caption,'Meu almoço');
  assert.equal(e.mediaKey.id,'msg-123');assert.equal(JSON.stringify(e).includes('untrusted'),false);
  p.data.message.imageMessage.viewOnce=true;assert.equal(normalizeEvolution(p),null);
  p.data.message={audioMessage:{seconds:20}};assert.equal(normalizeEvolution(p).mediaType,'audio');
  p.data.message.audioMessage.seconds=181;assert.equal(normalizeEvolution(p),null);
  p.data.key.remoteJid='123@lid';p.data.key.remoteJidAlt='5511999999999@s.whatsapp.net';
  p.data.message={audioMessage:{seconds:10}};assert.equal(normalizeEvolution(p).phone,'5511999999999');
  p.data.key.remoteJid='123@g.us';assert.equal(normalizeEvolution(p),null);
});
test('media validates size, MIME and conversion; failures never fabricate a meal',()=>{
  const event={mediaType:'image',caption:'foi meu almoço'};
  const image=validateMedia({base64:'a'.repeat(64),mimetype:'image/jpeg'},event);
  assert.equal(image.valid,true);assert.equal(validateMedia({base64:'a'.repeat(64),mimetype:'text/html'},event).valid,false);
  assert.equal(validateMedia({base64:'a'.repeat(64),mimetype:'audio/ogg'},{mediaType:'audio'}).valid,false);
  assert.equal(visionPrompt(image,event,'vision-model').messages.at(-1).content[1].image_url.url.startsWith('data:image/jpeg;base64,'),true);
  assert.match(mediaText({error:'timeout'},event),/não registre/);
  const text=mediaText({choices:[{finish_reason:'stop',message:{content:JSON.stringify({usable:true,description:'Uma maçã média'})}}]},event);
  assert.match(text,/estimativas visuais/);assert.match(text,/foi meu almoço/);
  assert.equal(mediaText({text:'Comi uma maçã'},{mediaType:'audio'}),'Comi uma maçã');
});
