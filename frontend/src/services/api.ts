import axios from 'axios';
import { getLanguage } from '@/i18n/t';

/**
 * Centralized API client for the AI-Powered Energy Analytics Platform.
 *
 * Every function here maps 1:1 to a FastAPI endpoint in the backend
 * (see backend/app/routers/). Response shapes are identical to the ones the
 * pages already consume, because the backend serialises with camelCase
 * aliases, so no page needed changing when the mock data was removed.
 *
 * Set VITE_API_URL in .env to point at the backend (defaults to localhost:8000).
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000, // AI endpoints fit models on request and can take a few seconds
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Attach the JWT issued by /auth/login to every outgoing request.
 *
 * Checked in both stores because "Remember me" decides which one holds the
 * session: localStorage when ticked, sessionStorage when not.
 */
function storedToken(): string | null {
  try {
    return localStorage.getItem('energy-token') ?? sessionStorage.getItem('energy-token');
  } catch {
    return null;
  }
}

/**
 * Whether someone is signed in on this device, whichever store "Remember me"
 * chose. The theme and language providers save a change to the account only
 * when this is true; they used to look in localStorage alone, so a session
 * signed in without "Remember me" never saved either choice to the account.
 */
export function hasSession(): boolean {
  return storedToken() !== null;
}

/**
 * Puts a new token where the current one is kept. Used after a password
 * change: the server retires every token issued before it, this device's
 * included, and hands this device a fresh one.
 */
function replaceStoredToken(token: string): void {
  try {
    if (localStorage.getItem('energy-token') !== null) localStorage.setItem('energy-token', token);
    else sessionStorage.setItem('energy-token', token);
  } catch {
    // Storage unavailable: the next request is refused and the user signs in again.
  }
}

api.interceptors.request.use((config) => {
  const token = storedToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // The backend writes recommendations, alerts and explanations in this
  // language (backend/app/core/i18n.py). Read on every request, so a language
  // chosen a moment ago applies to the very next call.
  config.headers['Accept-Language'] = getLanguage();
  return config;
});

