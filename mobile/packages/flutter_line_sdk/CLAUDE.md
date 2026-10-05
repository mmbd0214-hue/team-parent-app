# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Basic Flutter Commands
```bash
# Install dependencies
flutter pub get

# Run code analysis with project-specific lints
flutter analyze

# Strict analysis (CI-style, treats infos as errors)
flutter analyze --fatal-infos

# Format code
dart format .

# Run tests
flutter test

# Run specific test file
flutter test test/flutter_line_sdk_test.dart
```

### Example App Development
```bash
# Run example app (navigate to example directory first)
cd example/
flutter pub get
flutter run

# Build example for different platforms
flutter build apk           # Android APK
flutter build appbundle     # Android App Bundle  
flutter build ios           # iOS (macOS only)
```

### Platform-Specific Commands

#### Android
```bash
# In android/ directory
./gradlew build             # Build Android library
./gradlew clean             # Clean build
./gradlew test              # Run Android unit tests
```

#### iOS
```bash
# In example/ios/ directory
pod install                 # Install/update CocoaPods dependencies
open Runner.xcworkspace     # Open in Xcode
```

### Ruby/CocoaPods (iOS Development)
```bash
bundle install              # Install Ruby dependencies
bundle exec pod install     # Use bundled CocoaPods version
```

## Architecture Overview

### Plugin Architecture
This is a Flutter platform plugin that bridges Dart code with native LINE SDKs on Android and iOS. The architecture follows a three-layer pattern:

1. **Dart API Layer** (`/lib/src/line_sdk.dart`): Provides Flutter-friendly APIs
2. **Method Channel Bridge**: Single channel `"com.linecorp/flutter_line_sdk"` for cross-platform communication  
3. **Native Implementation**: Platform-specific wrappers around official LINE SDKs

### Key Components

#### Core API Class
- `LineSDK` (singleton): Main entry point for all LINE SDK operations
- Uses async/await pattern for all operations
- All methods return `Future<T>` for proper async handling

#### Data Models (`/lib/src/model/`)
- Type-safe Dart objects that serialize to/from JSON for native communication
- Key models: `LoginResult`, `AccessToken`, `UserProfile`, `BotFriendshipStatus`
- All models have private constructors and factory methods for JSON conversion

#### Platform Implementation
- **Android** (`/android/`): Kotlin-based wrapper using coroutines
  - `FlutterLineSdkPlugin.kt`: Plugin lifecycle and Activity binding
  - `LineSdkWrapper.kt`: LINE SDK functionality wrapper
  - Model classes handle JSON serialization
- **iOS** (`/ios/`): Swift-based implementation
  - `FlutterLineSdkPlugin.swift`: Plugin registration and method dispatch
  - Uses enum-based method routing for type safety

### Method Channel Communication
- All cross-platform communication uses JSON strings
- Native platforms convert LINE SDK objects to JSON before sending to Dart
- Dart layer parses JSON into strongly-typed model objects
- Error handling: Native exceptions converted to `PlatformException`

### LINE SDK Integration
- **Android**: Integrates `com.linecorp.linesdk:linesdk:5.11.0`
- **iOS**: Integrates `LineSDKSwift ~> 5.13` via CocoaPods
- Both platforms handle Activity/ViewController lifecycle properly
- Secure token storage managed by native SDKs

## Code Standards

### Lint Rules
Project uses `flutter_lints` with additional custom rules:
- `always_specify_types`: Explicit type annotations required
- `prefer_final_fields`: Use final for immutable fields
- `prefer_const_constructors`: Use const constructors where possible
- `avoid_print`: Use proper logging instead of print statements
- `public_member_api_docs`: All public APIs must have documentation
- `unnecessary_this`: Remove unnecessary this references

### Platform Requirements
- **iOS**: Minimum deployment target 13.0
- **Android**: Minimum SDK 24 (Android 7.0)
- **Flutter**: SDK >=2.12.0 <4.0.0 (null safety enabled)

## Important Files and Patterns

### Configuration Files
- `pubspec.yaml`: Plugin metadata and dependencies
- `ios/flutter_line_sdk.podspec`: iOS native dependency specification
- `android/build.gradle`: Android library configuration
- `analysis_options.yaml`: Dart/Flutter linting rules

### Testing
- Main test file: `test/flutter_line_sdk_test.dart`
- Example app serves as integration testing platform
- Use `flutter test` for unit testing

### Data Flow Pattern
1. Flutter app calls `LineSDK.instance.methodName()`
2. Dart method calls `MethodChannel.invokeMethod()` with JSON parameters
3. Native platform receives call, executes LINE SDK functionality
4. Native platform serializes result to JSON and returns
5. Dart layer deserializes JSON to typed model objects
6. Flutter app receives strongly-typed result

This architecture ensures type safety in Dart while leveraging the full power of official native LINE SDKs.