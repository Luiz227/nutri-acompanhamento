# Verificação física — 10/11/2026

Dispositivo: Samsung Galaxy A03s (SM-A037M), Android 13. APK ARM32 2.6.1-nutri-teste, versionCode 1075, mesma assinatura da versão anterior. Não publicamos capturas de tela, tokens, dados do perfil, número de telefone ou identificador do aparelho.

## Cenário reproduzido

A versão anterior falhava ao ler HiveEncryptionTag com BAD_DECRYPT. A leitura não destrutiva não recuperou a chave antiga. Após autorização explícita do usuário, os dados locais do pacote Nutri foram limpos uma única vez. O usuário refez o cadastro e vinculou o WhatsApp.

Com o vínculo já ativo, foram executadas duas rodadas independentes:

1. Encerrar o processo com am force-stop.
2. Iniciar a atividade principal com am start -W.
3. Aguardar a inicialização e verificar os logs apenas do processo do Nutri.
4. Conferir visualmente a tela inicial.

Ambas passaram: abertura concluída, tela inicial exibida e ausência de BAD_DECRYPT, erro de integridade do Hive ou exceção não tratada. Os dados cadastrados permaneceram disponíveis entre as reaberturas. Não houve nova limpeza.

## Limites

O teste confirma a correção no cenário do Galaxy após reiniciar o cadastro. Não afirma recuperação dos dados locais antigos nem cobertura de todos os modelos de aparelho. Dados do servidor não foram apagados pela limpeza local. O teste não enviou mensagens de WhatsApp, não chamou IA e não validou fotos/áudios ao vivo; essa função continua dependendo da API 7 e do workflow 0.6 publicados separadamente.
