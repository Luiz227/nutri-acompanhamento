import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';
import 'package:opennutritracker/core/utils/hive_db_provider.dart';
import 'package:opennutritracker/core/utils/locator.dart';
import 'package:opennutritracker/core/data/repository/intake_repository.dart';
import 'package:opennutritracker/core/data/repository/water_intake_repository.dart';
import 'package:opennutritracker/core/data/repository/weight_log_repository.dart';
import 'package:opennutritracker/core/data/repository/user_repository.dart';
import 'package:opennutritracker/core/data/repository/config_repository.dart';
import 'package:opennutritracker/core/domain/entity/user_entity.dart';
import 'package:opennutritracker/core/domain/usecase/get_kcal_goal_usecase.dart';
import 'package:opennutritracker/core/domain/usecase/get_macro_goal_usecase.dart';
import 'package:opennutritracker/core/domain/entity/intake_entity.dart';
import 'package:opennutritracker/core/domain/entity/intake_type_entity.dart';
import 'package:opennutritracker/core/domain/entity/water_intake_entity.dart';
import 'package:opennutritracker/core/domain/entity/weight_log_entity.dart';
import 'package:opennutritracker/features/add_meal/data/data_sources/taco_food_data_source.dart';
import 'package:opennutritracker/features/add_meal/data/dto/sp/sp_food_dto.dart';
import 'package:opennutritracker/features/add_meal/domain/entity/meal_entity.dart';
import 'package:opennutritracker/features/add_meal/domain/entity/meal_nutriments_entity.dart';
import 'package:opennutritracker/features/whatsapp/nutri_bridge_client.dart';

class BridgeSession {
  static final changed = ValueNotifier<int>(0);
  static final _running = <String, Future<void>>{};
  static final _taco = TacoFoodDataSource();
  final String profileId;
  final FlutterSecureStorage storage;
  final Future<String> Function() resolveUrl;
  final NutriBridgeClient Function(String) createClient;
  final void Function(Object, StackTrace)? onError;
  final Future<Map<String, dynamic>> Function() readProfile;
  BridgeSession(
    this.profileId, {
    this.storage = const FlutterSecureStorage(),
    Future<String> Function()? resolveUrl,
    NutriBridgeClient Function(String)? createClient,
    Future<Map<String, dynamic>> Function()? readProfile,
    this.onError,
  }) : resolveUrl = resolveUrl ?? resolveBaseUrl,
       readProfile = readProfile ?? readAppProfile,
       createClient = createClient ?? ((url) => NutriBridgeClient(url));

  static Map<String, dynamic> profileOf(UserEntity user) => {
    'birthday': user.birthday.toIso8601String().substring(0, 10),
    'heightCm': user.heightCM,
    'weightKg': user.weightKG,
    'gender': user.gender.name,
    'goal': user.goal.name,
    'activityLevel': user.pal.name,
    'targetWeightKg': user.targetWeightKg,
    'weeklyWeightGoalKg': user.weeklyWeightGoalKg,
  };

  static Future<Map<String, dynamic>> readAppProfile() async {
    if (!locator.isRegistered<UserRepository>()) return {};
    final repo = locator<UserRepository>();
    if (!await repo.hasUserData()) return {};
    final user = await repo.getUserData();
    final profile = profileOf(user);
    if (locator.isRegistered<GetKcalGoalUsecase>() &&
        locator.isRegistered<GetMacroGoalUsecase>() &&
        locator.isRegistered<ConfigRepository>()) {
      final kcal = await locator<GetKcalGoalUsecase>().getKcalGoal(
        userEntity: user,
      );
      if (kcal.isFinite && kcal > 0) {
        final macros = locator<GetMacroGoalUsecase>();
        final config = await locator<ConfigRepository>().getConfig();
        profile['dailyGoals'] = {
          'energyKcal': kcal,
          'proteinG': await macros.getProteinsGoal(kcal),
          'carbsG': await macros.getCarbsGoal(kcal),
          'fatG': await macros.getFatsGoal(kcal),
          'waterMl': config.effectiveDailyWaterGoalMl(
            user.gender,
            caloriesProfile: user.caloriesProfile,
          ),
        };
      }
    }
    return profile;
  }

  factory BridgeSession.current() =>
      BridgeSession(locator<HiveDBProvider>().activeProfileId);
  String get key => 'nutri-bridge-v1:$profileId';
  bool get sameProfile =>
      locator<HiveDBProvider>().activeProfileId == profileId;

