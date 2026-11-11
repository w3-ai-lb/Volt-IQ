import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, ArrowRight, BarChart3, Users, Brain, Bell, Lightbulb, TrendingUp, Check, Menu } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useTheme } from '@/context/ThemeContext';
import { Sun, Moon } from 'lucide-react';
import { withUnit } from '@/utils/helpers';
import { slideFrom, t } from '@/i18n/t';

const features = [
  { icon: Brain, title: 'AI Forecasting', description: 'Forecast demand from the consumption history, and check every forecast against what actually happened.' },
  // "Pay bills" promised a payment the portal does not take: it records a
  // payment made through the provider's own channels (pages/customer/BillsPage).
  { icon: Users, title: 'Customer Portal', description: 'A self-service portal where customers follow their usage, bills and payments, and get insights.' },
  { icon: BarChart3, title: 'Analytics Dashboard', description: 'KPIs for revenue, consumption and losses, dated to the newest reading rather than to the clock.' },
  { icon: Brain, title: 'AI Chatbot', description: 'Answers billing and usage questions from the account’s own bills and readings, and says so when it does not know.' },
  { icon: Lightbulb, title: 'Personalized Recommendations', description: 'Suggestions computed from each account’s own consumption history, with what each one is worth.' },
  { icon: Bell, title: 'Smart Alerts', description: 'Proactive notifications for high usage, anomalies, and payment reminders.' },
];

// These used to be "up to 15%" and "by 30%". Neither number was measured
// anywhere, and a page asserting them in front of a dashboard that reports its
// own backtest is a contradiction a reader will find. What is claimed here is
// what the software does, which needs no invented figure to be worth reading.
const benefits = [
  'Account for the gap between what the generators sent out and what the meters billed',
  'Separate ordinary technical loss from what still needs explaining',
  'Flag the accounts worth a visit, with the innocent explanations attached',
  'Give every subscriber their own readings, bills and payments',
];

const steps = [
  { number: '01', title: 'Connect your data', description: 'Load meter readings, invoices and generator telemetry from the provider’s own files.' },
  { number: '02', title: 'AI analyzes patterns', description: 'Our models learn consumption trends, detect anomalies, and forecast demand.' },
  { number: '03', title: 'Act on insights', description: 'Recommendations and alerts computed from each account’s own history.' },
];

// WHAT THESE USED TO SAY, AND WHY THEY DO NOT ANY MORE
// -----------------------------------------------------
// "24K+ customers monitored", "94% forecast accuracy", "15% avg. cost
// reduction", "4.2M kWh analyzed daily". Not one of the four was measured. The
// platform now backtests its own forecast and reports the result on the admin
// dashboard, so a front page claiming 94% sat directly in front of a screen
// reporting something else, the kind of contradiction that gets noticed in the
// room rather than on the page.
//
// What replaces them is the shape of the work, which is true without a claim:
// energy is measured going out, measured coming back, and the difference is
// broken into five named parts before anybody is accused of taking it.
const stats = [
  { value: 'kWh out', label: 'Measured at the generator' },
  { value: 'kWh in', label: 'Measured at the meter' },
  { value: '5 parts', label: 'The difference, explained' },
  { value: 'Zero', label: 'Figures without a source' },
];

