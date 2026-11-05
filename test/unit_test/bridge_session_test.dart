import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:opennutritracker/core/utils/hive_db_provider.dart';
import 'package:opennutritracker/core/utils/locator.dart';
import 'package:opennutritracker/core/data/repository/water_intake_repository.dart';
import 'package:opennutritracker/core/domain/entity/water_intake_entity.dart';
import 'package:opennutritracker/features/whatsapp/bridge_session.dart';
import 'package:opennutritracker/features/whatsapp/nutri_bridge_client.dart';

class _Profiles implements HiveDBProvider {
  String id = 'one';
  @override
  String get activeProfileId => id;
  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

class _Water implements WaterIntakeRepository {
  final entries = <String, WaterIntakeEntity>{};
  int writes = 0;
  @override
  Future<void> addEntry(WaterIntakeEntity entry) async {
    writes++;
    entries[entry.id] = entry;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _Profiles profiles;
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    profiles = _Profiles();
    locator.registerSingleton<HiveDBProvider>(profiles);
  });
  tearDown(() async => locator.reset());

  test(
    'offline signup is persisted without exposing server configuration to the user',
    () async {
      final session = BridgeSession(
        'one',
        resolveUrl: () async => throw StateError('offline'),
      );
      await session.enroll('55 (11) 99999-9999');
      final saved = await session.load();
      expect(saved['pending'], true);
      expect(saved['phone'], '5511999999999');
      expect((saved['appToken'] as String).length, 64);
      expect(saved['message'], contains('automaticamente'));
    },
  );

  test(
    'pending signup retries with the same installation token and code',
    () async {
      final first = BridgeSession(
        'one',
        resolveUrl: () async => throw StateError('offline'),
      );
      await first.enroll('5511999999999');
      final original = await first.load();
      var enrollments = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/api/v1/enroll') {
          enrollments++;
          final body = jsonDecode(request.body);
          expect(body['appToken'], original['appToken']);
          expect(body['pairingCode'], original['code']);
          return http.Response(
            jsonEncode({
              'token': 'patient-token',
              'expiresInSeconds': 600,
              'verified': false,
              'consentActive': true,
              'n8nConfigured': true,
            }),
            200,
          );
        }
        return http.Response('{"verified":false,"consentActive":true}', 200);
      });
      final session = BridgeSession(
        'one',
        resolveUrl: () async => 'https://nutri.example',
        createClient: (url) => NutriBridgeClient(url, client: client),
      );
      await Future.wait([session.synchronize(), session.synchronize()]);
      expect(enrollments, 1);
      expect((await session.load())['pending'], false);
    },
  );

  test(
    'confirmed water imports once and a different profile cannot read the session',
    () async {
      final water = _Water();
      locator.registerSingleton<WaterIntakeRepository>(water);
      const storage = FlutterSecureStorage();
      await storage.write(
        key: 'nutri-bridge-v1:one',
        value: jsonEncode({
          'token': 'test-token',
          'url': 'https://nutri.example',
          'cursor': 0,
          'records': [],
        }),
      );
      final session = BridgeSession(
        'one',
        onError: (error, stack) => fail('$error\n$stack'),
        createClient: (url) => NutriBridgeClient(
          url,
          client: MockClient((request) async {
            if (request.url.path == '/api/v1/me') {
              return http.Response(
                '{"verified":true,"consentActive":true}',
                200,
              );
            }
            final after = int.parse(request.url.queryParameters['after']!);
            return http.Response(
              jsonEncode({
                'records': after == 0
                    ? [
                        {
                          'id': 'note-1',
                          'seq': 1,
                          'kind': 'water',
                          'text': 'Água',
                          'quantity': 500,
                          'unit': 'ml',
                          'occurredAt': '2026-11-05T12:00:00Z',
                        },
                      ]
                    : [],
                'nextCursor': 1,
                'hasMore': false,
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }),
        ),
      );
      await session.synchronize();
      await session.synchronize();
      expect(water.entries['whatsapp:note-1']!.amountMl, 500);
      expect(water.writes, 1);
      profiles.id = 'two';
      expect(await BridgeSession('two').load(), isEmpty);
      await session.synchronize();
      expect(water.writes, 1);
    },
  );
}
