import { useState, useEffect } from 'react';
import { useAuth } from '@/src/lib/auth-context';
import { toast } from 'sonner';

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isPageReady, setIsPageReady] = useState(false);

  // Simulate page loading animation on mount
  useEffect(() => {
    const timer = setTimeout(() => setIsPageReady(true), 400);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;
    setIsLoading(true);

    try {
      await login(username, password);
      toast.success('登录成功');
    } catch (err: any) {
      toast.error('登录失败：' + (err.message || '请检查账号密码'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuickLogin = async () => {
    setIsLoading(true);
    try {
      await login('admin', 'admin123');
      toast.success('以管理员身份登录成功');
    } catch (err: any) {
      toast.error('登录失败：' + (err.message || '请重试'));
    } finally {
      setIsLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 14px',
    fontSize: '14px',
    color: 'var(--text-primary)',
    background: 'var(--input-bg)',
    border: '1px solid var(--input-border)',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    boxSizing: 'border-box',
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(180deg, #FAFBFC 0%, #F0F4FF 50%, #FAFBFC 100%)',
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    }}>
      {/* Page loading ring animation */}
      {!isPageReady && (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '16px',
        }}>
          <div style={{
            position: 'relative',
            width: '44px',
            height: '44px',
          }}>
            <div style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '50%',
              border: '3px solid var(--gray-200)',
            }} />
            <div style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '50%',
              border: '3px solid transparent',
              borderTopColor: 'var(--accent)',
              animation: 'enterprise-spin 0.8s linear infinite',
            }} />
          </div>
          <span style={{
            fontSize: '13px',
            color: 'var(--text-tertiary)',
          }}>
            KnowRAG
          </span>
        </div>
      )}

      {/* Login card */}
      <div style={{
        opacity: isPageReady ? 1 : 0,
        transform: isPageReady ? 'translateY(0)' : 'translateY(8px)',
        transition: 'opacity 0.5s ease, transform 0.5s ease',
        width: '100%',
        maxWidth: '380px',
        padding: '0 20px',
      }}>
        <div style={{
          background: '#FFFFFF',
          borderRadius: '12px',
          padding: '40px 32px',
          boxShadow: '0 2px 12px rgba(0,0,0,0.06), 0 8px 32px rgba(0,0,0,0.04)',
          border: '1px solid #F0F0F0',
        }}>
          {/* Logo */}
          <div style={{ textAlign: 'center', marginBottom: '28px' }}>
            <div style={{
              width: '52px',
              height: '52px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #4F7BE5, #3D6AD4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              boxShadow: '0 4px 12px rgba(79,123,229,0.25)',
            }}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <h1 style={{
              fontSize: '20px',
              fontWeight: 700,
              color: 'var(--text-primary)',
              margin: 0,
              letterSpacing: '-0.3px',
            }}>
              KnowRAG
            </h1>
            <p style={{
              fontSize: '13px',
              color: 'var(--text-tertiary)',
              margin: '6px 0 0',
            }}>
              企业级智能知识库平台
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{
                display: 'block',
                fontSize: '13px',
                fontWeight: 500,
                color: 'var(--text-primary)',
                marginBottom: '6px',
              }}>
                用户名 / 邮箱
              </label>
              <input
                type="text"
                placeholder="请输入用户名"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                style={inputStyle}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-focus-border)';
                  e.currentTarget.style.boxShadow = '0 0 0 3px var(--input-focus-shadow)';
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-border)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              />
            </div>
            <div>
              <label style={{
                display: 'block',
                fontSize: '13px',
                fontWeight: 500,
                color: 'var(--text-primary)',
                marginBottom: '6px',
              }}>
                密码
              </label>
              <input
                type="password"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                style={inputStyle}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-focus-border)';
                  e.currentTarget.style.boxShadow = '0 0 0 3px var(--input-focus-shadow)';
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-border)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || !username || !password}
              style={{
                width: '100%',
                padding: '10px 0',
                background: (isLoading || !username || !password)
                  ? '#93C5FD'
                  : 'var(--accent)',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 600,
                cursor: (isLoading || !username || !password) ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: (isLoading || !username || !password)
                  ? 'none'
                  : '0 2px 8px rgba(59,130,246,0.25)',
                marginTop: '4px',
              }}
              onMouseEnter={(e) => {
                if (!isLoading && username && password) {
                  e.currentTarget.style.background = 'var(--accent-hover)';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.boxShadow = '0 4px 14px rgba(37,99,235,0.3)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isLoading && username && password) {
                  e.currentTarget.style.background = 'var(--accent)';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(59,130,246,0.25)';
                }
              }}
            >
              {isLoading ? (
                <>
                  <div style={{
                    width: '16px',
                    height: '16px',
                    borderRadius: '50%',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#FFFFFF',
                    animation: 'enterprise-spin 0.7s linear infinite',
                  }} />
                  登录中...
                </>
              ) : (
                '登录'
              )}
            </button>
          </form>

          {/* Divider */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            margin: '20px 0',
          }}>
            <div style={{ flex: 1, height: '1px', background: 'var(--gray-200)' }} />
            <span style={{
              padding: '0 12px',
              fontSize: '12px',
              color: 'var(--text-tertiary)',
            }}>
              快速体验
            </span>
            <div style={{ flex: 1, height: '1px', background: 'var(--gray-200)' }} />
          </div>

          {/* Quick login */}
          <button
            onClick={handleQuickLogin}
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'transparent',
              color: 'var(--accent)',
              border: '1px solid var(--accent-border)',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              if (!isLoading) {
                e.currentTarget.style.background = 'var(--accent-light)';
                e.currentTarget.style.borderColor = 'var(--accent)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isLoading) {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.borderColor = 'var(--accent-border)';
              }
            }}
          >
            快速登录（管理员）
          </button>
          <p style={{
            textAlign: 'center',
            fontSize: '11px',
            color: 'var(--text-tertiary)',
            margin: '10px 0 0',
          }}>
            默认账号：admin / admin123
          </p>
        </div>

        {/* Footer */}
        <p style={{
          textAlign: 'center',
          fontSize: '11px',
          color: 'var(--text-tertiary)',
          marginTop: '20px',
        }}>
          KnowRAG Enterprise &copy; {new Date().getFullYear()}
        </p>
      </div>
    </div>
  );
}
