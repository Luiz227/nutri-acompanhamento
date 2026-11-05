# Nutri Acompanhamento — versão de teste

Derivado do [OpenNutriTracker](https://github.com/simonoppowa/OpenNutriTracker),
com autoria e histórico preservados, sob [GNU GPLv3](LICENSE).
Veja [créditos e alterações](NOTICE.md) e [documentação original](README.upstream.md).

## O que está preparado

**Fluxo atualizado:** cadastro com WhatsApp → boas-vindas → conversa pelo WhatsApp
→ confirmação do registro → atualização automática no aplicativo. O usuário
não precisa preencher endereço de servidor. Veja [o fluxo completo](deploy/FLUXO-WHATSAPP.md).

- Aplicativo Android em português brasileiro, TACO offline e tela
  **Configurações → Acompanhamento no WhatsApp**.
- APK de teste instalável diretamente, sem Play Store. Android 8 ou superior.
- Servidor de teste publicável no Easypanel pelo Dockerfile da raiz (porta 8080).
- Vínculo por código, credencial individual por instalação/perfil, consentimento,
  resumo opcional do diário, cancelamento e reservas de envio persistentes.
- Fluxo n8n para Evolution API v2, conexão por QR Code/Baileys.

**Ainda é uma versão para testes controlados**, sem publicação automática em
produção. Não inclui versão web do aplicativo, prescrição clínica ou sincronização
completa de todos os dados. O servidor entrega uma API, não a interface Flutter
no navegador. SQLite usa volume persistente e uma réplica; não escale horizontalmente.

## Publicar e testar

Siga [deploy/EASYPANEL.md](deploy/EASYPANEL.md). O Dockerfile da raiz publica
somente o servidor. O APK é compilado separadamente, com Flutter 3.44.6, e fica
na área de releases ou pode ser entregue junto com sua fonte correspondente.

1. Publique o servidor no Easypanel, configure volume e segredos próprios.
2. Importe [integrations/n8n/nutri-evolution.json](integrations/n8n/nutri-evolution.json).
3. Configure no n8n o servidor, Evolution, instância e credenciais da IA.
4. Instale o APK no seu Android e abra a tela de acompanhamento.
5. Informe seu WhatsApp com 55/DDD e autorize durante o cadastro; o endereço é configurado pelo administrador.
6. Responda no WhatsApp com o código de seis dígitos mostrado no app.
7. Converse pelo WhatsApp e responda CONFIRMAR às anotações. Consulte Registros do WhatsApp no app.

Com `AI_RESPONSES_ENABLED=false`, as respostas são fixas para testar o caminho
completo. Com `true`, o servidor permite a conversa geral da IA do n8n;
isso não é validação clínica. A IA é instruída a não prescrever ou alterar
tratamentos, e alguns temas clínicos recebem encaminhamento fixo. Não há fila
de revisão profissional nesta versão. Use dados fictícios antes de qualquer
piloto real e defina o atendimento humano necessário.

## Compilar APK

Os passos reproduzíveis estão em [deploy/APK.md](deploy/APK.md). Nunca compartilhe
a chave privada de assinatura. Um APK deve ser acompanhado da fonte correspondente
ao mesmo commit/tag, inclusive scripts de compilação e avisos de licença.

## Dados e privacidade

O diário principal continua no dispositivo. Ao autorizar, o cadastro é enviado
ao servidor, n8n e Evolution. Os registros confirmados na conversa são salvos
no servidor e sincronizados no aplicativo. Ao habilitar IA, o contexto autorizado
e o histórico recente podem ir ao provedor configurado.
Veja [deploy/PRIVACIDADE-TESTE.md](deploy/PRIVACIDADE-TESTE.md).

## Testes

```text
cd server
python -m unittest -v test_app
```

```text
node --test integrations/n8n/test/*.test.mjs
flutter analyze --no-pub
flutter test --concurrency=1 test/unit_test/nutri_bridge_client_test.dart test/unit_test/taco_food_test.dart test/unit_test/brazilian_portuguese_test.dart test/unit_test/search_products_usecase_test.dart
```

Os testes não substituem a validação do Docker no Easypanel, importação do n8n,
conexão do WhatsApp e instalação no aparelho real. Esses serviços exigem seus
endereços e credenciais e não são publicados pelo ato de criar este repositório.
