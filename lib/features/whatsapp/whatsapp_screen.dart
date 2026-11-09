import 'dart:async';
import 'package:flutter/material.dart';
import 'package:opennutritracker/features/whatsapp/bridge_session.dart';
import 'package:opennutritracker/features/whatsapp/whatsapp_signup.dart';

class WhatsappScreen extends StatefulWidget {
  const WhatsappScreen({super.key});
  @override
  State<WhatsappScreen> createState() => _WhatsappScreenState();
}

class _WhatsappScreenState extends State<WhatsappScreen>
    with WidgetsBindingObserver {
  late final BridgeSession _session;
  Map<String, dynamic> _data = {};
  Timer? _timer;
  bool _busy = false, _foreground = true, _consent = false;
  String _phone = '';
  @override
  void initState() {
    super.initState();
    _session = BridgeSession.current();
    WidgetsBinding.instance.addObserver(this);
    BridgeSession.changed.addListener(_load);
    _load();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 45), (_) {
      if (_foreground) _refresh();
    });
  }

  Future<void> _load() async {
    final data = _session.sameProfile
        ? await _session.load()
        : <String, dynamic>{
            'message': 'O perfil mudou. Abra esta tela novamente.',
          };
    if (mounted) setState(() => _data = data);
  }

  Future<void> _refresh() async {
    if (_busy || !_session.sameProfile) return;
    setState(() => _busy = true);
    try {
      await _session.synchronize();
      await _load();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connect() async {
    if (_busy || !_consent || !WhatsappSignup.isValidPhone(_phone)) return;
    if (!_session.sameProfile) {
      await _load();
      return;
    }
    setState(() => _busy = true);
    try {
      await _session.enroll(_phone);
      await _load();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (_foreground) _refresh();
  }

  @override
  void dispose() {
    _timer?.cancel();
    BridgeSession.changed.removeListener(_load);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final records = ((_data['records'] as List?) ?? []).reversed;
    final until = DateTime.tryParse(_data['codeUntil'] as String? ?? '');
    return Scaffold(
      appBar: AppBar(title: const Text('Registros do WhatsApp')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const Text(
              'Converse pelo WhatsApp. As anotações que você confirmar aparecerão automaticamente no aplicativo.',
            ),
            const SizedBox(height: 16),
            Text(
              _data['message'] as String? ??
                  'Seu acompanhamento ainda não foi conectado.',
            ),
            if (_data['token'] == null && _data['pending'] != true) ...[
              WhatsappSignup(
                onChanged: (phone, consent) => setState(() {
                  _phone = phone;
                  _consent = consent;
                }),
              ),
              Semantics(
                identifier: 'whatsapp-connect',
                child: FilledButton(
                  onPressed:
                      !_busy && _consent && WhatsappSignup.isValidPhone(_phone)
                      ? _connect
                      : null,
                  child: const Text('Conectar WhatsApp'),
                ),
              ),
            ],
            if (_data['verified'] != true &&
                _data['pending'] != true &&
                until != null &&
                until.isAfter(DateTime.now()))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: SelectableText(
                  'Responda no WhatsApp com este código: ${_data['code']}',
                ),
              ),
            if (_busy) const LinearProgressIndicator(),
            const SizedBox(height: 20),
            if (records.isEmpty)
              const Text(
                'Refeições, água, peso e observações confirmadas no WhatsApp aparecerão aqui.',
              ),
            for (final raw in records)
              _recordCard(context, Map<String, dynamic>.from(raw as Map)),
            if (_data['active'] == true || _data['pending'] == true)
              Semantics(
                identifier: 'whatsapp-revoke',
                child: TextButton(
                  onPressed: _busy
                      ? null
                      : () async {
                          try {
                            await _session.revoke();
                            await _load();
                          } catch (_) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                    'Sem conexão. Envie SAIR no WhatsApp para cancelar.',
                                  ),
                                ),
                              );
                            }
                          }
                        },
                  child: const Text('Cancelar acompanhamento'),
                ),
              ),
            if (_data['active'] == false && _data['token'] != null)
              Semantics(
                identifier: 'whatsapp-reconnect',
                child: TextButton(
                  onPressed: _busy
                      ? null
                      : () async {
                          await _session.storage.delete(key: _session.key);
                          await _load();
                        },
                  child: const Text('Conectar novamente'),
                ),
              ),
            const Divider(),
            const Text(
              'Assistente virtual. Dúvidas clínicas e alterações de plano devem ser tratadas com seu nutricionista.',
            ),
          ],
        ),
      ),
    );
  }

  Widget _recordCard(BuildContext context, Map<String, dynamic> record) {
    const labels = {
      'meal': 'Refeição',
      'water': 'Água',
      'weight': 'Peso',
      'observation': 'Observação',
    };
    final date = DateTime.tryParse(
      record['occurredAt'] as String? ?? '',
    )?.toLocal();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${labels[record['kind']] ?? 'Registro'} — ${date == null ? '' : '${date.day}/${date.month}/${date.year}'}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(record['text'] as String? ?? ''),
            if (record['mealType'] != null)
              Text(
                const {
                      'breakfast': 'Café da manhã',
                      'lunch': 'Almoço',
                      'dinner': 'Jantar',
                      'snack': 'Lanche',
                    }[record['mealType']] ??
                    '',
              ),
            if (record['nutrition'] is Map &&
                record['nutrition']['energyKcal'] is num)
              Text(
                '${(record['nutrition']['energyKcal'] as num).toStringAsFixed(1)} kcal',
              ),
            if (record['quantity'] != null)
              Text('${record['quantity']} ${record['unit']}'),
            if (record['kind'] == 'meal' && record['foodCode'] == null)
              const Text(
                'Cálculo nutricional pendente: alimento não identificado com precisão.',
              ),
            if (record['estimated'] == true)
              Text('Estimativa com referência em ${record['foodName']}.'),
            if (record['foodCode'] != null && record['estimated'] != true)
              Text(
                '${record['source'] ?? 'Tabela nutricional'} · registrado no diário.',
              ),
          ],
        ),
      ),
    );
  }
}
