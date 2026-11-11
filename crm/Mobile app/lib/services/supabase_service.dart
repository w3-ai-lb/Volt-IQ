import 'dart:async';
import 'dart:convert';

import 'package:supabase_flutter/supabase_flutter.dart';

class SupabaseService {
  static final SupabaseService instance = SupabaseService._internal();
  SupabaseService._internal();

  bool _isInitialized = false;
  Map<String, dynamic>? _currentEmployee;
  List<Map<String, dynamic>> _cachedReadings = [];

  void markInitialized() {
    _isInitialized = true;
  }

  SupabaseClient get client => Supabase.instance.client;

  bool get isInitialized => _isInitialized;

  User? get currentUser {
    if (!isInitialized) return null;
    return client.auth.currentUser;
  }

  Map<String, dynamic>? get currentEmployee => _currentEmployee;

  List<Map<String, dynamic>> get cachedReadings =>
      List.unmodifiable(_cachedReadings);

  void setCurrentEmployee(Map<String, dynamic> employee) {
    _currentEmployee = Map<String, dynamic>.from(employee);
  }

  Future<AuthResponse?> signIn(String email, String password) async {
    if (!isInitialized) return null;
    return client.auth.signInWithPassword(email: email, password: password);
  }

  Future<void> signOut() async {
    if (!isInitialized) return;
    _currentEmployee = null;
    await client.auth.signOut();
  }

  Future<List<Map<String, dynamic>>> getAllSubscribers() async {
    if (!isInitialized) return [];

    try {
      final response = await client
          .from('subscribers')
          .select()
          .order('created_at', ascending: false);
      return List<Map<String, dynamic>>.from(response);
    } catch (e) {
      print('Error fetching subscribers: $e');
      return [];
    }
  }

  Stream<List<Map<String, dynamic>>> getSubscribersStream() {
    if (!isInitialized) return Stream.value([]);

    return client
        .from('subscribers')
        .stream(primaryKey: ['subscriber_id'])
        .order('created_at', ascending: false)
        .map((rows) => List<Map<String, dynamic>>.from(rows));
  }

  Future<bool> addSubscriber({
    required String name,
    required String address,
    required String phone,
  }) async {
    if (!isInitialized) return false;

    try {
      await client.from('subscribers').insert({
        'full_name': name,
        'address': address,
        'phone': phone,
        'is_active': true,
      });
      return true;
    } catch (e) {
      print('Error adding subscriber: $e');
      return false;
    }
  }

