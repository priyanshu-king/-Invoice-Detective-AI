import React from 'react'
import ReactDOM from 'react-dom/client'
import './style.css'

type Finding = {
  id: number
  finding_type: string
  severity: string
  title: string
  description: string
  suggested_action: string
  affected_fields: string[] | null
  evidence: Record<string, unknown> | null
  review_status: string
}

type LineItem = {
  id?: number
  description: string | null
  quantity: number | null
  unit_price: number | null
  amount: number | null
  item_order: number
}

type InvoiceActivityEntry = {
  id: number
  event_type: string
  summary: string
  changed_fields: string[]
  created_at: string
}

type Invoice = {
  id: number
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  currency: string
  subtotal: number | null
  tax_amount: number | null
  tax_rate: number | null
  total_amount: number | null
  discount_amount: number | null
  vendor_address: string | null
  gstin: string | null
  notes: string | null
  raw_extracted_text: string | null
  extraction_confidence: string
  extraction_method: string | null
  processing_status: string
  processing_error: string | null
  review_status: string
  original_filename: string
  file_type: string
  uploaded_at: string
  line_items: LineItem[]
  findings: Finding[]
}

type DuplicateDetection = {
  id: number
  source_invoice_id: number | null
  matched_invoice_id: number
  match_type: string
  confidence: number
  created_at: string
}

type DuplicateComparison = {
  detection: DuplicateDetection
  source: Invoice | null
  matched: Invoice
}

type PurchaseOrderLineItem = {
  id?: number
  description: string
  quantity: number
  unit_price: number
  amount: number
  item_order: number
}

type PurchaseOrder = {
  id: number
  po_number: string
  vendor_name: string
  currency: string
  subtotal: number
  tax_rate: number
  tax_amount: number
  total_amount: number
  order_date: string | null
  expected_delivery_date: string | null
  status: 'open' | 'fulfilled' | 'cancelled'
  line_items: PurchaseOrderLineItem[]
  created_at: string
  updated_at: string
}

type PurchaseOrderComparison = {
  id: number
  invoice_id: number
  po_number: string
  po_vendor: string
  po_currency: string
  po_total: number
  comparison_result: Record<string, unknown>[]
}

type VendorProfile = {
  name: string
  invoice_count: number
  total_value_by_currency: CurrencyValue[]
  invoice_frequency: { month: string; count: number }[]
  findings_by_severity: Record<string, number>
  recent_findings: { invoice_id: number; title: string; severity: string; created_at: string }[]
  duplicate_matches: number
  price_changes: {
    description: string
    currency: string
    entries: { invoice_id: number; date: string | null; unit_price: number }[]
  }[]
  recent_invoices: {
    id: number
    invoice_number: string | null
    invoice_date: string | null
    due_date: string | null
    currency: string
    total_amount: number | null
    review_status: string
  }[]
  contact_details_available: boolean
  payment_tracking_available: boolean
}

type ReportData = {
  invoice_count: number
  total_value_by_currency: CurrencyValue[]
  review_status_counts: Record<string, number>
  findings_by_severity: Record<string, number>
  duplicate_matches: number
  monthly_invoice_volume: { month: string; count: number }[]
  vendor_spending: { vendor: string; currency: string; amount: number }[]
  items: {
    id: number
    invoice_number: string | null
    vendor_name: string | null
    invoice_date: string | null
    due_date: string | null
    currency: string
    total_amount: number | null
    review_status: string
    finding_count: number
    duplicate_matches: number
  }[]
}

type Dashboard = {
  total_invoices: number
  total_findings: number
  invoices_by_status: Record<string, number>
  findings_by_severity: Record<string, number>
  invoice_value_by_currency: CurrencyValue[]
  potential_duplicate_value_by_currency: CurrencyValue[]
  invoice_volume_by_month: { month: string; count: number }[]
  spend_by_month: { month: string; currency: string; amount: number }[]
  vendor_spend: { vendor: string; currency: string; amount: number; invoice_count: number }[]
  recent_invoices: Invoice[]
}

type CurrencyValue = { currency: string; amount: number }

type PrivacyInfo = {
  data_stored: string[]
  file_types_accepted: string[]
  storage_location: string
  data_retention: string
  third_party_sharing: string
  max_file_size_bytes: number
  external_ai_services: string
  database: { path: string; status: string; size_bytes: number }
  uploads: { path: string; status: string; file_count: number; size_bytes: number; error: string | null }
  reports: { path: string; status: string; file_count: number; size_bytes: number; error: string | null }
  workspace_data: { invoice_count: number; finding_count: number }
  authentication: {
    required: boolean
    scope: string
    session_lifetime_hours: number
    password_hashing: string
    rate_limiting_enabled: boolean
    email_verification_enabled: boolean
  }
  data_management: {
    invoice_metadata_export: string
    audit_findings_export: string
    invoice_deletion: string
  }
}

type WorkspaceSettings = {
  workspace_name: string
  business_name: string
  default_currency: string
  date_format: string
  time_zone: string
  language: string
  default_tax_rate: number | null
  invoice_number_prefix: string
  default_review_status: string
  notifications: {
    audit_completion: boolean
    duplicate_detection: boolean
    failed_upload: boolean
    review_reminders: boolean
  }
  profile: { display_name: string; email: string }
  appearance: 'light' | 'dark' | 'system'
  authentication: {
    status: string
    session_information: string
    password_management: string
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api').replace(/\/+$/, '')
const AUTH_TOKEN_KEY = 'invoice-detective-session-token'
const REVIEW_STATUSES = ['needs_review', 'reviewed', 'resolved']

type AuthResponse = {
  access_token: string
  expires_at: string
  user: { id: number; email: string; role: string }
  workspace: { id: number; name: string }
}

type UserProfile = { email: string; role: string; workspaceName: string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (response.status === 401 && token) {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    window.dispatchEvent(new Event('invoice-detective-unauthorized'))
  }
  const contentType = response.headers.get('content-type') ?? ''
  const body: unknown = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? String(body.detail)
      : String(body || response.statusText)
    throw new Error(`Request failed (${response.status}): ${detail}`)
  }

  return body as T
}

async function requestFile(path: string): Promise<Blob> {
  const headers = new Headers()
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { headers })
  if (response.status === 401 && token) {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    window.dispatchEvent(new Event('invoice-detective-unauthorized'))
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body: unknown = await response.json()
      if (typeof body === 'object' && body !== null && 'detail' in body) detail = String(body.detail)
    } catch {
      detail = response.statusText
    }
    throw new Error(`Request failed (${response.status}): ${detail}`)
  }
  return response.blob()
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function formatCurrency(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    return `${currency} ${amount.toLocaleString()}`
  }
}

function formatCurrencyBreakdown(values: CurrencyValue[] | undefined) {
  if (!values?.length) return 'No totals yet'
  return values.map(({ currency, amount }) => formatCurrency(amount, currency)).join(' · ')
}

function formatMonth(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  if (!year || !monthNumber) return month
  return new Intl.DateTimeFormat(undefined, { month: 'short', year: '2-digit' })
    .format(new Date(year, monthNumber - 1, 1))
}

function formatDate(value: string, format: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return value
  const [, year, month, day] = match
  if (format === 'DD/MM/YYYY') return `${day}/${month}/${year}`
  if (format === 'MM/DD/YYYY') return `${month}/${day}/${year}`
  return `${year}-${month}-${day}`
}

