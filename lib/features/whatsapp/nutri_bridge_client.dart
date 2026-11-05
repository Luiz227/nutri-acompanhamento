import 'dart:convert';
import 'package:http/http.dart' as http;

class NutriBridgeClient {
  final Uri base;
  final http.Client _client;
  NutriBridgeClient(String baseUrl, {http.Client? client})
    : base = validateBaseUrl(baseUrl),
      _client = client ?? http.Client();

  static Uri validateBaseUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const FormatException(
        'Informe somente o endereço HTTPS do servidor.',
      );
    }
    return uri.replace(path: '');
  }

  Future<Map<String, dynamic>> request(
    String method,
    String path, {
    String? token,
    Map<String, dynamic>? body,
  }) async {
    if (!path.startsWith('/api/v1/')) {
      throw const FormatException('Caminho de API inválido.');
    }
    final req = http.Request(method, base.resolve(path));
    req.followRedirects = false;
    req.headers['Content-Type'] = 'application/json';
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    if (body != null) req.body = jsonEncode(body);
    final response = await http.Response.fromStream(
      await _client.send(req).timeout(const Duration(seconds: 20)),
    ).timeout(const Duration(seconds: 20));
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Resposta inesperada do servidor.');
    }
    if (response.statusCode != 200) {
      throw Exception(
        decoded['error'] ?? 'Não foi possível conectar ao servidor.',
      );
    }
    return decoded;
  }

  void close() => _client.close();
}
