// Executes the exported Code/If/HTTP expressions with fake services only.
// This is a graph simulation, not a replacement for importing in real n8n.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

const flow = JSON.parse(readFileSync(new URL('../nutri-evolution.json', import.meta.url)));
function simulate(trigger, body, options = {}) {
  const memory = {}, calls = [];
  let name = trigger, value = { body }, steps = 0;
  let queue = [], texts = [];
  const event = body.eventId ? { eventId: body.eventId, userId: body.userId, phone: body.phone } :
    { eventId: `evo:nutri:${body.data?.key?.id}`, userId: 'patient-demo-0001', phone: '5511999999999' };
  const job = { ...event, verified: true, consentActive: true, action: options.action ?? 'assistant',
    message: body.data?.message?.conversation, context: {}, history: [], documentRequested: options.pdf === true,
    ...(options.stop ? { action: 'reply', consentActive: false, optOutPersisted: true } : {}) };
  function evaluate(source, json) {
    return vm.runInNewContext(source, {
      $json: json,
      $input: { first: () => ({ json }) },
      $: key => ({ first: () => ({ json: memory[key] }), item: { json: memory[key] } }),
      Date,
    });
  }
  const expression = (source, json) => source.startsWith('={{') ?
    evaluate('(' + source.slice(3, -2) + ')', json) : source;
  while (name) {
    assert.ok(++steps < 100, 'bounded execution');
    const node = flow.nodes.find(n => n.name === name);
    let branch = 0;
    if (node.type.endsWith('.code')) {
      let code = node.parameters.jsCode;
      if (name === 'Configurar conexões') code = code.replace('enabled: false', 'enabled: true')
        .replaceAll('https://API-DO-APLICATIVO.example', 'https://backend.test')
        .replaceAll('https://SUA-EVOLUTION.example', 'https://evolution.test')
        .replace("model: 'CONFIGURE_MODEL'", "model: 'model-test'");
      const outputs = evaluate('(function(){' + code + '\n})()', value);
      if (name === 'Preparar partes') queue = outputs.map(o => o.json);
      value = outputs[0].json;
    } else if (node.type.endsWith('.convertToFile')) {
      value={};
    } else if (node.type.endsWith('.splitInBatches')) {
      if (queue.length) { value = queue.shift(); branch = 1; } else { branch = 0; }
    } else if (node.type.endsWith('.wait')) {
      assert.equal(node.parameters.amount, 2);
    } else if (node.type.endsWith('.if')) {
      branch = expression(node.parameters.conditions.conditions[0].leftValue, value) ? 0 : 1;
    } else if (node.type.endsWith('.httpRequest')) {
      const url = expression(node.parameters.url, value);
      const payload = node.parameters.jsonBody ? JSON.parse(expression(node.parameters.jsonBody, value)) : {};
      calls.push({ name, url, payload });
      switch (name) {
        case 'Autorizar leitura de mídia': value={approved:!options.mediaBlocked,mediaToken:'media-claim-test'};break;
        case 'Baixar mídia da Evolution': value={base64:'a'.repeat(64),mimetype:body.data.message.imageMessage?'image/jpeg':'audio/mp4'};break;
        case 'Ler foto com IA': value={choices:[{finish_reason:'stop',message:{content:JSON.stringify({usable:true,description:'Uma maçã média'})}}]};break;
        case 'Transcrever áudio': value={text:'Comi uma maçã no lanche'};break;
        case 'Concluir leitura e agrupar': value={...job,message:payload.event.text};break;
        case 'Consultar servidor do aplicativo': value = options.ignore ? { action: 'ignore' } : job; break;
        case 'Consultar IA': value = { choices: [{ message: { content: JSON.stringify({reply:'Como foi seu almoço?',record:null,...(options.pdf?{plan:{meals:[],shopping:[],tips:[]}}:{})}) }, finish_reason: 'stop' }] }; break;
        case 'Autorizar e reservar envio': texts = options.parts ?? (options.pdf ? ['Seu guia está pronto','PDF'] : [payload.candidate]); value = options.block ? { approved: false } : {
          ...event, approved: true, instance: 'nutri', text: payload.candidate,
          parts: texts.map((_,index)=>({dispatchId:'dispatch-demo-0001',index})),
          dispatchId: 'dispatch-demo-0001', expiresAt: new Date(Date.now() + 30000).toISOString(),
        }; break;
        case 'Revalidar parte': value = options.cancelAfterFirst && payload.index > 0 ? {approved:false} : {approved:true,partId:'part-demo-'+payload.index,number:event.phone,instance:'nutri',text:texts[payload.index],...(options.pdf && payload.index===1 ? {mediaType:'document',mimetype:'application/pdf',fileName:'seu-guia-alimentar.pdf',media:'JVBERi0xLjQK'} : {})}; break;
        case 'Enviar PDF pela Evolution':
        case 'Enviar pela Evolution': value = options.timeout ? { error: 'timeout' } : { key: { id: 'evolution-out-1' } }; break;
        case 'Salvar resultado no servidor': value = { continue: payload.status === 'accepted' }; break;
        default: throw new Error(name);
      }
    }
    memory[name] = value;
    const edges = flow.connections[name]?.main?.[branch] ?? [];
    assert.ok(edges.length <= 1, 'no duplicate fanout sends');
    name = edges[0]?.node;
  }
  assert.equal(value.ok, true);
  return calls;
}
const message = text => ({ event: 'messages.upsert', instance: 'nutri', data: {
  key: { id: 'incoming-demo-1', fromMe: false, remoteJid: '5511999999999@s.whatsapp.net' },
  message: { conversation: text },
} });

