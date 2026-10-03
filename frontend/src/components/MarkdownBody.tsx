import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';

type MarkdownBodyProps = {
  text: string;
  className?: string;
};

function heading(children: ReactNode) {
  return (
    <h3 className="mb-2 mt-4 text-base font-semibold text-[var(--text-primary)] first:mt-0">
      {children}
    </h3>
  );
}

export default function MarkdownBody({ text, className }: MarkdownBodyProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => heading(children),
          h2: ({ children }) => heading(children),
          h3: ({ children }) => heading(children),
          p: ({ children }) => <p className="mb-2 leading-6 last:mb-0">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
          ),
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="leading-6">{children}</li>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
