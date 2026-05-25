import clsx from "clsx";
import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size    = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?:    Size;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary:   "bg-court-navy text-white hover:bg-blue-900 disabled:bg-gray-400",
  secondary: "bg-white text-court-navy border border-court-navy hover:bg-gray-50",
  danger:    "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
  ghost:     "text-court-navy hover:bg-gray-100",
};

const sizes: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export default function Button({
  variant = "primary",
  size    = "md",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: Props) {
  return (
    <button
      className={clsx(
        "inline-flex items-center gap-2 rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-court-navy focus:ring-offset-2",
        variants[variant],
        sizes[size],
        (disabled || loading) && "cursor-not-allowed opacity-60",
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      )}
      {children}
    </button>
  );
}
