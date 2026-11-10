# Agente nutricional: aplicativo + n8n + Evolution API

Importe **nutri-evolution.json**, gerado por build-workflow.mjs: 42 nós, desativado e sem segredos. Requer nutri-api **apiVersion 10**, Evolution **2.3.7** Baileys e uma credencial OpenAI nativa.

As verificações locais simulam os serviços. A versão nova ainda precisa ser importada/testada na instância real do operador. Leia [como atualizar e testar](../../deploy/MIDIA-E-ABERTURA.md).

## Configuração

1. Implante a nutri-api pelo Dockerfile da raiz, porta 8080 e volume /data existente.
2. Desative o workflow antigo antes de ativar o novo, pois os caminhos são iguais.
3. Selecione as credenciais abaixo. Não cole segredos no JSON, no GitHub ou no chat.

| Credencial | Tipo | Uso |
|---|---|---|
| Nutri - entrada do servidor | Header Auth, X-Nutri-App-Secret | Webhook Cadastro do aplicativo |
| Nutri - entrada Evolution | Header Auth, X-Nutri-Evolution-Secret | Webhook Mensagem da Evolution |
| Nutri - API do aplicativo | Header Auth, Authorization: Bearer TOKEN | Todos os HTTP Requests para a nutri-api |
| Nutri - Evolution (apikey) | Header Auth, apikey | Baixar mídia da Evolution e Enviar pela Evolution |
| Nutri - OpenAI | OpenAI nativa | Consultar IA, Ler foto com IA e Transcrever áudio |

4. Em Configurar conexões defina enabled=true, backendBaseUrl, evolutionBaseUrl, instance exata e model com suporte a imagens/Chat Completions JSON. A cópia configurada na release contém somente URLs e referências às credenciais já existentes do operador, nunca seus valores.
5. Na Evolution, configure a URL de produção /webhook/nutri-evolution-inbound, MESSAGES_UPSERT e o mesmo header secreto esperado pelo webhook n8n. Webhook by Events desligado. Base64 não é necessário no webhook.
6. No servidor use o webhook /webhook/nutri-app-registration e segredo exclusivo de entrada do cadastro. AI_RESPONSES_ENABLED=true libera a IA.
7. Ative o workflow e teste com seu próprio número vinculado pelo código do app.

## Foto automática (0.8)

Leia [FOTO-AUTOMATICA.md](../../deploy/FOTO-AUTOMATICA.md): análise visual estruturada, busca nutricional corrigida e registro direto de fotos reconhecíveis. O nó de conversa é dispensado nesse caminho, evitando a pergunta de confirmação. Imagens continuam sendo estimativas, e componentes incertos não recebem nutrientes inventados.

## PDF de sugestões (0.7)

Leia [FOTOS-AUDIOS-PDF.md](../../deploy/FOTOS-AUDIOS-PDF.md). O servidor gera um PDF privado de duas páginas com sugestões estruturadas da IA; o nó Enviar PDF pela Evolution entrega como documento. Sugestões não são lançadas como consumo no aplicativo.

## Caminho da conversa

Cadastro e vínculo por código precedem o uso de dados pessoais. O servidor decide autorização, contexto do paciente e respostas de onboarding. Nome, preferências de lembretes, perfil e metas do aplicativo chegam à IA; dados disponíveis não devem ser perguntados novamente.

Textos são agrupados por paciente após oito segundos de silêncio. Fotos e áudios recebem uma autorização persistente e única antes do download/interpretação. A mídia é buscada na Evolution pelo ID, nunca por uma URL fornecida pelo usuário. Texto enviado durante a interpretação aguarda a mídia, até o limite de 90 segundos. Falhas pedem reenvio sem inventar consumo.

Fotos JPEG/PNG/WebP de até 8 MB são descritas pelo modelo de conversa, preservando a legenda. Porções visuais são estimativas. Áudios de até três minutos e 20 MB passam pela conversão MP4 da Evolution e transcrição gpt-transcribe. Mensagens de visualização única, grupos, status, documentos, vídeos e stickers não são interpretados. A persistência de mensagens da Evolution precisa estar habilitada para buscar arquivos pelo ID.

A IA propõe registros estruturados. O servidor valida os dados, converte medidas caseiras revisadas do IBGE e calcula kcal/proteínas/carboidratos/gorduras a partir de TACO ou rótulos Open Food Facts. Registros válidos são salvos automaticamente, sem pedir CONFIRMAR. O app sincroniza enquanto aberto e ao retornar ao primeiro plano. Datas e categoria explícitas são preservadas; fonte/estimativas permanecem nos dados.

Parágrafos viram mensagens separadas, enviadas em sequência com pausa de dois segundos. Cada parte é reautorizada no servidor. Envios incertos não são repetidos automaticamente. SAIR cancela a autorização e bloqueia partes ainda não enviadas; também funciona quando recebido como fala transcrita.

Lembretes só são enviados com autorização específica. Horários padrão: 9h, 12h, 15h e 18h de Brasília; preferências e cancelamento são persistentes. Sugestões gerais exigem coleta de preferências e não constituem prescrição clínica. O PDF personalizado respeita a coleta de preferências e é enviado como documento, sem URL pública.

## Privacidade e verificação

A API armazena o texto interpretado, não os arquivos de mídia. Fotos e áudios passam por Evolution, n8n e OpenAI, sujeitos às políticas desses serviços. O workflow desativa salvamento de execuções; o operador deve cuidar dos logs e backups de toda a infraestrutura. store:false não promete ausência de retenção pelo provedor.

Execute:

```text
node integrations/n8n/build-workflow.mjs
node --test integrations/n8n/test/*.test.mjs
py -3 -m pip install -r server/requirements.txt
py -3 -m unittest discover -s server -p "test*.py"
```

Os testes não chamam IA nem enviam WhatsApp. Cobrem autorização, deduplicação, cancelamento, cálculos, isolamento, agrupamento e os caminhos simulados do workflow. O teste integrado com mídia real e a reabertura física do Galaxy continuam necessários.

## Referências

- [Evolution 2.3.7: download e conversão](https://github.com/EvolutionAPI/evolution-api/blob/2.3.7/src/api/integrations/channel/whatsapp/whatsapp.baileys.service.ts)
- [OpenAI: transcrição](https://developers.openai.com/api/docs/guides/speech-to-text)
- [OpenAI: imagens](https://developers.openai.com/api/docs/guides/images-vision)
- [IBGE: medidas referidas](https://biblioteca.ibge.gov.br/visualizacao/livros/liv50000.pdf)

A versão 0.9 usa o modelo visual personalizado e cinco opções de refeições no PDF, com preferências persistidas na apresentação. Consulte deploy/PDF-PERSONALIZADO.md.
