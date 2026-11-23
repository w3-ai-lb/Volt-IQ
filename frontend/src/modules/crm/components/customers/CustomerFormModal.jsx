import React, { useState, useEffect } from 'react';
import { useData } from '../../context/DataContext';
import { X, UserPlus, Save } from 'lucide-react';

export default function CustomerFormModal({ isOpen, onClose, customerToEdit = null }) {
  const { employees, addCustomer, updateCustomer } = useData();

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    address: '',
    tariffType: 'Residential',
    meterNo: '',
    initialReading: 0,
    assignedEmployeeId: employees[0]?.id || '',
    meterType: 'Digital Smart Meter',
    zone: 'North Metro District',
    status: 'Active'
  });

  useEffect(() => {
    if (customerToEdit) {
      setFormData({
        name: customerToEdit.name || '',
        email: customerToEdit.email || '',
        phone: customerToEdit.phone || '',
        address: customerToEdit.address || '',
        tariffType: customerToEdit.tariffType || 'Residential',
        meterNo: customerToEdit.meterNo || '',
        initialReading: customerToEdit.currentReading || 0,
        assignedEmployeeId: customerToEdit.assignedEmployeeId || employees[0]?.id || '',
        meterType: customerToEdit.meterType || 'Digital Smart Meter',
        zone: customerToEdit.zone || 'North Metro District',
        status: customerToEdit.status || 'Active'
      });
    } else {
      setFormData({
        name: '',
        email: '',
        phone: '',
        address: '',
        tariffType: 'Residential',
        meterNo: '',
        initialReading: 0,
        assignedEmployeeId: employees[0]?.id || '',
        meterType: 'Digital Smart Meter',
        zone: 'North Metro District',
        status: 'Active'
      });
    }
  }, [customerToEdit, employees, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (customerToEdit) {
      updateCustomer(customerToEdit.id, formData);
    } else {
      addCustomer(formData);
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <UserPlus className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">
                {customerToEdit ? 'Edit Customer Account' : 'Add New Customer Account'}
              </h3>
              <p className="text-xs text-slate-400">Electricity Utility CRM Registration</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Full Name / Business Name *</label>
              <input
                type="text"
                required
                placeholder="e.g. Acme Logistics HQ"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Phone Number</label>
              <input
                type="text"
                placeholder="+1 (555) 000-0000"
                value={formData.phone}
                onChange={e => setFormData({ ...formData, phone: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Email Address</label>
              <input
                type="email"
                placeholder="customer@domain.com"
                value={formData.email}
                onChange={e => setFormData({ ...formData, email: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Tariff Classification</label>
              <select
                value={formData.tariffType}
                onChange={e => setFormData({ ...formData, tariffType: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                <option value="Residential">Residential</option>
                <option value="Commercial">Commercial</option>
                <option value="Industrial">Industrial</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1">Service Address</label>
            <input
              type="text"
              placeholder="123 Utility Way, Metro City"
              value={formData.address}
              onChange={e => setFormData({ ...formData, address: e.target.value })}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Meter Serial Number</label>
              <input
                type="text"
                placeholder="e.g. MTR-998811 (Auto generated if blank)"
                value={formData.meterNo}
                onChange={e => setFormData({ ...formData, meterNo: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Initial Meter Reading (kWh)</label>
              <input
                type="number"
                step="0.1"
                placeholder="0.0"
                value={formData.initialReading}
                onChange={e => setFormData({ ...formData, initialReading: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Assigned Office / Field Agent</label>
              <select
                value={formData.assignedEmployeeId}
                onChange={e => setFormData({ ...formData, assignedEmployeeId: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                {employees.map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name} ({emp.roleTitle})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Meter Hardware Type</label>
              <select
                value={formData.meterType}
                onChange={e => setFormData({ ...formData, meterType: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                <option value="Digital Smart Meter">Digital Smart Meter</option>
                <option value="Analog Dial Meter">Analog Dial Meter</option>
                <option value="High-Voltage Smart Meter">High-Voltage Smart Meter</option>
              </select>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-semibold transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white shadow-md hover:opacity-95 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Save className="w-4 h-4" />
              <span>{customerToEdit ? 'Save Changes' : 'Register Customer'}</span>
            </button>
          </div>

        </form>

      </div>
    </div>
  );
}
