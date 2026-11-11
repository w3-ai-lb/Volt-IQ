import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Mail, ArrowRight, CheckCircle2, KeyRound } from 'lucide-react';
import { AuthLayout } from '@/layouts/AuthLayout';
import { Button } from '@/components/ui/Button';
import { Input, PasswordInput } from '@/components/ui/Input';
import { useToast } from '@/context/ToastContext';
import { authService } from '@/services/api';
import { errorMessage } from '@/utils/errors';
import { t } from '@/i18n/t';

export default function ForgotPasswordPage() {
  const { isAuthenticated, user } = useAuth();
  const toast = useToast();

  const [step, setStep] = useState<'request' | 'reset' | 'done'>('request');
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  /**
   * True when the backend handed the reset token straight back, which it does
   * while no email provider is configured (email delivery is listed as a future
   * enhancement in the architecture). It lets the flow be completed here
   * instead of waiting for a message that will never arrive.
   */
  const [tokenFromServer, setTokenFromServer] = useState(false);

  /**
   * True when the request went through but no token came back, which is the
   * default: there is no email provider, so no reset link is on its way. The
   * page says so instead of telling the customer to check an inbox.
   */
  const [unavailable, setUnavailable] = useState(false);

  const handleRequest = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!email) { setError(t('Email is required')); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError(t('Enter a valid email')); return; }
    setError(undefined);
    setUnavailable(false);
    setLoading(true);
    try {
      const res = await authService.forgotPassword(email);
      if (res.resetToken) {
        setToken(res.resetToken);
        setTokenFromServer(true);
        toast({
          type: 'info',
          title: t('Reset token issued'),
          message: t('Valid for {minutes} minutes. Choose a new password below.')
            .replace('{minutes}', String(res.expiresInMinutes ?? 30)),
        });
        setStep('reset');
      } else {
        setUnavailable(true);
      }
    } catch (err) {
      toast({ type: 'error', title: t('Request failed'), message: errorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!token) { setError(t('Paste the reset token from your email')); return; }
    if (newPassword.length < 6) { setError(t('Password must be at least 6 characters')); return; }
    if (newPassword !== confirm) { setError(t('The two passwords do not match')); return; }
    setError(undefined);
    setLoading(true);
    try {
      await authService.resetPassword(token, newPassword);
      setStep('done');
      toast({ type: 'success', title: t('Password updated'), message: t('You can sign in with your new password.') });
    } catch (err) {
      toast({ type: 'error', title: t('Reset failed'), message: errorMessage(err, 'The link may have expired.') });
    } finally {
      setLoading(false);
    }
  };

  if (isAuthenticated) {
    return <Navigate to={user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard'} replace />;
  }

  if (step === 'done') {
    return (
      <AuthLayout title={t('Password updated')} subtitle={t('Your password has been changed successfully.')}>
        <div className="text-center py-6">
          <div className="w-16 h-16 rounded-2xl bg-emerald-500/15 flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-600" />
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
            {t('You can now sign in to {email} with your new password.')
              .split('{email}')
              .map((part, i) => (i === 0 ? part : (
                <span key={i}><span className="font-semibold text-slate-900 dark:text-slate-100">{email}</span>{part}</span>
              )))}
          </p>
          <Link to="/login"><Button fullWidth>{t('Back to login')}</Button></Link>
        </div>
      </AuthLayout>
    );
  }

  if (step === 'reset') {
    return (
      <AuthLayout title={t('Choose a new password')} subtitle={t('Resetting the password for {email}.').replace('{email}', email)}>
        <form onSubmit={handleReset} className="space-y-4">
          {tokenFromServer ? (
            <div className="rounded-xl border border-warning-500/40 bg-warning-500/10 px-4 py-3 text-xs text-slate-700 dark:text-slate-300">
              {t('Email delivery is not configured yet, so the reset token was issued directly and filled in below. In production it would only be sent to your inbox.')}
            </div>
          ) : (
            <Input
              label={t('Reset token')}
              name="token"
              placeholder={t('Paste the token from your email')}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              leftIcon={<KeyRound className="w-4 h-4" />}
            />
          )}
          <PasswordInput
            label={t('New password')}
            name="newPassword"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <PasswordInput
            label={t('Confirm new password')}
            name="confirmPassword"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={error}
          />
          <Button type="submit" fullWidth loading={loading} rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Update password')}
          </Button>
        </form>
        <p className="mt-6 text-sm text-slate-500 dark:text-slate-400 text-center">
          <button
            type="button"
            onClick={() => { setStep('request'); setError(undefined); }}
            className="font-semibold text-primary-600 hover:text-primary-700"
          >{t('Use a different email')}
          </button>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t('Forgot password')} subtitle={t('Enter the email address of your account.')}>
      {unavailable && (
        <div role="status" className="mb-4 rounded-xl border border-warning-500/40 bg-warning-500/10 px-4 py-3 text-sm text-slate-700 dark:text-slate-300">
          <p className="font-semibold">{t('Reset by email is not available yet')}</p>
          <p className="mt-1">{t('Please contact the provider\'s office to reset your password.')}</p>
        </div>
      )}
      <form onSubmit={handleRequest} className="space-y-4">
        <Input
          label={t('Email')}
          type="email"
          name="email"
          placeholder={t('you@example.com')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={error}
          leftIcon={<Mail className="w-4 h-4" />}
        />
        <Button type="submit" fullWidth loading={loading} rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Continue')}
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400 text-center">
        {t('Remembered your password?')}{' '}
        <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">{t('Sign in')}</Link>
      </p>
    </AuthLayout>
  );
}
