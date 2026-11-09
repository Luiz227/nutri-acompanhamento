# Atualização 0.4: conversa natural e registro automático

## O que mudou

Refeições, água, peso e observações com dados suficientes são salvos automaticamente. Não é mais necessário responder CONFIRMAR. O aplicativo mantém o status interno confirmed por compatibilidade de sincronização; isso não implica confirmação manual.

As respostas de registro não mostram data, fuso, enumeração técnica, travessões de separação ou instruções repetidas de cancelamento. O resumo mostra kcal, proteína, carboidratos e gordura por alimento e total da refeição. Informações ausentes não são tratadas como zero.

Cada parágrafo vira uma bolha no WhatsApp, mesmo quando a resposta completa é curta. As partes têm até 420 caracteres e pausa de 2 segundos; mensagens comuns recebidas continuam sendo agrupadas por 8 segundos de silêncio. Códigos e comandos mantêm tratamento imediato.

## Alimentos, fontes e aproximações

1. Nomes exatos, sinônimos revisados e ordem de palavras são procurados na TACO local.
2. Produtos com código de barras informado pelo paciente podem ser consultados no Open Food Facts. A consulta externa recebe somente o código do produto, sem nome, telefone ou contexto do paciente. Há timeout de 5 segundos, cache de 24 horas e limite local de 10 consultas por minuto. O serviço público pode ficar indisponível.
3. Quando não há correspondência exata, pode ser usada uma referência próxima da mesma família alimentar, preservando os qualificadores de preparo disponíveis. A resposta e o aplicativo identificam expressamente a estimativa e a referência utilizada. O nome original do usuário é preservado.
4. Não se aproxima entre famílias sem relação, não se troca comum por integral e não se escolhe cru/grelhado para frango sem esclarecer o preparo. Se não houver aproximação compatível, fica uma anotação sem cálculo e é solicitada informação adicional. Não se inventam calorias.

Não há acesso automático a todas as tabelas nutricionais do mundo. Nesta versão, as fontes efetivamente integradas ao WhatsApp são TACO e Open Food Facts por código de barras. TBCA, USDA e outras fontes não estão integradas a esse agente. Dados do Open Food Facts são colaborativos, sob ODbL, não uma garantia de rótulo correto ou de ausência de alérgenos.

Referências técnicas e de atribuição:
- https://openfoodfacts.github.io/openfoodfacts-server/api/
- https://openfoodfacts.github.io/openfoodfacts-server/api/ref-cheatsheet/
- https://opendatacommons.org/licenses/odbl/1-0/

## Sugestões de alimentação

A assistente oferece sugestões uma vez no início ou após um registro alimentar. A pessoa também pode pedir uma sugestão de cardápio. Sem interesse, o diário continua normalmente.

Após aceitar, são coletados: idade adulta, objetivo e atividade, alergias/restrições/condições de saúde e rotina/preferências/orçamento. As respostas ficam no SQLite por paciente e são disponibilizadas à IA como contexto. Só depois a solicitação é enviada ao modelo.

A geração é de um exemplo flexível de refeições para adultos, considerando as informações autodeclaradas. Não calcula necessidade energética clínica, déficit ou metas de emagrecimento. Não substitui avaliação profissional, nem gera dietas terapêuticas para diabetes, doença renal, gestação/lactação, transtornos alimentares ou menores. Sugestões nunca são inseridas no diário como se tivessem sido consumidas.

Referência para orientações gerais: Guia Alimentar para a População Brasileira, Ministério da Saúde (2014):
https://www.gov.br/saude/pt-br/composicao/saps/promocao-da-saude/guias-alimentares/guias-alimentares

## Implantar

1. No Easypanel, mantenha o volume /data e as variáveis existentes. Implante a nutri-api a partir do ramo main. /healthz deve informar apiVersion 5 e mode general-ai.
2. Desative o fluxo antigo no n8n. Importe Nutri-v0.4-configurado.json, confira as credenciais selecionadas e publique. As referências de credenciais foram preservadas a partir do último arquivo enviado; os valores não estão no JSON. A credencial OpenAI é a nativa.
3. Atualize o APK sem desinstalar. No Galaxy A03s do teste, use ARM32. O APK novo importa produtos externos no diário e mostra o nome original com indicação de estimativa. APK antigo continua importando TACO, mas não esses produtos externos.
4. Teste água: envie “bebi 500 ml de água”. Deve salvar sem CONFIRMAR e responder brevemente.
5. Teste alimentação: envie alimento, peso e categoria, por exemplo “no almoço comi 100 g de peito de frango sem pele grelhado”. Deve salvar e mostrar os macros em bolhas separadas.
6. Teste sugestões: aceite a pergunta, responda a coleta e confira que a resposta respeita as preferências. Teste também NÃO e situações que exigem profissional.
7. Não compartilhe chaves ou execuções com cabeçalhos secretos. Eventos já processados não são enviados novamente ao reexecutar uma execução antiga.

