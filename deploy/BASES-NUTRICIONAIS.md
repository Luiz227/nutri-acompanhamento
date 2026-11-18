# Bases nutricionais da GarfoFala

## Como outros sistemas fazem

| Sistema | O que informa publicamente |
| --- | --- |
| Gluti | A IA identifica alimentos e estima a porção. TACO e USDA FoodData Central fornecem os valores de referência, e a pessoa pode corrigir o registro. [Metodologia oficial](https://www.gluti.com.br/metodologia-analise-alimentar-ia) |
| MetaboLab | Identifica alimentos e estima porções pelo tamanho aparente do prato, talher ou embalagem. Cita TACO e TBCA e permite revisar o resultado. [Descrição oficial](https://metabolab.app.br/) |
| Cronometer | Usa bases especializadas como NCCDB, USDA, CNF e CoFID. Para produtos de marca, diferencia dados de rótulo e registros revisados. [Fontes oficiais](https://support.cronometer.com/hc/en-us/articles/360018239472-Data-Sources) |
| MyFitnessPal | Mantém uma combinação de registros adicionados pela equipe e pela comunidade, com indicação em itens revisados. [Origem dos dados](https://support.myfitnesspal.com/hc/en-us/articles/360032271252-Where-does-MyFitnessPal-get-its-food-data) |

O servidor calcula cada nutriente multiplicando a referência por 100 g pela porção em gramas e dividindo por 100. O modelo estima ou interpreta a porção e sugere o nome para consulta. O servidor escolhe a referência e soma o prato. Para medidas caseiras, também consulta a POF pelo código do alimento, preparo e tipo de medida.

## Fontes ativas

- **TACO**, 591 registros utilizáveis. Prioridade para correspondências exatas.
- **IBGE POF 2008–2009**, 1.971 fichas de alimentos e preparações e 11.801 linhas de medidas referidas. São aceitos nomes sem ambiguidade e medidas compatíveis com o preparo, com prioridade para as medidas previamente revisadas. Valores ausentes ficam desconhecidos. [Composição](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2008_2009/Tabelas_de_Composicao_Nutricional_dos_Alimentos_Consumidos_no_Brasil/) · [Medidas caseiras](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2008_2009/Tabela_de_Medidas_Referidas_para_os_Alimentos_Consumidos_no_Brasil/)
- **Open Food Facts**, rótulos por código de barras. Se não houver um rótulo completo, o produto fica sem cálculo.
- **USDA Foundation Foods**, 364 registros. **SR Legacy**, 7.793. **FNDDS 2021–2023**, 5.431. [Arquivos oficiais](https://fdc.nal.usda.gov/download-datasets/)
- **CoFID 2021**, 1.502 registros úteis. [Arquivo oficial](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid)

Total: 15.090 registros complementares, com possíveis versões do mesmo alimento. Identificadores, fonte e link são preservados em cada correspondência. Referências internacionais são assinaladas como aproximações. Valores ausentes continuam desconhecidos. A TBCA não foi redistribuída em massa nesta versão devido às restrições de uso comercial indicadas pela própria base. [Exemplo de aviso da TBCA](https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?n0REd3kv7e86D%2BViXWYUnQ%3D%3D=dI7IS7n8zOD4eXKl8GXjwg%3D%3D)

Os quatro arquivos originais são identificados em tool/import_nutrition_catalog.py. Informações de licenciamento e transformação estão em assets/data/FOOD-COMPOSITION-NOTICE.txt.

## Ativar a POF no teste

Reimplante a API a partir do Dockerfile na raiz. Durante o build, o importador baixa os dois arquivos oficiais do IBGE, confere seus hashes e monta o catálogo usado pela API. O repositório distribui o importador. O catálogo gerado é obtido diretamente da edição oficial durante o build. Depois da implantação, confira `apiVersion: 16` em `/healthz`.

O fluxo n8n atualizado envia medidas como concha, colher de sopa, colher de servir e xícara. Teste com “Comi uma concha média cheia de feijoada no almoço”. O registro usa 225 g como estimativa e calcula os valores nutricionais com a referência da POF. Para testes fora do Docker, instale `xlrd==2.0.2`, rode `python tool/import_ibge_pof.py server/food_pof.json` e inicie a API.
