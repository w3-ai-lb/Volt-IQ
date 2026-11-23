// CRM data access. Every call goes to the VoltIQ backend (/crm/* endpoints in
// backend/app/routers/crm.py) through the shared axios client, so it carries
// the same sign-in token as the rest of the web app.
//
// This file replaced the Supabase client the CRM used before unification.
import api from '@/services/api';

const data = (promise) => promise.then((r) => r.data);

export const crmApi = {
  me: () => data(api.get('/crm/me')),

  listCustomers: () => data(api.get('/crm/customers')),
  createCustomer: (body) => data(api.post('/crm/customers', body)),
  updateCustomer: (id, body) => data(api.patch(`/crm/customers/${encodeURIComponent(id)}`, body)),
  deleteCustomer: (id) => api.delete(`/crm/customers/${encodeURIComponent(id)}`),

  listEmployees: () => data(api.get('/crm/employees')),
  createEmployee: (body) => data(api.post('/crm/employees', body)),
  updateEmployee: (id, body) => data(api.patch(`/crm/employees/${encodeURIComponent(id)}`, body)),
  deleteEmployee: (id) => api.delete(`/crm/employees/${encodeURIComponent(id)}`),
  assignCustomers: (id, customerIds) =>
    data(api.put(`/crm/employees/${encodeURIComponent(id)}/customers`, { customerIds })),

  listInvoices: () => data(api.get('/crm/invoices')),
  recordReading: (body) => data(api.post('/crm/readings', body)),

  listPayments: () => data(api.get('/crm/payments')),
  recordPayment: (body) => data(api.post('/crm/payments', body)),

  getTariff: () => data(api.get('/crm/tariff')),
  setTariff: (ratePerKwh) => data(api.put('/crm/tariff', { ratePerKwh })),
};

export function apiError(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return err?.message || fallback;
}
