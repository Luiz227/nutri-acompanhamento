# Cadastro no aplicativo, atendimento pelo WhatsApp

## Para o usuário

1. Instala o APK e preenche seu cadastro.
2. Informa o WhatsApp com 55/DDD e autoriza o acompanhamento.
3. Ao concluir, o cadastro é salvo localmente e enviado automaticamente ao servidor.
4. Recebe boas-vindas e confirma a posse do número respondendo com o código do app.
5. A partir daí, conversa pelo WhatsApp: refeições, água, peso e observações.
6. A IA propõe a anotação. O servidor mostra os dados e pede CONFIRMAR ou
   CANCELAR REGISTRO. Somente CONFIRMAR grava o registro.
7. Os registros aparecem automaticamente no app ao abri-lo/retomá-lo e a cada
   45 segundos enquanto aberto. Não há botão obrigatório de envio/sincronização.

O usuário não informa endereço de servidor, chave de IA, n8n ou Evolution.
Quem preferir não autorizar WhatsApp pode continuar apenas com o aplicativo local.

## Para o administrador

- A API está configurada em `config/mobile.json` para
  `https://testee-nutri-api.flgmd4.easypanel.host`.
- Esse arquivo público contém somente endereço, nunca segredos. Novos cadastros
  consultam a configuração; uma conexão existente continua presa à sua origem
  original para não enviar tokens a outro servidor após uma mudança de endereço.
- `NUTRI_API_URL` é uma alternativa de compilação para fixar a origem no APK.
- Publique a versão atual da API e reimporte o JSON atualizado do n8n. No n8n,
  configure backendBaseUrl, Evolution, instância, modelo e credenciais; habilite
  `enabled: true` após configurar. O modelo deve suportar JSON mode.
- Para o agente propor registros, configure `AI_RESPONSES_ENABLED=true` na API.
  `false` continua sendo o modo de teste com respostas fixas e sem chamada à IA.
- Os segredos ficam somente no Easypanel e nas credenciais do n8n.
- Domínio externo HTTPS, destino HTTP na porta 8080; volume persistente `/data`.

Se o servidor estiver indisponível no cadastro, o app conserva uma solicitação
pendente e tenta novamente ao abrir/retomar e enquanto está aberto. O token e o
código da instalação são reutilizados: uma repetição não cria outra boas-vindas.
Um app completamente fechado não executa esse retry; antes de distribuir a
pacientes o administrador precisa deixar a infraestrutura funcionando.

## Dados e limites

- Refeições com peso explícito em gramas. Nomes exatos na TACO usam nutrientes
  da tabela e entram no diário local com ID estável. O modelo não fornece calorias.
- Alimento não identificado com precisão fica como anotação com cálculo
  nutricional pendente; não é tratado como alimento com zero calorias.
- Água em ml/l, peso em kg/g; o servidor normaliza para ml/kg. Uma leitura
  manual de peso existente no mesmo dia não é sobrescrita pelo sync do WhatsApp.
- Observações são fatos informados pelo paciente, não diagnósticos ou prescrição.
- Até 200 anotações recentes ficam no cache seguro do app; registros confirmados
  permanecem no servidor. A sincronização percorre páginas e importa registros
  nativos com IDs estáveis, evitando duplicação.
- No APK v0.3.0, a categoria informada pelo paciente (café, almoço, jantar ou lanche) tem prioridade sobre o horário de envio. Registros antigos sem categoria mantêm a regra por horário. Edição remota de registros já confirmados não faz parte desta versão.
- Há confirmação por mensagem, vínculo por código, isolamento por paciente,
  cancelamento SAIR, validação de unidades e expiração de rascunhos em 30 minutos.
  Esses controles não são uma validação clínica do modelo.

Confirme o endpoint `/healthz`, os logs da implantação e um ciclo completo com
seu próprio número antes de usar dados reais. O APK antigo continua tendo o fluxo
manual; esta atualização precisa do APK novo e do servidor/n8n atualizados.


## Versão 0.3: conversa, memória e lembretes

- Após verificar o número, o servidor pergunta como a pessoa prefere ser chamada (PULAR é permitido). Nome e preferências ficam no SQLite por paciente, sem depender só do histórico do modelo.
- Em seguida solicita SIM ou NÃO para lembretes às 09:00, 12:00, 15:00 e 18:00 de Brasília. Silêncio ou resposta ambígua não autoriza envio. Não há meta hídrica prescrita.
- ALTERAR LEMBRETES pausa os envios e permite até seis horários HH:MM; após informar horários, é necessário autorizar novamente. PARAR LEMBRETES cancela só esses envios; SAIR revoga todo o acompanhamento. ATIVAR LEMBRETES pede consentimento novamente.
- O agendador roda na API, inclusive com o app fechado, reutilizando o webhook autenticado de cadastro e o workflow do n8n. Não é necessário outro cron no n8n. A API e o volume precisam ficar ativos. Cada horário tem chave persistente; não são recuperados horários perdidos durante indisponibilidade. Entrega de mensagens depende dos serviços externos e não é garantida.
- Antes de cada despacho, são revalidados consentimento, vínculo e validade do lembrete. Uma chamada já em trânsito pode chegar após cancelamento; não há reenvio automático de despacho com resultado incerto.
- O resumo no WhatsApp mostra kcal, proteínas, carboidratos, gorduras, fibras e sódio por item e total. Valores ausentes na TACO continuam como não informados. Uma refeição com alimento desconhecido tem apenas subtotal identificado, claramente sinalizado.
- A busca usa a TACO local, nomes equivalentes revisados e contexto recente. Não consulta a internet nem estima nutrientes de alimento ausente. Marca/rótulo e variedade podem ser solicitados; não há substituição automática entre comum/integral ou com/sem gordura.
- Os registros confirmados mais recentes e as últimas mensagens dão continuidade à conversa. O histórico de conversa tem retenção de 30 dias; nome/preferências e registros persistem no volume, até política de exclusão do operador. Não é uma memória ilimitada.
- Atualize a API (healthz apiVersion 3), importe o novo fluxo e selecione a credencial nativa OpenAI já criada no nó Consultar IA. O novo APK é necessário para a categoria explícita no diário. APIs antigas/n8n antigo não emitem os novos eventos de lembrete corretamente.
- O fluxo é entregue inativo. Desative a versão antiga antes de publicar a nova para evitar conflito de webhooks. Confirme cada credencial selecionada. N8N_REGISTRATION_WEBHOOK, EVOLUTION_INSTANCE e os segredos existentes permanecem.

Teste com seu próprio número: nome → NÃO (nenhum lembrete) → ATIVAR LEMBRETES → SIM; refeição com variedade, peso e categoria → conferir nutrientes → CONFIRMAR → abrir o APK novo e conferir a categoria. Para testar o agendador, ALTERAR LEMBRETES e escolher um horário alguns minutos à frente, autorizar e depois cancelar. Não publique chaves nem dados das execuções.
