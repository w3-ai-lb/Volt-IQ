import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Talks to the VoltIQ backend (the same FastAPI server the web app uses).
///
/// This replaced `SupabaseService` when the field app joined the unified
/// system. The public methods kept their names and the maps they return kept
/// their keys (`subscriber_id`, `full_name`, `reading_value`, ...), so the
/// screens did not have to be rewritten.
///
/// The server address comes from a build flag:
///
///   flutter run --dart-define=API_URL=http://10.0.2.2:8000
///
/// (10.0.2.2 is "this computer" from inside the Android emulator.)
class ApiService {
  static final ApiService instance = ApiService._internal();
  ApiService._internal();

  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const Duration _pollEvery = Duration(seconds: 20);

  String? _token;
  ApiUser? _user;
  Map<String, dynamic>? _currentEmployee;
  List<Map<String, dynamic>> _cachedReadings = [];

  /// The last invoice the server issued from a reading taken on this phone.
  Map<String, dynamic>? lastInvoice;

  /// True when a server address is configured (always, with the default).
  bool get isInitialized => baseUrl.isNotEmpty;

  ApiUser? get currentUser => _user;

  Map<String, dynamic>? get currentEmployee => _currentEmployee;

  List<Map<String, dynamic>> get cachedReadings => List.unmodifiable(_cachedReadings);

  void setCurrentEmployee(Map<String, dynamic> employee) {
    _currentEmployee = Map<String, dynamic>.from(employee);
  }

  // --- HTTP ------------------------------------------------------------------
  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<dynamic> _get(String path) async {
    final res = await http.get(_uri(path), headers: _headers).timeout(const Duration(seconds: 20));
    return _decode(res);
  }

  Future<dynamic> _send(String method, String path, Map<String, dynamic> body) async {
    final req = http.Request(method, _uri(path))
      ..headers.addAll(_headers)
      ..body = jsonEncode(body);
    final streamed = await req.send().timeout(const Duration(seconds: 20));
    return _decode(await http.Response.fromStream(streamed));
  }

