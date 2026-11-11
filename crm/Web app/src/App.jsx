import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DataProvider } from './context/DataContext';
import { SettingsProvider, useSettings } from './context/SettingsContext';
import Navbar from './components/layout/Navbar';
import Sidebar from './components/layout/Sidebar';
import LoginPage from './components/auth/LoginPage';
import DashboardView from './components/dashboard/DashboardView';
import CustomerList from './components/customers/CustomerList';
import EmployeeList from './components/employees/EmployeeList';
import BillingAndPaymentsView from './components/billing-payments/BillingAndPaymentsView';
import ReportsAnalyticsView from './components/reports/ReportsAnalyticsView';
import SettingsView from './components/settings/SettingsView';
import RecordPaymentModal from './components/payments/RecordPaymentModal';
import ReceiptModal from './components/payments/ReceiptModal';

function MainApp() {
  const { isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');

  // Global Record Payment Modal State
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [paymentTargetCustomer, setPaymentTargetCustomer] = useState(null);

  // Receipt Modal State
  const [receiptPayment, setReceiptPayment] = useState(null);
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  const handleOpenRecordPaymentCustomer = (customer) => {
    setPaymentTargetCustomer(customer);
    setIsPaymentModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col font-sans transition-colors duration-200">
      
      {/* Top Header Navbar */}
      <Navbar />

      {/* Main Layout Container */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Navigation Sidebar */}
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

        {/* Dynamic Route Content View */}
        <main className="flex-1 p-4 lg:p-8 overflow-y-auto max-w-7xl mx-auto w-full">
          
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

export default function App() {
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
