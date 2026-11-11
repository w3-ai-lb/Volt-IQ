import React, { useState, useEffect } from 'react';
import { useData } from '../../context/DataContext';
import { X, UserCheck, Check } from 'lucide-react';

export default function CustomerAssignModal({ employee, isOpen, onClose }) {
  const { customers, assignCustomersToEmployee } = useData();
  const [selectedCustomerIds, setSelectedCustomerIds] = useState([]);

  // Sync state whenever modal opens or employee changes
  useEffect(() => {
    if (employee && isOpen) {
      const initialIds = customers
        .filter(c => c.assignedEmployeeId === employee.id)
        .map(c => c.id);
      setSelectedCustomerIds(initialIds);
    }
  }, [employee, isOpen, customers]);

  if (!isOpen || !employee) return null;

  const toggleCustomer = (customerId) => {
    if (selectedCustomerIds.includes(customerId)) {
      setSelectedCustomerIds(selectedCustomerIds.filter(id => id !== customerId));
    } else {
      setSelectedCustomerIds([...selectedCustomerIds, customerId]);
    }
  };

  const handleSave = () => {
    assignCustomersToEmployee(employee.id, selectedCustomerIds);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <img src={employee.avatar} alt="" className="w-10 h-10 rounded-xl object-cover border border-cyan-500/30" />
            <div>
              <h3 className="font-bold text-base text-white">Assign Customers to {employee.name}</h3>
              <p className="text-xs text-slate-400">{employee.roleTitle} ({employee.zone})</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Customer Checklist Body */}
        <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto text-xs">
          <div className="flex items-center justify-between text-slate-400">
            <span>Select customer accounts to assign to {employee.name}:</span>
            <span className="font-bold text-cyan-400">{selectedCustomerIds.length} Selected</span>
          </div>

          <div className="space-y-2">
            {customers.map((cust) => {
              const isChecked = selectedCustomerIds.includes(cust.id);
              const currentlyAssignedName = cust.assignedEmployeeName || 'Unassigned';

              return (
                <div
                  key={cust.id}
                  onClick={() => toggleCustomer(cust.id)}
                  className={`p-3 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                    isChecked
                      ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-200'
                      : 'bg-slate-800/40 border-slate-700/60 text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-lg border flex items-center justify-center transition-colors ${
                      isChecked ? 'bg-cyan-500 border-cyan-400 text-slate-950 font-bold' : 'border-slate-600'
                    }`}>
                      {isChecked && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                    </div>
                    <div>
                      <span className="font-bold text-slate-100 block">{cust.name}</span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {cust.accountNo} | Tariff: {cust.tariffType}
                      </span>
                    </div>
                  </div>

                  <span className={`text-[10px] ${cust.assignedEmployeeId ? 'text-cyan-400 font-medium' : 'text-slate-500'}`}>
                    Currently: {currentlyAssignedName}
                  </span>
                </div>
              );
            })}
          </div>

        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-800 bg-slate-900/90">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-semibold transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white shadow-md hover:opacity-95 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <UserCheck className="w-4 h-4" /> Save Assignments
          </button>
        </div>

      </div>
    </div>
  );
}
