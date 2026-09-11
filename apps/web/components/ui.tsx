// IP — Caramurú Construções — assinatura do autor

import type { ButtonHTMLAttributes, HTMLAttributes } from "react";

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function Card({ className, children, ...props }: Omit<HTMLAttributes<HTMLDivElement>, "children"> & { children?: any }) {
  return <section className={cn("rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm dark:border-slate-700 dark:bg-slate-900/85", className)} {...props}>{children}</section>;
}

export function CardHeader({ className, children, ...props }: Omit<HTMLAttributes<HTMLDivElement>, "children"> & { children?: any }) {
  return <div className={cn("flex items-start justify-between gap-4 p-5", className)} {...props}>{children}</div>;
}

export function CardContent({ className, children, ...props }: Omit<HTMLAttributes<HTMLDivElement>, "children"> & { children?: any }) {
  return <div className={cn("px-5 pb-5", className)} {...props}>{children}</div>;
}

export function Button({ className, children, variant = "primary", ...props }: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & { children?: any; variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  const variants = {
    primary: "bg-caramuru-gold text-slate-950 hover:bg-amber-300",
    secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-white dark:hover:bg-slate-700",
    ghost: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
    danger: "bg-rose-600 text-white hover:bg-rose-500",
  };
  return <button className={cn("inline-flex min-h-10 items-center justify-center rounded-xl px-4 text-sm font-bold transition focus:outline-none focus:ring-2 focus:ring-caramuru-gold/70 disabled:cursor-not-allowed disabled:opacity-50", variants[variant], className)} {...props}>{children}</button>;
}

export function Badge({ children, tone = "slate" }: { children: any; tone?: "green" | "amber" | "red" | "blue" | "slate" }) {
  const tones = { green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300", amber: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300", red: "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300", blue: "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300", slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" };
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide", tones[tone])}>{children}</span>;
}

export function ProgressBar({ value, tone = "gold" }: { value: number; tone?: "gold" | "green" | "blue" }) {
  const colors = { gold: "bg-caramuru-gold", green: "bg-emerald-500", blue: "bg-blue-500" };
  return <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className={cn("h-full rounded-full transition-all", colors[tone])} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>;
}

export function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: any }) {
  return <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-[11px] font-black uppercase tracking-[0.18em] text-caramuru-gold">{eyebrow}</p><h2 className="mt-1 text-xl font-black tracking-tight text-slate-950 dark:text-white">{title}</h2>{description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>}</div>{action}</div>;
}
