# Abertura e armazenamento — correção 0.6.1

O diagnóstico por USB no Galaxy A03s identificou BAD_DECRYPT ao ler HiveEncryptionTag, antes da abertura do banco. O vínculo do WhatsApp usava FlutterSecureStorage com opções padrão, enquanto o diário usava SharedPrefs/CBC. Nessa biblioteca, sharedPreferencesName separa os valores, mas não isola as chaves de proteção. A inicialização/migração de um cliente podia afetar o outro.

## Correção

- Chave do banco em storageNamespace nutri_core_v2; vínculo WhatsApp em nutri_whatsapp_v2. Ambas usam resetOnError=false e migração com backup.
- Leitura do formato anterior por código nativo que usa somente chaves já existentes. Não gera, remove nem substitui chaves antigas. Antes da tentativa, preserva uma cópia criptografada das preferências no diretório privado noBackupFilesDir do próprio app.
- Uma chave recuperada só é copiada para o armazenamento novo depois de Hive abrir e verificar todos os conjuntos de caixas do perfil, com crashRecovery=false.
- Falha de recuperação gera hive_legacy_key_unreadable e tela em português. Não reinicializa banco, não apaga arquivos e não cria chave nova sobre dados existentes.
- Vínculos antigos que ainda possam ser descriptografados são copiados para o namespace separado.

## Limite real

No aparelho afetado, a tentativa de leitura não conseguiu recuperar a chave anterior. A correção impede o conflito nos próximos cadastros, mas não consegue recriar uma chave criptográfica perdida. A tentativa preservou os arquivos originais. Uma cópia criptografada sem a chave não garante recuperação. Depois desse diagnóstico, o usuário autorizou explicitamente limpar os dados locais e recomeçar. A limpeza foi executada apenas no pacote do Nutri; a primeira inicialização do armazenamento novo passou no Galaxy. Nenhum dado do servidor foi apagado por essa limpeza.

Não limpe dados nem desinstale para tentar recuperar informações locais. Se o usuário decidir recomeçar, explique primeiro que a limpeza apaga dados que existam apenas no aparelho e obtenha autorização explícita. Dados no servidor são separados; refazer um cadastro não garante a importação automática de um vínculo anterior.

A versão mantém a mesma assinatura do APK e incrementa o build para 75. A API e o fluxo da versão 0.6 não mudam. Os testes locais específicos de abertura, vínculo, consentimento e proteção contra substituição de chave passaram; a análise Flutter não apresentou problemas. O diagnóstico físico comprovou a falha de recuperação e a primeira inicialização limpa, não a recuperação dos registros antigos. Em 10/11/2026, após o novo cadastro e vínculo WhatsApp feitos pelo usuário, duas reaberturas completas no Galaxy passaram: am force-stop, am start -W, chegada visual à tela inicial e ausência de BAD_DECRYPT, HiveStorageIntegrityException ou Unhandled Exception nos logs do processo. Nenhuma limpeza adicional foi feita. Veja VERIFICACAO-GALAXY.md.
