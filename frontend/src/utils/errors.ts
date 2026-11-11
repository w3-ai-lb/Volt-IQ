import { t } from '@/i18n/t';

/**
 * The message to show for a failed request, in the interface language.
 *
 * The backend explains a refusal in `detail`, in English like every API
 * message. The ones a user can meet (a wrong password, too many attempts, an
 * email already in use) are catalogue keys, so they appear translated; any
 * other is shown as sent rather than hidden. This replaces three copies of the
 * same function that each returned the English text untouched.
 */
export function errorMessage(error: unknown, fallback = 'Please try again.'): string {
  const err = error as { response?: { data?: { detail?: unknown } }; code?: string } | null;
  if (err?.code === 'ERR_NETWORK') {
    return t('Cannot reach the server. Make sure the backend is running.');
  }
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return t(detail);
  return t(fallback);
}
