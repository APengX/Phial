"""A single, self-contained reference document in Phial's default design
language. It is shipped *inside* the generation prompt (see `html_agent.py`)
so the model has a concrete, copyable example rather than a prose spec.

The reference is itself a valid Phial document: warm editorial palette,
serif headings, a "30-second read" (`.tldr`) card, collapsibles, a callout,
mono pills, a code block, and the `window.phial` bridge wired up. The design
tokens match the html-effectiveness "Acme" set exactly (clay #D97757, rust
#B04A3F, sky #6A8CAF, ivory #FAF9F5, …) with CJK-aware font fallbacks added.

Keep this file lean — it costs prompt tokens on every create call.
"""

# A compact but complete document. Edit this when the design language changes;
# generated documents follow whatever this file demonstrates.
REFERENCE_DOC = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>文档示例 · Phial 设计语言</title>
<style>
  :root {
    /* 暖色 editorial 色板 —— 所有 Phial 文档共用这一套 */
    --ivory:#FAF9F5; --white:#FFFFFF; --slate:#141413;
    --clay:#D97757; --clay-d:#B85C3E; --oat:#E3DACC; --olive:#788C5D;
    --rust:#B04A3F; --sky:#6A8CAF; --bronze:#C78E3F;
    --gray-100:#F0EEE6; --gray-300:#D1CFC5; --gray-500:#87867F; --gray-700:#3D3D3A;
    --serif: ui-serif, Georgia, "Songti SC", "Source Han Serif SC", serif;
    --sans: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--ivory); color: var(--gray-700);
    font-family: var(--sans); font-size: 15px; line-height: 1.65;
    -webkit-font-smoothing: antialiased; padding: 56px 24px 120px;
  }
  .wrap { max-width: 720px; margin: 0 auto; }

  .eyebrow {
    font-family: var(--mono); font-size: 11px; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--gray-500); margin-bottom: 10px;
  }
  h1 {
    font-family: var(--serif); font-weight: 500; font-size: 32px;
    color: var(--slate); letter-spacing: -0.01em; margin-bottom: 16px;
  }
  h2 {
    font-family: var(--serif); font-weight: 500; font-size: 22px;
    color: var(--slate); letter-spacing: -0.01em; margin: 40px 0 14px;
  }
  p { margin-bottom: 12px; max-width: 680px; }
  a { color: var(--clay-d); }
  code {
    font-family: var(--mono); font-size: 13px;
    background: var(--gray-100); padding: 1px 5px; border-radius: 4px;
  }

  /* 30 秒速读 —— 每篇正文型文档开头都放一个 */
  .tldr {
    border: 1.5px solid var(--gray-300); border-left: 3px solid var(--clay);
    border-radius: 10px; background: var(--white);
    padding: 16px 18px; margin-bottom: 28px;
  }
  .tldr .k {
    font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--clay-d); margin-bottom: 6px;
  }
  .tldr p { margin: 0; color: var(--slate); }

  /* 提示框 */
  .callout {
    display: flex; gap: 12px; border: 1.5px solid var(--oat);
    background: rgba(227,218,204,0.35); border-radius: 10px;
    padding: 14px 16px; margin: 18px 0; font-size: 14px;
  }
  .callout .ico { color: var(--clay); font-weight: 600; }

  /* 折叠块 —— 次要细节收进来 */
  details {
    border: 1.5px solid var(--gray-300); border-radius: 10px;
    background: var(--white); margin: 14px 0; overflow: hidden;
  }
  summary {
    list-style: none; cursor: pointer; padding: 13px 16px;
    font-family: var(--serif); font-size: 16px; color: var(--slate);
    display: flex; align-items: baseline; gap: 10px;
  }
  summary::-webkit-details-marker { display: none; }
  summary::before {
    content: "\\25B8"; color: var(--clay); font-family: var(--sans);
    font-size: 12px; transition: transform 120ms;
  }
  details[open] summary::before { transform: rotate(90deg); }
  details .body { padding: 0 16px 16px; font-size: 14px; }

  /* 胶囊标签 */
  .pill {
    display: inline-flex; align-items: center; font-family: var(--mono);
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
    border-radius: 999px; padding: 2px 9px;
    background: var(--gray-100); color: var(--gray-700);
  }
  .pill.clay { background: #F5E2D8; color: var(--clay-d); }

  /* 代码块 —— 深色,衬在暖色页面上 */
  pre {
    font-family: var(--mono); font-size: 12.5px; line-height: 1.6;
    background: var(--slate); color: var(--ivory);
    border-radius: 10px; padding: 16px 18px; overflow-x: auto; margin: 16px 0;
  }
</style>
</head>
<body>
  <div class="wrap">
    <div class="eyebrow">文档示例 · Phial 设计语言</div>
    <h1>一篇 Phial 文档应有的样子</h1>

    <div class="tldr">
      <div class="k">30 秒速读</div>
      <p>每篇文档开头放一个这样的速读卡:两三句话讲清「这是什么、给谁看、看完能干什么」。陶土色左边线让它在象牙白页面上第一眼就被看到。</p>
    </div>

    <p>正文用系统无衬线体,字号 15px、行高 1.65,段落限宽在 <code>max-width: 680px</code> 以内;标题用衬线体,营造安静的 editorial 气质。强调色是陶土橙,只用在小处——左边线、折叠三角、链接——不大面积铺。</p>

    <h2>用结构,而不是大段文字</h2>
    <p>能折叠就折叠,能并排就并排。次要细节收进折叠块:</p>

    <details>
      <summary>点开看细节 <span class="pill clay">可选</span></summary>
      <div class="body">
        <p>把补充信息放进 <code>&lt;details&gt;</code>,读者按需展开,正文保持干净。</p>
      </div>
    </details>

    <div class="callout">
      <span class="ico">&#10022;</span>
      <div>提示框用燕麦色描边 + 半透明燕麦底,承载补充说明,不抢正文。</div>
    </div>

    <h2>需要交互时,接上 window.phial</h2>
    <p>文档里若有可操作的部分,状态变化时上报给宿主,让上游 AI 能接着上一步继续:</p>
    <pre>phial.setState({ read: true });</pre>
  </div>

  <script>
    // 文档加载完成,告诉宿主一声
    if (window.phial) {
      phial.ready();
      phial.setState({ opened: true });
    }
  </script>
</body>
</html>
"""
