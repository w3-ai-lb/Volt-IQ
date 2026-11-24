import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { crmApi, apiError } from '../crmApi';
import { formatCurrency, setCurrency } from '../utils/invoiceGenerator';

// CRM data, loaded from the VoltIQ backend.
//
// Stage 2 (fast lists): the context no longer downloads every full customer
// row. It keeps a SMALL row per customer for pickers (/crm/customers/options),
// the dashboard totals (/crm/summary) and the most recent 200 invoices and
// payments. The customer directory pages and searches on the server by itself
// (CustomerList.jsx). The 30-second refresh only reloads the cheap parts.
//
// Before unification this context read and wrote a separate Supabase project
// and kept copies in localStorage. Now the backend is the only source of
// truth: every change is sent to the API first and the lists are refreshed
// from its answer, so the web CRM, the field app and the analytics pages all
// see the same records.

const DataContext = createContext();

const DEFAULT_AVATAR =
  'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120';

const REFRESH_MS = 30000;
const RECENT = { limit: 200 };

const withAvatar = (emp) => ({ avatar: DEFAULT_AVATAR, ...emp });

export function DataProvider({ children }) {
  const [customers, setCustomers] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [payments, setPayments] = useState([]);
  const [tariff, setTariffState] = useState(null);
  const [summary, setSummary] = useState(null);
  // Bumped after every change, so screens that load their own data (the
  // paged customer directory) know to reload.
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [hasUnreadNotifications, setHasUnreadNotifications] = useState(false);
  const tariffTimer = useRef(null);

  const addNotification = useCallback((text, type = 'info') => {
    setNotifications((prev) => [{ id: Date.now() + Math.random(), text, type, time: 'Just now' }, ...prev.slice(0, 15)]);
    setHasUnreadNotifications(true);
  }, []);

  const markNotificationsAsRead = () => setHasUnreadNotifications(false);

  // The cheap, frequently changing parts: totals and the latest activity.
  const refreshActivity = useCallback(async () => {
    const [s, i, p] = await Promise.all([crmApi.summary(), crmApi.listInvoices(RECENT), crmApi.listPayments(RECENT)]);
    setSummary(s);
    setInvoices(i);
    setPayments(p);
  }, []);

  // Everything, after a change or on first load.
  const refresh = useCallback(async () => {
    try {
      const [options, e, t] = await Promise.all([
        crmApi.customerOptions(),
        crmApi.listEmployees(),
        crmApi.getTariff(),
        refreshActivity(),
      ]);
      setCurrency(t.currency);
      const staff = e.map(withAvatar);
      const nameOf = Object.fromEntries(staff.map((x) => [x.id, x.name]));
      setCustomers(options.map((c) => ({ ...c, assignedEmployeeName: nameOf[c.assignedEmployeeId] || 'Unassigned' })));
      setEmployees(staff);
      setTariffState(t);
      setVersion((v) => v + 1);
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load CRM data'));
    } finally {
      setLoading(false);
    }
  }, [refreshActivity]);

  useEffect(() => {
    refresh();
    // Picks up readings captured on the field app while this page is open.
    const timer = setInterval(() => refreshActivity().catch(() => {}), REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh, refreshActivity]);

  // Runs an API change, refreshes the lists, and reports the outcome.
  const mutate = async (fn, success) => {
    try {
      const result = await fn();
      await refresh();
      if (success) addNotification(typeof success === 'function' ? success(result) : success, 'success');
      return result;
    } catch (err) {
      addNotification(apiError(err), 'warning');
      return null;
    }
  };

  // Totals come from the server (/crm/summary), so they cover every record,
  // not just the rows loaded in the browser.
  const getDashboardStats = () => ({
    totalCustomers: summary?.totalCustomers ?? customers.length,
    totalRevenue: summary?.totalCollected ?? 0,
    outstandingPayments: summary?.outstanding ?? 0,
    totalKwhConsumed: summary?.kwhBilled ?? 0,
  });

  // Sets the tariff for invoices issued from now on. Debounced, because the
  // settings field calls it on every keystroke. Invoices already issued keep
  // the rate printed on them (a bill must not change after it was handed out).
  const recalculateOutstandingInvoices = (newKwhPrice) => {
    if (!newKwhPrice || newKwhPrice <= 0) return;
    clearTimeout(tariffTimer.current);
    tariffTimer.current = setTimeout(() => {
      mutate(() => crmApi.setTariff(newKwhPrice), `Tariff set to ${formatCurrency(newKwhPrice)} per kWh for new invoices.`);
    }, 800);
  };

  const addCustomer = (c) =>
    mutate(
      () =>
        crmApi.createCustomer({
          name: c.name,
          email: c.email || null,
          phone: c.phone,
          address: c.address,
          tariffType: c.tariffType,
          zone: c.zone,
          assignedEmployeeId: c.assignedEmployeeId || null,
          initialReading: parseFloat(c.initialReading) || 0,
          meterNo: c.meterNo || null,
          meterType: c.meterType,
          status: c.status || 'Active',
        }),
      (created) => `New customer "${created.name}" added.`
    );

  const updateCustomer = (id, f) =>
    mutate(
      () =>
        crmApi.updateCustomer(id, {
          name: f.name,
          email: f.email || undefined,
          phone: f.phone,
          address: f.address,
          tariffType: f.tariffType,
          zone: f.zone,
          assignedEmployeeId: f.assignedEmployeeId === undefined ? undefined : f.assignedEmployeeId || null,
          status: f.status,
          meterType: f.meterType,
        }),
      'Customer information updated.'
    );

  const deleteCustomer = (id) => {
    const cust = customers.find((c) => c.id === id);
    return mutate(() => crmApi.deleteCustomer(id), `Customer "${cust?.name || id}" removed.`);
  };

  const addEmployee = (e) =>
    mutate(
      () =>
        crmApi.createEmployee({
          name: e.name,
          email: e.email || null,
          password: e.password || null,
          phone: e.phone,
          role: e.role,
          roleTitle: e.roleTitle,
          department: e.department,
          zone: e.zone,
        }),
      (emp) => `Employee "${emp.name}" added${emp.canSignIn ? ' with sign-in access' : ''}.`
    );

  const updateEmployee = (id, f) =>
    mutate(
      () =>
        crmApi.updateEmployee(id, {
          name: f.name,
          phone: f.phone,
          role: f.role,
          department: f.department,
          zone: f.zone,
          status: f.status,
        }),
      'Employee profile updated.'
    );

  const deleteEmployee = (id) => {
    const emp = employees.find((e) => e.id === id);
    return mutate(() => crmApi.deleteEmployee(id), `Employee "${emp?.name || id}" deleted.`);
  };

  const assignCustomersToEmployee = (employeeId, customerIds) => {
    const emp = employees.find((e) => e.id === employeeId);
    return mutate(
      () => crmApi.assignCustomers(employeeId, customerIds),
      `Updated customer assignments for ${emp?.name || employeeId}.`
    );
  };

  // Office equivalent of a field reading: saves the reading and issues the invoice.
  const generateInvoiceFromReading = ({ customerId, previousReading, currentReading }) =>
    mutate(
      () => crmApi.recordReading({ customerId, previousReading, currentReading: Number(currentReading) }),
      (inv) => `Invoice ${inv.invoiceNumber} issued for ${inv.customerName} (${formatCurrency(inv.totalAmount)}).`
    );

  const recordPayment = ({ customerId, invoiceId, amount, paymentMethod = 'Cash', referenceNo = '', notes = '' }) =>
    mutate(
      () =>
        crmApi.recordPayment({
          customerId,
          invoiceId: invoiceId || null,
          amount: parseFloat(amount) || 0,
          paymentMethod,
          referenceNo,
          notes,
        }),
      (p) => `Payment of ${formatCurrency(p.amount)} recorded for ${p.customerName}. Receipt: ${p.receiptNo}`
    );

  return (
    <DataContext.Provider
      value={{
        customers,
        employees,
        invoices,
        payments,
        tariff,
        summary,
        version,
        loading,
        error,
        refresh,
        notifications,
        hasUnreadNotifications,
        markNotificationsAsRead,
        getDashboardStats,
        recalculateOutstandingInvoices,
        addCustomer,
        updateCustomer,
        deleteCustomer,
        addEmployee,
        updateEmployee,
        deleteEmployee,
        assignCustomersToEmployee,
        generateInvoiceFromReading,
        recordPayment,
        addNotification,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const context = useContext(DataContext);
  if (!context) throw new Error('useData must be used within a DataProvider');
  return context;
}
