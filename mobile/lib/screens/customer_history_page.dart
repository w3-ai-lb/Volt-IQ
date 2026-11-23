import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'customer_page.dart';
import 'ocr_reading_page.dart';

class CustomerHistoryPage extends StatefulWidget {
  final Customer customer;

  const CustomerHistoryPage({super.key, required this.customer});

  @override
  State<CustomerHistoryPage> createState() => _CustomerHistoryPageState();
}

class _CustomerHistoryPageState extends State<CustomerHistoryPage> {
  List<Map<String, dynamic>> _history = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    if (!mounted) return;
    setState(() => _isLoading = true);
    final list = await ApiService.instance.getCustomerReadings(widget.customer.id);
    if (mounted) {
      setState(() {
        _history = list;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [
              Color(0xFF0F172A), // Deep Slate
              Color(0xFF1E1B4B), // Very Dark Indigo
              Color(0xFF020617), // Solid Dark Background
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Customer Profile Header Card
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E293B).withOpacity(0.8),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: Colors.white.withOpacity(0.08),
                      width: 1,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(
                              widget.customer.name,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            decoration: BoxDecoration(
                              color: widget.customer.status == 'Completed'
                                  ? Colors.green.withOpacity(0.15)
                                  : Colors.amber.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: widget.customer.status == 'Completed'
                                    ? Colors.green.withOpacity(0.3)
                                    : Colors.amber.withOpacity(0.3),
                              ),
                            ),
                            child: Text(
                              widget.customer.status,
                              style: TextStyle(
                                color: widget.customer.status == 'Completed' ? Colors.green : Colors.amber,
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.location_on_outlined, color: Colors.white.withOpacity(0.4), size: 16),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              widget.customer.address,
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.6),
                                fontSize: 14,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.electric_meter_outlined, color: Colors.white.withOpacity(0.4), size: 16),
                          const SizedBox(width: 6),
                          Text(
                            'Meter ID: ${widget.customer.meterNumber}',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.4),
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),

              // Action Button (Record Reading)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                child: SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4F46E5),
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => OcrReadingPage(customer: widget.customer),
                        ),
                      ).then((_) {
                        _loadHistory();
                        if (mounted) setState(() {});
                      });
                    },
                    icon: const Icon(Icons.camera_alt_rounded),
                    label: const Text(
                      'Record New Reading',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // History list title
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  'Reading History',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),

              // List of readings with pull-to-refresh
              Expanded(
                child: _isLoading && _history.isEmpty
                    ? const Center(child: CircularProgressIndicator(color: Color(0xFF4F46E5)))
                    : RefreshIndicator(
                        onRefresh: _loadHistory,
                        color: const Color(0xFF4F46E5),
                        child: _history.isEmpty
                            ? ListView(
                                physics: const AlwaysScrollableScrollPhysics(),
                                children: [
                                  const SizedBox(height: 48),
                                  Center(
                                    child: Column(
                                      children: [
                                        Icon(
                                          Icons.history_rounded,
                                          size: 56,
                                          color: Colors.white.withOpacity(0.2),
                                        ),
                                        const SizedBox(height: 14),
                                        Text(
                                          'No Readings Recorded Yet',
                                          style: TextStyle(
                                            color: Colors.white.withOpacity(0.6),
                                            fontSize: 16,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                        const SizedBox(height: 6),
                                        Text(
                                          'Tap "Record New Reading" to scan this meter',
                                          style: TextStyle(
                                            color: Colors.white.withOpacity(0.35),
                                            fontSize: 13,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              )
                            : ListView.builder(
                                physics: const AlwaysScrollableScrollPhysics(),
                                padding: const EdgeInsets.all(20),
                                itemCount: _history.length,
                                itemBuilder: (context, index) {
                                  final record = _history[index];
                                  final isPaid = (record['is_paid'] == true || record['isPaid'] == true);
                                  final readingDisplay = record['reading']?.toString() ??
                                      '${record['reading_value'] ?? '0'} kWh';
                                  final dateDisplay = record['date']?.toString() ??
                                      (record['reading_date']?.toString().split('T')[0] ?? 'Recent');
                                  final amountDisplay = record['amount']?.toString() ??
                                      (record['cost'] != null ? '\$${(record['cost'] as num).toStringAsFixed(2)}' : '\$5.00');

                                  return Container(
                                    margin: const EdgeInsets.only(bottom: 16),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF1E293B).withOpacity(0.6),
                                      borderRadius: BorderRadius.circular(20),
                                      border: Border.all(
                                        color: Colors.white.withOpacity(0.08),
                                        width: 1,
                                      ),
                                    ),
                                    child: ListTile(
                                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                      onTap: () => _showReadingDetailsDialog(context, record),
                                      leading: Container(
                                        padding: const EdgeInsets.all(10),
                                        decoration: BoxDecoration(
                                          color: isPaid ? Colors.green.withOpacity(0.1) : Colors.redAccent.withOpacity(0.1),
                                          shape: BoxShape.circle,
                                        ),
                                        child: Icon(
                                          isPaid ? Icons.payment_rounded : Icons.money_off_rounded,
                                          color: isPaid ? Colors.green : Colors.redAccent,
                                          size: 22,
                                        ),
                                      ),
                                      title: Text(
                                        readingDisplay,
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontWeight: FontWeight.bold,
                                          fontSize: 16,
                                        ),
                                      ),
                                      subtitle: Padding(
                                        padding: const EdgeInsets.only(top: 4),
                                        child: Text(
                                          dateDisplay,
                                          style: TextStyle(
                                            color: Colors.white.withOpacity(0.5),
                                            fontSize: 12,
                                          ),
                                        ),
                                      ),
                                      trailing: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Text(
                                            amountDisplay,
                                            style: const TextStyle(
                                              color: Colors.white70,
                                              fontWeight: FontWeight.bold,
                                              fontSize: 13,
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                            decoration: BoxDecoration(
                                              color: isPaid ? Colors.green.withOpacity(0.15) : Colors.redAccent.withOpacity(0.15),
                                              borderRadius: BorderRadius.circular(10),
                                              border: Border.all(
                                                color: isPaid ? Colors.green.withOpacity(0.3) : Colors.redAccent.withOpacity(0.3),
                                              ),
                                            ),
                                            child: Text(
                                              isPaid ? 'Paid' : 'Unpaid',
                                              style: TextStyle(
                                                color: isPaid ? Colors.green : Colors.redAccent,
                                                fontSize: 10,
                                                fontWeight: FontWeight.bold,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                },
                              ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showReadingDetailsDialog(BuildContext context, Map<String, dynamic> record) {
    final isPaid = (record['is_paid'] == true || record['isPaid'] == true);
    final readingDisplay = record['reading']?.toString() ?? '${record['reading_value'] ?? '0'} kWh';
    final dateDisplay = record['date']?.toString() ?? (record['reading_date']?.toString().split('T')[0] ?? 'Recent');
    final amountDisplay = record['amount']?.toString() ??
        (record['cost'] != null ? '\$${(record['cost'] as num).toStringAsFixed(2)}' : '\$5.00');
    final recordedBy = record['recordedBy']?.toString() ?? (record['captured_by']?.toString() ?? 'Alex Carter');

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: const Text(
          'Reading Details',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildDialogInfoRow('Recorded Value', readingDisplay, Icons.speed_rounded),
              const SizedBox(height: 12),
              _buildDialogInfoRow('Date & Time', dateDisplay, Icons.event_note_rounded),
              const SizedBox(height: 12),
              _buildDialogInfoRow('Billing Amount', amountDisplay, Icons.attach_money_rounded),
              const SizedBox(height: 12),
              _buildDialogInfoRow('Recorded By', recordedBy, Icons.badge_outlined),
              const SizedBox(height: 12),
              _buildDialogInfoRow(
                'Payment Status',
                isPaid ? 'PAID' : 'UNPAID',
                isPaid ? Icons.check_circle_outline_rounded : Icons.cancel_outlined,
                valueColor: isPaid ? Colors.green : Colors.redAccent,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  Widget _buildDialogInfoRow(String label, String value, IconData icon, {Color? valueColor}) {
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 20),
        const SizedBox(width: 12),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
            const SizedBox(height: 2),
            Text(
              value,
              style: TextStyle(
                color: valueColor ?? Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
