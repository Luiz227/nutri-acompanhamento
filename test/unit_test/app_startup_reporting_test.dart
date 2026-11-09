import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:opennutritracker/core/utils/app_startup_reporting.dart';

void main() {
  test(
    'cold restart after consent with quoted empty DSN still starts the app',
    () async {
      var launches = 0;
      var sdkCalls = 0;
      for (final consent in [false, true]) {
        await startWithOptionalReporting(
          enabled: consent,
          dsn: '""',
          runApplication: () => launches++,
          initialize: (_, launch) async {
            sdkCalls++;
            throw ArgumentError('DSN');
          },
        );
      }
      expect(launches, 2);
      expect(sdkCalls, 0);
      for (final invalid in [
        '',
        ' ',
        '""',
        "''",
        'not-a-url',
        'https://example.com',
        'https://key@example.com',
      ]) {
        expect(usableReportingDsn(invalid), isNull);
      }
    },
  );
  test('reporting failure cannot prevent app startup', () async {
    var launches = 0;
    await startWithOptionalReporting(
      enabled: true,
      dsn: 'https://key@example.invalid/1',
      runApplication: () => launches++,
      initialize: (_, launch) async => throw StateError('plugin unavailable'),
    );
    expect(launches, 1);
  });
  test(
    'reporting timeout launches once even if SDK calls back later',
    () async {
      var launches = 0;
      late void Function() lateLaunch;
      final blocked = Completer<void>();
      await startWithOptionalReporting(
        enabled: true,
        dsn: 'https://key@example.invalid/1',
        timeout: const Duration(milliseconds: 5),
        runApplication: () => launches++,
        initialize: (_, launch) {
          lateLaunch = launch;
          return blocked.future;
        },
      );
      expect(launches, 1);
      lateLaunch();
      blocked.complete();
      expect(launches, 1);
    },
  );
  test(
    'successful SDK appRunner is not repeated after initialization',
    () async {
      var launches = 0;
      await startWithOptionalReporting(
        enabled: true,
        dsn: 'https://key@example.invalid/1',
        runApplication: () => launches++,
        initialize: (_, launch) async {
          launch();
        },
      );
      expect(launches, 1);
    },
  );
}
