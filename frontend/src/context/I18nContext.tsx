import {
  Fragment,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import {
  LANGUAGES,
  directionOf,
  getLanguage,
  isLanguageCode,
  setLanguage as setLanguageStore,
  subscribeLanguage,
  t,
  type LanguageCode,
} from '@/i18n/t';
import { hasSession, profileService } from '@/services/api';

export { LANGUAGES };
export type { LanguageCode };

interface I18nValue {
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
  /** Applies a language that came FROM the server, without saving it back. */
  applyLanguage: (code: LanguageCode) => void;
  t: (text: string) => string;
  direction: 'rtl' | 'ltr';
}

const I18nContext = createContext<I18nValue | undefined>(undefined);

/**
 * Makes the current language available to the tree and, more importantly,
 * forces the tree to redraw when it changes.
 *
 * The `key` on the Fragment is doing real work. `children` arrives as a prop
 * from App and is the same element object on every render, so React would
 * bail out of re-rendering the subtree and half the screen would stay in the
 * previous language. Changing the key remounts it, which is the behaviour a
 * language switch should have anyway: the whole interface changes at once.
 * It happens on a deliberate click in Settings, or once on sign-in, never
 * during normal use.
 *
 * WHY THE LANGUAGE IS SAVED TO THE ACCOUNT
 * ----------------------------------------
 * Because it was previously kept in localStorage alone, which is a property of
 * the browser rather than of the person using it. Choosing Arabic and then
 * signing in as somebody else left that second account reading Arabic, and a
 * brand-new account inherited a language nobody had chosen for it. The theme
 * had already been moved server-side for exactly this reason; this mirrors it.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const language = useSyncExternalStore(subscribeLanguage, getLanguage, getLanguage);

  /**
   * The value we believe is stored on the server, so we only PATCH when the
   * user actually changed something.
   *
   * Tracked as a value rather than a "skip the next save" flag, for the reason
   * spelled out in ThemeContext: a one-shot flag is never cleared when the
   * incoming language happens to equal the current one, because no state change
   * means no effect run, and it then swallows the user's next real change.
   */
  const serverLanguage = useRef<LanguageCode | null>(null);
  const firstRun = useRef(true);

  // On mount, adopt the signed-in user's stored language. This covers a page
  // reload, where there is no sign-in event to carry the value across.
  useEffect(() => {
    if (!hasSession()) return;
    profileService
      .getProfile()
      .then((profile) => {
        if (isLanguageCode(profile?.language)) {
          serverLanguage.current = profile.language;
          setLanguageStore(profile.language);
        }
      })
      .catch(() => {
        /* not signed in, or offline: the cached preference stands */
      });
  }, []);

  useEffect(() => {
    // Also set on first paint, not only when the language changes, so a reader
    // who chose Arabic gets a mirrored page on load rather than a
    // left-to-right flash.
    document.documentElement.lang = language;
    document.documentElement.dir = directionOf(language);

    // Never save on the initial paint: that value came from the cache, and the
    // mount effect above may be about to replace it with the real one.
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    // Signed out, this is only a preference of the browser. The sign-in page
    // belongs to the machine, not to any account, and somebody who reads Arabic
    // should not have to sign in through an English page to get back to it.
    if (!hasSession()) return;
    if (serverLanguage.current === language) return; // already in sync

    serverLanguage.current = language; // optimistic: avoids a duplicate PATCH
    profileService.updateProfile({ language }).catch(() => {
      // Roll back so a later change retries the save.
      serverLanguage.current = null;
    });
  }, [language]);

  const applyLanguage = (code: LanguageCode) => {
    serverLanguage.current = code; // it came from the server, so it is in sync
    setLanguageStore(code);
  };

  const value = useMemo<I18nValue>(
    () => ({
      language,
      setLanguage: setLanguageStore,
      applyLanguage,
      t,
      direction: directionOf(language),
    }),
    [language],
  );

  return (
    <I18nContext.Provider value={value}>
      <Fragment key={language}>{children}</Fragment>
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used inside I18nProvider');
  return context;
}
