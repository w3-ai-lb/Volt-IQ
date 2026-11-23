import { DashboardLayout } from '@/layouts/DashboardLayout';

/**
 * Dedicated entry point for administrator routes. The shared layout supplies
 * the responsive left navigation, header controls, and route outlet; the
 * administrator mode selects the admin-only navigation menu.
 */
export function AdminLayout() {
  return <DashboardLayout role="admin" />;
}
