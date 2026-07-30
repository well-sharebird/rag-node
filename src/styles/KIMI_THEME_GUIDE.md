# Kimi.com 主题应用指南

将当前前端设计从"AI 化"的紫色主题转换为 Kimi.com 风格的极简主义设计。

## 🎨 设计理念对比

### 当前设计 (Ui2 Purple)
- ❌ 紫色系主色调 (#7c3aed) - 典型"AI 产品"刻板印象
- ❌ 完全圆角的输入框 - 过度设计
- ❌ 鲜艳的渐变色 - 视觉干扰
- ❌ 中等对比度 - 可读性一般

### Kimi.com 风格
- ✅ 黑 + 蓝中性色调 - 专业、现代
- ✅ 适度圆角 (6-12px) - 简洁利落
- ✅ 高对比度 - 优秀可读性
- ✅ 充裕留白 - 呼吸感强
- ✅ 微妙阴影 - 精致层次感

## 📦 安装步骤

### 1. 引入 Kimi 主题文件

在 `src/index.css` 中添加：

```css
/* 在现有导入后添加 */
@import './styles/kimi-theme.css';
@import './styles/kimi-components.css';
```

### 2. 替换主题类名

将组件中的 `bird-` 前缀替换为 `kimi-`：

**Before:**
```tsx
<button className="bird-btn bird-btn-primary">提交</button>
<input className="bird-input" placeholder="请输入..." />
```

**After:**
```tsx
<button className="kimi-btn kimi-btn-primary">提交</button>
<input className="kimi-input" placeholder="请输入..." />
```

### 3. 更新 CSS 变量引用

全局搜索替换：

```bash
# 查找所有 bird- 变量
--bird-primary-600 → --kimi-black
--bird-input-radius → --kimi-input-radius
--bird-text-primary → --kimi-text-primary
# ... 等等
```

## 🎯 关键样式差异

### 按钮样式

| 属性 | Ui2 (当前) | Kimi (新) |
|------|-----------|----------|
| 主色 | `#7c3aed` (紫色) | `#1a1a1a` (黑色) |
| 强调色 | 紫色渐变 | `#0066ff` (蓝色) |
| 圆角 | `12px` | `10px` |
| 阴影 | 明显 | 微妙 |

### 输入框样式

| 属性 | Ui2 (当前) | Kimi (新) |
|------|-----------|----------|
| 圆角 | `9999px` (全圆) | `8px` (适度) |
| 背景 | `#ffffff` | `#fafafa` (浅灰) |
| 焦点边框 | 紫色 `#7c3aed` | 黑色 `#1a1a1a` |
| 高度 | `32px` | `32px` (保持一致) |

### 卡片样式

| 属性 | Ui2 (当前) | Kimi (新) |
|------|-----------|----------|
| 圆角 | `16px` | `12px` |
| 边框 | `#e5e7eb` | `#e5e5e5` |
| 阴影 | `shadow-sm` | 更微妙 |
| 悬停效果 | 明显阴影提升 | 轻微阴影变化 |

## 🔧 快速迁移脚本

使用以下命令批量替换：

```bash
# 备份当前文件
cp src/styles/bird-theme.css src/styles/bird-theme.css.bak
cp src/styles/bird-components.css src/styles/bird-components.css.bak

# 全局替换类名前缀
find src -type f -name "*.tsx" -o -name "*.ts" | xargs sed -i '' 's/\bbird-btn\b/kimi-btn/g'
find src -type f -name "*.tsx" -o -name "*.ts" | xargs sed -i '' 's/\bbird-input\b/kimi-input/g'
find src -type f -name "*.tsx" -o -name "*.ts" | xargs sed -i '' 's/\bbird-card\b/kimi-card/g'
find src -type f -name "*.tsx" -o -name "*.ts" | xargs sed -i '' 's/\bbird-\([a-z-]*\)/kimi-\1/g'
```

## 📋 组件迁移清单

### 高优先级组件
- [x] 按钮 (`kimi-btn`)
- [x] 输入框 (`kimi-input`)
- [x] 卡片 (`kimi-card`)
- [x] 表格 (`kimi-table`)
- [x] 对话框 (`kimi-modal`)
- [x] 徽章 (`kimi-badge`)
- [x] 表单 (`kimi-form-*`)

### 中优先级组件
- [ ] 下拉菜单 (`kimi-dropdown`)
- [ ] 复选框 (`kimi-checkbox`)
- [ ] 开关 (`kimi-switch`)
- [ ] 侧边栏 (`kimi-sidebar`)

### 可选组件
- [ ] 工具提示 (`kimi-tooltip`)
- [ ] 分割线 (`kimi-divider`)

## 🎨 自定义扩展

如需调整特定颜色或样式，可在 `src/index.css` 中覆盖 CSS 变量：

```css
:root {
  /* 覆盖 Kimi 主题默认值 */
  --kimi-black: #000000;  /* 更黑的黑色 */
  --kimi-blue: #0066ff;   /* 自定义蓝色 */
  --kimi-radius-lg: 12px; /* 调整圆角 */
}
```

## ✅ 验证清单

应用新主题后，检查以下内容：

- [ ] 所有按钮样式正确显示
- [ ] 输入框圆角适中 (非全圆)
- [ ] 卡片边框和阴影符合 Kimi 风格
- [ ] 文本对比度足够 (WCAG AA 标准)
- [ ] 深色模式正常工作
- [ ] 响应式布局未被破坏
- [ ] 所有交互状态 (hover/focus/active) 正常

## 📸 视觉对比示例

参见：`KIMI_DESIGN_COMPARISON.svg` (可视化对比图)

## 🚀 下一步

1. **测试驱动**: 在开发环境验证所有组件
2. **用户测试**: 收集用户对新设计的反馈
3. **性能优化**: 确保新主题不会影响加载速度
4. **文档更新**: 更新组件文档和设计规范

---

**创建时间**: 2026-07-28  
**基于版本**: Kimi.com Design System 2024  
**兼容性**: React 19+, TailwindCSS 4+, Vite 6+
