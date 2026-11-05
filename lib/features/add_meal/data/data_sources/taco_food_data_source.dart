import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:opennutritracker/features/add_meal/data/dto/sp/sp_food_dto.dart';
import 'package:opennutritracker/features/add_meal/domain/entity/meal_entity.dart';
import 'package:opennutritracker/features/add_meal/domain/entity/meal_nutriments_entity.dart';

/// Immutable, offline reference foods from the unchanged NEPA workbook.
/// Codes are namespaced because Hive also stores numeric USDA food IDs.
class TacoFoodDataSource {
  static const sourceCode = 'taco';
  static const assetPath = 'assets/data/taco_4ed.json';
  final Future<String> Function() _read;
  Future<List<MealEntity>>? _loaded;

  TacoFoodDataSource({Future<String> Function()? read})
    : _read = read ?? (() => rootBundle.loadString(assetPath));

  Future<List<MealEntity>> foods() => _loaded ??= _load();

  Future<List<MealEntity>> _load() async {
    final document = jsonDecode(await _read()) as Map<String, dynamic>;
    if (document['schema_version'] != 1 ||
        document['source'] != sourceCode ||
        document['basis']['quantity'] != 100 ||
        document['basis']['unit'] != 'g') {
      throw const FormatException(
        'Unsupported TACO catalogue or nutrient basis',
      );
    }
    final meals = <MealEntity>[];
    final ids = <int>{};
    for (final raw in document['foods'] as List<dynamic>) {
      final row = raw as Map<String, dynamic>;
      final id = row['id'] as int;
      if (!ids.add(id)) throw const FormatException('Duplicate TACO food ID');
      // Six entries have no usable energy. Do not let the intake engine's
      // legacy null-to-zero fallback present them as zero-calorie foods.
      if (row['usable_for_tracking'] != true) continue;
      final nutrients = row['nutrients'] as Map<String, dynamic>;
      for (final value in nutrients.values) {
        if (value != null && (value is! num || !value.isFinite || value < 0)) {
          throw const FormatException('Invalid TACO nutrient value');
        }
      }
      if (nutrients['energy_kcal_100'] == null) {
        throw const FormatException('TACO tracking food without energy');
      }
      final dto = SpFoodDTO.fromJson(nutrients);
      meals.add(
        MealEntity(
          code: 'taco:$id',
          name: row['name'] as String,
          url: document['source_url'] as String,
          mealQuantity: null,
          mealUnit: 'g',
          servingQuantity: null,
          servingUnit: 'g',
          servingSize: null,
          nutriments: MealNutrimentsEntity.fromSpFoodSummary(dto),
          source: MealSourceEntity.fdc,
          backendSource: sourceCode,
          detailed: true,
        ),
      );
    }
    return List.unmodifiable(meals);
  }

  Future<List<MealEntity>> search(String query) async {
    final tokens = _normalize(
      query,
    ).split(' ').where((s) => s.isNotEmpty).toList();
    if (tokens.isEmpty) return const [];
    final matches = (await foods()).where((food) {
      final name = _normalize(food.name!);
      return tokens.every(name.contains);
    }).toList();
    matches.sort((a, b) {
      final left = _normalize(a.name!);
      final right = _normalize(b.name!);
      final leftPrefix = left.startsWith(tokens.first) ? 0 : 1;
      final rightPrefix = right.startsWith(tokens.first) ? 0 : 1;
      final byPrefix = leftPrefix.compareTo(rightPrefix);
      if (byPrefix != 0) return byPrefix;
      final byLength = left.length.compareTo(right.length);
      return byLength != 0 ? byLength : a.code!.compareTo(b.code!);
    });
    return matches.take(25).toList(growable: false);
  }

  static String _normalize(String text) {
    var value = text.toLowerCase();
    for (final entry in const {
      '[áàâãä]': 'a',
      '[éèêë]': 'e',
      '[íìîï]': 'i',
      '[óòôõö]': 'o',
      '[úùûü]': 'u',
      'ç': 'c',
    }.entries) {
      value = value.replaceAll(RegExp(entry.key), entry.value);
    }
    return value.replaceAll(RegExp('[^a-z0-9]+'), ' ').trim();
  }
}
