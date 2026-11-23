import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  INITIAL_CUSTOMERS,
  INITIAL_EMPLOYEES,
  INITIAL_INVOICES,
  INITIAL_PAYMENTS
} from '../mockData/initialData';
import { calculateBillDetails } from '../utils/invoiceGenerator';
import { supabase } from '../lib/supabaseClient';

const DataContext = createContext();

const parseReadingMetadata = (row) => {
  const raw = row?.photo_url || row?.photoUrl || '';
  if (typeof raw !== 'string') return {};
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return {};
  try {
    return JSON.parse(trimmed);
  } catch (err) {
    console.log('Unable to parse meter reading metadata:', err);
    return {};
  }
};

const toNumber = (value, fallback = 0) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : fallback;
  const parsed = parseFloat(String(value ?? '').replace(/[^0-9.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : fallback;
};

const formatDate = (value) => {
  if (!value) return new Date().toISOString().split('T')[0];
  return String(value).includes('T') ? String(value).split('T')[0] : String(value).split(' ')[0];
};

const mapReadingToInvoice = (row, customerLookup = {}, allCustomers = []) => {
  const meta = parseReadingMetadata(row);
  const readingId = row.reading_id || meta.reading_id || `READ-${Date.now()}`;
  let customerId = meta.subscriber_id || row.subscriber_id || '';
  let customer = customerLookup[customerId] || {};

  if (!customer.id && meta.customer_name) {
    const match = allCustomers.find(c => c.name.toLowerCase() === meta.customer_name.toLowerCase());
    if (match) {
      customer = match;
      customerId = match.id;
    }
  }

  if (!customer.id && allCustomers.length > 0) {
    customer = allCustomers[0];
    customerId = customer.id;
  }

  const currentReading = toNumber(row.reading_value ?? meta.current_reading ?? meta.reading_value);
  const previousReading = toNumber(meta.previous_reading);
  const kwhConsumed = toNumber(meta.kwh ?? meta.consumption, Math.max(0, currentReading - previousReading));
  const totalAmount = Math.round(toNumber(meta.total_amount ?? meta.cost, (kwhConsumed * 0.15) + 5) * 100) / 100;
  const paidAmount = meta.is_paid === true || meta.isPaid === true ? totalAmount : 0;
  const issueDate = formatDate(row.reading_date || meta.date);
  const due = new Date(issueDate);
  if (!Number.isNaN(due.getTime())) {
    due.setDate(due.getDate() + 15);
  }

  return {
    id: readingId,
    readingId,
    invoiceNumber: meta.invoice_number || `PWR-2026-${String(readingId).slice(-5)}`,
    customerId: customerId || customer.id || 'CUST-1',
    customerName: customer.name || meta.customer_name || 'Customer Account',
    accountNo: customer.accountNo || (customerId ? `ACC-${String(customerId).slice(0, 5)}` : 'ACC-10001'),
    meterNo: meta.meter_number || customer.meterNo || 'MTR-10001',
    billingPeriod: issueDate,
    issueDate,
    dueDate: Number.isNaN(due.getTime()) ? issueDate : due.toISOString().split('T')[0],
    previousReading,
    currentReading,
    kwhConsumed,
    tariffType: customer.tariffType || 'Residential',
    baseCharge: 5,
    consumptionCharge: Math.max(0, totalAmount - 5),
    taxAmount: 0,
    totalAmount,
    paidAmount,
    status: paidAmount >= totalAmount ? 'Paid' : 'Unpaid',
    recordedBy: meta.captured_by_name || row.captured_by || 'Field Employee',
    source: 'meter_readings',
    rawReading: row
  };
};

const mapPaidInvoiceToPayment = (invoice) => ({
  id: `PAY-${invoice.id}`,
  receiptNo: `RCP-${invoice.invoiceNumber}`,
  customerId: invoice.customerId,
  customerName: invoice.customerName,
  invoiceId: invoice.id,
  invoiceNumber: invoice.invoiceNumber,
  amount: invoice.totalAmount,
  paymentMethod: 'Office Payment',
  paymentDate: invoice.issueDate,
  referenceNo: invoice.readingId,
  recordedBy: invoice.recordedBy,
  notes: 'Payment status synced from meter reading record'
});

export function DataProvider({ children }) {
  const [customers, setCustomers] = useState(() => {
    localStorage.removeItem('gridpower_customers');
    return [];
  });

  const [employees, setEmployees] = useState(() => {
    const saved = localStorage.getItem('gridpower_employees');
    return saved ? JSON.parse(saved) : INITIAL_EMPLOYEES;
  });

  const [invoices, setInvoices] = useState(() => {
    localStorage.removeItem('gridpower_invoices');
    return [];
  });

  const [payments, setPayments] = useState(() => {
    localStorage.removeItem('gridpower_payments');
    return [];
  });

  const [notifications, setNotifications] = useState([
    { id: 1, text: 'Payment of $380.82 recorded for Green Leaf Market', type: 'success', time: '1h ago' }
  ]);

  const [hasUnreadNotifications, setHasUnreadNotifications] = useState(true);

  const markNotificationsAsRead = () => {
    setHasUnreadNotifications(false);
  };

  // Sync with Supabase Schema on Initial Load & Live Realtime Updates
  useEffect(() => {
    const syncSupabase = async () => {
      try {
        // 1. Fetch Employees
        const { data: empData, error: empErr } = await supabase.from('employees').select('*');
        let currentEmployees = INITIAL_EMPLOYEES;
        if (!empErr && empData && empData.length > 0) {
          currentEmployees = empData.map(e => ({
            id: e.employee_id,
            authUserId: e.auth_user_id,
            name: e.full_name,
            email: `${e.full_name.toLowerCase().replace(/\s+/g, '.')}@gridpower.com`,
            role: e.role === 'admin' ? 'ADMIN' : e.role === 'office_staff' ? 'MANAGER' : 'OFFICE_EMPLOYEE',
            roleTitle: e.role.toUpperCase(),
            department: 'Operations',
            zone: 'Central District',
            assignedCustomersCount: 0,
            status: e.is_active ? 'Active' : 'Inactive',
            avatar: `https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120`,
            phone: e.phone || ''
          }));
          setEmployees(currentEmployees);
        } else if (!empErr && (!empData || empData.length === 0)) {
          setEmployees(INITIAL_EMPLOYEES);
          localStorage.removeItem('gridpower_employees');
        }

        // 2. Fetch Assignments from Supabase
        const { data: assignData } = await supabase.from('employee_subscriber_assignments').select('*');
        const assignmentMap = {};
        if (assignData && assignData.length > 0) {
          assignData.forEach(a => {
            if (a.is_active) {
              assignmentMap[a.subscriber_id] = a.employee_id;
            }
          });
        }

        // 3. Fetch Subscribers / Customers
        const { data: subData, error: subErr } = await supabase.from('subscribers').select('*');
        let syncedCustomers = [];
        if (!subErr) {
          if (subData && subData.length > 0) {
            const mappedSubscribers = subData.map(s => {
              const assignedEmpId = assignmentMap[s.subscriber_id] || null;
              const assignedEmp = currentEmployees.find(e => e.id === assignedEmpId);
              return {
                id: s.subscriber_id,
                accountNo: `ACC-${s.subscriber_id.slice(0, 5)}`,
                meterNo: `MTR-${s.subscriber_id.slice(0, 6)}`,
                name: s.full_name,
                phone: s.phone || '',
                address: s.address || '',
                tariffType: 'Residential',
                assignedEmployeeId: assignedEmpId,
                assignedEmployeeName: assignedEmp ? assignedEmp.name : 'Unassigned',
                previousReading: 0.0,
                currentReading: 0.0,
                lastReadingDate: s.created_at ? s.created_at.split('T')[0] : '2026-08-01',
                status: s.is_active ? 'Active' : 'Suspended',
                balance: 0.00,
                outstandingStatus: 'Paid',
                meterType: 'Digital Smart Meter',
                zone: 'North Metro District'
              };
            });
            syncedCustomers = mappedSubscribers;

            // Update employee customer counts
            if (currentEmployees.length > 0) {
              setEmployees(prev => prev.map(emp => ({
                ...emp,
                assignedCustomersCount: mappedSubscribers.filter(c => c.assignedEmployeeId === emp.id).length
              })));
            }
          } else {
            localStorage.removeItem('gridpower_customers');
          }
        }

        // 4. Fetch Mobile App Meter Readings and expose them as web invoices.
        const customerLookup = Object.fromEntries(syncedCustomers.map(c => [c.id, c]));
        const { data: readingData, error: readingErr } = await supabase
          .from('meter_readings')
          .select('*')
          .order('reading_date', { ascending: false });

        const syncedInvoices = !readingErr && readingData
          ? readingData.map(row => mapReadingToInvoice(row, customerLookup, syncedCustomers))
          : [];
        const syncedPayments = syncedInvoices.filter(inv => inv.status === 'Paid').map(mapPaidInvoiceToPayment);

        setInvoices(syncedInvoices);
        setPayments(syncedPayments);

        const invoicesByCustomer = syncedInvoices.reduce((acc, inv) => {
          if (!acc[inv.customerId]) acc[inv.customerId] = [];
          acc[inv.customerId].push(inv);
          return acc;
        }, {});

        setCustomers(syncedCustomers.map(cust => {
          const customerInvoices = invoicesByCustomer[cust.id] || [];
          const latestInvoice = customerInvoices[0];
          const balance = customerInvoices
            .filter(inv => inv.status !== 'Paid')
            .reduce((sum, inv) => sum + Math.max(0, inv.totalAmount - inv.paidAmount), 0);

          return {
            ...cust,
            previousReading: latestInvoice?.previousReading ?? cust.previousReading,
            currentReading: latestInvoice?.currentReading ?? cust.currentReading,
            lastReadingDate: latestInvoice?.issueDate ?? cust.lastReadingDate,
            balance: Math.round(balance * 100) / 100,
            outstandingStatus: balance > 0 ? 'Unpaid' : 'Paid'
          };
        }));

      } catch (err) {
        console.log('Supabase schema sync notice:', err);
      }
    };

    syncSupabase();

    // Live Real-Time Subscriptions for Bi-directional Sync with Mobile App
    const channel = supabase
      .channel('crm_realtime_channel')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'subscribers' }, () => syncSupabase())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'employees' }, () => syncSupabase())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'employee_subscriber_assignments' }, () => syncSupabase())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'meter_readings' }, () => syncSupabase())
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem('gridpower_customers', JSON.stringify(customers));
  }, [customers]);

  useEffect(() => {
    localStorage.setItem('gridpower_employees', JSON.stringify(employees));
  }, [employees]);

  useEffect(() => {
    localStorage.setItem('gridpower_invoices', JSON.stringify(invoices));
  }, [invoices]);

  useEffect(() => {
    localStorage.setItem('gridpower_payments', JSON.stringify(payments));
  }, [payments]);

  const getDashboardStats = () => {
    const totalCustomers = customers.length;
    const totalRevenue = payments.reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0);
    const outstandingPayments = invoices
      .filter(inv => inv.status === 'Unpaid' || inv.status === 'Overdue' || inv.status === 'Partial')
      .reduce((sum, inv) => sum + ((parseFloat(inv.totalAmount) || 0) - (parseFloat(inv.paidAmount) || 0)), 0);
    const totalKwhConsumed = invoices.reduce((sum, inv) => sum + (parseFloat(inv.kwhConsumed) || 0), 0);

    return {
      totalCustomers,
      totalRevenue: Math.round(totalRevenue * 100) / 100,
      outstandingPayments: Math.round(outstandingPayments * 100) / 100,
      totalKwhConsumed: Math.round(totalKwhConsumed * 10) / 10
    };
  };

  const recalculateOutstandingInvoices = (newKwhPrice) => {
    if (!newKwhPrice || newKwhPrice <= 0) return;

    setInvoices(prevInvoices => {
      const nextInvoices = prevInvoices.map(inv => {
        if (inv.status === 'Paid') {
          return inv;
        }

        const updatedBill = calculateBillDetails(inv.kwhConsumed, inv.tariffType, newKwhPrice);
        return {
          ...inv,
          consumptionCharge: updatedBill.consumptionCharge,
          taxAmount: updatedBill.taxAmount,
          totalAmount: updatedBill.totalAmount
        };
      });

      setCustomers(prevCustomers => {
        return prevCustomers.map(cust => {
          const custUnpaidInvoices = nextInvoices.filter(
            i => i.customerId === cust.id && i.status !== 'Paid'
          );

          const newBalance = custUnpaidInvoices.reduce(
            (sum, inv) => sum + ((parseFloat(inv.totalAmount) || 0) - (parseFloat(inv.paidAmount) || 0)),
            0
          );

          const roundedBalance = Math.round(newBalance * 100) / 100;
          return {
            ...cust,
            balance: roundedBalance,
            outstandingStatus: roundedBalance === 0 ? 'Paid' : 'Unpaid'
          };
        });
      });

      return nextInvoices;
    });
  };

  const addCustomer = async (customerData) => {
    let createdId = `CUST-${Math.floor(8000 + Math.random() * 1000)}`;

    try {
      const { data: inserted, error } = await supabase.from('subscribers').insert([{
        full_name: customerData.name,
        phone: customerData.phone || '',
        address: customerData.address || '',
        is_active: true
      }]).select('*');

      if (!error && inserted && inserted.length > 0) {
        createdId = inserted[0].subscriber_id;

        // Persist initial assignment to employee_subscriber_assignments table in Supabase
        if (customerData.assignedEmployeeId) {
          await supabase.from('employee_subscriber_assignments').insert([{
            employee_id: customerData.assignedEmployeeId,
            subscriber_id: createdId,
            is_active: true
          }]);
        }
      } else if (error) {
        console.log('Supabase insert subscriber error:', error);
      }
    } catch (e) {
      console.log('Supabase insert subscriber exception:', e);
    }

    const assignedEmp = employees.find(e => e.id === customerData.assignedEmployeeId);

    const newCustomer = {
      id: createdId,
      accountNo: `ACC-${createdId.slice(0, 5)}`,
      meterNo: customerData.meterNo || `MTR-${Math.floor(100000 + Math.random() * 900000)}`,
      name: customerData.name,
      email: customerData.email || '',
      phone: customerData.phone || '',
      address: customerData.address || '',
      tariffType: customerData.tariffType || 'Residential',
      assignedEmployeeId: customerData.assignedEmployeeId || null,
      assignedEmployeeName: assignedEmp ? assignedEmp.name : 'Unassigned',
      previousReading: parseFloat(customerData.initialReading) || 0.0,
      currentReading: parseFloat(customerData.initialReading) || 0.0,
      lastReadingDate: new Date().toISOString().split('T')[0],
      status: customerData.status || 'Active',
      balance: 0.00,
      outstandingStatus: 'Paid',
      meterType: customerData.meterType || 'Digital Smart Meter',
      zone: customerData.zone || 'North Metro District'
    };

    setCustomers(prev => {
      const nextCusts = [newCustomer, ...prev.filter(c => c.id !== newCustomer.id)];
      if (newCustomer.assignedEmployeeId) {
        setEmployees(prevEmps => prevEmps.map(emp => ({
          ...emp,
          assignedCustomersCount: nextCusts.filter(c => c.assignedEmployeeId === emp.id).length
        })));
      }
      return nextCusts;
    });

    addNotification(`New customer "${newCustomer.name}" added.`, 'info');
    return newCustomer;
  };

  const updateCustomer = async (customerId, updatedFields) => {
    setCustomers(prev => {
      const nextCusts = prev.map(cust => {
        if (cust.id === customerId) {
          let employeeName = cust.assignedEmployeeName;
          if (updatedFields.assignedEmployeeId !== undefined && updatedFields.assignedEmployeeId !== cust.assignedEmployeeId) {
            const emp = employees.find(e => e.id === updatedFields.assignedEmployeeId);
            employeeName = emp ? emp.name : 'Unassigned';
          }
          return { ...cust, ...updatedFields, assignedEmployeeName: employeeName };
        }
        return cust;
      });

      setEmployees(prevEmps => prevEmps.map(emp => ({
        ...emp,
        assignedCustomersCount: nextCusts.filter(c => c.assignedEmployeeId === emp.id).length
      })));

      return nextCusts;
    });

    // Supabase Update to `subscribers` table
    if (updatedFields.name || updatedFields.phone || updatedFields.address) {
      supabase.from('subscribers').update({
        full_name: updatedFields.name,
        phone: updatedFields.phone,
        address: updatedFields.address
      }).eq('subscriber_id', customerId).then(() => {}).catch(err => console.log('Supabase update subscriber:', err));
    }

    addNotification(`Customer information updated.`, 'info');
  };

  const deleteCustomer = async (customerId) => {
    const cust = customers.find(c => c.id === customerId);
    setCustomers(prev => {
      const nextCusts = prev.filter(c => c.id !== customerId);
      setEmployees(prevEmps => prevEmps.map(emp => ({
        ...emp,
        assignedCustomersCount: nextCusts.filter(c => c.assignedEmployeeId === emp.id).length
      })));
      return nextCusts;
    });

    // Supabase Delete from `subscribers` table
    supabase.from('subscribers').delete().eq('subscriber_id', customerId).then(() => {}).catch(err => console.log('Supabase delete subscriber:', err));

    if (cust) {
      addNotification(`Customer "${cust.name}" removed.`, 'warning');
    }
  };

  const addEmployee = async (empData) => {
    let createdId = `EMP-${Math.floor(100 + Math.random() * 900)}`;
    const dbRole = empData.role === 'ADMIN' ? 'admin' : empData.role === 'MANAGER' ? 'office_staff' : 'field_employee';
    let authUserId = null;

    // 1. Create authenticated account in Supabase Auth if credentials provided
    if (empData.email && empData.password) {
      try {
        const { data: authData, error: authErr } = await supabase.auth.signUp({
          email: empData.email,
          password: empData.password,
          options: {
            data: {
              full_name: empData.name,
              phone: empData.phone || '',
              role: dbRole
            }
          }
        });
        if (authData?.user) {
          authUserId = authData.user.id;
        } else if (authErr) {
          console.warn('Supabase Auth signUp notice:', authErr.message);
        }
      } catch (authEx) {
        console.warn('Supabase Auth signUp exception:', authEx);
      }
    }

    // 2. Insert into employees table linked with auth_user_id
    try {
      const payload = {
        full_name: empData.name,
        phone: empData.phone || '',
        role: dbRole,
        is_active: true
      };
      if (authUserId) {
        payload.auth_user_id = authUserId;
      }

      const { data: inserted, error } = await supabase.from('employees').insert([payload]).select('*');

      if (!error && inserted && inserted.length > 0) {
        createdId = inserted[0].employee_id;
      } else if (error) {
        console.log('Supabase insert employee error:', error);
      }
    } catch (e) {
      console.log('Supabase insert employee exception:', e);
    }

    const newEmp = {
      id: createdId,
      authUserId: authUserId,
      name: empData.name,
      email: empData.email,
      role: empData.role || 'OFFICE_EMPLOYEE',
      roleTitle: empData.roleTitle || 'Billing Specialist',
      department: empData.department || 'Operations',
      zone: empData.zone || 'Central District',
      assignedCustomersCount: 0,
      status: 'Active',
      avatar: empData.avatar || `https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120`,
      phone: empData.phone || '+1 (555) 000-0000'
    };

    setEmployees(prev => [newEmp, ...prev.filter(e => e.id !== newEmp.id)]);
    addNotification(`Employee "${newEmp.name}" registered with mobile login access.`, 'info');
    return newEmp;
  };

  const updateEmployee = async (employeeId, updatedFields) => {
    setEmployees(prev => prev.map(emp => emp.id === employeeId ? { ...emp, ...updatedFields } : emp));

    // Supabase Update to `employees` table
    if (updatedFields.name || updatedFields.phone || updatedFields.role) {
      const dbRole = updatedFields.role === 'ADMIN' ? 'admin' : updatedFields.role === 'MANAGER' ? 'office_staff' : 'field_employee';
      supabase.from('employees').update({
        full_name: updatedFields.name,
        phone: updatedFields.phone,
        role: dbRole
      }).eq('employee_id', employeeId).then(() => {}).catch(err => console.log('Supabase update employee:', err));
    }

    addNotification(`Employee profile updated.`, 'info');
  };

  const deleteEmployee = async (employeeId) => {
    const emp = employees.find(e => e.id === employeeId);
    setEmployees(prev => prev.filter(e => e.id !== employeeId));

    setCustomers(prevCusts => prevCusts.map(c => c.assignedEmployeeId === employeeId ? {
      ...c,
      assignedEmployeeId: null,
      assignedEmployeeName: 'Unassigned'
    } : c));

    // Supabase Delete from `employees` table
    supabase.from('employees').delete().eq('employee_id', employeeId).then(() => {}).catch(err => console.log('Supabase delete employee:', err));

    if (emp) {
      addNotification(`Employee "${emp.name}" deleted.`, 'warning');
    }
  };

  const assignCustomersToEmployee = async (employeeId, customerIds) => {
    const targetEmp = employees.find(e => e.id === employeeId);
    if (!targetEmp) return;

    // 1. Update React state immediately
    setCustomers(prevCustomers => {
      const nextCustomers = prevCustomers.map(cust => {
        if (customerIds.includes(cust.id)) {
          return { ...cust, assignedEmployeeId: employeeId, assignedEmployeeName: targetEmp.name };
        }
        if (cust.assignedEmployeeId === employeeId) {
          return { ...cust, assignedEmployeeId: null, assignedEmployeeName: 'Unassigned' };
        }
        return cust;
      });

      setEmployees(prevEmployees => prevEmployees.map(emp => {
        const count = nextCustomers.filter(c => c.assignedEmployeeId === emp.id).length;
        return { ...emp, assignedCustomersCount: count };
      }));

      return nextCustomers;
    });

    // 2. Persist to Supabase employee_subscriber_assignments table
    try {
      await supabase
        .from('employee_subscriber_assignments')
        .delete()
        .eq('employee_id', employeeId);

      if (customerIds && customerIds.length > 0) {
        const rows = customerIds.map(subId => ({
          employee_id: employeeId,
          subscriber_id: subId,
          is_active: true
        }));
        await supabase.from('employee_subscriber_assignments').insert(rows);
      }
    } catch (e) {
      console.log('Supabase assign customers error:', e);
    }

    addNotification(`Updated customer assignments for ${targetEmp.name}.`, 'success');
  };

  const generateInvoiceFromReading = ({
    customerId,
    previousReading,
    currentReading,
    tariffType
  }) => {
    const cust = customers.find(c => c.id === customerId);
    if (!cust) return null;

    const kwhConsumed = Math.max(0, currentReading - previousReading);
    const billDetails = calculateBillDetails(kwhConsumed, tariffType || cust.tariffType);
    
    const newInvId = `INV-2026-${Math.floor(100 + Math.random() * 900)}`;
    const invNumber = `PWR-2026-${Math.floor(1000 + Math.random() * 9000)}`;
    const now = new Date();
    const dueDate = new Date(now.getTime() + 15 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    const newInvoice = {
      id: newInvId,
      invoiceNumber: invNumber,
      customerId: cust.id,
      customerName: cust.name,
      accountNo: cust.accountNo,
      meterNo: cust.meterNo,
      billingPeriod: `${now.toLocaleString('default', { month: 'short' })} 1 - ${now.toLocaleString('default', { month: 'short' })} ${now.getDate()}, 2026`,
      issueDate: now.toISOString().split('T')[0],
      dueDate,
      previousReading,
      currentReading,
      kwhConsumed: billDetails.kwhConsumed,
      tariffType: cust.tariffType,
      baseCharge: billDetails.baseCharge,
      consumptionCharge: billDetails.consumptionCharge,
      taxAmount: billDetails.taxAmount,
      totalAmount: billDetails.totalAmount,
      status: 'Unpaid',
      paidAmount: 0.00
    };

    updateCustomer(cust.id, {
      previousReading,
      currentReading,
      lastReadingDate: now.toISOString().split('T')[0],
      balance: Math.round((cust.balance + billDetails.totalAmount) * 100) / 100,
      outstandingStatus: 'Unpaid'
    });

    setInvoices(prev => [newInvoice, ...prev]);
    addNotification(`Invoice ${invNumber} generated for ${cust.name} (${billDetails.totalAmount} USD).`, 'success');
    return newInvoice;
  };

  const markSupabaseReadingPaid = async (invoice, isPaid = true) => {
    if (!invoice?.readingId) return;

    try {
      const { data, error } = await supabase
        .from('meter_readings')
        .select('photo_url')
        .eq('reading_id', invoice.readingId)
        .limit(1);

      if (error || !data || data.length === 0) return;

      const currentMeta = parseReadingMetadata({ photo_url: data[0].photo_url });
      await supabase
        .from('meter_readings')
        .update({
          photo_url: JSON.stringify({
            ...currentMeta,
            is_paid: isPaid,
            paid_at: isPaid ? new Date().toISOString() : null
          })
        })
        .eq('reading_id', invoice.readingId);
    } catch (err) {
      console.log('Supabase reading payment sync error:', err);
    }
  };

  const recordPayment = ({
    customerId,
    invoiceId,
    amount,
    paymentMethod = 'Cash',
    referenceNo = '',
    notes = '',
    recordedBy = 'Office Employee'
  }) => {
    const cust = customers.find(c => c.id === customerId);
    const inv = invoiceId
      ? invoices.find(i => i.id === invoiceId)
      : invoices.find(i => i.customerId === customerId && i.status !== 'Paid');
    const targetInvoiceId = inv?.id || invoiceId || null;
    
    const numAmount = parseFloat(amount) || 0;
    if (numAmount <= 0) return null;

    const receiptNo = `RCP-2026-${Math.floor(1000 + Math.random() * 9000)}`;
    const now = new Date();
    const formattedDate = `${now.toISOString().split('T')[0]} ${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    const newPayment = {
      id: `PAY-${Math.floor(9000 + Math.random() * 1000)}`,
      receiptNo,
      customerId,
      customerName: cust?.name || 'Customer',
      invoiceId: targetInvoiceId,
      invoiceNumber: inv?.invoiceNumber || 'General Account Payment',
      amount: numAmount,
      paymentMethod,
      paymentDate: formattedDate,
      referenceNo: referenceNo || `TXN-${Math.floor(100000 + Math.random() * 900000)}`,
      recordedBy,
      notes
    };

    setPayments(prev => [newPayment, ...prev]);

    if (inv) {
      const newPaidAmount = Math.round(((inv.paidAmount || 0) + numAmount) * 100) / 100;
      let newInvStatus = inv.status;
      if (newPaidAmount >= inv.totalAmount) {
        newInvStatus = 'Paid';
      } else if (newPaidAmount > 0) {
        newInvStatus = 'Partial';
      }

      setInvoices(prev => prev.map(i => i.id === targetInvoiceId ? {
        ...i,
        paidAmount: newPaidAmount,
        status: newInvStatus
      } : i));

      if (newInvStatus === 'Paid') {
        markSupabaseReadingPaid(inv, true);
      }
    }

    if (cust) {
      const newCustBalance = Math.max(0, Math.round((cust.balance - numAmount) * 100) / 100);
      setCustomers(prev => prev.map(c => c.id === customerId ? {
        ...c,
        balance: newCustBalance,
        outstandingStatus: newCustBalance === 0 ? 'Paid' : 'Unpaid'
      } : c));
    }

    addNotification(`Payment of $${numAmount.toFixed(2)} recorded for ${cust?.name}. Receipt: ${receiptNo}`, 'success');
    return newPayment;
  };

  const addNotification = (text, type = 'info') => {
    setNotifications(prev => [
      { id: Date.now(), text, type, time: 'Just now' },
      ...prev.slice(0, 15)
    ]);
    setHasUnreadNotifications(true);
  };

  return (
    <DataContext.Provider value={{
      customers,
      employees,
      invoices,
      payments,
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
      addNotification
    }}>
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error('useData must be used within a DataProvider');
  }
  return context;
}
