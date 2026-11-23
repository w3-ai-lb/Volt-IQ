# VoltIQ Field (mobile app)

A Flutter app for **field employees**. They sign in, see the customers
assigned to them, read the meter with the camera (text recognition), and
send the reading. The **server** checks the reading and issues the invoice.
The app shows the invoice the server returns.

It talks only to the VoltIQ API, through
[`lib/services/api_service.dart`](lib/services/api_service.dart). Until the
VoltIQ unification it used Supabase directly.

## Run it

You need the Flutter SDK (3.x) and an Android emulator or a phone.

```bash
cd mobile
flutter pub get
# Android emulator -> API running on your computer:
flutter run --dart-define=API_URL=http://10.0.2.2:8000
# Real phone on the same Wi-Fi -> use your computer's IP:
flutter run --dart-define=API_URL=http://192.168.1.20:8000
# Online API:
flutter run --dart-define=API_URL=https://voltiq-api.onrender.com
```

Sign in with a **staff** account, for example the demo field employee
`field@voltiq.demo` / `field1234` (exists only after loading the demo data).
Customer accounts are refused.

## Notes

- Debug builds may use plain `http://` (see `android/app/src/debug/AndroidManifest.xml`).
  Release builds must use `https://`.
- The lists refresh every 20 seconds (polling), replacing the old Supabase realtime channels.
- **Not yet verified:** the switch from Supabase to the API was made on a
  machine without Flutter. Run `flutter pub get`, `flutter analyze` and
  `flutter run` once and fix anything they report.
