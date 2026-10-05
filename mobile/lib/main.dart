import 'dart:async';
import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_line_sdk/flutter_line_sdk.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'app/controller.dart';
import 'core/api_client.dart';
import 'core/config.dart';
import 'core/models.dart';
import 'core/repository.dart';
import 'core/selection_store.dart';
import 'features/shell.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const TeamParentApp());
}

class TeamParentApp extends StatefulWidget {
  const TeamParentApp({super.key});
  @override
  State<TeamParentApp> createState() => _TeamParentAppState();
}

class _TeamParentAppState extends State<TeamParentApp> {
  late final ApiClient api = ApiClient(
    AppConfig.apiUrl,
    SecureSessionStore(namespace: AppConfig.apiUrl),
  );
  late final AppController controller = AppController(
    TeamRepository(api),
    selections: SecurePlayerSelectionStore(AppConfig.apiUrl),
  );
  final AppLinks links = AppLinks();
  StreamSubscription<Uri>? subscription;
  bool busy = true;
  bool lineReady = false;
  String? startupError;
  int? pendingEvent;
  Json remoteConfig = {};
  bool blocked = false;

  @override
  void initState() {
    super.initState();
    controller.onReset = () {
      if (mounted) setState(() => pendingEvent = null);
    };
    subscription = links.uriLinkStream.listen(handleLink);
    bootstrap();
  }

  void handleLink(Uri uri) {
    final base = Uri.tryParse(AppConfig.apiUrl);
    if (uri.scheme != 'qingshan' &&
        (uri.scheme != 'https' || uri.host != base?.host)) {
      return;
    }
    final segments = uri.pathSegments;
    final id = int.tryParse(
      uri.queryParameters['event'] ??
          (segments.length == 2 && segments.first == 'events'
              ? segments.last
              : uri.scheme == 'qingshan' &&
                    uri.host == 'events' &&
                    segments.length == 1
              ? segments.first
              : ''),
    );
    if (id != null && id > 0 && mounted) setState(() => pendingEvent = id);
  }

