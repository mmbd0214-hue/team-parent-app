class AppConfig {
  static const apiUrl = String.fromEnvironment('API_BASE_URL');
  static const lineChannel = String.fromEnvironment('LINE_CHANNEL_ID');
  static const environment = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'production',
  );
  static const enableApple = bool.fromEnvironment('ENABLE_APPLE_LOGIN');
  static const allowMock = bool.fromEnvironment('ALLOW_MOCK_LOGIN');
  static const version = '1.0.0';

  static bool isOlder(String current, String minimum) {
    final a = current.split('.').map((s) => int.tryParse(s) ?? 0).toList();
    final b = minimum.split('.').map((s) => int.tryParse(s) ?? 0).toList();
    for (var i = 0; i < 3; i++) {
      final left = i < a.length ? a[i] : 0, right = i < b.length ? b[i] : 0;
      if (left != right) return left < right;
    }
    return false;
  }

  static void validate() {
    final uri = Uri.tryParse(apiUrl);
    if (uri == null ||
        !uri.hasAuthority ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        uri.path.isNotEmpty ||
        !['https', 'http'].contains(uri.scheme) ||
        (uri.scheme != 'https' && environment != 'development')) {
      throw StateError('請設定有效的 API_BASE_URL（正式環境必須使用 HTTPS）');
    }
    if (allowMock && environment != 'development') {
      throw StateError('正式環境不得啟用測試登入');
    }
  }
}
