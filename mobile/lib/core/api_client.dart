import 'dart:async';
import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

abstract class SessionStore {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  final FlutterSecureStorage storage;
  final String namespace;
  SecureSessionStore({
    this.storage = const FlutterSecureStorage(),
    this.namespace = 'default',
  });
  String get key => 'team_session:$namespace';
  @override
  Future<String?> read() => storage.read(key: key);
  @override
  Future<void> write(String value) => storage.write(key: key, value: value);
  @override
  Future<void> clear() => storage.delete(key: key);
}

class ApiClient {
  final String baseUrl;
  final http.Client httpClient;
  final SessionStore store;
  String? _access;
  String? _refresh;
  int _generation = 0;
  Future<void>? _refreshing;
  Future<void> _storageWork = Future.value();
  void Function()? onExpired;
  ApiClient(this.baseUrl, this.store, {http.Client? client})
    : httpClient = client ?? http.Client();
  bool get hasSession => _access != null;

  Future<void> _persist(Future<void> Function() work) {
    final next = _storageWork.then((_) => work());
    _storageWork = next.catchError((Object _) {});
    return next;
  }

  Future<void> restore() async {
    final value = await store.read();
    if (value == null) return;
    try {
      final data = jsonDecode(value) as Map<String, dynamic>;
      _access = data['access_token'] as String;
      _refresh = data['refresh_token'] as String;
    } catch (_) {
      await clear();
    }
  }

  Future<void> accept(Map<String, dynamic> data) async {
    _generation++;
    _access = data['access_token'] as String;
    _refresh = data['refresh_token'] as String;
    final value = jsonEncode({
      'access_token': _access,
      'refresh_token': _refresh,
    });
    await _persist(() => store.write(value));
  }

  Future<void> clear() async {
    _generation++;
    _access = null;
    _refresh = null;
    await _persist(store.clear);
  }

  Future<void> _doRefresh(int generation) async {
    final result =
        await request(
              'POST',
              '/api/auth/refresh',
              body: {'refresh_token': _refresh},
              authenticated: false,
            )
            as Map<String, dynamic>;
    if (_generation != generation) throw ApiException(401, '登入已變更');
    _access = result['access_token'] as String;
    _refresh = result['refresh_token'] as String;
    final value = jsonEncode({
      'access_token': _access,
      'refresh_token': _refresh,
    });
    await _persist(() async {
      if (_generation == generation) await store.write(value);
    });
  }

  Future<void> _ensureRefresh() async {
    final generation = _generation;
    try {
      final pending = _refreshing ??= _doRefresh(generation);
      await pending;
    } on ApiException catch (e) {
      if (e.status == 401 && generation == _generation) {
        await clear();
        onExpired?.call();
      }
      rethrow;
    } finally {
      _refreshing = null;
    }
  }

  Future<dynamic> request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
    bool retry = true,
  }) async {
    final generation = _generation;
    final requestAccess = _access;
    final uri = Uri.parse('$baseUrl$path');
    final req = http.Request(method, uri);
    req.headers['Content-Type'] = 'application/json';
    if (authenticated && _access != null) {
      req.headers['Authorization'] = 'Bearer $_access';
    }
    if (body != null) req.body = jsonEncode(body);
    http.Response response;
    try {
      response = await http.Response.fromStream(
        await httpClient.send(req).timeout(const Duration(seconds: 20)),
      ).timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw ApiException(0, '連線逾時。提交結果請重新整理確認。');
    } on http.ClientException {
      throw ApiException(0, '無法連線，請檢查網路後重試');
    }
    if (authenticated && generation != _generation) {
      throw ApiException(401, '登入已變更');
    }
    if (response.statusCode == 401 &&
        authenticated &&
        retry &&
        _refresh != null) {
      if (_access == requestAccess) await _ensureRefresh();
      return request(
        method,
        path,
        body: body,
        authenticated: true,
        retry: false,
      );
    }
    dynamic data;
    try {
      data = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      data = null;
    }
    if (response.statusCode >= 400) {
      final detail = data is Map ? data['detail'] : null;
      if (response.statusCode == 401 && authenticated) {
        await clear();
        onExpired?.call();
      }
      throw ApiException(
        response.statusCode,
        detail is String ? detail : '操作失敗，請重新整理後重試',
      );
    }
    return data;
  }
}
