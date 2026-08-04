import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { login as loginApi, getMe, getUserMenus, getUserPermissions, type UserResponse, type MenuData } from '@/lib/api-client';

interface User {
  id: number;
  email: string;
  username: string;
  fullName?: string;
  is_active: boolean;
  roles?: Array<{ id: number; name: string }>;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  menus: MenuData[] | null;
  permissions: string[] | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  refreshMenus: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function apiUserToLocal(user: UserResponse): User {
  return {
    id: user.id,
    email: user.email,
    username: user.username,
    fullName: user.full_name,
    is_active: user.is_active,
    roles: user.roles?.map(r => ({ id: r.id, name: r.name })) || [],
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [menus, setMenus] = useState<MenuData[] | null>(null);
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchMenusAndPermissions = async () => {
    try {
      const [menusData, permsData] = await Promise.all([
        getUserMenus().catch(() => ({ items: [], total: 0 })),
        getUserPermissions().catch(() => ({ permissions: [], roles: [] })),
      ]);
      setMenus(menusData.items || []);
      setPermissions(permsData.permissions || []);
    } catch (e) {
      console.error('Failed to fetch menus/permissions:', e);
      setMenus([]);
      setPermissions([]);
    }
  };

  useEffect(() => {
    // Load token from localStorage on mount
    const storedToken = localStorage.getItem('auth_token');
    if (storedToken) {
      setToken(storedToken);
      // Validate token by fetching current user
      fetchUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchUser = async (authToken: string) => {
    try {
      const data = await getMe();
      setUser(apiUserToLocal(data));
      // Fetch menus and permissions after user is loaded
      await fetchMenusAndPermissions();
    } catch (e) {
      localStorage.removeItem('auth_token');
      setToken(null);
      setUser(null);
      setMenus(null);
      setPermissions(null);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (username: string, password: string) => {
    try {
      const data = await loginApi({ username, password });
      setToken(data.access_token);
      if (data.user) {
        setUser(apiUserToLocal(data.user));
      }
      localStorage.setItem('auth_token', data.access_token);
      // Fetch menus and permissions after login
      await fetchMenusAndPermissions();
    } catch (e: any) {
      throw new Error(e.message || 'Login failed');
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setMenus(null);
    setPermissions(null);
    localStorage.removeItem('auth_token');
  };

  const refreshMenus = async () => {
    await fetchMenusAndPermissions();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        menus,
        permissions,
        login,
        logout,
        isAuthenticated: !!token,
        isLoading,
        refreshMenus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
