import React, { createContext, useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth as useAppAuth } from '@/context/AuthContext';
import { crmApi } from '../crmApi';

// CRM permissions on top of the platform's single sign-in.
//
// Before unification the CRM had its own login page, kept staff passwords in
// the browser's localStorage and let anyone "switch user" from a dropdown.
// All of that is gone: staff sign in once on the platform's /login page, the
// backend decides their role, and this file only translates that role into
// the CRM's permission names. The server enforces the same rules again on
// every /crm request, so hiding a button here is a convenience, not security.

const AuthContext = createContext();

export const ROLES = {
  ADMIN: 'ADMIN',
  MANAGER: 'MANAGER',
  OFFICE_EMPLOYEE: 'OFFICE_EMPLOYEE',
};

export const PERMISSIONS = {
  VIEW_DASHBOARD: 'VIEW_DASHBOARD',
  MANAGE_EMPLOYEES: 'MANAGE_EMPLOYEES',
  ADD_EMPLOYEE: 'ADD_EMPLOYEE',
  DELETE_EMPLOYEE: 'DELETE_EMPLOYEE',
  VIEW_CUSTOMERS: 'VIEW_CUSTOMERS',
  ADD_CUSTOMER: 'ADD_CUSTOMER',
  EDIT_CUSTOMER: 'EDIT_CUSTOMER',
  DELETE_CUSTOMER: 'DELETE_CUSTOMER',
  MANAGE_BILLING_PAYMENTS: 'MANAGE_BILLING_PAYMENTS',
  GENERATE_BILL: 'GENERATE_BILL',
  RECORD_PAYMENTS: 'RECORD_PAYMENTS',
  VIEW_REPORTS: 'VIEW_REPORTS',
};

const ALL = Object.values(PERMISSIONS);

const ROLE_PERMISSIONS = {
  [ROLES.ADMIN]: ALL,
  [ROLES.MANAGER]: ALL,
  [ROLES.OFFICE_EMPLOYEE]: [
    PERMISSIONS.VIEW_DASHBOARD,
    PERMISSIONS.VIEW_CUSTOMERS,
    PERMISSIONS.MANAGE_BILLING_PAYMENTS,
    PERMISSIONS.GENERATE_BILL,
    PERMISSIONS.RECORD_PAYMENTS,
  ],
};

const ROLE_FROM_ACCOUNT = { admin: ROLES.ADMIN, staff: ROLES.MANAGER, field: ROLES.OFFICE_EMPLOYEE };

const DEFAULT_AVATAR =
  'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120';

export function AuthProvider({ children }) {
  const { user, logout: appLogout } = useAppAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    let alive = true;
    crmApi
      .me()
      .then((me) => alive && setProfile(me))
      .catch(() => alive && setProfile(null));
    return () => {
      alive = false;
    };
  }, [user?.id]);

  const activeRole = profile?.role || ROLE_FROM_ACCOUNT[user?.role] || ROLES.OFFICE_EMPLOYEE;

  const currentUser = {
    id: profile?.id || user?.id,
    name: profile?.name || user?.name || '',
    email: profile?.email || user?.email || '',
    role: activeRole,
    roleTitle: profile?.roleTitle || '',
    accountRole: profile?.accountRole || user?.role,
    zone: profile?.zone,
    avatar: DEFAULT_AVATAR,
  };

  const hasPermission = (permission) => (ROLE_PERMISSIONS[activeRole] || []).includes(permission);

  const logout = () => {
    appLogout();
    navigate('/login', { replace: true });
  };

  return (
    <AuthContext.Provider value={{ currentUser, activeRole, hasPermission, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
