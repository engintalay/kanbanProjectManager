import html
import re
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="render_jira_markup")
def render_jira_markup(text):
    """
    Renders Jira wiki markup (or Markdown / plain text) safely into rich HTML.
    Prevents XSS by escaping HTML entities first.
    """
    if not text or not str(text).strip():
        return ""

    content = html.escape(str(text).strip())
    placeholders = {}
    p_counter = 0

    def store_placeholder(html_snippet: str) -> str:
        nonlocal p_counter
        token = f"__JIRA_BLOCK_{p_counter}__"
        placeholders[token] = html_snippet
        p_counter += 1
        return token

    # 1. Jira Code Blocks: {code:python} ... {code} or {code} ... {code}
    def repl_code_jira(m):
        meta = m.group(1) or ""
        code_text = m.group(2).strip("\r\n")
        lang_or_title = meta.strip(":").strip() if meta else ""
        header = f'<div class="jira-code-header">🖥️ {html.escape(lang_or_title)}</div>' if lang_or_title else ""
        block = f'<div class="jira-code-container">{header}<pre class="jira-code-block"><code>{code_text}</code></pre></div>'
        return store_placeholder(block)

    content = re.sub(r"\{code(?::([^}]*))?\}(.*?)\{code\}", repl_code_jira, content, flags=re.DOTALL | re.IGNORECASE)

    # 2. Noformat Blocks: {noformat} ... {noformat}
    def repl_noformat(m):
        code_text = m.group(1).strip("\r\n")
        block = f'<div class="jira-code-container"><pre class="jira-code-block"><code>{code_text}</code></pre></div>'
        return store_placeholder(block)

    content = re.sub(r"\{noformat\}(.*?)\{noformat\}", repl_noformat, content, flags=re.DOTALL | re.IGNORECASE)

    # 3. Markdown Triple Backticks: ```python ... ```
    def repl_code_md(m):
        lang = m.group(1) or ""
        code_text = m.group(2).strip("\r\n")
        header = f'<div class="jira-code-header">🖥️ {html.escape(lang.strip())}</div>' if lang.strip() else ""
        block = f'<div class="jira-code-container">{header}<pre class="jira-code-block"><code>{code_text}</code></pre></div>'
        return store_placeholder(block)

    content = re.sub(r"```([a-zA-Z0-9_\-]+)?\n?(.*?)```", repl_code_md, content, flags=re.DOTALL)

    # 4. Jira Panels: {panel:title=...}...{panel}
    def repl_panel(m):
        params = m.group(1) or ""
        body = m.group(2).strip()
        title_match = re.search(r"title=([^|]+)", params)
        title_text = title_match.group(1).strip() if title_match else ""
        header = f'<div class="jira-panel-title">📌 {html.escape(title_text)}</div>' if title_text else ""
        block = f'<div class="jira-panel">{header}<div class="jira-panel-body">{body}</div></div>'
        return store_placeholder(block)

    content = re.sub(r"\{panel(?::([^}]*))?\}(.*?)\{panel\}", repl_panel, content, flags=re.DOTALL | re.IGNORECASE)

    # 5. Jira Callouts: {info}, {tip}, {warning}, {note}
    callout_configs = [
        ("info", "ℹ️", "jira-callout-info"),
        ("tip", "💡", "jira-callout-tip"),
        ("warning", "⚠️", "jira-callout-warn"),
        ("note", "📝", "jira-callout-note"),
    ]
    for tag, icon, css_cls in callout_configs:
        def repl_callout(m, icon_str=icon, cls_str=css_cls):
            body = (m.group(1) or m.group(2) or "").strip()
            block = f'<div class="jira-callout {cls_str}"><span class="jira-callout-icon">{icon_str}</span><div class="jira-callout-body">{body}</div></div>'
            return store_placeholder(block)
        pattern = rf"\{{{tag}\}}(.*?)\{{/{tag}\}}|\{{{tag}\}}(.*?)\{{{tag}\}}"
        content = re.sub(pattern, repl_callout, content, flags=re.DOTALL | re.IGNORECASE)

    # 6. Quotes: {quote}...{quote}
    def repl_quote_block(m):
        body = m.group(1).strip()
        block = f'<blockquote class="jira-quote">{body}</blockquote>'
        return store_placeholder(block)

    content = re.sub(r"\{quote\}(.*?)\{quote\}", repl_quote_block, content, flags=re.DOTALL | re.IGNORECASE)

    # 7. Tables: ||Header|| or |Cell|
    def repl_table(m):
        table_text = m.group(0)
        lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
        html_rows = []
        for line in lines:
            if line.startswith("||") and line.endswith("||"):
                cells = [c.strip() for c in line.strip("|").split("||")]
                cells_html = "".join(f"<th>{c}</th>" for c in cells if c != "")
                html_rows.append(f"<tr>{cells_html}</tr>")
            elif line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                cells_html = "".join(f"<td>{c}</td>" for c in cells if c != "")
                html_rows.append(f"<tr>{cells_html}</tr>")
        if html_rows:
            tbody_html = "".join(html_rows)
            table_html = f'<div class="jira-table-wrap"><table class="jira-table"><tbody>{tbody_html}</tbody></table></div>'
            return store_placeholder(table_html)
        return table_text

    content = re.sub(r"((?:^(?:\|\||\|).*(?:\r?\n|$))+)", repl_table, content, flags=re.MULTILINE)

    # 8. Headings: h1. to h6. and # to ######
    for i in range(1, 7):
        content = re.sub(rf"(?m)^h{i}\.\s+(.*)$", rf'<h{i} class="jira-h{i}">\1</h{i}>', content)
    for i in range(6, 0, -1):
        h_hashes = "#" * i
        content = re.sub(rf"(?m)^{h_hashes}\s+(.*)$", rf'<h{i} class="jira-h{i}">\1</h{i}>', content)

    # 9. Blockquote single line: bq. or >
    content = re.sub(r"(?m)^bq\.\s+(.*)$", r'<blockquote class="jira-quote">\1</blockquote>', content)
    content = re.sub(r"(?m)^&gt;\s+(.*)$", r'<blockquote class="jira-quote">\1</blockquote>', content)

    # 10. Horizontal Rules: ---- or ---
    content = re.sub(r"(?m)^(?:-{3,}|_{3,}|\*{3,})$", r'<hr class="jira-divider">', content)

    # 11. Links: [label|url] or [url] or [label](url)
    def repl_jira_link(m):
        full = m.group(1)
        if "|" in full:
            parts = full.split("|", 1)
            label = parts[0].strip()
            url = parts[1].strip()
        else:
            label = full.strip()
            url = full.strip()
        safe_url = url if (url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:") or url.startswith("/")) else f"https://{url}"
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="jira-link">{label} ↗</a>'

    content = re.sub(r"\[([^\]\n]+)\](?!\()", repl_jira_link, content)

    def repl_md_link(m):
        label = m.group(1).strip()
        url = m.group(2).strip()
        safe_url = url if (url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:") or url.startswith("/")) else f"https://{url}"
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="jira-link">{label} ↗</a>'

    content = re.sub(r"\[([^\]\n]+)\]\(([^)\n]+)\)", repl_md_link, content)

    # 12. Inline Code: {{monospace}} or `code`
    content = re.sub(r"\{\{([^\n{}]+)\}\}", r'<code class="jira-inline-code">\1</code>', content)
    content = re.sub(r"`([^`\n]+)`", r'<code class="jira-inline-code">\1</code>', content)

    # 13. Text Formatting (Bold, Italic, Underline, Strikethrough)
    content = re.sub(r"\*\*([^\n*]+)\*\*", r"<strong>\1</strong>", content)
    content = re.sub(r"(?<!\w)\*([^\n*]+)\*(?!\w)", r"<strong>\1</strong>", content)
    content = re.sub(r"(?<!\w)_([^\n_]+)_(?!\w)", r"<em>\1</em>", content)
    content = re.sub(r"(?<!\w)\+([^\n+]+)\+(?!\w)", r"<u>\1</u>", content)
    content = re.sub(r"~~([^\n~]+)~~", r"<del>\1</del>", content)
    content = re.sub(r"(?<!\w)-([^\n\-]+)-(?!\w)", r"<del>\1</del>", content)

    # 14. Lists: * bullet or # numbered
    def repl_lists(text_block):
        lines = text_block.split("\n")
        in_ul = False
        in_ol = False
        res = []
        for line in lines:
            stripped = line.strip()
            m_ul = re.match(r"^(?:[\*\-]\s+)(.*)$", stripped)
            m_ol = re.match(r"^(?:#|\d+\.)\s+(.*)$", stripped)
            if m_ul:
                if in_ol:
                    res.append("</ol>")
                    in_ol = False
                if not in_ul:
                    res.append('<ul class="jira-list">')
                    in_ul = True
                res.append(f"<li>{m_ul.group(1)}</li>")
            elif m_ol:
                if in_ul:
                    res.append("</ul>")
                    in_ul = False
                if not in_ol:
                    res.append('<ol class="jira-list">')
                    in_ol = True
                res.append(f"<li>{m_ol.group(1)}</li>")
            else:
                if in_ul:
                    res.append("</ul>")
                    in_ul = False
                if in_ol:
                    res.append("</ol>")
                    in_ol = False
                res.append(line)
        if in_ul:
            res.append("</ul>")
        if in_ol:
            res.append("</ol>")
        return "\n".join(res)

    content = repl_lists(content)

    # 15. Paragraphs & Line Breaks
    lines = content.split("\n")
    processed = []
    for line in lines:
        s = line.strip()
        if (
            s.startswith("<h") or s.startswith("</h") or
            s.startswith("<ul") or s.startswith("</ul") or
            s.startswith("<ol") or s.startswith("</ol") or
            s.startswith("<li") or
            s.startswith("<blockquote") or s.startswith("</blockquote") or
            s.startswith("<table") or s.startswith("</table") or
            s.startswith("<div") or s.startswith("</div") or
            s.startswith("<hr") or
            "__JIRA_BLOCK_" in s
        ):
            processed.append(line)
        elif s == "":
            processed.append('<div class="jira-spacer"></div>')
        else:
            processed.append(f'<p class="jira-p">{line}</p>')

    content = "\n".join(processed)

    # 16. Restore Placeholders
    for token, block_html in placeholders.items():
        content = content.replace(f'<p class="jira-p">{token}</p>', block_html)
        content = content.replace(token, block_html)

    return mark_safe(content)
