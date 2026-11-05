import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opennutritracker/core/utils/hive_db_provider.dart';
import 'package:opennutritracker/core/utils/locator.dart';
import 'package:opennutritracker/features/whatsapp/whatsapp_screen.dart';

class _ProfileStore implements HiveDBProvider {
  String id = 'profile-one';
  @override
  String get activeProfileId => id;
  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

void main() {
  late _ProfileStore store;
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    store = _ProfileStore();
    locator.registerSingleton<HiveDBProvider>(store);
  });
  tearDown(() async => locator.reset());

  testWidgets('explicit consent is required before connecting WhatsApp', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: WhatsappScreen()));
    await tester.pumpAndSettle();
    final button = find.widgetWithText(FilledButton, 'Conectar WhatsApp');
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    expect(find.text('Acompanhamento no WhatsApp'), findsOneWidget);
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNotNull);
  });

  testWidgets('profile switch blocks enrollment from the old profile screen', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: WhatsappScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    store.id = 'profile-two';
    await tester.ensureVisible(find.text('Conectar WhatsApp'));
    await tester.tap(find.text('Conectar WhatsApp'));
    await tester.pump();
    expect(find.text('O perfil mudou. Feche esta tela e abra novamente.'), findsOneWidget);
  });
}
