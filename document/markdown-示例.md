# Markdown 语法示例

本文档展示阅读器支持的所有 Markdown 渲染效果。

---

## 文字样式

**粗体文字** 和 *斜体文字* 以及 ~~删除线~~，行内代码 `print("hello")`。

> 这是一段引用文字。
> 可以跨越多行。

---

## 代码块

```python
def fibonacci(n: int) -> list[int]:
    """生成斐波那契数列"""
    a, b = 0, 1
    result = []
    for _ in range(n):
        result.append(a)
        a, b = b, a + b
    return result

print(fibonacci(10))
```

```bash
# 启动服务
uv run python app.py

# 打包应用
uv run python build.py
```

```json
{
  "password": "your_password",
  "port": 5000,
  "docs_dir": "./document"
}
```

---

## 列表

### 无序列表

- 第一项
- 第二项
  - 嵌套项 A
  - 嵌套项 B
- 第三项

### 有序列表

1. 安装依赖
2. 配置密码
3. 启动服务
4. 打开浏览器

---

## 表格

| 语言 | 创建年份 | 主要用途 |
|------|---------|---------|
| Python | 1991 | 数据科学、Web、自动化 |
| Go | 2009 | 系统编程、云原生 |
| Rust | 2010 | 系统编程、WebAssembly |
| TypeScript | 2012 | 前端开发 |

---

## 链接与图片

[Flask 官方文档](https://flask.palletsprojects.com)

[Markdown 语法指南](https://www.markdownguide.org)

---

## 脚注

Markdown[^1] 是一种轻量级标记语言[^2]。

[^1]: 由 John Gruber 于 2004 年创建。
[^2]: 设计初衷是让文档源码保持可读性。

---

## 定义列表

Flask
: 一个轻量级的 Python Web 框架。

PyInstaller
: 将 Python 程序打包为独立可执行文件的工具。

---

## 水平分割线

以上是常用的 Markdown 元素，渲染效果清晰、美观。
