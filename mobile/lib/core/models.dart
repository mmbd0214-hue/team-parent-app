typedef Json = Map<String, dynamic>;
int number(dynamic value) =>
    value is num ? value.toInt() : int.tryParse('$value') ?? 0;
String text(dynamic value) => value?.toString() ?? '';

class Player {
  final int id;
  final String name, team, jersey;
  Player(Json j)
    : id = number(j['id']),
      name = text(j['name']),
      team = text(j['team']),
      jersey = text(j['number']);
  String get label => '$name · $team${jersey.isEmpty ? '' : ' #$jersey'}';
}

class Attendance {
  final int eventId, version;
  final String status, duration, note, reason;
  Attendance(Json j)
    : eventId = number(j['event_id']),
      version = number(j['version']),
      status = text(j['attendance_status']),
      duration = text(j['practice_duration']),
      note = text(j['attendance_note']),
      reason = text(j['leave_reason']);
  String get label => switch (status) {
    'leave' => '請假',
    'maybe' => '未確定',
    'attend' => switch (duration) {
      'morning_leave' => '下午出席',
      'afternoon_leave' => '上午出席',
      'half' => '半天（舊資料）',
      _ => '出席',
    },
    _ => '尚未回覆',
  };
}

class TeamEvent {
  final int id;
  final String title, date, location, type, meetTime;
  final bool survey;
  final List<Json> matches;
  TeamEvent(Json j)
    : id = number(j['id']),
      title = text(j['title']),
      date = text(j['event_date']),
      location = text(j['location']),
      type = text(j['event_type']),
      meetTime = j['meet_time_tbd'] == true
          ? '未定'
          : (text(j['meet_time']).isEmpty ? '未定' : text(j['meet_time'])),
      survey = j['survey_enabled'] != false,
      matches = (j['matches'] as List? ?? [])
          .map((e) => Json.from(e as Map))
          .toList();
}

class Payment {
  final int id, amount, version;
  final String title, dueDate, status, note, method, transferDate, last5;
  Payment(Json j)
    : id = number(j['id']),
      amount = number(j['amount']),
      version = number(j['version']),
      title = text(j['title']),
      dueDate = text(j['due_date']),
      status = text(j['status']),
      note = text(j['note']),
      method = text(j['payment_method']),
      transferDate = text(j['transfer_date']),
      last5 = text(j['transfer_account_last5']);
  String get statusLabel => switch (status) {
    'paid' => '已繳',
    'pending' => '待確認',
    'unpaid' => '未繳',
    _ => '狀態未知',
  };
}

class Announcement {
  final int id;
  final String title, message, created;
  Announcement(Json j)
    : id = number(j['id']),
      title = text(j['title']),
      message = text(j['message_text']),
      created = text(j['created_at']);
}
