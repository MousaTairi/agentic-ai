/* DOM-only Markdown rendering. Never insert model HTML into the document. */
function renderSafeMarkdown(text) {
  const root = document.createElement('div'); root.className = 'markdown';
  const source = String(text).replace(/\r\n?/g, '\n').replace(/<br\s*\/?>/gi, '\u0000');
  const fence = String.fromCharCode(96).repeat(3);
  function inline(parent, value) {
    if (value.includes('\u0000')) {
      value.split('\u0000').forEach((part,index) => {if(index) parent.append(document.createElement('br'));inline(parent,part);});
      return;
    }
    const pattern = /(\*\*([^*]+)\*\*|\x60([^\x60]+)\x60|\bPOL[-‑](\d{2})\b)/g;
    let last = 0, match;
    while ((match = pattern.exec(value))) {
      parent.append(document.createTextNode(value.slice(last, match.index)));
      const node = document.createElement(match[2] ? 'strong' : match[3] ? 'code' : 'span');
      if (match[4]) node.className = 'policy-citation';
      node.textContent = match[2] || match[3] || 'POL-' + match[4]; parent.append(node); last = pattern.lastIndex;
    }
    parent.append(document.createTextNode(value.slice(last)));
  }
  const lines = source.split('\n');
  for (let i = 0; i < lines.length;) {
    const line = lines[i].trim();
    if (!line || /^[-_*]{3,}$/.test(line)) { i++; continue; }
    if (line.startsWith(fence)) {
      const code = document.createElement('code'), pre = document.createElement('pre'); i++;
      const content = [];
      while (i < lines.length && !lines[i].trim().startsWith(fence)) content.push(lines[i++]);
      i++; code.textContent = content.join('\n'); pre.append(code); root.append(pre); continue;
    }
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      const wrapper = document.createElement('div'); wrapper.className = 'table-scroll';
      const table = document.createElement('table');
      function cells(value) { return value.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(x => x.trim()); }
      const header = document.createElement('tr');
      for (const value of cells(line)) { const cell = document.createElement('th'); inline(cell, value); header.append(cell); }
      const head = document.createElement('thead'); head.append(header); table.append(head); i += 2;
      const body = document.createElement('tbody');
      while (i < lines.length && lines[i].includes('|')) {
        const row = document.createElement('tr');
        for (const value of cells(lines[i++])) { const cell = document.createElement('td'); inline(cell, value); row.append(cell); }
        body.append(row);
      }
      table.append(body); wrapper.append(table); root.append(wrapper); continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) { const node = document.createElement('h4'); inline(node, heading[2]); root.append(node); i++; continue; }
    const item = line.match(/^(?:[-*•]\s+|\d+[.)]\s+)(.+)$/);
    if (item) {
      const ordered = /^\d/.test(line), list = document.createElement(ordered ? 'ol' : 'ul');
      while (i < lines.length) {
        const next = lines[i].trim().match(ordered ? /^\d+[.)]\s+(.+)$/ : /^[-*•]\s+(.+)$/);
        if (!next) break;
        const li = document.createElement('li'); inline(li, next[1]); list.append(li); i++;
      }
      root.append(list); continue;
    }
    const paragraph = document.createElement('p'); inline(paragraph, line); root.append(paragraph); i++;
  }
  return root;
}
