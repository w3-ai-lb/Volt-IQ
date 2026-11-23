import React, { createContext, useContext, useState, useEffect } from 'react';

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
    pricePerKwh: 'Electricity Tariff Rate ($/kWh)',
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
    pricePerKwh: 'تعرفة سعر الكيلوواط ($/kWh)',
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

export function SettingsProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('gridpower_theme') || 'dark';
  });

  const [language, setLanguage] = useState(() => {
    return localStorage.getItem('gridpower_lang') || 'en';
  });

  const [kwhPrice, setKwhPrice] = useState(() => {
    const saved = localStorage.getItem('gridpower_kwh_price');
    return saved ? parseFloat(saved) : 0.18;
  });

  useEffect(() => {
    localStorage.setItem('gridpower_theme', theme);
    const root = document.documentElement;
    if (theme === 'light') {
      root.classList.add('light');
    } else {
      root.classList.remove('light');
    }
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('gridpower_lang', language);
    const root = document.documentElement;
    root.setAttribute('dir', language === 'ar' ? 'rtl' : 'ltr');
    root.setAttribute('lang', language);
  }, [language]);

  useEffect(() => {
    localStorage.setItem('gridpower_kwh_price', String(kwhPrice));
  }, [kwhPrice]);

  const t = (key) => {
    return TRANSLATIONS[language]?.[key] || TRANSLATIONS.en[key] || key;
  };

  return (
    <SettingsContext.Provider value={{
      theme,
      setTheme,
      language,
      setLanguage,
      kwhPrice,
      setKwhPrice,
      t
    }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
