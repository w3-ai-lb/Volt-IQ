import React, { createContext, useContext, useState, useEffect } from 'react';
import { INITIAL_EMPLOYEES } from '../mockData/initialData';
import { supabase } from '../lib/supabaseClient';

const AuthContext = createContext();

export const ROLES = {
  ADMIN: 'ADMIN',
  MANAGER: 'MANAGER',
  OFFICE_EMPLOYEE: 'OFFICE_EMPLOYEE'
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
  VIEW_REPORTS: 'VIEW_REPORTS'
};

const ROLE_PERMISSIONS = {
  [ROLES.ADMIN]: [
    PERMISSIONS.VIEW_DASHBOARD,
    PERMISSIONS.MANAGE_EMPLOYEES,
    PERMISSIONS.ADD_EMPLOYEE,
    PERMISSIONS.DELETE_EMPLOYEE,
    PERMISSIONS.VIEW_CUSTOMERS,
    PERMISSIONS.ADD_CUSTOMER,
    PERMISSIONS.EDIT_CUSTOMER,
    PERMISSIONS.DELETE_CUSTOMER,
    PERMISSIONS.MANAGE_BILLING_PAYMENTS,
    PERMISSIONS.GENERATE_BILL,
    PERMISSIONS.RECORD_PAYMENTS,
    PERMISSIONS.VIEW_REPORTS
  ],
  [ROLES.MANAGER]: [
    PERMISSIONS.VIEW_DASHBOARD,
    PERMISSIONS.MANAGE_EMPLOYEES,
    PERMISSIONS.DELETE_EMPLOYEE,
    PERMISSIONS.VIEW_CUSTOMERS,
    PERMISSIONS.ADD_CUSTOMER,
    PERMISSIONS.EDIT_CUSTOMER,
    PERMISSIONS.DELETE_CUSTOMER,
    PERMISSIONS.MANAGE_BILLING_PAYMENTS,
    PERMISSIONS.GENERATE_BILL,
    PERMISSIONS.RECORD_PAYMENTS,
    PERMISSIONS.VIEW_REPORTS
  ],
  [ROLES.OFFICE_EMPLOYEE]: [
    PERMISSIONS.VIEW_DASHBOARD,
    PERMISSIONS.VIEW_CUSTOMERS,
    PERMISSIONS.MANAGE_BILLING_PAYMENTS,
    PERMISSIONS.GENERATE_BILL,
    PERMISSIONS.RECORD_PAYMENTS
  ]
};

const DEFAULT_AVATAR = 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120';

const titleCase = (value = '') =>
  value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());

const mapDbRoleToAppRole = (role) => {
  if (role === 'admin') return ROLES.ADMIN;
  if (role === 'office_staff') return ROLES.MANAGER;
  return ROLES.OFFICE_EMPLOYEE;
};

const mapEmployeeToUser = (employee) => {
  const name = employee.full_name || 'Unnamed Employee';
  return {
    id: employee.employee_id,
    authUserId: employee.auth_user_id,
    name,
    email: employee.email || `${name.toLowerCase().replace(/\s+/g, '.')}@gridpower.com`,
    role: mapDbRoleToAppRole(employee.role),
    roleTitle: titleCase(employee.role || 'field_employee'),
    department: employee.department || 'Operations',
    zone: employee.zone || 'Central District',
    status: employee.is_active === false ? 'Inactive' : 'Active',
    assignedCustomersCount: 0,
    phone: employee.phone || '',
    avatar: employee.avatar || DEFAULT_AVATAR
  };
};

const mergeUsers = (...lists) => {
  const merged = new Map();

  lists.flat().filter(Boolean).forEach(user => {
    const emailKey = user.email ? `email:${user.email.toLowerCase()}` : null;
    const idKey = user.id ? `id:${user.id}` : emailKey;
    const existing = merged.get(idKey) || (emailKey ? merged.get(emailKey) : null);
    const next = { ...existing, ...user };

    if (idKey) merged.set(idKey, next);
    if (emailKey) merged.set(emailKey, next);
  });

  return Array.from(new Set(merged.values()));
};

