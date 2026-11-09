import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opennutritracker/core/presentation/startup_app.dart';
import 'package:opennutritracker/core/presentation/splash_screen.dart';
import 'package:opennutritracker/core/utils/app_locale_service.dart';
import 'package:opennutritracker/core/utils/navigation_options.dart';

void main() {
  testWidgets(
    'startup is visible and identifies a stalled stage without clearing data',
    (tester) async {
      startupFailure.value = false;
      startupStage.value = 'Abrindo seu diário salvo';
      await tester.pumpWidget(const StartupApp());
      expect(find.text('Seu diário, do seu jeito'), findsOneWidget);
      await tester.pump(const Duration(seconds: 21));
      expect(find.textContaining('Está demorando'), findsOneWidget);
      expect(find.text('Abrindo seu diário salvo'), findsOneWidget);
      startupFailure.value = true;
      await tester.pump();
      expect(
        find.textContaining('Seus dados não foram apagados'),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox());
      startupFailure.value = false;
    },
  );

  testWidgets(
    'a native locale channel that never answers does not block startup',
    (tester) async {
      const channel = MethodChannel('com.opennutritracker/locale');
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(
        channel,
        (_) => Completer<Object?>().future,
      );
      final read = AppLocaleService.getApplicationLocale();
      final write = AppLocaleService.setApplicationLocale('pt');
      await tester.pump(const Duration(seconds: 3));
      expect((await read).readFailed, true);
      await write;
      messenger.setMockMethodCallHandler(channel, null);
    },
  );

  testWidgets(
    'returning user leaves splash even when animation tickers are disabled',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const TickerMode(
            enabled: false,
            child: SplashScreen(userInitialized: true),
          ),
          routes: {
            NavigationOptions.mainRoute: (_) =>
                const Scaffold(body: Text('Diário aberto')),
          },
        ),
      );
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
      expect(find.text('Diário aberto'), findsOneWidget);
    },
  );
}
