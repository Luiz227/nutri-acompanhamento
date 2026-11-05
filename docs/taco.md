# TACO brasileira offline

Dados: NEPA/UNICAMP, Tabela Brasileira de Composição de Alimentos (TACO),
4ª edição revisada e ampliada, Campinas, 2011.
Publicação e planilha oficial: https://nepa.unicamp.br/publicacoes/
O aviso de reprodução com atribuição acompanha o aplicativo em
`assets/data/TACO-NOTICE.txt`; a licença do código não substitui a da fonte.

O arquivo original está em `tool/data/taco/taco_4ed.xlsx`. Para regenerar o
catálogo, execute `python tool/import_taco.py` com openpyxl instalado.
O importador verifica o SHA-256 e não modifica a planilha. A origem, o hash,
as linhas e os marcadores originais são preservados no JSON gerado.

Dos 597 registros, 591 são pesquisáveis. Os IDs 450, 457, 458, 516, 517 e 591
não têm energia utilizável e ficam fora do registro alimentar para evitar
que calorias desconhecidas sejam apresentadas como zero. Cinco células
inconsistentes são registradas em `source_anomalies` e tratadas como ausentes.
Traços, NA, análises em reavaliação e células vazias permanecem desconhecidos.
Açúcares totais, trans totais, vitaminas D e B12 não são inferidos.

Valores por 100 g da parte comestível; minerais em mg, vitamina A em µg RAE.
O aplicativo escala os valores pelo peso informado em gramas. Não presume
densidade, mililitros, pesos de unidades ou medidas caseiras. A busca manual
ignora acentos, preserva preparações e mostra atribuição no detalhe. Não
alimenta o resolvedor automático de refeições sem pesos de porções verificados.

A fonte pode ser desativada nas configurações de fontes alimentares. Os
identificadores `taco:<id>` evitam colisões com registros de outras tabelas.
O catálogo fica dentro do aplicativo, sem servidor ou chave de acesso.
Na prévia, `ENABLE_SUPABASE_FOOD_SEARCH=false` desativa o servidor de tabelas
não configurado; o padrão do projeto permanece true para instalações com servidor.
