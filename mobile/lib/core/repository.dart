import 'api_client.dart';
import 'models.dart';

class TeamRepository {
  final ApiClient api;
  TeamRepository(this.api);
  Future<Json> me() async =>
      Json.from(await api.request('GET', '/api/me') as Map);
  Future<List<TeamEvent>> events(int id) async =>
      (await api.request('GET', '/api/events?player_id=$id') as List)
          .map((e) => TeamEvent(Json.from(e)))
          .toList();
  Future<Map<int, Attendance>> attendance(int id) async {
    final rows =
        await api.request('GET', '/api/players/$id/attendance') as List;
    return {
      for (final row in rows)
        number(row['event_id']): Attendance(Json.from(row)),
    };
  }

  Future<List<Payment>> payments(int id) async =>
      (await api.request('GET', '/api/players/$id/payments') as List)
          .map((e) => Payment(Json.from(e)))
          .toList();
  Future<Json> detail(int event, int player) async => Json.from(
    await api.request('GET', '/api/events/$event?player_id=$player') as Map,
  );
  Future<List<Json>> roster(int event) async =>
      (await api.request('GET', '/api/events/$event/attendance-summary')
              as List)
          .map((e) => Json.from(e))
          .toList();
  Future<Json> announcements({int? cursor}) async => Json.from(
    await api.request(
          'GET',
          '/api/announcements?limit=100${cursor == null ? '' : '&cursor=$cursor'}',
        )
        as Map,
  );
  Future<Json> seen() async =>
      Json.from(await api.request('GET', '/api/content-seen') as Map);
  Future<void> markSeen(String kind, int id, [String scope = '']) async =>
      api.request(
        'POST',
        '/api/content-seen',
        body: {'kind': kind, 'scope': scope, 'last_seen_id': id},
      );
}
