import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { UserPlus, Eye, Edit, Ban, Search, Trash2, KeyRound } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge, statusTone } from '@/components/ui/Badge';
import { DataTable } from '@/components/ui/DataTable';
import { Modal } from '@/components/ui/Modal';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { Pagination } from '@/components/ui/Pagination';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/context/ToastContext';
import { customerService, type CustomerRecord } from '@/services/api';
import { formatCurrency, formatDate, formatKwh } from '@/utils/helpers';
import { errorMessage } from '@/utils/errors';
import { t } from '@/i18n/t';

type Customer = CustomerRecord;

/** A code just issued: shown once, because the server keeps only its hash. */
interface IssuedCode { name: string; customerId: string; code: string; expiresAt: string }

// The plans as stored. The option shows the translation; the value sent to the
// server stays the stored word, whatever the interface language.
const PLANS = ['Residential', 'Commercial', 'Industrial'];
const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'inactive', label: 'Inactive' },
];

// The five fields the SRS specifies as inputs to the Customer Management
// Module (Section VI-i), plus region and plan for the analytics.
interface CustomerForm {
  customerId: string; name: string; email: string;
  phone: string; address: string; region: string; plan: string;
}

const EMPTY_FORM: CustomerForm = {
  customerId: '', name: '', email: '', phone: '', address: '', region: '', plan: 'Residential',
};

const PAGE_SIZE = 6;

