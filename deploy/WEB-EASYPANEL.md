# Site e contas web no Easypanel

O mesmo serviço publica o site, a API usada pelo aplicativo e a integração com o n8n. A página inicial fica em `https://SEU-DOMINIO/`. O banco SQLite e as contas ficam no volume persistente `/data`.

## Atualizar o serviço existente

1. No serviço **testee / nutri-api**, mantenha o repositório `Luiz227/nutri-acompanhamento`, branch `main`, caminho de build `/` e Dockerfile `Dockerfile`.
2. Mantenha o volume **nutri-dados** montado em **/data**, uma réplica, porta interna **8080** e o domínio com HTTPS ativo.
3. Preserve as variáveis e os segredos que já conectam a API ao n8n.
4. Acrescente as variáveis abaixo em **Ambiente**, usando a chave atual da Evolution no painel.

```dotenv
DATA_DIR=/data
EVOLUTION_API_URL=https://testee-evolution-api.flgmd4.easypanel.host
EVOLUTION_API_KEY=COLE_A_CHAVE_DA_EVOLUTION_NO_EASYPANEL
EVOLUTION_INSTANCE=Nutrição
PUBLIC_BASE_URL=https://testee-nutri-api.flgmd4.easypanel.host
```

`PUBLIC_BASE_URL` deve ser exatamente a origem HTTPS usada para abrir o site, sem caminho adicional. Se adicionar um domínio próprio ao site, atualize essa variável para o novo endereço. A chave em `EVOLUTION_API_KEY` é a credencial usada para enviar mensagens pela Evolution. Ela fica somente no servidor.

5. Clique em **Implantar**.
6. Abra `/healthz`. Confira `apiVersion: 24` e `webAuthConfigured: true`. Esse indicador confirma a configuração local das credenciais. O recebimento do código valida a conexão real com a Evolution.
7. Abra o domínio do serviço para acessar o site. O endereço informado no aplicativo e em `backendBaseUrl` do n8n continua atendendo as rotas de API.

## Cadastro, acesso e recuperação

- **Criar conta** pede o mesmo perfil do aplicativo, o número com DDD e uma senha de 12 a 128 caracteres, com pelo menos um caractere especial. A pessoa também confirma a senha e autoriza o acompanhamento.
- O servidor envia um código de seis dígitos pelo WhatsApp. A pessoa digita o código **no site**. Ele é válido por dez minutos e aceita até cinco tentativas.
- Depois da confirmação, a pessoa acessa o painel com perfil, metas, totais de hoje e diário por data. Um número já verificado no aplicativo é vinculado ao mesmo paciente e histórico.
- **Entrar** aceita telefone e senha. A sessão usa cookie Secure, HttpOnly e SameSite, válido por sete dias. A senha e o token da sessão não são gravados no localStorage.
- **Esqueci minha senha** envia outro código pelo WhatsApp. Após informar o código e a nova senha no site, a pessoa entra novamente. As sessões web anteriores são encerradas. A troca da senha web preserva o acesso do aplicativo e os registros.
- **Sair da conta** encerra a sessão do navegador. A autorização de acompanhamento pelo WhatsApp é mantida.
- O reenvio tem intervalo de um minuto. São aceitas até cinco solicitações de código por hora por telefone e dez tentativas de login por quinze minutos.

Senhas usam Argon2id com salt individual. O banco guarda hashes das sessões e autentica os códigos com HMAC. Os códigos são produzidos pela API, enviados diretamente pela Evolution e não dependem da geração de texto da IA. Nenhuma senha é enviada ao WhatsApp.

## n8n

O fluxo atual permanece responsável pela conversa, os registros, os PDFs e os lembretes. O envio dos códigos da conta web é feito por um processo separado da API usando a Evolution. O cadastro web confirmado aciona o webhook de cadastro já existente para iniciar ou retomar o acompanhamento.

Não é necessário importar outro fluxo n8n para adicionar o login web. Preserve `N8N_REGISTRATION_WEBHOOK`, `N8N_APP_WEBHOOK_SECRET` e `NUTRI_SERVICE_TOKEN`.

## Painel web 0.23

- **Diário** com refeições por categoria e data, nutrientes, registro manual de água, peso, alimentos e observações, edição e exclusão. A busca usa o catálogo do servidor; o código de barras consulta o Open Food Facts. Os cálculos usam o mesmo resolvedor nutricional do WhatsApp.
- **IMC** no resumo e na evolução, calculado com a última pesagem confirmada e a altura do perfil. Sem pesagens, usa o peso do perfil. Não cria pesagens históricas fictícias. A classificação adulta só aparece a partir dos 20 anos.
- **Evolução** com gráfico de peso, variação registrada, meta, histórico e períodos de 7, 30, 90 e 365 dias. Médias nutricionais usam somente os dias com refeições e valores completos; dias sem dados são identificados.
- **Perfil e metas** permite editar nascimento, gênero, altura, peso do perfil, objetivo, atividade, peso desejado e metas de calorias, macros e água. Os dados ficam disponíveis no contexto da IA.
- **Receitas e favoritos** guarda combinações por conta, calcula os nutrientes e permite adicionar uma porção ao diário. A biblioteca web é própria; não importa automaticamente receitas locais do Android.
- **Ajustes** com nome preferido, autorização e horários dos lembretes de água e exportação do perfil, biblioteca e diário em JSON.

Os registros criados, editados ou excluídos no site usam os cursores de revisão já consumidos pelo aplicativo. A atualização aparece após a sincronização do app. O site mostra os registros existentes no servidor; dados que existem somente no armazenamento local do Android não aparecem automaticamente no site. O envio de fotos e áudios continua pelo WhatsApp.

Esta versão amplia as funções web, mas não é uma cópia integral do aplicativo. Integrações nativas de saúde, múltiplos perfis locais, atividades físicas locais, importação dos formatos originais do app, scanner por câmera e configurações locais de aparência/unidades ainda não foram portados. Não conecte contas de pessoas diferentes para compartilhar uma sessão web.

## Teste após implantar

1. Crie a conta com um número que você controla e confirme o código no site.
2. Saia e entre novamente com telefone e senha.
3. Registre uma refeição pelo WhatsApp e confira a mesma data no diário web e no aplicativo.
4. Use **Esqueci minha senha**, informe o código recebido e defina outra senha.
5. Entre com a nova senha e confirme que os registros continuam disponíveis.
6. Faça uma nova implantação e entre novamente para verificar a persistência do volume.

## Validação e limites desta entrega

Os testes locais usam contas fictícias e simulam a Evolution. O recebimento real de códigos depende das credenciais e da instância conectada no seu Easypanel.

O site hospedado anteriormente em Sites é uma publicação separada. Esta entrega prepara o site para o endereço do serviço no Easypanel.