function Navbar() {
  const [open, setOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  return (
    <header className="fixed top-0 inset-x-0 z-50 glass border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-lg text-slate-900 dark:text-slate-100">{t('VoltIQ')}</span>
        </Link>
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600 dark:text-slate-300">
          <a href="#features" className="hover:text-primary-600 transition">{t('Features')}</a>
          <a href="#benefits" className="hover:text-primary-600 transition">{t('Benefits')}</a>
          <a href="#how" className="hover:text-primary-600 transition">{t('How it works')}</a>
        </nav>
        <div className="flex items-center gap-2">
          <button onClick={toggleTheme} className="p-2.5 rounded-xl text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition" aria-label={t('Toggle theme')}>
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <Link to="/login" className="hidden sm:block"><Button variant="ghost" size="sm">{t('Login')}</Button></Link>
          <Link to="/register" className="hidden sm:block"><Button size="sm">{t('Get Started')}</Button></Link>
          <button onClick={() => setOpen((o) => !o)} className="md:hidden p-2 text-slate-600" aria-label={t('Open menu')}><Menu className="w-5 h-5" /></button>
        </div>
      </div>
      {open && (
        <div className="md:hidden glass-strong border-t border-slate-200 dark:border-slate-800 p-4 space-y-2">
          <a href="#features" onClick={() => setOpen(false)} className="block py-2 text-sm text-slate-600 dark:text-slate-300">{t('Features')}</a>
          <a href="#benefits" onClick={() => setOpen(false)} className="block py-2 text-sm text-slate-600 dark:text-slate-300">{t('Benefits')}</a>
          <a href="#how" onClick={() => setOpen(false)} className="block py-2 text-sm text-slate-600 dark:text-slate-300">{t('How it works')}</a>
          <Link to="/login" className="block py-2 text-sm text-slate-600 dark:text-slate-300">{t('Login')}</Link>
          <Link to="/register"><Button size="sm" fullWidth>{t('Get Started')}</Button></Link>
        </div>
      )}
    </header>
  );
}

function Hero() {
  const heroTitle = t('AI-Powered Energy {highlight}').split('{highlight}');
  return (
    <section className="relative pt-32 pb-20 overflow-hidden bg-grid">
      <div className="absolute top-20 -left-20 w-72 h-72 bg-primary-500/20 rounded-full blur-3xl" />
      <div className="absolute top-40 right-0 w-96 h-96 bg-emerald-500/20 rounded-full blur-3xl" />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-12 items-center">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300 text-xs font-semibold mb-5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />{t('AI-Powered Energy Intelligence')}
          </div>
          {/* One sentence with a marked part, so each language can put the
              highlighted words where its own grammar wants them. */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-slate-900 dark:text-slate-100 leading-[1.1] text-balance">
            {heroTitle[0]}<span className="text-gradient-primary">{t('Analytics Platform')}</span>{heroTitle[1]}
          </h1>
          <p className="mt-5 text-lg text-slate-600 dark:text-slate-400 max-w-xl leading-relaxed">{t('Analyze electricity consumption, forecast demand, reduce costs, and improve customer engagement using AI, all in one modern platform.')}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register"><Button size="lg" rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Get Started')}</Button></Link>
            <Link to="/login"><Button size="lg" variant="outline">{t('Login')}</Button></Link>
          </div>
          <div className="mt-10 grid grid-cols-2 sm:grid-cols-4 gap-4">
            {stats.map((s) => (
              <div key={s.label}>
                <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t(s.value)}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t(s.label)}</p>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Dashboard mockup */}
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, delay: 0.2 }} className="relative">
          <div className="glass-strong rounded-3xl shadow-card-hover p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-error-400" />
                <div className="w-3 h-3 rounded-full bg-warning-400" />
                <div className="w-3 h-3 rounded-full bg-emerald-400" />
              </div>
              {/* The app's own address for the page shown, not a domain:
                  a made-up web address can belong to somebody. */}
              <div className="text-xs text-slate-400 font-medium ltr-num">/app/dashboard</div>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: t('Consumption'), value: withUnit('540', 'kWh'), tone: 'text-primary-600' },
                // 540 kWh at the provider's June 2026 rate plus the fixed charge. Lebanese
                // pounds, not dollars: this is an ishtirak. See utils/helpers.ts.
                { label: t('Current Bill'), value: withUnit('17.1M', 'LBP'), tone: 'text-emerald-600' },
                { label: t('Saving Score'), value: '78', tone: 'text-accent-600' },
              ].map((c) => (
                <div key={c.label} className="bg-white/60 dark:bg-slate-800/60 rounded-xl p-3">
                  <p className="text-[10px] text-slate-500">{t(c.label)}</p>
                  <p className={`text-lg font-bold ${c.tone}`}>{c.value}</p>
                </div>
              ))}
            </div>
            <div className="bg-white/60 dark:bg-slate-800/60 rounded-xl p-4 h-40 flex items-end gap-2">
              {[40, 55, 48, 70, 62, 85, 75, 90, 68, 80, 72, 88].map((h, i) => (
                <motion.div key={i} initial={{ height: 0 }} animate={{ height: `${h}%` }} transition={{ delay: 0.5 + i * 0.05, duration: 0.4 }} className="flex-1 bg-gradient-to-t from-primary-600 to-emerald-500 rounded-t-md" />
              ))}
            </div>
          </div>
          {/* Floating cards */}
          <motion.div animate={{ y: [0, -10, 0] }} transition={{ duration: 6, repeat: Infinity }} className="absolute -top-6 -right-4 glass-strong rounded-2xl shadow-card-hover p-3 flex items-center gap-2.5 w-44">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/15 flex items-center justify-center"><TrendingUp className="w-5 h-5 text-emerald-600" /></div>
            <div><p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{t('Down 13.6%')}</p><p className="text-[10px] text-slate-500">{t('vs the same month last year')}</p></div>
          </motion.div>
          <motion.div animate={{ y: [0, 10, 0] }} transition={{ duration: 5, repeat: Infinity }} className="absolute -bottom-6 -left-4 glass-strong rounded-2xl shadow-card-hover p-3 flex items-center gap-2.5 w-48">
            <div className="w-9 h-9 rounded-lg bg-primary-500/15 flex items-center justify-center"><Brain className="w-5 h-5 text-primary-600" /></div>
            <div><p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{t('AI Insight')}</p><p className="text-[10px] text-slate-500">{t('The network is busiest at 19:00')}</p></div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="features" className="py-20 max-w-7xl mx-auto px-4 sm:px-6">
      <div className="text-center max-w-2xl mx-auto mb-12">
        <p className="text-sm font-semibold text-primary-600 dark:text-primary-400 uppercase tracking-wide">{t('Features')}</p>
        <h2 className="mt-2 text-3xl sm:text-4xl font-bold text-slate-900 dark:text-slate-100">{t('Everything you need to run a smarter grid')}</h2>
        <p className="mt-3 text-slate-600 dark:text-slate-400">{t('From demand forecasting to customer engagement, VoltIQ brings every team into one platform.')}</p>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {features.map((f, i) => {
          const Icon = f.icon;
          return (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.05 }}
              className="card-surface shadow-card rounded-2xl p-6 hover:shadow-card-hover hover:-translate-y-1 transition-all duration-300"
            >
              <div className="w-12 h-12 rounded-xl bg-gradient-primary flex items-center justify-center mb-4 shadow-glow">
                <Icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{t(f.title)}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">{t(f.description)}</p>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

function Benefits() {
  return (
    <section id="benefits" className="py-20 bg-slate-50 dark:bg-slate-900/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <p className="text-sm font-semibold text-primary-600 dark:text-primary-400 uppercase tracking-wide">{t('Benefits')}</p>
          <h2 className="mt-2 text-3xl sm:text-4xl font-bold text-slate-900 dark:text-slate-100">{t('Real outcomes for your utility')}</h2>
          <p className="mt-3 text-slate-600 dark:text-slate-400">{t('What the platform is built to do, and what it deliberately refuses to guess.')}</p>
          <ul className="mt-8 space-y-4">
            {benefits.map((b, i) => (
              <motion.li key={i} initial={{ opacity: 0, x: slideFrom(-20) }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }} className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-full bg-emerald-500/15 flex items-center justify-center shrink-0 mt-0.5">
                  <Check className="w-4 h-4 text-emerald-600" />
                </div>
                <p className="text-slate-700 dark:text-slate-300">{t(b)}</p>
              </motion.li>
            ))}
          </ul>
          {/* "Start your free trial" was a software-as-a-service phrase. This is
              a provider's portal: nobody trials it, subscribers activate it. */}
          <Link to="/register" className="inline-block mt-8"><Button rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Activate your online account')}</Button></Link>
        </div>
        <motion.div initial={{ opacity: 0, scale: 0.95 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} className="grid grid-cols-2 gap-4">
          {[
            { value: 'Hourly', label: t('Generator telemetry'), color: 'from-primary-600 to-primary-400' },
            { value: 'Monthly', label: t('Meter readings, as they are taken'), color: 'from-emerald-600 to-emerald-400' },
            { value: 'Checked', label: t('Forecasts against outcomes'), color: 'from-accent-600 to-accent-400' },
            { value: 'Traceable', label: t('Every figure to a source file'), color: 'from-primary-600 to-emerald-400' },
          ].map((s) => (
            <div key={s.label} className={`rounded-2xl bg-gradient-to-br ${s.color} p-6 text-white shadow-card`}>
              <p className="text-3xl font-bold">{t(s.value)}</p>
              <p className="text-sm text-white/80 mt-1">{s.label}</p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="py-20 max-w-7xl mx-auto px-4 sm:px-6">
      <div className="text-center max-w-2xl mx-auto mb-12">
        <p className="text-sm font-semibold text-primary-600 dark:text-primary-400 uppercase tracking-wide">{t('How it works')}</p>
        <h2 className="mt-2 text-3xl sm:text-4xl font-bold text-slate-900 dark:text-slate-100">{t('Up and running in three steps')}</h2>
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        {steps.map((s, i) => (
          <motion.div key={s.number} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }} className="relative card-surface shadow-card rounded-2xl p-6">
            <span className="text-4xl font-extrabold text-primary-600/20 dark:text-primary-400/20">{s.number}</span>
            <h3 className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{t(s.title)}</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{t(s.description)}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

/*
 * A Testimonials section used to sit here.
 *
 * It rendered five quotes from `services/mockData.ts`, each attributed by name
 * and job title to a person at a named utility. None of those people exist and
 * none of those companies is a customer. At the time that was defended as a
 * distinction from the "94% forecast accuracy" then sitting further up this
 * page: an invented statistic is marketing, an invented quotation from a named
 * individual is not.
 *
 * The statistic half of that argument has since been withdrawn. The admin
 * dashboard shows the forecast's own backtest, labelled as a diagnostic rather
 * than a validated accuracy, so "94%" on the front page was contradicting the
 * product's own screen, and the
 * three figures beside it described a deployment that does not exist. They are
 * gone as well.
 *
 * Removed rather than rewritten, because there is no honest version of it until
 * the platform has a real customer to quote. Its removal also took the last
 * import of mockData.ts out of the application.
 */

function CTA() {
  return (
    <section className="py-20 max-w-7xl mx-auto px-4 sm:px-6">
      <div className="relative rounded-3xl bg-gradient-primary p-10 sm:p-16 text-center overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-20" />
        <div className="relative">
          {/* Addressed to the people who can actually register: the
              provider's own subscribers. It used to invite "utilities" to a
              "free" start, which this portal does not offer anybody. */}
          <h2 className="text-3xl sm:text-4xl font-bold text-white">{t('Already a subscriber?')}</h2>
          <p className="mt-3 text-white/80 max-w-xl mx-auto">{t('Activate online access with the Customer ID and the registration code printed on your bill.')}</p>
          <Link to="/register" className="inline-block mt-8"><Button size="lg" variant="secondary" rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>{t('Activate your online account')}</Button></Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-8">
        <div>
          <Link to="/" className="flex items-center gap-2.5 mb-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center"><Zap className="w-5 h-5 text-white" /></div>
            <span className="font-bold text-lg text-slate-900 dark:text-slate-100">{t('VoltIQ')}</span>
          </Link>
          <p className="text-sm text-slate-500 dark:text-slate-400">{t('AI-powered energy analytics and customer engagement for modern utilities.')}</p>
        </div>
        {/*
          Only links that lead somewhere. The footer used to list Pricing,
          Careers, Blog, Documentation and nine more, every one of them a "#"
          to a page that does not exist.
        */}
        {[
          { title: t('Product'), links: [['Features', '#features'], ['Benefits', '#benefits'], ['How it works', '#how']] },
          { title: t('Account'), links: [['Login', '/login'], ['Create your account', '/register'], ['Forgot password?', '/forgot-password']] },
        ].map((col) => (
          <div key={col.title}>
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3">{col.title}</h4>
            <ul className="space-y-2">
              {col.links.map(([label, href]) => (
                <li key={href}>
                  {href.startsWith('#')
                    ? <a href={href} className="text-sm text-slate-500 dark:text-slate-400 hover:text-primary-600 transition">{t(label)}</a>
                    : <Link to={href} className="text-sm text-slate-500 dark:text-slate-400 hover:text-primary-600 transition">{t(label)}</Link>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200 dark:border-slate-800 py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            <span className="ltr-num">© {new Date().getFullYear()} VoltIQ.</span> {t('All rights reserved.')}
          </p>
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-slate-950">
      <Navbar />
      <Hero />
      <Features />
      <Benefits />
      <HowItWorks />
      <CTA />
      <Footer />
    </div>
  );
}
