import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { homeFor, useAuth } from '@/context/AuthContext';

export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (user?.role !== 'admin') return <Navigate to={homeFor(user?.role)} replace />;

  return <>{children}</>;
}
