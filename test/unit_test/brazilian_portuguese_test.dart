import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:opennutritracker/core/l10n/app_locales.dart';
import 'package:opennutritracker/core/utils/off_const.dart';
import 'package:opennutritracker/core/utils/supported_language.dart';
import 'package:opennutritracker/features/add_meal/data/dto/off/off_product_dto.dart';
import 'package:opennutritracker/generated/l10n.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'Brazilian Portuguese renders navigation, plurals and parameters',
    () async {
      final strings = await S.delegate.load(const Locale('pt', 'BR'));
      expect(appLocales(S.supportedLocales), contains(const Locale('pt')));
      expect(strings.onboardingWelcomeLabel, 'Boas-vindas ao');
      expect(strings.buttonStartLabel, 'COMEÇAR');
      expect(strings.diaryLabel, 'Diário');
      expect(strings.settingsLabel, 'Configurações');
      expect(strings.measureUnitEgg(1), 'ovo');
      expect(strings.measureUnitEgg(2), 'ovos');
      expect(strings.appVersionName('2.5.0'), 'Versão 2.5.0');
      await initializeDateFormatting('pt_BR');
      expect(
        DateFormat.yMd('pt_BR').format(DateTime(2026, 10, 26)),
        '26/10/2026',
      );
    },
  );

  test(
    'Portuguese includes each interface message without damaged markers',
    () {
      final english =
          jsonDecode(File('lib/l10n/intl_en.arb').readAsStringSync())
              as Map<String, dynamic>;
      final portuguese =
          jsonDecode(File('lib/l10n/intl_pt.arb').readAsStringSync())
              as Map<String, dynamic>;
      for (final key in english.keys.where((key) => !key.startsWith('@'))) {
        expect(portuguese[key], isA<String>(), reason: key);
        final text = portuguese[key] as String;
        expect(text.trim(), isNotEmpty, reason: key);
        expect(text, isNot(contains('▁')), reason: key);
        expect(text, isNot(contains('__PH')), reason: key);
      }
    },
  );

  test('Portuguese food names are requested and preferred when available', () {
    expect(SupportedLanguage.fromCode('pt_BR'), SupportedLanguage.pt);
    expect(SupportedLanguage.fromCode('pt-BR'), SupportedLanguage.pt);
    final food = OFFProductDTO.fromJson({
      'product_name': 'Original name',
      'product_name_en': 'Rice',
      'product_name_pt': 'Arroz',
    });
    expect(food.getLocaleName(SupportedLanguage.pt), 'Arroz');
    expect(
      OFFConst.getOffBarcodeSearchUri('12345678').queryParameters['fields'],
      contains('product_name_pt'),
    );
  });
}
