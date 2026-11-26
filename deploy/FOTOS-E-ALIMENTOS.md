# Atualizar reconhecimento dos alimentos e fotos

## Servidor

No Easypanel, implante a branch `main` do serviço `nutri-api`, preservando o volume `/data` e todas as variáveis. Confira `apiVersion: 28` em `/healthz`. O APK permanece compatível.

A busca passa a oferecer nomes de alimentos da TACO e da POF, com equivalências revisadas para pratos brasileiros. As referências continuam sendo os dados já importados do IBGE, TACO e demais fontes existentes. Não foram inventados valores nutricionais nem substituídas bases por respostas numéricas da IA. Preparos e ingredientes distintos não são intercambiáveis.

## n8n — atualizar somente a leitura da foto

1. Abra o nó **Preparar leitura da foto** no fluxo que você já utiliza.
2. Dentro do código JavaScript, localize a função `function visionPrompt(...)`.
3. Substitua somente essa função pelo conteúdo de `integrations/n8n/atualizar-leitura-foto.js`. Preserve a declaração inicial e a linha `return [{json:visionPrompt(...)}];` que fica depois da função. Essa linha mantém os nomes dos nós e o modelo configurado no seu fluxo.
4. Salve e publique a alteração no n8n. Preserve as credenciais, os domínios e a configuração de instância.
5. Teste uma foto com acompanhamentos separados e outra com um prato misto. Compare alimento, categoria e pesos aproximados registrados no site.

Alternativamente, `integrations/n8n/nutri-evolution.json` contém o fluxo completo gerado, desativado e sem segredos. Ao importar esse arquivo, é necessário selecionar suas credenciais e configurar conexões antes de publicar. Evite manter dois fluxos ativos com os mesmos webhooks.

## O que mudou

- Nomes equivalentes e ordem das palavras preservam as referências brasileiras, sem adivinhar o prato por uma palavra isolada.
- Cuscuz de milho pronto não usa a referência de cuscuz de trigo; preparações secas/cruas não são escolhidas para um alimento cozido sem indicação explícita.
- O prompt visual pede revisão de identidade e porção, distingue receitas mistas de acompanhamentos e evita contar novamente ingredientes de baião de dois, galinhada e arroz carreteiro.
- Ingredientes ocultos, variantes regionais e cortes de carne não são tratados como conhecidos sem evidência.
- Componentes incertos permanecem sem cálculo e geram um pedido curto de foto aproximada. Os totais do dia ficam parciais e não mostram déficit calórico como se todos os alimentos fossem conhecidos.

Os testes verificam a seleção das referências e o processamento dos dados. Eles não medem acurácia do modelo em fotografias reais. A validação visual após a atualização deve usar as fotos que falharam anteriormente. Não há garantia de reconhecer todo alimento ou medir peso por imagem; as porções continuam estimadas.
