import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class PlayerSelectionStore {
  Future<int?> read(int parentId);
  Future<void> write(int parentId, int playerId);
}

class SecurePlayerSelectionStore implements PlayerSelectionStore {
  final FlutterSecureStorage storage;
  final String environmentKey;
  SecurePlayerSelectionStore(
    this.environmentKey, [
    this.storage = const FlutterSecureStorage(),
  ]);
  String key(int parentId) => 'selected_player:$environmentKey:$parentId';
  @override
  Future<int?> read(int parentId) async =>
      int.tryParse(await storage.read(key: key(parentId)) ?? '');
  @override
  Future<void> write(int parentId, int playerId) =>
      storage.write(key: key(parentId), value: '$playerId');
}
