# Verificação da distribuição de teste

Preparação em 05/11/2026:

- 43 testes direcionados de cliente HTTPS, TACO, português e busca aprovados.
- 2 testes de interface: consentimento obrigatório e bloqueio após troca de perfil.
- 13 testes do servidor: vínculo, expiração, autenticação, cancelamento, persistência
  e reserva concorrente de envios aprovados.
- 18 testes locais do workflow n8n aprovados, incluindo simulação dos ramos.
- Análise estática Flutter sem problemas.
- Compilação release assinada, sem minificação: APKs ARM32, ARM64 e x86_64.
- LICENSE original preservada; comparação SHA-256 idêntica.
- Revisão automatizada dos candidatos à publicação não encontrou padrões de
  credenciais. Isso não equivale a uma auditoria de segurança completa.

Ainda exigem validação no ambiente do operador: importação na versão real do
n8n, domínio/HTTPS do Easypanel, persistência do volume, Evolution conectada,
mensagem real e instalação no aparelho físico. A CI também verifica build e
saúde do container; consulte seu resultado, não presuma que passou.

O arquivo local de senha e o certificado da assinatura são excluídos do Git.
Um backup privado deles é necessário para futuras atualizações do APK.

## Atualização v0.2.0-teste.1

22 testes de servidor e 18 testes do workflow aprovados. Cinco testes Flutter específicos da conexão, persistência, isolamento de perfil e interface aprovados; análise Flutter sem problemas. O build usa versionCode base 69, mantendo a assinatura do teste anterior. O teste real de WhatsApp depende da configuração do operador.


## Atualização v0.3.0-teste.1

32 testes de servidor e 21 testes do workflow aprovados; 6 testes Flutter específicos aprovados. Análise Flutter sem problemas. Novos testes cobrem autorização e cancelamento de lembretes, idempotência de horários, nome persistente, proporção dos nutrientes, total parcial e categoria explícita de refeição importada no app. Não houve envio real de lembrete nem chamada paga à IA nesta verificação. O operador deve atualizar API, workflow e APK e validar no ambiente real.

## Agrupador e quebrador de mensagens

38 testes de servidor e 22 testes de workflow aprovados. Cobrem união de mensagens concorrentes, isolamento entre pacientes, SAIR durante a espera, partes ordenadas e não repetidas, interrupção após falha e simulação do loop com duas partes. Não foi executado envio real no n8n/Evolution; o teste de ponta a ponta depende da implantação pelo operador.

## v0.4.0-teste.1

48 testes do servidor, 22 do workflow e 7 testes Flutter específicos aprovados. Cobrem registro automático sem prompt de confirmação, macros determinísticos, aproximação identificada sem trocar comum por integral, fonte externa simulada e sódio convertido para mg, convite único e autorização para sugestões, bloqueio terapêutico, importação OFF/estimativas e divisão por parágrafo. Consulta pública de exemplo ao Open Food Facts retornou HTTP 200 com nutrientes; não houve envio de dados de paciente. Não foi executado ciclo real no n8n/Evolution nem chamada paga ao modelo nesta verificação.

## v0.4.1-teste.1

15 testes Flutter específicos aprovados, incluindo 4 novos de inicialização e os testes de privacidade dos relatórios. Análise Flutter sem problemas; 48 testes de servidor aprovados após simplificar os avisos de estimativa. O placeholder de relatórios vazio entre aspas foi confirmado sem imprimir o valor de credenciais. Nenhum dispositivo Android estava conectado; a validação física de reabertura permanece necessária após atualizar sem desinstalar.
