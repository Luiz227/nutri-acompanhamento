import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:opennutritracker/core/domain/entity/intake_entity.dart';
import 'package:opennutritracker/core/domain/entity/intake_type_entity.dart';
import 'package:opennutritracker/features/add_meal/data/data_sources/taco_food_data_source.dart';

void main() {
  late TacoFoodDataSource source;
  late Map<String, dynamic> document;
  setUp(() async {
    final text = await File(TacoFoodDataSource.assetPath).readAsString();
    document = jsonDecode(text) as Map<String, dynamic>;
    source = TacoFoodDataSource(read: () async => text);
  });

  test(
    'official catalogue excludes only the six foods with unknown energy',
    () async {
      final rows = document['foods'] as List;
      expect(rows, hasLength(597));
      expect(
        rows.where((r) => r['usable_for_tracking'] != true).map((r) => r['id']),
        [450, 457, 458, 516, 517, 591],
      );
      expect(document['source_anomalies'], hasLength(5));
      final foods = await source.foods();
      expect(foods, hasLength(591));
      expect(foods.map((f) => f.code).toSet(), hasLength(591));
      for (final food in foods) {
        expect(food.code, startsWith('taco:'));
        expect(food.backendSource, 'taco');
        expect(food.mealUnit, 'g');
        expect(food.hasServingValues, isFalse);
        expect(food.nutriments.sugars100, isNull);
        expect(food.nutriments.transFat100, isNull);
        expect(food.nutriments.vitaminD100, isNull);
      }
    },
  );

  test('accent-independent search distinguishes cooked and raw rice', () async {
    expect(
      (await source.search('FEIJAO carioca cozido')).map((f) => f.code),
      contains('taco:561'),
    );
    expect(await source.search('pao frances'), isNotEmpty);
    expect(await source.search('   '), isEmpty);
    final foods = await source.foods();
    expect(
      foods.singleWhere((f) => f.code == 'taco:3').nutriments.energyKcal100,
      128.258486,
    );
    expect(
      foods.singleWhere((f) => f.code == 'taco:4').nutriments.energyKcal100,
      357.789273,
    );
    expect(
      foods.singleWhere((f) => f.code == 'taco:561').nutriments.energyKcal100,
      76.424086,
    );
  });

  test(
    'weighed intake scales official rice nutrients at 50, 100 and 250 g',
    () async {
      final rice = (await source.foods()).singleWhere(
        (f) => f.code == 'taco:3',
      );
      for (final grams in [50.0, 100.0, 250.0]) {
        final intake = IntakeEntity(
          id: 'test',
          unit: 'g',
          amount: grams,
          type: IntakeTypeEntity.lunch,
          meal: rice,
          dateTime: DateTime(2026),
        );
        expect(intake.totalKcal, closeTo(128.258486 * grams / 100, 0.000001));
        expect(
          intake.totalProteinsGram,
          closeTo(2.520817 * grams / 100, 0.000001),
        );
        expect(
          intake.totalCarbsGram,
          closeTo(28.05985 * grams / 100, 0.000001),
        );
        expect(intake.totalFatsGram, closeTo(0.227 * grams / 100, 0.000001));
      }
    },
  );

  test(
    'invalid source carbohydrate cells remain unknown, never zero',
    () async {
      final foods = await source.foods();
      for (final id in [288, 322, 337, 400]) {
        expect(
          foods
              .singleWhere((f) => f.code == 'taco:$id')
              .nutriments
              .carbohydrates100,
          isNull,
        );
      }
    },
  );

  test(
    'rejects incompatible nutrient basis and duplicate identifiers',
    () async {
      document['basis']['unit'] = 'ml';
      await expectLater(
        TacoFoodDataSource(read: () async => jsonEncode(document)).foods(),
        throwsFormatException,
      );
      document['basis']['unit'] = 'g';
      (document['foods'] as List).add(document['foods'][0]);
      await expectLater(
        TacoFoodDataSource(read: () async => jsonEncode(document)).foods(),
        throwsFormatException,
      );
    },
  );
}
