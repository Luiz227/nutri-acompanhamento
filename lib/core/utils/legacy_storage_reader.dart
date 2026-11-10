import 'dart:io';
import 'package:flutter/services.dart';

/// Reads existing Android ciphertext using existing keys only. The native
/// implementation never resets preferences or generates a legacy key.
class LegacyStorageReader {
  static const _channel = MethodChannel('nutri/legacy-storage');
  static Future<({bool present, String? value})> read(String key) async {
    if (!Platform.isAndroid) return (present: false, value: null);
    return readNative(key);
  }

  static Future<({bool present, String? value})> readNative(String key) async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('read', {
        'key': key,
      });
      return (
        present: result?['present'] == true,
        value: result?['value'] as String?,
      );
    } on MissingPluginException {
      return (present: false, value: null);
    }
  }
}
