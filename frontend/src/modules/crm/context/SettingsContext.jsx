import React, { createContext, useContext, useState, useEffect } from 'react';
import { useData } from './DataContext';

const SettingsContext = createContext();

export const TRANSLATIONS = {
  en: {
    dashboard: 'Dashboard',
    customerManagement: 'Customer Management',
    employeeManagement: 'Employee Management',
    billingPayments: 'Billing & Payments',
    reports: 'Reports & Analytics',
    settings: 'Settings',
    systemSettings: 'System Settings & Preferences',
    theme: 'App Theme Display',
    lightMode: 'Light Mode',
    darkMode: 'Dark Mode',
    language: 'System Language',
    english: 'English (US)',
    arabic: 'Arabic (العربية)',
    pricePerKwh: 'Electricity tariff (per kWh)',
    notifications: 'Notifications',
    markAllRead: 'Mark all as read',
    noNotifications: 'No recent notifications',
    signOut: 'Sign Out',
    totalCustomers: 'Total Customers',
    totalRevenue: 'Total Revenue Collected',
    outstandingPayments: 'Outstanding Payments',
    electricityConsumption: 'Electricity Consumption',
    recordPayment: 'Record Payment',
    customerDirectory: 'Customer Directory',
    employeeDirectory: 'Employee Directory',
    saveChanges: 'Save Changes'
  },
  ar: {
    dashboard: 'لوحة التحكم',
    customerManagement: 'إدارة العملاء',
    employeeManagement: 'إدارة الموظفين',
    billingPayments: 'الفواتير والمدفوعات',
    reports: 'التقارير والتحليلات',
    settings: 'الإعدادات',
    systemSettings: 'إعدادات النظام والتفضيلات',
    theme: 'مظهر التطبيق',
    lightMode: 'الوضع الفاتح',
    darkMode: 'الوضع الداكن',
    language: 'لغة النظام',
    english: 'الإنجليزية (US)',
    arabic: 'العربية',
    pricePerKwh: 'تعرفة الكيلوواط ساعة',
    notifications: 'الإشعارات',
    markAllRead: 'تحديد الكل كمعلوم',
    noNotifications: 'لا توجد إشعارات حديثة',
    signOut: 'تسجيل الخروج',
    totalCustomers: 'إجمالي العملاء',
    totalRevenue: 'إجمالي الإيرادات المحصلة',
    outstandingPayments: 'المدفوعات المستحقة',
    electricityConsumption: 'استهلاك الكهرباء',
    recordPayment: 'تسجيل دفعة',
    customerDirectory: 'دليل العملاء',
    employeeDirectory: 'دليل الموظفين',
    saveChanges: 'حفظ التغييرات'
  }
};

// Theme and language apply to the CRM screens only (the class and the
// direction are set on the CRM's own root element, see CrmApp.jsx), so they
// never fight with the rest of the web app. The tariff comes from the backend.
export function SettingsProvider({ children }) {
  const { tariff } = useData();

  const [theme, setTheme] = useState(() => readPref('voltiq_crm_theme', 'dark'));
  const [language, setLanguage] = useState(() => readPref('voltiq_crm_lang', 'en'));
  const [kwhPrice, setKwhPrice] = useState(0);

  useEffect(() => {
    if (tariff?.ratePerKwh) setKwhPrice(tariff.ratePerKwh);
  }, [tariff?.ratePerKwh]);

  useEffect(() => writePref('voltiq_crm_theme', theme), [theme]);
  useEffect(() => writePref('voltiq_crm_lang', language), [language]);

  const t = (key) => TRANSLATIONS[language]?.[key] || TRANSLATIONS.en[key] || key;

  return (
    <SettingsContext.Provider value={{ theme, setTheme, language, setLanguage, kwhPrice, setKwhPrice, t }}>
      {children}
    </SettingsContext.Provider>
  );
}

function readPref(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function writePref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private window): the choice lasts for this visit only.
  }
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
