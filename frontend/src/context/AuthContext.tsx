import { createContext, useContext, useState, type ReactNode } from 'react';
import { authService } from '@/services/api';
import { useTheme } from '@/context/ThemeContext';
import { useI18n } from '@/context/I18nContext';
import { isLanguageCode } from '@/i18n/t';
import { errorMessage } from '@/utils/errors';

// 'staff' (office) and 'field' (meter readers) are the CRM roles added when the
// CRM joined the platform; they open /crm, never the customer or admin pages.
export type UserRole = 'customer' | 'admin' | 'staff' | 'field';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
  phone?: string;
  address?: string;
  theme?: 'light' | 'dark';
  language?: string;
}

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string, remember?: boolean) => Promise<User>;
  register: (customerId: string, registrationCode: string, name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
  updateProfile: (patch: Partial<User>) => void;
}

/** Where each role lands after signing in. */
export function homeFor(role?: string): string {
  if (role === 'admin') return '/admin/dashboard';
  if (role === 'staff' || role === 'field') return '/crm';
  return '/app/dashboard';
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_KEY = 'energy-user';
const TOKEN_KEY = 'energy-token';

/**
 * Where the session is kept.
 *
 * `localStorage` survives closing the browser; `sessionStorage` does not.
 * That distinction is what "Remember me" on the sign-in page now means. The
 * checkbox previously set a state variable that nothing read, so the session
 * was persisted either way and unticking it changed nothing.
 */
function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

/** Removes the session from both stores, so switching modes cannot leave a stale copy. */
function clearStoredSession(): void {
  for (const store of [localStorage, sessionStorage]) {
    try {
      store.removeItem(STORAGE_KEY);
      store.removeItem(TOKEN_KEY);
    } catch {
      // Storage can be unavailable in private browsing; signing out still works.
    }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(getStoredUser);
  const { applyTheme } = useTheme();
  const { applyLanguage } = useI18n();

  /**
   * Switch the interface to the preferences that belong to the account that
   * just signed in.
   *
   * Both are stored per account, so neither may be left over from whoever used
   * this browser last. `applyTheme` and `applyLanguage` set the value without
   * saving it back, because it is what the server already holds.
   */
  const adoptPreferences = (u: User) => {
    if (u.theme === 'light' || u.theme === 'dark') applyTheme(u.theme);
    // Changing the language remounts the tree below I18nProvider, which is why
    // BrowserRouter sits above it in App: the navigation that follows sign-in
    // has to outlive this call.
    if (isLanguageCode(u.language)) applyLanguage(u.language);
  };

  const persist = (u: User | null, token?: string, remember = true) => {
    setUser(u);
    if (!u) {
      clearStoredSession();
      return;
    }
    // Write to one store and clear the other, so an unticked "Remember me"
    // cannot leave yesterday's persistent session behind it.
    clearStoredSession();
    const store = remember ? localStorage : sessionStorage;
    store.setItem(STORAGE_KEY, JSON.stringify(u));
    if (token) store.setItem(TOKEN_KEY, token);
  };

  /**
   * Authenticates against POST /auth/login.
   * Credentials are verified by the backend (bcrypt) and a real JWT is
   * returned, the previous hard-coded check has moved server-side.
   */
  const login: AuthContextValue['login'] = async (email, password, remember = true) => {
    try {
      const res = await authService.login(email, password);
      const u = res.user as unknown as User;
      persist(u, res.token, remember);
      adoptPreferences(u);
      return u;
    } catch (error) {
      // Already in the interface language: see utils/errors.ts.
      throw new Error(errorMessage(error, 'Invalid credentials'));
    }
  };

  const register: AuthContextValue['register'] = async (customerId, registrationCode, name, email, password) => {
    try {
      const res = await authService.register(customerId, registrationCode, name, email, password);
      const u = res.user as unknown as User;
      persist(u, res.token);
      adoptPreferences(u);
      return u;
    } catch (error) {
      throw new Error(errorMessage(error, 'Registration failed'));
    }
  };

  const logout = () => persist(null);

  const updateProfile: AuthContextValue['updateProfile'] = (patch) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...patch };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: !!user, login, register, logout, updateProfile }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
