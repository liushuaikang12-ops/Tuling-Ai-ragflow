import katex from 'katex';
import 'katex/dist/katex.min.css';

type MarkdownParser = (source: string) => string;

interface MathFragment {
  token: string;
  html: string;
}

const CODE_TOKEN_PREFIX = 'SKCODEPLACEHOLDER';
const MATH_TOKEN_PREFIX = 'SKMATHPLACEHOLDER';

/** Render Markdown while preserving code and converting LaTeX delimiters with KaTeX. */
export function renderMarkdownWithMath(source: string, parseMarkdown: MarkdownParser): string {
  const codeFragments: string[] = [];
  const mathFragments: MathFragment[] = [];

  // Math-looking text inside fenced or inline code must stay literal.
  let protectedSource = source.replace(/```[\s\S]*?```|`[^`\n]+`/g, (code) => {
    const token = `${CODE_TOKEN_PREFIX}${codeFragments.length}X`;
    codeFragments.push(code);
    return token;
  });

  const stashMath = (expression: string, displayMode: boolean) => {
    const token = `${MATH_TOKEN_PREFIX}${mathFragments.length}X`;
    const html = katex.renderToString(expression.trim(), {
      displayMode,
      throwOnError: false,
      strict: 'warn',
      trust: false,
      output: 'htmlAndMathml',
    });
    mathFragments.push({ token, html });
    return token;
  };

  protectedSource = protectedSource
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, expression: string) => stashMath(expression, true))
    .replace(/\$\$([\s\S]*?)\$\$/g, (_match, expression: string) => stashMath(expression, true))
    .replace(/\\\(([^\n]*?)\\\)/g, (_match, expression: string) => stashMath(expression, false))
    .replace(/(^|[^\\$])\$([^$\n]+?)\$/g, (match, prefix: string, expression: string) => {
      // Avoid treating ordinary prices such as "$100" as formulas.
      if (!/[\\_^{}=+*/<>]|[A-Za-z]\d|\d[A-Za-z]/.test(expression)) return match;
      return `${prefix}${stashMath(expression, false)}`;
    });

  codeFragments.forEach((code, index) => {
    protectedSource = protectedSource.replace(`${CODE_TOKEN_PREFIX}${index}X`, code);
  });

  let html = parseMarkdown(protectedSource);
  mathFragments.forEach((fragment) => {
    html = html.split(fragment.token).join(fragment.html);
  });
  return html;
}
