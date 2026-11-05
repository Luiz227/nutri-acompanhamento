import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:opennutritracker/core/data/repository/intake_repository.dart';
import 'package:opennutritracker/core/utils/hive_db_provider.dart';
import 'package:opennutritracker/core/utils/locator.dart';
import 'package:opennutritracker/features/whatsapp/nutri_bridge_client.dart';
import 'package:url_launcher/url_launcher.dart';

class WhatsappScreen extends StatefulWidget {
  const WhatsappScreen({super.key});
  @override
  State<WhatsappScreen> createState() => _WhatsappScreenState();
}

class _WhatsappScreenState extends State<WhatsappScreen> {
  final _server = TextEditingController(
    text: const String.fromEnvironment('NUTRI_API_URL'),
  );
  final _phone = TextEditingController();
  final _name = TextEditingController();
  final _storage = const FlutterSecureStorage();
  late final String _profileId;
  String? _token, _connectedUrl, _code;
  String _status = 'Conecte seu WhatsApp para testar o acompanhamento.';
  bool _consent = false, _busy = false, _verified = false, _active = false;
  String get _key => 'nutri-bridge-v1:$_profileId';
  bool get _sameProfile =>
      locator<HiveDBProvider>().activeProfileId == _profileId;

  @override
  void initState() {
    super.initState();
    _profileId = locator<HiveDBProvider>().activeProfileId;
    _restore();
  }

