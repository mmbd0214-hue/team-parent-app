import 'dart:async';
import 'package:flutter/material.dart';
import '../app/controller.dart';
import '../core/config.dart';
import '../core/models.dart';
import 'binding.dart';
import 'common.dart';
import 'event_detail.dart';
import 'payment_form.dart';
export 'common.dart' show openTrustedUrl;

class TeamShell extends StatefulWidget {
  final AppController controller;
  final Json remoteConfig;
  final int? pendingEvent;
  final VoidCallback consumeEvent;
  final Future<bool> Function() reauthenticate;
  const TeamShell({
    super.key,
    required this.controller,
    required this.remoteConfig,
    required this.pendingEvent,
    required this.consumeEvent,
    required this.reauthenticate,
  });
  @override
  State<TeamShell> createState() => _TeamShellState();
}

class _TeamShellState extends State<TeamShell> with WidgetsBindingObserver {
  int page = 0;
  bool navigating = false;
  bool profileBusy = false;
  AppController get c => widget.controller;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    scheduleLink();
  }

  @override
  void didUpdateWidget(covariant TeamShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    scheduleLink();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(refreshIdentity());
  }

  Future<void> refreshIdentity() async {
    try {
      await c.loadIdentity();
    } catch (e) {
      if (mounted) message(context, '$e');
    }
  }

  void scheduleLink() {
    if (widget.pendingEvent == null || navigating || c.selected == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted || navigating || widget.pendingEvent == null) return;
      navigating = true;
      final event = widget.pendingEvent!;
      widget.consumeEvent();
      await openEvent(event, choosePlayer: true);
      navigating = false;
    });
  }

  Future<void> openEvent(int event, {bool choosePlayer = false}) async {
    var player = c.selected;
    if (choosePlayer && c.players.length > 1) {
      player = await showDialog<Player>(
        context: context,
        builder: (ctx) => SimpleDialog(
          title: const Text('選擇參加球員'),
          children: c.players
              .map(
                (p) => SimpleDialogOption(
                  onPressed: () => Navigator.pop(ctx, p),
                  child: Text(p.label),
                ),
              )
              .toList(),
        ),
      );
    }
    if (player == null || !mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) =>
            EventDetailPage(controller: c, eventId: event, player: player!),
      ),
    );
    if (mounted) await c.refresh();
  }

  Future<void> changePage(int index) async {
    setState(() => page = index);
    if (index == 0 || index == 1 || index == 3) {
      await c.refresh();
      if (mounted) {
        await c.mark(
          index == 0
              ? 'event'
              : index == 1
              ? 'announcement'
              : 'payment',
        );
      }
    }
  }

  Widget eventCard(TeamEvent event) => InfoCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(event.date, style: Theme.of(context).textTheme.labelLarge),
        Text(event.title, style: Theme.of(context).textTheme.titleMedium),
        Text('${event.location}\n集合：${event.meetTime}'),
        if (event.survey)
          Chip(label: Text(c.attendance[event.id]?.label ?? '尚未回覆')),
        TextButton(
          onPressed: () => openEvent(event.id),
          child: Text(event.survey ? '查看活動 / 回覆' : '查看活動公告'),
        ),
      ],
    ),
  );

  Widget paymentCard(Payment p) => InfoCard(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                p.title,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            Text('NT\$ ${p.amount}'),
          ],
        ),
        Text('期限：${p.dueDate.isEmpty ? '未設定' : p.dueDate}'),
        Chip(label: Text(p.statusLabel)),
        if (p.note.isNotEmpty) Text(p.note),
        if (p.method.isNotEmpty)
          Text(
            '${p.method == 'cash' ? '現金' : '轉帳'} · ${p.transferDate}${p.method == 'transfer' ? ' · 後五碼 ${p.last5}' : ''}',
          ),
        if (p.status == 'unpaid' || p.status == 'pending')
          TextButton(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => PaymentForm(controller: c, payment: p),
                ),
              );
              if (mounted) await c.refresh();
            },
            child: Text(p.status == 'pending' ? '修改繳費資料' : '回報繳費'),
          ),
      ],
    ),
  );

  List<Widget> body() => switch (page) {
    0 => [
      if (c.hasNew('announcement', c.announcements.map((a) => a.id)))
        InfoCard(
          child: TextButton(
            onPressed: () => changePage(1),
            child: const Text('有新公告，點此查看'),
          ),
        ),
      Section(
        '近期活動',
        c.events.isEmpty
            ? [const Text('目前沒有受邀活動')]
            : c.events.map(eventCard).toList(),
      ),
      Section(
        '待繳與待確認',
        c.payments
            .where((p) => p.status != 'paid')
            .take(3)
            .map(paymentCard)
            .toList(),
      ),
    ],
    1 => [
      Section(
        '球隊公告',
        c.announcements.isEmpty
            ? [const Text('目前沒有公告')]
            : c.announcements
                  .map(
                    (a) => InfoCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            a.title.isEmpty ? '球隊公告' : a.title,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          Text(a.created.split('T').first),
                          const SizedBox(height: 12),
                          SelectableText(a.message),
                          ...RegExp(r'https://[^\s<>]+')
                              .allMatches(a.message)
                              .map(
                                (m) => TextButton(
                                  onPressed: () =>
                                      openTrustedUrl(context, m.group(0)!),
                                  child: Text(m.group(0)!),
                                ),
                              ),
                        ],
                      ),
                    ),
                  )
                  .toList(),
      ),
      if (c.announcementCursor != null)
        OutlinedButton(
          onPressed: c.loadingMore
              ? null
              : () async {
                  try {
                    await c.moreAnnouncements();
                  } catch (e) {
                    if (mounted) message(context, '$e');
                  }
                },
          child: Text(c.loadingMore ? '載入中…' : '載入較早公告'),
        ),
    ],
    2 => [
      const Section('義工排班', [Text('開啟球隊既有義工系統完成登記。返回 App 後，請在義工系統確認填寫結果。')]),
      FilledButton(
        onPressed: () async {
          try {
            final config = await c.repo.api.request(
              'GET',
              '/api/config',
              authenticated: false,
            );
            if (mounted) {
              await openTrustedUrl(
                context,
                text(config['volunteer_url']),
                volunteer: true,
              );
            }
          } catch (e) {
            if (mounted) message(context, '$e');
          }
        },
        child: const Text('開啟義工排班'),
      ),
    ],
    3 => [
      Section(
        '繳費紀錄',
        c.payments.isEmpty
            ? [const Text('目前沒有繳費項目')]
            : c.payments.map(paymentCard).toList(),
      ),
    ],
    _ => profile(),
  };

  List<Widget> profile() => [
    InfoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            text(c.parent?['display_name']),
            style: Theme.of(context).textTheme.titleLarge,
          ),
          Text('已綁定 ${c.players.length} 位球員'),
          ...c.players.map((p) => Text(p.label)),
          TextButton(
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => BindingPage(controller: c),
                ),
              );
            },
            child: const Text('新增綁定球員'),
          ),
        ],
      ),
    ),
    if (c.isAdmin)
      FilledButton.tonal(
        onPressed: profileBusy
            ? null
            : () => runProfile(() async {
                final result = await c.repo.api.request(
                  'POST',
                  '/api/auth/web-handoff',
                );
                if (mounted) {
                  await openTrustedUrl(
                    context,
                    text(result['url']),
                    requiredHost: Uri.parse(AppConfig.apiUrl).host,
                  );
                }
              }),
        child: const Text('開啟球隊管理後台'),
      ),
    TextButton(
      onPressed: () =>
          openTrustedUrl(context, text(widget.remoteConfig['privacy_url'])),
      child: const Text('隱私政策'),
    ),
    TextButton(
      onPressed: () =>
          openTrustedUrl(context, text(widget.remoteConfig['support_url'])),
      child: const Text('聯絡球隊'),
    ),
    const Text('版本 ${AppConfig.version}', textAlign: TextAlign.center),
    OutlinedButton(
      onPressed: profileBusy
          ? null
          : () => runProfile(() async {
              final messenger = ScaffoldMessenger.of(context);
              try {
                await c.logout();
              } catch (_) {
                messenger.showSnackBar(
                  const SnackBar(content: Text('已清除本機登入；伺服器撤銷未確認，請稍後重新登入。')),
                );
              }
            }),
      child: const Text('登出'),
    ),
    TextButton(
      onPressed: profileBusy ? null : deleteAccount,
      child: const Text('刪除帳號', style: TextStyle(color: Colors.red)),
    ),
  ];

  Future<void> runProfile(Future<void> Function() action) async {
    setState(() => profileBusy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) message(context, '$e');
    } finally {
      if (mounted) setState(() => profileBusy = false);
    }
  }

  Future<void> deleteAccount() async {
    final confirm = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('刪除帳號'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('移除家長個資、綁定與個人訊息。共用球員的出席及繳費保留。確認後會重新驗證登入，請輸入「刪除帳號」。'),
            TextField(controller: confirm),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, confirm.text == '刪除帳號'),
            child: const Text('確認刪除'),
          ),
        ],
      ),
    );
    confirm.dispose();
    if (accepted != true || !mounted) return;
    await runProfile(() async {
      if (!await widget.reauthenticate()) return;
      await c.repo.api.request(
        'POST',
        '/api/me/deletion-request',
        body: {'confirmation': '刪除帳號'},
      );
      await c.repo.api.clear();
      c.reset();
    });
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: c,
    builder: (context, _) {
      final badges = [
        c.hasNew('event', c.events.map((e) => e.id)),
        c.hasNew('announcement', c.announcements.map((a) => a.id)),
        false,
        c.hasNew(
          'payment',
          c.payments.map((p) => p.id),
          '${c.selected?.id ?? ''}',
        ),
        false,
      ];
      if (!c.loading &&
          c.error == null &&
          (page == 0 || page == 1 || page == 3)) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            c.mark(
              page == 0
                  ? 'event'
                  : page == 1
                  ? 'announcement'
                  : 'payment',
            );
          }
        });
      }
      return Scaffold(
        appBar: AppBar(
          title: const Text('青山棒球家長'),
          actions: [
            IconButton(
              onPressed: refreshIdentity,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(
            children: [
              if (c.players.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: DropdownButtonFormField<int>(
                    key: ValueKey(c.selected?.id),
                    initialValue: c.selected?.id,
                    decoration: const InputDecoration(labelText: '目前球員'),
                    items: c.players
                        .map(
                          (p) => DropdownMenuItem(
                            value: p.id,
                            child: Text(p.label),
                          ),
                        )
                        .toList(),
                    onChanged: (id) {
                      if (id != null) {
                        c.select(c.players.firstWhere((p) => p.id == id));
                      }
                    },
                  ),
                ),
              if (c.loading) const LinearProgressIndicator(),
              if (c.error != null)
                MaterialBanner(
                  content: Text(c.error!),
                  actions: [
                    TextButton(onPressed: c.refresh, child: const Text('重試')),
                  ],
                ),
              Expanded(
                child: c.players.isEmpty && page != 4
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text('請先使用球隊提供的綁定碼新增球員'),
                            FilledButton(
                              onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                  builder: (_) => BindingPage(controller: c),
                                ),
                              ),
                              child: const Text('綁定球員'),
                            ),
                          ],
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: refreshIdentity,
                        child: ListView(
                          padding: const EdgeInsets.all(16),
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: body(),
                        ),
                      ),
              ),
            ],
          ),
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: page,
          onDestinationSelected: changePage,
          destinations: List.generate(
            5,
            (i) => NavigationDestination(
              icon: Badge(
                isLabelVisible: badges[i],
                label: const Text('NEW'),
                child: Icon(
                  [
                    Icons.home_outlined,
                    Icons.campaign_outlined,
                    Icons.volunteer_activism_outlined,
                    Icons.payments_outlined,
                    Icons.person_outline,
                  ][i],
                ),
              ),
              label: ['首頁', '公告', '義工', '繳費', '我的'][i],
            ),
          ),
        ),
      );
    },
  );
}
