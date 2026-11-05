# Contrato do servidor do aplicativo

**Esta distribuição inclui uma implementação piloto em `server/app.py`.**
Este documento conserva o contrato de referência. A implementação usa SQLite
persistente, código temporário e reservas únicas. Revisão clínica humana,
reconciliação automática de envios e escala horizontal não estão implementadas.
O modo padrão tem respostas fixas; conversa geral é liberada explicitamente
por `AI_RESPONSES_ENABLED=true`. Consulte o guia de deploy antes de ativar.
Não substitua estes endpoints por respostas fixas liberando usuários em produção.
Todos são internos, autenticados por token de serviço do n8n com escopo limitado.
A credencial do servidor que aciona o n8n é diferente e nunca vai no aplicativo.

## Modelo persistente mínimo

- Paciente: ID próprio do servidor, telefone normalizado e exclusivo, vínculo
  com usuário autenticado, estado de verificação, versão/data do consentimento,
  estado de cancelamento e revisão de autorização.
- Verificação: hash de código temporário gerado com aleatoriedade criptográfica,
  validade curta (por exemplo 10 min), no máximo 5 tentativas, uso único.
  O código é mostrado apenas na sessão autenticada do aplicativo; digitá-lo no
  WhatsApp confirma o vínculo. Informar telefone no formulário não o verifica.
- Evento: chave única de origem + instância + ID do evento, estado de trabalho,
  conteúdo minimizado e prazo de retenção. Não usar memória volátil do n8n
  como deduplicação ou estado de autorização.
- Envio/outbox: ID, evento/paciente, revisão de consentimento, candidato
  revisado, estado reservado/aceito/incerto/bloqueado e ID da Evolution.

Trate mudanças de telefone como novo vínculo. Números com 8/9 dígitos não
devem ser fundidos por heurística. Use a identidade verificada pelo servidor.
Rate limiting e limites de boas-vindas são obrigatórios no ingresso público
do aplicativo para impedir disparos por abuso do cadastro.

## POST /v1/nutri/events/ingest

Entrada `{ "event": ... }`: cadastro normalizado ou mensagem da Evolution.
Um cadastro vem do webhook autenticado do servidor, com `kind: registration`,
`eventId`, `userId`, `phone` e `consent`. Valide o evento contra o cadastro real
e o consentimento já salvo; não confie somente nos campos recebidos.

Uma mensagem tem `kind: incoming`, `eventId`, `messageId`, `instance`, `phone`,
`text` e `command` (null ou `stop`). Resolva o usuário pelo telefone e instância
verificados, sem aceitar um ID de paciente informado no texto da conversa.

Em transação:

1. Persista/recupere o evento por chave única. Uma repetição não cria nova tarefa.
2. Para `command: stop`, revogue a autorização imediatamente, invalide reservas
   pendentes e retorne confirmação uma única vez, mesmo se houver trabalho em curso.
3. Cadastro autorizado novo → `welcome`. Cadastros repetidos → `ignore`.
4. Remetente desconhecido/sem autorização → `ignore`, sem contexto clínico.
5. Paciente ainda não verificado → valide o código e limite tentativas; depois
   de confirmado retorne uma resposta fixa. Código incorreto não libera contexto.
6. Usuário verificado/ativo → `assistant` com contexto autorizado mínimo.

Exemplo para a IA:

```json
{
  "eventId": "evo:nutri:message-demo-0001",
  "userId": "patient-demo-0001",
  "phone": "5511999999999",
  "action": "assistant",
  "verified": true,
  "consentActive": true,
  "message": "Como registro meu almoço?",
  "context": {
    "displayName": "Ana",
    "approvedGoal": "Manter o diário alimentar",
    "approvedPlanSummary": "Somente informações revisadas pelo profissional",
    "recentDiarySummary": "Somente dados autorizados deste paciente"
  },
  "history": [{ "role": "user", "content": "Bom dia" }]
}
```

