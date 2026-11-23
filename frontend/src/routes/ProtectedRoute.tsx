import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

export function ProtectedRoute({ children, role }: { children: ReactNode; role?: 'customer' | 'admin' }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;

  if (role && user?.role !== role) {
    return <Navigate to={user?.role === 'admin' ? '/admin/dashboard' : '/app/dashboard'} replace />;
  }

  return <>{children}</>;
}
