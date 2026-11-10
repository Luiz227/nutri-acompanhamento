# Créditos e modificações

Nutri Acompanhamento é uma versão modificada de OpenNutriTracker,
de Simon Oppowa e demais contribuidores.

Origem: https://github.com/simonoppowa/OpenNutriTracker
Base: commit 1ab4940 (versão 2.5.0), histórico preservado neste repositório.
Licença do programa derivado: GNU GPL versão 3, conforme LICENSE e os avisos
originais. Não há transferência de autoria do projeto original nem alegação
de aprovação ou suporte dos autores originais a esta versão.

Modificações desta distribuição, 05/11/2026:

Atualização do fluxo de cadastro/WhatsApp: número e autorização no cadastro;
endereço configurado pelo administrador; registros de refeições, água, peso
e observações propostos pela IA e salvos somente após CONFIRMAR. Sincronização
automática no app e consulta determinística à TACO para alimentos identificados.
O código do servidor usa migração aditiva, sem excluir cadastros existentes.

- Interface em português brasileiro e suporte a nomes portugueses.
- Catálogo brasileiro TACO/NEPA/UNICAMP (2011) disponível offline, com
  atribuição e tratamento explícito de dados desconhecidos.
- Fluxo de integração n8n/Evolution e servidor de teste com SQLite persistente.
- Tela de vínculo WhatsApp, consentimento, resumo manual do diário e cancelamento.
- Nome e identificador Android de teste separados do original.
- Instruções de compilação de APK, distribuição da fonte e publicação no Easypanel.
- CI própria; automações de publicação e Weblate do projeto original desativadas
  nesta versão para não atuar em serviços dos autores originais.

A TACO tem aviso de reprodução próprio em assets/data/TACO-NOTICE.txt, mantido
separadamente. Bibliotecas e recursos de terceiros conservam suas licenças;
os avisos de bibliotecas estão na tela de licenças do Flutter.

Ao distribuir o APK, disponibilize também a fonte correspondente exata, scripts,
LICENSE e este aviso, sob GPLv3, pelo mesmo local de download. Não basta apontar
somente para o projeto original. Não publique senhas, certificados de assinatura,
tokens nem dados dos usuários. Uma versão privada precisa fornecer a fonte aos
destinatários do APK por outro meio acessível, sem impedir seus direitos GPL.

Versão 0.4: registro automático pelo WhatsApp, resumo conversacional e estimativas identificadas; integração de rótulos Open Food Facts (https://world.openfoodfacts.org), base sob Open Database License (ODbL), https://opendatacommons.org/licenses/odbl/1-0/. Não redistribuímos uma cópia da base; cada produto consultado mantém código, origem e URL. Sugestões gerais referenciam o Guia Alimentar para a População Brasileira, Ministério da Saúde (2014).

Versão 0.6: leitura de fotos/áudios pelo n8n, porções médias com referência IBGE POF 2008-2009 (Tabela de Medidas Referidas, 2011, https://biblioteca.ibge.gov.br/visualizacao/livros/liv50000.pdf), e inicialização com progresso visível. A fonte/página de cada medida permanece no registro; não redistribuímos o PDF nem afirmamos peso exato de porções estimadas.

Versão 0.6.1: isolamento das chaves locais do diário e do vínculo WhatsApp, leitura não destrutiva do formato legado e diagnóstico da falha de descriptografia. A recuperação não é garantida quando uma chave já foi perdida.

Versão 0.7: geração de PDF privado de sugestões gerais e envio pela Evolution, mantendo o registro de fotos/áudios. PDFs usam ReportLab 4.4.9, Copyright (c) ReportLab Inc., sob licença BSD (https://pypi.org/project/reportlab/4.4.9/); a instalação da dependência conserva seus avisos de licença. O exemplo distribuído usa dados fictícios.

Versão 0.8: registro direto de observações visuais estruturadas; associações de arroz simples/batata e referência estimada derivada de cortes bovinos grelhados. Médias e porções são identificadas como estimativas e mantêm a fonte TACO/NEPA/UNICAMP (2011) e IDs utilizados.
