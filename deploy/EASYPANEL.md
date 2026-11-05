# Publicar o servidor de teste no Easypanel

O APK funciona no Android. O Easypanel hospeda o servidor de ligação com o n8n;
não transforma a interface Flutter em uma versão web.

1. Crie um projeto separado, como `nutri-teste`, e um serviço App `nutri-api`.
2. Fonte GitHub: `luiz227/nutri-acompanhamento`, branch `main`, Build Path `/`.
3. Builder Dockerfile, caminho `Dockerfile`.
4. Porta interna **8080**, domínio HTTPS apontando para essa porta.
5. Adicione um Mount do tipo **Volume** em `/data`. O usuário do container é
   UID/GID 10001 e precisa de escrita. Não use armazenamento efêmero.
6. Mantenha **uma réplica**: o SQLite deste piloto não suporta várias réplicas.

Não é necessário outro PostgreSQL para este servidor. O banco da Evolution é separado.

## Ambiente

```dotenv
PORT=8080
DATA_DIR=/data
NUTRI_SERVICE_TOKEN=SEU_SEGREDO_ALEATORIO_1
N8N_REGISTRATION_WEBHOOK=https://SEU-N8N/webhook/nutri-app-registration
N8N_APP_WEBHOOK_SECRET=SEU_SEGREDO_ALEATORIO_2
EVOLUTION_INSTANCE=nutri
AI_RESPONSES_ENABLED=false
```

Gere dois segredos diferentes com pelo menos 32 caracteres aleatórios num
gerenciador de senhas. Não coloque segredos no GitHub, no APK ou no chat.
`server/.env.example` é só referência; valores `CHANGE_ME` são recusados.

`AI_RESPONSES_ENABLED=false` permite testar com respostas fixas. Após validar
vínculo e SAIR, `true` libera conversa geral da IA. Prompt e filtros básicos
não garantem validação clínica; não há fila de revisão profissional neste piloto.
Sem n8n pronto, deixe `N8N_REGISTRATION_WEBHOOK` vazio para testar apenas a API.

Clique em Deploy. `https://SEU-DOMINIO/healthz` deve retornar `ok: true`.
`n8nConfigured: true` significa que o endereço foi informado, não que foi testado.

## n8n e Evolution

Importe `integrations/n8n/nutri-evolution.json`. No nó Configurar conexões, defina
`backendBaseUrl`, `evolutionBaseUrl`, `instance`, o modelo da sua conta e,
depois das credenciais, `enabled: true`. Use somente origens HTTPS, sem caminhos.

| Credencial n8n | Cabeçalho | Valor |
|---|---|---|
| Nutri - entrada do servidor | X-Nutri-App-Secret | N8N_APP_WEBHOOK_SECRET |
| Nutri - API do aplicativo | Authorization | Bearer + NUTRI_SERVICE_TOKEN |
| Nutri - entrada Evolution | X-Nutri-Evolution-Secret | terceiro segredo exclusivo |
| Nutri - Evolution (apikey) | apikey | chave da instância |
| Nutri - IA (Authorization) | Authorization | Bearer + chave do provedor |

Selecione as credenciais nos nós e publique o workflow. Na Evolution v2/Baileys,
configure `MESSAGES_UPSERT`, `byEvents: false`, sem Base64 e a URL de produção
do nó Mensagem da Evolution, com seu cabeçalho secreto. Instância igual nos três serviços.

## Teste com seu próprio número

1. Instale o APK ARM64 no Android e permita a instalação por esse navegador,
   quando solicitado pelo sistema.
2. Crie o perfil e abra Configurações → Acompanhamento no WhatsApp.
3. Informe o HTTPS da API, número com 55/DDD e autorização. Toque em Conectar.
4. Responda à mensagem recebida no WhatsApp com o código mostrado no app (10 min).
5. Toque em Verificar conexão e, opcionalmente, Enviar resumo do diário.
6. Envie uma mensagem comum. No piloto a resposta é fixa; com IA habilitada,
   use perguntas gerais e dados fictícios.
7. Envie SAIR e confirme que o acompanhamento fica cancelado no aplicativo.

## Operação

- Faça backup consistente do SQLite/volume antes de modificar o serviço.
- Banco e backup precisam de proteção do operador; a aplicação não criptografa o volume.
- Cadastro: máximo 3 por telefone e 30 totais/hora. Antes de acesso público,
  adicione proteção contra abuso por origem no proxy.
- Código: 10 minutos e até 5 tentativas. Até 20 reservas de envio por paciente/hora.
- Cada evento tem reserva única. Timeout da Evolution não gera reenvio automático;
  reservas incertas exigem reconciliação manual.
- Uma mensagem já em trânsito pode chegar após SAIR; novas reservas serão bloqueadas.
- Dados de execução do n8n são desativados, mas logs dos demais serviços precisam
  de revisão. A privacidade e o atendimento humano precisam ser definidos antes
  de testes com pacientes reais.
- Esta preparação não publica automaticamente no seu Easypanel.

Referência: https://easypanel.io/docs/services/app
