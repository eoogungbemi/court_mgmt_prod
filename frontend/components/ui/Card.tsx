import clsx from "clsx";

interface Props {
  children:  React.ReactNode;
  className?: string;
  title?:    string;
  action?:   React.ReactNode;
}

export default function Card({ children, className, title, action }: Props) {
  return (
    <div className={clsx("rounded-lg bg-white shadow-sm ring-1 ring-gray-200", className)}>
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          {title && <h3 className="text-sm font-semibold text-gray-700">{title}</h3>}
          {action}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}
