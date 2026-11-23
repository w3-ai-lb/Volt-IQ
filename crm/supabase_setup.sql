-- ============================================================
-- SMART UTILITY CRM - COMPLETE ALL-IN-ONE SUPABASE SQL SCRIPT
-- ============================================================
-- Copy and paste this ENTIRE script into Supabase SQL Editor:
-- https://supabase.com/dashboard/project/pzwwssovyuugboseqntc/sql/new
--
-- This script creates all 11 tables, indexes, grants permissions,
-- and configures RLS policies so Web and Mobile apps work 100%.
-- ============================================================

-- CLEANUP OLD TABLES IF RE-CREATING
DROP TABLE IF EXISTS public.payments CASCADE;
DROP TABLE IF EXISTS public.invoices CASCADE;
DROP TABLE IF EXISTS public.tariffs CASCADE;
DROP TABLE IF EXISTS public.meter_readings CASCADE;
DROP TABLE IF EXISTS public.meters CASCADE;
DROP TABLE IF EXISTS public.employee_subscriber_assignments CASCADE;
DROP TABLE IF EXISTS public.subscriptions CASCADE;
DROP TABLE IF EXISTS public.generators CASCADE;
DROP TABLE IF EXISTS public.subscribers CASCADE;
DROP TABLE IF EXISTS public.employees CASCADE;
DROP TABLE IF EXISTS public.zones CASCADE;

