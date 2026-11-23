import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://unconfigured.invalid';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'unconfigured-publishable-key';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
