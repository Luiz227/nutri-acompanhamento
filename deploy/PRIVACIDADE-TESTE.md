# Informações de privacidade da versão de teste

Atualizado em 05/11/2026 — fluxo de cadastro e registros pelo WhatsApp. O operador que publica esta distribuição é responsável
pelo servidor e pelo tratamento dos dados. Os autores do OpenNutriTracker original
não operam este piloto. Antes de usar com pacientes, o responsável deve informar
sua identidade, contato, fornecedores e condições efetivas de tratamento.
Este documento não declara conformidade jurídica ou clínica de produção.

O diário principal permanece no dispositivo. O vínculo WhatsApp usa credencial
individual no armazenamento seguro, separada por perfil. O APK não contém
segredos de serviço do n8n, Evolution ou IA.

Ao autorizar e tocar em Conectar, seu número e versão/data da autorização são
enviados ao servidor escolhido. O evento de boas-vindas segue ao n8n, à Evolution
e ao WhatsApp/Meta. Responder pelo WhatsApp com o código exibido no app confirma
o vínculo; antes disso não se libera contexto do paciente.

Na versão atual, ao autorizar o acompanhamento no cadastro, número, altura,
peso inicial, data de nascimento e objetivo informado são enviados ao servidor.
As anotações de refeições, água, peso e observações propostas na conversa só
são salvas após a resposta CONFIRMAR. Elas são sincronizadas automaticamente
no app e até 200 anotações recentes ficam no armazenamento seguro por perfil.
O administrador configura a origem da API em `config/mobile.json`, sem segredos;
o app não pede esse endereço ao usuário e não envia tokens a uma nova origem
apenas porque a configuração pública mudou.

Com IA habilitada, o contexto autorizado e até oito mensagens recentes podem
ser enviados ao provedor configurado no n8n (OpenAI nesta referência). Cada
fornecedor e a hospedagem têm políticas/logs próprios que o operador deve informar.
O prompt não substitui acompanhamento profissional.

SAIR ou Cancelar acompanhamento bloqueia novos envios; mensagem em trânsito
pode chegar. Cancelar não exclui automaticamente cadastro, histórico ou mensagens
já recebidas. O usuário precisa de um canal com o responsável para solicitar
acesso/exclusão antes de qualquer piloto real.

Códigos ficam como hashes e expiram ou são invalidados após uso. O histórico
conversacional é limpo depois de 30 dias; cadastro e reservas persistem até
exclusão pelo responsável. A aplicação não criptografa o volume: o operador
precisa proteger disco, backup e acesso ao Easypanel. O servidor evita logs
de payloads e tokens; o fluxo desativa dados de execução no n8n, sem controlar
os logs dos outros fornecedores.

Use dados fictícios e seu próprio número na validação inicial.

A versão 0.3 também guarda o nome de preferência, estado das perguntas iniciais, autorização específica, horários e controle de envio de lembretes de água. O paciente pode responder NÃO, PARAR LEMBRETES ou SAIR; o diário confirmado recente e a preferência de nome são enviados ao provedor de IA para continuidade da conversa.
