/**
 * 调试脚本：打印前端收到的所有事件
 * 在 QAChatView.tsx 中添加日志
 */

// 在 handleStreamResponse 函数中添加日志
// 找到第 420 行左右的 for 循环，添加：

console.log('[DEBUG EVENT]', ev.type, {
  content: ev.content?.substring(0, 100),
  data: ev.data ? JSON.stringify(ev.data).substring(0, 100) : undefined
});

// 这样可以打印每个事件的类型和内容
