import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Mail, User, ArrowRight, Hash, KeyRound } from 'lucide-react';
import { AuthLayout } from '@/layouts/AuthLayout';
import { Button } from '@/components/ui/Button';
import { Input, PasswordInput } from '@/components/ui/Input';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { t } from '@/i18n/t';

export default function RegisterPage() {
  const { register, isAuthenticated, user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  // The account number printed on the customer's bill. This is what links the
  // new login to the meter readings the provider already holds, see the
  // /auth/register docstring in the backend.
  const [customerId, setCustomerId] = useState('');
  // The one-time code the provider issues with the bill. The Customer ID is
  // printed on every bill, so on its own it cannot prove who is registering.
  const [registrationCode, setRegistrationCode] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [agree, setAgree] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ customerId?: string; registrationCode?: string; name?: string; email?: string; password?: string; confirm?: string; agree?: string }>({});

  const validate = () => {
    const e: typeof errors = {};
    if (!customerId) e.customerId = t('Customer ID is required, find it on your bill');
    if (!registrationCode.trim()) e.registrationCode = t('Registration code is required');
    if (!name) e.name = t('Name is required');
    if (!email) e.email = t('Email is required');
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = t('Enter a valid email');
    if (!password) e.password = t('Password is required');
    else if (password.length < 6) e.password = t('Min 6 characters');
    if (confirm !== password) e.confirm = t('Passwords do not match');
    if (!agree) e.agree = t('You must accept the terms');
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!validate()) return;
    setLoading(true);
    try {
      const user = await register(customerId, registrationCode, name, email, password);
      toast({
        type: 'success',
        title: t('Account activated'),
        message: t('Welcome, {name}! Your account {id} is now linked.').replace('{name}', user.name).replace('{id}', user.id),
      });
      navigate('/app/dashboard');
    } catch (error) {
      // Already in the interface language: see utils/errors.ts.
      toast({ type: 'error', title: t('Registration failed'), message: error instanceof Error ? error.message : t('Please try again.') });
    } finally {
      setLoading(false);
    }
  };

  // A redirect is rendered, not called: navigating during render is a state
  // update in the middle of React drawing the page, which it warns about.
  if (isAuthenticated) {
    return <Navigate to={user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard'} replace />;
  }

  return (
    <AuthLayout title={t('Create your account')} subtitle={t('Activate online access to your existing electricity account.')}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label={t('Customer ID')}
          name="customerId"
          // In the format the provider's accounts actually use. "MTR-40118"
          // belonged to the demo data, which the delivered database no longer has.
          placeholder={t('e.g. GEN-00042')}
          hint={t('The account number printed on your electricity bill')}
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          error={errors.customerId}
          leftIcon={<Hash className="w-4 h-4" />}
        />
        <Input
          label={t('Registration code')}
          name="registrationCode"
          placeholder="K7M2QX9P"
          hint={t('The 8-character code on your bill')}
          value={registrationCode}
          onChange={(e) => setRegistrationCode(e.target.value)}
          error={errors.registrationCode}
          leftIcon={<KeyRound className="w-4 h-4" />}
          autoComplete="off"
        />
        <Input label={t('Full name')} name="name" placeholder={t('e.g. Nour Haddad')} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} leftIcon={<User className="w-4 h-4" />} />
        <Input label={t('Email')} type="email" name="email" placeholder={t('you@example.com')} value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} leftIcon={<Mail className="w-4 h-4" />} />
        <PasswordInput label={t('Password')} name="password" placeholder={t('Create a password')} value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
        <PasswordInput label={t('Confirm password')} name="confirm" placeholder={t('Re-enter password')} value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <div>
          <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="w-4 h-4 mt-0.5 rounded border-slate-300 text-primary-600 focus:ring-primary-500" />
            {/* These were <a href="#">, so the customer was asked to accept two
                documents they could not open. Stated as plain text until the
                provider supplies them. */}
            <span>{t('I agree to the provider\'s terms of service and privacy policy.')}</span>
          </label>
          {errors.agree && <p className="mt-1 text-xs text-error-600">{errors.agree}</p>}
        </div>
        <Button type="submit" fullWidth loading={loading} rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Create account')}</Button>
      </form>
      <p className="mt-6 text-sm text-slate-500 dark:text-slate-400 text-center">
        {t('Already have an account?')}{' '}
        <Link to="/login" className="font-semibold text-primary-600 hover:text-primary-700">{t('Sign in')}</Link>
      </p>
    </AuthLayout>
  );
}
