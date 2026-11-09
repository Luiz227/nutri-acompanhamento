import 'dart:async';

/// Optional diagnostics must never prevent first launch or a cold restart.
String? usableReportingDsn(String value) {
  var dsn = value.trim();
  if (dsn.length >= 2 &&
      ((dsn.startsWith('"') && dsn.endsWith('"')) ||
          (dsn.startsWith("'") && dsn.endsWith("'")))) {
    dsn = dsn.substring(1, dsn.length - 1).trim();
  }
  final uri = Uri.tryParse(dsn);
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host.isEmpty ||
      uri.userInfo.isEmpty ||
      uri.pathSegments.where((s) => s.isNotEmpty).isEmpty) {
    return null;
  }
  return dsn;
}

Future<void> startWithOptionalReporting({
  required bool enabled,
  required String dsn,
  required void Function() runApplication,
  required Future<void> Function(String dsn, void Function() launch) initialize,
  void Function()? onUnavailable,
  Duration timeout = const Duration(seconds: 5),
}) async {
  var launched = false;
  void launch() {
    if (launched) return;
    launched = true;
    runApplication();
  }

  final usable = usableReportingDsn(dsn);
  if (!enabled || usable == null) {
    launch();
    return;
  }
  try {
    await initialize(usable, launch).timeout(timeout);
  } catch (_) {
    onUnavailable?.call();
  } finally {
    // Also handles SDKs that complete without invoking their appRunner.
    // A late callback after timeout must not mount the application twice.
    launch();
  }
}
