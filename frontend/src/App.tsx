import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { AuthProvider } from '@/context/AuthContext';
import { ThemeProvider } from '@/context/ThemeContext';
import { ToastProvider } from '@/context/ToastContext';
import { I18nProvider } from '@/context/I18nContext';
import { CustomerRoute } from '@/routes/CustomerRoute';
import { AdminRoute } from '@/routes/AdminRoute';
import { StaffRoute } from '@/routes/StaffRoute';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { AdminLayout } from '@/layouts/AdminLayout';

const LandingPage = lazy(() => import('@/pages/LandingPage'));
const LoginPage = lazy(() => import('@/pages/auth/LoginPage'));
const RegisterPage = lazy(() => import('@/pages/auth/RegisterPage'));
const ForgotPasswordPage = lazy(() => import('@/pages/auth/ForgotPasswordPage'));
const CustomerDashboard = lazy(() => import('@/pages/customer/CustomerDashboard'));
const ConsumptionPage = lazy(() => import('@/pages/customer/ConsumptionPage'));
const BillsPage = lazy(() => import('@/pages/customer/BillsPage'));
const PaymentsPage = lazy(() => import('@/pages/customer/PaymentsPage'));
const RecommendationsPage = lazy(() => import('@/pages/customer/RecommendationsPage'));
const AlertsPage = lazy(() => import('@/pages/customer/AlertsPage'));
const ChatbotPage = lazy(() => import('@/pages/customer/ChatbotPage'));
const ProfilePage = lazy(() => import('@/pages/customer/ProfilePage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
const AdminDashboard = lazy(() => import('@/pages/admin/AdminDashboard'));
const LossDashboard = lazy(() => import('@/pages/admin/LossDashboard'));
const FieldVisits = lazy(() => import('@/pages/admin/FieldVisits'));
const CustomerManagement = lazy(() => import('@/pages/admin/CustomerManagement'));
const AnalyticsDashboard = lazy(() => import('@/pages/admin/AnalyticsDashboard'));
const RevenuePage = lazy(() => import('@/pages/admin/RevenuePage'));
const DemandForecast = lazy(() => import('@/pages/admin/DemandForecast'));
const CustomerSegmentation = lazy(() => import('@/pages/admin/CustomerSegmentation'));
const AnomalyDetection = lazy(() => import('@/pages/admin/AnomalyDetection'));
const ReportsPage = lazy(() => import('@/pages/admin/ReportsPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));
// The CRM module (formerly a separate app on Supabase), see src/modules/crm.
const CrmApp = lazy(() => import('@/modules/crm/CrmApp'));

function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
      {children}
    </motion.div>
  );
}

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Suspense><PageWrapper><LandingPage /></PageWrapper></Suspense>} />
        <Route path="/login" element={<Suspense><PageWrapper><LoginPage /></PageWrapper></Suspense>} />
        <Route path="/register" element={<Suspense><PageWrapper><RegisterPage /></PageWrapper></Suspense>} />
        <Route path="/forgot-password" element={<Suspense><PageWrapper><ForgotPasswordPage /></PageWrapper></Suspense>} />

        <Route path="/app" element={<CustomerRoute><DashboardLayout role="customer" /></CustomerRoute>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<Suspense><PageWrapper><CustomerDashboard /></PageWrapper></Suspense>} />
          <Route path="consumption" element={<Suspense><PageWrapper><ConsumptionPage /></PageWrapper></Suspense>} />
          <Route path="bills" element={<Suspense><PageWrapper><BillsPage /></PageWrapper></Suspense>} />
          <Route path="payments" element={<Suspense><PageWrapper><PaymentsPage /></PageWrapper></Suspense>} />
          <Route path="recommendations" element={<Suspense><PageWrapper><RecommendationsPage /></PageWrapper></Suspense>} />
          <Route path="alerts" element={<Suspense><PageWrapper><AlertsPage /></PageWrapper></Suspense>} />
          <Route path="chatbot" element={<Suspense><PageWrapper><ChatbotPage /></PageWrapper></Suspense>} />
          <Route path="profile" element={<Suspense><PageWrapper><ProfilePage /></PageWrapper></Suspense>} />
          <Route path="settings" element={<Suspense><PageWrapper><SettingsPage /></PageWrapper></Suspense>} />
        </Route>

        <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<Suspense><PageWrapper><AdminDashboard /></PageWrapper></Suspense>} />
          {/* Project 3: the generator owner's view of where his electricity went. */}
          <Route path="loss" element={<Suspense><PageWrapper><LossDashboard /></PageWrapper></Suspense>} />
          <Route path="visits" element={<Suspense><PageWrapper><FieldVisits /></PageWrapper></Suspense>} />
          <Route path="customers" element={<Suspense><PageWrapper><CustomerManagement /></PageWrapper></Suspense>} />
          <Route path="analytics" element={<Suspense><PageWrapper><AnalyticsDashboard /></PageWrapper></Suspense>} />
          <Route path="revenue" element={<Suspense><PageWrapper><RevenuePage /></PageWrapper></Suspense>} />
          <Route path="forecast" element={<Suspense><PageWrapper><DemandForecast /></PageWrapper></Suspense>} />
          <Route path="segmentation" element={<Suspense><PageWrapper><CustomerSegmentation /></PageWrapper></Suspense>} />
          <Route path="anomalies" element={<Suspense><PageWrapper><AnomalyDetection /></PageWrapper></Suspense>} />
          <Route path="reports" element={<Suspense><PageWrapper><ReportsPage /></PageWrapper></Suspense>} />
          {/* Administrators have their own account too. Without this route the
              Profile link in the header led to Settings, which has no name
              field, so an administrator could not change their own name. */}
          <Route path="profile" element={<Suspense><PageWrapper><ProfilePage /></PageWrapper></Suspense>} />
          <Route path="settings" element={<Suspense><PageWrapper><SettingsPage /></PageWrapper></Suspense>} />
        </Route>

        {/* CRM: customers, staff, billing and payments, for admins and staff. */}
        <Route path="/crm/*" element={<StaffRoute><Suspense><CrmApp /></Suspense></StaffRoute>} />

        <Route path="*" element={<Suspense><PageWrapper><NotFoundPage /></PageWrapper></Suspense>} />
      </Routes>
    </AnimatePresence>
  );
}

/**
 * The order of these providers is not cosmetic.
 *
 * I18nProvider remounts everything below it when the language changes, which is
 * what makes a language switch redraw the whole interface at once. Anything
 * that must survive that remount therefore has to sit ABOVE it:
 *
 *   - BrowserRouter, because signing in applies the account's language and then
 *     navigates. With the router below, the navigate call belonged to a router
 *     that had just been thrown away, and the sign-in appeared to hang.
 *   - ToastProvider, because "Language changed" is raised in the same click
 *     that changes it, and a toast held below the remount is discarded before
 *     anyone sees it.
 *
 * AuthProvider sits below because it reads the language and theme off the user
 * it just signed in, and both of those live in providers above it.
 */
export default function App() {
  return (
    <ThemeProvider>
      {/* basename lets the same build run at the site root or under a sub-path (GitHub Pages). */}
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
        <ToastProvider>
          <I18nProvider>
            <AuthProvider>
              <AnimatedRoutes />
            </AuthProvider>
          </I18nProvider>
        </ToastProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
