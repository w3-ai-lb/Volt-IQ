import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, Home, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/context/AuthContext';
import { t } from '@/i18n/t';

export default function NotFoundPage() {
  const { isAuthenticated, user } = useAuth();
  const home = isAuthenticated ? (user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard') : '/';

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4 bg-grid">
      <div className="text-center max-w-md">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="inline-flex items-center justify-center w-20 h-20 rounded-3xl bg-gradient-primary shadow-glow mb-6">
          <Zap className="w-10 h-10 text-white" />
        </motion.div>
        <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="text-7xl font-extrabold text-gradient-primary">404</motion.h1>
        <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mt-3 text-xl font-semibold text-slate-900 dark:text-slate-100">{t('Page not found')}</motion.p>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="mt-2 text-sm text-slate-500 dark:text-slate-400">{t('The page you\'re looking for doesn\'t exist or has been moved.')}</motion.p>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="mt-8 flex items-center justify-center gap-3">
          <Link to={home}><Button leftIcon={<Home className="w-4 h-4" />}>{t('Go home')}</Button></Link>
          <Link to="/"><Button variant="outline" leftIcon={<ArrowLeft className="w-4 h-4 rtl:-scale-x-100" />}>{t('Back to site')}</Button></Link>
        </motion.div>
      </div>
    </div>
  );
}