Os registros antigos não são reprocessados nem corrigidos automaticamente. A edição remota de registros existentes continua fora desta versão. A API deve permanecer com uma réplica; os lembretes e o SQLite persistem no volume.


## Correção 0.4.1: reabertura do APK e aviso de aproximação

A mensagem de registro deixou de expor nomes técnicos da TACO/UNICAMP ou da referência escolhida. Quando houver aproximação, os macros são apresentados como estimados ("Para essa porção, estimei..."). A referência, a fonte e a indicação de estimativa permanecem nos dados e nos detalhes do aplicativo.

O inicializador agora ignora configuração vazia/inválida do serviço opcional de relatórios de erro, limita a espera desse serviço a cinco segundos e continua abrindo o app se o serviço falhar. Um callback tardio não monta o app duas vezes. A investigação identificou um placeholder vazio entre aspas no build anterior, incompatível com a inicialização desse SDK quando a coleta de erros estava habilitada após o cadastro.

Não foi alterada a chave do Hive, não houve limpeza do armazenamento e não se solicita desinstalação. Instale o APK novo sobre o anterior. Para o ajuste das mensagens, implante a nutri-api novamente. O fluxo n8n continua o da versão 0.4; não precisa reimportar por causa deste patch.

A correção tem teste de regressão de primeira abertura e reabertura com consentimento, configuração inválida, falha do plugin, timeout e callback tardio. Não foi validada diretamente no Galaxy do usuário, pois não há dispositivo conectado nesta estação. Se o sintoma persistir após atualizar, serão necessários logs do aparelho para identificar outra etapa da inicialização.


## Versão 0.5: perfil e metas do aplicativo no acompanhamento

O APK envia gênero informado, nascimento, altura, peso, objetivo (perder/manter/ganhar), nível de atividade e, quando definidos, peso-alvo e ritmo semanal. As metas diárias de kcal, proteína, carboidratos, gordura e água usam os mesmos serviços de cálculo/configuração da tela inicial, sem gerar outro cálculo na IA.

O perfil vai no cadastro e é atualizado ao abrir/retomar o app e durante a sincronização em primeiro plano. Só há novo envio quando os dados mudam. Uma API antiga que não confirma profileUpdated não é considerada sincronizada; a tentativa é repetida sem bloquear a importação do diário. O usuário existente não precisa refazer cadastro. O app precisa ser atualizado e aberto para enviar os novos campos; o servidor não pode adivinhar gênero ou metas que nunca recebeu.

A API valida e substitui o snapshot do perfil, preservando o restante do contexto. Campos removidos não ficam com valores antigos. Metas são identificadas como configuração/estimativa do app, não como plano profissional aprovado. A IA recebe o perfil estruturado e um resumo legível; o prompt prioriza esses dados sobre lembranças antigas.

A coleta de sugestões pula idade, objetivo e atividade já conhecidos. Quando só uma informação falta, pergunta apenas ela. Com gênero masculino informado, a pergunta de saúde não inclui gestação/amamentação. Gênero ausente/não binário usa pergunta neutra; um relato espontâneo de condição relevante continua sendo considerado, sem inferir anatomia ou diagnósticos pelo gênero.

Implante a nutri-api (healthz apiVersion 6), importe o fluxo 0.5 e selecione as credenciais existentes, e atualize o APK sem desinstalar. Não limpe o volume nem os dados locais. Depois abra o app para sincronizar antes de testar perguntas sobre objetivo/metas no WhatsApp.

PDF personalizado é uma possibilidade futura; esta versão não gera nem envia PDF. O perfil sincronizado é a base para um documento com nome, objetivo, metas e preferências reais. Um plano clínico individual precisa de definição/revisão profissional antes da emissão; um cardápio geral deve ser identificado como sugestão.
