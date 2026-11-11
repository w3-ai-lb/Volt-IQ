import 'dart:async';
import 'package:flutter/material.dart';
import '../services/supabase_service.dart';
import 'login_page.dart';

class EmployeePage extends StatefulWidget {
  const EmployeePage({super.key});

  @override
  State<EmployeePage> createState() => _EmployeePageState();
}

class _EmployeePageState extends State<EmployeePage> {
  Map<String, dynamic>? _currentEmp;
  List<Map<String, dynamic>> _myReadings = [];
  int _assignedCount = 0;
  bool _isLoading = true;
  StreamSubscription<List<Map<String, dynamic>>>? _readingsSubscription;

  @override
  void initState() {
    super.initState();
    _loadProfileData();
    _subscribeToReadings();
  }

  void _subscribeToReadings() {
    _readingsSubscription = SupabaseService.instance.getReadingsStream().listen((_) {
      if (mounted) {
        _refreshMyReadings();
      }
    });
  }

  Future<void> _refreshMyReadings() async {
    final readings = await SupabaseService.instance.getMyReadings();
    if (mounted) {
      setState(() {
        _myReadings = readings;
      });
    }
  }

  Future<void> _loadProfileData() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    final emp = SupabaseService.instance.currentEmployee;
    final empId = emp?['employee_id']?.toString() ?? '';

    int assignedCount = 0;
    if (empId.isNotEmpty) {
      final assigned = await SupabaseService.instance.getAssignedSubscribers(empId);
      assignedCount = assigned.length;
    }

    final readings = await SupabaseService.instance.getMyReadings();

