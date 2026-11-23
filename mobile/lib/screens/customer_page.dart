import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'customer_history_page.dart';

class Customer {
  final String id;
  final String name;
  final String address;
  final String phone;
  final String meterNumber;
  String status;

  Customer({
    required this.id,
    required this.name,
    required this.address,
    required this.phone,
    required this.meterNumber,
    required this.status,
  });
}

class CustomerPage extends StatefulWidget {
  const CustomerPage({super.key});

  @override
  State<CustomerPage> createState() => _CustomerPageState();
}

class _CustomerPageState extends State<CustomerPage> {
  List<Customer> _customers = [];
  bool _isLoading = true;
  String _searchQuery = '';
  StreamSubscription<List<Map<String, dynamic>>>? _subscribersSubscription;

  @override
  void initState() {
    super.initState();
    _subscribeToSubscribers();
    _loadCustomers();
  }

  void _subscribeToSubscribers() {
    _subscribersSubscription = ApiService.instance.getSubscribersStream().listen((data) {
      if (mounted) {
        _updateCustomersFromData(data);
      }
    });
  }

  void _updateCustomersFromData(List<Map<String, dynamic>> data) {
    setState(() {
      _customers = data.map((item) {
        final id = item['subscriber_id']?.toString() ?? '';
        return Customer(
          id: id,
          name: item['full_name']?.toString() ?? 'Unnamed Customer',
          address: item['address']?.toString() ?? 'No address provided',
          phone: item['phone']?.toString() ?? '',
          meterNumber: 'MTR-${id.length > 6 ? id.substring(0, 6) : id}',
          status: (item['is_active'] == true) ? 'Active' : 'Inactive',
        );
      }).toList();
      _isLoading = false;
    });
  }

  Future<void> _loadCustomers() async {
    if (!mounted) return;
    final data = await ApiService.instance.getAllSubscribers();
    if (mounted) {
      _updateCustomersFromData(data);
    }
  }

