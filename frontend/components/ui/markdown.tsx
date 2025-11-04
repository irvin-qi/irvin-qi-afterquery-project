import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

type MarkdownProps = {
  className?: string;
  children?: string | null;
  components?: Components;
};

export function Markdown({ className, children, components }: MarkdownProps) {
  const linkRenderer: Components["a"] = components?.a
    ? components.a
    : ({ node: _node, ...props }) => (
        <a {...props} target="_blank" rel="noreferrer">
          {props.children}
        </a>
      );

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          ...components,
          a: linkRenderer,
        }}
      >
        {children ?? ""}
      </ReactMarkdown>
    </div>
  );
}