  Future<void> _restore() async {
    await _run(() async {
      final saved = await _storage.read(key: _key);
      if (saved == null) return;
      final data = jsonDecode(saved) as Map<String, dynamic>;
      _token = data['token'] as String;
      _connectedUrl = data['url'] as String;
      _server.text = _connectedUrl!;
      _phone.text = data['phone'] as String? ?? '';
      final until = DateTime.tryParse(data['codeUntil'] as String? ?? '');
      _code = until != null && until.isAfter(DateTime.now())
          ? data['code'] as String?
          : null;
      await _refresh();
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    if (!_sameProfile) {
      if (mounted) {
        setState(
          () => _status = 'O perfil mudou. Feche esta tela e abra novamente.',
        );
      }
      return;
    }
    if (mounted) setState(() => _busy = true);
    try {
      await action();
    } catch (_) {
      if (mounted) {
        setState(
          () => _status =
              'Não foi possível concluir. Confira o endereço e a conexão do servidor.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  NutriBridgeClient _connection({bool existing = true}) {
    if (existing && (_token == null || _connectedUrl != _server.text.trim())) {
      throw StateError('Use o endereço da conexão já cadastrada.');
    }
    return NutriBridgeClient(_server.text);
  }

  Future<void> _enroll() async {
    if (!_consent) return;
    final client = _connection(existing: false);
    try {
      final response = await client.request(
        'POST',
        '/api/v1/enroll',
        body: {
          'phone': _phone.text,
          'consent': {
            'granted': true,
            'version': '2026-11-05-whatsapp-test-v1',
          },
        },
      );
      final token = response['token'] as String;
      final code = response['pairingCode'] as String;
      final url = _server.text.trim();
      await _storage.write(
        key: _key,
        value: jsonEncode({
          'token': token,
          'url': url,
          'phone': _phone.text,
          'code': code,
          'codeUntil': DateTime.now()
              .add(const Duration(minutes: 10))
              .toIso8601String(),
        }),
      );
      _token = token;
      _connectedUrl = url;
      _code = code;
      _active = true;
      _verified = false;
      _status = response['n8nConfigured'] == true
          ? 'Cadastro salvo. Aguarde a mensagem no WhatsApp e responda com o código abaixo.'
          : 'Cadastro salvo. O operador ainda precisa configurar o n8n no servidor.';
    } finally {
      client.close();
    }
  }

  Future<void> _refresh() async {
    final client = _connection();
    try {
      final response = await client.request('GET', '/api/v1/me', token: _token);
      _verified = response['verified'] == true;
      _active = response['consentActive'] == true;
      if (_verified || !_active) _code = null;
      _status = !_active
          ? 'Acompanhamento cancelado.'
          : _verified
          ? 'WhatsApp confirmado. Você pode enviar um resumo do diário para o acompanhamento.'
          : 'Aguardando confirmação pelo WhatsApp. O código vale por 10 minutos.';
    } finally {
      client.close();
    }
  }

  Future<void> _shareDiary() async {
    if (!_active || !_verified) return;
    final intakes = await locator<IntakeRepository>().getAllIntakesDBO();
    if (!_sameProfile) throw StateError('Perfil alterado');
    final cutoff = DateTime.now().subtract(const Duration(days: 7));
    final recent = intakes.where((i) => i.dateTime.isAfter(cutoff)).toList()
      ..sort((a, b) => b.dateTime.compareTo(a.dateTime));
    final lines = recent
        .take(15)
        .map(
          (i) =>
              '${i.dateTime.toIso8601String().substring(0, 10)}: ${i.meal.name ?? 'Alimento'}, ${i.amount} ${i.unit}',
        )
        .join('\n');
    final client = _connection();
    try {
      await client.request(
        'PUT',
        '/api/v1/context',
        token: _token,
        body: {
          'displayName': _name.text.trim(),
          'recentDiarySummary': lines.isEmpty
              ? 'Nenhuma refeição registrada nos últimos sete dias.'
              : lines,
        },
      );
      _status =
          'Resumo enviado: até 15 registros dos últimos sete dias. Novas alterações só serão enviadas ao tocar neste botão novamente.';
    } finally {
      client.close();
    }
  }

  Future<void> _revoke() async {
    final client = _connection();
    try {
      await client.request('DELETE', '/api/v1/whatsapp', token: _token);
      _active = false;
      _code = null;
      _status = 'Mensagens de acompanhamento canceladas no servidor.';
    } finally {
      client.close();
    }
  }

  @override
  void dispose() {
    _server.dispose();
    _phone.dispose();
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Acompanhamento no WhatsApp')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'Versão de teste — assistente virtual. O atendimento não substitui seu nutricionista.',
        ),
        const SizedBox(height: 16),
        Semantics(
          identifier: 'whatsapp-server',
          child: TextField(
            controller: _server,
            enabled: !_busy && _token == null,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Endereço HTTPS do servidor',
            ),
          ),
        ),
        Semantics(
          identifier: 'whatsapp-phone',
          child: TextField(
            controller: _phone,
            enabled: !_busy && _token == null,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'WhatsApp com 55 e DDD',
              hintText: '5511999999999',
            ),
          ),
        ),
        if (_token == null) ...[
          Semantics(
            identifier: 'whatsapp-consent',
            child: CheckboxListTile(
              value: _consent,
              onChanged: _busy
                  ? null
                  : (value) => setState(() => _consent = value == true),
              title: const Text(
                'Autorizo o contato por WhatsApp pela assistente virtual.',
              ),
              subtitle: const Text(
                'Seu número e esta autorização serão enviados ao servidor do operador, n8n e Evolution. O resumo do diário só será compartilhado ao tocar em Enviar resumo. Posso cancelar aqui ou enviando SAIR.',
              ),
            ),
          ),
          Semantics(
            identifier: 'whatsapp-connect',
            child: FilledButton(
              onPressed: !_busy && _consent ? () => _run(_enroll) : null,
              child: const Text('Conectar WhatsApp'),
            ),
          ),
        ],
        const SizedBox(height: 16),
        Text(_status),
        if (_code != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: SelectableText(
              'Responda no WhatsApp com este código: $_code',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
        if (_token != null) ...[
          Semantics(
            identifier: 'whatsapp-refresh',
            child: OutlinedButton(
              onPressed: _busy ? null : () => _run(_refresh),
              child: const Text('Verificar conexão'),
            ),
          ),
          if (_verified && _active) ...[
            Semantics(
              identifier: 'whatsapp-alias',
              child: TextField(
                controller: _name,
                decoration: const InputDecoration(
                  labelText: 'Como deseja ser chamado (opcional)',
                ),
              ),
            ),
            Semantics(
              identifier: 'whatsapp-share-diary',
              child: FilledButton(
                onPressed: _busy ? null : () => _run(_shareDiary),
                child: const Text('Enviar resumo do diário'),
              ),
            ),
          ],
          if (_active)
            Semantics(
              identifier: 'whatsapp-revoke',
              child: TextButton(
                onPressed: _busy ? null : () => _run(_revoke),
                child: const Text('Cancelar acompanhamento'),
              ),
            ),
          if (!_active)
            Semantics(
              identifier: 'whatsapp-reset',
              child: TextButton(
                onPressed: _busy
                    ? null
                    : () => _run(() async {
                        await _storage.delete(key: _key);
                        _token = null;
                        _connectedUrl = null;
                        _code = null;
                        _consent = false;
                      }),
                child: const Text('Conectar novamente'),
              ),
            ),
        ],
        if (_busy) const Center(child: CircularProgressIndicator()),
        const Divider(),
        const Text(
          'Derivado do OpenNutriTracker, sob GPLv3. As mudanças desta versão e a fonte correspondente estão disponíveis no repositório.',
        ),
        Semantics(
          identifier: 'whatsapp-source-code',
          child: TextButton(
            onPressed: () => launchUrl(
              Uri.parse('https://github.com/luiz227/nutri-acompanhamento'),
            ),
            child: const Text('Código-fonte e licença'),
          ),
        ),
      ],
    ),
  );
}
