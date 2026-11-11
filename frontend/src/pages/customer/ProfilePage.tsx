import { useEffect, useState, type FormEvent } from 'react';
import { User, Mail, Phone, MapPin, Lock, Save } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input, PasswordInput } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { useAuth } from '@/context/AuthContext';
import { authService, profileService } from '@/services/api';
import { useToast } from '@/context/ToastContext';
import { errorMessage } from '@/utils/errors';
import { t } from '@/i18n/t';

export default function ProfilePage() {
  const { user, updateProfile } = useAuth();
  const toast = useToast();
  const [form, setForm] = useState({ name: '', email: '', phone: '', address: '' });
  const [pwd, setPwd] = useState({ current: '', next: '', confirm: '' });
  const [loading, setLoading] = useState(false);
  const [pwdLoading, setPwdLoading] = useState(false);

  useEffect(() => {
    if (user) setForm({ name: user.name, email: user.email, phone: user.phone ?? '', address: user.address ?? '' });
  }, [user]);

  const handleProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { toast({ type: 'error', title: t('Name is required') }); return; }
    setLoading(true);
    try {
      // Persist to the database, then mirror the saved values locally so the
      // header and sidebar update. Previously this only wrote to localStorage,
      // so edits vanished on any device that cleared its cache.
      const saved = await profileService.updateProfile(form);
      updateProfile({
        name: saved.name,
        email: saved.email,
        phone: saved.phone ?? '',
        address: saved.address ?? '',
      });
      toast({ type: 'success', title: t('Profile updated'), message: t('Your changes have been saved.') });
    } catch (error) {
      toast({ type: 'error', title: t('Could not save'), message: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  };

  const handlePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!pwd.current) { toast({ type: 'error', title: t('Enter your current password') }); return; }
    if (pwd.next !== pwd.confirm) { toast({ type: 'error', title: t('Passwords do not match') }); return; }
    if (pwd.next.length < 6) { toast({ type: 'error', title: t('Password too short'), message: t('Use at least 6 characters.') }); return; }

    setPwdLoading(true);
    try {
      await authService.changePassword(pwd.current, pwd.next);
      setPwd({ current: '', next: '', confirm: '' });
      toast({ type: 'success', title: t('Password changed'), message: t('Your other devices have been signed out.') });
    } catch (error) {
      // The fields are deliberately left filled so the user can correct them.
      toast({ type: 'error', title: t('Could not change password'), message: errorMessage(error) });
    } finally {
      setPwdLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={t('Profile')}
        description={t('Manage your personal information and password.')}
        breadcrumb={[
          // The page is shared by both roles, so the crumb has to lead back to
          // the dashboard the signed-in user actually has.
          { label: t('Dashboard'), href: user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard' },
          { label: t('Profile') },
        ]}
      />

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="p-6 text-center">
          <div className="w-20 h-20 rounded-2xl bg-gradient-primary flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4">
            {user?.name?.charAt(0) ?? 'U'}
          </div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{user?.name}</h3>
          <p className="text-sm text-slate-500">{user?.email}</p>
          <div className="mt-4 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-600 text-xs font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />{t('Active account')}
          </div>
          <div className="mt-6 pt-6 border-t border-slate-100 dark:border-slate-800 text-start space-y-3 text-sm">
            <div className="flex items-center gap-2 text-slate-500"><Phone className="w-4 h-4" /> {form.phone || t('No phone set')}</div>
            <div className="flex items-center gap-2 text-slate-500"><MapPin className="w-4 h-4" /> {form.address || t('No address set')}</div>
          </div>
        </Card>

        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardBody>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Personal Information')}</h3>
              <form onSubmit={handleProfile} className="space-y-4">
                <Input label={t('Full name')} name="name" autoComplete="name" leftIcon={<User className="w-4 h-4" />} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <Input label={t('Email')} name="email" type="email" autoComplete="email" leftIcon={<Mail className="w-4 h-4" />} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                <Input label={t('Phone')} name="phone" autoComplete="tel" leftIcon={<Phone className="w-4 h-4" />} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                <Input label={t('Address')} name="address" autoComplete="street-address" leftIcon={<MapPin className="w-4 h-4" />} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
                <Button type="submit" loading={loading} leftIcon={<Save className="w-4 h-4" />}>{t('Save changes')}</Button>
              </form>
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Change Password')}</h3>
              <form onSubmit={handlePassword} className="space-y-4">
                <PasswordInput label={t('Current password')} name="current-password" autoComplete="current-password" leftIcon={<Lock className="w-4 h-4" />} value={pwd.current} onChange={(e) => setPwd({ ...pwd, current: e.target.value })} />
                <div className="grid sm:grid-cols-2 gap-4">
                  <PasswordInput label={t('New password')} name="new-password" autoComplete="new-password" value={pwd.next} onChange={(e) => setPwd({ ...pwd, next: e.target.value })} />
                  <PasswordInput label={t('Confirm new password')} name="confirm-password" autoComplete="new-password" value={pwd.confirm} onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} />
                </div>
                <Button type="submit" variant="outline" loading={pwdLoading}>{t('Update password')}</Button>
              </form>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