// An expired or invalid token means the stored session is stale: clear it and
// send the user back to sign in, rather than letting pages fail one by one.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const isAuthCall = error?.config?.url?.includes('/auth/');

    if (status === 401 && !isAuthCall) {
      for (const store of [localStorage, sessionStorage]) {
        store.removeItem('energy-token');
        store.removeItem('energy-user');
      }
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

/** Unwraps `response.data` so call sites stay terse. */
const get = async <T>(url: string, params?: Record<string, unknown>): Promise<T> =>
  (await api.get<T>(url, { params })).data;

const post = async <T>(url: string, body?: unknown): Promise<T> =>
  (await api.post<T>(url, body)).data;

const patch = async <T>(url: string, body?: unknown): Promise<T> =>
  (await api.patch<T>(url, body)).data;

const del = async <T>(url: string): Promise<T> => (await api.delete<T>(url)).data;

/**
 * Fetches a file endpoint and saves the result to the user's device.
 *
 * Fetched as a blob rather than by navigating to the URL, because these
 * endpoints require the Authorization header and a plain link cannot send one.
 * Returns the filename that was saved.
 */
async function downloadBlob(
  url: string,
  params: Record<string, unknown>,
  fallbackName: string,
): Promise<string> {
  const response = await api.get(url, { params, responseType: 'blob' });

  const disposition = response.headers['content-disposition'] as string | undefined;
  const filename = disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? fallbackName;

  const objectUrl = window.URL.createObjectURL(response.data as Blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);

  return filename;
}

/* -------------------------------------------------------------------------- */
/* Response shapes, as the backend serialises them (backend/app/schemas)      */
/* -------------------------------------------------------------------------- */
export interface Bill {
  id: string; month: string; amount: number; dueDate: string; status: string;
  paid: number; remaining: number;
}

export interface Payment {
  id: string; date: string; amount: number; method: string; status: string; billId: string | null;
}

export interface Recommendation {
  id: string; title: string; description: string; estimatedSavings: number;
  priority: string; icon: string; completed: boolean;
}

export interface Alert {
  id: string; type: string; title: string; message: string; severity: string; date: string; read: boolean;
}

/** One calendar month. `period` is YYYY-MM; `month` alone ("Jan") has no year. */
export interface MonthlyConsumption {
  month: string; period: string | null; kwh: number; cost: number;
}

export interface CustomerDashboard {
  monthlyConsumption: MonthlyConsumption;
  currentBill: Bill;
  outstandingBalance: number;
  energySavingScore: number | null;
  /** What the score compares against: the same month last year, or last month. */
  energySavingBasis: 'year' | 'month' | null;
  energySavingChangePct: number | null;
  consumptionTrend: MonthlyConsumption[];
  monthlyBills: Bill[];
  paymentHistory: Payment[];
  recentRecommendations: Recommendation[];
  recentAlerts: Alert[];
}

export interface ForecastPoint {
  label: string; actual: number | null; predicted: number; lower: number; upper: number;
}

export interface ForecastCard {
  period: string; kwh: number; change: number; lower: number; upper: number;
}

export interface AdminStats {
  totalCustomers: number; activeCustomers: number; revenue: number; monthlyConsumption: number;
  predictionAccuracy: number | null; revenueChange: number; customersChange: number | null;
  consumptionChange: number;
  /** YYYY-MM of the month `monthlyConsumption` is for: the newest complete month. */
  consumptionPeriod: string | null;
  /** The day the month-based figures are for: the newest reading, not today. */
  asOf: string | null;
  isLive: boolean;
}

export interface TopConsumer { name: string; consumption: number; change: number | null }
export interface RegionalStat { region: string; customers: number; revenue: number; consumption: number }
export interface RevenuePoint { month: string; revenue: number }

export interface AdminDashboard {
  stats: AdminStats;
  revenueTrend: RevenuePoint[];
  customerGrowth: { month: string; customers: number }[];
  customerBase: { month: string; billed: number; settled: number }[];
  forecastData: ForecastPoint[];
  consumptionTrend: MonthlyConsumption[];
  topConsumers: TopConsumer[];
  recentActivities: { id: string; text: string; time: string; type: string }[];
}

export interface BusinessKpis {
  revenue: number; consumption: number; bills: number; payments: number;
  topConsumers: TopConsumer[];
  regionalStats: RegionalStat[];
  revenueTrend: RevenuePoint[];
  paymentTrend: { month: string; count: number }[];
  changes: { revenue: number | null; consumption: number | null; bills: number | null; payments: number | null };
}

export interface RevenueOverview {
  revenueTrend: RevenuePoint[];
  regionalStats: RegionalStat[];
  billingStatuses: { status: string; count: number }[];
  billedThisMonth: number;
  collectedThisMonth: number;
  periodLabel: string;
  periodIsCurrent: boolean;
  outstandingTotal: number;
  totalRevenue: number;
}

export interface Segment { name: string; count: number; percentage: number; color: string; description: string }

export interface AnomalyFinding {
  id: string; type: string; customer: string; severity: string; value: string; description: string; date: string;
}

export interface CustomerRecord {
  id: string; name: string; email: string; phone: string | null; address: string | null;
  region: string | null; plan: string; status: string; consumption: number; balance: number;
  /** False until the customer has registered for portal access with this ID. */
  registered: boolean;
}

export interface Profile {
  name: string; email: string; phone: string | null; address: string | null; theme: string; language: string;
}

/* -------------------------------------------------------------------------- */
/* Authentication                                                             */
/* -------------------------------------------------------------------------- */
export const authService = {
  login: async (email: string, password: string) =>
    post<{ token: string; user: Record<string, string> }>('/auth/login', { email, password }),

  /**
   * Activates portal access for an account the provider already holds.
   * `customerId` is the number on the customer's bill and is what links the
   * new login to their existing meter readings. `registrationCode` is the
   * one-time code the provider issues with it: the ID alone is printed on
   * every bill, so it cannot prove who is registering.
   */
  register: async (customerId: string, registrationCode: string, name: string, email: string, password: string) =>
    post<{ token: string; user: Record<string, string> }>('/auth/register', {
      customer_id: customerId,
      registration_code: registrationCode,
      name,
      email,
      password,
    }),

  /** Step 1 of password reset, issues a single-use, expiring token. */
  forgotPassword: async (email: string) =>
    post<{
      sent: boolean;
      email: string;
      // Returned only while no email provider is configured, so the flow can
      // be completed without one.
      resetToken?: string | null;
      expiresInMinutes?: number | null;
    }>('/auth/forgot-password', { email }),

  /** Step 2 of password reset, exchanges the token for a new password. */
  resetPassword: async (token: string, newPassword: string) =>
    post<{ reset: boolean; email: string }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    }),

  /** Validates a stored token against the backend. */
  me: async () => get<Record<string, string>>('/auth/me'),

  /**
   * Changes the password of the signed-in account. Requires the current
   * password, so a stolen session token alone cannot lock the owner out.
   *
   * The change signs out every other device. This one stays signed in because
   * the token that comes back replaces the one it was using.
   */
  changePassword: async (currentPassword: string, newPassword: string) => {
    const res = await post<{ changed: boolean; token?: string | null }>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    if (res.token) replaceStoredToken(res.token);
    return res;
  },
};

