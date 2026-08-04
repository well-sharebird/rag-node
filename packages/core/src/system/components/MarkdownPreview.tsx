import { MarkdownRenderer } from '@/src/components/MarkdownRenderer';

const markdownContent = `
# Markdown 渲染示例

支持代码块、数学公式、Mermaid 图表、提示卡片、JSON 树形视图等多种格式。

## 1. 提示/警告卡片 (Admonitions)

:::tip
这是一条实用技巧。提示卡片用于展示建议性的内容。
:::

:::note
这是一条备注信息。用于补充说明相关内容。
:::

:::info
这是一条一般性信息。用于提供额外背景知识。
:::

:::warning
这是一条警告。提醒用户注意潜在问题。
:::

:::danger
这是一条危险警告。提示严重风险或禁止事项。
:::

## 2. 代码块

### Python 代码
\`\`\`python
def fibonacci(n: int) -> list[int]:
    """生成斐波那契数列"""
    if n <= 0:
        return []
    sequence = [0, 1]
    while len(sequence) < n:
        sequence.append(sequence[-1] + sequence[-2])
    return sequence
\`\`\`

## 3. 数学公式

行内公式：$E = mc^2$

块级公式：
$$
\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}
$$

## 4. 流程图

\`\`\`mermaid
graph TD
    A[开始] --> B{条件判断}
    B -->|是 | C[执行操作 A]
    B -->|否 | D[执行操作 B]
    C --> E[结束]
    D --> E
\`\`\`

## 5. 时序图

\`\`\`mermaid
sequenceDiagram
    participant U as 用户
    participant F as 前端
    participant B as 后端
    U->>F: 提交请求
    F->>B: API 调用
    B-->>F: 返回结果
    F-->>U: 显示响应
\`\`\`

## 6. 思维导图 (Mind Map)

\`\`\`mermaid
mindmap
  root((RAG 系统))
    数据源
      本地文件
      网页抓取
      数据库
      API 接口
    处理流程
      文档解析
      文本分块
      向量化
      索引构建
    查询服务
      检索
      重排序
      生成回答
\`\`\`

## 7. 甘特图 (Gantt)

\`\`\`mermaid
gantt
    title 项目开发计划
    dateFormat  YYYY-MM-DD
    section 设计阶段
    需求分析      :done,    des1, 2024-01-01, 2024-01-15
    架构设计      :active,  des2, 2024-01-16, 2024-01-31
    section 开发阶段
    前端开发      :         dev1, 2024-02-01, 30d
    后端开发      :         dev2, 2024-02-01, 30d
    section 测试
    单元测试      :         test1, 2024-03-01, 15d
    集成测试      :         test2, 2024-03-16, 15d
\`\`\`

## 8. 用户旅程图 (Journey)

\`\`\`mermaid
journey
    title 用户使用流程
    section 注册阶段
      访问网站：5: 用户
      填写信息：3: 用户
      验证邮箱：4: 用户
    section 使用阶段
      上传文档：5: 用户
      提问查询：5: 用户
      查看结果：4: 用户
\`\`\`

## 9. JSON 树形视图

\`\`\`json-tree
{
  "user": {
    "id": 12345,
    "name": "张三",
    "email": "zhangsan@example.com",
    "roles": ["admin", "editor"],
    "profile": {
      "avatar": "https://example.com/avatar.jpg",
      "bio": "软件工程师",
      "location": "北京"
    },
    "settings": {
      "theme": "dark",
      "language": "zh-CN",
      "notifications": {
        "email": true,
        "push": false
      }
    }
  },
  "permissions": {
    "read": true,
    "write": true,
    "delete": false
  }
}
\`\`\`

## 10. 表格

| 功能 | 状态 | 优先级 | 负责人 |
|:-----|:----:|-------:|--------|
| Markdown 渲染 | ✅ 完成 | 高 | 张三 |
| 提示卡片 | ✅ 完成 | 高 | 李四 |
| JSON 树视图 | ✅ 完成 | 中 | 王五 |
| 思维导图 | ✅ 完成 | 中 | 赵六 |

## 11. 列表

### 无序列表
- 第一项
  - 子项 1
  - 子项 2
- 第二项
- 第三项

### 有序列表
1. 第一步：准备环境
2. 第二步：安装依赖
3. 第三步：运行测试

### 任务列表
- [x] 完成需求分析
- [x] 完成架构设计
- [ ] 进行开发实现
- [ ] 执行测试验证

## 12. 引用

> 这是一段引用文字，用于强调重要内容或引用他人观点。
>
> 引用可以包含多段内容。

## 13. 链接

- [Google](https://www.google.com) - 外部链接
- [GitHub](https://github.com)
`;

export function MarkdownPreview() {
  return (
    <div className="h-full overflow-auto bg-gray-50">
      <header className="h-[52px] px-5 bg-white flex items-center border-b border-gray-200">
        <h1 className="text-[15px] font-medium text-gray-900">Markdown 渲染预览</h1>
      </header>
      <div className="p-6 max-w-4xl mx-auto bg-white rounded-lg shadow-sm m-4">
        <MarkdownRenderer content={markdownContent} />
      </div>
    </div>
  );
}
