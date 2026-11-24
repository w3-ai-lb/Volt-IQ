// CRM data access. Every call goes to the VoltIQ backend (/crm/* endpoints in
// backend/app/routers/crm.py) through the shared axios client, so it carries
// the same sign-in token as the rest of the web app.
//
// This file replaced the Supabase client the CRM used before unification.
import api from '@/services/api';

const data = (promise) => promise.then((r) => r.data);

export const crmApi = {
  me: () => data(api.get('/crm/me')),

  // Stage 2: small rows for pickers, one page for the directory, totals for the dashboard.
  customerOptions: () => data(api.get('/crm/customers/options')),
  customersPage: (params) => data(api.get('/crm/customers/page', { params })),
  summary: () => data(api.get('/crm/summary')),
  createCustomer: (body) => data(api.post('/crm/customers', body)),
  updateCustomer: (id, body) => data(api.patch(`/crm/customers/${encodeURIComponent(id)}`, body)),
  deleteCustomer: (id) => api.delete(`/crm/customers/${encodeURIComponent(id)}`),

  listEmployees: () => data(api.get('/crm/employees')),
  createEmployee: (body) => data(api.post('/crm/employees', body)),
  updateEmployee: (id, body) => data(api.patch(`/crm/employees/${encodeURIComponent(id)}`, body)),
  deleteEmployee: (id) => api.delete(`/crm/employees/${encodeURIComponent(id)}`),
  assignCustomers: (id, customerIds) =>
    data(api.put(`/crm/employees/${encodeURIComponent(id)}/customers`, { customerIds })),

  listInvoices: (params = { limit: 200 }) => data(api.get('/crm/invoices', { params })),
  recordReading: (body) => data(api.post('/crm/readings', body)),

  listPayments: (params = { limit: 200 }) => data(api.get('/crm/payments', { params })),
  recordPayment: (body) => data(api.post('/crm/payments', body)),

  getTariff: () => data(api.get('/crm/tariff')),
  setTariff: (ratePerKwh) => data(api.put('/crm/tariff', { ratePerKwh })),
};

export function apiError(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return err?.message || fallback;
}