function App() {
  const [authToken, setAuthToken] = React.useState<string | null>(() => sessionStorage.getItem(AUTH_TOKEN_KEY))
  const [authChecking, setAuthChecking] = React.useState(() => Boolean(sessionStorage.getItem(AUTH_TOKEN_KEY)))
  const [profile, setProfile] = React.useState<UserProfile | null>(null)
  const [authMode, setAuthMode] = React.useState<'login' | 'register'>('login')
  const [authEmail, setAuthEmail] = React.useState('')
  const [authPassword, setAuthPassword] = React.useState('')
  const [workspaceName, setWorkspaceName] = React.useState('My workspace')
  const [status, setStatus] = React.useState('Connecting…')
  const [dashboard, setDashboard] = React.useState<Dashboard | null>(null)
  const [invoices, setInvoices] = React.useState<Invoice[]>([])
  const [invoiceTotal, setInvoiceTotal] = React.useState(0)
  const [reviewQueueInvoices, setReviewQueueInvoices] = React.useState<Invoice[]>([])
  const [reviewQueueTotal, setReviewQueueTotal] = React.useState(0)
  const [reviewQueueError, setReviewQueueError] = React.useState('')
  const [loadingMore, setLoadingMore] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<number | null>(null)
  const [focusedInvoice, setFocusedInvoice] = React.useState<Invoice | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  const [notice, setNotice] = React.useState('')
  const [file, setFile] = React.useState<File | null>(null)
  const [uploadDragActive, setUploadDragActive] = React.useState(false)
  const [searchText, setSearchText] = React.useState('')
  const [search, setSearch] = React.useState('')
  const [reviewStatusFilter, setReviewStatusFilter] = React.useState('')
  const [duplicateDetections, setDuplicateDetections] = React.useState<DuplicateDetection[]>([])
  const [duplicateError, setDuplicateError] = React.useState('')
  const [comparison, setComparison] = React.useState<DuplicateComparison | null>(null)
  const [comparisonLoadingId, setComparisonLoadingId] = React.useState<number | null>(null)
  const [comparisonError, setComparisonError] = React.useState('')
  const [purchaseOrders, setPurchaseOrders] = React.useState<PurchaseOrder[]>([])
  const [purchaseOrdersLoading, setPurchaseOrdersLoading] = React.useState(false)
  const [purchaseOrderError, setPurchaseOrderError] = React.useState('')
  const [purchaseOrderSaving, setPurchaseOrderSaving] = React.useState(false)
  const [editingPurchaseOrderId, setEditingPurchaseOrderId] = React.useState<number | null>(null)
  const [poNumber, setPoNumber] = React.useState('')
  const [poVendor, setPoVendor] = React.useState('')
  const [poCurrency, setPoCurrency] = React.useState('INR')
  const [poOrderDate, setPoOrderDate] = React.useState('')
  const [poExpectedDate, setPoExpectedDate] = React.useState('')
  const [poTaxRate, setPoTaxRate] = React.useState(0)
  const [poStatus, setPoStatus] = React.useState<PurchaseOrder['status']>('open')
  const [poLineItems, setPoLineItems] = React.useState<PurchaseOrderLineItem[]>([
    { description: '', quantity: 1, unit_price: 0, amount: 0, item_order: 0 },
  ])
  const [comparisonInvoiceId, setComparisonInvoiceId] = React.useState('')
  const [purchaseOrderComparison, setPurchaseOrderComparison] =
    React.useState<PurchaseOrderComparison | null>(null)
  const [vendors, setVendors] = React.useState<VendorProfile[]>([])
  const [vendorsLoading, setVendorsLoading] = React.useState(false)
  const [vendorError, setVendorError] = React.useState('')
  const [vendorSearch, setVendorSearch] = React.useState('')
  const [selectedVendorName, setSelectedVendorName] = React.useState('')
  const [reportData, setReportData] = React.useState<ReportData | null>(null)
  const [reportsLoading, setReportsLoading] = React.useState(false)
  const [reportsError, setReportsError] = React.useState('')
  const [reportDateFrom, setReportDateFrom] = React.useState('')
  const [reportDateTo, setReportDateTo] = React.useState('')
  const [reportVendor, setReportVendor] = React.useState('')
  const [reportCurrency, setReportCurrency] = React.useState('')
  const [reportReviewStatus, setReportReviewStatus] = React.useState('')
  const [reportType, setReportType] = React.useState('invoice_summary')
  const [privacyInfo, setPrivacyInfo] = React.useState<PrivacyInfo | null>(null)
  const [privacyError, setPrivacyError] = React.useState('')
  const [privacyExportError, setPrivacyExportError] = React.useState('')
  const [settings, setSettings] = React.useState<WorkspaceSettings | null>(null)
  const [settingsError, setSettingsError] = React.useState('')
  const [settingsSaving, setSettingsSaving] = React.useState(false)
  const [sourceFileUrl, setSourceFileUrl] = React.useState<string | null>(null)
  const [sourceFileError, setSourceFileError] = React.useState('')
  const [activityEntries, setActivityEntries] = React.useState<InvoiceActivityEntry[]>([])
  const [activityLoading, setActivityLoading] = React.useState(false)
  const [activityError, setActivityError] = React.useState('')
  const [lineItems, setLineItems] = React.useState<LineItem[]>([])
  const [navigationOpen, setNavigationOpen] = React.useState(false)
  const [activeSection, setActiveSection] = React.useState(window.location.hash || '#overview')
  const uploadInput = React.useRef<HTMLInputElement>(null)
  const navigationToggle = React.useRef<HTMLButtonElement>(null)
  const sidebar = React.useRef<HTMLElement>(null)

  React.useEffect(() => {
    const preference = authToken && settings ? settings.appearance : 'light'
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const updateTheme = () => {
      document.documentElement.dataset.theme = preference === 'system'
        ? (media.matches ? 'dark' : 'light')
        : preference
    }
    updateTheme()
    media.addEventListener('change', updateTheme)
    return () => media.removeEventListener('change', updateTheme)
  }, [authToken, settings?.appearance])

  function closeNavigation(restoreFocus = false) {
    setNavigationOpen(false)
    if (restoreFocus) navigationToggle.current?.focus()
  }

  React.useEffect(() => {
    const updateActiveSection = () => setActiveSection(window.location.hash || '#overview')
    window.addEventListener('hashchange', updateActiveSection)
    return () => window.removeEventListener('hashchange', updateActiveSection)
  }, [])

  React.useEffect(() => {
    if (!navigationOpen) return

    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeNavigation(true)
        return
      }
      if (event.key !== 'Tab') return

      const focusableItems = Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [],
      )
      if (!focusableItems.length) return
      const first = focusableItems[0]
      const last = focusableItems[focusableItems.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.body.style.overflow = 'hidden'
    sidebar.current?.querySelector<HTMLAnchorElement>('.nav-link')?.focus()
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [navigationOpen])

  const refresh = React.useCallback(async (resetFilters = false) => {
    setLoading(true)
    setError('')
    setReviewQueueInvoices([])
    setReviewQueueTotal(0)
    setReviewQueueError('')
    try {
      const params = new URLSearchParams({ page: '1', page_size: '100' })
      if (!resetFilters && search) params.set('search', search)
      if (!resetFilters && reviewStatusFilter) params.set('review_status', reviewStatusFilter)
      const [stats, list] = await Promise.all([
        request<Dashboard>('/dashboard'),
        request<{ items: Invoice[]; total: number }>(`/invoices?${params.toString()}`),
      ])
      setDashboard(stats)
      setInvoices(list.items)
      setFocusedInvoice((current) => current
        ? list.items.find((invoice) => invoice.id === current.id) ?? current
        : null)
      setInvoiceTotal(list.total)
      try {
        const queue = await request<{ items: Invoice[]; total: number }>(
          '/invoices?review_status=needs_review&page=1&page_size=100',
        )
        setReviewQueueInvoices(queue.items)
        setReviewQueueTotal(queue.total)
        setReviewQueueError('')
      } catch (reason) {
        setReviewQueueError(reason instanceof Error ? reason.message : String(reason))
      }
      setStatus(`Healthy · ${stats.total_invoices} invoices tracked`)
      try {
        setDuplicateDetections(await request<DuplicateDetection[]>('/duplicate-detections?limit=100'))
        setDuplicateError('')
      } catch (reason) {
        setDuplicateError(reason instanceof Error ? reason.message : String(reason))
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)
      setError(message)
      setStatus('Backend unavailable')
    } finally {
      setLoading(false)
    }
  }, [search, reviewStatusFilter])

  React.useEffect(() => {
    const handleUnauthorized = () => setAuthToken(null)
    window.addEventListener('invoice-detective-unauthorized', handleUnauthorized)
    return () => window.removeEventListener('invoice-detective-unauthorized', handleUnauthorized)
  }, [])

  React.useEffect(() => {
    let active = true
    if (!authToken) {
      setAuthChecking(false)
      return () => { active = false }
    }

    request<{ user: { email: string; role: string }; workspace: { name: string } }>('/auth/me')
      .then((session) => {
        if (active) {
          setProfile({
            email: session.user.email,
            role: session.user.role,
            workspaceName: session.workspace.name,
          })
        }
      })
      .catch(() => {
        if (active) {
          sessionStorage.removeItem(AUTH_TOKEN_KEY)
          setAuthToken(null)
        }
      })
      .finally(() => {
        if (active) setAuthChecking(false)
      })
    return () => { active = false }
  }, [])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setLoading(false)
      return
    }
    void refresh()
  }, [authToken, authChecking, refresh])

  const selected = focusedInvoice?.id === selectedId
    ? focusedInvoice
    : invoices.find((invoice) => invoice.id === selectedId) ?? null
  const filteredVendors = vendors.filter((vendor) => (
    vendor.name.toLocaleLowerCase().includes(vendorSearch.trim().toLocaleLowerCase())
  ))
  const selectedVendor = vendors.find((vendor) => vendor.name === selectedVendorName) ?? null
  const reportRows = (reportData?.items ?? []).filter((item) => {
    if (reportType === 'duplicate_detection') return item.duplicate_matches > 0
    if (reportType === 'due_dates') return Boolean(item.due_date)
    return true
  })

  React.useEffect(() => {
    setLineItems(selected?.line_items ?? [])
  }, [selectedId, selected])

  React.useEffect(() => {
    let active = true
    let objectUrl: string | null = null
    setSourceFileUrl(null)
    setSourceFileError('')
    if (!selected || !authToken || authChecking) return

    requestFile(`/invoices/${selected.id}/file`)
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setSourceFileUrl(objectUrl)
      })
      .catch((reason) => {
        if (active) setSourceFileError(reason instanceof Error ? reason.message : String(reason))
      })

    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selected?.id, authToken, authChecking])

  React.useEffect(() => {
    let active = true
    setActivityEntries([])
    setActivityError('')
    if (!selected || !authToken || authChecking) {
      setActivityLoading(false)
      return
    }

    setActivityLoading(true)
    request<{ items: InvoiceActivityEntry[] }>(`/invoices/${selected.id}/activity`)
      .then((result) => {
        if (active) setActivityEntries(result.items)
      })
      .catch((reason) => {
        if (active) setActivityError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => {
        if (active) setActivityLoading(false)
      })

    return () => { active = false }
  }, [selected?.id, authToken, authChecking])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setPrivacyInfo(null)
      setPrivacyError('')
      return
    }
    let active = true
    request<PrivacyInfo>('/privacy')
      .then((info) => {
        if (active) setPrivacyInfo(info)
      })
      .catch((reason) => {
        if (active) setPrivacyError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => {
      active = false
    }
  }, [authToken, authChecking])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setVendors([])
      setVendorError('')
      setVendorsLoading(false)
      setSelectedVendorName('')
      return
    }

    let active = true
    setVendorsLoading(true)
    setVendorError('')
    request<VendorProfile[]>('/vendors')
      .then((items) => {
        if (!active) return
        setVendors(items)
        setSelectedVendorName((current) => (
          items.some((vendor) => vendor.name === current) ? current : items[0]?.name ?? ''
        ))
      })
      .catch((reason) => {
        if (active) setVendorError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => {
        if (active) setVendorsLoading(false)
      })
    return () => {
      active = false
    }
  }, [authToken, authChecking])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setReportData(null)
      setReportsError('')
      setReportsLoading(false)
      return
    }

    let active = true
    setReportsLoading(true)
    setReportsError('')
    request<ReportData>('/reports/summary')
      .then((data) => {
        if (active) setReportData(data)
      })
      .catch((reason) => {
        if (active) setReportsError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => {
        if (active) setReportsLoading(false)
      })
    return () => {
      active = false
    }
  }, [authToken, authChecking])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setSettings(null)
      setSettingsError('')
      return
    }
    let active = true
    request<WorkspaceSettings>('/settings')
      .then((value) => {
        if (active) setSettings(value)
      })
      .catch((reason) => {
        if (active) setSettingsError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => {
      active = false
    }
  }, [authToken, authChecking])

  React.useEffect(() => {
    if (!authToken || authChecking) {
      setPurchaseOrders([])
      setPurchaseOrderError('')
      setPurchaseOrdersLoading(false)
      return
    }

    let active = true
    setPurchaseOrdersLoading(true)
    setPurchaseOrderError('')
    request<PurchaseOrder[]>('/purchase-orders')
      .then((orders) => {
        if (active) setPurchaseOrders(orders)
      })
      .catch((reason) => {
        if (active) setPurchaseOrderError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => {
        if (active) setPurchaseOrdersLoading(false)
      })
    return () => {
      active = false
    }
  }, [authToken, authChecking])

  async function authenticate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const registering = authMode === 'register'
    try {
      const session = await request<AuthResponse>(registering ? '/auth/register' : '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(registering
          ? { email: authEmail, password: authPassword, workspace_name: workspaceName }
          : { email: authEmail, password: authPassword }),
      })
      sessionStorage.setItem(AUTH_TOKEN_KEY, session.access_token)
      setAuthToken(session.access_token)
      setProfile({
        email: session.user.email,
        role: session.user.role,
        workspaceName: session.workspace.name,
      })
      setAuthPassword('')
      setError('')
      setNotice(`Signed in to ${session.workspace.name}.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    let logoutError = ''
    try {
      await request('/auth/logout', { method: 'POST' })
    } catch (reason) {
      logoutError = reason instanceof Error ? reason.message : String(reason)
    }
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    setAuthToken(null)
    setProfile(null)
    closeNavigation()
    setDashboard(null)
    setInvoices([])
    setInvoiceTotal(0)
    setSelectedId(null)
    setFocusedInvoice(null)
    setPrivacyInfo(null)
    setPurchaseOrders([])
    setPurchaseOrderComparison(null)
    setNotice('')
    setError(logoutError ? `Signed out here, but the server could not revoke the session: ${logoutError}` : '')
  }

  async function downloadCsv() {
    setReportsError('')
    try {
      saveBlob(await requestFile(`/reports/summary.csv?${reportQueryString()}`), 'filtered-invoice-report.csv')
      setNotice('Filtered invoice report downloaded.')
    } catch (reason) {
      setReportsError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function downloadPrivacyExport(path: string, filename: string, label: string) {
    setPrivacyExportError('')
    try {
      saveBlob(await requestFile(path), filename)
      setNotice(`${label} downloaded.`)
    } catch (reason) {
      setPrivacyExportError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function reportQueryString() {
    const params = new URLSearchParams()
    if (reportDateFrom) params.set('date_from', reportDateFrom)
    if (reportDateTo) params.set('date_to', reportDateTo)
    if (reportVendor.trim()) params.set('vendor', reportVendor.trim())
    if (reportCurrency) params.set('currency', reportCurrency)
    if (reportReviewStatus) params.set('review_status', reportReviewStatus)
    params.set('report_type', reportType)
    return params.toString()
  }

  async function loadReports(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setReportsError('')
    setReportsLoading(true)
    try {
      const query = reportQueryString()
      setReportData(await request<ReportData>(`/reports/summary${query ? `?${query}` : ''}`))
    } catch (reason) {
      setReportsError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setReportsLoading(false)
    }
  }

  function resetPurchaseOrderForm() {
    setEditingPurchaseOrderId(null)
    setPoNumber('')
    setPoVendor('')
    setPoCurrency('INR')
    setPoOrderDate('')
    setPoExpectedDate('')
    setPoTaxRate(0)
    setPoStatus('open')
    setPoLineItems([{ description: '', quantity: 1, unit_price: 0, amount: 0, item_order: 0 }])
    setPurchaseOrderError('')
  }

  function editPurchaseOrder(order: PurchaseOrder) {
    setEditingPurchaseOrderId(order.id)
    setPoNumber(order.po_number)
    setPoVendor(order.vendor_name)
    setPoCurrency(order.currency)
    setPoOrderDate(order.order_date ?? '')
    setPoExpectedDate(order.expected_delivery_date ?? '')
    setPoTaxRate(order.tax_rate)
    setPoStatus(order.status)
    setPoLineItems(order.line_items.map((item, index) => ({ ...item, item_order: index })))
    setPurchaseOrderError('')
    document.getElementById('purchase-order-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function updatePurchaseOrderLineItem(index: number, patch: Partial<PurchaseOrderLineItem>) {
    setPoLineItems((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )))
  }

  async function savePurchaseOrder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPurchaseOrderError('')
    setPurchaseOrderSaving(true)
    const payload = {
      po_number: poNumber.trim(),
      vendor_name: poVendor.trim(),
      currency: poCurrency.trim().toUpperCase(),
      order_date: poOrderDate,
      expected_delivery_date: poExpectedDate || null,
      tax_rate: poTaxRate,
      status: poStatus,
      line_items: poLineItems.map(({ description, quantity, unit_price }) => ({
        description: description.trim(),
        quantity,
        unit_price,
      })),
    }
    try {
      const saved = await request<PurchaseOrder>(
        editingPurchaseOrderId
          ? `/purchase-orders/${editingPurchaseOrderId}`
          : '/purchase-orders',
        {
          method: editingPurchaseOrderId ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      setPurchaseOrders((current) => editingPurchaseOrderId
        ? current.map((order) => order.id === saved.id ? saved : order)
        : [saved, ...current])
      setNotice(`Purchase order ${saved.po_number} ${editingPurchaseOrderId ? 'updated' : 'created'}.`)
      resetPurchaseOrderForm()
    } catch (reason) {
      setPurchaseOrderError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setPurchaseOrderSaving(false)
    }
  }

  async function deletePurchaseOrder(order: PurchaseOrder) {
    if (!window.confirm(`Delete purchase order ${order.po_number}? This cannot be undone.`)) return
    setPurchaseOrderSaving(true)
    setPurchaseOrderError('')
    try {
      await request<void>(`/purchase-orders/${order.id}`, { method: 'DELETE' })
      setPurchaseOrders((current) => current.filter((item) => item.id !== order.id))
      if (editingPurchaseOrderId === order.id) resetPurchaseOrderForm()
      setNotice(`Purchase order ${order.po_number} deleted.`)
    } catch (reason) {
      setPurchaseOrderError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setPurchaseOrderSaving(false)
    }
  }

  async function comparePurchaseOrder(order: PurchaseOrder) {
    if (!comparisonInvoiceId) {
      setPurchaseOrderError('Choose an invoice to compare with this purchase order.')
      return
    }
    setPurchaseOrderSaving(true)
    setPurchaseOrderError('')
    setPurchaseOrderComparison(null)
    try {
      const result = await request<PurchaseOrderComparison>(
        `/purchase-orders/${order.id}/invoices/${comparisonInvoiceId}/compare`,
        { method: 'POST' },
      )
      setPurchaseOrderComparison(result)
      setNotice(`Compared ${order.po_number} with invoice #${comparisonInvoiceId}.`)
    } catch (reason) {
      setPurchaseOrderError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setPurchaseOrderSaving(false)
    }
  }

  async function saveSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSettingsError('')
    setSettingsSaving(true)
    const form = new FormData(event.currentTarget)
    const taxRate = String(form.get('default_tax_rate') ?? '').trim()
    const payload = {
      workspace_name: String(form.get('workspace_name') ?? '').trim(),
      business_name: String(form.get('business_name') ?? '').trim(),
      default_currency: String(form.get('default_currency') ?? 'INR'),
      date_format: String(form.get('date_format') ?? 'YYYY-MM-DD'),
      time_zone: String(form.get('time_zone') ?? 'Asia/Kolkata'),
      language: String(form.get('language') ?? 'en'),
      default_tax_rate: taxRate ? Number(taxRate) : null,
      invoice_number_prefix: String(form.get('invoice_number_prefix') ?? '').trim(),
      default_review_status: String(form.get('default_review_status') ?? 'needs_review'),
      notify_audit_completion: form.has('notify_audit_completion'),
      notify_duplicate_detection: form.has('notify_duplicate_detection'),
      notify_failed_upload: form.has('notify_failed_upload'),
      notify_review_reminders: form.has('notify_review_reminders'),
      profile_display_name: String(form.get('profile_display_name') ?? '').trim(),
      appearance: String(form.get('appearance') ?? 'light'),
    }
    try {
      const saved = await request<WorkspaceSettings>('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setSettings(saved)
      setProfile((current) => current
        ? { ...current, workspaceName: saved.workspace_name }
        : current)
      setNotice('Workspace settings saved.')
    } catch (reason) {
      setSettingsError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setSettingsSaving(false)
    }
  }

  async function downloadInvoiceFile(invoice: Invoice) {
    setError('')
    try {
      const extension = invoice.file_type.toLowerCase()
      saveBlob(await requestFile(`/invoices/${invoice.id}/file`), `invoice-${invoice.id}${extension}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function selectInvoiceFile(candidate: File | undefined) {
    setError('')
    setNotice('')
    if (!candidate) {
      setFile(null)
      return
    }

    const extension = candidate.name.toLowerCase().slice(candidate.name.lastIndexOf('.'))
    const expectedMime: Record<string, string> = {
      '.pdf': 'application/pdf',
      '.png': 'image/png',
      '.jpg': 'image/jpeg',
      '.jpeg': 'image/jpeg',
    }
    if (!expectedMime[extension]) {
      setFile(null)
      setError('Unsupported invoice file. Choose a PDF, PNG, JPG, or JPEG document.')
      if (uploadInput.current) uploadInput.current.value = ''
      return
    }
    if (candidate.type && candidate.type !== expectedMime[extension]) {
      setFile(null)
      setError('The selected file type does not match its filename. Choose a valid PDF, PNG, or JPEG invoice.')
      if (uploadInput.current) uploadInput.current.value = ''
      return
    }
    if (privacyInfo && candidate.size > privacyInfo.max_file_size_bytes) {
      setFile(null)
      setError(`The selected file exceeds the configured ${Math.floor(privacyInfo.max_file_size_bytes / (1024 * 1024))} MB limit.`)
      if (uploadInput.current) uploadInput.current.value = ''
      return
    }
    setFile(candidate)
  }

  async function loadMoreInvoices() {
    setLoadingMore(true)
    setError('')
    try {
      const page = Math.floor(invoices.length / 100) + 1
      const params = new URLSearchParams({ page: String(page), page_size: '100' })
      if (search) params.set('search', search)
      if (reviewStatusFilter) params.set('review_status', reviewStatusFilter)
      const list = await request<{ items: Invoice[]; total: number }>(`/invoices?${params.toString()}`)
      setInvoices((current) => [...current, ...list.items])
      setInvoiceTotal(list.total)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLoadingMore(false)
    }
  }

  async function uploadInvoice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file) {
      setError('Choose a PDF, PNG, or JPEG invoice before uploading.')
      return
    }

    setBusy(true)
    setError('')
    setNotice('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const uploaded = await request<Invoice>('/invoices/upload', {
        method: 'POST',
        body: formData,
      })
      setFocusedInvoice(uploaded)
      setSelectedId(uploaded.id)
      setSearchText('')
      setSearch('')
      setReviewStatusFilter('')
      setFile(null)
      if (uploadInput.current) uploadInput.current.value = ''
      setNotice(uploaded.processing_error
        ? `${uploaded.original_filename} was saved, but extraction needs review: ${uploaded.processing_error}`
        : `${uploaded.original_filename} was uploaded. Review the extracted fields below.`)
      await refresh(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  function updateLineItem(index: number, patch: Partial<LineItem>) {
    setLineItems((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )))
  }

  async function saveInvoice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return

    const form = new FormData(event.currentTarget)
    const optionalText = (key: string) => String(form.get(key) ?? '').trim() || null
    const optionalNumber = (key: string) => {
      const value = String(form.get(key) ?? '').trim()
      return value ? Number(value) : null
    }
    const payload = {
      vendor_name: optionalText('vendor_name'),
      invoice_number: optionalText('invoice_number'),
      invoice_date: optionalText('invoice_date'),
      due_date: optionalText('due_date'),
      currency: optionalText('currency') || 'INR',
      vendor_address: optionalText('vendor_address'),
      subtotal: optionalNumber('subtotal'),
      tax_amount: optionalNumber('tax_amount'),
      tax_rate: optionalNumber('tax_rate'),
      discount_amount: optionalNumber('discount_amount'),
      total_amount: optionalNumber('total_amount'),
      gstin: optionalText('gstin'),
      notes: optionalText('notes'),
      review_status: String(form.get('review_status')),
    }
    const lineItemsPayload = lineItems.map((item, itemOrder) => ({
      description: item.description?.trim() || null,
      quantity: item.quantity,
      unit_price: item.unit_price,
      amount: item.amount,
      item_order: itemOrder,
    }))

    const numericValues = [
      ...Object.values(payload),
      ...lineItemsPayload.flatMap((item) => [item.quantity, item.unit_price, item.amount]),
    ]
    if (numericValues.some((value) => typeof value === 'number' && !Number.isFinite(value))) {
      setError('Amounts must be valid numbers.')
      return
    }

    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await request<Invoice>(`/invoices/${selected.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, line_items: lineItemsPayload }),
      })
      setFocusedInvoice(updated)
      setNotice('Invoice corrections saved and checks rerun.')
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function deleteInvoice(invoice: Invoice) {
    if (!window.confirm(`Delete ${invoice.original_filename} and its stored file?`)) return

    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request(`/invoices/${invoice.id}`, { method: 'DELETE' })
      setFocusedInvoice(null)
      setSelectedId(null)
      setNotice(`${invoice.original_filename} was deleted.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function updateFindingReview(invoiceId: number, findingId: number, reviewStatus: string) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request(`/invoices/${invoiceId}/findings/${findingId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_status: reviewStatus }),
      })
      setNotice('Finding review status updated.')
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function compareDuplicate(detection: DuplicateDetection) {
    setComparison(null)
    setComparisonError('')
    setComparisonLoadingId(detection.id)
    try {
      const [source, matched] = await Promise.all([
        detection.source_invoice_id
          ? request<Invoice>(`/invoices/${detection.source_invoice_id}`)
          : Promise.resolve(null),
        request<Invoice>(`/invoices/${detection.matched_invoice_id}`),
      ])
      setComparison({ detection, source, matched })
    } catch (reason) {
      setComparisonError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setComparisonLoadingId(null)
    }
  }

  const needsReview = dashboard?.invoices_by_status?.needs_review ?? invoices.filter((invoice) => invoice.review_status === 'needs_review').length
  const reviewCounts = [
    { key: 'needs_review', label: 'Needs review', count: dashboard?.invoices_by_status?.needs_review ?? 0 },
    { key: 'reviewed', label: 'Reviewed', count: dashboard?.invoices_by_status?.reviewed ?? 0 },
    { key: 'resolved', label: 'Resolved', count: dashboard?.invoices_by_status?.resolved ?? 0 },
  ]
  const reviewTotal = reviewCounts.reduce((total, item) => total + item.count, 0)
  const comparisonFields = comparison ? [
    { label: 'Vendor', source: comparison.source?.vendor_name ?? 'Not persisted', matched: comparison.matched.vendor_name ?? 'Not extracted' },
    { label: 'Invoice number', source: comparison.source?.invoice_number ?? 'Not persisted', matched: comparison.matched.invoice_number ?? 'Not extracted' },
    { label: 'Invoice date', source: comparison.source?.invoice_date ?? 'Not persisted', matched: comparison.matched.invoice_date ?? 'Not extracted' },
    {
      label: 'Total',
      source: comparison.source
        ? comparison.source.total_amount == null ? 'Not extracted' : `${comparison.source.currency} ${comparison.source.total_amount.toLocaleString()}`
        : 'Upload not retained',
      matched: comparison.matched.total_amount == null
        ? 'Not extracted'
        : `${comparison.matched.currency} ${comparison.matched.total_amount.toLocaleString()}`,
    },
    { label: 'Review status', source: comparison.source?.review_status.replace(/_/g, ' ') ?? 'Not persisted', matched: comparison.matched.review_status.replace(/_/g, ' ') },
  ] : []
  const invoiceVolume = dashboard?.invoice_volume_by_month ?? []
  const monthlySpend = dashboard?.spend_by_month ?? []
  const vendorSpend = dashboard?.vendor_spend ?? []
  const severityBreakdown = Object.entries(dashboard?.findings_by_severity ?? {})
    .sort((left, right) => right[1] - left[1])
  const maxMonthlyVolume = Math.max(1, ...invoiceVolume.map((row) => row.count))
  const maxSeverity = Math.max(1, ...severityBreakdown.map(([, count]) => count))
  const monthlySpendMax = new Map<string, number>()
  monthlySpend.forEach((row) => monthlySpendMax.set(
    row.currency,
    Math.max(monthlySpendMax.get(row.currency) ?? 0, row.amount),
  ))
  const vendorSpendMax = new Map<string, number>()
  vendorSpend.forEach((row) => vendorSpendMax.set(
    row.currency,
    Math.max(vendorSpendMax.get(row.currency) ?? 0, row.amount),
  ))
  const currentDate = new Date()
  const currentDateIso = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(currentDate.getDate()).padStart(2, '0')}`
  const currentDateLabel = new Intl.DateTimeFormat(undefined, { dateStyle: 'long' }).format(currentDate)

  if (authChecking) {
    return (
      <main className="auth-page">
        <section className="auth-card" aria-live="polite">
          <p className="eyebrow">PRIVATE WORKSPACE</p>
          <h1>Checking your session…</h1>
        </section>
      </main>
    )
  }

  if (!authToken) {
    return (
      <main className="auth-page">
        <section className="auth-card">
          <div className="auth-brand">
            <span className="auth-brand-mark" aria-hidden="true">ID</span>
            <span><strong>Invoice Detective</strong><small>Intelligent Invoice Audit Platform</small></span>
          </div>
          <p className="eyebrow">PRIVATE WORKSPACE</p>
          <h1>{authMode === 'register' ? 'Create your workspace.' : 'Welcome back.'}</h1>
          <p className="auth-intro">
            {authMode === 'register'
              ? 'Create a local account to keep your invoice records private to your workspace.'
              : 'Sign in to review invoices and audit findings in your workspace.'}
          </p>
          {error && <p className="error" role="alert">{error}</p>}
          <form className="auth-form" onSubmit={(event) => void authenticate(event)}>
            <label htmlFor="auth-email">Email address
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                maxLength={254}
                required
                value={authEmail}
                onChange={(event) => setAuthEmail(event.currentTarget.value)}
              />
            </label>
            <label htmlFor="auth-password">Password
              <input
                id="auth-password"
                type="password"
                autoComplete={authMode === 'register' ? 'new-password' : 'current-password'}
                minLength={authMode === 'register' ? 12 : undefined}
                maxLength={128}
                required
                value={authPassword}
                onChange={(event) => setAuthPassword(event.currentTarget.value)}
              />
            </label>
            {authMode === 'register' && (
              <label htmlFor="workspace-name">Workspace name
                <input
                  id="workspace-name"
                  maxLength={100}
                  required
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.currentTarget.value)}
                />
              </label>
            )}
            <button className="button auth-submit" type="submit" disabled={busy}>
              {busy ? 'Working…' : authMode === 'register' ? 'Create account' : 'Sign in'}
            </button>
          </form>
          <button
            className="text-button auth-mode-toggle"
            type="button"
            onClick={() => {
              setAuthMode((mode) => mode === 'login' ? 'register' : 'login')
              setError('')
            }}
          >
            {authMode === 'register' ? 'Already have a local account? Sign in' : 'New here? Create a workspace'}
          </button>
          <p className="auth-local-note">
            Local development only. Email verification, password recovery, and production account protections are not configured.
          </p>
        </section>
      </main>
    )
  }

  return (
    <div className="app-layout">
      {navigationOpen && (
        <button
          className="nav-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => closeNavigation(true)}
        />
      )}
      <aside
        ref={sidebar}
        className={`sidebar${navigationOpen ? ' sidebar-open' : ''}`}
        id="workspace-sidebar"
        aria-label="Workspace navigation"
      >
        <a className="brand-lockup" href="#overview">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 40 40" focusable="false">
              <path d="M20 3.5 34 8v10.5c0 8.6-5.8 15.1-14 18-8.2-2.9-14-9.4-14-18V8l14-4.5Z" />
              <path d="M13.5 20.5 18 25l9-10" />
            </svg>
          </span>
          <span className="brand-copy">
            <strong>Invoice <b>Detective</b></strong>
            <small>Intelligent Invoice Audit Platform</small>
          </span>
        </a>
        <button className="sidebar-close" type="button" onClick={() => closeNavigation(true)}>
          Close menu
        </button>

        <p className="nav-caption">WORKSPACE</p>
        <nav className="side-nav">
          <a className="nav-link" href="#overview" aria-current={activeSection === '#overview' ? 'page' : undefined} onClick={() => closeNavigation()}>Overview</a>
          <a className="nav-link" href="#upload" aria-current={activeSection === '#upload' ? 'page' : undefined} onClick={() => closeNavigation()}>Upload invoice</a>
          <a className="nav-link" href="#invoices" aria-current={activeSection === '#invoices' ? 'page' : undefined} onClick={() => closeNavigation()}>Invoice history</a>
          <a className="nav-link" href="#review" aria-current={activeSection === '#review' ? 'page' : undefined} onClick={() => closeNavigation()}>Review queue</a>
          <a className="nav-link" href="#duplicates" aria-current={activeSection === '#duplicates' ? 'page' : undefined} onClick={() => closeNavigation()}>Duplicate checks</a>
          <a className="nav-link" href="#purchase-orders" aria-current={activeSection === '#purchase-orders' ? 'page' : undefined} onClick={() => closeNavigation()}>Purchase orders</a>
          <a className="nav-link" href="#vendor-intelligence" aria-current={activeSection === '#vendor-intelligence' ? 'page' : undefined} onClick={() => closeNavigation()}>Vendor intelligence</a>
          <a className="nav-link" href="#reports" aria-current={activeSection === '#reports' ? 'page' : undefined} onClick={() => closeNavigation()}>Reports & exports</a>
          <a className="nav-link" href="#privacy" aria-current={activeSection === '#privacy' ? 'page' : undefined} onClick={() => closeNavigation()}>Data & privacy</a>
          <a className="nav-link" href="#settings" aria-current={activeSection === '#settings' ? 'page' : undefined} onClick={() => closeNavigation()}>Settings</a>
        </nav>

        <div className="sidebar-note">
          <span className="live-dot" aria-hidden="true" />
          <div><strong>Local workspace</strong><small>Documents stay on this machine</small></div>
        </div>
      </aside>

      <main className="app-shell">
        <header className="topbar" id="overview">
          <div className="hero-copy">
            <p className="eyebrow">WELCOME BACK · FINANCE CONTROL CENTER</p>
            <h1>Make every invoice <span>earn its place.</span></h1>
            <p className="hero-subtitle">A second set of eyes for the details that deserve a closer look.</p>
            <p className="hero-workspace">
              {profile?.workspaceName ?? 'Workspace'} · <time dateTime={currentDateIso}>{currentDateLabel}</time>
            </p>
          </div>
          <div className="topbar-actions">
            <button
              ref={navigationToggle}
              className="button button-secondary nav-toggle"
              type="button"
              aria-expanded={navigationOpen}
              aria-controls="workspace-sidebar"
              onClick={() => setNavigationOpen((open) => !open)}
            >
              <span className="menu-icon" aria-hidden="true" />
              {navigationOpen ? 'Close menu' : 'Menu'}
            </button>
            <span className={`status-pill ${status === 'Backend unavailable' ? 'status-error' : ''}`} role="status">
              <span className="live-dot" aria-hidden="true" />{status}
            </span>
            <a className="button button-secondary review-indicator" href="#review">
              Review queue <span>{dashboard ? needsReview : '—'}</span>
            </a>
            <details className="topbar-menu notification-menu">
              <summary aria-label="Open notification center">
                Alerts <span className="notification-count">{dashboard ? needsReview : '—'}</span>
              </summary>
              <div className="menu-popover">
                <strong>Workspace alerts</strong>
                <p>{dashboard ? needsReview : '—'} invoices are waiting for review.</p>
                <p>{dashboard?.total_findings ?? '—'} audit findings are saved for human review.</p>
                <a href="#review" onClick={() => setNavigationOpen(false)}>Open review queue</a>
              </div>
            </details>
            <button className="button button-secondary" type="button" onClick={() => void refresh()} disabled={loading}>
              Refresh
            </button>
            <a className="button" href="#upload">New review <span aria-hidden="true">+</span></a>
            <details className="topbar-menu profile-menu">
              <summary aria-label="Open profile menu">
                <span className="profile-avatar" aria-hidden="true">{profile?.email.slice(0, 1).toUpperCase() ?? 'L'}</span>
                <span className="profile-label">
                  <strong>{profile?.email ?? 'Local account'}</strong>
                  <small>{profile?.workspaceName ?? 'Workspace'} · {profile?.role ?? 'local'}</small>
                </span>
              </summary>
              <div className="menu-popover">
                <p><strong>{profile?.workspaceName ?? 'Workspace'}</strong></p>
                <p className="muted">{profile?.email ?? 'Local account'}</p>
                <button className="button button-secondary" type="button" onClick={() => void logout()}>Sign out</button>
              </div>
            </details>
          </div>
        </header>

      <section className="stats-grid" aria-label="Invoice summary">
        <div className="stat-card">
          <div className="stat-title"><span className="stat-label">Invoices tracked</span></div>
          <strong>{dashboard?.total_invoices ?? '—'}</strong>
          <small>All records in this workspace</small>
        </div>
        <div className="stat-card">
          <div className="stat-title"><span className="stat-label">Invoice value</span></div>
          <strong className="stat-currency-value">{dashboard ? formatCurrencyBreakdown(dashboard.invoice_value_by_currency) : '—'}</strong>
          <small>Summed separately by currency</small>
        </div>
        <div className="stat-card">
          <div className="stat-title"><span className="stat-label">Needs review</span></div>
          <strong>{dashboard ? needsReview : '—'}</strong>
          <small>Waiting for a human decision</small>
        </div>
        <div className="stat-card">
          <div className="stat-title"><span className="stat-label">Audit findings</span></div>
          <strong>{dashboard?.total_findings ?? '—'}</strong>
          <small>Potential issues, not fraud verdicts</small>
        </div>
        <div className="stat-card">
          <div className="stat-title"><span className="stat-label">Potential duplicate value</span></div>
          <strong className="stat-currency-value">{dashboard ? formatCurrencyBreakdown(dashboard.potential_duplicate_value_by_currency) : '—'}</strong>
          <small>Flagged amounts need human review</small>
        </div>
      </section>

      <section className="overview-grid" aria-label="Review overview and invoice upload">
        <div className="panel status-chart">
          <div className="section-heading">
            <div><p className="eyebrow">LIVE WORKFLOW</p><h2>Review status</h2></div>
            <span className="chart-total">{reviewTotal}</span>
          </div>
          <div className="status-bars">
            {reviewCounts.map((item) => (
              <div className="status-bar-row" key={item.key}>
                <div><span>{item.label}</span><strong>{item.count}</strong></div>
                <div className="status-bar-track" aria-hidden="true">
                  <span className={`status-bar-fill fill-${item.key}`} style={{ width: `${reviewTotal ? (item.count / reviewTotal) * 100 : 0}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="chart-caption">Status totals reflect saved invoice records. Every flag is a prompt for review.</p>
        </div>

      {error && (
        <section className="error" role="alert">
          <strong>Could not complete the request.</strong>
          <p>{error}</p>
          <small>API: {API_BASE}</small>
        </section>
      )}
      {notice && <p className="notice" role="status">{notice}</p>}

      <section className="panel upload-panel" id="upload">
        <div>
          <p className="eyebrow">01 / START A REVIEW</p>
          <h2>Bring in a source document</h2>
          <p className="muted">PDF, PNG, or JPEG</p>
        </div>
        <div className="upload-controls">
          <form className="upload-form" onSubmit={uploadInvoice} aria-busy={busy}>
            <label className="visually-hidden" htmlFor="invoice-file">Invoice file</label>
            <div
              className={`upload-dropzone${uploadDragActive ? ' upload-drag-active' : ''}`}
              onDragOver={(event) => {
                event.preventDefault()
                setUploadDragActive(true)
              }}
              onDragLeave={(event) => {
                if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) {
                  setUploadDragActive(false)
                }
              }}
              onDrop={(event) => {
                event.preventDefault()
                setUploadDragActive(false)
                selectInvoiceFile(event.dataTransfer.files.item(0) ?? undefined)
              }}
            >
              <p>Drop an invoice here or choose a file</p>
              <input
                ref={uploadInput}
                id="invoice-file"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                aria-describedby="upload-help"
                onChange={(event) => selectInvoiceFile(event.currentTarget.files?.[0])}
              />
            </div>
            <button className="button" type="submit" disabled={busy || !file}>
              {busy ? 'Uploading and checking…' : 'Upload and check'}
            </button>
          </form>
          <p id="upload-help" className="upload-help">
            PDF, PNG, JPG, or JPEG. Maximum size: {privacyInfo
              ? `${Math.floor(privacyInfo.max_file_size_bytes / (1024 * 1024))} MB`
              : 'configured by the server'}.
          </p>
          {file && <p className="upload-selection" role="status">Selected: {file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB</p>}
        </div>
      </section>
      </section>

      <section className="analytics-grid" aria-label="Financial analytics">
        <article className="panel analytics-card">
          <div className="section-heading">
            <div><p className="eyebrow">LAST 12 MONTHS</p><h2>Invoice volume</h2></div>
            <span className="muted">{invoiceVolume.reduce((sum, row) => sum + row.count, 0)} records</span>
          </div>
          {loading && !dashboard ? (
            <p className="empty-state" role="status">Loading invoice trends…</p>
          ) : invoiceVolume.length === 0 ? (
            <p className="empty-state">Monthly trends will appear after invoices are saved.</p>
          ) : (
            <div className="chart-list">
              {invoiceVolume.map((row) => (
                <div className="chart-row" key={row.month}>
                  <span>{formatMonth(row.month)}</span>
                  <div className="chart-track" aria-hidden="true">
                    <span className="chart-fill" style={{ width: `${(row.count / maxMonthlyVolume) * 100}%` }} />
                  </div>
                  <strong>{row.count}</strong>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="panel analytics-card">
          <div className="section-heading">
            <div><p className="eyebrow">RECORDED TOTALS</p><h2>Monthly spend</h2></div>
            <span className="muted">Compared within each currency</span>
          </div>
          {loading && !dashboard ? (
            <p className="empty-state" role="status">Loading spending trends…</p>
          ) : monthlySpend.length === 0 ? (
            <p className="empty-state">Spending trends will appear when invoices have extracted totals.</p>
          ) : (
            <div className="chart-list">
              {monthlySpend.map((row) => (
                <div className="chart-row chart-row-spend" key={`${row.month}-${row.currency}`}>
                  <span>{formatMonth(row.month)} · {row.currency}</span>
                  <div className="chart-track" aria-hidden="true">
                    <span className="chart-fill chart-fill-gold" style={{
                      width: `${(row.amount / (monthlySpendMax.get(row.currency) || 1)) * 100}%`,
                    }} />
                  </div>
                  <strong>{formatCurrency(row.amount, row.currency)}</strong>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="panel analytics-card">
          <div className="section-heading">
            <div><p className="eyebrow">VENDOR BREAKDOWN</p><h2>Top vendors</h2></div>
            <span className="muted">Top 10 by recorded value</span>
          </div>
          {loading && !dashboard ? (
            <p className="empty-state" role="status">Loading vendor totals…</p>
          ) : vendorSpend.length === 0 ? (
            <p className="empty-state">Vendor totals will appear after invoice data is saved.</p>
          ) : (
            <div className="chart-list vendor-chart">
              {vendorSpend.map((row) => (
                <div className="vendor-row" key={`${row.vendor}-${row.currency}`}>
                  <div className="vendor-row-heading">
                    <strong>{row.vendor}</strong>
                    <span>{formatCurrency(row.amount, row.currency)} · {row.invoice_count} invoices</span>
                  </div>
                  <div className="chart-track" aria-hidden="true">
                    <span className="chart-fill" style={{
                      width: `${(row.amount / (vendorSpendMax.get(row.currency) || 1)) * 100}%`,
                    }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="panel analytics-card">
          <div className="section-heading">
            <div><p className="eyebrow">HUMAN REVIEW</p><h2>Finding severity</h2></div>
            <span className="muted">{dashboard?.total_findings ?? '—'} findings</span>
          </div>
          {!dashboard ? (
            <p className="empty-state" role="status">Loading audit findings…</p>
          ) : severityBreakdown.length === 0 ? (
            <p className="empty-state">No audit findings have been saved.</p>
          ) : (
            <div className="chart-list">
              {severityBreakdown.map(([severity, count]) => (
                <div className="chart-row" key={severity}>
                  <span className={`severity severity-${severity}`}>{severity}</span>
                  <div className="chart-track" aria-hidden="true">
                    <span className={`chart-fill chart-fill-${severity}`} style={{ width: `${(count / maxSeverity) * 100}%` }} />
                  </div>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>
          )}
          <p className="chart-caption">Flags are potential issues for a person to review, not fraud verdicts.</p>
        </article>
      </section>

      <section className="panel recent-activity" aria-labelledby="recent-activity-title">
        <div className="section-heading">
          <div><p className="eyebrow">LATEST RECORDS</p><h2 id="recent-activity-title">Recent activity</h2></div>
          <a className="text-button" href="#invoices">View invoice history</a>
        </div>
        {loading && !dashboard ? (
          <p className="empty-state" role="status">Loading recent invoices…</p>
        ) : !dashboard?.recent_invoices.length ? (
          <div className="recent-empty">
            <p>No invoices have been uploaded to this workspace yet.</p>
            <a className="button button-secondary" href="#upload">Upload an invoice</a>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Vendor</th><th>Invoice #</th><th>Amount</th><th>Uploaded</th><th>Review status</th><th><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {dashboard.recent_invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td>{invoice.vendor_name ?? 'Unknown vendor'}</td>
                    <td>{invoice.invoice_number ?? '—'}</td>
                    <td>{invoice.total_amount == null ? 'Not extracted' : formatCurrency(invoice.total_amount, invoice.currency)}</td>
                    <td>{formatDate(invoice.uploaded_at, settings?.date_format ?? 'YYYY-MM-DD')}</td>
                    <td>{invoice.review_status.replace(/_/g, ' ')}</td>
                    <td><button className="text-button" type="button" onClick={() => {
                      setFocusedInvoice(invoice)
                      setSelectedId(invoice.id)
                    }}>Review</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel table-card" id="invoices">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Local SQLite history</p>
            <h2>Invoices</h2>
          </div>
          {dashboard && <span className="muted">{invoiceTotal} invoices · {dashboard.total_findings} findings</span>}
        </div>
        <form className="filter-bar" onSubmit={(event) => {
          event.preventDefault()
          setSearch(searchText.trim())
        }}>
          <label>
            Search invoices
            <input
              type="search"
              value={searchText}
              placeholder="Vendor, invoice number, or filename"
              onChange={(event) => setSearchText(event.currentTarget.value)}
            />
          </label>
          <label>
            Review status
            <select value={reviewStatusFilter} onChange={(event) => setReviewStatusFilter(event.currentTarget.value)}>
              <option value="">All statuses</option>
              {REVIEW_STATUSES.map((reviewStatus) => (
                <option key={reviewStatus} value={reviewStatus}>{reviewStatus.replace('_', ' ')}</option>
              ))}
            </select>
          </label>
          <div className="filter-actions">
            <button className="button" type="submit">Search</button>
            <button className="button button-secondary" type="button" onClick={() => {
              setSearchText('')
              setSearch('')
              setReviewStatusFilter('')
            }}>Clear</button>
          </div>
        </form>
        {loading ? (
          <p className="empty-state" role="status">Loading invoices from the backend…</p>
        ) : error ? (
          <p className="empty-state">Invoice history could not be loaded. Use Refresh after the backend is available.</p>
        ) : invoices.length === 0 ? (
          <p className="empty-state">
            {search || reviewStatusFilter
              ? 'No invoices match the current search and filters.'
              : 'No invoices yet. Upload an invoice to start the review flow.'}
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Invoice #</th>
                  <th>Date</th>
                  <th>Total</th>
                  <th>Review status</th>
                  <th>Processing</th>
                  <th>Findings</th>
                  <th><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} className={selectedId === invoice.id ? 'selected-row' : ''}>
                    <td>{invoice.vendor_name ?? 'Unknown vendor'}</td>
                    <td>{invoice.invoice_number ?? '—'}</td>
                    <td>{invoice.invoice_date ? formatDate(invoice.invoice_date, settings?.date_format ?? 'YYYY-MM-DD') : '—'}</td>
                    <td>{invoice.total_amount == null ? '—' : `${invoice.currency} ${invoice.total_amount.toLocaleString()}`}</td>
                    <td>{invoice.review_status.replace('_', ' ')}</td>
                    <td><span className={`processing-status processing-${invoice.processing_status}`}>{invoice.processing_status}</span></td>
                    <td>{invoice.findings.length}</td>
                    <td>
                      <button className="text-button" type="button" onClick={() => {
                        setFocusedInvoice(null)
                        setSelectedId(invoice.id)
                      }}>
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && invoices.length < invoiceTotal && (
          <button className="button button-secondary load-more" type="button" onClick={() => void loadMoreInvoices()} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load older invoices'}
          </button>
        )}
      </section>

      <section className="panel review-queue-panel" id="review">
        <div className="section-heading">
          <div>
            <p className="eyebrow">HUMAN REVIEW</p>
            <h2>Review queue</h2>
          </div>
          <span className="muted">{reviewQueueTotal} awaiting review</span>
        </div>
        {reviewQueueError ? (
          <p className="error" role="alert">Review queue could not be loaded: {reviewQueueError}</p>
        ) : loading && reviewQueueInvoices.length === 0 ? (
          <p className="muted" role="status">Loading invoices that need review…</p>
        ) : reviewQueueInvoices.length === 0 ? (
          <p className="empty-state">No invoices currently need review.</p>
        ) : (
          <>
            <ul className="review-queue-list">
              {reviewQueueInvoices.map((invoice) => (
                <li key={invoice.id}>
                  <div>
                    <strong>{invoice.vendor_name ?? 'Unknown vendor'}</strong>
                    <p className="muted">
                      {invoice.invoice_number ?? invoice.original_filename}
                      {' · '}{invoice.total_amount == null ? 'Amount not extracted' : formatCurrency(invoice.total_amount, invoice.currency)}
                      {' · '}{invoice.findings.length} findings
                    </p>
                  </div>
                  <button
                    className="button button-secondary"
                    type="button"
                    aria-label={`Review ${invoice.invoice_number ?? invoice.original_filename}`}
                    onClick={() => {
                      setFocusedInvoice(invoice)
                      setSelectedId(invoice.id)
                    }}
                  >Review</button>
                </li>
              ))}
            </ul>
            {reviewQueueTotal > reviewQueueInvoices.length && (
              <p className="muted">Showing the first {reviewQueueInvoices.length} of {reviewQueueTotal} invoices awaiting review.</p>
            )}
          </>
        )}
      </section>

      {selected && (
        <section className="panel detail-panel" id="review-detail">
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                Extraction {selected.processing_status} · confidence {selected.extraction_confidence}
                {selected.extraction_method ? ` · ${selected.extraction_method}` : ''}
              </p>
              <h2>Review invoice #{selected.id}</h2>
              <p className="muted">{selected.original_filename} · {selected.file_type}</p>
            </div>
            <button className="button button-danger" type="button" onClick={() => void deleteInvoice(selected)} disabled={busy}>
              Delete invoice
            </button>
          </div>

          {selected.notes && <p className="notice">{selected.notes}</p>}
          {selected.processing_error && (
            <p className="error" role="alert">
              Extraction needs attention: {selected.processing_error}
            </p>
          )}
          <div className="review-workspace">
            <aside className="source-card">
              <div className="source-card-heading">
                <span className="file-glyph" aria-hidden="true">{selected.file_type.replace('.', '').toUpperCase()}</span>
                <div><strong>Original document</strong><small>{selected.original_filename}</small></div>
              </div>
              <div className="document-stage">
                {sourceFileError ? (
                  <p className="empty-state" role="alert">Source document could not be loaded: {sourceFileError}</p>
                ) : !sourceFileUrl ? (
                  <p className="empty-state" role="status">Loading protected source document…</p>
                ) : selected.file_type.toLowerCase() === '.pdf' ? (
                  <iframe
                    src={sourceFileUrl}
                    title={`Source document: ${selected.original_filename}`}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <img
                    src={sourceFileUrl}
                    alt={`Source invoice ${selected.original_filename}`}
                    loading="lazy"
                  />
                )}
              </div>
              <div className="source-card-footer">
                <span>Stored locally · {selected.file_type.toUpperCase()}</span>
                <button className="text-button" type="button" onClick={() => void downloadInvoiceFile(selected)}>
                  Download
                </button>
              </div>
            </aside>
            <form className="editor-grid" onSubmit={saveInvoice}>
              <div className="editor-intro field-wide">
                <span className="confidence-badge">Extraction confidence · {selected.extraction_confidence}</span>
                <p>Verify the extracted fields against the source before resolving this invoice.</p>
              </div>
            <label>Vendor<input name="vendor_name" defaultValue={selected.vendor_name ?? ''} maxLength={255} /></label>
            <label>Invoice number<input name="invoice_number" defaultValue={selected.invoice_number ?? ''} maxLength={100} /></label>
            <label>Invoice date<input name="invoice_date" type="date" defaultValue={selected.invoice_date ?? ''} /></label>
            <label>Due date<input name="due_date" type="date" defaultValue={selected.due_date ?? ''} /></label>
            <label>Currency<input name="currency" defaultValue={selected.currency} maxLength={10} /></label>
            <label>GSTIN<input name="gstin" defaultValue={selected.gstin ?? ''} maxLength={15} /></label>
            <label className="field-wide">Vendor address<input name="vendor_address" defaultValue={selected.vendor_address ?? ''} maxLength={5000} /></label>
            <label>Subtotal<input name="subtotal" type="number" step="0.0001" defaultValue={selected.subtotal ?? ''} /></label>
            <label>Tax<input name="tax_amount" type="number" step="0.0001" defaultValue={selected.tax_amount ?? ''} /></label>
            <label>Tax rate (%)<input name="tax_rate" type="number" min="0" max="100" step="0.01" defaultValue={selected.tax_rate ?? ''} /></label>
            <label>Discount<input name="discount_amount" type="number" min="0" step="0.0001" defaultValue={selected.discount_amount ?? ''} /></label>
            <label>Total<input name="total_amount" type="number" step="0.0001" defaultValue={selected.total_amount ?? ''} /></label>
            <label>Review status
              <select name="review_status" defaultValue={selected.review_status}>
                {REVIEW_STATUSES.map((reviewStatus) => <option key={reviewStatus} value={reviewStatus}>{reviewStatus.replace('_', ' ')}</option>)}
              </select>
            </label>
            <label className="field-wide">Notes<textarea name="notes" rows={2} defaultValue={selected.notes ?? ''} /></label>
            <div className="field-wide line-items-editor">
              <div className="section-heading">
                <h3>Line items</h3>
                <button className="button button-secondary" type="button" onClick={() => setLineItems((items) => [
                  ...items,
                  { description: '', quantity: null, unit_price: null, amount: null, item_order: items.length },
                ])}>Add line item</button>
              </div>
              {lineItems.length === 0 ? (
                <p className="muted">No line items were extracted. Add them if they appear on the source invoice.</p>
              ) : lineItems.map((item, index) => (
                <div className="line-item-row" key={item.id ?? `new-${index}`}>
                  <label>Description<input value={item.description ?? ''} maxLength={500} onChange={(event) => updateLineItem(index, { description: event.currentTarget.value })} /></label>
                  <label>Quantity<input type="number" min="0" step="0.000001" value={item.quantity ?? ''} onChange={(event) => updateLineItem(index, { quantity: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })} /></label>
                  <label>Unit price<input type="number" min="0" step="0.0001" value={item.unit_price ?? ''} onChange={(event) => updateLineItem(index, { unit_price: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })} /></label>
                  <label>Amount<input type="number" min="0" step="0.0001" value={item.amount ?? ''} onChange={(event) => updateLineItem(index, { amount: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })} /></label>
                  <button className="text-button" type="button" onClick={() => setLineItems((items) => items.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
                </div>
              ))}
            </div>
            <div className="field-wide editor-actions">
              <button className="button" type="submit" disabled={busy}>Save corrections and rerun checks</button>
            </div>
            </form>
          </div>

          <div className="findings">
            <h3>Audit findings</h3>
            {selected.findings.length === 0 ? (
              <p className="muted">No findings for this invoice.</p>
            ) : (
              <ul>
                {selected.findings.map((finding) => (
                  <li key={finding.id}>
                    <span className={`severity severity-${finding.severity}`}>{finding.severity}</span>
                    <strong>{finding.title}</strong>
                    <p>{finding.description}</p>
                    <p><strong>Suggested action:</strong> {finding.suggested_action}</p>
                    {finding.affected_fields?.length ? <p className="muted">Fields: {finding.affected_fields.join(', ')}</p> : null}
                    <label className="finding-status">
                      Review state
                      <select
                        value={finding.review_status}
                        disabled={busy}
                        onChange={(event) => void updateFindingReview(selected.id, finding.id, event.currentTarget.value)}
                      >
                        {REVIEW_STATUSES.map((reviewStatus) => (
                          <option key={reviewStatus} value={reviewStatus}>{reviewStatus.replace('_', ' ')}</option>
                        ))}
                      </select>
                    </label>
                    {finding.evidence && (
                      <details>
                        <summary>Evidence</summary>
                        <pre>{JSON.stringify(finding.evidence, null, 2)}</pre>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <section className="activity-timeline" aria-labelledby="invoice-activity-title">
            <h3 id="invoice-activity-title">Activity history</h3>
            {activityError ? (
              <p className="error" role="alert">Activity history could not be loaded: {activityError}</p>
            ) : activityLoading ? (
              <p className="muted" role="status">Loading invoice activity…</p>
            ) : activityEntries.length === 0 ? (
              <p className="muted">No activity was recorded for this invoice before activity tracking was enabled.</p>
            ) : (
              <ol>
                {activityEntries.map((entry) => (
                  <li key={entry.id}>
                    <div className="activity-summary">
                      <strong>{entry.summary}</strong>
                      <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time>
                    </div>
                    {entry.changed_fields.length > 0 && (
                      <p className="muted">Updated: {entry.changed_fields.map((field) => field.replaceAll('_', ' ')).join(', ')}</p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
          {selected.raw_extracted_text && (
            <details>
              <summary>Show extracted source text</summary>
              <pre>{selected.raw_extracted_text}</pre>
            </details>
          )}
        </section>
      )}

      <section className="panel duplicate-panel" id="duplicates">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Potential matches</p>
            <h2>Duplicate detection</h2>
          </div>
          <span className="muted">{duplicateDetections.length} saved matches</span>
        </div>
        {duplicateError ? (
          <p className="error" role="alert">Duplicate matches could not be loaded: {duplicateError}</p>
        ) : duplicateDetections.length === 0 ? (
          <p className="empty-state">No potential duplicate matches have been recorded.</p>
        ) : (
          <ul className="duplicate-list">
            {duplicateDetections.map((detection) => (
              <li key={detection.id}>
                <div>
                  <strong>{detection.match_type.replace(/_/g, ' ')} match</strong>
                  <p className="muted">
                    {detection.source_invoice_id == null ? 'Upload' : `Invoice #${detection.source_invoice_id}`}
                    {' '}matches invoice #{detection.matched_invoice_id} · {Math.round(detection.confidence * 100)}% confidence
                  </p>
                </div>
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => void compareDuplicate(detection)}
                  disabled={comparisonLoadingId === detection.id}
                >
                  {comparisonLoadingId === detection.id ? 'Loading…' : 'Compare records'}
                </button>
              </li>
            ))}
          </ul>
        )}
        {comparisonError && <p className="error" role="alert">Comparison details could not be loaded: {comparisonError}</p>}
        {comparison && (
            <div className="comparison-view">
              <div className="comparison-heading">
                <div>
                  <p className="eyebrow">SIDE-BY-SIDE CHECK · {Math.round(comparison.detection.confidence * 100)}% MATCH</p>
                  <h3>Compare invoice details</h3>
                </div>
                <button className="text-button" type="button" onClick={() => setComparison(null)}>Close comparison</button>
              </div>
              <div className="comparison-cards">
                <article className="comparison-card">
                  <div className="comparison-card-header">
                    <span className="file-glyph" aria-hidden="true">A</span>
                    <div><strong>{comparison.source ? `Invoice #${comparison.source.id}` : 'Upload attempt'}</strong>
                      <small>{comparison.source?.original_filename ?? 'Exact duplicate upload was not retained'}</small></div>
                  </div>
                  {comparison.source ? (
                    <button className="text-button" type="button" onClick={() => {
                      const source = comparison.source
                      if (!source) return
                      setSearchText('')
                      setSearch('')
                      setReviewStatusFilter('')
                      setFocusedInvoice(source)
                      setSelectedId(source.id)
                    }}>Review source invoice</button>
                  ) : <p className="muted">No source fields are available for this rejected duplicate upload.</p>}
                </article>
                <article className="comparison-card comparison-card-match">
                  <div className="comparison-card-header">
                    <span className="file-glyph file-glyph-match" aria-hidden="true">B</span>
                    <div><strong>Existing invoice #{comparison.matched.id}</strong>
                      <small>{comparison.matched.original_filename}</small></div>
                  </div>
                  <button className="text-button" type="button" onClick={() => {
                    setSearchText('')
                    setSearch('')
                    setReviewStatusFilter('')
                    setFocusedInvoice(comparison.matched)
                    setSelectedId(comparison.matched.id)
                  }}>Review existing invoice</button>
                </article>
              </div>
              <div className="comparison-fields" role="table" aria-label="Invoice field comparison">
                <div className="comparison-row comparison-row-header" role="row">
                  <strong role="rowheader">Invoice field</strong>
                  <span role="columnheader">Source</span>
                  <span role="columnheader">Existing record</span>
                </div>
                {comparisonFields.map((field) => (
                  <div className="comparison-row" role="row" key={field.label}>
                    <strong role="rowheader">{field.label}</strong>
                    <span role="cell">{field.source}</span>
                    <span role="cell">{field.matched}</span>
                  </div>
                ))}
              </div>
            </div>
        )}
      </section>

      <section className="panel reports-panel" id="reports">
        <div className="section-heading">
          <div>
            <p className="eyebrow">WORKSPACE REPORTS</p>
            <h2>Reports & exports</h2>
            <p className="muted">Build report previews from saved invoices and audit findings.</p>
          </div>
        </div>
        {reportsError && <p className="error" role="alert">{reportsError}</p>}
        <form className="report-filter-form" onSubmit={(event) => void loadReports(event)}>
          <label>Report
            <select value={reportType} onChange={(event) => setReportType(event.target.value)}>
              <option value="invoice_summary">Invoice summary</option>
              <option value="monthly_audit">Monthly audit</option>
              <option value="duplicate_detection">Duplicate report</option>
              <option value="vendor_spending">Vendor spending</option>
              <option value="due_dates">Due-date report</option>
              <option value="review_status">Review status</option>
            </select>
          </label>
          <label>From date
            <input type="date" value={reportDateFrom} onChange={(event) => setReportDateFrom(event.target.value)} />
          </label>
          <label>To date
            <input type="date" value={reportDateTo} onChange={(event) => setReportDateTo(event.target.value)} />
          </label>
          <label>Vendor
            <input value={reportVendor} onChange={(event) => setReportVendor(event.target.value)} maxLength={255} />
          </label>
          <label>Currency
            <input value={reportCurrency} onChange={(event) => setReportCurrency(event.target.value.toUpperCase())} maxLength={3} pattern="[A-Za-z]{3}" />
          </label>
          <label>Review status
            <select value={reportReviewStatus} onChange={(event) => setReportReviewStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="needs_review">Needs review</option>
              <option value="reviewed">Reviewed</option>
              <option value="resolved">Resolved</option>
            </select>
          </label>
          <button className="button" type="submit" disabled={reportsLoading}>
            {reportsLoading ? 'Generating…' : 'Generate report'}
          </button>
        </form>

        <div className="report-actions">
          <button className="button button-secondary" type="button" onClick={() => void downloadCsv()} disabled={!reportData || reportsLoading}>
            Download filtered CSV
          </button>
          <button className="button button-secondary" type="button" onClick={() => window.print()} disabled={!reportData || reportsLoading}>
            Print / save as PDF
          </button>
          <span className="muted">Choose “Save as PDF” in the browser print dialog. Payment status is not stored, so due-date reports do not indicate whether an invoice is unpaid.</span>
        </div>

        {reportsLoading && <p className="muted" role="status">Loading report data…</p>}
        {!reportData && !reportsLoading ? (
          <p className="empty-state" role="status">Report data is not available.</p>
        ) : reportData && (
          <div className="report-preview">
            <div className="report-summary-grid">
              <article><span>Invoices</span><strong>{reportData.invoice_count}</strong></article>
              <article><span>Audit findings</span><strong>{Object.values(reportData.findings_by_severity).reduce((sum, count) => sum + count, 0)}</strong></article>
              <article><span>Potential duplicate matches</span><strong>{reportData.duplicate_matches}</strong></article>
              {reportData.total_value_by_currency.map((value) => (
                <article key={value.currency}><span>Total value · {value.currency}</span><strong>{formatCurrency(value.amount, value.currency)}</strong></article>
              ))}
            </div>

            {reportType === 'monthly_audit' && (
              <section className="report-breakdown">
                <h3>Monthly invoice volume</h3>
                {reportData.monthly_invoice_volume.length === 0
                  ? <p className="muted">No dated invoices match these filters.</p>
                  : <ul>{reportData.monthly_invoice_volume.map((month) => <li key={month.month}>{month.month}: {month.count}</li>)}</ul>}
              </section>
            )}
            {reportType === 'vendor_spending' && (
              <section className="report-breakdown">
                <h3>Vendor spending by currency</h3>
                {reportData.vendor_spending.length === 0
                  ? <p className="muted">No invoice totals match these filters.</p>
                  : <ul>{reportData.vendor_spending.map((row) => (
                    <li key={`${row.vendor}-${row.currency}`}>{row.vendor} · {row.currency}: {formatCurrency(row.amount, row.currency)}</li>
                  ))}</ul>}
              </section>
            )}
            {reportType === 'review_status' && (
              <section className="report-breakdown">
                <h3>Review status distribution</h3>
                {Object.keys(reportData.review_status_counts).length === 0
                  ? <p className="muted">No invoices match these filters.</p>
                  : <ul>{Object.entries(reportData.review_status_counts).map(([status, count]) => (
                    <li key={status}>{status.replaceAll('_', ' ')}: {count}</li>
                  ))}</ul>}
              </section>
            )}

            <div className="report-preview-scroll">
              {reportRows.length === 0 ? (
                <p className="empty-state">
                  {reportType === 'duplicate_detection'
                    ? 'No potential duplicate matches are recorded for these filters.'
                    : reportType === 'due_dates'
                      ? 'No invoices with due dates match these filters.'
                      : 'No invoices match these filters.'}
                </p>
              ) : (
                <table className="report-preview-table">
                  <thead><tr>
                    <th>Invoice</th><th>Vendor</th><th>Invoice date</th><th>Due date</th>
                    <th>Amount</th><th>Status</th><th>Findings</th><th>Duplicates</th>
                  </tr></thead>
                  <tbody>
                    {reportRows.map((item) => (
                      <tr key={item.id}>
                        <td>{item.invoice_number || `#${item.id}`}</td>
                        <td>{item.vendor_name || 'Not extracted'}</td>
                        <td>{item.invoice_date ? formatDate(item.invoice_date, settings?.date_format ?? 'YYYY-MM-DD') : '—'}</td>
                        <td>{item.due_date ? formatDate(item.due_date, settings?.date_format ?? 'YYYY-MM-DD') : '—'}</td>
                        <td>{item.total_amount === null ? 'Not extracted' : formatCurrency(item.total_amount, item.currency)}</td>
                        <td>{item.review_status.replaceAll('_', ' ')}</td>
                        <td>{item.finding_count}</td>
                        <td>{item.duplicate_matches}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="module-grid" aria-label="Additional workspace modules">
        <section className="panel purchase-orders-panel" id="purchase-orders">
          <div className="section-heading">
            <div>
              <p className="eyebrow">WORKSPACE PURCHASE ORDERS</p>
              <h2>Purchase orders</h2>
              <p className="muted">Save expected items and compare a purchase order with an invoice from this workspace.</p>
            </div>
            <span className="muted">{purchaseOrders.length} saved</span>
          </div>
          {purchaseOrderError && <p className="error" role="alert">{purchaseOrderError}</p>}

          <form id="purchase-order-form" className="purchase-order-form" onSubmit={(event) => void savePurchaseOrder(event)}>
            <div className="purchase-order-fields">
              <label>PO number
                <input value={poNumber} onChange={(event) => setPoNumber(event.target.value)} maxLength={100} required />
              </label>
              <label>Vendor
                <input list="invoice-vendors" value={poVendor} onChange={(event) => setPoVendor(event.target.value)} maxLength={255} required />
              </label>
              <label>Currency
                <input value={poCurrency} onChange={(event) => setPoCurrency(event.target.value.toUpperCase())} maxLength={3} minLength={3} pattern="[A-Za-z]{3}" required />
              </label>
              <label>Order date
                <input type="date" value={poOrderDate} onChange={(event) => setPoOrderDate(event.target.value)} required />
              </label>
              <label>Expected delivery
                <input type="date" value={poExpectedDate} onChange={(event) => setPoExpectedDate(event.target.value)} />
              </label>
              <label>Tax rate (%)
                <input type="number" min="0" max="100" step="0.01" value={poTaxRate} onChange={(event) => setPoTaxRate(Number(event.target.value))} required />
              </label>
              <label>Status
                <select value={poStatus} onChange={(event) => setPoStatus(event.target.value as PurchaseOrder['status'])}>
                  <option value="open">Open</option>
                  <option value="fulfilled">Fulfilled</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </label>
            </div>
            <datalist id="invoice-vendors">
              {Array.from(new Set(invoices.map((invoice) => invoice.vendor_name).filter(Boolean))).map((vendor) => (
                <option key={vendor} value={vendor ?? ''} />
              ))}
            </datalist>

            <fieldset className="purchase-order-lines">
              <legend>Line items</legend>
              {poLineItems.map((item, index) => (
                <div className="purchase-order-line" key={index}>
                  <label>Description
                    <input
                      value={item.description}
                      onChange={(event) => updatePurchaseOrderLineItem(index, { description: event.target.value })}
                      maxLength={500}
                      required
                    />
                  </label>
                  <label>Quantity
                    <input
                      type="number"
                      min="0.001"
                      step="0.001"
                      value={item.quantity}
                      onChange={(event) => updatePurchaseOrderLineItem(index, { quantity: Number(event.target.value) })}
                      required
                    />
                  </label>
                  <label>Unit price
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={item.unit_price}
                      onChange={(event) => updatePurchaseOrderLineItem(index, { unit_price: Number(event.target.value) })}
                      required
                    />
                  </label>
                  <button
                    className="text-button"
                    type="button"
                    disabled={poLineItems.length === 1}
                    onClick={() => setPoLineItems((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    aria-label={`Remove line item ${index + 1}`}
                  >Remove</button>
                </div>
              ))}
              <button
                className="button button-secondary"
                type="button"
                onClick={() => setPoLineItems((current) => [
                  ...current,
                  { description: '', quantity: 1, unit_price: 0, amount: 0, item_order: current.length },
                ])}
              >Add line item</button>
            </fieldset>

            <div className="purchase-order-form-actions">
              <button className="button" type="submit" disabled={purchaseOrderSaving}>
                {purchaseOrderSaving ? 'Saving…' : editingPurchaseOrderId ? 'Save changes' : 'Create purchase order'}
              </button>
              {editingPurchaseOrderId && (
                <button className="button button-secondary" type="button" onClick={resetPurchaseOrderForm}>
                  Cancel edit
                </button>
              )}
            </div>
          </form>

          {purchaseOrdersLoading ? (
            <p className="muted" role="status">Loading purchase orders…</p>
          ) : purchaseOrders.length === 0 ? (
            <p className="empty-state" role="status">No purchase orders have been saved in this workspace.</p>
          ) : (
            <div className="purchase-order-list">
              {purchaseOrders.map((order) => (
                <article className="purchase-order-card" key={order.id}>
                  <div className="purchase-order-card-heading">
                    <div>
                      <p className="eyebrow">{order.status.toUpperCase()}</p>
                      <h3>{order.po_number}</h3>
                      <p className="muted">{order.vendor_name} · {formatCurrency(order.total_amount, order.currency)}</p>
                    </div>
                    <div className="purchase-order-actions">
                      <button className="text-button" type="button" onClick={() => editPurchaseOrder(order)}>Edit</button>
                      <button className="text-button danger-text" type="button" onClick={() => void deletePurchaseOrder(order)}>Delete</button>
                    </div>
                  </div>
                  <p className="muted">
                    Ordered: {order.order_date
                      ? formatDate(order.order_date, settings?.date_format ?? 'YYYY-MM-DD')
                      : 'Not set'}
                    {' · '}Expected delivery: {
                      order.expected_delivery_date
                        ? formatDate(order.expected_delivery_date, settings?.date_format ?? 'YYYY-MM-DD')
                        : 'Not set'
                    }
                  </p>
                  <p className="muted">
                    Subtotal {formatCurrency(order.subtotal, order.currency)} · Tax {formatCurrency(order.tax_amount, order.currency)} ({order.tax_rate}%)
                  </p>
                  <ul className="purchase-order-item-list">
                    {order.line_items.map((item) => (
                      <li key={item.id ?? item.item_order}>
                        <span>{item.description} · {item.quantity} × {formatCurrency(item.unit_price, order.currency)}</span>
                        <strong>{formatCurrency(item.amount, order.currency)}</strong>
                      </li>
                    ))}
                  </ul>
                  <div className="purchase-order-compare">
                    <label>Compare with invoice
                      <select value={comparisonInvoiceId} onChange={(event) => setComparisonInvoiceId(event.target.value)}>
                        <option value="">Select an invoice</option>
                        {invoices.map((invoice) => (
                          <option key={invoice.id} value={invoice.id}>
                            #{invoice.id} · {invoice.vendor_name || 'Unknown vendor'} · {invoice.invoice_number || 'No number'}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="button button-secondary"
                      type="button"
                      disabled={purchaseOrderSaving || invoices.length === 0}
                      onClick={() => void comparePurchaseOrder(order)}
                    >Compare</button>
                  </div>
                </article>
              ))}
            </div>
          )}

          {purchaseOrderComparison && (
            <div className="purchase-order-comparison" role="status">
              <h3>Comparison for {purchaseOrderComparison.po_number} · invoice #{purchaseOrderComparison.invoice_id}</h3>
              <ul>
                {purchaseOrderComparison.comparison_result.map((result, index) => {
                  const field = String(result.field ?? 'Comparison')
                  const outcome = typeof result.match === 'boolean'
                    ? result.match ? 'Matches' : 'Discrepancy detected'
                    : String(result.status ?? JSON.stringify(result.matches ?? result))
                  return <li key={`${field}-${index}`}><strong>{field}:</strong> {outcome}</li>
                })}
              </ul>
              <p className="muted">The comparison and any findings are saved with the invoice review history.</p>
            </div>
          )}
        </section>
        <section className="panel vendor-intelligence-panel" id="vendor-intelligence">
          <div className="section-heading">
            <div>
              <p className="eyebrow">RECORDED INVOICE INTELLIGENCE</p>
              <h2>Vendor intelligence</h2>
              <p className="muted">Profiles are derived from invoice records in this workspace; no vendor details are invented.</p>
            </div>
            <span className="muted">{vendors.length} vendors</span>
          </div>
          {vendorError && <p className="error" role="alert">{vendorError}</p>}
          {vendorsLoading ? (
            <p className="muted" role="status">Loading vendor data…</p>
          ) : vendors.length === 0 ? (
            <p className="empty-state" role="status">Vendor profiles appear after saved invoices include a vendor name.</p>
          ) : (
            <div className="vendor-intelligence-grid">
              <div className="vendor-directory">
                <label>Search vendors
                  <input
                    type="search"
                    value={vendorSearch}
                    onChange={(event) => setVendorSearch(event.target.value)}
                    placeholder="Search recorded vendor names"
                  />
                </label>
                {filteredVendors.length === 0 ? (
                  <p className="empty-state">No recorded vendors match this search.</p>
                ) : (
                  <div className="vendor-directory-list" role="list" aria-label="Vendor directory">
                    {filteredVendors.map((vendor) => (
                      <button
                        key={vendor.name}
                        className={`vendor-directory-item${selectedVendorName === vendor.name ? ' selected' : ''}`}
                        type="button"
                        aria-pressed={selectedVendorName === vendor.name}
                        onClick={() => setSelectedVendorName(vendor.name)}
                      >
                        <strong>{vendor.name}</strong>
                        <span>{vendor.invoice_count} recorded {vendor.invoice_count === 1 ? 'invoice' : 'invoices'}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {selectedVendor && (
                <div className="vendor-profile">
                  <div className="vendor-profile-heading">
                    <div>
                      <p className="eyebrow">VENDOR PROFILE</p>
                      <h3>{selectedVendor.name}</h3>
                    </div>
                    <span>{selectedVendor.invoice_count} invoices</span>
                  </div>

                  <div className="vendor-metrics">
                    {selectedVendor.total_value_by_currency.map((value) => (
                      <article key={value.currency}>
                        <span>Total invoice value · {value.currency}</span>
                        <strong>{formatCurrency(value.amount, value.currency)}</strong>
                      </article>
                    ))}
                    <article>
                      <span>Potential duplicate matches</span>
                      <strong>{selectedVendor.duplicate_matches}</strong>
                    </article>
                    <article>
                      <span>Audit findings</span>
                      <strong>{Object.values(selectedVendor.findings_by_severity).reduce((sum, count) => sum + count, 0)}</strong>
                    </article>
                  </div>

                  <div className="vendor-profile-grid">
                    <section className="vendor-detail-card">
                      <h4>Invoice frequency</h4>
                      {selectedVendor.invoice_frequency.length === 0 ? (
                        <p className="muted">Invoice dates are not available for this vendor.</p>
                      ) : (
                        <ul>
                          {selectedVendor.invoice_frequency.map((month) => (
                            <li key={month.month}><span>{month.month}</span><strong>{month.count}</strong></li>
                          ))}
                        </ul>
                      )}
                    </section>
                    <section className="vendor-detail-card">
                      <h4>Price changes</h4>
                      {selectedVendor.price_changes.length === 0 ? (
                        <p className="muted">No price changes can be calculated from the recorded line items.</p>
                      ) : (
                        <ul>
                          {selectedVendor.price_changes.map((change) => (
                            <li key={`${change.description}-${change.currency}`}>
                              <span>{change.description} · {change.currency}</span>
                              <strong>{change.entries.map((entry) => formatCurrency(entry.unit_price, change.currency)).join(' → ')}</strong>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                    <section className="vendor-detail-card">
                      <h4>Recent audit findings</h4>
                      {selectedVendor.recent_findings.length === 0 ? (
                        <p className="muted">No audit findings are recorded for this vendor.</p>
                      ) : (
                        <ul>
                          {selectedVendor.recent_findings.map((finding, index) => (
                            <li key={`${finding.invoice_id}-${finding.title}-${index}`}>
                              <span>{finding.title} · Invoice #{finding.invoice_id}</span>
                              <strong>{finding.severity}</strong>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                    <section className="vendor-detail-card">
                      <h4>Recent invoices</h4>
                      {selectedVendor.recent_invoices.length === 0 ? (
                        <p className="muted">No invoice records are available.</p>
                      ) : (
                        <ul>
                          {selectedVendor.recent_invoices.map((invoice) => (
                            <li key={invoice.id}>
                              <span>
                                {invoice.invoice_number || `Invoice #${invoice.id}`}
                                {' · '}{invoice.invoice_date
                                  ? formatDate(invoice.invoice_date, settings?.date_format ?? 'YYYY-MM-DD')
                                  : 'Date unavailable'}
                              </span>
                              <strong>{invoice.total_amount === null
                                ? 'Amount unavailable'
                                : formatCurrency(invoice.total_amount, invoice.currency)}</strong>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  </div>
                  <p className="vendor-limitations">
                    Contact details and payment history are not stored in this build. Price changes use only matching recorded line-item descriptions and currencies.
                  </p>
                </div>
              )}
            </div>
          )}
        </section>
      </section>

      <section className="panel settings-panel" id="settings">
        <div className="section-heading settings-heading">
          <div>
            <p className="eyebrow">PERSISTED WORKSPACE PREFERENCES</p>
            <h2>Settings</h2>
            <p className="muted">Saved preferences are stored locally for this workspace and account.</p>
          </div>
          {settings && profile?.role !== 'owner' && (
            <span className="muted">Workspace settings are read-only for your role.</span>
          )}
        </div>
        {settingsError && <p className="error" role="alert">{settingsError}</p>}
        {!settings ? (
          <p className="muted" role="status">{settingsError ? 'Settings could not be loaded.' : 'Loading saved settings…'}</p>
        ) : (
          <form className="settings-form" onSubmit={(event) => void saveSettings(event)}>
            <fieldset disabled={profile?.role !== 'owner'}>
              <section className="settings-group" aria-labelledby="general-settings-title">
                <h3 id="general-settings-title">General settings</h3>
                <div className="settings-fields">
                  <label>Workspace name<input name="workspace_name" defaultValue={settings.workspace_name} maxLength={100} required /></label>
                  <label>Business name<input name="business_name" defaultValue={settings.business_name} maxLength={255} /></label>
                  <label>Default currency
                    <select name="default_currency" defaultValue={settings.default_currency}>
                      {['INR', 'USD', 'EUR', 'GBP', 'AUD', 'CAD', 'JPY'].map((currency) => <option key={currency}>{currency}</option>)}
                    </select>
                  </label>
                  <label>Date format
                    <select name="date_format" defaultValue={settings.date_format}>
                      <option value="YYYY-MM-DD">YYYY-MM-DD</option>
                      <option value="DD/MM/YYYY">DD/MM/YYYY</option>
                      <option value="MM/DD/YYYY">MM/DD/YYYY</option>
                    </select>
                  </label>
                  <label>Time zone
                    <select name="time_zone" defaultValue={settings.time_zone}>
                      <option value="Asia/Kolkata">Asia/Kolkata</option>
                      <option value="UTC">UTC</option>
                      <option value="Europe/London">Europe/London</option>
                      <option value="America/New_York">America/New_York</option>
                      <option value="Asia/Singapore">Asia/Singapore</option>
                    </select>
                  </label>
                  <label>Language
                    <select name="language" defaultValue={settings.language}>
                      <option value="en">English</option>
                      <option value="hi">Hindi</option>
                    </select>
                  </label>
                </div>
              </section>

              <section className="settings-group" aria-labelledby="profile-settings-title">
                <h3 id="profile-settings-title">Profile</h3>
                <div className="settings-fields">
                  <label>Display name<input name="profile_display_name" defaultValue={settings.profile.display_name} maxLength={100} /></label>
                  <label>Email address<input value={settings.profile.email} readOnly /></label>
                </div>
              </section>

              <section className="settings-group" aria-labelledby="team-settings-title">
                <h3 id="team-settings-title">Team access</h3>
                <p className="muted">Member invitations and role management are not available in this local build. No invitations or access changes can be made from this page.</p>
              </section>

              <section className="settings-group" aria-labelledby="invoice-settings-title">
                <h3 id="invoice-settings-title">Invoice preferences</h3>
                <div className="settings-fields">
                  <label>Default tax rate (%)<input name="default_tax_rate" type="number" min="0" max="100" step="0.01" defaultValue={settings.default_tax_rate ?? ''} /></label>
                  <label>Invoice number prefix<input name="invoice_number_prefix" defaultValue={settings.invoice_number_prefix} maxLength={32} /></label>
                  <label>Default review status
                    <select name="default_review_status" defaultValue={settings.default_review_status}>
                      <option value="needs_review">Needs review</option>
                      <option value="reviewed">Reviewed</option>
                    </select>
                  </label>
                </div>
                <p className="muted settings-note">These are workspace defaults; they do not overwrite values extracted from an uploaded invoice.</p>
              </section>

              <section className="settings-group" aria-labelledby="notification-settings-title">
                <h3 id="notification-settings-title">Notifications</h3>
                <div className="settings-checks">
                  <label><input name="notify_audit_completion" type="checkbox" defaultChecked={settings.notifications.audit_completion} /> Audit completion</label>
                  <label><input name="notify_duplicate_detection" type="checkbox" defaultChecked={settings.notifications.duplicate_detection} /> Duplicate detection</label>
                  <label><input name="notify_failed_upload" type="checkbox" defaultChecked={settings.notifications.failed_upload} /> Failed uploads</label>
                  <label><input name="notify_review_reminders" type="checkbox" defaultChecked={settings.notifications.review_reminders} /> Review reminders</label>
                </div>
                <p className="muted settings-note">Notification preferences are saved, but email and push delivery are not configured in this local build.</p>
              </section>

              <section className="settings-group" aria-labelledby="appearance-settings-title">
                <h3 id="appearance-settings-title">Appearance</h3>
                <label className="settings-appearance">Theme
                  <select name="appearance" defaultValue={settings.appearance}>
                    <option value="system">System preference</option>
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </label>
              </section>

              <section className="settings-group" aria-labelledby="security-settings-title">
                <h3 id="security-settings-title">Security</h3>
                <p><strong>Authentication:</strong> {settings.authentication.status}; your access is workspace-scoped.</p>
                <p className="muted">{settings.authentication.session_information}</p>
                <p className="muted">{settings.authentication.password_management}</p>
              </section>
            </fieldset>
            <div className="settings-actions">
              <button className="button" type="submit" disabled={settingsSaving || profile?.role !== 'owner'}>
                {settingsSaving ? 'Saving…' : 'Save settings'}
              </button>
              <span className="muted" role="status">{notice === 'Workspace settings saved.' ? notice : ''}</span>
            </div>
          </form>
        )}
      </section>

      <section className="panel privacy-panel" id="privacy">
        <div>
          <p className="eyebrow">Local data management</p>
          <h2>Privacy and storage</h2>
          <p className="muted">Workspace data and exports are scoped to the signed-in local account.</p>
        </div>
        {privacyError ? (
          <p className="error" role="alert">Data privacy request failed: {privacyError}</p>
        ) : privacyInfo ? (
          <>
            <dl className="privacy-grid">
              <div><dt>Stored data</dt><dd>{privacyInfo.data_stored.join(', ')}</dd></div>
              <div><dt>Workspace records</dt><dd>{privacyInfo.workspace_data.invoice_count} invoices · {privacyInfo.workspace_data.finding_count} findings</dd></div>
              <div><dt>Accepted files</dt><dd>{privacyInfo.file_types_accepted.join(', ')} · up to {Math.floor(privacyInfo.max_file_size_bytes / (1024 * 1024))} MB</dd></div>
              <div><dt>Storage location</dt><dd>{privacyInfo.storage_location}</dd></div>
              <div><dt>Local storage inventory</dt><dd>Database: {privacyInfo.database.status}, {privacyInfo.database.size_bytes} bytes. Uploads: {privacyInfo.uploads.file_count} files. Reports: {privacyInfo.reports.file_count} files.</dd></div>
              <div><dt>Retention</dt><dd>{privacyInfo.data_retention}</dd></div>
              <div><dt>Third-party sharing</dt><dd>{privacyInfo.third_party_sharing}</dd></div>
              <div><dt>Extraction services</dt><dd>{privacyInfo.external_ai_services}</dd></div>
              <div><dt>Workspace isolation</dt><dd>{privacyInfo.authentication.scope}. Password hashing: {privacyInfo.authentication.password_hashing}; sessions expire after {privacyInfo.authentication.session_lifetime_hours} hours.</dd></div>
              <div><dt>Security limitations</dt><dd>Email verification: {privacyInfo.authentication.email_verification_enabled ? 'enabled' : 'not configured'}. Rate limiting: {privacyInfo.authentication.rate_limiting_enabled ? 'enabled' : 'not configured'}.</dd></div>
            </dl>
            <div className="privacy-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void downloadPrivacyExport(
                  privacyInfo.data_management.invoice_metadata_export.replace(/^\/api/, ''),
                  'invoice-metadata.csv',
                  'Invoice metadata export',
                )}
              >Export invoice metadata CSV</button>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void downloadPrivacyExport(
                  privacyInfo.data_management.audit_findings_export.replace(/^\/api/, ''),
                  'audit-findings.csv',
                  'Audit findings export',
                )}
              >Export audit findings CSV</button>
              <a className="button button-secondary" href="#invoices">Manage invoice records</a>
            </div>
            {privacyExportError && <p className="error" role="alert">Export failed: {privacyExportError}</p>}
            <p className="muted privacy-deletion-note">
              {privacyInfo.data_management.invoice_deletion} Account and workspace deletion are not available in this local build. No data will be removed from this page.
            </p>
          </>
        ) : <p className="muted" role="status">Loading local storage details…</p>}
        <p className="privacy-warning">
          Local development only. Authentication and workspace scoping are implemented for the local workflow, but email verification, password recovery, account rate limits, and production security review are not. Do not expose this service to the public internet.
        </p>
      </section>

      <section className="panel information-panel" id="about">
        <p className="eyebrow">ABOUT THE PRODUCT</p>
        <h2>Invoice Detective</h2>
        <p>Intelligent Invoice Audit Platform</p>
        <p className="muted">Review uploaded invoices with extracted details, arithmetic checks, duplicate signals, purchase order comparisons, and explainable audit findings. This local build is designed for workspace-scoped review and does not make payment decisions.</p>
      </section>

      <section className="panel information-panel" id="help">
        <p className="eyebrow">HELP</p>
        <h2>Using the workspace</h2>
        <ol className="help-links">
          <li><a href="#upload">Upload an invoice</a> and check accepted formats and size limits in <a href="#privacy">Data &amp; Privacy</a>.</li>
          <li>Review extracted fields and evidence in the <a href="#review">Review Queue</a> or <a href="#invoices">Invoice History</a>; treat findings as signals to verify, not confirmed fraud.</li>
          <li>Use <a href="#reports">Reports &amp; Exports</a> for workspace-scoped CSV exports and print-to-PDF.</li>
        </ol>
      </section>

      <section className="panel information-panel" id="contact">
        <p className="eyebrow">CONTACT</p>
        <h2>Support availability</h2>
        <p className="muted">A support inbox or contact-submission service is not configured in this local build. No messages are collected or sent from this page, and no external contact details are available to provide.</p>
      </section>

      <footer className="app-footer">
        <span>Invoice Detective · Intelligent Invoice Audit Platform</span>
        <nav aria-label="Product information">
          <a href="#about">About</a>
          <a href="#help">Help</a>
          <a href="#contact">Contact</a>
        </nav>
        <span>Connected API: <code>{API_BASE}</code></span>
      </footer>
      </main>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('app')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
