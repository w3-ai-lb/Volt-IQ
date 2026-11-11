import React, { useState } from 'react';
import { useData } from '../../context/DataContext';
import { useAuth, PERMISSIONS, ROLES } from '../../context/AuthContext';
import EmployeeFormModal from './EmployeeFormModal';
import CustomerAssignModal from './CustomerAssignModal';
import {
  UserCheck,
  UserPlus,
  Edit,
  Trash2,
  Users,
  Briefcase,
  MapPin,
  Lock,
  AlertTriangle
} from 'lucide-react';

export default function EmployeeList() {
  const { employees, deleteEmployee } = useData();
  const { hasPermission } = useAuth();

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);

  const [isAssignOpen, setIsAssignOpen] = useState(false);
  const [assigningEmployee, setAssigningEmployee] = useState(null);

  const [deletingEmployee, setDeletingEmployee] = useState(null);

  const canAddEmployee = hasPermission(PERMISSIONS.ADD_EMPLOYEE); // ADMIN ONLY
  const canDeleteEmployee = hasPermission(PERMISSIONS.DELETE_EMPLOYEE); // ADMIN & MANAGER
  const canManageAssignments = hasPermission(PERMISSIONS.MANAGE_EMPLOYEES); // ADMIN & MANAGER

  const handleDeleteConfirm = () => {
    if (deletingEmployee) {
      deleteEmployee(deletingEmployee.id);
      setDeletingEmployee(null);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            Employee Directory & Customer Assignment <UserCheck className="w-5 h-5 text-cyan-400" />
          </h2>
          <p className="text-xs text-slate-400">
            Staff Directory & Account Allocations. Admin and Managers can delete employees.
          </p>
        </div>

        {/* ADMIN ONLY FOR ADDING EMPLOYEES */}
        {canAddEmployee && (
          <button
            onClick={() => {
              setEditingEmployee(null);
              setIsFormOpen(true);
            }}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white text-xs shadow-md shadow-cyan-500/20 hover:opacity-95 transition-all flex items-center gap-2 cursor-pointer self-start sm:self-auto"
          >
            <UserPlus className="w-4 h-4" /> Add New Employee
          </button>
        )}
      </div>

      {!canAddEmployee && (
        <div className="p-3.5 rounded-2xl bg-cyan-950/30 border border-cyan-800/40 text-cyan-300 text-xs flex items-center gap-2">
          <Lock className="w-4 h-4 text-amber-400 shrink-0" />
          <span>Note: Registration of new employee accounts is reserved exclusively for System Administrators.</span>
        </div>
      )}

      {/* Employee Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {employees.map((emp) => (
          <div
            key={emp.id}
            className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all shadow-xl space-y-4 flex flex-col justify-between"
          >
            <div className="space-y-3">
              
              {/* Profile Card Header */}
              <div className="flex items-start gap-3">
                <img src={emp.avatar} alt={emp.name} className="w-12 h-12 rounded-2xl object-cover border border-slate-700 shadow-md" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-slate-100 text-sm truncate">{emp.name}</h3>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                      emp.role === ROLES.ADMIN
                        ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                        : emp.role === ROLES.MANAGER
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                        : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
                    }`}>
                      {emp.role}
                    </span>
                  </div>
                  <span className="text-xs text-cyan-400 font-medium block truncate">{emp.roleTitle}</span>
                  <span className="text-[11px] text-slate-400 block font-mono">{emp.id}</span>
                </div>
              </div>

              {/* Specs Grid */}
              <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-700/50 text-xs space-y-1.5 text-slate-300">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Briefcase className="w-3.5 h-3.5 text-slate-500" /> Dept:
                  </span>
                  <span className="font-medium text-slate-200">{emp.department}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 text-slate-500" /> District:
                  </span>
                  <span className="font-medium text-slate-200">{emp.zone}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 flex items-center gap-1">
                    <Users className="w-3.5 h-3.5 text-slate-500" /> Assigned Accounts:
                  </span>
                  <span className="font-bold text-cyan-400">{emp.assignedCustomersCount} Customers</span>
                </div>
              </div>

            </div>

            {/* Actions */}
            {canManageAssignments && (
              <div className="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                <button
                  onClick={() => {
                    setAssigningEmployee(emp);
                    setIsAssignOpen(true);
                  }}
                  className="flex-1 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-400 text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                >
                  <Users className="w-3.5 h-3.5" /> Assign Customers
                </button>

                {canAddEmployee && (
                  <button
                    onClick={() => {
                      setEditingEmployee(emp);
                      setIsFormOpen(true);
                    }}
                    className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition-colors cursor-pointer"
                    title="Edit Employee Info"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                )}

                {/* DELETE EMPLOYEE BUTTON (FOR ADMIN & MANAGER) */}
                {canDeleteEmployee && (
                  <button
                    onClick={() => setDeletingEmployee(emp)}
                    className="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 transition-colors cursor-pointer"
                    title="Delete Employee (Admin/Manager)"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            )}

          </div>
        ))}
      </div>

      {/* Form Modal */}
      <EmployeeFormModal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        employeeToEdit={editingEmployee}
      />

      {/* Customer Assign Modal */}
      <CustomerAssignModal
        isOpen={isAssignOpen}
        onClose={() => setIsAssignOpen(false)}
        employee={assigningEmployee}
      />

      {/* Delete Confirmation Modal */}
      {deletingEmployee && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-base text-white">Delete Employee Account?</h3>
                <p className="text-xs text-slate-400">This action cannot be undone.</p>
              </div>
            </div>

            <p className="text-xs text-slate-300">
              Are you sure you want to remove <strong className="text-white">{deletingEmployee.name}</strong> ({deletingEmployee.roleTitle})? Any assigned customers will automatically revert to unassigned status.
            </p>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                onClick={() => setDeletingEmployee(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs font-semibold cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5"
              >
                <Trash2 className="w-4 h-4" /> Delete Employee
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
