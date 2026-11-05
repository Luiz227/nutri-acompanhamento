import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:opennutritracker/features/whatsapp/nutri_bridge_client.dart';

void main() {
  test('accepts only clean HTTPS origins, never tokens in URLs', () {
    expect(
      NutriBridgeClient.validateBaseUrl('https://nutri.example/').host,
      'nutri.example',
    );
    for (final url in [
      'http://nutri.example',
      'https://user:pass@nutri.example',
      'https://nutri.example?token=secret',
      'https://nutri.example/api',
      'file:///data',
    ]) {
      expect(
        () => NutriBridgeClient.validateBaseUrl(url),
        throwsFormatException,
      );
    }
  });
  test(
    'patient token is sent only as authorization to the configured origin',
    () async {
      final client = NutriBridgeClient(
        'https://nutri.example',
        client: MockClient((req) async {
          expect(req.url.toString(), 'https://nutri.example/api/v1/me');
          expect(req.headers['Authorization'], 'Bearer patient-token');
          return http.Response(jsonEncode({'verified': true}), 200);
        }),
      );
      expect(
        (await client.request(
          'GET',
          '/api/v1/me',
          token: 'patient-token',
        ))['verified'],
        true,
      );
      client.close();
    },
  );
  test('enrollment sends consent without service or Evolution keys', () async {
    final client = NutriBridgeClient(
      'https://nutri.example',
      client: MockClient((req) async {
        expect(req.headers.containsKey('Authorization'), false);
        expect(req.headers.containsKey('apikey'), false);
        expect(jsonDecode(req.body)['consent']['granted'], true);
        return http.Response('{"userId":"test"}', 200);
      }),
    );
    await client.request(
      'POST',
      '/api/v1/enroll',
      body: {
        'consent': {'granted': true},
      },
    );
    client.close();
  });
  test('server rejection never looks like enrollment success', () async {
    final client = NutriBridgeClient(
      'https://nutri.example',
      client: MockClient(
        (_) async => http.Response('{"error":"Sem autorização"}', 401),
      ),
    );
    await expectLater(client.request('GET', '/api/v1/me'), throwsException);
    client.close();
  });
}
