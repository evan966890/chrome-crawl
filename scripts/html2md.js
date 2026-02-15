// html2md.js — 在浏览器 eval 中运行的 HTML→Markdown 转换器
// 用法: agent-browser --cdp $CDP_PORT eval "$(cat ~/.openclaw/scripts/html2md.js)"
//
// 提取页面主内容区域并转换为 Markdown 格式。
// 返回字符串直接重定向到文件: > /tmp/page.md

(() => {
  // 找到主内容区域
  const root = document.querySelector('article, main, [role="main"], .post-body, .entry-content, .article-content, .content')
    || document.body;

  function escape(text) {
    return text.replace(/([\\`*_{}[\]()#+\-.!|])/g, '\\$1');
  }

  function walk(node, listDepth) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent.replace(/\s+/g, ' ');
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return '';

    const tag = node.tagName.toLowerCase();
    const children = () => Array.from(node.childNodes).map(c => walk(c, listDepth)).join('');

    // 跳过不可见元素和脚本/样式
    if (['script', 'style', 'noscript', 'svg', 'nav', 'footer', 'header'].includes(tag)) return '';
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return '';

    switch (tag) {
      case 'h1': return '\n\n# ' + node.innerText.trim() + '\n\n';
      case 'h2': return '\n\n## ' + node.innerText.trim() + '\n\n';
      case 'h3': return '\n\n### ' + node.innerText.trim() + '\n\n';
      case 'h4': return '\n\n#### ' + node.innerText.trim() + '\n\n';
      case 'h5': return '\n\n##### ' + node.innerText.trim() + '\n\n';
      case 'h6': return '\n\n###### ' + node.innerText.trim() + '\n\n';

      case 'p': return '\n\n' + children().trim() + '\n\n';
      case 'br': return '\n';
      case 'hr': return '\n\n---\n\n';

      case 'strong': case 'b': return '**' + children().trim() + '**';
      case 'em': case 'i': return '*' + children().trim() + '*';
      case 'del': case 's': return '~~' + children().trim() + '~~';
      case 'code': return '`' + node.innerText + '`';

      case 'pre': {
        const code = node.querySelector('code');
        const lang = code?.className?.match(/language-(\w+)/)?.[1] || '';
        const text = (code || node).innerText;
        return '\n\n```' + lang + '\n' + text + '\n```\n\n';
      }

      case 'blockquote': return '\n\n> ' + children().trim().replace(/\n/g, '\n> ') + '\n\n';

      case 'a': {
        const href = node.getAttribute('href');
        const text = node.innerText.trim();
        if (!text) return '';
        if (!href || href.startsWith('javascript:')) return text;
        return '[' + text + '](' + href + ')';
      }

      case 'img': {
        const alt = node.getAttribute('alt') || '';
        const src = node.getAttribute('src') || '';
        if (!src) return '';
        return '![' + alt + '](' + src + ')';
      }

      case 'ul': return '\n' + Array.from(node.children).map(li => {
        const indent = '  '.repeat(listDepth);
        return indent + '- ' + walk(li, listDepth + 1).trim();
      }).join('\n') + '\n';

      case 'ol': return '\n' + Array.from(node.children).map((li, i) => {
        const indent = '  '.repeat(listDepth);
        return indent + (i + 1) + '. ' + walk(li, listDepth + 1).trim();
      }).join('\n') + '\n';

      case 'li': return children();

      case 'table': {
        const rows = Array.from(node.querySelectorAll('tr'));
        if (rows.length === 0) return '';
        const matrix = rows.map(tr =>
          Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim().replace(/\|/g, '\\|'))
        );
        const colCount = Math.max(...matrix.map(r => r.length));
        const padded = matrix.map(r => {
          while (r.length < colCount) r.push('');
          return r;
        });
        let md = '\n\n| ' + padded[0].join(' | ') + ' |\n';
        md += '| ' + padded[0].map(() => '---').join(' | ') + ' |\n';
        for (let i = 1; i < padded.length; i++) {
          md += '| ' + padded[i].join(' | ') + ' |\n';
        }
        return md + '\n';
      }

      case 'div': case 'section': case 'article': case 'main': case 'span': case 'figure': case 'figcaption':
        return children();

      default: return children();
    }
  }

  let md = walk(root, 0);
  // 清理多余空行
  md = md.replace(/\n{3,}/g, '\n\n').trim();
  return md;
})()
