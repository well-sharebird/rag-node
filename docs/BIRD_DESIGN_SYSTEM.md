# Bird 风格设计规范

基于 Bird AI 的 UI/UX 设计语言，为 RAG 系统打造现代化、简洁、专业的企业级界面。

---

## 📐 设计原则

1. **简洁清晰** - 减少视觉噪音，内容优先
2. **现代专业** - 圆角、柔和阴影、精致细节
3. **高效交互** - 清晰的视觉层次，流畅的动画过渡
4. **一致体验** - 统一的组件语言和交互模式

---

## 🎨 颜色系统

### 主色调 - 紫色系

| 色阶 | 色值 | 用途 |
|------|------|------|
| 50 | `#f5f3ff` | 极浅背景 |
| 100 | `#ede9fe` | 浅色背景、徽章 |
| 200 | `#ddd6fe` | 边框、分隔线 |
| 300 | `#c4b5fd` | 悬停状态 |
| 400 | `#a78bfa` | 次要强调 |
| 500 | `#8b5cf6` | 标准紫色 |
| 600 | `#7c3aed` | **主按钮、焦点** |
| 700 | `#6d28d9` | 悬停状态 |
| 800 | `#5b21b6` | 按下状态 |
| 900 | `#4c1d95` | 深色主题 |

### 中性色

| 色阶 | 色值 | 用途 |
|------|------|------|
| 0 | `#ffffff` | 纯白背景 |
| 50 | `#f9fafb` | 页面背景、悬停 |
| 100 | `#f3f4f6` | 次要背景 |
| 200 | `#e5e7eb` | 边框、分隔线 |
| 300 | `#d1d5db` | 禁用边框 |
| 400 | `#9ca3af` | 次要文本 |
| 500 | `#6b7280` | 辅助文本 |
| 600 | `#4b5563` | 标准文本 |
| 700 | `#374151` | 强调文本 |
| 800 | `#1f2937` | 主文本 |
| 900 | `#111827` | 最深文本 |

### 功能色

| 用途 | 色值 | 背景色 |
|------|------|--------|
| 成功 | `#10b981` | `#d1fae5` |
| 警告 | `#f59e0b` | `#fef3c7` |
| 错误 | `#ef4444` | `#fee2e2` |
| 信息 | `#3b82f6` | `#dbeafe` |

---

## 📏 间距系统

基于 **4px** 栅格系统：

```css
--bird-spacing-1: 4px
--bird-spacing-2: 8px
--bird-spacing-3: 12px
--bird-spacing-4: 16px
--bird-spacing-5: 20px
--bird-spacing-6: 24px
--bird-spacing-8: 32px
--bird-spacing-10: 40px
--bird-spacing-12: 48px
--bird-spacing-16: 64px
```

---

## 🔲 圆角规范

| 等级 | 值 | 用途 |
|------|-----|------|
| none | `0` | 无需圆角 |
| sm | `4px` | 小元素 |
| md | `8px` | 小按钮、徽章 |
| lg | `12px` | **按钮** |
| xl | `16px` | **卡片、下拉菜单** |
| 2xl | `20px` | **对话框** |
| 3xl | `24px` | 大卡片 |
| full | `9999px` | **输入框、徽章** |

---

## ✨ 阴影系统

```css
/* 轻微悬浮 */
--bird-shadow-sm: 0 1px 3px rgba(0,0,0,0.1);

/* 卡片默认 */
--bird-shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);

/* 下拉菜单、弹窗 */
--bird-shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);

/* 大弹窗 */
--bird-shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.1);

/* 模态框 */
--bird-shadow-2xl: 0 25px 50px -12px rgba(0,0,0,0.25);
```

---

## 📝 字体系统

### 字体族

```css
--bird-font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 
                  'PingFang SC', 'Microsoft YaHei', sans-serif;
--bird-font-mono: 'SF Mono', 'Monaco', 'Fira Code', monospace;
```

### 字体大小

| 等级 | 大小 | 用途 |
|------|------|------|
| xs | `11px` | 辅助文字、徽章 |
| sm | `12px` | 次要文字、提示 |
| base | `13px` | **正文字号** |
| lg | `14px` | 小标题 |
| xl | `15px` | 卡片标题 |
| 2xl | `16px` | 对话框标题 |
| 3xl | `18px` | 页面标题 |
| 4xl | `20px` | 大标题 |
| 5xl | `24px` | 特大标题 |

### 字重

| 等级 | 值 | 用途 |
|------|-----|------|
| normal | `400` | 正文 |
| medium | `500` | 强调 |
| semibold | `600` | 标题 |
| bold | `700` | 强强调 |

---

## 🧩 组件使用指南

### 按钮 (Button)

```tsx
import { Button } from '@/components/bird';

// 主按钮
<Button variant="primary">创建</Button>

// 次要按钮
<Button variant="secondary">取消</Button>

// 幽灵按钮
<Button variant="ghost">查看更多</Button>

// 危险按钮
<Button variant="danger">删除</Button>

// 尺寸
<Button size="sm">小按钮</Button>
<Button size="md">中按钮</Button>
<Button size="lg">大按钮</Button>

// 带图标
<Button icon={<Plus />}>新建</Button>

// 加载中
<Button loading>保存中...</Button>
```

