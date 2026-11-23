import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { hasSession, profileService } from '@/services/api';

type Theme = 'light' | 'dark';

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
  /** Applies a theme that came FROM the server, without saving it back. */
  applyTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEY = 'energy-theme';

function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark';
}

/**
 * The theme lives in TWO places, deliberately:
 *
 *  - localStorage, read synchronously on first paint, so the page never
 *    flashes the wrong colour while the real preference loads.
 *  - the database (customers.theme), so the choice follows the user to any
 *    browser or device, and two people sharing a computer each keep their own.
 *
 * localStorage is the fast cache; the database is the source of truth.
 */
function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isTheme(stored)) return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  /**
   * The value we believe is stored on the server, so we only PATCH when the
   * user actually changes something.
   *
   * This is tracked as a value rather than a "skip the next save" flag on
   * purpose: a one-shot flag set by applyTheme() is never cleared when the
   * incoming theme happens to equal the current one (no state change means no
   * effect run), and it then swallows the user's next real toggle.
   */
  const serverTheme = useRef<Theme | null>(null);
  const firstRun = useRef(true);

  // On mount, adopt the signed-in user's stored theme. This covers a page
  // reload, where there is no login event to carry the value across.
  useEffect(() => {
    if (!hasSession()) return;
    profileService
      .getProfile()
      .then((profile) => {
        if (isTheme(profile?.theme)) {
          serverTheme.current = profile.theme;
          setThemeState(profile.theme);
        }
      })
      .catch(() => {
        /* not signed in, or offline, the cached preference stands */
      });
  }, []);

  // Apply to the DOM, cache locally, and persist when the user changed it.
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') root.classList.add('dark');
    else root.classList.remove('dark');
    window.localStorage.setItem(STORAGE_KEY, theme);

    // Never save on the initial paint, that value came from the cache, and
    // the mount effect above may be about to replace it with the real one.
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    if (!hasSession()) return;
    if (serverTheme.current === theme) return; // already in sync

    serverTheme.current = theme; // optimistic: avoids a duplicate PATCH
    profileService.updateProfile({ theme }).catch(() => {
      // Roll back so a later change retries the save.
      serverTheme.current = null;
    });
  }, [theme]);

  const setTheme = (t: Theme) => setThemeState(t);
  const toggleTheme = () => setThemeState((p) => (p === 'light' ? 'dark' : 'light'));

  const applyTheme = (t: Theme) => {
    serverTheme.current = t; // it came from the server, so it is already in sync
    setThemeState(t);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme, applyTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