  Future<void> bootstrap() async {
    setState(() {
      busy = true;
      startupError = null;
    });
    try {
      AppConfig.validate();
      blocked = false;
      await api.restore();
      remoteConfig = Json.from(
        await api.request('GET', '/api/app-config', authenticated: false),
      );
      if (remoteConfig['maintenance'] == true) {
        blocked = true;
        throw StateError('系統維護中，請稍後重試');
      }
      if (AppConfig.isOlder(
        AppConfig.version,
        text(remoteConfig['minimum_version']),
      )) {
        blocked = true;
        throw StateError('請先至商店更新 App，再繼續使用');
      }
      if (api.hasSession) {
        try {
          await controller.loadIdentity();
        } on ApiException catch (e) {
          if (e.status == 401) {
            await api.clear();
            controller.reset();
          } else {
            rethrow;
          }
        }
      }
      final link = await links.getInitialLink();
      if (link != null) handleLink(link);
    } catch (e) {
      startupError = '$e';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<bool> reauthenticate() async {
    final original = controller.parent;
    if (original == null) return false;
    Json result;
    if (original['line_user_id'] == null) {
      final challenge = Json.from(
        await api.request(
          'POST',
          '/api/auth/apple/challenge',
          authenticated: false,
        ),
      );
      final credential = await SignInWithApple.getAppleIDCredential(
        scopes: [],
        nonce: text(challenge['nonce']),
      );
      result = Json.from(
        await api.request(
          'POST',
          '/api/auth/apple',
          authenticated: false,
          body: {
            'identity_token': credential.identityToken,
            'authorization_code': credential.authorizationCode,
            'challenge': challenge['challenge'],
          },
        ),
      );
    } else {
      if (!lineReady) {
        await LineSDK.instance.setup(AppConfig.lineChannel);
        lineReady = true;
      }
      final credential = await LineSDK.instance.login(
        scopes: ['profile', 'openid'],
      );
      result = Json.from(
        await api.request(
          'POST',
          '/api/auth/line',
          authenticated: false,
          body: {'access_token': credential.accessToken.value},
        ),
      );
    }
    if (number(result['parent']['id']) != number(original['id'])) {
      throw StateError('請使用原帳號重新驗證');
    }
    await api.accept(result);
    return true;
  }

  Future<void> login({bool mock = false, bool apple = false}) async {
    setState(() {
      busy = true;
      startupError = null;
    });
    try {
      Json result;
      if (apple) {
        final challenge = Json.from(
          await api.request(
            'POST',
            '/api/auth/apple/challenge',
            authenticated: false,
          ),
        );
        final credential = await SignInWithApple.getAppleIDCredential(
          scopes: [AppleIDAuthorizationScopes.fullName],
          nonce: text(challenge['nonce']),
        );
        result = Json.from(
          await api.request(
            'POST',
            '/api/auth/apple',
            authenticated: false,
            body: {
              'identity_token': credential.identityToken,
              'authorization_code': credential.authorizationCode,
              'challenge': challenge['challenge'],
            },
          ),
        );
      } else {
        var lineToken = 'mock';
        if (!mock) {
          if (AppConfig.lineChannel.isEmpty) {
            throw StateError('尚未設定 LINE_CHANNEL_ID');
          }
          if (!lineReady) {
            await LineSDK.instance.setup(AppConfig.lineChannel);
            lineReady = true;
          }
          final credential = await LineSDK.instance.login(
            scopes: ['profile', 'openid'],
          );
          lineToken = credential.accessToken.value;
        } else if (!AppConfig.allowMock) {
          throw StateError('此版本無測試登入');
        }
        result = Json.from(
          await api.request(
            'POST',
            '/api/auth/line',
            body: {'access_token': lineToken},
            authenticated: false,
          ),
        );
      }
      await api.accept(result);
      await controller.loadIdentity();
    } catch (e) {
      startupError = '$e';
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    subscription?.cancel();
    controller.dispose();
    api.httpClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    locale: const Locale('zh', 'TW'),
    supportedLocales: const [Locale('zh', 'TW')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    title: '青山棒球家長',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff23644b)),
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xfff4f6f3),
      inputDecorationTheme: const InputDecorationTheme(
        border: OutlineInputBorder(),
      ),
    ),
    home: AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        if (busy) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (blocked) {
          return Scaffold(
            body: SafeArea(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(startupError ?? '暫時無法使用'),
                    TextButton(onPressed: bootstrap, child: const Text('重新確認')),
                    TextButton(
                      onPressed: () => openTrustedUrl(
                        context,
                        text(remoteConfig['support_url']),
                      ),
                      child: const Text('聯絡球隊'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }
        if (controller.parent != null) {
          return TeamShell(
            reauthenticate: reauthenticate,
            controller: controller,
            remoteConfig: remoteConfig,
            pendingEvent: pendingEvent,
            consumeEvent: () {
              if (mounted) setState(() => pendingEvent = null);
            },
          );
        }
        return Scaffold(
          body: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(28),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 440),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(
                        Icons.sports_baseball,
                        size: 72,
                        color: Color(0xff23644b),
                      ),
                      const SizedBox(height: 24),
                      const Text(
                        '青山社區棒球隊',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text('活動回覆、球隊公告與繳費紀錄', textAlign: TextAlign.center),
                      const SizedBox(height: 28),
                      if (startupError != null) ...[
                        Text(
                          startupError!,
                          style: const TextStyle(color: Colors.red),
                        ),
                        const SizedBox(height: 16),
                      ],
                      FilledButton(
                        onPressed: () => login(),
                        child: const Text('使用 LINE 登入'),
                      ),
                      if (AppConfig.enableApple)
                        OutlinedButton(
                          onPressed: () => login(apple: true),
                          child: const Text('使用 Apple 登入'),
                        ),
                      if (AppConfig.allowMock)
                        TextButton(
                          onPressed: () => login(mock: true),
                          child: const Text('開發環境測試登入'),
                        ),
                      TextButton(
                        onPressed: bootstrap,
                        child: const Text('重新連線'),
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        '首次登入後，請使用球隊提供的綁定碼連結球員。',
                        textAlign: TextAlign.center,
                      ),
                      TextButton(
                        onPressed: () => openTrustedUrl(
                          context,
                          text(remoteConfig['privacy_url']),
                        ),
                        child: const Text('隱私政策'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    ),
  );
}
