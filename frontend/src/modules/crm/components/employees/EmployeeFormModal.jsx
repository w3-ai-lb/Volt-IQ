import React, { useState, useEffect } from 'react';
import { useData } from '../../context/DataContext';
import { ROLES } from '../../context/AuthContext';
import { X, UserCheck, Save, Upload, Image as ImageIcon } from 'lucide-react';

export default function EmployeeFormModal({ isOpen, onClose, employeeToEdit = null }) {
  const { addEmployee, updateEmployee } = useData();

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    phone: '',
    role: ROLES.OFFICE_EMPLOYEE,
    roleTitle: 'Billing & Metering Specialist',
    department: 'Customer Relations',
    zone: 'North Metro District',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120'
  });

  useEffect(() => {
    if (employeeToEdit) {
      setFormData({
        name: employeeToEdit.name || '',
        email: employeeToEdit.email || '',
        password: '',
        phone: employeeToEdit.phone || '',
        role: employeeToEdit.role || ROLES.OFFICE_EMPLOYEE,
        roleTitle: employeeToEdit.roleTitle || '',
        department: employeeToEdit.department || '',
        zone: employeeToEdit.zone || 'North Metro District',
        avatar: employeeToEdit.avatar || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120'
      });
    } else {
      setFormData({
        name: '',
        email: '',
        password: '',
        phone: '',
        role: ROLES.OFFICE_EMPLOYEE,
        roleTitle: 'Billing & Metering Specialist',
        department: 'Customer Relations',
        zone: 'North Metro District',
        avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120'
      });
    }
  }, [employeeToEdit, isOpen]);

  if (!isOpen) return null;

  const handleImageFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setFormData(prev => ({ ...prev, avatar: reader.result }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (employeeToEdit) {
      updateEmployee(employeeToEdit.id, formData);
    } else {
      addEmployee(formData);
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">
                {employeeToEdit ? 'Edit Employee Details' : 'Register New Employee'}
              </h3>
              <p className="text-xs text-slate-400">Administrator Employee Management</p>
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
          
          {/* Profile Picture Upload Section */}
          <div className="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/60 flex items-center gap-4">
            <div className="relative shrink-0">
              <img
                src={formData.avatar}
                alt="Profile Preview"
                className="w-16 h-16 rounded-2xl object-cover border-2 border-cyan-500/50 shadow-md"
              />
              <div className="absolute -bottom-1 -right-1 p-1 bg-cyan-500 rounded-lg text-white">
                <ImageIcon className="w-3 h-3" />
              </div>
            </div>

            <div className="flex-1 space-y-2">
              <label className="block font-semibold text-slate-200">
                Employee Profile Picture
              </label>
              
              <div className="flex items-center gap-2">
                <label className="px-3 py-1.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-semibold flex items-center gap-1.5 cursor-pointer transition-colors text-xs">
                  <Upload className="w-3.5 h-3.5" />
                  <span>Import Picture</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleImageFileChange}
                    className="hidden"
                  />
                </label>

                <span className="text-[11px] text-slate-400">or paste URL below</span>
              </div>

              <input
                type="text"
                placeholder="https://example.com/avatar.jpg"
                value={formData.avatar.startsWith('data:') ? 'Image uploaded from file' : formData.avatar}
                onChange={e => setFormData({ ...formData, avatar: e.target.value })}
                className="w-full px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-slate-300 text-[11px] focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Full Name *</label>
              <input
                type="text"
                required
                placeholder="e.g. Michael Thorne"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Corporate Email *</label>
              <input
                type="email"
                required
                placeholder="name@company.com"
                value={formData.email}
                onChange={e => setFormData({ ...formData, email: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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

            <div>
              <label className="block font-semibold text-slate-300 mb-1">
                {employeeToEdit ? 'New Password (optional)' : 'Login Password (Min 6 chars) *'}
              </label>
              <input
                type="password"
                required={!employeeToEdit}
                minLength={6}
                placeholder="••••••••"
                value={formData.password}
                onChange={e => setFormData({ ...formData, password: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">System Permission Role</label>
              <select
                value={formData.role}
                onChange={e => setFormData({ ...formData, role: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                <option value={ROLES.ADMIN}>Administrator (Full Access)</option>
                <option value={ROLES.MANAGER}>Manager (Staff & Reports)</option>
                <option value={ROLES.OFFICE_EMPLOYEE}>Office Employee (Billing & Payments)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Job Title</label>
              <input
                type="text"
                placeholder="Senior Meter Reader / Billing Officer"
                value={formData.roleTitle}
                onChange={e => setFormData({ ...formData, roleTitle: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Department</label>
              <select
                value={formData.department}
                onChange={e => setFormData({ ...formData, department: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                <option value="Finance & Billing">Finance & Billing</option>
                <option value="Customer Relations">Customer Relations</option>
                <option value="Operations & IT">Operations & IT</option>
                <option value="Field Audit & Services">Field Audit & Services</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1">Assigned Zone / Region</label>
            <input
              type="text"
              placeholder="North Metro District"
              value={formData.zone}
              onChange={e => setFormData({ ...formData, zone: e.target.value })}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
            />
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
              <span>{employeeToEdit ? 'Save Changes' : 'Register Employee'}</span>
            </button>
          </div>

        </form>

      </div>
    </div>
  );
}
