import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

const variantClass: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm hover:bg-slate-50",
  ghost: "rounded-xl px-3 py-2 text-sm text-slate-600 hover:bg-slate-100",
};

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode; variant?: Variant }) {
  return (
    <button type="button" className={`${variantClass[variant]} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}
