import 'package:flutter/material.dart';
import 'customer_page.dart'; // To access Customer model

class ReadingInvoicePage extends StatelessWidget {
  final Customer customer;
  final String currentReadingStr;
  final double? previousReadingVal;

  const ReadingInvoicePage({
    super.key,
    required this.customer,
    required this.currentReadingStr,
    this.previousReadingVal,
  });

  @override
  Widget build(BuildContext context) {
    // Parse current reading
    final double currentReading = double.tryParse(currentReadingStr.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0.0;
    
    // Use actual previous reading if provided, otherwise estimate
    final double previousReading = (previousReadingVal != null && previousReadingVal! > 0)
        ? previousReadingVal!
        : (currentReading > 150 ? currentReading - 180.0 : currentReading * 0.6);
    final double consumption = (currentReading >= previousReading) ? (currentReading - previousReading) : currentReading;
    
    // Cost Calculations
    const double ratePerKwh = 0.15; // $0.15 per kWh
    final double consumptionCost = consumption * ratePerKwh;
    const double flatServiceFee = 5.00;
    final double totalBillAmount = consumptionCost + flatServiceFee;

    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [
              Color(0xFF0F172A), // Deep Slate
              Color(0xFF1E1B4B), // Very Dark Indigo
              Color(0xFF020617), // Black
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top header
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Reading Receipt',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, color: Colors.white70),
                      onPressed: () {
                        // Pop twice to return to Customer details screen
                        Navigator.pop(context);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 24),

                // Success Header
                Center(
                  child: Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.green.withOpacity(0.12),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.green.withOpacity(0.3), width: 2),
                        ),
                        child: const Icon(
                          Icons.check_circle_outline_rounded,
                          color: Colors.green,
                          size: 48,
                        ),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'Reading Registered Successfully',
                        style: TextStyle(
                          color: Colors.green,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Data synced to Cloud Database',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.4),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 32),

                // Bill Card (Receipt Design)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E293B).withOpacity(0.7),
                    borderRadius: BorderRadius.circular(28),
                    border: Border.all(
                      color: Colors.white.withOpacity(0.08),
                      width: 1,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Customer info
                      Text(
                        customer.name,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        customer.address,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 13,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.electric_meter_rounded, color: Colors.white.withOpacity(0.3), size: 14),
                          const SizedBox(width: 6),
                          Text(
                            'Meter ID: ${customer.meterNumber}',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.4),
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),
                      const Divider(color: Colors.white12, height: 1),
                      const SizedBox(height: 20),

                      // Consumption breakdown
                      _buildReceiptRow('Current Reading', '$currentReadingStr kWh'),
                      const SizedBox(height: 12),
                      _buildReceiptRow('Previous Reading', '${previousReading.toStringAsFixed(0)} kWh'),
                      const SizedBox(height: 12),
                      _buildReceiptRow(
                        'Total Consumption',
                        '${consumption.toStringAsFixed(0)} kWh',
                        valueColor: const Color(0xFF818CF8),
                        isBold: true,
                      ),
                      const SizedBox(height: 20),
                      const Divider(color: Colors.white12, height: 1),
                      const SizedBox(height: 20),

                      // Cost breakdown
                      _buildReceiptRow('Rate per kWh', '\$${ratePerKwh.toStringAsFixed(2)}'),
                      const SizedBox(height: 12),
                      _buildReceiptRow('Consumption Cost', '\$${consumptionCost.toStringAsFixed(2)}'),
                      const SizedBox(height: 12),
                      _buildReceiptRow('Flat Service Fee', '\$${flatServiceFee.toStringAsFixed(2)}'),
                      const SizedBox(height: 20),
                      const Divider(color: Colors.white12, height: 1),
                      const SizedBox(height: 20),

                      // Total Row
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Total Bill Amount',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            '\$${totalBillAmount.toStringAsFixed(2)}',
                            style: const TextStyle(
                              color: Colors.amber,
                              fontSize: 22,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 36),

                // Back Button
                SizedBox(
                  width: double.infinity,
                  height: 54,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4F46E5),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      elevation: 0,
                    ),
                    onPressed: () {
                      // Return to the customer history page
                      Navigator.pop(context);
                    },
                    child: const Text(
                      'Done & Return',
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

  Widget _buildReceiptRow(String label, String value, {Color? valueColor, bool isBold = false}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: Colors.white54,
            fontSize: 14,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: valueColor ?? Colors.white,
            fontSize: 14,
            fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ],
    );
  }
}
