# Agente nutricional: aplicativo + n8n + Evolution API

Arquivo para importar: **nutri-evolution.json** (um workflow com 21 nós).

**Estado: arquivo gerado e testado localmente; ainda não instalado nem executado
em uma instância real do n8n.** Esta distribuição inclui `server/app.py` e a
tela Configurações → Acompanhamento no WhatsApp. Siga `deploy/EASYPANEL.md`
na raiz para publicar e conectar os serviços. A IA tem respostas fixas por
padrão; `AI_RESPONSES_ENABLED=true` libera conversa geral, sem revisão clínica.
O fluxo bloqueia o envio enquanto as conexões não forem configuradas.

## O que este fluxo faz

1. Recebe do servidor do aplicativo o cadastro com autorização explícita.
2. Consulta esse servidor para verificar o evento e autorizar boas-vindas.
3. Envia boas-vindas genéricas pela Evolution, solicitando o código do aplicativo.
4. Recebe mensagens de texto individuais pela Evolution.
5. Solicita ao servidor a confirmação do vínculo, o estado de autorização e
   o contexto exclusivo daquele paciente. SAIR é processado antes da IA.
6. Para usuários verificados, usa a IA para conversar em português brasileiro.
7. Antes de cada envio, solicita uma reserva exclusiva ao servidor e confere
   o destinatário, o evento, a instância e a validade dessa autorização.
8. Salva no servidor a aceitação pela Evolution ou a incerteza de envio.

Na versão 2, a IA propõe refeições, água, peso e observações. O servidor valida
os dados e só grava após CONFIRMAR do paciente. O aplicativo sincroniza os
registros automaticamente enquanto aberto. Nutrientes vêm apenas da TACO,
quando há correspondência exata do alimento. Consulte
`deploy/FLUXO-WHATSAPP.md` na raiz para o cadastro sem endereço de servidor.
Não inclui lembretes agendados, interpretação de fotos/áudio ou prescrição de dietas.
Lembretes periódicos exigem um fluxo separado com horários e limites definidos.

## Configuração no n8n

1. No n8n, escolha **Import from File** e selecione `nutri-evolution.json`.
2. Mantenha o workflow desativado durante a configuração.
3. Crie cinco credenciais **Header Auth**, cada uma com seu próprio segredo:

| Nome usado no arquivo | Cabeçalho | Valor |
|---|---|---|
| Nutri - entrada do servidor | X-Nutri-App-Secret | segredo exclusivo servidor → n8n |
| Nutri - entrada Evolution | X-Nutri-Evolution-Secret | segredo exclusivo Evolution → n8n |
| Nutri - API do aplicativo | Authorization | Bearer + token de serviço restrito |
| Nutri - Evolution (apikey) | apikey | chave da instância Evolution |
| Nutri - IA (Authorization) | Authorization | Bearer + chave da API da IA |

4. Selecione as credenciais nos nós correspondentes. Os nomes são referências,
   não credenciais já existentes; nenhum segredo está embutido no arquivo.
5. No nó **Configurar conexões**, informe as URLs HTTPS do servidor e da
   Evolution, o nome da instância e um modelo disponível na sua conta.
   O nó de IA usa `https://api.openai.com/v1/chat/completions`; não depende de
   um modelo específico. Outro provedor exige adaptar esse nó e seu parser.
6. Após implementar e testar o backend, altere `enabled: false` para `true`.
7. Teste exclusivamente com conta e número seus. Publique o workflow somente
   após os testes. As URLs de produção são diferentes das URLs de teste.

Este arquivo usa somente Webhook, Code, If, HTTP Request e Sticky Note,
sem instalar nós comunitários. Os tipos/versões estão no JSON; a importação
e a execução precisam ser conferidas na versão do seu n8n.

## Evolution API

Integração de referência: Evolution API **v2**, envio por
`POST /message/sendText/{instance}`, corpo `{number, text, linkPreview}`.
Antes de configurar, confirme a versão instalada e o tipo de conexão.
Este envio de texto é voltado à conexão por QR Code/Baileys. Uma instância
ligada à API oficial exige adaptar o envio inicial a templates e suas regras;
este JSON não implementa envio de templates.

No webhook da instância configure:

- URL de produção: `https://SEU-N8N/webhook/nutri-evolution-inbound`.
- Evento: `MESSAGES_UPSERT` apenas.
- `byEvents: false`; não acrescente `/messages-upsert` ao caminho.
- `base64: false`; nesta versão só há texto.
- Cabeçalho `X-Nutri-Evolution-Secret`, igual à credencial de entrada.

Se sua versão não permitir cabeçalhos no webhook, use um intermediário que
autentique a origem e encaminhe o segredo. **Não remova a autenticação.**
Não encaminhe toda a conta ou histórico: eventos de grupos, mensagens próprias,
status, históricos e identificadores `@lid` são ignorados. Suporte a LID exige
resolução autenticada para número pelo servidor; não se deve tratar LID como telefone.

## Ligação com o aplicativo

O Flutter deve enviar o cadastro para **seu servidor autenticado**, e não guardar
nenhuma das chaves acima. O servidor valida o usuário e consentimento, cria um
ID estável e um código de vínculo temporário exibido no aplicativo, e envia:

```json
{
  "eventId": "registration:exemplo-0001",
  "userId": "patient-demo-0001",
  "phone": "5511999999999",
  "consent": {
    "granted": true,
    "version": "2026-11-01",
    "at": "2026-11-01T12:00:00Z"
  }
}
```

Destino: `POST https://SEU-N8N/webhook/nutri-app-registration`, com a credencial
do servidor. Este exemplo usa dados fictícios. O envio inicial não contém
nome, peso, dieta ou condições clínicas. O servidor pode carregar contexto
somente depois de verificar o vínculo e a autorização do paciente.

## Testes e limites da verificação

Com Node 22:

```text
node integrations/n8n/build-workflow.mjs
node --test integrations/n8n/test/*.test.mjs
```

Os testes não enviam mensagens e não chamam IA. Verificam validação, comandos,
filtragem, isolamento de contexto, limites de resposta, reservas de envio,
sintaxe dos nós e caminhos simulados do JSON exportado. Não comprovam a
persistência, a identidade ou a deduplicação do backend ainda inexistente.

O workflow desativa o armazenamento de dados de execução no n8n. O operador
também precisa revisar logs do proxy, da Evolution e do provedor de IA,
controle de acesso, retenção e cópias de segurança. `store: false` na chamada
da IA não é uma promessa de ausência de logs ou de retenção pelo provedor.

## Referências verificadas

- n8n Webhook: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- Evolution DTO de envio atual: https://github.com/EvolutionAPI/evolution-api/blob/main/src/api/dto/sendMessage.dto.ts
- Evolution webhooks: https://github.com/evolution-foundation/evolution-docs/blob/main/docs/02-Configuration/Webhooks.md
- OpenAI Chat Completions: https://platform.openai.com/docs/api-reference/chat/create

A documentação antiga da Evolution usa `textMessage.text`; o DTO atual usa
`text`. Este fluxo usa o segundo formato. Confirme no seu servidor instalado.