export default function CustomerManagement() {
  const toast = useToast();
  const [params] = useSearchParams();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  // Pre-filled when an administrator picked a customer in the header search,
  // so this page opens already filtered to the one they chose.
  const [search, setSearch] = useState(params.get('q') ?? '');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [addOpen, setAddOpen] = useState(false);
  const [viewing, setViewing] = useState<Customer | null>(null);
  const [newCustomer, setNewCustomer] = useState<CustomerForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [editCustomer, setEditCustomer] = useState<CustomerForm>(EMPTY_FORM);
  const [deleting, setDeleting] = useState<Customer | null>(null);
  const [codeFor, setCodeFor] = useState<Customer | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [issued, setIssued] = useState<IssuedCode | null>(null);

  useEffect(() => { customerService.getAll().then((c) => { setCustomers(c); setLoading(false); }); }, []);

  // Searching again from the header while already on this page changes the
  // query string without remounting, so the initial state above would go
  // stale. This keeps the two in step.
  useEffect(() => {
    const incoming = params.get('q');
    if (incoming !== null) {
      setSearch(incoming);
      setPage(1);
    }
  }, [params]);

  const filtered = customers.filter((c) => {
    const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase()) || c.id.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || c.status.toLowerCase() === statusFilter;
    return matchesSearch && matchesStatus;
  });
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Deactivate suspends access but keeps every reading, bill and payment.
  const handleDeactivate = async (c: Customer) => {
    const reactivating = c.status !== 'Active';
    try {
      const updated = reactivating
        ? await customerService.activate(c.id)
        : await customerService.deactivate(c.id);
      setCustomers((prev) => prev.map((customer) => customer.id === c.id ? updated : customer));
      setViewing((current) => current?.id === c.id ? updated : current);
      toast({ type: 'info', title: reactivating ? t('Customer reactivated') : t('Customer deactivated'), message: c.name });
    } catch (error) {
      toast({ type: 'error', title: t('Could not update the account'), message: errorMessage(error) });
    }
  };

  const handleAdd = async () => {
    if (!newCustomer.customerId || !newCustomer.name || !newCustomer.email) {
      toast({ type: 'error', title: t('Missing fields'), message: t('Customer ID, name and email are required.') });
      return;
    }
    try {
      // The Customer ID is the provider's account number: it is what links
      // this record to the meter readings loaded by the data pipeline.
      const created = await customerService.create(newCustomer);
      setCustomers((prev) => [created, ...prev]);
      setNewCustomer(EMPTY_FORM);
      setAddOpen(false);
      // Registering also needs a one-time code (app/core/registration_codes.py),
      // so the message points to where it is issued instead of implying that
      // the Customer ID alone is enough.
      toast({
        type: 'success',
        title: t('Customer added'),
        message: t('{name} ({id}). To register for portal access they also need a registration code: issue one from the list.')
          .replace('{name}', created.name).replace('{id}', created.id),
      });
    } catch (error) {
      toast({ type: 'error', title: t('Could not add the customer'), message: errorMessage(error) });
    }
  };

  const openEdit = (customer: Customer) => {
    setEditing(customer);
    setEditCustomer({
      customerId: customer.id,
      name: customer.name,
      email: customer.email,
      phone: customer.phone ?? '',
      address: customer.address ?? '',
      region: customer.region ?? '',
      plan: customer.plan,
    });
  };

  const handleEdit = async () => {
    if (!editing) return;
    if (!editCustomer.name || !editCustomer.email) {
      toast({ type: 'error', title: t('Missing fields'), message: t('Name and email are required.') });
      return;
    }
    try {
      const updated = await customerService.update(editing.id, editCustomer);
      setCustomers((prev) => prev.map((customer) => customer.id === updated.id ? updated : customer));
      setViewing((current) => current?.id === updated.id ? updated : current);
      setEditing(null);
      toast({ type: 'success', title: t('Customer updated'), message: updated.name });
    } catch (error) {
      toast({ type: 'error', title: t('Could not update the customer'), message: errorMessage(error) });
    }
  };

  // Permanent and irreversible: removes the customer's whole history too.
  const handleDelete = async () => {
    if (!deleting) return;
    try {
      const result = await customerService.remove(deleting.id);
      setCustomers((prev) => prev.filter((customer) => customer.id !== deleting.id));
      setViewing((current) => current?.id === deleting.id ? null : current);
      const name = deleting.name;
      setDeleting(null);
      toast({
        type: 'success',
        title: t('Customer deleted'),
        message: t('{name}: also removed {readings} readings, {bills} bills and {payments} payments.')
          .replace('{name}', name)
          .replace('{readings}', result.removedConsumptionRows.toLocaleString('en-US'))
          .replace('{bills}', result.removedBills.toLocaleString('en-US'))
          .replace('{payments}', result.removedPayments.toLocaleString('en-US')),
      });
    } catch (error) {
      toast({ type: 'error', title: t('Could not delete the customer'), message: errorMessage(error) });
    }
  };

  // Issuing replaces any code issued before, including one already printed on
  // a bill, so it is confirmed first (codeFor) and the new code is shown once.
  const handleIssueCode = async () => {
    if (!codeFor) return;
    setIssuing(true);
    try {
      const result = await customerService.issueRegistrationCode(codeFor.id);
      setIssued({ name: codeFor.name, customerId: result.customerId, code: result.registrationCode, expiresAt: result.expiresAt });
      setCodeFor(null);
    } catch (error) {
      toast({ type: 'error', title: t('Could not issue a registration code'), message: errorMessage(error) });
    } finally {
      setIssuing(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={t('Customer Management')}
        description={t('View, search, and manage all your customers.')}
        breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Customers') }]}
        action={<Button leftIcon={<UserPlus className="w-4 h-4" />} onClick={() => setAddOpen(true)}>{t('Add Customer')}</Button>}
      />

      <Card className="p-5">
        <div className="flex flex-col sm:flex-row gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder={t('Search by name, email, or ID...')} className="input-base ps-10 h-10" />
          </div>
          <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl">
            {STATUS_FILTERS.map((f) => (
              <button key={f.value} onClick={() => { setStatusFilter(f.value); setPage(1); }} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${statusFilter === f.value ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm' : 'text-slate-500'}`}>{t(f.label)}</button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="py-8 text-center text-sm text-slate-400">{t('Loading customers...')}</div>
        ) : paged.length === 0 ? (
          <EmptyState title={t('No customers found')} description={t('Try adjusting your search or filters.')} icon={<Search className="w-8 h-8" />} />
        ) : (
          <>
            <DataTable
              columns={[
                { key: 'id', header: t('ID'), render: (c: Customer) => <span className="font-mono text-xs font-semibold text-slate-900 dark:text-slate-100 whitespace-nowrap ltr-num">{c.id}</span> },
                { key: 'name', header: t('Name'), render: (c: Customer) => (
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center text-white text-xs font-bold">{c.name.charAt(0)}</div>
                    <div><p className="font-medium text-slate-900 dark:text-slate-100">{c.name}</p><p className="text-xs text-slate-400">{c.email}</p></div>
                  </div>
                ) },
                { key: 'region', header: t('Region') },
                { key: 'plan', header: t('Plan'), render: (c: Customer) => <Badge tone={c.plan === 'Commercial' ? 'primary' : 'neutral'}>{t(c.plan)}</Badge> },
                { key: 'consumption', header: t('Usage'), render: (c: Customer) => formatKwh(c.consumption) },
                { key: 'balance', header: t('Balance'), render: (c: Customer) => <span className={c.balance > 0 ? 'text-warning-600 font-semibold' : ''}>{formatCurrency(c.balance)}</span> },
                { key: 'status', header: t('Status'), render: (c: Customer) => <Badge tone={statusTone(c.status)}>{t(c.status)}</Badge> },
                // Five icons, packed so the column fits beside the others in a
                // 1440-pixel window: with the registration-code key added it
                // overflowed, and Delete could only be reached by scrolling.
                { key: 'actions', header: t('Actions'), className: 'text-end', render: (c: Customer) => (
                  <div className="flex items-center justify-end gap-0.5">
                    <button onClick={() => setViewing(c)} className="p-1 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 transition" aria-label={t('View')} title={t('View')}><Eye className="w-4 h-4" /></button>
                    <button onClick={() => openEdit(c)} className="p-1 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 transition" aria-label={t('Edit {name}').replace('{name}', c.name)} title={t('Edit {name}').replace('{name}', c.name)}><Edit className="w-4 h-4" /></button>
                    {!c.registered && (
                      <button onClick={() => setCodeFor(c)} className="p-1 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 transition" aria-label={t('Issue a registration code for {name}').replace('{name}', c.name)} title={t('Issue a registration code for {name}').replace('{name}', c.name)}><KeyRound className="w-4 h-4" /></button>
                    )}
                    <button onClick={() => handleDeactivate(c)} className="p-1 rounded-lg text-slate-400 hover:bg-warning-50 dark:hover:bg-warning-500/10 hover:text-warning-600 transition" aria-label={(c.status === 'Active' ? t('Deactivate {name}') : t('Activate {name}')).replace('{name}', c.name)} title={(c.status === 'Active' ? t('Deactivate {name}') : t('Activate {name}')).replace('{name}', c.name)}><Ban className="w-4 h-4" /></button>
                    <button onClick={() => setDeleting(c)} className="p-1 rounded-lg text-slate-400 hover:bg-error-50 dark:hover:bg-error-500/10 hover:text-error-600 transition" aria-label={t('Delete {name}').replace('{name}', c.name)} title={t('Delete {name}').replace('{name}', c.name)}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ) },
              ]}
              data={paged}
              rowKey={(c) => c.id}
            />
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        )}
      </Card>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title={t('Add New Customer')} description={t('To register for portal access, the customer needs this Customer ID and a one-time registration code, which you issue from the list once the account is added.')} size="md"
        footer={<><Button variant="outline" onClick={() => setAddOpen(false)}>{t('Cancel')}</Button><Button onClick={handleAdd}>{t('Add Customer')}</Button></>}>
        <div className="space-y-4">
          <Input label={t('Customer ID')} placeholder={t('e.g. GEN-00042')} hint={t("The provider's account number. Meter readings load against this ID.")} value={newCustomer.customerId} onChange={(e) => setNewCustomer({ ...newCustomer, customerId: e.target.value })} />
          <Input label={t('Full name')} placeholder={t('e.g. Nour Haddad')} value={newCustomer.name} onChange={(e) => setNewCustomer({ ...newCustomer, name: e.target.value })} />
          <Input label={t('Email')} type="email" placeholder={t('you@example.com')} value={newCustomer.email} onChange={(e) => setNewCustomer({ ...newCustomer, email: e.target.value })} />
          <Input label={t('Phone number')} placeholder="+961 3 214 887" value={newCustomer.phone} onChange={(e) => setNewCustomer({ ...newCustomer, phone: e.target.value })} />
          <Input label={t('Address')} placeholder={t('Hamra Street, Bldg 12, Beirut')} value={newCustomer.address} onChange={(e) => setNewCustomer({ ...newCustomer, address: e.target.value })} />
          <Input label={t('Region')} placeholder={t('Beirut')} value={newCustomer.region} onChange={(e) => setNewCustomer({ ...newCustomer, region: e.target.value })} />
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">{t('Plan')}</label>
            <select value={newCustomer.plan} onChange={(e) => setNewCustomer({ ...newCustomer, plan: e.target.value })} className="input-base">
              {PLANS.map((plan) => <option key={plan} value={plan}>{t(plan)}</option>)}
            </select>
          </div>
        </div>
      </Modal>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={t('Edit Customer')} description={t('Update the customer account details.')} size="md"
        footer={<><Button variant="outline" onClick={() => setEditing(null)}>{t('Cancel')}</Button><Button onClick={handleEdit}>{t('Save Changes')}</Button></>}>
        <div className="space-y-4">
          {/* The Customer ID is the primary key and the link to the meter
              readings, so it is shown for reference but never editable. */}
          <Input label={t('Customer ID')} value={editCustomer.customerId} readOnly disabled hint={t('Cannot be changed, meter readings are linked to it.')} />
          <Input label={t('Full name')} value={editCustomer.name} onChange={(e) => setEditCustomer({ ...editCustomer, name: e.target.value })} />
          <Input label={t('Email')} type="email" value={editCustomer.email} onChange={(e) => setEditCustomer({ ...editCustomer, email: e.target.value })} />
          <Input label={t('Phone number')} value={editCustomer.phone} onChange={(e) => setEditCustomer({ ...editCustomer, phone: e.target.value })} />
          <Input label={t('Address')} value={editCustomer.address} onChange={(e) => setEditCustomer({ ...editCustomer, address: e.target.value })} />
          <Input label={t('Region')} value={editCustomer.region} onChange={(e) => setEditCustomer({ ...editCustomer, region: e.target.value })} />
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">{t('Plan')}</label>
            <select value={editCustomer.plan} onChange={(e) => setEditCustomer({ ...editCustomer, plan: e.target.value })} className="input-base">
              {PLANS.map((plan) => <option key={plan} value={plan}>{t(plan)}</option>)}
            </select>
          </div>
        </div>
      </Modal>

      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={t('Delete Customer')} description={t('This permanently deletes the account and its entire history. This cannot be undone.')}
        footer={<><Button variant="outline" onClick={() => setDeleting(null)}>{t('Cancel')}</Button><Button variant="danger" onClick={handleDelete}>{t('Delete Customer')}</Button></>}>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {t('Permanently delete {name}, including every meter reading, bill and payment on record? To block access while keeping the records, use Deactivate instead.')
            .split('{name}')
            .map((part, i) => (i === 0 ? part : <span key={i}><span className="font-semibold">{deleting?.name}</span>{part}</span>))}
        </p>
      </Modal>

      <Modal open={!!codeFor} onClose={() => setCodeFor(null)} title={t('Issue a registration code')}
        description={t('The customer needs this code, with the Customer ID, to register for portal access. It can be used once, until the expiry date shown when it is issued.')}
        footer={<><Button variant="outline" onClick={() => setCodeFor(null)}>{t('Cancel')}</Button><Button onClick={handleIssueCode} loading={issuing}>{t('Issue code')}</Button></>}>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {t('Issue a code for {name}? A code issued before for this account, including one printed on a bill, stops working.')
            .split('{name}')
            .map((part, i) => (i === 0 ? part : <span key={i}><span className="font-semibold">{codeFor?.name}</span>{part}</span>))}
        </p>
      </Modal>

      <Modal open={!!issued} onClose={() => setIssued(null)} title={t('Registration code issued')}
        footer={<Button onClick={() => setIssued(null)}>{t('Done')}</Button>}>
        {issued && (
          <div className="space-y-4 text-sm">
            <p className="text-slate-600 dark:text-slate-300">{t('Give these to {name}. The code is shown only this once: it is not stored in a readable form.').replace('{name}', issued.name)}</p>
            <div className="grid grid-cols-2 gap-4">
              <div><p className="text-xs text-slate-500">{t('Customer ID')}</p><p className="font-mono font-semibold select-all ltr-num">{issued.customerId}</p></div>
              <div><p className="text-xs text-slate-500">{t('Registration code')}</p><p className="font-mono text-lg font-bold tracking-wider select-all ltr-num">{issued.code}</p></div>
              <div className="col-span-2"><p className="text-xs text-slate-500">{t('Valid until')}</p><p>{formatDate(issued.expiresAt)}</p></div>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={t('Customer Details')} size="md"
        footer={<Button variant="outline" onClick={() => setViewing(null)}>{t('Close')}</Button>}>
        {viewing && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-14 h-14 rounded-2xl bg-gradient-primary flex items-center justify-center text-white text-xl font-bold">{viewing.name.charAt(0)}</div>
              <div><p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{viewing.name}</p><p className="text-sm text-slate-500">{viewing.email}</p></div>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div><p className="text-xs text-slate-500">{t('Customer ID')}</p><p className="font-mono font-semibold ltr-num">{viewing.id}</p></div>
              <div><p className="text-xs text-slate-500">{t('Phone')}</p><p>{viewing.phone || t('Not set')}</p></div>
              <div className="col-span-2"><p className="text-xs text-slate-500">{t('Address')}</p><p>{viewing.address || t('Not set')}</p></div>
              <div><p className="text-xs text-slate-500">{t('Region')}</p><p>{viewing.region}</p></div>
              <div>
                <p className="text-xs text-slate-500">{t('Portal access')}</p>
                <Badge tone={viewing.registered ? 'success' : 'neutral'}>
                  {viewing.registered ? t('Registered') : t('Not registered yet')}
                </Badge>
              </div>
              <div><p className="text-xs text-slate-500">{t('Plan')}</p><Badge tone={viewing.plan === 'Commercial' ? 'primary' : 'neutral'}>{t(viewing.plan)}</Badge></div>
              <div><p className="text-xs text-slate-500">{t('Status')}</p><Badge tone={statusTone(viewing.status)}>{t(viewing.status)}</Badge></div>
              <div><p className="text-xs text-slate-500">{t('Monthly usage')}</p><p className="font-semibold">{formatKwh(viewing.consumption)}</p></div>
              <div><p className="text-xs text-slate-500">{t('Outstanding balance')}</p><p className="font-semibold">{formatCurrency(viewing.balance)}</p></div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