  @override
  void dispose() {
    _subscribersSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final filteredCustomers = _customers.where((customer) {
      final query = _searchQuery.toLowerCase();
      final nameMatches = customer.name.toLowerCase().contains(query);
      final addressMatches = customer.address.toLowerCase().contains(query);
      final meterMatches = customer.meterNumber.toLowerCase().contains(query);
      final phoneMatches = customer.phone.toLowerCase().contains(query);
      return nameMatches || addressMatches || meterMatches || phoneMatches;
    }).toList();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header with overflow-protected layout
            Padding(
              padding: const EdgeInsets.only(left: 20, right: 16, top: 16, bottom: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Customer Directory (All)',
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                          overflow: TextOverflow.ellipsis,
                          maxLines: 1,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'All registered customers in company database',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 13,
                          ),
                          overflow: TextOverflow.ellipsis,
                          maxLines: 1,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.refresh_rounded, color: Colors.cyan),
                    onPressed: _loadCustomers,
                    tooltip: 'Refresh Database',
                  ),
                ],
              ),
            ),

            // Search Bar
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1E293B).withOpacity(0.8),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: Colors.white.withOpacity(0.1),
                    width: 1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.1),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: TextField(
                  style: const TextStyle(color: Colors.white),
                  onChanged: (value) {
                    setState(() {
                      _searchQuery = value;
                    });
                  },
                  decoration: InputDecoration(
                    hintText: 'Search by name, phone, address, meter...',
                    hintStyle: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 13),
                    prefixIcon: Icon(Icons.search, color: Colors.white.withOpacity(0.6)),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  ),
                ),
              ),
            ),

            // Customer List View with Pull-To-Refresh
            Expanded(
              child: _isLoading && _customers.isEmpty
                  ? const Center(
                      child: CircularProgressIndicator(color: Color(0xFF4F46E5)),
                    )
                  : RefreshIndicator(
                      onRefresh: _loadCustomers,
                      color: const Color(0xFF4F46E5),
                      backgroundColor: const Color(0xFF1E293B),
                      child: filteredCustomers.isEmpty
                          ? ListView(
                              physics: const AlwaysScrollableScrollPhysics(),
                              children: [
                                SizedBox(height: MediaQuery.of(context).size.height * 0.2),
                                Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(
                                        Icons.people_outline_rounded,
                                        size: 64,
                                        color: Colors.white.withOpacity(0.2),
                                      ),
                                      const SizedBox(height: 16),
                                      Text(
                                        _searchQuery.isEmpty
                                            ? 'No customers found in database'
                                            : 'No customers match "$_searchQuery"',
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.5),
                                          fontSize: 15,
                                        ),
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        'Tap + below to add a customer',
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.3),
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
                              padding: const EdgeInsets.fromLTRB(20, 10, 20, 100),
                              itemCount: filteredCustomers.length,
                              itemBuilder: (context, index) {
                                final customer = filteredCustomers[index];

                                return Container(
                                  margin: const EdgeInsets.only(bottom: 14),
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      colors: [
                                        const Color(0xFF1E293B).withOpacity(0.8),
                                        const Color(0xFF0F172A).withOpacity(0.8),
                                      ],
                                      begin: Alignment.topLeft,
                                      end: Alignment.bottomRight,
                                    ),
                                    borderRadius: BorderRadius.circular(20),
                                    border: Border.all(
                                      color: Colors.white.withOpacity(0.08),
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
                                          Container(
                                            padding: const EdgeInsets.all(12),
                                            decoration: BoxDecoration(
                                              color: const Color(0xFF4F46E5).withOpacity(0.12),
                                              shape: BoxShape.circle,
                                            ),
                                            child: const Icon(
                                              Icons.person_rounded,
                                              color: Color(0xFF818CF8),
                                              size: 24,
                                            ),
                                          ),
                                          const SizedBox(width: 14),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  customer.name,
                                                  style: const TextStyle(
                                                    color: Colors.white,
                                                    fontWeight: FontWeight.bold,
                                                    fontSize: 16,
                                                  ),
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                                const SizedBox(height: 4),
                                                Text(
                                                  customer.address,
                                                  style: TextStyle(
                                                    color: Colors.white.withOpacity(0.6),
                                                    fontSize: 13,
                                                  ),
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                                if (customer.phone.isNotEmpty) ...[
                                                  const SizedBox(height: 4),
                                                  Text(
                                                    'Phone: ${customer.phone}',
                                                    style: TextStyle(
                                                      color: Colors.cyan.withOpacity(0.8),
                                                      fontSize: 12,
                                                    ),
                                                  ),
                                                ],
                                                const SizedBox(height: 6),
                                                Row(
                                                  children: [
                                                    Icon(
                                                      Icons.electric_meter,
                                                      size: 14,
                                                      color: Colors.white.withOpacity(0.4),
                                                    ),
                                                    const SizedBox(width: 4),
                                                    Text(
                                                      customer.meterNumber,
                                                      style: TextStyle(
                                                        color: Colors.white.withOpacity(0.4),
                                                        fontSize: 12,
                                                        fontWeight: FontWeight.w600,
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              ],
                                            ),
                                          ),
                                          Icon(
                                            Icons.arrow_forward_ios,
                                            color: Colors.white.withOpacity(0.3),
                                            size: 16,
                                          ),
                                        ],
                                      ),
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
      floatingActionButton: Padding(
        padding: const EdgeInsets.only(bottom: 70),
        child: FloatingActionButton(
          onPressed: () {
            _showAddCustomerDialog(context);
          },
          backgroundColor: const Color(0xFF4F46E5),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: const Icon(Icons.add),
        ),
      ),
    );
  }

  void _showAddCustomerDialog(BuildContext context) {
    final nameController = TextEditingController();
    final addressController = TextEditingController();
    final phoneController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: const Text(
          'Add New Customer',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildDialogField(
                controller: nameController,
                label: 'Customer Full Name',
                icon: Icons.person_outline,
              ),
              const SizedBox(height: 16),
              _buildDialogField(
                controller: addressController,
                label: 'Address',
                icon: Icons.map_outlined,
              ),
              const SizedBox(height: 16),
              _buildDialogField(
                controller: phoneController,
                label: 'Phone Number',
                icon: Icons.phone_outlined,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF4F46E5),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: () async {
              final name = nameController.text.trim();
              if (name.isNotEmpty) {
                final address = addressController.text.trim();
                final phone = phoneController.text.trim();

                Navigator.pop(context);

                final result = await ApiService.instance.addSubscriber(
                  name: name,
                  address: address,
                  phone: phone,
                );

                await _loadCustomers();

                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Customer "$name" saved and synced!'),
                      backgroundColor: result != null ? Colors.green : Colors.amber,
                    ),
                  );
                }
              }
            },
            child: const Text('Save Customer'),
          ),
        ],
      ),
    );
  }

  Widget _buildDialogField({
    required TextEditingController controller,
    required String label,
    required IconData icon,
  }) {
    return TextField(
      controller: controller,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: Colors.white54),
        prefixIcon: Icon(icon, color: Colors.white38),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF4F46E5)),
        ),
        filled: true,
        fillColor: const Color(0xFF0F172A),
      ),
    );
  }
}