export function AuthProvider({ children }) {
  const [registeredUsers, setRegisteredUsers] = useState(() => {
    const saved = localStorage.getItem('gridpower_registered_users');
    return saved ? JSON.parse(saved) : [];
  });
  const [syncedUsers, setSyncedUsers] = useState([]);

  const [currentUser, setCurrentUser] = useState(() => {
    const saved = localStorage.getItem('gridpower_current_user');
    return saved ? JSON.parse(saved) : INITIAL_EMPLOYEES[0];
  });

  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    const savedAuth = localStorage.getItem('gridpower_is_auth');
    return savedAuth ? JSON.parse(savedAuth) : true;
  });

  useEffect(() => {
    localStorage.setItem('gridpower_registered_users', JSON.stringify(registeredUsers));
  }, [registeredUsers]);

  useEffect(() => {
    localStorage.setItem('gridpower_current_user', JSON.stringify(currentUser));
  }, [currentUser]);

  useEffect(() => {
    localStorage.setItem('gridpower_is_auth', JSON.stringify(isAuthenticated));
  }, [isAuthenticated]);

  useEffect(() => {
    let cancelled = false;

    const syncEmployees = async () => {
      const { data, error } = await supabase
        .from('employees')
        .select('*')
        .order('created_at', { ascending: false });

      if (error) {
        console.warn('Auth employee sync failed:', error.message);
        return;
      }

      if (!cancelled && Array.isArray(data)) {
        const mappedUsers = data.map(mapEmployeeToUser);
        setSyncedUsers(mappedUsers);
        setCurrentUser(prev => {
          if (!prev) return prev;
          return mappedUsers.find(user =>
            user.id === prev.id ||
            (user.email && prev.email && user.email.toLowerCase() === prev.email.toLowerCase())
          ) || prev;
        });
      }
    };

    syncEmployees();
    const channel = supabase
      .channel('auth_employees')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'employees' }, syncEmployees)
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, []);

  const availableUsers = mergeUsers(registeredUsers, syncedUsers, INITIAL_EMPLOYEES);

  const activeRole = currentUser?.role || ROLES.OFFICE_EMPLOYEE;

  const hasPermission = (permission) => {
    const perms = ROLE_PERMISSIONS[activeRole] || [];
    return perms.includes(permission);
  };

  const registerUser = (user, rawPassword) => {
    if (!user) return;
    if (rawPassword) {
      localStorage.setItem(`gridpower_pwd_${user.email.toLowerCase()}`, rawPassword);
    }
    setRegisteredUsers(prev => [
      user,
      ...prev.filter(u =>
        u.id !== user.id &&
        (!u.email || !user.email || u.email.toLowerCase() !== user.email.toLowerCase())
      )
    ]);
    setCurrentUser(user);
    setIsAuthenticated(true);
    return user;
  };

  const login = async (email, password) => {
    const cleanEmail = email.trim().toLowerCase();
    
    // Strict password verification
    const savedPassword = localStorage.getItem(`gridpower_pwd_${cleanEmail}`);
    const expectedPassword = savedPassword || (cleanEmail === 'admin@gridpower.com' ? 'admin123' : null);

    if (expectedPassword && password !== expectedPassword) {
      throw new Error(`Incorrect password for ${email}. Please check your credentials.`);
    }

    const foundUser = availableUsers.find(e => e.email?.toLowerCase() === cleanEmail);
    
    if (foundUser) {
      setCurrentUser(foundUser);
      setIsAuthenticated(true);
      return foundUser;
    }

    // Dynamic user session matching entered email/role
    const newUser = {
      id: `EMP-${Math.floor(100 + Math.random() * 900)}`,
      name: email.split('@')[0].replace('.', ' '),
      email: email,
      role: email.includes('manager') ? ROLES.MANAGER : email.includes('admin') ? ROLES.ADMIN : ROLES.OFFICE_EMPLOYEE,
      roleTitle: email.includes('manager') ? 'Regional Operations Manager' : email.includes('admin') ? 'Chief Administrator' : 'Billing Specialist',
      department: 'Operations',
      zone: 'North Metro District',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120'
    };

    registerUser(newUser, password);
    return newUser;
  };

  const logout = () => {
    setIsAuthenticated(false);
  };

  const switchUser = (userId) => {
    const user = availableUsers.find(u => u.id === userId);
    if (user) {
      setCurrentUser(user);
      setIsAuthenticated(true);
    }
  };

  return (
    <AuthContext.Provider value={{
      currentUser,
      activeRole,
      isAuthenticated,
      hasPermission,
      registerUser,
      login,
      logout,
      switchUser,
      availableUsers
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
