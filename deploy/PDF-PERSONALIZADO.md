# Conversa personalizada e PDF - 0.9 / API 10

Reimplante nutri-api no Easypanel a partir de main. Em /healthz verifique apiVersion 10. Importe Nutri-v0.9-configurado.json no lugar do workflow anterior; confira as credenciais reconhecidas, publique/ative o novo e desative o anterior para não duplicar webhooks. O APK 2.6.1 permanece compatível, sem reinstalação ou limpeza de dados.

## O que muda

Após confirmar o WhatsApp e informar o nome, quem tiver objetivo no cadastro recebe uma abertura personalizada com esse objetivo. A assistente pergunta o que a pessoa gosta ou evita comer, guarda a resposta por usuário e só depois pergunta sobre os lembretes de água. A resposta sobre preferências não é autorização de lembretes. O pedido de sugestões em PDF continua opcional.

As preferências seguem para menuPreferences.foodPreferences e não se perdem durante o questionário. Idade, atividade, gênero, peso, altura e metas vêm do perfil sincronizado; dados ausentes não são inventados. Alergias e restrições ainda são verificadas. O nome pode ser alterado sem reiniciar as perguntas ou mudar lembretes.

Quem já concluiu a apresentação não precisa refazer o cadastro. Pode pedir sugestões em PDF pelo WhatsApp: o questionário já existente coleta rotina e preferências. A abertura personalizada nova aparece para novas apresentações; nada apaga ou reinicia os dados de quem já usa.

## Documento

Duas páginas A4, cabeçalho verde com formas em verde e dourado, fundo claro, nome e data, objetivo atual, cartões de refeições, trocas, hidratação e compras. Modelo visual adaptado da referência fornecida pelo usuário. Conteúdo variável por pessoa; o PDF de exemplo público tem dados fictícios e não representa um plano prescrito para Luiz.

Cinco opções: café, lanche da manhã opcional, almoço, lanche da tarde e jantar. O servidor aceita também as quatro refeições do fluxo anterior, mas o fluxo novo gera as cinco opções. Não inclui metas inventadas pelo modelo; apenas metas válidas já configuradas no app podem aparecer. O envio permanece privado via WhatsApp após solicitação, sem link público do documento de pacientes.

## Validação

77 testes do servidor e 30 do workflow passaram localmente. Conferência visual do exemplo e do caso de textos longos em duas páginas. Sem chamadas de IA ou mensagens reais durante os testes. A implantação no servidor do usuário e um teste real após a atualização continuam necessários. Não exige novo APK nem apaga os registros anteriores.