  dynamic _decode(http.Response res) {
    final body = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode >= 200 && res.statusCode < 300) return body;
    final detail = body is Map && body['detail'] is String ? body['detail'] as String : 'HTTP ${res.statusCode}';
    throw ApiException(res.statusCode, detail);
  }

  // --- sign in -----------------------------------------------------------------
  /// Signs in and loads the employee profile. Returns null on success, or a
  /// message to show the user.
  Future<String?> signIn(String email, String password) async {
    try {
      final auth = await _send('POST', '/auth/login', {'email': email, 'password': password});
      _token = auth['token'] as String?;
      final user = auth['user'] as Map<String, dynamic>;
      _user = ApiUser(id: user['id'].toString(), email: user['email'].toString());

      final me = await _get('/crm/me') as Map<String, dynamic>;
      _currentEmployee = {
        'employee_id': me['id'],
        'full_name': me['name'],
        'role': _dbRole(me['accountRole']?.toString()),
        'phone': me['phone'],
        'zone': me['zone'],
        'is_active': true,
      };
      return null;
    } on ApiException catch (e) {
      await signOut();
      if (e.status == 403) return 'Only staff accounts can use the field app.';
      if (e.status == 401) return 'Invalid email or password.';
      return e.message;
    } catch (e) {
      await signOut();
      debugPrint('Sign-in failed: $e');
      return 'Cannot reach the server at $baseUrl.';
    }
  }

  Future<void> signOut() async {
    _token = null;
    _user = null;
    _currentEmployee = null;
    _cachedReadings = [];
    lastInvoice = null;
  }

  static String _dbRole(String? accountRole) {
    switch (accountRole) {
      case 'admin':
        return 'admin';
      case 'staff':
        return 'office_staff';
      default:
        return 'field_employee';
    }
  }

  // --- subscribers -------------------------------------------------------------
  Map<String, dynamic> _subscriberRow(Map<String, dynamic> c) => {
        'subscriber_id': c['id'],
        'full_name': c['name'],
        'address': c['address'] ?? '',
        'phone': c['phone'] ?? '',
        'meter_number': c['meterNo'] ?? '',
        'current_reading': c['currentReading'],
        'zone': c['zone'],
        'balance': c['balance'],
        'is_active': c['status'] == 'Active',
        'created_at': c['lastReadingDate'],
      };

  Future<List<Map<String, dynamic>>> _customers({bool mine = false}) async {
    try {
      final rows = await _get(mine ? '/crm/customers?mine=true' : '/crm/customers') as List<dynamic>;
      return rows.map((r) => _subscriberRow(r as Map<String, dynamic>)).toList();
    } catch (e) {
      debugPrint('Error fetching customers: $e');
      return [];
    }
  }

  Future<List<Map<String, dynamic>>> getAllSubscribers() => _customers();

  Stream<List<Map<String, dynamic>>> getSubscribersStream() => _poll(getAllSubscribers);

  Future<bool> addSubscriber({required String name, required String address, required String phone}) async {
    try {
      await _send('POST', '/crm/customers', {'name': name, 'address': address, 'phone': phone});
      return true;
    } catch (e) {
      debugPrint('Error adding customer: $e');
      return false;
    }
  }

  /// The subscribers assigned to the signed-in employee. The server answers
  /// for whoever is signed in, so [employeeId] only guards against an empty id.
  Future<List<Map<String, dynamic>>> getAssignedSubscribers(String employeeId) async {
    if (employeeId.isEmpty) return [];
    return _customers(mine: true);
  }

  Stream<List<Map<String, dynamic>>> getAssignedSubscribersStream(String employeeId) =>
      _poll(() => getAssignedSubscribers(employeeId));

  // --- employees ---------------------------------------------------------------
  Future<List<Map<String, dynamic>>> getEmployees() async {
    try {
      final rows = await _get('/crm/employees') as List<dynamic>;
      return rows.map((r) {
        final e = r as Map<String, dynamic>;
        return {
          'employee_id': e['id'],
          'full_name': e['name'],
          'phone': e['phone'],
          'role': e['dbRole'],
          'is_active': e['status'] == 'Active',
        };
      }).toList();
    } catch (e) {
      debugPrint('Error fetching employees: $e');
      return [];
    }
  }

  Future<bool> addEmployee({required String name, required String phone, required String role}) async {
    try {
      await _send('POST', '/crm/employees', {'name': name, 'phone': phone, 'role': role});
      return true;
    } catch (e) {
      debugPrint('Error adding employee: $e');
      return false;
    }
  }

  // --- readings (each reading produces an invoice on the server) ------------
  Map<String, dynamic> _readingRow(Map<String, dynamic> inv) {
    final current = _toDouble(inv['currentReading']);
    final previous = _toDouble(inv['previousReading']);
    final kwh = _toDouble(inv['kwhConsumed']);
    final total = _toDouble(inv['totalAmount']);
    final currency = inv['currency']?.toString() ?? 'LBP';
    return {
      'reading_id': inv['id'],
      'invoice_number': inv['invoiceNumber'],
      'subscriber_id': inv['customerId'],
      'customer_name': inv['customerName'] ?? 'Customer',
      'meter_number': inv['meterNo'],
      'reading_value': current,
      'current_reading': current,
      'previous_reading': previous,
      'consumption': kwh,
      'cost': total,
      'currency': currency,
      'amount': formatMoney(total, currency),
      'reading': '${current.toStringAsFixed(0)} kWh',
      'date': inv['issueDate']?.toString() ?? '',
      'captured_by': inv['recordedBy'],
      'captured_by_id': inv['recordedById'],
      'is_paid': inv['status'] == 'Paid',
    };
  }

  Future<List<Map<String, dynamic>>> getReadings({String? capturedBy}) async {
    try {
      final rows = await _get('/crm/invoices') as List<dynamic>;
      var readings = rows.map((r) => _readingRow(r as Map<String, dynamic>)).toList();
      if (capturedBy != null && capturedBy.isNotEmpty) {
        readings = readings.where((r) => r['captured_by_id'] == capturedBy).toList();
      }
      _cachedReadings = readings;
      return readings;
    } catch (e) {
      debugPrint('Error fetching readings: $e');
      return [];
    }
  }

  Stream<List<Map<String, dynamic>>> getReadingsStream() => _poll(getReadings);

  Future<List<Map<String, dynamic>>> getMyReadings() async {
    final empId = _currentEmployee?['employee_id']?.toString() ?? '';
    final role = _currentEmployee?['role']?.toString() ?? '';
    if (empId.isEmpty || role == 'admin') return getReadings();
    return getReadings(capturedBy: empId);
  }

  Future<List<Map<String, dynamic>>> getCustomerReadings(String subscriberId) async {
    try {
      final rows = await _get('/crm/invoices?customerId=${Uri.encodeQueryComponent(subscriberId)}') as List<dynamic>;
      return rows.map((r) => _readingRow(r as Map<String, dynamic>)).toList();
    } catch (e) {
      debugPrint('Error fetching customer readings: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>?> getLatestReadingForCustomer(String subscriberId) async {
    final readings = await getCustomerReadings(subscriberId);
    return readings.isEmpty ? null : readings.first;
  }

  /// Sends a reading. The server checks it, calculates the bill from the
  /// current tariff and keeps the invoice in [lastInvoice]. The [consumption]
  /// and [cost] arguments are accepted for compatibility and ignored: the bill
  /// is always calculated by the server, never on the phone.
  Future<bool> recordMeterReading({
    required String subscriberId,
    required String customerName,
    required String meterNumber,
    required double previousReading,
    required String readingValue,
    double consumption = 0,
    double cost = 0,
  }) async {
    final current = double.tryParse(readingValue.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0.0;
    try {
      final inv = await _send('POST', '/crm/readings', {
        'customerId': subscriberId,
        'currentReading': current,
        if (previousReading > 0) 'previousReading': previousReading,
        'captureMethod': 'ocr',
      }) as Map<String, dynamic>;
      lastInvoice = _readingRow(inv)
        ..addAll({
          'rate_applied': _toDouble(inv['rateApplied']),
          'base_charge': _toDouble(inv['baseCharge']),
          'consumption_charge': _toDouble(inv['consumptionCharge']),
        });
      await getReadings();
      return true;
    } catch (e) {
      debugPrint('Error recording meter reading: $e');
      lastInvoice = null;
      return false;
    }
  }

  Future<bool> createInvoiceFromReading({
    required String subscriberId,
    required String customerName,
    required double currentReading,
    required double previousReading,
    required double unitsConsumed,
    required double totalAmount,
  }) {
    return recordMeterReading(
      subscriberId: subscriberId,
      customerName: customerName,
      meterNumber: '',
      previousReading: previousReading,
      readingValue: currentReading.toString(),
    );
  }

  // --- helpers -------------------------------------------------------------------
  /// Re-runs [load] every few seconds while somebody listens. Replaces the
  /// Supabase realtime channels with plain polling, which every server supports.
  Stream<List<Map<String, dynamic>>> _poll(Future<List<Map<String, dynamic>>> Function() load) {
    late StreamController<List<Map<String, dynamic>>> controller;
    Timer? timer;
    Future<void> emit() async {
      if (!controller.isClosed) controller.add(await load());
    }

    controller = StreamController<List<Map<String, dynamic>>>(
      onListen: () {
        emit();
        timer = Timer.periodic(_pollEvery, (_) => emit());
      },
      onCancel: () => timer?.cancel(),
    );
    return controller.stream;
  }

  static double _toDouble(dynamic value, [double fallback = 0.0]) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString().replaceAll(RegExp(r'[^0-9.-]'), '') ?? '') ?? fallback;
  }

  static String formatMoney(double amount, [String currency = 'LBP']) {
    final digits = currency == 'LBP' ? 0 : 2;
    final fixed = amount.toStringAsFixed(digits);
    final parts = fixed.split('.');
    final whole = parts[0].replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
    return parts.length > 1 ? '$currency $whole.${parts[1]}' : '$currency $whole';
  }
}

class ApiUser {
  final String id;
  final String email;
  const ApiUser({required this.id, required this.email});
}

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);

  @override
  String toString() => 'ApiException($status): $message';
}
