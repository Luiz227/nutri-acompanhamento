# Foto da refeição sem descrição detalhada — 0.8 / API 9

## Atualizar

1. No Easypanel, implante novamente a nutri-api com a branch main e o volume /data existente. Não apague dados. Confirme apiVersion: 9 em /healthz.
2. Desative o workflow antigo no n8n e importe Nutri-v0.8-configurado.json. Os caminhos e referências às credenciais existentes foram mantidos. Confira os nós OpenAI e Evolution e ative o fluxo novo.
3. Mantenha um modelo que aceite imagem e saída estruturada JSON Schema, como o gpt-5.4-mini já configurado. O nó Ler foto com IA usa um contrato estrito de alimentos, gramas e confiança.
4. Não precisa reinstalar o APK 2.6.1. Áudios, PDF, lembretes e mensagens em partes continuam no mesmo fluxo.

## Mudança no caminho da foto

Antes, o modelo descrevia o prato como um texto longo e uma segunda conversa decidia o que registrar. Essa conversa podia pedir confirmação e os nomes compostos dificultavam a busca. Agora, a análise visual retorna componentes separados com porções estimadas e nível de confiança. O servidor valida o resultado, associa os alimentos às referências nutricionais e registra a foto reconhecível diretamente, sem a etapa de conversa pedir confirmação ou solicitar a descrição de todo o prato.

A autorização, o vínculo, a espera por mensagens em sequência e a deduplicação continuam no servidor. O conteúdo estruturado não aceita calorias, nutrientes, IDs de paciente ou códigos de alimento fornecidos pelo modelo. O servidor escolhe as referências e calcula os valores. SAIR antes da reserva impede o registro/envio.

## Erro nutricional corrigido

O caso de arroz branco estava encontrando arroz carreteiro pela busca aproximada. Arroz branco e arroz branco cozido agora resolvem para Arroz, tipo 1, cozido (TACO 3). Batatas fritas, inclusive no plural, resolvem para Batata, inglesa, frita (TACO 93). Preparações compostas não são usadas como equivalentes de alimentos simples sem que seus ingredientes apareçam na descrição.

Bife bovino grelhado sem corte identificável usa uma referência derivada da média de cortes comuns grelhados disponíveis na TACO, não um corte inventado. O registro guarda os IDs de referência e marca a estimativa. O app já aceita esses nutrientes e identifica o alimento como estimado.

A frase do alimento pode conter “em tiras/fatiado” sem impedir o cálculo. Legumes identificáveis devem vir separados da análise visual; não são agrupados numa descrição longa e ambígua.

## Resposta e categoria

Uma foto identificável pode ser enviada sozinha. A categoria usa a legenda ou mensagens do mesmo grupo; se não houver, é inferida pelo horário: café 5h–10h59, almoço 11h–14h59, lanche 15h–18h59, jantar nos demais horários. Essa inferência fica identificada nos dados. Uma indicação explícita de café da manhã, almoço, lanche ou jantar tem prioridade.

A resposta tem uma introdução curta, um bloco por alimento com kcal/macros e o total estimado. O aviso sobre estimativa aparece uma vez por foto. Não há pedidos de código de barras para a comida do prato. Os blocos curtos evitam cortes no meio de uma frase.

Molhos ou componentes de baixa confiança ficam como observações, sem peso ou nutrientes inventados. Se algum componente ficar de fora, a resposta informa um subtotal, não apresenta esse número como o total completo do prato. Se nenhuma parte puder ser identificada, pede outra foto mais nítida. A fotografia não permite garantir peso, ingredientes ocultos ou calorias exatas.

Frases explícitas de não consumo, foto de exemplo, receita ou pergunta nutricional não geram consumo automático. Mensagens como “foi meu café da manhã” e “comi metade”, no mesmo grupo da foto, são consideradas antes do registro.

## Testar

Envie uma nova foto nítida do prato inteiro, sem escrever os alimentos. Confira a resposta com estimativas e os alimentos no app. Opcionalmente, use somente uma legenda curta como “meu almoço”. Teste também enviar a foto e depois “foi meu café da manhã”: a categoria precisa permanecer café da manhã.

Esta versão não recalcula nem altera lançamentos antigos. Evite manter um lançamento incorreto anterior e repetir o mesmo consumo sem revisar o diário.

## Verificação

75 testes do servidor e 30 do workflow passaram. O teste de sincronização Flutter (6 casos) também passou, incluindo uma referência derivada de carne grelhada, valores e categoria, sem duplicação. O prato do relato foi reproduzido em dados sintéticos para verificar arroz, bife, batata, legumes e molho incerto.

Os testes locais não enviaram WhatsApp nem chamaram o modelo de visão. Ainda é necessário testar a imagem real no n8n do operador após atualizar o servidor e importar o fluxo. O Dockerfile foi atualizado para incluir o novo módulo; o build Docker não foi executado localmente.

Referência nutricional: TACO/NEPA/UNICAMP, 4ª edição, 2011, já distribuída e atribuída no projeto. Contrato de saída: https://developers.openai.com/api/docs/guides/structured-outputs.
