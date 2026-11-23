import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, ArrowRight } from 'lucide-react';
import { AuthLayout } from '@/layouts/AuthLayout';
import { Button } from '@/components/ui/Button';
import { Input, PasswordInput } from '@/components/ui/Input';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { t } from '@/i18n/t';

export default function LoginPage() {
  const { login, isAuthenticated, user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});

  const validate = () => {
    const e: typeof errors = {};
    if (!email) e.email = t('Email is required');
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = t('Enter a valid email');
    if (!password) e.password = t('Password is required');
    else if (password.length < 6) e.password = t('Min 6 characters');
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!validate()) return;
    setLoading(true);
    try {
      const user = await login(email, password, remember);
      toast({ type: 'success', title: t('Welcome back!'), message: t('Signed in as {name}').replace('{name}', user.name) });
      navigate(user.role === 'admin' ? '/admin/dashboard' : '/app/dashboard');
    } catch (error) {
      // Show what actually went wrong. Only suggest the demo accounts when the
      // credentials themselves were rejected, offering them when the server is
      // unreachable sends the user chasing a password problem that isn't there.
      // The message arrives already in the interface language (utils/errors.ts),
      // so it is compared with the translated refusal, not searched for a word.
      const message = error instanceof Error ? error.message : t('Please try again.');
      const badCredentials = message === t('Invalid credentials');
      toast({
        type: 'error',
        title: t('Sign in failed'),
        // The demo credentials that used to be printed here (admin@nxttrn.com /
        // admin123) no longer exist once the invented data is removed, so the
        // message was telling people to sign in with accounts that are gone, 
        // and publishing a default administrator password on the sign-in screen
        // is not something to keep once the system holds real customer records.
        message: badCredentials
          // Registering takes the registration code as well as the Customer ID.
          ? t('Invalid email or password. If you have not registered yet, activate your account with the Customer ID and registration code printed on your bill.')
          : message,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      navigate(user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard', { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  return (
    <AuthLayout title={t('Welcome back')} subtitle={t('Sign in to your VoltIQ account to continue.')}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label={t('Email')}
          type="email"
          name="email"
          placeholder={t('you@example.com')}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          leftIcon={<Mail className="w-4 h-4" />}
          autoComplete="email"
        />
        <PasswordInput
          label={t('Password')}
          name="password"
          placeholder={t('Enter your password')}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500" />{t('Remember me')}
          </label>
          <Link to="/forgot-password" className="text-sm font-medium text-primary-600 hover:text-primary-700">{t('Forgot password?')}</Link>
        </div>
        <Button type="submit" fullWidth loading={loading} rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Sign in')}</Button>
      </form>
      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400 text-center">
        {t('Don\'t have an account?')}{' '}
        <Link to="/register" className="font-semibold text-primary-600 hover:text-primary-700">{t('Sign up')}</Link>
      </p>
      {/* The line that used to sit here told the visitor that an email
          containing "admin" would open the admin dashboard. That was true of
          the mock login this page replaced; it has not been true since
          authentication moved to the backend, where the role comes from the
          account record and no email string can grant it. Removed rather than
          translated: there is no point saying something false in six
          languages. */}
    </AuthLayout>
  );
}
