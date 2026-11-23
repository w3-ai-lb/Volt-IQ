import React, { useState } from 'react';
import { useAuth, ROLES } from '../../context/AuthContext';
import { useData } from '../../context/DataContext';
import { Zap, Mail, KeyRound, ArrowRight, ShieldCheck, Eye, EyeOff, Lock, CheckCircle2, AlertCircle, X, UserPlus, UserCheck } from 'lucide-react';

export default function LoginPage() {
  const { login, registerUser, switchUser, availableUsers } = useAuth();
  const { employees, addEmployee } = useData();

  const [email, setEmail] = useState('admin@gridpower.com');
  const [password, setPassword] = useState('admin123');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Change Password Modal State
  const [isChangeModalOpen, setIsChangeModalOpen] = useState(false);
  const [changeEmail, setChangeEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeSuccess, setChangeSuccess] = useState('');
  const [changeError, setChangeError] = useState('');

  // Create Account Modal State
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [regData, setRegData] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    role: ROLES.OFFICE_EMPLOYEE,
    roleTitle: 'Billing Specialist',
    department: 'Customer Relations',
    zone: 'North Metro District'
  });
  const [regSuccess, setRegSuccess] = useState('');
  const [regError, setRegError] = useState('');

  // Single Source of Truth for Staff Accounts (Synced across DataContext employees & AuthContext)
  const allStaffUsers = React.useMemo(() => {
    const map = new Map();
    (employees || []).forEach(e => {
      const userEmail = e.email || `${e.name.toLowerCase().replace(/\s+/g, '.')}@gridpower.com`;
      map.set(userEmail.toLowerCase(), {
        id: e.id,
        name: e.name,
        email: userEmail,
        role: e.role || 'OFFICE_EMPLOYEE',
        roleTitle: e.roleTitle || e.role,
        avatar: e.avatar || `https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120`
      });
    });

    (availableUsers || []).forEach(u => {
      const uEmail = u.email ? u.email.toLowerCase() : '';
      if (uEmail && !map.has(uEmail)) {
        map.set(uEmail, {
          id: u.id,
          name: u.name,
          email: u.email,
          role: u.role || 'OFFICE_EMPLOYEE',
          roleTitle: u.roleTitle || u.role,
          avatar: u.avatar || `https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120`
        });
      }
    });

    return Array.from(map.values());
  }, [availableUsers, employees]);

  const handleSelectStaffUser = (selectedEmail) => {
    const found = allStaffUsers.find(u => u.email.toLowerCase() === selectedEmail.toLowerCase());
    if (found) {
      setEmail(found.email);
      const savedPwd = localStorage.getItem(`gridpower_pwd_${found.email.toLowerCase()}`);
      setPassword(savedPwd || (found.email === 'admin@gridpower.com' ? 'admin123' : '••••••••'));
      switchUser(found.id);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');
    try {
      await login(email, password);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to authenticate');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePasswordSubmit = (e) => {
    e.preventDefault();
    setChangeSuccess('');
    setChangeError('');

    if (newPassword !== confirmPassword) {
      setChangeError('New passwords do not match!');
      return;
    }
    if (newPassword.length < 6) {
      setChangeError('Password must be at least 6 characters long.');
      return;
    }

    localStorage.setItem(`gridpower_pwd_${changeEmail.toLowerCase()}`, newPassword);
    setChangeSuccess('Password updated successfully! You can now sign in with your new password.');
    setTimeout(() => {
      setIsChangeModalOpen(false);
      setPassword(newPassword);
      setEmail(changeEmail);
      setChangeSuccess('');
    }, 2000);
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setRegSuccess('');
    setRegError('');

    if (!regData.name || !regData.email || !regData.password) {
      setRegError('Please fill in all required fields.');
      return;
    }
    if (regData.password.length < 6) {
      setRegError('Password must be at least 6 characters long.');
      return;
    }

    try {
      // 1. Add directly as an Employee into DataContext (shows in Employee Management) & Supabase
      const created = await addEmployee({
        name: regData.name,
        email: regData.email,
        phone: regData.phone,
        role: regData.role,
        roleTitle: regData.roleTitle || (regData.role === ROLES.MANAGER ? 'Regional Operations Manager' : 'Billing Specialist'),
        department: regData.department,
        zone: regData.zone
      });

      // 2. Store password for this account
      localStorage.setItem(`gridpower_pwd_${regData.email.toLowerCase()}`, regData.password);

      // 3. Register user session in AuthContext & log in
      const userAccount = {
        ...created,
        id: created?.id || `EMP-${Date.now()}`,
        name: regData.name,
        email: regData.email,
        role: regData.role,
        roleTitle: regData.roleTitle || (regData.role === ROLES.MANAGER ? 'Regional Operations Manager' : 'Billing Specialist')
      };

      setRegSuccess(`Account for ${regData.name} created and linked to Employee Management! Opening portal...`);

      setTimeout(() => {
        setIsRegisterModalOpen(false);
        setRegSuccess('');
        registerUser(userAccount, regData.password);
      }, 1500);

    } catch (err) {
      setRegError('Failed to create account: ' + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] flex items-center justify-center p-4 relative overflow-hidden font-sans">
      
      {/* Background Lighting Gradients */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-cyan-500/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-80 h-80 bg-blue-600/10 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative w-full max-w-md bg-slate-900/90 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden p-8 space-y-6">
        
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center shadow-lg shadow-cyan-500/30 mx-auto">
            <Zap className="w-8 h-8 text-white animate-pulse" />
          </div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">GridPower CRM</h1>
          <p className="text-xs text-slate-400">Electricity Utility Office Portal</p>
        </div>

        {/* Supabase Sync Banner */}
        <div className="p-3.5 rounded-2xl bg-cyan-950/40 border border-cyan-800/40 text-xs text-cyan-300 flex items-start gap-2.5">
          <ShieldCheck className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold block text-cyan-200">Supabase Database Sync</span>
            <span className="text-[11px] text-cyan-400/80">
              Live sync active across Web Admin, Mobile App, and Supabase backend.
            </span>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-semibold">
            {errorMsg}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          
          <div>
            <label className="block font-semibold text-slate-300 mb-1.5">Corporate Email Address</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              <input
                type="email"
                required
                placeholder="admin@gridpower.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="font-semibold text-slate-300">Password</label>
              <button
                type="button"
                onClick={() => {
                  setChangeEmail(email);
                  setChangeError('');
                  setChangeSuccess('');
                  setIsChangeModalOpen(true);
                }}
                className="text-cyan-400 hover:underline text-[11px] font-medium"
              >
                Change Password?
              </button>
            </div>

            {/* Password Input with Show / Hide Eye Icon Option */}
            <div className="relative">
              <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                placeholder="Password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200 transition-colors p-0.5 cursor-pointer"
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white shadow-lg shadow-cyan-500/25 hover:opacity-95 transition-all flex items-center justify-center gap-2 cursor-pointer text-sm"
          >
            <span>Sign In to Office Portal</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* Quick Switch Staff Selector */}
        {allStaffUsers && allStaffUsers.length > 0 && (
          <div className="border-t border-slate-800/80 pt-4 space-y-2">
            <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <span>Quick Staff Account Switch</span>
              <span className="text-cyan-400 font-mono">({allStaffUsers.length})</span>
            </div>

            <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
              {allStaffUsers.map((user) => (
                <button
                  key={user.id || user.email}
                  type="button"
                  onClick={() => handleSelectStaffUser(user.email)}
                  className={`w-full flex items-center gap-3 p-2 rounded-xl border text-left transition-all cursor-pointer ${
                    email.toLowerCase() === user.email.toLowerCase()
                      ? 'bg-cyan-950/40 border-cyan-500/50 shadow-sm shadow-cyan-500/10'
                      : 'bg-slate-800/40 hover:bg-slate-800 border-slate-700/60'
                  }`}
                >
                  <img src={user.avatar} className="w-7 h-7 rounded-lg object-cover" alt="" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200 truncate">{user.name}</span>
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                        {user.role}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 block truncate">{user.email}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Create Employee / Manager Account Link */}
        <div className="text-center border-t border-slate-800/80 pt-4">
          <p className="text-xs text-slate-400 mb-2">Need a new staff account?</p>
          <button
            type="button"
            onClick={() => {
              setRegError('');
              setRegSuccess('');
              setIsRegisterModalOpen(true);
            }}
            className="w-full py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-cyan-500/30 text-cyan-400 font-semibold transition-all flex items-center justify-center gap-2 text-xs cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            <span>Create Account (Employee / Manager)</span>
          </button>
        </div>

      </div>

      {/* Create Account Modal (Employee / Manager) */}
      {isRegisterModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in overflow-y-auto">
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-4 my-8">
            
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5 text-cyan-400">
                <UserCheck className="w-5 h-5" />
                <h3 className="font-bold text-base text-white">Create Staff Account</h3>
              </div>
              <button
                onClick={() => setIsRegisterModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {regSuccess && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{regSuccess}</span>
              </div>
            )}

            {regError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{regError}</span>
              </div>
            )}

            <form onSubmit={handleRegisterSubmit} className="space-y-3 text-xs">
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Full Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. John Miller"
                    value={regData.name}
                    onChange={e => setRegData({ ...regData, name: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Corporate Email *</label>
                  <input
                    type="email"
                    required
                    placeholder="j.miller@gridpower.com"
                    value={regData.email}
                    onChange={e => setRegData({ ...regData, email: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Password *</label>
                  <input
                    type="password"
                    required
                    placeholder="Min 6 characters"
                    value={regData.password}
                    onChange={e => setRegData({ ...regData, password: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Account Role *</label>
                  <select
                    value={regData.role}
                    onChange={e => setRegData({ ...regData, role: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value={ROLES.OFFICE_EMPLOYEE}>Office Employee (Billing & Payments)</option>
                    <option value={ROLES.MANAGER}>Manager (Staff & Reports)</option>
                    <option value={ROLES.ADMIN}>Administrator (Full Access)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Job Title</label>
                  <input
                    type="text"
                    placeholder="Regional Manager / Meter Officer"
                    value={regData.roleTitle}
                    onChange={e => setRegData({ ...regData, roleTitle: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Phone Number</label>
                  <input
                    type="text"
                    placeholder="+1 (555) 000-0000"
                    value={regData.phone}
                    onChange={e => setRegData({ ...regData, phone: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Department</label>
                  <select
                    value={regData.department}
                    onChange={e => setRegData({ ...regData, department: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="Customer Relations">Customer Relations</option>
                    <option value="Finance & Billing">Finance & Billing</option>
                    <option value="Operations & IT">Operations & IT</option>
                    <option value="Field Audit & Services">Field Audit & Services</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-300 mb-1">Assigned Zone</label>
                  <input
                    type="text"
                    placeholder="North Metro District"
                    value={regData.zone}
                    onChange={e => setRegData({ ...regData, zone: e.target.value })}
                    className="w-full px-3.5 py-2 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsRegisterModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs font-semibold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-95 text-white text-xs font-bold shadow-md cursor-pointer flex items-center gap-1.5"
                >
                  <UserPlus className="w-4 h-4" />
                  <span>Create Account & Open Portal</span>
                </button>
              </div>
            </form>

          </div>
        </div>
      )}

      {/* Change Password Modal */}
      {isChangeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-4">
            
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5 text-cyan-400">
                <Lock className="w-5 h-5" />
                <h3 className="font-bold text-base text-white">Change Account Password</h3>
              </div>
              <button
                onClick={() => setIsChangeModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {changeSuccess && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{changeSuccess}</span>
              </div>
            )}

            {changeError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{changeError}</span>
              </div>
            )}

            <form onSubmit={handleChangePasswordSubmit} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-semibold text-slate-300 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={changeEmail}
                  onChange={e => setChangeEmail(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-300 mb-1">New Password</label>
                <input
                  type="password"
                  required
                  placeholder="Enter new password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-300 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  required
                  placeholder="Confirm new password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsChangeModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs font-semibold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-95 text-white text-xs font-bold shadow-md cursor-pointer"
                >
                  Update Password
                </button>
              </div>
            </form>

          </div>
        </div>
      )}

    </div>
  );
}
