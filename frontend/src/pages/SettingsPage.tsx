import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Moon, Sun, Globe, Bell, Shield, Check, KeyRound } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { preferencesService, type NotificationPreferences } from '@/services/api';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { useTheme } from '@/context/ThemeContext';
import { useToast } from '@/context/ToastContext';
import { useAuth } from '@/context/AuthContext';
import { LANGUAGES, useI18n, type LanguageCode } from '@/context/I18nContext';
import { classNames } from '@/utils/helpers';
import { t } from '@/i18n/t';

function Toggle({ on, onClick, label, disabled = false }: { on: boolean; onClick: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={classNames(
        'relative w-11 h-6 rounded-full transition disabled:opacity-50',
        on ? 'bg-primary-600' : 'bg-slate-300 dark:bg-slate-700',
      )}
    >
      <span className={classNames(
        'absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform',
        // The knob slides along the reading direction, so in Arabic it has to
        // travel the other way. Without the rtl: variants it would slide off
        // the switch entirely.
        on ? 'translate-x-5 rtl:-translate-x-5' : 'translate-x-0.5 rtl:-translate-x-0.5',
      )} />
    </button>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { user } = useAuth();
  const toast = useToast();
  // The real setting, not a local copy: this writes through to the store that
  // t() reads, so choosing a language redraws the whole interface at once. It
  // used to be plain useState that nothing else ever read, which is why the
  // control looked alive and changed nothing.
  const { language, setLanguage } = useI18n();
  /**
   * The notification switches, loaded from and saved to the server.
   *
   * They used to be `useState` with hardcoded defaults and a Save button that
   * only raised a toast: nothing was stored, nothing read them, and the choice
   * was gone on the next page load. Each one now corresponds to a signal of
   * the alert engine, so turning one off stops those alerts being generated.
   */
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    preferencesService.getNotifications().then(setPrefs).catch(() => setPrefs(null));
  }, []);

  const togglePref = (key: keyof NotificationPreferences) =>
    setPrefs((current) => (current ? { ...current, [key]: !current[key] } : current));

  const handleSave = async () => {
    if (!prefs) return;
    setSaving(true);
    try {
      const saved = await preferencesService.updateNotifications(prefs);
      setPrefs(saved);
      toast({ type: 'success', title: t('Settings saved'), message: t('Your notification choices have been stored.') });
    } catch {
      toast({ type: 'error', title: t('Could not save'), message: t('Please try again.') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader title={t('Settings')} description={t('Manage your preferences, notifications, and security.')} breadcrumb={[{ label: t('Dashboard'), href: user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard' }, { label: t('Settings') }]} />

      <div className="space-y-6 max-w-3xl">
        <Card>
          <CardBody>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-primary-500/15 flex items-center justify-center">{theme === 'dark' ? <Moon className="w-5 h-5 text-primary-600" /> : <Sun className="w-5 h-5 text-primary-600" />}</div>
              <div><h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Theme')}</h3><p className="text-sm text-slate-500">{t('Choose how VoltIQ looks to you.')}</p></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {/* Named `mode`, not `t`: a parameter called t would shadow the
                  translation function imported at the top of this file. */}
              {(['light', 'dark'] as const).map((mode) => (
                <button key={mode} onClick={() => setTheme(mode)} className={classNames('flex items-center gap-3 p-4 rounded-xl border-2 transition', theme === mode ? 'border-primary-600 bg-primary-50 dark:bg-primary-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-slate-300')}>
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-slate-100 dark:bg-slate-800">{mode === 'light' ? <Sun className="w-4 h-4 text-warning-500" /> : <Moon className="w-4 h-4 text-primary-400" />}</div>
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{mode === 'light' ? t('Light') : t('Dark')}</span>
                  {theme === mode && <Check className="w-4 h-4 text-primary-600 ms-auto" />}
                </button>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center"><Globe className="w-5 h-5 text-emerald-600" /></div>
              <div><h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Language')}</h3><p className="text-sm text-slate-500">{t('Select your preferred language.')}</p></div>
            </div>
            <select
              id="language"
              value={language}
              onChange={(e) => {
                setLanguage(e.target.value as LanguageCode);
                toast({ type: 'success', title: t('Language changed') });
              }}
              aria-label={t('Language')}
              className="input-base max-w-xs"
            >
              {/* Each option is written in its own language, which is the
                  convention: someone who cannot read the current language can
                  still find their own in the list. */}
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-warning-500/15 flex items-center justify-center"><Bell className="w-5 h-5 text-warning-600" /></div>
              <div><h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Notification Preferences')}</h3><p className="text-sm text-slate-500">{t('Choose what you want to be notified about.')}</p></div>
            </div>
            {/* Four categories, because those are the four signals the alert
                engine actually produces. Delivery by email, SMS or push is not
                offered here: Architecture Section XI defers outbound email to
                a later version, so a switch for it would control nothing. */}
            <div className="space-y-1">
              {[
                { key: 'highUsage' as const, label: t('High usage alerts'), desc: t('When your consumption runs above your own recent normal') },
                { key: 'billReminders' as const, label: t('Bill reminders'), desc: t('When a bill is due or already overdue') },
                { key: 'anomalies' as const, label: t('Unusual consumption alerts'), desc: t('When a reading does not fit your established pattern') },
                { key: 'savingsMilestones' as const, label: t('Savings milestones'), desc: t('When your consumption falls against your baseline') },
              ].map((n) => (
                <div key={n.key} className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-800 last:border-0">
                  <div><p className="text-sm font-medium text-slate-900 dark:text-slate-100">{n.label}</p><p className="text-xs text-slate-500">{n.desc}</p></div>
                  <Toggle on={prefs?.[n.key] ?? true} label={n.label} disabled={!prefs} onClick={() => togglePref(n.key)} />
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-4">
              {t('Alerts appear on your Alerts page. Delivery by email and SMS is planned for a later version.')}
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-error-500/15 flex items-center justify-center"><Shield className="w-5 h-5 text-error-600" /></div>
              <div><h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Security')}</h3><p className="text-sm text-slate-500">{t('Protect your account with extra security.')}</p></div>
            </div>
            {/* A two-factor switch and a "Manage active sessions" button used to
                sit here. Neither had any backend: the switch raised a toast and
                no code was ever required at sign-in. Replaced by the control
                that does exist, rather than left as decoration. */}
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{t('Password')}</p>
                <p className="text-xs text-slate-500">{t('Changing it signs out every other device.')}</p>
              </div>
              <Link to={user?.role === 'admin' ? '/admin/profile' : '/app/profile'}>
                <Button variant="outline" leftIcon={<KeyRound className="w-4 h-4" />}>{t('Change Password')}</Button>
              </Link>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              {t('Sessions expire after eight hours. Two-factor authentication is a planned enhancement.')}
            </p>
          </CardBody>
        </Card>

        <div className="flex justify-end">
          <Button onClick={handleSave} loading={saving} disabled={!prefs}>{t('Save settings')}</Button>
        </div>
      </div>
    </div>
  );
}