test('exported registration branch sends a generic welcome without invoking AI', () => {
  const calls = simulate('Cadastro do aplicativo', { eventId: 'registration-demo-1',
    userId: 'patient-demo-0001', phone: '5511999999999', consent: { granted: true,
      version: '2026-11-01', at: '2026-11-01T12:00:00Z' } }, { action: 'welcome' });
  assert.equal(calls.some(c => c.name === 'Consultar IA'), false);
  const send = calls.find(c => c.name === 'Enviar pela Evolution');
  assert.equal(send.url, 'https://evolution.test/message/sendText/nutri');
  assert.equal(send.payload.number, '5511999999999');
  assert.match(send.payload.text, /assistente virtual/);
});
test('exported conversation branch consults AI then reserves and sends exactly once', () => {
  const calls = simulate('Mensagem da Evolution', message('Bom dia'));
  assert.deepEqual(calls.map(c => c.name), ['Consultar servidor do aplicativo', 'Consultar IA',
    'Autorizar e reservar envio', 'Revalidar parte', 'Enviar pela Evolution', 'Salvar resultado no servidor']);
  assert.equal(calls.find(c => c.name === 'Consultar IA').payload.model, 'model-test');
  assert.equal(calls.find(c => c.name === 'Enviar pela Evolution').payload.text, 'Como foi seu almoço?');
  assert.equal(calls.at(-1).payload.status, 'accepted');
});
test('exported cancellation branch never consults AI', () => {
  const calls = simulate('Mensagem da Evolution', message('SAIR'), { stop: true });
  assert.equal(calls.some(c => c.name === 'Consultar IA'), false);
  assert.equal(calls[0].payload.event.command, 'stop');
  assert.match(calls.find(c => c.name === 'Enviar pela Evolution').payload.text, /interrompidas/);
});
test('ignored group, duplicate and blocked reservation never send', () => {
  const group = message('oi'); group.data.key.remoteJid = '123@g.us';
  assert.equal(simulate('Mensagem da Evolution', group).length, 0);
  for (const options of [{ ignore: true }, { block: true }]) {
    assert.equal(simulate('Mensagem da Evolution', message('oi'), options)
      .some(c => c.name === 'Enviar pela Evolution'), false);
  }
});
test('timeout is saved as uncertain, without retrying the WhatsApp call', () => {
  const calls = simulate('Mensagem da Evolution', message('oi'), { timeout: true });
  assert.equal(calls.filter(c => c.name === 'Enviar pela Evolution').length, 1);
  assert.equal(calls.at(-1).payload.status, 'uncertain');
});


test('multipart loop sends parts in order and rechecks consent before each one', () => {
  const calls=simulate('Mensagem da Evolution',message('Oi'),{parts:['Primeira parte','Segunda parte']});
  assert.deepEqual(calls.filter(c=>c.name==='Enviar pela Evolution').map(c=>c.payload.text),['Primeira parte','Segunda parte']);
  assert.equal(calls.filter(c=>c.name==='Revalidar parte').length,2);
  const cancelled=simulate('Mensagem da Evolution',message('Oi'),{parts:['Primeira','Segunda'],cancelAfterFirst:true});
  assert.equal(cancelled.filter(c=>c.name==='Enviar pela Evolution').length,1);
});


test('photo and audio graph authorize before download, then collect interpretation before response',()=>{
  for(const type of ['image','audio']) {
    const p=message('');p.data.message=type==='image'?{imageMessage:{caption:'meu lanche'}}:{audioMessage:{seconds:10}};
    const calls=simulate('Mensagem da Evolution',p);
    const names=calls.map(c=>c.name);
    assert.ok(names.indexOf('Autorizar leitura de mídia')<names.indexOf('Baixar mídia da Evolution'));
    assert.ok(names.includes(type==='image'?'Ler foto com IA':'Transcrever áudio'));
    assert.ok(names.indexOf('Concluir leitura e agrupar')<names.indexOf('Consultar IA'));
    assert.ok(names.includes('Enviar pela Evolution'));
    const blocked=simulate('Mensagem da Evolution',p,{mediaBlocked:true});
    assert.deepEqual(blocked.map(c=>c.name),['Autorizar leitura de mídia']);
  }
});


test('PDF is sent as a document only after text and part authorization, and opt-out stops it',()=>{
  const calls=simulate('Mensagem da Evolution',message('Quero sugestões em PDF'),{pdf:true});
  const names=calls.map(c=>c.name);
  assert.ok(names.indexOf('Enviar pela Evolution')<names.indexOf('Enviar PDF pela Evolution'));
  const file=calls.find(c=>c.name==='Enviar PDF pela Evolution');
  assert.match(file.url,/message\/sendMedia\/nutri$/);
  assert.equal(file.payload.mimetype,'application/pdf');assert.equal(file.payload.mediatype,'document');
  assert.equal(file.payload.fileName,'seu-guia-alimentar.pdf');
  assert.ok(calls.find(c=>c.name==='Autorizar e reservar envio').payload.plan);
  const blocked=simulate('Mensagem da Evolution',message('Quero PDF'),{pdf:true,cancelAfterFirst:true});
  assert.equal(blocked.filter(c=>c.name==='Enviar PDF pela Evolution').length,0);
});
