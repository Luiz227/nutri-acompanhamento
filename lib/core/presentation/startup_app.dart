import 'dart:async';
import 'package:flutter/material.dart';

/// Rendered before storage/plugins run. Never clears storage or retries a
/// bootstrap that may still own open database files.
final startupStage = ValueNotifier<String>('Preparando seu diário');
final startupFailure = ValueNotifier<bool>(false);

class StartupApp extends StatefulWidget {
  const StartupApp({super.key});
  @override
  State<StartupApp> createState() => _StartupAppState();
}

class _StartupAppState extends State<StartupApp> {
  Timer? _timer;
  bool _slow = false;
  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(seconds: 20), () {
      if (mounted) setState(() => _slow = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff159957)),
    ),
    home: Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: ValueListenableBuilder<bool>(
              valueListenable: startupFailure,
              builder: (context, failed, _) => Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.spa_rounded,
                    size: 72,
                    color: Color(0xff159957),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    failed
                        ? 'Vamos cuidar da abertura do app'
                        : 'Seu diário, do seu jeito',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (!failed) const CircularProgressIndicator(),
                  const SizedBox(height: 20),
                  ValueListenableBuilder<String>(
                    valueListenable: startupStage,
                    builder: (context, stage, _) =>
                        Text(stage, textAlign: TextAlign.center),
                  ),
                  if (_slow || failed) ...[
                    const SizedBox(height: 20),
                    Text(
                      failed
                          ? 'Não foi possível concluir esta etapa. Feche o aplicativo e abra novamente. Seus dados não foram apagados.'
                          : 'Está demorando mais que o esperado. Seus dados continuam protegidos. Se não avançar, envie uma captura desta tela para verificarmos a etapa.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
