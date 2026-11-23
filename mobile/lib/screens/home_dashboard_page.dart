import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'customer_page.dart';
import 'customer_history_page.dart';

class HomeDashboardPage extends StatefulWidget {
  const HomeDashboardPage({super.key});

  @override
  State<HomeDashboardPage> createState() => _HomeDashboardPageState();
}

class _HomeDashboardPageState extends State<HomeDashboardPage> {
  List<Customer> _todayCustomers = [];
  bool _isLoading = true;
  StreamSubscription<List<Map<String, dynamic>>>? _scheduleSubscription;

  @override
  void initState() {
    super.initState();
    _subscribeToLiveSchedule();
    _loadSchedule();
  }

  void _subscribeToLiveSchedule() {
    final currentEmp = ApiService.instance.currentEmployee;
    final empId = currentEmp?['employee_id']?.toString() ?? '';
    final isSuperAdmin = empId == 'ADMIN-001' || currentEmp?['role'] == 'admin';

    if (isSuperAdmin || empId.isEmpty) {
      _scheduleSubscription = ApiService.instance.getSubscribersStream().listen((data) {
        if (mounted) {
          _updateScheduleFromData(data);
        }
      });
    } else {
      _scheduleSubscription = ApiService.instance.getAssignedSubscribersStream(empId).listen((data) {
        if (mounted) {
          _updateScheduleFromData(data);
        }
      });
    }
  }

  void _updateScheduleFromData(List<Map<String, dynamic>> data) {
    setState(() {
      _todayCustomers = data.map((item) {
        final id = item['subscriber_id']?.toString() ?? '';
        final hasReading = ApiService.instance.cachedReadings.any((r) => r['subscriber_id'] == id);
        return Customer(
          id: id,
          name: item['full_name']?.toString() ?? 'Unnamed Customer',
          address: item['address']?.toString() ?? 'No address provided',
          phone: item['phone']?.toString() ?? '',
          meterNumber: 'MTR-${id.length > 6 ? id.substring(0, 6) : id}',
          status: hasReading ? 'Completed' : 'Pending',
        );
      }).toList();
      _isLoading = false;
    });
  }

  Future<void> _loadSchedule() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    final currentEmp = ApiService.instance.currentEmployee;
    final empId = currentEmp?['employee_id']?.toString() ?? '';
    final isSuperAdmin = empId == 'ADMIN-001' || currentEmp?['role'] == 'admin';

    List<Map<String, dynamic>> data;
    if (isSuperAdmin || empId.isEmpty) {
      data = await ApiService.instance.getAllSubscribers();
    } else {
      data = await ApiService.instance.getAssignedSubscribers(empId);
    }