  Future<List<Map<String, dynamic>>> getEmployees() async {
    if (!isInitialized) return [];

    try {
      final response = await client
          .from('employees')
          .select()
          .order('created_at', ascending: false);
      return List<Map<String, dynamic>>.from(response);
    } catch (e) {
      print('Error fetching employees: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>?> getEmployeeByAuthUserId(
    String authUserId,
  ) async {
    if (!isInitialized) return null;

    try {
      final response = await client
          .from('employees')
          .select()
          .eq('auth_user_id', authUserId)
          .maybeSingle();
      return response == null ? null : Map<String, dynamic>.from(response);
    } catch (e) {
      print('Error fetching employee by auth user id: $e');
      return null;
    }
  }

  Future<bool> addEmployee({
    required String name,
    required String phone,
    required String role,
  }) async {
    if (!isInitialized) return false;

    try {
      await client.from('employees').insert({
        'full_name': name,
        'phone': phone,
        'role': role,
        'is_active': true,
      });
      return true;
    } catch (e) {
      print('Error adding employee: $e');
      return false;
    }
  }

  Future<List<Map<String, dynamic>>> getAssignedSubscribers(
    String employeeId,
  ) async {
    if (!isInitialized || employeeId.isEmpty) return [];

    try {
      final assignments = await client
          .from('employee_subscriber_assignments')
          .select('subscriber_id')
          .eq('employee_id', employeeId)
          .eq('is_active', true);

      final subscriberIds = List<Map<String, dynamic>>.from(assignments)
          .map((row) => row['subscriber_id']?.toString())
          .whereType<String>()
          .toList();

      if (subscriberIds.isEmpty) return [];

      final subscribers = await client
          .from('subscribers')
          .select()
          .inFilter('subscriber_id', subscriberIds)
          .order('created_at', ascending: false);

      return List<Map<String, dynamic>>.from(subscribers);
    } catch (e) {
      print('Error fetching assigned subscribers: $e');
      return [];
    }
  }

  Stream<List<Map<String, dynamic>>> getAssignedSubscribersStream(
    String employeeId,
  ) {
    if (!isInitialized || employeeId.isEmpty) return Stream.value([]);

    final controller = StreamController<List<Map<String, dynamic>>>();
    StreamSubscription<List<Map<String, dynamic>>>? subscriberSub;
    StreamSubscription<List<Map<String, dynamic>>>? assignmentSub;

    Future<void> emitAssigned() async {
      if (controller.isClosed) return;
      controller.add(await getAssignedSubscribers(employeeId));
    }

    controller.onListen = () {
      emitAssigned();
      subscriberSub = getSubscribersStream().listen((_) => emitAssigned());
      assignmentSub = client
          .from('employee_subscriber_assignments')
          .stream(primaryKey: ['assignment_id'])
          .listen((_) => emitAssigned());
    };

    controller.onCancel = () async {
      await subscriberSub?.cancel();
      await assignmentSub?.cancel();
    };

    return controller.stream;
  }

  Stream<List<Map<String, dynamic>>> getReadingsStream() {
    if (!isInitialized) return Stream.value([]);

    return client
        .from('meter_readings')
        .stream(primaryKey: ['reading_id'])
        .order('reading_date', ascending: false)
        .map((rows) {
          final mapped = rows.map(_mapReadingRow).toList();
          _cachedReadings = mapped;
          return mapped;
        });
  }

  Future<List<Map<String, dynamic>>> getMyReadings() async {
    final empId = _currentEmployee?['employee_id']?.toString() ?? '';
    if (empId.isEmpty || empId == 'ADMIN-001') {
      return getReadings();
    }
    return getReadings(capturedBy: empId);
  }

  Future<List<Map<String, dynamic>>> getCustomerReadings(
    String subscriberId,
  ) async {
    final readings = await getReadings();
    return readings
        .where((row) => row['subscriber_id']?.toString() == subscriberId)
        .toList();
  }

  Future<Map<String, dynamic>?> getLatestReadingForCustomer(
    String subscriberId,
  ) async {
    final readings = await getCustomerReadings(subscriberId);
    if (readings.isEmpty) return null;
    return readings.first;
  }

  Future<List<Map<String, dynamic>>> getReadings({String? capturedBy}) async {
    if (!isInitialized) return [];

    try {
      dynamic query = client
          .from('meter_readings')
          .select()
          .order('reading_date', ascending: false);

      if (capturedBy != null && capturedBy.isNotEmpty) {
        query = client
            .from('meter_readings')
            .select()
            .eq('captured_by', capturedBy)
            .order('reading_date', ascending: false);
      }

      final response = await query;
      final readings = List<Map<String, dynamic>>.from(
        response,
      ).map(_mapReadingRow).toList();
      _cachedReadings = readings;
      return readings;
    } catch (e) {
      print('Error fetching meter readings: $e');
      return [];
    }
  }

  Future<bool> recordMeterReading({
    required String subscriberId,
    required String customerName,
    required String meterNumber,
    required double previousReading,
    required String readingValue,
    required double consumption,
    required double cost,
  }) async {
    if (!isInitialized) return false;

    final currentReading =
        double.tryParse(readingValue.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0.0;
    final now = DateTime.now();
    final employeeId = _currentEmployee?['employee_id']?.toString();
    final employeeName =
        _currentEmployee?['full_name']?.toString() ??
        currentUser?.email ??
        'Field Employee';
    final metadata = {
      'subscriber_id': subscriberId,
      'customer_name': customerName,
      'meter_number': meterNumber,
      'current_reading': currentReading,
      'reading_value': currentReading,
      'previous_reading': previousReading,
      'kwh': consumption,
      'consumption': consumption,
      'total_amount': cost,
      'cost': cost,
      'date': now.toIso8601String(),
      'captured_by_name': employeeName,
      'is_paid': false,
      'invoice_number':
          'PWR-2026-${now.millisecondsSinceEpoch.toString().substring(7)}',
    };

    try {
      final payload = <String, dynamic>{
        'reading_value': currentReading,
        'reading_date': now.toIso8601String(),
        'ocr_raw_value': currentReading,
        'was_corrected': false,
        'photo_url': jsonEncode(metadata),
        'is_validated': true,
      };

      if (employeeId != null &&
          employeeId.isNotEmpty &&
          employeeId != 'ADMIN-001') {
        payload['captured_by'] = employeeId;
      }

      await client.from('meter_readings').insert(payload);
      await getReadings();
      return true;
    } catch (e) {
      print('Error recording meter reading: $e');
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
  }) async {
    return recordMeterReading(
      subscriberId: subscriberId,
      customerName: customerName,
      meterNumber:
          'MTR-${subscriberId.length > 6 ? subscriberId.substring(0, 6) : subscriberId}',
      previousReading: previousReading,
      readingValue: currentReading.toString(),
      consumption: unitsConsumed,
      cost: totalAmount,
    );
  }

  Map<String, dynamic> _mapReadingRow(Map<String, dynamic> row) {
    final meta = _parseReadingMetadata(row['photo_url']);
    final currentReading = _toDouble(
      row['reading_value'] ?? meta['current_reading'] ?? meta['reading_value'],
    );
    final previousReading = _toDouble(meta['previous_reading']);
    final consumption = _toDouble(
      meta['kwh'] ?? meta['consumption'],
      currentReading - previousReading,
    );
    final totalAmount = _toDouble(
      meta['total_amount'] ?? meta['cost'],
      (consumption * 0.15) + 5.0,
    );
    final date =
        row['reading_date']?.toString() ??
        meta['date']?.toString() ??
        DateTime.now().toIso8601String();

    return {
      ...row,
      ...meta,
      'reading_id': row['reading_id'] ?? meta['reading_id'],
      'subscriber_id': meta['subscriber_id'] ?? row['subscriber_id'],
      'customer_name': meta['customer_name'] ?? 'Customer',
      'meter_number': meta['meter_number'],
      'reading_value': currentReading,
      'current_reading': currentReading,
      'previous_reading': previousReading,
      'consumption': consumption,
      'cost': totalAmount,
      'amount': '\$${totalAmount.toStringAsFixed(2)}',
      'reading': '${currentReading.toStringAsFixed(0)} kWh',
      'date': date.contains('T') ? date.split('T').first : date,
      'captured_by': row['captured_by'] ?? meta['captured_by_name'],
      'is_paid': meta['is_paid'] == true || meta['isPaid'] == true,
    };
  }

  Map<String, dynamic> _parseReadingMetadata(dynamic rawValue) {
    if (rawValue is! String) return {};
    final raw = rawValue.trim();
    if (!raw.startsWith('{') || !raw.endsWith('}')) return {};

    try {
      final decoded = jsonDecode(raw);
      return decoded is Map ? Map<String, dynamic>.from(decoded) : {};
    } catch (_) {
      return {};
    }
  }

  double _toDouble(dynamic value, [double fallback = 0.0]) {
    if (value is num) return value.toDouble();
    final parsed = double.tryParse(
      value?.toString().replaceAll(RegExp(r'[^0-9.-]'), '') ?? '',
    );
    return parsed ?? fallback;
  }
}
