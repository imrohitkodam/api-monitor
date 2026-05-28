import { useState, useEffect, useRef } from 'react';
import {
  Bot,
  FileText,
  Play,
  Plus,
  Trash2,
  Activity,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Sparkles,
  Clock,
  Database,
  ArrowRight,
  RefreshCw,
  Mail,
  ChevronDown,
  Settings
} from 'lucide-react';

const CustomDropdown = ({ options, value, onChange, placeholder, disabled }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const selectedOption = options.find(opt => opt.value === value);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className={`custom-dropdown ${disabled ? 'disabled' : ''}`} ref={dropdownRef}>
      <button
        type="button"
        className="dropdown-trigger"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
      >
        <span>{selectedOption ? selectedOption.label : placeholder}</span>
        <ChevronDown size={16} className={`arrow-icon ${isOpen ? 'open' : ''}`} />
      </button>
      {isOpen && (
        <div className="dropdown-menu">
          {options.map((opt) => (
            <div
              key={opt.value}
              className={`dropdown-item ${opt.value === value ? 'selected' : ''}`}
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
              }}
            >
              {opt.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

function App() {
  // Backend URL
  const API_URL = 'http://localhost:5000';

  // State Management
  const [services, setServices] = useState([]);
  const [counts, setCounts] = useState({ total: 0, ok: 0, warn: 0, error: 0, idle: 0 });
  const [history, setHistory] = useState([]);
  const [predefinedServices, setPredefinedServices] = useState([]);
  const [lastCheck, setLastCheck] = useState('Not checked yet');
  const [checking, setChecking] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(true);

  // Form State
  const [form, setForm] = useState({ name: '', url: '', expected_codes: '200', tag: 'custom', description: '', notify_email: '' });

  // AI Analysis State
  const [selectedServiceId, setSelectedServiceId] = useState('');
  const [aiOutput, setAiOutput] = useState('');
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loadingAi, setLoadingAi] = useState(false);

  // UI State
  const [error, setError] = useState(null);

  // Schedule State
  const [scheduleInput, setScheduleInput] = useState({ value: 0, unit: 'minutes', notify_email: '' });
  const [showSchedule, setShowSchedule] = useState(false);

  const fetchSchedule = async () => {
    try {
      const response = await fetch(`${API_URL}/api/settings`);
      if (response.ok) {
        const data = await response.json();
        let val = data.interval_minutes || 0;
        let unit = 'minutes';
        if (val > 0) {
          if (val % (24 * 60) === 0) {
            val = val / (24 * 60);
            unit = 'days';
          } else if (val % 60 === 0) {
            val = val / 60;
            unit = 'hours';
          }
        }
        setScheduleInput({ value: val, unit: unit, notify_email: data.notify_email || '' });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const saveSchedule = async (e) => {
    if (e) e.preventDefault();
    try {
      let multiplier = 1;
      if (scheduleInput.unit === 'hours') multiplier = 60;
      if (scheduleInput.unit === 'days') multiplier = 60 * 24;

      const reqBody = {
        interval_minutes: scheduleInput.value * multiplier,
        notify_email: scheduleInput.notify_email
      };

      const response = await fetch(`${API_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqBody)
      });
      if (response.ok) {
        setShowSchedule(false);
      } else {
        const data = await response.json();
        setError(data.error || 'Failed to save schedule');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  // Fetch initial summary and history
  const fetchSummary = async () => {
    try {
      const response = await fetch(`${API_URL}/api/summary`);
      if (!response.ok) throw new Error('Failed to load services summary');
      const data = await response.json();
      setServices(data.services || []);
      setCounts(data.counts || { total: 0, ok: 0, warn: 0, error: 0, idle: 0 });

      // Auto select first service for AI if none selected
      if (data.services && data.services.length > 0 && !selectedServiceId) {
        setSelectedServiceId(data.services[0].id.toString());
      }
    } catch (err) {
      console.error(err);
      setError(err.message);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/api/history?limit=15`);
      if (!response.ok) throw new Error('Failed to load history');
      const data = await response.json();
      setHistory(data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchQuickAdd = async () => {
    try {
      const response = await fetch(`${API_URL}/api/quickadd`);
      if (!response.ok) throw new Error('Failed to load quickadd list');
      const data = await response.json();
      setPredefinedServices(data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const loadAll = async () => {
    setLoadingSummary(true);
    await Promise.all([fetchSummary(), fetchHistory(), fetchQuickAdd(), fetchSchedule()]);
    setLoadingSummary(false);
  };

  useEffect(() => {
    loadAll();
  }, []);

  // Form Actions
  const handleInputChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const addService = async (e) => {
    e.preventDefault();
    if (!form.name || !form.url) return;
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/services`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Failed to add service');

      setForm({ name: '', url: '', expected_codes: '200', tag: 'custom', description: '', notify_email: '' });
      await fetchSummary();
      if (data.id) {
        setSelectedServiceId(data.id.toString());
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const quickAdd = async (item) => {
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/services`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: item.name,
          url: item.url,
          expected_codes: item.expected_codes,
          tag: item.tag,
          description: item.description,
          notify_email: item.notify_email
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Failed to quick add service');

      await fetchSummary();
      if (data.id) {
        setSelectedServiceId(data.id.toString());
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const deleteService = async (id) => {
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/services/${id}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete service');

      await fetchSummary();
      // Reset selected service if deleted
      if (selectedServiceId === id.toString()) {
        setSelectedServiceId('');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  // Run Checks
  const runAllChecks = async () => {
    setChecking(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/check/all`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to execute health checks');

      setLastCheck(`Last check: ${new Date().toLocaleTimeString()}`);
      await Promise.all([fetchSummary(), fetchHistory()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  // AI Diagnostic Actions
  const runAiAction = async (actionType) => {
    if (!selectedServiceId) {
      setError('Please add and select a service to perform AI analysis.');
      return;
    }
    setLoadingAi(true);
    setAiOutput('');
    setPdfUrl(null);
    setError(null);

    let endpoint = '';
    if (actionType === 'diagnose') endpoint = '/api/ai/diagnose';
    else if (actionType === 'suggest') endpoint = '/api/ai/suggest_fix';
    else if (actionType === 'report') endpoint = '/api/ai/full_report';

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_id: parseInt(selectedServiceId)
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'AI analysis request failed');

      if (actionType === 'report') {
        const auditReport = data.result?.audit_report || '';
        const isErrorStr = typeof auditReport === 'string' && (auditReport.includes('Error:') || auditReport.includes('429'));

        if (isErrorStr) {
          setError(`AI Provider Error Detected: ${auditReport}`);
          setAiOutput(`Failed to generate report due to AI limits or errors.\n\nDetails: ${auditReport}`);
          setPdfUrl(null);
        } else if (data.pdf_url) {
          setPdfUrl(`${API_URL}${data.pdf_url}`);
          if (data.status === 'NO_CHANGE') {
            setAiOutput(data.message);
          } else {
            setAiOutput(`Deep Audit Pipeline executed successfully!\n\nAPI Title: ${data.result.title}\nDocs URL: ${data.result.docsUrl}\n\nA professional PDF report has been compiled and rendered below. You can download or view it instantly.`);
          }
        } else {
          setAiOutput(data.result || 'Failed to compile report.');
        }
      } else {
        const isErrorStr = typeof data.result === 'string' && (data.result.includes('Error:') || data.result.includes('429'));
        if (isErrorStr) {
          setError(`AI Provider Error Detected: ${data.result}`);
        }
        setAiOutput(data.result);
      }
    } catch (err) {
      setError(err.message);
      setAiOutput(`Error during AI diagnostics: ${err.message}`);
    } finally {
      setLoadingAi(false);
    }
  };

  return (
    <div className="app-wrapper">
      {/* Top Navbar */}
      <nav className="top-nav">
        <div className="nav-brand">
          <span>API Monitor</span>
        </div>
        <div className="nav-controls">
          <span className="last-check-text">{lastCheck}</span>
          <button
            className="btn btn-outline"
            onClick={() => setShowSchedule(!showSchedule)}
            title="Auto-Scan Settings"
          >
            <Settings size={14} /> Schedule
          </button>
          <button
            className="btn btn-primary run-all-btn"
            onClick={runAllChecks}
            disabled={checking || services.length === 0}
          >
            {checking ? (
              <><RefreshCw className="spin-icon" /> Checking...</>
            ) : (
              <><Play size={14} /> Run All Checks</>
            )}
          </button>
        </div>
      </nav>

      {showSchedule && (
        <div style={{ padding: '0 30px' }}>
          <div className="dashboard-card" style={{ marginBottom: '20px' }}>
            <h3 className="card-title"><Settings size={16} /> Automatic Scan Settings</h3>
            <p className="card-subtitle" style={{ marginBottom: '15px' }}>Configure background AI scanning and email notifications. Set interval to 0 to disable automatic scans.</p>
            <form onSubmit={saveSchedule} style={{ display: 'flex', gap: '20px', alignItems: 'flex-end' }}>
              <div className="form-group" style={{ margin: 0, flex: 0.5 }}>
                <label>Every</label>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={scheduleInput.value}
                  onChange={e => setScheduleInput({ ...scheduleInput, value: e.target.value })}
                  className="form-input"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="form-group" style={{ margin: 0, flex: 0.5 }}>
                <label>Unit</label>
                <select
                  value={scheduleInput.unit}
                  onChange={e => setScheduleInput({ ...scheduleInput, unit: e.target.value })}
                  className="form-input"
                >
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                </select>
              </div>
              <div className="form-group" style={{ margin: 0, flex: 2 }}>
                <label>Global Notification Email</label>
                <input
                  type="email"
                  placeholder="admin@example.com"
                  value={scheduleInput.notify_email}
                  onChange={e => setScheduleInput({ ...scheduleInput, notify_email: e.target.value })}
                  className="form-input"
                />
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button type="submit" className="btn btn-primary">Save Settings</button>
                <button type="button" className="btn btn-outline" onClick={() => setShowSchedule(false)}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <main className="dashboard-content">
        {error && (
          <div className="error-alert">
            <AlertTriangle size={18} />
            <span>{error}</span>
            <button className="close-alert-btn" onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        {/* 1. Stat Cards Row */}
        <section className="metrics-grid">
          <div className="metric-card">
            <div className="metric-header">
              <span className="metric-label">Services</span>
              <Database size={16} className="metric-icon-decor" />
            </div>
            <div className="metric-value">{loadingSummary ? '—' : counts.total}</div>
          </div>
          <div className="metric-card card-healthy">
            <div className="metric-header">
              <span className="metric-label">Healthy</span>
              <CheckCircle size={16} className="metric-icon-decor text-success" />
            </div>
            <div className="metric-value text-success">{loadingSummary ? '—' : (counts.ok || 0)}</div>
          </div>
          <div className="metric-card card-warning">
            <div className="metric-header">
              <span className="metric-label">Warnings</span>
              <AlertTriangle size={16} className="metric-icon-decor text-warning" />
            </div>
            <div className="metric-value text-warning">{loadingSummary ? '—' : (counts.warn || 0)}</div>
          </div>
          <div className="metric-card card-issue">
            <div className="metric-header">
              <span className="metric-label">Issues</span>
              <XCircle size={16} className="metric-icon-decor text-error" />
            </div>
            <div className="metric-value text-error">{loadingSummary ? '—' : (counts.error || 0)}</div>
          </div>
        </section>

        {/* 2. Form and Services List Grid */}
        <section className="grid-panels">
          {/* Left Panel: Add Service */}
          <div className="dashboard-card">
            <h2 className="card-title">Add a Service</h2>
            <p className="card-subtitle">Register new APIs to monitor for latency and code status.</p>

            <form onSubmit={addService} className="service-form">
              <div className="form-row">
                <input
                  type="text"
                  name="name"
                  placeholder="Service name (e.g. Twilio SMS)"
                  value={form.name}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-row">
                <input
                  type="url"
                  name="url"
                  placeholder="Endpoint URL"
                  value={form.url}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-row">
                <textarea
                  name="description"
                  placeholder="Integration description (e.g. PayPal split payments in adaptive_paypal.php)"
                  value={form.description || ''}
                  onChange={handleInputChange}
                  rows={3}
                  required
                />
              </div>
              <div className="form-row">
                <input
                  type="email"
                  name="notify_email"
                  placeholder="Notification email (e.g. user@example.com)"
                  value={form.notify_email || ''}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary add-submit-btn">
                <Plus size={16} /> Add Service
              </button>
            </form>

            <div className="quick-add-section">
              <h3 className="section-title">Quick-Add Popular APIs</h3>
              <CustomDropdown
                options={predefinedServices
                  .filter(p => !services.some(s => s.name.toLowerCase() === p.name.toLowerCase()))
                  .map(item => ({
                    value: item.name,
                    label: `+ ${item.name.replace(' API', '').replace(' Gateway', '')}`
                  }))}
                value=""
                onChange={(val) => {
                  const item = predefinedServices.find(p => p.name === val);
                  if (item) quickAdd(item);
                }}
                placeholder="Select an API to add..."
                disabled={predefinedServices.filter(p => !services.some(s => s.name.toLowerCase() === p.name.toLowerCase())).length === 0}
              />
            </div>
          </div>

          {/* Right Panel: Your Services */}
          <div className="dashboard-card flex-col-card">
            <h2 className="card-title">Your Services</h2>
            <p className="card-subtitle">Current status and response metrics of registered endpoints.</p>

            <div className="services-list-container">
              {loadingSummary ? (
                <div className="loading-state">
                  <div className="spinner"></div>
                  <p>Loading services...</p>
                </div>
              ) : services.length === 0 ? (
                <div className="empty-services">
                  <Database size={32} />
                  <p>No services monitored yet.</p>
                  <p className="hint">Use the form on the left or Quick-Add badges to add services.</p>
                </div>
              ) : (
                <div className="services-list">
                  {services.map((svc) => {
                    const st = svc.latest ? svc.latest.status : 'idle';
                    let dotClass = 'dot-idle';
                    let badgeClass = 'badge-idle';
                    let statusLabel = 'not checked';

                    if (st === 'ok') {
                      dotClass = 'dot-ok';
                      badgeClass = 'badge-ok';
                      statusLabel = 'healthy';
                    } else if (st === 'warn') {
                      dotClass = 'dot-warn';
                      badgeClass = 'badge-warn';
                      statusLabel = 'warning';
                    } else if (st === 'error') {
                      dotClass = 'dot-err';
                      badgeClass = 'badge-err';
                      statusLabel = 'issue';
                    }

                    return (
                      <div key={svc.id} className="service-row">
                        <span className={`status-dot ${dotClass}`} />
                        <div className="service-info">
                          <div className="service-header-row">
                            <span className="service-name">{svc.name}</span>
                            <span className={`status-badge ${badgeClass}`}>{statusLabel}</span>
                            <span className="category-tag">{svc.tag}</span>
                            {svc.latest && (
                              <>
                                <span className="latency-label">{svc.latest.latency_ms}ms</span>
                                {svc.latest.http_code && (
                                  <span className="http-code-label">HTTP {svc.latest.http_code}</span>
                                )}
                              </>
                            )}
                          </div>
                          <div className="service-url" title={svc.url}>{svc.url}</div>
                          {svc.latest && svc.latest.note && (
                            <div className="service-note text-warning">{svc.latest.note}</div>
                          )}
                        </div>
                        <button
                          className="delete-row-btn"
                          onClick={() => deleteService(svc.id)}
                          title="Remove service"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Check History Chart */}
            {history.length > 0 && (
              <div className="history-chart-section">
                <h3 className="section-title"><Clock size={12} style={{ marginRight: '4px' }} /> Recent Checks Timeline</h3>
                <div className="history-bars">
                  {history.map((h, idx) => {
                    const pct = Math.min(100, Math.max(12, ((h.latency_ms || 400) / 4000) * 100));
                    let color = '#64748b'; // default
                    if (h.status === 'ok') color = '#10b981';
                    else if (h.status === 'warn') color = '#f59e0b';
                    else if (h.status === 'error') color = '#ef4444';

                    return (
                      <div
                        key={idx}
                        className="hbar-wrapper"
                        title={`${h.service_name}: ${h.status.toUpperCase()} | ${h.latency_ms || '?'}ms | ${new Date(h.checked_at).toLocaleTimeString()}`}
                      >
                        <div
                          className="hbar"
                          style={{ height: `${pct}%`, backgroundColor: color }}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* 3. Bottom Panel: AI Analysis & Deep Report */}
        <section className="ai-audit-section">
          <div className="dashboard-card">
            <div className="ai-panel-header">
              <div className="ai-title-group">
                <Sparkles className="spark-icon" />
                <h2 className="card-title">AI Diagnostics & Deep Auditing</h2>
              </div>

              <div className="ai-settings">
                <CustomDropdown
                  options={services.map(s => ({ value: s.id.toString(), label: s.name }))}
                  value={selectedServiceId}
                  onChange={(val) => setSelectedServiceId(val)}
                  placeholder="Select API Service..."
                  disabled={services.length === 0}
                />
              </div>
            </div>

            <div className="ai-panel-body">
              {/* AI Button Controls */}
              <div className="ai-action-buttons">
                {(() => {
                  const svc = services.find(s => s.id.toString() === selectedServiceId);
                  const hasIssue = svc && svc.latest && ['warn', 'error'].includes(svc.latest.status);
                  return hasIssue && (
                    <>
                      <button
                        className="btn btn-secondary ai-action-btn"
                        onClick={() => runAiAction('diagnose')}
                        disabled={loadingAi}
                      >
                        <Bot size={16} /> Diagnose Issue
                      </button>
                      <button
                        className="btn btn-secondary ai-action-btn"
                        onClick={() => runAiAction('suggest')}
                        disabled={loadingAi}
                      >
                        <Sparkles size={16} /> Suggest Fixes
                      </button>
                    </>
                  );
                })()}
                <button
                  className="btn btn-gradient ai-action-btn"
                  onClick={() => runAiAction('report')}
                  disabled={loadingAi || !selectedServiceId}
                >
                  <FileText size={16} /> Compile PDF Report
                </button>
              </div>

              {/* Output Panel Grid (Console + PDF) */}
              <div className="ai-output-container">
                <div className={`ai-terminal-card ${pdfUrl ? 'split-terminal' : 'full-terminal'}`}>
                  <div className="terminal-header">
                    <span className="terminal-dot red-dot"></span>
                    <span className="terminal-dot yellow-dot"></span>
                    <span className="terminal-dot green-dot"></span>
                    <span className="terminal-title">ai-diagnostics-console</span>
                  </div>
                  <div className="terminal-body">
                    {loadingAi ? (
                      <div className="terminal-loading">
                        <div className="loader"></div>
                        <p className="loading-text">Summoning AI agent to audit configuration...</p>
                      </div>
                    ) : aiOutput ? (
                      <pre className="terminal-text">{aiOutput}</pre>
                    ) : (
                      <p className="terminal-placeholder">
                        Run health checks first, select a service, and choose an AI operation above to begin analysis.
                      </p>
                    )}
                  </div>
                </div>

                {pdfUrl && (
                  <div className="pdf-viewer-card">
                    <div className="pdf-header">
                      <FileText size={14} />
                      <span>Autonomous Compiled Audit Document (ReportLab PDF)</span>
                      <a href={pdfUrl} target="_blank" rel="noreferrer" className="pdf-download-link">
                        Open in New Tab
                      </a>
                    </div>
                    <iframe src={pdfUrl} title="AI Audit PDF" className="embedded-pdf"></iframe>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
