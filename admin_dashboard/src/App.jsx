import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Users,
  CreditCard,
  Shield,
  LineChart,
  Search,
  MoreVertical,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  Activity,
  Award,
  Calendar,
  X,
  UserCheck,
  UserMinus,
  Link as LinkIcon
} from 'lucide-react';
import './App.css';

// Base API Configuration
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json'
  }
});

function App() {
  const [users, setUsers] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Auth State
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [adminKey, setAdminKey] = useState('');
  const [loginError, setLoginError] = useState('');
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [activeTab, setActiveTab] = useState('users'); // 'users', 'analytics'

  // Modals
  const [editingUser, setEditingUser] = useState(null);
  const [isSubModalOpen, setSubModalOpen] = useState(false);
  const [isStatusModalOpen, setStatusModalOpen] = useState(false);

  // Check for existing session
  useEffect(() => {
    const savedKey = localStorage.getItem('hollow_admin_key');
    if (savedKey) {
      handleLogin(savedKey, true);
    } else {
      setLoading(false);
    }
  }, []);

  const handleLogin = async (key, isAutoLogin = false) => {
    try {
      if (!isAutoLogin) setIsAuthenticating(true);
      setLoginError('');
      
      // Verify key by fetching analytics
      const resp = await api.get('/v1/admin/analytics', {
        headers: { 'X-Admin-Key': key }
      });
      
      if (resp.data.success) {
        setAdminKey(key);
        localStorage.setItem('hollow_admin_key', key);
        setIsLoggedIn(true);
      } else {
        throw new Error('Invalid key');
      }
    } catch (err) {
      if (!isAutoLogin) {
        setLoginError('Invalid Administrator Key');
      } else {
        localStorage.removeItem('hollow_admin_key');
      }
    } finally {
      setIsAuthenticating(false);
      if (isAutoLogin) setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('hollow_admin_key');
    setIsLoggedIn(false);
    setAdminKey('');
  };

  // Debounce search
  useEffect(() => {
    if (!isLoggedIn) return;
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // Reset to first page on search
    }, 500);
    return () => clearTimeout(timer);
  }, [search, isLoggedIn]);

  useEffect(() => {
    if (isLoggedIn) {
      fetchData();
    }
  }, [page, debouncedSearch, isLoggedIn]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const config = {
        headers: { 'X-Admin-Key': adminKey }
      };

      const [usersResp, analyticsResp] = await Promise.all([
        api.get(`/v1/admin/users`, {
          ...config,
          params: { page, limit: 10, search: debouncedSearch || undefined }
        }),
        api.get('/v1/admin/analytics', config)
      ]);
      
      if (usersResp.data.success) {
        setUsers(usersResp.data.users);
        setTotalPages(usersResp.data.pagination.pages);
      } else {
        setError(usersResp.data.detail || 'Failed to fetch users');
      }
      
      if (analyticsResp.data.success) {
        setAnalytics(analyticsResp.data.analytics);
      }
    } catch (err) {
      console.error('Fetch error:', err);
      const msg = err.response?.data?.detail || err.message || 'Connection error';
      setError(`API Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const updateSubscription = async (userId, data) => {
    try {
      const resp = await api.post('/v1/admin/user/subscription', 
        { user_id: userId, ...data },
        { headers: { 'X-Admin-Key': adminKey } }
      );
      if (resp.data.success) {
        setSubModalOpen(false);
        fetchData();
      }
    } catch (err) {
      alert('Error updating subscription');
    }
  };

  const toggleStatus = async (userId, isActive) => {
    try {
      const resp = await api.post('/v1/admin/user/status', 
        { user_id: userId, is_active: isActive },
        { headers: { 'X-Admin-Key': adminKey } }
      );
      if (resp.data.success) {
        setStatusModalOpen(false);
        fetchData();
      }
    } catch (err) {
      alert('Error updating status');
    }
  };

  // UI Helper for Status Badges
  const getStatusBadge = (status) => {
    const className = `badge badge-${status?.toLowerCase() || 'free'}`;
    return <span className={className}>{status || 'Free'}</span>;
  };

  const getSourceBadge = (source) => {
    const className = `badge badge-${source?.toLowerCase() || 'none'}`;
    return <span className={className}>{source || 'App'}</span>;
  };

  if (!isLoggedIn) {
    return (
      <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'radial-gradient(circle at 50% 50%, #1e1b4b 0%, #0a0a0c 100%)' }}>
        <div className="glass-panel animate-in" style={{ padding: '3rem', maxWidth: '400px', width: '90%', textAlign: 'center' }}>
          <div style={{ marginBottom: '2rem' }}>
            <Award size={48} color="var(--accent-primary)" style={{ marginBottom: '1rem' }} />
            <h1 style={{ fontSize: '1.75rem', marginBottom: '0.5rem' }}>hollowControl</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Secure Administration Access</p>
          </div>
          
          <form onSubmit={(e) => {
            e.preventDefault();
            handleLogin(new FormData(e.target).get('key'));
          }}>
            <div className="form-group" style={{ textAlign: 'left' }}>
              <label>Administrator Key</label>
              <input 
                name="key" 
                type="password" 
                className="form-input" 
                placeholder="Enter secret key..."
                required 
                autoFocus
              />
            </div>
            {loginError && (
              <p style={{ color: 'var(--status-banned)', fontSize: '0.8rem', marginBottom: '1.5rem', fontWeight: 600 }}>
                {loginError}
              </p>
            )}
            <button 
              type="submit" 
              className="btn btn-primary" 
              style={{ width: '100%', padding: '1rem', fontSize: '1rem' }}
              disabled={isAuthenticating}
            >
              {isAuthenticating ? 'Authenticating...' : 'Unlock Dashboard'}
            </button>
          </form>
          
          <div style={{ marginTop: '2rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Authorized Personnel Only
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="logo-section">
          <Award size={28} />
          <span>hollowControl</span>
        </div>

        <nav className="nav-links">
          <div
            className={`nav-item ${activeTab === 'analytics' ? 'active' : ''}`}
            onClick={() => setActiveTab('analytics')}
          >
            <LineChart size={20} />
            <span>Overview</span>
          </div>
          <div
            className={`nav-item ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            <Users size={20} />
            <span>User Management</span>
          </div>
        </nav>

        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div className="nav-item">
            <Shield size={20} />
            <span>Security</span>
          </div>
          <div className="nav-item" style={{ color: 'var(--status-banned)' }} onClick={handleLogout}>
            <UserMinus size={20} />
            <span>Sign Out</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        {error && (
          <div className="glass-card animate-in" style={{ borderColor: 'var(--status-banned)', color: 'var(--status-banned)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <X size={20} />
            <div>{error}</div>
            <button className="btn btn-secondary" style={{ marginLeft: 'auto', padding: '0.2rem 0.5rem' }} onClick={fetchData}>Retry</button>
          </div>
        )}

        {loading && users.length === 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem' }}>
            <div className="animate-pulse">Loading platform data...</div>
          </div>
        )}
        {activeTab === 'analytics' && analytics && (
          <div className="animate-in">
            <div className="header-row">
              <div>
                <h1 style={{ fontSize: '2rem' }}>Analytics Hub</h1>
                <p style={{ color: 'var(--text-secondary)' }}>Real-time platform metrics</p>
              </div>
            </div>

            <div className="stats-grid" style={{ marginTop: '2rem' }}>
              <div className="glass-card stat-card">
                <div className="stat-label">Total Registered Users</div>
                <div className="stat-value">{analytics.total_users}</div>
                <div style={{ color: 'var(--status-active)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <TrendingUp size={14} /> +{analytics.new_users_24h} in 24h
                </div>
              </div>
              <div className="glass-card stat-card">
                <div className="stat-label">Premium Subscriptions</div>
                <div className="stat-value" style={{ color: 'var(--accent-primary)' }}>
                  {analytics.subscription_distribution.active || 0}
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                  {((analytics.subscription_distribution.active / analytics.total_users) * 100 || 0).toFixed(1)}% Conversion rate
                </div>
              </div>
              <div className="glass-card stat-card">
                <div className="stat-label">System Health</div>
                <div className="stat-value" style={{ color: 'var(--status-active)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={24} /> 99.9%
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>All services operational</div>
              </div>
            </div>

            <div className="glass-card" style={{ marginTop: '2rem' }}>
              <h3>Subscription Source Distribution</h3>
              <div style={{ display: 'flex', gap: '2rem', marginTop: '1.5rem', flexWrap: 'wrap' }}>
                {Object.entries(analytics.premium_sources).map(([source, count]) => (
                  <div key={source} style={{ display: 'flex', flexDirection: 'column' }}>
                    <span className="stat-label">{source}</span>
                    <span style={{ fontSize: '1.5rem', fontWeight: 800 }}>{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'users' && (
          <div className="animate-in">
            <div className="header-row">
              <div>
                <h1 style={{ fontSize: '2rem' }}>Users</h1>
                <p style={{ color: 'var(--text-secondary)' }}>Manage accounts and subscriptions</p>
              </div>
              <div className="glass-panel" style={{ padding: '4px 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Search size={18} color="var(--text-muted)" />
                <input
                  className="form-input"
                  style={{ border: 'none', background: 'transparent', width: '200px' }}
                  placeholder="Search email..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>

            <div className="data-table-container" style={{ marginTop: '2rem' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>User / ID</th>
                    <th>Linked Telegram</th>
                    <th>Status</th>
                    <th>Source</th>
                    <th>Joined</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{user.email || 'Anonymous'}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{user.id.substring(0, 13)}...</div>
                      </td>
                      <td>
                        {user.user_telegram_links && user.user_telegram_links.length > 0 ? (
                          user.user_telegram_links.map(link => (
                            <div key={link.telegram_id} style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--status-telegram)' }}>
                              <LinkIcon size={12} />
                              <span>@{link.telegram_username || link.telegram_id}</span>
                            </div>
                          ))
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>No links</span>
                        )}
                      </td>
                      <td>{getStatusBadge(user.subscription_status)}</td>
                      <td>{getSourceBadge(user.subscription_source)}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>
                        {new Date(user.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.4rem', borderRadius: '6px' }}
                            onClick={() => { setEditingUser(user); setSubModalOpen(true); }}
                            title="Edit Subscription"
                          >
                            <CreditCard size={16} />
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.4rem', borderRadius: '6px' }}
                            onClick={() => { setEditingUser(user); setStatusModalOpen(true); }}
                            title="Toggle Status"
                          >
                            {user.subscription_status === 'banned' ? <UserCheck size={16} color="var(--status-active)" /> : <UserMinus size={16} color="var(--status-banned)" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ padding: '1rem', display: 'flex', justifyContent: 'center', gap: '1rem', alignItems: 'center', borderTop: '1px solid var(--border-color)' }}>
                <button
                  className="btn btn-secondary"
                  disabled={page === 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                >
                  <ChevronLeft size={18} />
                </button>
                <span className="stat-label">Page {page} of {totalPages}</span>
                <button
                  className="btn btn-secondary"
                  disabled={page === totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Subscription Modal */}
      {isSubModalOpen && editingUser && (
        <div className="modal-overlay">
          <div className="glass-panel modal-content animate-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
              <h3>Subscription Override</h3>
              <X className="cursor-pointer" onClick={() => setSubModalOpen(false)} />
            </div>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Updating for: <b>{editingUser.email}</b>
            </p>

            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              updateSubscription(editingUser.id, {
                status: formData.get('status'),
                end_date: formData.get('expiry') ? new Date(formData.get('expiry')).toISOString() : null,
                source: formData.get('source')
              });
            }}>
              <div className="form-group">
                <label>Status</label>
                <select name="status" className="form-input" defaultValue={editingUser.subscription_status}>
                  <option value="active">Active (Premium)</option>
                  <option value="free">Free Tier</option>
                  <option value="expired">Expired</option>
                </select>
              </div>
              <div className="form-group">
                <label>Premium Source</label>
                <select name="source" className="form-input" defaultValue={editingUser.subscription_source || 'manual'}>
                  <option value="manual">Manual Admin Override</option>
                  <option value="stripe">Stripe Payment</option>
                  <option value="apple">Apple In-App Purchase</option>
                  <option value="telegram">Telegram Bot</option>
                </select>
              </div>
              <div className="form-group">
                <label>Expiry Date</label>
                <input
                  type="date"
                  name="expiry"
                  className="form-input"
                  defaultValue={editingUser.subscription_end ? new Date(editingUser.subscription_end).toISOString().split('T')[0] : ''}
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
                <button type="button" className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setSubModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" style={{ flex: 2 }}>Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Status Toggle Modal */}
      {isStatusModalOpen && editingUser && (
        <div className="modal-overlay">
          <div className="glass-panel modal-content animate-in">
            <h3>{editingUser.subscription_status === 'banned' ? 'Activate Account' : 'Restrict Account'}</h3>
            <p style={{ color: 'var(--text-secondary)', margin: '1.5rem 0' }}>
              Are you sure you want to {editingUser.subscription_status === 'banned' ? 'reactivate' : 'restrict'} <b>{editingUser.email}</b>'s access?
            </p>
            <div style={{ display: 'flex', gap: '1rem' }}>
              <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setStatusModalOpen(false)}>Cancel</button>
              <button
                className="btn btn-primary"
                style={{ flex: 2, background: editingUser.subscription_status === 'banned' ? 'var(--status-active)' : 'var(--status-banned)' }}
                onClick={() => toggleStatus(editingUser.id, editingUser.subscription_status === 'banned')}
              >
                Confirm {editingUser.subscription_status === 'banned' ? 'Activation' : 'Restriction'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
