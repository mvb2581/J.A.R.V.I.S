import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  a: ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
  pre: ({ children }) => <pre className="md-pre">{children}</pre>,
  code: ({ className, children, ...props }) => (
    <code className={className ? `${className} md-code-block` : "md-code-inline"} {...props}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="md-table-wrap">
      <table>{children}</table>
    </div>
  ),
};

export function MarkdownText({ content }: { content: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
