import React, { useState } from 'react';
import { AuthProvider } from './context/AuthContext';
import { DataProvider, useData } from './context/DataContext';
import { SettingsProvider, useSettings } from './context/SettingsContext';
import Navbar from './components/layout/Navbar';
import Sidebar from './components/layout/Sidebar';
import DashboardView from './components/dashboard/DashboardView';
import CustomerList from './components/customers/CustomerList';
import EmployeeList from './components/employees/EmployeeList';
import BillingAndPaymentsView from './components/billing-payments/BillingAndPaymentsView';
import ReportsAnalyticsView from './components/reports/ReportsAnalyticsView';
import SettingsView from './components/settings/SettingsView';
import RecordPaymentModal from './components/payments/RecordPaymentModal';
import ReceiptModal from './components/payments/ReceiptModal';
import './crm.css';

// The CRM module of the unified web app, served at /crm.
// Sign-in is handled by the platform (see StaffRoute in src/routes), so there
// is no login screen here any more.
function MainApp() {
  const { theme, language } = useSettings();
  const { loading, error } = useData();
  const [activeTab, setActiveTab] = useState('dashboard');

  // Global Record Payment Modal State
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [paymentTargetCustomer, setPaymentTargetCustomer] = useState(null);

  // Receipt Modal State
  const [receiptPayment, setReceiptPayment] = useState(null);
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);

  const handleOpenRecordPaymentCustomer = (customer) => {
    setPaymentTargetCustomer(customer);
    setIsPaymentModalOpen(true);
  };

  return (
    <div
      className={`crm-root min-h-screen text-slate-100 flex flex-col font-sans transition-colors duration-200 ${theme === 'light' ? 'light' : ''}`}
      dir={language === 'ar' ? 'rtl' : 'ltr'}
      lang={language}
    >

      {/* Top Header Navbar */}
      <Navbar />

      {/* Main Layout Container */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Navigation Sidebar */}
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

        {/* Dynamic Route Content View */}
        <main className="flex-1 p-4 lg:p-8 overflow-y-auto max-w-7xl mx-auto w-full">

          {error && (
            <div className="mb-4 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}
          {loading && <p className="text-sm text-slate-400">Loading CRM data...</p>}
          
          {activeTab === 'dashboard' && (
            <DashboardView
              onNavigate={(tab) => setActiveTab(tab)}
            />
          )}

          {activeTab === 'customers' && (
            <CustomerList
              onRecordPaymentForCustomer={(cust) => handleOpenRecordPaymentCustomer(cust)}
            />
          )}

          {activeTab === 'employees' && (
            <EmployeeList />
          )}

          {activeTab === 'billing-payments' && (
            <BillingAndPaymentsView />
          )}

          {activeTab === 'reports' && (
            <ReportsAnalyticsView />
          )}

          {activeTab === 'settings' && (
            <SettingsView />
          )}

        </main>
      </div>

      {/* Global Record Payment Modal */}
      <RecordPaymentModal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        preselectedCustomer={paymentTargetCustomer}
        onPaymentSuccess={(newPayment) => {
          setReceiptPayment(newPayment);
          setIsReceiptOpen(true);
        }}
      />

      {/* Global Receipt Viewer Modal */}
      <ReceiptModal
        isOpen={isReceiptOpen}
        onClose={() => setIsReceiptOpen(false)}
        payment={receiptPayment}
      />

    </div>
  );
}

export default function CrmApp() {
  return (
    <DataProvider>
      <AuthProvider>
        <SettingsProvider>
          <MainApp />
        </SettingsProvider>
      </AuthProvider>
    </DataProvider>
  );
}
