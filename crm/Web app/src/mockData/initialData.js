// Clean initial state (all mock customers, invoices, payments cleared)
// Everything syncs live with Supabase PostgreSQL database tables.

export const INITIAL_EMPLOYEES = [
  {
    id: 'EMP-101',
    name: 'System Administrator',
    email: 'admin@gridpower.com',
    role: 'ADMIN',
    roleTitle: 'Chief System Administrator',
    department: 'Operations & IT',
    zone: 'Headquarters',
    assignedCustomersCount: 0,
    status: 'Active',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120',
    phone: '+1 (555) 019-2831'
  }
];

export const INITIAL_CUSTOMERS = [];
export const INITIAL_INVOICES = [];
export const INITIAL_PAYMENTS = [];
