import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../app/controller.dart';
import '../core/api_client.dart';
import '../core/models.dart';
import 'common.dart';

class PaymentForm extends StatefulWidget {
  final AppController controller;
  final Payment payment;
  const PaymentForm({
    super.key,
    required this.controller,
    required this.payment,
  });
  @override
  State<PaymentForm> createState() => _PaymentFormState();
}

class _PaymentFormState extends State<PaymentForm> {
  final form = GlobalKey<FormState>();
  late String method = widget.payment.method;
  late String date = widget.payment.transferDate;
  late final last5 = TextEditingController(text: widget.payment.last5);
  bool busy = false;
  @override
  void dispose() {
    last5.dispose();
    super.dispose();
  }

  Future<void> pickDate() async {
    final today = DateTime.now().toUtc().add(const Duration(hours: 8));
    final chosen = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(date) ?? today,
      firstDate: DateTime(2000),
      lastDate: DateTime(today.year + 1, 12, 31),
    );
    if (chosen != null && mounted) {
      setState(
        () => date =
            '${chosen.year}-${chosen.month.toString().padLeft(2, '0')}-${chosen.day.toString().padLeft(2, '0')}',
      );
    }
  }

  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    if (date.isEmpty) {
      message(context, '請選擇繳交日期');
      return;
    }
    setState(() => busy = true);
    try {
      await widget.controller.repo.api.request(
        'PUT',
        '/api/payments/${widget.payment.id}/transfer',
        body: {
          'payment_method': method,
          'transfer_date': date,
          'account_last5': method == 'transfer' ? last5.text : '',
          'expected_version': widget.payment.version,
        },
      );
      if (mounted) {
        message(context, '資料已送出，等待管理員確認');
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        message(context, '$e');
        if (e is ApiException && e.status == 409) {
          Navigator.pop(context); // Reload latest paid/version state in shell.
        }
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('回報繳費')),
    body: Form(
      key: form,
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            '${widget.payment.title} · NT\$ ${widget.payment.amount}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 20),
          DropdownButtonFormField<String>(
            initialValue: method.isEmpty ? null : method,
            decoration: const InputDecoration(labelText: '繳費方式'),
            items: const [
              DropdownMenuItem(value: 'cash', child: Text('現場現金繳交')),
              DropdownMenuItem(value: 'transfer', child: Text('轉帳匯款')),
            ],
            validator: (v) => v == null ? '請選擇繳費方式' : null,
            onChanged: busy
                ? null
                : (m) => setState(() {
                    method = m!;
                    if (method == 'cash') last5.clear();
                  }),
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: busy ? null : pickDate,
            icon: const Icon(Icons.calendar_month),
            label: Text(date.isEmpty ? '選擇繳交日期' : date),
          ),
          if (method == 'transfer') ...[
            const SizedBox(height: 20),
            TextFormField(
              controller: last5,
              enabled: !busy,
              maxLength: 5,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(labelText: '帳號後五碼'),
              validator: (v) =>
                  RegExp(r'^[0-9]{5}$').hasMatch(v ?? '') ? null : '請輸入五位數字',
            ),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: busy ? null : submit,
            child: Text(busy ? '提交中…' : '送出繳費資料'),
          ),
          const SizedBox(height: 16),
          const Text('這是繳費資料回報，需由管理員確認後才會標為已繳。'),
        ],
      ),
    ),
  );
}
