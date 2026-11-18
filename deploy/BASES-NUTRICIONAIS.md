# Bases nutricionais da GarfoFala

## Como outros sistemas fazem

| Sistema | O que informa publicamente |
| --- | --- |
| Gluti | A IA identifica alimentos e estima a porção. TACO e USDA FoodData Central fornecem os valores de referência, e a pessoa pode corrigir o registro. [Metodologia oficial](https://www.gluti.com.br/metodologia-analise-alimentar-ia) |
| MetaboLab | Identifica alimentos e estima porções pelo tamanho aparente do prato, talher ou embalagem. Cita TACO e TBCA e permite revisar o resultado. [Descrição oficial](https://metabolab.app.br/) |
| Cronometer | Usa bases especializadas como NCCDB, USDA, CNF e CoFID. Para produtos de marca, diferencia dados de rótulo e registros revisados. [Fontes oficiais](https://support.cronometer.com/hc/en-us/articles/360018239472-Data-Sources) |
| MyFitnessPal | Mantém uma combinação de registros adicionados pela equipe e pela comunidade, com indicação em itens revisados. [Origem dos dados](https://support.myfitnesspal.com/hc/en-us/articles/360032271252-Where-does-MyFitnessPal-get-its-food-data) |

O servidor calcula cada nutriente multiplicando a referência por 100 g pela porção em gramas e dividindo por 100. O modelo estima ou interpreta a porção e sugere o nome para consulta. O servidor escolhe a referência e soma o prato. Medidas caseiras continuam usando as referências revisadas existentes.

## Fontes ativas

- **TACO**, 591 registros utilizáveis. Prioridade para correspondências brasileiras e receitas já revisadas.
- **Open Food Facts**, rótulos por código de barras. Se não houver um rótulo completo, o produto fica sem cálculo.
- **USDA Foundation Foods**, 364 registros. **SR Legacy**, 7.793. **FNDDS 2021–2023**, 5.431. [Arquivos oficiais](https://fdc.nal.usda.gov/download-datasets/)
- **CoFID 2021**, 1.502 registros úteis. [Arquivo oficial](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid)

Total: 15.090 registros complementares, com possíveis versões do mesmo alimento. Identificadores, fonte e link são preservados em cada correspondência. Referências internacionais são assinaladas como aproximações. Valores ausentes continuam desconhecidos. A TBCA não foi redistribuída em massa nesta versão devido às restrições de uso comercial indicadas pela própria base. [Exemplo de aviso da TBCA](https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?n0REd3kv7e86D%2BViXWYUnQ%3D%3D=dI7IS7n8zOD4eXKl8GXjwg%3D%3D)

Os quatro arquivos originais são identificados em tool/import_nutrition_catalog.py. Informações de licenciamento e transformação estão em assets/data/FOOD-COMPOSITION-NOTICE.txt.
