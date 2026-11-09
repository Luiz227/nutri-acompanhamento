# Atualização 0.6: fotos, áudio e abertura do aplicativo

## Instalação

1. No Easypanel, implante novamente a nutri-api com a branch main e o volume /data existente. Não apague o banco. /healthz deve mostrar apiVersion: 7.
2. Desative o fluxo antigo no n8n antes de ativar o novo: os dois usam os mesmos caminhos de webhook.
3. Importe o JSON desta versão. Preserve as cinco credenciais existentes (quatro Header Auth e uma OpenAI nativa). Selecione a credencial OpenAI também em Ler foto com IA e Transcrever áudio; a Evolution em Baixar mídia da Evolution; a credencial da nutri-api nos dois nós de autorização/conclusão da mídia.
4. Configure as URLs/instância/modelo em Configurar conexões e habilite enabled. Na cópia configurada da release, URLs e referências às credenciais de Luiz já estão preenchidas, sem valores secretos.
5. Na Evolution 2.3.7 mantenha webhook de produção, header secreto e MESSAGES_UPSERT. Não precisa ativar Base64 no webhook. A rota /chat/getBase64FromMediaMessage busca a mensagem pelo ID: a persistência de mensagens da Evolution precisa estar habilitada. A conversão de voz OGG para MP4 usa o suporte de conversão de áudio da própria Evolution. Se falhar, verifique o erro desse nó; o fluxo não inventa uma transcrição.
6. Instale nutri-teste-arm32.apk por cima da versão anterior no Galaxy A03s. Não desinstale nem limpe os dados.

## Teste

Com o número já vinculado, envie “No lanche comi 1 maçã”. A API converte a unidade média em 150 g (IBGE, PDF página 160), calcula os nutrientes com a referência alimentar compatível e identifica o resultado como estimativa.

Envie uma foto nítida da refeição com legenda “meu almoço”. Em seguida envie uma informação adicional. O servidor aguarda a leitura da mídia e o intervalo de silêncio de 8 segundos, junta o conteúdo por paciente e responde em partes. Não é pesagem: gramas inferidos pela imagem são estimativas visuais. Ingredientes/preparos não identificáveis exigem esclarecimento.

Envie um áudio curto, de até 3 minutos. O modelo gpt-transcribe recebe o arquivo convertido; a conversa e leitura de fotos usam o modelo de Configurar conexões. Todas essas chamadas usam a credencial OpenAI nativa já existente. São chamadas pagas conforme a conta do operador. Erros de formato, conversão ou IA resultam em pedido para reenviar, não em registros inventados.

Fotos/áudios só são baixados após vínculo e consentimento ativos. A API limita dez mídias em cinco minutos por paciente, deduplica o ID antes da interpretação e guarda apenas o texto interpretado, não os arquivos. O conteúdo passa pela Evolution, n8n e OpenAI; as políticas de retenção desses serviços continuam aplicáveis. Mensagens de visualização única, grupos, status, stickers, documentos e vídeos não entram neste caminho.

## Abertura

A interface aparece antes de abrir o banco e os plugins. Mostra uma mensagem acolhedora e a etapa atual em português. Integrações opcionais de saúde e idioma têm limites de espera; a sessão remota do Supabase não é restaurada neste APK sem login Supabase. A animação do logo tem uma saída independente do término da animação.

Se a abertura continuar parada, a nova tela informa a etapa: envie essa captura ou conecte o Galaxy por USB para capturar o erro. Os testes locais cobrem canais sem resposta e animação desativada; não substituem a reabertura no aparelho afetado. Não apagamos nem recriamos a chave de criptografia ou o diário como solução para um erro.

## Medidas domésticas

server/portions.py contém um conjunto inicial revisado, com fonte e página: maçã, laranja, banana-prata, pão francês, caqui, figo, mamão papaia e fatia de maçã. Não é cobertura de todas as medidas/alimentos. Referência: IBGE, Pesquisa de Orçamentos Familiares 2008–2009, Tabela de Medidas Referidas para os Alimentos Consumidos no Brasil (2011): https://biblioteca.ibge.gov.br/visualizacao/livros/liv50000.pdf.

Para tamanhos/medidas sem referência, a assistente pede um esclarecimento curto. Não converte todo prato, colher ou fruta em um peso arbitrário. Gramas explícitos têm prioridade; calorias e macros continuam calculados no servidor, não pelo modelo.