/* -------------------------------------------------------------------------- */
/* Dashboards                                                                 */
/* -------------------------------------------------------------------------- */
export const dashboardService = {
  getCustomerDashboard: async () => get<CustomerDashboard>('/dashboard/customer'),
  getAdminDashboard: async () => get<AdminDashboard>('/dashboard/admin'),
};

/* -------------------------------------------------------------------------- */
/* Consumption                                                                */
/* -------------------------------------------------------------------------- */
export const consumptionService = {
  /** Monthly totals. `months` is what the Consumption page's range selector changes. */
  getMonthly: async (months = 12) =>
    get<MonthlyConsumption[]>('/consumption/monthly', { months }),
  getDaily: async (days = 30) =>
    get<{ day: number; kwh: number }[]>('/consumption/daily', { days }),
  getHourly: async () => get<{ hour: string; kwh: number }[]>('/consumption/hourly'),

  /**
   * Downloads the customer's own consumption statement.
   * Server-generated, so the figures in the file are the figures in the
   * database rather than whatever the browser happened to have in memory.
   */
  exportStatement: async (months = 12, format: 'pdf' | 'excel' = 'pdf'): Promise<string> =>
    downloadBlob(
      '/consumption/export',
      { months, format },
      `consumption.${format === 'pdf' ? 'pdf' : 'xlsx'}`,
    ),
  /** Admin only, system-wide load by weekday and hour. */
  getHeatmap: async (days = 28) => get<Heatmap>('/consumption/heatmap', { days }),
};

/* -------------------------------------------------------------------------- */
/* Preferences                                                                */
/* -------------------------------------------------------------------------- */
export interface NotificationPreferences {
  highUsage: boolean;
  billReminders: boolean;
  anomalies: boolean;
  savingsMilestones: boolean;
}

export const preferencesService = {
  /** Which alert categories this account receives. */
  getNotifications: async () => get<NotificationPreferences>('/preferences/notifications'),

  /**
   * Saves the choices and re-runs the alert engine server-side, so the Alerts
   * page reflects the change immediately rather than at some later refresh.
   */
  updateNotifications: async (changes: Partial<NotificationPreferences>) =>
    patch<NotificationPreferences>('/preferences/notifications', changes),
};

/* -------------------------------------------------------------------------- */
/* Search                                                                     */
/* -------------------------------------------------------------------------- */
export type SearchKind =
  | 'customer'
  | 'bill'
  | 'payment'
  | 'recommendation'
  | 'alert'
  | 'anomaly';

export interface SearchResult {
  kind: SearchKind;
  id: string;
  title: string;
  subtitle: string;
}

export const searchService = {
  /**
   * Backs the header search box. One request, and what it searches depends on
   * the caller's role: an admin gets customers and open anomalies, a customer
   * gets their own bills, payments, recommendations and alerts.
   */
  search: async (q: string, limit = 8) =>
    get<{ query: string; results: SearchResult[] }>('/search', { q, limit }),
};

