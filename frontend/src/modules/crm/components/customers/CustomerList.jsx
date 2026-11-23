import React, { useState } from 'react';
import { useData } from '../../context/DataContext';
import { useAuth, PERMISSIONS } from '../../context/AuthContext';
import { formatCurrency, formatKwh } from '../../utils/invoiceGenerator';
import CustomerFormModal from './CustomerFormModal';
import CustomerDetailModal from './CustomerDetailModal';
import {
  Users,
  Search,
  Filter,
  UserPlus,
  Edit,
  Trash2,
  CreditCard
} from 'lucide-react';

export default function CustomerList({ onRecordPaymentForCustomer }) {
  const { customers, deleteCustomer, employees } = useData();
  const { hasPermission } = useAuth();

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTariff, setSelectedTariff] = useState('All');
  const [selectedEmployee, setSelectedEmployee] = useState('All');

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);

  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [viewingCustomer, setViewingCustomer] = useState(null);

  // Search & Filter logic
  const filteredCustomers = customers.filter((cust) => {
    const matchesSearch =
      cust.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cust.accountNo.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cust.meterNo.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cust.phone.includes(searchTerm);

    const matchesTariff = selectedTariff === 'All' || cust.tariffType === selectedTariff;
    const matchesEmployee = selectedEmployee === 'All' || cust.assignedEmployeeId === selectedEmployee;

    return matchesSearch && matchesTariff && matchesEmployee;
  });

  const handleDelete = (e, customerId, customerName) => {
    e.stopPropagation(); // Don't trigger row click modal
    if (window.confirm(`Are you sure you want to delete customer account "${customerName}"? This action cannot be undone.`)) {
      deleteCustomer(customerId);
    }
  };

  const handleEdit = (e, cust) => {
    e.stopPropagation(); // Don't trigger row click modal
    setEditingCustomer(cust);
    setIsFormOpen(true);
  };

  const handlePay = (e, cust) => {
    e.stopPropagation(); // Don't trigger row click modal
    onRecordPaymentForCustomer(cust);
  };

  const handleRowClick = (cust) => {
    setViewingCustomer(cust);
    setIsDetailOpen(true);
  };

  return (
    <div className="space-y-6 pb-12">
      
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            Customer Directory <Users className="w-5 h-5 text-cyan-400" />
          </h2>
          <p className="text-xs text-slate-400">
            Click any customer row to open profile details.
            {hasPermission(PERMISSIONS.ADD_CUSTOMER)
              ? ' Administrator/Manager Access: Full registration, edits, and deletions.'
              : ' Office Employee Access: View customer profiles and process payments.'}
          </p>
        </div>

        {hasPermission(PERMISSIONS.ADD_CUSTOMER) && (
          <button
            onClick={() => {
              setEditingCustomer(null);
              setIsFormOpen(true);
            }}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white text-xs shadow-md shadow-cyan-500/20 hover:opacity-95 transition-all flex items-center gap-2 cursor-pointer self-start sm:self-auto"
          >
            <UserPlus className="w-4 h-4" /> Add New Customer
          </button>
        )}
      </div>

      {/* Search & Filter Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-slate-900/80 p-4 rounded-2xl border border-slate-800">
        
        {/* Search Bar */}
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by Name, Account #, Meter #..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
          />
        </div>

        {/* Tariff Filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400 shrink-0" />
          <select
            value={selectedTariff}
            onChange={(e) => setSelectedTariff(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="All">All Tariff Types</option>
            <option value="Residential">Residential</option>
            <option value="Commercial">Commercial</option>
            <option value="Industrial">Industrial</option>
          </select>
        </div>

        {/* Employee Filter */}
        <div>
          <select
            value={selectedEmployee}
            onChange={(e) => setSelectedEmployee(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <option value="All">All Assigned Officers</option>
            {employees.map(emp => (
              <option key={emp.id} value={emp.id}>{emp.name}</option>
            ))}
          </select>
        </div>

      </div>

      {/* Customer Accounts Table */}
      <div className="p-4 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3 rounded-l-xl">Customer Account</th>
                <th className="px-4 py-3">Meter Serial</th>
                <th className="px-4 py-3">Tariff</th>
                <th className="px-4 py-3">Latest Reading</th>
                <th className="px-4 py-3">Outstanding Balance</th>
                <th className="px-4 py-3">Assigned Officer</th>
                <th className="px-4 py-3 rounded-r-xl text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredCustomers.length > 0 ? (
                filteredCustomers.map((cust) => (
                  <tr
                    key={cust.id}
                    onClick={() => handleRowClick(cust)}
                    className="hover:bg-cyan-950/30 transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3">
                      <div>
                        <span className="font-bold text-slate-100 group-hover:text-cyan-300 block text-sm transition-colors">
                          {cust.name}
                        </span>
                        <span className="text-[11px] font-mono text-cyan-400">{cust.accountNo}</span>
                      </div>
                    </td>

                    <td className="px-4 py-3 font-mono text-slate-300">{cust.meterNo}</td>

                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                        cust.tariffType === 'Commercial'
                          ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                          : cust.tariffType === 'Industrial'
                          ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                          : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
                      }`}>
                        {cust.tariffType}
                      </span>
                    </td>

                    <td className="px-4 py-3 font-mono">
                      <span className="font-bold text-slate-200">{formatKwh(cust.currentReading)}</span>
                      <span className="text-[10px] text-slate-500 block">{cust.lastReadingDate}</span>
                    </td>

                    <td className="px-4 py-3 font-bold">
                      <span className={cust.balance > 0 ? 'text-amber-400' : 'text-emerald-400'}>
                        {formatCurrency(cust.balance)}
                      </span>
                    </td>

                    <td className="px-4 py-3 text-slate-400">{cust.assignedEmployeeName}</td>

                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        
                        {/* Record Payment Action */}
                        <button
                          onClick={(e) => handlePay(e, cust)}
                          className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/30 transition-colors cursor-pointer"
                          title="Record Payment"
                        >
                          <CreditCard className="w-4 h-4" />
                        </button>

                        {/* Admin / Manager Edit */}
                        {hasPermission(PERMISSIONS.EDIT_CUSTOMER) && (
                          <button
                            onClick={(e) => handleEdit(e, cust)}
                            className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-amber-400 hover:bg-slate-700 transition-colors cursor-pointer"
                            title="Edit Customer Info"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                        )}

                        {/* Admin Only Delete */}
                        {hasPermission(PERMISSIONS.DELETE_CUSTOMER) && (
                          <button
                            onClick={(e) => handleDelete(e, cust.id, cust.name)}
                            className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30 transition-colors cursor-pointer"
                            title="Delete Customer Account (Admin Only)"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}

                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                    No customer accounts match your search parameters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Form Modal */}
      <CustomerFormModal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        customerToEdit={editingCustomer}
      />

      {/* Detail Profile Modal */}
      <CustomerDetailModal
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        customer={viewingCustomer}
        onRecordPayment={(cust) => onRecordPaymentForCustomer(cust)}
      />

    </div>
  );
}
