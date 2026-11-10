import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opennutritracker/core/utils/legacy_storage_reader.dart';
import 'package:opennutritracker/core/utils/secure_app_storage_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('nutri/legacy-storage');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test(
    'missing native support is distinct from an unreadable existing key',
    () async {
      expect(await LegacyStorageReader.readNative('HiveEncryptionTag'), (
        present: false,
        value: null,
      ));
      messenger.setMockMethodCallHandler(
        channel,
        (_) async => {'present': true, 'value': null},
      );
      expect(await LegacyStorageReader.readNative('HiveEncryptionTag'), (
        present: true,
        value: null,
      ));
    },
  );

  test(
    'unreadable legacy key refuses to generate or write a replacement',
    () async {
      const storageChannel = MethodChannel(
        'plugins.it_nomads.com/flutter_secure_storage',
      );
      final methods = <String>[];
      messenger.setMockMethodCallHandler(storageChannel, (call) async {
        methods.add(call.method);
        expect(call.arguments['options']['storageNamespace'], 'nutri_core_v2');
        expect(call.arguments['options']['resetOnError'], 'false');
        return null;
      });
      messenger.setMockMethodCallHandler(
        channel,
        (_) async => {'present': true, 'value': null},
      );
      await expectLater(
        SecureAppStorageProvider(
          readLegacy: LegacyStorageReader.readNative,
        ).getHiveEncryptionKey(),
        throwsA(
          predicate((e) => e.toString().contains('hive_legacy_key_unreadable')),
        ),
      );
      expect(methods, ['read']);
      messenger.setMockMethodCallHandler(storageChannel, null);
    },
  );
}
