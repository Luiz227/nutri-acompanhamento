# Fotos, áudios, calorias e PDF — versão 0.7 / API 8

## Atualizar

1. No Easypanel, no serviço nutri-api, implante a branch main usando o Dockerfile da raiz e mantenha o volume /data. Não apague o banco. O Dockerfile instala ReportLab automaticamente; não precisa criar um serviço separado para PDF.
2. Confirme /healthz com apiVersion: 8. Em 10/11/2026, a API pública do operador ainda estava na versão 6; a nova função não está ativa apenas por baixar este JSON.
3. No n8n, desative o workflow antigo e importe Nutri-v0.7-configurado.json. Os caminhos de webhook são os mesmos; não deixe dois fluxos ativos com essas rotas.
4. Confira as referências às credenciais existentes. OpenAI nativa nos nós Consultar IA, Ler foto com IA e Transcrever áudio. Credencial apikey da Evolution em Baixar mídia da Evolution, Enviar pela Evolution e Enviar PDF pela Evolution. Credencial da nutri-api nos nós do servidor. Os dois webhooks conservam seus segredos próprios. O arquivo configurado referencia IDs de credenciais existentes, sem incluir chaves.
5. Confira Configurar conexões: HTTPS da nutri-api e Evolution, instância Nutrição exata e modelo de conversa com imagens/JSON. A transcrição usa gpt-transcribe. Ative o workflow após a API 8 estar publicada.
6. A versão 2.6.1 do APK já é compatível. Não precisa reinstalar o aplicativo nem refazer cadastro para esta atualização do fluxo.

## Foto e áudio

Uma foto de refeição passa por autorização do paciente, download da própria Evolution e descrição visual. A legenda e os textos/áudios enviados em sequência são agrupados por paciente. A IA identifica alimentos e porções; o servidor consulta TACO ou rótulos disponíveis, calcula os nutrientes e salva na categoria de refeição indicada. A resposta ao usuário contém kcal, proteínas, carboidratos e gorduras. O modelo não fornece valores nutricionais ao banco.

A foto não pesa comida. Os pesos visuais e as medidas médias são identificados como estimativas. Quando não é possível reconhecer alimento ou preparo, a assistente pede um esclarecimento curto. Uma foto ilegível não gera um registro inventado. Sem referência compatível, não há promessa de calorias exatas.

Áudios de até três minutos são convertidos pela Evolution 2.3.7 para MP4 e transcritos. A persistência de mensagens e a conversão de áudio da Evolution precisam funcionar para buscar o arquivo pelo ID. Não há download de URLs arbitrárias enviadas pelo usuário. As chamadas de IA consomem a conta do operador.

## PDF

O usuário pode pedir “Quero sugestões de alimentação em PDF” ou “Quero meu PDF”. O servidor usa perfil, objetivo e metas atuais do aplicativo, nome e preferências já coletadas. Se faltar informação essencial, a conversa coleta antes de gerar. Não repete dados presentes no perfil.

A IA devolve sugestões estruturadas; o servidor valida e diagrama um documento privado de duas páginas: nome, objetivo, meta já existente no app quando disponível, quatro refeições, alternativas, lista de compras e dicas práticas. O PDF não cria nem altera a meta calórica e não é uma prescrição clínica. Restrições informadas devem ser respeitadas; o servidor também bloqueia incompatibilidades conhecidas com leite/lactose, ovos, amendoim e glúten. Isso não substitui a conferência dos rótulos nem garante cobertura de todos os alérgenos.

O documento é enviado como application/pdf pelo endpoint sendMedia da Evolution, em base64. Não há link público com dados do paciente. Primeiro vai a mensagem curta; depois, o arquivo. A autorização e o destinatário são verificados antes do envio de cada parte. Duplicatas do mesmo evento não geram outro envio e falhas incertas não são repetidas automaticamente. SAIR bloqueia partes pendentes; “Não quero PDF” impede o documento pendente sem cancelar todo o acompanhamento.

As sugestões do PDF não são refeições consumidas e não são lançadas no diário. Pessoas menores ou situações clínicas que exigem adaptação profissional seguem o encaminhamento do fluxo em vez de receber uma dieta automática.

O PDF fica no banco privado da API associado ao envio e é removido pela limpeza de retenção após 30 dias. n8n/Evolution/OpenAI têm suas próprias configurações de retenção e logs. O operador deve manter acesso e backups protegidos.

## Teste controlado

Com seu próprio número já vinculado:

- Envie uma foto nítida com a legenda “meu almoço” e, em seguida, uma informação adicional. Confira kcal/macros e a categoria no app aberto.
- Envie um áudio curto descrevendo alimento e refeição. Confira se o fluxo transcreve e agrupa os detalhes, sem duplicar o lançamento.
- Peça sugestões em PDF e responda somente o que faltar nas preferências. Confira o recebimento como documento.
- Peça um PDF e cancele antes da parte do arquivo: nenhum documento pendente deve ser autorizado.

O arquivo guia-alimentar-exemplo.pdf é uma demonstração visual com nome e dados fictícios; não é o plano real de nenhum usuário.

## Validação local

```text
python -m pip install -r server/requirements.txt
python -m unittest discover -s server -p "test*.py"
node integrations/n8n/build-workflow.mjs
node --test integrations/n8n/test/*.test.mjs
```

Os testes locais usam serviços simulados: não enviam WhatsApp nem chamam IA. O PDF de demonstração foi renderizado e conferido visualmente. A composição com textos no limite também foi verificada para manter duas páginas. A importação/execução no n8n real e a validação de mídia com as credenciais do operador continuam necessárias. O Dockerfile foi atualizado; não foi possível executar um build Docker local nesta estação.
