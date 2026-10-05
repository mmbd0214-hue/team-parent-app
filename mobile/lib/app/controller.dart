import 'package:flutter/foundation.dart';
import '../core/models.dart';
import '../core/repository.dart';
import '../core/selection_store.dart';

class AppController extends ChangeNotifier {
  final TeamRepository repo;
  final PlayerSelectionStore? selections;
  Json? parent;
  List<Player> players = [];
  Player? selected;
  List<TeamEvent> events = [];
  Map<int, Attendance> attendance = {};
  List<Payment> payments = [];
  List<Announcement> announcements = [];
  int? announcementCursor;
  bool loadingMore = false;
  Json seen = {};
  bool loading = false;
  String? error;
  int _generation = 0;
  void Function()? onReset;
  AppController(this.repo, {this.selections}) {
    repo.api.onExpired = reset;
  }
  bool get isAdmin => parent?['is_admin'] == true;
  bool hasNew(String kind, Iterable<int> ids, [String scope = '']) =>
      ids.any((id) => id > number(seen['$kind:$scope']));

  void reset() {
    _generation++;
    parent = null;
    players = [];
    selected = null;
    events = [];
    attendance = {};
    payments = [];
    announcements = [];
    announcementCursor = null;
    loadingMore = false;
    seen = {};
    loading = false;
    error = null;
    onReset?.call();
    notifyListeners();
  }

  Future<void> loadIdentity() async {
    final generation = _generation;
    final identity = await repo.me();
    final identitySeen = await repo.seen();
    final remembered = await selections?.read(number(identity['parent']['id']));
    if (generation != _generation) return;
    parent = Json.from(identity['parent']);
    players = (identity['players'] as List)
        .map((e) => Player(Json.from(e)))
        .toList();
    selected =
        players
            .where((p) => p.id == (selected?.id ?? remembered))
            .firstOrNull ??
        players.firstOrNull;
    seen = identitySeen;
    notifyListeners();
    await refresh();
  }

  Future<void> select(Player player) async {
    _generation++;
    selected = player;
    events = [];
    attendance = {};
    payments = [];
    notifyListeners();
    if (parent != null) {
      await selections?.write(number(parent!['id']), player.id);
    }
    await refresh();
  }

  Future<void> refresh() async {
    final generation = ++_generation;
    final id = selected?.id;
    loading = true;
    error = null;
    notifyListeners();
    try {
      final results = await Future.wait<dynamic>([
        if (id != null) repo.events(id),
        if (id != null) repo.attendance(id),
        if (id != null) repo.payments(id),
        repo.announcements(),
        repo.seen(),
      ]);
      if (generation != _generation) return;
      if (id != null) {
        events = results[0];
        attendance = results[1];
        payments = results[2];
      }
      final announcementPage = results[id != null ? 3 : 0] as Json;
      announcements = (announcementPage['items'] as List)
          .map((e) => Announcement(Json.from(e)))
          .toList();
      announcementCursor = announcementPage['next_cursor'] as int?;
      seen = results[id != null ? 4 : 1];
    } catch (e) {
      if (generation == _generation) error = '$e';
    } finally {
      if (generation == _generation) {
        loading = false;
        notifyListeners();
      }
    }
  }

  Future<void> mark(String kind) async {
    if (loading || error != null) return;
    final generation = _generation;
    final scope = kind == 'payment' ? '${selected?.id ?? ''}' : '';
    final ids = switch (kind) {
      'announcement' => announcements.map((a) => a.id),
      'payment' => payments.map((p) => p.id),
      _ => events.map((e) => e.id),
    };
    final maxId = ids.fold<int>(0, (m, id) => id > m ? id : m);
    if (maxId <= number(seen['$kind:$scope'])) return;
    try {
      await repo.markSeen(kind, maxId, scope);
      if (generation != _generation) return;
      seen['$kind:$scope'] = maxId > number(seen['$kind:$scope'])
          ? maxId
          : seen['$kind:$scope'];
      notifyListeners();
    } catch (_) {
      /* Retain badge; retry on next successful page display. */
    }
  }

  Future<void> moreAnnouncements() async {
    if (announcementCursor == null || loadingMore) return;
    final generation = _generation;
    loadingMore = true;
    notifyListeners();
    try {
      final next = await repo.announcements(cursor: announcementCursor);
      if (generation != _generation) return;
      final ids = announcements.map((a) => a.id).toSet();
      announcements.addAll(
        (next['items'] as List)
            .map((e) => Announcement(Json.from(e)))
            .where((a) => !ids.contains(a.id)),
      );
      announcementCursor = next['next_cursor'] as int?;
    } finally {
      loadingMore = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    try {
      await repo.api.request('POST', '/api/auth/logout');
    } finally {
      await repo.api.clear();
      reset();
    }
  }
}
