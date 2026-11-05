# Português brasileiro na prévia

Esta cópia inclui `lib/l10n/intl_pt.arb`, com os textos em português brasileiro.
O código-base de idioma é `pt` para compatibilidade com o seletor existente;
o nome exibido é “Português (Brasil)”. Tags `pt-BR` e `pt_BR` resolvem para esse
idioma. Cadastros novos começam em português, mesmo em um emulador em inglês.
Uma preferência de idioma já escolhida pode continuar sendo alterada nas
configurações. A instalação da prévia existente recebe a escolha pt-BR no Android.

Traduções de produtos dependem da fonte. Open Food Facts é consultado também
com `product_name_pt`. O catálogo Supabase continua usando os nomes originais
até a disponibilidade de traduções em português ser verificada. Nomes fornecidos
pelo usuário, nomes comerciais e nomes dos exemplos não são traduzidos pela UI.

## Preparação e revisão

A primeira versão usa tradução automática local com revisão manual de cadastro,
navegação, configurações, metas, exclusões, privacidade e avisos de saúde.
Antes de distribuição comercial, ainda é necessária revisão editorial das telas
secundárias, textos longos e descrições de atividades por um revisor brasileiro.
Os testes conferem mensagens presentes, parâmetros, plurais, datas e nomes de
produtos. Eles não comprovam qualidade linguística integral.

Ferramentas de autoria ficam fora do aplicativo, na pasta `.tools` do workspace.
Nenhum modelo, serviço de tradução ou dependência Python é executado no app.
O modelo offline é Argos Translate en→Portuguese (Brazil) 1.9, derivado de
OPUS-MT. Crédito: Jörg Tiedemann e Santhosh Thottingal, “OPUS-MT — Building open
translation services for the World”, EAMT 2020. Modelo original sob CC BY 4.0.
Inferência: CTranslate2 (MIT); tokenização: SentencePiece (Apache-2.0).
Índice do modelo: https://github.com/argosopentech/argospm-index

## Verificação

```text
flutter gen-l10n
dart run tool/check_locales.dart
flutter test --concurrency=1 test/unit_test/brazilian_portuguese_test.dart test/unit_test/app_locales_test.dart test/unit_test/off_request_locale_test.dart test/unit_test/app_locale_test.dart test/unit_test/shipped_locales_test.dart
```

Gere novamente o APK e use `Abrir-App.cmd` na raiz do workspace para instalar a
atualização sem apagar os dados existentes.
