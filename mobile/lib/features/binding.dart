import 'package:flutter/material.dart';
import '../app/controller.dart';
import '../core/models.dart';
import 'common.dart';

class BindingPage extends StatefulWidget {
  final AppController controller;
  const BindingPage({super.key, required this.controller});
  @override
  State<BindingPage> createState() => _BindingPageState();
}

class _BindingPageState extends State<BindingPage> {
  final code = TextEditingController();
  String pending = '';
  Json? preview;
  bool busy = false;
  @override
  void dispose() {
    code.dispose();
    super.dispose();
  }

  Future<void> query() async {
    final value = code.text.trim().toUpperCase();
    if (!RegExp(r'^[A-Z0-9]{6}$').hasMatch(value)) {
      message(context, '請輸入六碼綁定碼');
      return;
    }
    setState(() {
      busy = true;
      preview = null;
    });
    try {
      final row = Json.from(
        await widget.controller.repo.api.request(
          'POST',
          '/api/bind/preview',
          body: {'code': value},
        ),
      );
      if (mounted) {
        setState(() {
          pending = value;
          preview = row;
        });
      }
    } catch (e) {
      if (mounted) message(context, '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> confirm() async {
    setState(() => busy = true);
    try {
      await widget.controller.repo.api.request(
        'POST',
        '/api/bind/confirm',
        body: {'code': pending},
      );
      await widget.controller.loadIdentity();
      if (mounted) {
        message(context, '球員綁定完成');
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        message(context, '$e');
        setState(() => preview = null);
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('綁定球員')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Text('輸入球隊提供的綁定碼，確認球員資料後再綁定。'),
        const SizedBox(height: 20),
        TextField(
          controller: code,
          maxLength: 6,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(labelText: '球員綁定碼'),
          onChanged: (_) => setState(() => preview = null),
        ),
        FilledButton(
          onPressed: busy ? null : query,
          child: Text(busy ? '處理中…' : '查詢球員'),
        ),
        if (preview != null)
          InfoCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(Player(Json.from(preview!['player'])).label),
                Text(
                  '已綁定 ${preview!['linked_parents']}/${preview!['max_parents']} 位家長',
                ),
                if (preview!['already_bound'] == true)
                  const Text('你已綁定此球員')
                else if (preview!['can_bind'] == true)
                  FilledButton(
                    onPressed: busy ? null : confirm,
                    child: const Text('確認綁定'),
                  )
                else
                  const Text('此球員已達綁定上限，請聯絡球隊'),
              ],
            ),
          ),
      ],
    ),
  );
}
