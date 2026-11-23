import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { homeFor, useAuth } from '@/context/AuthContext';

/** The CRM is for the provider's people: administrators, office staff and field staff. */
const STAFF_ROLES = new Set(['admin', 'staff', 'field']);

export function StaffRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (!STAFF_ROLES.has(user?.role ?? '')) return <Navigate to={homeFor(user?.role)} replace />;

  return <>{children}</>;
}