    if (mounted) {
      _updateScheduleFromData(data);
    }
  }

  @override
  void dispose() {
    _scheduleSubscription?.cancel();
    super.dispose();
  }

  // Helper to get sorted list: Pending first, Completed last
  List<Customer> _getSortedList() {
    final sorted = List<Customer>.from(_todayCustomers);
    sorted.sort((a, b) {
      if (a.status == b.status) return 0;
      if (a.status == 'Pending') return -1; // Pending floats to top
      return 1; // Completed drops to bottom
    });
    return sorted;
  }

  @override
  Widget build(BuildContext context) {
    final currentEmp = ApiService.instance.currentEmployee;
    final empName = currentEmp?['full_name']?.toString() ?? 'Alex Carter';
    final empRole = (currentEmp?['role']?.toString().toUpperCase() ?? 'FIELD OPERATOR');
    final isSuperAdmin = currentEmp?['employee_id'] == 'ADMIN-001' || currentEmp?['role'] == 'admin';

    final sortedCustomers = _getSortedList();
    final completedCount = _todayCustomers.where((c) => c.status == 'Completed').length;
    final pendingCount = _todayCustomers.where((c) => c.status == 'Pending').length;

    return Scaffold(
      backgroundColor: Colors.black,
      body: RefreshIndicator(
        onRefresh: _loadSchedule,
        color: const Color(0xFF4F46E5),
        backgroundColor: const Color(0xFF1E293B),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top Header with Logged-in Employee Info & Power Theme Gradient Background
              Container(
                width: double.infinity,
                padding: const EdgeInsets.only(left: 24, right: 24, top: 60, bottom: 30),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [
                      Color(0xFF1E1B4B), // Deep Indigo
                      Color(0xFF311B92), // Electric Purple
                      Color(0xFF0F172A), // Dark Slate
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: const BorderRadius.only(
                    bottomLeft: Radius.circular(36),
                    bottomRight: Radius.circular(36),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF4F46E5).withOpacity(0.25),
                      blurRadius: 25,
                      offset: const Offset(0, 10),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Expanded(
                          child: Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: Colors.amber.withOpacity(0.2),
                                  shape: BoxShape.circle,
                                  border: Border.all(color: Colors.amber.withOpacity(0.4), width: 1.5),
                                ),
                                child: const Icon(
                                  Icons.bolt_rounded,
                                  color: Colors.amber,
                                  size: 28,
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      empName,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 18,
                                        fontWeight: FontWeight.w900,
                                        letterSpacing: 0.8,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                      maxLines: 1,
                                    ),
                                    Text(
                                      '$empRole • Assigned Field Schedule',
                                      style: TextStyle(
                                        color: Colors.white.withOpacity(0.6),
                                        fontSize: 12,
                                        fontWeight: FontWeight.w500,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                      maxLines: 1,
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.refresh_rounded, color: Colors.cyan),
                          onPressed: _loadSchedule,
                          tooltip: 'Sync with Cloud Database',
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),

                    // Schedule Overview Banner
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.06),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: Colors.white.withOpacity(0.1)),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.assignment_ind_rounded, color: Colors.white.withOpacity(0.8), size: 20),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  isSuperAdmin ? "Company-Wide Meter Schedule" : "My Assigned Customers Today",
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 15,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  ApiService.instance.isInitialized
                                      ? 'Live Cloud Sync • ${_todayCustomers.length} Assigned Accounts'
                                      : 'Offline Mode • ${_todayCustomers.length} Assigned Accounts',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.5),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Metrics Row (Pending vs Completed Today)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Row(
                  children: [
                    // Pending count card
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.7),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: Colors.amber.withOpacity(0.15),
                            width: 1,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Expanded(
                                  child: Text(
                                    'Pending',
                                    style: TextStyle(
                                      color: Colors.white60,
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                    maxLines: 1,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Icon(Icons.hourglass_empty_rounded, color: Colors.amber.withOpacity(0.8), size: 18),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Text(
                              '$pendingCount',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 28,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),

                    // Completed count card
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withOpacity(0.7),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: Colors.green.withOpacity(0.15),
                            width: 1,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Expanded(
                                  child: Text(
                                    'Completed Today',
                                    style: TextStyle(
                                      color: Colors.white60,
                                      fontSize: 13,
                                      fontWeight: FontWeight.bold,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                    maxLines: 1,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Icon(Icons.check_circle_outline_rounded, color: Colors.green.withOpacity(0.8), size: 18),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Text(
                              '$completedCount',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 28,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 28),

              // Section Header
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  isSuperAdmin ? 'All Scheduled Customers' : 'Assigned to You for Reading',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.8,
                  ),
                ),
              ),

              const SizedBox(height: 12),

              // Scheduled Customers List (Completed cards drop to bottom)
              if (_isLoading && _todayCustomers.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(40),
                  child: Center(
                    child: CircularProgressIndicator(color: Color(0xFF4F46E5)),
                  ),
                )
              else if (sortedCustomers.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E293B).withOpacity(0.4),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: Colors.white.withOpacity(0.06)),
                    ),
                    child: Column(
                      children: [
                        Icon(Icons.assignment_turned_in_outlined, size: 48, color: Colors.white.withOpacity(0.3)),
                        const SizedBox(height: 12),
                        const Text(
                          'No Customers Assigned to You',
                          style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold, fontSize: 16),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Your administrator can assign customer meter accounts to your profile in the Web Admin Panel.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                )
              else
                ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  itemCount: sortedCustomers.length,
                  itemBuilder: (context, index) {
                    final customer = sortedCustomers[index];
                    final isCompleted = customer.status == 'Completed';

                    return Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: isCompleted
                            ? const Color(0xFF1E293B).withOpacity(0.25)
                            : const Color(0xFF1E293B).withOpacity(0.6),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: isCompleted
                              ? Colors.green.withOpacity(0.1)
                              : Colors.white.withOpacity(0.06),
                          width: 1,
                        ),
                      ),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(20),
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => CustomerHistoryPage(customer: customer),
                            ),
                          ).then((_) {
                            if (mounted) setState(() {});
                          });
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Row(
                            children: [
                              // Index Circle Indicator
                              CircleAvatar(
                                radius: 18,
                                backgroundColor: isCompleted
                                    ? Colors.green.withOpacity(0.1)
                                    : const Color(0xFF4F46E5).withOpacity(0.15),
                                child: Text(
                                  '${index + 1}',
                                  style: TextStyle(
                                    color: isCompleted ? Colors.green : const Color(0xFF818CF8),
                                    fontWeight: FontWeight.bold,
                                    fontSize: 14,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 16),

                              // Details
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      customer.name,
                                      style: TextStyle(
                                        color: isCompleted ? Colors.white54 : Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                        decoration: isCompleted ? TextDecoration.lineThrough : null,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      customer.address,
                                      style: TextStyle(
                                        color: Colors.white.withOpacity(0.4),
                                        fontSize: 13,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    const SizedBox(height: 6),
                                    Row(
                                      children: [
                                        Icon(
                                          Icons.electric_meter_rounded,
                                          size: 13,
                                          color: Colors.white.withOpacity(0.3),
                                        ),
                                        const SizedBox(width: 4),
                                        Text(
                                          customer.meterNumber,
                                          style: TextStyle(
                                            color: Colors.white.withOpacity(0.3),
                                            fontSize: 11,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),

                              // Done / Pending Badge
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: isCompleted
                                      ? Colors.green.withOpacity(0.12)
                                      : Colors.amber.withOpacity(0.12),
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                    color: isCompleted
                                        ? Colors.green.withOpacity(0.3)
                                        : Colors.amber.withOpacity(0.3),
                                  ),
                                ),
                                child: Text(
                                  isCompleted ? 'Done' : 'Pending',
                                  style: TextStyle(
                                    color: isCompleted ? Colors.green : Colors.amber,
                                    fontSize: 10,
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
              const SizedBox(height: 100),
            ],
          ),
        ),
      ),
    );
  }
}
