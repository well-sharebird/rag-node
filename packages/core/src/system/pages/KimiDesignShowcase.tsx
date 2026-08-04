import { useState } from 'react';
import '../styles/kimi-theme.css';
import '../styles/kimi-components.css';

export function KimiDesignShowcase() {
  const [inputValue, setInputValue] = useState('');
  const [isChecked, setIsChecked] = useState(false);
  const [isSwitched, setIsSwitched] = useState(false);

  return (
    <div className="p-8 max-w-5xl mx-auto" style={{ fontFamily: 'var(--kimi-font-sans)', background: 'var(--kimi-bg-primary)', minHeight: '100vh' }}>
      {/* Header */}
      <div className="mb-12">
        <h1 className="text-3xl font-semibold mb-3" style={{ color: 'var(--kimi-text-primary)' }}>Kimi.com Design System</h1>
        <p className="text-base" style={{ color: 'var(--kimi-text-secondary)' }}>极简主义设计风格 - 专业、现代、高对比度</p>
      </div>

      {/* Color Palette */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Color Palette</h2>
        <div className="grid grid-cols-2 gap-6">
          {/* Primary Colors */}
          <div className="kimi-card p-6">
            <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--kimi-text-secondary)' }}>Primary Colors</h3>
            <div className="flex gap-4">
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-black)' }}></div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Black</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>var(--text-primary)</div>
              </div>
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-blue)' }}></div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Blue</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>#0066ff</div>
              </div>
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-gray-100)' }}></div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Gray 100</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>var(--gray-50)</div>
              </div>
            </div>
          </div>

          {/* Functional Colors */}
          <div className="kimi-card p-6">
            <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--kimi-text-secondary)' }}>Functional Colors</h3>
            <div className="flex gap-4">
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-success-bg)', color: 'var(--kimi-success)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px' }}>✓</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Success</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>#10b981</div>
              </div>
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-warning-bg)', color: 'var(--kimi-warning)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px' }}>!</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Warning</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>#f59e0b</div>
              </div>
              <div>
                <div className="w-16 h-16 rounded-lg mb-2" style={{ background: 'var(--kimi-error-bg)', color: 'var(--kimi-error)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px' }}>✕</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-primary)' }}>Error</div>
                <div className="text-xs" style={{ color: 'var(--kimi-text-tertiary)' }}>#ef4444</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Buttons */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Buttons</h2>
        <div className="kimi-card p-6">
          <div className="flex gap-4 mb-6">
            <button className="kimi-btn kimi-btn-primary">Primary Button</button>
            <button className="kimi-btn kimi-btn-secondary">Secondary Button</button>
            <button className="kimi-btn kimi-btn-ghost">Ghost Button</button>
            <button className="kimi-btn kimi-btn-blue">Blue Button</button>
            <button className="kimi-btn kimi-btn-danger">Danger Button</button>
          </div>
          <div className="flex gap-4">
            <button className="kimi-btn kimi-btn-primary kimi-btn-sm">Small</button>
            <button className="kimi-btn kimi-btn-primary">Default</button>
            <button className="kimi-btn kimi-btn-primary kimi-btn-lg">Large</button>
            <button className="kimi-btn kimi-btn-icon">🔍</button>
            <button className="kimi-btn kimi-btn-primary" disabled>Disabled</button>
          </div>
        </div>
      </section>

      {/* Form Elements */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Form Elements</h2>
        <div className="kimi-card p-6">
          <div className="grid gap-6 max-w-md">
            {/* Input */}
            <div>
              <label className="kimi-form-label kimi-form-label-required">Input Field</label>
              <input
                type="text"
                className="kimi-input"
                placeholder="请输入内容..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
            </div>

            {/* Input with error */}
            <div>
              <label className="kimi-form-label">Error State</label>
              <input
                type="text"
                className="kimi-input kimi-input-error"
                placeholder="错误状态"
                defaultValue="无效输入"
              />
              <div className="kimi-form-error">请输入有效的内容</div>
            </div>

            {/* Select */}
            <div>
              <label className="kimi-form-label">Select</label>
              <select className="kimi-input kimi-select">
                <option>选项 1</option>
                <option>选项 2</option>
                <option>选项 3</option>
              </select>
            </div>

            {/* Checkbox & Switch */}
            <div className="flex gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="kimi-checkbox"
                  checked={isChecked}
                  onChange={(e) => setIsChecked(e.target.checked)}
                />
                <span className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>Checkbox</span>
              </label>
              
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="kimi-switch"
                  checked={isSwitched}
                  onChange={(e) => setIsSwitched(e.target.checked)}
                />
                <span className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>Switch</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      {/* Cards */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Cards</h2>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="kimi-card">
            <div className="kimi-card-header">
              <h3 className="kimi-card-title">Card Title</h3>
              <p className="kimi-card-description">Card description text goes here</p>
            </div>
            <div className="kimi-card-body">
              <p className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>
                This is a card component with header, body, and footer sections. 
                Clean and minimalist design inspired by Kimi.com.
              </p>
            </div>
            <div className="kimi-card-footer">
              <button className="kimi-btn kimi-btn-primary kimi-btn-sm">Confirm</button>
              <button className="kimi-btn kimi-btn-secondary kimi-btn-sm">Cancel</button>
            </div>
          </div>

          <div className="kimi-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold" style={{ color: 'var(--kimi-text-primary)' }}>Statistics</h3>
              <span className="kimi-badge kimi-badge-blue">Live</span>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>Total Users</span>
                <span className="text-sm font-medium" style={{ color: 'var(--kimi-text-primary)' }}>12,345</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>Active Now</span>
                <span className="text-sm font-medium" style={{ color: 'var(--kimi-success)' }}>1,234</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm" style={{ color: 'var(--kimi-text-secondary)' }}>Revenue</span>
                <span className="text-sm font-medium" style={{ color: 'var(--kimi-text-primary)' }}>¥89,012</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Table */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Table</h2>
        <div className="kimi-card p-6">
          <div className="kimi-table-container">
            <table className="kimi-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Role</th>
                  <th>Last Active</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="font-medium" style={{ color: 'var(--kimi-text-primary)' }}>Zhang San</td>
                  <td><span className="kimi-badge kimi-badge-success">Active</span></td>
                  <td style={{ color: 'var(--kimi-text-secondary)' }}>Admin</td>
                  <td style={{ color: 'var(--kimi-text-tertiary)' }}>2 minutes ago</td>
                  <td>
                    <button className="kimi-btn kimi-btn-ghost kimi-btn-sm">Edit</button>
                  </td>
                </tr>
                <tr>
                  <td className="font-medium" style={{ color: 'var(--kimi-text-primary)' }}>Li Si</td>
                  <td><span className="kimi-badge kimi-badge-neutral">Offline</span></td>
                  <td style={{ color: 'var(--kimi-text-secondary)' }}>Editor</td>
                  <td style={{ color: 'var(--kimi-text-tertiary)' }}>1 hour ago</td>
                  <td>
                    <button className="kimi-btn kimi-btn-ghost kimi-btn-sm">Edit</button>
                  </td>
                </tr>
                <tr>
                  <td className="font-medium" style={{ color: 'var(--kimi-text-primary)' }}>Wang Wu</td>
                  <td><span className="kimi-badge kimi-badge-warning">Pending</span></td>
                  <td style={{ color: 'var(--kimi-text-secondary)' }}>Viewer</td>
                  <td style={{ color: 'var(--kimi-text-tertiary)' }}>3 hours ago</td>
                  <td>
                    <button className="kimi-btn kimi-btn-ghost kimi-btn-sm">Edit</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Badges */}
      <section className="mb-12">
        <h2 className="text-xl font-semibold mb-4" style={{ color: 'var(--kimi-text-primary)' }}>Badges</h2>
        <div className="kimi-card p-6">
          <div className="flex gap-3 flex-wrap">
            <span className="kimi-badge kimi-badge-primary">Primary</span>
            <span className="kimi-badge kimi-badge-blue">Blue</span>
            <span className="kimi-badge kimi-badge-success">Success</span>
            <span className="kimi-badge kimi-badge-warning">Warning</span>
            <span className="kimi-badge kimi-badge-error">Error</span>
            <span className="kimi-badge kimi-badge-neutral">Neutral</span>
          </div>
        </div>
      </section>
    </div>
  );
}