Outras respostas:

- `{ "action": "ignore" }` para duplicatas ou eventos sem resposta.
- `action: welcome`, mesma identidade, `consentActive: true`; pode ter
  `verified: false`. O fluxo gera texto fixo sem dados pessoais.
- `action: reply`, identidade, `verified: true`, `consentActive: true`, `text`
  para respostas fixas revisadas, como confirmação do vínculo.
- SAIR: `action: reply`, identidade, `consentActive: false`, `optOutPersisted: true`.
  Essa exceção permite apenas a confirmação de cancelamento, uma vez.

O endpoint deve permitir retomar eventos que falharam antes de reservar um
envio, sem repetir eventos já aceitos ou com envio incerto. Serialize mensagens
por paciente para preservar ordem de histórico e limites de frequência.

## POST /v1/nutri/dispatches/reserve

Entrada: `{eventId, userId, phone, kind, candidate}`. O candidato é texto não
confiável: uma saída de IA não é autorização de envio ou de tratamento clínico.

Em transação, resolva o evento original e confirme identidade, telefone, vínculo,
instância configurada pelo servidor, autorização atual e ausência de reserva
anterior. Para resposta clínica ou alteração de dieta, retenha o candidato para
revisão humana; não libere prescrição automática. Verifique limites de frequência
e a exceção estrita da única confirmação de cancelamento. O cliente não pode
escolher outro paciente, a instância ou o estado de autorização.

Crie uma reserva exclusiva e durável. Duplicatas/bloqueios retornam
`{ "approved": false }` com HTTP 200. Falhas de autorização retornam 401/403.

```json
{
  "approved": true,
  "dispatchId": "dispatch-demo-0001",
  "eventId": "evo:nutri:message-demo-0001",
  "userId": "patient-demo-0001",
  "phone": "5511999999999",
  "instance": "nutri",
  "text": "Texto revisado e autorizado para envio",
  "expiresAt": "2026-11-01T12:00:30Z"
}
```

A validade é curta (por exemplo 30 s) e a resposta deve corresponder ao relógio
atual. Candidato retido para revisão retorna `approved: false` e fica numa fila
de atendimento, que deve existir no servidor.

**Limite de concorrência:** uma revogação entre a resposta desta reserva e o
POST externo da Evolution ainda pode deixar uma mensagem em trânsito. Para
garantia estrita, mova o envio para um worker do próprio backend que serialize
revogação e despacho; este fluxo com envio direto não promete atomicidade
entre dois serviços. Nenhum envio subsequente deve ser autorizado após SAIR.

## POST /v1/nutri/dispatches/result

Entrada: `{dispatchId, status: "accepted" | "uncertain", providerMessageId}`.
Atualização idempotente vinculada à reserva. Não criar nova mensagem.

- `accepted`: a Evolution respondeu com ID; **não significa entrega ou leitura**.
- `uncertain`: erro, timeout ou resposta sem ID. Não reenviar automaticamente.
  A Evolution pode ter aceitado a mensagem antes da falha de rede.

O backend deve marcar para reconciliação reservas sem resultado (queda do n8n
após o envio, por exemplo). Não liberar nova tentativa apenas por expirar a
reserva. Para confirmar entrega/leitura, implemente depois eventos de status
da Evolution em fluxo separado.

Retorno `{ "ok": true }`. Mantenha um registro operacional mínimo, com retenção
definida, sem expor chaves, dados de outras pessoas ou payloads completos em logs.

## Garantias que dependem do backend

Deduplicação durável, cancelamento persistente, revisão humana, verificação do
telefone, histórico, filas de recuperação e integração com os registros do app
**não estão implementados pelo arquivo JSON**. São responsabilidades do servidor;
veja acima o que a implementação piloto cobre. O fluxo só valida as respostas
do contrato e bloqueia envio quando faltam os campos necessários.
