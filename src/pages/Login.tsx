import { useState } from 'react';
import { useAuth } from '@/src/lib/auth-context';
import { Button, Card, CardHeader, CardBody, CardTitle, CardDescription, Input } from '@/src/components/bird';
import { toast } from 'sonner';
import { Shield, Loader2 } from 'lucide-react';

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await login(username, password);
      toast.success('登录成功');
    } catch (err: any) {
      toast.error(`登录失败：${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuickLogin = async () => {
    setUsername('admin');
    setPassword('admin123');
    setIsLoading(true);

    try {
      await login('admin', 'admin123');
      toast.success('以管理员身份登录成功');
    } catch (err: any) {
      toast.error(`登录失败：${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f5f3ff] to-[#ede9fe]">
      <Card className="w-full max-w-md shadow-xl">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <div className="w-16 h-16 rounded-full bg-[#7c3aed]/10 flex items-center justify-center">
              <Shield className="w-8 h-8 text-[#7c3aed]" />
            </div>
          </div>
          <CardTitle className="text-2xl text-center">KnowRAG 企业版</CardTitle>
          <CardDescription className="text-center">
            登录用户与角色管理系统
          </CardDescription>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-medium text-[#4b5563]">用户名 / 邮箱</label>
              <Input
                id="username"
                type="text"
                placeholder="请输入用户名"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-[#4b5563]">密码</label>
              <Input
                id="password"
                type="password"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || !username || !password}
              loading={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  登录中...
                </>
              ) : (
                '登录'
              )}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-[#e5e7eb]">
            <Button
              variant="secondary"
              className="w-full"
              onClick={handleQuickLogin}
              disabled={isLoading}
            >
              快速登录（管理员）
            </Button>
            <p className="text-xs text-center text-[#9ca3af] mt-3">
              默认账号：admin / admin123
            </p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
