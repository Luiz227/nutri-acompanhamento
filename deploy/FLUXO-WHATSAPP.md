# Cadastro no aplicativo, atendimento pelo WhatsApp

**Versão atual 0.6 / API v7:** veja [fotos, áudios e abertura](MIDIA-E-ABERTURA.md). Histórico: o registro agora é automático, sem confirmação. A apresentação, as fontes e as sugestões foram atualizadas. Consulte [Conversa natural](CONVERSA-NATURAL.md); seções históricas abaixo descrevem versões anteriores.

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


## Agrupar mensagens e dividir respostas (API v4)

Atualize a nutri-api pelo Git e importe o fluxo atualizado. O APK v0.3 continua compatível; esta mudança não exige outro APK.

- O endpoint interno `/v1/nutri/events/collect` acumula mensagens comuns de um paciente verificado por 8 segundos após a última chegada. Cada mensagem seguinte reinicia essa janela. Execuções anteriores terminam sem resposta; somente a última processa o texto unido em ordem de chegada.
- O buffer é persistente no SQLite e separado por paciente. Não usa dados estáticos globais do n8n nem exige Redis. Não há garantia de recuperação automática de mensagens interrompidas por reinício durante a espera; uma nova mensagem permite retomar pendências. Duplicatas do mesmo evento não geram outra resposta.
- Boas-vindas, código de vínculo, perguntas iniciais, confirmações e comandos são processados sem a espera. SAIR cancela as mensagens ainda acumuladas antes da IA. Perguntas de nome/autorização continuam uma por vez.
- Até 32 mensagens / 16 mil caracteres são agrupados. Se a janela exceder o limite, a mensagem excedente é processada separadamente, sem truncar ou descartar as anteriores. Cada mensagem individual mantém o limite de 4 mil caracteres.
- A divisão usa parágrafos, linhas e espaços, com até 700 caracteres por parte. O texto completo mantém seu limite atual de 1800 caracteres. O nó Pausa entre partes espera 2 segundos antes de continuar o loop.
- O servidor prepara as partes autorizadas; o n8n revalida cada uma, envia uma por vez e salva o aceite ou a incerteza. Não há reenvio automático de partes com resultado incerto. Uma falha interrompe as demais partes. SAIR bloqueia partes ainda não iniciadas; uma requisição já em trânsito pode chegar.
- O webhook Evolution responde imediatamente; a execução pode continuar por alguns segundos. O request de coleta tem timeout de 60 segundos. O serviço deve operar com uma réplica, como a configuração SQLite atual.
- Textos do buffer e das partes são removidos pela limpeza após 30 dias. Evite exportar execuções com cabeçalhos secretos. As credenciais são referenciadas, nunca embutidas no JSON entregue.

Teste de ponta a ponta: envie “No café da manhã comi arroz cozido”, em seguida “50 gramas” em menos de oito segundos. Deve haver uma única consulta à IA com as duas mensagens. Teste uma resposta nutricional longa e observe as partes na ordem, separadas por dois segundos. PARAR LEMBRETES cancela apenas lembretes; SAIR encerra o acompanhamento.