-- 1. ZONES
CREATE TABLE public.zones (
    zone_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    area_type VARCHAR(20) CHECK (area_type IN ('urban', 'rural')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. EMPLOYEES
CREATE TABLE public.employees (
    employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30),
    role VARCHAR(30) NOT NULL CHECK (role IN ('admin', 'office_staff', 'field_employee', 'collector')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. SUBSCRIBERS / CUSTOMERS
CREATE TABLE public.subscribers (
    subscriber_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30),
    address TEXT,
    zone_id UUID REFERENCES public.zones(zone_id) ON DELETE SET NULL,
    gps_lat DECIMAL(10,7),
    gps_lng DECIMAL(10,7),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. GENERATORS
CREATE TABLE public.generators (
    generator_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id UUID REFERENCES public.zones(zone_id) ON DELETE SET NULL,
    name_code VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. SUBSCRIPTIONS
CREATE TABLE public.subscriptions (
    subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscriber_id UUID NOT NULL REFERENCES public.subscribers(subscriber_id) ON DELETE CASCADE,
    generator_id UUID REFERENCES public.generators(generator_id) ON DELETE RESTRICT,
    subscription_code VARCHAR(50) UNIQUE,
    ampere_capacity INTEGER DEFAULT 10 CHECK (ampere_capacity > 0),
    billing_model VARCHAR(20) NOT NULL DEFAULT 'metered' CHECK (billing_model IN ('metered', 'flat_rate')),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'disconnected', 'terminated')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. EMPLOYEE SUBSCRIBER ASSIGNMENTS
CREATE TABLE public.employee_subscriber_assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
    subscriber_id UUID NOT NULL REFERENCES public.subscribers(subscriber_id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    UNIQUE(employee_id, subscriber_id)
);

-- 7. METERS
CREATE TABLE public.meters (
    meter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID REFERENCES public.subscriptions(subscription_id) ON DELETE CASCADE,
    serial_number VARCHAR(100) NOT NULL UNIQUE,
    meter_type VARCHAR(20) NOT NULL DEFAULT 'analog' CHECK (meter_type IN ('analog', 'digital', 'smart')),
    initial_reading DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (initial_reading >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'replaced', 'faulty')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. METER READINGS
CREATE TABLE public.meter_readings (
    reading_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meter_id UUID REFERENCES public.meters(meter_id) ON DELETE CASCADE,
    reading_value DECIMAL(15,3) NOT NULL CHECK (reading_value >= 0),
    reading_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ocr_raw_value DECIMAL(15,3),
    ocr_confidence DECIMAL(5,4) CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)),
    was_corrected BOOLEAN NOT NULL DEFAULT FALSE,
    photo_url TEXT,
    captured_by UUID REFERENCES public.employees(employee_id) ON DELETE RESTRICT,
    is_validated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. TARIFFS
CREATE TABLE public.tariffs (
    tariff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    effective_month DATE NOT NULL UNIQUE,
    rate_per_kwh DECIMAL(15,3) NOT NULL CHECK (rate_per_kwh >= 0),
    fixed_fee DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (fixed_fee >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency IN ('LBP', 'USD')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. INVOICES
CREATE TABLE public.invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID REFERENCES public.subscriptions(subscription_id) ON DELETE RESTRICT,
    tariff_id UUID REFERENCES public.tariffs(tariff_id) ON DELETE RESTRICT,
    billing_period DATE NOT NULL,
    previous_reading_id UUID REFERENCES public.meter_readings(reading_id) ON DELETE SET NULL,
    current_reading_id UUID REFERENCES public.meter_readings(reading_id) ON DELETE SET NULL,
    units_consumed DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (units_consumed >= 0),
    fixed_charge DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (fixed_charge >= 0),
    variable_charge DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (variable_charge >= 0),
    total_amount DECIMAL(15,3) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency IN ('LBP', 'USD')),
    status VARCHAR(30) NOT NULL DEFAULT 'issued' CHECK (status IN ('draft', 'issued', 'partially_paid', 'paid', 'overdue', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. PAYMENTS
CREATE TABLE public.payments (
    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID REFERENCES public.invoices(invoice_id) ON DELETE CASCADE,
    amount DECIMAL(15,3) NOT NULL CHECK (amount > 0),
    payment_method VARCHAR(30) NOT NULL CHECK (payment_method IN ('cash', 'bank_transfer', 'whish', 'omt', 'credit_card', 'other')),
    payment_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    collected_by UUID REFERENCES public.employees(employee_id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'cancelled')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- INDEXES
CREATE INDEX idx_employees_auth_user ON public.employees(auth_user_id);
CREATE INDEX idx_subscribers_zone ON public.subscribers(zone_id);
CREATE INDEX idx_generators_zone ON public.generators(zone_id);
CREATE INDEX idx_subscriptions_subscriber ON public.subscriptions(subscriber_id);
CREATE INDEX idx_subscriptions_generator ON public.subscriptions(generator_id);
CREATE INDEX idx_assignments_employee ON public.employee_subscriber_assignments(employee_id);
CREATE INDEX idx_assignments_subscriber ON public.employee_subscriber_assignments(subscriber_id);
CREATE INDEX idx_meters_subscription ON public.meters(subscription_id);
CREATE INDEX idx_meter_readings_meter ON public.meter_readings(meter_id);
CREATE INDEX idx_meter_readings_employee ON public.meter_readings(captured_by);
CREATE INDEX idx_meter_readings_date ON public.meter_readings(reading_date);
CREATE INDEX idx_invoices_subscription ON public.invoices(subscription_id);
CREATE INDEX idx_invoices_tariff ON public.invoices(tariff_id);
CREATE INDEX idx_invoices_period ON public.invoices(billing_period);
CREATE INDEX idx_payments_invoice ON public.payments(invoice_id);
CREATE INDEX idx_payments_collector ON public.payments(collected_by);

-- ENABLE RLS ON ALL TABLES
ALTER TABLE public.zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscribers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employee_subscriber_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meter_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tariffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

-- GRANT TABLE PERMISSIONS TO ANON & AUTHENTICATED ROLES
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;

-- CREATE OPEN PERMISSIVE POLICIES FOR APP CRUD ACCESS
CREATE POLICY "allow_public_all_zones" ON public.zones FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_employees" ON public.employees FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_subscribers" ON public.subscribers FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_generators" ON public.generators FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_subscriptions" ON public.subscriptions FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_assignments" ON public.employee_subscriber_assignments FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_meters" ON public.meters FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_readings" ON public.meter_readings FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_tariffs" ON public.tariffs FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_invoices" ON public.invoices FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
CREATE POLICY "allow_public_all_payments" ON public.payments FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
