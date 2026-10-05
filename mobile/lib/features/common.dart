import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

void message(BuildContext context, String value) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(value)));
}

Future<void> openTrustedUrl(
  BuildContext context,
  String value, {
  String? requiredHost,
  bool volunteer = false,
}) async {
  final uri = Uri.tryParse(value);
  final allowed =
      uri != null &&
      uri.scheme == 'https' &&
      uri.userInfo.isEmpty &&
      (requiredHost == null || uri.host == requiredHost) &&
      (!volunteer ||
          {
            'script.google.com',
            'script.googleusercontent.com',
          }.contains(uri.host));
  if (!allowed) {
    if (context.mounted) message(context, '連結尚未設定或不受支援');
    return;
  }
  try {
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
        context.mounted) {
      message(context, '無法開啟連結');
    }
  } catch (_) {
    if (context.mounted) message(context, '無法開啟連結');
  }
}

class Section extends StatelessWidget {
  final String title;
  final List<Widget> children;
  const Section(this.title, this.children, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 12),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        ...children,
      ],
    ),
  );
}

class InfoCard extends StatelessWidget {
  final Widget child;
  const InfoCard({required this.child, super.key});
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(padding: const EdgeInsets.all(18), child: child),
  );
}