    if (mounted) {
      setState(() {
        _currentEmp = emp;
        _assignedCount = assignedCount;
        _myReadings = readings;
        _isLoading = false;
      });
    }
  }

  @override
  void dispose() {
    _readingsSubscription?.cancel();
    super.dispose();
  }

  Future<void> _handleLogout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Confirm Logout', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        content: const Text(
          'Are you sure you want to log out of your field employee session?',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.redAccent,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Log Out'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      await SupabaseService.instance.signOut();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (context) => const LoginPage()),
          (route) => false,
        );
      }
    }
  }

  void _showReadingDetailsDialog(BuildContext context, Map<String, dynamic> record) {
    final readingDisplay = record['reading']?.toString() ?? '${record['reading_value'] ?? '0'} kWh';
    final isPaid = (record['is_paid'] == true || record['isPaid'] == true);
    final dateDisplay = record['date']?.toString() ?? 'Recent';
    final amountDisplay = record['amount']?.toString() ?? '\$0.00';
    final customerName = record['customer_name']?.toString() ?? 'Customer';
    final meterNo = record['meter_number']?.toString() ?? 'N/A';
    final invoiceNo = record['invoice_number']?.toString() ?? 'PWR-2026-0000';
    final consumption = record['consumption']?.toString() ?? '0';

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF4F46E5).withOpacity(0.2),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.receipt_long_rounded, color: Color(0xFF818CF8), size: 22),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Text(
                'Reading Details',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildDetailRow('Customer', customerName),
            _buildDetailRow('Meter ID', meterNo),
            _buildDetailRow('Invoice #', invoiceNo),
            _buildDetailRow('Reading Value', readingDisplay),
            _buildDetailRow('Consumption', '$consumption kWh'),
            _buildDetailRow('Billed Amount', amountDisplay),
            _buildDetailRow('Date Recorded', dateDisplay),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Payment Status:', style: TextStyle(color: Colors.white60, fontSize: 13)),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: isPaid ? Colors.green.withOpacity(0.15) : Colors.amber.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: isPaid ? Colors.green.withOpacity(0.3) : Colors.amber.withOpacity(0.3)),
                  ),
                  child: Text(
                    isPaid ? 'PAID' : 'UNPAID',
                    style: TextStyle(
                      color: isPaid ? Colors.green : Colors.amber,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close', style: TextStyle(color: Color(0xFF818CF8), fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white54, fontSize: 13)),
          Flexible(
            child: Text(
              value,
              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final emp = _currentEmp ?? SupabaseService.instance.currentEmployee;
    final currentUser = SupabaseService.instance.currentUser;
    final empName = emp?['full_name']?.toString() ?? 'Field Operator';
    final empRole = (emp?['role']?.toString().toUpperCase() ?? 'FIELD OPERATOR').replaceAll('_', ' ');
    final empPhone = emp?['phone']?.toString() ?? '+1 (555) 019-2831';
    final empEmail = currentUser?.email ?? '${empName.toLowerCase().replaceAll(' ', '.')}@gridpower.com';
    final empId = emp?['employee_id']?.toString() ?? 'EMP-2026';

    double totalKwh = 0;
    for (final r in _myReadings) {
      final c = r['consumption'];
      if (c is num) totalKwh += c.toDouble();
    }

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadProfileData,
          color: const Color(0xFF4F46E5),
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 100),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top Header Row
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'My Employee Profile',
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Account Details & Operational Stats',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.refresh_rounded, color: Colors.cyan),
                      onPressed: _loadProfileData,
                      tooltip: 'Refresh Profile',
                    ),
                  ],
                ),
                const SizedBox(height: 20),

                // Employee Profile Card
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF1E1B4B), Color(0xFF312E81)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: const Color(0xFF818CF8).withOpacity(0.3),
                      width: 1.5,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF4F46E5).withOpacity(0.2),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 32,
                            backgroundColor: const Color(0xFF818CF8).withOpacity(0.2),
                            child: Text(
                              empName.isNotEmpty ? empName[0].toUpperCase() : 'E',
                              style: const TextStyle(
                                fontSize: 26,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  empName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.bold,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 4),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF818CF8).withOpacity(0.2),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: const Color(0xFF818CF8).withOpacity(0.4)),
                                  ),
                                  child: Text(
                                    empRole,
                                    style: const TextStyle(
                                      color: Color(0xFF818CF8),
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 0.5,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: Colors.green.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: Colors.green.withOpacity(0.3)),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                CircleAvatar(radius: 3, backgroundColor: Colors.green),
                                SizedBox(width: 4),
                                Text(
                                  'Active',
                                  style: TextStyle(color: Colors.green, fontSize: 11, fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      const Divider(color: Colors.white12, height: 1),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Icon(Icons.email_outlined, color: Colors.white.withOpacity(0.5), size: 16),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              empEmail,
                              style: TextStyle(color: Colors.white.withOpacity(0.8), fontSize: 12),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      if (empPhone.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Icon(Icons.phone_outlined, color: Colors.white.withOpacity(0.5), size: 16),
                            const SizedBox(width: 8),
                            Text(
                              empPhone,
                              style: TextStyle(color: Colors.white.withOpacity(0.8), fontSize: 12),
                            ),
                            const Spacer(),
                            Text(
                              'ID: ${empId.length > 8 ? empId.substring(0, 8) : empId}',
                              style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 11, fontFamily: 'monospace'),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                // KPI Stat Cards (Readings Logged, Assigned Accounts, Total kWh)
                Row(
                  children: [
                    // Total Readings Logged
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.7),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: Colors.white.withOpacity(0.08)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.assignment_turned_in_rounded, color: Color(0xFF818CF8), size: 20),
                            const SizedBox(height: 10),
                            Text(
                              '${_myReadings.length}',
                              style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Readings Logged',
                              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 11),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),

                    // Assigned Accounts
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.7),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: Colors.white.withOpacity(0.08)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.people_alt_rounded, color: Colors.amber, size: 20),
                            const SizedBox(height: 10),
                            Text(
                              '$_assignedCount',
                              style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Assigned Accounts',
                              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 11),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),

                    // Total kWh Logged
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.7),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(color: Colors.white.withOpacity(0.08)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.bolt_rounded, color: Colors.cyanAccent, size: 20),
                            const SizedBox(height: 10),
                            Text(
                              '${totalKwh.toStringAsFixed(0)}',
                              style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Total kWh',
                              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 11),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 28),

                // My Reading History Title
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'My Reading History',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: const Color(0xFF4F46E5).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${_myReadings.length} entries',
                        style: const TextStyle(color: Color(0xFF818CF8), fontSize: 12, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                // Readings List
                if (_isLoading && _myReadings.isEmpty)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: CircularProgressIndicator(color: Color(0xFF4F46E5)),
                    ),
                  )
                else if (_myReadings.isEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(28),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E293B).withOpacity(0.5),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: Colors.white.withOpacity(0.08)),
                    ),
                    child: Column(
                      children: [
                        Icon(Icons.history_rounded, size: 48, color: Colors.white.withOpacity(0.2)),
                        const SizedBox(height: 12),
                        Text(
                          'No Readings Recorded Yet',
                          style: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 15, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Readings you scan on the schedule will appear here',
                          style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  )
                else
                  ListView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _myReadings.length,
                    itemBuilder: (context, index) {
                      final record = _myReadings[index];
                      final isPaid = (record['is_paid'] == true || record['isPaid'] == true);
                      final readingDisplay = record['reading']?.toString() ??
                          '${record['reading_value'] ?? '0'} kWh';
                      final customerName = record['customer_name']?.toString() ?? 'Customer';
                      final meterNo = record['meter_number']?.toString() ?? '';
                      final dateDisplay = record['date']?.toString() ?? 'Recent';
                      final amountDisplay = record['amount']?.toString() ??
                          (record['cost'] != null ? '\$${(record['cost'] as num).toStringAsFixed(2)}' : '\$5.00');

                      return Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.65),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(
                            color: Colors.white.withOpacity(0.08),
                            width: 1,
                          ),
                        ),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                          onTap: () => _showReadingDetailsDialog(context, record),
                          leading: Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: isPaid ? Colors.green.withOpacity(0.12) : Colors.amber.withOpacity(0.12),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              isPaid ? Icons.check_circle_outline_rounded : Icons.pending_actions_rounded,
                              color: isPaid ? Colors.green : Colors.amber,
                              size: 22,
                            ),
                          ),
                          title: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  customerName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 15,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              Text(
                                readingDisplay,
                                style: const TextStyle(
                                  color: Colors.cyanAccent,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                ),
                              ),
                            ],
                          ),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Row(
                              children: [
                                if (meterNo.isNotEmpty) ...[
                                  Text(
                                    meterNo,
                                    style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
                                  ),
                                  const SizedBox(width: 8),
                                  Text('•', style: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 12)),
                                  const SizedBox(width: 8),
                                ],
                                Text(
                                  dateDisplay,
                                  style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
                                ),
                                const Spacer(),
                                Text(
                                  amountDisplay,
                                  style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                                const SizedBox(width: 6),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: isPaid ? Colors.green.withOpacity(0.15) : Colors.amber.withOpacity(0.15),
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: Text(
                                    isPaid ? 'Paid' : 'Unpaid',
                                    style: TextStyle(
                                      color: isPaid ? Colors.green : Colors.amber,
                                      fontSize: 9,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),

                const SizedBox(height: 32),

                // Logout Button
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.redAccent.withOpacity(0.1),
                      foregroundColor: Colors.redAccent,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                        side: BorderSide(color: Colors.redAccent.withOpacity(0.3)),
                      ),
                    ),
                    onPressed: _handleLogout,
                    icon: const Icon(Icons.logout_rounded),
                    label: const Text(
                      'Log Out',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