### 输入框 (Input)

```tsx
import { Input } from '@/components/bird';

// 基础用法
<Input placeholder="请输入..." />

// 带错误提示
<Input error="请输入有效的邮箱地址" />

// 带帮助文字
<Input helperText="密码至少 8 位" />

// 带前缀/后缀
<Input 
  prefix={<Search />} 
  suffix={<Button size="sm">搜索</Button>}
/>

// 禁用状态
<Input disabled />
```

### 对话框 (Modal)

```tsx
import { Modal } from '@/components/bird';

<Modal
  open={isOpen}
  onOpenChange={setOpen}
  title="确认删除"
  description="此操作不可恢复，请谨慎操作"
  footer={
    <>
      <Button variant="secondary" onClick={() => setOpen(false)}>取消</Button>
      <Button variant="danger" onClick={handleDelete}>删除</Button>
    </>
  }
>
  <p>确定要删除这个项目吗？</p>
</Modal>
```

### 卡片 (Card)

```tsx
import { Card, CardHeader, CardTitle, CardBody, CardFooter } from '@/components/bird';

<Card hover>
  <CardHeader>
    <CardTitle>卡片标题</CardTitle>
  </CardHeader>
  <CardBody>
    <p>卡片内容</p>
  </CardBody>
  <CardFooter>
    <Button size="sm">操作</Button>
  </CardFooter>
</Card>
```

### 表格 (Table)

```tsx
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/bird';

<Table striped hover>
  <TableHeader>
    <TableRow>
      <TableCell variant="header">姓名</TableCell>
      <TableCell variant="header">邮箱</TableCell>
      <TableCell variant="header">操作</TableCell>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow>
      <TableCell>张三</TableCell>
      <TableCell>zhangsan@example.com</TableCell>
      <TableCell><Button size="sm">编辑</Button></TableCell>
    </TableRow>
  </TableBody>
</Table>
```

---

## 🎯 最佳实践

### 1. 颜色使用

✅ **推荐**
- 主色用于主要操作按钮
- 中性色用于文本和边框
- 功能色用于状态反馈

❌ **避免**
- 滥用高饱和度颜色
- 同一页面超过 3 种强调色
- 在浅色背景上使用浅色文字

### 2. 间距一致性

✅ **推荐**
- 使用预设的 spacing 变量
- 保持组件内外间距一致
- 遵循 4px 栅格系统

❌ **避免**
- 使用奇数像素值 (如 13px)
- 随意自定义间距
- 组件之间间距不统一

### 3. 圆角统一

✅ **推荐**
- 输入框使用全圆角 (full)
- 按钮使用大圆角 (lg-xl)
- 卡片使用中等圆角 (xl)

❌ **避免**
- 混用不同圆角风格
- 在同一组件使用不同圆角
- 圆角过大导致视觉松散

### 4. 阴影层次

✅ **推荐**
- 卡片使用轻微阴影
- 弹窗使用中等阴影
- 模态框使用大阴影

❌ **避免**
- 阴影过深导致脏感
- 多层阴影叠加
- 忽略深色模式适配

---

## 🌓 深色模式

所有组件和颜色变量都已支持深色模式，只需在根元素添加 `dark` 类：

```tsx
<html className="dark">
```

深色模式会自动切换：
- 背景色变深
- 文本色变浅
- 边框色调整
- 阴影变柔和

---

## 📦 文件结构

```
src/
├── styles/
│   ├── bird-theme.css       # 主题变量
│   └── bird-components.css  # 组件样式
├── components/
│   └── bird/
│       ├── Button.tsx       # 按钮组件
│       ├── Input.tsx        # 输入框组件
│       ├── Modal.tsx        # 对话框组件
│       ├── Table.tsx        # 表格组件
│       ├── Card.tsx         # 卡片组件
│       └── index.ts         # 统一导出
└── docs/
    └── MIMO_DESIGN_SYSTEM.md # 本文档
```

---

## 🔧 自定义扩展

### 添加新颜色

在 `bird-theme.css` 中添加：

```css
:root {
  --bird-brand: #your-color;
  --bird-brand-hover: #your-hover-color;
}
```

### 添加新组件

1. 在 `bird-components.css` 中定义样式
2. 在 `components/bird/` 中创建 React 组件
3. 在 `index.ts` 中导出

### 覆盖默认样式

```tsx
<Button className="my-custom-class">
  自定义样式
</Button>
```

```css
.my-custom-class {
  /* 你的自定义样式 */
}
```

---

## 📝 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.0 | 2026-07-22 | 初始版本，包含基础组件 |

---

## 📚 参考资料

- [Bird AI](https://www.bird.com/) - 设计灵感来源
- [Tailwind CSS](https://tailwindcss.com/) - 工具类框架
- [shadcn/ui](https://ui.shadcn.com/) - 组件设计理念