/* -------------------------------------------------------------------------- */
/* Billing & payments                                                         */
/* -------------------------------------------------------------------------- */
export const billsService = {
  getAll: async () => get<Bill[]>('/bills'),
  getById: async (id: string) => get<Bill>(`/bills/${id}`),

  /**
   * Records a payment against a bill and returns the payment row.
   * The Pay button used to raise a toast and send nothing.
   */
  // Cash by default: the three channels this provider collects through are
  // Cash, OMT and Whish, and 'Online Card' was neither offered to the customer
  // nor possible, the endpoint records a book entry, it does not take money.
  pay: async (billId: string, method: 'Cash' | 'OMT' | 'Whish' = 'Cash') =>
    post<Payment>(
      `/bills/${billId}/pay`,
      { method },
    ),

  /** Downloads the bill as a PDF the server renders from the stored row. */
  download: async (billId: string): Promise<string> =>
    downloadBlob(`/bills/${billId}/pdf`, {}, `${billId}.pdf`),
};

export const paymentsService = {
  getAll: async () => get<Payment[]>('/payments'),

  /** Downloads a payment receipt PDF (SRS VI-iii "Payment receipts"). */
  downloadReceipt: async (paymentId: string): Promise<string> =>
    downloadBlob(`/payments/${paymentId}/receipt`, {}, `receipt-${paymentId}.pdf`),
};

/* -------------------------------------------------------------------------- */
/* Engagement, recommendations & alerts                                      */
/* -------------------------------------------------------------------------- */
export const recommendationsService = {
  getAll: async () => get<Recommendation[]>('/recommendations'),
  markCompleted: async (id: string) =>
    patch<{ id: string; completed: boolean }>(`/recommendations/${id}`, { completed: true }),
  /** Re-runs the recommendation engine against the latest consumption data. */
  refresh: async () => post<Recommendation[]>('/recommendations/refresh'),
};

export interface Heatmap {
  days: string[];
  hours: string[];
  grid: number[][];
  maxKwh: number;
  windowDays: number;
}

export interface RiskCustomer {
  customerId: string;
  name: string;
  region: string | null;
  plan: string | null;
  score: number;
  band: 'High' | 'Medium' | 'Low' | 'Unknown';
  outstanding: number;
  overdueBills: number;
  avgDaysLate: number;
  daysSincePayment: number | null;
  reasons: string[];
}

export interface RiskSummary {
  high: number;
  medium: number;
  low: number;
  unknown: number;
  amountAtRisk: number;
  /** The date the recency signal is counted to: the newest data, not today. */
  asOf: string | null;
  customers: RiskCustomer[];
}

export const riskService = {
  /** Payment-default early warning, the Proposal's "customers at risk of payment default". */
  getSummary: async () => get<RiskSummary>('/analytics/risk'),
};

export const alertsService = {
  getAll: async () => get<Alert[]>('/alerts'),
  /** Re-runs the alert engine against the latest readings, bills and anomalies. */
  refresh: async () => post<Alert[]>('/alerts/refresh', {}),
  markRead: async (id: string, read = true) =>
    patch<{ id: string; read: boolean }>(`/alerts/${id}`, { read }),
};

/* -------------------------------------------------------------------------- */
/* AI module                                                                  */
/* -------------------------------------------------------------------------- */
export interface ForecastInsights {
  trend: string;
  peakPeriod: string | null;
  peakKwh: number | null;
  model: string;
  weeksObserved: number;
  horizonWeeks: number;
  seasonal: boolean;
  usesWeather: boolean;
}

export const forecastService = {
  /** `insights` describes what the fit actually did, and is null when there was no data to fit. */
  getForecast: async () =>
    get<{ forecastData: ForecastPoint[]; forecastCards: ForecastCard[]; insights: ForecastInsights | null }>('/ai/forecast'),
};

export const segmentationService = {
  getSegments: async () => get<Segment[]>('/ai/segments'),
};

export const anomalyService = {
  getAll: async () => get<AnomalyFinding[]>('/ai/anomalies'),
  /** Re-scans every customer with the anomaly-detection model. */
  run: async () => post<AnomalyFinding[]>('/ai/anomalies/run'),
};

/* -------------------------------------------------------------------------- */
/* Admin analytics                                                            */
/* -------------------------------------------------------------------------- */
export const analyticsService = {
  getBusinessKpis: async () => get<BusinessKpis>('/analytics/kpis'),
  getRegional: async () => get<RegionalStat[]>('/analytics/regional'),
};

