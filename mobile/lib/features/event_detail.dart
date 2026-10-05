import 'package:flutter/material.dart';
import '../app/controller.dart';
import '../core/api_client.dart';
import '../core/models.dart';
import 'common.dart';

class EventDetailPage extends StatefulWidget {
  final AppController controller;
  final int eventId;
  final Player player;
  const EventDetailPage({
    super.key,
    required this.controller,
    required this.eventId,
    required this.player,
  });
  @override
  State<EventDetailPage> createState() => _EventDetailPageState();
}

class _EventDetailPageState extends State<EventDetailPage> {
  Json? detail;
  String? error;
  String status = 'attend';
  String duration = 'full';
  int version = 0;
  bool loading = true, saving = false;
  final note = TextEditingController(), reason = TextEditingController();
  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    note.dispose();
    reason.dispose();
    super.dispose();
  }

  Future<void> load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final data = await widget.controller.repo.detail(
        widget.eventId,
        widget.player.id,
      );
      if (!mounted) return;
      final raw = data['attendance'];
      final old = raw == null ? null : Attendance(Json.from(raw));
      setState(() {
        detail = data;
        status = old?.status ?? 'attend';
        version = old?.version ?? 0;
        duration = old?.duration ?? 'full';
        if (duration == 'half') {
          duration =
              ''; // Require an explicit choice for historical half-day entries.
        }
        note.text = old?.note ?? '';
        reason.text = old?.reason ?? '';
      });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> submit() async {
    if (detail == null) return;
    final practice = detail!['event']['event_type'] == 'practice';
    if (practice && status == 'attend' && duration.isEmpty) {
      message(context, '請重新選擇出席時段');
      return;
    }
    setState(() => saving = true);
    try {
      await widget.controller.repo.api.request(
        'PUT',
        '/api/events/${widget.eventId}/attendance',
        body: {
          'player_id': widget.player.id,
          'attendance_status': status,
          'practice_duration': practice && status == 'attend'
              ? duration
              : 'full',
          'attendance_note': status == 'attend' ? note.text : '',
          'leave_reason': status == 'leave' ? reason.text : '',
          'expected_version': version,
        },
      );
      if (mounted) {
        message(context, '活動回覆已保存');
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        message(context, '$e');
        if (e is ApiException && (e.status == 409 || e.status == 403)) {
          await load();
        }
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> roster() async {
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) =>
            RosterPage(controller: widget.controller, eventId: widget.eventId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('活動詳情')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('活動詳情')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(error!),
              TextButton(onPressed: load, child: const Text('重試')),
            ],
          ),
        ),
      );
    }
    final data = detail!;
    final event = TeamEvent(Json.from(data['event']));
    final eligibility = Json.from(data['eligibility']);
    final canReply = eligibility['can_reply'] == true;
    final matches = (data['matches'] as List).map((m) => Json.from(m)).toList();
    return Scaffold(
      appBar: AppBar(title: Text(event.title)),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            widget.player.label,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          InfoCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(event.date),
                Text(event.location),
                Text('集合：${event.meetTime}'),
                ...matches.indexed.map(
                  (m) => Text(
                    '第 ${m.$1 + 1} 場　${m.$2['game_time_tbd'] == true
                        ? '未定'
                        : text(m.$2['game_time']).isEmpty
                        ? '未定'
                        : m.$2['game_time']}　對手：${text(m.$2['opponent']).isEmpty ? '未定' : m.$2['opponent']}',
                  ),
                ),
                Text(
                  '回覆截止：${text(data['event']['response_deadline']).isEmpty ? '未設定' : data['event']['response_deadline']}',
                ),
              ],
            ),
          ),
          if (event.survey)
            OutlinedButton(onPressed: roster, child: const Text('查看出席名單')),
          if (!canReply)
            InfoCard(
              child: Text(
                event.survey
                    ? '活動已關閉或超過回覆期限。${data['attendance'] == null ? '' : '原回覆：${Attendance(Json.from(data['attendance'])).label}'}'
                    : '此活動只公告，不需要回覆',
              ),
            ),
          if (canReply) ...[
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: status,
              decoration: const InputDecoration(labelText: '出席狀態'),
              items: const [
                DropdownMenuItem(value: 'attend', child: Text('出席')),
                DropdownMenuItem(value: 'leave', child: Text('請假')),
                DropdownMenuItem(value: 'maybe', child: Text('未確定')),
              ],
              onChanged: saving
                  ? null
                  : (s) => setState(() {
                      status = s!;
                      if (status != 'attend') note.clear();
                      if (status != 'leave') reason.clear();
                    }),
            ),
            const SizedBox(height: 16),
            if (event.type == 'practice' && status == 'attend') ...[
              DropdownButtonFormField<String>(
                initialValue: duration.isEmpty ? null : duration,
                decoration: const InputDecoration(labelText: '練球出席時段'),
                items: const [
                  DropdownMenuItem(value: 'full', child: Text('全天')),
                  DropdownMenuItem(
                    value: 'morning_leave',
                    child: Text('下午出席（上午請假）'),
                  ),
                  DropdownMenuItem(
                    value: 'afternoon_leave',
                    child: Text('上午出席（下午請假）'),
                  ),
                ],
                onChanged: saving ? null : (d) => setState(() => duration = d!),
              ),
              const SizedBox(height: 16),
            ],
            if (status == 'attend')
              TextField(
                controller: note,
                enabled: !saving,
                maxLines: 4,
                maxLength: 2000,
                decoration: const InputDecoration(
                  labelText: '出席備註（選填）',
                  hintText: '可說明部分出席、晚到或其他安排',
                ),
              ),
            if (status == 'leave')
              TextField(
                controller: reason,
                enabled: !saving,
                maxLines: 4,
                maxLength: 2000,
                decoration: const InputDecoration(labelText: '請假原因（選填）'),
              ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: saving ? null : submit,
              child: Text(saving ? '保存中…' : '保存回覆'),
            ),
          ],
        ],
      ),
    );
  }
}

class RosterPage extends StatefulWidget {
  final AppController controller;
  final int eventId;
  const RosterPage({
    super.key,
    required this.controller,
    required this.eventId,
  });
  @override
  State<RosterPage> createState() => _RosterPageState();
}

class _RosterPageState extends State<RosterPage> {
  late Future<List<Json>> future = widget.controller.repo.roster(
    widget.eventId,
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('活動出席名單')),
    body: FutureBuilder<List<Json>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('${snapshot.error}'),
                TextButton(
                  onPressed: () => setState(
                    () =>
                        future = widget.controller.repo.roster(widget.eventId),
                  ),
                  child: const Text('重試'),
                ),
              ],
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: snapshot.data!
              .map(
                (p) => InfoCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(Player(p).label),
                      Text(Attendance(p).label),
                      if (text(p['attendance_note']).isNotEmpty)
                        Text('備註：${p['attendance_note']}'),
                      if (text(p['leave_reason']).isNotEmpty)
                        Text('請假：${p['leave_reason']}'),
                    ],
                  ),
                ),
              )
              .toList(),
        );
      },
    ),
  );
}
