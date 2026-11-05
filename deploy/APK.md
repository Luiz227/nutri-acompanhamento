# Compilar e distribuir o APK de teste

Flutter 3.44.6, Dart 3.12.2, Java 21 e Android SDK 36. Android mínimo: 8/API 26.

```text
cp .env.example .env
flutter pub get
flutter gen-l10n
dart run build_runner build --delete-conflicting-outputs
```

Crie um certificado próprio com keytool e configure `android/key.properties`,
ignorado pelo Git, com `storePassword`, `keyPassword`, `keyAlias` e `storeFile`
(caminho absoluto). Preserve o certificado e senha em backup privado: as
atualizações precisam da mesma assinatura. Nunca distribua a chave privada.

```text
flutter build apk --release --flavor develop --split-per-abi --dart-define=ENABLE_SUPABASE_FOOD_SEARCH=false
```

Saída em `build/app/outputs/flutter-apk/`:

O piloto desativa minificação/remoção de recursos para reduzir a memória de
compilação. O APK continua assinado e compilado em modo release; será maior
que uma versão otimizada para distribuição em escala.

- `app-armeabi-v7a-develop-release.apk`: ARM 32 bits.
- `app-arm64-v8a-develop-release.apk`: maioria dos aparelhos Android recentes.
- `app-x86_64-develop-release.apk`: emuladores x86_64.

Confira os nomes no resumo do Flutter. O identificador é
`com.opennutritracker.ont.opennutritracker.nutriteste`, separado do original.
O endereço HTTPS da API é configurável no app; nenhuma chave de serviço vai no APK.

Neste Windows o Java precisa de TEMP/TMP numa pasta curta e
`JAVA_TOOL_OPTIONS=-Djdk.net.unixdomain.tmpdir=CAMINHO_DA_PASTA`. Isso é apenas
um ajuste local de compilação.

## Fora da Play Store

Distribua por GitHub Releases ou HTTPS seu, junto com:

1. APK assinado da arquitetura apropriada.
2. Fonte completa da mesma tag/commit, scripts, manifests/lockfiles e assets.
3. LICENSE, NOTICE.md e avisos de terceiros, inclusive TACO.
4. SHA-256 do APK e identificação do commit/versão Flutter.

Um link apenas para o projeto original não é suficiente para a fonte desta
versão modificada. Uma tag pública do repositório deve acompanhar o release.
Se privado, entregue também o ZIP da fonte aos destinatários; link inacessível
não basta. Não substitua o binário de uma tag por outra fonte.

Referências: https://docs.flutter.dev/deployment/android
https://www.gnu.org/licenses/gpl-3.0.html