  static Future<String> resolveBaseUrl() async {
    const compiled = String.fromEnvironment('NUTRI_API_URL');
    if (compiled.isNotEmpty) {
      return NutriBridgeClient.validateBaseUrl(compiled).toString();
    }
    final response = await http
        .get(
          Uri.parse(
            'https://raw.githubusercontent.com/Luiz227/nutri-acompanhamento/main/config/mobile.json',
          ),
        )
        .timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw StateError('Serviço ainda não ativado.');
    }
    final value = jsonDecode(response.body);
    if (value is! Map ||
        value['schemaVersion'] != 1 ||
        value['apiUrl'] is! String) {
      throw StateError('Serviço ainda não ativado.');
    }
    return NutriBridgeClient.validateBaseUrl(
      value['apiUrl'] as String,
    ).toString();
  }

  Future<Map<String, dynamic>> load() async {
    final raw = await storage.read(key: key);
    return raw == null
        ? <String, dynamic>{}
        : jsonDecode(raw) as Map<String, dynamic>;
  }

  Future<void> _save(Map<String, dynamic> state) async {
    await storage.write(key: key, value: jsonEncode(state));
    changed.value++;
  }

  Future<void> enroll(
    String phone, {
    Map<String, dynamic> profile = const {},
  }) async {
    final number = phone.replaceAll(RegExp(r'[\s()+.-]'), '');
    if (!RegExp(r'^55\d{10,11}$').hasMatch(number)) {
      throw const FormatException('Informe 55, DDD e WhatsApp.');
    }
    final old = await load();
    if (old['token'] != null && old['active'] != false) return;
    final token =
        const Uuid().v4().replaceAll('-', '') +
        const Uuid().v4().replaceAll('-', '');
    final code = (Random.secure().nextInt(900000) + 100000).toString();
    await _save({
      'phone': number,
      'appToken': token,
      'code': code,
      'pending': true,
      'profile': profile,
      'records': <dynamic>[],
      'cursor': 0,
    });
    // Persist before networking so a temporary failure does not lose the registration.
    await synchronize();
  }

  Future<void> synchronize() =>
      _running[profileId] ??= _sync().whenComplete(() {
        _running.remove(profileId);
      });

  Future<void> _sync() async {
    if (!sameProfile) return;
    var state = await load();
    if (state.isEmpty) return;
    NutriBridgeClient? client;
    try {
      Map<String, dynamic> currentProfile = {};
      try {
        currentProfile = await readProfile();
      } catch (_) {
        // A profile read must not block local tracking or import of existing records.
      }
      if (!sameProfile) return;
      if (state['pending'] == true) {
        if (currentProfile.isNotEmpty) state['profile'] = currentProfile;
        final url = await resolveUrl();
        client = createClient(url);
        final result = await client.request(
          'POST',
          '/api/v1/enroll',
          body: {
            'phone': state['phone'],
            'appToken': state['appToken'],
            'pairingCode': state['code'],
            'profile': state['profile'] ?? {},
            'consent': {
              'granted': true,
              'version': '2026-11-05-cadastro-whatsapp-v2',
            },
          },
        );
        state.addAll({
          'token': result['token'],
          'url': url,
          'pending': false,
          'active': result['consentActive'] == true,
          'verified': result['verified'] == true,
          'codeUntil': DateTime.now()
              .add(
                Duration(seconds: (result['expiresInSeconds'] as num).toInt()),
              )
              .toIso8601String(),
          'message': result['n8nConfigured'] == true
              ? 'Aguarde a mensagem no WhatsApp e responda com o código de confirmação.'
              : 'Seu cadastro está salvo. O acompanhamento será iniciado quando o serviço estiver ativado.',
        });
        state.remove('appToken');
        state.remove('profile');
        await _save(state);
      }
      if (!sameProfile || state['token'] == null) return;
      client ??= createClient(state['url'] as String);
      final me = await client.request(
        'GET',
        '/api/v1/me',
        token: state['token'] as String,
      );
      state.addAll({
        'active': me['consentActive'] == true,
        'verified': me['verified'] == true,
      });
      if (state['active'] == true && currentProfile.isNotEmpty && sameProfile) {
        final encoded = jsonEncode(currentProfile);
        if (state['profileSynced'] != encoded) {
          try {
            final saved = await client.request(
              'PUT',
              '/api/v1/context',
              token: state['token'] as String,
              body: {'profile': currentProfile},
            );
            if (saved['profileUpdated'] == true) {
              state['profileSynced'] = encoded;
            }
          } catch (_) {
            // Retry on next foreground sync; profile updates must not block the diary.
          }
        }
      }
      if (state['verified'] == true) {
        var cursor = (state['cursor'] as num?)?.toInt() ?? 0;
        var cache = List<Map<String, dynamic>>.from(
          (state['records'] as List?)?.map(
                (e) => Map<String, dynamic>.from(e as Map),
              ) ??
              [],
        );
        for (var page = 0; page < 20 && sameProfile; page++) {
          final data = await client.request(
            'GET',
            '/api/v1/records?after=$cursor',
            token: state['token'] as String,
          );
          for (final raw in data['records'] as List) {
            if (!sameProfile) return;
            final record = Map<String, dynamic>.from(raw as Map);
            await _import(record);
            cache.removeWhere((r) => r['id'] == record['id']);
            cache.add(record);
          }
          cursor = (data['nextCursor'] as num).toInt();
          state['cursor'] = cursor;
          state['records'] = cache.length > 200
              ? cache.sublist(cache.length - 200)
              : cache;
          await _save(state);
          if (data['hasMore'] != true) break;
        }
      }
      state['message'] = state['active'] != true
          ? 'Acompanhamento cancelado.'
          : state['verified'] == true
          ? 'Conectado. Converse pelo WhatsApp; os registros confirmados aparecem aqui automaticamente.'
          : 'Aguarde a mensagem no WhatsApp e responda com o código mostrado abaixo.';
      await _save(state);
    } catch (error, stack) {
      onError?.call(error, stack);
      state['message'] = state['pending'] == true
          ? 'Cadastro salvo no celular. O acompanhamento será conectado automaticamente quando o serviço estiver disponível.'
          : 'Sem conexão no momento. Seus registros já recebidos continuam disponíveis.';
      await _save(state);
    } finally {
      client?.close();
    }
  }

  Future<void> _import(Map<String, dynamic> record) async {
    if (!sameProfile) return;
    final date = DateTime.parse(record['occurredAt'] as String).toLocal();
    final id = 'whatsapp:${record['id']}';
    final amount = (record['quantity'] as num?)?.toDouble();
    if (record['kind'] == 'water' &&
        record['unit'] == 'ml' &&
        amount != null &&
        amount > 0 &&
        amount <= 20000) {
      await locator<WaterIntakeRepository>().addEntry(
        WaterIntakeEntity(id: id, dateTime: date, amountMl: amount.round()),
      );
    } else if (record['kind'] == 'weight' &&
        record['unit'] == 'kg' &&
        amount != null &&
        amount > 0 &&
        amount <= 600) {
      final repository = locator<WeightLogRepository>();
      final existing = await repository.getEntry(date);
      if (!sameProfile) return;
      // Never overwrite a manual reading for the same day.
      if (existing == null || (existing.note ?? '').startsWith('WhatsApp:')) {
        await repository.addEntry(
          WeightLogEntity(
            date: date,
            weightKg: amount,
            note: 'WhatsApp: ${record['text']}',
          ),
        );
      }
    } else if (record['kind'] == 'meal' &&
        record['unit'] == 'g' &&
        amount != null &&
        amount > 0 &&
        amount <= 10000 &&
        record['foodCode'] is String) {
      final matches = (await _taco.foods()).where(
        (f) => f.code == record['foodCode'],
      );
      if (!sameProfile) return;
      MealEntity? food = matches.length == 1 ? matches.single : null;
      if ((record['foodCode'] as String).startsWith('off:') ||
          record['estimated'] == true) {
        final raw = record['nutrientsPer100g'];
        if (raw is! Map) return;
        final nutrients = Map<String, dynamic>.from(raw);
        for (final value in nutrients.values) {
          if (value != null &&
              (value is! num || !value.isFinite || value < 0)) {
            return;
          }
        }
        if (nutrients['energy_kcal_100'] is! num ||
            nutrients['energy_kcal_100'] > 950) {
          return;
        }
        final external = (record['foodCode'] as String).startsWith('off:');
        food = MealEntity(
          code: record['foodCode'] as String,
          name: record['estimated'] == true
              ? '${record['text']} (estimativa)'
              : record['foodName'] as String?,
          url: external
              ? 'https://world.openfoodfacts.org/product/${(record['foodCode'] as String).substring(4)}'
              : food?.url,
          mealQuantity: null,
          mealUnit: 'g',
          servingQuantity: null,
          servingUnit: 'g',
          servingSize: null,
          nutriments: MealNutrimentsEntity.fromSpFoodSummary(
            SpFoodDTO.fromJson(nutrients),
          ),
          source: external ? MealSourceEntity.off : MealSourceEntity.fdc,
          backendSource: external ? null : food?.backendSource,
          detailed: true,
        );
      }
      if (food == null) return;
      final hour = date.hour;
      final inferred = hour < 11
          ? IntakeTypeEntity.breakfast
          : hour < 15
          ? IntakeTypeEntity.lunch
          : hour < 19
          ? IntakeTypeEntity.snack
          : IntakeTypeEntity.dinner;
      final type = switch (record['mealType']) {
        'breakfast' => IntakeTypeEntity.breakfast,
        'lunch' => IntakeTypeEntity.lunch,
        'dinner' => IntakeTypeEntity.dinner,
        'snack' => IntakeTypeEntity.snack,
        _ => inferred,
      };
      await locator<IntakeRepository>().addIntake(
        IntakeEntity(
          id: id,
          unit: 'g',
          amount: amount,
          type: type,
          meal: food,
          dateTime: date,
        ),
      );
    }
  }

  Future<void> revoke() async {
    final state = await load();
    if (state['token'] != null) {
      final client = createClient(state['url'] as String);
      try {
        await client.request(
          'DELETE',
          '/api/v1/whatsapp',
          token: state['token'] as String,
        );
      } finally {
        client.close();
      }
    }
    state.addAll({
      'active': false,
      'pending': false,
      'message': 'Acompanhamento cancelado.',
    });
    await _save(state);
  }
}
