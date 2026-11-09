import 'package:flutter/material.dart';

class WhatsappSignup extends StatefulWidget {
  final void Function(String phone, bool consent) onChanged;
  final String initialPhone;
  final bool initialConsent;
  const WhatsappSignup({
    super.key,
    required this.onChanged,
    this.initialPhone = '',
    this.initialConsent = false,
  });
  static bool isValidPhone(String value) => RegExp(
    r'^55\d{10,11}$',
  ).hasMatch(value.replaceAll(RegExp(r'[\s()+.-]'), ''));
  @override
  State<WhatsappSignup> createState() => _WhatsappSignupState();
}

class _WhatsappSignupState extends State<WhatsappSignup> {
  late TextEditingController _controller;
  late bool _consent;
  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialPhone);
    _consent = widget.initialConsent;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _notify() => widget.onChanged(_controller.text, _consent);
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const SizedBox(height: 16),
      const Text('Seu acompanhamento pelo WhatsApp'),
      const Text(
        'Informe seu número. Após concluir o cadastro, você receberá uma mensagem da assistente virtual para confirmar a conexão.',
      ),
      Semantics(
        identifier: 'whatsapp-phone',
        child: TextField(
          controller: _controller,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'WhatsApp com 55 e DDD',
            hintText: '5511999999999',
          ),
          onChanged: (value) {
            _notify();
          },
        ),
      ),
      Semantics(
        identifier: 'whatsapp-consent',
        child: CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: _consent,
          onChanged: (value) {
            setState(() => _consent = value == true);
            _notify();
          },
          title: const Text('Quero receber o acompanhamento no WhatsApp.'),
          subtitle: const Text(
            'Autorizo o uso do meu cadastro e das mensagens, fotos e áudios que eu enviar para acompanhar minha alimentação, pelo servidor do aplicativo, n8n, Evolution/WhatsApp e provedor de IA configurado. As porções podem ser estimadas. Posso cancelar enviando SAIR.',
          ),
        ),
      ),
    ],
  );
}