export const revenueService = {
  getOverview: async () => get<RevenueOverview>('/revenue/overview'),
};

/**
 * The inputs the SRS specifies for the Customer Management Module
 * (Section VI-i): Customer ID, Full Name, Email, Phone, Address, plus region
 * and plan, which the regional and segment analytics need.
 */
export interface CustomerPayload {
  customerId: string;
  name: string;
  email: string;
  phone?: string;
  address?: string;
  region?: string;
  plan?: string;
  status?: string;
}

/** Converts the camelCase form payload to the snake_case body the API takes. */
function toCustomerBody(p: Partial<CustomerPayload>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (p.customerId !== undefined) body.customer_id = p.customerId;
  if (p.name !== undefined) body.name = p.name;
  if (p.email !== undefined) body.email = p.email;
  if (p.phone !== undefined) body.phone = p.phone;
  if (p.address !== undefined) body.address = p.address;
  if (p.region !== undefined) body.region = p.region;
  if (p.plan !== undefined) body.plan = p.plan;
  if (p.status !== undefined) body.status = p.status;
  return body;
}

export const customerService = {
  getAll: async () => get<CustomerRecord[]>('/customers'),
  getById: async (id: string) => get<CustomerRecord>(`/customers/${id}`),

  /** Manage Customer Accounts: Add */
  create: async (payload: CustomerPayload) => post<CustomerRecord>('/customers', toCustomerBody(payload)),

  /** Manage Customer Accounts, Update. The Customer ID is never editable. */
  update: async (id: string, payload: Partial<CustomerPayload>) => {
    const body = toCustomerBody(payload);
    delete body.customer_id;
    return patch<CustomerRecord>(`/customers/${id}`, body);
  },

  /** Manage Customer Accounts, Deactivate (suspends access, keeps all records) */
  deactivate: async (id: string) => post<CustomerRecord>(`/customers/${id}/deactivate`),

  /** Reactivate a suspended account */
  activate: async (id: string) => post<CustomerRecord>(`/customers/${id}/activate`),

  /**
   * Issues a one-time registration code for an account nobody has registered
   * yet. The customer needs it, with the Customer ID, to register. It is shown
   * once: the server keeps only its hash, and a new code replaces the old one.
   */
  issueRegistrationCode: async (id: string) =>
    post<{ customerId: string; registrationCode: string; expiresAt: string }>(`/customers/${id}/registration-code`),

  /** Permanent delete, also removes consumption, bills and payments */
  remove: async (id: string) =>
    del<{
      id: string;
      deleted: boolean;
      removedConsumptionRows: number;
      removedBills: number;
      removedPayments: number;
    }>(`/customers/${id}`),
};

/* -------------------------------------------------------------------------- */
/* AI chatbot                                                                 */
/* -------------------------------------------------------------------------- */
export const chatService = {
  getHistory: async () => get<{ id: string; title: string; date: string }[]>('/chat/history'),
  sendMessage: async (message: string, conversationId?: number) =>
    post<{ reply: string; conversationId?: number }>('/chat/message', {
      message,
      conversation_id: conversationId ?? null,
    }),

  /** One stored conversation with its messages, for reopening it from the sidebar. */
  getConversation: async (id: string) =>
    get<{
      id: string;
      title: string;
      date: string;
      messages: { id: string; role: 'user' | 'assistant'; content: string; time: string }[];
    }>(`/chat/history/${id}`),

  /** Deletes a conversation. Backs the bin icon in the sidebar. */
  deleteConversation: async (id: string) => del<{ deleted: boolean; id: string }>(`/chat/history/${id}`),
};

/* -------------------------------------------------------------------------- */
/* Reports, "Report Generation" (Software Architecture, Section V-ii)        */
/* -------------------------------------------------------------------------- */
export const reportService = {
  getTypes: async () =>
    get<{ id: string; label: string; description: string }[]>('/reports'),

  /**
   * Downloads a report and saves it to the user's device.
   *
   * Fetched as a blob rather than by navigating to the URL, because the
   * endpoint requires the Authorization header, a plain link cannot send it.
   */
  download: async (
    type: string,
    from: string,
    to: string,
    format: 'pdf' | 'excel',
  ): Promise<string> =>
    downloadBlob(
      `/reports/${type}`,
      { from, to, format },
      `${type}-report.${format === 'pdf' ? 'pdf' : 'xlsx'}`,
    ),
};

