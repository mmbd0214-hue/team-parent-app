import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:team_parent/core/api_client.dart';
import 'package:team_parent/core/models.dart';
import 'package:team_parent/core/repository.dart';
import 'package:team_parent/app/controller.dart';
import 'package:team_parent/features/binding.dart';

class MemoryStore implements SessionStore {
  String? value;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String v) async {
    value = v;
  }

  @override
  Future<void> clear() async {
    value = null;
  }
}

void main() {
  test(
    'Concurrent expired reads share one refresh and rotate stored credentials',
    () async {
      var refreshes = 0;
      final store = MemoryStore();
      final expired = Completer<void>();
      var reads = 0;
      final api = ApiClient(
        'https://team.test',
        store,
        client: MockClient((request) async {
          if (request.url.path == '/api/auth/refresh') {
            refreshes++;
            return http.Response(
              jsonEncode({'access_token': 'new', 'refresh_token': 'rotated'}),
              200,
            );
          }
          if (request.headers['Authorization'] == 'Bearer old') {
            reads++;
            if (reads == 2) expired.complete();
            await expired.future;
            return http.Response('{"detail":"expired"}', 401);
          }
          return http.Response('[]', 200);
        }),
      );
      await api.accept({'access_token': 'old', 'refresh_token': 'original'});
      await Future.wait([api.request('GET', '/a'), api.request('GET', '/b')]);
      expect(refreshes, 1);
      expect(jsonDecode(store.value!)['refresh_token'], 'rotated');
    },
  );

  test(
    'Logout while refresh is in flight cannot restore credentials',
    () async {
      final entered = Completer<void>(), result = Completer<http.Response>();
      final store = MemoryStore();
      final api = ApiClient(
        'https://team.test',
        store,
        client: MockClient((request) async {
          if (request.url.path.endsWith('refresh')) {
            entered.complete();
            return result.future;
          }
          return http.Response('{"detail":"expired"}', 401);
        }),
      );
      await api.accept({'access_token': 'old', 'refresh_token': 'original'});
      final pending = api.request('GET', '/a');
      final assertion = expectLater(pending, throwsA(isA<ApiException>()));
      await entered.future;
      await api.clear();
      result.complete(
        http.Response('{"access_token":"new","refresh_token":"rotated"}', 200),
      );
      await assertion;
      expect(store.value, isNull);
      expect(api.hasSession, false);
    },
  );

  test('Selecting B discards a late response for A', () async {
    final lateA = Completer<http.Response>();
    final api = ApiClient(
      'https://team.test',
      MemoryStore(),
      client: MockClient((r) async {
        if (r.url.path == '/api/events') {
          if (r.url.queryParameters['player_id'] == '1') return lateA.future;
          return http.Response('[{"id":22,"title":"B activity"}]', 200);
        }
        if (r.url.path == '/api/content-seen') return http.Response('{}', 200);
        if (r.url.path == '/api/announcements') {
          return http.Response('{"items":[],"next_cursor":null}', 200);
        }
        return http.Response('[]', 200);
      }),
    );
    final c = AppController(TeamRepository(api));
    final first = c.select(Player({'id': 1, 'name': 'A'}));
    await c.select(Player({'id': 2, 'name': 'B'}));
    lateA.complete(http.Response('[{"id":11,"title":"A activity"}]', 200));
    await first;
    expect(c.selected?.id, 2);
    expect(c.events.single.id, 22);
    c.dispose();
  });

  test(
    'Payment last-five digits preserve leading zeros; null response means unreplied',
    () {
      expect(Payment({'transfer_account_last5': '00123'}).last5, '00123');
      expect(Attendance({}).label, '尚未回覆');
      expect(Attendance({'attendance_status': 'maybe'}).label, '未確定');
      expect(
        Attendance({
          'attendance_status': 'attend',
          'practice_duration': 'morning_leave',
        }).label,
        '下午出席',
      );
    },
  );

  testWidgets('Binding requires a successful preview before confirmation', (
    tester,
  ) async {
    final calls = <String>[];
    final c = AppController(
      TeamRepository(
        ApiClient(
          'https://team.test',
          MemoryStore(),
          client: MockClient((r) async {
            calls.add(r.url.path);
            return http.Response(
              jsonEncode({
                'player': {'id': 1, 'name': '測試球員', 'team': 'U10'},
                'linked_parents': 1,
                'max_parents': 2,
                'already_bound': false,
                'can_bind': true,
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }),
        ),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: BindingPage(controller: c)));
    expect(find.text('確認綁定'), findsNothing);
    await tester.enterText(find.byType(TextField), 'AB1234');
    await tester.tap(find.text('查詢球員'));
    await tester.pumpAndSettle();
    expect(find.text('確認綁定'), findsOneWidget);
    expect(calls, ['/api/bind/preview']);
    await tester.enterText(find.byType(TextField), 'ZZ1234');
    await tester.pump();
    expect(find.text('確認綁定'), findsNothing);
    c.dispose();
  });
}
