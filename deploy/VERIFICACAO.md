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