/* -------------------------------------------------------------------------- */
/* Profile                                                                    */
/* -------------------------------------------------------------------------- */
export const profileService = {
  getProfile: async () => get<Profile>('/profile'),
  /** Accepts name, email, phone, address, theme ('light' | 'dark') and language. */
  updateProfile: async (patchBody: Record<string, string>) => patch<Profile>('/profile', patchBody),
};

/* -------------------------------------------------------------------------- */
/* Ishtirak: the generator business (Project 3)                               */
/* -------------------------------------------------------------------------- */
export interface IshtirakGenerator {
  generatorId: string; name: string; capacityKw: number;
  producedKwhPeriod: number; runHoursPeriod: number | null;
  fuelLitresPeriod: number | null; litresPerKwh: number | null; ecuConnected: boolean;
  phaseImbalancePct: number | null; imbalanceFlagged: boolean; activeAlarms: number;
}

export interface IshtirakZone {
  zoneId: string; name: string; areaType: string | null; avgDistanceM: number | null;
  deliveredKwh: number; billedKwh: number; lossKwh: number; lossPct: number | null;
  normalTechnicalKwh: number; excessTechnicalKwh: number; measurementKwh: number;
  unbilledKwh: number; unexplainedKwh: number; unexplainedPct: number | null;
  confidence: number | null; explanation: string;
}

export interface IshtirakDashboard {
  asOf: string; periodStart: string; periodEnd: string; isLive: boolean;
  producedKwh: number; billedKwh: number; gapKwh: number; lossPct: number | null;
  generators: IshtirakGenerator[];
  zones: IshtirakZone[];
  collections: { invoiced: number; collected: number; outstanding: number; currency: string; unpaidInvoices: number };
  alarms: { generatorId: string; generatorName: string | null; timestamp: string; severity: string | null; message: string | null }[];
  summary: string;
}

export interface IshtirakAnswer {
  question: string; answer: string; answered: boolean;
  source: 'database' | 'documents' | 'none';
  intent: string | null; facts: Record<string, unknown>;
  readsFrom: string[]; citations: string[]; rephrasedByModel: boolean;
}

export interface RuleShortlistEntry {
  subscriberId: string;
  subscriberName: string | null;
  zoneName: string | null;
  zoneId: string | null;
  rules: string[];
  /** 0-1. How far past the thresholds this case sits. NOT a probability of guilt. */
  score: number;
  evidence: string[];
  /** Every ordinary reason this pattern appears, shown beside the flag. */
  innocentExplanations: string[];
  /**
   * What to check on site, drawn from the rules this subscriber actually
   * tripped. Instructions about the meter and the supply, never about the
   * person: they are what settles which of the explanations above is true.
   */
  visitChecks: string[];
}

export interface IshtirakRules {
  perRule: Record<string, string[]>;
  flaggedSubscribers: string[];
  flaggedCount: number;
  totalSubscribers: number;
  shortlist: RuleShortlistEntry[];
  gridFindings: { generatorId: string; generatorName: string; rule: string; evidence: string; action: string }[];
  paymentDefaulters?: string[];
  note?: string;
}

export const ishtirakService = {
  getDashboard: async (months = 1) => get<IshtirakDashboard>(`/ishtirak/dashboard?months=${months}`),
  /**
   * The rules engine's output. Served since Phase 3 and, until now, displayed
   * nowhere: 38 flagged accounts, a ranked shortlist and two generator findings
   * were computed on every request and read by nothing.
   */
  getRules: async () => get<IshtirakRules>('/ishtirak/rules'),
  getZone: async (zoneId: string) => get<Record<string, unknown>>(`/ishtirak/zones/${zoneId}`),
  /** Every figure in the reply comes from a query; `facts` is that query's result. */
  ask: async (question: string) => post<IshtirakAnswer>('/ishtirak/ask', { question }),
  getCatalogue: async () => get<Record<string, unknown>>('/ishtirak/ask/catalogue'),
};

export default api;
